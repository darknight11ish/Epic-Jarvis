# Android client audit — 2026-10-08

**Nothing here was compiled, run, installed or tested.** This machine has no
Android SDK and virtualization is off in its firmware, so no emulator and no
Gradle build can start. Every statement below comes from **reading source** in
`jarvis-client/`. CI's Gradle build will be the first time any of this code is
compiled. Where something genuinely needs a phone, the report says so instead
of guessing.

**What was audited:** `jarvis-client/` — the app that actually talks to the
backend. `jarvis-android/` was **not** audited as if it ships: its own README
and `CLAUDE.md` say it speaks a protocol invented before `JARVIS-API.md` and
cannot talk to Jarvis at all.

**Why:** a click-audit of the desktop app found a class of real bugs —
controls that did nothing, settings that silently failed to save, two cards
with the same name doing different things, a card that could never be reached,
a dead menu group. This is the same audit, for the phone.

**Coverage, stated honestly.** The 13 largest screens, `net/`, `data/`,
`service/`, `platform/`, `widget/` and the navigation were read. The very
large work plates — `QuizPlate.kt`, `DecksPlate.kt`, `ChatbotPlate.kt`,
`ProjectsPlate.kt`, `GoalsPlate.kt`, `ProgressPlate.kt`, `SupportPlate.kt`,
`BriefingPlate.kt`, `WatchPlate.kt`, `SharedPlate.kt`, `UsedMemoriesPlate.kt`,
`TopicsPlate.kt` — were searched for the private-material gates, the
stale-link gate and their write calls, **not read line by line**. That is the
least-covered part of the app and the most likely place for another finding.

The parent agent verified every finding below by re-reading the named lines.
Two candidate findings produced by the first pass were **disproved** on
re-reading and are recorded at the end under "Checked and withdrawn" so a
later pass does not re-report them.

---

## Findings, ranked

### 1. HIGH — "Send test" says the test worked even when the phone posted no notification at all

`jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/PhoneNotificationsPlate.kt:412-432`

```kotlin
onClick = {
    com.jarvis.client.service.ScheduleNotifier.post(
        context, jobId = "test-job", kind = "reminder",
        title = "Jarvis test notification", ...)
    testSent = true
},
...
if (testSent) { Text("Test notification sent.", color = chrome.okInk) }
```

`ScheduleNotifier.post` returns early and only logs when Android has not been
granted the notification permission
(`service/ScheduleNotifier.kt:128-131`):

```kotlin
if (!allowed(context)) {
    Log.w(TAG, "POST_NOTIFICATIONS is not granted, so a $kind that went off is not shown")
    return
}
```

**What the code does:** `testSent = true` is set unconditionally, so the
green "Test notification sent." appears whether or not anything was posted.

**What the UI promises:** "Send test" is the only way to check that the
phone's alerts work. It reports success in exactly the state where every
reminder and — worse — every approval notification is being silently dropped
(`service/ApprovalNotifier.kt:133-138` counts those in `silenced`).
`MainActivity.kt:248-258` calls that "the worst shape a failure can take for
rule 4".

**Confidence:** CONFIRMED that the success message does not depend on the
permission. Whether the permission is granted *on the owner's phone today* is
a device fact I cannot see.

**Smallest honest fix:** check the permission before claiming success — show
the permission prompt and the same words `ScheduleNotifier` logs, and never
"Test notification sent." until something was actually posted.

### 2. MEDIUM — a Deny that does not reach the PC freezes the approval card's buttons and swipe

`jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt:3074-3083`

```kotlin
onDeny = { item -> JarvisRuntime.decideDetached(item, approve = false) },
onApproveWithReset = { item, onReset ->
    scope.launch { val sent = approveItem(item); if (!sent) onReset() }
},
onDenyWithReset = { item, onReset ->
    JarvisRuntime.decideDetached(item, approve = false)   // onReset never called
},
```

The card passes a reset closure precisely so a decision that does not go out
un-sticks it (`ui/approval/ApprovalCard.kt:246-250`):

```kotlin
val deny: () -> Unit = {
    decided = true
    haptics.performHapticFeedback(HapticFeedbackType.Reject)
    onDeny { decided = false }
}
```

Both buttons and the swipe are gated on that flag
(`ApprovalCard.kt:275`, `:623-624`), and `decided` is only ever cleared by the
reset the card hands in.

**What the code does:** the approve path honours the callback; the deny path
accepts it and never calls it.

**What the UI promises:** the card stays on screen with an explanation of the
failure, but neither Approve nor Deny can be tapped and the swipe is ignored
until the card expires or the owner leaves Home and comes back.

**Confidence:** CONFIRMED by reading both files. Whether Compose's
`remember(item.id)` keeps `decided` true across the queue refresh is inferred,
not run.

**Smallest honest fix:** honour the callback as the approve path does —
`if (JarvisRuntime.decide(item, approve = false) is ApiResult.Failed) onReset()`.

### 3. MEDIUM — the Mute tile can send "mute" twice, so a second tap never unmutes

`jarvis-client/app/src/main/java/com/jarvis/client/service/LinkTileService.kt:98-105`

```kotlin
val muted = JarvisRuntime.attention.value.muted
...
scope.launch { JarvisRuntime.setMuted(!muted) }
```

`setMuted` writes nothing locally; it POSTs and only then re-reads
(`JarvisRuntime.kt:3481-3487`), and the POST throws away the budget the
endpoint returns (`net/JarvisApi.kt:2588-2598`). On Android the `attention`
event does not carry the state — it triggers a full `GET /api/attention`
(`JarvisRuntime.kt:1445`, and the file's own comment that "the bus is a
doorbell").

**What the code does:** until that round trip lands, the tile still reports
the old value, so a quick second tap reads the same `muted` and sends the same
command again. Tap once to mute, tap again to unmute — the second tap mutes
again.

**What the UI promises:** the tile shows "Muted"/"Muted · N waiting" and
reads as a two-way toggle.

**Confidence:** CONFIRMED for the two-taps-same-command path. The source
comment at `LinkTileService.kt:94-97` describes this class of bug as already
fixed; it was fixed for `blocked_by` specifically, not for this.

**Smallest honest fix:** hold the requested state locally (show "Muting…"
until the re-read agrees) and ignore taps while a mute POST is in flight.

### 4. MEDIUM — Security's footer says turning something on is always instant; two switches are not

`jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SecurityScreen.kt:257-266`

```kotlin
Text("Saved on this phone only, never sent to your PC. Turning something on is " +
     "instant. Turning something off, or making it looser, asks for your " +
     "fingerprint or PIN first. ...")
```

`data/Security.kt:337-346` counts `(!from.swipeDecides && to.swipeDecides)` and
`(!from.screenRead && to.screenRead)` as **loosenings**, and
`MainActivity.kt:3479-3505` sends every loosening through `ownerCheck`. So
turning on "Swipe to approve or deny" (`SecurityScreen.kt:191-197`) and "Let
Jarvis read this phone's screen" (`LookPlate.kt:55-61`, under
`SecurityScreen.kt:231-233`) both ask for the fingerprint or PIN.

**What the UI promises:** the footer's first sentence says turning on is
always instant. The second sentence ("or making it looser, asks…") is true and
does cover these, so the screen contradicts itself. Screen's own comment above
`item(key = "look")` agrees with the code, not the footer.

**Confidence:** CONFIRMED. This is a wording defect only — the behaviour is
the correct, careful one.

**Smallest honest fix:** drop "Turning something on is instant" and leave
"Making it looser asks for your fingerprint or PIN first."

### 5. MEDIUM — the promised card can be lost for the day after a restart, and a refresh can resurrect one already answered

`jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt:923`, `:1475-1478`

```kotlin
var cachedSleepOffer by remember { mutableStateOf<JsonObject?>(null) }
...
if (offer != null && cachedSleepOffer == null && !sleepOfferDismissedToday && !sleepOfferAnswering) {
    cachedSleepOffer = offer
}
```

The card payload is plain `remember`; the suppression flag is
`rememberSaveable` (`:930`). The file's own comment (`:917-922`) justifies
this by saying the payload "re-populates… from the still-cached server data".
The server consumes the day's offer on the **read**, not on the answer
(`backend/jarvis_sleep.py`'s `_seen`).

**What the code does:** after a process death the payload is gone, the
restart's read returns no offer, and the card cannot appear again that day. A
rotation during an in-flight write can also re-adopt an offer whose write
already landed, because `sleepOfferAnswering` is plain `remember` (`:933`).

**What the UI promises:** the card is the daily offer to set a standby time.

**Confidence:** CONFIRMED for the mechanism; the exact window depends on
timing I cannot see.

**Smallest honest fix:** make the payload `rememberSaveable` (or re-read it
with the day's own key) so the card and its answering flag share one lifetime.

### 6. MEDIUM — "Open my spending" is answered "only in Jarvis on your PC", but the phone has it

`jarvis-client/app/src/main/java/com/jarvis/client/ui/OpenPlace.kt:109-125`

```kotlin
val PC_ONLY: Set<String> = setOf(
    "shortcuts", "account-secrets", "chatbot-api-keys", "tool-updates",
    "more-options", "crash-notes", "start-jarvis", "spending", ...
)
```

The phone does have the place: `BrainScreen.kt:530` draws `SpendingSection`
under `item(key = "spending")`, `ui/MenuPlaces.kt` already maps `"spending"` to
`"settings.spending"`, and `net/MenuCatalog.kt:64` marks that menu
`phone = true, hide = true`. Saying "open my spending" therefore answers
"That setting is only in Jarvis on your PC, not on this phone."

**What the UI promises:** one plain sentence telling the owner to go to the
PC for something he is holding in his hand.

**Confidence:** CONFIRMED in the phone's own source. The id has to arrive
from the PC's settings registry for the wrong sentence to be spoken, which I
did not run.

**Smallest honest fix:** move `"spending"` out of `PC_ONLY` into `PLACES` as
`Where.Go(Screen.BRAIN, "spending")`.

### 7. MEDIUM — the "Never look at" app picker lists every installed app on the main thread

`jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/LookPlate.kt:116-118`

```kotlin
val candidates = remember(security.neverApps) {
    store.installedApps(skipNotificationList = false)
        .filter { it.packageName !in security.neverApps }
```

`installedApps` walks `pm.getInstalledApplications(GET_META_DATA)` and asks
each app for its label (`data/NotificationAllowListStore.kt:113-119`). This
runs during composition. The identical call in
`PhoneNotificationsPlate.kt:258-264` was moved to `Dispatchers.IO` with a
comment saying it "froze the screen (bug audit 2026-09-29)".

**What the UI promises:** "Add an app" opens a picker.

**Confidence:** CONFIRMED that it is on the main thread. How bad it is on the
owner's phone is not observable here.

**Smallest honest fix:** copy `PhoneNotificationsPlate`'s `produceState`
loader and show a "Looking for apps…" line until it arrives.

### 8. LOW — "Show everything saved automatically" scrolls by index, so it can open a different list

`jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/BrainScreen.kt:712-716`

```kotlin
onOpenAutoList = {
    val here = listState.layoutInfo.visibleItemsInfo
        .firstOrNull { it.key == "memory-counts" }?.index
    if (here != null) listScope.launch { listState.animateScrollToItem(here + 1) }
},
```

The next item is only "Saved automatically" while that menu is drawn
(`BrainScreen.kt:729` guards it). It is hideable: `net/MenuCatalog.kt:95` marks
it `hide = true`, and `net/MenuState.kt:102-104` lets the owner hide it from
"Show or hide menus". The button is labelled "Show everything saved
automatically" (`net/MemoryUsed.kt`).

**What the code does:** with that menu hidden, `here + 1` is "Always keep in
mind" (`BrainScreen.kt:745`) and the promised list is not on screen. The app
already has the right tool for this — `MenuState.visitSet` shows a hidden menu
for the visit — and this button does not use it.

**Confidence:** CONFIRMED that the arithmetic is by index. It bites only when
the owner has hidden that menu, which is a setting I cannot read here.

**Smallest honest fix:** scroll by key, as `ui/parts/ScrollToKey.kt` already
does elsewhere.

### 9. LOW — "Clear the numbers" refills the PC's made-up figures

`jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/RetirementPlate.kt:229-238`

```kotlin
Quiet("Clear the numbers", enabled = !busy, onClick = {
    values = Retirement.startingValues(d)
    ...
})
```

`startingValues` returns exactly the fields with a placeholder default
(`net/Retirement.kt:151-153`) — the assumed figures the screen starts with.

**What the UI promises:** the label says the numbers will be cleared; after
the tap every "assumed" box still shows a number.

**Confidence:** CONFIRMED.

**Smallest honest fix:** rename it "Start over", or clear the owner's own
boxes and restore only the placeholders.

### 10. LOW — "Reading…" on the job list can never appear, so its colour branch is dead

`jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/TasksPlate.kt:117`

```kotlin
color = if (read is Tasks.Read.Reading) chrome.textMid else chrome.warnInk,
```

`read` is only ever assigned `JarvisRuntime.tasks()`, which returns `Loaded`,
`OlderBackend` or `Failed` (`net/Tasks.kt:171-180`). A whole-repo search found
`data object Reading : Read` at `net/Tasks.kt:137` and no construction of it
anywhere — unlike `SectionRead.Reading`, which is used in six places.

**What the UI promises:** `Tasks.readLine` has a "Reading…" string and the
plate has a colour for it, so the screen was written to say it is reading.
While the first read is in flight the plate shows its static intro sentence.

**Confidence:** CONFIRMED that nothing constructs it.

**Smallest honest fix:** set `read = Tasks.Read.Reading` before the call, or
delete the state and both branches.

### 11. LOW — "Hear it" prints the same result line twice

`jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/VoicesScreen.kt:635-650`

Two blocks with the same predicate — `saidFor == c.id && said.isNotBlank()`
and `said.isNotBlank() && saidFor == c.id` — draw the same `said` string in
the same column. Only the first carries `Modifier.liveStatus()`, so a screen
reader may also announce it twice.

**What the UI promises:** one line saying what happened when that voice's
"Hear it" was pressed; the owner sees it duplicated, so a real error reads as
a rendering fault. A merge (`ded67a59`) appears to have re-added a copy the
other side had removed.

**Confidence:** CONFIRMED.

**Smallest honest fix:** delete the second block and keep the `liveStatus`
one.

### 12. LOW — one setting, two names: "Quality" and "Sharpness" are the same control

`jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/FaceEditor.kt:164-187`
and `ui/screens/AnimalOptionsPlate.kt:183-199`

Both draw `QualityTier.entries.chunked(2)` and both write
`faceTuning.quality` / `tuning.quality` with the same
`copy(quality = it, autoAdjust = false)`. `AppearanceScreen.kt:554-555` and
`:650-651` hand the *identical* value and callback to both. There is exactly
one stored field (`data/FaceTuning.kt:20-21`), and it is phone-only.

**What the UI promises:** two differently-named settings on one screen, so
the owner can reasonably believe sharpness and quality are separate knobs. He
can change "Sharpness" and watch "Quality" move.

**Confidence:** CONFIRMED. ("Frame rate" is duplicated too, but with the same
name in both places.)

**Smallest honest fix:** give one of the two sections a pointer to the other,
or use one name for both.

---

## Two more wordings worth one line each

- `ui/screens/SettingsJump.kt:40-42` names "Look at this and Watch with me"
  and "Smartwatch notifications"; the sections they scroll to are headed
  "Picture mode" (`ScreenPicturePlate.kt:82`) and "Notifications"
  (`WatchNotifyPlate.kt:147`). CONFIRMED, cosmetic — the jump still lands on
  the right row, only the heading differs.
- `ui/screens/FloatingAvatarPlate.kt:92-97` promises a draggable floating
  circle and names only Android's "Allow bubbles" switch as what can stop it.
  `service/WakeWordService.kt:636-639` records a second, unfixed blocker
  (`NotificationCompat.MessagingStyle`). The paragraph is honest about one
  blocker and silent about the other. Whether the bubble actually appears
  needs a real Android 11+ phone.

---

## Checked and found clean

- **The non-negotiable rules hold where I could check them.** No
  speech-to-text on the phone (the recogniser is a stub that errors,
  `Speaker.speakOnDevice` refuses network voices rather than synthesising
  remotely); no browsable model catalogue (rows come from the phone's own
  read of installed models, and installing is a hand-typed reference); no
  memory graph; no "keep all"/bulk approve anywhere; and nothing clears a
  rush latch — the rush latch is drawn read-only with the words "Nothing is
  approved from here. A latch is cleared where the scanner runs."
- **Screenshots are blocked correctly by condition** (`data/Security.kt:324-330`
  with `MainActivity.kt:1016-1028`), and "Hide memory lists and chat history"
  really hides the chat thread, the used-memories list, the memory plates and
  the spending table.
- **`X-Jarvis-Client: hud`** is added in the one place requests are built, and
  no token or key was found logged or written in plain text.
- **The loosening rule is right in the code**: every loosening on the Security
  screen goes through `ownerCheck`; tightening is instant.
- **Settings jump list matches its rows in both directions** — the 18
  `SettingsJump` keys are exactly the 18 real `item(key = …)` rows.
- **Read-only plates are honest about it**: Reach, EmailSending, Backup,
  PcHelp, Skills and FeaturesScreen contain no write path at all.
- **A late alarm rings only if at most 10 minutes late**; the silent "missed"
  path is wired.
- **Crisis handling**: a crisis turn does not join the scrollable thread, and
  "A difficult moment" is the PC's own title.
- **ApprovalsScreen** is read-only exactly as documented; no screen was found
  unreachable from navigation.

## Checked and withdrawn (not findings)

Two things the first pass reported that **do not hold** on re-reading, so a
later audit should not re-report them:

- **"The Mute tile sends the opposite of what it shows."** False. `onClick`
  reads the same field the tile draws from — the one writer is the
  `GET /api/attention` result. The real defect is finding 3.
- **"The overnight card is held only in `remember` and its suppression is
  consumed server-side."** Muddled. The suppression flag is `rememberSaveable`;
  what the server consumes on read is the *offer*. The real defect is
  finding 5.

---

## Could not check without a phone (and no SDK)

These genuinely need a device or a compile — none can be settled by reading:

1. **Whether any of it compiles.** No SDK here. CI's Gradle build is the first
   compile. Every line number and every quote above is from the source as it
   sits on this branch at `165e8f2d`.
2. **Whether `POST_NOTIFICATIONS` is granted on the owner's phone today** — the
   finding is the missing check, not the current state. Only the phone can show
   whether the test notification actually arrives, whether approval
   notifications are currently being dropped, and whether the tile's "Muted"
   subtitle agrees with what a tap did.
3. **Whether App lock really blocks screenshots and recents**, and whether the
   biometric prompt and the Keystore behave after a reboot. The condition
   logic is right; the OS behaviour is not observable here.
4. **Whether a Floating Jarvis bubble appears at all** on Android 11+ — the
   project's own note says try it on a real phone.
5. **SSE reconnection and the stale-link gate under a real half-open socket**,
   including the 70-second keepalive watchdog (`JarvisRuntime.kt:1111-1212`).
   The gate is read, not exercised.
6. **Live audio**, the 2-second voice check, the headset button and the
   hand-off frames.
7. **TalkBack ordering and announcements**, and whether any of the jank in
   finding 7 is visible.
8. **Whether a given menu is hidden for the owner** — menu visibility is
   server-driven, so findings 8 and 12 may or may not be reachable in his
   configuration.

*Read, not tested. Nothing in this report claims the app was run.*
