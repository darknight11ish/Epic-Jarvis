# Ease-of-use audit: first-time setup (lens: setup)

2026-09-26. Read-only. Every claim cites the file and line I read. "Not checked"
means I did not check it. Screenshots of the first-launch windows, rendered from
a copy in a plain browser (not inside Tauri, so the HUD shows its preview state),
are next to this file: `setup-onboarding.png`, `setup-jarvis_hud.png`,
`setup-index.png`.

## The answer first

**Setting Jarvis up on a fresh Windows 11 PC and a new Android phone is hard
for a newcomer, and for anyone but the owner it cannot be done at all.** The
instructions themselves are good: honest, one line per command, and every trap
already hit is written down. The problem is how much there is, not how it is
written. To reach a first chat from the phone you install **6 programs on the
PC plus a private-network app on both devices**, paste about **11 commands**
(about **17** with voice), download about **5 GB** (about **6 GB** with voice),
build the desktop app from source, and type a **43-character** secret by hand
into a hidden field on the phone.

The guided setup that would fix most of this (idea I119) is planned but rated
"Later", and even when built it cannot fix the three worst blockers, because
they sit before any app is running.

## The numbers

| What | Count | Where I read it |
|---|---|---|
| Programs to install on the PC before the desktop app exists | 6 (Git, Python, Ollama; VS C++ Build Tools, Rust, Node.js) | `docs/INSTALL.md:53`, `:270` |
| Extra apps for the phone to reach the PC | Tailscale or NordVPN Meshnet, on **both** devices | `docs/INSTALL.md:514-518` |
| PowerShell blocks in INSTALL.md, parts 1-3 | 12 (13 in the whole file) | counted `^```powershell` |
| Required commands to reach a first phone chat | about 11 (1.1 ×2, 1.2, 1.4, 1.5, 1.7, 1.8, 2.1 ×2, firewall, start with bind) | `docs/INSTALL.md:53-598` |
| Extra commands for voice | 6 more (steps 1-5 and 7; step 6 re-runs the patch script) plus Smart Turn and the voice-ID model | `backend/README.md:4776-4870`, `:5001`, `:6770` |
| Largest single download | the model, about 5 GB | `docs/INSTALL.md:202` |
| Voice downloads | about 850 MB, plus 12 MB (Smart Turn) and 101 MB (voice ID) | `backend/README.md:4780`, `:5001`, `:6770` |
| Memory search models, fetched on first use | about 150 MB (70 + 80) | `backend/requirements.txt` (fastembed line) |
| Phone app | 31 MB | GitHub release `client-latest`, asset `jarvis-client-55c5acb.apk`, 31,073,584 bytes |
| VS Build Tools download | **not checked** (not stated anywhere in the repo) | - |
| Backend patches the script applies | 67 `.patch` files | `ls backend/*.patch` |
| Places INSTALL.md uses the owner's own folder `C:\Users\pcadmin\...` | 6, plus the patch script's default | `docs/INSTALL.md:40,109,126,232,598,634`; `scripts/apply-patches.ps1:73` |
| Distinct environment-variable names in INSTALL.md + backend/README.md | 53 | `grep -o JARVIS_*/OLLAMA_*/HUD_TOKEN`, sorted unique |
| Pairing token length | 43 characters, random letters, digits, `-` and `_` | `backend/jarvis_token_store.py:283` (`secrets.token_urlsafe(32)`) |
| Seconds the PC shows the token | 60, no Copy button (on purpose) | `jarvis-desktop/src/settings.html:99-106` |
| First-run walkthrough | 3 screens, desktop only; 0 on the phone | `jarvis-desktop/src/onboarding.html:130-179`; no walkthrough in `jarvis-client` (grep) |
| Windows opened on the first desktop launch | 4 at once: 1280×820 HUD, 320×44 widget, tray icon, walkthrough | `src-tauri/src/lib.rs:585,594`, `tauri.conf.json:40-56`, `lib.rs:1179-1180`, `docs/INSTALL.md:298-303` |
| Preflight checks | 13, none of them about the phone reaching the PC | `backend/selftest.py:962-1610` (`@preflight_check`) |
| Jargon words in INSTALL.md parts 1-3 | "token" 52, "HUD" 32, "bind" 15, "TOML" 13, "loopback" 7, "firewall" 8, "patch" 20, plus tailnet, MagicDNS, Modelfile, NSIS, adb | `grep -o -i` on lines 1-716 |

## What works

1. **The instructions are honest and runnable.** Each command is one line, as
   `CLAUDE.md` asks. Known traps are named before you hit them: the fake
   `python` Store shortcut (`INSTALL.md:62-67`), `Alt+Space` being taken
   (`:312-321`), the firewall treating Tailscale as a Public network
   (`:565-590`), the SmartScreen "More info" link (`:288-294`).
2. **The patch script is safe to run and re-run.** It rehearses on a copy,
   backs up, copies modules, never overwrites your settings file, installs
   packages and runs the tests (`INSTALL.md:129-151`).
3. **The token makes itself.** The backend creates it on first run and keeps
   it in Windows Credential Manager, and the desktop reads it from there, so
   the PC side needs no token setup (`INSTALL.md:626-629`).
4. **The phone guards its address and the token.** It refuses internet
   addresses (`jarvis-client/.../data/OwnNetwork.kt:39-43`), the token field is
   hidden and never saved in a way Android keeps outside the app
   (`PairingScreen.kt:93-102`), and Checks and Help can be opened *before*
   pairing (`MainActivity.kt:1020-1035`).
5. **Offline states have words.** The desktop bar says "Jarvis is not running
   at <address>. Start it, or check the address in Settings"
   (`src-tauri/src/stream.rs:394-396`, `src/jarvis-link.js:384-386`).
6. **The live preflight is thorough** for the backend: running, token,
   model on the graphics card, a real chat, patches present, gate, event
   stream, voice, reach, Credential Manager (`backend/selftest.py`, the 13
   `@preflight_check` lines).
7. **The phone asks for notifications at the right time**: after pairing,
   not at launch (`MainActivity.kt:883-903`).

## What is hard, ranked by how much it hurts a newcomer

### 1. The backend cannot be downloaded (blocker, anyone but the owner)

`docs/INSTALL.md:85-97`: "This is the one part no script can do for you,
because there is no download link." Files such as `jarvis_hud.py` and
`jarvis_gate.py` exist only in the owner's `Documents\Claude\` folder. The
repo ships 67 patches *against* those files. For the owner on a new or
reinstalled PC, setup depends on having a copy of that folder. INSTALL.md says
"keep that folder somewhere backed up" (`:97`) but gives no command for it.
**No app can fix this, and the guided setup (I119) does not cover it.**

### 2. The desktop app has to be built from source (blocker-level effort)

INSTALL.md 2.1 installs VS Build Tools, Rust and Node, then runs
`npm install; npm run tauri build` (`INSTALL.md:265-280`). The GitHub release
list has **only** `client-latest`; there is no `desktop-latest` (checked with
the GitHub API today). CI *does* build an unsigned installer on every run and
keeps it for 14 days (`.github/workflows/desktop-release.yml:13-16, 199-204`),
but INSTALL.md never mentions it and says "there is no download yet"
(`:265`). **Still open from the professionalism audit**, item 2
(`docs/PROFESSIONALISM-AUDIT-2026-09-26.md:40`).

### 3. Reaching the phone takes five separate things, and one setting silently does nothing

To pair the phone you must (a) install Tailscale or Meshnet on both devices,
(b) type the PC's `100.x` address into Settings, (c) add a firewall rule in an
**administrator** PowerShell (`INSTALL.md:571-576`), (d) restart the backend,
(e) type the PC's *name* (not the number) on the phone (`:542-545`).

- **INSTALL.md has no steps for installing Tailscale or Meshnet at all.**
  It only says both devices must be on it (`:514-518`). Nothing in
  `README.md`'s "Install it" section says the phone needs one (`README.md:84-87`).
- **The "Let my phone reach this" setting only works if the desktop starts
  Jarvis**, and that is off by default. The address is passed only to a
  backend the desktop starts (`src-tauri/src/sidecar.rs:482-485`); the
  Settings note under the box does not say so (`settings.html:109-118`).
  INSTALL.md says it (`:592-599`), Settings does not. Following Settings
  alone, a newcomer saves the address and the phone still cannot connect.
- **Mixed advice when the phone fails.** INSTALL.md says the phone's "Check
  your private network" message "is usually wrong" and to check the listening
  address first (`INSTALL.md:703-707`); the phone's own Help says the private
  network is "the most common cause by far" (`FaqScreen.kt:203-206`).
- **The phone suggests addresses that cannot work.** Its refusal message
  says to use "your home network (an address like 192.168.x.x or 10.x.x.x, or
  a name ending in .local)" (`OwnNetwork.kt:39-43`), but Android only lets the
  app talk plain `http` to `.ts.net`, `.nord`, `localhost` and `127.0.0.1`
  (`res/xml/network_security_config.xml`; `PlatformReadiness.kt:61-62`), and
  the desktop refuses to listen on a home address
  (`src-tauri/src/commands.rs:799-807`). So in practice **the phone needs
  Tailscale or Meshnet even at home**; the message says otherwise. This is
  where the 2026-09-26 "own networks" decision (which allows the home
  network) meets the older phone and desktop limits; the owner's decision is
  honoured by the address check but not by what can actually connect.
- **The preflight does not check any of this.** None of its 13 checks looks
  at the listening address or the firewall (`backend/selftest.py`, grep for
  "bind"/"firewall" finds only the self-test's own loopback start at `:355`,
  `:377`).

### 4. Typing the token on the phone

43 random characters (`jarvis_token_store.py:283`), shown on the PC for one
minute with no Copy button (`settings.html:99-106`), typed into a field that
hides every character and has no "show" button (`ui/parts/Parts.kt:677-681`,
`PairingScreen.kt:163-178`). One typo and the answer is "the desktop refused
that token", with no way to see which character was wrong. QR pairing was
decided on 2026-09-24 (`CLAUDE.md`) and is queued as I102
(`docs/FEASIBILITY-AUDIT-2026-09-26.md:249`), not built (no QR code in either
app: grep).

### 5. Jarvis does not start itself

Supervision ("Let Jarvis Desktop start and stop Jarvis") is off by default
(`settings.html:1180-1193`). With it off, after every restart of the PC the
owner opens PowerShell and runs `py -3 jarvis_hud.py` (`INSTALL.md:227-251`).
"Start Jarvis when Windows starts" starts only the desktop app
(`INSTALL.md:780-783`). Turning supervision on means pasting the full path of
`python.exe` (found with another command) and the full path of
`jarvis_hud.py` (`settings.html:1195-1211`). The offline bar says "Start it"
but has only a Reconnect button (`src/index.html:374-377`).

### 6. The first desktop launch opens four things, and the biggest is the least friendly

HUD (1280×820), widget, tray icon and the walkthrough all appear together
(numbers table). The HUD's first screen shows "escalate", "critic", "bulk"
each marked **CLOUD**, "proxy", "FREE-TIER BUDGET", "TOKENS", "COMPLEXITY",
"ENTITIES" (`setup-jarvis_hud.png`; that is the browser preview - with a live
backend the lanes may differ, **not checked**). For a program whose first rule
is "private things stay on the PC", seeing three CLOUD rows first is
alarming. The tray icon, which the walkthrough's screen 1 is about, starts
hidden in Windows 11's `^` overflow (`INSTALL.md:302-303`), and the
walkthrough does not say so (`onboarding.html:133-137`). The walkthrough also
names `Alt+Space` (`:154`) without saying it is often taken.

### 7. Turning on what Jarvis can *do* means editing a text file

The settings file this repo ships has **no** `[tools]` section, so every
model tool (calendar, email, notes search, home, web search by the model) is
off (`INSTALL.md:181-189`; confirmed: no `[tools]` in
`backend/rebuilt/jarvis-framework.toml`). Turning one on means Notepad, a
list of internal names, and a restart. No app has a switch for it (grep for
`[tools].enabled` in both apps: none). Timers and reminders still work
without it (`docs/JARVIS-API.md:3610-3620`).

### 8. Email and calendar are set up with PowerShell and environment variables

Gmail: 2-Step Verification, an app password, one PowerShell line that stores
the password as a **Windows user environment variable**, then a Notepad edit
to `[tools]`, then a restart (`backend/README.md:8851-8876`). The calendar
link works the same way (`:8742`). Neither app has a screen for these; that is
written down as deliberate for the calendar link (`docs/ARCHITECTURE.md:463-467`).
The web search keys, by contrast, go into Windows Credential Manager from a
screen (`backend/jarvis_search.py:65, 183`). Worth the owner knowing: a
user environment variable is kept as plain text in the Windows registry.
Whether that meets rule 3 ("kept out of anything the app writes to disk in
plain text") is the owner's call - the app does not write it, the owner's
pasted command does.

### 9. Voice is seven long commands

About 850 MB in five downloads, each a PowerShell line of roughly 900-1,600
characters, a settings-file edit by script, a patch re-run, a test and a
restart (`backend/README.md:4776-4870`), then Smart Turn and the voice-ID
model in later sections (`:5001`, `:6770`), then "Train my voice" on the phone
before its talk button appears (`:4871-4873`). There is no in-app install
(`VoiceModels.kt` only reads status).

### 10. The default web search needs Docker

SearXNG is the decided default (`CLAUDE.md`, 2026-09-25) and needs Docker
Desktop with WSL 2 plus a settings change (`backend/README.md:8943`,
`:9034-9040`). INSTALL.md never mentions Docker (0 matches). DuckDuckGo,
already installed by `requirements.txt`, works with no extra step.

### 11. The docs are written for one PC

INSTALL.md uses `C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop
program` in six commands and says "change it if yours is elsewhere"
(`:40-41`); the patch script defaults to it (`apply-patches.ps1:73`).
Still open from the professionalism audit, item 13 (`PROFESSIONALISM-AUDIT:51`),
as is the missing log file for the patch script (no `Start-Transcript` or
`Tee-Object` in the script) and the missing `jarvis-client/README.md` (item 21;
the file does not exist).

### 12. The phone has no welcome at all

After install the phone opens straight on "Pair with your desktop" with two
boxes (`PairingScreen.kt:123-178`). The desktop's three-screen walkthrough has
no phone counterpart, and `docs/ARCHITECTURE.md` §8 "One-sided on purpose"
(`:1106` on) does not say why (no "walkthrough"/"onboarding" in it), which
`CLAUDE.md`'s parity rule asks for. `tools/check_parity.py` passes, because it
checks API routes, not windows. The UI audit asked for the same
(`UI-AUDIT-2026-09-26.md:103`, item 16); still not done.

## Earlier audits: what is fixed, what is still open (setup items only)

| Item | Status | Evidence |
|---|---|---|
| Professionalism #2: no desktop download | **Open** | GitHub releases: only `client-latest` |
| Professionalism #13: patch script has the owner's folder as default, no log | **Open** | `apply-patches.ps1:73`; no transcript |
| Professionalism #21: no `jarvis-client` README | **Open** | file missing |
| UI #4a: walkthrough showed "thinking" in amber | **Fixed** | `onboarding.html:87-88` use `--state-thinking` / `--state-approval` |
| UI #16: pairing as a small welcome; §8 note | **Open** | `PairingScreen.kt:123-129`; §8 has no entry |
| Approvals "found along the way" #1: shipped settings lacked the read lines | **Fixed** | `backend/rebuilt/jarvis-framework.toml:90-93` |
| Feasibility I119: preflight with "Fix" buttons | **Later**, "not first run - the owner is set up" | `FEASIBILITY-AUDIT-2026-09-26.md:271` |

## The planned guided setup, compared

The design (`docs/CUTTING-EDGE-2026-09-26-round2-experience.md:143-156`,
idea I119): a checklist with a tick per step, skippable and resumable -
Start Jarvis, the model answers, your voice, pair your phone (QR), web search
provider, what leaves this PC.

- **It covers** problems 4, 5 and part of 3, 9 and 10 above.
- **It cannot cover** problems 1, 2 and the Tailscale install in 3, because
  they happen before the desktop app exists. Those need docs and a published
  installer.
- **It is missing four steps** a newcomer needs: "Can your phone reach this
  PC?" (listening address + firewall), "Turn on what Jarvis can do" (tools),
  "Email and calendar", and "Jarvis starts by itself".
- **"Not first run - the owner is set up"** (`FEASIBILITY-AUDIT:271`) is true
  today but the owner will set up again: the second graphics card is coming
  (`CLAUDE.md`), a reinstall or new PC means doing all of the above again, and
  the owner is a beginner. The same checklist is also the best "is everything
  still working?" screen afterwards.

## Concrete fixes

Sizes: S = under a day, M = a few days, L = a week or more. All stay inside
the five rules and the dated decisions.

| # | Fix | App | Size | Owner's call? |
|---|---|---|---|---|
| 1 | Make the updater signing key (the owner's 10 minutes, `jarvis-desktop/README.md` "Turning on updates") so CI publishes `desktop-latest`. Until then, add to INSTALL.md 2.1: "or download the installer from the latest **Desktop release** run on GitHub (Actions tab), kept 14 days" | Docs / owner | S | Yes (the key) |
| 2 | A one-line backup of the backend folder (zip to a USB drive or another disk, with the date), in INSTALL.md 1.3, and a line in the preflight when no backup newer than 30 days is found next to it | Docs, backend | S | No |
| 3 | Decide whether the unshipped backend files (`jarvis_hud.py`, `jarvis_gate.py`, ...) go into the repo, so a fresh PC can be set up from GitHub alone | Repo | M | **Yes** |
| 4 | "Start Jarvis for me": the desktop finds `python.exe` itself (it can run `py -3 -c "import sys; print(sys.executable)"`) and asks only for the backend folder with a folder picker; the offline bar gets a **Start Jarvis** button next to Reconnect | Desktop | M | No |
| 5 | Say under "Let my phone reach this" that it only works when the desktop starts Jarvis, and offer to switch that on; or write `[security].bind_address` into the settings file so a hand-started Jarvis uses it too (`INSTALL.md:616-624` says that setting works) | Desktop | S (words) / M (file) | No |
| 6 | Two new preflight checks: "Is Jarvis listening where the phone can reach it?" and "Does the firewall let the phone in?" (read-only: list the listening sockets and the inbound rules for port 4719) | Backend | S-M | No |
| 7 | Make the phone's messages agree: the refusal message should not suggest 192.168/.local while those cannot connect, and Help and INSTALL.md should give the same first thing to check | Phone, docs | S | Changes a shared message table (both apps' tests) |
| 8 | Until QR pairing lands: a "Show" eye on the phone's token field, and the PC shows the token in groups of four characters (display only, same 60 seconds) | Both | S | Mild - the owner may prefer the field to stay hidden |
| 9 | QR pairing with per-device keys (I102), already decided | Both | L | Decided |
| 10 | Tailscale steps in INSTALL.md part 3: install on both, sign in with the same account, turn on MagicDNS, where to read the name and the `100.x` address; and one line in `README.md` "Install it": "the phone needs Tailscale or NordVPN Meshnet, even at home" | Docs | S | No |
| 11 | Walkthrough screen 1: mention the `^` overflow and dragging the icon to the taskbar; screen 2: "or the shortcut Settings shows"; add a screen 0 "Is Jarvis running?" with the live link state. Open the HUD **after** the walkthrough is closed, not with it | Desktop | S | No |
| 12 | Phone: the pairing welcome from UI audit item 16, and a §8 line on why there is no three-step tour | Phone, docs | S | No |
| 13 | A "Turn on" switch per tool in "What Jarvis can reach", each raising the usual card (turning off immediate), instead of Notepad | Both + backend | M | Loosening from an app: the 2026-09-26 "What asks first" decision limits loosening to the PC and a short list, so the owner should say whether turning a tool **on** counts |
| 14 | Email and calendar secrets into Credential Manager (like the web search keys), with a PC-only screen to enter them | Desktop + backend | M | **Yes** (ARCHITECTURE says "no screen" on purpose for the calendar link) |
| 15 | Voice in one command (steps 1-5 together, stopping at the first bad checksum), then later a PC-only "Install voice" button behind a card | Docs, then desktop + backend | S, then M | The button is a new download from GitHub: the owner's call |
| 16 | INSTALL.md: set the backend folder once (`$B = "..."`) and use `$B` in every later command; the patch script asks for the folder when none is given instead of defaulting to the owner's | Docs, script | S | No |
| 17 | The guided setup (I119) moved from "Later" to after the current fix pass, with the four missing steps above | Both | M | **Yes** (queue order) |

## Not checked

- Anything on real Windows or a real phone: download times, the VS Build
  Tools size, whether Windows 11's `tar` unpacks the voice archives (the voice
  section says so too, `backend/README.md` "Not checked").
- What the HUD shows with a live backend (I rendered the browser preview only).
- Whether saving "Let my phone reach this" restarts a supervised Jarvis.
- Whether the GitHub repository is public; if private, a phone's browser
  cannot download the APK without signing in (`INSTALL.md:78-79` hints at
  this).
