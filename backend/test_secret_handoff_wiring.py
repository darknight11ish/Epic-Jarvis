"""test_secret_handoff_wiring.py - the host half of the owner-secret hand-off.

    python -B backend/test_secret_handoff_wiring.py

WHAT THIS PINS, WITH NO GUI AND NO NETWORK

  1. The plan hook: a `type` request aimed at a password-masked control raises
     the card with the agent's `why`; a non-password control never does.
  2. The route pair is host-only: cross-origin, tokenless and non-loopback
     callers are refused BEFORE the body is read, and the body is never echoed.
  3. The fill forwards to `execute_owner_fill(..., from_this_pc=True)` and the
     ENGINE decides every void: a changed target or an empty secret types
     nothing, and the route does not repeat those checks.
  4. The taint is visible to the read paths immediately after a fill:
     `get_window_state` returns `secret_read_restricted`; the selection read
     consults the same guard before it reads.
  5. The HUD card has the two labelled boxes, a password input and a clear on
     submit, and the three HUD twins stay byte-identical.
"""
from __future__ import annotations

import ast
import json
import sys
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_secret_handoff.py")
require_shipped("jarvis_secret_handoff_wiring.py")

import jarvis_secret_handoff as S  # noqa: E402
import jarvis_secret_handoff_wiring as W  # noqa: E402
import jarvis_ui_control as U  # noqa: E402

PASSED: list = []
FAILED: list = []


def check(name: str, cond: object, detail: str = "") -> bool:
    if cond:
        PASSED.append(name)
        return True
    FAILED.append(name)
    print(f"FAIL  {name}" + (f"\n        {detail}" if detail else ""))
    return False


DESC = {
    "window": "Login - Notepad",
    "pid": 1234,
    "hwnd": 5678,
    "window_class": "Notepad",
    "control_index": 0,
    "control_type": "EditControl",
    "control_id": "uia:1234:5678:0:EditControl:auto:42:EditControl",
    "target_key": "hwnd:1234:5678:notepad",
    "display_origin": "notepad.exe (PID 1234) - Login - EditControl (password field)",
}

TREE = [{"name": "(a password field)", "automation_id": "", "control_type": "Edit",
         "enabled": True, "password": True, "masked": True, "level": 0}]


class FakeHandler:
    def __init__(self, path, body=None, peer=("127.0.0.1", 50000)):
        self.path = path
        self.body = b"" if body is None else body
        self.client_address = peer
        self.connection = types.SimpleNamespace(getsockname=lambda: ("127.0.0.1", 4719))
        self.sent = None
        self.original = None

    def do_GET(self):
        self.original = ("get", self.path)

    def do_POST(self):
        self.original = ("post", self.path)

    def _send(self, code, body, **kw):
        self.sent = (code, body)


def installed(*, origin=True, token=True, body_reader=None):
    class Hd(FakeHandler):
        pass

    W.install(Hd, origin_ok=lambda s: origin, token_ok=lambda s: token,
              read_body=body_reader)
    return Hd


def reset():
    S.reset_for_tests()
    # The wiring's own metadata table, cleared through the public cancel path.
    for card in W.pending_cards():
        W.cancel_card(card["handoff_id"])


def post(path, payload, *, origin=True, token=True, peer=("127.0.0.1", 50000)):
    reads = []

    def read_body(handler):
        reads.append(handler.path)
        return handler.body

    H = installed(origin=origin, token=token, body_reader=read_body)
    h = H(path, body=json.dumps(payload).encode("utf-8"), peer=peer)
    h.do_POST()
    return h, reads


def get(path, *, origin=True, token=True, peer=("127.0.0.1", 50000)):
    H = installed(origin=origin, token=token, body_reader=lambda h: h.body)
    h = H(path, peer=peer)
    h.do_GET()
    return h


def real_plan_hook():
    """Record the card the plan hook asks for; return a fake card."""
    calls = []

    def fake_card_from_plan(*, window, index, purpose, goal=""):
        calls.append({"window": window, "index": index, "purpose": purpose, "goal": goal})
        return {"handoff_id": "sh_fake", "verified_target": DESC["display_origin"]}

    saved = W.card_from_plan
    W.card_from_plan = fake_card_from_plan
    return calls, saved


# --------------------------------------------------------------------------
#   1. The plan hook
# --------------------------------------------------------------------------

def t_a_password_type_request_raises_the_card_with_the_agents_why():
    calls, saved = real_plan_hook()
    try:
        p = U.plan("log in", "Login - Notepad",
                   [{"index": 0, "action": "type", "value": "x",
                     "why": "the owner asked me to sign in"}],
                   read=lambda _w: [dict(c) for c in TREE])
    finally:
        W.card_from_plan = saved
    check("plan(): a type request aimed at a password-masked control calls the host",
          len(calls) == 1 and calls[0]["purpose"] == "the owner asked me to sign in", calls)
    check("plan(): the request is not run - it is reported as a raised hand-off card",
          len(p.unmatched) == 1 and p.unmatched[0].get("code") == "secret_handoff_raised",
          p.unmatched)
    check("plan(): the plan contains no step that would type the secret",
          p.steps == [], p.steps)


def t_a_non_password_control_never_raises_a_card():
    calls, saved = real_plan_hook()
    tree = [{"name": "Search", "automation_id": "q", "control_type": "Edit",
             "enabled": True, "password": False, "masked": False, "level": 0}]
    try:
        p = U.plan("search", "Login - Notepad",
                   [{"control": "Search", "action": "type", "value": "hi", "why": "x"}],
                   read=lambda _w: tree)
    finally:
        W.card_from_plan = saved
    check("plan(): a non-password control never raises a hand-off card", calls == [], calls)
    check("plan(): ... and it becomes an ordinary typing step",
          len(p.steps) == 1 and p.steps[0].action == "type", p.steps)


# --------------------------------------------------------------------------
#   2. The route pair - host-only, token, body
# --------------------------------------------------------------------------

def t_installed_routes_refuse_before_reading_the_body():
    h, reads = post(W.FILL_PATH, {"handoff_id": "x", "secret": "pw"}, token=False)
    check("fill: no token -> 401 and the body is never read", h.sent and h.sent[0] == 401, h.sent)
    check("fill: ... the reader is not called", reads == [], reads)

    h, reads = post(W.CREATE_PATH, {"purpose": "x"}, origin=False)
    check("create: another origin -> 403 before the body", h.sent and h.sent[0] == 403, h.sent)
    check("create: ... the reader is not called", reads == [], reads)

    h, reads = post(W.CREATE_PATH, {"purpose": "x"}, peer=("100.64.0.9", 50000))
    check("create: another machine -> 403 BEFORE its body is read", h.sent and h.sent[0] == 403, h.sent)
    check("create: ... the reader is not called for another machine", reads == [], reads)

    h = get(W.PENDING_PATH, token=False)
    check("pending: no token -> 401 and no cards leak", h.sent and h.sent[0] == 401, h.sent)
    h = get(W.PENDING_PATH, peer=("100.64.0.9", 50000))
    check("pending: another machine -> 403", h.sent and h.sent[0] == 403, h.sent)


def t_a_non_password_target_cannot_raise_a_card():
    reset()
    saved = U.secret_handoff_focused_descriptor
    U.secret_handoff_focused_descriptor = lambda: (_ for _ in ()).throw(
        RuntimeError("the focused control is not password-masked"))
    try:
        h, reads = post(W.CREATE_PATH, {"purpose": "x"})
    finally:
        U.secret_handoff_focused_descriptor = saved
    check("create: a non-password focused control -> refusal, never a card",
          h.sent and h.sent[0] == 409 and W.pending_cards() == [], h.sent)
    check("create: ... the refusal does not echo the request body",
          "secret" not in json.dumps(h.sent[1]).lower(), h.sent)


def t_the_create_refusal_names_the_inner_reason_but_never_the_body():
    """A host caller must be able to tell "nothing is focused" from "the host
    could not measure at all" - the difference that hid a per-thread COM bug on
    2026-10-26. The reason is a safe E_* code (or the exception type), and the
    refusal still never echoes the request body."""
    reset()
    saved = U.secret_handoff_focused_descriptor
    U.secret_handoff_focused_descriptor = lambda: (_ for _ in ()).throw(
        U.UiaMeasurementError("E_UIA_READ_FAIL",
                              "the focused control could not be read (OSError)"))
    try:
        h, reads = post(W.CREATE_PATH, {"purpose": "raise it"})
    finally:
        U.secret_handoff_focused_descriptor = saved
    body = json.dumps(h.sent[1]).lower() if h.sent else ""
    check("create: the refusal carries the safe reason code",
          h.sent and h.sent[0] == 409
          and isinstance(h.sent[1], dict)
          and h.sent[1].get("reason_code") == "E_UIA_READ_FAIL", h.sent)
    check("create: ... and the inner sentence, never the request body",
          "could not be read" in body and "purpose" not in body
          and "secret" not in body, h.sent)


def t_the_create_refusal_falls_back_to_the_exception_type():
    """A failure with no reason code (e.g. the engine's own RuntimeError) still
    gives the caller a machine-readable tag rather than nothing."""
    reset()
    saved = U.secret_handoff_focused_descriptor
    U.secret_handoff_focused_descriptor = lambda: (_ for _ in ()).throw(
        RuntimeError("the focused control is not password-masked"))
    try:
        h, reads = post(W.CREATE_PATH, {"purpose": "x"})
    finally:
        U.secret_handoff_focused_descriptor = saved
    check("create: an exception with no reason code still names its type",
          h.sent and h.sent[0] == 409
          and isinstance(h.sent[1], dict)
          and h.sent[1].get("reason_code") == "RuntimeError", h.sent)


def t_create_returns_the_two_boxes_and_no_secret():
    reset()
    saved = U.secret_handoff_focused_descriptor
    U.secret_handoff_focused_descriptor = lambda: dict(DESC)
    try:
        h, reads = post(W.CREATE_PATH, {"purpose": "sign in to the shop\nnow"})
    finally:
        U.secret_handoff_focused_descriptor = saved
    card = (h.sent or (None, {}))[1].get("card") if isinstance(h.sent[1], dict) else None
    check("create: 200 with a card", h.sent and h.sent[0] == 200 and card, h.sent)
    check("create: box 1 is the host-measured target",
          bool(card) and card.get("verified_target") == DESC["display_origin"], card)
    check("create: box 2 is the cleaned agent note, labelled untrusted",
          bool(card) and card.get("agent_claimed_purpose") == "sign in to the shop now"
          and card.get("agent_purpose_is_untrusted") is True, card)
    check("create: the card has no secret field and no secret value",
          "secret" not in json.dumps(h.sent[1]).lower(), h.sent)
    pending = W.pending_cards()
    check("pending: the created card is what the HUD polls for",
          len(pending) == 1 and pending[0]["handoff_id"] == card["handoff_id"], pending)


# --------------------------------------------------------------------------
#   3. Fill: engine decides the void, typing is injected
# --------------------------------------------------------------------------

def _make_card():
    reset()
    saved = U.secret_handoff_focused_descriptor
    U.secret_handoff_focused_descriptor = lambda: dict(DESC)
    try:
        h, _ = post(W.CREATE_PATH, {"purpose": "log in"})
    finally:
        U.secret_handoff_focused_descriptor = saved
    return h.sent[1]["card"]["handoff_id"]


def t_fill_forwards_to_the_engine_and_taints_before_the_read_paths():
    reset()
    hid = _make_card()
    typed = []
    saved_live = U.secret_handoff_live_snapshot
    saved_type = U.secret_handoff_type
    U.secret_handoff_live_snapshot = lambda _d: {
        "target_key": DESC["target_key"], "display_origin": DESC["display_origin"],
        "is_password_field": True, "control_id": DESC["control_id"]}
    U.secret_handoff_type = lambda _d, value: typed.append(value)
    try:
        h, reads = post(W.FILL_PATH, {"handoff_id": hid, "secret": "hunter2"})
        check("fill: 200 and one receipt, with the value typed exactly once",
              h.sent and h.sent[0] == 200 and typed == ["hunter2"], (h.sent, typed))
        check("fill: the response never echoes the secret",
              "hunter2" not in json.dumps(h.sent[1]), h.sent)
        check("fill: the engine's taint is marked on the measured key",
              S.is_read_restricted(DESC["target_key"]) is True)
        code = U.get_window_state(
            1234, 5678,
            windows=lambda _pid: [{"window_id": 5678, "title": "Login - Notepad",
                                   "class_name": "Notepad", "process": "notepad.exe",
                                   "process_id": 1234}],
            tree=lambda *_a: (_ for _ in ()).throw(AssertionError("tree read after taint")))
        check("get_window_state: the tainted window is refused before its tree is read",
              code.get("ok") is False and code.get("code") == "secret_read_restricted", code)
    finally:
        U.secret_handoff_live_snapshot = saved_live
        U.secret_handoff_type = saved_type


def t_the_engine_decides_every_void_and_nothing_is_typed():
    reset()
    hid = _make_card()
    typed = []
    saved_live = U.secret_handoff_live_snapshot
    saved_type = U.secret_handoff_type
    U.secret_handoff_live_snapshot = lambda _d: {
        "target_key": "hwnd:999:888:other", "display_origin": "other window",
        "is_password_field": True, "control_id": "other"}
    U.secret_handoff_type = lambda _d, value: typed.append(value)
    try:
        h, _ = post(W.FILL_PATH, {"handoff_id": hid, "secret": "hunter2"})
        check("fill: a changed target is a void with NOTHING typed",
              h.sent and h.sent[0] == 409 and typed == [], (h.sent, typed))
        check("fill: the refusal is the engine's own changed-target sentence",
              "target changed" in str(h.sent[1].get("error", "")).lower(), h.sent)
        check("fill: the spent card is gone from the pending list", W.pending_cards() == [])

        hid2 = _make_card()
        h2, _ = post(W.FILL_PATH, {"handoff_id": hid2, "secret": ""})
        check("fill: an empty secret is refused by the engine, nothing typed",
              h2.sent and h2.sent[0] == 409 and typed == [], (h2.sent, typed))
    finally:
        U.secret_handoff_live_snapshot = saved_live
        U.secret_handoff_type = saved_type


def t_a_typing_failure_still_taints_and_spends_the_card():
    reset()
    hid = _make_card()
    saved_live = U.secret_handoff_live_snapshot
    saved_type = U.secret_handoff_type
    U.secret_handoff_live_snapshot = lambda _d: {
        "target_key": DESC["target_key"], "display_origin": DESC["display_origin"],
        "is_password_field": True, "control_id": DESC["control_id"]}

    def boom(_d, _v):
        raise RuntimeError("typing failed halfway")

    U.secret_handoff_type = boom
    try:
        h, _ = post(W.FILL_PATH, {"handoff_id": hid, "secret": "hunter2"})
        check("fill: a typing failure is reported as a failure, not a success",
              h.sent and h.sent[0] >= 400, h.sent)
        check("fill: the target stays read-locked after a typing failure",
              S.is_read_restricted(DESC["target_key"]) is True)
        check("fill: the card is spent, not left pending", W.pending_cards() == [])
    finally:
        U.secret_handoff_live_snapshot = saved_live
        U.secret_handoff_type = saved_type


# --------------------------------------------------------------------------
#   4. Source-level guarantees and the HUD card
# --------------------------------------------------------------------------

def t_the_wiring_module_has_no_logging_or_storage_path():
    source = Path(W.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = {"logging", "sqlite3", "socket", "http", "urllib", "requests",
                 "pathlib", "os", "subprocess", "ctypes"}
    check("the wiring module imports no logging/storage/network module",
          imported.isdisjoint(forbidden), sorted(imported & forbidden))
    check("the wiring module never prints or opens a file",
          "print(" not in source and "open(" not in source and ".write(" not in source)
    check("the route never puts the request body into a response",
          "secret_value" not in source.split("def handle_post", 1)[1]
          or "body.get(\"secret\")" in source, "reviewed by hand")


def t_the_engine_is_the_only_place_that_decides_a_void():
    source = Path(W.__file__).read_text(encoding="utf-8")
    check("the route does not repeat 'expired' / 'password-masked' / 'target changed'",
          "card expired" not in source and "no longer password-masked; nothing was typed"
          not in source and "target changed while the card was open" not in source)


HUD_TWINS = [
    REPO / "jarvis-desktop" / "src" / "jarvis_hud.html",
    REPO / "backend" / "jarvis_hud.html",
    REPO / "jarvis-backend" / "jarvis_hud.html",
]


def t_the_hud_card_has_the_two_boxes_and_clears_the_secret():
    texts = [p.read_text(encoding="utf-8") for p in HUD_TWINS]
    check("the three HUD twins exist and are byte-identical",
          all(p.is_file() for p in HUD_TWINS)
          and texts[0] == texts[1] == texts[2], [len(t) for t in texts])
    html = texts[0]
    for marker in ('id="secret-handoff"', 'id="sh-target"', 'id="sh-purpose"',
                   'id="sh-secret"', 'type="password"', 'autocomplete="off"',
                   "Checked by this PC (host-verified target)",
                   "Jarvis's note (unverified):", 'id="sh-type"', 'id="sh-cancel"',
                   "UNENCRYPTED HTTP"):
        check(f"HUD card contains {marker}", marker in html)
    check("HUD card: the fill path clears the secret before repaint",
          "shClearSecret();" in html and 'sh-secret' in html)
    block = html.split("async function shType()", 1)[1].split("async function shCancel()", 1)[0]
    check("HUD card: no console log in the secret path", "console." not in block)
    check("HUD card: the secret is never placed into innerHTML/textContent",
          "secret" not in block.split("shClearSecret()", 1)[0].lower()
          or "field.value" in block, "reviewed")


def main():
    print(f"--- secret hand-off wiring --- ({W.__file__})")
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception as exc:  # pragma: no cover - a crash is a failure
                traceback.print_exc()
                check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
