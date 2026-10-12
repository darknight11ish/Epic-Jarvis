# A known flake: chat-thread.mjs's crisis-pair check (2026-10-11)

**Known flake. Not reproducible outside CI, and load does not tip it locally.
Do not fix it by weakening the assertion.**

* **Suite and check**: `jarvis-desktop/tests/chat-thread.mjs`, *"the bar: a crisis
  question and its answer never join the thread or the model's history"*; the
  failing sentence is its last assertion, *"the crisis pair was re-sent to the
  model"*.
* **Where it was seen**: #308, CI run **38206724001**, job **114671731662**, on
  **`791dac08`** - `##[error]1 desktop suite(s) failed: chat-thread.mjs`, with
  **180 of 181 passed**, and **`chatbot-api-keys.mjs` passed in the same run**.
* **Local**: **15 passes, 0 reproductions** - 6 clean on `e59a243d`, 3 on the very
  commit CI failed (`791dac08`), and 6 concurrent copies under load. #308's diff is
  7 files and **cannot reach the assertion**.
* **A RECURRENCE, NOT A FIRST SIGHTING.** The suite's own `ask()` docstring
  (`:92-112`) already records this failure with this cause, dated **2026-10-08**:
  a question typed into a page still finishing the previous answer is DROPPED
  (`main.js`'s `send()` refuses while `state.inFlight || state.abort`), and *"a
  fixed sleep cannot tell 'not sent yet' from 'never will be'"* - so the suite
  reports *"the crisis pair was re-sent to the model"* when in truth the third
  question was never sent at all. It passed locally on a fast machine and failed
  on a loaded runner then, and did exactly that again on 2026-10-11.
* **What changed on 2026-10-11 - a LATENT-DEFECT CLEANUP, not a proven fix.**
  The retry loop's budget went from about one second (40 tries x 25 ms) to about
  five (200 tries x 25 ms), polling the **same observable** (`K.turnsSent` - the
  thing that tells "not sent yet" from "never will be"), and the fixed 250 ms
  sleep at `:137` is now `await page.locator(".thread-reads-from").first().waitFor()`,
  which waits on the exact element the assertions then read. **The assertion is
  unchanged and nothing was weakened.** Nobody has a failing run that proves this
  fixes the flake, and this note does not claim it does.
* **Is the claim underneath safe? Read, not assumed - YES, BY CONSTRUCTION.**
  `main.js:3850-3868` computes `crisisRoute(state.turnRoute)` once and puts BOTH
  writes - `state.conversation` (what the model is re-sent) and `state.thread`
  (what the page shows) - inside ONE `if` behind `keepsInThread(...)`
  (`chat-history.js:342`), synchronously. There is no window in which one holds
  the pair and the other does not, so the check's read order is not load-bearing.
  **Two limits, stated rather than implied:** it covers the page's thread and the
  recorded `stream_chat` payloads, **not the PC-side History path**; and the
  single point of failure is **the route header arriving** - `crisisRoute(undefined)`
  is `false`, so a crisis turn whose route never reached the page **would** be
  kept. That is a PC-to-page contract, flagged here as a **follow-up, not a defect
  found in this investigation**.
* **Do not fix it by weakening the assertion.** A crisis pair must never be
  re-sent. The flake is in **when** it is observed, not in what it claims.
