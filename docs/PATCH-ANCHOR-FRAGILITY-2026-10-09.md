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

## The durable fix

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

## One more blocker, unrelated

On the same day, `handoff-mode.patch` on `main` was **malformed**:

```
error: patch fragment without header at handoff-mode.patch:12: @@ -840,4 +841,14 @@
```

A hunk with no `@@` header cannot apply to anything, so this blocks every
install on its own, whatever happens to `screen-attach.patch`. It is a
one-line-class repair by whoever owns that patch, and it should be fixed before
anyone spends more time on the anchor.

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
