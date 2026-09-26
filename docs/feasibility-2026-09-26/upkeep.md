# Feasibility audit - the Upkeep reviewer (2026-09-26)

**My question:** what does each idea cost to keep working after the day it
is built? Tests (backend, desktop, phone), the CI burden (the phone compiles
only in CI, about 15 minutes a round), docs, new dependencies (other
people's code Jarvis would rely on) and how they are kept current, and how
the idea could quietly stop working without anyone noticing ("silent rot").

Read-only. Every claim about Jarvis's code below was checked in the file and
is cited as `path:line` from the repo root. Where I did not check, I say
"not checked". Line numbers are HEAD (`e656093`) unless I say otherwise:
another agent is editing `backend/jarvis_agent.py` in the working tree right
now (`git status` shows it modified), so its working-tree lines differ.

---

## 0. What I checked first - the upkeep machinery Jarvis already has

These are the facts the verdicts lean on.

1. **Backend tests run in CI, but only the ones that need no owner file.**
   `backend/run_suites.py:167` runs every `backend/test_*.py`; 19 suites that
   test patches against `jarvis_hud.py`, `jarvis_gate.py`,
   `jarvis_extract.py` or `jarvis_models.py` are SKIPPED in CI
   (`backend/run_suites.py:51-71`), because those files live only on the
   owner's PC. They run only when the owner runs `apply-patches.ps1` without
   `-SkipTests` (`scripts/apply-patches.ps1:1517-1533`).
2. **The backend itself has no version control.** "this repo is
   version-controlled and the thing it patches is not"
   (`docs/ARCHITECTURE.md:1174-1176`). There are now **67** patches in
   `apply-patches.ps1`'s list (`scripts/apply-patches.ps1:87`, counted by
   unique name), applied in order. Every idea that must patch an owner-only
   file grows that stack and gets only PC-side testing. Ideas that can ship
   as a whole new module are much cheaper to keep ("New capability that is a
   whole module ... ships as a file", `docs/ARCHITECTURE.md:1185-1188`).
3. **Python dependencies are not pinned and nothing checks them.**
   `backend/requirements.txt:17-26`: only `ddgs>=9.16.0` has a version floor;
   everything else is bare. CI installs whatever is newest on each run
   (`.github/workflows/ci.yml:141`). There is no Dependabot, Renovate,
   `pip-audit` or other advisory scan anywhere (grep of `.github/`,
   `tools/`, `scripts/`: no hits; `.github/` holds only `workflows/`). Rust
   is the only side with an advisory and licence check
   (`cargo deny check licenses advisories`, `ci.yml:445`). The phone's
   libraries are pinned by hand (`jarvis-client/app/build.gradle.kts:284-360`)
   and nothing checks them for updates either.
4. **One guard does exist:** `backend/test_shipped_modules.py:61, 252-284`
   fails if a shipped module imports a package that is not named in
   `requirements.txt`. And the backend starts without any listed package -
   each is imported inside a `try`, "and nothing on screen says so"
   (`backend/requirements.txt:8-11`). So **a missing or broken new package
   switches its feature off silently** unless the feature adds its own
   preflight line.
5. **Every backend change also runs the phone's CI.** The phone workflow
   triggers on `backend/**` (`.github/workflows/jarvis-client.yml:14`),
   because the phone's tests read backend files. So even a PC-only idea
   costs a phone build and emulator run.
6. **The good pattern: shared "golden" case files.** One generator writes
   the same cases for Python, the desktop and the phone
   (`tools/gen_hardware_cases.py:1-24`; 16 such files in
   `jarvis-client/app/src/test/resources/contract/`). The Python side can be
   checked in this container, so the phone's CI round mostly confirms, rather
   than discovers. Any two-app idea should use this.
7. **Enforced checklists already make each new action pay a fixed "tax":**
   a "What asks first" row (the test fails if any card action is missing,
   `backend/test_asks_first.py:92-94`), card words shared by both apps
   (`jarvis_card_words.TITLES`, `tools/gen_card_words_cases.py`), a
   "What Jarvis can reach" row for anything that reaches outside
   (`docs/ARCHITECTURE.md:1570-1572`, `backend/jarvis_reach.py:692`), a
   parity decision (`tools/check_parity.py:43-56`), and a JARVIS-API section
   (the file is 5,496 lines, 36 sections). That tax is good - it is what
   keeps the two apps honest - but it means even an "S" idea that adds an
   action touches six or more places.
8. **Live-model measurements are PC-only and nothing records when they last
   ran.** The tool test (`tools/tool_eval/README.md:1-25`) sends requests to
   Ollama; CI only checks that it imports and reads the real tool list
   (`backend/test_tool_text.py:121-134`). The memory test has a CI-safe
   "words only" mode (`backend/test_memory_recall.py:459-462`). About 20 of
   the ideas below are gated on "measure first" - and nothing in the
   preflight says "last measured N days ago".
9. **The phone's tests use stand-in voice models.** The real wake-word
   model's agreement with the PC was checked once, by hand, on a desktop JVM
   (`jarvis-client/app/src/test/java/com/jarvis/client/WakeListenTest.kt`,
   header comment). A model swap (I15, I22, I23) needs that manual check
   redone.
10. **Design drafts parked outside CI rot.** The MCP draft's wiring patch
    (`docs/designs/mcp-draft-2026-09-23/jarvis-agent-mcp.patch`, 2 hunks)
    **no longer applies** to HEAD's `backend/jarvis_agent.py`: I ran
    `git apply --check` on a scratch copy (not the repo): "patch failed:
    jarvis_agent.py:743". The code it edits has moved to
    `backend/jarvis_agent.py:3861` and been restructured. Its tests
    (`test_mcp.py`, `test_agent_wiring.py`) are not run by CI, because
    `run_suites.py` only looks in `backend/`. Three days was enough.
11. **The "tell me when" module branches on its two sources by name** in at
    least eleven places (`backend/jarvis_tellme.py:249, 254, 304, 310, 348,
    385, 393, 429, 473, 759, 842`). Eight ideas below add a third, fourth ...
    source.
12. **Hand-synced lists have already drifted once.** The router's private
    word list "said it was 'kept in sync ... by hand', and it was not -
    nothing read it at all" (`backend/rebuilt/jarvis_router.py:127-131`).
    And the phone hard-codes the manner list
    (`jarvis-client/app/src/main/java/com/jarvis/client/net/Manner.kt:26-44`),
    so any new preset needs a phone release.

### Key for the table's upkeep column

- **B** backend suite (runs in CI). **B-own** a patch test on an owner-only
  file (skips in CI, runs only on the PC). **D** desktop tests (Playwright
  pages on Linux CI; `cargo test` on Windows CI). **P** phone JVM test (CI
  only, ~15 min). **G** a shared golden-case file via `tools/gen_*_cases.py`.
  **PC** measured on the owner's PC with the real model or hardware only.
- Docs: **API** a JARVIS-API section; **A4** ARCHITECTURE §4 egress row;
  **A8** §8 "One-sided on purpose" row; **REACH** a `jarvis_reach` row;
  **ASKS** a "What asks first" row + card words; **SET** a setting in both
  apps.
- **Dep** a new dependency, with how to keep it current.

---

## 1. One row per idea

| id | verdict | reason (plain words) | upkeep cost: tests, CI, docs, dependencies, how it rots |
|---|---|---|---|
| I01 | build | Small, pure code, and it replaces a wrong error message. | B with a recorded `/api/show` reply. Rot: if Ollama renames its "capabilities" field, the check must fall back to today's behaviour (send tools) and WARN in the preflight, never quietly turn tools off. |
| I02 | build | One setting; cheap second lock behind rule 1. | Lives on the owner's PC, outside Jarvis's code, so it can vanish after an Ollama reinstall. Needs a preflight line that reads it (B for the check). PC test that `ollama pull` still works. |
| I03 | build | Numbers only; it is the measuring stick for I04, I06, I07, I107. | B from a recorded Ollama reply. Rot: field names change between Ollama versions (names not checked); missing field should read "not reported", not 0. |
| I04 | build later | A second retry path that only runs on failures is rarely exercised and rots; first let I05 show how often broken arguments happen. | B with a fake Ollama; PC re-measure per model. Depends on Ollama's schema-constrained output, which varies by model. |
| I05 | build | Owner chose; extends an existing tool. | New cases in `tools/tool_eval/jarvis_tool_cases.py`. CI only checks it imports (`test_tool_text.py:121-134`); scoring is PC only. Guard: results file dated, preflight shows its age. |
| I06 | build | Owner chose; must come before MCP. | M. B test that fails when any tool in `jarvis_agent.TOOLS` is in neither "core" nor "more" - otherwise every future tool silently lands in the wrong list. Tool test must score both modes. API. |
| I07 | build | Owner chose. Heaviest upkeep in the set (spec churn, SDK, third-party servers), so keep it small. | L. Move the draft into `backend/` so CI runs its fake-server tests (the draft's patch already no longer applies, §0.10). Dep: MCP Python SDK + each server, versions pinned with hashes in one file; one server first (git, read-only). New spec (2026-07-28 per ENG) means two protocol versions to test. REACH, A4, ASKS, API, both apps' server list. |
| I08 | build later | Second card; one Modelfile line, but an open Ollama bug can make it 10x slower (per ENG). | PC measure per model and per Ollama upgrade; a preflight speed line catches a regression. |
| I09 | no objection | A measurement run, no code to keep. | Uses I05's tool; downloads only. |
| I10 | build later | Waits for the card. | Update `jarvis_second_card.py`'s plan table and the second-card golden cases (`tools/gen_second_card_cases.py`); PC measure. |
| I11 | build later | L, tied to one vision model's accuracy and to app layouts that change; every model change means re-measuring. Build I27 (points, acts on nothing) first and only add clicking if it earns it. | PC only; screenshot fixtures go stale with each app update. |
| I12 | build | Small Rust fix at `jarvis-desktop/src-tauri/src/commands.rs:2617` (first line only) plus both apps' Hardware screen. | Extend `tools/gen_hardware_cases.py` (G) with a two-card nvidia-smi output; D (cargo test on Windows CI), P. Low. |
| I13 | build later | Measure once per card; the numbers go stale when drivers change, and value is modest. | The PowerShell line lives in docs, not a `.ps1`, so the 5.1 CI job (`ci.yml` "powershell-5") does not parse it: run it through `/opt/pwsh/pwsh` and read for 5.1 by hand. |
| I14 | build | Owner chose. Pick ONE OCR engine, and prefer the one CI can run. | Dep: RapidOCR (pip + ONNX model files, runs in Linux CI) or Windows OCR (a Windows-only winrt package; needs a windows-latest job like `credential-manager`, `ci.yml`). B with a small fixed PNG. Outside-text tagging test in B. API, both apps. |
| I15 | build | Owner chose. | Training is a one-off needing a GPU and Piper voices: commit the recipe as a tool (precedent: `tools/train_stopword.py`). Model ships twice: APK assets (`OrtWakeModels.kt:85-88`) and the PC's voice-models folder - add a hash check that both are the same file. Phone ONNX runtime is pinned at 1.22.0 (`build.gradle.kts:358`), PC's is unpinned: test the model on both versions. Redo the hand check behind `WakeListenTest.kt`. PC 110-clip re-measure. |
| I16 | build | Owner chose. | Needs `sherpa-onnx>=1.12.24` (per VV) but `requirements.txt:18` has no version: add the floor. The voice-copying weights sit behind a sign-up (per VV), so `apply-patches.ps1` cannot fetch them: a written manual step. Third engine in `jarvis_voices.py`: each engine multiplies voice tests. If it wins the timed test, retire an engine rather than keep three. |
| I17 | build later | Waits for the card. | Another model to keep; measure with `say_timings()`. |
| I18 | build later | Known bug (~20% empty or invented text, per VV); behind an off switch. | The name list is rebuilt from HA and contacts; test that a renamed device drops out. B. PC measure. |
| I19 | build later | An always-listening background part that can fail silently (mic unplugged, driver update) - bad for "smoke alarm" even with "not a safety device". Only with a "still listening" line in the preflight and on Coming up. | New model dep; new tellme source (see §0.11); both apps. PC measure of false alarms. |
| I20 | build later | Only if Qwen 3.5 9B proves weak at documents. | Another model to keep; skip unless needed. |
| I21 | build later | Kept only if word errors drop; small. | PC measure with the owner's recordings; ships via sherpa-onnx (already a dep). |
| I22 | build later | Worth it, but it changes the listening front in both apps; do it with I15 and measure together. | Model asset in APK and on PC; phone JVM tests use stand-ins, so real-model check is manual; TEN VAD's licence has extra terms (per VV) - prefer Silero. G for thresholds. |
| I23 | build later | Only if real numbers show the voice check letting others in. A new voice-ID model means the owner's stored voice print must be re-enrolled and every threshold re-measured (my inference; not checked in code). | PC measure; re-enrol flow in both apps. |
| I24 | don't build | Swapping the just-built F5 lane for another heavy PyTorch voice stack is churn with no measured problem to fix; these projects move fast. Revisit only if F5 fails a measured need on the new card. | Would add CUDA/PyTorch pins, a worker, re-measure. |
| I25 | don't build | The research itself says no local detector is reliable in 2026. | - |
| I26 | build later | Low upkeep (a word list and a comparison) and it is the real answer to replayed recordings; the owner's call. | B for the word check; both apps show the words (G). |
| I27 | build later | Waits for the card; acts on nothing. | PC measure per vision model. |
| I28 | build | Tiny, both apps, no card. | SET in both apps; G for the allowed values; B, P. |
| I29 | don't build | stable-diffusion.cpp builds plus multi-GB model files, each with their own update cycle, model juggling on the card, and a face-safety refusal to maintain - for a "nice to have". | Would be a new binary dep, model downloads, PC-only tests. |
| I30 | don't build | Fun, low value, a whole new model family to keep. | - |
| I31 | no objection | Already merged into HEAD (`git merge-base`: `9abdd68` is an ancestor). | Rot: the model name is fixed (`backend/rebuilt/jarvis_memory.py:483`) but fastembed is unpinned (`requirements.txt:20`) and downloads the model at first use. Re-run `eval_memory.py` after any fastembed upgrade. |
| I32 | no objection | Merged (`c33b5f0` in HEAD). | CI runs its words-only mode already. |
| I33 | no objection | Merged (`d2d8831` in HEAD). | - |
| I34 | no objection | Merged (`eee9b03` in HEAD). | - |
| I35 | build later | Another model call per saved fact and a new thing Erase must wipe. | B test that Erase also wipes the hints; re-measure with the memory test. |
| I36 | build | Small re-order only; cheap to test. | B via the memory test's words-only mode. |
| I37 | build | Owner chose; its precondition (I31-I34) is now in HEAD. | M. A scheduler kind (`register_kind`), cards only. B with a fake clock; PC run on the owner's data. API, both apps' Coming up. |
| I38 | build later | The owner said wait. | - |
| I39 | build | High value, small. Pick ONE search back end. | Everything's `es.exe` is a separate install the owner must keep updated; Windows' own index needs no install but a COM/ADO path (not checked). Either is Windows-only: stub in B, real check in a Windows CI job or the preflight. Reuse `file_read`'s refusal list (`backend/jarvis_agent.py:207-224`), not a copy. |
| I40 | build | Owner chose. | Dep: MarkItDown with document extras only. Add a B test that fails if `requirements.txt` names `markitdown[all]` or the audio or YouTube extras (they reach Google and YouTube, per R3-KNOW). Pin it: 0.1.x is young (per CAP, 0.1.8). |
| I41 | build later | The search half of I40; M-L and a new index file to keep in step with the folders. | Index rebuild and "folder removed" tests in B; which folders is the owner's call. |
| I42 | build | Trust value is high and the quote check is plain code. | M, both apps. G for the "sources" payload; B for the word-for-word check; P, D rendering. |
| I43 | no objection | Small and model-free. | Depends on finding today's daily note - the same gap I51 addresses. B. |
| I44 | build later | Four small parts; each one more report to keep. | B for each part; the wiki card already exists. |
| I45 | build later | A new, fast-moving dependency whose locked-down settings must be re-checked on every upgrade (new versions add file and network functions). | Dep: DuckDB, pin exactly. B test that each "switched off" setting really refuses (file read, network, extensions) - that test is the upkeep. Separate process, time limit. |
| I46 | build later | Needs ffmpeg, an outside program the owner must install and update. | Share code with voice memos; B with a tiny audio file. |
| I47 | build later | Small, one browser first. | Bookmarks file formats differ per browser; B with fixture files. |
| I48 | don't build | Browser history databases are locked while the browser runs, their layout changes, and the banking/health exclusion list needs upkeep forever - for a very private, modest-value feature. | Would need per-browser fixtures and a copied-file dance. |
| I49 | build later | Feeds break silently (moved addresses); needs a "last fetched OK" line. | Dep: feedparser (BSD, stable). A4, REACH, ASKS, API. |
| I50 | build later | Desktop only. | A8 row; D. |
| I51 | build later | Obsidian's CLI is new; its command list and output may change with Obsidian updates, and it needs Obsidian running. | Allow-list test in B; preflight line "Obsidian CLI found / version". |
| I52 | build | Detect-only half is a small file check. | B with a fake database-graph folder. The dry-run half waits for I07. |
| I53 | build | Owner chose. | S-M. B with a fake IMAP server (APPEND to Drafts; Gmail's folder name differs, `[Gmail]/Drafts` per CAP). A4 row, ASKS, API. |
| I54 | build later | Desktop only. | vCard parsing is messy; B with fixture files; A8 row. |
| I55 | don't build | The owner's calendar is Google (read by its private iCal link, CLAUDE.md), so this serves nobody today and adds a CalDAV library to keep. | - |
| I56 | build later | After I14; relies on NAPS2 or Windows scanning and on scanner drivers. | PC only; outside program to keep. |
| I57 | build later | py-fsrs has changed its parameter format between major versions (not checked here - check before pinning). | Dep pinned; B with a fake clock; a scheduler kind. |
| I58 | build | The first step is only a fixed prompt. | B for the prompt; the dedicated-model step waits. |
| I59 | build later | Typed only for now; one more prompt mode. | B. |
| I60 | build later | M; every "explain this error" prompt needs a behaviour test. | Belongs in I133's test. |
| I61 | build later | M, touches the gate (an owner-only file, so B-own only) and the "approves in bulk" rule needs the owner's reading first. | B-own; G for the plan card; both apps; ASKS, API. |
| I62 | build later | Builds on I61. | Same as I61 plus saved-routine migrations when a tool's arguments change. |
| I63 | build | Small, no model, one scheduler kind. | Must be declared on the scheduler (a new kind asks by default, `ARCHITECTURE.md:1545-1550`). B with a fake clock; both apps' Coming up; API. |
| I64 | build later | Needs the model and the second card for stage 3. | - |
| I65 | build later | Every tool must declare how it is undone or "cannot be undone"; that grows with every tool forever. Needs the owner's `jarvis_undo` read first (not in this repo, `git ls-files`). | B test that fails when a tool declares neither. B-own. |
| I66 | build | Useful, S-M each - but refactor "tell me when" into a source list first (§0.11). | After the refactor: one module per source, B each, both apps' setup screen. |
| I67 | build later | A new way out of the PC, decide with I49. | A4, REACH; "last fetched OK" line. |
| I68 | build | Owner chose. A long-open connection can die quietly and look exactly like "no new mail". | Dep: IMAPClient (BSD) - or a hand loop, fewer deps. Must re-issue IDLE before 29 minutes (the IMAP IDLE standard's limit, not checked in the report), reconnect, and fall back to the 5-minute look. B with a fake IMAP server that drops the connection. Preflight: "mail server last heard from N minutes ago". Tie to Stop everything and Standby. |
| I69 | build | Small, same module as I68. | B with a fake clock ("no match by Friday"). |
| I70 | build later | Must merge with the existing GitHub watchlist, which lives in an owner-only module (`jarvis_watch` - not in this repo). | Token handling per rule 3; B-own. |
| I71 | build later | Second card; the big model has no standby flag (per R3-ROUT). | - |
| I72 | build later | M-L. | Quote check shared with I42. |
| I73 | build | Owner chose, queued. Phone-heavy, CI-only compile. | P for the listener; the one-time-code masker in ONE place with G cases so phone and PC agree (not a new regex beside `jarvis_mail_mask.py`). Android's "restricted settings" for sideloaded apps (not verified) needs a written step. SET both apps, ASKS, API, A8 if one-sided. |
| I74 | build later | A night-shift candidate. | - |
| I75 | build | Owner chose; small. | HA's forecast is a service call whose shape HA has changed before (not checked in which release). Record a real reply as a B fixture; preflight line. The briefing's "not available" line is at `backend/jarvis_briefing.py:117-118, 338`. |
| I76 | build later | Small, modest value. | HA logbook reply fixture in B. |
| I77 | build later | Two device lists (Jarvis's and HA's) will drift; only worth it via HA's own API, with I78's client, not via HA's MCP server (no entity ids, per R3-HOME). | Dep shared with I78. |
| I78 | build later | Good value, but brings a WebSocket client (a new dep) and HA's WebSocket API. | Dep pinned; B with a fake HA; G for the room card. |
| I79 | build later | M, several signals, each can go stale. | Per-device setting in both apps. |
| I80 | build later | Needs I78. | - |
| I81 | build | Mostly a guide and one preflight WARN. | B for the WARN. |
| I82 | build | Already works through the "home" source (per Fit, `jarvis_tellme.py:310-336`); a doc and an example. | Docs only. |
| I83 | build later | M; its own card. | - |
| I84 | build later | After I12. | - |
| I85 | build later | Several signals and offers. | Back-off `OFFERS` kind (`ARCHITECTURE.md:1557-1569`). |
| I86 | build later | Each briefing line depends on the owner's HA entity names; many small lines, each can go stale. | Per-owner config; B per line. |
| I87 | build later | Writes to HA; the owner's choice of card. | B with a fake HA. |
| I88 | don't build | L, reads HA history, a new learning loop - high upkeep for an unmeasured gain. | - |
| I89 | build later | Needs a real network to test. | P for the packet; PC/HA side is setup docs. |
| I90 | don't build | Windows wake timers depend on power-plan settings and may need an administrator prompt (not verified); a sleep/wake bug means a missed alarm, and nothing in CI can test it. I93 already rings alarms on the phone with the PC off. | - |
| I91 | build later | Windows media controls need a Windows-only winrt package (per CAP) that updates often and cannot be tested on Linux CI. | Needs a Windows CI job or stubs; ASKS setting. |
| I92 | build later | List half only; winget output format changes. | B with fixture output. |
| I93 | build | Owner chose; small; phone intents. | P; A8 row (phone only). |
| I94 | no objection | Small phone intent; the owner sends. | P; A8 row. |
| I95 | build | Extends an existing CI suite (`backend/test_injection_cases.py`, corpus `backend/agentdojo_injections.json`) with a PC run on the real model. | PC only for the count; date the result. |
| I96 | build | Worth it, but an untested restore is not a backup. | Dep: `age` (pin). B round-trip test (backup, restore) on made-up data, AND a stored backup made by today's version that every later version must still restore - memory's layout changes often (I33, I34 just changed it). Preflight backup age (I97). |
| I97 | build | Small, read-only, WARN only. | B. |
| I98 | build | Small Rust logic in `jarvis-desktop/src-tauri/src/sidecar.rs` (no automatic restart today; grep). | D (`cargo test` on Windows CI) for "3 in 10 minutes then stop". |
| I99 | build | Small. | B; scrub test reuses `jarvis_scrub.py`. |
| I100 | don't build | A standing registry setting whose dumps can hold the token; a one-off how-to is enough. | - |
| I101 | build later | Only after I96; a cleared security chip would lose history for good. | Windows-only; PC test. |
| I102 | build | Owner chose. L, both apps, crypto. | G for the QR payload and expiry; P, D, B. Migration from today's single token to per-device keys needs its own test. Offline attestation checks embed Google's root certificates, which Google rotates (not checked when) - one file, with a "checked on" date. |
| I103 | build | Owner chose, inside I102. | B for signature checks with test keys; P. |
| I104 | build later | Half built (per Fit, `jarvis_agent.py:2615-2684`); every future tool must declare its sensitive arguments - enforce with a B test. Let I95 decide. | B test that fails on a tool without a declaration. |
| I105 | build later | Only if I95 shows fewer attacker cards. | A second model pass to keep in step with the tool loop. |
| I106 | don't build | A parallel "masked" re-run must track every change to the tool loop and doubles model calls; if I95 shows a need, I104 or I105 cover it with less to keep. | - |
| I107 | build later | S; measure with I95 (may hurt reading). | B for the marking. |
| I108 | don't build | Duplicates the existing "looked like planted instructions" warning (`backend/test_injection_cases.py` header), adds a model whose licence is unchecked. | - |
| I109 | build later | The existing ledger is in an owner-only module (`jarvis_ledger`, not in this repo) - read it first. | B-own. |
| I110 | build | Small, stricter only, both apps. | G for the delay rule; P, D. |
| I111 | build | Do the **pinning half now** (hash-locked requirements), before the new deps above arrive; the staged install later. | Pins need a monthly "update the pins" routine or they rot the other way (stuck on old, vulnerable versions). Add a Python advisory scan to CI next to `cargo deny`. |
| I112 | build later | Owner-side Tailscale setting; the `whois` half is small. | B with a fixture reply. |
| I113 | build | Merge the waiting commit (`e372eb7`, not in HEAD); the lock-screen half is one XML attribute (the widgets already say `home_screen` only, `jarvis-client/app/src/main/res/xml/widget_approval_info.xml:18`). | P; one CI round. |
| I114 | build | Small, both apps. | D (Rust clipboard format), P. |
| I115 | build | Small, but must reuse the existing masker, not add another. | B; share with I73 (one code detector). |
| I116 | build | Only if the list is generated from the no-model commands' own code and served by the PC, so the phone needs no release when a command changes. | B test that every fast-path command has an example; API route; P, D. |
| I117 | build later | M; overlaps the briefing and Coming up. | Reuse the briefing builder; G. |
| I118 | build later | After I117. | - |
| I119 | build later | After I102 (pairing by QR is one of its steps). | Reuses preflight checks. |
| I120 | build later | An installer change (Send To shortcut). | Desktop release workflow; D. |
| I121 | build later | After I40. | P, B. |
| I122 | build later | The phone tile is small; for the PC half, not checked whether Windows exposes Focus state through a documented interface - if it does not, drop that half (it would break on a Windows update). | P for the tile. |
| I123 | build later | Another special Android permission to explain and keep working. | P. |
| I124 | build later | Live Updates are Android 16 only while the app supports Android 13 up (`build.gradle.kts:79-80`): two code paths on the phone. | P; D (`winrt_toast.rs` exists). |
| I125 | build | A static shortcuts file (none today, `jarvis-client/app/src/main/res/xml/`). | P; one CI round. |
| I126 | build later | Glance 1.1.1 to 1.2 (`build.gradle.kts:313-314`) touches both existing widgets. | P; emulator round. |
| I127 | build | The automatic checks protect every later screen for little cost. | Dev-only accessibility checker in the Playwright tests; the screen-reader test is manual, once. |
| I128 | don't build | Package identity means signing and packaging a beginner must keep working release after release. | - |
| I129 | build | Small; also fixes the flat 300-token allowance (`_TEMPLATE_TOKENS = 300`, HEAD `backend/jarvis_agent.py:2016`, used `:3000`, `:3509`). | B test that measures the rules block against the allowance. I134 checks the installed model has it. |
| I130 | build later | Only if I133 shows a gain. | - |
| I131 | build | Small, fixed text, no model. | B; the "what can you reach" answer comes from `jarvis_reach` (one source). |
| I132 | build | Small. | B for the detector; P, D render a flag. |
| I133 | build | One tool, not the three scripts the reports propose. | CI part (no model) in B; PC part dated. Absorbs I60, I137, I153 checks. |
| I134 | build | Small preflight check; catches a stale model. | B. |
| I135 | build | A cheap CI test that stops style drift in fixed lines. | B (and a scan of both apps' string files). |
| I136 | build later | As a preset, once presets are served by the PC (phone hard-codes them, `Manner.kt:26`). | G. |
| I137 | build later | After I133. | - |
| I138 | build later | Dials x fixed sentences x two apps is a lot of strings; serve them from the PC first. | The 900-character cap test (per R4-GROW) in B. |
| I139 | build later | With I138. | - |
| I140 | build later | Reuses the learner's checks. | B. |
| I141 | build later | A counter and a back-off kind. | - |
| I142 | build later | A new fact label touches memory lists, Forget and Erase in both apps. | B, P, D. |
| I143 | build later | After I138-I142. | Refusal test in B. |
| I144 | build | Small. | B. |
| I145 | build | Look first (S): two style systems would conflict. `jarvis_persona.py` is not in this repo (`git ls-files`). | Reading only. |
| I146 | build later | Small. | - |
| I147 | build later | Changes the faces, which the phone CI photographs on every run (`jarvis-client.yml` "Photograph every face"). | P, D screenshots. |
| I148 | build later | Same. | - |
| I149 | don't build | No face with a mouth exists. | - |
| I150 | no objection | Guidance, nothing to keep. | - |
| I151 | build | Worth the care. Two things rot: the word list and the phone number. | Words: ONE shared list with `backend/jarvis_sensitive.py:192, 282` (not a copy). The number in one file with a "checked on" date and a preflight WARN when older than a year. B. |
| I152 | build | Small, but read the same list as I151, not a third copy (§0.12). | B (`test_router_private_terms.py` exists). |
| I153 | build later | Wording; measured by I133. | - |
| I154 | build | Small. | B; shares I151's list. |
| I155 | don't build | Outside test kits that default to a cloud judge, change often, and need the 14B model; I133 covers the need. | - |

Counts: **build 54, build later 79, don't build 14, no objection 8** (155).

---

## 2. Objections for the other reviewers

1. **To Fit and Security - I07 (MCP).** I say build (owner chose), but the
   draft is not "ready to wire in": its patch fails against HEAD (§0.10) and
   its tests are outside CI. I would make "move the draft into `backend/`,
   make CI run it, rewrite the wiring" the first step, and ship ONE server.
   If you think the owner should hear "MCP is L plus ongoing upkeep" before
   it starts, I agree.
2. **To everyone - pin before adding.** I rank I111's pinning half as
   "build now" (Fit said build later, Rules no objection). About a dozen new
   packages or outside programs arrive with this set (OCR, wake model, Pocket
   TTS weights, MarkItDown, IMAPClient, DuckDB, age, feedparser, py-fsrs, a
   WebSocket client, ffmpeg, NAPS2/Everything, the MCP SDK and servers).
   Today nothing is pinned and nothing is scanned (§0.3). Security may want
   the advisory scan first; Devil's advocate may say pinning adds a chore -
   it does (a monthly pin update), and I think it is worth it.
3. **To Fit and Security - I66, I19, I67, I69, I70, I73, I82.** Each adds a
   "tell me when" source. I want a refactor of `jarvis_tellme.py` into a
   source list before the third source lands (§0.11). Fit rated I66 "build"
   with no precondition.
4. **To Hardware - I24 and I29.** You said "build later [2nd card]"; I say
   don't build: the upkeep (PyTorch stacks, model files, card juggling) is
   out of proportion to "nicer voice" and "draw pictures". If the owner
   wants either, one only, replacing something.
5. **To Security - I106 and I108.** You said build later; I say don't
   build. Four overlapping defences (I104-I108) are four things to keep in
   step with the tool loop. Let I95 pick at most two.
6. **To Fit - I90 (sleep the PC).** We agree on "don't build", but for
   different reasons; mine is that a missed alarm from a sleep/wake bug
   cannot be tested anywhere and I93 already covers the need.
7. **To Rules and Security - I48 (browser history).** You said build later;
   I say don't build - the exclusion list and the per-browser formats are
   upkeep forever for a modest gain.
8. **To Overwhelm - lists served by the PC.** I116 (things you can say),
   I136/I138 (presets), I28 (speed) and I73 (chosen apps) all put lists on
   the phone. If the phone draws them from the PC, adding an entry costs no
   phone release. Hard-coding them (as `Manner.kt:26` does today) means a
   CI round each time.
9. **To Devil's advocate - the "measure first" gates.** About 20 ideas are
   "only if measurements show a gain". That promise is empty unless someone
   runs the measurements. I ask for one "run every measurement" command and
   a preflight line with each result's age. If you think that is itself
   overhead nobody will use, say so - then those ideas should be "don't
   build" rather than "build later".
10. **To Fit - owner-only modules.** I61, I65, I70, I104, I109 need
    changes in files only the owner's PC has, tested only there (§0.1-0.2).
    I would prefer new whole modules over new patches wherever possible;
    each new patch against `jarvis_hud.py`/`jarvis_gate.py` is the most
    expensive kind of change this project has.
11. **To Hardware - I31.** You want to change one default. Note that the
    re-ranker model is fixed in code but fastembed is unpinned; a default
    change should come with a pinned fastembed so the measurement stays
    true.

---

## 3. Wrong or out of date in the research and the master list

1. **Memory ideas 1-4 are merged.** The master list (note 1; I31-I34)
   says "not merged". `git merge-base --is-ancestor` shows `9abdd68`,
   `c33b5f0`, `d2d8831`, `eee9b03` and `a1b133e` are all in HEAD (Fit found
   the same). `e372eb7` (notifications) is still NOT in HEAD - that part is
   right.
2. **The MCP draft is not a working draft any more.** ENG and the master
   list (note 4, I07) treat `docs/designs/mcp-draft-2026-09-23/` as the
   starting point. Its `jarvis-agent-mcp.patch` fails `git apply --check`
   against HEAD's `backend/jarvis_agent.py` (tried on a scratch copy; "patch
   failed: jarvis_agent.py:743"); the code it edits is now at
   `backend/jarvis_agent.py:3861`, restructured. Its tests are not in CI.
3. **"Jarvis is tested on sherpa-onnx 1.13.8" (VV §3) is not guaranteed by
   anything.** `backend/requirements.txt:18` has no version and CI installs
   the newest each run (`.github/workflows/ci.yml:141`). What the owner's PC
   has is whatever was newest when they last installed. Pocket TTS's
   1.12.24 floor must be written into `requirements.txt`.
4. **ARCHITECTURE §9 says "Fifty-three patches"** (`docs/ARCHITECTURE.md:1178-1179`,
   counted 2026-09-24). The list now has 67 unique patch names
   (`scripts/apply-patches.ps1:87`). Not a research report, but a doc the
   builders read first.
5. **Line numbers moving under us.** The master list's I129 cites
   `jarvis_agent.py:2016, :3000, :3509`. Those are right in HEAD, but the
   working tree (being edited by another agent now) has them at `:2044`,
   `:3033`, `:3549`. Reviewers should cite HEAD.
6. **I151's citations are off by two:** the self-harm words are at
   `backend/jarvis_sensitive.py:192` and `:282`, not `:190` and `:280`
   (HEAD). The claim itself (no crisis handling on the answer path; no
   "helpline"/"samaritan" in `backend/*.py`) I re-checked by grep and it
   holds.
7. **R2-EXP #1, the lock-screen widget.** The report says the approval
   widget "may be allowed on the lock screen" on Android 16. The widget
   already declares `android:widgetCategory="home_screen"` only
   (`widget_approval_info.xml:18`, `widget_quicklink_info.xml:16`). Whether
   Android 16 still shows it on the lock screen is the report's "summary"
   claim, which I did not verify. Worth a check on a real Android 16 phone
   before adding the attribute, rather than assuming.
8. **Fit's cross-check stands on the ledger and watch modules:** R2-TRU #8
   and CAP #9 propose new ones without mentioning the owner's existing
   `jarvis_ledger` / `jarvis_watch`. Neither file is in this repo
   (`git ls-files`), so I could not check them either - someone must read
   them on the owner's PC first.
9. **Checked and right** (so nobody re-checks): the desktop reads only the
   first graphics card (`commands.rs:2617`); the briefing's weather line
   (`jarvis_briefing.py:117-118, 338`); the owner installs Python 3.12
   (`docs/INSTALL.md:53`), so `imaplib`'s IDLE (3.14) is not available;
   R2-TRU's `-Revert` citation (`apply-patches.ps1:1019`).

---

## 4. Upkeep guardrails for the whole set

1. **Pin, then add.** Hash-pinned Python requirements and a Python
   advisory scan in CI before the first new package; a monthly pin update.
2. **Every new package gets a preflight line.** The backend starts without
   any package and says nothing (`requirements.txt:8-11`); a feature whose
   package is missing must say "off: X is not installed".
3. **Every two-app feature gets a golden-case file** (`tools/gen_*_cases.py`),
   so the phone's CI round confirms rather than discovers.
4. **Lists the phone shows come from the PC** (presets, commands, apps),
   so adding an entry needs no phone release.
5. **One source for each word list** (sensitive, private, crisis, one-time
   codes); never a hand-synced copy (`jarvis_router.py:127-131`).
6. **Designs live where CI runs them**, or are marked "stale" with a date.
7. **Prefer a new whole module over a new patch** on an owner-only file.
8. **Every "measure first" result is dated**, one command runs them all,
   and the preflight shows their age.
9. **Refactor before the third copy**: "tell me when" sources before I66.
