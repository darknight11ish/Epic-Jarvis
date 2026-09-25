# Competitive audit: Jarvis vs the big commercial assistants (task #75), 2026-09-25

> **Status, 2026-09-25 (added when this report was saved to `docs/`).**
> Built since the report, from its list: timers, reminders and the to-do
> list answered without the AI model (Home Assistant's design, no code
> copied); one shared scheduler; "keep listening after a question" and
> "tell the model it was interrupted" (voice work); tool descriptions 16%
> shorter (not yet OpenClaw's lean mode / Tool Search); "who is my sister"
> (names and aliases). Being built: sleep mode, the morning briefing, and
> Leon's back-off rule. Still open: lean mode / Tool Search, chat-history
> search in the apps, QR pairing with per-device keys, a setup wizard that
> checks a real tool call, testing QwenPaw's Flash models in
> `tools/tool_eval/`, and a second copy of the backend files that live only
> on the owner's PC. The paths to `scratchpad/` below were the auditor's
> temporary clones; they no longer exist.

I only read things. Nothing in /home/user/Epic-Jarvis was edited, committed or checked out. I read it at commit `6d90068`.

## How far to trust this

- **Jarvis side:** checked against the repo files named below.
- **Competitor side:** almost all of it comes from **web search summaries only**. The network proxy blocked every page I tried to open (openai.com, help.openai.com, blog.google, support.google.com, consumerreports.org, wikipedia, sixcolors, windowsforum, datastudios). The only page I actually read was Claude's incognito help page (support.claude.com). So treat each competitor fact as "a search summary says so", not "I checked". Anything I say from general knowledge rather than a search is marked **(unverified)**.
- **Earlier work:** I built on the earlier research (research2/features/REPORT.md, RESEARCH-2026-09-24.md §7) and did not repeat it. COMPARISON.md and PEERS.md cover open-source projects, not these six products, so this report adds the commercial side.

---

## 0. The short answer

- **Jarvis wins on trust.** It asks before acting, you can see and edit its memory, and everything runs locally. It is ahead of all six on privacy and control, and nothing I found suggests they will catch up there.
- **Jarvis loses on everyday usefulness.** A daily user would notice these within a day:
  - there are no timers, alarms or reminders;
  - it cannot look up the web or the weather;
  - it is much less clever, being a small 8B model with a short working memory;
  - it answers out loud more slowly;
  - it is hard to set up;
  - nothing happens on its own ("remind me", "brief me every morning").
- **The competitors' own complaints are Jarvis's openings.** Several of the big assistants got *worse* at basic things when they switched to large AI models:
  - Gemini replacing Google Assistant broke alarms and "lights on";
  - Siri AI's beta has reminder and alarm problems and "something went wrong" network errors;
  - Alexa+ is called "erratic" and "half-completes tasks".

  The lesson for Jarvis: **handle simple commands without the AI model at all**, and be boringly reliable at them.
- **The queue is mostly right, but in the wrong order.** Everyday abilities (timers, reminders, web search) sit *after* all four running lanes. They should come before most of the graphics lane. Details in section 3.

---

## 1. Scorecard

Key: **A** = Jarvis ahead, **E** = even, **B** = Jarvis behind, **NfJ** = not for Jarvis (breaks a rule).

| Area | ChatGPT | Gemini | Claude apps | Copilot | Apple / Siri AI | Alexa+ |
|---|---|---|---|---|---|---|
| Conversation quality | B | B | B | B | B | B |
| Memory: **control and transparency** | A | A | E/A | A | A (unverified) | A |
| Memory: **how much it usefully recalls** | B | B | B | B | B | B |
| Voice | B | B | B | E | E | B |
| Actions / agents | B on ability, A on approval | B / A | B / A | E on your own PC, A on approval | B | B |
| Proactive / time-based | B | B | B | B | B | B |
| Integrations | B | B | B | B | B | B, but A on local smart home |
| Privacy / control | A | A | A | A | A (closest rival) | A |
| Setup / ease | B | B | B | B | B | B |
| Multi-device | B | B | B | B | B | B |
| Reliability | unknown: not measured on the owner's PC (see below) | same | same | same | same | same |

### The evidence, row by row

**Conversation quality: behind everyone.**
- Jarvis runs `qwen3:8b` with a working memory of 16,384 tokens (`backend/jarvis-primary.Modelfile:90`).
- The competitors run very large cloud models. Siri AI runs on a custom Gemini said to have 1.2 trillion parameters (search summary).
- Jarvis's partial answer is the cloud lane, used per question with an approval card (ARCHITECTURE §11), plus the big slow model for "deep questions". The big model is built but **off**, and has not been run on the owner's PC (ARCHITECTURE §10).
- The second card's Qwen 3.5 9B would narrow the gap, but not close it.

**Memory: two different verdicts.**
- *Control: Jarvis is ahead.* Every fact is dated. It learns only from the owner's own words. Every automatically saved fact is listed with Forget and "Erase the words". Sensitive topics wait for a yes. You can ask what it believed on a past date (JARVIS-API §19, ARCHITECTURE §5).
- *ChatGPT, by contrast:* since 9 Sep 2026 its settings panel has a single "Enable memory" switch over a profile it writes in the background. Its own FAQ says the memory summary "will not include everything ChatGPT remembers". Users report personal details surprising them, like an image showing a wedding ring after a divorce. (All search summaries.)
- *Copilot:* has memory you can review and delete (search summary).
- *Claude:* is the closest rival on control.
  - Incognito chats "aren't saved to your chat history", do not read existing memories, and do not create new ones (support.claude.com, **page read**).
  - Each Project has its own memory (search summary).
  - Jarvis has no temporary chat yet; it is queued.
- *Recall: Jarvis is behind.*
  - Jarvis brings only about 5 search-matched facts into each answer, so "owner is vegetarian" is missed when food is not mentioned (RESEARCH-2026-09-24 §3).
  - It never recalls from past chats, on purpose (ARCHITECTURE §5).
  - ChatGPT and Gemini draw on all past chats and on connected apps (search summaries).

**Voice.**
- Jarvis has:
  - a "Hey Jarvis" wake word on the PC and the phone;
  - an owner voice check;
  - Smart Turn (it knows whether you have finished or only paused);
  - interrupting by saying "stop" or "Hey Jarvis" (`jarvis-desktop/src/barge-in.js`, `StopWord.kt`).
- But it takes an estimated 2.5–4 seconds from when you stop talking to its first sound (ARCHITECTURE §11; an estimate, not measured on the owner's PC). Interrupting by simply talking is not in the apps yet (ARCHITECTURE §8).
- ChatGPT Voice and Gemini Live are near-real-time conversations. ChatGPT Voice now reaches email and calendar too (search summaries).
- Their complaint, and Jarvis's opening: ChatGPT's voice mode "keeps interrupting me" when users pause to think (OpenAI community threads, search summary). Jarvis's Smart Turn targets exactly that.
- Copilot ("Hey Copilot", opt-in) and Siri are roughly level on the wake word.
- Jarvis's owner voice check is a real difference: it answers only to the owner's voice.

**Actions and agents.**
- Jarvis can already do these, each behind a card and each off until switched on in the settings file: shell commands, reading files, clicking in Windows programs, controlling the phone over adb (Android's USB/debugging link), and Home Assistant. The browser works only once the second card is in (`backend/jarvis_agent.py:25-35`).
- ChatGPT agent, Gemini Agent / Gemini Intelligence (announced 12 May 2026), Claude computer use and Alexa+ can book things, fill in forms and use websites.
- Gemini and ChatGPT agent **do** ask before important steps: Gemini "will wait for your final confirmation to complete the checkout" (search summary).
- **But ChatGPT's app permission menu includes "Never ask"** (search summary). Jarvis's no-auto-approve rule is a real difference there.
- Copilot Actions works on your local files, so it is level with Jarvis on "your own PC".
- Jarvis is behind on how *capable* and how *reliable* its agent is: an 8B model with 16k of working memory, and the browser needs the second card.

**Proactive and time-based help: behind everyone. The biggest gap.**
- ChatGPT Scheduled Tasks relaunched 17 Jun 2026 with its own "Scheduled" page. It replaced Pulse, which was retired around 1 July. Limits: 3 active tasks on Free, 5 on Plus, 15 on Pro. It asks the user to approve tasks it suggests (search summaries).
- Gemini Spark runs tasks 24/7 "even if your phone and laptop are turned off", on a schedule or when something happens, such as an email arriving. Gemini Live has a "Daily Brief" (search summaries).
- Alexa, Siri and Google have always had timers and alarms.
- Jarvis: the initiative engine has **zero checks** (`backend/rebuilt/jarvis_initiative.py` header, per the earlier report). There are no timers or reminders. The digest has nothing filling it.

**Integrations: behind.**
- Jarvis:
  - reads the calendar (CalDAV) and email (IMAP), but cannot write to either;
  - works with Home Assistant, Obsidian, Logseq and Joplin;
  - searches GitHub;
  - has **no web search and no weather**, excluded on purpose (`jarvis_agent.py:35`);
  - has no music or media control: a search of `jarvis_home.py` and `jarvis_agent.py` for media or volume found nothing.
- ChatGPT "apps" connect to Gmail, Calendar, Drive, Outlook, Slack, GitHub and more. Copilot connects to Outlook, OneDrive, Gmail and Google Calendar (search summaries).
- Jarvis's one lead: smart home runs locally, with a card for locks, alarms and garage doors.

**Privacy and control: ahead of all six.**
- Jarvis:
  - runs locally;
  - opens no public tunnel;
  - uses the cloud only per question, with a card;
  - has no approve-all;
  - blocks approving when the event stream is stale ("held on a stale link", JARVIS-API §19.5).
- Apple is the closest: requests run on the device or in Private Cloud Compute (Apple's own servers, which Apple says do not store or read the data). But heavier requests go there automatically, and since iOS 27 the model behind them is Gemini-based (search summary).
- Alexa+ removed "Do Not Send Voice Recordings", so all audio goes to Amazon's cloud (search summary).
- Windows Recall still "raises security red flags" a year on (GeekWire, search summary).

**Setup and ease: far behind.**
- The competitors are: install the app, sign in, done.
- Jarvis has about 15 places where a beginner gets stuck (earlier report, Part B). The worst are typing a 43-character token into the phone, starting the backend by hand, and a voice install that is five long PowerShell lines.

**Multi-device: behind.**
- Jarvis is one PC plus one phone. When the PC is off or asleep, the phone can do nothing.
- Apple syncs conversations across iPhone, iPad, Mac, Watch and Vision Pro (search summary).
- Alexa and Google have room speakers.

**Reliability: I cannot score it honestly.**
- Much of Jarvis has **never run on the owner's PC**:
  - automatic learning was checked "only against stand-ins" (stand-in copies of the backend files) (JARVIS-API §19.6);
  - the second card and the big model: "Not measured on real cards" / "Not run against a real colibri" (ARCHITECTURE §10);
  - the wake word was tested only on synthetic voices.
- Built that way, local software cannot have a cloud outage or a usage cap. Siri AI has daily usage caps and talk of future paid access (AppleInsider headline, search summary).
- But Jarvis's polish is unproven, and a daily user judges on "did it work".

### Not for Jarvis, and why

| Competitor feature | Why not | Rule |
|---|---|---|
| Memory synced through a company's cloud (ChatGPT, Gemini, Alexa+, Siri's iCloud-synced chats) | Private things must stay on the local model | Rule 1 |
| Gemini Spark running while your devices are off | It needs your email and data sitting in a company's cloud | Rule 1 |
| ChatGPT app permission "Never ask" | That is auto-approve | Rule 4 and ARCHITECTURE invariant 3 |
| Alexa+ purchases, and its "Agentic Ads" | Commercial, and it acts on your money | Rule 5 in spirit; each purchase would need a card, and ads are out |
| Copilot Groups (up to 32 people in one session) | One owner only | ARCHITECTURE §1 |
| Windows Recall-style screen timeline | The same shape as screenpipe, which was rejected; it would capture passwords and email | ARCHITECTURE §11 |
| Phone speech-to-text (Gemini or Apple dictation on the phone) | Standing rule | CLAUDE.md |
| Share links, remote relays | Would need a public tunnel | Rule 2 |
| ChatGPT-style "reference all past chats" | **Not a rule break**, but a decision already taken (history is never used as memory, ARCHITECTURE §5). The owner's call if revisited. | — |

---

## 2. Honest advantages, and the gaps a daily user notices first

### Real advantages, most defensible first

1. **One action, one decision, with no bypass.**
   - Jarvis never auto-approves anything, and approving is blocked when the event stream is stale.
   - Some of the competitors offer "Never ask" (ChatGPT's app permissions, search summary).
   - Only the Undo and Trust tabs (`/api/undo`, `/api/ledger`; on the phone, `JarvisApi.kt:300,756`) come close to what they offer, and none of the six advertises an undo list for actions (unverified).
2. **Memory you can actually see.**
   - Every automatically saved fact is listed, with Forget and Erase.
   - It never learns from emails or web pages.
   - It keeps dates on what it believed and when.
   - This answers ChatGPT's best-documented complaint: memory that is opaque and surprising.
3. **Local means no caps, no subscription tiers and no data sent away.**
   - Competitors gate features behind plans. Gemini's Daily Brief needs AI Plus and Spark needs AI Pro. Siri AI has daily caps (search summaries).
4. **It answers only to the owner's voice**, and speech is turned into text on the PC.
   - Alexa+ sends every recording to Amazon's cloud.
5. **It drives the owner's real PC and phone.** Cloud agents such as ChatGPT agent use their own remote computer, not yours; only Copilot shares this.

### Not advantages, even if they feel like them

- The animated faces are nice, but Copilot is dropping its own avatar, Mico, in Aug 2026 (search summary). Nobody picks an assistant for its face.
- "Works on any GPU" does not matter to a one-owner product.

### The gaps a daily user notices first, in order

1. "Set a timer for 10 minutes" / "wake me at 7" / "remind me to call Mum at 6": **nothing**.
2. "What's the weather?" / "Who won last night?": **nothing**, by design, and with no way round it yet.
3. The spoken reply starts 2.5–4 seconds late (an estimate). Talking over it does not stop it in the apps yet.
4. Answers are noticeably less clever, and long chats hit the 16k memory limit.
5. The PC off or asleep means the phone is dead. This is not in the queue at all.
6. Setup: the 43-character token, and starting the backend by hand.

---

## 3. The queue

### Item by item

| Queued item | Verdict | Why |
|---|---|---|
| "Always keep in mind" pinned facts (running) | **Closes a gap** | It makes memory feel like it "just knows", as ChatGPT's and Claude's does. Small. Finish it. |
| "Who is my sister" (names and aliases) | Strengthens an advantage; medium value | Better recall, but less visible than the pinned list. Fine next, but lower than temporary chat. |
| Temporary chat, plus a "used in this answer" list with Forget | **Closes a gap, and makes a differentiator** | Temporary chat is table stakes (Claude incognito, page read; ChatGPT has one (unverified)). "Used in this answer" goes straight at ChatGPT's opacity complaint. Move it up. |
| Overnight tidy ("still true?" cards) | Matters little now | No competitor makes this visible. Nice later. |
| Any-GPU support, 3 presets per hardware case | **Over-invested for this owner** | One owner, and his hardware is already known. The second card is already detected (`jarvis_second_card.py`). It only matters if others will install Jarvis. Owner's call. |
| Docker option | **Over-invested, and a possible clash** | ARCHITECTURE §11 says "Sandbox: Git worktrees, not Docker", and `jarvis_agent.py:34` says "Docker-based execution ... remain excluded". If "Docker option" means *installing* Jarvis in Docker, it is a different thing. Either way, check its scope with the owner before building. |
| Model advice (suggest a bigger local model, the big model or the cloud per task) | Low; partly a duplicate | The router already offers the cloud lane per question (`jarvis_router.choose()`, `offer`, ARCHITECTURE §11). Make sure it extends that, not builds a second one. |
| Real mouse + headless browser + clicking by sight (second card) | **Over-invested relative to daily value right now** | Large, needs hardware, and even the cloud agents get complaints about being slow and unreliable. Later, after the card is installed and measured. |
| Interrupting by talking in both apps | **Closes a gap** | It is the ChatGPT Voice / Gemini Live baseline. Keep it high. |
| "One moment." when a tool starts, and an "I heard you" sound | **Closes a gap cheaply** | It hides the 2.5–4 s delay. Best value for the effort in the voice lane. |
| Sleep mode (schedule, unload models, warm-up) | Medium | **Clash to plan for:** alarms and reminders must still fire while the models are unloaded. That is one more reason timers must not depend on the AI model. |
| CI screenshot job, branch list, workflow updates | Invisible to the user | Fine as background work. Do not let it delay the user-facing items. |
| The four extraction modules: 4 fixes to the approval gate, a scrubber, 2 script skills, an MCP bridge (MCP is a standard way to plug outside tools into an assistant) | The gate fixes are safety work, so keep them. The MCP bridge could be a big multiplier for integrations. | Every tool it plugs in must still go through the gate and cards. It is the same pattern as ChatGPT "apps" and Claude's MCP connectors. |
| Security audit, then per-device keys, a device list, QR pairing | **QR pairing closes the worst setup gap.** Per-device keys are needed before more devices. | Keep. |
| Timers, reminders, alarms, to-do | **Closes the biggest gap. Move to the top.** | Every competitor has them, and Gemini and Siri users are angry that the AI versions broke them. Answer them without the model. |
| Morning briefing and scheduled tasks | **Closes a gap** | ChatGPT Scheduled, Gemini Daily Brief and Spark. Builds on timers and fills the digest and the empty initiative engine. |
| Calendar events and email drafts (never send) | Closes a gap | Medium. After search. |
| Web search and weather, one approved question at a time | **Closes a table-stakes gap** | But a card for *every* weather question will feel clumsy. See the owner question below. |
| Voice memos into Obsidian notes | Strengthens an advantage | It fits `#obs`, and no competitor writes into your own local notes app. |
| "Ask my documents and files" | Closes a gap | This is what ChatGPT and Claude Projects do. Medium to large. Better once the second card gives more working memory. |
| Quick text helper | Medium | Apple's Writing Tools and Copilot have this (unverified in 2026). A desktop hotkey on selected text would be nice. |
| Tidy my files | **Low value, higher risk** | Moving many files is exactly the "acts on many things" shape the rules dislike. Put it last. |
| Guided first-run setup | Closes a gap | Competitors have zero setup. QR pairing is the most valuable part. |
| Second card: Qwen 3.5 9B, and Kokoro voice on the GPU (~1 s replies) | **The biggest jump in quality and voice speed** | Blocked on hardware. Make it #1 the day the card is installed and measured. |
| Final audits | Needed; not user-facing | Keep at the end. |

### Missing from the queue (things competitors treat as basic)

1. **An instant path for simple commands that skips the AI model.** Timers, "stop", "what time is it", lights on or off. The earlier report pointed at Home Assistant's `prefer_local_intents` pattern. The Gemini and Siri complaints prove why: they broke exactly these by sending them through a large model. It belongs inside the timers item, but name it explicitly. S–M.
2. **Music and media control** ("pause", "next", "volume down"). This is core for Alexa, Siri and Google. It could use Windows media keys on the desktop, or Home Assistant's media players. I found nothing for it in the backend (grep). S–M.
3. **"The PC is asleep or off" on the phone.** Say it plainly on the phone, and offer "Wake my PC" when the phone is on home Wi-Fi. Wake-on-LAN (a signal that switches a PC on over the home network) needs to be on the same local network; whether it works through Tailscale is **unverified**. Every competitor is always on, so this matters. M.
4. **Searching chat history.** ChatGPT and Claude have chat search (unverified for 2026). JARVIS-API §18.3 has list and open routes but no search. S–M.
5. **Routines**: one phrase, several steps, each step that acts still getting a card. Skill discovery half-covers this. M.
6. **A "What can you do?" answer.** S.

### Proposed top 10, in order

1. **Timers, alarms, reminders and to-do, with the no-model instant path.** They must keep working in sleep mode. This is the biggest daily gap, and the competitors' own weakness right now.
2. **Finish the voice lane:** interrupt by talking, "One moment.", and the "I heard you" sound. They hide the delay in Jarvis's headline feature.
3. **"Always keep in mind"** (already running). Small, and memory immediately feels smarter.
4. **Temporary chat, plus "used in this answer" with Forget.** Table stakes, and the most visible proof of Jarvis's memory advantage.
5. **Web search and weather, one approved question at a time.** Removes the most common "it can't even…" moment.
6. **QR pairing and per-device keys**, straight after the security audit. Removes the worst setup step and makes multi-device possible.
7. **Scheduled tasks and the morning briefing.** Turns the empty initiative engine and digest into something the owner sees every day.
8. **Second card: Qwen 3.5 9B and Kokoro on the GPU.** Jumps to #1 the day the card is installed and measured.
9. **Calendar events and email drafts (never sent).** Real "doing" value, safely.
10. **Guided first-run checklist** ("Start Jarvis for me", the voice download as one card), plus media control.

**Moved down:** any-GPU presets, the Docker option, model advice, the real-mouse and vision-clicking agent, the overnight tidy, tidy my files. "Who is my sister" sits just below the top 10.

### Questions for the owner, kept short

**1. Weather.** Asking for the weather sends only your town to a weather service. A card every time will feel clumsy.
- **A card every time, like search** (recommended for now: it matches the "ask each time" rule you chose)
- **Allow it inside the morning briefing only.** Setting up the briefing is one card, and that card names the weather service.

**2. The Docker option.** ARCHITECTURE says "Git worktrees, not Docker". Is the queued Docker option about *installing* Jarvis, or about *running commands* inside Docker?
- **Installing only** (recommended: no clash)
- **Running commands**: that reopens a decision already taken

(The two open questions from the queue still stand: should timers and one-time reminders go without a card, and which search provider to use. The recommendations in the earlier report stand too.)

---

## 4. Top 5 "steal this" ideas, all rule-compatible

1. **A "Coming up" page** (from ChatGPT's "Scheduled" page, June 2026, search summary). One list in both apps of everything that will fire: timers, reminders, briefings. Each shows its next run time, with Pause and Delete per item. Setting up anything that repeats is a card, and the card lists the next 3 run times. There is no "delete all". **M**, with scheduled tasks.
2. **A one-tap "don't remember this chat" mode** (from Claude's incognito ghost icon; help page read). It shows a marker for the whole chat. The chat reads no memories, learns nothing and saves no history. The empty chat screen says so in one line. **S.**
3. **Memory, visible inline.**
   - Jarvis already shows a quiet "Jarvis remembered 2 things" line (JARVIS-API §19.5). Make that line open onto the facts themselves, with Forget beside each one, right under the answer.
   - Add the matching "Used 2 memories ▸" line, with Forget per fact.
   - This beats ChatGPT's "memory summary will not include everything". **S–M.**
4. **"Show me where to click" instead of clicking** (from Copilot Vision's highlight-where-to-click, search summary). Jarvis draws a highlight on the screen and says the step, and the owner clicks. It acts on nothing, so it needs no card, and it suits a beginner. It needs a model that can see, so second card. **M–L.**
5. **A spoken briefing on the first "Hey Jarvis" of the morning** (from Gemini Live's "Daily Brief", search summary). "Morning. Two things today, and it's 12 degrees." Any sensitive saved fact stays on screen, not read aloud, which is the owner's 2026-09-24 rule. **S** once scheduled tasks and weather exist.

(Near-miss: the "Important actions" wording from ChatGPT's app permissions. Every card could say in one short line *why* it is asking: "This leaves your PC" or "This can't be undone". Without the "Never ask" option. **S.**)

---

## Sources

All are search results only, not opened, except where marked "read".
- [Claude incognito chats, Claude Help Center (read)](https://support.claude.com/en/articles/12260368-use-incognito-chats)
- [Can ChatGPT remember previous conversations? (datastudios)](https://www.datastudios.org/post/can-chatgpt-remember-previous-conversations-memory-behavior-session-limits-and-persistence)
- [Simon Willison on ChatGPT's memory dossier](https://simonwillison.net/2025/May/21/chatgpt-new-memory/)
- [OpenAI: Memory and new controls](https://openai.com/index/memory-and-new-controls-for-chatgpt/)
- [ChatGPT Tasks limits by plan](https://www.ai-toolbox.co/chatgpt-management-and-productivity/how-to-use-chatgpt-tasks-schedule-2026)
- [OpenAI launches Scheduled Tasks, retires Pulse](https://techjacksolutions.com/ai-brief/agentic-ai-news-openai-launches-scheduled-tasks-in-chatgpt-a/)
- [ChatGPT Connectors 2026](https://justinmckelvey.com/blog/chatgpt-connectors)
- [ChatGPT agent help](https://help.openai.com/en/articles/11752874-chatgpt-agent)
- [OpenAI community: Advanced Voice Mode keeps interrupting me](https://community.openai.com/t/feature-request-advanced-voice-mode-keeps-interrupting-me/962909)
- [Google: productivity features in Gemini Live](https://blog.google/innovation-and-ai/products/gemini-app/productivity-features-gemini-live/)
- [Gemini Spark schedules help](https://support.google.com/gemini/answer/17094710?hl=en&co=GENIE.Platform%3DAndroid)
- [TechCrunch: Gemini Intelligence on Android](https://techcrunch.com/2026/05/12/google-brings-agentic-ai-and-vibe-coded-widgets-to-android/)
- [Google Home after Gemini: 136 bad reviews](https://unstar.app/blog/google-home-gemini-voice-commands-worse-reviews-2026)
- [9to5Google: Gemini replaces Assistant in 2026](https://9to5google.com/2025/12/19/google-assistant-gemini-2026/)
- [Apple Newsroom, June 2026](https://www.apple.com/newsroom/2026/06/apple-intelligence-brings-powerful-ai-capabilities-into-everyday-experiences/)
- [WWDC26 Siri AI and Gemini/PCC](https://mer.vin/2026/06/apple-wwdc26-siri-ai-and-gemini-backed-foundation-models-on-device-and-private-cloud-compute/)
- [MacRumors iOS 27 roundup](https://www.macrumors.com/roundup/ios-27/)
- [AppleInsider: Siri AI beta, usage caps](https://appleinsider.com/articles/26/09/09/siri-ai-will-launch-in-beta-complicated-by-daily-usage-caps-future-paid-access)
- [Mac Observer: Siri AI beta complaints](https://www.macobserver.com/news/siri-ai-beta-complaints-iphone-apple-watch/)
- [Neowin: Copilot Vision and Hey Copilot](https://www.neowin.net/news/microsoft-launches-copilot-vision-for-windows-11-and-hey-copilot-voice-activation/)
- [Copilot Fall release: memory, connectors](https://www.etavrian.com/news/copilot-fall-release-memory-search-connectors)
- [GeekWire: Copilot apps merging](https://www.geekwire.com/2026/microsoft-starts-merging-its-copilot-consumer-and-business-apps-in-advance-of-super-app-rollout/)
- [GeekWire: Recall still raises red flags](https://www.geekwire.com/2026/one-year-after-its-rocky-launch-microsofts-windows-recall-still-raises-security-red-flags/)
- [Windows Forum: Microsoft rolls back Copilot surfaces](https://windowsforum.com/threads/microsoft-rolls-back-copilot-surfaces-in-windows-11-focusing-on-privacy-and-control.405265/)
- [Consumer Reports: Alexa+ review](https://www.consumerreports.org/electronics/digital-assistants/amazon-alexa-plus-ai-assistant-review-a1667486499/)
- [Men's Journal: Alexa+ "unbearably erratic"](https://www.mensjournal.com/news/amazon-alexa-beta-testers-warned-service-felt-unbearably-erratic-ahead-of-launch)
- [The Conversation: everything said to Alexa sent to Amazon](https://theconversation.com/everything-you-say-to-an-alexa-speaker-will-be-sent-to-amazon-starting-today-252923)
- [Claude memory (reworked.co)](https://www.reworked.co/digital-workplace/claude-ai-gains-persistent-memory-in-latest-anthropic-update/)
