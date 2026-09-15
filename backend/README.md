# Backend patches

Six patches against the Jarvis backend, each self-contained and each with an
executable test. They touch different files and can be applied in any order,
but the order below is the one to use: `memory-safety` must land
before anything makes the extractor run.

| patch | file it changes | what it is for |
|---|---|---|
| `memory-safety.patch` | `jarvis_memory.py`, `jarvis_extract.py` | Five ways the memory store destroyed or refused data. Apply first. |
| `events-pump.patch` | `jarvis_hud.py` | Starts the event pump, which nothing was starting. One line and a comment. |
| `appearance.patch` | `jarvis_hud.py` | `GET`/`POST /api/appearance`, so the phone and the desktop can agree on a face. |
| `gate-push.patch` | `jarvis_gate.py` | Stops the approval gate posting unredacted private content to a public broker. Apply this one whether or not you use ntfy. |
| `skill-notes.patch` | `jarvis_skills.py` | Gates and surfaces the skill notes, which steer answers, are written without approval, and appear on no screen. |
| `documents-honesty.patch` | `jarvis_hud.py` | The brain map reports a document store that has never existed. Makes the status line true. |

## Apply them

```powershell
cd "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"
copy jarvis_hud.py jarvis_hud.py.bak
copy jarvis_memory.py jarvis_memory.py.bak
copy jarvis_extract.py jarvis_extract.py.bak
git apply --verbose path\to\memory-safety.patch
git apply --verbose path\to\events-pump.patch
git apply --verbose path\to\appearance.patch
```

No git in that folder? `patch -p1 < <name>.patch` does the same. Add
`--dry-run` first to see whether it will apply cleanly without changing
anything.

---

# `memory-safety.patch` — apply this one first

Five defects, each found by executing the code rather than reading it, each
with a reproduction in `test_memory_safety.py`. Together they are the reason
this patch has to land before extraction is ever wired up: the current code
does not learn anything, and the moment it starts learning it begins
destroying facts it already has.

### 1. A correction retired a random unrelated fact

`jarvis_extract._accept` took the model's free-text `replaces` string, ran
`store.search(..., k=1)`, and retired whatever came back. `search` has no
relevance floor, so it always came back with something. Measured: accepting
*"Mario drives a 1998 Volvo"* retired *"Mario prefers tabs over spaces in
Go"*. A `replaces` reading *"Mario's allergy"* retired the note about Vim. The
accept reply was `{"ok": true}` either way — the retirement was invisible, and
`retire()` has no route back.

Now `MemoryStore.find_one()` resolves it, requires at least two overlapping
content words and 50% containment, and returns **None** rather than a guess.
None means "store the new fact, retire nothing": two facts that disagree can be
sorted out later, a deleted allergy cannot. The target is also resolved when
the proposal is **queued**, not when it is accepted, and stored on the row — so
the approval card can say which fact this will retire before you agree to it.

### 2. Installing the embedding model bricked every future write

First run without `fastembed` creates `facts_vec` as `float[256]`, the hash
stand-in's width. `CREATE VIRTUAL TABLE IF NOT EXISTS` never rebuilds it, so
when the real 384-dimension model finished downloading, every `add_fact` raised
`Dimension mismatch` — permanently, on a store that had been working.

Worse, `add_fact`'s `INSERT` commits before the vector write (the connection is
`isolation_level=None`), so the failure was reported for a fact that had in
fact been stored, and every retry of the "failed" accept wrote another copy.

Now the table is **dropped** when the embedder changes so it rebuilds at the
new width, and `_embed_rows` swallows its own failures and returns a count
instead of raising past a committed row.

### 3. `backfill_embeddings()` had no caller, and looped forever if called

The module docstring promises that *"the moment the model appears the
embeddings are backfilled"*. Nothing called it. And its `while True` only broke
on an empty batch — a throwing embedder left `embedded=0` on the same rows, so
the next `SELECT` returned them again, forever. It now stops when a batch
writes nothing.

### 4. Five facts entered every prompt, related or not

`MemoryStore.search` had no relevance floor anywhere: the vector arm is a k-NN
scan that returns its nearest rows for *any* query, and the FTS arm built its
`OR` query from every word including `the` and `is`. So it returned a full five
facts for anything. Measured, asked *"why is the sky blue"*, it injected the
NAS, the car's MOT and the owner's diet; the same store also held their
medication and bank details.

That also made `jarvis_recall.select_facts` dead code, because
`jarvis_hud.py` only falls through to it when the store returns nothing —
and `select_facts`, whose comment reads *"Misleading context is more expensive
than missing context"*, correctly returns nothing for those questions.

Now: content words only in the FTS query, a distance cutoff on the vector arm,
and **no vote at all for a non-semantic embedder**. The hash stand-in measured
AUC 0.73 where chance is 0.50 — giving it an equal vote is what guaranteed a
full five results. On a machine with no model, search is now genuinely
lexical-only, and returns nothing when nothing matches.

### 5. The pre-queue filter discarded statements, not questions

`jarvis_extract` dropped anything under three words or opening with an
auxiliary. Measured against realistic extractor output it threw away
*"Can't eat gluten"*, *"Does not drink alcohol"*, *"Is vegetarian"*,
*"Wife: Dana"*, *"Do not suggest Docker, ever"* and *"Should always use metric
units"* — a coeliac diagnosis and four standing instructions — while keeping
*"Whose birthday is 3 March"*. It was matching the shape of a question word
rather than a question. An auxiliary is only interrogative when a subject
follows it; a wh-word almost never opens a durable fact.

### And the auto-accept branch is gone

`propose()` contained `if _cfg("auto_accept", False) and _cfg("setup_complete",
False) and conf >= 0.8: _accept(...)` — a path that wrote facts with no human
decision, two config lines from live. Combined with defect 1 it would have
silently deleted facts with nobody in the loop. Nothing in Jarvis approves on
the owner's behalf, and a queue whose contents can retire existing facts is the
last place to make an exception. `setup_status()` now reports `auto_accept:
false` unconditionally, because that is now true, and adds `queue_full` so a
client can say when the review queue has stopped accepting work.

### Test it

```
python3 backend/test_memory_safety.py
```

Fifty checks, run against real sqlite stores in a temp dir. Roughly a third are
**controls** — that a genuine correction still supersedes, that on-topic
retrieval still returns the right fact, that an accepted proposal is still
written, that no facts are lost in the embedder swap. Those are the ones that
fail if a fix is reverted or over-applied.

---

# `events-pump.patch`

`jarvis_events.Pump` existed. `POLLERS` listed `_poll_approvals`,
`_poll_power` and `_poll_persona`. The class docstring said *"Started by the
proxy"*. `jarvis_hud.py` is the proxy, and it never constructed one — so the
only event kinds ever published were `activity` and `model`, and `approval`,
which `JARVIS-API.md` documents with a worked example and both clients handle,
had never fired.

The cost is not cosmetic. An event is how a client learns that a gate was
raised or settled. Without it the desktop refreshes only on connect, on a
renumbered resume, or when the owner presses Retry — and the stream lives for
an hour with keepalives, so nothing ever times out. So a gate raised while the
desktop sat idle produced no toast and no tray badge for up to an hour, and an
approval settled on the phone left a live, clickable card on the desktop for
the same hour. The 409 on the second decision is what kept that safe; it should
never have been load-bearing.

The patch is one `Pump(engine=_ENGINE).start()` and a comment explaining why it
is there, plus a boot line so its absence is visible next time.

### Test it

```
python3 backend/test_events_pump.py
```

Ten checks: that a changed queue publishes exactly one event and an unchanged
one publishes none, that the payload truncates its items at ten (which is why
treating `approval` as a doorbell and re-reading `/api/pending` is correct
rather than wasteful), and — the control — that `jarvis_hud.py` still contains
a `Pump(...)` call that is started. That last one fails if the line is ever
removed again.

Run it from a directory holding `jarvis_events.py` and `jarvis_hud.py`.

---

# `appearance.patch`

`appearance.patch` adds the two routes the Faces window already speaks, so a
face chosen on the desktop is the face the phone wears. Without it the picker
still works and saves — it just says, every time, that the choice stayed on
this machine.

## Apply it

```powershell
cd "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"
copy jarvis_hud.py jarvis_hud.py.bak
git apply --verbose path\to\appearance.patch
```

No git in that folder? `patch -p1 < appearance.patch`, or apply the four edits
by hand — the patch is 200 lines and three of the four are one-liners.

Then restart the backend and press **save** in Faces. The line under the
buttons should change from *"saved on this machine only"* to *"saved to Jarvis
— the phone sees this too"*.

## What it adds

| | |
|---|---|
| `GET /api/appearance` | The stored document. Joins the existing desktop-only surfaces, so it carries the same origin and token checks as `/api/models` and `/api/config`. |
| `POST /api/appearance` | Writes it. Joins the existing gated-action tuple and dispatches through `_desktop_action`, like every other write. |
| `~/.openjarvis/appearance.json` | Where it lives — beside `config.toml`, not inside it. |
| an `appearance` event | Published on save, so a client that is already open repaints. Clients that do not know the kind ignore it. |

It does not touch anything else. No existing route changes behaviour.

## Why it is shaped this way

**It is cosmetic, so it is not gated.** The document decides how Jarvis looks.
It approves nothing, starts nothing and reveals nothing, so it needs no
approval and should never grow one. If a field would ever change *behaviour*
rather than appearance, it belongs on a different route.

**It rejects rather than clamps.** An unknown pattern or colour comes back 400
naming the offender. Silently dropping a bad binding would leave the picker
showing a choice that is in effect nowhere, which is worse than refusing and
worse than storing something odd.

**A machine without the spec stores anyway, and says so.** The server never
needed `jarvis-visual-spec.json` before, so it may not have one. Refusing every
write in that case would brick the feature the route exists to enable; instead
the reply carries `"note": "stored without checking it against the visual
spec"`. To get validation, drop a copy of the spec next to `jarvis_hud.py` or
in `~/.openjarvis/`.

**The server stamps `updated`, not the client.** Two devices with two clocks
are the case that field exists to arbitrate, so the one machine both of them
talk to owns it. Last write wins — there is one owner here, and a merge
strategy would be machinery for a conflict that does not happen.

**The write is atomic.** Written to a temporary file and renamed, because a
half-written file here means the owner's face silently reverting.

**`/api/config` was the obvious home and is not one.** It is a deliberate 501:
that file decides what Jarvis may do unattended, and the refusal explains why a
half-built editor for it would be worse than none. Appearance has no such
weight and should not sit behind that review.

## Test it

```
python3 backend/test_appearance.py "path/to/patched/jarvis_hud.py"
```

Fourteen checks against the real `jarvis-visual-spec.json`: that all fifty
colours are found, that an unknown colour is refused rather than dropped, that
`banked` is accepted, that a refused save leaves the stored document untouched,
that a save publishes an event, that a machine without the spec says so, and
that a corrupt file reports itself instead of taking the surface down.

Two of those exist because `python -m py_compile` passed while the patch was
broken twice: `time` was never imported, so every save would have raised
`NameError`; and the palette walk looked for `families[].shades[]`, which does
not exist — the fifty colours are a flat `palette.colors` — so colour checking
was silently finding nothing and passing everything.


---

# `gate-push.patch` — the one to read even if you never set a token

`jarvis_gate._redact` exists for a reason its own docstring states plainly:

> the gate "is handed exactly the sensitive part - the recipient of the email,
> the path of the file, the body of the shell command - so writing `detail`
> verbatim would turn the audit trail into the leak it exists to detect."

The local audit log honoured that. The **push did not**. 130 lines below that
docstring, `_push` sent the identical dict verbatim to
`https://ntfy.sh/<your-topic>`:

```
LOCAL AUDIT:  {"command":"<redacted 35 chars>","recipient":"<redacted 24 chars>"}
SENT TO ntfy: {"command":"grep -r 'password' /home/mario/.env",
               "recipient":"dr.okafor@clinic.example"}
```

An ntfy.sh topic is a URL with no authentication. The topic name is the only
secret, it travels in the path, and anyone who knows or guesses it subscribes
to everything. On tier `notify` this fires with **no human in the loop at
all** — the whole point of that tier is that it does not ask.

It also quietly falsifies the published contract: `risk_for` labels
`read_joplin_note`, `read_files_readonly` and `delete_file` as
`reach: "local"`, which both `JARVIS-API.md` and `JARVIS-FRAMEWORK.md` define
as *"nothing leaves this machine"*. Every one of them pushed outbound once it
reached `notify` or `ask`.

**Mitigating:** it is opt-in — nothing is sent unless `JARVIS_NTFY_TOPIC` is
set. **Aggravating:** ntfy appears in none of the three spec documents, so an
owner who sets that variable to get phone alerts has no way to learn what it
sends.

The patch does three things:

1. **Both call sites redact before sending.** The redactor already existed and
   already keeps enough shape to make a useful alert — you still learn that a
   `send_email` is waiting and how long the body was.
2. **No push at all while the conversation is latched local.** The taint latch
   exists precisely because private content is in play; a push is egress to a
   third party, which is the thing the latch is refusing. It fails closed:
   `taint_active()` returns true when it cannot read its own database.
3. **The `prompt` fallback is gone.** It was the wider of the two leaks —
   prose rather than a dict of keys. The notification is now a doorbell: what
   is waiting, its id, and "open Jarvis to read it". Same rule the SSE
   approval event already follows.

### Test it

```
python3 backend/test_gate_push.py
```

Ten checks against a stubbed network and a stubbed framework — nothing is sent
and no approvals database is touched. Four are controls: that `_redact` still
keeps the keys so the alert means something, that a redacted body reaches the
broker unchanged, and (parsing the source) that **neither** call site passes
raw `detail` or falls back to `prompt`. That last pair is what fails if someone
later "simplifies" the call sites back.


---

# `skill-notes.patch`

`jarvis_skills.refine(name, note)` appends free-text notes to a skill's index
row. Three facts about it, each true in the current code:

- **It is not gated.** `write_skill()` twenty lines above calls
  `_gate("modify_own_code", ...)`. `refine()` calls nothing.
- **Its notes reach the model.** `load()` returns `"notes": row.get("notes")`
  *alongside the body*, so they go into the prompt every time the skill is
  used, and they change what it does.
- **They appear on no surface.** `cards()` — what `GET /api/skills` serves, and
  the only place anything lists skills — returns name, description, trust and
  uses. Not notes.

So: a store of self-authored heuristics, written with no approval, injected
into prompts, invisible to the owner. That is the exact shape this product's
rules exist to forbid, sitting inside the module that otherwise enforces them
best — the one that scans skill bodies on raw bytes before a model sees them
and refuses outright at block severity rather than asking.

**Nothing calls `refine()` today**, which is why it has gone unnoticed. It is a
loaded gun, not a fired one. The patch is here so that stays true when
something does call it — and something will, because "let the assistant record
what it learned" is the single most requested feature in this class.

Two changes: `refine()` goes through `_gate("modify_own_code", ...)` like its
neighbour, with a prompt that shows the owner the note and says it will be read
every time the skill runs; and `cards()` returns `notes`, so anything steering
an answer is on a screen the owner can reach.

This is worth knowing before adopting anything from the self-improving-agent
literature. ExpeL's "Insight Pool" is this, with a research paper behind it. The
delta between a skill bank and an ungated one is approval, not storage — and we
already have the storage.

---

# `documents-honesty.patch`

Two readers, no writer, and a status line that said everything was fine.

`SELECT ... FROM documents` runs twice in `jarvis_hud.py` — in
`collect_documents()`, which builds the document half of the brain map, and in
`retrieval_corpus()`, which builds the text the retrieval trace matches
against. Nothing creates that table. `grep -rn "CREATE TABLE documents"` over
the whole backend returns nothing, and `MemoryStore._init` creates `facts`,
`facts_fts` and `facts_vec` and stops there.

So both queries have always raised `no such table: documents`, and both catch
`sqlite3.Error` and return empty. That is a reasonable thing to do when a
store is merely not set up yet — except that it makes *missing* and *empty*
the same silence, and the one surface that could have distinguished them said
the opposite:

```python
"sources": {
    "documents": DOCS_DB.exists(),     # <- true on every boot
```

`DOCS_DB` is `~/.openjarvis/memory.db`. The memory store creates that file for
its own tables the first time it runs, so `.exists()` has been true since the
first boot of the program and has never once been about documents. The brain
map's source list — the place you would look to find out whether a source is
wired up — reported a working document store on a machine that has never had
one.

## What it changes

A `_has_table(db_path, name)` helper beside `_ro_sqlite`, and three call sites
that ask it instead of asking the filesystem:

| site | was | is |
|---|---|---|
| `collect_documents()` | `if not DOCS_DB.exists()` | `if not _has_table(DOCS_DB, "documents")` |
| `retrieval_corpus()` | `if DOCS_DB.exists()` | `if _has_table(DOCS_DB, "documents")` |
| `build_graph()` sources | `DOCS_DB.exists()` | `_has_table(DOCS_DB, "documents")` |

and the two bare `except sqlite3.Error` returns now print. They were only
defensible while a missing table was the expected case; once the missing table
is ruled out above them, a read that still fails is a real fault and should
say so, the way `build_graph()`'s own per-source handler already does.

## What it does not change

It does not create the table. Nothing writes documents, so an empty table
would be the same nothing with a more convincing shape — and a document
corpus is a decision about what gets indexed and therefore about what a
resembling query can pull into a prompt, which is the owner's call and not a
patch's. The point of this one is that the status line now tells the truth
until that decision is made, so `documents: false` is what you see, and it is
correct.

## Test it

```powershell
python test_documents_honesty.py
```

Sixteen checks. `_has_table` is lifted out of `jarvis_hud.py` with `ast` and
executed against real SQLite files rather than paraphrased in the test, so
what runs is the shipped function: a `memory.db` holding a `facts` table and
no `documents` reads as absent, an empty `documents` table reads as present,
a view does not read as a table, and a corrupt file answers no instead of
raising. Against the unpatched file all sixteen fail.
