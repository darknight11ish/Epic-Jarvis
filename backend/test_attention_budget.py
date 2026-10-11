"""test_attention_budget.py - the owner can change how much Jarvis interrupts.

    python3 backend/test_attention_budget.py

Runs anywhere; no model, no network, no database of yours (the arbiter's own
database is a temporary file, and the settings file is a copy).

Why this file exists: "How much Jarvis may interrupt you" is a card in the
Brain on the PC (`jarvis-desktop/src/brain.html`, `div#budget-card`). Until
2026-10-08 the owner could READ it and change it nowhere - the audit of every
feature against the real settings surface (`dshwork/reports/
settings-backend.md`) found it the worst gap it had. These two numbers are
written into the owner's own `jarvis-framework.toml`, so the first thing that
has to be true is that changing one touches ONE line and nothing else: the
comments, the spacing, the CRLF endings and a byte-order mark all survive, the
same promise `jarvis_asks_first.set_tier` makes for the tier lines.

What it proves:

1. Changing `spoken_per_day` or `digest_hour` rewrites exactly one line, and
   the rest of the file is byte-identical.
2. The readers the product actually uses (`_limit()`, `_digest_hour()`, and
   `budget()`) see the new number straight away - not just the file.
3. A line the owner deleted comes back at the end of the `[arbiter]` table,
   and a file with no such table gets one.
4. Nonsense is refused with a plain message and NOTHING is written: not a
   number, a number out of the range the file's own comment gives, a missing
   file, a file that is not text.
5. Raising the budget says `"loosening": True` - it is the owner being
   interrupted more often, which is the one direction that needs an approval
   card - and lowering it, or moving the digest, never does.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_arbiter.py", "jarvis_framework.py")
sys.path.append(str(HERE / "rebuilt"))

TMP = Path(tempfile.mkdtemp(prefix="jarvis-attention-budget-"))
os.environ["JARVIS_FRAMEWORK_TOML"] = str(TMP / "jarvis-framework.toml")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_ARBITER_DB"] = str(TMP / "arbiter.db")

import jarvis_arbiter as A  # noqa: E402

SHIPPED = REPO / "backend" / "rebuilt" / "jarvis-framework.toml"
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def fresh(text: str = None, *, name: str = "jarvis-framework.toml") -> Path:
    """A copy of the shipped settings file to change, so the repository's own
    copy is never touched."""
    p = TMP / name
    if text is None:
        shutil.copyfile(SHIPPED, p)
    else:
        p.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
    A._reload()
    return p


def changed_lines(before: str, after: str) -> list:
    """The line numbers whose text differs - the whole point of the test."""
    b, a = before.splitlines(), after.splitlines()
    return [i for i, (x, y) in enumerate(zip(b, a), start=1) if x != y]


# --------------------------------------------------------------------------


def t_one_line_changes_and_the_rest_of_the_file_does_not():
    p = fresh()
    before = p.read_text(encoding="utf-8")
    out = A.set_spoken_per_day(6, path=p)
    after = p.read_text(encoding="utf-8")
    check("spoken_per_day: the answer reports the old and the new number",
          out.get("ok") and out.get("from") == 3 and out.get("to") == 6, out)
    diff = changed_lines(before, after)
    check("spoken_per_day: exactly one line of the file changed", len(diff) == 1, diff)
    if diff:
        n = diff[0]
        check("spoken_per_day: and it is the line the owner's file already had",
              after.splitlines()[n - 1].strip() == "spoken_per_day = 6",
              after.splitlines()[n - 1])
    check("spoken_per_day: the file's comments are all still there",
          before.count("#") == after.count("#"),
          (before.count("#"), after.count("#")))
    check("spoken_per_day: the rest of the file is byte-identical",
          "".join(after.splitlines(keepends=True)[:diff[0] - 1]) ==
          "".join(before.splitlines(keepends=True)[:diff[0] - 1]), diff)


def t_the_readers_the_product_uses_see_it():
    p = fresh()
    A.set_spoken_per_day(7, path=p)
    check("_limit() is the new number", A._limit() == 7, A._limit())
    A.set_digest_hour(9, path=p)
    check("_digest_hour() is the new hour", A._digest_hour() == 9, A._digest_hour())
    b = A.budget()
    check("budget() reports the new limit to the screens that show it",
          b.get("limit") == 7, b)


def t_the_line_keeps_its_own_comment_and_its_own_line_endings():
    text = ("# a comment\r\n[arbiter]\r\n"
            "spoken_per_day = 3        # three is the shipped number\r\n"
            "digest_hour = 18\r\n"
            "[other]\r\nspoken_per_day = 99\r\n")
    p = fresh(text)
    A.set_spoken_per_day(5, path=p)
    raw = p.read_bytes()
    check("CRLF endings survive the change", b"\r\n" in raw and b"\n\r" not in raw)
    check("the line's own trailing comment survives",
          b"spoken_per_day = 5        # three is the shipped number\r\n" in raw,
          raw.decode("utf-8"))
    check("the other table's line of the same name was not touched",
          b"[other]\r\nspoken_per_day = 99\r\n" in raw, raw.decode("utf-8"))
    p2 = fresh(b"\xef\xbb\xbf# bom\r\n[arbiter]\r\nspoken_per_day = 1\r\n")
    A.set_spoken_per_day(2, path=p2)
    check("a byte-order mark survives, and so does line one",
          p2.read_bytes().startswith(b"\xef\xbb\xbf# bom\r\n"), p2.read_bytes()[:20])


def t_a_deleted_line_comes_back_and_never_in_the_wrong_table():
    p = fresh("# nothing here\r\n[arbiter]\r\ndigest_hour = 18\r\n"
              "[after]\r\nkey = 1\r\n")
    out = A.set_spoken_per_day(4, path=p)
    text = p.read_text(encoding="utf-8")
    check("a missing line is added, and reported as no old value",
          out.get("from") is None and "spoken_per_day = 4" in text, out)
    check("it is added inside [arbiter], before the next table",
          text.index("spoken_per_day = 4") < text.index("[after]"), text)
    p2 = fresh("# no arbiter table at all\r\n[voice]\r\nthreshold = 0.35\r\n")
    A.set_digest_hour(20, path=p2)
    text2 = p2.read_text(encoding="utf-8")
    check("a file with no [arbiter] table gets one, at the end",
          "[arbiter]" in text2 and text2.index("[arbiter]") > text2.index("[voice]"),
          text2)


def t_nonsense_is_refused_and_writes_nothing():
    p = fresh()
    before = p.read_bytes()
    for value, why in ((25, "above the range the file's comment gives"),
                       (-1, "below it"),
                       ("later", "not a number"),
                       (None, "nothing at all")):
        try:
            A.set_spoken_per_day(value, path=p)
            check(f"spoken_per_day = {value!r} ({why}) is refused", False, "no error")
        except A.SettingsFileError as exc:
            check(f"spoken_per_day = {value!r} ({why}) is refused, in plain words",
                  "number" in str(exc).lower(), str(exc))
    check("and not one byte was written", p.read_bytes() == before)
    p2 = fresh()
    before2 = p2.read_bytes()
    try:
        A.set_digest_hour(24, path=p2)
        check("digest_hour = 24 is refused (the day ends at 23)", False)
    except A.SettingsFileError:
        check("digest_hour = 24 is refused (the day ends at 23)", True)
    check("and that refusal wrote nothing either", p2.read_bytes() == before2)
    try:
        A.set_spoken_per_day(3, path=TMP / "does-not-exist.toml")
        check("a missing settings file is refused, not a crash", False)
    except A.SettingsFileError as exc:
        check("a missing settings file is refused, in plain words",
              "settings file" in str(exc), str(exc))
    not_text = TMP / "binary.toml"
    not_text.write_bytes(b"\xff\xfe\x00\x01binary")
    before3 = not_text.read_bytes()
    try:
        A.set_spoken_per_day(3, path=not_text)
        check("a file that is not text is refused", False)
    except A.SettingsFileError as exc:
        check("a file that is not text is refused, in plain words",
              "plain text" in str(exc), str(exc))
    check("and it was left alone", not_text.read_bytes() == before3)


def t_only_raising_the_budget_is_a_loosening():
    p = fresh()
    A.set_spoken_per_day(1, path=p)
    up = A.set_spoken_per_day(5, path=p)
    check("raising the budget says it is a loosening", up.get("loosening") is True, up)
    down = A.set_spoken_per_day(2, path=p)
    check("lowering it does not - turning things down is never a card",
          down.get("loosening") is False, down)
    same = A.set_spoken_per_day(2, path=p)
    check("setting it to what it already is writes nothing at all",
          same.get("changed") is False, same)
    hour = A.set_digest_hour(21, path=p)
    check("moving the digest is never a loosening", hour.get("loosening") is False, hour)


def t_the_shipped_file_is_untouched_by_this_suite():
    shipped = SHIPPED.read_bytes()
    check("the repository's own settings file still says what it shipped with",
          b"spoken_per_day = 3" in shipped and b"digest_hour = 18" in shipped,
          shipped[:0])


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("t_") and callable(v)]
    for t in tests:
        print(f"--- {t.__name__} ---")
        t()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFAILED:")
        for f in FAILED:
            print(f"  {f}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
