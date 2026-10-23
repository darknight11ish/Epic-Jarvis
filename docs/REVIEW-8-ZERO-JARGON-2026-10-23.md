# Review #8 — zero-jargon baseline (2026-10-23)

**What this page is.** The opening measurement for Review #8 of the 10-Review
Playbook ("Zero-Jargon Beginner Readability & Error-Recovery Scanner"), made by
`tools/check_zero_jargon.py` on the tree of `main` = `4a98fd496`, 2026-10-23.
It records the real number and the top offenders; **it does not clean them**.
Cleaning the wording is follow-up work, done in small PRs against the recorded
baseline (the tool's `--check` ratchet is what keeps it from growing).

**The measurement (read it, do not quote it as something better or worse):**

- **255** user-facing developer-word hits, across
- **688** files scanned (194 backend shipped modules, 9 desktop HUD files,
  111 Rust source files, 374 Android Kotlin/XML files);
- **25** bare refusals - a user-facing message that says neither what happened
  in plain words nor what to do next (Review #8's second half).
- The full machine-readable report, with every path:line, word and string, is
  `docs/REVIEW-8-ZERO-JARGON-BASELINE-2026-10-23.json`.

| surface | hits | what it mostly is |
|---|---|---|
| backend | 192 | internal field names and Python module names inside messages (`sha_before`, `allowed_domains`, `element_token`, `jarvis_hud.py`), the state words `taint`/`latch`, `localhost` |
| desktop Rust | 53 | `HTTP 404` / `HTTP {code}` in command errors, and raw `null` in JSON-shaped error text |
| Android | 9 | `HTTP 500`-style words in user messages, `latch` in the Brain screen's wording, a `None` settings label |
| desktop HUD page | 1 | a developer command shown in the page's own text (`start py -3 jarvis_hud.py ...`) |

**Top terms:** config key ×100, jarvis module ×52, HTTP ×29, taint ×16,
null ×16, latch ×10, payload ×9, None ×7, ONNX ×4, exception class ×1,
from_this_pc ×1, localhost ×1, WAL ×1, API ×1.

**Representative findings (plain words):**

- `backend/jarvis_browser_control.py:2800` — "bind_tab needs the tab's own id - nothing was bound" (a tool's internal action name in a message).
- `backend/jarvis_brain_reads.py:400` — "Say which file and which saved version (path and sha_before)."
- `backend/jarvis_arbiter.py:537` — "Send one of these: spoken_per_day, digest_hour."
- `backend/jarvis_big_model.py:591` — "[big_model] coli_path is ..." (a config section and key).
- `jarvis-client/.../net/ForgetRange.kt:376` — "Not done. Your PC said no (HTTP ${reply.code})." (a status code where the owner needs the PC's plain reason).
- `jarvis-client/.../ui/screens/BrainScreen.kt:1597` — "Nothing is approved from here. A latch is cleared where the scanner runs."
- `jarvis-desktop/src-tauri/src/attention.rs:179` — "HTTP 404" (a bare status code as a command error).
- `jarvis-desktop/src/jarvis_hud.html:1818` — "Jarvis is not answering yet — start `py -3 jarvis_hud.py` on your desktop, then reload."
- Bare refusals (all 25 in the JSON) are short status-like messages such as
  `"error": "refused"`, `"error": "denied"`, `"error": "not found"`,
  `"error": "failed"`, `"error": "unavailable"` — the owner gets a state, not a
  next step. The full list is `bare_refusals` in the JSON.

**What is scanned, and how to read a finding.** The tool reads the strings the
three products show in an answer, a refusal, a card, a HUD label, a Rust
command error, an Android resource string or a Compose literal, and reports
developer words inside them. It is a **candidate list**, not a proof: it works
from context markers (`"error":`, `words:`, `textContent =`, `Err(...)`,
`Text(...)`, and every `strings.xml` value), so a sentence built at runtime out
of variables cannot be seen, and a marked line can occasionally catch a
string aimed at the model rather than the owner. Each finding names its path
and line so a person can judge it in seconds.

**What is deliberately not flagged.** Docstrings and comments (developer text,
not user words); SQL statements (code, never read by a person); dict/JSON keys
(`"error":` is the label, not the message); a bare number like `500` (because
`$500` is money - only `HTTP 500`/`status 422` forms are flagged); and the
allowlist in `tools/zero-jargon-allow.txt` (model names, `HTTPS`, `PIN`,
`Tailscale`, `Meshnet`, `API key`, ... - words the owner has already chosen to
see). An allowlist phrase does not swallow a bare term: "API key" passes while
a bare "API" in the same sentence still fails.

**How to run it, and the ratchet.**

```powershell
python -B tools/check_zero_jargon.py                 # report mode, exit 0
python -B tools/check_zero_jargon.py --check         # fails only if the tree got WORSE than this baseline
python -B tools/check_zero_jargon.py --report docs/REVIEW-8-ZERO-JARGON-BASELINE-2026-10-23.json
python -B backend/test_zero_jargon.py                # the scanner's own hermetic tests (27 checks)
```

The ratchet is registered in two places, following the repository's own
pattern: a step in the `audit` job of `.github/workflows/ci.yml`, and a
`test:` row in `docs/CLAIMS.tsv` whose suite the required `backend` job runs
through `backend/run_suites.py`. **It is not a "zero jargon" gate yet** - the
tree is not clean, and a gate that must start red gets ignored or switched
off. When a cleanup PR lowers the count, regenerate this baseline downward;
when it grows, either fix the wording or add a deliberate word to the
allowlist.

**What this does not cover.** It does not drive any UI: the Android and Rust
findings are static text, and a string can still be true but unkind. Review
#8's second half - does the advice actually tell the owner what to click - is
reported only as the bare-refusal count; judging whether a sentence's advice is
correct stays a person's call. Real-device wording (a tablet or phone screen
read by the owner) is **NOT-TESTABLE** from this repository and is not claimed
here.

**Status of Review #8:** the scanner exists, bites and is ratcheted (this PR);
the **cleanup of the 255 + 25 is open** and deliberately not done here.
