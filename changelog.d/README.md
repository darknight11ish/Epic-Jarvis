# changelog.d — one bullet per pull request, rolled into `CHANGELOG.md`

**Why this exists.** Every pull request used to append its entry at the top of
`CHANGELOG.md` — one shared place, by construction. Two pull requests therefore
changed the same lines, every merge to `main` turned the rest into CONFLICTS,
and a conflicted pull request gets **no CI at all**; re-clearing one costs a
fresh `frontend` run (about 71 minutes). This directory ends that race.

**What a pull request does instead.** Add ONE file here, named
`YYYY-MM-DD-<slug>.md`, whose whole content is ONE bullet — the same text that
used to go into `CHANGELOG.md`:

```
- **The phone's Galaxy gets a read-only "at a glance" band (2026-10-23).** What changed, and one honest limit.
```

The date in the name decides the order. Do **not** edit `CHANGELOG.md` from a
feature pull request.

**When to roll.** On a quiet `main`, run:

```
py -3 tools/roll_changelog.py --check     # what CI validates on every pull request
py -3 tools/roll_changelog.py --dry-run   # see what would be inserted
py -3 tools/roll_changelog.py             # fold them in and remove the fragments
```

The roll is **deliberate, never automatic**, and it is idempotent. Open ONE
pull request with the roll and nothing else in it — the same shape as the
periodic `docs/README.md` size refresh.

**What is checked, and what is not.** `--check` validates every fragment's name
and shape and that `CHANGELOG.md` still carries its `## Not in a numbered
version yet` heading. It deliberately does not require the fragments to have
been rolled yet, because that would fail the very pull requests this exists for.
`backend/test_roll_changelog.py` proves the roll (newest first, no lost
bullets, idempotent, dry-run writes nothing).
