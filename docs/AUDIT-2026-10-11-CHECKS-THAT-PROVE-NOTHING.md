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
| Playwright | **not installed in this environment** (`jarvis-desktop/node_modules` absent). The desktop `.mjs` suites therefore could **not** be mutated or run here. That is a fact about this audit, not about them |
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

1. **No desktop `.mjs` suite was run or mutated**: Playwright is absent here
   (`jarvis-desktop/node_modules` does not exist). The CI glob `tests/*.mjs`
   (`ci.yml:145`) is therefore **un-audited by mutation** in this document. The
   five incidents in the brief include at least two that live on that side
   (`initiallyOpen`, `rows` -> `composed`), so this is the largest gap - and it
   is a gap in *my evidence*, not a statement that those suites are sound.
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
this class does not look at it. **The largest gap is in my evidence, not in the
repository**: the desktop `.mjs` suites could not be run or mutated here because
Playwright is absent, so they remain unaudited and should not be read as cleared.
