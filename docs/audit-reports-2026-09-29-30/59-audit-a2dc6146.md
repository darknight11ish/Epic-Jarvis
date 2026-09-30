# Report 59 (audit), agent a2dc6146, 2026-09-30T08:48Z

> **What it was asked** (first 600 characters of the task): Read-only audit of /home/user/Epic-Jarvis (read CLAUDE.md first; beginner owner, plain words; verify each claim with file:line + quote; 'not checked' honestly; change no files). The owner asks: 'Does the memory and storage of Jarvis need a review? Can it be efficiently managed currently? Can it compress anything automatically to save space?' YOUR PART = DISK STORAGE on the owner's PC and phone. Inventory EVERYTHING Jarvis keeps on disk and its growth: (a) PC backend data folder (%USERPROFILE%\.openjarvis and the backend folder): memory.db (+ -wal/-shm), chat-history.db (encrypted), schedule.db

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

DISK STORAGE AUDIT (read-only; no files changed). Ran: repo size commands, greps, reading code. NOT measurable here: everything on the owner's PC and phone (no real .openjarvis, Ollama store, or APK data). Sizes below marked "est." are my estimates, not measurements.

SHORT ANSWER
Jarvis has no "Storage" page in either app and no single owner-visible view of what it keeps. Most stores are bounded. The real disk hogs are big files Jarvis does not manage: Ollama models, the update script's _jarvis-backup-* folders, and the audit-log folder. Automatic compression would save little, because the databases are small, and it would conflict with Forget/Erase.

MEASURED IN THE REPO
- Tracked files total 299 MB (git ls-files | du). .git is 400 MB, shallow clone.
- Largest tracked: six launch videos (v2 35 MB, v1 34 MB, v4 28 MB, v5 21 MB, v3 19 MB, v4 vertical 15 MB, ...), about 150 MB together. docs/SOURCE-BUNDLE.md is 13 MB. The phone's smart-turn-v3.2-cpu.onnx is 8.7 MB. Phone assets total 13 MB, desktop src 3.8 MB.
- Videos are already compressed mp4, so nothing to gain there. They only matter for cloning the repo, not for the running app.

TABLE (item | where | size/growth | bounded? | compressed? | can compress? | saving)
- memory.db (+wal/shm) | PC .openjarvis | est. MBs, slow | facts retired, not removed | no | VACUUM after Erase only | <10 MB. Erase must stay real.
- chat-history.db | PC | est. 10-500 MB over years | keep_days 0/30/90/365, default 0 = forever (jarvis_chat_log.py:198) | encrypted, not compressed | not safely (see rule note) | small
- VACUUM on chat log | jarvis_chat_log.py:219,760 | after deletes, at most hourly | yes | n/a | already done | none
- schedule.db, goals.db, projects.db, approvals/Activity, undo shelf | PC | KBs to few MB | not checked | no | no | none
- Audit logs | ~/.openjarvis/logs/jarvis-<date>.jsonl (backend/README.md:3878) | est. 1-20 MB per day, worst case more | 90 days per the brief; I found no cap in the code I grepped (not confirmed) | plain jsonl | YES: gzip files older than 7 days, roughly 10x smaller | est. 0.1-1 GB
- backend.log | PC | 4 MB rotation, desktop only (logfile.rs:48) | yes for the desktop log; backend's own log not checked | no | trivial | none
- Crash notes | desktop | max 10 per brief | yes (crash_notes.rs, cap not read) | no | no | none
- Backups | folder the owner picks | 5 files (KEEP=5, jarvis_backup.py:189, _retain :632) | by count only, not size | zip ZIP_DEFLATED at default level (:518), then AES-GCM (:389) | already well done (compresses before encrypting, correct order) | none. Prune by total size is an option.
- Backup dedupe | n/a | nearly identical every run | no | no | not possible: each is encrypted with a fresh code and nonce | none
- _jarvis-backup-* folders | inside backend folder, from apply-patches.ps1 | full copy of patched files per run, MBs each, grows every update | NEVER pruned ("Nothing deletes old backups for you", apply-patches.ps1:1339) | no | keep newest 2, delete the rest, or zip | est. 10-100 MB per run
- Ollama model store | %USERPROFILE%\.ollama (OLLAMA_MODELS) | 5 GB per 8B Q4_K_M; each extra model, the previous-model rollback copy, lane models and MiniCPM-V add 1-6 GB | no | already Q4_K_M (quantised) | YES: listing and removing unused models with one approval card | est. 5-20 GB. BIGGEST PAYOFF.
- Kokoro v1.0 pack + voices-jarvis.bin | PC | 350 MB, fixed | fixed | model files | no | none. The old v0.19 pack may still be there: est. 300 MB.
- fastembed, HF cache, Playwright/Obscura, Python packages | PC | est. 0.5-3 GB, fixed | not managed | mostly binaries | no | none
- Wake-word / voice prints | PC | small | fixed | no | no | none
- Screen/pictures | nowhere | design says none kept | n/a | n/a | n/a | not audited on disk, only design/docs read
- Exported support chats | wherever the owner exports | plain, not encrypted, by owner decision | owner's choice | no | no | small
- Phone: CapturedNotifications | data/CapturedNotifications.kt:272-275 | 200 rows, 7 days | yes | no | no need | KBs
- Phone: ModelsCache, ChatLog cache, CrashLog, DataStore/SharedPreferences | app private storage (CrashLog.kt:80 filesDir) | KBs | mostly | no | no | none
- Phone: APK | assets 13 MB (smart-turn 8.7 MB, wake word ~3.8 MB) | fixed | fixed | onnx already compact | maybe | not measured. APK total unknown.

FINDINGS, BY PAYOFF
1. Ollama models are the disk hog and nothing manages them (est. 5-20 GB). I found no "remove unused model" path in the code I grepped (jarvis_models.py does not exist under that name; not investigated further). Smallest safe change: a read-only "models on disk, size each, last used" list in Brain > Model, plus a "Remove" that raises one approval card (an existing card pattern). Saving: est. 5-20 GB.
2. Update-script backup folders grow forever. Smallest safe change: the script offers to delete all but the newest 2 after a green run (printing the line already exists at :1339). Saving: est. 10-100 MB per update.
3. Audit logs: 90 days retention per the brief, no compression that I found. Smallest safe change: gzip logs older than 7 days. Audit logs contain tool names and ids, not chat text (README:3878; content not read), so gzip carries little Forget risk. Est. 0.1-1 GB.
4. No "Storage" page. Only free-disk reads exist: jarvis_data_health.py:54-171 warns under 1 GiB free where Jarvis writes (WARN, never fails, never fixes); jarvis_pc_help.py:281-503 answers "how full is my disk"; a disk_free widget source (jarvis_widgets.py:181). Nothing in the desktop settings/brain or phone screens shows Jarvis's own usage. Smallest safe change: one read-only "Jarvis is using X MB" list (per store, honest sizes, "not measured" for Ollama) in both apps.
5. Full-disk behaviour: only the preflight warning exists. I did NOT verify what a write does when the disk is full (SQLite "database or disk is full", failed backup mid-write, log write). Backups write a temp file? Not checked. Owner call whether to test.
6. Backups are already compressed before encryption. Only a size-based prune is missing (count of 5 is fine unless the databases grow to GB).

RULE CONSTRAINTS
- Do NOT compress old chat rows into archives or keep zipped copies: they would keep copies of erased words. Chat-history.db already zero-overwrites and VACUUMs on delete (jarvis_chat_log.py:80-85). Any compression must be in-place inside the same database, and I recommend against it: the saving is small.
- Backups are already the accepted "erased facts stay until they age out" exception. Pruning by size does not worsen that.
- Compressing audit logs is safe for Erase but must not include chat text. Crisis chats: titles only, nothing to compress.
- Sizes shown in the UI must say "estimate" or "not measured" for Ollama.

OWNER DECISIONS
A. Old Ollama models: (1) recommended: list them with sizes and offer Remove behind one card; (2) only show the list; (3) leave it.
B. Update-script backup folders: (1) recommended: offer to delete all but the newest 2 at the end of a green run; (2) leave the message as it is.
C. Audit logs: (1) recommended: gzip after 7 days, delete at 90; (2) leave them.

Not checked: audit-log rotation code itself, crash-note cap value, PC-side backend log rotation, phone WebView cache, APK total size, whether the old Kokoro v0.19 pack stays after upgrade.
