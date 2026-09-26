# Skills that run code: design

Short version: skills can now run a small Python script, but only after you
have seen the whole script and the exact input and said yes. That happens
every time. The skill cannot choose how risky it is said to be, and neither
can the model.

## 0. First, something in the brief is wrong

The brief asks for a new `backend/jarvis_skills.py`. **Your machine already
has a file with that name, and it is the only copy.** Evidence:

- `backend/skill-notes.patch` patches `jarvis_skills.py` (its `cards()` and
  `refine()` functions, at original lines ~691 and ~831).
- `backend/rebuilt/jarvis-framework.toml:461-485` describes what that file
  does: it reads SKILL.md folders, scans them before the model sees them,
  gives each one a trust level (`self`, `local`, `third_party`), and asks you
  before it installs anything. It also says, at line 474: *"Bundled scripts
  are NEVER run by the loader."*
- `docs/ARCHITECTURE.md:387` says there is no second copy of the backend
  files anywhere.

So writing a new file with that name would overwrite the only copy of a
working module. The code here is therefore called **`jarvis_skill_tools.py`**.
It sits beside the old one and does only the one thing the old one refuses
to do: run a skill's script. Finding skills, scanning them and installing
them is still the old module's job. This one asks it for two things
(`scan_text` and `cards()`), and if it cannot reach them it refuses to run
anything.

I have **not** seen your `jarvis_skills.py`. I know only what the patch and
the TOML comment say about it. Section 7 lists what that leaves unchecked.

## 1. What changes for you

Today, if a skill wants a script run, the model has to write a shell command
for it. That command reaches the gate as `run_shell_on_host`, and the model
wrote every character of it.

With this module, a skill folder can include one extra file,
`jarvis-tool.toml`:

```toml
entrypoint = "scripts/convert.py"   # one Python file inside the skill folder
timeout_seconds = 20
effects = ["compute"]               # what the skill SAYS it does

[params.amount]
type = "number"
required = true
minimum = 0

[params.unit]
type = "string"
enum = ["km", "mi"]
default = "km"
```

The model then gets a tool called `skill__convert` with those parameters and
nothing else. When it uses the tool, you get an approval card showing:

- who wrote the skill (you, Jarvis, or someone outside)
- the exact input, defaults included, exactly as the script will receive it
- what the skill says it does, and what a read of its code actually found,
  line by line
- a plain sentence saying what Jarvis **cannot** promise (see section 5)
- a fingerprint of every file, then the full source of every Python file
- what happens if you say no

## 2. How a skill's risk level is decided (by code, never by the model)

| input | where it comes from | can the skill change it? |
|---|---|---|
| trust | `jarvis_skills.cards()`, which your approved install wrote. If missing, `third_party` | No. A `trust:` line in SKILL.md or jarvis-tool.toml makes the skill fail to load |
| effects | what it declares, **plus** what a read of its code finds | Only upward. Anything the code-reader does not recognise counts as "could do anything" |
| action | `skill_run_untrusted` / `skill_run_local` / `skill_run_local_network` | No. It is worked out from trust and effects |
| tier | your `jarvis-framework.toml` for that action | No. And anything other than `ask` does **not** run (see below) |

**Refused outright.** These never reach the approval queue, so you are never
asked about them:

1. The scanner in `jarvis_skills` blocks it, crashes, or cannot be found.
2. It reads private data **and** can reach the network or start other
   programs. Private data stays on this machine, whoever wrote the skill.
3. It is not your own code (`self` or `third_party`) **and** it can reach
   the network, start programs, or does something the code-reader cannot
   see (`eval`, `exec`, an unrecognised import).
4. It is not your own code, and it does more than it says it does.
5. It can reach the network, and this conversation has read something
   private, or that cannot be checked right now (`jarvis_gate.taint_active()`).

**Everything else waits for you.** There is no lower level than `ask`. If
`jarvis-framework.toml` sets one of these actions to `auto` or `notify`, the
skill is refused, and the refusal message names the line to change. This is
the same pattern `skill-notes.patch` uses for `refine()`. The reason: nothing
checks what a script actually does while it runs. There is no sandbox (the
decision at `ARCHITECTURE.md:435` is "git worktrees, not Docker"), so a
skill's list of effects is a claim, not a fact.

A skill **Jarvis wrote** (`self`) is treated like one from outside. You
approved its install, but approving code is not the same as having written
it.

## 3. The four steps, the same as everywhere else

This follows `ARCHITECTURE.md` section 3 (line 67), in the shape of
`jarvis_research.py`:

- **`discover()` / `load_skill()`**: reads the folders, checks them strictly
  and scans them. Runs nothing, opens no connection. The tests prove this by
  making sockets and new processes raise an error.
- **`plan(skill, args)`**: checks the model's arguments strictly (section 4),
  and refuses if any file changed since the scan. Takes no tier, trust or
  action: the tests check its signature.
- **`describe(plan)`**: the card. Nothing on it is shortened.
- **`run(plan, verdict)`**: takes the gate's own answer object, **not** an
  `approved=True` flag. It runs only if tier is `ask`, the outcome is
  `approved`, and the answer was for this action. It copies the skill to a
  private folder, checks the copy's fingerprints against the card, then runs
  **the copy**. So the file that runs is the file you read.

`invoke()` does plan, card, one gate call and run for callers outside the
chat loop. Nothing is remembered between calls, so the next use asks again.

## 4. Strict input types

The model's arguments are checked in code. Ollama's tool schema is only a
hint to the model.

- Types: `string`, `integer`, `number`, `boolean`, `string_list`. There are
  no nested objects.
- Values are never converted. `"5"` is not an integer. `5.0` is not an
  integer. `true` is not a number or an integer. In Python, `True == 1`, so
  without this check a yes/no answer would quietly become a number. NaN and
  infinity are refused.
- An argument the skill did not declare is an error, not ignored. So
  `{"tier": "auto"}` fails like any other wrong key.
- Each error is a sentence for the model to retry from, e.g. `count:
  expected a whole number, got str "5"`.
- Defaults are filled in before the card is shown. The card shows everything
  the script will get.

## 5. How it runs, and what that does NOT protect

- It runs `python -E -s -X utf8 -B <copy>/<entrypoint>` as a list of
  arguments, with no shell. The input goes in as JSON on standard input, not
  on the command line.
- It gets a **short list of environment variables and nothing else**:
  `SYSTEMROOT`/`WINDIR`, a PATH holding only Python's own folder, and a
  private temporary folder. Tokens and passwords (`JARVIS_GITHUB_TOKEN`,
  `HUD_TOKEN`, the IMAP password) are never passed on. A test sets all three
  and checks that the script sees none.
- There is a time limit (1-120 s) and an output limit (64 KB). Output goes to
  files, not memory, so a skill that prints forever cannot fill RAM.
- The result is marked `untrusted_output: true`.

**What it does not protect:** the script runs with your Windows account's
permissions. If its code opens a network connection or reads a file in a way
the code-reader does not recognise, nothing stops it. The code-reader can be
fooled on purpose. That is why a skill from outside is refused as soon as
anything unusual shows up in its code, and why the card says this in plain
words.

## 6. Wiring still to do (none of it applied)

The module does not wire itself in. Every item below is written down and not
applied, because each one changes a file on your machine.

1. **`jarvis_agent.py`: pass the gate's answer to the tool.**
   `jarvis_agent-verdict.diff` (9 added lines). It applies cleanly to this
   repo's `backend/jarvis_agent.py` (checked with `git apply --check`, which
   changes nothing). Without it, every skill call is refused, which is the
   safe way for it to be missing. The reason it is needed:
   `jarvis_agent.py:771` checks only `allowed`, and `allowed` is also True
   for `auto`/`notify` with nobody asked (`ARCHITECTURE.md:98`).
2. **The gate's own table (`jarvis_gate.py`)**: add three `_RISK` rows next
   to `run_shell_on_host` (`ui-control-wiring.patch:5`), all rated like it
   (`"no", "outbound"`), with this wording:
   - `skill_run_untrusted`: "runs code from outside on this PC"
   - `skill_run_local`: "runs a script you wrote on this PC"
   - `skill_run_local_network`: "runs a script you wrote that can reach the
     internet"

   Until then, these names fall back to `_UNKNOWN_RISK`
   (`ui-control-wiring.patch:22`) and to `unknown_action_tier = "ask"`
   (`jarvis-framework.toml:70`). So they still ask, but the card shows a
   generic reason instead of the one above.
3. **`jarvis-framework.toml` `[autonomy.tiers]`**: three lines, all `"ask"`.
   Set any of them to `"never"` to turn that kind off.
4. **HUD**: at startup, merge `jarvis_skill_tools.agent_tools()` into
   `jarvis_agent.TOOLS`. A skill tool is offered only if its name
   (`skill__<name>`) is listed in `[tools].enabled`. That is the same opt-in
   `browser_control` uses (`jarvis_agent.py:24-28`).
5. **A place to see it**: add `jarvis_skill_tools.cards()` to what
   `GET /api/skills` returns (`JARVIS-API.md:342`). It includes refused and
   rejected skills, each with its reason, so a skill never disappears
   without you being able to see why. `/api/skills/decide` stays
   removal-only (`JARVIS-API.md:378`).

Skipping step 4 or 5 is exactly the "capability with no call site" problem
`ARCHITECTURE.md` warns about. Until they are done, this module is a tested
library that nothing calls yet.

## 7. What was not checked

- **Your `jarvis_skills.py`.** Everything below comes from the patch and a
  TOML comment only:
  - that `scan_text(text, label)` returns findings with a `.severity` field
  - what the reason field on a finding is called (the code tries `reason`,
    then `message`, then `rule`, then `str()`)
  - that `cards()` lists every installed skill with its `trust`
  - which folder your skills live in. The default here,
    `~/.openjarvis/skills` or `$JARVIS_SKILLS_DIR`, is a guess based on where
    OpenJarvis keeps them (`skills/importer.py:69`)
- **Not run on Windows.** Tests ran on Linux with Python 3.11. None of these
  has been seen working on your machine:
  - detecting Windows junction folders
  - stopping the whole process tree with `taskkill /T`
  - hiding the console window (`CREATE_NO_WINDOW`)
  - Python starting with only `SYSTEMROOT` in its environment
- **Programs a skill starts are not stopped reliably.** On Linux, a timeout
  stops only the script itself, not any program it started. On Windows,
  `taskkill /T` should stop the whole group, but that is untested.
- **Ollama and `additionalProperties: false`.** Whether Ollama passes this
  through to the model has not been checked. It does not matter for safety,
  because the check happens in code (section 4).
- **The table from the other AI.** I did not have it. Everything about
  OpenJarvis below comes from reading its code myself, not from the table.
- **Python only.** A skill in any other language is not accepted, because
  there is no code-reader for it.
- **Changing the rules for any running tool.** An `auto` setting still runs
  other tools with nobody asked (`jarvis_agent.py:771`). That is the existing
  behaviour for `auto` tools, and I did not change it. Only skills insist on
  a person's yes.

## 8. What OpenJarvis actually does (read from source, commit e86c582)

| claim you might hear | what the code says |
|---|---|
| "strict agentskills.io validation" | The strict parser exists (`skills/parser.py:91-156`), but `load_skill_markdown` catches its error and builds the skill anyway, with no checks: `skills/loader.py:186-202` ("Legacy fallback"). It also never checks that the name matches the folder, which the spec requires (`agentskills docs/specification.mdx:65`). |
| "capability-based security for skills" | The checks read `required_capabilities`, which is the skill's own claim (`skills/security.py:44-55`). The skill-level check is off unless someone passes `allowed_capabilities` (`skills/executor.py:46-50`), and nothing in `src/` does (a grep finds no `allowed_capabilities=`; `manager.py:199,214,385` build the executor without it). A per-tool check does exist in `ToolExecutor` when a policy is configured (`tools/_stubs.py:328-366`, set up by `cli/skill_cmd.py:183`). |
| "typed tool parameters" | A pipeline skill's inputs are all `"type": "string"` (`skills/tool_adapter.py:50-95`). The command line splits `k=v` into text (`cli/skill_cmd.py:171-175`). Arguments go straight to `tool.execute(**params)` (`tools/_stubs.py:437`) with no check against the schema. A grep for `jsonschema` in `src/` finds nothing. |
| "scripts are gated" | They are copied only with `with_scripts=True` (`skills/importer.py:149,194-202`). OpenJarvis never runs them itself; the model would have to run them through a shell tool. |
| "dangerous skills need confirmation" | Only if the skill **declares** a dangerous capability (`skills/importer.py:116-139`). A skill that lists none is not flagged. |
| worth copying | Refusing symlinks in imported folders (`skills/importer.py:151-168`): adopted here, and extended to Windows junctions. |
| worth avoiding | Step arguments are filled in by plain text substitution, so a value containing `"` can inject extra JSON keys (`skills/executor.py:206-216`; from reading the code, not run). "Overlay" files from a learning folder rewrite a skill's description with nobody approving (`skills/manager.py:127-150`), which is the same problem `skill-notes.patch` fixed. The `.source` file is written by pasting text into TOML without escaping it (`skills/importer.py:259-269`). |

agentskills.io itself (`agentskills/agentskills` at 69ef37e,
`docs/specification.mdx`):

- **Fields.** The spec's fields are at lines 27-32. This module reads only
  those.
- **`allowed-tools`.** The spec defines it as "tools that are pre-approved
  to run" (`specification.mdx:32,163-173`). Jarvis never pre-approves
  anything, so the card shows this field and says it is ignored.
- **Names.** The reference validator accepts any Unicode letter in a name
  (`skills-ref/src/skills_ref/validator.py:54`). This module accepts only
  a-z, 0-9 and hyphens, as the spec's own text says (`specification.mdx:62`),
  so a look-alike name such as a Cyrillic "а" cannot pass as another skill.
- **Frontmatter.** It is read by a small hand-written reader rather than a
  YAML library, so there is no new dependency. It refuses the YAML features
  the spec never uses (anchors, tags, multi-line text, repeated keys), which
  are how two programs can read the same file differently.

## 9. Licence

- OpenJarvis is Apache-2.0 (`openjarvis/LICENSE`).
- agentskills code (`skills-ref/`) is Apache-2.0. Its documentation,
  including the spec, is CC-BY-4.0 (`docs/LICENSE`).
- **No code was copied from either.** `jarvis_skill_tools.py` was written for
  this project. What it takes from them is facts and ideas: the spec's field
  names and naming rules, and the idea of refusing symlinks. Using those does
  not require a licence notice.
- If code from either project is copied in later, keep its Apache-2.0 header
  and credit it in a NOTICE. Apache-2.0 allows that in a non-commercial
  project.
- Quoting the spec text itself would need credit under CC-BY-4.0.

## 10. Files

- `jarvis_skill_tools.py`: the module.
- `test_skill_tools.py`: 111 checks, all passing
  (`python3 test_skill_tools.py`). This includes loading the **real**
  `backend/jarvis_agent.py`, once as it is and once with the diff applied to
  a temporary copy.
- `jarvis_agent-verdict.diff`: the one change needed in the chat loop.
