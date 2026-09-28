# The documents, and which ones are current

There are about ninety documents here. **Five of them are the ones to read**;
the rest are the history of how Jarvis got here: audits, research, and notes
that one working session left for another. Nothing has been moved or
deleted, so every old link still works. This page says which is which.

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
| [SECOND-CARD.md](SECOND-CARD.md) | What a second graphics card will add. All built, all off until the card is installed and measured. |
| [BIG-MODEL.md](BIG-MODEL.md) | The optional slow, bigger model for jobs nobody is waiting on. |
| [WAKE-WORD.md](WAKE-WORD.md) | "Hey Jarvis": how it works and what it needed. |
| [APPROVAL-GAP-DESIGN.md](APPROVAL-GAP-DESIGN.md) | How the PC itself asks Windows Hello before a risky approval (step 1 is built). |
| [SHARED-LOOK.md](SHARED-LOOK.md) | What the phone and the desktop must agree on so they look the same. |
| [APPEARANCE-API.md](APPEARANCE-API.md) | The one address the face and colour picker uses. |
| [UFO-SAFETY-DESIGN.md](UFO-SAFETY-DESIGN.md) | Why controlling Windows apps is done the careful way it is. |
| [PEERS.md](PEERS.md), [COMPARISON.md](COMPARISON.md) | What other assistant projects built, and what Jarvis took from them. |
| [MEMORY-SCOREBOARD.md](MEMORY-SCOREBOARD.md) | The memory/learning self-test numbers, updated after every change - not a one-day snapshot. |
| [GRAPHENEOS.md](GRAPHENEOS.md) | What to check before moving the phone to GrapheneOS. Nothing needed building yet. |
| [designs/](designs/) | Draft designs not built yet (an MCP bridge, a skills system), each in its own subfolder with the draft's own README. |

## Audits and research (dated - true on the day written)

Each is a snapshot. Its findings have mostly been fixed since; the fix is
in the git history, and `CHANGELOG.md` at the top of the repository says
what changed when.

| Date | Document | About |
|---|---|---|
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
| [SOURCE-BUNDLE.md](SOURCE-BUNDLE.md) | A 720 KB copy of the phone app's source at an old commit on a deleted branch, made for an outside audit. The real source is in `jarvis-client/`. |
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
