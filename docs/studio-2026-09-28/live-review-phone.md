# Jarvis Live on the phone: play-test (studio, 2026-09-28)

Code walk-through of `jarvis-client` at merge deff2f5a - not a device test
(no Android build or emulator in the container). "Sure" = code path read end
to end; "Likely" = depends on real Android behaviour. `LiveRules.kt` and
`LiveRulesTest.kt` were compiled with kotlinc and pass (11 tests); no Live
Compose code looked uncompilable (CI has the final word). Parity: clean.

## Worst three

1. **The Live screen keeps the phone awake and unlocked forever, even after
   Live ends.** `LiveScreen.kt:98-102` sets `keepScreenOn = true` while the
   screen is open, Live on or not: the phone never auto-locks, App lock never
   re-locks, the last answer stays visible, the battery drains. (Sure.) Fix:
   `DisposableEffect(view, on) { view.keepScreenOn = on; onDispose { view.keepScreenOn = false } }`.
2. **"Hey Jarvis" to the phone while Live runs on the PC gets total
   silence.** `live_elsewhere` is only stored (`JarvisRuntime.kt:3777`) and
   shown on the Live screen (`LiveScreen.kt:176-183`); never spoken or
   notified; never expires (`_liveMove` cleared only on a successful start,
   `:3658`). Fix: speak "Live is on your PC.", a heads-up notification with
   "Move it here", clear after 30 s, say "PC" not "desktop".
3. **Live ends without a word for almost every reason.** Only the quiet end
   and "that's all" speak; time up, App lock, Stop everything, Standby and
   "moved" just stop the mic (`JarvisRuntime.kt:3849-3853, 3858-3861`). With
   App lock's 1-minute default (`Security.kt:62`), a pocketed phone ends Live
   silently. The "Two minutes left" warning is skipped if Jarvis is talking
   (`VoiceSession.kt:675`). No end tone. Fix: one fixed ending line per
   reason from `ended_words`; retry the warning after speech; the end tone;
   tell the owner on the Live screen that App lock ends Live after "Lock
   again after".

## Broken

- **B1 End from the notification can be lost** (`LiveService.kt:106-110`
  launches `liveStop` in the service scope, then `stopSelf()`; `onDestroy`
  `:132-135` cancels it; `endLiveHere` never cancels `liveWatch`,
  `JarvisRuntime.kt:3810-3814`). Fix: stop in the runtime scope, cancel
  `liveWatch`, mark ended locally at once. (Likely - a race.)
- **B2 End on a bad link leaves the screen claiming Live is on**
  (`JarvisRuntime.kt:3670-3680`), and the `busy` guard blocks End for up to
  20 s (`LiveScreen.kt:108-115, 159`). Fix: End skips `busy`, ends locally,
  retries the stop in the background. (Sure.)
- **B3 After a link drop, Live can look on while nobody listens** (watcher
  quits after 10 failed reads, `:3845-3848`; nothing restarts listening on
  recovery, `:1225`, `LiveScreen.kt:89`). Fix: on recovery with Live on
  here, restart listening and say "I'm back." (Sure.)
- **B4 Typing or tapping in Live does not count as activity** - only spoken
  clips (`note_owner`) and Jarvis's voice (`note_spoke`) reset the quiet
  clock (`backend/jarvis_live.py:889, 949, 813-816`), so 90 s of typing ends
  Live. Fix: a `{"do":"active"}` POST or the chat route touching the
  session. (Sure.)
- **B5 Tap buttons make nonsense choices** from `LiveRules.chips`
  (`LiveRules.kt:278-305`, shared with the desktop): "Which do you prefer,
  Italian or Thai?" -> [Prefer, Italian, Thai]; "Which one, the red or the
  blue?" -> [Which one, The red, The blue]; "Shall I read it out, or keep
  it on screen?" -> [I read it out, ...]; "Is that everything, or is there
  more?" -> [Is that everything, Is there more]. Fix: with a comma, take
  choices only after the last comma; add these to `tools/gen_live_cases.py`.
- **B6 A call that starts while Jarvis talks is not noticed until Jarvis
  finishes** (`LiveService.kt:173`, `LiveRules.kt:371`; audio focus has no
  listener, `Speaker.kt:485-499`). Fix: on focus loss, stop speech and mute
  Live. (Likely.)
- **B7 "Hey Jarvis, let's talk" from the pocket can say "I'm listening." and
  not listen** (`JarvisRuntime.kt:3762-3766`; Android 14 refuses a mic
  service from the background, `LiveService.kt:430-432`). Fix: speak only
  once the service is in the foreground; else stop and say "Open Jarvis to
  start Live." (Likely on 14+.)
- **B8 Tap buttons never appear if any old card waits** (`cardShown` counts
  every card, `JarvisRuntime.kt:600`; the PC only counts this session's).

## Confusing

- **C1** Live is hard to find: only the fifth, hidden item in Home's nav row
  (`HomeScreen.kt:647-648, 1369-1374`); no app-icon shortcut
  (`res/xml/shortcuts.xml`) though the design promised one.
- **C2** No Live sign on Home; the Home talk button still works during Live
  (two recorders). Fix: a Home strip "Jarvis Live · 24 min · End · Open";
  the talk button goes to Live while on.
- **C3** Opening Live while it runs on the PC shows plain "Start Jarvis
  Live" (`LiveRules.kt:155`); Start silently moves it. Show "Live is on your
  PC" + "Move it here".
- **C4** Captions show the Home chat's last Q/A before Live starts
  (`LiveScreen.kt:192`); Live continues whatever chat was open, so "one Live
  session is one chat" is not true on either app.
- **C5** Untrained-voice refusal says "Settings -> Voice check"
  (`jarvis_live.py:278`), but the phone trains in "Train my voice"
  (`SettingsScreen.kt:174-183`); no button from Live.
- **C6** "Mute" is ambiguous (closes the mic, does not quiet Jarvis) - "Mute
  mic", "End Live" (TalkBack label just "End"). Desktop too.
- **C7** "Show the card" does `nav.resetTo(HOME)` (`MainActivity.kt:1901`) -
  use `nav.go(HOME)`; show it only for `card`, not `cards_unknown`.
- **C8** Errors show class names (`LiveService.kt:122, 430, 470`), linger
  (`_liveNotice` cleared only on start), "(409)" (`JarvisRuntime.kt:3711`),
  and an old tap result stays forever (`LiveScreen.kt:184`).
- **C9** "Heard you - thinking" stays 6 s (`JarvisRuntime.kt:3872`) though
  answers start in 2-4 s; clear it on first sound (desktop the same).
- **C10** Voice check layout: the phone-only interrupt setting appears only
  after the PC answers (`VoiceCheckScreen.kt:286, 380`); the "stricter/looser"
  sentence (`:382`) sits under a setting that never asks; heading "Jarvis
  Live" (`StrictVoice.kt:208`) should say it applies with "Only trust the
  talk button"; "Hey Jarvis" missing quotes (`StrictVoice.kt:202`).
- **C11** TalkBack: sign changes not announced (no live region,
  `LiveScreen.kt:124-131`); TalkBack's own voice goes into the open mic.
- **C12** "Resume Live" goes stale: the watcher stops after an ending
  (`JarvisRuntime.kt:3853`); the desktop times the 10 minutes itself.

## Could be nicer

Subtitle "no wake word" is jargon -> "no "Hey Jarvis" needed"
(`LiveScreen.kt:118`); tap buttons in a `Row` (`:208`) -> `FlowRow`; no
`imePadding` on the root (`:117`), so the keyboard likely covers the text
box; the "no echo canceller" line from the design is not built; "Interrupt
by voice" silently does nothing when the PC's `barge_in` is off
(`VoiceSession.kt:279`); "It ended: Stop everything." reads oddly
(`LiveRules.kt:151`); no "Stop talking" notification action
(`LiveService.kt:415-416`); "20 more minutes" shows from the first second -
only in the last 5 minutes.

## Phone vs desktop mismatches

M1 the move offer (silent, never expires, "desktop" vs announced, 30 s,
"PC"); M2 phone has "20 more minutes", desktop has none; M3 unknown
`hands_free_live` shown as strictest on the phone (`VoiceStrict.kt:296-300`),
hidden on the desktop (`voice-training.js:665`); M4 screen-reader
announcements on the desktop only; M5 one visible desktop button vs a
hidden phone row; M6 "Resume Live" timing. The words themselves match (the
shared table proves it).

## Phone ideas (all 0 GB, either card setup, rules kept)

A Quick Settings tile; an app-icon shortcut (promised by the design); a
"Live ended - Resume" notification for 10 minutes; headset button (press =
stop talking, long press = mute, never approves); prefer a Bluetooth headset
mic in Live; a dim "pocket" mode; share sheet "Talk about this in Live"
(shared text marked outside text).
