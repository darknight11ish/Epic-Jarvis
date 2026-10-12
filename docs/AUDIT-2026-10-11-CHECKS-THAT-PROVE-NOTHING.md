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
     so nothing here should be read as clearing the desktop side. **Why that number
     is a structural limit rather than neglect - and the bed that lifts it - is
     3.1, written 2026-10-12 once the bed existed and its red had been witnessed.**
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

### 3.1 Why this record sits at two of 182 - the structural limit, and the bed that lifts it

**A mutation pass needs one tree where the suite can run AND the file may be
edited.** The desktop `.mjs` suites are runnable in exactly one worktree -
`node_modules` and Playwright are present in `.dsh-scratch/wt-suites/jarvis-desktop`
and absent from every other - and that worktree is shared, so **the only bed that
may be mutated is the one bed that must not be.** That is why this record sits at
2 of 182, and it is a **structural limit, not neglect.**

**And the trap that limit avoided, written down because it looks like success:**
mutating in one worktree while running the suite in another tests the **unmutated**
copy - so every mutation comes back green, and the table reads as the strongest
possible result while being twenty false findings. **An instrument answering a
question about a different tree.** It is the colour tool reading one channel, the
two-dot diff, and a sweep reading silence, in one shape - and it was caught before
a single mutation was run.

**The bed now exists and its red has been demonstrated**, which is what makes the
next session's twenty mutations evidence rather than decoration (`.dsh-scratch/`
is scratch space, so nothing here is committed; the bed itself carries no branch
and no commits, verified 2026-10-12 detached at the then-current `origin/main`):

```
worktree : .dsh-scratch/mutation-bed     detached at origin/main, no branch, carries no commits
junction : jarvis-desktop/node_modules -> wt-suites/jarvis-desktop/node_modules
           (wt-suites NOT modified; Chromium shared from %LOCALAPPDATA%\ms-playwright)

baseline           node tests/chatbot.mjs                                 -> exit 0
MUTATION           src/chatbot.js: "the amounts are estimates." -> "GUESSES."
run with mutation  node tests/chatbot.mjs                                 -> exit 1
                   FAIL  the words are the PC's and the phone's, word for word
restore            git checkout -- jarvis-desktop/src/chatbot.js
restored run       node tests/chatbot.mjs                                 -> exit 0
```

**Green, red, green - a witnessed failure and a witnessed recovery in the bed
itself**, and the junction survives all of it, so **no per-bed `npm i` is needed.**
The next session starts with exactly this:

```
cd .dsh-scratch/mutation-bed/jarvis-desktop && node tests/<suite>.mjs
```

**A bed whose red has not been demonstrated will report twenty false greens.** That
is why this proof lives in the record rather than in a message: the next reader has
to be able to check the bed before trusting anything it says.

---

### 3.2 Which desktop suites were mutated, and what caught it

**A mutation pass needs ONE tree where the suite can run AND the file may be
edited.** Playwright is installed in exactly one worktree (`.dsh-scratch/wt-suites`,
section 1) and that worktree is shared - so the only bed that may be mutated is
the one bed that must not be. **That is why this section is four rows and not ten,
and it is a structural limit rather than neglect.**

Mutating in one worktree while running the suite in another tests the *unmutated*
copy and reports **green for every mutation** - a table of false findings dressed
as the strongest possible result. That trap is why the bed below was built and
**proved red before any mutation was counted**.

The bed: `.dsh-scratch/mutation-bed`, a detached worktree at `origin/main`, with
`jarvis-desktop/node_modules` **junctioned** to `wt-suites`'. `wt-suites` was not
modified. The junction survives repeated runs and Chromium is shared from
`%LOCALAPPDATA%\ms-playwright`, so no per-bed install is needed.

**Proved before use:** `node tests/chatbot.mjs` green; `src/chatbot.js`
`"estimates."` -> `"GUESSES."` **red** (`FAIL the words are the PC's and the
phone's, word for word`); restored; green again.

| # | suite | what was mutated | result | the assertion that caught it |
|---|---|---|---|---|
| 1 | `chatbot-api-keys.mjs` | `src/chatbot-api-keys.js:30` - renamed the first entry of the exported `SERVICES` list, `"openai"` -> `"openai-typo"` | **RED** | `readChatbotApiKeys always returns the six, in order, even from an odd answer` **and** `CONTROL: the six services are the generated fixture's, in its order` |
| 2 | `heavy-approve.mjs` | `src/heavy-approve.js` - the weight test stops recognising `"heavy"` (`=== "heavy"` -> `=== "heavyy"`) | **RED** | `isHeavy: true only for notice.weight === "heavy"` **and** `CONTROL: a labelled heavy card is still heavy, and a labelled normal local card is not` |
| 3 | `approval-target.mjs` | `src/approval-target.js` - `GONE_LINE`'s words gain `" (changed)"` | **RED** | `the refusal is one plain sentence, and says where the card went` |
| 4 | `account-secrets.mjs` | `src/account-secrets.js` - one account-secret identifier renamed, `"home_token"` -> `"home_token_renamed"` | **RED** | `readAccountSecrets always returns the four, in order, even from an odd answer` **and** `Settings: all four secrets show, in order, each with its own help` **and** `Settings: a secret already set as an environment variable disables its box` |
| 5-10 | `approvals-contract.mjs`, `blockers.mjs`, `screen-work.mjs`, `lock-capture.mjs`, `chatbot-money.mjs`, `limits.mjs` | **not mutated** | - | next session; the bed is ready, and two of them need a different shape (below) |

**Restored after each mutation and proved green again: mutation 1 left the bed
with 0 modified files and `chatbot-api-keys.mjs` passing (exit 0).**

**Two things this pass found that are findings, not repairs.** First, **a shared
module means the catch belongs to the FILE, not the suite**: `chatbot-money.mjs`
and `chatbot-api-keys.mjs` both import `src/chatbot-api-keys.js`, so a red in
either can come from code the other one names. Second, **`account-secrets.mjs`
carries a self-referential assertion** - `assert.deepEqual(rows.map((r) => r.name),
[...SECRETS])` compares the module's output against **its own exported list**, so
on its own it cannot catch an edit to that list; what caught the rename were the
three assertions that **name** the secrets. Reported, not repaired: a vacuous
assertion and its repair are two changes.

**And two suites resisted for a reason worth recording rather than a verdict.**
`chatbot-money.mjs` and `limits.mjs` were **green**, but the mutations first
chosen **did not apply** (0 matches in the module each import resolves to), so
they get **no row**: reporting "stayed green" from a pattern that never landed
would have invented a vacuous suite out of a bad pattern. `lock-capture.mjs`
imports no `src/*.js` module at all - it reads files as text through `read(p)` -
so its mutation is a text change in another file rather than a constant.

**Every mutation above was restored, and the bed was left with 0 modified files
and the junction intact after each one.**


**Four suites of the ten, done properly, rather than ten claimed.** The method is
proved end to end - find a constant the suite asserts, change it, watch the suite
go red, restore, watch it go green - and the bed is ready for the remaining nine
with no setup.
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

---

## 8. Re-attribution: the plate-placement tests are the phone's, and the pattern behind two mis-attributions

This slice was a search, not a mutation, because the incident list **described
symptoms rather than locations** - and checking before mutating is what turned two
of the three attributions I was sent into corrections.

### 8.1 The pattern, as a finding about this audit's own inputs

**An incident list written from symptoms lands on different files than the brief
says, and a symptom is not a location.** Two of the three attributions given to me
for mutation did not match the files:

1. **`initiallyOpen`** - described as an assertion that "could never fail". It is a
   **log field name**, not an assertion, and it is already fixed (section 7.1).
   Mutating `ScrollToKeyTest.kt` for it would have produced a result about
   something else.
2. **"GoalsTest, RetirementTest on plate placement"** - checked, and **neither file
   contains a plate-placement assertion.** `GoalsTest.kt` asserts goal parsing and
   error mapping (`:49`, `:51-52`, `:60`, `:62-65`); `RetirementTest.kt` asserts the
   what-if's own words and constants (`:53`, `:59`, `:60-61`). Mutating either would
   have produced **a red or a green about goal parsing, recorded against an incident
   about plate placement - a fact about the wrong subject, which is worse than no
   fact.** So neither was mutated, and no row was written claiming otherwise.

**The credit, and the correction, belong to reading the source before spending the
budget.** The brief relayed the incident list as if it were a file list; it was not.
A `git show origin/main:<path>` read is what settled both, and that is the step
anyone re-attributing these should repeat.

### 8.2 Where the plate-placement tests actually are

Searched **both globs** for plate assertions. The answer is the **phone glob**:

- **`jarvis-client/app/src/test/java/com/jarvis/client/ui/parts/ScrollToKeyTest.kt`** -
  the walk over plates. The two passages that assert a plate arriving *after* the
  walk starts are `:130-144` (the holder opens, `brain-plate:people-and-things` is
  added to the list, and the count grows) and `:205-218` (the retry, where "only
  that second pass has the plate"). A plate that is absent is asserted at `:151-153`.
- **The desktop glob does NOT hold them.** `plate` appears in
  `jarvis-desktop/tests/*.mjs` only as **`deep.mjs`'s "deep plate"** - the Reading
  plate on the Memory tab (`deep.mjs:22`, `:44`, `:103`, `:108`, `:143`) - which is a
  different feature with a different subject.

**Which workflow was red, therefore, is settled by evidence rather than a guess: the
phone's.** The plate-placement tests live in `jarvis-client`, so the run that failed
them was `.github/workflows/jarvis-client.yml` - **the workflow that is not one of
the six required checks, and the one that `ci.yml` never invokes for a pull
request** (section 7). That is the same hole, seen from the other end: the incident
happened in the tests whose invocation is optional.

**And the useful surprise:** the suite holding the plate-placement tests is
**`ScrollToKeyTest` - the same suite I ran green** (`BUILD SUCCESSFUL in 1m 51s`,
section 7). So the two tests CI failed on are **runnable here right now**, on a
green baseline, which is exactly the starting point the next mutation needs.

### 8.3 What I did NOT do, and the limit on this pointer

**I did not mutate anything in this slice, and I did not confirm which two `@Test`
functions failed in that CI run** - I have no access to the historical run, only to
the assertions in the file. What is named above is the **file and the lines**, which
is what a correct pointer needs; the pairing of the failing tests to those lines is
an inference from the incident's description ("two tests about exactly that"), not a
measured fact, and it is labelled as such here.

**Sizing, two globs, separate and never added - unchanged:**
- **Desktop: two of 182 suites run, and both of those two mutated.**
- **Phone: one suite (`ScrollToKeyTest`) run and green; none mutated; no
  denominator claimed** for the phone's glob.

**Nothing in this document clears either glob.**
