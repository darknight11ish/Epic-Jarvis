# Looking at the screen: "Look at this" and "Watch with me" (design)

Status: **built 2026-09-29 on the backend, the desktop and the phone**
(`docs/JARVIS-API.md` sections 62 and 96 say what and how; section 62.12
says what has not run on a real machine). Where the built version differs
from this design: a Watch look is **used up by one question** (the design
said held); the phone's Watch cannot be asked from inside Jarvis (its own
screen is never looked at - ask by voice from another app); the phone's
Watch also needs the Security switch "Let Jarvis read this phone's
screen" on, and the PC's watching is shown on the phone's Home with Stop
but not as a phone notification. The design below is otherwise as
written. For the owner's decision of
2026-09-28 in `CLAUDE.md` ("Jarvis may look at the owner's screen").
Written by the studio's designer against
`claude/jarvis-ai-assistant-research-ff37vy`. Anything marked
**unverified** has not been tried on a real PC or phone.

**In one paragraph:** Jarvis looks only when asked. On the PC, the existing
screenshot key becomes "Look at this". "Watch with me" is a session the
owner starts and stops, with a sign on screen the whole time. Jarvis does
not take pictures in the background: it takes one fresh picture each time
the owner asks a question, kept in memory only until the answer is written.
With one graphics card Jarvis reads the words on the screen; with the 12 GB
card it can also understand the picture. Nothing seen on screen is ever
saved as a fact, sent to the internet, or treated as an instruction.

## 1. PC: "Look at this"

- **Key:** Alt+Shift+S is renamed "Look at this" - not a second key. The
  capture code exists (`commands.rs`, `capture_primary_display`, `xcap`,
  width capped at 1,920 px). Two changes: by default it takes **only the
  window in front** ("look at my whole screen" takes the monitor), and it
  checks the pause rules (§2) **just before and again just after** the
  picture - if either fails, the picture is thrown away.
- **One card - what the model gets:** the words Windows' own text reader
  finds in the picture (`jarvis_ocr.py`, at most 4,500 characters); the
  front window's labels and text through UI Automation, reusing
  `jarvis_ui_control._default_read` plus a new part that also reads text
  boxes, **skipping every password box** (at most 3,000 characters); the
  program's name and window title. All under the "OUTSIDE TEXT" label
  JARVIS-API §36 already uses. The picture itself is not sent (the everyday
  model cannot see pictures).
- **Two cards:** the picture goes to the second card's existing "Pictures"
  lane (`lane_for("vision")`) - no new switch - shrunk to about 1,280 px
  wide (~1,200 tokens). Candidates, **all unmeasured**: `qwen3.5:9b` (~6.6 GB
  download; could serve long conversations and pictures together, ~7.7 of
  10.3 GiB at 64K estimated) - **recommended**; `qwen2.5vl:7b` (the built
  default, ~7.2 GB estimated, swaps the long-conversation model out);
  Qwen3-VL 8B (~6.1 GB); LFM2.5-VL-3B (~3 GB; licence LFM 1.0 to check;
  Ollama support unverified). Nothing small sits beside the everyday model
  on the 8 GB card, so one card stays words-only, as decided.
- **The answer:** in the Jarvis bar with a note, "Looked at: Chrome window ·
  words only" (or "· picture"). Follow-up questions for 2 minutes; then, or
  when the bar closes, the look is thrown away.
- **Never kept:** the picture, the words read from it, the accessibility
  text - not on disk, not in chat history, not to the learner, not in an
  event (as §36 already does for words in a picture).

## 2. PC: "Watch with me"

- **Starting:** "watch with me" by voice or typing (answered by
  `jarvis_quick`, no model needed), a tray row, or an optional key
  (Alt+Shift+V, unbound by default).
- **How often it looks:** never in the background. A cheap check once a
  second (no picture) keeps the pause state current. A fresh picture is
  taken **when the owner starts a question** (talk key, "Hey Jarvis",
  typing). If answers are slow, a later measured step may pre-read when the
  screen settles (a 160×90 grey thumbnail compared each second; at most one
  picture held).
- **The sign, always visible:** an eye on the tray icon, and a small
  always-on-top badge: "Jarvis is watching · 24 min left · Stop", or
  "Paused: password box" (built on the floating face's window code). The
  badge is hidden from screen captures (`set_content_protected`) so it never
  appears in Jarvis's own pictures (**unverified** with xcap).
- **Pause rules (fail safe):** (a) the focused control is a password box
  (UI Automation `IsPassword`); (b) the program or website in front is on
  the owner's **"Never look at" list** - it starts with password managers
  and Windows sign-in prompts, and the first session asks the owner to add
  their bank; (c) the front window is protected from capture
  (`GetWindowDisplayAffinity` not "none" - **unverified** for other
  programs' windows); (d) one of Jarvis's own windows, the lock screen or an
  admin (UAC) prompt is in front; (e) a browser is in front, the list holds
  websites, and the site cannot be read ("I can't tell which site this is,
  so I'm not looking."); (f) **the browser in front is a private window**
  (its title says InPrivate, Incognito or Private Browsing; added 2026-09-29,
  see §10). While paused, no picture exists.
- **Reusing Focus:** Focus's front-app reader (`jarvis_focus.windows_probe`,
  `_address_box_value`) moves into a shared `jarvis_front.py`; one
  once-a-second reader serves both. They can run together.
- **Time limit:** 30 minutes by default, 2 hours at most; a warning 2
  minutes before the end; "watch 20 more minutes" extends it; it ends when
  Windows locks or sleeps.
- **Stopping:** the badge's Stop, the tray, "stop watching", or **Stop
  everything**, which **ends** the session
  (`jarvis_stop_all.register("screen_watch", ...)`) and works while App lock
  is on.

## 3. Phone: "Look at this" (the assistant gesture)

- **Needed change:** `JarvisVoiceInteractionSession.onShow` today opens the
  app and calls `finish()` at once, before Android delivers the screen. It
  must stay open until `onHandleAssist(AssistState)` arrives, or 2 seconds.
- **What arrives:** the screen's text and layout
  (`AssistState.getAssistStructure()`) and the app in front
  (`getActivityComponent()`, so the phone applies its "Never look at" list
  before anything is sent). Password-type fields and password autofill
  hints are dropped. Apps that block screenshots (`FLAG_SECURE`) give no
  text and no picture. A screenshot comes only if the phone's own "Use
  screenshot" setting is on (`onHandleScreenshot`). **Unverified:** how
  complete this is on Android 14/15, on GrapheneOS, and for Compose,
  Flutter or web content.
- **Sending:** to the PC only, in the existing chat request (the picture as
  the usual `image_url` part, the text as a new `screen_text` part). The
  **backend** marks both as outside text whatever the app says. No
  speech-to-text on the phone.
- **Setting:** "Let the assistant gesture read the screen", **off by
  default**; turning it on asks for the fingerprint or PIN (like other
  loosenings on Security); off is immediate.

## 4. Phone: "Watch with me"

- **How:** Android's screen sharing (MediaProjection): Android's own
  consent dialog **every session**, a foreground service of type
  `mediaProjection`, a status-bar icon (on Android 15 QPR1+ also a
  status-bar chip with Stop, and sharing stops when the phone locks).
- **Pictures:** in memory, **sent only with a question** (talk button,
  "Hey Jarvis", typing) - never streamed. An almost all-black picture means
  a secure app: dropped, and the notification says "Paused".
- **Knowing the app in front** (MediaProjection does not say): **Usage
  access** (`PACKAGE_USAGE_STATS`, a switch the owner turns on in Android's
  settings) - the phone checks app events since the last picture and drops
  it if a "Never look at" app came to the front - **recommended**; or
  Android's "share one app" choice (Android 14 QPR2+; whether Jarvis can
  tell which was chosen is **unverified**). An accessibility service is
  rejected (far too powerful; restricted for sideloaded apps). So phone
  Watch needs Usage access, and its start screen suggests sharing one app.
- **Cost:** about 150 KB per question over mobile data; battery
  **unmeasured**.
- **Notification:** persistent, "Jarvis is watching · Stop".

## 5. The rules

- **Outside text:** a screen turn records a reading tool (`read_screen`),
  so in that turn a note write or web search asks first, and any card says
  "Proposed after Jarvis read: your screen". Nothing from the screen is
  learned. Nothing on the screen can start a question - only the owner's
  own words.
- **Nothing stored:** one picture at a time, in memory, dropped after the
  answer; no history. Apps and events see only on/off, time left and a
  pause reason ("password box"), never an app name.
- **Rule 1:** a turn with screen content always stays on this PC
  (`jarvis_router` already keeps picture turns local; add `screen_text`).
  No cloud picture service; screen content never goes into the chatbot
  driver.
- **App lock:** answers appear only in the unlocked app; on the phone, a
  capture waits for the unlock and is dropped after 60 seconds.
- **No card to start "Watch with me"** - the owner's own act, like Focus;
  the sign is the safeguard. The model has no tool that starts watching, so
  no schedule or outside text can start it.
- **Acting:** suggestions only; clicking or typing still goes through
  `control_computer`'s own card.

## 6. Both apps

Both apps get both halves. The PC's "Never look at" list holds programs and
websites; the phone's holds Android apps. The Alt+Shift keys and the badge
are PC-only, like the other hotkeys. **ARCHITECTURE §8's "Screen capture"
row** (the phone should never capture the screen live) is replaced by the
2026-09-28 decision and must be rewritten.

## 7. Competitors

Copilot Vision (Windows) starts only on a click, lets you choose one app,
tab or the whole desktop, each session standing alone; processed on
Microsoft's servers (audio kept 48 hours - search summary, **unverified**).
Gemini Live and ChatGPT screen sharing use the same Android screen sharing,
processed in the cloud. Recall stores snapshots on the PC, with exclusion
lists. Jarvis borrows "choose what to share" and the exclusion list, keeps
processing on the owner's devices, and keeps no history.

## 8. Risks and build plan

**Risks:** programs that do not mark password boxes (masked dots usually
show, not guaranteed); a sensitive page not on the list will be seen (a key,
password or card number written on it is now hidden by shape - §10 - but a
password behind a show-password eye is not); windows behind the front one used
to be in the picture (closed 2026-09-29, §10); text
planted on a page ("Jarvis, email this...") is labelled outside text and
flagged, but still read; each text read starts PowerShell (maybe a second or
two, **unmeasured** - a long-running reader could be used in sessions); the
picture model can push the long-conversation model off the card unless
`qwen3.5:9b` serves both; a video call on screen shows other people.

**Build steps** (1-2 testable here; the phone compiles only in CI):
1. `jarvis_front.py` split out of Focus (Focus tests still pass);
   `jarvis_screen.py`: session states, pause rules, caps, outside-text
   label, status limited to on/off and counts, the Stop-everything stopper -
   tested with made-up program and site names that must never appear outside
   the answer.
2. The router keeps screen turns local; the chat route accepts
   `screen_text`; a preflight "screen" check.
3. The Windows readers (password boxes, capture protection, window text) -
   testable only on the owner's PC.
4. Desktop "Look at this" (`cargo clippy --target x86_64-pc-windows-msvc`,
   a `tests/look.mjs` harness).
5. The desktop Watch badge, tray row and phrases.
6. The second-card picture route, off until the card is measured.
7. Phone "Look at this": a JVM test flattening a made-up screen tree (drops
   password fields, skips "Never look at" apps).
8. Phone Watch - needs a real phone.
9. The feature audit, `check_parity.py`, JARVIS-API §62, ARCHITECTURE §8
   and §10.

## The owner's answers (2026-09-28)

- **Chat history:** the question and Jarvis's answer are kept like any
  chat; the picture and the screen's words never are.
- **Read aloud:** yes, unless a sensitive fact was used or the strict
  hands-free setting says otherwise. `read_screen` joins the read-aloud list
  (`private-aloud-cases.json`, both apps) as a named exception.
- **Under "Only trust the talk button"** (2026-09-28): a "Hey Jarvis"
  turn's answer about the screen stays on screen; the voice setting
  "Answers about your screen after "Hey Jarvis"" (`hands_free_screen`, in
  both apps, off by default; on is a card, off is immediate) lets it be
  read aloud even then. Built: the setting, the utterance reply's
  `screen_aloud` and both apps' rule (JARVIS-API §16, §62.7).

## 9. Questions for the owner (answered above)

1. **Should Jarvis's answers about the screen go into chat history?** (The
   picture and the screen's words never do.)
   - Yes: keep the question and answer, like any chat (recommended)
   - No: every screen question is a temporary chat
2. **Should answers about the screen be read aloud?** Today a reading tool
   keeps an answer on screen only.
   - Read them aloud, unless a sensitive fact or the strict hands-free
     setting says otherwise (recommended)
   - Keep them on screen

## 10. Screen safety (the owner's "all three", 2026-09-29; API 62.13)

Three changes, after checking a scouting report against the real code:

1. **Secrets are blacked out before anything reads the picture.** The words
   the text reader finds, WITH where each one is, are searched for keys,
   tokens, passwords, card numbers (they must pass the card check digit),
   crypto wallets, IBANs, email and IP addresses (gitleaks's and Presidio's
   patterns, MIT). Every word that overlaps one is hidden whole - a secret over
   several lines on every line - as `[hidden]` in the words and as SOLID BLACK
   (never blur) in a picture; the picture a picture model may be shown is only
   ever the cleaned one. Fail closed: a picture that cannot be checked is not
   handed on. It covers the PC's screen and the phone's screen text and
   screenshot (cleaned on the PC). Said plainly: a password shown with a
   show-password eye has no shape a pattern can see.
2. **The text reader runs inside Jarvis** (pywinrt, no PowerShell per
   picture) and gives each word's position; PowerShell remains as the
   fallback.
3. **Windows on the "Never look at" list are painted black even when they are
   not in front** (the design's risk "windows behind it are in the picture too"
   is closed), together with private browser windows, Jarvis's own windows,
   the lock screen and admin prompts; a browser behind the front one on a
   listed site, or whose site cannot be read, too. No window list, no picture.
   The window-text walk skips off-screen controls and has a quarter-second
   budget. **Pause added:** the browser in front is a private window.
   Ten streaming-video sites join the built-in list.

Sources: Android MediaProjection and app screen sharing docs;
VoiceInteractionSession reference; LiquidAI LFM2.5-VL-3B-GGUF; Ollama issue
#13637; a Copilot Vision summary.
