# Audit 08 - Persona play tests of both apps (2026-09-28)

Tree: `scratchpad/integ` (audit-integration, HEAD deaca649). Nothing in it was changed.

**How this was done**
- **Desktop:** the real windows (`onboarding.html`, `index.html` = the Jarvis bar, `settings.html`, `brain.html`, `faces.html`, `widget.html`, `floating.html`) ran in Chromium through Playwright. The Tauri bridge and backend were the mocks in `jarvis-desktop/tests/uikit.mjs`, fed with the recorded backend answers in `tests/fixtures/*.json`. Driver scripts are in `scratchpad/pt/drv/d1.mjs` to `d8.mjs` (outside the repo). Screenshots are `reports/shots/08-*.png`. None of the drivers logged a page error, apart from `jarvis_hud.html`, which calls the backend directly, so the mock cannot serve it (expected).
- **Phone:** there is no Android build here, so I read the Compose screens and followed each tap in code.
- **The real AI model was never used.** A mock answer only proves that the screen draws. It does not prove that Jarvis answers.

Labels: **seen in the browser** / **checked in code** / **needs a real try on device**.

---

## Top findings (fix list)

| # | Severity | Finding | Where | Label |
|---|---|---|---|---|
| F1 | medium | Choosing a face on the PC takes 85 Tab presses to reach the first face. "Use this face" does not save anything. The page is written for developers. | `faces.html` (animal-mascot branch) | seen in the browser |
| F2 | medium | Phone pairing is still "read a long token off the PC and type it in". There is no QR code, no short code and no approval card on the PC. | Settings > Connection, `PairingScreen.kt` | checked in code |
| F3 | medium | Every button on the phone has no visible focus or press sign, so keyboard and Switch Access users cannot see where they are. With "reduce motion" on, a tap gives no feedback at all. | `ui/parts/Parts.kt:85-110` | checked in code, needs a real try on device |
| F4 | low-medium | The first-run tour says clicking the tray icon opens the other windows and Quit. A left click actually opens the Jarvis bar. The bar itself says "right-click". | `onboarding.html:163` vs `tray.rs:1393-1407` | checked in code |
| F5 | low-medium | The Voice settings show a beginner file paths, package names and model names. | Settings > Voice | seen in the browser |
| F6 | low | An alarm heard late can still ring as if it were happening now, if the phone cannot read the job back from the PC. | `JarvisRuntime.kt:4214-4238` | checked in code, needs a real try on device |
| F7 | low | The same privacy switch has a different name in each app. | Security screens | seen in the browser + checked in code |
| F8 | low | The email card's body is the thing you must scroll before Approve unlocks. It has no name or role, and it only gets keyboard focus because Chromium adds that automatically. | `index.html:555` | seen in the browser |
| F9 | low | Wording and ordering friction (Work tab order, repeated sentences, jargon on the Brain's Model tab). | see persona 3 and persona 6 | seen in the browser |

---

## Persona 1 - First-day beginner

**Steps:** first launch tour (3 screens), then the Jarvis bar, then Settings > Connection ("Show the token for my phone"), then Appearance > Open Faces, then pick a face. On the phone: first launch, then Pairing, then Appearance.

**What they saw:** `08-p1-onboarding-1/2/3.png`, `08-p1-quickbar.png`, `08-set-connection.png`, `08-p1-pairing-shown.png`, `08-set-appearance-card.png`, `08-p1-faces.png`, `08-p1-faces-grid.png`, `08-p1-faces-solo.png`.

**Good:** the tour is short and plain. Screen 2 names the approval card and shows 3 things Jarvis already answers. The empty Jarvis bar lists examples. The token display has spaces for reading and no Copy button, and it says why.

**F4 - the tour's tray instruction is wrong (low-medium, checked in code; code is pre-existing on main).**
- `onboarding.html:163`: "Click it any time to open Jarvis's other windows, or to quit."
- `tray.rs:391` sets `.show_menu_on_left_click(false)`, and `tray.rs:1393-1407` sends a left click to `windows::show_quickbar`.
- The Jarvis bar's own footer (`sayable.js:40`) says "More: right-click the Jarvis icon by the clock."
- So a beginner who follows the tour clicks, gets the Jarvis bar, and never finds Settings or Brain.
- **Fix (code):** change the line to "Click it to open the Jarvis bar. Right-click it for Settings, the Brain, and Quit."

**F2 - pairing the phone is the hardest step for a beginner (medium, checked in code).** This is designed but not built.
- The owner decided (2026-09-24) on "Phone pairing by QR code, with a short typed code as the backup, confirmed by an approval card on the PC", to be built with per-device keys ("more devices").
- In this tree there is no QR code or short code anywhere. `grep -i "qr"` finds only the face shaders. Today's path is:
  1. On the PC, in Connection, type the PC's **100.x number** into "Let my phone reach this".
  2. Turn on "Let Jarvis Desktop start and stop Jarvis". It is hidden under **More options**, near the bottom of Settings. `settings.html:176-180` says "It works only when this app starts Jarvis for you".
  3. On the phone, type the PC's **name** (`.ts.net` / `.nord`), not the number (`PairingScreen.kt:207-212`).
  4. Read the token off the PC and type it by hand. `PairingScreen.kt:120` notes the token is 43 characters.
- Four steps in three places, with "number here, name there", is where a first-day user gets stuck. No approval card appears on the PC when a phone pairs, because pairing is not a gated action today.
- **Owner's call:** confirm that QR pairing still waits for "more devices". Until then, a small code change could help: put the four steps as a numbered list at the top of Connection.

**F1 - choosing a face on the PC (medium, seen in the browser; animal-mascot branch).**
- Settings > Appearance ends with "Open Faces". That page (`faces.html:120-122`) opens with "20 faces · 50 colours · 12 patterns · one spec, two renderers". The intro text reads: "Android is Compose and the desktop is a webview, so they cannot share drawing code — what they share is the **data** at the bottom of this page."
  - The page actually shows **24** faces (d4 listed 24 cards, the four animals last).
  - Each card's tag says "2d", "3d" or "sub-stepped".
  - The page ends with "Portable output: spec.json / Kotlin / TypeScript".
- **Keyboard:** it took **85 Tab presses** to reach the first face card. Before it come 8 state chips, 12 patterns, 50 colour swatches, quality, frame-rate and speed controls, and Randomise / Reset all / Save. There is no skip link. Arrow keys do work between cards once you get there (d4: "after ArrowRight: Orbit face").
- **Saving:** Enter on a card opens it full screen with focus on "Use this face". Pressing it changes the button to "✓ In use", but **no bridge call is made** (d4: `calls: []`). `faces.html:6862-6875` only sets `SOLO_FACE` and tells you "close, then press save". Save is a small chip next to **Reset all** and **Randomise**, above the grid (`faces.html:147-150`). One wrong click resets every colour, and after Save that reset reaches the phone too.
- **The phone does the same task in one tap.** Appearance > a face chip, applied at once with an Undo bar and sent to the PC (`AppearanceScreen.kt:330-350`, `FaceChip` with `Role.RadioButton` at `:1241-1254`). Different behaviour for the same task.
- **Fix (code, small):**
  - Make "Use this face" save straight away (call `saveAppearance()` after `syncFaceChoice()`).
  - Put the face grid first, with the palette and pattern editor below it or behind a "Customise colours" disclosure.
  - Fix the "20 faces" count, and move the developer text and "Portable output" behind a "For developers" fold.

**Also noticed (low):**
- The tour never mentions the phone or the face, so a beginner leaves it with no pointer to Settings > Connection.
- Status lines in Settings (for example "Not shared yet: Jarvis could not be asked") are set in a monospace font, which reads as an error log (`08-set-appearance-card.png`).

## Persona 2 - Privacy-cautious user

**Steps:** Brain > Memory ("Saved automatically"), Forget, "Erase the words", Settings > What asks first, Lockdown on, App lock, "hide lists". On the phone: the same, plus phone notifications.

**What they saw:** `08-brain-tab-memory.png`, `08-p2-saved-automatically.png`, `08-set-asks-first.png`, `08-p2-asksfirst-lockdown-on.png`, `08-p2-quickbar-lockdown.png`, `08-p2-security-applock.png`, `08-p2-widget-applock-approval.png`.

**Good:**
- Forget asks "Stop recalling this? … This cannot be undone." Erase asks first, then separately offers "Also delete the chat…", with the wording fixed after the last play test (d7 captured both dialogs).
- The widget under App lock shows only "Jarvis wants to send an email" and "Approve in the Jarvis bar", with Deny still working.
- The Lockdown strip in the Jarvis bar says exactly where to turn it off.
- Lockdown can also be said ("lockdown", `jarvis_quick.py:1585-1597`).
- On the phone, reading notifications is off by default, and the notification-access permission is explained (`PhoneNotificationsPlate.kt:98-176`).

**Friction:**
- **"What asks first" is 78 rows long** (d5 counted 78 "- Asks you first / Does it without asking / Never" rows). It is about 6,000 px tall. The jump list at the top of Settings (`settings.html:51-`) reaches it, and the rows are grouped, but there is no search box or "only show what does NOT ask" filter. A cautious user who wants to find what runs without asking has to read all of it. Low. **Code idea:** a "Show only what does not ask" toggle.
- **F7 (low):** the same switch is called "**Windows Hello for memory lists and chat history**" on the PC (Settings > Security, `08-p2-security-applock.png`) and "**Hide memory lists and chat history**" on the phone (`SecurityScreen.kt:159`). CLAUDE.md uses the phone's name. **Fix (code):** use one name in both apps, or add the phone's name as the PC's first words.
- Known already, repeated only for context: the Brain > Memory "Note: extraction is a scaffold: review its proposals…" line shows developer text to the owner. It came from the backend (`memory-safety.patch`) and was already flagged in `STUDIO-REVIEW-2026-09-27.md`.

## Persona 3 - Busy professional

**Steps:** Brain > Work (Today cards, briefing parts, Coming up with a timer and a reminder, Goals, Morning briefing), an email-send card in the Jarvis bar and on the widget, "tell me when".

**What they saw:** `08-brain-tab-work.png`, `08-p3-work-today.png`, `08-p3-work-coming-up.png`, `08-p3-work-briefing.png`, `08-p3-work-focus.png`, `08-p3-work-chatbot.png`, `08-p3-work-widgets.png`, `08-p3-quickbar-email-card.png`, `08-p3-widget-email-card.png`. The full Work text is in `pt/work.txt`.

**Good:**
- The email card shows From/To/Cc/Subject and every character of the body, not formatted.
- Approve stays locked until the card has been scrolled and 2 seconds have passed, and the card says so.
- Today shows today's cards plus the briefing's weather, calendar and email, and never news.
- Goals shows the steps with rough dates.

**Friction (F9, low):**
- The Work tab's order is Focus session, Today, Widgets, Talk to a chatbot, **Coming up**, Goals, Morning briefing, Background jobs, and so on. Timers and reminders, the most-used part, sit 5th, below the chatbot form. **Code idea:** move Coming up to directly after Today.
- The briefing appears twice on the same tab ("From your briefing" inside Today, and the Morning briefing section). That is harmless but long.
- The mock email body contained Markdown (`**See you there.**`, `[the menu](https://…)`), shown raw on the card as designed. If the real model writes Markdown into emails, that is what gets sent. **Needs a real try with the real model.**

Phone and desktop agree on the words; `today.mjs` already checks them word for word.

## Persona 4 - Hands-free cook

**Steps:** Jarvis bar > Live; Settings > Voice ("Hey Jarvis", hands-free trust, talk-to-type, voice check).

**What they saw:** `08-p4-live-click.png`, `08-set-voice.png`.

**Browser limit:** clicking **Live** sends `live_start`, but the mock does not answer it, so nothing visible changed (d6). I could not judge the Live screen from the browser; `tests/jarvis-live.mjs` covers it with fixtures.

**F5 (low-medium, seen in the browser):** Settings > Voice is about 3,200 px of settings, with around 20 sub-headings. A beginner sees text like:
- "microWakeWord … the pymicro-wakeword package is not installed in the Python that runs Jarvis"
- "looked for ~/.openjarvis/voice-models/speaker/resnet221.onnx"
- "NVIDIA's TitaNet"
- "Speech detector (Silero VAD) … (looked for ~/.openjarvis/voice-models/vad/silero_vad.onnx)"

These come from `voice-training.js:536` and `voice-settings.js:334`. On the mocked "phone_trained" PC, the top of the section also says spoken commands are refused until a voice-ID model is installed from `backend/README.md`. So on a fresh PC, voice is a dead end without a terminal step (there is an "Open the README at that step" link).
- **Code idea:** keep the file paths and package names behind a "Technical detail" fold, the pattern Connection already uses.
- **Owner's call:** whether the voice-ID install belongs in `apply-patches.ps1`, so that step goes away.

Talk-to-type explains its key (Alt+Shift+T) and that it cannot share the microphone with "hey Jarvis" listening (`voice-training.js:493-498`). Talk-to-type versus Jarvis Live on the microphone is already on the known list, so I did not re-test it.

## Persona 5 - Keyboard-only / screen-reader user

**Desktop, seen in the browser:**
- **Jarvis bar with a card waiting** (d2, `08-p5-quickbar-approval.png`, `08-p5-quickbar-tab7.png`). The Tab order is: mic, "hey Jarvis", Live, temporary chat, pin, note box, Send note, Deny, Approve. Each has a name (from `title` or `aria-label`) and a visible focus ring. Deny comes before Approve, which is good. After Approve, focus goes to `<body>` and then the prompt box. The prompt showed no outline ring when focused; it is the page's main text box with a caret, so this is acceptable.
- **F8 (low):** on the email card, Approve stays disabled until the body (`#approval-preview`, `index.html:555`) is scrolled. With the keyboard, Tab lands on that div and End unlocks Approve (d8: "approve disabled after End … : false"). That works only because Chromium makes scroll boxes focusable by itself. The div has no `tabindex`, no role and no name, so a screen reader announces an unnamed group. **Fix (code):** `<div … id="approval-preview" tabindex="0" role="region" aria-label="The whole card - scroll to read it">`. Needs a real try on the Windows WebView2.
- **Faces picker:** see F1 (85 Tab presses). The cards themselves are good: `role="button"`, `aria-label="<name> face"`, arrow keys move between them, Escape returns focus to the card.
- Brain and Settings: no control without an accessible name (d2/d3; the Settings hits were buttons inside closed `<details>`, a false alarm).

**Phone, checked in code:**
- **F3 (medium):** every tappable in the app uses `Modifier.pressable` (`ui/parts/Parts.kt:85-110`), which calls `clickable(indication = null, …)`. A comment above it says this replaces Material's ripple with a small scale spring. So:
  - with a hardware keyboard, D-pad or Switch Access, the focused control draws no highlight;
  - with "reduce motion" on, the spring is switched off (`if (pressed && !motion.reduced)`), so a tap has no visible feedback at all.
  - TalkBack still reads roles and names: `Role.Button` is the default, and face and theme chips use `Role.RadioButton` plus `selected`.
  - **Fix (code):** give `pressable` a focus indication, for example a 2 dp outline in `chrome.textMid` while `interaction.collectIsFocusedAsState()` is true.
  - **Needs a real try on device** with a Bluetooth keyboard or Switch Access.
- Only one `contentDescription = null` exists under `ui/`. The icon-only nav toggle is named ("Navigation", Shown/Hidden, `HomeScreen.kt:1407-1419`). The nav row is **hidden by default** (`HomeScreen.kt:1441` comment, `:1492` "which is hidden by default"), so a TalkBack user must find that small chevron to reach Brain, Inbox, Live, Appearance and Help.

## Persona 6 - Tinkerer

**Steps:** Brain > Model (switch or install a model), Settings > Hardware / Second graphics card (third card), Faces quality and fps, voice follows the face, chatbot compare, model tryouts, widgets, projects.

**What they saw:** `08-p6-brain-model.png`, `08-set-hardware.png`, `08-set-second-card.png`, `08-p3-work-chatbot.png`, `08-p3-work-widgets.png`, `08-brain-tab-projects.png`.

**Good:**
- Model: active, installed, "Use", "Roll back to …" and "Install" are all there. The Install box says nothing downloads until the card is approved, which matches the 2026-09-20 decision.
- The chatbot form says "These words will be sent to the chatbot exactly as you type them" and "Nothing is sent until you approve the card". "Ask several and compare" is on both apps (`ChatbotPlate.kt` has 45 mentions of compare).

**Friction (F9, low):**
- On the second-card screen, the sentence "Needs a capable second graphics card: only one graphics card found (the NVIDIA GeForce RTX 2080 SUPER)." is repeated under **six** switches, after a banner that already says it. The "Third graphics card" block stays hidden with one card, as it should.
- Brain > Model > Skills: "Quarantined skills are not listed — the scanner withholds them on the server. There is no route that installs one, because installing runs the scanner and the gate inside the module." This is developer wording on a tab that is not under Advanced.
- **Model tryouts have no screen in either app.** Commit `215cee49` says "Tools only": `tools/model_tryout/*.py` and PowerShell only. That is fine by design, but a tinkerer looking in the app finds nothing. **Owner's call:** add one line to Brain > Model saying where the tryout command is.
- **Voice follows the face:** the known default problem is not repeated here. Both apps show it (`CustomVoices.kt:73`; Settings > Jarvis's voice > "Each animal's voice").
- Face quality and frame rate appear in two places on the PC: the Faces page deck, and Settings > Appearance > "Face on this computer". Both use the same words (`face-pace.mjs` checks this).

## Persona 7 - Phone-only user away from home

**Steps:** a server address on Tailscale or Meshnet; PC off or stale; alarms heard late.

**What they saw:** `08-p7-quickbar-stale-card.png`, `08-p7-connection-ngrok.png`. The mock's `set_api_settings` accepted a public address. The real refusal is in Rust, is checked by `own-network.mjs`, and was not re-tested.

**Good:**
- With a stale link the Jarvis bar says "Catching up… Nothing can be approved until it has.", offers Reconnect, and **Approve is disabled** (d6: `stale approve disabled: true`).
- On the phone, the status line says "Offline" or "Catching up…", hides last-known model and lane facts, offers Retry, and greys every act and mark while stale (`HomeScreen.kt:1105-1108, 1257-1296, 1393`).
- The phone's address rule (names ending `.ts.net` / `.nord` only) is explained in the pairing hint and in the FAQ (`FaqScreen.kt:61-72`).

**Worth knowing (checked in code):**
- The phone has **no timer of its own**. Nothing on the phone schedules an alarm with Android (no `AlarmManager` / `setAlarmClock` in `jarvis-client`). With the PC off or asleep, a reminder does not ring on the phone at all. The fix already built is "Also on my phone" (`Schedule.kt:24-25`), which hands a job to the phone's Clock or calendar app by the owner's tap. The Coming up text says "They go off on both apps while they are connected", which is honest, but it is easy to miss. **Owner's call:** say it louder on the phone ("Your PC must be on for this to ring - tap Also on my phone to be sure").
- The phone's "home network" handling is **documented as one-sided**. The owner's 2026-09-27 answer allowed home-network addresses on the phone, but `network_security_config.xml` leaves `.local` / `.lan` off on purpose, with written reasons (the PC does not listen there; multicast name lookup on a café's Wi-Fi). The FAQ and the pairing hint say so. This is not a bug, but the owner should know the decision was narrowed.

**F6 (low, checked in code, needs a real try on device):** the "at most 10 minutes late" rule depends on reading the job back from the PC.
- `JarvisRuntime.kt:4214-4238`: `api.scheduleJob(id)` is called. If that read fails, `job` is `null`, so `Schedule.heardLate(job?.firedAt, …)` returns false (`Schedule.kt:806-807` needs a non-null `firedAt`). The notification then **rings as if it were happening now**, however late.
- The PC deletes a fired job after 24 hours (`jarvis_schedule.py:162` `FIRED_KEEP = 24 * 3600.0`, and `:1575-1576`). So a phone out of reach for a day, which then gets the event replayed, cannot read the job and rings.
- **Fix (code):** when the read fails, fall back to the event's own timestamp, or treat an unreadable job as late (`quiet = job == null || late`). Also check the desktop's `schedule.rs:912` for the same case.

---

## Where the two apps behave differently for the same task

| Task | PC | Phone | Written down? |
|---|---|---|---|
| Pick a face | Faces page: find the card (85 Tab presses), Use this face, Close, Save | one tap, applies at once with Undo | No. F1 proposes matching the phone |
| "Also delete the chat" on Erase | second `confirm()` dialog | a checkbox on the dialog | Yes (`auto-learn.js:216-226`) |
| Hide memory lists | "Windows Hello for memory lists and chat history" | "Hide memory lists and chat history" | No. F7 |
| Server address | any own-network address (home network allowed) | `.ts.net` / `.nord` names only | Yes (`network_security_config.xml`, ARCHITECTURE §2) |
| Turning Lockdown off | PC only, with a card and Windows Hello | the phone says "only on the PC" | Yes (owner's rule) |
| Reading phone notifications | none (setting lives on the PC) | the whole feature | Yes (ARCHITECTURE §8; `check_parity.py` clean) |

`tools/check_parity.py`: "No undecided drift". There is 1 route still to port (`/api/retrieve`, already listed).
