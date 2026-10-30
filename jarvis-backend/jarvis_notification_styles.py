"""jarvis_notification_styles.py - "Notification styles you describe" (2026-10-30).

The owner asked, 2026-10-30: *"does jarvis android have custom animated
notifications? if not can you build this feature into it? i want them
customizable and buildable by just chatting to jarvis"*.

The answer this module ships is the only one Android allows: a CLOSED STYLE
SPEC the owner describes in their own words, which the PC's local model turns
into JSON on a fixed menu, which plain code here checks, and which the phone
then draws inside its own notification. **Never code, never HTML, never a
layout, never a colour value, never an intent.** The model picks from lists;
the phone owns what each name draws.

Why the menu is the whole safety story: a RemoteViews notification layout is
inflated by SystemUI in ANOTHER process, and Android's allow-list there is a
short list of classes (see the research note, and RemoteViews' own javadoc).
So "the owner writes their own notification design" is not a thing Android
can do - not for Jarvis and not for any app - and the closed menu is not a
limitation somebody imposed on the feature, it is the shape of the platform.

What a style is (every key is required, nothing else may appear):

    name    plain words, 1..MAX_NAME, no web address
    theme   "ice" | "azure" | "indigo" | "ember" | "rose" | "mono"
    figure  "spark" | "redpanda" | "pygmyowl" | "seaotter" | "monkey"
            | "robot" | "dot" | "none"        (the faces this app already has)
    motion  "none" | "pulse" | "flip" | "spinner"
    speed   "slow" | "normal" | "fast"
    kinds   one or two of "approval" | "reminder"

The phone draws:
  - theme as the accent colour of a glyph and a thin bar (values live in the
    APP, keyed by name - the PC can never send a colour);
  - figure as one glyph from a fixed list;
  - motion as a stock Android animation that SystemUI itself runs: a
    ViewFlipper over two RemoteViews frames ("pulse" = the glyph dimming and
    brightening, "flip" = the glyph swapping), or an indeterminate
    ProgressBar ("spinner"), or nothing. **No frame is posted by this app**,
    so the animation keeps running when Jarvis' process is dead and costs no
    wakeups. That is the proof the owner's phone will show something real;
    the research note carries the citations.

PRIVACY FLOOR, and it is structural rather than a promise:
  - the PC stores only the six values above. There is nowhere in the spec to
    put an email, a saved fact, a file, a person or a token;
  - the phone passes the layout the SAME title and body the notifier already
    had, already redacted by that notifier's own rule;
  - when App lock, "Hide memory lists and chat history" or a phone with no
    secure lock screen is in force, the phone does NOT use the custom layout
    at all - it falls back to exactly today's notification. Redaction is not
    re-implemented in the pretty layout, so it cannot be forgotten there;
  - an approval card still offers Deny only, still opens the Inbox, and is
    still never approvable from a notification: this module only changes
    which layout draws the words.

No approval card, deliberately: a style shows nothing new, adds no button,
grants no capability, and nothing is applied until the owner taps Add on the
phone (the same shape as "Widgets you describe", JARVIS-API section 86). See
`NO_CARD`.

Routes, installed by jarvis_brain_reads.install() beside jarvis_widgets:
    GET  /api/notification-styles            the saved styles + what is live
    POST /api/notification-styles/draft      the owner's words -> a preview
    POST /api/notification-styles/add        keep ONE preview, exactly as shown
    POST /api/notification-styles/discard    drop ONE preview
    POST /api/notification-styles/delete     delete ONE saved style

Chat: "make my Jarvis notifications look like X" (jarvis_quick.py) makes a
PREVIEW only, from the owner's own typed or spoken words, and is refused in a
conversation that has read outside text (jarvis_widgets.chat_tainted - the
same taint rule, reused rather than re-invented).
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
import unicodedata
from pathlib import Path
from typing import Callable, Optional

# --------------------------------------------------------------------------
#   The menu
# --------------------------------------------------------------------------

LIST_PATH = "/api/notification-styles"
DRAFT_PATH = "/api/notification-styles/draft"
ADD_PATH = "/api/notification-styles/add"
DISCARD_PATH = "/api/notification-styles/discard"
DELETE_PATH = "/api/notification-styles/delete"
GET_PATHS = (LIST_PATH,)
POST_PATHS = (DRAFT_PATH, ADD_PATH, DISCARD_PATH, DELETE_PATH)

MAX_STYLES = 8
MAX_DRAFTS = 5
MAX_NAME = 40
MAX_WORDS = 300
MAX_RAW = 2000
DRAFT_TTL = 30 * 60.0
MODEL_TIMEOUT = 40.0

THEMES = ("ice", "azure", "indigo", "ember", "rose", "mono")
#: A figure is ONE character from a fixed list, drawn in a TextView inside the
#: notification. Never the owner's real face: those are GL/Compose drawings,
#: and RemoteViews refuses every View class it does not know, so the real face
#: cannot be inflated in a notification at all (see the research note).
FIGURES = ("spark", "ring", "dot", "star", "arrow", "none")
MOTIONS = ("none", "pulse", "flip", "spinner")
SPEEDS = ("slow", "normal", "fast")
KINDS = ("approval", "reminder")

#: Every key a style may have, and every one it must have. Anything else,
#: and the style - so the whole preview - is refused.
STYLE_KEYS = ("name", "theme", "figure", "motion", "speed", "kinds")
REQUIRED = STYLE_KEYS

#: What each choice means, in the owner's words. Used by the prompt, the
#: preview and the docs - one place, so they cannot drift apart.
THEME_WORDS = {
    "ice": "cool blue-white",
    "azure": "bright blue",
    "indigo": "deep violet-blue",
    "ember": "warm orange",
    "rose": "warm pink",
    "mono": "grey",
}
FIGURE_WORDS = {
    "spark": "a spark",
    "ring": "a ring",
    "dot": "a dot",
    "star": "a star",
    "arrow": "an arrow",
    "none": "no figure",
}
MOTION_WORDS = {
    "none": "still (no animation)",
    "pulse": "pulsing (two frames at the speed below)",
    "flip": "flipping between two frames at the speed below",
    "spinner": "a small spinner",
}
SPEED_WORDS = {
    "slow": "slowly",
    "normal": "at normal speed",
    "fast": "quickly",
}
KIND_WORDS = {
    "approval": "approval cards",
    "reminder": "reminders and timers",
}

# --------------------------------------------------------------------------
#   The owner's words back, plainly
# --------------------------------------------------------------------------

NO_CARD = (
    "No approval card: a style changes only how your own notifications look. It shows "
    "nothing new, adds no button and grants nothing, and nothing is applied until you tap Add."
)
NOT_OWN_WORDS = (
    "Styles are made only from your own typed or spoken words - not from pasted or shared text."
)
TAINTED = (
    "This chat has read outside text (an email, a web page, a file or a pasted message), so "
    "Jarvis will not make a style from it. Start a new chat, or describe the style in Brain, "
    "Notifications."
)
NO_WORDS = (
    "Say how the notifications should look - for example, \"warm orange, the sea otter, "
    "pulsing, for reminders\"."
)
TOO_LONG = f"That is too long for a style. Keep it under {MAX_WORDS} characters."
COULD_NOT = (
    "Jarvis could not turn that into a style. Try naming a colour, a face and an animation, "
    "like \"cool blue, the pygmy owl, a small spinner, for approvals\"."
)
NO_MODEL = "The AI model on your PC is not available right now, so no style was made. Try again soon."
TOO_MANY = (
    f"You already have {MAX_STYLES} styles. Delete one in Settings, Notifications from Jarvis before adding "
    "another."
)
DRAFT_GONE = "That preview has expired or was already used. Describe the style again."
NO_SUCH = "That style is not there any more."
PREVIEW_HINT = (
    "See the preview in Settings, Notifications from Jarvis and tap Add - nothing changes until you do."
)
OFFER_ADD = "Add it there to use it."
NOTHING_ON = "No style is live - notifications look the way they always did."

# --------------------------------------------------------------------------
#   Cleaning text: plain words only
# --------------------------------------------------------------------------

_URL = re.compile(
    r"(?i)\b[a-z][a-z0-9+.-]{1,20}:/"
    r"|\b(?:javascript|data|vbscript|file|mailto|intent|content)\s*:"
    r"|\bwww\."
    r"|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,24}/"
    r"|\b[a-z0-9-]+\.(?:com|net|org|io|ai|app|dev|co|xyz|ru|cn|info|biz|me|ly|gg|tk|top)\b"
)


class Refused(ValueError):
    """The description is not on the menu. str() is the reason, in words."""


def clean_text(value, cap: int, what: str) -> str:
    """Plain words: control, invisible and direction-changing characters are
    dropped, spaces collapsed, at most `cap` characters. A web address is
    refused, not cleaned - nothing here ever links anywhere."""
    if not isinstance(value, str):
        raise Refused(f"{what} is not text")
    if len(value) > cap * 8:
        raise Refused(f"{what} is far too long")
    out = []
    for ch in value:
        cat = unicodedata.category(ch)
        if cat in ("Zl", "Zp") or ch in "\t\r\n":
            out.append(" ")
        elif cat[0] == "C":
            continue
        elif ch in "<>{}`\\":
            continue
        else:
            out.append(ch)
    s = " ".join("".join(out).split())
    if _URL.search(s):
        raise Refused(f"{what} has a web address in it")
    if len(s) > cap:
        s = s[:cap].rstrip()
    return s


# --------------------------------------------------------------------------
#   Checking a description
# --------------------------------------------------------------------------

def _no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise Refused(f"the key {k!r} is there twice")
        out[k] = v
    return out


def _no_constants(name):
    raise Refused(f"{name} is not a value a style can use")


def loads(raw) -> object:
    """JSON, strictly: at most MAX_RAW characters, no repeated key, no NaN or
    Infinity, no prose around it. Raises Refused."""
    if not isinstance(raw, str):
        raise Refused("the answer is not text")
    if len(raw) > MAX_RAW:
        raise Refused("the answer is too long")
    try:
        return json.loads(raw, object_pairs_hook=_no_duplicates, parse_constant=_no_constants)
    except Refused:
        raise
    except (ValueError, RecursionError) as exc:
        raise Refused(f"the answer is not JSON ({type(exc).__name__})")


def _choice(obj: dict, key: str, allowed: tuple) -> str:
    got = obj.get(key)
    if not isinstance(got, str) or got not in allowed:
        raise Refused(f"\"{key}\" is not one of the choices a style has")
    return got


def validate(obj) -> dict:
    """The one checked, cleaned style, or Refused. Plain code: nothing here
    calls a model, opens a file or a socket."""
    if not isinstance(obj, dict):
        raise Refused("the answer is not a style")
    extra = sorted(set(map(str, obj)) - set(STYLE_KEYS))
    if extra:
        raise Refused(f"the style has something a style cannot have ({', '.join(extra)[:60]})")
    missing = [k for k in REQUIRED if k not in obj]
    if missing:
        raise Refused(f"the style is missing {', '.join(missing)}")
    name = clean_text(obj["name"], MAX_NAME, "the name")
    if not name:
        raise Refused("the style has no name")
    kinds = obj["kinds"]
    if not isinstance(kinds, list) or not kinds:
        raise Refused("the style says which notifications it is for")
    if len(kinds) > 8:
        raise Refused("a style is for at most two kinds of notification")
    out_kinds = []
    for k in kinds:
        if not isinstance(k, str) or k not in KINDS:
            raise Refused("a style is only for approvals or for reminders")
        if k not in out_kinds:
            out_kinds.append(k)
    if not out_kinds:
        raise Refused("the style says which notifications it is for")
    return {
        "name": name,
        "theme": _choice(obj, "theme", THEMES),
        "figure": _choice(obj, "figure", FIGURES),
        "motion": _choice(obj, "motion", MOTIONS),
        "speed": _choice(obj, "speed", SPEEDS),
        "kinds": out_kinds,
    }


def parse_model(raw) -> dict:
    """The model's answer -> a checked style, or Refused."""
    return validate(loads(raw))


def describe(style: dict) -> str:
    """One plain sentence about a checked style, for the preview and chat."""
    body = (
        f"{THEME_WORDS[style['theme']]}, {FIGURE_WORDS[style['figure']]}, "
        f"{MOTION_WORDS[style['motion']]}"
    )
    if style["motion"] != "none":
        body += f" {SPEED_WORDS[style['speed']]}"
    who = " and ".join(KIND_WORDS[k] for k in style["kinds"])
    return f"A style called \u201c{style['name']}\u201d: {body}, for {who}."


def parts(style: dict) -> list:
    """One plain line per choice, in order - the preview both apps show under
    the sentence, before Add."""
    return [
        f"Colour: {THEME_WORDS[style['theme']]}",
        f"Figure: {FIGURE_WORDS[style['figure']]}",
        f"Animation: {MOTION_WORDS[style['motion']]}",
        f"Speed: {SPEED_WORDS[style['speed']]}",
        "For: " + " and ".join(KIND_WORDS[k] for k in style["kinds"]),
    ]


def with_words(style: dict) -> dict:
    """A style or draft as the apps list it: with its sentence and parts."""
    return dict(style, said=describe(style), parts=parts(style))


def resolve(styles: list) -> dict:
    """Which saved style is LIVE for each kind: the newest one that claims it.

    Deterministic on purpose - two styles may name the same kind, and the
    answer has to be the same one every time it is asked, on every device.
    """
    out = {}
    for s in styles:
        for k in s.get("kinds") or []:
            out[k] = s
    return out


# --------------------------------------------------------------------------
#   The model: the owner's words -> JSON on the menu
# --------------------------------------------------------------------------

#: Ollama's structured output: the style's shape, with every choice an enum.
SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "maxLength": MAX_NAME},
        "theme": {"type": "string", "enum": list(THEMES)},
        "figure": {"type": "string", "enum": list(FIGURES)},
        "motion": {"type": "string", "enum": list(MOTIONS)},
        "speed": {"type": "string", "enum": list(SPEEDS)},
        "kinds": {
            "type": "array", "minItems": 1, "maxItems": len(KINDS),
            "items": {"type": "string", "enum": list(KINDS)},
        },
    },
    "required": list(STYLE_KEYS),
    "additionalProperties": False,
}


def prompt(words: str) -> str:
    themes = "\n".join(f'  - "{k}": {v}' for k, v in THEME_WORDS.items())
    figures = "\n".join(f'  - "{k}": {v}' for k, v in FIGURE_WORDS.items())
    motions = "\n".join(f'  - "{k}": {v}' for k, v in MOTION_WORDS.items())
    speeds = "\n".join(f'  - "{k}": {v}' for k, v in SPEED_WORDS.items())
    kinds = "\n".join(f'  - "{k}": {v}' for k, v in KIND_WORDS.items())
    return (
        "Turn the owner's request into a notification style in JSON. Use ONLY these choices, "
        "and give every field.\n"
        f"Colours:\n{themes}\n"
        f"Figures:\n{figures}\n"
        f"Animations:\n{motions}\n"
        f"Speeds:\n{speeds}\n"
        f"Which notifications it is for (one or two):\n{kinds}\n"
        f"Give it a short name of your own in plain words (at most {MAX_NAME} characters). "
        "If the request asks for something not on these lists - a photo, a colour value, a "
        "font, a sound, a web page, code - leave it out and choose the closest choice above.\n"
        'Answer only JSON: {"name": "...", "theme": "...", "figure": "...", "motion": "...", '
        '"speed": "...", "kinds": ["..."]}.\n\n'
        f"The owner's request: {words}"
    )


def _learner_model() -> tuple:
    try:
        import jarvis_sensitive
        return jarvis_sensitive.learner_model()
    except Exception:
        return (None, None)


def _local_check(url, model) -> str:
    try:
        import jarvis_auto_learn
        return jarvis_auto_learn.check_local_model(url, model)
    except Exception:
        return "the local-model check could not run"


def ollama_caller(url: str, model: str, timeout: float = MODEL_TIMEOUT) -> Callable:
    """ask(prompt) -> text or None, from THIS PC's Ollama, never through a
    proxy (jarvis_local_http). jarvis_widgets.ollama_caller's shape."""
    def ask(text: str) -> Optional[str]:
        import urllib.error
        import urllib.request
        body = {"model": model, "prompt": text, "stream": False, "format": SCHEMA,
                "think": False, "options": {"temperature": 0, "num_predict": 250}}
        for attempt in (1, 2):
            req = urllib.request.Request(
                str(url).rstrip("/") + "/api/generate",
                data=json.dumps(body).encode("utf-8"), method="POST",
                headers={"Content-Type": "application/json"})
            try:
                try:
                    import jarvis_local_http
                    resp = jarvis_local_http.urlopen(req, timeout)
                except ImportError:
                    resp = urllib.request.build_opener(
                        urllib.request.ProxyHandler({})).open(req, timeout=timeout)
                with resp as r:
                    out = json.loads(r.read(MAX_RAW * 4).decode("utf-8") or "{}")
            except urllib.error.HTTPError as exc:
                if attempt == 1 and exc.code == 400 and "think" in body:
                    body.pop("think", None)
                    continue
                return None
            except Exception:
                return None
            got = out.get("response") if isinstance(out, dict) else None
            return got if isinstance(got, str) else None
        return None
    return ask


def default_ask() -> tuple:
    """(ask, None) for this PC's own model, or (None, why) when there is none
    on this PC to ask."""
    url, model = _learner_model()
    if not url or not model:
        return None, "no model"
    why = _local_check(url, model)
    if why:
        return None, why
    return ollama_caller(url, model), None


# --------------------------------------------------------------------------
#   The store
# --------------------------------------------------------------------------

_ID = re.compile(r"s[0-9a-f]{10}")
_DRAFT_ID = re.compile(r"d[0-9a-f]{10}")


def _config_dir() -> Path:
    try:
        import jarvis_schedule
        return jarvis_schedule._config_dir()
    except Exception:
        env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
        if env:
            return Path(os.path.expanduser(env))
        return Path(os.path.expanduser("~")) / ".openjarvis"


def store_path() -> Path:
    env = os.environ.get("JARVIS_NOTIFICATION_STYLES_FILE")
    return Path(env) if env else _config_dir() / "notification_styles.json"


class Store:
    """The saved styles (a JSON file) and the drafts (memory only)."""

    def __init__(self, path: Optional[Path] = None, clock: Callable[[], float] = time.time):
        self.path = Path(path) if path is not None else None
        self.clock = clock
        self._lock = threading.Lock()
        self._drafts: dict = {}

    def _file(self) -> Path:
        return self.path if self.path is not None else store_path()

    # -- styles ----------------------------------------------------------------
    def _read(self) -> list:
        p = self._file()
        try:
            if not p.exists() or p.stat().st_size > 128 * 1024:
                return []
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
        rows = data.get("styles") if isinstance(data, dict) else None
        out = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) \
                    or not _ID.fullmatch(row["id"]):
                continue
            try:
                # checked again on every read: a hand edit smuggles nothing
                s = validate({k: row.get(k) for k in STYLE_KEYS})
            except Refused:
                continue
            created = row.get("created")
            s = {"id": row["id"], **s,
                 "created": float(created) if isinstance(created, (int, float))
                 and not isinstance(created, bool) else 0.0}
            out.append(s)
            if len(out) >= MAX_STYLES:
                break
        return out

    def _write(self, rows: list) -> None:
        p = self._file()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({"version": 1, "styles": rows}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, p)

    def styles(self) -> list:
        with self._lock:
            return self._read()

    def get(self, sid) -> Optional[dict]:
        if not isinstance(sid, str) or not _ID.fullmatch(sid):
            return None
        return next((s for s in self.styles() if s["id"] == sid), None)

    def delete(self, sid) -> bool:
        if not isinstance(sid, str) or not _ID.fullmatch(sid):
            return False
        with self._lock:
            rows = self._read()
            keep = [s for s in rows if s["id"] != sid]
            if len(keep) == len(rows):
                return False
            self._write(keep)
            return True

    # -- drafts ----------------------------------------------------------------
    def _prune(self) -> None:
        now = self.clock()
        for k in [k for k, d in self._drafts.items() if d["expires"] <= now]:
            del self._drafts[k]

    def add_draft(self, style: dict) -> dict:
        with self._lock:
            self._prune()
            while len(self._drafts) >= MAX_DRAFTS:
                oldest = min(self._drafts, key=lambda k: self._drafts[k]["expires"])
                del self._drafts[oldest]
            did = "d" + secrets.token_hex(5)
            d = {"id": did, **style, "expires": self.clock() + DRAFT_TTL}
            self._drafts[did] = d
            return dict(d)

    def drafts(self) -> list:
        with self._lock:
            self._prune()
            return sorted((dict(d) for d in self._drafts.values()), key=lambda d: d["expires"])

    def discard(self, did) -> bool:
        with self._lock:
            return self._drafts.pop(did, None) is not None if isinstance(did, str) else False

    def keep(self, did) -> tuple:
        """(style, None) - the draft, exactly as previewed, now saved - or
        (None, why)."""
        if not isinstance(did, str) or not _DRAFT_ID.fullmatch(did):
            return None, DRAFT_GONE
        with self._lock:
            self._prune()
            d = self._drafts.get(did)
            if d is None:
                return None, DRAFT_GONE
            rows = self._read()
            if len(rows) >= MAX_STYLES:
                return None, TOO_MANY
            s = {"id": "s" + secrets.token_hex(5),
                 **{k: d[k] for k in STYLE_KEYS}, "created": self.clock()}
            self._write(rows + [s])
            del self._drafts[did]
            return s, None


_STORE: Optional[Store] = None
_STORE_LOCK = threading.Lock()


def store() -> Store:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = Store()
        return _STORE


# --------------------------------------------------------------------------
#   Making a draft
# --------------------------------------------------------------------------

OWN_WORDS = ("typed", "voice")


def draft(words, *, provenance, tainted: bool = False, ask: Optional[Callable] = None,
          st: Optional[Store] = None) -> tuple:
    """(http status, answer). The owner's words -> a checked draft, held in
    memory for the preview. Nothing is saved here."""
    if provenance not in OWN_WORDS:
        return 400, {"ok": False, "error": NOT_OWN_WORDS}
    if tainted:
        return 409, {"ok": False, "error": TAINTED}
    if not isinstance(words, str) or not words.strip():
        return 400, {"ok": False, "error": NO_WORDS}
    if len(words) > MAX_WORDS:
        return 400, {"ok": False, "error": TOO_LONG}
    words = " ".join(words.split())
    if ask is None:
        ask, why = default_ask()
        if ask is None:
            return 503, {"ok": False, "error": NO_MODEL}
    try:
        raw = ask(prompt(words))
    except Exception:
        raw = None
    if raw is None:
        return 503, {"ok": False, "error": NO_MODEL}
    try:
        style = parse_model(raw)
    except Refused as exc:
        return 422, {"ok": False, "error": COULD_NOT, "why": str(exc)}
    d = (st or store()).add_draft(style)
    return 200, {"ok": True, "draft": with_words(d),
                 "said": describe(style) + " " + PREVIEW_HINT,
                 "card": False, "no_card": NO_CARD}


# --------------------------------------------------------------------------
#   The list the phone draws
# --------------------------------------------------------------------------

def menu() -> dict:
    return {"themes": [{"id": k, "label": v} for k, v in THEME_WORDS.items()],
            "figures": [{"id": k, "label": v} for k, v in FIGURE_WORDS.items()],
            "motions": [{"id": k, "label": v} for k, v in MOTION_WORDS.items()],
            "speeds": [{"id": k, "label": v} for k, v in SPEED_WORDS.items()],
            "kinds": [{"id": k, "label": v} for k, v in KIND_WORDS.items()],
            "limits": {"styles": MAX_STYLES, "words": MAX_WORDS, "name": MAX_NAME}}


def listing(st: Optional[Store] = None) -> dict:
    st = st or store()
    styles = st.styles()
    live = resolve(styles)
    return {"ok": True,
            "styles": [with_words(s) for s in styles],
            "drafts": [with_words(d) for d in st.drafts()],
            "active": {k: with_words(v) for k, v in live.items()},
            "live": sorted(live),
            "nothing_on": NOTHING_ON,
            "no_card": NO_CARD, **menu()}


# --------------------------------------------------------------------------
#   Routes
# --------------------------------------------------------------------------

def handle_get(path: str, query: str = "", *, st: Optional[Store] = None) -> tuple:
    if path == LIST_PATH:
        return 200, listing(st)
    return 404, {"error": "no such route"}


def handle_post(path: str, body, *, st: Optional[Store] = None,
                ask: Optional[Callable] = None) -> tuple:
    st = st or store()
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    if path == DRAFT_PATH:
        # The apps' own "Describe a style" box: no conversation, so nothing in
        # it can have read outside text; pasted words are refused by provenance.
        return draft(body.get("words"), provenance=body.get("provenance"), ask=ask, st=st)
    if path == ADD_PATH:
        s, why = st.keep(body.get("draft"))
        if s is None:
            return (409 if why == TOO_MANY else 404), {"ok": False, "error": why}
        return 200, {"ok": True, "style": with_words(s),
                     "said": f"Added \u201c{s['name']}\u201d. " + OFFER_ADD,
                     "active": {k: with_words(v) for k, v in resolve(st.styles()).items()}}
    if path == DISCARD_PATH:
        st.discard(body.get("draft"))
        return 200, {"ok": True}
    if path == DELETE_PATH:
        if not st.delete(body.get("id")):
            return 404, {"ok": False, "error": NO_SUCH}
        return 200, {"ok": True, "said": "Style deleted.",
                     "active": {k: with_words(v) for k, v in resolve(st.styles()).items()}}
    return 404, {"error": "no such route"}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so the style routes are
    answered here, after the server's own origin and token checks; every
    other request goes straight to the original, untouched."""
    if handler_cls.__dict__.get("_jarvis_notification_styles_on"):
        return "  notifstyle Notification styles you describe (already on)"
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST

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
        from urllib.parse import urlsplit
        parsed = urlsplit(str(getattr(self, "path", "") or ""))
        route = parsed.path.rstrip("/")
        if route not in GET_PATHS:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route, parsed.query)
        except Exception as exc:
            code, out = 500, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        from urllib.parse import urlsplit
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in POST_PATHS:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            raw = read_body(self) or b"{}"
            if len(raw) > 8 * 1024:
                return self._send(413, {"ok": False, "error": "too big"})
            body = json.loads(raw)
        except Exception as exc:
            return self._send(400, {"ok": False, "error": type(exc).__name__})
        try:
            code, out = handle_post(route, body)
        except Exception as exc:
            code, out = 500, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    handler_cls._jarvis_notification_styles_on = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return "  notifstyle Notification styles you describe: on"


# --------------------------------------------------------------------------
#   Chat: "make my Jarvis notifications look like ..." (jarvis_quick.py)
# --------------------------------------------------------------------------

def chat_tainted(conversation, messages) -> bool:
    """Has this conversation read outside text? jarvis_widgets' answer, reused
    rather than re-invented - one taint rule for everything the owner's words
    make."""
    try:
        import jarvis_widgets
        return bool(jarvis_widgets.chat_tainted(conversation, messages))
    except Exception:
        if not isinstance(messages, list):
            return True
        turns = [m for m in messages if isinstance(m, dict)
                 and m.get("role") in ("user", "assistant", "tool")]
        return len(turns) > 1 or any(m.get("role") != "user" for m in turns)


def from_chat(words: str, *, conversation=None, messages=None, ask: Optional[Callable] = None,
              st: Optional[Store] = None) -> str:
    """jarvis_quick's reply for "make my notifications look like ..."."""
    tainted = chat_tainted(conversation, messages)
    code, out = draft(words, provenance="typed", tainted=tainted, ask=ask, st=st)
    if code == 200:
        return "Made a style preview. " + out["said"]
    return str(out.get("error") or COULD_NOT)
