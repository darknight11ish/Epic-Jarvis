# Feasibility audit: the Security reviewer (2026-09-26)

Read-only. Nothing in the repo was changed. Every claim about Jarvis's code
below was checked in the file named (path:line, at commit `1381e6a`); where I
did not check, it says "not checked". Research-report claims I did not
re-check are marked "(report's claim)".

## A few words first

- **Prompt injection** = text Jarvis reads (an email, a web page, a file, a
  song title) that is written to give the AI orders. Jarvis's wall against
  it is the approval card: the AI can *propose*, only the owner's yes *acts*.
- **Outside text / taint** = Jarvis's label for anything not typed or said by
  the owner. A turn that read outside text asks before writing notes,
  searching the web with private words, or switching lights without a card.
- **Egress** = a way out of the PC (ARCHITECTURE section 4 lists every one).
- **Supply chain** = everything downloaded to make a feature work (models,
  libraries, programs): who publishes it, its licence, whether the version is
  pinned and checked, whether it "phones home" (sends usage data).
- **SSRF** = tricking the PC into fetching an address on the owner's own home
  network (router, Home Assistant) on an attacker's behalf.
- **Fails closed** = when something breaks, it does LESS (refuses, asks), not
  more.

## Five gaps in today's code that several new ideas would widen

These come first because the per-idea guardrails below lean on them.

**G1. After a backend restart, a conversation that read an email is no
longer "tainted".** The per-conversation taint lives only in memory:
`self._taint` (`backend/jarvis_chat_log.py:298`), set at `:536-538`, read by
`conversation_tainted` (`:586-589`); the docstring says "a restart forgets
them all" (`:520-522`). The tool loop asks it through
`_conversation_tainted` (`backend/jarvis_agent.py:2459-2468`), which also
returns `False` on any error. For automatic learning this fails closed (an
unremembered turn becomes a card), but for the tool loop it fails OPEN: turn 1
reads a planted email, the backend restarts, turn 2 in the same chat (whose
earlier answer may repeat the email's words) is treated as clean - note
writes, web searches with saved facts, and "lights without a card" stop
asking. Today restarts are rare and by hand (tray only,
`jarvis-desktop/src-tauri/src/sidecar.rs:396`). **I98 (watchdog), I111
(staged update switch) and I71 (night jobs that carry on after a restart)
make restarts routine.** Fix before them: seed the taint from the history
database's per-turn `tainted` column (it is written, `jarvis_chat_log.py:777`)
when history is on, and when it is off or unreadable treat an unknown
conversation that has earlier assistant turns as tainted.

**G2. `file_read` uses a refusal list, runs with no card, and the list has
holes.** Commit `1ce1dac` added `_PROTECTED_DIRS/_NAMES/_SUFFIXES`
(`backend/jarvis_agent.py:201-248`). The shipped settings copy puts file reads
at `read_files_readonly = "auto"` (`backend/rebuilt/jarvis-framework.toml:95`;
the owner's own file was not checked). Not on the list, checked:
`~/.android/adbkey` - the private key that lets a computer drive the owner's
phone over adb, which Jarvis itself uses (`backend/jarvis_android_control.py:13-43`);
Android/Java key stores (`.jks`, `.keystore`); Thunderbird profiles (mail
plus saved passwords); Chromium, Chrome Beta/Canary profiles; Discord and
Signal desktop data; `.cargo/credentials*`; `.git/config` files with a token
in the remote address. Round 3 knowledge recommended an **allowlist**
(`docs/CUTTING-EDGE-2026-09-26-round3-knowledge.md`, "Found while checking");
the fix chose a denylist, which is never complete. Two things soften it: the
turn is marked as having read outside text, and `jarvis_scrub.find_secret`
notices PEM private keys in what was read (`jarvis_agent.py:2600-2612`,
`jarvis_scrub.py:240`). **I39, I40, I41, I45, I46, I47, I48, I56, I120, I121
all open or list files.** They must share ONE list, and once I39/I41 give
the owner a folder allowlist, `file_read` should use it too (denylist kept
as a second layer).

**G3. Service passwords and tokens sit in plain text in the registry.**
`JARVIS_IMAP_PASSWORD`, `JARVIS_HOME_TOKEN`, `JARVIS_GITHUB_TOKEN`,
`JARVIS_CALENDAR_ICS_SECRET_URL` and others are Windows user environment
variables, which "sits in plain text in the registry, and every program you
start inherits it" (`backend/README.md:7717-7724`, `:8813-8819`). Only the
pairing token, the chat-history key and the search keys are in Credential
Manager (`jarvis_token_store.py`, `jarvis_search.py:65`). Rule 3 says keys are
"kept out of anything the app writes to disk in plain text" - the owner
writes these, not the app, so it is a grey area, but **every new secret
(I52 Logseq token, I68, I70 GitHub token, I81 HA token, I102 device keys)
must go into Credential Manager**, and moving the existing ones should come
before adding more.

**G4. The MCP draft's own "not verified" list is real.** `docs/designs/mcp-draft-2026-09-23/DESIGN.md`:
the bridge does not set the gate's timed taint flag (section "Not verified",
item 5), was never run on Windows (item 1), and its tier floor can drop below
"ask" for tools the owner lists in `below_ask_ok` (lines 79-95), while its
own summary says "every tool call raises its own approval card" (lines
22-24). A running MCP server is unsandboxed code under the owner's account
(lines 33-37).

**G5. Choosing or installing a cloud model is still not refused at the
switch/install routes** (`docs/ARCHITECTURE.md` section 4, last paragraph;
`backend/README.md:7725-7729`). I02 (`OLLAMA_NO_CLOUD=1`) is the fix at
Ollama's end; I09/I10/I17/I29 add more model downloads and should refuse
`-cloud`/`:cloud` names in Jarvis's own code too.

## 1. One row per idea

Verdicts: **build**, **build later**, **don't build**, **no objection** (no
security issue beyond the standing rules; the other reviewers decide).
"Owner chose" ideas are reviewed for HOW, not whether.

| id | verdict | reason (plain words) | guardrails |
|---|---|---|---|
| I01 | no objection | Asks the local Ollama a question; nothing new leaves the PC. | Treat "cannot tell" as "cannot use tools" (fail closed). |
| I02 | build | A second lock behind rule 1 for every program on the PC, and the fix at Ollama's end for G5. | Set it in the second Ollama's own environment (`jarvis_second_card.py:772-787`) and in the one-line setup for the main one; the preflight checks the setting, never by sending a real chat to a cloud name (without the lock that would reach ollama.com). Test that `ollama pull` still works (report's own open question). |
| I03 | no objection | Numbers only in the timings log. | Numbers only, never prompt text. |
| I04 | no objection | The retry still ends at the same gate and card. | Only for the tool the model already chose; never offer a new tool in the retry; counts toward `CARDS_PER_TURN`. |
| I05 | build | Tests only, on the PC, no egress. Also the measuring stick for I06/I07. | Offline; test data never includes real mail or memory. |
| I06 | build | Offering fewer tools is not less safe: all tools are offered today. | `more_tools` returns only tools in `[tools].enabled` and allowed on this lane; its answer is Jarvis's own text (should not by itself count as outside text); gate and tiers unchanged. |
| I07 | build (owner chose) | The biggest new attack surface in the list: a plug-in server is someone else's program running as the owner, and its answers are outside text. Safe enough only in the narrow shape below. | Version 1 = stdio servers started by Jarvis on this PC only; no HTTP (so not HA's or Logseq's MCP yet - see objections). Installed once into a fixed folder, exact version and file hash pinned, never `npx`/`uvx` at start. Start card per server; every call through the gate with "ask" as the floor until I95 shows otherwise (`below_ask_ok` empty in the shipped config). Results through the agent's normal `took_in` path (marks the turn) AND the bridge sets the conversation taint (G4). Env allowlist, never `HUD_TOKEN` or service passwords. First server `mcp-server-git`: read tools only, and only a version at or after the fixes for its path-traversal and argument-injection flaws (CVE-2025-68143, -68144, -68145, and CVE-2026-27735; fixed from 2025.9.25 / 2025.12.18 per public advisories, not checked here). Prefer calling voidtools `es.exe` directly (I39) over a one-person third-party "Everything" MCP wrapper. Run the draft's tests on Windows first. |
| I08 | no objection | A Modelfile line; no new code path. | None. |
| I09 | build later | Test downloads only. Model files are parsed by native code, so a crafted file is a real risk. | Official `library/` models only (Ollama checks each download's sha256), never user namespaces or loose GGUF files from forums; refuse cloud names (G5). |
| I10 | build later | Same as I09; waits for the card. | Same as I09. |
| I11 | build later | Clicking by picture position is riskier than by name; the screenshot holds private text. | Local vision model only; the screen text is outside text; the card shows the cropped target and says "clicking by position"; `run()` re-checks the spot; never on Jarvis's own windows (existing rule, ARCHITECTURE section 2). |
| I12 | no objection | Local readings from `nvidia-smi`. | None. |
| I13 | build later | Jarvis stays unelevated, but the proposed logon task runs as administrator every day. | The pasted line must create a task whose action is `nvidia-smi.exe` by its full system path with literal numbers - never a script or any file in a folder the owner's account can write (that would let any program run as admin at the next logon). Jarvis never creates or edits the task itself. |
| I14 | build (owner chose) | OCR is local; the risk is the design: the report puts the screenshot's text INTO the owner's typed message (voice-vision section 1), and a message tagged "typed" is the owner's own words to the tool loop (`OWN_WORDS`, `jarvis_agent.py:2385`). That would fail open. | The backend, not the app, marks the turn: the OCR text goes in as its own not-own-words part (like `picture_caption`/`shared`, `jarvis_agent.py:2386-2398`) and sets the conversation taint. RapidOCR pinned with hashes (Apache-2.0, ONNX files are data not code); or Windows' built-in OCR (no download). Never learned; never to a cloud lane. |
| I15 | build (owner chose) | The model file is data (ONNX), but training pulls a large tool chain. | Train in a separate Python environment, never the backend's; pin livekit-wakeword by commit (it is v0.2); record the output file's hash in the repo; ship the same file to both apps and check the hash in CI. Re-measure the owner check with it (report's own point). |
| I16 | build (owner chose) | Runs through sherpa-onnx, already trusted; the voice-copy weights sit behind a consent sign-up. | Download once by hand; do not keep a Hugging Face token anywhere Jarvis reads; hash-pin the files; the existing `custom_voice` card's consent wording stays. |
| I17 | build later | New model on the second card. | Same download rules as I09. |
| I18 | build later | Private names go only to the local speech model; the risk is wrong words (the known bug), which the voice check then trusts as "said". | Off by default, measured first; hints never include text from email or web. |
| I19 | build later | A new always-listening microphone. Anyone can play a smoke-alarm sound at it, but a match only notifies. | Card to turn on, off at once; labels only, no audio kept; never acts; "not a safety device"; prefer YAMNet (Apache-2.0) over CED (weights licence not checked). |
| I20 | build later | Photo-of-a-letter text is outside text. | Mark as outside text; official model sources only. |
| I21 | no objection | Placed after the voice check, so it cannot change the voice print's numbers. | Keep it after the check. |
| I22 | no objection | Only decides when to record; not speech-to-text. | TEN VAD's extra licence conditions written down. |
| I23 | build later | A voice-ID model changes the security bar of the voice check. | Its own measured limits; an unmeasured model means the strict setting. |
| I24 | build later | PyTorch voice models load pickled weight files, which can run code. | safetensors only, or `weights_only` loading; never `trust_remote_code`; separate environment. |
| I25 | build later | Only ever makes things stricter; no detector is reliable (report). | Never used to loosen anything. |
| I26 | build later | The only real defence against a replayed recording; useful if hands-free trust is ever widened. | Words shown on screen, never spoken; checked on the PC. |
| I27 | build later | Acts on nothing, but screenshots are private. | Local model only; never stored. |
| I28 | no objection | A setting. | None. |
| I29 | build later | Local; heavy dependency; photos are the owner's. | stable-diffusion.cpp pinned build; safetensors/GGUF from the publisher only; refuse face swaps of real people (report). |
| I30 | don't build | A whole new PyTorch stack of downloads for a "mostly fun" feature: more supply-chain risk than it is worth. | - |
| I31 | no objection | In progress; re-orders only, never adds or hides. | Re-ranker model hash-pinned; falls back to today's order (report). |
| I32 | no objection | Tests. | None. |
| I33 | no objection | Keeps dates and a tag, no words. | None. |
| I34 | no objection | Stricter about dates. | None. |
| I35 | build later | Hidden model-written words in the index; nothing leaves. | Erase and Forget wipe them (report); hints built only from saved facts, never outside text. |
| I36 | no objection | Re-orders only. | None. |
| I37 | build (owner chose) | Reads memory on the PC at night and only raises cards. | At most 5 cards; never changes memory; cards raised through the normal gate so App lock and the stale-stream rule apply. |
| I38 | build later (owner decided) | Past chats contain pasted and shared text too. | Search only turns tagged `typed`/`voice`; results count as outside text; honours history off. |
| I39 | build | File NAMES are private and can carry planted text, but stay local. | Call `es.exe` by full path with `-path` limited to owner-chosen folders; filter every result through the same protected-path rule as `file_read` (G2); preflight warns if Everything's HTTP or ETP server is on; results are outside text; never the "Lite" install (no command line anyway). |
| I40 | build (owner chose) | Parsing strangers' documents is a classic way to run code on a PC. | Install only `markitdown[pdf,docx,xlsx,pptx]` (never `[all]`: audio goes to Google, report-verified); hash-pinned; pdfminer.six at or after 20251107 (CVE-2025-64512, pickle code-run from a crafted PDF; a second advisory, CVE-2025-70559, also exists - public advisories, not checked here); convert in a child process with `jarvis_child_env` (no secrets), a time limit and a size cap; pass file paths only, never a web address (MarkItDown can fetch URLs - from memory, not checked); protected-path rule applies. |
| I41 | build later | A big index of private documents in one file. | Folders owner-picked, none by default; same protected-path list; index file deleted with one button; results outside text; never learned. |
| I42 | no objection | Built from tool results, not the model's claims. | Links shown with their host, opened only on a tap, never fetched for a preview (report). |
| I43 | no objection | Uses the existing note write; Jarvis never fetches the page. | A link from outside text keeps its note card. |
| I44 | build later | Wiki fixes still go through the existing card. | Source text stays outside text. |
| I45 | build later | The report's design is careful (DuckDB in a child process, external access and extensions off, settings locked). | Exactly as reported, plus the protected-path rule on the named file and `jarvis_child_env`; only one SELECT, checked by code. |
| I46 | build later | ffmpeg reads strangers' media and can follow references inside playlist-style files to other files or web addresses. | ffmpeg from a named publisher, pinned and hashed; run with `-protocol_whitelist file,pipe` (no network, no following links); child process with no secrets and a time limit; transcript is outside text. |
| I47 | build later | Reads one file inside a browser profile - a folder `file_read` refuses on purpose. | A narrow named-file reader (only `Bookmarks` / the bookmarks table), never a general exception to G2; titles outside text; nothing kept. |
| I48 | build later | Very private, and the History file sits beside Cookies and saved passwords. | Only after I47; card to turn on; read-only copy made in memory (or deleted at once), only the `urls`/`visits` tables, 30 days, banking/health excluded; outside text; nothing kept. |
| I49 | build later | A new way out of the PC, and headline text is outside text. | ARCHITECTURE section 4 row and `jarvis_reach` row first; https only, no redirect to another host, size and time caps, a parser that refuses XML entity tricks; shown in the model-free briefing only (`jarvis_briefing.py` is built without the AI, lines 1-20); card per feed. |
| I50 | no objection | Opens Obsidian by a local link. | Paths from the wiki only. |
| I51 | build | Removes a guessing gap; the CLI also has `eval` (runs code). | A fixed list of read commands with fixed arguments, called by full path; nothing from the model reaches the command line. |
| I52 | build (detect only) | Detecting a database graph is local and read-only. | The later MCP half waits for I07 and an HTTP decision; its bearer token in Credential Manager (G3). |
| I53 | build (owner chose) | A draft is uploaded to the mail provider, so private text (a memory, a note) can leave the PC with no card in a plain turn. | Card after outside text (owner's pending question) AND when a sensitive saved fact, a note or a file's text went into it (the web-search test); IMAP APPEND only to the server's `\Drafts` folder, same host/TLS/password rules as sending (`jarvis_email_send`); no attachments; local model only. |
| I54 | no objection | Tightens the send card; the .vcf is the owner's own export. | Say where the file is and that it is plain text; never learned. |
| I55 | build later | A write to the calendar server. | One card per event (report). |
| I56 | build later | Scanned text is outside text. | NAPS2 run as a separate program; OCR as I14; note write gets its card. |
| I57 | no objection | Temporary chat; drafts from a note the owner picks. | Note text counts as outside text. |
| I58 | no objection | Fixed instruction now. | Text to translate is outside text; a later dedicated model follows I09's download rules; licence read at download time. |
| I59 | no objection | Temporary chat. | None. |
| I60 | no objection | Never edits by itself. | File reads keep G2's rule. |
| I61 | build later | One yes for several steps is the pattern attackers aim at; safe only if a planted instruction can never shape the plan. | Only from the owner's own words in a turn with no outside text; any step whose values came from an earlier step is asked again (report); risky steps always their own card; wait for I95's numbers. |
| I62 | build later | Literal saved steps are good; the risk is compiling from a tainted turn. | Compile only from own words; "Try it" opens no socket; never runs by itself. |
| I63 | no objection | Owner's words, no model, reads nothing. | Health or money goals kept off lock screens (report). |
| I64 | build later | Model-drafted steps; accepting runs nothing. | Stays that way. |
| I65 | build later | Undo is itself an action. | Undo gets a card; "cannot be undone" said plainly. |
| I66 | build | Follows `jarvis_tellme`'s safe shape: nothing read reaches the model, words come from the owner (`jarvis_tellme.py:18-31`). | Folder must pass the protected-path rule; only a count and the owner's folder name shown; calendar via `calendar_read` at `auto`. |
| I67 | build later | A new way out, to an address typed once and then fetched for weeks. | Section 4 row; https only; refuse redirects and any address on the owner's own networks (SSRF), judged after DNS lookup; compare a hash only, page text never to the model. Decide with I49. |
| I68 | build (owner chose) | Same server and password, but held open for hours. | IMAPClient pinned with hashes; certificate checked; `EXAMINE` and `PEEK` only as today; every wake-up still passes the gate as `email_read` at `auto`; on a dropped link fall back to 5-minute looks and say so under Coming up (fails closed = says it is not watching). |
| I69 | build | Same match, reversed; nothing new leaves. | As I68. |
| I70 | build later | Uses a key every few minutes; today it would be an env var (G3). | Fine-grained read-only token for one repo, in Credential Manager, sent only to `api.github.com`; words from the owner, never commit text (report). |
| I71 | build later | Unattended jobs that read outside text overnight and resume after restarts (G1). | G1 fixed first; night jobs only read and prepare; anything that acts waits for a morning card; each job stoppable by Stop everything; big model respects standby. |
| I72 | build later | Snippets are fine; fetching whole pages is a new egress and an SSRF route (a result link can point at the home router). | Snippets only for now; each round of search words is a card; the reader has no tools. Whole pages: not until a fetcher refuses private addresses after DNS lookup and redirects. |
| I73 | build (owner chose, queued) | The phone app would see every app's notifications; one filter bug sends everything. | Allowlist of apps, empty by default, banking refused; filter and hide one-time codes ON THE PHONE before anything leaves the listener (same code table as `jarvis_mail_mask`); kept in phone memory only and sent only when the owner asks; outside text on the PC, never saved, never a cloud lane, never triggers an action; screenshots blocked while on; never SMS. CAP #17's "sender and app only" is safer than what the owner chose - see objections. |
| I74 | build later | Reads past chats (the same written rule as I38). | After the I38 decision; outside text inside chats stays outside; saved after a card. |
| I75 | build (owner chose) | Uses HA's service-call address (`POST /api/services/...`), the same one that acts. | A separate plan that can call exactly `weather.get_forecasts` with `return_response` and nothing else, never via `plan_service`; a test proves no other domain or service is reachable; forecast is outside text (briefing is model-free). |
| I76 | build | Read-only, one named device. | Logbook text is outside text. |
| I77 | build later | HA's exposed-devices list needs an ADMIN token (CAP #10, report's claim), which I81 is trying to remove. | Resolve the clash first; never HA's own MCP action tools; no HTTP MCP until decided. |
| I78 | build later | A new WebSocket client to HA. | `ws://` only inside the owner's own networks, by the same rule as `http://` (`jarvis_local_http.plain_http_problem`, `:182`); `wss://` certificate checked; library pinned or hand-written; groups still capped at 10 and never cut. |
| I79 | build later | Only ever narrows; turning on is a card. | A missing signal means "not at the PC" (quieter). |
| I80 | build later | Read-only; adds honesty to cards. | Needs I78's rules. |
| I81 | build | Shrinks what a leaked HA token can do. | Preflight warns on an admin token; guide the owner to a non-admin HA user. |
| I82 | build | Labels only, via `tellme`. | No picture, no face. |
| I83 | build later | A camera picture is among the most private things Jarvis could show. | Own card each time (`home_camera_look`, ask); never written to disk (including the app's web cache); hidden under App lock; local picture model only; never continuous. |
| I84 | no objection | Numbers. | None. |
| I85 | build later | Presence data; at most one offered card. | Only the owner's own `person.*`; nothing switches by itself. |
| I86 | no objection | Read-only HA values into the model-free briefing. | Car commands keep their own cards. |
| I87 | build later | Writes to HA; items may reach HA's cloud if the owner uses remote access. | Items from outside text get a card, like notes. |
| I88 | don't build (as an API writer) | Writing HA automations needs an admin token (clashes with I81) and creates actions that then run forever with no card. | A later, safe form: Jarvis drafts the automation text and the owner adds it in HA himself. |
| I89 | build later | Sends a wake packet; changes no data. | Never a router port-forward; HA button or a home box only. |
| I90 | build later | Admin need not verified. | The task is created unelevated and runs no Jarvis script. |
| I91 | build | Low-risk control, but song and video titles are written by strangers. | "What's playing" text is outside text; the no-card setting covers play/pause/next only. |
| I92 | build later (list only) | Updating runs installers as administrator, chosen from a list strangers publish. | List only, `--source winget`, winget's own telemetry off; updating stays a one-line command the owner runs, not a Jarvis action. |
| I93 | build (owner chose) | The owner's tap in the phone's own app is the approval. | Button warns about two alarms (report). |
| I94 | no objection | Opens Messages; the owner picks the person and presses send. | None. |
| I95 | build | Turns "is Jarvis safe?" into a number; decides I104-I108. | Offline on the PC; attack texts never reach real tools. |
| I96 | build | Protects against data loss; the backup is the most sensitive file Jarvis would ever make. | Code generated by Jarvis (not chosen), 100+ bits, shown once; age or Argon2id; this PC or USB only; a RESTORE must not loosen anything - it keeps the stricter of the current and restored tiers and "What asks first" lines, or lists each loosening on its card (the report's bundle includes `jarvis-framework.toml`, so a crafted backup could otherwise set tiers to "auto"); one card plus Windows Hello; "Erase the words cannot reach old backups" said. |
| I97 | build | Read-only checks. | WARN only. |
| I98 | build (after G1) | Safe for cards (a waiting card dies with the process; the stamp secret is new each start, `jarvis_owner_check.py:238-241`), NOT safe for taint (G1). | Fix G1 first; at most 3 restarts in 10 minutes, then stop and say so. |
| I99 | build | faulthandler writes stack lines, not variable values. | Rust panic file goes through the scrubber; kept on the PC; scrubbed before any sharing. |
| I100 | don't build (as a standing setting) | A crash dump is a plain-text copy of memory on disk: the token, keys and chat text (rule 3). | If ever needed, a one-off the owner switches on for one crash and deletes after. |
| I101 | build later | Good, but a cleared security chip loses history for good. | Only after I96. |
| I102 | build (owner chose) | Pairing is where a stolen phone or a listener on the home network gets in. | As designed (one-time 128-bit QR secret, 10 minutes, attestation checked offline, Windows Hello card with matching words, typed code only over encrypted links, 3 tries); the backend stores only a HASH of each device token; the old shared token gets a retire date - while it lives, the gap step 2 closes stays open. |
| I103 | build (owner chose) | Closes the "stolen token on another device" gap. | Sign card id + one-time number + hash of the card's words; refuse replays; face unlock that cannot unlock the key falls back to PIN (report). |
| I104 | build later | Stricter only. | Wait for I95. |
| I105 | build later | Only if I95 shows gains. | Reader has no tools. |
| I106 | build later | Label only. | Never loosens. |
| I107 | build later | May hurt reading. | Measure with I95. |
| I108 | build later | A downloaded detector; warning only. | Prefer an MIT/Apache model over the gated Llama-licence one; ONNX; never a block. |
| I109 | build | Counts only. | No text stored. |
| I110 | build | Stricter only. | Both apps. |
| I111 | build | Directly improves the supply chain. | Hash-locked packages, 7-day wait; staged switch only after G1. |
| I112 | build | Better device names and a lock on Tailscale's side. | Owner-side settings documented; `whois` is advice, never a grant. |
| I113 | build | Stricter only; half already built in a worktree. | Lock-screen widget opt-out confirmed in CI. |
| I114 | build | Keeps copies out of clipboard history and sync. | As reported. |
| I115 | build | Keeps pasted passwords out of stored history. | Same patterns as `jarvis_sensitive`/`jarvis_mail_mask`. |
| I116 | no objection | Fills the box, never sends. | None. |
| I117 | no objection | Titles only, never an Approve. | Hidden under App lock. |
| I118 | no objection | Owner's own words into the daily note. | None. |
| I119 | no objection | Each "Fix" that turns something on raises its usual card. | No Fix runs anything elevated. |
| I120 | build | A new way for any program on the PC to hand Jarvis a file. | Fills the box tagged `shared`, never sends by itself (report's rule); refuses protected paths (G2 - the Rust side needs the same list, via a shared case table like `tools/gen_own_network_cases.py`); App lock applies (as second launches already do, `lib.rs:629-660`). |
| I121 | build later | A new upload route on the backend. | After I40; token required; size cap; type checked by content; converted in I40's child process; `shared` tag. |
| I122 | no objection | Read-only link to Windows Focus. | None. |
| I123 | no objection | Silences only. | Alarms and urgent alerts get through. |
| I124 | no objection | Timer label on a lock screen. | Lock-screen words generic under App lock / hidden lists. |
| I125 | no objection | App lock still applies. | None. |
| I126 | no objection | Counts only. | Off the lock screen. |
| I127 | no objection | Accessibility. | None. |
| I128 | build later | A registered activation point (COM/Share target) that other programs can call. | Anything arriving through it is `shared`; never an Approve. |
| I129 | build | Fixing the flat rules allowance is also a safety fix: the rules are what tell the model outside text is data. | Test that the rules block's size fits; "outside text cannot change it" is wording, not a wall. |
| I130 | no objection | Wording. | None. |
| I131 | no objection | Fixed text, no model. | None. |
| I132 | no objection | Honesty label. | None. |
| I133 | build | Includes "outside text cannot change character". | Offline. |
| I134 | build | A stale model carries older safety wording. | WARN only. |
| I135 | no objection | Wording. | None. |
| I136 | no objection | Wording. | None. |
| I137 | no objection | Wording; never on cards. | None. |
| I138 | no objection | Values map to fixed repo sentences. | 900-character cap by test. |
| I139 | no objection | A list with Undo. | Hidden under App lock. |
| I140 | no objection | Guarded by the live-turn checks. | Same checks as automatic learning. |
| I141 | no objection | Wording. | None. |
| I142 | no objection | Ordinary memory with Forget/Erase. | Owner's words only. |
| I143 | build later | The one place owner text becomes an instruction to the model. | Typed on the settings page only; refuse anything about approvals, sending, rules or tools; 5 notes, short cap; placed in the style line, never the rules. |
| I144 | no objection | Wording. | None. |
| I145 | build (look first) | Eight unseen prompt modes nobody reviews could weaken the rules. | Read each mode's text before adding presets. |
| I146 | no objection | Temporary chat. | None. |
| I147 | no objection | Local sound analysis. | None. |
| I148 | no objection | Never looks like approval (report). | None. |
| I149 | no objection | Local. | None. |
| I150 | no objection | Guidance. | None. |
| I151 | build | Fixed help text; contacts no one, logs nothing. | As reported. |
| I152 | build | Keeps distress words away from the cloud offer. | Stricter only. |
| I153 | no objection | Wording. | None. |
| I154 | build | Stops crisis turns becoming memory cards. | Stricter only. |
| I155 | build later | These kits default to a cloud judge. | Local judge only; run offline; check no telemetry. |

## 2. Objections for the other reviewers

1. **To Fit and Upkeep: G1 must come before I98, I111 and I71.** A watchdog is
   pitched as "safe under the rules" (round 2 trust, item 4). It is safe for
   cards, not for taint. If you disagree, show where taint survives a restart.
2. **To Rules: I73 as the owner chose it lets notification TEXT reach the PC**
   (to summarise on request). CAP #17 proposed "sender and app only, never the
   message text". I am not re-opening the owner's choice, but the safer
   default inside it is: text stays on the phone and only reaches the PC for
   the one request the owner makes. If Rules reads the decision as requiring a
   PC-side store, say so.
3. **To Fit: "local servers only" for MCP (I07) should mean stdio child
   processes on this PC in version 1.** That rules out HA's MCP (I77) and
   Logseq's (I52 later) for now. Fit may argue Logseq's server on 127.0.0.1 is
   "local". My answer: it needs a bearer token (G3) and an HTTP client path
   the draft does not have; decide it as a separate step, not by default.
4. **To Fit and Hardware: I77 and I81 pull in opposite directions.** The
   exposed-devices list needs an admin HA token (CAP #10, report's claim, not
   checked); I81 says Jarvis should not hold one. I side with I81.
5. **To Devil's advocate and Overwhelm: I recommend BUILD for I96 (backup) even
   though it creates the most sensitive file Jarvis ever writes**, because
   today one dead disk loses memory and the history key. My condition is the
   restore rule (never loosens a tier). If you say "don't build", say what
   protects against disk loss instead.
6. **To Upkeep: G2's list needs to be ONE list read by the backend AND the
   desktop's Rust (for I120)**, generated like the own-network case table.
   That is CI work; I think it is worth it.
7. **To Rules: I53 drafts with no card in a plain turn still upload private
   text to the mail provider.** The owner's open question is "card only after
   outside text" vs "always". I add: also a card when a sensitive saved fact,
   a note or a file went into the draft (the same test web search uses).
8. **To Overwhelm: I92 (winget) update and I88 (HA automations) are "don't let
   Jarvis do it" from me, but "Jarvis tells the owner the one line / the text
   to paste" is fine.** That keeps the feature and removes the new power.
9. **To Hardware: I30 is a security "don't build"** (new PyTorch stack of
   downloads for a fun feature), not a GPU one. If Hardware says it fits,
   that does not change my reason.
10. **To Devil's advocate: I39 as "build"** - you may call Everything
   overlapping with Windows search. From security, `es.exe` with a folder
   limit is the smaller surface: Windows' index can include Outlook mail
   (round 3 knowledge, item 3, report's claim).

## 3. Wrong or out of date in the research reports

- **ENGINE section 9, "the MCP bridge draft is not in the repository"**: out of
  date. It is at `docs/designs/mcp-draft-2026-09-23/` (commit `676538e`, "keep
  the MCP bridge and skills drafts in the repo").
- **ENGINE section 9, "every call through the gate, tier ask by default"**,
  vs the draft itself: the draft lets a listed tool drop below "ask"
  (`DESIGN.md` lines 79-95) while its summary says every call raises a card
  (lines 22-24). One of the two must be made true.
- **ENGINE section 2 cites `jarvis_agent.py:2826-2833`** for the cloud-model
  refusal; it has moved to about `:2878-2900` (`_is_cloud_model` at `:2878`).
  00-ideas I129's `:2016/:3000/:3509` are now `:2044/:3033/:3549`. Line drift
  after the merge `1381e6a`, not wrong substance.
- **ROUND 3 KNOWLEDGE, "`file_read` can read any path"**: fixed by `1ce1dac`,
  but not as the report advised (an allowlist); a refusal list was used, and
  it misses `~/.android/adbkey` and others (G2). Its "tier not checked": the
  shipped copy says `auto` (`backend/rebuilt/jarvis-framework.toml:95`).
- **VOICE-VISION section 1** plans to turn the screenshot's image part "into a
  text part" of the same message. The same message keeps the owner's `typed`
  tag in the tool loop, so the "mark the turn like a pasted message" it asks
  for would not happen by itself (`OWN_WORDS`, `jarvis_agent.py:2385`). The
  chat log does retag a picture turn as `picture_caption`
  (`jarvis_chat_log.py:655-660`, and the desktop's `sentProvenance`,
  `jarvis-desktop/src/chat-history.js:202-206`); I did not check which tag the
  tool loop receives for a picture turn today, so the backend should mark the
  OCR text itself.
- **ROUND 2 TRUST item 4, the watchdog is "safe under the rules"**: true for
  waiting cards, not for conversation taint (G1).
- **ROUND 2 TRUST item 2, backup and restore**: the backup includes
  `jarvis-framework.toml`, so restoring can loosen tiers; the design does not
  say so.
- **CAPABILITIES item 5 (MarkItDown)** and **ROUND 3 KNOWLEDGE item 7
  (ffmpeg)** name no parsing risks. pdfminer.six (under MarkItDown's PDF path)
  had a code-run-from-a-crafted-PDF flaw fixed in 20251107 (CVE-2025-64512,
  public advisory, not re-read here); ffmpeg needs its network and
  link-following switched off.
- **ROUND 3 HOME item 2** gives the owner an admin logon task without saying
  its action must never be a file his normal account can change.
- **CAPABILITIES item 10** proposes HA's MCP (HTTP) as "the first real use of
  the MCP bridge"; the bridge draft speaks stdio only, and ENGINE section 9
  says no HTTP servers. Not wrong alone, but the two reports contradict each
  other (00-ideas note 5 saw this too).

Sources for the two outside facts used above (both public security
advisories; not otherwise checked): [mcp-server-git flaws (The Hacker News)](https://thehackernews.com/2026/01/three-flaws-in-anthropic-mcp-git-server.html),
[CVE-2026-27735](https://vulert.com/vuln-db/CVE-2026-27735),
[pdfminer.six CVE-2025-64512](https://www.sentinelone.com/vulnerability-database/cve-2025-64512/),
[pdfminer.six GHSA-f83h-ghpp-7wcc](https://github.com/pdfminer/pdfminer.six/security/advisories/GHSA-f83h-ghpp-7wcc).
