# EXPECTATIONS-0H.md — the exact 0H numbers for the wave-17 deploy (desktop target 0.2.448, read at 0E)

Re-taken by the **independent verifier lane**, 2026-11-11, from the frozen wave-16 file
(12,892 B). It is written against the union branch at **provisional head
`213d35f9276aed80b11804f908a6850e320b7045`** — not pushed, not merged — so every number that
depends on the frozen tree carries a status tag, and every value that can only be read at freeze
is a named **FREEZE_PENDING** placeholder with its re-derivation command (the full register is
§6), never a guess.

It says, for each number the deploy calls "0H": the value, **how it is compared**, whether it
must be exact or may move, and where the value came from. Anything that could not be established
from a real artefact is marked **NOT VERIFIED** rather than written as expected.

**Value-status key — read the tag before you use a number.**

| tag | meaning |
|---|---|
| `LIVE` | measured on the live folder, read-only, 2026-11-11 02:25 PT — a "before" value |
| `BASE` | measured at `1087d81c11f59f35059032c54d84da81c18b02a1` (the 0.2.446 merge: the tree the live folder was deployed from) |
| `P @213d35f92` | **PROVISIONAL** — measured at the union head above, derived from the tree (`git cat-file`, `$SHIPPED`, `git diff`); re-derive at the frozen head |
| `FREEZE_PENDING` | only knowable at freeze / from the 0H log; written as `<FROZEN_…>`, command in §6 |
| `VARIES` | a live counter that must be read at 0H and never pinned |

**0H** is the read-only dry run of `tools/reconcile_live_backend.py` taken at the deploy,
**after** the app/backend stop and **before** `apply`. It writes nothing. Its numbers are what
`apply` must then match.

**Version note.** `0.2.447` was the pre-merge arithmetic. PR **#1225** (ten `jarvis-desktop/`
files) consumes Desktop release run **447**, so the union merge is expected to publish
**0.2.448** (Lead decision, 2026-11-11). The deploy target is whatever gate **0E** reads from the
two releases — `0.2.448` is the expectation, never a typed constant, and this file writes it as
`0.2.448` wherever a rule depends on it.

---

## 1. The numbers, and the tolerance on each

| # | what the 0H log says | expected | must it be exact? | how it is compared | status |
|---|---|---|---|---|---|
| 1 | `SHIPPED (N files in $SHIPPED, flattened)` | **336** | **EXACT** | string + the count; 336 unique names | `P @213d35f92` — 336 entries in `$SHIPPED` in `scripts/apply-patches.ps1`; 335 at `BASE` |
| 2 | `to add:` | **1** (`jarvis_review.py`) | **EXACT** | exactly one name, and it is `jarvis_review.py`. **The wave-16 expectation "no file is new in this wave" is FALSE here** | `P @213d35f92` — the only `$SHIPPED` name with no blob at `BASE` |
| 3 | `to update:` | **15** | **EXACT** | and the 15 names are the 15 updated rows of §3 | `P @213d35f92` — `git diff --name-only 1087d81c1 213d35f92` ∩ `$SHIPPED` |
| 4 | `unchanged:` | **320** | **EXACT** | 336 − 15 − 1 | `P @213d35f92` — arithmetic over the two counts above |
| 5 | `HUD DELTAS (N patch/file delta(s) checked)` | **234** | **EXACT at 0H** | the tool's own count; expected unchanged because the HUD page is byte-identical at both shas and `$PATCHES` is still **180** | `FREEZE_PENDING` — read the new log; 234 is the wave-16 count, kept only as the expectation |
| 6 | HUD `already present` / `to insert:` | **234 / none (0)** | **EXACT at 0H** | `insert 0` is the corrected expectation; anything else is a STOP | `FREEZE_PENDING` |
| 7 | `VERSION: unchanged 0.2.446` | **0.2.446** at 0H; after `apply` it must read `wrote 0.2.448` (expected **0.2.448**) | **EXACT, at 0H only** | live `VERSION` is 7 B, no newline, `30 2e 32 2e 34 34 36` | `LIVE` for 0.2.446; `FREEZE_PENDING` for the after value (0E) |
| 8 | `BESIDE: unchanged requirements.lock` / `quiz_grader_cases.json` | **unchanged, both** | **EXACT** | this wave changes neither | `P @213d35f92` — neither path is in the union's 107-path diff |
| 9 | `PYCACHE: N stale .pyc file(s)` | **measured at 0H — do not pin** | **VARIES** | see §2; **231** observed at 2026-11-11 02:25 PT | `VARIES` |
| 10 | `PLANNED CHANGES: P file-level change(s)` | **P = 16 + N(pycache)** | **EXACT RELATION**, value follows #9 | at N=231 that is **247**; at N=232 it is **248**; at N=233, **249** | `P @213d35f92` (row set) + `VARIES` (N) |
| 11 | `READY PLUG-INS` | **32 present / 0 to add / 26 already wired** | **EXACT** | no `plugins/` path is in the union diff, so the expectation is "unchanged by this wave" | `FREEZE_PENDING` |
| 12 | `VERSION: wrote 0.2.448 (was 0.2.446)` (apply log) | the desktop version read at 0E — expected **0.2.448** | **EXACT given the run** | `apply` sets `JARVIS_DESKTOP_EXE` to the new setup, so it writes the new version even though `install-desktop` runs later | `FREEZE_PENDING` (0E) |
| 13 | `wrote N` (apply log) | **17** if VERSION was written (16 payload + 1 VERSION), **16** if not | **EXACT given #12** | `wrote` excludes pycache | `P @213d35f92` + `FREEZE_PENDING` (#12) |
| 14 | `planned_apply` (apply log) | **17 + N(pycache)** — at N=231 that is **248** | **follows #9/#10** | 16 payload + 1 VERSION + N pycache | same |
| 15 | tool backup dirs **before** the deploy | **30** | **EXACT** | measured 2026-11-11 02:25 PT | `LIVE` |
| 16 | gatepatch backup dirs **before** the deploy | **3** | **EXACT** | `20261102-133335` 184,951 B, `20261102-133341` 190,304 B, `20261110-213818` 220,771 B | `LIVE` |
| 17 | tool backup dirs **after** | **31** | **EXACT** | `apply` creates the 31st (the rollback journal) | `LIVE` + 1 |
| 18 | gatepatch backup dirs **after** | **4** | **EXACT** | gate 4A creates the 4th — assert the **stamp**, never `count == 1` | `LIVE` + 1 |
| 19 | all `_jarvis-deploy-backup-*` dirs after | **36** | **EXACT** | 31 + 4 + 1: the 4A2 step creates `_jarvis-deploy-backup-gatepatch-extra-*`, so 36 total (35 if 4A2 did not run); the packet's own gatepatch glob prints 5 because it also matches the extra folder — expected | arithmetic |

**Rows 1–4 and 13–14 are tree facts, not log facts.** At `213d35f92` the union's `$SHIPPED`
holds **336** names; `backend/jarvis_review.py` is the only one with no blob at `1087d81c1`; and
exactly **16** `$SHIPPED` paths differ between the two shas (15 updates + the 1 add).

> **A superseded snapshot, named so it is not reused.** An earlier mid-assembly checklist quoted
> `SHIPPED 336 = 1 add + 12 update + 323 unchanged` and `PLANNED 13 + pycache`. That snapshot
> predates the union's current 107-path shape: the head rewrites three more payload files than it
> did then, so it would fail a **correct** 0H run. Use **15 / 1 / 320** and **`16 + pycache`**.

### The lines to expect — shape only; every number comes from the new log

`_summ()` prints a count and then names (up to 12, then `... and N more`), so the block reads:

```
SHIPPED (336 files in $SHIPPED, flattened):
  to add: 1
      jarvis_review.py
  to update: 15
      jarvis_accounts.py
      ... 11 more names ...
      ... and 3 more
  unchanged: 320
HUD DELTAS (234 patch/file delta(s) checked):
  already present: 234
  to insert: none
VERSION: unchanged 0.2.446
BESIDE: unchanged requirements.lock
BESIDE: unchanged quiz_grader_cases.json
PYCACHE: <N> stale .pyc file(s)
READY PLUG-INS: 32 present / 0 to add / 26 already wired
PLANNED CHANGES: <16+N> file-level change(s) = add 1 + update 15 + insert 0 + beside+version 0 + pycache <N> - DRY RUN, nothing written
```

**Sources.** The 0H rows (1–7, 9–11) are quoted from **this run's** 0H log at
`D:\jarvis-scratch\WAVE17-DEPLOY-2026-11-11\run-<stamp>\0H-dryrun.txt` (the gate also writes the
byte copy `0H.txt`) — `FREEZE_PENDING`: the run folder does not exist until the first gate. The
apply rows (12–14) are quoted from `<run>\4-apply.txt`.
**No wave-16 log is a source for this file.** The wave-16 numbers are history and stay in the
frozen copy `D:\jarvis-scratch\WAVE16-VERIFIER-2026-11-10\EXPECTATIONS-0H.md`; do not copy them
into a wave-17 receipt.

**Sources for 15–16:** `Get-ChildItem` on the live folder, 2026-11-11 02:25 PT — **30**
`_jarvis-deploy-backup-tool-*` and **3** `_jarvis-deploy-backup-gatepatch-*`
(`20261102-133335` = 184,951 B, `20261102-133341` = 190,304 B, `20261110-213818` = **220,771 B**,
the gate 4A backup that holds the pre-0.2.446 gate). All three gatepatch folders are **not** this
deploy's; the fourth will be.

---

## 2. Why the pycache count may vary — and why `PLANNED` is a formula, not a number

The live backend is a **running Python process**: it imports modules lazily and writes bytecode
while it runs. Measured facts:

- 2026-11-10 14:31 PT: **231** `.pyc` → `PLANNED 250` under the old 19-row set
- 2026-11-10 14:48 PT: **232** `.pyc` → `PLANNED 251`
- 2026-11-11 02:25 PT, this lane, on the live folder: **231** `.pyc`

So the count moves **without anyone deploying anything**. The rule:

- **Read the counter at 0H, after the stop.** Quote that number, not 231/232/233.
- **Assert the relation**, which is exact:
  `PLANNED == 1 add + 15 update + 0 insert + beside+version + pycache`, and at 0H (with no
  `JARVIS_DESKTOP_EXE` set — the 0H gate clears it on purpose) `beside+version` is **0**, so
  **`PLANNED == 16 + pycache`**.
- **247** is the expected value **at pycache 231**; at 232 it is **248**, at 233 **249**.
  Asserting "247" against a different pycache is a false FAIL. The ledger gate in the post-deploy
  sheet (`post-deploy-checks-wave17.ps1`; this folder still holds the wave-16 copy under its old
  name until that lane re-takes it) checks the relation, not the constant.
- `apply` purges every planned top-level `.pyc`, so after `apply` the folder can read **0**
  `.pyc`; gate 4A's "purge `jarvis_gate*.pyc`" step is then a legitimate **0-match no-op** and
  must tolerate it.

**Why the relation and not a document's total.** This re-take already has that trap: the deploy
GO checklist quotes `PLANNED 13 + pycache` from the same superseded mid-assembly snapshot as
§1's note, while the frozen row set is **16 payload rows**. Both statements were honest when
written; only one can be right for this run, and it is the frozen row set that decides. Quote the
log in front of you and check the relation.

---

## 3. The 16 payload rows — what `apply` must install (15 updated + 1 added)

**All 16 rows below are `PROVISIONAL @213d35f92`.** They were computed by this lane from the union
tree at that sha (`git cat-file blob` → size + sha256), not quoted. At the freeze they must be
re-derived from the **frozen** head (§6), because the union was still moving while this file was
written: it moved to `543d12b2b06d27e866f246ade04421ce5d0930e9` before this re-take was finished.
The row **set** is unchanged there (still 16 paths), but `jarvis_agent.py`,
`jarvis_asks_first.py` and `jarvis_github.py` already carry different bytes, so **every row must be
re-derived at freeze** — see `EXPECT-ROLLBACK-STRUCT-NOTES.md` §5 item 13 for the newer readings.

Provenance of the set, measured 2026-11-11 02:25 PT: `git diff --name-only 1087d81c1 213d35f92`
∩ `$SHIPPED` = **16 paths**. Every one of the **15 that exist at `BASE`** was also hashed on the
live folder and **all 15 equal `1087d81c1`'s bytes** (0 mismatches), while the **16th,
`jarvis_review.py`, does not exist at `1087d81c1` and is not in the live folder**. So the honest
ratio is **15/15 equal to `1087d81c1`, and the 16th absent** — never "16/16".

| live file | bytes | sha256 |
|---|---:|---|
| `jarvis_accounts.py` | 59,060 | `C17422F0B234F2AC4819834FF56769BDBE4FFCDF4797587A011B91A0CB914A43` |
| `jarvis_agent.py` | 1,026,801 | `2CA9C13224B324C360AE668113D25A59190CB47525C45BB0103FB8AB4613C4F0` |
| `jarvis_asks_first.py` | 197,061 | `51AE87ECDCEDADCB1B134C2765D55BC15C06137D99087E6FCC215E56E1178C5B` |
| `jarvis_card_words.py` | 63,247 | `64FA1D4A3DE6596A7C667632F0633BEFCCE1EBF65CC42195BDA64230160A3253` |
| `jarvis_claims.py` | 34,067 | `789064002592F74B803B5D2EA3172B01ACAE6A89C8655A7473CA279C9A31536B` |
| `jarvis_feature_catalogue.py` | 168,626 | `5D1C1519360E078EA84EDF7D6F6582EED1B422B35F6FD08BD006F85138CEF079` |
| `jarvis_feature_guide.py` | 244,149 | `82E763CFA358576C925998388EA74F1A794F8CDB216E1F9E9E9C54A01ED7AC0D` |
| `jarvis_github.py` | 262,273 | `203B0F3CBCBE35F8FFD9FB81D57FACB786928407850432BF9CF01D9484DF474C` |
| `jarvis_owner_check.py` | 103,516 | `57172121659EA0289C02AEE9289D1B46A6C53D7ADF2FD9FE3471B5E99443066C` |
| `jarvis_quick.py` | 1,480,230 | `E7EB80C8E7AA34F4E068276139C19E12091334CAC540A27757D7B398236B3A8F` |
| `jarvis_reach.py` | 86,345 | `18ABBE1C9E8921BAEAD02A8A3E11833468CC7CE9C7801662A8FF3172955FE2CE` |
| `jarvis_recent_changes.py` | 2,817 | `34F344C465CFF2BFC432471770D1D0451A604E339623ECDE869E7F048205EE49` |
| `jarvis_review.py` (**added** — no `BASE` row) | 87,938 | `78F12F0E814CB34EA1ED3368E669ABAF3F6B51D33160456AF0F4F1E438B105D2` |
| `jarvis_settings_registry.py` | 282,997 | `5E2E38B7BD9C9F593E42164A14FAD89AC08F47C46BD93128B3C97879D4A733D4` |
| `jarvis_tool_profiles.py` | 173,726 | `69E723B03119B5FE65263E0F1F134755310A76AE35699B4B6CB1157163B8CD39` |
| `jarvis-self-code.json` | 317,220 | `5BEB63FB3F36445457F60C3F2565DD69ACA94C93A22D8009408E483600896710` |

**What changed in the set, against the wave-16 file's 19 rows.** Five rows left the table —
`jarvis_auto_learn.py`, `jarvis_connect_account.py`, `jarvis_project_read.py`,
`jarvis_memory.py` (the last from `backend/rebuilt/`, so **no row comes from `rebuilt/` any
more**) and `jarvis_hud.html` — and two names that had dropped out earlier came back:
`jarvis_accounts.py` and `jarvis_feature_guide.py`. Two rows are new to the table:
`jarvis_owner_check.py` (102,754 B at `BASE`) and the added `jarvis_review.py`. The arithmetic:
19 − 5 + 1 (owner_check) + 1 (review) = **16**.

**Notes on the table.**

- **15 of the 16 are `.py`**; `jarvis-self-code.json` is the self-code snapshot. No row is a page
  and no row is a config file.
- **`jarvis_review.py` has no `1087d81c1` ancestor at all.** A rollback cannot "restore" it; it
  must be deleted (`ROLLBACK-WAVE17.md` §2/§7 assert the absence).
- **`jarvis-self-code.json` is generated last on the union branch** (Lead decision, 2026-11-11).
  Its value here is the `213d35f92` one; at freeze it must match its own tree, and a mismatch is a
  STOP-and-reconcile, not a pin.
- `jarvis_recent_changes.py` **shrank** (2,931 → 2,918), so a "new bytes > old bytes" assertion is
  false for it.
- The base bytes of the 15 rows that have a `BASE` row — the rollback target — are tabulated in
  `ROLLBACK-WAVE17.md` §7. They are **not** repeated here; one table, one owner.

Re-frozen note: the wave-16 file said "re-frozen 2026-11-10 after PR #1222's commit
`37a3cc4ca`: only `jarvis_agent.py` changed". That history is not this wave's. This re-take's
freeze note belongs to the wave-17 packet and names the **frozen** candidate sha, tree and merge
sha — all `FREEZE_PENDING`.

**The `jarvis_gate.py` is NOT one of them.** It is not in `$SHIPPED` (it is a patched base file),
so `apply` stages nothing for it — gate 4A is the only carrier of the new gate rows. That is why
`insert` is 0 **and** `add` is 1 at the same time: `add` counts whole new `$SHIPPED` files,
`insert` counts in-file HUD deltas. They are different counters; neither contradicts the other.

### 3.1 Gate 4A, re-derived by this lane (not quoted)

**`PROVISIONAL @213d35f92`.** Live `jarvis_gate.py` today is **223,701 B /
`A75B15C9D53ED58AE24824E1E05EEBF8CDD4750AEC0F5D567C0754EB5398DD17`** — wave-16's *after*
image, so it is wave-17's *before*. Its own github block is **7,171 B / `6D76FE93…`**, measured
in this lane at byte offset **205,617** with a **10,913**-byte suffix (`205,617 + 7,171 + 10,913 =
223,701`), exactly **1** occurrence.

Replacing that block with the re-cut block from the union's `jarvis-backend/jarvis_gate.py`
(**13,996 B / `1CE451F67A16252F038471F214ED88C34E636554BE6DC1DC45A5F1521D0F9B89`** at the frozen head, exactly 1 occurrence there) gives, measured in
scratch on 2026-11-11:

- **230,526** / **`B3D03643A3679EDED7A47F102DB0AD75DD320E69F59BE5DDF5584A422C02AC85`** — measured
  on the frozen tree (was provisional 228,590 B / a scratch hash)
- **20** `"github_…": "…"` tool→action rows (was provisional 18; live had 10 before the deploy)
- `"github_pr_scan"` × 1, `"github_merge_pr"` × 3, `"github_fix_and_push"` × 3 — **unchanged** (measured)
- the probe's "old docstring" line moves with the block: it must now pin the **wave-16 ten-tool
  line** and find **0** occurrences (the six-tool line has been gone since wave 16); the new
  block's header wraps as `the seventeen GitHub tools, and FOURTEEN` / `actions`, so a probe for
  `and fourteen actions` would also find **0**
- the **205,617-byte prefix** and the **10,913-byte suffix** are byte-identical to the pre-repair
  file — derived, not assumed: `205,617 + 12,060 + 10,913 = 228,590`, and
  `223,701 − 7,171 + 12,060 = 228,590`

**A hash can never be derived, only measured.** The byte total is checkable by arithmetic; the
sha256 above came from actually building the image in scratch and hashing it, and it must be
re-derived from the **frozen** tree (§6). Note the union's own base gate is **203,058 B** at
`213d35f92` (195,503 B at `BASE`) — it is a different lineage from live's, which is why 4A is a
block substitution and never a copy.

### 3.2 The HUD page

**778,164 B / `84812A4F…E6F2`** — unchanged by this wave, and verified three ways at `213d35f92`:

- `backend/jarvis_hud.html`, `jarvis-desktop/src/jarvis_hud.html` and
  `jarvis-backend/jarvis_hud.html` are **one git blob** (`6ee523bc8ca7…`) at both `1087d81c1` and
  `213d35f92` — same bytes, same sha256;
- hashing the head blob gives exactly `84812A4FA4C5A8AD35B02721F4CE2914E7C5361EA265E1299253FD2F2ABAE6F2`;
- the live file is that same pair today (2026-11-11 02:25 PT).

The live folder carries **one** of the copies (`jarvis_hud.html`); the desktop's own copy is
inside the installed exe and cannot be read as a file. **776,898 B / `095772B9…` is the 0.2.445
page and must not appear anywhere in this wave's documents** — a rollback to 0.2.446 has to leave
the HUD at 778,164.

---

## 4. What "PASS" means for these numbers

- **All of 1–8, 11–13, 15–19 are exact.** One differing value is a **FAIL**, not a rounded pass.
- **9 and 10 are a measured pair.** PASS means `PLANNED == 16 + pycache` with the pycache count
  read at the same moment. Pinning 247 with a different pycache is a false FAIL; accepting any
  PLANNED number is a false PASS.
- **BLOCKED / PARTIAL / SKIP are never passes** (the project's 2026-10-11 rule). A 0H log that
  cannot be produced leaves the ledger row BLOCKED and the acceptance incomplete — it does not
  become a PASS by silence.
- The 0H numbers are **read-only expectations**. If the 0H run disagrees with any exact value,
  **STOP before `apply`** — nothing has been written yet, which is the cheapest possible moment
  to stop.

---

## 5. NOT VERIFIED — things this document does not claim

These are written here so nobody reads a gap as an expectation:

1. **The 0H dry run was not executed by this lane.** It needs the live folder at the 0H stop plus
   a worktree at the frozen ref, and no wave-17 run folder exists yet. Rows 1–4 and the row table
   in §3 are **derived from the tree** (`$SHIPPED`, `git diff`, `git cat-file`); treat them as the
   expectation the 0H log must reproduce, and re-derive them at the frozen head. **NOT RE-RUN
   HERE.**
2. **The 0.2.448 installer's own bytes are unknown until CI publishes them.** Read them at 0F
   (`Get-Item` / `Get-FileHash` on the downloaded asset, and the release API digest) — never from
   this document. The **0.2.446** installer, which is this wave's *rollback* source, is known and
   measured: `D:\jarvis-install-test\setup-wave16.exe`, **5,788,167 B** /
   `019CF3EBB5E6FC0400D5F28FDEF693440BCB993D884FF24B8ADE160E1B83983D`, FileVersion **0.2.446**
   (see `ROLLBACK-WAVE17.md` §4). The wave-16 file's §5.2 numbers (`exe 13,266,432 /
   E4EC1E15…`) do not match the published 0.2.446 asset measured here, so they are not the
   installer this wave would roll back to — do not carry them into a new document.
3. **The phone build is read, never typed.** Today's phone is **0.2.4059** (versionCode
   **1000004059**, installed 2026-11-10 21:39). The next build's number is its own
   `jarvis-client.yml` run number, already past **4069** at 10:02Z on 2026-11-11 because PR runs
   consume numbers; the APK row records it and proves the wave-17 phone text instead of pinning a
   number this lane cannot know.
4. **The live `jarvis-framework.toml` hash is the owner's.** It is **58,610 B /
   `209AC2FE46E636F4A115173A10C61E25305C1AE548642659EC5CDEB2F140705B`** today (mtime
   2026-11-10 22:39:22), moved from the frozen `58,409 / 9C6CDF76…`: **one key changed,
   `tools.enabled` 14 → 24** with the ten GitHub tools. Under the Lead's decision (Q6) this is the
   new baseline, **record-never-revert**: the deploy must not write it, the ten names must still be
   there after `apply`, and a different hash after the deploy means the **owner** edited it.
   `58,409 B / 9C6CDF76…` is stale and must not be used as a baseline.
5. **The 0H figure "ready plug-ins 32 / 0 / 26"** is quoted from the 0H log; this lane did not
   re-derive it from the plug-in catalogue.
6. **The pixel half of the cockpit is not verifiable by any script.** The CSS is proven present;
   whether the installed WebView2 *draws* two columns is the owner's eyes (see
   `README-ACCEPTANCE-WAVE17.md` §5 — that file is another lane's, and is re-taken with it).
7. **The gate 4A after-image is derived, not read.** 228,590 / `564B1D87…` was built in scratch
   from the live gate plus the union block at `213d35f92`; the freeze-time value must be measured
   from the frozen tree, and the union may still move.

---

## 6. Every `FREEZE_PENDING` value, and the command that fills it

All commands are read-only (the gate 4A one writes only under a scratch `-Out`). `<wt>` is the
deploy worktree at the frozen ref; the tested block-boundary rule and the 4A derivation helper are
documented in the packet-recon lane's
`D:\jarvis-scratch\wave17-02447-packet-recon-2026-11-11\GATE4A-CHANGE-MAP.md` §§4.2–4.4.

| placeholder | where it is used | command |
|---|---|---|
| `<FROZEN_CANDIDATE_SHA>` / `<FROZEN_CANDIDATE_TREE>` / `<FROZEN_MERGE_SHA>` | §3 freeze note; the packet's own constants | `git -C <union> rev-parse HEAD` and `HEAD^{tree}`; the merge sha only after the merge (`gh pr view <PR> --json mergeCommit`) — never the PR head in its place |
| `<FROZEN_HUD_DELTAS>` / `<FROZEN_HUD_PRESENT>` | §1 rows 5–6 | `py -3 -B tools/reconcile_live_backend.py --ref <frozen> --backend-path "<live>" --dry-run` → the `HUD DELTAS` / `already present` lines |
| `<FROZEN_READY_PLUGINS>` | §1 row 11 | same dry run → the `READY PLUG-INS:` line |
| `<FROZEN_DESKTOP_VERSION>` | §1 rows 7, 12, 13 | `gh release view desktop-latest --repo darknight11ish/Epic-Jarvis --json assets --jq '.assets[].name'` (the `_0.2.N_x64-setup.exe` name) — or gate 0E's `desktopVersion=` line |
| `<FROZEN_PHONE_VERSION>` | §5.3 | `gh release view client-latest --repo darknight11ish/Epic-Jarvis --json name,targetCommitish` |
| `<FROZEN_GATE_BYTES>` / `<FROZEN_GATE_SHA>` / `<FROZEN_GATE_ROWS>` | §3.1 | cut the block from the frozen `jarvis-backend/jarvis_gate.py` with the tested boundary rule, replace it in a **scratch copy** of the live gate, then `(Get-Item).Length` + `Get-FileHash`; count `"github_…": "…"` rows in the image (`GATE4A-CHANGE-MAP.md` §§4.2–4.4) |
| `<FROZEN_BLOCK_BYTES>` / `<FROZEN_BLOCK_SHA>` | §3.1 | the same cut, on the block file itself (must be exactly 1 occurrence in the image, 0 in the live gate) |
| the 16 payload rows | §3 | one `git -C <wt> cat-file blob <frozen>:backend/<name>` per row → size + `Get-FileHash`; or the packet's `check_updated_rows.py` AST compare |
| the new 0H log | §1 sources | gate 0H writes `<packet>\run-<stamp>\0H-dryrun.txt` and its byte copy `0H.txt` |

**Shape rule the numbers cannot carry:** a payload row is a **4-tuple** in the live verifier
(`repo path, live name, bytes, sha256`) and a **3-tuple** in the post-deploy sheet
(`live name, bytes, sha`). Both must carry all 16 rows, and the added row must be in the **same**
table as the other 15 — the verifier's tree gate excludes every name in that table from the
"unchanged" comparison precisely because the added file has no base blob.
