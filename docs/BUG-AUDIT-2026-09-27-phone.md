# Bug audit: the phone app (jarvis-client), 2026-09-27

Read-only audit. No source was changed. Scope: the phone code added on
2026-09-27 that had never had a bug audit, mainly "Floating Jarvis" (the
Bubble and Overlay avatar, "open a chat") and "open a settings section by
voice or chat", and how the two merged together in `MainActivity.kt` and
`SettingsScreen.kt`. After that, a lighter sweep of the rest of
`jarvis-client/app/src/main/java/`.

There is no Android build in this container, so this is careful reading plus
the real CI logs from GitHub (the only compiler this project has for the
phone).

## In short

1. **The phone app does not build right now.** One line in the new Bubble
   code uses something Android does not let apps change. GitHub's build has
   failed on it four times in a row (runs 130 to 133), so no new phone app has
   been made since Floating Jarvis was added. The fix is small.
2. **Even once it builds, Bubble will probably never appear.** Android only
   turns a notification into a bubble when it is a chat-style conversation
   with a shortcut, and never for the kind of "I am running" notification it
   is attached to. This is from my memory of Android's own source, not seen
   on a phone, so treat it as very likely rather than certain.
3. **"Open web search" (and most other sections) scrolls to the wrong place.**
   The list of where each section sits was written before Floating Jarvis
   added a new section above them, so it now lands one section too early.
4. **After "open ... settings", the app can jump back into Settings on its
   own** - for example when the phone is turned sideways later - and opening
   Settings by hand scrolls again, until the next question is asked.
5. **Smaller things:** the overlay notification's "Turn off" only lasts until
   Jarvis is next opened; a rare start-up path in the overlay could crash the
   app; and the phone and the PC each keep their own, different list of
   "open a chat" phrasings, so with Floating Jarvis off the PC says "Here you
   go." and nothing opens.
6. **Nothing found that breaks a safety rule.** The overlay shows nothing but
   a dimmed, plain icon while App lock is on, tapping it always goes through
   the app's own lock screen, nothing new is sent to the PC or logged, and
   "open settings" only ever moves between screens.

## Table

| # | Severity | Where | One-line bug | Fix size |
|---|---|---|---|---|
| 1 | High | `service/WakeWordService.kt` 622 | `notification.bubbleMetadata = ...` does not compile (`'val' cannot be reassigned`); CI runs 130-133 fail, no new APK since | Small |
| 2 | Medium (owner's call) | `service/WakeWordService.kt` 578-628, 715 | Bubble is attached to a foreground-service notification with no conversation shortcut, which Android (11+) will not show as a bubble | Medium, or remove Bubble |
| 3 | Medium | `ui/screens/SettingsScreen.kt` 65-77, 216-235 | `SETTINGS_ITEM_INDEX` was not shifted for the new `floating-avatar` item, so every section from "manner" down scrolls one item too early | Small |
| 4 | Low-Medium | `MainActivity.kt` 776-779, 1785; `ui/screens/SettingsScreen.kt` 129-132; `net/ChatSession.kt` 200-213 | `openSettings` is never consumed: a rotation (or any activity rebuild) jumps back into Settings, and every manual visit re-scrolls, until the next question | Small |
| 5 | Low | `service/AvatarOverlayService.kt` 114-125, 328; `MainActivity.kt` 646-654, 2405 | The overlay notification's "Turn off" is undone the next time the app comes to the front | Small |
| 6 | Low | `service/AvatarOverlayService.kt` 90-98 | `stopSelf()` before `startForeground()` in a service started with `startForegroundService` - Android crashes the app for this | Small |
| 7 | Low (owner's call) | `net/OpenChatPhrase.kt` 28-45; `backend/jarvis_quick.py` 1792-1799, 2117-2123 | Two different "open a chat" phrase lists; the phone ignores the PC's `quick: "open_chat"`, and the PC answers "Here you go." even when nothing will open | Small |

## Detailed findings

### 1. The phone app does not compile (High, confirmed by CI)

`WakeWordService.kt:622`, inside `attachBubble`:

```kotlin
notification.bubbleMetadata = Notification.BubbleMetadata.Builder(bubbleIntent, icon)
    .setDesiredHeight(BUBBLE_HEIGHT_DP)
    .setAutoExpandBubble(false)
    .setSuppressNotification(false)
    .build()
```

`android.app.Notification` has a public `getBubbleMetadata()` but its setter
is hidden from apps (apps set bubble data on the builder instead), so to
Kotlin `bubbleMetadata` is a read-only property. The `Jarvis client`
workflow on GitHub says exactly that, in its "Kotlin errors" group:

```
e: file:///home/runner/work/Epic-Jarvis/Epic-Jarvis/jarvis-client/app/src/main/java/com/jarvis/client/service/WakeWordService.kt:622:26 'val' cannot be reassigned.
> Task :app:compileDebugKotlin FAILED
```

That is run 133 (commit `959bd719`, the current head). Runs 130, 131 and
132 (every push since the Floating Jarvis merge `c514b65`) also failed. Run
129, the last one before it, compiled ("Kotlin errors: (none - so this is a
TEST failure, not a compile failure)").

What this means for the owner: the `client-latest` release only updates
when the build passes, so the phone app on offer is still the one from
before Floating Jarvis. None of the 2026-09-27 phone features (Floating
Jarvis, "open settings", "suggest the bigger model") are in any APK yet.

It was the only error the compiler reported, which suggests the rest of the
new code (the overlay service, both `SettingsScreen.kt` parameter groups,
the `MainActivity.kt` wiring) type-checks. That is good evidence, not proof:
a failed compile never gets as far as the later build steps.

Fix (small): set the bubble on the builder before `build()` -
`NotificationCompat.Builder.setBubbleMetadata(NotificationCompat.BubbleMetadata...)`
- or drop the Bubble option (see finding 2 first, since it decides whether
the fix is worth making).

Also expect, once this compiles: the unit tests have not run since run 129,
where `MemorySharedTest.theWordsAreBothAppsWordForWord` failed ("the desktop
does not say: Tagged. It is now in "Between us"."). Neither the test,
`net/MemoryShared.kt` nor `jarvis-desktop/src/memory-shared.js` has changed
since, so that failure is most likely still there. It is a test problem, not
an app bug: the JS file writes the quotes as `\"`, and the test looks for
them unescaped.

### 2. Bubble will very likely never show (Medium, the owner's call; medium-high confidence)

What the code does (`WakeWordService.kt`):

- `goForeground` builds the "hey Jarvis" listening notification with
  `NotificationCompat.BigTextStyle` and no shortcut or `Person`, then, when
  the setting is Bubble, calls `attachBubble(notification)` (line 715) and
  passes it to `ServiceCompat.startForeground(..., FOREGROUND_SERVICE_TYPE_MICROPHONE)`.
- The comment on `attachBubble` says the `Builder(PendingIntent, Icon)`
  form "needs no associated shortcut ... which is why it is the one used
  here: this is not a messaging app."

Why that is not enough: the builder does not need a shortcut, but Android
decides separately whether a notification may be shown as a bubble. From my
reading of Android's own `BubbleExtractor` (Android 11 and later), a
notification is only allowed to bubble when all of these hold:

- it is a **conversation** (MessagingStyle, tied to a long-lived sharing
  shortcut) and has shortcut info, and
- it is **not** a foreground-service notification
  (`(flags & FLAG_FOREGROUND_SERVICE) == 0`).

Otherwise Android quietly removes the bubble data. The listening
notification fails all three (not MessagingStyle, no shortcut, and it IS the
foreground-service notification). The app targets SDK 36 and has
`minSdk` 33, so the older, looser rules never apply.

I have not seen this on a phone and cannot check Android's source from here,
so I am stating it as very likely, not certain. The owner-facing text in
`FloatingAvatarPlate.kt` ("it gets a small floating circle you can drag
around") would then promise something that never appears, and the only hint
offered is Android's own "Allow bubbles" switch, which would not help.

Fix (owner's call): either remove Bubble and keep Overlay (the simplest,
honest option), or rebuild it as its own conversation-style notification
(MessagingStyle, a `Person`, a long-lived dynamic shortcut) that is not the
foreground-service one. A related question for that rebuild, not checked:
whether a bubble can expand `MainActivity`, which is `launchMode="singleTask"`.

### 3. "Open <section>" scrolls to the wrong section (Medium, high confidence)

The two pieces of work were merged without a text conflict, but they do not
fit together.

`SettingsScreen.kt:65-77` - the map, written by the "open settings" work:

```kotlin
private val SETTINGS_ITEM_INDEX: Map<String, Int> = mapOf(
    "voice" to 0,
    "security" to 1,
    "appearance-card" to 2,
    "manner" to 3,
    "web-search" to 4,
    ...
    "watch-notify" to 10,
)
```

`SettingsScreen.kt:140-237` - the list as it is now, after the Floating
Jarvis work inserted its own item at position 3:

| Position | Item key |
|---|---|
| 0 | `voice` |
| 1 | `security` |
| 2 | `appearance` |
| 3 | `floating-avatar` (new) |
| 4 | `manner` |
| 5 | `web-search` |
| 6 | `asks-first` |
| 7 | `reach` |
| 8 | `email-sending` |
| 9 | `folders` |
| 10 | `backup` |
| 11 | `watch-notify` |

`LaunchedEffect(initialSection)` (lines 129-132) calls
`listState.animateScrollToItem(index)`, which puts that item at the top. So
"open how Jarvis talks" puts Floating Jarvis at the top, "open web search"
puts "How Jarvis talks" at the top, and so on down to "open smartwatch
notifications", which puts Backups at the top. The wanted section is just
below, and may or may not be on screen, depending on how tall the one above
is. `voice`, `security` and `appearance-card` are still right.

(`appearance-card` is the PC's id for Appearance, from
`backend/jarvis_settings_registry.py:125`, so that key differing from the
phone's own `appearance` item key is deliberate and fine.)

The map's own comment says it is kept by hand "so a reordering of the items
below is a visible two-line diff here too" - but the two changes were made
in separate branches, so neither diff showed it.

Fix (small): add `"floating-avatar" to 3` and shift the rest by one; better,
look the index up from the item keys so it cannot drift again. There is also
no `floating-avatar` section on the PC's list, so "open Floating Jarvis"
cannot be said at all - a gap, not a bug.

### 4. A stale "open settings" answer re-opens Settings on its own (Low-Medium, high confidence in the code)

What the code does:

- `ChatSession.send` sets `_openSettings` from the answer's header
  (`ChatSession.kt:462`) and clears it only when the NEXT question is sent
  (line 301) or a new conversation starts (line 718). Nothing clears it
  once it has been acted on.
- `MainActivity.kt:776-779`:

  ```kotlin
  val openSettingsTarget by chat.openSettings.collectAsState()
  LaunchedEffect(openSettingsTarget) {
      if (openSettingsTarget != null) nav.go(Screen.SETTINGS)
  }
  ```

  A `LaunchedEffect` runs every time it first enters a composition, not
  only when its key changes.
- The screen stack is saved across an activity rebuild
  (`rememberNavState` uses `rememberSaveable`, `ui/Nav.kt:173-174`), and
  `ChatSession` lives in `JarvisRuntime`, so it survives too.
- `MainActivity` declares no `configChanges`, so a rotation, a switch
  between light and dark mode, a font-size change, or a window resize (now
  more likely, with `resizeableActivity="true"` added for Bubble) rebuilds
  the activity.

What happens:

1. The owner says "open web search". The phone goes to Settings, as meant.
2. The owner goes Back to Home and reads the answer.
3. The phone is turned sideways. The activity is rebuilt, the saved stack
   says Home, `openSettingsTarget` is still `"web-search"`, the effect runs
   again, and the app jumps into Settings.

Also: `SettingsScreen`'s own `LaunchedEffect(initialSection)` runs each time
Settings is opened, so opening Settings by hand afterwards scrolls to web
search again. `ChatSession.kt:207-209` promises the opposite: "cleared with
the answer, like them, so a manual reopen of Settings later does not jump
anywhere on its own."

Fix (small): treat it as a one-time request. For example, a
`ChatSession.consumeOpenSettings()` that the effect calls after navigating,
with the section kept in a `rememberSaveable` in `MainActivity` just long
enough for `SettingsScreen` to scroll once.

### 5. The overlay notification's "Turn off" does not stay off (Low, high confidence)

- The overlay's notification says: `Tap "Turn off" below, or turn "Floating
  Jarvis" off in Settings.` (`strings.xml`, `avatar_overlay_text`), and its
  action is `ACTION_STOP` (`AvatarOverlayService.kt:328`).
- `ACTION_STOP` only calls `stopSelf()` (lines 115-117). The saved setting
  stays `OVERLAY`.
- `MainActivity.onResume` bumps `permissionTick` (line 2405), and
  `LaunchedEffect(floatingAvatar, tick)` (lines 646-654) then calls
  `AvatarOverlayService.start` again, since the setting still says Overlay
  and the permission is still granted.

So "Turn off" means "hide until Jarvis is next opened". Fix (small): have
`ACTION_STOP` also call `JarvisRuntime.settings.setFloatingAvatar(OFF)`, or
relabel the button so it says what it does (for example "Hide for now").

### 6. A rare overlay start-up path can crash the app (Low; medium confidence, rare)

`AvatarOverlayService.start` uses `ContextCompat.startForegroundService`
(line 376). In `onCreate` (lines 90-98):

```kotlin
if (!Settings.canDrawOverlays(this)) {
    Log.w(TAG, "started without the overlay permission; stopping")
    stopSelf()
    return
}
if (!goForeground()) {
    stopSelf()
    return
}
```

On Android 8.1 and later, a service started with `startForegroundService`
that stops before calling `startForeground` makes Android crash the app
("Context.startForegroundService() did not then call
Service.startForeground()"). This is from my memory of Android's
`ActiveServices`, a well-known behaviour, but I have not run it.

When it can happen: only if "draw over other apps" is taken away in the
split second between `MainActivity`'s own check (line 648) and `onCreate`,
or if the service is started some other way (the case the comment itself
says the check is for). Fix (small): call `goForeground()` first and then
stop, or skip the check here, since the caller already made it.

The `goForeground()` failure path has the same shape, but there the
`startForeground` call itself has already failed, so it is a crash either
way.

### 7. Two different "open a chat" rulebooks (Low, the owner's call)

- The phone matches its own list (`OpenChatPhrase.kt:28-45`): "open a chat",
  "open chat", "open jarvis", "open the app", "let's chat", and others.
- The PC, since the Windows floating-face merge, has its own pattern
  (`backend/jarvis_quick.py:1792-1799`): "open a/the chat (window)", "show me
  the chat", "bring up the chat", "open the jarvis bar", and others. It
  answers "Here you go." without the model and puts `"open_chat"` in the
  answer's `quick` field (lines 2117-2123).
- The phone never reads that `quick` field (no `open_chat` anywhere under
  `jarvis-client/app/src/main/java`).

What the owner sees:

- With Floating Jarvis off (the default), saying "open a chat" to the phone
  while it is in the background gets "Here you go." spoken, and nothing
  opens (`JarvisRuntime.kt:582-591` only opens the app when the setting is
  not Off).
- "open the jarvis bar" is a quick answer from the PC but not a phone
  phrase, so the phone says "Here you go." and does nothing even with
  Floating Jarvis on; "let's chat" goes the other way, to the model, and
  also opens the app.

Fix (owner's call): have the phone act on `quick == "open_chat"` from the
answer's header, the same way it reads `open_settings`, and retire the
phone's own list, so there is one list, on the PC.

## Possible, not verified

- **"Open a chat" in Bubble mode, with the app in the background, may do
  nothing.** Android blocks an app from bringing itself to the front from the
  background unless it has an exemption. "Draw over other apps" is one
  (Overlay mode has it); a running microphone service is not. Being the
  phone's default assistant app (Jarvis has a `VoiceInteractionService`) is
  another, so it depends on the phone's setup. `runCatching` would hide the
  refusal (`JarvisRuntime.kt:590`), since Android usually refuses silently.
- **Turning Overlay off in the moment it is starting.** `stop()` does nothing
  while `_running` is false, and `_running` is only set at the end of
  `onCreate` (`AvatarOverlayService.kt:103`, `386`). Choosing Overlay and then
  Off within the same few milliseconds would leave the avatar up. Too fast to
  happen by hand; noted only because the comment on `stop()` assumes it cannot.
- **Scrolling before the list has been laid out.** `animateScrollToItem` in
  `SettingsScreen`'s effect runs as the screen first appears. I did not
  check whether Compose's lazy list always scrolls correctly before its first
  layout.
- **`addAvatarView` records the view even when adding it failed**
  (`.also { avatarView = root }` runs on both outcomes, line 189). Harmless
  today: `removeAvatarView` wraps `removeView` in `runCatching`.

## Areas read and found fine

- **`data/FloatingAvatar.kt` and `net/OpenChatPhrase.kt`:** an unknown or
  missing saved value reads as Off; the matcher only accepts a whole sentence
  from the fixed list (a leading "hey Jarvis" or "Jarvis", case, curly
  apostrophes and trailing `.!?` aside), so "Jarvis" alone or a longer
  sentence never matches. It is only ever used in addition to sending the
  turn, never instead of it.
- **Overlay lifecycle:** every early return in `onCreate` happens before the
  window is added; once added, every way out (`ACTION_STOP`, the setting set
  to Off, the permission gone on the next resume) goes through `stopSelf()`
  and `onDestroy`, which cancels the watcher and the scope and removes the
  window. `START_NOT_STICKY`, so it is never restarted in the background.
- **Touch handling:** a drag past 24 px moves the window with
  `updateViewLayout` on the same root view that was added; only a quick
  `ACTION_UP` without a drag opens the app, never `ACTION_CANCEL`.
  `FLAG_NOT_FOCUSABLE | FLAG_NOT_TOUCH_MODAL`, so touches outside the small
  window reach the app underneath.
- **App lock:** with App lock on, the avatar is always dimmed with no badge,
  whatever the link or listening state (`updateAvatar`, lines 214-221).
  A tap opens `MainActivity`, whose `App()` draws only the lock screen while
  locked (`MainActivity.kt:1039-1053`). No words Jarvis heard or said are
  ever drawn on the overlay.
- **The combined `MainActivity` wiring:** `floatingAvatar` and
  `openSettingsTarget` are both collected with `collectAsState` at the top
  level of `App()`, not inside a branch, and both effects sit before the
  lock-screen return, so the overlay stays in step even while locked, and an
  "open settings" answer only moves the stack behind the lock screen. The one
  `SettingsScreen(...)` call passes both sets of new parameters by name,
  and the compiler reported no error in either file (finding 1).
- **Threads:** `_openSettings` is written from the IO thread under the same
  `call === c` guard as `crisis` and `usedIds`; a `StateFlow` is safe to set
  from any thread, and the screen collects it on the main thread.
- **Permissions and manifest:** `SYSTEM_ALERT_WINDOW` and
  `FOREGROUND_SERVICE_SPECIAL_USE` are declared; the service is
  `exported="false"` with type `specialUse` and its own subtype text; the
  overlay permission is only asked for from its button, after the plain
  explanation.
- **PendingIntents:** all `FLAG_IMMUTABLE` and explicit. The overlay's
  "open" intent is the same as `EventService`'s (request code 0,
  `MainActivity`, no action, no extras), so `FLAG_UPDATE_CURRENT` overwrites
  nothing. The bubble's uses its own request code (3).
- **Rules:** nothing in this work sends anything new to the PC or anywhere
  else (the setting is saved on the phone only); no new request, so every
  request still carries `X-Jarvis-Client: hud`; the new log lines are fixed
  words plus an exception, never the token or the owner's words. "Open
  settings" on the phone is navigation only; the phone never calls the PC's
  "adjust a setting" path itself, and the PC-only settings still refuse
  from the phone on the PC's side.
- **Lighter sweep of the rest:** the 2026-09-26 audit's findings were checked
  quickly and have been fixed (for example, `EventService`'s Stop on a ringing
  alarm no longer restarts a link switched off, and `JarvisApi` passes the
  error kind). The "suggest the bigger model" phone code (`SecondCard.kt`,
  `SecondCardPlate.kt`, `JarvisRuntime.setSecondCardSuggest`) is held while
  the link is stale, like the other writes. `StateFlow.value` reads in UI code
  are all inside callbacks or effects, not in drawing code. The assistant
  entry point (`assistant/JarvisVoiceInteractionSession.kt`) only opens
  `MainActivity`, behind its lock screen. Nothing else found.
