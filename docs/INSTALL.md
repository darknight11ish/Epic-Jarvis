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

## What you are installing

Three things, and it is worth knowing which is which, because when something
breaks the error usually names the wrong one.

| | what it is | who starts it |
|---|---|---|
| **The backend** | `jarvis_hud.py` — a Python program. This *is* Jarvis: the model, the memory, the approval queue. | you, or the desktop app |
| **Jarvis Desktop** | the Windows app: the spotlight bar, the tray icon, the widget, the Brain. A **client**. | you |
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

**This is the one part no script can do for you, because there is no
download link.** The backend is not a public project. Searching for it found
two unrelated things — `open-jarvis/OpenJarvis` keeps its code under
`src/openjarvis/` with no flat `jarvis_*.py` at all, and `Twsman1/JARVIS` has
a `jarvis_hud.py` that is a wake-word overlay, not an HTTP server. Neither has
`jarvis_memory.py` or `jarvis_gate.py`.

What the files are, as far as the evidence goes: they were produced in
assistant conversations and saved to disk, under `Documents\Claude\` on the
owner's PC. **Those conversations are the only copy** of the files this
repository does not ship (`jarvis_hud.py`, `jarvis_gate.py`,
`jarvis_extract.py`, `jarvis_models.py`, `jarvis_skills.py` and a few more).
Keep that folder somewhere backed up.

Ten modules that were lost *have* been rebuilt, and live in this repository
(`backend\rebuilt\`), along with every newer module. You do not copy those by
hand: step 1.5 does.

### 1.4 Check the backend folder

One line. It reads every file in your backend folder, works out which
modules they need, and says which are there. It changes nothing.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-backend.ps1 -BackendPath "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"
```

(`-ExecutionPolicy Bypass` lets Windows run this one script file without
changing any setting. Without it, Windows refuses script files by default.)

- **`ok`** - there.
- **`not yet`** - this repository ships it; step 1.5 copies it in. Fine.
- **`MISSING`** - not there, and this repository does not have it either.
  Find it before going on (the list is most-needed first, and one missing
  file hides the others). It lists the files that need each one.

### 1.5 Run the one script

One line:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -BackendPath "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"
```

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

It is safe to run again - after a `git pull`, run the same line. It works out
what is already done and does the rest.

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

**Tools are off until you name them.** Step 1.5 copies in the tool modules
(checking GitHub for an existing library, reading and clicking other windows,
the phone over adb, a browser, calendar, email, notes, Home Assistant), but
the model is offered a tool only if the `enabled` list under `[tools]` names
it - and every action a tool takes still goes through the approval gate.
This repository's copy of the file has **no** `[tools]` section, so a PC set
up from it starts with every tool off. To turn one on, add a section like
this to the file (the names are the tools' names in
`backend\jarvis_agent.py`):

```toml
[tools]
enabled = ["calculator"]
```

`backend\README.md` has a section per tool saying what it needs set up first
and which approval tier it asks under. Restart the backend after editing.

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

**Voice (optional).** Talking to Jarvis needs model files downloaded onto the
PC as well. `backend\README.md`, section **"Voice that works"**, has the
steps.

### 1.8 Start it

One line (change the path if your backend folder is elsewhere):

```powershell
cd "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; py -3 jarvis_hud.py
```

Read what it prints at the top. Three lines matter:

- A `token` line saying `in Windows Credential Manager` - the pairing token
  was made and saved (step 1.5 applied the patches that do it). If it says
  `NOT SAVED` or `STILL IN THE OLD PLAIN-TEXT FILE` instead, the lines under
  it say why. No token line at all means `jarvis_token_store.py` is missing
  from the backend folder; run step 1.5 again.
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

The HUD window will say **"demo · not connected"** and show a banner telling you
to run `python jarvis_hud.py`. If you already did that in Part 1, ignore it —
that page is the backend's own browser page and does not know the desktop app
exists. The surfaces that tell you the truth are the tray and the spotlight bar.

### 2.4 The hotkeys, which may not work

Five are registered at startup. **`Alt+Space` is the most contested key on
Windows 11** — PowerToys Run and the Copilot app both claim it, both start at
login, and Jarvis starts after them, so Jarvis loses.

If a key was refused you get a toast saying so. If the toast fails you get
nothing at all, because release builds have no console.

**The fallback, worth memorising now:** right-click the tray icon → **Settings**
→ **Shortcuts**. Every binding is editable and each shows whether Windows
accepted it.

`Alt+Shift+S/N/W` clash with the Windows keyboard-layout switch if you have two
or more layouts installed.

### 2.5 Point it at the backend

Tray → **Settings** → **Backend**.

- Leave the URL at `http://127.0.0.1:4719`.
- **Supervision** is off by default and that is deliberate: with it on, the app
  adopts and kills the backend, which would kill a backend you started in a
  terminal. Turn it on only if you want the app to own the backend's lifetime.
- If you do turn it on, set **Program** to the full path of the real
  `python.exe` — not `python`, which may be the Store shortcut from step 1.1.
  This one line prints it:
  `py -3 -c "import sys; print(sys.executable)"` (typically
  `C:\Users\<you>\AppData\Local\Programs\Python\Python312\python.exe`).
  Set **Arguments** to the full path of `jarvis_hud.py`.

**Know the trade:** with supervision on, quitting Jarvis Desktop also stops the
backend, and therefore stops the phone from reaching anything.

---

## Jarvis learns from your conversations, and it is on

Worth knowing before you use it rather than after.

About 45 seconds after a conversation goes quiet, Jarvis re-reads **what you
typed** — never its own replies, never anything a tool returned — and asks the
local model which of it would still be true and useful next month. Anything it
finds goes into a review queue.

**Nothing it finds enters memory until you accept it, one at a time.** The
queue is the Memory tab in the Brain window, which is also where you can
reword a fact, stop one being recalled, or copy the lot out as JSON.

It never leaves the machine: the extractor talks to Ollama on loopback and
refuses to run at all if `OLLAMA_URL` points anywhere else.

To turn it off: the switch is in that same Memory tab. To turn it off before
Jarvis has ever started, set `JARVIS_EXTRACT=0` — that is a floor the in-app
switch cannot lift.

---

## Part 3 — The phone

**Read this part before you start it.**

### 3.1 What works

A private network between your own devices: **Tailscale** (both devices on the
same tailnet, with MagicDNS on) or **NordVPN Meshnet** (both devices on your
Meshnet). The owner's setup uses Meshnet, with names like
`marioirelan11-alps.nord`. A private mesh between two devices you own is not a
public tunnel; nothing is exposed to the internet.

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
(for example `marioirelan11-alps.nord:4719`).

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
hand instead, in the same window, from your backend folder (one line; put in
your own long random token and your own `100.x` address):

```powershell
$env:HUD_TOKEN = "<a long random string you invent>"; $env:JARVIS_HUD_BIND = "<your 100.x address>"; $env:JARVIS_HUD_ORIGINS = "http://tauri.localhost"; py -3 jarvis_hud.py
```

`JARVIS_HUD_ORIGINS` is the one the desktop also sets for a backend it starts
itself. Without it the server refuses every request from the desktop's HUD
window as cross-origin — the window's pages come from `http://tauri.localhost`,
which the server has no way to guess.

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

Setting `HUD_TOKEN` yourself still wins and nothing is saved in that case —
useful if you would rather choose it. To get a new token (which is also how
you unpair a device you no longer have), run
`py -3 jarvis_token_store.py forget` in the backend folder and start Jarvis
again; every device then has to pair again.

If the banner says `NOT SAVED`, Credential Manager refused the token: Jarvis
uses it for that run only and writes nothing to disk, so the phone would need
pairing again after every restart. The lines under it give the Windows error.
Setting `HUD_TOKEN` yourself avoids it.

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

   If it says `INSTALL_FAILED_UPDATE_INCOMPATIBLE`, the copy already on the
   phone was signed with the old key; [`keystore/README.md`](../keystore/README.md)
   has the three steps (uninstall once, install, pair again).
3. Open it → Pairing → host `yourpc.tailnet.ts.net:4719` (Tailscale) or
   `yourpc.nord:4719` (Meshnet, e.g. `marioirelan11-alps.nord:4719`), then the
   token: on the PC, the desktop app's **Settings → Connection → Show the
   token for my phone** (or `py -3 jarvis_token_store.py show` in the
   backend folder).
4. Connect.

### 3.4 When it fails

The phone says: *"Cannot reach the desktop… Check your private network
(Tailscale or NordVPN Meshnet) is up on both ends."* **This message is usually
wrong.** A loopback-bound backend refuses the connection identically to an
absent private network. Check the bind first — it is the
more likely cause.

*"The desktop refused that token"* can also mean the **server has no token at
all**: with `HUD_TOKEN` unset the server accepts only loopback callers, so your
phone gets a 401 that looks like a token mismatch.

---

## Uninstalling

The uninstaller leaves your settings behind, including **the pairing token**,
in Windows Credential Manager (Control Panel → Credential Manager → Windows
Credentials): "Jarvis Backend/pairing token" (the one Jarvis made) and, if you
ever typed a token into Settings, "Jarvis Desktop/pairing token". Select each
and press Remove. A backend older than 2026-09-24 also left it in plain text
as `.openjarvis\token` in your user folder. To remove everything else:

```
%APPDATA%\com.jarvis.desktop\
%LOCALAPPDATA%\com.jarvis.desktop\
%USERPROFILE%\.openjarvis\        <- your memory and facts. Back this up first.
```

---

## When something goes wrong

Open **Settings → Startup and logs → Open the log folder**. Two files:

- `jarvis-desktop.log` — the app itself: what it started, what failed.
- `backend.log` — everything the Python backend printed, including the reason
  it refused to start.

Both roll over at 4 MB, keeping one previous copy as `.1`. Neither is
redacted, so read before you share.

**"Jarvis got slow."** Open the Brain → Models. If the model has fallen off
the graphics card onto the CPU, there is now a yellow line at the top of that
list saying so, with the percentage. Nothing used to say it — Ollama reports
the model as loaded and healthy either way.

---

## Known rough edges

Things you will hit that are already on the list, so you know they are known
rather than your fault.

- ~~No autostart.~~ Fixed. Settings → Startup and logs → **Start Jarvis when
  Windows starts**. It still loses the `Alt+Space` race, though: every startup
  program asks for its shortcuts at once and whoever asks first wins, so being
  present after a reboot is not the same as owning the key.
- ~~No log file.~~ Fixed. Settings → Startup and logs → **Open the log
  folder**. `jarvis-desktop.log` is the app, `backend.log` is everything the
  Python side printed — which used to go to a closed handle, which is why the
  advice was to run it in a terminal. Both are **plain text and nothing in
  them is scrambled or hidden**, so read one before sending it anywhere.
- **The updater is off.** No signing key exists, so the in-app updater is inert
  and reports itself unsupported. Updating means building and installing again.
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
    On Linux and macOS the backend also sets the file to owner-only.
- **Do not run the OpenJarvis copy you downloaded.** It writes into the same `%USERPROFILE%\.openjarvis\` folder as Jarvis, including a `documents` table in `memory.db`; with `documents-owned.patch` applied Jarvis ignores that table, but nothing stops OpenJarvis changing the folder.
