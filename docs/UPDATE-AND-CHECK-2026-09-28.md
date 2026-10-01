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

   **If nearly every patch says "not onto the files as they are"** and near
   the top it says `Endings : ... CRLF`, your backend's files have Windows line
   endings (the patches use Unix ones). Add `-FixLineEndings` to the end of the
   same command: each affected file is copied into a
   `_jarvis-backup-<date>-endings` folder first, then only its line endings
   change (2026-09-30). Also make sure the clone is on the real `main`
   (`git status -sb` shows `## main...origin/main`), not an old branch.
   Your files are converted only **after** the whole rehearsal has worked and
   every other check has passed (changed 2026-09-30; before that they were
   rewritten first, so a run that then stopped had still changed them). If a
   file cannot be replaced (Jarvis still has it open), the run puts the files
   it already converted back, names the locked file, and says to close Jarvis.

   **How to read the end of the run (changed 2026-09-30).** The last lines
   are one of three things, in plain words:

   - a **green "ALL DONE - the backend is patched and proven"**: the patches
     are on, every test suite ran, none was skipped. Restart Jarvis.
   - a **yellow "DONE - no problems, but NOT fully proven"**: the patches are
     on, but the tests were skipped (`-SkipTests`), or some suites skipped
     parts of themselves (it names them), or it was a partial install
     (`-SkipMissing`). The line under it says which.
   - a **red "DONE WITH PROBLEMS"** with a numbered list, and the window's
     exit code is 1. It says whether any of your files were changed. If the
     patched files may be **half updated**, it says so, says **not to start
     Jarvis**, and prints **one line** that puts every file back exactly as it
     was (copy it whole, paste, press Enter); after that, close Jarvis and
     start it again.

   Two new checks: the script stops and says **Close Jarvis first** if a
   Python program that looks like Jarvis is running (add `-Force` to go ahead
   anyway), and after the patches go on it checks the real files a second
   time instead of trusting the patch tool's "ok". If your backend folder sits
   inside another git repository, the script tells git to ignore that
   repository for the run, so the rehearsal and the real run behave the same.

   **Old backups pile up.** Every run that changes something makes a
   `_jarvis-backup-<date>` folder (and `-endings` ones) inside your backend
   folder, and nothing deletes them. The last screen prints where this run's
   backup is. After a good run you can delete the old `_jarvis-backup-*`
   folders (keep the newest one for a while).

   **Worked if:** it ends with the green "ALL DONE" (or the yellow "DONE" and
   you understand the line under it), and a line naming the log file (in
   `_jarvis-logs` inside your backend folder).
   **If not:** send back that log file. The red screen says whether anything
   was changed: "None of your backend files were changed" means nothing was.
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
5. Signed approvals: after turning them on (checklist below), the PC really
   accepts a signature from the phone's fingerprint or PIN. This is the one
   thing that could not be tried without a real phone; if the PC says "did
   not accept" every time, tell me and do not retire the old shared key.

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
- [ ] **Signed approvals** (needs a phone paired the new way): on the phone,
  try to approve a risky card (say, "send an email to yourself"). It says
  signed approvals are not on and offers **Turn on signed approvals**; press
  it, and approve the card that appears on the PC (Windows Hello). Now try a
  risky card again: the phone asks for your fingerprint or PIN, and the PC
  accepts it. Deny, and cards that are not risky, work as before. Removing
  the phone in the PC's Devices list stops it approving anything.
- [ ] **An app in Projects** (PC, then phone): Projects, **New project**,
  **An app Jarvis builds**, then **Start a task**, and **Paste a change in**
  (blocks that start with `<<<FILE name>>>` and end with `<<<END>>>`). Open
  the task and read the whole change, then **Merge**. One card appears with
  every file and the whole change; say no first (nothing changes), then merge
  again and say yes (Windows Hello). On the phone the same project shows the
  app and its tasks; **Merge** opens only after you have paged to the end of
  the change. Jarvis does not write the code or run any commands yet.
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
- [ ] **Review decks and Spanish practice** (added 2026-09-30). **First run
  `apply-patches.ps1` again** (Round 1's step 1): it copies in the new
  `jarvis_decks.py` and `decks.patch`, and it installs **one new pinned
  package, py-fsrs 6.3.2** (from `backend\requirements.txt`; it works out when
  a card comes back, and Jarvis never installs its optimizer, which needs
  torch). Without that package the decks screen says so in a red line and
  refuses to keep anything. Then: Brain, Work, **Quiz me on a text**, answer a
  question or two, press **Keep these questions**, write the answer in your own
  words and press **Keep and finish** (for a Spanish quiz the sheet also shows
  the line saying Jarvis cannot recognise a crisis message written in Spanish).
  **My study decks** now lists the deck; press **Review** (a deck with cards
  ready), **Show answer**, then one of the four buttons. **Review all decks**
  (PC) and **Review** over the list (phone) do every deck in one go, and the
  phone can now rename a deck (**Edit**). Under **Coming up** the daily job is
  called **Card review** and has no Pause or Delete. **The decks are in the
  locked backup**, with their own key, under the same recovery code; a restore
  brings the decks back and the app reopens them (**nobody has restored one on
  a real PC yet - tell us if it does not**).
- [ ] **Retirement what-if** (PC: Brain → Work → Retirement; phone: Brain →
  Retirement). Type: age now 40, stop working at 65, savings 100000, add 12000
  a year, spend 30000, then press **Work it out**. You get a range ("in about
  N of 100 simulated futures ..."), the line "This is a simplified what-if,
  not financial advice." right under it, and a "What I used" list. The return
  box starts at **6** and is marked "assumed" (a placeholder for a mix of
  stocks and bonds, not a forecast); the pension box shows a grey **0**.
  Turn on "Hide memory lists and chat history": the card shows only
  "Retirement what-if hidden" and a **Show** button, and nothing you typed
  comes back. Nothing is read aloud or saved. **In chat** (after you add
  `"retirement_whatif"` to `[tools].enabled`): type "what if I retire at 65
  with 100,000 saved, adding 12,000 a year and spending 30,000 a year?". The
  answer is Jarvis's own fixed text with that same disclaimer, not a chatty
  sentence, and no approval card appears. Leave out a number ("what if I retire
  at 65?") and Jarvis asks for it instead of guessing. Ask by voice: the answer
  is written on screen and the numbers are not read out. Ask it right after
  Jarvis read an email in the same chat: it refuses and tells you to type the
  numbers in a new message.

- [ ] **Spending summaries** (chat, and PC: Settings → Spending). Spending is a
  settings-file tool, not a switch in the PC app: add `"my_spending"` to
  `[tools].enabled` in `jarvis-framework.toml` (the `[tools]` section, beside
  `my_files`), run `apply-patches.ps1` once (it installs `openpyxl 3.1.5`, which Excel
  files need), restart Jarvis, and make sure a folder is listed under "Folders Jarvis may
  look in". Drop a bank export (CSV or Excel) in it and ask "how much did I spend on food
  last month?". The first time, Jarvis says the columns must be checked on the PC:
  Settings → Spending → pick the file → **Check these columns**. The box now says how
  many rows count as money out and as money in **before** you save; if that looks wrong
  the box warns you. **Check the columns again** never deletes the layout: it opens the
  same box with your saved choices and Save writes over it. Ask a second question in the
  same chat and then a web search: the search asks first ("Jarvis looked at your bank
  spending earlier in this conversation"). Jarvis's one sentence only ever uses the totals
  and the rows it names; if it cannot make a table it shows a plain sentence and no
  figures.

- [ ] **Progress: the activity map and the balance chart** (PC: Brain →
  Projects, at the top; phone: Brain → Projects, "Progress"). **First run
  `apply-patches.ps1` again** (Round 1's step 1): this round changed
  `jarvis_projects.py` and `jarvis_goals.py` as well as the new
  `jarvis_progress.py`, and the script copies them all in. Then: (1) tick a
  goal's step and log a number on a benchmark - today's square gets darker; the
  five shades are clearly different from each other in every theme (try
  Daylight); a quiet day is just an outline. (2) In **Choose what to show**, pick
  3 to 8 numbers or goals and press **Save the chart**: both apps say **Chart
  saved.**; the chart keeps the order it had and a newly ticked area goes last.
  (3) Stop a goal that is on the chart: it leaves the chart, and steps you had
  ticked in it leave the map. (4) Turn on "Hide memory lists and chat history"
  with a health or money number on the chart: each picture shows only the
  "Hidden while memory lists and chat history are hidden." line and a **Show**
  button, there is no **Choose what to show** button, and nothing can be saved.
  On the PC with App lock on, Show says to unlock Jarvis first. (5) Phone: pick an
  area whose value is long ("1234567.5 of 2000000 kg") - its label wraps and stays
  inside the picture. Nothing here is read aloud or sent anywhere.

- [ ] **Study helper and Referee suggestions (only once the 12 GB card is in;
  both are OFF and cannot be turned on before, and say why).** (1) Settings →
  Second graphics card (or the phone's Brain) now lists seven switches. With one
  card, **Study helper** and **Referee suggestions** say "Needs a capable second
  graphics card". (2) With the card in, turn on **Study helper**: one card naming
  the card and `qwen3:8b`. Paste a text into "Quiz me on a text": the questions
  come from the second card (`ollama ps` on port 11435 shows the model) and the
  marks still say "Jarvis's guess" until you run
  `OLLAMA_URL=http://127.0.0.1:11435 JARVIS_LOCAL_MODEL=qwen3:8b python backend\eval_quiz_grader.py`.
  Turn it off: the quiz works as before. (3) Turn on **Referee suggestions**: one
  card, no model, no second Ollama starts. Make a goal step follow a number
  (Projects), set a target, then log a number that reaches it: within the hour a
  card "This looks done - tick it?" shows the numbers and says "a suggestion from a
  number, not a check". Say no: nothing is ticked and it does not ask again for a
  day. Say yes: the step is ticked; untick it in Goals. For a weight or money
  number the card says it is private. **Nobody has seen either card on a real PC.**

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

---

## Later - better voices (Kokoro v1.0, "Hear it"): only once that pull request is merged

Not on `main` yet (2026-09-29). When it is:

1. **Update the backend and both apps** the usual way (steps above). Nothing
   about how Jarvis sounds changes yet: the voice list now has a **Hear it**
   button on every voice (desktop: Settings, "Jarvis's built-in voice"; phone:
   the Voices screen), and a line under it says better voices are available.
   Your choice carries over on its own - the first time the PC is asked, a
   saved number becomes the voice's name (number 9 was George; it stays George).
2. **Optional: the new voice pack** (350 MB, one line). It is in
   `backend\README.md` under **"Upgrade the voice pack to Kokoro v1.0"**: copy
   that one line, paste it into PowerShell, wait for "OK - the new voices are
   in ...", then quit Jarvis from the tray and start it again. It checks the
   download first and installs nothing if it is not the expected file; your old
   pack stays beside it as `tts-old-...` so going back is a rename.
   **Optional, after that: Ashby and Clara** (two voices blended for Jarvis; they
   need the new pack). In `backend\README.md`, under **"Make Ashby and Clara"**,
   copy the one line, paste it into PowerShell and wait for "OK - Ashby and Clara
   are in ... voices-jarvis.bin"; then quit Jarvis from the tray and start it
   again. It makes a 28 MB file beside your voice pack and touches nothing else;
   until you do, the voice list says they are not made yet. Run the line again
   after any later voice-pack upgrade. **Check it**: both appear at the top of
   the voice list with a line under each; press **Hear it** on each (the first
   time takes a few seconds - Jarvis checks it does not sound like you); choose
   Ashby and ask Jarvis something: a calm British man, a little slower than the
   others - **nobody has listened to either, so tell us if it sounds wrong**.
3. **Check it** (five minutes): open the voice list, press **Hear it** on
   three voices - Heart, Bella and George - and confirm each one plays and the
   voice Jarvis uses does not change; press Hear it while Jarvis is talking (it
   should say it is busy). Pick a British voice (Emma or George) and ask
   Jarvis a question: it should sound British, not American - **nobody has
   listened to this yet, so tell us if it does not**. With an animal face on,
   the animals still sound like themselves.
4. **Optional, one more line: exact mouths on the new voices** (added
   2026-09-29). After step 2, the animals' mouths follow the sound, not
   Kokoro's own timing, until you run the same one line as for the old pack
   (`backend\README.md`, **"Mouths that match the words"**, step 2 - it now
   works on v1.0 too; about ten seconds, it writes one 56 MB file
   `model.durations.onnx` next to the voice model and says where). It never
   changes the voice pack, and if it says "this is not the Kokoro v1.0 model
   file", nothing was made and the mouths simply stay as they are now. Then
   restart Jarvis, turn an animal face on, ask something out loud, and watch
   that the lips close on "m", "b" and "p" and round on "oo" and "w" - **nobody
   has watched this on a v1.0 voice yet, so tell us how it looks**.
