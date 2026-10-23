"""test_pulse_sources.py - the Daily Pulse's four local read-only sources.

    python3 backend/test_pulse_sources.py

WHY THIS EXISTS (P3 seam B5-c, 2026-10-23). The briefing's Daily Pulse had a
money / study / PC-health half that was caller-supplied only: `Deps.pulse_sources`
was None in every production build, so the Pulse always called those sources
"not checked" and the "where to look" strip never carried a real one.
`jarvis_briefing.live_deps()` now supplies `jarvis_pulse_sources.pulse_sources()`,
which reads the four features' own local stores. This suite proves:

  1. the extras SHAPE is pinned (only money/study/pc lines, `anomalies`,
     `checked`; nothing else, nothing empty);
  2. one source contributes only its own facts (a fake per source), in a fixed
     deterministic order;
  3. empty stores add nothing at all (no line, no anomaly) while still being
     marked read - so nobody is told a source they have is "not checked";
  4. a source that RAISES or is SLOW is simply absent: the pulse always comes
     back, and the failed source is NOT marked checked (the briefing then says
     "not checked", never "0");
  5. App lock / hidden memory lists withhold the whole extras block, and a lock
     state that cannot be read counts as locked (fail closed);
  6. the no-leak rule: the real sources' words never carry a bank path/file
     name, a deck name, a finding's long paragraph, a route, an airline or an
     amount - checked with fake stores stuffed with those exact private strings;
  7. `pulse_from()` integration: the lines arrive with their labels, the
     anomalies reach the where-to-look strip, and `not_checked` is honest about
     a source that was read with nothing to say (the `checked` list);
  8. `live_deps()` really supplies the provider to the live entry points,
     while a plain `Deps()` (what tests use) stays empty.

Everything runs on fakes and a temporary config folder: no network, no owner
data, no approval card, nothing written.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_briefing.py", "jarvis_pulse_sources.py",
                "jarvis_spending.py", "jarvis_decks.py",
                "jarvis_price_radar.py", "jarvis_pc_help.py")

TMP = Path(tempfile.mkdtemp(prefix="jarvis-pulse-sources-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(TMP / "config")
os.environ["JARVIS_LOG_DIR"] = str(TMP / "logs")
(TMP / "config").mkdir(parents=True, exist_ok=True)

import jarvis_briefing as B  # noqa: E402
import jarvis_pulse_sources as P  # noqa: E402
import jarvis_schedule as S  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _fake(name, fn):
    """Put a stand-in module in sys.modules for one call; return a context-
    manager-ish (saved, restore) pair. `fn` is the module's attributes dict."""
    mod = types.ModuleType(name)
    for key, value in fn.items():
        setattr(mod, key, value)
    return name, mod


class _Swap:
    def __init__(self, *pairs):
        self.pairs = pairs
        self.saved = []

    def __enter__(self):
        for name, mod in self.pairs:
            self.saved.append((name, sys.modules.get(name)))
            sys.modules[name] = mod
        return self

    def __exit__(self, *exc):
        for name, old in reversed(self.saved):
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
        return False


# --------------------------------------------------------------------------
#   1. The shape
# --------------------------------------------------------------------------

def t_the_extras_shape_is_pinned():
    empty = P.pulse_sources(sources={"money": lambda: {}, "study": lambda: {},
                                     "pc": lambda: {}, "prices": lambda: {}},
                            locked=False)
    check("the extras hold only the two known containers (plus per-source lines)",
          set(empty) <= {"money", "study", "pc", "anomalies", "checked"}, empty)
    check("... anomalies is a list of non-empty strings",
          isinstance(empty.get("anomalies"), list)
          and all(isinstance(x, str) and x.strip() for x in empty["anomalies"]), empty)
    check("... checked lists only the three labelled sources",
          empty.get("checked") == ["money", "study", "pc"], empty.get("checked"))
    check("... empty stores add no line at all", "money" not in empty
          and "study" not in empty and "pc" not in empty, empty)


# --------------------------------------------------------------------------
#   2. One source, one set of facts
# --------------------------------------------------------------------------

def t_each_source_contributes_only_its_own_facts():
    got = P.pulse_sources(sources={
        "money": lambda: {"anomalies": ["A bank statement is waiting for you to check it on the PC."]},
        "study": lambda: {"line": "3 cards ready"},
        "pc": lambda: {"anomalies": ["The microphone is giving Jarvis silence."]},
        "prices": lambda: {"anomalies": ["A flight price you watch changed since the last check."]},
    }, locked=False)
    check("the money source adds its anomaly", got["anomalies"][0].startswith("A bank statement"), got)
    check("the study source adds a one-line summary", got.get("study") == "3 cards ready", got)
    check("the PC source adds only its title",
          "The microphone is giving Jarvis silence." in got["anomalies"], got)
    check("the watched-price source adds its own anomaly",
          any("flight price" in a for a in got["anomalies"]), got)
    check("... and the order is fixed: money, PC, prices (study has no anomaly)",
          got["anomalies"] == ["A bank statement is waiting for you to check it on the PC.",
                               "The microphone is giving Jarvis silence.",
                               "A flight price you watch changed since the last check."], got)
    check("... the watched-price source is not one of the three labels",
          "prices" not in got["checked"], got["checked"])


# --------------------------------------------------------------------------
#   3. A broken or slow source cannot stop the pulse
# --------------------------------------------------------------------------

def t_a_broken_source_is_absent_and_says_nothing():
    def boom():
        raise RuntimeError("the store is locked")

    got = P.pulse_sources(sources={"money": boom,
                                   "study": lambda: {"line": "1 card ready"},
                                   "pc": lambda: {},
                                   "prices": lambda: {}}, locked=False)
    check("a raising source does not stop the supplier", isinstance(got, dict), got)
    check("... its facts are absent, not invented", "money" not in got
          and not any("bank" in a for a in got["anomalies"]), got)
    check("... and it is NOT marked read (the briefing will say 'not checked')",
          "money" not in got["checked"] and "study" in got["checked"], got)
    check("... the other sources still arrive", got.get("study") == "1 card ready", got)


def t_a_slow_source_is_bounded():
    def slow():
        time.sleep(5.0)
        return {"line": "should never arrive"}

    started = time.monotonic()
    got = P.pulse_sources(sources={"money": slow,
                                   "study": lambda: {"line": "2 cards ready"},
                                   "pc": lambda: {},
                                   "prices": lambda: {}}, locked=False,
                          budget=1.5)
    elapsed = time.monotonic() - started
    check("a slow source does not hold the pulse past its own budget",
          elapsed < 1.6, elapsed)
    check("... its facts are absent", "money" not in got and "study" in got, got)
    check("... and it is not marked read", "money" not in got["checked"], got)


def t_anomalies_are_capped():
    got = P.pulse_sources(sources={
        "money": lambda: {"anomalies": ["m1", "m2"]},
        "study": lambda: {"anomalies": ["s1"]},
        "pc": lambda: {"anomalies": ["p1", "p2"]},
        "prices": lambda: {"anomalies": ["x1"]},
    }, locked=False)
    check("the supplier never adds more than MAX_ANOMALIES",
          len(got["anomalies"]) == P.MAX_ANOMALIES == 3, got["anomalies"])
    check("... and keeps the first ones in source order",
          got["anomalies"] == ["m1", "m2", "s1"], got["anomalies"])


# --------------------------------------------------------------------------
#   4. App lock / hidden memory lists: fail closed
# --------------------------------------------------------------------------

def t_locked_or_unreadable_withholds_everything():
    check("locked=True answers nothing at all", P.pulse_sources(locked=True) == {})

    def locked_pv():
        return {"locked": True, "app_locked": False, "hide_memory_lists": False}

    def hidden_pv():
        return {"locked": False, "app_locked": False, "hide_memory_lists": True}

    def open_pv():
        return {"locked": False, "app_locked": False, "hide_memory_lists": False}

    def broken_pv():
        raise RuntimeError("no private-view store")

    for fn, expected, why in ((locked_pv, True, "the locked state"),
                              (hidden_pv, True, "the hidden-lists state"),
                              (open_pv, False, "an open view"),
                              (broken_pv, True, "a view that cannot be read")):
        name, mod = _fake("jarvis_private_view", {"effective": lambda *a, **k: fn()})
        with _Swap((name, mod)):
            check(f"{why} is read as locked={expected}", P._locked() is expected)


# --------------------------------------------------------------------------
#   5. The no-leak rule, on the REAL sources' words (fake stores full of private text)
# --------------------------------------------------------------------------

def t_the_real_sources_never_copy_private_words():
    bank_path = "C:/Users/owner/Statements/private-bank-export.csv"
    spending = _fake("jarvis_spending", {
        "view": lambda: {"waiting": [bank_path, bank_path + ".xlsx"]},
    })[1]
    with _Swap(("jarvis_spending", spending)):
        money = P._money()
    check("money: the waiting bank files become a COUNT only",
          money.get("anomalies") == ["2 bank statements are waiting for you to check "
                                     "them on the PC."], money)
    check("... no path, file name or 'owner' survives into the words",
          all(s not in " ".join(money.get("anomalies") or ())
              for s in ("Statements", ".csv", ".xlsx", "owner", "private-bank")), money)

    deck = types.SimpleNamespace(line=lambda: "4 cards ready",
                                 radar=lambda: [{"topic": "Secret Deck", "cards": 2}])
    decks = _fake("jarvis_decks", {"get": lambda: deck})[1]
    with _Swap(("jarvis_decks", decks)):
        study = P._study()
    check("study: the deck's own line is kept", study.get("line") == "4 cards ready", study)
    check("... a fading topic becomes a COUNT, never the deck name",
          study.get("anomalies") == ["A study topic is fading."]
          and "Secret Deck" not in str(study), study)

    finding = {"id": "digital_zero_mic",
               "title": "The microphone is giving Jarvis silence",
               "words": "private words about the owner's device and room"}
    pc_help = _fake("jarvis_pc_help",
                    {"diagnose_silent_failures": lambda: [finding]})[1]
    with _Swap(("jarvis_pc_help", pc_help)):
        pc = P._pc()
    check("PC: the finding's TITLE is the strip item",
          pc.get("anomalies") == ["The microphone is giving Jarvis silence."], pc)
    check("... its long paragraph is never copied", "private words" not in str(pc), pc)

    class _Prices:
        def __init__(self):
            self.path = TMP / "price-radar.db"
            self.path.write_bytes(b"")

        def routes(self):
            return [{"id": 1}]

        def diff(self, route_id):
            return {"changed": True, "price_delta_cents": -5000,
                    "text": "LHR to JFK, $123 with British Airways"}

    radar = _fake("jarvis_price_radar", {
        "enabled": lambda: True,
        "store_path": lambda: TMP / "price-radar.db",
        "PriceStore": _Prices,
    })[1]
    (TMP / "price-radar.db").write_bytes(b"")
    with _Swap(("jarvis_price_radar", radar)):
        prices = P._prices()
    check("prices: a changed watched price is one plain sentence",
          prices.get("anomalies") == ["A flight price you watch changed since the "
                                      "last check."], prices)
    check("... no route, airline or amount survives",
          all(s not in str(prices) for s in ("LHR", "JFK", "$", "123", "British")), prices)


# --------------------------------------------------------------------------
#   6. The pulse_from() integration, and the honest 'not checked' line
# --------------------------------------------------------------------------

def t_pulse_from_uses_the_checked_list_honestly():
    extras = {"money": "2 bank statements are waiting.",
              "study": "3 cards ready",
              "anomalies": ["A study topic is fading."],
              "checked": ["money", "study", "pc"]}
    pulse = B.pulse_from(sections=[], warnings=[], quiet_rows=[], approvals=0,
                         extras=extras, deps=B.Deps())
    check("the money and study lines arrive with their labels",
          "Money: 2 bank statements are waiting." in pulse["lines"]
          and "Study: 3 cards ready" in pulse["lines"], pulse["lines"])
    check("the anomaly reaches the where-to-look strip",
          "A study topic is fading." in pulse["where_to_look"], pulse)
    check("a source READ with nothing to say is not called 'not checked'",
          "PC and GPU health" not in pulse["not_checked"], pulse["not_checked"])
    check("... but nobody-read quiet threads still are",
          "quiet email threads" in pulse["not_checked"], pulse["not_checked"])

    none = B.pulse_from(sections=[], warnings=[], quiet_rows=[], approvals=0,
                        extras=None, deps=B.Deps())
    check("no supplier at all: all three are honestly 'not checked'",
          {"money and subscriptions", "study decks", "PC and GPU health"}
          <= set(none["not_checked"]), none["not_checked"])

    old_style = B.pulse_from(sections=[], warnings=[], quiet_rows=[], approvals=0,
                             extras={"money": "Netflix rose $2.00"}, deps=B.Deps())
    check("an old-style provider with no 'checked' key behaves exactly as before",
          any("Netflix" in ln for ln in old_style["lines"])
          and "study decks" in old_style["not_checked"]
          and "PC and GPU health" in old_style["not_checked"], old_style)


def t_the_briefing_pulse_carries_the_live_shape():
    clock = lambda: 1_790_000_000.0
    sched = S.Scheduler(TMP / "pulse-schedule.db", clock=clock,
                        gate=lambda *a: None, tier_of=lambda a: "ask")
    extras = {"money": "1 bank statement is waiting.",
              "anomalies": ["A bank statement is waiting for you to check it on the PC."],
              "checked": ["money", "study", "pc"]}
    deps = B.Deps(tools_enabled=lambda: set(), pending_count=lambda: 0,
                  pulse_sources=lambda: extras)
    b = B.build(sched=sched, now=clock(), deps=deps)
    check("the built briefing's Pulse carries the supplier's line",
          any("Money: 1 bank statement is waiting." in ln
              for ln in b["pulse"]["lines"]), b["pulse"])
    check("... its anomaly, and no false 'not checked'",
          "A bank statement is waiting for you to check it on the PC."
          in b["pulse"]["where_to_look"]
          and "money and subscriptions" not in b["pulse"]["not_checked"], b["pulse"])
    check("... the text says the strip too",
          "Where to look today:" in b["text"] and "bank statement" in b["text"], b["text"])


def t_live_deps_supplies_the_provider_but_plain_deps_stays_empty():
    live = B.live_deps()
    check("live_deps() supplies a pulse_sources callable",
          callable(live.pulse_sources), live.pulse_sources)
    check("... it is this module's own supplier",
          live.pulse_sources is P.pulse_sources, live.pulse_sources)
    check("a plain Deps() (what a test builds) has no live supplier",
          B.Deps().pulse_sources is None)
    check("... and the guarded import answers the live callable in this tree",
          B._live_pulse_sources() is P.pulse_sources, B._live_pulse_sources())


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("t_") and callable(fn):
            try:
                fn()
            except Exception:
                import traceback
                FAILED.append(name)
                print(f"FAIL {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
