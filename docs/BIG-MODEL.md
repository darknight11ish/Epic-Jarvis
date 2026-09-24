# The big model (slow)

**Short version:** Jarvis can use a much bigger model than your graphics
card can hold, for jobs nobody is waiting on: the wiki builder, and "deep
questions" - a question you want a careful answer to, answered in the
background. It uses a free program called **colibri**. It is **off**, and it
can only be switched on once Jarvis finds colibri, a downloaded model, and
enough memory and disk. Each switch asks you first with an approval card;
turning one off never asks.

**It is slow, and nobody has measured how slow on your PC.** colibri's own
pages quote speeds from other people's computers. None of those numbers have
been checked on yours. Jarvis records the real speed of every job you run
(see "How fast is it, really?"), so the first real numbers will be yours.

---

## What it is for, and what it is not

colibri runs very large "mixture of experts" models (a model made of many
small parts, only a few of which work on each word) by keeping most of the
model on the SSD and reading only the parts each word needs. That makes
models far bigger than 8 or 12 GB of graphics memory possible - at the price
of speed: expect **minutes per answer**, not seconds.

So it is used for two things only:

| Job | What it does |
|---|---|
| **Wiki builder** (`wiki`) | The wiki builder (see [SECOND-CARD.md](SECOND-CARD.md), "Wiki builder") uses the big model instead of the second graphics card. Every page still goes through its one approval card. |
| **Deep questions** (`deep_questions`) | You ask one question; it is answered in the background, with no tools, no internet and no memory of your other conversations, and the answer is kept for you to read. |

It is **never** used for chat, voice or approvals. Those stay on your
everyday model, where answers take seconds.

Everything stays on this PC. colibri listens on `127.0.0.1` - this PC only,
not your network, not the internet - and only answers Jarvis, which holds its
key.

## The two models you chose

| Model | Kind | On disk | Memory it needs | Drive |
|---|---|---|---|---|
| **Qwen3.6-35B-A3B** | medium | about 20 GB | **about 24 GB, all the time it runs** (colibri's README: "needs full RAM residency"; its `docs/qwen36.md` says ~30 GB is comfortable) | the Samsung 870 EVO (SATA) |
| **DeepSeek V4 Flash** | giant | about 167 GB (the "REAP 150B" version: about 85 GB) | 16 GB at least, 32 GB comfortable (colibri's README) | the Samsung NVMe |

Two things to know about memory, said plainly:

- Your PC has 32 GB. The medium model needs about 24 GB **free** when it
  starts. With Windows, a browser and Jarvis running, that may often not be
  free - then Jarvis does not start it, and says how much was free. Close
  something big and try again.
- colibri is never left running: it starts when a job needs it and stops
  10 minutes after the last one (`idle_minutes`), so it does not sit on
  24 GB all day.

GLM-5.2 (372 GB) does not fit on the NVMe, and giant models on the SATA drive
are too slow (your own call, and colibri's README agrees: "Speed is set by
your disk"). If you put a giant model on a SATA drive, Jarvis says so on its
status line.

---

## Step 1 - install colibri (the ready-made Windows version)

This version runs on the processor only. It needs no compiler.

1. **Install Python 3** if you do not have it: <https://www.python.org/downloads/>.
   In the installer, **tick "Add python.exe to PATH"**. colibri's launcher is
   a Python script (colibri's `docs/windows.md`); the engine itself is not.
2. **Download colibri**: <https://github.com/JustVugg/colibri/releases> -
   the file ending in `windows-x86_64.zip` under the newest release.
3. **Unzip it** to `C:\colibri` (right-click the zip, Extract All, type
   `C:\colibri`). Inside you should see `coli.cmd`, `coli` and several `.exe`
   files. The `.exe` files are the engines; do not double-click them - on
   their own they flash a window and close, which is normal.
4. **Check it**, in PowerShell (one line):

```powershell
py -3 --version; C:\colibri\coli.cmd info
```

The first part should print `Python 3.x`; the second prints what colibri can
run.

If Windows says **"An Application Control policy has blocked this file"**,
that is Windows' Smart App Control, which blocks programs it does not know.
colibri's `docs/windows.md` (section 2) explains it and how to turn it off -
it needs a restart, and turning it back on later needs a Windows reset, so
read that first. Not checked here whether the ready-made `.exe` files
trigger it.

### The graphics card: what colibri's pages say, and why it is off

`[big_model] cuda` is `"off"` by default: colibri runs on the processor and
never touches a graphics card. That is on purpose:

- **The ready-made Windows download has no graphics-card support for your
  cards.** colibri's release recipe (`.github/workflows/release.yml` in its
  source) packs only the processor engines. Its `docs/deepseek-v4.md` says
  the Windows download "also contains the CUDA backend" - the release recipe
  in the same source does not do that, so that page looks out of date. The
  graphics-card file their automatic build does make (`coli_cuda.dll`) is
  kept for 30 days as a test file, and it is built for RTX 30 cards and newer
  (`CUDA_ARCH=portable`: sm_80 and up). Your RTX 2080 Super, RTX 2060 and
  RTX 2080 Ti are all RTX 20 cards (Turing, sm_75), which it does not cover.
- **The graphics-card route means building colibri yourself.** colibri's
  `docs/windows.md` walks through it: Git, MSYS2 (a Linux-like toolbox for
  Windows), Visual Studio 2022 Build Tools with "Desktop development with
  C++", the NVIDIA CUDA Toolkit, then building from the special "x64 Native
  Tools Command Prompt for VS 2022" with `make cuda-dll CUDA_ARCH=sm_75` and
  `make qwen36.exe CUDA_DLL=1`. For DeepSeek V4 it is a different file, built
  with `CUDA_ARCH=portable-pre-ampere NO_TC=1` for RTX 20 cards
  (`docs/deepseek-v4.md`, "GPU coverage"). That page lists a dozen ways it
  goes wrong. **It is a heavy job for a beginner.** Do it only if the
  processor-only speed Jarvis measures is really not enough.
- **If you ever do turn it on**, Jarvis uses the **second** card only - never
  the 2080 Super, which runs everyday chat - and only when Jarvis sees a
  capable second card whose own features are not running. Otherwise it
  refuses and says why. One more warning from colibri's own measurements
  (`docs/qwen36-cuda-tier.md`): Qwen3.6 with one 8 GB card peaked at 40 GB of
  memory, more than your PC has.

---

## Step 2 - download the models

Downloads come from Hugging Face (the website most open models are shared
on). They are big and resumable: if one stops, run the same line again.

First find out which drive letter is which. This line lists each drive with
its connection (NVMe or SATA), and changes nothing:

```powershell
Get-Partition | Where-Object { $_.DriveLetter -match '[A-Z]' } | ForEach-Object { $p = $_; $d = Get-PhysicalDisk | Where-Object { $_.DeviceId -eq [string]$p.DiskNumber }; '{0}:  {1}  {2}' -f $p.DriveLetter, $d.BusType, $d.FriendlyName }
```

Your NVMe is probably `C:` (the drive Windows is on). Below, `D:` stands for
the 870 EVO and `E:` for the NVMe - **put your real letters in**.

**The medium model** (about 20 GB, onto the 870 EVO). One line; the files
land in `D:\models\qwen36_i4_gs64`:

```powershell
py -3 -m pip install -U "huggingface_hub[hf_transfer]"; $env:HF_HUB_ENABLE_HF_TRANSFER = "1"; hf download Kreuzzelg/qwen36-35b-a3b-colibri-i4-gs64 --local-dir D:\models\qwen36_i4_gs64
```

This is the "gs64" version colibri recommends (its README and
`docs/qwen36.md`, "Which container?").

**The giant model** (onto the NVMe). Either the full one, about 167 GB,
landing in `E:\models\DeepSeek-V4-Flash`:

```powershell
$env:HF_HUB_ENABLE_HF_TRANSFER = "1"; hf download deepseek-ai/DeepSeek-V4-Flash-0731 --local-dir E:\models\DeepSeek-V4-Flash
```

or the smaller "REAP 150B" one, about 85 GB (132 of its 256 experts kept;
colibri loads it the same way - `docs/deepseek-v4.md`), landing in
`E:\models\DeepSeek-V4-Flash-reap-150b`:

```powershell
$env:HF_HUB_ENABLE_HF_TRANSFER = "1"; hf download puwaer/DeepSeek-V4-Flash-0731-reap-150b --local-dir E:\models\DeepSeek-V4-Flash-reap-150b
```

If PowerShell says `hf` is not recognised, close it, open a new PowerShell
window and run the line again. (Not checked here: whether a new window is
always enough on your PC.)

colibri's `docs/deepseek-v4.md` warns that a download can end with a cut-off
file even when it says it finished. Check a model with colibri's own
read-only check (one line; it changes nothing):

```powershell
C:\colibri\coli.cmd doctor --model D:\models\qwen36_i4_gs64
```

---

## Step 3 - tell Jarvis where everything is

Open `jarvis-framework.toml` (in your Jarvis settings folder, usually
`C:\Users\<you>\.openjarvis\`) in Notepad. Your copy was made before this
feature, so the lines are not in it yet: add these at the end, with your real
folders and drive letters.

**Use single quotes around Windows folders** (`'D:\models\x'`). In double
quotes a backslash means something else, and the whole file then fails to
load.

```toml
[big_model]
coli_path = 'C:\colibri'
port = 8765
idle_minutes = 10
ctx = 16384
cuda = "off"
wiki_model = "qwen36"
deep_model = "dsv4-flash"

[[big_model.models]]
id = "qwen36"
name = "Qwen3.6-35B-A3B"
dir = 'D:\models\qwen36_i4_gs64'
kind = "medium"

[[big_model.models]]
id = "dsv4-flash"
name = "DeepSeek V4 Flash"
dir = 'E:\models\DeepSeek-V4-Flash'
kind = "giant"
```

And under `[autonomy.tiers]` (search for `wiki_update` and add the line
under it):

```toml
big_model_enable          = "ask"
```

It must be `"ask"`: anything else and the switches refuse to turn on at all.

What the settings mean: `port` is where colibri listens (on this PC only; not
11434 or 11435, which are the two Ollamas). `idle_minutes` is how long it
stays loaded after the last job. `ctx` is how much text the model is given
room for. `wiki_model` and `deep_model` pick a model by its `id` for each
job; left empty, the wiki takes the first medium model and deep questions the
first giant one. The shipped settings file (`backend/rebuilt/jarvis-framework.toml`,
section 9c) has every setting with a comment, including `giant_ram_gb`,
`deep_max_tokens`, `load_minutes` and `answer_minutes`.

Then run `apply-patches.ps1` as usual (it copies `jarvis_big_model.py` in
and applies `big-model.patch`) and restart Jarvis.

---

## Step 4 - switch it on

There is one main switch ("use the big model") and one switch per job. The
main switch goes first. Each ON raises one approval card that says which
model, how much memory and disk, that it listens on `127.0.0.1` only, and
that nothing leaves this PC. Turning a switch off is immediate and stops
colibri if nothing else needs it.

**On the desktop:** open Settings (right-click the Jarvis icon by the clock,
then Settings) and scroll to **"Big model (slow)"**, just under "Second
graphics card". It shows what Jarvis found, and one switch for the big model
itself, then one per job. Tick "Use the big model" first and approve the
card; then tick "Deep questions" (and/or "Wiki builder") and approve that
card too. The page shows "Waiting for your approval" until you do. The
switches stay greyed out, with the reason written above them, until Jarvis
has found colibri, Python, a model and enough memory and disk. Deep
questions are asked in the Brain window, Memory tab, "Deep questions".

**On the phone:** open Mind (the button on Home), then the "Big model
(slow)" section, under "Second graphics card". It shows what Jarvis found,
the main switch and one switch per job. Turning a switch on raises the
approval card; the switch says "Waiting for you to approve the card on your
PC or phone" until you answer it. Right below it, "Deep questions" has the
box to ask one ("Ask slowly") and the recent answers. The phone does not
notify you when an answer is ready; look in that list.

Without either app, in PowerShell, **in your Jarvis backend folder** (one
line each; the first reads your pairing token into `$t` without showing it):

```powershell
$t = (py -3 .\jarvis_token_store.py show); $h = @{ 'X-Jarvis-Token' = $t; 'X-Jarvis-Client' = 'hud' }; Invoke-RestMethod -Method Post -Uri http://127.0.0.1:4719/api/big-model -Headers $h -ContentType 'application/json' -Body '{"switch":"master","enabled":true}'
```

Approve the card. Then the same line with `"switch":"deep_questions"` (and/or
`"switch":"wiki"`) instead of `"master"`, and approve that card too. To see
what Jarvis found and why each switch is or is not working:

```powershell
$t = (py -3 .\jarvis_token_store.py show); $h = @{ 'X-Jarvis-Token' = $t; 'X-Jarvis-Client' = 'hud' }; (Invoke-RestMethod -Uri http://127.0.0.1:4719/api/big-model -Headers $h) | ConvertTo-Json -Depth 6
```

### Asking a deep question

**On the desktop:** right-click the Jarvis icon by the clock, choose "Open
the Brain", and stay on the **Memory** tab (it opens there). Under "Wiki" is
**"Deep questions"**: type the question and press **Ask slowly** (or
Ctrl+Enter). The list below shows each question with its state, and when it
is done, how long it took, the words a second and the answer. It updates by
itself when an answer is ready. The box only appears once the "Deep
questions" switch is on and working; until then the line above it says why.

Without the desktop app, in PowerShell:

```powershell
$t = (py -3 .\jarvis_token_store.py show); $h = @{ 'X-Jarvis-Token' = $t; 'X-Jarvis-Client' = 'hud' }; Invoke-RestMethod -Method Post -Uri http://127.0.0.1:4719/api/deep/ask -Headers $h -ContentType 'application/json' -Body (@{ question = 'Why is the sky blue?' } | ConvertTo-Json)
```

It answers at once with "queued"; the answer comes later. No approval card
per question, on purpose: you approved the switch, a question acts on
nothing (no tools, no memory changes, no internet), and nothing leaves this
PC. To read the answers:

```powershell
$t = (py -3 .\jarvis_token_store.py show); $h = @{ 'X-Jarvis-Token' = $t; 'X-Jarvis-Client' = 'hud' }; (Invoke-RestMethod -Uri http://127.0.0.1:4719/api/deep -Headers $h).jobs | Format-List state, question, answer, why
```

The state goes `queued` → `loading` (colibri starting, can take minutes) →
`thinking` → `done` (or `failed`, with the reason in `why`). At most three
questions can be waiting or running at once; they are answered one at a time.

**Where the answers are kept:** `deep-questions.jsonl` in your Jarvis settings
folder, on this PC - your own question and answer, like a chat you chose to
keep. The last 100 are kept; older ones drop off. Delete the file to forget
them all. Note the difference from chat: the apps keep chat history in memory
only and never write it to disk. These are written to disk because an answer
can take an hour and should survive a restart.

---

## How fast is it, really?

Every deep question records how long it took, how many tokens (pieces of
words) the model wrote, and tokens and words per second. The time includes
reading your question, so it is a little slower than colibri's "decode"
figures. To list them (the file is in your settings folder; this changes
nothing):

```powershell
Get-Content "$env:USERPROFILE\.openjarvis\deep-questions.jsonl" | ForEach-Object { $j = $_ | ConvertFrom-Json; '{0}  {1}  {2} tokens/s  {3} words/s  {4} s' -f $j.state, $j.model, $j.tokens_per_s, $j.words_per_s, $j.seconds }
```

The last measurement is also in `GET /api/big-model` under `measured`, and
the wiki's model calls are measured the same way while Jarvis runs.

For comparison, the only numbers colibri publishes are from other machines -
for example Qwen3.6 on "a CPU box" at 2.9 tokens a second (its README), and
DeepSeek V4 at 1.5-1.6 tokens a second with a 16 GB RTX 5080 and two NVMe
drives (its `docs/deepseek-v4.md`). Your PC has no such graphics-card setup
for colibri and one NVMe; expect less, and let the recorded numbers decide.

---

## What was not checked, said plainly

- **Nothing here has run on your PC.** colibri has not been started by Jarvis
  anywhere: the tests replace it with a stand-in that answers in colibri's
  documented shape. The first real run is yours.
- **None of colibri's speed claims** have been checked on your PC.
- **Whether the medium model fits** alongside everything else you run is not
  known until it runs: colibri says 24 GB; Jarvis checks that much is free
  before starting, and that is all it can check.
- **Whether the models write the wiki's JSON reliably.** colibri cannot force
  a model to answer in a set shape for these two models (its "grammar" feature
  is a speed trick that works only for GLM, and it refuses the request
  otherwise). Jarvis asks for the shape in words and checks the answer as
  strictly as before; a bad answer is refused and nothing is written. How
  often that happens is not known yet.
- **The drive-type check** (`Get-PhysicalDisk`) has not been run on your PC;
  if it cannot tell, the status line says so rather than guessing.
- **The ready-made download and Smart App Control**: not checked whether
  Windows blocks colibri's `.exe` files.
- **The graphics-card route**: not built or tried. See "The graphics card".
- **`big-model.patch`** has been rehearsed only against stand-ins built from
  the earlier patches; `apply-patches.ps1` on your PC is the real test.
