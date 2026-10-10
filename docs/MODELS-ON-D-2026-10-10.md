# Every AI model on `D:\Jarvis Models\` — what is done, and the one step left

**Written 2026-10-10** by the conversation that owns the model move (item 1 of
`.dsh-scratch/HANDOFF-QUEUE-2-2026-10-10.md`; the owner's Decision 5).

Compared against **`origin/main` = `6be188ebb6be88110123c9e174a82bfaef21d6c2`**
("Merge pull request #222"). Branch `feat/models-on-d-and-storage-tiers`,
commit **`9103dbb6`**. Every figure below was measured on this PC.

The owner's words: *"I want all AI models moved to D drive that are currently
installed on my computer."*

---

## 1. Where it stands right now — read this first

**The models are copied to D: and verified. They are NOT yet in use from D:, and
nothing on C: has been deleted.**

| Store | Size | On C: | On D: | Verified |
|---|---|---|---|---|
| Ollama — `C:\Users\pcadmin\.lmstudio\models`, shared with LM Studio | 45.70 GB | still there | `D:\Jarvis Models\Ollama\store` | **83 files / 45.70 GB — match** |
| `C:\Users\pcadmin\Documents\AI Models` | 36.78 GB | still there | `D:\Jarvis Models\AI-Models` | **17 files / 36.78 GB — match** |
| `C:\Users\pcadmin\.cache\huggingface` | 0.18 GB | still there | `D:\Jarvis Models\HuggingFace\cache` | **1263 files / 0.18 GB — match** |
| `C:\Users\pcadmin\.openjarvis\voice-models` | 1.12 GB | still there | `D:\Jarvis Models\Jarvis-Voice\voice-models` | **388 files / 1.12 GB — match** |
| `C:\Users\pcadmin\.openjarvis\models` | 0.06 GB | still there | `D:\Jarvis Models\Jarvis-Memory-Search\models` | **9 files / 0.06 GB — match** |

**Total staged: 83.84 GB.** Moving it frees roughly **55–60 GB on C:**, which had
**27 GB free** when this ran — C: being nearly full is why builds keep breaking.

Baseline recorded before anything moved, so the move can be proved afterwards:
Ollama listed **8 models, 28.26 GB** (`/api/tags`). `C:\Users\pcadmin\.ollama\models`
really is empty; the live store has always been the `.lmstudio` one.

Two things that are easy to get wrong, both handled: the `.lmstudio` folder is
**LM Studio's own store**, which Ollama was pointed into — the two programs share
one `blobs` folder, so they move together; and the two scheduled lanes resolve
their store through `model-store.txt`, so that file changes with the move.

---

## 2. Why it stopped here, on purpose

The copy is finished. The cut-over — stopping the lanes and repointing them —
needs a **quiet window**, and 2026-10-10 was not one. Measured at 12:53:

```
port 11434 has 'jarvis-primary:latest' loaded in memory
port 11435 has 'qwen3:8b' loaded in memory
port 11436 has 'qwen3.5:9b' loaded in memory
13 test process(es) are running right now
```

Stopping the lanes would have broken whatever those runs were doing. The script
**refuses** instead of guessing, which is the point of it.

---

## 3. The one step left

Run this in a quiet window — no test suite running, nothing loaded on any lane,
no `-partial` file in the store, no `ollama pull` in flight, **and with the other
conversation's agreement**, because it restarts Ollama and both lanes:

```powershell
cd 'C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main'
powershell -NoProfile -File scripts\move-models-to-d.ps1 -CutOver
```

The plan alone, touching nothing, at any time:

```powershell
powershell -NoProfile -File scripts\move-models-to-d.ps1 -DryRun
```

Re-copy with no cut-over (safe even while tests run — it only reads):

```powershell
powershell -NoProfile -File scripts\move-models-to-d.ps1 -CopyOnly
```

### What `-CutOver` does, in order

1. Copies again (robocopy, so only changed files move) and **verifies file count
   and total bytes for all five stores**. Any mismatch stops it, and **nothing is
   deleted**.
2. Backs up `model-store.txt` and LM Studio's `settings.json` into
   `%LOCALAPPDATA%\JarvisOllama\move-backup-2026-10-10\`.
3. Stops `ollama app`, `ollama` **and every `llama-server` child** — stopping
   `ollama serve` alone leaves the children holding files and graphics memory.
4. Sets `OLLAMA_MODELS` for the owner's account, and writes the same path into
   `model-store.txt`. Both are needed: the saved setting covers `ollama app.exe`
   from the Start Menu, the file covers the two scheduled lanes.
5. Changes LM Studio's `settings.json` `downloadsFolder` to the same path.
6. Sets `HF_HOME` to `D:\Jarvis Models\HuggingFace\cache`.
7. Replaces `.openjarvis\voice-models` and `.openjarvis\models` with **junction
   links** pointing at D:. Jarvis's code has both paths built in, so a link means
   **no code change and no config change**, and undoing it is one command.
8. Deletes each C: original **only after its D: copy matched again in this run**.
9. Starts both lanes again and runs `health.ps1`.
10. Compares `/api/tags` before and after: the same 8 models with the same names
    and sizes, or it says so loudly.

---

## 4. How to undo it

In this order:

1. Stop the lanes:
   `Get-Process 'ollama app','ollama','llama-server' -ErrorAction SilentlyContinue | Stop-Process -Force`
2. Copy the models back, then remove the D: copy:
   `robocopy 'D:\Jarvis Models\Ollama\store' 'C:\Users\pcadmin\.lmstudio\models' /E /COPY:DAT /DCOPY:DAT`
3. Restore the two settings files from
   `%LOCALAPPDATA%\JarvisOllama\move-backup-2026-10-10\`.
4. Remove the two junctions with
   `cmd /c rmdir "C:\Users\pcadmin\.openjarvis\voice-models"` — **`rmdir`, never
   `Remove-Item -Recurse`**, because a recursive delete follows the link and
   would delete the real models on D: — then copy those two folders back.

---

## 5. What is known-risky, said plainly

- **LM Studio cannot be verified from here.** `settings.json` will say D:, but
  LM Studio is a GUI program and may hold its own copy of that setting and
  re-write the file. If LM Studio later shows no models, open its Settings and
  set the models folder to `D:\Jarvis Models\Ollama\store` by hand. Ollama is
  unaffected either way.
- **The HuggingFace cache has a live writer.** Test runs re-download the same
  embedding model into it, and the first verification failed because a file was
  written mid-copy. It read 1263 files on both sides on the second run. If
  `-CutOver` reports an HF mismatch, wait a minute and run it again — this is
  the one genuinely busy store.
- **`OLLAMA_MODELS` must be set in the same step as the move, never before** —
  pointing Ollama at an empty folder leaves Jarvis unable to load a single
  model. This script does not set it until every copy has verified.
- **A hand-started `ollama serve` needs the variable in that shell too:**
  ```powershell
  $env:OLLAMA_MODELS = 'D:\Jarvis Models\Ollama\store'
  ```
- **`gpt-oss:20b` is not being completed.** The owner dropped it (three stalls,
  never measured, and its `-partial` file is what took C: to 5.7 GB free). There
  is no `-partial` file in the store today, and the script refuses if one appears.
- **Nothing may run this pass twice.** `scripts/apply-patches.ps1` and this
  script both restart Jarvis's pieces; they must not be run at the same time.

---

## 6. The machine now knows what it can hold

In the same commit: `backend/jarvis_storage.py` with 92 checks
(`python backend/test_storage.py`). The owner asked for model options that scale
with the machine — *"I have a lot of space on my D drive ssd that has 4tb ... this
may not be the case for everyone that installs epic jarvis on their desktop"* —
so nothing here assumes his PC. Read live on his:

```
cards: 2   total 20.0 GB, largest 12.0 GB
   NVIDIA GeForce RTX 2060        12.0 GB total, 11.0 GB free
   NVIDIA GeForce RTX 2080 SUPER   8.0 GB total,  6.9 GB free
D:\Jarvis Models free: 3579 GB
suggested tier: generous
```

Three tiers — **Lean** (a small SSD: an everyday model, about 10–15 GB),
**Comfortable** (room for longer conversations and picture understanding) and
**Generous** (large models, per-domain specialists, the opt-in choices) — each
stating **its size on disk, what it is for, which card it uses, and what it
leaves free**, before anything is chosen. A tier that will not fit says why, and
the next one down is offered; nothing is changed quietly.

`may_download()` is the single gate every download passes: **never a silent
download**, and **never one that would leave less than 25 GB free**. The test
for that is built from 2026-10-10's evidence — a 12.85 GB download that would
leave 17 GB free is refused, and the refusal says why, names the drive and says
what to do instead. The `Generous` tier carries the owner's opt-in fiction model
with its measured cost on the label (TruthfulQA −5.8 to −6.9 points, MMLU about
noise, an older build), never as the everyday assistant and never as a default.

This is folded into the **work-setups** work rather than built as a second
chooser: `jarvis_storage` supplies the space facts, the setups decide what is
installed.

---

## 7. The phrase checklist, run at last

`python backend/run_phrase_tests.py` reads the owner's own checklist
(`.dsh-scratch/android-verify/PROMPTS-TO-TEST-2026-10-10.md`, sections 1–7) and
puts every phrase through the real grammar — no port, no model, no network:

```
phrases found  : 417
346 of 417 claimed with no state active
PHRASES PROVED: 349 of 417 (346 answered here, 3 correctly sent to the model)
PASS 3   FAIL 0
```

The 68 not claimed are the phrases that need a **session already running** —
`pause`, `lock on this`, `how am I doing?` need a focus session; `bye`,
`that's it`, `end live` need Jarvis Live running. They are listed as needing the
live backend and are **not counted as passes**. Running those for real needs the
deployed backend on 4719, which was down (`actively refused`) while this ran.
