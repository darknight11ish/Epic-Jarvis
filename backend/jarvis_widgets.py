"""jarvis_widgets.py - "Widgets you describe" (the owner's choice of 2026-09-28, the SAFE version).

docs/JARVIS-API.md section 86 is the contract.

The owner says what a small widget should show - "make me a widget showing
my next 3 reminders and a 10-minute timer button" - and Jarvis turns those
words into a SMALL DESCRIPTION, never into code. The description is JSON
from a fixed menu:

    {"name": "Morning",
     "blocks": [{"type": "title",    "text": "Morning"},
                {"type": "number",   "source": "todo_count", "label": "To do"},
                {"type": "list",     "source": "reminders", "max": 3},
                {"type": "progress", "source": "disk_free"},
                {"type": "button",   "action": "timer"}]}

WHAT THE AI MODEL DOES, AND WHAT IT CANNOT DO
The model is used for ONE thing: turning the owner's own words into that
JSON. It is asked through Ollama's structured output (the `format` schema
below), on this PC only, with the owner's words and the menu - nothing else:
no memory, no email, no web page, no earlier chat. Then this module checks
what came back with plain code (`validate`), and throws it away unless it is
exactly a thing on the menu:

  - only five block types; every block has exactly its own keys, no more;
  - data comes only from SOURCES, a fixed list of things both apps already
    read (the next reminders, the timers, the Today cards, the to-do list,
    counts from today's briefing, the free disk space, the focus session,
    what is playing on the PC). Never an email's text or sender, never a
    saved fact, never a web page;
  - a button is only one of ACTIONS - the SAME five as the phone's Quick
    Settings tiles (data/QuickTiles.kt): start a focus session, a 10-minute
    timer, Brief me (opens the app), Stop everything, play/pause on the PC.
    Never Approve or Deny, never anything that clears a rush latch or acts on
    several things at once, never a free-form action. A button's words are
    fixed here per action - the model cannot label a timer button "Approve";
  - no code, HTML, CSS, script, web address or styling: text is cleaned
    (control and invisible characters and < > { } ` \\ removed) and a text
    with a web address in it is refused; there are no colour, size or style
    keys to set;
  - sizes are capped: at most MAX_BLOCKS blocks, MAX_BUTTONS buttons, a list
    of at most MAX_LIST items, short texts, and the model's whole answer at
    most MAX_RAW characters.

NO APPROVAL CARD, AND WHY
A widget only SHOWS things both apps already show, and its buttons are only
the tile actions, each of which is already one tap with no card (a plain
timer, a focus session, Brief me, Stop everything, play/pause). Nothing is
added until the owner has seen the preview and tapped Add. Delete is
immediate. So there is no card: a card would ask the same question the Add
button already asks, about something that cannot make Jarvis do more.

ONLY THE OWNER'S OWN WORDS
`draft()` takes `provenance`: only "typed" and "voice" (the owner's own
words, ARCHITECTURE section 3) are used. In chat, a conversation that has
read outside text (an email, a web page, a file, a pasted message) is
refused with a plain sentence (`TAINTED`) - jarvis_quick.py asks
jarvis_chat_log before calling here. The words themselves are never kept:
a draft holds only the checked description.

WHERE IT IS KEPT
Drafts: in this process's memory only, at most MAX_DRAFTS, each for
DRAFT_TTL seconds. Widgets: `widgets.json` in the same folder as the
settings and schedule.db (at most MAX_WIDGETS), written whole and replaced
atomically. Not the scheduler's database: a widget is not a job - it has no
time and never goes off - and the scheduler's rows are timers and reminders
with their own limits and events. Every widget read back from the file is
checked again by `validate`, so a hand-edited file cannot smuggle anything
in either.

WHAT A WIDGET SHOWS
`show(id)` reads each block's source NOW, on this PC, and answers plain
strings and numbers. Blocks whose source holds the owner's own words or
another program's words (reminders, timers, Today cards, to-do items, what
is playing) are marked `"private": true`; both apps hide those words while
App lock or "Hide memory lists and chat history" is on (the phone's home
screen is as public as a lock screen). Counts, the disk and the focus
countdown are not private. Nothing here reaches the AI model: `show` is a
read for the apps only, and no tool offers it.

ROUTES (wrapped round the server's Handler by widgets.patch, behind the
token and origin checks like every route):

    GET  /api/widgets                 the saved widgets, the drafts, the menu
    GET  /api/widgets/show?id=w...    one widget, its blocks filled in now
    POST /api/widgets/draft {"words", "provenance"}   make a draft (the model)
    POST /api/widgets/add {"draft"}   keep a draft, exactly as previewed
    POST /api/widgets/discard {"draft"}
    POST /api/widgets/delete {"id"}   immediate
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import threading
import time
import unicodedata
from pathlib import Path
from typing import Callable, Optional

# --------------------------------------------------------------------------
#   The menu
# --------------------------------------------------------------------------

LIST_PATH = "/api/widgets"
SHOW_PATH = "/api/widgets/show"
DRAFT_PATH = "/api/widgets/draft"
ADD_PATH = "/api/widgets/add"
DISCARD_PATH = "/api/widgets/discard"
DELETE_PATH = "/api/widgets/delete"
GET_PATHS = (LIST_PATH, SHOW_PATH)
POST_PATHS = (DRAFT_PATH, ADD_PATH, DISCARD_PATH, DELETE_PATH)

MAX_BLOCKS = 8
MAX_BUTTONS = 4
MAX_LIST = 5
MAX_NAME = 40
MAX_TEXT = 60
MAX_LABEL = 40
MAX_RAW = 6000
MAX_WORDS = 300
MAX_WIDGETS = 12
MAX_DRAFTS = 5
DRAFT_TTL = 30 * 60.0
MODEL_TIMEOUT = 40.0

BLOCK_TYPES = ("title", "number", "list", "progress", "button")

#: Every key each block type may have. Anything else and the block - and so
#: the whole widget - is refused.
BLOCK_KEYS = {
    "title": ("type", "text"),
    "number": ("type", "source", "label"),
    "list": ("type", "source", "label", "max"),
    "progress": ("type", "source", "label"),
    "button": ("type", "action"),
}
REQUIRED = {
    "title": ("text",),
    "number": ("source",),
    "list": ("source",),
    "progress": ("source",),
    "button": ("action",),
}
TOP_KEYS = ("name", "blocks")
#: Every key any block may have. A key outside this is refused outright.
ALL_KEYS = tuple(sorted({k for keys in BLOCK_KEYS.values() for k in keys}))


class Source:
    def __init__(self, block: str, label: str, private: bool, describe: str, empty: str = ""):
        self.block = block          # the one block type it fills
        self.label = label          # its default label
        self.private = private      # holds the owner's (or a program's) own words
        self.describe = describe    # for the preview sentence and the prompt
        self.empty = empty          # a list's words when there is nothing


#: The fixed list of things a widget may show. Each is something the apps
#: already read (Coming up, Today, the briefing, PC help, Focus, "Playing on
#: your PC"). NEVER an email's text or sender, a saved fact or a web page.
SOURCES = {
    "reminders": Source("list", "Coming up", True, "your next reminders and alarms",
                        "Nothing coming up."),
    "timers": Source("list", "Timers", True, "your running timers", "No timer running."),
    "today": Source("list", "Today", True, "your Today cards showing now",
                    "No Today cards showing."),
    "todo": Source("list", "To do", True, "your to-do list", "Your to-do list is empty."),
    "now_playing": Source("list", "Playing on your PC", True, "what is playing on your PC",
                          "Nothing playing."),
    "reminders_count": Source("number", "Reminders left today", False,
                              "how many reminders and alarms are left today"),
    "todo_count": Source("number", "To do", False, "how many things are on your to-do list"),
    "email_count": Source("number", "Unread email", False,
                          "how many unread emails today's briefing found (never who from)"),
    "events_count": Source("number", "Events today", False,
                           "how many calendar events today's briefing found (never their titles)"),
    "disk_free": Source("progress", "Disk free", False, "the free space on your PC's main drive"),
    "focus": Source("progress", "Focus session", False, "the time left in a focus session"),
}

#: The buttons: the phone's Quick Settings tile actions (data/QuickTiles.kt
#: TileAction), the same wire names, the same words. The words are fixed
#: here: the model chooses WHICH button, never what it says.
ACTIONS = {
    "focus": "Focus session",
    "timer": "10-min timer",
    "brief_me": "Brief me",
    "stop_everything": "Stop everything",
    "pc_play_pause": "Play/pause PC",
}

# --------------------------------------------------------------------------
#   The owner's words back, plainly
# --------------------------------------------------------------------------

NO_CARD = ("No approval card: a widget only shows what Jarvis already shows you, and its "
           "buttons are the small one-tap actions (a 10-minute timer, a focus session, Brief "
           "me, Stop everything, play/pause) that never ask. Nothing is added until you tap Add.")
NOT_OWN_WORDS = ("Widgets are made only from your own typed or spoken words - not from pasted "
                 "or shared text.")
TAINTED = ("This chat has read outside text (an email, a web page, a file or a pasted "
           "message), so Jarvis will not make a widget from it. Start a new chat, or describe "
           "the widget under Brain, Widgets.")
NO_WORDS = "Say what the widget should show - for example, your next 3 reminders and a timer button."
TOO_LONG = f"That is too long for a widget. Keep it under {MAX_WORDS} characters."
COULD_NOT = ("Jarvis could not turn that into a widget. Try naming what it should show, like "
             "\"my next 3 reminders and a 10-minute timer button\".")
NO_MODEL = "The AI model on your PC is not available right now, so no widget was made. Try again soon."
TOO_MANY = (f"You already have {MAX_WIDGETS} widgets. Delete one under Brain, Widgets before "
            "adding another.")
DRAFT_GONE = "That preview has expired or was already used. Describe the widget again."
NO_SUCH = "That widget is not there any more."
PREVIEW_HINT = ("See the preview under Brain, Widgets and tap Add - nothing is added until "
                "you do.")
PRIVATE_HIDDEN = "Hidden - open Jarvis to see it."

# --------------------------------------------------------------------------
#   Cleaning text: plain words only
# --------------------------------------------------------------------------

#: Characters dropped from every text: markup and code punctuation.
_STRIP = set("<>{}`\\")
_URL = re.compile(
    r"(?i)\b[a-z][a-z0-9+.-]{1,20}:/"               # scheme://  (http:/, file:/ ...)
    r"|\b(?:javascript|data|vbscript|file|mailto|intent|content)\s*:"
    r"|\bwww\."
    r"|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,24}/"  # host.tld/path
    r"|\b[a-z0-9-]+\.(?:com|net|org|io|ai|app|dev|co|xyz|ru|cn|info|biz|me|ly|gg|tk|top)\b")


class Refused(ValueError):
    """The description is not on the menu. str() is the reason, in words."""


def clean_text(value, cap: int, what: str) -> str:
    """Plain words: control, invisible and direction-changing characters
    and < > { } ` \\ removed, spaces collapsed, at most `cap` characters.
    A web address is refused, not cleaned: nothing in a widget links out."""
    if not isinstance(value, str):
        raise Refused(f"{what} is not text")
    if len(value) > cap * 8:
        raise Refused(f"{what} is far too long")
    out = []
    for ch in value:
        cat = unicodedata.category(ch)
        if cat in ("Zl", "Zp") or ch in "\t\r\n":
            out.append(" ")
        elif cat[0] == "C" or ch in _STRIP:
            continue            # Cc, Cf (bidi, zero-width), Cs, Co, Cn
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
    raise Refused(f"{name} is not a number a widget can use")


def loads(raw) -> object:
    """JSON, strictly: at most MAX_RAW characters, no repeated key, no NaN
    or Infinity. Raises Refused."""
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


def _block(b, i: int) -> dict:
    where = f"part {i + 1}"
    if not isinstance(b, dict):
        raise Refused(f"{where} is not a block")
    kind = b.get("type")
    if not isinstance(kind, str) or kind not in BLOCK_TYPES:
        raise Refused(f"{where} is not one of the block types")
    extra = sorted(map(str, set(b) - set(ALL_KEYS)))
    if extra:
        raise Refused(f"{where} has something no block can have ({', '.join(extra)[:60]})")
    # A key from the menu that belongs to ANOTHER block type (a "label" on a
    # button) is left out, never used: the model's schema offers every key
    # to every block, so this is its commonest slip, and it adds nothing.
    b = {k: v for k, v in b.items() if k in BLOCK_KEYS[kind]}
    missing = [k for k in REQUIRED[kind] if k not in b]
    if missing:
        raise Refused(f"{where} is missing {', '.join(missing)}")
    if kind == "title":
        text = clean_text(b["text"], MAX_TEXT, f"{where}'s text")
        if not text:
            raise Refused(f"{where}'s text is empty")
        return {"type": "title", "text": text}
    if kind == "button":
        action = b["action"]
        if not isinstance(action, str) or action not in ACTIONS:
            raise Refused(f"{where} is not one of the safe buttons")
        return {"type": "button", "action": action}
    source = b["source"]
    if not isinstance(source, str) or source not in SOURCES:
        raise Refused(f"{where} does not show one of the things a widget can show")
    src = SOURCES[source]
    if src.block != kind:
        raise Refused(f"{where}: {source} cannot be shown as a {kind}")
    out = {"type": kind, "source": source}
    label = b.get("label")
    label = src.label if label is None else clean_text(label, MAX_LABEL, f"{where}'s label")
    out["label"] = label or src.label
    if kind == "list":
        n = b.get("max", 3)
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_LIST:
            raise Refused(f"{where}'s number of items must be 1 to {MAX_LIST}")
        out["max"] = n
    return out


def validate(obj) -> dict:
    """The one checked, cleaned widget description, or Refused. Plain code:
    nothing here calls a model, opens a file or a socket."""
    if not isinstance(obj, dict):
        raise Refused("the answer is not a widget")
    extra = sorted(set(obj) - set(TOP_KEYS))
    if extra:
        raise Refused(f"the widget has something a widget cannot have ({', '.join(map(str, extra))[:60]})")
    if "blocks" not in obj or "name" not in obj:
        raise Refused("the widget needs a name and its parts")
    name = clean_text(obj["name"], MAX_NAME, "the name")
    blocks = obj["blocks"]
    if not isinstance(blocks, list) or not blocks:
        raise Refused("the widget has no parts")
    if len(blocks) > MAX_BLOCKS:
        raise Refused(f"a widget has at most {MAX_BLOCKS} parts")
    out, seen_buttons = [], set()
    for i, b in enumerate(blocks):
        got = _block(b, i)
        if got["type"] == "button":
            if got["action"] in seen_buttons:
                continue        # the same button twice: once is enough
            seen_buttons.add(got["action"])
        out.append(got)
    if len(seen_buttons) > MAX_BUTTONS:
        raise Refused(f"a widget has at most {MAX_BUTTONS} buttons")
    if not name:
        first = next((b for b in out if b["type"] == "title"), None)
        name = first["text"][:MAX_NAME] if first else "My widget"
    return {"name": name, "blocks": out}


def parse_model(raw) -> dict:
    """The model's answer -> a checked widget, or Refused."""
    return validate(loads(raw))


def describe(widget: dict) -> str:
    """One plain sentence about a checked widget, for the preview and chat."""
    parts = []
    for b in widget.get("blocks") or []:
        t = b.get("type")
        if t == "title":
            parts.append(f"the heading “{b['text']}”")
        elif t == "button":
            parts.append(f"a {ACTIONS[b['action']]} button")
        elif t == "list":
            src = SOURCES[b["source"]]
            parts.append(f"{src.describe} (up to {b['max']})")
        else:
            parts.append(SOURCES[b["source"]].describe)
    if not parts:
        return f"A widget called “{widget.get('name', '')}”."
    body = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return f"A widget called “{widget.get('name', '')}” showing {body}."


def parts(widget: dict) -> list:
    """One plain line per part, in order - the preview both apps show under
    the sentence, before Add."""
    out = []
    for b in widget.get("blocks") or []:
        t = b.get("type")
        if t == "title":
            out.append(f"Heading: {b['text']}")
        elif t == "button":
            out.append(f"Button: {ACTIONS[b['action']]}")
        elif t == "list":
            out.append(f"List: {b['label']} - {SOURCES[b['source']].describe}, up to {b['max']}")
        elif t == "number":
            out.append(f"Number: {b['label']} - {SOURCES[b['source']].describe}")
        else:
            out.append(f"Bar: {b['label']} - {SOURCES[b['source']].describe}")
    return out


def with_words(w: dict) -> dict:
    """A widget or draft as the apps list it: with its sentence and parts."""
    return dict(w, said=describe(w), parts=parts(w))


# --------------------------------------------------------------------------
#   The model: the owner's words -> JSON on the menu
# --------------------------------------------------------------------------

#: Ollama's structured output: the answer's shape, with every choice an enum.
SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "maxLength": MAX_NAME},
        "blocks": {
            "type": "array", "minItems": 1, "maxItems": MAX_BLOCKS,
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": list(BLOCK_TYPES)},
                    "text": {"type": "string", "maxLength": MAX_TEXT},
                    "source": {"type": "string", "enum": list(SOURCES)},
                    "label": {"type": "string", "maxLength": MAX_LABEL},
                    "max": {"type": "integer", "minimum": 1, "maximum": MAX_LIST},
                    "action": {"type": "string", "enum": list(ACTIONS)},
                },
                "required": ["type"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["name", "blocks"],
    "additionalProperties": False,
}


def prompt(words: str) -> str:
    menu = "\n".join(f'  - "{k}" ({s.block}): {s.describe}' for k, s in SOURCES.items())
    buttons = "\n".join(f'  - "{k}": {v}' for k, v in ACTIONS.items())
    return (
        "Turn the owner's request into a small widget description in JSON. Use ONLY these "
        "parts.\n"
        "Block types:\n"
        '  - {"type": "title", "text": "..."}: a short heading\n'
        '  - {"type": "number", "source": ..., "label": "..."}\n'
        '  - {"type": "list", "source": ..., "label": "...", "max": 1-5}\n'
        '  - {"type": "progress", "source": ..., "label": "..."}\n'
        '  - {"type": "button", "action": ...}\n'
        f"Sources (each only as the block type shown):\n{menu}\n"
        f"Buttons (nothing else can be a button):\n{buttons}\n"
        f"At most {MAX_BLOCKS} blocks and {MAX_BUTTONS} buttons. Give the widget a short "
        "name. If the request asks for something not on these lists, leave it out.\n"
        'Answer only JSON: {"name": "...", "blocks": [...]}.\n\n'
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
    proxy (jarvis_local_http). jarvis_tidy.ollama_caller's shape."""
    def ask(text: str) -> Optional[str]:
        import urllib.error
        import urllib.request
        body = {"model": model, "prompt": text, "stream": False, "format": SCHEMA,
                "think": False, "options": {"temperature": 0, "num_predict": 400}}
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

_ID = re.compile(r"w[0-9a-f]{10}")
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
    env = os.environ.get("JARVIS_WIDGETS_FILE")
    return Path(env) if env else _config_dir() / "widgets.json"


class Store:
    """The saved widgets (a JSON file) and the drafts (memory only)."""

    def __init__(self, path: Optional[Path] = None, clock: Callable[[], float] = time.time):
        self.path = Path(path) if path is not None else None
        self.clock = clock
        self._lock = threading.Lock()
        self._drafts: dict = {}

    def _file(self) -> Path:
        return self.path if self.path is not None else store_path()

    # -- widgets ---------------------------------------------------------------
    def _read(self) -> list:
        p = self._file()
        try:
            if not p.exists() or p.stat().st_size > 256 * 1024:
                return []
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
        rows = data.get("widgets") if isinstance(data, dict) else None
        out = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) \
                    or not _ID.fullmatch(row["id"]):
                continue
            try:
                w = validate({"name": row.get("name"), "blocks": row.get("blocks")})
            except Refused:
                continue        # checked again on every read: a hand edit smuggles nothing
            created = row.get("created")
            w = {"id": row["id"], **w,
                 "created": float(created) if isinstance(created, (int, float))
                 and not isinstance(created, bool) else 0.0}
            out.append(w)
            if len(out) >= MAX_WIDGETS:
                break
        return out

    def _write(self, rows: list) -> None:
        p = self._file()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({"version": 1, "widgets": rows}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, p)

    def widgets(self) -> list:
        with self._lock:
            return self._read()

    def get(self, wid) -> Optional[dict]:
        if not isinstance(wid, str) or not _ID.fullmatch(wid):
            return None
        return next((w for w in self.widgets() if w["id"] == wid), None)

    def delete(self, wid) -> bool:
        if not isinstance(wid, str) or not _ID.fullmatch(wid):
            return False
        with self._lock:
            rows = self._read()
            keep = [w for w in rows if w["id"] != wid]
            if len(keep) == len(rows):
                return False
            self._write(keep)
            return True

    # -- drafts ----------------------------------------------------------------
    def _prune(self) -> None:
        now = self.clock()
        for k in [k for k, d in self._drafts.items() if d["expires"] <= now]:
            del self._drafts[k]

    def add_draft(self, widget: dict) -> dict:
        with self._lock:
            self._prune()
            while len(self._drafts) >= MAX_DRAFTS:
                oldest = min(self._drafts, key=lambda k: self._drafts[k]["expires"])
                del self._drafts[oldest]
            did = "d" + secrets.token_hex(5)
            d = {"id": did, **widget, "expires": self.clock() + DRAFT_TTL}
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
        """(widget, None) - the draft, exactly as previewed, now saved - or
        (None, why)."""
        if not isinstance(did, str) or not _DRAFT_ID.fullmatch(did):
            return None, DRAFT_GONE
        with self._lock:
            self._prune()
            d = self._drafts.get(did)
            if d is None:
                return None, DRAFT_GONE
            rows = self._read()
            if len(rows) >= MAX_WIDGETS:
                return None, TOO_MANY
            w = {"id": "w" + secrets.token_hex(5), "name": d["name"], "blocks": d["blocks"],
                 "created": self.clock()}
            self._write(rows + [w])
            del self._drafts[did]
            return w, None


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
        widget = parse_model(raw)
    except Refused as exc:
        return 422, {"ok": False, "error": COULD_NOT, "why": str(exc)}
    d = (st or store()).add_draft(widget)
    return 200, {"ok": True, "draft": with_words(d), "said": describe(widget) + " " + PREVIEW_HINT,
                 "card": False, "no_card": NO_CARD}


# --------------------------------------------------------------------------
#   Filling a widget in, now
# --------------------------------------------------------------------------

class Readers:
    """Where each source is read. Tests pass their own."""

    def __init__(self, *, sched=None, briefing=None, disk=None, focus=None, playing=None,
                 now=None):
        self.sched = sched or _sched
        self.briefing = briefing or _briefing
        self.disk = disk or _disk
        self.focus = focus or _focus
        self.playing = playing or _playing
        self.now = now or time.time


def _sched():
    import jarvis_schedule
    return jarvis_schedule.get()


def _briefing():
    import jarvis_briefing
    return jarvis_briefing.latest()


def _disk() -> Optional[tuple]:
    root = (os.environ.get("SystemDrive", "C:") + "\\") if os.name == "nt" else "/"
    u = shutil.disk_usage(root)
    return float(u.free), float(u.total)


def _focus() -> dict:
    import jarvis_focus
    return jarvis_focus.ENGINE.status()


def _playing() -> dict:
    import jarvis_media
    return jarvis_media.now_playing()


def _end_of_today(now: float) -> float:
    lt = time.localtime(now)
    start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    lt2 = time.localtime(start + 36 * 3600)
    return time.mktime((lt2.tm_year, lt2.tm_mon, lt2.tm_mday, 0, 0, 0, 0, 0, -1))


def _start_of_today(now: float) -> float:
    lt = time.localtime(now)
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def _gb(n: float) -> str:
    g = n / (1024 ** 3)
    return f"{g:.0f} GB" if g >= 10 else f"{g:.1f} GB"


def _mins(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    return f"{s // 60}:{s % 60:02d}"


_REMINDER_KINDS = ("alarm", "reminder")


def _item(text, when="") -> dict:
    return {"text": " ".join(str(text or "").split())[:200], "when": str(when or "")[:60]}


def _jobs(r: Readers) -> list:
    return list(r.sched().listed())


def _briefing_today(r: Readers) -> Optional[dict]:
    b = r.briefing()
    if not isinstance(b, dict):
        return None
    made = b.get("made")
    if not isinstance(made, (int, float)) or made < _start_of_today(r.now()):
        return None
    return b


def _section(b: dict, key: str) -> Optional[dict]:
    for s in b.get("sections") or []:
        if isinstance(s, dict) and s.get("key") == key:
            return s
    return None


_UNREAD = re.compile(r"^(\d+) unread email")

NO_BRIEFING = "No briefing yet today."


def fill(block: dict, r: Readers) -> dict:
    """One checked block, filled in now. Never raises: a source that cannot
    be read says so in `note`."""
    out = dict(block)
    t = block["type"]
    if t == "button":
        out["label"] = ACTIONS[block["action"]]
        return out
    if t == "title":
        return out
    src = SOURCES[block["source"]]
    out["private"] = src.private
    key = block["source"]
    try:
        if t == "list":
            n = int(block.get("max") or 3)
            items: list = []
            if key == "reminders":
                jobs = [j for j in _jobs(r) if j.get("kind") in _REMINDER_KINDS
                        and j.get("state") == "active" and j.get("due") is not None]
                jobs.sort(key=lambda j: float(j["due"]))
                items = [_item(j.get("text") or j["kind"].capitalize(), j.get("when")) for j in jobs]
            elif key == "timers":
                for j in _jobs(r):
                    if j.get("kind") != "timer":
                        continue
                    left = _mins(float(j.get("left") or 0.0))
                    items.append(_item(j.get("text") or "Timer",
                                       f"{left} left" + (" (paused)" if j.get("state") == "paused"
                                                         else "")))
            elif key == "today":
                items = [_item(j.get("text")) for j in _jobs(r)
                         if j.get("kind") == "today" and j.get("today") == "showing"]
            elif key == "todo":
                items = [_item(j.get("text")) for j in r.sched().todos() if not j.get("list")]
            elif key == "now_playing":
                got = r.playing() or {}
                said = str(got.get("said") or "")
                if got.get("ok") and said and not said.startswith("Nothing"):
                    items = [_item(said)]
                elif not got.get("ok"):
                    out["note"] = said[:120] or "Could not read what is playing."
            out["items"] = items[:n]
            out["more"] = max(0, len(items) - n)
            out["empty"] = src.empty
            return out
        if t == "number":
            if key == "reminders_count":
                end = _end_of_today(r.now())
                out["value"] = str(sum(1 for j in _jobs(r) if j.get("kind") in _REMINDER_KINDS
                                       and j.get("state") == "active"
                                       and j.get("due") is not None and float(j["due"]) < end))
            elif key == "todo_count":
                out["value"] = str(sum(1 for j in r.sched().todos() if not j.get("list")))
            elif key in ("email_count", "events_count"):
                b = _briefing_today(r)
                sec = None if b is None else _section(b, "email" if key == "email_count"
                                                      else "calendar")
                if b is None:
                    out["value"], out["note"] = "", NO_BRIEFING
                elif sec is None or sec.get("state") != "ok":
                    out["value"], out["note"] = "", "Not in today's briefing."
                elif key == "email_count":
                    m = _UNREAD.match(str(sec.get("summary") or ""))
                    out["value"] = m.group(1) if m else "0"
                else:
                    out["value"] = str(len(sec.get("items") or []))
            return out
        if t == "progress":
            if key == "disk_free":
                free, total = r.disk()
                out["fraction"] = round(free / total, 3) if total > 0 else 0.0
                out["value"] = f"{_gb(free)} free of {_gb(total)}"
            elif key == "focus":
                st = r.focus() or {}
                if not st.get("on"):
                    out["fraction"], out["value"] = 0.0, "No focus session."
                else:
                    total = float(st.get("minutes") or 0) * 60.0
                    left = float(st.get("left_s") or 0)
                    out["fraction"] = round(left / total, 3) if total > 0 else 0.0
                    out["value"] = f"{_mins(left)} left" + (" (paused)" if st.get("paused") else "")
            return out
    except Exception:
        out["note"] = "Could not read this on your PC just now."
        out.pop("items", None)
        if t == "list":
            out["items"], out["more"], out["empty"] = [], 0, src.empty
    return out


def show(wid, *, readers: Optional[Readers] = None, st: Optional[Store] = None) -> tuple:
    w = (st or store()).get(wid)
    if w is None:
        return 404, {"ok": False, "error": NO_SUCH}
    r = readers or Readers()
    return 200, {"ok": True, "id": w["id"], "name": w["name"], "at": r.now(),
                 "blocks": [fill(b, r) for b in w["blocks"]]}


def menu() -> dict:
    return {"sources": [{"id": k, "block": s.block, "label": s.label, "private": s.private,
                         "describe": s.describe} for k, s in SOURCES.items()],
            "actions": [{"id": k, "label": v} for k, v in ACTIONS.items()],
            "limits": {"blocks": MAX_BLOCKS, "buttons": MAX_BUTTONS, "list": MAX_LIST,
                       "widgets": MAX_WIDGETS, "words": MAX_WORDS}}


def listing(st: Optional[Store] = None) -> dict:
    st = st or store()
    widgets = st.widgets()
    return {"ok": True,
            "widgets": [with_words(w) for w in widgets],
            "drafts": [with_words(d) for d in st.drafts()],
            "no_card": NO_CARD, "private_hidden": PRIVATE_HIDDEN, **menu()}


# --------------------------------------------------------------------------
#   Routes
# --------------------------------------------------------------------------

def handle_get(path: str, query: str = "", *, st: Optional[Store] = None,
               readers: Optional[Readers] = None) -> tuple:
    if path == LIST_PATH:
        return 200, listing(st)
    if path == SHOW_PATH:
        from urllib.parse import parse_qs
        q = {k: v[0] for k, v in parse_qs(query or "").items() if v}
        return show(q.get("id"), readers=readers, st=st)
    return 404, {"error": "no such route"}


def handle_post(path: str, body, *, st: Optional[Store] = None,
                ask: Optional[Callable] = None) -> tuple:
    st = st or store()
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    if path == DRAFT_PATH:
        # The apps' own "Describe a widget" box: no conversation, so nothing
        # in it can have read outside text; a pasted description is refused
        # by its provenance.
        return draft(body.get("words"), provenance=body.get("provenance"), ask=ask, st=st)
    if path == ADD_PATH:
        w, why = st.keep(body.get("draft"))
        if w is None:
            return (409 if why == TOO_MANY else 404), {"ok": False, "error": why}
        return 200, {"ok": True, "widget": with_words(w),
                     "said": f"Added “{w['name']}”."}
    if path == DISCARD_PATH:
        st.discard(body.get("draft"))
        return 200, {"ok": True}
    if path == DELETE_PATH:
        if not st.delete(body.get("id")):
            return 404, {"ok": False, "error": NO_SUCH}
        return 200, {"ok": True, "said": "Widget deleted."}
    return 404, {"error": "no such route"}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so the widget routes are
    answered here, after the server's own origin and token checks; every
    other request goes straight to the original, untouched."""
    # Marked on the class, not on do_GET: jarvis_brain_reads wraps do_GET
    # again after this, so a mark on the function would be hidden under its.
    if handler_cls.__dict__.get("_jarvis_widgets_on"):
        return "  widgets    Widgets you describe (already on)"
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
            if len(raw) > 16 * 1024:
                return self._send(413, {"ok": False, "error": "too big"})
            body = json.loads(raw)
        except Exception as exc:
            return self._send(400, {"ok": False, "error": type(exc).__name__})
        try:
            code, out = handle_post(route, body)
        except Exception as exc:
            code, out = 500, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    handler_cls._jarvis_widgets_on = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return "  widgets    Widgets you describe: on"


# --------------------------------------------------------------------------
#   Chat: "make me a widget ..." (jarvis_quick.py)
# --------------------------------------------------------------------------

def chat_tainted(conversation, messages) -> bool:
    """Has this conversation read outside text? jarvis_chat_log's answer,
    failing CLOSED like jarvis_agent._conversation_tainted: without it, any
    earlier turn in the request counts as tainted."""
    try:
        import jarvis_chat_log
        return bool(jarvis_chat_log.conversation_tainted(conversation, messages))
    except Exception:
        if not isinstance(messages, list):
            return True
        turns = [m for m in messages if isinstance(m, dict)
                 and m.get("role") in ("user", "assistant", "tool")]
        return len(turns) > 1 or any(m.get("role") != "user" for m in turns)


def from_chat(words: str, *, conversation=None, messages=None, ask: Optional[Callable] = None,
              st: Optional[Store] = None) -> str:
    """jarvis_quick's reply for "make me a widget ...". The fast path only
    runs on the owner's own typed or spoken newest message; this adds the
    conversation's own taint."""
    tainted = chat_tainted(conversation, messages)
    code, out = draft(words, provenance="typed", tainted=tainted, ask=ask, st=st)
    if code == 200:
        return "Made a widget preview. " + out["said"]
    return str(out.get("error") or COULD_NOT)
