"""jarvis_chatbot_routes.py - the routes both apps use to have Jarvis talk to
an AI chatbot for the owner (docs/JARVIS-API.md section 60; step 3 of the
chatbot driver's build, docs/CHATBOT-DRIVER-DESIGN.md section 8).

NEW MODULE, shipped whole; chatbot.patch adds one install() call to
jarvis_hud.py. Every rule about the conversation itself - the card, the
limits, the last check before every message, the clean context, when it
stops - is in jarvis_chatbot.py, and nothing here loosens or repeats one.
This file only turns HTTP into those calls:

    GET  /api/chatbot/status (?id=)   jarvis_chatbot.view(): the chatbots,
                                      which version runs, and the
                                      conversation (the latest live one, or
                                      the one named) with its transcript
    POST /api/chatbot/start           plan() then start(): ONE approval card.
                                      Nothing is sent until a person says
                                      yes. A goal or limit plan() refuses is
                                      a 400 with the reason in plain words,
                                      and no card.
    POST /api/chatbot/stop            stop(): never a card
    POST /api/chatbot/limits          change_limits(): a NEW card; the limits
                                      change only on a yes. The card waits
                                      for the owner, so this answers 202 at
                                      once and the outcome rides on the next
                                      GET (`limits`).

Pause and Resume are the existing /api/task/pause and /api/task/resume
(Resume is its own card); Stop everything (/api/stop_all) stops a
conversation too. Every route sits behind the server's own origin and token
checks, like every other install()-shaped route.

NO EVENT OF ITS OWN. The core reports progress through the one activity
line ("Talking to Gemini: message 3 of 5."); it publishes no transcript on
the bus. Both apps read GET /api/chatbot/status again every few seconds
while a conversation is live, and on every activity event.

OUTSIDE TEXT. The chatbot's words and the end summary come back marked
`outside_text: true` (source "chatbot_transcript"), with `read_aloud: false`.
Both apps show them in their outside-text style, never read them aloud, and
never offer to remember anything from them.

WORDS is the one set of sentences both apps show for this feature;
tools/gen_chatbot_cases.py writes it, with real answers from these routes,
into both apps' contract file.

Standard library only. No I/O at import.
"""
from __future__ import annotations

import json
import re
import threading
from typing import Callable, Optional
from urllib.parse import parse_qs, urlsplit

import jarvis_chatbot as CB

STATUS_ROUTE = "/api/chatbot/status"
START_ROUTE = "/api/chatbot/start"
STOP_ROUTE = "/api/chatbot/stop"
LIMITS_ROUTE = "/api/chatbot/limits"
POST_ROUTES = (START_ROUTE, STOP_ROUTE, LIMITS_ROUTE)

#: What a conversation id looks like (jarvis_chatbot._new_id).
_ID = re.compile(r"^chat_[0-9a-f]{12}$")

#: The sentences both apps show, word for word (tools/gen_chatbot_cases.py).
WORDS = {
    "title": "Talk to a chatbot for me",
    "detail": ("Jarvis asks an AI chatbot about something for you, and writes its own "
               "follow-up questions on this PC, within limits you set. One approval card "
               "covers the whole conversation. While it does this, Jarvis knows only your "
               "goal - not your memory, email, calendar, notes or files."),
    "chatbot_label": "Chatbot",
    "goal_label": "What should Jarvis find out?",
    "goal_note": "These words will be sent to the chatbot exactly as you type them.",
    "messages_label": "Most messages",
    "minutes_label": "Most minutes",
    "never_label": "Words it must never send (optional, separated by commas)",
    "start": "Start",
    "start_note": "Nothing is sent until you approve the card.",
    "pause": "Pause",
    "resume": "Resume",
    "stop": "Stop",
    "change_limits": "Change limits",
    "limits_note": "A change to the limits needs a new approval card.",
    "transcript_title": "The conversation",
    "outside_note": ("The chatbot's words are outside text: shown here, never learned from, "
                     "never read aloud."),
    "summary_title": "What Jarvis found",
    "summary_note": "Written on this PC from the chatbot's words, so it is outside text too.",
    "claim_sourced": "it gave a source (not checked by Jarvis)",
    "claim_unsourced": "no source given",
    "open_title": "Still open",
    "question_title": "The chatbot asked about you",
    "question_note": ("Jarvis never answers questions about you. It is shown here for you to "
                      "decide."),
    "none_built": ("No chatbot can be reached yet: Gemini's part is still being built. "
                   "Start waits until it is."),
    "sign_in_pc": ("Signing in to the chatbot's account happens on the PC only, in the "
                   "browser window Jarvis uses."),
    "missing": ("Your PC's Jarvis cannot talk to chatbots yet - run apply-patches.ps1 on "
                "the PC."),
    "gone": ("That conversation is gone: Jarvis on the PC restarted, and conversations are "
             "kept in memory only."),
    "hidden": ("The goal and the conversation are hidden until you confirm it is you."),
    "version": "Version",
    "notify_running": "Talking to {name}, {used} of {max}",
    "notify_waiting": "Waiting for your yes to talk to {name}",
    "notify_paused": "Paused: talking to {name}, {used} of {max}",
    "notify_locked": "Jarvis is talking to a chatbot for you.",
}

#: The states in which a conversation is still going (jarvis_chatbot._live).
LIVE = ("asking", "approved", "running", "paused")

_LOCK = threading.Lock()
#: session id -> {"waiting": bool, "said": str}: the last limits change.
_LIMITS: dict = {}


def _sentence(text: str) -> str:
    """The core's reasons are lower-case fragments ("the goal cannot be
    sent: ..."); an app shows a sentence."""
    t = " ".join(str(text or "").split())
    if not t:
        return t
    t = t[0].upper() + t[1:]
    return t if t.endswith((".", "!", "?")) else t + "."


def _valid_id(value) -> Optional[str]:
    v = str(value or "")
    return v if _ID.match(v) else None


def _limits_view(session_id: str) -> dict:
    with _LOCK:
        got = dict(_LIMITS.get(session_id) or {})
    return {"waiting": bool(got.get("waiting")), "said": str(got.get("said") or "")}


def handle_get(query: str = "", *, deps=None) -> tuple:
    """GET /api/chatbot/status. A read: no card, never changes anything."""
    q = parse_qs(str(query or ""))
    raw = (q.get("id") or [""])[0]
    sid = ""
    if raw:
        sid = _valid_id(raw) or ""
        if not sid:
            return 400, {"error": "that is not a conversation id"}
    out = CB.view(sid, deps=deps)
    out["routed"] = True
    out["available"] = True
    s = out.get("session")
    out["limits"] = _limits_view(s["id"]) if isinstance(s, dict) else {"waiting": False,
                                                                         "said": ""}
    return 200, out


def _live_session() -> Optional[dict]:
    got = CB.view("").get("session")
    return got if isinstance(got, dict) and got.get("state") in LIVE else None


def _start(body: dict, deps, wait: bool) -> tuple:
    why = CB.tier_problem(deps)
    if why:
        return 409, {"ok": False, "error": _sentence(why)}
    live = _live_session()
    if live:
        return 409, {"ok": False, "session": live["id"],
                     "error": "Another chatbot conversation is still running or paused - "
                              "stop it or let it finish first."}
    s = CB.plan(body.get("chatbot"), body.get("goal"),
                max_turns=body.get("max_messages"), max_minutes=body.get("max_minutes"),
                never_send=body.get("never_send"), deps=deps)
    code, out = CB.start(s, deps=deps, wait=wait)
    if "error" in out:
        out["error"] = _sentence(out["error"])
    return code, out


def _stop(body: dict, deps) -> tuple:
    sid = _valid_id(body.get("id"))
    if not sid:
        return 400, {"ok": False, "error": "Say which conversation to stop."}
    code, out = CB.stop(sid, deps=deps)
    if "error" in out:
        out["error"] = _sentence(out["error"])
    return code, out


def _limits(body: dict, deps, spawn: Callable) -> tuple:
    sid = _valid_id(body.get("id"))
    if not sid:
        return 400, {"ok": False, "error": "Say which conversation's limits to change."}
    s = CB.get(sid)
    if s is None:
        return 404, {"ok": False, "error": "No such conversation."}
    if s.state not in ("running", "paused"):
        return 409, {"ok": False, "error": "Only a running or paused conversation's limits "
                                           "can change."}
    why = CB.tier_problem(deps)
    if why:
        return 409, {"ok": False, "error": _sentence(why)}
    # The same checks change_limits() makes before its card, made here too so
    # a bad number is a 400 now rather than a message on a later read.
    lim = CB.TIER_LIMITS[s.tier.id]
    try:
        new = CB.Limits(
            CB._limit(body.get("max_messages"), s.limits.max_turns, lim["turns"][1],
                      "messages"),
            CB._limit(body.get("max_minutes"), s.limits.max_minutes, lim["minutes"][1],
                      "minutes"),
            s.limits.never_send if body.get("never_send") is None
            else CB._clean_words(body.get("never_send")))
    except ValueError as exc:
        return 400, {"ok": False, "error": _sentence(str(exc))}
    if new == s.limits:
        return 200, {"ok": True, "changed": False, "message": "Those are the limits already."}
    with _LOCK:
        if (_LIMITS.get(sid) or {}).get("waiting"):
            return 409, {"ok": False, "error": "A card for new limits is already waiting for "
                                               "your answer."}
        _LIMITS[sid] = {"waiting": True, "said": ""}

    def ask():
        said = "The limits were not changed."
        try:
            _code, out = CB.change_limits(sid, max_turns=new.max_turns,
                                          max_minutes=new.max_minutes,
                                          never_send=list(new.never_send), deps=deps)
            said = str(out.get("message") or out.get("error") or said)
        except Exception as exc:  # the card failing is a no
            said = f"The limits were not changed ({type(exc).__name__})."
        with _LOCK:
            _LIMITS[sid] = {"waiting": False, "said": _sentence(said)}

    try:
        spawn(ask)
    except Exception:
        with _LOCK:
            _LIMITS.pop(sid, None)
        raise
    return 202, {"ok": True, "asking": True, "session": sid,
                 "message": "Nothing has changed yet. An approval card shows the new limits; "
                            "they apply only if you approve it."}


def _thread(fn: Callable) -> None:
    threading.Thread(target=fn, name="jarvis-chatbot-limits", daemon=True).start()


def handle_post(route: str, body, *, deps=None, spawn: Optional[Callable] = None,
                wait: bool = False) -> tuple:
    """Everything the three POST routes do. Returns (http status, body).
    `wait` and `spawn` are for the tests: the route itself asks the card on
    a background thread, because the gate waits for the owner."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "Need a JSON object."}
    if route == START_ROUTE:
        return _start(body, deps, wait)
    if route == STOP_ROUTE:
        return _stop(body, deps)
    if route == LIMITS_ROUTE:
        return _limits(body, deps, spawn or _thread)
    return 404, {"ok": False, "error": "no such route"}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so the chatbot routes are
    answered here, after the server's own origin and token checks. Every
    other request goes straight to the original."""
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_chatbot", False):
        return "  chatbot    Talk to a chatbot for me (already on)"

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
        parsed = urlsplit(str(getattr(self, "path", "") or ""))
        if parsed.path.rstrip("/") != STATUS_ROUTE:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(parsed.query)
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in POST_ROUTES:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"ok": False, "error": type(exc).__name__})
        try:
            code, out = handle_post(route, body)
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_chatbot = True
    do_POST._jarvis_chatbot = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    built = [c["name"] for c in CB.choices() if c.get("built")]
    return ("  chatbot    Talk to a chatbot for me: "
            + (", ".join(built) if built else "no chatbot built yet"))


def _reset_for_tests() -> None:
    with _LOCK:
        _LIMITS.clear()
