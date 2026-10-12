# Does his machine match the repo?

**Written 2026-10-11. Checkout `.dsh-scratch/jarvis-pictures` (branch `audit/machine-vs-repo`), off
`origin/main` `40f58fcf`.** Everything here was measured **read-only**: his installed program, his
phone and his running backend were read, nothing in them was changed.

**The short answer: no, and by three different amounts.** His backend is missing **three features**
that merged on 2026-10-10, and five of its modules are older copies than main's. His desktop app is
**two published builds behind**. His phone was updated today but carries no record of which commit it
was built from. None of the three can tell him he is behind - and one of them, the backend, can
finish a patch run **partially** and report success.

| surface | what he runs | what main has | the gap | how to close it |
|---|---|---|---|---|
| **backend** | patched 2026-10-11 11:48, and its own record says `"run": "partial"` | 144 patches, 190 shipped files | **5 patches never applied**, so **3 features are absent** and 5 modules are older copies | run `scripts/apply-patches.ps1` from an up-to-date checkout, **without `-SkipMissing`**, with Jarvis closed |
| **desktop** | **0.2.140**, installed 2026-10-11 11:23 | **0.2.142**, from `d98a5b2`, published 2026-10-11 22:52 | one behaviour change since (`f0e1dbe3`, the mesh-name pairing fix) plus the new cards/pictures UI rows | in the app: **Settings -> Updates -> Check now -> Install**. Jarvis never installs an update on its own |
| **phone** | `0.2.10008`, installed **2026-10-11 19:38** (from the device itself) | Android pre-release `0.2.1253` (main @ `4c604e8`) | 45 commits have touched `jarvis-client/` since the last commit the pass could pin its APK to | install the published APK, or build and `adb install` it |

---

## Settlement, re-measured later the same evening at `9c91e1fb`

**The page above is kept as it was measured; this is what it says now.** He ran the patcher again at
**21:01**, and most of the backend gap on this page closed. Re-measured with the same commands, the
same rule and the same read-only discipline:

| what this page says above | what it says now |
|---|---|
| his record: `run: partial`, **139** of 144 patches, 208 files, written **11:48:25** | `run: partial`, **142** of 144, 211 files, written **21:01:51** |
| **five** patches not applied | **two**: `embedding-guard.patch`, `event-allowlist.patch` |
| **three features absent** (`jarvis_work.py`, `jarvis_card_summary.py`, `jarvis_pictures.py`) | **all three present** - his `jarvis_hud.py` is now 370,234 bytes and carries cards-read-short's and pictures' install blocks |
| preflight rule: **182 identical, 3 missing, 5 different** - eight FAILs | **190 identical, 0 missing, 0 different** - **no module FAIL remains** |
| desktop: latest **0.2.142** (`d98a5b2`, 22:52) | latest **0.2.145** (`5891a87`, 2026-10-12 05:44) - his 0.2.140 is now **five** builds behind |
| **45** commits have touched `jarvis-client/` since `04af95c3` | **62** |

**Two corrections this page needs, both found by re-measuring:**

1. **The test for Work setups was wrong.** Section 1 says his hud has no
   `jarvis_work.install(Handler`. `work.patch` **does not add a startup call at all** - it wires
   `jarvis_work` as route handlers (`jarvis_work.status()`, `handle_recommend`, `handle_choose`),
   which his hud now has at lines 2914-2926 and 4137-4173. The absence of an install call was never
   evidence about that feature; the same is true of `big_coder` and `power_switch`, which are wired
   the same way.
2. **The two patches still missing from his record have no observable effect.** They touch
   `jarvis_memory.py` and `jarvis_events.py`, and **both files are byte-identical to main's** (the
   `0 different` above). So nothing they change is missing; what remains is only that his record says
   `partial` and, as section 3 says, **does not record which patches it left out or why**.

**The gap that did not close is the one sections 2 and 3 describe**, and it did not close because it
needs an *install*, not a patch run: the desktop is five published builds behind, and the phone is 62
commits behind. Nothing on the machine can tell him either - that part of the page is unchanged.

---

## 1. The backend on his PC

### What he is actually running

* the folder: `C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program`
* **right now:** `jarvis_hud.py` from that folder, process 69344, **started 2026-10-11 20:33:54**
* his `jarvis_hud.py`: 364,227 bytes, last written **2026-10-11 11:48:10**
* his installer's own record, `_jarvis-state.json`, written **2026-10-11T11:48:25**:

```
"run": "partial"          <- the run did not apply everything
139 patches applied, 0 unmatched, 208 files recorded
```

### What main has, and what is missing

Main's `scripts/apply-patches.ps1` lists **144** patches. Comparing that list with his record's 139,
**five patches main has but his last run did not apply**:

| patch | what it carries | module it needs |
|---|---|---|
| `work.patch` | **Work setups** - five model combinations for kinds of work, explained first (#267, `6f15b8a9`, 2026-10-10) | `jarvis_work.py` |
| `card-prefs.patch` | **Approval cards read short** - a summary, "Explain more", and a setting (#266, `c08d768a`, 2026-10-10) | `jarvis_card_summary.py` |
| `pictures.patch` | **Ask for a picture, and keep it** (#276, `c94e180b`, 2026-10-10) | `jarvis_pictures.py` |
| `embedding-guard.patch` | touches `jarvis_memory.py` | - |
| `event-allowlist.patch` | touches `jarvis_events.py` | - |

Measured with the preflight's own rule (`backend/selftest.py`, `pf_modules`: compare each of
`_where.SHIPPED`'s **190** entries, install side by its **leaf** name, SHA-256 over the bytes with
CRLF folded to LF):

```
182 identical      3 MISSING      5 DIFFERENT
missing   : jarvis_work.py, jarvis_card_summary.py, jarvis_pictures.py
different : jarvis_quick.py, jarvis_settings_registry.py, jarvis_card_words.py,
            jarvis_picture_card.py, jarvis_menus.py
```

The five "different" ones are not random: each matches a **specific commit on main**, and each has
moved only because of the three features above and their follow-ups.

| his copy of | is main as of | it is behind by |
|---|---|---|
| `jarvis_quick.py` | `25d04cb7` (2026-10-10) | cards read short (`c08d768a`) |
| `jarvis_menus.py` | `35f57331` (2026-10-10) | pictures, cards read short |
| `jarvis_settings_registry.py` | `f13d7951` (2026-10-11) | pictures, cards read short |
| `jarvis_card_words.py` | `f2077b51` (2026-10-11) | cards read short and its CI fixes (`fba50abc`) |
| `jarvis_picture_card.py` | `1eca139c` (2026-10-11) | the picture graph fix for this PC (`9a2656aa`) |

And his `jarvis_hud.py` has no startup call for any of the three: no `jarvis_work.install(Handler`,
no `jarvis_card_summary.install(Handler`, no `jarvis_pictures.install(Handler`. The single mention of
`jarvis_pictures` in the whole file is a **comment inside picture-card's block** that still says
"section 123" - the number main had before the renumbering to 129.

### What he will notice

* **No Work setups.** Nothing offers the five combinations built for kinds of work.
* **No "cards read short".** His approval cards cannot be told to show a summary with an "Explain
  more", and the setting behind it is not there.
* **No "ask for a picture".** The three picture routes do not exist, and neither does the setup card
  that would tell him the feature is off until he switches it on.
* **Some of today's fixes to features he already has are also missing**, because the same three
  features touched those five modules (`jarvis_menus.py`, `jarvis_settings_registry.py`,
  `jarvis_quick.py`, `jarvis_card_words.py`, `jarvis_picture_card.py`).

### How to close it

1. Get the checkout to current `main` (`git fetch`, and use the checkout the patcher runs from).
2. **Close Jarvis** - his backend is running right now (process 69344).
3. Run **`scripts/apply-patches.ps1`** and let it finish; **do not pass `-SkipMissing`**.
4. Start Jarvis again, then run the preflight (`backend/selftest.py --preflight`) and expect the three
   missing-file FAILs and the five "not this repository's copy" FAILs to be gone.

**A good sign for step 3:** with main's patch set as it stands today, **no patch is blocked** - I
checked every one of the 144 against his folder, and every file they expect is present. So the run
should have nothing to skip; whatever stopped those five last time is not a missing file today.

---

## 2. The desktop app: 0.2.140

### What he is running, and how it was dated

* `C:\Users\pcadmin\AppData\Local\Jarvis Desktop\jarvis-desktop.exe`, file dated **2026-10-11 11:23:02**
* the app's own Settings screen reads **Version 0.2.140 - the newest published** (recorded during the
  field test, `settings-desktop.txt:1738`)

**The version fields cannot answer this question.** `jarvis-desktop/src-tauri/tauri.conf.json` says
`"version": "0.2.0"` and `Cargo.toml` says `version = "0.2.0"`; `0.2.140` is a build number that lives
outside them. So the gap had to be dated from history - the same way the stuck-badge defect was dated:

| | |
|---|---|
| his build | installed 2026-10-11 **11:23** |
| main's published build | **0.2.142**, from commit **`d98a5b2`** on `main`, published 2026-10-11 **22:52** (`desktop-latest` is a rolling tag; the commit is named in the release body) |

### What main has that his build does not

Only **one non-merge commit** has touched `jarvis-desktop/` since his build:

* **`f0e1dbe3`, 19:00 - "pairing: the PC finds its own mesh name, so NordVPN Meshnet stops asking"**.
  This is the one he will notice: it is the desktop half of pairing over a mesh network.

The merges since his build also carry the desktop rows for **cards read short** and **ask for a
picture**, which arrive with any build after his.

### The defect from the field test belongs here, not to the backend

The stuck **"Jarvis is watching"** sign is **client-side**: `jarvis-desktop/src/watch-badge.js` and
`watch-badge.html` ship inside the desktop app (with `src-tauri/capabilities/watch-badge.json`).
**No backend patch can change it** - it needs a desktop install. Re-patching the backend will not
touch the badge.

### How to close it

In the app: **Settings -> Updates -> Check now -> Install**. Jarvis never installs an update on its
own (release notes, 2026-10-11), so this waits for him.

---

## 3. The phone

### What he is running (read from the device, just now)

```
adb shell dumpsys package com.jarvis.client
  versionName=0.2.10008      versionCode=10008
  lastUpdateTime=2026-10-11 19:38:21
  firstInstallTime=2026-10-09 22:14:29      device f0a5b32b
```

So the phone was updated **today at 19:38**. But **the app carries no record of which commit it was
built from**: `0.2.10008` is a local build counter, not a main commit, and it does not match any
published release number (the published Android pre-release is `0.2.1253`). The only commit the
field-test pass could pin to an APK was `04af95c3` (2026-10-10), inferred by comparing
`jarvis-client/` against main.

### What main has that his phone does not

**45 commits have touched `jarvis-client/` since `04af95c3`** (21 of them non-merge). The ones a user
would notice:

| commit | what he would notice |
|---|---|
| `ce1552f1` | **download and install an update from inside the app, with a changelog** |
| `393754b2` | the Galaxy gets a direct button on Home |
| `5f53d3db`, `04ab9da5`, `efefe7b9` | the Galaxy/Brain jump fixes - a link into Brain scrolls to the plate it named |
| `719963ae` | a timer's notification gets a **Stop**, and a "went off" notice whose job is gone is taken away |
| `f68a515e` | the quick-settings tiles say what they do, not "Jarvis tile 1" |
| `31e90b54` | the Find rows into Brain reach their card |
| `f2077b51`, `c08d768a`, `7380ad8f` | the client rows for the uncensored opt-ins, cards read short, and the picture setup card |

There is a small irony worth writing down: **the in-app update screen is one of the things he does not
have yet**, so the easiest route to getting current is exactly the route he cannot use until he is
current.

### How to close it

Install the published Android pre-release APK, or build `jarvis-client` from current `main` and
`adb install` it. Nothing on the phone checks for a newer build by itself.

---

## The honest part: how he gets current, and why this keeps happening

**Nothing pulls.** All three surfaces advance only when a person does something at the machine:

| surface | the only way it moves | needs him at the machine? |
|---|---|---|
| backend | `scripts/apply-patches.ps1` | **yes** - and with Jarvis closed |
| desktop | Settings -> Updates -> Check now -> Install | yes |
| phone | install the APK | yes |

Meanwhile main moved **144 patches, a desktop build published at 22:52, and 45 client commits** in
about a day. So drift is not an accident of one bad run; it is the resting state of a machine whose
updates are all manual, and the gap will grow every day nobody runs the three steps.

**Three things make it worse than it needs to be, all measured here:**

1. **A partial install looks like a finished one.** His record says `"run": "partial"`, and the
   installer's own help text for that mode says: *"Leave out any patch that needs a backend file which
   is not there, and apply the rest. A PARTIAL install: the features those patches carry will not be
   present."* It is a deliberate, useful mode - and nothing in the install afterwards says **which**
   patches were left out or **which file** was missing. Working that out took a comparison against
   main's patch list, which is why this document exists.
2. **Nothing on the machine can say which commit it was built from.** The backend's manifest records
   patches and file hashes but not a source commit; the desktop's two version fields both say
   `0.2.0`, and the build number lives only in the release page; the phone's `versionName` is a local
   counter. So "does this machine match the repo?" is **not answerable from the machine alone** - it
   has to be inferred from history and hashes.
3. **The "is a newer version waiting?" half is still not built.** `docs/PREFLIGHT-MODULE-COMPARISON-DECISION.md`
   already says so in its own "What is still open": the check today compares the files that are there
   and can fail for a *differing* copy, but it does not yet read the patcher's own patch list to say
   "a newer version is waiting". That is the check that would have told him three features were
   missing without anyone opening a terminal.

**And one thing that is not the pipeline's fault:** the field test's stuck "Jarvis is watching" sign
is a desktop-app file, so it is not fixed by re-patching the backend. Two different updates are
needed for two different problems, and neither is automatic.

---

## Where the evidence is

| what | where it came from |
|---|---|
| his installer's record | `...\Desktop program\_jarvis-state.json` (`run`, `patches[139]`, `patchList`, `files[208]`) |
| main's patch list (144) and shipped list (190) | `git show origin/main:scripts/apply-patches.ps1` - `$PATCHES`, `$SHIPPED` |
| the preflight's own comparison rule | `git show origin/main:backend/selftest.py` - `pf_modules`; `backend/_where.py` - `SHIPPED` |
| which main version each of his files is | `git log --format=%H -- backend/<file>`, hashing each version with CRLF folded to LF |
| his desktop build's date | the installed `jarvis-desktop.exe`'s own timestamp |
| his desktop's published build | `gh release view desktop-latest` - body names the commit |
| the version fields that cannot answer it | `git show origin/main:jarvis-desktop/src-tauri/tauri.conf.json` (`0.2.0`), `Cargo.toml` (`0.2.0`) |
| the badge is client-side | `git ls-tree -r origin/main` - `jarvis-desktop/src/watch-badge.js`, `.html` |
| his phone, from the device | `adb shell dumpsys package com.jarvis.client` |
| what the phone is missing | `git log origin/main --oneline 04af95c3..origin/main -- jarvis-client` |
| the existing decision on the module check | `docs/PREFLIGHT-MODULE-COMPARISON-DECISION.md` |
| the field test that found the badge defect | `docs/FIELD-TEST-MATRIX-2026-10-11.md`, its second pass |

**How this was measured, so it can be repeated.** Nothing was written to his folder. Every claim about
main comes from `git show origin/main:<path>` or `git ls-tree -r origin/main`, never from a search in
a working tree, because this repository is worked in parallel worktrees and a plain `git grep` answers
"what does this checkout say" (see `CLAUDE.md`, "Do not claim more than the evidence supports").
