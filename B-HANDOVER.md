# B — the phone's own control for raising a money limit: handover

**Status: NOT STARTED. Nothing is written on `feat/phone-limit-control`.** This file
is untracked and is deliberately not in any PR. It exists so the next agent starts
from verified facts instead of a summary.

Worktree: `.dsh-scratch/phone-limit-control` — **`c485a142`, clean, 0 commits ahead
of main.** It is already re-synced; the `JarvisRuntime.kt` collision is resolved.

---

## THE BOUNDARY — read this first, it is the whole task

**The phone never decides for itself that it may raise.** It asks the PC, the PC
answers `can_change` / `can_change_prices`, and the control exists **only where the
PC said yes**. Where the PC said no, the phone shows **the PC's reason and the
signed-approvals path** — never a button that 403s.

**If any part of this starts to look like "let the phone approve it after all",
stop and tell the lead.** That is the one outcome that is not acceptable, and it is
why this task has been held rather than rushed.

A control that 403s is worse than no control. That condition is now satisfied
(#314 merged: the phone may raise a limit with its own fingerprint), which is why
B was unblocked.

---

## THE CORRECTION THAT MATTERS — piece 2's path is wrong in the recon

The recon says *"regenerate `contract/chatbot-cases.json`"*. **There is no such
path.** The generator writes **two** files:

```
tools/gen_chatbot_cases.py:14  ->  jarvis-desktop/tests/fixtures/chatbot-cases.json
tools/gen_chatbot_cases.py:15  ->  jarvis-client/app/src/test/resources/contract/chatbot-cases.json
```

and **`ChatbotTest.kt:30` loads it off the CLASSPATH** as `contract/chatbot-cases.json`
— i.e. **the `jarvis-client/app/src/test/resources/contract/` copy**. Its own error
message says so: *"contract/chatbot-cases.json is missing - run
tools/gen_chatbot_cases.py"*.

**Why this would have cost a red suite:** piece 3 requires the phone's `WORDS` and
the regenerated fixture in the same commit, and the suite reads the **client**
resource. An agent following the recon literally would look for a repo-root
`contract/` file, not find it, and could **hand-edit the desktop fixture instead —
keys matching, values differing, red suite** — which is exactly the failure the
piece-3 warning exists to prevent.

> **BOTH FILES COME FROM THE GENERATOR. NEITHER IS HAND-EDITED. EVER.**

---

## THE ORDER — each step is there for a reason

1. **`backend/jarvis_chatbot_routes.py` AND `jarvis-backend/jarvis_chatbot_routes.py`
   in ONE commit.** The base twin already carries the same sentence, so editing the
   repo copy alone turns `test_base_matches_repo.py` red (another agent hit exactly
   that today: 234,154 against 236,577 bytes). **Run `backend/test_base_matches_repo.py`
   FIRST — it is green at this revision (20 passed, 0 failed).**
   - The sentence is **not the phone's to change**: `money_pc_only` is defined on the
     PC at `backend/jarvis_chatbot_routes.py:276`, and `Chatbot.kt` says these are
     *"the words, the PC's own"*. **Add exactly the keys the control uses and no more.**
2. **`tools/gen_chatbot_cases.py`** — regenerate **both** fixtures (see the correction
   above). Never hand-edit either.
3. **The phone's `WORDS` and the regenerated fixtures in the SAME commit.**
   `ChatbotTest.kt:47` asserts `assertEquals(w.keys, Chatbot.WORDS.keys)` **and every
   value**, so keys matching with one value differing is a red suite. The PC's map
   changes, the fixture is regenerated, the mirror follows — in that order.
4. **`WRITE_PATHS` in `net/Chatbot.kt` plus its one-entry delta test.**
   Today (`Chatbot.kt:52`):
   ```kotlin
   val WRITE_PATHS = setOf(START_PATH, STOP_PATH, LIMITS_PATH, COMPARE_START_PATH, COMPARE_STOP_PATH)
   ```
   There is **no `MONEY_PATH`**. Note `LIMITS_PATH = "/api/chatbot/limits"` already
   exists and is a **different** route. `WRITE_PATHS` is a deliberate allow-list —
   *"the only routes `chatbotWrite` posts to"* — and `ChatbotTest.kt` checks the set.
   **It gains EXACTLY ONE entry, and the allow-list property is what the test pins.**
   A route not listed is still refused. **Widening the set for convenience is the one
   change here that would be a security change rather than a feature.**
   - **Piece 4 does NOT ship alone.** Adding a path with no caller widens a security
     allow-list and puts nothing on the other end of it — the mirror image of the
     button that 403s. **Piece 4 ships with piece 5 or it does not ship.**
5. **`JarvisRuntime.kt` — read the file AS IT IS NOW.** It already carries #323's
   change: `:4003 if (approve && item.pcOnly)`, `:4007 APPROVE_ON_PC`. Add the read
   and raise wrappers mirroring the `chatbotStatus` / `chatbotWrite` pair (~`:7275`).
   **Do not edit around a description of this file from before #323.**
6. **`ui/screens/ChatbotPlate.kt`** — the control at **`:732`**
   (`val money = Chatbot.moneyLine(c)`) and **`:738`**
   (`Text(Chatbot.MONEY_PC_ONLY, ...)`), **existing only where the PC said
   `can_change`**.

Also needed: **`net/JarvisApi.kt`** — the `GET /api/chatbot/money` read beside
`chatbotStatus` (~`:2146`), and the money-view model and parser in `Chatbot.kt`.

---

## VERIFIED ANCHORS (checked at `c485a142`)

| thing | where |
|---|---|
| the PC's own sentence | `backend/jarvis_chatbot_routes.py:276` `"money_pc_only": (...)` |
| the base twin | `jarvis-backend/jarvis_chatbot_routes.py` (exists, same sentence) |
| the generator | `tools/gen_chatbot_cases.py` (writes two fixtures, `:14` and `:15`) |
| the contract test | `ChatbotTest.kt:47` `assertEquals(w.keys, Chatbot.WORDS.keys)` |
| the fixture loader | `ChatbotTest.kt:30` classpath `contract/chatbot-cases.json` |
| the allow-list | `net/Chatbot.kt:52` `WRITE_PATHS` |
| the plate | `ui/screens/ChatbotPlate.kt:732` and `:738` |
| #323 already present | `JarvisRuntime.kt:4003`, `:4007` |

---

## THE TEST THAT MUST NOT BE WEAKENED

`WRITE_PATHS`' delta test pins **the allow-list property**: the set gained exactly one
entry and a route not in it is still refused. **If a change makes the test easier to
pass rather than the property stronger, that is the wrong change** — the same rule
that kept the `chat-thread.mjs` crisis assertion intact tonight.

---

## DISCIPLINE

- `git show origin/main:<path>` for every line — **never `git grep`**, which answers
  "what does my branch say" while reading like a claim about main.
- **`ci.yml` is the lead's. `run_suites.py` never.**
- **`backend/test_base_matches_repo.py` before pushing if `backend/` is touched at
  all** — editing a shipped module is a two-file change even when it looks like one.
- **Do not push while a run is in flight.** A push to an existing PR's branch cancels
  its run and re-queues behind everything else.
- **`git diff --stat origin/main...HEAD` before opening a PR — THREE dots.** Two dots
  compares tips and reports main's newer work as your deletions (measured on a real
  branch tonight: 18 files/−1644 with two dots against 5 files/−9 with three).
- One PR. If it cannot be finished, **stop and say so** — eight agents have declined
  this task on capacity and every one was right. A verified recon with nothing written
  has beaten a half-built security change every time.

---

## WHY IT KEEPS BEING DECLINED, SAID PLAINLY

Not because the task is unclear — the order above is clear and correct. Because it is
**six pieces across two Python files, a generator, two JSON fixtures, four Kotlin
files, an API read and a delta test**, and the security property (`WRITE_PATHS` gains
exactly one entry) must not be half-crossed. **A change that must not be half-crossed
waits for someone with the budget to cross it once.**
