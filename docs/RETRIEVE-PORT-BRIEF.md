# The `/api/retrieve` port: the one route still marked "todo"

*Decision brief. Read-only investigation, nothing built. Branch `feat/retrieve-port`,
from `origin/main` at `165e8f2d`.*

## The headline

**The trace names your saved facts in plain words, and the desktop already
hides it for exactly that reason.** `lock/rules.rs` `redact_hud_read` answers
`{"available": false, "hidden": true}` for `/api/retrieve` whenever "Windows
Hello for memory lists and chat history" is on — the HUD's own copy of the
trace is wiped by Rust before the page sees it, and a Rust test proves it
(`a_hud_read_is_redacted_only_where_it_is_memory` asserts the words "jazz"
never survive).

So porting it to the phone is not a plumbing chore. It would put a list of
fact words on a device that already has a switch — **"Hide memory lists and
chat history"** — whose whole purpose is that those words are not on the
screen. This brief exists to get the owner's decision before anyone writes
Kotlin.

## 1. What the route actually returns today

**Where it lives.** The route is served by the owner's HUD process, not the
main backend: `jarvis-backend/jarvis_hud.py:3174` (handler) → `retrieve()` at
`:1969`. It is a real, live route, not a stale registry entry — the desktop
HUD page still calls it (`jarvis-desktop/src/jarvis_hud.html:1730`), the
Tauri side allow-lists it by hand (`hud_proxy.rs:41-85`), the desktop's own
test suite asserts that allow-list, and `backend/selftest.py:451` checks it
returns 200. **"Retire the entry" is not the right answer here.**

**The shape.** `GET /api/retrieve?q=<the question>` (with the phase's usual
token and origin checks — `jarvis_hud.py:2258`, because this one "serves
stored personal material"):

```json
{
  "available": true,
  "hits": [ { "id": "fact:12", "kind": "fact", "score": 0.71,
              "text": "first 150 characters of the matched text" } ],
  "near": [ ... the next 6, same shape ... ]
}
```

`hits` is the top 7, `near` is the 6 that lost. An empty question returns
empty lists. `ROUTING` off returns `available: false`.

**Which facts it names.** The corpus is *everything in the brain that carries
text* (`retrieval_corpus()`, `:1889`): saved memory facts (`fact:<n>`), stored
documents (`doc:<id>`, up to 300), **every Logseq page read off disk**
(`logseq:<file>`), and knowledge-graph entities (`kg:<id>` — name plus the
summary/verdict/licence fields). Joplin is deliberately excluded. So a single
answer can name a saved fact about the owner, a document, a work note, or a
person.

One honest correction to the registry's own wording: this trace is not
literally "which facts *an answer* reached for". `/api/retrieve` runs its own
parallel scoring pass over the whole corpus; the real answer's injected memory
is a different list (`/api/memory/used`). The words shown are the ones a
search *would* have handed over, not proof of what this answer used.

**How the HUD draws it today** (`jarvis_hud.html:1728-1799`). Sending a
question fires the trace alongside the answer. When it lands, a strip appears
under the question reading **"7 recalled · 6 near"**, and a panel opens with
two headed sections: **"Recalled for this answer"** and **"Near misses — what
it nearly used"**. Each row is a grey score (`0.71`) beside a **plain-text
snippet of the fact, document or note** — the words themselves, not an id or
a title. Rows are clickable: clicking one flies the brain map to that node.
The last eight questions are kept as chips along the top of the panel, so the
owner can flip between recent traces. In the brain map, hit and near nodes are
scored for highlighting.

## 2. Why the registry calls this a decision, not a chore

- **It names saved facts.** A row is a fact's own words, shortened to 150
  characters. There is no count-only or name-free mode in the route.
- **It collides with the hiding rules as it stands.** On the desktop, "Windows
  Hello for memory lists and chat history" removes this trace entirely and
  substitutes `{"available": false, "hidden": true}`. The phone's switch,
  "Hide memory lists and chat history", hides the "Used in this answer" list,
  the scrollable thread, the People-and-things list and topic names, and it
  blocks screenshots (`Security.kt:324-330`). A phone port that ignored that
  switch would put back, in one place, exactly the words the switch takes
  away — and if it *did* honour the switch, the panel would simply be empty
  whenever the owner has it on, which is the same outcome as not building it.
- **It is heavier than it looks on a PC, let alone a phone.** The route
  re-scores the entire corpus on every question — measured at about 494 ms
  plus 29 ms of disk reads per question at the shipped caps
  (`docs/audit-2026-10-07/G-performance.md`, G1), on a screen decoration.
  A port that fires it per question is a real cost for a "nice to look at".
- **The standing rules already point one way.** No memory graph, no deep
  memory editing and no memory export on the phone; `/api/memory/edit`,
  `/api/memory/export` and `/api/memory/fact-history` are all listed
  "deliberate" for that reason. This route is squarely in that family.

## 3. Options, with what each costs

**Recommendation: option B.**

- **A — Port it as-is.** Under the phone's hiding switch it shows nothing, so
  it needs a second decision about what happens when the switch is off; and
  even then it puts fact, document and note words on a device that can be
  lost. Cost: one new Kotlin client + screen, plus an empty-state design, plus
  a fresh argument for why the phone's hiding rule should not apply to it. It
  also drags the 500 ms-per-question scoring onto the phone's request path.

- **B — Count only: "this answer used 3 saved facts." (recommended)** The
  phone already has the pieces: a "Used in this answer" list under an answer
  (`UsedMemoriesPlate.kt`) with a count. A trace that shows *numbers* — how
  many were recalled, how many were near misses — says "the brain reached for
  something here" without printing a single fact word, and it is a count, the
  same shape the HUD's pending-card count already keeps while the lists are
  hidden. Cost: small; needs a count-only variant of the reply (or a
  count-only read on the phone) so the words never leave the PC.

- **C — Not on the phone.** The phone keeps what it has. Cost: the owner
  loses nothing they can use today (the desktop shows the full trace; the
  phone cannot click through to a brain map anyway, and there is no memory
  graph on the phone). Every remaining "todo" line then has an answer, which
  is worth something by itself.

## 4. The owner's question

**The desktop's retrieval trace prints the actual words of the facts, notes
and documents a question reached for, so the desktop already blanks it
whenever memory lists are hidden. What should the phone do?**

- **Show only the count — "3 recalled, 2 near" (recommended)**
- **Show it in full, words and all**
- **Not on the phone at all**

## Verify — `python tools/check_parity.py` (read-only, unchanged)

```
desktop: 254 routes   phone: 225   ported: 215   not porting: 36   still to port: 1   not the backend's: 2   planned (backend first): 0

Still to port:
  /api/retrieve              The HUD's retrieval trace (which facts an answer reached for). Not in JARVIS-API.md yet; decide what it should show before porting.
...
No undecided drift.
[exit code: 0]
```

## What I could not determine

- **Whether the phone's hiding switch would actually be consulted** by a
  future port — that is the owner's decision, not something in the code.
- **The real trace size on the owner's own data** — the 494 ms figure is from
  the 2026-10-07 audit at the shipped caps, not re-measured here.
- **Whether `/api/graph` (the map the trace's rows click through to) is ever
  ported** — it is separately refused (`brain/routes.rs` `READ_ROUTES`), and
  this brief assumes it stays that way.
- I did not run the HUD, the desktop app or any Android build: this is a code
  and document read only.
