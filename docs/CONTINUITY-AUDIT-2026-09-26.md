# Android and desktop continuity audit, 2026-09-26

Read-only audit: no code was changed. It asks one question: do the phone app
(`jarvis-client`) and the desktop app (`jarvis-desktop`) offer the same
features, with the same words, the same behaviour and the same rules? It
covers mostly the features added on 2026-09-25/26. The server-address check
was left out on purpose, because another piece of work is changing it.

Every finding below names the file and line I read. "High confidence" means I
read both sides and quote them. "Medium" means one step of it is inferred,
and the finding says which step.

## In short

1. **The two apps match closely.** Every shared word file is identical on both sides and matches the PC. The route check (`tools/check_parity.py`) is clean. The desktop tests that compare words with the phone's all pass.
2. **The biggest real gap: "Stop everything" has no button on the PC.** It is a keyboard shortcut only (Alt+Shift+X). On the phone it is a button.
3. **The "Hide memory lists and chat history" setting describes itself wrongly in both apps.** It now also hides the words of your timers, reminders, lists and morning briefing, and neither app says so.
4. **One written reason is wrong:** ARCHITECTURE §8 says the phone has no "newer version" notice. It has had one since 2026-09-24.
5. **The owner's 2026-09-26 decision (repeating reminders stop asking)** will make one sentence wrong in three places once it is built. The places are listed below, so none gets missed.
6. The rest is small: two "Stop everything" sentences worded differently, no "open Windows sign-in settings" button on the PC, notification text under App lock, and three document slips.

## The table

S = under an hour, M = a few hours, L = a day or more.

| Feature | Desktop | Phone | Gap | Fix size |
|---|---|---|---|---|
| Sending email | Settings, "Sending email" (`settings.html:964`, `email-sending-settings.js`); the card in the Jarvis bar, shown as plain text; the widget's Approve opens the bar (`widget.js:690`) | Mind, "Sending email" (`BrainScreen.kt:438`); the card in the app as plain text (`ApprovalCard.kt:306`) | None. Same words (`email-sending.js:26-33` = `EmailSending.kt:37-43`) | - |
| Plain approval cards | `card-words.js:28-48`, `card-link.js:30` | `CardWords.kt:29-53` | None. Shared file `card-words-cases.json` | - |
| Plain errors and manner | Settings, "How Jarvis talks" (`settings.html:585`) | Mind, "How Jarvis talks" (`BrainScreen.kt:445`) | None. Shared file `plain-error-cases.json` holds the manner words too | - |
| Coming up, snooze, named lists, "cancel that" | Brain, Work (`brain.html:446-465`, `coming-up.js`) | Mind (`BrainScreen.kt:386`, `Schedule.kt`) | None today. See finding 4 for the next change | S |
| "What did I miss?" | Brain, Work, beside "Brief me now" (`brain.js:4029`) | Mind, Morning briefing (`BriefingPlate.kt:217`) | None | - |
| Stop everything | Keyboard only: Alt+Shift+X (`hotkeys.rs:93`, `commands.rs:2170`) | A button on Home while busy (`HomeScreen.kt:948-951`) | No button on the PC (finding 2). Two sentences worded differently (finding 5) | S |
| Live preflight | A command run on the PC (`selftest.py --preflight`) | - | Neither app shows it. That is fine: it is a command-line check | - |
| "Tell me when" and ringing alarms | `coming-up.js:111-116`, `brain/schedule.rs:338-372`, ringing toast `winrt_toast.rs:229-265` | `Schedule.kt:175-222`, `JarvisRuntime.kt:3194`, ringing `ScheduleNotifier.kt:154-185` | None. Same titles, lock-screen words and "rings until seen" rule | - |
| Focus sessions | Brain, Work, and the widget (`brain.html:434`, `brain.js:3597`) | Mind (`BrainScreen.kt:399`, `FocusPlate.kt`) | "Lock on" and the spoken line are PC-only, as written in §8 | - |
| What Jarvis can reach | Settings (`settings.html:938`) | Mind (`BrainScreen.kt:430`) | None. Shared file `reach-cases.json` | - |
| Web search providers | Settings (`settings.html:878`) | Mind (`BrainScreen.kt:420`) | Typing a key is PC-only, as written in §8 | - |
| Morning briefing | Settings, and the Brain's Work tab | Mind (`BrainScreen.kt:406`) | None. Same words (`briefing.js:32-102` = `Briefing.kt:46-104`) | - |
| Calendar private link | No screen: a setting on the PC | No screen | None. Both show the briefing's "Included: ..." line | - |
| Approval gap, "no lock, no risky approval" | `lock/rules.rs:46-48` | `Security.kt:216-222` | Similar words, not identical. No settings button on the PC (finding 6) | S |
| "Hide memory lists and chat history" | `security-settings.js:146-151` | `SecurityScreen.kt:151-155` | Both descriptions are out of date, and they differ from each other (finding 1) | S |
| Update notice | Settings, Updates (`update.rs`) | Home line and Checks (`UpdateCheck.kt`, `HomeScreen.kt:741`) | §8 says the phone has none (finding 3) | S |
| Retrieval trace (`/api/retrieve`) | The HUD window | - | Still to port. Already tracked by `check_parity.py` | M |

## Findings, most important first

### 1. "Hide memory lists and chat history" describes itself wrongly, in both apps (high confidence)

**What is wrong.** Since 2026-09-25 this setting hides more than it says. It
also hides the words of timers, reminders, the to-do list and named lists.
It hides the morning briefing's lines. And it makes the notifications for
those things show only what kind of thing is due. Neither app's description
mentions any of this. The two descriptions also list different things.

- Desktop, `security-settings.js:146-151`: "The Brain's memory lists - what
  Jarvis knows about you, and facts waiting for you - and your chat history
  stay hidden until you press Show and pass Windows Hello. The Galaxy picture
  and answers in the Jarvis bar are not hidden."
- Phone, `SecurityScreen.kt:151-155`: "On Mind, what Jarvis wants to
  remember, what it saved automatically, what it believed on a date, the
  wiki's list of your notes and your chat history stay hidden until you tap
  Show and confirm it is you."

**Evidence that it hides more:**
- Coming up. Desktop: Rust takes the words out (`brain/schedule.rs:155-216`)
  and the Brain shows "Hidden until Windows Hello confirms it is you."
  (`brain.js:3897-3898`). Phone: "Words hidden. Tap Show and confirm it is
  you." (`ComingUpPlate.kt:170`).
- The briefing. Desktop: `brain/briefing.rs:97-116` and `brain.js:4074`.
  Phone: "Lines hidden. ..." (`BriefingPlate.kt:203`).
- Notifications. Desktop: `brain/schedule.rs:378` `toast_words(.., private)`.
  Phone: `JarvisRuntime.kt:3174` and `:3209`
  (`val locked = security.appLock || security.privateLists`).

**Smallest fix.** Write one shared sentence and use it in both apps. For
example: "Your memory lists, chat history, the words of your timers,
reminders and lists, and the morning briefing's lines stay hidden until you
confirm it is you. Their notifications say only what kind of thing is due."
Keep each app's own last line (desktop: "The Galaxy picture ..."; phone:
"Chat answers are not hidden ...").

### 2. "Stop everything" has no button on the PC (high confidence)

**What is wrong.** On the phone, "Stop everything" is a button on Home
(`HomeScreen.kt:948-951`, `StopEverything.kt:25`). On the PC it can only be
started with a key press:
- the hotkey (`hotkeys.rs:93`, `lib.rs:941`, `commands.rs:2170`);
- the only mention in any desktop window is the shortcut list in the Jarvis
  bar (`index.html:320-321`).

I searched every desktop page and Rust file for `stop_everything` and
`stop_all`. There is no button, no tray menu item and no widget control.
That matters in three cases: if another program has taken Alt+Shift+X, if
the owner is using only the mouse, or if the hotkey failed to register.

§8 (`ARCHITECTURE.md:982`) explains why the *hotkey* is PC-only. It does not
explain why the PC has no button.

**Smallest fix.** Add a "Stop everything" item to the tray menu. Also add
it to the widget while Jarvis is busy. Both call the same
`stop_everything_now` the hotkey uses. It must not be held by App lock or a
stale link, the same as the hotkey.

**Also noticed (medium confidence).** The phone shows its button only while
the PC reports activity, an answer is arriving, or the phone is speaking
(`HomeScreen.kt:948-949`). Stop everything also *pauses a focus session*
(`backend/jarvis_focus.py:1651-1660`). But I found nothing in
`jarvis_focus.py` that marks the PC as busy. So during a quiet focus session
the phone's button is probably hidden. I did not run this. The phone's own
Pause on Mind still works.

### 3. §8's "Update notice" row is out of date (high confidence)

`ARCHITECTURE.md:993` says: "The phone has no such notice ... Whether the
phone should say 'a newer version exists' has not been decided."

But the phone has had one since commit `6efeecf` (2026-09-24, "Phone: 'a
newer version is available' notice"):
- `net/UpdateCheck.kt:142-143`: "A newer build of this app is on GitHub (...";
- a quiet line on Home (`HomeScreen.kt:741`);
- a "Check for new versions" switch, on by default
  (`ClientSettings.kt:104-110`).

So the feature is now in both apps, and it was never a one-sided decision.

**Smallest fix.** Remove the row from "One-sided on purpose". Or reword it
as "in both apps: the desktop checks the desktop release, the phone checks
`client-latest`; neither installs on its own."

### 4. The owner's 2026-09-26 decision will make one sentence wrong in three places (high confidence, looking ahead)

`CLAUDE.md` (commit `87b4338`) now says plain repeating reminders, alarms
and the standby schedule "need no card". That is not built yet. Once it is,
these sentences become wrong. They are copied by hand in three places:

- "Anything that repeats waits for your yes on an approval card." Found in
  `brain.html:446`, `coming-up.js:34` and `Schedule.kt:81`.
- "Setting it up asks once with an approval card." (the standby schedule).
  Found in `brain.html:465`, `coming-up.js` (`STANDBY_DETAIL`) and
  `Schedule.kt` (`STANDBY_DETAIL`).

`tests/coming-up.mjs:115-178` will catch it if the HTML and the JS drift
apart, so change all three together. The briefing's and "tell me when"'s own
"asks once with an approval card" lines stay correct: they keep their card.

**Smallest fix.** When the decision is built, change the three copies in
the same commit. It would be better to have the backend send these
sentences (the way `/api/manner` sends its words), so there is one copy.

### 5. "Stop everything": two sentences worded differently (high confidence)

§8 (`ARCHITECTURE.md:982`) says the button uses "the same words" as the PC.
Most words do match, but two sentences do not:

| When | Desktop (`commands.rs`) | Phone (`StopEverything.kt`) |
|---|---|---|
| The PC answered without a sentence | `:2205` "Jarvis stopped what it was doing." | `:35` "The PC stopped what it was doing." |
| The PC could not be reached | `:2215` "...Jarvis could not be reached to stop anything else: {e}" (no full stop) | `:52` "...The PC could not be reached to stop anything else: {detail}." |

No shared word file or cross-check test covers Stop everything. The
desktop's word tests read `Briefing.kt`, `Schedule.kt`, `Focus.kt`,
`EmailSending.kt` and `WebSearch.kt`, but not `StopEverything.kt`.

**Smallest fix.** Pick one wording and use it on both sides. Add a small
check that reads `StopEverything.kt`, the way `tests/focus.mjs` reads
`Focus.kt`.

### 6. "No lock, no risky approval": similar words, and only the phone offers a way to fix it (high confidence)

§8 (`ARCHITECTURE.md:869`) says both apps use "the same words". They say
the same thing, adapted to each device, but the words are not the same:
- Desktop (`lock/rules.rs:46-48`): "Windows Hello is not set up on this PC,
  so Jarvis cannot check it is you, and risky approvals are refused until it
  is. Set up Windows Hello in Windows Settings (Accounts, Sign-in options) to
  approve risky actions - a PIN is enough"
- Phone (`Security.kt:216-219`): "Nothing was approved. This phone has no
  screen lock, ..."

The phone's message starts with "Nothing was approved." The desktop's does
not. The phone also shows a button, "Open screen-lock settings"
(`Security.kt:222`). The desktop has no button: nothing in the desktop code
opens `ms-settings:signinoptions`.

**Smallest fix.** Start the desktop sentence with "Nothing was approved."
too. Add an "Open Sign-in options" button beside it, which opens
`ms-settings:signinoptions`. Or reword §8 to "the same meaning".

### 7. With App lock on, approval notifications show different amounts (high confidence, low importance)

- Desktop: with App lock on, a card's Windows toast shows **the title only**
  (`stream.rs:1084-1094`).
- Phone: the notification shows the PC's title **and** its one-line body,
  whatever App lock says (`ApprovalNotifier.kt:241-245`). The lock screen
  shows only "A decision is waiting. Unlock to see it." (`strings.xml:34`).

The body is written by the PC from its own fixed tables, not from the
email or file, so nothing private leaks. §8 already records this for the
phone's home-screen *widget* ("shows the notice text ... lock or not"), but
not for notifications.

The fallback text for a card with an empty body also differs:
"Nothing runs until you decide." (`stream.rs:1099`) versus "Nothing has
happened yet." (`ApprovalNotifier.kt:244`).

**Smallest fix.** Use one fallback sentence in both apps. Then either add
one line to §8 ("phone notifications, like the widget, show the PC's title
and body under App lock"), or make the phone show the title only while App
lock is on.

### 8. The same kind of action is held on a stale link in one feature and not another (high confidence; both apps agree, so this is the owner's call)

"Held on a stale link" means the app will not do it while its live
connection to the PC is out of date (rule 4). The two apps agree on every
case below. But the rule differs from feature to feature:
- Focus: **Pause and Stop are not held**, because they only make Jarvis do
  less (`brain/focus.rs:51-52`, `Focus.kt:64`).
- Coming up: **Pause, Delete and Done on a timer or reminder are held**, and
  so is **Stop** on a morning briefing (`brain/schedule.rs:583`,
  `brain/briefing.rs:271`; phone `JarvisRuntime.kt:3075-3076`).
  `JARVIS-API.md:3415` says: "Both apps hold every one."

Deleting a ringing "tell me when" or an alarm only makes Jarvis quieter,
the same as pausing a focus session.

**Smallest fix, if the owner wants it:** let Pause, Delete and Stop through
on a stale link in both apps, as Focus does. Keep Add, Resume and "Set up"
held.

### 9. Three document slips (high confidence)

- `ARCHITECTURE.md:991` (the "Saying a timer aloud" row) points to
  "JARVIS-API §26.5" for ringing. §26.5 is the email-sending "Known gaps"
  (`JARVIS-API.md:4625`). Ringing is **§30.5** (`JARVIS-API.md:4941`).
- `ARCHITECTURE.md:1292` ("the hook focus sessions will use") and
  `JARVIS-API.md:4728` ("focus sessions will register one") are in the
  future tense. They already register: `backend/jarvis_focus.py:1659-1660`
  `jarvis_stop_all.register("focus", ...)`, which pauses the session.
- `JARVIS-API.md` §28 says the phone's button is behind App lock and the
  PC's hotkey is not. The App lock part of §8 (`ARCHITECTURE.md:843-880`)
  does not say this. One line there would help.

### 10. A focus session's "On: ..." words are not hidden (high confidence; both apps agree)

Both apps show the words the owner typed for a focus session, as "On: ..."
(`brain.js:3597`, `FocusPlate.kt:133-134`). They show them even while
"Hide memory lists and chat history" is on. Yet a reminder's words, which
are the owner's words in the same way, are hidden (finding 1). This is not a
gap between the apps. It is a question of how the setting fits the new
feature.

**Smallest fix, if wanted:** hide the "On:" line while the lists are hidden,
the same way Coming up hides its words.

## Looked at and fine

- **`tools/check_parity.py`:** clean. 107 desktop routes and 96 phone
  routes: 96 in both, 8 left out on purpose with reasons, 2 that are not
  Jarvis routes, 1 still to port (`/api/retrieve`), and "No undecided
  drift". Every "left out on purpose" route has a matching row in §8.
- **Shared word files.** All ten `*-cases.json` pairs are byte-for-byte
  identical on the desktop and the phone. Each generator's `--check`
  passes: card-words, email-sending, focus, plain-error, reach,
  risky-approval, web-search, second-card, big-model and hardware.
- **Desktop tests that compare with the phone** all pass (run today):
  `briefing`, `coming-up`, `focus`, `email-send`, `web-search`, `reach`,
  `plain-errors`, `card-words`, `security` and `continuity`.
- **Email sending.** The Settings words are the same. On the PC an email is
  approved in the Jarvis bar only, shown as plain text in a `<pre>` block
  (text shown exactly as written, never formatted). On the phone it is shown
  in full in the app. Notifications and widgets show only the PC's own title.
- **Card words.** Same on both: "Needs your OK", Deny on the left and
  Approve on the right, "Open the card" with "and N more waiting", and the
  same four spoken lines (`card-words.js:45-48` = `CardWords.kt:48-53`).
- **Manner.** Default "warm". The same labels and "why" lines on both.
  Changing it is held on a stale link on both (`plain_errors.rs:176-180`,
  `JarvisRuntime.kt:1544-1545`).
- **Coming up.** Same titles, empty lines, button labels, "Just went off",
  Snooze 10 minutes and the standby words. Clearing a named list asks "are
  you sure?" on both, with the same question
  (`coming-up.js:275-279` = `Schedule.kt:379-381`), and sends the count it
  showed. The phone's "Yes, clear it / Keep it" matches its own Forget
  confirmation.
- **"Tell me when" and alarms.** Same notification titles and lock-screen
  words (`brain/schedule.rs:342-372` = `Schedule.kt:190-210`). A match shows
  its `alert`, never what is watched. Alarms and urgent matches ring until
  seen on both, with Snooze on a ringing alarm. The button that silences it
  is "Stop" on the phone and Windows' own "Dismiss" on the PC. That is a
  difference in each system's own buttons, not in Jarvis's words.
- **Focus.** Same words and limits (1-240 minutes, +10). Start, Resume and
  "+10 minutes" are held on a stale link; Pause and Stop are not, on both.
  "Lock on" and the spoken line are PC-only, which §8 and
  `check_parity.py` explain (the backend refuses the spoken line to
  anything but this PC: `backend/focus.patch:13-23`).
- **Morning briefing and "What did I miss?"** Every sentence is identical.
  Turning "Show who new emails are from" on is held on a stale link and
  turning it off is not, on both. "Brief me now" and "What did I miss?" are
  reads (they only look), so they are not held. Hidden lists hide the lines
  on both.
- **Web search and what Jarvis can reach.** The words come from shared
  files. Typing a search key is PC-only, and §8 says why (rule 3).
- **Calendar private link.** Neither app has a screen for it, which is as
  designed. Both show the briefing's "Included: ..." line.
- **Approval gap.** Same choices and default ("Risky only" / "Every
  approval", `security-settings.js:33-34` = `Security.kt:58-62`). The PC
  asks Windows Hello itself, and §8 explains the phone's side.
- **Timer said aloud on the PC only.** Explained in §8.
- **Blocking screenshots.** Still the owner's call for the desktop, as §8
  says. Nothing in the desktop code protects its windows from screenshots.
- **Preflight.** A command run on the PC. Neither app shows it, so no §8
  row is needed.
