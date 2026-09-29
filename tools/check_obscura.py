#!/usr/bin/env python3
"""The owner's check of the headless browser (Obscura), run ON THE OWNER'S PC.

    py -3 tools\\check_obscura.py                # check what is installed
    py -3 tools\\check_obscura.py --accept-new   # ... and remember a NEW file's checksum
    py -3 tools\\check_obscura.py --backend "C:\\path\\to\\Desktop program"

Nothing in this repository could run a real Obscura (it is a Windows program,
and the build machine is not Windows), so what the backend's driver
(backend/jarvis_obscura.py) does with the real program is checked HERE, by you,
once, and again whenever you update it. This prints what it did, in plain words:

  1. the file it found, and its SHA-256 (the checksum Jarvis remembers, so a
     different file later is refused until you run the install line again);
  2. the program's version;
  3. that stealth is on: a made-up page read with --stealth says
     navigator.webdriver is false, as an ordinary Chrome's does;
  4. that it starts as the standard-input/output server Jarvis talks to, and
     that it opens NO network port;
  5. that it loads a made-up page that is inside this check (no real website is
     visited) and reads its words and its boxes;
  6. that it REFUSES to visit a page on this PC (a tiny page this check serves
     on 127.0.0.1) - Obscura's own guard against reaching your own network;
  7. that it can take a screenshot (only a build with drawing can).

If every step passes, the result is saved next to Jarvis's settings
(obscura-check.json) and Settings shows it. If one does not, nothing is saved
and the line above it says which.

The install line in Settings (Headless browser) runs the same check for you
right after it unpacks the program. This is the same code, for running it by
hand.

It never touches a real website, a key, a proxy or your Jarvis settings other
than that one file. Standard library only.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check the headless browser (Obscura) on this PC.")
    ap.add_argument("--accept-new", action="store_true",
                    help="remember this file's checksum even if it differs from the one remembered "
                         "(use it right after you updated Obscura on purpose)")
    ap.add_argument("--backend", default="",
                    help="the folder holding jarvis_obscura.py (default: this repository's backend "
                         "folder)")
    ap.add_argument("--config", default="",
                    help="Jarvis's settings folder (default: the one Jarvis uses, ~/.openjarvis)")
    args = ap.parse_args(argv)
    backend = Path(args.backend).expanduser() if args.backend else ROOT / "backend"
    if not (backend / "jarvis_obscura.py").is_file():
        print(f"jarvis_obscura.py is not in {backend}. Run scripts\\apply-patches.ps1 first, or "
              f"pass --backend.")
        return 2
    if args.config:
        os.environ["OPENJARVIS_CONFIG_DIR"] = args.config
    sys.path.insert(0, str(backend))
    import jarvis_obscura as OB
    print(f"Using {backend / 'jarvis_obscura.py'}")
    print(f"Jarvis will start it as:  {' '.join(OB.command())}")
    print(f"Its settings folder:      {OB.install_dir()}")
    print()
    return OB.check(accept_new=args.accept_new)


if __name__ == "__main__":
    sys.exit(main())
