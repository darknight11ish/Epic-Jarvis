# Audit 1 (bugs), Android half + audit 9 (optimization), Android part

Tree: `scratchpad/integ`, HEAD deaca649, scope `git diff 9cdb0567..HEAD -- jarvis-client` (about 115 main Kotlin/XML files, about 20k added lines).
Paths below are relative to `jarvis-client/app/src/main/java/com/jarvis/client/` unless they start with `jarvis-client/`.

How I worked: I read the code by hand, because nothing can build Android here. I read these parts in full: the notification-reading feature (listener, redactor, allow list, store, plate), LiveService with its JarvisRuntime watcher, the board widgets and Quick Settings tiles, CritterFaces and FaceView's frame loop, pairing, FLAG_SECURE, the request header code and NetworkWatch. I sampled the rest. I did not read every line of the 20k. The biggest gaps are ChatbotPlate, ProjectsPlate, GoalsPlate, ForgetRangePlate and the pose files. I checked the pose files only for how they are used.

## Compile status (read this first)

- **Each branch compiled on its own.** GitHub Actions shows the last "Jarvis client" and "CI" runs green on the tips that were merged: 4c5ce8d1 (3D animals), be393fe8 (research), 1a980b78/61be06a7 (competitors). I did not find a run for 4644cb9f (continuation) in the first 40 runs.
- **The combined tree has never been compiled.** The merge report (05-merge.md) says the hand-merged Kotlin files were JarvisRuntime, MainActivity, Schedule.kt `tag()`, HomeScreen, VoiceStrict/StrictVoice and BrainScreen. I checked these and found no problems:
  - no conflict markers are left;
  - no top-level name is declared twice in any package;
  - `Screen` has a new entry `LIVE`, and the `when (screen)` in `MainActivity.kt:1494` covers all 13 entries;
  - `Schedule.tag()` has one arm each for goal_checkin, NEXT_TIME and TODAY_CARD;
  - the `isLoosening(..., current)` merge in `net/VoiceStrict.kt` is consistent;
  - JarvisRuntime has two `cancelHold` functions, but they take different parameter types (`UndoEntry` and `String`), so they are legal overloads.
- A script compared the named arguments at each call site with the screen function signatures. Its only hits were false alarms caused by lambdas in the arguments, and I checked each one by hand.
- **Still unverified:** whether the combined tree compiles. Only CI can tell. Push the integration branch to a scratch branch and let "Jarvis client" run before trusting it.

---

## Findings

### A1. High: one-time codes get past the redactor in common message shapes
Checked in code. Branch: continuation-03kls1.

**What's wrong:** The code check looks at the title and the text separately, and its trigger-word list is narrow. So a code in the text is kept whenever the trigger word is only in the title, or when the message uses words like "PIN", "log in" or "sign in".

**Evidence:**
- `data/NotificationRedactor.kt:203`: `if (!TRIGGER.containsMatchIn(text) && !isBareCode(text)) return text`
- `:208`: `fun redactBoth(title, text) = redact(title) to redact(text)`
- The trigger list (`:184-187`) has no "pin", no "login" on its own (only "login code"), no "sign in" and no "log in".
- I ran the same regexes in Python. All five of these came back unredacted:
  - title "Verification code", text "Use 482913 to sign in"
  - "482-913 is your WhatsApp PIN"
  - "Your PIN is 4829"
  - "Enter 482913 to log in to Uber"
  - "482 913 is your Instagram login"
- The class comment (`:148-150`) says the NNN NNN grouping is caught "with or without a trigger word". The code only does that when the grouping is the whole text.
- The existing test (`NotificationRedactorTest.kt:122`) puts "code" in both strings, so it never tests the split case.

**Why it matters:** The owner decided that one-time codes are hidden before anything reaches the model. The captured text is stored and can be attached to a chat.

**Fix (code change):**
1. Decide on the trigger once, from `title + " " + text`, and redact both strings if it matches.
2. Add `\bpin\b`, `log ?in`, `sign[- ]?in`, `login`, `password` and `2-step` to the trigger list.
3. Always mask `\b\d{3}[- ]\d{3}\b`, trigger word or not.
4. Add tests for the five shapes above.

### A2. Medium: the notification switch on the phone goes out of step with the PC
Checked in code. Branch: continuation.

**What's wrong:** The listener only reads a cached copy of the switch, and that copy is only refreshed while the notifications plate is open on screen.

**Evidence:**
- `JarvisRuntime.phoneNotificationsSettings()` (`JarvisRuntime.kt:3561`) is the only place that refreshes the cache. Its only caller is `ui/screens/PhoneNotificationsPlate.kt:75`.
- `setPhoneNotifications` (`:3574-3585`) updates the cache only on `Outcome.Done`. Turning it ON returns `Waiting` while the approval card is pending.
- The plate reads again when the card leaves the queue (`:69-73`), but only if the plate is on screen at that moment.

**Why it matters:**
- (a) The owner taps ON, walks to the PC and approves. Nothing is ever captured until they reopen the plate, and nothing tells them.
- (b) The listener is bound by the system, and JarvisRuntime is never initialised in that process until another component starts. Its check `phoneNotificationsAllowed()` (`:3545`) returns false when `settings` is not ready. So a cold process that only the listener started captures nothing. Both effects fail in the safe direction, but the feature silently does nothing.

**Fix (code change):**
- Re-read `/api/notifications/phone` when the phone connects (`refreshAll`), and whenever a phone-notifications card leaves `_pending`.
- In `PhoneNotificationListenerService.onListenerConnected()`, call `JarvisRuntime.initialize(this)`.

### A3. Medium: captured notifications stay on the phone after the switch is off or an app is removed, and there is no delete button
Checked in code. Branch: continuation.

**Evidence:**
- `CapturedNotifications.clear()` (`data/CapturedNotifications.kt:350`) has no caller in the whole app (checked with grep).
- `NotificationAllowListStore.remove()` (`:232`) takes the app off the list but leaves its stored rows.
- `sharedText()` attaches rows from any app, including removed ones. Rows are kept for up to 7 days and at most 200 (`:429-432`).
- The Attach button is hidden while the switch is off (`MainActivity.kt:2300-2303`), but the text is still stored in plain SharedPreferences.

**Why it matters:**
- Turning the feature off is supposed to take effect at once. Today capture stops, but the stored copies stay on the phone for up to a week.
- Removing an app does not remove what was already captured from it.

**Fix (code change):**
- Call `clear()` when the switch reads as off.
- Filter out a removed package's rows in `remove()`.
- Add a "Delete captured notifications" button to the plate. This matches the Forget pattern used elsewhere.

### A4. Medium: turning on App lock or "Hide memory lists" does not hide the home-screen "Jarvis widget" text right away
Checked in code. Branch: audit-competitors-vyqpt1.

**Evidence:**
- `widget/JarvisBoardWidget.kt:92` hides the words when `security.appLock || security.privateLists`. But only a redraw applies that.
- The redraw trigger at `JarvisRuntime.kt:814-817` is `combine(_link, _stale, _scheduleTick, _widgetsTick, settings.homeWidgets)`. It does not include `settings.security`.
- `widget_board_info.xml` has `updatePeriodMillis="1800000"`.

**Why it matters:** After the owner switches on the privacy setting, whatever the widget showed (reminders, counts, items) stays on the home screen for up to 30 minutes, or until the link changes.

**Fix (code change):** Add `settings.security` to that `combine`, as a sixth flow.

### A5. Medium: Jarvis Live on the phone may stop by itself while the screen is off (needs a real try on a device)
Checked in code. Branch: research-ff37vy.

**Evidence:**
- `service/LiveService.kt:390-401` `refreshNotification` calls `goForeground(sign)` every time the sign or the talking state changes. `goForeground` calls `ServiceCompat.startForeground(..., FOREGROUND_SERVICE_TYPE_MICROPHONE)` again (`:453`).
- The catch at `:461-471` sets `running = false`. That ends the listening loop and shows "Android did not let Jarvis Live listen from the background".
- What I have not verified: I recall that Android 12+ re-checks the app's state on the second and later `startForeground` calls, and that Android 14 refuses the microphone type when the app is in the background. I did not check this against the AOSP source, so it needs a device.
- If it holds, the first sign change with the screen off ends Live. Examples: Jarvis starts talking, which adds the "Stop talking" button, or the link goes stale.

**Fix (code change, low risk either way):** After the first `startForeground`, update the notification with `NotificationManager.notify(NOTIFICATION_ID, notification)` instead of calling `startForeground` again.

### A6. Low: LiveService can start the microphone after Android has refused the foreground service
Checked in code; needs a device.

**Evidence:** `onCreate` calls `if (!goForeground(...)) stopSelf()` (`:102`). `onStartCommand` still runs afterwards, sets `running = true` and launches `listen()` (`:120-133`), because `loop == null`.

**Fix:** Keep a `foregroundOk` flag and return early from `onStartCommand` when it is false.

### A7. Low: the "Attach recent notifications" button can be out of date
Checked in code.

**Evidence:** `MainActivity.kt:2300`: `remember(tick) { phoneNotificationsAllowed() && CapturedNotifications(...).sharedText() != null }`. Here `tick` is `permissionTick` (`:684`), which almost never changes. So the button does not appear after the first notification is captured, or after the switch turns on. It also reads and parses up to 200 JSON rows on the main thread.

**Fix:** Make it state that follows `settings.phoneNotifications`, and have the store report its row count.

### A8. Low: duplicate captured rows
Checked in code.

**Evidence:**
- A notification that is updated in place usually keeps its `postTime`. So `id = "${pkg}:${key}:${postTime}"` repeats.
- `CapturedNotifications.add` (`:339-345`) does not remove duplicates, so a chat app's updated notification is stored and attached several times.

**Fix:** In `add`, drop rows with the same `key` before adding.

### A9. Low: a notification action shows the wrong message
Checked in code.

**Evidence:** `widget/JarvisBoardWidget.kt` `BoardButtonCallback`: the `OpenBriefing` and `OpenChooser` cases show the toast `W_STALE_SUB`, which is the "link is stale" message. `OpenBriefing` cannot be reached there because Brief-me is routed before this, but the wording is wrong for `OpenChooser`.

### Checked and found fine
All checked in code.
- **FLAG_SECURE** is set while App lock, "Hide lists" or the pairing token is shown (`MainActivity.kt:746-754`). The pairing field uses the password keyboard even while the token is shown (`PairingScreen.kt:234`).
- **Headers:** every new request goes through `authed()` (`net/JarvisApi.kt:299`). That adds the token and `X-Jarvis-Client`, including the new photoCall, widgetDraftCall and briefing calls, and EventStream. No new code logs the token. The new `Log` lines only print fixed strings or exceptions.
- **Addresses:** no new code builds its own URL or talks to anything outside the owner's networks. The only BaseUrl change is a comment.
- **Manifest:**
  - The listener is `exported=false` with `BIND_NOTIFICATION_LISTENER_SERVICE`, the same shape Android's own documentation uses.
  - The tiles are exported with `BIND_QUICK_SETTINGS_TILE`.
  - The board receivers are exported for the launcher, like the existing ones.
  - LiveService declares `foregroundServiceType="microphone"`, and `FOREGROUND_SERVICE_MICROPHONE` is already declared.
  - `<queries>` covers the launcher list and SMS_DELIVER.
- **Notification rules:** the listener never replies, dismisses or acts on a notification. It blocks SMS by the phone's default-SMS app and a fixed list, and it blocks banking apps when they are added (by store category and name).
- **Tiles:** `startActivityAndCollapse(PendingIntent)` is used correctly on Android 14+, and tiles never offer Approve.
- **Hey Jarvis:** WakeWordService steps aside while Live is on (`liveOnHere()`). The "Hey Jarvis after restart" notice at boot is only a notice; the microphone is not started at boot.
- **Find my phone** does not ring when the event is more than 120 s old.
- **Animal faces:** they use `RuntimeShader` (AGSL). That is not OpenGL, so there is no GL context to lose. The frame loop is inside `repeatOnLifecycle(STARTED)` (`FaceView.kt:262`), so it stops in the background. The older GL mesh faces still pause and resume with the lifecycle (`:790-803`).

---

## Optimization (audit 9, Android)

| # | Where | What | Expected gain | Risk |
|---|---|---|---|---|
| O1 | `JarvisRuntime.kt:4771-4772`, `LIVE_WATCH_MS = 1000` (`:4844`) | While Live is on, the phone reads `/api/live` every second, even though a `"live"` event already triggers `liveRead()` (`:1364`). Rely on the event and poll every 10 s as a backup; detect a dropped link from `_stale`/`_link`, which the watcher already reads. | About 3,600 to about 360 requests per hour of Live, and fewer radio wake-ups | Low to medium (the "Two minutes left" timing must still come from the status) |
| O2 | `service/LiveService.kt:195-199`, `IDLE_MS = 200` | While the microphone is closed (muted, card shown, link stale, on a call), the loop wakes 5 times a second to re-check. Suspend on a `combine` of liveStatus, stale, pending, voice.phase and interrupt instead. The call check (audio mode) could stay on a 1 s timer. | Removes about 18,000 wake-ups per hour while muted or waiting | Medium |
| O3 | `LiveService.kt:400,453` | Same fix as A5: after the first call, update the notification with `notify()` instead of `startForeground`. | Correctness first; also cheaper | Low |
| O4 | `face/CritterFaces.kt:88` (lazy `RuntimeShader`) and `ui/screens/AppearanceScreen.kt:221` | Animal shaders are warmed only when Appearance opens. On a cold start with an animal as the face, the large shader compiles on the main thread during the first Home frame. Warm the chosen face with `Dispatchers.Default` from `JarvisApp.onCreate`, next to `GpuProbe.start()`. | Removes one long first-frame stall (not measured) | Low |
| O5 | `JarvisRuntime.kt:738-745` | The sky is read every 10 min while connected, including in the background: EventService keeps the process alive, so this is about 144 reads a day. Only poll while a face is on screen, and read once when it comes back. | Small network and battery saving | Low |
| O6 | `JarvisRuntime.kt:814-817` | Every link or stale change redraws all three board widgets, and each redraw reads the PC. Add `debounce(1s)` and skip it when no board widget is placed (`GlanceAppWidgetManager.getGlanceIds`). | Fewer requests when the link flaps | Low |
| O7 | `data/CapturedNotifications.kt:339-345` and `MainActivity.kt:2300` | Every captured notification rewrites up to 200 JSON rows, and composition parses the whole store on the main thread. Keep a small in-memory cache and write in the background. | Small | Low |
| O8 | `face/FaceView.kt:384-409` | A resting face runs a `withFrameNanos` callback on every vsync (120 Hz) to draw at 30. The comment says this is a deliberate choice against judder. I leave it as is and note it only as a known cost. | Small | Changing it brings the judder back |
| O9 | `face/CritterPose.kt`, `OwlPose.kt`, `OtterPose.kt`, `MonkeyPose.kt` (about 2,800 lines) | These are hand-written Kotlin copies of the desktop's pose code, kept honest by golden fixtures. The shaders are already generated from one source (`tools/gen_critters.py`); the poses could be generated the same way, or turned into a shared data table. | Removes a whole class of desktop/phone drift for each new animal | Medium (big mechanical change; the golden tests already guard it) |
| O10 | `JarvisBoardWidget.kt` `provideGlance` | Each placed widget reads the PC on every redraw, with no short cache. Cache for about 30 s per slot. | Small | Low |

No wake locks were added in the new code. I did not find any new `GlobalScope` or `runBlocking` in the new code.
