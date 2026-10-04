# Handoff: the 2026-10-04 audit pass

Follows [`HANDOFF-2026-10-04-test-suite-fixes.md`](HANDOFF-2026-10-04-test-suite-fixes.md),
whose section 4.1 (the erase hole) is where this pass started. The owner then
asked for the other three problem areas (§4.2–§4.4) **and** every audit that
document recommends in its section 7, with the fixes applied.

**Result:** all four problem areas green, all six audits done, and the fixes
applied: **two product bugs** (the erase hole, and a dropped correction), **one
config bug** (an action with no approval tier), **two test/CI bugs** (a suite
reading the owner's real memory, and a fixture that only matched a machine with
`sqlite-vec` installed), **four fixture-generator bugs**, three new suites, and
one promise that had no guard at all now has one. Everything below is measured
on the owner's PC; the raw outputs are under `dshwork/audit-2026-10-04/`.

Machine notes are unchanged from the previous handoff: PowerShell 5.1, `py -3`
(3.12.10), the live backend at
`C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program`, and
`JARVIS_BACKEND` + `PYTHONIOENCODING=utf-8` for every suite run.

---

## 1. The four problem areas

### 1.1 §4.1 — the erase hole: a product bug, fixed

**Symptom.** `test_memory_erase` 3 failed, `test_memory_entities` 1 failed:
after "Erase the words", the word was still in `memory.db` twice and its
portable stem once.

**Root cause (measured, not guessed).** `secure_delete=ON` covers a cell
SQLite *drops*, but **not a row it overwrites in place**. When a fact's `text`
and `meta` are updated on a page that is already full, SQLite writes the new,
shorter cell over the old one and leaves the tail of the old cell exactly
where it was; the words, the meta and the message hash survived there.
`_scrub_file()` then checkpointed the write-ahead log — which never held them,
because they were in the file's own current page image.

The fixture was bisected one ingredient at a time (`erase_probe.py`), and the
decisive ingredient is the **fillers**, not the long fact and not the
proposals:

| fixture variant | word hits left in `memory.db` after erase |
|---|---|
| full (40 + long fact + accepted + pending + 40) | 2 (plus 1 stem in an FTS page) |
| long fact removed | 2 |
| pending proposal removed | 2 (plus 1 stem) |
| accepted proposal removed | 2 (plus 1 stem) |
| **fillers removed (4 rows only)** | **0** |

With only four rows the page still has room, so SQLite *moves* the cell
instead of overwriting it — which is why every small hand repro came out clean
and only the suite saw it. The two hypotheses the previous handoff suggested
(overflow pages; `proposals.replaces_text`) are both **disproven**.

**Fix.** `MemoryStore._scrub_file()` (`backend/rebuilt/jarvis_memory.py`)
now does: FTS `optimize` → **`VACUUM`** → `wal_checkpoint(TRUNCATE)`. The
checkpoint **must come after** the VACUUM: a VACUUM on its own writes the
rebuilt file into `memory.db-wal` and leaves `memory.db` byte-for-byte as it
was (measured: same size, same 2 hits) — which is exactly why the old order
never removed them. VACUUM rebuilds the file from the rows that survive, so
the words are gone from the file rather than merely unreachable.

* Cost: 0.02 s on the owner's own 172 KB `memory.db`; paid once per erased row,
  and erasing is a deliberate action.
* Works with the real schema: the owner's file has `facts_vec` (`vec0`,
  sqlite-vec 0.1.9) **and** `facts_fts` + its shadow tables; VACUUM handles
  both (measured on a copy).
* Honesty: `file_clean` is now true only when **both** the VACUUM and the
  checkpoint worked, so a blocked rewrite reports "an older copy may stay in
  memory.db or memory.db-wal" instead of claiming the words are gone.

**Verified.** `test_memory_erase` **85 passed, 0 failed**;
`test_memory_entities` **129 passed, 0 failed** (was 82/3 and 128/1).

### 1.2 §4.2 — `test_memory_intake`: a product bug *and* stale assertions

The previous handoff called this "stale assertions, product correct". It was
not: **the correction card was being dropped and a plain duplicate was queued
in its place**.

**Root cause (measured).** Two rules interacted:
1. `learned_text()` adds `" (as of <date>)"` to a fact from a conversation
   more than two days old. `near_duplicate()` compared `shape(text)` on the
   **raw** text, so that machine-added date counted as a word: the plain
   re-proposal was no longer a near-duplicate of the kept fact, and got queued.
2. `propose()`'s in-pass `have` set matches on text, and it has **no
   correction exemption**. The correction arriving later in the same batch had
   exactly that text, so it was skipped — the owner saw a duplicate card and
   no correction. `jarvis_intake`'s own documented rule is "a correction is
   never dropped".

**Fix (product).** `near_duplicate()` now compares `shape(undated(text))` —
dates aside — which is what its sibling `_repeats_of()` has always done. The
owner's own dates are untouched: an absolute date they said stays in `shape`'s
number set and a relative one in its date-word set.

**Fix (test).** The suite's three exact-string counts now compare
`jarvis_intake.undated(...)`, because every queued fact carries the date
suffix; and the correction check was **strengthened** from "some card carries
a `replaces` string" to "exactly one card carries the old wording **and names
the fact id it would retire**" — the weaker form is what let this bug through.

**Verified.** `test_memory_intake` **174 passed, 0 failed** (was 169/5);
`test_auto_learn` 396/0; and the memory self-test shows every learner kind
unchanged (see §3.6).

### 1.3 §4.3 — `test_extraction_wiring`: the suite reached the owner's real memory

The previous handoff guessed "the Ollama model not being loaded". It was not:
the fake extractor never raises in that test.

**Root cause (measured, and reproduced by test order).** The learner's pass
calls the *real* `jarvis_intake.propose()`, which builds its prompt from
whatever store `jarvis_memory` already has loaded. Nothing pinned one, so once
any test in the process had imported `jarvis_memory`, the next pass read the
**owner's own `~/.openjarvis/memory.db`** — and fastembed downloaded
`bge-small-en-v1.5` (about 15 s the first time) while holding that store's
lock. The burst test then reported "0 passes for 4 turns" because its pass was
waiting on the previous test's download. The test passes in 0.0 s on its own.

**Fix (test-harness).** The suite now pins a scratch store with an
8-dimension hash embedder (no download, never trusted for meaning) before any
test runs, so every pass in the file is the millisecond business it was
written for and nothing touches the owner's memory.

**Verified.** `test_extraction_wiring` **42 passed, 0 failed in 8 s**.

### 1.4 §4.4 — `test_voice_contract`: 18 of 21 cases read the machine's GPU

**Root cause.** `jarvis_voices.status()` → `_better_row()` → `_second_card()`
→ `jarvis_second_card.detect()` → `nvidia-smi`. The generator installed the
card stand-in in only **three** blocks; the other **eighteen** cases read the
real machine — three values each (`can_turn_on` / `card` / `why`), 45 values
in all.

Why the suite was still green here: the owner's real second card **is** an
RTX 2060 12 GB, the very name the stand-in uses, so a fresh run matched the
committed fixture by coincidence.

**Fix (generator).** `DEFAULT_CARDS = SCG.SMI["2080s_2060"]`, and the
generator's `World` now installs the stand-in for **every** case (`__enter__`
installs, `__exit__` removes); the one-card case passes its own. Fixture bytes
did not need to change.

**Verified.** `test_voice_contract` **737 passed, 0 failed**; and with
`nvidia-smi` made unreachable (an environment the three required configs
cannot see) the pre-fix generator produced 302 diff lines, the fixed one 0.

---

### 1.5 The two failures a fresh patcher run still had (found 2026-10-04, later)

The owner re-ran `apply-patches.ps1` and sent back a log from **09:24**, before
this pass: six suites. Four are §1.1–§1.4. The other two needed their own look:

* **`test_wellbeing` never ran** — it *refused*, because `require_shipped()`
  found the PC's `jarvis_intake.py` was an older copy than the repository's.
  That mismatch is exactly what this pass's staging repaired; the suite now
  runs and is **213 passed, 0 failed**.
* **`test_suite_state` (16 passed, 2 failed)** — it re-runs
  `run_suites.py test_task_control.py` in the CI/repo shape, and one check in
  that nested run failed: *"exactly one card was raised, under the ORIGINAL
  action's tier"*. Cause: `jarvis_agent.py` resolves a tool's lookup name to
  its action through `jarvis_gate.action_for_tool()`, inside a
  `try/except Exception: pass` — and **`jarvis_gate.py` exists only on the
  owner's PC**, so in a repo/CI run the resolution cannot happen and the card
  is raised under the raw lookup name (`jarvis_ui_control_run`). The product's
  fallback is safe (that name has no tier line, so it reaches the gate as
  `unknown_action_tier`, "ask"), but the *resolved* name is unprovable without
  the module.

  Fixed the way this project already handles an absent owner file: that one
  check now runs when `jarvis_gate.py` is here, and is **SKIPPED with its
  reason** when it is not (`test_task_control.py` already had the same pattern
  for `jarvis_hud.py`) — never reworded to match the fallback, which would
  enshrine it. `test_task_control.py` is **112/0 both ways** (the check really
  runs on the owner's PC), and `test_suite_state` is **18/0**.

## 2. The audits

### 2.1 §7.1 — promises vs tests
`backend/test_promise_guards.py` (**141 passed, 0 failed**) maps each promise
in CLAUDE.md / ARCHITECTURE.md to the product guard that enforces it and the
test that owns it, and asserts both still exist. Every promise with a guard
was **broken on purpose on a copy of the backend** and the named suite shown
red, then restored — never in the owner's own backend folder.

Five items came back **UNGUARDED**; the report lists each with the smallest
honest guard. Three are now closed:

* **`X-Jarvis-Client: hud` had no test at all** — every suite stubs
  `_origin_ok`, so replacing its last line with `return True` broke nothing
  (the audit re-ran all twelve suites that name `_origin_ok` to prove it).
  Closed by `backend/test_origin_hud_header.py` (**14 passed, 0 failed**),
  which lifts the **real** `_origin_ok` out of the installed `jarvis_hud.py`
  with `ast` and drives it: a served Origin is allowed, an unserved one is
  refused (DNS rebinding), a trailing slash still counts, and an Origin-less
  request is allowed **only** with `X-Jarvis-Client: hud` exactly. Proven:
  with the real fallback changed to `return True`, **7 checks go red**.
* **The every-interface refusal's order** (rule 2, "never opens a public
  tunnel") was asserted only against the *rehearsed patch text*, never the
  installed file. Closed by `backend/test_public_tunnel_refusal_order.py`
  (**11 passed, 0 failed**): the real `_refuse_every_interface` /
  `_binds_every_interface` are lifted with `ast` and asked about `0.0.0.0`,
  `::`, `::0` and an empty address (all `SystemExit(2)`), about every
  spelling in the shared `bind-address-cases.json` that **this machine's
  resolver** reads as every-interface, and about the contract's "refused"
  list (none of which may be refused); and `main()`'s refusal call is
  asserted to come before `ThreadingHTTPServer((bind, HUD_PORT), ...)` in the
  installed file. Proven: moving the refusal after the socket → 2 red,
  making the wildcard check a no-op → 3 red, restored → green.
* **The desktop Rust tests** were not *run* by the audit, but CI already runs
  `cargo test` (`.github/workflows/ci.yml`), so this is a verification gap in
  the audit rather than in the product.

Still open, recorded rather than half-fixed: the phone's own Keystore key +
fingerprint prompt for a risky approval (Kotlin, reachable only from Android
instrumentation tests), and "a key goes only to the one service it
authenticates against" as a general rule (proved for the chatbot API adapter,
not for every keyed feature).

### 2.2 §7.2 — fixture hermeticity
**48 generators × 4 environments (owner config / empty config / suite env /
no `nvidia-smi`), 192 runs, all byte-identical** to the committed fixtures.
Three leaks found and fixed:
1. the graphics card (§1.4);
2. **eleven** generators wrote CRLF on Windows where the repository holds LF
   (`.gitattributes`: "LF everywhere") — nine dirtied their fixture on every
   run, and three fixtures were committed CRLF because of it; fixed with
   `newline="\n"` and three fixtures regenerated (content identical);
3. **two** generators appended to the owner's **real** audit log
   (`~/.openjarvis/logs/jarvis-*.jsonl`) even with the config folder pointed
   elsewhere, because the shipped TOML's `log_directory` wins; fixed with the
   wrapper `jarvis_framework`'s own documented hook — re-measured 0 lines.

Independently re-checked here (`fixture_spotcheck.py`): six generators,
including the two audit-log ones, reproduce their fixtures byte-for-byte and
leave the owner's log at the same line count (2197 → 2197).

**A fourth leak, found by the Windows-CI audit and fixed here.** The
`memory-words-cases.json` fixture is generated by a store whose
`vector_search` / `unembedded` fields come from whether **sqlite-vec** is
installed. CI leaves the memory packages out *on purpose*, so the same
generator wrote 20,991 characters with it and 22,503 without (`vector_search`
true → false, `unembedded` 0 → 4), and `test_memory_words.py` failed in CI on
a fixture its own machine had just written. `tools/gen_memory_words_cases.py`
now states the extension's presence (`st._vec_ok`, marking the four scratch
facts embedded) instead of reading it off the box.

**Verified.** With sqlite-vec present **and** with it blocked as CI has it:
`test_memory_words` **14 passed, 0 failed** in both, and the blocked document
is byte-identical to the committed fixture (same sha256).

### 2.3 §7.3 — the Windows-vs-CI gap
A new `backend-windows` job in `.github/workflows/ci.yml` (pure insertion; the
Ubuntu job is byte-for-byte unchanged): `windows-latest`, 90-minute timeout,
**209 of 244 backend suites** run one at a time in repo mode. The 35 left out
each have a reason and its own output: 14 need a file only the owner's PC has,
7 need a rebuilt module only `run_suites.py` stages, 9 are only too slow, 3
ran and failed, 2 need packages the job cannot have.

Two real findings:
* **Fixed in the job:** the Ubuntu four pins are not enough on Windows —
  `tzdata` (Windows has no system time-zone database; `test_progress` failed)
  and `uiautomation` (the Windows screen readers; `test_screen_win` failed).
  Both are already declared for `win32` in `requirements.txt`; the job now
  installs them, and both suites pass.
* **Found and fixed here:** `test_memory_words` (§2.2).

Not proved: the job has never run on GitHub (this is a downloaded ZIP with no
`.git`, so there is nothing to push); repo mode is not the Ubuntu job's
configuration, so the ~21 suites needing owner files or the staged backend are
still Ubuntu-only.

### 2.4 §7.4 — "the test reads the source as text"
The handoff's "six" was an undercount: an AST census found **22 suites and 62
assertions** whose scope over a product module was a fixed character window or
a verbatim spelling. All 62 now use an AST or indentation-delimited block
read, each with a presence guard so a vanished marker cannot pass vacuously.
Every one was proved to still have teeth: green on the real text, **red** with
the property removed, green with 40 unrelated lines added inside the block;
and for 40 of them the *old* form goes red on that same grown text — the rot
reproduced. Six suites were also run end to end against a broken temp copy of
the backend. Final: **22 suites, 3,058 checks passed, 0 failed** (3,022
before; no check deleted).

### 2.5 §7.5 — gate-name consistency
`backend/test_gate_names.py` (**10 passed, 0 failed**) treats the live backend
as the authority: every tool's own lookup name must resolve to a real action
(not `unclassified_tool`), every action a suite names must still exist, every
action the gate can resolve must have an explicit tier line or be a recorded
fall-through, and the repository's shipped tier table must name nothing the
live one lacks. Teeth proved both in-process and against a broken backend
copy.

**Finding, and fixed:** five actions the gate could resolve had **no** tier
line and silently took `unknown_action_tier` (`"ask"`). Four are documented as
deferred (`control_browser`, `control_phone`, `research_authenticated`,
`run_plan`). The fifth, **`phone_notifications_read`**, is named by the
module, the denial list and `_RISK` but by neither TOML — an oversight. It now
has an explicit `= "ask"` line in **both** the repository's shipped table and
the owner's own `jarvis-framework.toml` (behaviour unchanged: `"ask"` is what
it already resolved to). The suite names the four remaining fall-throughs on
every run and goes red on any new unrecorded one.

### 2.6 §7.6 — memory quality with the real embedder
Full self-test run with the owner's real `BAAI/bge-small-en-v1.5`, before and
after this pass's learning change: `--against` compared **124 rows, every one
"unchanged"**, no "WORSE" line — so the change is kept under the project's own
rule. The distance-floor question from the previous handoff's finding 5.1 is
now measured (at 1.1 no wrong fact comes back where 1.0 returns one for ~5% of
unanswerable questions, at identical recall) and **deliberately not retuned**:
`eval_memory.py` chooses that floor on the tune half only, and it chose 1.0;
moving it on the strength of the held-out half is the peek the split exists to
prevent. Numbers, method and the next honest step (a bigger golden set) are on
the new scoreboard page, [`MEMORY-SCORES-2026-10-04.md`](MEMORY-SCORES-2026-10-04.md).

---

## 3. What was changed on the owner's PC (and how to undo it)

| What | Where | Undo |
|---|---|---|
| `jarvis_memory.py` (the VACUUM fix) | `Desktop program\jarvis_memory.py` | `dshwork\audit-2026-10-04\staged-backup\jarvis_memory.py.before-2026-10-04` |
| `jarvis_intake.py` (dates-aside fix) | `Desktop program\jarvis_intake.py` | `dshwork\audit-2026-10-04\staged-backup\jarvis_intake.py.before-2026-10-04` |
| one `[autonomy.tiers]` line | `Desktop program\jarvis-framework.toml` | `...\staged-backup\jarvis-framework.toml.before-tier-line` |

Both staged modules are byte-identical to this repository's copies, so
`apply-patches.ps1` reports them as up to date. **Nothing else on the PC was
written**: every red-on-purpose proof ran against a copy of the backend in
`%TEMP%` or `dshwork/`, and the live files were only read.

---

## 4. Not proved, and left open

* The real learner (`--learner-model qwen3:8b`) was not asked for; the
  model-free learner kinds are all unchanged, before and after.
* The Windows job has never run on GitHub (§2.3).
* `test_promise_guards.py` proves the *existence* of each guard and its owning
  test; the behavioural red-proofs are in the audit's evidence, not in the
  suite.
* The 16 patch-rehearsal suites in §2.4 have site-level red proofs, not
  suite-level end-to-end ones: a mutation would have to go into a `.patch`
  file.
* UNGUARDED, recorded and not patched: the phone's Keystore/fingerprint half
  of a risky approval, and "a key goes only to the one service it
  authenticates against" as a general rule.
* The relevance floor stays at 1.0 until a bigger golden set re-chooses it
  (§2.6).

## 5. Hygiene

* `dshwork/audit-2026-10-04/` holds this pass's evidence and can be deleted once
  its reports have been read. It is large — about 90 MB — because the audit-01
  evidence keeps its own **copies** of the backend (byte copies made so that
  promises could be broken without touching the owner's install). The reports
  worth keeping are `audit-0{1,2,3,4,5}-*.md` (audit 6 is
  `docs/MEMORY-SCORES-2026-10-04.md`); everything under `*-evidence/` and the
  `*.py`/`*.txt` probes is supporting raw output.
* `final-run.txt`, `final-run2.txt` and `yt-out.txt` in the repository root are
  the previous pass's leftovers; still safe to delete.
* `dshwork/audit-2026-10-04/staged-backup/` holds the three pre-change copies of
  the owner's files (§3). **Keep it** until the owner is happy with the changes.

## 6. How this was verified

**The full run, the way the owner runs it:**

```powershell
cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"
powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -FixLineEndings
```

> `skip  248 suites passed, but 29 of them skipped part or all of their checks.`
> `DONE - no problems, but NOT fully proven (see below)`

**248 passed, 0 failed**, exit 0 — the six failures the owner's earlier log
reported are all green (§1.1–§1.5), the four new suites are in it (the
patcher's list is a glob of `backend/test_*.py`, so new ones are picked up),
and the 29 skips are the known honest ones (other timezones, IPv6 wildcard
resolution, parts needing a package or a machine feature). Log:
`Desktop program\_jarvis-logs\apply-patches-2026-10-04-123118.txt`; transcript
in `dshwork/audit-2026-10-04/patcher-final-run.txt`.

**And the narrower runs, before that:**

```powershell
py -3 -u backend\run_suites.py <the 24 suites in verify-list.txt>
```

**24 passed, 0 failed, 0 skipped** against the live backend (owner's files
present), exit 0 — full output in
`dshwork/audit-2026-10-04/verify-run.txt`. The 24 are the four problem areas,
everything this pass changed, everything that `require_shipped`s a module this
pass changed, the three new suites, and the memory/gate neighbours
(`test_agent`, `test_auto_learn`, `test_bitemporal`, `test_chat_log`,
`test_forget_range`, `test_gate_names`, `test_gate_outcome`,
`test_memory_entities`, `test_memory_erase`, `test_memory_honesty`,
`test_memory_intake`, `test_memory_pane`, `test_memory_recall`,
`test_memory_safety`, `test_memory_words`, `test_origin_hud_header`,
`test_promise_guards`, `test_public_tunnel_refusal_order`, `test_rebuilt`,
`test_secret_rules`, `test_shipped_modules`, `test_topics_leaks`,
`test_voice_503`).

A 95-suite sweep was started first and **stopped**: it runs one child process
per suite and `test_auto_learn.py` alone takes 349 s, so it was going to run
for hours — the full patcher run above is the better use of the same time.

Then the patcher in adopt-and-check mode, before the full run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -FixLineEndings -SkipTests
```

> `ok  All 118 patches are already applied. Nothing to do.`
> `ok  All 158 modules this repository ships are there and up to date.`
> `DONE - no problems, but NOT fully proven (see below)`
> (the only config differences are the owner's own five, unchanged)

So the repository and the owner's backend agree on every shipped module,
including the two staged ones.

One hygiene fix made while finishing: `.github/workflows/ci.yml` had been
rewritten with CRLF endings by the Windows-CI pass. Every other workflow file
is LF and `.gitattributes` says `* text=auto eol=lf`, so the whole file would
have shown as changed in a pull request; it is LF again (parsed-identical
before and after).
