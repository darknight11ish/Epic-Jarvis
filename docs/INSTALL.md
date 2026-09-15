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

### 1.2 Put the backend files somewhere

`jarvis_hud.py` needs **all of its sibling `jarvis_*.py` modules in the same
folder**. It imports eighteen of them. Most are wrapped so a missing one does
not stop the program starting — which is the problem: it starts, looks healthy,
and then fails on the first real request.

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

## Part 3 — The phone

**Read this part before you start it.** Two pieces are not built yet and you
will hit both.

### 3.1 What works

Tailscale, on both devices, on the same tailnet, with MagicDNS on. The backend
already expects this — its own comments say so. A private mesh between two
devices you own is not a public tunnel; nothing is exposed to the internet.

### 3.2 What does not work yet

**The desktop app never tells the backend to listen anywhere but loopback.** It
passes three environment variables to a supervised backend and the bind address
is not one of them. So a backend the app started is unreachable from the phone,
no matter what you do on the phone.

Until that is fixed, start the backend by hand with both set:

```powershell
$env:HUD_TOKEN = "<a long random string you invent>"
$env:JARVIS_HUD_BIND = "<your Tailscale 100.x address>"
C:\...\python.exe jarvis_hud.py
```

Bind to the **specific Tailscale address**, not `0.0.0.0`. Then the port is not
reachable from the café Wi-Fi at all and the Windows Firewall profile stops
mattering.

The server refuses to start on a non-loopback bind with no token, which is
correct. Its refusal message tells you to edit `bind_address` in
`jarvis-framework.toml` — **ignore that**, the module that reads that file does
not exist. `JARVIS_HUD_BIND` is the only thing that works.

**Nothing generates the token.** Both ends are write-only: the desktop will not
show it back to you and neither will the phone. You invent it, you type it
twice, and **you write it down**, because there is no recovery except replacing
it on both ends.

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
plain text**. To remove everything:

```
%APPDATA%\com.jarvis.desktop\
%LOCALAPPDATA%\com.jarvis.desktop\
%USERPROFILE%\.openjarvis\        <- your memory and facts. Back this up first.
```

---

## Known rough edges

Things you will hit that are already on the list, so you know they are known
rather than your fault.

- **No autostart.** The app must be launched by hand after every boot, and it
  loses the `Alt+Space` race because it starts after everything else.
- **No log file.** The app writes no log, the release build has no console, and
  the Python child's output goes to a closed handle. When the backend fails to
  start, nothing anywhere records why. Start the backend in a terminal while
  setting up.
- **The updater is off.** No signing key exists, so the in-app updater is inert
  and reports itself unsupported. Updating means building and installing again.
- **The token is stored in plain text** in `%APPDATA%`, despite a code comment
  that used to claim otherwise.
