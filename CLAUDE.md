# Working with the owner of this repo

The desktop and Android sessions each kept their own copy of this file while
they worked on separate branches. This is the reconciled version, now that
both have merged into `main` — read this one, not an old copy on a deleted
branch.

## Keep multiple-choice questions SHORT

This is the rule that gets broken most. Asking four questions with four
paragraph-length options each is not a question, it is a document with radio
buttons. It makes a decision harder to make, not easier.

- **One or two questions at a time.** Three is a lot. Four is too many.
- **Two or three options each.** Not four.
- **One or two sentences per option.** Not a paragraph.
- **No jargon in the question itself.** If the question cannot be asked in
  plain words, explain the thing first in a sentence, then ask.
- Lead with the recommendation and say it is the recommendation.
- Put the long reasoning in the reply *around* the question, or in a document.
  Not inside the options.

Bad:

> Should the KV cache use q8_0 quantisation given that llama.cpp reaches the
> quantised path only through fused attention, and Ollama's `ml/device.go`
> gate admits compute capability 7.5 while excluding 7.2, which means…

Good:

> Jarvis can squeeze more conversation into the graphics card's memory by
> storing it in a smaller format. Slight risk it is not supported on your
> card, in which case things get much slower and nothing warns you.
>
> - **Do it, and check it worked** (recommended)
> - **Leave it alone**

## Explain things simply

The owner is a **beginner developer**. Write for someone who is smart and is
learning, not for someone who already knows the jargon.

- Say what a thing *is* before using its name. "R8 (the tool that shrinks the
  app)" beats "R8" on first mention.
- Prefer short sentences and plain words. "The app was slow because it was
  built in debug mode" beats "the debuggable variant disables ART AOT
  compilation".
- When something technical is unavoidable, explain it in one line and move on.
- **Say what to actually do**, concretely: which button, which file, which
  command, in order. Do not leave the next step implied.
- Do not assume knowledge of Gradle, Android build variants, CI, git internals,
  Rust, or Kotlin idioms.
- Lead with the answer. Put the reasoning after it, for anyone who wants it.

This is about clarity, not simplification of substance. Do not hide problems,
soften bad news, or skip caveats - explain them in plain words instead. If
something is broken, uncertain, or was my mistake, say so directly and early.

## What this project is

A local-first personal assistant. A Python backend on the owner's Windows 11
desktop, an 8B model in Ollama on the same machine, a Tauri 2 desktop shell
around it, and an Android companion reachable over Tailscale or NordVPN
Meshnet (both private device-to-device networks, never a public tunnel).

Hardware: an RTX 2080 Super (8 GB) today. **The owner is adding an RTX 2060
12 GB as a second card** - plan features with that second, larger-context
lane in mind, but do not switch anything on that depends on it until it is
installed and measured. `docs/MODEL-TOPOLOGY.md` has the numbers.

- `jarvis-desktop/` - the Tauri desktop app. Rust in `src-tauri/`, the windows
  in `src/`.
- `backend/` - patches against the Python backend, which lives outside this
  repo (`docs/ARCHITECTURE.md` §9 says where), plus tests that prove each
  patch works.
- `jarvis-client/` - the Android app (Jetpack Compose) that actually talks to
  the backend, over the real API (`docs/`'s `JARVIS-API.md`).
- `jarvis-android/` - an older Android app, kept for reference. It speaks a
  WebSocket protocol invented before `JARVIS-API.md` existed, and none of its
  endpoints exist on the backend, so it cannot talk to Jarvis at all. Its
  safe, self-contained parts (the approval widget, a quick-link widget) have
  already been adapted into `jarvis-client`; its duplex audio streaming was
  deliberately **not** ported, because `jarvis-client`'s own voice-print gate
  needs a complete recorded clip to check, and streaming would undermine
  that. See the module's own README before assuming anything else in it is
  safe to copy over verbatim.

## The five rules that are not negotiable

1. Anything touching email, files, credentials or stored memory stays on the
   local model. The app sends none of it anywhere.
2. The app never opens a public tunnel. No ngrok, no Cloudflare Tunnel, no
   Tailscale Funnel, no "share my Jarvis".
3. API keys are allowed in the app - the owner reversed the old blanket ban
   on 2026-09-17, to unblock things like a GitHub API integration. Any key
   still gets the same care the pairing token already gets: never logged,
   sent only to the one service it authenticates against, and kept out of
   anything the app writes to disk in plain text.
4. The app never auto-approves anything, and blocks acting when the event
   stream is stale.
5. Non-commercial build. Sideloaded via adb, never listed on Play.

Also standing: do not build the model catalogue, the memory graph, or deep
config editing on the phone. A client must not do speech-to-text. Never build a
control that clears a rush latch or approves in bulk. Send
`X-Jarvis-Client: hud` on every request. Never log the token.

Amended by the owner on 2026-09-18: **switching the local model from the
phone is allowed** - between models the desktop already has, via
`/api/models/switch`, which raises an approval card like any other change.

Amended by the owner on 2026-09-20: **installing a model from the phone is
allowed too**, the same shape as switching - a typed model reference posted
to `/api/models/install`, tier `ask` on the server, raising an approval
card like any other change; nothing downloads until that card is approved.
What is still off the phone is *browsing*: there is no catalogue to scroll
or search, no list of what could be installed, only of what already is.
The owner types the name by hand, the same as at a terminal
(`ollama pull <ref>`) - see `BrainScreen.kt`'s `ModelsPlate` and
`JarvisRuntime.installModel`.

Amended by the owner on 2026-09-24: **Jarvis learns automatically by
default.** Facts about the owner and their projects, learned from the
owner's own words only (never from web pages, emails, documents, notes or
tool output), are saved without a per-fact yes, and every one is listed in
both apps with a Forget (it asks "are you sure?" first - the owner chose
to keep that question, 2026-09-24, because forgetting cannot be undone).
Sensitive topics (health, money, passwords
and account details, private details about other people) still wait for
the owner's yes, unless the owner turns on "Also remember sensitive topics
automatically", which is off by default. Turning either setting on raises
an approval card; turning it off is immediate. **Chat history, including
voice transcripts, is kept on the PC by default**, encrypted, with a switch
to turn it off. Background learning stays on by default.

Also decided 2026-09-24: an answer that uses a sensitive saved fact is
**kept on screen, not read aloud**, by default - even under "Read aloud"
for answers that use memories. A voice setting lets the owner allow it;
turning that on raises an approval card like the other voice settings.

Also decided 2026-09-24, after the safety research
(`docs/RESEARCH-2026-09-24.md`):
- **Note-writing waits for a yes after outside text.** In a turn where Jarvis
  has read an email, web page, file or other tool output (or the
  conversation is tainted, or the message was pasted or shared), writing to
  Obsidian, Logseq or Joplin raises an approval card. Other turns save notes
  straight away, as before.
- **Passwords, PINs, account numbers and ID numbers always wait for the
  owner's yes**, even with "Also remember sensitive topics automatically"
  on. That setting covers health, money and the other sensitive topics only.
- **"Erase the words" joins Forget.** Forget still hides a fact and keeps its
  history. A second action, "Erase the words", wipes the fact's text for
  good (and its search entry); only the dates stay, so the history shows
  that something was erased. It asks "are you sure?" first, like Forget.
- **Hands-free voice is as trusted as the talk button by default, with a
  setting to make it stricter** (owner, 2026-09-24). A voice setting
  "Hands-free ("Hey Jarvis")" offers: "Same as the talk button" (default)
  and "Only trust the talk button" - under the stricter choice, a turn
  started by "Hey Jarvis" cannot save facts without a card, and its memory,
  sensitive or private answers stay on screen. Choosing the stricter option
  is immediate; going back raises an approval card, like the other voice
  settings. The voice check's wording says plainly that it cannot tell a
  recording or a copy from the real voice.
- **Spoken questions get spoken-style answers, and speech starts at the
  first comma.** A voice turn tells the model its answer will be spoken
  (short first sentence, 1-3 sentences unless asked for more, no lists or
  markdown); typed turns are unchanged. Both apps start speaking at the
  first comma of an answer once the phrase is long enough.
- **Phone pairing by QR code, with a short typed code as the backup**,
  confirmed by an approval card on the PC before any key is handed over.
  Built together with per-device keys (task "more devices"), since both
  change how a device gets its key.

Decided 2026-09-25, after the competitiveness audit
(`docs/RESEARCH-2026-09-24.md` and the audit reports):
- **Timers, reminders and one shared scheduler come first** in the queue.
  The any-GPU presets, Docker, model advice and mouse control wait. Build
  ONE scheduler (the initiative engine and digest) and reuse it for
  briefings, sleep mode and the overnight tidy - not one per feature.
- **A plain timer or a one-time reminder needs no approval card; anything
  that repeats ("every weekday at 7") asks once with a card**, and that
  card lists the next run times. Simple commands like timers are answered
  without the AI model, so they keep working when the model is slow,
  unloaded or asleep.
- On the desktop, while App lock is on, the approval widget shows only a
  short title and its Approve opens the locked app; the HUD is locked too.
  On the phone, screenshots are blocked while App lock or "Hide memory lists
  and chat history" is on.
- **Plain `http://` (unscrambled) to Home Assistant or the calendar is
  allowed only inside the owner's own networks:** this PC, the home network
  (private addresses such as 192.168.x.x and 10.x.x.x, and `.local` names),
  Tailscale and NordVPN Meshnet (both encrypt the traffic themselves). It is
  refused to anything on the open internet.
- **The "I heard you" sound gets a switch in both apps, off by default**,
  next to the "One moment" switch (the owner changed on to off, 2026-09-25).
- **The standby schedule wakes Jarvis only if the schedule put it on
  standby.** Standby switched on by hand stays on at the end of the hours.
- **The morning briefing shows new emails' count AND senders by default**,
  with a setting in both apps to show the count only.
- **Web search with a choice of five providers, SearXNG the default,** in
  this order: SearXNG (self-hosted, in Docker, on this PC only), DuckDuckGo
  (the `ddgs` library, DuckDuckGo backend only), Exa and Tavily (free keys,
  no payment card), and Brave (a key and a payment card that is charged past
  the $5 monthly credit - the owner removed it, then asked for it back the
  same day, 2026-09-25; its line says plainly that it can cost money). Keys
  follow rule 3. Each has a short "why use this one" line in both apps, and
  Jarvis can explain the choice. Left out, and the list says why: Whoogle
  (it stopped returning results in 2025). No silent fallback: if the chosen
  provider is down, Jarvis says so and offers to switch.
- **When a search asks first:** by default only when private things could
  slip in - a card showing the exact search words if the conversation has
  read email, files, notes or saved memories; no card for a search that
  comes straight from the owner's question. A setting makes it ask every
  time.
- **Jarvis may read Google Calendar through its private link** ("Secret
  address in iCal format"): read-only, set on the PC only, and the link
  kept as safely as a password (never logged, shown or sent anywhere but
  Google).

## Every new feature gets its own audit, without being asked

Standing instruction from the owner, 2026-09-24. Whenever features are added
to Jarvis, run a follow-up audit scoped to the new feature set as part of
the same piece of work. Do not wait to be asked. It covers three things:

1. **Bugs.** A bug audit of the new code. Findings are verified against the
   source before they are reported, as everywhere else in this file.
2. **Both apps.** Was the feature added to the desktop program AND the
   Android app, wherever it makes sense? If one side is deliberately left
   out, the reason must be written down in `docs/ARCHITECTURE.md` §8
   ("One-sided on purpose"). `tools/check_parity.py` must be clean.
3. **Fit with what is already there.** Does it tie in with the existing
   features? That means:
   - the same permission model and approval cards;
   - the same settings patterns and the same wording;
   - no clash with an existing feature, and no duplicate of one;
   - `docs/JARVIS-API.md` and the other docs updated.

"Features" means abilities the owner can see or use, not bug fixes or doc
edits. When several features land together, one audit covers the batch.
Report the result in plain words. Fix what it finds, or ask when the fix is
the owner's call.

## Tell the owner when something is wrong

Standing instruction from them: "Tell me plainly when something in the brief is
wrong, out of date, or won't work on the platform - I'd much rather hear that
than have you route around it quietly."

## Do not claim more than the evidence supports

This has caused real damage in this project more than once: a stack frame read
as a cause and relayed as "confirmed", and a bug invented by grepping my own
draft and mistaking it for the source file.

- Verify against the actual file before stating anything about it. Especially
  before stating it to the other session.
- Quote the evidence. Let the side that owns the code do the diagnosing.
- "I checked X and it says Y" beats "Y". "I have not checked" beats a guess
  delivered confidently.

## How the Android apps get built

There is no local Android build in this container. `dl.google.com` is blocked
by the network policy, so the Android Gradle plugin cannot resolve and
**GitHub Actions is the only compiler available** for `jarvis-client` and
`jarvis-android`. Expect a CI round trip (~15 min) to find out whether
anything compiles. Check work carefully before pushing.

The `jarvis-client` APK is published to the rolling `client-latest` release,
but only when the emulator smoke job passes. `jarvis-android` no longer
publishes a release at all - see the top-level `README.md` for why.

## Checking the Rust without waiting for CI

`cargo clippy` fails in the dev container: the product is a Windows app, the
Linux dependency graph pulls `gdk-sys`, and GTK is not installed. For a long
time that meant every Rust change was pushed unverified and checked by CI five
minutes later.

**It does not have to be.** The `x86_64-pc-windows-msvc` target is installed,
and checking against it selects the *Windows* dependency graph, which has no
GTK in it. Nothing is linked, so no MSVC toolchain is needed:

```
cd jarvis-desktop/src-tauri
cargo fmt --check
cargo check  --target x86_64-pc-windows-msvc --all-targets
cargo clippy --target x86_64-pc-windows-msvc --all-targets -- -D warnings
```

That is two of the three things CI runs, on the same code CI compiles,
including every `#[cfg(windows)]` block — which a Linux check would have
skipped entirely, and which is where the unsafe FFI lives. It takes about
twenty seconds warm.

The third, `cargo test`, still needs a Windows host. Write the Rust tests
anyway; they are compiled by `--all-targets` above, so at least they are known
to build. A "GNU compiler is not supported for this target" warning in the
output is expected and harmless.

## PowerShell: ONE line, ready to copy

The owner runs these by pasting into a terminal. A multi-line block is a
multi-line paste, and a multi-line paste into PowerShell goes wrong in ways
that look like the command is broken rather than like the paste was.

- **One line.** Statements joined with `;`. However long it ends up.
- **No `.ps1` file to run**, unless the point IS the file. A script file means
  being in the right folder, and it means the execution policy, and both of
  those produce errors that read as "your command is wrong".
- Say where any output file lands, in plain words, at the end of the command.

The trap, written down because it has already been shipped once: inside
`catch`, `$_` is the ERROR, not the pipeline item. In
`... | ForEach-Object { try { ... } catch { $o[$_] = ... } }` the catch writes
under an ErrorRecord instead of the name. Capture it first — `$n = $_` — or
use a plain `foreach` loop, where the variable is real.

## Running PowerShell here

There is a PowerShell 7 at `/opt/pwsh/pwsh` — the portable tarball, extracted,
no install. **Use it.** Three bugs shipped to the owner before it existed,
each found by them running the script and pasting an error back, which is the
slowest possible way to test anything:

```
/opt/pwsh/pwsh -NoProfile -File ./scripts/apply-patches.ps1 -BackendPath /tmp/fake -SkipTests
```

If it is gone after a container restart:
`curl -sSL https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/powershell-7.4.6-linux-x64.tar.gz -o /tmp/pwsh.tar.gz && mkdir -p /opt/pwsh && tar -xzf /tmp/pwsh.tar.gz -C /opt/pwsh && chmod +x /opt/pwsh/pwsh`

**It is 7, the owner has 5.1.** It catches syntax errors, logic and the
stderr trap; it does NOT catch 5.1-only problems like `??`, so those still
have to be read for.

The trap that cost the most: `$ErrorActionPreference = 'Stop'` turns **any
stderr output from a native program into a terminating error**, even on
success. `git apply --verbose` writes "Checking patch x..." to stderr every
time, so the script died on the first of nineteen patches. Wrap native calls:
save the preference, set `Continue`, restore in a `finally`.

## Where everything is written down

- `docs/ARCHITECTURE.md` — **read first.** The invariants, the one permission
  model every feature must use, memory, events, and what does not exist yet.
- `docs/MODEL-TOPOLOGY.md` — what runs on the graphics card and why.
- `backend/README.md` — the patches and what each one fixes.

The Python backend lives on the owner's machine, not in this repo. `backend/`
holds patches against it plus tests that prove the patches work.
