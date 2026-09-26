# Bug audit: the phone app (jarvis-client), 2026-09-26

Read-only audit. No source was changed. Scope: the phone code changed since
2026-09-24, mainly alarms and reminders on the phone, snooze, "tell me when",
focus sessions, "Stop everything", plain error words, the approval card
changes, and the "no screen lock, no risky approval" rule. Server-address
entry and the "what asks first" settings were left out on purpose (other work
is changing them now).

## In short

1. **Nothing found that breaks a safety rule.** No notification or widget can
   approve anything, every new request carries `X-Jarvis-Client: hud`, nothing
   new logs the pairing token, and every new change is held while the link is
   stale.
2. **The worst bug is about alarms on the phone.** If you snooze or stop an
   alarm anywhere other than the phone's own notification (on the PC, by
   voice, or in the phone's Coming up), the phone keeps ringing until someone
   picks it up.
3. **An alarm can ring late on the phone.** If the phone was out of reach when
   it went off, it rings when the phone reconnects, sometimes much later, and
   it does not say it is late.
4. **Some small slips:** after a restart one notification can replace another;
   Stop on a ringing alarm turns the link back on even if you had switched it
   off; Focus and Stop everything show raw network text (with IP addresses)
   instead of the plain words.
5. **It compiles.** The last CI run on this code (run 84, commit `b21c34a`)
   printed "Kotlin errors: (none - so this is a TEST failure, not a compile
   failure)", and since then only a test file and docs have changed. The
   plain-Kotlin parts were also compiled here and their 262 tests pass.

## Table

| # | Severity | Where | One-line bug | Fix size |
|---|---|---|---|---|
| 1 | Medium | `JarvisRuntime.kt` 3140-3157, 3075-3084; `ComingUpPlate.kt` 135-146 | A ringing alarm on the phone is never removed when it is snoozed, stopped or deleted anywhere but its own notification | Small |
| 2 | Medium (owner's call) | `JarvisRuntime.kt` 3140-3191 | A `fired` event replayed after a reconnect rings the alarm late, as if it were live, and says nothing about being late | Small |
| 3 | Low | `ScheduleNotifier.kt` 50-60, 69-72 | Notification numbers restart after the app restarts, so a new alarm or reminder can replace one still in the drawer, and Snooze cannot remove the old one | Small |
| 4 | Low | `EventService.kt` 87-93 | Stop on a ringing alarm reconnects the link even if the owner had switched the link off | One line |
| 5 | Low | `JarvisApi.kt` 411-412, 428, 907-908, 923; `StopEverything.kt` 51-52 | Focus and Stop everything failures show raw network text with IP addresses, not the plain words and their button | Small |
| 6 | Low | `JarvisRuntime.kt` 3165, 3202, 3358 | When the phone cannot read the job, the "shown once" key is `id@0`, so a later firing of the same repeating job is silently dropped | Small |

## Detailed findings

### 1. A ringing alarm is only removed by its own Snooze button (Medium, high confidence in the code, not seen on a phone)

What the code does:

- The only place that removes a phone notification for a job is the
  notification's own Snooze (`EventService.kt:137`:
  `if (changed) runCatching { ScheduleNotifier.cancel(this@EventService, id) }`).
- Coming up's "Just went off" Snooze calls `JarvisRuntime.scheduleAct(job.id, action)`
  (`ComingUpPlate.kt:140`). `scheduleAct` (`JarvisRuntime.kt:3075-3084`) only
  bumps `_scheduleTick`; it never calls `ScheduleNotifier.cancel`.
- When the PC snoozes a job, it sends a `changed` event
  (`backend/jarvis_schedule.py:1217`, `self._changed(jid, kind)` →
  `{"state": "changed"}` at line 862). On the phone, `onScheduleEvent` returns
  as soon as `firedFrom` finds no `"fired"` (`JarvisRuntime.kt:3156`:
  `val (id, kind) = com.jarvis.client.net.Schedule.firedFrom(obj) ?: return`;
  `Schedule.kt:620`). A JVM check confirmed `firedFrom` and `matchedFrom` both
  return null for a `changed` event.
- An alarm's notification is `FLAG_INSISTENT` (`ScheduleNotifier.kt:187`): its
  sound repeats until the notification is touched.

What happens:

1. 07:00. An alarm goes off on the PC. It rings on the PC and on the phone.
2. The owner is at the PC and presses Snooze on the Windows toast (or says
   "snooze", or taps Snooze in the phone's Coming up).
3. The PC snoozes it and sends `changed`. The phone reads Coming up again, but
   leaves its notification alone.
4. The phone, in another room, keeps ringing until someone picks it up. Ten
   minutes later the snoozed copy rings as well, as a second notification.

Fix (small): on a `schedule` event with `"state": "changed"`, and after
`scheduleAct` succeeds, call `ScheduleNotifier.cancel(context, id)` for that
job (or only when the job re-read by id is now snoozed, deleted or done).

### 2. A replayed `fired` event rings the alarm late, as if it were live (Medium, the owner's call; medium-high confidence)

What the code does:

- The phone saves its place in the event stream to disk (`noteResumePoint`,
  `JarvisRuntime.kt:944-958`) and sends it back as `Last-Event-ID` when it
  reconnects (`EventStream.kt:139`).
- The PC then replays everything still in its 512-event ring
  (`backend/rebuilt/jarvis_events.py:57`, `RING = 512`; replay unless the phone
  is stale or new, lines 688-690).
- `onScheduleEvent` (`JarvisRuntime.kt:3140-3191`) has no age check. It reads
  the job, builds the key `id + "@" + firedAt` (line 3165), and if that key was
  not shown in THIS process, it posts, and an alarm rings (line 3187,
  `ring = ...rings(kind, urgent = false)`). The "late" words
  (`Schedule.notification`, `Schedule.kt:610`) only cover the PC being off
  (`job.missed`), not the phone being away.

What happens:

1. 06:55. The phone loses Tailscale (a commute, flight mode, a dead spot).
2. 07:00. The alarm goes off on the PC. The owner may stop it there.
3. 07:40. The phone reconnects. The `fired` event is replayed. The phone rings
   insistently, titled "Alarm", with no sign it is 40 minutes old.

`docs/JARVIS-API.md` section 21 says a reminder missed while away is shown
when the phone reconnects, so showing it may be wanted. Ringing it as a live
alarm is the part to decide. Suggested fix (small): if `firedAt` is more than a
few minutes old, or the job was already snoozed or done, post it quietly with
"Went off at 07:00" and do not ring.

Related, not verified (see "Possible" below): because the "shown once" list
lives only in memory, a process restart plus the 2-second batching of the
saved stream position could replay an alarm the owner already stopped.

### 3. Notification numbers restart after a restart (Low, high confidence in the code)

`ScheduleNotifier.kt:50-51`: `private val assigned = LinkedHashMap<String, Int>()`
and `private var next = 0`, in memory only. `ApprovalNotifier` solved exactly
this with `restore()` ("Past anything already on screen, or the next approval
would overwrite a live one - the collision this whole map exists to prevent,
reintroduced by the restart", `ApprovalNotifier.kt:90-116`); ScheduleNotifier
has no equivalent.

What happens:

1. A reminder is in the drawer as notification 0x3100.
2. The app process restarts with the drawer intact (Android reclaims it and
   restarts the sticky service, or a crash).
3. A timer goes off. `idFor` hands out 0x3100 again, and the timer replaces the
   reminder. If the old one was a ringing alarm, it is silently replaced.
4. Also: a Snooze pressed on a notification from before the restart succeeds on
   the PC, but `cancel` finds nothing in the empty map (`ScheduleNotifier.kt:70`,
   `?: return`), so the notification stays.

Fix (small): seed `next` past any active notification in 0x3100-0x31FF at
first use (as `ApprovalNotifier.restore` does), and let `cancel` fall back to
the notification's own job id extra.

### 4. Stop on a ringing alarm reconnects a link the owner switched off (Low, high confidence)

`EventService.kt:87-93`:

```kotlin
if (intent?.action == ACTION_STOP_RINGING) {
    ScheduleNotifier.stopRinging(this, intent.getIntExtra(...))
    JarvisRuntime.startStream()
    return START_STICKY
}
```

The comment says "Nothing is sent, nothing decided", but it starts the stream.

What happens: an alarm is ringing; the owner turns the link off from the
quick-settings tile (`EventService.stop` → `ACTION_STOP` → `stopSelf()`; the
ringing notification stays, since `onDestroy` clears only approval
notifications). The owner then taps Stop on the alarm. The service is created
again (`onCreate` goes foreground) and the link reconnects against the owner's
choice. Stop does not need the link. Fix: drop `startStream()` from that
branch, and `stopSelf()` when the link was not running.

### 5. Focus and Stop everything show raw network text (Low, verified with a JVM check)

The plain-error words need the failure's kind (`PlainErrors.networkKind`).
Every other call passes it, but two new calls, merged from branches written
before plain errors landed, do not:

- `JarvisApi.kt:411-412` and `907-908`: `ApiError.Unreachable("No desktop address set")`
  (no `PlainErrors.NOT_PAIRED`).
- `JarvisApi.kt:428` and `923`: `ApiError.Unreachable(it.readableMessage())`
  (no `PlainErrors.networkKind(it)`).
- `StopEverything.kt:51-52` then puts `error.detail` straight into the sentence.

A JVM check (the same `PlainErrors` code) gave:

- Focus Start with the PC asleep: "Not changed. Failed to connect to
  /100.101.1.2 (port 8765) from /100.64.3.4 (port 45678) after 10000ms." -
  no "Try again" button. With the kind passed it would read "Your PC isn't
  answering. ..." with "Try again".
- Stop everything: "Stopped speaking. The PC could not be reached to stop
  anything else: failed to connect to /100.101.1.2 (port 8765) ...".
- No PC saved: "No desktop address set." instead of the "not connected to a
  PC yet" words and their "Check the connection settings" button.

This goes against the plain-errors decision (no raw errors or exception text
on screen), and puts the PC's private-network address on screen. Fix: pass the
two missing arguments, and have `StopEverything.describe` use
`PlainErrors.forApiError(error).text` for the unreachable case.

### 6. A failed read by id can hide a later firing (Low, high confidence, rare)

`JarvisRuntime.kt:3165` `val key = id + "@" + (job?.firedAt?.toLong() ?: 0L)`,
and the same shape at 3202 (`#match@`, "tell me when") and 3358 (briefing).
When `GET /api/schedule?id=` fails, the key is `id@0`. A JVM check confirmed
two such keys are equal. So: a reminder "every weekday at 7"; on Monday the
read by id times out (the notification still shows, with the kind's words);
on Tuesday it times out again, the key `id@0` is already in `scheduleShown`,
and Tuesday's reminder is not shown at all. Fix: when the job cannot be read,
use the event's own id (or the time it arrived) in the key.

## Possible, not verified

- **A stopped alarm ringing again after a restart.** `noteResumePoint` writes
  the stream position at most every 2 seconds (`RESUME_WRITE_GAP_MS`,
  `JarvisRuntime.kt:3789`) and flushes the rest only on `stopStream`. Its
  comment assumes a replayed event is "only a doorbell". A `fired` event is not:
  it posts a notification. If the process is killed with the `fired` event's id
  still held back, the next start replays it, `scheduleShown` is empty, and the
  alarm rings again. Whether this happens depends on event timing I could not
  check.
- **"Stop everything"'s answer lost.** `StopEverythingPlate`
  (`HomeScreen.kt:1672-1700`) calls the runtime from its own
  `rememberCoroutineScope`. The plate is only there while Jarvis is busy
  (`HomeScreen.kt:949-952`). If the busy state clears before the PC answers,
  the plate leaves the screen, its scope is cancelled, and
  `JarvisRuntime.stopEverything` never sets the notice. Timing not measured.
- **"Stop everything" missing in Full screen voice mode.** It is only in
  `ConversationList`; `VoiceBar` has only the chat Stop
  (`HomeScreen.kt:2410-2418`). Full screen steps aside for a running task
  (`HomeScreen.kt:656-658`), so it is there for tasks; while Jarvis is only
  thinking or speaking, the PC-side part (no more tools for this answer) needs
  "Show chat" first. Probably fine; noted for the parity rule.
- **"Open the card" line covering controls.** `CardWaitingLine` is drawn over
  the bottom of every screen but Home (`MainActivity.kt:2043-2060`) without
  taking space from the screen under it. A button pinned at the very bottom of
  a non-scrolling screen could be hidden behind it. Not checked screen by
  screen.
- **Stopping a ringing alarm from the lock screen on Android 13.** The
  lock-screen version (`ScheduleNotifier.locked`, lines 214-220) has no Stop,
  and on Android 13 the notification is `ongoing`, so it cannot be swiped
  away there. Pulling down the shade should silence it (`FLAG_INSISTENT`), but
  this was not seen on a real phone.
- **"Try again" repeating a quick action.** `ChatSession.retryLast`
  (`ChatSession.kt:674-678`) sends the last question again. If the first try
  dropped after the PC's fast path had already set a timer, "Try again" could
  set a second one. It depends on backend behaviour not checked here.
- **Which card "Open the card" names.** `CardWords.waiting` takes the last item
  as the newest (`CardWords.kt:65`). That is right only if `/api/pending` lists
  oldest first, which is decided in `jarvis_gate` on the owner's PC, not in this
  repo.
- **The token in Details.** `PlainErrors.scrubDetails` is never given the
  pairing token (every call passes only the text). The shape rules still catch
  a 43-character token unless it happens to contain no digit. The PC never
  sends the token back, so this is very unlikely to matter.

## Areas read and found fine

- **Rule 3 (secrets):** every new request goes through `authed()`
  (`JarvisApi.kt:285-289`), which adds the token and `X-Jarvis-Client: hud`;
  the only request without it is the GitHub update check, which must not carry
  the token. The new log lines contain no token and no user words. The phone
  never sends a web-search key (`webSearchPost` refuses any other path).
- **No Approve on any notification or widget:** schedule notifications offer
  only Snooze and Stop; the approval widget offers Deny and "Review" (opens the
  app); approving still goes through `confirmed()` → `BiometricGate` →
  `decide()` (`MainActivity.kt:1947-1960`, `2152-2163`).
- **Rule 4 (stale link):** `scheduleAct`, `addTodo`, `clearList`,
  `addStandbySchedule`, `focusStart`, focus Resume and +10, `setManner`,
  `setWebSearch`, `testWebSearch` and the notification Snooze are all held;
  Pause, Stop and Stop everything are not, as decided.
- **No screen lock, no risky approval:** `SecurityRules.afterApprovalCheck`
  refuses `UNAVAILABLE` in every case; `BiometricGate` maps "nothing enrolled",
  "no hardware" and "unsupported" to `UNAVAILABLE`, and a prompt that cannot
  be shown to a held decision, never a pass. The notice gets "Open
  screen-lock settings" only for those exact sentences.
- **Screenshots:** `FLAG_SECURE` and the blank recent-apps picture follow App
  lock and hidden lists (`MainActivity.kt:624-632`). The lock screen returns
  before anything else is drawn, so "Open the card" cannot show over it.
- **PendingIntents:** all `FLAG_IMMUTABLE`, explicit components, and
  Snooze and Stop share a request code but differ by action, so they never
  overwrite each other. `EventService` is `exported="false"`.
- **Lock-screen privacy:** every schedule notification has a public version
  with only the kind's words; with App lock or hidden lists on, the
  notification itself uses those words; "tell me when" shows the PC's alert,
  never what is watched.
- **Parsers** (`Schedule`, `Focus`, `Reach`, `EmailSending`, `Manner`,
  `PlainErrors`, `StopEverything`, `Briefing`, `WebSearch`, `CardWords`,
  `CardVoice`): only safe casts; missing or wrong-typed fields fall back to
  defaults; an older PC reads as "missing", not as a crash. Their tests pass
  here (262 tests).
- **The email card** shows the whole email: the agent passes `{"text": plan}`
  and `PendingRows` makes that text the card's summary, shown without a line
  limit.
- **Card order and voice lines:** Deny is on the left and Approve on the right
  on the card and the widget; card voice lines are fixed words, never the
  card's; nothing approves by voice.
- **Named lists:** the phone's list-name rule matches the PC's `list_key`, and
  Clear list sends the same count the PC checks (active and paused items).
- **Threads:** the new plates update Compose state on the main thread (the
  network calls switch to IO and come back); `EventService` works on the main
  dispatcher; `ScheduleNotifier`'s map is synchronized.
- **Compiling:** CI run 84 at `b21c34a` compiled the app ("Kotlin errors:
  none") and failed only on `MemoryUsedTest`, which `84ca552` fixed. Nothing in
  `app/src/main` has changed since. Run 85 (HEAD) was still running when this
  was checked.
