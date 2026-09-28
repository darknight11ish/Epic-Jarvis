"""jarvis_animal.py - every animal-face option in one place, shared by both apps.

NEW MODULE, shipped whole. animal.patch adds two small hunks to jarvis_hud.py:
one call at start-up, `install(Handler, ...)` (the same shape as
jarvis_sky.py), which answers GET /api/animal and POST /api/animal; and a few
lines in appearance.patch's `_appearance_view`, so GET /api/appearance - the
document both apps already re-read on every `appearance` event - carries the
same values as `"animal"`. docs/JARVIS-API.md section 60; backend/README.md
"Animal options".

THE OWNER'S DECISIONS (CLAUDE.md, 2026-09-28)
  * "Every animal option lives in one place in both apps' settings (Still,
    sun and moon, weather and its source, resolution, frame rate, and every
    new one), and Jarvis can change any of them when asked ... cosmetic
    options change at once; anything that opens a way out of the PC (online
    weather) still raises its approval card. Look-and-behaviour options are
    shared between the PC and the phone (one request changes both);
    sharpness and frame rate stay per device."
  * "New animal behaviours, all four chosen": listening nods, a focus buddy
    and small acknowledgements, petting, seasonal touches (off by default);
    and "Two cute idle moments per face ... with a switch in the animal
    options" (on by default).
  * Five faces share these options: the four animals and the robot (a
    fifth face, 2026-09-28). Nothing here names a face: each option applies
    to every character face the apps draw, so a new face needs no change.
    "Each is an option in the one animal options place and changeable by
    asking Jarvis. Still and serious moments switch every one off; calm
    makes them smaller."

WHAT LIVES WHERE (one home per option - nothing is kept twice)
  * HERE, on the PC, shared by both apps: "Keep the animal still" and the
    behaviour switches (SWITCHES below). Stored in `animal.json` in the
    Jarvis settings folder, beside appearance.json (the face and the state
    colours) - its own file, so the Faces window's save (appearance.patch's
    `_appearance_save`, which writes only the face and the colours) can never
    overwrite them, and a change here can never overwrite the face.
  * jarvis_sky.py, on the PC, shared by both apps already: the sun and moon
    (on/off), the town and the weather source. Not copied here: its card
    for Open-Meteo, its town rules and its words stay the one version. Both
    apps show it inside their Animal options section.
  * Each device, never sent anywhere: sharpness (the quality level) and the
    frame rate - what one graphics chip can draw says nothing about another's
    (jarvis-desktop/src/face-tuning.js, the phone's data/FaceTuning.kt).
    Jarvis changes those through the answer's X-Jarvis-Route header
    (`face_tuning`, the same road "open web search" uses), so the device the
    request came from changes itself - see DEVICE_CHANGES and step_device().

ADDING A BEHAVIOUR (the pattern the next ones follow)
One `Switch(...)` entry in SWITCHES: its id, its words, its default, whether
the animal already does it (`built`), and what the owner might call it. That
is all: the route, both apps' sections (they draw whatever the PC lists, and
fall back to their own copy of this list, held equal by
tools/gen_animal_cases.py's fixture) and the spoken on/off
(jarvis_settings_registry.find_animal_switch, jarvis_quick._animal) follow
from it. The six behaviours (the owner added "Cute idle moments" the same day) are
stored and shared from today, each with the owner's chosen default; the animal starts doing each one when that behaviour
is built, and until then its row says so plainly (COMING).

NOTHING HERE IS PRIVILEGED
Every switch here is cosmetic: it changes how the animal moves, approves
nothing, starts nothing, reads nothing and sends nothing anywhere - so no
card, either way, from either app or by asking (the same rule as the face and
the colours, docs/APPEARANCE-API.md). Anything that would open a way out of
the PC does not belong in SWITCHES: the one animal option that does (online
weather) is jarvis_sky.py's, with its card.

    python3 test_animal.py
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

PATH = "/api/animal"

# --------------------------------------------------------------------------
#   Words both apps show (jarvis-desktop/src/animal-shared.js and the phone's
#   net/AnimalOptions.kt fall back to the same words when the PC sends none)
# --------------------------------------------------------------------------

TITLE = "Animal options"
INTRO = ("Everything about the animal and robot faces, in one place. You can also ask Jarvis, "
         "like \"keep the animal still\" or \"turn off the weather\".")
SHARED_TITLE = "Shared with your phone"
SHARED_NOTE = ("Kept on your PC: a change here, on your phone or by asking Jarvis changes both. "
               "No approval card - these only change how the animal moves.")
SERIOUS_NOTE = ("\"Keep the animal still\" and serious moments (an approval, an error, a crisis "
                "answer) switch the behaviours off; calm motion makes them smaller.")
COMING = "Coming in the next update: saved now, and the animal starts doing it then."
MISSING = ("Your PC's Jarvis cannot share the animal options yet - run apply-patches.ps1 on "
           "the PC.")


@dataclass(frozen=True)
class Switch:
    """One shared on/off animal option. Everything about it is here."""
    id: str
    label: str
    detail: str
    default: bool
    #: False: stored and shared now; the animal starts doing it in a coming
    #: update, and both apps say so under the switch (COMING), as does
    #: `on_said`. When the behaviour is built: True, and `on_said` loses its
    #: "in the next update".
    built: bool
    #: What the owner might call it, for "turn on/off <name>" - lower case,
    #: whole phrases only (a leading "the"/"my"/"a" is ignored).
    names: tuple
    on_said: str
    off_said: str


SWITCHES: tuple = (
    Switch(
        "still", "Keep the animal still",
        "It only breathes and blinks - no looking around, gestures or little idle events. "
        "For the animal and robot faces; the others are not changed.",
        False, True,
        ("keep the animal still", "keeping the animal still", "the animal still", "still mode",
         "the still option", "still"),
        "the animal keeps still now, on your PC and phone",
        "the animal moves as usual again, on your PC and phone"),
    Switch(
        "nods", "Listening nods",
        "Small nods in your pauses while you talk, and gestures that land at the ends of "
        "Jarvis's sentences.",
        True, False,
        ("listening nods", "nods", "nodding", "the animal's nods", "the animal's nodding",
         "the animal nodding", "animal nods"),
        "listening nods are on for your PC and phone; the animal starts nodding in the next "
        "update",
        "listening nods are off, on your PC and phone"),
    Switch(
        "focus_buddy", "Focus buddy",
        "In a focus session the animal works quietly beside you and stretches at the end. It "
        "never sees your screen and never scolds.",
        True, False,
        ("focus buddy", "the animal's focus buddy", "focus buddy mode"),
        "focus buddy is on for your PC and phone; the animal starts doing it in the next "
        "update",
        "focus buddy is off, on your PC and phone"),
    Switch(
        "acks", "Small acknowledgements",
        "A small nod when Jarvis saves a fact (not while App lock or \"Hide memory lists\" is "
        "on), and a glow when a long answer is ready.",
        True, False,
        ("small acknowledgements", "small acknowledgments", "acknowledgements",
         "acknowledgments", "the animal's acknowledgements", "the animal's acknowledgments"),
        "small acknowledgements are on for your PC and phone; the animal starts doing them "
        "in the next update",
        "small acknowledgements are off, on your PC and phone"),
    Switch(
        "petting", "Petting",
        "Stroke the animal and it leans in. On the phone it is a long press on the face, which "
        "does not open the Brain.",
        True, False,
        ("petting", "the animal's petting", "petting the animal", "pet mode"),
        "petting is on for your PC and phone; the animal starts leaning in in the next "
        "update",
        "petting is off, on your PC and phone"),
    Switch(
        "cute_moments", "Cute idle moments",
        "Now and then, after the face has rested a while, one of its two short cute moments "
        "plays, then it settles back. Never during an approval or an error.",
        True, False,
        ("cute idle moments", "cute moments", "idle moments",
         "the animal's cute moments", "cute animations"),
        "cute idle moments are on for your PC and phone; they start playing in the next "
        "update",
        "cute idle moments are off, on your PC and phone"),
    Switch(
        "seasonal", "Seasonal touches",
        "Small touches for the time of year, from the date on your device. Off by default.",
        False, False,
        ("seasonal touches", "the animal's seasonal touches", "seasonal decorations",
         "seasonal things"),
        "seasonal touches are on for your PC and phone; they start showing in the next "
        "update",
        "seasonal touches are off, on your PC and phone"),
)

_BY_ID = {s.id: s for s in SWITCHES}
DEFAULTS = {s.id: s.default for s in SWITCHES}

# --------------------------------------------------------------------------
#   Per device: sharpness and frame rate (never stored here)
# --------------------------------------------------------------------------

DEVICE_TITLE = "Sharpness and frame rate"
DEVICE_NOTE = ("Each device keeps its own: what one graphics chip can draw says nothing about "
               "another's. They apply to every face, not only the animals.")

#: The same ids and words as face-tuning.js QUALITIES / FRAME_RATES and the
#: phone's QualityTier / FrameRateTarget (tests/continuity.mjs, the phone's
#: FaceBudgetTest hold those two together; the fixture holds these to them).
SHARPNESS = (("low", "Lower"), ("medium", "Balanced"), ("high", "High"), ("max", "Maximum"))
FRAME_RATES = (("auto", "Auto"), ("30", "30"), ("60", "60"), ("90", "90"), ("120", "120"),
               ("max", "Max"))
_SHARP_ORDER = [i for i, _ in SHARPNESS]
#: Stepping walks the numbered rates; "Auto" and "Max" are ends, not steps.
_RATE_STEPS = ["30", "60", "90", "120", "max"]

#: The `face_tuning` values X-Jarvis-Route may carry, and nothing else.
DEVICE_CHANGES = (
    "sharper", "softer", "smoother", "less_smooth", "auto",
    *(f"sharpness:{i}" for i, _ in SHARPNESS),
    *(f"frame_rate:{i}" for i, _ in FRAME_RATES if i != "auto"),
)

#: What Jarvis says for each - the device the request came from makes the
#: change, so the answer says "on this device only", never which one.
DEVICE_SAID = {
    "sharper": "Done - one step sharper, on this device only.",
    "softer": "Done - one step softer, on this device only.",
    "smoother": "Done - one step smoother (a higher frame rate), on this device only.",
    "less_smooth": "Done - a lower frame rate, on this device only.",
    "auto": "Done - sharpness and frame rate are picked automatically again, on this device "
            "only.",
}
for _i, _w in SHARPNESS:
    DEVICE_SAID[f"sharpness:{_i}"] = f"Done - sharpness {_w}, on this device only."
for _i, _w in FRAME_RATES:
    if _i != "auto":
        DEVICE_SAID[f"frame_rate:{_i}"] = f"Done - frame rate {_w}, on this device only."


def _label(pairs, i) -> str:
    return next((w for k, w in pairs if k == i), i)


def step_device(tuning: dict, change: str) -> dict:
    """The one rule both apps apply for a `face_tuning` change (the
    reference; animal-shared.js stepTuning and AnimalOptions.step are held to
    it by the fixture). `tuning` is {quality, frameRate, autoAdjust}.

    Returns {"tuning": {...}, "changed": bool, "line": "..."} - the line
    uses "{device}" ("this computer" / "this phone"), filled in by the app.
    A step picks a value, so Auto adjust goes off, exactly as a tap on a
    level in either app's Settings does; "auto" turns it back on. While
    Auto adjust is on, a step starts from High and from 60 - what Auto
    starts from."""
    q = tuning.get("quality") if tuning.get("quality") in _SHARP_ORDER else "high"
    f = str(tuning.get("frameRate")) if str(tuning.get("frameRate")) in dict(FRAME_RATES) \
        else "auto"
    auto = tuning.get("autoAdjust") is not False
    out = {"quality": q, "frameRate": f, "autoAdjust": auto}
    base_q = "high" if auto else q
    base_f = "60" if auto or f == "auto" else f

    def done(new: dict, line: str) -> dict:
        return {"tuning": new, "changed": new != out, "line": line}

    if change in ("sharper", "softer"):
        i = _SHARP_ORDER.index(base_q) + (1 if change == "sharper" else -1)
        if i < 0 or i >= len(_SHARP_ORDER):
            end = _label(SHARPNESS, base_q)
            if not auto:
                return done(dict(out), f"Sharpness is already {end} on {{device}}.")
            new = dict(out, quality=base_q, autoAdjust=False)
            return done(new, f"Sharpness on {{device}}: {end}.")
        new = dict(out, quality=_SHARP_ORDER[i], autoAdjust=False)
        return done(new, f"Sharpness on {{device}}: {_label(SHARPNESS, _SHARP_ORDER[i])}.")
    if change in ("smoother", "less_smooth"):
        j = _RATE_STEPS.index(base_f) if base_f in _RATE_STEPS else 1
        j += 1 if change == "smoother" else -1
        if j < 0 or j >= len(_RATE_STEPS):
            end = _label(FRAME_RATES, base_f)
            if not auto and f != "auto":
                return done(dict(out), f"Frame rate is already {end} on {{device}}.")
            new = dict(out, frameRate=base_f, autoAdjust=False)
            return done(new, f"Frame rate on {{device}}: {end}.")
        new = dict(out, frameRate=_RATE_STEPS[j], autoAdjust=False)
        return done(new, f"Frame rate on {{device}}: {_label(FRAME_RATES, _RATE_STEPS[j])}.")
    if change == "auto":
        return done(dict(out, autoAdjust=True),
                    "Auto adjust is on for {device}: it picks sharpness and frame rate.")
    if change.startswith("sharpness:") and change[10:] in _SHARP_ORDER:
        v = change[10:]
        return done(dict(out, quality=v, autoAdjust=False),
                    f"Sharpness on {{device}}: {_label(SHARPNESS, v)}.")
    if change.startswith("frame_rate:") and change[11:] in dict(FRAME_RATES):
        v = change[11:]
        return done(dict(out, frameRate=v, autoAdjust=False),
                    f"Frame rate on {{device}}: {_label(FRAME_RATES, v)}.")
    return done(dict(out), "")


# --------------------------------------------------------------------------
#   The settings file
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def settings_path() -> Path:
    return _config_dir() / "animal.json"


def _audit(event: str, detail: dict) -> None:
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _default_publish(kind: str, data: dict) -> None:
    try:
        import jarvis_events
        jarvis_events.BUS.publish(kind, data)
    except Exception:
        pass


#: Replaceable, so the tests see what would be published.
publish: Callable[[str, dict], None] = _default_publish

_LOCK = threading.RLock()


def values() -> dict:
    """Every switch's value: what is stored, else its default. A damaged
    or missing file is the defaults - every one of them cosmetic, so a
    default is never a risk."""
    out = dict(DEFAULTS)
    try:
        doc = json.loads(settings_path().read_text(encoding="utf-8"))
    except Exception:
        return out
    if isinstance(doc, dict):
        stored = doc.get("switches") if isinstance(doc.get("switches"), dict) else {}
        for k in out:
            if isinstance(stored.get(k), bool):
                out[k] = stored[k]
    return out


def _stored_meta() -> dict:
    try:
        doc = json.loads(settings_path().read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def _save(key: str, on: bool) -> dict:
    with _LOCK:
        cur = values()
        cur[key] = bool(on)
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({"switches": cur, "changed": time.time()}, indent=1),
                       encoding="utf-8")
        os.replace(tmp, p)
        return values()


def view() -> dict:
    """GET /api/animal: the values with the words both apps show."""
    v = values()
    return {
        "available": True, "title": TITLE, "intro": INTRO,
        "shared_title": SHARED_TITLE, "shared_note": SHARED_NOTE,
        "serious_note": SERIOUS_NOTE, "coming": COMING,
        "switches": [{"id": s.id, "label": s.label, "detail": s.detail, "default": s.default,
                      "built": s.built, "on": v[s.id]} for s in SWITCHES],
        "values": v,
        "changed": float(_stored_meta().get("changed") or 0.0),
        "device": {"title": DEVICE_TITLE, "note": DEVICE_NOTE,
                   "sharpness": [{"id": i, "label": w} for i, w in SHARPNESS],
                   "frame_rates": [{"id": i, "label": w} for i, w in FRAME_RATES]},
    }


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:] + "."


def set_switch(key: str, on) -> tuple:
    """ONE switch, at once, from either app or by asking - the function
    POST /api/animal and the spoken "turn off listening nods" both call.
    Returns (http code, {"ok", "said", "view"?, "error"?})."""
    s = _BY_ID.get(key)
    if s is None:
        return 400, {"ok": False, "error": f"{key!r} is not an animal option."}
    if not isinstance(on, bool):
        return 400, {"ok": False, "error": f"{key} is true or false."}
    before = values()
    if before[key] == on:
        word = "on" if on else "off"
        return 200, {"ok": True, "said": f"{s.label}: already {word}.", "changed": False,
                     "view": view()}
    try:
        now = _save(key, on)
    except Exception as exc:
        return 500, {"ok": False, "error": f"could not save ({type(exc).__name__})"}
    _audit("animal.switch", {"key": key, "on": on})
    # A doorbell both apps already answer: they re-read GET /api/appearance,
    # which carries these values (animal.patch), and repaint every face.
    try:
        publish("appearance", {"part": "animal", "animal": now})
    except Exception:
        pass
    said = "Done - " + (s.on_said if on else s.off_said) + "."
    return 200, {"ok": True, "said": said, "changed": True, "view": view()}


def handle_post(body) -> tuple:
    """POST /api/animal with ONE change: {"<switch id>": true|false}."""
    if not isinstance(body, dict) or len(body) != 1:
        return 400, {"ok": False, "error": "Send one change at a time."}
    (k, v), = body.items()
    return set_switch(k, v)


def handle_get() -> tuple:
    return 200, view()


# --------------------------------------------------------------------------
#   Spoken names (jarvis_settings_registry.find_animal_switch reads these)
# --------------------------------------------------------------------------

_ARTICLE = re.compile(r"^(?:the|my|a|an)\s+")


def _bare(words: str) -> str:
    return _ARTICLE.sub("", " ".join(str(words or "").lower().split()))


def find_switch(words: str) -> Optional[str]:
    """The one switch `words` names exactly, or None - never a guess."""
    bare = _bare(words)
    if not bare:
        return None
    for s in SWITCHES:
        if bare == _bare(s.id.replace("_", " ")) or any(bare == _bare(n) for n in s.names):
            return s.id
    return None


def switch(key: str) -> Optional[Switch]:
    return _BY_ID.get(key)


# --------------------------------------------------------------------------
#   The route both apps call
# --------------------------------------------------------------------------

def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so /api/animal is answered
    here, after the server's own origin and token checks. Every other
    request goes straight to the original."""
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_animal", False):
        return "  animal     Animal options (already on)"

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
        if route != PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get()
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        try:
            code, out = handle_post(body)
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_animal = True
    do_POST._jarvis_animal = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    v = values()
    on = [s.label for s in SWITCHES if v[s.id]]
    return "  animal     Animal options: " + (", ".join(on) if on else "all off")
