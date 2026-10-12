# Defect register

Where the agents on this repo write down a defect **before** they touch it, so
two of them do not repair the same thing twice and nobody has to guess who is
on what.

Two files, and they must agree:

- `docs/defect-register.tsv` - the machine file. The checker reads this one.
- `docs/DEFECT-REGISTER.md` - this file. The open defects are in the table at
  the bottom.

## How to claim a defect (3 steps)

1. **Add one row to `docs/defect-register.tsv`**: `status` = `open`, your own
   name in `owner`, the `files` you are about to touch, the `evidence` you
   already have, and the `checkout` you are working in.
2. **Add the same `id` as one row of the table at the bottom of this file.**
   The two must list exactly the same open ids.
3. **Run the checker** from the repo root:

   ```
   py -3 tools/check_defect_register.py
   ```

   It must print `defect register OK: ...` and exit 0. It exits 1, naming the
   row, when a row is malformed, when two open rows claim the same file, when a
   row names a file that is not in the checkout, or when this file and the
   `.tsv` disagree about which defects are open.

When the defect is fixed: set `status` to `closed` in the `.tsv` (leave the
row - the history is the point) and delete its row from the table below.

## The exact TSV row format

Seven fields, separated by **TAB** characters (not spaces), one defect per
line, after this header row:

```
id	owner	claimed_at	status	files	evidence	checkout
```

- `id` - `DEF-` and a number, unique.
- `owner` - who is on it, or `unclaimed`.
- `claimed_at` - `YYYY-MM-DD`, or empty while `owner` is `unclaimed`.
- `status` - `open` or `closed` only.
- `files` - repo-relative paths separated by `;`. One path may sit in only one
  open row.
- `evidence` - the log line, the suite numbers or the test name that proves it.
  One line: no tabs, no line breaks.
- `checkout` - the worktree and revision the evidence came from.

An example row (every gap between two words below is one TAB):

```
DEF-003	some-agent	2026-10-11	open	tools/example.py	tools/example.py:41 returns before the check; test_example.py fails	x/some-branch @ 1a2b3c4
```

## Before reporting a NEGATIVE result, check the instrument

**A "nothing found" is the shape that most looks like a clean run, so it needs
the most proof. Before a negative result is reported, ask whether the step that
was supposed to happen actually happened.** The practical form of that rule:
**make the check say what it did, not only what it found.**

Three examples from 2026-10-11, all on real work, none of them hypothetical:

- **The plate.** `BrainScreen`'s source said a plate was drawn; the runtime
  dropped it from the list. Every check that read the source was green while the
  thing being checked for was never on screen. *A claim in the source is not
  evidence the thing is drawn.*
- **The zero-line probe.** `adb logcat -d -s JarvisRuntime:I` returned **0 lines
  in total** - not "no reconcile line". It read like "nothing wrong". *A probe
  that returns nothing is not evidence of absence; it is not evidence at all
  until the probe is shown to work.*
- **The reading that was nearly sent.** An armed watcher **did** catch the
  orphan condition at 16:05, then failed to find a Coming up row, fell back to
  tapping the Brain tab, and printed **"STILL POSTED"** - an instrument failure
  wearing a result's clothes. What stopped it being reported was one diagnostic
  line above the verdict: *"no Coming up row found"*. *A negative verdict is
  worth nothing if the step it depended on did not run.*

All three were caught by a line that **contradicted the verdict** rather than by
the verdict itself, which is why the check has to narrate its own steps. **The
paired rule for positive results:** a test that passes because it is looking at
nowhere or nothing proves nothing either - run the allowed case first and watch
it FIND what the forbidden case must not contain
(`docs/PIP-DESIGN.md` section 7.1 is that rule written out for one feature).

## Why this exists (history, not an open defect)

On the night of 2026-10-11 the same real bug was repaired several times over,
by agents that had no shared view of what the others were doing:

- **three** duplicate repairs of one test module,
- **three** for one patch anchor,
- **five** for one branch cleanup,
- **six** for one test file.

Every one of those was paid for twice. That is the whole reason this register
exists: one line in one file, before the work starts.

## Open defects

| id | owner | claimed_at | status | files | evidence | checkout |
| --- | --- | --- | --- | --- | --- | --- |
| DEF-002 | desktop feature-test agent | 2026-10-11 | open | `jarvis-desktop/src-tauri/src/windows.rs`; `jarvis-backend/jarvis_hud.py` | the Settings gear's path (`main.js:5233` -> `plain_errors.rs:312` -> `windows.rs:516`) builds the window on the command thread, and `/api/status` (`jarvis_hud.py:3181`) makes 3-4 live upstream probes while `/api/pending` (`jarvis_hud.py:3160`) is a DB read: measured 4598 ms against 9 ms at app 0.2.129 | wt-reg-2026-10-11 @ f8e96ab4 |
| DEF-003 | unclaimed | 2026-10-11 | open | `backend/jarvis_agent.py`; `backend/test_gate_touches.py` | a protected name **beyond character 1500** of the tool arguments is still never scanned: `jarvis_agent.py:1199` (`_gate_prompt`) and `:1384` (the plan-step line) cut the JSON at 1500 **before** the gate sees it, so a long argument can still hide a write to `jarvis_gate.py`. PR #260 closed only the half where the cut JSON did not parse | wt-verify2-2026-10-11 @ 621aad36 |
| DEF-004 | unclaimed | 2026-10-11 | open | `scripts/move-models-to-d.ps1` | section 8h called `Start-ScheduledTask` on `Jarvis Ollama - Everyday model` / `... Coding model` - names that do not exist (the real ones end ` (RTX 2060)` / ` (RTX 2080 Super)`) - with `-ErrorAction SilentlyContinue`, then exited 0. Both tasks show `LastTaskResult 0xC000013A` and the lanes stayed down for an hour. Fixed by PR #255 | wt-lanes-2026-10-11 @ bda48094 |
| DEF-005 | fix-265 | 2026-10-11 | open | `backend/test_power_switch.py` | `backend-windows` on PR #265 (job 114438288189) printed `FAIL  waking from standby loads the chat model at once` and then `KeyError: 'warm_up'` in `t_waking_loads_the_chat_model_again` (59 passed, 1 skipped, 2 failed). `set_mode` joins its work thread for `wait_s` only (1.5 s) and then answers 202 "Waiting for your approval", a body with no `warm_up` in it, so an in-place warm-up slower than 1.5 s is read as if it were the answer. Reproduced exactly on `.dsh-scratch/docs-drift`: fails at 2.0 s of warm-up, passes at 1.2 s - the boundary **is** the 1.5 s join. `main` carries the same racy test, so merging `main` alone does not fix it. Fixed by #265 (`45e35ec9`): the test passes `wait_s=30` and asserts `code == 200` | `.dsh-scratch/docs-drift @ 45e35ec9` |
| DEF-009 | unclaimed | 2026-10-11 | open | `tools/gen_phone_voice_cases.py`; `backend/test_voice_contract.py` | **LOW SEVERITY, and not a fix in itself** - a producer/harness property, not a wrong answer from the app. `render()` is not a function of the tree: it prints the voice-flow store (`turns`, `median_ms`, `worst_ms`, `timings`) that **its own run appends to**, so rendering it twice in ONE interpreter with the same root gives different output. Reproduced read-only on 2026-10-11 in `.dsh-scratch/voice-triage` at main `82c27ff7` (`main()` never called; the committed fixture never written): render() #1 = **1,054,760 bytes**, #2 = **1,218,390 bytes**, #3 = **1,296,386** - it does not settle at two. #1 has `"turns": 0, "median_ms": null, "worst_ms": null, "timings": []` for every step; #2 has `"turns": 10, "median_ms": 1.0, "worst_ms": 1.0` and the recorded timings; #3 has still more. So **`median_ms` is not nondeterministic** - it is a real measurement of the stand-in turns, at 1.0 ms - and the app is right; what is wrong is that the producer reads state its own execution appends to, so two renders in one process compare two different worlds. That is why #282's new property check had to spawn fresh processes: a workaround for this, not a property of the test. **An existing test does depend on the assumption:** `backend/test_voice_contract.py:512-514` imports the producer in-process and asserts `P.main(["--check"]) == 0` against the committed fixture - it passes today (738 passed, 0 failed on the owner's PC, 2026-10-11) only because nothing earlier in that process has recorded a turn at that root, i.e. **by the order of the suite, not by design**; one earlier recorded turn would add `turns`/`median_ms`/`timings` to the render and the compare would fail. **That is the consequence to act on: a passing suite here depends on suite order** - nothing in the check guarantees the store is empty at that point, it is empty only because of what runs before it, so a green run says nothing about the producer being a function of the tree, and a test added or reordered above it can turn it red for a reason that has nothing to do with the change. **What a fix would take** (not one line, so not done here): `render()` should own a throwaway root/state per call - the shape the other fixture generators use with temp dirs - or the stats should be pre-seeded deterministically, so the fixture is a function of the tree alone. Small and mechanical, but it changes a tool #282 currently works around, and the fixture may need regenerating | `.dsh-scratch/voice-triage @ 82c27ff7` |
| DEF-010 | unclaimed | 2026-10-11 | open | `jarvis-desktop/src/watch-badge.js`; `jarvis-desktop/src/main.js`; `backend/jarvis_screen.py` | CORRECTED 2026-10-11 FROM THE LEAD'S FIELD EVIDENCE - THE STOP WORKS; THE BADGE DOES NOT CLEAR, and that is the defect. First filed as "the Stop does not stop it", which was WRONG about its central fact. The state, read from GET /api/screen after the fact: state "ended", on false, paused null, left_s null, ended "owner", ended_words "you stopped it" - the backend had ALREADY ended the session before the read. The badge window was still on screen ten minutes later saying "Jarvis is watching - paused" and "Paused: one of Jarvis's own windows - 8 min left", its Stop still offering to stop nothing, while the number it showed counted down on its own. THE HARM IS THE SIGN ITSELF: a stale "Jarvis is watching" badge is a FALSE PRIVACY ALARM, in the one feature whose whole promise is a visible sign plus an instant stop, and the owner will act on it. CAUSE, TRACED - the badge is EVENT-ONLY after startup and never re-reads: watch-badge.js:156 listens for the screen-status event, :161 reads screen_status ONCE at startup, and render() re-schedules itself every 10 s while sign.on and current() decrements left_s LOCALLY from the last payload - which is exactly why a frozen payload looks alive, with a decreasing countdown. The desktop emits screen-status only when THE APP ITSELF makes the call (look.rs:551-552 run_watch -> on_status -> :468 emit_all), and on_status hides the badge only in its else-if-was branch after BADGE_ENDED_FOR, 15 s (look.rs:476-485). So ANY ending that does not come through this app's own screen_watch command - another client, the voice or quick "stop watching" path (screen_stop), the countdown running out on the PC, a watchdog - leaves the badge up for ever. Two readings of this field case remain, and each is testable: either the ending came from a path that emits nothing, or it came from the app and the event never reached the badge window's listener. THE DISCRIMINATOR IS ALREADY ON THE SCREEN: the bar and the tray follow the SAME on_status, so if the Jarvis bar still shows a watching sign, the app never learned; if the bar cleared and only the badge is stale, the event reached the app but not the badge window. Also noted: ended "owner" is the string ENGINE.stop() writes (jarvis_screen.py:1312-1314), so the ending was a POST /api/screen stop and not the hotkey, whose stop_everything() writes "stop_all" (:1649). ALREADY REFUTED, kept for the record: the paused state is not the cause (jarvis_screen.py:1310 and :1646 both end a PAUSED session) and the verb is accepted from anywhere (ANY_DOS :1814). NOT CHANGED AND NOT TO BE CHANGED: the pause rule and the sign's wording behaved correctly. WHAT A FIX MUST DO, and it is not done here: the badge must be able to learn the session ended WITHOUT this app being the one that ended it - a status re-read on the same 10 s tick it already runs, with the existing 15 s ended display then closing it. The live backend and the running prebuilt app were not reachable from the investigating branch. LIVE REPRODUCTION ADDED 2026-10-11, BOTH READ IN THE SAME MINUTE: the badge on screen said "Jarvis is watching - paused" and "Paused: one of Jarvis's own windows - under a minute left" while GET /api/screen in that same minute said state=ended, on=False, paused=, left_s=, ended=owner, ended_words="you stopped it". The session had been stopped at about 17 minutes left, and the sign counted all the way down to under a minute while the backend said ended the whole time. THE FIGURE THAT MATTERS, and it is arithmetic from the API rather than an estimate: the sign does not linger for BADGE_ENDED_FOR (15 s) - its own local arithmetic is the only thing driving it, so it lingers for the WHOLE REMAINING COUNTDOWN, and the largest session is 120 minutes (max_minutes in the same /api/screen answer). SO THE SIGN CAN CLAIM "JARVIS IS WATCHING" FOR UP TO TWO HOURS AFTER WATCHING STOPPED. That is why the fix's bound must be one tick plus the ended display (25 s) REGARDLESS of how much countdown was left, which is what tests/look-rules.mjs pins, and why the earlier wording "stale by a few seconds" would have understated it. AND PAST THE COUNTDOWN IT LINGERS INDEFINITELY - CONFIRMED LIVE 2026-10-11: with the backend at state=ended the minutes line bottomed out at "under a minute left" and the sign SIMPLY STAYED, still saying "Jarvis is watching - paused", and it is still on screen now. The failing build has NO close path at all: the frozen payload keeps watchOn(s) true, render() keeps re-scheduling itself every 10 s, and Rust's hide_badge only runs on the on-to-off transition that on_status itself observed. So "lingers for the remaining countdown" is TOO KIND - it does not clear late, IT DOES NOT CLEAR AT ALL, and it sits there claiming Jarvis is watching until the app is restarted. That is why the fix re-reads rather than merely re-rendering, and why its own closeBadge() matters: with it the sign is gone within one tick plus the ended display (25 s) whatever was left. THE STALE STATE IS NOT ONLY IN THE BADGE: the bar's own Watch with me control reported Off while the sign stayed up, so two of the app's own surfaces disagree with the backend AND WITH EACH OTHER - the badge is the worst one only because it is the surface a person sees. AND THE RUST HIDE IS TRANSITION-GATED AND ONE-SHOT, which is why pressing Stop again cannot clear a stray badge: look.rs:465-485 computes was = ON_HERE.swap(on, ...) and reaches hide_badge ONLY inside "else if was", then re-checks !on_here() 15 s later. Once the app's own flag has settled to false there is no transition left to observe, so no hide is scheduled at all - no retry, no idempotence, and a second Stop cannot re-trigger it. DATING THE PATH, so the running build can be judged rather than guessed: fn hide_badge and BADGE_ENDED_FOR were BOTH introduced on 2026-09-29 by 5fbf0371, the original "Watch with me" commit - so any build that has the badge at all also has this path, which dates the running app after it. The repository's version field cannot answer the question either: tauri.conf.json and Cargo.toml both still read 0.2.0, so 0.2.140 is a build number that does not come from it. | `.dsh-scratch/watch-stop @ 32ae9abe` |
| DEF-011 | unclaimed |  | open | `docs/README.md`; `tools/check_docs_map.py` | STRUCTURAL DEFECT, not a code bug, and the fix is a SHAPE change rather than a patch. docs/README.md carries the number of documents and the total size of docs/ as HAND-TYPED values, and every docs pull request edits those same lines - so any two docs PRs conflict BY CONSTRUCTION. MEASURED 2026-10-11, and this is arithmetic rather than opinion: between two consecutive runs of tools/check_docs_map.py on ONE tree, the byte figure moved 8,417,863 -> 8,417,870, because WRITING THE FIGURE INTO THE PAGE CHANGED THE PAGE. A hand-typed value that changes when you write it is a value no pull request can ever get right and leave alone. THE COST, counted from tonight alone: the page or the register beside it was touched or re-synced by #291, #296, #302, #310, #312, #320 and #325; three of the day's conflicts were this page alone (#310's and #304's among them); and the working rule became 'take main's page and let the checker give the numbers', which is a workaround for a missing generator. THE FIX SHAPE: have the checker PRINT the two numbers and have the page QUOTE a single generated line, so no docs PR edits a number at all - the checker already computes both (it prints 'N documents' and 'B bytes' and compares them against the page), so this is a generator plus one quoted line, not a new measurement. NOT DONE YET - registered here so it is not lost - and the same reasoning is in #310's commit message: 'it stays a conflict magnet until the count is generated rather than typed'. UNTIL THEN: a docs PR takes docs/README.md from main and lets the checker give the numbers, and a re-sync is worth one push only when a merge is REFUSED. | `.dsh-scratch/def011` |
