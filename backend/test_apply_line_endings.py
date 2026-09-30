"""apply-patches.ps1 and a backend whose files have Windows line endings (CRLF).

Seen 2026-09-30: every line of the owner's jarvis_hud.py ended CRLF, the patches
are LF, and 100+ patches said "not onto the files as they are". The script only
reported it. Now `-FixLineEndings` backs each affected file up
(_jarvis-backup-<date>-endings) and rewrites it LF; without the switch nothing
of the owner's is touched. This builds a backend the way the patch stack leaves
it (_stack), turns it CRLF, and runs the real script under PowerShell 7 both ways.

Skipped where there is no PowerShell 7 (pwsh). Standard library + git + pwsh.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _stack  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name)
    if not cond and detail:
        print("        " + str(detail)[:400])


PWSH = shutil.which("pwsh") or ("/opt/pwsh/pwsh" if os.path.exists("/opt/pwsh/pwsh") else None)
PS1 = HERE.parent / "scripts" / "apply-patches.ps1"


def build_backend(dest: Path, crlf: bool) -> list:
    """Each patch target as the whole stack leaves it (what a fully patched backend is)."""
    targets = set()
    for name in _stack.order():
        text = (HERE / name).read_text(encoding="utf-8")
        targets |= set(re.findall(r"^\+\+\+ b/(\S+)", text, re.M))
    made = []
    for t in sorted(targets):
        body, _log = _stack.stand_in(t)
        if body is None:
            continue
        data = body.encode("utf-8")
        if crlf:
            data = data.replace(b"\n", b"\r\n")
        (dest / t).write_bytes(data)
        made.append(t)
    return made


def run(backend: Path, *extra) -> str:
    r = subprocess.run([PWSH, "-NoProfile", "-File", str(PS1), "-BackendPath", str(backend),
                        "-SkipTests", "-SkipPackages", *extra],
                       capture_output=True, text=True, timeout=900)
    return r.stdout + r.stderr


def t_crlf_backend():
    if not PWSH:
        print("SKIP  no PowerShell 7 (pwsh) here")
        return
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-endings-"))
    try:
        lf, crlf = tmp / "lf", tmp / "crlf"
        lf.mkdir()
        crlf.mkdir()
        made = build_backend(lf, crlf=False)
        build_backend(crlf, crlf=True)
        check("a fake backend was built", "jarvis_hud.py" in made, made)
        ref = run(lf)
        # The stand-in has one known artefact (memory-safety's rebuilt half wants the
        # original file's first lines); the reference run is the yardstick.
        ref_on = re.search(r"(\d+) of these are already on your backend", ref)
        check("the LF reference run recognises the applied patches", bool(ref_on), ref[-400:])
        before = (crlf / "jarvis_hud.py").read_bytes()

        bad = run(crlf)
        check("CRLF without the switch: names the files and the switch",
              "-FixLineEndings" in bad and "jarvis_hud.py (" in bad, bad[:600])
        check("CRLF without the switch: the patches do not fit (the reported symptom)",
              bad.count("not onto the files as they are") > 50 or "will not apply" in bad)
        check("CRLF without the switch: nothing of the owner's was rewritten",
              (crlf / "jarvis_hud.py").read_bytes() == before
              and not list(crlf.glob("_jarvis-backup-*-endings")))

        fixed = run(crlf, "-FixLineEndings")
        hud = (crlf / "jarvis_hud.py").read_bytes()
        check("-FixLineEndings: the file is LF now", b"\r\n" not in hud and hud.count(b"\n") > 100)
        check("-FixLineEndings: same content, only the endings changed",
              hud == before.replace(b"\r\n", b"\n"))
        backups = list(crlf.glob("_jarvis-backup-*-endings/jarvis_hud.py"))
        check("-FixLineEndings: the original was kept in a backup folder, CRLF as it was",
              len(backups) == 1 and backups[0].read_bytes() == before)
        fixed_on = re.search(r"(\d+) of these are already on your backend", fixed)
        check("-FixLineEndings: the result matches the LF backend's",
              bool(fixed_on) and bool(ref_on) and fixed_on.group(1) == ref_on.group(1),
              (fixed_on and fixed_on.group(0), ref_on and ref_on.group(0)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t_script_says_so():
    ps1 = PS1.read_text(encoding="utf-8")
    check("the script has the switch and documents it",
          "[switch] $FixLineEndings" in ps1 and ".PARAMETER FixLineEndings" in ps1)
    check("it backs up before it rewrites",
          ps1.index("_jarvis-backup-$Stamp-endings") < ps1.index("Copy-AsLf -Src $cf.Path"))


def main():
    for fn in (t_script_says_so, t_crlf_backend):
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
