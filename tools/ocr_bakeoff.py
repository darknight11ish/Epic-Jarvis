#!/usr/bin/env python3
"""ocr_bakeoff.py - read the same pictures with BOTH picture readers and report
what each one actually said.

    py -3 tools/ocr_bakeoff.py <picture> [<picture> ...]
    py -3 backend/jarvis_ocr.py compare <picture> [<picture> ...]

Both spellings give the same numbers: this is only a front door. The
measurement itself lives in `backend/jarvis_ocr.py` (`compare_pictures` and
`report_comparison`), because a shipped backend file must not import anything
out of this repository - `scripts/check-backend.ps1` walks the imports of
every file that gets shipped and would fail on it - and because the owner has
to be able to run the measurement on their own PC, where the backend is and
this repository is not. This file imports the backend; the backend never
imports this.

WHY THE MEASUREMENT EXISTS
==========================
`jarvis_ocr.py` can read the words in a picture with Windows' own text
recognition (the default) or with RapidOCR (a second reader, added
2026-10-13, OFF until the owner turns it on). The research that put RapidOCR
on the shortlist said plainly that NOTHING YET SHOWS IT BEATS WINDOWS' OWN
READER on this owner's screen text. So it ships off, and this is the
measurement that would have to say otherwise. `jarvis_ocr.report_comparison`
documents exactly what is compared, and exactly what it does not prove.
"""
import sys
from pathlib import Path


def _backend():
    """backend/ beside this repository, or jarvis-backend/ - whichever is
    here. Nothing of it is imported until this runs."""
    here = Path(__file__).resolve().parent
    for cand in (here.parent / "backend", here.parent / "jarvis-backend"):
        if (cand / "jarvis_ocr.py").is_file():
            if str(cand) not in sys.path:
                sys.path.insert(0, str(cand))
            break
    import jarvis_ocr
    return jarvis_ocr


def main(argv=None) -> int:
    args = [a for a in (sys.argv[1:] if argv is None else argv) if a != "--"]
    if not args:
        print(__doc__.strip().split("\n\n")[0])
        print("\nGive it one or more picture files. Nothing leaves this PC.")
        return 2
    J = _backend()
    return J._cmd_compare(args)


if __name__ == "__main__":
    sys.exit(main())
