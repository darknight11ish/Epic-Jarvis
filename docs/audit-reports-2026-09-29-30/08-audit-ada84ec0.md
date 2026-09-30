# Report 08 (audit), agent ada84ec0, 2026-09-29T09:54Z

> **What it was asked** (first 600 characters of the task): Repo /home/user/Epic-Jarvis, branch ccr-a9b557ac-cpnbwx (= origin/main 1748ac33 plus small fixes). Do NOT edit files. Check what PR #30 brought in (Inbox tidy by voice; the Kokoro v1.0 voice upgrade with 'Hear it'; see `git diff cbc6d12d..1748ac33 --stat -- . ':!docs/SOURCE-BUNDLE.md'`) against CLAUDE.md's five rules and every dated owner decision, docs/ARCHITECTURE.md sections 3, 4 (named ways out of the PC: inbox tidy must be a NEW named way out and its own gate action, like sending email - verify the row exists and the gate action is in HARD_LIMITS/MUST_ASK/NEEDS_A_PERSON/_RISK 'risky', tie

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

RULES CHECK OF PR #30 (Inbox tidy by voice, Kokoro v1.0 with "Hear it")

**Bottom line:** I found no rule violation and no unrecorded bend. The five rules, the dated owner decisions and ARCHITECTURE sections 3, 4 and 8 all hold. I found three housekeeping problems (a branch regression, a failing test, stale words in CLAUDE.md).

Tests that pass here: `tools/check_parity.py` ("No undecided drift"), `tools/gen_notices.py --check`, `tools/gen_inbox_tidy_cases.py --check`, and the backend suites `test_inbox_tidy` (400), `test_kokoro` (153), `test_voices` (140), `test_voice_upgrades` (319), `test_asks_first` (174), `test_card_words` (109), `test_reach` (133), `test_lockdown` (53), `test_gate_risk_words`, `test_approval_contract`, `test_owner_check` and `test_shipped_modules` (459). The desktop tests `inbox-tidy.mjs`, `custom-voices.mjs` and `email-send.mjs` also pass, with no failures.

Note on how I ran things: plain `python3` crashes on the `cryptography` package in this container. Use `python3.12` for `test_inbox_tidy` and `test_asks_first`.

I did not run the Android Kotlin tests or the Rust tests (this container cannot). I only read that code.

## A. Problems, ranked (none breaks a rule)

**1. MEDIUM - this branch's merge commit deleted the inbox-tidy patch history.**
- `git diff 1748ac33 HEAD --stat -- backend/patch-history` shows:
  - `backend/patch-history/inbox-tidy/34c6103.patch`, `98a5310.patch` and `d8d7911.patch` deleted (60 lines each);
  - `backend/patch-history/index.tsv` loses 3 rows.
- Cause: the merge commit `8eaa521d` ("Merge origin/main (PR #30) into the audit-fixes branch").
- Result: `python3.12 backend/test_patch_history.py` fails: "missing a version of: inbox-tidy.patch, inbox-tidy.patch, inbox-tidy.patch". CI's backend job would go red.
- Fix: restore those files from `1748ac33`, or run `git fetch --unshallow` and then `python3 tools/build_patch_history.py`.
- Separate wording in the same test output: "wellbeing.patch: leaving out the version from 31ad726 - a hunk header's line counts do not match". That message appears to be old.

**2. LOW-MEDIUM - `backend/test_agent.py` fails 5 checks, and it fails the same way on PR #30's own tip `1748ac33`.**
- All 5 are `tidy_inbox` cases inside `t_every_outbound_tool_is_refused_unless_a_person_approved`:
  - at tier auto, notify and ask, "the model is told why, and which line to change";
  - at tier ask with outcome approved: "runs" (the check saw `executed=[]`);
  - at tier ask with outcome None: "runs".
- Product behaviour is correct and fails safe. The generic test does not know about tidying's extra rule, and the real check reads `email_read` through `_tier_of` (`jarvis_agent.py:2221`). In the test that lookup falls back to "ask" (the file's own comment says it does so when it cannot read the config), so `_tidy_inbox_refusal` refuses with "reading your email asks first on this PC...".
- In production `email_read = "auto"` (`rebuilt/jarvis-framework.toml:91`), so the real tool works.
- Fix: make the test's tier lookup return "auto" for `email_read`, or skip `tidy_inbox` in that loop the way `propose_plan` is skipped there.
- I did not check whether CI's `run_suites.py` runs this suite.

**3. LOW - CLAUDE.md is stale.**
- Line 548 ends the Inbox tidy decision with "Not built yet."
- Line 572 ends the Kokoro v1.0 decision with "Not built yet."
- Both are built (JARVIS-API sections 94 and 95, and `.claude/agents/JARVIS-TODAY.md` say so). Suggest editing those two lines to "Built 2026-09-28/29".

**4. INFO - "delete" is refused, not silently turned into Trash.**
- `jarvis_inbox_tidy.py` `plan()` refuses any action outside archive/star/mark_read/trash: "There is no permanent delete: \"delete\" means trash."
- The tool's action list has no "delete" either (`jarvis_agent.py:1313-1330`).
- The safe direction is met (delete never happens). The model just has to retry with "trash".

## B. Owner-recorded bends (fine, listed for completeness)
- Inbox tidy is a risky approval: it changes the mailbox on the owner's own mail server. The gate line is `"tidy_inbox": ("yes", "outbound", ...)` (`inbox-tidy.patch`). Anything outbound counts as risky (`jarvis_owner_check.py:150-170`, and the same rule in Rust `lock/rules.rs:227`). So Windows Hello is needed on the PC and the screen lock on the phone. `test_inbox_tidy.py:1207-1211` proves it.
- Kokoro download: 350 MB, one PowerShell line, run by the owner, pinned in `jarvis_kokoro.py:66-71`: URL from GitHub, 349,906,910 bytes, `sha256 c5f7e2d2...3298`. The line refuses to install if the hash differs. It also refuses to give any line if the hash is empty. It keeps the old pack as `tts-old-<date>`.

## C. Checked and fine, with evidence

**Inbox tidy, the owner's decisions**
- **Four actions only:** archive, star, mark_read and trash (`jarvis_agent.py:1313-1330`, enum). Cap of 30 emails (`MAX_EMAILS = 30`).
- **No permanent delete:**
  - the only `EXPUNGE` is `conn.uid("EXPUNGE", str(uid))` inside `_move_by_copy`, on one message, after the server confirmed the copy (`jarvis_inbox_tidy.py:864-876`);
  - no plain `EXPUNGE`;
  - never `CLOSE` on a folder opened for changes (lines 53-54 and 487, 1051);
  - a server with neither MOVE nor UIDPLUS is refused before anything is touched.
- **One card lists every email:** `describe()` (lines ~690-720) numbers each email with sender, subject and date, plus "Left out: N ..." for emails with no Message-ID. The card is refused rather than cut if too long (`TIDY_INBOX_TOO_LONG`, `jarvis_agent.py:6620`). Sender and subject are trimmed to 24 and 38 characters on the card (lines 170-171). That is truncation of each line, not omission of any email.
- **Outside text is stated plainly:** `tidy_inbox_card_lines()` (`jarvis_agent.py:1953`) puts a line at the top when `watch.read` or `watch.tainted` is set: "This conversation read outside text ... check that tidying these emails was your idea...". It also covers a non-typed message and app-added context. It is wired in at `6595-6599`.
- **On-screen approval only, never by voice:** `NEEDS_A_PERSON` contains `tidy_inbox` (`jarvis_agent.py:1720`). Only a person's yes (an approved outcome) runs it. Nothing in voice, quick-command or settings-registry code mentions tidy (grep on `jarvis_quick.py`, `jarvis_speech.py`, `jarvis_settings_registry.py`). A voice-provenance turn still needs the card (`test_inbox_tidy.py:986`).
- **No "always allow":** `tidy_inbox` is in `jarvis_asks_first.py` HARD_LIMITS (line 282) and MUST_ASK (line 308), and not in SWITCHABLE. The toml line is `tidy_inbox = "ask"` (`rebuilt/jarvis-framework.toml:162`). The module refuses any tier other than "ask" (`tier_problem`). Also in `NEEDS_A_PERSON`, `LOCKDOWN_ACTIONS` (line 1605) and the "Email and calendar" group (line 340).
- **Undo:** 10 minutes, one tap, no card. It is kept in memory only, with ids and no words. It is held on a stale link and while App lock or hidden lists apply, in both apps (desktop `brain/inbox_tidy.rs:151-160`; phone `JarvisRuntime.kt:6329-6333`). While locked or hidden, the desktop strip shows only "Your inbox was tidied. You can undo it for a few minutes."
- **Rule 1:**
  - the mailbox is read by code on the PC, and only the local model asks for a tidy;
  - `_tidy_inbox_refusal` refuses unless the model is on this PC (`local_model_refusal`);
  - the model is told counts only;
  - the only network connection is IMAP over TLS to the owner's own server (`imaplib.IMAP4_SSL`, line 470).
- **Rule 3:**
  - the password comes from `jarvis_email.imap_password` (same as reading and sending);
  - it is registered with the scrubber, including its base64 form (lines 245-260);
  - it is never in the plan, card, result or audit log (the audit records counts and outcomes only);
  - `describe()` says "your password goes to that server and nowhere else".
- **ARCHITECTURE section 4:** there is a dedicated row (line 625) and a prose paragraph (lines 729-767). Section 4 also says the row "reaches no new destination" (the same mail server as reading and sending). It is a named way out, has its own gate action, and is treated like sending email.
- **Gate wiring (`inbox-tidy.patch`):**
  - the "acts only on tier ask" set;
  - its `_RISK` line, `("yes", "outbound", ...)`;
  - its `_TOOL_ACTIONS` line.
  - The gate file itself is outside this repo. The patch and its tests, not the real file, are the proof.
- **PC_ONLY_ACTIONS:** `tidy_inbox` is not in it (`jarvis_owner_check.py:125`). The owner did not ask for PC-only; the phone may approve with its fingerprint, as with send_email.
- **Lockdown:** the `email_read` tier becomes "ask", and `read_problem` refuses tidying then ("reading your email asks first... so tidying is not offered"). So Lockdown effectively blocks it, and `test_lockdown` passes.
- **Stop everything:** it is a screen-action hotkey and does not apply here. A tool call also honours `watch.stopped()`.
- **Both apps:** desktop `brain/inbox_tidy.rs`, `inbox-tidy.js`, `surfaces.toml` and permission files; phone `net/InboxTidy.kt`, the Home Undo strip and `JarvisRuntime`.
- **Contract files:** desktop and phone copies match `tools/gen_inbox_tidy_cases.py`.
- **Parity:** routes `/api/email/tidy` and `/api/email/tidy/undo` are "ported" in `tools/check_parity.py:116-117`, and check_parity is clean.
- **Section 8 (one-sided on purpose):** ARCHITECTURE lines 1824 and 1996 explain that the Undo strip is left off the desktop's separate widget and HUD window because they show no chat, and the widget's Approve for a tidy card opens the Jarvis bar.
- **Names:** no duplicate gate action, route or tool. `tidy_inbox` shares the "draft or tidy email" more-tools group (`jarvis_agent.py:3887`). It is excluded from plan-card steps (`_PLAN_EXCLUDED_STEPS`, line 837) and from the `_NOT_READING` list, so its own answer does not count as read text.
- **"What asks first" and "What can Jarvis reach":** there is a row `"tidy_inbox": "Tidy your inbox (one card lists every email)"` (`jarvis_reach.py:104`) and an "Email (tidying)" reach row (lines 553-572). The card title `"tidy your inbox (archive, star, mark read or trash)"` is in `jarvis_card_words.py:56`. Fixtures for asks-first, card-words and reach match in both apps (the tests above pass).
- **Docs:** JARVIS-API 95 matches the code (gate action, tier, risky rule, Undo, cap). `backend/README.md` has an `inbox-tidy.patch` row (line 162) and an "Inbox tidy" section.

**Kokoro v1.0 and "Hear it"**
- **Sky and Adam not offered:** `V1_PICK` (`jarvis_kokoro.py:145`) and `V019_PICK` exclude `af_sky` and `am_adam`. So are `af_alloy`, `am_echo`, `am_onyx`, `af_nova` and `bm_fable` (OpenAI look-alike names). `NEVER_FOR_ANIMALS = ("af_sky", "am_adam")` (line 156).
- **Sky and Adam for an existing owner choice:** an owner who already picked one keeps it, listed once as "your current choice". Their pick is their own, and the rule about Sky is for the sea otter. I found no conflict.
- **Migration:** `migrate_saved_choices()` (`jarvis_voices.py` ~line 560) rewrites saved numbers as names once. An animal choice of Sky or Adam falls back to the animal's own voice.
- **Saved by name:** `set_speaker` takes a name from the offered list (`jarvis_voices.py:545-560`). Old numbers carry over through `LEGACY_NAME`.
- **Hear it:** `POST /api/voice/voices/sample` takes only `{"voice": name}`, and only names from the offered list. It plays one fixed line in a built-in Kokoro voice, no custom recording. It uses no card, sends no event, writes no audit line, keeps only 16 samples in memory and changes no setting (`jarvis_voices.py:589-670`). The voices come from Kokoro's own pack, so it cannot be a real person's or the owner's voice. It is also not a way out of the PC (a local sound). It is not held on a stale link, the same as "Try it".
- **Notices:** `THIRD-PARTY-NOTICES.txt:158-166` credits "Kokoro-82M v0.19 and v1.0 (Apache-2.0; v1.0 is sherpa-onnx's kokoro-multi-lang-v1_0 release, 350 MB, pinned in backend/jarvis_kokoro.py...)". It notes the bundled espeak-ng-data (GPL-3) and that nothing is shipped. `tools/gen_notices.py --check` reports it up to date.
- **No speech-to-text on either app:** this feature is text-to-speech only.

**Not proven, so not claimed**
- No live test against a real mail server or a real Kokoro v1.0 pack. The docs say so: "not tried against a real mail server".
- The Kotlin and Rust tests were not run here.
- I did not verify the SHA-256 independently. `test_kokoro` checks the README line against the pin.

Key files:
- `/home/user/Epic-Jarvis/backend/jarvis_inbox_tidy.py`
- `/home/user/Epic-Jarvis/backend/inbox-tidy.patch`
- `/home/user/Epic-Jarvis/backend/jarvis_agent.py`
- `/home/user/Epic-Jarvis/backend/jarvis_kokoro.py`
- `/home/user/Epic-Jarvis/backend/jarvis_voices.py`
- `/home/user/Epic-Jarvis/backend/test_agent.py`
- `/home/user/Epic-Jarvis/backend/patch-history/index.tsv`
- `/home/user/Epic-Jarvis/CLAUDE.md`
