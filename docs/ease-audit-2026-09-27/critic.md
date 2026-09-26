# Ease-of-use audit: the critic

2026-09-26. Read-only. I read the six lens reports (`setup.md`, `customize.md`,
`everyday.md`, `history.md`, `recovery.md`, `newcomer.md`), re-checked the
claims that the proposed fixes depend on against the source at `ad44732`, and
looked up how other assistants handle the same five jobs. Web facts are marked
**page read** (I opened the page) or **search summary** (I only saw a search
engine's summary; two help sites, help.openai.com and home-assistant.io, are
blocked from this container, so those are summaries only).

---

## The answer first

1. **The six lenses agree, and they are right.** Jarvis is very hard to set up,
   settings are hard to *find* (not hard to *understand*), a newcomer is never
   told what to say, and there is no way to look back at what was approved.
   I re-checked 22 of their claims; 20 hold, 2 are small counting errors
   (section 1).
2. **Together they propose about 94 fixes. About 18 of them add a new screen,
   list, page or window, and 5 add a new button to the Jarvis bar.** Built as
   written, that would make Jarvis *harder* to use. Many are the same fix
   proposed 2 to 5 times under different names.
3. **After the attack, 14 fixes survive as a first batch** (section 4). Together they add
   **1 new list** ("Activity"), **1 list already approved** ("Things you can
   say", I116), **2 settings already approved or low-risk** (speaking speed
   and built-in voice), **0 new card kinds** and **0 new buttons in the bar**. Net,
   the bar gets *fewer* rows.
4. **Three things the owner should hear plainly** (CLAUDE.md "Tell the owner
   when something is wrong"):
   - **"What asks first" says something untrue about web search.** Its row
     reads "Asks you first, every time" and "Always asks", but a search that
     comes straight from your question runs with no card
     (`backend/jarvis_asks_first.py:133-144`, `:329-333`;
     `backend/rebuilt/jarvis-framework.toml:185-193`). The trust page must not
     be wrong.
   - **The 2026-09-26 "own networks" decision works for the address check, but
     the phone still cannot reach the PC over home Wi-Fi.** The phone's refusal
     message suggests "192.168.x.x ... or a name ending in .local"
     (`jarvis-client/.../data/OwnNetwork.kt:39-43`). But Android only lets the app
     talk unscrambled to `ts.net`, `nord`, `localhost` and `127.0.0.1`
     (`res/xml/network_security_config.xml`). And the desktop refuses to make Jarvis listen on
     anything but a Tailscale/Meshnet address (`src-tauri/src/commands.rs:799-807`).
     In practice the phone needs Tailscale or Meshnet, even at home.
   - **Out of the box, web search (the decided default, SearXNG) is not
     available to the AI at all.** The shipped settings file has no `[tools]`
     section, so every tool is off (`docs/INSTALL.md:181-194`, confirmed no
     `[tools]` in `backend/rebuilt/jarvis-framework.toml`). The Web search card
     lets you pick a provider and save keys anyway.
5. **Compared with the others** (section 2): Jarvis is **far behind** on setup
   and on reviewing past chats. It is **behind** on finding settings,
   on "what can I say?" and on backup. It is **ahead** on explaining each
   setting, on showing what it remembers, and on showing what asks first. No
   competitor has a page like "What asks first" or dated, forgettable facts
   with "what did you know on this date?".

---

## 1. Where the lenses got it wrong or disagree (checked)

| Claim | What I found | Matters? |
|---|---|---|
| Tray menu has 21 rows (`everyday.md` 2.4) | 18 rows plus 4 separators; Settings is the 16th row (`src-tauri/src/tray.rs:302-335`). `customize.md` is right | Small |
| HUD opens at 1280×900 (`newcomer.md` step 14, cites `windows.rs:521`) | `windows.rs:521` is the **Faces** window. The HUD is 1280×820 (`src-tauri/src/lib.rs:585`). `setup.md` is right | Small |
| Settings file has 39 sections (`customize.md`) | 38 section headers (`grep -c '^\['`). `newcomer.md` is right | Small |
| Phone Brain has "~35" sections (`newcomer.md`) | 38 `item(key` in `BrainScreen.kt`. `customize.md` is right | Small |
| Jarvis understands "~12 families" (`everyday.md`) vs "~39 kinds" (`newcomer.md`) | Both true: 39 distinct `Intent(...)` names in `backend/jarvis_quick.py`, in about 12 families. There is **no** "help" or "what can you do" intent | Consistent |
| Moving email/calendar passwords into Credential Manager is "the owner's call" (`setup.md` #14) / "not checked whether discussed" (`customize.md` hard #2) | **Already queued**: feasibility step 5, "Moving service passwords from Windows user settings into Credential Manager (Security G3)" (`docs/FEASIBILITY-AUDIT-2026-09-26.md:351`) | Yes: not a new question |
| ARCHITECTURE says "no screen on purpose" for the calendar link (`setup.md` #14) | The stated reason is about the **phone**: "a link typed on the phone would be one more place to keep a password safe" (`docs/ARCHITECTURE.md:463-467`). A PC-only box does not go against that reason | Yes: makes the fix easier |
| History search is blocked by the 2026-09-26 decision | Only partly. The decision (`CLAUDE.md:329`) comes from memory idea 8, which is a **tool Jarvis uses** to search your words (`docs/MEMORY-RESEARCH-2026-09-26.md:106-110`). ARCHITECTURE §5's rule is "nothing in it is recalled into a chat" (`docs/ARCHITECTURE.md:841`). A search box only you use, with results on screen and never sent to the model, does not recall anything into a chat. Its one hard rule: any search index must be encrypted too, or it breaks "encrypted or not kept" | Yes: see question 2 |

Re-checked and **true** (a sample): "Let my phone reach this" is used only when the
desktop starts Jarvis (`sidecar.rs:482-492`); `jarvis_not_running` tells you to
use a "Start Jarvis" button that does not exist under that name
(`plain-errors.js:39-42`); the autostart switch says "Start Jarvis when Windows
starts" (`settings.html:1245`), but it starts only the desktop app. The phone
hides its nav row by default (`AppearanceStore.kt:644`). The phone's voice and
security settings are under "Platform checks" (`ReadinessScreen.kt:197`). No
example phrases exist in either app (grep). Neither app reads `answer_kept`
(grep). The deep-question note says "the answer is kept" (`brain.html:381-382`),
but the answers last only until a restart (`JARVIS-API.md:1705-1709`). The error Details cannot be
selected on the desktop: the body has `user-select: none` (`style.css:75`), and
`#answer-problem` is not inside `.markdown` (`index.html:621`). The phone app has no
`SelectionContainer` anywhere. Forget really does ask twice
(`brain.js:2128-2132`). `/api/pending` answers with `history`
(`JARVIS-API.md:208`), and the phone refuses it by name (`JarvisApi.kt:121`).

---

## 2. How Jarvis compares (2025-26)

Grades: **Ahead**, **Level**, **Behind**, **Far behind**, compared with the best
of the group on that row.

| Job | Jarvis today | The others | Verdict |
|---|---|---|---|
| **Setup** | About 24 steps. 13 PowerShell lines (+7 for voice, 1 as administrator), 6 programs, a build from source, a hand-typed 43-character key; blocked entirely for anyone without the owner's backend files (`setup.md`, `newcomer.md`) | ChatGPT, Claude, Gemini: install and sign in. Alexa and Google Home: a phone app wizard. Open WebUI: `pip install open-webui` then `open-webui serve`, or one `docker run` line with Ollama bundled ([Open WebUI Quick Start](https://docs.openwebui.com/getting-started/quick-start/), search summary). Leon: `npm install --global @leon-ai/cli`, `leon create birth`, then `leon check` ([Leon README](https://github.com/leon-ai/leon/blob/develop/README.md), search summary). Home Assistant Voice PE: a phone wizard that picks the wake word (including "Hey Jarvis") and the voice ([HA Voice PE](https://www.home-assistant.io/voice-pe/), search summary) | **Far behind** even the open-source ones. Leon's `leon check` is Jarvis's preflight, but Leon puts it in the install steps |
| **Settings** | 21 cards on one 15-screen page, no map, no search. The phone has no Settings screen. Every setting explains itself in plain words. Tools need a file edit | ChatGPT: Settings → Personalization, with 8 "Base style and tone" presets and a Custom instructions box ([ChatGPT personality help](https://help.openai.com/en/articles/11899719-customizing-your-chatgpt-personality), search summary). Claude: Settings → Memory, one switch "Search and reference chats" ([Claude help](https://support.claude.com/en/articles/11817273-use-claude-s-chat-search-and-memory-to-build-on-previous-context), **page read**). Home Assistant: Settings → Voice assistants → **Expose** tab, one list with a switch per device, and locks and garage doors are kept apart ([HA expose](https://www.home-assistant.io/voice_control/voice_remote_expose_devices/), search summary) | **Behind** on finding things, **ahead** on explaining. HA's Expose tab is the model for Jarvis's "tools only in a file" problem: one list, a switch per thing, in the app |
| **Understanding "what can I say / what is it doing"** | 0 example phrases anywhere; 8 face states, 3 taught; the approval card is very clear; "Used in this answer" shows which facts were used | Alexa: "Things to try" in the app, and Amazon publishes starter lists ([About Amazon UK](https://www.aboutamazon.co.uk/news/devices/your-guide-to-the-first-30-things-to-try-with-alexa-in-the-uk), search summary). Home Assistant: a "Sentences starter pack" page, and a **Debug** view that shows how a sentence was understood ([HA troubleshooting](https://www.home-assistant.io/voice_control/troubleshooting/), [starter pack](https://www.home-assistant.io/voice_control/builtin_sentences/), search summaries). Gemini: suggested prompts under the box (seen only in Google's **Enterprise** docs; consumer app **not verified**) | **Behind** on "what can I say". **Ahead** on "why did it do that" for memory and approvals |
| **Reviewing past chats** | Read-only list, 30 a page, no search, no weekday, no export, not reachable from the bar | ChatGPT: chat search, and since 14 July 2026 one search over chats, files and images, free for everyone ([Digital Trends](https://www.digitaltrends.com/computing/chatgpt-can-now-search-your-entire-chat-history-for-answers/), [gHacks](https://www.ghacks.net/2026/01/19/chatgpt-now-searches-your-full-chat-history-for-answers/), search summaries). Export from Settings → Data controls; the email link lasts 24 hours ([OpenAI export help](https://help.openai.com/en/articles/7260999-exporting-your-chatgpt-history-and-data), search summary). Claude: chat search on by default (**page read**, above). Open WebUI: Ctrl+K search, archived chats, import and export ([Open WebUI history](https://docs.openwebui.com/features/chat-conversations/chat-features/history-search/), search summary). Alexa: voice history filtered by date, device and profile ([Amazon help](https://www.amazon.com/gp/help/customer/display.html?nodeId=GHXNJNLTRWCTBBGW), search summary). Google: Gemini Apps activity, delete by hour, day or range, auto-delete after 18 months by default ([Google help](https://support.google.com/gemini/answer/13278892), search summary) | **Far behind.** Every one of the others can find an old chat by word or date |
| **Reviewing past actions and changes** | 0 places show past approvals or settings changes; "Ledger" shows hashes, under Advanced | Home Assistant: **Activity** (formerly Logbook) lists every state change and, since recent releases, what caused it: a user, an automation or a script ([HA Activity](https://www.home-assistant.io/integrations/logbook/), search summary; community threads say it does not always name the user). Google Home: Home History, with delete by range and auto-delete of 3, 18 or 36 months ([Google Home help](https://support.google.com/googlehome/answer/16613583), search summary). ChatGPT, Claude: no list of approvals that I found (**not verified**) | **Behind** Home Assistant and Google Home. Level with the chat assistants, which have little to approve |
| **Memory review** | Every fact dated; Forget and Erase; "what did you know on this date?"; export | Claude: Settings → Memory, listed under Topics, each one editable or deletable (**page read**). ChatGPT: its memory summary "will not include everything" (`docs/COMPETITORS-COMMERCIAL-2026-09-25.md:74`, earlier search summary) | **Ahead** |
| **Recovery and backup** | Shared plain error words (good); preflight excellent but hidden; no backup, no restore | Home Assistant 2025.1: new users are asked to set up nightly **encrypted** backups (3 kept by default), are given an "emergency kit" with the key, and can restore on every install type ([HA 3-2-1 Backup](https://www.home-assistant.io/blog/2025/01/03/3-2-1-backup/), [emergency kit](https://www.home-assistant.io/more-info/backup-emergency-kit/), search summaries). The cloud assistants keep your data on their servers, so there is nothing to back up | **Behind** Home Assistant. HA's design matches the owner's queued I96 (encrypted, a recovery code shown once) almost exactly, which supports it |

Where this repeats `docs/COMPETITORS-COMMERCIAL-2026-09-25.md` (its "Setup / ease:
far behind"), it confirms that report a day later. What is new here: the
history, review and recovery rows, and the open-source comparison.

---

## 3. Attacking the fixes

**The test for each fix:**

- Does it add a screen, setting, card or button? That means more to learn.
- Does another lens already propose it? That means a duplicate.
- Does it break one of the five rules, a dated decision, or a feasibility
  guardrail (`FEASIBILITY-AUDIT-2026-09-26.md:361-376`)?
- Does it break the UI audit's budget: Settings get 0 new switches; the bar,
  Brain and onboarding get 1 new idea each (`UI-AUDIT-2026-09-26.md:59`)?
- Would a smaller fix do?

### 3.1 The worst overlap: five "look back" lists become one

Proposed separately:

- customize #6 "Recent changes";
- everyday #8 "Activity" (also absorbs the Undo shelf);
- history #2 "Recent decisions" and #9 "Recent changes to settings";
- newcomer #12 "Decisions";
- history #10 "past focus sessions".

That is up to **5 new lists** for one question, which breaks guardrail 1, "one
home per kind of thing".

**The simpler fix:** one read-only **Activity** list, built from the decided
cards the PC *already sends* (`/api/pending` → `history`, `JARVIS-API.md:208`).
It needs no audit-log reader. Here is why that is enough: **every change that
makes Jarvis looser already raises a card** (the "stricter is instant, looser is
a card" rule, guardrail 4). So a list of decided cards already answers "did I
turn that on?" for every loosening. Only changes that made Jarvis stricter
would be missing, and those are the safe direction.

- Each row: the card's title (already written to be safe on a lock screen),
  Approved / Denied / Timed out, when, and which device.
- It has no buttons that decide anything.
- It never shares a list with the waiting cards. Keep the guard at
  `JarvisApi.kt:121`.
- Where it goes: the desktop Brain's Work tab and the phone's Inbox. Both
  already hold the Undo shelf, so "what happened" and "put it back" sit side by
  side.
- **Drop, for now:** absorbing the Undo shelf. It depends on the owner's own
  `jarvis_undo`, which has not been checked (`ARCHITECTURE.md:1513-1520`). Also
  drop the audit-log reader (history #9): the log is written by about 26
  modules with free-form details (`rebuilt/jarvis_framework.py:406-431`, "This
  does not redact"), so every event name would need an allow-list.
- **Before building:** check on the owner's PC what the gate's `history` rows
  contain and how long they are kept. The gate is in `jarvis_gate.py`, which is
  not in this repo. This is **not checked**, and the fix depends on it.
- Focus sessions (history #10) wait. They are numbers the owner did not ask
  about.

### 3.2 "What did I miss?" gets bigger, but no new button

History #1 wants "What did I miss?" to include cards that timed out,
automatically saved facts, "tell me when" matches, finished jobs and focus
sessions, plus **a new button in the bar and on phone Home**.

- **Keep** the extra content. It is one existing builder, needs no model, and
  it closes the 180-second timed-out-card hole.
- **Drop** the buttons. Saying "what did I miss?" already works from both apps
  (`JARVIS-API.md:4152-4155`). Teach it in "Things you can say" (3.3) instead.
  That costs 0 new buttons.

### 3.3 "Things you can say": one list, in fewer places

Proposed by everyday #1 and newcomer #3. Everyday puts it in 4 places, and
everyday #7 adds a 4th onboarding screen for it.

- **Survives.** It is I116, already approved "Now" and "served by the PC; fills
  the box, never sends" (`FEASIBILITY-AUDIT:268`).
- **Place it where it replaces something.** The empty Jarvis bar shows 10 rows
  of shortcut keys and `#` tags. Replace them with about 5 example phrases and
  one plain line: "Shortcuts, History and Settings: right-click the Jarvis icon
  by the clock." The shortcut list already lives in Settings → Shortcuts
  (`settings.html:291`). The bar ends up with *fewer* rows.
- Also show it in Help (both apps), and as one quiet line under "Ask Jarvis" on
  phone Home.
- Add one quick intent, "what can you do?", that answers from the same list
  with no model (newcomer #3). That is 1 new intent, 0 screens.
- **Drop** the 4th onboarding screen (everyday #7) and the extra "screen 0"
  (setup #11). Put 3 example lines on the existing screen 2, next to Alt+Space.
  The walkthrough stays 3 screens, as newcomer #4 and the UI budget ask.

### 3.4 Settings: tidy the page first, then build the phone screen

| Proposed | Attack | Verdict |
|---|---|---|
| Desktop jump list **and** search box **and** gear button in the bar (customize #3), 5-group headings (newcomer #5), 7-group plan for both apps (customize) | A search box is a second way to do what a jump list does. A gear adds a 5th icon to a bar that already has 4 icon-only buttons (`index.html:118-183`). The 7-group redesign of both apps is L and moves every setting at once | **Jump list and reordered cards survive** (everyday first, rare in the middle, read-only last, FAQ near the top). Drop the search box. Drop the gear: the "Things you can say" footer line (3.3) says where Settings is. Keep the 7 groups as the *target order* of the jump list, so the phone screen can copy it later |
| Phone Settings screen (customize #2, everyday #10, newcomer #13), L | It is really a *move*, not a new screen. But it is the biggest phone change (CI only, about 15 minutes a try) | **Survives, but second.** First do the S fixes, which get most of the benefit: show the nav row by default (`AppearanceStore.kt:644` → `true`), rename "Platform checks" to "Checks and setup", and put a "Talk: teach Jarvis your voice first →" line where the missing mic would be |
| Tool switches in the apps (setup #13, customize #1, newcomer #9) | The 2026-09-26 rule: from an app, the owner may loosen **only** "note writes, the wiki, reading their own calendar, email, notes and home status", **PC only**, "one card plus Windows Hello". "Nothing outside that list can be loosened from an app." (`CLAUDE.md`, approvals audit). Web search, shell, computer control and the browser are **not** on that list | **Survives, narrowed:** a switch per tool on "What Jarvis can reach", **on the PC only**, and only for calendar, email, notes and home reading, using the existing What-asks-first loosen card + Windows Hello (0 new card kinds). Every other tool stays in the file, but its line says so in plain words, not `[tools].enabled`. Web search: see question 1 |
| Built-in voice list and speaking speed (customize #4) | Speed is I28, already approved "Now", no card. A built-in voice picker adds 1 setting | **Survives.** 2 settings is exactly guardrail 13's limit, and neither is a loosening |
| "One home per kind": merge the model cards, retire `[power]` quiet hours, remove Brain's second theme picker (customize #5) | Right under guardrail 1. Retiring `[power]` changes the backend | **Survives in part:** remove the second theme picker, and rename "Faculties" to "Model" (S). Merging the schedules waits for the scheduler work, where it belongs |
| Email and calendar secrets into Credential Manager from a PC box (customize #8, setup #14) | Already queued as Security G3. A PC-only box fits the calendar decision's reason (section 1) | **Survives**, as "move G3 earlier"; it is not a new decision |
| "Put back how it came" per card (customize #12) | A reset that only makes things *stricter* needs no card, but it adds a button to about 3 cards | **Later.** Low demand; nobody has asked |

### 3.5 Starting Jarvis, and the phone reaching it

| Proposed | Attack | Verdict |
|---|---|---|
| "Start Jarvis for me" with a python finder and folder picker (setup #4, recovery #1 M); a "Start Jarvis" button in the offline bar (setup #4) | Supervision off by default is deliberate (`sidecar.rs:20-22`), and both keep it off. A new bar button is unneeded: the offline error already has a fix-button slot (`main.js:803-816`) | **Survives, without a new button:** change `jarvis_not_running`'s fix to name the real place and open Settings there (one shared words table, `tools/gen_plain_error_cases.py`). Rename the autostart switch to "Start Jarvis Desktop when Windows starts", with a line under it. The python finder (M) comes second |
| "Let my phone reach this": words (setup #5, newcomer #6) vs. the desktop writing `[security].bind_address` into the settings file (setup #5 M) | Having the desktop write the backend's *listening address* into its settings file is a new write path to a safety setting. Words fix the trap | **Words survive; drop the file write** |
| Two preflight checks: is Jarvis listening where the phone can reach it, and is the firewall open (setup #6)? | Read-only preflight lines, the guardrail 9 pattern | **Survives** |
| Make the phone's messages agree (setup #7) | Needs the owner to know about the home-network gap (answer-first point 4) | **Survives:** reword to "Tailscale or NordVPN Meshnet (needed even at home)". Changing the rule itself is *not* recommended: it would mean Jarvis listening on the home Wi-Fi, which `commands.rs:799-807` refuses on purpose |
| Show the token in groups of 4, and a "Show" eye on the phone (setup #8, newcomer #8) | QR pairing (I102) is decided and replaces both | **Grouping survives** (display only, S). **Drop the eye.** QR comes soon enough, and a visible key on a phone screen is a new way to leak it |
| Tailscale install steps (setup #10, newcomer #7); the README warning that the backend is not public (newcomer #1) | Docs only | **Survive** |
| Guided setup I119 moved earlier (setup #17), with 4 extra steps | It is "Later", after I102. Building a wizard before QR pairing means building pairing twice. And it cannot fix the three worst blockers, which all come before the app exists (`setup.md`) | **Stays Later.** The preflight fixes above are its cheap first half |
| Publish the desktop installer (setup #1, newcomer #2) | The owner's 10 minutes. The "download it from the Actions tab" stopgap asks a beginner to find build files that disappear after 14 days | **Key survives; drop the Actions stopgap from INSTALL** |
| Unshipped backend files go into the repo (setup #3) | The only real fix for blocker 1. The owner's call (licence, what is public). Already listed as open in `COMPETITORS-COMMERCIAL-2026-09-25.md:12-13` | Owner's call, **not re-asked here**: it is already on record |

### 3.6 History

| Proposed | Attack | Verdict |
|---|---|---|
| Weekday in dates ("Tue 22 Sept") (newcomer #11) | `whenWords` uses day, month and year, with no weekday (`history-view.js:216-227`) | **Survives**, S, no decision needed |
| Word search in History (everyday #9, history #6, customize #9, newcomer #11) | See section 1: an owner-only search does not recall into a chat. It must not create an unencrypted index. A plain scan on the PC, decrypting in memory, needs no index | **Question 2** for the owner |
| "Carry on this chat" (everyday #9, history #7, newcomer #11) | Loads old turns into a small (~8K) context. It must keep the old "read outside text" flag. It is a new feature, with its own audit | **Later** |
| Save one chat to a file (history #8) | ARCHITECTURE §5: chat history is "Encrypted or not kept ... There is no plain-text path" (`ARCHITECTURE.md:843-846`). An export is a plain-text path. Memory export already exists, so there is a precedent, but the invariant's wording would need changing | **Owner's call; not in the first batch.** Flagged because none of the lenses noticed it breaks a written invariant |
| `answer_kept: false` shown in words (history #3); deep-question wording (history #4); "deleting does not forget facts" next to Delete (history #13) | Truth fixes, S | **Survive** |
| A History link in the bar (history #5); a History pointer in Settings (history #11) | The bar link is a 6th control. The footer line in 3.3 covers it | **Pointer in Settings survives** (one line in the jump list). **Drop the bar link** |
| Findings in the desktop Brain, or a §8 note (history #14) | Parity rule | **Survives as the §8 note** (S); adding the panel waits |
| Filter box on "What Jarvis knows about you" (history #15) | It filters a list already loaded, with no new route | **Survives**, S |

### 3.7 Recovery

| Proposed | Attack | Verdict |
|---|---|---|
| "Copy details" button (recovery #5) | The Brain avoids the clipboard on purpose: Windows can sync it to the cloud (`brain.js:1738-1743`). The Details are scrubbed of keys and addresses, but a traceback could still hold a note's title (rule 1) | **Simpler fix:** make the Details text *selectable* (1 CSS line, `style.css:75`; `SelectionContainer` on the phone). Copying is then the owner's own choice, the same as with the answer text |
| "Update Jarvis on the PC" Settings card with a Copy button (recovery #3) | A 22nd card on a 15-screen page | **Replace** with one FAQ answer "How do I update Jarvis?" in both apps, plus an INSTALL.md "Updating everything" section. The ~78 messages keep their words and add "(Help: How do I update Jarvis?)" |
| PC-sleep: INSTALL line, a sentence under "Coming up", a preflight WARN (recovery #2) | No new setting. "Also on my phone" (decided) is the real fix | **Survives** |
| Preflight: fix the README line, a first "is this your backend folder?" check, and "what to do" in the tray status check (recovery #4 S) | S, no new surface | **Survive.** The `/api/preflight` "Check everything" button is I119: **Later** |
| A zip backup line in INSTALL.md, and a "Back up now" button (recovery #6, setup #2) | A plain zip of `.openjarvis` puts every memory, unscrambled, on a USB stick. It **pre-empts I96** (encrypted, "restore never loosens a tier") and the owner's open question 3 on backups (`OWNER-QUESTIONS-2026-09-27.md`) | **Split.** Keep a zip of the *backend program folder* (source files, not personal) and the plain sentence "chat history cannot move to a new PC". **Drop** the `.openjarvis` zip and the button: wait for I96 |
| Uninstall lists all 7 Credential Manager entries; lost-phone FAQ line; stale-message fixes; `Start-Transcript` in the patch script (recovery #6-8, #5) | S, no new surface | **Survive** |
| "Save a problem report" (recovery #5 M) | A new feature. Selectable Details plus a stated log location cover most of it | **Later** |

### 3.8 Words and first run

| Proposed | Verdict |
|---|---|
| Wording pass: Linked → Connected, "Stale" → "Catching up…", Faculties, Long Fuse jobs, "State of mind", "route badge" (everyday #3, history #12) | **Survives.** One shared-words change, no new surface. Drop "digest → things waiting to be told" (clumsy); use "the day's summary" |
| One name for the bar (everyday #4); Faces window retitled, false sentence fixed (`faces.html:152-153`) | **Survives**, S |
| Colour legend in Help (everyday #5) | **Survives** as one Help answer, drawn from the live spec. It is not a new screen |
| Tray "Help…" row (everyday #6) | **Simpler:** rename "Settings…" to "Settings and help…". 0 new rows |
| About/FAQ untrue lines (customize #10): the About page says every action asks, which is no longer true | **Survives**, S. This is the same kind of error as the "What asks first" one |
| "Stop learning" → "Pause background learning"; Forget's date question becomes an optional link (everyday 2.9, newcomer #15) | **Survives, narrowed.** Keep "are you sure?": the owner chose to keep it on 2026-09-24. Merging the three learning controls into two switches is **dropped**: turning on `learning_enable` is a MUST_ASK card (`jarvis_asks_first.py:199`), and a redesign risks changing that |
| HUD: open it only after the walkthrough is closed (setup #11); hide its lane names (newcomer #14) | **First half survives** (S). The second is **not checked** against a live backend: the lenses saw only the browser preview |

---

## 4. What survives: the first batch, in order

Sizes: S = under a day, M = a few days. "Both" = the desktop and phone apps.

| # | Fix | Where | Size | New surface |
|---|---|---|---|---|
| 1 | **Truth fixes**: the web search row in "What asks first", the two "Read your calendar" rows merged, About/FAQ lines, the deep-question note, `answer_kept` shown in words, the phone's network message, INSTALL 3.4 and the phone FAQ's old messages | backend, both, docs | S | 0 |
| 2 | **Starting Jarvis**: the `jarvis_not_running` fix names and opens the real place; rename the autostart switch; a line under "Let my phone reach this" | both (shared words), desktop | S | 0 |
| 3 | **Phone way around**: nav row shown by default, "Platform checks" renamed "Checks and setup", the "teach your voice first" line on Home | phone | S | 0 |
| 4 | **"Things you can say"** (I116) replaces the bar's shortcut rows; one line on phone Home; in Help; the "what can you do?" quick intent; 3 examples on walkthrough screen 2 | backend, both | M | 1 list (approved) |
| 5 | **Wording pass** plus one name for the bar, the Faces title, "Settings and help…" | both | S | 0 |
| 6 | **Desktop Settings jump list**, cards reordered, FAQ near the top, a History pointer | desktop | S-M | 0 |
| 7 | **Activity list** from the decided cards (after checking the gate's `history` on the PC) | backend check, both | M | 1 list |
| 8 | **"What did I miss?"** also covers timed-out cards, auto-saved facts, "tell me when" matches and finished jobs | backend | M | 0 |
| 9 | **History**: weekday in dates; the note next to Delete; a filter on the facts list | both | S | 0 |
| 10 | **Recovery docs and preflight**: README line, backend-folder check first, tray status "what to do", PC-sleep line and WARN, the Update FAQ, Tailscale steps, Uninstall's 7 entries, lost-phone line, a backend program folder backup line | docs, backend, desktop | S | 0 |
| 11 | **Selectable error Details** on both apps, and the two log sentences corrected | both | S | 0 |
| 12 | **Speaking speed (I28) and a built-in voice choice** | backend, both | M | 2 settings (within the limit of 2) |
| 13 | **Reading tools switched on from the PC** (calendar, email, notes, home), with the existing loosen card + Windows Hello; plain words for the rest | backend, desktop | M | 0 new card kinds |
| 14 | **The owner's 10 minutes**: the updater signing key, so a ready installer is published | owner | S | 0 |

**Budget check (guardrail 13):** 2 new settings (#12), 0 new card kinds, 0 new
notifications, 1 new list (#7), plus 1 list that is already approved (#4). The
Jarvis bar ends with fewer rows than today. Items 4, 7, 12 and 13 are new
features, so each needs its own follow-up audit (CLAUDE.md standing rule).

**Second batch:** the phone Settings screen (L), the python finder for
supervision, Credential Manager boxes for email and calendar (G3), the phone
welcome (UI #16), and history search (if question 2 is yes).

**Dropped or later:** the gear button, a History button in the bar, a "What did
I miss?" button, a 4th onboarding screen, the settings search box, the
token-show eye, the `.openjarvis` zip and "Back up now" (wait for I96), the
desktop writing the listening address, the audit-log reader, "Save a problem
report", "Carry on this chat", exporting a chat, a focus-session list,
per-card reset, merging the learning controls, and moving I119 earlier.

---

## 5. Two questions for the owner

**1. Web search out of the box.** Jarvis ships with every tool off, so the
AI cannot search the web until you edit a file, even though you picked
SearXNG as the default.
- **Ship it with web search switched on** (recommended). Plain searches from
  your own question still need no card, and after outside text a search still
  asks first, as you decided on 2026-09-25.
- **Leave it off, and fix the words so the app says how to turn it on.**

**2. Searching your own old chats.** A search box in History, just for you.
The PC unscrambles your chats in its memory to look, shows the matches on
screen, and never hands them to Jarvis's model.
- **Allow it now, on the PC, with no saved index** (recommended)
- **Wait until memory ideas 1-4 are measured**, as for Jarvis's own search

---

## Not checked

- What the gate's `history` rows carry and how long they are kept
  (`jarvis_gate.py` is on the owner's PC only). Fix #7 depends on it.
- Anything on real Windows or a real phone. I rendered no windows myself; the
  lens screenshots used the test kit's sample data.
- The pages on help.openai.com and home-assistant.io: blocked here, so those
  facts are search summaries. Whether ChatGPT or Claude show any list of
  approvals: not verified.
- Whether switching web search on in the shipped file changes anything on the
  owner's PC. The patch script never overwrites an existing settings file
  (`INSTALL.md:129-151`), so the owner would add one line by hand.
