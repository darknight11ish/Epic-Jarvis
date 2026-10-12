# The checker census (2026-10-12)

**Why this exists.** A checker that nothing runs is green this morning and
worthless the moment it stops being green, because nothing tells anyone. On
2026-10-12 two checkers under `tools/` were found to be **named in `ci.yml` but
never run by it** - `check_obscura.py` and `check_work_claims.py` - and the
question that followed was wider than those two:

> Under `tools/` and `backend/`, what can be run and can fail, and does anything
> run it?

The census below answers that for every such file, **not** only the ones whose
name starts with `check_`.

## The population

| | count |
|---|---|
| non-data files under `tools/` and `backend/` | **647** |
| of those, files that can be run and can fail (a `__main__`, argv parsing, or a script extension) | **478** |
| ... suites (`test_*.py`) | 298 |
| ... programs | **180** |

A name-shaped census ("grep for `check_*`") can see about **40** of those 478.
That gap is the reason this document exists.

## The result

- **`NO HOME`: none.** Every one of the **180 programs is named by something.**
  There is no runnable tool under `tools/` or `backend/` that nothing at all
  mentions. Of the 180: **33** run in CI, **41** are invoked from `scripts/`,
  **81** are driven by a suite, **15** by another tool, and **10** are named only
  in documentation or configuration (below).
- **Named only in documentation or configuration (10)** - nothing that runs them
  names them:
  `tools/find-flat-regions.ps1`, `tools/offdevice/SelfCheck.ps1`,
  `tools/pretend_linux.py`, `tools/gen_galaxy_cases.py`,
  `tools/gen_gemini_bundles.py`, `tools/gen_launcher_icon.py`,
  `tools/gen_ollama_direct_patch.py`, `tools/gen_quiz_cloud_cases.py`,
  `tools/gen_source_bundle.py`, `tools/gen_youtube_cases.py`.
  Two are the instruments used while writing this (`find-flat-regions.ps1` and
  `SelfCheck.ps1`) and both are **by-hand tools whose own headers say so** - a
  documented by-hand home is a home, but it is worth knowing that no runner and
  no script names them. (Bucket caveat: the bucket means "no runner, script,
  suite or tool file names it". Two entries have a non-doc first reference -
  `jarvis-desktop/src-tauri/src/windows.rs` and `.gitignore` - which the bucket
  counts here because neither file runs anything.)
- **The two comment-only checkers, and where each really runs:**
  - `check_obscura.py` - **run by hand on the owner's PC**: `backend/README.md:18439`
    ("runs the check again by hand"), `CHANGELOG.md:229`; its logic is exercised
    without the binary through `backend/_fake_obscura.py`.
  - `check_work_claims.py` - **driven by `backend/test_work.py:756`**, which
    reports its no-input exit as a **SKIP**. So it is not "his PC or nothing".
  - Neither should be wired as a step: in CI each could only ever **skip**, and
    **a step that always skips is noise, not a check** - it trains people to
    ignore the column it sits in, exactly as a permanently-red `audit` does from
    the other side.

## Three traps this census fell into, so the next one does not

1. **A name in a workflow is not a run.** The "deliberately NOT wired" comment in
   `ci.yml` *names* `check_obscura.py` and `check_work_claims.py`; a census that
   greps for the name reports both as wired. Discriminate by the **line**: a
   reference counts as a run only when the line is a command (it does not start
   with `#` and contains `run:`, `python` or `-File`). **The tell that the
   discriminator is missing: every bucket comes back `0`. A classification that
   returns the same verdict for everything has not classified anything.**
2. **A name in a skip list reads exactly like a name in a run list.**
   `backend/run_suites.py:28` - *"the skip list is explicit, not guessed from a
   failure"* - so the ~31 suite names in that file are the suites to **skip**, not
   the suites it runs. Reading them as a run list invents dozens of "orphan"
   suites that are in fact run.
3. **"Mentioned in a workflow" and "run by a workflow" are different questions
   again.** The Ubuntu backend job runs `backend/run_suites.py` (`ci.yml:213`),
   which runs **every** suite and skips only its own list; the hand-listed arrays
   in `ci.yml` belong to the **Windows** job, which is a deliberate subset. So a
   job that invokes a runner naming almost nothing will make **every one of its
   suites look unrun** to a name-based census. The second question is answered by
   **reading how the job selects suites**, not by finding names in the file.

## How the census was controlled

Before trusting any classification, two files were classified whose answers were
already known - and they had to give **two different verdicts**, because one
expectation for both proves nothing:

| file | workflow | home | correct? |
|---|---|---|---|
| `tools/check_stale_twins.py` | `COMMAND` | `CI` | yes |
| `tools/check_obscura.py` | `COMMENT-ONLY` | not `CI` | yes |

A first attempt was voided because its `.github/` branch counted a mention in a
comment as a run, and because the guard asked for `CI` from both controls. **A
census is a checker: a check that cannot fail is not a check.**

## What this document does not say

The figures above are **candidates, not verdicts**, in two places: the
documentation-only bucket (a reference could be a command line in a file type the
buckets do not model) and any per-file home that depends on a mention whose line
was not read. The two controls are the part that was verified; the rest is what
the classifier returned.