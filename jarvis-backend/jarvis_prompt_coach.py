"""jarvis_prompt_coach.py - "Coach this": what is missing from a prompt.

The owner asked, 2026-10-08: *"Are there any GitHub repos that would help me
write better prompts and give me feedback? I'd like to integrate this as a
feature I can turn off and on in Jarvis."* The four libraries they were
offered are all rejected, with the evidence in
`docs/PROMPT-COACH-DESIGN.md`; the one that matters is that `promptimal`
requires an OpenAI API key and has no local-model support, so adopting it
would send the owner's own words to OpenAI - rule 1 broken. This module does
the job with the model already on the PC, and adds no dependency at all.

WHAT IT IS. The owner writes a question and presses **Coach this**. This module
reads that question (and, by the owner's decision of 2026-10-08, the last few
turns of the conversation, so "it" and "that" have an antecedent) and returns a
strict JSON critique: a score, up to four things that are missing, questions it
would have to ask, and one rewritten prompt. Both apps then offer "Send mine"
and "Send the suggestion".

WHAT IT IS NOT, and this is the part that must not drift:

* **It never sends anything.** It returns text. The owner sends either their
  own words or the suggestion, by pressing a button. There is no
  improve-and-send, and no mode where the coach is in the path of every
  message - the owner chose the button, with this switch as the master switch.
* **It approves nothing and acts on nothing.** No tool runs, no file is
  touched, no approval card is raised, and this module does not import
  `jarvis_gate`. A critique is advice, never a decision, and the score is never
  a gate: a 1 out of 10 is still sendable.
* **It never leaves the PC.** The model is found the house way, and the address
  is checked with `jarvis_auto_learn.check_local_model()` **before** the
  request is built - `jarvis_entities.py`'s shape, and the check fails closed.
* **Nothing is kept.** The prompt, the critique and the score are not written
  to chat history, not saved as a fact, not learned from and not counted. The
  words are the owner's own, and the critique is not a fact about them.
* **It is off until the owner turns it on.** `enabled()` reads a file and fails
  to off - missing, unreadable, malformed or not-a-bool all mean off.

WHY THE JUDGE IS WEAK, SAID PLAINLY. The model is an 8B one on the owner's own
PC. It is a mediocre prompt critic: it will miss things a strong model catches
and will sometimes be confidently wrong. That is the reason for the button
rather than an interceptor, and for "a critique with nothing to say is a valid
answer" below. The app's own line under the switch says so.

NO NEW DEPENDENCY, AND NOTHING CLEVER. Standard library only. The one HTTP call
goes through jarvis_local_http.urlopen (the helper that ignores a proxy) and
the model name comes from jarvis_sensitive.learner_model(), so nothing is
hardcoded here.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Callable, Optional

#: The file that holds the switch, in the Jarvis settings folder. Any *.json
#: directly in that folder is picked up by the locked backup automatically
#: (jarvis_backup.py), so a new file needs no backup edit.
SETTINGS_NAME = "prompt-coach.json"

#: What the owner sees. Second person, plain, the default stated first and the
#: consequence of each direction spelled out - the house style (see
#: jarvis_search.ENABLED_DETAIL). Neither direction raises a card, and the
#: detail says why: this reads words the chat is about to send to the same
#: local model anyway, takes no action, and opens no way out of the PC.
LABEL = "Prompt coach"
DETAIL = (
    "Off (the default): nothing is read and there is no Coach this button. "
    "On: a Coach this button appears beside the box where you type. Pressing it "
    "asks the model on your own PC what is missing from your question - a score, "
    "up to four gaps, and a rewritten version you can send instead of yours. It "
    "never sends anything by itself, it never changes your words unless you pick "
    "the rewritten one, and it is only ever advice: a low score does not stop you "
    "sending what you wrote. The model on this PC is small, so its advice is "
    "sometimes wrong and it misses things a bigger model would catch. Turning "
    "this on or off happens at once - no approval card, because nothing here "
    "leaves the PC and nothing is acted on.")

HEADING = "Prompt coach"
BUTTON = "Coach this"
SEND_MINE = "Send mine"
SEND_SUGGESTION = "Send the suggestion"
OFF_LINE = "The prompt coach is switched off."

#: The most gaps ever shown. A list of ten things wrong with a question is not
#: advice, it is a wall - and the model is not reliable enough to rank ten.
MAX_ISSUES = 4
#: How many earlier turns the critique may see. The owner's answer of
#: 2026-10-08: the last few turns, so pronouns have an antecedent, and no more.
MAX_TURNS = 6
TIMEOUT_SECONDS = 120.0
#: A question shorter than this is not worth a model call, and coaching "hi"
#: would only ever produce invented complaints.
MIN_WORDS = 3

#: Ollama is given this as `format`, so the shape is constrained while it
#: decodes rather than parsed hopefully afterwards. This is the house norm -
#: every shipped module declares its own SCHEMA - and `jarvis_entities.py` is
#: the smallest module to copy the surrounding call from.
SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 1, "maximum": 10},
        "clear": {"type": "boolean"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"what": {"type": "string"},
                               "why": {"type": "string"},
                               "fix": {"type": "string"}},
                "required": ["what", "why", "fix"],
            },
        },
        "missing": {"type": "array", "items": {"type": "string"}},
        "suggestion": {"type": "string"},
    },
    "required": ["score", "clear", "issues", "missing", "suggestion"],
}

PROMPT = """You are checking ONE question a person is about to send to their \
own assistant. You are not answering it. You are telling them what is missing \
from it, so they can decide whether to improve it before sending.

The checks, in the order that matters:
1. WHAT IS IT ACTUALLY ASKING FOR? A question with more than one job in it, or \
with no clear ask, is the most common problem.
2. REFERENCES. Does it say "it", "that", "the file" with nothing to point at?
3. OUTPUT. Does it say what shape the answer should take - a list, a table, a \
short paragraph, a number - when that would change the answer?
4. CONSTRAINTS. Length, tone, what to leave out, what to do if it cannot.
5. ASSUMPTIONS. Anything it takes for granted that might be wrong.
6. EDGE CASES. What should happen when the answer is empty, missing or fails.

Be honest, not flattering. If the question is already clear, say so: set \
`clear` to true, keep `issues` empty, and put the question back almost \
unchanged in `suggestion`. INVENTING A COMPLAINT IS A FAILURE - an empty \
`issues` with `clear` true is a correct and expected answer.

Never add facts you were not given. Never answer the question. Never write \
more than four issues, and prefer the two that matter most. Each `fix` must be \
the smallest change that solves it.

Reply with JSON only, exactly this shape:
{"score": 1-10, "clear": true|false,
 "issues": [{"what": "...", "why": "...", "fix": "..."}],
 "missing": ["a question you would have to ask to do this well"],
 "suggestion": "the same request, rewritten"}

The question, and the few turns before it:

"""


class Refused(ValueError):
    """A plain-sentence refusal. str() is the reason, in words."""


# --------------------------------------------------------------------------
#   The switch
# --------------------------------------------------------------------------
_S_LOCK = threading.Lock()
_DAMAGED = ("The prompt coach's setting file could not be read, so the prompt "
            "coach stays off.")


def _config_dir() -> Path:
    """The Jarvis settings folder, the same one every other module uses:
    jarvis_framework's own answer first, then the environment, then the
    default. Read-only here - this module never creates it."""
    try:
        import jarvis_framework
        return Path(jarvis_framework.CONFIG_DIR)
    except Exception:
        pass
    for name in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR"):
        raw = os.environ.get(name)
        if raw:
            return Path(raw)
    return Path.home() / ".openjarvis"


def settings_path() -> Path:
    """prompt-coach.json in the Jarvis settings folder."""
    return _config_dir() / SETTINGS_NAME


def setting() -> dict:
    """{"on": bool, "why": str}. No file: off, the default. Unreadable, not
    JSON, or not a bool: off, and `why` says so - never a bare False."""
    try:
        raw = settings_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"on": False, "why": ""}
    except OSError as exc:
        return {"on": False, "why": f"The prompt coach's setting file could not "
                                    f"be read ({type(exc).__name__}), so it stays off."}
    try:
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise ValueError
    except Exception:
        return {"on": False, "why": _DAMAGED}
    on = doc.get("enabled", False)
    if not isinstance(on, bool):
        return {"on": False, "why": _DAMAGED}
    return {"on": bool(on), "why": ""}


def enabled() -> bool:
    """What every caller asks. Fails to off."""
    try:
        return setting()["on"] is True
    except Exception:
        return False


def set_enabled(on: bool) -> dict:
    """Write the switch. Atomic, under a lock, like every other setting here.
    Both directions are instant: nothing about this feature opens a way out of
    the PC, takes an action or loosens a rule, so neither direction asks."""
    with _S_LOCK:
        path = settings_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps({"enabled": bool(on), "changed": time.time()}),
                           encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            raise Refused(f"The prompt coach's setting could not be saved "
                          f"({type(exc).__name__}).")
    return dict(setting(), ok=True)


# --------------------------------------------------------------------------
#   The model
# --------------------------------------------------------------------------
def _model() -> tuple:
    """(url, model) the house way, or (None, None). Never raises: this is the
    same shape jarvis_entities.py, jarvis_widgets.py and jarvis_tidy.py use."""
    try:
        import jarvis_sensitive
        url, model = jarvis_sensitive.learner_model()
    except Exception:
        return (None, None)
    if not url or not model:
        return (None, None)
    return (str(url), str(model))


def _local_check(url: str, model: str) -> str:
    """The mandatory gate before anything is sent. "" means the address is
    this PC; anything else is the plain sentence to show instead. Fails closed:
    if the checker cannot be imported, nothing is sent."""
    try:
        import jarvis_auto_learn
        return jarvis_auto_learn.check_local_model(url, model)
    except Exception:
        return ("Jarvis could not confirm the model is on this PC, so the prompt "
                "coach did not send anything.")


def _ask(url: str, model: str, prompt: str) -> Optional[str]:
    """One non-streamed answer from the local model, or None. Standard library
    plus jarvis_local_http (which is the helper that ignores a proxy)."""
    import urllib.error
    import urllib.request

    body = {"model": model, "prompt": prompt, "stream": False, "format": SCHEMA,
            "think": False, "options": {"temperature": 0.1, "num_predict": 700}}
    req = urllib.request.Request(str(url).rstrip("/") + "/api/generate",
                                 data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        try:
            import jarvis_local_http
            resp = jarvis_local_http.urlopen(req, TIMEOUT_SECONDS)
        except ImportError:
            resp = urllib.request.build_opener(
                urllib.request.ProxyHandler({})).open(req, timeout=TIMEOUT_SECONDS)
        with resp as r:
            out = json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        if exc.code == 400 and "think" in body:
            body.pop("think", None)
            try:
                resp = urllib.request.build_opener(
                    urllib.request.ProxyHandler({})).open(
                        urllib.request.Request(
                            str(url).rstrip("/") + "/api/generate",
                            data=json.dumps(body).encode("utf-8"), method="POST",
                            headers={"Content-Type": "application/json"}),
                        timeout=TIMEOUT_SECONDS)
                with resp as r:
                    out = json.loads(r.read().decode("utf-8") or "{}")
            except Exception:
                return None
        else:
            return None
    except Exception:
        return None
    text = out.get("response") if isinstance(out, dict) else None
    return text if isinstance(text, str) else None


# --------------------------------------------------------------------------
#   Reading the answer
# --------------------------------------------------------------------------
def _clean(text: str) -> str:
    """Strip a ```json fence and any stray prose around one JSON object."""
    text = (text or "").strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    return text


def parse(raw: object) -> dict:
    """The critique, or Refused. Every field is checked for type, and the
    lists are trimmed to what the screen can show. A missing or malformed
    field is a refusal, never a half-filled card."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    if not isinstance(raw, str):
        raise Refused("The prompt coach did not get an answer it could read.")
    try:
        doc = json.loads(_clean(raw))
    except Exception:
        raise Refused("The prompt coach's answer was not readable JSON.")
    if not isinstance(doc, dict):
        raise Refused("The prompt coach's answer was not the shape it should be.")

    score = doc.get("score")
    if not isinstance(score, int) or isinstance(score, bool):
        raise Refused("The prompt coach's answer had no score.")
    score = max(1, min(10, score))

    raw_issues = doc.get("issues")
    if not isinstance(raw_issues, list):
        raise Refused("The prompt coach's answer had no list of gaps.")
    issues = []
    for item in raw_issues:
        if not isinstance(item, dict):
            continue
        what = item.get("what")
        if not isinstance(what, str) or not what.strip():
            continue
        issues.append({"what": what.strip(),
                       "why": str(item.get("why") or "").strip(),
                       "fix": str(item.get("fix") or "").strip()})
        if len(issues) >= MAX_ISSUES:
            break

    raw_missing = doc.get("missing")
    missing = [str(m).strip() for m in raw_missing
               if isinstance(m, str) and m.strip()] if isinstance(raw_missing, list) else []

    suggestion = doc.get("suggestion")
    if not isinstance(suggestion, str):
        suggestion = ""

    # `clear` is the model's own answer to "is this already fine?", and the
    # screen leans on it - but a model that says "clear" while listing four
    # gaps is contradicting itself, and the gaps are the more useful half.
    clear = doc.get("clear") is True and not issues
    return {"score": score, "clear": clear, "issues": issues,
            "missing": missing, "suggestion": suggestion.strip()}


# --------------------------------------------------------------------------
#   The one entry point
# --------------------------------------------------------------------------
def _turns(history: object) -> list:
    """The last few turns, as (who, text) pairs. Anything unexpected is
    dropped rather than guessed at, and the coach never sees more than the
    owner allowed."""
    out = []
    if isinstance(history, (list, tuple)):
        for item in history:
            if isinstance(item, dict):
                who, text = item.get("who"), item.get("text")
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                who, text = item
            else:
                continue
            if isinstance(text, str) and text.strip():
                out.append((str(who or "?"), text.strip()))
    return out[-MAX_TURNS:]


def coach(text: str, history: object = (), *,
          ask: Optional[Callable[[str, str, str], Optional[str]]] = None,
          url: Optional[str] = None, model: Optional[str] = None) -> dict:
    """Critique one prompt.

    `ask` is injectable so every test in test_prompt_coach.py runs with no
    model at all - the same seam jarvis_entities.py uses. Anything wrong is a
    Refused with a plain sentence; this never raises anything else.
    """
    words = str(text or "").strip()
    if len(words.split()) < MIN_WORDS:
        raise Refused("That is too short to coach - write a little more and try again.")
    if not enabled():
        raise Refused(OFF_LINE)

    if url is None or model is None:
        found_url, found_model = _model()
        url = url or found_url
        model = model or found_model
    if not url or not model:
        raise Refused("Jarvis could not find the model on this PC, so there is "
                      "nothing to coach with.")

    why = _local_check(str(url), str(model))
    if why:
        raise Refused(why)

    prompt = PROMPT
    for who, said in _turns(history):
        prompt += f"{who}: {said}\n"
    prompt += f"owner: {words}\n"

    caller = ask or _ask
    raw = caller(str(url), str(model), prompt)
    if raw is None:
        raise Refused("The model on this PC did not answer, so there is no "
                      "coaching to show. Nothing was sent anywhere.")
    return parse(raw)


# --------------------------------------------------------------------------
#   The route's half
# --------------------------------------------------------------------------
def handle_post(body: object) -> tuple:
    """(status, dict). The house shape: the module answers the code itself and
    jarvis_hud.py forwards the pair without mapping any exception."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "The request was not the shape it should be."}
    try:
        out = coach(body.get("text") or "",
                    body.get("history") or (),
                    ask=None, url=body.get("url"), model=body.get("model"))
    except Refused as exc:
        return 409, {"ok": False, "error": str(exc)}
    return 200, {"ok": True, "coach": out}


def handle_setting(body: object) -> tuple:
    """(status, dict) for POST /api/prompt/coach/setting - the switch.

    Enabled must be a real true or false. Anything else is refused rather than
    guessed at, because guessing here would mean "your switch moved" when it
    did not.
    """
    if not isinstance(body, dict) or not isinstance(body.get("enabled"), bool):
        return 400, {"ok": False,
                     "error": "The request needs an enabled true or false."}
    try:
        set_enabled(body["enabled"])
    except Refused as exc:
        return 409, {"ok": False, "error": str(exc)}
    return 200, status()


def status() -> dict:
    """The switch's own state, for the settings screens and for
    "is the prompt coach on?" - the same shape as jarvis_search.settings()."""
    out = dict(setting())
    out.update({"label": LABEL, "detail": DETAIL, "heading": HEADING,
                "button": BUTTON, "send_mine": SEND_MINE,
                "send_suggestion": SEND_SUGGESTION, "ok": True})
    return out
