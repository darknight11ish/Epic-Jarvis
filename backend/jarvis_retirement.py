"""jarvis_retirement.py - the retirement what-if calculator (JARVIS-API section 103).

NEW MODULE, shipped whole. Plain Python, standard library only (no numpy, no
scipy: numpy is on the requirements list but the backend STARTS without it, and
this feature should not depend on it). Nothing here reads a file, opens a
network connection, writes anything to disk or prints.

WHAT IT IS
  The owner types a few numbers of their own; the code plays out 10,000
  made-up futures with the same fixed random seed, and answers only as
  RANGES: "in about 78 of 100 simulated futures the money lasts to age 95".
  Never one exact number, and every answer carries the sentence
  "This is a simplified what-if, not financial advice." - added HERE, by code,
  not left to the model (docs/FINANCE-DESIGN.md part B).

THE MODEL (all in today's money, so inflation is already taken out)
  * Yearly steps from the current age to the plan-to age. At the start of each
    year of age `a`: before the retirement age the yearly saving is added; from
    the retirement age the year's spending, less any other income that has
    started, is taken out. If the money left cannot cover it the money has RUN
    OUT AT AGE a (the age at which it was needed and was not there). Then the
    year's return is applied.
  * Other income (a pension, a benefit) only counts from the retirement age on,
    and only up to the spending: a surplus is not saved (said in the answer).
  * The real return is (1 + nominal) / (1 + inflation) - 1. A year's growth is
    log-normal with that arithmetic mean and the typed spread, so one bad year
    can never take a balance below zero by itself.
  * The random numbers are fixed per path and per year, whatever the inputs are
    (the same 90 draws per path, always): the same inputs give the same answer,
    and "more savings" can never lower the share that lasts, because every
    input is judged on the very same futures.
  * The "1 point lower / higher" answers use the same futures with the yearly
    return moved by one point.

THE PITFALL THIS FILE MUST NOT REPEAT
  `numpy.argmax` on a row of "ran out" flags returns 0 when the flag is never
  true - which reads as "ran out in the first year" for a future that never
  ran out (reproduced 2026-09-30). Nothing here uses argmax: a future that never
  runs out is `None`, tested first, by `first_true()` and by the loop's own
  sentinel. `test_retirement.py` keeps the regression.

WHAT THE MODEL MAY DO
  Only words. The numbers come from `run()`; a sentence the model writes is
  kept only if every number in it is in the result (`verify_sentence`).

PRIVACY (money, screen only)
  The answer is `private`, not read aloud, not remembered, not sent to a search
  or a chatbot, and not stored here (nothing is cached but the inputs-free table
  of random numbers). Errors never repeat the numbers typed.
"""
from __future__ import annotations

import json
import math
import random
import re
import threading
import time
from array import array
from typing import Optional
from urllib.parse import urlsplit

try:  # the money reader is shared with the spending summaries
    import jarvis_money_parse as _mp
except Exception:  # pragma: no cover - the numbers can still be typed as numbers
    _mp = None

TITLE = "Retirement what-if"
DISCLAIMER = "This is a simplified what-if, not financial advice."
PLACEHOLDER_NOTE = ("The return figures are placeholders you can change, not a forecast. "
                    "Real life will differ.")
TODAYS_MONEY = "All amounts are in today's money, so inflation is already taken out."
DETAIL = ("Type your own numbers and Jarvis plays out 10,000 made-up futures. The answer is "
          "a range, never one exact figure. It stays on screen only: never read aloud, never "
          "remembered, never sent to a web search or a chatbot, and not saved.")
HIDDEN = "Retirement what-if hidden"
BUSY = "Another what-if is still being worked out. Try again in a moment."
TOO_SLOW = "That took too long to work out, so it was stopped. Try again."
OUTSIDE_TEXT = ("I will not run a what-if in a turn that has read an email, a web page or a "
                "file. Type the numbers yourself in a new message, or use the form.")
NOT_ENOUGH_NO_SPENDING = ("There is nothing to test: with no spending in retirement the money "
                          "cannot run out. Type what you expect to spend each year.")
NOT_ENOUGH_NO_SPENDING_REASON = "no_spending"
DROPPED_LINE = ("(Jarvis's own summary sentence used a figure that is not in the answer, so it "
                "was left out.)")
SPOKEN_LINE = "I have put it on your screen."

PATH_RUN = "/api/retirement/run"
PATH_DEFAULTS = "/api/retirement/defaults"

SEED = 20260930
PATHS = 10_000            # futures per answer; the most and the default
MIN_PATHS = 100           # only for tests: the route always uses PATHS
MAX_YEARS = 90            # most years simulated (plan-to age minus current age)
TIME_BUDGET = 30.0        # seconds; a run over this is stopped, not finished
BAND_POINTS = 1.0         # "1 point lower / higher" yearly return
_EPS = 1e-9

MIN_AGE, MAX_AGE, MAX_PLAN_AGE = 18, 100, 110
MAX_MONEY = 1_000_000_000
MIN_RETURN, MAX_RETURN = -5.0, 15.0
MIN_SPREAD, MAX_SPREAD = 0.0, 40.0
MIN_INFLATION, MAX_INFLATION = 0.0, 15.0

# The fields, in the order a form shows them. `default` None = the owner must
# type it. `placeholder` = a made-up value the answer marks "assumed".
FIELDS = (
    {"key": "current_age", "label": "Your age now", "unit": "years", "kind": "age",
     "min": MIN_AGE, "max": MAX_AGE, "default": None, "placeholder": False,
     "help": "A whole number."},
    {"key": "retirement_age", "label": "Age you stop working", "unit": "years", "kind": "age",
     "min": MIN_AGE, "max": MAX_AGE, "default": None, "placeholder": False,
     "help": "A whole number. If you already have, type your age now."},
    {"key": "plan_to_age", "label": "Plan the money to age", "unit": "years", "kind": "age",
     "min": MIN_AGE, "max": MAX_PLAN_AGE, "default": 95, "placeholder": True,
     "help": "How long the money should last. Must be after the age you stop working."},
    {"key": "savings", "label": "Savings you have now", "unit": "money", "kind": "money",
     "min": 0, "max": MAX_MONEY, "default": None, "placeholder": False,
     "help": "In today's money. Type 0 if none."},
    {"key": "yearly_saving", "label": "You add each year until you stop working",
     "unit": "money per year", "kind": "money", "min": 0, "max": MAX_MONEY,
     "default": None, "placeholder": False, "help": "In today's money. Type 0 if none."},
    {"key": "yearly_spending", "label": "You spend each year in retirement",
     "unit": "money per year", "kind": "money", "min": 0, "max": MAX_MONEY,
     "default": None, "placeholder": False, "help": "In today's money."},
    {"key": "other_income", "label": "Pension or other income each year (optional)",
     "unit": "money per year", "kind": "money", "min": 0, "max": MAX_MONEY,
     "default": 0, "placeholder": False,
     "help": "In today's money. It only ever covers spending; extra is not saved."},
    {"key": "other_income_start_age", "label": "That income starts at age (optional)",
     "unit": "years", "kind": "age", "min": MIN_AGE, "max": MAX_PLAN_AGE,
     "default": None, "placeholder": False,
     "help": "Leave empty to start when you stop working."},
    {"key": "expected_return_percent", "label": "Expected yearly return before inflation",
     "unit": "percent", "kind": "percent", "min": MIN_RETURN, "max": MAX_RETURN,
     "default": 7.0, "placeholder": True, "help": "A placeholder, not advice. Change it."},
    {"key": "volatility_percent", "label": "How much yearly returns swing",
     "unit": "percent", "kind": "percent", "min": MIN_SPREAD, "max": MAX_SPREAD,
     "default": 12.0, "placeholder": True, "help": "A placeholder, not advice. Change it."},
    {"key": "inflation_percent", "label": "Expected yearly inflation",
     "unit": "percent", "kind": "percent", "min": MIN_INFLATION, "max": MAX_INFLATION,
     "default": 2.5, "placeholder": True, "help": "A placeholder, not advice. Change it."},
)
_BY_KEY = {f["key"]: f for f in FIELDS}
REQUIRED = tuple(f["key"] for f in FIELDS if f["default"] is None and f["key"] != "other_income_start_age")

_TOOL_KEYS = tuple(f["key"] for f in FIELDS)


class InputError(ValueError):
    """A typed number that cannot be used. `.code`, `.field` and the plain
    `.message` are all the owner sees; the value typed is never in them."""

    def __init__(self, code: str, field: str, message: str):
        super().__init__(message)
        self.code, self.field, self.message = code, field, message


def _bad(code, key, message):
    return InputError(code, key, message)


def _range_words(f) -> str:
    kind = f["kind"]
    if kind == "age":
        return f"a whole number from {f['min']} to {f['max']}"
    if kind == "money":
        return f"an amount from 0 to {f['max']:,}"
    return f"a number from {f['min']:g} to {f['max']:g}"


# ------------------------------------------------------------------ reading the typed numbers

_PERCENT_RE = re.compile(r"^[+-]?\d{1,4}(?:\.\d{1,6})?$")
_INT_RE = re.compile(r"^\d{1,4}$")


def _finite_number(value):
    """A bool is not a number here. Returns a float or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if abs(value) > 10 ** 15:
            return math.inf
        return float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return None


def parse_age(key: str, value) -> int:
    f = _BY_KEY[key]
    msg = f"{f['label']} must be {_range_words(f)}."
    if isinstance(value, str):
        text = value.strip()
        if not _INT_RE.match(text):
            raise _bad("bad_number", key, msg)
        n = int(text)
    else:
        x = _finite_number(value)
        if x is None or not math.isfinite(x) or x != int(x):
            raise _bad("bad_number", key, msg)
        n = int(x)
    if n < f["min"] or n > f["max"]:
        raise _bad("out_of_range", key, msg)
    return n


def parse_money(key: str, value) -> float:
    """Whole currency units as a float (the simulation is a model, not a ledger)."""
    f = _BY_KEY[key]
    msg = f"{f['label']} must be {_range_words(f)}."
    if isinstance(value, str):
        text = value.strip()
        if not text or len(text) > 40:
            raise _bad("bad_number", key, msg)
        cents = _mp.parse_money(text, ".") if _mp is not None else None
        if cents is None and _mp is None and re.match(r"^\d{1,12}(?:\.\d{1,2})?$", text):
            cents = int(round(float(text) * 100))
        if cents is None:
            raise _bad("bad_number", key, msg)
        x = cents / 100.0
    else:
        x = _finite_number(value)
        if x is None or not math.isfinite(x):
            raise _bad("bad_number", key, msg)
    if x < 0:
        raise _bad("negative", key, f"{f['label']} cannot be negative.")
    if x > f["max"]:
        raise _bad("out_of_range", key, msg)
    return round(x, 2)


def parse_percent(key: str, value) -> float:
    f = _BY_KEY[key]
    msg = f"{f['label']} must be {_range_words(f)}."
    if isinstance(value, str):
        text = value.strip().rstrip("%").strip()
        if not _PERCENT_RE.match(text):
            raise _bad("bad_number", key, msg)
        x = float(text)
    else:
        x = _finite_number(value)
        if x is None or not math.isfinite(x):
            raise _bad("bad_number", key, msg)
    if x < f["min"] or x > f["max"]:
        raise _bad("out_of_range", key, msg)
    return float(x)


_PARSERS = {"age": parse_age, "money": parse_money, "percent": parse_percent}


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def validate(raw) -> dict:
    """The typed fields, checked and bounded. Raises InputError (never with the
    number typed in its words). Returns clean numbers plus which ones were
    assumed (a made-up default), in `assumed`."""
    if not isinstance(raw, dict):
        raise _bad("bad_request", "", "Send the numbers as a set of named fields.")
    unknown = [k for k in raw if k not in _BY_KEY]
    if unknown:
        raise _bad("unknown_field", str(unknown[0])[:40], "That is not one of the what-if's fields.")
    out, assumed = {}, []
    for f in FIELDS:
        key = f["key"]
        value = raw.get(key)
        if _blank(value):
            if key == "other_income_start_age":
                continue
            if f["default"] is None:
                raise _bad("missing", key, f"I need {f['label'].lower()}. Type it in; I will not guess it.")
            out[key] = f["default"]
            if f["placeholder"]:
                assumed.append(key)
            continue
        out[key] = _PARSERS[f["kind"]](key, value)
    cur, ret, plan = out["current_age"], out["retirement_age"], out["plan_to_age"]
    if plan <= max(ret, cur):
        raise _bad("plan_not_after", "plan_to_age",
                   "The age to plan the money to must be after the age you stop working "
                   "(and after your age now).")
    if plan - cur > MAX_YEARS:
        raise _bad("too_many_years", "plan_to_age",
                   f"That is more than {MAX_YEARS} years from your age now. Pick a nearer age.")
    if "other_income_start_age" not in out:
        out["other_income_start_age"] = max(ret, cur)
    return {"values": out, "assumed": assumed}


# ------------------------------------------------------------------ the random numbers

_Z_LOCK = threading.Lock()
_Z = {"rng": None, "table": array("d"), "rows": 0}


def _z_rows(rows: int) -> array:
    """Standard normal draws, MAX_YEARS per path, from ONE fixed stream, so path
    i always gets the same numbers whatever the inputs (or how many paths are
    asked for). Only random numbers are kept - nothing about the owner."""
    with _Z_LOCK:
        if _Z["rng"] is None:
            _Z["rng"] = random.Random(SEED)
        rng, table = _Z["rng"], _Z["table"]
        while _Z["rows"] < rows:
            table.extend(rng.gauss(0.0, 1.0) for _ in range(MAX_YEARS))
            _Z["rows"] += 1
        return table


def first_true(flags) -> Optional[int]:
    """The index of the first true flag, or None when none is. (numpy's argmax
    would say 0 for "never": do not use it for this.)"""
    for i, flag in enumerate(flags):
        if flag:
            return i
    return None


def _nearest_rank(sorted_values: list, q: float):
    if not sorted_values:
        return None
    k = max(0, min(len(sorted_values) - 1, int(math.ceil(q * len(sorted_values))) - 1))
    return sorted_values[k]


def _round_sig(x: float, digits: int = 2) -> int:
    """A money figure shown to 2 significant figures (a range, not a price)."""
    if x <= 0:
        return 0
    n = int(x)
    if n < 100:
        return n
    step = 10 ** (len(str(n)) - digits)
    return int(round(x / step)) * step


def _money_text(n: int) -> str:
    return f"{n:,}"


# ------------------------------------------------------------------ the simulation

def _scenario_stats(v: dict, shift_points: float, paths: int, deadline: float, clock):
    cur, ret, plan = v["current_age"], v["retirement_age"], v["plan_to_age"]
    years = plan - cur
    dep, need = [], []
    for k in range(years):
        a = cur + k
        if a < ret:
            dep.append(v["yearly_saving"])
            need.append(0.0)
        else:
            inc = v["other_income"] if a >= v["other_income_start_age"] else 0.0
            dep.append(0.0)
            need.append(max(0.0, v["yearly_spending"] - inc))
    nominal = v["expected_return_percent"] / 100.0
    infl = v["inflation_percent"] / 100.0
    spread = v["volatility_percent"] / 100.0
    real0 = (1.0 + nominal) / (1.0 + infl) - 1.0
    sig = math.sqrt(math.log(1.0 + (spread / (1.0 + real0)) ** 2)) if spread > 0 else 0.0
    mu = []
    for s in shift_points:
        real = (1.0 + nominal + s / 100.0) / (1.0 + infl) - 1.0
        real = max(real, -0.99)
        mu.append(math.exp(math.log(1.0 + real) - sig * sig / 2.0))   # exp(mu_log)
    table = _z_rows(paths)
    exp = math.exp
    res = [{"ok": 0, "ended": [], "lasted": [], "failed_at": []} for _ in shift_points]
    savings = v["savings"]
    for i in range(paths):
        if (i & 255) == 0 and clock() > deadline:
            raise TimeoutError("too slow")
        base = i * MAX_YEARS
        if sig > 0:
            ez = [exp(sig * table[base + k]) for k in range(years)]
        else:
            ez = None
        for si, gm in enumerate(mu):
            bal = savings
            failed = None
            for k in range(years):
                bal += dep[k]
                n = need[k]
                if n > 0.0:
                    if bal < n - _EPS:
                        failed = k
                        break
                    bal -= n
                bal *= gm * (ez[k] if ez is not None else 1.0)
            r = res[si]
            if failed is None:
                r["ok"] += 1
                r["ended"].append(bal)
                r["lasted"].append(plan)
            else:
                r["ended"].append(0.0)
                r["lasted"].append(cur + failed)
                r["failed_at"].append(cur + failed)
    return res


def _share(ok: int, n: int) -> dict:
    pct = int(round(100.0 * ok / n))
    if ok == n:
        return {"per_100": 99, "label": "more than 99 of 100", "all": True, "none": False}
    if ok == 0:
        return {"per_100": 0, "label": "fewer than 1 of 100", "all": False, "none": True}
    pct = max(1, min(99, pct))
    return {"per_100": pct, "label": f"about {pct} of 100", "all": False, "none": False}


def _used_list(v: dict, assumed: list, paths: int) -> list:
    rows = []

    def add(key, text):
        rows.append({"key": key, "label": _BY_KEY[key]["label"], "value": text,
                     "assumed": key in assumed})
    add("current_age", str(v["current_age"]))
    add("retirement_age", str(v["retirement_age"]))
    add("plan_to_age", str(v["plan_to_age"]))
    add("savings", _money_text(int(round(v["savings"]))))
    add("yearly_saving", _money_text(int(round(v["yearly_saving"]))))
    add("yearly_spending", _money_text(int(round(v["yearly_spending"]))))
    if v["other_income"] > 0:
        add("other_income", _money_text(int(round(v["other_income"]))))
        add("other_income_start_age", str(v["other_income_start_age"]))
    add("expected_return_percent", f"{v['expected_return_percent']:g}%")
    add("volatility_percent", f"{v['volatility_percent']:g}%")
    add("inflation_percent", f"{v['inflation_percent']:g}%")
    rows.append({"key": "paths", "label": "Simulated futures", "value": f"{paths:,}", "assumed": False})
    rows.append({"key": "seed", "label": "Random seed (the same every time)", "value": str(SEED),
                 "assumed": False})
    return rows


def run(raw: dict, *, paths: int = PATHS, clock=time.monotonic, budget: float = TIME_BUDGET) -> dict:
    """Validate and play out the futures. Returns the result block (see the
    frozen contract in docs/FINANCE-DESIGN.md). Raises InputError for a bad
    number, TimeoutError when the run is stopped for time."""
    if not isinstance(paths, int) or isinstance(paths, bool) or paths < MIN_PATHS or paths > PATHS:
        paths = PATHS
    clean = validate(raw)
    v, assumed = clean["values"], clean["assumed"]
    plan = v["plan_to_age"]
    base = {"ok": True, "kind": "retirement", "version": 1, "title": TITLE,
            "paths": paths, "seed": SEED,
            "used": _used_list(v, assumed, paths),
            "todays_money": TODAYS_MONEY,
            "placeholder_note": PLACEHOLDER_NOTE,
            "disclaimer": DISCLAIMER,
            "private": True, "read_aloud": False, "remember": False,
            "words": {"hidden": HIDDEN}}
    if v["yearly_spending"] <= 0:
        base.update({"state": "not_enough_to_say", "reason": NOT_ENOUGH_NO_SPENDING_REASON,
                     "share": None, "bands": None, "end_balance": None, "poor_case": None,
                     "runs_out_between": None,
                     "summary": [NOT_ENOUGH_NO_SPENDING]})
        base["text"] = _join_text(base["summary"])
        return base
    deadline = clock() + budget
    lo, hi = -BAND_POINTS, BAND_POINTS
    stats = _scenario_stats(v, (0.0, lo, hi), paths, deadline, clock)
    mid = stats[0]
    n = paths
    share = _share(mid["ok"], n)
    bands = {"lower": dict(_share(stats[1]["ok"], n), points=lo),
             "higher": dict(_share(stats[2]["ok"], n), points=hi)}
    ended = sorted(mid["ended"])
    lasted = sorted(mid["lasted"])
    end_bal = {k: _round_sig(_nearest_rank(ended, q)) for k, q in (("p10", 0.10), ("p50", 0.50), ("p90", 0.90))}
    end_bal["age"] = plan
    end_bal["text"] = {k: _money_text(end_bal[k]) for k in ("p10", "p50", "p90")}
    poor_age = _nearest_rank(lasted, 0.10)
    poor = {"lasts": poor_age >= plan, "age": None if poor_age >= plan else poor_age}
    failed = sorted(mid["failed_at"])
    between = None
    if failed:
        a, b = _nearest_rank(failed, 0.25), _nearest_rank(failed, 0.75)
        between = [a, b]
    median_age = _nearest_rank(lasted, 0.50)
    state = "never_runs_out" if share["all"] else ("always_runs_out" if share["none"] else "mixed")
    base.update({"state": state, "reason": None, "share": share, "bands": bands,
                 "end_balance": end_bal, "poor_case": poor, "runs_out_between": between,
                 "middle_lasts_to": median_age})
    base["summary"] = _summary(base, plan)
    base["text"] = _join_text(base["summary"])
    return base


def _join_text(lines: list) -> str:
    return " ".join(list(lines) + [DISCLAIMER])


def _age_range(between) -> str:
    a, b = between
    return f"about age {a}" if a == b else f"about age {a} to {b}"


def _summary(r: dict, plan: int) -> list:
    n = r["paths"]
    state, share = r["state"], r["share"]
    out = []
    if state == "never_runs_out":
        out.append(f"In all {n:,} simulated futures your money lasts to age {plan}. "
                   "That does not mean it is guaranteed.")
    elif state == "always_runs_out":
        out.append(f"In none of the {n:,} simulated futures does your money last to age {plan}; "
                   f"it runs out at {_age_range(r['runs_out_between'])}.")
    else:
        out.append(f"In {share['label']} simulated futures your money lasts to age {plan}. "
                   f"Where it runs out, that is usually at {_age_range(r['runs_out_between'])}.")
    lo, hi = r["bands"]["lower"], r["bands"]["higher"]
    out.append(f"If yearly returns are 1 point lower, that becomes {lo['label']}; "
               f"1 point higher, {hi['label']}.")
    e = r["end_balance"]
    if r["poor_case"]["lasts"]:
        out.append(f"Even in a poor case (1 in 10) it lasts, leaving about {e['text']['p10']} at age {plan}.")
    else:
        out.append(f"In a poor case (1 in 10) the money runs out at about age {r['poor_case']['age']}.")
    if e["p50"] > 0:
        out.append(f"The middle case leaves about {e['text']['p50']} at age {plan}; "
                   f"a good case (1 in 10) about {e['text']['p90']}.")
    else:
        out.append(f"In the middle case the money runs out at about age {r['middle_lasts_to']}.")
    if r["used"] and any(u["key"] == "other_income" for u in r["used"]):
        out.append("Other income only covers spending; any extra is not saved.")
    return out


# ------------------------------------------------------------------ the model's words

_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers_in(text: str) -> set:
    return {t.rstrip(",").replace(",", "") for t in _NUM_RE.findall(str(text))}


def allowed_numbers(result: dict) -> set:
    """Every number the answer itself shows: its own sentences, the inputs it
    used, the ages and the shares. A model sentence may use only these."""
    if not isinstance(result, dict):
        return set()
    bag = set()
    for line in result.get("summary") or []:
        bag |= _numbers_in(line)
    for u in result.get("used") or []:
        bag |= _numbers_in(u.get("value", ""))
    for key in ("share",):
        s = result.get(key)
        if s:
            bag.add(str(s.get("per_100")))
    for b in (result.get("bands") or {}).values():
        bag.add(str(b.get("per_100")))
        bag.add(str(int(abs(b.get("points", 0)))))
    e = result.get("end_balance")
    if e:
        for k in ("p10", "p50", "p90"):
            bag.add(str(e.get(k)))
    bag |= {"100", "10", "1", str(result.get("paths"))}
    return bag


def verify_sentence(sentence, result: dict, *, limit: int = 400) -> bool:
    """True only for one plain line whose every number is in the result."""
    if not isinstance(sentence, str):
        return False
    text = sentence.strip()
    if not text or len(text) > limit or "\n" in text or "\r" in text:
        return False
    if result is None or result.get("state") == "not_enough_to_say":
        return False
    allowed = allowed_numbers(result)
    return all(tok in allowed for tok in _numbers_in(text))


def chat_words(result: dict, model_sentence=None, *, spoken: bool = False) -> str:
    """What the chat shows: the model's sentence when code has verified it, else
    the answer's first sentence, plus the disclaimer - always. A spoken question
    gets only 'I have put it on your screen.' (nothing about money is read aloud)."""
    if spoken:
        return SPOKEN_LINE
    if verify_sentence(model_sentence, result):
        head = model_sentence.strip()
    else:
        head = result["summary"][0]
        if model_sentence not in (None, ""):
            head = head + " " + DROPPED_LINE
    if DISCLAIMER not in head:
        head = head + " " + DISCLAIMER
    return head


# ------------------------------------------------------------------ the chat door (tool)

TOOL_NAME = "retirement_whatif"
TOOL_DESCRIPTION = ("Play out a simplified retirement what-if from numbers the owner typed. "
                    "Ask for any missing one; never guess it.")


def tool_schema() -> dict:
    props = {}
    for f in FIELDS:
        props[f["key"]] = {"type": ["number", "string"], "description": f["label"] + " (" + f["unit"] + ")"}
    return {"type": "object", "properties": props, "required": list(REQUIRED),
            "additionalProperties": False}


def tool_call(args: dict, *, tainted: bool = False, paths: int = PATHS) -> dict:
    """The model-callable door, kept out of jarvis_agent.py until the spending
    builder's edits settle (docs/JARVIS-API.md section 103.6). Refused after
    outside text. Returns {ok, result} or {ok: False, error, field, message};
    the model gets `text_for_model` (the answer's own sentences), never a
    number to change."""
    if tainted:
        return {"ok": False, "error": "outside_text", "field": "", "message": OUTSIDE_TEXT}
    try:
        res = run(args, paths=paths)
    except InputError as e:
        return {"ok": False, "error": e.code, "field": e.field, "message": e.message}
    except TimeoutError:
        return {"ok": False, "error": "too_slow", "field": "", "message": TOO_SLOW}
    return {"ok": True, "result": res, "text_for_model": res["text"]}


# ------------------------------------------------------------------ the routes

def defaults() -> dict:
    """GET /api/retirement/defaults: the form, its limits, its placeholders."""
    fields = []
    for f in FIELDS:
        g = dict(f)
        g["required"] = f["key"] in REQUIRED
        fields.append(g)
    return {"ok": True, "available": True, "title": TITLE, "detail": DETAIL, "fields": fields,
            "paths": PATHS, "seed": SEED, "max_years": MAX_YEARS,
            "disclaimer": DISCLAIMER, "placeholder_note": PLACEHOLDER_NOTE,
            "todays_money": TODAYS_MONEY, "band_points": BAND_POINTS,
            "words": {"hidden": HIDDEN, "busy": BUSY, "too_slow": TOO_SLOW},
            "private": True, "read_aloud": False, "remember": False}


_RUN_LOCK = threading.Lock()


def handle_get(route: str):
    if route == PATH_DEFAULTS:
        return 200, defaults()
    return 404, {"ok": False, "error": "not_found"}


def handle_post(route: str, body):
    if route != PATH_RUN:
        return 404, {"ok": False, "error": "not_found"}
    if not _RUN_LOCK.acquire(blocking=False):
        return 429, {"ok": False, "error": "busy", "field": "", "message": BUSY}
    try:
        try:
            return 200, {"ok": True, "result": run(body)}
        except InputError as e:
            return 400, {"ok": False, "error": e.code, "field": e.field, "message": e.message}
        except TimeoutError:
            return 503, {"ok": False, "error": "too_slow", "field": "", "message": TOO_SLOW}
    finally:
        _RUN_LOCK.release()


_ROUTES_GET = (PATH_DEFAULTS,)
_ROUTES_POST = (PATH_RUN,)


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap do_GET and do_POST so the two retirement routes are answered here,
    after the server's own origin and token checks. Every other request goes
    straight to the original. Returns the banner line."""
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_retirement", False):
        return "  retirement Retirement what-if (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in _ROUTES_GET:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route)
        except Exception as exc:
            code, out = 503, {"ok": False, "available": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in _ROUTES_POST:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception:
            return self._send(400, {"ok": False, "error": "bad_request", "field": "",
                                    "message": "Send the numbers as a set of named fields."})
        try:
            code, out = handle_post(route, body)
        except Exception as exc:
            code, out = 503, {"ok": False, "available": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_retirement = True
    do_POST._jarvis_retirement = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return "  retirement Retirement what-if: on (POST /api/retirement/run)"


if __name__ == "__main__":
    t = time.monotonic()
    r = run({"current_age": 40, "retirement_age": 65, "savings": 100000, "yearly_saving": 12000,
             "yearly_spending": 30000})
    print(r["text"])
    print(f"({time.monotonic() - t:.1f}s)")
