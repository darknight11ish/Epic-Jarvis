# Handoff - continue the Jarvis work in a new Claude Code conversation (2026-09-27)

Written at the end of the overnight session of 2026-09-26/27. Read this whole
file first, then `CLAUDE.md` (binding), then `docs/OWNER-QUESTIONS-2026-09-27.md`.

## 1. Where things are

- **Branch:** `claude/admiring-ritchie-5urg5h` (pushed). All work is there.
  `main` on GitHub is still old; the owner decided to bring it up to date
  with ONE pull request after the bug-audit fixes (they have landed - see 6).
- **Last full local check on the branch head:** `python3 backend/run_suites.py`
  107 passed, 0 failed, 19 skipped; all `tools/gen_*_cases.py --check` clean;
  `tools/check_parity.py` clean; `tools/build_patch_history.py --check` clean;
  Rust `cargo fmt --check` + Windows-target clippy clean (checked after the
  quick-wins merge; the voice merge touched no Rust); desktop tests near every
  merged change pass; phone plain-Kotlin tests pass (184 in the last run).
- **GitHub CI:** the phone build ("Jarvis client") was green on every run
  checked overnight (runs 91-94). The push made with this handoff starts new
  runs - **check them first** (see 7 for how).

## 2. What landed overnight (all merged and pushed)

Research and audits (all in `docs/`):
- Cutting-edge research rounds 3 and 4 (`CUTTING-EDGE-2026-09-26-round3-*`, `-round4-*`).
- **Feasibility audit** of 156 ideas, 7 reviewers incl. security:
  `FEASIBILITY-AUDIT-2026-09-26.md` + `feasibility-2026-09-26/`. Its section 3
  is the build order being followed; section 4 the "keep Jarvis simple" rules.
- **UI audit** `UI-AUDIT-2026-09-26.md` + `ui-audit-2026-09-26/` (with
  `ui-mockups.html`, a before/after picture page).
- **Memory review** `MEMORY-REVIEW-2026-09-27.md` (19 verified bugs).
- **Ease-of-use audit** `EASE-OF-USE-AUDIT-2026-09-27.md` + `ease-audit-2026-09-27/`
  (scores: setup 2/10, customizing 5, everyday 5, reviewing the past 4, recovery 4).
- `MEMORY-SCOREBOARD.md` (numbers after each memory change + the owner's PC line).

Built:
- file_read refuses keys/passwords/browser data/Jarvis's own data, and opens
  exactly the resolved path it checked.
- Engine: a model that cannot use tools gets no tools and a true message;
  `OLLAMA_NO_CLOUD=1` on the second card and in the one-line PowerShell.
- Fix pass A (desktop + phone bug fixes, "Mind" -> "Brain", late alarms,
  App lock on notes, no fallback to this PC, Stop everything in the tray...).
- Memory ideas 1-4 (re-ranker - now OFF by default until the PC test shows it
  helps -, bigger self-test, "said again", real "true from" dates) and then
  the memory review's backend fixes (B1-B15, B17, improvements I1, I3-I7,
  I12, I13; I2 dropped by measurement) and app screens (B16, B19, I8-I11).
- Step 0 of the feasibility order: taint survives a restart (security G1),
  draft_email ships as "ask", file_read list holes (G2), prompt-reuse numbers
  (I03), hash-locked `backend/requirements.lock` + a Python advisory CI job
  (NOT yet what apply-patches installs - see DEPS audit doc).
- Quick wins: HA weather in the briefing (+ non-admin HA user doc), "Also on
  my phone" (phone only), reading the words in a screenshot on the PC (marked
  outside text by the backend), both graphics cards' health.
- Documents & email: "Folders Jarvis may look in", the `my_files` tool (PDF,
  Word, Excel, PowerPoint via MarkItDown doc extras only, run as a separate
  process), the Notion import, instant "tell me when" for email (IMAP IDLE),
  "tell me if X hasn't replied by Friday". Email drafts NOT built (owner Q1).
  **Security fix found here:** Python's imaplib did not check the mail
  server's certificate; every IMAP connection now does (`jarvis_email.tls_context`).
- Voice upgrades as a bake-off (Pocket TTS, a newer "hey Jarvis" detector,
  both OFF, judged by `jarvis_bakeoff.py` on the PC) and speaking speed in both apps.
- Desktop look bugs (undefined CSS variables, onboarding's wrong colours) + a
  new `tests/css-vars.mjs`.
- Test fixes: approval-contract `_RISK` reader (reported by the brag session),
  a clock-dependent preflight test.

## 3. Two finished pieces of work NOT merged yet - do these first

Both were built and tested by their builders, but conflict with the branch.
They are saved as patch files here (the builders' own branches only existed
in the old container):

- `patches/smarter-tools/0001-*.patch` - tool/behaviour test (I05+I95+I133),
  the short tool list (I06, ships OFF), the MCP plug-in bridge moved into
  `backend/` (stdio only, read-only, a card when a server is added/changes).
- `patches/ease-fixes/0001-*.patch` - the ease-of-use audit's "do first"
  items 1, 2, 5, 6, 7, 8 (untrue wording fixed, starting-Jarvis words, one
  wording pass in both apps, selectable error text, history weekday + filter,
  docs and check-tool fixes).

Apply each with `git am -3 docs/handoff-2026-09-27/patches/<name>/*.patch`.
Expected conflicts, and how the same ones were resolved before:
- **Lists** (`backend/_where.py` SHIPPED, `scripts/apply-patches.ps1`,
  `docs/ARCHITECTURE.md` §8 tables, preflight name lists): keep BOTH sides.
  `tools/union.py` in this folder does "both" for a file.
- **`backend/README.md`:** keep the branch's side of every conflict, then
  append the patch's own new sections (take them from the patch's version of
  the file: `git show :3:backend/README.md` during the am, from the section
  heading to the end).
- **`docs/JARVIS-API.md`:** the smarter-tools patch numbers its section **35**;
  35 is taken (folders) and 36 too (picture words). Make it **§37** (headings
  and `### 35.x` -> `### 37.x`) and fix its two "(section 35)" references in
  §4-ish text about the plug-in programs' cards.
- **`tools/tool_eval/README.md`:** take the patch's rewrite.
- **After smarter-tools applies, two tests FAIL** (`test_short_tool_list.py`,
  `test_tool_eval.py`): the documents work added a new tool, `my_files`,
  that the short list does not know. It must get exactly one home (a
  `more_tools` group, e.g. "files"; it is only offered while a folder is
  listed), the pinned token budget (1,450) must be re-checked, and the tool
  test's expected first-request list updated. Do not raise the budget just to
  pass; measure with `estimate_tokens`.
- **Ease-fixes** conflicts in `backend/selftest.py` and
  `backend/test_selftest_preflight.py` (the preflight check list: keep every
  check from both sides - folders, instant_email, home, and its new
  "PC sleeps on mains power" warning).
Run the full checks (section 7) before committing each.

## 4. Things to tell the owner (not yet acknowledged by them)

1. The imaplib certificate problem above - fixed; if reading email suddenly
   fails after updating, this is the likely cause.
2. **The phone cannot reach home-network addresses** (192.168.x.x, `.local`)
   although the 2026-09-26 own-networks decision allows them: Android's
   network config in the app only allows cleartext to `.ts.net` and `.nord`.
   The ease-fixes patch corrects the wording; making home addresses work is
   the owner's call.
3. `OLLAMA_NO_CLOUD=1` - not verified that installing a model still works;
   check on the PC.
4. Reading screenshot text uses Windows' own text recognition; never run.
5. Pocket TTS ignores speaking speed (measured).

## 5. The owner's open questions and PC to-dos

`docs/OWNER-QUESTIONS-2026-09-27.md` has ~27 short multiple-choice questions,
recommended answer first. Ask them TWO at a time (CLAUDE.md). The most
important: email drafts (card every time?), MCP "local" meaning, NordLocker
backup, the 31 small items, go-ahead on the UI "do first" list, crisis help
line country, web search on by default. Add from the builders' reports:
- the short tool list and the re-ranker are both OFF until the PC tests
  measure them (not questions - measurements);
- "Also on my phone" and MCP card-on-change (feasibility Q9) are built to the
  recommended answer;
- home-network addresses on the phone (item 4.2).
Record every answer in CLAUDE.md with the date, as before.

Owner PC to-dos (one line each, in the docs named):
- memory self-test: `docs/MEMORY-SCOREBOARD.md`;
- tool test: `py -3 tools\tool_eval\ollama_tool_eval.py --models jarvis-primary`
  (from the repository folder);
- voice bake-off: `backend/README.md`, "Voice upgrades: the bake-off";
- dependency freeze for the hash-locked install: `docs/DEPS-TESTS-CI-AUDIT-2026-09-26.md`;
- apply-patches after updating; set `draft_email = "ask"` in their own
  `jarvis-framework.toml`; add `"my_files"` to `[tools] enabled`;
- send copies of `jarvis_undo.py`, `jarvis_ledger.py`, `jarvis_watch.py`,
  `jarvis_persona.py`, `jarvis_gate.py` (needed before extending them);
- the updater signing key (professionalism audit #2) - 10 minutes.

## 6. What comes next (in order)

1. Merge the two patches (section 3), full checks, push, watch CI.
2. Open the ONE pull request from this branch to `main` (the owner decided
   this; they press Merge). Use the repo's PR template if one exists.
3. Ask the owner's questions two at a time; record answers in CLAUDE.md.
4. Then, per `FEASIBILITY-AUDIT-2026-09-26.md` §3: email drafts (after Q1),
   the UI "do first" list (after its question), step 5 small items (after the
   queue question), the ease audit's "then" list, the full security & privacy
   audit, then "more devices" / QR pairing, then phone notifications.
5. Every feature batch gets its own audit (CLAUDE.md standing rule).

## 7. How to work here (what the last session learned)

- **Checks:** `python3 backend/run_suites.py`; `for g in tools/gen_*_cases.py; do python3 $g --check; done`;
  `python3 tools/check_parity.py`; `python3 tools/build_patch_history.py --check`;
  `python3 tools/gen_notices.py --check`; Rust: `cd jarvis-desktop/src-tauri && cargo fmt --check && cargo clippy --target x86_64-pc-windows-msvc --all-targets -- -D warnings`;
  desktop: `node jarvis-desktop/tests/<name>.mjs` (Playwright resolves from
  `/home/user/node_modules` if present), then ALWAYS
  `git checkout -- jarvis-desktop/tests/shots` (never commit it).
  `tools/quickchecks.sh <repo dir>` here runs the drift checks.
- **Phone:** compiles only in GitHub Actions (~15 min). `tools/run-main.sh`
  and `build-main.sh` here are a local JVM runner for the phone's plain
  Kotlin; they need kotlinc and the kotlinx-serialization/junit/coroutines
  jars at the paths inside them - re-download and re-point them in a new
  container, and add any new pure `net/*.kt` file to `run-main.sh`'s list.
- **PowerShell:** `/opt/pwsh/pwsh` (reinstall line in CLAUDE.md). One line,
  5.1-safe, for the owner.
- **Disk:** builder worktrees each grow a Rust `target/` (3 GB+). The disk
  filled once and broke a test run. Remove merged worktrees
  (`git worktree remove --force`), and have builders use
  `CARGO_TARGET_DIR=/home/user/Epic-Jarvis/jarvis-desktop/src-tauri/target`.
- **Builders in worktrees** may start from the OLD main: every brief starts
  with `git fetch origin claude/admiring-ritchie-5urg5h && git reset --hard origin/claude/admiring-ritchie-5urg5h`.
  Tell them not to push or merge; verify every claim they make before
  relaying it; merge one at a time with full checks.
- **Merge traps seen:** parallel builders pick the same JARVIS-API section
  number (renumber the later one and fix references); README sections
  collide at the end (keep ours, append theirs); generated fixtures go stale
  when another merge changes backend status (`tools/gen_memory_words_cases.py`).
- **Pushes cancel running CI** of the same workflow; the phone workflow only
  runs when `jarvis-client/**` (and a few shared files) change.
- Commit trailer (exactly):
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_015UUeD3W4kG7RWyUe7qR4bc`
  (a new session will be given its own session line - use that one).
- Never put the owner's email address in any request; fake secrets in tests
  are built by concatenation.
