#!/usr/bin/env python3
"""Writes the topic-controls contract both apps read (docs/TOPIC-CONTROLS-DESIGN.md,
JARVIS-API section 107):

    jarvis-desktop/tests/fixtures/topics-cases.json
    jarvis-client/app/src/test/resources/contract/topics-cases.json

    python3 tools/gen_topics_cases.py            # write both
    python3 tools/gen_topics_cases.py --check    # compare only

One source (backend/jarvis_topics.py) for:
  * every word both apps show - the four modes and their sentences, the errors
    by code, the row and picker lines, "Check these", "Show them", how a card
    ended;
  * the shared look - the eight colour slots (the chat tags' own palette, so
    the contrast is checked once) and the icon names, and the ready-made list;
  * the rule for which changes need a card, as worked examples every (old mode,
    new mode, private) - so neither app has to work it out its own way;
  * the name and keyword rules as valid / invalid examples;
  * the screen-reader and hidden-list lines.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
for p in (BACKEND, BACKEND / "rebuilt", ROOT / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_topics as T  # noqa: E402
import gen_history_cases as H  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "topics-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "topics-cases.json")

NAME_CASES = ["Work", "  Garden   plans ", "", "x" * 24, "x" * 25, "Tab\there", "Unsorted"]
WORDS_CASES = [["boiler", "central heating"], ["a"], ["x" * 31], ["fine", "fine"], [3],
               "one, two\nthree", None]


def build() -> dict:
    modes = [m[0] for m in T.MODE_INFO]
    mode_cases = []
    for old in modes:
        for new in modes:
            for private in (False, True):
                loosens = T.looser(old, new)
                mode_cases.append({"old": old, "new": new, "private": private,
                                   "loosens": loosens,
                                   "needs_card": bool(loosens and private)})
    return {
        "schema": 1,
        "words": T.WORDS,
        "errors": T.ERRORS,
        "last_words": T.LAST_WORDS,
        "gate_failed": T.GATE_FAILED_WORDS,
        "modes": [{"id": i, "name": n, "sentence": s} for i, n, s in T.MODE_INFO],
        "limits": {"max_topics": T.MAX_TOPICS, "name_max": T.NAME_MAX,
                   "words_max": T.WORDS_MAX, "batch": T.BATCH, "colours": T.COLOURS,
                   "unsorted_id": T.UNSORTED},
        "icons": list(T.ICONS),
        "palette": H.TAG_PALETTE,
        "starters": [{"name": n, "colour": c, "icon": i, "private": p}
                     for _k, n, c, i, p in T.STARTERS],
        "unsorted": {"name": T.WORDS["unsorted_name"], "colour": 6, "icon": "flag"},
        "mode_cases": mode_cases,
        "name_cases": [{"raw": n, "clean": T.clean_name(n)} for n in NAME_CASES],
        "words_cases": [{"raw": w, "clean": T.clean_words(w)} for w in WORDS_CASES],
        "screen_reader_cases": [
            {"name": "Work", "facts": 41, "mode": "use_only",
             "expect": T.WORDS["screen_reader"].format(name="Work", n=41,
                                                       mode=T.MODE_NAME["use_only"])},
            {"name": "Work", "facts": 1, "mode": "use_only",
             "expect": T.WORDS["screen_reader_one"].format(name="Work",
                                                           mode=T.MODE_NAME["use_only"])}],
        "hidden_row_cases": [
            {"index": 1, "facts": 41, "mode": "use_only",
             "expect": T.WORDS["hidden_row"].format(index=1, n=41,
                                                    mode=T.MODE_NAME["use_only"])},
            {"index": 2, "facts": 1, "mode": "use_only",
             "expect": T.WORDS["hidden_row_one"].format(index=2, mode=T.MODE_NAME["use_only"])}],
        "count_cases": [
            {"line": "kept_hidden", "n": 1, "expect": T.WORDS["kept_hidden_one"]},
            {"line": "kept_hidden", "n": 5, "expect": T.WORDS["kept_hidden"].format(n=5)},
            {"line": "skipped", "n": 1, "expect": T.WORDS["skipped_one"]},
            {"line": "skipped", "n": 3, "expect": T.WORDS["skipped"].format(n=3)},
            {"line": "sorted_guess", "n": 1, "total": 40, "expect": T.WORDS["sorted_guess_one"]},
            {"line": "sorted_guess", "n": 3, "total": 40,
             "expect": T.WORDS["sorted_guess"].format(n=3, total=40)}],
        "pin_paused_cases": [
            {"name": "Work", "mode": "off", "expect": T.WORDS["pin_paused"].format(name="Work")},
            {"name": "Work", "mode": "learn_only",
             "expect": T.WORDS["pin_paused_learn"].format(name="Work")}],
        "preview_cases": [
            {"name": "Work", "n": 12, "expect": T.WORDS["preview_left_out"].format(
                n=12, name="Work")},
            {"name": "Work", "n": 1, "expect": T.WORDS["preview_left_out_one"].format(
                name="Work")}],
        "card_cases": [
            {"name": "Health", "old": "learn_only", "new": "both", "private": True,
             "outside": False, "text": T.mode_card("Health", "learn_only", "both", True)},
            {"name": "Money", "old": "off", "new": "use_only", "private": True,
             "outside": True, "text": T.mode_card("Money", "off", "use_only", True, True)}],
    }


def main() -> int:
    text = json.dumps(build(), indent=2, ensure_ascii=False) + "\n"
    check = "--check" in sys.argv[1:]
    bad = False
    for path in (DESKTOP, PHONE):
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                print(f"STALE: {path.relative_to(ROOT)} - run python3 tools/gen_topics_cases.py")
                bad = True
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path.relative_to(ROOT)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
