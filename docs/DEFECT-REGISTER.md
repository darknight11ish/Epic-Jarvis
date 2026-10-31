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
| DEF-018 | sec-deploy | 2026-10-30 | open | `backend/jarvis_agent.py`; `jarvis-backend/jarvis_agent.py`; `backend/test_tainted_tool_gates.py` | FIVE 2026-10-30 AUDIT FINDINGS IN ONE FILE-SCOPE, RECORDED AS ONE OPEN ROW BECAUSE the register's own rule says one path may sit in only one open row (docs/DEFECT-REGISTER.md:47, enforced by tools/check_defect_register.py); DEF-017 is the multi-part precedent. Line numbers are origin/main f11e2ff78, backend/jarvis_agent.py (twin byte-identical). (1) SAME-TURN REMINDER REFUSAL INTRODUCED BY C5 (#1003): :3019 result = watch.took_in('coming_up', result) now marks the turn as having read outside text (:6280-6282 self.read[name] = self.read.get(name, 0) + 1), and the schedule-write guard :2984 if name != 'coming_up' and watch is not None and watch.note_needs_a_person() then REFUSES the write with SCHEDULE_AFTER_OUTSIDE (:2871-2873), raising no card, because schedule tools are 'straight to jarvis_schedule, no gate' (:2981); so one answer to 'what's coming up, and remind me to call Mum at 6' succeeds on the read and refuses the reminder. note_needs_a_person (:6443-6456) counts coming_up because it is in neither NOTE_WRITES (:3464-3506) nor _NOT_READING (:5654-5667). The C5 test itself avoids this combination: backend/test_schedule.py:1159-1163 gives coming_up its own _TurnWatch 'so that read mark does not change the schedule-write checks below'. (2) GAP-1 ADDRESS TEST IS A RAW SUBSTRING: _url_in_owner_words (:3749-3755) returns bool(words) and key in words, so a model-chosen 'evil.com' counts as owner-given whenever the owner typed 'notevil.com'; url_fetch_card_lines (:3770, :3776-3777) then omits URL_FETCH_READ and the card cannot say the address was the model's choice (the fetch still asks through NEEDS_A_PERSON). (3) GAP-1 COMMENTS CONTRADICT THE CODE: :3703-3709 promises read_web_page 'is asked under URL_FETCH_AFTER_OUTSIDE_ACTION when its own tier would not ask', :12103-12110 says 'No action swap here, and that is deliberate', and :3735 URL_FETCH_AFTER_OUTSIDE_ACTION = 'read_web_page' makes test_tainted_tool_gates.py:389 (gate.last['action'] == AG.URL_FETCH_AFTER_OUTSIDE_ACTION) true with no swap at all, so that pin cannot fail. (4) SILENT DEPTH CAP: _strings_in (:5793-5805), _vetted (:5823-5838) and _cleaned (:5808-5820) return unchanged past depth 20, so a deeper string reaches the model unnormalised and un-scanned; demonstrated with a 26-level synthetic payload by .dsh-scratch/AUDIT-2026-10-30/verify_findings.py (verify-findings.log: 6 confirmed, 0 not shown). (5) LATENT PLAN-STEP GAP: _plan_step_dispatch (:1683-1838) applies _sandbox_action_for but none of the new shaped-turn belts - no sandbox_why swap to SANDBOX_FILES_ACTION, no Gap-1 url_why/URL_FETCH line, no NOBODY_ASKED_SANDBOX_WORDS/NOBODY_ASKED_URL_WORDS refusal; unreachable on the shipped config because [tools].enabled does not name propose_plan (backend/rebuilt/jarvis-framework.toml:1875) and jarvis_plan.enabled requires a fresh measured tool-eval (backend/jarvis_plan.py:541-565), so it becomes live only if that card is switched on. SMALLEST FIX PER ITEM: ignore the coming_up read in the schedule guard only - note_needs_a_person(ignore_read=('coming_up',)) at :2984 - so a note write after coming_up still asks a person; boundary-match the address in _url_in_owner_words; correct the Gap-1 comments and make the test assert a distinct ask action or the belt refusal; vet deep strings or refuse an over-deep result rather than pass it through; port the three belts into _plan_step_dispatch. TESTS THAT WOULD CATCH THEM: backend/test_schedule.py on one watch coming_up then set_reminder (expect ok True); test_tainted_tool_gates.py with owner words 'notevil.com' and model URL 'evil.com' expecting URL_FETCH_READ; a deep-payload stub tool; and a plan-step test asserting ask/refusal for run_data_script and a model-chosen URL in a shaped turn. | origin/main @ f11e2ff78 |
| DEF-019 | sec-deploy | 2026-10-30 | open | `backend/jarvis_documents.py`; `jarvis-backend/jarvis_documents.py`; `backend/test_content_risk.py` | C6 BOUNDARY CLAIMS MORE THAN IT COVERS (#1003), FOUND 2026-10-30. backend/jarvis_documents.py:265-300 says 'Every word this module returns comes from a FILE the owner did not write ... So the store draws the boundary itself now', but _mark_answer (:330) folds and labels only out['text'] and each results[].snippet; read() also returns the document's own part title (:2061 '"title": title, "text": body') and, for a multi-part document, 'contents' built from those part titles (:2066-2069 shown = f'{i}. {t or (untitled)}'), and both come back byte-identical - not folded, not labelled, not scanned. VERIFIED BY RUNNING THE REAL FUNCTION: .dsh-scratch/AUDIT-2026-10-30/verify_findings.py extracts _mark_answer from the origin/main source and, on a read()-shaped answer whose title and contents line carry U+200B, the text gets OUTSIDE_LABEL while the title and every contents line are unchanged (verify-findings.log: 6 confirmed, 0 not shown). Through the agent today _TurnWatch.took_in still normalises every string, so nothing reaches the model raw; the defect is the STORE-level property C6 exists to create for a second caller or a future route. SMALLEST FIX: fold and label title and each contents line in _mark_answer (name and path stay raw on purpose). TEST: backend/test_content_risk.py reads a generated .docx or .pdf whose part title contains U+200B and asserts the returned title and contents lines are folded and carry OUTSIDE_LABEL. | origin/main @ f11e2ff78 |
| DEF-020 | sec-deploy | 2026-10-30 | open | `scripts/update-jarvis.ps1`; `scripts/test-update-jarvis.ps1` | UPDATER TREATS A DIRTY TREE AS THE RELEASED CODE (#1010), FOUND 2026-10-30. scripts/update-jarvis.ps1 Get-LocalVsRelease (:719-746) answers from commit identity only: :737 'if ($headSha -eq $relSha) { return ''same'' }', then two merge-base --is-ancestor calls (:738-741); the whole script contains no 'git status' and no 'git diff' (read end to end for it - verify_findings.py F2 in .dsh-scratch/AUDIT-2026-10-30). The caller then prints, :1298-1300, 'this folder is at the released commit ..., so the signed release is exactly this code - using it instead of rebuilding' and installs the published installer. A working tree standing ON the released commit can hold uncommitted newer work, and that work is silently replaced by the published build, against the function's own rule (:1288-1291 'Only a folder that has moved PAST the release keeps its own build'). NO EFFECT ON THIS PC TODAY: the owner's checkout is clean and work happens in .dsh-scratch worktrees. SMALLEST FIX: after the SHA equality, a non-empty 'git status --porcelain --untracked-files=no' returns local-ahead (build) or a new 'dirty' answer that builds and says why. TEST: scripts/test-update-jarvis.ps1 commits a throwaway repo at the release commit, modifies a file, and expects local-ahead/'dirty' rather than 'same'. | origin/main @ f11e2ff78 |
| DEF-021 | sec-deploy | 2026-10-30 | open | `jarvis-backend/jarvis_gate.py`; `backend/jarvis_asks_first.py`; `backend/test_gate_unknown_risk.py` | _SYNTH_TIERS SILENTLY OVERRIDES THE OWNER'S [autonomy.tiers] LINE, AND #1008'S FORCED ASK INHERITS THE EXEMPTION, FOUND 2026-10-30 AND PRE-EXISTING (the override predates today; today's forced-ask rule is built around it). jarvis-backend/jarvis_gate.py:1227-1241: _tiers() reads and validates the file's autonomy.tiers (:1237-1239) then :1240 'out.update(_SYNTH_TIERS)' - the file's own line is overwritten by the tool table's literal tier, for every _TOOL_ACTIONS entry whose value is a bare tier ('calculator': 'auto', 'memory_store': 'notify', 'git_commit': 'ask', :842-869), about forty names. The new forced ask then skips exactly those names (:1804-1813). PROVED BY RUNNING THE PUBLISHED GATE: .dsh-scratch/AUDIT-2026-10-30/verify_findings.py imports jarvis-backend/jarvis_gate.py from origin/main f11e2ff78 with a stub jarvis_framework, calls gate.action_for_tool('calculator'), then _tiers({'autonomy': {'tiers': {'calculator': 'never', 'some_real_action': 'never'}}}) returns calculator 'auto' and some_real_action 'never'; gate.check('calculator', framework=...) returns allowed=True, tier='auto', outcome='auto'. So an owner who writes calculator = "never" in the settings file gets auto behaviour. DIVERGENCE: backend/jarvis_asks_first.py:851-855 reads _file_tiers() = fw.all_tiers(), the file's tiers, so the What asks first page can show 'never' while the gate runs auto. SMALLEST FIX: let an explicit file line win - out = dict(_SYNTH_TIERS); out.update(file_tiers) - and make the forced-ask exemption require that no file line exists for the name. TESTS: a temp framework with calculator='never' makes check() refuse at never; calculator='ask' raises a card; and the asks_first page and _tiers() agree for such a name. | origin/main @ f11e2ff78 |
| DEF-022 | sec-deploy | 2026-10-30 | open | `jarvis-client/app/src/main/java/com/jarvis/client/data/Security.kt`; `jarvis-client/app/src/main/java/com/jarvis/client/ui/approval/ApprovalCard.kt`; `jarvis-client/app/src/main/java/com/jarvis/client/net/SignedApproval.kt`; `jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt` | PHONE CARD'S NEW LINE PROMISES A PROMPT THE OFFER PATH DOES NOT SHOW (#1004), FOUND 2026-10-30. The owner's 2026-10-30 ruling adds a sentence under Approve saying what the press will ask for; Security.kt:230-240 approveCheckWords reads only approvalNeedsCheck(s, item) and s.method, so a risky card gets 'Approve asks for your fingerprint or PIN' regardless of whether signed approvals are on, and ApprovalCard.kt:322-323 (drawn at :856) draws it whenever there is a live Approve. But with signed approvals OFF, SignedApproval.pathFor (:295-304) returns Path.OFFER (:299), and MainActivity.approveItem (:4351-4374) sends that path straight to SignedApproval.noticeFor (:4372) without confirmed() - the local biometric prompt - so pressing Approve shows 'Nothing was approved. Risky approvals from this phone need to be signed with your fingerprint or PIN, and signed approvals are not turned on yet.' (OFFER_WORDS :312-314) and sends nothing. No approval leaks (nothing is sent), but the card's sentence is false for that press. SMALLEST FIX: give the line the signed-approval state and word the OFF case 'once signed approvals are on', or let the offer notice be the only sentence. TEST: ApproveAsksFingerprintTest adds the three signed-approval states crossed with a risky item and asserts the sentence matches what Approve actually does (prompt vs offer). | origin/main @ f11e2ff78 |
