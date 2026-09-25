# Creativity audit, lens 4: the experience (2026-09-25)

How Jarvis feels to use on the PC, on the phone and by voice. Read-only: nothing in the repo was changed.

**How far to trust this.** I could not run either app. I read the code and the tests, and I ran the desktop's screenshot harness (`node jarvis-desktop/tests/shots.mjs`, 11 scenes) and looked at the pictures. Then I restored `tests/shots/` with `git checkout`. The harness uses made-up sample data (`tests/uikit.mjs`), so a screenshot shows how the screen *draws*, not what the real backend sends. Timings are estimates unless a file is quoted. Guesses are marked **(guess)**. File paths are relative to the repo root. `…/client/` means `jarvis-client/app/src/main/java/com/jarvis/client/`.

I tried not to repeat the three earlier UI audits (`docs/UI-AUDIT-2026-09-14/18/23.md`) or the competitor audits. I spot-checked two of 09-23's Phase 1 items and both are in the code now: re-pairing (`…/client/ui/screens/PairingScreen.kt:126`, "Change desktop or token") and the connection words on Home (`HomeScreen.kt:1012`).

---

## 0. The short version

1. **The approval card, the most important screen, speaks three dialects.** The Jarvis bar shows the raw code name ("JARVIS WANTS TO / `switch_model`"). The widget says "APPROVAL REQUIRED" and shows `send_email`. The phone says "Jarvis wants to switch model". **Approve and Deny are in opposite places:** Deny comes first in the Jarvis bar, and Approve comes first in the widget and on the phone. The server's own titles turn code names into broken English: "Jarvis wants to learning enable", "Jarvis wants to models create".
2. **Voice goes silent exactly when it matters.** If a spoken question needs a card, Jarvis says nothing. You may be across the room while a card waits about 3 minutes and then expires. Also, when a reminder or a repeating alarm is set by voice, Jarvis says "Nothing is set up until you *say yes*". Saying "yes" out loud does nothing, because only a tap on the card approves.
3. **"What did Jarvis do today?" has no answer in either app.** The only record is "Ledger" / "Audit chain". It shows hash codes and entry counts, not events, and on the PC it is hidden behind Advanced.
4. **Web-search cards will be the most common card, maybe on nearly every search.** Pinned "Always keep in mind" facts are added to *every* question. A turn that has any recalled memory makes a search ask first. So once you pin one fact, every web search in a normal chat raises a card. Settings describes this as asking "only when private things could slip in".
5. **Settings are scattered on the phone and very long on the PC.** Phone voice settings live under "Checks". Briefing, web search and learning live in the middle of a ~25-section "Mind" scroll. The PC's Settings is one page of ~17 cards with no contents list. The same place is called "Brain" on the PC and "Mind" on the phone.
6. **Recovery often shows computer talk.** "Cannot reach the desktop: <raw error>", "The desktop answered 503", "Streaming · 42 chunks · 3.4s", "tier auto → ask", "from tool:browser_navigate", "Core / Ollama / LiteLLM".
7. **Alarms are just notifications.** On the PC an alarm is one ordinary Windows notification (`brain/schedule.rs:338`). On the phone it arrives only if the phone is connected to the PC at that moment. Nothing rings until you stop it, and nothing is said aloud.

What is already good, and should be kept: a clear "Nothing runs until you decide." on every card; "Used 2 memories" with Forget under an answer; answers without the AI model for timers; honest offline/stale words that block approving; a fixed "It's on your screen." for private answers; one scheduler for everything.

---

## 1. The main journeys, step by step

Steps are counted from the code. PC = desktop app, Phone = `jarvis-client`.

| Journey | PC | Phone | Where it hurts |
|---|---|---|---|
| **Ask by voice** | Alt+Space, then hold Space or the mic, speak, let go: **2 steps**. Hands-free: say "Hey Jarvis" once listening is switched on in the bar. | Open the app (plus fingerprint if App lock is on), hold the talk button, speak, let go: **2–3 steps**. The long-press-home / assist gesture opens the app but **does not start listening** (`assistant/JarvisVoiceInteractionSession.kt:53-67`). | Waiting: "Checking it's you…" → "Thinking…" → speech. The earlier audit estimated 2.5–4 s before the first word (`COMPETITORS-COMMERCIAL` §2); I did not measure it. If the model is loading after standby, the screen still just says "Thinking…" (`main.js:2102-2107`). "One moment." plays only when a tool starts (`voice-flow.js:28-33`), so a slow model with no tool means silence. |
| **Ask by typing** | Alt+Space, type, Enter: **2 steps**. | Open, tap the field, type, send: **3–4 steps**. | The PC answer card's header says "Streaming" and "N chunks · 3.4s" (`main.js:2135,2145`). That is developer information. |
| **Approve a card on the PC** | Heavy card: a Windows notification (Deny only). Alt+Space → read → Approve (+ Windows Hello if set): **2–3 steps**. | – | A "normal" card (reversible, stays on the PC, such as most settings) **gets no notification at all**. It only changes the tray icon (`stream.rs:1011`). It expires after about 3 minutes (180 s is what the tests and the phone assume, `backend/test_approval_contract.py:61`; the gate itself is on your PC). |
| **Approve a card on the phone** | – | Notification (heavy only) → tap → app (fingerprint if locked) → Home makes room → Approve (fingerprint if risky): **2–4 taps**. | Good. Swipe to approve is there too. Approve is on the left here but on the right in the PC's Jarvis bar. |
| **Set a timer** | Say or type "set a timer for 10 minutes": **1 step**, answered without the AI model, with a "Done" line. | Same. | When it goes off: an ordinary notification on the PC (`brain/schedule.rs:338`). On the phone, a notification only while the phone is connected to the PC (`service/ScheduleNotifier.kt` header: "THE PC IS THE CLOCK"). Not spoken. Nothing rings until you stop it. |
| **Set up the morning briefing** | **By words:** "brief me every weekday at 7" → card with the next 3 times → Approve: **2 steps**, the best path. **By Settings:** tray → Settings → scroll to the 8th card → time and days → Set up → "Asked. Your PC shows an approval card…" (`briefing.js:61`), **but no notification and no link to it** → Alt+Space → Approve: **~7 steps**. | Mind → scroll to Morning briefing (4th section) → set → then find the card on Home. `BriefingPlate.kt` has no "open the card" link (only the Hardware, Big model and Second card plates have one). | The briefing arrives as "your morning briefing is ready". You open Brain → Work to read it. It is spoken only if you ask. |
| **Choose a web search provider** | Settings → Web search (the 12th card) → pick → Test. Keys for Exa, Tavily and Brave are entered here only. | Mind → Web search (5th section) → pick. | The default, SearXNG, needs Docker running on the PC. A beginner's first search will probably fail **(guess)**. Jarvis then offers: *"Switch web search to DuckDuckGo? Say 'use DuckDuckGo for web search'"* (`backend/jarvis_search.py:484-488`). A plain "yes" does nothing. |
| **Find and forget a fact** | Brain → Memory (opens first) → scroll "Saved automatically" or "What Jarvis knows about you". **No search box** (the only search is the graph's). Then Forget → "are you sure?": **4 steps + scanning**. | Swipe open the nav → Mind → scroll past ~14 sections (Doing, Steps, Coming up, Briefing, Web search, Model, Hardware, Second card, Big model, Deep questions, Attention budget, Background work, Compute, Memory counts) → "Saved automatically" (Show + fingerprint if hidden) → "Load older…" → Forget → confirm: **6–8 taps + scrolling**. | You cannot say "forget that I…". There is no quick command for it (`backend/jarvis_quick.py` intents) and no chat tool. The fastest path is "Used N memories" under an answer, which works well. |
| **See what Jarvis did today** | Brain → Advanced → Trust → Ledger: "Head", "Head sequence", "Anchors" (`brain.js:3988-4018`). The step list (Live) is also behind Advanced. | Mind → "Audit chain – Entry count and last verified point" (`BrainScreen.kt:599`). | **Nothing in plain words:** no list of cards approved or denied, searches sent, notes written, facts saved or timers that went off. |

**Summary.** Speaking or typing a request is fast. Getting to the right *place* is slow. Settings that raise a card leave you to hunt for it. Voice falls silent on the phone and PC as soon as a card is involved.

---

## 2. Card fatigue: how many cards a normal day raises

**The rules, from the code:**
- **Web search** asks first if any of these happened: saved memories were recalled for this question, *including pinned facts, which are added to every question* (`backend/memory-profile.patch` ~lines 82-92; `backend/jarvis_agent.py:1038-1039` "pinned facts too"); the conversation has read outside text, *including an earlier web search* (`jarvis_agent.py:1036-1037`); or the message was pasted or shared. So a second search in the same chat always asks.
- **Notes** (Obsidian, Logseq, Joplin) written by the model after outside text: one card each.
- **Home Assistant:** one card per action on **one** device (`backend/jarvis_home.py:26-32`, `plan_service(domain, service, entity_id)`). "Turn off the kitchen and living room lights" = 2 cards.
- **Anything that repeats:** one card, once. Timers and one-off reminders: none.
- **Email:** there is no sending. Reading is tier `auto`, so no card (`jarvis_email.py` docstring). Calendar reads: `auto`.
- **Settings that loosen something** (learning, history, "Hey Jarvis", voices, the stricter voice options, the second card and more): one card each.
- **At most 5 cards per answer** (`CARDS_PER_TURN`). After that, a refusal.

**Estimate for a normal day (guess, from these rules):**

| Day | Searches | Notes after reading | Home Assistant | Repeats / settings | Total |
|---|---|---|---|---|---|
| Light, no smart home | 3–6 cards (nearly every search, once memory is used) | 0–2 | 0 | 0–1 | **~4–9** |
| With lights and plugs by voice | 3–6 | 0–2 | 5–10 | 0–1 | **~10–18** |
| A setup day (first week) | – | – | – | 10–20 settings cards | **10–20+** |

The rule "one action, one decision" is the product's backbone and should stay. The problem is not the number of decisions. It is that each one is harder to read than it needs to be, and some turn up where you are not.

**Ways to lower the burden without weakening the rule:**
1. **Say what it is, in words.** Give the server's `notice_for` a small table of plain phrases: "search the web", "turn on automatic learning", "set up a repeating reminder". Show that title on all three card surfaces. Put the one-line *why* ("Because Jarvis recalled a saved fact: 'You live in Leeds'") and the *cost of no* at the top. Reading faster is the biggest relief.
2. **One card for one request with several named devices** (Home Assistant). `ARCHITECTURE.md` §2 already allows "one decision about one bounded set of things, every one of them shown in full". "Kitchen light, living-room light, off" on one card, with every device listed, fits that exactly. This is question 1 below.
3. **Show the cards from one answer together.** "2 cards from this answer", both open on one screen, **each with its own Approve and Deny**. The bar already says "1 of 3" (`main.js:1324-1328`). Seeing them together stops the "approve, next appears under the cursor" effect the code comments warn about.
4. **Make the search card show its trigger.** Show which recalled fact or earlier read caused the card. Mark any search word that also appears in that fact. The owner then sees at a glance "none of my private words are in here", and approves in a second. *(Skipping the card when no words overlap would be a rule change, and a weak one, because the model can paraphrase. I do not recommend it.)*
5. **Bring the card to the person who asked for it.** When you press a button in Settings or Mind that raises a card, add an **"Open the card"** link, and let that one card send a notification even though it is "normal" weight. Otherwise it sits unnoticed and expires.
6. **Voice: say that a card is waiting, but do not approve by voice.** The voice check "cannot tell a recording or a copy from the real voice" (`CLAUDE.md`). A web page read aloud, or a video, could say "yes". Speaking a fixed heads-up is safe: "I need your OK on screen for that: it's a web search."

---

## 3. Personality and voice

**What Jarvis is like today.** The model's instructions are rules only: say what's a guess, never claim an action happened, keep memories private (`backend/jarvis-primary.Modelfile:160-167`, `jarvis_agent.py:2441`). Nothing about manner. Canned lines are plain and good: "It's on your screen." (`private-speech.js:51`), "Added to your to-do list.", "Reminder set for 18:00, in 40 minutes." (`jarvis_quick.py`). Spoken-style answers and starting speech at the first comma are built. "One moment" plays on a tool start. The "I heard you" sound is off by default. Custom voices exist.

**What would make it feel like a capable assistant rather than a tool:**
1. **A short "manner" paragraph** in the model's instructions, the same in both prompts. For example: warm and brief, use the owner's name if one is pinned, acknowledge before acting ("On it."), end with a clear next step, light dry humour at most once in a while. Plus one owner setting: **Plain / Friendly**. Small, and a noticeable change **(guess, an 8B model follows tone instructions loosely)**. Question 2 below.
2. **Say what's happening during the long waits.** "Waking up. About ten seconds." when the model is loading after standby. Today that is silent, "Thinking…". "Searching the web…" when the search starts. These are fixed phrases from the event stream, not the model's words, so they are safe.
3. **Timers and alarms said aloud, in Jarvis's voice:** "Your tea timer's done." This should respect the interruption budget, Quiet and Standby, as spoken interruptions already do. Alarms should keep ringing until dismissed (see §5).
4. **Close the loop after a card.** After Approve: "Done, I've added it." After Deny: "OK, I won't." After it expires: "That request timed out. Ask again if you still want it." Today the answer card just stops.
5. **The face can show more states.** The spec has 8 states (idle, listening, thinking, speaking, approval, standby, error, banked: `jarvis-visual-spec.json`). Two more would make it feel alive and explain waits: **"checking your voice"** (currently shown as thinking) and **"waking up"** (model loading). Small, low-contrast one-off reactions would also help: a soft glint when a fact is saved, a quick settle when a no-model command finishes. They must stay inside the flash limits in `face/Spec.kt` **(design guess, not priced for frame time)**.
6. **Make the assist gesture start listening** (phone). Long-press home should mean "I'm talking now", the way it does for every other assistant. The voice-print check still gets one complete clip, because the phone already ends a turn with Smart Turn.
7. **Let "yes" accept Jarvis's own *offer*.** Examples: "Switch web search to DuckDuckGo?" → "yes". This is an immediate setting and the owner's own words, not an approval card. It must never answer a card.

---

## 4. Clarity and trust

**Does the owner always know what Jarvis is doing, what it read, what it remembered and why it asked?**
- *Remembered:* yes, and this is a real strength. "Jarvis remembered 2 things" and "Used 2 memories" with Forget and Erase.
- *Doing:* partly. The step list exists, but on a separate screen (phone Mind "What Jarvis is doing"; PC Brain → Live, behind Advanced). The answer itself only says "Working…". **Put one live line under the answer:** "Searched the web (SearXNG) · read 5 results · waiting for your OK".
- *Read:* the card's "What shaped this request" says it, in code-ish words ("from tool:browser_navigate", "tier auto → ask", seen in the bar's "raised" block in the screenshot `07-quickbar-everything`).
- *Why it asked:* the server writes good reasons (`WEB_SEARCH_MEMORY` etc., `jarvis_agent.py:1049-1060`). The titles above them are the weak part.
- *Did today:* no (see §1).

**Wording that differs between the two apps** (the standing rule is that wording must match):

| Thing | PC | Phone |
|---|---|---|
| The window or screen for memory and status | **Brain** | **Mind** |
| Card heading | "JARVIS WANTS TO" + `switch_model` (bar, `main.js:1289`); "APPROVAL REQUIRED" + `send_email` (widget, `widget.html:211`) | "Jarvis wants to switch model" (`net/PendingRows.kt:128`) |
| Button order | Bar: **Deny, Approve** (`index.html:559,563`). Widget: Approve, Deny (`widget.html:275`) | **Approve, Deny** (`ApprovalCard.kt:463`) |
| Answer rating | "Was this answer right?" (`index.html:617`) | "Was this right?" (`HomeScreen.kt:1989`) |
| Hands-free choice | "Same as the talk button" | "Same as the talk button (default)" (`voice/StrictVoice.kt:140`) |
| Voice switches | Checkboxes named by the setting | Buttons named by the action ("Stay quiet while I wait", `ReadinessScreen.kt:656`) |
| Where the settings live | Settings (voice, briefing, web search); Brain → Memory (learning) | Checks (voice, security), Mind (briefing, web search, learning), Appearance |

**Words a beginner will not know**, on everyday screens: "Stale — reconnecting" and "The event stream is stale" (`jarvis-link.js:392`, `answer-memory.js:65`); "Tier raised", "tier auto → ask"; "chunks"; "Core · Ollama · LiteLLM" (bar footer); "long-fuse", "gate", "watch" as source labels in the brief; "Banked"; "Faculties", "Galaxy", "Ledger", "Anchors", "Content risk", "Compute"; "The desktop answered 503" (`JarvisRuntime.kt:672`). A suggestion: "Catching up with your PC — nothing can be approved until it does." The continuity test holds both apps to one set of link words (`tests/continuity.mjs`), so change both apps and that test together.

**A sentence that promises something that doesn't work:** "Nothing is set up until you **say yes**" (`jarvis_quick.py:1060,1135`, `briefing.js:56`). By voice, that invites a spoken "yes", which does nothing. Suggested: "…until you approve it on screen."

---

## 5. First run and recovery

| Moment | What happens now | How well it goes |
|---|---|---|
| **First run, PC** | Three explanation screens (tray, approvals, memory) (`onboarding.html`). No steps: nothing checks the backend, trains your voice, pairs the phone or picks a search provider. | Friendly, but it doesn't *get you working*. The competitor audit's "guided first-run checklist" still holds; I'd make it a checklist with a green tick per item. |
| **First run, phone** | Type the desktop's name and a long token by hand (`PairingScreen.kt:144-171`). QR pairing is decided but not built. | The hardest step in the product. Already queued. |
| **Backend not running (PC)** | Red line "Offline — Jarvis is not running at …", a **Reconnect** button, and the words "Settings live in the tray menu" (`index.html:370-375`). | Honest, but the fix, "Start Jarvis", is only in Settings (`settings.js:378`). Put a **Start Jarvis** button in that red line when this PC starts it. |
| **PC off or asleep (phone)** | "Cannot reach the desktop: \<raw error text\>. Check your private network (Tailscale or NordVPN Meshnet) is up on both ends." (`JarvisRuntime.kt:671`) | It shows the raw error and doesn't tell apart "PC off or asleep" (a timeout) from "PC on, Jarvis not running" (connection refused) from "wrong token". Those three need different fixes, and the phone can already tell them apart from the error type **(believed, not tested)**. |
| **Link stale** | Both apps block approving and say so. | Correct and safe; only the word "stale" is jargon. |
| **Model loading after standby** | "Thinking…", no sound. | The longest silent wait in the product **(guess: 5–20 s, from the Modelfile's "~6 second stall" note and model size)**. Say "Waking up…" on screen and in the face. |
| **Search provider down** | A plain sentence and a phrase to say. | Good principle (no silent fallback). Add a tap button "Switch to DuckDuckGo" under the answer, and accept "yes". |
| **Card expired** | The card disappears. | Say so in the answer: "That timed out, nothing was done." |
| **Alarm while PC is fine but phone off the link** | The phone never hears it (by design, the PC is the clock). | "Wake me at 7" can silently fail on the phone. At least say so when the alarm is set: "It will go off on your PC, and on your phone if it's connected." |

---

## 6. Top 10 improvements, ranked by felt difference per effort

| # | Improvement | Where it lands | Size | Rule or card it touches | Both apps? |
|---|---|---|---|---|---|
| 1 | **One plain card everywhere.** A phrase table in `notice_for` (still built only from our own tables, never from `detail`). The Jarvis bar and widget show `notice.title`, not `approval.action`. **One button order** in all three places. The *why* line first. | `backend/approval-notice.patch` (`notice_for`); `jarvis-desktop/src/main.js:1289,1266`; `widget.html:211,275`, `widget.js:549`; `index.html:559-566`; phone already uses the title (`net/PendingRows.kt:128`) | S | The notice contract (ARCHITECTURE §3, rule 3). No new approval path. The order change is muscle memory, so pick once. | Yes. Mostly desktop; the phone gets better titles free. |
| 2 | **Voice says when it's waiting on you, and closes the loop.** A fixed line when a spoken turn hits a card ("I need your OK on screen for that: it's a web search"), and after approve, deny or expiry. Fix "say yes" wording. | `jarvis-desktop/src/main.js` `showWaitStatus` (~2109); `…/client/voice/VoiceSession.kt`; `backend/jarvis_quick.py:1060,1135`; `jarvis-desktop/src/briefing.js:56` | S–M | Approving stays tap-only. Private-answer rules unchanged (fixed words only). | Yes. |
| 3 | **A "Today" page.** A plain timeline: cards approved, denied or expired (by title); searches sent (the words, hidden under "Hide memory lists…" like other private lists); notes filed; facts saved; timers and briefings that went off. "Audit chain" moves under it as "Proof this list wasn't changed". | New backend read route over the gate's audit log, chat log and scheduler; `jarvis-desktop/src/brain.html` (Work or a new Today tab); `…/client/ui/screens/BrainScreen.kt` | M–L | Reads only. Follows App lock and hide rules. Needs a JARVIS-API entry and `check_parity.py`. | Yes. |
| 4 | **Live activity line under the answer** ("Searching the web…", "Waking up…", "Waiting for your OK"), and drop "Streaming / chunks". | `main.js:2102-2145`; `HomeScreen.kt` answer block; the existing `step` events and `: jarvis-status` words; a backend "loading" word is needed for model load **(guess: not emitted today)** | S–M | None. | Yes. |
| 5 | **"Open the card" on every button that raises one**, and a notification for a card the owner just asked for, even if its weight is "normal". | `briefing-settings.js`, `web-search-settings.js`, `voice-panel.js`, `auto-learn.js`; `BriefingPlate.kt`, `WebSearchPlate.kt`, `AutoLearnPlate.kt`, voice screens; `stream.rs:1011` | S | Cards themselves are unchanged. | Yes. |
| 6 | **One card for several named smart-home devices** from one request, every device listed. | `backend/jarvis_home.py` (a plan over a short list, each entity checked as today); card text | M | ARCHITECTURE §2 "one bounded set, shown in full". Stays under the 5-card limit. | Backend. Both apps show it unchanged. |
| 7 | **Settings map.** The phone gets a "Settings" destination with the PC's section names and order (Voice, Jarvis's voice, Morning briefing, Web search, Security, Learning). Mind keeps "what Jarvis knows and is doing". The PC Settings page gets a jump list at the top. One name for Brain/Mind. | `…/client/ui/screens/HomeScreen.kt:1178-1210` (NavRow), `MainActivity.kt`, `ReadinessScreen.kt`, `BrainScreen.kt`; `jarvis-desktop/src/settings.html` | M | "Wording must match" rule. Update the parity check and the FAQ. | Yes. |
| 8 | **Recovery in words, with the fix on the spot.** "Start Jarvis" in the PC's offline line. The phone tells apart PC asleep/off, Jarvis not running and wrong token, with no raw errors or HTTP codes. | `index.html:370-375`, `main.js` offline code; `JarvisRuntime.kt:660-673` | S–M | Rule 4 unchanged (still blocks acting). | Yes. |
| 9 | **Alarms that ring and timers said aloud.** Alarm kind: a looping "alarm" Windows toast until dismissed, and an Android alarm-style notification. Jarvis says "Your 10-minute timer is done" when the interruption budget allows. Be honest when set that the phone rings only if connected. | `jarvis-desktop/src-tauri/src/brain/schedule.rs:305-339` (and `winrt_toast.rs`); `service/ScheduleNotifier.kt`; speech via the existing voice path | M | Interruption budget, Quiet and Standby must still win. Nothing private on the lock screen. | Yes. |
| 10 | **Faster voice start and a bit of personality.** The assist gesture starts listening. "yes" accepts Jarvis's own offers (never cards). A short manner paragraph with a Plain/Friendly setting. "Waking up" and "checking your voice" face states. "Forget that…" shows the matching fact with a Forget button (still the owner's tap and confirm). | `assistant/JarvisVoiceInteractionSession.kt`; `backend/jarvis_quick.py`; `jarvis-primary.Modelfile:160` + `jarvis_agent.py:2441`; `jarvis-visual-spec.json` + both face kits | S each (the face states are M) | Offers only, never approvals. Forget keeps its "are you sure?". Face changes stay inside the flash limits. | Yes (the face on both). |

Already queued elsewhere and not repeated here: QR pairing, the guided first-run checklist, spoken greeting on the first "Hey Jarvis" of the day, and Wake-on-LAN for a sleeping PC.

**One small honesty note for whoever edits it next:** the comment at the top of `jarvis-desktop/src/settings.html` (line ~39) says rarely used things "sit behind a closed 'More options'". There is no such section; only face tuning is folded. It's a comment, not UI, but it's the kind of sentence this project likes to keep true.

---

## 7. Two questions for the owner

**1. Smart-home requests that name several devices.** Today "turn off the kitchen and living-room lights" gives you two cards.
- **One card that lists every device by name, with one Approve** (recommended: your rules already allow one decision about a fully listed set).
- **Keep one card per device.**

**2. Jarvis's manner.** Right now Jarvis is told only rules, nothing about tone.
- **Warm and brief, and uses your name if you've pinned it** (recommended; add a "Plain" choice in settings for when you want it dry).
- **Keep it plain as it is.**
