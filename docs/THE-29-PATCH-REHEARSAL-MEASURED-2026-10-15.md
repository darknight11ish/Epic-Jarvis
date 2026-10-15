# The 29-patch rehearsal failure: what it actually is, measured

**Written 2026-10-15** by the Lead, after an earlier attempt to "fix" this was
**wrong** and was closed (PR #437). This file replaces that guess with a
measurement, and it deliberately stops short of a fix.

## The symptom

`scripts/apply-patches.ps1` rehearses every patch against the published base
(`jarvis-backend/`) before it changes anything. On `main` that rehearsal reports
**29 patches will not apply**, exit 1. Re-running against a copy that carries
`_jarvis-state.json` reports "all patches are already on" instead, because the
record short-circuits the rehearsal — so this is only visible against a
**freshly copied base with no record**, which is what the handoff's own
instructions produce.

## What the 29 are, classified

Each failing patch was checked against its own base file for two things: does the
base still hold the patch's **pre-image** (so it should apply), or does it already
hold the **post-image** (so it is redundant)?

```
POST-IMAGE (redundant):      0
PRE-IMAGE  (undrifted):      2      screen-attach, card-prefs
NEITHER    (real drift):    31      (the other 29 + the 4 rebuilt halves)
```

So this is **not** redundant patches and **not** a line-number problem. **31 of 33
failing patches are at neither the state they expect to apply to nor the state
they would produce.** The base and those patches come from different generations
of the program.

## Why, from the repository's own record

`jarvis-backend/README.md` documents this exact class of problem, measured
**2026-10-10** (lines ~114-127):

- The base "was kept here by hand until 2026-10-10, and by then it had gone
  stale: 77 files" out of date.
- Re-taking it from the owner's live folder and following the rule to the letter
  made **9 checks fail** across three suites, "and a re-taken file already
  carries the patch".

**A re-taken base is a POST-patch folder.** The live backend has all 143 patches
applied, so a base re-taken from it carries their changes. That is correct for a
clone that has to run, and it is exactly why the patches then find their
pre-image gone.

The numbers confirm the generations have since moved further apart:

| since the base was published (`0c5bc2f9`, 2026-10-06) | count |
|---|---|
| base `*.py` files changed | **75** |
| patch files changed | **65** |

## What this means

The base and the patches have **two different jobs and they have diverged**:

- the **base** is a runnable folder, and it is at (or near) the post-patch state;
- the **patches** describe the delta from a **pre-patch** state.

A rehearsal that applies every patch to the base is therefore asking the base to
be something it is not. **The pre-image the patches need is not in the
repository** — it is the owner's live folder *before* the patches went on, and
nobody keeps that.

## What is NOT the answer (and cost real time to learn)

**Do not edit `jarvis-backend/jarvis_hud.py` to move it back toward a pre-image.**
That was PR #437. It removed 38 lines from the base, broke **seven suites** that
read that file directly as the canonical patched program, and had to be reverted
and closed. `jarvis-backend/` is not scratch space; it is the shipped program.

## What a real decision would have to settle

This needs a choice, not a patch, and it is the owner's:

1. **Regenerate the base and stop pretending it is a patch target.** Accept that
   the rehearsal cannot pass, and replace it with the check that *is* meaningful:
   does the base differ from the owner's live folder only in ways the patches
   explain? `tools/gen_base_from_backend.py --check` is that check, and
   `backend/test_base_regeneration.py` passes today (36 passed, 0 failed) — so the
   base *is* consistent with its own rule.
2. **Keep a true pre-patch snapshot in the repository** so the rehearsal has
   something honest to apply to. That is new state to maintain, and it will drift
   the moment anyone patches the live folder without re-taking it.
3. **Drop the rehearsal for the fresh-clone path** and document that patches are
   for the owner's own folder, which is what they were written for.

Until one of those is chosen, the honest position is: **the rehearsal's red is a
true statement about a structural mismatch, not a bug, and it should not be
"fixed" by editing the base.**

## The one thing that IS a genuine bug, and is separate

`apply-patches.ps1` gives a rehearsal on a copy that carries `_jarvis-state.json`
the answer "all patches are already on" **without rehearsing anything**. That is
intended for a real run — the record is hash-verified, and a record that
disagrees with the files prints the drift and rehearses anyway — but it is a trap
for anyone following the handoff's rehearsal instruction, because the obvious
scratch folder (`$env:TEMP\hudstack`) is one an earlier run already recorded. This
is now written into the script's own `.PARAMETER Manifest` help. Measured and
fixed there; no behaviour changed.
