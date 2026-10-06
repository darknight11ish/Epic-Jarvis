# Measured on the owner's PC, 2026-10-05

**The first real measurement this project has ever taken on its own hardware.**
Everything in `HARDWARE-PROFILES.md`, `MODEL-TOPOLOGY.md` and `SECOND-CARD.md`
until now was labelled "calculated, not measured" by its own text. These numbers
replace that for the questions below.

- **When:** 2026-10-05, 09:33 PDT.
- **Machine:** Windows 11, NVIDIA driver 616.56, CUDA UMD 13.4.
- **Commands the owner ran:** `nvidia-smi`, `ollama ps`, and a log search.
- **Nothing was changed to take these.** They describe the machine as it runs.

## What is installed

| Card | Role in `nvidia-smi` | Memory | In use at rest |
|---|---|---|---|
| RTX 2060 12 GB | GPU 0 | 12288 MiB | **4725 MiB**, with `llama-server.exe` on it |
| RTX 2080 SUPER 8 GB | GPU 1 | 8192 MiB | 1144 MiB, desktop windows only |

**Both cards are installed and working, and the model is running on the 12 GB
card.** Four documents still say no second card is installed and that everything
is calculated - `SECOND-CARD.md:29`, `MODEL-TOPOLOGY.md:418`,
`HARDWARE-PROFILES.md:4-5` and `JARVIS-API.md:1854`. They are out of date as of
this measurement and should be corrected rather than left to contradict the
machine.

Note also that the **12 GB card is GPU 0** and holds the model, while the
2080 SUPER is GPU 1 and runs the desktop. The documents describe the 2080 SUPER as
the primary card; the machine has it the other way round.

**Which card the monitor is on, re-read 2026-10-06.** The same `nvidia-smi`
answers this too, in one line (`display_active` is the column):

```powershell
nvidia-smi --query-gpu=index,name,memory.total,display_active,compute_cap --format=csv
```

```
index, name,                   memory.total [MiB], display_active, compute_cap
0,     NVIDIA GeForce RTX 2060,       12288 MiB, Disabled,      7.5
1,     NVIDIA GeForce RTX 2080 SUPER,  8192 MiB, Enabled,       7.5
```

**So the monitor is on the 2080 SUPER (GPU 1), not on the 12 GB card.** Two things
follow. `docs/HARDWARE-PROFILES.md`'s generated table had this the wrong way round:
its `two_2080s_2060_mon12` row said "monitor on the 2060". That row is now the same
machine as `two_2080s_2060_mon8` (monitor on the 2080 SUPER), and both are made by
`tools/gen_hardware_cases.py` from the designer's case list, so the table cannot
drift from it again. And the case list is where the *planner* reads the monitor
from; `jarvis_compute.primary()` (which does read `display_active`) sits in the
second-card path, `jarvis_second_card._primary`, not in `jarvis_profiles.plan()`.

## What the model is doing

```
NAME        ID              SIZE      PROCESSOR    CONTEXT    UNTIL
qwen3:8b    500a1f067a9f    5.6 GB    100% GPU     4096       Forever
```

**1. There is no spill - the audit's central performance fear does not apply.**
`100% GPU` means every layer is on the card, and Ollama's own log says the same
thing in one line: `load_tensors: offloaded 37/37 layers to GPU`. That is the
strongest single proof available that no part of the model is on the processor -
**37 of 37** means every layer, and any spill would show a smaller first number
(`offloaded 33/37` and so on). The same log entry records how the memory was
divided: `CUDA0 model buffer size = 4643.78 MiB` on the card against
`CUDA_Host model buffer size = 333.84 MiB` beside it, and
`llama_context: n_ctx = 4096`, which confirms the 4,096 beside it in Ollama's own
output above, from the loading side. The arithmetic in
`HARDWARE-PROFILES.md:528` (8.60 GiB against an 8.0 GiB card, "~4 of 37 layers
would fall to the processor, five times slower") was written for the old one-card
arrangement. On the 12 GB card the model occupies 5.6 GB and leaves about
**6.4 GB free**. `DEEP-AUDITS-2026-10-05.md` §4 called this "the most important
unmeasured number in the project"; it is now measured, and the answer is the good
one.

**2. But the model is running at 4,096 tokens of context, not the 16,384 the
documents call the everyday configuration.** This confirms
`MODEL-TOPOLOGY.md:46-88`, which says the deployed context falls to 4,096 and
"nothing in the request chooses it". So the 16K `jarvis-primary` preset is
described in the docs and **not in use**.

**3. The honest advice is the opposite of what the audit recommended.** The audit
said "if it is spilling, drop the context to 8,192". It is not spilling, and
16,384 needs roughly 6.5 GB against 12 GB - so **16K fits with room to spare and
the owner can raise the context for longer conversations.** That is the one change
these numbers justify.

**4. `UNTIL: Forever`** confirms `OLLAMA_KEEP_ALIVE=-1`: the model never unloads,
so 5.6 GB is held permanently. On the 12 GB card that is affordable; it is still a
permanent cost worth knowing.

## The log search that found nothing, and what it did not mean

**Corrected 2026-10-05.** This section used to say the Ollama log does not exist
on this machine. **That was wrong, and here is what is true.**

The log is at `%LOCALAPPDATA%\Ollama\server.log`, and it is there:

| What was checked | What the machine says |
|---|---|
| The file | **exists** - 898,124 bytes when this was measured |
| Created | 2026-09-02, 22:41 |
| Last written | 2026-10-05, 09:56 (this morning, while the measurement was being taken) |
| Length | 10,011 lines, and still growing - Ollama adds a line for every request it answers |
| `offloaded N/M layers to GPU` | **found** - `load_tensors: offloaded 37/37 layers to GPU`, 277 lines from the end |
| `flash_attn` | **found** - `llama_context: flash_attn            = auto` |

**Why the earlier note was written.** A search of the log for that pattern came
back with nothing, so the section concluded the log was not there. The search did
return nothing - but a search that returns nothing is **not** proof that a file is
absent. It can mean the words searched for are not spelled that way, that the
search looked at the wrong path, that the search itself did not run, **or that the
search looked at too little of the file.** The claim in the old wording was a
conclusion drawn from a result that could not support it.

That last reason is a real trap with this very log. It only ever grows, and on
2026-10-05 the `offloaded 37/37` line sat **277 lines from the end** of a file that
was 10,011 lines long. Any search that reads a fixed window near the end - a
`-Tail`, a `Select-Object -Last`, a line count typed by hand - finds that line today
and loses it after a few hundred more lines are written, while still reporting
"nothing found". **The measurement kit is no longer one of those**:
`scripts\measure-cards.ps1` now reads **the whole file** (a line at a time, never
held in memory) when the file is 64 MB or less, and the last **20,000 lines** when
it is bigger, and prints which of the two it read. At 898,124 bytes this log is far
under 64 MB, so on this machine the line is read every time and cannot stop being
found while the file stays under 64 MB. The two "nothing found" sentences now say
which search ran: "Searched the whole file, and it holds none of the lines worth
reading" is the file's own answer, while "Searched the last 20,000 lines" means
those lines may still be further back, in a part the check did NOT read.

**What to do differently: check the file itself.** Before writing down that a file
is missing, look at the file:

```powershell
Test-Path "$env:LOCALAPPDATA\Ollama\server.log"      # True or False
Get-Item  "$env:LOCALAPPDATA\Ollama\server.log" | Select-Object Length, CreationTime, LastWriteTime
```

**Use `ollama ps` first anyway.** It prints the processor split, the size, the
context and the keep-alive straight from Ollama, which is easier to read than a
log and is live rather than a record of the last time the model loaded. Treat the
log as a useful extra that may be absent on another machine - and if a search of
it finds nothing, say that, rather than saying the file is not there.

## What this unblocks

Features gated on "the second card is installed and measured" can now be planned
against a measured machine: the second-card lane, longer conversations, picture
understanding, and the 60-frame face cap the owner deferred on 2026-09-29 pending
"a measurement from the owner's PC".

The two things still unmeasured: **whether `CUDA_VISIBLE_DEVICES` pinning works on
this pair** (switch a lane on and watch which card's memory rises), and **the frame
cap question** (the face and the model sharing the 2060 while it talks). Both are
one command away and neither needs a restart.
