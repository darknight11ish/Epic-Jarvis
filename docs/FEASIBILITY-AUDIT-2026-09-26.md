# Feasibility audit - the chair's report (2026-09-26)

Seven reviewers (Fit, Hardware and speed, Rules, Security, Overwhelm, Upkeep,
Devil's advocate) each read all 155 ideas from the 2026-09-26 research. This
report is where their positions meet: where they disagree, I checked the code
myself and say who is right. Their full write-ups are the appendices (listed
at the end). Nothing in the repository was changed.

Code was read at HEAD `4f25802` (2026-09-26). Paths are from the repo root,
`/home/user/Epic-Jarvis`. "Not checked" means exactly that.

---

## The summary (10 lines)

1. **156 ideas** (the 155 on the master list, plus the Notion import the owner chose, which the list missed) got one verdict each: **46 build now, 76 build later, 26 don't build, 8 already built (or guidance only).** 15 of the "build now" are ones the owner already chose; the other 31 are small recommendations.
2. **The hidden limit is the model's working memory.** On today's 8 GB card it holds about 6,000-8,000 tokens (a token is about ¾ of a word), not the 16,000 most reports assumed. The tool descriptions alone already take about 35-45% of that. So "a short tool list" (I06) and "measure every turn's cost" (I03) come first, and anything that adds words to every turn must prove it helps.
3. **Fix five things in today's code before adding features** (section 3, step 0). The biggest: when the backend restarts, it forgets that a conversation read an email, so the next turn stops asking before note writes and lights (checked: `backend/jarvis_chat_log.py:520-522`). Two ideas (the crash watchdog, the night shift) would make restarts routine.
4. **The memory re-ranker shipped switched on but unmeasured** (`backend/rebuilt/jarvis_memory.py:504-506`). The owner's own rule of 2026-09-26 says a memory change must beat the self-test first. It should be off until the PC run says it helps.
5. **Email drafts: the settings file Jarvis ships already says "no card" for `draft_email`** (`backend/rebuilt/jarvis-framework.toml:96`), even though it is on the "never loosened" list. That must be set on purpose before drafts are built.
6. **All four groups the owner chose can be built safely**, with the guardrails in section 2. Two need a change of HOW: screenshot text must be marked as outside text by the backend (the research's plan would have counted it as the owner's own words), and the plug-in server (MCP) bridge must be "programs on this PC only" in version 1 - its old draft no longer fits the code.
7. **The 12 GB card is not roomy.** Beside the planned long-conversation model it has about 2 GiB free, so the existing "better voice" (F5) already cannot run at the same time. Someone has to choose what that card is for.
8. **Many ideas copy something Jarvis already has** (goals vs repeating reminders, "welcome home" vs "What did I miss?", a new ledger, undo and GitHub watch vs modules already on the owner's PC). Those are cut or folded in.
9. **Keep Jarvis simple:** one home for each kind of thing, nothing new speaks unasked, no new daily card, invisible upgrades get no switch (section 4).
10. **13 questions for the owner** (section 5), asked two at a time. The first two: should every email draft show a card, and does "local plug-in servers" mean programs on this PC only?

---

## Words used below, in plain terms

- **Card** - an approval card: Jarvis shows exactly what it wants to do and waits for the owner's yes.
- **Outside text** - anything the owner did not type or say (an email, a web page, a file, a screenshot). A conversation that has read some is "tainted": it asks before note writes, some web searches, and lights.
- **Token** - a word or part of a word. The model can hold only so many at once (its "context" or working memory).
- **MCP** - a standard way to plug outside tool programs ("servers") into an assistant.
- **stdio** - the plug-in runs as a small program on this PC that Jarvis starts and talks to directly, with no network.
- **Egress** - a way out of the PC. Every one has a row in ARCHITECTURE section 4.
- **Pinning** - writing down the exact version (and a fingerprint, the "hash") of every downloaded package, so an update cannot slip in unnoticed.
- **Preflight** - Jarvis's own check-up (`selftest.py --preflight`) that prints pass / fail / warn.

---

## 1. The debate: where reviewers disagreed, and who is right

Each item: what was disputed, what the code says (checked by me unless marked), and the ruling. A Security "not safe enough" was only overridden where a named guardrail fixes it.

### 1.1 Facts first: what is already built (settles several disputes)

- **Memory ideas 1-4 (I31-I34) are merged.** `git merge-base --is-ancestor` succeeds for `9abdd68`, `c33b5f0`, `d2d8831`, `eee9b03`. The master list said "not merged"; every reviewer caught this.
- **The "notifications stay on the phone" commit `e372eb7` is now merged too** (merge `d1af3c7`, after the reviewers wrote). `setLocalOnly(true)` is in HEAD at `jarvis-client/.../service/ScheduleNotifier.kt:129,183,237` and `EventService.kt:362`. Fit, Rules, Upkeep and Devil all said "not in HEAD" - true when they looked, out of date now.
- **I01 and I02 are built** (commit `f973178`): `_model_can_use_tools` reads Ollama's `capabilities` (`backend/jarvis_agent.py:1996-2013`, used at `:3490`); `OLLAMA_NO_CLOUD=1` is set for the second Ollama (`backend/jarvis_second_card.py:792`) and in the owner's one-line setup (`backend/jarvis_profiles.py:844`). **Devil's advocate was right; the others rated work that was already done.** Still open: nobody has checked on the PC that installing a model still works with the lock on.
- **I82 ("someone is at the door") already works** through the existing `home` source, which watches any one Home Assistant entity for any state (`backend/jarvis_tellme.py:308-336`). Only a phrase and docs are missing.

### 1.2 Disagreements about specific ideas

| # | Idea | Who said what | What I checked | Ruling |
|---|---|---|---|---|
| 1 | I01, unknown answer | Fit/Security: if Ollama cannot say, send no tools ("fail closed"). Upkeep: keep sending tools and warn. | Built code sends tools unless the answer is a clear "no" (`jarvis_agent.py:3490`, `is False`). Tools still pass the gate either way. | **Upkeep is right.** "Unknown" means an older Ollama; refusing tools there would break Jarvis for no safety gain (every action still needs its card). Add a preflight WARN. |
| 2 | I31 re-ranker default | Hardware, Devil: off until measured; wait too long. Fit/Overwhelm: no objection. | On by default (`rebuilt/jarvis_memory.py:505-506`); a question waits up to 1.5 s (`:504`, `t.join` at `:641`); README: "The re-ranker is NOT measured" (`backend/README.md:10330`). Owner, 2026-09-26: a memory change must beat the self-test before it is kept (CLAUDE.md). | **Hardware and Devil are right.** Off by default until the PC self-test shows a gain; then cap the wait at about 0.3 s on spoken turns. Not an owner question - the owner's rule already decides it. |
| 3 | I06 short tool list | Hardware/Devil: a fixed core, fixed order; changing the list re-reads the whole prompt (~3-4 s). Fit: fine either way. | 22-23 tool descriptions ≈ 3,067-3,612 tokens by Jarvis's own counter (Hardware and Devil both measured; I did not re-measure). Real room ~8,000 (`backend/test_tool_text.py:3-5`), 6K in the "Smartest answers" preset (`docs/HARDWARE-PROFILES.md:702`). | **Hardware/Devil.** Fixed core in fixed order; once a group of extra tools is opened, keep it for the rest of that chat; measure with I03 before and after. "More tools" never offers a tool that is switched off or not allowed on that lane. |
| 4 | I07 MCP, what "local" means | Fit, Rules, Security, Devil: stdio programs on this PC only. The research (CAP #10, #12) planned Home Assistant's and Logseq's servers, which speak HTTP. | The draft refuses anything but stdio (`docs/designs/mcp-draft-2026-09-23/jarvis_mcp.py:238-241`). HA's MCP action tools act with no card. | **Version 1 = stdio only.** HA's MCP: never (its tools act without a card; Jarvis's own HA client does this safely). Logseq's server on 127.0.0.1 is a separate, later owner decision. Owner question 2. |
| 5 | I07, "a card to start each server" | Overwhelm: every launch = a card per server per reboot; prefer once per server and again on a version change. | Owner's words (CLAUDE.md, cutting-edge decision): "a card to start each server". Ambiguous. | **The owner's call** - owner question 9. |
| 6 | I07, the draft's state | Upkeep: the draft's patch no longer applies. | Confirmed on a scratch copy: `git apply --check` → "patch failed: jarvis_agent.py:743"; the code moved to `backend/jarvis_agent.py:3861`. The draft also lets listed tools go below "ask" (`jarvis_mcp.py:287-292`, `:468`) while its summary says every call raises a card (`DESIGN.md:23-24`). | **Upkeep and Security are right.** First step: move the draft into `backend/` where CI runs its tests, rewrite the wiring, keep `below_ask_ok` empty. Tell the owner MCP is large and needs ongoing upkeep. |
| 7 | I07, first server | Devil: "Everything" file search is better done directly (I39); git is rarely asked by voice. | Security agrees `es.exe` direct is the smaller surface. | **Devil is right about Everything** - do I39 with `es.exe`, no bridge. Ship the bridge with one server (git, read tools only, a version after its 2025-26 security fixes); its value is the servers that come later. |
| 8 | I53 email drafts | Rules/Security: card after outside text, AND when a saved sensitive fact, a note or a file went in. Devil: a card every time (a draft is uploaded to Google). Overwhelm: no objection to a card every time. | New finding: the shipped settings say `draft_email = "auto"` - no card at all (`backend/rebuilt/jarvis-framework.toml:96`), while `draft_email` is on the "never loosened from an app" list whose reason includes "anything that leaves the PC" (`backend/jarvis_asks_first.py:174-179`). Nothing uses `draft_email` yet (grep). | **The owner's call** (owner question 1). My recommendation: a card every time - drafts are rare and owner-asked, the text leaves the PC for Google's servers, and one rule is simpler than a conditional one. Either way, the "auto" line must be changed on purpose before drafts are wired in. |
| 9 | I14 screenshot text | Security: the research's plan puts the text into the owner's own typed message, so it would count as the owner's words. Others: "outside text", no detail. | `OWN_WORDS = {"typed", "voice"}` (`jarvis_agent.py:2385`); picture captions are a separate not-own-words kind (`:2386-2389`). | **Security is right.** The backend itself adds the OCR text as its own not-own-words part and marks the conversation tainted. Cap it at about 1,500 tokens and say when it was cut (Hardware). |
| 10 | I37 the overnight tidy, how many cards | Rules, Overwhelm, Devil: the research's "5 a night" does not fit the back-off's limit of 3 waiting; the tidy's cards ask for something not on the allowed list. | `MAX_WAITING = 3` (`backend/jarvis_backoff.py:88`); `MAY_ASK` has only "record a wish" and "save a routine" (`:154-159`). CLAUDE.md gives no number - only "cards only". | **Cap at 3 waiting**, one fact per card, a new declared kind "change one named fact, shown in full". Not an owner question: the 5 came from the research, not the owner. Show them as one "Tidy suggestions" list in Brain → Memory, on the quiet notification channel. |
| 11 | I61 the plan card | Fit/Rules: allowed by ARCHITECTURE's written meaning of "no approve-all", with conditions. Devil: close to "approves in bulk"; needs the owner. Security: only after the safety test (I95). | ARCHITECTURE "What no approve-all actually means" allows "one decision about one bounded set of things, every one of them shown in full"; CLAUDE.md says "Never build a control that ... approves in bulk". | **Both are partly right.** The written test allows it only with Rules' four conditions (every step shown as its own card would; a step filled in from an earlier step's result is asked again; risky steps always get their own card; grants nothing for later) and Security's (only from the owner's own words, no outside text in the turn). Because the owner wrote "approves in bulk" himself and this is a new kind of card, **the owner decides** (question 6). Build later either way, after the multi-step tool tests and I95. |
| 12 | I62 saved routines | Overwhelm, Devil: don't build (skills already exist). Fit: build later, but it must BE a skill. | Skills already save a repeated tool chain and still ask step by step (`backend/jarvis_skill_discovery.py:1-17`; `MAY_ASK["save_a_routine"]`, `jarvis_backoff.py:158`). Rules: a routine's lights would need a card anyway (the lights setting needs every device named in the newest message, `jarvis_agent.py:1183-1192`). | **Don't build as a separate thing.** Fold "Try it" and "read back each step" into skills later. |
| 13 | I63 goals | Devil: a plain repeating reminder already does this with no card. Others: build. | Plain repeating reminders need no card (CLAUDE.md, approvals audit). | **Devil is half right.** Goals add a deadline and a done/still-on-it status, which a reminder does not. Build later, one weekly check for all goals, landing in the briefing - not now. |
| 14 | I91 music and video control | Overwhelm: no card and no setting (like timers). Fit, Rules, Security, Devil: the lights pattern (a setting, off until turned on with a card). | Every card-free action so far has been an owner decision (CLAUDE.md, approvals audit). | **The owner's call** (question 10). Either way: play, pause, next and "what's playing" only; song titles are outside text. |
| 15 | I96 encrypted backup | Security, Devil, Overwhelm, Upkeep, Fit: build. Rules: later (Erase wording). | Security: the backup includes the tier settings file, so a restore could loosen tiers (research claim, not re-checked by me). | **Build now**, with Rules' and Security's conditions: Erase's "are you sure?" says old backups still hold the words until replaced; backups rotate; a restore never loosens a tier or a "What asks first" line (it keeps the stricter one or lists each loosening on its card); restore = one card plus Windows Hello. Where it goes is question 4. |
| 16 | I98 watchdog (and I111, I71) | Security: taint is forgotten on restart, so routine restarts make the tool loop "fail open". Others: safe. | Taint is in memory only; "a restart forgets them all" (`jarvis_chat_log.py:520-522`, `:586-589`); `_conversation_tainted` returns False on any error (`jarvis_agent.py:2492-2501`). The lights-without-card rule depends on it (`jarvis_agent.py:1185-1188`). | **Security is right** - no other reviewer showed taint surviving a restart. Fix it first (step 0): seed taint from history's per-turn `tainted` column; with history off, treat an unknown conversation that has earlier Jarvis answers as tainted. |
| 17 | I100 crash dumps | Rules, Security, Upkeep, Devil: don't build (a dump can hold the pairing token). | - | **Don't build** as a standing setting. A one-off, owner-started capture, deleted after, is fine if ever needed. |
| 18 | I104-I108 extra injection defences | Hardware/Upkeep/Devil: don't build I106, I108 (and Devil I107). Fit/Rules/Security: build later after I95. | No reviewer said these are unsafe - they are extra defences, so the question is cost and value. I106 adds 3-8 s per card after outside text (Hardware estimate); I108 duplicates the existing planted-instruction flag (`jarvis_agent.py`, `injection_flags`, shown on the card per Fit). | **I106 and I108: don't build.** I104, I105, I107: build later, and only the ones I95's numbers show help (Upkeep: at most two). |
| 19 | One warning slot per card | Overwhelm: merge warnings; Security might see that as hiding detail. | - | **Both satisfied:** one slot, strongest warning first, "and N more" on tap. Nothing is dropped. |
| 20 | I110 slower Approve | Overwhelm, Devil: risky cards only. Security: "stricter only" (did not ask for every card). | - | **Risky cards only.** |
| 21 | I111 pinning | Upkeep: pin now, before a dozen new packages arrive. Fit/Devil: later. | `backend/requirements.txt` pins only `ddgs>=9.16.0`; nothing scans Python packages (per Upkeep; I confirmed the file has no other versions). | **Upkeep is right for the pinning half** (step 0). The staged updater waits for the taint fix and for the backend's own code to have a second copy (Devil's point: `docs/ARCHITECTURE.md` says the backend has no version control). |
| 22 | I73 phone notifications | Hardware, Rules, Security: text stays on the phone; only app and sender are matched there; text reaches the PC only for a request the owner makes. Fit: "tell me when" matching lives on the PC. | Owner: "shown or summarised only when the owner asks; nothing leaves the owner's own devices" (CLAUDE.md). | **Keep text on the phone until asked** - it fits the owner's words and is the least data. "Tell me when" rules match app + sender on the phone and send only that. No owner question needed: this is stricter, inside his decision. |
| 23 | I66 folder "tell me when" | Devil: a new always-running file watcher. Fit: a polling check on the scheduler, not a watcher thread. Upkeep: refactor "tell me when" first. | `jarvis_tellme.py` branches on its two sources by name in many places (per Upkeep, e.g. `:249`, `:304`, `:310`). | **Fit and Upkeep:** build later, after the sources are made a list; the folder is looked at by the scheduler's check, no watcher thread. |
| 24 | I117 Today page | Overwhelm: build, as the one home for "my day". Devil: don't (a fourth summary). Fit: later. | The phone's Inbox is already "one screen rather than three" (`InboxScreen.kt:41-49`). | **Build later**, and only by growing the phone's Inbox and the desktop's Coming up - replacing, never adding. |
| 25 | I19 household sounds | Overwhelm, Devil: don't. Fit, Rules, Security, Upkeep: later. | The desktop's listener already runs when hands-free is on (ARCHITECTURE, "the desktop's listener is always listening"). | **Don't build now.** A permanently analysed microphone for a "not a safety device" alert is much for little. Revisit if the owner names a need (e.g. someone in the house who is hard of hearing). |
| 26 | I47 / I48 bookmarks and browser history | Devil: don't (the browser does it). Rules/Security: later with a narrow reader. Overwhelm/Upkeep/Fit: don't build I48. | `file_read` refuses browser profile folders on purpose (`jarvis_agent.py:211-214`). | **Don't build either.** Keeps those folders fully closed; the browser already searches both. |
| 27 | I24 / I29 new voice and pictures on the 12 GB card | Upkeep, Devil: don't (heavy PyTorch stacks). Others: later. | `LONG_BIG = ("qwen3:8b", 32768, 7.69)` (`jarvis_second_card.py:198`); F5 needs 3,072 MB (`jarvis_voices.py:151`). | **Later, and only if the owner picks that purpose for the card** (question 7). |
| 28 | I22 speech detector in the apps | Hardware: build (saves phone battery). Devil: small gain. | The PC already runs Silero and refuses a noise-only clip before anything else (`backend/jarvis_speech.py:42-44`, `:1543-1547`); the desktop's trigger is loudness, then Silero decides (`jarvis-desktop/src-tauri/src/voice.rs:59-66`). | **Devil.** Later, in one measured round of the listening front end. |
| 29 | I151 crisis help line | Fit/Upkeep: reuse the existing word list. Devil: that list's `suicid\w*` fires on "Suicide Squad". Rules: "logs nothing" is untrue while history is on. | `r"suicid\w*"` at `backend/jarvis_sensitive.py:192` (master list said `:190`). Chat history is kept by default (CLAUDE.md, 2026-09-24). | **All three are right.** One source file, but the crisis check uses its own named phrase list with a false-alarm test; the wording says "keeps no separate record". The number is question 8. |
| 30 | I09 model shortlist | Security: later (a crafted model file is a risk). Hardware, Devil: build (the smaller 8B file may give 12K of working memory on today's card). | - | **Build now, as a test**, with Security's guardrail: official `library/` models only (Ollama checks each download's fingerprint), no loose files, refuse cloud names. 2-3 models, not more. |
| 31 | I88 "a home that learns routines" | Everyone: don't build as written. | An automation Jarvis writes runs forever with no card - a standing grant (ARCHITECTURE "no approve-all"). | **Don't build.** The safe later form: Jarvis shows the automation text and the owner adds it in Home Assistant himself. |
| 32 | I89 "wake my PC" | Rules: the away-from-home route would put the first key on the phone, and a PC that is off means a stale link. | Keys are PC-only today (`docs/JARVIS-API.md:4264`, "no field and no route for a key"). | **Later**, home Wi-Fi only first (no key). Away from home: open Home Assistant's own app. |
| 33 | I77 vs I81 (HA device list vs a non-admin HA user) | Security: HA's exposed-devices list needs an admin token (research's claim, not checked); I81 removes admin. | Not checked (Home Assistant is not in the repo). | **Side with I81.** I77 don't build. |
| 34 | I13 power limit | Security: the admin logon task must run `nvidia-smi.exe` by its full system path with fixed numbers, never a script the owner's account can edit. Devil: a standing admin job for a few watts. | - | **Later, low priority**, with Security's guardrail if ever. |
| 35 | I18 name hints | Devil: don't (invented names ~20% of the time). Overwhelm: no switch. Others: later. | Report's claim, not checked. | **Later, only once the upstream bug is fixed**, then measured and shipped with no switch. |

### 1.3 Objections every reviewer should hear (adopted as rules for the whole set)

- **Price every idea against the real ~8K, not 16K** (Hardware, Devil). Adopted.
- **One rule for background model jobs, not a setting** (Hardware 5): they run only when Jarvis has been idle a few minutes, never during a voice turn, never in standby hours. Overwhelm confirmed it needs no switch. Adopted.
- **Read the PC's RAM before adding more than two or three processor models** (Hardware 6). Nobody wrote the RAM down. Adopted: a preflight line.
- **"Measure first" is empty unless someone runs it** (Upkeep 9). Adopted: one command runs every measurement, results are dated, the preflight shows their age. The memory scoreboard (`docs/MEMORY-SCOREBOARD.md`, being written now, not yet committed) is the model.
- **Refactor "tell me when" into a list of sources before the third one** (Upkeep 3). Adopted.
- **Read the owner-only modules before extending them** (Fit 11): `jarvis_undo`, `jarvis_ledger`, `jarvis_watch` (ARCHITECTURE: "present, but only on the owner's PC ... unverified from here") and `jarvis_persona` (not in the repo, `git ls-files`). I65, I70, I109, I137/I138 wait on this.
- **Lists the phone shows come from the PC** (Upkeep 8, Fit 8): the phone hard-codes the two manners (`jarvis-client/.../net/Manner.kt:26`), so any new preset is a phone release. Adopted.
- **One folder list** for files, documents, the library, the folder watch and the Notion import (Overwhelm, Fit). Adopted.
- **One protected-paths list, read by both the backend and the desktop's Rust** (Security 6). Adopted.

---

## 2. Verdicts - one line per idea

**Now** = build as soon as its turn in section 3 comes. For ideas the owner has not chosen yet, "Now" is a recommendation (question 3). **Later** = says what it waits for. **No** = don't build. **Done** = already built, or nothing to build.

"Owner chose" marks the owner's own decisions (CLAUDE.md, 2026-09-26). Those are reviewed for HOW, not whether.

### Engine

| Id | Idea | Verdict | Reason | Guardrails / waits for |
|---|---|---|---|---|
| I01 | Check the model can use tools | **Done** | Built, `f973178` (`jarvis_agent.py:1996-2013`). | Add a preflight WARN when Ollama does not say. |
| I02 | `OLLAMA_NO_CLOUD=1` | **Done** | Built, `f973178`. | Check on the PC that installing a model still works; preflight reads the setting (never by sending a real chat to a cloud name). |
| I03 | Record prompt reuse every turn | **Now** (first) | The ruler for I06, I07, I129 and I107. | Numbers only, never text; "not reported" if Ollama leaves the field out. |
| I04 | "Fill in this form" retry | **Later** | Waits for I05 to count how often arguments are broken. | Still exactly one retry, through the gate; the form must allow "I need to ask the owner". |
| I05 | "Ask, don't guess" and multi-step tests (owner chose) | **Now** | One harness with I95 and I133. | PC only; made-up data. |
| I06 | Short tool list (owner chose) | **Now** | Tools take 35-45% of the real room. | Fixed core, fixed order; opened groups stay for the chat; never offers a disabled tool or one the lane may not use; measure with I03 and I05. |
| I07 | MCP bridge (owner chose) | **Now** (last in its group) | Owner chose; large, with upkeep. | Stdio on this PC only; draft moved into `backend/` and CI first; installed once, exact versions and hashes, never fetched at start (`npx`/`uvx`); `below_ask_ok` empty; results are outside text and taint the conversation; environment allow-list (no token, no passwords); one server first (git, read tools only). |
| I08 | MTP speed-up | **Later** | Second card and a Qwen 3.5 switch; the 1.5-2x claim comes from a 27B on newer cards. | Measure with I03; one-line off switch. |
| I09 | Model shortlist test | **Now** (test only) | May give 12K of working memory on today's card. | Official `library/` models only; refuse cloud names; 2-3 models; nothing switches without the owner. |
| I10 | One model for long talks and pictures | **Later** | Second card, measured. | Existing model-switch card. |
| I11 | Picture-based pointer that clicks | **Later** | Second card, and only after I27 shows the pointing is accurate. | Crop on the card; re-check before click; never on Jarvis's own windows. |
| I12 | Health readings for both cards | **Now** | Desktop reads only the first card (`commands.rs:2617`); needed before the 2060. | Local `nvidia-smi` only; no new notification. |
| I13 | Measured power limit | **Later** | Low value; the 2060 part waits for the card. | Admin task runs `nvidia-smi.exe` by full path with fixed numbers; Jarvis never elevated. |

### Voice and vision

| Id | Idea | Verdict | Reason | Guardrails / waits for |
|---|---|---|---|---|
| I14 | Read screenshot text (OCR) (owner chose) | **Now** | Works with no graphics card. | Backend adds the text as not-own-words and taints the chat; cap ~1,500 tokens; RapidOCR pinned (CI can test it); never learned. |
| I15 | Newer "Hey Jarvis" detector (owner chose) | **Now** (as a bake-off) | The 100x claim is on another phrase. | Keep today's model unless the owner's own clips win; train in a separate environment; same file hash in both apps. |
| I16 | Pocket TTS voice copy (owner chose) | **Now** (as a bake-off) | The 0.2 s claim is from an Apple laptop. | Replaces ZipVoice if it wins, never a third engine on screen; sherpa-onnx ≥1.12.24 in requirements; weights downloaded by hand, hash-pinned; same consent card. |
| I17 | Kokoro on the graphics card | **Later** | Second card; measure Kokoro on the 3900X first. | - |
| I18 | Name hints for speech-to-text | **Later** | Upstream bug gives empty/invented text. | Then measured, no switch. |
| I19 | Household sounds | **No** | A continuously analysed mic for a "not a safety device" alert. | Revisit only on the owner's request. |
| I20 | Document model for photos | **Later** | Only if I10's model is weak at documents. | Outside text. |
| I21 | Noise clean-up | **Later** | Only if word errors drop. | After the voice check. |
| I22 | Neural speech detector in the apps | **Later** | The PC already filters noise with Silero. | One measured round with the listening front end; prefer Silero (TEN's licence has extra terms). |
| I23 | Stronger voice-ID model | **Later** | Only if the owner's numbers show others getting in. | Own measured limits. |
| I24 | Better voice on the 12 GB card | **Later** | Question 7; would replace F5. | safetensors only; never `trust_remote_code`. |
| I25 | Fake-voice detector | **No** | No reliable local detector exists (research). | - |
| I26 | "Say these 3 words" check | **Later** | Only if hands-free is ever trusted with more. | Never approve-by-voice; words shown, never spoken. |
| I27 | "Show me where to click" | **Later** | Second card (needs a seeing model). | Screenshot local only; acts on nothing. |
| I28 | Speaking-speed setting | **Now** | The setting exists but no app shows it (`jarvis_voices.py:251-252`; no hit in either app). | No card; allowed values served by the PC. |
| I29 | Make and edit pictures | **Later** | Question 7. | Pinned build; refuse face swaps of real people. |
| I30 | Make music | **No** | Fun, heavy, a new download stack. | - |

### Memory

| Id | Idea | Verdict | Reason | Guardrails / waits for |
|---|---|---|---|---|
| I31 | Re-ranker | **Done** + fix now | Merged; on by default and unmeasured. | Off by default until the PC self-test shows a gain (owner's rule); then ≤0.3 s wait on spoken turns; pin fastembed. |
| I32 | Bigger self-test | **Done** | Merged. | The owner runs it on the PC (the one line in `docs/MEMORY-SCOREBOARD.md`). |
| I33 | "Said again" | **Done** | Merged. | - |
| I34 | "True from" dates | **Done** | Merged. | - |
| I35 | Search hints | **Later** | After the re-ranker's PC numbers. | Erase and Forget wipe the hints; never shown. |
| I36 | Date-closeness boost | **Later** | After I34's PC numbers; must beat the self-test. | Reuse `jarvis_past.py`'s date parser. |
| I37 | Overnight tidy (owner chose) | **Now** (after the PC self-test run) | Owner: tidy after ideas 1-4 are measured. | Cards only; at most 3 waiting; one fact per card; new declared offer kind; quiet channel; one list in Brain → Memory; never in Quiet/Standby; runs before standby. |
| I38 | Search own past chat words | **Later** | Owner said wait. | Only `typed`/`voice` turns; outside text; nothing saved. |

### Knowledge and documents

| Id | Idea | Verdict | Reason | Guardrails / waits for |
|---|---|---|---|---|
| I39 | "Where's that file?" | **Now** | Asked often, answered in under a second. | `es.exe` by full path; one folder list; protected-paths filter; warn if Everything's network server is on; outside text; local model. |
| I40 | Documents to text, read in slices (owner chose) | **Now** | Owner chose. | Only MarkItDown's document extras, pinned (never audio/YouTube); pdfminer.six at a fixed version (public advisory); child process with no secrets, time and size caps; file paths only; slices ≤1,500 tokens; its own file, not the `documents` table. |
| N1 | Notion export import (owner chose; missing from the master list) | **Now** (with I40) | Owner chose (CLAUDE.md, 2026-09-26). | Same folder list; outside text, never learned; notes written back ask. |
| I41 | One local library index | **Later** | Only if I40's slice search is not enough. | None indexed by default; one delete button. |
| I42 | "Where this came from" + quote check | **Now** | Straight at trustworthy answers. | From tool results only; one collapsed "Used: ..." line with memories; "not a direct quote", never "false". |
| I43 | Reading list in the daily note | **Later** | Low value. | Never fetches the page. |
| I44 | Wiki next steps | **Later** | The wiki builder is not yet run against a real model. | Fixes through the wiki card. |
| I45 | Spreadsheet questions (DuckDB) | **Later** | Rare; a new engine to keep locked down. | One owner-named file; one SELECT; no files/network/extensions; caps. |
| I46 | Transcribe an audio/video file | **Later** | Rare; long job. | Tagged `shared`, never `voice` (test it); ffmpeg with network off; paused during voice turns. |
| I47 | Bookmarks Q&A | **No** | Browser does it; keeps profile folders closed. | - |
| I48 | Browser history Q&A | **No** | Very private; browser does it; upkeep forever. | - |
| I49 | News headlines | **Later** | Question 12 (decide with I67). | Egress row; one card per feed; headlines only. |
| I50 | "Open in Obsidian" | **Later** | The button only; no second galaxy. | Desktop only. |
| I51 | Obsidian CLI, allow-listed | **Later** | Not checked whether Obsidian must be running. | Fixed read commands; never `eval`. |
| I52 | Detect Logseq database graphs | **Later** | Only if the owner uses them (not known). | Detect and say; the MCP half waits for question 2. |
| I53 | Email draft to Drafts (owner chose) | **Now** (after question 1) | Owner chose. | Change the shipped `draft_email = "auto"` on purpose first; egress row; IMAP APPEND to `\Drafts` only; no attachments; local model only. |
| I54 | Contacts from a `.vcf` | **Later** | Small gain. | Never learned; never read aloud. |
| I55 | CalDAV writes | **No** | The owner's calendar is Google, read-only. | - |
| I56 | Scan to Obsidian | **Later** | Only if the owner has a scanner (not known). | OCR text is outside text. |
| I57 | Quiz me (FSRS) | **No** | A daily-prompt machine and a new dependency for a rarely-used feature. | - |
| I58 | "Translate this" | **No** | Nothing to build: the model translates when asked. | - |
| I59 | Language practice | **No** | Typed works in a temporary chat today; spoken is impossible (English-only speech model). | - |
| I60 | Code helper | **No** | The model explains errors already; an editor is a separate, risky decision. | - |

### Routines and agents

| Id | Idea | Verdict | Reason | Guardrails / waits for |
|---|---|---|---|---|
| I61 | Plan card | **Later** | Question 6; I05 multi-step cases; I95. | Rules' four conditions; owner's own words only, no outside text. |
| I62 | Saved routines | **No** | Skills already are this. | Improve skills instead. |
| I63 | Goals, stage 1 | **Later** | A reminder covers most of it; not urgent. | One weekly check for all goals; in the briefing. |
| I64 | Goals, stages 2-3 | **Later** | After I63; second card. | Accepting a plan runs nothing. |
| I65 | Undo on the card | **Later** | Read the owner's `jarvis_undo` first. | Undo gets a card; "cannot be undone" said plainly. |
| I66 | "Tell me when" for a folder / the calendar | **Later** | After the sources refactor. | Scheduler check, no watcher thread; folder from the one list. |
| I67 | Web page change watch | **Later** | Question 12. | Egress row; refuse home-network addresses after lookup; hash only. |
| I68 | Instant email (IMAP IDLE) (owner chose) | **Now** | Owner chose. | IMAPClient pinned (or a hand loop); `EXAMINE`/`PEEK` only; each fetch through the gate; renew before ~29 min; on any drop fall back to 5-minute looks and say so; closed on Stop everything, Standby and the end date. |
| I69 | "Tell me if X hasn't replied by Friday" | **Now** (with I68) | Tiny, same match. | Notifies only. |
| I70 | GitHub "tell me when" | **Later** | Read the owner's `jarvis_watch` first; merge. | Read-only token for one repo, in Credential Manager, only to `api.github.com`. |
| I71 | Night shift | **Later** | Second card; taint fix; big-model standby. | Only before standby; acts wait for a morning card; big model given a thread limit or low priority. |
| I72 | Research helper | **Later** | An 8B on snippets will often say "not found". | One card with exact search words; no loop; snippets only. |
| I73 | Phone notifications (owner chose, queued) | **Later** | Owner queued it after the four groups and the security audit. | Empty app list by default, banking refused; codes hidden on the phone; text stays on the phone until asked; outside text, never saved, never acts; never SMS. |
| I74 | Weekly journal | **Later** | Needs the history-as-source decision (with I38). | Saved after a card. |

### Home and the PC

| Id | Idea | Verdict | Reason | Guardrails / waits for |
|---|---|---|---|---|
| I75 | Weather from Home Assistant (owner chose) | **Now** | Fills "not available" (`jarvis_briefing.py:117-118`, `:338`). | A separate plan that can call exactly `weather.get_forecasts`, never through `home_control`; test that nothing else is reachable; outside text. |
| I76 | "Why did the light turn on?" | **Later** | Modest value. | Outside text. |
| I77 | HA's exposed-devices list | **No** | Needs an admin token (claim) and HA's MCP has no entity ids. | - |
| I78 | Rooms and floors | **Later** | A new WebSocket client. | A room is always one card listing every device, at most ten. |
| I79 | Room awareness | **Later** | After I102 (needs per-device keys). | Only ever quieter. |
| I80 | "Goes through the maker's cloud" line | **Later** | After I78. | - |
| I81 | Non-admin HA user | **Now** | Shrinks what a leaked token can do. | Preflight WARN on an admin token; guide in docs. |
| I82 | "Someone at the door" | **Now** (docs and a phrase) | Already works. | Labels only; suggest a 10-minute gap between repeats. |
| I83 | Camera snapshot | **Later** | Second card for the model part. | Own card; never on disk; hidden under App lock. |
| I84 | "What did Jarvis cost today?" | **No** | Asked once; leaves out the processor. | - |
| I85 | Welcome home | **No** | Duplicates "What did I miss?". | - |
| I86 | Printer / weather station / car levels | **Later** | Only for devices the owner has. | Read-only; only when notable. |
| I87 | Shopping list mirrored to HA | **Later** | Owner's card-or-setting choice when built. | Mirror the existing named lists. |
| I88 | Home that learns routines | **No** | A standing grant. | Safe later form: Jarvis shows the text, the owner adds it. |
| I89 | Wake my PC | **Later** | Home Wi-Fi only first. | Never a router port-forward; no key on the phone. |
| I90 | Sleep the PC | **No** | The PC is Jarvis's only clock; admin need unverified; I93 covers alarms. | - |
| I91 | Music and video control | **Later** | Question 10. | Play/pause/next only; titles are outside text. |
| I92 | winget updates | **Later** | List only. | Updating stays a line the owner runs; never "update all". |
| I93 | "Also on my phone" (owner chose) | **Now** | Owner chose. | The owner's tap is the approval; the button warns about two alarms and that the phone's calendar may copy the event to Google. |
| I94 | "Text Mum" SMS draft | **Later** | Low priority. | Never sends; never reads SMS. |

### Trust and safety

| Id | Idea | Verdict | Reason | Guardrails / waits for |
|---|---|---|---|---|
| I95 | Planted-instruction test on the real model | **Now** | Decides I104-I108. | Offline on the PC; attack texts never reach real tools; overnight. |
| I96 | Encrypted backup + restore | **Now** | Memory and history cannot be re-made. | Question 4 (where); code shown once; restore never loosens a tier; card + Windows Hello; Erase warns about old backups. |
| I97 | Data health in the preflight | **Now** | Small, read-only. | WARN, never fix. |
| I98 | Watchdog restart | **Now** (after the taint fix) | Small. | At most 3 in 10 minutes, then stop and say so; nothing resumes by itself. |
| I99 | Hang and crash notes | **Now** | Small. | Rust panic text through the scrubber; newest 10. |
| I100 | Windows crash dumps | **No** | A dump can hold the token (rule 3). | One-off by hand only. |
| I101 | History key in the security chip | **Later** | After I96. | - |
| I102 | QR pairing, per-device keys (owner chose) | **Now** | Owner chose. | As designed; backend stores only a hash of each device token; retire date for the old shared token. |
| I103 | Fingerprint-signed yes from the phone (owner chose) | **Now** (with I102) | Owner chose. | Signs card id + one-time number + hash of the card's words; refuses replays. |
| I104 | Sensitive-argument labels | **Later** | After I95. | Stricter only; one warning slot. |
| I105 | Tool-less reader pass | **Later** | Only if I95 shows fewer attacker cards. | Reader has no tools. |
| I106 | Masked re-run (MELON) | **No** | +3-8 s per card after outside text on the 8 GB card. | Revisit only if I95 shows nothing else works. |
| I107 | Datamarking | **Later** | Measured with I95 (may hurt reading, costs tokens). | - |
| I108 | Injection classifier | **No** | Duplicates the existing planted-instruction flag; licence unchecked. | - |
| I109 | Decision counts | **Later** | Read the owner's `jarvis_ledger` first. | Counts only; Trust tab only; never a nag. |
| I110 | Slower Approve on risky cards | **Now** | Stops rubber-stamping. | Risky cards only; both apps. |
| I111 | Safer backend updates | **Now** (pinning half) / **Later** (staged switch) | Pin before new packages. | Hash-locked requirements, advisory scan in CI, monthly pin update; staged switch after the taint fix. |
| I112 | `tailscale whois`, Tailnet Lock | **Later** | After I102. | Advice, never a grant. |
| I113 | Notifications local; widget off lock screen | **Done** (+ one check) | Notification half merged (`d1af3c7`); widgets already declare `home_screen` only (`widget_approval_info.xml:18`). | Check on a real Android 16 phone; question 11 (alarms on a watch). |
| I114 | "Private copy" | **Now** | Windows clipboard sync can carry a copied answer off the PC. | Needs a small Rust command (Devil); hide preview on the phone. |
| I115 | Paste guard | **Now** | Keeps pasted passwords out of stored history. | Reuse `jarvis_sensitive`/`jarvis_mail_mask` patterns. |

### Experience

| Id | Idea | Verdict | Reason | Guardrails / waits for |
|---|---|---|---|---|
| I116 | "Things you can say" | **Now** | Makes the fastest, no-model commands findable. | Served by the PC; fills the box, never sends. |
| I117 | Today page | **Later** | Only as the Inbox/Coming up grown, never a fourth view. | Never an Approve. |
| I118 | "Close the day" | **Later** | After I117. | Owner's own words only. |
| I119 | Preflight in Settings with "Fix" | **Later** | After I102; not "first run" - the owner is set up. | A Fix never skips its card. |
| I120 | "Send to → Jarvis" | **Later** | Nice, not core. | Tagged `shared`; protected paths refused; waits for Enter. |
| I121 | Share a document from the phone | **Later** | After I40. | Own upload route; size cap. |
| I122 | Follow Windows Focus; phone tile | **Later** | Not checked that Windows exposes Focus state. | Off by default; read only. |
| I123 | Phone Do Not Disturb | **Later** | After focus sessions prove used. | Alarms and urgent alerts get through. |
| I124 | Live countdown | **Later** | Two code paths on the phone. | Label hidden on a locked screen. |
| I125 | App-icon shortcuts | **Now** | Small; bundle with other phone changes (one CI round). | Meets App lock. |
| I126 | Glance 1.2 + Today widget | **Later** | Touches both widgets. | Counts only; off the lock screen. |
| I127 | Accessibility pass | **Later** | Bundle with the next screen batch. | - |
| I128 | Windows package identity | **No** | Large packaging change for a beginner. | - |

### Personality and character

| Id | Idea | Verdict | Reason | Guardrails / waits for |
|---|---|---|---|---|
| I129 | Character block; fix the rules allowance | **Now** (the fix) | The flat 300-token allowance (`jarvis_agent.py:2044`, used `:3033`, `:3549`) is a real bug. | Keep the block short (~270 tokens = ~3-4% of 8K); keep it only if I133 shows a gain; change both copies of the rules. |
| I130 | Two example exchanges | **Later** | After I133. | - |
| I131 | Fixed "who are you" answers | **Now** | Instant, honest, no model. | Fixed text; no romance. |
| I132 | "You told me" check | **Now** | Catches a damaging false claim. | Part of the one "Used: ..." line. |
| I133 | One behaviour test | **Now** | One tool, not three. | PC only; fixed checks, no 8B judging an 8B. |
| I134 | Preflight: model runs today's rules | **Now** (with I129) | Catches a stale model. | WARN only. |
| I135 | Style test for fixed lines | **Now** | Cheap. | - |
| I136 | "Patient teacher" | **Later** | As a third preset, once presets come from the PC. | - |
| I137 | Humour setting | **Later** | After I133 shows no harm; the owner's taste (later question). | Never on cards or serious topics. |
| I138 | Presets and dials | **Later** | Trimmed: 3 presets + "Call me", ≤3 dials folded away; after I145. | 900-character cap by test. |
| I139 | "How Jarvis talks to you" list | **Later** | With I138. | - |
| I140 | "From now on ..." | **Later** | "Call me" first. | Owner's live words only. |
| I141 | "Just this chat", counted | **No** | Machinery for a preference the owner can simply say. | - |
| I142 | "Between us" label | **No** | Already an ordinary memory. | - |
| I143 | "Your words" style notes | **No** | The one place owner text becomes an instruction; small gain. | - |
| I144 | Briefer during focus | **Now** | Saves tokens and time. | Saved setting untouched. |
| I145 | Settle the old persona modes | **Now** (look first) | Eight unseen modes could conflict. | Needs the owner's `jarvis_persona.py`. |
| I146 | Games in a temporary chat | **No** | Temporary chats already exist. | - |
| I147 | Face follows voice shape | **Later** | Nice, not core. | Flash limits. |
| I148 | Idle life for the face | **Later** | Nice, not core. | Reduced motion. |
| I149 | Lip-sync | **No** | No face with a mouth. | - |
| I150 | The name "Jarvis" (guidance) | **Done** | Guidance only. | Keep away from Marvel styling, "sir", film lines. |

### Wellbeing

| Id | Idea | Verdict | Reason | Guardrails / waits for |
|---|---|---|---|---|
| I151 | Crisis help line | **Now** | Nothing handles it today. | Own phrase list with a false-alarm test ("Suicide Squad"); no tools that turn; contacts no one; "keeps no separate record"; number = question 8, in one file with a "checked on" date. |
| I152 | Distress words off the cloud offer | **Now** | Small; latent today (no cloud lane). | Same source as I151. |
| I153 | Feelings and goodbye lines | **Later** | Fold into I129; measured by I133. | - |
| I154 | Moods are not facts | **Now** | Small, stricter. | No mood log. |
| I155 | Outside test kits | **No** | Default to a cloud judge; I133 covers it. | - |

**Counts (156 lines, tallied from the table):** Now **46** · Later **76** · No **26** · Done **8**.

- Done: I01, I02, I31 (with a fix: off until measured), I32, I33, I34, I113 (with one phone check), I150 (guidance).
- Now, owner chose (15): I05, I06, I07, I14, I15, I16, I37, I40, N1, I53, I68, I75, I93, I102, I103.
- Now, recommended but not yet chosen (31): I03, I09, I12, I28, I39, I42, I69, I81, I82, I95, I96, I97, I98, I99, I110, I111 (pinning half), I114, I115, I116, I125, I129, I131, I132, I133, I134, I135, I144, I145, I151, I152, I154.
- Owner chose but Later: I73 (owner queued it after the four groups and the security audit), I38 (owner said wait).

---

## 3. Build order

This respects: the four groups the owner chose (CLAUDE.md, cutting-edge decision), memory running alongside them (CLAUDE.md, "Memory and learning run now"), phone notifications after the four groups and the security audit, the second card's timing, and what is being built right now (the memory scoreboard, `docs/MEMORY-SCOREBOARD.md`, uncommitted; a desktop look fix in the `ui-lookfix` worktree).

**Step 0 - fix today's code first (bug fixes, no new features):**
1. Taint survives a restart (Security G1; `jarvis_chat_log.py:520-522`). Blocks I98, I111's staged switch and I71.
2. Re-ranker off by default until the PC self-test (`rebuilt/jarvis_memory.py:505`); fix the README's "It never makes a chat wait" - it waits up to 1.5 s (`:641`).
3. Set `draft_email` in the shipped settings on purpose (`rebuilt/jarvis-framework.toml:96` says "auto") - before I53.
4. Close the holes in `file_read`'s refusal list (`jarvis_agent.py:207-222`): the phone-control key `~/.android/adbkey`, Android/Java key stores, Thunderbird, Chrome Beta/Canary, Discord/Signal data, `.cargo/credentials`, `.git/config` with a token (Security G2). One list, shared with the desktop's Rust later.
5. Pin Python packages with hashes and add a Python advisory scan to CI (I111, first half).
6. I03 (measure prompt reuse) - the ruler for everything below.
7. **Owner action:** run the memory self-test on the PC (the one line in `docs/MEMORY-SCOREBOARD.md`) and send back the result.

**Step 1 - Quick wins (owner chose):** I75 weather (with I81, the non-admin HA user), I93 "Also on my phone", I14 screenshot text. Also I12 (both cards' health, before the 2060 arrives).

**Step 2 - Smarter tools (owner chose):** one test harness for I05 + I95 + I133 → I06 short tool list (measured with I03) → move the MCP draft into `backend/` and CI → I07 with one stdio server (after question 2). I09 (model shortlist test) can run overnight here.

**Step 3 - Voice upgrades (owner chose):** I15 and I16 as bake-offs that can end in "keep what we have". I28 (speaking speed) rides along in the same voice-settings change.

**Step 4 - Documents and email (owner chose):** I40 + the Notion import + I39, sharing one folder list → I68 + I69 instant email → I53 drafts (after question 1 and step 0.3).

**Alongside steps 1-4 - memory (owner chose "now"):** once the PC numbers are in: I37 the overnight tidy (cap 3). Then, only if the numbers ask for it: I36, I35. I38 waits, as the owner said.

**Step 5 - small safety and quality items (question 3 asks to add these to the queue):** I129 (the allowance fix) + I134; I131, I132, I135, I144, I145 (needs the owner's `jarvis_persona.py`); I151, I152, I154; I96 backup, I97, I98 (after step 0.1), I99; I110, I114, I115; I42; I116; I125 bundled with another phone change. Moving service passwords from Windows user settings into Credential Manager (Security G3) belongs here, before any new key.

**Step 6 - the security audit the owner queued, then "more devices":** I102 + I103 (owner chose; large). Then I73 phone notifications (owner queued after the four groups and the security audit). I79, I112, I119 come after I102.

**Step 7 - when the 12 GB card is installed:** measure it first (the Hardware screen's Measure), then the owner's answer to question 7 decides the order among I10, I27, I17, I08, and possibly I24 or I29. I20, I44's model part, I64 stage 3, I71, I83's model part, I11 (after I27) follow.

**Later, in dependency order:** tellme sources refactor → I66, I70 (after reading `jarvis_watch`); read `jarvis_undo`/`jarvis_ledger` → I65, I109; I95's numbers → I104, I105, I107; I61 (after question 6 and I05's multi-step cases) → nothing else depends on it; I117 → I118; I138 trimmed (after the phone draws presets from the PC) → I136, I139, I140, I137.

---

## 4. Keep Jarvis simple - guardrails for the whole set

1. **One home per kind of thing.** Every "does it ask?" is a row in "What asks first". Every watched thing is a "tell me when" source. Every timed thing is one scheduler kind. Every folder is in one "Folders Jarvis may look in" list (PC only, empty by default). Every unasked suggestion goes through the back-off and shares its 3 slots.
2. **Invisible upgrades get no switch.** A new model, detector, voice engine or speed-up is measured, then shipped or dropped. A switch the owner cannot judge is a question pushed onto him.
3. **Replace, don't add.** A winning voice, wake detector or model replaces the old one on screen.
4. **Off by default; turning something looser is a card; turning it stricter is instant** - the existing pattern, unchanged.
5. **No new daily card, and nothing new speaks unasked.** New card kinds must be rare (setup time) or owner-asked.
6. **One line under an answer, one warning slot on a card.** Memories, sources and "no saved fact was used" share one collapsed "Used: ..." line; warnings show the strongest first and "and N more".
7. **Every idea that adds words to every turn names its cost against the real ~8K** and is kept only if a test shows it helps.
8. **Background model jobs run only when Jarvis is idle** - never during a voice turn, never in standby hours. A written rule, not a setting.
9. **Pin, then add.** Every new package: pinned with a hash, a preflight line when it is missing ("off: X is not installed"), and never a download at start-up.
10. **Every "measure first" result is dated**, one command runs them all, the preflight shows their age.
11. **Lists the phone shows come from the PC** (presets, commands, apps), so adding one needs no phone release.
12. **One source for each word list** (sensitive, private, crisis, one-time codes) - never a hand-synced copy.
13. **Budget check per batch:** each feature audit counts new settings, card kinds, notifications and pages; more than 2 new settings or 1 new card kind in a batch needs a written reason.

---

## 5. Questions for the owner

Most important first. Ask two at a time (CLAUDE.md: "One or two questions at a time").

**1. Email drafts.** When Jarvis saves a draft to your Gmail Drafts folder, the text goes up to Google's servers.
- **A card every time, showing the full draft** (recommended)
- A card only if Jarvis read an email, web page or file in that chat, or used a private saved fact

**2. Plug-in servers ("MCP").** You said "local servers only". Some plug-ins are small programs on this PC; others run as a web service (Logseq's, Home Assistant's).
- **Programs on this PC only, for now** (recommended)
- Also services on this PC's own address, such as Logseq's

**3. The new small items.** 31 small items are marked "Now" that you have not chosen yet (backup, crisis help line, "who are you" answers, both graphics cards' health, and so on - listed under the counts in section 2).
- **Add them to the queue after your four groups** (recommended)
- Only the four groups for now; ask me again later

**4. Backups.** Jarvis would keep one encrypted backup of memory, chat history and settings, with a recovery code shown once.
- **This PC or a USB drive only** (recommended)
- Also a shared folder on your home network

**5. The memory test run.** The re-ranker (the part that re-orders saved facts) was switched on without being measured, which your rule forbids. I recommend it goes off until the test runs on your PC.
- **Switch it off now; you run the one-line test when convenient** (recommended)
- Leave it on until you run the test

**6. The plan card.** For a job with several steps, one card would list every step; your yes runs the safe ones; a risky step (sends, deletes, spends) still gets its own card. You wrote "never ... approves in bulk", so this is yours to decide.
- **Allow it later, only after the safety tests pass** (recommended)
- Never - keep one card per step

**7. The 12 GB card's job.** It holds only one big extra thing beside the long-conversation model. Even today's "better voice" cannot run at the same time as it.
- **Longer conversations and pictures, with one model** (recommended)
- A better voice
- Making pictures

**8. Crisis help line number.** If you ever write about suicide or self-harm, Jarvis would show a help number. It contacts nobody.
- **UK and Ireland: Samaritans 116 123, and 999** (recommended - guessed from the British spelling in your notes)
- Another country (tell me which)

**9. Starting a plug-in server.** You asked for "a card to start each server".
- **A card when a server is added, and again when its version changes** (recommended)
- A card every time it starts (a card per server after each restart)

**10. Music and video control on this PC** ("pause", "next", "what's playing").
- **No card, only when you say it yourself** (recommended - it is instantly undone and stays on the PC)
- A switch, off until you turn it on with a card

**11. Alarms on a smartwatch.** A recent change keeps every Jarvis notification on the phone, including alarms, so none reach a watch. It was made without asking you.
- **Keep everything on the phone** (recommended - simplest, most private)
- Let alarms (only) reach the watch

**12. News headlines and "tell me when this page changes".** Both would fetch web addresses you type, on a schedule - a new way out of the PC.
- **Not now; keep "news: not available"** (recommended)
- Yes, one card per address you add

**13. The focus streak.** The focus report card shows "Streak: N clean sessions in a row" (`backend/jarvis_focus.py:702-704`). The research says streaks make assistants naggy; you asked for "a report card", not a streak.
- **Keep the report card, drop the streak line** (recommended)
- Keep the streak

**For later, when those features come up** (not now): whether new repeating kinds such as a weekly goal check need a card (Rules); whether waking the PC from the phone is allowed while the link is down (I89); a humour setting (I137); the "say these 3 words" check (I26).

**Owner actions (not decisions):** run the memory test (step 0.7); send copies of `jarvis_undo.py`, `jarvis_ledger.py`, `jarvis_watch.py` and `jarvis_persona.py` from the PC so they can be read before anything extends them; after I02, check on the PC that installing a model still works.

---

## 6. What the research got wrong, and what nobody could check

### Wrong or out of date (each checked by me unless marked)

1. **Memory ideas 1-4 and the "notifications stay on the phone" commit are merged** - the master list said neither was (`git merge-base --is-ancestor`; merge `d1af3c7` for `e372eb7`).
2. **I01 and I02 were listed as not built; they are** (`f973178`; `jarvis_agent.py:1996-2013`; `jarvis_second_card.py:792`; `jarvis_profiles.py:844`).
3. **"16% of a 16K window" (ENG) and "1.6% of 16K" (R4-CHAR)** use the wrong size. The backend's own test says ~8,000 tokens (`backend/test_tool_text.py:3-5`); the 8B preset gets 6K (`docs/HARDWARE-PROFILES.md:702`). Tool text is ~35-45% of that (Hardware's and Devil's counts; I did not re-count).
4. **MEM said the re-ranker would be off until measured; it shipped on** (`rebuilt/jarvis_memory.py:505-506`). **The README's "It never makes a chat wait"** is not quite true: a question waits up to 1.5 s (`:504`, `:641`) before giving up on it.
5. **MEM's "at most 5 cards a night, under the existing back-off"** does not fit: the back-off allows 3 waiting (`jarvis_backoff.py:88`) and only two kinds of ask (`:154-159`).
6. **VV's screenshot plan** would put the text inside the owner's typed message, where it counts as the owner's own words (`OWN_WORDS`, `jarvis_agent.py:2385`).
7. **R3-KNOW's "`file_read` can read any path"** was fixed with a refusal list, not the allow-list it advised, and the list misses the phone-control key and others (`jarvis_agent.py:207-222`; `~/.android` absent).
8. **R2-TRU's "the watchdog is safe under the rules"** is true for cards, not for taint (`jarvis_chat_log.py:520-522`).
9. **CAP #4 ("nothing leaves their account")** - a draft is stored on Google's servers; and the shipped settings already say `draft_email = "auto"` (`rebuilt/jarvis-framework.toml:96`), which no report noticed.
10. **R4-WELL's crisis design reuses a pattern that fires on "Suicide Squad"** (`jarvis_sensitive.py:192`), and its "logs nothing" is untrue while chat history is on by default.
11. **R3-ROUT #4: a routine's lights need no card with the lights setting on** - wrong: that setting needs every device named in the owner's newest message (`jarvis_agent.py:1183-1192`).
12. **The MCP draft is not a working starting point**: its patch fails against HEAD (checked on a scratch copy), and its summary ("every tool call raises its own approval card", `DESIGN.md:23-24`) contradicts its own `below_ask_ok` option (`jarvis_mcp.py:287-292`).
13. **CAP #10/#12 planned HTTP MCP servers; ENG and the draft refuse anything but stdio** (`jarvis_mcp.py:238-241`).
14. **CAP #2 calls "Also on my phone" fully local** - an event added to a Google-synced phone calendar reaches Google (Rules; the report's own row says so).
15. **ENG's MTP "1.5-2x faster"** rests on a 27B on RTX 30/40/50 cards, with no 20-series figure (per Devil, quoting ENG; I did not re-read ENG).
16. **R2-PER and R4-WELL say a 14B goes on the 12 GB card**; the plan is `qwen3:8b` at 32K (`jarvis_second_card.py:198`).
17. **Several reports propose a new ledger, undo or GitHub watch** without mentioning the ones already on the owner's PC (ARCHITECTURE, "Present, but only on the owner's PC").
18. **The reports' "no streaks" rule versus the focus report card's streak** (`jarvis_focus.py:652`, `:702-704`) - nobody noticed.
19. **The master list missed the owner's Notion import** (CLAUDE.md, 2026-09-26) and called I82 new when it already works (`jarvis_tellme.py:308-336`).
20. **Line numbers drift** as other agents work (e.g. `_TEMPLATE_TOKENS` is now at `jarvis_agent.py:2044`, not `:2016`; the crisis words at `jarvis_sensitive.py:192`, not `:190`). Upkeep also reports ARCHITECTURE's "Fifty-three patches" is now 67 - not checked by me.

### What nobody could check

- **Anything on the owner's PC:** the real working-memory size and speed (every token and second figure above is calculated, not measured); the PC's RAM; whether the re-ranker helps; the owner-only modules `jarvis_undo`, `jarvis_ledger`, `jarvis_watch`, `jarvis_persona`, `jarvis_gate`, `jarvis_hud`; the owner's own tier settings file (only the shipped copy was read).
- **Outside services and devices:** Gmail's IDLE time limit; whether Home Assistant's exposed-devices list needs an admin token; whether Android lets a sideloaded app read notifications without "Allow restricted settings"; whether Android 16 still offers a `home_screen` widget on the lock screen; whether Windows exposes its Focus state through a documented interface; whether a Windows wake timer works without an admin prompt; whether the Obsidian CLI needs Obsidian running; whether the owner has Frigate, a scanner, Logseq's database version or a smartwatch.
- **Other people's numbers:** MTP's speed-up, the new wake word's "100x fewer false wakes", Pocket TTS's 0.2 s, the IQ4_XS saving (0.4 or 0.6 GiB - huggingface.co is blocked here), the speech-hint bug rate.
- **Licences and security advisories:** TEN VAD, CED and Prompt Guard licences; the fixed versions for the `mcp-server-git` and pdfminer.six flaws come from public advisories the Security reviewer cited - I did not re-read them.
- **Ollama details:** whether it accepts a forced answer format and a tool list in one request (I04); whether it reuses the prompt when the tool list changes (I06).

---

## Appendices - the reviewers' own reports

All in `docs/feasibility-2026-09-26/`:

- `00-ideas.md` - the master list of 155 ideas
- `fit.md` - Fit reviewer
- `hardware.md` - Hardware and speed reviewer
- `rules.md` - Rules reviewer
- `security.md` - Security reviewer (threat model per idea; gaps G1-G5)
- `overwhelm.md` - Overwhelm reviewer (the settings / cards / pages count)
- `upkeep.md` - Upkeep reviewer
- `devil.md` - Devil's advocate
