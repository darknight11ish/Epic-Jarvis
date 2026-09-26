"""eval_learner.py - the learner half of the memory self-test (memory idea 2).

    python eval_memory.py                              # runs this too
    python eval_memory.py --learner-model qwen3:8b     # ... with the model

Run by eval_memory.py; not on its own. It is not copied to the backend
folder.

WHY A LEARNER TEST

HaluMem (2025) found that in every memory system it tested, SAVING was the
weak step, not finding. Jarvis's own self-test (eval_memory.py) only asked
whether search finds a fact. This asks whether the right facts get IN, and
whether the wrong ones stay out.

WHAT IT CHECKS, WITH NO MODEL (the default run - nothing is downloaded)

The made-up conversations in backend/eval/learner_cases.jsonl, one per line:

  reads      which turns the learner may read at all (jarvis_intake.
             owner_turns): the owner's own turns - never the assistant's,
             never a tool's answer, never a turn the backend wrote itself,
             never a "Remember:" (queued on its own) or a reminder.
  remember   "Remember: ..." is queued in the owner's own words, word for
             word, with a relative date given its real date - and whether
             it is then saved without a card (a colon, one line, typed).
  dates      a relative date in a fact gets its real date added
             (jarvis_intake.anchor_dates), anchored to the day it was said.
  gate       a fact AS THE MODEL WOULD WRITE IT, from a conversation: is it
             saved without a card, or left a card - and for the right
             reason? Pasted text, a link, email headers, a tool that read
             outside text earlier, a voice turn nobody checked, a word the
             owner never said, a "not" left out, a correction, a sensitive
             topic: each must stay a card. The owner's own plain words must
             be saved. This runs the real jarvis_auto_learn.after_pass, the
             real live-turn registry and the real jarvis_extract functions
             the patch stack writes (backend/_stack.py), on a scratch store.

  The one stand-in: the sensitive-topic check's SECOND layer asks the local
  model, and there is no model here. Its answer is replaced by "not
  sensitive", so the pattern layer and every other check are what is
  measured - except in a case that says what a real model would answer
  ("model": "health"): a private fact about someone the word lists see only
  as "a person" is judged the way the PC's model would judge it (the
  memory review of 2026-09-27, I5). With no model at all the real check
  fails closed (a card).

  Each gate case gets a fresh scratch store (World.fresh): whether a fact
  contradicts one already saved is part of the gate now (the memory
  review's B5), so only the facts a case lists as stored may decide it.

WITH A MODEL (optional: --learner-model NAME, on the PC)

  propose    the real learner - jarvis_extract.propose through jarvis_intake.
             propose, the same prompt and the same checks - on made-up
             conversations, asking this PC's Ollama (loopback only; a cloud
             model is refused). Scored: did it propose each expected fact
             (all its key words, every "not" kept), did it propose nothing
             from the assistant's or a tool's words, and did a correction
             point at the right stored fact. Needs JARVIS_BACKEND pointing
             at the backend folder, because jarvis_extract.py is only there.
             NOT RUN in this repository's container: there is no model and
             no jarvis_extract.py here, so this part is untested here.

NEVER YOUR DATA. Everything is made up, on a scratch store in the self-test's
temporary folder; the chat log and settings files it needs are written there
too. Nothing is sent anywhere without --learner-model, and with it only to
the loopback address given.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import types
from contextlib import closing
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
CASES = HERE / "eval" / "learner_cases.jsonl"
LOCAL = "http://127.0.0.1:11434"
KEY = bytes(range(32))


def _day(text: str) -> float:
    y, m, d = (int(x) for x in text.split("-"))
    return time.mktime((y, m, d, 12, 0, 0, 0, 0, -1))


def load_cases(path: Path = CASES) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


# ------------------------------------------------------------ the world --

def _proposals_table(c) -> None:
    """The proposals table as memory-safety, memory-intake and the owner's
    file leave it (the owner's _init is in no patch) - test_auto_learn's."""
    c.execute("""CREATE TABLE IF NOT EXISTS proposals (
        id INTEGER PRIMARY KEY, text TEXT NOT NULL, replaces TEXT,
        confidence REAL, source TEXT, created REAL,
        state TEXT NOT NULL DEFAULT 'pending', decided REAL, fact_id INTEGER,
        replaces_id INTEGER, replaces_text TEXT)""")


def _extract_stand_in(M):
    """A jarvis_extract whose accept_auto, _accept, propose_verbatim and the
    rest are the REAL text the patch stack writes (test_auto_learn's way)."""
    import _stack
    src, log = _stack.stand_in("jarvis_extract.py")
    if src is None:
        raise RuntimeError("the patch stack does not build jarvis_extract.py")
    x = types.ModuleType("jarvis_extract")
    x.M, x.closing, x.time, x.Optional, x.json = M, closing, time, Optional, json
    x._init = _proposals_table
    x._cfg = lambda k, d=None: d
    x._dropped_full = 0
    x.OLLAMA = LOCAL
    body = [line for line in src.splitlines()
            if line.startswith(("RETIRE_SOURCE = ", "AUTO_SOURCES = ", "MERGE_SOURCE = "))]
    for name in ("_accept_retire", "_accept_merge", "_accept", "accept_auto", "_fact_source",
                 "_fact_meta", "propose_verbatim"):
        t = _stack.function_text(src, name)
        if t is None:
            raise RuntimeError(f"the stack does not write exactly one {name}()")
        body.append(t)
    exec(compile("\n\n".join(body), "<jarvis_extract.py, as the stack leaves it>", "exec"),
         x.__dict__)
    return x


class World:
    """One scratch store, chat log and jarvis_extract for the whole run."""

    def __init__(self, M, scratch: Path):
        import jarvis_chat_log as H
        self.M, self.H = M, H
        self.dir = scratch / "learner"
        self.dir.mkdir(parents=True, exist_ok=True)
        fw = sys.modules.get("jarvis_framework")
        if fw is not None:
            fw.CONFIG_DIR = self.dir
        self.store = M.MemoryStore(self.dir / "memory.db", embedder=M.HashEmbedder())
        self._old_store = getattr(M, "_store", None)
        M._store = self.store
        with closing(self.store._connect()) as c:
            _proposals_table(c)
        self.x = _extract_stand_in(M)
        self._old_extract = sys.modules.get("jarvis_extract")
        sys.modules["jarvis_extract"] = self.x
        self.log = H.ChatLog(self.dir / "chat-history.db", self.dir / "chat-history.json",
                             lambda: KEY)
        H.use(self.log)
        self._old_events = sys.modules.get("jarvis_events")
        ev = types.ModuleType("jarvis_events")
        ev.BUS = types.SimpleNamespace(publish=lambda kind, data: None)
        sys.modules["jarvis_events"] = ev
        self.n = 0

    def fresh(self) -> None:
        """A new, empty scratch store for the next case (the chat log and
        jarvis_extract stay). A gate case is judged against only the facts
        it lists as stored: since the contradiction check (the memory
        review, B5) looks at what is already saved, a fact another case
        saved must not decide this one."""
        self.n_stores = getattr(self, "n_stores", 0) + 1
        self.store = self.M.MemoryStore(self.dir / f"memory-{self.n_stores}.db",
                                        embedder=self.M.HashEmbedder())
        self.M._store = self.store
        with closing(self.store._connect()) as c:
            _proposals_table(c)

    def conversation(self) -> str:
        self.n += 1
        return f"eval-learner-{self.n:04d}"

    def say(self, cid: str, history: list, turn: dict) -> list:
        """One /api/chat request, recorded as the chat route records it; the
        app re-sends the conversation so far, as both apps do."""
        msg = {"role": "user", "content": turn["text"]}
        prov = turn.get("prov", "typed")
        if prov is not None:
            msg["provenance"] = prov
        msgs = list(history) + [msg]
        self.H.record_turn({"messages": msgs, "conversation_id": cid, "device": "desktop"},
                           lane="eval", turn={"finish_reason": "stop", "answer": "ok",
                                              "tools_ran": ["web_search"] if turn.get("tools")
                                              else []})
        return msgs + [{"role": "assistant", "content": "ok"}]

    def queue(self, text: str, replaces_id: Optional[int] = None) -> dict:
        with closing(self.store._connect()) as c:
            cur = c.execute("INSERT INTO proposals (text, replaces, confidence, source, created,"
                            " replaces_id, replaces_text) VALUES (?,?,?,?,?,?,?)",
                            (text, None, 0.9, "conversation", time.time(), replaces_id, None))
            return {"id": cur.lastrowid, "text": text, "replaces_id": replaces_id,
                    "state": "pending"}

    def close(self) -> None:
        self.H.use(None)
        self.M._store = self._old_store
        for name, old in (("jarvis_extract", self._old_extract),
                          ("jarvis_events", self._old_events)):
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


# ------------------------------------------------------------- the kinds --

def _reads(w, I, case) -> dict:
    for t in case.get("authored", []):
        I.mark_jarvis_authored(t)
    got = [m["content"] for m in I.owner_turns(case["messages"], I.ORIGIN_OWNER)]
    return {"ok": got == case["want"], "got": got}


def _remember(w, I, A, case) -> dict:
    cid = w.conversation()
    msgs = w.say(cid, [], {"text": case["text"], "prov": case.get("prov", "typed")})
    msgs = msgs[:-1]                       # the request, before the answer
    res = I.remember_from_turn(msgs, extract=w.x, when=_day(case["at"]) if case.get("at")
                               else None)
    row = None
    if isinstance(res, dict) and res.get("proposal_id"):
        with closing(w.store._connect()) as c:
            r = c.execute("SELECT text FROM proposals WHERE id=?",
                          (res["proposal_id"],)).fetchone()
            row = r[0] if r else None
    auto = A.after_remember(res, msgs, conversation_id=cid, learning_on=True, extract=w.x,
                            publish=lambda ids: None)
    how = "auto" if auto.get("saved") else "card"
    return {"ok": row == case["queued"] and how == case["want"],
            "got": {"queued": row, "decision": how,
                    "why": next(iter((auto.get("cards") or {}).values()), "")}}


def _dates(w, I, case) -> dict:
    got = I.anchor_dates(case["text"], _day(case["at"]))
    return {"ok": got == case["want"], "got": got}


def _model_says(case):
    """The stand-in for the sensitive-topic check's local model: "not
    sensitive", unless the case says what a real model would answer
    ("model": "health" - the memory review's I5, so a private fact about
    someone is judged the way the PC's model would judge it)."""
    cat = case.get("model")
    if not cat:
        return None
    if cat == "none":
        return lambda prompt: '{"sensitive": false, "category": "none"}'
    return lambda prompt: json.dumps({"sensitive": True, "category": cat})


def _gate(w, I, A, case) -> dict:
    w.fresh()
    cid = w.conversation()
    history = []
    for turn in case["turns"]:
        if turn.get("prov") == "voice" and turn.get("heard"):
            w.H.note_transcript(turn["text"], strictness="very_strict",
                                model=A.STRONG_MODEL_LABEL, mode="owner",
                                source="push_to_talk")
        history = w.say(cid, history, turn)
    rid = None
    for text in case.get("stored", []):
        rid = w.store.add(text, source="eval")
    turns = [t["text"] for t in case["turns"]]
    shown = None
    if case.get("candidate"):
        # What the learner's model is shown as "already stored, may be
        # corrected" (jarvis_intake.candidates) for this conversation.
        shown = [c["text"] for c in I.candidates(
            w.store, [{"role": "user", "content": t} for t in turns])]
    q = w.queue(case["fact"], replaces_id=rid if case.get("correction") else None)
    import jarvis_sensitive as S
    keep = S.ASK_MODEL
    said = _model_says(case)
    if said is not None:
        S.ASK_MODEL = said
    try:
        res = A.after_pass([q], [{"role": "user", "content": t} for t in turns],
                           conversation_id=cid, model="qwen3:8b", ollama=LOCAL,
                           learning_on=True, extract=w.x, publish=lambda ids: None)
    finally:
        S.ASK_MODEL = keep
    how = "auto" if res.get("saved") else "card"
    why = next(iter((res.get("cards") or {}).values()), "")
    ok = how == case["want"] and (how == "auto" or case.get("why", "") in why)
    got = {"decision": how, "why": why}
    if shown is not None:
        got["shown"] = shown
        ok = ok and case["candidate"] in shown
    return {"ok": ok, "got": got}


def _said_again(w, I, A, case) -> dict:
    """Memory idea 3: the owner says something Jarvis already knows. The
    learner's model is a stand-in that proposes `proposed` (as the real one
    would re-propose a fact it hears again); the rest is the real code -
    jarvis_intake.propose's wrapper, note_said_again, the live-turn
    registry and MemoryStore.said_again. Scored: how many times it was
    recorded for the stored fact."""
    if not hasattr(w.store, "said_again_counts") or not hasattr(I, "note_said_again"):
        return {"ok": False, "got": "this memory has no \"said again\" (idea 3 not built)"}
    cid = w.conversation()
    history = []

    def say(turn):
        nonlocal history
        if turn.get("prov") == "voice" and turn.get("heard"):
            w.H.note_transcript(turn["text"], strictness="very_strict",
                                model=A.STRONG_MODEL_LABEL, mode="owner",
                                source="push_to_talk")
        history = w.say(cid, history, turn)
    for turn in case.get("before", []):
        say(turn)
    time.sleep(0.005)
    stored = case["stored"]
    if case.get("stored_days_ago"):
        # The stored fact's relative date made real as the learner would
        # have on that day: "started yesterday" said N days ago.
        stored = I.anchor_dates(stored, time.time() - 86400 * float(case["stored_days_ago"]))
    fid = w.store.add(stored, source="eval")
    if case.get("forget"):
        w.store.retire(fid)
    time.sleep(0.005)
    for turn in case.get("turns", []):
        time.sleep(0.005)
        say(turn)
    facts = [p if isinstance(p, dict) else {"text": p} for p in case.get("proposed", [])]
    answer = json.dumps({"facts": facts})
    extract = types.SimpleNamespace(
        propose=lambda messages, llm=None, source="": (llm("the learner's prompt"), [])[1])
    owner = [{"role": "user", "content": m["content"]} for m in history
             if m.get("role") == "user"]
    import jarvis_intake
    for _ in range(int(case.get("passes", 1))):
        if case.get("remember"):
            msgs = w.say(cid, history, {"text": case["remember"]})[:-1]
            I.remember_from_turn(msgs, extract=w.x)
        else:
            jarvis_intake.propose(extract, owner, lambda prompt, *a, **k: answer,
                                  store=w.store)
    got = w.store.said_again_counts([fid]).get(fid, {}).get("count", 0)
    return {"ok": got == case["want"], "got": {"recorded": got}}


def _true_from(w, case) -> dict:
    """Memory idea 4: the fact is added through the real MemoryStore.add()
    on the day it was told; scored on the "true from" date it gets - the
    date its words give, or none (then it is the day it was told)."""
    M = w.M
    if not hasattr(M, "true_from"):
        return {"ok": False, "got": "this memory has no \"true from\" dates (idea 4 not built)"}
    told = _day(case["told"])
    real = M.time
    M.time = types.SimpleNamespace(**{k: getattr(real, k) for k in dir(real)
                                      if not k.startswith("_")})
    M.time.time = lambda: told
    try:
        fid = w.store.add(case["text"], source="eval")
    finally:
        M.time = real
    row = w.store.get(fid)
    said = M.said_from(row.get("meta"))
    got = time.strftime("%Y-%m-%d", time.localtime(row["valid_from"])) if said else None
    return {"ok": got == case["want"], "got": {"true_from": got}}


# ----------------------------------------------------- the real learner --

def _ollama(url: str, model: str, timeout: float = 120.0):
    """ask(prompt) -> the model's answer, from this PC's Ollama, never
    through a proxy. Loopback only - checked by the caller."""
    import urllib.request

    def ask(prompt, *a, **kw):
        body = {"model": model, "prompt": prompt, "stream": False,
                "options": {"temperature": 0}}
        req = urllib.request.Request(url.rstrip("/") + "/api/generate",
                                     data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json"})
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}").get("response") or ""
    return ask


def _has(text: str, words) -> bool:
    low = " " + " ".join(str(text).lower().replace("'", " ").split()) + " "
    return all((" " + str(w).lower() in low) for w in words)


def _propose(M, I, A, case, ask, store) -> dict:
    """One conversation through the real learner, scored."""
    import jarvis_extract as X      # the owner's file: JARVIS_BACKEND must hold it
    for text in case.get("stored", []):
        store.add(text, source="eval")
    import jarvis_intake
    said = jarvis_intake.owner_turns(case["messages"], jarvis_intake.ORIGIN_OWNER)
    out = jarvis_intake.propose(X, said, ask, source="conversation", when=_day(case["at"]),
                                store=store) or []
    texts = [str(r.get("text") or "") for r in out if isinstance(r, dict)]
    found = [any(_has(t, want) for t in texts) for want in case.get("want", [])]
    leaked = [w for w in case.get("never", []) if any(w.lower() in t.lower() for t in texts)]
    target_ok = True
    if case.get("replaces"):
        target_ok = any(isinstance(r, dict) and r.get("replaces_text")
                        and _has(r["replaces_text"], case["replaces"]) for r in out)
    return {"ok": all(found) and not leaked and target_ok,
            "got": {"proposed": texts, "found": found, "leaked": leaked,
                    "correction_aimed_right": target_ok}}


def run_model_part(M, I, A, cases, scratch: Path, model: str, ollama: str) -> dict:
    if not A._is_loopback(ollama):
        return {"ran": False, "why": f"{ollama} is not this PC (loopback only)"}
    if A._remote(model):
        return {"ran": False, "why": f"{model} is a cloud model - refused"}
    try:
        import jarvis_extract  # noqa: F401
        if not hasattr(jarvis_extract, "propose"):
            raise ImportError("no propose()")
    except Exception as exc:
        return {"ran": False, "why": "jarvis_extract.py could not be loaded "
                f"({type(exc).__name__}); set JARVIS_BACKEND to the backend folder"}
    ask = _ollama(ollama, model)
    rows = []
    for case in [c for c in cases if c["kind"] == "propose"]:
        d = Path(tempfile.mkdtemp(prefix="propose-", dir=scratch))
        st = M.MemoryStore(d / "memory.db", embedder=M.HashEmbedder())
        old = getattr(M, "_store", None)
        M._store = st
        try:
            with closing(st._connect()) as c:
                _proposals_table(c)
            r = _propose(M, I, A, case, ask, st)
        except Exception as exc:
            r = {"ok": False, "got": {"error": f"{type(exc).__name__}: {exc}"[:300]}}
        finally:
            M._store = old
        rows.append({"id": case["id"], "what": case.get("what", ""), **r})
    return {"ran": True, "model": model, "cases": rows,
            "right": sum(r["ok"] for r in rows), "total": len(rows)}


# ------------------------------------------------------------- the run --

def run(M, scratch: Path, *, model: Optional[str] = None, ollama: str = LOCAL) -> dict:
    """Every case once. {"available", "kinds": {kind: {"right", "total"}},
    "cases": [...], "model_part": {...}}. Never raises: a module that is
    missing is reported, not a crash of the whole self-test."""
    try:
        import jarvis_intake as I
        import jarvis_auto_learn as A
        import jarvis_sensitive as S
    except Exception as exc:
        return {"available": False, "why": f"{type(exc).__name__}: {exc}"}
    cases = load_cases()
    keep_ask = getattr(S, "ASK_MODEL", None)
    if model is None:
        # The stand-in (see the module docstring): the local model's answer
        # to "is this sensitive?" is "no", so the patterns and every other
        # check are what is measured.
        S.ASK_MODEL = lambda prompt: '{"sensitive": false, "category": "none"}'
    A._reset_for_tests()
    try:
        w = World(M, scratch)
    except Exception as exc:
        S.ASK_MODEL = keep_ask
        return {"available": False, "why": f"{type(exc).__name__}: {exc}"}
    rows = []
    try:
        for case in cases:
            kind = case["kind"]
            if kind == "propose":
                continue
            try:
                if kind == "reads":
                    r = _reads(w, I, case)
                elif kind == "remember":
                    r = _remember(w, I, A, case)
                elif kind == "dates":
                    r = _dates(w, I, case)
                elif kind == "gate":
                    r = _gate(w, I, A, case)
                elif kind == "said_again":
                    r = _said_again(w, I, A, case)
                elif kind == "true_from":
                    r = _true_from(w, case)
                else:
                    r = {"ok": False, "got": f"unknown kind {kind!r}"}
            except Exception as exc:
                r = {"ok": False, "got": f"{type(exc).__name__}: {exc}"[:300]}
            rows.append({"id": case["id"], "kind": kind, "what": case.get("what", ""),
                         "want": case.get("want"), **r})
        model_part = {"ran": False, "why": "no model asked for (--learner-model); the "
                      "real learner needs this PC's local model and jarvis_extract.py"}
        if model:
            model_part = run_model_part(M, I, A, cases, scratch, model, ollama)
    finally:
        w.close()
        S.ASK_MODEL = keep_ask
    kinds = {}
    for r in rows:
        k = kinds.setdefault(r["kind"], {"right": 0, "total": 0})
        k["total"] += 1
        k["right"] += bool(r["ok"])
    gate = [r for r in rows if r["kind"] == "gate"]
    return {"available": True, "kinds": kinds, "cases": rows,
            "gate_auto": [sum(r["ok"] for r in gate if r["want"] == "auto"),
                          sum(r["want"] == "auto" for r in gate)],
            "gate_card": [sum(r["ok"] for r in gate if r["want"] == "card"),
                          sum(r["want"] == "card" for r in gate)],
            "model_part": model_part}


def markdown(res: dict) -> list:
    """The report's lines for the learner."""
    lines = ["", "**The learner** (memory idea 2): do the right facts get IN, and do the "
             "wrong ones stay out? Made-up conversations, backend/eval/learner_cases.jsonl."]
    if not res.get("available"):
        return lines + ["", f"Not measured: {res.get('why')}"]
    names = {"reads": "Which turns it may read (never the assistant, a tool, or the "
                      "backend's own)",
             "remember": "\"Remember: ...\" kept word for word, and saved or carded right",
             "dates": "Relative dates given their real date",
             "gate": "Saved without a card, or kept a card for the right reason",
             "said_again": "\"Said again\": a repeat recorded once, only from the owner's "
                           "own live words",
             "true_from": "\"True from\" dates taken from the owner's words"}
    lines += ["", "| What | Right |", "|---|---|"]
    for k, v in res["kinds"].items():
        lines.append(f"| {names.get(k, k)} | {v['right']}/{v['total']} |")
    lines += ["", f"Saved when it should be: {res['gate_auto'][0]}/{res['gate_auto'][1]}. "
              f"Kept a card when it should: {res['gate_card'][0]}/{res['gate_card'][1]}. "
              "(The local model's sensitive-topic answer is a stand-in: \"not sensitive\", "
              "or - for a case that says what a real model would answer, such as a private "
              "fact about someone - that answer.)"]
    wrong = [r for r in res["cases"] if not r["ok"]]
    if wrong:
        lines += ["", "Wrong: " + "; ".join(f"{r['id']} ({r['what']}): {r['got']}"
                                             for r in wrong)]
    mp = res.get("model_part") or {}
    if mp.get("ran"):
        lines += ["", f"The real learner ({mp['model']}): {mp['right']}/{mp['total']} "
                  "conversations right (every expected fact proposed with its \"not\" kept, "
                  "nothing from the assistant's or a tool's words, corrections aimed right)."]
        for r in mp["cases"]:
            if not r["ok"]:
                lines.append(f"- {r['id']} ({r['what']}): {r['got']}")
    else:
        lines += ["", f"The real learner: not run - {mp.get('why')}."]
    return lines
