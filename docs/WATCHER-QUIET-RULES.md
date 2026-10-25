# The watchers' quiet rules: what may be silent, and what may never be

**Written 2026-10-15.** The design question that stopped work on this, answered.

**Status: a decision on paper. No code.** No line of `jarvis_news.py`,
`jarvis_tellme.py`, `jarvis_schedule.py` or `jarvis_briefing.py` has changed.

---

## The question that stopped it

The work order asked for a quiet rule on the four polling modules: poll, and
**emit nothing when nothing has changed**. It named the token `[SILENT]`.

Work on it stopped, correctly, with this objection:

> `[SILENT]` looks like a Hermes-style **agent response** token, and these four
> are backend **pollers**. Which layer emits `[SILENT]` is a design question I
> could not answer from the brief — and **a half-wired quiet rule suppresses the
> owner's notifications wrongly**, which is the worst outcome available here.

That objection is right, and the answer turns out to be: **none of them, and do
not add the token at all.**

---

## What the four modules actually are

Measured on `main`, not assumed:

- They **return dictionaries**. `jarvis_tellme.check_watch(w) -> dict` (`:574`),
  `check_rule(rule, now) -> dict` (`:754`), `jarvis_watch.report(...) -> dict`
  (`:464`). None of them prints, sends, or speaks.
- **No agent loop calls them.** They are not in the chat turn path; the apps ask
  and render. Nothing here produces a chat turn, so there is no turn for
  `[SILENT]` to be silent *in*.
- **`[SILENT]` does not exist in this repository at all.** A whole-tree search
  finds only the word "silently" in prose and IMAP's `FLAGS.SILENT`. It is not a
  Jarvis convention; importing it would invent one.
- **`notify` in these files is not a notification.** It is a **permission tier**
  — `jarvis_news.py:374`, `jarvis_briefing.py:493`, `jarvis_tellme.py:95` all read
  `tier_of(...) in ("auto", "notify")`. Reading "notify" as "sends a
  notification" is the trap this note exists to prevent.

So `[SILENT]` has **no home**: there is no chat turn, and no layer whose job is
to speak. Adding it would mean inventing a delivery layer to hold a token that
means "do not deliver" — a layer performing a suppression that the app can
already perform by not drawing a card.

---

## The decision

**Split "nothing new" from "I could not tell", and make the second one loud.**

That distinction is the whole design. The work order's rule — *deliver only on a
material change* — is right, but written flat it also suppresses **the failure
case**, and a watcher that has silently stopped working is exactly what the owner
must be told about.

| state | what it means | what happens |
|---|---|---|
| **unchanged** | looked, and nothing is new | **deliver nothing.** The app draws no card. No token, no message |
| **new** | looked, and something is genuinely new | deliver, as today |
| **first look** | no `first_seen` record yet, so everything is "new" | **deliver — once.** Otherwise the first run either floods or hides everything |
| **stale** | the read failed | **deliver, with the reason**, and keep the last-known-good values on screen |
| **broken** | the watcher cannot run at all | **deliver, loudly.** Never silent |

**Background learning stays on by default** (`CLAUDE.md`, amended 2026-09-24), so
being quiet is about **not interrupting**, never about **not looking**.

---

## Where each rule goes

**Nothing new goes in the four pollers.** The change-detection already exists and
is already the right shape. `jarvis_watch.py:29-34` states the rule outright:

> NEW AND UPDATED ARE DIFFERENT QUESTIONS. "New" is easy: an id never seen
> before. "Updated" is the one that needs care, because a repository's push
> timestamp moves every time somebody fixes a typo.

It already **stores** `first_seen`/`last_seen` with the new row (`:432-437`, both
set to `now` on first sight), **records a finding** rather than a bare timestamp —
`:438` writes `_finding(c, topic, r, "new", ["first seen"], now)` — and computes
`changed = _changes(dict(old), r)` at `:441` for everything it has seen before.

**So the quiet decision this work order asks for is already made in one module,
and simply not made in the other three.** The rule should **reuse that
vocabulary**, not invent a watermark beside it — two notions of "new" in one
subsystem is how they drift.

- **`changed` / `first look`** — decided by the existing `first_seen` comparison,
  in the module that already does it. `jarvis_watch.py` has the only implemented
  one; `jarvis_news.py` and `jarvis_tellme.py` need the same comparison, in the
  same words.
- **`stale: True` plus `last_good_at`** — set where the read happens, and the
  **last-known-good values must not be overwritten** by a failed read. That is the
  whole rule: a failed read must not destroy good data.
- **The silence itself** — the **app**, by drawing no card for `unchanged`. The
  backend returns the state; it does not decide to be quiet, because a backend
  that returns nothing cannot be distinguished from a backend that is broken.
  **That indistinguishability is the failure this design refuses.**

---

## Why not the "obvious" version

**Returning nothing on no-change looks equivalent and is not.** It makes "nothing
changed" and "the watcher is broken" the same answer on the wire. The owner then
cannot tell a quiet day from a dead feed — and the second is precisely the thing
a watcher exists to prevent. It also makes `stale` impossible to report, because
there is no channel left to report it in.

**Warning-tier notices are unaffected.** `jarvis_briefing.py:796` and
`jarvis_news.py:384` route on the tier, and the quiet rule must not gain the power
to suppress a `notify`-tier notice — Rule 4 is that Jarvis never acts unattended,
and a scheduled read that silently stops reporting is a Rule 4 problem, not a
tidiness problem.

---

## What this means for the work order

**Revised, and this is the change to carry forward:**

- **Do not add `[SILENT]`.** It is not a Jarvis convention (0 hits), it has no
  chat turn to live in, and adding it means building a layer to hold a
  suppression the app already performs.
- **Do build:** the shared `first_seen` comparison in `jarvis_news.py` and
  `jarvis_tellme.py` (copying `jarvis_watch.py`'s existing vocabulary), the
  `stale`/`last_good_at` state with last-known-good preservation, and the
  **first-look-delivers-once** case.
- **Do bite-prove two things:** an unchanged poll delivers nothing, **and** a
  failed read still reports — with the cached values intact. A quiet rule that
  cannot be shown to stay quiet, or that goes quiet on failure, has not been
  built.

**The three skills (work order piece 4) are untouched by all of this** and remain
as briefed: `grill-me`, `pdf-workflow`, `skill-authoring`, with the
**never `anthropics/skills/{docx,pdf,pptx,xlsx}`** restriction.
