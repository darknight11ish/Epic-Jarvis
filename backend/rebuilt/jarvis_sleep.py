"""jarvis_sleep.py - the overnight consolidation pass, and whether it is on.

REBUILT. Three call sites:

    jarvis_hud.py:2231   if not jarvis_sleep.enabled():
    jarvis_hud.py         jarvis_sleep._cfg(...)
    jarvis_hud.py         jarvis_sleep.reminder_card()

and one banner line the HUD prints when it is off:

    "sleep-time off (a daily card will offer to enable it; remind=false stops that)"

That sentence is the specification for `reminder_card()`: something that
OFFERS, once a day, and can be switched off by a `remind` setting. The config
section is `[memory.sleep_time]`.

DELIBERATELY DOES NOT RUN ANYTHING YET. The owner's own recorded decision was
to "park all memory-system work until Jarvis is actually running and he has
used it for a while". A consolidation pass that reorganises memory unattended
is exactly the thing that decision was about, so this module reports and
offers; it does not consolidate. An INFERRED implementation of the pass itself
would be a silent, unreviewed rewrite of the fact store.
"""
from __future__ import annotations

import time
from typing import Optional

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore


def _cfg(key: str, default=None):
    """`[memory.sleep_time]`, one key. Called directly by jarvis_hud."""
    if fw is None:
        return default
    try:
        mem = fw.load_framework().get("memory", {})
        node = mem.get("sleep_time", {}) if isinstance(mem, dict) else {}
        return node.get(key, default) if isinstance(node, dict) else default
    except Exception:
        return default


def enabled() -> bool:
    """Is the overnight pass switched on?

    Defaults FALSE, unlike most settings here. The banner line the HUD prints
    assumes off is the normal state ("sleep-time off (a daily card will offer
    to enable it)"), and a memory-reorganising pass that turned itself on
    because a config key was missing is the wrong direction to fail in.
    """
    return bool(_cfg("enabled", False))


def remind() -> bool:
    return bool(_cfg("remind", True))


def hour() -> int:
    # The TOML key is `remind_hour_local` (jarvis-framework.toml:367), not
    # "hour" - the same class of typo as jarvis_power's old
    # quiet_hours_start/quiet_start mismatch, in a different module. There is
    # no current caller (grepped the whole repo), so nothing has silently
    # used 3am instead of the owner's configured hour yet - but the moment
    # reminder_card() or anything else gates on this, it would have.
    try:
        h = int(_cfg("remind_hour_local", 3))
    except (TypeError, ValueError):
        return 3
    return h if 0 <= h <= 23 else 3


def reminder_card() -> Optional[dict]:
    """The daily offer to switch it on, or None.

    None in three cases: it is already on, reminders are off, or one has
    already been offered today. The last is why this returns None rather than
    an empty dict - the HUD tests the result for truthiness.
    """
    if enabled() or not remind():
        return None
    today = time.strftime("%Y-%m-%d")
    if _seen.get("day") == today:
        return None
    _seen["day"] = today
    return {
        "kind": "sleep_time_offer",
        "title": "Let Jarvis tidy its memory overnight?",
        "body": ("Once a night it would re-read what it learned that day, "
                 "merge duplicates and retire facts that newer ones replaced. "
                 "It changes stored facts, so it is off until you say."),
        "actions": ["enable", "not now", "stop asking"],
        "config": "[memory.sleep_time] enabled / remind",
    }


_seen: dict = {}


def status() -> dict:
    return {"enabled": enabled(), "remind": remind(), "hour": hour(),
            "implemented": False,
            "note": "reports and offers; the consolidation pass itself is "
                    "deliberately not implemented - see the module docstring"}


if __name__ == "__main__":
    for k, v in status().items():
        print(f"  {k:<14} {v}")
