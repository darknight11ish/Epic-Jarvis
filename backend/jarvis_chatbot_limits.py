"""jarvis_chatbot_limits.py - the monthly money limits and the price list for
the chatbot driver's API services, set from the PC's own app
(docs/ACCOUNT-KEYS-DESIGN.md steps 3-5 and decision 1, the owner's approval of
2026-10-06; JARVIS-API section 87.4.1).

NEW MODULE, shipped whole; `chatbot-limits.patch` adds one `install()` call to
jarvis_hud.py and the three gate lines. The numbers themselves are NOT this
file's: every read and every write goes through `jarvis_chatbot_api.py`'s own
`limit_of` / `spent_of` / `money_view` / `price_of` / `set_limit` / `set_price`
/ `reset_price`, so there is one copy of the money rules and one file holding
them (`chatbot/api-money.json`). This file only turns HTTP into those calls and
adds the approval card that raising a limit needs.

    GET  /api/chatbot/money           every service: its monthly limit, what is
                                      spent, what is left, its model and that
                                      model's price WITH where the number came
                                      from and when it was set, and this PC's
                                      own words. A read.

    POST /api/chatbot/money           ONE change, named by `action`:

      {"action": "raise_limit",   "service": "openai", "dollars": 10}
      {"action": "lower_limit",   "service": "openai", "dollars": 3}
      {"action": "remove_limit",  "service": "openai"}
      {"action": "set_price",     "service": "openai", "in": 0.25, "out": 2.00}
      {"action": "reset_price",   "service": "openai"}

THE ONE RULE THAT MATTERS (decision 3, and CLAUDE.md rule 4)
Raising a limit is a LOOSENING: it gets ONE approval card naming the service,
the old amount and the new amount, plus Windows Hello, and it is refused from
any other device. Lowering a limit, removing one, correcting a price and
resetting one all only make a turn stricter or fix a wrong number, so they need
no card - the same "it only makes it stricter, so it does not ask" rule every
other tightening in Jarvis follows.

That is why there are TWO gate actions rather than one. `jarvis_owner_check.
PC_ONLY_ACTIONS` attaches Windows Hello to the ACTION NAME, not to a direction
(the design note's own wording, section 4.3), so one action covering both
directions would ask Hello for a lowering too. Two names keeps Hello on the
loosening only, and this module is the single place that decides which name a
request gets:

    raise_limit  -> gate action `raise_api_limit`, in PC_ONLY_ACTIONS, tier ask
    lower_limit  -> gate action `lower_api_limit`, tier auto, no card
    remove_limit -> gate action `lower_api_limit` (it only ever spends less)
    set_price    -> no gate action at all; a correction is not a loosening
    reset_price  -> no gate action at all

A request that names no `action` is refused. A request from the phone (or from
anything that is not this PC) is refused with 403 `pc_only`, before anything is
read or written - the owner's own decision, "a monthly amount per service, set
on the PC", and the same shape jarvis_spending.py uses for its own PC-only
routes.

FAILING CLOSED. `jarvis_chatbot_api` raises `MoneyFileError` when its money file
is there but unreadable, and that must never read as "nothing spent" - every
path here turns it into a refusal in the module's own words (`_file_words`),
never into a zero.

NOTHING PRIVATE, NOTHING LOGGED. The answer holds service ids, model names,
dollars, dates and the PC's own sentences. No key, no message, no chat and no
piece of one is ever read or written here. The audit line carries the action,
the service and the dollar amounts only.

Standard library only. No I/O at import.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
from typing import Callable, Optional

PATH = "/api/chatbot/money"

#: The two gate actions. See the module note: the NAME carries the Hello.
RAISE_ACTION = "raise_api_limit"
LOWER_ACTION = "lower_api_limit"

#: The card's own words for a raise.
TITLE = "Raise a chatbot's monthly money limit?"
ABOUT = ("How much Jarvis may spend on this service's account in one calendar month. "
         "Raising it lets Jarvis spend more of your money than it could before.")

PC_ONLY = ("This is set on the PC only, so nothing was changed. A monthly money limit is "
           "what keeps a chatbot service from spending past what you agreed to, and the "
           "card that raises one is answered on the PC with Windows Hello.")

_STATE = {"gate": None, "tier_of": None, "spawn": None, "api": None, "audit": None,
          "now": time.time}


def configure(*, gate=None, tier_of=None, spawn=None, api=None, audit=None,
              now=None) -> None:
    """Tests only: stand in for the gate, the tier table, the thread, the API
    module, the audit log and the clock. Passing None for one puts its default
    back."""
    _STATE.update(gate=gate, tier_of=tier_of, spawn=spawn, api=api, audit=audit,
                  now=now or time.time)


def _dep(name: str, default):
    got = _STATE.get(name)
    return default if got is None else got


def _now() -> float:
    return float(_STATE["now"]())


def _api():
    import jarvis_chatbot_api
    return jarvis_chatbot_api


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-chatbot-limits", daemon=True).start()


def _audit(event: str, detail: dict) -> None:
    """Counts, ids and dollars only - never a key, a message or a word of one.
    A missing logger is not an error: the money file is the record."""
    log = _STATE.get("audit")
    if log is None:
        try:
            import jarvis_framework as fw
            log = fw.audit_log
        except Exception:
            return
    try:
        log(event, detail)
    except Exception:
        pass


def _from_this_pc(peer, local) -> bool:
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local))
    except Exception:
        return False        # cannot tell: not this PC


def _peer_local(handler) -> tuple:
    """(the address the request came from, the address it was made to) - the
    pair jarvis_owner_check.from_this_pc reads. The same two lines
    jarvis_spending.py's own `_peer_local` uses."""
    peer = (getattr(handler, "client_address", None) or ("",))[0]
    try:
        local = handler.connection.getsockname()[0]
    except Exception:
        local = None
    return peer, local


# ---------------------------------------------------------------------------
#   The words a refusal uses
# ---------------------------------------------------------------------------

def _file_words(why: str) -> str:
    """jarvis_chatbot_api's own sentence, so the apps and the PC's `spent`
    command say the same thing about an unreadable money file."""
    return _api()._file_words(why)


def _person_said_yes(v) -> bool:
    """The same reading jarvis_quiz_cloud.py uses: the tier must really be
    "ask" and the outcome must really be an approval on this PC."""
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    import jarvis_gate
    try:
        return str(jarvis_gate.tier_of(action))
    except Exception:
        try:
            return str(jarvis_gate._tiers().get(action, "ask"))
        except Exception:
            return "ask"


def _dollars(x) -> str:
    return _api().dollars(x)


def _num(v) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    if f != f or f in (float("inf"), float("-inf")) or f < 0:
        return None
    return f


# ---------------------------------------------------------------------------
#   The read
# ---------------------------------------------------------------------------

def _price_row(api, pid: str, model: str, data: dict) -> dict:
    """One model's price, WITH where the number came from and when it was set -
    decision 4: a wrong price is easier to fix when the app says which numbers
    are guesses."""
    p = api.PRESETS[pid]
    got = api.DEFAULT_PRICES.get((pid, model))
    pr = api.price_of(pid, model, data) if model else None
    mine = (data.get("prices") or {}).get(pid)
    mine = mine.get(model) if isinstance(mine, dict) else None
    set_on = mine.get("set") if isinstance(mine, dict) else None
    if pr is None:
        return {"model": model, "source": "none", "verified": False, "set": "",
                "in": None, "out": None,
                "line": (f"No price is known for the model \"{model}\", so Jarvis cannot keep "
                         f"to your limit. Look one up at {p.price_page or 'the price page'} "
                         f"and set it here."),
                "price_page": p.price_page}
    where = "yours" if pr[2] == "yours" else "default"
    if where == "yours":
        line = (f"${pr[0]:g} per million word-pieces in, ${pr[1]:g} out - your own price"
                + (f", set {set_on}" if set_on else "") + ".")
    else:
        line = (f"${pr[0]:g} per million word-pieces in, ${pr[1]:g} out - the default written "
                f"{api.PRICES_WRITTEN}, UNVERIFIED. Check it at "
                f"{p.price_page or 'the price page'} and correct it here.")
    return {"model": model, "source": where, "verified": False if where == "default" else True,
            "set": set_on or "", "in": pr[0], "out": pr[1], "line": line,
            "price_page": p.price_page, "default": got is not None}


def _service_row(api, pid: str, data: dict, *, here: bool) -> dict:
    p = api.PRESETS[pid]
    model, problem = api.model_for(pid)
    limit = api.limit_of(pid, data)
    spent = api.spent_of(pid, data)
    out = {
        "service": p.short,
        "company": p.company,
        "name": p.name,
        "host": p.host,
        "model": model,
        "model_problem": problem,
        "limit": None if limit is None else round(limit, 2),
        "limit_words": "not set" if limit is None else _dollars(limit),
        "spent": round(spent, 2),
        "spent_words": _dollars(spent),
        "left_words": "--" if limit is None else _dollars(max(0.0, limit - spent)),
        "until": api.next_month_words(),
        "reached": limit is not None and spent >= limit,
        "ready": api.ready_for(pid),
        "cap": api.cap_words(p),
        "price_page": p.price_page,
        "price": _price_row(api, pid, model, data) if model else None,
        "can_change": bool(here),
    }
    if limit is None:
        out["line"] = api.no_limit_words(p)
    else:
        out["line"] = api.MONEY_LEFT.format(left=out["left_words"],
                                            limit=_dollars(limit), company=p.company)
    return out


def view(*, here: bool = False) -> tuple:
    """GET /api/chatbot/money. (status, body)."""
    api = _api()
    try:
        data = api._load()
    except api.MoneyFileError as exc:
        return 503, {"ok": False, "available": False, "error": "money_unreadable",
                     "message": _file_words(str(exc))}
    rows = [_service_row(api, pid, data, here=here) for pid in api.PRESETS]
    return 200, {
        "ok": True,
        "available": True,
        "title": "Chatbot money limits",
        "about": ABOUT,
        "can_change": bool(here),
        "pc_only": PC_ONLY,
        "raise_words": ("Raising a limit asks you on an approval card, and Windows Hello on "
                        "this PC confirms it is you. Lowering one, removing one and "
                        "correcting a price change at once, with no card."),
        "raise_action": RAISE_ACTION,
        "lower_action": LOWER_ACTION,
        "estimates": ("Every price here is used to ESTIMATE what an answer cost. The default "
                      "prices are unverified guesses, so the amounts spent are about, not "
                      "exact - only the service's own bill is exact."),
        "until": api.next_month_words(),
        "money_file_words": api.MONEY_FILE,
        "services": rows,
    }


# ---------------------------------------------------------------------------
#   The writes
# ---------------------------------------------------------------------------

def _refuse(code: str, status: int, message: str = "") -> tuple:
    return status, {"ok": False, "error": code, "message": message}


def _raise_card(api, pid: str, old, amount: float):
    """The card for a RAISE, and the yes. (None, said) when it went through;
    ((status, body), "") when it did not."""
    p = api.PRESETS[pid]
    was = "no limit" if old is None else _dollars(old)
    prompt = (f"Let Jarvis spend up to {_dollars(amount)} a month on {p.company}, instead of "
              f"{was}?")
    detail = {
        "text": prompt,
        "what": f"raise the monthly money limit for {p.company}",
        "service": p.short,
        "company": p.company,
        "was": was,
        "now": _dollars(amount),
        "leaves_this_pc": False,
    }
    gate = _dep("gate", _gate)
    tier_of = _dep("tier_of", _tier)
    try:
        if tier_of(RAISE_ACTION) != "ask":
            return _refuse("tier_not_ask", 503), ""
        v = gate(RAISE_ACTION, detail, prompt)
    except Exception:
        return _refuse("card_unavailable", 503), ""
    if not _person_said_yes(v):
        outcome = getattr(v, "outcome", None)
        state = outcome if outcome in ("denied", "timed_out") else "refused"
        words = {"denied": "You said no, so the limit was not raised.",
                 "timed_out": "The card was not answered in time, so the limit was not raised."}
        return _refuse("not_approved", 409,
                       words.get(state, "The card was not approved, so the limit was not "
                                        "raised.")), ""
    return None, f"The limit for {p.company} is now {_dollars(amount)} a month."


def _apply(api, body: dict, *, here: bool) -> tuple:
    """One change. (status, body)."""
    action = str(body.get("action") or "").strip().lower()
    pid = api.BY_SHORT.get(str(body.get("service") or "").strip().lower())
    if action not in ("raise_limit", "lower_limit", "remove_limit", "set_price",
                      "reset_price"):
        return _refuse("unknown_action", 400,
                       "Say what to change: raise or lower a limit, remove one, set a price, "
                       "or reset one.")
    if pid is None:
        return _refuse("no_such_service", 400,
                       "Say which service: " + ", ".join(sorted(api.BY_SHORT)) + ".")
    p = api.PRESETS[pid]

    if action in ("set_price", "reset_price"):
        model, problem = api.model_for(pid)
        if problem or not model:
            return _refuse("no_model", 400, f"{p.name} has no usable model: {problem}.")
        if action == "reset_price":
            got = api.reset_price(pid, model)
        else:
            pin, pout = _num(body.get("in")), _num(body.get("out"))
            if pin is None or pout is None or pin > api.MOST_PRICE or pout > api.MOST_PRICE:
                return _refuse("bad_price", 400,
                               "Each price is dollars per million word-pieces, from 0 to "
                               f"{api.MOST_PRICE:,.0f}.")
            got = api.set_price(pid, model, pin, pout)
        if not got.get("ok"):
            return _refuse("price_not_set", 400, str(got.get("error") or ""))
        _audit("chatbot_money.price", {"action": action, "service": p.short, "model": model})
        return 200, {"ok": True, "changed": True, "said": got.get("said", ""),
                     **(view(here=here)[1])}

    # ---- a limit ----------------------------------------------------------
    try:
        data = api._load()
    except api.MoneyFileError as exc:
        return _refuse("money_unreadable", 503, _file_words(str(exc)))
    old = api.limit_of(pid, data)
    if action == "remove_limit":
        amount = None
    else:
        amount = _num(body.get("dollars"))
        if amount is None or amount > api.MOST_LIMIT:
            return _refuse("bad_amount", 400,
                           "The limit is a number of dollars a month, from 0 to "
                           f"{api.MOST_LIMIT:,.0f}.")
    if action == "raise_limit" and old is not None and amount is not None and amount <= old:
        # Asked to raise, to no more than it already is: that is a lowering (or
        # nothing), and a lowering must not be dressed up as a raise to get a
        # card. Send it down the tightening path instead.
        action = "lower_limit"
    if action == "remove_limit" and old is None:
        # Nothing to take away. Not an error in the API module, but answering
        # "removed" for a limit that was never there would be a lie.
        return _refuse("nothing_to_do", 400, "There is no limit set to remove.")

    if action == "raise_limit":
        refused, said = _raise_card(api, pid, old, amount)
        if refused is not None:
            _audit("chatbot_money.limit", {"action": "raise", "service": p.short,
                                           "outcome": "not_approved"})
            return refused
    else:
        # Tightening: no card, and never held. Checked here rather than in the
        # gate, because there is no gate action for it by design.
        said = ""

    got = api.set_limit(pid, amount)
    if not got.get("ok"):
        return _refuse("limit_not_set", 400, str(got.get("error") or ""))
    _audit("chatbot_money.limit",
           {"action": "raise" if action == "raise_limit" else "tighten",
            "service": p.short,
            "amount": None if amount is None else round(float(amount), 2),
            "was": None if old is None else round(float(old), 2)})
    return 200, {"ok": True, "changed": True, "raised": action == "raise_limit",
                 "approved": action == "raise_limit",
                 "said": said or str(got.get("said") or ""),
                 **(view(here=here)[1])}


def change(body, *, peer=None, local=None) -> tuple:
    """POST /api/chatbot/money. (status, body). PC only."""
    here = _from_this_pc(peer, local)
    if not here:
        return 403, {"ok": False, "error": "pc_only", "pc_only": True, "message": PC_ONLY}
    if not isinstance(body, dict):
        return _refuse("bad_request", 400)
    api = _api()
    return _apply(api, body, here=True)


# ---------------------------------------------------------------------------
#   The routes
# ---------------------------------------------------------------------------

def owns(method: str, route: str) -> bool:
    return route == PATH and method in ("GET", "POST")


def handle_get(route: str, query: dict, peer=None, local=None) -> tuple:
    if route != PATH:
        return 404, {"ok": False, "error": "not_found"}
    return view(here=_from_this_pc(peer, local))


def handle_post(route: str, body, peer=None, local=None) -> tuple:
    if route != PATH:
        return 404, {"ok": False, "error": "not_found"}
    return change(body, peer=peer, local=local)


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so the route is answered here,
    after the server's own origin and token checks - the shape
    jarvis_quiz_cloud.install uses. Every other request goes to the original."""
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_chatbot_limits", False):
        return "  chatbot money limits (already on)"

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

    def _path(self) -> str:
        return urllib.parse.urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")

    def _query(self) -> dict:
        return urllib.parse.parse_qs(
            urllib.parse.urlsplit(str(getattr(self, "path", "") or "")).query)

    def do_GET(self):
        route = _path(self)
        if not owns("GET", route):
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route, _query(self), *_peer_local(self))
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = _path(self)
        if not owns("POST", route):
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        try:
            code, out = handle_post(route, body, *_peer_local(self))
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_chatbot_limits = True
    do_POST._jarvis_chatbot_limits = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return ("  chatbot money limits (a raise needs a card and Windows Hello; a lowering does "
            "not; prices are editable and always say where the number came from)")


# ---------------------------------------------------------------------------
#   Tests only
# ---------------------------------------------------------------------------

def _reset_for_tests() -> None:
    configure(gate=None, tier_of=None, spawn=None, api=None, audit=None, now=None)
