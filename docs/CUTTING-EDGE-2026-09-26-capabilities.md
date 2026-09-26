# Cutting-edge audit, 2026-09-26: everyday capabilities and integrations

What the newest open-source assistants ship, which local integrations are
worth adding, and where each would plug into Jarvis. Research only: nothing
here is built, and nothing about the rules changes without the owner's yes.
This builds on the 2026-09-25 reports (`COMPETITORS-*`, `CREATIVITY-AUDIT`,
`creativity-2026-09-25/`) and `MEMORY-RESEARCH-2026-09-26.md`, and does not
repeat their ideas.

## In short (for the owner)

1. Jarvis already has most everyday basics now. The best next gains are **small links between what exists**, not new outside services.
2. **Weather can come from your own Home Assistant**, so Jarvis gets it without any new connection to the internet.
3. **Your phone can hold its own alarm and calendar entry** when you tap "also on my phone". It then rings even when the PC is off.
4. **Email gets quicker and handier:** "tell me when" can hear new mail at once instead of every 5 minutes, and Jarvis can save a draft into your Gmail Drafts for you to finish.
5. **"Ask my documents" can start small:** turn PDFs and Word files into plain text on the PC, then search them the way Jarvis searches notes.
6. Two answers from you would unblock the most: pausing music without a card, and when a saved draft needs a card (the questions are at the end).

## How far to trust this

- **Read myself** (raw files on GitHub; that route was open): Home Assistant's
  2026.7 and 2026.9 release notes and the source for its MCP server, logbook,
  weather and to-do services; Open WebUI's `CHANGELOG.md` (0.10.0 to 0.11.4);
  OpenClaw's changelogs 2026.9.2 to 2026.9.6 and "Unreleased"; Logseq's
  `db-version.md`; kepano's `obsidian-cli` skill file; GitHub's
  `github-mcp-server` README; CPython 3.14's `imaplib.rst`; the licences named
  below; PyPI metadata (versions, licences).
- **Search summaries only** (the sites were blocked: home-assistant.io,
  obsidian.md, dev.to, docs.python.org, and the GitHub API): Android
  "restricted settings", Android 15 OTP redaction, Android 16 Live Updates,
  winget's PowerShell module, PowerToys, the MCP 2026-07-28 draft, Logseq's
  beta date, Ollama's September notes. These are marked **(summary)**.
- **Not re-checked since 2026-09-25:** Leon, Khoj, Hermes (its changelog path
  404s), goose, Jan and AnythingLLM beyond their READMEs.
- Vendor claims are claims. Nothing here was measured on the owner's PC.

## What changed out there (since the 09-25 reports)

| Project | What is new | What it means for Jarvis |
|---|---|---|
| **OpenClaw** 2026.9.4-9.6 | "Tool Search" **on by default** (tools found when needed, not all described up front); a read-only, public-only **GitHub reader**; **live meeting notes** from Meet/Teams/Zoom; editing an automation now **retires its "Always allow"** grant | Confirms the queued "lean mode" item. The re-approval fix shows why standing grants hurt: Jarvis has none. Its "Unreleased" notes turn **cross-provider messaging on by default** - a loosening Jarvis must not copy |
| **Open WebUI** 0.10-0.11.4 (to 2026-09-21) | A Files ability: the model lists, greps and reads **only the parts it needs** of attached files; chat timers that **cancel themselves if you reply first**; web-search confirmation (optional); sub-agents | The file-reading design suits a small model with little memory: search and read a slice, never paste a whole document. Idea 5 below |
| **Home Assistant** 2026.7-2026.9.3 | Activity (the logbook) now explains **why** something changed (automation → trigger → device); a new cloud speech engine (Soniox, cloud) | The "why" data is in the logbook's REST reply (idea 8). The cloud speech is not for Jarvis |
| **Logseq** | The database version is in beta, announced 2026-07-13 **(summary)**; it stores a graph in SQLite, not Markdown files, and has a local MCP server with a **"pretend"** (dry-run) mode (`db-version.md`, read) | Jarvis appends to journal *files*. A database graph would not see them (idea 12) |
| **Obsidian** 1.12 | An official CLI, free since 1.12.4 **(summary)**; it needs the app running and includes `daily:path`, `tasks`, and also `eval` (runs JavaScript) (kepano's skill file, read) | Can fix Jarvis's "daily notes in every date format" gap, with a strict allow-list (idea 11) |
| **MCP** | 2025-11-25 added async Tasks; a 2026-07-28 release candidate adds a stateless core and extensions **(summary)**. Home Assistant's server speaks stateless Streamable HTTP (docs source, read) | A Jarvis MCP bridge can be plain HTTP POSTs with `urllib`, no MCP library (idea 10) |

## Ranked list

"Rule risk" = how close it comes to the five rules and the owner's decisions.

| # | Idea | Why it matters | Size | Rule risk |
|---|---|---|---|---|
| 1 | Weather from Home Assistant's own weather device | Closes "weather: not available" with no new way out of the PC | S | Low |
| 2 | "Also on my phone": alarm to the phone's Clock app, event to the phone's calendar, by the owner's tap | Rings with the PC off; writes to Google Calendar without Google sign-in | S | None |
| 3 | Instant "tell me when" for email (IMAP IDLE), plus "tell me if X hasn't replied by Friday" | 5-minute wait becomes seconds; covers the common "chase-up" case | S-M | Low |
| 4 | Save an email draft into the owner's own Drafts folder | "Draft a reply to Sam" → finish it in Gmail on the phone; nothing is sent | S-M | Medium (owner's call) |
| 5 | Documents to text on the PC (MarkItDown), searched and read in slices | First step of "ask my documents" that fits today's 8 GB card | S-M | Low |
| 6 | Contacts from a `.vcf` file on the PC | "Email Priya" finds the address; the card warns "not in your contacts" | S-M | Low (a tightening) |
| 7 | Music and video control on this PC (Windows media controls) | "Pause", "next", "what's playing" - an everyday gap | S-M | Low (owner's call on cards) |
| 8 | "Why did the hall light turn on?" from Home Assistant's logbook | Home questions answered from HA's own record, read-only | S | Low |
| 9 | "Tell me when CI finishes" / "when the APK is published" (GitHub) | The owner waits on CI for every phone build | S-M | Low (rule 3 key, already allowed) |
| 10 | Home Assistant's own "exposed devices" list as Jarvis's device list | The owner picks devices in HA; less text for the 8B | S-M | Low |
| 11 | Obsidian CLI for "where is today's note?" and open tasks | Fixes the date-format gap in `ARCHITECTURE.md` §10 | S | Low (strict allow-list) |
| 12 | Logseq database graphs: detect and say so; later its MCP "pretend" as the card | Stops silent notes going nowhere | S (then M) | Low |
| 13 | Android 16 Live Updates for timers and focus sessions | The countdown stays on the lock screen | S | None |
| 14 | "What needs updating on this PC?" (winget), update only with a card | Keeps apps patched | S read / M update | Medium (new way out) |
| 15 | Mirror the shopping list to a Home Assistant to-do list | Readable in the HA phone app when the PC is off | M | Medium (owner's call) |
| 16 | Write events to a CalDAV calendar, one card per event | Only useful if the owner has a non-Google calendar | M | Low |
| 17 | Phone notifications feeding "tell me when" / "what did I miss?" | Messages from WhatsApp etc. | M-L | High (owner's call) |
| 18 | "Text Mum I'm late" as a ready SMS draft in the Messages app | Small step over the phone's existing Share button | S | None |

## Details

Each item: what it is, source and licence, whether it is local, where it
plugs in, and how it fits the permission model (ARCHITECTURE §3, §4, §12).

**1. Weather from Home Assistant.** HA can hold a weather device (many
installs have "Forecast Home" from met.no - I did not check that HA's setup
still adds it by default). HA's `weather.get_forecasts` service returns the
forecast when called with `?return_response` (`api/__init__.py:409-453`,
`weather/services.yaml:19`, read; Apache-2.0). *Local?* Jarvis talks only to
HA on the owner's network. HA fetches the forecast itself, as it already does,
so Jarvis opens no new connection. *Plugs in:* a new read-only plan in
`backend/jarvis_home.py` beside `plan_states` (line 236). It must allow only
this one service, never go through `home_control`. The briefing's
`"weather": not_available` (`jarvis_briefing.py:338`) and a fast-path "what's
the weather?" answer in `jarvis_quick.py`. *Fit:* a read at tier `auto` like
`home_read`, and the forecast is outside text like calendar titles. Update
`jarvis_reach.py`'s HA row. *Value:* high (a daily question). **S.**

**2. "Also on my phone" (alarm, calendar event, text draft).** Android's
`AlarmClock.ACTION_SET_ALARM` opens the phone's own Clock app with the time
filled in. It needs only the install-time `SET_ALARM` permission, and the
owner confirms in that app **(summary; standard Android API)**.
`CalendarContract` `ACTION_INSERT` opens the phone's calendar pre-filled and
needs no permission; saving to a Google account there needs no Google sign-in
from Jarvis. `smsto:` with a body does the same for a text (idea 18). *Local?*
Yes, the phone's own apps. *Plugs in:* a button on an alarm in the phone's
Coming up (`ScheduleNotifier.kt`, Mind → Coming up), and on an event answer.
It builds on the creativity audit's "Add to Google Calendar by the owner's
own tap" (usefulness #12, the desktop half). *Fit:* the owner's tap in their
own app is the approval, so there is no card. The PC stays the clock
(JARVIS-API §21.1); this only makes a copy the owner asked for. It closes
§21.7's gap "the phone hears of a job going off only while connected", for
alarms. Watch for: two alarms ringing if both are kept - the button text
should say so. **S.**

**3. Instant email watch, and "hasn't replied".** Today `jarvis_tellme.py`
signs in every 5 minutes (header, lines 37-41). IMAP IDLE keeps **one**
connection open and the server says when mail arrives. Mail providers prefer
that to repeated sign-ins. CPython's `IMAP4.idle()` is new in **3.14**
(`imaplib.rst`, "versionadded:: 3.14", read), but the owner installs **3.12**
(`docs/INSTALL.md:53`). So use `IMAPClient` (PyPI 4.1.0, BSD, Python ≥3.8),
or write the IDLE loop by hand. The second part: "tell me if Priya hasn't
replied by Friday" is the same From-line match with a deadline. It notifies
when **no** match arrives, like Open WebUI's timers that cancel when you
reply first. *Plugs in:* `jarvis_tellme.py` (the email source, line 249 on)
and its own check (`register_kind(check=)`). *Fit:* the same egress row (the
owner's IMAP server, `BODY.PEEK`, From line only), the same ONE setup card,
and a match only notifies. **S-M.**

**4. Drafts into the owner's Drafts folder.** IMAP `APPEND` puts a message into
`Drafts` (Gmail: `[Gmail]/Drafts`). The owner finishes and sends it from any
mail app. Nothing leaves their account. Not built today: `grep` finds no
APPEND in `jarvis_email.py` or `jarvis_email_send.py`. *Plugs in:* a
`save_draft` beside `jarvis_email_send.plan/describe/run`. It reuses the
same account, the same address checks, and the rule that only the local model
writes it. *Fit:* this is the owner's call. My suggestion copies the
note-writing rule (CLAUDE.md 2026-09-24): no card in a plain turn, **a card
after outside text** (for example a planted instruction asking for a draft to
a stranger). It needs a new line in §4's "owner's own accounts" row: writes
one draft to the owner's own mail server. **S-M.**

**5. Documents to text, read in slices.** Microsoft's **MarkItDown** (MIT, PyPI
0.1.8, Python 3.10-3.14) turns PDF, Word, PowerPoint, Excel and Outlook
`.msg` files into Markdown on the PC (README, read). **Docling** (MIT, PyPI
2.130.0) does the same with better tables, but it is heavier because it uses
AI models. Today the wiki's `Sources` folder takes only `.md` and `.txt`
(`jarvis_wiki.py:15`), and notes search reads only `*.md` (`jarvis_notes.py:89`).
*Plugs in:* convert dropped files into a text copy under the vault's
`Jarvis Wiki/Sources`. Give the model Open WebUI 0.11's pattern: search, then
read one slice (with a line cap), instead of pasting whole files. That fits a
16k context now and gets better on the second card. *Fit:* read-only, and the
text is outside text (`jarvis_agent.py:2266` already says files and notes
are). Never learned as facts. Do **not** turn on MarkItDown's optional LLM
picture captions or Azure Document Intelligence (rule 1). It is the first
step of `future.md` idea 1, not a new idea. **S-M.**

**6. Contacts from a `.vcf` file.** The owner exports their contacts (Google
Contacts → Export → vCard) into a folder on the PC. Jarvis reads the file and
opens no network connection. Google's CardDAV would need a Google sign-in, so
a file is simpler. *Plugs in:* the names layer (`jarvis_entities.py`) links
"Priya" to an address. The `send_email` card (`jarvis_email_send.describe`)
adds one line: "in your contacts" or "**not** in your contacts". That is
`rules.md` I-8's "never written to this address" warning, which is not built
(no match in `jarvis_email_send.py`). *Fit:* a tightening only. Addresses are
private: kept local, never learned as facts. The desktop only, like other deep
data (§8 "One-sided on purpose" gets a row). **S-M.**

**7. Media control on this PC.** Windows' "global media controls" (the
`GlobalSystemMediaTransportControlsSessionManager` API) report what is playing
in Spotify, a browser and other players, and can pause, play and skip. The
desktop's `windows` 0.61 crate is already a dependency (`Cargo.toml:99`), and
its `Media_Control` feature exists (checked in the crate's `Cargo.toml`). For
the phone and voice to use it too, the backend can call it via
`winrt-Windows.Media.Control` (PyPI 3.2.1, MIT). *Plugs in:* a fast-path
sentence in `jarvis_quick.py` ("pause", "next song", "what's playing") and a
backend route that both apps call (parity). *Fit:* local and easy to undo. The
owner decides whether play, pause and next run without a card, like "Lights,
plugs and fans without a card" (JARVIS-API §33) - question 1. It builds on the
"media keys" item that the earlier audits queued. **S-M.**

**8. "Why did that happen?"** HA's `/api/logbook` rows carry `context_entity_id`,
`context_event_type`, `context_service` and `context_name`
(`logbook/const.py:24-33`, `logbook/rest_api.py:38`, read). HA 2026.9's
Activity dialog is built on this kind of chain. *Plugs in:* a read-only
`plan_logbook(entity, hours)` in `jarvis_home.py`, and a tool the model can
call. *Fit:* tier `auto` read, outside text, and only the named device. **S.**

**9. GitHub: tell me when CI or a release is done.** Jarvis already keeps a
GitHub token (`JARVIS_GITHUB_TOKEN`, `jarvis_research.py:68`) and a GitHub row
in "What Jarvis can reach" (`jarvis_reach.py:564`). A new `tell me when`
source would check one named repo's latest workflow run or release. A
fine-grained token that can only read that one repo is enough. *Fit:* the key
goes only to `api.github.com` (rule 3, 2026-09-17). There is ONE setup card
and a match only notifies. The words come from the owner's own ("The phone app
build finished"), never from commit text. GitHub's official MCP server (MIT)
has a `--read-only` mode and toolsets (README, read). It is a fallback for the
MCP bridge, not needed for this. OpenClaw's new GitHub reader is public-only
and read-only, the same shape. **S-M.**

**10. HA's exposed devices as Jarvis's list.** HA's MCP server (`/api/mcp`,
stateless Streamable HTTP, Apache-2.0) offers only the devices the owner
exposed to Assist, plus a live snapshot of them (`mcp_server/server.py`,
docs source, read). HA's websocket list of exposed devices needs an admin
token (`exposed_entities.py:396-463`, `require_admin`). *Plugs in:*
`jarvis_home.py` reads that list to decide which devices the model may even
name. This is the first real use of the queued MCP bridge, with nothing but
`urllib` (the reason `jarvis_home.py:7-12` gives for avoiding MCP
dependencies still holds). *Fit:* Jarvis only reads the list. Acting stays
`plan_service` with its cards, **never** HA's own MCP tools, which act with no
card. It uses the home network URL only. HA's docs suggest Nabu Casa or a
public URL for remote AI clients, which is rule 2 (see Not for Jarvis). **S-M.**

**11. Obsidian CLI, allow-listed.** `obsidian daily:path` asks Obsidian itself
where today's note is, which ends the "date formats we cannot compute" refusal
(ARCHITECTURE §10, first "Still missing" item). `obsidian tasks daily todo`
lists open tasks. The CLI also has `eval` (runs JavaScript) and plugin
commands, so Jarvis must call only a fixed list of read commands, with fixed
arguments. It needs the app open, so fall back to today's file rules when it
is not. *Plugs in:* `jarvis_note_capture.py` (the daily-note path) and
`jarvis_notes.py`. **S.**

**12. Logseq database graphs.** A graph in the new database version is SQLite,
so Jarvis's file append (`jarvis_note_capture.py:56-61`) would not show up in
it. First: detect such a graph and say so plainly (**S**). Later, its local
MCP server (`127.0.0.1:12315/mcp`, bearer token) has a "pretend" mode. That
is exactly Jarvis's `plan()`: show the dry run on the card, then run it
(**M**, after the MCP bridge).

**13. Android 16 Live Updates.** A promoted ongoing notification keeps a timer
or focus countdown on the lock screen and in the status bar chip. It needs
the install-time `POST_PROMOTED_NOTIFICATIONS` permission and
`setRequestPromotedOngoing` **(summary, developer.android.com)**.
`compileSdk = 36` already (`jarvis-client/app/build.gradle.kts:73`). Phones below Android 16
keep today's notification. *Plugs in:* `ScheduleNotifier.kt`, and focus
sessions. The owner's phone model and Android version are not known here.
**S.**

**14. winget, "what needs updating?".** `Get-WinGetPackage` with
`IsUpdateAvailable` (the Microsoft.WinGet.Client module) lists apps with an
update available **(summary)**. There are known cases where it disagrees with
`winget upgrade` (winget-cli issues #5540, #5968). Listing contacts winget's
sources, so it is a **new way out of the PC**: it needs a §4 row and a
`jarvis_reach.py` row. Limit it to `--source winget` (I have not checked what
that source sends). Updating installs software: one card per package, plus
Windows Hello as a risky approval. Never an "update all". **S** (list) / **M**
(update).

**15. Shopping list mirrored to HA.** HA's `todo.add_item` and `todo.get_items`
(`todo/services.yaml`, read) would put the named list where the HA phone app
can read it while the PC is off. That was a later question from the
creativity audit. It writes to HA, so it is the owner's call: a setting that
is ON through one card, and each add without a card (like lights), or a card
each time. **M.**

**16. CalDAV write.** The Python `caldav` library (PyPI 3.3.1, licence
"GPL-3.0-or-later OR Apache-2.0"; pick Apache) can save one event to a CalDAV
server. It needs one card per event showing the exact title, time and
calendar. Google's CalDAV needs Google sign-in, and the owner reads Google
through the private link, which is read-only. So this matters only if the
owner has another calendar. Idea 2 covers Google. **M.**

**17. Phone notifications.** A `NotificationListenerService` would let "tell
me when" hear "WhatsApp from Priya". The costs, plainly: Android 13+ blocks
this for sideloaded apps until the owner taps "Allow restricted settings" in
the app's info page **(summary; whether an adb install counts as sideloaded
is not verified)**. Android 15 hides one-time codes from such apps
**(summary)**. Every message from every app would flow to the PC as outside
text. The owner's call. If built: only the sender name and app are sent,
matched on the phone, never the message text. **M-L.**

**18. SMS draft.** `smsto:` with the text filled in opens Messages. The
owner picks the person and presses send. The phone's answer already has a
Share button (`HomeScreen.kt:2033`), so this saves one tap. **S.**

**Personal knowledge graph:** nothing new to add. `MEMORY-RESEARCH-2026-09-26.md`
covers it, and the entity layer exists (`jarvis_entities.py`, desktop-only by
rule). One new fact for that list: **KuzuDB, an embedded graph database, is
archived** (its README says "We are archiving the KuzuDB project"), so it
should not be adopted.

## Not for Jarvis

| Seen in | What | Why not |
|---|---|---|
| OpenClaw "Unreleased" | Cross-provider messaging allowed by default | Loosening a default quietly; Jarvis's lanes are named and off until set (§4) |
| OpenClaw | Heartbeat model turns every 30 min; "Always allow" for automations | A standing grant (invariant 3); runs of the one scheduler only read |
| OpenClaw 2026.9.6 | Live meeting notes from Meet/Teams/Zoom | Records other people; its notes use the configured (often cloud) model; Jarvis's voice takes ≤30 s clips (`jarvis_speech.py`, per usefulness.md). Not now |
| HA MCP docs | Reaching HA from an AI client through Nabu Casa or a public URL | Rule 2. Jarvis uses the home network URL only |
| HA 2026.9 | Cloud speech-to-text (Soniox) | Rule 1; speech-to-text stays on the PC |
| Open WebUI 0.11 | "Open" chat share links without sign-in | Rule 2 |
| Obsidian CLI | `eval`, plugin and developer commands | Runs arbitrary code; only a fixed read list may be called |
| MarkItDown | LLM picture captions, Azure Document Intelligence | Sends documents out (rule 1) |
| Android | Reading SMS; sending SMS from the PC without the owner's tap | Reading SMS hands every one-time code to the PC; sending is covered by idea 18 with the owner's own tap |
| n8n (Sustainable Use License) | A second automation engine | Duplicates the one scheduler (§12) and each workflow is an unnamed way out of the PC |
| JMAP | Email, contacts, calendars over JMAP (Stalwart, Fastmail) | Not a rule break. Gmail does not speak it; revisit only if the owner moves mail provider |
| Graph DB servers | Graphiti (needs Neo4j), KuzuDB (archived) | See `MEMORY-RESEARCH-2026-09-26.md` §7 |
| Ollama (summary) | Running models inside ChatGPT Desktop | A cloud app; nothing for Jarvis |

## Questions for the owner

1. Jarvis could pause, play and skip music or videos on your PC. Should it do
   that without an approval card, like the lights setting?
   - **Yes, as a setting, off until you turn it on** (recommended)
   - **Keep a card each time**
2. Jarvis could save an email draft into your Drafts folder (nothing is sent).
   When should that ask first?
   - **Only after it has read outside text, like notes** (recommended)
   - **Always a card**

## Sources

Read (raw files):
- HA 2026.9 notes: https://github.com/home-assistant/home-assistant.io/blob/current/source/_posts/2026-09-02-release-20269.markdown ; 2026.7: `.../2026-07-01-release-20267.markdown`
- HA MCP server docs: https://github.com/home-assistant/home-assistant.io/blob/current/source/_integrations/mcp_server.markdown
- HA core (Apache-2.0): https://github.com/home-assistant/core/tree/dev/homeassistant/components - `api/__init__.py`, `logbook/const.py`, `logbook/rest_api.py`, `weather/services.yaml`, `todo/services.yaml`, `homeassistant/exposed_entities.py`, `mcp_server/server.py`
- Open WebUI changelog: https://github.com/open-webui/open-webui/blob/main/CHANGELOG.md
- OpenClaw changelogs (MIT): https://github.com/openclaw/openclaw/tree/main/CHANGELOG (2026.9.2, 9.4, 9.5, 9.6, Unreleased)
- Logseq DB version: https://github.com/logseq/docs/blob/master/db-version.md
- Obsidian CLI skill: https://github.com/kepano/obsidian-skills/blob/main/skills/obsidian-cli/SKILL.md
- GitHub MCP server (MIT): https://github.com/github/github-mcp-server
- CPython 3.14 imaplib: https://github.com/python/cpython/blob/3.14/Doc/library/imaplib.rst
- MarkItDown (MIT): https://github.com/microsoft/markitdown ; Docling (MIT): https://github.com/docling-project/docling
- caldav (GPL-3/Apache-2.0): https://github.com/python-caldav/caldav ; Radicale, Tasks.org, DAVx5 (all GPL-3, licences read; not recommended above)
- KuzuDB archived notice: https://github.com/kuzudb/kuzu ; Graphiti (Apache-2.0): https://github.com/getzep/graphiti
- PyPI JSON for winrt-Windows.Media.Control, markitdown, docling, caldav, IMAPClient

Search summaries only:
- OpenClaw releases index: https://github.com/openclaw/openclaw/releases
- Obsidian CLI: https://obsidian.md/help/cli ; https://obsidian.md/changelog/2026-02-27-desktop-v1.12.4/
- Logseq split: https://discuss.logseq.com/t/logseq-og-markdown-vs-logseq-db-sqlite/34608
- Android restricted settings: https://www.androidauthority.com/android-15-restricted-settings-sideloading-3481098/
- Android 15 OTP redaction: https://www.androidauthority.com/android-15-two-factor-authentication-codes-3492585/
- Android 16 Live Updates: https://developer.android.com/develop/ui/views/notifications/live-update
- WinGet PowerShell: https://github.com/microsoft/winget-cli/blob/master/src/PowerShell/Help/Microsoft.WinGet.Client/Get-WinGetPackage.md ; issue https://github.com/microsoft/winget-cli/issues/5968
- PowerToys Command Palette: https://learn.microsoft.com/en-us/windows/powertoys/command-palette/extension-development
- MCP 2026-07-28 RC: https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/
- JMAP in Stalwart: https://stalw.art/blog/jmap-collaboration/
- Ollama notes: https://releasebot.io/updates/ollama

Repo files checked: CLAUDE.md; docs/ARCHITECTURE.md §4, §8, §10-12;
docs/JARVIS-API.md contents, §21.1, §21.7, §33; backend `jarvis_agent.py`
(tool list, line 2266), `jarvis_home.py`, `jarvis_tellme.py`,
`jarvis_email.py`, `jarvis_email_send.py`, `jarvis_briefing.py:338`,
`jarvis_wiki.py:15`, `jarvis_notes.py`, `jarvis_note_capture.py`,
`jarvis_reach.py`, `jarvis_research.py`, `jarvis_schedule.py`;
`jarvis-desktop/src-tauri/Cargo.toml`; `jarvis-client` manifest,
`app/build.gradle.kts`, `HomeScreen.kt`, `ScheduleNotifier.kt`.
