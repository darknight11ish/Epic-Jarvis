"""test_api_doc.py - hold `docs/JARVIS-API.md` to the code it describes.

    python3 backend/test_api_doc.py

WHY THIS EXISTS. On 2026-10-10 a prompt audit read the API document against a
SIDE BRANCH rather than `main` and concluded the running install was 12 modules
ahead of the repository. Re-run against `origin/main` and against
`jarvis-backend/` (the published base), the opposite was true for six of those
modules. The same audit found four pieces of the document that had simply gone
stale - a list that said "Seven" where the code says ten, a repeating reminder
said to raise a card it stopped raising on 2026-09-26, four implemented phrases
that appeared nowhere, and two lines that named as absent a file the repository
had held for weeks.

Every one of those was a sentence somebody had trusted instead of re-checking.
This suite is the machine that re-checks the ones this repository can settle
from its own tree. It is deliberately narrow: it checks the claims that have a
definite answer in code, and it checks NOTHING it cannot read.

A CHECK THAT CANNOT FIND ITS SOURCE FAILS. Every helper below raises `Anchor`
rather than returning an empty result, so a section renamed, a table moved or
`docs/JARVIS-API.md` deleted is a red run with the anchor's own name in the
message - never a quiet pass over an empty string. That is the whole point: the
drift this catches is exactly the kind that looks fine when nothing is read.

WHAT IT PROVES
  1. section 41.1's count word ("Ten sentences") is the word for
     `jarvis_sayable.SENTENCES`' own length, and its table lists exactly those
     sentences, in order, each naming the module that really answers it.
  2. Every interruption-budget sentence documented in section 123.4 (section 58.2's own
     neighbour) really matches `jarvis_quick.py`'s grammar, as the intent that
     changes that number.
  3. section 21.5 no longer marks a plain repeating reminder "(a card)", and the
     scheduler really does register only `alarm` and `reminder`
     `plain_repeat=True` - so the document and the card rule agree.
  4. The two snooze windows in section 21.9 are the two constants: the route reaches
     back a day (`FIRED_KEEP`), the list and the phrase one hour
     (`WENT_OFF_SHOWN`).
  5. section 123.1's count matches the rows in `jarvis_limits.LIMITS` written by hand,
     and names every one of them.
  6. No line says a module this repository holds is "not in this repository" -
     the family of sentence that went stale the moment the base backend was
     published.
  7. The four PM4 routes both apps depend on are FROZEN in section 88.12
     (ruling 5.3, 2026-11-21): the page lists each route's request and response
     keys and its status codes, the build notes 88.10/88.11 point at it, and
     `tools/check_parity.py` keeps them classified the way the freeze says -
     the shared three `ported`, the desktop-only export `deliberate`.
  8. The Updates card's `PROOF:` phase labels are FROZEN in section 184.12
     (ruling 2, 2026-11-21): the page's four labels are exactly
     `BOUNDED_PROOF_PHASES`' four names, in order, and the section says that
     changing one is a breaking change with the same treatment as a route
     change. The page is read against `tools/update_backend.py`'s own tuple.

No network, no model.
"""
from __future__ import annotations

import ast
import importlib.util
import inspect
import re
import shutil
import sys
import tempfile
import textwrap
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_sayable.py", "jarvis_quick.py", "jarvis_schedule.py",
                "jarvis_limits.py", "jarvis_projects.py")

import jarvis_quick as Q  # noqa: E402
import jarvis_limits as L  # noqa: E402
import jarvis_sayable as S  # noqa: E402
import jarvis_schedule as SCHED  # noqa: E402

#: `jarvis_projects`' writes pass through `jarvis_framework`'s audit log, and
#: the real module lives on the owner's PC only. This suite builds a real store
#: in a TEMPORARY folder (never the owner's), so the same stub
#: `backend/test_projects.py` uses is installed before the import: no audit
#: line, no config read, no owner file touched.
_fw = types.ModuleType("jarvis_framework")
_fw.CONFIG_DIR = HERE
_fw.LOG_DIR = HERE
_fw.load_framework = lambda: {}
_fw.audit_log = lambda event, detail=None: None
_fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = _fw

import jarvis_projects as P  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []

DOC = REPO / "docs" / "JARVIS-API.md"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


class Anchor(Exception):
    """The document, or the code, does not read the way this check needs.

    Raised - never swallowed - so a moved section is a failure that names
    itself instead of a check that quietly compared nothing to nothing.
    """


def text() -> str:
    if not DOC.is_file():
        raise Anchor(f"docs/JARVIS-API.md is not at {DOC}")
    return DOC.read_text(encoding="utf-8")


def section(src: str, start: str, end: str, what: str) -> str:
    i = src.find(start)
    if i < 0:
        raise Anchor(f"{what}: the anchor {start!r} is not in docs/JARVIS-API.md")
    j = src.find(end, i + len(start))
    if j < 0:
        raise Anchor(f"{what}: the closing anchor {end!r} is not after {start!r}")
    return src[i:j]


def table_rows(block: str, what: str, first_cell_starts=None) -> list:
    """The data rows of the first markdown table in `block`, split on `|`.

    A row is a line beginning `|`; the `|---|` separator and the header are
    dropped. Finding no rows at all is an Anchor: a table that vanished is not
    a table with nothing in it."""
    rows, started = [], False
    for line in block.splitlines():
        if not line.startswith("|"):
            if started:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if not started:
            started = True          # the header row
            continue
        if first_cell_starts is not None and not cells[0].startswith(first_cell_starts):
            continue
        rows.append(cells)
    if not rows:
        raise Anchor(f"{what}: no table rows found in the block that should hold them")
    return rows


WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
         "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
         "sixteen", "seventeen", "eighteen", "nineteen", "twenty")


def word(n: int) -> str:
    if not 0 <= n < len(WORDS):
        raise Anchor(f"no word is written for {n} - extend WORDS in this test")
    return WORDS[n]


QUOTED = re.compile(r'"([^"]+)"')


def one_quote(s: str) -> str:
    got = QUOTED.findall(s)
    if not got:
        raise Anchor(f"no quoted sentence in {s!r}")
    return got[0]


# ---------------------------------------------------------------- section 41 things

def t_the_sayable_list_matches_the_code():
    """section 41.1: the count, the table, and the JSON sketch, all three."""
    block = section(text(), "### 41.1 The list, and how it was picked",
                    "### 41.2 The route", "section 41.1")
    n = len(S.SENTENCES)

    m = re.search(r"^(\w+) sentences, each checked against", block, re.M)
    if m is None:
        raise Anchor("section 41.1 no longer says '<word> sentences, each checked "
                     "against ...' - the count this check reads is gone")
    check(f"section 41.1's count word is {word(n)!r}, the length of "
          f"jarvis_sayable.SENTENCES", m.group(1).lower() == word(n),
          f"the document says {m.group(1)!r}; the code has {n}")

    rows = table_rows(block[block.index("| Sentence | Answered by |"):], "section 41.1's table")
    documented = [one_quote(r[0]) for r in rows]
    check("section 41.1's table lists exactly jarvis_sayable.SENTENCES, in order",
          documented == list(S.SENTENCES),
          f"document {documented}\n        code     {list(S.SENTENCES)}")

    # EVERY documented sentence is answered by the intent the row names - the
    # row's own claim, checked against jarvis_quick.py's real grammar - and
    # every module it names is really in the tree. A row that named a module
    # which does not exist, an intent the grammar does not reach, or a
    # sentence that stopped matching all fail here.
    for row in rows:
        sentence = one_quote(row[0])
        named = re.findall(r"`([^`]+)`", row[1])
        if not named:
            raise Anchor(f"section 41.1's row for {sentence!r} names nothing in "
                         "backticks - this check cannot tell what answers it")
        intent = Q.match(sentence)
        check(f"the grammar really answers section 41.1's {sentence!r}",
              intent is not None)
        if intent is not None:
            check(f"... and it is the intent the row names: {named[0]!r}",
                  intent.name == named[0],
                  f"the row says {named[0]!r}; the grammar answers {intent.name!r}")
        for mod in [n for n in named if n.endswith(".py")]:
            where = next((p for p in (REPO / "jarvis-backend" / mod,
                                      REPO / "backend" / mod) if p.is_file()), None)
            check(f"section 41.1 names a module that is really here: {mod}",
                  where is not None)

    src = text()
    m = re.search(r'"sentences": \[<the (\d+), in order>\]', src)
    if m is None:
        raise Anchor("the route's JSON sketch no longer carries "
                     "'\"sentences\": [<the N, in order>]' anywhere in the document")
    check("the JSON sketch counts the same list",
          int(m.group(1)) == n, f"the sketch says {m.group(1)}; the code has {n}")

    m = re.search(r'"walkthrough_examples": \[<3 of the (\d+),', src)
    if m is None:
        raise Anchor("the route's JSON sketch no longer carries the "
                     "walkthrough_examples line")
    check("... and so does the walkthrough line",
          int(m.group(1)) == n, f"the sketch says {m.group(1)}; the code has {n}")

    # The two other places in the document that counted the same list.
    for phrase in ("shows the 10 sentences as tappable buttons",
                   "3 of the 10 (`WALKTHROUGH_EXAMPLES`)"):
        if n == 10:
            check(f"section 41.4 says {phrase!r}", phrase in src)
        else:
            skip(f"section 41.4's wording check assumes ten sentences; the code has {n}")


def t_every_documented_sentence_is_answered_by_the_module_it_names():
    """The same claim as above, asked the other way round: nothing the code
    serves is missing from the document either. A list that grows in
    jarvis_sayable.py and not in section 41.1 fails here."""
    block = section(text(), "### 41.1 The list, and how it was picked",
                    "### 41.2 The route", "section 41.1")
    rows = table_rows(block[block.index("| Sentence | Answered by |"):], "section 41.1's table")
    documented = {one_quote(r[0]) for r in rows}
    for s in S.SENTENCES:
        check(f"the document lists the served sentence {s!r}", s in documented)


# ------------------------------------------------- the interruption budget

def t_the_budget_phrases_are_in_the_grammar():
    """section 123.4's table, every quoted sentence, against jarvis_quick.match()."""
    block = section(text(), "### 123.4 The interruption budget",
                    "Both routes are reached by tapping", "section 123.4")
    rows = table_rows(block, "section 123.4's phrase table")
    seen = []
    for row in rows:
        sentences = QUOTED.findall(row[0])
        if not sentences:
            raise Anchor(f"section 123.4's row {row[0]!r} quotes no sentence")
        for s in sentences:
            seen.append(s)
            intent = Q.match(s)
            check(f"the grammar really answers section 123.4's {s!r}",
                  intent is not None and intent.name == "settings_budget",
                  f"got {None if intent is None else intent.name!r}")
    check("section 123.4 documents the four shapes the audit found undocumented",
          all(any(s.startswith(p) for s in seen) for p in
              ("speak up", "speak up less", "speak up more", "the brief",
               "the digest arrives")),
          seen)

    # section 58.2's own neighbour table must carry the same phrases: the budget is a
    # setting sentence like every other row there, and it was the one missing.
    block = section(text(), "### 58.2 \"Adjust a setting\"",
                    "### 58.3", "section 58.2")
    rows = table_rows(block, "section 58.2's table")
    joined = "\n".join(r[1] for r in rows if len(r) > 1)
    for s in ("speak up", "speak up less", "speak up more", "the brief at 8pm",
              "the digest arrives at 7 in the morning"):
        check(f"section 58.2's table carries {s!r}", s in joined)
    m = re.search(r"^(\w+) settings are covered", block, re.M)
    if m is None:
        raise Anchor("section 58.2 no longer says '<word> settings are covered'")
    check("section 58.2's count of covered settings matches its own table",
          m.group(1).lower() == word(len(rows)),
          f"it says {m.group(1)!r}; the table has {len(rows)} settings rows")


# --------------------------------------------------- the repeating-card rule

def t_a_plain_repeat_really_needs_no_card():
    """section 21.5's Reminders row against the scheduler's own registrations."""
    block = section(text(), "### 21.5 Answered without the model",
                    "### 21.6", "section 21.5")

    for example in ("remind me every weekday at 7 to take my pills",
                    "remind me to stretch every 2 hours"):
        row = next((l for l in block.splitlines()
                    if l.startswith("| Reminders |") and example in l), None)
        if row is None:
            raise Anchor(f"section 21.5's Reminders row no longer carries {example!r}")
        check(f"section 21.5 does not mark a plain repeat '(a card)': {example!r}",
              "(a card)" not in row, row.strip())

    plain = {name for name, k in SCHED.KINDS.items() if getattr(k, "plain_repeat", False)}
    check("only alarm and reminder are plain_repeat - the rule the paragraph states",
          plain == {"alarm", "reminder"},
          f"jarvis_schedule says {sorted(plain)}")
    check("... and both of them, so a repeat of either really is set up at once",
          {"alarm", "reminder"} <= set(SCHED.KINDS))

    check("section 21.5 says which repeats DO card (the briefing and \"tell me when\")",
          "A repeating briefing" in block and '"tell me when"' in block)


# ------------------------------------------------------- the snooze windows

def t_the_two_snooze_windows_are_the_two_constants():
    """section 21.9: the routes' and the list's day against the phrase's hour."""
    block = section(text(), "### 21.9 Snooze", "**\"Cancel that\".**", "section 21.9")

    check("section 21.9 no longer says a snooze reaches back 'in the last day'",
          "(in the last day)" not in block)
    check("section 21.9 names the routes' own window, FIRED_KEEP, as a day",
          "FIRED_KEEP" in block and "24 hours" in block)
    check("section 21.9 names the list's window, WENT_OFF_SHOWN, as that same day",
          "WENT_OFF_SHOWN" in block and "same day" in block)
    check("section 21.9 names the phrase's own window, SNOOZE_SHOWN, as one hour",
          "SNOOZE_SHOWN" in block and "own hour" in block)

    check("FIRED_KEEP really is a day", SCHED.FIRED_KEEP == 24 * 3600.0,
          f"jarvis_schedule says {SCHED.FIRED_KEEP}")
    check("WENT_OFF_SHOWN really is the day a fired job is kept",
          SCHED.WENT_OFF_SHOWN == SCHED.FIRED_KEEP,
          f"jarvis_schedule says {SCHED.WENT_OFF_SHOWN}")
    check("SNOOZE_SHOWN really is one hour", SCHED.SNOOZE_SHOWN == 3600.0,
          f"jarvis_schedule says {SCHED.SNOOZE_SHOWN}")

    src = (HERE / "jarvis_quick.py").read_text(encoding="utf-8")
    check("... and the phrase path says 'the last hour' in its own words",
          "went off in the last hour, so there is nothing to snooze." in src)


# ------------------------------------------------------- the limits table

def t_the_limits_table_matches_the_code():
    """section 123.1's count word and its rows against jarvis_limits.LIMITS."""
    block = section(text(), "### 123.1 One table, one route, for every limit",
                    "Two fields, two different jobs", "section 123.1")
    rows = table_rows(block, "section 123.1's limits table", first_cell_starts="`")
    documented = [r[0].strip("`") for r in rows]

    written_by_hand = [x.key for x in L.LIMITS if not x.key.startswith("notif_")]
    check("section 123.1's table lists every limit written by hand, in order",
          documented == written_by_hand,
          f"document {documented}\n        code     {written_by_hand}")

    m = re.search(r"(\w+) of them \(`jarvis_limits\.LIMITS`", block)
    if m is None:
        raise Anchor("section 123.1 no longer says '<word> of them "
                     "(`jarvis_limits.LIMITS` ...'")
    check(f"section 123.1's count word is {word(len(written_by_hand))!r}",
          m.group(1).lower() == word(len(written_by_hand)),
          f"it says {m.group(1)!r}; the code has {len(written_by_hand)} written by hand")

    notify = [x.key for x in L.LIMITS if x.key.startswith("notif_")]
    check("... and it admits the notification rows that join the same table",
          "eight more" in block and len(notify) == 8,
          f"jarvis_limits adds {len(notify)} notification rows")


# ------------------------------- the PM4 route contract, frozen (ruling 5.3)

#: Ruling 5.3 (Gemini, 2026-11-21): the four PM4 routes both apps now depend on
#: are frozen into this page. The section is ONE stable heading on purpose - a
#: moved or renamed frozen contract is a contract change, and these checks name
#: it instead of quietly comparing nothing to nothing.
PM4_HEADING = "### 88.12 The PM4 route contract (FROZEN, 2026-11-21)"
PM4_END = "## 89. The sun, the moon and the weather behind the animals"

#: Each frozen route: the page's spelling, `tools/check_parity.py`'s key, the
#: method it answers, and the classification the freeze gives it. The shared
#: three are `ported` because BOTH apps call them; the export stays
#: `deliberate` - the desktop's alone, with its reason written down.
PM4_ROUTES = (
    ("/api/projects/<id>/plan", "/api/projects/{id}/plan", "GET", "ported"),
    ("/api/projects/<id>/work_items", "/api/projects/{id}/work_items", "POST",
     "ported"),
    ("/api/projects/<id>/work_items/<wid>/status",
     "/api/projects/{id}/work_items/{id}/status", "POST", "ported"),
    ("/api/projects/<id>/export", "/api/projects/{id}/export", "POST",
     "deliberate"),
)

#: The status codes the frozen status table must list for each route. All of
#: them are answered by the real handler in `_pm4_answer()` except the two that
#: need a card or a receipt: the `202` of an export whose card is still up, and
#: the `200` of a status change (which leaves its `jarvis_undo` receipt). Those
#: two are proved against a real store in `backend/test_projects.py`, so this
#: check never has to draw a card or write the owner's receipts store.
PM4_STATUS_CODES = {
    "/api/projects/<id>/plan": {"200", "404"},
    "/api/projects/<id>/work_items": {"200", "400", "404", "405"},
    "/api/projects/<id>/work_items/<wid>/status": {"200", "400", "404", "405"},
    "/api/projects/<id>/export": {"202", "200", "404", "405"},
}


def pm4_block() -> str:
    """The frozen contract's own text, anchored by its heading and section 89."""
    return section(text(), PM4_HEADING, PM4_END, "the frozen PM4 contract")


def key_line(block: str, label: str) -> list:
    """The backticked keys on the block's `- **<label>:** ...` line."""
    m = re.search(r"^[ \t]*- \*\*" + re.escape(label) + r":\*\* (.+)$", block,
                  re.M)
    if m is None:
        raise Anchor(f"the frozen PM4 contract no longer carries a "
                     f"'- **{label}:** ...' line, so its keys cannot be read")
    return re.findall(r"`([^`]+)`", m.group(1))


def returned_answer_keys(fn) -> list:
    """The dict-literal keys of every answer a route function returns.

    `return 202, {...}` and `return {...}` are both read, by walking the `ast`
    nodes - the project's own replacement for a source-text pin, so renaming a
    local or reformatting the function cannot turn this red.
    """
    fn_text = textwrap.dedent(inspect.getsource(fn))
    tree = ast.parse(fn_text)
    answers = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        value = node.value
        pieces = value.elts if isinstance(value, ast.Tuple) else [value]
        for piece in pieces:
            if (isinstance(piece, ast.Dict)
                    and all(isinstance(k, ast.Constant)
                            and isinstance(k.value, str) for k in piece.keys)):
                answers.append({k.value for k in piece.keys})
    if not answers:
        raise Anchor(f"no dict-literal answer found in {fn.__name__}")
    return answers


def _pm4_answer() -> dict:
    """A real plan read and Quick Add from a real store in a temp folder.

    Nothing here touches the owner's `projects.db`, receipts store or audit
    log: the store is created under `tempfile.mkdtemp()` and removed again, and
    the framework stub above makes the audit log a no-op. The status change is
    NOT called for its 200 (that writes a receipt); only its refusals are,
    which are raised before any write.
    """
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-api-doc-"))
    try:
        s = P.Projects(tmp / "projects.db")
        pid = s.create({"name": "Doc probe", "kind": "life"}, here=True)["id"]
        s.set_plan_fields(pid, {"objective": "the owner's own words",
                                "success_criteria": "what done looks like",
                                "status": "active", "target_date": "2026-04-12"})
        mid = s.add_milestone(pid, {"title": "A milestone"})["id"]
        first = s.add_work_item(pid, {"title": "A step", "status": "ready",
                                      "milestone": mid})
        second = s.add_work_item(pid, {"title": "A blocker", "status": "ready"})
        s.add_edge("blocks", second["id"], first["id"])
        code, plan = P.handle_get(f"/api/projects/{pid}/plan", "", store=s)
        if code != 200:
            raise Anchor(f"the plan route answers {code} on a real store")
        add_code, add = P.handle_post(f"/api/projects/{pid}/work_items",
                                      {"title": "  A typed task  "}, store=s)
        if add_code != 200:
            raise Anchor(f"Quick Add answers {add_code} on a real store")
        blocked = next(i for i in plan["work_items"] if i["id"] == first["id"])
        gone = "0" * 32
        item = first["id"]
        # Every status answer the frozen table names, from the REAL handler.
        # The two that need a card or a receipt are left to test_projects.py.
        codes = {
            "plan": P.handle_get(f"/api/projects/{pid}/plan", "",
                                 store=s)[0],
            "plan_unknown": P.handle_get(f"/api/projects/{gone}/plan", "",
                                         store=s)[0],
            "plan_post": P.handle_post(f"/api/projects/{pid}/plan", {},
                                       store=s)[0],
            "add": add_code,
            "add_bad_key": P.handle_post(f"/api/projects/{pid}/work_items",
                                         {"title": "Dated",
                                          "due_date": "2026-01-01"},
                                         store=s)[0],
            "add_unknown": P.handle_post(f"/api/projects/{gone}/work_items",
                                         {"title": "Nowhere"}, store=s)[0],
            "add_get": P.handle_get(f"/api/projects/{pid}/work_items", "",
                                    store=s)[0],
            "status_get": P.handle_get(
                f"/api/projects/{pid}/work_items/{item}/status", "",
                store=s)[0],
            "status_bad": P.handle_post(
                f"/api/projects/{pid}/work_items/{item}/status",
                {"status": "finished"}, store=s)[0],
            "status_unknown_item": P.handle_post(
                f"/api/projects/{pid}/work_items/{'a' * 32}/status",
                {"status": "done"}, store=s)[0],
            "export_get": P.handle_get(f"/api/projects/{pid}/export", "",
                                       store=s)[0],
            "export_unknown": P.handle_post(f"/api/projects/{gone}/export",
                                            {}, store=s)[0],
        }
        return {"plan": plan, "add": add, "blocked": blocked, "codes": codes,
                "pid": pid}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t_the_pm4_routes_are_frozen_and_the_build_notes_point_at_them():
    """Ruling 5.3: one stable FROZEN section owns the four routes, and the two
    PM4 build notes (88.10, 88.11) point at it instead of standing alone."""
    doc = text()
    block = pm4_block()
    low = block.lower()

    check("the frozen section says it IS the frozen contract",
          "frozen contract" in low)
    check("... and names the ruling that froze it", "ruling 5.3" in low)
    check("... and says a change is written there FIRST, not in the code",
          "written in this section first" in low)
    check("... and says sections 88.10/88.11 are now the build record",
          "build record" in low)

    head = "| Route | Method | Called by | Card |"
    if head not in block:
        raise Anchor("the frozen PM4 contract no longer opens with its "
                     "'| Route | Method | Called by | Card |' table")
    rows = table_rows(block[block.index(head):], "the frozen PM4 at-a-glance table")
    got = [(r[0].strip("`"), r[1].strip("`")) for r in rows]
    check("the frozen section lists exactly the four routes with their methods",
          got == [(route, method) for route, _key, method, _kind in PM4_ROUTES],
          got)
    by_route = {r[0].strip("`"): r for r in rows}
    for route, _key, _method, kind in PM4_ROUTES:
        row = by_route.get(route)
        check(f"{route} is in the frozen at-a-glance table", row is not None)
        if row is None:
            continue
        card = row[3].lower()
        if kind == "deliberate":
            check(f"{route} names the ONE notes-editor card it raises",
                  "edit_vault_note" in card, row[3])
        else:
            check(f"{route} is recorded as cardless", card.startswith("none"), row[3])
    for phrase, what in (
            ("read-only", "the plan read is read-only"),
            ("cardless", "the two writes are cardless"),
            ("owner-direct", "the two writes are the owner's own"),
            ("stale link", "both apps hold the writes on a stale link (rule 4)"),
            ("gate action", "no route adds a gate action"),
            ("new permission", "no route adds a permission"),
            ("creates `projects.db`", "the read never creates projects.db"),
            ("edit_vault_note` card", "the export raises the notes editor's card"),
            ("never read back", "the hub note is one-way"),
    ):
        check(f"the frozen contract says {what}", phrase in low)

    build10 = section(doc, "### 88.10 ", "### 88.11 ", "section 88.10")
    build11 = section(doc, "### 88.11 ", PM4_HEADING, "section 88.11")
    check("section 88.10 points at the frozen contract", "88.12" in build10)
    check("section 88.11 points at the frozen contract", "88.12" in build11)
    check("section 88.10 no longer calls the work-item states 'five'",
          "five states" not in build10 and "outside the five" not in build10)


def t_the_pm4_plan_read_keys_are_the_codes_own():
    """The frozen plan read's key lists are the REAL answer's keys, not a
    remembered list: the check builds a real store and reads the route."""
    block = pm4_block()
    answer = _pm4_answer()
    plan = answer["plan"]
    documented = {
        "top-level keys": set(key_line(block, "top-level keys")),
        "counts keys": set(key_line(block, "counts keys")),
        "milestone keys": set(key_line(block, "milestone keys")),
        "work item keys": set(key_line(block, "work item keys")),
        "blocked_by keys": set(key_line(block, "blocked_by keys")),
        "event keys": set(key_line(block, "event keys")),
    }
    real = {
        "top-level keys": set(plan),
        "counts keys": set(plan["counts"]),
        "milestone keys": set(plan["milestones"][0]),
        "work item keys": set(plan["work_items"][0]),
        "blocked_by keys": set(answer["blocked"]["blocked_by"][0]),
        "event keys": set(plan["events"][0]),
    }
    for label in documented:
        check(f"the frozen plan read's {label} are exactly the answer's keys",
              documented[label] == real[label],
              f"document {sorted(documented[label])}\n        code     {sorted(real[label])}")
    check("a blocked item in the real answer names its blocker",
          answer["blocked"]["blocked_by"],
          "the probe store must really have an open blocking edge")
    check("... so the blocked_by key list above is measured, not empty",
          answer["blocked"]["blocked_by"] != [])


def t_the_pm4_requests_and_status_lists_are_the_codes_own():
    """The frozen request keys, state lists and status codes are the code's."""
    block = pm4_block()
    answer = _pm4_answer()
    codes = answer["codes"]

    check("Quick Add's frozen request takes exactly title",
          key_line(block, "add request keys") == ["title"])
    check("... and the store's own door accepts exactly that one key",
          set(P.APP_ADD_FIELDS) == {"title"}, sorted(P.APP_ADD_FIELDS))
    check("the status tap's frozen request takes exactly status",
          key_line(block, "status request keys") == ["status"])
    check("the frozen work-item states are the store's seven, in its order",
          key_line(block, "work-item statuses") == list(P.WORK_STATUSES),
          f"document {key_line(block, 'work-item statuses')}\n"
          f"        code     {list(P.WORK_STATUSES)}")
    check("the frozen project states are the store's five, in its order",
          key_line(block, "project statuses") == list(P.PROJECT_STATUSES),
          f"document {key_line(block, 'project statuses')}\n"
          f"        code     {list(P.PROJECT_STATUSES)}")
    check("the frozen executor values are the store's four",
          key_line(block, "executor values") == list(P.EXECUTORS),
          f"document {key_line(block, 'executor values')}\n"
          f"        code     {list(P.EXECUTORS)}")
    check("the ready list's frozen cap is PLAN_READY_MAX",
          str(P.PLAN_READY_MAX) in block and "capped at" in block.lower())
    check("the event window's frozen bound is PLAN_EVENTS_MAX",
          str(P.PLAN_EVENTS_MAX) in block)
    check("the export's frozen request reads no body field",
          "no body field is read" in block.lower())

    head = "| Route | Success | Bad request | Not found | Wrong method |"
    if head not in block:
        raise Anchor("the frozen PM4 contract no longer carries its "
                     "'| Route | Success | Bad request | Not found | Wrong method |' "
                     "status table")
    rows = table_rows(block[block.index(head):], "the frozen PM4 status table")
    documented = {}
    for row in rows:
        route = row[0].strip("`")
        documented[route] = set(re.findall(r"`(\d{3})`", " | ".join(row[1:])))
    check("the frozen status table lists exactly the four routes",
          set(documented) == set(PM4_STATUS_CODES), sorted(documented))
    for route, wanted in PM4_STATUS_CODES.items():
        check(f"{route}'s frozen status codes are {sorted(wanted)}",
              documented.get(route) == wanted, documented.get(route))

    # The real handler answers every documented code except the card/receipt
    # two; the codes below ARE the ones each situation answers.
    check("the plan read answers 200 on a real store", codes["plan"] == 200, codes)
    for name, wanted in (
            ("plan_unknown", 404), ("plan_post", 404),
            ("add", 200), ("add_bad_key", 400), ("add_unknown", 404),
            ("add_get", 405), ("status_get", 405), ("status_bad", 400),
            ("status_unknown_item", 404), ("export_get", 405),
            ("export_unknown", 404)):
        check(f"the real route answers {wanted} where the frozen table says "
              f"{wanted} ({name})", codes[name] == wanted, codes[name])


def t_the_pm4_write_and_export_answers_are_the_codes_own():
    """The frozen answer keys are the keys the code really builds."""
    block = pm4_block()
    answer = _pm4_answer()
    check("the frozen add answer keys are the real Quick Add answer's",
          set(key_line(block, "add answer keys")) == set(answer["add"]),
          f"document {key_line(block, 'add answer keys')}\n"
          f"        code     {sorted(answer['add'])}")
    check("... and its frozen message is the real one",
          'Added "<the title>".' in block)
    check("... and the real answer really says it",
          answer["add"]["message"] == 'Added "A typed task".',
          answer["add"]["message"])

    status_answers = returned_answer_keys(P.change_work_item_status)
    check("the status route builds exactly ONE answer", len(status_answers) == 1)
    check("the frozen status answer keys are that answer's keys",
          len(status_answers) == 1
          and set(key_line(block, "status answer keys")) == status_answers[0],
          f"document {key_line(block, 'status answer keys')}\n"
          f"        code     {sorted(status_answers[0]) if status_answers else None}")

    export_answers = returned_answer_keys(P.request_export_hub)
    check("the export route builds three answers: waiting, saved, refused",
          len(export_answers) == 3, export_answers)
    if len(export_answers) == 3:
        common = set.intersection(*export_answers)
        extra = set.union(*export_answers) - common
        check("every frozen export answer key is on all three answers",
              set(key_line(block, "export answer keys")) == common,
              f"document {sorted(key_line(block, 'export answer keys'))}\n"
              f"        code     {sorted(common)}")
        check("... and only the refused answer adds the frozen `error` key",
              extra == {"error"}
              and sum("error" in a for a in export_answers) == 1,
              (sorted(extra), sum("error" in a for a in export_answers)))


def _parity_module():
    """`tools/check_parity.py` loaded from the tree - the same existing path
    `backend/test_creator_mode.py` uses to read a CLASSIFICATION entry."""
    spec = importlib.util.spec_from_file_location("pm4_check_parity",
                                                  REPO / "tools" / "check_parity.py")
    if spec is None or spec.loader is None:
        raise Anchor("tools/check_parity.py cannot be loaded")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def t_the_pm4_parity_classification_is_frozen():
    """`tools/check_parity.py`: the shared three stay `ported`, the export stays
    `deliberate`, and every reason names the frozen contract (ruling 5.3)."""
    mod = _parity_module()
    for route, key, _method, kind in PM4_ROUTES:
        entry = mod.CLASSIFICATION.get(key)
        check(f"{route} is classified in tools/check_parity.py",
              entry is not None, key)
        if entry is None:
            continue
        status, why = entry
        check(f"{route} stays {kind!r} - the freeze does not move it",
              status == kind, status)
        check(f"{route}'s reason is written down", len(why) > 80, len(why))
        low = why.lower()
        check(f"{route}'s reason names the frozen section, 88.12",
              "88.12" in why, why[:160])
        check(f"{route}'s reason says it is frozen", "frozen" in low, why[:160])
        if kind == "ported":
            check(f"{route}'s reason says BOTH apps call it",
                  "both apps" in low, why[:160])
        else:
            check(f"{route}'s reason says why the phone deliberately has none",
                  "phone" in low and "deliberate" in low, why[:160])


# -------------------------- the bounded proof's PROOF: contract, frozen (ruling 2)

#: Ruling 2 (Gemini, 2026-11-21): the four phase labels the Updates card shows
#: are frozen into this page, because the card renders the
#: `PROOF: Step N/4 - <phase> - x of y` line VERBATIM. The section is ONE stable
#: heading on purpose - a moved or renamed frozen contract is a contract change,
#: and this check names it instead of quietly comparing nothing to nothing.
PROOF_HEADING = "### 184.12 The Updates card's PROOF: contract (FROZEN, 2026-11-21)"
PROOF_END = "## 185. Jarvis measures its own token speed"


def bounded_proof_phase_names() -> list:
    """`BOUNDED_PROOF_PHASES`'s four `name` values, in order, from the tool's source.

    Read by parsing `tools/update_backend.py` with `ast`, never by importing it:
    the contract this check needs is the literal tuple, and a tool that failed
    to import for an unrelated reason must not turn a doc check into a skip.
    """
    path = REPO / "tools" / "update_backend.py"
    if not path.is_file():
        raise Anchor(f"{path} is not in this checkout, so the frozen phase "
                     "list cannot be read")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name)
                   and target.id == "BOUNDED_PROOF_PHASES"
                   for target in node.targets):
            continue
        if not isinstance(node.value, ast.Tuple):
            raise Anchor("BOUNDED_PROOF_PHASES is no longer a tuple of dicts")
        names = []
        for element in node.value.elts:
            if not isinstance(element, ast.Dict):
                raise Anchor("BOUNDED_PROOF_PHASES is no longer a tuple of dicts")
            keyed = {key.value: value for key, value in zip(element.keys,
                                                           element.values)
                     if isinstance(key, ast.Constant)}
            name = keyed.get("name")
            if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
                raise Anchor("a BOUNDED_PROOF_PHASES entry has no string 'name'")
            names.append(name.value)
        if names:
            return names
    raise Anchor("tools/update_backend.py has no BOUNDED_PROOF_PHASES tuple of names")


def t_the_bounded_proof_phase_names_are_frozen_in_the_page():
    """Ruling 2: the page's four frozen labels ARE the code's four names, in order."""
    block = section(text(), PROOF_HEADING, PROOF_END, "the frozen PROOF: contract")
    documented = re.findall(r"^- `([^`]+)`$", block, re.M)
    code = bounded_proof_phase_names()
    check("the frozen PROOF: contract lists four phase labels", len(documented) == 4,
          documented)
    check("... and they are BOUNDED_PROOF_PHASES' four names, in order",
          documented == code, (documented, code))
    flat = " ".join(block.split())
    check("... the section says changing a label is now a BREAKING change",
          "breaking change" in flat, block[:240])
    check("... and that it needs the same treatment as a route change",
          "same treatment as a route change" in flat, flat[:400])
    check("... and it names the card's progress line shape",
          "PROOF: Step 2/4 - instant API answers - 1 of 1" in flat, flat[:400])


# ------------------------------------- "not in this repository", the family

#: Modules this check holds the document to. Every one of them is in the
#: repository as the published base; the sentence the audit found stale is the
#: one that says otherwise.
IN_THE_REPOSITORY = ("jarvis_hud.py", "jarvis_arbiter.py", "jarvis_gate.py",
                     "jarvis_content_risk.py", "jarvis_watch.py")

NOT_HERE = ("not in this repository", "not in the repository",
            "this repository does not hold", "this repository does not have",
            "repository does not hold")


def t_nothing_held_here_is_called_absent():
    src = text()
    lines = src.splitlines()
    for mod in IN_THE_REPOSITORY:
        where = next((p for p in (REPO / "jarvis-backend" / mod,
                                  REPO / "backend" / mod) if p.is_file()), None)
        check(f"{mod} is really in the repository, so calling it absent is wrong",
              where is not None,
              "this check is meaningless while the module itself is missing")

    for i, line in enumerate(lines):
        window = " ".join(lines[i:i + 2]).lower()
        if not any(p in window for p in NOT_HERE):
            continue
        named = [m for m in IN_THE_REPOSITORY if m in window]
        if named:
            check(f"docs/JARVIS-API.md:{i + 1} does not call {named[0]} absent",
                  False, f"{line.strip()}\n        {lines[i + 1].strip() if i + 1 < len(lines) else ''}")


def main():
    for fn in (t_the_sayable_list_matches_the_code,
               t_every_documented_sentence_is_answered_by_the_module_it_names,
               t_the_budget_phrases_are_in_the_grammar,
               t_a_plain_repeat_really_needs_no_card,
               t_the_two_snooze_windows_are_the_two_constants,
               t_the_limits_table_matches_the_code,
               t_the_pm4_routes_are_frozen_and_the_build_notes_point_at_them,
               t_the_pm4_plan_read_keys_are_the_codes_own,
               t_the_pm4_requests_and_status_lists_are_the_codes_own,
               t_the_pm4_write_and_export_answers_are_the_codes_own,
               t_the_pm4_parity_classification_is_frozen,
               t_the_bounded_proof_phase_names_are_frozen_in_the_page,
               t_nothing_held_here_is_called_absent):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Anchor as exc:
            FAILED.append(fn.__name__)
            print(f"FAIL  {fn.__name__}: {exc}")
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
