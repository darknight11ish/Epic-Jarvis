# Stream E — review of the five open PRs "in testing"

**Base:** `main` @ `fa2b379f` (clean worktree `.dsh-scratch/audit-main`).
**Heads reviewed:** #92 `next-settings-jumpto` `d0ac1d7e` · #91 `fix/hud-open-bar-comments` `1d5121d7` ·
#90 `fix/tutorial-hud-box` `dc6110ac` · #86 `next-account-keys-design` `a65e9f22`.
**Read-only:** nothing merged, pushed or commented. Every command was `gh pr view/diff/checks`,
`git merge-tree`, `git show HEAD:<path>` into `.dsh-scratch/E86/`, and local runs of the repo's own
tests and modules. The `wt-keysdesign` worktree is **dirty** (uncommitted non-PR edits to
`backend/jarvis_chatbot_api.py`, `_stack.py`, `ollama-direct.patch`, `test_chatbot_api.py`,
`test_ollama_direct.py`, `gen_ollama_direct_patch.py`), so every #86 file I read or ran came from
`git show HEAD:` / the committed content, never from that working tree.

## Verdict table

| PR | Verdict | The single most important reason |
|---|---|---|
| **#92** settings jump-to | **Merge after fixing E9/E10/E11** (three small wording/measurement defects, one line of CSS) | The new test suite passes 107/107 and the 32 links are unchanged in the same order, but the Rare band shows "The AI and its tools" twice and `settings.css`'s 104px gutter is 4px too narrow for its own longest label — measured, and the PR says the list has never been rendered. |
| **#91** HUD comment sweep | **Safe to merge** | All three comment sites now say what the code does; the only remaining "one chat box" strings in the tree are dated audit reports, old CHANGELOG entries and CLAUDE.md's own history, which are records, not live claims (E12). |
| **#90** tutorial fix | **Safe to merge** | The tutorial, the ARCHITECTURE row and the JARVIS-API sentence are all corrected in both `backend/` and `jarvis-backend/`; no test or fixture anywhere still holds the old wording (E13). |
| **#86** keys + money limits | **Needs rework — 3 Critical** | The `ollama-direct.patch` after-image **does not compile** (E1, proven with `py_compile` on the repo's own mirror of `jarvis_hud.py`); `{"action":"lower_limit","dollars":500}` **raises** the monthly money limit with **no approval card** (E2, proven by running the PR's own modules); and the new cloud-lane transport **never records what it spends**, so the monthly limit it advertises can never advance (E3). |

CI, all four PRs: **no failing job** — every job is either `pass` or `pending` (queued/blocked, 0s elapsed).
For **#86** the `backend`, `backend-windows`, `frontend`, `smoke` and `face-shots` jobs are all still
`pending`, so none of #86's new Python or JS tests has ever run in CI — including the one that fails
(E4). #92 is missing `backend`, `backend-windows`, `build`, `frontend`; #91 is missing `frontend`,
`backend-windows`; #90 is missing `frontend`.

---

## Critical

### E1. `ollama-direct.patch` produces a `jarvis_hud.py` that cannot be imported at all

**PR:** #86
**Where:** `backend/ollama-direct.patch:75` (`nonlocal _cloud_model, _cloud_key, _cloud_problem`) and
`:18` (`bearer = _cloud_key or JARVIS_API_KEY`), applied to `jarvis-backend/jarvis_hud.py:4685`
(`_completions_url`, nested at 8-space indent inside the `do_POST` handler) and `:1474`
(module-level `def _auth_headers`).
**What happens:** `_completions_url` is nested in the request handler, **not** inside `_open`, and the
patch never binds those three names anywhere in the enclosing function scope. CPython therefore rejects
the whole file at compile time:

```
SyntaxError: no binding for nonlocal '_cloud_model' found
   (line 4733 of the patched file)
```

`scripts/apply-patches.ps1` applies this patch to the owner's real backend (it is listed at line 155, and
`backend/_stack.py` just raised the `jarvis_hud.py` ratchet from 45 to 47 for it). A `jarvis_hud.py` that
does not compile is not "the cloud lane is off" — it is **the entire backend failing to start**: chat,
approvals, the event stream, everything. This is the most serious thing in the five PRs.

Reproduced exactly (not inferred): `tools/gen_ollama_direct_patch.py`'s own `OLD_*`/`NEW_*` constants
from the PR head were applied to the repo's own mirror of the owner's file, then compiled:

```powershell
python .dsh-scratch\E86\repro.py     # builds .dsh-scratch\E86\hud_pr86_patched.py from PR-head text
   _completions_url: old text found 1 time(s)
   _auth_headers:    old text found 1 time(s)
   the 503's words:  old text found 1 time(s)
   COMPILE FAILED: SyntaxError: no binding for nonlocal '_cloud_model' found (line 4733)
```

**Confidence:** Certain (executed).
**Severity:** Critical — the patch stack bricks the backend on the owner's PC.
**Obvious or subtle:** Subtle to *see* (a patch that applies cleanly and a test that passes), obvious to
*fix*.
**Fix:** one of two mechanical changes, both inside the generated patch text:
1. bind the three names in the enclosing method as well (e.g. `_cloud_model, _cloud_key, _cloud_problem =
   {}, "", ""` in the handler that defines `_completions_url`), **and** set the module global that
   `_auth_headers` actually reads — see E7; or
2. drop `nonlocal` and use a module-level holder (a small dict or three module globals) that both
   `_completions_url` and the module-level `_auth_headers` share.

Whichever is chosen, add a check that the patched file **compiles** — see E7 for why the existing test
cannot catch this.

### E2. A "lower_limit" that is really a raise is applied with **no approval card and no Windows Hello**

**PR:** #86
**Where:** `backend/jarvis_chatbot_limits.py:394-398` (the only direction guard) and `:404-415` (the
`else` branch that treats every non-raise as a tightening).
**What happens:** the route trusts the client's `action` label for the direction that matters in the
wrong way. It only rewrites a **raise** that is not a raise:

```python
if action == "raise_limit" and old is not None and amount is not None and amount <= old:
    action = "lower_limit"          # 394-398
...
if action == "raise_limit":
    refused, said = _raise_card(api, pid, old, amount)   # card + Windows Hello
else:
    said = ""                       # 411-413: anything else is "tightening"
got = api.set_limit(pid, amount)                              # 415
```

There is no guard in the other direction: `{"action": "lower_limit", "dollars": 500}` against a current
limit of `$1` walks straight to `set_limit(…, 500)` — a **loosening applied without a card**. The module's
own docstring makes the opposite promise ("The BACKEND decides which of the two a request is, from the
amount against the limit it already holds - never this file, and never the page"), and
`jarvis-desktop/src-tauri/src/chatbot_money.rs:151-158` shows the page may send `lower_limit` verbatim
(`limit_action` accepts it and `limit_body` forwards it). The desktop *page* computes the honest action
(`jarvis-desktop/src/chatbot-api-keys.js:153-159`), so the app's UI hides the hole; anything else on the
PC that can reach the route (the project's own documented "a program already on the PC" gap, or a script
in the Settings window) can lift the cap to `MOST_LIMIT` = $10,000 with no card.

Run against the PR's own modules at `a65e9f22`, with a spy on the gate and `_from_this_pc` = true
(`.dsh-scratch/E86/prove_lower_bypass.py`):

```
honest lower (5 -> 1)              status=200  limit 5.0 -> 1.0    approval cards asked: 0
'lower' that RAISES (1 -> 500)     status=200  limit 1.0 -> 500.0  approval cards asked: 0
honest raise (500 -> 900)          status=200  limit 500.0 -> 900.0 approval cards asked: 1
```

**Confidence:** Certain (executed against the PR head).
**Severity:** Critical — an auto-approve path and a money-limit bypass, both named by rule 4.
**Obvious or subtle:** Subtle (the one-way guard reads as if it were two-way).
**Fix:** mechanical — decide the direction from the numbers, both ways, before choosing a path:
`if old is not None and amount is not None and amount > old: action = "raise_limit"`, or refuse a
`lower_limit` whose amount exceeds the current limit with a "that would be a raise; it needs a card"
refusal. Keep the existing "raise that isn't" rewrite for the page's own sake. Worth mirroring in
`chatbot_money.rs` as defence in depth, but the backend is the place that must not be fooled.

### E3. The cloud escalation lane never records what it spends, so its monthly money limit never advances

**PR:** #86
**Where:** `backend/jarvis_chatbot_api.py:1576-1602` (`cloud_lane()`, the lane's pre-check) and
`:823-842` (`record_spend`) with its **only** production caller at `:1340`
(`ApiChatbot.read_reply`, the chatbot-driver adapter). The new lane path is
`backend/ollama-direct.patch` hunk 2 (`jarvis_hud.py`'s `_completions_url` inside `_open`'s
`do_POST`), which sends the request itself with `urllib.request` and records nothing.
**What happens:** the new transport pre-checks the month (`cloud_lane()` → `ready_for()` →
`money_check(..., next_chars=LANE_ASSUMED_CHARS)`) and then never calls `record_spend` for the answer.
A repo-wide search for `record_spend` over every `*.py` and `*.patch` at the PR head finds exactly two
production hits, both in `jarvis_chatbot_api.py` itself (the definition and the driver's own call). So
`spent_of("deepseek_api")` stays at whatever the *driver* recorded — normally `$0.00` — and the lane's
pre-check keeps saying yes forever. The per-answer cap (`max_tokens`) bounds one answer; nothing bounds
the number of answers, which is exactly what the monthly limit is for. The claim is made in three
places that the limit stops this lane: `CHANGELOG.md` ("the monthly money limit … a lane the limit
cannot pay for is answered on this PC instead, so the offer can disappear rather than overspend"),
`jarvis_reach.py`'s new words ("A lane whose limit is reached is not offered at all"), and the lane
status view's `money` row, which will show "About $5.00 of $5.00 left" after any amount of spending.
**Confidence:** High (static, exhaustive: the only caller is the driver; the lane's code path contains no
`jarvis_chatbot_api` call other than `cloud_lane`/`lane_key`/`ready_for`).
**Severity:** Critical — the owner's "a money limit comes before API chatbots are used for real" rule is
not enforced on the path this PR exists to build.
**Obvious or subtle:** Subtle. The code *looks* like it enforces a limit, and the pre-check is real; only
the accounting half is missing.
**Fix:** after a lane answer, record it — the HUD path knows the token counts only if it reads the
response's `usage`, so the least invasive fix is to have `_completions_url`'s caller (or the
response-reading lines just after it) call `jarvis_chatbot_api.record_spend(pid, model, prompt_tokens,
completion_tokens, guessed=True)` when `usage` is absent, and to say plainly in the lane's words that a
lane answer's cost is counted as an estimate. **Judgement call:** how to count an answer the service
reports no usage for (a worst-case estimate is the fail-closed answer, but it will over-count).

---

## High

### E4. PR #86's own new backend test fails against PR #86's own code

**PR:** #86
**Where:** `backend/test_chatbot_limits.py:605-627` (`t_no_other_module_raises_a_chatbot_money_card`,
check at `:627`) versus `backend/jarvis_asks_first.py:410` (`"raise_api_limit", "lower_api_limit",`).
**What happens:** the test scans `backend/*.py` for the two action names, excluding only
`jarvis_chatbot_limits.py`, `jarvis_owner_check.py`, `jarvis_card_words.py` and `test_*`. The same PR
adds both names to `jarvis_asks_first.py` (so the "What asks first" page can list them), so the test's
own repo fails:

```
FAIL  no other module in this repository names either action
        ['jarvis_asks_first.py']
140 passed, 0 skipped, 1 failed
```

(`py -3 backend/test_chatbot_limits.py` at `a65e9f22`; the `backend` CI job for #86 is `pending`, so
nobody has seen this.) Either the allowlist needs `jarvis_asks_first.py` with its reason, or the
asks-first entry needs a different mechanism. Neither is a design question.
**Confidence:** Certain (executed).
**Severity:** High — the PR ships a red suite; it also means #86's other 140 green checks were never run
in CI.
**Obvious or subtle:** Obvious once run.
**Fix:** mechanical — add `jarvis_asks_first.py` to the exclusion with the same kind of comment the other
three have ("the page must name them; it is not a second path to the decision"), or assert the weaker,
true thing (no other module *calls* the gate or `set_limit` for a raise).

### E5. A price of `$0` is accepted with no card, and a `$0` price makes the monthly limit inert

**PR:** #86
**Where:** `backend/jarvis_chatbot_limits.py:368-373` (`set_price` accepts `0`; only `> MOST_PRICE` is
refused), `backend/jarvis_chatbot_api.py:888-891` ("from 0 to 1,000") and `:984-985`
(`reply_cap`: `if pout <= 0: cap = MOST_REPLY_TOKENS`).
**What happens:** a price correction needs no card by design, and `0` is a legal "price". A `$0` price
makes every answer count as `$0.000000`, so `spent` never grows and the limit never bites. Executed
(`.dsh-scratch/E86/prove_zero_price.py`), limit `$1`:

```
set_price 0/0 through the route: status 200, cards asked: 0
request 1: money_check '' cap=8000; counted $0.000000; month $0.000000 of $1.0
request 2: money_check '' cap=8000; counted $0.000000; month $0.000000 of $1.0
request 3: money_check '' cap=8000; counted $0.000000; month $0.000000 of $1.0
```

**Confidence:** Certain (executed).
**Severity:** High — a second, card-free way to make the money limit meaningless (and one the owner can
trigger by typing `0` in the new box).
**Obvious or subtle:** Subtle — "correcting a price is not a loosening" is true of every price except
zero, which is not a price any service charges.
**Fix:** mechanical — refuse `0` for either price (a floor such as `0.000001`, or "a price of zero is not
a real price: set the real one"), in both the route and `jarvis_chatbot_api.set_price`'s own validator so
the CLI cannot do it either. **Judgement call:** whether a very low but non-zero price should also warn.

---

## Medium

### E6. The money card tells the owner DeepSeek's verified price is a 2026-09-28 unverified guess

**PR:** #86
**Where:** `backend/jarvis_chatbot_limits.py:233-234` (the `"default"` branch's line text) and `:236`
(`"verified": False if where == "default" else True`), versus `backend/jarvis_chatbot_api.py:1669-1680`
(`verified_price()`) and `:1682+` (`spent_lines()`, the CLI, which *does* use it).
**What happens:** `_price_row` never calls `verified_price()`, so for DeepSeek — whose two defaults this
same PR re-read from DeepSeek's own page on 2026-10-06 and re-priced to the worst case `$0.30/$1.20` —
the Settings card still prints "the default written 2026-09-28, UNVERIFIED". The app and the PC's own
`spent` command therefore contradict each other about the same number, and decision 4 ("the app says
which numbers are guesses") reports the wrong provenance. `backend/test_chatbot_limits.py:212-214`
asserts "UNVERIFIED" is in the line for every service row, so the test currently **enshrines** the wrong
claim and must change with the fix.
**Confidence:** High (code read; the DeepSeek branch of `verified_price` is unambiguous).
**Severity:** Medium — no money is lost, but the one thing this card was built to be honest about is
wrong for the service the cloud lane actually uses.
**Obvious or subtle:** Subtle.
**Fix:** mechanical — use `api.verified_price(pid, model)` in the `"default"` branch (and set `verified`
from it), exactly as `spent_lines` does; update the two test assertions to expect the checked wording for
DeepSeek and UNVERIFIED for the rest.

### E7. `_auth_headers` reads a global that nothing sets — the whole request path raises `NameError`

**PR:** #86
**Where:** `backend/ollama-direct.patch:18` (`bearer = _cloud_key or JARVIS_API_KEY`, in the
**module-level** `_auth_headers`, `jarvis-backend/jarvis_hud.py:1474`), while `:75` binds `_cloud_key`
only as a `nonlocal` of the nested `_completions_url`.
**What happens:** even after E1 is fixed by declaring the three names in the enclosing handler, the
module-level `_auth_headers` can never see a local of `do_POST`: it looks `_cloud_key` up in the module
globals, finds nothing, and raises `NameError` on the **first request of any kind** — including a purely
local turn. Verified by lifting the patched function with the globals the real module has
(`.dsh-scratch/E86/repro2.py`):

```
call the patched _auth_headers with the real globals   -> NameError: name '_cloud_key' is not defined
the same function once a test injects _cloud_key       -> {'Authorization': 'Bearer the-pairing-token'}
```

That second line is why the suite is green: `backend/test_ollama_direct.py:119-128` puts `_cloud_key`
into the namespace itself, and `:93-116` wraps the lifted `_completions_url` in a `_run()` that declares
the three names, so the test supplies precisely the bindings the real file lacks. `ast.parse` also
succeeds on the broken file (scope rules run at compile time), and `backend/run_suites.py`'s
`NEEDS_OWNER` marks this suite as needing the owner's `jarvis_hud.py`, so in CI it **skips**. The net
effect: the only test that touches this code cannot fail, while the code cannot work.
**Confidence:** Certain (executed).
**Severity:** Medium as written (it cannot fire until E1 is fixed) — but the fix for E1 must not be
"declare the names in the handler" alone, or this becomes the next Critical.
**Obvious or subtle:** Subtle.
**Fix:** mechanical — make the key travel through a module-level holder both functions can see (three
module globals set by `_completions_url`, or a one-entry dict), and add a **compile** check plus a
"no undefined global" rehearsal to the test: build the after-image from the patch text, `compile()` it,
and only then lift the functions. That check alone would have caught E1 and E7 together.

---

## Low

### E8. Stale docstrings and comments inside #86

**PR:** #86
**Where and what:**
- `backend/jarvis_chatbot_api.py:854` — `set_limit`'s docstring still says *"The owner's command line
  only (there is NO route)"*, while this PR adds `POST /api/chatbot/money`, which calls it.
- `jarvis-desktop/src/chatbot-api-keys-settings.js:5-10` — the module doc says "Five Rust commands" and
  names `chatbot_limits` / `set_chatbot_limit`, which do not exist; the real names are `chatbot_money` /
  `set_chatbot_money` (`src-tauri/src/chatbot_money.rs:136`, `:210`).
- `tools/gen_ollama_direct_patch.py:1-19` — the docstring says the tool builds
  `backend/cloud-lane-transport.patch`; `main()` writes only `ollama-direct.patch`, and no
  `cloud-lane-transport.patch` exists anywhere in the tree (checked with `git ls-tree`).
- `CHANGELOG.md` (this PR's hunk) — the two new bullets have no blank line between them, unlike every
  other entry in the file.
**Confidence:** Certain (read).
**Severity:** Low — words only, but this is the exact class of defect #91 exists to clean up, inside a PR
that is 7,500 lines long.
**Obvious or subtle:** Obvious.
**Fix:** mechanical, four small edits.

### E9. #92 shows the same short row label twice in one band, and the CHANGELOG lists one fewer row than the page has

**PR:** #92
**Where:** `jarvis-desktop/src/settings.html:128` (first "The AI and its tools" row, holding Web
search) and `:142` (the same label again, holding Folders, Spending, Look at this, Browser without a
window) — both inside the Rare band.
**What happens:** a reader sees the same sub-heading twice in one band with no difference between them.
The CHANGELOG's own list of the Rare rows names seven ("On this PC, Voice and sound, The AI and its
tools, More on this PC, The model and cards, Where things are kept and Keeping it up to date") while the
page has eight — so the entry omits the duplicate rather than explaining it.
**Confidence:** Certain (read; 17 place labels, one of them twice).
**Severity:** Low — cosmetic/wayfinding, on the page the change exists to make findable.
**Obvious or subtle:** Obvious.
**Fix:** **Judgement call on the wording**, mechanical to apply: either merge the two rows into one
seven-link row, or give the second a distinct name (for example "Files, screen and browser"). Then make
the CHANGELOG and the `settings.html` header comment list exactly the labels the page uses.

### E10. The 104px gutter is too narrow for its own longest label — 108px — and the "longest label" comment names the wrong one

**PR:** #92
**Where:** `jarvis-desktop/src/settings.css:102-111` (`.settings-jump-label`, `min-width: 104px` at `:111`,
with the comment at `:106-110`: "Wide enough for the longest band name ("What Jarvis does") and for every
place label below (the longest is "The AI and its tools")") and `:133` (`.settings-jump-place-label`, the
same `min-width`).
**What happens:** the longest place label is not "The AI and its tools" (20 chars) but **"Where things are
kept"** (21) and "Keeping it up to date" (21). Measured with Pillow against `--font-ui`'s first
available family (`--text-xs: 11px`, `theme.css:235`; `.settings-jump-place-label` is weight 400):

```
Where things are kept    108.0px  WRAPS   (min-width = 104px)
Keeping it up to date    102.0px  fits
The AI and its tools      94.0px  fits
What Jarvis may do        94.0px  fits
band labels, 600 weight:  What Jarvis does 86-88px  fits
```

So "Where things are kept" wraps inside its 104px box, making that one row two lines tall and breaking
the shared left edge the comment promises. The measurement is on Segoe UI (Windows 11's "Segoe UI
Variable Display" is not installable here and its metrics differ slightly), so treat the 4px as
"borderline, and the comment's premise is definitely wrong". The PR itself says the list "has not been
seen rendered in a browser" because Playwright is not installed (`CHANGELOG.md`, this PR's entry;
`tests/ia.mjs` exits without checking), which is why nothing caught it.
**Confidence:** Medium-High on the wrap (4px over on the measurable fallback font), Certain on the
comment being factually wrong.
**Severity:** Low — a wrapped label, not a broken link.
**Obvious or subtle:** Subtle.
**Fix:** mechanical — raise `min-width` to ~116px (or `13ch`/`max-content` with a shared grid column) and
correct the comment to name "Where things are kept"; then actually open the page once (or run a Playwright
check) before calling the tidy-up done.

### E11. The grouping's stated provenance does not match the document it cites

**PR:** #92
**Where:** `CHANGELOG.md` (this PR's entry: "the short rows are the six groups
`docs/ease-audit-2026-09-27/customize.md` proposed and `critic.md:199` kept as 'the target order of the
jump list' for both apps") and `jarvis-desktop/src/settings.html:41-58` (the header comment, which says
"the six groups" and then lists **ten** names, including "What Jarvis is allowed to do" where the page
says "What Jarvis may do").
**What happens:** `docs/ease-audit-2026-09-27/customize.md:273-292` proposes **seven** groups for the whole
Settings page, with different names ("Talking to Jarvis", "Your voice", "What Jarvis may do", "Memory and
history", "Schedules", "Look", "This PC / this phone"), and `critic.md:199` kept those seven as the target
order. #92 ships 17 rows under 16 different labels, only two of which ("Look", "Schedules") match. The
comment also lists the groups in an order the page does not use. The grouping itself is reasonable; the
authority claimed for it is not.
**Confidence:** Certain (both cited files read).
**Severity:** Low — a comment and a changelog entry that would mislead the next reader (and the phone's
screen, which the cited decision says should copy this list).
**Obvious or subtle:** Subtle.
**Fix:** mechanical — say what the test's docstring already says honestly ("the grouping is this page's
own") and drop the citation, or adopt the seven proposed groups. **Judgement call:** which of the two,
since the second touches the phone's future screen.

### E12. #91's sweep is complete — what remains is history, not a live claim

**PR:** #91
**Where / what:** the three fixed sites are
`jarvis-desktop/src-tauri/src/voice.rs:749-756`, `permissions/surfaces.toml:144-150` and
`build.rs:738-739`; all changed lines are comments (`//` or `#`), nothing else moved, which matches the
PR's "comments only" claim. A repo-wide sweep of the #91 head for `one chat box`, `opens the Jarvis bar`,
`opens this one` and `one conversation` leaves, besides dates records:
- `CLAUDE.md:746` and the root `CLAUDE.md`'s 2026-09-28 entry — the dated decision, already followed by
  the 2026-10-06 reversal entry at the top of the same file;
- `CHANGELOG.md:13` and `:350` — the reversal entry and an older, dated entry;
- `docs/studio-2026-09-28/chat-audit2-memory.md:175` — a dated audit report ("Otherwise ARCHITECTURE §5
  and §8 are true to the code. The HUD's one chat box … all match"), true when written;
- `jarvis-desktop/src-tauri/src/hud_bootstrap.js:1016-1023` — already describes the reversal correctly;
- several `opens the Jarvis bar` lines about **approval cards** and the widget, which are about the bar as
  a destination, not about the HUD's box (`commands.rs`, `widget.js`, `lock.rs`, `backend/README.md`).
I found no remaining **live** comment or user-visible string that still teaches the old rule. Two of the
four files #91 touches also collide with #86 (`build.rs`, `surfaces.toml`) but `git merge-tree` shows both
auto-merge cleanly (see the conflict table).
**Confidence:** High.
**Severity:** Informational.
**Obvious or subtle:** —
**Fix:** none.

### E13. #90 catches the tutorial up completely; nothing else holds the old wording

**PR:** #90
**Where / what:** `backend/jarvis_tutorials.py:697-700` and its mirror
`jarvis-backend/jarvis_tutorials.py:697-700` (identical after-image), `docs/ARCHITECTURE.md:2121` (the
Inbox-tidy row no longer says the HUD "shows no chat") and `docs/JARVIS-API.md:17408` ("a chat box he
already has"). I searched the whole #90 head for `only ever one conversation` and `The one chat box on
the PC` and found **no** test, fixture, contract case or doc left holding the old text, and the phone's
own main sources contain no "one chat box" claim at all.
**Confidence:** High.
**Severity:** Informational.
**Obvious or subtle:** —
**Fix:** none. (One shared hazard, not a defect: #90's and #91's CHANGELOG entries land in the same slot —
see below.)

---

## Conflicts between the PRs (measured with `git merge-tree`, base `fa2b379f`)

| Pair | Result |
|---|---|
| #92 + #91 | **CONFLICT** `CHANGELOG.md` |
| #92 + #90 | **CONFLICT** `CHANGELOG.md` |
| #92 + #86 | **CONFLICT** `CHANGELOG.md`, **`jarvis-desktop/src/settings.html`** |
| #91 + #90 | **CONFLICT** `CHANGELOG.md` |
| #91 + #86 | **CONFLICT** `CHANGELOG.md` (`build.rs`, `surfaces.toml` auto-merge) |
| #90 + #86 | **CONFLICT** `CHANGELOG.md` |

- **`CHANGELOG.md` — every pair.** All four PRs insert their bullet(s) at the same place: main's
  `CHANGELOG.md:9`, immediately after `## Not in a numbered version yet` and before the existing
  "Settings → Accounts …" entry. Each PR is individually mergeable into `main`; any second one needs that
  slot resolved by hand.
- **`settings.html` — #92 + #86 only.** #92 rewrites the whole `<nav class="settings-jump">` block
  (main `jarvis-desktop/src/settings.html:51-94`) into banded rows; #86 adds one flat
  `<a href="#chatbot-api-keys">Chatbot API keys</a>` at main line 74. Beyond the textual conflict there is
  an ordering hazard: if the hand resolution leaves #86's link as a **flat** `<a>` inside a band, #92's new
  `t_jump_list_matches_the_page` fails its "a band holds only jump rows and its own label" check
  (`backend/test_settings_registry.py:282-285`), and if the link is dropped the same test fails its
  "every card in the band is listed" check. So the resolution must put the link inside a
  `.settings-jump-place` row in the band its card sits in.
- Everything else auto-merges: the Rust permission files, `build.rs`, `surfaces.toml`, the menu catalogs
  and the two `jarvis_tutorials.py` copies.

## What I ran (so the findings can be checked)

```powershell
gh pr view/diff/checks 92 91 90 86 --repo darknight11ish/Epic-Jarvis        # metadata, diffs, CI
git merge-tree --write-tree --name-only <head> <head>                        # the conflict table
git -C wt-keysdesign show HEAD:<path> > .dsh-scratch/E86/...                 # pristine PR-head files

# #92, its own suite, 107 checks, passes:
py -3 .dsh-scratch/E86/run_one.py backend\test_settings_registry.py          # 107 passed, 0 failed
python .dsh-scratch/E86/measure_labels.py                                    # 108px label in a 104px box

# #86, its own suites:
py -3 .dsh-scratch/E86/run_one.py backend\test_chatbot_keys.py               # 56 passed, 0 failed
py -3 .dsh-scratch/E86/run_one.py backend\test_chatbot_limits.py             # 140 passed, 1 FAILED
python .dsh-scratch/E86/repro.py                                             # SyntaxError, line 4733
python .dsh-scratch/E86/repro2.py                                            # NameError, + why the test is green
python .dsh-scratch/E86/prove_lower_bypass.py                                # limit 1 -> 500, no card
python .dsh-scratch/E86/prove_zero_price.py                                  # $0 price, limit inert
```

Two environment notes, for anyone repeating this on Windows: `tempfile.mkdtemp()` directories are not
writable under this sandbox (`.dsh-scratch/E86/run_one.py` creates temp dirs with `os.makedirs` and points
`OPENJARVIS_CONFIG_DIR`/`JARVIS_CONFIG_DIR` at a writable folder before the modules import — the same
thing `backend/run_suites.py`'s `private_state()` does). `test_gate_risk_words.py` (12 failures),
`test_devices.py` (13) and `test_referee.py` (3) fail the same way on **clean main** in this sandbox, so
those are environmental, not #86 regressions; **`test_chatbot_limits.py`'s single failure is not** — it
comes from a file this PR edits and reproduces from the committed text alone.
