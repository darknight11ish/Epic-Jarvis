# Report 41 (audit), agent a031a5c2, 2026-09-30T07:07Z

> **What it was asked** (first 600 characters of the task): Read-only audit of /home/user/Epic-Jarvis (read CLAUDE.md first, esp. the backup decision 2026-09-27 (locked backup file, recovery code shown once, keeps last few, bends rule 1 for that one file), Forget / Erase the words / Forget a time frame / auto-delete / chat history / Temporary chat, the crisis rules 'never learned/counted/kept'; verify each claim with file:line + quote; 'not checked' honestly; change no files). AREA: BACKUP, RESTORE and DELETION COMPLETENESS. Audit: (1) backend/jarvis_backup.py + its routes/apps UI: what exactly goes in the backup (chat history, memory facts, settings, 

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

AUDIT: BACKUP, RESTORE, DELETION (read-only; no files changed)

RAN: nothing useful. pytest is missing here and `python3 test_backup.py` dies on a broken `cryptography` install (pyo3 panic). Everything below is read from source, not run.
NOT CHECKED: `jarvis_memory.py` (the owner's own file, not in the repo, so the real erase code); Windows Credential Manager behaviour; real Windows restore; the Kotlin phone code beyond greps.

PART 1: BACKUP

Sound, verified:
- Cipher and key: AES-256-GCM with a key from Argon2id (64 MiB, 3 iterations, 4 lanes). Fresh random 16-byte salt and 12-byte nonce per file (jarvis_backup.py:374-384). The header is authenticated (AAD).
- Recovery code: 20 characters from 32 symbols, about 100 bits (l.347). Never written to disk. The restore code path reads it once (take_restore_result).
- Wrong code and bad files: a wrong code gives a plain error, and a wrong-shape file gives WrongCode (l.387-410). A zip that is corrupt but decrypts is caught as BadZipFile (l.868).
- Write safety: the file is written to a temp name, then os.replace (l.627-629).
- Restore paths: archive names are checked by `_inside` (l.956).
- Tokens and keys: the pairing token is a file named `token` (token-file.patch), which the `*.json` glob never matches. devices/registry.json is in a subfolder, so it is also left out. Rule 3 holds.
- The chat-history key IS in the backup (`secrets/chat-history-key.b64`, l.538). This is deliberate: a restore onto another PC needs it. It is protected only by the recovery code, so a synced NordLocker or OneDrive copy is only as safe as that code.

Findings, worst first:
1. **Retention deletes real backups when the clock is wrong (confirmed).** `list_backups` sorts by NAME (l.594) and `_retain` keeps `rows[:5]` (l.598-604). There is no "newest real backup" safeguard.
   - A bogus future-named file, for example `jarvis-backup-20991231-000000.jbak` from a wrong clock, sorts first. Five such files push every real backup out.
   - Worse: if the PC clock runs behind, the backup just written can rank below five older files, and `_retain` deletes it right after showing the owner its one-time code.
   - Smallest fix: never delete the file just written, and take the newest by file mtime when a name is later than "now".
2. **A restore replaces whole database files, but the card says "never deletes anything you have added since".** The card text is at l.911-913, the file swap at `_apply_restore` l.1021-1024. Facts and chats added after the backup are lost from the live data. They survive only in the safety backup.
   - Smallest fix: change the wording to "replaces your memory and chat files with that day's copies".
3. **Restore can leave the data in a mixed state, and the failed message misleads.**
   - The files are swapped one by one with no rollback. On Windows, `os.replace` over an SQLite file the running backend has open can raise PermissionError partway.
   - The "failed" message says "your data was not changed" (l.897), which can be false after a partial apply.
   - No WAL handling: nothing deletes a stale `memory.db-wal` or `-shm` sitting beside the restored file. I did not verify that the databases use WAL mode.
   - The docs say to restart Jarvis afterwards, but nothing stops the backend before the swap.
   - The chat-history key write failure is swallowed (l.1016, `except: pass`), which would leave the restored chat history unreadable with no warning.
4. **Backups are manual only.** The desktop text says so ("only when you press Back up now"), and no scheduler use exists in the module. The owner's "one scheduler" rule is not violated. But there is no failure or success notification beyond the panel, and no "last backup is old" nudge. The phone shows "Last backup: 3 days ago".
5. **Folder problems are only lightly handled.**
   - A removed drive or full disk gives an OSError and a "could not write" message (l.810).
   - `tmp.write_bytes` failures leave a `.tmp` file behind (l.627-628).
   - Nothing is tested for spaces in the path, a network drive, or a disappeared drive.
6. **Old and new versions:** the format is JBAK1 and reads its own Argon2 settings from the header, which is good. There is no app-version field and no check that a newer backup's table shapes match the current app. A restore of an older backup over a newer schema was not checked.
7. **Test coverage:** test_backup.py has about 13 checks. I found no tests for a future-named file, a truncated file, a stale WAL, a partial-apply failure, or a full disk.
8. **The "erased facts stay in older backups" limit is said at the point of use, but not on the phone.** It is on the restore card (`ERASE_LIMIT`, l.918) and shown in the desktop backup panel (`backup-settings.js:218`). The phone only shows the last-backup time, which fits its design.

Not built and worth naming: no "verify this backup opens" button, and no "restore onto a different PC" walkthrough. The key goes into Credential Manager (l.1013), so it would work, but it is untested.

PART 2: BOTH APPS
Backups are PC-only on purpose, written up in ARCHITECTURE §8 (l.1994). The phone's read-only "last backup" line is `ported`. I did not run check_parity.py.

PART 3: FIT
The gates match the design: restore is `restore_backup`, tier ask, PC-only with Windows Hello, and the folder card reuses `change_own_config`. The wording is consistent, apart from finding 2.

DELETION TABLE (severity order)

| Data | Where stored | Removed by | Still present? |
|---|---|---|---|
| Erased fact's words | memory.db, plus backups | Erase the words wipes text, FTS entry, vector and copies in the file and WAL (per test_memory_erase.py) | **YES, in any backup from before the erase, for up to 5 backups. Restore can bring it back.** Disclosed on the card. |
| Deleted chat, and chats removed by Forget a time frame | chat-history.db (secure_delete on, VACUUM hourly at most, l.84 and 757) | Delete chat, auto-delete, forget range after 10 minutes | **YES in older backups.** Also in RAM for the 10-minute undo window, then dropped (`_purge`, forget_range l.572). |
| Chat history key | Credential Manager, and inside every backup | nothing | YES, by design. |
| Forgotten fact (not erased) | memory.db | Forget retires it and keeps its text as history | YES by design. A restore keeps it retired. Only Erase removes the words. |
| Backups themselves | backup folder, possibly cloud-synced | 5-file rotation only | YES. Cloud sync copies are outside Jarvis's reach. |
| Temporary chat, crisis chat | Not verified in code. temporary-chat.patch and `CRISIS_TITLE` (chat_log l.196) exist. | | Not checked whether a crisis turn's words reach memory.db or the backup. |
| Phone captured notifications | prefs (CapturedNotifications.kt `clear()` and `removeApp` exist) | switch off / clear | Not verified that turning the switch off calls clear(). |
| Phone models cache | ModelsCacheStore | none stored beyond model names | fine, it holds no personal text |
| Exported support chats | plain file, named exception | owner | YES by design |
| Embeddings, entity layer, re-ranker caches, learner queues, logs, crash notes, prompt caches | not traced | | NOT CHECKED. `jarvis_entities.py`, `jarvis_tidy.py` and `jarvis_auto_learn.py` skip erased rows, which is a good sign. |

OWNER'S CALLS
A. Retention guard (finding 1).
- (recommended) Always keep the newest by real file time, and never delete the file just written.
- Leave it, and warn if the clock is off.

B. Erased words in old backups.
- (recommended) Keep the current disclosure, and add a "delete older backups now" button after an Erase.
- Have Erase also drop every backup made before it, which is drastic.

C. Restore safety.
- (recommended) Stop the backend before the swap, and roll back on failure.
- Keep the current approach, and reword the card and the failed message.

I did not change any files.
