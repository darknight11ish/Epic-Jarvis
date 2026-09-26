# Feasibility audit - the Rules reviewer (2026-09-26)

**My question:** can each idea keep the five rules, one card per action,
"never auto-approve", "block acting when the event stream is stale", the
owner-only-words rule for memory, the phone rules (no speech-to-text, no
model catalogue, no bulk approve), and every dated owner decision in
`CLAUDE.md`? Where one is at risk, which one, and what is the smallest change
that keeps it?

Read-only. Paths are from the repo root (`/home/user/Epic-Jarvis`). Every
code claim below was checked in the file named; "not checked" where not.
Report claims I did not re-check are marked "(per <report>)".

## The yardsticks, in plain words (all checked)

- **Rule 1** (`CLAUDE.md:90-91`): email, files, credentials and saved memory
  stay on the local model; the app sends none of it anywhere. Today **no
  cloud lane is configured at all** ("No cloud lane is configured on this
  project yet", `backend/test_router_private_terms.py:14-15`), so the cloud
  risks below are latent, not live.
- **Rule 3** (`CLAUDE.md:94-98`): keys allowed, never logged, sent only to
  their own service, never written to disk in plain text. In practice every
  key so far is entered **on the PC only**: search keys live in Windows
  Credential Manager and "there is no field and no route for a key"
  (`docs/JARVIS-API.md:4241`, `:4349-4355`); the calendar link is "set on
  the PC only" (`CLAUDE.md:215-218`).
- **Rule 4** (`CLAUDE.md:99-100`): no auto-approve; no acting on a stale
  event stream. The stale check lives in the apps: desktop
  `jarvis-desktop/src-tauri/src/commands.rs:2142-2160`, phone
  `JarvisRuntime.kt:290-297`. Stopping is never gated
  (`docs/ARCHITECTURE.md:218-227`).
- **"No approve-all" means** no control that grants **future, unnamed**
  actions. One decision about one bounded set, every item shown in full, is
  allowed (`docs/ARCHITECTURE.md:102-119`); a smart-home set is at most ten,
  never cut (`:115`). A standing setting for one named kind, off by default,
  on by a card, off at once, is not an approve-all (`:121-138`) - but each
  such setting has been an **owner decision**, and "nothing outside that list
  can be loosened from an app" (`CLAUDE.md:300-305`).
- **Card cap:** five cards per answer (`backend/jarvis_agent.py:1560`).
  Actions that always need a person: `NEEDS_A_PERSON`
  (`backend/jarvis_agent.py:1169-1177`).
- **The lights setting** runs with no card only when "every device is named
  in the owner's newest message" and nothing from outside shaped the turn
  (`backend/jarvis_agent.py:1185-1192`).
- **Owner-only words:** facts are learned only from the owner's own typed or
  verified-voice words (`CLAUDE.md:122-127`; `docs/ARCHITECTURE.md:782-811`).
  History provenance tags are `typed, voice, shared, clipboard, pasted,
  picture_caption` (`backend/jarvis_chat_log.py:117`); any transcript the
  PC's speech route makes can make a matching message count as "voice" for
  10 minutes (`backend/jarvis_chat_log.py:477-481`, `:661-666`).
- **Repeating jobs:** anything that repeats asks once with a card
  (`CLAUDE.md:180-184`), except the three kinds the owner freed on
  2026-09-26 - plain alarms, reminders and the standby schedule
  (`CLAUDE.md:288-292`; `docs/ARCHITECTURE.md:1547-1550`: "a new kind asks by
  default").
- **Offers** (things Jarvis suggests unasked): at most 3 waiting
  (`backend/jarvis_backoff.py:88`), never in Quiet or Standby, and each kind
  declared with what it asks for; only two kinds of ask exist
  (`MAY_ASK`, `:154-159`) and an offer may never ask for more access, a new
  connection, a key, or to "show or trust more" (`NEVER_ASKS`, `:142-151`).
- **Locked screens** get only the kind of a schedule event, never its words
  (`docs/ARCHITECTURE.md:890-891`); a notification may Deny, never Approve
  (`:340-348`); never approve by voice (`:412-415`).
- **Phone:** no speech-to-text, no model catalogue, no deep config, no bulk
  approve (`CLAUDE.md:103-106`, `:112-120`). Wake-word detection on the
  phone already exists and is not speech-to-text (`docs/ARCHITECTURE.md:1513`,
  openWakeWord "on the phone and the PC alike").
- **`file_read`'s refusal list** already blocks browser profiles, `.ssh`,
  credential stores (`backend/jarvis_agent.py:200-226`).

## 1. One row per idea

Verdicts: **build** (keeps every rule with the guardrails named), **build
later** (keeps the rules only after a named change, a decision, or a
dependency), **don't build** (breaks a rule as written), **no objection**
(no rule at risk; other reviewers decide worth).

| id | verdict | reason (plain words) | guardrails / smallest change that keeps the rules |
|---|---|---|---|
| I01 | build | Owner chose it (`CLAUDE.md:355`); it only makes an error truthful. | None beyond the check itself. |
| I02 | build | Owner chose it (`CLAUDE.md:356`); a second lock behind rule 1. | Test that model install from the phone (`CLAUDE.md:112-115`) still works with it on. |
| I03 | no objection | Numbers only, never words. | Log counts, never prompt text. |
| I04 | no objection | Still goes through the schema check and the gate. | The forced "fill this form" must not force an invented value: the form must allow "I need to ask the owner" (ties to I05), or the retry makes the model guess a recipient/time and the card then shows a guess as if chosen. |
| I05 | build | Owner chose it; test only, on the PC. | Test prompts made up, never the owner's data. |
| I06 | build | Owner chose it (`CLAUDE.md:347`). | The gate and `NEEDS_A_PERSON` apply to a tool however it was loaded; "more tools" never offers a tool the turn's lane may not use (e.g. `send_email` on a non-local model, `docs/ARCHITECTURE.md:440-443`); a "more tools" request made after outside text is itself marked "shaped by outside text". |
| I07 | build | Owner chose it: local servers only, read-only first, a card per server start, every call through the gate (`CLAUDE.md:347-350`). | "Local" = a program on this PC started by Jarvis over stdio. The draft already refuses sampling, elicitation and roots (`docs/designs/mcp-draft-2026-09-23/jarvis_mcp.py:911-913`, `:962`), passes only a safe list of environment variables (`:162`, so no key leaks to a server - rule 3), scans descriptions and lets the owner replace them (`:69-72`, `:179`), and lets annotations only make things stricter (`:449-460`). Keep all of that. Results are outside text, never learned. Home Assistant's MCP server is on another machine and its action tools act with no card - not "local", use `jarvis_home` instead. |
| I08 | no objection | A speed setting. | Measure first (Hardware's call). |
| I09 | no objection | A test on the PC. | The shortlist stays on the PC: a "models you could try" list on the phone would be the catalogue `CLAUDE.md:116-117` forbids. Each download through the existing install card. |
| I10 | build later | Waits for the card (`CLAUDE.md:66-69`). | Switch through the existing model-switch card. |
| I11 | build later | Needs the 12 GB card; one plan, one card, never a loop fits §3. | Refuse every Jarvis window as a target (`docs/ARCHITECTURE.md:140-145`); screenshot to the local model only; a stale stream blocks the card like any other. |
| I12 | no objection | Read-only numbers. | - |
| I13 | no objection | Jarvis never elevated; the owner pastes one line. | One PowerShell line, per `CLAUDE.md` "PowerShell: ONE line". |
| I14 | build | Owner chose it (`CLAUDE.md:345-346`). | OCR text tagged outside text (taints the turn, so note writes ask, `CLAUDE.md:143-147`); never learned (screenshots are already skipped by the learner, `docs/ARCHITECTURE.md:777-780`). |
| I15 | build | Owner chose it; wake-word detection on the phone already exists and is not speech-to-text (`docs/ARCHITECTURE.md:1513`). | Keep "Hey Jarvis" turns under the hands-free setting (`CLAUDE.md:155-163`). |
| I16 | build | Owner chose it. | Same consent card as today's custom voices, and the same refusal of a voice that sounds like the owner's (`docs/ARCHITECTURE.md:1513`, `jarvis_voices.py`); never another real person's voice. |
| I17 | build later | Waits for the second card. | - |
| I18 | build later | Off by default and measured first (per VV). | Contact and device names go only to the PC's own speech model; contact names count as private details about other people (`CLAUDE.md:335-338`), so never to a cloud lane. |
| I19 | build later | An always-listening PC mic is a bigger step than today's wake word. | PC only; on by a card, off at once; no audio kept; a match only notifies ("tell me when" shape, `docs/ARCHITECTURE.md:447-455`); the "not a safety device" line is required by invariant 6, "nothing is claimed that is not true" (`docs/ARCHITECTURE.md:98-100`). |
| I20 | build later | Only if the vision model is weak. | Outside text; local only. |
| I21 | no objection | After the voice check, so its limits hold. | - |
| I22 | no objection | Speech detection is not speech-to-text; the phone rule holds. | TEN's licence has extra conditions (per VV) - Upkeep/Security to read it; rule 5 (non-commercial) does not waive them. |
| I23 | no objection | Only if real numbers show others getting in. | New limits measured before use. |
| I24 | build later | Waits for the card. | Same consent card and owner-voice refusal as I16. |
| I25 | no objection | Stricter only: a flag can only move a turn to "only trust the talk button". | Never the reverse; never described as able to catch a recording (`CLAUDE.md:162-163`). |
| I26 | build later | The owner's call, not decided. | **It must never become approve-by-voice** (`docs/ARCHITECTURE.md:412-415`): passing the three words may raise trust for learning or reading aloud, never answer a card. The words are shown on screen, checked by the PC's speech model (not the phone). Update the "cannot tell a recording" wording only for turns that passed it. |
| I27 | build later | Needs a model that sees; acts on nothing, so no card. | Screenshot to the local model only; never done while a Jarvis card is on screen. |
| I28 | no objection | Wording/speed only, like manner (`CLAUDE.md:255-257`). | - |
| I29 | build later | Waits for the card. | Photos are files: local only (rule 1); refuse turning a real person's face into someone else (per R2-PER). |
| I30 | no objection | Local; nothing leaves. | - |
| I31 | build | Owner chose it; merged (commit `9abdd68` is an ancestor of HEAD, checked with `git merge-base --is-ancestor`). | Re-orders only; never adds, hides or changes a fact. |
| I32 | build | Owner chose it; merged (`c33b5f0`). | Test data made up. |
| I33 | build | Owner chose it; merged (`d2d8831`). | Counts only the owner's own repeats (live-turn checks), no words kept. |
| I34 | build | Owner chose it; merged (`eee9b03`). | Dates only from the owner's own words. |
| I35 | build later | Model-written words added to memory's search index. | Local model only (rule 1); index only, never shown or sent to the model; **"Erase the words" must wipe them** or the owner's "wipes the fact's text for good (and its search entry)" (`CLAUDE.md:151-154`) becomes untrue; a sensitive fact gets no hints (or hints that are sensitive too). |
| I36 | no objection | Re-orders only. | - |
| I37 | build | Owner chose it, cards only (`CLAUDE.md:328`). | **Clash to fix first:** MEM idea 7 says "at most 5 cards a night, under the existing back-off" (`docs/MEMORY-RESEARCH-2026-09-26.md:103`) but the back-off allows at most 3 offers waiting (`backend/jarvis_backoff.py:88`) and applies to the tidy card (`docs/ARCHITECTURE.md:1384`). Either cap at 3, or say plainly that 5 are made and 3 shown. Also its cards ask to change a fact, which is not one of the two declared kinds of ask (`MAY_ASK`, `:154-159`): declare a new kind ("change one named fact, shown in full") - it is not in `NEVER_ASKS`. Never in Quiet/Standby; each card one fact (no "accept all 5"). |
| I38 | build later | The owner decided it waits until I31-I34 are measured; it changes a written rule (`CLAUDE.md:329-330`; `docs/ARCHITECTURE.md:836-838`). | Search only rows tagged `typed` or `voice` (`backend/jarvis_chat_log.py:117`) - never pasted, shared or picture captions, never Jarvis's answers; nothing saved from it; temporary chats never there (`docs/ARCHITECTURE.md:860-862`); local model only; a turn using it counts as memory for read-aloud and search-asks rules. |
| I39 | build | Names only, owner-chosen folders. | Local model only (file names are file data, rule 1); outside text; reuse `file_read`'s refusal list (`backend/jarvis_agent.py:200-226`) so `.ssh` etc. never appear; never Everything's network server (rule 2 spirit - a listener). |
| I40 | build | Owner chose it (`CLAUDE.md:353`). | Install only the document parts: MarkItDown's audio part sends sound to Google and its YouTube part fetches from YouTube (per R3-KNOW; not checked) - both would break rule 1. Same refusal list as `file_read`; outside text; never learned. |
| I41 | build later | Needs its folders chosen, and it is the search half of I40. | Folders chosen **on the PC** (deep config stays off the phone, `CLAUDE.md:103-104`); its own file, never memory; the refusal list plus `.env`, password files; local model only. |
| I42 | build | Makes answers more truthful (invariant 6). | Sources from what tools returned, never from the model's claim. |
| I43 | no objection | A note write from the owner's words; a pasted link already makes the note write ask (`CLAUDE.md:143-147`). | Jarvis never fetches the page. |
| I44 | no objection | Fixes go through the existing wiki card. | Wiki reads are outside text. |
| I45 | build later | Model-written code running is the risky part; the report's lock-down is the right one. | Read-only, one owner-named file, no network/extension/file access, time and row caps; query and result shown; the named file must pass the `file_read` refusal list. |
| I46 | build later | Speech-to-text on the PC is allowed; the phone rule holds if the phone only shares the file. | **A file transcript must never count as the owner's live voice.** The PC's speech route marks transcripts so a matching message is tagged `voice` (`backend/jarvis_chat_log.py:477-481`); file transcription must not call `note_transcript`, and its text goes in tagged `shared` (outside text, never learned, `CLAUDE.md:122-127`). Never a live meeting. |
| I47 | build later | Bookmarks live inside the browser profile folder that `file_read` refuses on purpose (`backend/jarvis_agent.py:211-214`). | A separate reader that opens only the one `Bookmarks` file by exact name, read-only, never `Cookies`/`Login Data`; `file_read`'s refusal list stays as it is; titles are outside text; local model. |
| I48 | build later | Very private; same profile-folder problem as I47. | Same exact-file reader on a copy; off by default, on by a card, off at once (notifications pattern, `CLAUDE.md:358-365`); banking and health sites dropped before the model sees anything; local model only; nothing kept. |
| I49 | build later | A new way out of the PC. | A row in the egress table and "What Jarvis can reach" (`docs/ARCHITECTURE.md:419-431`, `:1570-1573`); one card per feed (repeat = card, `CLAUDE.md:180-181`); feeds typed on the PC; headlines are outside text. |
| I50 | no objection | Desktop only; the graph stays off the phone (`CLAUDE.md:103`). | - |
| I51 | no objection | A fixed read list, never `eval`. | - |
| I52 | no objection | Detect-and-say first. | The later dry-run half waits for I07. |
| I53 | build | Owner chose it (`CLAUDE.md:354`); the "when does it ask" question is still open. | A saved draft **leaves the PC** (it is uploaded to Google's mail server), so it needs its own line in §4's egress table, written by the local model only (as `send_email`, `docs/ARCHITECTURE.md:440-443`). My view on the open question: the recommended "card only after outside text" keeps the rules, **plus** always a card when a saved sensitive fact is in the draft - the note-write precedent is about files on this PC, not text uploaded to Google. |
| I54 | build later | Contact details stay sensitive everywhere (`CLAUDE.md:335-338`). | Never learned as facts; a looked-up address is never read aloud (the sensitive-answer rule, `CLAUDE.md:136-139`) and makes a web search ask; the `.vcf` path set on the PC. |
| I55 | build later | Only if a non-Google calendar exists. | One card per event; a new write line in §4's egress table. |
| I56 | no objection | OCR text is outside text, so the vault write already asks (`CLAUDE.md:143-147`). | Local OCR only. |
| I57 | build later | Review reminders **repeat**, and only three repeating kinds are card-free (`CLAUDE.md:288-292`). | Either one card at setup (today's rule) or ask the owner to add "quiz reviews the owner set up" to the card-free list. Questions drafted from a note are outside text: temporary chat, never learned. |
| I58 | no objection | Text to translate is pasted, so outside text. | - |
| I59 | no objection | Speech-to-text stays on the PC. | Temporary chat, so practice sentences are never learned. |
| I60 | no objection | Never edits by itself. | Any later edit: a full diff on one card. |
| I61 | build later | Allowed by the written meaning of "no approve-all" (one bounded set shown in full, `docs/ARCHITECTURE.md:102-119`) - but it is a new kind of card, so the owner's Q1 first. | Four conditions, all needed: (1) every step shown exactly as its own card would show it; (2) **a step whose values come from an earlier step's output is asked again** (per R3-ROUT §1) - it was not "shown in full" at the yes; (3) a risky step is never covered, and waits on a stale stream; (4) the plan grants nothing for later and counts once toward the five-card cap. |
| I62 | build later | A saved routine is fine if it carries no approval with it. | **Two gaps in R3-ROUT's text.** "If every step would run without a card when asked on its own ... the routine needs none" (`docs/CUTTING-EDGE-2026-09-26-round3-routines.md:180-182`): the lights setting needs every device named in the owner's **newest message** (`backend/jarvis_agent.py:1192`), and "movie night" names none - so a routine's lights need a card unless the owner decides otherwise. And a routine **on a timetable** must always raise its card, even when every step would be card-free on request - otherwise it acts with nobody there. |
| I63 | build | Owner's words only, no model. | The weekly check-in repeats: a card once at setup under today's rule, or the owner adds it to the card-free kinds (`CLAUDE.md:288-292`; `docs/ARCHITECTURE.md:1550`). |
| I64 | build later | Drafting steps is fine; accepting runs nothing. | Re-planning offered only through the back-off, as a declared kind; local model only (goals are the owner's private plans). |
| I65 | build later | Undoing is acting. | Each undo through the gate; "Undo this run" may be one card listing every reversal in full (allowed, `docs/ARCHITECTURE.md:106-110`); blocked on a stale stream; never claims "can be undone" for a sent email. Check the owner's existing `jarvis_undo` first (per fit.md; not checked). |
| I66 | no objection | Same one card, same end date, a match only notifies. | File names are outside text; watched folder chosen on the PC. |
| I67 | build later | A new way out of the PC, on a schedule. | Egress row; one card showing the exact address; the alert's words built from the owner's own plus a number, never page text (`docs/ARCHITECTURE.md:452-454`). |
| I68 | build | Owner chose it; same egress row and one card as today. | IMAP password stays in Credential Manager (rule 3). |
| I69 | no objection | Same match, same card. | - |
| I70 | build later | Rule 3 allows the key; a new source. | Read-only token, in Credential Manager, only to `api.github.com`; set on the PC only (no key route on the phone, `docs/JARVIS-API.md:4241`); check the owner's existing `jarvis_watch` first (per fit.md). |
| I71 | build later | Standby unloads every model (`docs/ARCHITECTURE.md:1333-1337`) and "starts nothing". | Only the recommended Q2 answer keeps standby honest: night jobs only before standby starts. Anything that acts waits for a morning card (stale stream blocks it as usual); searches approved with their exact words when queued. |
| I72 | build later | Enumerated searches on one card are allowed (`docs/ARCHITECTURE.md:107-109`). | Whole pages = a new egress row and a card listing the exact addresses; never keeps searching by itself. |
| I73 | build | Owner chose the safe version (`CLAUDE.md:358-365`). | Reconcile with CAP #17 (below): match "tell me when" **on the phone** and send only app + sender; send message text to the PC only when the owner asks. Hide one-time codes **on the phone** before anything leaves it. Deliver it as tool output (outside text), never as a user-role message, so it can never be learned. Local model only; never SMS. |
| I74 | build later | A model-written page about the owner's week, **from chat history**. | It uses history as a source, which is the rule change the owner deferred with I38 (`CLAUDE.md:329-330`) - decide together. Saved after a card; never into memory. |
| I75 | build | Owner chose it (`CLAUDE.md:343`). | One read-only service; forecast is outside text. |
| I76 | no objection | Read-only; outside text. | - |
| I77 | build later | The list is fine; the MCP route is not. | Read HA's exposed list over Jarvis's own REST/WebSocket client; do not use HA's MCP endpoint (another machine, action tools with no card). |
| I78 | build later | A room is a set of devices. | A room or floor **always gets a card listing every device**, at most ten, never cut (`docs/ARCHITECTURE.md:115`). The other Q1 option ("treat a room like named lights") would widen the owner's lights setting beyond "every device is named in the owner's newest message" (`backend/jarvis_agent.py:1192`) - that needs a new owner decision, not a design choice. |
| I79 | no objection | Only ever makes Jarvis quieter or narrower. | Card to turn on. |
| I80 | no objection | Adds a line to the card (stricter). | - |
| I81 | build | Stricter. | Note it may block I88 (see below). |
| I82 | no objection | Labels only. | - |
| I83 | build later | A camera picture is private. | Its own card; never to disk; local model only, only if asked; never face recognition. |
| I84 | no objection | Numbers. | - |
| I85 | build later | An offer triggered by arrival, not by the owner's words. | Never under the lights setting (no device named by the owner); always a full card; declared as a new offer kind; never in Quiet/Standby; at most one. |
| I86 | no objection | Read-only; outside text. | Car locks and covers keep their own card. |
| I87 | build later | "One card turns on adds without a card" is a new standing setting. | New standing settings have each been owner decisions (`CLAUDE.md:293-296`, `:300-305`): owner's call; never after outside text; only items from the owner's own words. |
| I88 | don't build (as written) | A home automation written by Jarvis acts every day with no card - a standing grant for future actions (`docs/ARCHITECTURE.md:104`). R3-ROUT itself says HA automations are "the place for" things that run by themselves (`...round3-routines.md:186-187`), i.e. made by the owner. | Smallest change: Jarvis notices the pattern and hands the owner the automation text to add in HA themselves; Jarvis holds no write access. (Also: writing automations likely needs an admin HA token, which I81 removes - per my knowledge of HA, not checked.) |
| I89 | build later | Two rule points. | (1) Away from home the report's path needs a Home Assistant token **on the phone** - the first key held by the phone; rule 3 allows it, but every key so far is PC-only (`docs/JARVIS-API.md:4241`). Smaller: at home the phone sends the wake packet itself (no key); away, open HA's own app. (2) With the PC off, the event stream is necessarily stale; rule 4 blocks acting on a stale stream. Waking approves nothing, so write it down beside "stopping is never gated" (`docs/ARCHITECTURE.md:218-227`) as an owner-confirmed exception. |
| I90 | build later | Not verified to work without admin. | Jarvis never elevated; if admin is needed, one pasted line by the owner (as I13). |
| I91 | build later | "Without a card" is a new standing setting (the owner's Q1). | Off by default, on by a card, off at once, never after outside text, only play/pause/next - the lights pattern (`backend/jarvis_agent.py:1180-1196`). |
| I92 | build later | Listing reaches Microsoft's servers (new egress row); updating is acting. | One card plus Windows Hello **per package**; never "update all" (bulk, `CLAUDE.md:104-105`); no lock, no risky approval (`CLAUDE.md:241-243`). |
| I93 | build | Owner chose it (`CLAUDE.md:344-345`); the owner's tap is the approval. | The event button must say plainly that the phone's calendar may copy it to Google (CAP #2 calls it "Local? Yes" - see section 3); warn about two alarms; the late-alarm rule (`CLAUDE.md:318-321`) stays on Jarvis's own alarms. |
| I94 | no objection | The owner picks the person and presses Send. | Never sends; never reads SMS (`CLAUDE.md:365`). |
| I95 | build | Test only, on the PC; the attack texts are already in the repo (`backend/agentdojo_injections.json`). | - |
| I96 | build later | A backup is a copy of memory and history. | (1) **"Erase the words" cannot reach an old backup**, but the owner was told it wipes the text "for good" (`CLAUDE.md:151-154`): the Erase confirm must say old backups still hold it until replaced, and backups must rotate. (2) Recommended Q1 (this PC or a USB drive only) is the only answer that keeps rule 1's "sends none of it anywhere" simple. (3) Restore: one card plus Windows Hello. |
| I97 | no objection | Warns, never fixes. | - |
| I98 | build | Restarting a crashed backend decides nothing. | After a restart nothing resumes by itself (Resume is a card, `docs/ARCHITECTURE.md:223-224`); waiting cards are not approved; a pressed "stop everything" is not undone. |
| I99 | no objection | Stack frames, not values. | Scrub the Rust panic text of any token or key before it is written. |
| I100 | don't build | A crash dump is a copy of memory; "even a mini dump can hold the token" (per R2-TRU). Writing it to disk in plain text breaks rule 3 ("kept out of anything the app writes to disk in plain text", `CLAUDE.md:97-98`) and "never log the token" (`CLAUDE.md:106`). | If ever needed: a one-off capture the owner starts by hand, deleted after, never kept on by the app. |
| I101 | build later | Only after backups exist (per R2-TRU). | - |
| I102 | build | Owner chose it (`CLAUDE.md:169-172`). | One PC card with Windows Hello before any key is handed over; one-time secret with expiry; typed backup code only on the owner's own networks; each device's token removable. |
| I103 | build | Owner chose it (`CLAUDE.md:238-240`). | No lock, no risky approval (`CLAUDE.md:241-243`). |
| I104 | no objection | Stricter only. | - |
| I105 | build later | Only if I95 shows fewer attacker cards. | - |
| I106 | build later | Label only. | Local model. |
| I107 | build later | Measure with I95. | - |
| I108 | no objection | A warning, never a block and never a pass. | Licences to check (Security). |
| I109 | no objection | Counts only; never changes a tier. | Never used to suggest loosening ("you always approve this" offers are out; 00-ideas "not for Jarvis"). |
| I110 | build | Stricter only, both apps. | - |
| I111 | no objection | - | - |
| I112 | no objection | Local Tailscale query. | Tailnet Lock is the owner's own setting. |
| I113 | build | Stricter. | **The owner's question was answered in code without asking**: commit `e372eb7` (not in HEAD, checked) keeps alarms off the watch too. Tell the owner and let them choose (`CLAUDE.md` "Tell the owner when something is wrong"). The widget half: `widget_approval_info.xml:18` is `home_screen` only; whether Android 16 still offers it on the lock screen is not verified. |
| I114 | no objection | - | - |
| I115 | no objection | The password still reaches only the local model. | - |
| I116 | no objection | Fills the box, never sends. | - |
| I117 | no objection | "Open the card", never Approve. | Titles from `notice` only (`docs/ARCHITECTURE.md:350-355`). |
| I118 | no objection | The owner's own words into the daily note. | - |
| I119 | build later | A "Fix" button can change a setting. | A Fix never skips the card that setting normally raises. |
| I120 | no objection | Tagged "shared", so outside text and never learned. | - |
| I121 | no objection | Phone to PC over the private link only. | Tagged "shared"; local model only. |
| I122 | no objection | Makes Jarvis quieter. | - |
| I123 | no objection | Phone-side quiet. | - |
| I124 | build | Both apps; no approval. | **A lock-screen Live Update must not show the timer's label**: a locked screen gets only the kind (`docs/ARCHITECTURE.md:890-891`). Show "Timer - 3:40" locked, the label only unlocked; "+5" and Stop are fine (they approve nothing). |
| I125 | no objection | Still meets App lock. | - |
| I126 | no objection | Counts only; off the lock screen. | - |
| I127 | no objection | - | - |
| I128 | build later | Opens "reply-in-notification". | Never an Approve from a notification (`docs/ARCHITECTURE.md:340-348`). |
| I129 | no objection | Wording; rules block stays first (`docs/ARCHITECTURE.md:940-946`). | - |
| I130 | no objection | - | - |
| I131 | no objection | "What can you reach" from code, not the model (`docs/ARCHITECTURE.md:465-471`). | - |
| I132 | no objection | Makes answers truer. | - |
| I133 | no objection | Test only, on the PC. | Made-up data. |
| I134 | no objection | Warns only. | - |
| I135 | no objection | - | - |
| I136 | no objection | Manner is wording only (`CLAUDE.md:255-257`). | - |
| I137 | no objection | Never on cards or errors. | - |
| I138 | no objection | Wording only. | Each dial one fixed sentence; placed after the rules; never sent to a cloud lane (`docs/ARCHITECTURE.md:944-946`). |
| I139 | no objection | - | - |
| I140 | build later | A spoken or typed "from now on" changes a setting with no card. | Only the owner's live words (the auto-learn checks, `docs/ARCHITECTURE.md:797-803`); under "Only trust the talk button" a "Hey Jarvis" turn cannot change it without a card (`CLAUDE.md:155-163`); wording dials only, never a tier. |
| I141 | build later | An offer. | Declare it as an offer kind; it asks only to change a wording dial (not in `NEVER_ASKS`). |
| I142 | no objection | Ordinary facts from the owner's words, Forget and Erase as usual. | Sensitive rules still apply to them. |
| I143 | build later | The one place owner text becomes an instruction. | Typed in Settings only - never from chat, voice, paste or share; capped; placed after the rules with "every rule still applies"; tiers stay in code, so a note cannot loosen anything, but refuse notes about approvals, sending or tools so the model never *says* it will skip a card. |
| I144 | no objection | - | - |
| I145 | no objection | Owner's call. | Confirm no old persona mode changes a tier or what is remembered (not checked - `jarvis_persona.py` is not in this repo, per R4-CHAR). |
| I146 | no objection | Temporary chat, so never learned. | - |
| I147 | no objection | - | - |
| I148 | no objection | Never looks like "approved". | - |
| I149 | no objection | - | - |
| I150 | no objection | Guidance. | - |
| I151 | build | A fixed floor, no tools that turn, contacts no one. | Word it truthfully: it "keeps no separate record", not "logs nothing" - chat history keeps every turn by default, encrypted (`CLAUDE.md:132-134`), unless it is a temporary chat. Never offered to a cloud lane (I152). |
| I152 | no objection | Tightens rule 1; latent today (no cloud lane, `backend/test_router_private_terms.py:14-15`). Checked: no distress words in `_PRIVATE_TERMS` (`backend/rebuilt/jarvis_router.py:70`). | - |
| I153 | no objection | - | - |
| I154 | build | Stricter on the owner-only-words rule. | - |
| I155 | build later | These kits default to a cloud judge (per R4-WELL). | Local judge only; made-up conversations only. |

**Counts:** build 32, build later 50, don't build 2 (I88, I100), no objection 71 (total
155).

## 2. Objections for the other reviewers

1. **Fit / Devil's advocate - the plan card (I61).** I say it is allowed by
   the written meaning of "no approve-all" (`docs/ARCHITECTURE.md:102-119`),
   with four conditions. Someone may say `CLAUDE.md:104-105` ("never ...
   approves in bulk") forbids it outright. Answer me with the case: which
   step of a plan is approved without being shown in full? If the answer is
   "a step filled in from an earlier step's output", that is my condition 2.
2. **Overwhelm - more repeating cards.** I say goal check-ins (I63), quiz
   reviews (I57), feeds (I49), page watches (I67) and night jobs (I71) each
   need a card at setup under today's rule, because only three repeating
   kinds are card-free (`CLAUDE.md:288-292`). Overwhelm will want fewer
   cards. That is fine - but it is an owner decision (extend the card-free
   list to "things only the owner's own words can set, that only notify"),
   not something a design may assume.
3. **Fit - the overnight tidy's numbers (I37).** 5 cards a night vs 3 offers
   waiting. Fit may prefer to raise `MAX_WAITING`. I object: the back-off is
   the nag guard for every offer; raise it only for the tidy, and say so.
4. **Security - "local" for MCP (I07).** I read the owner's "local servers
   only" as "a program on this PC started by Jarvis". Security may accept
   Logseq's HTTP server on 127.0.0.1 with a bearer token as local. I accept
   that only if the token is in Credential Manager, sent to that one server
   (rule 3), and the server is one the owner already runs - Jarvis must not
   open a listener of its own.
5. **Hardware / Upkeep - I89 "wake my PC".** The cheap route holds a Home
   Assistant token on the phone. Rule 3 allows it, but it would be the first
   key on the phone. I prefer "open HA's own app" away from home. And the
   owner must confirm that waking the PC is an exception to "no acting on a
   stale stream".
6. **Devil's advocate - I88 as "don't build".** Someone may say the owner
   approves the automation once, so it is one bounded decision. My answer: it
   is bounded in *what*, but it runs forever with no one present, which is
   what "future, unnamed actions" means in practice, and R3-ROUT itself puts
   self-running automations on the owner's side of HA.
7. **Fit / Security - I53 drafts.** The recommended "card only after outside
   text" treats a draft like a note. A note stays on this PC; a draft is
   uploaded to Google. I add: always a card when a sensitive saved fact is in
   it, and a new egress line. Security may want a card every time; the
   owner already has that question in front of them.
8. **Overwhelm - I96 Erase wording.** The Erase confirm gets longer ("old
   backups still hold it"). Overwhelm may want it shorter. The sentence is
   needed: invariant 6 (`docs/ARCHITECTURE.md:98-100`).
9. **Security - I100 as "don't build".** Security may want dumps for
   diagnosing native crashes. I only object to the app keeping them on by
   default; a one-off, owner-started, deleted-after capture is fine.
10. **Fit - I47/I48 need a new reader.** `file_read` refuses browser
    profiles on purpose (`backend/jarvis_agent.py:211-214`). Do not loosen
    that list; add an exact-file reader.
11. **Upkeep - I46 provenance.** Reusing the speech route for file
    transcripts is the obvious shortcut and the wrong one; it would let a
    transcript be tagged as the owner's live voice
    (`backend/jarvis_chat_log.py:477-481`). A test should prove a file
    transcript is never tagged `voice`.

## 3. Wrong or out of date in the reports (with evidence)

1. **00-ideas note 1 is out of date:** "Memory ideas 1-4 are already built in
   another agent's worktree, not merged". `git merge-base --is-ancestor`
   says `9abdd68`, `c33b5f0`, `d2d8831`, `eee9b03` and `a1b133e` are all
   ancestors of HEAD (`e656093`). `e372eb7` (notifications local-only) is
   **not** in HEAD. (fit.md says the same.)
2. **CAP #2 rates "Also on my phone" as rule risk "None" and "Local? Yes,
   the phone's own apps"** (`docs/CUTTING-EDGE-2026-09-26-capabilities.md:53`,
   `:98-99`), but its own row says it "writes to Google Calendar without
   Google sign-in" (`:53`). An event handed to a Google-synced phone
   calendar reaches Google. The owner's tap makes it the owner's choice, but
   the button must say so.
3. **CAP #17's "only the sender name and app are sent, never the message
   text"** (`...capabilities.md:261-262`) was written before the owner's
   decision, which allows showing or summarising the text when asked
   (`CLAUDE.md:364`). Both can hold: match on the phone with sender and app
   only; send text only when asked.
4. **R3-ROUT #4: "If every step would run without a card when asked on its
   own (a timer; lights with 'Lights, plugs and fans without a card' on),
   the routine needs none"** (`...round3-routines.md:180-182`). Wrong for
   lights: that setting requires every device to be named in the owner's
   newest message (`backend/jarvis_agent.py:1192`), and a routine's phrase
   names none.
5. **MEM idea 7: "At most 5 cards a night, under the existing back-off"**
   (`docs/MEMORY-RESEARCH-2026-09-26.md:103`). The back-off allows 3 waiting
   (`backend/jarvis_backoff.py:88`), and the tidy's cards ask for something
   not in `MAY_ASK` (`:154-159`).
6. **R2-EXP #9 (Live Update on the lock screen, "Tea - 3:40 left")** does
   not mention that a locked screen gets only the kind of a schedule event
   (`docs/ARCHITECTURE.md:890-891`). Label hidden when locked.
7. **R4-WELL #1's "logs nothing"** is not true while chat history is on by
   default (`CLAUDE.md:132-134`): the turn is kept, encrypted. Say "keeps no
   separate record".
8. **R4-WELL #2 does not say the risk is latent:** no cloud lane is
   configured yet (`backend/test_router_private_terms.py:14-15`). The
   finding itself is right: `_PRIVATE_TERMS`
   (`backend/rebuilt/jarvis_router.py:70`) has no distress words (grep for
   `suicid`, `self-harm`, `depress` finds none).
9. **00-ideas "Not for Jarvis": "Typing API keys on the phone ... the Rules
   reviewer should confirm this still stands."** It still stands in
   practice. Rule 3's 2026-09-17 change allows keys in the app, but no owner
   decision moved key entry to the phone, and the code has "no field and no
   route for a key" (`docs/JARVIS-API.md:4241`); keys live in Credential
   Manager on the PC (`:4349-4355`). I89 would be the first exception and
   needs the owner's word.
10. **00-ideas note 2 / I113:** `e372eb7` answers an owner question
    ("let alarms reach the watch?") in code without asking. Stricter, so no
    rule is broken, but the owner should be told and asked.
