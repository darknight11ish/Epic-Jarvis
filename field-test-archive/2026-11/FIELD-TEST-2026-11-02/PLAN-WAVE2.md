# FIELD TEST WAVE 2 — plan (2026-11-02, after the wave-2 deploy)

Same rules as wave 1 (`.dsh-scratch/FIELD-TEST-2026-11-02/RESULTS.md`): results only;
PASS means the feature was actually driven on this hardware after the deploy;
BLOCKED / NOT-TESTABLE / PARTIAL are never passes; no approval is ever made;
a setting flipped for a test is put back; the token is never printed; phone rows
come from `adb shell uiautomator dump` XML (screenshots are black under
FLAG_SECURE); desktop rows may be API-level or NOT-TESTABLE with the reason.

## Tier 1 — health (before any feature row)

| # | Check | How |
|---|---|---|
| T1.1 | `/api/version` 200, `api=1`, `started` after the deploy restart | authenticated GET |
| T1.2 | `/api/status` 200, `ollama=true`, model/lanes as before | authenticated GET |
| T1.3 | live `jarvis_gate.py` sha == the wave-2 expected sha (197478 bytes) | Get-FileHash |
| T1.4 | live `jarvis_hud.py` / `jarvis_skills.py` shas == expected | Get-FileHash |
| T1.5 | phone install: `versionName`/`versionCode` moved, `firstInstallTime` unchanged, no FATAL | adb dumpsys + logcat |
| T1.6 | desktop version installed and running | FileVersion + Get-Process |
| T1.7 | verifier verdict, and its phone-vs-release cell (UNVERIFIED is never PASS) | `verify-run/report.md` |
| T1.8 | `/api/pending` waiting = 0 at the end | authenticated GET |

## Tier 2 — the features this wave carries

| # | Feature (PR) | How to drive it | honest ceiling |
|---|---|---|---|
| 1 | Quick phone mic message skips the voice-ID check (#1099) | press the phone mic, hold ~1 s, release; read the chat text and the history row; a 0.3 s clip must NOT produce the "that was too short to be sure it was you" line, and `mode` in the voice verdict must be `quick_message` | real speech needs a human; a silent/short clip only proves the gate is skipped. If no audio reaches the backend, NOT-TESTABLE with the read line |
| 2 | Chat panel opens on the newest message (#1098) | uiautomator: from the face, open the chat (Show chat) and again after Back to full screen; the first visible chat row must be the newest message, not the thread's first | PASS only if the row is visibly the newest one in both paths |
| 3 | Skills menu on the PC (#1092) | API: `GET /api/skills/list`, a scan of a temp folder, a Hermes scan, an off/on attempt; each write must raise exactly ONE card and write nothing until denied; then `GET /api/skills/list` unchanged | the desktop Settings card (`settings.html#skills-menu`) is a Tauri window this lane cannot click: UI presence via installed app files only → the row is PARTIAL even when the API half passes |
| 4 | To-do carry-over switch (#1093) | phone: Settings → Limits → the carry-over row; read the current mode, flip to the other one, read `/api/schedule` (or the mode endpoint) to see the real value move, flip back | desktop Settings card not driven (same shared value) → note it |
| 5 | Memory paraphrase switch (#1096) | phone: Settings → the "Save facts even when Jarvis had to reword them" row; turning ON raises ONE card → deny it and re-read the switch OFF; the phrase "turn on facts in your own words" via chat resolves to that one card | deny only; approve path is owner-only |
| 6 | Approval notification actions (#1091) | raise one read-only card (an ordinary web search from the phone chat), then expand the notification shade (`adb shell cmd statusbar expand-notifications`, uiautomator dump) and check the notification carries Deny / Review (and Approve gated by unlock); press **Deny** from the notification and prove `/api/pending` waiting=0 + the history row denied | approve-from-notification is owner-only (needs unlock) → NOT-TESTABLE for the approve half |
| 7 | Phone app allow-list (#1097) | API/phone Settings: `GET /api/phone/apps` (read-only list); an add attempt must raise exactly ONE `change_own_config` card naming the app and package → deny; list unchanged | approving the add is owner-only |
| 8 | Web-search grant card reachable (#1100) | phone chat: "Give me full approval to search the web for this conversation." → exactly ONE `grant_web_search_conversation` card (uiautomator + `/api/pending`), deny it; then a search must still raise its own `search_the_web` card. The model's answer must not claim a grant that is not in the store | the grant-after-approve path is owner-only; the row's pass is "one card, honest answer" |
| 9 | Obsidian note editing from the phone (already on main) | phone: Mind → Notes; open today's note and read it; a save raises ONE `edit_vault_note` card → deny; the note on disk is unchanged | read half can PASS; the save half is card-then-deny |
| 10 | Settings search finds the new rows | phone Settings search: `skills` (expected: desktop-only refusal naming the PC), `carry-over`, `reworded`/`own words`, `apps on my phone`; read the "found/refused" text | phone-only |

## Tier 3 — safety and cleanliness

| # | Check |
|---|---|
| S1 | `/api/pending` waiting = 0 at the end; every card this session was denied, none approved |
| S2 | `decided_by` on every decision names `field-test-2026-11-02`; no approve call was made |
| S3 | token never printed or written; only read inside the helper |
| S4 | every setting flipped is restored and re-read |
| S5 | no install/update/restart happened inside the field test (that belongs to Stage B/D/H) |

End: one PASS/FAIL/PARTIAL/BLOCKED/NOT-TESTABLE table in
`.dsh-scratch/FIELD-TEST-2026-11-02/RESULTS-WAVE2.md`, plus the one-line counts.
