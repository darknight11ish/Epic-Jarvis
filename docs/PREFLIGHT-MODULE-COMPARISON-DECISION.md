# What the preflight's module check should compare against

**2026-10-10. The decision is made.** This page says what is wrong, what the
choices were, and why the recommended one was chosen. **The owner chose option
a — compare against the record the installer writes — on 2026-10-10**, and the
change that follows from it is in its own pull request, described at the end of
this page. Nothing in `scripts/` has been touched.

## Why this page exists

`backend/selftest.py` is the preflight: the check that walks every real chain
on the PC and ends in "N pass, N fail, N warn". One of its checks is called
`modules`, and its own question is *"Is the file Jarvis runs the file you
think?"*

It cannot answer that question today, and it never can while it is written the
way it is: it compares the **installed** Jarvis against **the copy of the
modules in whichever checkout the check is being run from**. Two people in two
checkouts, looking at the same install, get two different verdicts — and
neither is wrong, because the check never says which copy is the right one.

## What the check does today

`backend/selftest.py`, `pf_modules` (lines 1331–1375). The comparison itself is
one line, 1343:

```python
theirs, ours = live.backend / leaf, HERE / rel
```

* `theirs` — the file in your installed Jarvis folder. That folder comes from
  `JARVIS_BACKEND` if it is set, and otherwise from the checkout itself
  (`_where.py:89`).
* `ours` — `HERE`, which is the folder `selftest.py` is sitting in
  (`selftest.py:82`). **This is the half that moves.**
* `leaf` and the list it loops over — `_where.SHIPPED`, 181 entries on `main`.
  That list is also a property of the checkout, not of the install.

Each file is hashed with SHA-256 over its bytes with Windows line endings
folded to Unix ones (`_sha`, `selftest.py:949–951`), so a CRLF/LF difference
alone is not reported. Any other difference is a FAIL, with no threshold
(`selftest.py:1352–1357`):

```
FAIL  jarvis_limits.py in the backend folder is not this repository's copy
      (dc77f1b9 there, d5fd7aad here)
      Most likely an older one. Run apply-patches.ps1, then restart Jarvis.
```

A shipped module that is missing from the install is its own FAIL
(`selftest.py:1345`), and a module the *checkout* lacks is skipped in silence
(`selftest.py:1349–1350`) — which is part of why the totals differ per tree.

The whole preflight returns exit code 1 if there is any FAIL
(`selftest.py:2291–2293`), so this one tree-dependent check decides the
verdict line at the bottom of the run.

## Why two checkouts give two answers — measured

Run against the *same* installed folder on this PC, with nothing changed
between the two runs:

| Run from | Shipped list | FAIL rows | Detail |
|---|---|---|---|
| the owner's checkout (`Epic-Jarvis-main`, branch `fix/widget-decides-nothing-clamped`) | 178 entries | **10** | 10 modules whose text differs |
| a clean tree based on `origin/main` (`348ffbb2`) | 181 entries | **7** | 6 modules whose text differs, plus `jarvis_plugins.py`, which the install does not have at all |

Both numbers are one FAIL row per divergent module — there is no aggregation.
The real preflight, run from the clean `origin/main` tree, printed this:

```
  FAIL  plugin-loader.patch is not in jarvis_hud.py
  FAIL  jarvis_framework.py in the backend folder is not this repository's copy (fa396738 there, 54e5e779 here)
  FAIL  jarvis_voice.py in the backend folder is not this repository's copy (a906f692 there, e5b3f208 here)
  FAIL  jarvis_voice_enroll.py in the backend folder is not this repository's copy (489b625a there, 9907046e here)
  FAIL  jarvis_settings_registry.py in the backend folder is not this repository's copy (ad261b09 there, a3924ce0 here)
  FAIL  jarvis_asks_first.py in the backend folder is not this repository's copy (168e43ac there, 4a2d8d48 here)
  FAIL  jarvis_limits.py in the backend folder is not this repository's copy (dc77f1b9 there, d5fd7aad here)
  FAIL  jarvis_plugins.py is not in the backend folder
  PASS  174 of 181 shipped modules are identical to this repository's copies

35 pass, 8 fail, 3 warn (5 skipped)
VERDICT: something is broken. Each FAIL above says what to do.
```

The same install reported **35 pass, 1 fail, 4 warn** in
`docs/ANDROID-PAIRED-AUDIT-2026-10-10.md` §2, hours earlier. Nothing about the
install changed in between; the repository's copies did. That is the fault in
one sentence: **the target moves, so the answer moves.**

There is also no way to satisfy the check from any tree today. Running
`apply-patches.ps1` from one checkout makes that checkout agree with the
install — and any later commit to a shipped module in *any* checkout makes the
next run disagree again.

## What the install actually is

The install is not junk and it is not random. Every file in it matches a
specific commit's copy exactly. For example:

| File | Installed hash | Matches the copy at |
|---|---|---|
| `jarvis_settings_registry.py` | `ad261b09` | commit `0eda5929`, 2026-10-09 17:42 |
| `jarvis_asks_first.py` | `168e43ac` | commit `c22cb5c6`, 2026-10-09 15:57 |
| `jarvis_limits.py` | `dc77f1b9` | commit `13e829c7`, 2026-10-09 15:09 |
| `jarvis_framework.py` | `fa396738` | commit `40063ab8`, 2026-10-05 14:38 |
| `jarvis_voice_enroll.py` | `489b625a` | commit `81afa6c0`, 2026-09-30 07:47 |
| `jarvis_voice.py` | `a906f692` | commit `97d63c92`, 2026-09-28 19:50 |

The install dates from 2026-10-09 21:44, and its own run log records which tree
performed it. So "what is installed" is a knowable fact — the check simply
never consults a record of it.

The audit's quoted pair is out of date by one install, and this is worth
recording because it caused real confusion: `1af5e181` is not the installed
file, it is the file the installer **replaced**. It is still on disk as
`_jarvis-backup-2026-10-09-214407\jarvis_settings_registry.py` in the installed
folder. The installed file hashes `ad261b09`, and the repository's copy hashes
`a3924ce0`.

## The choices

| # | Compare against | What it would catch | What it would miss | Effort | Risk |
|---|---|---|---|---|---|
| **a** | **The record the installer wrote** — `_jarvis-state.json` in the installed folder | Whether the install still matches what the installer put there; a hand edit; a module a run never copied; and it gives the **same answer from every checkout** | `jarvis_hud.html` (the record covers `.py` only — it needs its own entry), and it cannot say "a newer version is waiting" | Small: the record and its tests already exist | Low. Until the owner's next install writes one, the check must print a clear WARN, never a pass |
| **f** | **The published base copy** `jarvis-backend/` | The same drift, identically from every checkout | It still answers "matches the published snapshot", not "matches what your installer wrote"; the snapshot is hand-taken and documented as one patch behind | Very small: one line's meaning | Medium — a stale base moves the target again |
| b | A pinned version or commit number | "Something newer exists" | Which file, which symptom — the only thing the check is for; and nothing on the install side records a version today | Medium | High |
| c | Fetching `origin/main` when the check runs | The newest drift | It needs the network and a token, adds a new way for the preflight to fail, and still compares against a moving branch | Medium | High |
| d | Recomputing the expected file from `backend/*.patch` | The seven patched target files, which `pf_patches` already covers | 174 of the 181 shipped modules, which have no patch at all | High | High, for no gain |
| e | The copy the test suite stages | The same thing the tree's copy catches | Everything install-specific | Low | No benefit |

Two supporting facts for option **a**:

* The patcher already writes the record. `scripts/apply-patches.ps1` has a
  `-Manifest` option (`apply-patches.ps1:96–99, 125`), defaulting to
  `_jarvis-state.json` beside the backend (`apply-patches.ps1:1960`), written
  by `Write-Manifest` (`apply-patches.ps1:2832–2937`) and called at the end of
  a finished run (`apply-patches.ps1:4239–4277`). Its `files` map holds, per
  file, the file's own `sha256` (folded the same way `_sha` folds), the patch
  that owns it, and whether the run verified it. Its schema string is
  `jarvis-updater-manifest/1`, and four checks in
  `backend/test_apply_outcomes.py` already pin its shape.
* It is **not on this PC yet**, and that is expected rather than broken: the
  record was only built on 2026-10-10 (commit `c3d7a282`), after the 2026-10-09
  21:44 install. So the first run after this decision must treat "no record" as
  a plain WARN — *"no installer record on this PC yet: run apply-patches.ps1
  once, then run this again"* — and never as a pass.

Option **f** is the fallback if nothing new should be built yet. It is one
small change and it does stop one checkout disagreeing with another, which is
the immediate complaint. It is second best because it still does not answer
"is my install what the installer wrote?".

## Recommendation

**Option a — compare against the record the installer wrote.** It is the only
choice that is a fact about *this* PC, written at the moment the files were put
there; it is already built and already tested; it hashes exactly the way the
check already hashes; and it gives the same answer no matter which checkout the
preflight is run from. It also keeps two different questions apart, which is
what makes the current output confusing: *"is my install what the installer
wrote?"* (a FAIL if not) and *"is a newer version waiting?"* (a WARN).

If the owner prefers the smallest possible change today, **option f** is the
fallback, understood as a partial fix.

## What the owner chose, and what it took

**Option a.** The work that called for, and what was done:

1. **The reference itself** — `pf_modules` now reads `_jarvis-state.json` from
   the installed folder instead of `HERE / rel`. Done.
2. **A clear WARN, never a pass, when the record is absent or unreadable.** Done,
   and it is the state this PC is in today: the record is only written by a
   patcher run since 2026-10-10, and the owner's last install was 2026-10-09
   21:44. The WARN says what to run.
3. **`jarvis_hud.html`** is judged by whether it is there at all, since the
   record holds `.py` files only. A missing one is still a FAIL.
4. **The commit or version inside the record** — **not done, deliberately.**
   Writing it means changing `scripts/apply-patches.ps1`, which another pull
   request is rewriting at the same time. It is left to whoever lands that work;
   the record already carries `written`, and the check now prints it.
5. **A test that fails without the fix.** Done, and measured both ways below.

## What was built, and how it was checked

`backend/selftest.py` — `pf_modules`, plus one helper, `_install_record`. The
check now:

* FAILs, per file, when a file the record names has different bytes
  (`"<name> has changed since the installer wrote it (<hash> now, <hash> when
  recorded)"`), or when the record names a file the install no longer has;
* FAILs when a shipped module is absent from the install — the silent "feature
  switched off" incident this whole check was built for;
* WARNs, naming them, about installed `.py` files the record does not speak for;
* WARNs about files edited after the running Jarvis started, exactly as before;
* PASSes with a count of the files that still match the record, and says nothing
  any more about "this repository's copies".

`backend/test_selftest_preflight.py` — `t_modules` rewritten, plus a `_record`
helper that writes a record the way the patcher does. The suite, run with
`JARVIS_BACKEND` unset:

| Run | Result |
|---|---|
| with the change | **142 passed, 0 failed** |
| with `backend/selftest.py` reverted to `origin/main` | **135 passed, 7 failed** — every failure one of the new checks, among them "an install that matches its record passes, even where this checkout's copy differs from it" |

That second row is the point: the new test fails on the old code, so it is a
test and not decoration.

One correctness detail worth writing down, because the two hashers are not
written the same way. The record's hashes come from the patcher's
`Get-Sha256Hex -AsLf`, which decodes each file to text and re-encodes it, while
`_sha` hashes the raw bytes with CRLF folded to LF. Those two disagree on a file
carrying a UTF-8 byte-order mark or bytes that are not UTF-8. Measured over all
**201** `.py` files in this PC's install: **0 disagreements, 0 files with a
mark**. So the record's hashes can be trusted here — and a file that did gain a
mark would be reported as changed, which is the safe direction.

## What is still open

* Whether the owner's next `apply-patches.ps1` run finishes and writes the
  record. `docs/UPDATER-REDESIGN.md` §10 records that his folder refused for a
  long time; the 2026-10-09 21:44 log ends `DONE - no problems`, which is
  evidence and not proof.
* The "is a newer version waiting?" half, which the recommendation keeps as a
  WARN separate from the FAIL. It needs the patcher's own patch list read out of
  a PowerShell file, and it is not built.
* **The same tree reference still exists one file over, and is deliberately left
  alone.** `backend/_where.py`'s `require_shipped` (lines 583-616) compares
  `BACKEND / leaf` against `_HERE / n` in exactly the same way, and stops the
  *backend suites* with `sys.exit(1)` when `JARVIS_BACKEND` points at an install
  whose copies differ from the checkout the suite is run from. That one is a
  developer guard rather than an owner-facing check, and it is right where it is:
  a suite asked to grade a real install *should* refuse when the install is not
  the copy the checkout describes, because otherwise its result describes a
  different program. It is also why 42 of the 44 failures in the audit of
  2026-10-10 were environmental. It is named here so nobody thinks it was missed.

## Where the evidence is

| What | Where |
|---|---|
| The check, verbatim | `backend/selftest.py` — `pf_modules` holds it, `_sha` is at `:949–951` and the verdict at `:2291–2293` (before the 2026-10-10 change the comparison was at `:1343`, which is the line quoted above) |
| The file list | `backend/_where.py:135–573` (`SHIPPED`), kept equal to the script's `$SHIPPED` by `backend/test_shipped_modules.py` |
| The comparison target | `backend/selftest.py:1343` (`HERE / rel`), `:82` (`HERE`) |
| The record the installer writes | `scripts/apply-patches.ps1:96–99`, `:125`, `:1960`, `:2832–2937`, `:4239–4277` |
| The record's shape, already tested | `backend/test_apply_outcomes.py` (`MANIFEST = "_jarvis-state.json"`) |
| The published base and its keeper | `jarvis-backend/README.md`; `backend/test_base_matches_repo.py`; `tools/check_stale_twins.py` |
| The original incident this check was built for | `scripts/apply-patches.ps1:3895–3904`; `backend/selftest.py:47–65` ("ADD ONE CHECK PER REAL INCIDENT"); added by commit `7eb0455c` |
| The audit that hit it | `docs/ANDROID-PAIRED-AUDIT-2026-10-10.md` §2 |
| The updater design this belongs to | `docs/UPDATER-REDESIGN.md` §4.1, §5, §9, §10 |
