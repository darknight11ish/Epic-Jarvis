# Finance: spending summaries and a retirement what-if (design, 2026-09-30)

Status: **designed, not built.** Two pieces from the owner's build queue
(`docs/BUILD-QUEUE-2026-09-30.md`): item 2, **spending summaries** from bank
export files (JARVIS-API section 100), and item 5, the **retirement what-if
calculator** (section 103; it needs item 2's number and money handling first).
Section 9 lists the questions the owner still has to answer.

## In short

- **Spending:** the owner drops a bank export (CSV or Excel) into a folder that
  is already on "Folders Jarvis may look in". They ask "how much did I spend on
  food last month?". **Plain Python code adds the numbers up.** The AI model
  only puts a sentence around them. The table appears on screen only.
- **How the code reads the file:** Python's built-in `csv` module plus
  `openpyxl`, which is already installed (MarkItDown's Excel part brings it). No
  DuckDB: it would be a new heavy download, and Jarvis has no need to run
  model-written database queries for this.
- **Categories** are plain keyword rules in a small file the owner can read and
  edit. The model may *suggest* a category for a shop name; nothing is kept
  until the owner taps yes.
- **Retirement what-if:** about 150 lines of Jarvis's own `numpy` code, not
  monteplan (reasons in section 6). It says "in about 78 of 100 simulated
  futures the money lasts to age 95", never one exact number, with a
  "not financial advice; a simplified model" line every time.
- **Everything here is money.** It stays on screen: never read aloud, never
  remembered, never sent to a web search or a chatbot, hidden under "Hide
  memory lists and chat history". Account and card numbers in a file are
  hidden before anything is shown. **Bank connections (Plaid and the like)
  stay refused.**

## 1. Where this meets the rules

- **Rule 1.** Bank files are money and identity data. Everything runs on the
  PC; the model that words the reply is the local one (tools run only on the
  local lane). Nothing goes to a cloud lane.
- **Standing limits of 2026-09-30** (`BUILD-QUEUE-2026-09-30.md`): numbers come
  from code; money stays on screen; no outside JavaScript library; nothing
  stored as SQL to run; no bank connections; no new server or port; "never
  reached" is its own answer.
- **Muse comparison** (`COMPETITORS-MUSE-2026-09-25.md`): Muse links bank
  accounts through Plaid and kept nudging for more data. Jarvis reads only a
  file the owner chose to drop in, and never suggests connecting a bank.
- **Outside text.** A bank file is a file, so what the tool returns counts as
  outside text (as `my_files` results do): a note written afterwards asks first,
  and nothing in it is learned as a fact. Shop names in a file can be written
  by anyone, so the model never gets a raw description as an instruction. See 3.6.

## 2. Spending summaries: what the owner sees

1. Owner drops `bank-march.csv` into a listed folder. (The folder card was
   already decided when the folder was added; nothing new to approve.)
2. Owner asks in chat, typed or spoken: "how much did I spend on food last
   month?" or "spending by category for 2026".
3. **First time for a file shape only:** Jarvis says it does not know the
   columns and opens a small "Check these columns" box on the PC (section 3.1).
   The owner confirms once; it is remembered for files with the same header.
4. Jarvis answers with one sentence and a small table, drawn from numbers the
   code computed. Spoken turns say "I have put it on your screen."

## 3. Spending summaries: design

### 3.1 Reading a bank export (format detection, mapping once)

- Read with `csv.Sniffer` on the first 4 KB for the separator (comma,
  semicolon, tab), tolerating a byte-order mark and blank lines. Excel: the
  first sheet only, or the one the owner names.
- **Find the header row** instead of assuming row 1: some banks put lines like
  "Account: 12345678" above it. The header is the first row with at least three
  non-empty cells, one of which looks like a date word ("date", "posted",
  "datum", "fecha") and one like an amount word. If none is found, ask.
- **Guess the columns** from header words: date; description (payee, details,
  memo); and either one *amount* column, or a *debit* and a *credit* column, or
  an amount plus a "Dr/Cr" or "type" column; optionally balance (ignored) and
  currency. Show the guess as a plain table of the first five rows and let the
  owner change any dropdown.
- **A "profile"** is the confirmed mapping (columns, separator, date order,
  number style, sign rule, header row, skip footer rows). Saved in
  `spending-profiles.json` in the Jarvis settings folder, keyed by a fingerprint
  of the header row (a hash of the lowercased header cells, never file content).
  Same header again means no question. The owner can see and delete profiles.
  Nothing here is a secret; the file holds column names and choices only.
- **Footer and junk rows** ("Total", "Closing balance", blank amount) are
  skipped and counted; the count is shown ("2 rows skipped").

### 3.2 Numbers, signs and currency

- **All money is kept as whole minor units (cents) in Python integers**, parsed
  with `decimal.Decimal`, never `float`. A cent-off total is a bug we can test.
- **Number styles the parser must handle:** `1,234.56`, `1.234,56`, `1 234,56`,
  `(45.10)` meaning negative, `45.10-` (trailing minus), `-£45.10`, `$` `£` `€`
  symbols, `CR`/`DR` suffixes. Which of `.` and `,` is the decimal mark is a
  profile setting, guessed from the whole column (a value like `1,234` alone is
  ambiguous; a column with any `12,5` or `1.234,56` decides it). If the whole
  column stays ambiguous, ask; never guess.
- **Sign rule** is a profile choice with four forms: (a) negative = money out;
  (b) positive = money out (many credit-card exports); (c) separate debit and
  credit columns; (d) amount plus a Dr/Cr column. The check box shows a plain
  sentence: "Rows like 'TESCO -45.10' will be counted as money spent."
- **Refunds** (money in with a shop name) reduce that category's spending and
  are shown on their own line so nothing is hidden by netting.
- **Income and transfers:** a category "Transfers" (own accounts, card
  payments) is left out of "spending" and shown separately. Money in is "Income".
- **Currency:** one currency per file. The symbol or a currency column is
  detected; a file with several currencies is summed **per currency, never
  converted** (no exchange rates: that would need the internet). The table
  header says which currency each total is in.
- **Dates:** ISO (`2026-03-04`), `dd/mm/yyyy`, `mm/dd/yyyy`, `dd.mm.yyyy`,
  `4 Mar 2026`, and Excel date cells. **dd/mm versus mm/dd is decided from the
  whole file:** if any first part is over 12 it is day-first; if any second part
  is over 12 it is month-first; if every value is 12 or less, the code
  **refuses to guess** and asks the owner in the check box. A wrong guess would
  silently move a month's spending, which is the worst kind of error here.

### 3.3 Categories

- **Rules, stored plainly:** `spending-categories.json`, a list of
  `{"category": "Food", "words": ["tesco","sainsbury","lidl","aldi"]}`. Matching
  is case-insensitive, whole-word, first rule in the owner's order wins, and the
  file is shown in full in the app's "Categories" box (PC edits; the phone
  shows it read-only, see section 5).
- **A small starter list** the owner can edit: Food and groceries, Eating out,
  Transport, Home and bills, Health, Shopping, Fun and travel, Subscriptions,
  Cash, Transfers, Income, Other. Only the category *names* ship; the keyword
  lists start with a few very common shop words and the owner grows them.
- **Rows no rule catches** land in "Uncategorised", which is always shown, with
  a count. It is never silently added to "Other".
- **Model suggestions, never automatic.** "Suggest categories" sends the local
  model the top uncategorised shop names (already cleaned, section 3.5), at most
  20 at a time, and gets back a category per name. They show as ticked-off
  proposals ("MIRAGE CAFE -> Eating out"); the owner unticks any and taps
  "Add these rules". Only then are keyword rules written. The model never
  categorises a total on the spot: the same file always gives the same numbers.
- **Editing a rule re-runs the totals at once.** No approval card: the owner's
  own tap changes their own rule file and it can only affect this screen.

### 3.4 Duplicates across overlapping exports

Banks export "last 90 days", so March appears in two files. When the owner asks
about a *set* of files (a folder or "all files for this account"), rows are
combined like this:

- The key of a row is (date, amount in cents, cleaned description).
- **Within one file, identical keys are kept** (two 2.50 coffees the same day
  are real). Across files, for each key **the larger count of any single file is
  used, not the sum.** So a row that is in both files counts once, and the two
  coffees still count twice.
- The answer says how many rows were counted once because they were in more
  than one file. It is a visible line, not a silent fix.
- **Known weak spot:** a bank that rewrites a description between a "pending"
  and a "posted" export breaks the match, so that row counts twice. The check
  box warns about this in one sentence.
- By default a question uses **one file**; "all my files" is asked for by name
  or chosen in the box. Which files belong to one account is a profile setting.

### 3.5 Hiding account and card numbers

Before any row is shown or given to the model, every description and every
other text cell goes through `jarvis_secrets.redact_text` with its existing
kinds (`card` with the Luhn check, `iban`, `email`, `ip`, `crypto`, plus the
key patterns). Two additions the money case needs, both plain code in
`jarvis_spending.py`, not changes to `jarvis_secrets`:

- Any run of 8 or more digits (an account number, a sort code plus account, a
  reference) is replaced by `[hidden]` (all of it, no last digits left visible), and the check box preview shows `[hidden]` too.
- Any header cell whose name says "account", "iban", "card", "sort code" is
  never displayed, even hidden; it is dropped from what the app receives.
- **Fails closed:** if the text is too large or the check runs out of time
  (`jarvis_secrets.Unchecked`), the file is not shown and the answer says why.
- Said plainly to the owner: a hidden value is hidden on screen and from the
  model; the file on disk is untouched. Emails hidden means a payee that is an
  email address shows as `[hidden]` (the same trade-off as the screen feature).

### 3.6 What the model sees

The model gets: the category names, the totals, the period, the currency, the
skipped and de-duplicated counts. It **does not get raw descriptions** except in
"Suggest categories", where the names are passed as quoted data, capped at 40
characters each, with a header saying they are data and not instructions. The
reply the model writes is **checked by code**: every number in its sentence must
appear in the table; a sentence with any other number is thrown away and the
table is shown alone with a plain fallback line. The model can never change a
figure, only word it.

### 3.7 The tool, its gate and its card

- **Tool name in `TOOLS`: `my_spending`**, beside `my_files`. Actions: `summary`
  (period, group by category or month or both, optional category), `files` (which
  files could be read), `suggest` (category suggestions). It only reads.
- **Gate action: `read_files_readonly`**, the same as `file_read` and `my_files`
  (`gate_lookup_name=lambda args: "file_read"` in `my_files`; the same here). Why
  no new card: adding the folder already took an approval card that names it, and
  reading a listed folder needs none today; this tool reads the same files with
  the same limit. Turning a file into totals adds no way out of the PC.
  It shares the one line on "What asks first" (`jarvis_reach.py` gets a
  plain-English `TOOL_NAMES` row; `tools/gen_reach_cases.py` is re-run).
- **Not in `NEEDS_A_PERSON`:** it changes nothing and sends nothing. (That table
  is for tools that act.) It does refuse a path outside a listed folder, reusing
  `jarvis_agent._protected_path` and the same link-following check as
  `jarvis_documents.py`, and never opens a file over a size cap (proposal: 5 MB
  or 50,000 rows, then "this file is too big; export a shorter period").
- **Excel:** read directly with `openpyxl` (`read_only=True`, `data_only=True`,
  so formulas are not run; macros are never run, `.xlsm` is refused). A CSV
  needs no child process. **Question for the builder:** MarkItDown runs as a
  child process for safety with unknown Office files; `openpyxl` inside the
  backend process is a bigger trust step. Recommended: run the openpyxl read in
  the **same kind of child process** (`python -I`, `jarvis_child_env`) that
  `jarvis_documents.py` uses, returning rows as JSON. CSV stays in-process.
- **Refuses after outside text in the turn** (an email or web page just read),
  and on a phone message that is pasted or shared: the file choice could be
  steered by injected text. Same signals `note_needs_a_person` already uses.

### 3.8 Showing the result, in both apps

- **Chat answer with a small table** (recommended first version), because the
  owner asked in chat. The backend answer carries a structured `table` block
  (title, columns, rows, currency, notes) that both apps draw natively:
  desktop as plain HTML/CSS, phone as a Compose list. No chart in the first
  version; a bar per category drawn as hand SVG / Canvas is a possible second
  step (no outside JavaScript library).
- **The answer is marked private/sensitive (money)** so the existing rules do
  the work: not read aloud, kept on screen. `jarvis_sensitive` already has a
  money category; a spending answer is marked directly rather than by guessing
  from words. Follows how the quiz and Projects mark screen-only answers.
- **Hide lists and App lock:** under "Hide memory lists and chat history" the
  table is not drawn, only "Spending table hidden"; with App lock on, the table
  needs the app unlocked, like approval notes. The phone already blocks
  screenshots in exactly these two states.
- **Not remembered:** no fact is created from a total; memory learning only takes
  the owner's own typed or spoken words, and a table is neither.
- **Chat history (owner's call, Q2):** recommended that the kept chat holds the
  question and the sentence, but **not the table** (a placeholder line instead),
  so a year of spending is not sitting in the history file.

## 4. Spending: backend pieces and routes (sketch)

New modules, shipped whole: `backend/jarvis_money_parse.py` (numbers, signs,
dates, header finder: shared with the retirement piece so both parse the same
way), `backend/jarvis_spending.py` (profiles, categories, summary, de-duplication,
hiding, the tool), with `spending.patch` (route install, the `TOOLS` entry, the
gate lookup) and `tools/build_patch_history.py` run afterwards. Add a
line for `openpyxl` to `requirements.txt` (it is installed already through
MarkItDown; naming it makes `test_shipped_modules.py` pass and stops a later
MarkItDown change removing it unnoticed). **No DuckDB.**

Route sketch under section **100** (numbers within the section not assigned):
read the profiles and categories; save a profile or category rules (PC only,
like folders); ask for a summary; ask for category suggestions. Profile and rule
writes are refused from any device but this PC (`jarvis_owner_check.from_this_pc`).
Nothing writes or moves a bank file.

**Python csv/openpyxl or DuckDB, chosen:** csv/openpyxl. DuckDB is not in
`requirements.txt`, would add a large native package, and its own documentation
calls its lock-down settings "defense-in-depth", not a sandbox
(`CUTTING-EDGE-2026-09-26-round3-knowledge.md` idea 6). Its strength is running
model-written SQL, which this design deliberately does not do: the code itself
groups and sums a list of a few thousand rows in milliseconds. If the owner later
wants free-form questions ("biggest purchase over 100?"), idea 6 remains the
place to do it.

## 5. Both apps: what each side does

- **Desktop:** the chat table; a "Spending" box in Brain -> Work (or Settings)
  for the column check, the profiles list and the categories editor; hide-list
  and App lock handling.
- **Phone:** the same chat table, drawn natively; the categories list **read-only**.
- **Deliberately one-sided (write in ARCHITECTURE section 8, "One-sided on
  purpose"):** the column check and the categories editor are **PC only**. Reason:
  bank files live on the PC, adding a folder is already PC-only, and a phone
  screen is a poor place to map columns; it also fits the standing "no deep
  config editing on the phone". The phone can ask the same questions and read
  the answer, because the PC does the work and sends back only a table over
  Tailscale or Meshnet (screen only, not stored on the phone).
- If a file needs its columns confirmed, the phone says "Open Jarvis on the PC to
  check the columns" instead of asking.
- `tools/check_parity.py` must be clean (routes classified `pc-only` or shared).

## 6. Retirement what-if calculator (queue item 5)

### 6.1 What the owner types and gets

The owner types their own numbers, in a small form or in chat (Q4): current age,
retirement age, plan-to age (default 95), savings now, yearly saving until
retirement, yearly spending in retirement, and optional pension or other income
(amount and start age). **All in today's money** (the model works in "real"
terms, so inflation is already taken out; the form says so in one line).

Answer, always in this shape:

> In about **78 of 100** simulated futures your money lasts to age 95.
> If yearly returns are 1 point lower, that becomes about 66; 1 point higher,
> about 87. The middle case leaves about 310,000 at 95; a poor case (1 in 10)
> runs out at about age 88.
> *This is not financial advice. It is a simplified model with made-up return
> figures; real life will differ.*

- **Never a single exact number.** Percentages are rounded to whole numbers and
  shown with the low/high return band above; money amounts are rounded to 2
  significant figures and shown as a range (10th, 50th, 90th percentile).
- **The disclaimer line is added by code to every result**, not left to the
  model, and is part of the table block so it cannot be dropped.
- **Inputs shown back** in a "What I used" list; anything the owner did not state
  is marked "assumed" (returns, spread, plan-to age). The model may not fill a
  missing number silently; it asks the owner.

### 6.2 monteplan or Jarvis's own numpy: compared

| | engineerinvestor/monteplan | ~150 lines of own numpy |
|---|---|---|
| Licence | Apache-2.0 | Jarvis's own (MIT) |
| Python | needs >= 3.11 | works on the backend's range |
| Dependencies | numpy, scipy, pydantic, click, pyyaml | numpy (already required) |
| Install | not on PyPI as far as checked; from source | nothing new |
| Maintenance | one author, v0.6.0, last commit 2026-02 | ours to maintain, tiny |
| Notice | Apache NOTICE / credit if shipped | none needed; a courtesy line at most |
| Fit | full planning features we would not expose | exactly the few inputs above |

**Recommendation: write our own** (`backend/jarvis_retirement.py`). Reasons:
(1) the backend still supports Python 3.10 (`requirements.txt` carries
`tomli; python_version < "3.11"`), and monteplan needs 3.11, so using it would
force a higher minimum; (2) four new packages including scipy for one small
calculation; (3) an install "from source" from a single-author project is a
supply-chain step the project's own habits avoid (pinned, hash-checked
dependencies); (4) our own code can be tested line by line against a hand
calculation. monteplan (or a re-run by hand) can be used **in a developer script
under `tools/`** to cross-check our numbers, never installed by the app. The
monteplan facts above are from the request and not re-checked here.

### 6.3 The model and its pitfalls

- Yearly steps. Each year: add saving (before retirement) or subtract spending
  minus other income (after), then apply that year's return. Returns are drawn
  from a normal distribution of the **log** return (so a balance can never go
  below zero from one year's return), defaults labelled as assumptions (for
  example real mean 4.5%, spread 12%; the exact defaults are the owner's to
  set: the form shows them and lets the owner edit).
- **10,000 futures, fixed random seed**, so the same inputs always give the same
  answer (otherwise the percentage wobbles between two clicks and looks broken).
  The seed is stated in the "What I used" list.
- **"Never reached" is its own answer.** With `depleted = balance <= 0`
  (shape futures by years), `np.argmax(depleted, axis=1)` returns 0 for a row
  that is never true, which reads as "ran out at the first year". This was
  reproduced on 2026-09-30. The code must test `depleted.any(axis=1)` first and
  only take `argmax` where it is true; rows with no depletion are counted as
  "lasted". If **no** future runs out, the text says "in all 10,000 simulated
  futures" plus "this does not mean it is guaranteed", and the percentage is
  shown as "more than 99" rather than 100.
- **"Not enough to say"** when plan-to age is not after retirement age, or the
  spending is zero (nothing to test).
- **Validated and bounded:** ages whole numbers 18 to 100, plan-to age at most
  110 and after retirement age; money 0 to 1,000,000,000; returns -5% to 15%;
  spread 0% to 40%; at most 90 years simulated. Text, NaN, infinity, booleans and
  negative money are refused with a plain sentence saying which field. Numbers
  are parsed with the same `jarvis_money_parse` as part A.
- **Screen only, sensitive (money)**, same handling as section 3.8: not read
  aloud, not remembered as a fact, hidden under "Hide memory lists", never sent to
  search or a chatbot. Not saved between runs unless the owner taps "Keep these
  numbers" (Q in section 9); by default the form starts empty each time.
- **Refused after outside text in the turn**, so an email cannot feed it
  numbers.

### 6.4 The tool, gate and routes

- **Tool `retirement_whatif`**, a pure calculation on numbers the owner typed:
  no files, no network. Gate: decided like `calculator` (a pure calculator, no
  card); the builder confirms in `jarvis_agent.py` and `jarvis_reach.py` which
  action `calculator` uses and reuses it rather than inventing one. It joins the
  "What asks first" list in plain words.
- Route sketch under section **103**: one call taking the inputs and returning the
  same `table` block used in section 3.8 (plus the fixed disclaimer field). No
  route stores anything.
- Both apps: a small form with the same fields (the phone can do this; it is not
  a catalogue, memory graph or deep config), and chat. The phone's form sends the
  numbers to the PC and draws the reply; nothing is computed or stored on the
  phone. No reason for one side only.

## 7. Turned down (checked for this design)

- **Actual Budget / actualpy:** needs its Node sync server and a password; running
  it headless is unverified; a second server and a stored password conflict with
  "no new server or port". Nothing to gain over a file we read ourselves.
- **Econumo:** young project, a Go server, and the edition described was hosted;
  a hosted budget is money data leaving the PC.
- **Beancount:** GPL-2.0, so it could only ever be a separate program, never part
  of Jarvis (`THIRD-PARTY-NOTICES.txt` already says no GPL part is inside the
  apps). Later, Jarvis could read the owner's own `.bean` files with its **own
  small parser** (plain text: date, account, amounts), no Beancount code.
- **Fava:** Beancount's web viewer, so the same reasons and one more server.
- **Bank connections (Plaid, Open Banking, screen-scraping a bank site):**
  refused. They hand Jarvis's bank credentials or a long-lived token to a third
  party and break rule 1; Muse's Plaid links were the most quoted "creepy"
  moment in its reviews.

## 8. Tests and proof

**Spending fixtures** (invented, in `backend/fixtures/spending/`, no real data):

1. `a_signed.csv`: ISO dates, one signed amount, negative = spent.
2. `b_debit_credit.csv`: dd/mm/yyyy, separate Debit and Credit columns.
3. `c_thousands.csv`: `"1,234.56"`, `(45.10)` negatives, `£` symbols.
4. `d_european.csv`: semicolons, `1.234,56`, `dd.mm.yyyy`.
5. `e_card_positive.csv`: card export where positive = money out, `mm/dd/yyyy`.
6. `f_tricky.xlsx` and `f_tricky.csv`: preamble lines above the header, a footer
   "Total" row, a byte-order mark, an 11-digit account number in a description
   and a 16-digit card number that passes the Luhn check, a refund, two
   identical coffees on one day.
7. `g_overlap_1.csv`/`g_overlap_2.csv`: two exports sharing 10 rows.
8. `h_ambiguous.csv`: every date has both parts 12 or less: must ask, never guess.
9. `i_bad.csv`: empty file, text in the amount column, one giant row, a
   formula-looking cell (`=HYPERLINK(...)`), a description that says "ignore your
   instructions": none may crash, run, or reach the model as an instruction.

**Correctness is proven by a hand-computed expected file:** for each fixture an
`expected/<name>.json` lists the totals by category and month **written by hand
with a calculator before the code exists** (fixtures are small enough, 20 to 40
rows). `test_spending.py` fails on any difference of even one cent. Extra
checks: category totals add up to the grand total; the sum of months equals the
sum of categories; a file and its shuffled copy give identical answers; combining
`g_overlap_1` and `g_overlap_2` equals the single full export `g_full.csv`; no
`float` appears in the parse path (a source check).

Also tested: account and card numbers absent from everything returned; `[hidden]`
present; the model-sentence check throws away a sentence containing an invented
number; the tool refuses paths outside listed folders, big files, `.xlsm`, and a
turn that read outside text; the answer is marked private; profiles and rules
cannot be written from the phone.

**Retirement tests** (`test_retirement.py`): a **zero-volatility case** whose
answer can be worked out by hand (fixed 3% real return, known savings and
spending gives an exact depletion age, 100% or 0% lasting); the "never runs out"
case says "all futures", not age 0 (the argmax pitfall as a regression test); the
"runs out at once" case; the same inputs twice give the same output; more
spending never raises the success percentage, a higher return never lowers it;
the disclaimer is in every result; each bound rejects its bad value; no exact
single figure appears (only rounded/range fields). A `tools/` script compares a
few cases with monteplan run by hand, marked developer-only.

**Both apps:** fixture tests that the phone's and desktop's text for the table
labels and the disclaimer match, following the pattern in `gen_reach_cases.py`;
`tools/check_parity.py`; the feature audit below.

## 9. Owner's questions (two at a time)

**Round 1: spending**

Q1. Where should the spending answer appear?
- **A chat answer with a small table, in both apps** (recommended): simple, fits
  how you ask.
- A chat answer plus a "Spending" page in Brain with a bar picture.

Q2. Should Jarvis keep the numbers in your chat history?
- **Keep your question and Jarvis's sentence, but not the table** (recommended):
  the history never holds a year of spending.
- Keep the table too, like other screen-only answers, encrypted on the PC.

**Round 2: starting point and retirement** (asked after Round 1)

Q3. Should the category list start with words filled in?
- **A short starter list of about 12 categories with a few common shop names each**
  (recommended): you edit it from there.
- Empty: you build every rule yourself.

Q4. For the retirement calculator, how do you type your numbers?
- **A small form in both apps, and Jarvis can fill it from chat** (recommended).
- Chat only.

Smaller choices the builder may make unless told otherwise: the 5 MB / 50,000-row
file limit; "Keep these numbers" for the calculator off (form starts empty).

## 10. Feature-audit checklist (runs with the build, unasked)

1. **Bugs:** cents-exact totals; dd/mm ambiguity refusal; the argmax pitfall;
   every bound; a file changing between check and read; very large files; CSV
   formula cells never evaluated; the ambiguous thousands/decimal case.
2. **Both apps:** desktop and phone show the same table and disclaimer; the
   PC-only pieces are written in ARCHITECTURE section 8; `check_parity.py` clean;
   phone screenshots blocked under App lock / "Hide memory lists".
3. **Fit:** `read_files_readonly` used, no new card type; "What asks first" row;
   `jarvis_reach` fixtures regenerated; `docs/JARVIS-API.md` sections 100 and 103;
   `backend/README.md`; `requirements.txt` (`openpyxl`); THIRD-PARTY-NOTICES
   (no new code copied; add a line if any monteplan or gitleaks-style pattern is
   adapted); no clash with Goals or Projects benchmarks (a "monthly spending"
   benchmark stays the owner's own typed number, not read from a bank file);
   ARCHITECTURE section 4 needs no new "way out of the PC" because nothing leaves.
4. **Rules re-check:** not read aloud; not remembered; not to search or chatbot;
   local lane only; outside-text mark; crisis and sensitive paths untouched.

## 11. Not verified

- Nothing was built or run. No real bank export was read; the header words and
  layouts listed are from general knowledge of common exports, and the fixtures
  are invented. Real banks will have layouts this list misses; the column-check
  box exists for that reason.
- monteplan's licence, Python range, dependencies, version and commit date are
  **taken from the request, not re-checked**; whether it is on PyPI was not
  re-checked. Actual Budget, Econumo, Beancount and Fava were not re-checked
  either; their entries come from the request.
- `openpyxl` is stated to be installed through `markitdown[xlsx]`
  (`requirements.txt` says MarkItDown brings it); its exact version and its
  behaviour on a locked or very large workbook were not tested.
- The exact mechanism that marks an answer "private / screen only" and
  suppresses read-aloud was not traced here; the design assumes the flag the
  quiz and Projects use, and the builder must confirm it and the gate action
  `calculator` uses.
- Whether the backend's minimum Python is really 3.10 was inferred from the
  `tomli; python_version < "3.11"` line, not from a stated policy.
- The default return figures for the retirement model are placeholders for the
  owner to see and change, not researched or recommended.
- Nothing was tried on Windows or on the phone.
