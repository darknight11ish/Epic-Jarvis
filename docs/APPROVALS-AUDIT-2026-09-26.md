# Approvals audit, 2026-09-26: what asks first, and what could stop asking

Read-only audit. No code was changed. Every claim names the file and line it was checked against. **How often** figures are estimates: there are no usage logs, and the counts depend on which tools you have switched on in `[tools].enabled`, which I cannot see.

**In short**
1. Most cards Jarvis raises today are the right ones: they guard sending, spending, deleting, the internet, locks, and your security settings. Those stay.
2. The quickest win may be a mistake in the settings file this repo ships, not a rule: it has no lines for reading your calendar, email, notes or home, so on a PC set up from it, every one of those reads asks (details in "Found along the way").
3. The biggest everyday cards that could go are: **lights and plugs**, **plain repeating reminders**, and **memory cards for harmless facts about people you mention**. Each one touches a decision you already made, so each is a question for you, not a change I would just make.
4. Removing a card is **not** auto-approving. Auto-approving means a card is raised and something says yes for you. That is banned, and nothing here does it. "No card" means the action is on a short list you chose ahead of time, like saving to your Obsidian daily note today.
5. Right now you can only loosen or tighten by editing `jarvis-framework.toml` in Notepad. Neither app can do it, and some lines cannot be loosened at all (they switch the feature off instead). A plain "What asks first" page would fix that.

Words used: **card** = an approval card (Deny / Approve). **Tier** = the line for each action in `jarvis-framework.toml`: `auto` (just do it), `notify` (do it, tell you after), `ask` (a card every time), `never`.

---

## 1. Ranked changes: the most cards removed for the least risk

| # | What | Today | Recommend | Risk, in one line | Size |
|---|---|---|---|---|---|
| 1 | Add the four missing "read" lines to the shipped settings file (`calendar_read`, `email_read`, `notes_search`, `home_read` = `"auto"`) | Missing from `backend/rebuilt/jarvis-framework.toml` (lines 77-238), so each read asks. The README says they should be `auto` (`backend/README.md:3016-3020`) | **NO CARD** (what was always intended) | Reads your own data on this PC. It still marks the chat as having read outside text, so a later search or note in that chat still asks | S |
| 2 | Lights, plugs and fans you name yourself, with no card, as a setting that is **off** until you turn it on | Every home change is a card, whatever the tier (`jarvis_agent.py:1121`) | **MAKE IT A SETTING**, default: card. **Ask you (Q2)** | A misheard "Hey Jarvis" or a planted instruction flips a light. Annoying, not harmful. Locks, doors, alarms and covers stay one card each | M |
| 3 | Plain repeating reminders, alarms and the standby schedule, with no card | One card for anything that repeats (`jarvis_schedule.py:73-81`, toml:151-157) | **NO CARD by default** for these three. The briefing and "tell me when" keep theirs. **Ask you (Q1)** | A repeat you did not mean keeps ringing until you delete it. Only your own words can set one (`jarvis_agent.py:913-921`), and deleting is instant | S |
| 4 | Everyday facts about people you mention ("my sister likes jazz") saved automatically | Any fact about another person waits for a memory card (`jarvis_sensitive.py:39-47`) | **NO CARD** for everyday facts. Their health, money, address and contact details still ask. **Ask you (Q3)** | Jarvis remembers something about someone who did not agree to it. It stays on this PC and has Forget | S-M |
| 5 | Add "Start a fresh chat" to cards raised only because of earlier outside text | Outside text marks the whole chat (toml:40), so every later search or note write asks | **KEEP the card** and add the line and button (rules.md idea I-7) | None. It loosens nothing; it just shows the way out | S |
| 6 | A "What asks first" page: every action with its tier in plain words, "make stricter" switches in both apps, and loosening from a short safe list on the PC (one card each) | File only; `POST /api/config` answers 501 (`docs/JARVIS-API.md:1054`) | Build the read-only view and "make stricter" parts (already in the 2026-09-25 plan, item 17, not built). The loosening part: **ask you (Q4)** | A loosening could slip in unnoticed. Guard: loosening is one card plus Windows Hello, and the list never offers anything under section 2 | S-M |
| 7 | Check how your gate rates `home_control` | No patch adds a risk entry for it. The README asks you to add one by hand (`backend/README.md:3004-3009`) | **Check first.** If it is missing, every light card counts as "unclassified", so it also asks Windows Hello (`jarvis_owner_check.py:139-140`). The fix is two actions: lights (not risky) and locks (risky) | Rating locks as not risky would drop Windows Hello for a door. So split it; never just lower it | S-M |

Everything else in the inventory: **KEEP**.

---

## 2. Hard limits: things I did not recommend changing

These are not up for a trade-off. Where an idea above comes close to one, it says so.

- **Rule 4: never auto-approve, and block acting on a stale link.** Nothing here raises a card and answers it for you. Removing a card (changes 1-4) is a different thing: nothing is asked, because you put that action on a no-card list ahead of time. That is how Obsidian notes, power modes and model rollback already work (toml:122, 178, 143).
- **Rule 1: email, files, credentials and memory stay on this PC.** Nothing here sends anything anywhere new.
- **No "always allow", no approve-all, no approving in bulk, no approving by voice** (`docs/ARCHITECTURE.md:62-88`, `jarvis_card_words.py:33-37`).
- **These keep their card:** anything that leaves the PC (web search after outside text, GitHub, the browser, email); anything that cannot be undone, or deletes; spending money; sending messages or email; locks, alarms, doors and covers; passwords, PINs, account and ID numbers; and turning on or loosening a security or privacy setting.
- **Your decisions in CLAUDE.md stand.** Changes 2, 3, 4 and the loosening half of 6 would each change one, so they are questions for you (section 5), not recommendations to build.
- **Change 2 is the closest to a line.** `NEEDS_A_PERSON` exists so that a line in a settings file can never be your yes for something physical (`jarvis_agent.py:1094-1095`). A setting for lights would be a standing permission for one named kind of device. That is the same kind of thing as Obsidian notes at `auto`, not an approve-all button. But it does bend that rule, which is why it would be off by default and would take a card to turn on.

---

## 3. Found along the way (checked against the files)

1. **The shipped settings file lacks the read lines.** `backend/rebuilt/jarvis-framework.toml` has `read_calendar` and `read_files_readonly` (lines 79-80). Those are older names. It has nothing for `calendar_read`, `email_read`, `notes_search` or `home_read`, which are what the tools use (`jarvis_reach.py:122-126`). When a line is missing, the tier falls back to `unknown_action_tier = "ask"` (toml:74, `rebuilt/jarvis_framework.py:339-341`). The result, on a PC set up from this copy:
   - every calendar, email, notes or home read in chat is a card;
   - the morning briefing leaves out your calendar and email (`jarvis_briefing.py:322-326`);
   - "tell me when" refuses to be set up (`jarvis_tellme.py:253, 267`).
   A test comment says your own file has these reads at `auto` (`test_injection_cases.py:517-518`). I cannot see your file. **To check:** open "What Jarvis can reach" in Settings or on the phone's Mind screen. If "Reading your calendar" says "Asks you first: Yes, every time", this is the cause.
2. **`jarvis_briefing.py:26-27` says the reads are "the shipped `auto`".** For this repo's copy of the file, that is not true (see item 1).
3. **`jarvis_reach.py` has two small slips.** The docstring says "the six tools" that always need a person (line 19), but there are seven now, because `send_email` joined `NEEDS_A_PERSON` (`jarvis_agent.py:1122`). The fallback list at line 132 also lacks `send_email`. This only affects what the page says, and only when `jarvis_agent` cannot be loaded. Sending still needs a card.

---

## 4. Can you loosen or tighten today? (question 5 of the brief)

- **Only by editing the file.** Open `jarvis-framework.toml` in Notepad, change a line under `[autonomy.tiers]`, then restart the backend (`docs/INSTALL.md:170-197`). The file's own header says: "changing this requires editing this file, not asking in conversation" (toml:49-51).
- **Neither app can change a tier.** `POST /api/config` answers 501 on purpose (`jarvis-desktop/src/settings.js:5-8`, `src-tauri/src/brain.rs:22-25`, `docs/JARVIS-API.md:1054`).
- **You can see the tiers in both apps.** "What Jarvis can reach" shows "Asks you first" for each tool. The PC writes that list from your real settings (`jarvis_reach.py:1-25`; desktop `reach.js:34`, phone `Reach.kt:44`).
- **Some switches already make things stricter, in both apps:**
  - "Ask before every web search";
  - the voice settings (on-screen instead of read aloud, "Only trust the talk button");
  - Windows Hello "Every approval" instead of "Risky only" (`security-settings.js:16-35`).
  Tightening applies at once. Loosening back raises a card.
- **Watch out: many lines cannot be loosened.** The code only accepts `ask` for them. Setting one to `auto` does not remove the card; it switches the feature off. The toml says "Must stay 'ask'" at lines 84-86, 129-131, 147-149, 155-157, 164-171, 184-191, 207-238.
  - The tools in `NEEDS_A_PERSON` ignore any looser tier and refuse (`jarvis_agent.py:3824-3838`).
  - So does a note write after outside text (`jarvis_agent.py:3840-3850`).
- **What does work if you edit it:** `wiki_update` (the file itself says you may lower it, toml:198-200), the note writes (toml:99-122), the four reads (item 1 above), and `power_manage`.
- **Is it explained anywhere?** Only in pieces: the toml's comments, `docs/INSTALL.md` §1.6, and one section per tool in `backend/README.md`. Nothing in plain words lists "these asks can be loosened, these cannot". Change 6 would be that list.

---

## 5. Worth asking the owner

Two at a time is kinder, so ask Q1 and Q2 first.

**Q1. Repeating reminders.** Should a plain repeating reminder or alarm ("every weekday at 7, take pills"), or the standby schedule, be set up without a card? Anything that reads your email or calendar, like the briefing or "tell me when", keeps its card. Why ask: you decided on 2026-09-25 that anything that repeats asks once.
- **Yes, no card for these** (recommended)
- **Keep one card for anything that repeats**

**Q2. Lights.** Should there be a setting, off until you turn it on, that lets Jarvis switch lights, plugs and fans you name yourself without a card? Locks, doors, alarms and covers stay one card each, and it never applies after Jarvis has read outside text. Why ask: every home change needs a person today (`jarvis_agent.py:1121`), and you chose "one card for several devices", not "no card".
- **Yes, as a setting that is off by default** (recommended)
- **Keep a card for every change in the house**

**Q3. Facts about people.** Should everyday facts about people you mention ("my sister likes jazz") save automatically, while their health, money, address and contact details still ask? Why ask: on 2026-09-24 you listed "private details about other people" as sensitive, and the check today flags any fact that names someone.
- **Yes, save the everyday ones** (recommended)
- **Keep asking about every fact that mentions someone**

**Q4. Loosening from the app.** Should the desktop app let you loosen a small, safe set of asks, with one card plus Windows Hello each, instead of editing the file? The set would be the note writes, the wiki and the reads. Why ask: the settings file says tiers change only by editing the file.
- **Yes, on the PC only, from that short list** (recommended)
- **No, keep it file-only; the app only shows the list and makes things stricter**

---

## 6. The full inventory

"Without a card" means what could go wrong if this one had none. "How often" is an estimate for a normal day, assuming the tool is switched on.

### 6a. Cards raised from chat (the model's tools)

| What | What triggers it | Tier today | Without a card | How often (estimate) | Recommend |
|---|---|---|---|---|---|
| Change something in the home (`home_control`) | "Turn off the lights"; up to 10 devices on one card, locks and doors always on their own (`jarvis_agent.py:804-822`, `ARCHITECTURE.md:74-80`) | Always a card (`NEEDS_A_PERSON`, `jarvis_agent.py:1121`) | Lights: a nuisance. Locks, doors, alarms: someone gets in | 2-6 a day if you run lights by voice; 0 if Home Assistant is off | Locks etc.: **KEEP**. Lights and plugs: **SETTING** (Q2) |
| Web search | Only after outside text, when the search repeats a saved fact or a sensitive fact was used, for pasted or shared text, or with "Ask before every web search" on (`jarvis_agent.py:1221-1245, 1327-1345`) | `ask` for those (toml:168); otherwise no card | Private words from an email or your memory end up in a search engine | 0-3, mostly in chats that read email | **KEEP** (decided 2026-09-25). Add change 5 |
| Note write after outside text | Obsidian, Logseq or Joplin, in a chat that read outside text (`jarvis_agent.py:1207, 3720-3724`) | `ask` (toml:131) | An email plants text in your notes, or a private file ends up in a synced note | 0-2 | **KEEP** (decided 2026-09-24). Add change 5 |
| Send an email | One card per email, showing all of it (`jarvis_agent.py:1122`) | `ask` (toml:87) | An email goes out in your name; it cannot be taken back | 0-3 | **KEEP** (hard limit) |
| Run a command (`shell_exec`) | The model wants a PowerShell command | Always a card (toml:91) | Anything at all, including the internet | 0-2 | **KEEP** |
| Control the computer, the phone, a browser | One card per plan of steps (`jarvis_agent.py:1117-1120`) | Always a card | A click on Send or Pay | 0-2 | **KEEP** |
| GitHub search | "Is there a library for ..." | Always a card, even though `web_research` is `auto` (toml:78) | Your search words, and your token if set, go to GitHub | A few a week | **KEEP** (leaves the PC) |
| Read calendar, email, notes, home state | The model reads | Meant to be `auto` (`README.md:3016-3020`); `ask` with this repo's file (section 3) | Nothing leaves; your own data is read on your own PC | 2-8 if the lines are missing | **NO CARD** (change 1) |
| Resume a paused task | Resume after Pause (`jarvis_task_control.py:36-41`) | The original action's tier | The rest of a plan runs after things may have changed | Rare | **KEEP** |
| Calendar edit or delete, delete a file, spend money, post outside, change its own code | OpenJarvis's own tools on your PC. No tool in this repo's `jarvis_agent.TOOLS` uses them | `ask` or `never` (toml:88-97) | Cannot be undone, or costs money | Rare | **KEEP** |

Two limits on top of these: at most 5 cards per answer (`ARCHITECTURE.md:138`), and a card that is not answered within 180 seconds is refused (toml:75).

### 6b. Cards from things that repeat (one scheduler, action `schedule_repeat`)

| What | Tier | Without a card | How often (estimate) | Recommend |
|---|---|---|---|---|
| Repeating reminder, alarm or to-do (`jarvis_schedule.py:73-81`) | `ask`; any other tier refuses (toml:151-157) | A repeat you did not mean. Only your own words can set one (`jarvis_agent.py:913-921`), and deleting is instant | 1-3 a week | **NO CARD** (Q1) |
| Standby schedule (`jarvis_standby_schedule.py:40-46`) | Same | Jarvis sleeps at night. Going to standby by hand is already `auto` (toml:173-178) | Once | **NO CARD** (Q1) |
| Morning briefing, repeating (`jarvis_quick.py:19-22`) | Same | It reads your calendar and inbox every day | Once | **KEEP** |
| "Tell me when ..." (`jarvis_tellme.py:18-21`) | Same | It signs in to your mailbox every 5 minutes for up to 30 days (lines 36-55) | A few a month | **KEEP** (decided 2026-09-25) |

### 6c. Cards from turning a setting on, or looser (turning off is always instant)

All of these are **KEEP**. Each one is a security or privacy setting, you see it once, and it follows your rule "on asks, off is immediate".

| Setting | Action (file:line) |
|---|---|
| Background learning on | `learning_enable` (toml:209-212) |
| Learn automatically; also remember sensitive topics | `learning_auto_enable`, `learning_sensitive_enable` (toml:219-227) |
| Keep chat history, back on | `history_enable` (toml:213-218) |
| Second graphics card; browser control | `second_card_enable`, `second_card_browser_enable` (toml:180-191) |
| Big model | `big_model_enable` (toml:203-208) |
| Add a custom voice; speak in it; better voice | `custom_voice`, `better_voice_enable` (toml:229-238) |
| Wake word on; train or replace the voice print | `change_own_config` (`jarvis_speech.py:86-96`, `jarvis_voice_enroll.py:27-33`) |
| Voice loosening: balanced, read private or memory or sensitive answers aloud, trust "Hey Jarvis" like the talk button | `change_own_config` (`JARVIS-API.md:2037-2092`) |
| Briefing shows email senders | `change_own_config` (`jarvis_briefing.py:962-972`) |
| Stop asking before every web search | `stop_asking_before_every_web_search` (toml:169-171) |

How often: a handful of times, ever.

### 6d. Cards from buttons in the apps

| What | Tier | Without a card | How often | Recommend |
|---|---|---|---|---|
| Install a model you typed; switch model | `ask` (toml:141-142) | A download you did not want; a different model reads your email | Rare | **KEEP** |
| Make a tuned copy of a model (hardware setups) | `ask`, must stay (toml:144-149) | Nothing leaves the PC; it adds a model | Once per setup | **KEEP** (rare, not worth it) |
| Add a document to the wiki | `ask`; you may lower it (toml:193-201) | Pages written in your vault; the old copies are kept | A few a week while you use it | **SETTING** (change 6 / Q4) |
| "Save this as a skill?" | `modify_own_code` (`jarvis_skill_discovery.py:11-17`) | Jarvis writes instructions for itself | Rare | **KEEP** |

### 6e. Memory cards (a separate queue: they wait for you and do not time out)

| What | Without a card | How often (estimate) | Recommend |
|---|---|---|---|
| Passwords, PINs, account or ID numbers, birthdays, phone numbers, email addresses (`ARCHITECTURE.md:680-684`) | Secrets saved into memory | Rare | **KEEP** (hard limit) |
| Health, money | Sensitive facts saved by mistake | Rare | Already a setting ("Also remember sensitive topics automatically") |
| Any fact that names another person (`jarvis_sensitive.py:39-47`) | A harmless fact about someone who did not agree to it | 1-4 a day | **NO CARD** for everyday facts (Q3) |
| From pasted, shared or unverified words, or a chat where a tool ran (`JARVIS-API.md:2896-2960`) | Planted "facts" | 0-3 | **KEEP** |

### 6f. Windows Hello (not a card, but it feels like one)

With "Risky only" (the default, `security-settings.js:16-21`), Windows Hello or the phone's fingerprint is asked for a card that is unclassified, leaves the PC, cannot be undone, or that outside text tried to rush (`jarvis_owner_check.py:125-147`). Repeating reminders and note writes count as local and undoable, so they do not ask (`schedule_repeat` and the note actions' risk entries in the patches). See change 7 for lights.

### 6g. Already no card (the whole picture)

- **Timers, alarms, reminders, to-do.** One-time timers, alarms and reminders; the to-do list and named lists; snooze; "cancel that"; Coming up (`jarvis_agent.py:907-918`, `jarvis_quick.py:52-66`). After outside text, these are refused instead, so a web page cannot set your alarms.
- **Reads.** Briefing "now" (reads only), "what did I miss?", "what can you reach?".
- **Focus sessions** (`jarvis_focus.py:59-69`).
- **Stopping.** Stop, Pause, Stop everything (`ARCHITECTURE.md:145-153`).
- **Power.** Quiet, Standby, Active (toml:178).
- **Models.** Model rollback and browsing models (toml:140-143).
- **Always-free tools.** Calculator, memory search, reading a file (`README.md:2367-2368`, toml:80).
- **Web search** from your own question in a clean chat (toml:159-168).
- **Notes.** The Obsidian daily note and Logseq journal (`auto`); a new Joplin note (`notify`, you are told after) (toml:103-122).
- **Memory.** Automatically learned facts; Forget, "Erase the words", pinned facts (`README.md:111-113`).
- **Everyday settings.** Manner (`jarvis_manner.py:29`); the search provider; every "turn off" switch; every "make stricter" voice setting; back to the built-in voice.
- **Temporary chat, and answering cards.** A temporary chat; Deny from a notification; a "tell me when" match (it only notifies).

---

*Not verified:*
- your own `jarvis-framework.toml` and `jarvis_gate.py` (only this repo's copies);
- which tools you have switched on;
- how often any card actually appears.

The frequencies above are guesses from how the code works.
