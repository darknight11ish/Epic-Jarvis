# Field-test runbook — the features that are merged or merging tonight (2026-11-03)

**Written 2026-11-03 21:50 PT, measurements through 21:53 PT. This page tests nothing by itself; it is
the script for the moment the deployed state is proven.** Nothing on the live system was changed to
write it: every command run while writing was a GET, a file read, a hash, or `gh`/`git` read-only. No
card was raised, approved or dismissed, no install folder was written, no app was restarted. (The
deploy that ran between 21:47 and 21:52 was the partner session's, not this one.)

Tonight's set is **F6 (`#1116`, merged at `378ef988a`) plus the increment that is merging now
(`#1129` / `#1130`)** — *not* the quiz (Wave B) or multi-part routines (Wave C). Three more PRs
(`#1125`, `#1126`, `#1128`) are **not** green as of 21:50 PT; their rows are CONDITIONAL and say so.

---

## 0. How to read this

| Mark | Means exactly this |
|---|---|
| **PASS** | The feature was driven on the real PC or the real phone, and the expected thing happened. A screenshot, a card, a HUD row, an API answer or a log line is named as the proof. |
| **PARTIAL** | Some of it worked. The row says which half did and which half did not. |
| **BLOCKED** | The row could not be reached. The row says why (route absent, feature switched off, PR not merged, phone not here). |
| **NOT-TESTABLE** | There is no way to test it without special setup, or the claim as written does not match the code. |

**A row is never marked PASS from reading code.** Reading `jarvis_self_portrait.py` can tell you what
*should* happen; it cannot tell you that it did. This project has a written rule for that
(`CLAUDE.md`, the 2026-10-11 decision: *"BLOCKED and NOT-TESTABLE are never counted as passes… only a
feature driven on real hardware is a PASS"*), and `docs/FIELD-TEST-MATRIX-2026-10-11.md` is where the
rule was first applied.

**Which tree a claim came from.** This checkout's working tree is on an **old `main`** (`dba25cc7d`),
which does not contain F6 at all. So every code claim below names its tree:

- `origin/main` in this checkout = **`9cf55df68`** (F6 `378ef988a` + `#1130` `916c432ee` + `#1129`
  `9cf55df68`), read with `git show origin/main:<path>`.
- PR heads were read at their own commits: `#1129` `074459ab8`, `#1130` `93966eb7b`, `#1125`
  `6490e53c9`, `#1126` `8c9afb2c3`, `#1128` `72f684738`.
- The live install was read at `C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program`
  (the folder `JARVIS_BACKEND` points at).

Do **not** compare the live folder to the files in this working tree — they are months of commits
behind. Compare it to `git show <deployed-ref>:backend/<file>`, as Gate 0 does.

---

## 1. What is actually in tonight's set (measured, not assumed)

`gh pr view` / `gh pr checks` at **21:50 PT on 2026-11-03**, for the head each PR had at that minute:

| Lane | State at 21:50 PT | The evidence | Playable tonight? |
|---|---|---|---|
| **#1116 / F6** — self portrait, conversation tools, one-card clear | **MERGED** 05:19Z as `378ef988a`; **deployed and running at 21:44** (resealed 21:31:04, server started 21:31:30) | live `jarvis_self_portrait.py` is byte-identical to `378ef988a:backend/jarvis_self_portrait.py` (git blob `b9bf311f…` both sides); `/api/self` answered 200 | **yes** — subject to Gate 0 |
| **#1130** — memory: per-fact attribution, patient sensitive ask, reworded recheck | **MERGED** 05:40Z as `916c432ee`; **deployed** — files copied 21:48:43, resealed 21:51:37, backend started 21:51:47 (byte-identical, §1.1) | `gh pr view 1130`; live mtime + `git hash-object` + `started_at` | **yes** — Gate 0 holds |
| **#1129** — Coding preset 32,768-token pooled window | **MERGED** as `9cf55df68` (origin/main moved to it during this session; all 17 checks green, `CLEAN` before merge); **deployed** in the same reseal, byte-identical | `gh pr checks 1129`; `git log origin/main`; §1.1 | **yes** — Gate 0 holds |
| **#1125** — voice check only on a locked phone | **OPEN, RED**: `backend` FAIL (44m52s), `audit` FAIL; `mergeStateStatus: BLOCKED` at head `6490e53c9` | run `41746814576`; the red suites are `test_ask_to_change.py` (its line *"…and every other switch (32) IS in the list"* FAILED) and `test_claims.py` | **only if it is fixed, merged and deployed tonight** |
| **#1126** — standby hours free the GPUs | **OPEN, RED and CONFLICTING**: `backend` FAIL, `audit` FAIL, `mergeable: CONFLICTING` at head `8c9afb2c3` | run `41743931312`; its own new suite fails `test_standby_hours.py` on **"outside the window the mode is active"** | **only if a fix lands and merges** |
| **#1128** — GitHub read + three actions | **OPEN, RED and CONFLICTING**: `backend`, `backend-windows` and `audit` all FAIL at head `72f684738` | run `41748525969` | **only if its fix lane lands** |

**The brief this runbook was written from says `#1125` and `#1126` are "green and about to merge".
That is not true at 21:50 PT** — both are red, and `#1126` also conflicts. It also says the desktop
app must be restarted "to load the new Rust": **tonight's merged set contains no Rust change** (F6 is
backend-only, `#1129`/`#1130` are Python; the desktop half is `#1115`, still open). What must restart
is the **Python backend**, and Gate 0.3 proves it did.

### 1.1 The measured state of the live install while this was written

- `21:44` — `/api/self` answers 200: **190 places**, **46 settings**, **175 abilities**, **23
  plugins**, **3 stores**. (The 59-Settings-section + 131-menu split is `#1116`'s own figure; only the
  total was read live.)
- `21:44` — `/api/self/version`: `app_version: "unknown"` ("no VERSION file beside the backend"),
  `deploy.recorded: true`, `run: "partial"`, `files_recorded: 232`, `files_verified: 3`,
  `resealed.ref = 378ef988a…`, `identity.jarvis_hud.py = 3033f447…`.
- `21:47`–`21:49` — the backend **stopped answering** (`127.0.0.1:4719` connection refused) while the
  increment files were still at their 11:50 mtimes and `resealed.ref` was still `378ef988a`. That is
  the deploy in progress. **This is why Gate 0 exists: do not start a row on a server you have not
  proven is the new one.**
- `21:48:43` → `21:51:37` → `21:51:47` — **the increment deploy completed while this page was being
  written.** `jarvis_auto_learn.py`, `jarvis_presets.py`, `jarvis_model_lanes.py` and
  `jarvis_big_coder.py` were copied at 21:48:43, the install resealed at `21:51:37` to **`9cf55df68`**,
  and the backend started at **`21:51:47`** — *later* than the files, so **Gate 0.3 holds**: the running
  process loaded the new bytes. All four files are **byte-identical** to `9cf55df68:backend/<file>` by
  `git hash-object` (Gate 0.4's own method, exercised), and `/api/self/version` now answers 200 with
  `resealed.ref = 9cf55df68`.
- The live `jarvis-framework.toml` still carries the owner's own ten-tool list
  `["calculator", "change_setting", "memory_search", "web_search", "feature_guide", "my_files",
  "calendar_read", "email_check", "home_read", "notes_search"]` — **neither deploy replaced it**, which
  is what must stay true (Gate 0.6).

---

## 2. Gate 0 — prove the deployed state before any row is attempted

Run these in **one** PowerShell window, in order. `$t` lives in that session and is never printed.
`$ref` is the commit the partner session says it deployed (tonight: `9cf55df68` unless a later PR
merges first). If any gate fails, **every row below is BLOCKED** — write that down and stop; do not
test old code and call it tonight's build.

**G0.0 — get the token without printing it.**

```powershell
$live="C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; Push-Location $live; $t=(& py -3 jarvis_token_store.py show | Select-Object -First 1).Trim(); Pop-Location; $h=@{ "X-Jarvis-Token"=$t; "X-Jarvis-Client"="hud" }; "token length: $($t.Length)"
```

Expected: `token length: 43` (the live key is 43 characters today). Never paste `$t`, screenshot it or
write it to a log. The older harness in this folder (`state_now.py`) uses
`jarvis_token_store.resolve(%APPDATA%\Jarvis\token)` for the same reason.

**G0.1 — the listener is alive.** `Invoke-WebRequest -UseBasicParsing http://127.0.0.1:4719/api/status`
answers `403` with no token (that is the origin check, i.e. alive and refusing) and `200` with `$h`.
*Connection refused = the backend is down → BLOCKED, not a feature failure.*

**G0.2 — the deployed ref matches the record.**

```powershell
(Invoke-RestMethod http://127.0.0.1:4719/api/self/version -Headers $h).deploy.resealed
```

Expected: `ref` and `commit` equal `$ref`. Anything else → the increment is not on the PC → **BLOCKED**.

**G0.3 — the running process loaded the new bytes.** Compare the server's `started_at` with the
newest mtime among the increment's modules (`jarvis_auto_learn.py`, `jarvis_presets.py`,
`jarvis_model_lanes.py`, `jarvis_big_coder.py`):

```powershell
$v=Invoke-RestMethod http://127.0.0.1:4719/api/self/version -Headers $h; [DateTimeOffset]::FromUnixTimeSeconds([int64]$v.started_at).ToLocalTime().ToString('yyyy-MM-dd HH:mm:ss'); Get-ChildItem $live -Filter 'jarvis_*.py' | Sort-Object LastWriteTime -Descending | Select-Object -First 3 Name,LastWriteTime
```

Expected: the start time is **later** than every changed module's mtime. (At 21:31:30 vs 21:27:08 this
held for F6-A, which is how the F6 deploy was known to be loaded.) If the files are newer than the
process, Jarvis is running old code → **BLOCKED until the restart**.

**G0.4 — the changed modules are byte-identical to the deployed ref.** `git hash-object` gives the git
blob id of a file; the same id on both sides means identical bytes. `cmd /c` is used so the pipe is
raw bytes and Windows does not rewrite line endings:

```powershell
foreach ($f in 'jarvis_auto_learn.py','jarvis_presets.py','jarvis_model_lanes.py','jarvis_big_coder.py','jarvis_self_portrait.py') { $a = cmd /c "cd /d ""C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"" && git show $ref`:backend/$f | git hash-object --stdin"; $b = git hash-object (Join-Path $live $f); "{0,-28} {1} {2}" -f $f, $(if ($a -eq $b) {'MATCH'} else {'DIFFER'}), $a }
```

Expected: `MATCH` on every line. A `DIFFER` means the file on disk is not the file at `$ref` — say
which one and treat the rows that depend on it as BLOCKED.

**G0.5 — the new routes are mounted.** All three must answer without raising a card:

```powershell
(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:4719/api/self -Headers $h).StatusCode
(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:4719/api/conversations -Headers $h).StatusCode
try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:4719/api/conversations/clear -Headers $h -ContentType 'application/json' -Body '{"id":"not-a-real-id-000"}' } catch { $_.ErrorDetails.Message }
```

Expected: `200`, `200`, and a JSON error for the clear probe. **Use a malformed id** —
`{"id":"bad id with spaces"}` gives `400 {"ok": false, "error": "That is not a conversation id."}`
(tested at 21:57). A plain-word id such as `not-a-real-id-000` passes the regex and answers
`404 {"ok": false, "error": "no such conversation - it may already have been deleted"}`. **Neither
raises a card**: `clear_request` checks the body, the id shape, the tier, then reads the chat, and only
a real id reaches the card (`backend/jarvis_self_portrait.py`, `clear_request`). A
`404 {"error": "not found"}` means the self-portrait plugin is not installed → **BLOCKED**.

**G0.6 — the owner's settings survived the deploy.** No writes, just reads:

```powershell
Select-String -Path (Join-Path $live 'jarvis-framework.toml') -Pattern '^\s*enabled\s*=\s*\[' | ForEach-Object { $_.Line }; Select-String -Path (Join-Path $live 'jarvis-framework.toml') -Pattern 'conversation_clear|storage_cleanup' | ForEach-Object { $_.Line }
```

Expected: the **owner's ten names** (above), and `conversation_clear = "ask"` plus
`storage_cleanup = "ask"` present. If the enabled line now reads the shipped nine-name list
(`web_search`, `change_setting`, `feature_guide`, `phone_apps`, …), **STOP** — the deploy replaced the
owner's settings file, and that is a bigger problem than any row here.

**G0.7 — record the installer's own caveat.** `/api/self/version` says `run: "partial"` and
`_jarvis-state.json` (written 2026-10-19) names **two patches left out**: `embedding-guard.patch` and
`event-allowlist.patch`, with `files_recorded: 232` and `files_verified: 3`. Copy that into the
results page. It is pre-existing, it is not tonight's deploy failing, and it means **"deployed" does
not mean "every merged patch applied"** — `resealed.commit` proves the reseal, not the patch list.

---

## 3. Group A — automatable by the Lead, no owner needed

These are read-only (or, in A3, a POST the code proves changes nothing). Each row still has to be
written up with its result; "the call returned 200" is not the point, the point is *what it proves*.

### A1 — The self portrait answers as an API

- **Feature:** `GET /api/self` — the running Jarvis's own inventory (F6, `#1116`).
- **Surface:** backend API (no app screen reads it tonight; `#1115` is the desktop half and is open).
- **Steps:** `$j=Invoke-RestMethod http://127.0.0.1:4719/api/self -Headers $h` then print
  `$j.places.Count, $j.settings.Count, $j.abilities.Count, $j.plugins.Count, $j.stores.Count,
  $j.private.locked`.
- **What should happen:** HTTP 200, `schema: "jarvis-self-portrait/1"`, **190 / 46 / 175 / 23 / 3** and
  `locked: false` on this PC (measured 21:44 on F6-A and **again 21:56 on the increment build —
  unchanged**). `places` splits 59 `settings_section` + 131 `menu` (`#1116`'s own figure).
- **How to prove it:** save that one line of counts with the timestamp; the numbers are the evidence.
  Do not save the whole body (it carries every setting's live value and the store counts).
- **Blocked if:** 401/403 (token/origin), 404 (plugin `jarvis_plugins\self-portrait` absent), or App
  lock on (`private.locked: true` withholds the store counts — that is the guard working, not a fault).
- **Source:** `origin/main:backend/jarvis_self_portrait.py` (`build`, `places`, `sections`, `menus`,
  `ROUTES`), `origin/main:plugins/ready/self-portrait/plugin.json`.

### A2 — The deploy identity the Update button will read

- **Feature:** `GET /api/self/version` — version string + the installer's recorded identity (F6).
- **Surface:** backend API.
- **Steps:** `(Invoke-RestMethod http://127.0.0.1:4719/api/self/version -Headers $h) | ConvertTo-Json -Depth 6`.
- **What should happen:** `deploy.recorded: true`, `deploy.resealed.ref == $ref`, `deploy.run`,
  `deploy.files_recorded`, `deploy.files_verified`, `deploy.identity` (`jarvis_gate.py`,
  `jarvis_hud.py`, `jarvis_skills.py` sha256), and `app_version`. **On this PC `app_version` reads
  `"unknown"` with `app_version_source: "no VERSION file beside the backend"`** (measured 21:44).
- **How to prove it:** record `resealed.ref`, `run`, `files_recorded` and `app_version` verbatim. The
  `resealed.ref` is Gate 0.2; `app_version: "unknown"` is what makes row B8 not testable.
- **Blocked if:** `recorded: false` (missing/damaged `_jarvis-state.json`; the body carries `why_not`).
- **Source:** `origin/main:backend/jarvis_self_portrait.py` (`deploy_block`, `_read_deploy_state`,
  `version_block`); `_jarvis-state.json` beside `jarvis_hud.py`.

### A3 — Refresh re-reads its own inventory (no card, no restart)

- **Feature:** `POST /api/self/refresh` — one plain sentence saying what moved (F6).
- **Surface:** backend API.
- **Steps:**
  `Invoke-RestMethod -Method Post -Uri http://127.0.0.1:4719/api/self/refresh -Headers $h -ContentType 'application/json' -Body '{}'`
- **What should happen:** HTTP 200, `ok: true`, `changed: {}` (nothing moved in a quiet minute), and
  `said` reading exactly the module's sentence —
  *"I re-read what I can do and have now: {places} places, {settings} settings, {tools} ask-first
  actions, {plugins} plugins and {abilities} abilities. Everything matches what I had. Nothing was
  restarted."* — with tonight's numbers in it (`#1116` reports 135 ask-first rows on this PC; A1's
  counts are the other four). `started_at` in the answer equals the one in A2.
- **How to prove it:** the sentence, quoted; plus `changed` and an unchanged `started_at` (proves the
  same process, nothing restarted).
- **Blocked if:** 405 (a GET — the route is POST-only, `GET -> 405` by design), 404 (plugin absent).
- **Note (this is the one POST in Group A):** the code path is `refresh()` → `_clear_caches()` →
  `build(refresh=True)`. It writes nothing, raises no card, changes no setting and carries `started_at`
  through (docstring, `origin/main:backend/jarvis_self_portrait.py`). If the Lead wants the old
  GET-only rule for tonight, skip this row and mark it BLOCKED-by-policy.
- **Source:** `jarvis_self_portrait.refresh`, `refresh_sentence`, `counts`; `GET -> 405` in `handle_get`.

### A4 — The conversation list alias

- **Feature:** `GET /api/conversations` — one History list, the same body the History screen reads (F6).
- **Surface:** backend API.
- **Steps:** `$c=Invoke-RestMethod http://127.0.0.1:4719/api/conversations -Headers $h; "$($c.conversations.Count) chats, history enabled=$($c.enabled) recording=$($c.recording) keep_days=$($c.keep_days) encrypted=$($c.encrypted)"; $c.conversations | Select-Object -First 3 id,title,turns`
  — print ids, titles and turn **numbers** only. **Do not print message text.**
- **What should happen:** 200 with the History list under `conversations` (the same body
  `GET /api/history` answers — this route is a thin alias on `jarvis_chat_log.handle_get`, so the two
  can never disagree). Each row carries `id,title,started,updated,turns,device,has_voice,tainted,kind,
  project,tag_id,pinned,pinned_at,archived`. **Observed at 21:57:** `enabled=true`, `recording=true`,
  `keep_days=0`, `encrypted=true`, **30 conversations**. App lock withholds it with the same 423 the
  History screen gets.
- **How to prove it:** the count of rows and one id; that id feeds A5.
- **Blocked if:** 423 (App lock / "Hide memory lists and chat history"), 503 (chat history unavailable),
  or `enabled=false` (history recording is off — say so; B5 then has nothing to clear).
- **Source:** `origin/main:backend/jarvis_self_portrait.py` (`conversation_list`).

### A5 — Opening one kept conversation

- **Feature:** `GET /api/conversations/<id>` — that conversation's turns (F6).
- **Surface:** backend API.
- **Steps:** `$one=Invoke-RestMethod "http://127.0.0.1:4719/api/conversations/$id" -Headers $h; "$($one.title.Length) chars in the title, $($one.turns.Count) turns"; $one.turns[0].PSObject.Properties.Name -join ','`
  (substitute an id from A4; print the **count** and the field names, not the words).
- **What should happen:** 200 with `id,title,history,tainted,turns,kind,project,tag_id,pinned,pinned_at,
  archived,started,updated,continuable,continue_why,forkable,fork_why,marks,markable,mark_why`, and
  `turns` an **array** whose rows carry `idx,role,text,at,provenance,read_outside,answer_kept`
  (observed at 21:57: 4 turns on the chat read). A malformed id (a space, punctuation) gives the read's
  `400 {"error": "need a conversation id"}`; the clear route gives its own 400 wording; a well-formed
  but deleted id gives 404.
- **How to prove it:** the turn count for that id, plus the field names (they are the same shape the
  History reader gets).
- **Blocked if:** 423/503 as A4; 404 means that chat is gone — pick another, do not read it as a fault.
- **Source:** `conversation_get`, `_CID`.

### A6 — The one-card clear refuses what it should (no card raised)

- **Feature:** `POST /api/conversations/clear` — the route's guard rails (F6).
- **Surface:** backend API.
- **Steps:** three probes, all of which must leave `/api/pending` unchanged: (1) body `{}` → 400, the
  message asking for exactly the one-id body; (2) `{"id":"bad id with spaces"}` → 400 *"That is not a
  conversation id."* (**tested at 21:57**); (3) a well-formed but nonexistent id, e.g.
  `{"id":"not-a-real-id-000"}` → **404** *"no such conversation - it may already have been deleted"*
  (**tested at 21:57** — a plain word passes the id regex, so it reaches the read, not the 400).
- **What should happen:** exactly those three, and **no card** in `GET /api/pending` before/after.
- **How to prove it:** the three bodies plus the unchanged pending count (save both counts).
- **Blocked if:** a 202 appears for any of them (a card was raised — stop, that is a bug), 503
  (`conversation_clear` is not tier `ask`), 404 *"not found"* (route absent; note the *different* 404
  body the route itself gives for an unknown id).
- **Source:** `clear_request` (body → id → tier → lock → read → card); live toml line 279
  `conversation_clear = "ask"`.

### A7 — The tools gate: what is switched OFF in the owner's own file

- **Feature:** the four F6 chat tools' precondition (and, if `#1128` lands, the six GitHub tools').
- **Surface:** the live settings file (read-only).
- **Steps:** G0.6's command, plus a search for each name:
  `Select-String -Path (Join-Path $live 'jarvis-framework.toml') -Pattern 'self_portrait|conversation_find|conversation_open|refresh_abilities|github_list|github_read_file|github_ci_status|github_comment|github_open_issue|github_rerun_workflow'`.
- **What should happen (today):** **nothing** — the owner's ten-name list does not contain any of them.
  The shipped `[tools].enabled` (`origin/main:backend/rebuilt/jarvis-framework.toml`) names nine tools
  and also none of the new ones, so this is the shipped default, not a deploy mistake.
- **How to prove it:** the enabled line, quoted. **This single line is why rows B1–B4 are BLOCKED
  tonight unless the owner chooses B0.**
- **Blocked if:** n/a — this *is* the gate. It cannot be turned on from either app: none of the four is
  in `jarvis_asks_first.TIER_A/TIER_B` (the "What asks first" switches), so the only door is the
  settings file.
- **Source:** live toml line 1149; `origin/main:backend/rebuilt/jarvis-framework.toml`;
  `origin/main:backend/jarvis_asks_first.py` (`TIER_A`, `TIER_B`, `TIER_C`, `TIER_UNLISTED`).

### A8 — The learner's own counters, before the owner talks to it

- **Feature:** the live proof `#1130` is waiting for: `saved` rises, `last_saved_at` set (DEF-017).
- **Surface:** backend API + a file under the config folder.
- **Steps:** `Invoke-RestMethod http://127.0.0.1:4719/api/memory/learning -Headers $h | ConvertTo-Json -Depth 4`
  and read `%USERPROFILE%\.openjarvis\learning-stats.json`.
- **What should happen (measured 21:52, on the increment build — the route is confirmed live):**
  `counters` = `{"passes": 5, "saved": 0, "carded": 6, "failed": 8, "last_pass_at": 1793666004.93,
  "last_error": "after_pass: OperationalError", "last_saved_at": null, "sensitive_unchecked": 0}`, plus
  the module's own `note`: *"5 learning pass(es) have run and saved nothing yet; 6 fact(s) are waiting
  on cards. The last pass failed (after_pass: OperationalError)."* The switches read `auto: true`,
  `sensitive: false`, `paraphrase: false`, and `facts_total: 1`. `last_pass_at` is **2026-11-02 16:33
  PT** — the learner had not run for ~29 hours when this was written. That is the "0 auto-saved / 6
  carded" the PR body names.
- **How to prove it:** copy those counters verbatim before the first fact test and after it (B9). The
  two numbers that matter are `saved` (must rise) and `last_saved_at` (must stop being null). **Watch
  `failed` too**: it is already 8 with `last_error: "after_pass: OperationalError"`, so a first pass on
  the new code that raises again is a real finding, not a test error — quote `last_error`.
- **Blocked if:** the route 404s (it did not — it answered 200 at 21:52); then the file is the only
  read-out, and say so.
- **Source:** `#1130` head `93966eb7b:backend/jarvis_auto_learn.py` (`learning_status`, `stats`,
  `_stats_read`); live `%USERPROFILE%\.openjarvis\learning-stats.json`; live `GET /api/memory/learning`
  at 21:52.

### A9 — The preconditions snapshot (decides several rows)

- **Feature:** the state several rows depend on: power hours, notification quiet hours, App lock,
  which model is loaded.
- **Surface:** backend API + live toml.
- **Steps:** read `[power]` (`schedule_enabled`, `schedule_mode`, `quiet_start`, `quiet_end`),
  `GET /api/status`, `GET /api/models`, and the `private` block from A1.
- **What should happen (measured 21:44):** `[power]` is `enabled = true`, `schedule_mode = "quiet"`,
  `schedule_enabled = false`, `quiet_start = "23:00"`, `quiet_end = "07:00"`. `private.locked: false`.
- **How to prove it:** one block of those values with the timestamp.
- **Blocked if:** the backend is down (nothing to read) — Gate 0.1.
- **Source:** live `jarvis-framework.toml` `[power]`; `jarvis_limits._notify_rows` for the separate
  notification quiet hours.

**Group A: 9 rows.**

---

## 4. Group B — needs the owner at the keyboard

Statuses are eligibility, not results: **READY** = attempt it after Gate 0; **DECISION** = the owner
must choose first; **CONDITIONAL** = depends on a PR that is not merged at 21:50; **BLOCKED-TONIGHT** /
**NOT-TESTABLE** as written.

### B0 — DECISION: switch on the four F6 chat tools, or record them BLOCKED

- **Feature:** the only door to `self_portrait`, `conversation_find`, `conversation_open`,
  `refresh_abilities` is the owner's own `[tools].enabled` line (A7).
- **Surface:** the owner's settings file, edited by the owner (never by a deploy).
- **Options (the owner's call):**
  - **A (recommended):** add the four names to his list and restart the backend once, before Gate 0 is
    re-run. Then B1–B4 are READY.
  - **B:** leave them off; B1–B4 are written BLOCKED with A7's line as the reason.
- **Exact edit (option A):** the line at `jarvis-framework.toml:1149` becomes
  `enabled = [ ... the ten names ..., "self_portrait", "conversation_find", "conversation_open", "refresh_abilities"]`.
  **Keep `conversation_clear` out** — it is not a tool and must never be one (see B5).
- **Before editing:** copy the file aside by hand (`Copy-Item jarvis-framework.toml
  jarvis-framework.toml.before-tonight-20261103`) so the owner can put it back; that copy is his, not a
  deploy's.
- **Blocked if:** the deploy is mid-flight (G0.3 fails) — edit only after the deployed state is proven,
  then re-run G0.3/G0.6 so the restart is proven too.
- **Source:** A7; `origin/main:backend/jarvis_agent.py` (`offered_tools` reads the list it is given;
  a tool not named there is never offered).

### B1 — Self portrait by chat — **BLOCKED-TONIGHT** (tool off; see B0)

- **Feature:** `self_portrait` — Jarvis quotes its own inventory in plain words (F6).
- **Surface:** desktop app chat (or the phone's chat, same backend).
- **Steps:** type **"What are you made of right now?"** (the tool text says *"Use when: the owner asks
  what you can do, what you have, what is connected, or where a kind of setting lives"*).
- **What should happen:** one answer with the counts — places, settings, ask-first actions, abilities,
  plugins, stores, and the version — **no approval card** (gate action `skill_list`, tier `auto`).
- **How to prove it:** the chat bubble, quoted; it must agree with A1's numbers (190 places etc.).
- **Blocked if:** the tool is off (A7) — then Jarvis answers from `feature_guide` instead, which is a
  *different* source; do not score that as a PASS.
- **Source:** `origin/main:backend/jarvis_agent.py` (`_self_portrait_tool_text`, `_run_self_portrait`,
  `SELF_READ_TOOLS`), `#1116` body: *"`self_portrait` … READ-ONLY, no card (gate action `skill_list`,
  tier auto, like `feature_guide`)"*.

### B2 — "Refresh your abilities" by chat — **BLOCKED-TONIGHT** (tool off; see B0)

- **Feature:** `refresh_abilities` — re-read and say what changed (F6).
- **Surface:** desktop app chat.
- **Steps:** type **"Refresh your abilities"** (the exact phrase in the tool text).
- **What should happen:** one sentence naming the counts and what changed; **nothing restarted, no
  setting changed, no card**.
- **How to prove it:** the sentence, quoted. It should match A3's `said` almost word for word (same
  function, `SP.refresh()`).
- **Blocked if:** tool off. The API form (A3) still proves the behaviour underneath.
- **Source:** `jarvis_agent._refresh_abilities_tool_text`, `_run_refresh_abilities`.

### B3 — "Which old chat was about X?" — **BLOCKED-TONIGHT** (tool off; see B0)

- **Feature:** `conversation_find` — titles, dates and ids only (F6).
- **Surface:** desktop app chat.
- **Steps:** type **"Which old chat was about the pooled lane?"** (or any topic he knows he discussed).
- **What should happen:** a list of chats with id, title and date — **never message text**
  (`#1116`: *"returns titles/dates/ids only, never message text"*), **no card**.
- **How to prove it:** the answer; check no message body appears. The ids must exist — A4 is the same
  list.
- **Blocked if:** tool off; or the answer invents an id (that is a FAIL, not a PARTIAL).
- **Source:** `jarvis_agent._conversation_find_tool_text`, `_run_conversation_find`,
  `CONVERSATION_FIND_MAX = 10`.

### B4 — "Open that conversation" — **BLOCKED-TONIGHT** (tool off; see B0)

- **Feature:** `conversation_open` — one kept chat's turns, local model only (F6).
- **Surface:** desktop app chat.
- **Steps:** after B3 gives an id, type **"Open conversation <id> and tell me what we decided."**
- **What should happen:** an answer about that chat's contents; stays on this PC's model; no card; at
  most the last 60 turns (`CONVERSATION_OPEN_MAX = 60`). A deleted id gets *"…deleted. Call
  conversation_find again."*
- **How to prove it:** the answer plus the id it used; the turns never leave the PC (rule 1).
- **Blocked if:** tool off; App lock (the read it wraps answers 423).
- **Source:** `jarvis_agent._conversation_open_tool_text`, `_run_conversation_open`.

### B5 — One-card conversation clear — **READY**

- **Feature:** `POST /api/conversations/clear` raises ONE `conversation_clear` card (tier `ask`); only
  a person's yes deletes (F6). **It is deliberately not a model tool.**
- **Surface:** backend API (no screen calls it yet — `SELF-AWARENESS.md`: *"has a route but no button
  yet"*) + the approval card in either app.
- **Steps:** pick a **throwaway** conversation id from A4 (there were **30 chats** at 21:57). As the
  owner: `Invoke-RestMethod -Method Post -Uri http://127.0.0.1:4719/api/conversations/clear -Headers $h
  -ContentType 'application/json' -Body '{"id":"<id>"}'`. Then answer the card in the app he is using.
- **What should happen:** `202 {"ok": true, "waiting": true, "id", "title", "messages",
  "action": "conversation_clear", "message": "Waiting for your approval. Nothing is deleted unless …"}`,
  and **one** card whose text is exactly:
  ```
  Delete ONE conversation from this PC?

  "<title>" - N messages.

  It is removed from this PC and this cannot be undone.
  The facts Jarvis learned from it are KEPT - deleting a chat never forgets them. To forget those too, use Forget a time frame.
  Copies in older backups stay until they age out.

  Approve to delete this one conversation. Nothing else is touched.
  ```
  Approve → that chat is gone from A4's list; **the learned facts stay**; no second card appears.
  Deny or let it time out → nothing is deleted and the route can be asked again.
- **How to prove it:** a screenshot of the card (the exact words above), the 202 body, the before/after
  list from A4, and the memory count from A1 unchanged-or-not-decreased.
- **Blocked if:** 409 (a clear card is already waiting — answer it first), 423 (App lock), 503
  (`conversation_clear` is not tier `ask`), 404 for the id.
- **Do not:** ask for "clear all", or try to get the model to call it — `#1116` and Gemini ruling 1
  forbid both; a model tool for this must never exist.
- **Source:** `origin/main:backend/jarvis_self_portrait.py` (`clear_request`, `clear_card_text`),
  `jarvis_card_words.py` (`"conversation_clear": "delete one conversation from this PC"`),
  `jarvis_asks_first.py` (the page row), live toml line 279.

### B6 — "Open <a place>" — **PARTIAL by design** (one half works, one half is not wired)

- **Feature:** named places it can open (F6).
- **Surface:** desktop app / phone app (display only; nothing changes).
- **Steps:** (1) say **"open web search"** or **"take me to reminders"**; (2) say **"open history"**
  and then **"open memory"**.
- **What should happen:** (1) the app jumps to that Settings section — this path has existed since
  September and still works. (2) **It does not jump.** The merged code does not yet turn a menu name
  into a place id: `SELF-AWARENESS.md` says *"the PC's own side that turns 'open history' or 'open
  memory' into a place id is not wired up yet. Until it is, asking for one of those is answered in
  words rather than by jumping."* `resolve_place()` exists (190 places) but **nothing calls it**:
  `git grep resolve_place origin/main -- backend` finds only the definition and
  `test_self_portrait.py`, and `#1116`'s own "Not in this PR" says *"The quick-path fallback that
  consumes `resolve_place()` … is waiting on #1112"*.
- **How to prove it:** (1) a screenshot of the section that opened; (2) the sentence Jarvis answers
  with, and **no** jump. Score (1) PASS and (2) PARTIAL — and write **NOT-TESTABLE-AS-WRITTEN** against
  the brief's phrase "named places it can open", which is not what the merged tree does for menus.
- **Blocked if:** the app in front has no such screen — then it must say so in one plain sentence
  ("Jarvis asked to open X, but the desktop has no X. Nothing was opened."), which is also a PASS of
  the honesty rule.
- **Source:** `origin/main:docs/SELF-AWARENESS.md` ("What is built but not yet connected", "Open <a
  place>"); `jarvis_self_portrait.resolve_place`; `jarvis_quick.py`'s only F6 change is one catalogue
  line (`self-portrait`), not navigation.

### B7 — More than one chat window on the PC — **NOT-TESTABLE tonight**

- **Feature:** "New chat window" / "Open this chat in a new window" (F6's desktop half).
- **Surface:** desktop app HUD + tray.
- **Steps:** none possible.
- **What should happen:** `docs/SELF-AWARENESS.md` describes the two buttons and the tray row as
  available — but that is `#1115`, which is **still open**. `origin/main`'s
  `jarvis-desktop/src-tauri/src/hud_proxy.rs` has an 11-path `HUD_GET_PATHS` and **no `/api/self`**,
  and the merged F6 diff contains no desktop code at all.
- **How to prove it:** the absence is the finding — the installed desktop app does not have the
  buttons. Say NOT-TESTABLE and cite `gh pr view 1115`.
- **Blocked if:** `#1115` merges and a desktop build ships — then this becomes testable and the doc
  becomes true.
- **Source:** `gh pr view 1115`; `origin/main:jarvis-desktop/src-tauri/src/hud_proxy.rs`; the F6 diff
  `git diff --stat 911d6db3e..378ef988a` (no `jarvis-desktop/src` change).

### B8 — The Update button reads both halves back — **NOT-TESTABLE-AS-WRITTEN**

- **Feature:** the Updates card compares the desktop's version with the backend's (F6).
- **Surface:** desktop app → Updates card.
- **Steps:** none that can pass tonight.
- **What should happen in the doc:** "in sync" / "mismatch" / "newer backend" / "cannot be compared".
  **Two things stop it tonight:** the read-back is the desktop half (`#1115`, open), and the live
  backend reports `app_version: "unknown"` because there is no `VERSION` file beside it (A2) — so even
  the shipped comparison could only say "cannot be compared".
- **How to prove it:** A2's `app_version` field, quoted, plus `#1115`'s state. Mark NOT-TESTABLE; do
  not accept "it said cannot be compared" as a PASS of the feature.
- **Blocked if:** a `VERSION` file appears beside `jarvis_hud.py` and `#1115` ships.
- **Source:** `origin/main:backend/jarvis_self_portrait.py` (`version_block`, `_app_version`),
  `#1116` body ("The desktop half is verified only after #1115 ships").

### B9 — An ordinary fact saves with no card — **READY**

- **Feature:** `#1130` Repair A — per-fact attribution; ordinary facts save without a card on their own.
- **Surface:** desktop app chat (the phone works too — C2).
- **Steps:** note A8's counters. Then have a normal exchange where the owner states a plain fact about
  himself in his own words, e.g. **"My workshop fan is a 120 mm Noctua."** Let the turn finish, wait
  ~10 s for the after-pass, then re-read A8 and the memory list.
- **What should happen:** **no approval card**; `saved` rises by one; `last_saved_at` stops being null;
  the fact appears in the memory list. `#1130`'s acceptance sentence: *"DEF-017 stays open until Slice
  2's live proof (`saved` rises, `last_saved_at` set)."*
- **How to prove it:** before/after `learning-stats.json` (or A8's `counters`), the memory-list row,
  and the **absence** of a card in `/api/pending`.
- **If it does not happen:** `saved` staying at 0 **and** `failed` rising is the finding — the live
  learner already shows `"after_pass: OperationalError"` with 8 failures, so quote `last_error` and the
  pass time. Do not call that a test error.
- **Source:** `#1130` head `93966eb7b:backend/jarvis_auto_learn.py` (`_attributed`, `note_pass`).

### B10 — A sensitive fact still waits for a yes (negative control) — **READY**

- **Feature:** `#1130` Repair B — a check that could not RUN is asked again once; a sensitive topic
  still cards.
- **Surface:** desktop app chat + card.
- **Steps:** state a sensitive fact in his own words (health, money, passwords — his choice whether to
  use a real one; a harmless stand-in like "my blood pressure tablets are ..." is enough to trip the
  topic check).
- **What should happen:** **one card** (the sensitive-topic ask), not a silent save. If the check could
  not run, it is retried once after 1.5 s with a 30 s deadline; a clean second answer saves, a second
  failure is still a card. **This row passes when the card appears** — the feature is that it still
  asks.
- **How to prove it:** the card, quoted; `carded` rises by one in A8.
- **Blocked if:** "Also remember sensitive topics automatically" is on — then a save is correct and
  this row is NOT-TESTABLE until it is off.
- **Source:** `#1130` body; `jarvis_auto_learn` (`SENSITIVE_RETRY_BACKOFF = 1.5`,
  `SENSITIVE_RETRY_TIMEOUT = 30.0`).

### B11 — The reworded-card recheck — **READY, observable only by counters (PARTIAL at best)**

- **Feature:** `#1130` ruling Q3 — pending cards whose only reason was "not in your own words" are
  saved once the reworded switch is on, at most five per call.
- **Surface:** desktop app Settings (the switch) + A8.
- **Steps:** note `carded`/`saved`. Turn on **"Save facts even when Jarvis had to reword them"** (its
  ON is ONE `learning_paraphrase_enable` card; OFF is immediate). Let the next learning pass run.
- **What should happen:** up to five of those pending cards become saved facts (marked `meta.reworded`,
  shown with the mark in both apps); `saved` rises, `carded` does not rise. The other two old card
  reasons stay cards — the PR says so: *"the other two old card reasons need the pass's turns, which
  were never stored … so they stay cards, and the docs say so plainly."*
- **How to prove it:** before/after counters **and** the honest limit: the live store's `proposals`
  has no turn column, so a specific card cannot be attributed to this repair from outside. Score
  PARTIAL unless the before/after numbers move cleanly.
- **Blocked if:** there are no pending "not in your own words" cards — then say NOT-TESTABLE, do not
  turn the switch on just to make a number move.
- **Source:** `#1130` head, `recheck_pending_proposals`, `GROUNDED_CARD`; the switch's own text in
  `jarvis_auto_learn`'s header.

### B12 — The Coding preset asks for 32,768 tokens, with 323.5 MiB of spill accepted — **READY**

- **Feature:** `#1129` — the pooled both-card lane's window goes to 32,768 and one capped spill is
  allowed (352 MiB).
- **Surface:** desktop app (Presets) + the PC's own Ollama on port 11450.
- **Steps:** open the Presets menu, read the Coding card, apply it. Answer the card it raises. Wait for
  the cold load (~36 s measured). Then run a real 15-minute coding question.
- **What should happen:** the card's cost words say **32,768 tokens**, *"another 0.3 GB in system RAM
  at this window"*, *"about 36 s on a cold load"*; the load succeeds; `GET
  http://127.0.0.1:11450/api/ps` shows the model with `size - size_vram` ≈ **323.5 MiB** (0.3 GiB),
  never more than 352 MiB; the 15-minute test answers correctly. `#1129`'s cap sentence: *"a load over
  the allowance, or one whose spill the server does not report, is still refused and unloaded with both
  numbers in the `why`."*
- **How to prove it:** a screenshot of the Coding card's cost text; the `/api/ps` numbers (`size`,
  `size_vram`, difference); the cold-load time; the answer to the coding test.
- **Blocked if:** the 2080 Super is driving the monitor and another heavy job holds it; the model is
  not in the local store; the lane refuses the load (then quote the `why` — it names both numbers).
- **Honest limit from the PR, quote it:** *"the window was loaded, not filled — every prompt was 40–43
  tokens, so a genuinely long 32k conversation and the decode speed of a nearly-full window are
  unmeasured. A 15-minute real coding test runs after deployment."* Tonight's 15-minute test is that
  test; it still does not fill the window.
- **Source:** `#1129` head `074459ab8:backend/jarvis_presets.py` (`context=32768`, `spill_gib=0.3`,
  `context_measured=32768`, cost words), `jarvis_model_lanes.py` (`POOLED_CTX = 32768`,
  `POOLED_SPILL_ALLOWANCE = 352 MiB`, `POOLED_SPILL_MEASURED_MIB = 323.5`),
  `docs/MEASURED-2026-11-02-POOLED-LANE.md`'s 2026-11-03 amendment.

### B13 — The four standby-hours rows appear and each change asks — **CONDITIONAL on #1126**

- **Feature:** `#1126` — Settings > Limits gains four rows, and changing any raises one
  `change_own_config` card.
- **Surface:** desktop app Settings > Limits (the phone draws the same four rows; no client change).
- **Steps:** open Settings > Limits; find the four rows; read them; then change **"My hours start"** to
  a time two minutes from now and answer the card.
- **What should happen:** the four rows read **"Keep Jarvis quiet during my hours"** (off), **"Unload
  the graphics cards during my hours"** (off), **"My hours start"** 23:00, **"My hours end"** 07:00;
  changing any one raises ONE `change_own_config` card in either direction, and setting a value to
  what it already is raises **no** card.
- **How to prove it:** a screenshot of the four rows; the card; the live toml's `[power]` before/after.
- **Blocked if:** `#1126` is not merged and deployed — **at 21:50 it is red and CONFLICTING**, and its
  own suite fails on the hour-dependent line `test_standby_hours.py`: `eq("outside the window the mode
  is active", P.current(), "active")` (151 passed, 1 failed on CI). `P.current()` reads the **real
  clock**, so the test passes or fails depending on what time it runs — the "hour-independent test" the
  brief expects is **not in the PR head**. If it merges without that fix, this row is
  **NOT-TESTABLE-AS-WRITTEN** and the test is the finding.
- **Source:** `#1126` head `8c9afb2c3:backend/jarvis_limits.py` (`_STANDBY_ROWS`, `always_asks`),
  `backend/test_standby_hours.py`, `jarvis_power.py`.

### B14 — The GPUs actually unload at the edge, and the next question wakes them — **CONDITIONAL on #1126 (and needs 30+ minutes)**

- **Feature:** `#1126` — the hours free the cards; the next question loads the model again.
- **Surface:** the PC (nvidia-smi / Ollama) + chat.
- **Steps:** set "My hours start" to two minutes ahead and "Unload the graphics cards during my hours"
  ON (both cards answered). At the edge, watch `nvidia-smi` and `GET http://127.0.0.1:11436/api/ps`
  until the model is gone. Then ask Jarvis a question inside the window and time the answer.
- **What should happen:** the model is unloaded at the edge (within 30 s, not on the minute); the next
  question is **5–15 s slower** (the PR's own figure, not re-measured); nothing is unloaded while a
  turn is running, Live is on, a card waits, or a task runs — the code records why it held off.
- **How to prove it:** `nvidia-smi` before/after, `/api/ps` empty, the answer's latency, and the `why`
  line if it held off.
- **Blocked if:** `#1126` is not merged; or a card is waiting (the unload is refused — which is itself
  a PASS of the in-flight guard, say which you saw).
- **Source:** `#1126` body; `backend/rebuilt/jarvis_power.py` (`enforce`, the keeper),
  `jarvis_power_switch.set_mode("standby")`.

### B15 — GitHub: read, three actions, never merge or push — **CONDITIONAL on #1128**

- **Feature:** `#1128` — six tools, each behind one card, tier `ask`; never merge, push, commit, delete
  or close.
- **Surface:** desktop app chat + cards (no screen in either app).
- **Steps:** (1) make sure a token exists — the *existing* "connect GitHub" fast path, which stores it
  in Windows Credential Manager; (2) add the six tool names to `[tools].enabled` (A7); (3) ask
  **"List my repositories"**; answer the card; (4) ask **"Comment on issue N: <text>"**; answer the
  card; (5) ask **"Merge pull request N"** and **"Push this commit"**.
- **What should happen:** (3) ONE `github_inspect` card, then the repo list (fixed endpoints only);
  (4) ONE `github_comment` card showing **the whole text**, then the comment; (5) one plain sentence
  naming what it cannot do and why — **no tool, no card, no action**. `#1128`: *"No merge, no push, no
  commit, no delete, no close, no file write. There is no planner, no endpoint and no tool for any of
  them, and the absence is the control."*
- **How to prove it:** each card (the read card included — *"The reads ask too"*), the answers, and
  the refusal sentence for (5). The token must appear in no card, no address and no result.
- **Blocked if:** `#1128` is not merged (**red and CONFLICTING at 21:50**), no token saved, or the
  tools are off (they ship off, like `github_search`).
- **Source:** `#1128` head `72f684738:backend/jarvis_github.py`, `jarvis_agent.GITHUB_READ_TOOLS` /
  `GITHUB_ACTION_TOOLS`; `docs/JARVIS-API.md` §184.

**Group B: 16 rows.**

---

## 5. Group C — needs the phone physically present

### C1 — Install tonight's APK and prove which build it is — **READY**

- **Feature:** the Android update itself.
- **Surface:** phone app.
- **Steps:** on the PC, download `jarvis-client-378ef98.apk` from the rolling `client-latest` release
  (asset created 2026-11-04T05:36:42Z, `sha256:8576dee8…`, 34,846,878 bytes). Then
  `adb install -r <path>`, open Jarvis, and read the version in the app's About/Settings.
- **What should happen:** the install succeeds over the existing app (same `applicationId
  com.jarvis.client`), and the app shows **0.2.3686** (`main @ 378ef98`). The pairing survives an
  in-place update.
- **How to prove it:** the About screen's version string, and `adb shell dumpsys package
  com.jarvis.client | Select-String versionName` on the PC.
- **Blocked if:** `INSTALL_FAILED_UPDATE_INCOMPATIBLE` (a different signing key) — then an uninstall is
  needed, which **drops the pairing**; re-pairing is a separate, carded step. Also blocked with no
  cable/adb or no Wi-Fi debugging.
- **Important:** this APK is built from `378ef98`, which contains **no phone code change** tonight
  (F6 is backend-only; `#1125`'s Kotlin is not merged). So C1 proves the update path, not a new phone
  feature.
- **Source:** `gh release view client-latest`; `jarvis-client/app/build.gradle.kts`
  (`applicationId`, the versionCode scheme).

### C2 — A fact saved from the phone, with no card — **READY**

- **Feature:** `#1130` on the phone's surface (same backend, same learner).
- **Surface:** phone app chat.
- **Steps:** same as B9, typed or dictated on the phone: state a plain fact about himself. Wait, then
  re-read A8 from the PC.
- **What should happen:** no card on either device; `saved` rises; the fact appears in the phone's
  memory list.
- **How to prove it:** the phone's memory list row + A8's counters before/after.
- **Blocked if:** the phone cannot reach the PC (Tailscale/NordVPN Meshnet down), or the phone holds a
  retired key (`{"key": "device_removed"}`).
- **Source:** as B9.

### C3 — The phone's History delete stays cardless (negative control) — **READY**

- **Feature:** the unchanged History screen, and the proof that **no phone screen calls the new clear
  route**.
- **Surface:** phone app → History.
- **Steps:** delete one throwaway chat with the History screen's own "are you sure?".
- **What should happen:** it deletes after that question, **with no card from the PC** — because no
  screen calls `POST /api/conversations/clear` yet (`git grep conversations/clear origin/main -- backend jarvis-desktop jarvis-client`
  finds no caller in either app). This is a PASS *of the unchanged path*, and it is the evidence for
  B5's "route only".
- **How to prove it:** the phone's confirmation dialog and the absence of a PC card.
- **Blocked if:** a card *does* appear — then some screen does call the route and B5's premise is
  wrong; report it.
- **Source:** `git grep` above; `docs/SELF-AWARENESS.md` ("What you can do today").

### C4 — The voice-check switch, and Live on an unlocked phone — **CONDITIONAL on #1125**

- **Feature:** `#1125` — "Only check my voice on a locked phone"; Live started on an explicitly
  unlocked phone runs no voice-print check.
- **Surface:** phone app → Settings → Voice; then Live.
- **Steps:** (1) open Settings → Voice and read the switch — it shows the **PC's** answer, never "off"
  when the PC has not answered. (2) Tap it OFF — that is immediate, no card. (3) Tap it ON — that is
  the looser direction and raises **ONE `change_own_config` card**; approve it. (4) Unlock the phone,
  start Live, speak one ordinary sentence. (5) Lock the phone, say **"hi Jarvis"**.
- **What should happen:** (3) nothing changes until the card is approved; a denied card changes
  nothing; (4) **no voice check** — the session is `trusted` with no speaker model run; (5) the phone
  **still checks** — and the app says so itself: *"Saying 'hi Jarvis' on an unlocked phone is still
  checked for now - a later PC update stops that."* (DEF-033; the wake half is not wired yet.)
- **How to prove it:** a screenshot of the switch in both states, the card, and the presence/absence of
  a "is that you?" step in (4) and (5).
- **Blocked if:** `#1125` is not merged (**red at 21:50**: `backend` and `audit` fail, the red suites
  being `test_ask_to_change.py` — its *"…and every other switch (32) IS in the list"* line FAILED —
  and `test_claims.py`), no new APK (the switch is drawn by `VoiceSwitchesPlate.kt`, which needs C1's
  build **and** `#1125` in it), or the PC's answer is unknown (the plate offers nothing to press —
  that is the guard working).
- **Source:** `#1125` head `6490e53c9:backend/jarvis_live.py` (`voice_check_needed`),
  `jarvis_settings_registry.py` (`voice_check_locked`), `VoiceSwitchesPlate.kt`, `VoiceCheckRule.kt`.

### C5 — Clearing a conversation from the phone — **NOT-TESTABLE tonight**

- **Feature:** the one-card clear on the phone.
- **Surface:** phone app.
- **Steps:** none. There is no button anywhere that calls the route (`C3`), and adding one is not in
  tonight's set.
- **How to prove it:** the absence, with C3's grep and `SELF-AWARENESS.md`'s sentence.
- **Blocked if:** n/a — this is a "not built yet", not a failure.

**Group C: 5 rows.**

---

## 6. Known risks tonight

1. **Approval-card patience.** Every card waits 900 s by default (`[autonomy].approval_timeout_seconds`)
   and a card that times out is **refused**, not approved. The card rows are B5, B10, B11, B12, B13,
   B15 and C4 — do them **one at a time**, and never leave a second card stacking: `clear_request`
   answers 409 while one is waiting, and the pooled lane's start is refused while one waits too.
   (B9 and C2 must raise **no** card; a card there is a finding, not a step.)
2. **The owner's live `jarvis-framework.toml` must never be overwritten.** Measured at **21:52, after
   both deploys** (F6-A and the increment): it still holds his ten-name `[tools].enabled` list, and
   `conversation_clear`/`storage_cleanup` are both `ask`. If any deploy ever leaves the shipped
   nine-name list there, **stop** and restore from his own backup. The rows B1–B4 and B15 depend on
   edits **he** makes, not the deploy (B0).
3. **The restart that matters is the backend, not the desktop.** Tonight's merged set has no Rust
   change; `#1115` (the desktop half: `HUD_GET_PATHS`, the extra chat windows) is still open. Prove the
   backend restart with Gate 0.3 (`started_at` later than the newest module mtime): the increment's
   files landed 21:48:43, the state resealed 21:51:37, and the process started **21:51:47** — so the
   restart is proven as this page closes. Mid-deploy (21:47–21:49) the backend was **down**; that was
   the deploy, not a fault.
4. **The APK install replaces the sideloaded app in place.** Same `applicationId`, so data and the
   pairing survive a normal `-r` update. A signature mismatch forces an uninstall (pairing lost). And
   the published APK is built from `378ef98`, so tonight it carries **no new phone feature** — `#1125`
   is what would add one, and it is red.
5. **Quiet hours can silence the PC's notifications — and there are two different quiet hours.** The
   `[power]` hours B13/B14 touch stop Jarvis *speaking* and (with the switch on) unload the model; the
   **notification** quiet hours are a separate feature (`"Be quiet during quiet hours (on your PC)"`,
   default 22:00–07:00, `jarvis_limits._notify_rows`). `#1126` says plainly it does **not** wire the
   two together. Turn the notification quiet hours off (or move them) for the test, and do not read a
   silent PC as a broken feature.
6. **Anything that needs the second GPU lane.** The Coding preset (`#1129`) takes **both** cards as one
   pooled lane on port 11450, and accepts 323.5 MiB of spill (cap 352 MiB); `#1126` unloads every
   model, the pooled lane included. Do not run B12 while another heavy job holds the 2080 Super (it
   also drives the monitor), and expect the first answer after a standby window to be 5–15 s slower.
7. **The deploy's own record says "partial".** `_jarvis-state.json` says `run: "partial"` with two
   patches left out (`embedding-guard.patch`, `event-allowlist.patch`), `files_recorded: 232`,
   `files_verified: 3`. `resealed.commit` proves the reseal and the file bytes, **not** that every
   merged patch applied. Record it; do not silently treat "deployed" as "complete".
8. **App lock / "Hide memory lists and chat history".** With either on, the clear route answers **423**,
   the portrait withholds store counts, and the conversation aliases answer 423. That is the guard
   working. Run the rows with the PC unlocked and say which state you ran in.
9. **The memory learner has a history of failing, and that is the thing B9 is watching.** At 21:52 its
   own record read `failed: 8`, `last_error: "after_pass: OperationalError"`, `last_pass_at`
   2026-11-02 16:33 and `facts_total: 1`. The first learning pass on the new code is tonight's real
   test: `#1130`'s repairs can be right and the pass can still raise. If `failed` rises and `saved`
   stays 0, DEF-017 stays open — quote `last_error` and the time; do not mark the memory feature PASS
   on the strength of the unit suites.

---

## 7. What I could not determine (and why)

- **Whether `#1125`, `#1126`, `#1128` merge tonight.** At 21:50 PT all three are red; `#1126` and
  `#1128` are also `CONFLICTING`. Their fix lanes are outside this deliverable, and the brief's
  "green and about to merge" is contradicted by the checks. All three groups of rows are written as
  CONDITIONAL for that reason.
- **Whether the phone is present, paired and reachable.** No phone was touched; the runbook says what
  to do when it is in hand. Tailscale/Meshnet state is not observable from here.
- **Whether the APK is signed with the same key as the installed app.** That depends on CI secrets I
  cannot read; `adb install -r` is the test, and the failure mode is named in risk 4.
- **The real pooled-lane spill tonight.** It needs the Coding preset applied and the model loaded; the
  PR measured 323.5 MiB at 32,768. The `/api/ps` read in B12 is the proof, and it has to be run.
- **What the live 6 carded facts' reasons are.** `#1130` itself says the store never kept the turns
  (`proposals` has no turn column), so the reworded recheck (B11) can only be seen through counters,
  not attributed per card.
- **Whether `GET /api/memory/learning` is served on the increment build — answered yes at 21:52** (it
  returned 200 with `counters`); I could not read it before the restart because the backend was down.
- **Why `app_version` is `"unknown"`.** The body says "no VERSION file beside the backend"; whether the
  installer is supposed to write one is a deploy question for the partner session, not something I
  could settle read-only.
- **Whether the four F6 chat tools are wanted on at all.** That is the owner's decision (B0); the
  runbook gives both options and the exact edit.

---

## 8. Source index — where to look when a step fails

| Feature | Files that implement it | Tree read |
|---|---|---|
| Self portrait API + refresh + version | `backend/jarvis_self_portrait.py`; `plugins/ready/self-portrait/plugin.json`; live `jarvis_plugins\self-portrait` | `origin/main` `9cf55df68` (F6 merge `378ef988a`) |
| The four chat tools | `backend/jarvis_agent.py` (`SELF_READ_TOOLS`, `_self_portrait_tool_text`, `_run_*`, `REFRESH_ABILITIES_TOOL`), `jarvis_card_words.py`, `jarvis_reach.py`, `jarvis_claims.py` | same |
| One-card clear | `backend/jarvis_self_portrait.py` (`clear_request`, `clear_card_text`, `_decide`), live `jarvis-framework.toml:279` | same |
| Conversation aliases | `backend/jarvis_self_portrait.py` (`conversation_list`, `conversation_get`) | same |
| Places / navigation | `backend/jarvis_self_portrait.py` (`places`, `resolve_place`), `backend/jarvis_quick.py` (catalogue line only), `docs/SELF-AWARENESS.md` | same |
| Desktop half (not deployed) | `jarvis-desktop/src-tauri/src/hud_proxy.rs` (`HUD_GET_PATHS`), `#1115` | `origin/main` (11 paths) + `gh pr view 1115` |
| Coding preset 32,768 | `backend/jarvis_presets.py`, `backend/jarvis_model_lanes.py`, `backend/jarvis_big_coder.py`, `docs/MEASURED-2026-11-02-POOLED-LANE.md`, `docs/MODEL-TOPOLOGY.md` | `#1129` `074459ab8` / `origin/main` |
| Memory learning repairs | `backend/jarvis_auto_learn.py` (`_attributed`, `recheck_pending_proposals`, `learning_status`, `note_pass`), `%USERPROFILE%\.openjarvis\learning-stats.json` | `#1130` `93966eb7b` |
| Standby hours (conditional) | `backend/jarvis_limits.py` (`_STANDBY_ROWS`), `backend/rebuilt/jarvis_power.py`, `backend/jarvis_power_switch.py`, `backend/test_standby_hours.py` | `#1126` `8c9afb2c3` |
| Voice check (conditional) | `backend/jarvis_live.py` (`voice_check_needed`, `request_voice_check`), `backend/jarvis_settings_registry.py`, `jarvis-client/.../VoiceSwitchesPlate.kt`, `.../voice/VoiceCheckRule.kt` | `#1125` `6490e53c9` |
| GitHub tools (conditional) | `backend/jarvis_github.py`, `backend/jarvis_agent.py` (`GITHUB_READ_TOOLS`, `GITHUB_ACTION_TOOLS`), `backend/github-tools.patch` | `#1128` `72f684738` |
| The deployed record | `_jarvis-state.json` beside `jarvis_hud.py`; `GET /api/self/version` | live install, 21:52 |

---

### Result sheet (fill in tonight — one line per row, never a PASS from code)

| Row | Result | What proved it | Time |
|---|---|---|---|
| A1 … A9 | | | |
| B0 … B15 | | | |
| C1 … C5 | | | |
