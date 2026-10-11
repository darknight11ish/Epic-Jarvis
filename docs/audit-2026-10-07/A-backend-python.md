# Stream A — backend Python modules + patch-stack integrity

**Target:** `.dsh-scratch/audit-main`, detached HEAD `fa2b379f` (merge PR #89, 2026-10-06 21:55 -0700).
**Scope:** `backend/**` and `jarvis-backend/**` — product modules, the `.patch` stack, `rebuilt/`,
`rebuilt-patches/`, `patch-history/`, `_where.py`, `run_suites.py`, apply-patches inputs.
**Read-only:** no product file was edited. The only file written is this report.

**Volume examined:** `backend/` 753 files (434 `.py` = 344,382 lines, 264 `.patch` = 10,117 lines);
`jarvis-backend/` 186 files (178 `.py` = 193,569 lines); `scripts/apply-patches.ps1` (3,067 lines).
Static sweeps covered **all 171 product modules** in `backend/` plus the 10 in `backend/rebuilt/`;
**all 124 patches** were parsed hunk by hunk.

**Provenance caveat (not a finding, worth knowing):** the worktree is not byte-clean against HEAD.
`git status` reports `backend/decks_fsrs_golden.json`, `jarvis-client/.../Palette.kt` and
`jarvis-client/.../pattern-golden.json` modified, plus untracked `backend/run_suites_audit.py`
(the audit harness). The first and third differ from HEAD only in line endings; `Palette.kt` has a
real 51-line content diff, and it is **outside my scope** (`jarvis-client/`) — flagged to the Lead,
not counted as a backend finding. Line-ending-only differences do not affect anything below.

---

### A1. A secret shorter than eight characters is never redacted — it is written to the log in clear

**Where:** `backend/jarvis_scrub.py:108` (`_MIN_KNOWN = 8`), enforced at `jarvis_scrub.py:152`
(`register_secret`) and `jarvis_scrub.py:188` (`_known_values`, the environment sweep).

**What happens:** the two places that feed the scrubber a *known* secret both drop it when its
value is under eight characters. `jarvis_scrub.install(token)` is how the backend protects the
pairing token, and `jarvis_hud` calls it with `HUD_TOKEN` — a token the owner may well have set by
hand, and which can be shorter than the generated `token_urlsafe(32)`. The same applies to every
`*_PASSWORD` / `*_TOKEN` / `*_KEY` variable in the environment: a 4–6 digit PIN or a short mail
password is simply not in the "known values" table. The value then falls through to the *shape*
layer, which cannot recognise an arbitrary short string, so it is printed verbatim to the console
and to `backend.log`. That is rule 3 ("never logged") broken for exactly the secrets whose names
mark them as secrets.

**Reproduced, not inferred** (this machine, this worktree):

```
input : connecting with token abc1234 and password 1234 to the mail server
output: connecting with token abc1234 and password 1234 to the mail server     # 7 chars: NOT redacted
input : connecting with token abc12345 and password 12345 to the mail server
output: connecting with token [redacted: HUD_TOKEN value] and password 12345   # 8 chars: redacted
```

So the threshold is the whole difference between redacted and printed.

**Confidence:** Confirmed (ran `scrub_text` on both sides of the boundary).
**Severity:** Medium.
**Obvious or subtle:** subtle — the floor is deliberate and documented ("replacing '1' or 'yes'
everywhere would wreck the log", line 106-107), and the fix is a policy choice, not a typo.
**Fix:** keep `_MIN_KNOWN` for the *bare-value* replacement only, but treat a value that arrived
from a *named* secret (`_secret_name(name)` at line 186, and `register_secret`'s argument) as
always-redact. A name-marked secret is never the word "yes", so the reason for the floor does not
apply to it.

---

### A2. `_apply_toml_tiers.py` overwrites the owner's config **before** writing the backup it promises

**Where:** `backend/_apply_toml_tiers.py:223` (the live file is written) and
`backend/_apply_toml_tiers.py:228` (the backup is written) — while the module's own docstring at
`_apply_toml_tiers.py:50-51` says *"Writes a timestamped copy beside the live file **before** it
writes"*.

**What happens:** the order is the other way round. `live_path.write_bytes(out)` replaces the
owner's `jarvis-framework.toml` first; only then is `raw` (held in memory) written to
`jarvis-framework.toml.backup-<date-time>`. Two concrete consequences:

- If the backup write fails (folder refuses new files, disk full, antivirus holding the path), the
  tool's printed line is `Your copy from before the change: (could not be kept: ...)` — but the
  live file **has already been changed**, and the one-line undo it also prints
  ("To undo it, copy that file back over jarvis-framework.toml", line 237) refers to a file that
  does not exist.
- If the process stops or the PC loses power between the two writes, the tier table has been
  edited with no copy of the previous file anywhere. The whole point of the tool is the
  `[autonomy.tiers]` table — the approval policy — and the tool's own guarantee ("Nothing already
  here is changed", "Refuses to write unless ...", verified by `verify()` at line 147) is what
  makes it safe to run unattended from `apply-patches.ps1`.

`raw` is already in memory at line 192, so nothing depends on the current order.

**Confidence:** Confirmed (read both lines; the docstring states the opposite order).
**Severity:** Medium.
**Obvious or subtle:** obvious — a two-line move, no behaviour to decide.
**Fix:** move the backup write (lines 220-231, minus the `kept` print) above
`live_path.write_bytes(out)`, and return 2 without touching the live file when the backup cannot
be written.

---

### A3. `_where.py`'s Python < 3.10 compatibility shim can never install

**Where:** `backend/_where.py:53-67`, specifically the probe at `backend/_where.py:55`:
`Path("").write_text("", newline="\n")`.

**What happens:** the probe is meant to raise `TypeError` on a Python older than 3.10 (where
`Path.write_text` has no `newline` parameter) so the `except TypeError:` branch at line 56 installs
`_compat_write_text`. But `Path("")` is `Path(".")` — a **directory** — so the call fails before
the signature is ever checked. Measured here: `PermissionError: [Errno 13] Permission denied: '.'`
(on Linux it is `IsADirectoryError`). Neither is a `TypeError`, so the branch is unreachable and
the wrapper is never installed; the `except Exception: pass` at line 66 silently swallows it.
The consequence lands on the version the shim exists for: on Python 3.9, every
`Path.write_text(..., newline=...)` call raises `TypeError`. That is **84 call sites across 50
files** — 80 of them in **47 suite files** (e.g. `test_projects.py:1165`, `test_devices.py:592`,
`test_spending.py:134`) plus two product modules (`jarvis_app_workspace.py:284`,
`jarvis_skill_discovery.py:571`) — so on 3.9 the suites that build a fixture would error out rather
than report a result.

**Confidence:** Confirmed (ran the exact probe on this machine; the `newline=` call sites were
counted mechanically).
**Severity:** Low — the documented install path uses Python 3.12
(`docs/INSTALL.md:41`, `winget install Python.Python.3.12`), and the older-Python path is exactly
what was intended to keep working.
**Obvious or subtle:** obvious.
**Fix:** probe a file that can actually be opened for writing — e.g.
`with tempfile.NamedTemporaryFile(suffix=".tmp", delete=True) as fh: Path(fh.name).write_text("", newline="\n")`
— or simply feature-detect with `inspect.signature(Path.write_text).parameters`.

---

### A4. `jarvis_devices.py` annotates a name it never imports (`Sequence`)

**Where:** `backend/jarvis_devices.py:2048` uses `Optional[Sequence[str]]`;
`backend/jarvis_devices.py:119` imports only `Callable, Optional` from `typing`.

**What happens:** `Sequence` is undefined in the module. `from __future__ import annotations`
(line 103) makes annotations lazy strings, so the module imports and every call to
`key_card_text` works — which is why the 171-module import sweep did not catch it. It becomes a
`NameError` the moment anything resolves the annotation (`typing.get_type_hints`). Nothing in this
repository does that today (no `get_type_hints` anywhere), so **the live consequence is nil**; it is
recorded because it is a real undefined name in shipped code and the fix is one word, and because
the phone-pairing card path is safety-adjacent (it is the function that words the
`register_approval_key` card at `jarvis_devices.py:2061`).

**Confidence:** Confirmed (mechanical undefined-name sweep over product modules found exactly this
one; verified by reading both lines).
**Severity:** Low.
**Obvious or subtle:** obvious.
**Fix:** add `Sequence` to the `typing` import at `jarvis_devices.py:119`.

---

## Areas checked and found clean (with how, and how many)

Each of these is a claim I checked with a tool or a read, not an impression.

- **Patch list integrity — clean.** Every `.patch` on disk is in `scripts/apply-patches.ps1`'s
  `$PATCHES` and vice versa: **124 on disk = 124 listed, 0 unlisted, 0 missing, 0 duplicates**
  (`scripts/apply-patches.ps1:107-1109`, and the script's own guard at `:1421-1430`).
- **Patch hunk integrity — clean.** Parsed all **123** patches that carry `---`/`+++` headers
  (`thinking.patch` opens with `diff --git`, which is normal) and **all 367 hunks**: every
  `@@ -a,b +c,d @@` header count matches the number of context/`+`/`-` lines in its body. **0
  mismatches** — no malformed hunks that `git apply` would reject.
- **Patch targets — clean.** All 124 patches target modules that exist in `jarvis-backend/` or
  `backend/rebuilt/`; 39 patches touch more than one file. No patch points at a module that is not
  in the base.
- **`_where.py` SHIPPED vs apply-patches `$SHIPPED` — clean.** Both are the **same 163 entries in
  the same order** (compared with `ast`, not by eye), and every entry exists on disk
  (`backend/_where.py:128`, `scripts/apply-patches.ps1:1125`).
- **`backend/` vs `jarvis-backend/` duplication — no drift.** Every module present in both is
  **byte-identical** (SHA-256 compared: **153** same-named modules, 0 different), and the 10
  `backend/rebuilt/*.py` are byte-identical to their `jarvis-backend/` twins. `jarvis-backend/` is a
  superset (186 files, 178 of them `.py`) holding the un-patched base that lives outside this repo;
  it is not authoritative for anything
  `apply-patches.ps1` ships. The one deliberate divergence (four duplicate `jarvis_gate.py` dict
  keys removed) is disclosed in `jarvis-backend/README.md:95-121`; I re-checked it and the surviving
  values are the stricter ones, so applying the three named patches cannot loosen a tier.
- **Nothing is stale or unreferenced.** `$SHIPPED`'s 163 entries are all present; the only
  `backend/*.py` files not shipped and not patch targets are harness ( `run_suites.py`,
  `selftest.py`, `_*.py`, `eval_*.py`, `fake_mcp_server.py`, `grade-peers.py`).
- **Compiles and imports — clean.** `py_compile` over all **434** `.py` in `backend/` +
  `jarvis-backend/` + `rebuilt/`: 0 failures. Importing all **171** product modules: 171 clean
  (only `fake_mcp_server`, a script, exits with `SystemExit(0)`).
- **AST sweeps over all 171 product modules (192,536 lines) — clean.** 0 mutable default
  arguments, 0 bare `except:`, 0 unreachable statements after `return`/`raise`/`break`/`continue`,
  0 constant `if` conditions, 0 `is`-compared-to-a-literal, 0 `del` while iterating. Only 5 `assert`
  statements (2 in `eval_memory.py`, 2 in `jarvis_sayable.py:98-99`, 1 in `jarvis_wellbeing.py:151`)
  and none carries a required side effect.
- **Encoding-less `open()` — 40 hits, all false positives.** Every one is `urlopen(...).open()`,
  `os.open`, `zipfile.open` or `PIL.open`; no text file is opened without an explicit encoding.
- **Clock handling — clean.** No `utcnow` anywhere in product code; no file mixes naive and aware
  datetimes. `time.time()` (259 uses) and `time.monotonic()` (152 uses) are separated as they should
  be — wall clock for records, monotonic for timeouts.
- **TLS — deliberate, not a defect.** The only `verify_mode = CERT_NONE` in the tree is
  `backend/jarvis_email.py:140-141`, and it is scoped to a mail server on this PC
  (`_THIS_PC = ("127.0.0.1", "::1", "localhost")`, line 123); remote hosts go through
  `ssl.create_default_context()` at line 143. Documented at lines 126-136, and
  `test_email.py:279` locks the behaviour in.
- **`shell=True` — deliberate, one site.** `backend/jarvis_agent.py:371`, the command tool, which
  refuses to run at all unless `jarvis_child_env.py` can build an allowlisted environment
  (`jarvis_agent.py:355-369`). Rule 3 is respected by `jarvis_child_env.py`, which I read in full:
  an allowlist, plus a second `_looks_secret` filter, plus the three telemetry-off switches.
- **The approval stamp — clean.** `jarvis-backend/jarvis_gate.py:1166-1174` requires
  `jarvis_owner_check.take_stamp` and fails closed if the module is missing; `take_stamp` pops the
  stamp (one use only) and re-checks the HMAC and the 15-minute TTL
  (`jarvis_owner_check.py:283-293`). The int-vs-string request-id worry is a non-issue: `_mac`
  formats both through an f-string, so `12` and `"12"` produce the same MAC
  (`jarvis_owner_check.py:265-267`), and `pending()` only ever returns `state='pending'` rows with
  an `expires_in` set, so the "card stopped waiting" re-read at `jarvis_owner_check.py:684-689`
  cannot be fooled by a row that was denied meanwhile.
- **Fail-closed picture gate — clean.** `jarvis_chat_picture.clean_messages` returns
  `withhold_all(...)` on **every** unexpected exception (`jarvis_chat_picture.py:323-324`) and when
  the checker is not installed (`:295`); `_check_one` returns `part: None` for every failure shape
  (`:246-267`). No path sends an unchecked picture to a model.
- **"Erase the words" — clean.** `backend/rebuilt/jarvis_memory.py:2156-2209` turns on
  `PRAGMA secure_delete`, wipes `text` to `ERASED_TEXT`, deletes the FTS entry and the vector row
  inside one `BEGIN IMMEDIATE` transaction, then scrubs the file; the old words are read into
  `old_text` first only so copies can be erased. Restore path traversal is defended in
  `jarvis_backup._inside` (`jarvis_backup.py:1319-1324`) — it rejects `\`, a leading `/`, a `:`
  (drive letters and NTFS streams) and any `.`/`..`/empty part.
- **`run_suites.py` blind spot is not reachable.** `suite_result` reports "ok" whenever the exit
  code is 0, even with `FAIL` lines in the output (`run_suites.py:270-284`) — but that needs a
  suite that prints a failure and still exits 0, and there is none: **165 occurrences of
  `sys.exit(1 if FAILED else 0)` across 164 suite files** (the form that appears where `main()` is
  used is `sys.exit(main())` with `main` ending `return 1 if FAILED else 0`), and 260 of the 263
  `test_*.py` files exit explicitly — the 3 that do not are the `unittest` suites, which exit
  non-zero through unittest itself. The "exit 0 with no checks at all" case is correctly turned
  into a failure at `run_suites.py:270-272`.
- **`time.time_ns()` on Windows — measured, and the remaining sites are benign.** The hazard is
  real here: **12 consecutive `time.time_ns()` calls on this PC returned the identical value** (0 ns
  between them), and 199 of 200 consecutive pairs were identical. 15 sites remain, all in test
  files; the 4 that still *build a path* from it (`test_backoff_rule.py:77`, `test_backup.py:507`,
  `test_obsidian_notes.py:206`, `test_tidy.py:177`) were each traced to their assertions.
  `test_tidy.py:177` is the worst-looking — all **seven** `backoff()` calls in that suite produce
  the same path — but it is harmless: `may_offer`, `opened` and `closed` never write the state file
  (`jarvis_backoff.py:371-396`); only `declined()` and `accepted()` do (`:415`, `:427`), and the
  tidy path never calls them. The other three use distinct prefixes or assert a path does *not*
  exist. No finding — the `tempfile.mkdtemp` fix used elsewhere in the same suite is the right
  pattern, this residue just has no consequence.

---

## Summary

| # | Finding | Severity | Confidence | Obvious/subtle |
|---|---|---|---|---|
| A1 | Secrets under 8 characters never redacted — printed to `backend.log` in clear | Medium | Confirmed (reproduced) | subtle |
| A2 | `_apply_toml_tiers.py` changes the live config before writing the promised backup | Medium | Confirmed | obvious |
| A3 | `_where.py`'s Python < 3.10 shim can never install (probe opens a directory) | Low | Confirmed (reproduced) | obvious |
| A4 | `jarvis_devices.py:2048` annotates `Sequence`, never imported | Low | Confirmed | obvious |

No Critical or High finding. The patch stack is structurally sound (124/124 patches listed,
367/367 hunks internally consistent, no stray or stale patch), `backend/` and `jarvis-backend/`
have not drifted, and the safety-critical paths I could reach (the approval stamp and its
fail-closed gate check, the picture black-out gate, memory erase, restore path traversal, child
environments, log scrubbing as a mechanism) are all built to fail closed.
