#!/usr/bin/env python3
"""Does every measured claim a work setup makes still trace back to the numbers?

    python3 tools/check_work_claims.py

`backend/jarvis_work.py` says things like "3x slower split across both cards",
"9.17 GB", "44.9 tokens a second" and "scored 8/10". Each of those is a
measurement somebody made on the owner's PC on 2026-10-10, and each one is
what the owner reads on screen. A number that drifts - because a model was
re-measured, or because somebody edited the words - would quietly become a
false claim about the owner's own machine, which is the kind of wrong answer
this project treats as worse than no answer.

So: every claim the module makes is a numbered line in `CLAIMS` below, with
the words that MUST appear in the evidence. This fails when one is missing.

WHERE THE EVIDENCE IS. The two reports named by `jarvis_work.EVIDENCE`:

    .dsh-scratch/android-verify/MODEL-STRATEGY-2026-10-10.md
    .dsh-scratch/android-verify/MODEL-BENCH-2026-10-10.md

`.dsh-scratch/` is not in git, so on a machine without it this exits 2 - a
code of its own, never 0 - with the plain reason printed rather than passing
quietly. The suite that runs it (`backend/test_work.py`) reports that as a
SKIP, so a checkout without the reports is green-but-honest, and the check
really runs wherever the measurements are.

WHAT IT DOES NOT CHECK. It does not re-measure anything and it cannot say the
numbers are still true today - only that the module still quotes the numbers
the reports actually contain. Re-running the measurement is
`.dsh-scratch/android-verify/strategy-raw/`, which is a person's job.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_work as W  # noqa: E402

#: (claim id, the setup it belongs to ("" = the module's own rules), phrases
#: that must appear in the evidence). A phrase is matched with its spaces
#: flexible, so a report writing "196,608 tokens" satisfies "196,608".
CLAIMS = (
    ("rule-pin-one-card", "",
     ("both-card server was *three times slower* on `qwen3.5:9b` @ 196,608 "
      "(13.4 vs 44.9 tok/s)",
      "When a model fits on one card, pinning it there is better")),
    ("rule-long-context-card", "",
     ("`qwen3.5:9b` holds **196,608 tokens** entirely in video memory on the 2060",
      "RTX 2080 SUPER 8 GB - max clean `num_ctx`")),
    ("rule-fast-card", "",
     ("64.0 vs 49.3 tok/s", "`qwen3:8b` on the 2080 Super is genuinely faster than on the 2060")),
    ("rule-both-cards-free", "",
     ("the main model lost **1.9%** of its writing speed",)),
    ("rule-13gb-ceiling", "",
     ("**The honest headline: nothing bigger than about 13 GB fits.**",
      "Every 27B-and-up model on the current library is 16-24 GB")),
    ("rule-thinking-empty", "",
     ('Jarvis must send `"think": false` for ordinary turns',
      "returned an **empty answer** on all three test questions")),

    ("everyday", "everyday",
     ("| `qwen3:8b` | 4.87 GB | Apache 2.0 | 2080 Super | 5.84 GB @16k | **16,384** |",
      "| `qwen3.5:9b` | 6.10 GB | Apache 2.0 | 2060 | 9.17 GB @192k | **196,608** |",
      "about 15,600 tokens of real input",
      "it gives the outdated reason first")),

    ("coding", "coding",
     ("| **`ornith:9b`** (the agentic-coding specialist) | **8 / 10** |",
      "| `qwen3.5:9b` | **10 / 10** |",
      "| `qwen3.5:4b` | **10 / 10** |",
      "still fits** on the 2060 + 2080 pair",
      "77.1")),

    ("admin", "admin",
     ("**`qwen3.5:9b` gave the best answer.**",
      "~30% slower per token",
      "12x more conversation")),

    ("long", "long",
     ("| `qwen3.5:4b` | 2060 | 262,144 | 8.27 GB | 8.27 GB | 0 | 63.1 tok/s |",
      "**WRONG**, and self-contradictory",
      "21.9", "40,960")),

    ("specialist", "specialist",
     ("| `ornith:9b` **[new]** | 5.24 GB | **MIT** | 2060 | 5.07 GB @8k | **196,608** |",
      "45.6 vs 49.3 tok/s",
      "SWE-bench, Terminal-Bench")),
)

#: Phrases in the module that must match a claim above, so a NEW number cannot
#: be added to a setup without a claim to back it. Digits with a unit, or a
#: bare measurement word - deliberately narrow, because a check that fails on
#: ordinary prose gets switched off.
_NUMBER = re.compile(
    r"\b\d[\d,\.]*\s*(?:GB|GiB|tok/s|tokens a second|tokens|MB|%|x\b|/10\b)", re.I)


def read_evidence() -> tuple:
    """(text, missing). Every evidence file, joined - or the files that are
    not here, which is a failure of its own (exit 2)."""
    text, missing = [], []
    for rel in W.EVIDENCE:
        p = ROOT / rel
        if not p.is_file():
            missing.append(rel)
        else:
            text.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(text), missing


def flexible(needle: str) -> "re.Pattern":
    """`needle` as a pattern with any run of whitespace between its words, so
    a phrase re-wrapped in the report still matches."""
    parts = [re.escape(w) for w in needle.split()]
    return re.compile(r"\s+".join(parts))


def main() -> int:
    text, missing = read_evidence()
    if missing:
        print("Not checked: the measurements this module quotes are not in this checkout.")
        for rel in missing:
            print(f"  missing: {rel}")
        print("They live in .dsh-scratch/, which is not in git. On the owner's PC they")
        print("are there. Nothing is claimed about the numbers without them.")
        return 2

    bad, ok = [], 0
    for claim_id, setup_id, needles in CLAIMS:
        for needle in needles:
            if flexible(needle).search(text):
                ok += 1
            else:
                bad.append((claim_id, needle))
    print(f"{ok} of {ok + len(bad)} measured phrases in the module's own words are in the reports")
    for claim_id, needle in bad:
        print(f"FAIL  {claim_id}: the reports do not say {needle!r}")

    # Every setup's claim_text must be traceable: any measurement-shaped phrase
    # in it has to appear in the evidence, so a fresh number cannot slip in.
    for s in W.SETUPS:
        for m in _NUMBER.finditer(W.claim_text(s)):
            got = m.group(0).strip()
            number = re.match(r"[\d,\.]+", got).group(0).rstrip(".")
            if not flexible(number).search(text):
                bad.append((s.id, got))
                print(f"FAIL  {s.id}: {got!r} appears in no measurement")
    if bad:
        print(f"\n{len(bad)} claim(s) the module makes are not in the evidence.")
        return 1
    print("every measured claim in jarvis_work.py traces back to a report")
    return 0


if __name__ == "__main__":
    sys.exit(main())
