# Cutting-edge audit, round 2, 2026-09-26: how Jarvis fits into the day

Where Jarvis shows up on the PC and the phone outside its own windows (the taskbar, right-click
menus, notifications, the lock screen, the clipboard, widgets and tiles), plus the queued Today page
and first-run setup, and accessibility. Research only: nothing was built and nothing in the repo
changed except this file. It does not repeat the 09-25 reports, the three round-1 cutting-edge
reports or the memory research. Where one of them already has an idea (Android 16 Live Updates,
"Also on my phone", the evening wrap-up, the weekly journal), this report points to it and adds only
what is new.

## In six lines, for the owner

1. **Two small privacy fixes come first.** Today, if a smartwatch is paired, Android copies Jarvis's phone notifications to it, card titles and "tell me when" alerts included. And on Android 16, the approval widget may be allowed on the lock screen. Both can be switched off in a few lines.
2. **Copying an answer should not send it to the cloud.** Windows can copy your clipboard to your other devices through your Microsoft account. Jarvis can mark its copies "do not keep, do not sync". The phone can hide the copy's preview.
3. **A "Things you can say" list** in both apps: the commands that work without the AI model (timers, lists, focus, "what did I miss?"), one tap to use.
4. **The Today page and first-run setup now have concrete designs** (below). The first-run design reuses the live preflight check, so every setup step shows a green tick or a "Fix" button.
5. **Right-click a file → Send to → Jarvis** works on Windows 11 with no installer tricks. What arrives is always treated as outside text and never sent by itself.
6. **Not for Jarvis:** letting Gemini or Copilot call into Jarvis, a smartwatch app that syncs through Google's servers, and approving from anywhere except inside the app.

## How far to trust this

- **Read myself:** the repo files named below; Google's Android pages for Glance releases and
  notification bridging (developer.android.com was open); Microsoft's clipboard-formats page (as its
  GitHub copy, `MicrosoftDocs/win32`); arboard 3.6.1's source in the local cargo cache; Tauri issue
  #12901; a GitHub issue quoting Google's lock-screen-widget FAQ.
- **Search summaries only** (the sites were blocked here: learn.microsoft.com,
  android-developers.googleblog.com, samsung.com): Windows toast input, App Actions on Windows, the
  File Explorer context menu, FocusSessionManager, toast progress bars, PowerToys Command Palette,
  Android Modes, the lock-screen widget FAQ itself, AppFunctions, Wear OS 6, and the Today and
  journaling designs (Sunsama, Things, Now Brief, Apple Journal). These are marked **(summary)**.
  Vendor statements are marked **(claim)**.
- **Not checked at all:** anything on a real Windows PC, phone or watch. I do not know the owner's
  phone model, Android version, or whether a watch is paired. "Same as the Windows setting"
  behaviours are claims until the owner sees them.

## Ranked list

| # | Idea | Why it matters | Size | Rule risk |
|---|---|---|---|---|
| 1 | Keep private notifications on the phone; keep the approval widget off the lock screen | Stops card titles and email-sender alerts reaching a watch (and, possibly, the watch maker's servers) and a locked phone | S | Lowers it (rule 1) |
| 2 | "Private copy": copies stay out of clipboard history and cloud sync (PC) and show no preview (phone) | Copy is the one everyday button that can push an answer off the PC with nobody deciding | S | Lowers it (rule 1) |
| 3 | "Things you can say": a list of the no-model commands, in both apps | A beginner cannot guess the phrasing; these work even when the model is asleep | S-M | None |
| 4 | Today page: concrete design | Queued (creativity #10); this gives it a shape: Next, Waiting on you, Done today, This evening | M | None (reads only) |
| 5 | First-run setup = the preflight with "Fix" buttons, plus "what leaves this PC" | Queued; the checks already exist as a script, and `/api/reach` already lists every way out | M | None |
| 6 | "Send to → Jarvis" on the PC; everything the shell hands Jarvis lands in the text box, tagged as outside text | Ask about a file without opening it; one safe pattern for every future shell entry | S-M | Low (outside-text rules already cover it) |
| 7 | Focus: follow Windows' own Focus, and a Focus tile on the phone | Starting focus where the owner already is; no new watching | S | None |
| 8 | A "Jarvis focus" Do Not Disturb mode on the phone (off by default) | The phone stops buzzing during a PC focus session | S-M | Low (owner's call) |
| 9 | A countdown toast with a progress bar on the PC | Desktop version of the phone's Live Update countdown (round 1, #13) | S-M | None |
| 10 | Long-press shortcuts on the phone's app icon | Talk, Note, Brief me, What did I miss - one press from the home screen | S | None |
| 11 | "Close the day": one line in your own words into the daily note | The concrete shape of the queued evening wrap-up | S-M | None |
| 12 | Accessibility pass: Windows Contrast themes, automatic checks in both test suites, a screen-reader test of the frameless windows, 200% text | Catches what the good existing work misses | S each | None |
| 13 | Paste guard: a pasted password or code is kept out of chat history, and Jarvis says so | Passwords already always wait for a yes when saved; this stops them entering chat history | S-M | Lowers it (rule 3) |
| 14 | Glance 1.2 and a small Today widget (counts only) | Real previews in the widget picker; next thing at a glance | S-M | Low |
| 15 | Share a document from the phone to the PC | Feeds "ask my documents" (round 1, #5) from the phone | M | Low |
| 16 | Later: give the desktop a Windows "package identity" | Unlocks the modern right-click menu, the Windows Share target and reply-in-notification | L | Low, but fiddly for a beginner |

## Details

### 1. Private notifications stay on the phone; approval widget off the lock screen (S)

- **Plain words.** Android copies every app's notifications to a paired watch unless the app says
  "this one stays here". Jarvis never says that: there is no `setLocalOnly` anywhere in
  `jarvis-client` (checked by search). Separately, on Android 16 QPR2 phones, widgets are **allowed
  on the lock screen by default** and an app opts out with a new category, `not_keyguard` **(summary
  of Google's FAQ, quoted in divinevideo/divine-mobile#8370; the FAQ page itself was blocked)**.
  Jarvis's widgets declare only `android:widgetCategory="home_screen"`
  (`res/xml/widget_approval_info.xml`, `widget_quicklink_info.xml`).
- **Why it matters.** The approval notification is carefully redacted for the lock screen
  (`ApprovalNotifier.kt:278-279`, `VISIBILITY_PRIVATE` with a public version), but a watch shows the
  full version. Google says a local-only notification also stays off "other wearables and any other
  connected devices" (developer.android.com, bridging page). Some watch makers can deliver the
  phone's notifications over the internet when the watch is out of Bluetooth range **(summary;
  Samsung's page was blocked)**. That would send email senders' names and card titles through a
  company's servers: rule 1. The approval widget shows the notice text and a Deny button, so on a
  lock screen anyone holding the phone could read titles.
- **Plugs in.** `.setLocalOnly(true)` on the builders in `service/ApprovalNotifier.kt:264,322,330`
  and `service/ScheduleNotifier.kt:114` (timers, reminders, quiet "tell me when"). The ringing
  builder (`ScheduleNotifier.kt:164`) is shared by alarms and urgent "tell me when" alerts, so
  decide by kind there: an alarm may bridge if the owner wants it on a watch, an alert may not. Add
  `not_keyguard` to the approval widget for Android 16 (the summary says in a `res/xml-v36/` copy,
  so older phones still read the old file; confirm in the CI build).
- **Permission fit.** Only makes things stricter. Nothing about cards changes.

### 2. "Private copy" (S)

- **Plain words.** The Copy button under an answer puts the text on the clipboard
  (`jarvis-desktop/src/main.js:3883` → `commands.rs:4624` `write_clipboard`; phone
  `ui/screens/HomeScreen.kt:2030`). On Windows that copy can go into Win+V history and, with "Sync
  across your devices" on, to the owner's Microsoft account. The repo already knows this: the memory
  export was moved from the clipboard to a file for exactly this reason (`brain.rs:515-520`). An
  answer can hold a recalled memory or email text.
- **How.** Windows has a clipboard format, `ExcludeClipboardContentFromMonitorProcessing`, that
  keeps a copy out of history **and** cloud sync (Microsoft's clipboard-formats page, read as its
  GitHub copy). `arboard` 3.6.1, already in `Cargo.lock` under the clipboard plugin, has it as
  `SetExtWindows::exclude_from_monitoring()` (checked in its source; licence MIT OR Apache-2.0). The
  Tauri plugin does not expose it, so `write_clipboard` would call arboard directly. On the phone,
  `ClipDescription.EXTRA_IS_SENSITIVE` (Android 13+, and `minSdk` is 33) hides the copied text in
  the keyboard's preview **(Google's docs)**. Whether a phone keyboard's own cloud clipboard honours
  that flag: not checked.
- **Permission fit.** Stricter only. Say it once in plain words next to the button: "Copied. Kept
  out of Windows clipboard history and sync."

### 3. "Things you can say" (S-M)

- **Plain words.** Launchers like PowerToys Command Palette (MIT, the successor to PowerToys Run; an
  extension gallery came in v0.100 **(summary)**) and Raycast show everything you can do as a
  searchable list. Jarvis has many commands that work **without the model**
  (`backend/jarvis_quick.py`: timers, reminders, named lists, snooze, focus, "what did I miss?",
  "tell me when", "what can you reach?"), but the quickbar shows only "Ask Jarvis anything…"
  (`index.html:91`) and the phone shows no examples.
- **Design.** Type `/` in the quickbar, or tap a "?" beside the phone's text box: a short grouped
  list ("Timers and reminders", "Lists", "Focus", "Catch up"), each with one example sentence.
  Choosing one puts the sentence in the box for the owner to finish and send. Nothing is sent by the
  list itself. One shared JSON list read by both apps and by a test, like `card-words`.
- **Permission fit.** The sentence is the app's own fixed text chosen by the owner, then sent by the
  owner: count it as `typed`. Commands that raise a card still raise it.

### 4. The Today page: a concrete design (M)

Sources of the patterns: Things 3's Today with a separate **This Evening** section at the bottom
("still present, but unobtrusive") **(summary)**; Samsung Now Brief and Pixel Daily Hub's
time-of-day cards, and the reviews of Now Brief that call its generic cards filler **(summary)**;
Sunsama's "shutdown" at a chosen end-of-day time **(summary)**.

- **Four bands, top to bottom:** **Next** (the next 3 things from the scheduler); **Waiting on you**
  (how many cards wait, each by title, and "Open the card" - never an Approve on this page); **Done
  today** (a timeline in plain words: timers that went off, notes filed, facts saved, web searches
  sent, focus sessions and their report lines); **This evening** (reminders after a time the owner
  picks, greyed until then).
- **Show nothing rather than filler.** An empty band is one short line ("No reminders tonight."),
  never a suggestion card.
- **Every line says where it came from:** "Saved from what you said at 10:02", "Filed in Obsidian
  after your OK".
- **Reuse, do not rebuild:** the briefing builder already makes "went off", "approvals" and "coming
  up" sections without the model (`jarvis_briefing.build_missed`, `backend/jarvis_briefing.py:834`).
  A Today route is the same builder with "since midnight".
- **Honest gap, from JARVIS-API §22.9:** cards that expired are not listed, because the gate's own
  record lives in the owner's `jarvis_gate.py`, which this repo does not hold. The page should say
  so rather than look complete.
- **Privacy:** search words and saved facts hide with "Hide memory lists and chat history", like the
  other private lists. It is a read, so a stale link shows the last copy marked as old.

### 5. First-run setup = the preflight, with a "Fix" button per step (M)

- **Today:** three explanation screens (`jarvis-desktop/src/onboarding.html:129-188`), no checks.
  The live preflight exists only as a command (`selftest.py --preflight`, JARVIS-API §29).
- **Patterns borrowed:** Home Assistant's onboarding is five short browser steps, and its analytics
  are **off unless you opt in** during setup **(summary)**. LM Studio shows a "likely fits" badge
  per model for your hardware **(summary)**. Jarvis already has the Hardware screen for that.
- **Design:** a checklist with a tick per step, each skippable and resumable, and a "Setup: 4 of 6
  done" line in Settings until finished: *Start Jarvis* → *The model answers* → *Your voice*
  (optional) → *Pair your phone* (the decided QR code) → *Web search provider* → *What leaves this
  PC*. The last step shows `/api/reach` (JARVIS-API §24) in plain words: "Right now, nothing leaves
  this PC except: (none)". Each failed check shows its one fix button, using the plain-errors words
  (`plain-errors.js`). Ask for permissions (notifications, microphone) at first use, as the phone
  already does for the microphone.
- **Permission fit:** any step that turns something on raises its usual card.

### 6. "Send to → Jarvis" on the PC, and one rule for all shell entries (S-M)

- **Plain words.** Windows 11 still has "Send to" (under "Show more options", or Shift+right-click);
  any shortcut placed in `shell:sendto` appears there **(summary, several guides)**. The installer
  can place a "Jarvis" shortcut there that starts `jarvis.exe --shared <file>`. The running app
  already receives a second launch's command line (`src-tauri/src/lib.rs:629`,
  `tauri_plugin_single_instance`, used today for the toast Deny).
- **The rule (new, and worth writing down once):** anything that arrives from outside the app (a
  file, text from another program, a future jump-list task) **fills the text box with the provenance
  tag `shared`** and waits for the owner to press Enter. The phone's Share already works exactly
  this way ("folded into the composer draft, never sent on its own", `AndroidManifest.xml`). A
  `shared` message is outside text, so a note write after it asks first (ARCHITECTURE §3).
- **Limits.** Plain-text files work at once; PDFs and Word files need round 1's document-to-text
  step. The modern (not "more options") menu needs item 16.

### 7. Focus: follow Windows' own Focus, and a Focus tile (S)

- **Follow Windows Focus.** Windows 11 lets any desktop app *read* whether a Focus session is on
  (`Windows.UI.Shell.FocusSessionManager`, `IsFocusActive` and a change event). *Starting* one is a
  Limited Access Feature that needs a token from Microsoft **(summary)**. A setting "When Windows
  Focus is on, Jarvis goes Quiet" is a read-only, on-PC link: it puts Jarvis into Quiet the way the
  standby schedule does, and back only if it set Quiet itself. Not checked on the owner's Windows
  version.
- **A Focus tile on the phone.** A second Quick Settings tile next to the mute tile
  (`service/LinkTileService.kt`): one tap starts a 25-minute session (`POST /api/focus/start`,
  JARVIS-API §31.2), a second tap opens the session. Android 13+ can offer to add the tile with
  `requestAddTileService` **(summary)**.
- **Permission fit.** Focus has no card, by design (JARVIS-API §31.4). The tile follows the
  stale-link rule like Home's own buttons.

### 8. A "Jarvis focus" Do Not Disturb mode on the phone (S-M)

- **Plain words.** Since Android 15, apps no longer switch Do Not Disturb directly. An app adds its
  own named **mode**, which shows in the phone's Settings → Modes, and the strictest active mode
  wins **(summary; Android 15 features page)**. It needs "Do Not Disturb access", which the owner
  grants in Settings.
- **Plugs in.** `net/Focus.kt` and the focus event: when a session starts on either app, the mode
  turns on; when it ends, off.
- **Permission fit.** A setting, off by default. Turning it on is a phone-only permission the owner
  grants in Android's own screen, so no Jarvis card is needed (it silences, never acts outward).
  Alarms and urgent "tell me when" should be allowed through the mode.

### 9. A countdown toast with a progress bar on the PC (S-M)

- Windows toasts can carry a progress bar whose value is updated in place by data binding, without
  re-showing the toast **(summary, Microsoft Learn)**. `src-tauri/src/winrt_toast.rs` already builds
  raw toast XML (the alarm toast at line 252), so a bound `<progress>` element and a periodic update
  fit the same module.
- For a timer over ~5 minutes and a focus session: "Tea - 3:40 left", with "Stop" and "+5". The
  phone half is round 1's Live Updates (#13). Together they are one feature in both apps.
- Must respect Quiet and Standby exactly as the alarm toast does.

### 10. Long-press shortcuts on the phone's icon (S)

- No `shortcuts.xml` exists (`res/xml/` checked). `MainActivity` already handles
  `ACTION_START_VOICE`, `ACTION_QUICK_NOTE` and `ACTION_OPEN_BRIEFING`
  (`MainActivity.kt:2357-2363`). Four static shortcuts reuse them: Talk (opens with the mic ready,
  not recording - the widget's lesson in `QuickLinkWidget.kt`), Note, Brief me, What did I miss.
- Opening through a shortcut still meets App lock.

### 11. "Close the day" (S-M)

- The concrete shape of the queued evening wrap-up (creativity #12). At a time the owner picks, the
  Today page shows "Close the day": what is still open (from the scheduler), tomorrow's first thing,
  and one box: "Anything to remember about today?"
- What the owner types is **their own words** (`typed`), so it goes into the Obsidian daily note
  straight away (`jarvis_note_capture.py`) and through automatic learning under today's rules. Apple
  Journal's pattern fits here: suggestions are built on the device and the owner picks which to
  write about **(summary)**. Jarvis can list its own records (a focus report line, a finished
  reminder) as tappable starters. It never writes the reflection itself.

### 12. Accessibility pass (S each)

What is already good (checked): 200+ ARIA attributes, live regions tested in
`jarvis-desktop/tests/a11y.mjs`, a contrast test in `tests/contrast.mjs`, a High Contrast theme
(`theme.css:328`), `prefers-reduced-motion` in every stylesheet, and the answer is announced once,
not per chunk (`index.html:607`). On the phone: `heading()`, `liveRegion` and `stateDescription` are
used, the text size multiplies the system font scale (`JarvisTheme.kt:421`), and "Remove animations"
is honoured (`JarvisTheme.kt:351`).

- **Windows Contrast themes.** No `forced-colors` rule exists in the desktop's CSS (searched).
  WebView2 is Chromium, which supports it **(summary)**. The transparent, glowing quickbar is the
  part most likely to break.
- **Automatic checks.** Desktop: run axe-core (MPL-2.0) inside the existing Playwright tests. Phone:
  Compose 1.8+ has `enableAccessibilityChecks()` for UI tests **(summary)**. The BOM is 2026.06.00,
  so it is available. Run it in the emulator smoke job.
- **Screen reader on frameless windows.** Tauri issue #12901 (open, "priority: 1 high") reports NVDA
  no longer reading text under the mouse in windows with `decorations: false` since Tauri 2.3. The
  quickbar and widget are frameless (`tauri.conf.json:24,52`) on Tauri 2.11.5. This needs a
  10-minute test on the PC with Narrator and NVDA.
- **200% text.** Android 14+ scales text non-linearly up to 200% **(summary)**. Add one screenshot
  test of Home and an approval card at font scale 2.0.

### 13. Paste guard (S-M)

- Pasted text is already tagged and treated as outside text. But a password, PIN or one-time code
  pasted into the text box is the newest user message, and that is kept in chat history with its tag
  (JARVIS-API §18.2; encrypted, but kept). `backend/jarvis_sensitive.py` already recognises
  credentials (its section at line 538) and `jarvis_mail_mask.py` recognises one-time codes.
- **Design:** when a `pasted` or `shared` message contains one, the stored history keeps it masked
  and the reply starts with one fixed line: "That looked like a password, so it is not kept in chat
  history." The same wording in both apps. The model still gets the text for this turn, on the local
  model only (rule 1).

### 14. Glance 1.2 and a small Today widget (S-M)

- `jarvis-client` uses Glance 1.1.1 (`app/build.gradle.kts:313-314`). Google's release page lists
  1.2.0 stable on 2026-08-26, with **generated previews** (the widget picker shows the real widget,
  not a picture).
- A 2×1 "Today" widget: the next thing and the number of cards waiting. Counts only, no titles, opt
  out of the lock screen (item 1).

### 15. Share a document from the phone to the PC (M)

- Today the phone's Share accepts `text/plain` and one image (`AndroidManifest.xml`). Accepting
  `application/pdf` and Word files would send the file over the private link to the PC's
  document-to-text step (round 1, item 5), then fill the box as `shared`. It stays on the owner's
  own networks (rule 2), and the content is outside text.

### 16. Later: a Windows "package identity" (L)

- The modern right-click menu (`IExplorerCommand`), the Windows Share target, App Actions and toast
  text boxes all need either a package identity or a registered COM activator **(summary)**.
  Microsoft's `winapp` CLI (January 2026) adds identity to an ordinary .exe with a "sparse package"
  **(claim)**. `winrt_toast.rs` already explains why a COM activator was not risked. Worth doing
  once, for several surfaces together, only after the owner has a way to test on the PC. A taskbar
  jump list (`ICustomDestinationList`) needs no identity, but Jarvis lives in the tray
  (`skipTaskbar: true`), so it is low value.

## Not for Jarvis

| Seen in | What | Why not |
|---|---|---|
| Android AppFunctions (2026, Gemini in private preview **(summary)**); App Actions on Windows / Click to Do | Letting the phone's or PC's own AI agent call into Jarvis | A cloud assistant would reach Jarvis's memory and actions (rule 1), and would act without Jarvis's own card on Jarvis's screen |
| Wear OS Data Layer | A Jarvis watch app | Google: data "may at some point use Google-owned servers". Rule 1. Plain bridged alarms (item 1) give the watch what it needs |
| Toasts, widgets, tiles, watches, lock screens | An Approve button anywhere outside the app | Already a rule (ARCHITECTURE §8, the widget has Deny only). Restated because every new surface tempts it |
| Clipboard managers, "watch the clipboard" helpers | Reading the clipboard in the background, or Win+V history | Every copied password and code would become outside text. Android blocks background reads anyway. Jarvis reads the clipboard only on the owner's hotkey |
| PowerToys Command Palette extension, Flow Launcher plugin (both MIT) | A launcher plugin that talks to Jarvis | It would hold the pairing token in another program (rule 3 care). If ever wanted, use item 6's "fill the box, tagged `shared`" path, which needs no token |
| Windows Focus API | Jarvis *starting* Windows Focus | A Limited Access Feature that needs Microsoft's token **(summary)**. Reading it is enough (item 7) |
| Phone screen-time (`UsageStatsManager`) | Focus watching on the phone | The owner decided watching is PC only (CLAUDE.md, 2026-09-25) |
| Always-on "journal from your day" audio | Ambient recording for the journal | No speech-to-text on a client; it would record other people |
| Raycast AI, PowerToys Advanced Paste pointed at a cloud model | Launcher-side AI | Sends the owner's text out (rule 1); the quickbar already is the local launcher |

## Two questions for the owner

1. If you have a smartwatch, Android copies Jarvis's phone notifications to it.
   - **Keep cards and alerts on the phone only; let alarms reach the watch** (recommended)
   - **Keep everything on the phone only**
2. Should copying an answer keep it out of Windows clipboard history and sync?
   - **Yes, always** (recommended)
   - **Only for answers that used a memory or read email**

## Sources

- **Android:** bridging and `setLocalOnly` https://developer.android.com/training/wearables/notifications/bridger · Data Layer https://developer.android.com/training/wearables/data/overview · lock-screen widgets https://github.com/divinevideo/divine-mobile/issues/8370 (quotes the blocked FAQ https://android-developers.googleblog.com/2025/03/widgets-on-lock-screen-faq.html) · QPR2 https://www.androidauthority.com/lock-screen-widgets-on-phones-android-16-qpr2-3589668/ · Glance https://developer.android.com/jetpack/androidx/releases/glance · `EXTRA_IS_SENSITIVE` https://developer.android.com/privacy-and-security/risks/secure-clipboard-handling · Modes https://developer.android.com/about/versions/15/features · tiles https://developer.android.com/develop/ui/views/quicksettings-tiles · AppFunctions https://developer.android.com/ai/appfunctions
- **Windows:** clipboard formats https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/dataxchg/clipboard-formats.md · arboard (MIT OR Apache-2.0) https://github.com/1Password/arboard · toast activation and input https://learn.microsoft.com/en-us/windows/apps/design/shell/tiles-and-notifications/toast-desktop-apps · toast progress https://learn.microsoft.com/en-us/windows/apps/develop/notifications/app-notifications/app-notifications-progress-bar · context menu https://blogs.windows.com/windowsdeveloper/2021/07/19/extending-the-context-menu-and-share-dialog-in-windows-11/ · Send To https://www.elevenforum.com/t/add-or-remove-items-in-send-to-context-menu-in-windows-11.4984/ · winapp CLI https://github.com/microsoft/winappcli · App Actions https://learn.microsoft.com/en-us/windows/ai/app-actions/ · FocusSessionManager https://learn.microsoft.com/en-us/uwp/api/windows.ui.shell.focussessionmanager and https://inthehand.com/2023/05/16/keeping-focus/
- **Launchers:** PowerToys Command Palette (MIT) https://learn.microsoft.com/en-us/windows/powertoys/command-palette/extension-development · gallery https://github.com/microsoft/CmdPal-Extensions · Flow Launcher (MIT) https://github.com/Flow-Launcher/docs/blob/main/json-rpc.md
- **Accessibility:** Tauri #12901 https://github.com/tauri-apps/tauri/issues/12901 · `forced-colors` https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/forced-colors · Compose testing https://developer.android.com/develop/ui/compose/accessibility/testing · font scale https://developer.android.com/develop/ui/compose/accessibility/scalable-content · axe-core (MPL-2.0) https://github.com/dequelabs/axe-core
- **Today and journaling:** Things https://culturedcode.com/things/support/articles/4001304/ · Sunsama https://www.sunsama.com/features/daily-planning-and-shutdown · Now Brief review https://www.androidauthority.com/samsung-now-brief-missing-features-disappointing-3529568/ · Daily Hub https://www.androidcentral.com/phones/google-pixel/how-enable-and-use-daily-hub · Apple Journal https://www.apple.com/newsroom/2023/12/apple-launches-journal-app-a-new-app-for-reflecting-on-everyday-moments/
- **Onboarding:** Home Assistant https://www.home-assistant.io/getting-started/onboarding/ · analytics opt-in https://www.home-assistant.io/integrations/analytics/ · LM Studio (summary via guides) https://localclaw.io/blog/lm-studio-beginner-guide
