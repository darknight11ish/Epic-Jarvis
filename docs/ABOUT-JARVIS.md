# About Jarvis — the history, from the record

**What this page is.** The story of how Jarvis was built and why, written for
someone who is smart and learning — no git, Rust or Android knowledge assumed.
Every claim in it is traceable to a file, a commit or a quoted line, and each
one names which. Where the record does not say why something was done, this
page says **"not recorded"** instead of guessing.

**Why that rule is in here at all.** This project's own standing instruction is
*"Do not claim more than the evidence supports"* (`CLAUDE.md`), written after
two occasions when it was broken: a stack frame read as a cause and relayed as
"confirmed", and *"a bug invented by grepping my own draft and mistaking it for
the source file."* An origin story is exactly the place where a project invents
its own mythology, so this one is built the other way round: the record first.

**How to read the citations.** `path:line` means a line in a file on this
branch. `DECISIONS.md` means `docs/DECISIONS.md`, the dated record of the
owner's own decisions from 2026-09-24 to 2026-10-13 — quoted here exactly as it
stands, never reworded. Commit hashes are real and can be read with
`git show <hash>`.

**Where this page came from.** It was written by reading the record, not by
asking anyone to remember. The files it leans on hardest are named at the end.

---

## 1. Why Jarvis exists

### What the repository itself says

The first commit is `e7c466a4`, **2026-09-12, "Initial commit"**, and the entire
repository at that moment was **one file**: a `README.md` reading, in full:

> `# Epic-Jarvis`
> `Epic Javis based on openjarvis  and greatly enhanced .`

That is the repository's own statement of where it came from, typos and all. It
is the only origin sentence the project ever wrote down about itself in its own
voice, and it is worth being precise about it:

- **OpenJarvis is a real, separate project** — Stanford's open-source local
  assistant framework, Apache-2.0 licensed (`docs/LEARNING-RESEARCH-2026-09-23.md:15`,
  which names it as "Stanford's open-source local assistant framework
  (Apache-2.0, a licence that allows reuse)").
- **The two projects share no code.** Same file, line 17: *"But the two
  projects share no code."*
- **Epic-Jarvis began as something that sat in front of OpenJarvis, not inside
  it.** Same section: *"Epic-Jarvis was designed to sit **in front of**
  OpenJarvis. Early on, chat was passed through to OpenJarvis's server on port
  8000 ... and the permission gate knows OpenJarvis's tool names."*

### What that relationship actually turned into

OpenJarvis was **never running**. From `backend/README.md:2636`:

> *"**OpenJarvis was never actually part of this setup.** The owner downloaded
> it once, separately, to look at it — it was never installed as this project's
> completion backend. So every local chat turn was silently doomed to a 503 the
> moment it reached `_open()`, unless OpenJarvis happened to be running, which
> it never was."*

The fix has its own patch, `ollama-direct.patch`, which points the local lane
straight at Ollama instead (`backend/README.md:97`). Later, each OpenJarvis
piece was replaced by this project's own: *"it talks to Ollama directly
(`ollama-direct.patch`), has its own tool loop (`backend/jarvis_agent.py`), and
its own memory"* (`docs/LEARNING-RESEARCH-2026-09-23.md:17`).

**In plain words:** Jarvis started out as a client in front of somebody else's
assistant framework, discovered that framework was never there, and grew its
own everything instead. The folder it keeps its settings in is still called
`.openjarvis` (`README.md:798-799`), which is the fingerprint of that beginning.

### What he wanted, in his own words

The record is thin here, and this page will not fill the gap with a story.
What exists are the owner's own dated requests, quoted in `DECISIONS.md`. These
are the earliest statements of purpose in the record, and they are all specific
wants rather than a mission statement:

- *"add the ability for jarvis to request a multi-step process that it does on
  its own, and it sends me a detailed approval card that I only give to approve
  once. Really refine this"* (2026-09-28, `DECISIONS.md:1016-1018`).
- *"is there a button where I can find the entire feature set of Jarvis on my
  desktop or android phone? It's important I can know all the features"*
  (2026-10-08, quoted in `tools/check_feature_list.py:6-9`).
- *"make sure that there are effective, interactive tutorials that are
  interactive on both the android app and desktop program, and that they are
  specific to each platform"* (2026-10-10, `docs/TUTORIALS-DESIGN.md:342-344`).
- *"jarvis should be able to change all settings if i ask it to in chat or in
  the live mode"* (2026-10-13, `DECISIONS.md:1944-1946`).

### The name, and what it deliberately is not

The name is Jarvis. The record's most interesting fact about it is what it
forbids. A report into the assistant's character
(`docs/CUTTING-EDGE-2026-09-26-round4-character.md`) lists what Jarvis must
never do, and the third item is:

> *"Says 'sir', quotes Iron Man, or calls itself J.A.R.V.I.S."* (line 86)

Its own decision table (line 122) says what was borrowed from the Iron Man
character and what was left: **borrowed** — *"Calm competence and dry
understatement; says plainly when a plan is risky"*; **left** — *"The name
styling, 'sir', the butler act, film lines, the actor's voice."* The stated
reason is a trademark, not a taste: `docs/ui-audit-2026-09-26/restraint.md:223-231`
("Rule 8. Keep clear of Iron Man") records that Marvel holds the JARVIS
trademark for voice-assistant software, and that the risk *"grows with 'Iron
Man visuals (arc-reactor rings)', the 'J.A.R.V.I.S.' spelling, or film
lines."*

The same report borrows **ideas** from four other fictional assistants — TARS
from *Interstellar* (humour as a setting the user controls), Alfred (loyalty and
candour), Samantha from *Her* (warmth) and Star Trek's ship computer (exact
neutral answers) — and names what is refused from each (lines 122-128), for
instance *"The honesty setting ('90 percent'). In Jarvis, honesty is fixed"*.

> **Where the record is silent.** There is **no statement anywhere in this
> repository of what first prompted the owner to want a local assistant**, and
> no diary of the first idea. The earliest durable trace is the commit of
> 2026-09-12 and its one-line README. A motive beyond "based on openjarvis and
> greatly enhanced" is **not recorded**, and this page does not invent one.

---

## 2. The research that shaped it

Jarvis is unusual in that it repeatedly stopped building in order to go and
read. The pattern is visible in the filenames: audits, competitor checks and
research notes, each ending in a decision in the owner's own words. Here are
the ones the record shows changing the product.

| Research | What it was | What it changed |
|---|---|---|
| `docs/LEARNING-RESEARCH-2026-09-23.md` (2026-09-23, 22 KB) | "Has Jarvis taken everything useful from OpenJarvis for 'learning over time'?" | Established that no OpenJarvis learning code is in Epic-Jarvis, that **"Most of OpenJarvis's learning features are not connected up inside OpenJarvis itself"** (line 9), and surfaced one real gap: **"you have no way to tell Jarvis an answer was wrong"** (line 13). The owner's answer was the five patches added at the end of the stack: `feedback.patch`, `memory-intake.patch`, `skill-suggest.patch`, `documents-owned.patch`, `speed-record.patch` (`backend/README.md:24-26`). |
| `docs/RESEARCH-2026-09-24.md` (safety research) | Named directly in the decision it produced | *"Note-writing waits for a yes after outside text"*; passwords/PINs/account/ID numbers always wait; "Erase the words" invented; hands-free voice trusted like the talk button by default (`DECISIONS.md:17-39`). |
| `docs/RESEARCH-2026-09-24.md` + audit reports (competitiveness) | What a competitor already had | Put **"Timers, reminders and one shared scheduler"** first in the queue, and explicitly *"Build ONE scheduler"* rather than one per feature (`DECISIONS.md:50-55`). |
| `docs/COMPETITORS-MUSE-2026-09-25.md` | An audit against Meta's Muse | *"Jarvis may SEND email, one approval card per email, the card showing the exact recipients, subject and full text; never an 'always allow'"* (`DECISIONS.md:96-101`). |
| `docs/CREATIVITY-AUDIT-2026-09-25.md` | A creativity audit | Narrowed when a web search asks first, allowed one smart-home card to cover several named devices, and gave Jarvis a manner setting — *"warm and brief by default, with a 'Plain' option"* (`DECISIONS.md:121-133`). |
| `docs/APPROVALS-AUDIT-2026-09-26.md` | An approvals audit | The general principle that **small, low-risk things stop asking**: plain repeating reminders need no card; lights and plugs get a setting, off by default; everyday facts about people save automatically (`DECISIONS.md:162-181`). |
| `docs/MEMORY-RESEARCH-2026-09-26.md` | Memory research | Build memory ideas 1–4 first, *"each measured by the memory self-test"* (`DECISIONS.md:199-206`). This is where the "measured before kept" habit enters the record. |
| `docs/FEASIBILITY-AUDIT-2026-09-26.md`, `docs/UI-AUDIT-2026-*`, `docs/ease-audit-2026-09-27/` | Feasibility, UI and ease-of-use | 31 small items queued, the "do first" UI list built, and the gaps written down that later became the tutorials (*"First run does not mention it", "Setup: about 24 steps, 13 PowerShell lines"*, quoted at `docs/TUTORIALS-DESIGN.md:59-60`). |
| `docs/COMPETITORS-OPENMUSE-2026-10-08.md` | A comparison against CopilotKit's OpenMuse | The job list (`backend/jarvis_tasks.py`), with five specific protections copied *in shape* — a lease, a checkpoint per step, `outcome_unknown`, an idempotency key, and a card decision bound to the words shown (`DECISIONS.md:1829-1842`). |
| `docs/PROMPT-COACH-DESIGN.md` (2026-10-08) | Four open-source prompt tools the owner offered | **None was used.** `promptimal` "requires an OpenAI API key and has no local-model support (Ollama is item 1 of its own roadmap), so using it would have sent the owner's own typed words to OpenAI, which is rule 1" (`DECISIONS.md:1790-1793`). |
| `docs/INTEGRATION-EVAL-2026-10-10.md` | Eight outside projects | Found one idea worth taking, borrowed "as an idea: no code, no dependency, no licence exposure" (`DECISIONS.md:1870-1872`). |

**The habit this produced.** Research here is not reading for its own sake; it
ends in a numbered decision with a stated reason and a stated size. And when a
research report was *wrong*, the correction went into the record as part of the
point — see §5, "the correction is the point".

---

## 3. How it was built

This is genuinely part of the history, because the way the work is done shaped
what got built.

### The backend lives outside the repository

The Python program that does the work — `jarvis_hud.py`, `jarvis_gate.py`,
`jarvis_memory.py` and their neighbours — lives on the owner's own PC and was
never in the repository at first. `docs/ARCHITECTURE.md:2290-2295`:

> *"**The owner's live copies are not in this repo.** ... `backend/` holds
> **patches** against them plus the tests that prove the patches do what they
> claim. `backend/.gitignore` refuses the sources, because a stale copy in git
> is worse than no copy."*

So the repository held **changes to a program it did not contain**. That is why
there is a `backend/` folder of 145 `.patch` files
(`Get-ChildItem backend/*.patch` → 145), each with a test that proves it works,
applied in one fixed order by `scripts/apply-patches.ps1`. The order is not
decoration: *"many patches edit lines an earlier one wrote"*, and *"above all,
`memory-safety` must land first: without it the first accepted proposal retires
a roughly-matching unrelated fact, permanently"* (`docs/ARCHITECTURE.md:2331-2335`).

**Where the code actually came from is recorded, and it is not flattering but
it is honest.** `docs/ARCHITECTURE.md:2311-2319`:

> *"**Five modules had no second copy anywhere until 2026-10-06.** `jarvis_hud.py`,
> `jarvis_gate.py`, `jarvis_extract.py`, `jarvis_models.py` and `jarvis_skills.py`
> — 605 KB — existed only in the one folder on the owner's PC ... No public
> upstream has ever been found for any of the twenty-six: the evidence is that
> the files were produced in assistant conversations and saved to disk, which
> makes that chat history their only origin."*

### Then half of it was published

On 2026-10-06 that changed: `jarvis-backend/` is *"a checked snapshot of the
owner's folder, taken so that a stranger can clone this repository and have a
backend to run rather than a folder of patches against a folder they do not
have"* (`docs/ARCHITECTURE.md:2297-2300`). `README.md:585-589` says why it
mattered: *"Until 2026-10-06 it existed only on the author's PC, so nobody else
could run Jarvis at all, however carefully they followed the install page."*

Two rules grew out of that: editing **any** file under `backend/` is a
**two-file change**, because `backend/<file>` and `jarvis-backend/<file>` are
kept equal; and this drifted into being more than two files, because the base
also reads some files without importing them (`jarvis-backend/rust-crates.lock`
and `requirements.lock` among them) — a rule that got its pointed correction on
2026-10-13 after a one-line omission in a lock file turned two CI jobs red
(`CLAUDE.md`, "Editing any file under `backend/` is a two-file change"; the
twin rule's history is in that same section).

### Parallel copies of the code, and agents working in them

The project runs in **`git worktree` checkouts** — a worktree is a second copy
of the code on another branch. Several agents work at once, each in its own
worktree, and this shapes the rules. The clearest statement of the cost is in
`CLAUDE.md`:

> *"a plain search answers 'what does MY checkout say' while reading exactly
> like a claim about `main` ... This cost two rounds on 2026-10-11: a false
> finding about a privacy-sensitive plate, and then a second reader
> 'independently confirmed' it — with the same command, in the same feature
> branch, and neither of them asked what it searched. **Two confirmations of
> the same wrong thing, because the instrument was the same.**"*

The other cost is duplicate work, and it is written down in
`docs/DEFECT-REGISTER.md:90-101`: on the night of 2026-10-11 the same real bug
was repaired **three** times over in one test module, **three** times for one
patch anchor, **five** times for one branch cleanup and **six** times for one
test file — *"Every one of those was paid for twice."* That is why the defect
register exists: one line in one file, before the work starts.

`docs/HANDOFF-2026-10-05-tutorials-and-ci.md` is what a handover between those
sessions looks like: what was built, the evidence, the open work in priority
order, and a **"Hazards — things this session got wrong, so the next one does
not"** section (lines 86-129). Its first hazard is a commit, `8969a1d5`, that
was *"a mass deletion"* of 11 files and 531,882 lines pushed by accident and
undone in `d0cdb7d8`, with the cause recorded: *"a `git revert` aborted because
the working tree was dirty, and the script committed anyway."*

### The checkers

Because a claim in a document is cheap, this project keeps **checkers** —
small programs that read the repository and fail when it stops being true. 26
of them are named `check_*.py` under `tools/` (`Get-ChildItem tools/check_*.py`
→ 26), and a census of what runs them is itself a document
(`docs/CHECKER-CENSUS-2026-10-12.md`), because two of them were once *"named in
`ci.yml` but never run by it"* (line 5).

The checkers that gate changes include:

- `tools/check_claims.py` — *"one row per thing this project says about itself,
  with a check a machine runs"* (`docs/CLAIMS.tsv`, 152 rows). On the tree this
  page was written from it reports **152 claims: 137 built, 7 still open, 8
  unverifiable** — *"and every `open` one is still a real gap."*
- `tools/check_parity.py` — did a feature land in both apps, or is one side
  deliberately left out?
- `tools/check_feature_list.py` — is `features/features.json` (the "Everything
  Jarvis can do" list) complete, and is every line on it still true?
- `tools/check_vacuous_checks.py` — is any test *"a fake skip"*, or does any
  check have a string or defaulted condition that can only pass?

### The field-test discipline

Testing on real hardware, and reading the app without a picture of it, became a
discipline of its own on 2026-10-11. `docs/FIELD-TEST-HOW-TO-READ-THE-APPS.md`
opens with the one rule:

> *"**A screen you cannot read is not a screen you have tested.** ... And **a
> feature that could not be reached is never a pass**: PARTIAL and BLOCKED are
> the honest verdicts, and they are written as such."* (lines 9-14)

The five ways in are recorded (the phone's accessibility tree, the desktop's
Windows UI Automation tree, the phone's notification record, the backend's own
state, and real input events), and so is what none of them can do — the tray
icon *"sits inside the 'Show Hidden Icons' overflow and produces **no readable
menu**"*, and the face picker *"is a picture, so `uiautomator` sees no labels
for it at all"* (lines 26-49).

---

## 4. The big decisions, and what each replaced

The reversals are the most instructive part of the record, because each one
states what it replaced. All of these are quotes or near-quotes from
`DECISIONS.md`, which is the owner's own dated log.

### Things that were banned and then allowed

**1. API keys. Banned, then allowed — the oldest reversal in the record.**
The rule as it originally read (visible in the commit that changed it,
`5c78f44a`, 2026-09-17):

> `-3. No API keys in the app. The only secret it stores is the pairing token.`

and after:

> *"API keys are allowed in the app — the owner reversed the old blanket ban
> on 2026-09-17, to unblock things like a GitHub API integration."*
> (`CLAUDE.md`; the commit message adds: *"it was blocking things like a GitHub
> API integration"*.)

**2. Meta's "Sky" voice, for the sea otter. Not a taste — a promise.**
`CLAUDE.md` says *"the sea otter's voice is not a matter of taste, and the
record says why."* Here is why, in full (`DECISIONS.md:432-442`):

> *"**Animal faces offer their own voice once** (owner, 2026-09-28) ... **The
> sea otter must not use Kokoro's 'Sky' voice** (its name matches the voice
> OpenAI withdrew in 2024 over a likeness complaint); give it another Kokoro
> voice with the same playful pitch. Animal voices are Kokoro voices, blends
> and pitch from Jarvis's own sources only — never a real person's voice — and
> must pass the 'not the owner's voice' check."*

The same entry records that the mascot branch's switch *"Voice follows the
face"* was **built on by default**, and the owner's decision was that it
*"stays, but starts off"*, with a one-time question doing the turning on.

**3. Bot-detection stealth. A refusal, reversed after the risk was explained
and accepted.** On 2026-09-28 the record says the chatbot driver is
*"~~driven openly - at human pace, in a visible browser window, with nothing
that hides it from or dodges Google's bot detection, and no captcha-solving~~"*
and that *"A request to add 'tactics that help avoid bans' was declined:
getting round a site's bot protection is not something this project builds."*
On 2026-09-29 the owner reversed it, and the reversal names itself
(`DECISIONS.md:1513-1529`):

> *"Decided 2026-09-29, the owner REVERSED the 2026-09-28 'driven openly' rule
> (asked several times, after being told the ban risk each time; 'get rid of
> the rule blocking it')"* — **"Stealth on for everything"**, with the ban risk
> *"explained and accepted"*.

What did **not** change is written beside it: *"Jarvis itself never solves a
captcha"*, no proxy service, nothing private goes into a web chat, and *"if the
other side asks directly whether it is talking to a bot, Jarvis never claims to
be human"* (`DECISIONS.md:1530-1540`).

**4. Plain-text screen reading with one card. Reversed, as a switch.**
On 2026-09-28 the record says with one card Jarvis *"reads the screen's text
only"*. On 2026-09-29 the owner reversed that too, in the entry that says so in
those words (`DECISIONS.md:1486-1494`):

> *"**A slow picture mode for a one-card PC is allowed, as a switch** (owner,
> 2026-09-29: 'add it as a feature that can be enabled or disabled') ... This
> reverses 'one card reads the screen's words only'. Built the careful way:
> **off by default, turning it on raises an approval card (a new download)**"*

### Defaults that flipped

- **The "I heard you" sound.** *"off by default"*, and then, in parentheses,
  *"the owner changed on to off, 2026-09-25"* (`DECISIONS.md:70-71`).
- **Reading an answer aloud.** *"This replaces 'any tool keeps the answer on
  screen.'"* (`DECISIONS.md:388-393`) — answers that used web search, weather or
  home status are now read aloud when read-aloud applies.
- **When a web search asks first.** Narrowed twice: first to *"only when
  private things could slip in"* (2026-09-25), then again to *"only when the
  search words would repeat a saved fact, or a sensitive fact was used"*
  (`DECISIONS.md:123-126`) — and the second one was recorded a third time on
  2026-10-13 *as a loosening*, with the explicit note that no code changed:
  *"What this adds is the record of his explicit yes to it as a loosening"*
  (`DECISIONS.md:2142-2149`).
- **Which patch... which hotkey.** Talk-to-type was decided as *"held Right
  Ctrl"* and corrected on 2026-10-08: *"A bare Ctrl key cannot be a global
  hotkey in this build ... so 'held Right Ctrl' was never buildable as
  written."* It ships on **Alt+Shift+T** (`DECISIONS.md:592-599`).
- **The settings tool.** *"This replaces the earlier position in the same day's
  work that the tool 'ships OFF, like every tool but `web_search`'"* — the
  owner said on 2026-10-13: *"yes turn it on for my pc. it should also be
  enabled by default."* (`DECISIONS.md:2100-2136`.)
- **An 8 GB second card is now usable.** The floor had been 10 GB; on
  2026-09-30 it dropped to 8 GB with three of the switches available and two
  refused for a stated reason — *"because an 8 GB card holds no more than the
  main card's 16,384 tokens"* (`DECISIONS.md:1649-1656`).

### The rule that grew a pointed amendment

**Loosening a privacy rule used to be a PC-only job. On 2026-10-13 that changed,
and the record calls it a weakening in those words.** What it replaced, quoted
word for word (`DECISIONS.md:1955-1963`):

> *"On the PC only, the owner may also loosen a short safe list (note writes,
> the wiki, reading their own calendar, email, notes and home status) - one card
> plus Windows Hello per change. **Nothing outside that list can be loosened
> from an app.**"*

> *"Both sentences are gone: there is no short safe list any more, and a change
> to something privacy- or security-related no longer has to be made at the PC.
> That is a WEAKENING and it is written here as one."*

Two things make this entry the model for how this project records a reversal.
First, it says plainly what still protects it and what is *not* yet true:
*"the server does not honour the phone's signature for the actions this
decision is about"*, so *"until that list is narrowed, **the phone still cannot
loosen anything**: the decision above is not the shipped behaviour for it"*
(`DECISIONS.md:1986-1999`). Second, it signs its own work: *"This entry is the
RECORD of his decision. The behaviour ... is a separate piece of work."*
(`DECISIONS.md:2004-2006`).

### A few more worth reading in full

- **Goals vs the plan card, a mix-up the record refuses to repeat a third
  time** (`DECISIONS.md:987-992`): *"**This is NOT 'the plan card'** ... Goals
  never batches anything ... `jarvis_goals.py`'s own docstring exists partly so
  this does not get confused a third time."* The plan card itself was built
  **switched off**, gated on a real measured test result: *"measured not
  promised: it reads `tools/tool_eval/tool_eval_results.json` and says yes only
  once a real run, for the real model, clears two bars ... No file yet, so
  nothing is unlocked yet"* (`DECISIONS.md:1036-1041`).
- **The phone's network rule got stricter, not looser.** *"The phone connects
  through Tailscale or NordVPN Meshnet only (owner, 2026-09-28), replacing
  'Phone: allow home-network addresses' of 2026-09-27. Allowing a home address
  would mean the PC also answering on home Wi-Fi, where the pairing key travels
  unscrambled"* (`DECISIONS.md:424-428`).
- **Teaching the app to teach.** The first tutorials were *"Step cards that
  explain and show ... Not live click-along walkthroughs"* (`docs/TUTORIALS-DESIGN.md:41-43`),
  and on 2026-10-10 the design note says of that decision: *"That is what was
  built, and it is what the owner is now asking to move past"* (`docs/TUTORIALS-DESIGN.md:329-336`).
- **Five things that are not negotiable.** They were written into `CLAUDE.md` in
  the commit `fa562659`, **2026-09-15** ("Add CLAUDE.md: the owner is a beginner,
  explain things plainly") — the same commit that established the
  explain-it-simply rule. Their current text is in `CLAUDE.md` and repeated
  verbatim in `README.md:56-78`. Each one has since been *tested* by a
  reversal: rule 1 by the locked backup and support-chat details, rule 3 by the
  API-key lift above, rule 4 by the chatbot conversation, rule 5 by the
  owner's statement that EpicJarvis *"will never be commercialized"*
  (2026-09-28). Rule 2 has no exception at all — see §7.

---

## 5. The failures, kept on purpose

> *"A history with no mistakes in it is not a history."* This project agrees,
> and keeps the mistakes in its own files. `docs/DEFECT-REGISTER.md:90` labels
> its history section *"(history, not an open defect)"*.

These are real, and each carries what it taught.

**The app that could never hold a conversation.**
*"the desktop app the owner has been building this whole session could never
have actually held a conversation, because the one thing it depends on to
answer was assumed into existence and never verified"* (`backend/README.md:2636-2643`).
**Taught:** assumed infrastructure is not infrastructure. The fix —
`ollama-direct.patch` — deliberately changed only the URL, because everything
around it was real and load-bearing.

**The red panda that was four times over the size limit.**
`CLAUDE.md` records that the first red panda's shader *"went out four times
over and only the emulator test caught it"*, because *"WebGL and a newer Skia
on a PC accept an over-size shader without a word."* **Taught:** a renderer that
says nothing is not an approval. The project now measures with
`tools/shader_size.py`, and CI runs it with `--check`.

**A commit that deleted 531,882 lines.**
`docs/HANDOFF-2026-10-05-tutorials-and-ci.md:88-93`. **Taught:** *"Check
`git status` is clean before any revert, and never commit after a failed
revert."*

**Two people confirming the same wrong thing.**
The worktree/scoping dead end above, written up three times — `CLAUDE.md`, and
as dead end 3 in `docs/FIELD-TEST-HOW-TO-READ-THE-APPS.md:158-171`.
**Taught:** say which tree you asked. A second reader is not independent if they
ran the same command.

**A "nothing found" that was the instrument, not the result.**
`docs/DEFECT-REGISTER.md:59-88` lists three cases from 2026-10-11, and the
lesson is one line: *"**A probe that returns nothing is not evidence of absence;
it is not evidence at all until the probe is shown to work.**"* The third case
is the sharpest — an armed watcher *"did catch the orphan condition at 16:05,
then failed to find a Coming up row, fell back to tapping the Brain tab, and
printed **'STILL POSTED'** — an instrument failure wearing a result's clothes."*
**Taught:** *"make the check say what it did, not only what it found."*

**Counting what you can see and concluding about what you cannot.**
Dead end 4 in `docs/FIELD-TEST-HOW-TO-READ-THE-APPS.md:172-182`: the crash-notes
row was recorded **FAIL** because the word "crash" appeared zero times in the
2,067 strings the Settings window exposed — and the row lives inside a
**collapsed fold**. Re-measured after opening the fold: still zero, *"which is
exactly why the count was never evidence."*

**A screen that contradicted itself, and the reassuring half was wrong.**
`CHANGELOG.md`, 2026-10-09: the badge read **"Watches · 3 new"** while the block
under it read **"Nothing new since you last marked the list read."** Both apps
read keys the route had never served, so *"every **successful** read came back as
the empty list and the all-clear was drawn whatever the list held."* **Taught:**
the desktop's UI fixture was hand-written, so *"the harness agreed with the client
and disagreed with the backend"*. The fixture is now produced by running the real
module.

**A test that had never once passed.**
`CLAUDE.md`, "Running the tests — the fourth command": PR #394's `rust` job
failed on a test asserting `"Not installed"` against a fixture saying
`"not installed"` — *"**deterministically impossible, it had never once passed.**
It hid because clippy *compiles* tests without running them."* **Taught:** a
checker that compiles is not a checker that runs; a skipped test is never a pass.

**A tool that passed here and failed in CI.**
`CLAUDE.md`, "Editing a backend `.patch`": the patch-history tool *"refuses to
run"* in a shallow clone, and `test_patch_history.py` *"quietly skips the checks
that need history — so it passes here and fails in CI."* Shipped once,
2026-09-28. **Taught:** a check that can silently not run will.

**A CI job that was quietly made to run what it was forbidden to run.**
`docs/HANDOFF-2026-10-05-tutorials-and-ci.md:50-58`: the `backend-windows` job
runs a hand-curated list *"which its own comment forbids in capital letters
('This is NOT "run_suites.py again, on Windows" on purpose')"*; commit
`70fce021` made it do exactly that. **Taught:** a comment is not a guard.

**A patch anchored in the wrong place.**
Same file, lines 101-106: `tutorials.patch` *"was anchored on the wrong install
block (retirement, 40 lines too early) because it was built from the rehearsal
stand-in."* **Taught:** *"A patch's context must be checked against the owner's
real backend files"* — `git apply --check` against a copy of the real file.

**The correction that was the point.**
`DECISIONS.md:1843-1850`: an outside comparison report *"first listed OpenMuse's
IP-pinned egress check as a gap to copy"* — and the project had already done it,
better, since 2026-09-27. *"That was the third time this project has 'gone
looking for' something it already had (`docs/PEERS.md` recorded the first two)."*
**Taught:** the two real things the comparison did earn were closed the same day.

**A bug invented by grepping a draft.**
Named in `CLAUDE.md` as one of the two occasions that produced the
"do not claim more than the evidence supports" rule: *"a bug invented by
grepping my own draft and mistaking it for the source file."* **Taught:** the
whole rule, and the `git show origin/main:<path> | Select-String` habit that
goes with it.

### Still open, at the time of writing

The register is not a museum: on the tree this page was written from,
`docs/defect-register.tsv` holds **14 rows, 13 closed and 1 open** — DEF-002 (a
measured 4,598 ms against 9 ms, `docs/DEFECT-REGISTER.md:107`). And 7 of the 152
claims in `docs/CLAIMS.tsv` are still marked open.

---

## 6. Where it is now

Everything below was measured on this branch by running the command shown. The
counts are honest counts, not estimates, and they change — re-run the command
rather than trusting the number.

| What | Number | How it was counted |
|---|---|---|
| Commits | **3,115** (738 of them merges) | `git rev-list --count HEAD`; `git rev-list --merges --count HEAD` |
| First commit | **2026-09-12**, `e7c466a4` "Initial commit" | `git log --reverse` |
| Last *numbered* release | **0.2.0** | `VERSION`; `CHANGELOG.md:10` ("the last *numbered* release"; newer work sits above it under "Not in a numbered version yet") |
| Features both apps show | **129**, in 9 groups | `features/features.json`, checked by `tools/check_feature_list.py` |
| Backend patches | **145** | `Get-ChildItem backend/*.patch` |
| Backend test suites | **315** | `Get-ChildItem backend/test_*.py` |
| Desktop test suites | **184** `.mjs` files | `Get-ChildItem jarvis-desktop/tests/*.mjs` |
| Phone test files | **218** `*Test.kt` | `Get-ChildItem jarvis-client -Recurse -Filter *Test.kt` |
| Documents | **379** markdown files, about 9.3 MB | `Get-ChildItem docs -Recurse -Filter *.md`; the page's own figures are checked by `tools/check_docs_map.py` |
| Checkers named `check_*` | **26** | `Get-ChildItem tools/check_*.py` |
| Claims about itself, each with a machine check | **152 rows**, 137 built / 7 open / 8 unverifiable | `python -B tools/check_claims.py` |
| Defect register | **14 rows**, 13 closed / 1 open | `docs/defect-register.tsv` |
| Launch videos kept | **6** numbered versions, v1–v6, never replaced | `videos/README.md`; the owner's rule of 2026-09-24 (`CLAUDE.md`) |

**What runs when a change is pushed.** Ten CI jobs are declared in
`.github/workflows/ci.yml` — `rust`, `frontend`, `backend`, `backend-windows`,
`credential-manager`, `powershell-5`, `phone-unit-tests`, `audit`,
`python-advisories` (and the `push` trigger). **Six of them gate a merge** —
`rust`, `frontend`, `backend`, `backend-windows`, `credential-manager`,
`powershell-5` — while `audit` and `python-advisories` are informational
(`CLAUDE.md`, final section, which records a direct push refused with *"6 of 6
required status checks are expected."*).

**The checkers, run for this page.** All five exit 0 on this branch, with
`JARVIS_BACKEND` cleared:

- `python -B tools/check_docs_map.py` — `docs map OK: 379 documents, 9,292,745 bytes, and README.md agrees`
- `python -B tools/check_feature_list.py` — `129 entries in 9 groups; 122 of 139 route sections and menu ids covered` / `5 passed, 0 failed`
- `python -B tools/check_claims.py` — `152 claim(s) checked ... 137 built, 7 still open, 8 unverifiable`
- `python -B tools/check_vacuous_checks.py` — `320 suite file(s) read, 21735 check() call(s) looked at: no check is a fake skip`
- `python -B tools/check_parity.py` — `No undecided drift.` (with three `planned` warnings, which it prints rather than hides)

**The hardware, as measured.** `docs/MEASURED-2026-10-05-owner-pc.md:3-6` calls
itself *"**The first real measurement this project has ever taken on its own
hardware.** Everything in `HARDWARE-PROFILES.md`, `MODEL-TOPOLOGY.md` and
`SECOND-CARD.md` until now was labelled 'calculated, not measured' by its own
text."* It found the RTX 2060 12 GB holding the model and the RTX 2080 SUPER
8 GB running the desktop — **and that the documents had it the other way
round**, which is recorded as a correction rather than quietly fixed (lines
31-37). The rule that came out of it is in `CLAUDE.md`: *"do not switch a
feature on until *that feature* is measured"*, which is why all seven
second-card switches are **off** (`README.md:755-760`).

---

## 7. What it is not

This is the section the project writes about itself, and the fuller live list is
`README.md` → "Honest limits" (line 745 onwards) and `docs/INSTALL.md` →
"Known rough edges". The short version:

- **Not a cloud service, and not a company product.** *"It is one person's
  project, built for one owner, and published so somebody else can run it"*
  (`README.md:48-49`). Non-commercial, sideloaded, never on Play.
- **Rule 1 is bent three times, each named and bounded.** A project's
  "Shareable" switch (off by default), the locked backup file (which may land in
  a cloud-synced folder), and support-chat details (the listed values only,
  per chat). `README.md:80-97` names all three; `docs/ARCHITECTURE.md` §2
  carries the first two with their code and their API sections.
- **Rule 2 has no exception anywhere.** *"**No public tunnel, ever.**"*
  (`docs/ARCHITECTURE.md:65`). No ngrok, no Cloudflare Tunnel, no Tailscale
  Funnel, no "share my Jarvis" (`CLAUDE.md`, rule 2). And the other end too:
  both apps talk only to a Jarvis on the owner's own networks, *"by the
  backend's own rule"*, refused otherwise — *"https:// included (this is about
  where the token goes, not whether the line is scrambled)"*
  (`docs/ARCHITECTURE.md` §2, item 2).
- **The phone is deliberately limited, and each limit has a reason.** It does no
  speech-to-text — *"A client must not do speech-to-text"* (`CLAUDE.md`); it has
  no model catalogue to browse, no memory graph and no deep config editing
  ("Also standing", same file); it reaches the PC only through Tailscale or
  NordVPN Meshnet, *"at home too"* (`README.md:486-489`); and where a feature is
  left off one side on purpose, the reason must be written down in
  `docs/ARCHITECTURE.md` §8, "One-sided on purpose" — which is why the chatbot
  driver's "Try the cloud model" button is *"Left off the desktop's separate
  widget on purpose, not by oversight"* (`DECISIONS.md:956-959`).
- **The approval gap is narrowed, not closed.** A program written specifically
  to attack Jarvis *"can still get around it"* (`README.md:784-787`).
- **Several things are built but never tried for real.** The chatbot website
  conversations, the API conversations, the comparison, the support chat, the
  hidden browser, the inbox tidy (tried against a stand-in mail server, *"never
  a real mailbox"*), and the v1.0 voices — *"Nobody has listened to a v1.0 voice
  yet"* (`README.md:776-783`).
- **Some numbers are still calculated, not measured.** Everyday chat holds
  *"about 4,096 tokens"* and *"the bigger figures for what fits on each card are
  still worked out on paper — none of them is measured"* (`README.md:761-764`).
- **The wake word has never heard a real person.** It was tested against
  synthesised speech, 44 of 44 heard; *"what it does with a real person, a
  television or a phone's battery is unmeasured"* (`README.md:765-767`).
- **The AI-agent collaboration in how this was built is a real part of the
  history, and whether it belongs on a public page is the owner's call, not
  this document's.** See the question at the end of §8.
- **The desktop installer is not published yet** (`README.md:750-754`), the
  updater's own log is not scrubbed, and a token in Windows Credential Manager
  *"can still be read by any program running as you"* (`README.md:788-793`).

---

## 8. "About Jarvis" — how this becomes part of the education material

### What already exists, so this does not duplicate it

The app already has an "About Jarvis", and it is already a checked feature:

- **A card, on the PC.** `jarvis-desktop/src/settings.html:2755-2802`, headed
  `About Jarvis`, with one paragraph and five facts: Version, Made by, Licence,
  Source, Notices. Its paragraph is already a four-line honest summary —
  *"A local-first personal assistant. A Python backend on this computer ... there
  is no public tunnel into this program, there are no API keys built into it, and
  there is no 'approve everything' control anywhere in it."*
- **The phone** reaches the same thing at the end of Help
  (`features/features.json`, the `about` entry: *"Where: Settings, About Jarvis.
  On the phone it is the end of Help."*).
- **It is in the feature list**, in the group "The PC itself", with
  `"asks": "No card."` (same entry, `features/features.json:1397`).
- **It is tested, and it has also been field-tested on real hardware.**
  `jarvis-desktop/tests/about.mjs` is 129 lines and nine
  checks: the five facts are present and in order, the version *"is the real
  running version, not a placeholder"* and tracks `update_status`, the maker is
  *"darknight11ish (owner, 2026-09-26), not an invented company"*, both links
  open in the real OS browser rather than navigating the WebView away, and the
  explanatory note must be *"more than a sentence fragment"* and must contain
  the word "local". Separately, a field-test pass recorded the real card on a
  real machine: *"Help → scrolled to the About card: `Version 0.2.1227`, `Made
  by darknight11ish`, `MIT, with third-party parts under their own licences`,
  the source link, the notices link. Real version, not the local build's
  `0.2.0`"* (`docs/FIELD-TEST-2026-10-11-RESULTS.md:109`) — and, said plainly
  because this project counts honestly, a later pass at a different build
  recorded it **PARTIAL** because *"the version the README-style About card
  shows **was not captured before the window was closed**, so no number is
  claimed for it here"* (`docs/FIELD-TEST-2026-10-13-DESKTOP.md:202`).
- **The teaching place already exists too.** `backend/jarvis_tutorials.py` holds
  a catalogue of tutorials plus a 20-question FAQ, on both apps, with progress
  kept on the PC and shared (`docs/TUTORIALS-DESIGN.md:7-22`, status **BUILT**,
  2026-10-05). It is reached at **Brain → Tutorials and the FAQ** on the PC and
  the phone, and it is feature `tutorials` in `features/features.json:669`.
- **That place is already being redesigned.** `docs/TUTORIALS-DESIGN.md`'s
  second half (line 324 onwards) is *"Interactive tutorials — design"*,
  **DESIGN + FIRST SLICE**, 2026-10-10, and it states its own reversal of the
  first half's decision. Its four-part test for "interactive" and its two
  prohibitions — *"It never acts on Jarvis's behalf"* and *"It never invents a
  control"* (lines 379-388) — are the frame this proposal has to fit inside.

### The proposal, in one line

**One chapter of reading, added to the education place that already exists, with
its own entry point from the About card — not a new tab, not a new screen, and
not one word of new UI code.**

### Where it sits, and why

| Question | Answer | Why |
|---|---|---|
| A lesson, a chapter, a screen, or reading? | **Reading, in chapters** — a new tutorial-shaped entry in `jarvis_tutorials.py`, `section: "both"` | The tutorials are *data* (a catalogue the two apps render), so adding a chapter is content, not code — the same reason the design says the remaining tutorials *"are then content, not code"* (`docs/TUTORIALS-DESIGN.md:307`). |
| Where does a beginner meet it? | **Last in the intro's own row, and offered — never forced** | The intro tutorial ("What Jarvis is") already covers *"what it runs on, where your words go, the five rules"* (`docs/TUTORIALS-DESIGN.md:181`). "How it got here" is the natural second question, and the design's rule is that the intro is *"offered once from the Brain's own list ... never a modal that blocks anything"* (line 161). |
| How does someone who is already past the intro find it? | **One link from the About card**, "How Jarvis was built", opening the same chapter | The About card is already the place a person looks to ask *"what is this and where did it come from"* — the code comment above it says exactly that (settings.html:2749-2751). No second source of truth, and no new route: the tutorials already have three routes (`GET /api/tutorials`, `GET`/`POST /api/tutorials/progress`). |
| Reading inside the tab, or a file? | **The document is the source; the chapter renders from it** | See "how it stays true" below. |

### Phone versus PC: how long, on each

The measurements to argue from are real. The design puts a tutorial at
**4–8 steps, two minutes** (`docs/TUTORIALS-DESIGN.md:177`), and a step is
*"a sentence or two plus a picture of the real screen"* (line 42). The launch
video is 25.6 seconds on the wide cut and 13.6 seconds on the upright one
(`README.md:807-810`).

- **On the phone: about two minutes, six to eight steps, one idea per step.**
  The phone is the wrong place for this page's citation apparatus; a phone step
  should carry the plain sentence and at most one short quote, with the
  quotation's source named in the same line ("his words, 2026-09-28"). A step
  that needs a table is not a phone step.
- **On the PC: the same six to eight steps, plus the full chapter underneath.**
  The PC's education place is *"two halves drawn on one page"*
  (`features/features.json`, the `tutorials` limit), so the step cards stay short
  and the long version — this document, section for section — is what the
  chapter links to when a reader wants the evidence. The PC is where a reader
  will actually follow a `DECISIONS.md:1516` reference, so it is where the
  references belong.
- **The ceiling, stated as a rule rather than a hope:** the chapter should be
  **short enough to read in one sitting on a phone and complete enough to
  answer "why" on the PC**. If a proposed paragraph is longer on a phone screen
  than the tutorial's own two-minute budget, it belongs in the PC half.

### How it stays true as the project changes

This is the part that decides whether the chapter is still honest in a month,
and it is the part the project already has machinery for:

1. **One source, and it is versioned like every other tutorial.** The catalogue
   carries a `version` per entry, and *"A tutorial whose steps changed (higher
   `version`) is offered again rather than being counted done on words the owner
   never saw"* (`docs/TUTORIALS-DESIGN.md:121-124`). A history chapter that
   changes should behave the same way — a reader who finished the old one has
   not read the new one.
2. **Every checkable sentence becomes a claim.** `docs/CLAIMS.tsv` exists for
   exactly this: *"one row per thing this project says about itself, with a
   check a machine runs"*, and `tools/check_claims.py` *"says so when a gap
   closes ... so the row cannot outlive the build the way CLAUDE.md's 'not yet
   built' queue outlived tap-to-talk."* The countable statements in §6 of this
   page are the obvious first rows. **Honest caution:** 8 of the 152 rows are
   `unverifiable` and say why, so a claim in the chapter that no machine can
   check should be written as a quotation with a date on it, not as a fact.
3. **The numbers are re-measured, never remembered.** §6's table names the
   command for every figure, and `tools/check_docs_map.py` already re-measures
   the docs figures on every run. Any number that enters the app's own words
   should come from a checker's output, on the same principle as the About
   card's version, which *"comes from the same `update_status` read the Updates
   section above already makes — never a second, separately-maintained copy of
   the number that could drift from the one actually running"*
   (`jarvis-desktop/src/settings.html:2749-2754`).
4. **"Not recorded" is a value the chapter is allowed to contain.** §1 of this
   page ends with one. That should survive into the app: a chapter that admits
   *"the record does not say"* is more useful to a beginner than one that fills
   the gap, and it is the same rule the app's own refusal wording follows
   ("three kinds of not knowing, kept apart",
   `docs/CUTTING-EDGE-2026-09-26-round4-character.md:100-102`).
5. **The app never claims more than the chapter can prove.** The interactive
   design's own prohibition applies unchanged: *"It never invents a control"*
   (`docs/TUTORIALS-DESIGN.md:386-388`) — and by the same rule, it must never
   invent a date, a motive or a number.

### The one thing that must not happen

**The chapter must not become a second copy.** If the same history is written
once here, once in the app's own strings and once in a README, the three will
disagree within a month — which is the failure this project has already paid for
twice: the hand-written UI fixture that *"agreed with the client and disagreed
with the backend"* (`CHANGELOG.md`, 2026-10-09), and the settings registry where
*"every switch is hand-written in three places ... and nothing tests that the
copies agree"* (`DECISIONS.md:1820-1827`). One source; everything else renders
from it.

### Fitting with `docs/EDUCATION-TAB-DESIGN.md`

**As of the tree this page was written on, `docs/EDUCATION-TAB-DESIGN.md` does
not exist** — `git ls-tree -r --name-only origin/main -- docs` returns nothing
matching `EDUCATION`, and the newest commit on `origin/main` was `1e7d5c2a`
("Merge pull request #402 ... bar-face-clipped"). What exists in its place is
`docs/TUTORIALS-DESIGN.md`, which this proposal is written against directly, and
which the sibling agent may be extending rather than replacing.

**How the two fit together, stated so it holds either way:**

- If the education tab is **an extension of the tutorials and FAQ**, this
  chapter is one more entry in the catalogue the tab already renders — no new
  surface, no new route, and the tab's own design owns the frame.
- If the education tab is **a new screen**, this chapter is content for it, and
  the About card's link becomes a second way in rather than the only one. The
  open questions the education design should answer, and this page deliberately
  does not, are: where the tab lives (its own Brain section, or inside
  Tutorials), whether it is offered at first run, and whether a chapter counts
  as "progress" the way a tutorial does.
- **What this page does claim, either way:** the history belongs *inside* the
  education material rather than beside it as a separate document, because a
  reader who finishes "What Jarvis is" and "What asks first" is exactly the
  reader who asks "why is rule 2 absolute?" — and the answer is a dated
  decision with a quotation in it, which is what the education material is for.

---

## 9. One question for the owner

**The AI-agent collaboration is a real part of how this was built** — agents
working in parallel worktrees, verifying each other, and this very page is an
example of it. The record already says so in public places
(`docs/DEFECT-REGISTER.md:92-98`; `docs/DECISIONS.md:1205-1208`;
`docs/HANDOFF-2026-10-05-tutorials-and-ci.md:86-129`), but a *narrative section about how the project is built
with AI agents* is a different thing from a line in a handoff, and whether that
belongs on a page strangers can read is the owner's call. So this page names the
choice and does not make it.

> **Question for the owner — should the history say how the AI-agent
> collaboration worked?**
>
> - **Say it plainly, in its own short section** — how the parallel worktrees
>   and the checkers that verify each other actually work, and what went wrong
>   (the duplicate repairs, the two confirmations of the same wrong thing).
>   *(Recommended: the project already keeps its mistakes on the record on
>   purpose, and "how it is built" is genuinely part of the history — §3 above
>   already names it without a section of its own.)*
> - **Keep it where it is now: mentioned in passing in the process documents,
>   not a section of its own** — the history then describes what was built and
>   why, and leaves how the sessions were staffed to the handoffs.
>
> Either answer is easy to implement: it changes §3's last three paragraphs and
> one line of the chapter outline. **This page is written so that the second
> answer is what it currently does.**

---

## 10. Where this page's facts come from

The files it leans on, in the order a reader would want them:

| File | What it is |
|---|---|
| `docs/DECISIONS.md` (2,170 lines, 142 KB) | **The record.** The owner's dated decisions from 2026-09-24 to 2026-10-13, moved verbatim out of `CLAUDE.md` on 2026-10-12. Every quotation in §4 and most in §1 comes from here. |
| `CLAUDE.md` | The rulebook (the rules, not the reasons): the five non-negotiables, the standing amendments, the process rules, and the "do not claim more than the evidence supports" rule. |
| `README.md` (849 lines) | The project's own description of itself, including "What it is, and what it is not" and "Honest limits". |
| `docs/ARCHITECTURE.md` (2,801 lines) | The invariants, the one permission model, the egress boundary, and §9 — where the backend lives and where the code came from. |
| `backend/README.md` (19,159 lines) | A section per patch, including the OpenJarvis story and what was deliberately not ported. Its own sentences carry counts from when they were written — *"The paragraphs below were written as the list grew, so the counts in them are the count at the time."* (`:17-18`) — while the opener names the number to trust and where it comes from: *"Both figures come from the `$PATCHES` list in `scripts/apply-patches.ps1`, which is the list the installer actually walks…"* (`:13-14`) That is why §6 counted the files instead of quoting a sentence. |
| `docs/LEARNING-RESEARCH-2026-09-23.md` | The research note that established the OpenJarvis relationship in §1. |
| `docs/FIELD-TEST-HOW-TO-READ-THE-APPS.md` | The field-test method, and the dead ends (§5). |
| `docs/DEFECT-REGISTER.md` + `docs/defect-register.tsv` | The failure record, and the "check the instrument" rule (§5). |
| `docs/CHECKER-CENSUS-2026-10-12.md` | Which checkers exist and whether anything runs them (§3). |
| `docs/TUTORIALS-DESIGN.md` | The education place this page proposes to join (§8). |
| `docs/MEASURED-2026-10-05-owner-pc.md` | The first real measurement on the owner's own hardware (§6). |
| `CHANGELOG.md` (1,311 lines) | Newest-first, one version number for the desktop app, the phone app and the backend files. |
| `videos/README.md`, `videos/v1` … `v6` | Every launch video's brief, plan and share copy, kept and numbered — *"never replace a launch video"* (`CLAUDE.md`, 2026-09-24). |

### Corrections to the brief this page was written from

Recorded here because the project's rule is to say when something in a brief is
wrong rather than route around it:

1. **`docs/JARVIS-EXPLAINED.md` (~60 KB) is not in this repository.** No file
   matching `*EXPLAIN*` exists anywhere under `docs/`
   (`Get-ChildItem docs -Recurse -Filter "*EXPLAIN*"` returns nothing, and
   `git ls-files | Select-String EXPLAINED` returns nothing). The references to
   it in this repository are all to **the owner's own backend folder**, which is
   not published: `docs/BACKEND-PUBLISH-INVENTORY-2026-10-06.md:202-205` lists
   `JARVIS-EXPLAINED.md` among *"The six `.md` files (0.16 MB) ... Exclude from
   the *base*"* — one of which, `JARVIS-API.md`, is there because it is
   *"superseded by `docs/JARVIS-API.md`"* — and `docs/AUDIT-2026-09-14.md:663`
   cites its §3 as explaining the wake word design. **Consequence: everything
   this page says about the wake word, the voice-print gate and barge-in comes
   from repository files, and one source the brief named could not be read at
   all.**
2. **The brief's list of decisions to mine named `docs/HANDOFF-2026-10-04-*.md`
   as a gloss** (singular). There are two:
   `docs/HANDOFF-2026-10-04-audit-pass.md` and
   `docs/HANDOFF-2026-10-04-test-suite-fixes.md`, plus
   `docs/HANDOFF-AFTER-PR39.md`, which `CLAUDE.md` points a new session at.
3. **`docs/EDUCATION-TAB-DESIGN.md` did not exist** on `origin/main` at the time
   of writing (§8), so this page could not align with it and aligned with
   `docs/TUTORIALS-DESIGN.md` instead, which is the education material that does
   exist and is built.
4. **The brief says the record covers "2026-09-24 to 2026-10-11"**; it now
   reaches **2026-10-13** (`docs/DECISIONS.md:2100`, `:2138`, `:2080`, `:2008`).
   The 2026-10-13 entries are the newest and the most instructive reversals in
   the file, so leaving them out would have been the wrong call.
