# Gemini audit of everything since the last one (2026-09-28)

**Where to start from.** The last outside audit that was run AND closed is
commit `093caeec`, 2026-09-20 ("Fix seven real findings from a Gemini
audit, verified against source first (#10)"). The 2026-09-25 package
(`docs/GEMINI-AUDIT-2026-09-25.md`) was only partly run: three of its
findings were checked and fixed on 2026-09-26 (`79526e37`, `c78a04e2`,
`9cc21cae`), but no answer was ever written down for the rest, so it cannot
count as closed. The 2026-09-28 Gemini rounds on the GitHub-repos branch
reviewed a list of outside projects, not Jarvis's code. So this package
covers everything after `093caeec`: **1,090 commits**, including all five
branches not yet merged (details in `docs/audit-2026-09-28/gemini-baseline.md`).

The prompt is **blind** on purpose: it does not say what the 2026-09-28
Claude audits found, because a reviewer handed a list tends to confirm it
instead of finding the next thing (`docs/GEMINI-AUDIT.md` explains).

**Model:** the owner asked for "Gemini 3.8 Flash" with extended thinking.
Claude has not checked that model's name or how much it can read at once.
The files are cut to at most about 400k tokens each (the size
`docs/GEMINI-AUDIT.md` found a model still reads carefully); if the model
refuses a file as too big, run the tool again with a smaller `--budget`
(below) - no other change is needed.

## The fourteen files

Each is one Markdown file holding every added or changed source file of one
part of Jarvis, whole, with a list at the top of what is in it and of what
changed but was left out (tests, generated files, old patch copies) and why.
A part too big for one file is split into "part 1 of N" files; give each
part its own chat, with the same prompt.

| session | file | what |
|---|---|---|
| 1a (2 parts) | `jarvis-audit-1a-backend-safety-part…` | the agent loop, the approval gate and what asks first, memory and learning, the sensitive and private-text checks, the token, the plan card, backups, the patches and the install script |
| 1b (3 parts) | `jarvis-audit-1b-backend-abilities-part…` | voice, Jarvis Live, web search, timers, briefing and Today, calendar, email, notes, chatbots, projects and goals, phone notifications, faces' voices, the graphics-card lanes |
| 2 (2 parts) | `jarvis-audit-2-desktop-rust-part…` | the desktop app's Rust |
| 3 (2 parts) | `jarvis-audit-3-desktop-web-part…` | the desktop app's windows (JavaScript, HTML, CSS, shaders) |
| 4a (2 parts) | `jarvis-audit-4a-phone-core-part…` | the phone's network, runtime, security, services, build |
| 4b (2 parts) | `jarvis-audit-4b-phone-screens-part…` | the phone's screens, faces and voice |
| 5 | `jarvis-audit-5-tools-and-build.md` | the repository's tools, helper scripts and CI workflows |

**If you only run one, run 1a part 1** - it is where a mistake would break
one of the five rules.

## Steps, one at a time

1. **Get the files.** They were sent to you with the 2026-09-28 audit
   report (built from all five branches combined, so they include work not
   yet on `main`). Put them in one folder. *After the five branches are
   merged*, you can also make a fresh set on your PC (one line; the folder
   opens at the end):

   ```powershell
   cd "$env:USERPROFILE\Epic-Jarvis"; git pull; py -3 tools\gen_gemini_bundles.py --since 093caeec; explorer "$env:USERPROFILE\jarvis-gemini-audit"
   ```

   Smaller files, if the model says a file is too big (300k tokens each;
   more files):

   ```powershell
   cd "$env:USERPROFILE\Epic-Jarvis"; py -3 tools\gen_gemini_bundles.py --since 093caeec --budget 300; explorer "$env:USERPROFILE\jarvis-gemini-audit"
   ```

2. Open https://gemini.google.com, choose the model, turn on its extended
   thinking, and start a **new chat for each file** - never two files in one
   chat.
3. Attach that file, and also `docs\ARCHITECTURE.md` from the repository
   folder (the permission model the code is supposed to follow).
4. Paste the prompt below, changing only the first line to the file's
   session and part.
5. Save each answer (copy it into a text file named after the file) and send
   them all to Claude. Every finding is checked against the real source
   before anything changes - earlier Gemini passes had real findings and
   wrong ones, and both have been handled that way.

---

## The prompt (paste everything between the lines)

---

SESSION: 1a part 1 of 2 (change this line to the file you attached)

You are auditing part of "Jarvis", a personal, non-commercial, local-first
assistant: a Python backend on the owner's Windows 11 PC with a local 8B model
in Ollama, a Tauri 2 desktop app (Rust + JavaScript), and an Android app
(Kotlin, Jetpack Compose) that reaches the PC over Tailscale or NordVPN
Meshnet. The backend is delivered as patches against a program that is not
in this repository, plus whole modules this repository ships; a PowerShell
script (`apply-patches.ps1`, run on Windows PowerShell **5.1**) applies them.

The attached bundle holds every source file of this part that was added or
changed since the last outside audit (2026-09-20), whole. `ARCHITECTURE.md`
describes the permission model the code must follow. Be adversarial,
specific and unsparing. I would much rather be told something is broken
than have it smoothed over, and "looks fine" about a file you did not
actually read is worse than saying you skipped it.

### The five rules that must not be broken - check these first

For each, say whether THIS code enforces it, citing file and line, not
whether a comment claims it does.

1. Anything touching email, files, credentials or stored memory stays on the
   local model. Nothing sends it anywhere else - including to an outside
   chatbot or a cloud model the owner can choose to ask.
2. Never a public tunnel (no ngrok, Cloudflare Tunnel, Tailscale Funnel,
   "share my Jarvis"). The apps accept a server address on the owner's own
   networks only.
3. API keys (chatbot and web search keys, a private calendar link, service
   passwords, the pairing token) are never logged, sent only to the one
   service they authenticate against, and never written to disk in plain
   text.
4. Nothing is ever approved automatically; acting is blocked when the event
   stream is stale.
5. Non-commercial, sideloaded, never on a store.

### Also required by design

- One approval card per action; never a way to approve in bulk or to clear a
  rush latch. A card's "no" must not quietly become a permanent rule unless
  the code says so on purpose. A feature that shows one card for several
  steps must stay switched off until its own safety tests pass, and even
  then every risky step keeps its own card.
- Text from outside (web pages, search results, emails, calendar entries,
  file contents, phone notifications, chatbot answers, imported chat
  histories, tool output, pasted or shared text) must never be able to make
  Jarvis act, raise its own permissions, or be saved as a fact about the
  owner. Facts are learned only from the owner's own words.
- Phone notifications: off by default; only apps the owner picks, never
  banking; one-time codes hidden before anything reaches the model; never
  text messages; Jarvis never replies.
- Anything sent to an outside chatbot or a cloud model is shown word for word
  on a card first, and a private or outside-text conversation can never be
  sent.
- Hands-free listening ("Hey Jarvis", a hands-free conversation) must not
  let a TV or a recording approve or act.
- Settings that show more or trust more raise a card to turn on; turning them
  off is immediate, everywhere (both apps).
- A timer or one-time reminder needs no card and works without the model.
- A crisis message is never learned from and never counted; it gets the
  owner's crisis numbers.
- Every request from the apps sends `X-Jarvis-Client: hud`; the token is never
  logged.

### What to look for

Bugs that change behaviour, in this order: broken rules above; security
(injection, path traversal, parsing untrusted files, secrets leaking into
logs/errors/events/UI, redirects carrying credentials, requests going
through a proxy they should not, unbounded reads); data loss or corruption
(SQLite, files, migrations, encryption); concurrency (threads, locks, races
between a card being answered and the thing it approves, two features
wanting the microphone at once); error paths that crash, hang or silently
do the wrong thing; time and time-zone handling; resource leaks (including
graphics: the animated faces share the graphics card with the AI model);
and, for the PowerShell script, anything that fails on Windows PowerShell
5.1 specifically (e.g. `??`, `?.`, ternaries) or dies because
`$ErrorActionPreference = 'Stop'` meets a native program writing to stderr.
For Kotlin in 4a/4b: this code is compiled only by CI, so also flag
anything that would not compile. For session 5: tools that would silently
pass when they should fail. Skip style, naming and formatting.

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

Send them to Claude as they are. They are treated as reports, not facts:
each is checked against the file and line it cites, fixed if real (with a
test that fails first), and answered with the reason if not. The results go
in a short write-up, like the earlier rounds (`docs/GEMINI-AUDIT.md`).

When this round's fixes land, move `LAST_AUDIT` in
`tools/gen_gemini_bundles.py` to the commit that closes it, and write down
which findings were real and which were not, so the next round has a clear
starting point (the 2026-09-25 round did not, which is why this one starts
from 2026-09-20).
