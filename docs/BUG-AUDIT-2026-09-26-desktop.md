# Desktop bug audit, 2026-09-26

Scope: the Tauri desktop app. That is the Rust in `jarvis-desktop/src-tauri/src`,
including every `#[cfg(windows)]` block, and the windows in `jarvis-desktop/src`.
I looked hardest at what changed since 2026-09-24. I skipped the server-address
check (`validate_base`) and the "what asks first" screens, because other work is
changing those right now.

## In short (for the owner)

1. **No serious hole found.** Nothing lets a window approve an email, approve
   while App lock is on, or approve from a notification. The Rust checks behind
   those rules hold. The Rust build checks are clean too (`cargo fmt --check`,
   and `cargo clippy` for Windows with `-D warnings`).
2. **Two small "Stop" problems.** After you press Alt+Shift+X, a focus-session
   line that was already being made can still be spoken a second later. And a
   Deny pressed on a Windows notification is silently dropped if the app's live
   link to the PC is reconnecting at that moment. Nothing tells you it failed.
3. **App lock has one gap on the widget.** While App lock is on, the widget still
   lets anyone at the PC type a note into a task Jarvis is running. The widget
   hides the same kind of note on an approval card, so the two disagree. Whether
   that note belongs behind the lock is your call.
4. **An alarm can ring twice.** If you restart only the desktop app, and the Jarvis
   backend stayed running, the app can replay the last few events. An alarm or an
   urgent "tell me when" that already rang can then ring again.
5. **Two leftover weak spots.** Neither needs a fix before anything else. The
   email-in-the-widget check "fails open" for a card the app has not read yet.
   And every window, including Faces and the first-run window, receives the whole
   approval queue, although their descriptions say they cannot.

## The table

| # | Severity | Where | One-line bug | Fix size |
|---|---|---|---|---|
| 1 | Low | `brain/focus.rs:201-240`, `main.js:3299-3314` | A focus callout already being made plays after "Stop everything" (reproduced in the page harness) | S |
| 2 | Low | `lib.rs:636-642`, `winrt_toast.rs:318-330`, `commands.rs:1933` | A notification Deny on a running app is dropped without a word when the link is stale; there is no wait and no message | S |
| 3 | Low (owner's call) | `widget.js:1129-1150`, `widget.html:169-184`, `commands.rs:2221`, `commands.rs:2284` | With App lock on, the widget's task note still steers a running task (reproduced); neither note command checks App lock in Rust | S |
| 4 | Low | `stream.rs:63`, `stream.rs:505`, `stream.rs:1213-1234`, `lib.rs:1201`, `brain/schedule.rs:417-459` | Restarting only the desktop app can replay events, so an alarm or an urgent "tell me when" rings again | S |
| 5 | Low | `commands.rs:2581-2590`, `commands.rs:1964` | The "emails are approved in the Jarvis bar only" check lets an unknown id through from the widget, where the Windows Hello check treats unknown as risky | XS |
| 6 | Low | `lib.rs:262`, `stream.rs:737`, `stream.rs:1069-1073`, `capabilities/faces.json`, `capabilities/onboarding.json` | Faces and onboarding can listen to the full approval queue and every event, which their capability descriptions say they cannot | S |

Severity is how much harm the bug can do. Confidence is how sure I am that the
bug is real, and it is given with each finding.

## Detailed findings

### 1. A focus callout already being made plays after "Stop everything"

**Severity:** low. **Confidence:** high about the order of events. The JavaScript
half was reproduced in the page harness. The Rust half was checked by reading it.

What happens, in order:

1. The PC says a focus line is ready. `stream.rs` starts `play_callout` on its
   own task (`stream.rs` `"focus" if ... "callout"`).
2. `play_callout` asks the PC for the sound: `GET /api/focus/callout?seq=`
   (`brain/focus.rs:212-218`). The PC takes the line and **then** makes the
   sound. `backend/jarvis_focus.py:1615` is `line = ENGINE.take_line(seq)`, and
   `:1620` is `wav = speak_wav(line)`, which synthesises with Kokoro or a custom
   voice. That takes a noticeable moment.
3. While that is happening, the owner presses Alt+Shift+X.
   `commands.rs:2171` sends `stop-everything`, and `main.js:3985` calls
   `stopSpeaking()`, which stops a callout **only if one is already playing**
   (`stopFocusCallout`, `main.js:3292-3297`). Nothing is playing yet. The PC's own
   stopper clears only a line that has not been taken yet
   (`jarvis_focus.py:1365`: `self._mail = None`).
4. The sound arrives. `focus.rs:236` sends `focus-callout` to the Jarvis bar, and
   `playFocusCallout` plays it. Its only guard is
   `if (jarvisTalking() || focusAudio) return;` (`main.js:3302`), and it knows
   nothing about a stop.

Reproduction I ran: a throwaway harness test (now deleted) loaded `index.html`,
sent `stop-everything`, then 100 ms later sent `focus-callout` with a WAV data
URI. Output:
`Audio elements created after stop-everything: ["data:audio/wav;base64,UklGRiQA"]`.
So the page plays it.

Why it matters: the hotkey's own hint says it "Stops Jarvis talking ... at once"
(`hotkeys.rs:100`). Here Jarvis says "Instagram can wait" just after being told to
stop.

Smallest fix: keep a "stopped at" time or a counter in Rust. Have `play_callout`
note it before the fetch and drop the sound if a stop happened since. Or have the
page ignore `focus-callout` for a few seconds after `stop-everything`.

### 2. A notification Deny can be silently dropped

**Severity:** low. This is the safe direction: nothing is approved, and the card
times out on its own. **Confidence:** high, checked by reading the code. I did not
run it, because it needs Windows.

- When Jarvis is already running, a Deny click arrives through the
  single-instance callback. It goes straight to
  `winrt_toast::decide_denied_detached(app, id)` (`lib.rs:640`), with no wait.
- That calls `answer_approval`, which refuses any decision while the link is
  stale (`commands.rs:1933`: `if app.state::<crate::stream::StreamState>().link().stale {`).
- The failure is only written to the log file (`winrt_toast.rs:325-328`,
  "notification Deny for {id} did not go through"). No notification says so.

Compare the other two paths:
- The cold-start path waits up to 45 s for the link (`decide_denied_at_startup`).
- A toast's Snooze reports a failure in a notification (`brain/schedule.rs:541`,
  "Not snoozed: ...").

When this happens: the link is stale while it reconnects, for example after the
PC wakes from sleep or after the backend restarts. That is exactly when a
leftover notification is likely to be clicked. The toast disappears on click,
and the owner reasonably thinks the card was denied. The card stays waiting in
the Jarvis bar until it runs out.

Smallest fix: use the same wait-for-the-link loop as the cold start for the
running-app path, and on a failure show a notification ("Not denied: ... it is
still waiting in the Jarvis bar").

### 3. App lock: the widget's task note still works (owner's call)

**Severity:** low. **Confidence:** high (reproduced).

- The rule written in the widget: a note that changes the plan "waits for the
  unlocked Jarvis bar too". The approval card's note row is hidden while locked
  (`widget.js:694-696`, `if (noteRow) noteRow.hidden = locked;`).
- But the **task** note row (`widget.html:169-184`, "Add something before it
  continues…") is not hidden. `sendTaskNote` (`widget.js:1129-1150`) sends it
  with no lock check, and `inject_task_note` (`commands.rs:2221`) has none either.
- In Rust, `amend_approval` (`commands.rs:2284`) also does not check App lock.
  Today only the page hides that row. ARCHITECTURE §8 says "a check that lives
  only in the webview is not a check".

Reproduction I ran: a throwaway harness test (now deleted) opened `widget.html`
with `appLock: true`, a running task and a waiting card. Output:
`{"appLock":true,"apprNoteHidden":true,"taskNoteVisible":true,"enabled":true,"sent":["also forward the report to my boss"]}`.
So someone at the PC can type an instruction into a running task while App lock
is on.

What limits the harm: anything that note leads to that needs a card still needs
a card, and a card cannot be approved from the widget while locked. The widget's
quick capture (a note straight to Logseq, Joplin or Obsidian) also works while
locked. That looks deliberate, but it is not written down in §8.

Smallest fix, if you want the lock to cover it: hide the task-note row while
App lock is on. Also refuse `inject_task_note` and `amend_approval` in Rust when
the caller is the widget and App lock is on, the same way `answer_approval`
refuses Approve (`commands.rs:1947-1954`).

### 4. Restarting only the desktop app can ring an alarm again

**Severity:** low. **Confidence:** medium. The code path is checked by reading it.
It needs the backend to keep running while the desktop app restarts: a backend
you started yourself, not one the app started (`sidecar.rs:677-680` stops only
an "owned" one).

How it happens:
- The resume point (the last event id seen) is saved at most once every 5 s
  (`stream.rs:63` `RESUME_SAVE_INTERVAL`; `stream.rs:505` `save_resume(app, false)`;
  `stream.rs:1223` `let due = last.is_none_or(...)`). It is forced only when the
  stream drops (`stream.rs:314`).
- On exit, the only thing that runs is `sidecar::stop_on_exit` (`lib.rs:1201`).
  The resume point is not saved.
- So an alarm's `schedule fired` event that arrived less than 5 s after the last
  save is often not on disk. Other events arriving close together (activity,
  attention) make that likely.
- On the next start, the app resumes from the older id, and the backend replays
  the events after it (`Last-Event-ID`, JARVIS-API §3).
- `toast_fired` reads the job, which the PC keeps readable for a day, and asks
  `first_time(&id, fired_at)` (`brain/schedule.rs:459`). That memory is a static
  in the process (`schedule.rs:417`), empty after a restart. So the toast shows
  again, and for an alarm it is the looping one. The same applies to
  `toast_matched` ("tell me when").

Approvals are not affected: the first queue read after a start makes no toasts
(`seeded`).

Smallest fix: save the resume point on `RunEvent::Exit`, forced. Also skip a
`fired` toast whose `fired_at` is more than a few minutes old unless the event
says `late`.

### 5. The email rule in the widget lets an unknown id through

**Severity:** low. It takes a script running inside the widget page. **Confidence:**
high, checked by reading the code.

`waiting_email` (`commands.rs:2581-2590`) is true only when the id is found in
this app's copy of the queue and its action is `send_email`. An id the app has
not read yet gives `false`, so an Approve from the widget goes on
(`commands.rs:1964`). The Windows Hello rule decides the opposite way on purpose:
`lock/rules.rs:207-208` says "An id this PC cannot find in its queue is treated
as risky: not knowing is not 'safe'".

When the gap exists: between the backend raising the email card and this app
re-reading `/api/pending`. That takes up to 10 s (`FETCH_TIMEOUT`).

The widget's own button never does this (`widget.js:856-860`), so this matters
only if the widget page were ever made to run someone else's script. Windows
Hello still asks, but its prompt then says only "Approve a Jarvis action".

Smallest fix: in `answer_approval`, refuse an Approve from the widget when the id
is not in the queue: "open the Jarvis bar to read it first".

### 6. Faces and onboarding can hear the whole approval queue

**Severity:** low: both windows load only this app's own bundled pages.
**Confidence:** high, checked against the Tauri 2.11.5 source.

- `emit_all` is `app.emit(...)` (`lib.rs:262-266`). In Tauri 2.11.5, `emit`
  "Emits an event to all targets" (`tauri-2.11.5/src/lib.rs:934`), and the
  `listen` command takes any event name with no scope
  (`src/event/plugin.rs:15-22`; `core:event:allow-listen` is "without any
  pre-configured scope").
- `approvals-changed` carries every row in full, including `detail` (an email's
  whole text) (`stream.rs:1069-1073`). `jarvis-event` carries every event frame
  (`stream.rs:737`).
- `capabilities/faces.json` holds `core:event:allow-listen` and says the window
  "cannot reach the event stream, the approval queue". `onboarding.json` says the
  same ("cannot read the event stream, the approval queue"). Both statements are
  untrue.

Smallest fix: send those two events only to the windows that show them (Tauri's
`emit_filter` or `emit_to` with the quickbar, widget, Brain, Settings and HUD
labels). Or correct the two descriptions.

## Possible, not verified

- **Toast buttons may not reach the app at all.** Deny and Snooze use
  `activationType="foreground"` on a program installed without a registered COM
  activator. On such a program, Windows may start it without passing the button's
  `arguments`. `winrt_toast.rs`'s own header already says this has "not been
  watched fire on a real Windows machine". I cannot check it here. Test on the PC:
  click Deny on a card's toast with Jarvis running, and again with it closed.
- **A failed read can hide a later toast.** When `read_job` fails,
  `toast_fired` and `toast_matched` fall back to `fired_at`/`alert_at` = 0
  (`brain/schedule.rs:453-459`, `487-493`). A second failed read for the same
  job then counts as "already shown", and that toast is skipped. This needs two
  failed reads of the same job, for example a repeating "tell me when" during a
  backend hiccup. I have not reproduced it.
- **Any program may take the front for a moment.** `let_backend_prompt_forward`
  calls `AllowSetForegroundWindow(ASFW_ANY)` (`lock.rs:475-484`). That lets
  **any** program come to the front until the owner next clicks or types, not
  only the backend's Windows Hello prompt. Passing the backend's process id,
  when the app started the backend, would be narrower. Probably harmless. I have
  not tried to misuse it.
- **The widget re-reads every second at zero.** When its focus countdown reaches
  zero, the widget re-reads `/api/focus` every second (`widget.js:291-297`, no
  wait between reads) until the PC says the session ended. The Brain waits 2 s
  between reads (`brain.js:3558`). This is harmless if the PC ends the session
  promptly, which its scheduler normally does.

## Areas read and found fine

- **The approval path** (`commands.rs` `answer_approval`). In order it checks:
  a refused option id, a stale link, the widget under App lock, an email from
  the widget, Windows Hello (`lock::check_approval`), the link again after the
  prompt, and the backend's own owner-check refusal passed on in its own words. A
  notification can only deny.
- **The owner-check capability.** `owner_check_in_version` accepts only the
  string `"backend"`. `base_is_loopback` accepts only localhost, 127.x and ::1.
  `approval_needs_local_check` still asks under "Every approval" for a card that
  is not risky, or that the app cannot find. An older or unreachable backend
  means the desktop asks, as before.
- **Toast XML** (`winrt_toast.rs`). Title, body, id and button label are all
  escaped (`& < > "`, inside double-quoted attributes). A malformed string only
  makes `LoadXml` fail, and the plain toast is shown instead. No Approve appears
  in any toast. The alarm toast's only buttons are Snooze (the id only) and
  Windows' own Dismiss.
- **The launch arguments.** `jarvis-deny:` can only deny. `jarvis-snooze:`
  accepts only an id of the form `s` plus ten hex digits (`valid_id`), and it is
  held on a stale link and reported. Neither kind of launch puts a window on
  screen (`launched_by_deny`).
- **Approval toasts.** One per new id. The first read after a start is silent
  (`seeded`). Under App lock a toast shows the title only. The words come only
  from `notice`, never `detail`.
- **Coming up, the briefing and "tell me when" while the private lists are
  hidden.** The words, the list names and `alert` are taken out in Rust
  (`redact_list`, `briefing::redact`). A tell-me-when's `note` holds only fixed
  sentences (`jarvis_tellme.py:785-796`).
- **Focus sessions** (`brain/focus.rs`). Only the five actions are accepted. Stop
  and Pause are not held on a stale link; Resume, Extend and Lock on are. The
  sound is fetched from loopback only and must start with `RIFF`. It goes to the
  Jarvis bar only.
- **Stop everything.** Nothing holds it back: not a stale link, App lock, or a
  waiting card. It stops speech in the quickbar and the HUD before asking the
  PC. Its notification shows only the PC's fixed sentences. It approves nothing.
- **The email card.** The Jarvis bar shows it in a `<pre>` with `textContent`,
  never as Markdown. The widget shows one line and sends Approve to the bar. An
  email cut off by the gate cannot be approved.
- **Plain errors.** `chat_failure` tags a failed chat with a length-capped
  detail, and the page cleans that detail before showing it (`scrubDetails`).
  The token never appears in a URL. Manner accepts only "warm" or "plain", and
  a change is held on a stale link.
- **Web search keys.** They go only into Credential Manager, are read back to
  check they saved, and are never returned to the page. The input box is
  emptied before the save call. An error never contains the key.
- **What Jarvis can reach, and the briefing settings.** They read the PC's
  answers defensively. Repeating set-ups and turning a setting on are held on a
  stale link. A briefing can be stopped only if the PC lists it as one.
- **"Open the card".** It passes the id only, and the Jarvis bar opens behind
  App lock. When the card has gone, the bar falls back to the first waiting card.
- **The widget's App lock handling.** It reads the lock state first and treats a
  failed read as "locked". The card shows the title only. Options, the rush
  quote and the note are hidden. Approve opens the bar. Deny still works.
- **Crashes and poisoned locks.** No `unwrap` or `expect` on remote data outside
  tests. Every `Mutex` recovers from poisoning (`unwrap_or_else(into_inner)`).
  The one-prompt-at-a-time lock (`LockState.prompt`) is never taken twice on the
  same path.
- **The unsafe code blocks** (`lock.rs` `hello`, `winrt_toast.rs`
  `SetCurrentProcessExplicitAppUserModelID`, `AllowSetForegroundWindow`). Each
  one has its safety conditions written next to it, and they hold. COM is started
  on a thread of its own and released afterwards.
- **Commands and permissions.** Every command registered in `lib.rs` is listed in
  `build.rs`. The new permission sets (`focus`, `focus-start`, `open-card`, and
  `get_app_lock` in `approvals`) go only to the windows that use them.
- **Checks run.**
  - `cargo fmt --check`: clean.
  - `CARGO_TARGET_DIR=... cargo clippy --target x86_64-pc-windows-msvc --all-targets -- -D warnings`:
    clean. The only warning was the expected, harmless "GNU compiler is not
    supported".
  - These node tests pass: `focus`, `coming-up`, `email-send`, `card-words`,
    `plain-errors`, `briefing`, `web-search`, `reach`, `hotkeys`, `security`,
    `uikit`, `decide`, `approvals-contract`, `chat-stream`.
  - `cargo test` needs Windows, so it was not run.
