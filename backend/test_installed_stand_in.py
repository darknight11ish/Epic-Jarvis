"""The "installed file" suites, run against the whole patch stack's output.

    python3 test_installed_stand_in.py

Several suites test the owner's installed jarvis_hud.py when there is one and
something else when there is not. CI never has one, so their installed-file
branch ran only on the owner's PC - which is where test_loopback_too.py first
failed: bind-wildcard.patch (later in the stack) made `_loopback_companion`
call `_binds_every_interface`, and the suite lifted `_loopback_companion`
alone (audit S1).

This builds a stand-in jarvis_hud.py from EVERY patch apply-patches.ps1
applies, in its order (backend/_stack.py), keeps the parts those suites read -
the functions they lift and the lines of main() the patches wrote - as a
module Python can parse, and runs each suite with JARVIS_BACKEND pointing at
it. Each must pass, and must say it tested the installed file.

What it cannot say: whether the owner's own lines between the hunks match.
Only apply-patches.ps1, on a copy of the real files, proves that.
"""
import ast
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _stack  # noqa: E402

FAILED, PASSED = [], []
SKIPPED = []

#: suite -> (the functions it lifts from jarvis_hud.py, a line of main() it reads,
#: what it prints when it used the installed file)
SUITES = {
    "test_loopback_too.py": (("_binds_every_interface", "_refuse_every_interface",
                              "_loopback_companion"),
                             "_loopback_companion(bind, HUD_PORT, Handler)",
                             "testing the function from the installed jarvis_hud.py"),
    "test_bind_wildcard.py": (("_binds_every_interface", "_refuse_every_interface",
                               "_loopback_companion"),
                              "_loopback_companion(bind, HUD_PORT, Handler)",
                              "testing the functions from the installed jarvis_hud.py"),
}

HEADER = '''"""A stand-in jarvis_hud.py: what the whole patch stack wrote, and nothing else.
Built by backend/test_installed_stand_in.py - not the owner's file."""
import os
import sys
from http.server import ThreadingHTTPServer

HUD_PORT = 4719


class Handler:
    pass

'''


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (It used to be check("SKIP - ...", True) - a condition of
    the constant True, so it printed as a pass and was counted as one.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


def _main_from(lines: list) -> str:
    """`def main():` around the stack's lines of it, trimmed at both ends to
    whole statements (a fragment starts and ends wherever a hunk did)."""
    body = list(lines)
    while body:
        text = "def main():\n    bind = os.environ.get('JARVIS_HUD_BIND', '127.0.0.1')\n" \
               + "\n".join(body) + "\n"
        try:
            ast.parse(text)
            return text
        except SyntaxError:
            pass
        # Drop a leading line that is deeper than main()'s own body first -
        # the middle of a block the fragment began in - then a trailing one.
        first = body[0]
        if len(first) - len(first.lstrip(" ")) != 4 or not first.strip():
            body.pop(0)
        else:
            body.pop()
    return ""


def build(source: str, names, needle: str):
    parts = [HEADER]
    for n in names:
        text = _stack.function_text(source, n)
        if text is None:
            return None, f"the stack does not write exactly one {n}()"
        parts.append(text + "\n\n")
    frag = _stack.fragment_with(source, needle)
    if frag is None:
        return None, f"the stack does not write exactly one line with {needle!r}"
    main = _main_from(frag)
    if needle not in main:
        return None, f"main()'s lines with {needle!r} could not be made into a function"
    parts.append(main)
    module = "".join(parts)
    ast.parse(module)
    return module, ""


def t_the_stack_builds():
    text, log = _stack.stand_in("jarvis_hud.py")
    check("every hunk of every patch for jarvis_hud.py applies, in apply-patches.ps1's order",
          text is not None, "\n".join(log[-3:]))
    if text:
        print(f"(stand-in: {len(text.splitlines())} lines, {len(log)} piece(s) of the "
              f"original had to be filled in)")


def t_the_stand_in_invents_no_more_than_it_used_to():
    """The ratchet (backend/_stack.py's RATCHET).

    A hunk whose pre-image is not in the stand-in gets that pre-image pasted in
    for it, and then applies - so a patch whose context has drifted looks fine,
    and every suite reading the stand-in proves nothing about the owner's real
    file. That is the shape of several bugs an audit found (2026-10-04). The
    number of such hunks is pinned per file and may only go DOWN.

    This FAILS when one goes up. That is not automatically a bug: a new patch
    whose context is text only the owner's PC holds raises the count honestly.
    Either way, look at which patch needed it, decide, then move the pin by
    hand in _stack.py's RATCHET. It never fails for going down."""
    for target, pinned in sorted(_stack.RATCHET.items()):
        st = _stack.materialised(target)
        if not st.get("hunks"):
            return skip(f"{target}: the stand-in could not be built here (no git)")
        got = st["materialised"]
        check(f"{target}: {got} hunk(s) invented a pre-image, pinned at {pinned}",
              got <= pinned,
              f"{got} now, {pinned} pinned - it went UP by {got - pinned}. Which patch "
              f"needed it: {sorted(st['by_patch'].items(), key=lambda kv: -kv[1])}. Look "
              f"at whether that patch's context is text an earlier patch should have "
              f"written (a real drift - fix the patch) or text only the owner's PC holds "
              f"(honest - raise _stack.py's RATCHET['{target}']), then say which in the "
              f"commit message.")
        if got < pinned:
            print(f"(note: {target} is {pinned - got} lower than the pin ({got} of "
                  f"{pinned}) - _stack.py's RATCHET can be tightened to {got})")


def t_each_installed_file_suite_passes_on_the_stand_in():
    text, log = _stack.stand_in("jarvis_hud.py")
    if text is None:
        if "git is not installed" in log[-1]:
            return skip("git is not installed, so the whole stack cannot be built here")
        return check("the stack stand-in could not be built", False, log[-1])
    for suite, (names, needle, said) in SUITES.items():
        module, why = build(text, names, needle)
        check(f"{suite}: a stand-in module is made from the stack", module is not None, why)
        if module is None:
            continue
        d = Path(tempfile.mkdtemp(prefix="jarvis-stand-in-"))
        try:
            (d / "jarvis_hud.py").write_text(module, encoding="utf-8")
            env = dict(os.environ, JARVIS_BACKEND=str(d), PYTHONDONTWRITEBYTECODE="1")
            r = subprocess.run([sys.executable, str(HERE / suite)], cwd=HERE, env=env,
                               capture_output=True, text=True, timeout=300)
            out = r.stdout + r.stderr
            check(f"{suite} used the installed-file branch", said in out, out[-600:])
            check(f"{suite} passes against the whole stack's jarvis_hud.py", r.returncode == 0,
                  "\n".join(out.strip().splitlines()[-25:]))
        finally:
            shutil.rmtree(d, ignore_errors=True)


def t_a_scratch_folder_inside_the_checkout_still_builds_the_stand_in():
    """TMPDIR inside the repository must not empty the stand-in.

    `git apply`, run anywhere inside a work tree, resolves the paths in the
    patch against the work-tree ROOT rather than the current directory. So a
    scratch folder under the checkout made a bare `--include jarvis_gate.py`
    match nothing - and git still exits 0 - leaving an EMPTY file that a dozen
    suites then asserted against. A review on 2026-10-08 pointed its temp
    folder inside the repository and spent an hour on the wreckage. The ceiling
    in `_gitapply.py` is what makes the answer the same either way; this check
    fails if it is ever dropped, and it is the reason the count below is the
    real one rather than zero."""
    inside = HERE.parent / "_stand_in_scratch"
    inside.mkdir(exist_ok=True)
    saved = tempfile.tempdir
    try:
        tempfile.tempdir = str(inside)
        text, log = _stack.stand_in("jarvis_gate.py")
    finally:
        tempfile.tempdir = saved
        shutil.rmtree(inside, ignore_errors=True)
    check("a scratch folder inside the checkout still builds the stand-in",
          bool(text and text.strip()), (log or ["(no log)"])[-1])
    check("...and it is the whole file, not an empty string",
          bool(text) and len(text) > 10000, f"{len(text or '')} characters")
    if text:
        stats = {}
        _stack.stand_in("jarvis_gate.py", stats=stats)
        check("...with the hunks the ratchet pins, not zero",
              stats.get("materialised") == _stack.RATCHET["jarvis_gate.py"],
              stats)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
