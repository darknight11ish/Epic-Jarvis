"""test_capability_core_subset.py - the fast capability core subset CI runs.

    python3 backend/test_capability_core_subset.py

WHY THIS EXISTS (2026-11-18, the two CI guards the external review asked for).
On 2026-11-18 two pull requests that each touched `backend/jarvis_quick.py`
were green alone, merged, and changed each other's behaviour: main went red on
`backend/test_capability_answers.py` - "no ordinary shape lost its row",
`cloud-escalation 63 < 65`. The suite that caught it exists; what the review
ruled is that the exhaustive 5,410-question sweep should not be the every-PR
shape. So the suite now runs a fast CORE SUBSET on every pull request (239
pinned cases), and the full sweep only when `features/features.json` or
`backend/jarvis_feature_catalogue.py` (or its twin) changed.

WHAT THIS PROVES, and each check bites:
1. THE COUNTS. The core is exactly 239 cases: 184 owner-worded (one question
   naming each catalogue row's own title) + 53 regression-sensitive (every
   answer the 2026-11-18 capability fix changed) + 2 dated known losses that
   are printed but never counted as passes.
2. THE SUBSET. Every core question is a question the full sweep already asks,
   generated from the SAME row's own words - so the core cannot drift into a
   second sweep, and a core case is always a real full-sweep case.
3. THE MODE. The 5,410-question sweep is OFF by default (the every-PR mode)
   and ON only with JARVIS_CAPABILITY_FULL_SWEEP=1. In the default mode the
   sweep function registers no checks at all - it prints a SKIP sentence
   saying the full sweep did NOT run, because a skip is never a pass.
4. IT BITES. A core case pinned to the wrong row makes the core check FAIL, and
   a row that loses its own title question fails - proved by perturbing a copy
   of the pinned list, not by trusting the test to be strict.
5. THE WIRING IN ci.yml. The required `backend` job's shard job runs the suite
   (default core mode) and has the named `--core` step; the full-sweep step
   exists, is in shard 1, carries JARVIS_CAPABILITY_FULL_SWEEP=1, and is
   gated on the changed-file step that names the ruling's three paths. A diff
   that touches none of them does not run the full sweep.
"""
from __future__ import annotations

import contextlib
import io
import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CI_YML = REPO / ".github" / "workflows" / "ci.yml"
sys.path.insert(0, str(HERE))
import test_capability_answers as CAP  # noqa: E402

FAILED, PASSED = [], []

#: The ruling's three paths - the feature catalogue's source and its twin, and
#: the generated features.json the catalogue's rows come from.
CATALOGUE_PATHS = (
    "features/features.json",
    "backend/jarvis_feature_catalogue.py",
    "jarvis-backend/jarvis_feature_catalogue.py",
)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _full_sweep() -> dict:
    """question -> the catalogue row whose own words generated it.

    Built with the suite's own generator, exactly as `t_no_ordinary_shape_lost
    _its_row` builds it, so "the core is a subset of the full sweep" is asked
    of the same instrument the full sweep uses.
    """
    full = {}
    for row in CAP.C.FEATURES:
        for sentence in CAP._ordinary_shapes(row):
            full.setdefault(sentence, set()).add(row["id"])
    return full


def _job_block(text: str, name: str) -> str:
    """One job's lines in ci.yml, from `  <name>:` to the next `  <job>:`."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines)
                  if line.rstrip() == f"  {name}:"), None)
    if start is None:
        return ""
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if re.match(r"^  [A-Za-z0-9_-]+:\s*$", lines[i]):
            end = i
            break
    return "\n".join(lines[start:end])


def _code(block: str) -> str:
    """A job's lines with comments removed - the YAML that actually runs."""
    return "\n".join(line for line in block.splitlines()
                     if not line.lstrip().startswith("#"))


# --------------------------------------------------------------------------
#   1. the counts
# --------------------------------------------------------------------------
def t_the_core_has_its_counts():
    check("the catalogue still has 184 rows, so the owner-worded group is one per"
          " row", len(CAP.C.FEATURES) == 184, str(len(CAP.C.FEATURES)))
    check("the core carries 184 owner-worded cases",
          len(CAP.CORE_OWNER_WORDED) == 184,
          str(len(CAP.CORE_OWNER_WORDED)))
    check("... 53 regression-sensitive cases (the capability fix's changed"
          " answers)", len(CAP.CORE_REGRESSION) == 53,
          str(len(CAP.CORE_REGRESSION)))
    check("... and two dated known losses, named but never counted as passes",
          len(CAP.CORE_KNOWN_LOST) == 2, str(len(CAP.CORE_KNOWN_LOST)))
    total = (len(CAP.CORE_OWNER_WORDED) + len(CAP.CORE_REGRESSION)
             + len(CAP.CORE_KNOWN_LOST))
    check("the routed total is 239 cases (~230: the review's estimate)",
          total == 239, str(total))
    check("no question appears twice across the pinned lists",
          len({q for q, _ in CAP.CORE_OWNER_WORDED}
              | {q for q, _ in CAP.CORE_REGRESSION}
              | {q for q, _, _ in CAP.CORE_KNOWN_LOST})
          == len(CAP.CORE_OWNER_WORDED) + len(CAP.CORE_REGRESSION)
          + len(CAP.CORE_KNOWN_LOST))


# --------------------------------------------------------------------------
#   2. the core is a SUBSET of the full sweep, row for row
# --------------------------------------------------------------------------
def t_the_core_is_a_subset_of_the_full_sweep():
    full = _full_sweep()
    check("the full sweep really is the 5,410 questions the suite measures",
          sum(len(CAP._ordinary_shapes(row)) for row in CAP.C.FEATURES) == 5410,
          "not 5410")
    missing = []
    for sentence, row_id in (list(CAP.CORE_OWNER_WORDED)
                             + list(CAP.CORE_REGRESSION)):
        if sentence not in full:
            missing.append(f"{sentence!r} is not in the full sweep")
        elif row_id not in full[sentence]:
            missing.append(f"{sentence!r} is a full-sweep question, but not one "
                           f"built from {row_id}'s own words")
    check("every owner-worded and regression-sensitive core case is a question"
          " of the full sweep, built from the same row's own words",
          not missing, "; ".join(missing[:8]))
    known_missing = [sentence for sentence, _row, _wrong in CAP.CORE_KNOWN_LOST
                     if sentence not in full]
    check("... and every dated known loss is a full-sweep question too",
          not known_missing, str(known_missing))
    # A specific, named pair is in BOTH lists - the review's own phrasing: "a
    # case in the core list is also in the full list".
    sample = CAP.CORE_OWNER_WORDED[0]
    check("a named core case is literally in the full list (spot check)",
          sample[0] in full and sample[1] in full[sample[0]],
          f"{sample!r} not in the generated sweep")


# --------------------------------------------------------------------------
#   3. the mode: the full sweep is off by default, on only by the one variable
# --------------------------------------------------------------------------
def t_the_full_sweep_is_off_by_default():
    check("the mode variable is named once", CAP.FULL_SWEEP_ENV
          == "JARVIS_CAPABILITY_FULL_SWEEP", CAP.FULL_SWEEP_ENV)
    check("no environment at all means the core subset, not the full sweep",
          CAP.full_sweep_enabled({}) is False)
    check("... and the explicit on value is the only truthy one",
          CAP.full_sweep_enabled({CAP.FULL_SWEEP_ENV: "1"}) is True)
    for value in ("", "0", "true", "yes", " 1 ", "2"):
        check(f"it fails closed on {value!r}",
              CAP.full_sweep_enabled({CAP.FULL_SWEEP_ENV: value}) is False,
              value)
    # The default mode really does not run the 5,410-question sweep: the sweep
    # function registers NO check, it prints a SKIP sentence instead.
    before = len(CAP.PASSED)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        CAP.t_no_ordinary_shape_lost_its_row()
    printed = out.getvalue()
    check("in the default (every-PR) mode the full sweep registers no check at all",
          len(CAP.PASSED) == before, f"{len(CAP.PASSED) - before} check(s) registered")
    check("... and says SKIP, naming the variable that would run it",
          "SKIP the full 5,410-question sweep" in printed
          and CAP.FULL_SWEEP_ENV in printed, printed[:300])
    check("... and never counts itself as a pass",
          "ok   the sweep" not in printed, printed[:300])


# --------------------------------------------------------------------------
#   4. the core BITES: a wrong row or a lost question fails it
# --------------------------------------------------------------------------
def t_a_pinned_wrong_row_fails_the_core():
    """Mutate the pinned list, run the real check, watch it go red, restore."""
    original = CAP.CORE_REGRESSION
    bogus = (("What is Type a message and read the answer?", "cloud-escalation"),)
    passed_before, failed_before = len(CAP.PASSED), len(CAP.FAILED)
    try:
        CAP.CORE_REGRESSION = original + bogus
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            CAP.t_the_core_subset_holds()
        printed = out.getvalue()
        failed = len(CAP.FAILED) - failed_before
        check("a core case pinned to the wrong row makes the core check FAIL",
              failed >= 1, f"{failed} failing check(s)\n{printed[-600:]}")
        check("... and the failure names the question the reader must look at",
              "cloud-escalation" in printed and "Type a message" in printed,
              printed[-600:])
    finally:
        CAP.CORE_REGRESSION = original
        # Undo the checks the perturbation added to the suite's own tallies.
        del CAP.PASSED[passed_before:]
        del CAP.FAILED[failed_before:]


def t_a_lost_title_question_fails_the_core():
    """A row whose own-title question stops reaching it is a failed core."""
    # The known-lost entries are the live example: the check reports them, and
    # the only reason the suite is green is that they are on the dated list.
    check("the dated known losses are exactly the two cloud-escalation questions",
          {row for _s, row, _w in CAP.CORE_KNOWN_LOST} == {"cloud-escalation"},
          str(CAP.CORE_KNOWN_LOST))
    out = io.StringIO()
    before = len(CAP.FAILED)
    with contextlib.redirect_stdout(out):
        CAP.t_the_core_subset_holds()
    printed = out.getvalue()
    check("the live core subset passes with no NEW losses", len(CAP.FAILED) == before,
          printed[-600:])
    check("... and prints both known losses on every run, as KNOWN LOST, never ok",
          printed.count("KNOWN LOST") == 2
          and "NOT a pass" in printed, printed[-800:])


# --------------------------------------------------------------------------
#   5. the CI wiring
# --------------------------------------------------------------------------
def _step_block(code: str, marker: str) -> str:
    """The step whose lines contain `marker`, from its `- name:` to the next one."""
    lines = code.splitlines()
    hit = next((i for i, line in enumerate(lines) if marker in line), None)
    if hit is None:
        return ""
    start = hit
    while start > 0 and not lines[start].lstrip().startswith("- "):
        start -= 1
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("- "):
            end = i
            break
    return "\n".join(lines[start:end])


def t_ci_runs_the_core_every_pr():
    if not CI_YML.is_file():
        check("ci.yml is where this test expects it", False, str(CI_YML))
        return
    text = CI_YML.read_text(encoding="utf-8")
    shard = _job_block(text, "backend-shard")
    backend = _job_block(text, "backend")
    code = _code(shard)
    check("ci.yml has the `backend-shard` job the backend suites run in",
          bool(shard), "backend-shard")
    check("the shard job runs every backend suite through run_suites.py (which"
          " runs this capability suite in its default CORE mode)",
          "backend/run_suites.py" in code, code[:400])
    check("the full-sweep variable appears exactly once in the shard job, on the"
          " full-sweep step - no ordinary pull request pays for the 5,410"
          " questions", code.count(CAP.FULL_SWEEP_ENV) == 1,
          f"{code.count(CAP.FULL_SWEEP_ENV)} occurrences")
    check("the required `backend` check is the aggregator over `backend-shard`",
          bool(re.search(r"needs:\s*\[?[^\]\n]*backend-shard",
                         _code(backend))),
          (backend or "")[:400])
    core_step = _step_block(code, "backend/test_capability_answers.py --core")
    check("a named step runs the core subset explicitly (--core)", bool(core_step),
          "no --core step in backend-shard")
    check("... and it is shard 1 only, like the other once-per-run steps",
          "matrix.shard == 1" in core_step, core_step[:300])
    check("... and that step does not set the full-sweep variable",
          CAP.FULL_SWEEP_ENV not in core_step, core_step[:300])


def t_ci_runs_the_full_sweep_only_when_the_catalogue_changed():
    text = CI_YML.read_text(encoding="utf-8")
    shard = _code(_job_block(text, "backend-shard"))
    marker = "backend/test_capability_answers.py"
    full_step = _step_block(shard, "JARVIS_CAPABILITY_FULL_SWEEP")
    check("the full-sweep step exists in the shard job", bool(full_step),
          "no step sets the full-sweep variable")
    check("... it sets the full-sweep variable to its only truthy value",
          re.search(re.escape(CAP.FULL_SWEEP_ENV) + r':\s*"1"', full_step)
          is not None, full_step[:500])
    check("... it is gated on the changed-file step's output",
          "steps.catalogue.outputs.catalogue == 'true'" in full_step,
          full_step[:500])
    check("... it is shard 1 only, so the full sweep is paid for once",
          "matrix.shard == 1" in full_step, full_step[:500])
    check("... and it is the full suite, not the --core shortcut",
          marker in full_step and "--core" not in full_step, full_step[:500])
    # The changed-file step: the ruling's three paths, and an output the gate
    # reads. YAML has no per-job `paths:`, so these three literal paths ARE the
    # filter.
    changed_step = _step_block(shard, "Did the feature catalogue change?")
    check("the changed-file step is in the shard job, where the gate can need it",
          bool(changed_step), "no changed-file step")
    # The step writes the paths inside a grep -E pattern, where the dots are
    # escaped (`features\.json`), so compare against that spelling.
    unescaped = changed_step.replace("\\.", ".")
    for path in CATALOGUE_PATHS:
        check(f"the changed-file step names the catalogue path {path}",
              path in unescaped, "missing from the changed-file step")
    check("the changed-file step writes the `catalogue` output the full sweep"
          " gate reads", 'echo "catalogue=true" >> "$GITHUB_OUTPUT"' in changed_step
          and 'echo "catalogue=false" >> "$GITHUB_OUTPUT"' in changed_step)
    check("the step compares with git, because a workflow-level paths: filter"
          " would stop a required check reporting",
          'git diff --name-only "$base...HEAD"' in changed_step)
    # The grep pattern is the ruling's filter in its executable form; prove it
    # selects exactly the three paths and nothing that merely looks like them.
    found = re.search(r"grep -E '(\^.*\$)'", changed_step)
    check("the changed-file step filters with one anchored pattern", bool(found),
          changed_step[-500:])
    if found:
        pattern = re.compile(found.group(1))
        for path in CATALOGUE_PATHS:
            check(f"... and the filter selects {path}", bool(pattern.match(path)))
        for path in ("features/features.json.bak",
                     "backend/jarvis_feature_catalogue_extra.py",
                     "backend/jarvis_quick.py",
                     "docs/JARVIS-API.md",
                     "jarvis-desktop/package.json"):
            check(f"... and the filter does not select {path}",
                  not pattern.match(path))


def main():
    for fn in (t_the_core_has_its_counts,
               t_the_core_is_a_subset_of_the_full_sweep,
               t_the_full_sweep_is_off_by_default,
               t_a_pinned_wrong_row_fails_the_core,
               t_a_lost_title_question_fails_the_core,
               t_ci_runs_the_core_every_pr,
               t_ci_runs_the_full_sweep_only_when_the_catalogue_changed):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
