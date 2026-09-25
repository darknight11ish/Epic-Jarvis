"""jarvis_entities.py - the OPTIONAL local-model pass of the entity layer.

WHAT IT IS, IN PLAIN WORDS

Every fact Jarvis saves is already linked to the people, pets, places and
things it names, by fixed rules and no model (rebuilt/jarvis_memory.py, "The
entity layer": capitalised names, and "my sister is called Priya" / "my
brother Arjun" / "Mario is my manager"). Those rules are English only and
miss names that are not capitalised or relations said another way.

This module can ALSO ask the local model to read the facts one learner pass
saved and name who and what is in them. It is OFF by default, and it is
UNMEASURED: nobody has run it against a real model and a known set of
answers yet, so nobody knows whether it helps more than it adds noise. Turn
it on only to measure it:

    jarvis-framework.toml   [memory.entities]  model_pass = true
    or the environment      JARVIS_ENTITY_MODEL=1

THE RULES IT KEEPS (the research sketch's, memresearch/graph/REPORT.md)

  * ONE model call per learner pass, batched over the facts saved in that
    pass, on a background thread - never on the chat path, never per fact.
  * This PC's model only: the address must be this machine (loopback) AND
    the model must not be a cloud model by name - the same two checks the
    learner and the sensitive-topic check make (jarvis_auto_learn
    .check_local_model). Otherwise nothing is sent anywhere.
  * Ollama's `format` is a JSON schema, so the answer has a fixed shape.
  * What comes back only ever ADDS links, and only through
    MemoryStore.link_entities, which drops any name or alias that is not in
    the fact's own text word for word, and keeps an alias only with a name
    from the same fact. The model can never retire, edit or hide a fact,
    and never merge two entries (that is always the owner's card).
  * Nothing is logged but counts. The facts' words go to the local model
    and nowhere else.

Standard library only.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Callable, Optional

#: The kinds the model may say. Anything else is stored as no kind.
KINDS = ("person", "pet", "place", "organisation", "project", "thing")

#: At most this many facts in the one call (a learner pass saves a few).
MAX_FACTS = 20

#: How long the one call may take. It is on a background thread.
TIMEOUT = 60.0

#: The shape Ollama is asked to answer in (its `format` field). The
#: sketch's schema: {"entities": [{"name", "kind", "aliases": []}]}.
SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "maxItems": 24,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "aliases": {"type": "array", "items": {"type": "string"},
                                "maxItems": 4},
                },
                "required": ["name", "kind", "aliases"],
            },
        },
    },
    "required": ["entities"],
}

# The rules are paraphrased from Graphiti's extract_nodes.py "never extract"
# list and its kinship rule (Apache-2.0), rewritten for one owner, and
# LightRAG's "do not fill the limit" (MIT). THIRD-PARTY-NOTICES.txt.
PROMPT = """You read short facts one person saved about their own life. List the \
specific people, pets, places, organisations and projects the facts name.

Rules:
- Copy each name exactly as it is written in the facts. Never invent, shorten \
or complete a name.
- Do not list the owner ("I", "me", "Owner"), pronouns, dates, times, numbers, \
amounts, feelings, actions, or general things ("the car", "work", "a wedding").
- A word the owner uses for someone (sister, boss, dentist, cat) is NOT a \
name. Put it in that name's "aliases" only when the SAME fact says both, as in \
"My sister is called Priya" (name "Priya", aliases ["sister"]).
- List fewer entities if fewer are there. Do not try to fill the list. An \
empty list is a good answer.

Facts:
{facts}
"""


def _config() -> dict:
    try:
        import jarvis_framework as fw
        mem = fw.load_framework().get("memory") or {}
        ent = mem.get("entities") if isinstance(mem, dict) else None
        return ent if isinstance(ent, dict) else {}
    except Exception:
        return {}


def enabled() -> bool:
    """Is the model pass switched on? OFF unless the config says exactly
    `model_pass = true` or JARVIS_ENTITY_MODEL is 1/true/on."""
    env = os.environ.get("JARVIS_ENTITY_MODEL", "").strip().lower()
    if env in ("1", "true", "on", "yes"):
        return True
    if env in ("0", "false", "off", "no"):
        return False
    return _config().get("model_pass") is True


def build_prompt(texts: list) -> str:
    lines = "\n".join(f"- {' '.join(str(t).split())}" for t in texts)
    return PROMPT.format(facts=lines)


def parse(raw) -> list:
    """The model's answer as [{"name", "kind", "aliases"}], or [] for
    anything that is not the JSON asked for. Shape only - whether a name is
    really in a fact is MemoryStore.link_entities's check."""
    try:
        got = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return []
    items = got.get("entities") if isinstance(got, dict) else None
    if not isinstance(items, list):
        return []
    out = []
    for it in items[:24]:
        if not isinstance(it, dict):
            continue
        name = it.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            continue
        kind = it.get("kind") if it.get("kind") in KINDS else None
        aliases = [a for a in (it.get("aliases") or [])
                   if isinstance(a, str) and a.strip() and len(a) <= 40][:4]
        out.append({"name": " ".join(name.split()), "kind": kind, "aliases": aliases})
    return out


def _local_check(ollama, model) -> str:
    """"" when (ollama, model) is this PC's own model; the reason otherwise.
    The learner's own check (address AND name), failing closed."""
    try:
        import jarvis_auto_learn
        return jarvis_auto_learn.check_local_model(ollama, model)
    except Exception:
        pass
    try:
        import jarvis_sensitive
        if not jarvis_sensitive._is_loopback(ollama):
            return "the learning model is not on this PC"
        if not model or jarvis_sensitive._remote(model):
            return "the learning model is a cloud model, not one on this PC"
        return ""
    except Exception:
        return "the local-model check could not run"


def _learner_model() -> tuple:
    try:
        import jarvis_sensitive
        return jarvis_sensitive.learner_model()
    except Exception:
        return (None, None)


def ollama_caller(url: str, model: str, timeout: float = TIMEOUT) -> Callable:
    """ask(prompt) -> text or None: one answer from this PC's Ollama, in the
    SCHEMA shape. Never through a proxy (jarvis_local_http). Raises
    nothing."""
    def ask(prompt: str) -> Optional[str]:
        import urllib.error
        import urllib.request
        body = {"model": model, "prompt": prompt, "stream": False, "format": SCHEMA,
                "think": False, "options": {"temperature": 0, "num_predict": 400}}
        for attempt in (1, 2):
            req = urllib.request.Request(
                str(url).rstrip("/") + "/api/generate",
                data=json.dumps(body).encode("utf-8"), method="POST",
                headers={"Content-Type": "application/json"})
            try:
                try:
                    import jarvis_local_http
                    resp = jarvis_local_http.urlopen(req, timeout)
                except ImportError:
                    resp = urllib.request.build_opener(
                        urllib.request.ProxyHandler({})).open(req, timeout=timeout)
                with resp as r:
                    out = json.loads(r.read().decode("utf-8") or "{}")
            except urllib.error.HTTPError as exc:
                if attempt == 1 and exc.code == 400 and "think" in body:
                    body.pop("think", None)
                    continue
                return None
            except Exception:
                return None
            text = out.get("response") if isinstance(out, dict) else None
            return text if isinstance(text, str) else None
        return None
    return ask


#: What the last pass did - counts only, never a word. For status and tests.
LAST: dict = {}


def run_pass(fact_ids, *, ollama: Optional[str] = None, model: Optional[str] = None,
             ask: Optional[Callable] = None, store=None, force: bool = False) -> dict:
    """ONE model call over these saved facts; each entity it names is linked
    to every one of them that says that name word for word. Returns counts:
    {"ran", "why", "facts", "entities", "linked"}. Never raises.

    `ask` (a test's stand-in model) and `force` skip the setting; nothing
    else does. Without `ask`, the model must pass the learner's local
    check, or nothing is sent."""
    out = {"ran": False, "why": "", "facts": 0, "entities": 0, "linked": 0}
    try:
        if not (force or ask is not None) and not enabled():
            out["why"] = "off"
            return out
        if store is None:
            import jarvis_memory
            store = jarvis_memory.store()
        facts = []
        now = time.time()
        for fid in list(fact_ids or [])[:MAX_FACTS]:
            if isinstance(fid, bool) or not isinstance(fid, int):
                continue
            f = store.get(fid)
            if (not f or f.get("erased_at") is not None
                    or (f.get("valid_to") is not None and float(f["valid_to"]) <= now)):
                continue
            facts.append((fid, str(f.get("text") or "")))
        out["facts"] = len(facts)
        if not facts:
            out["why"] = "no current facts"
            return out
        if ask is None:
            if ollama is None or model is None:
                u, m = _learner_model()
                ollama, model = ollama or u, model or m
            why = _local_check(ollama, model)
            if why:
                out["why"] = why
                return out
            ask = ollama_caller(ollama, model)
        raw = ask(build_prompt([t for _, t in facts]))
        out["ran"] = True
        ents = parse(raw)
        out["entities"] = len(ents)
        for fid, text in facts:
            found = {"names": [], "aliases": []}
            for e in ents:
                found["names"].append((e["name"], e["kind"]))
                found["aliases"] += [(a, e["name"]) for a in e["aliases"]]
            got = store.link_entities(fid, found)
            if got:
                out["linked"] += len(got.get("entities") or [])
    except Exception as exc:
        out["why"] = type(exc).__name__
    LAST.clear()
    LAST.update(out, at=time.time())
    return out


def after_learner_pass(saved_ids, *, ollama: Optional[str] = None,
                       model: Optional[str] = None) -> bool:
    """What jarvis_auto_learn.after_pass calls with the facts it just saved.
    Off (the default): does nothing and returns False. On: starts the one
    call on its own background thread and returns True at once."""
    if not saved_ids or not enabled():
        return False
    t = threading.Thread(target=run_pass, args=(list(saved_ids),),
                         kwargs={"ollama": ollama, "model": model},
                         name="jarvis-entities-model", daemon=True)
    t.start()
    return True
