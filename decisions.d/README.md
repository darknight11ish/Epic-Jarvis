# decisions.d — one dated bullet per pull request, rolled into `docs/DECISIONS.md`

**Why this exists.** Every pull request that recorded an owner decision appended
its entry at the end of `docs/DECISIONS.md` — one shared place, by construction.
Two such pull requests therefore changed the same lines, every merge to `main`
turned the rest into CONFLICTS, and a conflicted pull request gets **no CI at
all**; re-clearing one costs a fresh `frontend` run (about 62 minutes — PR #386
is where it happened last). This is the fix `changelog.d/` has used since
2026-10-23, one file over: Gemini's ruling Q8.

**What a pull request does instead.** Add ONE file here, named
`YYYY-MM-DD-<slug>.md`, whose whole content is ONE dated bullet — the same prose
that used to be appended to `docs/DECISIONS.md`:

```
- **2026-10-28 — A quieter HUD:** What was decided, what it replaced, and what
  it deliberately does not do.
```

The date in the filename decides the order, and it must agree with the date in
the bullet. The bullet wraps like any markdown paragraph — it is one bullet, not
one line — but a blank line inside it is refused, because a blank line ends the
bullet.

**Do not edit `docs/DECISIONS.md` from a feature pull request.** Existing history
stays exactly where it is, untouched; the file is only ever written by the roll
below (and by the one commit that added this mechanism).

**When to roll.** On a quiet `main`, run:

```
py -3 tools/roll_decisions.py --check     # what CI validates on every pull request
py -3 tools/roll_decisions.py --dry-run   # see what would be inserted
py -3 tools/roll_decisions.py             # fold them in and remove the fragments
```

The roll is **deliberate, never automatic**: no workflow runs it, and a feature
pull request must not run it — only this tool's own tests and the person doing
the roll do. Open ONE pull request with the roll and nothing else in it, the same
shape as the periodic `docs/README.md` size refresh. The roll is idempotent.

**Where the roll inserts, and why.** `docs/DECISIONS.md` is chronological,
**oldest first**, so the roll appends at the very END of the file and writes one
roll's bullets **in date order** — oldest of the batch first. `CHANGELOG.md` is
newest-first, so `roll_changelog.py` inserts newest-first; copying that here
would leave every rolled batch running backwards inside a forwards file.

The record carries an anchor heading near its end, exactly this line:

```
## Decisions written as `decisions.d/` fragments, folded in here in date order
```

and `--check` fails if it disappears. It is a canary, not the insertion point:
the roll always appends at the end of the file, so the date order holds even if
somebody appends an entry above it.

**What is checked, and what is not.** `--check` validates every fragment's name,
its bullet shape and that the date in the name matches the date in the bullet,
and that the anchor heading is still there. It deliberately does not require the
fragments to have been rolled yet, because that would fail the very pull requests
this exists for. `backend/test_roll_decisions.py` proves the roll (appended at the
end, date order, no lost bullet, idempotent, dry-run writes nothing, malformed
fragments rejected, two pull requests' fragments never meeting in the same file).

**Claims sources follow the entry.** A `docs/CLAIMS.tsv` row may cite a decision
as `decisions.d/<name>.md:<line>`. When the roll removes that fragment it rewrites
those `source` cells to `docs/DECISIONS.md:<the line the entry now starts on>`,
and touches no other row — so the register keeps pointing at the sentence after
the entry has moved, without anyone re-anchoring it by hand.
