# Audit #1 - bug audit, desktop half (jarvis-desktop/)

Tree: `scratchpad/integ` at deaca649, new work = `git diff 9cdb0567..HEAD -- jarvis-desktop` (252 files).
Nothing in the tree was edited; tests ran in a copy (`scratchpad/b01-tree`), cargo used its own target dir (`scratchpad/target-b01`). `git status` of integ was clean afterwards.

## What was run

| check | result |
|---|---|
| `cargo fmt --check` | clean |
| `cargo clippy --locked --target x86_64-pc-windows-msvc --all-targets -- -D warnings` | clean (exit 0; only the expected "GNU compiler is not supported" warning) |
| every `node tests/*.mjs` (105 files, uikit.mjs is a helper) | see "Test results" at the end |
| Tauri command wiring (script `scratchpad/b01-caps.py`) | every command JS invokes is registered in `lib.rs` `generate_handler!` AND listed in `build.rs`; no page invokes a command its window's capability lacks (the only "misses" the script printed are library functions in `jarvis-link.js`/`face-voice.js` that those pages never call) |
| `innerHTML` / `insertAdjacentHTML` / `eval` / `fetch` in new JS | none new, apart from `dom.answer.innerHTML = renderMarkdown(...)` (escapes first, `markdown.js:36`); the new `_italic_` rule runs on already-escaped text |
| postMessage into faces.html | checks `event.source === window.parent && event.origin === location.origin` (`faces.html:6603`) |
| WebGL context loss | handled (`faces.html:557-564`: preventDefault, drop programs, re-init later) |
| New unwrap/expect/index on network data in Rust | none that can panic (`chatbot.rs:224 ids[0]` is after `ids.len() < 2` returns; `sky.rs:84 expect("one entry")` is after `o.len() == 1`) |
| Rule 4 (stale link) on every new write command | checked each: widgets add/delete, board actions (except Stop everything / Brief me), projects (except Shareable OFF), goals, photo reminder, history import (before AND after the file dialog), forget-range forget, sky "adds", third card assign, chatbot start/limits/resume/compare, Live start/extend/resume, talk-to-type (before listening and again before typing). All held in Rust, not only in the page. |
| Unsafe FFI (`live.rs` lock/registry, `talk_type/paste_windows.rs`, `autostart.rs`) | read line by line; buffer sizes, handle closing and the Arc handed to window user-data are right. Two small leaks noted below (low). |

## Findings

### 1. Talk-to-type and Jarvis Live: the microphone check is one-sided - medium
**checked in code** - branches: talk-to-type from `audit-competitors-vyqpt1` (59f82aea), Live from `ai-assistant-research-ff37vy` (3c7744bc); the clash only exists in the merged tree.

What's wrong: the talk button refuses while Live is on (even while Live's microphone is closed for a pause), but talk-to-type does not ask about Live at all - it only asks whether a listener is open right now.

Evidence:
- `voice.rs:849-854` (talk button): `// Jarvis Live has the microphone - even while it is closed for a pause ... if LIVE_MODE.load(Ordering::SeqCst) { return Err(crate::live::BUSY_MIC.to_string()); }`
- `talk_type.rs:300-306` (talk-to-type): `if app.state::<crate::voice::AutoListenState>().busy() { return Err(MIC_WAKE); }` - no `LIVE_MODE` check. Live's listener lives in that same `AutoListenState` (`voice.rs:1343 open_live_listener -> open_listener`), and a paused Live has taken it out (`voice.rs:1366 suspend_for_live -> take_listener`).
- `live.rs:571-581` `apply_hold`: when a pause ends, `voice::resume_for_live(app)` fails if talk-to-type holds the microphone (`voice.rs:1877 open_listener ... TALK_TYPE_HAS_MIC`), and then `listener_stopped(app)` - which calls `stop(&app, "owner")` and ENDS Live.

Two visible effects:
1. While Live is listening, pressing the talk-to-type key says `talk_type/rules.rs:66`: *"Jarvis is listening for "hey Jarvis", and both cannot use the microphone at once. Turn listening off in the Jarvis bar, then try again."* - wrong: it is Live, and the "hey Jarvis" button is not how Live is ended.
2. While Live is paused (Mic off, a card on screen, a stale link, a tap-only answer playing), talk-to-type is allowed. If the pause ends while the owner is still holding the key (for example they press "Mic on", or the card is decided), Live silently ends as if the owner had ended it.

Fix (code change, small): in `talk_type.rs` `mic_free`, refuse while Live is on, with its own words:
```rust
if crate::voice::LIVE_MODE.load(std::sync::atomic::Ordering::SeqCst) {
    return Err(MIC_LIVE); // "Jarvis Live is using the microphone. End Live first, or just talk to Jarvis."
}
```
(Owner's call only if they would rather talk-to-type work during a muted Live; then `apply_hold` must retry instead of ending Live when talk-to-type has the microphone.)

### 2. Settings recording during Live: right outcome, wrong words - low
**checked in code** (research branch). `voice_training.rs:237-242` calls `stop_listening_because(... "This PC stopped listening for \"hey Jarvis\" while you record in Settings. Turn it back on here when you are done.")`. With Live on, `voice.rs:2324-2326` ends Live (`live::listener_stopped`) and the owner is told "hey Jarvis" stopped. Fix: when `LIVE_MODE` is set, say "Jarvis Live ended because Settings is recording." (code change).

### 3. Widget tile buttons work while App lock is on - low, owner's call
**checked in code** (competitors branch, 2a7490f3). `widget.js:600-609` `pressBoard` checks only the link (`boardCanPress` = stale check), not `state.appLock`; `brain/widgets.rs` `widget_board_action` checks only `require_link_live`. So at a locked PC anyone can start a Focus session (which then watches which app is in front), a 10-minute timer, or play/pause music from the widget. The owner already decided that App lock covers task notes in the widget (`widget.js:1482 ... || state.appLock) return;`). Nothing private is shown (names are redacted, `widgets.rs` `widget_board` with `hidden`). Proposed: disable the three non-Stop tiles while `state.appLock` (and refuse in Rust with `crate::lock::locked_now`). Owner's call.

### 4. "Try the cloud model" is not held on a stale link - low, owner's call
**checked in code** (continuation branch, 061e39cc - no PR yet). `main.js:3018-3024` `tryCloudModel` resends the question with `cloudYes: true` with no link check, and `commands.rs` only inserts `cloud_yes` into the body. The backend re-runs its privacy gates, so rule 1 is not at risk; but it is the owner's "yes" to send words off the PC, and every other yes in the app is held while the stream is stale (rule 4). Proposed: hide/disable the button while `linkWords(currentLink()).canAct` is false. Owner's call whether a chat resend counts as "acting".

### 5. The Live badge holds `live_hold`, which it never uses - low
**checked in code** (research branch). `capabilities/live-badge.json` grants the whole `live` set; `surfaces.toml:911-920` includes `allow-live-hold`; `live-badge.js` never invokes it (it uses live_status/start/stop/act/mute). `live_hold` can open or close the microphone hold flags (`live.rs:476-500`). Harmless today, but against the file's own rule ("a command is reachable only from the surface that has a reason to call it"). Fix: split `live-hold` into its own set granted to the quickbar only (code change).

### 6. Error words from the Live badge vanish within a second - low
**checked in code**. `live-badge.js:49-56` writes a refusal (e.g. "The connection to Jarvis is catching up...") into `el.detail`, but while Live is on the watcher sends `live-status` every second (`live.rs:541 WATCH_EVERY`, `tell(...)` at the end of each look) and `render()` overwrites `el.detail`. The owner sees the reason flash and disappear. Fix: keep the error for ~6 s like the "heard" flash (code change).

### 7. Talk-to-type does not stop an animal's "Try it" - low
**checked in code**. The talk button sends `voice-capture-started` so Settings' "Try it" stops before the microphone opens (`voice.rs:861-863`; `voice-panel.js` `followJarvisVoice`). Talk-to-type opens the microphone without sending it (`talk_type.rs` `start`), so the animal voice can be recorded into a dictation (the voice check will most likely refuse it as "That did not sound like you"). Fix: `crate::emit_all(&app, crate::events::VOICE_CAPTURE_STARTED, ())` before `open_microphone` (code change).

### 8. Two small FFI leaks in the paste code - low
**checked in code** (competitors branch, `talk_type/paste_windows.rs`).
- `restore_snapshot` line ~437: `let _ = SetClipboardData(CF_BITMAP, Some(HANDLE(raw ...)))` - if it fails, the copied bitmap is never `DeleteObject`-ed; and if `restore_snapshot` returns early (clipboard busy, or the owner copied something), `saved_bitmap` is never freed either. A GDI handle per failed restore.
- If `open_clipboard` fails in `restore_snapshot` ("could not open the clipboard to put it back"), the delayed-render promise is still on the clipboard; when the hidden window is destroyed `WM_RENDERALLFORMATS` renders the dictated words for real (`paste_windows.rs` `paste_wnd_proc`), so they stay on the clipboard (still with the "no history / no cloud" markers). Rare; worth a log line saying the words were left on the clipboard. Code change.

### 9. Animal faces may keep drawing, or trip the GPU watchdog, in a hidden window - low
**needs a real try on device**. The display-mode loop (`faces.html:6580-6595`) re-arms `requestAnimationFrame` with no visibility check, and the stall timer (`faces.html` "THE STALL CHECK", `setInterval(..., 250)`) only skips when `document.visibilityState !== "visible"`. Tauri's `window.hide()` on Windows does not always flip `visibilityState` in WebView2 while it does stop frames; if so, hiding the widget/floating face mid-draw looks like a 3-second stall and turns the face flat. I could not test this without Windows; the face-watchdog tests pass in Chromium, where hiding does change visibility.

### Checked and fine (not findings)
- Live start/adopt refuse on a stale link and under App lock; the watcher closes the microphone on a stale link or a failed read, ends Live on App lock/Windows lock; `stop_automatic_listening` during Live no longer kills Live's microphone (`voice.rs:2298-2303`).
- Talk-to-type: generation counter makes Stop everything drop an in-flight dictation; modifier keys are waited for; the same window must be in front; password boxes refused (Win32 + UI Automation with a 1.5 s limit); clipboard restored only if the sequence number is unchanged. Loopback-only server.
- Registry reads (`live.rs` `reg`, `autostart.rs`) have correct buffer lengths and close their keys; `RRF_RT_REG_QWORD` restricts the type; Task Manager's "switched off" byte is read correctly (odd = off).
- Every new Brain read that returns private words is redacted in Rust while "Hide memory lists and chat history" is on (history search, fact history, conversation facts, forget-range, goals, projects, chatbot, widgets, schedule).
- Timers added in new JS (chatbot poll, screen-work tick/poll, widget board read) are cleared when their condition ends.
- `window_memory.rs` never restores visibility (HUD stays behind App lock); tests enforce it.

## Test results
(filled in below)

All 105 test files were run (logs: `scratchpad/b01-logs/`). **102 passed the first time. After re-runs, the only real failure is the known one, `faces.mjs`.**

- `faces.mjs` - FAIL `nothing is fetched from the network: the page still references a remote URL`. This is the known failure (an https:// credit in a GLSL comment in faces.html). Not re-reported.
- `memory.mjs` - failed first with `ModuleNotFoundError: No module named '_cffi_backend'` / pyo3 panic. The test runs `python3` on the backend, and the system Python's `cryptography` is broken (the brief mentions this). It **passes** when re-run with the scratchpad venv's python first on PATH. So this is a problem with this container, not the code.
- `face-pace.mjs` - failed once while the machine was busy (load around 9): `an animal picked at Maximum is traced at 2x2 and averaged down: 600 !== 1200`. It **passed** when re-run alone (load around 4), and it also passed in the merge helper's run. So the test is **flaky under load**, not a real bug: my unverified guess is that the page steps its resolution down when the machine is slow, even though the test sets `autoAdjust: false`. Low: worth a look so CI does not fail at random.
