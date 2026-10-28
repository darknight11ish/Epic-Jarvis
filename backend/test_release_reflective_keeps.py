"""The release-dex guard is green, honest, and cannot pass without an APK.

    python3 backend/test_release_reflective_keeps.py

WHAT THIS IS. `tools/check_apk_reflective_keeps.py` is the check that reads a
release APK's own `classes*.dex` and fails when R8 has stripped a class or
constructor the app creates by NAME (the 2026-10-27 widget failure: every
WorkManager job died with "Could not create Input Merger" and all five
home-screen widgets sat on a spinner, while the unit tests and the debug build
were green). This suite is the proof that the check exists, runs, judges
correctly, and refuses to report success when it has nothing to look at.

WHAT IT PROVES, in temp folders only:

  1. `--self-test` exits 0, so the tool's own fabricated-inventory cases pass.
  2. The target table still names the four reflective entry points with their
     exact signatures. A table entry deleted by a future edit - which is how
     this guard would quietly stop guarding - fails here.
  3. A missing constructor and a missing class are both reported, with the
     class's Java name, the words "reflective instantiation hole" and
     "proguard-rules.pro", and exit 1.
  4. A concrete `*InputMerger` nobody listed is caught; an abstract one is not.
  5. Run with no APK, it exits 1 and says so. A check that reports success
     because it looked at nothing is the failure mode this project has paid
     for more than once.
  6. A "release" APK whose `classes.dex` is not a dex, and one with no dex at
     all, are ERRORS, not passes: a parser that cannot read the artifact must
     never conclude the artifact is fine. That is the direction that would let
     a real hole ship.
  7. A path that looks like the debug build is refused, because R8 does not
     run there and the check could never fail on it.

WHAT IT DELIBERATELY DOES NOT PROVE. There is no release APK in this
repository (a build artifact, ~32 MB), so the PARSER is not exercised here
against a real one. It is exercised every time the `Jarvis client` workflow
builds an APK, and by hand with the command in the tool's docstring, where the
same file also says how to see it fail. Its docstring records the measured
good/broken builds. This suite covers the judgement and the refusals, which is
the half that needs to hold when nobody has run a device in months.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOOL = REPO / "tools" / "check_apk_reflective_keeps.py"

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def run(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-B", str(TOOL), *args],
        cwd=str(cwd or REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def load_tool():
    spec = importlib.util.spec_from_file_location("reflective_keeps", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inventory(module, missing=(), methods=None):
    """Every target present, except what `missing` names."""
    classes = {}
    for target in module.TARGETS:
        if target.descriptor in missing:
            continue
        signature = (target.method, target.method_descriptor)
        if methods and target.descriptor in methods:
            signature = methods[target.descriptor]
        classes[target.descriptor] = module.ClassInfo(
            target.descriptor, 0x11, None, {signature}
        )
    return classes


def main() -> int:
    tool = run("--self-test")
    out = (tool.stdout or "") + (tool.stderr or "")
    check("the tool's own self-test passes", tool.returncode == 0, out[-900:])
    check("... and says the failure message names the class, the hole and the fix",
          "names the class, the hole and the fix" in out, out[-900:])

    module = load_tool()

    # The table is the guard. If a future edit deletes an entry, the check still
    # runs and still passes - it just stops guarding the thing that was deleted.
    expected = {
        "Landroidx/work/OverwritingInputMerger;": ("<init>", "()V"),
        "Landroidx/work/ArrayCreatingInputMerger;": ("<init>", "()V"),
        "Landroidx/glance/session/SessionWorker;":
            ("<init>", "(Landroid/content/Context;Landroidx/work/WorkerParameters;)V"),
        "Landroidx/work/impl/WorkDatabase_Impl;": ("<init>", "()V"),
    }
    table = {t.descriptor: (t.method, t.method_descriptor) for t in module.TARGETS}
    check("the table still holds every known reflective target, by exact signature",
          table == expected,
          f"missing: {sorted(set(expected) - set(table))}; "
          f"unexpected: {sorted(set(table) - set(expected))}")
    check("... and every entry says why it is there",
          all(t.why.strip() for t in module.TARGETS))

    good = inventory(module)
    check("a complete inventory passes", module.report(good, False) == 0)

    broken = inventory(
        module,
        missing=("Landroidx/work/impl/WorkDatabase_Impl;",),
        methods={"Landroidx/work/OverwritingInputMerger;": ("a", "()V")},
    )
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = module.report(broken, False)
    message = buffer.getvalue()
    check("a stripped InputMerger constructor and a missing Room class both fail",
          code == 1, message[-900:])
    check("... both are named",
          "androidx.work.OverwritingInputMerger" in message
          and "androidx.work.impl.WorkDatabase_Impl" in message, message[-900:])
    check('... and the report says "reflective instantiation hole ... proguard-rules.pro"',
          "reflective instantiation hole" in message and "proguard-rules.pro" in message,
          message[-900:])

    concrete = inventory(module)
    concrete["Lcom/example/UnlistedInputMerger;"] = module.ClassInfo(
        "Lcom/example/UnlistedInputMerger;", 0x11, None, {("<init>", "(I)V")}
    )
    check("a concrete *InputMerger nobody listed is caught",
          len(module.problems(concrete)) == 1)
    abstract = inventory(module)
    abstract["Landroidx/work/InputMerger;"] = module.ClassInfo(
        "Landroidx/work/InputMerger;", 0x0401, None, set()
    )
    check("an abstract *InputMerger is not required to have a constructor",
          module.problems(abstract) == [])

    empty = module.problems({})
    check("an empty inventory fails for every target, never passes",
          len(empty) == len(module.TARGETS))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # No APK at all: the check must not call that a pass.
        nothing = run(cwd=tmp)
        out = (nothing.stdout or "") + (nothing.stderr or "")
        check("with no APK it exits 1 and says nothing was checked",
              nothing.returncode == 1 and "nothing was checked" in out, out[-500:])

        # A file whose dex cannot be parsed must be an error, not a pass.
        junk = tmp / "app-release.apk"
        with zipfile.ZipFile(junk, "w") as archive:
            archive.writestr("classes.dex", b"this is not a dex file")
        bad_dex = run(str(junk))
        out = (bad_dex.stdout or "") + (bad_dex.stderr or "")
        check("an unparsable classes.dex is an error, not a pass",
              bad_dex.returncode == 1 and "not a dex file" in out, out[-500:])

        # An APK with no dex at all is the same shape of nothing.
        nodex = tmp / "nodex-release.apk"
        with zipfile.ZipFile(nodex, "w") as archive:
            archive.writestr("AndroidManifest.xml", b"")
        no_dex = run(str(nodex))
        out = (no_dex.stdout or "") + (no_dex.stderr or "")
        check("an APK carrying no classes*.dex is an error, not a pass",
              no_dex.returncode == 1 and "no classes*.dex" in out, out[-500:])

        # R8 does not run on a debug build, so a pass on one would prove nothing.
        debug = tmp / "app-debug.apk"
        debug.write_bytes(b"not even a zip")
        on_debug = run(str(debug))
        out = (on_debug.stdout or "") + (on_debug.stderr or "")
        check("a debug-looking APK is refused rather than passed",
              on_debug.returncode == 1 and "DEBUG" in out, out[-500:])

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
