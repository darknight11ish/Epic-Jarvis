"""Build backend/no-expiry-cards.patch from the base's copy and mine.

    python .patchgen.py

The published base (jarvis-backend/) is edited directly, so each file's copy
at HEAD is the patch's pre-image. difflib produces the unified diff - the same
hunk headers git would - and the result is written with LF endings, which is
this repository's rule (.gitattributes: `* text=auto eol=lf`).

Run it again after any further edit to the two files.
"""
import difflib
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "backend" / "no-expiry-cards.patch"
TARGETS = ("jarvis_gate.py", "jarvis_owner_check.py", "jarvis_devices.py")


def lines(name: str) -> tuple:
    base = subprocess.run(["git", "show", f"HEAD:jarvis-backend/{name}"], cwd=HERE,
                          capture_output=True, check=True).stdout.decode("utf-8")
    mine = (HERE / "jarvis-backend" / name).read_text(encoding="utf-8")
    return base.splitlines(), mine.splitlines()


out = []
for name in TARGETS:
    old, new = lines(name)
    body = list(difflib.unified_diff(old, new, fromfile=f"a/{name}",
                                     tofile=f"b/{name}", n=6, lineterm=""))
    if not body:
        raise SystemExit(f"{name} is unchanged - nothing to write")
    out.append(f"--- a/{name}")
    out.append(f"+++ b/{name}")
    out.extend(body[2:])
OUT.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
print(f"wrote {OUT.relative_to(HERE)}  ({len(out)} lines)")
