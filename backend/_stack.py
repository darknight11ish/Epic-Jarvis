"""A stand-in for one of the owner's files, as the WHOLE patch stack leaves it.

WHY

About twenty suites test "the installed file" - jarvis_hud.py, jarvis_gate.py
- when it is there, and something else (a patch's own `+` lines, a
_skeleton rehearsal) when it is not. In CI it is never there, so the
installed-file branch of those suites never ran anywhere but the owner's PC.
That is how test_loopback_too.py came to fail only on the owner's machine:
bind-wildcard.patch, later in the stack, made `_loopback_companion` call a
new function, and the suite lifted `_loopback_companion` alone.

_skeleton.build() lays each named patch's after-image side by side. This goes
further: it walks every patch scripts/apply-patches.ps1 applies, IN ITS
ORDER, and applies each hunk for the target file with `git apply`. When a
hunk's context is not in the stand-in yet - it is text of the owner's
original file, which this repository does not hold - that context (the
hunk's pre-image) is added first, after a "# gap" line, and the hunk is then
applied to it. So every patch's lines are in the result, and where a later
patch rewrote an earlier one's lines, the result has the rewrite.

What it cannot say: anything about the owner's own lines between the hunks.
A hunk whose pre-image had to be added is logged ("materialised"); a hunk
whose context an EARLIER patch was meant to write, but did not, would be
materialised too rather than fail - scripts/apply-patches.ps1, on a copy of
the real files, is the only proof of that.

Not a test (no `test_` prefix). Standard library and git only.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS1 = HERE.parent / "scripts" / "apply-patches.ps1"
GAP = "# gap"


def order() -> list:
    """The patches apply-patches.ps1 applies, in its order, as paths under
    backend/: a patch the rebuilt modules supersede is its rebuilt-patches/
    half when it has one, and left out when it has none (the script always
    applies the halves, because it always copies the rebuilt modules in)."""
    ps1 = PS1.read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    sup_start = ps1.index("$REBUILT_SUPERSEDES = @{")
    sup = set(re.findall(r"^\s*'([\w.-]+\.patch)'\s*=",
                         ps1[sup_start:ps1.index("\n}", sup_start)], re.M))
    out = []
    for n in names:
        if n in sup:
            if (HERE / "rebuilt-patches" / n).is_file():
                out.append("rebuilt-patches/" + n)
        else:
            out.append(n)
    return out


_AT = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


def hunks(patch_text: str, target: str) -> list:
    """[(hunk text with its @@ line, pre-image lines)] for `target` in a patch.

    A hunk ends when the line counts in its @@ header are used up, the way
    git reads it. It used to end only at the next header, so the empty line
    at the very end of a patch file was read as one more (blank) context
    line - and the last hunk of rebuilt-patches/memory-safety.patch, which
    ends the file, then asked for a blank line the file does not have, and
    no stand-in of jarvis_extract.py could be built (auto-learn.patch,
    2026-09-24)."""
    out, cur, on = [], None, False
    left = [0, 0]                      # old lines, new lines still to come
    for line in patch_text.replace("\r\n", "\n").split("\n"):
        if cur is not None and left[0] <= 0 and left[1] <= 0 and not line.startswith("\\"):
            cur = None
        if line.startswith("+++ ") and cur is None:
            on = line.split()[1] == "b/" + target
            continue
        if line.startswith(("--- ", "diff ", "index ")) and cur is None:
            continue
        if not on:
            continue
        m = _AT.match(line)
        if m and cur is None:
            cur = [[line], []]
            left = [int(m.group(1) or 1), int(m.group(2) or 1)]
            out.append(cur)
        elif cur is not None and line[:1] in (" ", "-", "+", "\\"):
            cur[0].append(line)
            if line[:1] in (" ", "-"):
                cur[1].append(line[1:])
                left[0] -= 1
            if line[:1] in (" ", "+"):
                left[1] -= 1
        elif cur is not None and line == "":
            # A blank context line some editors strip to nothing.
            cur[0].append(" ")
            cur[1].append("")
            left[0] -= 1
            left[1] -= 1
    return [("\n".join(h) + "\n", pre) for h, pre in out]


def _apply(git: str, d: Path, target: str, hunk: str, *extra: str) -> bool:
    p = d / "one.patch"
    p.write_text(f"--- a/{target}\n+++ b/{target}\n{hunk}", encoding="utf-8", newline="\n")
    r = subprocess.run([git, "apply", *extra, "--include", target, str(p)], cwd=d,
                       capture_output=True, text=True)
    return r.returncode == 0


def stand_in(target: str, patches=None, *, replace: dict = None):
    """(text, log) - `target` after every patch in `patches` (default: the
    whole stack, order()). `replace` maps a patch name to other text to use
    for it (a rehearsal of an edited patch before it is committed). Returns
    (None, why) when git is missing or a hunk will not apply even to its own
    pre-image (a broken patch)."""
    git = shutil.which("git")
    if not git:
        return None, ["git is not installed"]
    patches = order() if patches is None else list(patches)
    d = Path(tempfile.mkdtemp(prefix="jarvis-stack-"))
    log = []
    try:
        f = d / target
        f.write_text("", encoding="utf-8", newline="\n")
        gaps = 0
        for name in patches:
            text_of = (replace or {}).get(name)
            if text_of is None:
                text_of = (HERE / name).read_text(encoding="utf-8")
            for hunk, pre in hunks(text_of, target):
                if _apply(git, d, target, hunk):
                    continue
                gaps += 1
                text = f.read_text(encoding="utf-8")
                if text and not text.endswith("\n"):
                    text += "\n"
                f.write_text(text + f"{GAP} {gaps}\n" + "\n".join(pre) + "\n",
                             encoding="utf-8", newline="\n")
                if not _apply(git, d, target, hunk):
                    return None, log + [f"{name}: a hunk does not apply even to its own "
                                        f"pre-image:\n{hunk[:400]}"]
                log.append(f"{name}: materialised {len(pre)} line(s) of the original")
        return f.read_text(encoding="utf-8"), log
    finally:
        shutil.rmtree(d, ignore_errors=True)


def function_text(source: str, name: str):
    """One top-level `def name(` and its body, cut out by lines (a stand-in is
    fragments, not a module Python can parse). None unless there is exactly one."""
    lines = source.splitlines()
    starts = [i for i, l in enumerate(lines) if l.startswith(f"def {name}(")]
    if len(starts) != 1:
        return None
    out = [lines[starts[0]]]
    for line in lines[starts[0] + 1:]:
        if line and not line[0].isspace():
            break
        out.append(line)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out) + "\n"


def fragment_with(source: str, needle: str):
    """The lines between the two "# gap" markers around `needle` - one piece
    of the original file with every patch's edits in it."""
    lines = source.splitlines()
    at = [i for i, l in enumerate(lines) if needle in l]
    if len(at) != 1:
        return None
    a = at[0]
    while a > 0 and not lines[a - 1].startswith(GAP):
        a -= 1
    b = at[0]
    while b + 1 < len(lines) and not lines[b + 1].startswith(GAP):
        b += 1
    return lines[a:b + 1]
