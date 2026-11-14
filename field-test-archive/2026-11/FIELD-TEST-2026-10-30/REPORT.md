# Field test — remaining rows, measured 2026-10-30 16:25–16:35 PDT

**Who measured what.** This report was produced by the `field-test` subagent in a **read-only**
session. Everything below was measured with `adb` reads, file reads on the PC, and `git show
origin/main:` checks — **no live API call, no token read, no install, no app launch, no approval, no
phone app data read**. The one input this session did not measure itself is the owner's two
screenshots; the Lead relayed them in words (§3). They are labelled **OWNER-VISUAL**, not driven.

**Status words.** PASS = the feature was driven on the owner's hardware and its effect observed.
PARTIAL = some hardware evidence exists (screen read, file/log measured) but the effect was not
operated. BLOCKED = needs the owner (fingerprint / Windows PIN / Windows Hello / approval card) or a
condition nobody can manufacture. NOT-TESTABLE = needs accounts, hardware or a voice this machine
does not have. Per `CLAUDE.md` and `docs/FIELD-TEST-MATRIX-2026-10-11.md`, **BLOCKED and
NOT-TESTABLE are never counted as passes.**

**Which tree the code claims came from.** The primary checkout is stale and dirty (HEAD
`b0aabefcd`, 45 modified entries) and was **never written to**. Every claim about the repository in
this report was read with `git show origin/main:<path>` / `git grep origin/main` at
**`origin/main = 57c14136c`**. Every claim about the live install was read from
`C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program` (read-only).

---

## 1. Device and build state (measured this session)

| what | measured value | how |
|---|---|---|
| device | `f0a5b32b  device` — present and authorised | `adb devices` |
| model / OS | CPH2419, OnePlus, Android 15 | `adb shell getprop` |
| phone time | `Fri Oct 30 16:32:08 PDT 2026` | `adb shell date` |
| screen | `mWakefulness=Awake`, display suspend blocker held | `adb shell dumpsys power` |
| Jarvis packages | `com.jarvis.client`, `com.jarvis.made.field_test_app`, `com.jarvis.client.test` | `adb shell pm list packages \| findstr -i jarvis` |
| Jarvis app version | `versionCode=1000003261`, `versionName=0.2.3261` | `adb shell dumpsys package com.jarvis.client` |
| install times | `lastUpdateTime=2026-10-30 12:01:36`, `firstInstallTime=2026-10-09 22:14:29` | same |
| foreground at session start | `topResumedActivity=com.jarvis.made.field_test_app/.MainActivity` | `adb shell dumpsys activity activities` |
| foreground after my read (one HOME key) | `topResumedActivity=com.android.launcher/.Launcher` | same |

**The build the owner's screenshots came from.** The installed app is **0.2.3261 / versionCode
1000003261**, installed **2026-10-30 12:01:36 PDT**, and `FIELD-TEST-FINAL-2026-10-30.md:17-18`
records that APK as built from `main` = **`21add9d53`** (`FIELD-TEST-FINAL-2026-10-30.md:5-6`
names it as "the CI-built release APK from main = 21add9d53"; `:17-18` records the install and the
version; commit time `2026-10-30 11:43:17 -0700`, measured with `git log -1 21add9d53`).
`firstInstallTime` is still 2026-10-09, so the app was updated in place, never uninstalled.

**The newest CI build is already past it.** `gh release view client-latest` (read-only) now names
**`jarvis-client-d72735a.apk` — "Jarvis for Android 0.2.3272", from `main` commit `d72735a`, built
2026-10-30 22:22 UTC** (asset created `2026-10-30T22:22:19Z` = **15:22 PDT**; sha256
`aa2b25346f2e5964bd3a1b743ed1558f66b4a7fcd72b4ecf723e1930e091d0a0`). Ancestry measured:
`git merge-base --is-ancestor 21add9d53 d72735a` → exit 0, so the installed build is an ancestor of
the newest build. **The owner's "latest android app" is 0.2.3261, one published build behind
0.2.3272.** Under the matrix's mandatory binary build-SHA gate
(`docs/FIELD-TEST-HOW-TO-READ-THE-APPS.md:139-167`), any row measured on these screenshots belongs
to `21add9d53`, not to the latest APK.

**Feature ancestry inside the installed build (measured, not assumed).**
`git merge-base --is-ancestor f86b88172 21add9d53` → **exit 0**, so the installed 0.2.3261 contains
**#987 "feat(history): chat history one click away, with archive and an Archived list — desktop,
phone and the PC contract"**. That is why the owner's History screenshot shows the Archived/filter
UI. `bd3023111` (the commit that introduced `"Put it on my home screen"`, `git log -S` on
`jarvis-client/.../net/JarvisWidgets.kt`) is also an ancestor of the installed build (exit 0).

---

## 2. The two rows named in the handoff §6.8 — status

### 2.1 Home widget slot (matrix row 21 `widgets`) — **PARTIAL**

**What the field-test record says.** `FIELD-TEST-FINAL-2026-10-30.md:24` (row 1): the widget feature
was driven end to end earlier that morning (chat → preview → Add → slot set to *Jarvis widget 2* →
"Put it on my home screen" answered *"Jarvis widget 2 is already on your home screen."* → the card
drew *"Next Reminders / Coming up / Hidden — open Jarvis to see it."*), and then: **"After installing
the CI release APK the phone's app data from the debug build was replaced, and the slot now reads
'No widget chosen' — the saved widget is still on the PC; the slot has to be re-picked once in
Brain → Widgets. NOT a pass for the current install until that re-pick is driven."**

**Measured on the phone now (this is the direct evidence the handoff asked for).**
`adb shell input keyevent 3` then `adb shell uiautomator dump` of the launcher, at 16:26 PDT. The
home screen's Jarvis card contains exactly:

```
text="No widget chosen"
text="Tap, then choose one under Brain, Widgets"
content-desc="Jarvis widget 2"
```

So the card on the visible home page **is bound and drawing** — it is the "Jarvis widget 2" slot —
and its content is the **empty-slot** state. That matches the record exactly.

`adb shell dumpsys appwidget` (saved whole in `appwidget-dump-20261030.txt`, 26,589 bytes) shows all
three Jarvis board widgets are **still bound to the launcher**, which is the part the APK update did
not remove:

```
[63] provider ... com.jarvis.client/com.jarvis.client.widget.ApprovalWidgetReceiver
[64] provider ... com.jarvis.client/com.jarvis.client.widget.QuickLinkWidgetReceiver
[65] provider ... com.jarvis.client/com.jarvis.client.widget.JarvisBoardWidgetOneReceiver
[66] provider ... com.jarvis.client/com.jarvis.client.widget.JarvisBoardWidgetTwoReceiver
[67] provider ... com.jarvis.client/com.jarvis.client.widget.JarvisBoardWidgetThreeReceiver
[69] provider ... com.jarvis.client/com.jarvis.client.widget.CalendarWidgetReceiver
...
Widgets:
  [3] id=30 host=... pkg:com.android.launcher  provider=...JarvisBoardWidgetThreeReceiver
  [4] id=32 host=... pkg:com.android.launcher  provider=...ApprovalWidgetReceiver
  [5] id=33 host=... pkg:com.android.launcher  provider=...QuickLinkWidgetReceiver
  [6] id=34 host=... pkg:com.android.launcher  provider=...JarvisBoardWidgetOneReceiver
  [7] id=35 host=... pkg:com.android.launcher  provider=...JarvisBoardWidgetTwoReceiver
Hosts:
  [0] hostId=... pkg:com.android.launcher  widgets.size=8 zombie=false
```

**The saved widget is still on the PC (measured).** `C:\Users\pcadmin\.openjarvis\widgets.json`
(360 B, written 2026-10-30 06:26:15) holds:

```json
{"version": 1, "widgets": [{"id": "w7dbe0ba0ae", "name": "Next Reminders", "layout": "stack",
  "blocks": [{"type":"title","text":"Next Reminders"},
             {"type":"list","source":"reminders","label":"Coming up","max":3}]}]}
```

That is the same widget (`w7dbe0ba0ae`, "Next Reminders", 3 reminders) the morning field test drove.

**Verdict: PARTIAL.** The Android slot is bound and the launcher card is live; the app-side choice is
empty, so the card reads "No widget chosen". The empty state is confirmed by the phone's own
accessibility tree and by the saved-widget file on the PC.

**Exact evidence needed for a PASS:** the home card's own text changes from "No widget chosen" to
the saved widget's content (`Next Reminders` / `Coming up`), read the same way (launcher
`uiautomator dump`) or seen by the owner; the PC's `/api/widgets` still lists `w7dbe0ba0ae`.

**Can it be driven without the owner?** Technically yes — it is a UI pick under Brain → Widgets, no
biometric and no approval card — but it is a **persistent write** (the chosen slot is kept), so this
read-only session did not do it. The owner can do it in about four taps, and the Lead asked for it
by name.

### 2.2 Phone History archive (matrix row 39 `history`) — **PARTIAL** (three parts)

The handoff names one row; on measurement it is three separable claims, and only one of them is
owner-visual evidence so far.

#### (a) The History screen and its list render on the phone — **OWNER-VISUAL, PASS-like for rendering only**

Owner-provided, relayed by the Lead at **16:22–16:23 PDT** (the image files were not in this
session's possession; the labels below are the Lead's transcription of them — I did not see the
images). Screenshot A, quoted labels: header **"History"**, **"Chat history, kept on your PC"**,
Back, New chat, Refresh; a **"Search what was said…"** field with **"Newest"** sort; **"On. New
chats are kept on your PC, encrypted."** + **"Change"**; section **CONVERSATIONS** with **"Tags"**
and **"Forget a time frame…"**; filter rows **All chats / Just chats / Live only / Support chats /
Chats with other AIs / Comparisons / Archived**; tag rows **All / Work / Learning / Personal /
Projects / Ideas / Untagged (238)**; then an expanded **"Untagged (238)"** group listing real chats,
e.g. **"what is this document about — Today 11:52 — phone — 4 messages — read outside text"**,
**"Field test attachment — Today 08:38 — phone — 2 messages"**, **"hello — Yesterday 18:21 — phone —
2 messages"**.

Screenshot B, quoted labels: the chat screen with **"Connected"** and a History tab, and a **"More"**
sheet: **"Your chats, the presets, and the chat controls that used to sit around the box. Only what
this PC offers is listed."** with entries New chat / Earlier chats / Pinned messages / Jarvis Presets
(In Brain, under Hardware) / Photo / Attach a file (PDF, Word, Excel, PowerPoint, text, Markdown or
CSV, up to 2.5 MB. Read on your PC.) / Think / Coach this / Incognito / Quick note / Close.

**What this proves:** the installed Android app renders the History screen and the More sheet
correctly, with **real PC-backed chat history visible** (238 untagged conversations, timestamps,
message counts, `phone` provenance). **What it does not prove:** the biometric Show control was
exercised, or that Archive/Unarchive was operated. The Lead said the same thing and this report
agrees.

#### (b) The "Show" gate is real, by design, and is the owner's — **BLOCKED (owner), by design**

* **Phone side:** `jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/HistoryScreen.kt:144-146`
  — *"'Hide memory lists and chat history' (Security) hides the list and any open conversation until
  Show is confirmed, the same as Brain's memory lists. The settings stay visible: they say nothing
  about what was said."* The History screen gates its sections through
  `HiddenSection(..., onShow = onShowPrivate)` at `:583`, `:626`, `:721`.
* **The Show control itself:** `SecurityScreen.kt:330` (`fun HiddenSection`), which draws
  `"Hidden. Tap Show and confirm it is you."` and `Quiet(if (busy) "Checking…" else "Show", …,
  onClick = onShow)`.
* **The check is the phone's biometric / device credential:** `MainActivity.kt:4576-4583`
  (`showPrivateLists()`) calls `ownerCheck(title = "Show memory lists", method =
  currentSecurity().method, whatStays = "the lists stay hidden") { lockSession.showPrivate() }`, and
  `ownerCheck` (`MainActivity.kt:4539-4562`) runs
  `BiometricGate.check(this@MainActivity, title, "Confirm it is you.", method)` at `:4551`.
  So the gate is **by design**, the phone's own prompt, and a harness cannot and must not fake it.
* **The PC enforces the same rule server-side** (so the phone cannot bypass it by hiding the UI):
  - `jarvis_chat_log.py:4061-4065` — while App lock / "Hide memory lists and chat history" is on,
    `GET /api/history` withholds every row (`hidden=True`, `conversations=[]`, `hidden_count`);
  - `jarvis_chat_log.py:4124-4131` — `POST /api/history/pin` answers **423** for every id while the
    lists are hidden;
  - `jarvis_chat_log.py:4144-4151` — `POST /api/history/archive` answers **423** the same way.

**State at the owner's 16:22 screenshot:** the transcription shows the conversation list itself
(238 chats), and it does **not** include the "Hidden. Tap Show and confirm it is you." line — so in
that session the lists were **not** hidden/covered. Compare the morning record
(`.dsh-scratch/FIELD-TEST-FINAL-2026-10-30.md:29`): at that point the list read *"Hidden. Tap Show
and confirm it is you."* Both can be true at different times — the cover depends on the phone's
Security setting / lock state, and the owner may have used Show in between. This session did not
measure the setting itself (it lives in the phone app's own data, which a release build does not
expose to adb), so it is recorded as *state evidence changes*, not as a resolved question.

#### (c) The archive action itself — **PARTIAL, never driven on this install**

The routes exist, on the live install, now. Measured in the live install's own files:

* `…\Desktop program\jarvis_hud.py` (mtime `2026-10-30 12:44:03 PM`; the pre-repair copy is kept as
  `jarvis_hud.py.before-repair-20261030-124403`) — the POST dispatch list at **`:4735-4738`**
  contains `"/api/history/fork", "/api/history/mark", "/api/history/pin", "/api/history/archive"`,
  and **`:4765`** is `code, out = jarvis_chat_log.handle_post(route, body)`.
  The GET side is at **`:3409-3428`**: `/api/history`, `/api/history/conversation`,
  `/api/history/tags`, `/api/history/tags/suggest` → `jarvis_chat_log.handle_get(...)`.
* `…\Desktop program\jarvis_chat_log.py` — `handle_get` **`:4038-4065`** documents and implements
  `archived=1` (*"the archived chats only; absent, 0, false or anything unreadable is the ordinary
  list"*); `handle_post` **`:4119-4137`** is pin, **`:4138-4157`** is archive
  (`{"id", "archived"}`, reversible, no card, audit event `history.archive` at `:4156`).
* The repo carries the same code: `git show origin/main:backend/jarvis_chat_log.py:4138` etc., and
  the tests name the route: `origin/main:backend/test_chat_log.py:998` calls
  `H.handle_post("/api/history/archive", …)` — a suite check, not field evidence.
* **The route has never been exercised on this install.** The live audit log
  `C:\Users\pcadmin\.openjarvis\logs\jarvis-2026-10-30.jsonl` (written through
  `jarvis_framework.audit_log`, required by `jarvis_chat_log.py:3812-3817`) contains **no**
  `history.pin` and **no** `history.archive` event. (`_audit("history.pin", …)` is
  `jarvis_chat_log.py:4136`, `_audit("history.archive", …)` is `:4156`.)

**What the morning record said and what is now fixed:** `FIELD-TEST-FINAL-2026-10-30.md:29` had the
archive route answering **404** because the live HUD lacked the route. The handoff §4 records that
#997 repaired exactly this and re-verified it after restart (*"routes answer 400 not 404"*,
`JARVIS-HANDOFF-2026-10-30-continuation.md:97-99`). My code inspection confirms the repaired live
HUD now lists both routes and hands them to `jarvis_chat_log.handle_post`; the line where the HUD
went from no-route to route is in `jarvis_hud.py` at `:4735-4738`. **I did not re-call the API**, as
this session is forbidden to call the live API, so the handoff's 400-not-404 measurement is cited,
not re-measured.

**Exact evidence needed for a PASS (archive):** on the phone, with the list visible, open one chat's
row overflow menu (`⋮`) → **Archive** (menu labels measured in the repo:
`net/ChatLog.kt:659-660` `ARCHIVE = "Archive"` / `UNARCHIVE = "Unarchive"`; the row's own archive
handler is `HistoryScreen.kt:501-524`), then open the **Archived** filter (`ChatLog.kt:666`
`ARCHIVE_FILTER_TITLE = "Show archived chats"`; chip drawn at `HistoryScreen.kt:807-816`) and see the
chat there, then overflow → **Unarchive**. Corroborating evidence (any one): the phone's Archived
view lists the chat; the PC's `GET /api/history?archived=1` returns it (an agent with the token may
check it); the live audit log gains `"event": "history.archive"` with `{"archived": true}`, then
`{"archived": false}` after unarchive. **No approval card is involved** — the code comments say
*"one chat, one reversible local flag, no card — putting a chat away reveals nothing and sends
nothing"* (`jarvis_chat_log.py:4138-4143`).

**Can it be driven without the owner?** The archive tap itself needs no biometric and no card
**when the lists are visible** — which is the state of the owner's 16:22 screenshot. So in
principle an agent with the phone could drive it (uiautomator taps); this session stayed read-only
because the mission forbids live writes, and because the moment the view is hidden the 423/Show gate
makes it the owner's by design. Fastest honest route: **the owner does it** (about five taps), or
the Lead authorises an agent to drive that one reversible write. The PASS still needs a read of the
result afterwards — the audit log line is the cheapest read-only confirmation.

---

## 3. Wider field-test matrix — inventory of the unproven rows

Read in the repo checkout (stale tree) at `docs/FIELD-TEST-MATRIX-2026-10-11.md`; row/verdict claims
cross-checked against `origin/main` where the document itself cites later files. The matrix's own
corrected note (2026-10-15) states, over its then-129 rows: **DRIVEN 5, SCREEN 93, BLOCKED 19,
NOT-TESTABLE 12**. Rows 130–136 were added after that note and carry their own verdicts; counting
the table as it stands today gives **DRIVEN 10, SCREEN 93, BLOCKED 19, NOT-TESTABLE 14 = 136** (my
arithmetic over the document's rows, not a new test — no count was reverse-engineered).

### 3.1 BLOCKED (19 rows) — who can settle each, by group

| group | rows (matrix #) | what a PASS needs | owner needed? |
|---|---|---|---|
| Hidden-memory / fingerprint group (10) | 27 `memory-saved`, 29 `memory-known`, 30 `memory-people`, 31 `pinned-facts`, 32 `between-us`, 34 `memory-learning`, 37 `memory-as-of`, 40 `chat-tags`, 41 `forget-range`, 66 `sensitive-facts` | on the phone, tap **Show** and confirm it is you (fingerprint/PIN — by design, cannot be delegated), or turn the hiding setting off; then read each row's content on its own screen | **yes — the biometric** |
| Windows Hello / device credential (2) | 105 `big-model`, 120 `app-lock` | the owner's own click through the PC's Windows Hello / the phone lock | **yes** |
| Owner decisions (3) | 116 `past-approvals`, 118 `approvals`, 124 `trust` | a card actually raised and decided by the owner; the audit chain's state comes from his decisions | **yes** |
| Harness cannot reach the window (2) | 26 `memory-tab`, 101 `work-tab` | open the desktop Brain from its tray icon — the tray icon is in the "Show Hidden Icons" overflow and exposes no readable menu (`docs/FIELD-TEST-HOW-TO-READ-THE-APPS.md` method 2, the documented dead end) | **yes, at the PC — two clicks** |
| Real defect / behaviour (2) | 19 `coming-up` (the "screen declared=19 … composed=11" defect), 122 `stale-link` (no Find row on the phone) | 19: read the phone's Brain "Coming up" plate on a current build and count the rows it draws; 122: a genuinely stale link must exist to observe it | 19: **no owner needed** (agent with phone); 122: **no practical way** without manufacturing a stale link |

### 3.2 NOT-TESTABLE (14 rows) — absent accounts, hardware, voice, or a deliberate refusal to provoke

`65 chatbot-money` (owner's chatbot keys + monthly limit), `67 crisis-help` (**deliberately not
provoked**, as the matrix says), `68 home-status`, `69 lights`, `70 locks` (Home Assistant not
present), `71 calendar`, `72 weather-sky`, `73 email-read`, `74 email-send`, `75 email-drafts`,
`76 inbox-tidy` (owner's mail account not set up here), `113 accounts` (the owner's accounts/keys),
`130 galaxy picture` (the matrix's reason: *no human has run it on a phone*), `134 read-aloud-withheld`
(needs a private-gated answer).

* **Owner-only in substance:** 65, 67 (must not be provoked casually), 68, 69, 70, 72, 73, 74, 75,
  76, 113.
* **Row 71 `calendar` is overtaken by today's own field test.** The matrix's NOT-TESTABLE reason was
  *"Not included: your calendar is not set up for Jarvis on this PC"*
  (`docs/FIELD-TEST-2026-10-12-TOPUP.md:117`). But `FIELD-TEST-FINAL-2026-10-30.md:27` row 4 records
  the phone Calendar **driven today**: it rendered *"October 2026"*, *"Friday 30 October, today"*,
  *"Nothing on this day."*; a *"Field test"* 09:00 event was created and the PC's `GET /api/calendar`
  showed it (`id cf10c9605c7`), then it was deleted from the phone and the PC read `events=0`. The
  matrix row's stated reason no longer holds for the phone's own calendar; **updating the matrix row
  is the Lead's/record owner's call** — this report only names the contradiction, and does not
  promote the row (the desktop calendar page and any external-calendar account were not driven).
* **Row 130 `galaxy picture` is drivable now without the owner's hands** — the phone is attached and
  the read-only Galaxy picture needs no biometric or approval. It was **not** driven in this session
  because the session is read-only and opening the app is a launch; it is a genuine candidate for an
  agent-at-phone pass next.
* **Row 134 `read-aloud-withheld`** needs a private-gated answer to exist; that is data/owner
  dependent, not drivable read-only today.

### 3.3 SCREEN (93 rows) — not unproven-by-failure; simply never operated

The matrix's own correction says these are rows whose **screen or row was found and read, never
exercised**. Nothing in this session lowers or raises them: a PASS for any one needs the feature
operated on the phone (uiautomator taps + reads, as the matrix's method section describes) or on the
desktop (UI Automation), and this session was read-only. The matrix's own "what cannot be tested
from a checkout" list — his voice for the ACCEPT half, the PC microphone print, the tray, Home
Assistant, his accounts — still stands as written
(`docs/FIELD-TEST-MATRIX-2026-10-11.md:78-99`).

### 3.4 A record inconsistency worth naming (row 39)

Three records disagree about matrix row 39 `history`:

* `docs/FIELD-TEST-2026-10-13-PHONE-PASS.md:80` — **PASS**: the History list was reachable and
  readable with no gate on that build (*"the conversation list itself (`Untagged (41)`, then named
  conversations with their dates and message counts) … that sentence is gone"*).
* `docs/FIELD-TEST-2026-10-12-TOPUP-3.md:74` — **PARTIAL**: *"the conversation list is the owner's
  to unlock"*.
* The matrix row 39 (`docs/FIELD-TEST-MATRIX-2026-10-11.md:398`) — **SCREEN**, with the 2026-10-13
  correction citing TOPUP-3 and *not* the later PHONE-PASS, i.e. the matrix kept the lower reading.

Today's owner screenshot again shows the list visible. Both readings can be true at different
times (the cover depends on the phone's Security setting / lock state), so the honest resolution is
**PARTIAL with the state dependency named**, and the archive action remains the unproven half. This
report does not edit the shared matrix (it must not be edited from here); it names the gap for the
record owner.

---

## 4. Owner-provided screenshots (16:22–16:23 PDT) — recorded exactly as evidence

**Source and limits.** The owner sent two screenshots to the Lead; the Lead relayed them to this
subagent in words. **I did not receive or view the image files**, so every label quoted in §2.2(a) is
the Lead's transcription, not my own OCR. They are recorded as **OWNER-VISUAL evidence**: the owner
saw the app on his own phone; no agent drove anything.

| item | owner-visible evidence | what it proves | what it does not prove |
|---|---|---|---|
| Screenshot A (History, ~16:22) | Real History screen with the conversation list visible: `CONVERSATIONS`, filters `All chats / Just chats / Live only / Support chats / Chats with other AIs / Comparisons / Archived`, `Untagged (238)` expanded with named chats, times, `phone`, message counts | the installed app **renders the History screen and a real PC-backed list**; the `Archived` filter UI is present (consistent with #987 being in build `21add9d53`) | not the Show gate (not exercised/shown), not the Archive action (not operated), not agent-driven |
| Screenshot B (More sheet, ~16:23) | "More" sheet over the chat screen with its full list (New chat, Earlier chats, Pinned messages, Jarvis Presets, Photo, Attach a file … up to 2.5 MB, Think, Coach this, Incognito, Quick note, Close) and `Connected` | the installed app **renders the More sheet correctly** on this phone | nothing further — it is a screen read |

**Build that produced them (measured now):** `versionName=0.2.3261`, `versionCode=1000003261`,
`lastUpdateTime=2026-10-30 12:01:36`, i.e. the APK from `main` `21add9d53`. **Not** the newest
published build (`0.2.3272` / `d72735a`, asset 15:22 PDT) — see §1.

---

## 5. What the owner must do to finish the two named rows (plain words, for relaying)

1. **Home widget (2 minutes).** Open Jarvis on the phone → **Brain** → **Widgets**. The home-screen
   slot ("Jarvis widget 2") shows **"No widget chosen"**. Choose the saved **"Next Reminders"**
   widget for that slot (it is still saved on the PC). Then look at the home screen: it should say
   **"Next Reminders"** with the three upcoming reminders, not "No widget chosen".
2. **History archive (2 minutes).** Open Jarvis → History. If it says **"Hidden. Tap Show and
   confirm it is you."**, tap **Show** and pass your fingerprint or PIN — that is the by-design gate
   and only you can answer it. With the list showing, tap the three-dot menu on any chat →
   **Archive**. Tap the **Archived** filter (beside the Show chips) and check the chat is there.
   Then three-dot → **Unarchive** to put it back.
3. **Nothing else.** No approval cards are involved in either; both are reversible and local.

For the Lead's own follow-up: the cheapest confirmation of (2) after the owner taps is the live
audit log line `"event": "history.archive"` in
`C:\Users\pcadmin\.openjarvis\logs\jarvis-2026-10-30.jsonl` (or `GET /api/history?archived=1` with
the token, by whoever is permitted to call the live API).

---

## 6. Limits of this measurement, said plainly

* No live API call was made and the token was not read. The "routes are live" claim is code
  inspection of the repaired live HUD (`jarvis_hud.py:4735-4738`, `:4765`) plus the handoff's own
  post-restart measurement ("400 not 404", handoff §4), not a new round trip.
* No install, no launch of the Jarvis app, no approval, no phone app data read. The only phone input
  was one `KEYCODE_HOME` so the launcher could be read; the phone was left on the home screen, still
  connected (`adb devices` → `f0a5b32b device` at 16:32 PDT).
* The in-app Brain → Widgets plate text was not read directly (a release build does not expose its
  data store). The empty-slot state is evidenced by the **launcher's own accessibility tree**
  (`No widget chosen` inside the "Jarvis widget 2" card) plus the morning field-test record.
* The owner's screenshots were relayed in words, not viewed as images.
* The stale/dirty primary checkout was used only as the location of the matrix document and of this
  scratch folder; all `origin/main` claims were read from the git object database at `57c14136c`.
* Matrix counts are quoted/counted from the document, not re-tested.

## 7. Artifacts written here

| file | what |
|---|---|
| `REPORT.md` | this report |
| `appwidget-dump-20261030.txt` | full `adb shell dumpsys appwidget` (26,589 B; launcher + Jarvis providers/bindings) |
| `home-dump-20261030.xml` | `uiautomator` dump of the launcher home page (9,766 B; contains "No widget chosen" and content-desc "Jarvis widget 2") |
| `phone-package-20261030.txt` | captured `dumpsys package com.jarvis.client` version/install lines |
| `pass2\` | raw dumps from the concurrent pass (see the section below) |
| `phone-ui.ps1` | the read-only phone UI reader/driver used for the concurrent pass (dump / tap a node / scroll / BACK / HOME) |

---

## Concurrent pass — 2026-10-30 17:52–17:56 PDT (Galaxy picture row 130, Coming up row 19, widget re-check)

**Method.** Phone UI only, through `adb`: launch `com.jarvis.client`, read the accessibility tree
(`adb shell uiautomator dump`), tap nodes by their own bounds (`adb shell input tap`), scroll
(`adb shell input swipe`), HOME. No writes, no approvals, no install, no live API, no token. Raw
dumps: `pass2\pass2-*.xml` next to the first pass's evidence. **The phone was left on the launcher
and is still connected** (`f0a5b32b  device`, checked at 17:55:24 PDT).

**Two facts that moved before this pass started:**

* `origin/main` is now **`263ea0d86`** (measured 17:53 PDT; the first pass read `57c14136c`).
  #1004, #1005, #1007, #1009 and #1010 have merged since.
* `client-latest` is now **0.2.3285 from `263ea0d`**, built 2026-10-31 00:36 UTC (17:36 PDT, sha256
  `78e3a97e…`). The installed app (**0.2.3261, main `21add9d53`, installed 12:01:36**) is now **two
  published builds behind**. The app's own Home banner says so: *"A newer build of this app is on
  GitHub (main, 263ea0d). Nothing is downloaded until you choose to."* (measured in
  `pass2-home.xml`). Code citations below were re-read this pass at `origin/main` `263ea0d86`.

### Row 130 — the phone's read-only Galaxy picture — **BLOCKED** (owner's biometric Show), not PASS, not PARTIAL

**Correction of the first report's §3.2 bullet.** The first pass listed this row as *"drivable now
without the owner"*. That is only true while the phone's hidden-memory gate is unlocked. At 17:53 the
gate was **up**, so the picture could not be reached by an agent at all:

* Tapped Home's **"The Galaxy →"** door (text found and tapped at `190,921`, bounds
  `[36,849][345,993]`).
* The Brain opened on **"PEOPLE AND THINGS"** and the plate's whole body was the hidden state — the
  dump contains exactly the line `Hidden. Tap Show and confirm it is you.` plus a `Show` button, and
  **no** galaxy picture, no dot names, no band and no names list.
* Code proof the picture is behind the same guard, not only the list: `EntitiesPlate.kt:100-108` —
  `PeopleAndThingsSection(...)` starts `if (privateHidden) { HiddenSection(Entities.TITLE, busy =
  showPrivateBusy, onShow = onShowPrivate); return }`; the picture is drawn only after that guard at
  `:209-238` (`Kicker(Entities.GALAXY_TITLE)` → `GalaxyPicture(band, …)` → `GalaxyBand(band)`). The
  door's own doc says the same (`HomeScreen.kt:2636-2642`: *"the plate's own 'Hide memory lists and
  chat history' guard decides whether names are shown … this button adds no way around it"*).

So **no part of row 130 was driven**: no names, no links, no 48-name cap, no tap-to-facts. **Status:
BLOCKED** — the blocker is the owner's biometric Show, by design; it is not a defect.

**Why it was locked again.** The owner's 16:22 screenshots showed the lists visible; the app was then
in the background from ~16:32 to 17:53 (this session left it on the launcher) and at 17:53 it was
locked. Why it re-locked was **not measured** (screen lock / app process restart are the likely
causes); the measured fact is the state change.

**To finish (one owner action unlocks this row and the archive row together):** the owner taps
**Show** and passes fingerprint/PIN once; then, in that unlocked session, a read-only run can record
the picture's dot nodes (each dot's content-desc is `Entities.galaxyNameLine`), the band/list, the
`Showing {n} of {total}` line at the 48-name cap (`Entities.kt:112`), and a tap on one dot → that
name's facts view → **"Back to the list"** (`Entities.kt:99`). PASS = those observed.

### Row 19 — timers, alarms, reminders and lists (Coming up) — **PARTIAL**

**Driven read-only, and the plate now opens and draws.** Path measured: Home → **Brain** → scrolled
to the **"Money and time"** section row (`[48,1548][1032,1692]`, its own line `8 inside`) → tapped it
→ the **COMING UP** plate was open (a `Fold` control is present, which only an expanded plate has).
Exact labels read from the dump, top to bottom:

* `Timers, alarms and reminders, kept on your PC. They go off on both apps while they are connected. A repeating reminder or alarm is set up at once, with no card; a repeating briefing or "tell me when" waits for your yes on an approval card.`
* `They go off on your PC. This phone shows them while it is connected to it.`
* `Words hidden. Tap Show and confirm it is you.` + `Show` — the reminder words are hidden by the
  same privacy setting, by design (`ComingUpPlate.kt:63-65`: the words are hidden *"but not the
  times, so a timer still counts down; Show brings the words back"*).
* `Nothing coming up. Say or type "set a timer for 10 minutes" or "remind me at 6 to call Mum".`
* `Tell me when` + its explanation; `Reminder for next time` + its explanation.
* `To-do list` → `Nothing on your to-do list.` + `Add`.
* `Standby schedule` → explanation, `STANDBY AT 01:00`, `WAKE AT 07:00`, `Set up`.
* then the next plate: `JARVIS CALENDAR` → `Today, 30 October`, `Nothing today`, `Open the calendar`.

**What that changes about the row's old record.** The row was BLOCKED on 2026-10-11 because the plate
was *declared* but not composed (`screen declared=19 … composed=11`, `found=false`). On the installed
0.2.3261 the plate **does open and draw its whole body** — that blocker looks fixed on this build. It
is still **not a PASS**: the PC reported **nothing coming up and nothing on the to-do list**, so no
timer/reminder/alarm/to-do row existed to observe, and no action was driven (this pass is read-only).
PASS needs one real upcoming item on screen (a live timer counting down, or a reminder with its time)
and, for the action half, one disposable item's Pause/Resume/Delete driven.

**Empty is the PC's own answer**, not a phone failure: the same pass saw the calendar plate answer
`Nothing today`, and the phone was `Connected`.

### Re-check: home widget slot and app version — nothing changed

Measured at 17:55:24 PDT, after returning to the launcher:

| item | first pass (~16:26) | now (~17:55) | changed? |
|---|---|---|---|
| launcher widget text | `No widget chosen` / `Tap, then choose one under Brain, Widgets` | same, unchanged | **no** |
| widget slot | content-desc `Jarvis widget 2` | same | **no** |
| app version | 0.2.3261 / versionCode 1000003261 / lastUpdate 12:01:36 | same | **no** |
| `client-latest` | 0.2.3272 / `d72735a` | **0.2.3285 / `263ea0d`** | yes (release moved) |
| `origin/main` | `57c14136c` | **`263ea0d86`** | yes (main moved) |

So **the owner has not re-picked the widget** yet, and nothing else about the install changed.

### What is left for the owner (unchanged, and smaller than it looks)

1. **Widget re-pick** — Brain → Widgets → slot "Jarvis widget 2" → choose **"Next Reminders"**.
2. **One Show, then the two hidden-memory rows.** Tapping **Show** + fingerprint/PIN once unlocks
   the hidden-memory gate for that session; in that same window the **history archive** round trip
   and the **Galaxy picture** (row 130) can both be driven. Suggested order: owner taps Show; an
   agent (or the owner) immediately opens History → chat ⋮ → Archive → Archived filter → Unarchive,
   and Home → The Galaxy → (the picture now drawn) → tap a dot → facts → Back.

No approval cards are involved in any of this.

### Raw evidence files for this pass

`pass2\pass2-home.xml` (Home, with the newer-build banner), `pass2\pass2-galaxy-open.xml` (the
Hidden/Show gate where the picture should be), `pass2\pass2-brain-scroll1.xml` and
`pass2\pass2-brain-scroll2.xml` (the Brain sections, the `Money and time` row),
`pass2\pass2-money-time.xml` (COMING UP plate top), `pass2\pass2-comingup-2.xml` and
`pass2\pass2-comingup-3.xml` (to-do list and standby rows), `pass2\pass2-home-launcher.xml` (widget
state at 17:55).

---

## SCREEN-row batch 2026-10-30 18:05–18:10 PDT (read-only phone UI, 27 rows)

**Method.** `adb` only: launched `com.jarvis.client`, read the accessibility tree
(`adb shell uiautomator dump`), tapped nodes by their own bounds, swiped to scroll, BACK/HOME. **No
writes were made**: no setting was toggled, no model switched, no style added, no backup made, no
folder added, no notification access granted, no Live session started, no chat message sent (a chat
turn writes history, so it was not done). No live API, no token, no install, no approval. The app's
own Home banner still reads *"A newer build of this app is on GitHub (main, 263ea0d)…"*; `origin/main`
was `263ea0d86` when this pass read the code, and the phone runs **0.2.3261 / versionCode 1000003261 /
lastUpdate 12:01:36** (unchanged). The phone was left on the launcher, still connected
(`f0a5b32b  device` at 18:09:41 PDT).

**Method note that saves the next runner time.** Settings' `JUMP TO:` links are **in-page scrolls** of
one long Settings page, not separate screens; one BACK from a scrolled Settings page exits Settings
straight to Home. The batch therefore did: BACK → Settings → tap the target → dump, per row.

**What the statuses mean here.** PASS is used only where the feature *is* a read-only readout and the
readout was operated and observed (a list/state screen opened with real data). PARTIAL means the
screen/row opened and its own words/state were read, but the effect would need a write (the write is
named). NOT-REACHABLE means the thing needs something the owner alone can supply. No row in this
batch hit the `Hidden. Tap Show and confirm it is you.` gate — the memory-gated rows were deliberately
not opened, because this batch is for rows reachable **without** the biometric Show.

| # | row | status | what was driven (adb) and the evidence read |
|---|---|---|---|
| 12 | Jarvis Live (`live`) | **PARTIAL** | Home → Live tab. Read: `Jarvis Live`, `Talk back and forth - no "Hey Jarvis" needed`, `Jarvis is idle`, `Start Jarvis Live`, and *"Jarvis listens after every answer until you end it, say "Okay Jarvis, that's all for now", or it has been quiet for 90 seconds. Every sentence is checked for your voice on your PC before any words are made of it."* Session **not** started (it opens the mic — a state change), so the behaviour is undriven. |
| 23 | What Jarvis is doing right now (`now`) | **PASS** | Home → Brain → `What Jarvis is doing` section → DOING plate. Read `Link live · board read just now`, `Activity — Idle`, `Power — Active`, `Route — Not reported`, and the plate `WHAT JARVIS IS DOING / Nothing yet. Steps appear here while Jarvis answers with its tools.` The feature is the read-only state readout; it was operated and observed. |
| 24 | How much Jarvis may interrupt you (`attention-budget`) | **PARTIAL** | Brain: `ATTENTION BUDGET`, `3 of 3 spoken interruptions left today`, `Speak up`, and *"Turning the count down applies at once. Turning it up asks you on the PC first, and nothing changes until you answer there."* Value read; changing it is a write (not done). |
| 25 | Focus session (`focus`) | **PARTIAL** | Brain → `Your projects and goals` region: `Last session`, `Focus session stopped early.`, `On target: 0 of 1 minute (10 planned).`, `No drifts.`, `100% focused.` Read the last-session report; starting a session is a state change (not done). |
| 51 | Folders Jarvis may look in (`folders`) | **PASS** | Settings → `Folders Jarvis may look in`. Read the folder list `Documents — C:\Users\pcadmin\Documents — Remove`, `Folders are added on the PC: Settings, Folders Jarvis may look in.`, `PDF, Word, Excel and PowerPoint files can be read.` Read-only list; opened and read. |
| 53 | Tutorials and the FAQ (`tutorials`) | **PARTIAL** | Help tab: FAQ index read (`Do I need Tailscale for this to work?`, `Does this app run any AI on my phone?`, `How do I teach Jarvis my voice? …`, `Why can't I approve everything waiting for me in one tap?`, …); opened `How do I update Jarvis?` and read its full answer (*"Most of it in one command… scripts/update-jarvis.ps1… This app: install the newest file from the release page over the old one; it stays paired."*). The FAQ half was driven; the tutorials catalogue half was not reached on this screen. |
| 56 | A browser without a window (`browser-engine`) | **PARTIAL** | Settings → `Browser without a window (Obscura)`. Read `Off. Jarvis uses the visible browser only.`, `Obscura is not installed on this PC yet.`, plus the full explanation. State read; the behaviour needs Obscura installed on the PC (a PC-side install, not done). |
| 58 | Talk to a chatbot for me (`chatbot`) | **NOT-REACHABLE** | Brain → `TALK TO A CHATBOT FOR ME` (explanation read: *"Jarvis asks an AI chatbot about something for you, and writes its own follow-up questions on this PC, within limits you set. One approval card covers the whole conversation…"*), and the per-site state: `Gemini — Jarvis's Gemini window has never been signed in…`, `ChatGPT — …never been signed in…`, `Claude` listed. Blocked by the owner's accounts: nothing can be operated without a sign-in on the PC. |
| 79 | Devices (`devices`) | **PASS** | Settings → `Devices`. Read `This PC — PC`, `OnePlus (this phone) — phone · paired 10 Oct · last active just now`, `Pixel 9 — phone · paired 17 Oct · last active just now`, `Signed approvals — Off…`, `Old shared key…`. Read-only device list; operated and read. |
| 80 | Let Jarvis read phone notifications (`phone-notifications`) | **PARTIAL** | Settings → `Phone notifications`. Read `Jarvis never sees a phone notification.`, `Notification access: not granted yet.`, `No apps added yet.`, `No captured notifications are kept on this phone.` State read; granting access is an OS write (not done). |
| 81 | Smartwatch notifications (`phone-watch`) | **PARTIAL** | Settings → `Smartwatch notifications` section: `NOTIFICATIONS`, `Show notifications on a compatible watch`. No paired watch exists, so the behaviour is not observable — row label read only. |
| 82 | Floating Jarvis (`phone-floating`) | **PARTIAL** | Settings → `Floating Jarvis`: `Off / Bubble / Overlay`, `Off. Nothing floats over other apps.` Choices/state read; switching is a write. |
| 88 | Appearance (`appearance`) | **PARTIAL** | Appearance tab. Read `Follow the system`, `THEME` (`Reactor`, `Daylight`, `High Contrast` + descriptions), `HOME` (`Face size on Home: Full screen / Extra large / Large / Medium / Hidden` + explanation), `Tabs row`. Options read; nothing changed (a write). |
| 90 | Choose Jarvis's face (`faces`) | **PARTIAL** | Appearance → `FACE`: the face is drawn (`content-desc="Jarvis is idle"` — the documented drawn-not-text dead end), and the readable labels were captured: `Cycle states`, `Face editor — Pattern, colour, quality, frame rate and speed.`, patterns `Arc / Orbit / Comb / Spiral / Iris / Fullerene`, and the face list `Tokamak / Membrane / Red Panda / Pygmy Owl / Sea Otter / Monkey / Robot` with *"All 25 of the desktop's faces render here now"*. Labels read; the face picture itself cannot be read by this harness (no vision) and no face was changed. |
| 91 | Animal options (`animal-options`) | **PARTIAL** | Appearance → `ANIMAL OPTIONS`. Read `Keep the animal still`, `Cute idle moments`, `Seasonal touches`, `SUN, MOON AND WEATHER / Show the sun and moon behind the face`, `Your town — No town yet, so there is no sun or moon to show…`. Full options plate read; none changed (writes). |
| 93 | Show or hide menus (`menu-visibility`) | **PARTIAL** | Settings → `Show or hide menus`. Read `This hides menus on this device only.`, `Nothing is hidden.`, `Show everything`, and the per-group rows with what each hides (e.g. `Study — Hides Quiz me on a text, Quiz from a YouTube link, My study decks`; `Goals and projects`…). Read; hiding/hiding settings are writes. |
| 95 | Models (`models`) | **PASS** | Home → `Model →`. The MODEL plate listed real installed models, each with `Use`: `gemma4:12b-it-qat`, `minicpm-v4.6:latest`, `medgemma1.5:4b-it-q4_K_M`, `hf.co/mradermacher/Huihui-Qwen3.5-9B-abliterated-GGUF:Q4_K_M`, `jonathancoletti-qwen3.8-27b…`, `qwen3-coder-30b-a3b-ud-q3-k-xl:latest`, `qwen3-vl:8b-thinking`, `jarvis-uncensored-qwen2.5-14b:latest`, `qwen3.5:0.8b`, … The read-only list is the feature; opened and read. `Use` not tapped (switching a model is a write + approval card). |
| 99 | Notifications (`notifications`) | **PARTIAL** | Settings → `Notifications from Jarvis`. Read `NOTIFICATIONS FROM JARVIS / Open Android's notification settings`, `NOTIFICATION STYLES`, `Live now: approval cards - Deep Blue Spark Pulse, reminders - Deep Blue Spark Pulse.`, `Hidden - open Jarvis to see it.`, and the style prompt. Read; creating/adding a style is a write. |
| 103 | Hardware and models (`hardware`) | **PASS** | Home → `Presets →` → `HARDWARE`. Read `FOCUS PRESETS`, `General - Current`, `qwen3.5:9b on RTX 2060 (the long-context card), 196,608 tokens`, *"9.17 of its 12 GB; nothing else fits beside it. Writing is 44.9 tokens a second…"*, `The Fast preset uses the 2080 SUPER.` Read-only hardware readout; operated and read. |
| 104 | The second graphics card (`second-card`) | **PASS** | Same `HARDWARE` plate: the RTX 2060 is named as the long-context card with its model/token/GB/speed readout, and the 2080 SUPER is named as the Fast preset's card — the second-card lane's readout was observed. (No preset applied, no model switched.) |
| 110 | About Jarvis (`about`) | **PASS** | Help → scrolled to `About Jarvis`. Read `Version — 0.2.3261`, `Made by — darknight11ish`, `Licence — MIT, with third-party parts under their own licences`, `Signed by — 62ef7742e35e`, and the About paragraph. Read-only card; operated and read. |
| 112 | Backups (`backup`) | **PARTIAL** | Settings → `Backups`. Read `Last backup: 20 days ago.`, `In: Jarvis Backups`, `Kept: 4 of the last 5.`, *"Jarvis checked this file just now: it is a complete, well-formed backup, and nothing about it has changed since it was written."*, plus the note that proving a backup opens needs the recovery code on the PC. Status/integrity read; making a new backup is a write (not done). |
| 114 | What Jarvis can reach (`reach`) | **PASS** | Settings → `What Jarvis can reach`. Read the list: `Cloud model - On / Goes to: api.deepseek.com / Asks you first: Yes, every question`; `Web search - On / Goes to: this PC (SearXNG, which asks other search engines) / Asks you first: Only when private things could slip in…`; `Read one web page out loud - Off`; and the intro *"The PC writes this list from its own settings - the AI model does not write it…"*. Read-only readout; operated and read. |
| 118 | Approval cards (`approvals`) | **PARTIAL** | Settings → `Approval cards`. Read `APPROVAL CARDS`, *"This only changes how much of a card is shown at first - the same card, the same words underneath, the same buttons."*, `Start short (default) (in use)`, `Always show everything`. This is the card-display setting only; **the matrix row stays BLOCKED** — actually raising and answering a card is the owner's. |
| 119 | What asks first (`what-asks-first`) | **PARTIAL** | Settings → `What asks first`. Read `WHAT ASKS FIRST`, `Lockdown is off: everything asks first as your settings say.`, `Turn on Lockdown`, `Reading your own things`, `Read your calendar - Does it without asking` + `Ask me first`, `Read your email - Does it without asking` + `Ask me first`, and the explanation *"The PC writes this list from its own settings - the AI model does not write it… Letting one go ahead without asking … takes an approval card and Windows Hello."* List read; toggling a row is a write. |
| 120 | Lock Jarvis, and hide what it remembers (`app-lock`) | **PARTIAL** | Settings → `Security`. Read `SECURITY`, `App lock off, risky approvals ask, memory lists hidden.`, `Lock and fingerprint settings`, and the `APP CONTROL` section. Summary read; **the matrix row stays BLOCKED** — enabling the lock needs the owner's lock/fingerprint. |
| 121 | Hand a captcha to your phone (`captcha-handoff`) | **PARTIAL** | Settings → `When a captcha stops Jarvis`. Both choices read in full: `Leave it where it is (in use)` + *"The window is not touched: it keeps its size, its place and whatever is in front of it…"*; `Bring it to the front` + *"That one window is raised and activated the moment Jarvis is stuck… turning this on asks for your approval."* Read; choosing is a write/approval. |

**Rows that were candidates but are deliberately not in the table** (so nothing is overclaimed):

* the memory-gated rows (`history`, `memory-*`, `pinned-facts`, `between-us`, `chat-tags`,
  `sensitive-facts`, `forget-range`, and the Galaxy picture row 130) — opening them today shows
  `Hidden. Tap Show and confirm it is you.`, which needs the owner's biometric; this batch is the
  rows reachable without it;
* **83 `phone-tiles`** — no on-screen row for it was found on the Settings or Appearance surfaces
  visited; not claimed either way (`MenuCatalog.kt:99` defines the setting id, but this pass did not
  see a visible control for it);
* **94 `shortcuts`** — the phone's own feature directory says it is a PC-only setting on the phone
  (`FeatureDirectory.kt:137`, "Honest Refusal on Phone"); not driven on the phone;
* **92 `first-run`** — the row was not found on the Home/Settings/Help surfaces visited in this pass;
* rows needing a state-changing turn (chat `typing`, answers, notes, alerts that post) — a message
  writes history, so they are PARTIAL at best and were not driven read-only.

**Limits of this batch.** A settings page read is not a setting operated: every control here is
marked PARTIAL for that reason, with the write it would need named. PASS rows are the read-only list
or state surfaces (About, Devices, Folders, Models, Hardware/second card, Reach, Now). The `Faces`
picture remains the documented drawn-not-text dead end. No count of hidden/composed rows was retried
here; that was the earlier pass's question and this batch does not re-answer it.

**Raw dumps for this batch** (in `pass3\`): `p3-home.xml`, `p3-help.xml`, `p3-help-2.xml`,
`p3-faq-answer.xml`, `p3-settings-1.xml`, `p3-settings-bottom.xml`, `p3-asks-first.xml`,
`p3-reach.xml`, `p3-backups.xml`, `p3-watch.xml`, `p3-phone-notifications.xml`, `p3-floating.xml`,
`p3-menus.xml`, `p3-captcha.xml`, `p3-folders.xml`, `p3-notifications.xml`, `p3-email.xml`,
`p3-devices.xml`, `p3-browser.xml`, `p3-phone-noanswer.xml`, `p3-security.xml`,
`p3-approvalcards.xml`, `p3-appearance.xml`, `p3-appearance-2.xml` / `-3.xml` / `-4.xml`,
`p3-model.xml`, `p3-presets.xml`, `p3-doing.xml`, `p3-projects.xml`, `p3-live.xml`,
`p3-home-launcher.xml`, plus the captured `before-*`/`-root`/`-leave` intermediates.

---

## Gemini-authorized agent pass 2026-10-30 18:17–18:27 PDT (widget re-pick, to-do round trip, archive)

**Authority / scope.** Gemini's F1–F6 rulings (`C:\Users\pcadmin\Downloads\gemini_rulings_f1_to_f6_field_test_gaps_2026_10_30.md`,
§2 F3/F5) authorize an agent to drive the widget re-pick, the reversible archive, and the 93 SCREEN
rows, with every state restored. This pass therefore made **three reversible drives only**: the
slot-2 widget re-pick, one scratch To-Do add+delete, and an attempt at one archive round trip. No
approval card was answered, no user data was deleted beyond the item created in this pass, nothing
external was sent, and no security toggle was touched.

**Evidence standard (Gemini F3 a–e).** (a) build: phone `f0a5b32b` (CPH2419/OnePlus, Android 15),
`com.jarvis.client` **0.2.3261 / versionCode 1000003261**, `lastUpdateTime 2026-10-30 12:01:36`,
`firstInstallTime 2026-10-09 22:14:29`; installed build candidate `main` **`21add9d53`** (commit
`2026-10-30 11:43:17 -0700`, per `FIELD-TEST-FINAL:5-6,17-18`); `origin/main` during this pass
**`263ea0d86`**. Saved in `pass4\p4-build-evidence.txt`. (b) pre-action dumps, (c) exact taps and
commands, (d) post-action dumps, (e) restoration dump / audit-log lines — all below, raw files in
`pass4\`. The phone was left on the launcher, connected, at the end.

### Row 21 `widgets` — **PARTIAL, NOT promoted to PASS**

* **Before** (`p4-widget-before.xml`): launcher card `content-desc="Jarvis widget 2"` reads
  `No widget chosen` / `Tap, then choose one under Brain, Widgets`.
* **Drive**: Home → Brain → `Money and time` → `WIDGETS` plate → Open. The plate's slot control
  showed `Jarvis widget 2` with the two choices `Nothing` / `Widget 1`, and the
  `Put it on my home screen` button was **already present** — which the code only draws once that
  slot has a widget (`WidgetsPlate.kt:172-180`). So the app-side slot-2 mapping was already set (the
  only saved widget is `w7dbe0ba0ae`; its name renders as `Widget 1` while the lists are hidden —
  `WidgetsPlate.kt:160-167`).
* To force a real re-pick: tapped `Nothing` (slot cleared; the PIN button disappeared —
  `p4-widget-cleared.xml`), then tapped `Widget 1` (mapping restored; PIN button returned —
  `p4-widget-repicked.xml`). **Net state after the drive = the same mapping as before it** (slot 2 →
  the one saved widget).
* **After** (`p4-widget-after.xml`, `-after2`, `-after3`, `-after4`, `-after6`, `-after7`): the
  launcher card **still reads `No widget chosen` / `Tap, then choose one under Brain, Widgets`.**
  Also tried: `Put it on my home screen` twice (`p4-widget-pin.xml`, `p4-widget-pin2.xml`), the
  WIDGETS plate's own `Refresh`, an 8-second wait, and a force-stop + fresh app process
  (`p4-widget-after6.xml`). Attempting to wake the provider directly with
  `adb shell am broadcast -a android.appwidget.action.APPWIDGET_UPDATE -n
  com.jarvis.client/com.jarvis.client.widget.JarvisBoardWidgetTwoReceiver --eia appWidgetIds 35`
  was **refused by Android**: `SecurityException: Permission Denial: not allowed to send broadcast
  android.appwidget.action.APPWIDGET_UPDATE from unknown caller`.
* **Verdict: PARTIAL.** The app-side preference is correct and persisting, but the home-screen card
  does not repaint to the mapped widget on this install. That is an update-path finding, not a
  missing preference; row 21 stays PARTIAL until the card itself shows `Next Reminders` /
  `Coming up`.

### Row 19 `coming-up` — **PASS** (add → rendered → delete → restored, with PC audit proof)

* **Pre-action** (`p4-t2-comingup-header.xml`): `To-do list`, `Nothing on your to-do list.`, the
  empty Add field and `Add`.
* **Drive**: tapped the Add field (`540,1421`), typed `FIELD TEST 2026-10-30 - delete me`
  (`adb shell input text`, spaces as `%s`), pressed IME Done (`input keyevent 66`).
* **Post-action** (`p4-t2-enter.xml`): the list changed to a `to-do` row showing `(hidden)` with
  `Done` and `Delete` where "Nothing on your to-do list." had been — one to-do **rendered under
  Coming up**. While "Hide memory lists and chat history" is on, the item's own words are replaced
  with `(hidden)` by design (`Schedule.kt:477-497`); the row and its buttons are what the phone can
  show, and the item's real name is proven by the PC audit line below.
* **Delete**: tapped `Delete` (`345,1467`) → `p4-t2-deleted.xml` shows `Nothing on your to-do list.`
  again. **Pre-test state restored.**
* **PC-side proof** (read-only, `C:\Users\pcadmin\.openjarvis\logs\jarvis-2026-10-31.jsonl`):
  ```
  L1: {"t": 1793409917.669, "iso": "2026-10-31T01:25:17Z", "event": "schedule.add", "detail": {"id": "sb4346b7243", "kind": "todo", "repeats": false}}
  L2: {"t": 1793409929.603, "iso": "2026-10-31T01:25:29Z", "event": "schedule.act", "detail": {"id": "sb4346b7243", "kind": "todo", "do": "delete"}}
  ```
  Same id added at 18:25:17 PDT then deleted at 18:25:29 PDT — a clean create/remove, no other
  schedule rows touched. Saved in `pass4\p4-audit-evidence.txt`.
* **Verdict: PASS** for the F5 criterion ("adds one scratch To-Do, observes it rendered under
  Coming up, and deletes it"), with the honest caveat that the phone displays `(hidden)` for the
  words while the owner's privacy setting is on.

### Row 39 `history` archive round trip — **BLOCKED** (owner's biometric Show)

* `p4-t3-history.xml`: History opens correctly (`Chat history, kept on your PC`, `On. New chats are
  kept on your PC, encrypted.`, `Change chat history settings.`), but the `CONVERSATIONS` section
  reads exactly **`Hidden. Tap Show and confirm it is you.`** with a `Show` button.
* Per the task, stopped there. No chat was opened, archived or unarchived; the audit log contains
  **no `history.archive` event** in either the 10-30 or the 10-31 file (checked).
* **Verdict: BLOCKED** — the owner must tap `Show` + fingerprint/PIN once; the same unlocked window
  can then drive row 39 (Archive → Archived filter → Unarchive) and row 130 (the Galaxy picture).

### Important for F5's evidence rule: the audit file name rolls at 17:00 PDT

`jarvis_framework.py:650-658` names the audit file by **UTC date**
(`time.strftime('%Y-%m-%d', time.gmtime(when))`), so any evening drive after **17:00 PDT** writes to
`jarvis-2026-10-31.jsonl`, **not** `jarvis-2026-10-30.jsonl` (that file's last write is 13:54:12
PDT, last event `android.installed`). Gemini F5 says row 39 promotes when `history.archive`
`true → false` is recorded in `jarvis-2026-10-30.jsonl`; when the owner unlocks and this is driven
tonight, the proving line will be in the **10-31** file. The to-do audit lines above are in that
file for the same reason.

### Final state

Phone: `f0a5b32b  device`, `topResumedActivity=com.android.launcher/.Launcher`, version unchanged
(0.2.3261 / lastUpdate 12:01:36), measured 18:27 PDT. Raw dumps and evidence files in `pass4\`
(before/after widget dumps, `p4-t2-*.xml` for the to-do round trip, `p4-t3-history.xml`,
`p4-build-evidence.txt`, `p4-audit-evidence.txt`).

---

## Gemini F5 — desktop Calendar UI pass (2026-10-30 18:44–18:51 PDT) — **PARTIAL, exact failure recorded**

**Task.** Drive the installed desktop HUD's Calendar view read-only through Windows UI Automation
(`docs/FIELD-TEST-HOW-TO-READ-THE-APPS.md` method 2, starting from `scripts/fieldtest-desktop.ps1`)
to close row 71's remaining desktop half to PASS. **It could not be reached, and the reason is
recorded here rather than smoothed over.**

**Build measured (a).** `C:\Users\pcadmin\AppData\Local\Jarvis Desktop\jarvis-desktop.exe` —
**FileVersion 0.2.368, ProductVersion 0.2.368** (exe `LastWriteTime 2026-10-30 10:42:52`); registry
`DisplayVersion 0.2.368`. `desktop-latest` (read-only `gh release view`) is **Jarvis Desktop 0.2.368
from commit `bd30231` on main**, i.e. the installed app is the published 0.2.368 build.

**What happened.**

1. At 18:44 PDT the desktop app was **not running** (`Get-Process jarvis*` → none); the Python
   backend was running and listening (`python` pid 48324 on `127.0.0.1:4719` and
   `100.75.21.228:4719`, from `netstat -ano`).
2. Five launch attempts all failed with the **same hard crash**: three direct `Start-Process`
   attempts, once via the Desktop `.lnk` shortcut, and once through the `Shell.Application` COM
   server (`ShellExecute`). Each produced a Windows `Application Error` id 1000:
   `Faulting application name: jarvis-desktop.exe, version: 0.2.368.0 … Exception code: 0xc0000409
   … Fault offset: 0x000000000073fbc5` (BEX64 fail-fast). Five events between **18:45:28 and
   18:49:21 PDT**, recorded in `pass5\desktop-calendar-ui-evidence.txt`.
3. The app's own log (`C:\Users\pcadmin\AppData\Local\com.jarvis.desktop\logs\jarvis-desktop.log`,
   UTC timestamps) shows **no new "===== Jarvis Desktop 0.2.0 starting =====" line for any of the
   five attempts** — the process dies before its logger initialises. Its last successful start was
   `00:57:49Z` (= **17:57:49 PDT**, `HUD window created for http://127.0.0.1:4719`, backend pid
   48324), so **the installed 0.2.368 build does run on this PC in a normal desktop session** — it
   is not universally broken, and the 17:57 backend it spawned is still alive.
4. The documented harness was run exactly as documented and refused:
   `scripts/fieldtest-desktop.ps1 -Windows` → **`EXCEPTION: jarvis-desktop is not running`**
   (`pass5\uia-windows-attempt.txt`; the harness was extracted from `origin/main` `263ea0d86` into
   `pass5\fieldtest-desktop.ps1`). **With no HUD window there is no UI Automation element to attach
   to, so no Calendar tree could be dumped.**

**Control tests — is it the app, or this session?** From this agent session:

| test | result |
|---|---|
| `cmd.exe /c exit 7` (console child) | ran, `ExitCode=7` — child processes work normally |
| `notepad.exe` (modern GUI app) | `HasExited=True ExitCode=-1073740791 (0xC0000409)` — **the same fail-fast code as Jarvis** |
| `control.exe` (classic Win32 GUI) | ran, but **`MainWindowTitle` empty — no interactive window** |
| `charmap.exe` | exited 0 |

So **this agent session cannot host a normal interactive GUI application** (no window title on the
control test; modern GUI apps fail-fast with 0xC0000409). The Jarvis app's startup crash **cannot be
attributed to the app alone from this session**, and it must not be written up as a product defect.

**Row 71 status: PARTIAL.** The desktop Calendar view was **not opened and not read**, so its
desktop half is not driven. The exact reason is that Windows UI Automation has no window to attach
to, because the installed desktop app cannot be launched from this agent session (0xC0000409/BEX64;
five WER events; harness output *"jarvis-desktop is not running"*). The phone + PC-API half already
recorded today is unchanged. **What would finish it:** from a session with a real interactive
desktop (or with the owner leaving the app open), run the documented harness —
`pwsh -File pass5\fieldtest-desktop.ps1 -Windows`, then `-List`/`-Text`, open the rail door
`#rail-calendar-open` (accessible name **"Calendar: your own events, kept on this PC"**; the rail
card's own button is `#cal-open`, "Open calendar"), and read the panel title **"Calendar"**, the
period line, the **Month/Week/Day** tabs, and the side list **"Today"** plus any events (today's
"Field test" event was deleted, so an empty day is expected). That is one click plus one read.

**For the later F6 update run (read-only note, no token).** **Jarvis backend IS running** —
`python` pid 48324, listening on `127.0.0.1:4719` and `100.75.21.228:4719`. **The desktop app is NOT
running** (all launch attempts from this session crash as above; it was last started successfully at
17:57:49 PDT). **The phone `f0a5b32b` is connected** (`adb devices` → `f0a5b32b device`); it was
shown `Connected` in the app at 18:20 and the Devices page lists `OnePlus (this phone) · paired
10 Oct`, and `C:\Users\pcadmin\.openjarvis\devices\registry.json` was last written 18:48:32 — i.e.
paired and talking to the backend. Nothing was approved, changed, installed or pushed in this pass.

**Raw evidence in `pass5\`**: `desktop-calendar-ui-evidence.txt` (build, launch attempts, five WER
1000 events with signatures, app-log tail, control tests, backend/phone state),
`uia-windows-attempt.txt` (documented harness output), `fieldtest-desktop.ps1` (the harness,
extracted from `origin/main`).

**Disclosed side effect.** One `explorer.exe` instance was started at 18:46:43 PDT by the
shell-mediated launch attempt; it was left running deliberately so as not to disturb the desktop
shell. No other test process remains (`notepad`, `charmap` and `control` were closed after their
diagnostic; `jarvis-desktop` never stayed up). No file, setting or data was changed by this pass.

---

## AUDIT pass 6 — 2026-10-30 19:46–19:52 PDT (three matrix rows settled: 83, 84, and row 53's missing half)

**Method / discovery.** The Settings screen's own **`SEARCH SETTINGS`** field is the reliable route to
settings the `JUMP TO:` grid omits: tapping the field and typing a word filters the page (measured
this pass). That is what found **Quick Settings tiles** and **Screen refresh rate**, both recorded
"no on-screen row found on the phone" in the pass-3 batch. Phone UI only (`adb` uiautomator dumps +
taps), **no token, no approval, no PC write**; every changed setting was restored and re-dumped. Phone
left on the launcher, connected (`f0a5b32b device`), version 0.2.3261 unchanged, at 19:50 PDT.

**Row 83 `phone-tiles` — PASS (operated, state changed, restored).**
Settings → `SEARCH SETTINGS` → typed `tiles` → `1 setting matches.` → **QUICK SETTINGS TILES** section
opened with its description (*"Up to three Jarvis tiles for the panel you pull down from the top of
the screen…"*) and `Tile 1 - 10-min timer` plus its choices `Nothing / Focus session / 10-min timer /
Stop everything / Play/pause PC`. Tapped **`Focus session`** → the heading became **`Tile 1 - Focus
session`** and the selected state moved (the selected chip is the non-clickable one). Tapped
**`10-min timer`** → heading back to **`Tile 1 - 10-min timer`**, selected state restored.
Dumps: `pass6/p6-search-tiles.xml`, `p6-tiles-changed.xml`, `p6-tiles-restored.xml`.

**Row 84 `phone-screen-rate` — PASS (operated, readout changed, restored).**
Search `refresh` → `1 setting matches.` → **SCREEN REFRESH RATE**: explanation *"While Jarvis is on
screen, Jarvis asks the screen for this rate. It cannot change your phone's own display setting…"*,
`Now: the phone decides.`, choices `Follow the phone / 60 Hz · now / 90 Hz / 120 Hz`, plus
`This screen offers 60, 90, 120 Hz.`, the battery note, and the note that this is **not** the animal's
frame rate. Tapped **`90 Hz`** → readout became **`Now: asking for 90 Hz.`** (the effect was observed,
not just the control). Tapped **`Follow the phone`** → **`Now: the phone decides.`** restored.
Dumps: `p6-search-refresh.xml`, `p6-rate-changed.xml`, `p6-rate-restored.xml`.

**Row 53 `tutorials` — upgraded PARTIAL → PASS (its missing half now reached).**
Brain → `Jarvis on your PC` → **TUTORIALS** plate (read-only): **`You have met 0 of the 36 lessons
here. 36 to go.`**, `ON THIS PC`, and the lesson rows `What Jarvis is`, `Talking to it`,
`What asks first`, `What Jarvis remembers`, `Records, history and what is kept`,
`When something is wrong` with `Not started` / `Start again`. The FAQ half (FAQ index + a full answer)
was already read in pass 3, so both halves have now been seen. Dump: `pass6/p6-onpc-scroll3.xml`
(plus `p6-onpc*.xml` for the section path). Nothing was started — starting a lesson writes progress.

**Incidental re-read (no status change):** the same section path re-displayed the MODEL, HARDWARE /
FOCUS PRESETS and ATTENTION BUDGET plates, consistent with rows 95/103/104 and 24 already recorded.

**Restoration proof.** Tile 1 back to `10-min timer` and the refresh rate back to `Follow the phone`
(exact pre-test readouts and selected chips), nothing else touched; no approval card was raised; no
token was read; phone left on the launcher.

**Deliverable:** `.dsh-scratch/AUDIT-2026-10-30/TESTABLE-NOW.md` — the claims that could be settled now
(drivable phone / drivable live-backend read-only / not drivable by an agent), with this pass's three
settlements marked. Raw dumps: `pass6/p6-*.xml` (20 files).

---

## AUDIT pass 7 — 2026-10-30 19:57–20:05 PDT (the remaining drivable-now items settled)

**Method.** Phone UI only via `adb` (uiautomator dumps + taps). Two routes: the phone's own
**Help → Find anything** search (a *place* index — it lists places and takes you to them) and
**Settings → SEARCH SETTINGS** (the pass-6 discovery). **Read-only:** no setting was changed this pass
(the pass-6 reversible changes were restored there), no approval card, no token, no live API call, no
install. Phone left on the launcher, connected (`f0a5b32b device`), 0.2.3261 unchanged, at 20:04 PDT.

**`Find anything` method check — PASS, with its limits measured.** Help → `Find anything` opened
(`85 things Jarvis can do`, grouped: Brain → Study, Goals and projects, Graphics cards, …). Typing
`compute` → `1 match` → tapping the result landed **exactly on the COMPUTE plate** (not at the top of
the Brain), so "Find searches every screen and takes you there" holds for places. Measured gaps:
`update`, `shortcuts`, `stop everything` → **`Nothing matches that.`**; `background jobs` DOES find
the place but tapping it lands at the Brain top because the plate is not drawn (row 102 below).
Dumps: `pass7/p7-find.xml`, `p7-find-compute.xml`, `p7-compute-plate.xml`, `p7-find-jobs.xml`,
`p7-find-shortcuts.xml`, `p7-find-stopevery.xml`, `p7-search-update.xml`.

| # | item | status | what was measured |
|---|---|---|---|
| 96 | Compute plate | **PASS** | Find → `compute` → landed on **COMPUTE**: `Text model local`, `Text on cuda:1`, `Vision resident false`, `Tts resident false`, `Simulated false`, `Prefer speed`, `Devices 2`, `Total mb 20480`, the speed line naming the RTX 2080 SUPER and the second card, and `AUDIT CHAIN Available true` with `ledger.db`/`ledger.key` paths. Read-only readout of the plate (no control to operate). |
| 97 | Skills plate | **PASS** | Find → `skills` → landed on **SKILLS**: `Installed, with what the safety scanner said about each.` / `No skills installed, or the scanner has quarantined them all.` The empty state is the readout; reading it is the operation. |
| 109 | What this backend supports | **PASS** | Find → `backend supports` → landed on **THIS BACKEND**: `Server jarvis-hud`, `API 1`, the `CAPABILITIES` list (appearance, approvals, lockdown, memory, models, owner_check, pairing, persona, power, private_chat, retrieve_count, skills, stop_all, temporary_chat, think_per_question, voice, voiceprint) and a `NOT ON THIS BACKEND` list starting with `connectors`. |
| 115 | Undo ("How long you can undo") | **PARTIAL** | Find → `undo` → Settings **LIMITS AND HOW OFTEN JARVIS DOES THINGS**: `How long you can undo` / `keep undo for a day`; choices `1 hours` / `24 hours (in use)` / `168 hours`. **Write not made:** changing the undo window is a PC-asking write (the row says turning it up asks on the PC); the undo *action* itself was not exercised. |
| 117 | Limits and frequency | **PARTIAL** | Same screen holds `How long an approval card waits` (`300 seconds` / `900 seconds (in use)`) plus *"These are the PC's own settings, in the PC's own words."* and *"Changing something here may take effect at once or ask you on the PC first"*. Read; no limit changed (the write is named above). |
| 94 | Keyboard shortcuts (PC-only refusal) | **NOT-REACHABLE** | Settings → SEARCH SETTINGS → `shortcuts` → **`Nothing here matches "shortcuts".`**; Find → `shortcuts` → `Nothing matches that.`. The refusal exists only as the feature directory's own row (`FeatureDirectory.kt:137`, "PC-Only Setting (Honest Refusal on Phone)"), not as a phone screen. Exact reason recorded; not claimed as a pass. |
| 102 | Background jobs list | **NOT-REACHABLE now** | Find DOES list the place (`Background jobs — Long jobs Jarvis is running.`) but tapping it lands at the Brain top with no plate; opening Brain → `What Jarvis is doing` manually shows **no node containing "background" or "jobs"** (81 nodes in the opened section). The plate is keyed in that section with the note *"drawn only when there are background jobs"* (`BrainSections.kt:259`) and the queue is empty — nothing to read until a job exists. |
| 106 | Updates | **NOT-REACHABLE on this build via the two routes** | Settings search `version` → `Nothing here matches "version".`; Find `update` → `Nothing matches that.`. The record's own directory says the phone surface is *"Check for new versions" on Platform checks, under This app* (`FeatureDirectory.kt:150`) — that screen is not in Settings, and its route was not located this pass. Not claimed. |
| 107 | Check for tool updates | **NOT-REACHABLE** | Settings search `tool` matched only **WHAT JARVIS CAN REACH** (whose text mentions tool updates); no `Check for tool updates` row appears. The directory marks it PC-only on the phone (`FeatureDirectory.kt:151`), so there is no phone control to drive. |
| 123 | Stop everything | **PARTIAL** | A **quick-tile action**, not a screen: `QuickTiles.kt:68` (`STOP_EVERYTHING("stop_everything", "Stop everything", …)`), and it appears as a selectable choice in the QUICK SETTINGS TILES section read in pass 6 (`pass6/p6-search-tiles.xml`). The run-time Home button is drawn only when something is running; operating it would be a state write, so it was not tapped. Find → `stop everything` → `Nothing matches that.`. |

**States changed:** none — this pass only read (navigation + dumps). No approval card, no token, no
live API, no install.

**Ledger update (one line):** rows 96/97/109 → **PASS**, rows 115/117/123 → **PARTIAL** (write named),
rows 94/102/106/107 → **NOT-REACHABLE with exact reasons**; Find-anything method → **PASS**; the
"still drivable now without the owner" phone list from `TESTABLE-NOW.md` is now **empty** — what remains
there is owner-gated, GUI-gated, hardware/account-gated, or blocked on the Final-1 releases.
Raw dumps: `pass7/p7-*.xml` (31 files).
