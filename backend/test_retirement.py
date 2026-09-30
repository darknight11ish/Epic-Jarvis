"""test_retirement.py - the retirement what-if (JARVIS-API section 103).

Hand-worked cases use a spread of 0 (no randomness) so the answer can be
worked out on paper; the random ones check what must always hold (same inputs,
same answer; more savings never lowers the share that lasts; the argmax pitfall).
Run: python backend/test_retirement.py
"""
import contextlib
import io
import json
import logging
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_retirement.py", "jarvis_money_parse.py")
import _stack  # noqa: E402
import jarvis_retirement as R  # noqa: E402

FAILED, PASSED = [], []
FAST = 1000            # futures for the random checks (the route itself uses 10,000)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def base(**kw):
    d = dict(current_age=40, retirement_age=65, plan_to_age=95, savings=100000, yearly_saving=12000,
             yearly_spending=30000, expected_return_percent=7.0, volatility_percent=12.0,
             inflation_percent=2.5)
    d.update(kw)
    return d


def flat(**kw):
    """No randomness and no growth: paper arithmetic."""
    return base(expected_return_percent=0, inflation_percent=0, volatility_percent=0, **kw)


def err(raw, **kw):
    try:
        R.run(raw, paths=100, **kw)
    except R.InputError as e:
        return e
    return None


# ============================================================ 1. worked by hand

def t_worked_by_hand():
    # 60 -> retire 65, plan to 80. Saves 10,000 a year for ages 60..64 -> 150,000 at 65.
    # Spends 30,000 from 65: ages 65..69 covered (0 left), age 70 cannot be -> runs out at 70.
    r = R.run(flat(current_age=60, retirement_age=65, plan_to_age=80, savings=100000,
                   yearly_saving=10000), paths=100)
    check("worked: state is always_runs_out", r["state"] == "always_runs_out", r["state"])
    check("worked: runs out at exactly 70", r["runs_out_between"] == [70, 70], r["runs_out_between"])
    check("worked: poor case age 70, not lasting", r["poor_case"] == {"lasts": False, "age": 70})
    # Other income 10,000 from age 67: 65 and 66 cost 30,000 each (150-60=90,000 left); 67.. cost 20,000:
    # 67,68,69,70 -> 10,000 left; age 71 needs 20,000 -> runs out at 71.
    r = R.run(flat(current_age=60, retirement_age=65, plan_to_age=80, savings=100000, yearly_saving=10000,
                   other_income=10000, other_income_start_age=67), paths=100)
    check("worked: pension from 67 moves it to 71", r["runs_out_between"] == [71, 71], r["runs_out_between"])
    # Exactly enough: 300,000 for ages 65..74, plan to 75 -> lasts, ends at 0.
    r = R.run(flat(current_age=65, retirement_age=65, plan_to_age=75, savings=300000, yearly_saving=0),
              paths=100)
    check("worked: exactly enough is a success", r["state"] == "never_runs_out", r["state"])
    check("worked: and leaves nothing", r["end_balance"]["p50"] == 0, r["end_balance"])
    # One cent short of covering the last year is a failure at the last year's age (74).
    r = R.run(flat(current_age=65, retirement_age=65, plan_to_age=75, savings=299999.99, yearly_saving=0),
              paths=100)
    check("worked: a cent short runs out in the last year, at 74",
          r["state"] == "always_runs_out" and r["runs_out_between"] == [74, 74], (r["state"], r["runs_out_between"]))
    # Growth: 1,000 at 10% real for 10 years = 2,593.74; age 40 needs 1 -> (2593.74-1)*1.1 = 2851.99 -> 2.9k
    r = R.run(base(current_age=30, retirement_age=40, plan_to_age=41, savings=1000, yearly_saving=0,
                   yearly_spending=1, expected_return_percent=10, inflation_percent=0, volatility_percent=0),
              paths=100)
    check("worked: compounding to 2 significant figures", r["end_balance"]["p50"] == 2900, r["end_balance"])
    # Inflation is taken out: 7% nominal, 2.5% inflation is (1.07/1.025)-1 = 4.39% real.
    real = 1.07 / 1.025 - 1
    r = R.run(base(current_age=30, retirement_age=40, plan_to_age=41, savings=100000, yearly_saving=0,
                   yearly_spending=1, volatility_percent=0), paths=100)
    want = ((100000 * (1 + real) ** 10) - 1) * (1 + real)
    check("worked: real return is nominal against inflation",
          abs(r["end_balance"]["p50"] - R._round_sig(want)) <= 0, (r["end_balance"]["p50"], want))
    # Surplus income is not saved: spending 10,000, income 50,000 -> balance never grows from it.
    r = R.run(flat(current_age=65, retirement_age=65, plan_to_age=70, savings=1000, yearly_saving=0,
                   yearly_spending=10000, other_income=50000, other_income_start_age=65), paths=100)
    check("worked: income above spending never runs out and adds nothing",
          r["state"] == "never_runs_out" and r["end_balance"]["p50"] == 1000, r["end_balance"])
    # Zero savings, zero spending is 'not enough to say', and says so plainly.
    r = R.run(base(yearly_spending=0), paths=100)
    check("worked: no spending is 'not enough to say'", r["state"] == "not_enough_to_say"
          and r["share"] is None and R.DISCLAIMER in r["text"])
    # Zero savings with saving and spending still works.
    r = R.run(flat(savings=0, current_age=60, retirement_age=62, plan_to_age=70, yearly_saving=50000,
                   yearly_spending=25000), paths=100)
    check("worked: zero savings start (100,000 saved, spends 25,000 from 62 -> 4 years, runs out at 66)",
          r["runs_out_between"] == [66, 66], r["runs_out_between"])
    # Already retired: the yearly saving is ignored.
    r = R.run(flat(current_age=70, retirement_age=65, plan_to_age=75, savings=100000, yearly_saving=99999,
                   yearly_spending=20000), paths=100)
    check("worked: already retired ignores the yearly saving (5 years of 20,000 = 100,000, lasts)",
          r["state"] == "never_runs_out", r["state"])


# ============================================================ 2. the states, in words

def t_states_and_words():
    r = R.run(base(savings=5_000_000, yearly_spending=20000), paths=FAST)
    check("never runs out: state", r["state"] == "never_runs_out", r["state"])
    check("never runs out: 'in all 1,000' plus 'not guaranteed'",
          r["summary"][0].startswith("In all 1,000 simulated futures") and "not mean it is guaranteed" in r["summary"][0])
    check("never runs out: shown as 'more than 99', never 100", r["share"]["label"] == "more than 99 of 100"
          and r["share"]["per_100"] == 99 and r["share"]["all"])
    check("never runs out: no run-out age is invented (argmax pitfall)",
          r["runs_out_between"] is None and r["poor_case"]["lasts"] and r["poor_case"]["age"] is None)
    r = R.run(base(savings=0, yearly_saving=0, yearly_spending=40000), paths=FAST)
    check("always runs out: state, words", r["state"] == "always_runs_out"
          and r["summary"][0].startswith("In none of the 1,000") and "runs out at about age" in r["summary"][0])
    check("always runs out: at the first year of retirement (age 65)", r["runs_out_between"] == [65, 65]
          or r["runs_out_between"][0] >= 40, r["runs_out_between"])
    r = R.run(base(), paths=FAST)
    check("mixed: state and a whole-number share", r["state"] == "mixed" and 1 <= r["share"]["per_100"] <= 99
          and r["share"]["label"] == f"about {r['share']['per_100']} of 100", r["share"])
    check("mixed: the run-out ages are a range low <= high", r["runs_out_between"] is not None
          and r["runs_out_between"][0] <= r["runs_out_between"][1] and r["runs_out_between"][0] >= 65,
          r["runs_out_between"])
    check("mixed: 1 point lower/higher bands", r["bands"]["lower"]["points"] == -1.0
          and r["bands"]["higher"]["points"] == 1.0
          and r["bands"]["lower"]["per_100"] <= r["share"]["per_100"] <= r["bands"]["higher"]["per_100"])
    e = r["end_balance"]
    check("mixed: end balances are ordered and shown to 2 significant figures",
          e["p10"] <= e["p50"] <= e["p90"] and all(len(str(v).rstrip("0")) <= 2 or v < 100 for v in (e["p10"], e["p50"], e["p90"])), e)
    check("the disclaimer is in every result, added by code",
          r["disclaimer"] == "This is a simplified what-if, not financial advice."
          and r["text"].endswith(R.DISCLAIMER))
    for st in (R.run(base(savings=5_000_000), paths=FAST), R.run(base(savings=0, yearly_saving=0), paths=FAST),
               R.run(base(yearly_spending=0), paths=FAST)):
        check(f"disclaimer present in state {st['state']}", R.DISCLAIMER in st["text"] and st["disclaimer"] == R.DISCLAIMER)
    check("private flags", r["private"] is True and r["read_aloud"] is False and r["remember"] is False)
    only = {k: v for k, v in base().items() if k in R.REQUIRED}
    r0 = R.run(only, paths=FAST)
    check("what I used marks the made-up numbers as assumed",
          {u["key"] for u in r0["used"] if u["assumed"]} == {"plan_to_age", "expected_return_percent",
                                                           "volatility_percent", "inflation_percent"},
          [u for u in r0["used"] if u["assumed"]])
    check("numbers the owner typed are not marked assumed", not any(u["assumed"] for u in r["used"]))
    r2 = R.run({k: v for k, v in base().items() if k not in ("plan_to_age", "expected_return_percent")}, paths=FAST)
    check("defaults fill in and are labelled",
          {u["key"] for u in r2["used"] if u["assumed"]} >= {"plan_to_age", "expected_return_percent"})
    check("the seed and the count are stated", any(u["key"] == "seed" for u in r["used"])
          and any(u["key"] == "paths" and u["value"] == "1,000" for u in r["used"]))
    check("no single exact money figure: every amount is 2 significant figures at most",
          all(R._round_sig(v) == v for v in (e["p10"], e["p50"], e["p90"])))
    check("the top-level words never say 'guarantee' except to deny it",
          all("guarantee" not in s or "not mean it is guaranteed" in s for s in r["summary"]))


# ============================================================ 3. behaviour that must hold

def t_reproducible_and_monotone():
    a = R.run(base(), paths=FAST)
    b = R.run(base(), paths=FAST)
    check("same inputs, byte-identical answer", json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True))
    shares = []
    for s in (0, 20000, 50000, 100000, 250000, 500000, 1_000_000):
        shares.append(R.run(base(savings=s), paths=FAST)["share"]["per_100"])
    check("more savings never lowers the share that lasts", shares == sorted(shares), shares)
    shares = [R.run(base(yearly_saving=s), paths=FAST)["share"]["per_100"] for s in (0, 5000, 12000, 30000)]
    check("more yearly saving never lowers it", shares == sorted(shares), shares)
    shares = [R.run(base(yearly_spending=s), paths=FAST)["share"]["per_100"] for s in (15000, 25000, 40000, 60000)]
    check("less spending never lowers it", shares == sorted(shares, reverse=True), shares)
    shares = [R.run(base(other_income=s, other_income_start_age=67), paths=FAST)["share"]["per_100"]
              for s in (0, 5000, 15000, 30000)]
    check("more pension never lowers it", shares == sorted(shares), shares)
    shares = [R.run(base(expected_return_percent=x), paths=FAST)["share"]["per_100"] for x in (2, 4, 6, 8, 10)]
    check("a higher return never lowers it", shares == sorted(shares), shares)
    shares = [R.run(base(retirement_age=x), paths=FAST)["share"]["per_100"] for x in (60, 65, 70, 75)]
    check("retiring later never lowers it", shares == sorted(shares), shares)
    a = R.run(base(), paths=1000)["share"]["per_100"]
    b = R.run(base(), paths=10_000)["share"]["per_100"]
    check("1,000 and 10,000 futures agree within a few points (the first are the same futures)",
          abs(a - b) <= 4, (a, b))
    golden = R.run(base(), paths=10_000)
    check("golden: the 40-year-old example on the fixed seed is in the expected range (60-80 of 100)",
          60 <= golden["share"]["per_100"] <= 80, golden["share"])
    check("golden: the count is what the answer says", golden["paths"] == 10_000)


def t_argmax_pitfall():
    check("first_true: never true is None (not 0)", R.first_true([False, False, False]) is None)
    check("first_true: first true index", R.first_true([False, True, True]) == 1)
    check("first_true: empty", R.first_true([]) is None)
    try:
        import numpy as np
        flags = np.array([[False, False], [False, True]])
        check("(numpy reproduces the pitfall: argmax says 0 for a never-true row)",
              int(np.argmax(flags, axis=1)[0]) == 0)
    except ImportError:
        print("skip  numpy not installed here: the argmax reproduction is skipped")
    src = (HERE / "jarvis_retirement.py").read_text(encoding="utf-8")
    import tokenize
    names = set()
    with open(HERE / "jarvis_retirement.py", "rb") as f:
        for tok in tokenize.tokenize(f.readline):
            if tok.type == tokenize.NAME:
                names.add(tok.string)
    check("the module does not use argmax or numpy", "argmax" not in names and "numpy" not in names
          and "np" not in names)
    r = R.run(base(savings=10_000_000, yearly_spending=10000), paths=FAST)
    check("a rich case is 'never runs out', not 'ran out in year one'",
          r["state"] == "never_runs_out" and r["runs_out_between"] is None
          and not any(str(x) in r["text"] for x in ("age 40 to", "at about age 40")))
    # a mix: some futures never run out and some do, the range holds only real run-out ages
    r = R.run(base(savings=40000, yearly_saving=8000), paths=FAST)
    check("a mixed case: run-out ages are all retirement-time ages, never the starting age",
          r["state"] == "mixed" and r["runs_out_between"][0] >= 65, r["runs_out_between"])


# ============================================================ 4. the bounds

def t_bounds():
    def code(raw):
        e = err(raw)
        return None if e is None else (e.code, e.field)
    check("valid input passes", err(base()) is None)
    check("string numbers work (money with commas, percent with %)",
          err(base(savings="1,250,000", expected_return_percent="6.5%", current_age="40")) is None)
    check("0 savings is fine", err(base(savings=0)) is None)
    check("the largest money is fine", err(base(savings=1_000_000_000)) is None)
    check("over the largest money is refused", code(base(savings=1_000_000_001)) == ("out_of_range", "savings"))
    check("huge is refused", code(base(savings=10 ** 30)) == ("out_of_range", "savings")
          or code(base(savings=10 ** 30)) == ("bad_number", "savings"))
    check("negative money is refused", code(base(savings=-1)) == ("negative", "savings"))
    check("negative spending is refused", code(base(yearly_spending=-5)) == ("negative", "yearly_spending"))
    check("negative money as text is refused", code(base(yearly_saving="-100")) == ("negative", "yearly_saving"))
    check("NaN is refused", code(base(savings=float("nan"))) == ("bad_number", "savings"))
    check("infinity is refused", code(base(savings=float("inf"))) == ("bad_number", "savings"))
    check("negative infinity is refused", code(base(savings=float("-inf"))) == ("bad_number", "savings"))
    check("the word NaN as text is refused", code(base(savings="NaN")) == ("bad_number", "savings"))
    check("text is refused", code(base(savings="lots")) == ("bad_number", "savings"))
    check("a true/false is not a number", code(base(savings=True)) == ("bad_number", "savings")
          and code(base(current_age=False)) == ("bad_number", "current_age"))
    check("a list is not a number", code(base(savings=[1])) == ("bad_number", "savings"))
    check("a dict is not a number", code(base(savings={"a": 1})) == ("bad_number", "savings"))
    check("a missing required field is asked for, never guessed", code({k: v for k, v in base().items()
          if k != "savings"}) == ("missing", "savings"))
    check("an empty string counts as missing", code(base(savings="  ")) == ("missing", "savings"))
    check("each required field is required", all(
        code({k: v for k, v in base().items() if k != key}) == ("missing", key) for key in R.REQUIRED))
    check("age 17 refused", code(base(current_age=17)) == ("out_of_range", "current_age"))
    check("age 101 refused", code(base(current_age=101)) == ("out_of_range", "current_age"))
    check("age with a fraction refused", code(base(current_age=40.5)) == ("bad_number", "current_age"))
    check("age 40.0 accepted", err(base(current_age=40.0)) is None)
    check("plan-to age 111 refused", code(base(plan_to_age=111)) == ("out_of_range", "plan_to_age"))
    check("plan-to age not after retirement refused", code(base(plan_to_age=65)) == ("plan_not_after", "plan_to_age")
          and code(base(plan_to_age=60)) == ("plan_not_after", "plan_to_age"))
    check("plan-to not after current age refused", code(base(current_age=80, retirement_age=70, plan_to_age=80))
          == ("plan_not_after", "plan_to_age"))
    check("more than 90 years refused", code(base(current_age=18, retirement_age=60, plan_to_age=109))
          == ("too_many_years", "plan_to_age"))
    check("exactly 90 years accepted", err(base(current_age=20, retirement_age=60, plan_to_age=110)) is None)
    check("return -6 refused, 16 refused", code(base(expected_return_percent=-6)) == ("out_of_range", "expected_return_percent")
          and code(base(expected_return_percent=16)) == ("out_of_range", "expected_return_percent"))
    check("return -5 and 15 accepted", err(base(expected_return_percent=-5)) is None
          and err(base(expected_return_percent=15)) is None)
    check("spread 41 refused, -1 refused", code(base(volatility_percent=41)) == ("out_of_range", "volatility_percent")
          and code(base(volatility_percent=-1)) == ("out_of_range", "volatility_percent"))
    check("inflation 16 refused", code(base(inflation_percent=16)) == ("out_of_range", "inflation_percent"))
    check("an unknown field is refused", code(base(favourite_colour="blue")) == ("unknown_field", "favourite_colour"))
    check("not a dict is refused", code(["x"]) == ("bad_request", ""))
    check("pension start age out of range refused", code(base(other_income=1, other_income_start_age=5))
          == ("out_of_range", "other_income_start_age"))
    check("a string percent that is a sum is refused", code(base(expected_return_percent="4+3")) == ("bad_number", "expected_return_percent"))
    check("a very long string is refused", code(base(savings="1" * 500)) == ("bad_number", "savings"))
    e = err(base(savings=1234567.89, current_age=200))
    check("the error message never repeats the numbers typed", e is not None and "200" not in e.message
          and "1234567" not in e.message)
    e = err(base(savings="a secret 4111 1111 1111 1111"))
    check("nor text typed", e is not None and "4111" not in e.message and "secret" not in e.message)
    # each error is a plain sentence
    check("every error is a plain sentence", all(
        isinstance(err(base(**{k: "x"})).message, str) and err(base(**{k: "x"})).message.endswith(".")
        for k in ("savings", "current_age", "expected_return_percent")))


# ============================================================ 5. speed and caps

def t_speed_and_caps():
    t = time.monotonic()
    R.run(base(current_age=18, retirement_age=60, plan_to_age=108), paths=10_000)
    took = time.monotonic() - t
    check("the biggest allowed run finishes well inside the time budget", took < R.TIME_BUDGET / 2, f"{took:.1f}s")
    check("the path count is capped: a bigger ask is treated as the default",
          R.run(base(), paths=10 ** 7)["paths"] == R.PATHS)
    check("a tiny ask is treated as the default too", R.run(base(), paths=3)["paths"] == R.PATHS)
    # A run that is over budget is stopped, not finished (a fake clock that jumps).
    ticks = iter([0.0] + [1e6] * 100)
    try:
        R.run(base(), paths=1000, clock=lambda: next(ticks), budget=1.0)
        stopped = False
    except TimeoutError:
        stopped = True
    check("a run over its time budget is stopped", stopped)
    code, out = R.handle_post(R.PATH_RUN, base(savings=-5))
    check("route: bad number is 400 with field and message", code == 400 and out["ok"] is False
          and out["field"] == "savings" and out["error"] == "negative", out)
    R._RUN_LOCK.acquire()
    try:
        code, out = R.handle_post(R.PATH_RUN, base())
    finally:
        R._RUN_LOCK.release()
    check("route: a second run at the same time is told to wait (429)", code == 429 and out["error"] == "busy")
    check("the length of the time budget is bounded", R.TIME_BUDGET <= 60 and R.PATHS <= 10_000)


# ============================================================ 6. the model's words

def t_sentence_verification():
    r = R.run(base(), paths=FAST)
    pct = r["share"]["per_100"]
    good = f"In {r['share']['label']} simulated futures your money lasts to age 95."
    check("a sentence whose numbers are all in the result is kept", R.verify_sentence(good, r))
    check("a made-up percentage is dropped", not R.verify_sentence(f"About {pct + 7} of 100 futures work out.", r))
    check("a made-up age is dropped", not R.verify_sentence("Your money lasts to age 101.", r))
    check("an invented amount is dropped", not R.verify_sentence("You would have 1,234,567 at the end.", r))
    check("the amount in the result is allowed", R.verify_sentence(
        f"The middle case leaves about {r['end_balance']['text']['p50']} at age 95.", r) or r["end_balance"]["p50"] == 0)
    check("a sentence with no numbers is allowed", R.verify_sentence("It looks fairly solid, but nothing is certain.", r))
    check("an empty or non-string sentence is dropped", not R.verify_sentence("", r) and not R.verify_sentence(None, r)
          and not R.verify_sentence(42, r))
    check("a two-line or very long sentence is dropped", not R.verify_sentence("a\nb", r)
          and not R.verify_sentence("x" * 500, r))
    check("nothing to verify against a not-enough-to-say result", not R.verify_sentence("Fine.", R.run(base(yearly_spending=0), paths=100)))
    check("a number hidden in a comma group is checked whole",
          not R.verify_sentence("You keep 310,001.", r))
    text = R.chat_words(r, good)
    check("chat: a verified sentence is shown with the disclaimer", text.startswith(good) and text.endswith(R.DISCLAIMER))
    text = R.chat_words(r, f"About {pct + 7} of 100 futures work.")
    check("chat: a dropped sentence is replaced by code's own headline and the plain note",
          r["summary"][0] in text and R.DROPPED_LINE in text and text.endswith(R.DISCLAIMER) and f"{pct + 7}" not in text, text)
    text = R.chat_words(r, None)
    check("chat: no model sentence gives code's headline and the disclaimer", r["summary"][0] in text and text.endswith(R.DISCLAIMER))
    check("chat: a spoken question gets only 'I have put it on your screen.'", R.chat_words(r, good, spoken=True) == R.SPOKEN_LINE
          and not any(ch.isdigit() for ch in R.SPOKEN_LINE))


# ============================================================ 7. the tool door

def t_tool_door():
    out = R.tool_call(base(), paths=FAST)
    check("tool: works on typed numbers", out["ok"] and out["result"]["kind"] == "retirement"
          and R.DISCLAIMER in out["text_for_model"])
    out = R.tool_call(base(), tainted=True, paths=FAST)
    check("tool: refused after outside text", not out["ok"] and out["error"] == "outside_text")
    out = R.tool_call({k: v for k, v in base().items() if k != "savings"}, paths=FAST)
    check("tool: a missing number is asked for", not out["ok"] and out["error"] == "missing" and out["field"] == "savings")
    sch = R.tool_schema()
    check("tool schema: every field, required ones listed, nothing extra allowed",
          set(sch["properties"]) == {f["key"] for f in R.FIELDS} and set(sch["required"]) == set(R.REQUIRED)
          and sch["additionalProperties"] is False)
    check("tool description is short", len(R.TOOL_DESCRIPTION) < 200)


# ============================================================ 8. no leaks

def t_no_leaks():
    marker = 7654321
    buf, err_buf = io.StringIO(), io.StringIO()
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    cwd = Path(tempfile.mkdtemp(prefix="jarvis-retire-"))
    old_cwd = os.getcwd()
    os.chdir(cwd)
    before = set(os.listdir(tempfile.gettempdir()))
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err_buf):
            R.handle_post(R.PATH_RUN, base(savings=marker))
            R.handle_post(R.PATH_RUN, base(savings=-marker))
            R.tool_call(base(savings=marker), paths=100)
            R.handle_get(R.PATH_DEFAULTS)
    finally:
        os.chdir(old_cwd)
        root.removeHandler(handler)
        root.setLevel(old_level)
    seen = buf.getvalue() + err_buf.getvalue() + log_stream.getvalue()
    check("nothing printed and nothing logged", seen == "", seen[:200])
    check("no file written in the working folder", os.listdir(cwd) == [])
    shutil.rmtree(cwd, ignore_errors=True)
    src = (HERE / "jarvis_retirement.py").read_text(encoding="utf-8")
    import tokenize
    calls = []
    with open(HERE / "jarvis_retirement.py", "rb") as f:
        toks = list(tokenize.tokenize(f.readline))
    for i, tok in enumerate(toks[:-1]):
        if tok.type == tokenize.NAME and toks[i + 1].string == "(" and tok.string in (
                "open", "print", "write_text", "write_bytes", "system", "Popen", "urlopen", "socket"):
            # the __main__ demo at the bottom is allowed one print
            if tok.string == "print" and tok.start[0] > src[:src.index('if __name__')].count("\n"):
                continue
            calls.append((tok.string, tok.start[0]))
    check("the module opens no file and no network and prints only in its demo", calls == [], calls)
    imports = {l.split()[1].split(".")[0] for l in src.splitlines() if l.startswith(("import ", "from "))}
    check("only standard-library imports and the shared money reader",
          imports <= {"__future__", "json", "math", "random", "re", "threading", "time", "array", "typing",
                      "urllib", "jarvis_money_parse"}, imports)
    r = R.run(base(savings=marker), paths=100)
    check("the answer is flagged screen-only, and only the random table is kept between runs",
          r["private"] and not r["read_aloud"] and not r["remember"]
          and set(R._Z) == {"rng", "table", "rows"})
    check("the random table holds no input", all(isinstance(x, float) for x in R._Z["table"][:50]))
    check("the answer carries no key that a store might pick up (no 'id', no path)",
          "id" not in r and "path" not in r)


# ============================================================ 9. the routes and the patch

class _H:
    def __init__(self, path, body=b"", ok=True):
        self.path, self.sent, self._body, self.ok = path, [], body, ok

    def _send(self, code, obj):
        self.sent.append((code, obj))


def t_routes_and_install():
    class Handler:
        def do_GET(self):
            self.sent.append(("orig-get", None))

        def do_POST(self):
            self.sent.append(("orig-post", None))
    line = R.install(Handler, origin_ok=lambda h: h.ok, token_ok=lambda h: h.ok,
                     read_body=lambda h: h._body)
    check("install returns a banner line", "retirement" in line.lower())
    check("install twice wraps once", "already on" in R.install(
        Handler, origin_ok=lambda h: True, token_ok=lambda h: True, read_body=lambda h: b"{}"))
    h = _H("/api/retirement/defaults")
    Handler.do_GET(h)
    code, out = h.sent[0]
    check("GET defaults: fields, limits, disclaimer, paths, seed", code == 200 and out["disclaimer"] == R.DISCLAIMER
          and out["paths"] == 10000 and out["seed"] == R.SEED and len(out["fields"]) == len(R.FIELDS)
          and all({"key", "label", "unit", "min", "max", "default", "required", "placeholder"} <= set(f)
                  for f in out["fields"]))
    h = _H("/api/retirement/run", json.dumps(base(current_age=60, retirement_age=65, plan_to_age=80, savings=100000,
                                                  yearly_saving=10000, expected_return_percent=0,
                                                  inflation_percent=0, volatility_percent=0)).encode())
    Handler.do_POST(h)
    code, out = h.sent[0]
    check("POST run: 200 with a result", code == 200 and out["ok"] and out["result"]["state"] == "always_runs_out"
          and out["result"]["paths"] == 10000, (code, str(out)[:200]))
    h = _H("/api/retirement/run", b"{not json")
    Handler.do_POST(h)
    check("POST run: bad JSON is 400", h.sent[0][0] == 400 and h.sent[0][1]["ok"] is False)
    h = _H("/api/retirement/run", b"[1]")
    Handler.do_POST(h)
    check("POST run: a list body is 400", h.sent[0][0] == 400 and h.sent[0][1]["error"] == "bad_request")
    h = _H("/api/other")
    Handler.do_GET(h)
    Handler.do_POST(h)
    check("other routes go to the original", [s[0] for s in h.sent] == ["orig-get", "orig-post"])
    h = _H("/api/retirement/run", b"{}", ok=False)
    Handler.do_POST(h)
    check("no token or bad origin is refused before anything is read", h.sent[0][0] in (401, 403))
    check("a different route under the prefix is 404", R.handle_post("/api/retirement/nope", {})[0] == 404
          and R.handle_get("/api/retirement/nope")[0] == 404)


def t_the_patch_and_the_lists():
    order = _stack.order()
    check("retirement.patch is in apply-patches.ps1's list, after spending.patch",
          "retirement.patch" in order and order.index("spending.patch") < order.index("retirement.patch"), order[-4:])
    patch = (HERE / "retirement.patch").read_text(encoding="utf-8")
    check("it patches jarvis_hud.py only",
          [l[6:].strip() for l in patch.splitlines() if l.startswith("+++ b/")] == ["jarvis_hud.py"])
    check("it needs no card and no gate line", "jarvis_gate" not in patch)
    git = shutil.which("git")
    at = order.index("retirement.patch")
    text, log = _stack.stand_in("jarvis_hud.py", order[:at])
    note = ""
    if text is None:
        bad = [l.split(":")[0] for l in log if "does not apply" in l]
        text, _l = _stack.stand_in("jarvis_hud.py", [p for p in order[:at] if p not in bad])
        note = f" (stack stand-in built without {bad})"
    check("git is here and the stand-in exists" + note, bool(git) and text is not None, log[-2:])
    if git and text:
        d = Path(tempfile.mkdtemp(prefix="jarvis-retirement-patch-"))
        try:
            marker_line = "    # Before the main socket, so the banner lists every address together.\n"
            for prev in order[max(0, at - 3):at]:
                # a neighbour that is not in the stand-in is added from its own text
                key = {"spending.patch": "jarvis_spending.install(Handler", "decks.patch": "jarvis_decks.install(Handler"}.get(prev)
                if key and key not in text:
                    adds = [l[1:] for l in (HERE / prev).read_text(encoding="utf-8").splitlines()
                            if l.startswith("+") and not l.startswith("+++")]
                    text = text.replace(marker_line, "\n".join(adds) + "\n" + marker_line, 1)
            (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
            (d / "p.patch").write_text(patch, encoding="utf-8", newline="\n")
            r = subprocess.run([git, "apply", "p.patch"], cwd=d, capture_output=True, text=True)
            after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
            r2 = subprocess.run([git, "apply", "-R", "p.patch"], cwd=d, capture_output=True, text=True)
            back = (d / "jarvis_hud.py").read_text(encoding="utf-8") == text
            check("applies to what the earlier patches wrote, and reverses",
                  r.returncode == 0 and r2.returncode == 0 and back, (r.stderr, r2.stderr))
            i = after.find("jarvis_retirement.install(Handler")
            k = after.find("_loopback_companion(bind, HUD_PORT, Handler)\n    print(")
            check("installed before anything listens, with the server's own checks",
                  -1 < i < k and "origin_ok=_origin_ok" in after[i:i + 200] and "token_ok=_token_ok" in after[i:i + 200])
        finally:
            shutil.rmtree(d, ignore_errors=True)
    import _where
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    shipped = ps1[ps1.index("$SHIPPED = @("):]
    check("jarvis_retirement.py is shipped: apply-patches.ps1 and _where.SHIPPED",
          "'jarvis_retirement.py'" in shipped and "jarvis_retirement.py" in _where.SHIPPED)
    reqs = (HERE / "requirements.txt").read_text(encoding="utf-8").lower()
    check("no monteplan, scipy or new package was added for this", not any(w in reqs for w in ("monteplan", "scipy")))


def t_words_are_plain():
    for name in ("TITLE", "DISCLAIMER", "PLACEHOLDER_NOTE", "TODAYS_MONEY", "DETAIL", "HIDDEN", "BUSY", "TOO_SLOW",
                 "OUTSIDE_TEXT", "NOT_ENOUGH_NO_SPENDING", "DROPPED_LINE", "SPOKEN_LINE"):
        check(f"{name} is a sentence", isinstance(getattr(R, name), str) and len(getattr(R, name)) > 3)
    check("the disclaimer is exactly the agreed sentence", R.DISCLAIMER == "This is a simplified what-if, not financial advice.")
    check("the detail says never read aloud, remembered or sent",
          all(w in R.DETAIL for w in ("never read aloud", "never remembered", "never sent")))
    check("no jargon in the owner's words", not any(w in (R.DETAIL + R.NOT_ENOUGH_NO_SPENDING + R.OUTSIDE_TEXT).lower()
                                                   for w in ("monte carlo", "lognormal", "seed", "json", "api")))
    check("every field has a label and help", all(f["label"] and f["help"] for f in R.FIELDS))


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
