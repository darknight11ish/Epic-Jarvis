# How to read the two apps without vision (and when you cannot)

**Written 2026-10-11, from the field-test pass of the same day.** The pass had to read a phone app and
a desktop app and record what each one really says, with **no screenshots and no vision** - there is no
vision provider on this machine. Five ways in were found, four of which had never been written down.
This document is the method; `FIELD-TEST-MATRIX-2026-10-11.md` is what the pass found, and
`FIELD-TEST-2026-10-11-RESULTS.md` is the per-feature record with the raw evidence behind it.

## The one rule

**A screen you cannot read is not a screen you have tested.** Every reading below comes from the app's
own structures - its accessibility tree, its UI Automation tree, the phone's notification record, or the
backend's own state - never from a picture of the screen. And **a feature that could not be reached is
never a pass**: PARTIAL and BLOCKED are the honest verdicts, and they are written as such.

## The five ways in

### 1. The phone's own accessibility tree - `adb shell uiautomator dump`

The phone app hands Android its whole screen as text. `uiautomator dump` writes it to the device;
pull it and read the `text="..."` values and the `bounds="[x,y][x,y]"` of each node, and you can both
read a screen and tap a real control by its own rectangle.

* **Works:** every screen whose words are real text - which is nearly all of them (`uiautomator`
  reported whole screens: `ATTENTION BUDGET`, `SHOW OR HIDE MENUS`, `WHAT ASKS FIRST`, and so on).
* **Does not work:** anything **drawn rather than laid out**. The clearest case is the **face picker**
  on the Appearance screen: it is a picture, so `uiautomator` sees no labels for it at all, and with no
  vision provider here the picker cannot be read by a machine. `faces` is PARTIAL for exactly this
  reason.
* **Script:** `scripts/fieldtest-phone.ps1` (the pass called it `phone-lookup.ps1`). Give it
  `term|expected row|tag` targets; it goes Home, opens Find, searches, taps the row whose text starts
  with the expected string, then dumps and prints the screen it landed on. Every step is verified: a
  step that fails says it failed rather than reporting a screen it never reached.

### 2. The desktop's page over Windows UI Automation - `UIAutomationClient`

The desktop app is a Tauri/WebView2 window, and **WebView2 exposes its whole page to UI Automation**.
That single fact is what makes the desktop half testable at all: the app's real text and its real
controls are both reachable, by name or by `AutomationId`.

* **Works:** reading, and driving. The Settings window alone exposed **2,067 strings**; a control can be
  found by name (exact, then prefix, then contains - a settings row's accessible name is often its label
  *and* its one-line description joined together) or by `AutomationId`, and clicked through its own
  `Invoke`, `Toggle` or `SelectionItem` pattern.
* **Does not work:** the **tray icon**. Jarvis's tray icon sits inside the "Show Hidden Icons" overflow
  and produces **no readable menu**, so the **desktop Brain window could not be opened from a harness at
  all** - which is why `work-tab` is the one BLOCKED feature that a person at the machine reaches in two
  clicks. Three scripts tried (`tray.ps1`, `tray-open.ps1`, `tray-menu.ps1`); it is a dead end, not a
  missing flag.
* **Script:** `scripts/fieldtest-desktop.ps1` (the pass called it `desktop.ps1`):
  `-Windows` lists the app's top-level windows, `-List` every readable element, `-Text` just the text in
  order, `-Click '<name>'` or `-Click -Id '<id>'` drives one control, and `-Window`/`-Nth` choose which
  window (the app can have **two** windows called `Jarvis`: the HUD and the quickbar).

### 3. The phone's notification record - `adb shell dumpsys notification --noredact`

Some features are actions, not screens ("ring my phone"). Asking is the honest test - but the model's
own answer is not evidence that anything happened. **The phone's notification record is.** It is how
"ring my phone" was *proved*: the app's notification was there, in the phone's own words
(`title = "Jarvis is ringing this phone"`, `channel = jarvis_alarm`), not merely claimed.

* **Works:** proving that a notification was really posted - which is the whole of "ring my phone",
  "tell me when", and the alarm/reminder path.
* **Does not work:** it proves the *notification*, not the *effect*. That the phone actually rang, or
  that the owner heard it, is beyond this method.
* **Script:** none needed - it is one `adb` line. The **asking** side was `phone-ask.ps1`, which types
  into the phone's own chat box and records what comes back.

### 4. The backend's own state - `GET /api/screen` and friends

The PC's backend keeps the truth about what it is doing, and it answers over its own API. Reading it is
what **corrected a wrong field-test write-up**: the watching badge looked unstoppable, until the backend
said

```
GET /api/screen -> HTTP 200
{"state":"ended","on":false,"paused":null,"left_s":null,
 "ended":"owner","ended_words":"you stopped it", ...}
```

and `ended:"owner"` is the string the backend's `ENGINE.stop()` writes. The session **was** stopped; what
was broken was the **badge**, which stayed on screen with a falling countdown. Read the backend before
believing the UI.

* **Works:** any question about real state - is a session on, was it ended, by whom, what is left.
* **Does not work:** it says nothing about what is *drawn*. A correct backend and a lying screen can both
  be true at once, and that difference is exactly what this method is for.
* **Never print the pairing token.** Read it from the backend's own file at run time, send it, and keep
  it out of anything written down - the same rule the app itself follows.

### 5. Real input, not synthetic - `SetCursorPos` + `mouse_event`, and real key combinations

UI Automation's `Invoke`/`Toggle` is the first thing to try and is usually enough. **It is not always
enough**, so the pass kept three tools that go through Windows' real input path: a real mouse event at an
element's own bounding rectangle (`click-real.ps1`: `SetCursorPos` then `mouse_event` down/up), a real key
combination (`send-hotkey.ps1`), and a real click followed by real keystrokes (`type-into.ps1`).

* **Works:** controls that ignore the programmatic patterns, and anything that needs a genuine key or
  pointer event (global hotkeys, typing into a field).
* **Does not work:** real input is not proof of an effect either - it only proves the input was sent.
  Confirm the effect by method 4 (or 3), never by the click alone.
* **One correction to keep:** the comments in `click-real.ps1` and `send-hotkey.ps1` say the badge's Stop
  button "did not" end a watching session. The backend's own state (method 4) later disproved that. The
  technique is what is worth keeping; that claim is not.

## The harnesses, and where they live

`.dsh-scratch/` is **gitignored**, so nothing in that folder is tracked and a clean-up would lose it.
Two of the harnesses are general-purpose readers, so they are now in the repo under `scripts/`; the rest
are one-off tools for one problem each and are described here instead.

| script | what it is for | in the repo |
|---|---|---|
| `fieldtest-phone.ps1` (was `phone-lookup.ps1`) | general-purpose phone reader: search a term, tap the row, dump the screen | **yes** - `scripts/` |
| `fieldtest-desktop.ps1` (was `desktop.ps1`) | general-purpose desktop reader/driver: `-List`, `-Text`, `-Click`, `-Id`, `-Window`, `-Nth` | **yes** - `scripts/` |
| `phone-ask.ps1` | ask a question in the phone's own chat box and record the answer | no - one-off |
| `click-real.ps1` | a real mouse click at an element's rectangle | no - one-off |
| `send-hotkey.ps1` | a real key combination (e.g. `Alt+Shift+X`) | no - one-off |
| `type-into.ps1` | a real click, then real keystrokes | no - one-off |
| `tray.ps1`, `tray-open.ps1`, `tray-menu.ps1` | reach the tray icon and read its menu - **the dead end in method 2** | no - the route failed |
| `settings-desktop.txt` | a dump of the 2,067 strings the Settings window exposes | no - it is output, not a tool |

If the one-offs are ever wanted back, they are in `.dsh-scratch/fieldtest-2026-10-11/` until that folder
is cleaned. `scripts/` is where this repository keeps PowerShell that is run by hand on the owner's PC
(`apply-patches.ps1`, `update-jarvis.ps1`, `measure-cards.ps1` and the rest), which is why the two
readers went there and not into `tools/` (that folder holds the Python checkers CI runs).

## The provenance, so a number can be re-checked

* `FIELD-TEST-MATRIX-2026-10-11.md` - **the verdicts**: what each feature did, and the second pass's
  corrections.
* `FIELD-TEST-2026-10-11-RESULTS.md` - **the record**: per feature, the verdict and the raw evidence it
  came from, copied into the repo on 2026-10-11 from the untracked folder so the evidence behind the
  matrix's numbers survives it. One row was corrected after it was written; the note at the top of that
  file says which and why.

## The checklist for next time

1. Put real input in front of the app being read - a phone screen the app is showing, a window that is
   not minimised - and drive **one process at a time**.
2. Read with method 1 on the phone and method 2 on the desktop. Read, do not guess.
3. When the UI says something happened, confirm it with method 3 (notifications) or method 4 (the
   backend's own state) before writing it down.
4. If a control ignores `Invoke`, try method 5 - and still confirm the effect with method 3 or 4.
5. Write down what could **not** be reached and why. "Drawn, not text" and "no readable menu" are
   findings; "assumed working" is not.
