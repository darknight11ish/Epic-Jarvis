# The documents, and which ones are current

There are **290 markdown documents** here, adding up to about **6.8 MB**. Neither
number is a guess, and neither is asked to stay still: the documents are written
to all day, so the count and the size both move. Both were measured on 2026-10-06
with the two lines below, run from the top of the repository - so run them again
whenever you want today's numbers rather than this page's:

```powershell
(Get-ChildItem docs -Recurse -Filter *.md).Count                        # 290 documents
"{0:N0}" -f (Get-ChildItem docs -Recurse -Filter *.md |
  Measure-Object -Property Length -Sum).Sum                             # about 6,760,000 bytes
```

Both lines count the documents in the subfolders too, not only the ones sitting
directly in `docs/`. The count is the honest measure of how much is here; treat
the size as "around 6.8 MB" and re-measure it rather than trusting the digits
above. **Five of the documents are the ones to read**; the rest are the history of
how Jarvis got here: audits, research, and notes that one working session left for
another. One generated file, the source bundle, is **really gone** now: the removal
this page had recorded before it was run was run on 2026-10-05 (see the last table
below), and `.gitignore` carries the path so a regenerated copy cannot come back
tracked - `docs/` is 13.5 MB smaller than it was. Apart from that one file,
nothing had been moved or deleted before 2026-10-06, so every old link still
worked. That changed on 2026-10-06: three more tracked things were deleted - the
vendored telemetry package `tel/`, the stray tarball
`evidence-dev-telemetry-2.1.3.tgz`, and the eyelid preview
`docs/critters/eyelids-preview/`. Nothing referenced any of the four, and the last
table on this page says what each one was. Deleting from the newest commit stops
carrying it forward; it does not shrink a clone that already has it, and
`git show <older-commit>:<path>` still returns the file. This page says which
document is which.

(An earlier version of this paragraph said "about ninety documents", and at some
point it also gave a size of 720 KB for something that had grown far past that -
the source bundle alone was 13.5 MB when it was deleted on 2026-10-05, as the last
table on this page records. Both figures were wrong, which is why the numbers now
come with the commands that measure them.)

If two documents disagree, `ARCHITECTURE.md` wins, and the other one is out
of date.

## Start here

| Document | What it is for |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | **Read first.** How the pieces fit, the rules every feature follows, and the one way anything asks for your OK. |
| [INSTALL.md](INSTALL.md) | Setting Jarvis up on a Windows PC and a phone, step by step. |
| [JARVIS-API.md](JARVIS-API.md) | Every address the two apps call on the PC, and what each one answers. Long; use it as a reference. |
| [MODEL-TOPOLOGY.md](MODEL-TOPOLOGY.md) | Which AI model runs on the graphics card, and how much it can hold in mind. |
| [../backend/README.md](../backend/README.md) | The changes (patches) made to the backend on the PC, and what each one fixes. |

Also current, for one area each:

| Document | What it is for |
|---|---|
| [HARDWARE-PROFILES.md](HARDWARE-PROFILES.md) | Settings for different graphics cards, one card or two. |
| [SECOND-CARD.md](SECOND-CARD.md) | What a second graphics card adds. All built, all off until that feature is measured. |
| [BIG-MODEL.md](BIG-MODEL.md) | The optional slow, bigger model for jobs nobody is waiting on. |
| [WAKE-WORD.md](WAKE-WORD.md) | "Hey Jarvis": how it works and what it needed. |
| [APPROVAL-GAP-DESIGN.md](APPROVAL-GAP-DESIGN.md) | How the PC itself asks Windows Hello before a risky approval (step 1 is built). |
| [SHARED-LOOK.md](SHARED-LOOK.md) | What the phone and the desktop must agree on so they look the same. |
| [APPEARANCE-API.md](APPEARANCE-API.md) | The one address the face and colour picker uses. |
| [UFO-SAFETY-DESIGN.md](UFO-SAFETY-DESIGN.md) | Why controlling Windows apps is done the careful way it is. |
| [LIVE-DESIGN.md](LIVE-DESIGN.md) | "Jarvis Live": a back-and-forth voice conversation, plus the phone's camera (design only, not built). |
| [CAPTCHA-HANDOFF-DESIGN.md](CAPTCHA-HANDOFF-DESIGN.md) | Handing a captcha or sign-in page to the owner's phone ("Solve it here"): the flow, what crosses to the phone and what is never saved, the limits, how the owner stops it, and the questions only the owner can answer. The backend and both apps are built; **never tried against a real captcha or a real phone**. |
| [RETRIEVE-PORT-BRIEF.md](RETRIEVE-PORT-BRIEF.md) | The brief behind the retrieval trace's move to the phone: what `GET /api/retrieve` returns (the matched words themselves - a saved fact, a document, every Logseq page on disk), why the desktop already blanks it while the memory lists are hidden, and the three options the owner chose between. The owner chose **"Just the number"** on 2026-10-08; the built result is section 119 of [JARVIS-API.md](JARVIS-API.md). |
| [LOCAL-APK-SIGNING.md](LOCAL-APK-SIGNING.md) | Building the phone app **on this PC**: why a locally built APK will not install over the app already on the phone (`INSTALL_FAILED_UPDATE_INCOMPATIBLE`, and the uninstall that wipes the pairing token), where the project's signing key must go (`keystore/debug.keystore` at the repository root - **not** inside `jarvis-client/`), that `*.keystore` is gitignored, the helper script that restores the key from the `DEBUG_KEYSTORE_B64` secret and its failure paths, and the SHA-256 fingerprint comparison to run before installing. |
| [OFF-DEVICE-COMPILE.md](OFF-DEVICE-COMPILE.md) | How to compile a few phone Kotlin files and run their JUnit tests on this PC, which has no Android SDK and virtualisation off in its firmware (`tools/offdevice/`). Says plainly what it proves (the touched files compile; the touched tests pass) and what it does not (Gradle's whole-app build and the other ~1900 tests - CI remains the judge), names every stand-in, and has the desktop counterpart (`cargo fmt` / `check` / `clippy` / `test --lib`). |
| [PEERS.md](PEERS.md), [COMPARISON.md](COMPARISON.md) | What other assistant projects built, and what Jarvis took from them. |
| [MEMORY-SCOREBOARD.md](MEMORY-SCOREBOARD.md) | The memory/learning self-test numbers, updated after every change - not a one-day snapshot. |
| [GRAPHENEOS.md](GRAPHENEOS.md) | What to check before moving the phone to GrapheneOS. Nothing needed building yet. |
| [BUG-AUDIT-2026-10-07.md](BUG-AUDIT-2026-10-07.md) | **Start here for the 2026-10-07 audit.** The whole-program bug audit: the nine bugs fixed in its own pull request (including a truncated approval card that could still be approved, and two money-limit holes that had just merged), what was verified and left alone, and the four things left for the owner to decide. The eight working reports behind it are in [audit-2026-10-07/](audit-2026-10-07/README.md). |
| [designs/](designs/) | Draft designs not built yet (an MCP bridge, a skills system), each in its own subfolder with the draft's own README. |
| [FEATURE-REVIEW-2026-10-04.md](FEATURE-REVIEW-2026-10-04.md) | A whole-project feature review (2026-10-04): what Jarvis has, what is missing next to other projects, what to remove, what to change, and the risks. A review, not a plan - it ends with six decisions for the owner. |
| [COMPETITORS-2026-10-05.md](COMPETITORS-2026-10-05.md) | Jarvis next to Meta's Muse, OpenAI's ChatGPT "Dots" and the rest, as of 2026-10-05: the one-page matrix, where Jarvis is ahead and behind, what to copy and what never to copy. Updates the three 2026-09-25 competitor audits. |
| [PATCH-ANCHOR-FRAGILITY-2026-10-09.md](PATCH-ANCHOR-FRAGILITY-2026-10-09.md) | Why one patch in the installer keeps breaking (2026-10-09): forty-one patches insert a block before the same line in `jarvis_hud.py`, each naming the block above it as its context, so every new patch at that line breaks the last one. The failure shows only on the repair pass - which is the one the owner's PC takes. Proposes a sentinel anchor and a test to enforce it, and records a separate malformed patch that blocks installs on its own. |
| [PROMPT-COACH-DESIGN.md](PROMPT-COACH-DESIGN.md) | The design for "Coach this" (2026-10-08): what a prompt coach is, the four open-source libraries the owner was offered and why none of them is used (one needs an OpenAI key and has no local-model support, one is AGPL-3.0 rather than the MIT claimed), the three routes, the switch, and the two questions the owner answered. |
| [COMPETITORS-OPENMUSE-2026-10-08.md](COMPETITORS-OPENMUSE-2026-10-08.md) | Jarvis next to CopilotKit's OpenMuse (2026-10-08), the open-source personal agent with a browser, a terminal and durable background work. The one-page scorecard, where Jarvis is ahead and behind, the ranked borrow list, what never to copy, and where the two projects independently agree. **OpenMuse is the first rival read by this project that is ahead of Jarvis at finishing a job that takes a while** - a lease-and-checkpoint task worker, `outcome_unknown` for an interrupted write, idempotency keys and hash-bound approval are most of the five things worth copying. **It also carries a correction:** the report first listed OpenMuse's IP-pinned egress check as a gap, and Jarvis already had it - the third time this project has "found" something it already had. |
| [BUG-AUDIT-2026-10-05.md](BUG-AUDIT-2026-10-05.md) | A fresh bug hunt (2026-10-05): the cross-cutting pass, what came back clean, the two small defects it found, and the bug class this project actually suffers from. The four deeper area passes follow. |
| [UI-AUDIT-2026-10-05.md](UI-AUDIT-2026-10-05.md) | A user-interface audit of both apps (2026-10-05): what is measurably right (the token and contrast guards, the shared-look contract), what good looks like for an approval-gated assistant, and the findings from all three passes. |
| [DEEP-AUDITS-2026-10-05.md](DEEP-AUDITS-2026-10-05.md) | The four deeper audits (2026-10-05): prompt injection and untrusted text end to end (the rush latch has no caller on the read path), and dependencies, supply chain and what breaks in twelve months. Disaster recovery and performance follow. |
| [AUDIT-PASS-2026-10-05.md](AUDIT-PASS-2026-10-05.md) | **Start here for the 2026-10-05 audit pass.** The timestamped record: what was run, what is still running, the headline results, and a link to each of the five documents. |
| [WORK-ORDER-2026-10-05.md](WORK-ORDER-2026-10-05.md) | What the owner decided after that pass (2026-10-05): the fourteen choices, what gets fixed and in what order, what only the owner can do, and what is deliberately left out. |
| [MEASURED-2026-10-05-owner-pc.md](MEASURED-2026-10-05-owner-pc.md) | **The first real measurement of the owner's own PC.** Both cards are in and working and the model runs entirely on the 12 GB card, so nothing spills onto the processor - and 16,384 tokens of context fits with room to spare. Also records the honest correction about the Ollama log: it does exist, and a search that returns nothing is not proof that a file is absent. |
| [MEASURE-CARDS.md](MEASURE-CARDS.md) | The one-line check to run on the PC (reads only, changes nothing) and how to read what it prints: is the model on a card or partly on the processor, how much room is left, why 16,384 fits, and why the earlier advice to drop to 8,192 was wrong for this machine. |
| [ADAPTIVE-MEMORY-DESIGN.md](ADAPTIVE-MEMORY-DESIGN.md) | Keeping recent conversation exact and compressing older turns in words instead of squeezing the whole window at the bit level (**design only, not built, not approved to build**). Its own answer is "do not build it yet": at 16K the ten turns the apps send already fit, and at 4,096 the tool list is what fills the window, not the conversation. |
| [SETTINGS-MERGE-FINDINGS-2026-10-05.md](SETTINGS-MERGE-FINDINGS-2026-10-05.md) | Why the plan to merge the desktop Settings page from 33 cards to about 20 was **parked**, and what a correct retry must satisfy - read from the test suites, not guessed. The page on disk is the unchanged one, so the owner sees no difference. |

## Audits and research (dated - true on the day written)

Each is a snapshot. Its findings have mostly been fixed since; the fix is
in the git history, and `CHANGELOG.md` at the top of the repository says
what changed when.

| Date | Document | About |
|---|---|---|
| 2026-09-28 | [AUDIT-2026-09-28-AFTER-CHANGES.md](AUDIT-2026-09-28-AFTER-CHANGES.md) and [audit-2026-09-28/](audit-2026-09-28/) | Twelve audits of all five unmerged branches together: bugs, both apps, security, merge clashes, owner decisions, play tests, speed, docs, tools, unfinished work. |
| 2026-09-28 | [UPDATE-AND-CHECK-2026-09-28.md](UPDATE-AND-CHECK-2026-09-28.md) | How to put the new work on the PC and phone, and a checklist that it works. |
| 2026-09-28 | [GEMINI-AUDIT-2026-09-28.md](GEMINI-AUDIT-2026-09-28.md) | The outside (Gemini) audit package for everything since 2026-09-20, with its prompt. |
| 2026-09-28 | [RESEARCH-AUDIT-2026-09-28.md](RESEARCH-AUDIT-2026-09-28.md) and [research-audit-2026-09-28/](research-audit-2026-09-28/) | Every feature next to competitors and GitHub projects; the Brain; what to fix, borrow and speed up. |
| 2026-09-28 | [HARDWARE-DETECTION-AUDIT-2026-09-28.md](HARDWARE-DETECTION-AUDIT-2026-09-28.md) | How well Jarvis detects hardware (graphics cards, Windows Hello, the phone's mic/notifications/battery, RAM and disk), adapts to it, and tells the owner why - every mechanism, not only GPUs. One small wording bug found. |
| 2026-09-27 | [BACKGROUND-WORK-AUDIT-2026-09-27.md](BACKGROUND-WORK-AUDIT-2026-09-27.md) | Everything Jarvis does unattended - the scheduler, standby, briefing, "tell me when", focus, backups, initiative - checked and tested for real. |
| 2026-09-27 | [GPU-SUPPORT-RESEARCH-2026-09-27.md](GPU-SUPPORT-RESEARCH-2026-09-27.md) | What a third graphics card, and AMD/Intel GPUs, would actually need - sized, not guessed. |
| 2026-09-27 | [OFFLINE-MODELS-DESIGN-2026-09-27.md](OFFLINE-MODELS-DESIGN-2026-09-27.md) | Design for viewing installed models in both apps without a running backend. |
| 2026-09-27 | [JARVIS-EVALUATION-2026-09-27.md](JARVIS-EVALUATION-2026-09-27.md) | Are the five core rules too strict, how Jarvis compares to Muse, and whether it actually flows as an assistant - three research passes, synthesized. Two questions for the owner. |
| 2026-09-27 | [BUG-AUDIT-2026-09-27-backend.md](BUG-AUDIT-2026-09-27-backend.md), [-desktop-js](BUG-AUDIT-2026-09-27-desktop-js.md), [-desktop-rust](BUG-AUDIT-2026-09-27-desktop-rust.md), [-phone](BUG-AUDIT-2026-09-27-phone.md), [-cross-cutting](BUG-AUDIT-2026-09-27-cross-cutting.md) | The full bug audit, a team of agents, five reports. Every finding was fixed. |
| 2026-09-27 | [QUALITY-AUDIT-2026-09-27.md](QUALITY-AUDIT-2026-09-27.md), [SECURITY-PRIVACY-DEPS-AUDIT-2026-09-27.md](SECURITY-PRIVACY-DEPS-AUDIT-2026-09-27.md), [SETUP-SETTINGS-RECOVERY-AUDIT-2026-09-27.md](SETUP-SETTINGS-RECOVERY-AUDIT-2026-09-27.md) and [handoff-2026-09-27/](handoff-2026-09-27/) | The three combined audit passes the owner asked for (quality; security/privacy/dependencies; setup/settings/recovery). |
| 2026-09-27 | [EASE-OF-USE-AUDIT-2026-09-27.md](EASE-OF-USE-AUDIT-2026-09-27.md) and [ease-audit-2026-09-27/](ease-audit-2026-09-27/) | How easy Jarvis is to set up, use, understand and customize, for someone new to it. |
| 2026-09-27 | [OWNER-QUESTIONS-2026-09-27.md](OWNER-QUESTIONS-2026-09-27.md) | Short multiple-choice questions for the owner from the audits above. Answered - see CLAUDE.md's decision log. |
| 2026-09-27 | [MEMORY-REVIEW-2026-09-27.md](MEMORY-REVIEW-2026-09-27.md) | A second reviewer's check of the memory/learning self-test claims and bugs. |
| 2026-09-27 | [PERSONA-MODES-CHECK-2026-09-27.md](PERSONA-MODES-CHECK-2026-09-27.md) | Whether the older `[persona]` modes still fit, next to the character block. A look, not a build. |
| 2026-09-26 | [FEASIBILITY-AUDIT-2026-09-26.md](FEASIBILITY-AUDIT-2026-09-26.md) (plan: [FEASIBILITY-AUDIT-PLAN-2026-09-26.md](FEASIBILITY-AUDIT-PLAN-2026-09-26.md)) and [feasibility-2026-09-26/](feasibility-2026-09-26/) | Seven reviewers rank all 155 ideas from the cutting-edge research below. |
| 2026-09-26 | [CUTTING-EDGE-2026-09-26-capabilities.md](CUTTING-EDGE-2026-09-26-capabilities.md), [-engine](CUTTING-EDGE-2026-09-26-engine.md), [-voice-vision](CUTTING-EDGE-2026-09-26-voice-vision.md) | Cutting-edge research, round 1: what Jarvis could do, its engine, voice and vision. |
| 2026-09-26 | [CUTTING-EDGE-2026-09-26-round2-experience.md](CUTTING-EDGE-2026-09-26-round2-experience.md), [-personality](CUTTING-EDGE-2026-09-26-round2-personality.md), [-trust](CUTTING-EDGE-2026-09-26-round2-trust.md) | Cutting-edge research, round 2. |
| 2026-09-26 | [CUTTING-EDGE-2026-09-26-round3-home.md](CUTTING-EDGE-2026-09-26-round3-home.md), [-knowledge](CUTTING-EDGE-2026-09-26-round3-knowledge.md), [-routines](CUTTING-EDGE-2026-09-26-round3-routines.md) | Cutting-edge research, round 3. |
| 2026-09-26 | [CUTTING-EDGE-2026-09-26-round4-character.md](CUTTING-EDGE-2026-09-26-round4-character.md), [-growth](CUTTING-EDGE-2026-09-26-round4-growth.md), [-wellbeing](CUTTING-EDGE-2026-09-26-round4-wellbeing.md) | Cutting-edge research, round 4. |
| 2026-09-26 | [UI-AUDIT-2026-09-26.md](UI-AUDIT-2026-09-26.md) and [ui-audit-2026-09-26/](ui-audit-2026-09-26/) | "Spice it up without overwhelming": a chair's report over six team reports, and a picture page. |
| 2026-09-26 | [BUG-AUDIT-2026-09-26-backend.md](BUG-AUDIT-2026-09-26-backend.md), [-desktop](BUG-AUDIT-2026-09-26-desktop.md), [-phone](BUG-AUDIT-2026-09-26-phone.md) | Bug hunts in each part. |
| 2026-09-26 | [APPROVALS-AUDIT-2026-09-26.md](APPROVALS-AUDIT-2026-09-26.md) | What asks first, and what could stop asking. |
| 2026-09-26 | [PROFESSIONALISM-AUDIT-2026-09-26.md](PROFESSIONALISM-AUDIT-2026-09-26.md) | Packaging, versions, READMEs, wording. |
| 2026-09-26 | [DEPS-TESTS-CI-AUDIT-2026-09-26.md](DEPS-TESTS-CI-AUDIT-2026-09-26.md) | Libraries, licences, tests and the build machines. |
| 2026-09-26 | [CONTINUITY-AUDIT-2026-09-26.md](CONTINUITY-AUDIT-2026-09-26.md) | Do the phone and the desktop offer the same things? |
| 2026-09-26 | [MEMORY-RESEARCH-2026-09-26.md](MEMORY-RESEARCH-2026-09-26.md) | How other projects do memory; the build order it led to. |
| 2026-09-25 | [CREATIVITY-AUDIT-2026-09-25.md](CREATIVITY-AUDIT-2026-09-25.md) and [creativity-2026-09-25/](creativity-2026-09-25/) | Ideas, and one ranked plan. |
| 2026-09-25 | [COMPETITORS-COMMERCIAL-2026-09-25.md](COMPETITORS-COMMERCIAL-2026-09-25.md), [-OPEN-SOURCE](COMPETITORS-OPEN-SOURCE-2026-09-25.md), [-MUSE](COMPETITORS-MUSE-2026-09-25.md) | Jarvis next to other assistants. |
| 2026-09-25 | [GEMINI-AUDIT-2026-09-25.md](GEMINI-AUDIT-2026-09-25.md) | An outside model's audit. |
| 2026-09-24 | [RESEARCH-2026-09-24.md](RESEARCH-2026-09-24.md) | Safety and memory research. |
| 2026-09-23 | [EXTRACTION-RESEARCH-2026-09-23.md](EXTRACTION-RESEARCH-2026-09-23.md), [LEARNING-RESEARCH-2026-09-23.md](LEARNING-RESEARCH-2026-09-23.md) | How Jarvis learns facts. |
| 2026-09-23 | [UI-AUDIT-2026-09-23.md](UI-AUDIT-2026-09-23.md) | The phone app's design (older ones: [09-18](UI-AUDIT-2026-09-18.md), [09-14](UI-AUDIT-2026-09-14.md)). |
| 2026-09-19 | [AUDIT-FINDINGS-2026-09-19.md](AUDIT-FINDINGS-2026-09-19.md) | Bug audit of all four codebases. |
| 2026-09-14 | [AUDIT-2026-09-14.md](AUDIT-2026-09-14.md), [ARCHITECTURE-PANEL-2026-09-14.md](ARCHITECTURE-PANEL-2026-09-14.md) | The first phone audit, and how phone and desktop should relate. |
| undated | [AUDIT.md](AUDIT.md) | The first desktop audit. |

## Out of date - kept for the record only

These are **stale on purpose**: notes between two working sessions (one
building the desktop, one the phone) before they were merged, proposals
that were later built differently, and generated snapshots. Do not follow
them; the current documents above replace them.

| Document | Why it is stale |
|---|---|
| ~~SOURCE-BUNDLE.md~~ | **Removed 2026-10-05, and this time the removal was really run**: `git ls-files docs/SOURCE-BUNDLE.md` lists nothing, and `.gitignore` now carries the path so a regenerated copy cannot come back tracked. It was 13,469,567 bytes of generated output - 13.5 MB of the 19 MB `docs/` was this one file - a copy of the phone app's source at an old commit on a deleted branch, made for an outside audit. The real source is in `jarvis-client/`, and the bundle is regenerated from the tree in one line whenever a reviewer wants it: `py -3 tools/gen_source_bundle.py`, which is still tracked. Git history still has the file (`git show <older-commit>:docs/SOURCE-BUNDLE.md`), so nothing is lost. |
| `tel/`, `evidence-dev-telemetry-2.1.3.tgz` | **Removed 2026-10-06.** These were both the same third-party npm package, `@evidence-dev/telemetry` 2.1.3: `tel/package/` was its unpacked contents (5 files, 9,453 bytes) and the tarball was the download it came out of (3,906 bytes). Its own `index.cjs` opens a `@segment/analytics-node` connection and reports the operating system, Node version, architecture and hashed home directory, so it is a phone-home sitting in a project whose first rule is that nothing leaves the PC. Nothing in Jarvis, the desktop app, the phone app or any workflow imported it - the two words `tel/package` appear in no tracked file. `git show <older-commit>:tel/package/index.cjs` still returns it, so nothing is lost. `.gitignore` already covers `*.tgz` (added 2026-10-05); no new rule is needed for `tel/`, which a `npm install` would recreate anyway. |
| ~~docs/critters/eyelids-preview/~~ | **Removed 2026-10-06.** Four files, 2.83 MB: two "before and after" pictures and the generator that drew them. Its own `README.md:3-4` says it is "a PREVIEW, not part of the app yet" and that "the main branch does not have it" - it did - and `README.md:14-16` says it was "not wired to the animals' poses" and that no golden file changed. The feature was built afterwards and is kept properly in [CRITTERS.md](CRITTERS.md), with its pictures in `docs/critters/eyelids/` (6.77 MB, still here). Its generator imported from `.claude/worktrees/agent-abd7d5ab573657428/`, a worktree that no longer exists, so those pictures could not be drawn again anyway. Nothing pointed at it - no test, no workflow, no document, not the CHANGELOG, which names `docs/critters/eyelids/`. Git history still has it (`git show <older-commit>:docs/critters/eyelids-preview/README.md`), so nothing is lost. |
| [GEMINI-AUDIT-PROMPT.md](GEMINI-AUDIT-PROMPT.md), [GEMINI-AUDIT.md](GEMINI-AUDIT.md), [ASK-GEMINI.md](ASK-GEMINI.md) | Instructions for past outside audits. |
| [HANDOFF.md](HANDOFF.md) | A handover note for the phone app, 15 September. |
| [ANDROID-FEATURE-AUDIT.md](ANDROID-FEATURE-AUDIT.md), [ANDROID-REPLY-2026-09-15.md](ANDROID-REPLY-2026-09-15.md), [ANDROID-REPLY-2026-09-15-GRADIENT.md](ANDROID-REPLY-2026-09-15-GRADIENT.md), [ANDROID-REPLY-2026-09-18-CATCHUP.md](ANDROID-REPLY-2026-09-18-CATCHUP.md), [ANDROID-REPLY-2026-09-18-ENGINE-PARITY.md](ANDROID-REPLY-2026-09-18-ENGINE-PARITY.md), [ANDROID-REPLY-2026-09-18-FEATURE-AUDIT.md](ANDROID-REPLY-2026-09-18-FEATURE-AUDIT.md) | Messages between the phone and desktop sessions, 15-18 September. |
| [CROSS-CLIENT-CONTRACT.md](CROSS-CLIENT-CONTRACT.md), [CROSS-CLIENT-CONTRACT-REPLY.md](CROSS-CLIENT-CONTRACT-REPLY.md), [CROSS-CLIENT-CONTRACT-REPLY-2.md](CROSS-CLIENT-CONTRACT-REPLY-2.md) | The same, about what both apps must agree on. `SHARED-LOOK.md` and `JARVIS-API.md` are the current answer. |
| [ANDROID-VOICE-FALLBACK.md](ANDROID-VOICE-FALLBACK.md), [ANDROID-VOICE-STREAMING.md](ANDROID-VOICE-STREAMING.md) | Early voice problems and a streaming proposal. Voice was rebuilt since (`JARVIS-API.md` section 17). |
| [APPEARANCE-SYNC-PROPOSAL.md](APPEARANCE-SYNC-PROPOSAL.md) | The proposal `APPEARANCE-API.md` replaced. |
| [AUTONOMY-PROPOSALS.md](AUTONOMY-PROPOSALS.md) | Early ideas for richer proposals, live progress and a stop switch. What was built is in `ARCHITECTURE.md` and `JARVIS-API.md`. |
| [API-DISAGREEMENTS.md](API-DISAGREEMENTS.md) | Differences found between the docs and the backend at the time. `JARVIS-API.md` is the current contract. |
| [VIDEO-BRIEF.md](VIDEO-BRIEF.md) | A brief for a launch video, 24 September. |

Other files: [reference/](reference/) holds the original look of the reactor
face; `launcher-icon-preview.png` shows the phone's icon in every shape
Android can crop it to.
