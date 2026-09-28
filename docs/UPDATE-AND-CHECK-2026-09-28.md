# Update Jarvis on your PC and phone, and check it works (2026-09-28)

Written after the audits of 2026-09-28
([`AUDIT-2026-09-28-AFTER-CHANGES.md`](AUDIT-2026-09-28-AFTER-CHANGES.md)).
It builds on [`INSTALL.md`](INSTALL.md) ("Updating everything"); where the two
differ, this page is newer.

**Read this first.** Most of the new work (chatbot compare, Jarvis Live,
Goals, phone notifications, the monkey, Lockdown, Today and the rest) is
still on five branches that are **not merged into `main`**, and nothing
reaches your devices until it is. So there are two rounds:

- **Round 1, today:** update to what is on `main` now - the three animal
  faces (pull request #20) and "the rules stay first" (#21).
- **Round 2, after the five branches are merged:** the same steps again,
  then the longer checklist.

Every PowerShell command below is **one line**: copy the whole line, paste,
press Enter. Each was checked for PowerShell 5.1 (the one Windows comes
with) by reading, and parsed by PowerShell 7 here; none was run on a real
Windows PC. Where a path says `pcadmin` or `Desktop program`, it is your
backend folder as written in INSTALL.md; change it if yours moved.

---

## Round 1 - update to today's `main`

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

### 3. The phone

The phone app on the `client-latest` release is already built from today's
`main` (version 0.2.206, commit `f81d230`, "tested on an emulator before
publishing"). On the phone, open
<https://github.com/darknight11ish/Epic-Jarvis/releases/tag/client-latest>,
tap `jarvis-client-f81d230.apk`, and install it over the old one. It stays
paired.

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
   owl, then the otter. Each should move gently and blink. **Known, not yet
   fixed:** "Voice follows the face" starts ON and the otter uses the "Sky"
   voice - both against your 2026-09-28 decision; turn the switch off by
   hand for now.

---

## Round 2 - getting the five branches in

### Before anything merges: what must be fixed first

These block a safe merge. Each is in the audit report named, with the file,
the line and a proposed fix:

| # | What | Branch | Report |
|---|---|---|---|
| 1 | One-time codes get past the phone's hiding filter | continuation | [04 security](audit-2026-09-28/04-security.md), [01 Android](audit-2026-09-28/01-bugs-android.md) |
| 2 | Your animal-voice decision (starts off, one-time question, otter not "Sky") | mascot | [06 decisions](audit-2026-09-28/06-decisions.md) |
| 3 | The five "right after the sources block" patches, and the four "is last" tests | all five | [05 merge](audit-2026-09-28/05-merge.md) |
| 4 | Desktop `send()`: Live and "Try the cloud model" clash | research + continuation | [05 merge](audit-2026-09-28/05-merge.md) |
| 5 | API section numbers §59-61 and the phone's settings index 12 used twice | all | [05 merge](audit-2026-09-28/05-merge.md) |
| 6 | The web address in a code comment in `faces.html` (fails a test) | GitHub repos | [10 sessions](audit-2026-09-28/10-threads.md) |

Items 3-5 are already solved in the combined copy this audit built.

### How it gets merged - your choice

- **Recommended: one pull request with everything.** Let one Claude
  session push the combined, already-resolved copy plus fixes 1, 2 and 6
  as one branch, open one pull request, and get GitHub's checks green on
  it. It is the only way the phone app gets built from the combined code
  before it reaches you, and it avoids five rounds of clashes.
- **Or five pull requests, one at a time, in this order:** continuation (it
  has no pull request yet - ask its session to open one), GitHub repos,
  competitor audit, research, mascot. After each merge, the next session
  brings `main` in and fixes the clashes before you merge it.

Either way: **you press Merge** on GitHub, only when its checks are green.

### After it is merged

Do Round 1's steps 1, 2 and 4 again (backend, desktop, live check). For
the phone, **wait until the `client-latest` page names the new `main`
commit** (it is only published after the emulator test passes on that
exact file; it says "from `main`, commit ..." at the top), then install it.

**New pairing?** No. Pairing is unchanged in all five branches (QR pairing
is still for later), so the phone stays paired.

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
  off from the phone: immediate. **Known gap:** turning it off from the PC
  only reaches the phone next time its settings page opens.
- [ ] **One-time codes hidden** (after fix 1): with notifications on for a
  test app, send yourself "Use 482913 to log in". Ask Jarvis "what are my
  latest notifications?". The code shows as `[hidden code]`.
- [ ] **Goals:** "set a goal: walk three times a week". One card to accept;
  ticking a step off needs no card.
- [ ] **The plan card stays off.** Ask for three things in one go. You get
  one card per acting step, never one card for several.
- [ ] **Chatbot compare** (Brain → the chatbot section on the PC): compare
  a general question. A card shows exactly the words to be sent and which chatbots
  (at most 3 on one card). Nothing is sent before you approve.
- [ ] **Jarvis Live** (PC): start it, talk, pause, stop. It answers in
  short spoken sentences; pressing Stop everything (Alt+Shift+X) ends it at
  once. Try talk-to-type (Alt+Shift+T) while Live is on: **known gap**, the
  message blames "Hey Jarvis".
- [ ] **Lockdown:** turn it on. Timers still ring; nothing else runs by
  itself. **Known gap:** a chatbot comparison already running, and the
  weather, keep going.
- [ ] **Today / widgets / tiles:** the Today page shows the day; a
  quick-settings tile on the phone never offers Approve.
- [ ] **Faces:** all four animals (with the monkey) on both apps; the Zs
  when on standby; "Voice follows the face" starts OFF and asks once (after
  fix 2).
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
