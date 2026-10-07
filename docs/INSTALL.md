# Installing Jarvis, start to finish

From a Windows 11 PC with nothing on it to a working, fully patched Jarvis,
in order. Nothing here is aspirational: where something does not work yet,
it says so and tells you what to do instead.

**How to use this page.** Every command is ONE line. Copy the whole line,
paste it into **PowerShell** (Start menu → type `PowerShell` → Enter), press
Enter, and wait for it to finish before the next one. Where a step says
"open a NEW PowerShell window", do that - a program you just installed is
only found by windows opened after it.

The short version of the backend part: install four programs, get two
folders, then **one script** (`scripts\apply-patches.ps1`) does everything
else - the patches, the modules, the settings file, the Python packages -
and tests the result.

---

## Quick start: the shortest way to a first chat

The fewest steps from a fresh Windows 11 PC to typing a question and getting
an answer, then pairing the phone. Voice, tools and notes are left out - add
them later from the full sections. Each step names the full section that
explains it, for when something does not go as written.

In every command, replace `<your backend folder>` with the folder that holds
`jarvis_hud.py` on your PC (keep the quotes around it).

**You type that path once, not every time.** Step 3 below runs a script that
tells this PC where the folder is; the live check and the test suites read it
from then on. The patch script still takes the path on its own command line,
so keep it there where you see it.

**On the PC**

1. **Install Git, Python and Ollama** (section 1.1). One line; the programs
   install into their usual places under Program Files and your user folder:

   ```powershell
   winget install --id Git.Git -e; winget install --id Python.Python.3.12 -e; winget install --id Ollama.Ollama -e
   ```

   Then close PowerShell and open a new one.

2. **Get this repository** (section 1.2). It lands in
   `C:\Users\<you>\Epic-Jarvis`, and PowerShell moves into it:

   ```powershell
   git clone https://github.com/darknight11ish/Epic-Jarvis.git "$env:USERPROFILE\Epic-Jarvis"; cd "$env:USERPROFILE\Epic-Jarvis"
   ```

3. **Have your backend folder ready** (section 1.3). It is published in this
   repository, as `jarvis-backend\`, so copying it into place and pointing this
   PC at it is two lines - or one command, `scripts\setup-jarvis.ps1`, which
   also patches it, deals with the model, installs the desktop app and checks
   the result. By hand, first tell this PC where the folder is: one line, it
   changes nothing inside the folder, and the live check and the test suites
   then find the folder by themselves (section 1.5 has this in full):

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\install-backend.ps1 -BackendPath "<your backend folder>"
   ```

   Then set it up with the one script (section 1.5). It changes
   only that folder, and saves everything it prints to
   `<your backend folder>\_jarvis-logs\apply-patches-<date>.txt`:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -BackendPath "<your backend folder>"
   ```

4. **Get the model** (section 1.7). About 5 GB, downloaded into Ollama's
   own models folder (`C:\Users\<you>\.ollama\models`). Then quit Ollama from
   its tray icon and start it again from the Start menu:

   ```powershell
   [Environment]::SetEnvironmentVariable('OLLAMA_KV_CACHE_TYPE', 'q8_0', 'User'); [Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE', '-1', 'User'); ollama pull qwen3:8b; ollama create jarvis-primary -f backend\jarvis-primary.Modelfile
   ```

5. **Build the desktop app** (section 2.1). First the build programs (one
   line, slow), then open a NEW PowerShell window and build it (one line).
   The installer lands in
   `C:\Users\<you>\Epic-Jarvis\jarvis-desktop\src-tauri\target\release\bundle\nsis\`:

   ```powershell
   winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"; winget install --id Rustlang.Rustup -e; winget install --id OpenJS.NodeJS.LTS -e
   ```

   ```powershell
   cd "$env:USERPROFILE\Epic-Jarvis\jarvis-desktop"; npm install; npm run tauri build
   ```

   Double-click the `-setup.exe` in that folder. Windows says it "protected
   your PC": click **More info**, then **Run anyway** (section 2.2).

6. **Let the desktop app start Jarvis for you** - no PowerShell window to
   keep open (section 2.5). In Jarvis Desktop: tray icon → **Settings and
   help…** → **More options** (the closed box near the end) → **Starting
   Jarvis for you**:
   - **Program**: press **Find it for me**.
   - **Arguments**: `<your backend folder>\jarvis_hud.py`
   - Switch on **Let Jarvis Desktop start and stop Jarvis**, press **Save**,
     then **Start**.

7. **Your first chat.** Press `Alt+Space` (or tray icon → **Show or hide the
   Jarvis bar**, if another program took that key), type `hello`, and press
   Enter. An answer means the whole chain works.

8. **Check everything at once** (section 1.10), from the repository folder.
   It changes nothing, and saves its result as `preflight.txt` on your
   Desktop:

   ```powershell
   cd "$env:USERPROFILE\Epic-Jarvis"; $env:JARVIS_BACKEND = "<your backend folder>"; $env:PYTHONIOENCODING = "utf-8"; py -3 backend\selftest.py --preflight | Tee-Object -FilePath "$env:USERPROFILE\Desktop\preflight.txt"; Write-Host "Saved to $env:USERPROFILE\Desktop\preflight.txt"
   ```

**The phone** (Part 3). It reaches the PC only through **Tailscale** or
**NordVPN Meshnet**, at home too. Tailscale is shown here.

9. **Tailscale on both** (section 3.1). On the PC, one line (it installs
   into Program Files), then open Tailscale from the Start menu and sign in.
   On the phone, install Tailscale from the Play Store, sign in with the
   same account, and switch it on:

   ```powershell
   winget install --id Tailscale.Tailscale -e
   ```

10. **Let the phone in** (section 3.2). In Jarvis Desktop, Settings →
    **Connection** → **Let my phone reach this**: type the PC's Tailscale
    address (it starts with `100.`; the Tailscale app shows it), press
    **Save**, then in **Starting Jarvis for you** press **Stop** and
    **Start**. Then one line in PowerShell **opened as administrator**
    (right-click PowerShell → Run as administrator); it adds one Windows
    Firewall rule and writes no file:

    ```powershell
    New-NetFirewallRule -DisplayName "Jarvis backend (private mesh only)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 4719 -RemoteAddress 100.64.0.0/10 -Profile Any
    ```

11. **Install the app and pair** (section 3.3). Install the APK from the
    [`client-latest` release](https://github.com/darknight11ish/Epic-Jarvis/releases/tag/client-latest).
    On the pairing screen, type the PC's Tailscale **name** (it ends in
    `.ts.net`), then the token from Jarvis Desktop's Settings →
    **Connection** → **Show the token for my phone**. Spaces do not matter.
    **Show token** under the box shows what you typed, to check it.

12. **If the phone does not connect**, run step 8's line again: its "Can your
    phone reach Jarvis?" lines check the phone address, Tailscale on the PC,
    Jarvis listening for the phone, and the firewall rule, and each says
    what to do. The phone itself says "Tailscale (or Meshnet) is off on this
    phone" when that is the problem. Section 3.4 has the rest.

After a restart of the PC, Jarvis starts again when Jarvis Desktop does; to
have Jarvis Desktop start with Windows, switch on **Start Jarvis Desktop
when Windows starts** (Settings → More options → Startup and logs).

---

## What you are installing

Three things, and it is worth knowing which is which, because when something
breaks the error usually names the wrong one.

| | what it is | who starts it |
|---|---|---|
| **The backend** | `jarvis_hud.py` — a Python program. This *is* Jarvis: the model, the memory, the approval queue. | you, or the desktop app |
| **Jarvis Desktop** | the Windows app: the Jarvis bar (Alt+Space), the tray icon, the widget, the Brain. A **client**. | you |
| **The phone app** | `jarvis-client`. Also a client. | you |

Both clients are windows onto the backend. If the backend is not running,
both are offline and neither can do anything about it on its own.

Two folders, and they are different:

- **This repository** (the code on GitHub) - the patches, the modules, the
  scripts, the apps. Step 1.2 puts it at `C:\Users\<you>\Epic-Jarvis`.
- **Your backend folder** - where `jarvis_hud.py` lives, on your PC only.
  The owner's is
  `C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program`.
  The commands below use that path; change it if yours is elsewhere.

---

## Part 1 — The backend

### 1.1 Install the programs

Git (to get this repository), Python (runs the backend) and Ollama (runs the
model on your graphics card). One line:

```powershell
winget install --id Git.Git -e; winget install --id Python.Python.3.12 -e; winget install --id Ollama.Ollama -e
```

Then **close PowerShell and open a new one**, and check all three are found:

```powershell
git --version; py -3 --version; ollama --version
```

Three version numbers means you are done. **Do not use the word `python` on
its own** to run anything: on a fresh Windows 11, `python` is a Microsoft
Store shortcut that is not Python at all - it opens the Store, or prints
"Python was not found", and a program started with it looks started while
nothing is running. `py -3` is the real one. The scripts here know this and
use `py -3` themselves.

### 1.2 Get this repository

One line. It lands in `C:\Users\<you>\Epic-Jarvis`, and the second half moves
PowerShell into that folder:

```powershell
git clone https://github.com/darknight11ish/Epic-Jarvis.git "$env:USERPROFILE\Epic-Jarvis"; cd "$env:USERPROFILE\Epic-Jarvis"
```

If the repository is private, Git opens a browser window to sign in to
GitHub first. **Run every command below from this folder** - each one names
files relative to it. To get back here in a new window:
`cd "$env:USERPROFILE\Epic-Jarvis"`. To update it later: `git pull`.

### 1.3 Get the backend files

**This is now a copy, not a search.** The Python program that does the work —
`jarvis_hud.py` and the 180 files beside it — is published in this repository,
in [`jarvis-backend/`](../jarvis-backend/README.md), as plain source under the
same licence as everything else here. Step 1.2's clone already fetched it.

Copy it to a folder of your own, because the next steps write into it and a git
clone is a bad place for a program that rewrites itself:

```powershell
Copy-Item -Recurse -Force .\jarvis-backend "$env:USERPROFILE\Documents\jarvis-backend"
```

**Wherever this page says "your backend folder", use
`C:\Users\<you>\Documents\jarvis-backend`.**

**If you are the author**, this section is not for you. Your backend is the
folder you have always used, and the patches in `backend\` are written against
it; keep using its path in the steps below.

**Why this took until 2026-10-06.** The backend existed in exactly one place on
Earth — the author's PC. Searching for a public copy found two unrelated things
(`open-jarvis/OpenJarvis` keeps its code under `src/openjarvis/` with no flat
`jarvis_*.py` at all, and `Twsman1/JARVIS`'s `jarvis_hud.py` is a wake-word
overlay, not an HTTP server), and fifteen modules — `jarvis_hud.py`,
`jarvis_gate.py`, `jarvis_extract.py`, `jarvis_models.py`, `jarvis_skills.py`
and ten others — had no copy anywhere. They were produced in assistant
conversations and saved to disk, which made those conversations their only
origin. `jarvis-backend/README.md` says where the published copy came from and
what it deliberately leaves out.

Ten modules that were lost *have* been rebuilt, and live in this repository
(`backend\rebuilt\`), along with every newer module. You do not copy those by
hand: step 1.5 does, and the published folder already has them.

**Or let one command do the whole first part.** From the folder you downloaded
this into:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-jarvis.ps1
```

It copies the published folder into place, runs 1.5's two scripts, says whether
Ollama and Jarvis's model are ready, installs the desktop app (part 2, by
calling `scripts\update-jarvis.ps1`), starts the backend, and runs the live
check. Two honest limits, both by design: it **prints** 1.7's model command
rather than downloading about 5 GB for you, and if the model is missing it stops
before starting an assistant that cannot answer. Add `-Print` to see every
command it would run while changing nothing, `-SkipTests` to skip the suite run,
`-BackendPath` to put the folder somewhere else, or `-SkipDesktop` to leave the
desktop app alone.

### 1.4 Check the backend folder

One line. It reads every file in your backend folder, works out which
modules they need, and says which are there. It changes nothing.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-backend.ps1 -BackendPath "$env:USERPROFILE\Documents\jarvis-backend"
```

(`-ExecutionPolicy Bypass` lets Windows run this one script file without
changing any setting. Without it, Windows refuses script files by default.)

- **`ok`** - there.
- **`not yet`** - this repository ships it; step 1.5 copies it in. On the
  published folder from 1.3 there should be none of these.
- **`MISSING`** - not there, and this repository does not have it either.
  Find it before going on (the list is most-needed first, and one missing
  file hides the others). It lists the files that need each one.

### 1.5 Tell this PC where the backend is, then run the one script

**First, one line that retires the path.** Almost every command in this
project needs to know which folder your backend is in, and this writes it
down once, for your Windows account:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-backend.ps1 -BackendPath "$env:USERPROFILE\Documents\jarvis-backend"
```

(That is the folder you made in 1.3. If you are the author it is your own
backend folder instead — **replace the path with yours**, the folder holding
`jarvis_hud.py`. Every command on this page with that path in it needs the same
replacement.)

It checks the folder really is a backend folder (it must hold
`jarvis_hud.py`) **before** it changes anything, so a wrong path cannot be
half-installed. It looks at file **names** in that folder and nothing else:
it never opens a file, and the only thing it changes anywhere is that one
setting. It prints exactly what it changed and how to undo it. Add `-Print`
to see what it would do without doing it. Safe to run twice, and again if
you move the folder.

If it says the folder has no `jarvis_hud.py`, fix that first - step 1.3 says
where those files come from. **Open a NEW PowerShell window** afterwards, so
the new setting is picked up.

**Then the script that does the work.** One line:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -BackendPath "$env:USERPROFILE\Documents\jarvis-backend"
```

**On the published folder this script changes nothing, and that is the correct
result.** Run against a copy of `jarvis-backend/` on 2026-10-06 it exited 0,
left `jarvis_hud.py`'s SHA-256 identical, and reported `Checked again on the
real files: all 120 patches are on` and `All 160 modules this repository ships
are there and up to date`: the published folder is the state *after* the
patches, so a fresh copy never needs them applied. It still does its other
work — the Python packages, the settings file, and the test suites.

(If it stops and says a Jarvis program is running, close Jarvis first —
right-click the tray icon and choose "Stop the backend" — then run the line
again. `-Force` skips that check; only use it when you know the folder is not
in use.)

**Keep `-BackendPath` on this one, with your own folder in it.** The setting
you just saved is read by the live check and the test suites; this script
still has a folder of its own written into it, and if you leave the parameter
out it uses that one. (Making it read the saved setting too is a change to
the patch script itself - the one script on this page that is allowed to
alter your backend - so it is written down here rather than done quietly:
**not done yet**.)

In order, it:

1. **Rehearses** every patch on a throwaway copy of your files. If any would
   not apply, it stops, prints why, and says **NOTHING HAS BEEN CHANGED** -
   true: your folder was never opened. Send that output back.
2. **Backs up** every file it is about to change, into a
   `_jarvis-backup-<date>` folder inside your backend folder, then applies
   the patches. Among them: the pairing token, `127.0.0.1` staying reachable
   when the phone is paired, chat actually reaching Ollama, nothing ever
   approved without you, and private content never leaving the PC.
3. **Copies in every module this repository ships** - the ten rebuilt ones,
   the tools, and the new modules the patches call - backing up any older
   copy first.
4. **The settings file** (`jarvis-framework.toml`): if you have none, it
   puts this repository's copy beside `jarvis_hud.py`. **If you have one, it
   is never overwritten** - the script lists, setting by setting, how yours
   differs from this repository's, for you to decide on.
5. **Installs the Python packages** in `backend\requirements.txt` (memory
   search by meaning, the voice features). A minute or two the first time.
6. **Runs the test suites** against your backend and prints a summary.

**Everything it prints is also saved**, one file per run, in a
`_jarvis-logs` folder inside your backend folder
(`_jarvis-logs\apply-patches-<date>.txt`); the `Log` line near the top of
what it prints gives the exact file. Send that file back if a run goes
wrong - no token or key is ever printed by the script.

It is safe to run again - after a `git pull`, run the same line. It works out
what is already done and does the rest.

**Update the desktop app at the same time** (build and install it again,
Part 2). The first time the patched backend starts, it moves its pairing
token out of the old plain-text file into Windows Credential Manager and
deletes the file. A desktop app built before 2026-09-24 only knows that old
file, so it would be locked out of its own backend until it is updated.

**If you ran this script before, it will recognise the older patches and
replace them.** Some patches were changed after they were first published.
The script keeps every earlier version (in `backend\patch-history`), finds
which one your backend has, takes it off and puts the current one on -
rehearsed on a copy first like everything else. It prints a line starting
`older` for each one it replaces, so you can see what happened.

**If it ends with failures**, send back what it printed. A failing suite
here is a real finding: CI runs the suites too, but the ones that test a
patch against *your* `jarvis_hud.py` can only run on your PC.

### 1.6 The settings file, and turning tools on

`jarvis-framework.toml` holds the decisions only you make: which actions ask
you first (`[autonomy.tiers]`), and which tools the model may use. The
backend looks for it in this order and uses the first it finds:

1. the file named by the `JARVIS_FRAMEWORK_TOML` environment variable, if set;
2. `C:\Users\<you>\.openjarvis\jarvis-framework.toml`;
3. beside `jarvis_hud.py` in your backend folder (where step 1.5 puts one);
4. the folder above that.

**Tools are off until you name them - except web search.** Step 1.5 copies
in the tool modules (checking GitHub for an existing library, reading and
clicking other windows, the phone over adb, a browser, calendar, email,
notes, Home Assistant), but the model is offered a tool only if the
`enabled` list under `[tools]` names it - and every action a tool takes
still goes through the approval gate. This repository's copy of the file
ends with:

```toml
[tools]
enabled = ["web_search"]
```

so a PC set up from it can search the web and nothing else (the owner's
decision of 2026-09-27, "web search ships switched on"). **If your settings
file is older than that, it has no `[tools]` section at all**, so every
tool is off, web search included, until you add one.

To turn another tool on, add its name **inside that same list** (the names
are the tools' names in `backend\jarvis_agent.py`), for example
`enabled = ["web_search", "calculator"]`. If your file has no `[tools]`
line yet, add both lines above at the end of it. **Do not add a second
`[tools]` line** to a file that already has one: a settings file with the
same heading twice cannot be read at all.

The four reading tools (calendar, email, notes and home status) can also be
switched on from the desktop app instead of this file: Settings, **What asks
first**, "Offer this to the AI model" - one approval card plus Windows Hello
each. `backend\README.md` has a section per tool saying what it needs set up
first and which approval tier it asks under. Restart the backend after
editing the file.

### 1.7 The model

One time. The first two lines are settings Ollama reads at start-up (a
Modelfile cannot hold them); the rest downloads the base model (about 5 GB)
and builds Jarvis's tuned copy of it from `backend\jarvis-primary.Modelfile`:

```powershell
[Environment]::SetEnvironmentVariable('OLLAMA_KV_CACHE_TYPE', 'q8_0', 'User'); [Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE', '-1', 'User'); ollama pull qwen3:8b; ollama create jarvis-primary -f backend\jarvis-primary.Modelfile
```

Then quit Ollama from its tray icon and start it again, so it reads the two
settings. [`MODEL-TOPOLOGY.md`](MODEL-TOPOLOGY.md) says why this model and
these numbers, and how to check it is really running on the graphics card
and not spilling into system memory (which makes everything about five times
slower with no warning).

**Another graphics card, or a different one?** Once the desktop app is
running (Part 2), open Settings, **Hardware and models**. It lists your
cards and offers three setups worked out for them (fastest answers,
smartest answers, most features), each with its own one-line command.
Nothing changes until you pick one, and each step then asks you with its
own approval card. Its **Measure** button checks that the model really is
all on the graphics card.

**Voice (optional).** Talking to Jarvis needs model files downloaded onto the
PC as well. `backend\README.md`, section **"Voice that works"**, has the
steps.

### 1.8 Start it

One line (change the path if your backend folder is elsewhere):

```powershell
cd "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; $env:HF_HUB_DISABLE_TELEMETRY = "1"; $env:DO_NOT_TRACK = "1"; $env:ANONYMIZED_TELEMETRY = "False"; py -3 jarvis_hud.py
```

The three `$env:` settings in the middle tell the libraries Jarvis uses (the
model downloader, and tools that honour the shared "do not track" switch) not
to report anything about your use. Jarvis also sets them itself once it is
running; putting them in the start line makes sure they are on before any
library loads. (Supply-chain audit, 2026-09-30. They cover those three names
only - `docs/ARCHITECTURE.md` says which telemetry is not covered.)

Read what it prints at the top. Three lines matter:

- A `token` line saying `in Windows Credential Manager` - the pairing token
  was made and saved (step 1.5 applied the patches that do it). If it says
  `NOT SAVED` or `STILL IN THE OLD PLAIN-TEXT FILE` instead, the lines under
  it say why. If it says `token NONE - jarvis_token_store.py is missing from
  this folder`, that file was not copied in; run step 1.5 again. No token
  line at all - or one that only shows a file path ending in
  `.openjarvis\token` - means `token-store.patch` is not applied yet; run
  step 1.5 again and read what it says about that patch.
- `routing off - jarvis_router.py / jarvis_recall.py not found` — **this
  message names the wrong file.** It prints both names whichever is missing.
  Check which one you actually lack.
- If the memory block is missing entirely, one of the memory modules failed
  to import and Jarvis has no memory. The banner does not say so.

Leave this window open. Everything it prints goes here and nowhere else.

The browser page at `http://localhost:4719/` needs `jarvis_hud.html` beside
`jarvis_hud.py`. The desktop app does not: it carries its own copy. If you
want the browser page, copy `jarvis-desktop\src\jarvis_hud.html` into your
backend folder; without it that address returns an error (a 500) while
everything else works.

**After every restart of the PC, Jarvis is off again** until you run this
line again - or until the desktop app starts it for you (step 2.5, "Let
Jarvis Desktop start and stop Jarvis", together with "Start Jarvis Desktop
when Windows starts").

### 1.9 Keep the PC awake

**Alarms, reminders and "tell me when" go off on the PC, by the PC's clock.**
While Windows has the PC asleep, nothing goes off, and the phone cannot reach
Jarvis either; when the PC wakes, anything that was due goes off once and
says when it was missed (backend/README.md, "Timers, alarms, reminders").

To keep the PC awake while it is plugged in, one line in PowerShell (the
screen can still turn itself off; this changes only the sleep timer on mains
power, and writes no file):

```powershell
powercfg /change standby-timeout-ac 0
```

To undo it, the same line with a number of minutes instead of `0`, or
Windows Settings → System → Power → Screen and sleep. The live check
(below) warns when the PC sleeps on mains power.

### 1.10 Check that it all works

With Jarvis running, open a **second** PowerShell window in this
repository's folder (`cd "$env:USERPROFILE\Epic-Jarvis"`) and run this one
line, with your backend folder - the one holding `jarvis_hud.py` - between
the first quotes. It checks the running Jarvis end to end and ends with
"N pass, N fail, N warn"; the result is also saved as `preflight.txt` on
your Desktop:

```powershell
$env:JARVIS_BACKEND = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; $env:PYTHONIOENCODING = "utf-8"; py -3 backend\selftest.py --preflight | Tee-Object -FilePath "$env:USERPROFILE\Desktop\preflight.txt"; Write-Host "Saved to $env:USERPROFILE\Desktop\preflight.txt"
```

It changes nothing. Each FAIL says what to do. If it says `jarvis_hud.py is
not in ...`, the folder between the first quotes is not your backend
folder.

---

## Part 2 — The desktop app

### 2.1 Build it

It is built on your PC; there is no download yet. That needs three more
programs - Microsoft's C++ build tools, Rust and Node.js. One line (the build
tools are large, and the line takes a while):

```powershell
winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"; winget install --id Rustlang.Rustup -e; winget install --id OpenJS.NodeJS.LTS -e
```

Open a NEW PowerShell window, then (one line):

```powershell
cd "$env:USERPROFILE\Epic-Jarvis\jarvis-desktop"; npm install; npm run tauri build
```

The installers land in `jarvis-desktop\src-tauri\target\release\bundle\` —
`nsis\*-setup.exe` and `msi\*.msi`. Use the NSIS one.

**You only build by hand until the update signing key exists.** After that,
GitHub builds the installer and it appears on the Releases page - see "The
desktop installer, and the update signing key", later in this page (about ten
minutes of setup). Nothing above stops working; there is just no longer a
reason to do it.

### 2.2 Get past SmartScreen

The app is **not code-signed**. There is no way around this that does not cost
money, and paying for an EV certificate no longer buys instant reputation —
Microsoft removed that in 2024. So:

1. If your browser blocks the download: ⋮ → **Keep** → **Keep anyway**.
2. Double-click the installer. A blue dialog says *"Windows protected your PC"*.
   The only button is **Don't run**.
3. Click **More info** — the small link, easy to miss.
4. Click **Run anyway**.
5. The installer runs. No UAC prompt: it installs for you only, into
   `%LOCALAPPDATA%`, which is where all its settings live anyway.

### 2.3 What you will actually see on first launch

The README used to say the app has no window at startup. **It does.** Expect:

- a **1280×820 HUD window**, centred and focused;
- a small **320×44 glass pill** at the top-left — the widget, always on top;
- a **tray icon**, which on Windows 11 starts hidden in the `^` overflow.
  Drag it onto the taskbar now. You will need it.
- the first time only, a small **Welcome** window: three short screens (the
  tray icon, approval cards, and what Jarvis remembers). Press **Next** to
  go through them, or Esc to close it. It comes back once whenever a later
  version of the app changes what it says.

If the HUD window says **"demo · not connected"** with a banner telling you to
run `py -3 jarvis_hud.py`, the desktop app could not reach Jarvis: the HUD's
requests go through the desktop app (since 2026-09-25), to the address in
Settings → Connection. Check that Jarvis is running (Part 1, step 1.8) and
that address (step 2.5). The HUD checks only when it opens, and closing its
window only hides it, so then quit Jarvis Desktop (tray icon → **Quit
Jarvis**) and start it again from the Start menu. (This page
used to say the banner could be ignored because the HUD did not know the
desktop app existed; that stopped being true on 2026-09-25.) The tray and
the Jarvis bar tell you the same thing in plainer words.

### 2.4 The hotkeys, which may not work

Seven are registered at startup:

| key | what it does |
|---|---|
| `Alt+Space` | show or hide the Jarvis bar |
| `Win+Shift+J` | attach what is on the clipboard |
| `Alt+Shift+S` | attach a screen capture |
| `Alt+Shift+N` | quick note |
| `Alt+Shift+W` | show or hide the widget |
| `Alt+Shift+F` | show or hide the floating face |
| `Alt+Shift+X` | **Stop everything** - Jarvis stops talking and stops anything it is doing on the screen or the phone, at once |

**`Alt+Space` is the most contested key on
Windows 11** — PowerToys Run and the Copilot app both claim it, both start at
login, and Jarvis starts after them, so Jarvis loses.

If a key was refused you get a toast saying so. If the toast fails you get
nothing at all, because release builds have no console.

**The fallback, worth memorising now:** right-click the tray icon → **Settings and help…**
→ **Shortcuts**. Every binding is editable and each shows whether Windows
accepted it.

`Alt+Shift+S/N/W/X/F` clash with the Windows keyboard-layout switch if you have
two or more layouts installed. Stop everything is also in the tray menu, so
it still works if its key was refused.

### 2.5 Point it at the backend

Tray → **Settings and help…** → **Connection**.

- Leave **Jarvis's address on this computer** at `http://127.0.0.1:4719`.
- **Letting the app start Jarvis for you** is under **More options** (the
  closed box near the end of Settings) → **Starting Jarvis for you** →
  **Let Jarvis Desktop start and stop Jarvis**. It is off by default and
  that is deliberate: with it on, the app starts Jarvis when it opens and
  stops it when it quits. A Jarvis you started yourself in PowerShell is
  never taken over and never stopped. Its **Start** button is greyed out
  until this switch is on.
- If you do turn it on, set **Program** to the full path of the real
  `python.exe` — not `python`, which may be the Store shortcut from step 1.1.
  The **Find it for me** button under the box searches this PC for a working
  Python and fills the box in (it saves nothing; check it and press **Save**).
  Or this one line prints it:
  `py -3 -c "import sys; print(sys.executable)"` (typically
  `C:\Users\<you>\AppData\Local\Programs\Python\Python312\python.exe`).
  Set **Arguments** to the full path of `jarvis_hud.py`.
- **Start Jarvis Desktop when Windows starts** (More options → Startup and
  logs) starts the app, not Jarvis. Jarvis starts with it only when "Let
  Jarvis Desktop start and stop Jarvis" is on too.

**Know the trade:** with that switch on, quitting Jarvis Desktop also stops
Jarvis, and therefore stops the phone from reaching anything.

**What it does if Jarvis crashes.** With that switch on, the desktop app
checks every 15 seconds on the Jarvis it started. If Jarvis has crashed, or
has not answered for about 45 seconds, the app restarts it - at most 3 times
in 10 minutes. After that it stops trying and shows one notification saying
so; see "When something goes wrong", below, for what to do then. A Jarvis
you started yourself in PowerShell is never watched or restarted.

### 2.6 Set up Windows Hello (a PIN is enough)

Risky approvals - sending an email, restoring a backup, loosening what asks
first - need Windows to confirm it is you, and **on a PC without Windows
Hello they are refused**, with a message saying so. If you do not already
sign in to Windows with a PIN, fingerprint or face: Windows Settings →
**Accounts** → **Sign-in options** → **PIN (Windows Hello)** → Set up. The
desktop app's Settings → **Security** shows whether this PC has it.

---

## Jarvis learns from your conversations, and it is on

Worth knowing before you use it rather than after.

About 45 seconds after a conversation goes quiet, Jarvis re-reads **what you
typed or said** — never its own replies, never anything a tool returned — and asks the
local model which of it would still be true and useful next month.

**Facts from your own words are saved straight away** ("Learn automatically",
on by default) - never from emails, web pages, documents or files. Every one
is listed under "Saved automatically" in the Memory tab of the Brain window,
with a Forget button. **Health, money, passwords and other people's private
details wait for your yes**, one at a time, in the same tab, unless you turn
on "Also remember sensitive topics automatically" (off by default). Anything
Jarvis is not sure came from you waits for your yes too. The Memory tab is
also where you can reword a fact, stop one being recalled, or copy the lot
out as JSON.

It never leaves the machine: the extractor talks to Ollama on loopback and
refuses to run at all if `OLLAMA_URL` points anywhere else.

To turn it off: the switch is in that same Memory tab. To turn it off before
Jarvis has ever started, set `JARVIS_EXTRACT=0` — that is a floor the in-app
switch cannot lift.

---

## Notes: Logseq, Joplin and Obsidian

Jarvis can file a note you type straight into a notes app on this PC:
`#log` for today's Logseq journal, `#joplin` (or `#jop`) for a new Joplin
note, `#obs` for today's Obsidian daily note. On the phone it is Home →
**Quick note…**. No model is involved: what you typed is what gets written,
and nothing leaves the PC.

**Only the apps that are set up on the PC are shown** — in the quickbar's
help, on the widget, and on the phone. If you type a prefix for one that is
not set up, Jarvis says "Obsidian isn't set up on your PC" (or Logseq, or
Joplin) and files nothing. If the desktop or phone cannot ask the PC which
apps are set up, it shows none, and says why.

What "set up" means for each:

- **Logseq**: the graph folder exists — `[notes.logseq] graph_directory` in
  `jarvis-framework.toml` (or the `JARVIS_LOGSEQ_GRAPH` environment variable).
- **Joplin**: Joplin's Web Clipper token (Joplin: Tools → Options → Web
  Clipper) is in an environment variable Jarvis can read:
  `JARVIS_JOPLIN_TOKEN`, or else the one named by `[notes.joplin] token_env`
  in `jarvis-framework.toml` (that is `JOPLIN_TOKEN` unless you changed it).
  Filing notes and the notes search both look in the same two places.
  Joplin also has to be open when you file.
- **Obsidian**: the vault folder is set, below.

### Obsidian

Jarvis reads and writes your vault as a plain folder of files. It needs no
Obsidian plugin and no API key.

1. **Find your vault folder.** It is the folder that has a hidden
   `.obsidian` folder inside it. In Obsidian: click the vault name at the
   bottom left → **Manage vaults**; the path is shown under each vault's name.
2. **Tell Jarvis where it is.** Open your `jarvis-framework.toml` (step 1.6
   says where it is) in Notepad and add, or fill in:
   ```toml
   [notes.obsidian]
   vault_directory = 'C:\Users\you\Documents\MyVault'
   ```
   Use single quotes, so the backslashes are kept as they are. The folder
   must already exist; Jarvis never creates a vault.
3. **Let `#obs` save straight away.** In the same file, under
   `[autonomy.tiers]`, add:
   ```toml
   append_obsidian_daily     = "auto"
   ```
   This repository's copy already has that line; yours is left alone, so
   `apply-patches.ps1` prints it as a difference instead. Without it, every
   `#obs` note waits for you to approve it first. Put `"ask"` there if that
   is what you want. (A note Jarvis writes **from chat** after it has read
   an email, a web page, a file or other outside text - or after you pasted
   or shared something - always asks first, whatever this line says. That
   is `write_notes_after_outside_text = "ask"`; a file without that line
   asks anyway.)
4. **Turn on Daily notes in Obsidian.** Settings (the gear, bottom left) →
   **Core plugins** → switch on **Daily notes**. Its options (Settings →
   **Daily notes**) decide where today's note is:
   - **New file location**: the folder. Empty means the top of the vault.
   - **Date format**: the file name. Leave it as `YYYY-MM-DD`. Jarvis also
     follows `YYYY/MM/YYYY-MM-DD`-style formats that make a folder per year or
     month, and words in square brackets like `[Journal]`. It will **not**
     guess formats with month or day *names* (`MMMM`, `dddd`) or week numbers:
     it refuses and tells you which part it could not follow.
   - **Template**: when Obsidian makes today's note, it uses your template.
     When Jarvis makes it (because you filed a note before opening today's
     note), the file holds just your note; the template is not applied.
   If the Periodic Notes community plugin is on and handles daily notes,
   Jarvis refuses rather than guess, because that plugin can name the note
   instead.
5. **Restart the backend.** Then open the quickbar: its help should now list
   `#obs`. Type `#obs call the plumber` and press Enter; it should say
   "Filed in Obsidian, 2026-09-24.md" (with today's date). The note is added
   at the **end** of today's note, after a blank line; nothing already in the
   file is changed.

**Searching the vault.** When a vault is set, Jarvis's notes search (the
`notes_search` tool, which is off until you add it to `[tools].enabled`,
step 1.6) reads the vault's `.md` files directly. It skips the `.obsidian`
and `.trash` folders, and anything linked from outside the vault, and it
stops after 5,000 files or 5 seconds so a big vault cannot hold up an
answer. What it finds goes only to the local model on this PC. If you also
use Joplin for search, the vault wins; set the environment variable
`JARVIS_NOTES_BACKEND=joplin` to search Joplin instead.

### Your vault on your phone, with Syncthing

Jarvis does nothing with Syncthing; this is only how to get the same vault
onto your phone. Syncthing copies a folder between your own devices,
directly, with no account.

**On the PC (Windows):**

1. Download the Windows zip from Syncthing's releases page
   (`https://github.com/syncthing/syncthing/releases/latest`, the file named
   `syncthing-windows-amd64-v….zip`), unzip it, and double-click `syncthing.exe`. The
   first time, it opens its control page in your browser at
   `http://127.0.0.1:8384`; that page is where Syncthing is controlled. It
   syncs only while it is running; Syncthing's own documentation
   ("Starting Syncthing Automatically") shows how to start it with Windows.
2. Click **Add Folder**. For **Folder Path**, give your vault folder (the one
   from step 1 above). Give it a label such as `Obsidian`. Save.
3. Click **Actions** (top right) → **Show ID**. Leave that showing; the
   phone needs it.

**On the phone (Android):**

4. Install **Syncthing-Fork** (from F-Droid, or its GitHub releases page:
   `https://github.com/researchxxl/syncthing-android/releases`). The original
   Syncthing Android app is discontinued; Syncthing-Fork is the maintained one.
5. Open it, allow what it asks for (it needs file access to write the vault).
6. **Devices** tab → **+** → scan the QR code the PC is showing (or type the
   ID). Save.
7. On the PC, a message appears asking to add the phone. Click **Add
   Device**, and on the **Sharing** tab tick the `Obsidian` folder. Save.
8. On the phone, accept the `Obsidian` folder when it is offered, and choose
   where it goes (for example a new folder `Obsidian` in the phone's storage).
9. Install Obsidian on the phone, choose **Open folder as vault**, and pick
   that folder.

Two things worth knowing:

- If you edit today's note on the phone at the same moment Jarvis adds to it
  on the PC, Syncthing keeps both, and names one of them
  `...sync-conflict-....md`. Nothing is lost, but you merge them by hand.
- Syncthing encrypts everything between your devices. By default, when the
  two cannot reach each other directly, it may pass that encrypted traffic
  through a public relay server. To keep it on your own network only: in
  the PC's Syncthing page, **Actions → Settings → Connections**, untick
  **Enable Relaying** and **Global Discovery** (and do the same on the
  phone). The two then only find each other on the same network, or over
  Tailscale if you type the other's Tailscale address into the device.

---

## Part 3 — The phone

**Read this part before you start it.**

### 3.1 What works

A private network between your own devices: **Tailscale** (both devices on the
same tailnet, with MagicDNS on) or **NordVPN Meshnet** (both devices on your
Meshnet). The owner's setup uses Meshnet, with names like
`my-pc.nord`. A private mesh between two devices you own is not a
public tunnel; nothing is exposed to the internet.

**You need one even at home, on the same Wi-Fi.** The phone app can only
reach the PC by its Tailscale name (ending in `.ts.net`) or its Meshnet name
(ending in `.nord`): Android lets this app use plain `http://` only to those
names (`jarvis-client/app/src/main/res/xml/network_security_config.xml`),
so a home-network address such as `192.168.1.20`, a name ending in
`.local`, or the PC's `100.x` number does not work from the phone, even
though it is on your own network. The phone says so as soon as you pair,
in one sentence, and tells you to type the name instead - the Tailscale or
NordVPN app shows it. (Jarvis on the PC does not listen on your home Wi-Fi
anyway, only on its Tailscale or Meshnet address; `docs/ARCHITECTURE.md`
section 2, "Which addresses the phone can use", has the reasons.)

**Tailscale, step by step** (Meshnet works the same way, in the NordVPN app):

1. **On the PC**, one line in PowerShell, then open **Tailscale** from the
   Start menu and sign in (a Google, Microsoft or GitHub account; the free
   plan is enough):

   ```powershell
   winget install --id Tailscale.Tailscale -e
   ```

2. **On the phone**, install **Tailscale** from the Play Store, open it,
   sign in with the **same** account, and switch it on.
3. In a browser, open Tailscale's admin page, **DNS**
   (`https://login.tailscale.com/admin/dns`), and check **MagicDNS** is on -
   that is what gives the PC a name.
4. **The PC's name** is in the admin page's **Machines** list. It ends in
   `.ts.net`, for example `desktop.tail1234.ts.net`. That name, followed by
   `:4719`, is what the phone's Pairing screen asks for (step 3.3).
5. Then step 3.2 below: the PC side, which lets the phone in.

Both devices must be signed in and switched on in Tailscale whenever the
phone talks to Jarvis - at home too.

### 3.2 Reaching a supervised backend from the phone

**Fixed 2026-09-16.** The desktop app used to never tell a backend it started
to listen anywhere but loopback — it passed three environment variables to a
supervised backend and the bind address was not one of them, so that backend
was unreachable from the phone no matter what you did on the phone's side.

It is now a setting: **Settings → Connection → "Let my phone reach this
(Tailscale or NordVPN Meshnet)."** Type this machine's own address on that
network there (it looks like `100.x.x.x`; the Tailscale or NordVPN app shows
it) and save. The desktop sets
`JARVIS_HUD_BIND` on the supervised backend from that value every time it
starts it. Leave the field blank — the default — and nothing changes: the
backend stays loopback-only.

**Keep the desktop's own Base URL at `http://127.0.0.1:4719` either way.** The
backend used to have one socket, so a bind address *moved* it off loopback and
the desktop lost it the moment the phone could reach it. `loopback-too.patch`
makes it listen on `127.0.0.1` as well. Do not point the desktop at the
mesh address instead: its HUD window is only allowed to talk to `127.0.0.1`
and `localhost`, and every request it makes to anything else is refused.

**On the phone, type the computer's NAME, not that number.** The desktop box
takes the `100.x` address; the phone takes the name, followed by `:4719` — the
Tailscale name ending in `.ts.net`, or the Meshnet name ending in `.nord`
(for example `my-pc.nord:4719`).

That field only takes an address that starts with `100.64` up to `100.127`
(the range Tailscale and NordVPN Meshnet hand out), `127.0.0.1` or
`localhost`. It refuses `0.0.0.0` — "every network interface", which
includes the café Wi-Fi — in every spelling, including the short ones such as
`0` and `0x0` that Windows reads the same way (an older version only caught
the exact text `0.0.0.0`). It also refuses a home-network address such as
`192.168.x.x`, because that would open Jarvis to everything on your Wi-Fi,
and a name such as `mypc.nord`, because it cannot tell what a name points
at. A value an older version saved that is refused now is not passed to the
backend at all; Settings says so in red.

With `bind-wildcard.patch` the backend refuses too: started with
`JARVIS_HUD_BIND` (or `bind_address`) set to any spelling of "every
interface", it prints why and stops instead of listening. Type the specific
Tailscale address, never the wildcard — that is what keeps the port
unreachable from the café Wi-Fi. (The Windows Firewall still asks about
`python.exe` the first time; see the firewall step.)

**It does NOT keep Windows Firewall out of the picture.** This page used to
say it did, and that was wrong. The first time the backend listens on the
`100.x` address, Windows asks whether to let Python through the firewall.
The Tailscale and Meshnet network adapters are often classed as **Public**
networks, and the prompt's default is Private only - so the phone can be
blocked while everything looks right. One line, in PowerShell **opened as
administrator** (right-click PowerShell → Run as administrator), lets in the
backend's port from private-mesh addresses only and nothing else:

```powershell
New-NetFirewallRule -DisplayName "Jarvis backend (private mesh only)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 4719 -RemoteAddress 100.64.0.0/10 -Profile Any
```

`100.64.0.0/10` is the private address range Tailscale uses for devices on
your tailnet (all of them start `100.`); NordVPN Meshnet addresses are in it
too. If you answered **Cancel** or **Don't allow** to Windows' prompt, it
made a rule that *blocks* Python, and a block beats any allow. This line
lists Python's rules, so you can see one (it changes nothing):

```powershell
Get-NetFirewallRule -Direction Inbound | Where-Object { $_.DisplayName -like '*python*' } | Format-Table DisplayName, Action, Profile, Enabled
```

A row with `Block` in it is the one; delete it in **Windows Defender Firewall
with Advanced Security → Inbound Rules** (search the Start menu for
"firewall").

If you start the backend yourself rather than letting the desktop supervise
it, the desktop's setting does not apply — set the environment variables by
hand instead. One line (put in your own `100.x` address, and change the path
if your backend folder is elsewhere):

```powershell
cd "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; $env:JARVIS_HUD_BIND = "<your 100.x address>"; $env:HF_HUB_DISABLE_TELEMETRY = "1"; $env:DO_NOT_TRACK = "1"; $env:ANONYMIZED_TELEMETRY = "False"; py -3 jarvis_hud.py
```

**Do not set `HUD_TOKEN` here.** This page used to tell you to invent one,
and that was wrong: a `HUD_TOKEN` you set wins over the token saved in
Credential Manager, and the desktop app and the phone only know the saved
one - so both would be locked out. Leave it unset and the backend uses the
saved token.

`JARVIS_HUD_ORIGINS` used to be in that line too, for the desktop's HUD
window. It is not needed any more (2026-09-25): the HUD's requests are now
made by the desktop app itself, not by the window's page, so the server
never sees the window's origin. If you still set it, it does no harm.

The server refuses to start on a non-loopback bind with no token, which is
correct. Its refusal message tells you to edit `bind_address` in
`jarvis-framework.toml`.

**That advice used to be wrong and is now right.** This page said "ignore that,
the module that reads that file does not exist" — true at the time, because
`jarvis_framework.py` was one of the ten missing modules, so
`[security].bind_address` was a setting nothing read. It was rebuilt on
2026-09-16 and the setting works: with `bind_address = "100.64.1.5"` in the
TOML, `jarvis_hud._bind_address()` returns `100.64.1.5`. Verified, not assumed.

`JARVIS_HUD_BIND` still wins over the file, so the command above is still the
quickest way to do it once. Use the TOML if you want it to persist.

**The token is now made for you.** On first run the backend makes a random one
and saves it in **Windows Credential Manager** (as `Jarvis Backend/pairing
token` - never a plain file, per CLAUDE.md rule 3), and the desktop app reads
it from there, so neither end needs configuring. To get it for the phone, open
the desktop app's **Settings → Connection → Show the token for my phone** and
type what it shows into the phone's Token box (it hides itself again after a
minute). Without the desktop app, this one line in PowerShell prints it (change
the path if your backend folder is elsewhere):
`cd "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; py -3 jarvis_token_store.py show`

If an older backend left the token in the plain file
`%USERPROFILE%\.openjarvis\token`, the first start after `apply-patches.ps1`
moves it into Credential Manager, checks it arrived, and deletes the file - so
the phone stays paired. The banner says `moved out of the plain-text file`.

Setting `HUD_TOKEN` yourself still wins over the saved token, and nothing new
is made in that case (an old token file is still moved into Credential
Manager, as above). Only do it if you want to choose the token yourself -
and then type that same token into the desktop app (**Settings →
Connection**) and into the phone, or neither can connect. To get a new token (which is also how
you unpair a device you no longer have), run
`py -3 jarvis_token_store.py forget` in the backend folder and start Jarvis
again; every device then has to pair again.

**`forget` does not unpair anything while another token is in use.** It
only deletes the token kept in Credential Manager. Two other tokens win over
that one, and `forget` cannot touch either:

- **A token typed into the desktop app's Settings.** When the desktop app
  starts Jarvis, it hands that token over, and Jarvis uses it. Clear it
  first: desktop app, **Settings → Connection → Clear token**. Then run
  `forget`.
- **`HUD_TOKEN` set in your environment.** Remove it first with this one
  line in PowerShell, then open a new PowerShell window before running
  `forget`:
  `[Environment]::SetEnvironmentVariable('HUD_TOKEN', $null, 'User')`

`forget` reminds you of both when it runs (the `HUD_TOKEN` one only when
it is set in the window you run it in).

If the banner says `NOT SAVED`, Credential Manager refused the token: Jarvis
uses it for that run only and writes nothing to disk, so the phone would need
pairing again after every restart. The lines under it give the Windows error.
Setting `HUD_TOKEN` yourself avoids it (with the same catch as above: type it
into both apps too).

### 3.3 Pair

1. **Get the APK.** Open the
   [`client-latest` release](https://github.com/darknight11ish/Epic-Jarvis/releases/tag/client-latest).
   The file is named `jarvis-client-<commit>.apk` (for example
   `jarvis-client-497563d.apk`); the top of the release notes says which
   branch and commit it was built from.
2. **Install it**, one of two ways:
   - **On the phone:** open that page in the phone's browser and tap the
     `.apk`. The first time, Android asks to allow installing apps from that
     browser (Settings → Apps → *your browser* → **Install unknown apps** →
     Allow). Then tap Install.
   - **From the PC, over USB:** turn on USB debugging on the phone (Settings
     → About phone → tap **Build number** seven times; then Settings →
     System → Developer options → **USB debugging**), plug it in, accept the
     prompt on the phone, and from the folder the APK is in:
     `adb install -r jarvis-client-<commit>.apk`. (`adb` comes with Google's
     "SDK Platform Tools", one line: `winget install --id Google.PlatformTools -e`.)

   **Android developer verification (2027).** Google is changing how
   Android installs apps from outside the Play Store. From 2027, on phones
   with Google's apps and Google's certification (most phones sold with
   Google Play), installing an app from a developer Google has not verified
   **by tapping the file** will need a one-time "advanced" flow with a
   24-hour wait. **Installing with `adb` from the PC (the second way above)
   stays allowed.** Jarvis is not verified - it is sideloaded, never on Play
   (rule 5) - so on such a phone use `adb`, or do the 24-hour flow once. This
   comes from a search summary of Google's announcement (developer.android.com,
   "developer verification", and press coverage), not from trying it on a
   phone; the exact screens are not known yet. GrapheneOS is not a
   Google-certified system, so it is **likely** unaffected - not checked
   (`docs/GRAPHENEOS.md`).

   If it says `INSTALL_FAILED_UPDATE_INCOMPATIBLE`, the copy already on the
   phone was signed with the old key; [`keystore/README.md`](../keystore/README.md)
   has the three steps (uninstall once, install, pair again).
3. Open it → Pairing → host `yourpc.tailnet.ts.net:4719` (Tailscale) or
   `yourpc.nord:4719` (Meshnet, e.g. `my-pc.nord:4719`), then the
   token: on the PC, the desktop app's **Settings → Connection → Show the
   token for my phone** (or `py -3 jarvis_token_store.py show` in the
   backend folder).
4. Connect.

### 3.4 When it fails

The phone says one of these (the desktop app uses the same words):

- *"Your PC isn't answering."* Nothing answered at all. The PC may be asleep
  or switched off (step 1.9), or Tailscale or Meshnet may be off at one end.
  Windows Firewall blocking the port looks the same (step 3.2, the firewall
  line).
- *"Jarvis isn't running on your PC."* The PC answered, but nothing was
  listening for the phone. Either Jarvis is not started - start it (step
  1.8, or the desktop app's Settings → More options → Starting Jarvis for
  you → Start) - or **it is running but listens on this PC only**
  (`127.0.0.1`, no bind address), which looks exactly the same from the
  phone. If Jarvis is running on the PC, check the bind next (step 3.2).
- *"This device can't find your PC by its name."* The name is wrong, or
  Tailscale or Meshnet is off on the phone.
- *"Tailscale (or Meshnet) is off on this phone"*, under the link on Home
  and on Checks: the phone has no VPN running at all, and both Tailscale
  and Meshnet run as one. Switch it on in the Tailscale or NordVPN app; the
  phone reconnects by itself as soon as the network changes.

On the PC, `selftest.py --preflight` (step 1.10) checks the PC's half in
one go - the phone address, Tailscale or Meshnet on the PC, Jarvis
listening for the phone, and the firewall rule - under "Can your phone
reach Jarvis?".
- *"Your PC didn't accept this app's pairing key."* The key is wrong - or the
  **server has no key at all**: when its banner says `token NONE`, the
  server accepts only callers on the PC itself, so the phone is refused as
  if the key were wrong. (Normally the backend makes and saves a key for
  itself; `NONE` almost always means `jarvis_token_store.py` is missing -
  see step 1.8. The lines under it say why.)

Every message has a **Details** line under it for a bug report, with keys
and passwords taken out. It can be selected and copied by hand.

---

## Backups

Settings → **Backups** writes one locked file - your memory, chat history,
settings and notes, encrypted - into a folder you pick (a NordLocker,
OneDrive or other synced folder is fine: the file stays locked either way).
Choosing the folder asks once with an approval card; after that, **Back up
now** needs no card. Jarvis keeps the newest 5 backups there and deletes
older ones. It does not back up on a timer: a backup is made only when you
press the button.

Three things to know before you rely on it:

- **Every backup gets its own recovery code**, shown once, right after it
  is made. Write it down with the date of that backup. A code opens only
  the backup it was made with.
- **A lost code means a useless backup.** Jarvis never keeps a copy of the
  code and has no way round it.
- Keys and passwords (the pairing token, web search keys, the email
  password, the calendar link, the Home Assistant token) are **not** in a
  backup; after a restore on a new PC, enter them again. And "Erase the
  words" cannot reach into a backup made before the erase: those words stay
  in it until it is one of the older ones deleted.

Restoring is a card plus Windows Hello, on the PC only. Jarvis backs up
what it has now first, with a fresh code of its own (shown once, like the
others), so a restore can be undone.

---

## Updating everything

When this repository changes (the apps say "run apply-patches.ps1" when
your PC's Jarvis is too old for something), update all three parts.

**Or update both halves in one command.** From the folder you downloaded this
into. It stops Jarvis, patches the backend, updates the desktop app, starts
Jarvis again and runs the live check:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update-jarvis.ps1
```

It is safe to run again, keeps a log in `_jarvis-logs` inside your backend
folder, changes nothing at all if something is wrong, and prints the whole plan
first with `-Print`. It is steps 1, 2 and 4 below, in the one order that works -
do those by hand instead when it stops and says why. The phone is still step 3.

1. **The backend.** Stop Jarvis (close its PowerShell window, or quit the
   desktop app if it starts Jarvis for you). Then one line in PowerShell -
   it gets the newest copy of this repository and runs the patch script
   again, which keeps your settings file and backs up everything it
   replaces; its log lands in `_jarvis-logs` inside your backend folder:

   ```powershell
   cd "$env:USERPROFILE\Epic-Jarvis"; git pull; powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -BackendPath "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"
   ```

   Then start Jarvis again (step 1.8).
2. **The desktop app.** If the update signing key is set up ("The desktop
   installer, and the update signing key", above), it is now the app's own
   button: Settings → Updates → **Check now**, then **Install**. Until that
   key exists, build it again (step 2.1's second line) and run the new
   installer over the old one. Your settings stay either way.
3. **The phone app.** Download the newest `.apk` from the `client-latest`
   release and install it over the old one (step 3.3, 1-2). It stays
   paired: an update signed with the same key keeps the app's data.
4. **Check** with the live check (step 1.10).

**Not the same thing:** Settings → **Check for tool updates** looks up
whether the Python packages and other building blocks Jarvis is made from
have newer versions out, and shows a command for each. It never installs
anything, and the first press asks once with an approval card (it reaches
the internet). You do not need it to update Jarvis: the steps above are the
update. A command it shows is a version nobody has tested with Jarvis yet,
so leave those alone unless you know why you want one.

---

## The desktop installer, and the update signing key

Right now the only way to get the desktop app is to build it yourself (step
2.1). Nothing is wrong with that, but it is not something a second person
could do - and it is also the reason **Settings → Updates says "Not set up
yet"**.

This section is the one thing that changes both, and it is about **ten
minutes of your time**. When you have finished it, GitHub builds the
installer for you, you download it like any other program, and each new
version after that appears in Settings → Updates. `scripts\update-jarvis.ps1`
uses that same published installer for the desktop half from then on (before it
exists, that script builds the app from this folder instead).

**One limit worth knowing, said plainly.** `scripts\update-jarvis.ps1`
downloads the installer over HTTPS from this project's own release page - the
same file that page offers anyone - and then runs it with no clicks. It cannot
check the signature published beside it: PowerShell has no way to check that
kind of signature, and the Tauri command line tool has no `signer verify`
command (checked: its `signer` subcommands are `generate` and `sign`). So the
script prints the file's SHA-256 and says this on screen. The app's own
**Settings → Updates** button is the route that does check the signature; add
`-FromSource` to build the app from this folder if you would rather nothing was
downloaded at all.

**What a signing key is, in one line.** Two files made together: the
**private** key stamps each installer (kept secret, on your PC and in
GitHub's secrets), and the **public** key goes inside the app so it can
refuse any installer that does not match. The public key is safe to share;
the private one is the whole security of the update, so it follows the same
rule as every other key in this project (rule 3) and **never goes in this
repository**.

**Do not do half of this.** Half-done is worse than not started: an app with
a public key but a build nobody signed cannot check anything, and a release
page with an installer but no signature is a download the app must refuse.
So the order below is the order that works, and nothing publishes until both
halves exist. Until then the committed settings file stays switched off, and
the app tells the truth about it rather than offering a button that fails.

### 1. Make the key

One line, in PowerShell. It needs Node, which step 2.1 already installed
(the command downloads the Tauri tool itself, so it works before you have
ever built the app):

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.tauri" | Out-Null; npx --yes @tauri-apps/cli@2 signer generate -w "$env:USERPROFILE\.tauri\jarvis-desktop.key"
```

The plain command is `tauri signer generate`; the line above is only that,
wrapped so it writes to a known place without a prompt.

- **It asks twice for a password.** Type one and write it down somewhere
  safe (a password manager). It is asked for every time the installer is
  signed, so step 3 needs it too.
  - **Choose a password.** If you press Enter twice and leave it blank, the
    key has no password and the key file alone signs anything - so anyone who
    ever copies that one file could publish an update your app would accept.
    The password is the only thing that stops that.
- It writes **two** files into `C:\Users\<you>\.tauri\`:
  - `jarvis-desktop.key` - the **private** key. Secret. Never send it to
    anyone, never paste it into a chat, never commit it.
  - `jarvis-desktop.key.pub` - the **public** key. It goes in the app.

**Back both up now** - the two files and the password. If you lose the
private key or its password, GitHub can no longer sign a build that your
installed copy will accept, and getting updates working again means
installing one build by hand (step 5, all over again).

### 2. Put the public key in the app

This copies the public key to your clipboard:

```powershell
(Get-Content "$env:USERPROFILE\.tauri\jarvis-desktop.key.pub" -Raw).Trim() | Set-Clipboard; Write-Host "The PUBLIC key is on your clipboard."
```

Open `jarvis-desktop\src-tauri\tauri.conf.json` and find this near the
bottom:

```json
"pubkey": "",
```

Paste between the two quotes, so the value is the whole long line the file
holds - the public key is one very long string starting
`dW50cnVzdGVkIGNvbW1lbnQ6`.

**That empty string is the entire reason updates are off**: as long as the
value is empty, the app is built without an update key, and `update.rs`
deliberately reports "this build cannot update itself" instead of offering a
Check button that could only fail. Filling it in is what switches the app's
half on.

**It is filled in by you, and never by a script.** In this repository the
value is empty **on purpose** and must stay empty until you have a key of
your own - an empty value is a working, honest "no", not a placeholder
somebody forgot. If you are reading this without having made a key in step 1,
leave it exactly as it is.

**`createUpdaterArtifacts` stays `false` in this file. Do not change it.** It
is off so that a build on your own PC works with no key at all, exactly as
step 2.1 describes. The build that runs on GitHub turns it on **by itself,
only in the run where a key is present**, using a small extra settings file
it writes for that one build. That is the same "off unless it can really
sign" rule as above, done where it cannot be forgotten. (A test in
`jarvis-desktop\tests\updates.mjs` fails if this line is ever committed as
`true`, on purpose: a `true` here would make your own local builds fail
looking for a key that is not in the repository.)

Commit and push that one-line change (or ask for it to be put in for you -
it is the public key, so it is safe to send).

### 3. Give GitHub the private key, and the password

This copies the private key to your clipboard:

```powershell
(Get-Content "$env:USERPROFILE\.tauri\jarvis-desktop.key" -Raw).Trim() | Set-Clipboard; Write-Host "The PRIVATE key is on your clipboard. Paste it into GitHub now, then copy something else."
```

Then, on github.com:

1. Open `darknight11ish/Epic-Jarvis` and click **Settings** (the tab at the
   top of the repository, not your account).
2. In the left column: **Secrets and variables** → **Actions**.
3. **New repository secret**. Name: `TAURI_SIGNING_PRIVATE_KEY`. Secret:
   paste. **Add secret**.
4. **New repository secret** again. Name:
   `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`. Secret: the password from step 1.
   **Add secret**.

Nobody can read a secret back after saving it - not even you; GitHub hands
it to the build machine only while it builds.

These two names are not a choice: `TAURI_SIGNING_PRIVATE_KEY` is the name the
Tauri build reads and the name this repository's workflow looks for. Under
any other name the build finds no key, signs nothing, and publishes nothing -
after twenty minutes of building.

**Both secrets, or neither is any use.** GitHub shows a secret's name and
never its value, so if you are unsure whether the password one saved, the
run in step 4 is what tells you: a build with the private key but the wrong
password fails at "Build the installer" instead of publishing something
unsigned.

### 4. Let it build and publish

Push the step-2 change, or press the button: repository **Actions** tab →
**Desktop release** in the left column → **Run workflow** → **Run workflow**
(choose the branch). It takes 15-25 minutes.

**Pushing only starts it by itself on `main`** (and on the one working branch
the workflow names). A push on any other branch builds nothing at all - that
is deliberate, not broken: whichever branch could publish is a branch that can
replace your own download. **Run workflow works from any branch**, so that is
the way to try it from wherever you are now.

Read the run's own summary line before anything else - it says in one plain
sentence what happened:

| the summary says | what it means |
|---|---|
| `Signed, and published to the 'desktop-latest' release as version 0.2.<n>` | worked; the installer and its signature are on the release you download from |
| `The TAURI_SIGNING_PRIVATE_KEY secret is not set...` | step 3 did not save, or you are on a branch that does not publish |
| `The signing secret is set, but tauri.conf.json has no public key...` | step 2 did not get committed, or is not on this branch |
| `Signed, but <branch> is neither main nor the owner's working branch, so it is not published` | everything works; this branch is just not a publishing one. Take the installer from the run itself (the **Artifacts** box at the bottom of the run's page) |

**If it failed at "Publish" with a 403:** repository **Settings** →
**Actions** → **General** → **Workflow permissions** → **Read and write
permissions** → **Save**, then run it again.

**What should be on the release afterwards:** the installer
(`jarvis-desktop_0.2.<n>_x64-setup.exe`), a small `latest.json` next to it
(the file the app reads), and - the proof that signing happened - an
`.exe.sig` file beside the installer. A release with the installer but no
`.sig` is not a signed release, whatever the summary said; do not install
from it.

### 5. Install that build once, by hand

The copy on your PC now was built **before** the public key existed, so it
cannot check or accept anything - it is the honest "no" from step 2. This is
the one step that cannot be done through the app.

Open the repository's **Releases** (right-hand column on the main page) →
**Jarvis Desktop - latest** → download
`jarvis-desktop_0.2.<n>_x64-setup.exe` → run it. SmartScreen will complain
exactly as in step 2.2 (**More info** → **Run anyway**); that is unchanged
and is not a sign anything is wrong, because signing here means the *update*
is verified by the app, not that Windows trusts the publisher.

Your settings and your pairing stay: the installer runs over the old one.

### 6. Check it, then stop thinking about it

Open the new app: tray icon → **Settings and help…** → **Updates**. It should
now offer **Check now** instead of saying "Not set up yet". Press it. If it
answers "the newest published", you are done - the whole path works, and
**every future build on `main` publishes itself** from then on.

Installing stays a button a person presses. Nothing installs on its own; that
is a rule, not an unfinished setting.

---

## If you lose your phone

The phone holds the pairing key, so whoever has it unlocked can use
Jarvis. On the PC, in this order:

1. **Take the phone off your private network**: Tailscale's admin page,
   **Machines** → the phone → **Remove** (or remove it from your Meshnet
   in the NordVPN app). From then on it cannot reach the PC at all.
2. **Make a new pairing key**, so the old one stops working: follow
   "To get a new token" in step 3.2 (`py -3 jarvis_token_store.py forget`
   in the backend folder, after clearing a token typed into the desktop
   app and any `HUD_TOKEN`), then start Jarvis again.
3. **Pair your other devices again** with the new key (step 3.3).

---

## Uninstalling

The uninstaller leaves your settings behind, including **the pairing token
and your keys**, in Windows Credential Manager (Control Panel → Credential
Manager → Windows Credentials). Jarvis may have made up to eleven entries
there; remove each one that is listed (select it, then **Remove**):

| entry | what it is |
|---|---|
| `Jarvis Backend/pairing token` | the pairing key Jarvis made |
| `Jarvis Desktop/pairing token` | a pairing key you typed into the desktop app's Settings |
| `Jarvis Backend/chat history key` | the key your kept chats are encrypted with. **Remove it only if you are also deleting your chats** (the `.openjarvis` folder below): without it they can never be read again |
| `Jarvis Backend/study decks key` | the key your review decks (`study.db`) are sealed with. **Remove it only if you are also deleting the decks**: without it they can never be read again. It is kept in your locked backup too |
| `Jarvis Backend/Exa key` | your Exa web search key, if you added one |
| `Jarvis Backend/Tavily key` | your Tavily web search key, if you added one |
| `Jarvis Backend/Brave Search key` | your Brave Search key, if you added one |
| `Jarvis Big Model/api key` | the key between Jarvis and the big model's engine, if you switched the big model on |
| `Jarvis Backend/IMAP username` | your email account's username, if you entered it in Settings, "Accounts" rather than as an environment variable |
| `Jarvis Backend/IMAP password` | your email account's password, the same way |
| `Jarvis Backend/Calendar iCal link` | your Google Calendar private link ("Secret address in iCal format"), the same way |
| `Jarvis Backend/Home Assistant token` | your Home Assistant long-lived access token, the same way |

The last four are only there if you entered them in Settings, "Accounts"
(added 2026-09-27) instead of - or as well as - a Windows environment
variable; if you set one of those variables instead, remove it the usual
way (Windows Settings → search "environment variables" → Environment
Variables → your user variables → select it → Delete), separately from
Credential Manager.

A backend older than 2026-09-24 also left the pairing token in plain text
as `.openjarvis\token` in your user folder. To remove everything else:

```
%APPDATA%\com.jarvis.desktop\
%LOCALAPPDATA%\com.jarvis.desktop\
%USERPROFILE%\.openjarvis\        <- your memory and facts. Back this up first.
```

Backup files you made (Settings → Backups; "Backups", above) are not in any of those
folders: they stay in the folder you chose for them, as
`jarvis-backup-<date>.jbak`, until you delete them there.

---

## When something goes wrong

Open **Settings → More options → Startup and logs → Open the log folder**.
Two files:

- `jarvis-desktop.log` — the app itself: what it started, what failed.
- `backend.log` — everything the Python backend printed, including the reason
  it refused to start. **It exists only when the desktop app starts Jarvis
  for you** (step 2.5); a Jarvis you start in PowerShell prints to that
  window instead.

Both roll over at 4 MB, keeping one previous copy as `.1`. Jarvis takes
passwords, keys and the pairing key out of what it writes to `backend.log`
(`log-scrub.patch`), but a list of patterns never catches everything, and
`jarvis-desktop.log` has no such pass - so read either before you share it.

The patch script keeps its own log of each run in `_jarvis-logs` inside your
backend folder (step 1.5).

**"...so Jarvis Desktop stopped restarting it."** When the desktop app
starts Jarvis for you, it restarts a Jarvis that crashes or stops answering,
at most 3 times in 10 minutes (step 2.5). A fourth time, it gives up and
shows that notification, because restarting again would only repeat the
same crash. What to do, in order:

1. Open `backend.log` (the log folder, above) and read its last lines: the
   reason Jarvis stopped is usually the last thing it printed. **Settings →
   More options → Hang and crash notes** lists when each crash or hang
   happened.
2. Fix what it names, if you can (a missing file usually means running
   `apply-patches.ps1` again, step 1.5).
3. Start Jarvis again from the tray icon. If its menu shows **Stop the
   backend (pid ...)**, press that first - after a crash the app still holds
   on to the Jarvis that stopped - and then press **Start the backend**. (The
   same in Settings → More options → Starting Jarvis for you: **Stop**, then
   **Start**. Its status line may still say Jarvis "has been running" until
   you do.)

Until you quit and reopen Jarvis Desktop, the app does not restart a crashed
Jarvis on its own again, even after you start it by hand - so if it crashes
once more, start it by hand again (or quit and reopen the app). If you
cannot tell why it crashes, send the last lines of `backend.log` (read them
first, as above).

**"Cannot reach" errors while everything is running: check for a proxy.**
A proxy is a go-between server some workplaces, VPNs or "privacy" apps set
up for internet traffic. Windows keeps two separate proxy settings, and a
third can come from environment variables:

- **Settings → Network & internet → Proxy.** The one browsers and most apps
  use. For Jarvis you want "Automatically detect settings" and nothing under
  "Manual proxy setup", or, if a proxy is needed there, the box
  "Don't use the proxy server for local (intranet) addresses" ticked.
- **The WinHTTP proxy**, used by some programs and services, and the
  `HTTP_PROXY` / `HTTPS_PROXY` environment variables, which Python reads.
  This one line shows both (it changes nothing):

```powershell
netsh winhttp show proxy; Get-ChildItem Env: | Where-Object { $_.Name -like '*proxy*' } | Format-Table Name, Value
```

`Direct access (no proxy server).` and no rows under it mean there is no
proxy there. Jarvis's calls to programs on this PC (the backend, Ollama) are
being changed to never use a proxy at all; until that is done, a proxy set in
any of these places can get between them.

**"Jarvis got slow."** Open the Brain → Model → Models. If the model has fallen off
the graphics card onto the CPU, there is now a yellow line at the top of that
list saying so, with the percentage. Nothing used to say it — Ollama reports
the model as loaded and healthy either way.

---

## Known rough edges

Things you will hit that are already on the list, so you know they are known
rather than your fault.

- ~~No autostart.~~ Fixed. Settings → More options → Startup and logs →
  **Start Jarvis Desktop when Windows starts**. It starts the app; Jarvis
  itself starts with it only when "Let Jarvis Desktop start and stop Jarvis"
  is on too. It still loses the `Alt+Space` race, though: every startup
  program asks for its shortcuts at once and whoever asks first wins, so being
  present after a reboot is not the same as owning the key.
- ~~No log file.~~ Fixed. Settings → More options → Startup and logs →
  **Open the log folder**. `jarvis-desktop.log` is the app, `backend.log` is
  everything the Python side printed when the app started it — which used to
  go to a closed handle, which is why the advice was to run it in a
  terminal. Both are plain text; `backend.log` has passwords, keys and the
  pairing key taken out, `jarvis-desktop.log` does not, and neither catches
  everything - so read one before sending it anywhere.
- **The updater is off until you make a signing key.** No key exists in this
  repository and none can - a private key kept in a repository is not a key -
  so the committed app is built unable to verify a download, and says so
  rather than offering a button that fails. You can change that: "The desktop
  installer, and the update signing key" (above, about ten minutes) makes
  GitHub build and publish a signed installer, after which Settings →
  Updates stops saying "Not set up yet".
- ~~There is no download link for the backend, and there will not be one.~~
  **Fixed 2026-10-06.** Until then the Python program Jarvis is made of existed
  on the author's PC only, so a second person could not install Jarvis at all.
  It is now published in this repository as [`jarvis-backend\`](../jarvis-backend/README.md),
  as plain source - step 1.3, and `scripts\setup-jarvis.ps1` copies it into
  place for you. Nothing about the five rules changes: the published copy is
  the same local-first program, and it still sends none of your things
  anywhere.
- **Where the token is kept, honestly.** Two places.
  - A token you **typed into Settings** is in **Windows Credential Manager**
    (since 2026-09-23), encrypted to your Windows account — the same place
    Windows keeps saved network passwords. An older version kept it in the
    app's settings file under `%APPDATA%` as plain text; the first start of
    this version moves it across, checks it arrived, and only then deletes
    the plain-text copy. If Credential Manager refuses that move, the old
    copy is left as it was (so you are not unpaired) and Settings says so.
    A NEW token Credential Manager refuses is not saved at all (since
    2026-09-24; it used to fall back to the settings file) - Settings says
    so, and nothing is written to disk.
  - The token **the backend makes for itself** is in Credential Manager too
    (since 2026-09-24, `token-store.patch`), as `Jarvis Backend/pairing
    token`. It used to be a plain file, `%USERPROFILE%\.openjarvis\token`;
    the first start after the update moves it in and deletes the file.
  - What this does not change: any program running as you can still ask
    Credential Manager for either token, just as it could read the old
    file. What changes is that neither sits on disk as readable text - in a
    backup, a copied or synced folder, or a file search.
- **Do not run the OpenJarvis copy you downloaded.** It writes into the same `%USERPROFILE%\.openjarvis\` folder as Jarvis, including a `documents` table in `memory.db`; with `documents-owned.patch` applied Jarvis ignores that table, but nothing stops OpenJarvis changing the folder.
