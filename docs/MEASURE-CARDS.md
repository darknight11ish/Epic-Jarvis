# The graphics cards, measured: one line to run, and how to read it

**Short version.** Paste one line (below). It reads your two cards and what
Ollama is doing with them, prints the answer in plain words, and **changes
nothing** - it is safe while Jarvis is running. Its job is to answer the one
question the documents have argued about since 2026-09-23: *is the model
really on the 12 GB card, or is part of it on your processor?* As of
2026-10-05 that is answered: **it is entirely on the card, and there is room to
raise the context.**

The numbers behind the answer are measured, not calculated. The row they came
from is at the bottom of this page.

---

## What to run

From the folder this repository is cloned into:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\measure-cards.ps1
```

The same thing as one line, if you are not already in that folder
(adjust the path if yours differs):

```powershell
cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; powershell -ExecutionPolicy Bypass -File .\scripts\measure-cards.ps1
```

To add a row to the card scoreboard as well:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\measure-cards.ps1 -Save
```

`-Save` is the **only** thing that ever writes anything (see "The scoreboard"
below). Without it, nothing on your PC is written or changed.

**It does not run, load or unload a model.** `ollama ps` and Ollama's `/api/ps`
only report what is already in memory, and `nvidia-smi` only reads. So it will
not disturb an answer Jarvis is giving, and it will not wake a sleeping model -
which also means: if nothing is loaded, there is no split to read, and it says
so.

**It never prints a token or a key.** The only thing it talks to is Ollama on
this PC (`127.0.0.1`), and it sends no header of its own - nothing to
authenticate, so there is no token here to send or print - and no conversation
text is read anywhere.

---

## What it checks, in order, and what each line means

### 1. `ollama ps` - the main answer

Ollama's own table, then one plain line per loaded model. This is the check to
trust; the rest is evidence around it.

```
NAME        ID              SIZE      PROCESSOR    CONTEXT    UNTIL
qwen3:8b    500a1f067a9f    5.6 GB    100% GPU     4096       Forever
```

| Column | What it means |
|---|---|
| **SIZE** | How much memory Ollama is holding for the model, as Ollama counts it. |
| **PROCESSOR** | **The column that matters.** `100% GPU` means every layer is on a graphics card. Anything else - `52%/48% CPU/GPU`, or `100% CPU` - means part of the model is on your processor, which is about five times slower for that part, and nothing else warns you. |
| **CONTEXT** | How much conversation the model can hold at once, in tokens (a token is a word or part of a word). What you have now is 4,096; the everyday setting this project documents is 16,384. |
| **UNTIL** | When the model unloads. `Forever` means never. |

The one you do not want to see:

```
   SPILL   qwen3:8b: PROCESSOR is "52%/48% CPU/GPU" - part of your model is running on
           your processor. That part is about five times slower, and
           nothing else warns you about it.
```

If you see that, the fixes are, cheapest first: free the card (close a game or
a browser playing hardware video), **lower** the context, or move that work to
the second card. On 2026-10-05 this machine showed `100% GPU`, so none of that
was needed.

### 2. `nvidia-smi` - the cards themselves

```
   #0  NVIDIA GeForce RTX 2060     12,288 MiB total     4,725 used     7,563 free
   #1  NVIDIA GeForce RTX 2080 SUPER   8,192 MiB total     1,144 used     7,048 free
```

MiB is the unit NVIDIA's own tool prints, and the exact numbers are kept as
they come: **12,288 MiB is a 12 GB card**. Both cards are listed, so "is the
second card installed?" is answered by the top line of this block.

Then it says which card the model is on, found by asking `nvidia-smi` which
card is running the model's own process (`llama-server.exe`):

```
   The model is on #0 (llama-server.exe, 4,725 MiB).
```

Some Windows drivers do not name the process at all. When that happens the
check says so, and works the card out from memory instead - the card already
holding at least as much as the model's size:

```
   nvidia-smi did not name the model's process. The cards' own memory says
   the model is on #0: 5,435 MiB in use there, and the model is 5.6 GB.
```

On this PC (2026-10-05) the process was **not** named, so the fallback wording
is the one you will see - and it reached the same answer. **Which card the
model is on is worth reading carefully**: the documents describe the 2080 SUPER
as the primary card, and the machine has it the other way round - the 12 GB
card is GPU 0 and holds the model.

### 3. `/api/ps` - the exact split, in bytes

`ollama ps` rounds; this does not:

```
   qwen3:8b: on the card 5,320 MiB of 5,320 MiB = 100%   (context 4096)
```

`size_vram` (the part on the card) against `size` (the whole thing). **100%
means no spill.** Anything less is the spill the `PROCESSOR` column warned
about, and the check says which of the two to believe: the exact bytes.

If Ollama is not answering, or no model is loaded, it says so in one line and
carries on. That is not a failure of the check; there is simply nothing loaded
to measure.

### 4. The context - the one change these numbers justify

```
   running now                4,096 tokens
   the everyday setting       16,384 tokens
   16,384 needs               about 6.5 GB of model on the card, in total
   room on that card          12,288 MiB total, 7,563 MiB free right now (nvidia-smi)

   So: 16,384 FITS - about 5,632 MiB to spare on the card.
```

Three numbers, in plain words: what you run now, what this project documents as
the everyday setting, and how much room the card has. 16,384 tokens needs about
**6.5 GB** of model on the card; the 12 GB card holds it with room to spare.

**The old advice was the opposite, and it is wrong for this machine.** The
2026-10-05 audit said that if the model were spilling, dropping the context to
8,192 would fix it. It is not spilling, so **do not drop to 8,192** - that
would throw away half your conversation for nothing. Raising it is the change
the numbers support.

**Where the setting lives.** It is the context length, `num_ctx`:

- The everyday model's own file, `backend\jarvis-primary.Modelfile`, carries
  `PARAMETER num_ctx 16384`. Ollama uses it only when that tuned copy is the
  model loaded; building it is one line, and the setting is read when the model
  loads:

  ```powershell
  ollama create jarvis-primary -f backend\jarvis-primary.Modelfile
  ```

- The other way is the setting `OLLAMA_CONTEXT_LENGTH=16384` for Ollama
  itself, which applies to a model that carries no setting of its own. Ollama
  reads it only when it starts, so Ollama has to be restarted for it to take
  effect.

Either way, **run this check again afterwards and read the CONTEXT column** -
it is the proof, and it costs one line. `MODEL-TOPOLOGY.md` ("Setup") has the
rest of the sequence.

A note on why 4,096 is what you have: `ollama ps` on 2026-10-05 showed the
plain `qwen3:8b`, not the tuned `jarvis-primary` copy, and a model with no
setting of its own gets Ollama's own choice. `MODEL-TOPOLOGY.md`, "The thing
that is wrong right now", says the same thing and explains how Ollama picks
4,096.

**What is measured here and what is not:** 4,096, the card's memory and the
free memory are all measured. "16,384 needs about 6.5 GB and fits" is
*calculated from those measurements* using this project's own budget
(`MODEL-TOPOLOGY.md`, "The budget"; `HARDWARE-PROFILES.md` section 8.2) - 16K
has not been loaded on this PC yet. It is the next thing to measure, and this
same command is how.

### 5. What `UNTIL: Forever` costs

```
   qwen3:8b: UNTIL is Forever, so the model never unloads and 5.6 GB stays held on
   the card for as long as Ollama runs (OLLAMA_KEEP_ALIVE=-1).
```

`Forever` means the model **never unloads**: 5.6 GB is held on the card
permanently, for as long as Ollama runs. That is deliberate
(`OLLAMA_KEEP_ALIVE=-1`): it is what stops the first word after you step away
waiting about six seconds for a reload. On the 12 GB card it is affordable. It
is still 5.6 GB that is never free for anything else - worth knowing, not a
problem to fix.

If the column shows a time instead, the check says the opposite: the model
unloads then, and the next question after that waits for it to load again.

### 6. Ollama's own log - the extra check, after `ollama ps`

The audit suggested reading `%LOCALAPPDATA%\Ollama\server.log` for
`offloaded N/M layers to GPU`. The check reads it **if it is there**, prints the
few useful lines, and says what `offloaded 37/37 layers to GPU` means (whole
model on the card; a smaller first number means part of it is not).

**This is the extra, not the main answer.** Run `ollama ps` (§1) first: it prints
the processor split, the size, the context and the keep-alive straight from
Ollama, it is live rather than a record of the last load, and it cannot fail to
show you something because a file moved or a search missed. The log is a second
witness to the same fact.

If the file is not there, the check prints one plain line saying so and carries
on. **A missing log is never a warning and never a failure** - which is exactly
why `ollama ps` leads.

**One correction, measured 2026-10-05: the log file does exist on this PC.**
`%LOCALAPPDATA%\Ollama\server.log`, created 2026-09-02, last written 2026-10-05
at 09:56. It is about **898,000 bytes** and it grows every time Ollama writes to
it, so read that size as "roughly this, and still moving". Its lines include both
of the things the audit suggested looking for:

```
load_tensors: offloaded 37/37 layers to GPU
llama_context: flash_attn            = auto
```

`offloaded 37/37` says the same thing `ollama ps` says: every layer is on the card.
**An earlier search of this same log came back with nothing, and that empty result
was taken to mean the file was not there.** The file was there all along.

**So: a search that finds nothing does not prove a file is absent.** It can mean
the words are spelled differently, the search looked in the wrong place, the
search did not run at all - **or the search did not read enough of the file.**
That last one is why the check now says which part of the log it read: **the whole
file** when the file is 64 MB or less (read a line at a time, so even a big file
never has to fit in memory), and otherwise the last **20,000 lines**. Its two
"nothing found" sentences are deliberately different: "Searched the whole file,
and it holds none of the lines worth reading" is the file's own answer, while
"Searched the last 20,000 lines" says those lines may still be further back, in a
part the check did NOT read. On 2026-10-05 the log was well under 64 MB and the
`offloaded 37/37` line sat 277 lines from the end, so the check reads it every
time, and it cannot drop out of view while the file stays under 64 MB. When it
matters, read the whole file:

```powershell
Test-Path "$env:LOCALAPPDATA\Ollama\server.log"
Select-String "$env:LOCALAPPDATA\Ollama\server.log" -Pattern 'offloaded \d+/\d+ layers to GPU' |
  Select-Object -Last 3
```

`MEASURED-2026-10-05-owner-pc.md` carries the same correction, so the two pages
agree with each other and with the machine. Nothing here depends on the log
either way: `ollama ps` is the better evidence, which is why it leads.

---

## The scoreboard: the `-Save` row

With `-Save`, the check adds **one row** to a small file beside `speed.jsonl`,
in the same settings folder everything else in Jarvis uses
(`%OPENJARVIS_CONFIG_DIR%`, else `%USERPROFILE%\.openjarvis`):

```
cards.jsonl
```

Append only, one JSON line per run, numbers and names only - no words of any
conversation, ever. Rows are never deleted or rewritten, so the file becomes the
history of what the cards were doing on the days you looked. It is a different
file from `speed.jsonl` on purpose: `speed.jsonl` is about one answer's speed,
this is about the cards.

To read the last row later:

```powershell
Get-Content "$env:USERPROFILE\.openjarvis\cards.jsonl" | Select-Object -Last 1
```

`-Save` also prints the same row as a markdown line, to paste into the table
below. Nothing else is written, and if nothing could be read, no row is written
at all - an empty row in a scoreboard looks like a measurement, and it is not
one.

---

## The measured rows

**Everything in this table is measured** - printed by `ollama ps` and
`nvidia-smi`, not worked out on paper. Copied here word for word from
`MEASURED-2026-10-05-owner-pc.md` and from the check's own first live run.

| When | Machine | Cards | Model | Size | PROCESSOR | Context | UNTIL |
|---|---|---|---|---|---|---|---|
| **2026-10-05 09:33 PDT** | owner's PC (`MARIOSBEASTDESK`), Windows 11, NVIDIA driver 616.56, CUDA UMD 13.4 | #0 RTX 2060 12,288 MiB; #1 RTX 2080 SUPER 8,192 MiB | qwen3:8b | 5.6 GB | **100% GPU** | **4,096** | **Forever** |
| 2026-10-05 09:48 PDT | the same PC, read by `scripts\measure-cards.ps1` itself | #0 RTX 2060 12,288 MiB (5,435 used, 6,627 free); #1 RTX 2080 SUPER 8,192 MiB (1,098 used, 6,890 free) | qwen3:8b | 5.6 GB | 100% GPU | 4,096 | Forever |

The first row is the owner's hand measurement, and it is the **first real
measurement this project has ever taken on its own hardware** - everything in
`HARDWARE-PROFILES.md`, `MODEL-TOPOLOGY.md` and `SECOND-CARD.md` before it was
labelled "calculated, not measured" by its own text.

The second row was taken by the check itself, accidentally, while it was being
built - a live run that was meant to be a rehearsal. It is kept here because it
is real and it agrees with the hand measurement on every point that matters. It
also earned its keep: that run exposed a bug in the check's guess at which card
the model is on (it named the 8 GB card by mistake when `nvidia-smi` did not
name the model's process), which is now fixed and is why the check falls back to
the cards' own memory instead.

What the cards were doing at 09:33, as `nvidia-smi` printed it:

| Card | Total | In use | What was on it |
|---|---|---|---|
| #0 RTX 2060 12 GB | 12,288 MiB | 4,725 MiB | `llama-server.exe` - the model |
| #1 RTX 2080 SUPER 8 GB | 8,192 MiB | 1,144 MiB | desktop windows only |

And Ollama's own log, read on 2026-10-05 after the two rows above, describing the
same load:

| Line in the log | What it proves |
|---|---|
| `load_tensors: offloaded 37/37 layers to GPU` | **Every layer is on the card.** The strongest single proof there is that no part of the model is on the processor - a spill would show a smaller first number |
| `load_tensors: CUDA0 model buffer size = 4643.78 MiB` | 4.6 GB of the model sits on the card's own memory |
| `load_tensors: CUDA_Host model buffer size = 333.84 MiB` | 334 MB sits beside it in ordinary memory - the buffer set aside for the card, not layers running on the processor |
| `llama_context: n_ctx = 4096` | the 4,096 context confirmed from the loading side |
| `llama_context: n_ctx_seq (4096) < n_ctx_train (40960)` | the model could hold 40,960 tokens; it is being run at 4,096, so most of its capacity is unused |
| `llama_context: flash_attn            = auto` | the second line the audit asked for, found |

These are the lines Ollama wrote when it loaded the model. The log does not print
a clock time on them, so they are placed by what they say, not by a timestamp: they
describe one load of `qwen3:8b` at 4,096 tokens, which is the load the rows above
measured. The log itself was last written at 09:56, after the two rows above.

**Read together:** both cards are installed and working; the model is on the
12 GB card; no part of it is on the processor; the context is 4,096 while 16,384
fits; and 5.6 GB is held forever.

---

## What these numbers do not answer yet

Two questions, both one command away, neither measured:

- **Does pinning a lane to one card work on this pair?** Switch one lane on
  (`SECOND-CARD.md`'s switches) and watch which card's memory rises: if the
  2060's rises while the 2080 SUPER's does not, `CUDA_VISIBLE_DEVICES` and
  `OLLAMA_VULKAN=0` are doing their job.
- **How much graphics work is left for the face while the model talks?** The
  60-frame cap the owner deferred on 2026-09-29 is waiting on exactly this.

And 16,384 itself has not been loaded yet - the fit is calculated, from the
measurements above. Loading it and running this check again turns that
calculation into a measurement, and takes one line.

---

## Where these numbers come from

- [MEASURED-2026-10-05-owner-pc.md](MEASURED-2026-10-05-owner-pc.md) - the
  owner's hand measurement, both cards, and what it unblocks.
- [MODEL-TOPOLOGY.md](MODEL-TOPOLOGY.md) - the context budget, why 4,096 is
  what you have, and the setup sequence for 16,384.
- [HARDWARE-PROFILES.md](HARDWARE-PROFILES.md) section 4.7 - what a
  measurement records, and the fingerprint a scoreboard row is keyed by.
- [SECOND-CARD.md](SECOND-CARD.md) - the seven switches, all built and all off
  until you turn them on.
- `scripts\measure-cards.ps1` - the check itself: reads only, reasons first, and
  every read it makes is listed at the top of the file.
