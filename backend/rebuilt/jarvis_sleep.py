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

`set_enabled`/`set_remind` answer the card's own three actions ("enable",
"not now", "stop asking") so a client can act on it, added when the card was
first wired into the desktop and phone UIs rather than only ever printed to a
console. Neither writes `jarvis-framework.toml` - that file is the owner's
own, hand-edited, and this module was never going to start rewriting it from
an HTTP handler. They write a small JSON file next to it instead, the same
shape `extraction-wiring.patch`'s `learning.json` already uses for the same
reason, and `_cfg` reads it first, ahead of the TOML.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore


def _override_path() -> Optional[Path]:
    if fw is None:
        return None
    try:
        return fw.CONFIG_DIR / "sleep_time.json"
    except Exception:
        return None


def _override() -> dict:
    """A correction on top of the TOML, written by `_set` below."""
    path = _override_path()
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _cfg(key: str, default=None):
    """`[memory.sleep_time]`, one key. Called directly by jarvis_hud.

    The override file wins when it has an opinion - it is the newer of the
    two, since it can only exist by someone acting on the card this module
    itself offered - and falls through to the TOML otherwise.
    """
    override = _override()
    if key in override:
        return override[key]
    if fw is None:
        return default
    try:
        mem = fw.load_framework().get("memory", {})
        node = mem.get("sleep_time", {}) if isinstance(mem, dict) else {}
        return node.get(key, default) if isinstance(node, dict) else default
    except Exception:
        return default


def _set(key: str, value: bool) -> dict:
    """Writes one key to the override file, leaving any other key alone.

    Same atomic write as `extraction-wiring.patch`'s `set_learning`: a
    temp file written in full, then renamed over the real one, so a crash
    mid-write leaves the old file intact rather than a half-written one.
    """
    path = _override_path()
    if path is None:
        return {"ok": False, "error": "no config directory available",
                "enabled": enabled(), "remind": remind()}
    try:
        data = _override()
        data[key] = bool(value)
        data["changed"] = time.time()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "enabled": enabled(), "remind": remind()}
    return {"ok": True, "enabled": enabled(), "remind": remind()}


def set_enabled(on: bool) -> dict:
    """The card's "enable" action. Starts nothing - turning this on only
    records the wish and stops `reminder_card()` from offering again; the
    consolidation pass itself remains unimplemented, see the module
    docstring. If it is ever built, it may only PROPOSE changes as review
    cards: nothing retires a stored fact without the owner's yes on that
    one fact."""
    return _set("enabled", on)


def set_remind(on: bool) -> dict:
    """The card's "stop asking" action, sent as `set_remind(False)`."""
    return _set("remind", on)


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
    # The words are the whole of this card, so they must be true. They used
    # to promise a pass that would "merge duplicates and retire facts that
    # newer ones replaced" - nothing does either (status() says
    # "implemented": false), and a pass that retired facts by itself would
    # break the rule that no fact is retired without the owner's yes on that
    # one fact. So: what is built (nothing runs), what switching it on does
    # (records a wish), and what any future version may do (ask, card by
    # card). The clients show `title` and `body` as they are.
    return {
        "kind": "sleep_time_offer",
        "title": "Overnight memory tidying - not built yet",
        "body": ("One day, Jarvis could look over what it learned each day and "
                 "suggest tidying it, such as merging repeats - as ordinary "
                 "review cards you answer one at a time. None of that is built "
                 "yet. Switching it on only records that you want it: nothing "
                 "runs, and nothing in memory changes. Jarvis never changes or "
                 "retires a stored fact without your yes on that one fact."),
        "actions": ["enable", "not now", "stop asking"],
        "implemented": False,
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
