# Finance: spending summaries and a retirement what-if (design, 2026-09-30)

Status: **built** (re-checked 2026-10-05; this page called itself a design until
the claims register re-checked it): spending summaries are
`backend/jarvis_spending.py` + `spending.patch` (JARVIS-API section 100), and
the retirement what-if is `backend/jarvis_retirement.py` + `retirement.patch`
(section 103). Two pieces from the owner's build queue
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


## Slice contract (frozen)

Written 2026-09-30, when part A (spending summaries, queue item 2, JARVIS-API section 100)
was built on the backend. **Amended 2026-09-30 after the audit** (the changes are marked
"(audit)" below; the fixture file was regenerated, so the apps' tests follow it). **Two other builders (the desktop, the phone) build against this
section.** Do not change a field name, a value or a word below on either app's side; if
something here is wrong, say so and the backend changes first. Part B (the retirement
what-if, section 103) is not frozen; it will reuse the `sections` shape but not necessarily
this exact block.

Built and tested on the backend: `backend/jarvis_spending.py`, `backend/jarvis_money_parse.py`
(shipped whole), `backend/spending.patch` (one install block), the `my_spending` tool in
`backend/jarvis_agent.py`, `backend/test_spending.py` (471 checks, totals worked out by
hand in `backend/fixtures/spending/expected.json`). **The reference for every shape and every
word is one generated file, made by the real code:**

```
python3 tools/gen_spending_cases.py            # write both copies
python3 tools/gen_spending_cases.py --check    # compare only (test_spending.py runs it)
  jarvis-desktop/tests/fixtures/spending-cases.json
  jarvis-client/app/src/test/resources/contract/spending-cases.json    (byte-identical)
```

Both apps' tests load it. It holds `words` (every shared sentence, exact), `sign_sentences`,
`errors`, `tables` (six tables: by_category, by_month, by_category_and_month,
two_files_overlapping, two_currencies, one_category) and the `GET /api/spending` and
column-check answers in named situations (`view_pc_*`, `view_phone_*`, `proposal_*`).
Neither app writes a word or a figure of its own for the table; it draws what the file says.

### 1. How a table reaches an app

1. `POST /api/chat` streams as usual. When the answer used `my_spending` and a table was
   made, the stream carries ONE comment line, immediately BEFORE the answer's sentence:

   ```
   : jarvis-table 3f9c0a5e1d7b4c2a8e6f01b2c3d4e5f6

   ```

   (`: jarvis-table ` + 32 lowercase hex characters + a blank line, the same style as
   `: jarvis-status <word>`). It is an SSE comment: an app that does not know it ignores it.
   A `stream: false` reply carries the same id as a top-level `"jarvis_table": "<id>"` on the
   completion body. The words of the answer (the `data:` chunks) are the checked sentence
   alone; they never contain a figure that is not in the table.
2. The app fetches `GET /api/chat/table?id=<id>` (header `X-Jarvis-Token`, `X-Jarvis-Client:
   hud`, like every request) -> `200 {"ok": true, "table": {...}}`, or
   `404 {"ok": false, "error": "gone", "message": <words.TABLE_GONE>}`. The table is kept two
   hours in memory (the last 50) and can be fetched again.
3. **Hidden states: do NOT fetch, and draw `words.TABLE_HIDDEN` ("Spending table hidden") in
   its place**, when (a) "Hide memory lists and chat history" is on, or (b) on the desktop,
   App lock is on and the app is locked (fetch and draw when it unlocks; the id is still good
   for two hours). Phone: those two states already block screenshots; the table is one more
   thing on that screen.
4. **The table is never stored by an app**: not in `localStorage`, DataStore, Room, a log
   or a saved chat. It lives in memory for the conversation on screen and is dropped when the
   conversation is cleared or the app closes. After a restart the thread shows the sentence
   only (that is all chat history keeps: `words.TABLE_GONE` if the app tries the old id).
5. **Never read aloud.** Nothing to add: the tool is not on the read-aloud list
   (`private-aloud-cases.json` was regenerated with `my_spending` in the tool list), so the
   apps' existing rule keeps a spoken answer on screen and says its own fixed line. A table
   is never spoken, copied, shared or exported in this first version (no export button).

### 2. The table block (`GET /api/chat/table` -> `table`)

```
{
 "kind": "spending", "version": 1,
 "title":  "Spending by category, March 2026",
 "period": "March 2026",                       // or "2026-03-01 to 2026-04-02" when no period was asked
 "sources": ["bank-march.csv (layout: Main account)"],   // file name + the saved layout used (audit); digits hidden; at most 6
 "columns": [{"key": "category", "label": "Category", "align": "left"},
             {"key": "spent",    "label": "Spent",    "align": "right"},
             {"key": "rows",     "label": "Rows",     "align": "right"}],
 "sections": [                                  // one per currency; ONE for nearly every file
   {"heading": "GBP" | "",  "currency": "GBP" | "",
    "rows":   [{"kind": "category" | "uncategorised" | "month", "cells": ["Food and groceries", "70.40", "2"]}],
    "totals": [{"kind": "total", "cells": ["Total spent", "119.64", "7"]}],
    "also":   [{"kind": "refunds" | "income" | "transfers", "cells": ["Refunds (already taken off above)", "5.10", "1"]}]}],
 "caveats": ["3 rows were in more than one file and were counted once.", "..."],
 "private": true, "read_aloud": false, "remember": false,
 "words": {"hidden": "Spending table hidden"}
}
```

Rules for drawing it:

- `columns[i]` names the i-th string of every `cells` list; **every `cells` list has exactly
  `len(columns)` strings, in every section and every group** (a test enforces it). Draw a
  string as it is: figures are already formatted ("1,234.56", a leading minus for a
  negative, no currency symbol - the section `heading` is the currency). **An app never adds,
  rounds, sorts, re-formats or hides a figure**, and never computes a percentage or a bar
  from them (a bar picture is a possible later slice).
- `align`: `"left"` for the first column, `"right"` for figures.
- `sections`: draw `heading` (when not empty) as a small title above its rows; two currencies
  are two sections, never merged. `rows`, then `totals` (bold, a rule above), then `also`
  (smaller, muted: refunds, income, transfers are shown apart from spending, not netted).
  `kind: "uncategorised"` is an ordinary row with a neutral style (never red, no warning
  icon); it is always present, even at 0.00 and 0 rows.
- Three layouts, by `columns`: (name, Spent, Rows) for `by: category` and `by: month`;
  (Category, one column per month, Total) for both - up to 13 columns, so the phone scrolls
  the table sideways and the desktop lets it scroll inside the chat bubble.
- `title` (strong), then `period` (muted), then the table, then `caveats` as a short muted
  list under it (each already a full sentence; do not join or reword them), then `sources`
  as one muted line ("From: a.csv (layout: Main account), b.csv (layout: Card)"; the
  "(layout: ...)" text is already in each string - a layout with no name is "Saved layout"). No streaks, no praise, no warnings, no colour
  meaning good or bad.
- `private: true` means: not in any copy-to-clipboard/share path, not in notifications, not
  in the widget or the tray, not in a screenshot when the app is locked/hidden (see 1.3).
- Screen reader (both): each row is read as its cells joined by commas with the column
  labels ("Food and groceries, Spent 70.40, Rows 2"); the totals row first says "Total".

### 3. The words (exact, in `spending-cases.json` -> `words`)

`TITLE` "Spending", `DETAIL`, `PC_ONLY`, `NEEDS_SETUP_ON_PC`, `EMPTY_PROFILES`,
`STARTER_NOTE`, `HIDDEN_COLUMNS_NOTE`, `TABLE_HIDDEN`, `TABLE_GONE`, `SPOKEN_LINE`,
`NO_SENTENCE_LINE`, `DROPPED_LINE`, `NO_TABLE_LINE`, `SAVED_LAYOUT`, `SLOW_FIRST_TIME`
(audit), the row labels `ROW_TOTAL`, `ROW_UNCATEGORISED`,
`ROW_REFUNDS`, `ROW_INCOME`, `ROW_TRANSFERS_OUT`, `ROW_TRANSFERS_IN`, and the caveats
`CAV_*` (already filled in the table; listed so a test can check the app never re-words
them; `CAV_SHEETS` and `CAV_ACCOUNTS` are new), and the box's `COUNTS_LINE`,
`COUNTS_UNREAD` (audit) and the empty-period pieces `EMPTY_SKIPPED`, `EMPTY_SKIPPED_ONE`,
`EMPTY_RANGE`. The sign sentences are `sign_sentences` (negative_out, positive_out, debit_credit,
drcr). Error texts the backend returns as `message` are in `errors`. **The app shows
`message`/the words as given.** Words only the desktop uses (the column-check box) are in
section 5 below. Phone words: `TITLE`, `DETAIL`, `PC_ONLY` ("Set up on the PC: Settings,
Spending. The columns of a new bank file are checked there, once."), `EMPTY_PROFILES`,
`STARTER_NOTE`, `TABLE_HIDDEN`, `TABLE_GONE`.

### 4. `GET /api/spending` (any device) - who reads what

`{"available", "title", "detail", "can_edit", "pc_only", "profiles": [{"id", "label",
"columns", "sign", "sign_sentence", "saved"}], "empty_profiles", "categories": [{"category",
"words": [..]}], "categories_are_starter", "starter_note", "waiting": [{"name", "path"?}],
"sign_sentences", "needs_setup", "table_hidden"}`. **On the PC only (audit)** it also carries
`"bank_files": [{"name", "path", "kind": "csv"|"xlsx", "layout_id": <a profiles[].id or
null>, "checked": bool, "waiting": bool}]` - the bank-looking files in the listed folders,
for the file picker below (no other device gets it).

- `can_edit` is true only for a request from this PC. `waiting[].path` is present only on the
  PC (a bank file whose columns are not checked yet, kept in memory; it leaves the list once a
  saved layout fits it).
- **Phone**: a read-only "Spending" plate in Brain (a plain list, like Folders): `title`,
  `detail`, the categories with their words, `starter_note` when `categories_are_starter`,
  the saved layouts (`label`, `columns`, `sign_sentence`), each waiting file's `name` with
  `needs_setup`, and `pc_only` at the top ("Set up on the PC ..."). **No edit control, no
  form.** The phone also asks the questions in the ordinary chat and draws the table.
- **Desktop**: Settings, "Spending" (beside "Folders Jarvis may look in"), see section 5.

### 5. The PC-only box (desktop builds it; the phone never does)

Routes (full request and answer shapes: JARVIS-API section 100.4; every write is **403
`pc_only`** from any other device; none raises an approval card):

| route | use |
|---|---|
| `GET /api/spending/profile?file=<path>` | the proposal for a waiting file (or `known: true` with its saved profile) |
| `GET /api/spending/profile?file=<path>&again=1` | (audit) "Check the columns again": a fresh proposal with the saved choices filled in (`again: true`, `saved_choices`, `questions: []`, `counts`, `line`); a saved layout that no longer fits comes back the same way with `misfit`. **Nothing is deleted.** |
| `POST /api/spending/profile` | save the confirmed columns (`confirm: true` required; (audit) `answered` = the questions the box asked, `accept_warnings` only after the owner ticked "save it anyway") |
| `POST /api/spending/profile` with `preview: true` | (audit) what the choices would count before saving: `{ready, counts: {out, in, rows, unread}, line, problems, warnings}` |
| `POST /api/spending/profile/delete` `{id}` | forget a saved layout |
| `POST /api/spending/categories` `{categories}` / `{reset: true}` | save or reset the category words |
| `POST /api/spending/suggest` `{file}` | proposals for shop names no rule catches (nothing saved) |

"Check these columns" (a dialog opened from a `waiting` row, or from a saved layout's row):

1. Call `GET /api/spending/profile?file=<waiting[i].path>` (URL-encoded).
2. Show `hidden_note` when `hidden_columns > 0`. Show a table of `header` + `preview` (already
   hidden; private columns removed; `header[i]` is original column `header_index[i]`).
3. Choices, each a dropdown: **Date column**, **Description column**, then **how the amounts
   are written** as three radio choices - "One amount column" (`sign` negative_out or
   positive_out, `columns.amount`), "Separate Debit and Credit columns" (`sign` debit_credit,
   `columns.debit` and `columns.credit`), "An amount column and a Dr/Cr column" (`sign` drcr,
   `columns.amount` and `columns.drcr`); the **sign rule** for a single amount column
   ("Minus means money spent" = negative_out, "Plus means money spent" = positive_out);
   **Date order** ("Day first, like 25/03/2026" = dmy, "Month first, like 03/25/2026" = mdy;
   when `guess.date_order` is `ymd` show "The dates say their own order" and no choice);
   **Decimal mark** ("." or ","); **Currency** (free text, at most 6 characters, optional);
   **Name** (free text, at most 60). Dropdown values are ORIGINAL column numbers
   (`header_index`), never positions in `header`.
3a. **(audit) Under the choices, show `line`** ("With these choices, 8 rows count as money out
   and 2 as money in.") from the answer of `preview: true` (ask again after each change, a
   moment after the owner stops). When `warnings` is not empty show them, and keep Save
   disabled until the owner ticks "This does not look right, but save it anyway"; then send
   `accept_warnings: true`. A save the PC refuses as `misfit_confirm` shows its `message` and
   the same tick box. Also send `answered` (the `questions` names the box showed) and
   `date_serial` (from `guess`) with every save. **Name** starts empty - never the file name.
4. Every field named in `questions` starts with no choice and **Save is disabled until each
   has one** (this is the "never guess" rule: `date_order`, `decimal`, `sign`,
   `date_column`, `description_column`, `amount_column`, `header_row`). When `header_row` is
   in `questions` there is no usable guess (`guess` is null): show the first rows, let the
   owner pick the number of the header row and every column themselves, and send that
   `header_row` with the POST (the backend re-reads the file with it).
5. Under the sign choice show `sign_sentences[sign]` (it changes as the choice changes).
6. Save -> `POST /api/spending/profile` with `{file, confirm: true, header_row, columns,
   sign, date_order, decimal, currency, label}` (`guess` filled in with the owner's choices).
   200 -> "Saved. {rows_read} rows read, {rows_skipped} left out." then refresh
   `GET /api/spending`. 400 -> show `message` verbatim.
7. Words for this box (desktop only): dialog title "Check these columns"; button "Save these
   columns"; "Cancel"; a saved layout's button "Forget this layout"; "Check the columns again".
   **(audit) "Check the columns again" never deletes anything first**: it calls
   `GET .../profile?file=<that layout's file>&again=1`, opens this same dialog with the saved
   choices in it, Save writes over the same layout, Cancel changes nothing. The file is the
   one the layout row belongs to (a `bank_files` entry whose `layout_id` is that row's `id`),
   not whatever is in a box. **"Forget this layout" is the only thing that deletes**, and it
   asks "are you sure?" first. **(audit) The free-text "Bank file" box is a picker over
   `bank_files`** (shown by `name`; the value is `path`).

Categories editor (same Settings block): one row per category (name, then its words as
comma-separated text or chips); reorder (first match wins - say so in one line); add and remove
rows; **Save** posts the whole list; **Reset to the starter list** posts `{reset: true}` after
an "are you sure?"; the starter list is shown with `starter_note`. Words are matched whole-word
and case-blind; the editor shows them lower-case as the backend keeps them. "Suggest
categories" (a button, only when a file is chosen) posts `/suggest`, shows each `{name,
category}` ticked with a plain "Add these rules" button (unticking drops it); adding merges the
ticked names into that category's words and posts the whole list. Nothing is added by the
model on its own. Desktop-only words: "Categories", "Suggest categories", "Add these rules",
"Reset to the starter list", "Save categories".

### 6. What the backend does and does not do (so neither app duplicates it)

- **(audit) A saved layout is checked against the file before it is trusted** (JARVIS-API
  100.4): one that does not fit leaves the file "waiting" and the tool says which layout was
  tried and why; the layout key holds the kind of file (csv/xlsx); Excel numbers, hidden
  sheets and date serials are read as described there; the layout's name is hidden and never
  defaults to the file name; files from different layouts are never matched against each other.
- **(audit) The one sentence's rule**: it may quote only the Total spent figure, or the figure
  on the row whose name is nearest to it; never a row count, a caveat number, a percentage, a
  fraction or a rounded/spelled-out amount. When `my_spending` was called and made no table,
  the model's words are shown only if they carry no amount of money; else the tool's own
  plain sentence is. Both apps show whatever the stream carries, as before.
- **(audit) The conversation becomes money-sensitive** once the tool was called: a later web
  search asks first and a chatbot is not started from it (docs/ARCHITECTURE.md section 5).
- Refuses a bank file after outside text, on a pasted or shared message, and for a second table
  in one answer (the model is told; the app sees nothing special).
- Holds the model's words until code has checked them, so the sentence in the stream is final:
  the app never edits, hides or re-checks it.
- Does not stream the table: it is fetched. Does not put a table in `POST /api/chat`'s
  `X-Jarvis-Route` header (it is sent before the tool runs).
- Not built: a bar picture; any Spending page; asking about a period longer than 12 months by
  month; converting currencies; reading a bank site; Beancount/Plaid/Actual Budget.

### 7. Who builds what

| piece | desktop builder | phone builder |
|---|---|---|
| Read the `: jarvis-table` line (and `jarvis_table` on a JSON body) in the chat stream reader | yes (the window that reads `: jarvis-status`) | yes (the SSE reader that reads it) |
| `GET /api/chat/table` and draw the block in the chat thread (Jarvis bar) | yes (`tests/spending.mjs` against `spending-cases.json` `tables`) | yes (Compose; `SpendingTest.kt` / a contract test against the same file) |
| Hidden states (Hide lists; desktop App lock) and "never stored" | yes | yes (memory only; not in Room/DataStore) |
| `GET /api/spending`, the read-only plate | Settings, Spending (shows everything, editable) | Brain, Spending (read-only, "Set up on the PC") |
| Column check, layouts list, categories editor, suggestions | **yes (PC only)** | **no, on purpose** (ARCHITECTURE section 8 already has the row) |
| Words | copy from `spending-cases.json` (a test compares) | copy from `spending-cases.json` (a test compares) |
| `tools/check_parity.py` | when the desktop calls `/api/spending/profile`, `/profile/delete`, `/categories`, `/suggest`, change their `planned` rows to `deliberate` (kept off the phone); when both call `/api/spending` and `/api/chat/table`, change those to `ported` | |
| The widget (`widget.html`) | not drawn there (it never renders chat text; ARCHITECTURE section 8) | the home-screen widget likewise shows nothing of it |

### 8. Not verified

- No real bank file, no real model, no Windows or phone run. The tests script the model and
  use invented files (`backend/fixtures/spending/`). The header words and layouts are from
  general knowledge of common exports; the column-check box exists for the ones missed.
- `openpyxl` reading ran on Linux with 3.1.5 only.
- Whether the apps' stream readers already tolerate an unknown SSE comment line is assumed
  from `: jarvis-status` (the SSE rule), not tested here.
- Speed: hiding account numbers in descriptions is about 1 second per 1,000 distinct
  descriptions on this container (a 40,000-row file took about 36 seconds the first time; the
  hidden text is then remembered in memory). A period narrows it first.


## Retirement contract (frozen)

Written 2026-09-30, when part B (the retirement what-if, queue item 5, JARVIS-API section 103)
was built on the backend. **Two other builders (the desktop, the phone) build against this
section.** Do not change a field name, a value or a word below on either app's side; if
something here is wrong, say so and the backend changes first. Where this differs from section 6
above (the design), this section wins: it says what was built.

Built and tested: `backend/jarvis_retirement.py` (shipped whole, plain Python, no numpy),
`backend/retirement.patch` (one install block), `backend/test_retirement.py` (174 checks).
Also built (audit fixes, 2026-09-30): the `retirement_whatif` chat tool, registered in
`jarvis_agent.py` (JARVIS-API 103.6; tests in `backend/test_agent_retirement_wiring.py`), which
shows **code-written text only** (the model writes no sentence about the answer), and both apps'
cards. The placeholder return was lowered from 7% to 6% (about 3.4% a year after the 2.5%
placeholder inflation) and every placeholder is now labelled "placeholders for a mix of stocks and
bonds, not a forecast". Both apps are tested against ONE file of the real backend's answers,
`tools/gen_retirement_cases.py` (`python3 tools/gen_retirement_cases.py --check`).

### R1. Where it lives, and what the two apps build

| piece | desktop builder | phone builder |
|---|---|---|
| Place | **Brain -> Work -> Retirement** (a card beside Goals; menu id `brain.work.retirement`) | **Brain -> Retirement** (a plate beside Goals; menu id `brain.retirement`) |
| Menu group | `finance` (`group.finance`, MENU-VISIBILITY-DESIGN section 4). This is the first member of the group, so the group now exists in each app that has this card; the Spending settings card joins it later | same |
| Form: `GET /api/retirement/defaults`, then `POST /api/retirement/run` | yes | yes (the phone sends the numbers to the PC and draws the reply; nothing is computed or stored on the phone) |
| Draw the result and the "What I used" list | yes | yes |
| Hidden states, never stored | yes (also: the app must be unlocked while App lock is on) | yes (screenshots already blocked; memory only, not in Room or DataStore) |
| Words | copy from `GET /defaults` and from the result (never write a figure or a sentence of its own) | same |
| `tools/check_parity.py` | both routes are `planned`; when both apps call them change both to `ported` | |
| One-sided anywhere? | No. Not one-sided: the phone can do this (it is a form and an answer, not a catalogue, memory graph or deep config). | |

### R2. `GET /api/retirement/defaults` (any paired device)

```
{"ok": true, "available": true, "title": "Retirement what-if", "detail": "<one plain paragraph>",
 "fields": [{"key", "label", "unit", "kind": "age"|"money"|"percent", "min", "max",
             "default": number|null, "required": bool, "placeholder": bool, "help"}],
 "paths": 10000, "seed": 20260930, "max_years": 90, "disclaimer", "placeholder_note",
 "todays_money", "band_points": 1.0,
 "words": {"hidden": "Retirement what-if hidden", "busy", "too_slow"},
 "private": true, "read_aloud": false, "remember": false}
```

The form draws `fields` in this order, one input each (a number box; money may be typed with commas,
percent with or without `%`):

| key | label | unit | limits | default |
|---|---|---|---|---|
| `current_age` | Your age now | years | whole 18 to 100 | **none: required** |
| `retirement_age` | Age you stop working | years | whole 18 to 100 | **none: required** |
| `plan_to_age` | Plan the money to age | years | whole 18 to 110, after the retirement age, at most 90 years from now | 95 (placeholder) |
| `savings` | Savings you have now | money | 0 to 1,000,000,000 | **none: required** (0 is fine) |
| `yearly_saving` | You add each year until you stop working | money per year | 0 to 1,000,000,000 | **none: required** (0 is fine) |
| `yearly_spending` | You spend each year in retirement | money per year | 0 to 1,000,000,000 | **none: required** |
| `other_income` | Pension or other income each year (optional) | money per year | 0 to 1,000,000,000 | 0 |
| `other_income_start_age` | That income starts at age (optional) | years | whole 18 to 110 | empty = the retirement age |
| `expected_return_percent` | Expected yearly return before inflation | percent | -5 to 15 | 6.0 (placeholder; about 3.4% after the 2.5% inflation) |
| `volatility_percent` | How much yearly returns swing | percent | 0 to 40 | 12.0 (placeholder) |
| `inflation_percent` | Expected yearly inflation | percent | 0 to 15 | 2.5 (placeholder) |

The form shows the labels, `help` lines and limits **from the response, not from its own copy**.
The three return-related boxes start filled with their placeholder defaults and show
`placeholder_note` beside them ("The return, swing and inflation figures are placeholders for a mix of
stocks and bonds, not a forecast. You can change them. Real life will differ."); the required boxes
start empty (the form never keeps numbers between visits: nothing is saved, no "Keep these
numbers"). An optional box that has a default but does not start filled (the pension's 0) shows it as
a grey hint in the empty box, in BOTH apps. `todays_money` is shown once above the form. Money has no currency sign: the owner's own currency, in today's money.

### R3. `POST /api/retirement/run`

Body: a flat object with the field keys above (numbers, or text like `"1,250,000"` / `"6.5%"`);
empty or missing optional fields take their default. Any other key is refused. Response:

```
200 {"ok": true, "result": {
  "kind": "retirement", "version": 1, "title": "Retirement what-if",
  "state": "mixed" | "never_runs_out" | "always_runs_out" | "not_enough_to_say",
  "reason": null | "no_spending",
  "paths": 10000, "seed": 20260930,
  "share": null | {"per_100": 51, "label": "about 51 of 100", "all": false, "none": false},
  "bands": null | {"lower":  {"per_100", "label", "all", "none", "points": -1.0},
                   "higher": {"per_100", "label", "all", "none", "points":  1.0}},
  "end_balance": null | {"p10": 0, "p50": 12000, "p90": 1800000, "age": 95,
                         "text": {"p10": "0", "p50": "12,000", "p90": "1,800,000"}},
  "poor_case": null | {"lasts": false, "age": 78},
  "runs_out_between": null | [79, 88],
  "middle_lasts_to": null | 95,
  "summary": [<sentence>, ...],
  "text": "<summary joined, then the disclaimer>",
  "used": [{"key", "label", "value": "<string>", "assumed": bool}],
  "todays_money", "placeholder_note",
  "disclaimer": "This is a simplified what-if, not financial advice.",
  "private": true, "read_aloud": false, "remember": false,
  "words": {"hidden": "Retirement what-if hidden"}}}
```

An example made by the real code (40 now, stop at 65, 100,000 saved, 12,000 a year, spend 30,000; all
else the placeholders, so a 6% return): `state` "mixed", `share.label` "about 51 of 100",
`bands.lower.label` "about 31 of 100", `bands.higher.label` "about 71 of 100", `end_balance` p10 0 /
p50 12000 / p90 1800000, `poor_case` `{"lasts": false, "age": 78}`, `runs_out_between` [79, 88] and
`summary` (the real file is `tests/fixtures/retirement-cases.json`, made by
`tools/gen_retirement_cases.py`):

1. In about 51 of 100 simulated futures your money lasts to age 95. Where it runs out, that is usually at about age 79 to 88.
2. If yearly returns are 1 point lower, that becomes about 31 of 100; 1 point higher, about 71 of 100.
3. In a poor case (1 in 10) the money runs out at about age 78.
4. The middle case leaves about 12,000 at age 95; a good case (1 in 10) about 1,800,000.

**What the app draws, in this order:** the `summary` sentences as a short list or paragraph
(exactly as sent, the app never edits, rounds or re-words a figure); the `disclaimer` on its own
line right after them, always visible, never collapsible; a "What I used" list from `used` (an
`assumed: true` row gets the word "assumed" beside it, from the app's own fixed word "assumed");
`placeholder_note`; `todays_money`. Optional: a bar of the three end balances or a share meter drawn
by hand (desktop hand SVG, phone Compose Canvas), only from `share.per_100`, `bands.*.per_100` and
`end_balance`, never as a single big number; no streaks, no colours that mean pass or fail beyond
the plain state words. The headline of the card is `share.label` phrase from the first sentence, not a
lone number.

**States (exact meaning):**

| `state` | when | `summary[0]` starts | share |
|---|---|---|---|
| `mixed` | some futures last, some do not | "In about N of 100 simulated futures your money lasts to age A. Where it runs out, that is usually at about age X to Y." | `label` "about N of 100", N always 1 to 99 (a share that rounds to 0 or 100 is still shown as "about 1" or "about 99"; "fewer than 1" and "more than 99" belong only to the two states below) |
| `never_runs_out` | every future lasts | "In all 10,000 simulated futures your money lasts to age A. That does not mean it is guaranteed." | `label` "more than 99 of 100", `all: true`, `per_100: 99`; `runs_out_between` null, `poor_case.lasts` true |
| `always_runs_out` | no future lasts | "In none of the 10,000 simulated futures does your money last to age A; it runs out at about age X." (or "X to Y") | `label` "fewer than 1 of 100", `none: true`, `per_100: 0` |
| `not_enough_to_say` | yearly spending is 0 | "There is nothing to test: with no spending in retirement the money cannot run out. Type what you expect to spend each year." | `share`, `bands`, `end_balance`, `poor_case`, `runs_out_between`, `middle_lasts_to` are all null |

Other sentences the backend may add, all fixed: "Even in a poor case (1 in 10) it lasts, leaving about
N at age A." (poor case lasts; "leaving very little" when that rounds to nothing); "In the middle
case the money runs out at about age A." (the middle case did NOT last to the plan-to age; a middle
case that lasted but leaves nothing says "The middle case leaves very little at age A, and so does a
good case (1 in 10)." or "...very little at age A; a good case (1 in 10) about N."); "Other income only covers spending; any extra is not saved." (when other income was
typed). The run-out age is **never** shown as 0 or as the starting age for a future that does not run
out (the argmax pitfall): a null `runs_out_between` means there is nothing to say, the app draws no
"runs out" line.

**Errors** (`400 {"ok": false, "error", "field", "message"}`; the app shows `message` next to the
field named in `field`, and never repeats what was typed):

| `error` | when | `message` |
|---|---|---|
| `missing` | a required box is empty | Please type in "<label>". I will not guess it. |
| `bad_number` | text, NaN, infinity, true/false, a fraction for an age | <label> must be a whole number from 18 to 100. (ages) / an amount from 0 to 1,000,000,000 (money) / a number from -5 to 15 (percent; the limits of that field) |
| `negative` | negative money | <label> cannot be negative. |
| `out_of_range` | outside the field's limits | as `bad_number` |
| `plan_not_after` | plan-to age not after the retirement age (or the age now) | The age to plan the money to must be after the age you stop working (and after your age now). |
| `too_many_years` | more than 90 years from now | That is more than 90 years from your age now. Pick a nearer age. |
| `unknown_field` | a key that is not a field (an app bug) | That is not one of the what-if's fields. |
| `bad_request` | not a set of fields | Send the numbers as a set of named fields. |

`429 {"error": "busy", "message": "Another what-if is still being worked out. Try again in a moment."}`
(one run at a time; the app tries once more after a second, then shows the message);
`503 {"error": "too_slow", "message": "That took too long to work out, so it was stopped. Try again."}`.
A run normally takes 1 to 3 seconds on the PC, so both apps show a plain "Working it out" state and
disable the button while waiting. A stale link (rule 4) greys the button like every other action and
BOTH apps say why ("Waiting for the link to catch up. Nothing can be sent until it does."); a result
already on screen stays. Percent boxes also take ".5" and "5." and "7%%" (the phone's early check
accepts them too, and leaves full-width digits to the PC).

### R4. Hidden-lists behaviour, and what is never done

- Under "Hide memory lists and chat history" (both apps) the card shows only `words.hidden`, "Retirement
  what-if hidden", and a **Show** button (both apps, like every hidden section), and no result or form
  value; the form's boxes are emptied when hidden. On the desktop Show asks Windows Hello
  (`reveal_private_answers`) and brings back an EMPTY form; under App lock it cannot lift the lock and
  says "Still hidden. If Jarvis is locked, unlock it first, then press Show.". The desktop also needs
  the app unlocked while App lock is on (the same rule as the spending table); the phone already
  blocks screenshots in both states. The numbers are wiped when the card scrolls away or the window is
  minimised (the owner kept this, 2026-09-30).
- The numbers are never written by an app: not to disk, not to a store, not to a log, not to chat
  history, not to a widget or a notification. The result lives in memory while the card is on
  screen and goes when the owner leaves it. The backend keeps nothing either.
- Never read aloud (in chat too: the tool is not on the read-aloud list, so a spoken question still
  gets its answer on screen only). Never sent to a web search, a chatbot or any cloud lane. Never remembered as a fact
  and never offered to Goals or Projects as a number to track (the owner types those themselves).
- No card, no Windows Hello: this is a calculation on numbers the owner typed.
- Nothing computed on the phone. The phone builds no simulation.

### R5. Fixed words the apps own (not in the response)

The card title comes from `title`. Button: "Work it out". Waiting: "Working it out". The small tag
beside a made-up figure: "assumed". Section heading above the list: "What I used". Everything else
comes from the backend.

### R6. Not verified

- Nothing was run on Windows or the phone; no real model has called the chat tool (the tests script
  the model). The phone's Compose screen was read by eye, not compiled here; its logic
  (`net/Retirement.kt`, `RetirementTest`) was compiled and run.
- The default return (6%), spread (12%) and inflation (2.5%) are placeholders for a mix of stocks and
  bonds, not researched and not a forecast. The share moves by a few points with another random seed,
  and the answer says "about".
- Whether a 30-year-old with 90 years to plan and 10,000 futures stays under the 30-second cap on the
  owner's slowest PC was measured only on this container (about 1 second warm).
