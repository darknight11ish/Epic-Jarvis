# Report 52 (audit), agent ae7b0ecc, 2026-09-30T07:21Z

> **What it was asked** (first 600 characters of the task): Read-only audit of /home/user/Epic-Jarvis (read CLAUDE.md first; beginner owner, plain words; verify each claim with file:line + quote; 'not checked' honestly; change no files; working directory may have been changed: use absolute paths under /home/user/Epic-Jarvis). The owner asks: 'Does the android app or desktop program have the ability to (1) quickly check different parts of Jarvis or a current task running, (2) just have a chat with Jarvis WITHOUT any Jarvis face/model/avatar showing, (3) shortcuts or widgets on Android made through the app for easy access to different features, (4) CUSTO

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Read-only audit. I only READ code and docs; I ran no tests and did not run check_parity.py. Tap counts below come from reading, not from a phone.

**Short answers**
1. Quick check of Jarvis or a running task: yes, but only inside the apps and the tray. No single "status" widget or tile exists.
2. Chat without a face: yes on both, in slightly different ways (details in B).
3. Android shortcuts and widgets: yes. Five long-press app-icon shortcuts, 3 configurable Quick Settings tiles plus 2 fixed tiles, and 3 widget types.
4. Customizable widgets: yes, in a "describe it in words" way (JARVIS-API §86). It is not a Samsung-style drag-and-configure widget.

**Correction to the brief:** `res/xml/shortcuts.xml` has FIVE shortcuts, not four: Talk, Live, Note, Brief me, What did I miss. All are static.

**(A) Quick status (from code; taps are estimates)**
- What Jarvis is doing now: phone Home shows activity (`state.activity`, `HomeScreen.kt:882` for the task row). Desktop: tray menu line `ID_STATUS_ACTIVITY` (disabled text, `tray.rs:175`), and the Brain "Now" tab ("Right now", `brain.html:244`). About 1 tap on the phone once the app is open, 2 clicks on the PC.
- Running or paused task with Pause/Stop: phone Home shows it while WORKING or PAUSED (`HomeScreen.kt:882`, `onStopTask` at line 607; the API calls `/api/task/pause` and `/stop` are in `JarvisApi.kt:447-451`). Desktop: `commands.rs:2527/2548`. Work-tab panels (`brain.js`) show Pause/Resume/Stop for chatbot, support and focus tasks. Nothing outside the app shows it.
- Approvals waiting: tray row "N waiting" (`tray.rs`), the desktop widget, the phone ApprovalWidget and notifications. This is the best-covered item.
- Link, health, errors: tray icon, the phone's Link tile (`LinkTileService`), the widgets' "Not up to date" line. A full health page also exists.
- Coming up: Brain sections on both apps. The widget list blocks (`reminders`, `timers`) can show it.
- Model in use and GPU state: Brain -> Model (both apps). Not available in a widget or tile. The board widget has no model or GPU source (§86.1 source list).
- Last briefing or missed items: "Brief me" and "What did I miss" shortcuts. Widget sources cover counts only (`email_count`, `events_count`).
- **A single glance surface that works without opening the app: partial.** The desktop tray is closest. On the phone, only a self-made "Jarvis widget" (§86) comes close. The lists it can show are `reminders`, `timers`, `today`, `todo`, `now_playing`, plus counts, disk and focus. **There is no "current task" or "running/paused" source, and no approvals-count source.** The ApprovalWidget covers approvals.

**(B) Chat without a face**
- Desktop: the Jarvis bar (`index.html`) has no canvas or iframe, so it is text only. I grepped it and found no face element. Faces live in the HUD and widget iframes (`jarvis_hud.html:609`, `widget.html:123`) and the floating window. The tray has "Show or hide the Jarvis bar", "…widget" and "…floating face" items, and each has a hotkey (Alt+Space is the bar's default). So a face-free chat is the Jarvis bar, and it can be reached by a hotkey. The Jarvis-bar hotkey is on by default. There is no "off for the HUD" switch that I found (not fully checked).
- Phone: Appearance has a face size "Hidden" (`FaceSize.HIDDEN`, `AppearanceStore.kt:598`), and `HomeScreen.kt:1066` has a `faceSize.hidden` branch. Home then is the chat. History and Continue this chat also work. The floating avatar is off by default.
- "Temporary chat" and "Hide memory lists" are separate privacy switches, not face options.
- No notification reply box was found (not checked exhaustively).

**(C) Inventory**

| Name | What it does | Configurable | App lock | Issues |
|---|---|---|---|---|
| App-icon shortcuts (5, static) | Talk (opens, no capture), Live (opens screen), Note, Brief me, What did I miss | No, fixed list | Open behind lock | Only 5 exist. No pinned or dynamic shortcut code exists for owner use. The only `pushDynamicShortcut` is the bubble one in `WakeWordService.kt:721` |
| Quick Settings tiles ×3 | One action each: Focus, 10-min timer, Brief me, Stop everything, Play/pause PC | Yes, Settings -> Quick Settings tiles (§81.2) | Stop everything runs anyway; others ask phone unlock | Only 5 actions to choose from. Not Coming up, Look, Live, or a chat |
| LinkTileService, LiveTileService | Mute/link, and Live start/end | No | Live ends in the tile, Start opens the app | None found |
| ApprovalWidget (4x2, resizable, updatePeriod 0) | Shows waiting card, Deny one-tap, Approve opens app | No configure activity | Shows title only; Approve opens app | No `previewLayout` in the XML (grepped) |
| JarvisBoardWidget "Jarvis widget" 1-3 (4x2, resizable, 30 min) | Draws a saved description | Yes: say it in Brain -> Widgets, tap Add, then pick which widget each slot shows | Private blocks show "Hidden"; buttons open the app except Stop everything | Slots 1-3 only; owner can't edit a widget, only delete and re-describe (§86.3 has no edit route); no "last updated" seen in the draw path (not fully checked) |
| QuickLinkWidget (3x1, resizable) | Link status, Mic, Note | Fixed | Opens app | No configure; can't choose actions |
| Floating Jarvis (overlay/bubble), Assist gesture, Share targets | Avatar, assistant, share into chat | Settings | Bubble unverified on device | Bubble needs MessagingStyle (CLAUDE.md note) |
| Desktop widget window | Face, or a chosen board widget | Picker; describe in words | Approve blocked; Focus, timer, play/pause open the bar | The board widget is available there too (§86.4) |
| Desktop tray | Status, power mode, approvals, waiting, mute, Stop everything, Live, Watch, windows | Fixed | Stop always works | Nothing task-specific |
| Desktop hotkeys (10) | Bar, clipboard, Look, note, widget, Stop everything, floating, talk-to-type, Watch, Live | Yes, Settings rows | Start held under lock | No "chat only" or "show current task" key |

Android Auto and watch: only the smartwatch notification mirror setting exists (§ in CLAUDE.md); no Auto app.

**(D) Gaps, ranked (all obey the five rules if they never approve)**
1. **Add "current task" and "approvals waiting" as widget sources.** S. Both apps already read them; a widget shows them with a Stop button that reuses `/api/task/stop` (never approves). Private in the widget until App lock is off. Works on one card.
2. **Let the owner edit a saved widget and add more than 3 phone slots.** M.
3. **More tile/widget actions: Coming up, Look at this, Live, a saved question.** S-M. Each opens the app; none act by themselves.
4. **Pinned shortcuts for Brain sections, History chat, Focus, Coming up** via `ShortcutManagerCompat.requestPinShortcut` (my grep found none). M. This gives the "make my own shortcuts" behaviour. Open behind App lock. Not a catalogue.
5. **A phone "text chat only" Home** without needing the Appearance switch. S, low value since Hidden face exists. **Desktop:** a tray "Quick chat" that opens the Jarvis bar is basically there.
6. A status widget that ignores App lock is refused (rule 4 and lock decisions).

For parity: tiles and widgets are phone-only, and the desktop has widget board and hotkeys. Whether each gap is listed in ARCHITECTURE §8 was not checked, and `check_parity.py` was not run.

**Owner decisions**
- Q1 Status widget: (a) add "current task + Stop" and "approvals" as sources to the existing board widget (recommended); (b) build a separate fixed Status widget; (c) leave it.
- Q2 Shortcuts: (a) let the owner pin any Brain section or chat as a phone shortcut (recommended); (b) just add 2-3 more fixed ones.
- Q3 Face-free chat: (a) leave as is and tell the owner where it is (recommended); (b) add a one-tap "text only" mode on both apps.
