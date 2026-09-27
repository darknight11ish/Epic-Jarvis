# Security, privacy and dependencies audit - 2026-09-27

One of the three combined passes in `docs/handoff-2026-09-27/HANDOFF.md` §4.
Branch `claude/jarvis-continuation-03kls1`, starting at `c92f90ed`. Scope: the
five rules checked against code, every egress lane added this session, the
DNS-rebinding guard, the backup file, the Credential Manager accounts, the
Python / Rust / npm / Android dependencies and their licences, and the
hash-locked install. It builds on `docs/DEPS-TESTS-CI-AUDIT-2026-09-26.md`
and does not repeat what that audit found (its B-1 to B-24 stand).

Every finding says **CONFIRMED** (checked against the file, and where it says
so, reproduced with a script) or **PLAUSIBLE** (reasoned, with what is
missing). `file:line` refers to this commit, after the fixes below.

## In plain words (for the owner)

1. **I found no break of the five rules.** Nothing new sends your email,
   files, passwords or memories anywhere; nothing opens a public tunnel; no
   new card can be approved without a person; nothing uses Google Play.
2. **The Python packages are still NOT installed from the locked list.**
   `apply-patches.ps1` installs from the loose list (`requirements.txt`),
   and pip keeps any package you already have. So the green "0 known
   security problems" check describes the locked list, not your PC. What is
   actually on your PC has never been checked. (Question 1 below.)
3. **A real gap in the news-feed and "tell me when this page changes"
   safety check, now fixed.** The check looked up an address's number,
   then the download looked it up a second time. A web address that
   changes its answer in that split second could make Jarvis download from
   your own PC or home network. The download now uses the very number it
   checked. Also fixed: two smaller ways around the same check and around
   the feed reader's "no tricks in the file" rule.
4. **"What Jarvis can reach" is missing four things.** It says "anything
   not on this list stays on this PC", but it does not list news feeds,
   watched web pages, "Check for tool updates", or the backup folder. Not
   fixed here: it needs a row in both apps. It should be the next small
   build.
5. **"Check for tool updates" told PyPI, crates.io and GitHub your GitHub
   name** on every check, although its card says "never anything about
   you". Fixed. Its suggested commands (`pip install --upgrade ...`) skip
   the locked list and its 7-day wait. (Question 2 below.)
6. **Dependencies: no known security problem, no licence problem.** 77
   locked Python packages: 0 advisories. Rust: 0 advisories (the rustls one
   from yesterday's audit is gone). The desktop's npm tools: 0. Every
   licence is permissive or file-level (MPL-2.0); nothing GPL.
7. **Fixed directly, with tests:** the rebinding gap, the two smaller
   check gaps, the lock check that ignored version numbers, the tool
   updater's User-Agent, a restore that could write outside its folder,
   and five untrue sentences in the docs. **Waiting for you:** two short
   questions at the end.

## Findings

| # | Severity | Status | Where | One line | Fixed here? |
|---|---|---|---|---|---|
| 1 | Medium | CONFIRMED, reproduced | `jarvis_local_http.py` (`private_fetch_problem`, then urllib's own connect) | Check and connection did two separate DNS lookups: fast DNS rebinding reached this PC | **Yes** (`public_urlopen`) |
| 2 | Medium | CONFIRMED | `jarvis_reach.py:782` `KINDS`, `:75` `EVERYTHING_ELSE` | "What Jarvis can reach" omits news feeds, page watches, tool-update checks and the backup folder, while saying anything not listed stays on this PC | No - a small build, both apps |
| 3 | Medium (practical) | CONFIRMED | `scripts/apply-patches.ps1:1708,1723`; `requirements.lock:21`; `ci.yml:141` | The install uses `requirements.txt`, not the lock; pip keeps what is installed; the advisory check does not describe the PC | No - owner's call (Question 1) |
| 4 | Low-medium | CONFIRMED, reproduced | `tools/check_python_advisories.py` `check_lock` | The lock check compared NAMES only: `requirements.txt` could ask `markitdown==0.1.9` while the lock pinned 0.1.8, and it passed | **Yes** (`spec_problems`) |
| 5 | Low-medium | CONFIRMED | `jarvis_tool_updates.py:552` | The report tells the owner to run `pip install --upgrade <name>`: newest release at once, no hash, no 7-day wait, and `apply-patches.ps1` may undo it | No - owner's call (Question 2) |
| 6 | Low | CONFIRMED, reproduced | `jarvis_local_http.py:269` `_resolved_addresses` | A DNS answer `::ffff:127.0.0.1` passed; the same address typed literally was refused | **Yes** |
| 7 | Low | CONFIRMED, reproduced | `jarvis_news.py:283` `_declares_doctype` | The DOCTYPE/ENTITY refusal was a byte search; a UTF-16 feed slipped past it and ElementTree expanded its entities | **Yes** |
| 8 | Low | CONFIRMED | `jarvis_tool_updates.py` `_PYPI_UA` etc. | The User-Agent carried `github.com/darknight11ish/Epic-Jarvis` to three services on every check; the card says "never ... anything about you" | **Yes** |
| 9 | Low | CONFIRMED, reproduced | `jarvis_backup.py:960` `_apply_restore` | Restore joined any name in the archive: `db/../x` wrote outside the settings folder | **Yes** (`_inside`) - see "Overlap" |
| 10 | Low | CONFIRMED | `jarvis_tool_updates.py:336-342`, `:823` | Plain `urlopen`: redirects followed, system proxy used; routes take any paired device's token ("desktop only" is only the apps' choice) | Docs corrected; code left (nothing secret is sent) |
| 11 | Info | CONFIRMED | `jarvis_news.py` `_decide`, `jarvis_tool_updates.py:714` | Their cards' `leaves_this_pc` said False, though approving them is what makes Jarvis go online | **Yes** (True, matching `jarvis_tellme`) |
| 12 | Info | CONFIRMED | `jarvis_news.py:583`, `jarvis_tellme.py:1247` | Adding a feed or page watch does one DNS lookup of the typed name BEFORE its card | Docs now say so |
| 13 | Info | PLAUSIBLE | `jarvis_mcp.py:67` | A plug-in runs as the owner, so it can read every Credential Manager entry (the IMAP password, keys, the pairing token); the docs say "files and the internet" only | No - wording suggestion |
| 14 | Info | CONFIRMED | `jarvis_backup.py` `restore_card` | Restore brings back old approvals too (plug-ins, loosened "What asks first", folders); the card says only "settings" | No - wording suggestion |
| 15 | Info | CONFIRMED | `backend/README.md`, `jarvis_backup.py` docstring | "This repository hash-locks every dependency" - true of the lock file, not of the install | **Yes** |
| 16 | Info | CONFIRMED | `jarvis_local_http.py` `_PRIVATE_NETS` | NAT64 (64:ff9b::/96), 6to4 (2002::/16) and multicast are not refused | No - see details |

---

### 1. DNS rebinding between the check and the connection (Medium, fixed)

**Evidence.** `jarvis_news.read_feed` calls `LH.private_fetch_problem(url)`
(`jarvis_news.py:381`), which does `socket.getaddrinfo` itself; then
`_default_fetch` opened the URL by NAME through `LH.urlopen`, and
`http.client` looked the name up again to connect. `jarvis_tellme._look_page`
(`:967`) then `_default_page_fetch` had the same shape. Nothing tied the
second lookup to the first.

**Reproduced** (a stand-in resolver answering 93.184.215.14 on the first
lookup and 127.0.0.1 on the second, and a small web server on 127.0.0.1):
`read_feed` returned `{'ok': True, 'headlines': ['FROM 127.0.0.1']}` and the
local server logged the request. A real attack needs a DNS server that
answers with a zero lifetime for a feed the owner approved; it is a blind
request (the attacker does not see the answer), but some home devices act
on a plain GET.

The design text claimed this was covered ("DNS rebinding is checked for, not
only assumed away", ARCHITECTURE §4). Checking again before every fetch
covers the slow case (the answer changes between the card and a later look),
not this one.

**Fix.** `jarvis_local_http.public_urlopen` / `public_opener`: HTTP and
HTTPS connections whose `_create_connection` is `_connect_public`
(`jarvis_local_http.py:374`) - ONE lookup, every answer refused if private
(the same `_is_private` rule), then a connection to one of exactly those
checked numbers. HTTPS still checks the certificate against the NAME
(`http.client` wraps with `server_hostname=<name>`); a real HTTPS fetch of
`https://pypi.org/rss/updates.xml` through it worked here (HTTP 200).
Redirects go through the same connections, so they are checked at connect
time too, besides the existing `_FeedRedirect`/`_PageRedirect`. No proxy
(a proxy would look the name up out of reach of the check). News and page
watches now use it (`jarvis_news.py:271`, `jarvis_tellme.py:955`).
`private_fetch_problem` stays as the early check that gives the plain
sentence. Tests: `test_local_http.py`
`t_public_urlopen_checks_the_address_it_connects_to` (http and https, with a
control showing the old path DID reach this PC),
`t_public_urlopen_connects_to_the_checked_address` (one lookup),
`t_news_and_page_watch_fetch_through_public_urlopen` (read from the source).

### 2. "What Jarvis can reach" is missing four ways out (Medium, not fixed)

**Evidence.** `jarvis_reach.py:782` `KINDS` has 18 rows (cloud model, web
search, calendar, email read/send, Home Assistant, notes, GitHub, phone push,
computer/browser/phone control, shell, plug-ins, second card, big model).
None is for news feeds (`jarvis_news`), watched pages (`jarvis_tellme`'s
`page` source), "Check for tool updates" (`jarvis_tool_updates`), or the
backup folder (which the owner's decision says may be cloud-synced). The page
ends with `EVERYTHING_ELSE = "Anything not on this list stays on this PC."`
(`:75`), and "what can you reach?" is answered from the same list
(`jarvis_quick.py`). Email drafts are covered by `draft_email` in the tools
list (`:103`).

**Why it matters.** This list exists because "a model can say anything about
itself; this list cannot" (its own docstring). Four lanes built this session
never joined it, so the list now says something untrue.

**Suggested fix** (not done here: both apps render it, and `test_reach.py`
and the phone's copy need rows): four rows - "News feeds" (on when
`news_feeds.json` lists any; goes to "the feed addresses you added"), "Web
pages you watch" (on when a page watch is active), "Check for tool updates"
(on once approved; PyPI, crates.io, GitHub; only when you press the button),
"Backups" (on when a folder is set; "a folder you chose - if a sync program
uploads it, the file is locked with your recovery code"). Also add a line to
`docs/ARCHITECTURE.md` §12's checklist: a new egress row needs a `KINDS` row.

### 3. The hash-locked install: the definitive answer (Medium in practice, owner's call)

**The answer: the install does not use the lock.**

- `scripts/apply-patches.ps1:1708` sets `$reqs = Join-Path $PatchDir
  'requirements.txt'` and `:1723` runs `pip install
  --disable-pip-version-check -r $reqs`. No `--require-hashes`, no
  `requirements.lock`. The only use of the lock in that script is step 3b
  (`:1599`), which COPIES it beside `jarvis_hud.py` for "Check for tool
  updates" to read.
- `backend/requirements.lock:21` says so itself: "NOT YET what
  scripts/apply-patches.ps1 installs from".
- CI's backend job installs four packages by name, unpinned
  (`.github/workflows/ci.yml:141`).

**What it means in practice.**
- `requirements.txt` pins only three packages (`sherpa-onnx>=1.12.26`,
  `ddgs>=9.16.0`, `markitdown[...]==0.1.8`); everything else is whatever
  PyPI serves on the day, with no hash check and no 7-day wait.
- `pip install -r` without `--upgrade` keeps a package that is already
  installed if its line allows it. So an OLD package installed long ago
  stays on the PC. Neither "the newest" nor "the locked version" describes
  the PC: it is "whatever was installed first".
- The CI job `python-advisories` (`ci.yml:458`) checks the LOCK. Its green
  result (today: 77 pinned releases, 0 advisories) says nothing about the
  PC. The PC's packages have never been checked by anyone.
- One concrete effect found: backup needs `cryptography` 44.0.0 or newer
  (Argon2id). An older one on the PC makes backing up refuse, in words, and
  never write anything unencrypted (`jarvis_backup.py` `_require_crypto`).
  It fails closed, but the docs said "already pinned at 50.0.1"; they now say
  what is really true.
- The reason the switch was not made (yesterday's audit, section "Python
  packages pinned with hashes"): installing the lock would move shared
  packages (for example `huggingface-hub`, `tokenizers`) under the optional
  better voice (f5-tts). Still true; still unmeasured on the PC.

**Also checked, the checker itself** (not trusted blindly):
- It really finds advisories: asked about known-bad versions it reported
  requests 2.31.0 (6), pdfminer-six 20250506 (4), cryptography 41.0.0 (20),
  urllib3 2.2.1 (14). Today's lock: 0.
- It checks every platform's pins, not only this machine's (correct, and the
  reason given for not using pip-audit holds).
- **It compared names only (finding 4, fixed).**
- Limits, written down: it reads PyPI's own advisory list (the PyPA
  database); an advisory only in GitHub's database is not seen. The optional
  packages (playwright, torch, speechbrain, f5-tts, soundfile) are in
  neither file and never checked.

### 4. The lock check ignored version numbers (Low-medium, fixed)

**Reproduced:** with `requirements.txt` changed to `markitdown==0.1.9` and
`sherpa-onnx>=1.14.0`, `check_lock()` returned no problem (only names were
compared). Once the install uses the lock, that disagreement would silently
install versions the requirements file forbids. **Fix:**
`requirement_specs`/`spec_problems` in `tools/check_python_advisories.py`
check every version rule against every version the lock pins for that name
(numpy has one per Python version); a rule it cannot decide (`~=`, odd
version text) is reported, never passed. Runs in CI's `python-advisories`
job and offline in `test_shipped_modules.py` (4 new checks).

### 5. Tool updates advise `pip install --upgrade` (Low-medium, owner's call)

`jarvis_tool_updates.py:552`: `"command": f"py -3 -m pip install --upgrade
{orig}"`. Running it installs the newest release at once - no hash, no 7-day
wait - which is exactly what the lock was made to stop, and for
`markitdown` (pinned `==0.1.8`) the next `apply-patches.ps1` run would put
0.1.8 back. The Rust advice (`cargo update -p <name>`) at least goes through
`Cargo.lock` and CI's `cargo deny`. See Question 2.

### 6. An IPv4-mapped DNS answer passed the private check (Low, fixed)

`_as_address` unwraps `::ffff:a.b.c.d` for a LITERAL address, but
`_resolved_addresses` built DNS answers with `ipaddress.ip_address` directly.
**Reproduced:** a DNS answer `::ffff:127.0.0.1` gave `private_fetch_problem
== ""`; the literal `[::ffff:127.0.0.1]` was refused. On Linux a connection
to that address reaches 127.0.0.1. On Windows, IPv6 sockets default to
IPv6-only, which should make such a connection fail - PLAUSIBLE, not tested
on Windows. Fixed by unwrapping in `_resolved_addresses`; test
`t_an_ipv4_mapped_dns_answer_is_judged_as_ipv4`.

### 7. The feed reader's "no DOCTYPE" rule missed UTF-16 (Low, fixed)

`parse_headlines`/`feed_title` refused `re.search(rb"<!DOCTYPE|<!ENTITY",
raw)`. A UTF-16 document spells those with a zero byte between letters.
**Reproduced:** a UTF-16 feed with `<!ENTITY a "ENTITY-EXPANDED">` returned
`['ENTITY-EXPANDED']`; nested entities expanded too. Impact is bounded:
ElementTree never fetches external entities, input is capped at 2 MB, and
expat 2.4+ limits entity blow-up (this container has expat 2.6.1; the
owner's Python was not checked). **Fix:** `_declares_doctype`
(`jarvis_news.py:283`) runs expat itself - the same parser, the same
encoding detection - and stops at the first DOCTYPE or ENTITY declaration,
before anything expands. Tests in `test_news.py` (a UTF-16 bomb refused, an
ordinary UTF-16 feed still read).

### 8. The tool updater named the owner to three services (Low, fixed)

The three User-Agents were `Jarvis-tool-update-check (local,
non-commercial, github.com/darknight11ish/Epic-Jarvis)`: the owner's GitHub
name, with their internet address, to PyPI, crates.io and GitHub on every
check. The card (`CARD`) says "never a file path, a folder name, or anything
about you"; the project's own test for the advisory checker already insists
on "a generic User-Agent, nothing of the owner's"
(`test_shipped_modules.py`). Now `Jarvis-tool-update-check/1 (local,
non-commercial)`; crates.io answered it with HTTP 200 here. Also: only the
NAME is sent (`pypi.org/pypi/<name>/json`, `crates.io/api/v1/crates/<name>`),
not the version the card and the docs said; the docs now say so (the card
text itself is unchanged - it promises more privacy than it needs to, not
less).

### 9. Restore could write outside the settings folder (Low, fixed)

`_apply_restore` joined whatever name the archive held (`conf /
name[len("db/"):]`), so `db/../x` or, on Windows, `notes/C:/...` landed
elsewhere. Only an archive that opens with a recovery code the owner types
gets this far, and `build_archive` never writes such names, so this is a
second lock rather than a reported attack. **Fix:** `_inside`
(`jarvis_backup.py:941`) refuses `..`, empty or `.` parts, a leading `/`, a
backslash or a drive letter; `db/` and `settings/` take one name only.
Skipped names are counted (`applied["skipped"]`). Test
`t_restore_never_writes_outside_its_own_folders`.

### 10. Tool updates: redirects, proxy, and who may press the button (Low, documented)

`_get_json` (`jarvis_tool_updates.py:336`) uses plain
`urllib.request.urlopen` (`:342`): it follows redirects and uses the system
proxy. Nothing secret is in the request (no key, no token), and all three
hosts are https, so this is acceptable - but ARCHITECTURE §4 did not say it;
it does now. `install` (`:823`) checks only origin and token, so any paired
device can raise the first card or, once approved, start a check; "desktop
only" is only the apps' choice (the backup routes, by contrast, use
`from_this_pc`). Low impact (it starts ~650 read-only requests); recommended
later: the same `from_this_pc` check.

### 11-16. Smaller items

- **11.** `leaves_this_pc` is recorded with each card's detail; the news-feed
  and tool-update cards said False. `jarvis_tellme`'s page card and
  `jarvis_schedule` already say True for the same shape. Now True, tested.
  (It does not decide riskiness; that comes from the gate's `_RISK` table by
  action name - checked in `tools/gen_risky_approval_cases.py`.)
- **12.** `request_add` (`jarvis_news.py:583`) and `add`
  (`jarvis_tellme.py:1247`) look the typed name up in DNS before raising the
  card, to refuse a private one early. The DNS server sees the name the owner
  typed; nothing else leaves. Documented in ARCHITECTURE §4.
- **13.** PLAUSIBLE (standard Windows behaviour, not tested here): a program
  running as the owner can read the owner's generic Credential Manager
  entries. So a plug-in (MCP) program can read the IMAP password, the search
  keys and the pairing token, even though Jarvis hands it none
  (`jarvis_child_env`). This was equally true when those lived in
  environment variables, so nothing got worse; but `jarvis_mcp.py:67` and
  ARCHITECTURE §4 say only "read files and use the internet". Suggested
  wording for its card: "It can also read the passwords and keys saved on
  this PC."
- **14.** A restore brings back the old `*.json` settings and
  `jarvis-framework.toml` - so a plug-in removed since, a "What asks first"
  loosening withdrawn since, or a folder removed since, comes back with it.
  The restore is one card plus Windows Hello, so it is the owner's own
  choice; but the card says only "settings". Suggested line: "Approvals you
  have changed since (plug-ins, what asks first, folders) go back to how they
  were then."
- **15.** Two places said "this repository hash-locks every dependency";
  corrected in `backend/README.md` and the `jarvis_backup.py` docstring.
- **16.** `_PRIVATE_NETS` does not refuse NAT64 (64:ff9b::/96), 6to4
  (2002::/16), multicast or reserved ranges. Only NAT64 on the home network
  could reach a private IPv4 that way, which is rare. Switching to Python's
  `is_global` would catch all of them but would also refuse 198.18.0.0/15,
  which some VPN/proxy programs use for every name ("fake IP" mode) - it
  would silently break every feed there. Left as is, written down.

## The five rules, checked against code

| Rule | Where it is enforced (checked today) | This session's features |
|---|---|---|
| 1. Private things stay on the local model | Cloud lanes filtered per hop (ARCHITECTURE §4); `send_email`/`draft_email` refused unless the turn's model is on this PC | News: sends only the typed address (`read_feed`, no owner data). Page watch: one GET, only a SHA-256 kept (`_default_page_fetch`). Tool updates: names only. Backup: one encrypted file written to a local folder (the owner's recorded exception). Accounts: written to Credential Manager by Rust (`account_secrets.rs`), never over HTTP. Sources/quote check: `jarvis_sources.py` imports no network module (only `urllib.parse`). MarkItDown: builtins off, only the four document converters, in a child with no secrets (`jarvis_documents.py` `_CHILD`). **Holds.** |
| 2. No public tunnel | No ngrok/cloudflared/funnel code anywhere in `backend`, `jarvis-desktop`, `jarvis-client`, `scripts` - only refusal tests (`commands.rs:5847`, `PairingScreen.kt:191`) | Nothing new opens a listener. **Holds.** |
| 3. Keys never logged, only to their service, never plain on disk | Every request carrying a key refuses redirects: `jarvis_search._RefuseRedirect` (`:869`), `jarvis_research._RefuseRedirect` (`:236`), `jarvis_calendar._RefuseRedirect`/`_FeedRedirect`; Credential Manager values registered with `jarvis_scrub` (`jarvis_token_store.resolve_secret`) | Tool updates: no key in any request (headers are User-Agent and Accept only). Backup: excludes the pairing token (`token`, not `*.json`) and every key (Credential Manager, not settings files - `jarvis_search.save_key`); the one secret inside, the chat-history key, is inside the AES-256-GCM archive. The framework file names secrets by environment-variable name only. **Holds.** |
| 4. Never auto-approve; block on a stale stream | Each new card's `_decide` refuses unless the gate answered at tier `ask` AND the configured tier is `ask` AND the outcome is `approved`: `jarvis_news._decide`, `jarvis_tool_updates._decide` (`:714`), `jarvis_backup._decide_restore` (+ `PC_ONLY_ACTIONS`, Windows Hello), page watch through `jarvis_schedule` (`vtier != "ask"` refused). Every app-side answer still goes through the desktop's `answer_approval` / the phone's `decide`; the HUD page's own approve is not in `hud_proxy.rs`'s allowed list | "Check for tool updates" remembers one yes for ever (`tool_updates.json`) - a standing consent, but only for read-only lookups with nothing of the owner's; JARVIS-API §53.1 says "the owner decided", and CLAUDE.md has no line recording it (I could not check the owner's words). **Holds.** |
| 5. Non-commercial, sideloaded | `jarvis-client/app/build.gradle.kts:284-381`: AndroidX, Kotlin, OkHttp/Okio, ONNX Runtime only; no `com.google.android.gms`, Firebase or billing anywhere in `app/src/main` | No Android dependency added this session (the gradle diffs since 2026-09-24 change versioning, signing and one packaging line only). **Holds.** |

## The new egress rows, one by one

The house pattern is a `plan()` that opens no socket and a `run()` that does.
None of these three modules uses those names; the functions that play each
part are named instead.

| Row | "Plan" (no socket) | "Run" (the socket) | Before its card? | Redirects | Sends more than claimed? |
|---|---|---|---|---|---|
| News feed | `check_feed` (syntax), `request_add` (`jarvis_news.py:568`) raises the card | `read_feed` (`:371`) -> `_default_fetch` (`:261`) | Only a DNS lookup of the typed name (item 12) | `_FeedRedirect`: checked with `private_fetch_problem`; now also at connect | No: headers are User-Agent and Accept; titles only are kept |
| Page watch | `jarvis_tellme.add` (`:1218`) -> scheduler card | `_look_page` (`:960`) -> `_default_page_fetch` | Same DNS lookup only | `_PageRedirect`, same; now also at connect | No: body hashed, never kept |
| Tool updates | `request_check` (`:747`): `approved()` and the card before anything | `run_check` -> `_get_json` (`:336`) | No socket | Followed (default opener) - acceptable, nothing secret | It sent the owner's GitHub address (fixed); it sends names, not versions |

**The DNS-rebinding guard, call sites** (read from the code, not the
docstring): `private_fetch_problem` is called at `jarvis_news.py:381`
(every `read_feed`), `:583` (add), `:253` (every redirect);
`jarvis_tellme.py:967` (every look), `:1247` (add), `:934` (every redirect).
So it WAS checked on every fetch, as claimed - but see finding 1: before
this audit the check and the connection were separate lookups.

## Dependencies and licences

**Security advisories (run today):**
- Python: `python3 tools/check_python_advisories.py` - "77 pinned
  releases ... 0 problem(s)". The checker was tested against known-bad
  versions first (section 3).
- Rust: `cargo audit` 0.22.2 (installed into the scratchpad), advisory
  database at commit `e2111519` (2026-09-25): "0 vulnerabilities", 7 allowed
  warnings (the unmaintained/unsound ones `deny.toml` already names:
  proc-macro-error, five unic-* crates, glib). rustls is 0.23.45 now, so
  yesterday's RUSTSEC-2026-0285 is gone. Its yanked-crate check failed
  (crates.io index answered 503) - not checked.
- npm (desktop build tools): `npm audit --package-lock-only` - 0.
- Android: not checkable here (Google Maven and OSV are blocked).

**Dependencies added this session** (from `git log -p` of the four
dependency files since 2026-09-24): Python `ddgs` (+ primp, lxml, click),
`markitdown[pdf,docx,xlsx,pptx]==0.1.8` (+ pdfminer.six, pdfplumber,
pypdfium2, mammoth, python-pptx, openpyxl, pandas, magika, ...),
`winrt-Windows.Media.Control` (+ winrt-runtime), `sherpa-onnx-core`,
`tzdata`; Rust: two more Windows API features for the clipboard (`Win32_System_DataExchange`, `Win32_System_Memory`), no new crate; Android and npm:
none. Each is in the lock and was in today's advisory run.

**Licences** (PyPI's own metadata for every locked release, read today):
all MIT, MIT-0, BSD, Apache-2.0, PSF or MIT-CMU, except `certifi`
(MPL-2.0) and `tqdm` (MPL-2.0 AND MIT) - file-level copyleft, used
unmodified, and not shipped by this project (pip installs them on the PC).
No GPL, LGPL or AGPL. Two metadata oddities, not problems: `fastembed` says
"Apache License" but carries an "Other/Proprietary" classifier (its
repository is Apache-2.0 - PLAUSIBLE, not re-read); `py-rust-stemmers` gives
no licence in its metadata (not checked further).

**`LICENSE` and the notices agree.** `LICENSE` is MIT, copyright
darknight11ish, and now excepts the files named in `THIRD-PARTY-NOTICES.txt`
and the phone's `NOTICES.txt` (yesterday's audit asked for that line; it is
there). Nothing added this session conflicts with a non-commercial,
darknight11ish-owned project. One gap: `THIRD-PARTY-NOTICES.txt` names the
pip-installed `ddgs` and MarkItDown in its own hand-written sections but not
`winrt-Windows.Media.Control` (MIT, added in `13d23adc`). Not a licence
obligation (it is not shipped), only consistency; not fixed here.

## Overlap with the other two passes

- `backend/jarvis_backup.py` (`_inside`, `_apply_restore`, and a docstring
  paragraph near the top) is the file most likely to be touched by the
  **setup/settings/recovery** pass. My change is confined to `_apply_restore`
  (and one new function above it) and one paragraph of the module
  docstring.
- `backend/README.md` and `docs/ARCHITECTURE.md` §4 are edited by almost
  everyone; my edits are single sentences inside the backup paragraph and
  the three egress rows.
- `tools/check_python_advisories.py` may interest the **quality** pass
  (CI/testing).

## What nobody could check

- The owner's installed Python packages (see Question 1) and Python/expat
  versions.
- Anything on Windows: the IPv4-mapped connection behaviour (item 6), the
  Credential Manager read-by-another-program claim (item 13), `cargo test`.
- Android dependency advisories and newest versions (Google Maven, OSV
  blocked).
- The owner's `jarvis_gate.py`: how it uses `leaves_this_pc` (nothing in
  this repository reads it back) and its `_RISK` entry for
  `check_tool_updates`.
- crates.io's written User-Agent policy (its page did not render here); the
  new User-Agent was only tried once (HTTP 200).
- Whether the owner actually chose "one card, ever" for tool updates:
  CLAUDE.md does not record it.

## Questions for the owner

Your Python packages are installed from a loose list, so nobody knows exactly
what is on your PC. A one-line check (it installs nothing) would tell us
whether the safe, locked list can be switched on without upsetting the
better voice.

- **Run the check and send me the two files** (recommended) - the line is in
  `docs/DEPS-TESTS-CI-AUDIT-2026-09-26.md`, "The plan, in order", step 1.
- **Leave it for now.**

"Check for tool updates" tells you to type `pip install --upgrade <name>`.
That skips the locked list and its one-week safety wait.

- **Show "update the locked list" instead** (recommended) - one command that
  remakes the list, then the normal install.
- **Keep the upgrade commands.**

## Verification

- `cd backend && python3 run_suites.py`: 128 passed, 0 failed, 19 skipped
  (need the owner's files).
- `python3 tools/build_patch_history.py --check`: up to date (its existing
  note about `wellbeing.patch` at `31ad726` is unchanged).
- `python3 tools/check_parity.py`: "No undecided drift."
- `python3 tools/check_python_advisories.py`: 77 pinned releases, every
  requirement locked at a version `requirements.txt` allows, 0 advisories.
- No Rust, desktop JavaScript or Android file was changed.
