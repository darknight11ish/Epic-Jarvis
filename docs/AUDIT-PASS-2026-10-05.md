# Audit pass, 2026-10-05 - manifest and results

**Recorded:** 2026-10-04 23:44 PDT (2026-10-05 06:44 UTC)
**Branch:** `fix/2026-10-04-audit-pass`
**Tree:** `fb1433fd` plus the five documents below (nothing else in the product was
touched)
**Scope:** a whole-project review asked for by the owner, run as fourteen
read-only passes over the repository, the owner's live backend
(`C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program`) and the
state folder (`C:\Users\pcadmin\.openjarvis`). Nothing was built, fixed, removed
or edited in the product.

## Why this document exists

The five audit documents are dated in their filenames but carry no exact time, and
two of the fourteen passes were still running when they were written. This page is
the timestamped record: what was run, when, what it found at the top level, and
what is still outstanding. The owner can read it first and follow the links.

## The five documents

| Document | What it holds |
|---|---|
| [FEATURE-REVIEW-2026-10-04.md](FEATURE-REVIEW-2026-10-04.md) | What Jarvis has; what is missing next to other projects; what to remove; what to change; the risk register; complexity; the owner-facing side; a seven-step plan and six decisions |
| [COMPETITORS-2026-10-05.md](COMPETITORS-2026-10-05.md) | Meta Muse, OpenAI ChatGPT "Dots" and the rest; the capability matrix; where Jarvis is ahead and behind; what to copy and what never to copy; what changed since the project's own 2026-09-25 audits |
| [BUG-AUDIT-2026-10-05.md](BUG-AUDIT-2026-10-05.md) | Cross-cutting checks plus four area passes (backend, desktop front end, Rust, Android); the live-backend patch proof; fourteen silent failures and the guards that would catch them |
| [UI-AUDIT-2026-10-05.md](UI-AUDIT-2026-10-05.md) | What is measurably right (token and contrast guards, the shared-look contract); what good looks like for an approval-gated assistant; the phone, desktop and cross-app passes; corrected counts |
| [DEEP-AUDITS-2026-10-05.md](DEEP-AUDITS-2026-10-05.md) | Prompt injection and untrusted text end to end; dependencies, supply chain and what breaks in twelve months |

## The fourteen passes, and their state at this timestamp

**Complete (12).** External feature research; backend capability inventory;
desktop audit; Android audit; decision-log conformance; privacy/security and the
five rules; repository and code hygiene; user-facing sprawl; independent
verification of the headline claims; the bug hunt in four areas (backend Python,
desktop front end, desktop Rust, Android Kotlin - the last four counted
together); the UI audit in three areas (phone, desktop, cross-app); prompt
injection end to end; dependencies and supply chain.

**Complete: all fourteen.** External feature research; backend capability
inventory; desktop audit; Android audit; decision-log conformance; privacy/security
and the five rules; repository and code hygiene; user-facing sprawl; independent
verification of the headline claims; the bug hunt in four areas (backend Python,
desktop front end, desktop Rust, Android Kotlin); the UI audit in three areas
(phone, desktop, cross-app); prompt injection end to end; dependencies and supply
chain; **disaster recovery and data integrity**; **performance, resources and
battery**; and an **open-findings register** that re-checked the project's own
1,132 earlier findings against today's tree (408 already fixed).

The last three are in [DEEP-AUDITS-2026-10-05.md](DEEP-AUDITS-2026-10-05.md) §3-§5.
Three findings there outrank everything in the earlier sections:

1. **The desktop widget can approve the wrong card** - the queue handler shows
   `items[0]` with no swap guard, so a click aimed at a card decided elsewhere
   acts on whatever slid into slot 0 (`widget.js:1731-1733`).
2. **The owner-voice gate fails open for a blend with no voice print trained** -
   Ashby and Clara are spoken with no voice check at all
   (`jarvis_voices.py:1922-1925`).
3. **The shipped everyday configuration may already be spilling to the
   processor** - the project's own arithmetic puts it ~0.6 GiB over an 8 GB card,
   which would make every answer several times slower, and the one-line check has
   never been run (`MODEL-TOPOLOGY.md:153`).

And one structural cause: **141 suite lines print SKIP as PASS**
(`check("SKIP …", True)`), which is why several of these went unnoticed.

## The headline results

1. **The 12 GB card is installed and nothing is measured.** `nvidia-smi` reports
   an RTX 2060 12 GB and the RTX 2080 SUPER 8 GB; about a dozen built features are
   still switched off "until the second card is installed and measured", and no
   document says the facts changed.
2. **Fourteen of the worst defects are features or tests that silently do
   nothing** - the cloud escalation button with no transport, the plan card gated
   on a missing file, "Grade this better" with no permission grant, **all spoken
   audio** (CSP `media-src` lacks `data:`), the "What Jarvis can see" privacy
   section, the Faces window's state, the HUD's live event stream, 46 of 56 local
   UI suites, and six assertions that are `... or True`. None throws; several
   shipped in pull requests that reported green checks.
3. **The live backend is exactly base + stack:** all 119 patches that the
   installer applies reverse-apply cleanly, 119 of 119.
4. **One gap has nothing else standing in front of it:** the rush latch
   (`jarvis_content_risk.py`) exists, is tested, can only add a card - and has no
   caller on Jarvis's own read path, so a hostile page saying "approve now, before
   it expires" reaches the model with no flag set.
5. **The install cannot be done by a second person:** the backend has no download
   at all, the desktop has no installer, and both blockers are unchanged since the
   project's own ease audit.
6. **Both named rivals moved toward Jarvis's design** - Dots' read-only background
   research and per-app rules, Muse's host-side Sentinel - while charging $20-$500
   a month for it. Muse's "Allow Always" leaked a home address to a stranger.

## The decisions this pass produced

Eleven choice groups, each with a recommended option, are in the hand-off message
that accompanied this pass; the detail behind every one of them is in the five
documents above. The two that block the most other work are **measuring the 12 GB
card** and **fixing the fourteen silent failures**, because a dozen queued
features depend on the first and the second is the class of bug this project
actually suffers from.
