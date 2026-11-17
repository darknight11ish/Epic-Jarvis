# bench_coding - the coding & hybrid routing benchmark

    py -3 tools\bench_coding\run.py                  # run the measurable rows
    py -3 tools\bench_coding\run.py --dry            # list every row; send nothing
    py -3 tools\bench_coding\run.py --self-test      # this tool's own suite
    py -3 tools\bench_coding\run.py --only T1.1 --timeout 300
    py -3 tools\bench_coding\run.py --json-out results.json --report report.md

This is the measurement half of the 2026-11-16 spec
(`Downloads/for_deepseek_2026_11_16_2023pt_jarvis_coding_and_hybrid_benchmark.md`).
It drives the **live** backend at `http://127.0.0.1:4719` the way a client does
and judges each task from the exact command's exit code, never from the
answer's words.

## What it measures, and how

| The spec asks for | What this harness actually reads |
| --- | --- |
| route (`X-Jarvis-Route`, `local` vs `jarvis-escalate`) | the real `X-Jarvis-Route` **response header** of every `POST /api/chat`, kept verbatim as JSON. It reports `lane` (which model answered), `where` (`local`), `gate`, `reason`, `tainted`, `auto`, `offer` - there is no two-word `local`/`jarvis-escalate` value to read. |
| tokens/s | `~/.openjarvis/speed.jsonl`, whose first line is the schema. Real fields: `prompt_tokens`, `cached_tokens`, `tokens`, `tokens_per_s`, `total_ms`, `first_word_ms`, `prompt_rounds`, `tools`. There is no `completion_tokens` field; `tokens` is the completion count. |
| cloud `$` | the delta of `~/.openjarvis/chatbot/api-money.json` (`months.<month>.<service>.dollars`). **`daily-budget.json` does not exist** on this PC - there is no daily cap - and the report says so instead of inventing one. |
| git cleanliness | `git status --short` and `git diff --stat` **inside the disposable repo**, after every coding row, always. |
| a throwaway repo | every row gets a NEW `git init` repository under `%LOCALAPPDATA%\Jarvis\bench-coding`, with **no remote at all**. Nothing reads or writes this checkout, `origin/main`, or any live Jarvis file. |

Each chat turn is `POST /api/chat` with `stream: false`, `temporary: true` (so
the run leaves no conversation in the owner's history and depends on no
remembered fact), `X-Jarvis-Client: hud`, and a **hard wall-clock deadline**
(a keepalive trickle cannot hold it open).

## The disposable project

`fixture.py` writes `bench-shop`, a small Python project with a real pytest
suite and a real ruff config. It carries the three seeded defects the spec
names, each with one failing test:

* an **OR-query bug** in `src/shop/search.py` (`match="any"` joins with AND);
* a **missing dict key** in `src/shop/pricing.py` (`"gift-card"` is not
  normalised, so the lookup raises `UnknownSku`);
* an **off-by-one** in `src/shop/paginate.py` (page 1 starts at -1 and is empty);
* plus the **four-file float -> integer-cents refactor** T2.3 needs.

A row's pass criterion is its own exact command, e.g.
`pytest -q tests/test_search.py`. The other seeded defects are deliberately
still there - the spec names three - and the report prints both the scoped
command's exit code and why.

pytest and ruff come from a benchmark-only virtual environment at
`%LOCALAPPDATA%\Jarvis\bench-coding\venv`, made once and reused. They are never
installed into the owner's Python.

## The states, and BLOCKED is never a pass

* **PASS** - the row ran and its own criterion was met, measured.
* **FAIL** - the row ran and its criterion was not met.
* **BLOCKED** - the row could not be measured: an open PR, an unbuilt feature, a
  setting the harness must not flip, or a known live defect another lane is
  fixing. Not a pass, not a failure of the product.
* **NOT-RUN** - `--only` did not select it (and `--dry` sends nothing).

Exit code 0 when every row that ran passed (BLOCKED is counted on its own line,
not as a failure of the run), 1 when a measured row failed, 2 when the run could
not start (no token, no live backend, no benchmark environment).

## What it will not do

* It never writes to, commits to, or checks out a branch in this checkout.
* It never approves a card. It DOES decline a card that appears during one of
  its own turns: a no executes nothing, and without it one tool call the model
  makes would hold the turn for the card's whole lifetime. Every declined card
  (id, action, answer) is recorded in the JSON and the report.
* It never prints, logs or saves the pairing token (`jarvis_token_store.py show`
  is read into memory, and every string is scrubbed before it is written).
* It never flips a setting, starts a model or switches a preset unless
  `--apply-preset` is passed - and even then it cannot answer the `switch_model`
  card a Coding apply raises, so it reports what happened instead of forcing it.
  The preset state before and after is recorded.

## Why this is separate from `backend/jarvis_bench.py`

`jarvis_bench.py` measures **a model**: tokens a second, RAM/GPU placement,
context sizes, across repeats, with its own store (`bench.jsonl`). This measures
**task outcomes through the whole product**: which lane answered, whether the
code passed its real tests, what the cloud cost, what was touched, and what the
honest verdict is. Neither reads the other's numbers, and this tool never opens
`bench.jsonl`.

## Its own suite

    py -3 tools\bench_coding\run.py --self-test

62 stdlib `unittest` tests under `tools/bench_coding/tests/` (nothing is
registered in `backend/`, so CI's alphabetical shard order is untouched). They
prove the fixture's defects are real, that an answer can only write inside a
disposable repo, that an `X-Jarvis-Route` header is parsed as measured, that a
BLOCKED row can never be scored as met, that the harness has no approve route,
never prints the token, never pushes and never checks out a branch.

## What it could not measure on 2026-11-16

The live state is part of the record, not a footnote:

* **The coding preset's pooled lane was not loaded.** The live PC reported the
  coding preset as chosen, but chat was pointed at the everyday lane and
  `qwen3-coder-30b-a3b-ud-q3-k-xl` was loaded there at **8,192 tokens** of
  context with about 3.5 GiB spilled into system RAM - not the preset's own
  49,152-token pooled lane. The rows that ran measured the model the product
  actually served, at that window; the report says so per row.
* **The cloud could not be reached by design.** The cloud escalation switch is
  off and a taint latch was active, so T3.1's cloud leg and all of T3.2 are
  BLOCKED.
* **`X-Jarvis-Route` is a real header with a JSON body, not the spec's two-word
  flag.** `lane` + `where` are the honest fields; the whole header is in the
  JSON.
* **No tool-call names in telemetry.** T1.3's "0 write tools" is measured by
  whether an approval card was raised, the only write-tool signal these files
  carry.
* **`speed.jsonl` under-reports completion tokens on a tool-loop turn.** One
  measured row from 2026-11-16 has `words: 703` and `tokens: 1` after three
  prompt rounds; the PC's own writer counts only the last round. The harness
  reports the row as written and flags it, rather than recomputing a nicer
  number.
