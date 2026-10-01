"""eval_topics.py - the self-test's part for TOPIC CONTROLS (2026-09-30;
docs/TOPIC-CONTROLS-DESIGN.md section 9, JARVIS-API section 107).

    python eval_memory.py                              # runs this too

Run by eval_memory.py; not on its own. It is not copied to the backend folder.
Made-up facts on a scratch store in the self-test's temporary folder; never the
owner's memory; no model is asked, nothing is sent anywhere.

WHAT IT CHECKS

  parity     With every topic on "Learn and use" - the state the feature ships
             in - a topic-aware memory returns EXACTLY the facts the memory
             without any topic rows returned, for every question, in the same
             order (the "chat recall" path, the entity layer on). Any
             difference is a bug. Checked at every filler size.

  off        The made-up person's facts carry a hand-labelled topic
             (eval/golden_topics.json). With Work set to Off, and again to
             "Learn, but don't use":
               leaks        Work facts that reach a question's five facts, on
                            the chat path (words, meaning, the entity list, "who
                            is this", past recall) and with a Work fact PINNED.
                            The number that matters. It must be 0. (The same
                            run with Work on shows how many WOULD leak, so a
                            zero is not a test that could not fail.)
               on-topic     recall@5 for the questions whose answers are all in
                            topics that stay on: not allowed to get worse.
               work-only    questions whose only answers are Work facts: no
                            Work fact may come back ("don't know" is right).
             and the search time with and without a blocked topic.

  sorting    The fixed rules that file a fact (layers 1-2 of jarvis_topics,
             no model) run over the same labelled facts: per topic, how many
             land in the right topic, in another topic, or Unsorted. These are
             MADE-UP English facts written for this test - NOT a measure of how
             well real facts are sorted. tools/topic_accuracy.py is the same on a
             bigger labelled set the owner can run and extend.
"""
from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
EVAL = HERE / "eval"
K = 5
SCENARIOS = (("off", "Work", "off"), ("learn_only", "Work", "learn_only"))


def _labels() -> dict:
    doc = json.loads((EVAL / "golden_topics.json").read_text(encoding="utf-8"))
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def _file(T, st, ids: dict, labels: dict) -> dict:
    """File the labelled facts under their topics, the owner's way (a tap):
    {topic name: topic id}."""
    with T._db(st) as c:
        by_name = {t["name"]: t["id"] for t in T.topics_of(c)}
    for name, fact_ids in labels.items():
        real = [ids[f] for f in fact_ids if f in ids]
        if real:
            T.file_facts({"ids": real, "topic_id": by_name[name]}, st)
    return by_name


def _recall(M, P, st, qs: list, gid: dict, now: float, pins: bool = False) -> dict:
    """Every question once, the way a chat turn recalls (entity layer on):
    {question id: [fact ids]}."""
    out = {}
    was = getattr(M, "_ENTITY_RECALL", None)
    M._ENTITY_RECALL = True
    try:
        for q in qs:
            if q["type"] == "belief":
                res = st.search(q["q"], k=K, known_at=_day(q["known_at"]), entities=True)
            else:
                res = P.recall(st, q["q"], k=K, now=now)
            if pins:
                res = M.with_profile(st, res, K)
            out[q["id"]] = [r["id"] for r in res]
    finally:
        if was is not None:
            M._ENTITY_RECALL = was
    return out


def _day(text: str) -> float:
    import eval_memory as E
    return E._day(text)


def _p(vals: list, q: float) -> float:
    vals = sorted(vals)
    return round(vals[int(q * (len(vals) - 1))], 2)


def _time(M, st, qs: list) -> dict:
    lat = []
    was = getattr(M, "_ENTITY_RECALL", None)
    M._ENTITY_RECALL = True
    try:
        for _ in range(3):
            for q in qs:
                t0 = time.perf_counter()
                st.search(q["q"], k=K, entities=True)
                lat.append((time.perf_counter() - t0) * 1000)
    finally:
        if was is not None:
            M._ENTITY_RECALL = was
    return {"p50_ms": round(statistics.median(lat), 2), "p95_ms": _p(lat, 0.95)}


def _sorting(T, st, ids: dict, facts: list, labels: dict) -> dict:
    truth = {f: name for name, fs in labels.items() for f in fs}
    by_id = {f["id"]: f for f in facts}
    out = {}
    with T._db(st) as c:
        ts = {t["id"]: t["name"] for t in T.topics_of(c)}
        for name in labels:
            right = other = missed = 0
            for f in labels[name]:
                got = T.classify(by_id[f]["text"], c)
                tid = got["topic_id"]
                if tid is None:
                    missed += 1
                elif ts.get(tid) == name:
                    right += 1
                else:
                    other += 1
            out[name] = {"total": len(labels[name]), "right": right, "other_topic": other,
                         "unsorted": missed}
        stray = [f["id"] for f in facts
                 if f["id"] not in truth and T.classify(f["text"], c)["topic_id"] is not None]
        out["_unlabelled_filed_somewhere"] = {"ids": stray, "of": len(facts) - len(truth)}
    return out


def run(M, scratch: Path, *, sizes: Optional[list] = None, words_only: bool = True) -> dict:
    """Every scenario once. {"available", "levels": [...], "sorting": {...}}.
    Never raises: a memory without topic tables is reported, not a crash."""
    try:
        import eval_memory as E
        import jarvis_past as P
        import jarvis_topics as T
        if not hasattr(M, "topic_blocked"):
            return {"available": False, "why": "this jarvis_memory.py has no topic controls"}
    except Exception as exc:
        return {"available": False, "why": f"{type(exc).__name__}: {exc}"}
    sizes = sorted(sizes or [0, 100, 1000])
    facts = E._read_jsonl(EVAL / "golden_facts.jsonl")
    qs = E._read_jsonl(EVAL / "golden_questions.jsonl")
    labels = _labels()
    now = E._day(E.EVAL_NOW_TEXT)
    out = {"available": True, "levels": [], "sorting": None, "scenarios": [s[0] for s in SCENARIOS]}
    d = scratch / "topics"
    d.mkdir(parents=True, exist_ok=True)
    emb = M.HashEmbedder() if words_only else M._make_embedder()
    st = M.MemoryStore(d / "memory.db", embedder=emb)
    ids = E._put_golden(M, st, facts)
    gid = {v: k for k, v in ids.items()}
    work_ids = {ids[f] for f in labels.get("Work", []) if f in ids}
    # The store as it is before any topic exists: what parity is measured against.
    plain = {"filler": 0}
    stream = E.filler("neutral")
    have = 0
    by_name = None
    was_recall = getattr(M, "_ENTITY_RECALL", False)
    try:
        for size in sizes:
            E._add_filler(st, stream, size - have)
            have = size
            # 1. before any topic row exists (the plain memory)
            with T._db(st) as c:
                c.execute("DELETE FROM fact_topics")
                c.execute("DELETE FROM topics")
                c.execute("DELETE FROM meta WHERE k IN ('topics_seeded','topic_starters')")
            before = _recall(M, P, st, qs, gid, now)
            # 2. the topics seeded, the labelled facts filed, every topic on "both"
            by_name = _file(T, st, ids, labels)
            with T._db(st) as c:
                c.execute("UPDATE fact_topics SET checked=1")
            same = _recall(M, P, st, qs, gid, now)
            level = {"filler_facts": size, "facts": st.status()["facts"],
                     "parity": before == same,
                     "parity_diff": [q for q in same if same[q] != before.get(q)][:10],
                     "scenarios": []}
            base = same
            answerable = [q for q in qs if q["answers"]]
            work_only = [q for q in answerable
                         if {ids[a] for a in q["answers"] if a in ids} <= work_ids]
            on_topic = [q for q in answerable if q not in work_only
                        and not ({ids[a] for a in q["answers"] if a in ids} & work_ids)]

            def hits5(res, group):
                return sum(1 for q in group
                           if {ids[a] for a in q["answers"] if a in ids} & set(res[q["id"]]))
            would = sum(1 for q in qs for i in base[q["id"]] if i in work_ids)
            timed = [q for q in qs if q["type"] in E.ANSWERABLE | {"abstain"}]
            level["unblocked"] = {"work_facts_in_answers": would,
                                  "on_topic_recall_at_5": hits5(base, on_topic),
                                  "on_topic_questions": len(on_topic),
                                  "work_only_questions": len(work_only),
                                  **_time(M, st, timed)}
            for label, topic, mode in SCENARIOS:
                T.set_mode(by_name[topic], mode, store=st)
                got = _recall(M, P, st, qs, gid, now)
                leaks = sorted({q for q in got for i in got[q] if i in work_ids})
                # a Work fact PINNED: the topic wins (owner's answer)
                pin_id = sorted(work_ids)[0]
                st.pin(pin_id)
                pinned = _recall(M, P, st, qs[:40], gid, now, pins=True)
                pin_leak = any(pin_id in v for v in pinned.values())
                st.unpin(pin_id)
                # the non-recall readers with their own paths
                with T._db(st) as c:
                    blocked = M.topic_blocked(c, "use")
                    visible = M.topic_blocked(c, "visible")
                level["scenarios"].append({
                    "mode": label, "topic": topic,
                    "leaks": len(leaks), "leaking_questions": leaks[:10],
                    "pin_leak": pin_leak,
                    "on_topic_recall_at_5": hits5(got, on_topic),
                    "on_topic_questions": len(on_topic),
                    "work_only_none": sum(1 for q in work_only
                                          if not (set(got[q["id"]]) & work_ids)),
                    "work_only_questions": len(work_only),
                    "blocked_ids_match": (blocked == work_ids) if label != "" else True,
                    "hidden_from_lists": len(visible),
                    **_time(M, st, timed)})
                T.set_mode(by_name[topic], "both", store=st)
            out["levels"].append(level)
        out["sorting"] = _sorting(T, st, ids, facts, labels)
    except Exception as exc:
        out["available"] = False
        out["why"] = f"{type(exc).__name__}: {exc}"
    finally:
        M._ENTITY_RECALL = was_recall
    return out


def markdown(res: dict) -> list:
    lines = ["", "**Topic controls** (JARVIS-API section 107): a topic set to \"don't use\" "
             "must never reach an answer, and with every topic on \"Learn and use\" nothing "
             "may change. Made-up facts; Work is the topic switched off."]
    if not res.get("available"):
        return lines + ["", f"Not measured: {res.get('why')}"]
    lines += ["", "| Filler | Facts | Same as with no topics? | Mode | Work facts in answers "
              "(would be, if on) | Leaks | Pinned Work fact leaks | On-topic recall@5 (on -> now) "
              "| Work-only questions with no Work fact | Search p50 ms (on -> blocked) |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for lv in res["levels"]:
        for sc in lv["scenarios"]:
            u = lv["unblocked"]
            lines.append(
                f"| {lv['filler_facts']:,} | {lv['facts']:,} | {'yes' if lv['parity'] else 'NO'} "
                f"| {sc['mode']} | {u['work_facts_in_answers']} | **{sc['leaks']}** "
                f"| {'YES' if sc['pin_leak'] else 'no'} "
                f"| {u['on_topic_recall_at_5']}/{u['on_topic_questions']} -> "
                f"{sc['on_topic_recall_at_5']}/{sc['on_topic_questions']} "
                f"| {sc['work_only_none']}/{sc['work_only_questions']} "
                f"| {u['p50_ms']} -> {sc['p50_ms']} |")
    s = res.get("sorting") or {}
    if s:
        lines += ["", "The fixed sorting rules on these made-up facts (English only; NOT a "
                  "measure of real facts): per topic, filed right / in another topic / left "
                  "Unsorted.", "", "| Topic | Facts | Right | Another topic | Unsorted |",
                  "|---|---|---|---|---|"]
        for name, v in s.items():
            if name.startswith("_"):
                continue
            lines.append(f"| {name} | {v['total']} | {v['right']} | {v['other_topic']} "
                         f"| {v['unsorted']} |")
        st = s.get("_unlabelled_filed_somewhere") or {}
        lines.append(f"\nUnlabelled facts the rules filed under some topic anyway: "
                     f"{len(st.get('ids', []))} of {st.get('of', 0)}.")
    return lines


def compared(old: dict, new: dict) -> list:
    """(name, old, new, how, gate) rows for --against: leaks and parity may
    never get worse."""
    out = []
    if not (isinstance(old, dict) and old.get("available") and new.get("available")):
        return out
    for a, b in zip(old.get("levels", []), new.get("levels", [])):
        if a.get("filler_facts") != b.get("filler_facts"):
            continue
        la = sum(s["leaks"] for s in a["scenarios"])
        lb = sum(s["leaks"] for s in b["scenarios"])
        out.append((f"topic leaks at {b['filler_facts']:,} filler", la, lb, "down", True))
        out.append((f"same as no topics at {b['filler_facts']:,} filler",
                    int(a["parity"]), int(b["parity"]), "up", True))
    return out
