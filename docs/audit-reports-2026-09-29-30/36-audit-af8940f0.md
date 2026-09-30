# Report 36 (audit), agent af8940f0, 2026-09-30T06:58Z

> **What it was asked** (first 600 characters of the task): Read-only audit of the DESKTOP program notifications in /home/user/Epic-Jarvis/jarvis-desktop (Tauri 2; Rust in src-tauri/src, windows in src/) and the backend side that decides what to notify (backend/jarvis_*notify*, jarvis_watch_notify.py, jarvis_urgent*, jarvis_schedule.py, jarvis_initiative*, jarvis_briefing*, approvals/jarvis_gate, focus, Live, alarms/reminders/timers, jarvis_events). Read CLAUDE.md first (rules; plain-words rule for a beginner owner; decisions: approval widget shows only a short title under App lock and its Approve opens the locked app; a late alarm rings only if at mos

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

DESKTOP NOTIFICATIONS AUDIT (read-only, nothing changed). Not checked: anything on real Windows (toast registration, Focus Assist, sound); `cargo test` and the browser tests were not run. Paths below are under /home/user/Epic-Jarvis/jarvis-desktop/src-tauri/src unless stated.

TABLE (notification | trigger | wording | urgency and sound | App lock | switch | issues)
1. Approval toast | new id in the pending queue (stream.rs:1146-1170; the first read is skipped as "seeded") | the PC's own notice title and body (`toast_words` stream.rs:1189) | heavy card: default sound, once. "normal" card: `<audio silent="true"/>` (winrt_toast.rs:186). One Deny button, never Approve (:200) | title only (stream.rs:1200 "if app_lock { return (title, String::new()) }") | none | see F2, F3, F5
2. Alarm going off | `schedule` event, state fired (stream.rs:731 -> schedule.rs:568) | title "Alarm"; body is the job text, or "Jarvis: alarm." | `scenario="alarm"`, looping sound, Snooze plus Windows Dismiss (winrt_toast.rs:239-262). Keeps ringing until dismissed | `private = app_lock || private_hidden` gives the fixed lock-screen words only (schedule.rs:601) | only the backend's `notify:false` (schedule.rs:381) | F1, F4
3. Timer or reminder or to-do | same event | "Timer done" or "Reminder" or "To-do"; the timer body is "The {text} timer is done." | one normal sound, plus a Snooze button (winrt_toast.rs:485). It is auto-removed if the job changes on another device (`remove_fired` :526) | as row 2 | same | F1
4. Late alarm or reminder (more than 10 minutes late) | same event, `heard_late` (schedule.rs:584-590) | "Missed at {time}. {text}" | silent, no buttons (`quiet_xml`) | as row 2 | none | matches the owner's decision. F1
5. Morning briefing ready | `schedule` state ready (briefing.rs:339) | fixed words only, "Jarvis: your morning briefing is ready." | plugin toast, one sound | fixed words | none on the desktop | ignores `notify` (does not call `wants_toast`)
6. "Tell me when" matched | state matched (schedule.rs:630) | the job's `alert` sentence | urgent: rings until dismissed, no Snooze (`rings()` :429). Not urgent: normal | generic words when private | none | see the cross-device section
7. "Tell me when" cannot look | state broken (schedule.rs:663) | the job's `broken` sentence | never rings, by design | generic words when private | none | ok
8. System toasts through `commands::notify` (commands.rs:1303, plugin, one sound each) | Stop everything (commands.rs:2581); Live errors (live.rs:442, 590); Look and Watch (look.rs:432-567); talk-to-type (talk_type.rs:166); tray actions (tray.rs:1341-1555); update available (update.rs:328); hotkeys in use (lib.rs:1410); look spec drift (spec_drift.rs:236); backend down (sidecar.rs:931, quiet); "Jarvis is locked" (lock.rs:541); Snooze or Deny result | English sentences, some carrying raw error text | one default sound | not looked at; none of these check `app_lock` | none | F6
9. Tray icon and tooltip | link changes (tray.rs:1180) | "Live is on", "watching your screen", the approvals count, hours | passive, no sound | approvals and attention counts still appear in the tooltip while locked (tray.rs:1194-1201) | none | F7
10. Badges: Live badge and Watch badge (live-badge.js, watch-badge.js) | while a session is on | fixed words, never screen content | persistent windows | no words from private content | tied to the session | ok
11. Sounds: "I heard you" (main.js:4364), "One moment" (settings.js:2950), timer spoken aloud (coming-up.js:203) | each has its own trigger | short tone, spoken line | not looping | the timer line is generic | "I heard you" is off by default and read at use time: `loadHeard` reads localStorage on each call (voice-flow.js:272). Verified. "One moment" has a Settings toggle | none

FINDINGS, by severity
1. No Settings section for notifications. `grep notif|toast settings.html` finds only the approval note (settings.html:319) and the briefing note (:1000). No per-kind switches, no quiet hours, no sound choice, no test button, and the styles (urgent, approval, reminder, briefing, reply, status) cannot be chosen. The only off-switch is the backend's per-job `notify:false` (schedule.py:1599), so "a disabled kind is not shown" only holds for that flag. It is read at use time (`wants_toast` schedule.rs:381), but only in `toast_fired`. Not called by the briefing, matched or broken toasts (medium; sure).
2. An approval toast is never withdrawn after the card is decided on the phone, the bar or the widget, or after it times out. It carries no tag, and `RemoveGroupedTag` is used only for schedule jobs (winrt_toast.rs:530). A stale Deny then comes back as "Not denied ...". The desktop and the phone both post for the same card, with no "seen on the other device" cancel (medium; sure for the desktop, the phone side not checked in depth).
3. There is no Focus Assist or Do Not Disturb handling. `grep` finds nothing in the Rust, so I could not check whether an alarm-scenario toast gets through (not checked on Windows). Whether an urgent alert overrides Focus Assist is undecided.
4. Late-alarm guard has a hole. If `read_job` fails (a timeout, a stale link), `fired_at` is 0, `heard_late(0, ..)` is false (schedule.rs:590), and an old alarm rings loudly with generic words. The replay guard `TOASTED` is in memory only, so after an app restart a replay within 10 minutes can toast twice (low to medium).
5. "Hide memory lists" alone does not shorten the approval toast. Only `app_lock` is read (stream.rs:1146), while the schedule toasts also check `private_hidden`. Not a leak, since the notice is built from the action table and never reads the card's detail, but the two are inconsistent (low).
6. Toasts from `commands::notify` are not App-lock aware and can carry raw `err` text (backend or HUD error strings, "Clipboard unavailable: {err}"). Whether a path or address could appear was not checked (low to medium).
7. The tray tooltip shows the approvals count and the "waiting" count while App lock is on. Counts only, not words (low).
8. Dev and uninstalled builds fall back to the plain plugin toast (`is_uninstalled_build`). The alarm then rings once, with no Deny or Snooze button (winrt_toast.rs:273). This is honestly documented in the file. On installed builds the AUMID `com.jarvis.desktop` must match the NSIS shortcut, which is unverified on Windows (the file itself says so).
9. A captcha or sign-in hand-off has no desktop toast. The window and the Brain status show it (ARCHITECTURE section 8, row at :2027), so if the Brain is closed nothing tells the owner. The design chose this, but it is a real gap for a paused job (low).
10. The timer spoken aloud (coming-up.js:203) does not check lateness, so a replayed "fired" event can speak after 10 minutes (low).

CROSS-DEVICE
- `tools/check_parity.py` says "No undecided drift", but it checks routes, not notification behaviour.
- Declared one-sided: the smartwatch and phone-notification routes (phone-only, ARCHITECTURE section 8), the chatbot ongoing notification (:2027), the Live tile and Resume notification (:2049), and the desktop-only screen badge. The phone's channels (JarvisApp.kt:35-104) let Android's own settings choose sound and priority per channel. The desktop has nothing equivalent, and Windows' own per-app notification page is the only place to adjust it.
- The same wording is shared by fixtures (`toast_title`, `lock_screen_words`) and `tests/fixtures/card-words-cases.json`, which is good.
- Cancel on change exists for schedule jobs on both (phone: ScheduleNotifier.cancel; desktop: remove_fired). Not there for approvals or "tell me when".
- The claims "urgent rings until seen" and "PC plays an alarm sound until dismissed" (jarvis_tellme.py:985) hold only on an installed Windows build.

OPEN OWNER DECISIONS
1. Notification settings on the desktop?
 a) A small Settings section (recommended): per-kind on/off, a Test button, and quiet hours that never silence urgent alerts or approvals.
 b) Only a Test button and a link to Windows' own notification settings.
 c) Leave as is.
2. Old approval toasts?
 a) Remove them when decided anywhere, and remove a phone card's toast from the desktop the same way (recommended).
 b) Leave them.
3. Urgent alerts and Focus Assist?
 a) Let alarm and urgent toasts break through, and show a one-line note in Settings saying so (recommended).
 b) Respect Focus Assist for everything.
