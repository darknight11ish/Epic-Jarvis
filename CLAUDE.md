# Working with the owner of this repo

The desktop and Android sessions each kept their own copy of this file while
they worked on separate branches. This is the reconciled version, now that
both have merged into `main` — read this one, not an old copy on a deleted
branch.

## Whenever a choice is needed, give multiple choice

The owner has said it again and again ("Give me multiple choice", 2026-09-29
and before): when a decision is theirs, offer it as a multiple-choice
question, not an open one and not a wall of text. Lead with the recommended
option. The rules below say how to keep it short.

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

Hardware: both cards are installed and measured (2026-10-05): an RTX 2080
Super 8 GB with the monitor, running the desktop, and an RTX 2060 12 GB with
none, holding the everyday model. Both are Turing (compute 7.5), so both
clear the cache and flash-attention floor. The 2060 is the second,
larger-context lane. **The second card is installed but its features are not
measured** - plan features with that lane in mind, but do not switch a feature
on until *that feature* is measured; every feature that uses the second card
keeps its own switch, off until the owner turns it on
(`docs/MEASURED-2026-10-05-owner-pc.md`; `docs/MODEL-TOPOLOGY.md` has the
numbers).

- `jarvis-desktop/` - the Tauri desktop app. Rust in `src-tauri/`, the windows
  in `src/`.
- `backend/` - patches against the Python backend, which lives outside this
  repo (`docs/ARCHITECTURE.md` §9 says where), plus tests that prove each
  patch works.
- `jarvis-client/` - the Android app (Jetpack Compose) that actually talks to
  the backend, over the real API (`docs/`'s `JARVIS-API.md`).
- `jarvis-android/` - an older Android app, kept for reference. It speaks a
  WebSocket protocol invented before `JARVIS-API.md` existed, and its one
  endpoint is not wired into the backend, so it cannot talk to Jarvis at all.
  Its safe, self-contained parts (the approval widget, a quick-link widget)
  have already been adapted into `jarvis-client`; its duplex audio streaming
  was deliberately **not** ported, because `jarvis-client`'s own voice-print
  gate needs a complete recorded clip to check, and streaming would undermine
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
   The owner said on 2026-09-28 that EpicJarvis **will never be
   commercialized**. So a non-commercial licence (CC BY-NC, CC BY-NC-SA) is
   no reason to avoid or replace a part - don't raise "it blocks selling
   Jarvis" as a concern. Everything else those licences ask still applies:
   credit in THIRD-PARTY-NOTICES.txt, share-alike, no redistribution
   against their terms.

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

## The dated decision log lives in `docs/DECISIONS.md`

Everything this file used to carry as a **dated decision** - every block written
"Decided 2026-09-xx"/"2026-10-xx" from 2026-09-24 to 2026-10-11 - now lives in
**`docs/DECISIONS.md`**. That file is **the record**: what was decided, when, in the
owner's own words, and what each decision replaced. It is **not** the rulebook.

This file keeps the rules themselves: the five non-negotiables, the standing
amendments to them, the never-do-this list, and the sections below. **Read this file
to know a rule; read `docs/DECISIONS.md` to know why it exists and when it changed.**
The split was made on 2026-10-12 because this file had grown past the 64 KB
instruction budget and was being silently truncated - so the newest rules, at the
bottom, were the ones most at risk of never being read.

**Earlier decisions still bind.** Before building or changing anything, search
`docs/DECISIONS.md` for it: the reasoning lives there, and some of it is a promise to
someone outside this project - the sea otter's voice is not a matter of taste, and the
record says why. **Not finding a rule here does not mean there is no decision.**

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
- **Say which tree you asked.** This repository is worked in parallel `git
  worktree` checkouts - **a worktree is a second copy of the code, on another
  branch** - so a plain search answers "what does MY checkout say" while reading
  exactly like a claim about `main`:

  ```powershell
  git grep -n 'X' -- path                        # what THIS checkout says (a branch, often)
  git show origin/main:path | Select-String 'X'  # what main says
  ```

  This cost two rounds on 2026-10-11: a false finding about a privacy-sensitive
  plate, and then a second reader "independently confirmed" it - with the same
  command, in the same feature branch, and neither of them asked what it searched.
  **Two confirmations of the same wrong thing, because the instrument was the
  same.** When the claim is about `main`, read `origin/main`; when it is about the
  file in front of you, say so. (Written up as one of the dead ends in
  `docs/FIELD-TEST-HOW-TO-READ-THE-APPS.md`.)

## How the Android apps get built

There is no local Android build in this container. `dl.google.com` is blocked
by the network policy, so the Android Gradle plugin cannot resolve and
**GitHub Actions is the only compiler available** for `jarvis-client` and
`jarvis-android`. Expect a CI round trip (~15 min) to find out whether
anything compiles. Check work carefully before pushing.

**A phone face's AGSL shader must stay under Android's size limit.** Android
compiles `RuntimeShader`s in Skia's strict mode, which refuses any shader
whose flattened size is over 100,000 - and the app crashes when that face is
drawn. Every operation counts 1, a call counts the called function's whole
size, and a loop counts its body once per step, so a big distance function
inside a long march loop blows it fast. WebGL and a newer Skia on a PC
(skia-python) accept an over-size shader without a word: the first red panda
went out four times over and only the emulator test caught it. Measure with
`python3 tools/shader_size.py` (CI runs `--check`) before pushing a shader.

The `jarvis-client` APK is published to the rolling `client-latest` release,
but only when the emulator smoke job passes. `jarvis-android` no longer
publishes a release at all - see the top-level `README.md` for why.

## Editing a backend `.patch`: record its old version first

After changing any `backend/*.patch`, run `python3 tools/build_patch_history.py`
before committing (its docstring says why). **This container's clone is
shallow**, and there the tool refuses to run and `test_patch_history.py`
quietly skips the checks that need history - so it passes here and fails in
CI. Run `git fetch --unshallow origin` first. (Shipped once, 2026-09-28:
`voices.patch` changed, CI's backend job went red.)

## Checking the Rust without waiting for CI

`cargo clippy` fails in the dev container: the product is a Windows app, the
Linux dependency graph pulls `gdk-sys`, and GTK is not installed. For a long
time that meant every Rust change was pushed unverified and checked by CI five
minutes later.

**It does not have to be.** Check against the `x86_64-pc-windows-msvc`
target. It is not always installed in a fresh container (it was missing on
2026-09-27): if `rustup target list --installed` does not list it, run
`rustup target add x86_64-pc-windows-msvc` first. Checking against it selects the *Windows* dependency graph, which has no
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

**Use the same Rust as CI.** CI runs the newest stable Rust, and this container
can lag behind it: on 2026-09-29 the container's 1.94 passed clippy while CI's
1.98 flagged a nested `if` (`collapsible_match`) and failed the `rust` check.
Run `rustup toolchain install stable --profile minimal -c clippy -c rustfmt
--no-self-update` first, then the three commands above.

The third, `cargo test`, used to need a Windows host and nothing else was said
about it. Write the Rust tests anyway; they are compiled by `--all-targets`
above, so at least they are known to build. A "GNU compiler is not supported
for this target" warning in the output is expected and harmless.

### Running the tests — the fourth command

**Clippy never runs a test, and that is not a small thing.** PR #394's `rust`
job failed on a test that asserted `"Not installed"` against a fixture saying
`"not installed"` — **deterministically impossible, it had never once passed.**
It hid because clippy *compiles* tests without running them, so a test that
cannot pass is invisible locally and shows up in CI forty minutes later. One
test here also opens a window and screenshots the screen, which is why nobody
ran the suite at a desk they did not want disturbed. Now there is a way to run
the rest of it.

```
cargo test --target x86_64-pc-windows-msvc
```

That is the third thing CI runs, on the same Windows target as the checks
above. It is happy with the owner sitting in front of his own PC: **the one
test that opens a window and reads the screen is `lock.rs`'s capture probe**
(`lock::capture_probe::the_exclusion_is_real_and_reversible_on_this_pc`, the
red window the screenshot-exclusion probe is measured against). Nothing else
in the suite opens a window, drives a webview or looks at the screen — every
other test in a file that *builds* windows is a pure one: geometry, JSON
fixtures and source-text pins.

**The documented opt-out.** When the owner would rather nothing appear on his
screen at all, set `JARVIS_SKIP_WINDOW_TESTS=1` and the probe does not run:

```
$env:JARVIS_SKIP_WINDOW_TESTS="1"; cargo test --target x86_64-pc-windows-msvc
```

A skipped test is **never** a pass here (the BLOCKED-is-never-a-pass rule), so
the skip says so out loud, on the process's own stderr — which libtest does not
capture, so the line shows in a plain run with no `--nocapture`. It reads:

```
SKIPPED  the_exclusion_is_real_and_reversible_on_this_pc - this test opens a window or reads the screen, and JARVIS_SKIP_WINDOW_TESTS=1 is set. It did NOT run, and it did NOT pass. Unset that variable to run it.
```

The harness still prints `ok` for it, and it always will: Rust has no skipped
state, and `assert!`-ing the skip would fail the suite, which is the opposite
of an opt-out. So the printed SKIPPED line is the honest report, and it is the
thing to look for. `#[ignore]` was the alternative and was turned down — it
inverts the default so every ordinary run loses the probe, it cannot be driven
by an environment variable, and it prints `ignored`, which this project does
not accept in place of "did not run". A second test,
`lock::capture_probe::the_window_probe_is_the_only_test_the_opt_out_guards`,
stops the gate from being quietly renamed away: it reads the source and checks
the variable name and the guard are both still there.

**`CARGO_PROFILE_DEV_DEBUG="0"` on this PC.** Its `cl.exe` intermittently fails
`D8050` on an unrelated C++ helper crate (`vswhom-sys`). The flag avoids that
and changes nothing about the code compiled; the toolset is complete and the
error does not always reproduce, so it is not a code problem.

**Three tests fail here and are not this suite being broken.** On 2026-10-13,
`crash_notes::tests::a_successful_write_really_lands_on_disk`,
`crash_notes::tests::record_and_read_round_trip_and_keep_only_the_newest` and
`commands::wiki_tests::only_a_real_jarvis_wiki_folder_is_opened` all failed on
unmodified `main` too: they are `%TEMP%`-folder operations and `%TEMP%` here
refuses the write (`Access is denied`). Everything else passed — 775 of 778.

**The whole thing as ONE line, ready to paste.** Run it from the repository
root (`$log` is resolved before the folder changes, so the log lands in the
repository root and not in `src-tauri`). It sets the opt-out, changes into
`jarvis-desktop/src-tauri`, runs the four commands in order, and writes the
full output — all four commands, including the failures — to
`rust-check-<date>.log` **in the repository root**. It ends by saying where
that file is:

```powershell
$env:CARGO_PROFILE_DEV_DEBUG="0"; $env:JARVIS_SKIP_WINDOW_TESTS="1"; $log="$PWD\rust-check-$(Get-Date -f yyyy-MM-dd).log"; Push-Location jarvis-desktop\src-tauri; cargo fmt --check; cargo check --target x86_64-pc-windows-msvc --all-targets; cargo clippy --target x86_64-pc-windows-msvc --all-targets -- -D warnings; cargo test --target x86_64-pc-windows-msvc *>&1 | Tee-Object -FilePath $log; Pop-Location; "Full output: $log"
```

Drop `$env:JARVIS_SKIP_WINDOW_TESTS="1";` from that line to run the probe too.
`*>&1` merges stderr as well, so the SKIPPED lines are in the log as well as on
the screen.

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

## Launch videos: every version is kept and numbered

The owner's rule, 2026-09-24: never replace a launch video. Each new one is
the next version, and every version goes on GitHub.

- Finished videos live in `videos/vN/` as `jarvis-launch-vN.mp4` with its
  poster `jarvis-launch-vN.jpg`, the plan, the brief, the share copy and the
  Hyperframes project. v1 to v6 are there (v3 to v6 also have an upright
  cut, `jarvis-launch-vN-vertical.mp4`); the next one is v7.
- The `/brag` skill renders into `brag-output/`, which is gitignored scratch.
  Copy the finished video into `videos/vN/`, add it to the top of
  `videos/README.md`, point the README's "Launch video" section at it, and
  post it: push and open a pull request.
- Keep each `.mp4` under GitHub's 100 MB file limit (re-encode if a render
  comes out bigger), and check the soundtrack's loudness after rendering:
  once the renderer's mixer made it 11 dB quieter than the score.
- A video says only what the code supports. Mark anything built-but-off as
  "ready" and anything designed-but-not-built as "next".

## Where everything is written down

- `docs/HANDOFF-2026-10-04-audit-pass.md` — **start here in a new conversation**:
  the 2026-10-04 audit pass and its work order (the newest handoff, checked
  2026-10-05). Then `docs/HANDOFF-2026-09-30.md` (where things stood after
  PR #39) and `docs/HANDOFF-2026-10-04-test-suite-fixes.md`.
- `docs/ARCHITECTURE.md` — **read first.** The invariants, the one permission
  model every feature must use, memory, events, and what does not exist yet.
- `docs/MODEL-TOPOLOGY.md` — what runs on the graphics card and why.
- `backend/README.md` — the patches and what each one fixes.
- `docs/DECISIONS.md` — **the dated record, not the rulebook**: the owner's decisions
  from 2026-09-24 to 2026-10-11, moved out of this file on 2026-10-12 when it grew past
  the instruction budget. The rules are here; when and why each was decided is there.

The Python backend lives on the owner's machine, not in this repo. `backend/`
holds patches against it plus tests that prove the patches work.

Decided 2026-10-11, written down here on 2026-10-12 by the docs review, because
these are rules the project now runs on and a reader should not have to infer them
from a commit message:

- **BLOCKED and NOT-TESTABLE are never counted as passes.** A field-test row that
  could not be reached is written as BLOCKED, PARTIAL or NOT-TESTABLE and reads as
  such; only a feature driven on real hardware is a PASS. The rule and the rows it
  applies to are in `docs/FIELD-TEST-MATRIX-2026-10-11.md`.
- **Editing any file under `backend/` is a two-file change, and "any file" is
  broader than "any module".** `backend/<file>` and `jarvis-backend/<file>` are
  kept equal - the second is the published base an installer starts from - so a
  change to one must be carried to the other. That is the modules this repository
  ships whole (the `SHIPPED` list in `backend/_where.py`, plus `backend/rebuilt/`)
  **and the "beside-files" the base's code reads without importing**, which land
  under the same bare name in the base: `backend/rebuilt/jarvis-framework.toml`,
  `backend/requirements.lock`, `backend/quiz_grader_cases.json`,
  `jarvis-desktop/src/jarvis_hud.html` and
  `jarvis-desktop/src-tauri/Cargo.lock`. The authority on that list is the
  re-take rule's own table - `BESIDE` in `tools/gen_base_from_backend.py`, the
  script that writes the base. Two entries there are deliberately **not** carried
  by copying: `backend/_where.py` lands as the base's copy *plus*
  `BASE_WHERE_TRAILER`, so re-take it rather than copy it, and
  `jarvis-visual-spec.json` is re-taken from the owner's live backend folder, so
  this repository holds no copy of it to compare. (`backend/requirements.txt` is
  not part of this - the base carries no `.txt` at all, so it has no twin.) Run
  **all three** before pushing: `python -B backend/test_base_matches_repo.py`,
  `python -B backend/test_base_regeneration.py` and
  `python -B tools/check_stale_twins.py`. **CI does run all three, and that is not
  a reason to skip them at the desk.** The two suites run in the **required**
  `backend` job, through `python backend/run_suites.py`
  (`.github/workflows/ci.yml:213`, which globs every `backend/test_*.py`), and
  `test_base_matches_repo.py` runs a second time in the **required**
  `backend-windows` job by name (`.github/workflows/ci.yml:578`).
  `tools/check_stale_twins.py` runs in the `audit` job
  (`.github/workflows/ci.yml:1534`), which is informational and does **not** gate
  a merge. So a stale twin is caught before merge - and costs a full CI round
  trip plus the diagnosis, which is the reason to run the three at the desk
  first. **This bullet used to end "Neither is run by a workflow", quoting
  `docs/AUDIT-2026-10-11-IS-MAIN-COHERENT.md` section 1; that was true when the
  audit measured it, and `df9ae3d9` ("ci: run the five checkers that existed and
  no workflow ran") made it false the same week. Corrected 2026-10-13.**

  **Why the beside-files are spelled out here, measured 2026-10-13.** PR #390
  added `rapidocr` to `backend/requirements.lock` and not to
  `jarvis-backend/requirements.lock`. The rule as it used to read named
  `backend/<file>` and was read as being about modules;
  `tools/check_stale_twins.py` compared the shipped modules only; the author's
  local run was green, "all 191 shipped modules match". CI went red on two jobs
  at once - `backend` and `audit` - on
  `FAIL ... these differ (or are absent): requirements.lock`, the line
  `backend/test_base_regeneration.py` prints. One missing line reached both
  jobs through the claims register: `tools/check_claims.py` runs every suite a
  `test:` row names (row D11 is this one), the `audit` job runs that checker
  directly, and the required `backend` job runs it through
  `backend/test_claims.py`, which asserts it exits 0. **A local check that
  passes while CI fails is the expensive case** - it costs the pushed run, the
  diagnosis and a second push, for a one-line omission - so the beside-files are
  named here rather than left to be inferred from `backend/<file>`.
  `tools/check_stale_twins.py` compares them now too, so it is caught in a
  second at the desk instead.
- The same day's owner decision - **the phone may raise a spending limit with its
  own fingerprint** - is recorded in `docs/DECISIONS.md` (search it for "the phone
  may raise the limit too"), not in this file, and is deliberately not repeated here.
  **This pointer used to read "recorded above under 'Amended by the owner on
  2026-10-11'" - a heading that has never existed in this file.** The dated decisions
  were moved out to `docs/DECISIONS.md` on 2026-10-12, and this one moved with them
  without the pointer being corrected; fixed 2026-10-13.

**`audit` and `python-advisories` are informational. Six required checks are what
gate a merge** - `rust`, `frontend`, `backend`, `backend-windows`,
`credential-manager` and `powershell-5` - and the ruleset says so itself: a direct
push to `main` was refused with ***"6 of 6 required status checks are expected."***
The owner's evidence for the other half is five merged PRs (#312, #314, #315, #317,
#318) that each had those six green **while `audit` was red**. So **a red `audit` is
a signal to fix `main`'s own state - never a reason to hold a PR.** The cost of not
knowing this was hours of holding mergeable work, which is why it is written here
rather than left to be inferred.
