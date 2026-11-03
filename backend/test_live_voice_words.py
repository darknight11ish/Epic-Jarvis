"""test_live_voice_words.py - the words about Live's voice check say what the
PC really does (DEF-028, docs/defect-register.tsv).

    python -B backend/test_live_voice_words.py

WHY THIS SUITE EXISTS. Since #1069 (2026-11-01) one successful check verifies
a whole Live session: the first full clip (>= jarvis_live.TRUST_SPOT_S, 2.0 s)
gets the real speaker check before any words are made, and from then on
nothing asks the owner to verify again - a 1.5 s to 2.0 s clip runs on the
session's own trust with no speaker model at all
(jarvis_live.trust_decision's "trusted" action, jarvis_speech._SessionTrusted),
and ending Live ends that trust. Several places still promised "every sentence
is checked", which stopped being true that day. DEF-028 recorded the copies;
this suite pins the corrected words so the promise cannot quietly come back.

WHAT IT READS (text only - no model, no network, no session): the two desktop
files, the two backend modules and their `jarvis-backend/` twins, the two
generated asks-first fixtures, docs/LIVE-DESIGN.md, docs/JARVIS-API.md and
backend/README.md. It also pins the two clip lengths the docs name against
the constants in backend/jarvis_live.py, because DEF-028 was words drifting
away from the code: change that rule and these sentences must be looked at.

WHAT IT DOES NOT PROVE: that the check runs (backend/test_live.py does), or
that the fixtures are current (tools/gen_asks_first_cases.py --check does).
This suite is about the promise, not the speaker model.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASSED = []
FAILED = []

#: Every place DEF-028 named, plus the Rust doc comment that repeated it.
PLACES = {
    "jarvis-desktop/src/desktop-help.js": "Your voice is checked once for the Live session on this PC",
    "jarvis-desktop/src/main.js": "Your voice is checked once for this Live session, not on every sentence.",
    "jarvis-desktop/src-tauri/src/live.rs": "then trusted without checking each sentence",
    "backend/jarvis_asks_first.py": "once per Live session and not again on each sentence",
    "jarvis-backend/jarvis_asks_first.py": "once per Live session and not again on each sentence",
    "backend/jarvis_voice_enroll.py": "Your voice is checked once per Live session",
    "jarvis-backend/jarvis_voice_enroll.py": "Your voice is checked once per Live session",
    "docs/LIVE-DESIGN.md": "That one check verifies the whole session, so later short replies are trusted without a check, and ending Live ends that trust.",
    "docs/JARVIS-API.md": "The owner's voice is verified once per session",
    "backend/README.md": "Your voice is checked once on the PC",
}

#: The false promise DEF-028 found, in every shape it was written.
OLD = (
    "Every sentence is still checked",
    "Every sentence is checked for your voice",
    "still checked to be your voice",
    "Unchanged, on every clip",
    "before any words, every clip",
    "whole clip, **checked for the owner's voice before any words exist**, and",
    "the voice check runs on every clip",
)
#: A new sentence promising a check on every sentence, however worded. It
#: must be the claim "every sentence is checked", not just those words near
#: each other: the corrected main.js comment says "every sentence goes as
#: source=live ... trusted without checking each sentence again", which is true.
OLD_SHAPE = re.compile(
    r"every (?:sentence|clip)[^.\n]{0,40}\b(?:is|are|gets?)\s+(?:still\s+)?checked",
    re.IGNORECASE)

#: The generated asks-first fixtures, whose `fixed:live` note carries the words.
FIXTURES = (
    "jarvis-desktop/tests/fixtures/asks-first-cases.json",
    "jarvis-client/app/src/test/resources/contract/asks-first-cases.json",
)
NOTE = ("Your voice is checked once per Live session and not again on each "
        "sentence; ending Live ends that trust.")
OLD_NOTE = "Every sentence is still checked for your voice"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def squash(text):
    """One line, so a pinned phrase can cross a line break in the source.

    Two things are removed first, and each one hid a copy of DEF-028 from a
    first version of this suite:
    - a Python module splits one sentence over two string literals
      (`"... is still "` then `"checked for your voice"`), so the quote join
      goes; without it the claim in jarvis_asks_first.py would read as
      `is still " "checked` and slip past;
    - a Rust or JavaScript comment repeats `//!` or `//` on every line, so
      those are stripped; without it live.rs's old "the voice check runs on
      / every clip" could never be matched as one sentence.
    """
    joined = re.sub(r'"\s*\n\s*"', "", text)
    joined = re.sub(r"(?m)^\s*//[/!]?\s?", "", joined)
    return re.sub(r"\s+", " ", joined).strip()


def t_every_place_is_present():
    """The suite fails loudly if a file moves, instead of passing on nothing."""
    for rel in list(PLACES) + list(FIXTURES):
        check(f"{rel} is in this checkout", (ROOT / rel).is_file(), rel)


def t_the_old_promise_is_gone():
    """DEF-028's sentences, in every shape, are gone from every place."""
    for rel in PLACES:
        text = squash(read(rel))
        kept = [phrase for phrase in OLD if phrase in text]
        check(f"{rel} carries none of DEF-028's sentences", not kept, kept)
        found = OLD_SHAPE.search(text)
        check(f"{rel} promises no check on every sentence", found is None,
              found.group(0) if found else "")
    for rel in FIXTURES:
        check(f"{rel} carries none of the old note", OLD_NOTE not in read(rel))


def t_each_place_states_the_rule():
    """The real rule is in each place's own words: verified once per session.

    Not a phrase this suite invented - the sentence DEF-028's repair wrote in
    that place, pinned so a later edit has to change this suite on purpose.
    """
    for rel, phrase in PLACES.items():
        text = squash(read(rel))
        check(f"{rel} states the rule: {phrase!r}", phrase in text, text[:400])
    # LIVE-DESIGN's table says it a second way, and names both clip lengths.
    live = squash(read("docs/LIVE-DESIGN.md"))
    check("LIVE-DESIGN.md's table says once per session",
          "**Once per session**" in live)
    check("LIVE-DESIGN.md names the 2.0 s clip", "2.0 s or more" in live)
    check("LIVE-DESIGN.md names the 1.5-2.0 s trusted clip", "1.5-2.0 s" in live)
    check("LIVE-DESIGN.md says the session is then trusted, with no per-sentence check",
          "the session then trusted (no per-sentence check)" in live)


def t_the_fixtures_carry_the_note():
    """Both generated copies carry the new note, and are the same file."""
    for rel in FIXTURES:
        check(f"{rel} carries the new note", NOTE in read(rel))
    first, second = (read(rel) for rel in FIXTURES)
    check("the two asks-first fixtures are byte-identical", first == second)


def t_the_twins_are_identical():
    """The two-file rule, for the two shipped modules this change touched."""
    for name in ("jarvis_asks_first.py", "jarvis_voice_enroll.py"):
        a = (ROOT / "backend" / name).read_bytes()
        b = (ROOT / "jarvis-backend" / name).read_bytes()
        check(f"backend/{name} and jarvis-backend/{name} are one file", a == b)


def t_the_words_match_the_code():
    """The clip lengths the docs name are the ones jarvis_live.py enforces.

    2.0 s is the clip that still gets the real check (TRUST_SPOT_S); 1.5 s is
    where the session's own trust starts (TRUST_STEADY_S). If either moves,
    the sentences this suite just pinned are out of date, which is exactly
    the defect DEF-028 was: words drifting away from the code.
    """
    live = read("backend/jarvis_live.py")
    spot = re.search(r"^TRUST_SPOT_S\s*=\s*([0-9.]+)", live, re.MULTILINE)
    steady = re.search(r"^TRUST_STEADY_S\s*=\s*([0-9.]+)", live, re.MULTILINE)
    check("jarvis_live.py still has TRUST_SPOT_S = 2.0",
          bool(spot) and spot.group(1) == "2.0",
          spot.group(0) if spot else "TRUST_SPOT_S not found - the words need a new look")
    check("jarvis_live.py still has TRUST_STEADY_S = 1.5",
          bool(steady) and steady.group(1) == "1.5",
          steady.group(0) if steady else "TRUST_STEADY_S not found - the words need a new look")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:                      # noqa: BLE001 - report, then fail
                import traceback
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
