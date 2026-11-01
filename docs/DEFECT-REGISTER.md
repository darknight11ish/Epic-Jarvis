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
DEF-006	some-agent	2026-10-11	open	tools/example.py	tools/example.py:41 returns before the check; test_example.py fails	x/some-branch @ 1a2b3c4
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
| DEF-017 | learning-lane | 2026-10-28 | open | `backend/jarvis_auto_learn.py`; `jarvis-backend/jarvis_auto_learn.py`; `backend/test_learning_after_pass.py`; `jarvis-backend/jarvis_extract.py` | REAL DEFECT, FOUND 2026-10-27/28 IN THE LIVE LEARNING LANE AND REPRODUCED HERE. `_init_notes()` migrated `auto_learn_notes` with three unguarded `ALTER TABLE` statements, and its `CREATE TABLE IF NOT EXISTS` omitted `topic_ask` - so a FIRST-RUN database ran an ALTER on its very first card. Two writers reach `_init_notes` on the same table: `after_pass` -> `_note_card` (`jarvis_auto_learn.py:1799` at origin/main `44fa39a58`) and every `/api/memory/pending` read -> `card_notes` (`:1820`). A second writer that adds the column between the first one's `PRAGMA table_info` (`:1778`) and its `ALTER` (`:1780`) makes the loser raise `sqlite3.OperationalError: duplicate column name: sensitive`. REPRODUCED deterministically, not reasoned: `_init_notes:1780` <- `_note_card:1799` <- `after_pass:2067`, the pass returns `{'saved': [], 'cards': {}, 'error': 'OperationalError'}`, `note_failure` (`:2104`) records `last_error` `after_pass: OperationalError`, and `passes` never moves - exactly the live counter shape. THE LIVE COUNTERS ARE STALE AND SAID SO: `~/.openjarvis/learning-stats.json` was last written 2026-10-10 20:03 local (eight `learning.failed` events inside six seconds; `last_error_at` 1791687798.5), the eight audit lines carry only `{where, kind}`, and today's `memory.db` has NO `auto_learn_notes` table - the store was re-seeded 2026-10-15, after those events. THE FIX IN THIS PR: a guarded `_add_note_column()` that swallows ONLY `sqlite3.OperationalError` whose message names a duplicate column (everything else re-raises, and the suite pins that), plus `topic_ask` in the CREATE so a new install runs no ALTER at all. REGRESSION TEST: `backend/test_learning_after_pass.py`, 11 checks - 6 passed / 5 failed against origin/main `44fa39a58`, 11 passed / 0 failed with the fix, and one check is the guard that "database is locked" and "no such table" still raise. SECOND HALF OF THE SAME ROW, the swallowed exception: `jarvis_extract._local_llm`'s `except Exception: return None` threw away the HTTP status and the body, so the learner could only print "reached no model at http://127.0.0.1:11436 ... Is it pulled?" while Ollama listed AND loaded `qwen3.5:9b`. It now records a CLOSED-WORLD reason - exception class, HTTP status, wall duration and Ollama's own `done_reason`, never a prompt word or an answer word - keeps returning None, and hands the reason to `jarvis_auto_learn.note_model_failure`, which `/api/memory/learning` already reads back, so no HUD change is needed. ONE AUTHORIZED BOUNDED LIVE DIAGNOSTIC (2026-10-27 23:46 local, no user data, one POST, no retry): `POST /api/generate` to `127.0.0.1:11436` with the one-word prompt "ok", `num_predict` 1, returned HTTP 200 in 1.969 s with an EMPTY `response` and `done_reason` "length" on a lane whose `/api/ps` reports `qwen3.5:9b` loaded (9.86 GB VRAM) - so "Is it pulled?" is measurably the wrong question, and an empty answer (not only an exception) is a reason worth recording. Raw evidence: `.dsh-scratch/RED-PR-LANE-2026-10-28/learning/POST-DIAGNOSTIC.txt`. NOT DEPLOYED: the owner's PC still runs the old modules until `scripts/apply-patches.ps1` is re-run, and the row stays open until it is. | fix/learning-after-pass-notes-migration @ `1452f4525` plus this PR's later commits (worktree `.dsh-scratch/RED-PR-LANE-2026-10-28/wt-learning`) |
| DEF-022 | sec-deploy | 2026-10-30 | open | `jarvis-client/app/src/main/java/com/jarvis/client/data/Security.kt`; `jarvis-client/app/src/main/java/com/jarvis/client/ui/approval/ApprovalCard.kt`; `jarvis-client/app/src/main/java/com/jarvis/client/net/SignedApproval.kt`; `jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt`; `jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/HomeScreen.kt`; `jarvis-client/app/src/test/java/com/jarvis/client/ApproveAsksFingerprintTest.kt` | PHONE CARD'S NEW LINE PROMISES A PROMPT THE OFFER PATH DOES NOT SHOW (#1004), FOUND 2026-10-30. The owner's 2026-10-30 ruling adds a sentence under Approve saying what the press will ask for; Security.kt:230-240 approveCheckWords reads only approvalNeedsCheck(s, item) and s.method, so a risky card gets 'Approve asks for your fingerprint or PIN' regardless of whether signed approvals are on, and ApprovalCard.kt:322-323 (drawn at :856) draws it whenever there is a live Approve. But with signed approvals OFF, SignedApproval.pathFor (:295-304) returns Path.OFFER (:299), and MainActivity.approveItem (:4351-4374) sends that path straight to SignedApproval.noticeFor (:4372) without confirmed() - the local biometric prompt - so pressing Approve shows 'Nothing was approved. Risky approvals from this phone need to be signed with your fingerprint or PIN, and signed approvals are not turned on yet.' (OFFER_WORDS :312-314) and sends nothing. No approval leaks (nothing is sent), but the card's sentence is false for that press. SMALLEST FIX: give the line the signed-approval state and word the OFF case 'once signed approvals are on', or let the offer notice be the only sentence. TEST: ApproveAsksFingerprintTest adds the three signed-approval states crossed with a risky item and asserts the sentence matches what Approve actually does (prompt vs offer).  FIXED IN CODE (branch fix/def-022-phone-card-promise-2026-10-31; not pushed, no PR yet): THE LINE NOW KNOWS THE SIGNED-APPROVAL STATE. SecurityRules.approveCheckWords takes the state (SignedApproval.State?) next to the Security settings and the card; for a RISKY card it asks SignedApproval.pathFor's own answer - the SIGNED path and the PLAIN path really run this phone's check, so they keep "Approve asks for your fingerprint or PIN." (or "... your fingerprint." under Fingerprint only), while the OFFER, OFFER_AGAIN and WAITING paths show no prompt and now say so instead: "Approve asks you to turn signed approvals on first. Risky approvals from this phone need your fingerprint or PIN once they are on." / "...on again first: this phone's approval key stopped working." / "...answer the card that turns signed approvals on first.". A null state (not read / read failed / not paired) is honestly the prompt case, because the PLAIN path still runs the local check. The state is read once in MainActivity only while Home is the screen and a risky card that can take the signed path is waiting (it uses the existing GET /api/devices read - no new route, card, permission or behaviour), carried in HomeState -> HomeScreen -> ApprovalCard. Non-risky and EVERY cards are unchanged (the PLAIN prompt always runs for them). The card's promise is now true for every press. TEST: ApproveAsksFingerprintTest grew to 9 tests; the new "the sentence matches what Approve really does, on every signed-approval state" crosses every SignedApproval.State plus null with a risky item and asserts the words match SignedApproval.pathFor (prompt words iff the path really prompts); "a signed-approval state only changes a risky card's line"; and "the signed-approval state really reaches the card's line" pins the MainActivity -> HomeState -> HomeScreen -> ApprovalCard threading. PROVEN TO BITE: with the state branch reverted the new test fails exactly as the defect says - state=OFF path=OFFER words="Approve asks for your fingerprint or PIN." - and passes with the fix. JVM: 3,057 tests, 0 failures, 0 skipped (277 suite files). docs/ARCHITECTURE.md's paragraph on this line was corrected to name the signed-approval state. ON-SCREEN CONFIRM STILL OWED: this row stays open until the owner sees a risky card's line with signed approvals off on a phone (no live install here; the state read is device-dependent).| fix/def-022-phone-card-promise-2026-10-31 (worktree .dsh-scratch/DEF-022-2026-10-31/wt, base origin/main @ 5a1e84c21) |
| DEF-025 | lead | 2026-10-31 | open Pass 10 reproduced it on the OLD build 0.2.3326: the drawn (hidden) row and a TextView carrying the full title sat in the same accessibility dump; the fix (PR #1026, merged main 5a1e84c21) is on main and the row stays open for the owner's on-device confirm. | `jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/CalendarPlate.kt`; `jarvis-client/app/src/main/java/com/jarvis/client/net/Calendar.kt`  `jarvis-client/app/src/test/java/com/jarvis/client/CalendarHiddenA11yTest.kt`| PHONE'S HIDDEN-LISTS STATE DRAWS "(hidden)" BUT THE ACCESSIBILITY TREE STILL CARRIES THE FULL EVENT TITLE (field test 2026-10-31, pass 9 P8; a FINDING, not a claimed-exploited defect). Measured on phone 0.2.3303 (versionCode 1000003303), with "Hide memory lists and chat history" ON: one clearly-named test event ("ZZ field test delete me", 09:00) was created and the calendar row drew "09:00 / (hidden) / Edit / Delete" with place and recurrence suppressed (CalendarPlate.kt:562 `if (hidden) Calendar.HIDDEN_TITLE else event.title`, HIDDEN_TITLE "(hidden)" at net/Calendar.kt:116); BUT the same accessibility dump (p9-cal-saved.xml) also carries a TextView node index 49 with text "ZZ field test delete me, Saturday 31 October at 09:00." (bounds [36,1883][1033,1922], package com.jarvis.client). The screen is FLAG_SECURE, so the pixels cannot be checked, and the root cause (which composable emits that node, and whether it is visible or only TalkBack-readable) is NOT determined. Needs the owner's own check to decide the fix. Evidence: .dsh-scratch/FIELD-TEST-2026-10-31/pass9/NOTES.md P8, p9-cal-saved.xml. NOT FIXED.  FIXED IN CODE (local branch fix/def-025-hidden-a11y-2026-10-31; not pushed, no PR yet): THE ROOT CAUSE IS FOUND, IN SOURCE - the extra accessibility node was NOT the event row (the row already drew "(hidden)"), it was the PC's own write-confirmation sentence drawn under the screen by CalendarPlate.kt's `write` -> `said` line. backend/jarvis_local_calendar.py's _said() builds "<title>, Saturday 31 October at 09:00." (jarvis_local_calendar.py:836-837: return f"{ev['title']}, {_when_words(ev)}."), and the plate assigned that sentence unconditionally, so with titles hidden it both echoed the title on screen and exposed it as a TextView to TalkBack - exactly the node the field test recorded. THE FIX, in the phone app: Calendar.displaySaid (net/Calendar.kt) is now the only path from a write's sentence to the screen; while hidden it never returns the PC's words and always returns one fixed title-free line (HIDDEN_SAVED / HIDDEN_DELETED / HIDDEN_NOT_SAVED), and the hidden title Text and the hidden said Text both clearAndSetSemantics to the withholding words, so the title cannot sit in text, contentDescription or any other property of a semantic node. A delete is passed deleted = true so the line says "Deleted.". The delete confirmation (already title-free while hidden) and the row's place/recurrence suppression are unchanged and pinned. TEST: jarvis-client CalendarHiddenA11yTest - the field test's exact sentence is asserted absent from every hidden line, the visible case still returns the PC's sentence unchanged, and the plate's guard/clearAndSetSemantics structure is pinned. ON-DEVICE CONFIRM STILL OWED: this row stays OPEN until the owner checks on a phone that TalkBack no longer reads the title (the screen is FLAG_SECURE, so the pixels were never readable in the field test either). RELATED, NOT FIXED HERE: the desktop HUD draws the same reply.said in its calendar banner (jarvis-desktop/src/jarvis_hud.html:11028), so the same echo exists on the PC side under lock/hidden lists - a separate lane. MERGED 2026-10-31: PR #1026 landed on main as 5a1e84c21 (fix commit 74eda3f12, 2026-10-31 09:09:13 -0700; changed jarvis-client Calendar.kt / CalendarPlate.kt / CalendarHiddenA11yTest.kt plus this register row) - the "local branch, not pushed, no PR yet" words above describe the pre-merge state. The row stays OPEN for the OWNER'S ON-DEVICE CONFIRM only: press Show + fingerprint, hide the lists, create and delete one calendar event, and check TalkBack no longer reads the title; then close it. The desktop HUD calendar banner is a separate lane (DEF-026, not on this checkout).| origin/main @ 5a1e84c21 (PR #1026 merged, fix 74eda3f12; on-device confirm owed) |
| DEF-026 | phone-jobs | 2026-10-31 | open | `jarvis-desktop/src/jarvis_hud.html`; `backend/jarvis_hud.html`; `jarvis-backend/jarvis_hud.html`; `jarvis-desktop/tests/hud-calendar.mjs` | DESKTOP HUD ECHOES A HIDDEN CALENDAR TITLE IN ITS WRITE BANNER (the desktop twin of DEF-025; field-test pass 9 P8 plus code reading, 2026-10-31). jarvis-desktop/src/jarvis_hud.html:11028 before this branch drew `banner.textContent = state.said`, and the three write handlers set `state.said` from `reply.said` (:11573 add/update, :11612 and :11734 delete). That sentence is the PC's own `jarvis_local_calendar._said()`: `f"{ev['title']}, {_when_words(ev)}."` (backend/jarvis_local_calendar.py:836-837), so it NAMES the event; the fresh-confirmation branch runs BEFORE the locked-read branch (`read.hidden`, :11036), so with App lock / "Hide memory lists" on the title the grid had just redacted appeared under the calendar. The phone's half was DEF-025 (fixed in branch fix/def-025-hidden-a11y-2026-10-31). FIXED IN CODE on this branch: `bannerSaid()` (jarvis_hud.html, beside the existing `wordsHidden()` flag at :10810) returns the PC's sentence only while titles are visible; while `wordsHidden()` it returns one fixed title-free line - "Saved. Its words stay hidden while your memory lists are hidden." or "Deleted. Its words stay hidden while your memory lists are hidden." - and an unknown write kind FAILS CLOSED to the Saved line; the three write sites set `state.saidKind` saved/deleted and the banner calls `bannerSaid()`. The three vendored copies (jarvis-desktop/src, backend/, jarvis-backend/) are kept byte-identical. TEST: jarvis-desktop/tests/hud-calendar.mjs "DEF-026: a write's confirmation never names a title while titles are hidden" - it runs the real page block, sets the same state the write handlers set and calls the real paint(): hidden saved/deleted/unknown all show the fixed lines and never the title, the visible case still shows the PC's sentence, and the old raw draw is pinned absent. It FAILS with `bannerSaid()` reverted to `state.said` (33 passed, 1 failed) and passes with the fix (34 passed, 0 failed). ON-SCREEN CONFIRM OWED: this row stays open until the owner sees the HUD banner on a locked PC; no live install, nothing pushed. | fix/def-026-desktop-calendar-hidden-echo-2026-10-31 (worktree .dsh-scratch/DEF-026-2026-10-31/wt, base origin/main @ 8f7e165d5) |
