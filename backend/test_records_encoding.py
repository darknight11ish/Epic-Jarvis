"""The record files are real UTF-8, and no row carries a mojibake sequence.

    python3 test_records_encoding.py

WHY THIS EXISTS. On 2026-10-25 a merge read `git show` through the wrong
encoding and put a double-decoded section sign into one `docs/CLAIMS.tsv` row
where a plain section sign belonged. It was fixed by #816
(`changelog.d/2026-10-25-claims-register-utf8.md`), and finding it needed a
person to look. Every count checker passed while the row was wrong: mojibake is
*valid* UTF-8, so a reader that decodes the file never fails on it. This suite
is the gate that does.

WHAT THIS PINS

  1. Each record file decodes as strict UTF-8. A byte that is not UTF-8 fails
     here, named with the byte offset, instead of reaching a reader as a
     replacement character.
  2. No U+FFFD replacement character is in any of them. That is what a lossy
     decode leaves behind and it is never deliberate in a record.
  3. None of the three double-decode signatures appears: a lone `\u00c3`, a lone
     `\u00c2`, or `\u00e2\u20ac`. Each is one UTF-8 character decoded as
     Latin-1/CP1252 and encoded again; the 2026-10-25 incident's section sign is
     the third one twice over.
  4. The detector is proven against the real incident string, so a gate that
     quietly stopped matching cannot pass as a green suite.

`changelog.d/` is deliberately NOT scanned: one fragment quotes the bad bytes
on purpose, as the record of the bug. This gate is about the records the
repository *relies on*, not about history that quotes a failure.

Runs anywhere: standard library only, nothing of the owner's read.
"""
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


#: The files this gate is about. The four records first - they are what the
#: wrong decode hit and what the record checkers re-read on every run - then
#: the two pages that quote the register's measured numbers.
FILES = (
    ROOT / "docs" / "CLAIMS.tsv",
    ROOT / "docs" / "DECISIONS.md",
    ROOT / "docs" / "defect-register.tsv",
    ROOT / "docs" / "DEFECT-REGISTER.md",
    ROOT / "docs" / "ABOUT-JARVIS.md",
    ROOT / "README.md",
)

#: One UTF-8 character decoded as Latin-1/CP1252 and encoded again shows up as
#: one of these. The order matters only for the message.
SIGNATURES = ("\u00c3", "\u00c2", "\u00e2\u20ac", "\ufffd")


def mojibake_hits(text):
    """Return [(line number, signature)] for every line that carries one."""
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        for signature in SIGNATURES:
            if signature in line:
                hits.append((number, signature))
                break
    return hits


def t_every_record_is_strict_utf8():
    for path in FILES:
        name = path.relative_to(ROOT).as_posix()
        if not path.is_file():
            check(f"{name} exists", False, f"missing: {path}")
            continue
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            check(f"{name} decodes as UTF-8", False,
                  f"{exc.reason} at byte {exc.start} of {len(raw)}")
        else:
            check(f"{name} decodes as UTF-8", True)


def t_no_record_carries_mojibake():
    for path in FILES:
        name = path.relative_to(ROOT).as_posix()
        if not path.is_file():
            check(f"{name} is readable for the mojibake scan", False,
                  f"missing: {path}")
            continue
        text = path.read_bytes().decode("utf-8", errors="replace")
        hits = mojibake_hits(text)
        first = ", ".join(f"line {line}: {sig!r}" for line, sig in hits[:3])
        check(f"{name} has no mojibake", not hits,
              f"{len(hits)} line(s): {first}")


def t_the_detector_catches_the_real_incident():
    """The gate proves itself against the bytes that started it."""
    incident = "C18\t... the register's \u00c3\u201a\u00c2\u00a7 row ..."
    check("the detector flags the 2026-10-25 double-decoded section sign", bool(mojibake_hits(incident)))
    check("... and does not flag a correctly encoded section sign", not mojibake_hits("the register's \u00a7 row"))
    check("... and does not flag ordinary non-ASCII prose",
          not mojibake_hits("the phone · the PC — and one arrow →"))


if __name__ == "__main__":
    for fn in (t_every_record_is_strict_utf8,
               t_no_record_carries_mojibake,
               t_the_detector_catches_the_real_incident):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
