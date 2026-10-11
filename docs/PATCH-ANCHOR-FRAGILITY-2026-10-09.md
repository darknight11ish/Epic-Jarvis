# The banner anchor: why `screen-attach.patch` keeps breaking, and the fix that lasts

Written 2026-10-09 after an installer rehearsal found that `apply-patches.ps1`
could not run **at all** on the owner's PC. This is the write-up the owner asked
for instead of another one-patch repair: the same breakage has now happened
three times in a day, each time for the same structural reason, and re-anchoring
the patch each time is a treadmill, not a fix.

## What the owner sees

```
FAIL  screen-attach.patch - will not apply
FAIL  1 patch(es) will not apply. NOTHING HAS BEEN CHANGED.
```

Nothing is written, and the update stops. The message says the backend file has
"moved on since the patch was written", which is true but not the useful part.

## What is actually wrong

Forty-one patches insert a block into `jarvis_hud.py` immediately before the
same line:

```python
    # Before the main socket, so the banner lists every address together.
```

Each one names the thing above that comment as its **leading context**. In list
order that works, because each patch's leading context is the tail of the block
the patch before it wrote — a chain. `screen-attach.patch` names
`tutorials.patch`'s two print lines:

```python
        print(f"  tutorials  NOT ON (...) - the tutorials and FAQ are off")
        print("             until jarvis_tutorials.py is back: run apply-patches.ps1 again")
    # Before the main socket, so the banner lists every address together.
```

Those lines really do exist in the published base, at exactly the line numbers
the patch names (6506–6508). But `chatbot-limits-hud.patch` is applied **after**
`tutorials.patch` and inserts its own block in front of the same comment, so by
the time `screen-attach.patch` runs the line above the comment is chatbot
money's, and the three lines are no longer contiguous. The patch's *added* lines
were always correct; only its neighbour was stale.

## Why it looked fine for so long

The rehearsal runs the walk twice, and only the second one fails:

1. **A backend as it is** — `screen-attach.patch` counts as `already on`, so its
   context is never tested.
2. **The repair pass** — "take those off, newest first, then put all N back on
   in order". This runs when the backend carries an **older version of any
   patch**, and it is what re-applies from scratch.

The owner's PC carries seven older patch versions, so the owner always gets pass
two — the one that fails. A checkout without older patches never sees it.

## Why re-anchoring does not fix it

Measured, not argued. On 2026-10-09:

- The patch was re-anchored against the neighbourhood the walk really leaves,
  proved by a full rehearsal (`ok screen-attach.patch`, "all 128 patches are
  on"), and all four affected suites went green.
- **Within the hour**, main had grown from 128 to 131 patches. Three new ones
  (`attention-settings`, `limits-settings`, `handoff-mode`) also insert before
  that comment, so the neighbour was stale again and the same failure returned.

So the anchor is not a value that can be corrected; it is a **position in a
chain that other people keep inserting into**. Every patch added at that comment
breaks whichever patch was last there. The `test_screen_attach.py` rule that
"screen-attach is last, bar the ones written after it" is exactly the
acknowledgement of this — and it is not enough, because "bar the ones written
after" is a list somebody has to remember to extend.

## The proposed fix - NOT VERIFIED, and do not approve it on this document alone

**Read this first.** The sentinel below is a PROPOSAL. Its load-bearing
claim - that a hunk whose only context is the sentinel applies no matter what
precedes it - has NOT been demonstrated. An attempt to prove it on a synthetic
file failed in every case, including a single patch against a clean file with
nothing else in it:

```
sentinel-anchored patch, applied in a DIFFERENT ORDER than written:
  written first                 : FAILED  error: hud.py: patch does not apply
  reverse of writing            : FAILED  error: hud.py: patch does not apply
  new one inserted in the middle: FAILED  error: hud.py: patch does not apply
  new one first                 : FAILED  error: hud.py: patch does not apply
claim holds: False
```

A failure in the trivial case points at the test harness rather than at the
claim, and the harness bug was not isolated. So this is genuinely unknown:
neither confirmed nor refuted. **Nobody should change 41 patches on the strength
of the argument below until someone has made that test pass.** What IS
established is the mechanism and the treadmill, above - those are observed.


**Give the anchor a sentinel that no patch competes for, and make every patch
at that anchor use the sentinel alone as context.**

1. One patch adds a single marker line, once, above the socket comment:

   ```python
       # jarvis: install blocks above this line, in patch-list order.
       # Before the main socket, so the banner lists every address together.
   ```

2. Every patch that installs a banner block anchors **only** on that marker,
   as *trailing* context, with no leading context:

   ```
   @@ -NNNN,1 +NNNN,17 @@
        # jarvis: install blocks above this line, in patch-list order.
   +    ...the block...
   ```

   A hunk with trailing context only applies wherever the marker is, so the
   **order of these patches stops mattering** and adding a new one cannot break
   an existing one. This is the whole point: the failure mode disappears rather
   than moving.

3. A test enforces it, because a convention nobody checks is how this happened:
   every patch whose added lines contain `_loopback_companion`, `# Before the
   main socket`, or an `install(Handler` banner block must use the sentinel as
   its only context line. That turns the next person's mistake into a clear CI
   failure instead of an installer that refuses on the owner's PC.

**Cost.** The 41 existing patches each need their context line changed once —
mechanical, and the same single-line edit every time. The stand-in walk
(`backend/_stack.py`, and `test_installed_stand_in.py`'s ratchet) will move when
it does, and that pin is already the mechanism for recording exactly this kind
of change honestly.

**The longer cure, if the owner wants it:** stop patching the banner at all.
The install blocks are enumerable — module name, call, message — so they could
be **generated** into `jarvis_hud.py` from one list, the way
`gen_menu_cases.py` generates both apps' menu catalogues. That removes the
anchor, the chain and the ordering rule together. It is a bigger change and
would want its own design note; the sentinel is the small version that can be
done now.

## The second blocker I reported, and the correction

While rehearsing, this appeared alongside the anchor failure:

```
FAIL  handoff-mode.patch - will not apply
error: patch fragment without header at handoff-mode.patch:12: @@ -840,4 +841,14 @@
```

I called it a live blocker in the first version of this document. **That was
true when the rehearsal observed it and is not true now.** It was fixed in
`cb294e04` ("one wrong integer in a hunk header blocked every install",
2026-10-09, merged as PR #142), which landed *after* the `main` that rehearsal
ran against. Any checkout of current `main` carries the fixed text.

Two details from the diagnosis worth keeping, because the error misleads:

- **The line number in the message is not the defect.** Git blamed line 12; the
  real fault was one integer on **line 3**, where `@@ -190,6 +190,7 @@`
  under-claimed by one line (the body supplies 7 old and 8 new). Fixing line 12
  instead still failed identically. Editing the header on line 3 to
  `@@ -190,7 +190,8 @@` was the whole repair, and the merged diff is exactly that
  one character per side.
- **A test now catches this class of defect.** `backend/test_patch_wellformed.py`
  runs `git apply --numstat` over every name in `$PATCHES` and every rebuilt
  half, and was added by the same fix. Before it, nothing did:
  `test_apply_outcomes.py` drives the installer with two fake one-hunk patches,
  and the feature's own suite asserted only that the patch text *contains*
  certain strings - which a malformed patch contains just as well.

That second point strengthens the case for the proposal above: a convention
without a test is exactly how a one-character defect blocked every install.

## The third report, and the correction: `prompt-coach.patch` and `3478`

Reported 2026-10-10 as a live blocker of the same kind, with the same wording:

```
FAIL  prompt-coach.patch - will not apply
error: patch failed: jarvis_hud.py:3478
```

**It is not the anchor, and it is not live.** Two independent measurements say
so, and both are worth keeping, because this report cost an agent a whole
attempt and the number in it is the thing that misleads.

**1. That exact failure was real on 2026-10-08 and was fixed the same day.**
It is the commit message of `45175c86` ("prompt-coach.patch: anchor the POST
hunk so it applies after tasks.patch"), which is on `main` — and it was fixed
by this document's own method: the POST hunk was re-anchored onto
`tasks.patch`'s last lines, where it really lands, with the added lines left
byte for byte. Both patches inserted at the same point and both named the same
neighbour, so whichever went second failed; the anchor moved down one block and
`@@ -3478,7 +3478,32 @@` became `@@ -3544,6 +3544,31 @@`. **`3478` is the pre-fix header.** It
survives today in exactly one place — `backend/patch-history/prompt-coach/f56e6ab.patch`,
the archived older text — so a `git apply` of *that* file is the only thing
that still prints 3478. Grepping the owner's own `_jarvis-logs` finds `3478`
in **none** of them, and `FAIL  prompt-coach.patch` in none either.

**2. The owner's own newest log ran the repair pass and passed.**
`apply-patches-2026-10-09-214407.txt` (his file, his machine):

```
  not onto the files as they are   prompt-coach.patch
132 of these are already on your backend from an earlier run.
Rehearsing again: take those off, newest first, then put all 133 back on in order.
  ok    prompt-coach.patch
```

and it ends `Checked again on the real files: all 133 patches are on.` /
`DONE - no problems`. Re-measured here on a fresh GUID copy of his live folder:
stripping all 133 with `-Revert` and then applying all 133 forward in list
order from the shipped base ends `EXIT=0` with `ok prompt-coach.patch` at
line 140 and line 277. The repair pass is the pass that fails first, and it
passes.

### What the report really was: the patch's own line endings

The one real defect next to this patch is that `prompt-coach.patch` was the
**only one of 135 patches stored with CRLF endings**, and it arrived in that
state with `45175c86` — a Windows editor wrote the file, and `.gitattributes`'
`*.patch -text` (deliberately "no conversion, ever") meant nothing normalised
it. Measured on a copy of the owner's live `jarvis_hud.py`:

```
git apply --check          backend/prompt-coach.patch   -> exit 1
    error: patch failed: jarvis_hud.py:2457
git apply --reverse --check backend/prompt-coach.patch  -> exit 1
    error: patch failed: jarvis_hud.py:2457
the same text with LF endings:
git apply --reverse --check <the LF copy>               -> exit 0
```

Both directions failing against a file that already carries the patch is
*indistinguishable*, from the outside, from a stale anchor — which is how this
report was born, and why `.gitattributes`' own warning ("the error it prints
says nothing about line endings, so the natural conclusion is that the patch is
wrong rather than that git edited it in transit") belongs in a test and not
only in a comment. The patch is now stored LF, and
`test_patch_wellformed.py` fails if any patch is stored with CRLF again — the
half `test_patch_history.py` already held for the archived versions.

Nothing else moved: not one byte of content changed (`git diff
--ignore-cr-at-eol` is empty), the installer normalised the file to LF before
applying it anyway (`Copy-AsLf`) and the manifest hashes that same LF copy, so
no run's behaviour or record changes.

## What is proven, and what is not

- **Proven:** the failure reproduces deterministically in the repair pass; the
  six-line `chatbot money` neighbourhood is what the walk really leaves; a
  re-anchor makes the whole walk pass with "all 128 patches are on"; and
  `test_installed_stand_in` 15/0, `test_retrieve_count` 62/0,
  `test_screen_attach` 57/0, `test_patch_history` 24/0 with it.
- **Not proven:** the sentinel proposal has not been built. It is a small change
  with a large blast radius (41 patches), so it is the owner's call, not a
  thing to do quietly.
- **Not claimed:** that re-anchoring again would not work. It would — for a few
  hours.
