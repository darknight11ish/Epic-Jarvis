"""Rehearse a new patch against the text earlier patches wrote.

WHY

The real jarvis_hud.py is on the owner's PC, not in this repository. A new
patch's context lines have to be real text of that file, and the only real
text this repository holds is what earlier patches put there - their `+`
lines and their context. So this builds a stand-in jarvis_hud.py out of
exactly that: the after-image of the named earlier hunks, at roughly their
real line numbers, with filler lines between them. Then `git apply --check`
answers one question honestly: does the new patch's context match what the
patches before it wrote?

What it cannot say: whether the rest of the real file matches, or whether
another patch applied between them changed those lines. The owner's own
`apply-patches.ps1` run, which rehearses the whole stack on a copy of the
real files, is the only proof of that.

Not a test by itself (no `test_` prefix); test_speed_record.py and
test_documents_owned.py use it.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def hunks(patch: str, target: str = "jarvis_hud.py") -> list:
    """[(after_start_line, after_lines)] for every hunk of `patch` on `target`."""
    out, cur, on = [], None, False
    for l in (HERE / patch).read_text(encoding="utf-8").splitlines():
        if l.startswith("+++ "):
            on = l.split()[1] == "b/" + target
            cur = None
            continue
        if l.startswith("--- ") or not on:
            continue
        if l.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", l)
            cur = (int(m.group(1)), [])
            out.append(cur)
        elif cur is not None and not l.startswith(("-", "\\")):
            cur[1].append(l[1:] if l[:1] in "+ " else l)
    return out


def build(*patches: str, target: str = "jarvis_hud.py") -> str:
    frags = sorted((h for p in patches for h in hunks(p, target)), key=lambda f: f[0])
    body = []
    for start, lines in frags:
        while len(body) < start - 3:
            body.append(f"# filler {len(body)}")
        body.append("# filler gap")
        body.extend(lines)
    body += ["# filler end"] * 5
    return "\n".join(body) + "\n"


def rehearse(new_patch: str, *earlier: str, target: str = "jarvis_hud.py",
             on_top: tuple = ()):
    """(ok, output). ok is None when git is not installed - a skip, not a pass.

    `on_top`: patches applied, in order, to the stand-in built from `earlier`
    before `new_patch` - for a new patch whose context is text a patch wrote
    INSIDE another patch's lines (speed-record's inside tool-calling-wiring's),
    which `build` cannot place, because it lays fragments side by side."""
    git = shutil.which("git")
    if not git:
        return None, "git is not installed, so the rehearsal could not run"
    d = Path(tempfile.mkdtemp(prefix="jarvis-skel-"))
    try:
        # LF on both sides, byte for byte, whatever this checkout did to the
        # patch files - apply-patches.ps1 does the same before applying.
        with open(d / target, "w", encoding="utf-8", newline="\n") as f:
            f.write(build(*earlier, target=target))
        for i, name in enumerate(on_top):
            below = d / f"below{i}.patch"
            below.write_bytes((HERE / name).read_bytes().replace(b"\r\n", b"\n"))
            r = subprocess.run([git, "apply", "--include", target, str(below)], cwd=d,
                               capture_output=True, text=True)
            if r.returncode != 0:
                return False, f"{name} (applied first): {r.stderr.strip() or r.stdout.strip()}"
        lf = d / "new.patch"
        lf.write_bytes((HERE / new_patch).read_bytes().replace(b"\r\n", b"\n"))
        steps = [["apply", "--check", str(lf)],
                 ["apply", str(lf)],
                 ["apply", "--check", "--reverse", str(lf)]]
        for args in steps:
            r = subprocess.run([git] + args, cwd=d, capture_output=True, text=True)
            if r.returncode != 0:
                return False, f"git {' '.join(args[:-1])}: {r.stderr.strip() or r.stdout.strip()}"
        return True, (d / target).read_text(encoding="utf-8")
    finally:
        shutil.rmtree(d, ignore_errors=True)
