# antislop

The Anti-Slop filter: `miqdadbadjuber/anti-slop`'s rules, distilled, so Jarvis
writes and builds without the AI tells - no em dashes in prose, no buzzwords or
generic calls to action, no decorative comment banners in code - plus an audit
that measures contrast (WCAG AA, unrounded), finds dead controls and finds a
focus ring that was removed with nothing put back.

**Drop-in, and this one replaces NO patch.** Nothing about `jarvis_hud.py`
changes to add this, and there is nothing in the core to take out: the feature
was born as a folder. Copy this folder into the backend's `jarvis_plugins\`
folder (or run `scripts\add-plugin.ps1 -Name antislop`) and restart Jarvis.

- Module the loader calls: `jarvis_antislop.install()` (takes the core's Handler)
- The patch this replaces: none - this is not a feature that used to be a patch
- Position in the loader's order: 159, after every folder that has one
  (`sandbox` is the highest at 158), so its three paths are checked in the order
  they were added rather than in the middle of somebody else's

The module itself is one of the ones this repository already ships
(`backend/jarvis_antislop.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not change it.

Its three routes:

    GET  /api/antislop          what the filter is set to now. A read.
    POST /api/antislop          change enabled / mode / scopes / dials. No card.
    POST /api/antislop/audit    audit a text, a page or a file. Read-only.

**No approval card, in either direction.** Turning this on opens no network
door, reads no folder, takes no action and loosens no gate: it changes the
WORDS Jarvis writes. Both directions are instant, like the prompt coach, and
every change leaves ONE action receipt with a one-click Undo
(`jarvis_receipts.py`).

That is the owner's own classification, recorded in `docs/DECISIONS.md`
(2026-10-28). If that ever stops being true - if a scope grows something that
reaches outside this PC - it stops being cardless, and the record changes with
it.

## What it sends the model, and what it costs

A compact `<antislop_filter mode="...">` system note, at most 1,050 characters,
scoped to the owner's copy/code/ui switches and carrying the three Liveliness
dials (ENERGY / RHYTHM / MOTION). **Off, it is the empty string: 0 tokens.**
There is no `npx`, no npm, no network install and no second rulebook to read at
run time - the rules are vendored in the module, and `THIRD-PARTY-NOTICES.txt`
carries the MIT attribution.

## Two modes

- **during** (the default when switched on) - filter as it writes: the note,
  plus a deterministic scrub of the words the model already wrote (em dashes in
  prose, decorative comments in fenced code).
- **after** - audit only. The note tells the model to answer with a numbered
  findings list and not to edit anything, and the scrub is bypassed, because an
  audit is allowed to quote the very em dash it reports.

## What it really checks, and what it only guides

The audit report says which is which in its own header, on every run, because a
rule that a regex cannot see must never be described as enforced:

- **Class A, checked here:** `R-02` (with the exemptions below), the `R-10` /
  `R-13` dose caps, `R-15` generic CTAs, `R-16` AI buzzwords, `R-17`/`R-36`/`R-38`
  through `jarvis_claims.py`, the **static** half of `R-24`/`R-26` (dead links,
  unwired buttons), `R-25` unrounded WCAG 2.1 contrast on a static hex pair, the
  **static** half of `R-32` (`outline: none` with no ring put back), and
  `antislop-code` comment banners.
- **Class B, prompt-guided only:** `R-03`'s dynamic overflow and rendered 44x44
  tap targets, `R-18` (is a testimonial fabricated?), `R-20` (the identity test),
  `R-23` (asset confirmation), `R-27` (semantic empty/loading/error states),
  `R-28` (is an FAQ generic?), `R-30` (clone detection) and `R-34`/`R-35` (live
  theme switching and click-through). These need a live browser, a person's
  judgement or the data source; this module guides them and does not check them.

## One rule that wins over the filter

`R-02` bans em dashes in agent-written copy, and `R-37` says a sample of the
owner's own writing is direction. When **Write Like Me** (`jarvis_voiceprint`)
is on and the owner's own samples use em dashes, the ban yields - both in the
prompt and in the scrub. `jarvis_antislop.voiceprint_uses_em_dash()` is the one
place that is decided, and it answers False whenever it cannot read the samples.

The owner can also allow em dashes outright: `allow_em_dashes` (default off)
drops the R-02 line and leaves prose dashes alone while the rest of the copy
scope keeps working, and it is a stored flag rather than a second reading of the
samples. `POST /api/antislop {"allow_em_dashes": true}` is the one door; the
Settings card's checkbox posts the same key.

## What the scrub may never touch

Only the words the model wrote in a chat answer - its prose, and the fenced code
blocks inside it. Never a tool's input or output, a file Jarvis writes, a diff or
a patch, or a file already in a repository; the audit is read-only. Inside fenced
code it removes only a wordless separator line or a comment led by one of ten
decorative emoji. Shebangs, `# -*- coding`, `# type:`, `# noqa`, `# pragma:`,
`// @ts-`, `// eslint-`, Rust `///` and `//!` doc comments, diff headers and any
comment carrying real words are never touched.

