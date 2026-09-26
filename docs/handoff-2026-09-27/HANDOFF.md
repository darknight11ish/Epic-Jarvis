# Handoff - continue the Jarvis work in a new Claude Code conversation (2026-09-27)

Read this whole file first, then `CLAUDE.md` (binding - including the owner's
answers of 2026-09-27 near its end). Everything below was checked at the time
of writing; re-check anything you rely on.

## 1. Where things are

- **All work is on branch `claude/admiring-ritchie-5urg5h`** (pushed), and in
  pull request **darknight11ish/Epic-Jarvis#17** into `main`
  (https://github.com/darknight11ish/Epic-Jarvis/pull/17). The branch already
  contains `main`'s launch-video commits, so the PR merges cleanly. **Once the
  owner presses Merge, `main` has everything**, and a new conversation can
  simply start on `main` (and branch from it).
- **Nothing is left unmerged.** The two pieces saved as patches earlier
  (smarter tools; the ease-of-use "do first" fixes) are merged. The short
  tool list's clash with the new `my_files` tool was fixed by giving
  `my_files` its own "documents" group.
- **Last local checks (after the final merge):** backend `run_suites.py`
  111 passed, 0 failed, 19 skipped (they need the owner's PC files); all
  `gen_*_cases --check`, `check_parity`, `build_patch_history --check`,
  `gen_notices --check` clean; `apply-patches.ps1` parses; Rust fmt + Windows
  clippy clean (after the ease merge; smarter tools touched no Rust). The
  desktop test result is in section 6.
- **GitHub CI:** check the newest runs on the branch/PR first (section 7).

## 2. The owner's decisions

All answered on 2026-09-27 and written in `CLAUDE.md` ("Decided 2026-09-27,
the owner's answers"). `docs/OWNER-QUESTIONS-2026-09-27.md` is the record of
what was asked. **There are no open owner questions right now.**

## 3. What to build next, in order

Follow `docs/FEASIBILITY-AUDIT-2026-09-26.md` §3-4 and CLAUDE.md. Each batch
gets its own feature audit (standing rule). Decided and waiting to be built:

1. **Small fixes that follow directly from the answers:** web search ships on;
   drop the focus streak line; phone accepts home-network addresses (Android
   `network_security_config.xml` only allows cleartext to `.ts.net`/`.nord`
   today - the app's own `OwnNetwork` check must stay the gatekeeper; think
   this through carefully, it is a security change); crisis help line (US:
   988 / 911) + crisis messages never learned (wellbeing report W1-W6,
   `docs/CUTTING-EDGE-2026-09-26-round4-wellbeing.md`); games/role-play in a
   temporary chat; smartwatch setting (default phone-only, a card to allow).
2. **Email drafts** (a card every time, full text) - feasibility I53.
3. **UI "do first" list** (`docs/UI-AUDIT-2026-09-26.md` §3) with the answers:
   HUD uses theme colours, widget Approve matches the bar, phone keeps its font.
4. **Ease-of-use "then" list** (`docs/EASE-OF-USE-AUDIT-2026-09-27.md` §3,
   items 10-21) with the answers: reading tools switchable from the PC (card
   + Windows Hello), past-approvals list (needs the owner's `jarvis_gate.py`),
   chat-history search box, "Things you can say" (I116).
5. **Memory:** Erase also offers deleting the chat it came from; re-ranker
   score floor (only if the PC test shows it helps); inside jokes list;
   "from now on" style changes at once with Undo; humour switch (off).
6. **Backups:** one locked file (age format + recovery code shown once) into a
   folder the owner picks, NordLocker included; keep the last few; restore is
   a card + Windows Hello (`docs/CUTTING-EDGE-2026-09-26-round2-trust.md` idea 2).
7. **The 31 small items** (feasibility §2 "Now" rows), then news headlines /
   "tell me when this page changes" (safe version), media keys (no card).
8. Later: plan card (after multi-step safety tests), the 12 GB card's jobs
   (after it is installed and measured), phone notifications (after the
   security audit), "more devices" / QR pairing.

## 4. Audits the owner asked for that are NOT done yet

The owner asked for all of these; do them as **three combined team passes**
(cheaper than ten separate ones, and the earlier audits overlapped):
- **Security, privacy and dependencies pass:** the full security & privacy
  audit of all of Jarvis, dependencies & licences, the hash-locked install
  switch-over (`docs/DEPS-TESTS-CI-AUDIT-2026-09-26.md`).
- **Setup, settings and recovery pass:** settings audit, install
  walkthrough, failure & recovery, first-run guided setup design.
- **Quality pass:** scaling (one vs two cards), feature-set clashes, full gap
  audit, accessibility + plain words, performance + battery, test quality,
  CI/release, memory effectiveness.
Then the GitHub repo tidy-up audit, and **last of all** the Gemini audit
package (only when nothing else is running).

## 5. Things to tell the owner (from this round's builders)

- Email reading now checks the mail server's certificate (it did not before).
  If reading email fails after updating, that is the likely cause.
- `OLLAMA_NO_CLOUD=1`: installing a model from the phone is not yet verified
  to still work - check on the PC.
- Screenshot text uses Windows' own text recognition - never run yet.
- Pocket TTS ignores the speaking speed (measured).
- Short tool list, memory re-ranker and the voice upgrades all ship OFF until
  the PC measurements say they help.

Owner PC to-dos (one line each, in the docs named): memory self-test
(`docs/MEMORY-SCOREBOARD.md`); tool test
(`py -3 tools\tool_eval\ollama_tool_eval.py --models jarvis-primary`, from the
repository folder); voice bake-off (`backend/README.md`, "Voice upgrades: the
bake-off"); dependency freeze (`docs/DEPS-TESTS-CI-AUDIT-2026-09-26.md`);
apply-patches after updating; set `draft_email = "ask"` in their own
`jarvis-framework.toml`; add `"my_files"` to `[tools] enabled`; send copies of
`jarvis_undo.py`, `jarvis_ledger.py`, `jarvis_watch.py`, `jarvis_persona.py`,
`jarvis_gate.py`; make the updater signing key (professionalism audit #2).

## 6. Last desktop test run

See the commit that adds this file: its message states the full desktop
test result on the merged branch.

## 7. How to work here efficiently (lessons from the last session)

- **At most 3-4 builders at once.** Seven in parallel filled the disk and
  made every test run slow. Give each builder `CARGO_TARGET_DIR=/home/user/Epic-Jarvis/jarvis-desktop/src-tauri/target`
  and remove merged worktrees (`git worktree remove --force`).
- **Reserve doc section numbers per builder up front** (JARVIS-API is at §37;
  the next free is §38), and tell each builder to put its README section in a
  named place - parallel builders kept colliding there.
- Builders in worktrees may start from an OLD base: every brief starts with
  `git fetch origin <branch> && git reset --hard origin/<branch>`. They never
  push or merge. Verify every claim they report before relaying it. Merge one
  at a time; run the checks BEFORE committing a merge.
- Generated fixtures can go stale when another merge changes backend status
  (e.g. `tools/gen_memory_words_cases.py`) - rerun all `gen_*` checks after
  every merge.
- **Checks:** `python3 backend/run_suites.py`; `for g in tools/gen_*_cases.py; do python3 $g --check; done`;
  `python3 tools/check_parity.py`; `python3 tools/build_patch_history.py --check`;
  `python3 tools/gen_notices.py --check`; Rust
  `cd jarvis-desktop/src-tauri && cargo fmt --check && cargo clippy --target x86_64-pc-windows-msvc --all-targets -- -D warnings`;
  desktop `node jarvis-desktop/tests/<name>.mjs` (Playwright from
  `/home/user/node_modules` if present), then always
  `git checkout -- jarvis-desktop/tests/shots`. `tools/quickchecks.sh` here
  runs the drift checks.
- **Phone:** compiles only in GitHub Actions (~15 min). `tools/run-main.sh` +
  `build-main.sh` here are a local JVM runner for the phone's plain Kotlin;
  re-download kotlinc and the kotlinx-serialization / junit / coroutines jars
  and re-point the paths inside them in a new container; add new pure
  `net/*.kt` files to `run-main.sh`'s list.
- **Pushes cancel running CI** of the same workflow; the phone workflow runs
  only when `jarvis-client/**` (and a few shared files) change. Push less often.
- PowerShell for the owner: one line, 5.1-safe, tested with `/opt/pwsh/pwsh`.
- Never put the owner's email address in any request; fake secrets in tests
  are built by concatenation; commit trailers as CLAUDE.md / the session says.
