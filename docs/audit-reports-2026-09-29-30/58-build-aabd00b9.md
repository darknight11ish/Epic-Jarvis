# Report 58 (build), agent aabd00b9, 2026-09-30T07:48Z

> **What it was asked** (first 600 characters of the task): You are in a git worktree of Epic-Jarvis (branch based on the current work; a parallel agent edits scripts/apply-patches.ps1; other agents edit jarvis-desktop/ and jarvis-client/ and jarvis_second_card.py/jarvis_agent.py: do NOT touch those). Read CLAUDE.md fully first (rules, plain words for a beginner owner, both-apps rule, patch-history rule: after changing any backend/*.patch commit, git fetch --unshallow origin if needed, run python3 tools/build_patch_history.py, commit again; 'do not claim more than the evidence supports'). Do NOT push or open a PR; commit on your worktree branch, report

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Branch `worktree-agent-aabd00b9f18c47fd4`, commit 81afa6c0. Full `backend/run_suites.py` in the clean venv: 204 passed, 0 failed, 19 skipped (owner-PC-only files). `tools/check_parity.py` is clean. No `.patch` was touched, so no patch-history run was needed. Not pushed. Each new test was run against HEAD's old module; it failed there and passes now.

**Changes by file**
- `jarvis_secrets.py`: scan limit 80,000 -> 25,000 characters, budget 10 -> 6 s, clock checked every 32 matches inside a rule. A 70k dense screen now fails closed in under 1 s, and a 25k dense scan does not stall a ticker thread. New patterns: `DB_PASSWORD=`/`API_SECRET_x=`, `Passwort:`/`Kennwort`, "password hunter2" (needs a digit) and a bare label above its value, `Authorization: Bearer`, US SSN (new `"ssn"` kind), "482913 is your verification code", "Your code is 482913". Dates, phone numbers, "password reset" and "Zip code: 12345" are left alone.
- `jarvis_screen.py`:
  - The desktop Watch heartbeat: `{"do":"heartbeat"}` (this PC only); a Watch started with `from:"desktop"` ends after 45 s of silence by the monotonic clock, as `ended:"no_heartbeat"`, "the Jarvis window stopped answering". Watches started any other way never time out this way.
  - `ask()` no longer stores a look if Stop or a pause arrived while it was being taken.
  - An unchecked phone picture now says "could not check", not "no words".
- `jarvis_screen_win.py`: a visible window with an unknown exe is painted black when the Never-look list is non-empty or unreadable (old test updated).
- `jarvis_backup.py`:
  - Retention never deletes the file just written, ranks a future-dated name by real file time, and treats a same-second `-2` file as newer.
  - A truncated file is not counted among the kept, and reads as "damaged", not "wrong code".
  - Restore now stages temp files first, swaps each file, rolls back on any failure, and removes stale `-wal`/`-shm`. There is no writer-pause hook in the module, so it still needs a restart afterwards.
  - Failure messages are now true ("failed", "failed_partial", "safety backup could not be made"). A chat-key write failure is a plain `warning`, not silence. `.tmp` is cleaned on a full disk.
  - Restore card reworded ("replaces … with that day's copies").
  - New `POST /api/backup/delete-older`: this PC only, one `change_own_config` card, makes a fresh backup first, then deletes the others; the fresh backup's recovery code is shown once. It is not tied to an Erase; the apps just offer the button afterwards.
- `jarvis_schedule.py`: `age_s` on a fired job's view (not on the event; the event tests pin its exact keys). Running timers shift back with a clock set backwards; alarms and reminders stay.
- `jarvis_quick.py`: "12 at night / in the evening / tonight at 12" is midnight. A bare 12 or "every day at 12" is read as before, and the reply now says "That is 12:00 midnight/noon. If you meant the other, say …".
- `jarvis_forget_range.py`: "29 february to 15 january" asks again instead of raising. The Undo window also has a monotonic deadline.
- `jarvis_past.py`: "last week" uses calendar-date arithmetic. New `test_past_time_zones.py` covers Asia/Jerusalem and other DST changes.
- `jarvis_inbox_tidy.py`: monotonic guard on the Undo window.
- `jarvis_speech.py`, `jarvis_voice_enroll.py`, `jarvis_voices.py`: waiting-card time left uses the monotonic clock.
- `jarvis_child_env.py`: sets `HF_HUB_DISABLE_TELEMETRY=1`, `DO_NOT_TRACK=1` and `ANONYMIZED_TELEMETRY=False` on import and in every child environment. `jarvis_voices.worker_env` and both start lines in `docs/INSTALL.md` set them too. New `test_telemetry_off.py`.
- Tests pinned to a fixed zone and time: `test_briefing.py`, `test_forget_range.py`.
- `jarvis-desktop/src-tauri/deny.toml`: added `[sources]` deny sections, and `ci.yml` now runs `cargo deny check licenses advisories sources`. `ci.yml` pip installs are pinned to the versions in `requirements.lock` (numpy 2.5.3, sherpa-onnx 1.13.8, onnxruntime 1.30.0, cryptography 50.0.1).
- Docs updated: `JARVIS-API.md` §21, §45, §62, `ARCHITECTURE.md`.

**Could not verify**
- The `deny.toml` syntax is from memory and cargo-deny is not installed; the first CI run is the check.
- The `npm install playwright` line is left unpinned: no version appears anywhere in the repo.
- Telemetry env is set at import of `jarvis_child_env` and in the INSTALL start line, but the desktop app's own Rust backend launcher is not covered.
- Nothing ran on a real Windows PC.

**Touched outside my area, needs your attention**
- I re-ran `tools/gen_screen_cases.py`, which changed `jarvis-desktop/tests/fixtures/screen-cases.json` and `jarvis-client/.../screen-cases.json` (one new end-words entry). Re-run the generator after merging if those files conflict.

**For the app wiring**
- Desktop:
  - `POST /api/screen` `{"do":"start","from":"desktop"}`, then `{"do":"heartbeat"}` every 10–15 s. When `watching` comes back false, drop the sign.
  - `POST /api/backup/delete-older`; read `last_delete_older` and `pending_delete_older_card` from `GET /api/backup`.
  - When wiring it, add a `check_parity.py` row for the route; it fails if the entry exists before the desktop calls it.
- Clients can use `age_s` from the job view instead of comparing clocks.

**Owner decisions found**
- "Read it as midnight and always say the time back."
- Backup: "after an Erase the apps offer a button 'Delete older backups now'".

**Paste-ready note for CLAUDE.md**
Built 2026-09-30, the owner-approved audit fixes. Screen safety: the secret scan is capped at 25,000 characters and 6 s and fails closed, with new patterns (`DB_PASSWORD=`, `Passwort:`, Bearer headers, SSN, code-before-label, "password hunter2"). A Watch started from the desktop ends after 45 s without a heartbeat. A look racing Stop is discarded. A window whose program is unknown is painted black. An unchecked phone picture says so. Backups: retention never deletes the file just written and ranks future-dated names by file time. Restore is all-or-nothing with rollback, stale `-wal`/`-shm` are removed, failure messages are true, and a chat-key failure warns. "Delete older backups now" (`POST /api/backup/delete-older`, one card, fresh backup first) is built on the backend. Time: `age_s` on fired jobs, timers survive a clock set back, "12 at night" is midnight and a bare 12 is said back, Undo and waiting-card windows have monotonic guards, and the DST "last week" and leap-day range bugs are fixed. Supply chain: telemetry switches are set for Jarvis and every child it starts, `cargo deny` checks sources (syntax unverified), and CI pip installs are pinned.
