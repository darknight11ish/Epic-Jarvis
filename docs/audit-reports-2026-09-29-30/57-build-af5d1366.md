# Report 57 (build), agent af5d1366, 2026-09-30T07:31Z

> **What it was asked** (first 600 characters of the task): You are in a git worktree of Epic-Jarvis. Read CLAUDE.md fully first (rules; plain words for a beginner owner; both-apps rule; 'Checking the Rust' section: install stable toolchain and use the x86_64-pc-windows-msvc target for fmt/check/clippy -D warnings; cargo test cannot run here). Do NOT push or open a PR; commit on your worktree branch, report branch+sha. Other agents edit backend/*.py, jarvis-client/ (Kotlin) and scripts/: do NOT touch those. Scope: jarvis-desktop/ only (src-tauri Rust, src HTML/JS/CSS, tests/*.mjs). Implement these owner-approved audit findings (re-verify each against s

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Branch `worktree-agent-af5d1366edd6274ef`, commit `52aa958d` (not pushed). Scope was jarvis-desktop/ only.

**Results**
- `cargo fmt --check`: clean.
- `cargo check` and `cargo clippy -D warnings` on `x86_64-pc-windows-msvc --all-targets` (rustc 1.98.1): clean.
- `tools/check_parity.py`: no undecided drift.
- Node tests that need no browser: 27 pass, 0 fail. The other 95 `tests/*.mjs` need Playwright/Chromium and did not run.
- None of the new Rust unit tests ran (no `cargo test` here); they only compile. Nothing ran on Windows.

**Changes by item**
1. **App lock fail-open** (`lock/rules.rs`, `lock.rs`):
   - `parse_stored` now reads each field on its own; a wrong-typed "on" (`"true"`, `1`) stays on.
   - An unknown `approvals` value becomes Every (stricter). I deliberately changed the old test's expectation for that.
   - `current()` keeps the last known state if the settings store can't be opened, and writes one crash note per outage.
   - The read decision is a pure function, `resolve_read`.
   - Tests added in both files.
2. **backend.log cap** (`logfile.rs`, `sidecar.rs`): `trim_backend_log()` runs on each watchdog tick (15 s). It copies the file to `.1` and truncates the original in place. A rename would leave the child writing to the renamed file. Log lines written between the copy and the truncate are lost. The 4 MB decision is a pure `over_cap`, tested.
3. **CSP**: `'unsafe-inline'` is kept. 12 inline `<script>` blocks remain: the theme guard on 8 pages, onboarding's second block, the 388 KB block in faces.html, and 2 large blocks in jarvis_hud.html. Playwright tests, `tools/shader_size.py` and `scripts/build-resolve-vectors.mjs` read faces.html's inline script, and none of that could be run here. Tauri already hashes inline scripts at build time, so the packaged pages already ignore `'unsafe-inline'` (see the `tests/hud.mjs` header). New `tests/csp-inline.mjs` pins the inline-script count per page and fails on inline handlers or `javascript:` URLs. It also fails if `'unsafe-inline'` is dropped while any inline script remains.
4. **innerHTML guard**: new `tests/html-sinks.mjs` scans `src/*.js`. It allows constants and `renderMarkdown(...)`, plus two allowlisted `main.js` sites (thread and diff), each keyed by file and target with its allowed interpolations. Any new sink fails.
5. **Focus rings**: the four listed rules now use `outline: 2px solid var(--focus-ring)` plus `outline-offset`, with `@media (forced-colors: active)` blocks in `widget.css` and `style.css`. `--focus-ring` passes 3:1 on every theme surface (lowest 7.2:1), so it is unchanged. New `tests/focus-outline.mjs`.
6. **Watch heartbeat** (`look.rs`): `start_heartbeat` runs while a session is on and posts `{"do":"heartbeat"}` to `POST /api/screen` every 12 s. Errors are ignored, so an older backend is harmless. If the response has an `"on"` key it is fed to `on_status`, so an ended session updates the sign. Pure `beat_action` and timing tests added. The docs contain no heartbeat contract, so the backend must accept the `heartbeat` verb and end the session after about 45 s of silence.
7. **Approval toasts** (`stream.rs`, `winrt_toast.rs`):
   - Toasts are now tagged (Tag = card id, Group = `jarvis-approval`).
   - `stream.rs` withdraws the toast of any card that leaves the pending queue, using pure `ids_that_left`.
   - A Deny on a card the server answers 409 for (decided, expired or gone) now shows a quiet "Already decided." instead of an error toast; it is skipped under privacy.
8. **Toasts under App lock** (`commands.rs` helpers `notify_failed`, `notify_guarded`, `toast_privacy_on`, `failure_body`):
   - Raw `err` text is removed from the tray, lib, clipboard, HUD and backend-start toasts and goes scrubbed to the log instead; a failed backend start also records a crash note (kind `start`).
   - Look/Watch, Live, talk-to-type and Stop everything toasts go generic when locked.
   - The approval toast now also uses `private_hidden`.
   - Not done: tray tooltip counts are kept because I wasn't sure of the design.
9. **Captcha hand-off toast**: not built. The hand-off only shows up when the page polls `GET /api/chatbot/status`, and no SSE event for it reaches `stream.rs`. Tell me the event name if the backend adds one.

**Owner decisions found:** focus ring "solid bright outline, no fade" (from your brief).

**Paste-ready note for CLAUDE.md**
Built 2026-09-30 (desktop audit fixes, commit 52aa958d): App lock now reads its settings field by field, so one bad value can no longer switch a lock off, and it keeps its last known state if the settings file can't be read. backend.log is capped at 4 MB while Jarvis runs. Approval toasts are withdrawn when their card leaves the queue, and a Deny on a decided card is a quiet "Already decided." Failure toasts carry plain words instead of raw errors and go generic under App lock or hidden private lists. The approval focus ring is a solid outline with a forced-colors fallback. Watch with me sends a `heartbeat` every 12 s. CSP `'unsafe-inline'` is kept, and three new node tests (`csp-inline`, `html-sinks`, `focus-outline`) hold the line. Nothing ran on Windows. The captcha hand-off toast is not built (no SSE event reaches the desktop).
