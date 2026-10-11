# Work setups

Five combinations of local models, each chosen for a kind of work, each
explaining in plain words what it is for **before** the owner starts.

The owner asked for this on 2026-10-10:

> "analyze what different model combinations from the latest and best models
> available for download would be best for different work for jarvis. like if i
> was going to code an android app, or work on admin stuff from my own life. and
> have these as selectable options that explain what they do before i start
> work. and jarvis can also recommend loading up certain combos if i talk about
> work i'd like to do"

- **The reasoning and every measurement**: the working design note,
  `.dsh-scratch/android-verify/WORK-SETUPS-DESIGN-2026-10-10.md` (that folder is
  not in git; it is on the owner's PC beside the two benchmark reports it cites).
- **The setups themselves, and the words a person reads**: `backend/jarvis_work.py`.
  That module is the single source - both apps show its strings, and
  `backend/test_work.py` plus
  `jarvis-client/app/src/test/resources/contract/work-setups-cases.json`
  (`tools/gen_work_cases.py`) hold the two halves to it.

## The five setups

| # | Work | Models and cards | Cost | Why |
|---|---|---|---|---|
| 1 | Everyday quick answers | `qwen3:8b` on the RTX 2080 SUPER at 16,384 (64.0 tok/s), `qwen3.5:9b` on the RTX 2060 at 196,608 | both cards busy at once (-1.9% measured); the main model's own chat is capped at about 15,600 tokens | the fastest useful setup measured, and the 2060 is not idle beside it |
| 2 | Building an Android app | `qwen3.5:9b` on the 2060 at 196,608 (44.9 tok/s), `qwen3.5:4b` on the 2080 SUPER at 65,536 (77.1 tok/s) | the coding card is the slower one; 12x the context instead | 10/10 on the coding test, the best explanation answer measured, 192k on the 2060 with nothing spilled |
| 3 | Admin and paperwork | `qwen3.5:9b` on the 2060 at 196,608, `qwen3:8b` on the 2080 SUPER at 16,384 | about 30% slower writing; the 2060 fully committed | the best-quality model measured, holding a whole letter or statement |
| 4 | Long conversations and big documents | `qwen3.5:4b` on the 2060 at 262,144 (63.1 tok/s), `qwen3:8b` on the 2080 SUPER | answer quality: the 4B got a trap question wrong | the only model that holds 262,144 in video memory on this PC with **zero spill** |
| 5 | Careful coding with a coding specialist | `ornith:9b` on the 2060 at 196,608 (49.1 tok/s), `qwen3.5:9b` on the 2080 SUPER at 8,192 | it scored **8/10** where the general models scored 10/10 | the only model here built for multi-step agentic work, MIT, 256K - offered so the owner can settle the choice on real work |

Five rules, each a measurement, are in the module's own docstring: one model per
card; the 2060 is the long-context card; the 2080 SUPER is the fast card; both
cards run at once for free; and `qwen3.5:9b` is the awkward one (9.17 of the
2060's 12 GB at 196,608, so nothing fits beside it).

## What it does, and what it refuses to do

- **A recommendation is an offer, and the offer is NOT wired into a chat turn
  yet** (measured 2026-10-11). `jarvis_work.match()` reads the owner's own
  words and returns the setup to *offer* and the sentence to say. It never
  switches, loads, unloads or writes anything, and the answer carries
  `switched: false`. A crisis turn offers nothing; a turn where the owner is
  already talking about models says nothing; one loose word is never enough.
- **The recommendation half is a follow-up, and the picker does not depend on
  it.** `JarvisRuntime.offerWorkSetup` is the only thing in either app that
  would POST `/api/work/recommend`, and **no Kotlin file under
  `jarvis-client/app/src/main` calls it** - so
  `HardwarePlate.kt`'s offer panel reads `JarvisRuntime.workOffer`, which is
  never set, and the panel can never be populated. The chat route in
  `jarvis_hud.py` does not call `jarvis_work.match()` either. Two checks now
  hold that, so it cannot be forgotten and cannot be over-claimed:
  `backend/test_work.py` fails the day the offer is wired up (the docs and
  `tools/check_parity.py`'s `UNREACHABLE` entry must be corrected in the same
  change), and `backend/test_parity_callgraph.py` proves the checker itself
  refuses to keep calling an unreachable route a call.
- **Choosing only remembers.** `POST /api/work/choose` writes one preference
  (`work-setup-choice.json`) and returns the ONE step that would switch a model.
  It changes no model and no Ollama setting.
- **Every model change is the existing card.** The step's route is
  `/api/models/switch`, tier `ask`, raised by the app that posts it - and only
  from the chosen setup (the phone's `WorkSetups.stepRequest` refuses every
  other setup, even though the PC sends each one a step). No new gate action,
  no new tier, no download route: a setup whose model is not on the PC says so
  and points at the ordinary download card.
- **Not a catalogue.** Five combinations of models already on this PC, in the
  PC's own words. No list of what could be installed, no search.
- **Uncensored is not part of any setup.** Abliteration measured a TruthfulQA
  loss of 5.75-6.87 points. If it is ever offered it must be a separate opt-in
  with the cost on the label.

## Where it lives

| Piece | File |
|---|---|
| The setups, the offer, the choice (pure) | `backend/jarvis_work.py` (shipped; base copy in `jarvis-backend/`) |
| The three routes | `backend/work.patch` (after `hardware.patch` and `second-card-suggest.patch`) |
| Python suite | `backend/test_work.py` |
| The dead-offer guard, on the checker itself | `backend/test_parity_callgraph.py` |
| Claim checker (numbers must trace to the reports) | `tools/check_work_claims.py` |
| Golden file for both apps | `jarvis-client/app/src/test/resources/contract/work-setups-cases.json` |
| Generator | `tools/gen_work_cases.py` |
| Phone | `net/WorkSetups.kt`, `HardwarePlate.kt` (`WorkSetupsSection`), `JarvisRuntime` |

## Still to build (the desktop half, and the wire into a chat turn)

`jarvis-desktop/` and `src-tauri/` were another conversation's surface while
this was built, so **nothing there was edited**. The desktop needs:

1. a **Work setups** section in Settings → Hardware and models
   (`jarvis-desktop/src/hardware-panel.js`), shaped like the phone's
   `WorkSetupsSection`: the PC's words for each setup, with what it is worse at
   on its own line, and one button that only chooses;
2. the same two reads/one write in Rust (`hardware.rs` or a new `work.rs`):
   `GET /api/work`, `POST /api/work/choose`, and `POST /api/work/recommend`,
   building against the golden file above.

**And the recommendation itself is not wired into a turn yet.** That needs a
seam that does not exist: `jarvis_hud.py`'s chat route would have to call
`jarvis_work.match()` on the owner's own newest words, exactly as it already
calls `jarvis_second_card.maybe_suggest_combined` at the end of a turn, and
append the sentence. The route is ready and safe to call; the seam is the core
file, and this feature's patch deliberately does not touch it. **So today the
offer is reachable by nobody**: the phone's screen draws one only from
`JarvisRuntime.workOffer`, nothing calls `offerWorkSetup`, and a client that
asked `/api/work/recommend` would be the first ever to do so.

The three routes are listed as `planned` in `tools/check_parity.py`, which is
its word for "on the backend, not in the desktop yet". `/api/work/recommend`
goes one step further: it is also in that tool's `UNREACHABLE` list, because
the phone builds it in a function nothing calls - so the checker prints the
missing half rather than reporting agreement it has not shown, and it is not
listed among the routes the phone is on (a literal in the phone's source is not
a call). What it prints, word for word:

    ::warning::/api/work/recommend is 'planned' and NEITHER app calls it: the
    phone builds the route in a helper nothing calls (...)
