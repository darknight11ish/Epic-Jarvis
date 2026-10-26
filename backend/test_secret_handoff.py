"""test_secret_handoff.py - the owner-secret hand-off rules, with no GUI and no network.

    python -B backend/test_secret_handoff.py

WHAT THIS PINS
  1. The target key: a page is scheme + host + path (query/fragment stripped);
     a window is pid + hwnd + class. Non-http page schemes and zero ids raise.
  2. The taint table: in memory only, 15 minutes, at most 32 targets, oldest
     evicted first, re-marking refreshes, expiry is monotonic-clock based.
  3. The card: only for a password-masked control; the agent's claimed purpose
     is cleaned, capped and marked untrusted; the card never contains a secret.
  4. The fill order, which is the security property: every abort condition is
     checked BEFORE the first character is typed, and the taint is marked
     BEFORE typing, so a failure halfway through still leaves the target
     read-locked.
  5. No persistence: the module never opens a file, never imports sqlite/logging,
     never prints, and a typed secret appears in no returned structure.

No owner config, no temp database, no model, no network. A fake monotonic clock
means no test sleeps. The suite runs the same in this repository and on the
owner's PC; it does not import `jarvis_gate`, the UI control or the browser.
"""
from __future__ import annotations

import ast
import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_secret_handoff.py")

import jarvis_secret_handoff as S  # noqa: E402

PASSED: list = []
FAILED: list = []
SKIPPED: list = []


def check(name: str, cond: object, detail: str = "") -> bool:
    if cond:
        PASSED.append(name)
        return True
    FAILED.append(name)
    print(f"FAIL  {name}" + (f"\n        {detail}" if detail else ""))
    return False


def skip(name: str, why: str) -> None:
    SKIPPED.append(name)
    print(f"SKIP  {name} - {why}")


class Clock:
    """A monotonic clock the test moves by hand; no test sleeps."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = float(start)

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += float(seconds)


def browser_snapshot(clock: Clock, *, url: str = "https://github.com/login",
                     control_id: str = "input-1", purpose: str = "sign in",
                     password: bool = True) -> "S.VerifiedTargetSnapshot":
    key = S.normalize_secret_target_key(url=url)
    return S.VerifiedTargetSnapshot(
        target_key=key, kind="browser", display_origin=url,
        is_https=S.web_target_is_https(url), is_password_field=password,
        control_id=control_id, agent_claimed_purpose=purpose)


def window_snapshot(clock: Clock, *, pid: int = 4812, hwnd: int = 9001,
                    window_class: str = "Edit", control_id: str = "edit-7",
                    purpose: str = "unlock") -> "S.VerifiedTargetSnapshot":
    key = S.normalize_secret_target_key(pid=pid, hwnd=hwnd, window_class=window_class)
    return S.VerifiedTargetSnapshot(
        target_key=key, kind="desktop_window",
        display_origin=f"1Password.exe (PID {pid}) - Unlock",
        is_https=True, is_password_field=True, control_id=control_id,
        agent_claimed_purpose=purpose)


def make_coordinator(clock: Clock, **kwargs):
    taint = S.SecretPageTaintRegistry(clock=clock)
    return S.SecretHandoffCoordinator(taint, clock=clock, **kwargs), taint


def raises(exc_type: type, fn) -> bool:
    try:
        fn()
    except exc_type:
        return True
    except Exception:
        return False
    return False


# --- 1. keys -----------------------------------------------------------------

def t_key_normalization():
    raw = "https://Example.COM:443/login?next=%2Fhome#fragment"
    check("query string and fragment are stripped from the page key",
          S.normalize_secret_target_key(url=raw) == "url:https://example.com:443/login",
          S.normalize_secret_target_key(url=raw))
    check("the scheme and host are lower-cased",
          S.normalize_secret_target_key(url="HTTPS://GitHub.com/Login") ==
          "url:https://github.com/Login")
    check("a bare origin has path /", S.normalize_secret_target_key(
        url="https://example.com") == "url:https://example.com/")
    check("http is recognized as not encrypted",
          S.web_target_is_https("http://example.com/x") is False)
    check("https is recognized as encrypted",
          S.web_target_is_https("https://example.com/x") is True)
    check("a page key is recognized as web", S.is_web_target_key("url:https://a/b"))
    check("a window key is not web", not S.is_web_target_key("hwnd:1:2:edit"))
    check("a non-http page scheme is refused",
          raises(ValueError, lambda: S.normalize_secret_target_key(url="ftp://example.com/x")))
    check("a page with no host is refused",
          raises(ValueError, lambda: S.normalize_secret_target_key(url="https:///login")))
    check("a file: address is refused",
          raises(ValueError, lambda: S.normalize_secret_target_key(url="file:///c:/x")))
    check("the desktop key carries pid, hwnd and the lower-cased class",
          S.normalize_secret_target_key(pid=4812, hwnd=9001, window_class="Edit") ==
          "hwnd:4812:9001:edit")
    check("a missing window class becomes -, not an empty field",
          S.normalize_secret_target_key(pid=1, hwnd=2) == "hwnd:1:2:-")
    check("numeric strings are accepted for pid/hwnd",
          S.normalize_secret_target_key(pid="4812", hwnd="9001", window_class="Edit") ==
          "hwnd:4812:9001:edit")
    check("a zero pid is refused",
          raises(ValueError, lambda: S.normalize_secret_target_key(pid=0, hwnd=2)))
    check("a negative hwnd is refused",
          raises(ValueError, lambda: S.normalize_secret_target_key(pid=4, hwnd=-1)))
    check("no target at all is refused", raises(ValueError, lambda: S.normalize_secret_target_key()))
    check("the agent purpose is cleaned of control characters and capped",
          S.clean_agent_purpose(" sign\nin\tto\x00 github " + "x" * 500) ==
          ("sign in to github " + "x" * 500)[:S.MAX_PURPOSE_CHARS])
    check("an empty purpose is fine", S.clean_agent_purpose(None) == "")


# --- 2. the taint table ------------------------------------------------------

def t_taint_registry():
    clock = Clock()
    reg = S.SecretPageTaintRegistry(clock=clock)
    key = "url:https://github.com/login"
    check("a fresh target is readable", reg.is_read_restricted(key) is False)
    check("an empty key is never restricted", reg.is_read_restricted("") is False)
    reg.mark_secret_entered(key)
    check("a marked target is read-locked", reg.is_read_restricted(key) is True)
    check("a different target is untouched",
          reg.is_read_restricted("url:https://github.com/home") is False)
    clock.advance(S.SECRET_TAINT_TTL_S - 1)
    check("still locked one second before the taint expires",
          reg.is_read_restricted(key) is True)
    clock.advance(2)
    check("unlocked once the taint expires",
          reg.is_read_restricted(key) is False)
    reg.mark_secret_entered(key)
    clock.advance(S.SECRET_TAINT_TTL_S - 10)
    reg.mark_secret_entered(key)
    clock.advance(20)
    check("re-marking refreshes the 15 minutes",
          reg.is_read_restricted(key) is True)
    try:
        reg.require_read_allowed(key)
        refusal = ""
    except S.SecretPageReadRestrictedError as exc:
        refusal = str(exc)
    check("require_read_allowed raises the honest refusal",
          bool(refusal) and "read paused" in refusal.lower())
    check("the refusal names the target but no secret",
          key in refusal and "password" not in refusal.lower())
    reg.clear_key(key)
    check("clear_key unlocks it immediately", reg.is_read_restricted(key) is False)
    check("an empty mark is a no-op", (reg.mark_secret_entered("") or True) and
          reg.is_read_restricted("") is False)

    small = S.SecretPageTaintRegistry(clock=clock, max_keys=3)
    for i in range(4):
        small.mark_secret_entered(f"url:https://example.com/p{i}")
    keys = small.active_keys()
    check("the table is bounded and evicts the oldest key",
          len(keys) == 3 and keys[0] == "url:https://example.com/p1", keys)
    status = small.status()
    check("status is counts and addresses only",
          status["active"] == 3 and status["ttl_seconds"] == int(S.SECRET_TAINT_TTL_S)
          and isinstance(status["keys"], list) and len(status["keys"]) == 3)
    small.clear_all()
    check("clear_all empties the table", small.active_keys() == ())




# --- 3. the card -------------------------------------------------------------

def t_handoff_card():
    clock = Clock()
    coord, taint = make_coordinator(clock)
    plain = S.VerifiedTargetSnapshot(
        target_key="url:https://github.com/login", kind="browser",
        display_origin="https://github.com/login", is_https=True,
        is_password_field=False, control_id="input-1", agent_claimed_purpose="x")
    check("a card cannot be raised for a non-password control",
          raises(S.SecretHandoffVoidedError,
                 lambda: coord.create_handoff_card(snapshot=plain)))

    snap = browser_snapshot(clock, purpose="sign in\n to github")
    card = coord.create_handoff_card(snapshot=snap)
    check("the card id is a prefixed opaque handle",
          isinstance(card["handoff_id"], str) and card["handoff_id"].startswith("sh_"),
          card.get("handoff_id"))
    check("the card shows the host-verified origin",
          card["verified_target"] == "https://github.com/login")
    check("the card says the agent purpose is untrusted",
          card["agent_purpose_is_untrusted"] is True)
    check("the agent purpose is cleaned and shown as a note",
          card["agent_claimed_purpose"] == "sign in to github")
    check("the card is PC-only", card["from_this_pc_only"] is True)
    check("the card expires in 180 seconds", card["expires_in_seconds"] == 180)
    check("the card contains no secret-bearing key",
          not any("secret" in k.lower() for k in card), list(card))
    check("one pending card is counted", coord.pending_count() == 1)

    second = browser_snapshot(clock, url="https://gitlab.com/users/sign_in")
    card2 = coord.create_handoff_card(snapshot=second)
    check("a second card gets its own id", card2["handoff_id"] != card["handoff_id"])
    check("http is shown as not encrypted",
          coord.create_handoff_card(snapshot=browser_snapshot(
              clock, url="http://example.com/login"))["is_https"] is False)

    tight, _ = make_coordinator(clock, max_pending_cards=2)
    tight.create_handoff_card(snapshot=browser_snapshot(clock, url="https://a.example/login"))
    tight.create_handoff_card(snapshot=browser_snapshot(clock, url="https://b.example/login"))
    check("a bounded number of cards may wait",
          raises(S.SecretHandoffVoidedError, lambda: tight.create_handoff_card(
              snapshot=browser_snapshot(clock, url="https://c.example/login"))))
    clock.advance(S.HANDOFF_CARD_TTL_S + 1)
    check("expired cards stop counting as pending", tight.pending_count() == 0)


# --- 4. the fill -------------------------------------------------------------

def t_execute_success():
    clock = Clock()
    coord, taint = make_coordinator(clock)
    snap = browser_snapshot(clock, purpose="sign in")
    card = coord.create_handoff_card(snapshot=snap)
    seen = {}

    def type_into(control_id: str, value: str) -> None:
        seen["control"] = control_id
        seen["value"] = value
        seen["tainted_before_typing"] = taint.is_read_restricted(snap.target_key)

    receipt = coord.execute_owner_fill(
        card["handoff_id"], "correct horse battery staple",
        current_live_snapshot=snap, type_into_control_fn=type_into)
    check("the secret is typed into the named control",
          seen.get("control") == "input-1" and seen.get("value") == "correct horse battery staple")
    check("the taint is marked BEFORE the first character is typed",
          seen.get("tainted_before_typing") is True)
    check("the receipt says filled and tainted",
          receipt["ok"] is True and receipt["filled"] is True
          and receipt["page_read_tainted"] is True)
    check("the receipt keeps the taint duration",
          receipt["taint_ttl_seconds"] == int(S.SECRET_TAINT_TTL_S))
    check("the receipt names the verified target, not the secret",
          receipt["verified_target"] == "https://github.com/login"
          and "horse" not in json.dumps(receipt))
    check("the card is consumed exactly once",
          coord.pending_count() == 0 and raises(
              S.SecretHandoffVoidedError, lambda: coord.execute_owner_fill(
                  card["handoff_id"], "again", current_live_snapshot=snap,
                  type_into_control_fn=lambda *a: None)))
    check("the page is read-locked for 15 minutes after typing",
          taint.is_read_restricted(snap.target_key) is True)
    clock.advance(S.SECRET_TAINT_TTL_S + 1)
    check("the page becomes readable when the taint expires",
          taint.is_read_restricted(snap.target_key) is False)


def t_execute_voids():
    clock = Clock()
    typed = []

    def fresh(**overrides):
        coord, taint = make_coordinator(clock)
        snap = browser_snapshot(clock, purpose="sign in")
        card = coord.create_handoff_card(snapshot=snap)
        args = dict(current_live_snapshot=snap,
                    type_into_control_fn=lambda c, v: typed.append((c, v)))
        args.update(overrides)
        return coord, taint, snap, card, args, typed

    coord, taint, snap, card, args, typed = fresh()
    moved = browser_snapshot(clock, url="https://evil.example/login")
    check("a changed page aborts with nothing typed",
          raises(S.SecretHandoffVoidedError, lambda: coord.execute_owner_fill(
              card["handoff_id"], "pw", current_live_snapshot=moved,
              type_into_control_fn=lambda c, v: typed.append((c, v)))))
    check("... and taints nothing", taint.is_read_restricted(moved.target_key) is False)

    coord, taint, snap, card, args, typed = fresh()
    clearer = browser_snapshot(clock, control_id="input-1", password=False)
    check("a control that is no longer password-masked aborts",
          raises(S.SecretHandoffVoidedError, lambda: coord.execute_owner_fill(
              card["handoff_id"], "pw", current_live_snapshot=clearer,
              type_into_control_fn=lambda c, v: typed.append((c, v)))))
    check("... and nothing was typed", typed == [])

    coord, taint, snap, card, args, typed = fresh()
    refocused = browser_snapshot(clock, control_id="search-box")
    check("a changed focused control aborts",
          raises(S.SecretHandoffVoidedError, lambda: coord.execute_owner_fill(
              card["handoff_id"], "pw", current_live_snapshot=refocused,
              type_into_control_fn=lambda c, v: typed.append((c, v)))))
    check("... and nothing was typed", typed == [])

    coord, taint, snap, card, args, typed = fresh()
    check("an empty secret aborts",
          raises(S.SecretHandoffVoidedError, lambda: coord.execute_owner_fill(
              card["handoff_id"], "", **args)))
    check("an oversized secret aborts",
          raises(S.SecretHandoffVoidedError, lambda: coord.execute_owner_fill(
              card["handoff_id"], "x" * (S.SECRET_MAX_CHARS + 1), **args)))
    check("... and nothing was typed", typed == [])

    coord, taint, snap, card, args, typed = fresh()
    check("a card cannot be answered from another PC",
          raises(S.SecretHandoffVoidedError, lambda: coord.execute_owner_fill(
              card["handoff_id"], "pw", from_this_pc=False, **args)))
    check("... and the card is still usable on this PC", coord.pending_count() == 1)

    coord, taint, snap, card, args, typed = fresh()
    clock.advance(S.HANDOFF_CARD_TTL_S + 1)
    check("an expired card aborts",
          raises(S.SecretHandoffVoidedError, lambda: coord.execute_owner_fill(
              card["handoff_id"], "pw", **args)))
    check("... and nothing was typed", typed == [])

    coord, taint, snap, card, args, typed = fresh()
    check("an unknown card id aborts",
          raises(S.SecretHandoffVoidedError, lambda: coord.execute_owner_fill(
              "sh_does_not_exist", "pw", **args)))
    check("cancel drops a pending card",
          coord.abort_handoff(card["handoff_id"]) is True
          and coord.abort_handoff(card["handoff_id"]) is False)

    coord, taint, snap, card, args, typed = fresh()
    def boom(control_id, value):
        typed.append((control_id, value))
        raise RuntimeError("the control refused the text")
    check("a typing failure surfaces without the secret",
          raises(RuntimeError, lambda: coord.execute_owner_fill(
              card["handoff_id"], "pw", current_live_snapshot=snap,
              type_into_control_fn=boom)))
    check("... yet the target is still tainted",
          taint.is_read_restricted(snap.target_key) is True)
    check("... and the card was consumed", coord.pending_count() == 0)

    forced = browser_snapshot(clock)
    object.__setattr__(forced, "kind", "desktop_window")
    coord, taint, snap, card, args, typed = fresh()
    check("a changed target kind aborts",
          raises(S.SecretHandoffVoidedError, lambda: coord.execute_owner_fill(
              card["handoff_id"], "pw", current_live_snapshot=forced,
              type_into_control_fn=lambda c, v: typed.append((c, v)))))

    glass = window_snapshot(clock)
    coord, taint = make_coordinator(clock)
    card = coord.create_handoff_card(snapshot=glass)
    receipt = coord.execute_owner_fill(
        card["handoff_id"], "pw", current_live_snapshot=glass,
        type_into_control_fn=lambda c, v: None)
    check("a desktop window hand-off works and taints by pid+hwnd+class",
          receipt["target_kind"] == "desktop_window"
          and taint.is_read_restricted("hwnd:4812:9001:edit") is True)


# --- 5. no persistence, no surprise imports ----------------------------------

def t_no_persistence():
    source = Path(S.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    opened, printed, bad_imports = [], [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "open":
                opened.append(node.lineno)
            if node.func.id == "print":
                printed.append(node.lineno)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in (
                        "sqlite3", "logging", "requests", "urllib3", "clipboard",
                        "pyperclip", "tkinter", "win32clipboard"):
                    bad_imports.append(alias.name)
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in ("sqlite3", "logging", "requests",
                                             "urllib3", "clipboard", "pyperclip",
                                             "tkinter", "win32clipboard"):
                bad_imports.append(node.module)
    check("the module never opens a file", opened == [], opened)
    check("the module never prints", printed == [], printed)
    check("the module imports no storage, logging or network library",
          bad_imports == [], bad_imports)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    check("the only imports are the standard library essentials",
          imported <= {"__future__", "collections", "secrets", "threading",
                       "time", "urllib", "dataclasses", "typing"} and bool(imported),
          sorted(imported))
    check("nothing in the module writes a temp or database path",
          ("sqlite" not in source.lower()) and ("tempfile" not in source.lower()))
    check("the module imports no clipboard or logging module",
          ("import clipboard" not in source) and ("import logging" not in source)
          and ("win32clipboard" not in source) and ("pyperclip" not in source))


def t_singletons():
    S.reset_for_tests()
    S.mark_secret_entered("url:https://example.com/page")
    check("the process-wide table is the one the wiring will use",
          S.is_read_restricted("url:https://example.com/page") is True)
    S.reset_for_tests()
    check("reset clears the process-wide table",
          S.is_read_restricted("url:https://example.com/page") is False)
    snap = browser_snapshot(Clock())
    card = S.create_handoff_card(snapshot=snap)
    receipt = S.execute_owner_fill(
        card["handoff_id"], "pw",
        current_live_snapshot=snap,
        type_into_control_fn=lambda c, v: None)
    check("the process-wide coordinator carries a module-level hand-off",
          receipt["filled"] is True)
    S.reset_for_tests()


def main():
    print(f"--- secret hand-off --- ({S.__file__})")
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception as exc:  # pragma: no cover - a crash is a failure
                traceback.print_exc()
                check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
