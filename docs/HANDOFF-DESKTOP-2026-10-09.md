# HANDOFF — the desktop half

Written 2026-10-09 for a **third conversation** that owns the desktop app end to
end. Three sessions now run in parallel, split **by surface, not by task list**:

| Session | Owns | Do not touch |
|---|---|---|
| **Android** | `jarvis-client/`, the attached phone | desktop, merging |
| **This one (desktop)** | `jarvis-desktop/`, `src-tauri/` | `jarvis-client/`, the phone, merging |
| **The first session** | The merge pipeline, all PRs, cross-session reconciliation | — |

The split exists because today proved the alternative: a settings search box was
built **twice** by two sessions, and two agents fought over one handset until
neither result was trustworthy. **Your files are yours.** If you need something
in `jarvis-client/`, do not edit it — report it instead.

Repo: `C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main`.
Read **`CLAUDE.md`** at the repo root first: 2,000 lines of the owner's
decisions, and the source of truth for what any setting or control must do.

## The queue, in value order

**1. The two widget approval defects, then theme colours as one source of truth.**
This is the owner's own ordering and the reason is blunt: **nothing else matters
if a click can approve the wrong card.** The approval-gap research already did the
analysis — read `docs/HANDOFF-UI-RESEARCH-2026-10-09.md` (the continuation
document) and `docs/UI-CUTTING-EDGE-2026-10-09.md` Part 14, which covers the open
PRs and **six self-corrections** the research made to itself.

**A fix is already written and hiding on a superseded branch.** The handoff's §2
says: `origin/audit-pass-2026-10-05` and `origin/next-browser-suites` are the same
commit, **all seven of its commits are already in `main` under different hashes**,
and merging it today would be a **net deletion of 754 files — do not merge it.**
But it carries the widget's wrong-card fix as
`jarvis-desktop/src/approval-target.js` + `tests/approval-target.mjs`.
**Lift the file; do not merge the branch.**

**2. Brain: pin Galaxy as DOM/SVG buttons** — the owner chose this next, and the
point is a rule, not a look: *"nothing drawn only on the canvas"* must become a
**fact the build can check**, not a promise. Real buttons pinned by kind mean
keyboard, theming and high contrast come free. Read the handoff's §6 (the ten
Brain directions, and which to pick) and §17 of the research. The other Brain
views, in the owner's order: the plain table (the only fully accessible surface),
then the River timeline.

**3. Docker's settings layer and its route patch** — **blocked, deliberately**,
on PR **#163** (`tools/gen_settings_cases.py`, the settings generator) merging.
That work is written, compiled and proved, and preserved in
`docs/DOCKER-INTEGRATION-SETTINGS-LAYER.patch.txt`; the module itself
(`backend/jarvis_docker.py`) is in PR #175. Do not hand-write a settings row to
work around the block — declare it in the registry once the generator is in.

**4. The desktop half of tutorials** — already built and in PR #173; a step may
name one real control per app, and a desktop control in another Tauri window
(Settings, the HUD, Faces) is answered **in words**, because no script can reach
across windows.

## The desktop's shape, and three things not to do

It is **11 separate HTML documents, each its own webview and its own JS realm.**
`brain.js` at 497 KB is an **ES-modules** problem, `@layer` is the cascade
problem, `<template>` + `cloneNode` is the rendering problem.

* **Do not rewrite the frontend in a component framework** — the runtime would be
  instantiated once per window, and Svelte/Solid need a compiler.
* **Do not swap Acrylic for Mica** — `windows.rs:126-143` already reasons it out
  (Fluent puts Mica on long-lived base layers and Acrylic on transient
  light-dismiss surfaces; a command palette is the canonical Acrylic case; Mica
  needs Windows 11 22000+ and samples the wallpaper rather than blurring what is
  behind). What *is* still worth doing: **measure a drag** of the quickbar and the
  widget, because the ~7 Hz resize throttle covers resizing but not dragging.
* **Do not adopt Material 3 Expressive** — it is beta, it overshoots the project's
  own *"small, slow, eased, never busy"* doctrine, and it is not in `material3`
  1.4.0. Take its **stiffness** with standard damping.

Also already fixed, so do not redo: `imePadding()`, the Settings "Jump to" stale
indices, the missing minimum tap target, and the chrome accent **already derived
from Idle** (`jarvis-link.js:921-1064`) — that predates the audit which said it was
missing. `settings.css` has had `forced-colors` since `f4eaf03f`; **only
`brain.css` lacks it.**

## Traps that cost real time today

* **19 desktop test files read `src/settings.html` as text**, and
  `voice-panel.js:1784` calls `addEventListener` **unguarded** — so a row that
  only exists at runtime throws and aborts that initialiser. Rows go **in the
  file**.
* **`settings.html`'s toggle rows ARE NOW GENERATED** — PR #163 **merged** on
  2026-10-09 (`main` = `58f93e86`), so `tools/gen_settings_cases.py` is on `main`
  and the rows are spliced between `settings-toggles:begin` / `:end` HTML-comment
  markers from the table in `backend/jarvis_settings_registry.py`.
  **Hand-editing a toggle row will be overwritten**, and `test_settings_rows.py`
  will fail until the table matches. Declare rows in the table; regenerate with
  `py -3 tools/gen_settings_cases.py`, and `--check` must print that everything
  matches. (Before #163 merged they were hand-written — if you are on an older
  branch, that is why your copy looks different.)
* **A new Tauri command with no ACL silently does nothing.** Wire `build.rs`,
  `surfaces.toml`, a capability grant and the generated permission toml;
  `check_command_acl.py` and `check_invoke_grants.py` must pass.
* **`cargo test` OOMs this machine** — use `cargo check --offline`.
* **CI only triggers on pull requests**, and **auto-merge is not allowed here**.
  `frontend` takes **~57 minutes**; `main` moves several times an hour, so expect
  "green but not mergeable" and re-check mergeability right before merging.
* **`JARVIS_BACKEND` is set in the shell** and makes some suites fail with a scary
  *"this would have tested the repository's copy"* message — **not** a code
  failure; and an assertion *about the live backend* must run **with** it set.
* **PowerShell has no heredocs** — `git commit -F <file>`, never `git commit -m`
  (a multi-line `-m` silently loses the commit).
* **Fresh GUID-suffixed temp directories only** — `Copy-Item -Recurse` into an
  existing folder **nests** instead of replacing and produces confidently wrong
  results. This caused a completely false failure report today.
* `git checkout --` reverts uncommitted work. `py -3`, not `python`.
  `scripts/apply-patches.ps1` must stay **pure ASCII.**
* **Never log the pairing token** (UTF-8, 43 chars, `CredRead`, header
  `X-Jarvis-Token` — not a bearer token).

## The rules that do not move

Never auto-approve; acting stays blocked while the event stream is stale.
Nothing private leaves the PC. No public tunnel. A client never does
speech-to-text. Non-commercial, sideloaded, never Play. No bulk approval, and
nothing that clears a rush latch. **Jarvis never sends a text message** — auto-send
is forbidden and is not built (`docs/RULE-FLEXIBILITY.md` entry 002). The eight
"must stay fixed" items in the research's Part 15.5 must **not** become settings;
they already have tests that fail the build if they change.

**If a rule seems to need relaxing, that is a finding to report to the owner, not
a change to make.** The process is in `docs/RULE-FLEXIBILITY.md`: a written entry
naming the rule and exactly what is kept, a card that says in plain words *which*
rule is being relaxed, and a line on the "What asks first" page. Only the owner
decides that.

## How the owner wants to be asked

Multiple choice, **one or two questions at a time**, two or three options, one or
two sentences each, **recommendation first and labelled as yours**. Plain words —
they are a beginner developer. Long reasoning goes in the reply or a file, **never
inside the options**. Then **do the work**; do not ask them to approve each step.

## Working practice

* **The owner's app is running** (`%LOCALAPPDATA%\Jarvis Desktop\jarvis-desktop.exe`).
  Don't stop it without saying so. Builds: `node_modules\.bin\tauri.cmd build
  --no-bundle` with `CARGO_TARGET_DIR` pointing at a shared target dir; keep a
  timestamped backup before replacing the installed exe, and check the new exe's
  timestamp is **fresher than the build started** or you will install the old one.
* **Push your work and open a PR.** The first session merges, so do not merge
  yourself — but finished work with no PR number is indistinguishable from work
  that was never done, which is how **seven finished branches** sat invisible for
  hours today.
* Verify with real output, and say plainly what you could not verify. **A test
  that skips is not a test that passes.**
