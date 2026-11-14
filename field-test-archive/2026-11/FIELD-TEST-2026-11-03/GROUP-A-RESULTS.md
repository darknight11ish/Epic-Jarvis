# Field test — Group A results (automatable rows), 2026-11-03 21:55–22:00 PT

Live install: `C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program`.
Backend PID **56520**, started **21:51:47**, listeners 2 (127.0.0.1 + 100.75.21.228), `GET /` -> 401.
Deployed ref proven: `/api/self/version` -> `resealed.ref = commit = 9cf55df68…` (F7).
Gate 0.3: process start 21:51:47 is later than the newest increment module mtime (21:48:43) -> the running process loaded the new bytes.
The four increment modules are byte-identical to `9cf55df68:backend/<file>` (git hash-object, all MATCH).
Owner's live `jarvis-framework.toml`: ten-name `[tools].enabled` list intact; `conversation_clear = "ask"`, `storage_cleanup = "ask"`.
Token length 43, never printed. Raw transcript: `group-a-raw.txt` (same folder).

| Row | Result | What proved it | Time |
|---|---|---|---|
| A1 — self portrait API | **PASS** | `GET /api/self` 200, `schema: jarvis-self-portrait/1`, counts **190 places / 46 settings / 175 abilities / 23 plugins / 3 stores**, `private.locked: false`. | 21:55:52 |
| A2 — deploy identity | **PASS** | `deploy.recorded: true`, `resealed.ref = 9cf55df68…` (the deployed F7 ref), `run: "partial"`, `files_recorded: 232`, `files_verified: 3`, `app_version: "unknown"`, `app_version_source: "no VERSION file beside the backend"`. | 21:55:52 |
| A3 — refresh re-reads inventory | **PASS** | `POST /api/self/refresh` -> 200, `ok: true`, `changed: {}`, sentence: *"I re-read what I can do and have now: 190 places, 46 settings, 136 ask-first actions, 23 plugins and 175 abilities. Everything matches what I had. Nothing was restarted."* Same process: PID stayed 56520 and `/api/self/version.started_at` stayed 21:51:47. **Runbook correction:** the refresh response has no `started_at` field (the runbook assumed it does), so the no-restart proof is PID + version.started_at, not the refresh body. Observed 136 ask-first actions where the runbook predicted 135 — record 136. | 21:58:10 |
| A4 — conversation list alias | **PASS** | `GET /api/conversations` 200; `enabled: true`, `recording: true`, `keep_days: 0`, `encrypted: true`, **30 conversations**; first ids `df84ae1a-166f-4802-bb73-c19a52906b26`, `untagged-unknown-20261103`, `6f93f8f2-a893-4688-95bc-0dd070c03649`. | 21:55:52 |
| A5 — opening one kept chat | **PASS** | `GET /api/conversations/df84ae1a-…` 200: 31-char title, **12 turns**, top-level fields `id,title,history,tainted,turns,kind,project,tag_id,pinned,pinned_at,archived,started,updated,continuable,continue_why,forkable,fork_why,marks,markable,mark_why`; turn fields `idx,role,text,at,provenance,read_outside,answer_kept`. | 21:55:52 |
| A6 — one-card clear guard rails | **PASS** | `GET /api/pending` -> `pending: []` before and after. Three probes, no card raised: body `{}` -> 400 *"Send exactly {\"id\": \"<conversation id>\"} - one conversation per request. There is no bulk clear."*; `{"id":"bad id with spaces"}` -> 400 *"That is not a conversation id."*; `{"id":"not-a-real-id-000"}` -> 404 *"no such conversation - it may already have been deleted"*. (History shows an earlier `conversation_clear` card that **expired**; expired = refused, nothing deleted.) | 21:55:52 |
| A7 — tools gate (owner's file) | **PASS (gate only)** | Owner's enabled list is exactly the ten names `calculator, change_setting, memory_search, web_search, feature_guide, my_files, calendar_read, email_check, home_read, notes_search`. None of `self_portrait, conversation_find, conversation_open, refresh_abilities` (nor the six GitHub tools) is present **anywhere** in the toml. So B1–B4 are BLOCKED unless the owner chooses B0; B15 is conditional on #1128 anyway. | 21:55:52 |
| A8 — learner counters baseline | **PASS (baseline)** | `counters`: `passes 5, saved 0, carded 6, failed 8, last_pass_at 2026-11-02 16:33 PT, last_error "after_pass: OperationalError", last_saved_at null, sensitive_unchecked 0`; `facts_total 1`; module note *"5 learning pass(es) have run and saved nothing yet; 6 fact(s) are waiting on cards. The last pass failed (after_pass: OperationalError)."* This is the before-number for B9/B10/B11. | 21:55:52 |
| A9 — preconditions snapshot | **PASS** | `[power]`: `enabled = true`, `schedule_mode = "quiet"`, `idle_mode = "quiet"`, `schedule_enabled = false`, `quiet_start = "23:00"`, `quiet_end = "07:00"`, `idle_enabled = false`, `idle_minutes = 45`. `/api/status`: routing true, jarvis false, ollama true, proxy false, `tools: 28`, `default_model: "qwen3.5:9b"`. `/api/models`: 1 model, current `qwen3.5:9b`. `private.locked: false`. | 21:55:52 |

## Group A tally: 9 of 9 PASS (2 of them prove a gate/baseline, not a feature — A7, A8)

## Not yet attempted

- Group B (16 rows) — needs the owner at the keyboard; B0 decision pending.
- Group C (5 rows) — needs the phone in hand; C1 already done by the Lead before this run (APK 0.2.3686 installed at 21:41:29, sha256 8576dee8… matches client-latest), so C1 is PASS pending the owner reading the About screen.
