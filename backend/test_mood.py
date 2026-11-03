"""test_mood.py - the owner's own mood log (the 2026-11-02 life-coach
decision D1; backend/jarvis_mood.py).

    python3 backend/test_mood.py

What it proves, on REAL SQLite files in a temporary folder and a stand-in
Handler (no server, no gate, no model, no network):

  - ONE row per day: the first entry adds it, a second entry the same day
    REPLACES it (upsert), and the store never holds two rows for one day;
  - the scale is exactly 1-5: 0, 6, 3.5, True and rubbish are refused in words;
  - the optional words are the owner's own, saved as typed, capped, and may be
    empty; a too-long word list is refused rather than silently cut;
  - the history is rows newest-first inside the window, with no average, no
    trend and no verdict computed anywhere;
  - count_days counts ROWS and never reads a value (the week in review's only
    window into this store);
  - no card can be raised (the gate is not imported at all), no model is
    called, no network client is imported;
  - the CRISIS path is untouched: this module holds no crisis phrase list and
    imports no wellbeing module, so the one real help path stays where it is;
  - the two routes answer exactly those shapes, 400 for a bad value, and leave
    an unrelated route to the original handler.

Every check fails on the code before this feature: jarvis_mood.py did not
exist.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_mood.py")

import jarvis_mood as M  # noqa: E402

PASSED, FAILED = [], []
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-mood-"))

#: A mood module must never say a verdict, an average or a judgement word.
BANNED = ("streak", "score", "average", "trend", "diagnos", "depress", "anxiety",
          "symptom", "well done", "great job", "you seem", "you are")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


_N = [0]


def fresh() -> str:
    """A new, empty mood.db for one test."""
    _N[0] += 1
    path = _TMP / f"mood-{_N[0]}.db"
    os.environ["JARVIS_MOOD_DB"] = str(path)
    M._reset_for_tests()
    return str(path)


def _handler_class():
    class Handler:
        def __init__(self, path="/api/mood", body=b"{}"):
            self.path = path
            self.body = body
            self.sent = None

        def do_GET(self):
            return "original-get"

        def do_POST(self):
            return "original-post"

        def _send(self, code, out):
            self.sent = (code, out)
            return self.sent

    return Handler


def _raises(exc_type, fn, *a, **kw) -> bool:
    try:
        fn(*a, **kw)
        return False
    except exc_type:
        return True


# --------------------------------------------------------------------------
#   One row per day, upsert
# --------------------------------------------------------------------------

def t_first_entry_adds_a_row_and_a_second_replaces_it():
    fresh()
    first = M.record(3, words="long day", day="2026-11-02")
    check("the first entry is saved", first["ok"] is True and first["replaced"] is False)
    check("... it says so in plain words", first["said"] == M.WORDS["saved"])
    check("... the value is the one tapped", first["entry"]["value"] == 3)
    check("... and the words are the owner's own", first["entry"]["words"] == "long day")
    second = M.record(4, words="better", day="2026-11-02")
    check("a second entry the same day REPLACES it", second["replaced"] is True)
    check("... and says so", second["said"] == M.WORDS["replaced"])
    check("... the store still holds ONE row for that day",
          len(M.history(30, day="2026-11-02")) == 1,
          str(M.history(30, day="2026-11-02")))
    got = M.get("2026-11-02")
    check("... the row is the newest value", got["value"] == 4 and got["words"] == "better",
          str(got))


def t_a_different_day_is_a_second_row():
    fresh()
    M.record(2, day="2026-11-01")
    M.record(5, day="2026-11-02")
    rows = M.history(30, day="2026-11-02")
    check("two days are two rows", len(rows) == 2, str(rows))
    check("... newest first, as a chart reads", [r["day"] for r in rows]
          == ["2026-11-02", "2026-11-01"], str([r["day"] for r in rows]))
    check("today's entry is the one asked for", M.get("2026-11-02")["value"] == 5)


def t_no_day_means_the_owners_own_wall_clock_day():
    fresh()
    out = M.record(3)
    check("no day means today, on the owner's own clock",
          out["entry"]["day"] == _dt.date.today().isoformat(), out["entry"]["day"])


# --------------------------------------------------------------------------
#   The scale: exactly 1-5
# --------------------------------------------------------------------------

def t_the_scale_is_exactly_one_to_five():
    fresh()
    for value in (0, 6, -1, 99):
        check(f"value {value} is refused", _raises(ValueError, M.record, value, day="2026-11-02"))
    for value in (3.5, True, None, "lots", [], {}):
        check(f"value {value!r} is refused", _raises(ValueError, M.record, value,
                                                     day="2026-11-02"))
    check("a JSON client's '4' is accepted as the number 4",
          M.record("4", day="2026-11-02")["entry"]["value"] == 4)
    for i, value in enumerate((1, 2, 3, 4, 5), start=1):
        check(f"value {value} is accepted on the scale",
              M.record(value, day=f"2026-11-0{i}") is not None)
    check("the refusal is one plain sentence, not a stack trace",
          M.WORDS["scale"] in str(_value_error(9)), str(_value_error(9)))


def _value_error(value):
    try:
        M.record(value, day="2026-11-02")
        return ""
    except ValueError as exc:
        return str(exc)


def t_bad_days_are_refused():
    fresh()
    for day in ("2026-13-01", "02-11-2026", "tomorrow", "2026-1-2"):
        check(f"day {day!r} is refused", _raises(ValueError, M.record, 3, day=day))
    check("a real date is accepted", M.record(3, day="2026-02-28")["ok"] is True)


# --------------------------------------------------------------------------
#   The optional words
# --------------------------------------------------------------------------

def t_the_words_are_optional_and_capped():
    fresh()
    check("an entry with no words is fine", M.record(3, day="2026-11-01")["ok"] is True)
    check("... and stores an empty string",
          M.get("2026-11-01")["words"] == "")
    M.record(4, words="  a   long \n day  ", day="2026-11-02")
    check("words are whitespace-collapsed, as every other field here is",
          M.get("2026-11-02")["words"] == "a long day", M.get("2026-11-02")["words"])
    check("words longer than MAX_WORDS are refused, never silently cut",
          _raises(ValueError, M.record, 3, words="x" * (M.MAX_WORDS + 1),
                  day="2026-11-02"))
    M.record(3, words="y" * M.MAX_WORDS, day="2026-11-03")
    check("... exactly MAX_WORDS is allowed",
          len(M.get("2026-11-03")["words"]) == M.MAX_WORDS)


# --------------------------------------------------------------------------
#   Reading: rows, never a verdict
# --------------------------------------------------------------------------

def t_history_is_rows_inside_the_window():
    fresh()
    M.record(1, day="2026-10-01")
    M.record(2, day="2026-10-31")
    M.record(3, day="2026-11-01")
    rows = M.history(7, day="2026-11-02")
    check("only rows inside the window come back",
          [r["day"] for r in rows] == ["2026-11-01", "2026-10-31"],
          str([r["day"] for r in rows]))
    check("the window is capped at MAX_DAYS, never unbounded",
          len(M.history(10_000, day="2026-11-02")) <= M.MAX_DAYS + 1)
    check("history holds no computed average or verdict key",
          all(set(r) == {"day", "value", "words", "created", "changed"} for r in rows),
          str(rows))
    check("latest() is the newest row, value and words only",
          M.latest()["day"] == "2026-11-01", str(M.latest()))


def t_count_days_counts_rows_and_reads_no_value():
    fresh()
    M.record(1, day="2026-10-31")
    M.record(5, day="2026-11-01")
    M.record(3, day="2026-11-02")
    check("count_days counts the days with a row",
          M.count_days("2026-10-30", "2026-11-02") == 3,
          str(M.count_days("2026-10-30", "2026-11-02")))
    check("... and only inside the two dates given",
          M.count_days("2026-11-01", "2026-11-02") == 2)
    src = (HERE / "jarvis_mood.py").read_text(encoding="utf-8")
    body = src[src.index("def count_days"):src.index("def clear")]
    sql = [line for line in body.splitlines() if "SELECT" in line]
    check("... with SQL that selects a COUNT and no column at all",
          sql and all("COUNT(*)" in line for line in sql)
          and not any("SELECT *" in line for line in sql), str(sql))


def t_clear_removes_one_day_only():
    fresh()
    M.record(3, day="2026-11-01")
    M.record(4, day="2026-11-02")
    out = M.clear("2026-11-02")
    check("clear removes that day", out["removed"] is True and M.get("2026-11-02") is None)
    check("... and leaves the day before it alone", M.get("2026-11-01")["value"] == 3)
    check("clearing a day with no entry says so, not an error",
          M.clear("2026-11-05")["removed"] is False)


# --------------------------------------------------------------------------
#   What the module promises about itself
# --------------------------------------------------------------------------

def _imports_and_attrs(path: Path):
    import ast
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods, attrs = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and not node.level:
                mods.add(node.module)
        elif isinstance(node, ast.Attribute):
            attrs.add(node.attr)
    return mods, attrs


def t_the_module_holds_no_card_no_model_and_no_network():
    mods, attrs = _imports_and_attrs(HERE / "jarvis_mood.py")
    top = {m.split(".")[0] for m in mods}
    check("jarvis_mood.py never imports the gate (so it cannot raise a card)",
          "jarvis_gate" not in top, str(sorted(mods)))
    check("... and never names a card in its code path",
          "card" not in "".join(sorted(attrs)).lower())
    for word in ("requests", "socket", "ssl", "ftplib", "http"):
        check(f"jarvis_mood.py imports no network client ({word})", word not in top,
              str(sorted(mods)))
    check("... and no urllib client (request/error) either",
          not any(m.startswith("urllib.") and m != "urllib.parse" for m in mods),
          str(sorted(mods)))
    for call in ("open_stream", "urlopen", "create_connection"):
        check(f"jarvis_mood.py never calls {call}", call not in attrs,
              str(sorted(attrs)))


def t_the_crisis_path_is_untouched():
    """This module must never grow its own help-line logic: the one crisis path
    is jarvis_wellbeing.py's, and a log that started answering crisis text would
    be a second, unreviewed one."""
    mods, attrs = _imports_and_attrs(HERE / "jarvis_mood.py")
    check("jarvis_mood.py imports no wellbeing module",
          "jarvis_wellbeing" not in {m.split(".")[0] for m in mods}, str(sorted(mods)))
    src = (HERE / "jarvis_mood.py").read_text(encoding="utf-8")
    for word in ("988", "911", "suicide", "self-harm", "hotline", "lifeline"):
        check(f"jarvis_mood.py holds no crisis word of its own ({word})",
              word not in src)
    check("... and no crisis()/crisis_in_turn() call",
          "crisis(" not in src and "crisis_in_turn" not in src)


def t_no_verdict_word_is_ever_stored_or_shown():
    fresh()
    blank = M.record(3, day="2026-11-02")
    shown = " ".join([str(blank.get("said") or ""), M.WORDS["saved"],
                      M.WORDS["replaced"], M.WORDS["scale"]]).lower()
    check("the module's own words hold no verdict or diagnosis word",
          not any(w in shown for w in BANNED), shown)
    check("a value is kept as a number, never turned into a word",
          isinstance(blank["entry"]["value"], int))


# --------------------------------------------------------------------------
#   The routes
# --------------------------------------------------------------------------

def t_the_routes_answer_the_shapes_both_apps_read():
    fresh()
    Handler = _handler_class()
    M.install(Handler, origin_ok=lambda h: True, token_ok=lambda h: True,
              read_body=lambda h: h.body)
    # The SAVE and the CLEAR below must name the SAME day: a body with no `day`
    # is stored for TODAY, so a clear pinned to one literal date removed nothing
    # on any other day (CI: `removed: False`, "No mood entry for that day.").
    # Naming today in both is what the round trip actually proves.
    day = _dt.date.today().isoformat()
    h = Handler(path="/api/mood", body=json.dumps({"value": 4, "words": "ok",
                                                   "day": day}).encode())
    code, out = h.do_POST()
    check("POST /api/mood saves the day", code == 200 and out["ok"] is True,
          str(out)[:200])
    check("... and answers with the recent history for the chart",
          len(out["history"]) == 1 and out["history"][0]["value"] == 4,
          str(out.get("history"))[:200])

    h = Handler(path="/api/mood")
    code, out = h.do_GET()
    check("GET /api/mood answers history, latest, limits and words",
          code == 200 and out["latest"]["value"] == 4
          and out["limits"]["min"] == 1 and out["limits"]["max"] == 5
          and out["words"] == M.WORDS, str(out)[:240])

    h = Handler(path="/api/mood", body=json.dumps({"value": 9}).encode())
    code, out = h.do_POST()
    check("a value off the scale is a plain 400", code == 400
          and out["error"] == M.WORDS["scale"], f"{code} {out}")

    h = Handler(path="/api/mood", body=json.dumps({"clear": True,
                                                   "day": day}).encode())
    code, out = h.do_POST()
    check("clear removes the day", code == 200 and out["removed"] is True, str(out)[:200])

    h = Handler(path="/api/mood", body=b"{not json")
    code, out = h.do_POST()
    check("a body that is not JSON is refused, never crashed on", code == 400
          and out["ok"] is False, f"{code} {out}")


def t_an_unrelated_route_and_a_wrong_origin_are_handled():
    fresh()
    Handler = _handler_class()
    M.install(Handler, origin_ok=lambda h: True, token_ok=lambda h: True,
              read_body=lambda h: h.body)
    check("an unrelated GET is left to the original handler",
          Handler(path="/api/chat").do_GET() == "original-get")
    check("an unrelated POST is left to the original handler",
          Handler(path="/api/chat").do_POST() == "original-post")

    seen = {}
    Spying = _handler_class()
    real_send = Spying._send

    def _send(self, code, out):
        seen["code"] = code
        return real_send(self, code, out)

    Spying._send = _send
    M.install(Spying, origin_ok=lambda h: True, token_ok=lambda h: False,
              read_body=lambda h: b"{}")
    code = Spying(path="/api/mood").do_GET()
    check("a bad token is refused with 401", seen.get("code") == 401, str(seen))
    check("... and the route answered nothing", code is None)


def t_the_plugin_folder_installs_it():
    row = json.loads((ROOT / "plugins/ready/mood/plugin.json").read_text(encoding="utf-8"))
    check("the plugin folder that installs it exists and names this module",
          row["module"] == "jarvis_mood" and row["install"] == "handler", str(row))
    check("it replaces no patch (it was born a folder)",
          "replaces_patch" not in row, str(row))


def main():
    tests = [t_first_entry_adds_a_row_and_a_second_replaces_it,
             t_a_different_day_is_a_second_row,
             t_no_day_means_the_owners_own_wall_clock_day,
             t_the_scale_is_exactly_one_to_five,
             t_bad_days_are_refused,
             t_the_words_are_optional_and_capped,
             t_history_is_rows_inside_the_window,
             t_count_days_counts_rows_and_reads_no_value,
             t_clear_removes_one_day_only,
             t_the_module_holds_no_card_no_model_and_no_network,
             t_the_crisis_path_is_untouched,
             t_no_verdict_word_is_ever_stored_or_shown,
             t_the_routes_answer_the_shapes_both_apps_read,
             t_an_unrelated_route_and_a_wrong_origin_are_handled,
             t_the_plugin_folder_installs_it]
    for fn in tests:
        print("\n-- " + fn.__name__ + " " + "-" * 40)
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            check(fn.__name__ + " ran", False, traceback.format_exc()[-900:])
    print("\n" + "=" * 74)
    print(f"PASS {len(PASSED)}  FAIL {len(FAILED)}  SKIP 0")
    for name in FAILED:
        print("  FAIL:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
