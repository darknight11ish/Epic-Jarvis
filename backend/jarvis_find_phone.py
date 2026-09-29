"""jarvis_find_phone.py - "ring my phone" / "find my phone": ONE event the
phone reacts to by ringing on its alarm channel, even on silent, with a Stop
button and a time-out.

NEW MODULE, shipped whole, no patch: jarvis_quick.py answers the owner's
words WITHOUT the AI model and calls ring() or stop() here, which publish on
the event bus the chat route already runs. docs/JARVIS-API.md section 74;
backend/README.md "Ring my phone".

THE OWNER'S DECISION (2026-09-28, the research audit, idea 7): "Ring my
phone" said or typed to Jarvis is answered on the PC without the AI model;
the phone rings on the alarm channel, even on silent, with Stop and a
time-out. No card: it only rings the owner's own phone, from the owner's own
words. The idea is KDE Connect's "Find my phone" (GPL) - the idea only, no
code.

THE EVENT - a doorbell with no words
`ring_phone` on the bus: {"id": "r" + 12 hex, "state": "ring" | "stop",
"at": epoch on the PC, "until": epoch, "seconds": RING_SECONDS}. No words
at all - the phone writes its own ("Jarvis is ringing this phone").

A STALE OR REPLAYED EVENT NEVER RINGS
The phone rings only when (net/FindPhone.kt, the phone's own check):
  * it has not rung for this `id` before (a reconnect replays the ring of
    recent events - it must not ring twice), and
  * the event is fresh: the phone's clock is within FRESH seconds of `at`
    (a phone that was out of reach and catches up later stays quiet - far
    stricter than the 10-minute rule for alarms, because a ring that comes
    late is only a surprise, never useful).
`until` lets it stop by itself even if the Stop is never pressed.

WHICH PHONE
The backend cannot tell phones apart: every paired device uses the ONE
pairing key (jarvis_token_store), and the "more devices" work that gives
each its own key is not built yet. So every phone whose Jarvis app is
connected rings, and the answer says so when the owner named one ("ring my
work phone"). Nothing reports back which phone rang - the PC does not know,
and the answer never pretends to.

Standard library only. Opens no socket, reads nothing of the owner's.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Callable, Optional

EVENT = "ring_phone"
#: How long the phone rings unless Stop is pressed first.
RING_SECONDS = 60
#: The phone ignores a ring whose `at` is further than this from its own
#: clock (both apps' copy: net/FindPhone.kt FRESH_SECONDS).
FRESH = 120
#: Saying it twice in quick succession sends one ring, not two.
AGAIN_AFTER = 5.0

RINGING = ("Ringing your phone now - for up to a minute, even on silent, if the Jarvis app on "
           "it is connected. Press Stop on the phone to stop it.")
RINGING_NAMED = ("Jarvis cannot tell your phones apart yet - they share one pairing key - so "
                 "every phone with the Jarvis app connected will ring, for up to a minute, even "
                 "on silent. Press Stop on it to stop it.")
ALREADY = "It is already ringing. Press Stop on the phone to stop it."
STOPPED = "Stopped ringing your phone."
NOT_RINGING = "Your phone is not ringing."
NO_BUS = ("Jarvis could not send the ring to your phone just now - try again in a moment, or "
          "restart Jarvis on the PC.")

_LOCK = threading.Lock()
_LAST: dict = {}


def _default_publish(kind: str, data: dict) -> None:
    import jarvis_events
    jarvis_events.BUS.publish(kind, data)


def _audit(event: str, detail: dict) -> None:
    try:
        import jarvis_framework as fw
        fw.audit_log(event, detail)
    except Exception:
        pass


def ring(*, named: bool = False, now: Optional[float] = None,
         publish: Optional[Callable[[str, dict], None]] = None) -> dict:
    """Send ONE ring. {"ok", "said", "id"?}. Never raises."""
    now = time.time() if now is None else float(now)
    publish = publish or _default_publish
    with _LOCK:
        last = _LAST.get("ring")
        if last and last.get("state") == "ring" and now - float(last["at"]) < AGAIN_AFTER:
            return {"ok": True, "said": ALREADY, "id": last["id"]}
        rid = "r" + uuid.uuid4().hex[:12]
        data = {"id": rid, "state": "ring", "at": now, "until": now + RING_SECONDS,
                "seconds": RING_SECONDS}
        try:
            publish(EVENT, data)
        except Exception:
            return {"ok": False, "said": NO_BUS}
        _LAST["ring"] = dict(data)
    _audit("find_phone.ring", {"id": rid})
    return {"ok": True, "said": RINGING_NAMED if named else RINGING, "id": rid}


def stop(*, now: Optional[float] = None,
         publish: Optional[Callable[[str, dict], None]] = None) -> dict:
    """Stop the ring still going, from the PC. {"ok", "said"}. Never raises."""
    now = time.time() if now is None else float(now)
    publish = publish or _default_publish
    with _LOCK:
        last = _LAST.get("ring")
        if not last or last.get("state") != "ring" or now > float(last["until"]):
            return {"ok": True, "said": NOT_RINGING}
        data = {"id": last["id"], "state": "stop", "at": now, "until": now, "seconds": 0}
        try:
            publish(EVENT, data)
        except Exception:
            return {"ok": False, "said": NO_BUS}
        _LAST["ring"] = dict(last, state="stopped")
    _audit("find_phone.stop", {"id": data["id"]})
    return {"ok": True, "said": STOPPED}


def _reset_for_tests() -> None:
    with _LOCK:
        _LAST.clear()
