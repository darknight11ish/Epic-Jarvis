# The updater: why it cannot finish, and what to do about the owner's own edits

Written 2026-10-08 on `design/updater-redesign`, from `origin/main` at
`165e8f2d`. **No algorithm code in this pass** — this is a design note, a
reproduction, and the questions that belong to the owner.

Everything below was measured. The folding line where a command was run is
named beside the number, and nothing here was changed on the owner's machine:
his backend folder was **read only**, and every run happened against a copy in
`%TEMP%`.

---

## 1. What the tool does today, in plain words

`scripts/apply-patches.ps1` brings the owner's backend folder up to date. The
owner's folder is not in this repository (`docs/ARCHITECTURE.md` §9); this
repository holds **patches** — small text files describing edits — and the
script applies them in a fixed order.

The problem the script has to solve is that the owner's folder is often
**partly** patched: an earlier run applied the list as it was then, and since
then patches have been added and edited here. A patch cannot simply be applied
again if it is already on — the lines it looks for are no longer where it
expects.

So the script answers "which patches are on?" by **taking them off**. Its
rehearsal, on a throwaway copy, is:

1. **Strip.** Walk the 126-patch list backwards (newest first) and reverse
   each patch off the copy, one at a time.
2. **Re-apply.** Put the whole list back on, in order.
3. **Check the result.** Take the whole list off the copy again. The gate.

If step 3 cannot finish, the script refuses **everything** and changes
nothing. That refusal is correct — a backend missing half a feature is worse
than one waiting to be updated — but it is where the owner is stuck.

### Why it deadlocks

The strategy assumes that *what can be taken off* is *what is on*. On the
owner's backend that is false in both directions at once:

- `screen-attach.patch` is **on** his files and **can be taken off** there.
  But it was written to sit on the block `tutorials.patch` installs. Once the
  strip has removed both and the re-apply puts the list back on, `tutorials`
  lands exactly where `screen-attach`'s own context expects to find itself.
  Measured: in the re-apply, **both** fail (`git-ok=False`) and are recorded
  "already on … left as it is". The two are nested, so neither can be put back
  on in that rehearsal — and step 3 then cannot take `screen-attach` off the
  state the run would leave.
- Four further patches (`tasks`, `accounts`, `chatbot-limits`,
  `chatbot-limits-hud`) are on his files, and the strip **fails** to take them
  off — a later patch has rewritten the context they were written against. So
  they are left in the tree and then re-applied on top of themselves.

The strategy is therefore **circular**: what gets removed is decided by what
can be removed, and then the result is judged against a fixed list. On a stack
where any patch fails either half, there is no answer it can accept. That is
the deadlock, and it is in the strategy — not in any one patch, and not in the
patches being wrong.

---

## 2. The reproduction, and its real output

The script's own rehearsal copies `*.py` out of the backend folder
(`Reset-Rehearsal`, `apply-patches.ps1:2388`), so a copy is exactly what it
does. I made the same copy myself and pointed the script at it.

```powershell
# the owner's folder was only READ. This copy is what every run used.
$src = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"
$dst = "$env:TEMP\jarvis-deadlock-repro"
Copy-Item "$src\*" $dst -Recurse -Force

pwsh -File scripts\apply-patches.ps1 -BackendPath $dst -SkipTests -SkipPackages
```

`-SkipTests -SkipPackages` is what keeps it fast; it changes nothing about the
patch decision, which is over before either step runs. The run ended
`exit=1`. Its own words:

```
Endings : LF, which is what the patches expect

Rehearsing all 126 on a copy first.
  9 ok, 117 "not onto the files as they are"        <- expected: most are already on

122 of these are already on your backend from an earlier run.

Rehearsing again: take those off, newest first, then put all
126 back on in order. Still on the copy.
  124 ok
  already on   tutorials.patch  (left as it is)
  already on   screen-attach.patch  (left as it is)

  FAIL  1 patch(es) will not apply. NOTHING HAS BEEN CHANGED.

--- the state this run would leave ---
screen-attach.patch cannot be taken off the state this run would leave

This is not a patch that has drifted. Taking the applied ones off and
putting the whole list back on would leave a backend that does not carry
every patch in this list - and a backend missing part of a feature is
worse than one waiting to be updated. So nothing was changed, on
purpose. The patch named above is the one already on your files that
cannot survive that.
```

**This is the #107 deadlock, reproduced exactly, and it names the same two
patches.** The check stops at the first failure, so it names `screen-attach`;
`tutorials.patch` fails the same gate for the same reason. Every `.py` file in
the copy was byte-identical afterwards.

**And the two faults are visible in the run's own numbers**, without needing to
trust a hand-built replica of step 2:

- the strip prints `122 of these are already on your backend from an earlier
  run`, and instrumenting that exact loop shows it as
  `INSTR_FOUND_COUNT=122 INSTR_ALREADYON_COUNT=0`. So **122 came off and 4 did
  not** (`tasks`, `accounts`, `chatbot-limits`, `chatbot-limits-hud`).
- pass 2 prints `ok` for four patches that the strip had already confirmed were
  in the tree and taken off — and instrumenting the re-apply shows
  `chatbot-limits-hud.patch git-ok=True`, likewise `chatbot-limits`, `accounts`
  and `tasks`. Those four are exactly the four the strip could not take off, so
  they go on a second time.
- `tutorials.patch` and `screen-attach.patch` are reported `already on … left as
  it is`, and instrumenting confirms `git-ok=False` for both: neither is put
  back on, which is precisely the half-applied state step 3 exists to catch.

I could not make the headline counts add up to the last line, and I am not
going to dress that up. Pass 2 prints **124 `ok`** and 2 "already on", while
the patch list has 126 entries; the split-patch handling
(`$UsingRebuilt`, `apply-patches.ps1:1818`) and the two dropped superseded
patches mean the line the loop counts and the line I count are not obviously
the same, and I did not resolve it. **What is measured, and all this note
relies on, is the per-patch evidence above, read out of the script's own
branches.**

### Two things the #107 notes say that are no longer true, and one that is

- **Line endings are no longer the blocker.** The notes describe `-FixLineEndings`
  and a CRLF `jarvis_hud.py`. Today that file is **plain LF**, as are
  `jarvis_gate.py` and `jarvis_extract.py` (measured byte by byte). The script's
  own line says `Endings : LF, which is what the patches expect`. The
  `-FixLineEndings` deadlock is gone; the nest (`tutorials` / `screen-attach`)
  is what remains.
- **The 28 "rewritten" patches are no longer refused.** The notes say 28
  patches whose added lines a later patch rewrote "still answer not on and stay
  refused", with `token-file.patch`'s `TOKEN_FILE` line as the example. That
  line is still rewritten — the patch adds
  `TOKEN_FILE = CONFIG_DIR / "token"` and the owner's file carries
  `TOKEN_FILE = CONFIG_DIR / "token"      # the OLD plain-text place; only read, to move it`
  — but the script now recognises it. On today's state, of the 126 entries the
  strip is given, **122 come off (120 by their current text, 2 by an older text
  from `backend/patch-history/`) and 4 do not.** The `#107` work recognising
  122 where it used to recognise 9 still holds.
- **The `Test-PatchOnBackend` rescue does not fire at all on today's state.**
  Instrumenting the script's own strip loop (a copy of the script, on a copy of
  the backend; nothing of the owner's touched) prints
  `INSTR_FOUND_COUNT=122 INSTR_ALREADYON_COUNT=0`. The rescue added by `#107`
  — "already on, leave it alone" — is not what is refusing. The refusal is
  purely step 3.

### What the four un-strippable patches actually do

They are left in the tree, and the re-apply then puts them **on a second
time** — instrumenting the re-apply branch shows
`chatbot-limits-hud.patch git-ok=True`, and the same for `chatbot-limits`,
`accounts` and `tasks`. Nothing skipped them, because the "already on … left as
it is" verdict is only reached *after* a patch has failed to apply
(`apply-patches.ps1:2801`).

So the rehearsal's own result state contains a second copy of those four
patches' work. The gate then refuses — and here it happens to refuse over
`screen-attach` first, so this second problem is masked. That is worth saying
plainly: **on a backend where the nest is not present, the same code path would
reach the gate with a doubled result state, and the gate would be the only
thing standing between the owner and a file carrying the same edit twice.** The
gate is doing real work, not merely being stubborn.

I could not measure the doubled state directly: step 3 has no exit that keeps
its scratch folder, and a hand-built replica of step 2 did not reproduce the
script's exact split-patch handling (`$UsingRebuilt`, `apply-patches.ps1:1818`).
What is measured is the re-application itself.

### The set the tool is asked to work on is smaller than the folder

`backend/` holds **128** `.patch` files. The script's list holds **128** names,
but before the rehearsal it **drops two** — `embedding-guard.patch` and
`event-allowlist.patch`, whose only fix is already inside the rebuilt
`backend/rebuilt/jarvis_memory.py` and `jarvis_events.py` (`$REBUILT_SUPERSEDES`,
`apply-patches.ps1:1487`) — and swaps four others for the split halves in
`backend/rebuilt-patches/`. That is why the run says **126**.

---

## 3. The question that actually matters

Everything above is about `.patch` files. But the reason the owner is stuck is
narrower and more personal than that:

> **His backend is a live, hand-modified program.** It carries edits the patch
> stack cannot reproduce.

Measured: his `jarvis_hud.py` differs from this repository's published base by
exactly two hunks (a 21-line difference at a whole-file level). One of them is
`screen-attach.patch`, which simply has not been in a base snapshot yet. The
other is **not in any patch at all**:

```diff
-            # each with its reason. Never the reason a pass fails.
+            # each with its reason.
+            _auto, _why = {}, ""
             try:
@@
-            except Exception:
-                _auto = {}
+                _why = str((_auto or {}).get("error") or "")
+            except Exception as _exc:
+                _auto, _why = {}, type(_exc).__name__
             _saved = len((_auto or {}).get("saved") or [])
@@
-            if len(out) > _saved:
+            if _why:
+                # Honest errors: a pass that raised did NOT leave its
+                # proposals waiting for review (2026-10-06).
+                print(f"  memory     the learning pass failed ({_why}) - nothing was "
+                      f"saved or carded for it")
+            elif len(out) > _saved:
```

A learning pass that raised now says so instead of reporting proposals waiting
for review. **No patch in `backend/` adds that.** It is hand work, or work that
was never written back into a patch. It is in the live file; it is not in the
published base; and no run of this tool will ever reproduce it.

That is the whole question. **A file on his machine that the patches cannot
reproduce has to be either:** left alone and the patch skipped with a plain
report; backed up and overwritten with the patched version; or shown to him as
a difference and chosen per file.

| | what it costs him |
|---|---|
| **(a) Left alone, patch skipped, plain report** | His hand-edit survives, always. The cost is that the update is **incomplete**: a feature in that patch is not on his machine until he merges it by hand, and he has to read a report to find out. Nothing is lost; something is not gained. |
| **(b) Backed up and overwritten** | The update is **complete and simple** — one command, no reading. The cost is that his hand-edit is **gone from the live file**. It survives only in a `_jarvis-backup-<date>` folder, and he has to notice and re-apply it. If he does not notice, behaviour he added silently stops working. |
| **(c) Shown as a difference, chosen per file** | Nothing is lost and nothing is silent, and he decides with the text in front of him. The cost is **work at every update**: he reads a diff and answers per file, and a long-running update path that asks him questions is one he may stop running. |

**This is the owner's decision, not mine.** It is question 1 in §6, and **he
answered it on 2026-10-08: (b), back it up and overwrite.**

One thing can be said about the choice: **(c) is the only one of the three that
cannot lose his edit and cannot silently omit a feature**, and it is the only
one whose cost falls on us rather than on him. That was a reason to recommend
it, not a reason to take it for him - and he chose (b) with the cost above in
front of him. The recommendation below stands as written; §5's build order is
unchanged by his answer, because the answer is what step 4 acts on.

---

## 4. The approaches, compared honestly

Each answer below is from reading the code and from the measurements above.

### 4.1 A state manifest — a written record of what is on

**What it is.** After a run, write down which patches are on, with a hash of
each patch and of each file it produced. Then "what is on?" is a **read**, not
a rehearsal: no strip, no re-apply, no result gate, and the deadlock of §1
cannot happen because the circular question is never asked.

**What it needs.** A file the owner's folder carries (e.g.
`_jarvis-state.json`), written only after a run that succeeded, listing each
patch's identity and the hash of each resulting file.

**The hard part — bootstrapping, and it is genuinely hard.** A backend that
predates the manifest has no record, and his folder is exactly that case. The
first run still has to answer "what is on?" by guessing, which is the code in
§1 — so **the manifest does not remove the deadlock on the first run; it only
stops it recurring.** For the bootstrap, either:

- the first run must be allowed to be *honest and partial*: write a manifest
  recording only what it can **prove** (by the `#107` proof, patch by patch)
  and mark the rest "unknown", then let him decide about the unknowns; or
- the bootstrap is resolved by taking a fresh snapshot of his folder as the new
  baseline (§4.3), and the manifest starts from there — which is *correct* but
  requires him to accept a snapshot.

Neither is free, and picking one is an owner question (question 2 in §6).

**What it cannot do.** It cannot tell you what a patch *did* if the file has
since changed by hand: a manifest records the hash the patch produced, and a
hand-edit changes that hash. So the manifest answers "has this file changed
since we wrote it?" — which is exactly the signal needed for §3's choice — but
it does not by itself say whether the change was a hand-edit or a later patch
unless the later patch is also in the manifest. A file whose hash matches no
recorded patch output is **drift**, and that is the flag §3 needs.

**Verdict: the right long-term spine**, and the only approach that makes "what
is on?" cheap and truthful — but it does not by itself solve first boot on his
machine, and it should not be sold as if it does.

### 4.2 Three-way apply (`git apply --3way`)

**What it is.** Git's own merge: given the pre-image, the post-image and the
current file, try to merge. It is the standard answer to "the context moved".

**Can it be used here? No, and the reason is measured, not assumed.**
`git apply --3way` requires a **git repository**: it reads the pre-image blobs
out of the object database. Measured:

```
$ git -C "<owner's backend>" rev-parse --show-toplevel
fatal: not a git repository (or any of the parent directories): .git

$ git apply --3way --check backend\tutorials.patch       # in a copy of his folder
error: '--3way' outside a repository

$ git apply --3way --check backend\screen-attach.patch
error: '--3way' outside a repository

$ git apply --3way --check backend\token-file.patch
error: '--3way' outside a repository
```

And the blobs would not be there even inside a repository: of the 128 patches,
**exactly one** (`thinking.patch`) carries the `index <a>..<b>` line that names
pre-image and post-image objects. The other 127 carry no object names at all,
so there is nothing for `--3way` to look up.

**What it would need.** Making his backend a git repository, *and* having the
pre-image of every patch committed as a blob. The pre-images are reconstructible
in principle (a patch's `-` lines plus its context describe them), but building
that object database is a new piece of machinery, not a flag.

**What it cannot do.** Even with the machinery, `--3way` can leave **conflict
markers in a live Python file**. The script deliberately refuses this today —
`apply-patches.ps1:2195`, `--3way is deliberately absent. It can leave conflict
markers in a working Python file, which turns "the patch did not apply" into
"the backend will not start and the error is a syntax error on line 900".` That
judgement is right and should survive any redesign: `--3way` is a tool for a
tree you can afford to break, and this is the program the owner runs.

**Verdict: not available as written, and not desirable on a live tree even if
it were.** Worth revisiting only as an *inner* step that produces a candidate
merged file **off to the side** — never in place.

### 4.3 Staging from the shipped base (`jarvis-backend/`)

**What it is.** Instead of stripping the live copy, build the target state
from `jarvis-backend/` — the snapshot published 2026-10-06 — and copy the
result over.

**What it needs — and the catch is decisive.** `jarvis-backend/` is the only
complete copy of this program that exists anywhere public. Measured: the
patches name **7 distinct target files** —
`jarvis_events.py`, `jarvis_extract.py`, `jarvis_gate.py`, `jarvis_hud.py`,
`jarvis_memory.py`, `jarvis_models.py`, `jarvis_skills.py` — and under
`backend/` only **two** of them exist. The other five exist **only** in
`jarvis-backend/`. So `backend/` alone cannot even describe a backend, and
`jarvis-backend/` is what a stranger runs.

**But the base is a snapshot, not a source of truth, and it is already stale.**
Measured against the owner's live folder, LF-normalised:

| file | live lines | base lines | same? |
|---|---|---|---|
| `jarvis_hud.py` | 6544 | 6523 | **no** (−21) |
| `jarvis_gate.py` | 1973 | 1964 | **no** (−9) |
| `jarvis_extract.py` | 840 | 840 | yes |
| `jarvis_models.py` | 1319 | 1319 | yes |
| `jarvis_skills.py` | 896 | 896 | yes |
| `jarvis_memory.py` | 5245 | 5245 | yes |
| `jarvis_events.py` | 981 | 981 | yes |

The gap is not drift in the bad sense — it is the base being a **2026-10-06
photograph** and `screen-attach.patch` being decided on 2026-10-07, plus the
hand-edit in §3. Which means:

- **Staging from the base would silently drop `screen-attach.patch`**, and it
  is the newest feature in the list.
- **`jarvis-backend/README.md` is now wrong about the patcher.** It says
  "`apply-patches.ps1` changes nothing here, and that is the correct result …
  exit 0". Measured today, against a copy of that folder:

```
Rehearsing all 126 on a copy first.
  ...
error: patch failed: jarvis_hud.py:6506
error: jarvis_hud.py: patch does not apply
...
  1. 1 patch(es) will not apply to your files as they are: screen-attach.patch.
```

  `exit=1`, and `jarvis_hud.py`'s SHA-256 unchanged. The script is right and
  the README is out of date; the base is one patch behind.

**What it cannot do.** It cannot be the source of truth without becoming a
regenerated artefact — and **nothing regenerates it**. Its own README lists
this as known follow-up 8: "The base is not regenerated by a script. The rule
is in 'The exact rule, so it can be re-taken' above and was followed by hand."
A hand-taken snapshot that is already one patch stale, with five files that
exist nowhere else, is a copy of the truth, not the truth.

**Verdict: real, and it is the right thing to build *on* — not to trust
blindly.** Using it as the staging tree is a genuinely good idea (§5). Treating
it as the *definition* of the owner's install is not: it is a snapshot from
2026-10-06 that is already one patch behind, and it differs from his file in two
places by design (§3's hand-edit and README's four removed dead lines), and the
only thing that would fix that is regenerating it — which is the same "keep two
copies in step" problem that `test_base_matches_repo.py` already exists to
police.

### 4.4 Retiring the patch stack entirely

**What it is.** Stop shipping patches. Ship the base. The owner's update
becomes "copy this folder over mine".

**Is it a real option or a trap? On the evidence: a trap, for now — but the
evidence is closer than the phrasing suggests, and it points at a real path.**

*The trap, measured:*

1. **The base is not the stack's output, and the repository says so.**
   `test_base_matches_repo.py`'s own docstring: "It cannot prove the base is
   the state the patch stack describes. Reversing the stack off the base stops
   at `approval-notice.patch`… So the base is checked against THIS
   REPOSITORY's copies, never against the patch stack." And running the patcher
   against a copy of the base refuses at `screen-attach.patch`, as above.
2. **The base is deliberately not the owner's file.** `jarvis-backend/README.md`
   records one deliberate difference — four dead duplicate dict entries removed
   from `jarvis_gate.py`, which the owner's live file still carries. A
   retirement plan has to decide which of the two is canonical for those four
   lines, and today they disagree **by design**.
3. **The base is one patch behind the list.** `screen-attach.patch` (2026-10-07)
   is not in a 2026-10-06 snapshot.
4. **Five of the seven target files are in the base and nowhere else.** So the
   patch stack can never be validated against anything but his disk. That is an
   argument *for* retirement, but it is also why retiring is not a mechanical
   change: after retirement, `backend/` becomes a set of documents about the
   past, and `test_base_matches_repo.py`'s job (keep the two copies in step)
   shrinks to keeping the base in step with itself — which is no job at all.

*Where it stops being a trap, honestly:*

The measured fact that **94 of the 128 patches already have every added line
present somewhere in `jarvis-backend/`** shows the base is not a pristine
pre-patch tree that the stack builds from — it is the *result*. The patches
overlap the base heavily; the base is what the stack produces, refreshed by
hand. If the base were regenerated by a script from the owner's folder on every
release, "retire the patches" would become a real and much simpler design.

**Verdict: not a trap in principle — a trap as the repository stands today,
because the base is hand-taken, one patch stale, and deliberately differs from
his file.** The honest version of this option is not "delete the patches"; it
is **"make the base regenerable, then reconsider"**, which is build step 3 in
§5.

---

## 5. Recommendation and build order

**Recommendation (marked as mine, not the owner's): keep the patch stack for
now, add a state manifest, and make the base regenerable — but decide §3 first,
because every one of those steps is shaped by the answer.**

The reasoning: the deadlock is a **strategy** bug, and a manifest removes the
strategy. The base cannot replace the stack until it is regenerable, and
regenerating it is exactly what produces trustworthy manifests. So the two work
together, and neither requires the owner to accept losing a hand-edit before
he has said what should happen to one.

Each step below is small enough to verify on its own, and **none of them
touches the owner's live files until the step that is specifically about doing
so.**

1. **Write down the classification a run reaches, in a machine-readable form.**
   Extend the rehearsal's report to emit, per patch, one of: *taken off*,
   *taken off (older text)*, *on but unstrippable*, *not recognised*. Today
   that information is only in prose. **Verify:** run against a copy and diff
   the classification against the JSON emitted here; they must agree patch for
   patch. No behaviour change, no file touched.

2. **Write the manifest.** After a run that finishes, write
   `_jarvis-state.json` beside the backend: each patch's file hash, and the
   hash of each `.py` it produced. **Verify:** run twice on a copy — the second
   run must read the manifest and need no rehearsal at all; and hand-edit one
   `.py` in the copy and confirm the next run reports that file as drift, by
   name. Still nothing of the owner's.

3. **Make the base regenerable, and make its staleness a failure.** One script
   that re-takes `jarvis-backend/` from a given backend folder, and a check
   that fails when it differs. `jarvis-backend/README.md`'s follow-up 8 asks
   for exactly this. **Verify:** regenerate from a copy of the owner's folder
   and confirm `test_base_matches_repo.py` still passes; then confirm the
   patcher runs against that regenerated base and reaches the same place as
   against his folder. *This is the step that tests §4.4 properly, and it may
   well be the step that makes retirement right.*

4. **Then, and only then, act on §3.** **The owner answered §3 on 2026-10-08:
(b), back up and overwrite** (§6, question 1, for the backup's name and place
and what he is told). So this step is now a fixed behaviour rather than a
choice: when the manifest says a file is drift, copy his version into
`_jarvis-backup-<date>`, put the patched version in its place, and say so by
name. **Verify:** a copy of his folder, with the hand-edit of §3 deliberately
present, must produce that behaviour - the backup byte-identical to the file as
it was, the patched version in place afterwards, and the file he was told about
named in the run's own output.

5. **Fix the one real defect found on the way.** Where the script decides a
   patch is "already on" it reaches that verdict by *failing to put it on*
   (`apply-patches.ps1:2801`), which is not proof that the work is there — §2
   measured four patches re-applied on top of themselves after exactly this
   path. The result gate catches it today. Before the gate is relaxed or the
   strategy is replaced, this verdict must be obtained **before** anything is
   applied, not after. **Verify:** a test whose expected answer is "left alone"
   must answer the same way whether the patch would have applied or not.

---

## 6. The owner's questions

### Answered

**1. When a file on your PC has been edited by hand and the patches cannot
reproduce it, what should happen to it? — ANSWERED 2026-10-08: back it up and
overwrite.** The owner's own words: **"Back it up and overwrite"**. He did not
choose "show me the difference per file" and did not choose "leave it and
report the skip", so the updater does not do either of those for this case.

What that commits the updater to, concretely:

- **The backup.** Before a file that the patches cannot reproduce is replaced,
  the owner's own copy is **copied**, byte for byte, into a folder named
  `_jarvis-backup-<date>` inside the backend folder - the same name and the
  same place the script already uses for the files it is about to touch
  (`apply-patches.ps1`, step 2), so there is one kind of backup on his machine,
  not two. Nothing is deleted from it and old backup folders are not cleaned up
  by the tool.
- **The overwrite.** The patched version then replaces the file, so the run's
  result carries every patch in the list. The update is **complete and
  simple** - one command, no diff to read.
- **How he is told.** He must not have to notice a folder. So the update
  **says so in its own output, by name**: which file was hand-edited, that its
  copy is in `_jarvis-backup-<date>`, and that the behaviour his edit added is
  **no longer in the live file until he puts it back**. A run that overwrote
  something of his does not end as a plain success and does not stay silent
  about it. (The exact wording and where it is printed belong to build step 4,
  with the manifest that detects the drift.)
- **What it costs him, written down here because it is real:** his hand-edit is
  gone from the live file, and if he does not put it back, behaviour he added
  silently stops working. That is the cost he accepted on 2026-10-08.

**4. Should a run that had to skip patches still report success? — ANSWERED
2026-10-09: no, it always ends as "not finished" until the skipped list has
been read.** The owner's own words: **"always end as 'not finished' until I
have seen the skipped list"**. He did not choose "report success and list the
skips underneath", so the updater does not do that.

What that commits the updater to, concretely:

- **A run that skipped anything does not end as a plain success.** Not a
  success with a note under it, and not a success whose detail is left in a
  file: the run's own result must say plainly that it is **not finished**.
- **It names the patches it skipped**, one by one, in its own output - the
  owner should not have to open a JSON file to find out what is missing.
- **It leaves the decision to him.** Having read the list, he decides whether
  to run it again (or deal with a patch by hand). The tool does not retry by
  itself and does not treat the skip as settled.
- **The rule this makes: "finished" means "everything went on".** No patch is
  ever silently counted as on when it is not - which is the failure mode §8
  calls the one that hurts most.
- **Where the skipped list comes from: build step 1, already built.** A run
  with `-StateJson <path>` writes one entry per patch (§9). The two verdicts
  that mean "skipped" are **`not-recognised`** (no text of the patch came off
  and the content check did not find its work either) and
  **`on-but-unstrippable`** (its work is measured as present, and no text of
  the patch can take it off the files this run found). That record is what the
  run's own words must be built from, and it exists even when the result gate
  refuses - which is exactly when the list is worth most.
- **What it costs him, written down here because it is real:** a run that got
  most of the way now still reports itself as **not finished**, so an update is
  never declared done by the tool alone. He reads the skipped list and decides
  before running it again. That is the cost he accepted on 2026-10-09, and it
  is the trade he asked for: less silence, a little more reading.

**One thing to fix on the way, so the rule means what it says.** The two
verdicts above are not yet the whole story of a skip on today's files. §9
measured `tutorials.patch` and `screen-attach.patch` failing the **re-apply**
and being reported in the script's prose as `already on … left as it is`, while
the run's own record calls them `on-but-unstrippable` - and §9's own note says
the skip in the re-apply loop is not what would fix the four doubled patches.
So "skipped" cannot be read off today's prose line; it has to be read off the
`-StateJson` classification, and step 5's honest "left alone" verdict (obtained
**before** anything is applied, §5 step 5) is what makes that list complete.
**This decision does not relax the result gate**, and it does not change step
5's order: relaxing the gate before step 5 is still forbidden (§8).

### Still open

4. **Held over, because it needs question 1's answer first:** should a run that
   had to skip patches still report success, or must it always end as "not
   finished" until you have looked at the skipped list?

   **Still open as of 2026-10-09.** It was not asked again and it was not
   answered, so step 2 does not answer it: a run that had to skip patches still
   reports exactly what it reported before, and the record does not change that.

### Answered 2026-10-09

**2. For the first run, which has no record of what is on your PC yet, may the
tool take a fresh snapshot of your current files as the new starting point? —
ANSWERED 2026-10-09: yes — snapshot first, then tell me what it could not
match.** The owner's own words: **"Yes — snapshot first, then tell me what it
could not match."** He did not choose "work it out from the files as they are".

What that commits the updater to, concretely (and step 2 is built to exactly
this shape - §10):

- **The snapshot writes down hashes only, and modifies nothing of his.** The
  first run that finishes records what his files hold at that moment as the
  baseline: each patch's own text hash, and the hash of each `.py` this run left
  in place. His files are not copied, rewritten or moved by this step. Step 4 is
  still the step that backs up and overwrites, and it is not built.
- **What it could not match is named, in the run's own words.** A file whose
  content cannot be tied to a patch this run applied - a patch the run could not
  recognise, a file two patches of the list both write - is recorded as a hash
  the record **cannot speak for**, and is listed by name when the record is
  written and again on every later run that reads it. It is never blessed as
  verified. That distinction is the whole of the answer: the baseline is honest
  about its own blind spots, so §8's "silence" failure mode - a report that
  reads clean while something is missing - cannot come from here.
- **A run that does not finish writes no record at all.** A refused run (and the
  owner's machine still refuses, §9) leaves the baseline a good run wrote
  exactly as it was, so a hand-edit recorded by that baseline is not forgotten
  on the next run.

**3. `jarvis-backend/` is the only complete copy of your program in the
repository, and it is one patch behind your PC (it is missing
`screen-attach.patch`) and deliberately differs from your `jarvis_gate.py`
in four dead lines. Should it be regenerated from your folder? — ANSWERED
2026-10-09: yes — regenerate `jarvis-backend/` and make it a check that fails
when it drifts.** That is **build step 3** of §5, and the answer means step 3
is now unblocked. **Step 2 did not do it**: step 3 is a script that re-takes
`jarvis-backend/` from a given backend folder plus a check that fails when the
two differ, and nothing in this pass touched `jarvis-backend/` at all.

---

## 7. What this note could not determine

- **Why pass 2's headline count does not match the patch list.** Pass 2 prints
  124 `ok` and 2 "already on" against a 126-entry list. The per-patch evidence
  in §2 is solid and is what this note rests on, but I did not reconcile the
  totals, and I am not claiming the extra two are anything in particular.
- **The doubled result state, directly.** §2 measures the four patches being
  re-applied `git-ok=True` on a tree that already carries their work, and reads
  the code path that would drop them from the real run. It does not produce the
  exact pre-gate tree byte for byte: step 3 has no exit that keeps its scratch
  folder, and a hand-built replica of step 2 diverged from the script's own
  split-patch handling (`$UsingRebuilt`, `apply-patches.ps1:1818`). What is
  asserted is the measured re-application, not a diff of the result.
- **Whether the four patches, applied twice, produce duplicated code** rather
  than a harmless second application. They applied cleanly; what the file looks
  like afterwards was not captured, because the only run that gets there
  continues into step 3 and refuses.
- **How many patches the `Test-PatchOnBackend` rescue would catch on a
  different backend.** On today's state it catches none
  (`INSTR_ALREADYON_COUNT=0`); the 80 "left exactly as they are" that `#107`
  reports are not reproducible from the current files.
- **Whether `jarvis_gate.py`'s 9-line gap is the same story. It is, and it was
  diffed:** the base has **2 fewer** lines (the dead `append_logseq_journal` and
  `send_email` duplicate dict entries `jarvis-backend/README.md` says were
  deliberately removed) and **7 more** that only live has — `read_web_page` in
  `_TOOL_ACTIONS`, which is `readpage.patch` and has not been in a snapshot
  yet. So both files' gaps are the same two causes: one patch newer than the
  snapshot, plus one deliberate difference.
- **Anything about a Windows PowerShell 5.1 run.** Every measurement here used
  PowerShell 7 (`pwsh`), which is what the script's own tests use.
- **A test pinning these numbers, and why one was not written.** The brief
  asked for one "only if it is honest". The two deadlocking patches and the
  four doubled ones are facts about **this PC's folder**, which CI does not
  have; a test that skips without it proves nothing, and one that hard-codes
  `122`/`126`/`4` would fail on the next patch added — a test that breaks for
  the wrong reason is worse than none. Pinning the *gate's* behaviour is
  genuinely valuable and is what build step 5 asks for, but writing it well
  means first getting the re-apply to expose a "left alone" verdict **before**
  it applies — which is a code change, and this pass is deliberately not one.
  **Built since (2026-10-08, §9):** build step 1's own test,
  `test_apply_outcomes.py`'s `t_mini_state_json_classifies_every_patch`, pins the
  *recording* on a made-up backend, not these numbers — the four numbers above
  still have no test, exactly as argued here.

## 8. Risk

- **Nothing of the owner's was changed.** His backend folder was read; every
  script run used a copy in `%TEMP%`; `-FixLineEndings` was never passed
  against his folder; his running Jarvis was not stopped. The one run that hit
  the "Jarvis is still running" guard was `-Revert`, and it correctly refused
  and changed nothing.
- **The real risk is in acting on this note too early.** The temptation is to
  "just relax the result gate" — it is the line that refuses, and removing it
  makes the run finish. That would be wrong: §2 shows the gate is currently the
  only thing standing between the owner and a backend carrying a doubly-applied
  patch. **Do not relax the gate before step 5.**
- **The second risk is silence.** Whichever of §3's three choices is taken, the
  failure mode that hurts most is an update that reports success while a
  hand-edit or a feature is quietly missing. Any of the three is better than
  that, which is why the choice is worth making explicitly rather than
  defaulting.

---

## 9. Build step 1, built (2026-10-08)

**Step 1 of §5 is done: the classification a run reaches is now emitted in a
machine-readable form.** The switch is `-StateJson <path>`; with it, a run
writes a JSON file with one entry per patch in the list:

| verdict | what it means |
|---|---|
| `taken-off` | the run found this patch's work on the files and took it off, to put the current text back on |
| `taken-off-older-text` | the same, but the text that came off was an **older committed version** of the patch (`backend/patch-history`), named in the entry |
| `on-but-unstrippable` | the work is measured as present, and no text of the patch can take it off the files this run found |
| `not-recognised` | neither: no text of it came off, and the content check did not find its work |

The file also carries a **totals** object, so a count can be checked without
recounting the list. Without `-StateJson` nothing is written and nothing about
the run changes - the switch is opt-in, and the default path is byte-identical
to before. The JSON is written **even when the result gate refuses**, which is
the case on the owner's machine: a refusal is exactly when a record of the
classification is worth most.

Measured on a copy of the owner's folder with this switch on, the counts are
**taken-off 122, taken-off-older-text 2, on-but-unstrippable 2,
not-recognised 0** - 126 in total, and they agree patch for patch with the
script's own prose (`122 of these are already on your backend` / `2 of those are
an OLDER version` / the two `already on … left as it is` lines). Without
`-StateJson` nothing is written and nothing about the run changes - the switch is
opt-in, and the default path is byte-identical to before. The JSON is written
**even when the result gate refuses**, which is the case on the owner's machine:
a refusal is exactly when a record of the classification is worth most.

Two things this step measured, on copies, that change what step 5 is:

- **The four doubled patches are worse than §2 describes, and the strip does not
  name them.** `Test-PatchOnBackend` is what §2 says decides "already on, leave
  it alone"; instrumenting its calls on today's state (a throwaway copy of the
  script, on a copy of the backend) gives **`False` for all four** - `tasks`,
  `accounts`, `chatbot-limits`, `chatbot-limits-hud` - and `True` only for
  `screen-attach`. So `$alreadyOn` does not hold those four, and the re-apply
  loop **does** apply them: instrumenting the loop prints `apply … True` for
  `tasks`, `accounts` and `chatbot-limits`, i.e. the work goes on a second time.
  They are recorded here as `not-recognised` **only when the re-apply fails**;
  measured, all four re-apply `ok`, so on today's state they are counted
  `taken-off` and the doubling is invisible in this file. **The classification
  alone does not fix them, and the skip in the re-apply loop is not what would**;
  step 5 must obtain a "left alone" verdict *before* anything is applied, exactly
  as it says.
- **`tutorials.patch` and `screen-attach.patch` are the pair the gate refuses
  over, and they come off the strip but will not go back on.** Measured: both
  are taken off the copy by the strip (they are inside the `122`), and in the
  re-apply both fail forward and reach "already on … left as it is" - the
  patches applied before them have rewritten the context they land in. The
  strip therefore says "taken off" while the state the run would leave does not
  carry them, which is exactly the half-applied backend the gate refuses. They
  are recorded `on-but-unstrippable`, and the result gate still refuses
  (`exit=1`, `screen-attach.patch cannot be taken off the state this run would
  leave`) - **the gate's behaviour is unchanged.**

One rule the recording had to settle, because a patch can reach both sources:
the strip and the re-apply disagree, and "last one wins" is wrong in both
directions. `taken-off-older-text` is never replaced by a plain `taken-off`
(cloud-one-turn and ollama-direct were, in the first version of this, which
threw away the only record that what was on the files was an older text), and
`on-but-unstrippable` beats `taken-off` (tutorials and screen-attach came off
cleanly and then would not go back on). Both are in `Set-PatchClass`'s comment,
with the measurements.

What step 1 does **not** do, plainly: it does not back anything up, it does not
overwrite anything, and it does not detect a hand-edit. §3's test - the backup
byte-identical to the file as it was, the patched version in place afterwards,
the owner told by name - needs step 2's manifest (a hand-edit is *drift*: a hash
that matches no patch's output) and is built in step 4. Nothing about the result
gate changed, which is deliberate: §8 says do not relax it before step 5, and it
is still the only thing standing between the owner and a backend carrying a
doubly-applied patch.

---

## 10. Build step 2, built (2026-10-09)

**Step 2 of §5 is done: a run that finishes writes `_jarvis-state.json` beside
the backend, and a later run reads it instead of rehearsing.** The switch is
`-Manifest <path>`, defaulting to `_jarvis-state.json` in the backend folder;
`-Manifest none` turns the whole step off, exactly as omitting `-StateJson`
turns step 1 off. Nothing about the default path changed when the switch is off,
and the result gate is untouched (§8, §9).

### What is in the file

| field | what it is |
|---|---|
| `schema` | `jarvis-updater-manifest/1` |
| `run` | `baseline` (the first run that wrote it - the snapshot the owner chose on 2026-10-09), `checked` (a run that read a usable record first), or `partial` |
| `patchList` | this run's patch list, in order - what makes a record usable for a run |
| `patches[]` | one entry per patch of the list: `Patch`, its own text's `Sha256`, and the `Verdict` this run reached (the four §9 words) |
| `files` | every `.py` beside the backend: `sha256` (over the text with CRLF made LF), `patch` (the one patch of the list whose header names it and which this run applied), `verified` (true only when there is exactly one such patch) |
| `unmatched[]` | every patch of the list this run could not apply, by name and verdict |

### The rules it follows, and why

- **It is read before the rehearsal, and only used when it covers the whole
  list.** `patchList` must equal this run's list, in order; every patch of the
  list must be named by some `files[].patch`; and every recorded hash must equal
  the file on disk. Any of those failing means the rehearsal runs exactly as
  before - no strip, re-apply or gate is skipped on a guess.
- **A file two patches of the list both write is never called verified.** Its
  hash cannot say which of the two put the text there, so a hand-edit in it
  would read as a clean record. It is named instead, and the rehearsal runs.
  Today that is `jarvis_gate.py` and `jarvis_hud.py` (several patches each), so
  the fast path is exercised only where every file a patch writes is its own.
- **Drift is named, and the record is left alone.** A recorded file whose hash
  has moved is printed by name, the run goes on to the rehearsal, and the record
  is **not** rewritten - so the hand-edit is named again on the next run instead
  of being blessed as the new baseline. Writing the new baseline instead would
  have made §4.1's drift signal disappear after one run, which is the silence
  §8 warns about.
- **Only a run that finished writes.** The write happens after the patches, the
  shipped modules and the settings file, and a run that refused or stopped part
  way never reaches it. The tests below the write cannot change a `.py` file, so
  the record is still true when they have finished.
- **The first run's baseline is a snapshot of hashes, not of files.** Nothing of
  the owner's is copied or modified (that is step 4, still not built), and every
  file it could not tie to a patch is named in the run's own words and again on
  the next run that reads the record.

### What it does NOT do

It does not relax the result gate, and it does not back anything up or overwrite
anything. On the owner's own folder a run still refuses (§9), so **his machine
still has no `_jarvis-state.json`**: the record is written only after a finish,
and the first finish is waiting on the patch-anchoring problem `prompt-coach.patch`
has on his files, which is the same blocker commit `4bf3d19e8` recorded. Step 2
is therefore finished and proven on copies, and it is **not yet running on his
PC** - which is also why it cannot be the thing that fixes his update.

### How it was verified

`backend/test_apply_outcomes.py` gained four checks, all of which fail on the
script without this change:

- `t_mini_manifest_is_written_and_names_the_files` - the record's shape, above.
- `t_mini_second_run_needs_no_rehearsal` - **run it twice on a copy**: the
  second run prints "No rehearsal was needed", prints no strip and no re-apply,
  changes not one byte of the backend, and re-checks the real files and the
  shipped modules anyway. A record from a different patch list, and no record at
  all, both fall back to the rehearsal (so "no rehearsal" is not satisfied by
  never rehearsing).
- `t_mini_a_hand_edit_is_drift_by_name` - **hand-edit one `.py` in the copy**:
  the next run names it as changed, leaves the edit's bytes alone, leaves the
  record alone, and names it again on a third run. Putting the edit back makes
  the record usable again, with no drift reported.
- `t_mini_unmatched_files_are_named_not_blessed` - a `.py` no patch of the list
  writes is recorded by hash with `patch: ""` and `verified: false`, is named in
  the run's own words, and is named again on the next run. A gate refusal writes
  no record at all.

`t_mini_success_and_endings`'s second-run expectation changed from "already
applied" to the record's own wording, because on a backend the record covers the
second run no longer asks the stack that question.


