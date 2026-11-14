# Phone drive — agent-driven, 2026-11-03

**These are AGENT-DRIVEN observations, not owner field PASSes.** The owner delegated the
driving; an agent tap is not the owner's own hand. `docs/FIELD-TEST-MATRIX-2026-10-11.md`'s
rule stands: a probe PASS is not a field PASS, and BLOCKED/PARTIAL never become PASS. Each row
below is marked `AGENT-PASS`, `FAIL`, or `BLOCKED` and says what was actually driven.

## What was driven, and how

- **Device:** `f0a5b32b` — CPH2419 (OnePlus), Android 15 / SDK 35, `adb` from
  `C:\Users\pcadmin\AppData\Local\Android\Sdk\platform-tools\adb.exe`.
- **App:** `com.jarvis.client`, **versionName `0.2.3635` / versionCode `1000003635`** (read from
  `adb shell dumpsys package com.jarvis.client`). The Home screen itself says
  *"A newer build of this app is on GitHub (main, 1c4d915). Nothing is downloaded until you
  choose to."* — so this drive is evidence for build 0.2.3635, not for latest `main`.
- **Method:** `adb shell monkey -p com.jarvis.client -c android.intent.category.LAUNCHER 1`,
  `adb shell uiautomator dump /sdcard/ui-drive.xml` + `adb exec-out cat` for the tree, and
  `adb exec-out screencap -p` for pictures; every tap was by `bounds` centre from the dump.
  Navigation was restarted from the app launcher whenever a back-stack step landed elsewhere
  (Home's system Back exits the app — by design).
- **Hard constraints observed:** no Approve/Deny was ever tapped (the approvals queue was
  `pending=[]` before and after the run, read-only; history count 20 unchanged); no setting was
  changed; no memory or conversation was cleared; nothing was installed/uninstalled; no tunnel
  was used. The only writes were inside `.dsh-scratch/FIELD-TEST-2026-11-03/` plus one temporary
  `/sdcard/ui-drive.xml` dump on the phone, deleted at the end.

### Screenshots are black — by the app's own design, not a failed capture

Every Jarvis screen captures as a ~31 KB black PNG with a status bar, while a control capture of
a non-Jarvis screen (the battery page at 14:31) is a normal 192 KB PNG. Reason, measured:

- Settings → Security summary says **"App lock off, risky approvals ask, memory lists hidden."**
- The app sets `FLAG_SECURE` while *"Hide memory lists and chat history"* is on
  (`SecurityRules.blockScreenCapture`, `MainActivity.kt`), and `dumpsys window` shows the Jarvis
  window attributes include `SECURE`:
  `fl=LAYOUT_IN_SCREEN SECURE LAYOUT_INSET_DECOR SPLIT_TOUCH HARDWARE_ACCELERATED …`
- Turning that protection off is a security-setting change on the owner's phone, which this run
  must not make. So **the uiautomator dumps are the evidence**, and the PNGs are kept as proof
  that the app screens themselves are capture-blocked. This is itself a positive privacy
  observation and a practical limit on agent-driven field testing.

## Rows

| Row | Verdict (agent) | What was driven / seen | Evidence |
|---|---|---|---|
| **F5-09B** — no switch for the page-reading tool | **AGENT-PASS** | Settings → JUMP TO → **What asks first**, scrolled to the end (149 unique labels recorded). The page-reading tool has ONE row: **"Read a web page out loud - Asks you first, every time"**, a plain `android.widget.TextView` (`checkable="false"`, `clickable="false"`, bounds `[90,768][990,891]`) with the note **"Always asks. This cannot be changed from an app."** — no switch, toggle or "Ask me first" control exists at or beside it. Backend confirms the row is `read_web_page` and is in `tools.not_offered.tier_c`. | `phone/F5-09B-switches-ordered.txt`, `phone/F5-09B-evidence.txt`, `phone/F5-09B-sec-16.xml`, `phone/F5-09B-asks-first-opened.png` |
| **F4-08B** — DEF-028 Live wording | **FAIL** (phone half) | Two different Live lines exist on the phone, and they contradict each other. **The corrected line is present** in Settings → What asks first: *"Start Jarvis Live (a back-and-forth voice conversation) - Does it without asking"* with *"Your voice is checked once per Live session and not again on each sentence; ending Live ends that trust. A card that comes up during Live still waits for your tap. How far Live is trusted is a Voice setting."* **But the old false promise is still on the Live screen itself**, exactly: *"Jarvis listens after every answer until you end it, say "Okay Jarvis, that's all for now", or it has been quiet for 90 seconds. **Every full sentence is checked for your voice on your PC**; once this session is verified, a short reply is trusted without a check."* The installed APK contains that string (byte offset 7,196,437) and the corrected wording does not; the same old sentence is still in `origin/main`'s source (`LiveScreen.kt:378-385`), so this is not just a stale app. | `phone/F4-08B-live.xml`, `phone/F4-08B-live.png` (black), `phone/F4-08B-evidence.txt`, `phone/F5-09B-sec-*.xml` (corrected line) |
| **F4-01B** — habit check-in on the phone | **BLOCKED** | The Reminders screen has **no Habits section**: driven labels across 8 scrolls are only *Reminders / 0 reminders / Refresh / Daily to-do list / COMING UP / "Nothing coming up…"*. No way to create "walk three times a week" or tick it on the phone. The installed app's own feature text says *"Neither app has a screen for it yet - the Habits section on the Reminders screen is the next lane."* Read-only backend is live: `GET /api/habits` → `200 {"ok": true, "habits": [], count 0}`. Nothing was created, so the row cannot be a pass. | `phone/F4-01B-reminders-scroll-*.xml`, `phone/F4-01B-reminders.png` (black), `phone/F4-01B-02B-03B-evidence.txt` |
| **F4-02B** — mood entry + history chart | **BLOCKED** | Same screen, same reason: **no Mood section and no chart** in this build (the app's own text: *"the Mood section on the Reminders screen is the next lane"*). Read-only backend: `GET /api/mood?days=7` → `200 {"ok": true, "latest": null}` (keys `history`, `latest`, `limits`, `ok`, `words`). No 1–5 tap exists to drive. | `phone/F4-01B-reminders-scroll-*.xml`, `phone/F4-01B-02B-03B-evidence.txt` |
| **F4-03B** — week in review | **BLOCKED — not enough time yet** | No full week has passed since F4 landed: the last complete week is **2026-10-27 to 2026-11-02**, and F4 reached the live system on **2026-11-03**. The phone also has no Week in review screen (the string does not exist in the installed APK), and the weekly filing is off (`on:false`, `job:null`). Read-only counts for the record — NOT a pass: habit ticks 0, goal steps 0, reminders that went off 7, mood entries 0 of 7 days, with the PC's own note *"These are counts of what is stored on this PC - nothing here is a judgement."* | `phone/F4-01B-02B-03B-evidence.txt` |
| **F4-10B** — wake word | **BLOCKED (needs the owner)** | Settings → Voice shows **Wake word - "hey Jarvis"  ON**; the always-listening switch **"Listen on this phone" is off** ("Off by default, and never turns itself on"), and the screen says *"This phone is not listening."* Seeing the switch state is all an agent can do — saying "Hey Jarvis" needs the owner's voice. Not a pass. | `phone/F4-08B-settings-voice.xml`, `phone/F4-08B-settings-voice.png` (black), `phone/F4-10B-11B-12B-evidence.txt` |
| **F4-12B** — approve a card with the fingerprint | **BLOCKED (needs the owner)** | Settings → Security: *"App lock off, risky approvals ask, memory lists hidden."* Lock and fingerprint screen: **App lock is OFF**, **End Live when App lock would ask again**, **Fingerprint for approvals = Risky only** (small read-only cards are approved by the card alone; risky ones ask for the fingerprint; denying never asks). The approvals queue is empty (`/api/pending` → `pending: []`), so there is no card waiting even if a finger were present. Not a pass. | `phone/F4-12B-lock-fingerprint.xml`, `phone/F4-12B-lock-fingerprint.png` (black), `phone/F4-12B-security-screen.png` (black), `phone/F4-10B-11B-12B-evidence.txt` |
| **F4-11B** — Live started by voice | **BLOCKED (needs the owner)** | Live screen (not started): *Back / Jarvis Live / Jarvis is idle / Start Jarvis Live*. Voice check: **"How far Jarvis Live is trusted" → "Trust Live fully (default)" is the checked option** (*"What you say in Jarvis Live is trusted like the talk button, however you started Live."*). Starting Live by saying "Hey Jarvis, let's talk" needs the owner's voice. Not a pass. | `phone/F4-08B-live.xml`, `phone/F4-08B-voice-check*.xml`, `phone/F4-10B-11B-12B-evidence.txt` |

## Defect candidates (found while driving, verified against source/APK)

1. **DEF-028 still on the phone: the Live screen still promises the false thing**
   (`F4-08B`, FAIL above). The backend's `fixed:live` row and the phone's Settings list now say
   the truth (*"checked once per Live session and not again on each sentence"*), but the Live
   screen's own hard-coded hint still says *"Every full sentence is checked for your voice on
   your PC…"*. The two screens contradict each other. Evidence: `phone/F4-08B-evidence.txt`,
   `phone/F4-08B-live.xml`, source `jarvis-client/.../ui/screens/LiveScreen.kt:378-385`.
   Classification: **real defect on the phone half of the DEF-028 fix** — if DEF-028 is to be
   recorded fixed, this text needs the same correction as the backend's.
2. **The field-test brief assumes habit/mood/week screens that this build does not have**
   (`F4-01B`, `F4-02B`, `F4-03B`). Not an app defect: the app's own feature directory says both
   are "the next lane". But it is a planning defect in the field-test matrix — these rows cannot
   be driven from the phone until that UI exists, and the attached "next lane" wording should
   not be read as "built". Screens: `phone/F4-01B-reminders.png`, dumps
   `phone/F4-01B-reminders-scroll-*.xml`.

## Ambiguous / felt-broken notes (not ranked as defects)

- **"What asks first" is not its own screen.** It is a very long section *inside* Settings,
  reached by JUMP TO; scrolling from it runs into the rest of Settings with no section boundary
  marker at the end (the next heading appears only as content). Tappable rows and plain state
  rows look the same; only the trailing wording ("Asks you first, every time" vs "Does it
  without asking") tells behaviour apart. Fine once known — worth a real screen heading if this
  list is meant to be read by a person.
- **Home's update line.** "A newer build of this app is on GitHub (main, 1c4d915)" sits directly
  under the nav row. For a field test it means the phone is not on latest `main`, which is worth
  stating in every phone row's evidence, but it reads like an error on first glance.
- **Wake word ON vs "not listening".** Correct and clearly explained, but two switches that both
  look like "listening" ("Wake word - hey Jarvis" and "Listen on this phone") can be read as a
  contradiction for a second; the explanation under them is what resolves it.
- **Black screenshots** (above) are by design, but they make an agent-driven phone field test
  unable to produce visual evidence unless the owner temporarily turns off "Hide memory lists and
  chat history" — worth a line in the field-test method for future agent runs.

## Evidence index (all inside `.dsh-scratch/FIELD-TEST-2026-11-03/`)

- Rows: `phone/F5-09B-evidence.txt`, `phone/F5-09B-switches-ordered.txt`,
  `phone/F4-08B-evidence.txt`, `phone/F4-01B-02B-03B-evidence.txt`,
  `phone/F4-10B-11B-12B-evidence.txt`
- Dumps: `phone/*.xml` (171 files; `F5-09B-sec-*` is the full What asks first section,
  `F4-08B-live.xml` holds the Live hint, `F4-12B-lock-fingerprint.xml` the security states,
  `F4-01B-reminders-scroll-*` the bare Reminders screen).
- Screenshots: `phone/*.png` — all Jarvis ones black by FLAG_SECURE (see above);
  `phone/00-launch.png` is the non-Jarvis control showing screencap works.
- Harness: `phone/drive.ps1` (adb helpers), `phone_drive_api.py` (GET-only reads, token read the
  `probe.py` way and never printed). The APK pulled from the phone for the string evidence was
  deleted after the two strings above were extracted into `phone/F4-08B-evidence.txt`.
