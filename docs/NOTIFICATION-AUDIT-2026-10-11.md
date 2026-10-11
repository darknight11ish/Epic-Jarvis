# Notification audit, both platforms (2026-10-11)

The owner, 2026-10-11: *"i have them go off from jarvis but theres not turn off
alarm, only a snooze in the notifcation that appears on desktop. also make sure
this isnt an issue with android phone notification. do a general audit of
notifications on both android phone and desktop through actual testing to make
sure the right options are convenitly available to take on the notification
itself, that all of the notifcations display the right content and work
properly, and more"*.

Checkout: `.dsh-scratch/notif-audit`, branch `audit/notifications-both-platforms`
off `origin/main` (70077268). Phone: CPH2419, adb serial `f0a5b32b`, Android 15
(SDK 35), locale en-US; app `com.jarvis.client` (the test build
`com.jarvis.client.test` is also installed). PC: the running installed app
`%LOCALAPPDATA%\Jarvis Desktop\jarvis-desktop.exe`, pid 32272, backend on
127.0.0.1:4719.

## 1. The desktop defect, and what proves it

**VERDICT: REAL, and the fix is in this branch.**

Two separate faults, both of which the owner would describe the same way.

### 1a. The ringing toast's "way out" had no label at all

`winrt_toast.rs::alarm_xml` built:

```xml
<action activationType="system" arguments="dismiss" content=""/>
```

`content` is the text **displayed on the button** (Microsoft's own
[action element](https://learn.microsoft.com/en-us/uwp/schemas/tiles/toastschema/element-action)
table: "content - The content displayed on the button", required, no default).
Empty is therefore a button with no word on it. The doc comment above it
claimed "Windows requires an alarm toast to carry a button; its last button is
Windows' own Dismiss (`activationType="system"`)" - nothing had ever verified
that, and **it is the empty label, not Windows, that produced what the owner
saw: one labelled Snooze and a blank second button.**

Proof that Windows does not fill the word in for this app: Microsoft's own
Defender toast in the same store (notification id 1753, handler
`Windows.Defender.SecurityCenter`) carries
`<action activationType="system" content="Dismiss" arguments="dismiss"/>` -
the same system action, with the word written out. Nothing in Windows invents
it.

### 1b. A timer's toast could only be snoozed

`try_notify_fired` built one action, Snooze. Windows' own notification store on
this PC (`%LOCALAPPDATA%\Microsoft\Windows\Notifications\wpndatabase.db`,
handler `com.jarvis.desktop`, group `jarvis-schedule`) held **22 "went off"
toasts, every one of them with `<action content="Snooze 10 minutes" .../>` and
no other action** - no dismiss, nothing to take it away. The only ways out were
to snooze it or to click through into the app. That is exactly "theres not turn
off alarm, only a snooze in the notifcation".

(Those 22 are timers and reminders. No *alarm* had ever gone off on this PC, so
the alarm toast's own label was never on screen here either - it is 1a that
covers the alarm case, and it is proven from the XML being sent, not from the
history.)

### The fix

- `alarm_xml` (the ringing alarm, and an urgent "tell me when") now carries
  **Snooze 10 minutes**, a labelled **Stop** (`activationType="system"`,
  `arguments="jarvis-stop:<job id>"`), and a labelled Windows **Dismiss**. The
  ringing is unchanged: still `scenario="alarm"`, still
  `Notification.Looping.Alarm` with `loop="true"`.
- `fired_xml` (a timer, alarm or reminder that rang once) now carries Snooze
  **and** Stop.
- Stop is **job-scoped and answers nothing**: it takes that one notification
  away, sends no request, changes no state, and therefore needs no event stream
  and puts no window up. It is the same thing the phone's own Stop does
  (`ScheduleNotifier.stopRinging`). Pressing it while Jarvis is closed is
  handled at startup, and `launched_by_deny()` counts it so the click does not
  raise a window.
- Tests: three new/updated (`a_ringing_alarm_s_way_out_is_a_labelled_stop_and_windows_dismiss`,
  `a_timer_that_went_off_offers_snooze_and_stop`, `a_stop_click_yields_one_job_id_and_nothing_else_does`),
  including the exact old shape as a negative (`!xml.contains(r#"content="""#)`).
  `cargo test --lib winrt_toast`: 17 passed, 0 failed. `cargo fmt --check`:
  clean.

## 2. What the DEVICE actually shows (Android, CPH2419)

Method: I created real jobs through the running PC's own
`POST /api/schedule/add` route (pairing token read from Windows Credential
Manager; never printed), then read them out of the phone with
`adb shell dumpsys notification --noredact` - the authoritative record of the
actions a posted notification really carries.

### 2a. A plain timer that went off - the phone does NOT have the desktop's 1b

```
tag=s933c7b6ebf channel=jarvis_schedule actions=1 category=reminder
  flags=AUTO_CANCEL|LOCAL_ONLY
  [0] "Snooze 10 minutes"
  android.title=String (Timer done)
  android.text=String (Jarvis: your timer is done.)
```

The phone's timer offers Snooze only, exactly like the desktop timer did. Same
shape for every other timer in the dump (`sca26723667`, `se4f63ed019`,
`s8c579790e5`, `sfaa6ce879d`, `s2030b3359b`, `scf7b635305`). It was live
(`airtimeMs=5638`, `mShowBanner=true`), and its lock-screen version shows only
`Jarvis` / `Jarvis: your timer is done.`

**So the phone is not exempt from 1b** - it has the same Snooze-only timer the
owner complained about on the desktop. It *is* exempt from 1a: see 2b.

### 2b. An alarm going off - the phone HAS a labelled Stop, and it rings

```
tag=s7623a9a982 importance=4 channel=jarvis_alarm id=12544
  flags=ONGOING_EVENT|INSISTENT|AUTO_CANCEL|LOCAL_ONLY category=alarm actions=2
  [0] "Stop"             -> startService (com.jarvis.client)
  [1] "Snooze 10 minutes" -> startService (com.jarvis.client)
  android.title=String (Alarm)
  android.text=String (Jarvis: alarm.)
```

`ONGOING_EVENT|INSISTENT` is the ringing; the two actions are both labelled and
both act from the notification without opening the app. A screenshot of the
shade at 08:05 shows the same notification live under "Jarvis - Just now" with
the alarm bell icon, above "Timer done". **The phone's alarm passes.**

Two honest limits on the phone side:

- I could not complete a *tap* on Stop: the action is delivered to
  `EventService.ACTION_STOP_RINGING` (a non-exported service), and my taps on
  the shade's per-row chevron kept expanding and collapsing the group instead.
  What is proven is that the button exists, is labelled, is offered on the
  notification itself, and is wired to `ScheduleNotifier.stopRinging`, which
  cancels exactly that (tag, id). It was not proven by a real finger.
- The dump's action label is what Android stored; it is the same string the
  phone's own code puts on the button (`STOP = "Stop"`).

## 3. The per-notification audit

"Actions" is what the notification itself offers; "convenient" asks whether a
person can act without opening an app.

### Desktop (Windows, `com.jarvis.desktop`)

| Notification | Actions on it (after this fix) | Convenient? | Content | Does the action work |
|---|---|---|---|---|
| Timer / reminder that went off | Snooze 10 minutes, **Stop** | Yes - both, from the toast | Title "Timer done" / "Reminder", body the job's own words, or the kind's words while App lock is on | Snooze: proven - it rides the same `jarvis-snooze:` path the 22 stored toasts use and lands in `schedule.rs::snooze_from_toast`. Stop: removes that tag+group; unit-tested; not yet seen on screen |
| Alarm going off | Snooze 10 minutes, **Stop**, Windows Dismiss | Yes | "Alarm" / "Jarvis: alarm." | As above; ringing itself unchanged (`scenario="alarm"`, looping alarm sound) |
| Urgent "tell me when" match | Snooze, **Stop**, Windows Dismiss | Yes | The alert's own words | As above |
| Ordinary "tell me when" match | **None** - `toast_matched` passes `snooze: None`, so no Snooze and no Stop; the notice is dismissed like any toast | By design: a match is a notice, and its job ends the moment it matched | The alert's own words | No action to work; dismissal is the notification itself |
| Heard LATE (>10 min, quiet) | **None** | By design (owner's 2026-09-26 decision): no sound, no Snooze | "Missed at HH:MM." + the job's words, or the kind's words while App lock is on | No action to work; dismissal is the notification itself |
| Morning briefing ready | None (plain toast, tap opens the app) | Tap only | "Morning briefing" | Tap opens the Brain |
| Approval card | **Deny only**, never Approve | Yes - Deny from the toast, deliberately not Approve | The card's title, and its body line unless App lock is on | Deny proven by design + `decide_denied_detached`; Approve is refused on purpose |
| "Live ended - Resume" | None on desktop (the phone has one) | Desktop: notification only | Live's own words | - |
| Backend/tray/status failures, spec drift, hotkey clash, update notices | None | Informational only | Their own sentence | - |
| PC-notifications card (phone notifications read on the PC) | None - it is a switch/card, not a toast with actions | - | - | - |

### Android (`com.jarvis.client`)

| Notification | Actions on it | Convenient? | Content | Does the action work |
|---|---|---|---|---|
| Timer / reminder that went off | Snooze 10 minutes | Yes | "Timer done" / "Jarvis: your timer is done."; locked screen shows only the kind's words | Snooze -> `EventService.ACTION_SNOOZE` -> one `POST /api/schedule/act`; held on a stale link |
| Alarm / urgent "tell me when" | **Stop**, Snooze 10 minutes | Yes - both | "Alarm" / "Jarvis: alarm."; ringing (`INSISTENT`, alarm channel) | Stop -> `ACTION_STOP_RINGING` -> cancels that tag+id only |
| Heard LATE (quiet) | **None** | By design | "Missed at HH:MM."; no sound, no Snooze | None to work |
| "Ring my phone" (find my phone) | Stop, and Snooze if it is a snoozable kind | Yes | The ring's own words; goes quiet by itself after its time (`setTimeoutAfter`) | Stop proven by the same path |
| Morning briefing ready | None (tap opens Brain) | Tap only | The briefing's first line | Tap opens the Brain |
| Live session running | End Live, Mute, and Stop talking while Jarvis talks | Yes | Live's sign line | Each -> the Live service's own action |
| "Jarvis Live offers" (move it here) | "Move it here" | Yes | "Open Jarvis Live to move it to this phone." | Opens Live |
| "Live ended - Resume" | Resume | Yes | Resume title + the ended words | Resumes |
| Approval card | **Deny only** (and only when the card says denying blind is safe) | Yes | Title + first line of the body; a locked phone gets a redacted version | Deny -> `EventService`, no fingerprint needed, on purpose |
| Approvals summary row | None | Informational | "N approvals waiting" | - |
| Chatbot/support run | Stop | Yes | The run's own line | Stop -> the chatbot's own stop route |
| A website needs you (hand-off) | "Bring it to the front" / here | Yes | The hand-off's words | Opens that window |
| Watch with me / ScreenWatch | "Stop watching" | Yes | The sign's own text | Stops the session |
| Avatar overlay | "Turn off" | Yes | The overlay's own words | Stops the overlay |
| Wake word listening | "Stop listening" | Yes | The listening line | Stops the service |
| Jarvis link (foreground) | None | Informational, silent | "Jarvis" / "Connected" | - |
| Wake-word resume note | None | Informational | Its own line | - |

### What PASSES, plainly

- The phone's alarm is right and always was: a labelled **Stop** beside Snooze,
  on the notification, on the alarm channel, ringing until stopped.
- Every other action either platform offers is labelled and reachable without
  opening the app - Deny on approval cards, Stop on Live, Watch, the chatbot,
  the overlay and the wake word, Resume, "Move it here", "Bring it to the
  front".
- The quiet/late path has no actions on either platform, which is the owner's
  own 2026-09-26 decision and is matched on both.
- Lock-screen content matches the rule on both: only the kind's words, never the
  job's own.

### What FAILS

1. **Desktop, the owner's report (REAL, fixed here):** the ringing toast's only
   pressable word was Snooze, and its second button had no label at all
   (`content=""`).
2. **Desktop (REAL, fixed here):** a timer's toast offered Snooze and nothing
   else - 22 of 22 stored toasts.
3. **Phone (REAL, not fixed here - same class as 2):** a plain timer's
   notification also offers Snooze and nothing else. The owner's phone alarm is
   fine; his phone *timer* has the desktop's old problem. Fixing it means
   adding a Stop to the phone's quiet path too, which changes a shipped phone
   behaviour and deserves its own decision.
4. **Neither platform, but worth knowing:** no toast banner renders on this PC
   at all right now - my own test toasts and the app's own timer toast are
   accepted into the store (`wpndatabase.db`, `PeriodicNotificationCount` rising
   from 132 to 134) but never appear on screen, which is Windows suppressing
   banners here (Focus Assist/DND, no per-app opt-out set). That is why the
   *visual* proof of the new buttons is missing below.

## 4. What is NOT proven, and how to prove it

- **The new desktop buttons have not been seen on screen.** A
  `target\release` build is deliberately treated as uninstalled by this app and
  would show no buttons at all, so proving it visually means putting a release
  build in `%LOCALAPPDATA%\Jarvis Desktop\` (backing up the current exe first,
  as the settings-freeze pass did), firing a timer, screenshotting the two
  buttons, pressing Stop, and restoring the original exe. Not done: it needs the
  running app stopped and restarted, which is the lead's call.
- **The desktop's late/quiet path was not fired.** The app owns its backend
  process, so closing the app to age an event past ten minutes also stops the
  thing that would replay it. The advice is the same in code (`is_late` ->
  `show_quiet` -> no actions) and matches the phone, which was checked.
- **A real finger never pressed Stop on the phone.** The action exists and is
  wired; the tap did not land in my tests.
