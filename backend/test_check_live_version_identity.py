"""test_check_live_version_identity.py - the post-deploy identity check's own contract.

    py -3 -B backend/test_check_live_version_identity.py

WHY THIS EXISTS. Wave 6 (2026-11-06) deployed a healthy backend and still showed
the owner the wrong version: the live `VERSION` file said 0.2.421 while the
installed desktop was 0.2.433, and the HUD said "MISMATCH: the backend 0.2.421,
but this HUD expects 0.2.433". `tools/check_live_version_identity.py` is the
read-only checker that compares those two numbers, and this suite pins its three
answers and the one rule that matters most: **an unreadable side is exit 2, never
a pass.**

WHAT IS PROVED HERE, all on temporary folders:

  1. a match is exit 0, one line, and the line carries the agreed value;
  2. a mismatch is exit 1, and the line names BOTH values so a reader can act;
  3. a missing VERSION file, an EMPTY VERSION file, and an unreadable desktop are
     each exit 2 - the BLOCKED-is-never-a-pass rule;
  4. the real readers read what is on disk (a temp VERSION with surrounding
     whitespace is stripped; a missing one is ""), and the desktop reader never
     invents a value for a path that is not there;
  5. `--desktop-exe`, then `JARVIS_DESKTOP_EXE`, then the installed default - the
     same precedence `tools/reconcile_live_backend.py` uses, so the deploy and this
     check always name the same desktop;
  6. the CLI reaches the same decision (`main()` returns the code, not a print).

NOTHING HERE TOUCHES THE OWNER'S PC. The desktop reader is injected everywhere it
could read the real exe, and the only `main()` calls hand it temporary paths. On a
Windows runner the two real-reader checks still touch only a temp folder.
"""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

sys.path.insert(0, str(REPO / "tools"))
import check_live_version_identity as C  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def tmpdir(prefix="version-identity-test-"):
    return Path(tempfile.mkdtemp(prefix=prefix))


def write(path: Path, text: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run(live, exe="", live_version="", exe_version=""):
    """`C.check` with both readers injected. Returns (code, printed lines)."""
    lines = []
    code = C.check(
        live, exe,
        version_reader=lambda _p: live_version,
        exe_reader=lambda _p: exe_version,
        out=lines.append)
    return code, lines


# --------------------------------------------------------------------------
#   1. the three answers
# --------------------------------------------------------------------------

def t_a_match_is_exit_0_and_says_the_agreed_value():
    root = tmpdir()
    try:
        code, lines = run(root, "exe", live_version="0.2.433", exe_version="0.2.433")
        check("match: exit code is 0", code == C.MATCH == 0, code)
        check("match: exactly one line is printed", len(lines) == 1, lines)
        check("match: the line says MATCH and names the value",
              len(lines) == 1 and "MATCH" in lines[0] and "0.2.433" in lines[0], lines)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_mismatch_is_exit_1_and_names_both_values():
    root = tmpdir()
    try:
        code, lines = run(root, "exe", live_version="0.2.421", exe_version="0.2.433")
        check("mismatch: exit code is 1", code == C.MISMATCH == 1, code)
        check("mismatch: exactly one line is printed", len(lines) == 1, lines)
        check("mismatch: the line says MISMATCH and names BOTH values",
              len(lines) == 1 and "MISMATCH" in lines[0]
              and "0.2.421" in lines[0] and "0.2.433" in lines[0], lines)
        check("mismatch: ... and says what to do next",
              len(lines) == 1 and "release-marker" in lines[0], lines)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_an_unreadable_side_is_exit_2_and_never_a_pass():
    root = tmpdir()
    try:
        code, lines = run(root, "exe", live_version="", exe_version="0.2.433")
        check("unreadable: a missing/empty VERSION is exit 2", code == C.UNREADABLE == 2,
              code)
        check("unreadable: ... the line says UNREADABLE and is not a pass",
              len(lines) == 1 and "UNREADABLE" in lines[0]
              and "not a pass" in lines[0], lines)

        code2, lines2 = run(root, "exe", live_version="0.2.433", exe_version="")
        check("unreadable: an unreadable desktop is exit 2 too", code2 == 2, code2)
        check("unreadable: ... and names the desktop it could not read",
              len(lines2) == 1 and "UNREADABLE" in lines2[0]
              and "FileVersion" in lines2[0], lines2)

        # An empty VERSION file is not version "" - it is missing evidence, and the
        # REAL reader is what turns it into exit 2 here.
        empty = write(root / "empty-live" / "VERSION", "")
        lines3 = []
        code3 = C.check(empty.parent, "exe",
                        exe_reader=lambda _p: "0.2.433", out=lines3.append)
        check("unreadable: an EMPTY VERSION file is exit 2, never version ''",
              code3 == 2, (code3, lines3))

        # ... and the real reader with a real value is still a match.
        good = write(root / "good-live" / "VERSION", "0.2.433\n")
        code4 = C.check(good.parent, "exe",
                        exe_reader=lambda _p: "0.2.433", out=lambda _m: None)
        check("match: the real VERSION reader agrees with the seam -> 0", code4 == 0,
              code4)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --------------------------------------------------------------------------
#   2. the real readers, on temporary files only
# --------------------------------------------------------------------------

def t_the_real_readers_read_the_files_on_disk():
    root = tmpdir()
    try:
        live = root / "live"
        write(live / "VERSION", "  0.2.433\n")
        check("readers: the live VERSION is read and stripped",
              C.read_live_version(live) == "0.2.433", C.read_live_version(live))
        check("readers: a missing live folder reads as ''",
              C.read_live_version(root / "no-such-folder") == "")
        empty = root / "empty"
        write(empty / "VERSION", "")
        check("readers: an empty VERSION file reads as ''",
              C.read_live_version(empty) == "")
        check("readers: a missing desktop exe reads as '', never a guess",
              C.read_desktop_file_version(root / "no-desktop" / "jarvis-desktop.exe") == "")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_desktop_path_precedence_is_the_deploy_tools():
    root = tmpdir()
    try:
        explicit = root / "explicit" / "jarvis-desktop.exe"
        check("paths: an explicit --desktop-exe wins",
              C.desktop_exe_path(str(explicit)) == explicit,
              C.desktop_exe_path(str(explicit)))
        with mock.patch.dict(os.environ, {C.DESKTOP_EXE_ENV: str(root / "env.exe")}):
            check("paths: JARVIS_DESKTOP_EXE is used when no override is given",
                  C.desktop_exe_path() == root / "env.exe", C.desktop_exe_path())
        env = {k: v for k, v in os.environ.items() if k != C.DESKTOP_EXE_ENV}
        env["LOCALAPPDATA"] = str(root / "Local")
        with mock.patch.dict(os.environ, env, clear=True):
            default = C.desktop_exe_path()
        check("paths: the default is %LOCALAPPDATA%\\Jarvis Desktop\\jarvis-desktop.exe",
              default == root / "Local" / C.DEFAULT_DESKTOP_DIR / C.DESKTOP_EXE_NAME,
              default)
        check("paths: the shipped default live folder holds jarvis_hud.py's neighbour",
              C.DEFAULT_BACKEND_PATH.name == "Desktop program", C.DEFAULT_BACKEND_PATH)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --------------------------------------------------------------------------
#   3. the CLI reaches the same decision
# --------------------------------------------------------------------------

def t_the_cli_returns_the_same_codes():
    root = tmpdir()
    try:
        # Both paths are temporary and the live one has no VERSION, so this
        # returns 2 before anything could read the owner's installed app.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = C.main(["--backend-path", str(root / "no-live"),
                           "--desktop-exe", str(root / "no-exe.exe")])
        check("cli: a missing VERSION through main() is exit 2", code == 2, code)
        check("cli: ... and main() printed the UNREADABLE line",
              "UNREADABLE" in buf.getvalue(), buf.getvalue())

        # A REAL temp VERSION with a missing --desktop-exe is still 2, and the
        # line names THAT exe - so the flag reaches the exe read instead of the
        # installed default.
        live = root / "live"
        write(live / "VERSION", "0.2.433")
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            code2 = C.main(["--backend-path", str(live),
                            "--desktop-exe", str(root / "no-exe.exe")])
        check("cli: --desktop-exe is threaded through (a missing exe is exit 2)",
              code2 == 2, code2)
        check("cli: ... and the line names the exe it could not read",
              "no-exe.exe" in buf2.getvalue(), buf2.getvalue())
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    for fn in (t_a_match_is_exit_0_and_says_the_agreed_value,
               t_a_mismatch_is_exit_1_and_names_both_values,
               t_an_unreadable_side_is_exit_2_and_never_a_pass,
               t_the_real_readers_read_the_files_on_disk,
               t_the_desktop_path_precedence_is_the_deploy_tools,
               t_the_cli_returns_the_same_codes):
        fn()
    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED, {len(PASSED)} passed")
        for name in FAILED:
            print(f"  - {name}")
        return 1
    print(f"all {len(PASSED)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
