# Update Jarvis on your PC and phone, and check it works (2026-09-28)

Written after the audits of 2026-09-28
([`AUDIT-2026-09-28-AFTER-CHANGES.md`](AUDIT-2026-09-28-AFTER-CHANGES.md)).
It builds on [`INSTALL.md`](INSTALL.md) ("Updating everything"); where the two
differ, this page is newer.

**Read this first (updated after pull requests #23 and #25 were merged).**
Everything the sessions had built by the evening of 2026-09-28 is now on
`main`: the five branches (chatbot compare, Jarvis Live, Goals, phone
notifications, the monkey, Lockdown, Today and the rest) came in with #23,
and **QR-code pairing with a key per device**, the audits' fixes and the
one-time animal-voice question came in with #25 (and a small follow-up
after it). So:

- **Use Round 1's steps 1, 2 and 4** (backend, desktop, quick check) as the
  update steps - they still work - but **not its step 3**: that names an
  old phone build. Ignore the rest of Round 1's wording; it was written
  before the merge.
- **Then "After it is merged"** (it says how to get the right phone build
  and how to try the new pairing), then the **checklist** and the
  **measurements**.
- **Not on `main` yet:** work other sessions pushed afterwards - mainly
  customer-support chats (research session) and the animal-options page
  (animal-face session). It arrives in its own later pull request.

Every PowerShell command below is **one line**: copy the whole line, paste,
press Enter. Each was checked for PowerShell 5.1 (the one Windows comes
with) by reading, and parsed by PowerShell 7 here; none was run on a real
Windows PC. Where a path says `pcadmin` or `Desktop program`, it is your
backend folder as written in INSTALL.md; change it if yours moved.

---

## Round 1 - the update steps (written before the merge: use steps 1, 2 and 4 only)

### 1. The backend on the PC

1. Stop Jarvis: close the PowerShell window it runs in, or quit the desktop
   app from the tray if the app starts Jarvis for you.
2. Get the new code and put it into your backend (one line). It rehearses
   every change on a copy first and stops, saying **NOTHING HAS BEEN
   CHANGED**, if anything would not fit:

   ```powershell
   cd "$env:USERPROFILE\Epic-Jarvis"; git checkout main; git pull; powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -BackendPath "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"
   ```

   **Worked if:** it ends with a test summary and no `FAIL` lines, and a
   line naming the log file (in `_jarvis-logs` inside your backend folder).
   **If not:** send back that log file. Nothing was changed if it says so.
3. Make Ollama refuse its own cloud models (a second lock behind rule 1,
   decided 2026-09-26; the second-card setup lines already set it for that
   card, but the patch script does not set it for your main Ollama).
   One line, then close Ollama from its tray icon and start it again:

   ```powershell
   [Environment]::SetEnvironmentVariable('OLLAMA_NO_CLOUD', '1', 'User'); Write-Host "Saved. Quit Ollama from its tray icon and start it again."
   ```

4. Start Jarvis again (INSTALL.md step 1.8), or let the desktop app start it.

### 2. The desktop app

There is still no ready-made download (the update signing key is not set
up), so build it again, then run the new installer over the old one. Your
settings stay. One line (it takes a few minutes):

```powershell
cd "$env:USERPROFILE\Epic-Jarvis\jarvis-desktop"; npm install; npm run tauri build; explorer "$env:USERPROFILE\Epic-Jarvis\jarvis-desktop\src-tauri\target\release\bundle\nsis"
```

A folder opens: double-click the `...-setup.exe` in it.

### 3. The phone (old - use "After it is merged" below instead)

The phone app on the `client-latest` release was, when this was written, built from that day's
`main` (version 0.2.206, commit `f81d230`, "tested on an emulator before
publishing"). On the phone, open
<https://github.com/darknight11ish/Epic-Jarvis/releases/tag/client-latest>,
tap `jarvis-client-f81d230.apk`, and install it over the old one. It stays
paired. **Do not install that one now** - it is older than the merge; wait
for the page to name the newest `main` commit (see "After it is merged").

### 4. Quick check

1. The live check (one line; the result is also saved on your Desktop as
   `preflight.txt`):

   ```powershell
   cd "$env:USERPROFILE\Epic-Jarvis"; $env:JARVIS_BACKEND = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; $env:PYTHONIOENCODING = "utf-8"; py -3 backend\selftest.py --preflight | Tee-Object -FilePath "$env:USERPROFILE\Desktop\preflight.txt"; Write-Host "Saved to $env:USERPROFILE\Desktop\preflight.txt"
   ```

   **Worked if:** the last line reads "N pass, 0 fail". A `warn` is fine if
   its line says why. A `fail`: send back `preflight.txt`.
2. **The rules stay first** (PR #21): in the Jarvis bar, ask "who are you
   and what won't you do?". It should answer as Jarvis, briefly, and mention
   asking before acting.
3. **The animal faces:** Settings → Faces, pick the red panda, then the
   owl, then the otter. Each should move gently and blink. (The old note
   here, that "Voice follows the face" starts on and the otter uses the
   "Sky" voice, is fixed: it starts off, and the otter uses another voice.)

---

## Round 2 - how the five branches got in (done)

### Before anything merges: what must be fixed first

These block a safe merge. Each is in the audit report named, with the file,
the line and a proposed fix:

| # | What | Branch | Report | Status |
|---|---|---|---|---|
| 1 | One-time codes get past the phone's hiding filter | continuation | [04 security](audit-2026-09-28/04-security.md), [01 Android](audit-2026-09-28/01-bugs-android.md) | fixed in the combined pull request |
| 2 | Your animal-voice decision (starts off, one-time question, otter not "Sky") | mascot | [06 decisions](audit-2026-09-28/06-decisions.md) | fixed: starts off, otter not "Sky", and the one-time question (each animal asks once for itself) came in with #25 |
| 3 | The five "right after the sources block" patches, and the four "is last" tests | all five | [05 merge](audit-2026-09-28/05-merge.md) | fixed |
| 4 | Desktop `send()`: Live and "Try the cloud model" clash | research + continuation | [05 merge](audit-2026-09-28/05-merge.md) | fixed |
| 5 | API section numbers §59-61 and the phone's settings index 12 used twice | all | [05 merge](audit-2026-09-28/05-merge.md) | fixed |
| 6 | The web address in a code comment in `faces.html` (fails a test) | GitHub repos | [10 sessions](audit-2026-09-28/10-threads.md) | fixed |

### How it got merged - one pull request (your choice, 2026-09-28; done as #23)

All five branches, the fixes above and the audit's own fixes are in ONE
pull request from `claude/jarvis-post-change-audits-olihzo`. **You press
Merge** on GitHub, only when all its checks are green - that includes the
phone app being built and started on an emulator from the combined code,
which has never happened before.

Work the other sessions push to their own branches AFTER this pull request
was made is not in it; it goes in a later pull request.

### After it is merged

Do Round 1's steps 1, 2 and 4 again (backend, desktop, live check). For
the phone, **wait until the `client-latest` page names the new `main`
commit** (it is only published after the emulator test passes on that
exact file; it says "from `main`, commit ..." at the top), then install it.

**New pairing?** Yes, but nothing forces you to redo it. QR-code pairing
with a key for each device is built (design: `PAIRING-DESIGN.md`, API:
`JARVIS-API.md` section 90). Your phone **stays paired with its old shared
key**, which keeps working until you retire it. To try the new way: PC,
Settings, **Devices**, **Pair a phone**; on the phone, Settings or the
pairing screen, **Scan the code on your PC** (or type the 8-letter code).
Both screens show the same four words; approve the card on the PC (with
Windows Hello) only if they match.

**The half-hour test before you retire the old shared key.** Retire is
the one step you cannot try safely on paper, so check these four things
first (each fails safe if wrong):

1. On the PC, in PowerShell: `tailscale status --json` prints something and
   the PC's own name (`Self`, `DNSName`) is in it.
2. Pair the phone the new way, then in Devices press **Remove** for it: the
   phone's live connection drops within about 10 seconds.
3. When the pairing card appears on the PC, the Windows Hello prompt comes
   to the front (not hidden behind another window).
4. The phone connects through Tailscale or NordVPN Meshnet (not home
   Wi-Fi); pairing over plain home Wi-Fi is refused with a plain message.

If any fail, do not press **Retire the old shared key**; send back what you
saw. Not built yet: the fingerprint-signed "yes" for risky cards on the
phone (phase 2 of the design), and the check that the phone's security
chip is genuine (left out on purpose, see design section 9).

---

## The checklist - does each new thing work?

Do these after Round 2. "PC" is the desktop app, "phone" is the phone app.
Each line says what you should see, **as the code says it should behave -
none of this has been tried on a real device yet**, and a button's exact
name may differ slightly from what is written here. If something does not
happen, write down which line and what you saw instead.

### The five rules first

- [ ] **Nothing approves by itself.** Ask (PC): "write a note saying test in
  my notes". An approval card appears; wait without pressing anything - it
  times out, and no note is written.
- [ ] **Stale link blocks acting.** Stop Jarvis on the PC while the phone
  shows a card. Within a few seconds the phone greys out Approve and says
  the PC is not reachable.
- [ ] **No public tunnel.** Phone: Settings → server address, type an
  ngrok-style address (`https://abc.ngrok.io`). It is refused, with a plain
  reason.
- [ ] **Private stays local.** Ask (PC) something that mentions an email you
  received, then press "Try the cloud model" if it appears. It must say it
  will not send private or outside text to the cloud.
- [ ] **Keys stay hidden.** In Settings, any saved API key shows only dots
  and its last characters, on both apps.

### New features

- [ ] **A timer with the model unloaded.** Stop Ollama. Say or type "set a
  timer for 1 minute". It is set anyway and rings.
- [ ] **Phone notifications, off by default** (phone): Settings → Phone
  notifications shows OFF. Turning it on raises a card on the PC. Turn it
  off from the phone: immediate. Turn it off from the PC: the phone stops
  saving new ones within about 15 seconds of the next capture, and what it
  had saved is deleted; "Delete captured notifications" on that page does
  the same by hand (it asks "are you sure?" first).
- [ ] **One-time codes hidden:** with notifications on for a
  test app, send yourself "Use 482913 to log in". Ask Jarvis "what are my
  latest notifications?". The code shows as `[hidden code]`.
- [ ] **Goals:** "set a goal: walk three times a week". Accepting sets up
  the weekly check-in straight away, **with no card** (like a repeating
  reminder); ticking a step off needs no card either.
- [ ] **The plan card stays off.** Ask for three things in one go. You get
  one card per acting step, never one card for several.
- [ ] **Chatbot compare** (Brain → the chatbot section on the PC): compare
  a general question. A card shows exactly the words to be sent and which chatbots
  (at most 3 on one card). Nothing is sent before you approve.
- [ ] **Jarvis Live** (PC): start it, talk, pause, stop. It answers in
  short spoken sentences; pressing Stop everything (Alt+Shift+X) ends it at
  once. Try talk-to-type (Alt+Shift+T) while Live is on: it says "Jarvis Live
  is using the microphone. End Live first, or just talk to Jarvis."
- [ ] **Lockdown:** turn it on. Timers still ring; nothing else runs by
  itself, and a chatbot conversation or comparison that was already running
  stops, and the online weather behind the animal stops.
- [ ] **Today / widgets / tiles:** the Today page shows the day; a
  quick-settings tile on the phone never offers Approve.
- [ ] **Faces:** all four animals (with the monkey) on both apps; the Zs
  when on standby; "Voice follows the face" starts OFF. The first time you
  pick each animal it asks "The Red Panda has its own voice. Use it?" - once
  per animal; "Use it" for one animal does not change another. Later, in
  the voice settings, each animal's row has **Use its own voice** or **Keep
  my voice** to change your mind.
- [ ] **Picking a face on the PC:** the Faces window: Tab once reaches
  "Skip to the faces"; **Use this face** applies and saves at once, with
  Undo.
- [ ] **Widgets under App lock:** turn App lock on. On the phone, a
  home-screen widget button opens Jarvis to unlock instead of acting (Stop
  everything still works); on the PC widget, Focus, timer and music open the
  Jarvis bar instead of acting.
- [ ] **QR pairing and Devices** (both apps): see "New pairing?" above; the
  Devices list on both apps shows each device with **Remove**, and marks
  this one.
- [ ] **Inbox tidy (only after you add `"tidy_inbox"` to `[tools].enabled`;
  not tried on a real mailbox yet):** send yourself three emails with
  "tidytest" in the subject and follow the seven steps in
  `backend/README.md`, "Inbox tidy" (mark as read, star, archive, Trash, each
  with Undo; a too-big request; Undo gone after 11 minutes). The card lists
  all three emails; the PC asks Windows Hello when you approve; saying "yes"
  out loud approves nothing; "delete" only ever moves to Trash. Write down
  the step and your mail provider if anything is off.
- [ ] **Backup:** Settings → Backups → make one now. A locked file appears
  in the folder you chose, and the recovery code is shown once.

### Measurements only your PC can make

1. **Memory tests with the real model** (they decide the entity layer; the
   results open in a folder):

   ```powershell
   cd "$env:USERPROFILE\Epic-Jarvis"; $env:JARVIS_BACKEND = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; py -3 backend\eval_memory.py --learner-model qwen3:8b; explorer "$env:USERPROFILE\jarvis-memory-eval"
   ```

   Then the long-conversation test (after Round 2; it prints "Found all @5"):

   ```powershell
   cd "$env:USERPROFILE\Epic-Jarvis"; $env:JARVIS_BACKEND = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; py -3 backend\eval_memory.py --locomo | Tee-Object -FilePath "$env:USERPROFILE\Desktop\locomo.txt"; Write-Host "Saved to $env:USERPROFILE\Desktop\locomo.txt"
   ```

   Send both results back. If the entity layer still loses, this turns it
   off (then quit Jarvis from the tray and start it again):

   ```powershell
   [Environment]::SetEnvironmentVariable('JARVIS_MEMORY_ENTITIES', '0', 'User'); Write-Host "Done. Quit Jarvis from the tray and start it again."
   ```

   **A possible fix to try first: "skip very common names".** The entity
   layer loses mostly because a person named in most of memory floods the
   answers with their newest facts. There is now a switch that skips such
   a name (built 2026-09-28, **off** until your PC's numbers say it helps).
   On the build machine (words only, no real model) it took LoCoMo's
   "Found all @5" from 3.6% back up to 8.3% and left the main self-test
   unchanged - your PC's meaning search may differ. After the update steps, this one
   line runs both tests twice, without and with it, and opens the folder
   (`jarvis-memory-eval\common-cut` in your user folder, with an `off` and
   an `on` folder inside). It takes a while:

   ```powershell
   cd "$env:USERPROFILE\Epic-Jarvis"; $env:JARVIS_BACKEND = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; Remove-Item Env:JARVIS_MEMORY_ENTITY_COMMON_CUT -ErrorAction SilentlyContinue; $o = "$env:USERPROFILE\jarvis-memory-eval\common-cut"; py -3 backend\eval_memory.py --out "$o\off"; py -3 backend\eval_memory.py --common-cut --out "$o\on"; py -3 backend\eval_memory.py --locomo --out "$o\off"; py -3 backend\eval_memory.py --locomo --common-cut --out "$o\on"; Write-Host "Done. The results are in $o (off and on)"; explorer $o
   ```

   Each result file says near the top whether the cut was on. Send the
   four files back; if no number gets worse with it on, this keeps it on
   (then quit Jarvis from the tray and start it again):

   ```powershell
   [Environment]::SetEnvironmentVariable('JARVIS_MEMORY_ENTITY_COMMON_CUT', '1', 'User'); Write-Host "Done. Quit Jarvis from the tray and start it again."
   ```

2. **The tool test** (it decides whether the plan card may ever be switched
   on; results land in `tools\tool_eval\tool_eval_results.json` in the
   repository folder):

   ```powershell
   cd "$env:USERPROFILE\Epic-Jarvis"; py -3 tools\tool_eval\ollama_tool_eval.py --models jarvis-primary; Write-Host "Results saved in tools\tool_eval\tool_eval_results.json, inside this repository folder"
   ```

3. **How much of the graphics card the faces use.** It asks you to press
   Enter three times (face hidden, face showing, face showing while Jarvis
   answers), records about a minute each, and opens the folder with the
   results at the end (`jarvis-gpu-test` in your user folder):

   ```powershell
   $d = "$env:USERPROFILE\jarvis-gpu-test"; New-Item -ItemType Directory -Force -Path $d | Out-Null; $f = Join-Path $d ("gpu-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".csv"); "phase,time,card,gpu_busy_pct,card_mem_used_MiB,card_mem_total_MiB,power_W,jarvis_windows_MiB,ollama_MiB" | Set-Content -Path $f -Encoding UTF8; foreach ($p in @("1-face-hidden", "2-face-showing", "3-face-showing-while-Jarvis-answers")) { Read-Host "Step $p - get it ready, then press Enter (records for about 1 minute)" | Out-Null; for ($i = 0; $i -lt 30; $i++) { $w = 0; $o = 0; $wp = @(Get-Process -Name msedgewebview2 -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }); $op = @(Get-Process -Name ollama*, llama* -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }); try { foreach ($s in (Get-Counter -Counter "\GPU Process Memory(*)\Dedicated Usage" -ErrorAction Stop).CounterSamples) { if ($s.InstanceName -match "pid_(\d+)_") { $id = [int]$Matches[1]; if ($wp -contains $id) { $w += $s.CookedValue } elseif ($op -contains $id) { $o += $s.CookedValue } } } } catch { $w = $null; $o = $null }; $t = Get-Date -Format "HH:mm:ss"; foreach ($line in @(nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total,power.draw --format=csv,noheader,nounits)) { "$p,$t," + ($line -replace "\s", "") + "," + $(if ($null -eq $w) { "n/a" } else { [math]::Round($w / 1MB) }) + "," + $(if ($null -eq $o) { "n/a" } else { [math]::Round($o / 1MB) }) | Add-Content -Path $f -Encoding UTF8 }; Start-Sleep -Seconds 1 }; $log = "$env:LOCALAPPDATA\Ollama\server.log"; if (Test-Path $log) { $last = Select-String -Path $log -Pattern "offloaded \d+/\d+ layers to GPU" | Select-Object -Last 1; if ($last) { "$p,note,Ollama says: " + ($last.Line -replace ",", " ") | Add-Content -Path $f -Encoding UTF8 } } }; Write-Host "Done. The results are in $f"; explorer $d
   ```

   The audit's estimate: about 10-60 MB for the small faces, up to about
   230 MB for the big face at Maximum - small, but the 16K model setting is
   already about 0.6 GB over on the 8 GB card, so every bit counts.

4. **On the phone:** start Jarvis Live, turn the screen off, and keep
   talking for a minute. The audits could not tell whether newer Android
   stops it in the background.
