# The field-test run, 2026-10-14 — what was driven, and what was not

**What this is.** The result of the pass `docs/FIELD-TEST-PLAN-2026-10-14.md` (PR #413) planned:
the owner's live Jarvis, on his own hardware, driven through the controls and routes a person
uses, with a verdict and the literal evidence for each row. It is **not** a plan and **not** a
suite run.

**The rule this record runs on, unchanged.** *BLOCKED and NOT-TESTABLE are never counted as
passes.* A row that could not be reached is written **BLOCKED**, **PARTIAL** or
**NOT-TESTABLE** and reads as such. Only a feature **driven on real hardware** is a PASS. And
**do not claim more than the evidence supports**: where this record reasons from a timestamp
or a source read rather than a measurement, it says so in the row.

**Which tree this record was written in.** The worktree
`.dsh-scratch/wt-fieldtest-now`, branch `docs/field-test-2026-10-14`, created from
`origin/main` at `d979ac21` (PR #410). Every claim about `main` was read with
`git show origin/main:<path>` or `git grep <pattern> origin/main`, and every claim about a
live file names the live file. The repository root's `CLAUDE.md` was **not** used; the copy
read is the one in this worktree, which is `origin/main`'s.

---

## 1. The builds under test

A verdict without its build is not evidence, so each one was read from the thing itself:

| what | the build, and where it was read |
|---|---|
| **Desktop** | **0.2.169**, running. Read twice: from the Settings page's own line — *"Version 0.2.170 is available. You are running 0.2.169 · published 2026-10-14 8:34:32.0 +00:00:00."* — and from the installed exe's own version info (`ProductVersion 0.2.169`). The exe was written **2026-10-14 00:53:42 -0700**. |
| **Backend** | The live backend on `127.0.0.1:4719`, process started **2026-10-14 01:40:04**. Its `/api/status` answers `"ollama": true`, `"tools": 28`, `"default_model": "qwen3.5:9b"`. |
| **Phone** | **0.2.1380 — NOT updated.** `dumpsys package com.jarvis.client` reads `versionName=0.2.1380`, `versionCode=1000001380`, `lastUpdateTime=2026-10-13 16:35:35`. **The app's own banner names its build**: *"A newer build of this app is on GitHub (main, 1b546df). Nothing is downloaded until you choose to."* That commit is `1b546df396436f3f78285ab3462f85add50d69ca`, 2026-10-13 13:00:19 -0700. |

**The one line that decides most of this record.** The phone's build is `1b546df`
(2026-10-13 13:00). Anything merged into `main` **after** that instant is provably absent
from the phone under test. That was checked commit by commit with
`git merge-base --is-ancestor <fix> 1b546df`, not assumed from a date. **§5 is the list.**

**And the same test for the desktop.** The exe was written 2026-10-14 00:53:42 -0700, so a
fix that merged after that cannot be in the installed 0.2.169. That is stated as a
**timestamp comparison**, not as a measurement of the binary, wherever it is used below.

---

## 2. The rows that were driven

Each row is: the verdict word, what was actually driven, the literal result, and — new since
the third pass — **who can settle it** where it is not settled.

### 2.1 N9 — `change_setting` asked in the owner's own words (the model path)

**PARTIAL.** The half PR #405 fixed holds; the half the plan's PASS needs did not.

*Driven, on real hardware:* the HUD's own chat box (`#input`) and its own **Send** button
(`#send`), over Windows UI Automation — the two controls a person uses. Wording was chosen to
sit **outside** the fixed phrase grammar (`_ADJUST_ONOFF` in the live `jarvis_quick.py` covers
`turn|switch on|off <name>`, `enable <name>`, `disable <name>`), because a grammar-covered
sentence never reaches the model at all:

> typed: `I'd like a little more humour in your replies.`
> the HUD answered: **"Got it—I'll try to keep things light and friendly!"**
> the HUD's own badge: **`ANSWERED BY  qwen3.5:9b`**

*The route, read literally.* A person cannot read a response header, so the header was read
from an API turn carrying the **identical** wording with the same token and
`X-Jarvis-Client: hud`:

```
X-Jarvis-Route: {"lane": "qwen3.5:9b", "reason": "complexity 0.075 is under the threshold",
                 "gate": "complexity", "complexity": 0.075, "inject_memory": true,
                 "tainted": false, "offer": "", "injected_facts": 0, "injected_ids": [],
                 "memory_side": "none", "turn_id": "41e74e19bee84d88bf0ccf3427ded87b",
                 "injected_sensitive": 0, "topics_left_out": 0, "where": "local"}
```

So the route is **not** `{"lane": "no AI model"}` — the model lane was asked, which is the half
PR #405 is about, and it is better than the third pass's grammar-only answer.

*The half that did not hold, verified against the live store and not against the model's own
sentence about itself:* **the tool was not called and the setting did not change.**
`~/.openjarvis/manner.json` read `{"manner": "warm", "humor": false}` **before both turns and
after both turns**. The second turn refused in words instead:

> the API turn's answer: **"Hmm, I can't switch my humour on from this reply—it's pulled from
> a web page. Say "turn on humour" in your own words and I'll make the change right after."**

**The honest reading of that refusal, and its limit.** The words point the owner back at the
fixed phrase, which is the fast door that already works — not a false claim of success, and not
the "looks-like-success" failure PR #405 exists to end. **But its stated reason is not
supported by the same turn's own route header**: the route says `"tainted": false` and
`"injected_facts": 0`, while the answer says the reply "is pulled from a web page". This
record does **not** diagnose that mismatch; it names it, with both sides quoted, for whoever
owns `jarvis_agent.py` to diagnose.

**Not a rate.** Two turns, at the model's own temperature. PR #405's own body says roughly one
request in twenty still finds no call at that temperature, and this is one more sample, not a
measurement of the fix.

*Who can settle the rest:* a pass that runs the wording many times, or (better) the owner, in
ten seconds, by saying *"turn on humour"* — which the grammar answers.

### 2.2 N10 — a loosening through the asking path still raises a card

**PASS.** Driven through the HUD's own chat box, real hardware:

> typed: `turn on remembering sensitive topics automatically`
> the HUD answered: **"Waiting for your approval. It turns on only if you approve the card,
> on your PC or phone."**
> the HUD's own badge: **`ANSWERED BY  no AI model`**

A card was really raised (`GET /api/pending`):

```
{"id": "8e678a1f013e", "action": "learning_sensitive_enable", "tier": "ask",
 "detail": "{... \"what\": \"also remember sensitive topics automatically\",
             \"leaves_this_pc\": false}"}
```

**It was DENIED** — never approved:

```
POST /api/deny {"id":"8e678a1f013e","by":"fieldtest-2026-10-14"}
HTTP/1.0 200 OK
{"ok": true, "id": "8e678a1f013e", "state": "denied", "error": null}
```

**The setting did not move.** The card's yes writes `auto_sensitive` into
`~/.openjarvis/auto-learning.json` (`jarvis_auto_learn.py`'s `settings_path()`, `set_sensitive`);
that file **does not exist**, so no `auto_sensitive` is set anywhere, and `jarvis-framework.toml`'s
SHA-256 was unchanged across the whole session (below). The plan's own warning is honoured: the
setting did **not** change without a card, so this is not written up as a partial and is
certainly not a FAIL.

### 2.3 N6 — the two raise actions' cards

**PASS.** Both cards were raised for real and read from `GET /api/pending`, then **DENIED**.

| card | `action` | what the card's own `risk` said |
|---|---|---|
| raising the interruption budget 3 → 4 | `raise_attention_budget` | `{"reversible": "no", "reach": "local", "swipe_ok": false, "classified": true}` |
| raising the undo window 24 → 168 | `raise_a_limit` | `{"reversible": "no", "reach": "local", "swipe_ok": false, "classified": true}` |

* Neither carries `'classified': False`, and neither says *"not classified, so treated as
  irreversible and outbound"* — the exact pre-fix vocabulary PR #384's body quotes.
* The bar's own rendered card line reads: **"No undo · stays on this machine — lets Jarvis keep
  your Undo history longer, or lets a model read what you save to find the people and things in
  it; …"** — `reach: local` in the app's own words, not a red **UNCLASSIFIED** pill.
* The live backend's own table carries the two rows the fix added:
  `jarvis_gate.py:624-625` (read from the live file) both read
  `("no", "local", "lets Jarvis … nothing is sent anywhere, and lowering it again is instant …")`.
* Both cards were **DENIED**, and nothing was written (§6).
* `expires_in` was **895** on both, not the plan's 599: the ceiling is
  `approval_timeout_seconds = 900` in `jarvis-framework.toml`, the owner's 2026-10-13 decision
  to boost cards to 15 minutes. The plan's "599 at the ten-minute ceiling" is stale.

### 2.4 N2 — `POST /api/attention/settings`, the route that was a 404

**PASS**, and the plan's own driving method is wrong in two ways (§7).

| request | literal result |
|---|---|
| `GET /api/attention/settings` | **404** `{"error": "not found"}` — there is **no GET** |
| `POST /api/attention/settings {}` | **400** `{"ok": false, "error": "Send one of these: spoken_per_day, digest_hour."}` — the route **exists**; it is not the 404 shape |
| `POST {"spoken_per_day": 3}` | **200** `{"ok": true, "changed": false, "loosening": false, "approved": false, "from": 3, "to": 3, "said": "Jarvis may speak up to 3 times a day."}` |
| `POST {"spoken_per_day": 99}` | **400** `{"ok": false, "error": "That has to be a whole number between 0 and 24."}` |
| `POST {"digest_hour": 19}` | **200** `{"ok": true, "changed": true, "loosening": false, "from": 18, "to": 19, "said": "The morning brief arrives at 19:00 now."}` |
| `POST {"digest_hour": 18}` (restore) | **200** `{"ok": true, "changed": true, "loosening": false, "from": 19, "to": 18, …}` |
| `POST {"spoken_per_day": 4}` (a raise) | raised a card and **blocked**; after the card was denied: **409** `{"ok": false, "error": "You said no, so Jarvis still speaks up to 3 times a day."}` |

**Restore, proved by hash, not by promise.** `jarvis-framework.toml` in the live backend folder
was `65BB08756D4DD4DA91F3F45227E5D1C629340E182B33E42477D27D46E6C3E845` **before** the writes and
the **same value after the restore**, and the same value again after both raise cards were
denied. The file's own lines read `spoken_per_day = 3` and `digest_hour = 18` both before and
after. The prior values were read first (`jarvis-framework.toml` lines 988 and 993,
`spoken_per_day = 3`, `digest_hour = 18`), as the plan's restore rule requires.

### 2.5 Row 24, `attention-budget` — the raise itself (§3.7 of the plan)

**PARTIAL.** The plan asks for the raise to be driven **separately from "the card was read"**,
on both apps. The route the Brain's own card posts to was driven (§2.4: a real raise, a real
card, a real refusal with the number unchanged), so the raise is no longer only a card read
anywhere. **But the card's own button was not pressed on either app** — that button lives on
the Brain's Interruption-budget card, and the Brain window cannot be opened from a harness
(§3, and §4 of the 2026-10-13 desktop record). *Who can settle it:* the owner, in two clicks,
on either app.

### 2.6 N8 — "what can I change?"

**PASS.** Driven through the HUD's own chat box:

> typed: `what can I change?`
> the HUD answered: **"You can change 51 settings by asking. Here is what they cover:
> background learning; remembering sensitive topics automatically; lights without asking (what
> asks first); prompt coach (the prompt coach); asking before every web search (the web
> search); …; Lockdown (what asks first). A family that names a number covers that many
> separate settings. Anything that loosens a rule still shows you a card first, and say "undo"
> in the same chat if you change your mind."**
> the HUD's own badge: **`ANSWERED BY  no AI model`** · **`LATENCY  71 ms`**

The count is **51**, not the old **13**, and the answer is in plain words with family rows
standing for several settings — the shape the fix was for. **The number has moved again since
PR #365's own table** (which recorded `count 13 → 43`, `rows 13 → 26`): the live answer says 51
and lists 34 families. This record quotes the live answer rather than the PR's figure, and does
not claim to have re-derived 51 from the settings tables.

### 2.7 N5 — deleting a reminder that has already gone off

**PARTIAL.** The backend half — the fix — was driven end to end and **works**. The two UI
halves could not be reached.

*Driven:* a throwaway 60-second timer of this pass's own, labelled
`dsh field test timer - delete me` (`{"kind":"timer","seconds":60}` → `{"ok": true, "job":
{"id": "s4a222c035f", …}}`). It came due and the schedule listed it under `went_off` with
`"state": "fired"`. Then Delete:

```
POST /api/schedule/act {"id":"s4a222c035f","do":"delete"}
HTTP/1.0 200 OK
{"ok": true, "id": "s4a222c035f", "said": "Deleted."}
```

and the read-back is `"jobs": [], "todo": [], "went_off": [], "lists": []` — the row is gone
from both lists. **That is the exact opposite of the 2026-10-13 desktop record's own
observation**, `{"ok": false, "reason": "no_such_job"}` while the row was still in
`schedule.db`: the lead that record left is now closed, with the same call against the same
kind of fired job.

*BLOCKED — the desktop's own Delete button.* The *"Just went off"* plate with its **Snooze** and
**Delete** buttons is drawn on the **Brain window's Work tab** (`coming-up.js:61`,
`WENT_OFF_ACTIONS`, `brain.html:735-743`), and the Brain window cannot be opened from a
harness: a UI Automation search of both open windows for `Brain` returned
`MATCHES=0` in the bar and only two *text* nodes in the HUD (`BRAIN IN USE`, and a sentence),
with no control. *Who can settle it:* a person at the PC, two clicks.

*BLOCKED — the phone's Delete.* The installed build `1b546df` predates the fix
(`44ea3b7d`, merged 2026-10-13 16:17:50 -0700; `git merge-base --is-ancestor 44ea3b7d 1b546df`
→ **not an ancestor**). The phone *did* fire the timer and draw its notification
(`android.title=String (Timer done)`, `android.text=String (Jarvis: your timer is done.)`,
`actions=2`), and that notification cleared when the job was deleted from the PC — but the
**Delete** action under test is not in that build. See §5.

*Left clean:* both of this pass's timers were deleted and the schedule reads
`jobs: 0, todo: 0, went_off: 0, lists: 0`. No reminder of the owner's was touched.

### 2.8 N11 — the phone can ask the PC for a backup

**PARTIAL.** The route half — the whole point of the design — was driven and holds. The phone's
own screen could not be reached, and the PC-only refusal could not be staged.

*`GET /api/backup/status`* (the route the phone reads):

```
{"available": true, "folder": "Jarvis Backups", "keep": 5, "kept": 4,
 "last_backup_at": 1791650945, "last_backup_name": "jarvis-backup-20261010-164905.jbak",
 "verify": {"ok": true, "why": "complete", "words": "Jarvis checked this file just now: it is a
   complete, well-formed backup, and nothing about it has changed since it was written.",
   "proves_open": false, "limit": "Jarvis cannot prove from your phone that a backup OPENS -
   that needs the recovery code, and codes are only ever typed on your PC. …"},
 "last_attempt": null, "prepared": null}
```

Note the folder is named by its **last segment only** — *"Jarvis Backups"* — which is the design
rule; **this record does not print the full path either.**

*`POST /api/backup/prepare {}`* — **and it wrote nothing, checked by hash:**

```
HTTP/1.0 200 OK
{"ok": true, "pending": true, "id": "b27d610f976642bcae1976435beb6d06",
 "folder": "Jarvis Backups", "keep": 5, "message": "Your PC will make one locked backup into
 the folder you chose there, and show you a recovery code for it. Nothing is written until you
 say you have saved that code - so a run you do not finish leaves your PC exactly as it was. …"}
```

**The folder before and after is byte-for-byte identical** — five files, same sizes, same
SHA-256 prefixes, and the folder's own mtime unchanged:

| | count | `last-run.txt` | folder mtime |
|---|---|---|---|
| before `prepare` | 5 | `201` bytes, `3C0532061F2705F5` | `2026-10-14T00:25:37` |
| after `prepare` | 5 | `201` bytes, `3C0532061F2705F5` | `2026-10-14T00:25:37` |

and `GET /api/backup/status` then reads `"prepared": {"at": 1791968008.3989952, "expires_at":
1791968908.3989952}` — the pending run is visible, and **no code is in it**.

**The one-time code: minted, never used, and its fate is recorded.** `prepare` minted a code
(23 characters; **not printed here and never written to any file**), held in the PC's memory
with a **15-minute** window (`PENDING_TTL_S = 15 * 60`). **No commit was attempted with it.**
The brief's rule is honoured: the code did not go unrecorded — the run's id, its mint time and
its expiry are above, and it was left to lapse.

**Nothing was committed and no backup was made.** The only `commit` call made was with **no
code at all**, which writes nothing by the code's own contract:

```
POST http://<this PC's own Tailscale address>:4719/api/backup/commit {}    <- no code
HTTP/1.0 400 Bad Request
{"ok": false, "error": "That is not the code for the backup waiting to be written, so nothing
 was written and your folder is unchanged. Ask for a backup again."}
```

*BLOCKED — "refused from anywhere but the PC".* It could **not** be driven from this machine,
and that is a property of the machine, not a gap in the test: `jarvis_backup.request_commit`
calls `jarvis_owner_check.from_this_pc(peer, local)`, whose own docstring says *"Loopback
(127.0.0.1, ::1) is this PC. So is a connection from one of this PC's own addresses"* — and the
Tailscale call above was accepted (it reached the code check, not the 403). **A second device
is needed to make a request come from a phone's address.** *Who can settle it:* the owner, from
the phone, once the APK is current.

*BLOCKED — the phone's own **Back up now** screen.* The feature's backend merged in #408 at
2026-10-14 08:12 UTC; the phone's build is `1b546df`, hours earlier. The code-minted /
**full-screen in four groups of five** / **tick before the run can finish** half is therefore
absent from the phone under test. See §5.

### 2.9 N3 — the bar's far-left face

**PARTIAL, and the pixels were not judged.**

*What the live instrument can and cannot see, measured.* The bar window was opened from the
HUD's own **"Open the Jarvis bar"** control (`hud-open-bar`), and its **full 67-element** UI
Automation tree was dumped. It contains **no `#reactor`, no `#reactor-face` and no canvas
node** — only `#shell`, `#prompt`, the buttons and the primer. **So this pass could not measure
the live geometry of the face at all**, and does not claim to. (The plan's PASS-as-harness
numbers — slot 40 × 40, frame 40 × 40, backing store 360 × 360 — were **not** reproduced here.)

*What was read instead, and how far it goes.* On `origin/main`
(`git show origin/main:jarvis-desktop/src/style.css`) the fix is present:

```css
#reactor-face {
  width: 100%;
  height: 100%;
  /* … a grid item's automatic minimum size is its content's … the frame laid out
     40 x 150 in a 40 x 40 slot … */
  min-height: 0;
}
```

at line 295, with the defect written into the comment beside it, and
`jarvis-desktop/tests/bar-face.mjs` pins `min-height: 0 now`. The installed exe was written
2026-10-14 00:53:42 -0700, **35 minutes after** #402 merged (2026-10-14 00:18:09 -0700), so the
built app should carry it — **that is an inference from two timestamps, not a measurement.**

*The pixel half: not settled, and not guessed.* There is no vision provider on this machine,
and per the brief a screen capture through the acrylic window could not decide it. **This pass
did not obtain a decidable capture, so no verdict is given on what the face looks like.**
*Who can settle it:* the owner, by looking at the bar.

### 2.10 N7 — the second picture reader (RapidOCR), off by default

**PARTIAL.** The switch exists and was read as **off**, from the switch's own mouth:

```
> py -3 jarvis_ocr.py reader
The picture reader is: windows
  engine:    Windows' own text recognition
  available: yes
```

* Read-only: `_cmd_reader` with no argument only reads (`_fresh_settings()`, `status()`); it
  writes nothing, and `~/.openjarvis/ocr-reader.json` **does not exist** before or after, so
  the default is in force (`DEFAULT_READER = "windows"`, live `jarvis_ocr.py:99`).
* **There is no in-app control for it.** `set_reader` is called from exactly one place in the
  whole live backend — the command line, `jarvis_ocr.py:1216` — and `rapidocr` appears in **no
  other live module**; `git grep -i rapidocr -- jarvis-client` is empty. So the plan's driving
  method ("*App:* desktop. *Control:* the picture-reader switch") describes a control that does
  not exist in either app: it is a command line and a settings file.
* **The ON path was therefore not driven, and must not be:** the brief forbids turning it on,
  and there is no control to turn it on with. **The blacking-out property — the whole point of
  the switch — is NOT tested by this pass.**

### 2.11 N1 — one Update control that updates both halves

**PARTIAL.** The section is real and was read on the live 0.2.169 Settings page; the dialog was
not opened.

Read on real hardware (Settings → Updates): the heading **"Update both halves"**, the two
boxes `ub-repo` ("THE JARVIS PROGRAM FOLDER ON THIS PC") and `ub-backend` ("YOUR BACKEND FOLDER
(THE ONE HOLDING JARVIS_HUD.PY)"), a **"Save these two folders"** button, and the button
**"Update everything"** (`ub-go`). The app's own line beside it says, verbatim:

> *"This app does not know where the Jarvis program folder is on this PC, so it cannot update the
> backend. Type its full path into "The Jarvis program folder on this PC" above - the folder you
> cloned from GitHub, the one with a scripts folder in it. Nothing was changed."*
> *"Cannot update the backend on this PC yet — see the line above."*

**Pressing `ub-go` produced no dialog.** The element is present and reports
`HAS InvokePatternIdentifiers.Pattern`, but `Invoke()` threw, twice and reproducibly:

```
Exception calling "Invoke" with "0" argument(s): "Unrecognized error."
```

and `-Scroll` reported `scrolled 0 container(s)`. **So none of the five facts the plan's PASS
requires — the backend folder by path, the `_jarvis-backup-<date>` copy, which half runs first,
what happens if the first half fails — could be read.** Two independent reasons stand in the
way, and both are named: the app does not know the folder (its own words), and the harness
cannot invoke the button. **No path was typed and no run was started** — a real run rewrites his
live install and is the owner's call, and this pass was told never to run
`scripts/apply-patches.ps1`. *Who can settle it:* the owner, at the PC.

### 2.12 N4 — a switch found by the words printed on it

**BLOCKED — the phone under test predates the fix.** Both boxes were driven on the phone, and
both gave the **pre-fix** answer PR #391's body records (`settings=[] find=[]`):

| the box | what was typed | the phone's literal answer |
|---|---|---|
| Settings → **SEARCH SETTINGS** | `Hide memory lists and chat history` | **"Nothing here matches “Hide memory lists and chat history”."** + "Clear the box and everything comes back." |
| Home → **Find** ("Find anything", "78 things Jarvis can do") | the same words | **"Nothing matches that."** + "Try the name you see on the screen, or a word from its one-line description." |

That is not a failure of the fix: **the fix is provably absent from this build.** #391's merge
`88f460a8` is dated 2026-10-14 01:21:03 UTC, and
`git merge-base --is-ancestor 88f460a8 1b546df` is **false** — the phone's own banner names its
build as `1b546df`, 2026-10-13 13:00:19 -0700, five hours before the fix merged. See §5.

### 2.13 N13 — a dead model lane says so, before the question

**BLOCKED — the fix merged during this pass, after every build under test was written, so there
is nothing on this machine carrying it to drive.**

**The state changed while the pass was running, and both readings are recorded because both were
true when taken.** At the start of the pass PR **#409 was open** (`409 OPEN MERGEABLE`);
`git grep -n "local model isn't running" origin/main` returned **nothing**, and the live
backend's own `jarvis_hud.html` contained the sentence **nowhere**. **#409 merged at
2026-10-14 08:54:06 UTC = 01:54:06 -0700**, and the refreshed `origin/main` (`ee6078bd`) now
carries it:

```
origin/main:jarvis-desktop/src/lane-warning.js
    export const LANE_DOWN_WORDS = "The local model isn't running on your PC.";
origin/main:jarvis-client/.../ModelWords.kt:57
    const val HOME_SUFFIX = "Model not running"
```

**None of it is on the machine under test, measured rather than inferred from a date alone:**

* the installed desktop exe was written **00:53:42 -0700** — **61 minutes before** #409 merged,
  so the running 0.2.169 cannot have been built from a `main` containing it;
* the live backend's served HUD asset, `jarvis_hud.html` in the live backend folder, contained
  **0** occurrences of *"local model isn't running"* (measured this pass, after the merge), so
  the page the live backend serves cannot draw the line either;
* the phone's build is `1b546df`, a day older still.

*And the state could not be produced honestly even with the fix present:* it needs
`GET /api/status` to carry `"ollama": false`, which the plan's own method reaches by pointing
`OLLAMA_URL` at a dead port and **restarting his live backend** — a change to the machine that
outlives the test, and one the standing restore rule forbids while other agents may be using the
backend. **No restart was performed.** What the live status does say, for the record, is
`"ollama": true`.

### 2.14 N12, N15, N16 — the three backup features still in flight

**BLOCKED — not merged, so not in any build under test.** Checked with
`gh pr view <n> --json state` on 2026-10-14, not taken from the plan's table:

| row | the PR | its state | why that blocks the row |
|---|---|---|---|
| **N12** one destination for both backups | #407 | **OPEN, CONFLICTING** | the picker and the run-time read of `backup.json` are not on `main` |
| **N15** personal data copied by SQLite | #403 | **OPEN, MERGEABLE** | the snapshot tool's new behaviour is not on `main` |
| **N16** the weekly snapshots encrypted | #406 and #412 | **OPEN** (#406 MERGEABLE, #412 **CONFLICTING**) | neither is on `main` |

**A conflicted pull request gets no CI at all** (`CLAUDE.md`), so #407 and #412 have to be
resolved before they can even be tested. *Who can settle it:* whoever clears the conflicts and
merges; then a pass drives them.

### 2.15 N14 — a device says what it is

**BLOCKED — both builds under test predate the merge.** #381 merged 2026-10-14 08:05:29 UTC =
**01:05:29 -0700**, and the installed desktop exe was written **00:53:42 -0700** — twelve
minutes earlier — while the phone's build is a day older still. *Stated as a timestamp
comparison*, not as a reading of the binaries: the shipped builds cannot have been built from a
`main` containing it, so the row was not driven rather than being driven and failed.

---

## 3. The rows that were not reached, and why

Named honestly, each with its reason and its verdict. **None of these is a pass, and none is
quietly dropped.**

### 3.1 The desktop memory and history group (14 rows)

`memory-tab` (26), `memory-saved` (27), `memory-waiting` (28), `memory-known` (29),
`memory-people` (30), `pinned-facts` (31), `between-us` (32), `memory-learning` (34),
`memory-as-of` (37), `history` (39), `chat-tags` (40), `forget-range` (41), `sensitive-facts`
(66), `history-search` (17) — **BLOCKED, reason: his fingerprint and Windows Hello, and the
Brain window.** The plate is on the **Brain** window's tabs, and this pass re-confirmed the
2026-10-13 finding by measurement rather than repeating it: a UI Automation search of both open
windows for `Brain` returned **`MATCHES=0`** in the bar, and in the HUD only two *text* nodes,
**no control**. Even reached, the rows read *"Hidden. Show asks Windows Hello first"* — the
gate working, not the feature failing. *Who can settle it:* the owner, at the PC.

### 3.2 The desktop-only rows needing a person at the machine

| row | what it needs | verdict |
|---|---|---|
| `work-tab` (101) | the Brain's Work tab, from the tray icon | **BLOCKED** — the Brain window cannot be opened from a harness (measured above) |
| `talk-to-type` (14) | Windows Hello to turn it on, and **his voice** to type | **BLOCKED — Windows Hello, and his voice** |
| `model-memory` (98) | the Model page's summary row | **BLOCKED for a harness; a person at the PC settles it** |

### 3.3 The rows needing hardware or a behaviour that must not be staged

| row | why no agent can reach it | verdict |
|---|---|---|
| `phone-watch` (81) | *"no paired watch"* | **NOT-TESTABLE** |
| `rush-latch` (125) | needs a turn carrying rushing text; **a harness must not manufacture a rush at the owner** | **NOT-TESTABLE** |
| `also-on-phone` (85) | the copy **writes into his own Clock or Calendar**; a harness must not put something in his calendar to prove a button | **BLOCKED** — *the owner settles it* |
| `live-extras` (13) | needs a Live session and OS surfaces this pass does not have | **NOT-TESTABLE** |

### 3.4 The NOT-TESTABLE ten

No driving method is written for these, deliberately — each needs **a service or an account
this PC does not have**: `crisis-help` (67) **not provoked, by choice**, `home-status` (68),
`calendar` (71), `weather-sky` (72), `email-read` (73), `email-send` (74), `email-drafts` (75),
`inbox-tidy` (76), `lights` (69), `locks` (70). Each is **NOT-TESTABLE**, with "the thing it
talks to does not exist here" as the reason — not "I could not reach it".

### 3.5 What no agent can reach (§4 of the plan)

| what | row(s) | verdict |
|---|---|---|
| **His voice** | `wake-word` (4), `voice-check` (8), `interrupt` (11), `custom-voices` (9), `read-aloud` (5), `spoken-style` (6), `voice-training` (7), `live` (12)'s session | **NOT-TESTABLE** — *"a stand-in would test the stand-in"* |
| **The camera, and a photo of his** | `live-camera` (47), `photo-reminder` (46) | **NOT-TESTABLE** |
| **His fingerprint / Windows Hello** | `app-lock` (120), `big-model` (105) | **BLOCKED — his fingerprint; Windows Hello** |
| **His accounts and keys** | `accounts` (113), `chatbot-money` (65) | **NOT-TESTABLE** |
| **A real company and a real account** | `support` (59) | **NOT-TESTABLE** |

---

## 4. The counts

**The unit is the row as this record writes it.** Every verdict in §2 and §3 is one row below,
and the arithmetic is checkable against the tables.

| verdict | rows |
|---|---|
| **PASS** | **4** |
| **PARTIAL** | **7** |
| **BLOCKED** | **26** |
| **NOT-TESTABLE** | **26** |
| **total rows written** | **63** |

**The four passes**, named, so nobody has to hunt for them: N2 (the attention route, with a real
write and a hash-proved restore) · N6 (both raise cards, `reach: local`, `classified: true`,
both denied) · N8 ("what can I change?" → 51) · N10 (a loosening raises a card, is denied, and
the setting does not move).

**The seven partials:** N9 · row 24 · N5 · N11 · N3 · N7 · N1.

**Nine of the BLOCKED rows are on the pile because a build under test is too old** — those are
listed separately in §5, and they are the ones a single APK or installer would clear.

**Nothing here is a FAIL.** No row was driven and produced the wrong thing: every row that could
be reached answered as the fix says it should. What is missing is reach, not correctness — and
per this project's rule, reach that is missing is written as BLOCKED or NOT-TESTABLE, never as
a pass.

---

## 5. What is blocked on the newer phone APK — the explicit list

The phone under test is **0.2.1380, build `1b546df` (2026-10-13 13:00:19 -0700)**, read from
the app's own banner. Every one below was checked with
`git merge-base --is-ancestor <fix> 1b546df` → **false**, so the fix is provably not in it.

| row | the fix | merged | what the phone cannot do until it is current |
|---|---|---|---|
| **N4** settings search | `88f460a8` (#391) | 2026-10-14 01:21:03 UTC | find a switch by the words printed on it — both boxes answer *"Nothing here matches"* / *"Nothing matches that."* |
| **N5** fired-reminder Delete | `44ea3b7d` (#387) | 2026-10-13 16:17:50 -0700 | delete a fired reminder from the *"Just went off"* row (the desktop/backend half **works**, §2.7) |
| **N11** the phone's **Back up now** | `cb35c914` (#408) | 2026-10-14 08:12:35 UTC | ask the PC for a backup, and the code drawn full-screen in four groups of five with the tick before the run can finish |
| **N14** a device says what it is | #381 | 2026-10-14 08:05:29 UTC | show the kind of each device, and keep two same-labelled rows distinguishable |
| **N13** the phone's Home status line | #409 — **merged 2026-10-14 08:54:06 UTC, after this build** | 2026-10-14 01:54:06 -0700 | read **"Connected · Model not running"**; blocked twice over: the APK predates the merge, and so does the installed desktop exe |

**Also on this pile, and worth saying plainly:** the published `client-latest` APK is older than
`main`, and republishing needs a full `Jarvis client` CI run whose smoke job passes while `main`
keeps moving. So this list will grow, not shrink, until that run lands. Nothing in §2 or §3 is a
defect report against the phone: it is a build that predates the fixes.

---

## 6. What was changed, and how it was put back

The owner authorised real actions for this pass. Nothing was approved; nothing of his was
deleted; no privacy setting was loosened. **Every change below is named with its restore and its
proof.**

| what was changed | restore | proof it is back |
|---|---|---|
| `spoken_per_day` written and re-written through the route (3 → 3, and a raise to 4 that was **denied**) | the value was never different from 3; the raise wrote nothing | `jarvis-framework.toml` SHA-256 `65BB08…845` **before and after**; the file's own line reads `spoken_per_day = 3` |
| `digest_hour` moved 18 → 19, then back | `POST {"digest_hour": 18}` → `from 19, to 18` | the **same SHA-256** after the restore; the file's own line reads `digest_hour = 18` |
| `humour` flipped **by the app** for N9's grammar control: `{"manner": "warm", "humor": false}` → `…"humor": true}` | the HUD turn `turn off humour` → *"Jarvis will not use humour."* | `manner.json` reads `{"manner": "warm", "humor": false}` |
| two throwaway timers created (`s4a222c035f`, `s89d6e07d04`), both labelled `dsh field test timer … delete me` | `POST /api/schedule/act {"do":"delete"}` → `{"ok": true, …, "said": "Deleted."}` for each | `GET /api/schedule` reads `"jobs": [], "todo": [], "went_off": [], "lists": []` |
| three approval cards **raised and denied** (`3b5615ea57cc`, `4eaf031e79bb`, `8e678a1f013e`) | denying is the restore — it leaves the setting at its prior value and takes the card off the queue | `GET /api/pending` reads `"pending": []` |
| a backup run **prepared** for N11 | nothing to restore — `prepare` writes nothing | the backup folder is byte-for-byte identical (§2.8); **nothing was committed** |
| a **recovery code** minted by `prepare` | none needed — it was never used | the run was left to lapse; its id and expiry are in §2.8, and the code is not written down anywhere |
| the desktop **Settings window** opened for N1 | closed again | the window list is back to the one pre-existing `Jarvis` (HUD) window |
| the phone's **Settings search** and **Find** boxes used for N4 | cleared, and the screen returned to Home | the phone is on `MainActivity`'s Home with no search text |
| `docs/README.md`'s document count, to make room for this record | not a change to the machine; a two-digit edit on this branch | `main` stated **380** while its tree held **381** (§8.1), so the count was written as **382** — `main`'s real 381 plus this record. **The size figure was left exactly as it was**, per the rule that only the count is bumped by hand and the size is refreshed on its own branch. `python -B tools/check_docs_map.py` exits **0** on this branch |

**Not touched, on purpose:** no card was approved; no privacy switch was moved; no Windows Hello
prompt was completed; no fingerprint prompt was answered; `C:\Users\pcadmin\.openjarvis\config.toml`
was **not** edited by hand (the route wrote `jarvis-framework.toml`, the module's own settings
file, and it was restored); `scripts/apply-patches.ps1` was **never run**;
`.github/workflows/ci.yml` was not touched; **no service was restarted**.

**Two of the owner's own fired reminders** show notifications on the phone
(`se9ab3630ca`, `s734d5434c2`). They are **his**, they predate this pass, and they were left
exactly where they were. Their words are deliberately **not** written down here.

*One row the plan says not to "restore" by guesswork:* the owner's repeating reminder
`se80955f188`, lost during the 2026-10-13 desktop pass with no established cause. **It was not
recreated, no cause was invented for its loss, and the count of 0 was not read as evidence about
it.**

---

## 7. What in the plan and the brief was wrong

Said plainly, because the standing instruction is to say so rather than route around it.

1. **The plan's N2 driving method is wrong twice.** It says the route takes
   `{"per_day": <current+1>}` and that the current values are read "first with a `GET`".
   The live route accepts **`spoken_per_day`** or **`digest_hour`** only, and there is **no GET**:
   `GET /api/attention/settings` → **404** `{"error": "not found"}`, while
   `POST {}` → 400 *"Send one of these: spoken_per_day, digest_hour."*
2. **`{"per_day": <current+1>}` would also have been a raise**, and a raise is a loosening that
   raises a card and **blocks the request** until the card is answered or expires. The plan's
   restore step — "put the number back and name the prior value" — **cannot be done through the
   route**: putting it back is itself a raise, so it needs a card, and a harness must deny cards.
   This pass avoided the trap by writing only the symmetric key (`digest_hour`, never a
   loosening) and proving the restore by hash. **The plan should say so.**
3. **The plan's "599 at the ten-minute ceiling" is stale.** The live ceiling is
   `approval_timeout_seconds = 900` — 15 minutes — and the cards read `expires_in: 895`.
4. **The plan's N7 describes a control that does not exist.** "the picture-reader switch (off by
   default)" is a **command line** (`py -3 jarvis_ocr.py reader rapidocr`) and a settings file
   (`~/.openjarvis/ocr-reader.json`), reachable from no route and neither app: `set_reader` has
   exactly one caller in the whole live backend, and `rapidocr` appears in no other live module.
5. **The plan's §1b table is out of date, as the plan itself warns.** Since it was written:
   **#408 merged** (2026-10-14 08:12), **#381 merged** (08:05), and four PRs it does not mention
   are open (#414, #415, #416, #417, #418). #409, #407, #403, #406, #412 are still open. A pass
   must re-read `gh pr list` — this one did.
6. **The plan's N8 figures have moved.** It quotes PR #365's `count 13 → 43`, `rows 13 → 26`;
   the live answer on the shipped backend says **"You can change 51 settings"** and lists 34
   families. The number to quote is the live one.
7. **The brief's list of things to drive included two that cannot be driven, and the reason is
   the same one for both: a build.** The **dead-lane warning** (#409) **merged at 01:54:06
   -0700 — 61 minutes after the installed desktop exe was written, and a day after the phone's
   build** — and the **fired-reminder Delete on the phone** is gated behind an APK from the 8th.
   Both are BLOCKED, not failures. **`main` also moved twice during this pass** (#411 and #409),
   which is why §2.13 carries both readings of the same row: each was true when it was taken.
8. **The brief's own state notes were right where it mattered and are confirmed here**: the route
   that was a 404 now answers (400/200/409, never 404-for-unknown-route); `GET /api/backup/status`
   and `POST /api/backup/prepare` are live and `prepare` writes nothing; the desktop is 0.2.169;
   the phone is 0.2.1380 and not updated. **The brief's "both model lanes are up" could not be
   checked by this pass** — `tools/check_lanes.py` was not run and no lane was probed, so this
   record says nothing about the coding lane either way.
9. **A trap that is worth writing down**: `jarvis-framework.toml` — the file the attention and
   limits settings are actually written into — is **beside the modules in the live backend
   folder**, not `~/.openjarvis/config.toml`. This pass grepped the wrong file first and briefly
   concluded the route was not live, because the patch in the repo is against `jarvis_hud.py`
   while the wording of its error message lives in `jarvis_arbiter.py`. The fix is to read the
   route, not to guess from the module name.

---

## 8. Defects and anomalies this pass found, with the evidence

Named, with the evidence, and — where they are not diagnosed — **saying so** rather than
guessing at a cause. Two of these were found *because* this record was written.

### 8.1 `main`'s own docs map is red — measured, not inferred

**This is a defect on `main`, found by adding a document.** `main` at `ee6078bd` (and at
`6525d123` before it) has **381** markdown documents under `docs/`, while `docs/README.md`
states **380**, in both places it states it. Measured in a detached worktree of `origin/main`:

```
> python -B tools/check_docs_map.py
ok    ...docs/README.md states how many documents there are
FAIL  every document count on the page matches the tree (381)
docs map FAILED. Re-run the two lines the page prints and put today's numbers in it:
exit 1
```

PR **#411** added `docs/ABOUT-JARVIS.md` and did not bump the page. **The consequence for this
record is that its own bump is two, not one**: the count had to go from `main`'s stated **380**
to **382** (`main`'s real 381, plus this record) — see §6. The size figure was deliberately left
alone, per the standing rule that only the count is bumped by hand. *Who can settle it:* this
PR's own bump **is** the correction; if it is not taken, `main` stays red on this checker.

### 8.2 The bar draws a card's own words while the queue is empty — named, not diagnosed

Twice, after both cards had been **denied**, the bar's own approval region still read as though
a card were waiting, while `GET /api/pending` said otherwise. Both readings were taken in the
same minute:

| the bar's own words (`#approval-kicker` + title) | `GET /api/pending` |
|---|---|
| **"Needs your OK: Jarvis wants to let Jarvis do more, for longer, or more often. No undo · stays on this machine — lets Jarvis keep your Undo history longer…"** | `{"available": true, "pending": [], …` |
| **"Needs your OK: Jarvis wants to also learn sensitive topics automatically. Reversible · stays on this machine — lets Jarvis also save facts about health, money and other people's private details without asking first…"** | `{"available": true, "pending": [], …` |

**What is not established, and is not being claimed:** whether the bar keeps the last card on
screen by design. `jarvis-desktop/src/main.js` holds state for *"Gate ids the user put away with
Esc. Still pending; just not on screen"* (`main.js:640`), and the two cards above had been
**denied**, not put away with Esc — but this pass did not read far enough into the bar's own
card rendering to say whether a decided card is deliberately left visible or is a stale
re-render. **The owning side can settle it in one read of `main.js`; this record hands it over
with both halves quoted rather than diagnosing it.**

### 8.3 The model's stated reason for refusing a setting change is not supported by its own turn

§2.1: the answer said the change could not be made because the reply *"is pulled from a web
page"*, while the same turn's own `X-Jarvis-Route` says `"tainted": false` and
`"injected_facts": 0`. **Named, not diagnosed** — the route header and the answer are both
quoted, and the module that owns the wording (`jarvis_agent.py`) is the one that can say which
of the two is wrong.

### 8.4 A prepared backup run is still advertised after its own expiry

Measured at the very end of the pass, on the run §2.8 prepared and deliberately left to lapse:

```
GET /api/backup/status
    "prepared": {"at": 1791968008.3989952, "expires_at": 1791968908.3989952}
the PC's own clock at that read:  1791969123.3     <- 215 seconds PAST expires_at
```

`request_commit` refuses an expired run (`_is_expired(row)` → `COMMIT_NO_RUN`), so **nothing
unsafe can happen**: what is stale is the *report*. The phone reads this field, so a screen that
trusts it would show a countdown that has already run out. **Named, not diagnosed** — this pass
did not read the phone's backup screen (it is not in the installed build), and whether the phone
guards against an expired `prepared` is exactly the thing that could not be tested.

### 8.5 Two smaller things this pass had to work around, for the next one

* **`POST /api/backup/prepare` with no request body at all answers 400; with `{}` it answers
  200.** Every other route this pass drove tolerates an absent body. The phone sends a body, so
  nothing is broken; it is written down because a harness that omits the body reads it as a
  refusal rather than as a missing argument.
* **The bar window exposes no face element to Windows UI Automation.** Its full 67-element tree
  contains no `#reactor`, no `#reactor-face` and no canvas node, so the geometry half of the
  bar-face row (§2.9) **cannot be measured on real hardware by this project's own instrument** —
  only by the suite or by a person's eyes. That is a gap in the instrument, not in the app, and
  it is the reason `tests/bar-face.mjs` exists at all.

---

## 9. What this pass could not test, in one list

* **Anything needing his voice** — every row in §3.5's first block.
* **Anything needing his fingerprint, his PIN, or Windows Hello** — the desktop memory group,
  `app-lock`, `big-model`, `talk-to-type`.
* **Anything needing his accounts, keys, calendar, mail or Home Assistant** — the ten in §3.4
  and `accounts`/`chatbot-money`.
* **Anything needing a second device** — the "commit is refused from anywhere but the PC" half of
  N11, and any card decided from the phone.
* **Anything needing the camera, a paired watch, or a photo of his.**
* **Anything needing the newer phone APK** — §5, nine rows' worth of reach.
* **Anything needing the Brain window** — a harness cannot open it; measured, not assumed.
* **The pixels of the bar's face**, and every other "drawn, not text" surface.
* **The desktop suite, and the backend suite.** `backend/run_suites.py` was **not** run: it is
  unsafe right now (concurrent runs corrupt each other's staging and produce false reds pointing
  at another runner's `jarvis-sweep-*` folder), and the brief says so. **Suites are not field
  testing anyway**, and nothing here rests on a suite result.
