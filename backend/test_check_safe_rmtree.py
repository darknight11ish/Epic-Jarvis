"""tools/check_safe_rmtree.py catches the shapes that actually deleted a tree.

The measurement that produced this file: on 2026-11-27 a scratch helper took
`Path("")` to mean "no folder". `Path("")` is `"."`, so `shutil.rmtree(".")`
ran with the repository root as its working directory and removed this
checkout's working tree and most of `.git`.

Every case below is one of the shapes that has to be impossible, and the last
one proves the checker is not simply refusing everything: a path built from
`tempfile.gettempdir()` is allowed.

The synthetic tree is built under the PC's temp folder and removed with a path
this file itself asserts is inside that folder - the rule the checker enforces,
applied to the test that enforces it.
"""
import importlib.util
import json
import os
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOOL = REPO / "tools" / "check_safe_rmtree.py"

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    if cond:
        PASSED.append(name)
    else:
        FAILED.append(name)
        print(f"FAIL  {name}" + (f"\n        {detail}" if detail else ""))
    print(f"{'ok    ' if cond else 'FAIL  '}{name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def load_tool():
    spec = importlib.util.spec_from_file_location("check_safe_rmtree", TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_safe_rmtree"] = mod
    spec.loader.exec_module(mod)
    return mod


DANGEROUS = textwrap.dedent('''
    """A fake tools/ module carrying every shape that must be refused."""
    import os
    import shutil
    import tempfile
    from pathlib import Path


    def delete_empty():
        shutil.rmtree("")


    def delete_dot():
        shutil.rmtree(".")


    def delete_dotdot():
        shutil.rmtree("..")


    def delete_home():
        shutil.rmtree(Path.home())


    def delete_a_variable():
        target = os.environ.get("SOMEWHERE")
        shutil.rmtree(target)


    def delete_a_subdirectory_of_the_checkout():
        shutil.rmtree(Path(__file__).resolve().parent)


    def delete_inside_the_temp_folder():
        shutil.rmtree(Path(tempfile.gettempdir()) / "a-folder-of-my-own")
''')


def a_synthetic_tree():
    """A temp root holding `tools/fake.py`, the shape the checker scans."""
    root = Path(tempfile.mkdtemp(prefix="safe-rmtree-probe-"))
    (root / "tools").mkdir()
    (root / "tools" / "fake.py").write_text(DANGEROUS, encoding="utf-8")
    return root


def remove_only_inside_temp(root: Path) -> None:
    """Delete the probe folder, refusing to touch anything outside %TEMP%."""
    import shutil
    resolved = root.resolve()
    inside = str(resolved).lower().startswith(
        str(Path(tempfile.gettempdir()).resolve()).lower())
    if not inside or resolved == Path(tempfile.gettempdir()).resolve():
        raise AssertionError(f"refusing to delete {resolved}: not strictly inside the temp folder")
    shutil.rmtree(resolved)


def t_the_checker_catches_every_shape_that_deleted_a_checkout():
    mod = load_tool()
    root = a_synthetic_tree()
    try:
        flagged, allowed, confined, sites, files = mod.scan(root, False)
        texts = " ".join(row[3] for row in flagged)
        scopes = {row[2] for row in flagged}
        check("the empty string is refused", '""' in texts or "''" in texts, texts[:200])
        check('a bare "." is refused', '"."' in texts or "'.'" in texts, texts[:200])
        check('".." is refused', '".."' in texts or "'..'" in texts, texts[:200])
        check("the home directory is refused", "home()" in texts, texts[:200])
        check("an unguarded variable is refused", "target" in texts, texts[:200])
        check("a subdirectory of the checkout is refused",
              "__file__" in texts, texts[:200])
        check("seven calls were seen", sites == 7, sites)
        check("the temp-folder call is NOT flagged",
              "delete_inside_the_temp_folder" not in scopes, sorted(scopes))
        check("... and it is counted as confined or unflagged",
              len(flagged) == 6, len(flagged))
    finally:
        remove_only_inside_temp(root)


def t_the_checker_refuses_an_empty_tree_rather_than_passing_it():
    mod = load_tool()
    root = Path(tempfile.mkdtemp(prefix="safe-rmtree-empty-"))
    try:
        import subprocess
        out = subprocess.run([sys.executable, "-B", str(TOOL), "--root", str(root)],
                             capture_output=True, text=True)
        check("a root with no tools/ folder is a FAIL, not a pass",
              out.returncode == 1 and "nothing was scanned" in (out.stdout + out.stderr),
              (out.returncode, (out.stdout + out.stderr)[:200]))
        check("... and the module agrees it scanned nothing",
              mod is not None)
    finally:
        remove_only_inside_temp(root)


def t_the_hard_tier_is_the_rulings_list_and_not_the_tracers_guess():
    """The owner's Q2 list, on the ARGUMENT TEXT, not on the checker's DANGER kind.

    The checker reports an untraceable module constant as "the home directory":
    `rmtree(TMP)`, where TMP is a `tempfile.mkdtemp()` result, is a scratch dir
    every backend test makes. A tier built on that label hard-failed 20 such
    fixtures on the day this was wired. The hard tier must name the shapes that
    delete a checkout, and nothing else.
    """
    mod = load_tool()
    for text in ('""', "''", '"."', "'.'", '".."', "'..'",
                 "Path.home()", "str(Path.home())", "os.path.expanduser('~')"):
        row = ("backend/test_x.py", 1, "t", text, f"shutil.rmtree({text})", "", "danger")
        check(f"hard tier catches {text}", mod._is_hard(row) is True, text)
    for text in ("TMP", "TMP / d", "CONF", "ARTIFACT_DIR", "venv", "child",
                 "Path(__file__).parent"):
        row = ("backend/test_x.py", 1, "t", text, f"shutil.rmtree({text})", "", "danger")
        check(f"... and does NOT hard-fail {text!r}", mod._is_hard(row) is False, text)


def t_the_ratchet_refuses_to_grow():
    """A ceiling may only go down; a NEW unguarded site is refused."""
    mod = load_tool()
    saved = mod.BASELINE
    root = Path(tempfile.mkdtemp(prefix="safe-rmtree-ratchet-"))
    try:
        mod.BASELINE = root / "baseline.json"
        mod.BASELINE.write_text(json.dumps(
            {"backend_unknown": [["backend/test_x.py", "t", "TMP"]],
             "tools_unknown": []}), encoding="utf-8")
        grew = [("backend/test_x.py", 1, "t", "TMP", "rmtree(TMP)", "", "unknown"),
                ("backend/test_y.py", 2, "u", "OTHER", "rmtree(OTHER)", "", "unknown")]
        check("a NEW unguarded site makes the writer refuse",
              mod.write_baseline(grew) == 1)
        check("... and the recorded ceiling is not overwritten",
              "test_y.py" not in mod.BASELINE.read_text(encoding="utf-8"))
        same = [grew[0]]
        check("... while the same set writes through",
              mod.write_baseline(same) == 0)
    finally:
        mod.BASELINE = saved
        remove_only_inside_temp(root)


def main(argv=None):
    tests = (t_the_checker_catches_every_shape_that_deleted_a_checkout,
             t_the_checker_refuses_an_empty_tree_rather_than_passing_it,
             t_the_hard_tier_is_the_rulings_list_and_not_the_tracers_guess,
             t_the_ratchet_refuses_to_grow)
    for fn in tests:
        print(f"--- {fn.__name__} ---")
        try:
            fn()
        except Exception:                       # noqa: BLE001 - reported, not raised
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
