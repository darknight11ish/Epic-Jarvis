# Report 01 (audit), agent a54af994, 2026-09-29T08:18Z

> **What it was asked** (first 600 characters of the task): Repo /home/user/Epic-Jarvis at origin/main (79a36545). Do NOT edit files. Bug-hunt the NEWEST backend code: backend/jarvis_plan.py, backend/jarvis_phone_notifications.py, the chatbot driver modules (find them: `ls backend | grep -i -e chat -e driver -e adapter -e compare -e support`), the pairing/device-key code (jdk1 keys, SHA-256 store, QR/backup code, rate limits: 10 min, one use, 3 wrong tries), jarvis_second_card.py third-lane code, Jarvis Live / screen-watch backend modules, forget-range, money-limit code, and the propose_plan wiring in the agent patch. Prove each bug against the source 

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

I found one real bug, in the propose_plan wiring, plus one minor config bug. I reproduced both. The other areas I read turned up nothing provable. No files were edited; my scratch script is in the scratchpad.

## 1. Plan card: a chain of "result-filled" steps skips its own card and re-runs the wrong step (severity: high, approval bypass / wrong action)

**Where:** `backend/jarvis_agent.py`, `_plan_step_dispatch`, about lines 844-985. The cache is `cache: dict = {}   # id(step) -> ...` with `key = id(step)`. It works together with `backend/jarvis_plan.py` `run()`, around line 291.

**Cause:**
- `run()` builds a temporary copy for every step that has `from_step`: `step = fill(step, results.get(step.from_step, ""))`. That copy is a new `PlanStep` object.
- The loop variable rebinds on the next iteration, so the previous filled copy is freed.
- `_resolve` caches `(tool, state, checked_args, verdict)` under `id(step)` and does not keep the step object alive.
- CPython reuses the memory address of freed objects, so the next filled step gets the same `id`.
- That step hits the cache entry of the previous filled step. Its own tool, arguments and approval card are skipped.
- `run_step` then executes the earlier step's `tool.execute(checked_args, state)` again, with the earlier step's already-approved verdict.

**Trigger:** the model proposes a plan where two or more consecutive steps use `from_step`, for example step 2 uses `{{step 1}}` and step 3 uses `{{step 2}}`. `propose()` allows this. The feature is off until `jarvis_plan.enabled()` passes, but the code path is live once it is on.

**Proof (ran it):** I built four steps with the real `_plan_step_dispatch` and the real `jarvis_plan.run()`, using fake tools t1, t2 and t3:

| Step | Tool | Marked |
|---|---|---|
| 1 | t1 | safe |
| 2 | t2 | `from_step` = step 1 |
| 3 | t3 | `from_step` = step 2 |
| 4 | t1 | `from_step` = step 3 |

- Executions: `[('t1', {'q': 'one'}), ('t2', {'q': '{"ok": true, "v": "Rt1"}'}), ('t2', {...same...}), ('t2', {...same...})]`
- Cards raised: 2 (step 1 and step 2 only).
- Steps 3 and 4 never got the "own card" that the plan card promised (condition 2). Instead t2 ran three times, and t3 never ran.

**What the owner sees:** steps 3 and 4 in the run result show step 2's action repeated. That could mean an email or a smart-home action fired again, or a wrong action run under an old approval, with no fresh card.

**Fix:** key the cache by the step's position (pass an index) or by `(tool, json of args)`. Alternatively, store the step object itself in the cache tuple so its `id` cannot be reused while the entry lives. The simplest change is to add `step` as a fifth element of the tuple and compare `cached[4] is step`.

**Test gap:** the existing `test_agent_plan_wiring.py` never chains two `from_step` steps.

## 2. Second card: a configured `port` equal to 11436 collides with the third lane (severity: low, misconfiguration only)

**Where:** `backend/jarvis_second_card.py`, `_third_port()`, lines 823-832. It falls back to `DEFAULT_THIRD_PORT` without checking it against `_port()`.

**Proof (ran it):** with `[second_card] port = 11436`, `_port()` returns 11436 and `_third_port()` also returns 11436. The second and third Ollama copies would then fight over one port. The function's docstring promises "never … `_port()`'s own value".

**Fix:** when the fallback equals `_port()` or `MAIN_OLLAMA_PORT`, pick the next free port.

## Areas checked with no proven bug

- **Pairing and device keys (`jarvis_devices.py`):**
  - Key checks use `hmac.compare_digest`.
  - A `jdk1.` key never falls through to the old shared-key check.
  - Removed devices are refused, and `_StreamGuard` cuts open streams.
  - The 10-minute expiry uses a monotonic clock, and `_tick` uses `>=`, so there is no off-by-one.
  - 3 wrong tries burn the session, and a second claim counts as a wrong try.
  - The key is handed over once (state moves to `done` in the same lock).
  - Registry writes are atomic and only a SHA-256 of each key is stored.
  - The only weakness is that a mesh peer can burn a session (a denial of service), which the design already accepts.
- **`jarvis_phone_notifications.py`:**
  - The off switch withdraws a waiting card under `_SWITCH`.
  - Turning it on needs tier `ask` plus an approved outcome.
  - The settings file fails closed.
  - A non-dict POST body gives a 503 instead of a 400, which is cosmetic.
- **`jarvis_plan.py` itself:** taint refusal, the `MAX_STEPS` cap, the `{{step N}}` slot validation and the stop/pause checks are correct. The bug in item 1 is in the agent wiring, not here.
- **`jarvis_forget_range.py`:**
  - Every fact and chat is re-checked against the frame between the card and the apply step.
  - Only tier `ask` with an approved outcome is accepted.
  - Undo state is held under `_SWITCH`.
  - The chat log's lock is an `RLock`, so the VACUUM inside `take_out` cannot deadlock.
  - A hypothetical unrecoverable case exists if `put_back` fails before its `try` block, but I did not prove it and am not reporting it.
- **Money limit (`jarvis_chatbot_api.py`):**
  - It fails closed on an unreadable file, and the key is pinned to the preset host.
  - Redirects are refused, and the per-answer cap is applied.
  - Spend is not counted for answers that are too large or fail to parse, or for timed-out requests. That is an under-count, not a bypass, so I did not report it.
- **Chatbot routes, support checks, hand-off and Live:** these read as correct.
  - Token and origin checks run before every route.
  - Card numbers are checked with the Luhn algorithm.
  - Hand-off pictures and input re-check the window host before and after each action.
- **`jarvis_screen.py`:** no route reaches it yet, and its pause rules fail safe.
- **Not run:** I could not run the module tests because `pytest` is not installed here. I used direct `python3` scripts instead.

Scratch script: `/tmp/claude-0/-home-user-Epic-Jarvis/9107f2ad-de34-5a00-97f9-3a345fb31dd0/scratchpad/idreuse.py`
