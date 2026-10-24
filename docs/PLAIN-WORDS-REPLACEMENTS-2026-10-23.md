# Plain words for developer words (2026-10-23)

**What this page is.** A small dictionary for Review #8. When a message in
Jarvis shows a word from the code's own world, this page says what to write
instead - in words a beginner can read once and act on.

**How the scanner and this page fit together.** `tools/check_zero_jargon.py`
finds the developer words in the strings Jarvis shows you, with a file and line
for each one; this page is the wording to use when you fix one. The scanner only
reports - it never rewrites a word - and its `--check` ratchet stops the count
going up while the fixes are done one screen at a time. This page is the other
half: the words to write instead. (The two-word version: the scanner finds them,
this page replaces them.)

## The dictionary

Each row is a **suggestion**, not an edit that has already been made. The
left-hand column is what the code says; the right-hand column is what the owner
should read.

| Developer word (what the code says) | Write this instead (what a beginner reads) | Note |
|---|---|---|
| `taint` / `tainted` / `untainted` / `taint_latch` | "outside text from the web or email" | Never show the internal state word. |
| `latch` / `rush_latched` / `latch is cleared` | "this was switched on by a check" | Same rule: say what happened, not the state name. |
| `FTS5` / `BM25` / `RRF` | "word and meaning search" | The search feature, in plain words. |
| `ONNX` / `cosine` / `cosine similarity` | "the on-PC model that turns words into numbers" | It runs on your PC; nothing leaves it. |
| `from_this_pc` / `loopback` / `localhost` | "on this PC (not from a phone)" | Says where the request came from. |
| `target_digest` / `digest_mismatch` | "this approval card changed since it was shown - please review the updated card" | Give the recovery step, not the check's field name. |
| `HTTP 500` / `HTTP 404` / `status 422` | "your PC said it could not do that" + the PC's plain reason | Never the number alone. |
| `SQLITE_BUSY` / `WAL` / `wal_checkpoint` | "Jarvis is saving something; try again in a moment" | Names what to do next. |
| `ECONNREFUSED` / `ENETUNREACH` / `socket` / `timeout` | "Jarvis cannot reach your PC right now - check the link, then try again" | Names the action. |
| `null` / `None` / `undefined` / `NaN` | "not set yet" / "no answer yet" | Say what is missing. |
| `payload` / raw JSON fragments | "the details it sent" | Never paste JSON at a person. |
| `extraction is a scaffold; review its proposals and tune the prompt...` | "New facts wait under 'Waiting for you' below until you approve them." | Already removed from the shipped code by a shipped patch. |
| module names (`jarvis_*.py`), snake_case config keys, exception class names, `traceback`, `stdout`/`stderr`, `errno` | Say what happened in plain words and what to press; keep the key name only if the owner must type it | One sentence, then the next step. |

## A worked example

Before (a refusal that names the code's own words):

```json
{"error": "HTTP 404"}
```

After (what happened, then what to do):

```json
{"error": "Jarvis could not find that page on your PC. Check the address, then try again."}
```

The second one takes the same space, says the same fact, and leaves the owner
with something to do.

## What this page is not

- **It is not a cleanup.** The recorded baseline is **255** developer-word hits
  and **25** bare refusals (`docs/REVIEW-8-ZERO-JARGON-2026-10-23.md`). Fixing
  them is follow-up work, done in small batches - one surface per pull request -
  not during a merge freeze.
- **It is not a promise the word is wrong.** A hit is a candidate: a person
  reads the path and line and decides. Some technical words are deliberate - the
  model names (`Ollama`, `qwen`), `HTTPS`, `PIN`, `Tailscale`, `Meshnet` and
  `API key` are on `tools/zero-jargon-allow.txt` because the owner has chosen to
  see them.
- **It does not cover every message.** The scanner reads strings it can see, so
  a sentence built at runtime out of pieces cannot appear in its list.

## The five terms added on 2026-10-23

`target_digest`, `cosine`, `SQLITE_BUSY`, `ECONNREFUSED` and `ENETUNREACH` -
the terms Section 3 of the owner's work order names - became scanner rules on
2026-10-23, each with a test that proves it is caught and a plain-English word
near it is not ("busy", "refused", "unreachable", "target", "daily digest",
"cosign"). The tree showed no user-facing copy using any of them that day, so
the recorded baseline stayed at 255 + 25.
