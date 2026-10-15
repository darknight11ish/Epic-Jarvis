# The phone revisit, 2026-10-14 — the five rows the old APK blocked, driven at last

**What this is, and why it is a separate document.** `docs/FIELD-TEST-2026-10-14-RUN.md` (PR
**#419**) is the run record for the pass earlier the same day. It closed with **§5, "What is
blocked on the newer phone APK"**: five rows that could not be driven because the phone under
test was **0.2.1380, build `1b546df`**, and each of the five fixes merged *after* that build —
proved with `git merge-base --is-ancestor <fix> 1b546df` → **false**, not inferred from a date.
The phone has since been updated **over the old app, with no uninstall**, so the pairing token
survived. This document drives those five rows and **upgrades their verdicts**, quoting #419's
own row ids and its own wording so the change is auditable.

**Why this is not an appended section of #419's file.** That file is 601 lines and lives on the
branch `docs/field-test-2026-10-14`, not on `main` (`git show
origin/docs/field-test-2026-10-14:docs/FIELD-TEST-2026-10-14-RUN.md`; `gh pr view 419` → OPEN).
Editing it from a branch cut from `main` would produce a **second, rival copy** of the whole
document at the same path and a guaranteed conflict with #419. **It is extended, not forked**:
every verdict below names the row id #419 used and quotes the §5 wording it is replacing.

**The rule this record runs on, unchanged.** *BLOCKED and NOT-TESTABLE are never counted as
passes.* Only a feature **driven on real hardware** is a PASS. Where this record reasons from a
timestamp or a source read rather than a measurement, it says so in the row.

**Which tree this record was written in.** A worktree of the same repository,
`.dsh-scratch/wt-phone-fieldtest`, branch `docs/field-test-2026-10-14-phone`, created from
`origin/main` at **`48b18add`** after `git fetch origin`. Every claim about `main` was read with
`git show origin/main:<path>` or `git grep … origin/main`. The `CLAUDE.md` read is
`origin/main`'s, not the stale copy at the repository root.

---

## 1. The build under test, and the one measurement that decides the five rows

| what | the build, and where it was read |
|---|---|
| **Phone** | **0.2.1443.** Read from the device itself: `dumpsys package com.jarvis.client` → `versionName=0.2.1443`, `versionCode=1000001443`, `lastUpdateTime=2026-10-14 08:24:58`. The app's own Help → About page reads **`Version 0.2.1443`**. Device `f0a5b32b` (OnePlus `CPH2419`). |
| **The upgrade kept the pairing** | `firstInstallTime=2026-10-09 22:14:29` is unchanged from the earlier pass: the app was **installed over** the old one, not uninstalled first, so the token the phone already held survived. The phone's own Settings → Platform checks reads **Connected**, desktop **`marioirelan11-alps.nord:4719`**, "Connected, and updates are arriving." |
| **The build behind the APK** | The APK is `jarvis-client-c2f0dc3.apk`; `c2f0dc3` is `c2f0dc3f968977f45eb4bdbb02e4ce70bbde8ef9`, *"Merge pull request #416"*, **2026-10-14 02:23:53 -0700**, and it **is** an ancestor of `origin/main` (`git merge-base --is-ancestor c2f0dc3 origin/main` → true). |
| **Backend** | Read from `127.0.0.1:4719` and from `100.75.21.228:4719` (see §6 — this pass had to start it): `{"routing": true, "jarvis": false, "ollama": false, "proxy": false, "models": [], "default_model": "qwen3.5:9b", "tools": 28}`. |
| **Desktop app** | **Not running.** The same status says `"jarvis": false`, and no `Jarvis` process exists. Stated because two of #419's five rows needed the desktop half of the same feature. |

**The five fixes, each checked as an ancestor of *this* build** — the same instrument #419 used,
run against the new commit, not against a date:

| row | the fix | merged | `git merge-base --is-ancestor <fix> c2f0dc3` |
|---|---|---|---|
| **N4** settings search | `88f460a8` (#391) | 2026-10-14 01:21:03 UTC | **true** |
| **N5** fired-reminder Delete | `44ea3b7d` (#387), backend `91295187` (#383) | 2026-10-13 16:17:50 -0700 | **true**, **true** |
| **N11** the phone's **Back up now** | `cb35c914` (#408) | 2026-10-14 08:12:35 UTC | **true** |
| **N14** a device says what it is | #381, merge `1b4468ef` | 2026-10-14 01:05:29 -0700 | **true** |
| **N13** the phone's Home status line | #409, merge `ee6078bd` | 2026-10-14 01:54:05 -0700 | **true** |

So the reason every one of these rows was BLOCKED is gone, and the rows are drivable. What
follows is what happened when they were driven.

---

## 2. The five rows: what was driven, the literal result, before → after

### 2.1 **N4 — a switch found by the words printed on it** — BLOCKED → **PASS**

*Before (#419 §2.12, §5, quoted):* both boxes gave the pre-fix answer — Settings search read
**"Nothing here matches “Hide memory lists and chat history”."** and Find read **"Nothing matches
that."** The row's verdict was **BLOCKED — the phone under test predates the fix.**

*Driven now, on the phone:* the Settings search box (Settings → **SEARCH SETTINGS**, the
`EditText` at `[90,392][990,536]`), typing the switch's own words with `adb shell input text
'Hide%smemory%slists%sand%schat%shistory'`:

> the phone's literal answer: **"1 setting matches."**
> then **`SECURITY`** · **"App lock off, risky approvals ask, memory lists hidden."** ·
> **"Lock and fingerprint settings"**

Tapping that result lands on the Security screen, and the switch under its own heading
**`FINGERPRINT FOR PRIVATE LISTS`** is labelled, verbatim:

> **"Hide memory lists and chat history"**

— the words typed are the words printed on the switch, which is what the row is named after.
The second box, Home → **Find anything**, typed with the same words:

> **"1 match"** · **`Settings`** · **`Security`** · **"App lock and Windows Hello or the screen lock."**

*Verdict:* **PASS.** Both boxes offer the Security row, which is the plan's own PASS for N4.
**One wording difference, said rather than smoothed over:** the Settings box names the row
*"Lock and fingerprint settings"* and Find names it *"Security"* — two indexes, the app's own
words in each list, both landing on the same screen. Neither says *"Nothing here matches"*.

### 2.2 **N5 — deleting a reminder that has already gone off, on the phone** — BLOCKED → **PASS (the phone)**

*Before (#419 §2.7, §5, quoted):* the backend half **worked**, but *"BLOCKED — the phone's
Delete. The installed build `1b546df` predates the fix"*, with
`git merge-base --is-ancestor 44ea3b7d 1b546df` → not an ancestor.

*Driven now, on the phone:* a throwaway 60-second timer **of this pass's own**, never one of
his — `POST /api/schedule/add {"kind":"timer","seconds":60,"text":"dsh field test timer - delete
me"}` → `{"ok": true, "job": {"id": "sbde22f6d7d", …, "when": "08:39 today"}}`. It came due and
the PC listed it under `went_off` with `"state": "fired"`, `"fired_at": 1791992394.918`,
`"went_off_at": "08:39"`, `"age_s": 213.6`.

The phone's own **Coming up** plate (Home → Find → *"Coming up"*) drew its **"Just went off"**
section with the row on it:

> `timer` · **`(hidden) timer`** · `Went off at 08:39` · **`Snooze 10 minutes`** · **`Delete`**

**The words are hidden, and that is his privacy switch working, not a defect.** The plate's own
line above the section reads *"Words hidden. Tap Show and confirm it is you."*, and **Show was
not tapped** — that asks for his fingerprint or PIN. So the row was driven, and its verdict, on
the shape and the button alone.

**The Delete button was pressed.** The literal results, all three:

* the phone's plate then read **"Nothing coming up. Say or type \"set a timer for 10 minutes\" or
  \"remind me at 6 to call Mum\"."** — the row and the whole section are gone;
* `GET /api/schedule` reads **`"jobs": [], "todo": [], "went_off": [], "lists": []`**;
* `GET /api/schedule?id=sbde22f6d7d` → **404** `{"ok": false, "reason": "no_such_job", "error":
  "That is not on the list any more."}` — which is the plan's own PASS condition, met.

*On the notification:* `dumpsys notification --noredact`, read before and after the press,
shows exactly one `com.jarvis.client` record either side — `id=19030`,
`channel=jarvis_link`, `flags=ONGOING_EVENT|FOREGROUND_SERVICE` — which is the app's own link
notification, not the timer's. **No timer notification was present at the time of the drive**, so
this record does not claim the notification cleared; it says what the device showed.

*Verdict:* **PASS — on the phone**, which is what this pass was for, and which is what #419 §5
listed as blocked. **Two limits stated plainly, because PASS must not be read as more than it is:**
the desktop's own **Delete** button is still **unreached by any harness** (#419 §2.7: the Brain
window cannot be opened from one — not re-tested here, and not contradicted), so this is not
*both* apps; and the row's own words were never on screen, because his privacy switch hid them.

### 2.3 **N11 — the phone can ask the PC for a backup** — BLOCKED → **PASS**, with one claim in the design called wrong

*Before (#419 §2.8, §5, quoted):* the **route** half was driven and holds (`prepare` writes
nothing, checked by hash), but *"BLOCKED — the phone's own Back up now screen. The feature's
backend merged in #408 at 2026-10-14 08:12 UTC; the phone's build is `1b546df`, hours earlier."*

*Driven now, on the phone:* Settings → **Backups**. The card's own words, quoted:

> **"Last backup: 3 days ago."** · **"In: Jarvis Backups"** · **"Kept: 4 of the last 5."**
> the PC's verify sentence: *"Jarvis checked this file just now: it is a complete, well-formed
> backup, and nothing about it has changed since it was written."*
> its stated limit: *"Jarvis cannot prove from your phone that a backup OPENS - that needs the
> recovery code, and codes are only ever typed on your PC. …"*
> and the button: **"Back up now"**

The folder is named by its **last segment only** — *"Jarvis Backups"* — which is the design rule;
**this record does not print the full path either.** `last_backup_at` is `1791650945`, and the
phone's *"3 days ago"* is its own rounding of that (3.94 days), not a separate reading.

**Pressing "Back up now"** drew a dialog, whose literal contents were:

> **"Recovery code for this backup"** · *"This is the only time this code is ever shown. Nothing is
> written to your PC until you finish - so if you lose the code before saving it, tap Cancel and
> nothing changes."* · the code itself, **in four groups of five** (4 groups × 5 characters, 23
> characters with its hyphens — **the code is deliberately not written down here, and was written
> to no file**) · a tick, **"I have written this code down somewhere safe"** · a button,
> **"I have saved the code - write the backup"** · **"Cancel - write nothing"**

**The tick is a real gate, and it was measured without risking his backups.** The clickable view
behind *"I have saved the code - write the backup"* (`bounds=[102,1788][978,1937]`) reports
**`enabled="false"`** while the tick is unchecked, and the tick's own node reports
`checkable="true" checked="false"`. So the run cannot be finished until the tick is set — read
from the app's own accessibility attributes, with **no commit attempted**.

**One thing the design says that the pixels do not support.** PR #408 and the plan both word this
as *"the phone draws the code **full-screen**, in four groups of five"*. Measured with
`dumpsys window windows`, the dialog's window frame is

```
Window{… com.jarvis.client/com.jarvis.client.MainActivity}
    Frames: … frame=[60,437][1020,2081]
Physical size: 1080x2412
```

— **960 × 1644 pixels on a 1080 × 2412 screen**: a large centred dialog, covering about 40% of
the screen's area, next to a dimmed screen behind it. **"Four groups of five" holds. "Full-screen"
does not**, and this record says so rather than repeating the design's word.

**Nothing was written, and that is measured, not promised.** *"Cancel - write nothing"* was
pressed; the phone then read **"Cancelled. Nothing was written to your PC, and your backups are
exactly as they were."** The folder, hashed before and after:

| | files | top-level files | `last-run.txt` | folder mtime |
|---|---|---|---|---|
| before the press | **161** | 5 (4 `.jbak` + `last-run.txt`) | 201 bytes, `3C0532061F2705F5` | `2026-10-14T00:25:37.4755260-07:00` |
| after the cancel | **161** | same five, **same SHA-256 prefixes** | 201 bytes, `3C0532061F2705F5` | `2026-10-14T00:25:37.4755260-07:00` |

**The minted code's fate, recorded as the brief requires.** `GET /api/backup/status` read
`"prepared": {"at": 1791992092.7379048, "expires_at": 1791992992.7379048}` — a **15-minute**
window. **No commit was ever sent, with or without the code**; the run was left to lapse; the
code went into no file, no log and no line of this record. `last_attempt` read **`null`** all
through, so nothing failed either. **The lapse was then waited out and measured**, which is
§7.5: 36.3 seconds past the expiry the route still advertises the run, and the folder is still
byte-identical. **No code was ever sent to the PC**, so the refusal path that consumes one was
never entered.

**A line on that screen that reads like a failure and is not one, corrected by reading the
client's own source.** Under the button the phone draws, on every fresh load:

> *"Your PC is not answering, so nothing was asked for. Nothing has changed - try again when
> your PC is reachable."*

taken with the PC answering (the card above it was freshly populated) and surviving a **Refresh**.
It is **not** a stale error and not a failed attempt: it is `Backup.kt`'s `NEEDS_THE_PC` constant,
drawn statically by `BackupPlate.kt:229` under `if (run == null)` in the low-contrast "textLo"
colour, with its own comment — *"The one thing that can still go wrong after this much work, said
in advance rather than discovered"*. This record initially read it as an anomaly and then checked;
the source settled it. It is written down because the wording invites exactly that misreading.

*Verdict:* **PASS** — the phone's Back up now asks the PC, shows the code in four groups of five,
gates the run on the tick, and writes nothing until told to.

### 2.4 **N14 — a device says what it is, and a label cannot make two rows read the same** — BLOCKED → **PASS**, with a defect found in the phone's wording

*Before (#419 §2.15, §5):* **BLOCKED** — #381 merged at 01:05:29 -0700, twelve minutes after the
installed desktop exe was written and a day after the phone's build. #419's §5 table names the
fix as *"#381"* only; the merge commit is **`1b4468ef`**, and that is what was checked here.

*Driven now, on the phone:* Settings → **Devices**. The two rows, literally:

> **"This PC"** · **`PC`**
> **"OnePlus (this phone)"** · **`phone · paired 10 Oct · last used just now`**

**Each row names the kind of device it is** — the host as `PC`, this phone as `phone` — which is
#381's first fault fixed at the place the owner reads it. `GET /api/devices` agrees and is the
same data the screen is drawn from: `{"id": "pc", …, "kind": "pc", "this_device": true}` and
`{"id": "dd4dd7eee", "name": "OnePlus", "label": null, "shown": "OnePlus", "kind": "phone"}`.

**The collision was attempted, from the phone.** *"Name this device…"* was opened, `This PC` was
typed into the box (`[132,1075][948,1219]`) and **Save** was pressed. The literal result:

> the phone's answer: **"Not named. Try again."**
> the phone's own row: still **"OnePlus (this phone)"** — unlabelled, not renamed

and the PC's list is **byte-identical** across the attempt (`label: null` on both rows, the whole
`/api/devices` body equal before and after). Driven directly, the route that refuses it says:

```
POST /api/devices/label {"id":"dd4dd7eee","label":"This PC"}
HTTP 400
{"ok": false, "reason": "label_taken", "error": "Another device on this list is already called
 \"This PC\". Pick a different name so you can tell them apart - or remove that device first."}
```

So #381's second fault is fixed where it is enforced: **the label is refused, nothing is written,
and the row never reads the same as the PC's.** A refused label leaves no change to restore.

**The defect this pass found, named with both halves quoted.** PR #381's own body says the
refusal *"is a plain `error` sentence, which the phone already knows how to show (`\"Not named.
…\"`), so no shared contract and no app change was needed."* **For this refusal the phone does
not show it.** `jarvis-client/app/src/main/java/com/jarvis/client/net/Devices.kt`'s `labelSaid()`
words a 400 with arms for `bad_label` and `not_labelable` only, and everything else falls to:

```kotlin
else "Not named. Try again."
```

`label_taken` is exactly such a reason, so the sentence that **names what is in the way** — *"Another
device on this list is already called "This PC". Pick a different name so you can tell them apart"*
— reaches the PC's answer and not the owner's screen, which instead invites him to *"Try again."*
when trying again can never work. **Named, not diagnosed**: the client half is not this pass's to
change, and the fix is one arm in one `when`.

*Verdict:* **PASS for the fix** — each row names its kind, the collision is refused, and the two
rows stay distinguishable — with the wording defect above recorded beside it. **One half of #381
is not drivable from this phone at all, and is not claimed:** its first fault is about a
**laptop** being listed as a phone, and PR #381 says outright that the laptop client itself is not
built. There is no laptop on this list to read.

### 2.5 **N13 — a dead model lane says so, before the question** — BLOCKED → **PASS**

*Before (#419 §2.13, §5):* **BLOCKED twice over** — #409 merged *"61 minutes after the installed
desktop exe was written, and a day after the phone's build"* — and the state itself *"could not be
produced honestly even with the fix present"*, because it needed `/api/status` to carry
`"ollama": false` and the only method the plan had was pointing `OLLAMA_URL` at a dead port and
**restarting his live backend**.

*Driven now, on the phone:* the Home screen's own status line, read at the top of
`uiautomator dump`, before any question was asked and with nothing staged:

> **`Connected · Model not running`**

**How this record knows the lane is genuinely dead rather than staged** — four independent
readings, all taken this pass, none of them a change to his machine:

* **No listener** on `11435` or `11436` (`Get-NetTCPConnection -State Listen`), while `11434`
  answers — a plain Ollama server, the port his Jarvis is *not* on (`OLLAMA_URL` is a user
  environment variable on this PC: **`http://127.0.0.1:11436`**);
* **both lane tasks report success and are not running**: `Jarvis Ollama - Everyday model (RTX
  2060)` and `… Coding model (RTX 2080 Super)` each read `State=Ready`, `LastRun=2026-10-14
  08:18:57`, `Result=0`;
* **their logs stop mid-sentence**: `main.log`'s last lines are `Listening on 127.0.0.1:11436
  (version 0.40.3)` … `inference compute … RTX 2060` at **08:19:11**, and nothing after — the
  same silent death `CHANGELOG.md` records for 2026-10-13, whose tasks *"still reported last run
  09:11, result 0"*;
* the backend's own `GET /api/status` carries **`"ollama": false`** — and `11436` is the address
  the chat itself uses (`jarvis_hud.py:74` reads exactly that variable).

**And the phone is reading that field, not probing a port of its own:** `11434` *is* answering
`/api/tags` on this PC, so an app that probed the everyday Ollama port would have said
"connected" — the mistake #409's own CHANGELOG records for the desktop (`check_server_health`
probed `127.0.0.1:11434`, *"a port his lane is not on"*). The phone said `Model not running`.

**Nothing was "correctly absent" here**, which the brief asked about: this is the state the line
exists for, produced by the machine itself, not by a test. **No lane was started and no address
was changed to make it appear.**

*Verdict:* **PASS.** The amber-state phone line #409 adds is drawn, in the state the fix is for,
before any question.

---

## 3. Also driven: the tutorial tab and the "met N of M" line

**Where the tutorials live on this phone, since the brief points at the wrong tab.** Help on the
phone is the **FAQ** (`FaqScreen.kt`, opening *"Frequently asked questions, for this phone."*). The
**tutorials are a card on the Brain tab** (`BrainScreen.kt:1332`, `TutorialsSection()`, menu key
`brain.model.tutorials`), reached in this pass by Home → **Find** → `tutorial` → *"Tutorials and
the FAQ"*.

**What the phone actually draws**, literally:

> **`TUTORIALS`**
> **"You have met 0 of the 23 lessons here. 23 to go."**
> **`ON THIS PC`** … then the lessons, each with **`Not started`** and **`Start again`**

So the **new line is present and correct in form** — the *"met N of M"* sentence, the minutes-ago
shape of it, and `N = 0` truthfully, because this pass has never opened a lesson. **What it does
not say is 35.**

**Why the number is 23 and not 35 — measured on both sides, not a phone defect.** The catalogue
comes from the **PC**; `Tutorials.kt` says so itself (*"The catalogue comes from the PC, never from
this file"*), and the phone's own card is reading the PC's counts:

| where | how many lessons |
|---|---|
| the live PC's `GET /api/tutorials` | **`counts {"done": 0, "due": 23, "total": 23}`**, 23 tutorials |
| the live PC's `jarvis_tutorials.py` (mtime `2026-10-09 20:38:07`, 1321 lines) | **23** lesson rows; **none** of the twelve new lesson ids |
| `origin/main:backend/jarvis_tutorials.py` (1823 lines) | **35** lesson rows, including all twelve |

The twelve new ids (`model-page`, `hardware`, `limits-and-notes`, `set-up-jarvis-card`,
`money-and-health`, `home-devices`, `memory-lists`, `work-and-attention`, `how-it-talks`,
`home-overview`, `phone-limits`, `phone-extras`) are each **present on `main` and `ABSENT` from the
live file** — checked id by id. PR #416's own table says exactly this: *Tutorials 23 → 35*.

**So the honest reading is: the phone's half is current and drawing correctly, and the number it
draws is the PC's — and the PC's backend on this machine is the old one.** The phone cannot show
35 until his backend is updated, which is the *"Update both halves"* control and **his call, not a
phone defect and not this pass's to do.**

**And the brief's grouping is wrong on one point, measured:** it says the *"met N of M"* line is
*"drawn by both apps as of #415/#416"*. **#415 is not in this phone's build and not on
`origin/main`** — `gh pr view 415` → **OPEN**, and `git merge-base --is-ancestor
355573cae2724b93a21f89b97c1c19b7df3d0a55 c2f0dc3` → **false** (and likewise against `origin/main`
and against `48b18add`). #416's merge is what this phone carries; its branch contained #415's
commit *as it stood when #416 was branched*, and #415's head has moved since. That is why the
ancestry test, not the mention of a pull request, is what this record reports.

---

## 4. The counts, and the before → after in one table

**The unit is the row as #419 wrote it.** §4 of #419 counted 63 rows: **4 PASS, 7 PARTIAL, 26
BLOCKED, 26 NOT-TESTABLE**. Five of those BLOCKED rows are the subject of this document.

| row | where #419 wrote it | #419's verdict, and its reason | verdict now | what moved it |
|---|---|---|---|---|
| **N4** settings search | §2.12, §5 | **BLOCKED** — *"the phone under test predates the fix"*; both boxes said *"Nothing here matches"* / *"Nothing matches that."* | **PASS** | both boxes offer the Security row, whose own switch carries the typed words |
| **N5** fired-reminder Delete (phone) | §2.7, §5 | **BLOCKED** — the APK predated `44ea3b7d` (the backend half was already **PASS**) | **PASS (the phone)** | the row was deleted by the phone's own **Delete**; the PC's list and the single-job read agree |
| **N11** the phone's **Back up now** | §2.8, §5 | **BLOCKED** — the APK predated `cb35c914` (the route half was already **PASS**) | **PASS** | the phone asked, drew the code in four groups of five, gated the tick, wrote nothing; cancel confirmed |
| **N14** a device says what it is | §2.15, §5 | **BLOCKED** — the build predated #381's merge `1b4468ef` | **PASS**, with a wording defect named | each row names its kind; the collision is refused and nothing is written |
| **N13** the phone's Home line | §2.13, §5 | **BLOCKED** twice — the build predated #409 **and** the state needed a staged backend restart | **PASS** | the line reads `Connected · Model not running` with both lanes genuinely dead |

**And the row this document adds, because the brief asked for it:**

| row | #419's verdict | verdict now | what moved it |
|---|---|---|---|
| the education work — the "met N of M" line | not a row in #419 (the work landed after it) | **PASS** for the line the phone draws; the *"35"* is **the PC's number to move, not a phone row** | the phone draws *"You have met 0 of the 23 lessons here. 23 to go."*; the **PC** holds 23 lessons, `main` holds 35 |

**#419's tally is superseded for these rows only, and this document does not restate it.** What
this document claims is exactly **five rows moved from BLOCKED to PASS**, plus one new finding
about the education work — and it claims nothing about the other 58 rows, which it did not drive
and did not re-read. **The arithmetic belongs in one place, and that place is #419's own §4:** a
reader who wants the whole tally should apply those five moves to that table rather than trust a
second sum computed from a summary of a summary.

---

## 5. What this pass changed on the machine, and how each was put back

The brief's rules stand: nothing was approved, no privacy switch was moved, nothing of his was
deleted, and every change is named with its restore and its proof.

| what was changed | why it was necessary | restore / proof it is back |
|---|---|---|
| **The backend was started** — it was **not running** when this pass began (§6) | four of the five rows need it; the phone read *"Your PC isn't answering."* | Started from the live backend folder with `JARVIS_HUD_BIND=100.75.21.228` and `HUD_TOKEN` set from `jarvis_token_store.py show` **inside the same process, so the token was never on a command line, in a file, or in this record**. **Left running**, and said plainly here: the brief's own premise was that the backend was up, and the owner's phone works again with it. The desktop app's own store (`%APPDATA%\com.jarvis.desktop\jarvis-desktop.json`) reads `"bind_address": "100.75.21.228"` and `"pair_phone_address": "marioirelan11-alps.nord"`, so this reproduces the address its own supervisor would use. **`127.0.0.1:4719` is answered too** — the `loopback-too` behaviour — so nothing that used loopback lost it. |
| **One timer, this pass's own** (`sbde22f6d7d`, labelled `dsh field test timer - delete me`) | it is N5's test subject | **Deleted by the test itself, on the phone**, which is the row. `GET /api/schedule` reads `"jobs": [], "todo": [], "went_off": [], "lists": []`, and the single-job read is 404 `no_such_job`. **None of his reminders was touched**; none was listed before this pass began. |
| **One backup recovery code, minted** | N11's button is the row | **Never used, never written down, left to lapse** (`prepared` at `1791992092.7379`, expires `1791992992.7379` — 15 minutes). **No commit was sent at all**, and the folder is byte-identical by count, by top-level SHA-256 and by its own mtime (§2.3). |
| **A device label attempted, and refused** | N14's collision is the row | A refused label leaves nothing behind: `/api/devices` is **byte-identical** across the attempt and both rows read `"label": null`. |
| **The phone's Settings search box, and Find** | N4's two boxes are the row | Both were cleared with their own **Clear** control; the phone was returned to **Home with no search text and no dialog open**. |
| **`docs/README.md`'s stated document count** | a new document is added by this pass | Not a change to the machine, and not a generator run: `main`'s tree holds **381** while its page states **380** (§7.1), so the page now states **382** — `main`'s real 381 plus this document. **The size figure was left exactly as it was**, per the rule that only the count is bumped by hand. `python -B tools/check_docs_map.py` exits **0** on this branch. |

**Not touched, on purpose:** no card was approved (none was raised — `GET /api/pending` reads
`"pending": []` before and after); **no privacy switch was moved**; the Security screen's *"Show"*
under *"Words hidden"* was **not** tapped, because it asks for his fingerprint or PIN; no
Windows Hello prompt was answered; **none of his data was deleted** — the only deletion in this
document is the timer this pass created; no `jarvis-framework.toml`, `config.toml` or any other
live file was edited by hand; `scripts/apply-patches.ps1` was **never run**; **no lane was
started**; and the desktop app was not launched.

**One thing left exactly as found, and reported because it is not this pass's to fix:** the two
model lanes are dead (§2.5), as they were when this pass began, and this pass did not start them.

---

## 6. What in the brief was wrong, said plainly

The standing instruction is to say this rather than route around it.

1. **"The backend is on `127.0.0.1:4719`" was false when this pass began — it was not running at
   all.** `Get-NetTCPConnection` showed no listener on `4719`, `11435` or `11436`; the only Ollama
   answering was `11434`; and the phone's Home screen said **"Your PC isn't answering."** with a
   **Retry** button. **The desktop app was not running either.** Whatever the earlier pass left,
   the PC side was down. Four of the five rows are unreachable in that state, so this pass started
   the backend (§5) rather than write four rows BLOCKED for a reason that is about a service and
   not about the phone. **This is the one place this document departs from a strict reading of
   its instructions, and it is disclosed here and in §5.**
   **A second, sharper fact behind it, which cost the most time to find:** a hand-started backend
   on its defaults is **invisible to the phone**. The live `jarvis-framework.toml` reads
   `[security] bind_address = "127.0.0.1"`, and `jarvis_hud.py` refuses a non-loopback bind unless
   `HUD_TOKEN` is set. The phone reaches this PC at the **NordVPN Meshnet** name
   `marioirelan11-alps.nord:4719` (= `100.75.21.228`), which is the address the desktop app's own
   store and the phone's own Settings → Platform checks both name. **The phone did not connect
   until the backend was bound to `100.75.21.228` with the token set**; until then it read
   *"Your PC isn't answering."* while `curl http://127.0.0.1:4719/api/status` answered 200.
2. **"the phone's tutorial tab should now show 35 tutorials" is not reachable on this machine, and
   the reason is the PC, not the phone.** The phone draws *"You have met 0 of the 23 lessons
   here. 23 to go."* because the **live backend serves 23**; `main`'s catalogue holds **35**
   (§3). The number is the PC's by design.
3. **The tutorials are not on the Help tab.** Help is the FAQ; the tutorials are a card on the
   **Brain** tab. A pass that looks for a "tutorial tab" beside the FAQ will not find it.
4. **"the new 'met N of M' line (that line is drawn by both apps as of #415/#416)" is half wrong
   about #415:** #415 is **OPEN**, and its head `355573ca` is an ancestor neither of this phone's
   build `c2f0dc3` nor of `origin/main` (§3). It is #416's merge the phone carries.
5. **The plan's and #408's word "full-screen" for the recovery-code dialog is not what the screen
   does** — measured, the dialog is `[60,437][1020,2081]`, 960 × 1644 on a 1080 × 2412 screen
   (§2.3). The *"four groups of five"* and the tick gate are both exactly as described.
6. **The brief's "the phone is now 0.2.1443 (`jarvis-client-c2f0dc3.apk`)" is right, and worth
   restating with its own proof:** `versionName=0.2.1443`, and every one of the five fixes is an
   ancestor of `c2f0dc3` (§1) — checked, not assumed from the version string.
7. **Confirmed rather than corrected, and worth recording because the brief said them:** the
   pairing token survived (no uninstall: `firstInstallTime` unchanged); `jarvis_token_store.py
   show` in the live backend folder is the blessed reader for it (JARVIS-API §6947) and returns a
   43-character token, which this record never prints; `X-Jarvis-Client: hud` is required —
   without it the server answers `{"error": "cross-origin request refused"}`; and `OLLAMA_URL` on
   this PC really is `http://127.0.0.1:11436`, while `jarvis_hud.py:74`'s own default is
   `11434`.

---

## 7. Defects and anomalies this pass found, with the evidence

### 7.1 `main`'s own docs map is red, and this document's count bump is two rather than one

Measured in this worktree, which is `origin/main` at `48b18add` **before** this document was
added:

```
> python -B tools/check_docs_map.py
ok    …docs/README.md states how many documents there are
FAIL  every document count on the page matches the tree (381)
        the prose line (count) says 380
        the comment on the measuring command (count) says 380
docs map FAILED.
exit 1
```

`main`'s tree holds **381** markdown files under `docs/` and its page states **380**, in both
places it states it. **This is the same defect #419 §8.1 recorded and PR #420 addresses; it is
still true on `main` at `48b18add`**, so this document's bump has to be from the stated **380**
to **382** — `main`'s real 381 plus this document — not to 381. **A reader merging #420 and this
branch will have a one-line conflict in `docs/README.md`, and the number that is right after both
is 382.**

### 7.2 The phone drops the PC's sentence when a device label collides

Named in full in §2.4: `Devices.labelSaid()` has no arm for `label_taken`, so the owner is told
**"Not named. Try again."** instead of the sentence that names what is in the way. **The route is
right; the phone's wording for it is missing one arm.** Not diagnosed further than that, and not
fixed here — the client half is not this pass's to change.

### 7.3 The word "full-screen" in #408 and the plan

Named in full in §2.3, with the frame measured.

### 7.4 The model lanes died again, silently, and the tasks still report success

`08:18:57` both lane tasks ran, `Result=0`; `08:19:11` both logs stop immediately after
`Listening on 127.0.0.1:11436` / `…:11435`; by `08:30` neither port has a listener. The failure
is **silent in the same way `CHANGELOG.md` describes for 2026-10-13** — *"the scheduled tasks
still reported last run 09:11, result 0, their logs simply stop"*. **Reported, not diagnosed**:
whoever owns `start-lane.ps1` has the cause in a file this pass did not read. **It is why §2.5
could be driven honestly at all**, and it is also a real fault on his PC that a person may want
to know about.

### 7.5 A prepared backup run is still advertised past its own expiry — **reproduced, measured**

#419 §8.4 found a lapsed `prepared` run still reported by `GET /api/backup/status`. This pass
minted a fresh one for N11, left it to lapse, and **waited the window out to re-test it**:

```
GET /api/backup/status
    "prepared": {"at": 1791992092.7379048, "expires_at": 1791992992.7379048}
    the PC's own clock at that read:  1791993029     <- 36.3 seconds PAST expires_at
    "last_attempt": null
```

So **#419 §8.4 is reproduced on a second, independent run** — the *report* is stale, and the
*route* is not unsafe: `request_commit` refuses an expired run (`_is_expired(row)` →
`COMMIT_NO_RUN`), which #419 read and this pass did not re-drive, because re-driving it would
mean sending a commit with a code this record must never hold. And the folder stayed untouched
across the lapse as well: **161 files**, mtime `2026-10-14T00:25:37.4755260-07:00`, unchanged
from §2.3.

---

## 8. What this pass could not test, in one list

* **Anything needing his fingerprint or PIN.** Re-confirmed on hardware, not repeated from a
  record: the Brain's memory section draws **"Hidden. Tap Show and confirm it is you."** with a
  **Show** control; the Coming-up plate's fired row drew its words as **`(hidden) timer`** behind
  the same line; and the Security screen says *"Turning it on asks for your fingerprint or PIN"*
  on the switches beside the one this pass searched for. **Not one of those prompts was
  answered.**
* **The desktop's own halves of N5, N14 and N13** — the desktop app was not running, and for
  N5's Delete button #419 §2.7's reason (a harness cannot open the Brain window) is not
  contradicted here, only not re-tested.
* **The laptop half of #381** — no laptop client exists (PR #381 says so itself).
* **The 35-lesson catalogue on the phone** — the PC has 23; only a backend update makes the
  number move, and that is the owner's call.
* **Anything needing his voice, his accounts, his camera, a paired watch, or a second device to
  approve a card from** — unchanged from #419 §3 and §9, and none of it touched here.
* **The refusal path that consumes a recovery code** (`COMMIT_NO_RUN` on an expired run) — not
  re-driven, because driving it means holding and sending a code, and this record holds none
  (§2.3, §7.5). The stale *report* was measured instead.
* **`backend/run_suites.py`**, and every suite: **not run**, and nothing here rests on one. This
  document is field testing on real hardware, not a suite result.
