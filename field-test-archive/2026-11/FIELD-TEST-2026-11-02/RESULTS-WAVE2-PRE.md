# FIELD TEST — WAVE 2 PRE-CHECK (phone lane), 2026-11-02

Build under test: **com.jarvis.client 0.2.3552** (`versionCode=1000003552`), the CI build
from merged `main` 4bcd062. Device: OnePlus CPH2419, `adb` serial `f0a5b32b`.

Method: every phone row comes from `adb shell uiautomator dump` + pull, parsed for text and
bounds (screenshots are black under FLAG_SECURE and were not used). No card was approved, no
app was installed or uninstalled, the pairing token was never read or printed. The one setting
flipped for a test (face size) was recorded first and restored, and the restore was verified
from the widget's own checked state.

Two cross-cutting facts are recorded in "Incidents" and must be read before trusting any row:
a **second adb client was driving this same phone** throughout, and **one of my taps snoozed
the owner's timer**.

---

## 1. #1098 — "Show chat and then back to full screen does not show the chat properly"

**Verdict: PASS** for the driven Full-screen path. Second path (answer menu): **NOT-TESTABLE**
(the menu carries no "Show chat" — see 1d).

Original face size recorded before touching anything: **Hidden**
(`[549,2026][990,2170] checked=true`, other four radios `checked=false`).
It was set to **Full screen** (`[90,1864][378,2008] checked=true`) for the test and put back to
**Hidden** afterwards (`[549,2026][990,2170] checked=true`, Full screen `checked=false`).

The setting is not findable by search: Settings search `full screen` →
`Nothing here matches “full screen”.` It lives at
Settings → Appearance → **HOME** → `Face size on Home`, with options
`Full screen` / `Extra large` / `Large` / `Medium` / `Hidden` and the note
`Full screen is for talking: just Jarvis and the microphone. Hidden gives the chat the whole screen. The two biggest sizes use more battery.`

To make "lands on the newest" a real check (not trivially true), two exchanges were created
first, through the full-screen typing box, and each answer is unmistakable:

| # | drove | verdict | exact evidence |
|---|---|---|---|
| setup | typed `Reply with exactly BLUE LANTERN 4291` into the full-screen typing box `[666,565][870,2382]` and pressed Enter → answered `BLUE LANTERN 4291`. Then typed `Say only ALPHA` into the chat composer `[255,2245][588,2389]` — Enter there inserts a newline, so it was sent with the `Send` button `[714,556][822,609]` → answered `ALPHA` | PASS | two exchanges exist and the newest answer is unmistakable: `Your next question follows on from the last 2.`, and the face itself shows `ALPHA` `[36,494][1044,547]` |
| 1a | tap `Show chat` (`[66,1451][254,1497]`) from the face | PASS — lands on newest | visible chat rows, top to bottom: `YOU` `[90,1138]` / `Say only ALPHA` `[90,1186][424,1305]`, then `JARVIS` `[90,1394]` / `ALPHA` `[90,1503][259,1562]`, `Used 1 memory`, `Copy`, `Share`, `It's on your screen.`, `Your next question follows on from the last 2.`, `New chat` `[120,1986][289,2032]`, `Back to full screen` `[684,2113][1014,2159]`. The **older** exchange (`Reply with exactly BLUE LANTERN 4291` / `BLUE LANTERN 4291`) is **absent from the dump** — i.e. scrolled out above, so the list is sitting at its end |
| 1b | tap `Back to full screen` (`[684,2113][1014,2159]`) | PASS — face restored | back on the full-screen face: `Show chat` `[66,1451][254,1497]`, `More`, mic, `Type a message to Jarvis` `[666,565][870,2382]`, and the last answer `ALPHA` `[36,494][1044,547]` |
| 1c | tap `Show chat` **again** (the #1098 regression step) | PASS — same as first open | identical dump to 1a: `Say only ALPHA` at `[90,1186][424,1305]`, `ALPHA` at `[90,1503][259,1562]`, `Used 1 memory`, `Copy`/`Share`, `It's on your screen.`, `Your next question follows on from the last 2.`, `New chat`, `Back to full screen`. Older exchange still out of view. **Nothing missing, blank or doubled.** |
| 1d | answer menu on the newest answer (tap `Message actions for this answer` `[846,1807][990,1951]`) | NOT-TESTABLE — row not present | sheet `This answer` / `One message: a mark, or a pin.` / `Mon 02 Nov, 16:53` / `Was this right?` / `Right` / `Wrong` / `Pin message` / `Kept on this phone. In History, under Pinned.` / `Close`. There is **no `Show chat`** entry in this menu, so the "Show chat under a finished answer" path could not be driven. Not a pass. |

Ceiling on the PASS, stated plainly: the conversation held only **2** exchanges. "Lands on the
newest" is evidenced by the newest exchange being at the top of the visible chat area while the
older one is scrolled out of the dump — not by scrolling a long conversation. I tried to scroll
the chat up to prove the older content exists above; the swipe was **refused twice by the
focus gate** because the other adb client kept taking the screen (see Incidents), so that extra
confirmation was not driven.

---

## 2. Reminders baseline

**Verdict: PASS** (navigation recorded; nothing changed there).

Driven: home nav row → `Reminders` at `[540,368][720,392]`, twice, from two separate launches.

It opens a **subsection of Brain**, exactly as the owner described — screen title `Brain`,
scrolled to the `COMING UP` section:

| element | exact text |
|---|---|
| header | `Brain` `[234,159][392,236]`, controls `Refresh` `[719,384][858,430]`, `Fold` `[921,384][1000,430]` |
| section | `COMING UP` `[48,388][264,427]` |
| intro | `Timers, alarms and reminders, kept on your PC. They go off on both apps while they are connected. A repeating reminder or alarm is set up at once, with no card; a repeating briefing or "tell me when" waits for your yes on an approval card.` |
| | `They go off on your PC. This phone shows them while it is connected to it.` |
| privacy | `Words hidden. Tap Show and confirm it is you.` + `Show` `[860,960][960,1006]` |
| live timer | `Just went off` / `timer` / `(hidden) timer` / `Went off at 16:12` / `Snooze 10 minutes` / `Delete` |
| empty | `Nothing coming up. Say or type "set a timer for 10 minutes" or "remind me at 6 to call Mum".` |
| below | `Tell me when` (long description, with `add "urgently" to make it ring until you look`), `Reminder for next time`, `To-do list` / `Nothing on your to-do list.` |

Anomaly, for honesty: the **first** attempt landed on a screen titled `Platform checks` /
`What this phone will and will not allow` instead. It did not reproduce — the next two attempts
(and the app's own resumed state) both went to `Brain` → `COMING UP`. I believe that first tap
was consumed while the app was mid-transition, but I did not prove it.

---

## 3. Settings search baseline (what this installed build already has)

**Verdict: PASS** (all five strings driven; this is a baseline, so the verdict is "driven and
recorded", not "feature works").

Search field is the `EditText` at `[90,392][990,536]`; hint
`Type a word to show only the settings that match.`

| typed | verdict | exact evidence |
|---|---|---|
| `skills` | driven — **no match** | `Nothing here matches “skills”.` / `Clear the box and everything comes back.` |
| `to-do` | driven — matches the feature directory | `1 setting matches.` then card `ALL FEATURES AND ABILITIES`, `Every feature Jarvis knows about, in the PC's own words. A switch is only shown where the PC really has one - the rest say what they are and where to find them.`, `Search abilities: voice, backup, timer, galaxy...`, `168 features`, `Command-Only (Runs When You Ask — No Switch Needed)`, first row `Type a message and read the answer` |
| `carry-over` | driven — **no match** | `Nothing here matches “carry-over”.` / `Clear the box and everything comes back.` |
| `reworded` | driven — **no match** | `Nothing here matches “reworded”.` / `Clear the box and everything comes back.` |
| `apps on my phone` | driven — **no match** | `Nothing here matches “apps on my phone”.` / `Clear the box and everything comes back.` |

What this proves about build 0.2.3552: there is **no** settings row for skills, to-do
carry-over, memory paraphrase ("reworded"), or the phone app allow-list. In particular the
wave-2 plan's expected "desktop-only refusal naming the PC" for `skills` **does not exist in
this build** — the answer is the generic no-match. Only the feature directory (168 features)
answers `to-do`.

---

## 4. Home screen

**Verdict: PASS** — the home cards are really drawn, so a blank-screen report cannot be
confused with this state.

Evidence (text rows, with bounds): `Connected` `[96,156]`; `History` `[907,168][1038,214]`
(desc `Chat history, kept on your PC`); nav row `Brain` `Inbox` `Live` `Reminders` `Settings`
`Help` at y `368–407`; buttons `The Galaxy →`, `Presets →`, `Model →`;
**`YOUR HOME SCREEN · 30 CARDS`** `[48,656][665,695]` + `Rearrange it in Settings, Home screen`
`[665,656][1032,695]`; section header **`TOP STRIP`** `[48,719][245,758]`; cards
`Waiting for your yes` / `The approvals queue: one card per tap.`,
`Emergency stop` / `Stops everything, at once. Never hidden.`,
`Right now` / `What Jarvis is doing at this moment.`,
`Attention budget` / `How much Jarvis may interrupt you today.`,
`What Jarvis is doing` / `The steps behind the last answer.`

In the owner's normal face size (`Hidden`) the home also carries the chat inline
(`YOU` / `Say only ALPHA` / `JARVIS` / `ALPHA`) and the footer
`Old chats are in History, one tap away. New chat is in More, or under a finished answer.`
There is **no** `Show chat` button in that mode — it only exists on the **Full screen** face.

---

## Incidents — read these before trusting any row above

### I1. A second adb client was driving this phone all session (affects provenance)

`logcat` shows app launches with `mCallingUid=2000` (= adb shell) that I did not issue:

```
16:38:47 START com.jarvis.client/.MainActivity            (before my lane started)
16:49:05 START syncthingfork/OnboardingActivity  act=MAIN cat=LAUNCHER
16:49:29 START syncthingfork/OnboardingActivity  flg=0x10000000 (a bare `am start -n`)
16:52:27 START syncthingfork/OnboardingActivity
```

That client then walked Syncthing's setup forward — it opened Android's
`Settings$AppManageExternalStorageActivity` ("All files access") and
`RequestIgnoreBatteryOptimizations`, and reached Syncthing's `Storage Permission` page
(`Grant permission`) and `Battery Optimization` page, ending on Syncthing's main screen. It also
opened the notification shade on me repeatedly (5+ times between 16:56 and 17:03).

Consequences, all disclosed:
- Four of my dumps were taken with Syncthing in the foreground and are **discarded** as
  evidence of my navigation (files `08`, `10`, `20`, `31` in `w2/`). Every row above is from a
  dump whose `FOCUS:` line reads `com.jarvis.client/com.jarvis.client.MainActivity`.
- I built a focus gate (`w2tap.ps1`) that **refuses to tap unless Jarvis is foreground** and
  does not type unless it still is. It refused 5 times, three of them logged in this file.
- I did **not** press `Continue` or `Grant permission` in Syncthing, and never typed into it.
- Disclosure: early on I pressed `KEYCODE_BACK` on Syncthing's wizard to get my screen back,
  which rewound its pages (Storage Permission → Welcome). I stopped doing that once I saw it
  was someone else's flow, and from then on used the Jarvis launcher intent to take the screen
  instead of touching Syncthing's UI.

This is not the owner's finger — owner taps do not arrive with `mCallingUid=2000`. It is another
automated lane on the same serial. **Two lanes on one phone corrupt each other's evidence.**

### I2. My one unintended state change: the owner's timer was snoozed

The app resumes to its **last screen**, not to Home. After a relaunch it was sitting on
Brain/Reminders, and a tap I aimed from a stale coordinate for `Show chat` (160,1474) actually
landed on that screen's `Snooze 10 minutes` (`[120,1447][459,1493]`).

- Before: `timer` / `(hidden) timer` / `Went off at 16:12`, with `Snooze 10 minutes` · `Delete`.
- After: `timer, snoozed` / `(hidden) timer` / `9:16 left` at 17:01, with `+5 minutes` · `Pause` · `Delete`.
- This is a **PC-side** change, not phone-only: the section's own words are
  `Timers, alarms and reminders, kept on your PC. They go off on both apps while they are connected.`
  so the owner's timer was rescheduled on the PC to ring again at about **17:10**.
- The timer was **not** deleted or paused. When it rings it should return to the
  `Just went off` list. There is no "un-snooze" control, so letting it fire is the closest
  available restoration and I left it rather than destroy the owner's timer.
- **Verified after the fact (17:10):** it rang and settled back by itself. The row now reads
  `Just went off` / `timer, snoozed` / `(hidden) timer` / `Went off at 17:10`, with the normal
  pair of buttons `Snooze 10 minutes` · `Delete` (the `+5 minutes` / `Pause` trio is gone).
  So the timer still exists, is still un-deleted, and is in the same resting state it was in
  before — with one difference I cannot undo: the label carries `snoozed`, and its last ring
  moved from `16:12` to `17:10` (one extra ring, ten minutes late).
- Cause was mine: I tapped a coordinate I had not re-read from a fresh dump. After this, every
  tap was taken from the dump I had just made.

---

## What I could not drive, and why

| item | status | reason |
|---|---|---|
| #1098 answer-menu path ("Show chat" under a finished answer) | NOT-TESTABLE | the menu genuinely has no `Show chat` (evidence in 1d) — nothing to drive |
| #1098 long-conversation scroll proof | NOT driven | the swipe that would prove older turns sit above the fold was refused twice by the focus gate while the other adb client held the screen; the 2-exchange view was used instead |
| #1098 repeated back-and-forth cycles (>1) | NOT driven | one `Back to full screen` round trip only, to limit further contention; the app's setting was then restored |
| any approval path | never attempted | lane rule: no card is ever approved |

## End state of the phone

- Face size restored to the owner's original **Hidden**, confirmed from the radio state.
- theme untouched (`Reactor` `checked=true` before and after).
- Jarvis is foreground on its normal Hidden home screen; the answer sheet was closed.
- No app installed, uninstalled, or updated; no permission granted by me.
- No card created by this lane; the pairing token was never read or printed.
- One residual I caused: the owner's timer carries a ~10-minute snooze (I2). It has since rung
  again at 17:10 and settled back into `Just went off`, un-deleted, so the phone is usable and
  nothing of the owner's was destroyed — but the row keeps the `snoozed` label and its
  last-ring time moved from `16:12` to `17:10`. That difference is mine and cannot be undone
  from the phone.
