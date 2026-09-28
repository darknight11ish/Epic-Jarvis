"""eval_tidy.py - the self-test's part for "Where did I put ...?" and the
overnight tidy's "Which is true now?" (2026-09-28; docs/JARVIS-API.md
sections 77 and 78).

    python eval_memory.py                              # runs this too
    python eval_memory.py --learner-model qwen3:8b     # ... and the real model

Run by eval_memory.py; not on its own. It is not copied to the backend
folder. Made-up facts on a scratch store in the self-test's temporary
folder; never the owner's memory, nothing sent anywhere without
--learner-model (and then only to this PC's Ollama, loopback only).

TWO PARTS

  where      backend/eval/where_cases.jsonl: facts said on made-up days - a
             passport put in one drawer, then moved; glasses moved; winter
             coats moved three times, one of them older news - saved
             through the real MemoryStore.add() and moved by the real
             jarvis_places.apply_move(), as automatic learning does. Then the
             questions go through the REAL fast path (jarvis_quick.answer,
             no model): is the answer the newest place, never an older one,
             and is a question it cannot answer ("where is my sister?",
             "where did I leave my phone?" with no place saved) handed to
             the model instead of guessed? Scored: right answers, and wrong
             places given (an older place, or an answer where none was due).

  conflicts  backend/eval/conflict_cases.jsonl: 20 real conflicts ("works at
             Initech" / "started a new job at Globex") and 20 pairs that can
             both be true ("works at Initech" / "started learning the
             guitar"), all in one store. The tidy's own finder
             (jarvis_tidy.find_conflicts) picks the candidates and builds the
             numbered prompt; a STAND-IN model answers every prompt
             CORRECTLY from the case file. So this measures everything
             except the model: whether the right older fact is among the
             candidates at all (recall), and whether the numbers the model
             gives are mapped back to the right facts (precision). The
             owner's rule for this feature: keep it only if precision is at
             least 0.8 here. What the REAL model gets right is measured only
             with --learner-model, on the PC.
"""
from __future__ import annotations

import json
import re
import sys
import time
import types
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
WHERE = HERE / "eval" / "where_cases.jsonl"
CONFLICTS = HERE / "eval" / "conflict_cases.jsonl"
LOCAL = "http://127.0.0.1:11434"

#: The owner's bar for keeping "Which is true now?" (2026-09-28).
PRECISION_BAR = 0.8


def _read(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _at(M, when: float, fn):
    """fn() with the memory module's clock at `when` (as eval_learner's
    true_from cases do)."""
    real = M.time
    M.time = types.SimpleNamespace(**{k: getattr(real, k) for k in dir(real)
                                      if not k.startswith("_")})
    M.time.time = lambda: when
    try:
        return fn()
    finally:
        M.time = real


def _scratch_store(M, scratch: Path, name: str):
    d = scratch / name
    d.mkdir(parents=True, exist_ok=True)
    return M.MemoryStore(d / "memory.db", embedder=M.HashEmbedder())

# --------------------------------------------------------------- where --


def where_part(M, scratch: Path) -> dict:
    import jarvis_places as PL
    import jarvis_quick as Q
    rows = _read(WHERE)
    st = _scratch_store(M, scratch, "where")
    old = getattr(M, "_store", None)
    M._store = st
    now = time.time()
    try:
        for r in [x for x in rows if "say" in x]:
            when = now - float(r.get("days_ago", 0)) * 86400.0
            fid = _at(M, when, lambda: st.add(r["say"], source="eval"))
            prev = PL.older_place(st, r["say"], exclude=(fid,))
            if prev is not None:
                PL.apply_move(st, fid, int(prev["id"]))
        cases = []
        for r in [x for x in rows if "ask" in x]:
            res = Q.answer(r["ask"], sched=types.SimpleNamespace(
                mark_command=lambda t: None, note_set=lambda *a, **k: None,
                forget_set=lambda c: None), now=now)
            said = res.reply if res is not None else None
            want = r.get("want")
            if want is None:
                ok = said is None
                wrong = said is not None
            else:
                ok = said is not None and want in said and \
                    (not r.get("also") or r["also"] in said) and \
                    (not r.get("never") or r["never"] not in said)
                wrong = said is not None and bool(r.get("never")) and r["never"] in said
            cases.append({"id": r["id"], "ask": r["ask"], "ok": ok, "wrong_place": wrong,
                          "said": said})
    finally:
        M._store = old
    return {"right": sum(c["ok"] for c in cases), "total": len(cases),
            "wrong_places": sum(c["wrong_place"] for c in cases), "cases": cases}

# ----------------------------------------------------------- conflicts --


def _truth(cases: list) -> dict:
    """new text -> the old texts it really contradicts."""
    out: dict = {}
    for c in cases:
        out.setdefault(c["new"], set())
        if c["conflict"]:
            out[c["new"]].add(c["old"])
    return out


def correct_model(cases: list):
    """A stand-in model that answers every prompt RIGHT: the numbers of the
    listed existing facts that the case file says the new fact contradicts."""
    truth = _truth(cases)

    def ask(prompt: str) -> str:
        tail = prompt.rsplit("NEW FACT:", 1)[-1]
        new = tail.split("\n", 1)[0].strip()
        listed = re.findall(r"^(\d+): (.*)$", tail.split("EXISTING FACTS:", 1)[-1], re.M)
        want = truth.get(new, set())
        return json.dumps({"contradicted": [int(i) for i, t in listed if t.strip() in want]})
    return ask


def conflicts_part(M, scratch: Path, ask=None, label: str = "stand-in (always right)") -> dict:
    import jarvis_tidy as T
    cases = _read(CONFLICTS)
    st = _scratch_store(M, scratch, f"conflicts-{label.split()[0]}")
    old_store = getattr(M, "_store", None)
    M._store = st
    ids = {}
    now = time.time()
    try:
        base = now - 30 * 86400.0
        for i, text in enumerate(dict.fromkeys(c["old"] for c in cases)):
            ids[text] = _at(M, base + i, lambda: st.add(text, source="eval"))
        since = base + 10_000
        for i, c in enumerate(cases):
            ids[c["new"]] = _at(M, since + 60 + i, lambda: st.add(c["new"], source="eval"))
        got = T.find_conflicts(st, ask or correct_model(cases), since=since, now=now,
                               limit=10_000, raise_cards=False, max_new=len(cases))
    finally:
        M._store = old_store
    pairs = {frozenset(p) for p in got["pairs"]}
    real = {frozenset((ids[c["old"]], ids[c["new"]])): c for c in cases if c["conflict"]}
    fake = {frozenset((ids[c["old"]], ids[c["new"]])): c for c in cases if not c["conflict"]}
    flagged = len(pairs)
    right = len(pairs & set(real))
    return {"model": label, "flagged": flagged, "right": right,
            "precision": round(right / flagged, 3) if flagged else None,
            "recall": round(right / len(real), 3) if real else None,
            "conflicts": len(real), "distractors": len(fake),
            "distractors_flagged": len(pairs & set(fake)),
            "missed": sorted(c["id"] for k, c in real.items() if k not in pairs),
            "asked": got["asked"]}


def run(M, scratch: Path, *, model: Optional[str] = None, ollama: str = LOCAL) -> dict:
    """Both parts. Never raises: what is missing is reported."""
    out = {"available": True}
    try:
        out["where"] = where_part(M, scratch)
    except Exception as exc:
        out["where"] = {"available": False, "why": f"{type(exc).__name__}: {exc}"[:300]}
    try:
        out["conflicts"] = conflicts_part(M, scratch)
    except Exception as exc:
        out["conflicts"] = {"available": False, "why": f"{type(exc).__name__}: {exc}"[:300]}
    if model:
        try:
            import jarvis_tidy as T
            import jarvis_auto_learn as A
            if not A._is_loopback(ollama):
                why = f"{ollama} is not this PC (loopback only)"
            elif A._remote(model):
                why = f"{model} is a cloud model - refused"
            else:
                why = ""
            if why:
                out["conflicts_real"] = {"available": False, "why": why}
            else:
                out["conflicts_real"] = conflicts_part(
                    M, scratch, ask=T.ollama_caller(ollama, model), label=f"{model} (real)")
        except Exception as exc:
            out["conflicts_real"] = {"available": False,
                                     "why": f"{type(exc).__name__}: {exc}"[:300]}
    return out


def markdown(res: dict) -> list:
    lines = ["", "**\"Where did I put ...?\" and the overnight tidy** (2026-09-28): answered "
             "without the AI model from the places the owner said, newest first; and the "
             "tidy's \"Which is true now?\" finder."]
    w = res.get("where") or {}
    if w.get("total"):
        lines += ["", f"Where-questions answered right: **{w['right']}/{w['total']}**; an older "
                  f"place (or a guess where none was due) given: **{w['wrong_places']}**."]
        wrong = [c for c in w["cases"] if not c["ok"]]
        if wrong:
            lines.append("Wrong: " + "; ".join(f"{c['id']} ({c['ask']}): {c['said']!r}"
                                               for c in wrong))
    else:
        lines += ["", f"Where-questions: not measured - {w.get('why')}"]
    for key in ("conflicts", "conflicts_real"):
        c = res.get(key)
        if not c:
            continue
        if c.get("available") is False:
            lines += ["", f"\"Which is true now?\" ({key}): not measured - {c.get('why')}"]
            continue
        prec = c["precision"]
        lines += ["", f"\"Which is true now?\" with the {c['model']} model: precision "
                  f"**{prec if prec is not None else '-'}** ({c['right']} of {c['flagged']} "
                  f"pairs raised were real conflicts), recall **{c['recall']}** ({c['right']} of "
                  f"{c['conflicts']} real conflicts found), {c['distractors_flagged']} of "
                  f"{c['distractors']} pairs that can both be true raised. Model asked "
                  f"{c['asked']} times."
                  + (f" Missed: {', '.join(c['missed'])}." if c["missed"] else "")]
        if key == "conflicts":
            ok = prec is not None and prec >= PRECISION_BAR
            lines.append(f"The owner's bar is precision {PRECISION_BAR} or more: "
                         f"{'met' if ok else 'NOT met'}. The stand-in model is always right, "
                         "so this measures the finder, not the model.")
    if "conflicts_real" not in res:
        lines += ["", "The real model's precision is measured only on the PC "
                  "(--learner-model)."]
    return lines


def compared(old: dict, new: dict) -> list:
    """(name, earlier, now, how, gates) rows for eval_memory.compare."""
    out = []
    ow, nw = (old or {}).get("where") or {}, (new or {}).get("where") or {}
    if ow.get("total") and nw.get("total"):
        a, b = ow["total"] - ow["right"], nw["total"] - nw["right"]
        out.append(("where-questions wrong", a, b,
                    "unchanged" if a == b else ("better" if b < a else "WORSE"), True))
    oc, nc = (old or {}).get("conflicts") or {}, (new or {}).get("conflicts") or {}
    for k, up in (("precision", True), ("recall", True)):
        a, b = oc.get(k), nc.get(k)
        if a is None or b is None:
            continue
        how = "unchanged" if a == b else ("better" if (b > a) == up else "WORSE")
        out.append((f"which is true now: {k}", a, b, how, k == "precision"))
    return out
