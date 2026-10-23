"""jarvis_pulse_sources.py - the Daily Pulse's four local read-only summaries.

WHY THIS EXISTS (2026-10-23, P3 seam B5-c). Wave D-1 gave the briefing a
Daily Pulse, but its money / study / PC-health halves were caller-supplied
only: `Deps.pulse_sources` was None in every production build, so the Pulse
always said those sources were "not checked" and the "where to look" strip
never carried a real one. This module is the supplier the live briefing wires
in (`jarvis_briefing.live_deps()`): it reads the SAME local stores the four
features already keep, and returns them in the shape `pulse_from()` already
knows - optional `money` / `study` / `pc` one-line summaries, an `anomalies`
list, and the new `checked` list of sources that really were read.

WHAT IT READS, and nothing else:

* **money** - `jarvis_spending.view()`: the layout profiles and the in-memory
  list of bank files waiting for a layout. A count only, never a file name, a
  path, a merchant or an amount.
* **study** - `jarvis_decks.get().line()`: "3 cards ready" / "Nothing ready
  today" from numbers that need no key, and the fading-topic COUNT from
  `radar()` (which is discarded; a deck name is never read into the pulse).
* **PC health** - `jarvis_pc_help.diagnose_silent_failures()`: the Pillar 28
  findings' short TITLES only; the long paragraphs are not copied.
* **watched prices** - `jarvis_price_radar`: only when the owner turned the
  radar on and its store already exists. "a price changed" - never the route,
  the airline or the amount.

THE RULES, and they are the point:

* READ-ONLY. No network, no program started, no approval card, no route, no
  writing a preference. Every call is a read of a store this PC already has.
* PRIVACY FIRST. App lock / "Hide memory lists and chat history" withholds the
  whole extras block (fail closed: a lock state that cannot be read counts as
  locked). The Today board already withholds the Pulse while hidden; this is
  the second, independent half. Counts and titles only - never the ceiling of
  what the owning feature can show.
* BOUNDED AND FAIL-SOFT. Each source gets a short deadline on a daemon thread
  and its own `try`/`except`; one slow or broken source is simply absent, and
  the briefing then reports it "not checked" - never "0".
* DETERMINISTIC. Sources run in one fixed order (money, study, PC, prices) and
  the anomalies list is capped at MAX_ANOMALIES.

Tests: `backend/test_pulse_sources.py` (fake sources, one per source, slow and
failing sources, the locked case, the no-names/no-amounts rule, the extras
shape, and the `pulse_from` integration including the honest `not_checked`).
"""
from __future__ import annotations

import threading
import time

#: One source may take at most this long...
SOURCE_BUDGET_S = 1.2
#: ... and the whole supplier at most this, so a briefing never waits for it.
TOTAL_BUDGET_S = 2.0
#: The strip's own cap is three; the supplier never adds more than three.
MAX_ANOMALIES = 3
#: How many watched routes are inspected (the store can hold more).
MAX_PRICE_ROUTES = 3


def _bounded(fn, seconds: float):
    """Run `fn()` on a daemon thread; its dict, or None if it raised or was
    slower than `seconds`. The thread is abandoned, never waited for for ever."""
    box: dict = {}

    def run():
        try:
            box["value"] = fn()
        except Exception:
            box["value"] = None

    thread = threading.Thread(target=run, daemon=True, name="jarvis-pulse-source")
    thread.start()
    thread.join(max(0.0, float(seconds)))
    if thread.is_alive():
        return None
    return box.get("value")


# --------------------------------------------------------------------------
#   The sources, one per owning module
# --------------------------------------------------------------------------

def _money() -> dict:
    """A bank file waiting for its layout, as a count - never its name/path."""
    import jarvis_spending as S
    view = S.view()
    waiting = len(view.get("waiting") or [])
    if waiting <= 0:
        return {}
    if waiting == 1:
        return {"anomalies": ["A bank statement is waiting for you to check it on the PC."]}
    return {"anomalies": [f"{waiting} bank statements are waiting for you to check "
                          "them on the PC."]}


def _study() -> dict:
    """The decks' own line (numbers only) plus how many topics are fading."""
    import jarvis_decks as D
    out: dict = {}
    line = ""
    try:
        line = str(D.get().line() or "").strip()
    except Exception:
        line = ""
    if line:
        out["line"] = line
    radar = []
    try:
        radar = D.get().radar() or []
    except Exception:
        radar = []          # no key / no crypto: the line above still stands
    if radar:
        n = len(radar)
        out["anomalies"] = [("A study topic is fading." if n == 1
                             else f"{n} study topics are fading.")]
    return out


def _pc() -> dict:
    """The silent-failure doctor's short titles, never its paragraphs."""
    import jarvis_pc_help as H
    anomalies = []
    for finding in H.diagnose_silent_failures() or ():
        title = str((finding or {}).get("title") or "").strip()
        if not title:
            continue
        if not title.endswith((".", "!", "?")):
            title += "."
        anomalies.append(title)
        if len(anomalies) >= 2:      # two is plenty on the strip
            break
    return {"anomalies": anomalies} if anomalies else {}


def _prices() -> dict:
    """A watched flight price changed - never the route, airline or amount."""
    import jarvis_price_radar as PR
    if not PR.enabled():
        return {}
    try:
        if not PR.store_path().is_file():
            return {}
        store = PR.PriceStore()
        routes = store.routes() or []
    except Exception:
        return {}
    for route in routes[:MAX_PRICE_ROUTES]:
        try:
            change = store.diff(route.get("id"))
        except Exception:
            continue
        if isinstance(change, dict) and change.get("changed"):
            return {"anomalies": ["A flight price you watch changed since the last check."]}
    return {}


#: Fixed order: the pulse's content and the strip's order are deterministic.
_DEFAULTS = (
    ("money", _money),
    ("study", _study),
    ("pc", _pc),
    ("prices", _prices),
)
#: The three sources `pulse_from()` reports in `not_checked` when nobody read
#: them. "prices" is not one of them (the radar is optional and off by default).
_LABELS = ("money", "study", "pc")


def _locked() -> bool:
    """App lock / hidden memory lists, fail closed: cannot tell means locked."""
    try:
        import jarvis_private_view as PV
        got = PV.effective(app_locked=False, hide_memory_lists=False)
        return bool(got.get("locked") or got.get("app_locked")
                    or got.get("hide_memory_lists"))
    except Exception:
        return True


def pulse_sources(*, sources: dict | None = None, locked: bool | None = None,
                  budget: float | None = None) -> dict:
    """The Pulse's extras, from four local read-only sources.

    `sources` replaces individual defaults by name (tests pass fakes); `locked`
    overrides the App-lock check (None reads it, fail closed); `budget` is the
    whole supplier's deadline in seconds.

    Answers only the keys with something in them, plus `anomalies` (a list of
    short plain sentences, at most MAX_ANOMALIES) and `checked` (the label
    sources that really were read - a source that failed or timed out is NOT
    in it, so the briefing's `not_checked` stays honest). While locked/hidden
    it answers `{}`: a source nobody may read is a source nobody read.
    """
    if locked is None:
        locked = _locked()
    if locked:
        return {}
    chosen = dict(_DEFAULTS)
    for name, fn in (sources or {}).items():
        if name in chosen and callable(fn):
            chosen[name] = fn
    extras: dict = {"anomalies": [], "checked": []}
    start = time.monotonic()
    total = TOTAL_BUDGET_S if budget is None else float(budget)
    seen = set()
    for name, fn in chosen.items():
        left = total - (time.monotonic() - start)
        if left <= 0:
            break
        got = _bounded(fn, min(SOURCE_BUDGET_S, left))
        if not isinstance(got, dict):
            continue          # failed/slow: absent, and NOT marked checked
        line = str(got.get("line") or "").strip()
        if line:
            extras[name] = line
        if name in _LABELS:
            extras["checked"].append(name)
        for anomaly in got.get("anomalies") or ():
            text = str(anomaly or "").strip()
            if text and text not in seen:
                seen.add(text)
                extras["anomalies"].append(text)
        if len(extras["anomalies"]) >= MAX_ANOMALIES:
            break
    extras["anomalies"] = extras["anomalies"][:MAX_ANOMALIES]
    return extras
