# The self-code map: how Jarvis knows its own code

Jarvis runs from this repository, but until 2026-11-07 it could not say so:
asked *"what is your own GitHub repository?"*, the live backend answered "I
don't have a public GitHub repository of my own". The version, the tools and the
feature list were all answerable; the code itself was not.

**The self-code map is a generated index of this repository's major parts, shipped
beside the backend.** It is not a code reader and not a model: it is one JSON
file, `backend/jarvis-self-code.json`, that lists every part of Jarvis's own code,
the files each part owns, the module to start reading for it, and the tests and
documents that go with it. Jarvis answers "what are your major parts", "where is
the code for X", "what changed recently" and "what is your GitHub repository" from
that file, with no model and no code execution.

## What is in it

- `repo`, `public`, `ref`, `built_at`, `version` - the public repository, the
  commit the map was built from, that commit's own date, and the version read
  from `VERSION`.
- `architecture` - the five runtime parts in the order they fit: the backend on
  the PC, the models in Ollama, the Tauri desktop shell, the Android client over
  a private network, and the public repository with its CI and deploy pipeline.
- `subsystems` - one row per major part of the code (27 of them). Each row has a
  one-sentence purpose, every file it owns, up to a handful of **key modules**
  with the first sentence of each module's own docstring, the suites that prove
  it, the documents that describe it, and its areas (backend / base / desktop /
  android / tools / docs / ci).
- `recent_commits` - the newest 20 subjects and dates at that commit, so Jarvis
  can say what changed around the deploy that built the map.
- `top_level` - the repository's major directories, one plain line each.
- `coverage` and `excluded_patterns` - how many files were covered, how many were
  skipped and by which named pattern.

The file is about 300 KB. It names code; it does not contain code bodies.

## How it is built

`tools/gen_self_code_map.py` is deterministic, standard-library only and opens no
socket. Run it from the repository root:

```powershell
py -3 tools/gen_self_code_map.py            # write backend/jarvis-self-code.json
py -3 tools/gen_self_code_map.py --check    # compare, exit 1 on drift
```

It walks the tree a commit would carry (`git ls-files --cached --others
--exclude-standard`), reads `VERSION`, reads each key module's docstring with
`ast` (it never imports the module), and reads the newest commits with
`git log`. It writes with LF endings and no absolute path anywhere.

**Completeness is checked by construction.** Every file belongs to exactly one
subsystem, from the table in the generator. The generator exits non-zero and
names the paths when a file belongs to *none* or to *two* - so "every major part"
is a property a machine proves, not a claim in this document. Generated, binary
and vendored files are skipped by an explicit named list, and each count is
printed and stored in the map, so nothing is dropped silently. A reference the
tree no longer holds (a key module, a test or a doc that moved) also fails the
run rather than being quietly left out.

`--check` re-derives the whole document in memory and compares it byte for byte
with the committed file, printing the first differing line. Two details make that
check honest rather than self-referential:

- the commit fields (`ref`, `built_at`, `recent_commits`) are taken from the map
  being checked, not from the checkout. They describe the commit the map was
  built from; re-deriving them from `HEAD` would make every later commit a false
  drift.
- it refuses a dirty tree **when the map itself is clean**, because then "the map
  still matches" would be an answer about code nobody committed. When the map is
  one of the changes, a dirty tree is the point - you are building it.

## What it cannot do, plainly

- **It does not read code bodies.** It knows a module's path and its first
  docstring sentence. Ask it *what* a part does and *where* it lives; it cannot
  quote a function or explain an algorithm.
- **It never runs anything.** No import, no subprocess, no model, no socket. A
  file that will not parse simply gets no summary.
- **It knows nothing newer than the deploy that built it.** The reader
  (`backend/jarvis_self_code.py`) reads the JSON beside itself and nothing else -
  no git, no network, no writes. A question about code merged after that deploy
  is answered with "not in the map I was built with", never with a guess.
- **It is a map, not an authority.** When the map and the code disagree, the code
  wins and the map is stale - which `--check` is there to catch.
- **It is a beside-file, so it travels in two copies.** `backend/jarvis-self-code.json`
  and `jarvis-backend/jarvis-self-code.json` are byte-identical, the same
  two-file rule every shipped module follows. `backend/test_base_matches_repo.py`
  and `tools/check_stale_twins.py` prove it.

## How to refresh it

On a branch, after any change that adds, moves or renames files - and after a
change to a key module's docstring or to the subsystem table:

```powershell
py -3 tools/gen_self_code_map.py
py -3 tools/gen_self_code_map.py --check
Copy-Item backend\jarvis-self-code.json jarvis-backend\jarvis-self-code.json
py -3 backend\test_self_code.py
```

Commit both copies in the same change, with the code they describe. `--check`
in CI (and `backend/test_self_code.py` at the desk) fails when they drift.

## What reads it

- `backend/jarvis_self_code.py` - the shipped reader: `available()`,
  `map_info()`, `overview()`, `lookup(topic)`, `recent()`, `self_repo()`.
- `backend/jarvis_quick.py` - four deterministic chat intents over that reader:
  the overview, a lookup, the recent changes, and the repository identity.
- `docs/ARCHITECTURE.md` §20 - where the capability sits among the others.
- `docs/CLAIMS.tsv` - one row, checked by `backend/test_self_code.py`.
