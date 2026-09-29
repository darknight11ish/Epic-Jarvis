"""build_locomo_fixture.py - make backend/fixtures/locomo_multihop.json from LoCoMo.

    git clone https://github.com/snap-research/locomo /tmp/locomo
    python3 tools/build_locomo_fixture.py /tmp/locomo

WHAT IT KEEPS. LoCoMo (Snap Research, ACL 2024; data CC BY-NC 4.0) is ten
long made-up chats between two people, with questions whose answers are
known and, for each, the chat turns ("D3:13" = session 3, turn 13) that
hold the answer. Its "multi-hop" questions need two or more of those turns
joined up ("What is Caroline's relationship status?" needs D2:14 and D3:13).

The memory self-test (backend/eval_memory.py --locomo) stores every turn of
a chat as one memory item and asks whether search brings those evidence
turns back. So the fixture keeps, for FIVE of the ten chats, every turn
(the whole chat is the haystack; keeping only the evidence turns would make
search trivially easy) and their multi-hop questions. Nothing else: no
observations, summaries, event lists, image links or other question types.

WHICH FIVE. All ten would be about 1 MB. The five with the most multi-hop
questions are kept (ties: the earlier chat in LoCoMo's own file), so the
fixture stays near half a megabyte and still has most of the questions.

WHICH QUESTIONS ARE "MULTI-HOP". LoCoMo's file numbers the kinds, and its
README does not say which number is which. task_eval/evaluation.py does:
category 1 is scored as "multi-hop ... sub-answers" (2, 3, 4 are single-hop,
temporal and open-domain; 5 is adversarial). And 276 of the 282 category-1
questions do cite two or more turns. That reading is recorded in the fixture.

EVIDENCE FIXES. A few evidence ids in LoCoMo's file are malformed or name a
turn that does not exist. They are mended when the fix is unambiguous
("D:11:26" -> "D11:26", "D8:6; D9:17" -> two ids), dropped when the turn
does not exist, and every change is listed in the fixture's "fixes". A
question left with no evidence at all is left out, and listed too.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "backend" / "fixtures" / "locomo_multihop.json"
MULTI_HOP = 1
KEEP = 5


def _date(text: str) -> str:
    """'1:56 pm on 8 May, 2023' -> '2023-05-08T13:56'."""
    return datetime.strptime(text.strip(), "%I:%M %p on %d %B, %Y").strftime("%Y-%m-%dT%H:%M")


def _mend(raw: str) -> list:
    out = []
    for part in re.split(r"[;,]\s*", raw.strip()):
        m = re.fullmatch(r"D:?(\d+):(\d+)", part.strip())
        if m:
            out.append(f"D{int(m.group(1))}:{int(m.group(2))}")
    return out


def build(src: Path) -> dict:
    data = json.loads((src / "data" / "locomo10.json").read_text(encoding="utf-8"))
    commit = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    ranked = sorted(enumerate(data), key=lambda p: (
        -sum(q["category"] == MULTI_HOP for q in p[1]["qa"]), p[0]))
    chosen = sorted(i for i, _ in ranked[:KEEP])
    fixes, convs = [], []
    for i in chosen:
        s = data[i]
        c = s["conversation"]
        nums = sorted(int(k.split("_")[1]) for k in c if re.fullmatch(r"session_\d+", k))
        sessions, have = [], set()
        for n in nums:
            turns = []
            for t in c[f"session_{n}"]:
                row = [t["dia_id"], t["speaker"], t["text"]]
                if t.get("blip_caption"):
                    row.append(t["blip_caption"])
                turns.append(row)
                have.add(t["dia_id"])
            sessions.append({"session": n, "date": _date(c[f"session_{n}_date_time"]),
                             "turns": turns})
        questions = []
        for q in s["qa"]:
            if q["category"] != MULTI_HOP:
                continue
            ev = []
            for raw in q.get("evidence", []):
                mended = _mend(raw)
                if mended != [raw]:
                    fixes.append({"chat": s["sample_id"], "question": q["question"],
                                  "evidence": raw, "now": mended or None,
                                  "why": "malformed id"})
                for e in mended:
                    if e not in have:
                        fixes.append({"chat": s["sample_id"], "question": q["question"],
                                      "evidence": e, "now": None,
                                      "why": "no such turn in the chat"})
                    elif e not in ev:
                        ev.append(e)
            if not ev:
                fixes.append({"chat": s["sample_id"], "question": q["question"],
                              "evidence": None, "now": None,
                              "why": "no evidence left - question left out"})
                continue
            questions.append({"q": q["question"], "answer": str(q["answer"]),
                              "evidence": ev})
        convs.append({"id": s["sample_id"], "speakers": [c["speaker_a"], c["speaker_b"]],
                      "sessions": sessions, "questions": questions})
    return {
        "source": "LoCoMo (Snap Research), https://github.com/snap-research/locomo - "
                  "Maharana, Lee, Tulyakov, Bansal, Barbieri and Fang, \"Evaluating Very "
                  "Long-Term Conversational Memory of LLM Agents\", ACL 2024",
        "commit": commit,
        "file": "data/locomo10.json",
        "licence": "CC BY-NC 4.0 (Creative Commons Attribution-NonCommercial 4.0 "
                   "International), LoCoMo's LICENSE.txt. Test data only: never shipped "
                   "to the PC's backend folder or in either app. Credited in "
                   "THIRD-PARTY-NOTICES.txt.",
        "changes": "Cut down, not edited: the turns of 5 of the 10 chats (the five with "
                   "the most multi-hop questions) as [turn id, speaker, text, optional "
                   "image caption], session dates as ISO (from e.g. '1:56 pm on 8 May, "
                   "2023'), and their category-1 (multi-hop) questions with answer and "
                   "evidence turn ids. Evidence ids mended or dropped as listed in "
                   "\"fixes\". Made by tools/build_locomo_fixture.py.",
        "multi_hop_category": "category 1, per LoCoMo's task_eval/evaluation.py "
                              "('multi-hop eval by splitting ... into sub-answers')",
        "fixes": fixes,
        "chats": convs,
    }


def dump(doc: dict) -> str:
    """Readable and small: indented, but one turn per line."""
    head = {k: v for k, v in doc.items() if k != "chats"}
    lines = ["{"]
    for k, v in head.items():
        lines.append(f" {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},")
    lines.append(' "chats": [')
    for ci, c in enumerate(doc["chats"]):
        lines.append("  {")
        lines.append(f'   "id": {json.dumps(c["id"])},')
        lines.append(f'   "speakers": {json.dumps(c["speakers"], ensure_ascii=False)},')
        lines.append('   "questions": [')
        qs = [json.dumps(q, ensure_ascii=False) for q in c["questions"]]
        lines += [f"    {q}," for q in qs[:-1]] + [f"    {qs[-1]}"]
        lines.append("   ],")
        lines.append('   "sessions": [')
        for si, s in enumerate(c["sessions"]):
            lines.append(f'    {{"session": {s["session"]}, "date": {json.dumps(s["date"])}, '
                         '"turns": [')
            ts = [json.dumps(t, ensure_ascii=False) for t in s["turns"]]
            lines += [f"     {t}," for t in ts[:-1]] + [f"     {ts[-1]}"]
            lines.append("    ]}" + ("," if si < len(c["sessions"]) - 1 else ""))
        lines.append("   ]")
        lines.append("  }" + ("," if ci < len(doc["chats"]) - 1 else ""))
    lines.append(" ]")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__.split("\n\n")[1])
        return 2
    doc = build(Path(argv[1]))
    text = dump(doc)
    assert json.loads(text) == json.loads(json.dumps(doc))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    n = sum(len(c["questions"]) for c in doc["chats"])
    t = sum(len(s["turns"]) for c in doc["chats"] for s in c["sessions"])
    print(f"{OUT}: {len(doc['chats'])} chats, {t} turns, {n} multi-hop questions, "
          f"{len(doc['fixes'])} fixes, {len(text.encode('utf-8')):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
