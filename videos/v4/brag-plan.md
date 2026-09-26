# Jarvis launch video v4: "Cutting-edge. And it still asks first."

Two cuts from one project:

- `jarvis-launch-v4.mp4`: 1920×1080, 30 s, for the README and GitHub.
- `jarvis-launch-v4-vertical.mp4`: 1080×1920, 15 s, for a phone held upright.

## The idea

Jarvis's newest features are cutting-edge, and **it still asks first**. The only
big lines on screen are:

- **CUTTING-EDGE.**
- **AND IT STILL ASKS FIRST.**
- **YOUR ASSISTANT. YOUR PC. YOUR RULES.**

Each feature beat carries its claim in one short mono readout, v2's "tag line".
Every spoken line is captioned.

## The look: v2's style, v3's honesty

The owner preferred v2's style, so v4 brings it back:

- machine capitals slammed onto the screen, with a red and cyan glitch;
- camera punches, a white flash and a colour split on the beat;
- HUD corner brackets and readouts;
- scanlines, film grain and the purple flare at the end;
- a fast cut on the bar, and a driving 120 BPM score.

From v3 it keeps:

- the real desktop app's screens, rendered from its own code, with made-up
  example data;
- captions on every spoken line;
- a claim table checked against the code.

## Storyboard (landscape, 30 s)

| time | beat | on screen | words |
|---|---|---|---|
| 0–2 | CUTTING-EDGE | The reactor ignites. | **CUTTING-EDGE.** |
| 2–5.5 | Lives on your PC | The real desktop widget with its LOCAL badge. A ring holds EMAIL / FILES / MEMORIES. | LOCAL AI MODEL · YOUR EMAIL, FILES AND MEMORIES ARE HANDLED ONLY BY IT. PHONE ↔ PC OVER YOUR PRIVATE NETWORK · NEVER A PUBLIC TUNNEL |
| 5.5–9.5 | Focus | Real Brain › Work › Focus session: on target, then off target, then the real report card. | You: "Focus for 30 minutes." Jarvis: "YouTube can wait." WATCHES THE PC ONLY · KEEPS COUNTS, NEVER WHAT IT SAW |
| 9.5–12.5 | Tell me when | The real approval card for the watch, Approve, then the phone ringing. | You: "Tell me when an email from Alex arrives. Urgently." ONE YES TO SET UP · URGENT RINGS UNTIL YOU LOOK · NEVER REPLIES |
| 12.5–15 | Stop everything | ALT + SHIFT + X slams, the music stops dead, and the Windows notification appears. | ALT+SHIFT+X · STOPS TALKING · HALTS BEFORE ITS NEXT STEP |
| 15–19 | Asks first | The real "send an email" card, then Windows Hello. | **AND IT STILL ASKS FIRST.** READY · SENDING IS OFF UNTIL YOU TURN IT ON. WINDOWS HELLO ON THE PC · FINGERPRINT OR PIN ON THE PHONE · NO "ALWAYS ALLOW" |
| 19–22 | Instant answers | The reactor asleep; the real quick-ask reply. | You: "Set a timer for 10 minutes." ANSWERED WITHOUT THE AI MODEL · WORKS WHILE IT SLEEPS |
| 22–25.5 | It learns you | Real Brain › Memory, with Forget and "Erase the words", then a sensitive fact waiting. | LEARNS FROM YOUR OWN WORDS ONLY · SENSITIVE TOPICS WAIT FOR YOUR YES |
| 25.5–30 | Your rules | Flare and the reactor. | **YOUR ASSISTANT. YOUR PC. YOUR RULES.** READY FOR A SECOND GRAPHICS CARD ▸ LONGER CONVERSATIONS · PICTURES |

The upright cut (15 s) keeps CUTTING-EDGE, Focus, Tell me when, Stop, Asks
first (with the phone's fingerprint sheet) and Your rules.

## Evidence for every claim

B = branch `claude/admiring-ritchie-5urg5h` at b218ae1. "Today" means built
and tested in the code on that branch. **Nothing has run on the owner's PC
yet**, and the Windows-only parts (reading the front window, Windows Hello)
have never run on Windows at all.

| claim on screen | status | evidence |
|---|---|---|
| Local AI model | today | An 8B model in Ollama on the PC; a model that is not on this PC, or a `:cloud` one, is sent nothing (B `docs/ARCHITECTURE.md` §7, §4). |
| Your email, files and memories are handled only by it | today | B `docs/ARCHITECTURE.md` §4: the lanes out of the PC carry no email, file or memory content to an AI. Worded carefully: reading email signs in to *your* mail server, and an approved email is sent, so "never leave the PC" would overclaim. |
| Phone ↔ PC over your private network · never a public tunnel | today | The desktop listens only on this PC or Tailscale/Meshnet addresses and refuses 0.0.0.0 (B `jarvis-desktop/src-tauri/src/commands.rs:701-753`), and there is no tunnel code anywhere (CLAUDE.md rule 2). The phone itself still accepts any `https://` address (`data/BaseUrl.kt:29-40`); the being-built "server address on your own networks only" check is **not** used or shown. |
| "Focus for 30 minutes." | today | Answered without the model (B `backend/jarvis_quick.py:967-1002`, `test_focus.py:873`). |
| Watches the PC only | today (never run on Windows) | The backend reads the front window (B `backend/jarvis_focus.py:443-566`). Nothing leaves the PC. |
| "YouTube can wait." | today | Template `"{name} can wait."` (`jarvis_focus.py:205`); youtube.com is spoken as "YouTube" (`:283`). It is one of four starting lines, picked at random. The card on screen switches to the real "off target" state at that moment ("14 minutes left - off target.", "One drift so far."), captured from `jarvis_focus.Engine` driven with YouTube in front. |
| Keeps counts, never what it saw | today | The saved record holds numbers and true/false only (`jarvis_focus.py:597-631`), tested at `test_focus.py:661-701`. |
| The report card | today | `report_from` (`jarvis_focus.py:680-715`): "Focus session done.", "On target: N of M minutes.", "N% focused.". The numbers on screen are example data. |
| "Tell me when an email from Alex arrives. Urgently." — one yes to set up | today | B `backend/jarvis_tellme.py`. "Tell me when" and "urgently" are recognised in `jarvis_quick.py:1134-1236`. One approval card, and the card says "It never replies, never acts, and never opens or reads out the email". |
| Urgent rings until you look | today (phone drawn unlocked: a locked phone shows only "Jarvis: something you asked to be told about happened.") | The phone notification's sound and vibration repeat until it is opened or swiped away, with a "Stop" button, on the "Alarms and urgent alerts" channel (B `ScheduleNotifier.kt:161-189`). It rings only while the phone is connected to the PC. |
| Never replies (no phone-call service) | today | The code only notifies; there is no telephony. |
| Alt+Shift+X: stops talking, halts before its next step | today | Registered as "Stop everything", default Alt+Shift+X (B `jarvis-desktop/src-tauri/src/hotkeys.rs:92-100`, `lib.rs:941`). It silences speech, then `/api/stop_all` stops the task before its next step and the current answer from using more tools (`backend/jarvis_stop_all.py:9-44`). Worded "before its next step" because a step already running finishes. |
| The Windows notification | today | Title "Stop everything"; text "Stopped speaking. " (`commands.rs:2206`) plus the backend's message (`jarvis_stop_all.py:197-235`). Drawn, because it is Windows' own notification, not an app screen. |
| The phone's red "Stop everything" button | today | B `HomeScreen.kt:948-953, 1671-1700`, with its hint word for word. |
| The send-email card: every word shown | **ready** | `jarvis_email_send.describe()` (`backend/jarvis_email_send.py:424-454`), title "Jarvis wants to send an email". Sending is built but **off until the owner turns it on** (`send_email` in `[tools].enabled`), so it is labelled READY on screen. |
| Windows Hello on the PC | today (never run on Windows) | The backend itself asks Windows Hello before a risky approval from the PC (B `backend/jarvis_owner_check.py`, `owner-check.patch`, `test_owner_check.py`). The prompt's words are `approval_message()`: the card's title, then the risk line for `send_email` (`email-send.patch:48`). |
| Fingerprint or PIN on the phone | today | B `BiometricGate.kt:216-228`: fingerprint or the phone's PIN by default. |
| No "always allow" | today | Neither app has one. If `send_email` is set to anything but "ask", the email is refused (`jarvis_email_send.py:488-499`). |
| "Set a timer for 10 minutes." — answered without the AI model; works while it sleeps | today (English) | B `backend/jarvis_quick.py:1-70`, wired in before the model (`schedule.patch:88-122`). A test with every network connection failing still answers (`test_schedule.py:617-694`). The line "Done - answered on this PC without the AI model." is `jarvis_quick.py:129`. |
| Learns from your own words only | today | "…from what you type or say to it - never from web pages, emails, documents or notes." (B `jarvis-desktop/src/auto-learn.js:34-37`; `backend/jarvis_auto_learn.py`) |
| Forget and "Erase the words" | today | On every fact row (B `brain.js:2122, 2146, 3274-3276`). Both ask "are you sure?" first. |
| Sensitive topics wait for your yes | today | "Not saved automatically: about health, a sensitive topic", with Keep / Discard (`auto-learn.js:352`; `jarvis_sensitive.py`). |
| Ready for a second graphics card: longer conversations, pictures | **ready** | All off until a suitable second card is found and the owner approves (B `jarvis_second_card.py:7-46`; `test_second_card.py`). Features "Longer conversations" and "Pictures". |

## Left out on purpose

- **The "server address on your own networks only" check and the lighter
  approval rules:** still being built (the owner's instruction).
- **"Your email, files and memory never leave the PC":** it overclaims (see
  above).
- **"Every action stops at once":** a step already running finishes first.
- **The preflight check's "22 pass, 0 fail":** that count comes from a test
  with stand-ins, not a real run, so it is not shown.
- **"Hey Jarvis", interrupting by talking, and speech from the first comma:**
  all built, but hard to show honestly in a picture without a real voice. They
  are named in the share copy instead.
- **Web search on SearXNG:** built; cut for time.

## Honest limits of the picture

- **The desktop screens are real.** They are the app's own HTML, CSS and
  JavaScript, rendered headless with made-up data ("Alex", example.com
  addresses). Open Sans stands in for Windows' Segoe UI.
- **Some screens are drawn, not captured,** because they are Windows' or
  Android's own:
  - the Windows Hello prompt and the Windows notification;
  - the phone and its notification, fingerprint sheet and Stop button.

  Every word on them comes from the code cited above.
- **The focus numbers, the email and the facts are examples.** Nothing here
  was run on the owner's PC.
