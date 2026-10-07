# Publishing the base backend — a file-by-file inventory

**Read-only analysis. Nothing was published, no repository was created, the
live backend folder was not modified.** Measured 2026-10-06 off
`origin/main` (`2647f80c`) in the worktree `C:\Users\pcadmin\Documents\jarvis-publish`,
branch `next-publish-inventory`.

The folder examined is the owner's live install:

    C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program

Counted with `Get-ChildItem -LiteralPath <folder> -Recurse -File -Force` and
`Measure-Object -Length -Sum`. **487 files, 32,254,703 bytes = 30.76 MB.**
That matches the brief's "~30.8 MB in 487 files", so this is the right folder.

---

## 1. The single biggest obstacle

**You can copy the files out today. What you cannot do today is *check* them.**

Nothing in the repository can prove that the 179 files you would publish are
the same base that the 122 patches and the test suites describe. Two measured
facts show this:

1. **The 122-patch stack does not come off the live backend.** Reversing them
   newest-first on a copy stops dead at `approval-notice.patch` (21st in
   `$PATCHES`, the 101st tried). Command and result:

   ```
   # on a throwaway copy in %TEMP%, never the real folder
   git apply --reverse <patch>        # for each of $PATCHES, reversed
   → REVERSE STACK stopped after 100 patches, at: approval-notice.patch
   ```

   The cause is concrete and is exactly the class of bug this repository keeps
   producing: **`backend/rebuilt/jarvis_events.py` already contains the code
   `approval-notice.patch` adds**, at its lines 453/457, and the owner's live
   `jarvis_events.py` is byte-identical to it
   (`3F0DA6DA…9205B8`, both files). The patch's own hunk no longer matches
   anything, so it can neither go on nor come off.

   So the live tree is *not* "the shipped modules plus the 122 patches". Six
   patches (`memory-safety`, `extraction-wiring`, `bitemporal`,
   `embedding-guard`, `event-allowlist`, `approval-notice`) edit the two
   modules the repository also ships whole — two authorities for the same file
   that have already drifted apart.

2. **`backend/.gitignore` ignores the backend sources on purpose.** It names
   eleven files that must never be committed, because `backend/` is a *patch*
   directory, not the backend:

   ```
   jarvis_hud.py    jarvis_memory.py   jarvis_extract.py   jarvis_events.py
   jarvis_gate.py   jarvis_skills.py   jarvis_recall.py    jarvis_models.py
   jarvis_persona.py  jarvis_structured.py  jarvis_speech.py   *.py.bak
   ```

   (`!rebuilt/` re-includes the ten rebuilt copies and nothing else.
   `jarvis_persona.py` does not exist anywhere — a stale entry.)

Because of (2), the files that decide whether anyone else can ever install
this have *never been copied into the repository at all* — not hidden, not
ignored-then-forgotten, simply never placed there. And because of (1), when
they are placed there, nothing will tell you whether the copy is right.

**This is fixable, and it is not a reason to say no.** It is a reason to do
the copy as a deliberate, checked step rather than a `copy-item` — see the
recommendation in §6.

### The premise in the brief does not reproduce

The brief says a previous check found **68 top-level `jarvis_*.py` modules
neither in `backend/rebuilt/` nor named by any patch**. Measured today, that
number is **15**, not 68:

| What | Count |
|---|---|
| Top-level `.py` in the live backend | **189** |
| …byte-identical to a copy already in the repository | **160** |
| …differing from the repository's copy | **1** (`test_speech.py`; the repo's is *newer* — 15,666 B vs the owner's 10,232 B) |
| …with **no copy in the repository at all** | **28** |

Of those 28, after removing tests and dev scripts: **15 real modules**, and
**161 of the 189 top-level modules are already public in this repository.**

So publishing the base is much smaller than it sounds — and, more
importantly, **it is mostly a de-duplication problem, not a missing-code
problem.** The brief's 68 figure should not be used to size the work.

---

## 2. The exact file list to publish

### How I decided

Not a heuristic. Every top-level `.py` was placed by three tests, in order:

1. **Is it imported by the running program?** I rebuilt `check-backend.ps1`'s
   own import walk over the live folder: regex for `from X import` /
   `import X` on every file, keep only `jarvis_*` (and `_jarvis*`,
   `import_history`, `patch_openjarvis`, `spike_`). Result:
   **162 modules needed, 0 missing.**
2. **Does the repository already have an identical copy?** SHA-256 of the
   file with CRLF normalised to LF (the same test `backend/_where.py`
   `_same_text()` uses), against `backend/<name>` then `backend/rebuilt/<name>`.
3. **Is it a file the code expects *beside itself*?** Every `HERE / "..."`,
   `_HERE / "..."` and `Path(__file__).parent / "..."` reference was
   collected and each named file checked for existence.

I then **staged the result in `%TEMP%` and ran the repository's own
`scripts/check-backend.ps1` against it**, which is the strongest available
check:

```
STAGED: 180 files, 10.49 MB
Backend : C:\Users\pcadmin\AppData\Local\Temp\jarvis-publish-stage
Modules : 158 needed, 158 present, 0 to be copied in by apply-patches.ps1, 0 missing
→ "Nothing is missing that only your PC can have."
```

The staged import graph closes completely. (158 vs the 162 above: the four
extra are only needed by the test files, which were not staged.)

### NEEDED — the base source (179 files, 10.40 MB)

**Rule, exact and reproducible:**

```
every top-level *.py in the live backend folder, EXCEPT
  - test_*.py          (12 files)
  - patch_openjarvis.py
  - spike_sandbox.py
plus exactly these five non-Python files:
  jarvis-visual-spec.json    61,301 B   /api/visual-spec reads it
  rust-crates.lock          173,930 B   jarvis_tool_updates.py reads it
  requirements.lock         167,781 B   jarvis_tool_updates.py, jarvis_backup.py, jarvis_pc_help.py read it
  quiz_grader_cases.json      9,573 B   eval_quiz_grader.py reads it
  jarvis-framework.toml                 ← from backend/rebuilt/jarvis-framework.toml, NOT the owner's
```

**And two files that are NOT in the backend folder and must come from the
repository** (see §4):

```
jarvis-desktop/src/jarvis_hud.html      the page jarvis_hud.py serves at "/"
```

**The 15 modules that a naive copy from this repository would still miss.**
These have no copy in the repository at all, so they cannot be recovered by
`apply-patches.ps1` or by any `git checkout`:

```
the five core files the patcher edits (605 KB, ~25,000 lines):
  jarvis_hud.py        339,860 B   the entry point — nothing runs without it
  jarvis_gate.py       119,944 B   every approval
  jarvis_extract.py     38,579 B
  jarvis_models.py      57,285 B
  jarvis_skills.py      40,118 B

the ten modules that exist nowhere else (360 KB):
  jarvis_preview.py     78,467 B   imports jarvis_content_risk; /api/holds/cancel
  jarvis_ledger.py      50,820 B   /api/ledger, /api/undo
  jarvis_jobs.py        47,118 B   /api/jobs/cancel; imported by jarvis_arbiter
  jarvis_undo.py        46,640 B   /api/undo/revert, /api/undo
  jarvis_content_risk.py 26,873 B  imports jarvis_arbiter; read by jarvis_gate, jarvis_skills
  jarvis_watch.py       24,391 B   imports jarvis_arbiter, jarvis_jobs
  jarvis_arbiter.py     23,621 B   imports jarvis_jobs
  jarvis_tripwire.py    12,702 B   imported by jarvis_models
  jarvis_structured.py   9,656 B   imported by jarvis_extract   ← the one name in backend/.gitignore
  jarvis_style.py        8,668 B   imported only by test_tripwire.py
```

### Could go either way — say so plainly

* **The 12 top-level `test_*.py` (0.24 MB).** I would include them.
  Eleven of the twelve have **no copy in the repository**, and they are the
  *only* tests for the ten modules above — `test_arbiter.py`,
  `test_content_risk.py`, `test_jobs.py`, `test_ledger.py`,
  `test_preview.py`, `test_structured.py`, `test_tripwire.py`,
  `test_undo.py`, `test_watch.py`, `test_voice_http.py`, `test_patcher.py`.
  Publish the modules without their tests and those ten modules ship
  unverified forever. The twelfth, `test_speech.py`, should be **excluded** —
  the repository's copy is newer and larger.
  With them: **191 files, 10.64 MB.**

* **`eval_quiz_grader.py` (3,956 B).** Kept as NEEDED because it is in the
  repository's `SHIPPED` list and `apply-patches.ps1` step 3b copies
  `quiz_grader_cases.json` beside it. It is a development script, not a
  request path.

* **`faces_helpers.js`, `faces_bodies.js`, `shell.html`,
  `jarvis-reactor-kit.html` (0.52 MB).** I would exclude. No Python module
  anywhere reads them (measured: zero hits across all 189 modules). They are
  the superseded "Jarvis Reactor Kit" front-end, and the repository already
  carries its own copy of `jarvis-reactor-kit.html` at
  `docs/reference/jarvis-reactor-kit.html` — a *different* 247,780 B version
  from the backend's 305,236 B one. Three different revisions of one page
  exist. They could be published as historical reference, but they are not
  part of the base.

* **The six `.md` files (0.16 MB)** — `JARVIS-API.md` (superseded by
  `docs/JARVIS-API.md`, 1,260,278 B), `JARVIS-EXPLAINED.md`,
  `JARVIS-FRAMEWORK.md`, `DESKTOP-BUILD.md`, `DESKTOP-UPDATE-PROMPT.md`,
  `ANDROID-VOICE-PROMPT.md`. Exclude from the *base*; two of them
  (`DESKTOP-BUILD.md`, `DESKTOP-UPDATE-PROMPT.md`) contain the owner's
  absolute path twice each and may be worth keeping as `docs/` history.

---

## 3. PRIVATE — NEVER PUBLISH

**Counts: 111 files, 9.18 MB** (2 loose files, 109 inside 14 folders).

| Item | Files | Size | Why it is private |
|---|---|---|---|
| `jarvis-framework.toml` | 1 | 50,856 B | The owner's **live** settings. Not a secret today — see the scan below — but it is live state, and publishing it would be actively harmful: **it is missing 23 settings the repository's 88,386 B template has** (`[tools] enabled`, `read_web_page` and `chat_card_pin` approval tiers, all seven `[second_card]` keys, five `[big_model]` keys). A new user given this file as their template gets a settings file the current code reads as "missing, so off". `_config_diff.py` exists *precisely* so this file is never overwritten. It also holds 5 settings the template lacks, including `[voice] stt_engine = "faster-whisper"`. |
| `jarvis-framework.toml.backup-2026-10-03-210230` | 1 | 48,022 B | An older copy of the same live settings file. |
| `_jarvis-logs/` | 21 | 0.97 MB | 21 `apply-patches-*.txt` transcripts. One holds the owner's absolute path **231 times**, and together they are a full inventory of his machine's file names and patch history. No credential — but his machine's business, and `*.log` in the root `.gitignore` does **not** match `.txt`. |
| `_jarvis-backup-*/` (13 folders) | 88 | 8.11 MB | The patcher's own before-images. Eight of the thirteen hold the five core modules; four hold 12–18 modules including `jarvis_agent.py`, `jarvis_second_card.py`, `jarvis_secrets.py`, `jarvis_voices.py`. These are **superseded revisions of security-relevant files**: a reader can diff them against the published version and find exactly which bounds, gates and secrets-handling were fixed, and when. `_jarvis-backup-2026-10-06-110138` alone holds 18 files. |
| **Total** | **111** | **9.18 MB** | |

The root `.gitignore` already has `_jarvis-backup-*`. **It does not have
`jarvis-framework.toml`, `_jarvis-logs`, or `*.before-loopback`** — measured
with a search of every `.gitignore` in the repository. A careless `git add .`
after dropping the base into this repository would therefore sweep in:

```
jarvis-framework.toml                     ← the live settings file
jarvis-framework.toml.backup-2026-10-03-210230
_jarvis-logs/                             ← 21 files, 0.97 MB, 231 owner paths
jarvis_hud.py.before-loopback             ← see §4, GENERATED
```

`__pycache__/` and `*.py[cod]` **are** covered (root and `backend/`), and
`*.py.bak` is covered by `backend/.gitignore` — but only while the file sits
in `backend/`. If the base becomes its own folder, that rule stops applying
and `jarvis_hud.py.bak` would come in too.

### What I checked for, and what I found

Scanned **all 487 files** (skinny: every file under 8 MB except the 171
`.pyc`; 316 files actually read) with these patterns:

| Looked for | Result in the backend folder |
|---|---|
| OpenAI / Anthropic / GitHub / Google / AWS / Slack keys, Bearer tokens, `BEGIN … PRIVATE KEY`, password literals | **None real.** The only hits are test literals: `sk-live-4f9a2b7c1d8e6f0a3b5c7d9e` (`test_undo.py:308`), `AKIAIOSFODNN7EXAMPLE` / `AKIAJ4NEWNEWNEW7EXAMPLE` (`test_undo.py`, `test_preview.py`), `-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n` (`test_undo.py:335`, `test_preview.py:647`), and `AIzaSy…` strings that are regex *patterns* inside `jarvis_secret_rules.py:101` plus base64 blobs in `jarvis_voicebank.py` / `jarvis_wakebank.py` / `faces_helpers.js`. All four `AIza`-looking and four `exa/tavily`-looking samples I traced are base64 model data or test fixtures. |
| Email addresses | **24 unique, all documentation or test values** — `a@b.test`, `a@example.test`, `bob@example.test`, `carol@example.test`, `dentist@example.test`, `billing@evil.example`, `accounts@northgate.example`, `alice@example.test`, `mario@example.com`, `client@example.com`, `noreply@github.com`, … **No personal address anywhere.** |
| Tailscale `100.x` CGNAT addresses | **None real.** One hit, `100.64.0.0` — the documentation CIDR, in 5 files. |
| `.ts.net` mesh hostnames | **None.** |
| Machine name / user name | `pcadmin` in 23 files, 29 occurrences — **and already published in this repository**: `README.md:91`, `backend/README.md` (dozens), `scripts/check-backend.ps1:34`, `scripts/apply-patches.ps1:91`, and the shipped modules `backend/jarvis_kokoro.py:576`, `backend/jarvis_mouth.py:267`, `backend/jarvis_live_photo_test.py:13`. Nothing new would be leaked. |
| Chat records, approval records, voice prints, face images | **Not in this folder at all.** It contains **no `.db`, `.sqlite`, `.wav`, `.npy`, `.png`, `.jpg`** — checked by extension across all 487 files. They live in `C:\Users\pcadmin\.openjarvis` (45 entries), which is outside the backend folder and outside the repository: `chat-history.db`, `memory.db`, `approvals.db`, `arbiter.db`, `feedback.db`, `goals.db`, `jobs.db`, `knowledge.db`, `ledger.db`, `schedule.db`, `sync_state.db`, `telemetry.db`, `traces.db`, `speed.jsonl`, `tripwire.json`, `cloud-keys.env`, `litellm-proxy.yaml`, `anon_id`, `USER.md`, `SOUL.md`, `MEMORY.md`, plus `models/` (64.07 MB), `logs/` (7 files), `voice/`, `skills/`, `apps/`. **`~/.openjarvis` is the folder that must never be published; the backend folder is not.** |

**Bottom line for a "safe to publish" verdict: I found no credential, key,
token, private key, real email address, mesh address, chat record, approval
record, voice print or face image anywhere in the backend folder.** I am not
saying "safe to publish" — §1 says why the *copy* cannot be checked yet, and
§5 lists what a stranger would still be missing. But the privacy objection to
this particular folder is empty apart from the four items in the table above.

---

## 4. GENERATED / EXCLUDE

**Counts: 185 files, 10.94 MB.**

| Item | Files | Size | Why |
|---|---|---|---|
| `__pycache__/` | 171 | 9.92 MB | Bytecode. Already ignored by both root and `backend/.gitignore`. It also embeds absolute paths. |
| `jarvis_hud.py.bak` | 1 | 155,291 B | A stale second copy of the entry point. |
| `jarvis_hud.py.before-loopback` | 1 | 156,527 B | A stale third copy — and the **name records a security change** (the loopback bind). Publishing an older revision of a security-relevant file is a hazard even though its text is not secret. Not covered by any `.gitignore` pattern. |
| `patch_openjarvis.py` | 1 | 20,136 B | A standalone tool that patches a *different* project (OpenJarvis). No Python module imports it; `jarvis_gate.py:922` and `jarvis_skills.py:330` only name it in a string list. Absent from the repository and from `$SHIPPED`. |
| `spike_sandbox.py` | 1 | 17,612 B | An experiment. Referenced only by itself. |
| Reactor Kit front-end | 4 | 549,217 B | `shell.html` (102,140), `jarvis-reactor-kit.html` (305,236), `faces_bodies.js` (89,850), `faces_helpers.js` (51,991). Zero reads from any `.py`. Superseded; the repository keeps its own copy at `docs/reference/`. |
| Legacy `.md` | 6 | 167,067 B | Superseded by `docs/`; two contain the owner's path. |
| **Total** | **185** | **10.94 MB** | |

**Accounting closes:** 179 (NEEDED) + 111 (PRIVATE) + 185 (EXCLUDE) + 12
(tests, either-way) = **487 files**. Sizes: 10.40 + 9.18 + 10.94 + 0.24 =
**30.76 MB**.

---

## 5. Does the base reference something that would NOT be published?

**One hard blocker, one stale entry, and a large optional set.**

### The hard blocker: `jarvis_hud.html` is missing everywhere

```
jarvis_hud.py:2226    page = HERE / "jarvis_hud.html"
jarvis_hud.py:2228    "jarvis_hud.html is missing from this folder."   (HTTP 500)
```

The file is **not in the backend folder and never has been** — I searched the
whole of `Documents\Claude\Open jarvis files` and found none. It exists in the
repository at `jarvis-desktop/src/jarvis_hud.html` and the Tauri app loads its
own bundled copy, so **the desktop app works and the raw backend URL does
not**: `http://localhost:4719/` returns HTTP 500. A stranger who clones the
base and opens that URL sees an error, which is the first thing anyone tries.

**Fix: the publish step must place `jarvis-desktop/src/jarvis_hud.html` beside
`jarvis_hud.py`**, or `jarvis_hud.py` must be taught to look there (its
`_visual_spec()` already searches `HERE`, `HERE/src`, `HERE/jarvis-desktop/src`
and `here_up/jarvis-desktop/src` — the same search list would fix this).

### The ten orphan modules: they start, then fail on a real request

`check-backend.ps1`'s own docstring describes this exact failure. These
imports are **lazy — inside route handlers, not at module top** — so a base
without them starts cleanly and looks healthy:

```
jarvis_hud.py:774    import jarvis_undo      → /api/undo/revert   (unguarded: 500)
jarvis_hud.py:782    import jarvis_jobs      → /api/jobs/cancel   (unguarded: 500)
jarvis_hud.py:793    import jarvis_preview   → /api/holds/cancel  (unguarded: 500)
jarvis_hud.py:2331   import jarvis_undo      → /api/undo          (inside try/except → "available": false)
jarvis_hud.py:2339   import jarvis_ledger    → /api/ledger        (inside try/except → "available": false)
jarvis_hud.py:824    jarvis_watch, :851 jarvis_arbiter — imported from handlers
jarvis_extract.py    imports jarvis_structured
jarvis_models.py     imports jarvis_tripwire
jarvis_gate.py:     imports jarvis_content_risk
```

`jarvis_style.py` (8,668 B) is imported **only** by `test_tripwire.py` — so it
is needed only if the tests ship.

### The stale entry

`backend/.gitignore` names `jarvis_persona.py`. **It does not exist** on the
owner's PC or in the repository. A rule protecting nothing is a rule that will
mislead the next person.

### Not a blocker, but a stranger is still short of these

* **Model and voice assets (about 64 MB, in `~/.openjarvis/models`, not in the
  folder).** 30+ named files the code reads and no one has:
  `model.onnx`, `voices.bin`, `voices-jarvis.bin`, `tokens.txt`, `vocab.json`,
  `encoder.int8.onnx`, `decoder.int8.onnx`, `joiner.int8.onnx`,
  `model.int8.onnx`, `lm_flow.int8.onnx`, `lm_main.int8.onnx`,
  `text_conditioner.onnx`, `pytorch_model.bin`, `encoder.onnx`,
  `melspectrogram.onnx`, `embedding_model.onnx`, `hey_jarvis_v0.1.onnx`,
  `hey_jarvis_livekit.onnx`, `hey_jarvis.tflite`, `silero_vad.onnx`,
  `silero_vad_v6.onnx`, `smart-turn-v3.2-cpu.onnx`, `resnet221.onnx`,
  `strong.onnx`, `model.durations.onnx`, `lexicon.txt`, `self-test.wav`,
  `clip.wav`. `backend/README.md` ("Voice that works", "Better voice") is the
  document that says how to get them. Without them the voice features are off
  and say so.
* **Model weights for the local AI.** Ollama's own store, not this folder —
  `docs/INSTALL.md` covers `ollama pull`.
* **A hardcoded owner path in three already-published modules.**
  `backend/jarvis_kokoro.py:576` and `backend/jarvis_mouth.py:267` hold
  PowerShell one-liners containing the owner's exact folder, and
  `backend/jarvis_live_photo_test.py:13` a `cd` line. On a stranger's PC the
  printed setup command points at a folder they do not have. **This is already
  public** — it is not a new leak, but it is a broken instruction, and fixing
  it is part of making the base installable.
* **The data folder.** Every module builds `~/.openjarvis` on demand
  (`jarvis_framework.py:77` is the canonical one; `jarvis_hud.py:81` honours
  `OPENJARVIS_CONFIG_DIR`). Created if absent. Fine.

**Nothing else points outside the folder.** The internal import graph is
complete — 162 modules needed, 0 missing — verified twice, including by the
repository's own `check-backend.ps1` against a staged copy.

---

## 6. Size and shape of the result

| | Files | Size |
|---|---|---|
| **Publish without the tests** | **179** | **10.40 MB** |
| **Publish with the 12 tests** | **191** | **10.64 MB** |
| (for comparison) the whole folder | 487 | 30.76 MB |

**Largest files in the publish set** — nothing is close to a problem:

```
jarvis_wakebank.py       930,233 B   0.887 MB
jarvis_sky_places.py     569,486 B   0.543 MB
jarvis_agent.py          399,487 B   0.381 MB
jarvis_hud.py            339,860 B   0.324 MB
jarvis_voicebank.py      322,830 B   0.308 MB
jarvis_stopword.py       289,056 B   0.276 MB
jarvis_second_card.py    263,490 B   0.251 MB
jarvis_memory.py         259,615 B   0.248 MB
```

**GitHub's 100 MB per-file limit: not approached.** The largest single file in
the whole 487 is 0.887 MB; **zero files exceed 50 MB**. The 1 GB repository
guidance is not approached either at 10.6 MB.

**`requirements.txt` and PyPI.** `backend/requirements.txt` names 24
distributions. I verified these four by fetching PyPI directly, because they
were the ones that looked unusual:

| Package | On PyPI |
|---|---|
| `sherpa-onnx-core` | **Yes** — 0.0.1 … **1.13.8**, "Core shared libraries for sherpa-onnx", publisher `csukuangfj`, Apache-2.0, Windows wheels present |
| `winrt-Windows.Media.Control` | **Yes** — **3.2.1**, pywinrt, MIT, Windows-only |
| `espeakng-loader` | **Yes** — **0.2.4**, Windows wheels present |
| `sqlite-vec` | **Yes** — **0.1.9**, MIT/Apache-2.0 |

The remaining 20 are all ordinary, and the repository's own
`backend/requirements.lock` (167,781 B) **hash-pins 78 packages** and is
written by a tool from real PyPI releases, so every one of them exists. The
repository's `backend/test_shipped_modules.py` fails if a shipped module
imports a package that is in neither `requirements.txt` nor its "not
installed" list.

**The four optional packages named in the "NOT installed" comment** —
`playwright`, `speechbrain`, `torch`, `soundfile` — all exist on PyPI, and
`pymicro-wakeword` is real and pinned by hash in `backend/README.md:16489`
(`pymicro-wakeword==2.5.0`, sha256 `e518dd22…f20ff5`, with
`pymicro-features==2.0.2`).

**Not established:** I did not fetch all 24 names individually from PyPI; 4
were fetched and 20 were taken from the repository's hash-locked list. If you
want each of the 24 confirmed one by one, say so and I will do it.

---

## 7. Recommendation: snapshot — but as a *checked* copy, not a new source of truth

**Recommended: publish the base as plain source in git, updated by ordinary
commits. Do not keep the patch model as the way a new user installs.**

Reasons, in order of weight:

1. **A new user cannot use the patch model at all, and never could.** The
   patcher's whole job is to modify a backend that arrives from somewhere
   else — `docs/INSTALL.md:221` says so outright. If the base is published,
   that "somewhere else" *is* the repository, so the patches have nothing left
   to do. Keeping both means maintaining two descriptions of the same file.
2. **They have already drifted.** §1 item 1: `backend/rebuilt/jarvis_events.py`
   contains what `approval-notice.patch` adds; six patches edit modules the
   repository also ships whole. The patch model is *already* not the single
   source of truth, and the repository has no check that would notice.
3. **161 of the 189 modules are already in the repository**, byte-identical.
   The patch model is carrying a description of files that are, for the most
   part, already here.

### What the 122 patches and `backend/rebuilt/` would become

* **The 122 patches become history.** For a fresh install they are no-ops: the
  published base is the *post-patch* state, so a new user never runs them.
  They keep their only remaining value — describing what changed, and letting
  the owner rebuild or revert **his own** backend — so I would keep them, move
  them under `backend/patches/`, and mark them clearly as "for the owner's
  existing install only". I would not delete them: `docs/` and
  `backend/README.md` reference them by name in hundreds of places.
* **`backend/rebuilt/` becomes a duplicate** of ten modules the base also
  holds. `backend/_where.py`'s `require_shipped()` and
  `backend/test_shipped_modules.py` exist to keep the repository's copies equal
  to the owner's. Once the base is in the repository, those two must be
  re-pointed at the base — see below.

### What breaks in `scripts/apply-patches.ps1` if the base is already present

Nothing breaks *structurally* — and that is the trap, because it will **appear
to work**:

1. **Step 2 takes the wrong branch.** `apply-patches.ps1` asks "is it already
   patched?" by reversing the whole 122-patch stack (`Test-StackReverses`,
   line 2267). On the owner's tree that **fails** (§1), so it does *not* take
   the clean `"All 122 patches are already applied. Nothing to do."` path
   (line 2289). It falls through to path (b): forward-rehearse all 122 on a
   copy, where many report `not onto the files as they are` — expected, since
   they are already on — and then to path (c), which **peels the applied ones
   off newest-first and puts the whole list back on**. That is the one code
   path in this script that can leave a half-applied backend. **I could not
   establish read-only whether it succeeds**, because proving it requires
   running it, and running it writes.
   → *This is the concrete work item: fix the `approval-notice.patch` /
   `rebuilt/jarvis_events.py` drift so the stack reverses, or make the
   "already applied" test content-based rather than hunk-based.*

2. **Step 3 re-copies every shipped module on every run** (line 2533: "Checked
   here, by content, every run — including the 'already applied' one"). With
   the base present, all 161 comparisons come out equal and it skips them —
   correct behaviour, no change needed. But it means the repository's
   `backend/*.py` copies must stay byte-identical to the base, forever, or
   step 3 will silently overwrite the published base with the repository's
   copy on the owner's machine.

3. **The missing-file check (line 2140)** lists files the patches expect that
   are absent. With the base present, this list becomes empty. Dead code, not
   breakage — but `check-backend.ps1`'s `MISSING` branch ("not there, and this
   repository does not have them either", line 157) and `docs/INSTALL.md` §1.3
   and §1.4 become wrong and must be rewritten.

4. **`backend/_where.py`'s `require_shipped()`** compares the backend's copy
   of each shipped module against `backend/<name>` and **exits 1** on any
   difference. It only does this when `JARVIS_BACKEND` is set. Once the base is
   in the repository, this must be re-pointed at the base, or the suites will
   be checking the repository against itself and reporting success while the
   base drifts.

### The one precondition I would ask for

Publishing the base is worth doing. But **do the first copy as a checked
step, not a `Copy-Item`**, and add the missing check:

> A new test — call it `test_base_matches_repo.py` — that asserts, for every
> module the repository ships whole, that the base's copy is byte-identical to
> `backend/<name>`, and fails with the file names when it is not. That is the
> check that does not exist today, and its absence is the whole of §1.

Without it, the published base and the repository's `backend/` copies are two
copies of 161 modules that nothing keeps in step — and this repository's own
history (the `.gitignore` naming a file that does not exist; the brief's "68"
figure that measures 15) shows exactly how that ends.

### Where I would put it

Keep `backend/` as the patch-and-test directory and add the base as a new
top-level folder — e.g. `jarvis-backend/`. Moving the base *into* `backend/`
means fighting `backend/.gitignore`, which ignores eleven of the very files
being published. A separate folder also keeps `backend/requirements.txt`,
`backend/README.md` and the ~380 suites where they are, so no test import path
changes.

**If the owner would rather not carry two copies at all**, the alternative is
to make the new folder the single source and delete the 161 duplicate `.py`
files from `backend/`, pointing `_where.py`, `test_shipped_modules.py` and the
suites at it. That is the cleaner end state and roughly a day's refactor
across ~380 test files. I would do the separate folder first, get a stranger
installing successfully, and only then consider the refactor.

---

## 8. What is NOT established

Stated plainly, so nothing here is read as more than it is:

1. **Whether `apply-patches.ps1` would succeed against the owner's current
   backend.** Its "already applied" test fails (§1), so it takes the
   peel-off-and-replace path. Proving that path works requires running the
   script, which writes to the backend folder — outside this read-only brief.
2. **Whether the 15 unpublished modules are the *current* files or themselves
   carry hand edits.** I can see they are the live files; I have no earlier
   complete copy to diff them against. The five core files differ from every
   `_jarvis-backup-*` copy, but those backups are mid-stream, not a baseline.
3. **Whether all 24 `requirements.txt` names exist on PyPI.** Four checked
   directly; the other twenty are taken from the repository's own
   hash-locked `requirements.lock`, which was generated from real releases.
4. **Whether `jarvis_wakebank.py` (930 KB), `jarvis_voicebank.py` (323 KB) and
   `jarvis_sky_places.py` (569 KB) contain anything private.** They are large
   embedded model/data tables. My pattern scan covered them (base64 blobs, no
   credentials), but I did not read them line by line.
5. **Whether publishing these files is compatible with every embedded
   licence.** `requirements.txt` documents the licences of the *packages*
   (espeak-ng is GPL-3, several are MIT/Apache-2.0, `youtube-transcript-api`
   breaks YouTube's terms). I did not audit the licences of code *inside* the
   189 modules, or the provenance of the base64 voice and wake-word banks,
   against `THIRD-PARTY-NOTICES.txt`. **This is a real gap and it is not a
   small one** — the base embeds large opaque data blobs whose origin I did not
   establish.
6. **The repository's own numbers vs mine.** The brief's "68 top-level
   `jarvis_*.py` modules" and "121 patches" do not reproduce: I measure **15**
   such modules and **122** patch files (`$PATCHES` has 122 entries; the
   directory holds 122 `.patch` files). I have not tried to work out which
   earlier state produced 68 and 121.

---

## 9. Commands, so every number above can be re-run

```powershell
$b = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"

# 487 files, 30.75 MB
(Get-ChildItem -LiteralPath $b -Recurse -File -Force).Count
(Get-ChildItem -LiteralPath $b -Recurse -File -Force | Measure-Object Length -Sum).Sum / 1MB

# 189 top-level .py / 28 with no copy in the repository
(Get-ChildItem -LiteralPath $b -File -Filter *.py).Count
#   ... compare each against backend\<name> then backend\rebuilt\<name> by
#       SHA-256 with CRLF normalised to LF (the test _where.py's _same_text uses)

# 162 modules needed, 0 missing — the repository's own script
powershell -ExecutionPolicy Bypass -File .\scripts\check-backend.ps1 -BackendPath $b

# 122 patches, and the reverse-stack test that stops at approval-notice.patch
(Get-ChildItem .\backend -File -Filter *.patch).Count
#   ... copy the 189 .py to %TEMP%, then `git apply --reverse` each of
#       $PATCHES in reverse order and see where it stops

# the private data folder, outside the backend folder — names only
Get-ChildItem -LiteralPath (Join-Path $env:USERPROFILE '.openjarvis') -Force
```
