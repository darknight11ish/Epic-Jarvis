# Picture-in-picture: a small Jarvis window over other apps (design)

**Status: DESIGN ONLY - nothing built, nothing measured on a phone.** Written
2026-10-11 on branch `docs/pip-design`, off `main` at `5f382aff`. **Every
question this design raised has been answered by the owner (§9), so the design
is settled and nothing is left open.**

**The owner's words (2026-10-11):** *"can you add a picture in picture mode to
jarvis that's similar to Google maps"* - and when asked what the little window
should show, he chose **all three, as options in Settings**, saying "1 or 3 by
default".

**The lead's call, recorded as his:** three modes, selectable, and the default
is **mode 1** (the face plus the current answer's first line), because that is
always true, whereas mode 3 (Live) needs a Live session actually running or the
window has nothing to show.

**Mode 3 IS automatic while Live runs - DECIDED BY THE OWNER (§9.2), on the
designer's recommendation and with the reasoning accepted as written.** See
§2.4. The SETTING says whether PiP exists and which mode the owner prefers; it
should not be able to leave a Live session invisible in a window that is already
up. Mode 3 joins the default automatically while Live runs and steps aside when
it ends, so "1 or 3" is one preference, not two things to keep in sync.

**Unverified everywhere below** means: not tried on a real phone. Nothing in
this document has been run.

**In one paragraph:** Jarvis gets a small window that stays on screen when the
owner leaves the app - Android's own picture-in-picture, like Maps' next-turn
box. The window shows one of three compact things the owner picks in Settings:
the face with the first line of the current answer, the last few messages of the
conversation, or Jarvis Live continuing while he uses another app. It can never
approve anything, never show a hidden list or a locked answer, and never becomes
a second place to change a setting. Tapping it brings the real app back.

## 1. What already exists, so this does not become a fourth thing doing the same job

Grepped on `5f382aff` and read, not assumed:

- **`data/FloatingAvatar.kt`** - "Floating Jarvis" (`Settings -> This app`,
  menu id `settings.floating-avatar`, `net/MenuCatalog.kt:90`). Two values:
  `BUBBLE` ("bubble") and `OVERLAY` ("overlay"), plus `OFF`. Saved on the phone
  only (`data/ClientSettings.kt`: `KEY_FLOATING_AVATAR`).
- **`service/AvatarOverlayService.kt`** - the Overlay path: a 56 dp
  `TYPE_APPLICATION_OVERLAY` window, `FLAG_NOT_FOCUSABLE or FLAG_NOT_TOUCH_MODAL`,
  drag to move, tap to open the app. It shows a reachability badge and a dimmed
  state, and its class doc is explicit that it "cannot change a setting, approve
  a card, or read anything out loud".
- **The Bubble path** - `Notification.BubbleMetadata`, attached in
  `service/WakeWordService.kt:828`; it needs `android:resizeableActivity="true"`
  on MainActivity, which is already there (`AndroidManifest.xml`, with a comment
  naming the bubble as the reason).
- **`MainActivity` is the only activity**, `launchMode="singleTask"`,
  `resizableActivity="true"`, and the whole app is ONE composable tree switched
  by a `Screen` enum and a `nav` object - there is no second, cut-down activity
  for a floating window to show.
- **Long-running work is already in foreground services**: `EventService`
  (specialUse), `WakeWordService` (microphone), `LiveService` (microphone),
  `ScreenWatchService` (mediaProjection). A PiP window does not need to keep
  anything alive that is not already alive.
- **`data/Security.kt`** - `Security.appLock`, `Security.privateLists`, and
  `LockSession` (`:504`): `privateHidden(s) = s.privateLists && !privateShown`,
  where `privateShown` is cleared when the app relocks (`settle`, `:593`). This
  is the ONE gate the privacy answers in §4 reuse; nothing new is invented.
- **`JarvisRuntime.decide(item, approve, signature)` (`:3821`)** - the one
  function that sends an approval decision, with `decisionBlocker` (`:3779`)
  checking link, staleness, in-flight, still-pending and expiry. The approvals
  notification offers **Deny only, never Approve** (`service/ApprovalNotifier.kt:301`).

**So PiP is a third mechanism, and the honest count is three.** The others are
an overlay window Jarvis draws itself, and a notification-based bubble. PiP is
different in kind: an OS-managed miniature of **this app's own activity**, with
its own system chrome and its own lifecycle. It cannot be folded into
`FloatingAvatarMode`, because that enum's values are two answers to one
question ("how should the floating face appear?") and PiP answers a third,
independent one ("what does the window show when I leave the app?").

## 2. The settings, and what the window shows

### 2.1 One new Settings row, one three-way choice - DECIDED (§9.3)

A new row **`pip-mode`**, "Picture-in-picture", next to "Floating Jarvis"
(Settings -> This app) - **the owner's choice (§9.3)**, over folding it into the
"Floating Jarvis" row as a third value. Plain words before it:

> A small Jarvis window that stays on screen while you use other apps - like the
> next-turn box in Maps. It can never approve anything. Tapping it brings Jarvis
> back.

Three choices, matching the owner's picks:

| Value | Label | The window shows | Default |
|---|---|---|---|
| `off` | Off | nothing (the app just goes to the background) | |
| `face` | The face and the answer | face + state + first line of the current answer | **yes** |
| `thread` | The conversation | the last few messages, the newest at the bottom, scrollable | |
| `live` | Jarvis Live | the Live session (voice, and the camera only if it is on) | |

**Saved on the phone only** (`data/ClientSettings.kt`, key `pip_mode`), like
`floatingAvatar` and every other display setting - nothing about it is sent to
the PC. No new permission: PiP needs none.

### 2.2 Can two of them be on at once? Yes - DECIDED (§9.3)

`Floating Jarvis` and `Picture-in-picture` are **separate rows and may both be
on** - the owner's choice (§9.3). They do different things: the floating face is
a way to TALK to Jarvis without opening it; PiP is a way to SEE something after
leaving it. Turning one on must not silently turn the other off - that is the
kind of hidden coupling that produces a bug report six weeks later.

What happens if both are on is worth stating, because it is visible on screen:

- **Overlay + PiP**: two small Jarvis things on screen at once. That is
  Android's own behaviour with any overlay, not something Jarvis can prevent.
  **The floating face is the one that should yield**: while the PiP window is
  up, `AvatarOverlayService` hides its window (`View.GONE`, not a stop, so the
  setting is untouched) and shows it again when PiP ends. One Jarvis on screen,
  and the one showing real content is the one that stays.
- **Bubble + PiP**: the listening notification's bubble stays as it is. Bubbles
  live in the system's own bubble stack, so they do not fight the PiP window.
- **App lock** does not change any of this (§4).

### 2.3 What each mode draws in a genuinely tiny window

A PiP window is not a phone screen. On a 1080×2400 phone it is roughly
**1/3 of the screen's width** in portrait, taller in landscape. Maps shows the
next turn, not the map, and the same discipline applies here.

**Mode 1 - the face and the answer** (the default, the Maps shape):

```
┌──────────────────────────┐
│  [face]    Listening     │   face: the existing FaceView, small
│                          │   state line: the ONE word/short phrase that
│  Let me check the        │   already exists (Listening / Thinking /
│  weather for…            │   Waiting for you / Not connected)
│                          │
│            ⤢ Expand      │   body: first line of chat.reply, ellipsised
└──────────────────────────┘
```

- The face is the SAME `FaceView` the app already draws, at a smaller size - not
  a new drawing. If the face costs too much in the PiP frame budget it shows as
  a still frame of the same face; that is a build-time measurement, not a
  design choice (**unmeasured**).
- The answer body is **`ChatSession.reply`'s first line**, truncated to one
  line. `reply` is `StateFlow<String>` (`net/ChatSession.kt:74`, "The reply so
  far. Grows as chunks land."), so this needs no new data plumbing - and while
  an answer streams the line grows, which is exactly Maps' behaviour.
- **Dropped:** every button, the sources list, the read-outside-text note, the
  table, any card. Mode 1 never shows a second line, by construction.

**Mode 2 - the conversation:** the last 3-4 entries of
`ChatSession.thread` (`StateFlow<List<ChatHistory.Exchange>>`, `:205`), the
newest at the bottom, scrolled to the bottom on open, and **scrollable in the
window** (a PiP window does take touch in its own bounds). The owner's own
messages are right-aligned and short; Jarvis's answers are clipped to a couple
of lines each. **Dropped:** the input box (typing into a PiP window is a bad
surface - the keyboard would cover the whole thing), the send button, the
toolbar, and any card.

**Mode 3 - Jarvis Live:** the existing Live screen at its smallest useful size -
whether Jarvis is listening, the mute/end controls, and the camera preview only
if the camera is on. **Dropped:** the transcript, the settings, and everything
that is not "is it listening" and "stop it".

**All three** carry exactly one action, `Expand`, which is a
`RemoteAction` in the PiP params: it brings the full app back. No second action
in any mode.

### 2.4 Mode 3 while Live is not running - and 3 IS automatic (decided)

**DECIDED BY THE OWNER, 2026-10-11: yes, automatic.** While a Live session is
running, mode 3's display takes over whatever mode is set, and gives the window
back when Live ends. The reasons below are the ones put to him and accepted as
written:

1. A Live session is a thing the owner started and expects to keep going. If he
   set mode 1 and then started Live, a window showing the last typed answer
   while he is TALKING would be actively misleading.
2. It keeps "1 or 3" honest as ONE preference. The owner said "1 or 3 by
   default", which reads as *either of those is a fine default*, not *make me
   choose per context*.
3. The setting still decides whether PiP exists at all. `off` means no window,
   so nothing about this makes Live harder to stop.

**If Live is not running and the setting is `live`:** the window does NOT close
(it is the owner's window, and closing it would look like a crash). It shows
mode 1's face and state line with one plain line above the answer slot:

> Live is off. Start it and it shows here.

**When Live ends while the window is up:** the same fallback, in place, with no
window animation - the face and "Live is off" replace the Live view. The "Live
ended - Resume" notification already exists (`LiveService`) and is unchanged; the
PiP window does not duplicate it.

## 3. The one architecture decision: a PiP layout, not a shrunken screen

Android mirrors **whatever the activity is currently showing** into the PiP
window. Since MainActivity is one activity with a `Screen` enum, doing nothing
would put a shrunken Settings screen, or a shrunken History list, into the
window - which is not a design, it is an accident.

So: `MainActivity` carries a `pipShowing` state (set from
`onPictureInPictureModeChanged`), and the composable tree renders **the PiP
layout instead of the current `Screen`** while it is true. The PiP layout is its
own small composable per mode, fed by the same `JarvisRuntime` flows the full
screens already use.

- Entering PiP is `setPictureInPictureParams(...)` on every composition where
  the relevant state changes (aspect ratio 16:9, the `Expand` action, and the
  source rect), then `enterPictureInPictureMode()`.
- The aspect ratio per mode: mode 1 and 3 about 16:9; mode 2 taller (about 9:16
  in portrait) because it is a short list.
- **`setAutoEnterEnabled(true)` on Android 12+** means the owner does not press
  an "enter PiP" button at all - swiping home drops it into the window, which is
  the Maps behaviour he asked for. Below Android 12 the same window is reached
  from the app's own PiP button (`enterPictureInPictureMode()`), which works
  from API 26; the app's `minSdk` is 33, so **every supported phone is Android
  13+ and the button is a fallback nobody should need** - it is written down
  rather than assumed, because "minSdk says 33" and "the API behaves" are
  different claims.

**No new dependency.** Checked rather than assumed: `app/build.gradle.kts:298`
already has `androidx.core:core-ktx:1.15.0` (which carries
`androidx.core.app.RemoteAction`, the type a PiP action must be) and `:307` has
`androidx.activity:activity-compose:1.12.4` (whose `ComponentActivity` provides
`enterPictureInPictureMode` and receives `onPictureInPictureModeChanged`).
`PictureInPictureParams.Builder` is framework, present at `compileSdk` 36 with
no support library. `minSdk` is 33 and `targetSdk` 36 (`app/build.gradle.kts`).

**The manifest needs two added attributes** on the `MainActivity` element, and
neither is there today (grepped: no `supportsPictureInPicture`, no
`configChanges`, and zero uses of any PiP API in the whole app):
`android:supportsPictureInPicture="true"` and
`android:configChanges="screenSize|smallestScreenSize|screenLayout|orientation"`,
so Android resizes the window instead of restarting the activity under the
owner. `resizeableActivity="true"` is already present, with the bubble as its
recorded reason.

## 4. Privacy - what must never appear in the window

This project has just spent hours on a plate that was **silently dropped from a
list**, and on a check that was green while the artefact was wrong. So this
section says what is forbidden AND how each is proven to hold (§6).

**Never in a PiP window, in any mode:**

1. **Anything "Hide memory lists and chat history" hides.** The answer text in
   mode 1, the thread in mode 2, and any memory list are all in that set. The
   existing gate decides: `LockSession.privateHidden(s) = s.privateLists &&
   !privateShown` (`data/Security.kt:521`).
2. **Anything App lock hides.** With App lock on and the app not unlocked
   (`LockSession.locked(s)`, `:518`), no answer text and no conversation.
3. **Any approval's words** - title, body, the plan, the exact recipients, the
   search words, the file names. Not truncated, not abbreviated, not "1 new
   approval". See §5.
4. **Any card that acts.** No Approve, no Deny, no Forget, no Send, no "keep
   this fact". The only action anywhere in the window is `Expand`.
5. **The pairing token, the server address, or any key.** This is not new, but
   a floating surface is a new place to leak it and it is listed so no build
   step has to remember.
6. **Anything heard or seen by voice or camera** beyond the state word
   (`Listening`) - never a transcript line, never a camera frame in mode 1 or 2.
   A camera preview exists only in mode 3, where the owner turned the camera on.

**What the window shows when the content IS hidden - DECIDED BY THE OWNER,
2026-10-11 (§10): a dimmed face that says why.**

- **A neutral face, dimmed, and one line: "Hidden while Jarvis is locked."**
  The face is already public information (§1: the floating face shows
  connectivity while App lock is on, the owner's 2026-09-27 decision), and this
  says *why* there is nothing to read, so it does not look broken.
- The other option put to him - the face alone, no words at all - was **not**
  taken.

**The reason he gave is the reason it was written that way:** the failure this
project lived through on the day this design was written was content silently
missing from a list, with no way to tell *hidden* from *broken*. This window
must never reproduce that. It always says which state it is in.

## 5. Approvals are never decided in a PiP window

**If an approval arrives while the window is up:** nothing appears in the PiP
window except, at most, the state word the face already uses (`Waiting for you`)
with no title and no body - and the existing approvals notification, which is
unchanged, is what the owner acts on. That notification offers **Deny only**
(`ApprovalNotifier.kt:301`), and tapping it opens the real app.

**Why a PiP surface is the wrong place to approve anything**, in order:

1. **A PiP window is a glanceable surface.** Android lets a PiP window be
   dismissed, moved, or covered without any interaction from the owner; a
   button in it can be tapped by accident while putting the phone in a pocket.
   The project's rule is that a decision on a card is deliberate.
2. **Risky approvals need the screen lock** (`JarvisRuntime.decide` refuses
   `pcOnly` approvals from the phone at all, `:3837`), and the existing phone
   path is a fresh fingerprint for signed approvals. Approving from a PiP window
   would either skip that or half-show it; both are worse than "open Jarvis".
3. **The approval's own words must be readable to be judged.** A PiP window can
   show a third of a line. Approving something whose recipients and full text
   you cannot read is not an approval.
4. **One door.** `decide()` is where the checks live (`decisionBlocker`,
   `:3779`) - link, staleness, in-flight, pending, expiry. A new surface is a new
   way to reach it, so the honest move is: the PiP window does not call it at
   all, and a future change that wants to must add its own gate there.

If the owner ever wants an approval action in PiP, it should be the same shape
as the notification: **Deny only, and it opens the app for anything real.**

## 6. How each claim is proven to hold

The failure this project just spent hours on was a thing **shown to be in a list
in the source and silently dropped at runtime**. So:

**On a plain JVM (`gradlew :app:testDebugUnitTest`), testable now:**

1. **Mode selection is pure.** `PipMode.fromWire` and "which layout does this
   state draw" (`PipLayout.forState(mode, liveRunning, privateHidden, appLock)`)
   become pure functions, so a test drives the whole truth table: every
   combination of the four inputs, and the assertion that with `privateHidden`
   or `appLock` the answer is the hidden layout and never the answer layout.
2. **THE FORBIDDEN-WORDS TEST ON THE VALUES - the test that makes §4 real
   rather than stated.** A made-up answer is built carrying three things that
   must never survive into a PiP window:
   - a fake secret (`API_KEY=sk-live-0000` style, plus a fake card number);
   - a fake recipient address (a made-up `@example.invalid` address) and a fake
     subject line;
   - a fake approval title and body ("Send this email?", the plan's own words).

   The test feeds that through every PiP formatter - mode 1's first line, mode
   2's thread rows, and the action labels - and asserts **none** of those
   strings appears in any result, in any mode, with `privateHidden` true or
   false. The same shape as the project's existing private-aloud cases.

   This is the test that would have caught the plate: it checks the **value**
   that comes out, not that a function was called. "The formatter ran" is not
   the claim; "the secret is not in the string" is.
3. **The first line, and only the first line.** `PipText.firstLine(reply)` is
   pure: given a multi-line answer it returns one line, ellipsised, with no
   second line and no markdown.
4. **One action, and it is Expand.** A test reads the PiP params builder and
   asserts exactly one action is added and it is `Expand` - so a later change
   that adds an Approve fails here.
5. **A registered setting, or the checks fail.** The new row is a
   `Section(...)` in `backend/jarvis_settings_registry.py` (the "floating-avatar"
   entry at `:306` is the pattern) and the generated
   `jarvis-client/app/src/test/resources/contract/settings-cases.json` is
   regenerated with `tools/gen_settings_cases.py`. `SettingsCatalogTest`,
   `MenuVisibilityTest`, `SettingsJumpTest` and the backend's
   `test_settings_registry.py` then hold it, and the registry's own note at
   `:296-305` records what happened the last time a row was drawn without being
   registered.
6. **The manifest, read as text.** A test asserts `supportsPictureInPicture` and
   the needed `configChanges` are on the `MainActivity` element (the manifest is
   already read as text by `LiveExtrasTest`, `QuickTilesTest` and
   `AlsoOnPhoneTest`), and that NO service gained a new
   `foregroundServiceType` for this feature.

**On the phone, and only there:** whether the window actually appears, what
Android's own chrome does to it, whether the face's frame budget holds in it,
and whether a tap on `Expand` returns the app. §7 is the list.

**What is deliberately NOT claimed:** that a PiP window cannot be photographed
by another app, that `FLAG_SECURE` behaves the same in PiP (it is the same
window, so it should, but that is **unverified**), or that the window is
invisible to Android's recents thumbnail. Those are "we did not measure it"
statements, not assurances.

## 7. What "pass" means on the real phone

Plain steps, with the exact commands. The phone is connected over adb in this
project, and the build is `assembleDebug`.

**Setup, once:**
1. `adb install -r jarvis-client/app/build/outputs/apk/debug/app-debug.apk`
2. In the app: Settings -> This app -> **Picture-in-picture** -> **The face and
   the answer**.
3. `adb shell dumpsys activity activities | Select-String -Pattern "pinned|pictur|MainActivity"`

**Then, per step, with the check that proves it (a pass is the OUTPUT, never the
absence of an error):**

| # | Do this | Pass looks like |
|---|---|---|
| 1 | Open Jarvis, ask something, then swipe up to Home | `dumpsys activity activities` shows `mLastPinnedStackInfo`/`pinned=true` for `com.jarvis.client/.MainActivity`; the window is on screen |
| 2 | Read the window | `adb shell uiautomator dump` shows the face's state node AND a text node whose content equals the FIRST LINE of the answer just given - matched as a string, not "there was some text" |
| 3 | Put a long answer on screen (ask for a list), enter PiP | the dump shows ONE answer line and no second line |
| 4 | Settings -> Picture-in-picture -> The conversation, enter PiP | the dump shows at least two message lines; `adb shell input swipe` inside the window scrolls it |
| 5 | Settings -> Picture-in-picture -> Jarvis Live, start Live, then Home | the window shows the Live controls; `adb shell dumpsys activity services | Select-String JarvisLive` still shows `LiveService` running |
| 6 | While mode 1 is set, start Live, then Home | the window shows the LIVE view, not the answer (the §2.4 automatic swap) |
| 7 | End Live from the window | the window still exists and shows the face with the "Live is off" line; it does **not** close |
| 8 | Turn ON "Hide memory lists and chat history", enter PiP | the dump contains **neither** the answer's first line **nor** any memory word, and **does** contain the decided line from §9.1: "Hidden while Jarvis is locked." |
| 9 | Turn ON App lock, lock, enter PiP | same as 8, with the App-lock wording |
| 10 | Raise an approval on the PC while the window is up | the PiP window's dump contains **no** approval title, body, recipient or plan word, and **no** action other than Expand: `adb shell dumpsys activity activities | Select-String -Pattern "approve|deny"` finds nothing for the PiP session |
| 11 | Tap `Expand` in the window | the full app returns with the same screen it left on |
| 12 | Settings -> Picture-in-picture -> Off, then swipe Home | no PiP window; `dumpsys activity activities` shows no pinned stack; the app is simply in the background and Live, if on, keeps running |
| 13 | With Floating Jarvis = Overlay AND PiP on, enter PiP | exactly ONE Jarvis window is visible; the overlay is hidden while PiP is up and returns when it ends |

### 7.1 The negative controls - not optional, and not tidied away

**For steps 8, 9 and 10, run the SAME dump with the setting OFF first and
confirm the words ARE there.** A dump that never contained the string proves
nothing, and a privacy check that passes because it is looking at an empty
window proves less than nothing - it is the shape of a false pass.

This is not a hypothetical. On the day this design was written, the same
project produced **two** examples of exactly that shape:

1. a plate the source said was composed, which the runtime silently dropped, so
   the screen was checked and looked "fine" while the thing being checked for
   was never there;
2. a `logcat` probe that returned **zero lines in total**, which read like "no
   problem found" when it actually meant "nothing was being observed at all".

Both were caught only because someone checked that the observation apparatus
itself worked before believing its answer. Step 8's OFF run is that check here:
the words must be FOUND when they are allowed, before their absence when they
are forbidden counts as a pass.

## 8. Risks

- **The face in a PiP window.** PiP runs the activity in a shrunken window;
  whether the ray-marched face holds its frame budget there is **unmeasured**.
  If it does not, mode 1 shows a still frame of the face (the same shape as the
  existing "Still" option) rather than dropping the window.
- **Android's own PiP chrome** takes screen space and offers its own close and
  expand controls, which Jarvis does not control and cannot restyle. Whatever is
  designed here is drawn inside a box Android owns.
- **Two floating things at once** (§2.2) is handled for the overlay, but the
  bubble is in Android's stack and the owner can end up with both a bubble and a
  PiP window. That is Android's behaviour, not a Jarvis defect, and the Settings
  text should say so plainly rather than pretend otherwise.
- **`setAutoEnterEnabled`** means the window appears on a swipe home the owner
  may not have intended. The `off` value is the escape, and it must be reachable
  without going through PiP.
- **Mode 2 in a very small window** may show only one and a half messages. The
  design accepts that (Maps accepts the same), but the owner should see it
  before it is called finished.
- **A PiP window is a new place an approval's words could leak** (§5). The
  build step must not add any approval text to the PiP layout "just for the
  state word" - the state word is fixed and already exists.

## 9. The owner's answers (2026-10-11) - all four decided, nothing left open

*(The four questions below were put to him in this shape, recommended option
first. He took the recommendation on every one. Each block keeps the reasoning
he accepted, so a later reader can see what was HIS and what was the designer's.)*

### 9.1 When a list is hidden and the little window is up, what does it show?

- **DECIDED: a dimmed face and "Hidden while Jarvis is locked."**
- Not taken: the face alone, no words at all.
- **His reason, and he said it in these terms:** with the content silently gone
  there is no way to tell *hidden* from *broken* - which is exactly what this
  project spent the day fixing (a plate the source said was drawn and the
  runtime dropped). The window always says which state it is in.

### 9.2 Should the window switch to Live by itself while a Live session runs?

- **DECIDED: yes - Live takes the window while it runs, and gives it back
  after.** The three reasons in §2.4 are accepted as written.
- Not taken: the window shows only what the setting says, so mode 1 would hide
  a running Live session entirely.

### 9.3 Where does the setting live?

- **DECIDED: its own row, "Picture-in-picture" (`pip-mode`), next to "Floating
  Jarvis" - and both may be on at once.** The overlay hides (`GONE`) while PiP
  is up, and the setting itself is never touched (§2.2).
- Not taken: a third value inside "Floating Jarvis", which would have meant the
  owner could not have the floating face AND the window.

### 9.4 Is one `Expand` action enough?

- **DECIDED: `Expand` only.** Approvals are never decided in the window, and
  `decide()` (`JarvisRuntime.kt:3821`) is not called from that surface at all
  (§5).
- Not taken: `Expand` plus Deny for an approval - quicker on a card, and it puts
  a decision one accidental tap away in a window Android can move or cover.

**Nothing is open.** The three things this document deliberately does NOT
answer are in §8, and they are not questions for the owner - they are
measurements that only a phone can make: **the face's frame budget inside a PiP
window**, **`FLAG_SECURE` behaviour there**, and **Android's own PiP chrome**,
which Jarvis does not control and cannot restyle. They stay marked unverified
rather than guessed at.
