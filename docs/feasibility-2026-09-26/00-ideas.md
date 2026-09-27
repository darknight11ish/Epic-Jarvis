# Feasibility audit, step 0: the master list of ideas (2026-09-26)

Built from every 2026-09-26 research report, plus the older reports they
point back to. Read-only: nothing in the repo was changed. Duplicates are
merged (one entry, every source listed). Ideas a report itself called "not
for Jarvis" are left out of the numbered list and listed at the end, one
line each, so the reviewers can confirm they stay out.

## How to read an entry

- **Size** is the report's own (S = about a day / one module; M = a few
  days / several files, maybe both apps; L = a week or more / a new
  subsystem). Where two reports disagree, both are given.
- **Status** is one of: *owner chose to build (CLAUDE.md line N)*;
  *already in progress* (code for it exists in a worktree or commit, cited);
  *new* (not decided; "queued earlier" means an older audit listed it, but
  the owner has not chosen it in CLAUDE.md and no code exists).
- **Q** = a question the report raised for the owner.
- Code claims made HERE were checked against the file named. Claims inside
  the reports were not all re-checked; where I did not check, it says so.

## Source key (all under /home/user/Epic-Jarvis/docs/)

| Short name | File |
|---|---|
| ENG | CUTTING-EDGE-2026-09-26-engine.md |
| CAP | CUTTING-EDGE-2026-09-26-capabilities.md |
| VV | CUTTING-EDGE-2026-09-26-voice-vision.md |
| R2-EXP | CUTTING-EDGE-2026-09-26-round2-experience.md |
| R2-PER | CUTTING-EDGE-2026-09-26-round2-personality.md |
| R2-TRU | CUTTING-EDGE-2026-09-26-round2-trust.md |
| R3-HOME | CUTTING-EDGE-2026-09-26-round3-home.md |
| R3-KNOW | CUTTING-EDGE-2026-09-26-round3-knowledge.md |
| R3-ROUT | CUTTING-EDGE-2026-09-26-round3-routines.md |
| R4-CHAR | CUTTING-EDGE-2026-09-26-round4-character.md |
| R4-GROW | CUTTING-EDGE-2026-09-26-round4-growth.md |
| R4-WELL | CUTTING-EDGE-2026-09-26-round4-wellbeing.md |
| MEM | MEMORY-RESEARCH-2026-09-26.md |
| CREA | CREATIVITY-AUDIT-2026-09-25.md (and creativity-2026-09-25/*.md) |
| COM-C / COM-OS | COMPETITORS-COMMERCIAL-2026-09-25.md / COMPETITORS-OPEN-SOURCE-2026-09-25.md |

## Things the reviewers should know before starting (checked here)

1. **Memory ideas 1-4 are already built in another agent's worktree, not
   merged:** `.claude/worktrees/agent-a4d69393e5376ccb0`, commits `9abdd68`
   (re-ranker), `c33b5f0` (bigger self-test), `d2d8831` ("said again"),
   `eee9b03` ("true from" dates), `a1b133e` (docs and audit fixes) - read
   with `git log`, not run.
2. **"Every phone notification local only" is built in another worktree,
   not merged:** `.claude/worktrees/agent-a85710b02d8399f76`, commit
   `e372eb7`; `setLocalOnly(true)` at
   `jarvis-client/app/src/main/java/com/jarvis/client/service/ScheduleNotifier.kt:129,183,237`
   and `EventService.kt:362` there. It covers alarms too, so R2-EXP's owner
   question ("let alarms reach the watch?") has been answered in code as
   "everything stays on the phone" without the owner being asked. The
   lock-screen-widget half (`not_keyguard`) is not built: no match for
   "keyguard" in either worktree's `res/xml/` widget files (the only hit is a
   comment in `voice_interaction_service.xml:9`).
3. **R3-KNOW's "`file_read` can read any path" is already fixed** on this
   branch: commit `1ce1dac`; the refusal list is at
   `backend/jarvis_agent.py:201-224` (`/.ssh/`, `/.gnupg/`, ... at `:208`).
4. **ENG's "the MCP bridge draft is not in the repo" is out of date:** it is
   now at `docs/designs/mcp-draft-2026-09-23/` (`jarvis_mcp.py`, `DESIGN.md`,
   tests), added by commit `676538e`.
5. **A conflict between reports on MCP:** ENG §9 says local stdio servers
   only, "no HTTP servers"; CAP #10 and #12 plan to use Home Assistant's MCP
   server (HTTP, on the home network) and Logseq's (HTTP on 127.0.0.1 with a
   bearer token). The owner's words are "local servers only"
   (CLAUDE.md line 348-350). Which of these counts as "local" needs deciding.
6. **A difference on phone notifications:** CAP #17 proposed "only the
   sender name and app are sent, never the message text"; the owner's
   decision (CLAUDE.md line 358-365) allows summarising when asked, so text
   would reach the PC. The Rules and Security reviewers should compare them.
7. **CLAUDE.md line 104-105: "Never build a control that ... approves in
   bulk."** The plan card (I61) and a routine's single card (I62) must be
   checked against it.

---

## Engine (I01-I13)

**I01. Check what the model can do before offering tools.** Ask Ollama
(`/api/show`) whether the current model supports tools, and do not send tools
to one that does not; say plainly "this model cannot use tools". Today such a
model fails every turn with a wrong "restart Ollama" message (per ENG, not
re-checked here; I found no use of Ollama's `capabilities` field in
`backend/jarvis_agent.py` by grep - the only hits at `:5`, `:380`, `:764` are
unrelated). Size S. Source: ENG §1. Status: owner chose to build ("fixed
without asking", CLAUDE.md line 355).

**I02. `OLLAMA_NO_CLOUD=1` on both Ollamas.** One Ollama setting that makes
Ollama itself refuse its cloud models and cloud web search, as a second lock
behind rule 1. Needs a test that installing a model still works. Size S.
Source: ENG §2. Status: owner chose to build (CLAUDE.md line 356); not found
anywhere in `backend/` (grep).

**I03. Record the prompt-cache hit on every turn.** Ollama now reports how
much of a question it reused instead of re-reading. Jarvis would log "prompt
N, reused M" in its timings and the preflight - numbers only - before any
model switch. Size S. Source: ENG §3. Status: new.

**I04. "Fill in this form" retry for a broken tool call.** When the model
picks a real tool but writes broken arguments, the one retry asks Ollama to
fill that tool's own form (its schema), so the result cannot be malformed.
Still goes through the gate. Size S-M. Source: ENG §4. Status: new.

**I05. Tool test: "ask, don't guess" and multi-step cases.** Add test cases
where a needed value is missing (did the model ask, or invent a time or a
recipient?) and 2-3-step cases judged on the final call. Runs on the PC only.
Size S-M. Source: ENG §5. Status: owner chose to build (CLAUDE.md line 348).

**I06. Short tool list, more on request ("lean mode").** Always offer a small
core of tools; the rest come through one "more tools" tool when the model
asks. Frees the model's working memory; must come before MCP. Size M.
Sources: ENG §6; COM-OS line 139 and COM-C line 8 (OpenClaw's lean mode /
Tool Search); CAP "what changed" table (OpenClaw turned it on by default).
Status: owner chose to build (CLAUDE.md line 347).

**I07. The MCP bridge (plug-in tool servers), local only.** MCP is a standard
way to plug outside tool programs into an assistant. Local servers only,
installed once with pinned versions, a card to start each server, read-only
first, every call through the gate, results treated as outside text; speak
the new 2026-07-28 spec too. First servers suggested: git (read tools only
at first) and an "Everything" file-name search server (see I39). Size L.
Sources: ENG §9; CAP #10 and #12 (want HTTP servers - see note 5 above);
EXTRACTION-RESEARCH-2026-09-23 (the draft). Status: owner chose to build
(CLAUDE.md line 348-350); a draft exists at
`docs/designs/mcp-draft-2026-09-23/`.

**I08. MTP speed-up for Qwen 3.5.** Some models carry a small built-in
"guess the next few words" head; one Modelfile line turns it on in Ollama.
Claimed 1.5-2x faster answers; an open Ollama bug can make it 10x slower, so
measure first. 12 GB card first. Size S. Source: ENG §7. Status: new.

**I09. A model shortlist to test on each card.** A test, not a switch: run
the tool test on Qwen 3.5 4B (8 GB card), Gemma 4 E4B, Ministral 3, and a
smaller-file (IQ4_XS) version of the 8B that frees ~0.6 GiB for longer
chats. Each is a download. Size S (test). Source: ENG §8. Status: new.

**I10. Second card: one model for long talks AND pictures.** When the 12 GB
card is in and measured, try Qwen 3.5 9B as both the "Longer conversations"
and the "Pictures" model, so the two no longer swap in and out. Size S.
Sources: VV §4; ENG §8; COM-C lines 230, 251 (Qwen 3.5 9B for the second
card); RESEARCH-2026-09-24 §6. Status: new (queued earlier; waits for the
card, CLAUDE.md line 68).

**I11. A picture-based "pointer" for Windows control.** When an app's buttons
have no readable names, a local vision model points at the named thing in a
screenshot; the card shows a cropped picture of the exact target; one plan,
one card, never a loop. Needs the 12 GB card. Size L. Source: ENG §10.
Status: new.

**I12. Health readings for BOTH graphics cards.** Heat, power and "slowed
down because hot" for each card, in both apps' Hardware screen and the
widget. Today the desktop reads only the first card: checked,
`jarvis-desktop/src-tauri/src/commands.rs:2617` takes `text.lines().next()`.
Size S. Source: R3-HOME #1. Status: new.

**I13. A measured power limit per card.** Jarvis measures speed at 100%, 85%
and 70% of each card's power limit, shows the trade-off, and gives the owner
one PowerShell line to paste in an administrator window; Jarvis itself is
never elevated. Size S-M. Source: R3-HOME #2. Status: new (the 2060 part
waits for the card).

## Voice & vision (I14-I30)

**I14. Read the text in a screenshot, on the processor (OCR).** OCR =
optical character recognition, turning a picture of text into text. When the
model cannot see pictures, send the screenshot's text instead, marked as
outside text (it taints the turn). RapidOCR or Windows' own OCR. Both apps
through the backend. Size S-M. Source: VV §1. Status: owner chose to build
(CLAUDE.md line 345-346).

**I15. A newer "Hey Jarvis" detector (livekit-wakeword).** Keeps the same
front end Jarvis already runs, replaces the last small model; claimed 100x
fewer false wake-ups (measured on another phrase). Trained once on the PC,
then used by PC and phone; re-measure with the voice check. Size M.
Source: VV §2. Status: owner chose to build (CLAUDE.md line 351-352).

**I16. Pocket TTS, a voice-copying voice on the processor.** A third
custom-voice engine beside ZipVoice, run through the voice library Jarvis
already uses (sherpa-onnx); claimed first audio in ~0.2 s. Its consent terms
match the existing custom-voice card. Timed test before it replaces anything.
Size M. Source: VV §3. Status: owner chose to build (CLAUDE.md line 351-352).

**I17. Kokoro voice on the graphics card.** Run the everyday voice on the
second card for ~1 s spoken replies. Size not given. Sources: COM-C lines
230, 251; VV intro ("queued voice work", not repeated). Status: new (queued
earlier; waits for the card).

**I18. Name hints for speech-to-text.** Pass Home Assistant device names,
contact names and voice names to the speech model so rare names are heard
right. A known bug (empty or invented text ~20% of the time in the needed
mode): behind a setting, off by default, measured first. Size S-M.
Source: VV §5. Status: new.

**I19. Household sounds for "tell me when".** A small sound-labelling model
("smoke alarm", "doorbell", "glass breaking") as a new "tell me when" kind;
it means the PC microphone listens all the time, so turning it on is a card;
no audio kept; "not a safety device". Size M. Source: VV §6. Status: new.

**I20. Reading documents from photos (PaddleOCR-VL).** A small document model
that turns a photo of a letter, bill or table into clean text; only if Qwen
3.5 9B turns out weak at documents. Outside text. Size M. Source: VV §7.
Status: new.

**I21. Noise clean-up before speech-to-text (GTCRN).** A tiny model that
cleans noisy audio, placed AFTER the owner's voice check so the check's
measured limits still hold; kept only if word errors drop. Size S.
Source: VV §8. Status: new.

**I22. A neural speech detector in both apps.** Replace the loudness trigger
that starts a recording (a fan or TV can start one) with Silero VAD or TEN
VAD (TEN's licence has extra conditions). Not speech-to-text, so the phone
rule holds. Size M. Source: VV §9. Status: new.

**I23. A stronger voice-ID model (ReDimNet).** Only if the owner's real
"someone else" numbers show the voice check letting others in; needs its own
measured limits. Size M. Source: VV §10. Status: new.

**I24. A better voice on the 12 GB card (CosyVoice 3, Qwen3-TTS, Chatterbox).**
More emotion and better voice copies; it would replace F5, not add to it,
and competes with the long-conversation lane for memory; some may not run
well on this card generation. Size L. Source: VV §11. Status: new (waits for
the card).

**I25. A fake-voice detector used only to make things stricter.** Research
says no local detector is reliable in 2026 and none catches a replayed
recording; if ever tried, a flagged hands-free turn is treated as "Only
trust the talk button", never the reverse. Size M. Source: VV §12.
Status: new (research only).

**I26. The "say these 3 words" check.** Words shown on screen, never spoken,
that a recording made earlier cannot contain - the real answer to "can
Jarvis tell a recording from me?". Size not given. Sources: VV §12 ("the
real fix, the owner's call"); RESEARCH-2026-09-24 §5 (line 113). Status: new
(owner's call, not decided).

**I27. "Show me where to click" instead of clicking.** Jarvis highlights the
spot on screen and says the step; the owner clicks. Acts on nothing, so no
card; needs a model that can see (second card). Size M-L. Sources: COM-C
line 279; VV intro (not repeated). Status: new (queued earlier).

**I28. Speaking-speed setting in both apps.** Slower / normal / faster; the
setting exists only in a settings file today (per R2-PER; not re-checked).
No card, like manner. Size S. Source: R2-PER §2. Status: new.

**I29. Make and edit pictures on the 12 GB card.** "Draw a birthday card",
"remove this photo's background", with FLUX.2 klein 4B or Z-Image through
stable-diffusion.cpp; the long-conversation model must step aside while a
picture is made; refuse turning a real person's face into someone else.
Size L. Source: R2-PER §11. Status: new. **Q:** build later once the card is
in and measured (recommended) / not interested.

**I30. Make music and sound effects.** ACE-Step 1.5 or Stable Audio 3.0 Small
for a focus-session loop or a custom alarm sound. Mostly fun; low priority.
Size M-L. Source: R2-PER §13. Status: new.

## Memory (I31-I38)

**I31. A re-ranker over the top ~20 facts.** A small model on the processor
re-reads the question with each candidate fact and re-orders them before 5
go to the model; it never adds, changes or hides a fact; falls back to
today's order if slow. Size S. Source: MEM idea 1. Status: already in
progress (owner chose, CLAUDE.md line 325-326; commit `9abdd68` in worktree
`agent-a4d69393e5376ccb0`, not merged).

**I32. A bigger memory self-test.** Two-fact questions, time questions and a
test of the learner (does it propose the right fact, keep every "not", date
"last week" right?). Size S-M. Source: MEM idea 2. Status: already in
progress (CLAUDE.md line 325-327; commit `c33b5f0`, same worktree).

**I33. "Said again" counts.** When the owner repeats a known fact, keep the
date and how it was said (no words), instead of dropping it. Feeds search
tie-breaks and the tidy's "keep this in mind?" offer. Size S. Source: MEM
idea 3. Status: already in progress (CLAUDE.md line 327; commit `d2d8831`,
same worktree).

**I34. Real "true from" dates; older news never replaces newer.** A fact
about the past gets its real date; a correction about an earlier time cannot
retire a newer fact. Past dates only. Size M. Source: MEM idea 4. Status:
already in progress (CLAUDE.md line 327; commit `eee9b03`, same worktree).

**I35. Search hints.** The local model writes 3-6 extra search words per
saved fact ("boss" for "manager"), kept in the index only, never shown or
sent to the model; Erase must wipe them too. Size M. Source: MEM idea 5.
Status: new.

**I36. Date-closeness boost.** A question with a date prefers facts from near
that date (re-orders only). Best after I34. Size S. Source: MEM idea 6.
Status: new.

**I37. The overnight tidy, cards only.** On the one scheduler: likely
duplicates, likely contradictions, "is this still true?" - at most 5 cards a
night, never changing memory by itself. Size M-L. Sources: MEM idea 7;
CREA (sleep mode). Status: owner chose to build, after I31-I34 (CLAUDE.md
line 328; one shared scheduler, line 176-179).

**I38. Search the owner's own past chat words, when asked.** "What did I say
about the boiler in August?" answered from the owner's own typed and voice
turns in the encrypted history; nothing saved from it. Changes a written
rule (ARCHITECTURE §5: history is not memory). Size M. Source: MEM idea 8;
CREA #18 (whether "ask my own stuff" may search past chats). Status: owner
decided it waits until I31-I34 are built and measured (CLAUDE.md line
329-330).

## Knowledge & documents (I39-I60)

**I39. "Where's that file?" by name.** Find files by name in under a second
with voidtools Everything (`es.exe`, or an Everything MCP server) or Windows'
own search index, limited to folders the owner allows; never Everything's
network server. Names are private: local model only, outside text. Size
S-M. Sources: R3-KNOW #3; ENG §9 (Everything search server as a first MCP
server). Status: new. (A related refusal list for `file_read` is already
built: `backend/jarvis_agent.py:201-224`.)

**I40. Documents to text on the PC, read in slices.** MarkItDown turns PDF,
Word, PowerPoint and Excel files into text on the PC; the model searches and
reads one slice at a time instead of pasting whole files. Install only the
document parts: MarkItDown's audio part sends sound to Google and its
YouTube part fetches from YouTube (R3-KNOW "found while checking"). Size
S-M. Sources: CAP #5; R3-KNOW (found while checking); CREA #18 (the first
step of "ask my own stuff"). Status: owner chose to build (CLAUDE.md line
353).

**I41. One local "library" index.** One search index (word search + meaning
search + the approved re-ranker) over the vault, the wiki and folders the
owner picks, in its own file, never memory. None by default; `.ssh`,
password files, `.env`, browser profiles always left out. Size M-L. Source:
R3-KNOW #5. Status: new (the search half of the owner-chosen I40). **Q
(implied):** which folders.

**I42. "Where this came from" under every answer, with a quote check.** List
the notes, wiki pages, web links and files Jarvis read for an answer (from
what the tools returned, never from the model's claim), and check word for
word that its quotes really are in them. Both apps. Size M. Sources: R3-KNOW
#1; R3-ROUT §9 and R3-KNOW #4 reuse the same check. Status: new.

**I43. Reading list in the daily note ("save for later").** "Save for later:
<link>" adds an unticked line to today's Obsidian daily note; "what's on my
reading list?" is answered without the model. Jarvis never fetches the page.
Size S. Source: R3-KNOW #2. Status: new.

**I44. The wiki builder's next steps.** "Check my wiki" report
(contradictions, stale or orphan pages), quotes checked against the source,
big documents split at headings instead of refused, and "ask the wiki" by
reading its index first. Fixes only through the existing wiki card. Size M
(four S parts). Source: R3-KNOW #4. Status: new.

**I45. Spreadsheet and CSV questions through a locked-down DuckDB.** The model
writes ONE read-only database query over the one file the owner named; it
runs in a separate process with file, network and extension access switched
off, a time limit and a row cap; the query and result are shown. Size M.
Source: R3-KNOW #6. Status: new.

**I46. Transcribe and summarise an audio or video FILE the owner gives.**
Cut a podcast, lecture or voice memo at the pauses and turn it into text on
the PC with the parts Jarvis already has; save a `.transcript.md`, summary
only when asked. The text is outside text, never learned; never a live
meeting. Needs ffmpeg. Shares code with the queued "voice memos into
Obsidian". Size M. Sources: R2-PER §7; R3-KNOW #7; COM-C line 225 and
creativity-2026-09-25/future.md line 84 (voice memos). Status: new (voice
memos queued earlier).

**I47. Bookmarks Q&A.** "Did I bookmark a ramen recipe?" read on request from
the browser's bookmarks file; titles are outside text; nothing kept. Size S.
Source: R3-KNOW #8. Status: new. **Q:** bookmarks only for now (recommended)
/ bookmarks plus history (see I48).

**I48. Browser history Q&A, off unless switched on.** "Which site had that
desk last week?" from a read-only copy of the browser's history file, on the
phone-notifications pattern: off by default, on by card, last 30 days,
banking and health sites excluded, nothing kept. Very private. Size M.
Source: R3-KNOW #11. Status: new. **Q:** same as I47.

**I49. News headlines from feeds the owner chooses.** Headlines only (title,
site, time) in the briefing, from feeds typed in on the PC, or from a local
Miniflux/FreshRSS. A new way out of the PC: needs an egress row. Size M.
Source: R3-KNOW #10. Status: new. **Q:** one card per feed added
(recommended) / keep "news: not available". Decide with I67.

**I50. Wiki pages on the desktop's memory map; "Open in Obsidian".** Draw
wiki pages and their links as a second layer of the Brain's galaxy, or first
just an "Open in Obsidian" button. Desktop only (the graph stays off the
phone). Size S. Source: R3-KNOW #9. Status: new.

**I51. Obsidian CLI, allow-listed.** Ask Obsidian itself where today's note
is (ends the "date formats we cannot compute" gap) and list open tasks; only
a fixed list of read commands, never its `eval`. Size S. Source: CAP #11.
Status: new.

**I52. Logseq database graphs: detect and say so; later a dry-run card.**
Logseq's new database version would not see Jarvis's file appends; first
detect such a graph and say so; later use its local MCP server's "pretend"
mode as the card's preview. Size S, then M (after I07). Source: CAP #12.
Status: new.

**I53. Save an email draft into the owner's own Drafts folder.** "Draft a
reply to Sam" puts a draft in Gmail's Drafts; nothing is sent. Size S-M.
Source: CAP #4. Status: owner chose to build (CLAUDE.md line 354). **Q (still
open):** ask first only after outside text, like notes (recommended) /
always a card.

**I54. Contacts from a `.vcf` file on the PC.** "Email Priya" finds the
address from an exported contacts file; the send card adds "in your
contacts" or "not in your contacts". Desktop only; never learned as facts.
Size S-M. Source: CAP #6. Status: new.

**I55. Write events to a CalDAV calendar, one card per event.** Only useful
if the owner has a non-Google calendar (Google is covered by I93). Size M.
Source: CAP #16. Status: new.

**I56. Scan to Obsidian.** Scan paper on the PC (NAPS2 console or Windows'
built-in scanning), read its text locally (I14's OCR), save PDF plus text
into the vault; outside text, so the note write gets a card. Size M.
Source: R3-HOME #12. Status: new.

**I57. "Quiz me on this note" with smart review times (FSRS).** The model
drafts 5-10 question cards from a note the owner picks; the owner edits
them; Jarvis asks again on Anki's spacing maths (py-fsrs, MIT) through the
one scheduler; quizzes run as a temporary chat. Size M. Source: R2-PER §6.
Status: new. **Q (in report):** whether review reminders need a card.

**I58. "Translate this".** Now: the everyday model with a fixed translation
instruction. Later, if not good enough: a dedicated local model (Hy-MT2
1.8B, TranslateGemma, MADLAD-400; NLLB is non-commercial). Size S, then M.
Source: R2-PER §8. Status: new.

**I59. Language practice.** "Let's practise French" in a temporary chat, one
gentle correction per turn. Typed works now; spoken does not (today's speech
model is English only). Size M. Source: R2-PER §9. Status: new.

**I60. Code helper for a beginner.** "Help me understand this error / file":
explain in plain words and say what to try; never edits by itself (any edit
later a full diff on a card). Size M. Source: R2-PER §10. Status: new.

## Routines & agents (I61-I74)

**I61. The plan card.** For a job with several steps, one card lists every
step; the owner's yes runs the safe steps; a risky step (leaves the PC,
cannot be undone, or needs a person) gets its own card at its moment. At
most 8 steps, 3 risky; risky steps wait while no app is connected. Size M.
Source: R3-ROUT #1. Status: new. **Q1:** one plan card, risky steps asked
again (recommended) / keep one card per step. (Check against CLAUDE.md line
104-105, "never ... approves in bulk".)

**I62. Routines compiled to a checked plan.** "Movie night" becomes a saved,
code-checked list of literal steps with typed blanks the owner fills; "Try
it" shows what would happen without doing it; each step is read back after
it runs; a routine that acts never runs by itself. Size M. Sources: R3-ROUT
#4; creativity-2026-09-25/future.md idea 7. Status: new (queued earlier).

**I63. Goals, stage 1 - no AI model.** "Track: insulate the garage by 1
November" goes on Coming up with a weekly "done / still on it / stop" and a
briefing line; owner's own words only. Size S-M. Sources: R3-ROUT #2; CREA
#19; future.md idea 3. Status: new (queued earlier). Note in report: the
scheduler asks by default for a new kind, so "no card" must be written down.

**I64. Goals, stages 2-3.** The model drafts at most 7 steps the owner edits
(accepting runs nothing); later, background re-planning offered through the
back-off rules, on the second card or the big model. Size M. Source: R3-ROUT
#7. Status: new.

**I65. Undo on the card.** Before approval each step says how it can be taken
back, or "cannot be undone"; "Undo this run" lists the reversals on one card.
Jarvis can undo only what its own tools did, if nothing changed since.
Size M. Source: R3-ROUT #5. Status: new.

**I66. More "tell me when" sources: a folder on this PC, and the calendar.**
"Tell me when a file lands in Scans"; "tell me when something is added for
Friday". Same card, same end date, a match only notifies. Size S-M each.
Source: R3-ROUT #6. Status: new.

**I67. "Tell me when this web page changes."** The one address the owner
typed is fetched on a schedule (price drops, page changes). A new named way
out of the PC. Size S-M. Source: R3-ROUT #6. Status: new. **Q (later):**
wanted at all; decide with I49.

**I68. Instant email "tell me when" (IMAP IDLE).** One open connection that
the mail server tells when mail arrives, instead of signing in every 5
minutes. The owner's Python is 3.12, so the IMAPClient library (or a
hand-written loop) is needed. Size S-M. Source: CAP #3. Status: owner chose
to build (CLAUDE.md line 353-354).

**I69. "Tell me if X hasn't replied by Friday."** The same From-line match
with a deadline; it notifies when NO match arrives. Size S (part of CAP #3's
S-M). Source: CAP #3. Status: new (same report item as I68, but not named in
the owner's decision).

**I70. "Tell me when CI finishes / the APK is published" (GitHub).** A new
"tell me when" source for one named repo's latest workflow run or release,
with a read-only token that goes only to GitHub. Size S-M. Sources: CAP #9;
CREA #14 (merged with the GitHub watchlist). Status: new.

**I71. Night shift: long jobs that only read and prepare.** Jobs queued for
the night (approved searches, wiki drafts, a goal re-plan, the journal
draft) run on the 12 GB card and wait as "Ready for you"; anything that acts
waits for a morning card. Clash found: the big model has no standby flag.
Size M. Source: R3-ROUT #8. Status: new. **Q2:** run night jobs only before
standby starts (recommended) / let them run during standby.

**I72. Research helper.** "Compare these three heat pumps, with sources": one
card with the exact search words, a comparison table, every claim carrying a
checked quote; never loops by itself; the reader has no tools; works from
snippets unless whole pages are allowed (a new way out). Size M-L. Source:
R3-ROUT #9. Status: new. **Q (later):** may it read whole web pages.

**I73. Reading phone notifications (safe version).** Off by default, on with
a card, chosen apps only (never banking), one-time codes hidden first,
outside text, shown or summarised only when asked, never SMS, never replies.
Feeds "tell me when" and "what did I miss?". Android may need "Allow
restricted settings" for a sideloaded app (not verified). Size M-L. Source:
CAP #17. Status: owner chose to build, queued after the four cutting-edge
groups and the security audit (CLAUDE.md line 358-365). See note 6 above.

**I74. The weekly journal draft.** Sunday evening, a page in Obsidian: what
the owner worked on, decided and changed their mind about; saved after a
card. A candidate night-shift job. Size M. Sources: CREA #22; future.md idea
5; R3-ROUT (not repeated) and #8; R2-EXP intro. Status: new (queued earlier).

## Home and the PC itself (I75-I94)

**I75. Weather from the owner's own Home Assistant.** Read HA's forecast (HA
already fetches it) for the briefing and a no-model "what's the weather?";
only that one read-only service. Today the briefing says "not available":
checked, `backend/jarvis_briefing.py:117` and `:338`. Size S. Source: CAP
#1. Status: owner chose to build (CLAUDE.md line 343).

**I76. "Why did the hall light turn on?"** Read HA's logbook for the named
device (it now records what triggered a change); read-only, outside text.
Size S. Source: CAP #8. Status: new.

**I77. HA's own "exposed devices" list as Jarvis's device list.** Use the
devices the owner exposed in HA as the list the model may name; acting stays
on Jarvis's own cards. Correction from R3-HOME: HA's MCP device list has no
entity ids, so it cannot drive actions alone. Size S-M. Sources: CAP #10;
R3-HOME (correction). Status: new. See note 5 above (HTTP MCP).

**I78. Rooms and floors: "turn off the downstairs lights".** Read HA's area
and floor lists (needs a small WebSocket client, a new dependency), turn a
room into a device list, and show one card listing every light; locks,
doors, alarms and covers still get their own. Size M. Source: R3-HOME #4.
Status: new. **Q1:** a room or floor always gets one card (recommended) /
treat a room like named lights under the lights setting.

**I79. Room awareness.** Jarvis knows which room a request came from (a
per-device setting), whether someone else was heard lately, and whether the
owner is at the PC; it only ever makes Jarvis quieter or narrower. Turning
it on is a card. Size M. Sources: R3-HOME #5; CREA ("room awareness" offered
instead of household mode). Status: new.

**I80. "Goes through the maker's cloud" line on home cards.** A card for a
car, a cloud plug or a cloud camera says "Home Assistant sends this through
Tesla's servers". Needs I78's WebSocket client. Size S-M. Source: R3-HOME
#6. Status: new.

**I81. A non-admin Home Assistant user for Jarvis.** Setup guide and a
preflight warning "this token is an admin's", so a leaked token cannot use
HA's admin-only routes. Also: copy HA's exact address (new installs have no
`:8123`). Size S. Source: R3-HOME #7. Status: new.

**I82. "Tell me when someone is at the door."** Use Frigate's or HA's
"person detected" sensor as a "tell me when" source: labels only, no
picture, no face. Size S. Source: R3-HOME #8. Status: new.

**I83. Camera snapshot on request.** "Show me the front door": one still,
shown in the app, never written to disk; the model sees it only if asked,
on the local picture model; its own card; never face recognition. Size M.
Source: R3-HOME #9. Status: new.

**I84. Energy: "what did running Jarvis cost today?"** From the cards' power
readings (I12), and optionally HA's energy totals. Size S / M. Source:
R3-HOME #10. Status: new.

**I85. Welcome home, done safely.** On arrival, a "while you were out"
summary when the owner sits down, and at most one offered card ("turn on
the hall lights?"); nothing switches by itself. Size S-M. Source: R3-HOME
#11. Status: new.

**I86. Printer, weather station and car levels, read-only through HA.**
Briefing lines such as "toner low" or "car at 80%"; car locks and covers
keep their own cards. Size S each. Source: R3-HOME #13. Status: new.

**I87. Shopping list mirrored to a Home Assistant to-do list.** Readable in
HA's phone app while the PC is off. Writes to HA, so the owner chooses: a
setting turned on by one card, or a card per add. Size M. Sources: CAP #15;
CREA "later" question (a read-only shopping list on the phone). Status: new.

**I88. A home that learns routines.** Notices routines in HA's own history
and offers one automation at a time, as a card. Size L. Sources: CREA #21;
future.md idea 4; R3-ROUT (not repeated). Status: new (queued earlier).

**I89. "Wake my PC" from the phone.** At home the phone sends the wake
packet itself; away, through an always-on device at home (HA's button,
tailscale-wakeonlan or UpSnap); never a router port-forward. Size M.
Source: R3-HOME #3. Status: new. **Q2:** use HA's own button (recommended) /
only when the phone is on home Wi-Fi.

**I90. Sleep the PC, waking it for the next alarm.** A Windows scheduled task
set to wake the computer before the next alarm; whether it works without an
administrator prompt is not verified. Size M. Source: R3-HOME #14. Status:
new.

**I91. Music and video control on this PC.** "Pause", "next", "what's
playing" through Windows' media controls, in both apps. Size S-M. Sources:
CAP #7; COM-C line 236 (queued "media keys"). Status: new (queued earlier).
**Q1:** without a card, as a setting that is off until turned on
(recommended) / a card each time.

**I92. "What needs updating on this PC?" (winget).** List apps with updates;
updating is one card plus Windows Hello per package, never "update all".
Listing is a new way out of the PC. Size S (list) / M (update). Source: CAP
#14. Status: new.

**I93. "Also on my phone": alarm and calendar event handed to the phone's own
apps.** A button hands an alarm to the phone's Clock app, or an event to the
phone's calendar, by the owner's tap (that tap is the approval); rings even
with the PC off. The button should warn about two alarms. Size S. Sources:
CAP #2; creativity-2026-09-25/usefulness.md #12 (add to Google Calendar by
the owner's tap). Status: owner chose to build (CLAUDE.md line 344-345).
(Listed here because it replaces an HA/PC job with the phone; it is an
Experience feature too.)

**I94. "Text Mum I'm late" as a ready SMS draft.** Opens the phone's Messages
app with the text filled in; the owner picks the person and presses send.
Size S. Source: CAP #18. Status: new.

## Trust & safety (I95-I115)

**I95. Planted-instruction test with the real model, on the PC.** Feed the
AgentDojo and LLMail-Inject attack texts through Jarvis's real tool schemas
to the local model and count how many attacker-made cards the owner would
see. Decides I104-I108. Size S-M. Source: R2-TRU #1. Status: new.

**I96. Encrypted backup with a recovery code, and a plain restore.** One
file (memory, history, schedule, settings, notes, voice enrolment, the
history key; not keys or the pairing token), encrypted with `age` and a
recovery code shown once; restore is one card plus Windows Hello, and backs
up first. "Erase the words" cannot reach old backups - must be said. Size M.
Source: R2-TRU #2. Status: new. **Q1:** this PC or a USB drive only
(recommended) / also a shared folder on the home network.

**I97. Data health in the preflight.** Read-only checks: each database's
integrity, free disk space, backup age, whether the history key exists;
WARN, never fix. Size S. Source: R2-TRU #3. Status: new.

**I98. Watchdog: restart the backend after a crash.** At most 3 times in 10
minutes, then stop and say so. Size S-M. Source: R2-TRU #4. Status: new.
**Q2:** yes, up to 3 times (recommended) / no, I will restart it.

**I99. Hang and crash notes kept on the PC.** Python's `faulthandler` and a
Rust panic file, newest 10, scrubbed before any sharing. Size S. Source:
R2-TRU #5. Status: new.

**I100. Windows crash dumps kept on the PC (WER LocalDumps).** Native crashes
become diagnosable; even a mini dump can hold the token, so it is the
owner's call. Size S. Source: R2-TRU #16. Status: new.

**I101. Chat-history key protected by the PC's security chip (TPM/VBS).** The
key cannot be copied off the PC (but any program of the owner's can still
use it); only after backups exist, since a cleared TPM would lose history
for good. Size not given (not ranked). Source: R2-TRU #16 (note). Status:
new.

**I102. QR pairing with per-device keys ("more devices").** QR code with a
one-time secret and expiry; the phone's own key in its security chip, with
key attestation checked offline; one PC card with Windows Hello and four
matching words; a token per device, each removable; a short typed backup
code only over encrypted links. Size L. Sources: R2-TRU #6; COM-OS lines
66, 118, 148 and COM-C lines 220, 249 (OpenClaw); R2-EXP #5 (first-run
step). Status: owner chose to build (CLAUDE.md line 169-172).

**I103. Approval gap step 2: a fingerprint-signed yes from the phone.** A
second phone key that needs a fresh fingerprint or PIN for each use signs
the card id, a one-time number and a hash of the card's words; the backend
checks it. Size M (inside I102). Source: R2-TRU #7;
docs/APPROVAL-GAP-DESIGN.md. Status: owner chose to build, with "more
devices" (CLAUDE.md line 238-240).

**I104. Value-level labels on tool arguments.** Each tool names its sensitive
arguments (recipient, command, path, URL); a value taken from outside text
there gets a top-of-card warning and makes the card "heavy". Stricter only.
Size M. Source: R2-TRU #10 (FIDES/Progent idea). Status: new.

**I105. A tool-less "reader" pass for email and web text.** After an email or
web read, the model fills a fixed short form with no tools; the tool-using
loop sees the form, raw text only on request. Build only if I95 shows fewer
attacker cards. Size M. Sources: R2-TRU #11; R3-ROUT §9 (the research
helper's reader). Status: new.

**I106. Masked re-run before a card after outside text (MELON idea).**
Re-ask with the owner's request replaced by "summarise this"; the same tool
call means the text drove it, and the card says so. Label only. Size M.
Source: R2-TRU #12. Status: new.

**I107. Datamarking of tool output.** Mark every word of outside text so a
small model is less likely to obey it; measure with I95 (it may hurt
reading). Size S. Source: R2-TRU #13. Status: new.

**I108. A small injection classifier as a second warning.** A small model on
the processor flags injection-like text; warning only, never a block. Model
licences not checked. Size S-M. Source: R2-TRU #14. Status: new.

**I109. A ledger of decisions, counts only.** Per card only action, outcome,
seconds to decide, "shaped by outside text"; a weekly "12 cards, 11
approved, 7 in under 2 seconds"; never changes a tier. Size S-M. Source:
R2-TRU #8. Status: new.

**I110. A slower Approve on risky cards.** Approve stays greyed for ~2
seconds and until the whole text has been in view. Stricter only; both apps.
Size S. Source: R3-ROUT #3. Status: new.

**I111. Safer backend updates.** Apply an update into a copy, run the
preflight on it, switch only on a pass, one command back; hash-pinned
packages with a 7-day wait; optionally a CI build with a signed
provenance record. Size M. Source: R2-TRU #9. Status: new.

**I112. `tailscale whois` names the device; Tailnet Lock.** Cards can say
"approved on Pixel 8", and Tailscale's servers cannot add a device without
the owner's signature (owner-side setting). Size S. Source: R2-TRU #15.
Status: new.

**I113. Private notifications stay on the phone; approval widget off the lock
screen.** Mark Jarvis's notifications local-only (never copied to a watch),
and opt the approval widget out of Android 16's lock screen. Size S.
Source: R2-EXP #1. Status: already in progress for the notification half
(commit `e372eb7`, worktree `agent-a85710b02d8399f76`, see note 2); new for
the lock-screen half. **Q (pre-empted by that commit):** let alarms reach
the watch (recommended in the report) / keep everything on the phone.

**I114. "Private copy".** The Copy button keeps answers out of Windows
clipboard history and cloud sync, and hides the preview on the phone. Size
S. Source: R2-EXP #2. Status: new. **Q:** yes, always (recommended) / only
for answers that used a memory or read email.

**I115. Paste guard.** A pasted password, PIN or one-time code is masked in
the stored chat history, with one fixed line saying so; the model still sees
it for this turn, on the local model. Size S-M. Source: R2-EXP #13. Status:
new.

## Experience (I116-I128)

**I116. "Things you can say".** Type `/` in the quickbar or tap "?" on the
phone: a grouped list of the commands that work without the AI model, with
one example each; choosing one fills the box, never sends. Size S-M.
Source: R2-EXP #3. Status: new.

**I117. The Today page.** Four bands: Next, Waiting on you (titles and "Open
the card" - never an Approve), Done today (each line says where it came
from), This evening; shows nothing rather than filler. Reuses the
briefing's builder. Size M. Sources: R2-EXP #4; CREA #10. Status: new
(queued earlier).

**I118. "Close the day".** At a time the owner picks, the Today page shows
what is still open, tomorrow's first thing, and one box "Anything to
remember about today?" whose answer (the owner's own words) goes into the
daily note. Jarvis never writes the reflection. Size S-M. Sources: R2-EXP
#11; CREA #12 (evening wrap-up). Status: new (queued earlier).

**I119. First-run setup = the preflight with a "Fix" button per step.** A
resumable checklist: start Jarvis, the model answers, your voice, pair your
phone (QR), web search provider, "what leaves this PC". Size M. Sources:
R2-EXP #5; COM-C line 229 and COM-OS line 11 (guided setup). Status: new.

**I119 update (ease-of-use audit #21, 2026-09-27).** Four steps the checklist
was missing, added in place: "can your phone reach this PC?" (right before
pairing, so a Tailscale or Meshnet problem is caught before the owner is
asked to type a token), "tools" and "email/calendar" (turning on the
reading tools the PC app can switch on, once there is a PC to switch them
from), and "Jarvis starts by itself" (last, so finishing the checklist also
means not having to start Jarvis by hand again). The full, updated order:
start Jarvis, the model answers, your voice, can your phone reach this PC?,
pair your phone (QR), tools, email/calendar, web search provider, "what
leaves this PC", Jarvis starts by itself. Still Size M, and still **Later**,
after QR pairing (I102) lands - this is the design gaining its missing
steps, not a decision to build it now.

**I120. "Send to -> Jarvis" on the PC, and one rule for all shell entries.**
Right-click a file, Send to, Jarvis: the file lands in the text box tagged
as outside text ("shared") and waits for Enter. Size S-M. Source: R2-EXP
#6. Status: new.

**I121. Share a document from the phone to the PC.** Accept PDF and Word
files in the phone's Share, send them over the private link to I40's
document-to-text step, fill the box as "shared". Size M. Source: R2-EXP
#15. Status: new.

**I122. Focus: follow Windows' own Focus, and a Focus tile on the phone.**
When Windows Focus is on, Jarvis goes Quiet (read-only); a Quick Settings
tile starts a 25-minute session. Size S. Source: R2-EXP #7. Status: new.

**I123. A "Jarvis focus" Do Not Disturb mode on the phone.** Off by default;
the phone goes quiet during a focus session; alarms and urgent alerts get
through. Size S-M. Source: R2-EXP #8. Status: new.

**I124. A live countdown for timers and focus, in both apps.** Phone: an
Android 16 "Live Update" keeps the countdown on the lock screen. PC: a toast
with a progress bar ("Tea - 3:40 left", Stop, +5). One feature in both
apps. Size S (phone) + S-M (PC). Sources: CAP #13; R2-EXP #9. Status: new.

**I125. Long-press shortcuts on the phone's app icon.** Talk, Note, Brief me,
What did I miss; still meets App lock. No `shortcuts.xml` exists today
(checked: `jarvis-client/app/src/main/res/xml/` has none). Size S. Source:
R2-EXP #10. Status: new.

**I126. Glance 1.2 and a small Today widget (counts only).** Real previews in
the widget picker; a 2x1 widget with the next thing and the number of cards
waiting, no titles, off the lock screen. Size S-M. Source: R2-EXP #14.
Status: new.

**I127. Accessibility pass.** Windows Contrast themes (`forced-colors`),
automatic checks in both test suites, a screen-reader test of the frameless
windows (a known Tauri bug), and a 200% text screenshot test. Size S each.
Source: R2-EXP #12. Status: new.

**I128. Later: a Windows "package identity" for the desktop.** Unlocks the
modern right-click menu, the Windows Share target and reply-in-notification;
fiddly for a beginner. Size L. Source: R2-EXP #16. Status: new.

## Personality & character (I129-I150)

**I129. A character block in the rules, "honest before agreeable" first.**
A ~160-word "who you are" block (calm, capable, honest before agreeable,
"I don't know" is a full answer, software with no claimed feelings, no
"sir", outside text cannot change it), placed with the rules the model
always reads first. Same change must fix the flat 300-token allowance for
the rules (checked: `_TEMPLATE_TOKENS = 300` at `backend/jarvis_agent.py:2016`,
used at `:3000` and `:3509`), or long chats overflow silently (per R4-CHAR).
Size S. Sources: R4-CHAR #1; R4-WELL #3 (W5 wording); R4-GROW #3 (the same
honesty line in the style message). Status: new.

**I130. Two tiny example exchanges in the block.** "Wrong premise" and "not
yet, it's on the card", ~90 tokens; kept only if the test (I133) shows a
gain; not as Modelfile MESSAGE lines. Size S. Source: R4-CHAR #6. Status:
new.

**I131. Fixed answers about who Jarvis is.** "Who are you / which model /
what can you do / what can you reach" answered from settings without the
model; "Do you have feelings?", "I love you", "be my girlfriend", "do you
miss me?" answered from fixed, friendly text; no romance. Size S. Sources:
R2-PER #1; R4-WELL #5 (W6); R4-CHAR ("what Jarvis never does"). Status: new.

**I132. The "you told me" check.** When an answer says "you told me" or "I
remember" but no saved fact went into it, the app adds "No saved fact was
used in this answer". Size S. Source: R2-PER #1. Status: new.

**I133. One offline behaviour test on the PC (character, style drift,
wellbeing).** Made-up questions sent to the local model, scored by fixed
checks: identity, "I don't know", holding a right answer under pushback, no
fake actions or feelings, outside text cannot change character, manner,
spoken length, humour limits, drift after 10+ turns, flattery, goodbyes,
crisis wording; plus no-model unit tests in CI. The three reports propose
three scripts; one tool would do. Size M. Sources: R4-CHAR #2; R4-GROW #6;
R4-WELL #7. Status: new.

**I134. Preflight: is the model running today's rules?** Compare the
installed `jarvis-primary` model's stored rules with the backend's copy;
WARN with the one-line fix if stale. Size S. Source: R4-CHAR #3. Status:
new.

**I135. Style rules for fixed lines, checked by a test.** Cards, errors and
notifications carry no personality; a test fails on emoji, "!" on cards,
more than one "sorry", or film phrases. Size S. Source: R4-CHAR #4. Status:
new.

**I136. "Explain simply" / "Patient teacher".** Say what a thing is before
naming it, short sentences, one example - as a switch (round 2) or as a
third preset beside Warm and Plain (round 4). Wording only, no card. Size S.
Sources: R2-PER #2; R4-GROW #1. Status: new (builds on the manner setting,
CLAUDE.md line 255-257).

**I137. A humour setting: Off / Now and then.** A light, dry joke now and
then, in chat answers only, never on cards, errors or serious topics; not a
percentage. Size S. Sources: R4-CHAR #5; R4-GROW #1 (humour dial). Status:
new. **Q:** add it, off at first, on once the test (I133) shows no harm
(recommended) / no humour at all.

**I138. Presets and fine-tune dials, plus "Call me".** Presets (Warm and
brief / Plain / Patient teacher) plus dials for length, formality, humour,
emoji, lists and a "call me" name; each value maps to one fixed sentence
written in the repo; one style message with a 900-character cap held by a
test. Size S-M. Sources: R4-GROW #1, #3 (size test). Status: new (grows the
manner setting, CLAUDE.md line 255-257).

**I139. "How Jarvis talks to you" list.** Every style change as a dated row
saying how it happened, with Undo on each and Reset, in Brain in both apps.
Size S (with I138). Source: R4-GROW #2. Status: new.

**I140. "From now on ..." said by the owner, applied at once.** "From now on
keep it short" or "call me Sam" changes the dial at once with Undo, but
only if the turn passes automatic learning's live-turn checks (own words,
not pasted, not after outside text). Size M. Source: R4-GROW #4. Status:
new. **Q:** just do it, with Undo in Brain (recommended) / a card each time.

**I141. "Just this chat" requests, counted, then one offer.** "Shorter please"
applies to this chat; three of the same in 14 days leads to one offer
through the back-off rules. Size M. Source: R4-GROW #5. Status: new.

**I142. "Between us": inside jokes and shared history.** "We call the printer
'the beast'" saved as an ordinary memory with a label, from the owner's
words only, Forget and Erase as usual, Warm manner only. Size S-M. Source:
R4-GROW #7. Status: new. **Q:** keep them (recommended) / don't keep them.

**I143. "Your words": up to 5 style notes.** Owner-typed notes such as "use
British spelling", stored as facts of kind "style" and placed in the style
line. The one place owner text becomes an instruction; refuse anything about
approvals, sending, rules or tools. Build I138-I142 first. Size M. Source:
R4-GROW #8. Status: new.

**I144. Briefer during a focus session.** While a focus session runs, answers
use "shorter" without changing the saved setting. Size S. Source: R4-GROW
#9. Status: new.

**I145. Settle the older `[persona]` modes against manner.** Eight older
modes sit in the backend's settings, unseen by both apps; check what each
adds to the prompt before adding humour or presets, so styles never
conflict. `jarvis_persona.py` is not in this repo (per R4-CHAR; not
re-checked). Size S to look, M to merge. Source: R4-CHAR #7. Status: new
(owner's call).

**I146. Games and small talk in a temporary chat.** 20 questions, trivia,
riddles, a story together, always in a temporary chat so "I'm a dragon" is
never learned as a fact. Size S. Source: R2-PER #5. Status: new. **Q:**
games always in a temporary chat (recommended) / normal chat.

**I147. The face follows the voice's shape, not only its loudness.** Split
the sound into low (open vowels) and high (hiss) bands to drive the face,
on every face, no new model; inside the flash limits. Size S. Source:
R2-PER #3. Status: new.

**I148. Idle life for the face.** A slow glance, dozing after a long quiet
spell, a calmer evening look, a brief "perk up" on "Hey Jarvis"; keeps the
idle frame-rate savings and reduced motion; never looks like "approval".
Size S-M. Source: R2-PER #4. Status: new.

**I149. Lip-sync mouth shapes.** Only worth it if a face with a mouth is
ever designed (HeadTTS or Rhubarb). Size M. Source: R2-PER #12. Status: new.

**I150. The name "Jarvis": guidance, nothing to build.** Keep away from
Marvel's styling, "J.A.R.V.I.S.", film lines, "sir" and any actor's voice;
renaming later would be L because the wake word is the ready-made "hey
jarvis" model. Size none (guidance). Source: R4-CHAR ("The name"). Status:
new (guidance only; kept so the reviewers see it).

## Wellbeing (I151-I155)

**I151. A crisis help line.** A code check on the owner's newest words (not
left to the model) for suicide or self-harm; that turn gets a short calm
instruction to the model, no tools offered, and a fixed help message with a
real number added after the answer (and alone if the model fails). Never
contacts anyone, keeps no count, logs nothing. A floor, not a guarantee.
Checked: no answer path handles this today - the words appear only in the
fact-saving lists (`backend/jarvis_sensitive.py:190`, `:280`; no
"helpline", "samaritan" or "crisis" in any `backend/*.py`). Size M. Source:
R4-WELL #1. Status: new. **Q:** which country's help line (UK and Ireland:
Samaritans 116 123 and 999, or another).

**I152. Keep distress words off the "send to a cloud model?" offer.** Add
mood, mental-health and self-harm words to the router's private-word list,
so such a message is never offered to a cloud model. Size S. Source: R4-WELL
#2. Status: new.

**I153. Feelings and goodbye lines in both manners.** Acknowledge a feeling
in a few plain words, then help; never label or diagnose; never ask about
feelings not mentioned; goodbyes get one short line, never "one more
thing". Size S. Source: R4-WELL #4. Status: new.

**I154. Passing moods are not facts; crisis turns are never learned.** A rule
in the learner's prompt, and crisis turns skipped by the learner, so "I feel
hopeless" never becomes a "remember this?" card. No mood log ever. Size S.
Source: R4-WELL #6. Status: new. **Q:** never learn from those messages
(recommended) / learn as normal.

**I155. Optional open test kits with a local judge.** Spiral-Bench,
SYCON-Bench, Bloom, VERA-MH for deeper multi-turn checks; they default to a
cloud judge, so only with a local one (the 14B model on the 12 GB card).
Size M. Source: R4-WELL #8. Status: new.

---

## Count and ranges

155 ids, I01-I155, numbered in order, no gaps.

| Group | Ids |
|---|---|
| Engine | I01-I13 (13) |
| Voice & vision | I14-I30 (17) |
| Memory | I31-I38 (8) |
| Knowledge & documents | I39-I60 (22) |
| Routines & agents | I61-I74 (14) |
| Home and the PC itself | I75-I94 (20) |
| Trust & safety | I95-I115 (21) |
| Experience | I116-I128 (13) |
| Personality & character | I129-I150 (22) |
| Wellbeing | I151-I155 (5) |

Owner already chose to build (CLAUDE.md): I01, I02, I05, I06, I07, I14,
I15, I16, I37 (after I31-I34), I40, I53, I68, I73, I75, I93, I102, I103.
Owner decided to wait: I38. Already in progress (unmerged worktrees):
I31, I32, I33, I34, and the notification half of I113.

---

## Not for Jarvis (the reports' own list; confirm these stay out)

One line each, merged where several reports say the same.

**Engine and tools**
- Windows-MCP as a whole: PowerShell/Registry tools, HTTP serving, usage data on by default (ENG).
- Playwright/browser MCP servers: duplicate the existing browser control without its checks (ENG).
- The MCP "memory" server: the model writes memory with no review (ENG; MEM §7).
- The MCP "fetch" server: a new unnamed way out of the PC (ENG).
- Remote MCP servers, OAuth sign-in, HTTP transport: a network service (ENG; but see note 5).
- Computer-use agents that loop by themselves (Fara-7B, UI-TARS-1.5, OmniTool): a standing grant (ENG).
- Ollama cloud models and Ollama web search: rule 1 (ENG; I02 switches them off).
- TurboQuant 3-4-bit cache: community forks only, card support unverified (ENG).
- Tool calls written as ReAct text: bypasses the schema check for no gain (ENG).
- Splitting one model across both cards: already decided against (ENG; MODEL-TOPOLOGY).
- mcp-scan and scanners that upload the tool list (ENG; RESEARCH-2026-09-24 §4).
- Running models inside ChatGPT Desktop: a cloud app (CAP).

**Voice, vision and sound**
- Talk-and-listen-at-once models (Moshi, PersonaPlex, LFM2.5-Audio): speak before Jarvis can check (VV).
- Omni models as Jarvis's ears (Gemma 4 E2B/E4B audio, Qwen Omni; Qwen3.8-Omni-Flash is cloud-only): no owner check first (VV).
- Speech-to-text on the phone of any kind: standing rule (VV; CLAUDE.md line 104).
- End-of-turn models that read the words; streaming speech-to-text before the owner check (VV).
- Shazam-style music recognition: sends room sound out (VV).
- Always-on camera, face recognition, "who is at my desk" (VV; R3-HOME).
- Porcupine wake word (online licence check); Supertonic 3 (archived) (VV).
- Guessing the owner's mood from their voice (R2-PER; R4-GROW; R4-WELL).
- Other people's voices copied for games; any actor's voice (R2-PER; R4-CHAR).
- Photo-real talking heads or face swaps (R2-PER).
- Cloud cameras and doorbells (Ring, Nest) directly (R3-HOME).

**Memory and learning**
- The model updating, deleting or writing memory by itself (MEM §7).
- Saving what the assistant said (MEM §7; R4-GROW).
- Summarising memories into observations, profiles or personas; a model-written owner profile (MEM §7; R4-GROW).
- Forgetting by "heat" or decay (MEM §7).
- A graph database or Postgres server (Graphiti/Neo4j, KuzuDB archived) (MEM §7; CAP).
- Memory packages with telemetry on by default (mem0, Graphiti, Cognee) (MEM §7).
- The big model re-checking 20 results every question (MEM §7).
- Rewriting Jarvis's rules from feedback (MEM §7).
- Hosted memory or cloud sync, including of the personality (MEM §7; R4-GROW).
- Learning facts from notes, files, feeds, history or transcripts (R3-KNOW).
- Quizzes made automatically from emails or web pages (R2-PER).
- Goals guessed from email or chats (R3-ROUT).

**Knowledge and documents**
- MarkItDown's LLM picture captions, Azure Document Intelligence, audio transcription (sends to Google) and YouTube transcripts (CAP; R3-KNOW).
- Gemini in Chrome / Edge Copilot history answers in the cloud (R3-KNOW).
- Windows Recall, screenpipe (record everything seen) (R3-KNOW).
- Everything's HTTP/ETP server (R3-KNOW).
- Karakeep's default cloud tagging and shared lists (R3-KNOW).
- Adopting qmd whole (Node, downloads models at first run) (R3-KNOW).
- mcp-run-python (archived as unsafe); model-written pandas/Python on the PC (R3-KNOW).
- ContextCite (too heavy for 8 GB now) (R3-KNOW).
- Windows semantic search (needs an NPU) (R3-KNOW).
- Meeting recorders and live meeting notes (CAP; R3-KNOW).
- A knowledge map on the phone (R3-KNOW; CLAUDE.md line 103).
- Downloading from YouTube or podcast sites (yt-dlp) (R2-PER).
- Cloud picture, music or translation services (R2-PER).
- JMAP: not a rule break; revisit only if the owner leaves Gmail (CAP).

**Routines and agents**
- "Always allow" / "don't ask again" for automations, routines, goals or plans (CAP; R3-ROUT; CREA).
- A model deciding which actions need the owner (auto mode) - an AI that approves (R2-TRU; R3-ROUT).
- "You always approve this - loosen it?" offers; suggesting passes from past approvals (R3-ROUT; CREA).
- A watcher that acts when it matches (R3-ROUT).
- Research that keeps searching by itself (R3-ROUT).
- A second automation engine (n8n, Node-RED, Huginn, Temporal, DBOS) (CAP; R3-ROUT).
- CaMeL or Dromedary as the runtime; full CaMeL (R2-TRU; R3-ROUT).
- Cloud background agents (Gemini Spark, ChatGPT scheduled tasks) (R3-ROUT).
- LangGraph as the agent framework (R3-ROUT).
- Approving anything by voice, including a plan's risky step (R3-ROUT; CREA).
- Heartbeat model turns every 30 minutes (OpenClaw) (CAP).
- Cross-provider messaging on by default (OpenClaw) (CAP).

**Home**
- HA's Assist or its MCP action tools controlling devices (they act with no card) (R3-HOME; CAP).
- Reaching HA through Nabu Casa or a public URL; forwarding the wake-on-LAN port (CAP; R3-HOME).
- Jarvis as its own Matter controller (R3-HOME).
- Setting, reading or saying lock PIN codes (R3-HOME).
- Frigate face names, "who is at the door" (R3-HOME).
- A camera Jarvis watches continuously, or storing clips (R3-HOME).
- Tracking other household members' locations (R3-HOME).
- Jarvis running as administrator, or controlling fan curves (R3-HOME).
- Car control through a maker's cloud API held by Jarvis (R3-HOME).
- Arrival or motion switching devices without a card (R3-HOME).
- Printing outside text without a card (R3-HOME).
- Cloud speech-to-text (Soniox in HA) (CAP).
- Household mode (breaks "one owner") (CREA).

**Trust, keys and devices**
- Cloud backups, even encrypted (restic to a USB drive is fine) (R2-TRU).
- Passkeys/WebAuthn at home (public certificate logs, Google sync) (R2-TRU).
- Base64 "encoding" spotlighting (an 8B cannot read it) (R2-TRU).
- promptfoo as shipped (telemetry, cloud fallback); garak is fine offline (R2-TRU).
- Android Protected Confirmation (deprecated) (R2-TRU).
- The backend as a Windows service (breaks microphone, windows, Windows Hello) (R2-TRU).
- An extra Noise encryption channel (R2-TRU).
- Online attestation revocation checks; crash services such as Sentry (R2-TRU).
- A detector used as a block (R2-TRU).
- An Approve button anywhere outside the app (toasts, widgets, tiles, watches, lock screens) (R2-EXP).
- Android AppFunctions or Windows App Actions letting the phone's or PC's own AI call Jarvis (R2-EXP).
- A Wear OS watch app (data may pass through Google's servers) (R2-EXP).
- Background clipboard reading or clipboard managers (R2-EXP).
- Launcher plugins that hold the pairing token (PowerToys, Flow Launcher) (R2-EXP).
- Launcher-side cloud AI (Raycast AI, Advanced Paste to a cloud model) (R2-EXP).
- Open chat share links without sign-in (Open WebUI) (CAP).
- Reading SMS, or sending SMS without the owner's tap (CAP).
- Obsidian CLI's `eval`, plugin and developer commands (CAP).
- Typing API keys on the phone (CREA; note rule 3 was relaxed 2026-09-17 - the Rules reviewer should confirm this still stands).
- A standing cloud grant (CREA).

**Focus, wellbeing and character**
- Jarvis starting Windows Focus (needs Microsoft's token); phone screen-time watching; always-on journal audio (R2-EXP).
- Control/persona vectors, activation capping, steering the model's insides (R4-CHAR; R4-GROW; R4-WELL).
- A LoRA persona fine-tune (Ollama refuses LoRA; owner ruled out fine-tuning) (R4-CHAR).
- An honesty setting; percentage humour or chattiness sliders (R4-CHAR).
- Companion or romance modes, "I missed you", streaks, relationship levels (R4-CHAR; R4-GROW; R4-WELL; R2-PER).
- Marvel styling, "sir", film quotes (R4-CHAR).
- Importing character cards or downloaded personas (R4-CHAR; R4-GROW).
- A persona the model rewrites (Soul.md, Letta persona block) (R2-PER; R4-CHAR; R4-GROW).
- Guessing the owner's personality or psychology (Honcho) (R4-GROW).
- Learning style from thumbs-up marks or engagement (R4-GROW; R4-WELL).
- Mirroring the owner's moods (R4-GROW).
- "Recalling Too Well"'s fixes (saving assistant turns, summarising chats) (R4-GROW).
- Style copied from uploaded writing samples (R4-GROW).
- A "Cynical" or sarcastic preset (R4-GROW: "the owner's call if wanted").
- A mood log, score or chart; a separate sentiment model (R4-WELL).
- Unprompted "How are you feeling today?" (R4-WELL).
- An "AI therapist", CBT course or questionnaire (R4-WELL).
- Calling or messaging anyone by itself in a crisis (R4-WELL).
- "You've chatted 3 hours, take a break" nags (R4-WELL).
- Streaks and guilt nudges (R2-PER).
