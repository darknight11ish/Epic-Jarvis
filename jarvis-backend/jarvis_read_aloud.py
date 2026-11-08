"""jarvis_read_aloud.py - the automatic read-aloud switch (Wave-9, 2026-11-07).

THE OWNER'S ASK. Jarvis reads every finished reply out loud in the big HUD
window, and there was no switch for it: the only read-aloud setting (the
speakers beside answers, 2026-10-27) added a per-answer button and said, in its
own words, that it "does not turn read-aloud on or off". The owner asked for a
real one: a Settings switch named "read replies out loud", ON by default so
nothing he hears today changes, and OFF at once - by the switch, or by saying
"stop reading your replies out loud" in chat or Jarvis Live.

WHAT OFF DOES, AND WHAT IT DOES NOT. OFF stops the HUD page's AUTOMATIC
speaking of finished answers. It does not remove the per-answer speaker icons
or the answer menu's "Read out loud" item: those are the owner's own tap, one
answer at a time, and they stay. Nothing about the private-speech rule moves:
a private answer is never read, whether this switch is on or off - see
`jarvis-desktop/src/private-speech.js` and the HUD page's own gate.

NO CARD, IN EITHER DIRECTION, and this is a decision rather than an omission.
Turning it off removes speech - it cannot leak anything, reach anything or
change what Jarvis is allowed to do. Turning it back on restores the shipped
default. Neither loosens a rule, so neither needs the owner's second yes.

A MODEL ANSWER NEVER TOGGLES IT. There is no model tool for this switch and no
route for the model to reach: the only writers are the two chat/Live intents in
`jarvis_quick.py` (deterministic, no model) and the Settings switch, both of
which call `set_enabled()` below.

WHERE THE VALUE LIVES. `read_aloud.json` in the Jarvis settings folder, written
atomically, the same shape every other cardless preference here uses. A
missing file is the shipped default (ON). A file that cannot be read FAILS
CLOSED (OFF): a damaged file must not start a silent room talking, which is
the same direction `jarvis_antislop.is_enabled()` chooses for its own switch.

THE ROUTE. GET/POST `/api/read-aloud`, installed by this module's own
`install()` and loaded by `plugins/ready/read-aloud/plugin.json` - the
`jarvis_antislop.py` pattern, so this feature needs no patch of its own and
the Settings page and the HUD page both read the one value.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

#: The shipped default: ON, so every current install behaves exactly as before
#: the switch existed until the owner turns it off.
DEFAULT_ON = True

#: The state file, in the Jarvis settings folder.
STATE_NAME = "read_aloud.json"

#: The one route this module installs (GET the state, POST one change).
STATE_PATH = "/api/read-aloud"

_LOCK = threading.Lock()

#: The chat/Live STATE answer. Two sentences: what the switch is, and what it
#: means right now. It never says "read-aloud is on" because that phrase is
#: what the awareness gate reads as a CLAIM of a change.
STATE_ON = ("Yes - read replies out loud is on. I read each finished answer "
            "aloud, except an answer that has to stay on your screen. Say "
            "\"stop reading your replies out loud\" to stop it, or turn off "
            "\"Read replies out loud\" in Settings.")
STATE_OFF = ("No - read replies out loud is off. I show answers on screen and "
             "read one only when you ask for it (the speaker beside an answer, "
             "or Read out loud in its menu). Say \"read your replies out loud\" "
             "to turn it back on.")

#: The change answers. "Nothing was changed" only when the switch already had
#: the asked-for value - never after a real change.
SET_ON = ("Read-aloud is on now - I read each finished answer aloud again, "
          "except an answer that has to stay on your screen.")
SET_OFF = ("Read-aloud is off now - I keep answers on screen and read one only "
           "when you ask. Nothing else changed.")
ALREADY_ON = "Read replies out loud is already on. Nothing was changed."
ALREADY_OFF = "Read replies out loud is already off. Nothing was changed."

#: THE PHONE-CONNECT REFUSAL (deploy finding 3, 2026-11-07; architect ruling
#: Q8). Measured on the live Wave-8.2 build: "read remembered facts aloud when
#: my phone connects" was answered "I'll set a reminder to read remembered
#: facts aloud when your phone connects" - a change that was never made, for a
#: thing that does not exist. Jarvis never switches a privacy rule on when a
#: device connects: a connection is not the owner's permission. The honest
#: answer says so and points at the REAL control, which is on the phone.
PHONE_CONNECT_REFUSAL = (
    "I cannot do that, and nothing was changed. Jarvis never turns a privacy "
    "setting on when a device connects - a connection is not your permission. "
    "Reading remembered answers aloud is the phone's own choice: on the phone, "
    "open Settings, Voice, and turn on \"Read out answers that use what Jarvis "
    "remembers\". It is off by default and stays the way you set it, whether "
    "the phone is connected or not.")


def _config_dir() -> Path:
    """The Jarvis settings folder, the one every other module uses.

    `jarvis_framework`'s own answer first, then the environment, then the
    default - the same order `jarvis_antislop.py` uses, so a test that points
    `OPENJARVIS_CONFIG_DIR` at a temp folder owns this file too.
    """
    try:
        import jarvis_framework
        return Path(jarvis_framework.CONFIG_DIR)
    except Exception:
        pass
    for name in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR"):
        raw = os.environ.get(name)
        if raw:
            return Path(raw)
    return Path.home() / ".openjarvis"


def state_path() -> Path:
    """`read_aloud.json` in the Jarvis settings folder."""
    return _config_dir() / STATE_NAME


def _on_disk():
    """(found, the document) for the state file.

    `(False, None)` when it was never written - the shipped default applies.
    `(True, None)` when it exists but cannot be read or is not a JSON object -
    the caller fails CLOSED, because a damaged file must not start speaking.
    """
    path = state_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False, None
    except OSError:
        return True, None
    try:
        doc = json.loads(raw)
    except Exception:
        return True, None
    if not isinstance(doc, dict):
        return True, None
    return True, doc


def enabled() -> bool:
    """Is automatic read-aloud on right now? Fails CLOSED on a damaged file."""
    found, doc = _on_disk()
    if not found:
        return DEFAULT_ON
    if doc is None:
        return False
    if isinstance(doc.get("enabled"), bool):
        return doc["enabled"]
    if "enabled" not in doc:
        return DEFAULT_ON
    return False


def state() -> dict:
    """The switch as both apps read it - never a guess and never a write."""
    found, doc = _on_disk()
    known = (not found) or (doc is not None and isinstance(doc.get("enabled"), bool))
    on = enabled()
    return {"ok": True, "enabled": on, "default": DEFAULT_ON,
            "known": known, "words": STATE_ON if on else STATE_OFF,
            "state_path": str(state_path())}


def _publish(on: bool) -> None:
    """Tell anything with an event stream open that the switch moved.

    One kind per feature, the backend's own shape (`jarvis_antislop` publishes
    "antislop"). Never raises: a backend without an event bus still changes the
    setting.
    """
    try:
        import jarvis_events
        jarvis_events.BUS.publish("read_aloud", {"enabled": bool(on)})
    except Exception:
        pass


def set_enabled(on: bool) -> dict:
    """Turn automatic read-aloud on or off, and say what really happened.

    Raises ValueError for anything that is not a real yes/no - a typo must not
    read back as "your setting was saved". Writing is atomic; the previous
    value is read before the write and returned in `before`.
    """
    if not isinstance(on, bool):
        raise ValueError("read replies out loud takes on or off, not that")
    before = enabled()
    path = state_path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({"enabled": bool(on),
                                   "updated_at": time.time()}),
                       encoding="utf-8")
        os.replace(tmp, path)
    changed = before != on
    _publish(on)
    said = ((SET_ON if on else SET_OFF) if changed
            else (ALREADY_ON if on else ALREADY_OFF))
    return {"ok": True, "enabled": bool(on), "before": before,
            "changed": changed, "words": said}


def state_words() -> str:
    """The chat/Live STATE answer for the switch as it stands."""
    return STATE_ON if enabled() else STATE_OFF


def set_words(on: bool) -> str:
    """The change answer for `on`, including the honest no-op sentence."""
    changed = enabled() != on
    if changed and on:
        return SET_ON
    if changed:
        return SET_OFF
    return ALREADY_ON if on else ALREADY_OFF


# --------------------------------------------------------------------------
#   The route (GET the state, POST one change) - installed by the loader
# --------------------------------------------------------------------------

def handle_get(route: str, query: str = "") -> tuple:
    """GET /api/read-aloud -> (200, the state). A read; nothing is written."""
    if route != STATE_PATH:
        return 404, {"ok": False, "error": "not_found"}
    return 200, state()


def handle_post(route: str, body: object) -> tuple:
    """POST /api/read-aloud {"enabled": true|false} -> (200, the new state)."""
    if route != STATE_PATH:
        return 404, {"ok": False, "error": "not_found"}
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "bad_body",
                     "message": "the request body must be a JSON object"}
    unknown = sorted(set(body) - {"enabled"})
    if unknown:
        return 400, {"ok": False, "error": "unknown_setting",
                     "message": f"read replies out loud has no setting called "
                                f"{unknown[0]}"}
    try:
        out = set_enabled(body.get("enabled"))
    except ValueError as exc:
        return 400, {"ok": False, "error": "bad_value", "message": str(exc)}
    except Exception as exc:                      # noqa: BLE001 - said, not swallowed
        return 503, {"ok": False, "error": type(exc).__name__,
                     "message": "the read-aloud setting could not be saved"}
    out.update({"default": DEFAULT_ON, "known": True,
                "state_path": str(state_path())})
    return 200, out


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET`/`do_POST` so this module answers its own route.

    Every other request goes straight to the original, untouched - the same
    shape `jarvis_antislop.install()` uses, and the reason this feature needs
    no patch: `plugins/ready/read-aloud/plugin.json` names this module and
    `jarvis_plugins.py` makes the call the patch would have made.
    """
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(get0, "_jarvis_read_aloud", False):
        return "read-aloud   the automatic read-aloud switch (already on)"

    from urllib.parse import urlsplit

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
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if route != STATE_PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route, parts.query)
        except Exception as exc:                  # noqa: BLE001 - never a traceback page
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if route != STATE_PATH:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception:
            body = None
        try:
            code, out = handle_post(route, body)
        except Exception as exc:                  # noqa: BLE001 - never a traceback page
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_read_aloud = True
    do_POST._jarvis_read_aloud = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return "read-aloud   the automatic read-aloud switch (GET/POST /api/read-aloud)"
