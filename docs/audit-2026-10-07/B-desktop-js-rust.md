# Audit stream B — desktop JS + Rust

Target: clean `main` worktree `.dsh-scratch/audit-main` (detached HEAD `fa2b379f` = `origin/main`).
Scope audited: `jarvis-desktop/src/**` (158 JS/HTML files), `jarvis-desktop/tests/**` (151 suites),
`jarvis-desktop/src-tauri/**` (Rust + capabilities + permissions), `jarvis-desktop/README.md`.
All findings below were found by reading the cited line; every `path:line` is verified.

---

## Findings

### B1. The quickbar's "Erase the words" silently loses the "how many other facts stay" count — `brain_conversation_facts` is not granted to the quickbar

**Where:**
`jarvis-desktop/src-tauri/capabilities/quickbar.json:22` (grants `memory-used`, which does *not* contain the permission),
`jarvis-desktop/src-tauri/permissions/surfaces.toml:811` (the permission lives only in the `brain-memory` set, which is granted only by `capabilities/brain.json:25`),
`jarvis-desktop/src/answer-memory.js:328` (the call),
`jarvis-desktop/src/auto-learn.js:288` and `:292` (the invoke and the swallow).

**What happens:** In the Jarvis bar, "Used in this answer" → **"Erase the words"** runs `writeErase`
(`answer-memory.js:318`). Line 324 asks `brain_fact_chat` — that *is* granted (the `memory-used` set
carries `allow-brain-fact-chat`), so `chat` comes back as a real object. Line 328 then calls
`otherFactsInChat(invoke, chat, f.id)`, which invokes `brain_conversation_facts`. The quickbar's only
capability file grants `allow-brain-memory-forget`, `allow-brain-memory-erase` and `allow-brain-fact-chat`
but **not** `allow-brain-conversation-facts`, so Tauri refuses that IPC call. `otherFactsInChat` catches
it and returns `0` (`auto-learn.js:292-294`), so nothing is logged, nothing is shown, and the
"Also delete the chat it came from?" question always falls to the general sentence instead of naming
how many **other** facts that chat taught. That count is the whole point of
`auto-learn.js:280-285` ("the second chat audit, 2026-09-28, desktop B1"): it is the warning that
deleting the chat forgets none of those facts. The Brain's own copy of the same flow
(`brain.js:6193`) works, because the Brain holds the `brain-memory` set — so the bar and the Brain
disagree about the same question, and only the bar is wrong.

**Confidence:** Confirmed (verified by diffing every capability file and permission set against every
JS `invoke("…")` — this is the only ungraded-but-reachable command in the whole desktop).
**Severity:** Medium
**Obvious or subtle:** obvious
**Fix:** add `"allow-brain-conversation-facts"` to the `memory-used` set in
`src-tauri/permissions/surfaces.toml` (it is the read that only ever counts facts taught by a chat, and
`memory-used` already carries the erase and forget this question is attached to), and, in
`answer-memory.js:328`, move the `otherFactsInChat` call inside the existing `try` above it so a future
refusal degrades visibly rather than to the number `0`.

---

### B2. A card whose request was cut off can still be approved — the refusal is a disabled button in the two webviews and is never re-checked in Rust

**Where:**
`jarvis-desktop/src/main.js:2642-2644` and `jarvis-desktop/src/widget.js:1195` (the whole enforcement),
`jarvis-desktop/src-tauri/src/commands.rs:2392-2566` (`answer_approval`, the one place a decision is sent — no such check),
`jarvis-desktop/src-tauri/src/commands.rs:2447-2453` (the staleness check that *is* in Rust, for contrast),
`jarvis-desktop/src/jarvis-link.js:158-168` (the rule and the `cutOff` computation).

**What happens:** `jarvis_gate` stores `detail` as `json.dumps(detail)[:4000]`, so a long command arrives
truncated and the card shows **part** of what would run. `jarvis-link.js:162-168` marks that `cutOff`,
and both surfaces set `Approve.disabled = … || approval.cutOff` — and that is all that stops it. `answer_approval`
(the single decision path every window shares) checks the id, the option id, staleness, the widget's App
lock, the widget's email rule, Windows Hello and the notification rule — but never the cut-off. So any
caller that reaches `decide_approval` without going through those two pages' `syncApprovalButtons`
approves a command nobody has seen in full, which is exactly what ARCHITECTURE §3's "every command, in
FULL" forbids. The project already learned this lesson once, in the same function:
`commands.rs:2431-2443` explains that rule 4 used to live only in the webview and was moved into Rust
because "a disabled button is a courtesy, not a gate: any window holding the `approvals` capability
reaches this directly". The cut-off refusal was not moved with it. The same is true of the "heavy" card
gate (`main.js:2638` `heavyBlocked`, `widget.js:1069-1070`): the delay-and-scroll rule that makes the
owner read a heavy card exists only in the two pages.

**Confidence:** Confirmed for the code fact (no cut-off or `weight: "heavy"` check anywhere in
`src-tauri/src`, including `stream.rs`'s queue rows and `lock/rules.rs`); the owner-visible risk today is
limited to a script or a future surface, since both shipped pages do disable the button.
**Severity:** High (safety rule, same class as the gap the file already documents and fixed)
**Obvious or subtle:** obvious
**Fix:** in `answer_approval`, next to the staleness check at `commands.rs:2447`, look the id up in
`StreamState`'s last-read `pending` rows (`stream.rs:149`) and refuse when that row's `detail` is a
`String` of `>= 4000` characters that does not parse as JSON — the same test `jarvis-link.js:163-169`
applies; the heavy gate can be carried in the same place by refusing when the row's `notice.weight` is
`"heavy"` and the caller is not the quickbar.

---

### B3. `screen-captured` and `capture-failed` are declared and listened for, but nothing in the app ever emits them — the quickbar's picture attachment and its vision notice are unreachable, and four suites test that dead path

**Where:**
`jarvis-desktop/src-tauri/src/lib.rs:110` and `:112` (declared; the names appear nowhere else in Rust),
`jarvis-desktop/src/main.js:5236` and `:5268` (the listeners),
`jarvis-desktop/README.md:308-309` (documents both as emitted events),
`jarvis-desktop/tests/picture.mjs:30` (and `provenance.mjs:188`, `second-card.mjs:962`, `photo-reminder.mjs:105` — all drive it with `window.__emit`).

**What happens:** The only writer of `state.capture` is `attachCapture` (`main.js:1770`), whose only caller
is the `screen-captured` listener. Nothing in `src-tauri` emits that event or `capture-failed`: the
Alt+Shift+S hotkey now goes to `look::look_from_hotkey` (`lib.rs:1239`, `look.rs:488`), which posts to
`/api/screen` and emits only `screen-look` + `focus-input` (`look.rs:519-525`) — the PC keeps the picture
itself, so nothing comes back to the page. Consequences: (a) the bar's picture chip, the `hasImage`
routing and the "your local model cannot see this picture" gate (`main.js:3393-3404`, `showPictureNotice`)
can never appear in the shipped app, so the code and its README/`tests/picture.mjs:2-9` claim ("Alt+Shift+S
attaches a picture") describe something the desktop no longer does; (b) the four suites named above pass
while guarding code the app cannot reach, so a real regression in the live `screen-look` path is invisible
and a change to the dead path looks verified — the false-confidence case this audit was asked to look for.
`spec_drift.rs:22` shows the project's own convention for this situation: it states plainly that "No window
subscribes to it today; the log line is the real output". These two events never got that treatment.

**Confidence:** Confirmed (whole-tree search: the only references are the declarations, the listeners and
the tests).
**Severity:** Medium
**Obvious or subtle:** subtle (needs the owner's decision: delete the dead path, or wire the picture back)
**Fix:** decide one way and make it true — either delete the two constants, the two listeners, the picture
chip/notice chain and the four suites' `window.__emit("screen-captured", …)` calls, or restore an emit at
the end of `look_then_bar` when the PC returns a data URI; either way correct `README.md:308-309` to name
what is actually emitted.

---

### B4. `tests/shots.mjs` cannot fail, and its CI-run sibling `tests/sheet.mjs` asserts nothing

**Where:**
`jarvis-desktop/tests/shots.mjs:98` (a failed scene driver is pushed onto `problems`),
`jarvis-desktop/tests/shots.mjs:101` (every page console error is pushed onto `problems`),
`jarvis-desktop/tests/shots.mjs:109` (the list is printed and the process still exits 0),
`jarvis-desktop/tests/sheet.mjs:36` (prints a path; no check of any kind),
`.github/workflows/ci.yml:135` (`case "$name" in uikit.mjs|shots.mjs) continue ;; esac`).

**What happens:** A run where a page throws on load, or where a scene's driver fails, is reported only as a
`PROBLEMS:` block on stdout — the exit code stays 0, so `npm run shots` and any wrapper that checks only
the exit code read a broken page as a clean run. CI excludes `shots.mjs` (ci.yml:135) but does **not**
exclude `sheet.mjs`, so the suite job runs a file whose only behaviour is to read whatever PNGs happen to
be committed under `tests/shots/<theme>` and print a contact sheet path; a scene added to `shots.mjs`
without regenerating the committed shots would keep `sheet.mjs` green. This is the "suite that cannot
fail" class, at low blast radius because these two are harness tools rather than behavioural checks.

**Confidence:** Confirmed (read both files end to end; `shots.mjs` has no `process.exit` at all).
**Severity:** Low
**Obvious or subtle:** obvious
**Fix:** end `shots.mjs` with `if (problems.length) { console.error(…); process.exit(1); }`, and either add
`sheet.mjs` to the CI skip list beside `shots.mjs` or give it one assertion (that every scene id in
`SCENES` has a committed PNG for the theme it is composing).

---

## Areas checked and found clean

- **Tauri command wiring.** All 272 distinct `invoke("…")` names in `src/**` are in
  `lib.rs`'s `generate_handler!` list (343 entries), and the only seven `#[tauri::command]` bodies not
  registered (`capture_screen`, `toggle_widget`, `show_quickbar`, `toggle_hud`, `is_quickbar_pinned`,
  `read_clipboard`, `quit_app`) are deliberately unregistered and explained at `lib.rs:804-812` —
  not a defect (confirmed independently by `docs/FEATURE-REVIEW-2026-10-04.md:561`).
- **Per-window capability grants.** Every window's page graph was closed over its transitive ES imports
  and diffed against its capability file and `permissions/surfaces.toml`; after that pass **no** window
  invokes a command it is not granted, with the single exception of B1.
- **Approval flow.** `decide_approval` is the one path (`jarvis-link.js:722-732` is the only caller of
  it); the widget's wrong-card fix, the `decided` latch, the 409 handling, the option-id refusal, the
  Windows Hello ordering, the notification-cannot-approve rule and the double staleness check (before and
  after the Hello prompt, `commands.rs:2447` and `:2519`) all read correctly.
- **Event stream / staleness.** `stale` starts `true` (`stream.rs:128`), is cleared only via
  `hello_may_clear_stale` (`stream.rs:1406-1414`, with its own Rust tests) or after a successful queue
  read (`stream.rs:613-622`, `:649-653`), and is re-checked in `answer_approval` before the request is
  built. The webview and the Rust agree.
- **Pairing token.** Never written plain to disk in the current build: `commands.rs:295-333` migrates the
  old plain-text copy into Credential Manager before anything reads it, `save_file_then_token`
  (`commands.rs:1006-1016`) writes the settings file first and the token second, and the HUD is
  configured with an empty token on every load (`lib.rs:370-390`, `hud_proxy.rs`). The one
  `localStorage.setItem("jarvis.token", …)` in the tree (`src/jarvis_hud.html:764`) is reachable only from
  a browser console setting and the shell always passes `persist = false` plus `JARVIS.forget()`.
  No token appears in any JS `console.*` call.
- **Reachable panics in Rust.** Only ten `unwrap`/`expect` calls exist outside `#[cfg(test)]`; each was
  read and is guarded (`animal.rs:99`/`sky.rs:84` filter on `len() == 1`, `crash_notes.rs:407` is behind
  the `sep_ok` check, `hotkeys.rs:318` re-parses a string validated on line 314, `proctree.rs` is a
  `#[cfg(all(test, unix))]` module, `spec.rs:144`/`lib.rs:1549` are startup-only).
- **Mutexes across `.await`.** Every shared lock is a tight scope (`commands.rs:2905-2909`,
  `stream.rs:1131-1146`) or a `tokio::sync::Mutex` used with `.await` for its own gate
  (`lock.rs:201-204`, `sidecar.rs:163`). Nothing holds a `std::sync::Mutex` guard across an await.
- **Subprocesses.** Every `Command::new` has a timeout-and-kill path or a watchdog (`devices.rs:363-391`
  reads the pipe on its own thread and kills at the limit; `commands.rs:3086` logs a killed GPU probe).
- **Element ids / DOM.** Across all ten pages: no duplicate `id` attributes, and every
  `getElementById`/`querySelector("#…")` in a page's own scripts resolves to an id that page defines or
  that its scripts create.
- **Accessibility (spot check).** The buttons with empty static content (`faces.html:199-200`,
  `index.html:417/825/834`, `settings.html:102/1324-1325/1975-1976`) all get their text from JS at render
  time (e.g. `faces.html:7630`), so they are not unnamed controls.
- **Test teeth.** No suite asserts a tautology (`assert(true)`, `x === x`, `length >= 0`) and none
  swallows its own failure: the shared pattern is `catch (e) { fails.push(name); … }` ending in
  `process.exit(fails ? 1 : 0)`. The `SKIP` paths (Playwright or Python absent) are documented at
  `tests/README.md:59-86`, print as `SKIP`, and never as `ok`. Apart from B4, the toothless-suite class is
  clean.
- **Safety rules, statically.** No tunnel client, tunnel host or "share my Jarvis" anywhere in
  `src/**` or `src-tauri/**`; the only `ngrok`/`trycloudflare` strings are the refusal cases in
  `commands.rs:6503-6596` and the Settings wording at `settings.html:170`. No auto-approve or bulk-approve
  path exists — every write of a decision goes through `decide_approval`.

---

## Environment notes for whoever runs the suites (not product bugs)

1. **Playwright cannot launch in this session.** `node tests/<browser suite>.mjs` dies with
   `browserType.launch: spawn EPERM` (uikit.mjs:3335) because Chromium is started with
   `--remote-debugging-pipe`, which the DSH sandbox forbids. 118 of the 151 suites are browser suites, so
   they all fail here for this reason and none of them says anything about the code. The 33 pure-node
   suites run fine.
2. **Any suite that shells out through a pipe fails too.** `tests/lipsync.mjs` reports
   `FAIL … spawnSync python EPERM` and `tests/updater-manifest.mjs` `spawnSync … EPERM` on this machine
   and only this machine.
3. **The 33 pure-node suites were run: 31 pass, and the 2 failures are exactly the two in note 2.**
   `animal-motion`, `approval-target`, `approvals-contract`, `brain-settings-door`, `browser-engine`,
   `card-words`, `chat-history`, `csp-inline`, `css-vars`, `first-run-settings`, `flashgov`,
   `focus-outline`, `forecast`, `form-review`, `goal-locks`, `handoff`, `heavy-approve`, `html-sinks`,
   `inbox-tidy`, `look-rules`, `memory-words`, `menu-visibility`, `model-chat`, `notifications-settings`,
   `onboarding`, `quiz-cloud`, `speech-pieces`, `thinking`, `tutorials`, `voice-speed`, `voicecheck`
   all exit 0.

## Coverage

Read line by line (JS): `jarvis-link.js`, `main.js` (approval, stream, picture, used-facts, task-control
sections), `widget.js` (approval + lock sections), `answer-memory.js`, `auto-learn.js`,
`approval-target.js`, `heavy-approve.js` (via its suite), `jarvis_hud.html` (transport),
`look-settings.js`. Read line by line (Rust): `commands.rs` (`answer_approval` and the chat/compute
paths around it), `lib.rs` (events module, handler list, HUD configure), `stream.rs` (link state, hello
and doorbell handling), `look.rs` (delivery), `devices.rs` (pairing), `spec_drift.rs`, `hotkeys.rs`,
`animal.rs`, `crash_notes.rs`, `proctree.rs`. Read in full (tests/tooling): `shots.mjs`, `sheet.mjs`,
`themecheck.mjs`, `css-vars.mjs`, `picture.mjs`, `tests/README.md`, `ci.yml` (desktop job).
Mechanically scanned: 158 `src` files, 151 suites, 343 registered commands, 604 handler entries,
34 event constants, 62 permission sets and 10 capability files, plus every `invoke(`, `JSON.parse`,
`parseInt`, `listen(` and `process.exit` in the desktop half. Roughly 4,500 lines read line by line.
