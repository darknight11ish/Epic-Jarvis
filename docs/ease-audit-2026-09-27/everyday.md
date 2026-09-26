# Ease-of-use audit: everyday use and understanding (a newcomer's first day)

Lens: the Jarvis bar, widget, tray, HUD, Brain and Faces on the desktop, and
Home, voice, cards, Brain and Help on the phone. The questions: can someone new
tell what Jarvis is doing, why it asks, what a card or a face colour means, how
to stop it, what it remembers, whether it is online, and what they can say to it?

How it was checked: I read the source at commit `ad44732`, read-only. I also
rendered four desktop windows (bar, widget, Brain, onboarding) in a throwaway
copy with the repo's own test kit (`tests/uikit.mjs`), deleted afterwards. The
screenshots are in `everyday-shots/` next to this file. Nothing was run on
Windows or on a phone. Paths: `desk/` = `jarvis-desktop/src/`, `rust/` =
`jarvis-desktop/src-tauri/src/`, `phone/` =
`jarvis-client/app/src/main/java/com/jarvis/client/`.

---

## In short

1. **Nothing tells a newcomer what they can say.** Jarvis understands about 12 kinds of instant command (timers, alarms, reminders, lists, snooze, "cancel that", focus, "tell me when", briefing, "what did I miss?", web-search choice, "what can you reach?"). Neither app lists them. The feasibility audit approved "Things you can say" (I116) as **Now**, and it has not been built.
2. **On the phone, the way around is hidden.** The row with Brain, Inbox, Appearance and Help is **hidden by default**. Voice training, "hey Jarvis", the voice check, voices and Security all sit inside "Platform checks", which you reach by tapping the status line. The talk button is missing until your voice is trained, and Home does not say why.
3. **Reviewing the past is thin.** Chat history exists in both apps, but you cannot search it or carry on an old chat. There is **no plain list of what Jarvis did or what you approved or denied**. The only log on screen is the "Ledger", which shows hashes and sits under Advanced.
4. **The desktop uses too many names and windows.** The bar has 4 names ("Jarvis bar", "Spotlight", "Quickbar", "Summon Jarvis"). There are 7 windows plus the tray, and two different places to chat. The Faces window is a developer's kit, and one of its sentences is now wrong.
5. **Jargon on everyday screens**: about 60 uses of words a newcomer would not know (table in section 3). The worst are "Stale", "Linked", "Faculties", "Long Fuse jobs", "Core / Ollama / LiteLLM", "VRAM", "route badge", "State of mind" and "Platform checks".
6. **The face and tray have 8 states, and onboarding teaches 3.** There is no legend anywhere. Quiet shows the Standby colour.
7. **Help answers safety questions, not everyday ones.** There are 27 questions across both apps. None of them says what you can ask, what the colours mean, how to see what Jarvis did, or how to undo something. On the desktop, Help sits at section 17 of 21 in Settings, and the tray has no Help row.
8. **What already works well:** approval cards (one wording on every screen, with an honest "Reversible · stays on this machine" line), offline messages that come with a Reconnect button, several ways to stop, and plain words on the Memory page.

---

## 1. What works (keep it)

- **Approval cards are the clearest thing in the product.** Every screen shows the same card: "Needs your OK", a plain title, Deny on the left and Approve on the right (`desk/card-words.js:27-33`). There is a risk line in words: "Reversible / Hard to undo / No undo · stays on / leaves this machine — why" (`desk/jarvis-link.js:1207-1216`). Beside the buttons it says "Nothing runs until you decide." (`desk/index.html` approval-reassure). When you ask by voice, Jarvis says where the card is: "I need your OK for that. There's a card on your screen." (`desk/card-words.js:43-48`).
- **Online or not, in words.** "Offline — …", "Connecting to Jarvis… Approving is blocked until it connects." (`desk/jarvis-link.js:373-406`). The bar and the widget each have a Reconnect button (`desk/index.html:375-380`, `desk/widget.html:121-124`). On the phone, you tap the status line to find out why (`phone/ui/screens/HomeScreen.kt:1156-1161`).
- **Stopping.** The bar has a Stop button while it answers (`desk/index.html:591`). There is a "Stop everything" tray row, never greyed out (`rust/tray.rs:229-240`), a hotkey Alt+Shift+X, and a button on the phone while Jarvis is busy. Continuity-audit finding 2 (no mouse way to stop on the PC) is now fixed by the tray row.
- **A slow first answer is explained**: "Waking up the model - the first answer after standby takes a little longer." (`desk/plain-errors.js:151`).
- **The Memory page speaks plainly.** It has real empty states ("Nothing has been saved automatically yet."), and it warns that deleting a chat does not forget the facts learned from it (render of `brain.html`, Memory).
- **The desktop Brain was trimmed** to 4 everyday tabs, with Galaxy, Live, Trust and Watch under "Advanced" (`desk/brain.html:84-121`).
- **Brain → Work is the one place that teaches commands**, with example sentences for focus sessions, "tell me when" and lists (`desk/brain.html:441, 453, 462`). That is the right idea, in the wrong place (see 2.1).
- **Fixed since the earlier audits** (checked): onboarding now uses the real state colours (`desk/onboarding.html:86-88`, UI audit #4a). The "Hide memory lists" wording is shared and correct (`desk/security-settings.js:151-154`, continuity #1). The phone screen is titled "Brain" (`phone/ui/screens/BrainScreen.kt:246`). `CHANGELOG.md` exists.

---

## 2. What is hard, ranked by how much it hurts a newcomer

### 2.1 No "things you can say" (hurts most)

- **What exists:** `backend/jarvis_quick.py:619-806` understands these without the AI model: timer set, cancel, pause, add time and status; alarm set, cancel and list; briefing; web-search choice; "what can you reach?"; "tell me when"; reminders; to-do add, list, done and remove; named lists; "what did I miss?"; snooze; "cancel that"; focus (about 9 phrasings). That is **about 12 families and 30+ phrasings**.
- **What the newcomer sees:**
  - The empty bar shows **10 rows of shortcut keys and `#` tags**, and not one example sentence (render `bar-first-run.png`; `desk/index.html:296-345`).
  - Phone Home shows the face and a box that says "Ask Jarvis" (`HomeScreen.kt:2264`).
  - A search for "Things you can say", "try saying", "you can say" and "try asking" across both apps found **no matches**.
- **Why it matters:** the instant commands are the fastest and most reliable part of Jarvis. They work even when the model is asleep. A newcomer will only find them by accident.
- **Fix (M, both apps):** build I116 as already approved. It is a short list served by the PC, grouped by kind, and tapping a line fills the box but never sends. Show it:
  - in the empty bar, instead of most of the shortcut rows;
  - under "Ask Jarvis" on an empty phone Home, as one quiet line "What can I say?" that opens the list;
  - in Help on both apps.

  One source means both apps stay in step (the `*-cases.json` pattern).

### 2.2 The phone hides its own map

- **The navigation row is hidden by default.** `navAlwaysShown` defaults to `false` (`phone/data/AppearanceStore.kt:644`, `HomeScreen.kt:286, 599-600`). You open it by swiping down on the status line, or with a 14×8 dp chevron (`HomeScreen.kt:1136-1143, 1210-1245`). Until then, Brain, Inbox, Appearance and Help are out of sight.
- **Voice and security live in "Platform checks".** Train my voice, the voice check, Voices and Security are all opened from the Checks screen (`phone/MainActivity.kt:1336-1359`). Its title is "Platform checks — What this phone will and will not allow" (`ReadinessScreen.kt:197`). You reach it by tapping the status line.
- **The talk button just isn't there** until your voice is trained (`HomeScreen.kt:2317`, `voiceOffered`). The reason ("Jarvis has not learned your voice yet. Use Train my voice on the Checks screen.", `backend/jarvis_speech.py:1028-1030`) is shown only on the Checks screen (`ReadinessScreen.kt:445-448`), never on Home. The FAQ has to explain it ("Where is the talk button?").
- **Counts:**
  - Turning on "hey Jarvis" takes 1 hidden tap, then a button, then a card on the PC, then "Listen on this phone" (`FaqScreen.kt` "How do I use hey Jarvis?").
  - Seeing a past chat takes 1 hidden gesture, then Brain, then a scroll past **at least 20 sections**, then History. Twenty sections render before History whatever state the phone is in (`BrainScreen.kt:304-574`). Web search, "What asks first", manner and hardware all come before memory.
- **Fixes:**
  - (S) Show the nav row by default, and keep hiding it as an Appearance option.
  - (S) Where the mic would be, show one quiet line: "Talk: teach Jarvis your voice first →", which opens Train my voice.
  - (S) Rename "Platform checks" to "Checks and setup".
  - (L) The phone Settings screen from UI audit #14, still not built.

### 2.3 "What did Jarvis do, and what did I say yes to?" has no answer

- **Chat history:**
  - Both apps have it, with a plain list, device tags and a "read outside text" mark (`desk/history-view.js`, `phone/ui/screens/HistoryScreen.kt`).
  - **No search** in either app. A grep of both for search or filter in history found nothing.
  - **No "carry on this conversation"**: a transcript is read-only (JARVIS-API §18.4).
- **Decisions:**
  - No list of past cards (approved, denied or timed out) in either app. A grep for "recently decided", "approval history", "activity log" and "What Jarvis did" found nothing.
  - The only log on screen is Brain → Advanced → Trust → **Ledger**: "Chain status only — entry count, the last verified point, the anchors" (`desk/brain.html:523-527`). It shows "Head", "Head sequence" and "Anchors" (`desk/brain.js:4342-4349`). That tells a newcomer nothing.
- **Undo** has two homes. On the desktop it is Brain → Work → "Undo shelf" (`desk/brain.html:497-505`, with "before-images" in its note). On the phone it is Inbox → "The undo shelf" (`InboxScreen.kt:153`).
- **Settings changes:** no record of what you changed or when.
- **Fixes:**
  - (M-L, backend + both apps) **An "Activity" list**: one line per card, giving its title (already written to be safe on a lock screen, JARVIS-API §3), when, which device, and Approved / Denied / Timed out, plus the Undo button when there is one. It uses the same card words, so nothing private is added. It would take over from the Undo shelf as the one home for "what happened".
  - (M) Word search in History, run on the PC. Before building it, check this against the dated decision "Searching the owner's own past chat words waits" (CLAUDE.md, 2026-09-26). That decision is about Jarvis's memory recalling old chats. A search box the owner types into may be a different thing, but it is the **owner's call**.
  - (S) Rename "Undo shelf" to "Put things back", and drop "before-images" from its note.

### 2.4 Too many names, too many windows (desktop)

- **The bar has 4 names:**
  - "Jarvis bar" (onboarding, cards, history tags: `desk/email-sending.js:37-38`, `desk/history-view.js:53`);
  - **"Show or hide Spotlight"** in the tray (`rust/tray.rs:258`);
  - **"Quickbar unavailable"** in notifications (`rust/tray.rs:1079, 1128`);
  - "Summon Jarvis" in Settings → Shortcuts (`desk/settings.html:298`).

  INSTALL.md says "spotlight bar" (`docs/INSTALL.md:28`).
- **7 windows plus the tray:** bar, widget, HUD, Brain, Settings, Faces and onboarding. The tray menu has **21 rows** (`rust/tray.rs:303-340`).
- **Two places to chat:** the bar, and the HUD ("Speak, or type here…", `desk/jarvis_hud.html:586`). A newcomer cannot tell which one to use.
- **The widget's expanded view** is a face, the numbers VRAM, CPU and GPU, and a note box (render `widget-expanded.png`; `desk/widget.html:109-200`). It has no way to ask Jarvis anything. In my render, the status badge was cut to "OFFLI…" at 340 px. That was the test kit's fixture, not checked on Windows.
- **The Faces window** is titled "Jarvis Reactor Kit". It is headed "20 faces · 50 colours · 12 patterns · one spec, two renderers", mentions Compose and webview, has export tabs for "spec.json / Kotlin / TypeScript", and its footer is about WebGL and "sub-stepped" (`desk/faces.html:116-118, 177-182, 186`).
- **One sentence there is now false:** "A chosen FACE applies on the phone: nothing on this desktop draws one yet." (`desk/faces.html:152-153`). The widget draws the face (`desk/widget.html:109-114`, `desk/widget.js:399` loads `faces.html?mode=display`).
- **Fixes:**
  - (S) Use one name, "Jarvis bar", everywhere. That means the tray row, the two notifications, the Settings row and INSTALL.md.
  - (S) Retitle Faces to "Choose Jarvis's face", put the export box and the frame-time numbers behind "Details" (UI audit #20 asked for the same), and fix the false sentence.
  - (S) Rename the tray row "Show the HUD window" to "Big screen view (HUD)", or say in its tooltip what the window is for.

### 2.5 Jargon shown on everyday screens

**How I counted.** I used a fixed list of about 60 terms, matched only against visible text: HTML with comments, scripts and styles removed, and string literals in the Rust and Kotlin files. This is a rough count: text drawn by JavaScript at run time is only partly included. The script is `jargon.py`, next to this file.

| Screen | Distinct jargon words | Uses | Examples |
|---|---|---|---|
| Desktop Brain (static HTML) | 16 | 19 | Faculties, Compute, Ledger, Content risk, rush latch, **Long Fuse jobs**, capability set, digest, before-images, Undo shelf, payload |
| Desktop Settings | 8 | 49 | token ×15, Ollama ×8, backend ×7, Tailscale ×7, Meshnet ×6 (mostly setup, so fair there) |
| Tray menu (Rust) | 7 | 13 | "Reconnect the event stream", "Backend: not supervised", "Stop the backend (pid N)", digest, Spotlight, Quickbar |
| Faces window | 7 | 7 | spec.json, Kotlin, TypeScript, renderer, WebGL |
| HUD | 5 | 5 | Telemetry, tier, token |
| Widget | 4 | 5 | VRAM, CPU, GPU, Core |
| Jarvis bar | 4 | 4 | Core, Ollama, LiteLLM (footer, `desk/index.html:654-657`), "route badge" (the first sentence a new owner reads, `desk/index.html:359-363`) |
| Phone Brain | 16 | 19 | Attention budget, interruption budget, Banked, tier, rush latch, Compute, VRAM, **State of mind** |
| Phone Home | 3 | 5 | "Stale — reconnecting", "Linked" ×3, "State of mind →" |
| Desktop onboarding | 0 | 0 | good |

On both apps, "Stale — reconnecting" and "Linked" are the words for online state (`desk/jarvis-link.js:400-406`, `phone/ui/screens/HomeScreen.kt:1090-1101`).

**Fix (S, both apps), one wording pass:**

| Now | Change to |
|---|---|
| Linked | Connected |
| Stale — reconnecting | Catching up… |
| Faculties | Models and PC |
| Long Fuse jobs | Background jobs |
| digest | things waiting to be told |
| State of mind | drop it |
| route badge | the Local / Cloud label |
| Reconnect the event stream | Reconnect to Jarvis |

The shared-words tests (`*-cases.json`) keep the two apps in step.

### 2.6 Face and tray colours: 8 states, 3 explained

- **8 states in the spec:** idle, listening, thinking, speaking, "waiting on you", standby, error, banked (`desk/jarvis-visual-spec.json` `states`).
- **The tray shows all 8** (`rust/tray.rs:403-429`). Onboarding explains only resting, thinking and waiting (`desk/onboarding.html:137-139`).
- **"Banked"** means "things are waiting and Jarvis won't say them out loud": dim and still, with notches. It is explained only inside the phone's Brain text (`BrainScreen.kt:1096`).
- **Quiet shows the Standby colour** (`rust/tray.rs:426`). A newcomer who chose Quiet would read it as asleep.
- I found **no legend** in either app outside the Faces editor's state chips. If the owner recolours a state in Faces, the onboarding picture no longer matches.
- **Fix (S, both apps):** a small "What the colours mean" card in Help. Draw it from the live spec with the owner's own colours (8 rows, one line each), and link it from the Faces window. Also add a second word to the tray tooltip when it is banked ("… · 3 waiting quietly").

### 2.7 Help answers safety, not everyday questions

- **Desktop:** 11 questions (`desk/settings.html:1007-1150`). They sit at section 17 of 21 in Settings (`settings.html:998`), and the tray has **no Help row** (`rust/tray.rs:303-340`).
- **Phone:** 16 questions (`phone/ui/screens/FaqScreen.kt`). It is reachable only through the hidden nav row (2.2).
- **Of the 27, none covers:** what can I ask; what do the colours mean; how do I see what Jarvis did or undo it; how do I find an old chat; what is a temporary chat. About 14 of the 27 are about privacy or security.
- **Small errors found:**
  - The desktop answer "What is the difference between Quiet and Standby?" says the first answer after Standby takes "five to fifteen seconds". A few lines later it says the first answer after waking "is quick" (`settings.html:1106-1126`). Both are true in different cases, but a newcomer reads a contradiction.
  - "Jarvis suddenly got slow" points to "Brain → Faculties → Models" (`settings.html:1094-1101`), which is jargon again.
- **Fixes:**
  - (S) Add a tray row "Help…" that opens Settings at the FAQ.
  - (S) Add 5 shared everyday questions to both FAQs.
  - (S) Reword the Quiet/Standby answer so it separates "asked while on Standby" from "woken first".

### 2.8 First run teaches safety, not use

- **Desktop onboarding** is 3 screens: tray, approvals, memory (`desk/onboarding.html:131-176`). The words are good. But it never says how to ask something (Alt+Space appears only in brackets on screen 2), how to talk, how to stop, or one thing to try. Esc skips it for good (`onboarding.html:221-223`), and there is no "show the tour again" link.
- **Phone:** no welcome at all. The pairing form is the first screen (`PairingScreen.kt:122-127`), and grep finds no onboarding code. UI audit #16 is still open.
- **Fixes:**
  - (S) Add a 4th desktop screen, "Try it". It would give Alt+Space to open the bar, three example lines ("set a timer for 10 minutes", "what did I miss?", "remember my sister likes jazz"), and Alt+Shift+X to stop everything. Raise `ONBOARDING_VERSION` (`rust/commands.rs:601`).
  - (S) Add a "Show the welcome again" link in Settings → About.
  - (S) Build UI audit #16 on the phone: one still picture and one sentence above the pairing form.

### 2.9 Smaller things

- **The Memory card has three learning controls** that sound alike: a "Stop learning" button (background learning, `desk/brain.js:1683-1725`), a "Learn automatically" box, and an "Also remember sensitive topics automatically" box (render `brain-memory.png`). **Fix (S):** "Pause background learning", with one line saying what it pauses that the box below does not.
- **The bar has 4 icon-only buttons:** mic, "hey Jarvis", temporary chat (a ghost icon) and pin. They are explained only by tooltips (`desk/index.html:118-183`). **Fix (S):** a word under or beside the temporary-chat and "hey Jarvis" icons the first few times, or labels that show on hover and focus.
- **The desktop mic before voice training:** not checked, so I cannot say whether the desktop hides it like the phone does.

---

## 3. Still unfixed from earlier audits (checked today)

| Earlier item | Status | Evidence |
|---|---|---|
| UI #9: group the phone Brain | Rename done; grouping not done; "State of mind" still shown | `BrainScreen.kt:246`, `HomeScreen.kt:1568`, ≥20 sections before History |
| UI #13: jump list in desktop Settings | Not done | 21 `<h2>` sections, no nav in `settings.html` |
| UI #14: phone Settings screen | Not done | voice and security still under Platform checks (`MainActivity.kt:1336-1359`) |
| UI #16: phone welcome | Not done | no onboarding code in `phone/` |
| UI #18: drop Core/Ollama/LiteLLM dots | Not done | `desk/index.html:654-657` |
| UI #19: shorter shortcut list on the bar | Not done | 10 rows in the render |
| UI #20: hide the Faces window's developer numbers | Not done | `desk/faces.html:155-157` |
| Feasibility I116: "Things you can say" (verdict: Now) | Not built | no matches in either app |
| Continuity #2: a mouse way to Stop everything on the PC | Fixed in the tray, still no button in the bar | `rust/tray.rs:233-240` |
| Professionalism #15: Brain/Mind naming | Done | `BrainScreen.kt:246` |

---

## 4. Fixes, in the order I would do them

| # | Fix | App | Size |
|---|---|---|---|
| 1 | "Things you can say" (I116), served by the PC, in the empty bar, on phone Home and in Help | both | M |
| 2 | Phone: show the nav row by default; add "Teach Jarvis your voice first →" where the mic would be; rename "Platform checks" | phone | S |
| 3 | Wording pass: Connected / Catching up / Models and PC / Background jobs; drop "State of mind" and "route badge" | both | S |
| 4 | One name for the bar ("Jarvis bar") in the tray, notifications, Settings and INSTALL.md; a Faces title in plain words, with its false sentence fixed | desktop | S |
| 5 | "What the colours mean" in Help, drawn from the live spec; tray tooltip says "waiting quietly" | both | S |
| 6 | Tray "Help…" row, plus 5 everyday FAQ questions in both apps | both | S |
| 7 | Onboarding screen 4, "Try it", plus "Show the welcome again"; phone welcome (UI #16) | both | S |
| 8 | An "Activity" list of past cards (title, when, device, outcome, Undo), as one home that absorbs the Undo shelf | backend + both | M-L |
| 9 | History search (the owner's call first, see 2.3) and "carry on this chat" | backend + both | M |
| 10 | Phone Settings screen (UI #14) | phone | L |

Every item keeps the five rules. Nothing approves anything, nothing new leaves
the PC, and the Activity list reuses card titles that are already safe for a
lock screen. Items 1 and 8 are new features, so each needs its own follow-up
audit under CLAUDE.md's standing rule.
