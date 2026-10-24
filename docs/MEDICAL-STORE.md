# The medical record, kept apart - and now locked

**Written 2026-10-24, updated the same day after the owner's decision.** This
page explains, in plain words, what Jarvis now has for medical records, what it
deliberately does **not** have, and the one question that is still yours to
answer. It describes the code in `backend/jarvis_medical_advocate.py` (and its
copy in `jarvis-backend/`).

On 2026-10-24 the owner answered the two open questions this page used to carry:

> "I wanted it encrypted as well and part of that file."

So the record is now **encrypted at rest**, and `health.db` **is part of the
same `.jbak` backup file** - reversing the first version of this page, which
said "not encrypted" and "not in your backups". The rest of this page describes
what is true now, and the first version's reasons are kept in
`docs/DECISIONS.md`.

---

## What this is

Three small things that share one subject:

1. **A separate, encrypted store for your medical record.** Conditions,
   medicines, lab results and visits live in their own file, in their own
   folder, with every record field sealed:

   `C:\Users\<you>\.openjarvis\medical\health.db`

   Not in `memory.db`. Not in `projects.db`. Not in `today.db`. Nothing in
   Jarvis's general memory reads it, and nothing in it is learned as a "fact
   about you". Its own key lives in Windows Credential Manager, and the record
   travels in your `.jbak` backup under its own `medical/` folder.

2. **A checker for a health record file.** If you have a file exported from a
   patient portal in the FHIR R4 format (the standard most US portals use), the
   checker reads it on this PC and reports:
   - whether the file's own shape is broken (a missing status, a reference that
     points at nothing, two records with the same address);
   - whether a lab row contradicts itself (the number and its unit disagree,
     the printed range is upside down, the "normal/high/low" flag disagrees with
     the number);
   - every code it **cannot** check the meaning of - which is all of them,
     because the LOINC, RxNorm, ICD-10-CM and SNOMED tables are not on this PC.

   It is a checker, not a medical review and not a diagnosis.

3. **A client for a small local medical model.** MedGemma 1.5 4B runs on your
   RTX 2080 SUPER in a lane of its own. It can read a lab row and say "this
   looks odd", or "I cannot tell". It is never the authority on anything, and
   it can never change what the checker found.

There is **no screen** for any of this yet - not on the desktop, not on the
phone. It is a library, and a library is what tonight's slice could finish
honestly.

---

## The five limits, stated plainly

These are the things a person is most likely to assume wrongly. Read them
before trusting the rest.

1. **Reading a medical record pins the chat to local models for 30 minutes,
   not forever.** Every read and write sets the same "taint" latch the calendar
   and the file tools use. The latch lasts 30 minutes
   (`taint_latch_minutes = 30` in `jarvis-framework.toml`). After that, a later
   turn in the same chat with no medical words in it can be routed to a cloud
   lane again. Two settings in the file look like they promise a permanent
   latch; nothing reads them, and it is **not** built.
2. **The record is in your backups, in its own folder, with its own key.** A
   `.jbak` file carries `health.db` as `db/medical/health.db` - its own folder,
   never flattened beside `memory.db` - and carries the record's 32-byte
   encryption key inside the same encrypted archive, exactly as it already does
   for chat history. That is what makes a restore on a **new PC** work: the new
   PC has no key in Windows Credential Manager, and the restore puts the
   backup's key there. The one limit: if the key cannot be read when the backup
   is made, the record is left out rather than carried as a file nothing could
   open.
3. **It is encrypted at rest, and this is what still sits in plain sight.** Every
   record field - label, dates, value, unit, source, note - is sealed with
   AES-256-GCM under a 32-byte key kept in Windows Credential Manager, under an
   entry of its own called `Jarvis Backend/medical key` (you can see and delete
   it in Control Panel, Credential Manager, Windows Credentials). The file
   itself is still a readable SQLite database, so a person or a program looking
   at it can see: the file's name and folder, its size and times, that there are
   rows in `conditions`, `medications`, `labs` or `visits`, each row's number, a
   random 16-character row label, **when** each row was made, and the audit rows
   (which action, which kind of record, which row number, how many rows - never
   a record's words). They can see that a medical row exists and when. They
   cannot see what it says without the key. A second key does not make this
   unbreakable: anyone who is already you on this PC, and can run programs as
   you, can ask Windows Credential Manager for the key the same way Jarvis does.
   Encryption protects the file at rest, on a disk, in a copy - not against
   someone who already controls your Windows account.
4. **Your chat history still contains the medical conversation, and it IS
   backed up.** Keeping the structured record in its own file does not remove
   the words from `chat-history.db` (voice transcripts included), from a
   screenshot, or from the backups that carry chat history.
5. **The model is an explainer, never an authority or a verifier of codes.**
   Measured on 2026-10-24: asked for the LOINC code of a basic metabolic panel,
   MedGemma 1.5 4B answered `8141`, and `81416-1`/`81417-1`/... in another run.
   The usual code is `24323-8`. It also leaks its internal thinking markers
   (`<unused94> ... <unused95>`) into the visible answer; the module strips
   them. Never treat "the model said so" as a check.

---

## What is built tonight, and what is not

**Built** (backend only, in `backend/jarvis_medical_advocate.py`):

- the isolated store: four record kinds, write-ahead logging, secure delete,
  and an `erase_all()` that empties only that one file and then rebuilds it -
  and **does not need the encryption key**: a lost or replaced key never stops
  you wiping the record, because erasing deletes the sealed bytes without
  decrypting anything (the 30-minute latch is still required, first, as for
  every other operation on this file);
- **encryption at rest**: every record field sealed with AES-256-GCM under a
  key of its own in Windows Credential Manager. No record payload is ever
  written to disk in plain text, and a test reads the raw file bytes (and any
  journal beside it) and fails if a distinctive secret appears;
- **the medical record in every backup**, under `db/medical/health.db`, with
  its key inside the archive, so a restore on a new PC opens it;
- an audit table that records **what happened** (which action, which row id,
  how many rows) and never the words of a record or a question;
- the 30-minute health latch on every read and every write, failing closed:
  if the latch cannot be set, nothing is opened and nothing is written;
- the local MedGemma lane client, with a calm fallback to your main local model
  (`:11436`) when the lane is down. Its request timeout is **120 seconds**, not
  the 25 it first shipped with: measured on 2026-10-24, one answer took 28.35 s,
  so 25 s was cutting the model off and showing you the fallback instead;
- the offline FHIR R4 structural checker and its plain-English summary.

**NOT built tonight** - do not expect these, and do not let a future summary
imply them:

- **No biometric lock screen.** Nothing asks for Windows Hello or a fingerprint
  before reading the store.
- **No phone screen and no desktop screen.** No route, no button, no panel.
  `tools/check_parity.py` has nothing to classify because no route exists.
- **No backup toggle.** There is nothing to switch: the record is always in a
  backup now, that is the owner's decision, and it travels locked. Turning it
  back out would be a code change to `jarvis_backup.SOURCE_DBS`.
- **No non-expiring latch.** See limit 1. "Keep this chat local until it ends"
  needs code, not a settings change.
- **No federal-API lookup.** Nothing asks RxNav, MedlinePlus, openFDA or
  DailyMed anything. Every one of those is a network call, and a bare LOINC
  code already reveals which tests you had.
- **No outbound de-identifier.** There is no code that strips names, dates or
  record numbers from a query, and none is reused from `jarvis_scrub.py` (which
  says in its own header that it is not an egress filter).
- **No import into the store.** The checker reads a file and saves nothing; the
  store is filled only by a direct call to `add_record()`.
- **No code-meaning checking.** No LOINC, RxNorm, ICD-10-CM or SNOMED table is
  on this PC. The checker reports code **shapes** and lists every meaning as
  "not checked".
- **No data-health check of this file.** The existing "is my data OK" check
  opens three databases (`chat-history.db`, `memory.db`, `projects.db`) and does
  not look at this one. A damaged medical file would not be reported there.

---

## The medical model lane

MedGemma 1.5 4B is installed in Ollama as **`medgemma1.5:4b-it-q4_K_M`**.
`medgemma:4b` is the older 1.0 model - do not use that tag.

- **Lane address:** `http://127.0.0.1:11435` (loopback only; the module refuses
  any other host).
- **Model store:** `D:\Jarvis Models\Ollama\store`, shared by all the lanes.
- **Your main local model** is on `:11436` (`qwen3.5:9b`). `:11434` is a third,
  empty server.
- **Measured:** 100% GPU on the RTX 2080 SUPER, 16,384 context,
  `size_vram` 2,817,953,626 bytes. The primary model never moved when this lane
  was started.

### Start the lane (one line, copy-ready)

The lane does **not** survive a reboot. This starts it again, on the 2080 SUPER
only, without touching the other two lanes:

```powershell
$env:OLLAMA_HOST='127.0.0.1:11435'; $env:OLLAMA_MODELS='D:\Jarvis Models\Ollama\store'; $env:OLLAMA_KEEP_ALIVE='5m'; $env:OLLAMA_CONTEXT_LENGTH='16384'; $env:OLLAMA_KV_CACHE_TYPE='q8_0'; $env:OLLAMA_VULKAN='false'; $env:CUDA_DEVICE_ORDER='PCI_BUS_ID'; $env:CUDA_VISIBLE_DEVICES='1'; Start-Process 'C:\Users\pcadmin\AppData\Local\Programs\Ollama\ollama.exe' -ArgumentList 'serve' -WindowStyle Hidden
```

Those `$env:` lines affect only that shell and the process it starts. The
`CUDA_DEVICE_ORDER` line is not optional: without it, `CUDA_VISIBLE_DEVICES=1`
points at the **wrong** card on this PC (measured 2026-10-24).

If the model itself is ever missing, pull it into the lane:

```powershell
$env:OLLAMA_HOST='127.0.0.1:11435'; ollama pull medgemma1.5:4b-it-q4_K_M
```

### Check the lane is up

```powershell
Invoke-RestMethod 'http://127.0.0.1:11435/api/tags' | Select-Object -ExpandProperty models | Select-Object name, size
Invoke-RestMethod 'http://127.0.0.1:11435/api/ps'
Invoke-RestMethod 'http://127.0.0.1:11436/api/ps'
```

What you should see: the first shows `medgemma1.5:4b-it-q4_K_M`; the second
shows it loaded after a question, 100% GPU at 16,384 context; the third still
shows `qwen3.5:9b` untouched.

From Python, the module does the same check in 0.2 seconds and never opens a
real socket outside this PC:

```python
import jarvis_medical_advocate as M
M.lane_status()
# {'available': True,
#  'lane_url': 'http://127.0.0.1:11435',
#  'model': 'medgemma1.5:4b-it-q4_K_M',
#  'note': 'The local medical model is running on this PC. ...'}
```

If the lane is down, `lane_status()` returns `available: False` and a calm note
that names your main local model (`:11436`). It does not raise.

---

## Using the store

```python
import jarvis_medical_advocate as M

M.init_store()                     # makes the folder, the file and the key
M.add_record("labs", label="HbA1c", observed="2026-10-01",
             value="6.1", unit="%", source="paper report")
M.list_records("labs", 20)         # newest first, opened with the key
M.erase_all()                      # empties this file only; no key needed
```

The four record kinds are `conditions`, `medications`, `labs` and `visits`. A
row carries a `label`, `started`, `observed`, `value`, `unit`, `source` and
`note`; `label` is the only required one. All seven are sealed before they are
written.

`JARVIS_MEDICAL_DB` moves the file somewhere else - the test suite uses it to
work in a scratch folder, and you may use it to put the file on another disk.
The default is `~/.openjarvis/medical/health.db`. A backup follows the setting
too: it asks the module where the file really is, so a moved store is still
carried (and put back at the same place).

Every read and write sets the health latch **before** it touches the file, and
asks for the key before it opens anything. If the latch cannot be set, or the
key cannot be had, or the key is the wrong length, or the key does not open
what is already kept, the call raises `MedicalStoreUnavailable` and nothing is
created, read or written. There is no plain-text fallback and no environment
variable that carries a key.

---

## Checking a FHIR file

```python
import jarvis_medical_advocate as M
report = M.validate_bundle(open("export.json", "rb").read())
print(M.summarise(report))
```

The report says one of three things about the file's shape:
`no_errors_found`, `errors_found` or `not_checked`. It never says the file is
"valid": a finite hand-written check list cannot prove that. Code meanings are
always listed under `unverified`, because the code tables are not on this PC.

The checker does not raise on bad input: a file that is not JSON, too big, too
deeply nested, or not a Bundle comes back as `not_checked` with one plain
sentence saying so.

You can give it a local model as a second reader:

```python
answer = lambda prompt: M.consult_local_medgemma(prompt)["response"]
report = M.validate_bundle(bundle, model=answer)
```

The model sees only numeric lab rows - no names, dates, addresses or free text -
and its answers are opinions with `authority: "none"`. It cannot add a code, it
cannot give advice, and it cannot change the structural report. If it is absent,
down or answers junk, `report["model"]["used"]` is `False` and the rest of the
report is exactly what it would have been.

---

## What is still your decision

**One question is still yours, and it is unchanged:** how long should a medical
read pin the chat to this PC?

- **30 minutes for now** (recommended). Free, already built, ends by itself.
- **Until the chat ends.** Needs a code change (a non-expiring latch); the two
  settings that look like they already do this are read by nobody.

The other question - whether `health.db` should go into backups - was yours and
you answered it on 2026-10-24: **"I wanted it encrypted as well and part of that
file."** Both halves are now built, and the choice is written down in
`docs/DECISIONS.md`. What you should still know about it: every archive you keep
now contains the medical record (encrypted, with its key inside the same
encrypted archive). If a backup folder is synced by a cloud program, that
program copies the encrypted file - the same as it already does for chat
history. Jarvis itself still sends nothing anywhere.

---

## How this is checked

`backend/test_medical_advocate.py` (95 tests, no socket, no model, no owner PC,
in-memory key - it never touches Windows Credential Manager) proves the store
round-trip, **that no record word reaches the disk in plain text** (it writes a
distinctive secret and scans the raw file and any journal beside it), the
payload is not readable JSON, the plain-metadata list above, the latch ordering
and fail-closed behaviour for a missing, broken, short or replaced key, that
`erase_all()` still wipes when no key can be had, that a sealed payload moved
between rows is refused instead of decoded, the separation pins, the loopback
guard, the 120-second timeout, the lane's three states, the fallback note, the
thinking-marker strip, and the FHIR canaries - each against a positive control
or a negative one beside it.

The backup is pinned by three tests: two in the medical suite (the name is in
`SOURCE_DBS`, not in `NOT_BACKED_UP`, and the key has its own target), and two
real round-trips in `backend/test_backup.py` - backup on a PC that has the key,
restore on a "new PC" whose Credential Manager entry does not exist, then read
the record back; and the harder one, a new PC that had already minted its OWN
medical key before the restore, where the archive's key replaces it and a stale
`-wal` beside the restored file is removed. The same suite's own count is now
**18 carried + 7 excluded**.

Nothing on this page is a claim about a live portal export, a real phone, or a
medical review. Those remain NOT-TESTABLE until someone runs them.
