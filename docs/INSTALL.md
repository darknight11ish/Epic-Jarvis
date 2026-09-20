# Installing Jarvis Desktop, start to finish

Written because an audit walked the path from a fresh Windows 11 machine to a
working system and found **nine of sixteen steps documented nowhere**. Nothing
here is aspirational: where something does not work yet, it says so and tells
you what to do instead.

Read the whole page once before starting. Two of the steps are much easier if
you know they are coming.

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

---

## Part 1 — The backend

### 1.1 Install Python

```powershell
winget install Python.Python.3.12
```

**Do not rely on the `python` command afterwards.** On a fresh Windows 11 the
name `python` is a Microsoft Store *App Execution Alias* — a zero-byte stub
that opens the Store if Python is not installed. It is not an error you can
see: the app will report "Started the backend (pid 12345)" and nothing will be
listening.

Find the real one and write the path down:

```powershell
py -3 -c "import sys; print(sys.executable)"
```

Typically `C:\Users\<you>\AppData\Local\Programs\Python\Python312\python.exe`.
Use that full path everywhere below.

### 1.2 Get the backend files

**This step used to be missing from this page, and it cost a day.** It went
straight to "put the files somewhere" without saying where to get them. When
ten of them turned out to be absent from the owner's machine, there was
nothing here to reinstall from.

So, plainly: **there is no download link.** The backend is not a public
project. Searching for it found two unrelated things — `open-jarvis/OpenJarvis`
keeps its code under `src/openjarvis/` with no flat `jarvis_*.py` at all, and
`Twsman1/JARVIS` has a `jarvis_hud.py` that is a wake-word overlay, not an
HTTP server. Neither has `jarvis_memory.py` or `jarvis_gate.py`. If a real
upstream exists, it has not been found.

What the files are, as far as the evidence goes: they were produced in
assistant conversations and saved to disk. The owner's copy lives under
`Documents\Claude\`, `patch_openjarvis.py` is written in the same voice as
the rest, and there is no installer, package or archive anywhere on the
machine that contains them.

**The practical consequence: those conversations are the only copy.** Save the
files somewhere backed up, and if one goes missing, the chat history is where
it is.

### 1.2b Check the folder is complete before anything else

`jarvis_hud.py` needs **all of its sibling `jarvis_*.py` modules in the same
folder**. There are twenty-six. Most imports are wrapped so a missing one does
not stop the program starting — which is the problem: it starts, looks healthy,
and then fails on the first real request.

And one missing file hides the others. `jarvis_framework` is imported by
fifteen of the twenty-six, so the moment it is absent Python stops at the very
first import and you never learn what else is gone.

```powershell
.\scripts\check-backend.ps1
```

It reads the import lines of every file you have, works out the full list of
modules they need, and says which are present — most-needed first. It changes
nothing. Run it before the patches, and again after recovering any file.

It also wants `jarvis_hud.html` beside it, for the browser HUD. That file lives
in this repo at `jarvis-desktop/src/jarvis_hud.html`; copy it across, or accept
that `http://localhost:4719/` returns a 500 while the desktop app works fine.

**There is nothing to `pip install`.** The backend is standard library only.
That claim is in its docstring and it is true — verified by walking every
import.

### 1.3 Apply the patches

In `backend/` of this repo, in this order. `memory-safety` must go first: until
it lands, a correction can retire an unrelated fact, and installing the
embedding model breaks every future write.

```powershell
copy jarvis_hud.py jarvis_hud.py.bak
copy jarvis_memory.py jarvis_memory.py.bak
copy jarvis_extract.py jarvis_extract.py.bak
git apply path\to\memory-safety.patch
git apply path\to\events-pump.patch
```

`events-pump.patch` is **not optional if you want the phone.** Without it the
server never publishes an `approval` event, so a gate raised on the PC does not
reach the phone until the hourly reconnect. Everything else can be perfect and
the phone will still look broken.

### 1.4 Start it

```powershell
C:\...\python.exe jarvis_hud.py
```

Read the banner. Three lines matter:

- `hud token  NOT SET` — fine for now, loopback only.
- `routing off - jarvis_router.py / jarvis_recall.py not found` — **this message
  names the wrong file.** It prints both names whichever is missing. Check which
  one you actually lack.
- If the memory block is missing entirely, one of the five memory modules failed
  to import and Jarvis has no memory. The banner does not say so.

Leave this window open. Everything it prints goes here and nowhere else.

---

## Part 2 — The desktop app

### 2.1 Build it

```powershell
cd jarvis-desktop
npm install
npm run tauri build
```

The installers land in `src-tauri\target\release\bundle\` — `nsis\*-setup.exe`
and `msi\*.msi`. Use the NSIS one.

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
- If you do turn it on, set **Program** to the full `python.exe` path from step
  1.1 — not `python` — and **Arguments** to the full path of `jarvis_hud.py`.

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

Tailscale, on both devices, on the same tailnet, with MagicDNS on. The backend
already expects this — its own comments say so. A private mesh between two
devices you own is not a public tunnel; nothing is exposed to the internet.

### 3.2 Reaching a supervised backend from the phone

**Fixed 2026-09-16.** The desktop app used to never tell a backend it started
to listen anywhere but loopback — it passed three environment variables to a
supervised backend and the bind address was not one of them, so that backend
was unreachable from the phone no matter what you did on the phone's side.

It is now a setting: **Settings → Connection → "Let my phone reach this over
Tailscale."** Type this machine's own Tailscale address there (it looks like
`100.x.x.x`; find it in the Tailscale app) and save. The desktop sets
`JARVIS_HUD_BIND` on the supervised backend from that value every time it
starts it. Leave the field blank — the default — and nothing changes: the
backend stays loopback-only.

That field refuses `0.0.0.0` outright, on either side: the setting will not
save it, and if it somehow reached the backend, `jarvis_hud._bind_address()`
would still be binding every interface on the machine, not just the tailnet.
Type the specific Tailscale address, never the wildcard — that is what keeps
the port unreachable from the café Wi-Fi and the Windows Firewall profile out
of the picture.

If you start the backend yourself rather than letting the desktop supervise
it, the desktop's setting does not apply — set the environment variable by
hand instead:

```powershell
$env:HUD_TOKEN = "<a long random string you invent>"
$env:JARVIS_HUD_BIND = "<your Tailscale 100.x address>"
C:\...\python.exe jarvis_hud.py
```

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

**The token is now made for you.** On first run the backend writes a random one
to `%USERPROFILE%\.openjarvis\token` and the desktop app reads it from there,
so neither end needs configuring. Open that file to get the string for the
phone.

Setting `HUD_TOKEN` yourself still wins and nothing is written in that case —
useful if you would rather choose it. Delete the file to get a new one; the
phone then has to be re-paired, which is also how you unpair a device you no
longer have.

If the boot banner does not print a `token` line, the backend could not write
that file. Check the permissions on the folder. It will still run on loopback
without one, but the phone cannot pair.

### 3.3 Pair

1. Sideload the APK: `adb install -r client-latest.apk`
2. Open it → Pairing → host `yourpc.tailnet.ts.net:4719`, then the token.
3. Connect.

### 3.4 When it fails

The phone says: *"Cannot reach the desktop… Check Tailscale is up on both
ends."* **This message is usually wrong.** A loopback-bound backend refuses the
connection identically to an absent Tailscale. Check the bind first — it is the
more likely cause.

*"The desktop refused that token"* can also mean the **server has no token at
all**: with `HUD_TOKEN` unset the server accepts only loopback callers, so your
phone gets a 401 that looks like a token mismatch.

---

## Uninstalling

The uninstaller leaves your settings behind, including **the pairing token, in
plain text** — in the `.openjarvis` folder, and in `%APPDATA%` too if you ever
typed a token into Settings. To remove everything:

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
- **The token is stored in plain text**, in two places: the one the backend
  makes for itself at `%USERPROFILE%\.openjarvis\token`, and — only if you
  typed one into Settings — the desktop app's store under `%APPDATA%`. Neither
  is encrypted and neither is in the Windows credential manager. Anything
  running as you can read them. On Linux and macOS the backend at least sets
  the file to owner-only; Windows has no equivalent in that code path, so the
  file inherits whatever the folder allows.
