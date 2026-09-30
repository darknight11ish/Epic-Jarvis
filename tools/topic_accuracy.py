#!/usr/bin/env python3
"""How well does Jarvis sort a fact into a topic? (topic controls, 2026-09-30)

    py -3 tools\\topic_accuracy.py                    # the fixed rules only (no model)
    py -3 tools\\topic_accuracy.py --model qwen3:8b   # ... and the local model's suggestion
                                                       # for the facts the rules left Unsorted
    py -3 tools\\topic_accuracy.py --extra mine.jsonl # add your own labelled lines

Reads backend/topic_cases/cases.jsonl - one made-up fact per line with the topic
a person would file it under ("topic": null = belongs to none of the ready-made
topics) - and runs jarvis_topics.classify() on each. Writes nothing into any
memory of yours: the topics live in a new file in a temporary folder that is
deleted at the end. Nothing is sent anywhere without --model, and then only to
this PC's Ollama (loopback).

THE TWO NUMBERS THAT MATTER, per topic X:
  leak     of the facts that belong under X, how many the rules did NOT file under
           X. If X is switched Off, each of these could still reach an answer.
  held     of the facts that belong elsewhere (or nowhere), how many the rules
           filed under X anyway. If X is switched Off, each of these is wrongly
           left out of answers.

THIS IS NOT A MEASURE OF YOUR REAL FACTS. The set is small, English (plus two
health/money lines the measured sensitive-topic lists cover), and written for
the test. The numbers say how the RULES behave on it; add your own lines and
run it again to see how they behave on what you actually say.
"""
import argparse
import json
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"


def _load(scratch: Path):
    os.environ["JARVIS_MEMORY_DB"] = str(scratch / "memory.db")
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = scratch
    fw.LOG_DIR = scratch
    fw.audit_log = lambda *a, **k: None
    fw.load_framework = lambda *a, **k: {}
    sys.modules["jarvis_framework"] = fw
    real = os.environ.get("JARVIS_BACKEND")
    paths = ([real] if real and (Path(real) / "jarvis_memory.py").is_file() else []) \
        + [str(BACKEND / "rebuilt"), str(BACKEND)]
    for p in reversed(paths):
        sys.path.insert(0, p)
    import jarvis_memory as M
    import jarvis_topics as T
    return M, T


def _read(path: Path) -> list:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--extra", default=None, help="another cases file (same format)")
    ap.add_argument("--model", default=None, help="also ask this local Ollama model")
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--out", default=str(Path.home() / "jarvis-topic-accuracy"))
    a = ap.parse_args(argv)
    cases = _read(BACKEND / "topic_cases" / "cases.jsonl")
    if a.extra:
        cases += _read(Path(a.extra))
    with tempfile.TemporaryDirectory(prefix="jarvis-topic-accuracy-") as tmp:
        M, T = _load(Path(tmp))
        st = M.MemoryStore(Path(tmp) / "memory.db", embedder=M.HashEmbedder())
        with T._db(st) as c:
            ts = T.topics_of(c)
            names = {t["id"]: t["name"] for t in ts}
            rows = []
            for case in cases:
                got = T.classify(case["text"], c, topics=ts)
                filed = names.get(got["topic_id"]) if got["topic_id"] else None
                rows.append((case["text"], case.get("topic"), filed, got["sure"]))
        topics = sorted({r[1] for r in rows if r[1]})
        lines = ["# Topic sorting: the fixed rules on the labelled facts", "",
                 f"{len(rows)} facts. NOT a measure of real facts (see the top of "
                 "tools/topic_accuracy.py).", "",
                 "| Topic | Facts | Filed right | Filed elsewhere | Left Unsorted | Leak | "
                 "Others filed here (held) | Held |", "|---|---|---|---|---|---|---|---|"]
        summary = {}
        for t in topics:
            mine = [r for r in rows if r[1] == t]
            right = sum(1 for r in mine if r[2] == t)
            other = sum(1 for r in mine if r[2] not in (None, t))
            none = sum(1 for r in mine if r[2] is None)
            others = [r for r in rows if r[1] != t]
            held = sum(1 for r in others if r[2] == t)
            summary[t] = {"facts": len(mine), "right": right, "leak": len(mine) - right,
                          "held": held}
            lines.append(f"| {t} | {len(mine)} | {right} | {other} | {none} "
                         f"| {100 * (len(mine) - right) / max(1, len(mine)):.0f}% "
                         f"| {held} of {len(others)} | {100 * held / max(1, len(others)):.0f}% |")
        unl = [r for r in rows if r[1] is None]
        stray = [r for r in unl if r[2] is not None]
        lines += ["", f"Facts that belong to no ready-made topic: {len(unl)}; filed under "
                  f"a topic by the rules anyway: {len(stray)}."]
        wrong = [r for r in rows if r[1] != r[2]]
        if wrong:
            lines += ["", "Every fact the rules did not file as labelled:", ""]
            lines += [f"- {r[0]}  ->  should be {r[1] or 'Unsorted'}, was {r[2] or 'Unsorted'}"
                      for r in wrong]
        if a.model:
            import jarvis_sensitive as S
            import jarvis_auto_learn as A
            why = A.check_local_model(a.ollama, a.model)
            if why:
                lines += ["", f"The model part did not run: {why}."]
            else:
                ask = S.ollama_caller(a.ollama, a.model)
                with T._db(st) as c:
                    ts = T.topics_of(c)
                ok = tot = 0
                for text, truth, filed, _sure in rows:
                    if filed is not None:
                        continue
                    tot += 1
                    tid = T.suggest_with_model(text, ts, ask)
                    guess = next((t["name"] for t in ts if t["id"] == tid), None)
                    ok += guess == truth
                lines += ["", f"The local model ({a.model}) on the {tot} facts the rules left "
                          f"Unsorted: {ok} right (it may answer 'unsure' - that counts as "
                          "Unsorted, right only for a fact that belongs to no topic)."]
        text = "\n".join(lines) + "\n"
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "topic-accuracy.md").write_text(text, encoding="utf-8")
        print(text)
        print(f"Saved: {out / 'topic-accuracy.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
