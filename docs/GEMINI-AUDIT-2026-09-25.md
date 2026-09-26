# Gemini audit of everything since the last one (2026-09-25)

The last outside audit closed on **2026-09-20** (commit `093caee`, "Fix seven
real findings from a Gemini audit", PR #10). Since then about 510 commits
landed: roughly 700 files added or changed. This is the package for a fresh,
**blind** outside read of all of it - blind meaning the prompt does not say
what earlier audits found, because a reviewer handed a list tends to confirm
it instead of finding the next thing (`docs/GEMINI-AUDIT.md` explains).

## The six files

Each is one Markdown file holding every added or changed source file of one
part of Jarvis, whole, with a list at the top of what is in it and of what
changed but was left out (tests, generated number files, old patch copies)
and why.

| session | file | what | size |
|---|---|---|---|
| 1a | `jarvis-audit-1a-backend-safety.md` | the agent loop, the approval gate, memory and learning, the sensitive-topic check, the patches, the installer | ~390k tokens |
| 1b | `jarvis-audit-1b-backend-abilities.md` | voice, web search, timers and the scheduler, the briefing, calendar, email, notes, graphics-card lanes, computer control | ~340k tokens |
| 2 | `jarvis-audit-2-desktop-rust.md` | the desktop app's Rust | ~270k tokens |
| 3 | `jarvis-audit-3-desktop-web.md` | the desktop app's windows (JavaScript, HTML) | ~380k tokens |
| 4a | `jarvis-audit-4a-phone-core.md` | the phone's network, runtime, security, services, build | ~300k tokens |
| 4b | `jarvis-audit-4b-phone-screens.md` | the phone's screens, face and voice | ~330k tokens |

**If you only run one, run 1a** - it is where a mistake would break one of
the five rules.

## Steps, one at a time

1. Make the six files on your PC (after `git pull`). In PowerShell:

   ```powershell
   cd "$env:USERPROFILE\Epic-Jarvis"
   ```

   ```powershell
   py -3 tools\gen_gemini_bundles.py
   ```

   ```powershell
   explorer "$env:USERPROFILE\jarvis-gemini-audit"
   ```

   The six files are in that folder (`C:\Users\pcadmin\jarvis-gemini-audit`).

2. Open https://gemini.google.com, choose the strongest model offered, and
   start a **new chat for each session** - never two files in one chat.
3. Attach that session's file, and also `docs\ARCHITECTURE.md` from the
   repository folder (the permission model the code is supposed to follow).
4. Paste the prompt below, changing only the first line to the session's
   name.
5. Save each answer (copy it into a text file) and send them to Claude.
   Every finding is checked against the real source before anything is
   changed - earlier Gemini passes had real findings and some that were
   wrong, and both kinds have been handled that way before.

---

## The prompt (paste everything between the lines)

---

SESSION: 1a (change this line to the session you attached: 1a, 1b, 2, 3, 4a or 4b)

You are auditing part of "Jarvis", a personal, non-commercial, local-first
assistant: a Python backend on the owner's Windows 11 PC with a local 8B model
in Ollama, a Tauri 2 desktop app (Rust + JavaScript), and an Android app
(Kotlin, Jetpack Compose) that reaches the PC over Tailscale or NordVPN
Meshnet. The backend is delivered as patches against a program that is not
in this repository, plus whole modules this repository ships; a PowerShell
script (`apply-patches.ps1`, run on Windows PowerShell **5.1**) applies them.

The attached bundle holds every source file of this part that was added or
changed in the last five days, whole. `ARCHITECTURE.md` describes the
permission model the code must follow. Be adversarial, specific and
unsparing. I would much rather be told something is broken than have it
smoothed over, and "looks fine" about a file you did not actually read is
worse than saying you skipped it.

### The five rules that must not be broken - check these first

For each, say whether THIS code enforces it, citing file and line, not
whether a comment claims it does.

1. Anything touching email, files, credentials or stored memory stays on the
   local model. Nothing sends it anywhere else.
2. Never a public tunnel (no ngrok, Cloudflare Tunnel, Tailscale Funnel,
   "share my Jarvis").
3. API keys (web search keys, a private calendar link, service passwords,
   the pairing token) are never logged, sent only to the one service they
   authenticate against, and never written to disk in plain text.
4. Nothing is ever approved automatically; acting is blocked when the event
   stream is stale.
5. Non-commercial, sideloaded, never on a store.

### Also required by design

- One approval card per action; never a way to approve in bulk or to clear a
  rush latch. A card's "no" must not quietly become a permanent rule unless
  the code says so on purpose.
- Text from outside (web pages, search results, emails, calendar entries,
  file contents, tool output, pasted or shared text) must never be able to
  make Jarvis act, raise its own permissions, or be saved as a fact about the
  owner. Facts are learned only from the owner's own words.
- Settings that show more or trust more raise a card to turn on; turning them
  off is immediate.
- A timer or one-time reminder needs no card; anything that repeats asks once.
- Web search: no silent switch to another provider when the chosen one is
  down; a card showing the exact search words when the conversation has read
  private things.
- Every request from the apps sends `X-Jarvis-Client: hud`; the token is never
  logged.

### What to look for

Bugs that change behaviour, in this order: broken rules above; security
(injection, path traversal, secrets leaking into logs/errors/events/UI,
redirects carrying credentials, requests going through a proxy they should
not, unbounded reads); data loss or corruption (SQLite, files, migrations,
encryption); concurrency (threads, locks, races between a card being
answered and the thing it approves); error paths that crash, hang or
silently do the wrong thing; time and time-zone handling; resource leaks;
and, for the PowerShell script, anything that fails on Windows PowerShell 5.1
specifically (e.g. `??`, `?.`, ternaries) or dies because
`$ErrorActionPreference = 'Stop'` meets a native program writing to stderr.
For Kotlin in session 4a/4b: this code is compiled only by CI, so also flag
anything that would not compile. Skip style, naming and formatting.

### How to answer

A numbered list, most serious first. For each finding:

- **Severity**: critical / high / medium / low.
- **Where**: file path and line (or function).
- **Evidence**: quote the exact line(s) of code.
- **What goes wrong**: a concrete sequence of events, in plain words.
- **Fix**: the smallest change that fixes it.
- **Confidence**: certain / likely / possible - and what you did not check.

Then two short lists: **files you read fully**, and **files you skimmed or
skipped**. Do not report something you inferred from a file name or a
comment. If you find nothing serious in an area, say so plainly.

---

## After the answers come back

Send them to Claude as they are. They will be treated as reports, not facts:
each is checked against the file and line it cites, fixed if real (with a
test that fails first), and answered with the reason if not. The results go
in a short write-up, like the earlier rounds (`docs/GEMINI-AUDIT.md`).

To make a fresh set later (after more work lands), run step 1 again; it
always starts from the last outside audit. After the fixes from this round
land, the starting point in `tools/gen_gemini_bundles.py` (`LAST_AUDIT`)
moves to that commit.
