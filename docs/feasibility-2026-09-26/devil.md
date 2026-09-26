# Feasibility audit - the Devil's advocate (2026-09-26)

**My job:** argue against every idea. I look for hype, for "nice but not
worth it", for speed claims that will not hold on an 8B model on this PC,
for features the owner would use once, and for anything that makes Jarvis
worse at its core job: **fast, private, trustworthy answers.** Where an idea
survives my best attack, I say so.

Read-only. Every claim about Jarvis's code was checked in the file and is
cited as `path:line` (paths from `/home/user/Epic-Jarvis`). "Not checked"
means exactly that. HEAD when I read it: `f973178`.

Where the owner has already chosen an idea (CLAUDE.md lines 340-381:
the four cutting-edge groups, phone notifications, memory now, the Notion
import), I do not argue about **whether**. I argue about **how**, and about
the guardrails. The verdict for those is "build", with the "how" in the
reason.

## The one number that sits behind most of my objections

Jarvis's model has a small working memory (its "context": everything it can
read at once, counted in tokens, about ¾ of a word each).

- On the owner's 8 GB card the backend's own test says the real room is
  **"about 8,000 tokens"** (`backend/test_tool_text.py:3-5`). The hardware
  table gives the 8B model only **6K** in the "Smartest answers" preset
  (`docs/HARDWARE-PROFILES.md:702`).
- I counted the 23 tool descriptions the model is offered today with
  Jarvis's own counter (`estimate_tokens`, `backend/jarvis_agent.py:2021`,
  3 characters a token; `offered_tools(None)` gives all 23): **3,612 tokens.**
  ENG counts the same text as ~2,700 with 4 characters a token. Either way it
  is **roughly 35-45% of the real room**, not the "16% of 16K" ENG gives.
- Also fixed on every turn: 1,024 kept for the answer
  (`DEFAULT_MAX_TOKENS`, `jarvis_agent.py:1707`) and a flat 300 for the rules
  (`_TEMPLATE_TOKENS`, `jarvis_agent.py:2044`).
- Re-reading 6,000 tokens costs about **3.1 s** on this card
  (`docs/MODEL-TOPOLOGY.md:257`; arithmetic, not measured on the owner's PC,
  `:472-475`).

So every idea that adds words to every turn - more tools, a character
block, example chats, style dials, word-marking outside text - is paid for
out of the conversation the owner can have, or in seconds of waiting. The
reports mostly price these as "a few % of 16K". On this card, today, that is
the wrong denominator.

---

## 1. The verdict table

Verdicts: **build** / **build later** / **don't build** / **no objection**
(= already built, guidance, or so small I have nothing against it).
Last column: for security-relevant ideas, the guardrails; for hardware
ideas, the cost numbers; otherwise "-".

### Engine (I01-I13)

| Id | Verdict | Reason | Guardrails / cost |
|---|---|---|---|
| I01 | no objection | Already built: HEAD `f973178` reads `/api/show` "capabilities" (`backend/jarvis_agent.py:1999-2008`). | - |
| I02 | no objection | Already built: `jarvis_second_card.py:792`, `jarvis_profiles.py:844`. The commit itself says "not verified here" that `ollama pull` still works - check that on the owner's PC. | Fails closed (refuses cloud); risk is only that installs break. |
| I03 | build | Cheap, and it is the only way to know whether I06, I129 or I107 cost seconds. Without it, speed arguments are guesses. | Numbers only, never text. |
| I04 | build later | Solves a failure nobody has counted. Build only if I05 shows broken tool arguments are a real share of failures. | Still one retry, still through the gate. |
| I05 | build | Owner chose it. It is the ruler for I06, I07, I09 and I61 - build it first. | PC only. |
| I06 | build | Owner chose it; the budget above is the best argument for it. **How:** the 2026-09-24 router that guessed tools was right only 50-61% (ENG §6) - an 8B must *prove*, with I05, that it asks for "more tools" when it needs them. The tool list sits at the start of the prompt (ENG itself says fixed order helps the cache, ENG:243-244), so changing it re-reads everything. | Fixed core, fixed order; once a group is opened keep it for the rest of that chat (one re-read, not one per turn); measure with I03. Cost: frees ~2,000-2,500 tokens; each list change ≈ 3 s at 6,000 tokens. |
| I07 | build | Owner chose it, last in its group. **But** it is an L-size subsystem, and the two suggested first servers do not earn it: "Everything" file search is I39, which `es.exe` does directly with no bridge; git read tools are not something a beginner asks a voice assistant often. Pick a first server the owner will really use, or the bridge ships empty. | After I06 and I05; stdio only (no HTTP - settles note 5 of the master list the strict way); pinned install, no `uvx`/`npx` fetch at start; card when a server is added or its version changes; read-only first; results are outside text; each tool ≤300 tokens (`test_tool_text.py` `PER_TOOL`); started on demand, stopped when idle. |
| I08 | build later | Hype check: ENG's headline "~1.5-2x faster" (ENG:23) rests on a 27B on RTX 3090/4090/5090 with "no RTX 20-series figure found" (ENG:181-183), needs a switch to Qwen 3.5 (today's `qwen3:8b` has no MTP head, ENG:180), and an open Ollama bug makes it ~10x slower. | Cost: extra memory (1-2 GB on a 27B; unknown for 9B). 12 GB card first; `draft_num_predict 0` as the off switch. |
| I09 | build | A test, not a switch; information is cheap. Keep it to 2-3 models: every one is a multi-GB download (size not checked). | Downloads only from Ollama's registry; I05 decides. |
| I10 | build later | Survives: one model for two jobs removes a 6-10 s swap (`MODEL-TOPOLOGY.md:254-258`). Waits for the card. | 12 GB card, measured first. |
| I11 | don't build | A small local vision model that points at buttons will sometimes point at the wrong one, and a wrong click is an action. I27 (show, the owner clicks) gives the same help with no risk. Revisit only if I27 proves the pointing is accurate. | - |
| I12 | build | Survives: small, and a real blind spot - the desktop reads only the first card (`jarvis-desktop/src-tauri/src/commands.rs:2617`, `text.lines().next()`). Needed before the second card arrives. | None new (same `nvidia-smi` read). |
| I13 | build later | Used once, and the limit resets at every restart (R3-HOME:98-99), so it needs an administrator scheduled task at every boot - a standing elevated job for a few watts. | Never elevate Jarvis; the owner pastes the one line. |

### Voice & vision (I14-I30)

| Id | Verdict | Reason | Guardrails / cost |
|---|---|---|---|
| I14 | build | Owner chose it. Try Windows' own OCR first (no download), RapidOCR only if it is worse. | Outside text (taints the turn); never learned. |
| I15 | build | Owner chose it. **How:** a bake-off, not a replacement. The "100x" is the makers' own test on "hey livekit" (VV:106-108), and the new model is trained on synthetic Piper voices - it could hear the real owner *worse*. Keep today's `hey_jarvis` unless the owner's own clips and an hour of household noise say otherwise. | Cost: one-time training on the card, chat off meanwhile; phone battery unmeasured. |
| I16 | build | Owner chose it. **How:** the ~0.2 s first sound is from an Apple laptop, not the 3900X (VV:149), and VV says the copy "sounds different". Keep only if it beats ZipVoice on the 3900X *and* passes the owner's ear. | Same custom-voice card and consent; 0 VRAM, shares processor with speech-to-text. |
| I17 | build later | Kokoro already runs on the processor; moving it to a card saves maybe a second and takes memory from the long-conversation lane. | Second card only. |
| I18 | don't build | The known bug gives empty or invented text ~20% of the time in the mode it needs (VV §5). An invented contact or device name is worse than a misheard one. Revisit when fixed upstream. | - |
| I19 | don't build | The PC microphone listening all day, for an alert that VV itself says is "not a safety device". Rarely useful, always a listener. | (If ever: its own card, no audio kept.) |
| I20 | build later | Only if Qwen 3.5 9B turns out weak at documents - the report's own condition. | Outside text. |
| I21 | build later | Only if word errors drop on the owner's audio; noise is already rejected. | After the voice check. |
| I22 | build later | Smaller gain than it sounds: the PC already runs Silero and refuses a noise-only clip before anything else runs (`backend/jarvis_speech.py:44`, `:1544`). The gain is fewer wasted clips and some phone battery, for a CI round trip. | Not speech-to-text, so the phone rule holds. |
| I23 | build later | Only if the owner's own "someone else" numbers show a problem (VV's own condition). | New limits measured. |
| I24 | build later | Replaces F5 and fights the long lane for the 12 GB card. | Second card. |
| I25 | don't build | No reliable local detector exists and none catches a replay (VV §12). | - |
| I26 | build later | The honest fix for "a recording is not me", but it adds a step; the "Only trust the talk button" setting already covers today's risk. Only if hands-free is ever trusted with more. | - |
| I27 | build later | Survives as the safe version of I11: shows, never clicks. Needs a model that can see (second card). | No card needed; acts on nothing. |
| I28 | build | Survives: the setting already exists in the backend (`tts_speed`, 0.5-2.0, `backend/jarvis_voices.py:251-252`) but no app shows it (grep: no `tts_speed` in `jarvis-desktop/` or `jarvis-client/`). Tiny. | - |
| I29 | don't build | "Draw a birthday card" is a few-times-a-year feature. Every picture unloads the long lane (6-10 s reload) and takes about a minute (Hardware, unmeasured); new model supply chain; a face-swap guard to maintain. | Cost: most of the 12 GB card for a minute. |
| I30 | don't build | Fun once; not the core job. | - |

### Memory (I31-I38)

| Id | Verdict | Reason | Guardrails / cost |
|---|---|---|---|
| I31 | build | Already merged - but **on by default and unmeasured.** `_RERANK_ON` defaults to on (`backend/rebuilt/jarvis_memory.py:505-506`); the README says "The re-ranker is NOT measured" and the stand-in lost two-fact questions at 1,071 and 10,071 facts (`backend/README.md:10330-10337`). The owner's rule is that a memory change must beat the self-test *before* it is kept (CLAUDE.md:369-373), and MEM said "off until the self-test on your PC shows it helps" (MEM:52). | Default off until `eval_memory.py` on the PC shows a gain. Cost: up to 1.5 s wait per question (`RERANK_BUDGET_S`, `:504`, and `t.join`, `:641`); cap ~0.3 s on spoken turns. |
| I32 | no objection | Merged; a test. | - |
| I33 | no objection | Merged; invisible. | - |
| I34 | no objection | Merged; invisible. | - |
| I35 | build later | The model writing search words into the index is a small step toward "the model writes memory". Only if the self-test shows reworded misses that the re-ranker does not fix. | Erase wipes the hints; never shown. |
| I36 | no objection | Small and invisible, if it beats the self-test (the owner's rule). | - |
| I37 | build | Owner chose it. **How:** "at most 5 cards a night" is up to 35 a week (MEM:103, as Overwhelm found). A tidy the owner learns to ignore trains them to approve without reading. | Cap at the back-off's 3 waiting; one "Tidy suggestions" list, not pop-ups; if ignored two weeks running, slow down; never changes memory itself. |
| I38 | build later | Owner decided it waits (CLAUDE.md:329-330). | - |

### Knowledge & documents (I39-I60)

| Id | Verdict | Reason | Guardrails / cost |
|---|---|---|---|
| I39 | build | Survives: "where's that file?" is asked often and answered in under a second. Do it with `es.exe` directly, not as an MCP server. | Allowed folders only; never Everything's network server; names are outside text; local model only; the `file_read` refusal list stays (`backend/jarvis_agent.py:201-224`). |
| I40 | build | Owner chose it. **How:** MarkItDown reads the text layer; a scanned letter or bill has none, so the owner gets "nothing found" unless it falls through to I14's OCR. Say so plainly. The Notion import (CLAUDE.md:376-381) uses the same folder list. | Install only the document extras, pinned; never the audio (sends to Google) or YouTube parts; read in slices; outside text; never learned. |
| I41 | build later | A second search system beside memory. Build only when I40's slice-search proves not enough. | `.ssh`, `.env`, password files, browser profiles always out. |
| I42 | build | Survives: "where this came from" goes straight at the core job (trustworthy answers), taken from what tools returned, not from the model. **But** an 8B paraphrases; a word-for-word quote check will flag many honest answers. Show "not a direct quote", not "false". | Source list from tool results only. |
| I43 | don't build | Obsidian and the phone's Share already save links; "what's on my reading list?" is a once-a-month question. | - |
| I44 | build later | Four small parts, none urgent. | Fixes through the existing wiki card. |
| I45 | build later | How often will the owner ask a spreadsheet question by voice? A sandboxed DuckDB is one more engine to keep safe. | Separate process, no files/network/extensions, time limit, row cap. |
| I46 | build later | Rare; a 1-hour file is ~5-6 min of processor time and ~13,000 tokens, more than the window (Hardware). | Outside text, never learned, never a live meeting. |
| I47 | don't build | The browser's own bookmark search already does this. Novelty. | - |
| I48 | don't build | Very private, rarely useful, and the browser's own history search exists. | - |
| I49 | build later | A new way out of the PC for headlines; the owner's question is still open. | Egress row; one card per feed. |
| I50 | build later | The "Open in Obsidian" button is useful; drawing wiki pages in the galaxy is decoration. | Desktop only. |
| I51 | build later | Fixes a real date-format gap, but ties Jarvis to a new Obsidian command line. | Fixed read-only command list; never `eval`. |
| I52 | no objection | Detect-and-say is small. Only matters if the owner uses Logseq's new database graphs (not checked). | - |
| I53 | build | Owner chose it. **How:** keep a card every time. `draft_email` is already a hard limit - "leaves the PC" (`backend/jarvis_asks_first.py:175-179`) - and an IMAP draft is uploaded to Google's servers, possibly with memory or file text in it. CAP's recommended "ask only after outside text" would loosen a hard limit. | One card per draft showing the full text. |
| I54 | build later | Small gain over typing the address. | Desktop only; never learned. |
| I55 | don't build | The owner's calendar is Google through a read-only link; no second calendar is known. | - |
| I56 | don't build | Needs a scanner (not checked that the owner has one); a phone photo plus I14 covers it. | - |
| I57 | don't build | A quiz feature the owner would try once; another scheduler kind to maintain. | - |
| I58 | don't build | Nothing to build: the model already translates when asked. A dedicated model is another download for a rare need. | - |
| I59 | don't build | Spoken practice is impossible (Parakeet v2 is English only, `docs/ARCHITECTURE.md:1513`; the phone may not do speech-to-text). Typed practice is just a chat. | - |
| I60 | don't build | The model already explains errors when asked. As a "feature" it adds nothing; as an editor it would be a new risky tool. | - |

### Routines & agents (I61-I74)

| Id | Verdict | Reason | Guardrails / cost |
|---|---|---|---|
| I61 | build later | One yes for several steps is close to "approves in bulk" (CLAUDE.md:104-105); the owner carved out exactly one such exception, for listed smart-home devices. It needs his own decision, and an 8B's multi-step planning is unproven until I05's multi-step cases pass. | Risky steps asked again; ≤8 steps; never by voice. |
| I62 | don't build | A small second automation engine; Home Assistant's own scenes and scripts already do "movie night". | - |
| I63 | don't build | A plain repeating reminder ("every Sunday ask me about the garage") already does this and needs no card (CLAUDE.md:288-291). | - |
| I64 | don't build | Builds on I63; a model drafting life plans is where an 8B is weakest. | - |
| I65 | build later | The owner's PC already has an undo shelf (`jarvis_undo`, `/api/undo`, `docs/ARCHITECTURE.md:1491-1497`), whose code is not in this repo. Read it before designing a second one. | - |
| I66 | build later | The calendar source is useful; the folder watcher is a new always-running listener for a rare question. | Same card, end date, notify only. |
| I67 | build later | A new way out of the PC; decide with I49. | Egress row; the one typed address only. |
| I68 | build | Owner chose it. **How:** a five-minute wait is already fine for most "tell me when"; the risk is a connection that silently dies. Mail servers end idle connections (how often for Gmail: not checked); on any drop, fall back to today's 5-minute check, never a second sign-in path. | One connection; From line only; `BODY.PEEK`. |
| I69 | build | Survives: small, reuses the same match, and "chase-up" is a real, repeated need. | Notify only. |
| I70 | build later | The owner's PC already has a GitHub watchlist (`jarvis_watch`, `/api/watch`, `docs/ARCHITECTURE.md:1491-1497`; `jarvis-client/.../net/Watch.kt:1-20`). Extend it, do not add a second. | Read-only token, sent only to GitHub (rule 3). |
| I71 | build later | The big model has no standby flag (R3-ROUT), and the owner may turn the PC off at night. | Only reads and prepares; acts need a morning card. |
| I72 | build later | An 8B working from search snippets, with every claim quote-checked, will mostly say "not found". | One card with exact search words; never loops. |
| I73 | build | Owner chose it (queued). **How:** "Allow restricted settings" for a sideloaded app is not verified (not checked here either). | Off by default; card to turn on; chosen apps only; codes masked on the phone before sending; outside text; never SMS; never replies. |
| I74 | don't build | An 8B summarising a week of chats into "what you decided and changed your mind about" will invent, and history is not memory (ARCHITECTURE §5). | - |

### Home and the PC itself (I75-I94)

| Id | Verdict | Reason | Guardrails / cost |
|---|---|---|---|
| I75 | build | Owner chose it; survives: fills a real gap (`backend/jarvis_briefing.py:117`, "Weather and news: not available"). | One read-only HA service; non-admin token (I81). |
| I76 | no objection | Small and read-only. | Outside text. |
| I77 | don't build | HA's list has no entity ids, so it cannot drive actions (R3-HOME's correction); Jarvis's own list already works. | - |
| I78 | build later | "Downstairs lights" is nice, but it adds a WebSocket client dependency. | One card listing every light; locks/doors/covers alone. |
| I79 | don't build | Per-device rooms, "someone else was heard lately", "is the owner at the PC" - a lot of machinery that only makes Jarvis quieter, and a listener that notices other people. | - |
| I80 | build later | Needs I78. | - |
| I81 | build | Survives: small, and it limits the damage of a leaked HA token. | Preflight warning if the token is an admin's. |
| I82 | build later | Only if the owner has Frigate or an HA person sensor (not checked). | Labels only, no pictures. |
| I83 | build later | Useful sometimes; a camera image is sensitive. | Own card; never written to disk; never faces. |
| I84 | don't build | "What did Jarvis cost today?" is asked once, out of curiosity. | - |
| I85 | don't build | "While you were out" duplicates "What did I miss?" (`backend/jarvis_quick.py:68`, `:890`). | - |
| I86 | build later | Only for devices the owner actually has. | Read-only. |
| I87 | build later | Writes to HA; small gain. | Card or setting-by-card. |
| I88 | don't build | A model proposing automations from history - card after card of guesses. | - |
| I89 | build later | Useful if the PC sleeps; needs an always-on device at home. | Never a router port-forward. |
| I90 | don't build | Whether it works without an administrator prompt is unverified, and an alarm that fails to wake the PC is worse than a PC left on. | - |
| I91 | build | Survives: pause/next/what's playing are asked many times a day. | Setting off until turned on; no network. |
| I92 | build later | Listing is a new way out of the PC; updating is card plus Windows Hello per package. | Never "update all". |
| I93 | build | Owner chose it; survives. | The owner's tap is the approval; warn about two alarms. |
| I94 | no objection | Small; the owner picks the person and presses send. | Never reads SMS. |

### Trust & safety (I95-I115)

| Id | Verdict | Reason | Guardrails / cost |
|---|---|---|---|
| I95 | build | Survives: the only way to know whether I104-I108 do anything on *this* model. Build it before any of them. | PC only, overnight. |
| I96 | build | Survives: memory and chat history are the one thing that cannot be re-made. (Even the backend's code has "no second copy", `docs/ARCHITECTURE.md:1167-1170`.) | This PC or USB only; recovery code shown once; restore = card + Windows Hello; say plainly Erase cannot reach old backups. |
| I97 | build | Small, read-only. | Warn, never fix. |
| I98 | build | Small; stops after 3 in 10 minutes and says so. | Never hides a crash loop. |
| I99 | build | Small. | Newest 10; scrubbed before sharing. |
| I100 | don't build | Even a mini dump can hold the pairing token. | - |
| I101 | build later | Only after I96 exists; a cleared security chip would lose history for good. | - |
| I102 | build | Owner chose it. Large, but the design is already written. | As designed (R2-TRU #6). |
| I103 | build | Owner chose it, with I102. | Fresh fingerprint per risky approval. |
| I104 | build later | After I95. Stricter-only is right, but another warning line on cards feeds card fatigue. | One warning slot per card (Overwhelm). |
| I105 | build later | Only if I95 shows fewer attacker cards (the report's own condition). | - |
| I106 | don't build | Re-runs the model before every card after outside text: roughly +3-8 s (Hardware estimate) on the turns that already read an email. | - |
| I107 | don't build | Marking every word of outside text makes a small model read worse - the same reason Base64 was ruled out (master list line 1085) - and costs tokens from the tight budget. Revisit only if I95 shows a clear gain. | - |
| I108 | don't build | A second model that only warns, with unchecked licences; the taint latch already marks outside text. | - |
| I109 | build later | The owner's PC already has `jarvis_ledger` (`/api/ledger`, `docs/ARCHITECTURE.md:1491-1497`). Read it first. "7 approved in under 2 seconds" is a nag unless worded with care. | Counts only; never changes a tier. |
| I110 | build | Survives: the real risk with one-card-per-action is rubber-stamping; 2 seconds on *risky* cards only is a small price. | Stricter only; both apps. |
| I111 | build later | Update machinery for a backend whose code has no second copy (`docs/ARCHITECTURE.md:1167-1170`). First get the code backed up; then build a safe updater. | Hash-pinned packages. |
| I112 | build later | Covers Tailscale only, not NordVPN Meshnet; Tailnet Lock is an owner-side setting - a doc line, not code. | - |
| I113 | build | Lock-screen half: small. The notification half is built but unmerged (`e372eb7` is not in HEAD - checked) and answered an owner question without asking. | Widget off the lock screen. |
| I114 | no objection | Small in value, but not a one-line change: the desktop copies with the browser's `navigator.clipboard.writeText` (e.g. `jarvis-desktop/src/hardware-panel.js:385`), which cannot set Windows' "keep out of history" flags - a Rust command is needed. | - |
| I115 | build | Survives: keeps a pasted password out of stored history. | The model still sees it for this turn only, local only. |

### Experience (I116-I128)

| Id | Verdict | Reason | Guardrails / cost |
|---|---|---|---|
| I116 | build | Survives: makes the no-model commands - the fastest, most reliable part of Jarvis - findable. | Fills the box, never sends. |
| I117 | don't build | A fourth summary surface beside the briefing, Coming up (`jarvis-desktop/src/coming-up.js:31`) and "What did I miss?" (`jarvis_quick.py:890`). Improve those instead. | - |
| I118 | build later | Pleasant, not core. | Owner's own words only. |
| I119 | don't build (as "first run") | The owner has already set Jarvis up, and three onboarding screens exist (`jarvis-desktop/src/onboarding.html`). The useful part is showing the preflight (today a command only) in Settings with "Fix" buttons - do that, later, under that name. | - |
| I120 | build later | Nice; the paste/share path already exists. | Tagged "shared" (outside text); waits for Enter. |
| I121 | build later | After I40. | Private link only; outside text. |
| I122 | build later | Reading Windows Focus state needs an interface nobody has checked. | - |
| I123 | build later | After focus sessions prove used. | Alarms and urgent alerts still ring. |
| I124 | build later | Nice; two builds (phone and PC). | - |
| I125 | no objection | Small, but costs a CI round trip. | Meets App lock. |
| I126 | build later | Nice. | Counts only; off the lock screen. |
| I127 | build later | One owner, no known need; screen-reader and 200% tests cost CI time. | - |
| I128 | don't build | Large and fiddly for a beginner. | - |

### Personality & character (I129-I150)

| Id | Verdict | Reason | Guardrails / cost |
|---|---|---|---|
| I129 | build | The valuable part is the **bug fix**, not the character: the rules are added after trimming (`keep_rules_first`, `jarvis_agent.py:3350`, `:3579`) against a flat 300 (`:2044`). A paragraph will not make an 8B "honest before agreeable"; keep the block short and keep it only if I133 shows a gain. | Cost: ~270 tokens, **~3-4% of the real 8K**, not "1.6% of 16K" (R4-CHAR:192). |
| I130 | build later | Only if I133 shows a gain (the report's own condition). | ~90 tokens every turn. |
| I131 | build | Survives: answered without the model, so instant and honest. | Fixed text; no romance. |
| I132 | build | Survives: catches the most trust-damaging false claim ("you told me") for very little. | - |
| I133 | build | One tool, not the three the reports propose. Fixed, crisp checks only; no 8B judging an 8B. | PC only. |
| I134 | build | Small; catches a stale model file. | Warn only. |
| I135 | build | Small test. | - |
| I136 | build later | Possibly useful for a beginner, but only as one preset beside Warm and Plain - not a switch *and* a preset (R4-GROW duplicates itself). | Wording only. |
| I137 | don't build | An 8B's jokes are hit and miss, and the same joke the twentieth time grates. Humour is the fastest way to make an assistant feel worse. | - |
| I138 | don't build | Dials the owner sets once, each adding a sentence to every turn (up to 900 characters ≈ 300 tokens by Jarvis's own count). Warm and Plain already exist. | - |
| I139 | don't build | Only needed if I138 exists. | - |
| I140 | build later | "Call me Sam" is the one piece worth having, and it is close to an ordinary saved fact. | Owner's live words only. |
| I141 | don't build | Counting "shorter please" and offering later is machinery for a preference the owner can simply set. | - |
| I142 | don't build | "We call the printer the beast" is already an ordinary memory; a label adds nothing. | - |
| I143 | don't build | The one place owner text becomes an instruction to the model - a new rule and a new risk for small gain. | - |
| I144 | no objection | Small. | - |
| I145 | build | Look first: eight older modes nobody sees may already conflict with manner. Cleanup, not a feature. | - |
| I146 | don't build | Temporary chats already exist (`docs/ARCHITECTURE.md:686-687`); the owner can play 20 questions in one today. | - |
| I147 | build later | Nice, not core. | Inside the flash limits. |
| I148 | build later | Nice, not core. | Reduced motion respected. |
| I149 | don't build | Only if a face with a mouth is ever designed. | - |
| I150 | no objection | Guidance only. | - |

### Wellbeing (I151-I155)

| Id | Verdict | Reason | Guardrails / cost |
|---|---|---|---|
| I151 | build | Survives: rare, but when it matters it matters most, and today nothing handles it. **How:** the existing pattern `suicid\w*` (`backend/jarvis_sensitive.py:190`) matches "Suicide Squad", which R4-WELL says must *not* fire (R4-WELL:151-153) - write a separate phrase list with a false-alarm test. | A floor, not a guarantee; contacts no one; logs nothing; number chosen by the owner. |
| I152 | build | Small; keeps distress words off the cloud offer. | - |
| I153 | build later | Fold into I129's block; not separate text. | - |
| I154 | build | Small; a passing mood must never become a saved fact. | - |
| I155 | don't build | These kits default to a cloud judge; a local 14B judge needs the second card and is itself unreliable. | - |

**Counts:** build 44, build later 57, don't build 41 (I119 counted here,
"as first run"), no objection 13 (155 in all).

---

## 2. Objections for the other reviewers

Stated so each can be answered.

**Everyone**
- **Price context in the real room, not 16K.** Hardware already did
  (I06, I129). Fit, Rules and the reports still quote "% of 16K". On the 8 GB
  card the backend's own test says ~8,000 tokens (`test_tool_text.py:3-5`),
  and the 8B preset gets 6K (`HARDWARE-PROFILES.md:702`). I claim: any idea
  that adds fixed text to every turn must name its token cost against 8K.
- **"Build" is too generous.** Fit has ~60 builds, Overwhelm 54, Security
  about 50. Many are "nice". My test: *will the owner use it more than a
  handful of times, and does it make answers faster, more private or more
  trustworthy?* Where a reviewer says "build" and I say "don't", the burden
  is to name the repeated use.

**Fit**
- I07: you accept "Everything" as a first MCP server; I say do I39 with
  `es.exe` directly and keep the bridge for a server that has no simpler
  route.
- I63 (goals): you say build; I say a repeating reminder already does it,
  with no card (CLAUDE.md:288-291). Name what goals add beyond that.
- I58, I36, I52, I127: you say build; I say there is nothing to build (I58),
  or no known need (I52, I127).
- I119: I call it "don't build as first run" - do you agree the useful part
  is a Settings preflight page?

**Hardware and speed**
- I46, I22, I119: you say build; I say rare use (I46), small gain because
  the PC already rejects noise with Silero (I22), wrong framing (I119).
- I104: you say build (0 model cost). It costs no seconds, but it costs
  the owner's attention on every card - I want I95 first.
- I31: we agree on the 1.5 s wait. I go further: off by default until the
  PC self-test says it helps, because that is the owner's written rule.

**Rules**
- I96 (backup): you say build later; I say build now - it protects the one
  thing that cannot be re-made. What rule does it strain?
- I61 (plan card): you say build later; I say it needs the owner's own
  decision against "approves in bulk", the same way he made the smart-home
  exception. Do you read the plan card as bulk approval or not?
- I53: the open question's recommended option would loosen a hard limit
  (`jarvis_asks_first.py:175-179`). Do you agree it should stay a card
  every time?

**Security**
- I109, I112, I114: you say build; I say later (ledger already exists on
  the PC; Tailnet Lock is a doc line; clipboard needs Rust).
- I66: you say build. A folder watcher is a new always-running listener -
  is that surface worth "tell me when a scan lands"?
- I107, I108: you say build later; I say don't build unless I95 shows a
  clear gain, because datamarking has the same weakness that ruled out
  Base64, and a warning-only second model duplicates the taint latch.
- I19: you say build later; I say an always-on PC microphone for a
  "not a safety device" alert should not be built at all.

**Overwhelm**
- I117: you want the Today page as the hub that replaces five other
  ideas. I say it is a fourth summary beside the briefing, Coming up and
  "What did I miss?" - cut the five ideas instead and there is nothing to
  consolidate.
- I85, I62: we agree (don't build).

**Upkeep** (not yet written when I read the folder)
- Every phone-side idea costs a ~15-minute CI round trip per attempt
  (CLAUDE.md, "How the Android apps get built"). My "don't build" list
  removes a number of phone changes (not counted by me). Please count
  phone-touching ideas per verdict.

**Against myself** (where I could be wrong)
- I137 humour, I147-I148 face life: the owner may simply enjoy them;
  "fun" is a fair reason if it costs no trust. Ask him.
- I19 household sounds: if someone in the house is hard of hearing, the
  value changes. Not known.
- I117: if the owner does not use the briefing or Coming up today, a
  single Today page might replace them rather than add to them.

---

## 3. Wrong or out of date in the research reports

1. **00-ideas.md, note 1, is out of date.** Memory ideas 1-4 are merged:
   `git merge-base --is-ancestor` succeeds for `9abdd68`, `c33b5f0`,
   `d2d8831`, `eee9b03`, `a1b133e` (merge commit `1381e6a`). `e372eb7` (the
   notifications half of I113) is **not** in HEAD - note 2 still holds.
2. **00-ideas.md, I01 and I02 "not found" is out of date.** HEAD `f973178`
   built both: `backend/jarvis_agent.py:1999-2008` (capabilities),
   `backend/jarvis_second_card.py:792` and `backend/jarvis_profiles.py:844`
   (`OLLAMA_NO_CLOUD=1`).
3. **Line numbers have moved.** `_TEMPLATE_TOKENS` is now at
   `jarvis_agent.py:2044` (00-ideas says `:2016`, Hardware says `:2016`,
   R4-CHAR says `:1964`); its uses are at `:3033` and `:3549`.
4. **MEM line 9 says all four memory ideas are "built and measured by the
   self-test".** The README says the opposite for the re-ranker: "The
   re-ranker is NOT measured" (`backend/README.md:10330`). MEM:52 says it
   "should be off until the self-test on your PC shows it helps"; the
   merged code has it **on** by default (`backend/rebuilt/jarvis_memory.py:505-506`).
   The README admits this (`:10352-10354`), but it conflicts with the
   owner's rule (CLAUDE.md:369-373).
5. **ENG's headline overstates MTP.** "~1.5-2x faster" (ENG:23, :43) rests
   on a 27B on RTX 3090/4090/5090, "no RTX 20-series figure found"
   (ENG:181-183), and the model Jarvis runs has no MTP head (ENG:180).
6. **ENG §6 prices lean mode as "about a second" per extra round** (ENG:164)
   and the tool text as "~16% of the 16K window" (ENG:148-151). A changed
   tool list re-reads the whole prompt (≈3.1 s per 6,000 tokens,
   `MODEL-TOPOLOGY.md:257`), which ENG half-says itself at :243-244; and
   the real room is ~8,000 (`test_tool_text.py:3-5`), so the share is
   ~35-45%.
7. **R4-CHAR's "1.6% of 16K"** (R4-CHAR:192) has the same wrong
   denominator (Hardware found this too).
8. **R4-WELL's crisis design reuses a list that breaks its own test.** It
   says to use the words `jarvis_sensitive.py` already has (R4-WELL:151)
   and that the check must not fire on "Suicide Squad" (:152-153); the
   existing pattern `suicid\w*` (`jarvis_sensitive.py:190`) matches it.
9. **CAP #4 / the I53 question.** "Nothing leaves their account" is true
   of the account but not of the PC: an IMAP draft is stored on Google's
   servers. `draft_email` is already a hard limit whose stated reason is
   that it "leaves the PC" (`backend/jarvis_asks_first.py:175-179`), so the
   recommended "ask only after outside text" would loosen a hard limit.
10. **00-ideas.md misses the Notion import** (CLAUDE.md:376-381), as
    Overwhelm found. It belongs with I40 and must share its folder list.
11. **R2-EXP #5 calls I119 "first-run setup"** for an owner who is past
    first run; the preflight-with-Fix idea is sound, the name and
    placement are not.

## Five strongest points

1. **The hidden cost is the model's working memory.** The 23 tools already
   take 3,612 tokens by Jarvis's own count, of ~8,000 real on the 8 GB card
   (`test_tool_text.py:3-5`; the 8B preset has 6K, `HARDWARE-PROFILES.md:702`).
   Every "just a few tokens" idea (character block, examples, style dials,
   datamarking, MCP tools) comes out of the owner's conversation; the
   reports price them against 16K.
2. **Lean mode and the prompt cache pull against each other.** Changing the
   tool list re-reads everything (~3 s per 6,000 tokens). Keep a fixed core
   in fixed order; once a group is opened, keep it for that chat; measure
   with I03 and I05 before and after.
3. **The re-ranker shipped on by default and unmeasured**
   (`jarvis_memory.py:504-506`, `README.md:10330`), against the owner's
   2026-09-26 rule and MEM's own advice, and it can add up to 1.5 s to a
   question. Turn it off by default until the PC self-test shows a gain.
4. **The speed claims are other people's numbers:** MTP's 1.5-2x from a 27B
   on 30/40/50-series cards; the wake word's 100x from the makers' own
   phrase; Pocket TTS's 0.2 s from an Apple laptop. Each owner-chosen voice
   upgrade must be a bake-off that can end in "keep what we have".
5. **Many ideas duplicate what Jarvis already has:** goals = repeating
   reminders (CLAUDE.md:288-291); "welcome home" = "What did I miss?"
   (`jarvis_quick.py:890`); the Today page = a fourth summary; undo, the
   ledger and the GitHub watch already exist on the owner's PC
   (`ARCHITECTURE.md:1491-1497`); first-run setup for an owner who is set
   up; translate, code help and games are just chat. Cutting these costs
   nothing and keeps Jarvis simple.
