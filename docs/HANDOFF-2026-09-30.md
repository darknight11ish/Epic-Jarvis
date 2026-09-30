# Handoff - 30 September 2026 (state after PR #39)

Everything a new conversation needs to carry on. Written for someone starting
cold. It does not repeat `CLAUDE.md`; it says where things stand, what was
decided, what is still to do, what is known to be wrong, and how this work has
been run. **Read `CLAUDE.md` first** (the owner's rules and every decision are
there), then this file.

**Moving to a new Claude account? Read `docs/NEW-ACCOUNT-SETUP.md` first.** The full text
of every audit and build report from this work is saved in
`docs/audit-reports-2026-09-29-30/` (start at its `INDEX.md`); the notes below say which
report holds the detail.

An older handoff, `docs/HANDOFF.md` (15 September, Android client), is history
and mostly out of date. This file replaces it as the place to start.

---

## 0. Paste this to start the next conversation

> Read `CLAUDE.md`, then `docs/HANDOFF-2026-09-30.md`, in full. Then check `origin/main`
> and open pull requests (there should be none). Work on branch
> `ccr-a9b557ac-cpnbwx`, restarted from `origin/main` (that branch's last pull
> request was merged). Before building anything, ask the owner (one short
> multiple-choice question) whether they have run the update on their PC and how
> it went. Then continue the queue in section 5, in order, fixing anything that
> does not need the owner and asking short multiple choice for anything that does.

---

## 1. The owner, and how to work with them

- **A beginner developer.** Plain words. Say what a thing is before using its
  name. Lead with the answer. Say exactly what to do (which button, file,
  command). Explain any jargon in one line.
- **Multiple choice, and short** (`CLAUDE.md` says it twice): one or two
  questions, two or three options, one or two sentences each, recommendation
  first and labelled. Put reasoning around the question, not in it.
- **The owner's standing instruction, 2026-09-30:** *"Give me multiple choice for
  any actions that require me. If it doesn't require me fix it automatically."*
  So: fix what does not need a decision; ask (short multiple choice) for what does.
- **The owner's standing instruction about pull requests:** make a pull request,
  track it until every check passes, then merge it. **Merge with a merge
  commit, never squash. Never merge over a red check.** Do not open a pull
  request unless the owner has asked or this standing instruction applies
  (it does, for finished work).
- **PowerShell commands must be ONE line**, ready to paste, using wildcard paths
  (copying from chat drops spaces: the owner's folder is
  `...\Documents\Claude\Open jarvis files\Desktop program`).
- **The owner said "no more audits are needed" earlier, then asked for several.**
  `CLAUDE.md` has a standing rule: every new feature gets its own audit, without
  being asked. Run one short audit per batch of new features, not more.
- **The owner asked not to work on educational features for now** (quizzes,
  flashcards, YouTube learning, Spanish). They stay queued behind everything
  else. The note-quiz idea (`py-fsrs`, `docs/AUDIT-2026-09-28-REPO-REFS.md`
  milestone 3) was described and accepted in principle, then paused.
- Commit and pull-request text end with the attribution lines the harness gives
  (see the system reminder in the session). Do not put a model name in any
  commit, pull request or code comment.

---

## 2. Where things stand right now

- **`origin/main` is at `d9133ae0`** ("Merge pull request #39"). Everything below
  in section 3 is on it. **No pull request is open.** No trigger of mine is
  running. (A "Daily awesome reminder" routine exists on the account; it is not
  part of this work, do not touch it.)
- **Local branch `ccr-a9b557ac-cpnbwx`** was reset to `origin/main`; this file is
  the only new commit on it. Old worktrees under `.claude/worktrees/` and
  `/tmp` are leftovers (their work is all merged); remove them
  (`git worktree remove --force <path>`; three need `-f -f`) if the disk fills.
- **The owner's PC has NOT been updated.** Their backend is a week old. They had
  trouble: old backend files with Windows line endings, and a broken
  `screen.patch` (my mistake, fixed). They have not yet run the fixed update.
  **First thing to ask the owner** (short multiple choice): did the update run,
  and how did it end? The new script ends with a green, yellow or red summary.
  If red, they paste the last 40 lines and you fix whichever patch is named.
- The owner's clone is `C:\Users\<your-windows-name>\Epic-Jarvis-main` (a fresh clone of real
  `main`). The old clone `C:\Users\<your-windows-name>\Epic-Jarvis` is on a stale branch with
  a stash; ignore it. The real backend is under
  `C:\Users\<your-windows-name>\Documents\Claude\Open jarvis files\Desktop program`
  (a week-old copy is also in NordLocker: only a backup).

### The update steps to give the owner (unchanged, repeat them)

1. `cd "$env:USERPROFILE\Epic-Jarvis-main"; git pull`
2. `$b = (Get-Item "$env:USERPROFILE\Documents\Claude\Open*\Desk*\jarvis_hud.py").DirectoryName; powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -BackendPath $b -FixLineEndings`
   (Jarvis must be closed first; the script now refuses to run while it is
   running unless `-Force`.) Green "ALL DONE" = worked and proven. Yellow
   "DONE but NOT fully proven" = applied, some tests could not run (normal on
   the owner's PC). Red "DONE WITH PROBLEMS" = read the list; it prints a
   one-line restore command.
3. Rebuild the desktop app from the same folder: `cd jarvis-desktop; npm install; npm run tauri build`, run the `-setup.exe`.
4. Install the phone app from the `client-latest` release once its page names the
   new `main` commit (the phone job publishes only when the emulator smoke job passes).
5. Then the checklist: Preflight, "Look at this", Watch badge, Kokoro "Hear it"
   voices, phone notifications, `tools\check_screen_safety.py`
   (`docs/UPDATE-AND-CHECK-2026-09-28.md` has the full list).

---

## 3. What is on `main` from this session (pull requests #37, #38, #39)

- **#37:** the update script's `-FixLineEndings`, the `screen.patch` context fix
  plus a test that it applies to real context, a time-of-day-proof `test_tidy`.
- **#38** (another session's): fill a web form, show the owner a picture,
  a separate Submit card (`browser_form_submit`), up to 8 cards for one site's
  multi-page form. See `docs/FORM-REVIEW-DESIGN.md`, `JARVIS-API.md` section 98.
- **#39** (this work; 163 files):
  - **Extra graphics cards of 8 GB** work (floor 7,680 MiB reported). Learning,
    Wiki, Pictures on an 8 GB card; not "Longer conversations" or "Browser
    control" (an 8 GB card holds no more than the main card's 16K). 16/24 GB get
    the same qwen3:8b at 32K plan. Third-card approval tied to the card's id
    (a different card, or an old file, counts as unassigned and asks again).
    **All sizes are calculated, not measured; no extra card is installed.**
  - **"Look at this" / "Watch with me" use the Pictures lane first**
    (`jarvis_screen_picture.pictures_lane()`), processor picture mode as fallback.
    Picture mode's own switch still decides whether a picture is read at all
    (the owner was asked; left as built). The local chatbot's model-size limit
    follows the card's real memory.
  - **Screen safety:** secret scan capped (25,000 chars, 6 s, fails closed),
    more patterns (`DB_PASSWORD=`, Bearer, US SSN, code-before-label,
    `Passwort:`); a look racing Stop is discarded; unreadable program name is
    painted black; a Watch started from the desktop ends after 45 s without a
    `heartbeat` (`POST /api/screen {"do":"heartbeat"}`; the desktop sends it every
    12 s and now sends `"from":"desktop"` on start); phone Watch ends after 10 s
    of a lost link and says it cannot see password boxes.
  - **Settings:** the email switch bug (`email_read` vs `email_check`) fixed for
    all four reading switches (`jarvis_asks_first.TOOL_NAME`); **web search on/off
    in both apps** (`web_search_enable` card via `web-search-switch.patch`);
    settings registry knows devices, crash notes, quick tiles; phone voice
    switches moved to Settings > Voice; phone Settings jump list; greyed panels
    say why on a stale link; "What Jarvis can reach" explains file-only tools.
  - **Phone hardening:** Live/handoff start only with an app-private secret
    (`InternalLaunch`), the approval widget and Mute tile obey App lock, stream
    start single-file, all notification ids in `NotificationIds`, TalkBack labels.
  - **Desktop hardening:** App lock fails closed on a bad saved value;
    `backend.log` capped at 4 MB while running; approval toasts withdrawn when a
    card is decided elsewhere; failure toasts plain and App-lock aware; solid
    focus ring with a forced-colors fallback; three guard tests
    (`csp-inline`, `html-sinks`, `focus-outline`).
  - **Backups/time:** retention never deletes the newest file; restore is
    all-or-nothing with rollback; truthful restore card;
    `POST /api/backup/delete-older` (backend only); `age_s` on fired jobs;
    "12 at night" is midnight; timers survive a clock set back; DST/leap-day
    parser bugs fixed.
  - **Supply chain:** telemetry env switches (`jarvis_child_env.py`), `cargo deny`
    checks sources, CI pip installs pinned.
  - **Update script:** rehearse-then-convert, honest summary/exit codes,
    one-line restore, refuses while Jarvis runs, guards `git` against an outer repo.

CI at merge: all 17 checks green (backend, frontend, rust incl. `cargo test` on
Windows, powershell-5, audit incl. `cargo deny` sources, python-advisories,
credential-manager, Android `build`, `smoke`, `face-shots`).

---

## 4. Decisions the owner made this session (also in `CLAUDE.md`)

Multi-GPU: 8 GB extra cards must be fully used; screen looks use the Pictures lane
first with processor fallback; "Pictures" does NOT switch on "Picture mode"
(they asked "explain more", then I explained; **left as built - if they say
otherwise, change it**); web search back-on can be approved from the phone
(as built); single 16-32 GB first card gets a suggestion line in Brain > Model
and counts as capable for Pictures/Wiki/Browser without a preset (each off
until approved); 14B on 16/24 GB waits for measurement; per-model thinking
levels (Off/Quick/Deep/**Auto**), per model; multi-model failover, checker
(tool plans and code only), local compare - all off by default, measured first;
notifications: full settings screen (style per kind, quiet hours that never
silence urgent alerts or approvals, Test button) and urgent alerts break through
Do Not Disturb / Focus Assist with a note, late urgent = silent "Missed";
status widget sources ("current task with Stop", "approvals waiting"),
pinned shortcuts for any Brain section/chat, widget transparency/accent/high
contrast/live preview, "graphics memory per card" and "tokens per second"
widget sources (marked not measured); approval history shows one non-sensitive
summary line; "Delete older backups now" button after an Erase; list and remove
old Ollama models behind one card; compress audit logs after 7 days (delete at
90); memory size line in Brain; free space after Erase (vacuum, at most hourly);
screenpipe stays rejected; app-merge "restore to before" queued with the app
builder; a stale-area check after every big merge.

Rejected as replacements (ideas only): Xinference, LocalAI, GPUStack, Triton, a
llama-server supervisor, Outlines (cannot constrain Ollama; Ollama's `format`
schema already used), STORM, MCP filesystem/git servers (MCP bridge already
built, local programs only), Zebar, yasb, tauri-plugin-decorum (no window fault
to fix), json-to-compose / free-form widget renderer (design section 86.5
already rejects model-written layouts), Skill-Anything, QuizScribe, deepeval.
Ideas kept: a per-lane measured log (time to first token, tokens/s, memory),
a slow-slot warning for the second card.

---

## 5. THE QUEUE (build in this order; each: fix without asking, ask only what needs the owner)

Each item ends with the standing audit (bugs / both apps / fit) and one pull
request per batch, tracked to green and merged (merge commit).

### 5.1 Notifications (both apps + backend)  [owner-approved: full set]
Source: two audits this session (phone, desktop). Verified findings still open:
- **Phone:** no notification settings screen (per kind on/off, style, Test,
  quiet hours; link to each Android channel); reminders/briefings share the
  `jarvis_approval` (HIGH, "Approvals") channel - give them their own new channel
  id (an existing channel's importance cannot be changed by the app); urgent
  "tell me" alerts and briefings never run the late-ring rule (`heardLate` is
  only called at `JarvisRuntime.kt` ~4864) - a late urgent alert must become the
  silent "Missed at HH:MM" notice (owner chose this); the phone judges "late" with
  its own clock vs the PC's (`Schedule.kt` ~806): **use `age_s`** (already sent by
  the PC on a fired job's view); approval notification text ignores App lock /
  "hide lists" (`ApprovalNotifier.textFor`); Live offer/Resume skip the
  POST_NOTIFICATIONS check; urgent alerts do not bypass Do Not Disturb by
  design - add the plain note and, where Android allows, the alarm-category
  path; no `AlarmManager` (phone alarms depend on the PC event stream reaching
  the phone at ring time - say so in the UI).
- **Desktop:** no Settings section for notifications; briefing / tell-me toasts
  ignore the per-job `notify:false`; alarm replays after an app restart can toast
  twice (`TOASTED` guard is in memory); if the job read fails `fired_at` is 0 and
  an old alarm rings loudly (`schedule.rs:590-594`; **use `age_s`**); no Focus
  Assist handling; tray tooltip shows approval/attention counts under App lock
  (`tray.rs:1194-1201`); dev/uninstalled builds fall back to a plain toast with no
  Deny/Snooze; the **captcha/sign-in hand-off has no desktop toast because no
  event reaches `stream.rs`** (backend must publish one first); timer spoken
  aloud (`coming-up.js:203`) ignores lateness.
- Cross-device: approval toasts are not de-duplicated between phone and desktop
  ("seen on the other device" cancel exists only for schedule jobs).
- The audits' full write-ups are saved in `docs/audit-reports-2026-09-29-30/` (numbers are
  the file prefixes; `INDEX.md` lists them all): notifications 35 (phone) and 36 (desktop); approval
  cards 48 (content, card counts) and 49 (how they feel in the apps); quick access and widgets 52,
  outside widget repos 53-54; GPU use 25 (backend), 26 (apps and defaults), 29 (8-32 GB first
  cards); settings 27 (backend) and 28 (apps); multi-model 30; outside suggestion checks 24, 31, 32;
  coverage map 37 and probes 38; permissions 39; update path 40; backups and deletion 41; supply
  chain 42; accessibility 43; time 44; phone background services 45; pairing and signed approvals 46;
  screen safety 47; test quality 50; memory 60 and disk storage 59. Reports 1-23 are the earlier
  (29 September) audits and worker notes; 33, 34, 51 and 55-58 are the build workers' notes. Re-derive line numbers from the code: they were read, not run.

### 5.2 Card experience + quick access  [owner-approved]
- **BUG (fairly sure, from code): a cancelled fingerprint kills the card buttons
  on the phone** - `ApprovalCard.kt` ~145 `decided` is set at tap and never reset
  when the risky-approval check is cancelled or refused (`MainActivity.approveItem`
  ~3133; `Verdict.Stop(null)`, `Security.kt` ~222). Fix: reset on failure or drive
  from `JarvisRuntime.deciding`.
- Notification tap scrolls to the wrong place (`HomeScreen.kt` ~992-998 `leading`
  does not count `quick-note`, `pc-media` and other items above the cards).
- `ReachBadge` (`ApprovalCard.kt` ~790) is an if/else so an outbound+irreversible
  card loses its "NO UNDO" cue. Buttons are not pinned on long phone cards
  (desktop pins them). Approve does not say a fingerprint follows. A card decided
  elsewhere slides the next card under the finger (id binding keeps it correct,
  but add a short guard). Routine cards are silent and expire in 3 minutes: add a
  quiet reminder when under 60 s remain. No "which task raised this" line.
- After any approve, one line says which Undo exists (inbox tidy 10 min, Forget
  a time frame 10 min, reminders "cancel that", model Roll back, settings off is
  instant; note writes and smart-home lights have none; irreversible cards say
  "This cannot be undone").
- Past approvals (Activity, `JARVIS-API.md` section 42) keep only title, decision,
  time, device: **add one non-sensitive summary line** (owner: yes), filters by
  decision/device, paging. The real row shape lives in the owner's
  `jarvis_gate.py` (not in this repo): field names are assumed - confirm on the PC.
- Setup cards in plain words: `jarvis_second_card.py` ~3032 says "a second copy
  of Ollama", shows an id and a port; the fallback card title for an unknown
  action is weak; "check PyPI, crates.io and GitHub" is jargon.
- Widgets: add sources "current task with Stop" and "approvals waiting" (never
  approve; "Hidden" under App lock; Stop reuses `/api/task/stop`); "graphics
  memory per card", "tokens per second" (marked not measured); edit a saved
  widget (today: delete and re-describe), more than 3 phone slots; per-widget
  transparency / accent / high contrast; a live preview before pinning; phone
  "Pin to home screen" (`ShortcutManagerCompat.requestPinShortcut`) for any Brain
  section or chat, opening behind App lock; more tile actions (Coming up, Look at
  this, Live). The five long-press shortcuts (Talk, Live, Note, Brief me, What did
  I miss) are static. A hint in both apps saying where the face-free chat is
  (desktop: the Jarvis bar, Alt+Space; phone: Appearance > face size "Hidden").
- "Talk about this in Live" share can still start Live once unlocked if another
  app fires it: make it open the Live screen with the shared text and wait for
  Start (like the tile now does).
- `widget_approval_info.xml` has no `previewLayout`.

### 5.3 Small items
- **Tap-to-talk on the phone** with a pause stop (Smart Turn), decided
  2026-09-28, never built: the phone Talk button is hold-to-talk
  (`ui/parts/VoiceButton.kt` 107-190), which blocks motor-impaired and Switch
  Access owners from voice. Words are still worked out on the PC after the voice
  check (a client must not do speech-to-text).
- "Delete older backups now" **button in both apps** after an Erase (backend
  route `POST /api/backup/delete-older` exists: one `change_own_config` card,
  fresh backup first, recovery code shown once; read `last_delete_older` and
  `pending_delete_older_card` from `GET /api/backup`; add its `check_parity.py`
  row only when the desktop calls it).
- Pairing: after the first phone turns on signed approvals, a standing "Retire the
  old shared key" prompt in both apps (today the shared key still approves
  risky cards from another mesh device with no check, ARCHITECTURE section 3);
  show the same four words (from `PairWords`, of the public key's hash) on the
  key-enrolment card and on the phone so a stolen device key cannot slip in.
- Test hardening: a per-patch "reads original text" ratchet (patches ordered
  after position 29 must materialise 0 lines except `cloud-say-yes.patch`); make
  `check("SKIP ...", True)` record a skip and list them; fail on CI if `git` is
  missing; add `gen_support_cases.py --check` to CI; print "N real-file suites ran"
  at the end of `apply-patches.ps1`; a test comparing
  `jarvis_reach._FALLBACK_ACTIONS` to the real gate table when present; pin
  time-dependent tests (`test_email_send`, `test_email_draft` use `datetime.now`;
  44 suites read `time.time()`).
- Stale-area check after every big merge (list areas changed since their last
  audit; the coverage map from this session is the template).
- Backend timers still on the wall clock: Undo windows also keep wall-clock
  `until` fields for display (monotonic guards were added); calendar events in a
  different time zone show at the wrong hour (`jarvis_briefing.py` ~680-702);
  "friday at 5pm" said on a Friday afternoon means next Friday (`jarvis_quick.py`
  ~476, looks intentional; decide).

### 5.4 Big first cards  [owner-approved]
- One-line suggestion in Brain > Model for a 16-32 GB first card ("your card can
  hold the 14B at 32K - try the Smartest preset"); change nothing by itself.
- With ONE big card and no second, let the no-preset path treat a 16 GB or larger
  first card as capable for Pictures / Wiki / Browser (`jarvis_second_card._detect`
  returns `capable:False` "only one graphics card found" today; presets already
  do this - `_detect_preset`). Each feature still off until approved with a card.
- Remove baked-in "12 GB"/"8 GB" wording: `jarvis_live_photo_test.py` ~379
  ("Install the 12 GB card"), `jarvis_live.py` CAMERA_NEEDS (done in #39, recheck),
  `jarvis_chatbot_local.py` NEEDS_SECOND, desktop `settings.html` ~1494 "the
  second card's own lane", phone `SecondCardPlate.kt` "Ollama".
- Under a chosen preset the 10/8 GB and Turing checks are skipped and a real third
  card looks absent (`_detect_preset`, `_third: None`); explain in words.
- `COMPUTE_BY_NAME` collisions when the driver lacks `compute_cap` ("RTX 50"
  matches "RTX 5000 Ada"; A-series cards match nothing) - low.
- The everyday model file `backend/jarvis-primary.Modelfile` is fixed at 8B / 16K
  (a 24-32 GB card is barely used unless the owner picks a preset); the preset
  catalogue stops at 14B/32K. Larger sizes only after measuring.
- Tests: no 32 GB case in `test_profiles.py`; `test_second_card.py` has no 16/24/32
  GB extra card; add them.
- The second card's master switch is not bound to a card id (only the third
  card's assignment is) - fix the same way.

### 5.5 Per-model thinking levels  [owner-approved incl. Auto]
Today `jarvis_agent.py` ~2652 `REASONING_OFF = {"reasoning_effort": "none"}` on
every chat request; small jobs send `"think": False`; `<think>` text is stripped;
no app shows thinking. Build: a setting per model (everyday model, second-card
lane's model, third-card lane's model) - Off / Quick / Deep / Auto; only levels
the loaded model supports (read from Ollama `/api/show` capabilities; this can
replace the `reasoning_effort` retry at `jarvis_agent.py` ~6272); default Off;
voice answers always fast; change needs no card; both apps show one row per
running model; changeable by voice/chat ("think harder"); Auto decides per
question and must be tested first (tool-eval style, `tools/tool_eval/`). Say in
plain words that thinking uses conversation room. Thinking text is never shown,
saved or learned from.

### 5.6 Multi-model work  [owner: failover first, then checker, then local compare]
Findings: no single "who does what" table; routing is spread over
`jarvis_agent.choose_lane` (picture, over-long conversation, combined), the
router (`rebuilt/jarvis_router.py`, cloud, nine gates), per-feature `lane_for`;
no mid-turn failover for chat lanes (only the learner falls back after 600 s);
no queueing/back-pressure; local models cannot check or compare each other;
compare (`jarvis_chatbot_compare.py`) is web/API chatbots only, sequential; thin
observability; "Stop everything" reaches compare but not verified for lanes 2/3.
Build (all off by default; approval card to turn on; measured first): **C:
failover** - if a lane errors or times out mid-answer, retry once on the main
card and say so in plain words (a fix, not a feature; test by killing the lane);
**A: checker** - the bigger local model reviews TOOL PLANS AND CODE only (never
chat), kept only if `tools/tool_eval/ollama_tool_eval.py` multi-step pass rate
gains >= 3 points for < 3 s; **B: local compare** - reuse compare with two local
roles, nothing leaves the PC; **per-lane measured log** (time to first token,
tokens/s, memory) beside the prompt-cache share in Brain > Model; a read-only
"who does what" roles table; one "Working together" section in the Second graphics
card page (both apps). No cloud model is ever a role in a plan that touches email,
files, credentials or memory. None of this is measured until the 12 GB card is in.
The plan card (`jarvis_plan.py`) stays off until `tools/tool_eval/tool_eval_results.json`
clears 90% multi-step and 0 injections.

### 5.7 Memory and storage  [owner-approved parts]
Facts: memory ~1.8 KB per fact (85% is the 384-dim float32 vector); brute-force
search 66 ms at 100k facts; retired/superseded facts keep their vectors and FTS
entries (by design); Erase is real (secure delete, vector and FTS removed, WAL
checkpoint) but **memory.db is never VACUUMed** (only the chat log is); recall
drops retired facts AFTER taking the top 50 so old versions can crowd out. ARCHITECTURE
section 5 says never compress facts or transcripts. Do: a size line in Brain
(`status()` gains `db_bytes`, retired-with-vector count, free pages) in both apps;
VACUUM/incremental_vacuum after an Erase (at most hourly); **measure** dropping
retired facts' vectors and int8 vectors with `backend/eval_memory.py` on the
owner's PC before keeping either; a soft "memory is large" note at 50,000 facts.
Storage: a read-only "What Jarvis is using" list in both apps (per store, honest
sizes; Ollama says "estimate"); Brain > Model lists installed models with size and
last use and offers **Remove behind one card** (never the model in use or its
rollback copy); gzip audit logs older than 7 days, delete at 90 (they hold tool
names and ids, no chat text); the update script offers to delete all but the
newest 2 `_jarvis-backup-*` folders after a green run; a size-based backup prune
is optional. Never compress old chats into archives (it would keep erased words).
Not checked: what a write does on a full disk (SQLite, backup temp file, logs);
real `.openjarvis` sizes; whether the old Kokoro v0.19 pack stays after upgrade.

---

## 6. Verified findings NOT fixed (so nothing is lost)

**Owner-side, not code:**
- Obscura install pin: `jarvis_obscura.py` `PINNED_DIGEST = ""` (the release zip's
  hash was read from a page, not hashed). MiniCPM-V pin: `jarvis_screen_picture.py`
  `PINNED_DIGEST = ""` (trust on first use); its licence (reported Apache-2.0)
  and tag are unverified. **Owner: run `Get-FileHash` once and paste the digest**
  (they asked "what is a checksum?" - a fingerprint of a file; explained; they said
  "yes, later"). Give them the exact one-line commands when they are ready.
- SearXNG docker line uses `:latest` (`backend/README.md` ~9798): pin an `@sha256:`.
- No Gradle dependency lock / `verification-metadata.xml` (needs a machine that can
  reach dl.google.com; CI could generate it). CI `npm install playwright` is
  unpinned (no version anywhere in the repo).
- Desktop CSP still has `script-src 'unsafe-inline'` (12 inline scripts: theme guard
  on 8 pages, onboarding, `faces.html` 388 KB block, two in `jarvis_hud.html`;
  Playwright tests, `tools/shader_size.py` and `scripts/build-resolve-vectors.mjs`
  read `faces.html`'s inline script). Tauri hashes inline scripts in packaged
  builds already. Do it only with a browser to test.
- Android permissions were reviewed: fine (SMS is only a `<queries>` entry to
  refuse reading the default SMS app). `PACKAGE_USAGE_STATS` and
  `SYSTEM_ALERT_WINDOW` are optional features. The old `jarvis-android` app still
  declares extras and cannot talk to the backend (stop shipping it).
- `docs/SOURCE-BUNDLE.md` (13 MB, generated) was not regenerated.

**Code, low to medium:**
- Screen: a password behind a show-password eye has no pattern (said in the docs);
  non-English labels and text inside images are not caught; `look`/`ask` need no
  key press at the backend (the token's normal power, accepted); Chrome's
  `IsPassword` may read False when accessibility is off; the picture reader's
  Ollama keeps its last prompt in cache (no way found for another request to read
  it); Pictures lane `think:false` behaviour on `qwen2.5vl:7b` untested.
- Backups: no writer-pause hook, so a restore still needs a Jarvis restart; backups
  are manual only (no "backup is old" nudge, no success/failure notification); no
  "verify this backup opens" button; no size-based prune; old/new schema version
  not checked on restore; folder problems (removed drive, full disk, spaces, network
  drive) lightly handled and untested.
- Deletion: an erased fact's words survive in up to five older backups (disclosed on
  the restore card); crisis turns in memory/backup and whether the phone's captured
  notifications clear when the switch goes off were not verified.
- Pairing/approvals: a phone blocks Deny on a stale link (stricter than rule 4
  needs); card expiry `expires_in` comes from `time.time()`; an orphan device row
  if a `collect` reply is lost; a stamp lives up to 15 minutes if the handler then
  refuses; `POST /api/pending/<id>/amend` note is not in the signed hash; phone app
  merge "shows the whole change" not verified; the backend server file
  (`jarvis_hud.py`) is not in the repo, so unauthenticated-route checks stop there.
- Time: phone alarms depend on the PC stream; "Missed at HH:MM" shows the PC's
  zone, no date; timers/alarms are absolute epochs (forward clock steps fire early);
  DST tests skip on Windows (`test_schedule.py` ~140, 170; `time.tzset`);
  `test_briefing.py` etc. were pinned, others not.
- Accessibility: desktop text 10-11 px in places (`--text-2xs/xs`, widget buttons
  11 px); 200% zoom reflow of the 320 px widget unchecked; widget reachable only by
  hotkey for keyboard/screen-reader use; approval countdown expiry not announced;
  35 JS-built `div`/`span` elements not audited for keyboard use; brain graph
  (`galaxy-view.js`) keyboard use unchecked; phone font-scale not tested; touch
  targets checked only on shared controls.
- Phone services: Watch cannot pause on password boxes in ordinary apps (a stated
  limit); `WakeWordService.goForeground` republishes its notification on every
  recorder reopen; `onTaskRemoved`/`onTrimMemory` not implemented; no
  `filterTouchesWhenObscured` (approvals are in `MainActivity`, not audited for
  tapjacking); `BootReceiver` MY_PACKAGE_REPLACED foreground-start exemption on
  Android 12-14 unverified; battery/doze behaviour needs a device.
- Tests: the stand-in `_stack.py` starts from an empty file and MATERIALISES the
  original text when a hunk does not apply, so it can hide a bad hunk (this
  produced my `screen.patch` mistake). 125 of 310 hunks depend on original text the
  repo does not hold; the only real proof is `apply-patches.ps1` on the owner's PC
  (19 backend suites skip in CI for that reason: gate egress, gate outcomes, memory
  safety, extraction wiring...). `run_suites.py` prints skips as passes inside suites
  (`check("SKIP ...", True)` in 62 suites).
- Models on disk are unmanaged (est. 5-20 GB); the Kokoro v1.0 pack (350 MB) and
  an old v0.19 pack may both stay.
- The board and slot claims in Gemini's text (a B550 board, the second card in a
  PCIe 3.0 x4 slot) are NOT in the docs; the 2060 12 GB is not installed.

---

## 7. What the owner still has to do (needs their PC or phone)

1. Run the update (section 2) and report green / yellow / red.
2. Rebuild the desktop app; install the phone app from `client-latest`.
3. Try the things nobody has run for real: Preflight, "Look at this" and "Watch with
   me" (`tools\check_screen_safety.py`), Kokoro v1.0 "Hear it" samples, phone
   notifications, the phone home-screen widget on a real launcher, the animals on
   the phone. `docs/UPDATE-AND-CHECK-2026-09-28.md` has the list.
4. Get and paste the two checksums (Obscura zip, MiniCPM-V).
5. When the RTX 2060 12 GB is installed: measure it (`docs/MODEL-TOPOLOGY.md`),
   then the multi-GPU numbers can stop being "calculated". Also the 60-frame cap
   measurement (one PowerShell line, waiting since 2026-09-29), the memory
   self-test on the PC (`backend/eval_memory.py`, `eval_learner.py`).
6. Pick an `apply-patches` follow-up if it fails (paste the last 40 lines).

---

## 8. How this work has been run (lessons that will save you time)

**Environment**
- No local Android compiler (`dl.google.com` blocked): **GitHub Actions is the only
  Kotlin compiler.** The phone build/test/smoke jobs live in a SEPARATE workflow,
  `Jarvis client` (`.github/workflows/jarvis-client.yml`), which is NOT in the pull
  request's usual check list and only runs when `jarvis-client/` files change.
  **Always read it** (`actions_list list_workflow_runs` with `resource_id
  jarvis-client.yml`, branch filter). It failed silently on my earlier pushes
  (4 test bugs) while the main CI list looked fine. `get_job_logs` with
  `tail_lines` 400 shows the failing test names ("Failing tests" group).
- The container is `Linux`, ~10 GB writable allowance: **it ran out of disk once**
  (trial worktrees, cargo `target`, three GB worktrees). Remove finished
  `.claude/worktrees/agent-*` (`git worktree remove --force`) before starting.
- `python3` here has a broken `cryptography` package (import panic): use a clean
  venv (`python3 -m venv <dir>`, then `pip install` numpy, sherpa-onnx,
  onnxruntime, cryptography, pillow and whatever a failing suite names; CI pins
  numpy 2.5.3, sherpa-onnx 1.13.8, onnxruntime 1.30.0, cryptography 50.0.1).
  The old venv lived in the session's scratchpad and may be gone.
- Run the full suite with `python3 backend/run_suites.py` (it isolates settings);
  a single suite run from `backend/` can pick up leftovers and fail
  (`test_agent.py` fails 5 `tidy_inbox` checks alone on unmodified `main`).
  Do NOT run other test batches at the same time (a run overlapping a disk-full
  moment failed `test_apply_outcomes`; alone it passes 59/59). About 35 minutes.
- Rust: `rustup toolchain install stable --profile minimal -c clippy -c rustfmt`,
  `rustup target add x86_64-pc-windows-msvc`, then `cargo fmt --check`, `cargo check
  --target x86_64-pc-windows-msvc --all-targets`, `cargo clippy ... -D warnings`
  (about 3 minutes cold). `cargo test` only runs in CI (Windows).
- PowerShell 7 at `/opt/pwsh/pwsh` (the owner has 5.1: no `??`, no ternary, ASCII
  only in the script; the `powershell-5` CI job runs the real 5.1).
- Playwright/Chromium cannot run here; desktop `.mjs` tests that need no browser can.
- GitHub MCP tools are deferred and disconnect now and then: load them with
  `ToolSearch select:mcp__github__pull_request_read,...`. `pull_request_read
  get_files` output can be huge (saved to a file: parse with python).
- A "stop hook" complains about unpushed commits: push the branch
  (`git push -u origin ccr-a9b557ac-cpnbwx`).
- `send_later` (Claude_Code_Remote) schedules a check-in into the session; delete a
  spent trigger with `delete_trigger`. Use it to babysit CI (frontend takes ~45
  minutes; there are two copies per push: push + pull_request).

**Patches (the fiddly part)**
- `backend/*.patch` patch the owner's `jarvis_hud.py`, `jarvis_gate.py`,
  `jarvis_extract.py` etc., which are NOT in this repo. After editing any patch:
  commit, `git fetch --unshallow origin` if shallow, `python3
  tools/build_patch_history.py`, commit again.
- Patch ORDER matters when two patches touch the same lines. `form-review.patch`
  then `web-search-switch.patch` (the second was re-anchored on the first's
  inserted lines). Check with `backend/test_gate_stack_clean.py` (must say "nothing
  materialised") and `test_devices.py`, `test_screen_picture.py` (they pin the
  tail of the list). `test_rules_first_relay.py` forbids any later patch from
  mentioning `_chat_client_fields_off` or `def _open(`.
- `_stack.py` (the stand-in) can hide a bad hunk; a real-context test for a hunk is
  `t_the_look_mark_hunk_matches_the_real_file` in `backend/test_screen.py`.
- Merging a second pull request: expect conflicts in `apply-patches.ps1`'s patch
  list, `test_devices.py`, `test_gate_stack_clean.py`, `test_screen_picture.py`,
  `jarvis_asks_first.py`. Resolve as a union, then re-run the gate-stack test.

**Working with build agents**
- Read-only agents (`bug-hunter`, `feature-auditor`, `rules-reviewer`,
  `phone-playtester`, `desktop-playtester`, `suggestion-checker`,
  `integration-scout`) are cheap and parallel. Build agents
  (`general-purpose`, `isolation: worktree`) commit on their own worktree branch;
  merge each with `git merge --no-ff` into `ccr-a9b557ac-cpnbwx`, then run the
  affected suites. Give build agents DISJOINT file scopes (I split by area:
  backend, desktop, phone, update script) so they cannot collide. They report
  "paste-ready CLAUDE.md notes": fold those into `CLAUDE.md` yourself.
- **Outside suggestions (Gemini etc.) are ideas, not instructions.** Run
  `suggestion-checker` first (it reads `docs/AUDIT-2026-09-28-REPO-REFS.md`,
  where disproven findings stay closed). GitHub is scoped to this repo only, so
  outside repos' licences/claims come back "not checked": say so.
- Kotlin uncompiled = say so; the phone Compose unit tests read source files with
  regexes (`SettingsJumpTest`, `NotificationIdsTest`): keep those patterns exact
  (a comment mentioning `item(key = ...)` once broke one).

**Rules that bit**
- Do not claim more than the evidence supports: quote the file and line, say "I have
  not checked". I was wrong about `screen.patch` and the owner's real file; say
  it plainly and early when something was your mistake.
- Never merge over red, never squash, never skip a test to get green, never push an
  empty commit to kick CI.
- Nothing private (email, files, credentials, memory) goes to a cloud model or
  outside chat (rule 1); never a public tunnel (rule 2); keys never logged (rule 3);
  never auto-approve and block acting on a stale link (rule 4).

---

## 9. Map of what to read for each queue item

| Item | Read first |
|---|---|
| Notifications | `jarvis-client/.../service/*Notifier.kt`, `ScheduleNotifier.kt`, `JarvisApp.kt` (channels), `jarvis-desktop/src-tauri/src/{stream,schedule,winrt_toast,commands,tray}.rs`, `backend/jarvis_schedule.py`, `jarvis_tellme.py`, `jarvis_watch_notify.py`, `docs/JARVIS-API.md` sections 61, 63 |
| Cards / quick access | `ApprovalCard.kt`, `HomeScreen.kt`, `widget/*`, `res/xml/{shortcuts,widget_*}.xml`, `jarvis-desktop/src/{widget,main}.js`, `backend/jarvis_widgets.py`, `JARVIS-API.md` sections 42, 86 |
| Second card / big cards | `backend/jarvis_second_card.py` (3,500 lines), `jarvis_hardware.py`, `jarvis_profiles.py`, `docs/MODEL-TOPOLOGY.md`, `docs/SECOND-CARD.md`, `docs/GPU-SUPPORT-RESEARCH-2026-09-27.md`, `docs/HARDWARE-PROFILES.md` |
| Thinking / multi-model | `backend/jarvis_agent.py` (~7,000 lines: `choose_lane`, `REASONING_OFF`, `run_local_turn`), `rebuilt/jarvis_router.py`, `jarvis_chatbot_compare.py`, `jarvis_chatbot_local.py`, `tools/tool_eval/`, `docs/CHATBOT-DRIVER-DESIGN.md` |
| Memory / storage | `backend/rebuilt/jarvis_memory.py`, `jarvis_chat_log.py`, `jarvis_backup.py`, `jarvis_tidy.py`, `docs/ARCHITECTURE.md` section 5, `docs/MEMORY-RESEARCH-2026-09-26.md`, `docs/MEMORY-SCOREBOARD.md`, `jarvis_data_health.py`, `jarvis_pc_help.py` |
| Update / patches | `scripts/apply-patches.ps1` (~2,500 lines), `backend/_stack.py`, `backend/test_apply_outcomes.py`, `backend/test_apply_line_endings.py`, `docs/UPDATE-AND-CHECK-2026-09-28.md` |
| Pairing | `backend/jarvis_devices.py`, `jarvis_owner_check.py`, `docs/PAIRING-DESIGN.md`, `docs/APPROVAL-GAP-DESIGN.md` |
| Screen | `backend/jarvis_screen*.py`, `jarvis_secrets.py`, `jarvis_picture.py`, `docs/SCREEN-DESIGN.md`, `tools/check_screen_safety.py` |

---

## 10. Cost note (asked by the owner)

Estimated $25-$85 for everything queued, most likely about $45 (Sonnet 5.5 pricing
per 1M tokens: cache reads $0.20, cache writes $2.50, input $2, output $10). A
big build agent is roughly $1-4 and an audit or check $0.2-1; a long conversation's
re-reading of its history is a real part of the total, so **start a fresh
conversation for each queue item** and keep audits short. This is an estimate, not
a measurement: the real figure is on the owner's usage page.
