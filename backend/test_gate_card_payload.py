"""The two fields every approval card gained on 2026-11-06: hidden bytes, cost.

    python3 test_gate_card_payload.py

THE OWNER'S RULING (2026-11-06 11:35 PT, next-sprint PR 2, Hermes borrows #1
and #7):

  * a card's own text is scanned for hidden Unicode - zero-width characters,
    bidirectional controls, other control bytes - and for a long run of
    padding, and a card that has any is marked so BOTH apps can draw a warning
    pill. Deterministic, and it never changes what the card SAYS.
  * a card that can spend money carries what it costs: one answer's estimate,
    this month's cloud ledger, and the cap the owner set - all from real
    numbers the repo already keeps (the model price table and the money file
    the monthly limit is enforced against). A card that cannot spend money
    carries neither field, and a ledger that cannot be read produces the
    REASON, never an invented figure.

Where the fields are built: `jarvis_gate.pending()`, the one function that
makes the row both apps draw. That is why these checks read it there rather
than reading two clients.

Runs anywhere: a temp approvals database, and a stand-in for the money module
whose numbers are chosen so the arithmetic is checkable by hand.
"""
import json
import os
import sqlite3
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _base  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# A temp home BEFORE the import: jarvis_gate opens its queue at import time.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-card-payload-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP)
os.environ["JARVIS_APPROVALS_DB"] = str(_TMP / "approvals.db")
os.environ["JARVIS_NTFY_TOPIC"] = ""
# Long enough that no row inserted below is expired by _init()'s sweep.
os.environ["JARVIS_APPROVAL_TIMEOUT"] = "600"

# The same framework stub the other gate suites use: redaction on, a real tier
# table, and an audit log that goes nowhere.
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {
    "logging": {"redact_private_content_in_logs": True},
    "autonomy": {"unknown_action_tier": "ask", "tiers": {}},
}
fw.audit_log = lambda *a, **k: None
sys.modules["jarvis_framework"] = fw

BASE = _base.folder("jarvis_gate.py")
if BASE is not None:
    _base.put_on_path(BASE)
    _base.say(BASE, "jarvis_gate.py")

import jarvis_gate as G  # noqa: E402


def _insert(rid, action, detail, prompt, state="pending"):
    """One waiting row, written the same shape check() writes."""
    G._init()
    if isinstance(detail, str):
        detail_text = detail
    else:
        detail_text = json.dumps(detail)
    with sqlite3.connect(str(G.DB_PATH)) as c:
        c.execute(
            "INSERT OR REPLACE INTO approvals (id,action,tier,detail,prompt,state,created)"
            " VALUES (?,?,?,?,?,?,?)",
            (rid, action, "ask", detail_text, prompt, state, time.time()))


def _row(rid):
    for row in G.pending():
        if row.get("id") == rid:
            return row
    return {}


# --------------------------------------------------------------------------
#   The detector itself: zero-width, bidi, control, padding
# --------------------------------------------------------------------------

def t_clean_text_is_never_flagged():
    for text in ("Install the update and restart Jarvis.",
                 "Send the report to Anna - the one from Tuesday.",
                 "Cost: $12.50 (about 20% off)\r\nSecond line\tstill fine.",
                 "A curly quote \u201cand\u201d an en dash \u2013 and an em dash \u2014"):
        check(f"clean text is not flagged: {text[:32]!r}",
              G.hidden_bytes(text) == [], G.hidden_bytes(text))


def t_a_bidi_override_is_one_entry_with_the_pc_label():
    rows = G.hidden_bytes("Install now\u202e then restart")
    check("U+202E is found once", len(rows) == 1, rows)
    if not rows:
        return
    row = rows[0]
    check("U+202E's label is the pill's own words",
          row.get("label") == "[hidden byte: U+202E]", row)
    check("U+202E's code point is named", row.get("codepoint") == "U+202E", row)
    check("U+202E's position is where it is", row.get("position") == 11, row)
    check("U+202E is called a bidi control", row.get("kind") == "bidi", row)


def t_a_zero_width_character_is_one_entry():
    rows = G.hidden_bytes("Jarvis\u200bplease run this")
    check("U+200B is found once", len(rows) == 1, rows)
    if rows:
        check("U+200B's label is the pill's own words",
              rows[0].get("label") == "[hidden byte: U+200B]", rows[0])
        check("U+200B's position is where it is", rows[0].get("position") == 6, rows)
        check("U+200B is called zero-width", rows[0].get("kind") == "zero-width", rows)


def t_a_control_byte_is_one_entry_and_whitespace_is_not():
    rows = G.hidden_bytes("rm -rf\x07 the folder")
    check("U+0007 is one entry", len(rows) == 1 and rows[0]["label"] == "[hidden byte: U+0007]",
          rows)
    check("a newline, a tab and a carriage return are ordinary text",
          G.hidden_bytes("a\nb\tc\r\nd") == [], G.hidden_bytes("a\nb\tc\r\nd"))


def t_a_run_of_twenty_spaces_is_the_padding_entry():
    rows = G.hidden_bytes("Files:" + " " * 20 + "renamed.vbs")
    check("a run of 20 spaces is one entry", len(rows) == 1, rows)
    if rows:
        check("the padding label counts the spaces",
              rows[0].get("label") == "[whitespace padding: 20 spaces]", rows[0])
        check("the padding entry says where the run starts",
              rows[0].get("position") == 6, rows[0])
        check("the padding entry's kind is padding", rows[0].get("kind") == "padding", rows)
    check("19 spaces is ordinary text (the boundary is 20)",
          G.hidden_bytes("Files:" + " " * 19 + "x") == [],
          G.hidden_bytes("Files:" + " " * 19 + "x"))


def t_one_entry_per_run_not_per_character():
    rows = G.hidden_bytes("a" + "\u200b" * 5 + "b\u202e\u202e c")
    check("five zero-widths in a row are ONE entry",
          len([r for r in rows if r["kind"] == "zero-width"]) == 1, rows)
    check("two bidi controls in a row are ONE entry",
          len([r for r in rows if r["kind"] == "bidi"]) == 1, rows)
    zw = [r for r in rows if r["kind"] == "zero-width"]
    check("... and the run's count is 5", zw and zw[0]["count"] == 5, zw)


# --------------------------------------------------------------------------
#   What pending() attaches, and what it must not
# --------------------------------------------------------------------------

def t_a_clean_card_carries_an_empty_list_and_no_pill():
    _insert("clean1", "send_email",
            {"text": "Send the report to Anna - the one from Tuesday.",
             "to": "anna@example.com"},
            "Send the report?")
    row = _row("clean1")
    check("a clean card is served", bool(row), row)
    check("a clean card's hidden_bytes is [] (so no pill is drawn)",
          row.get("hidden_bytes") == [], row.get("hidden_bytes"))
    check("... and carries no 'more' count", "hidden_bytes_more" not in row, list(row))


def t_a_dirty_card_names_the_byte_on_the_row():
    # `detail.text` is what a card SHOWS, and it wins over `prompt` - the same
    # choice the desktop's apprDescribe makes, so the scan is over what the
    # reader really sees.
    _insert("dirty1", "run_shell_on_host",
            {"text": "Delete the folder\u202e and empty the bin"},
            "Delete the folder?")
    row = _row("dirty1")
    check("a dirty card carries one entry",
          len(row.get("hidden_bytes") or []) == 1, row.get("hidden_bytes"))
    check("... with the PC's label on it",
          (row.get("hidden_bytes") or [{}])[0].get("label") == "[hidden byte: U+202E]",
          row.get("hidden_bytes"))
    # The card's own words are NOT changed by the scan: the text is byte for
    # byte what was stored.
    detail = json.loads(row.get("detail") or "{}")
    check("the card's text is unchanged by the scan",
          detail.get("text") == "Delete the folder\u202e and empty the bin", detail)


def t_a_hostile_line_is_capped_and_counted():
    text = "".join(ch + "\u200b" for ch in "abcdefghijklmnop")
    _insert("many1", "run_shell_on_host", {"text": text}, text)
    row = _row("many1")
    rows = row.get("hidden_bytes") or []
    check("at most MAX_HIDDEN_ROWS entries reach the card",
          len(rows) == G.MAX_HIDDEN_ROWS, len(rows))
    check("the rest are COUNTED, not silently dropped",
          row.get("hidden_bytes_more") == 16 - G.MAX_HIDDEN_ROWS,
          row.get("hidden_bytes_more"))


def t_pending_text_is_the_card_text_and_nothing_else():
    _insert("text1", "send_email", {"text": "The text a card shows"}, "the prompt")
    check("pending_text answers with detail.text", G.pending_text("text1") == "The text a card shows",
          G.pending_text("text1"))
    check("an unknown id answers with an empty string", G.pending_text("nope") == "")
    _insert("done1", "send_email", {"text": "already answered"}, "p", state="denied")
    check("a decided card answers with an empty string", G.pending_text("done1") == "",
          G.pending_text("done1"))


# --------------------------------------------------------------------------
#   What a card costs
# --------------------------------------------------------------------------

def _fake_money(*, load=None, limit=10.0, spent=1.14, requests=380,
                estimate_if_no_average=0.003, price=True):
    """A stand-in for jarvis_chatbot_api with numbers chosen to be checkable.

    1.14 spent over 380 requests IS $0.003 a request, which is the ruling's
    own example line - so a reader can do the arithmetic.
    """
    m = types.ModuleType("jarvis_chatbot_api")
    m.PRESETS = {"deepseek_api": types.SimpleNamespace(
        short="deepseek", company="DeepSeek", name="DeepSeek-V4", model="deepseek-flash")}
    m.BY_SHORT = {"deepseek": "deepseek_api"}
    m.DEFAULT_PRICES = {("deepseek_api", "deepseek-flash"): (0.30, 1.20)}

    def _load():
        if load is not None:
            raise load
        return {}

    m._load = _load
    m.month_key = lambda: "2026-11"
    m.limit_of = lambda pid, data=None: limit
    m.spent_of = lambda pid, data=None, month=None: spent
    m.price_of = (lambda pid, model, data=None: (0.30, 1.20, "default")) if price else (
        lambda pid, model, data=None: None)
    m.cost_of = (lambda pid, model, pt, ct, data=None: estimate_if_no_average) if price else (
        lambda pid, model, pt, ct, data=None: None)
    m.model_for = lambda pid: ("deepseek-flash", "")
    # The months row the average is read from. `pending()` asks _load() for it
    # only when it needs the average, and this is that row.
    m._MONTHS = {"2026-11": {"deepseek_api": {"dollars": spent, "requests": requests}}}
    return m


def _with_money(module, fn):
    """Run `fn` with `jarvis_chatbot_api` replaced, then put the real one back."""
    real = sys.modules.get("jarvis_chatbot_api")
    sys.modules["jarvis_chatbot_api"] = module
    try:
        return fn()
    finally:
        if real is None:
            sys.modules.pop("jarvis_chatbot_api", None)
        else:
            sys.modules["jarvis_chatbot_api"] = real


def _cost_for(rid, action, detail):
    _insert(rid, action, detail, "the prompt")
    row = _row(rid)
    return row.get("cost", "ABSENT")


def t_a_cloud_card_carries_the_three_real_numbers():
    # The months row is read from `_load()`, so the average needs a dict.
    m = _fake_money()

    def run():
        data = {"months": m._MONTHS}
        m._load = lambda: data
        # The card's detail names the service; the ledger comes from the
        # module. Every number below is the fake's, by construction.
        _insert("cloud1", "raise_a_limit",
                {"text": "Let Jarvis spend up to $10.00 a month on DeepSeek?",
                 "service": "deepseek"}, "raise the limit?")
        return _row("cloud1").get("cost")
    cost = _with_money(m, run)
    check("a cloud card carries a cost", isinstance(cost, dict), cost)
    check("... with one answer's estimate", cost and cost.get("estimate_usd") == 0.003, cost)
    check("... the month's own ledger", cost and cost.get("monthly_usd") == 1.14, cost)
    check("... and the cap the owner set", cost and cost.get("cap_usd") == 10.0, cost)


def t_a_local_card_carries_no_cost_at_all():
    m = _fake_money()
    cost = _with_money(m, lambda: _cost_for("local1", "send_email",
                                           {"text": "Send it", "to": "a@b.c"}))
    check("an ordinary card has no cost field", cost == "ABSENT", cost)


def t_a_card_cannot_claim_a_cost_when_the_ledger_is_unreadable():
    m = _fake_money(load=RuntimeError("the money file is gone"))

    def run():
        _insert("broken1", "raise_a_limit",
                {"text": "Let Jarvis spend up to $10 a month?", "service": "deepseek"},
                "raise the limit?")
        return _row("broken1").get("cost")
    cost = _with_money(m, run)
    check("an unreadable ledger produces a cost object", isinstance(cost, dict), cost)
    check("... with NO number in it",
          not any(k in cost for k in ("estimate_usd", "monthly_usd", "cap_usd")), cost)
    check("... and the reason, in plain words",
          "cannot be read" in str(cost.get("why") or ""), cost)


def t_no_limit_and_no_price_are_said_not_guessed():
    m = _fake_money(limit=None)

    def run_no_limit():
        _insert("nolimit1", "raise_a_limit",
                {"text": "x", "service": "deepseek"}, "p")
        return _row("nolimit1").get("cost")
    cost = _with_money(m, run_no_limit)
    check("no monthly limit: a reason, never a number",
          isinstance(cost, dict) and "why" in cost and "monthly money limit" in cost["why"],
          cost)

    m2 = _fake_money(price=False)

    def run_no_price():
        _insert("noprice1", "raise_a_limit", {"text": "x", "service": "deepseek"}, "p")
        return _row("noprice1").get("cost")
    cost = _with_money(m2, run_no_price)
    check("no price for the model: a reason, never a number",
          isinstance(cost, dict) and "why" in cost and "no price" in cost["why"], cost)


def t_the_explicit_cloud_mark_is_what_a_shared_action_reads():
    """`change_own_config` is every settings card. Only the one that spends
    money (the standing cloud switch) is marked, and only it gets the line."""
    m = _fake_money()

    def run():
        data = {"months": m._MONTHS}
        m._load = lambda: data
        _insert("marked1", "change_own_config",
                {"text": "Let hard questions go to the cloud?",
                 "costs_money": "cloud", "pid": "deepseek_api"}, "p")
        _insert("unmarked1", "change_own_config",
                {"text": "Turn on the night light?"}, "p")
        return _row("marked1").get("cost"), _row("unmarked1").get("cost", "ABSENT")
    marked, unmarked = _with_money(m, run)
    check("a marked change_own_config card carries a cost", isinstance(marked, dict), marked)
    check("an unmarked one carries none", unmarked == "ABSENT", unmarked)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
