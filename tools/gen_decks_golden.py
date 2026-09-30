#!/usr/bin/env python3
"""Regenerate backend/decks_fsrs_golden.json from the pinned py-fsrs itself.

    py -3 tools/gen_decks_golden.py        (needs fsrs==6.3.2, the version in backend/requirements.txt)

The file holds fixed rating sequences run straight through the library (not
through backend/jarvis_decks.py), fuzzing off, no learning steps: what py-fsrs
6.3.2 says each card's numbers are after each rating. backend/test_decks.py runs
the same sequences through Jarvis's own wrapper and compares, so a changed pin,
or a wrapper that drifts, fails loudly. These are py-fsrs's numbers only; they
are NOT checked against Anki's.

Regenerating is deliberate: do it only when the pin in requirements.txt moves,
and read the diff.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from importlib import metadata
from pathlib import Path

import fsrs

OUT = Path(__file__).resolve().parent.parent / "backend" / "decks_fsrs_golden.json"
T0 = datetime(2026, 10, 1, 9, 0, 0, tzinfo=timezone.utc)
R = {"again": fsrs.Rating.Again, "hard": fsrs.Rating.Hard, "good": fsrs.Rating.Good,
     "easy": fsrs.Rating.Easy}
# name -> [(rating, hours after the previous due date; None = at the due time)]
SEQUENCES = {
    "new_good_good": [("good", None), ("good", None)],
    "new_again_good": [("again", None), ("good", None)],
    "good_good_again_good": [("good", None), ("good", None), ("again", None), ("good", None)],
    "easy_then_good": [("easy", None), ("good", None)],
    "hard_then_good": [("hard", None), ("good", None)],
    "good_then_hard_late": [("good", None), ("hard", 72)],
    "same_day_twice": [("good", None), ("good", 3)],
}


def main() -> int:
    ver = metadata.version("fsrs")
    if ver != "6.3.2":
        print(f"fsrs {ver} is installed; this file is generated from 6.3.2", file=sys.stderr)
        return 1
    sch = fsrs.Scheduler(desired_retention=0.9, learning_steps=(), relearning_steps=(),
                         enable_fuzzing=False)
    out = {"fsrs": ver, "start": T0.timestamp(), "sequences": {}}
    for name, steps in SEQUENCES.items():
        card = fsrs.Card(card_id=1, due=T0)
        at, rows = T0, []
        for i, (rating, wait) in enumerate(steps):
            if i:
                at = card.due if name != "same_day_twice" else at
                if wait:
                    at = at + timedelta(hours=wait)
            card, _log = sch.review_card(card, R[rating], at)
            rows.append({"rating": rating, "at": at.timestamp(),
                         "after": {"state": int(card.state.value), "step": card.step,
                                   "stability": card.stability, "difficulty": card.difficulty,
                                   "due": card.due.timestamp(),
                                   "last_review": card.last_review.timestamp()}})
        out["sequences"][name] = rows
    OUT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
