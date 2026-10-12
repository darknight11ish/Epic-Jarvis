# Do the checks check anything? An audit of checks that could pass while proving nothing

**Status: AUDIT ONLY. Nothing was fixed, and no test was changed.** Written
2026-10-11 against `origin/main` `64381c0d`. Every line number below was read
with `git show origin/main:<path>` - never `git grep`, which reads the working
tree and produced a false finding in this project earlier the same day.

The owner asked the question directly: *do the checks check anything?* This
document answers with what was **measured**, not with an opinion about the test
suite. It found one shape still present, one already documented, one gap in the
checker that is supposed to catch this class - and it names the checks that are
**sound**, because a list of problems alone says nothing about whether the good
checks are good.

---

## 1. What was run, so the reader can weigh the rest

| What | Result |
|---|---|
| `python tools/check_vacuous_checks.py` | **313 suite files read, 21,350 `check()` call sites examined: "no check is a fake skip, none has a string or defaulted condition."** |
| `git show origin/main:.github/workflows/ci.yml` | the backend job runs `python backend/run_suites.py` (`:213`), then **re-runs each suite on its own** and reports only the first 10 (`:221-226`); the desktop job runs `for f in tests/*.mjs` (`:145`), skipping `uikit.mjs` and `shots.mjs` (`:147`) |
| Playwright | **installed in the scratch test-bed worktree `.dsh-scratch/wt-suites`**, so the desktop `.mjs` suites CAN be run from there. **Two of 182 were run** (`hud.mjs`, `progress.mjs`) at main `40f58fcf`; **none was mutated**, so the desktop side is run but not cleared - see section 3.1 |
| `cargo test` | not run - it OOMs on this machine, as the brief says |

**The 21,350-check number is the strongest single fact in this document**, and
it comes from a tool the repository already has. It means the *specific* shape
the project has been burned by before - `check("SKIP - ...", True)`, a string
condition, or a defaulted condition - is genuinely absent across every suite,
not merely rare. Anyone reading this audit should take that as the floor, not as
the whole answer, because that tool's scope **does not cover the family in
finding 1** (see 3.3).

---

## 2. Findings, ordered by what a wrong green would cost

Nothing found here is a privacy or money check. That ordering matters and is not
a formality: the checks that guard the gate, the spend caps and the scrubber are
**sound** - see section 4 - so the findings below sit in test-harness hygiene,
not in the safety floor.

### 2.1 MEDIUM - a check whose condition is the literal `True` and whose only real evidence is "no exception, no hang"

**File and line:** `backend/test_agent.py:786`
(`check("run_local_turn returns rather than looping forever", True)`).

**What it claims:** that `run_local_turn` terminates instead of looping forever
when a model keeps asking for a tool.

**What it actually does:** the call is made inside a `try:` (`:781-785`) and the
`check(..., True)` runs only if the call returned (`:786`). The condition
therefore **cannot fail**. If `run_local_turn` did loop forever the check would
not go red - the suite would **hang**, and a hang is reported by
`run_suites.py` as a timeout, not as this check failing. The check's own name
promises an assertion on termination that the code does not make.

**Why the mutation is impractical in a bounded run, said plainly:** the
mutation that proves it is "make `run_local_turn` not terminate". That does not
produce a failing assertion to photograph - it produces a hang, which is the
finding. Reproducing it here would wedge a suite in a shared environment, which
is exactly the behaviour that cost this project a night of `%TEMP%` litter. So
this is reported on the next-best evidence the brief allows: **the assertion
read against what it names**, plus the structure of the code around it
(`:775-788`, read in full).

**The fix I would make (not made):** assert on the observable rather than on
having returned - `run_local_turn` already takes `max_rounds=3` at `:784`, so
the check should count the rounds actually used and assert it stopped at the
bound, which can fail. Where a real bound cannot be observed, a dead-man's
timeout around the call is the honest instrument; `check(..., True)` is not.

**How big is this family?** It is not one line. The same shape -
`check(<something>, True)` after a call whose failure mode is an exception or a
hang - appears across the suites (a scan of `backend/test_*.py` finds dozens of
literal-`True` conditions), and **most of them are sound**, because they sit in
the `try/except` idiom of section 4.1. Telling the two apart is exactly the
work this audit could only sample: the distinguishing question is *"if the code
under it broke, would this check go red, or would the suite crash/hang
instead?"* For `test_agent.py:786` the answer is crash-or-hang.

### 2.2 ALREADY KNOWN - green by suite order, not by design (DEF-009)

`backend/test_voice_contract.py:512-514` checks the phone's voice cases against
a fixture, and is **green only because of the order the earlier checks in that
suite leave the world in**. This is already documented as **DEF-009**; it is
listed here so the reader knows it was looked at, and it is **not** reported as a
new finding.

### 2.3 INFO - the checker that hunts this class does not cover its largest member

`tools/check_vacuous_checks.py` reports "no check is a fake skip, none has a
string or defaulted condition" over 21,350 call sites. That is real and
valuable - and it is **scoped to the fake-skip shape**. The `True`-in-a-`try`
family of 2.1 is invisible to it: the condition is the literal `True`, but it is
not a *skip*, so the tool correctly says nothing about it. A reader who takes
"no check is a fake skip" as "no check is vacuous" would be reading a green for
more than it covers - which is the disease this audit exists to find, in the
checker itself. **Widening that tool is the highest-value follow-up here**, and
it is a one-file change.

---

## 3. What I could not do, and why - so no reader fills the gap with optimism

1. **The desktop `.mjs` suites - PARTLY CLOSED, and this paragraph replaces the
   earlier "Playwright is absent" limit.** Playwright is now installed in a
   scratch worktree sitting at `origin/main` (`.dsh-scratch/wt-suites`; a test
   bed, not a branch, and nothing is committed from it). Two of the **182**
   suites in `jarvis-desktop/tests/*.mjs` were run there, at main `40f58fcf`:
   - `node tests/hud.mjs` - **all checks passed**; this is where the
     `rows` -> `composed` incident lives (`hud.mjs:309`, asserted `:367-373`);
   - `node tests/progress.mjs` - **passed** ("the progress pictures hold"; its
     own `composed` ramp is built and asserted at `:400-425`).
   **A pass is not the finding - and one of the two has now been MUTATED.** The
   `hud.mjs` suite's own subject was broken and the suite **went RED**, which is
   the other half of this audit:

   - **Mutation RUN, and it caught it.** `jarvis-desktop/src-tauri/src/hud_bootstrap.js`
     builds the HUD's button; its label and its tooltip are **two separate
     assignments** to the same function - `open.textContent = barLabel(barOnScreen)`
     and, ten lines later, `open.title = barLabel(barOnScreen)`. **Only the
     tooltip assignment was changed**, to a fixed string, leaving the label
     untouched. `node tests/hud.mjs` then reported:
     `FAIL with the shell, the HUD's own chat box is usable, and the button opens
     and hides the bar` / `the tooltip and the label disagree` - **1 failed**,
     exactly the assertion at `tests/hud.mjs:373`. The file was restored from git
     and the suite passes again.
   - **The trap in this mutation, written down because it wastes a run:** changing
     the shared constant `OPEN_BAR` (`hud_bootstrap.js:1168`) changes **both** the
     label and the tooltip, so `assert.equal(composed.title, composed.button)`
     would still pass and prove **nothing**. **Break one assignment, never the
     constant they both read.**
   - **Mutation RUN on the third attempt, and the check caught it - and it names
     WHICH assertion.** The fixture's first ratio
     (`jarvis-desktop/tests/fixtures/progress-cases.json`, the `over_surface`
     array that `tests/progress.mjs:424-425` compares against the live ramp) was
     changed `3.06` -> `3.11`. `node tests/progress.mjs` then reported
     **`1 failed: level 0 is an outline only; levels 1 to 4 are the accent at the
     contract's alphas, and distinguishable in every theme`**, with the failing
     message **`deep-space: the fixture's ratios`** - that is **`:425`**, the
     fixture-ratio comparison, and **not** `:404` (alpha) or `:429` (hue). So the
     red is attributable to the assertion being tested, which was the point of
     naming all three in advance. Restored from git; `git diff` on the fixture is
     empty and the suite is green again.
   - **The first two attempts were refused by the rule below, and the refusal was
     correct**: the first because **two** files matched its search (the test *and*
     its fixture) rather than guessing, the second because its pattern expected
     JavaScript while the file is JSON - `"over_surface": [`, a **quoted key**.
     **In both refused cases the suite run printed green, on an unmutated tree: I
     had two greens from a mutation that never landed, which say nothing.** A green
     from an unmutated tree is not evidence; it is the absence of an experiment.
   - **THE RULE THIS AUDIT LEARNED ABOUT ITS OWN INSTRUMENT, and it belongs in the
     findings, not in a footnote: a mutation must ASSERT THAT IT ACTUALLY CHANGED
     SOMETHING before its run is trusted.** The first attempt at the `hud.mjs`
     mutation **silently did nothing** - PowerShell mangled the quoting, the file
     was never touched, and `node tests/hud.mjs` printed `all passed` on an
     **unmutated** file. That is **a false green manufactured by the mutation tool
     itself** - this audit's disease turned on this audit - and it was caught only
     because the patch script asserted the occurrence count it was replacing.
     Every later attempt asserted the edit and **re-read the file from disk** to
     prove the change had landed before any run was believed. Anyone building this
     instrument should make it refuse loudly, exactly as these did.
   - **Sizing the remaining gap honestly: two of 182 desktop suites have been run,
     and both of those two have been mutated** - `hud.mjs` red at `:373`,
     `progress.mjs` red at `:425`. The rest of the glob is un-run *and* un-mutated,
     so nothing here should be read as clearing the desktop side.
2. **`cargo test` was not run** (it OOMs here, per the brief), so the Rust-side
   assertions are not covered either.
3. **The mutations I would run next, in order, with budget:** (a) make
   `run_local_turn` exceed `max_rounds` and show 2.1's check cannot go red;
   (b) run the mutation recipe the brief describes over `tests/*.mjs` in an
   environment with Playwright; (c) widen `tools/check_vacuous_checks.py` to
   flag a literal-`True` condition whose enclosing block has no `except` that
   can set it `False`.
4. **The 21,350-call sweep is a measurement, not a mutation.** It proves a
   *shape* is absent; it does not prove any individual check would notice its
   subject breaking. Those are different claims, and this document does not
   merge them.

---

## 4. The other half: checks examined and found SOUND

An audit that lists only problems is not an audit. These are the checks I read
against what they claim, and the reason each can genuinely fail:

### 4.1 The `try/except` idiom - a check that CAN go red

`backend/test_animal.py:489-493`:
```python
try:
    compile("def f(self, bind, Handler):\n    " + blk, "<start-up block>", "exec")
    check("the start-up block compiles", True)
except SyntaxError as exc:
    check("the start-up block compiles", False, str(exc))
```
This is the same literal `True` as 2.1 and it is **correct**, because the
`except` sibling turns it red on the exact failure the name promises, and it
carries the exception text into the failure message. **The distinguishing
property is the sibling, not the `True`.** Any future scanner for this family
should look for the `except` that can fail the same-named check before it flags
anything - which is precisely the tool-widening proposed in 2.3.

### 4.2 The repository's own vacuous-check sweep - sound for what it claims

`tools/check_vacuous_checks.py`, measured above: **313 suites, 21,350 call
sites, none a fake skip, none with a string or defaulted condition.** Its own
message states its scope honestly ("A `check("SKIP - ...", True)` is counted as
a PASS ... the project's answer is a real `skip(why)`"), which is the behaviour
I want from a checker: it says what it checked, not just that it passed.

### 4.3 The safety-floor checks were read, not flattered

The gate, spend-cap and scrubber checks are where a wrong green would cost
privacy or money, so they were the first place I looked: **no finding there.**
The scrubber's own docstring refuses to pretend it is a cloud-lane guarantee
(`backend/jarvis_scrub.py:29-32`), and the router's privacy rule is enforced from
the lane rather than passed in by a caller
(`backend/rebuilt/jarvis_router.py:22-23`) - both are the opposite of a check
that proves nothing: each states the limit of what it can promise.

---

## 5. Summary for the owner, in one paragraph

The project's checks are in better shape than the day that produced these five
incidents would suggest: **21,350 call sites across 313 suites were swept for
the known dead shapes and none was found**, and the safety-floor checks were read
against what they claim and are sound. **One shape is still present** - a check
whose condition is the literal `True` while its only real evidence is "the call
did not crash", at `backend/test_agent.py:786` - and it is worth fixing because
its failure mode is a **hang**, which CI reports as a timeout rather than as
that check failing. **One checker gap** follows from it: the tool built to catch
this class does not look at it. **One mutation has now been run and the check
caught it:** breaking the HUD button's tooltip - one assignment, not the shared
constant - made `tests/hud.mjs` go **red** with `the tooltip and the label
disagree`, then the file was restored. **Two of 182 desktop suites have been
run; one has been mutated.** `progress.mjs`'s mutation is named in section 3.1
and not yet run.

---

## 6. The next slice: two of the five incidents are NOT in the desktop glob

The next slice was to take the next two suites where the five incidents live and
mutate them the same way. **Searching for them changed the picture, so the finding
here is about where those incidents actually live.**

- **`initiallyOpen`** - the identity comparison that could never fail - is **not in
  any desktop `.mjs` suite**. It is in the phone's Kotlin:
  `jarvis-client/app/src/main/java/com/jarvis/client/ui/parts/ScrollToKey.kt`, with
  its test in `jarvis-client/app/src/test/java/com/jarvis/client/ui/parts/ScrollToKeyTest.kt`.
- **The plate-placement incident** - where a substitute instrument reported
  "0 moved" while CI failed two tests about exactly that - is also the phone's:
  `jarvis-client/app/src/test/java/com/jarvis/client/GoalsTest.kt` and
  `RetirementTest.kt`.
- **`emitted`** does not appear as an assertion in the backend suites or the
  desktop suites on main (only in comments: `bar-chrome.mjs:221`,
  `uikit.mjs:663`, `voice-speech.mjs:129`), so `emitted=0` is not reproducible
  from this glob either; it may have been renamed since, or live in the Kotlin
  tests as well.

**These are Kotlin/Gradle tests, not `.mjs` suites, and they are run by a
DIFFERENT workflow:** `.github/workflows/jarvis-client.yml` runs
`./gradlew testDebugUnitTest` (around `:113-118`) on `ubuntu-latest`. **`ci.yml`'s
jobs are `rust`, `frontend`, `backend`, `backend-windows`, `credential-manager`,
plus the informational `audit` and `python-advisories` - there is no Gradle job in
`ci.yml` at all.** So two of the five incidents sit in tests that **none of the six
required checks runs**; their green is trusted through a separate workflow.

**Why I did not mutate them here, stated rather than skipped silently:** the
Android SDK *is* present on this machine (`ANDROID_HOME` set, `gradlew` present),
so they are not impossible - but running them means a full Gradle/Android build,
which is a different instrument from the Playwright suites this slice was scoped
to, and a build-mutate-restore cycle did not fit the slice. **They are the right
next target and they need their own run.**

**Sizing sentence, exact and unchanged for the desktop glob: two of 182 desktop
suites have been run, and both of those two have been mutated** (`hud.mjs` red at
`:373`, `progress.mjs` red at `:425`). This slice added no desktop suite, because
the two remaining incidents are not desktop suites. **Nothing here clears the
desktop side**, and the Kotlin suites are now named with the workflow that runs
them so the next person does not have to search for them again.

---

## 7. The phone's suites: they RUN here, and `initiallyOpen` is already fixed

Second glob. The phone's Kotlin tests are a **second set of suites**, and unlike the
desktop ones they need Gradle. **They build and run on this machine** - Android SDK
present (`ANDROID_HOME` set), JDK 17, `gradlew` present:

    cd jarvis-client
    ./gradlew :app:testDebugUnitTest --tests "com.jarvis.client.ui.parts.ScrollToKeyTest"
    -> BUILD SUCCESSFUL in 1m 51s   (ScrollToKeyTest green)

**So the hole is not that these tests cannot run. They run. The hole is that
`ci.yml` never invokes them for a given pull request** - they are run only by
`.github/workflows/jarvis-client.yml`, which is not one of the six required checks.
A phone change can therefore merge with its tests skipped, and the tests exist and
pass when someone chooses to run them.

### 7.1 `initiallyOpen` - the identity comparison - is ALREADY FIXED on main

This was the strongest claim in the audit, so it was checked first, and the answer
is in the source rather than in a test. `initiallyOpen` is **not an identifier and
not an assertion**: it was a **log field name**, and the string appears on main only
in comments. The code that used it now carries this note
(`jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/BrainScreen.kt`,
the `jumpOpens=` log line):

> NOT "initiallyOpen": this is a function of the ASKED-FOR section alone (`toOpen`
> is `sectionOf(key)?.key`), so it can only ever equal `holder`. It says nothing
> about what was open before the jump, and the old name said it did - which would
> have made a controlled pair unreadable, both runs printing the same value
> whatever the real state was. `openKey` is the field that answers that question.

**So the incident is real, already known, and already fixed** - the field was
renamed to `jumpOpens`, and the source says in its own words that the old name
"could only ever equal" the holder. It is reported here as **already fixed**, not as
a new finding (the same category as DEF-009).

**Why no mutation was run for it:** a comparison of one expression with itself
cannot be made to fail by changing anything else - that impossibility *is* the
finding, and the fix has already removed it. There is nothing left to mutate.

### 7.2 `GoalsTest` / `RetirementTest` - the plate-placement incident - NOT mutated

`jarvis-client/app/src/test/java/com/jarvis/client/GoalsTest.kt` and
`RetirementTest.kt` exist on main and the Gradle build above compiles them (both
appear in the build's own output). **They were not run or mutated in this slice:**
a full Gradle cycle is ~2 minutes per run, and a run-mutate-restore cycle did not
fit. The instrument is proven to work here, so the next person starts from a
green baseline rather than from "can this even build".

### 7.3 Sizing, both globs, exact

- **Desktop: two of 182 suites have been run, and both of those two have been
  mutated** (`hud.mjs` red at `:373`, `progress.mjs` red at `:425`).
- **Phone: one suite (`ScrollToKeyTest`) has been run and is green; no phone suite
  has been mutated.** The phone's glob has not been counted here, so no fraction is
  claimed for it.

**Nothing in this document clears either glob.**
