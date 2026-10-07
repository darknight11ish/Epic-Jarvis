# The base backend

**This folder is a copy of the Python program that is Jarvis on the owner's
PC, published as plain source.** It is here so that this repository can be
*cloned and run*, rather than only patched: `backend/` is the patch
directory, and a patch is only useful if you already have the thing it
patches.

    181 files copied from the owner's backend folder, 11,108,190 bytes (10.59 MB)
      175 top-level .py - 173 named jarvis_*.py, plus eval_quiz_grader.py and
        import_history.py, which are run as scripts rather than imported
      6 more files: jarvis_hud.html, jarvis-framework.toml, requirements.lock,
        quiz_grader_cases.json, jarvis-visual-spec.json, rust-crates.lock
    plus this README and this folder's .gitignore, which are not part of the copy

Most of it was already in this repository byte for byte: **160 of the 175
top-level modules** have an identical copy under `backend/` or
`backend/rebuilt/`. The other **15 exist nowhere else on Earth** - the five the
patcher edits (`jarvis_hud.py`, the entry point nothing runs without;
`jarvis_gate.py`, every approval; `jarvis_extract.py`, `jarvis_models.py`,
`jarvis_skills.py`) and the ten orphans (`jarvis_arbiter.py`,
`jarvis_content_risk.py`, `jarvis_jobs.py`, `jarvis_ledger.py`,
`jarvis_preview.py`, `jarvis_structured.py`, `jarvis_style.py`,
`jarvis_tripwire.py`, `jarvis_undo.py`, `jarvis_watch.py`) - until 2026-10-06,
when they were published here. The inventory's section 2 lists the same
fifteen, with what each one carries.

## Where it came from

Copied out of the owner's live backend folder (the path is `$BackendPath` in
`scripts/apply-patches.ps1`) on 2026-10-06, from the state measured file by
file in [docs/BACKEND-PUBLISH-INVENTORY-2026-10-06.md](../docs/BACKEND-PUBLISH-INVENTORY-2026-10-06.md).
**The live folder was only read. Nothing there was changed.**

Every file here has LF line endings, which is this repository's rule
(`.gitattributes`: `* text=auto eol=lf`). The owner's live copies have CRLF.
It is the same text either way - `backend/_where.py`'s `_same_text()` is the
comparison that decides this, and it ignores line endings.

### The exact rule, so it can be re-taken

```
every top-level *.py in the live backend folder, EXCEPT
    test_*.py             (12 files - see "What is not here")
    patch_openjarvis.py   (a tool for a different project)
    spike_sandbox.py      (an experiment)
plus these six files:
    jarvis_hud.html          from jarvis-desktop/src/          (see below)
    jarvis-framework.toml    from backend/rebuilt/  - the TEMPLATE, never the live file
    requirements.lock        from backend/
    quiz_grader_cases.json   from backend/
    rust-crates.lock         from jarvis-desktop/src-tauri/Cargo.lock
    jarvis-visual-spec.json  the owner's own copy, which is what /api/visual-spec reads
```

`jarvis_hud.html` is the one file that was missing **everywhere**.
`jarvis_hud.py:2226` serves `HERE / "jarvis_hud.html"` at
`http://localhost:<port>/` and answers HTTP 500 without it, and the file was
never in the backend folder - the desktop app loaded its own bundled copy.
The copy here is `jarvis-desktop/src/jarvis_hud.html`, so a fresh clone's
front page works.

## What is NOT here, and why

* **The owner's data.** Memory, chat history, approvals, the voice print,
  cloud keys and every model file live in `~/.openjarvis`, which is outside
  the backend folder and outside this repository. The backend folder contains
  no `.db`, `.wav`, `.npy`, `.png` or `.jpg` file at all.
* **The pairing token, and any other credential.** The token is in Windows
  Credential Manager (`jarvis_token_store.py`), and `token-file.patch` writes
  it to `~/.openjarvis/token` - not to the backend folder. A scan of all 487
  files in the live folder found no real key, token, private key, personal
  email address, tailnet address, chat record, approval record, voice print
  or face image; the only hits were test literals and the name `pcadmin`,
  which this repository already publishes.
* **The owner's live settings file.** The `jarvis-framework.toml` here is the
  template from `backend/rebuilt/`. His live one is smaller and is **missing
  23 settings the template has** - a new user given it would run with
  `[tools] enabled`, all seven `[second_card]` keys and five `[big_model]`
  keys absent, so features would be off and nothing would say why.
* **12 tests, the patcher's `_jarvis-backup-*` folders, `_jarvis-logs/`, the
  stale `.bak` and `.before-loopback` copies, the superseded Reactor Kit
  pages and the six legacy `.md` guides.** The backup folders are
  superseded revisions of security-relevant files; the log transcripts name
  the owner's absolute path 231 times; the Reactor Kit pages are read by no
  module. See the inventory's §3 and §4.

## How it is kept true

**[backend/test_base_matches_repo.py](../backend/test_base_matches_repo.py)**
- it compares this folder file by file against `backend/` and
  `backend/rebuilt/` (the copies `apply-patches.ps1` installs), checks that the
  base's own import graph closes with nothing missing, checks the non-Python
  files are beside the code, and fails if a database, a token, a
  `__pycache__`, a patcher backup folder or the owner's live settings file is
  ever dropped in here.

That test is the point of the exercise. Without it there are two copies of
160 modules and nothing keeping them in step - and `apply-patches.ps1`
step 3 copies the repository's copy over the published one's, on the owner's
machine, every run, silently.

## What this folder is NOT - read this before trusting it

* **It is not the owner's install, and it does not change it.** The patches in
  `backend/` remain the description of *his* backend, applied by
  `apply-patches.ps1` to *his* folder. This folder is a snapshot for everyone
  else.
* **It is not proven to be the state the patch stack describes.** Reversing
  the stack off this base stops at `approval-notice.patch`, because
  `backend/rebuilt/jarvis_events.py` already contains the code that patch
  adds (inventory §1). `test_base_matches_repo.py` proves only that this
  folder matches **this repository's** copies.
* **It is not a complete install.** The AI model (Ollama) and about 64 MB of
  model and voice assets under `~/.openjarvis/models` are not here.
  [docs/INSTALL.md](../docs/INSTALL.md) covers both, and
  `backend/README.md`'s "Voice that works" covers the voice files.

## Running it, and what the patcher does to it

**`apply-patches.ps1` changes nothing here, and that is the correct result.**
Measured on 2026-10-06 against a copy of this folder: exit 0, `jarvis_hud.py`'s
SHA-256 identical before and after (`5B98F24B…A88E1D1`), and its own report
said `Checked again on the real files: all 120 patches are on` and `All 160
modules this repository ships are there and up to date`. This folder is the
state *after* the patches, so a fresh copy never needs them applied. The script
is still worth running once: it installs the Python packages, puts the settings
file in place, and runs the test suites. (It made a `_jarvis-backup-*` folder
and an `_jarvis-logs/` transcript on that run even though it changed no code —
both are in this folder's `.gitignore`, which is why they are.)

## Known follow-ups, not done in this commit

1. **Three files hardcode the owner's working folder** - `jarvis_kokoro.py:576`
   (`MAKE_LINE`), `jarvis_mouth.py:267` (`PREPARE_LINE`) and
   `jarvis_live_photo_test.py:13` (a docstring) all name
   `C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program`. It is
   not a credential and not a secret filename, but it is new structural
   exposure, it is broken for a stranger, and it contradicts `jarvis_scrub.py`,
   which exists in the same folder to redact exactly that string. **The fix has
   to land in `backend/jarvis_kokoro.py` and `backend/jarvis_mouth.py` first**
   and then be copied here, or `test_base_matches_repo.py` will fail on the two
   it compares.
2. **`backend/_where.py`'s `require_shipped()` and the rest of
   `backend/test_shipped_modules.py` still treat `backend/` as the only
   authority.** Now that a base exists, they should compare against it too, or
   they check this repository against itself while the base drifts.
3. **`scripts/check-backend.ps1`'s MISSING branch** still says "this repository
   does not have them either" - true of `backend/`, no longer true of the
   repository.
4. **`apply-patches.ps1` step 2 asks "already patched?" by reversing the whole
   stack**, which does not reverse off the owner's tree (inventory §7). It
   behaved correctly on this copy of the base, but the owner's own folder is the
   case that still matters, and it is worth fixing independently of this folder.
5. **Documents that still say the backend "is not in this repository"**:
   `CLAUDE.md:1112`, about fourteen lines in `backend/README.md`, and six in
   `docs/JARVIS-API.md`. `README.md` and `docs/INSTALL.md` §1.3-§1.5 were
   brought up to date with this folder.
6. **`jarvis-visual-spec.json` exists in three revisions in this repository** -
   this folder's 61,301 B (the owner's), `jarvis-desktop/src`'s 73,121 B and
   `jarvis-client/app/src/test/resources`' 75,171 B. Which one is current is a
   separate question.
7. **The 12 tests beside the owner's backend are not published.** Nothing in
   this repository runs them, and one of them (`test_speech.py`) is older and
   smaller than the copy in `backend/`.
8. **The base is not regenerated by a script.** The rule is in "The exact rule,
   so it can be re-taken" above and was followed by hand; one script that
   re-takes it and fails on a difference would be the next step.

## Licence

Covered by this repository's licence (MIT - [LICENSE](../LICENSE)), like
everything else here. Third-party components and their licences are listed in
[THIRD-PARTY-NOTICES.txt](../THIRD-PARTY-NOTICES.txt).
