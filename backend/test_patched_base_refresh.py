"""test_patched_base_refresh.py - the refresh tool's own contract, proved hermetically.

    python3 test_patched_base_refresh.py

WHY

`tools/refresh_patched_base.py` is the clean path for the 2026-11-19 review
ruling: the two hand-written shims on the live `jarvis_models.py` (appended
2026-11-18 and 2026-11-19) are TEMPORARY DEBT TO CLEAR, NO THIRD SHIM MAY BE
ADDED, and the deploy's cross-file guard (#1400) stays absolute. The tool
writes a patched-base file - the one class of file `reconcile_live_backend.py`
never carries - so every failure path matters more than the happy one:

  1. the LINEAGE PROOF: a target is refreshable only when its bytes are exactly
     an older published base (or one plus replayed patch hunks, or one plus a
     gap-repair suffix of module-level definitions). A target carrying an edit
     that no published base and no `$PATCHES` entry explains is REFUSED and
     nothing is written - that is the fixture with a changed line and the
     fixture with `def mystery()` below.
  2. the NEW FILE is the current published base (plus any patch the target
     carries that the base does not yet), and the refresh may ADD a name but
     never LOSE one. A patch the target carries that the current base neither
     carries nor can take is refused rather than silently dropped.
  3. a patch rewritten after a base version was published is handled by
     `backend/patch-history`'s recorded older versions: the old shape being in
     the target is "baked in", not an unexplained edit. `gpu-offload.patch` on
     the owner's live copy is the real case, modelled here.
  4. the APPENDED BLOCK is the hand-shim shape: its definitions are replaced by
     the published base's own, and ONLY when every name it binds is absent from
     the published bytes (a gap-fill, not a redefinition) and bound by the
     current base. A top-level call, a redefinition, a name the base lacks, a
     `from ... import *` or invalid Python in the suffix is REFUSED.
  5. the SHIMS THEMSELVES: a fixture built from the REAL `jarvis-backend/
     jarvis_models.py` history - its oldest published version, plus appended
     definitions for the three names the live shims provide - refreshes to the
     repository's current base, so the two hand shims are REPLACED. Needs the
     full git history (CI's required backend job checks it out); a shallow
     clone says SKIP out loud and is not counted as a pass.
  6. the CROSS-FILE GUARD IS NOT WEAKENED: the guard's own functions are run on
     a folder holding the refreshed base - it passes - and taking
     `probe_refusal` back out makes it refuse, naming the function. Its refusal
     names this tool and the no-third-shim ruling.
  7. the WRITE: one backup, temp compile, swap; a failed compile restores the
     original byte for byte; the written file is re-planned and must be current.
  8. the CLI on a REAL temporary git repository: check exits 1 with a refresh
     available, --apply exits 0 and writes the base's bytes, a second check
     exits 0 and --json parses, an unknown-edit target exits 2 with no write
     and no backup, and `--apply` without `--file` is refused.

Nothing here touches the owner's live folder, imports a live module, opens a
socket, or writes outside a temporary directory.
"""
import ast
import contextlib
import difflib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOOL = REPO / "tools" / "refresh_patched_base.py"
DEPLOY = REPO / "tools" / "reconcile_live_backend.py"
FILE = "jarvis_models.py"

PASSED, FAILED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    """A skip is SAID and is never counted as a pass (the BLOCKED rule)."""
    SKIPPED.append(name)
    print(f"skip  {name}\n        {why}")


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module          # dataclasses looks the module up by name
    spec.loader.exec_module(module)
    return module


def tmpdir():
    return Path(tempfile.mkdtemp(prefix="test-refresh-base-"))


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def quiet(fn, *args):
    """(return code, stdout) - run a function that prints, capturing its words."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn(*args)
    return code, buf.getvalue()


def raises(exc_type, fn, words=""):
    try:
        fn()
    except exc_type as exc:
        return not words or words in str(exc)
    return False


# ---------------------------------------------------------------------------
#   Fixture text: a small module with two patch insertion points
# ---------------------------------------------------------------------------

V1 = '''"""Fixture module for the refresh tool's suite."""


def kept() -> str:
    """A function both published versions bind."""
    return "kept"


def middle() -> str:
    """The patch inserts before this function."""
    return "middle"


def tail() -> str:
    """The last function the old base has."""
    return "tail"


def ollama_url_on_this_pc(*args, **kwargs):
    """Declared cross-file name (fixture stub)."""
    return "http://127.0.0.1:11434"


def discover(*args, **kwargs):
    """Declared cross-file name (fixture stub)."""
    return []


def probe_refusal(*args, **kwargs):
    """Declared cross-file name (fixture stub)."""
    return ""


def rollback(*args, **kwargs):
    """Declared cross-file name (fixture stub)."""
    return None


def safe_ref(*args, **kwargs):
    """Declared cross-file name (fixture stub)."""
    return ""


def switch_to(*args, **kwargs):
    """Declared cross-file name (fixture stub)."""
    return None
'''

ADDED_BLOCK = ('def added_by_patch() -> str:\n'
               '    """The fixture patch\'s first function."""\n'
               '    return "from the patch"\n\n\n')
ALSO_BLOCK = ('def also_by_patch() -> str:\n'
              '    """The fixture patch\'s second function."""\n'
              '    return "also from the patch"\n\n\n')


def insert_before(text: str, anchor: str, block: str) -> str:
    assert text.count(anchor) == 1, anchor
    return text.replace(anchor, block + anchor, 1)


PATCH_TARGET = insert_before(
    insert_before(V1, "def middle", ADDED_BLOCK),
    "def ollama_url_on_this_pc", ALSO_BLOCK)
V2 = PATCH_TARGET + ('\n\ndef fixed_in_base() -> str:\n'
                     '    """A name the newer published base added."""\n'
                     '    return "newer"\n')
V2_NO_PATCH = V1 + ('\n\ndef fixed_in_base() -> str:\n'
                    '    """A name the newer published base added."""\n'
                    '    return "newer"\n')

OLD_ADDED_BLOCK = ('def added_by_patch() -> str:\n'
                   '    """The fixture patch\'s first function (old shape)."""\n'
                   '    return "from the OLD patch"\n\n\n')
OLD_ALSO_BLOCK = ('def also_by_patch() -> str:\n'
                  '    """The fixture patch\'s second function (old shape)."""\n'
                  '    return "also from the OLD patch"\n\n\n')
OLD_SHAPE = insert_before(
    insert_before(V1, "def middle", OLD_ADDED_BLOCK),
    "def ollama_url_on_this_pc", OLD_ALSO_BLOCK)


def make_patch(path: str, before: str, after: str) -> str:
    """A real unified diff `before` -> `after`, with a/ + b/ headers."""
    diff = difflib.unified_diff(before.splitlines(keepends=True),
                                after.splitlines(keepends=True),
                                fromfile=f"a/{path}", tofile=f"b/{path}",
                                n=3, lineterm="\n")
    return "".join(diff)


#: The patch in `$PATCHES`: its two insertions are the current (new) shape.
FIX_PATCH = make_patch(FILE, V1, PATCH_TARGET)
#: An earlier recorded version of the same patch (the old bodies).
OLD_FIX_PATCH = make_patch(FILE, V1, OLD_SHAPE)


def versions_for(*texts):
    """(commit, date, subject, text) published-base versions, newest first."""
    out = []
    for index, text in enumerate(texts):
        out.append((f"c{len(texts) - index:02d}" + "0" * 36,
                    "2026-11-01", f"base version {len(texts) - index}", text))
    return out


def plan(mod, target, versions, patches=(), history=None, base_now=None,
         required=()):
    """Call the tool's pure planning function with tuples, not git."""
    return mod.plan_refresh(
        FILE, target,
        [mod.BaseVersion(commit, date, subject, text)
         for commit, date, subject, text in versions],
        [mod.PatchText(name, text) for name, text in patches],
        history or {},
        base_now if base_now is not None else versions[0][3],
        required_names=required)


# ---------------------------------------------------------------------------
# 1. the deploy tool's contract is IMPORTED, not copied
# ---------------------------------------------------------------------------

def t_the_five_patched_files_come_from_the_deploy_tool():
    mod = load_module(TOOL, "refresh_base_tool")
    check("the tool reads the deploy tool beside it", mod.DEPLOY_TOOL == DEPLOY,
          mod.DEPLOY_TOOL)
    check("the five patched-base files are the deploy's own list, in order",
          tuple(mod.PATCHED_FILES) == (
              "jarvis_hud.py", "jarvis_gate.py", "jarvis_extract.py",
              "jarvis_models.py", "jarvis_skills.py"),
          mod.PATCHED_FILES)
    check("the tool reads module-level names with the deploy's own reader",
          "module_level_names" in dir(mod.R))
    check("the tool refuses a file the deploy already carries whole",
          raises(mod.Refused, lambda: mod.plan_refresh(
              "jarvis_router.py", "", [], [], {}, V1),
              "not one of the five"))


# ---------------------------------------------------------------------------
# 2. patch replay: applied, applicable, half-applied, ambiguous
# ---------------------------------------------------------------------------

def t_patch_replay_is_exact_and_never_guesses():
    mod = load_module(TOOL, "refresh_base_tool")
    patch = mod.PatchText("fix.patch", FIX_PATCH)
    check("the fixture patch really has two hunks (the two insertions)",
          len(mod.R.patch_hunks(FIX_PATCH, FILE)) == 2,
          len(mod.R.patch_hunks(FIX_PATCH, FILE)))
    state, why = mod.patch_state(V1, patch, FILE)
    check("a patch whose pre-images are present exactly once is APPLICABLE",
          state == mod.APPLICABLE, (state, why))
    check("... and replaying it gives the patch's own post-image",
          mod.replay_patch(V1, patch, FILE) == PATCH_TARGET)
    state, why = mod.patch_state(PATCH_TARGET, patch, FILE)
    check("the same patch on its own post-image is APPLIED",
          state == mod.APPLIED, (state, why))
    half = insert_before(V1, "def middle", ADDED_BLOCK)
    state, why = mod.patch_state(half, patch, FILE)
    check("a HALF-applied patch is UNEXPLAINED, never 'apply the rest'",
          state == mod.UNEXPLAINED and "half applied" in why, (state, why))
    doubled = V1 + "\n\n" + V1
    state, why = mod.patch_state(doubled, patch, FILE)
    check("an ambiguous pre-image (present twice) is UNEXPLAINED",
          state == mod.UNEXPLAINED, (state, why))
    check("... and replaying onto it is REFUSED, so no block is guessed",
          raises(mod.Refused, lambda: mod.replay_patch(doubled, patch, FILE),
                 "expected exactly 1"))


# ---------------------------------------------------------------------------
# 3. the lineage proof: older base, + a patch, -> the newer file
# ---------------------------------------------------------------------------

def t_an_older_base_plus_a_patch_refreshes_to_the_newer_base():
    mod = load_module(TOOL, "refresh_base_tool")
    # the current base already carries the patch's change; target = old base + patch
    result = plan(mod, PATCH_TARGET, versions_for(V2, V1),
                  patches=[("fix.patch", FIX_PATCH)], base_now=V2)
    check("older base + a replayed patch is PROVED refreshable",
          result.status == mod.REFRESHABLE, result.why)
    check("... the lineage names the older base commit and its date",
          "c01" in result.lineage and "2026-11-01" in result.lineage,
          result.lineage)
    check("... the new file is the CURRENT published base",
          result.new_text == V2, result.new_text[:80])
    check("... the patch is reported as already in the current base",
          any(name == "fix.patch" and "current base" in what
              for name, what in result.patches), result.patches)
    check("... and the refresh adds names, losing none",
          result.names_lost == () and "fixed_in_base" in result.names_added,
          (result.names_lost, result.names_added))
    check("... the report says a dry run wrote nothing",
          mod.NOTHING_WRITTEN not in (result.why or ""), result.why)


def t_a_patch_the_current_base_does_not_carry_is_replayed_onto_it():
    mod = load_module(TOOL, "refresh_base_tool")
    result = plan(mod, PATCH_TARGET, versions_for(V2_NO_PATCH, V1),
                  patches=[("fix.patch", FIX_PATCH)], base_now=V2_NO_PATCH)
    check("an older base + a patch refreshes even when the base lacks the "
          "patch: the patch is replayed ONTO the base",
          result.status == mod.REFRESHABLE
          and "def added_by_patch" in result.new_text
          and "def also_by_patch" in result.new_text
          and "def fixed_in_base" in result.new_text,
          (result.status, result.why))
    check("... and the report says the patch was replayed onto the current base",
          any(name == "fix.patch" and "replayed onto the current base" in what
              for name, what in result.patches), result.patches)


def t_a_target_that_is_already_the_current_base_is_current():
    mod = load_module(TOOL, "refresh_base_tool")
    result = plan(mod, V2, versions_for(V2, V1), base_now=V2)
    check("a target equal to the current base is CURRENT (nothing to do)",
          result.status == mod.CURRENT, result.why)
    check("... and its report says byte for byte",
          "byte for byte" in result.lineage, result.lineage)


def t_an_unknown_change_is_refused_and_writes_nothing():
    mod = load_module(TOOL, "refresh_base_tool")
    changed = V1.replace('    return "kept"',
                         '    return "edited in the live file"')
    result = plan(mod, changed, versions_for(V2, V1), base_now=V2)
    check("a target with a changed line no published base has is REFUSED",
          result.status == mod.REFUSED, result.why)
    check("... the refusal says it is no published base plus its patches",
          "not any published base" in result.why
          and "DELTA_TABLE" in result.why, result.why)
    check("... and it says nothing was written", mod.NOTHING_WRITTEN in result.why,
          result.why)
    check("... the refused plan carries no new bytes",
          result.new_text == "", repr(result.new_text))


def t_an_appended_unknown_name_is_refused():
    mod = load_module(TOOL, "refresh_base_tool")
    unknown = PATCH_TARGET + ('\n\ndef mystery() -> str:\n'
                              '    """An edit no published base explains."""\n'
                              '    return "?"\n')
    result = plan(mod, unknown, versions_for(V2, V1),
                  patches=[("fix.patch", FIX_PATCH)], base_now=V2)
    check("an appended name the current base does not bind is REFUSED - not "
          "silently dropped",
          result.status == mod.REFUSED and "mystery" in result.why
          and "REMOVE" in result.why, result.why)


def t_an_unprovable_namespace_is_refused():
    mod = load_module(TOOL, "refresh_base_tool")
    dynamic = V1 + '\nexec("x = 1")\n'
    check("a target version whose namespace is built dynamically is REFUSED, "
          "not guessed at",
          raises(mod.Refused, lambda: plan(
              mod, dynamic, versions_for(V2, dynamic), base_now=V2),
              "cannot be proved static"))


# ---------------------------------------------------------------------------
# 4. the new file may add a name but never lose one
# ---------------------------------------------------------------------------

def t_a_refresh_that_would_lose_a_name_is_refused():
    mod = load_module(TOOL, "refresh_base_tool")
    lost = ('def kept() -> str:\n'
            '    """A function both published versions bind."""\n'
            '    return "kept"\n\n\n')
    newer_without_kept = V2.replace(lost, "")
    result = plan(mod, V1, versions_for(newer_without_kept, V1),
                  base_now=newer_without_kept)
    check("a current base that dropped a name the target binds is REFUSED",
          result.status == mod.REFUSED and "'kept'" in result.why, result.why)
    check("... the plan records the name it would have lost",
          result.names_lost == ("kept",), result.names_lost)


def t_a_patch_the_base_neither_carries_nor_can_take_is_refused():
    mod = load_module(TOOL, "refresh_base_tool")
    # the current base moved the insertion point's context, so the patch cannot
    # be replayed onto it and is not in it: a refresh would drop it.
    broken = V2_NO_PATCH.replace('def middle() -> str:',
                                 'def middle(name: str = "") -> str:')
    result = plan(mod, PATCH_TARGET, versions_for(V1),
                  patches=[("fix.patch", FIX_PATCH)], base_now=broken)
    check("a patch the target carries that the current base cannot take is "
          "REFUSED rather than silently dropped",
          result.status == mod.REFUSED and "DROP" in result.why, result.why)


def t_a_declared_cross_file_requirement_must_be_bound():
    mod = load_module(TOOL, "refresh_base_tool")
    result = plan(mod, V1, versions_for(V2, V1), base_now=V2,
                  required=("needed_by_shipped",))
    check("a refresh that would not bind a declared cross-file name is REFUSED",
          result.status == mod.REFUSED
          and "needed_by_shipped" in result.why
          and "guard it exists for" in result.why, result.why)


# ---------------------------------------------------------------------------
# 5. a patch rewritten after the base version was published: patch-history
# ---------------------------------------------------------------------------

def t_a_recorded_older_patch_shape_baked_into_the_base_is_not_an_edit():
    mod = load_module(TOOL, "refresh_base_tool")
    result = plan(mod, OLD_SHAPE, versions_for(V2, OLD_SHAPE),
                  patches=[("fix.patch", FIX_PATCH)],
                  history={"fix.patch": [mod.PatchText("fix.patch",
                                                       OLD_FIX_PATCH)]},
                  base_now=V2)
    check("a published base carrying a patch's OLDER recorded shape proves as "
          "baked in, not as an unknown edit",
          result.status == mod.REFRESHABLE, result.why)
    check("... the report says the target carries the older shape",
          any("older shape" in what for _name, what in result.patches),
          result.patches)
    check("... and the new file is the current base, which carries the newer "
          "shape", result.new_text == V2)


# ---------------------------------------------------------------------------
# 6. the appended block: the two hand shims are REPLACED
# ---------------------------------------------------------------------------

SHIM_SUFFIX = ('''# ---------------------------------------------------------------------------
# DEPLOY GAP REPAIR (fixture). Definitions the published base now provides.
def gap_one(raw=None):
    """A gap-filling definition."""
    return raw


def gap_two(model) -> bool:
    """A second gap-filling definition."""
    return bool(model)
# ---------------------------------------------------------------------------
''')

V1_WITH_SHIMS = V1 + "\n" + SHIM_SUFFIX
NEWER_WITH_GAPS = V2 + ('\n\ndef gap_one(raw=None):\n'
                        '    """The published base\'s own definition."""\n'
                        '    return raw\n\n\n'
                        'def gap_two(model) -> bool:\n'
                        '    """The published base\'s own definition."""\n'
                        '    return bool(model)\n')


def t_an_appended_gap_repair_is_replaced_by_the_base_definition():
    mod = load_module(TOOL, "refresh_base_tool")
    result = plan(mod, V1_WITH_SHIMS, versions_for(NEWER_WITH_GAPS, V1),
                  base_now=NEWER_WITH_GAPS)
    check("a target that is an older base plus an appended gap repair is "
          "REFRESHABLE", result.status == mod.REFRESHABLE, result.why)
    check("... the appended definitions are named, and REPLACED",
          result.appended == ({"name": "gap_one", "kind": "FunctionDef"},
                              {"name": "gap_two", "kind": "FunctionDef"}),
          result.appended)
    check("... the new file is the base, so the appended block is dropped",
          result.new_text == NEWER_WITH_GAPS
          and 'gap_one(raw=None):\n    """A gap' not in result.new_text,
          result.new_text[-200:])
    check("... the lineage says they are replaced by the base's own",
          "replaced by the published base's own" in result.lineage,
          result.lineage)


def t_an_appended_redefinition_or_unclosed_name_is_refused():
    mod = load_module(TOOL, "refresh_base_tool")
    redefines = V1 + ("\n\n"
                      "def kept() -> str:\n"
                      "    \"\"\"An appended block that REDEFINES a base name.\"\"\"\n"
                      "    return \"shim\"\n")
    result = plan(mod, redefines, versions_for(V2, V1), base_now=V2)
    check("an appended block that redefines a published name is REFUSED",
          result.status == mod.REFUSED and "'kept'" in result.why, result.why)
    unclosed = V1 + ("\n\n"
                     "def owner_only_fix() -> str:\n"
                     "    \"\"\"A name the current base does not bind.\"\"\"\n"
                     "    return \"fix\"\n")
    result = plan(mod, unclosed, versions_for(V2, V1), base_now=V2)
    check("an appended name the current base does not bind is REFUSED - a "
          "refresh may not REMOVE a fix",
          result.status == mod.REFUSED and "owner_only_fix" in result.why
          and "REMOVE" in result.why, result.why)


def t_an_override_after_a_newer_published_version_is_never_accepted():
    """A suffix is a gap repair only relative to the TRUE ancestor.

    Here a newer published version's bytes are a prefix of the target and the
    block after them REDEFINES a name that newer version binds. The tool refuses
    at that newer prefix - it does not fall back to an older published version
    that could accept the same bytes as a "gap repair" and silently drop the
    override. That fallback is the mistake this check prevents.
    """
    mod = load_module(TOOL, "refresh_base_tool")
    newer = V1 + ('\n\ndef added_in_newer() -> str:\n'
                  '    """A name the newer published base added."""\n'
                  '    return "from the newer base"\n')
    override = ('\n\ndef added_in_newer() -> str:\n'
                '    """An appended block that overrides the newer base name."""\n'
                '    return "override"\n')
    live = newer + override
    result = plan(mod, live, versions_for(newer, V1), base_now=newer)
    check("an appended block that overrides a name the NEWER published "
          "version binds is REFUSED, not re-read against an older version",
          result.status == mod.REFUSED, result.why)
    check("... the refusal says it redefines a name the published bytes bind",
          "redefine" in result.why, result.why)
    check("... and nothing is written for it", result.new_text == "")


def t_an_appended_block_that_runs_code_is_refused():
    mod = load_module(TOOL, "refresh_base_tool")
    side_effect = V1 + ('\n\ndef gap_one(raw=None):\n    return raw\n\n\n'
                        'gap_one()\n')
    check("an appended block with a top-level CALL is REFUSED - dropping it "
          "could drop an effect",
          raises(mod.Refused, lambda: plan(mod, side_effect,
                                           versions_for(V2, V1), base_now=V2),
                 "not only definitions"))
    star = V1 + '\n\nfrom somewhere import *\n'
    check("an appended 'from ... import *' is REFUSED - it binds names the "
          "tool cannot enumerate",
          raises(mod.Refused, lambda: plan(mod, star, versions_for(V2, V1),
                                           base_now=V2), "import *"))


# ---------------------------------------------------------------------------
# 7. the real hand shims: the published base's own history is the fixture
# ---------------------------------------------------------------------------

def _git(*args, cwd=None):
    proc = subprocess.run(["git", *args], cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, ["git", *args],
                                            proc.stdout, proc.stderr)
    return proc.stdout


def _pick_ref() -> Optional[str]:
    """`origin/main` when this clone has it, else HEAD; None without history."""
    if not shutil.which("git"):
        return None
    for ref in ("origin/main", "HEAD"):
        try:
            _git("rev-parse", "--verify", f"{ref}^{{commit}}", cwd=REPO)
            _git("log", "-1", "--format=%H", ref, "--",
                 "jarvis-backend/jarvis_models.py", cwd=REPO)
            return ref
        except (subprocess.CalledProcessError, OSError):
            continue
    return None


def t_the_two_real_shims_would_be_replaced_proved_on_the_base_history():
    """The ruling's own names, on the REAL published base's own history.

    Build the target the owner's install has: the OLDEST published
    `jarvis-backend/jarvis_models.py` (the version the live copy's bytes date
    from) plus appended definitions for the three names the live hand shims
    provide. The tool must refresh it to the repository's current base and
    report exactly those three definitions as replaced. Needs the full git
    history; a shallow clone says SKIP out loud, never a pass.
    """
    mod = load_module(TOOL, "refresh_base_tool")
    ref = _pick_ref()
    if ref is None:
        skip("the real published-base shim fixture",
             "no git history for jarvis-backend/jarvis_models.py is available "
             "(a shallow clone or no git), so the lineage cannot be built")
        return
    try:
        history = _git("log", "--format=%H", ref, "--",
                       "jarvis-backend/jarvis_models.py", cwd=REPO).split()
        if len(history) < 2:
            skip("the real published-base shim fixture",
                 f"only {len(history)} published version(s) of "
                 f"jarvis-backend/jarvis_models.py in this clone")
            return
        oldest = _git("show", f"{history[-1]}:jarvis-backend/"
                              f"jarvis_models.py", cwd=REPO)
        current = (REPO / "jarvis-backend" / "jarvis_models.py").read_text(
            encoding="utf-8")
    except (OSError, subprocess.CalledProcessError) as exc:
        skip("the real published-base shim fixture", f"git could not read it ({exc})")
        return
    names = ("ollama_url_on_this_pc", "is_pooled_model", "probe_refusal")
    oldest_names, _why = mod.R.module_level_names(oldest)
    current_names, _why = mod.R.module_level_names(current)
    absent_from_old = [n for n in names if n not in oldest_names]
    present_in_new = [n for n in names if n in current_names]
    check("the three names the live hand shims provide are all in the current "
          "published base", present_in_new == list(names), present_in_new)
    check("... and none of them is in the oldest published version (the "
          "version the live copy's bytes date from)",
          absent_from_old == list(names), absent_from_old)
    suffix = ("\n# ---------------------------------------------------------------------------\n"
              "# DEPLOY GAP REPAIR (fixture): the hand shims, as functions.\n")
    for name in names:
        suffix += (f"def {name}(*args, **kwargs):\n"
                   f"    \"\"\"The hand shim the fixture replaces.\"\"\"\n"
                   f"    return None\n\n\n")
    target = oldest + suffix
    result = plan(mod, target, versions_for(current, oldest), base_now=current)
    check("the REAL old base plus the three shim definitions is PROVED "
          "refreshable", result.status == mod.REFRESHABLE, result.why)
    check("... and the refresh REPLACES exactly the three hand shims",
          tuple(item["name"] for item in result.appended) == names,
          result.appended)
    check("... the new file is the repository's current published base",
          result.new_text == current, len(result.new_text))
    check("... so after the refresh the file binds every name the deploy's "
          "cross-file table declares for jarvis_models.py",
          all(name in mod.namespace(result.new_text, FILE)
              for name in mod.declared_requirements(FILE)),
          mod.declared_requirements(FILE))


# ---------------------------------------------------------------------------
# 8. the deploy's cross-file guard: passes after the refresh, still refuses a
#    still-missing name, and its refusal names the clean path
# ---------------------------------------------------------------------------

def t_the_cross_file_guard_passes_after_the_refresh_and_still_refuses():
    mod = load_module(TOOL, "refresh_base_tool")
    R = mod.R
    root = tmpdir()
    try:
        target = root / "target"
        target.mkdir()
        # A folder holding the refreshed base (the repository's current
        # jarvis_models.py) is exactly what the refresh produces.
        for name in ("jarvis_models.py", "jarvis_gate.py"):
            shutil.copy2(REPO / "jarvis-backend" / name, target / name)
        needs, _notes = R.cross_file_needs([])
        gaps, unproven = R.cross_file_gaps(target, needs)
        check("the deploy's cross-file guard PASSES on a folder whose "
              "jarvis_models.py is the refreshed base",
              gaps == [] and unproven == [], (gaps, unproven))
        # take probe_refusal back out of the refreshed file: the guard must
        # still refuse, naming the function - the guard is NOT weakened.
        missing = root / "missing"
        shutil.copytree(target, missing)
        text = (missing / "jarvis_models.py").read_text(encoding="utf-8")
        node = next(item for item in ast.parse(text).body
                    if isinstance(item, ast.FunctionDef)
                    and item.name == "probe_refusal")
        lines = text.splitlines(keepends=True)
        del lines[node.lineno - 1:(node.end_lineno or node.lineno)]
        (missing / "jarvis_models.py").write_text("".join(lines),
                                                  encoding="utf-8")
        gaps, unproven = R.cross_file_gaps(missing, needs)
        names = {(gap.file, gap.name) for gap in gaps}
        check("... and it STILL REFUSES when probe_refusal is taken back out - "
              "the guard is not weakened",
              ("jarvis_models.py", "probe_refusal") in names
              and unproven == [], (gaps, unproven))
        words = "\n".join(R.cross_file_refusal_lines(missing, gaps, unproven))
        check("... the refusal names this refresh tool as the clean path",
              "refresh_patched_base.py --backend-path" in words, words)
        check("... and it quotes the ruling: no third shim, the two are debt "
              "to clear",
              "no third" in words and "temporary debt to clear" in words
              and "review ruling" in words, words)
        check("... the deploy still says it never carries a patched base file",
              "never" in words and "patched base file" in words, words)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# 9. the write: one backup, compile before swap, restore on failure
# ---------------------------------------------------------------------------

def t_apply_writes_one_backup_and_a_second_plan_is_current():
    mod = load_module(TOOL, "refresh_base_tool")
    root = tmpdir()
    try:
        live = root / "live"
        live.mkdir()
        write(live / FILE, V1_WITH_SHIMS)
        before = (live / FILE).read_bytes()
        result = plan(mod, V1_WITH_SHIMS,
                      versions_for(NEWER_WITH_GAPS, V1), base_now=NEWER_WITH_GAPS)
        check("the fixture plans as refreshable before the write",
              result.status == mod.REFRESHABLE, result.why)
        backup = mod.apply_refresh(live, result, stamp="suite")
        check("the write keeps ONE backup beside the file",
              backup.name == f"{FILE}.before-refresh-suite"
              and backup.read_bytes() == before, backup)
        check("... and the file is the proved new bytes",
              (live / FILE).read_bytes() == result.new_text.encode("utf-8"))
        again = plan(mod, (live / FILE).read_text(encoding="utf-8"),
                     versions_for(NEWER_WITH_GAPS, V1), base_now=NEWER_WITH_GAPS)
        check("... a second check reads CURRENT", again.status == mod.CURRENT,
              again.why)
        check("... and applying CURRENT is refused, so it cannot write twice",
              raises(mod.Refused, lambda: mod.apply_refresh(live, again),
                     "nothing to apply"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_broken_refresh_is_rolled_back_and_the_original_kept():
    mod = load_module(TOOL, "refresh_base_tool")
    root = tmpdir()
    try:
        live = root / "live"
        live.mkdir()
        write(live / FILE, V1)
        before = (live / FILE).read_bytes()
        broken = V1 + "\n\ndef broken():\n    return 1\n\n\nreturn 2\n"
        result = mod.RefreshPlan(file=FILE, status=mod.REFRESHABLE,
                                 new_text=broken,
                                 new_sha256=mod._sha256(broken))
        check("a ready-to-write plan with a non-compiling body is refused on "
              "apply",
              raises(mod.Refused, lambda: mod.apply_refresh(
                  live, result, stamp="suite"), "did not compile"))
        check("... the original file is restored byte for byte",
              (live / FILE).read_bytes() == before)
        check("... and the backup of the pre-write bytes is kept",
              (live / f"{FILE}.before-refresh-suite").read_bytes() == before)
        check("... no temporary file is left in the folder",
              not list(live.glob("*.refresh-tmp")))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_refresh_whose_result_does_not_compile_is_refused_before_any_write():
    mod = load_module(TOOL, "refresh_base_tool")
    invalid = V1 + "\n\nreturn 3\n"          # parses, does not compile
    result = plan(mod, V1, versions_for(invalid, V1), base_now=invalid)
    check("a current base that does not compile is REFUSED in the planning "
          "step, before any write folder is touched",
          result.status == mod.REFUSED and "does not compile" in result.why,
          result.why)


# ---------------------------------------------------------------------------
# 10. the CLI on a real temporary git repository
# ---------------------------------------------------------------------------

def _fixture_repo(root: Path) -> Path:
    """A real git repository: a base file's history and one patch in $PATCHES.

    Three commits rewrite `jarvis-backend/jarvis_models.py` oldest-first, so
    the base's own history is the lineage the tool must prove against.
    """
    repo = root / "repo"
    write(repo / "scripts" / "apply-patches.ps1",
          "# fixture patch stack\n$PATCHES = @(\n    \"fix.patch\"\n)\n\n"
          "$SHIPPED = @(\n    \"jarvis_router.py\"\n)\n")
    write(repo / "backend" / "fix.patch", FIX_PATCH)
    write(repo / "jarvis-backend" / FILE, V1)
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "suite@example.invalid", cwd=repo)
    _git("config", "user.name", "refresh suite", cwd=repo)
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "fixture: the old published base", cwd=repo)
    for index, text in enumerate((PATCH_TARGET, V2), 1):
        write(repo / "jarvis-backend" / FILE, text)
        _git("add", "-A", cwd=repo)
        _git("commit", "-q", "-m",
             f"fixture: published base version {index}", cwd=repo)
    return repo


def _cli(mod, *args):
    return quiet(mod.main, list(args))


def t_the_cli_refreshes_on_a_real_temporary_git_repository():
    mod = load_module(TOOL, "refresh_base_tool")
    if not shutil.which("git"):
        skip("the CLI fixture", "git is not installed")
        return
    root = tmpdir()
    try:
        repo = _fixture_repo(root)
        live = root / "live"
        live.mkdir()
        write(live / FILE, PATCH_TARGET)
        base_args = ["--backend-path", str(live), "--repo", str(repo),
                     "--ref", "HEAD", "--file", FILE]
        code, out = _cli(mod, *base_args)
        check("check mode on a drifted fixture exits 1 - a refresh is available",
              code == 1, (code, out))
        check("... it says the dry run wrote nothing and names the file ready",
              "dry run wrote NOTHING" in out and "ready" in out, out)
        check("... and it proves the lineage against the fixture's older base",
              "PROVED" in out and f"the target is jarvis-backend/{FILE} at" in out,
              out)
        check("... the file was NOT touched by the check",
              (live / FILE).read_text(encoding="utf-8") == PATCH_TARGET)
        code, out = _cli(mod, *base_args, "--apply")
        check("--apply exits 0 and reports the write", code == 0, (code, out))
        check("... the live file is now the newer published base byte for byte",
              (live / FILE).read_text(encoding="utf-8") == V2,
              (live / FILE).read_text(encoding="utf-8")[:120])
        backups = list(live.glob(f"{FILE}.before-refresh-*"))
        check("... with one backup holding the pre-refresh bytes",
              len(backups) == 1
              and backups[0].read_text(encoding="utf-8") == PATCH_TARGET,
              backups)
        code, out = _cli(mod, *base_args)
        check("... a second check exits 0 - the folder is current",
              code == 0 and "0 refreshable" in out, (code, out))
        code, out = _cli(mod, *base_args, "--json")
        parsed = json.loads(out) if code == 0 else []
        check("... --json exits 0 and its output is valid JSON naming the file",
              code == 0 and isinstance(parsed, list) and parsed
              and parsed[0]["file"] == FILE, (code, out[:300]))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_cli_refuses_an_unknown_edit_and_writes_nothing():
    mod = load_module(TOOL, "refresh_base_tool")
    if not shutil.which("git"):
        skip("the CLI refusal fixture", "git is not installed")
        return
    root = tmpdir()
    try:
        repo = _fixture_repo(root)
        live = root / "live"
        live.mkdir()
        unknown = PATCH_TARGET.replace('    return "kept"',
                                       '    return "edited in the live file"')
        write(live / FILE, unknown)
        before = (live / FILE).read_bytes()
        code, out = _cli(mod, "--backend-path", str(live), "--repo", str(repo),
                         "--ref", "HEAD", "--file", FILE, "--apply")
        check("--apply on a target carrying an unknown edit exits 2 - REFUSED",
              code == 2, (code, out))
        check("... the refusal says no published base plus its patches matches",
              "not any published base" in out, out)
        check("... the live file is byte-identical to before",
              (live / FILE).read_bytes() == before)
        check("... and no backup was made, because nothing was written",
              not list(live.glob(f"{FILE}.before-refresh-*")))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_cli_requires_a_file_to_apply():
    mod = load_module(TOOL, "refresh_base_tool")
    root = tmpdir()
    try:
        code, out = _cli(mod, "--backend-path", str(root), "--apply")
        check("--apply without --file is refused: one file, one write",
              code == 2 and "ONE file at a time" in out, (code, out))
        code, out = _cli(mod, "--backend-path", str(root / "nope"),
                         "--file", FILE)
        check("a missing backend folder is refused",
              code == 2 and "not a folder" in out, (code, out))
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
#   main
# ---------------------------------------------------------------------------

def main():
    for name, fn in list(globals().items()):
        if not (name.startswith("t_") and callable(fn)):
            continue
        print(f"\n--- {name} ---")
        try:
            fn()
        except Exception as exc:                              # pragma: no cover
            traceback.print_exc()
            check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, "
          f"{len(SKIPPED)} skipped (a skip is NOT a pass)")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
