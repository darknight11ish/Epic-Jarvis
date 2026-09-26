# Cutting-edge audit, round 3, 2026-09-26: knowledge and information

The slice: helping the owner **find, keep and understand** their own things,
all on the PC. Research only. Nothing was built, nothing in Jarvis changed.
It does not repeat the earlier reports: "Ask my own stuff" (`creativity-2026-09-25/future.md`
idea 1), documents to text with MarkItDown (`CUTTING-EDGE-2026-09-26-capabilities.md`
idea 5, approved by the owner on 2026-09-26), the memory re-ranker and past-chat
search (`MEMORY-RESEARCH-2026-09-26.md`), screenshot text and PaddleOCR-VL
(`CUTTING-EDGE-2026-09-26-voice-vision.md`). Where an idea here builds on one
of those, it says so.

**How it was checked.** Jarvis read at commit `598a600`. Read myself: the
READMEs, licences or source of qmd, voidtools ES, DuckDB's "Securing DuckDB"
page, Monty, mcp-run-python, ContextCite, Karakeep, wallabag, Miniflux,
FreshRSS, sherpa-onnx (and its long-audio example scripts), MarkItDown's audio
converter; PyPI metadata for versions and licences. **Search summaries only**
(marked **(summary)**): voidtools.com (blocked), Karpathy's LLM Wiki gist
(blocked), Windows 11 semantic search, Pocket's and Omnivore's shutdowns,
Gemini-in-Chrome and Edge Copilot history features, browser file locations,
Parakeet v3. Vendor numbers are **claims**. Nothing was measured on the owner's PC.

---

## In short (for the owner)

1. **Show where every answer came from.** Under an answer, list the notes, wiki pages, web links and files Jarvis read, and check its quotes really are in them.
2. **"Save this for later"** can go into your Obsidian daily note as a reading-list line, and "what's on my reading list?" can be answered without the AI model.
3. **"Where's that file?"** can use tools Windows users already have (Windows' own search index, or the free "Everything" app), on the PC only.
4. **The wiki builder's next steps:** a "check my wiki" report, quotes that are checked against the source, and big documents split instead of refused.
5. **Spreadsheets:** Jarvis can answer "what did I spend on food in March?" from a CSV by running a database query in a locked box and showing you the query and the numbers.
6. **Two things are your call:** reading browser history (very private) and fetching news headlines (a new way out of the PC). Both questions are at the end.

---

## Ranked list

"Rule risk" = how close it comes to the five rules and the owner's dated decisions.

| # | Idea | Why it matters | Size | Rule risk |
|---|---|---|---|---|
| 1 | "Where this came from" under every answer, with a quote check | Stops confident answers stitched from old notes; the owner can check in one tap | M | Low |
| 2 | Reading list in the daily note ("save for later") | Pocket and Omnivore both shut down; a list in your own files cannot | S | None |
| 3 | "Where's that file?" by name (Everything or Windows' index) | An everyday gap; answered in under a second, no AI model needed | S-M | Low |
| 4 | Wiki builder, next steps: check, quote, split | Keeps the wiki honest as it grows; uses the existing card | M | Low |
| 5 | One local "library" index: vault, wiki and chosen folders | The search half of "ask my documents" (already approved), done once for all | M-L | Low-medium (which folders) |
| 6 | Spreadsheet and CSV questions through DuckDB, locked down | Numbers come from a database, not the model's guess | M | Medium (model-written queries are code) |
| 7 | Transcribe an audio or video FILE the owner gives | Lectures, podcasts, own voice memos into text, then into the wiki | M | Low-medium (other people's voices) |
| 8 | Bookmarks Q&A | "Did I bookmark a ramen recipe?" | S | Low |
| 9 | Wiki pages on the desktop's memory map, and "Open in Obsidian" | See how pages link, on the PC only | S | None (desktop only, by rule) |
| 10 | News headlines from feeds the owner chooses, in the briefing | Closes "news: not available" | M | Medium (a new way out) |
| 11 | Browser history Q&A, off unless switched on | "Which site had that desk last week?" | M | High (owner's call) |

---

## Details

**1. "Where this came from", with a quote check.** Today only saved facts are
listed under an answer ("Used in this answer", `docs/JARVIS-API.md:682`, from
`injected_ids`). Notes, wiki pages, web results and files the model read are
not: the apps get no tool results ("No tool receipt", JARVIS-API §4). *What:*
the PC records, per answer, each reading tool's result by reference - a note's
`ref` (`jarvis_notes.py` `_search_vault` already returns it), a wiki page path,
a web result's link, a file path - and a new read route by the answer's
`turn_id` (already in `X-Jarvis-Route`, JARVIS-API.md:530) returns that list,
the way `/api/memory/used` does. Built in code from what the tools returned,
never from what the model claims. *Quote check:* when the answer quotes, code
checks each quote word for word (spacing and case ignored) against this
answer's tool results, and a quote not found is marked "not found in what
Jarvis read". *Source:* the research method ContextCite (MIT, MadryLab) does
this better, but it needs Hugging Face models and dozens of extra model runs
per answer - too heavy for the 8 GB card today; the plain word check is the
fit. *Plugs in:* `jarvis_agent.py` tool loop (`TOOLS`, line 591); desktop
`answer-memory.js` / `memory-used.js`; phone `UsedMemoriesPlate.kt`. *Fit:*
no new way out. A web link is shown as text with its host and opens only when
the owner taps it (never fetched by Jarvis to show a preview). Note titles are
private, so the list hides with "Hide memory lists and chat history" and App
lock. The check only ever warns; it never makes outside text more trusted and
never loosens a card. Both apps. **M.**

**2. Reading list in the daily note.** Pocket shut down on 2025-07-08 and
Omnivore in November 2024, deleting what people saved **(summary)**. *What:*
"save for later: <link>" typed or said adds `- [ ] <link> <owner's words> #readlater`
to today's Obsidian daily note through the existing `append_obsidian_daily`
(tier `auto`, the owner's own words). "What's on my reading list?" is answered
without the model (`jarvis_quick.py`) from a vault search for unticked
`#readlater` lines; ticking it in Obsidian marks it read. *Fit:* a link shared
from the phone is outside text, so it gets the note card, as today
(`usefulness.md` cut a "read later inbox" for exactly that reason; this
version works around it by using the owner's own words). Jarvis does not fetch
the page: fetching pages is a new way out of the PC and stays unbuilt. If the
owner already runs a read-later server on the PC, **wallabag** (MIT) or
**Karakeep** (AGPL-3.0; supports local Ollama for its tagging), a read-only
bridge to it on 127.0.0.1 is a later M, not needed first. **S.**

**3. "Where's that file?" by name.** Two options, both local:
- **Everything** by voidtools: indexes every file NAME on NTFS drives in real
  time. Its command-line tool `es.exe` is MIT (read); Everything itself is
  freeware under an MIT-style licence, 1.4.1.1032 stable (2026-01-23) and 1.5
  in preview **(summary; voidtools.com blocked)**. The command line and SDK do
  not work with the "Lite" install. Jarvis would call `es.exe -n 20 -path <allowed folder> <words>`.
- **Windows Search's own index**, queried with SQL through the
  `Search.CollatorDSO` provider (`SELECT TOP 20 System.ItemPathDisplay ... FROM SystemIndex WHERE SCOPE='file:...'`),
  via `pywin32` (PSF licence, 312). Built into Windows, and it can match words
  INSIDE Office and PDF files. But its scope is whatever Windows indexes, which
  can include Outlook mail, so Jarvis must add its own folder allowlist in the
  `SCOPE`. Windows 11's newer "semantic" file search needs a Copilot+ PC with
  a 40+ TOPS NPU **(summary)**; the owner's desktop almost certainly has none
  **(guess)**, so it is not an option.
*Plugs in:* a new read-only tool beside `notes_search` (`jarvis_agent.py:780`),
plan/describe/gate/run like `jarvis_notes.py`, and a fast path in
`jarvis_quick.py` ("find the file called invoice"). "Open folder" on the PC;
the phone shows the list only. *Fit:* file names are private, so they stay on
this PC's model (tools run only on the local lane) and count as outside text,
so a later web search asks first. Never turn on Everything's HTTP or ETP
server: it shares the file list over the network. **S-M.**

**4. The wiki builder's next steps.** The builder exists: `backend/jarvis_wiki.py`
(one `wiki_update` card per document, tier `ask`, `jarvis-framework.toml:230`;
reads only `.md` and `.txt`, line 139; at most 12 pages, line 141; refuses a
document too big for the model). It follows Karpathy's "LLM Wiki" pattern
(gist, 2026-04-04 **(summary)**), which has three steps: ingest, query and
**lint**. Jarvis has ingest only. Four small steps, each S:
- **"Check my wiki" (lint).** The wiki's model reads `index.md` and the pages
  and reports contradictions, pages whose source changed or disappeared, pages
  nothing links to, and missing links. A report first; any fix is proposed
  through the same `wiki_update` card. Never edits by itself.
- **Quotes that are checked.** Each section of a page carries a short quote
  from its source; `jarvis_wiki.py`'s validation (before the card) refuses a
  quote that is not in the source word for word. The same check as idea 1.
- **Split, do not refuse.** A document "too big" is split at its headings into
  parts, each added in turn with its own card. Nothing is cut short, as now.
- **Ask the wiki, index first.** For a wiki question, the model reads
  `index.md` (a few thousand words), picks the pages and reads only those.
  No embeddings needed at this size **(summary of the gist's claim)**, and it
  fits today's ~16k context. Wiki pages are already reachable through
  `notes_search`, because the vault search skips only hidden folders
  (`jarvis_notes.py` `_search_vault`).
PDFs and Word files come with the already-approved MarkItDown work. Everything
here needs the second card or the big model, as the builder does. **M in all.**

**5. One local "library" index.** The approved "asking about PDFs and Word
files" work needs a search over the text MarkItDown makes. Build it once, for
the vault, the wiki and folders the owner picks. *How:* the same parts memory
already uses - FTS5 word search, `sqlite-vec` meaning search, fastembed with
`BAAI/bge-small-en-v1.5` on the processor (`rebuilt/jarvis_memory.py:410-421`),
fused by rank - plus the re-ranker the owner approved for memory. Kept in its
own file (for example `library.db`), NOT in `memory.db`: a `documents` table
there already clashes with OpenJarvis's indexer (ARCHITECTURE §10). Ideas worth
copying from **qmd** (MIT, 2.8.3, 2026-08-16, read): a one-line description per
folder returned with each hit, and skipping the slow query-rewriting step when
the word search is already strong. Do not adopt qmd itself: it is Node, and it
downloads models from Hugging Face on first use. *Folders:* none by default.
The owner adds folders on the PC; always left out: `AppData`, browser profiles,
`.ssh`, password-manager files (`.kdbx`), `.env` files, Jarvis's own data
folder, hidden and system files. Re-indexing is a kind on the one scheduler
(ARCHITECTURE §12); a new kind asks by default. *Fit:* nothing leaves the PC;
results are outside text, never learned as facts (2026-09-24 rule); the index
file is deleted with one button. **M-L.**

**6. Spreadsheet and CSV questions, locked down.** *How:* **DuckDB** (MIT,
1.5.5) runs in a separate process with Jarvis's secrets stripped from its
environment (`jarvis_child_env`, as `shell_exec` does). Jarvis's own code
loads the ONE file the owner named, then switches off DuckDB's file and network
access (`enable_external_access = false`), extension loading
(`autoload_known_extensions`, `autoinstall_known_extensions`,
`allow_community_extensions = false`), caps memory and threads, and locks the
settings (`lock_configuration = true`). The model sees the column names and a
few rows, writes ONE `SELECT`, and code checks it is one SELECT, runs it with
a time limit and a row cap, and shows the query and the result table. DuckDB's
own page says these settings are "defense-in-depth", "not a substitute for
proper sandboxing", so the separate process and the time limit are not
optional. Excel files are turned into CSV by Jarvis first (DuckDB's Excel
support is an extension, and installing one downloads it). *Later option:*
**Monty** (MIT, 1.0.0 released 2026-09-25), a Python sandbox in Rust with no
files, network or environment inside; it has no pandas and only a subset of
Python, and it is one day old. *Fit:* acts on nothing and sends nothing, so no
card; the cells are outside text. It does not contradict "no sandbox exists"
(`jarvis-framework.toml:314`): this is a narrow query box, not a place to run
general code, and the docs must say so. **M.**

**7. Transcribe a file the owner gives.** Jarvis's voice takes clips of at
most 30 seconds (`jarvis_speech.py:944`). *How:* for a whole file, cut it at
the pauses with the Silero speech detector Jarvis already has, and put each
piece through the same sherpa-onnx Parakeet model; sherpa-onnx ships this
exact pattern (`python-api-examples/generate-subtitles.py` and
`vad-with-non-streaming-asr.py`, read) and optional "who spoke when"
(`offline-speaker-diarization.py`). Parakeet TDT 0.6B v3 adds 25 European
languages **(summary; claim)**. The result is a `.transcript.md` with times,
put in `Jarvis Wiki/Sources` so the wiki and the library can use it; a summary
only when asked. A background job, paused while the owner is talking to
Jarvis. mp3/mp4 need ffmpeg on the PC. *Fit:* the transcript is outside text:
never a command, never through the voice check, never learned, never used as
a voice sample. **Why meetings stay out:** recording a live meeting records
other people, often without their consent; the earlier audits cut it for that
and the 30-second limit (`creativity-2026-09-25/usefulness.md`,
`CUTTING-EDGE-2026-09-26-capabilities.md` "Not for Jarvis"). A file the owner
already has is different: Jarvis never records, it only reads what it is given.
Shares its cutting-up code with the queued "voice memos to Obsidian". **M.**

**8. Bookmarks Q&A.** Chrome and Edge keep bookmarks in a `Bookmarks` JSON
file in the profile folder; Firefox in `places.sqlite` **(summary)**. Read on
request, nothing copied or kept. Titles are set by websites, so they are
outside text. One read-only tool, the same four steps as §3. **S.**

**9. The wiki on the desktop's map.** The Brain already draws memory as a
"galaxy" (`jarvis-desktop/src/brain.js`, from line 4622; `/api/graph`). A
second layer could draw wiki pages and their `[[links]]`, parsed on the PC.
Cheaper first step: an "Open in Obsidian" button (the `obsidian://open` link),
because Obsidian's own graph view already shows these links. **Desktop only:
the graph stays off the phone** (`CLAUDE.md`; `tools/check_parity.py:144`),
so this goes in ARCHITECTURE §8's list. **S.**

**10. News headlines from chosen feeds.** The briefing says "Weather and news:
not available" (`jarvis_briefing.py:117`). *How:* **feedparser** (BSD-2,
6.0.14, 2026-07-30) reads feeds the owner types into the PC's Settings;
headlines only (title, site, time), https only, no redirect to another host.
Or run **Miniflux** (Apache-2.0) or **FreshRSS** (AGPL-3.0) on this PC in
Docker, like SearXNG, and Jarvis reads it on 127.0.0.1 only. *Fit:* it is a
new way out of the PC, so it needs a row in ARCHITECTURE §4 and in
`jarvis_reach.KINDS` (line 692). It sends nothing of the owner's except which
feeds they read (true of any feed reader). Headlines are outside text: never
facts, never actions, and a web search after reading them asks first under
the existing rule. Adding a feed shows more, so it would be one card per feed,
like other settings that show more. **M.**

**11. Browser history Q&A.** Chrome and Edge keep history in a plain SQLite
file (`...\User Data\Default\History`, tables `urls` and `visits`), locked
while the browser runs, so it is read from a read-only copy **(summary)**.
Google's Gemini in Chrome and Edge's Copilot now answer "which site had the
walnut desk?", sending the matching history to their cloud **(summary)**;
Jarvis could do it on the PC. *If built:* the same safe shape the owner chose
for phone notifications - off by default, on with a card, off at once; only
when asked; only the last 30 days; banking and health sites left out by a list
the owner edits; nothing kept, logged or learned; outside text; hidden under
App lock; the answer lists the entries it used (idea 1). **M.** Rule risk is
high because the file holds everything the owner looked at.

---

## Found while checking (tell the owner)

- **MarkItDown's audio option sends sound to Google.** Its audio converter
  calls `recognize_google` (`_transcribe_audio.py`, read), and its YouTube
  converter fetches transcripts from YouTube. The approved documents work must
  install only the document parts (for example `markitdown[pdf,docx,xlsx,pptx]`),
  never `[all]` or `[audio-transcription]` - rule 1. Round 1 warned only about
  its picture captions and Azure.
- **`file_read` can read any path.** `_run_file_read` (`jarvis_agent.py:199-216`)
  opens whatever path the model names, `.ssh` included; only reserved Windows
  device names are refused. Which tier it gets is set in `jarvis_gate.py`, on
  the owner's PC, and was not checked here. Ideas 3 and 5 bring a folder
  allowlist; `file_read` should share it.

---

## Not for Jarvis

| Seen in | What | Why not |
|---|---|---|
| MarkItDown | Audio transcription, YouTube transcripts | Sends audio to Google, fetches from YouTube (rule 1; an unnamed way out) |
| Gemini in Chrome, Edge Copilot | History and open-tab answers in the cloud | Rule 1. Idea 11 is the local version, and only if the owner wants it |
| Windows Recall, screenpipe | Recording everything seen, to search later | Already rejected (ARCHITECTURE §11) |
| Everything | Its HTTP / ETP server | Serves the owner's file list over the network |
| Karakeep | Its default cloud (OpenAI) tagging, shared lists | Rule 1; "one owner". Only with local Ollama, read-only |
| qmd | Adopting it whole | Node runtime; downloads models from Hugging Face at first run; copy the ideas instead |
| mcp-run-python (Pyodide) | Running model-written Python | Archived by its makers: "no way to run Python within pyodide safely" |
| pandas or Python on the PC itself | Model-written analysis code | No sandbox exists (`jarvis-framework.toml:314`); idea 6 is the narrow alternative |
| ContextCite | Exact answer-to-source attribution | Needs Hugging Face models and many extra runs per answer; not on 8 GB now |
| Windows semantic search | Meaning-based file search | Copilot+ PCs with a 40 TOPS NPU only **(summary)** |
| Meeting recorders | Recording live calls or rooms | Records other people; ≤30 s clips; cut twice before |
| Any of these | Learning facts from notes, files, feeds, history or transcripts | Facts come from the owner's own words only (2026-09-24) |
| Any of these | A knowledge map on the phone | The memory graph stays off the phone (`CLAUDE.md`) |

---

## Questions for the owner

1. Jarvis could answer "which website was that?" from your browser history,
   on the PC only. It would see everything you have looked at.
   - **Bookmarks only, for now** (recommended)
   - **Bookmarks, plus history, off until I switch it on with a card**
2. The morning briefing could list news headlines from websites you choose.
   Jarvis would then fetch those feeds from the internet.
   - **Yes, one card for each feed I add** (recommended)
   - **Keep "news: not available"**

---

## Sources

**Read myself (raw files on GitHub, PyPI):**
- qmd README, LICENSE (MIT), CHANGELOG (2.8.3, 2026-08-16): https://github.com/tobi/qmd
- voidtools ES (MIT): https://github.com/voidtools/ES
- DuckDB, "Securing DuckDB": https://github.com/duckdb/duckdb-web/blob/main/docs/current/operations_manual/securing_duckdb/overview.md ; PyPI `duckdb` 1.5.5
- Monty README and limitations (MIT, 1.0.0, 2026-09-25): https://github.com/pydantic/monty
- mcp-run-python archive notice: https://github.com/pydantic/mcp-run-python
- ContextCite (MIT): https://github.com/MadryLab/context-cite ; paper https://arxiv.org/abs/2409.00729
- Karakeep README and LICENSE (AGPL-3.0): https://github.com/karakeep-app/karakeep
- wallabag COPYING (MIT): https://github.com/wallabag/wallabag ; Miniflux (Apache-2.0): https://github.com/miniflux/v2 ; FreshRSS (AGPL-3.0): https://github.com/FreshRSS/FreshRSS
- sherpa-onnx README and `python-api-examples/` (Apache-2.0, 1.13.8): https://github.com/k2-fsa/sherpa-onnx
- MarkItDown `_transcribe_audio.py`, `_youtube_converter.py`: https://github.com/microsoft/markitdown
- PyPI: feedparser 6.0.14 (BSD-2), pywin32 312 (PSF), fastembed 0.8.1 (Apache-2.0), sqlite-vec 0.1.9 (MIT/Apache-2.0), markitdown 0.1.8 (MIT)

**Search summaries only (pages blocked or not opened):**
- Everything licence and versions: https://en.wikipedia.org/wiki/Everything_(software) ; SDK page https://www.voidtools.com/support/everything/sdk/
- Windows Search SQL: https://learn.microsoft.com/en-us/previous-versions/windows/desktop/legacy/ff684395(v=vs.85)
- Windows 11 semantic search behind Copilot+: https://windowsforum.com/news/windows-11-semantic-search-arrives-behind-copilot-hardware-gate.381526/
- Karpathy's LLM Wiki gist: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- Pocket shutdown: https://techcrunch.com/2025/05/22/mozilla-is-shutting-down-read-it-later-app-pocket ; Omnivore: https://gleamr.io/blog/omnivore-shut-down-alternatives
- Chrome history with Gemini: https://support.google.com/chrome/answer/16716225 ; Edge Copilot history: https://windowsforum.com/threads/microsoft-edge-copilot-update-browse-with-copilot-tab-context-and-privacy-risks.418409/
- Browser history files: https://en.wikiversity.org/wiki/Chromium_browsing_history_database
- Parakeet TDT 0.6B v3: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3

**Jarvis files read:** `CLAUDE.md`; `docs/ARCHITECTURE.md` §1-5, §8, §10-12;
`docs/JARVIS-API.md` contents, §4 ("Used in this answer"), §13, §23;
`docs/SECOND-CARD.md` "Wiki builder"; the earlier reports named at the top;
`backend/jarvis_wiki.py` (header, constants), `jarvis_notes.py` (header, vault
search), `jarvis_agent.py` (header, `TOOLS`, `file_read`, outside-text lines
2256-2345), `jarvis_briefing.py` (weather and news lines),
`rebuilt/jarvis_memory.py` (embedder), `rebuilt/jarvis-framework.toml` (tiers,
sandbox note); `jarvis-desktop/src/brain.js` (galaxy header).

**Not checked:** which gate tier `file_read` gets (`jarvis_gate.py` is on the
owner's PC); whether the owner's PC has Everything, an NPU, or Outlook in its
Windows index; any speed or quality figure on the owner's hardware.
