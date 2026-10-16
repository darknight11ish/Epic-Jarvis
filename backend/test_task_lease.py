"""jarvis_task_lease.py: the lease, its four consent boundaries, and the one
thing it must never become - a standing grant.

    python3 test_task_lease.py

WHAT IS PROVEN HERE, all of it on plain dicts with no browser, no desktop, no
phone and no real gate:

  * a lease opens ONLY on a person's yes - a denied, timed-out, notify or auto
    answer opens nothing, and a gate that cannot be reached at all fails
    closed;
  * an ordinary step inside the lease is allowed, and each allow spends one of
    the lease's own steps;
  * and EACH way out of a lease comes back `step_up_ask` rather than acting: a
    step-up verb on the target, a host outside the allowed sites, a password
    field, a card or file control, the step budget, the TTL, revocation, and
    Jarvis's own window, page or Android package.

Nothing here opens a socket, starts a process, writes a file or raises a real
card: every `create()` call is handed a stand-in gate, and the one test that
exercises the REAL default gate does it with `jarvis_gate` made unimportable,
which is the machine that has no gate on it.
"""
import ast
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, require_shipped  # noqa: E402,F401

require_shipped("jarvis_task_lease.py")

import jarvis_task_lease as L  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   Standing in for the gate - nothing below waits for a person
# --------------------------------------------------------------------------

class _Said:
    """As much of `jarvis_gate.Verdict` as this module reads."""

    def __init__(self, allowed=True, tier="ask", outcome="approved", reason=""):
        self.allowed = allowed
        self.tier = tier
        self.outcome = outcome
        self.reason = reason


def yes(*_a, **_k):
    return _Said(True, "ask", "approved", "approved by a human")


def recording():
    """A gate that remembers it was asked, so a check can prove it was NOT."""
    calls = []

    def gate(action, detail, prompt):
        calls.append(action)
        return yes()

    return gate, calls


def fresh(gate=yes, **kw):
    """No leases at all, then exactly one, opened with a stand-in gate."""
    L._reset_for_tests()
    kw.setdefault("goal", "an ordinary errand")
    kw.setdefault("surface", "browser")
    if kw["surface"] == "browser":
        kw.setdefault("allowed_domains", ["example.com"])
    return L.create(gate=gate, **kw)


# --------------------------------------------------------------------------
#   1. opening a lease needs a person
# --------------------------------------------------------------------------

def t_a_lease_opens_only_on_a_persons_yes():
    lease = fresh(goal="find the opening hours")
    check("the lease is open, with an id of its own",
          bool(lease.lease_id) and L.get(lease.lease_id) is lease, lease)
    check("it carries the goal in the owner's own words",
          lease.goal == "find the opening hours", lease.goal)
    check("the default TTL is 300 seconds",
          round(lease.expires_at - lease.created_at) == 300, lease.expires_at - lease.created_at)
    check("the default step budget is 25, and none is spent yet",
          lease.max_steps == 25 and lease.steps_used == 0, lease)
    check("delivery is background unless someone opted in",
          lease.delivery_mode == "background", lease.delivery_mode)
    check("the default actions are the ordinary ones",
          lease.allowed_actions == L.DEFAULT_ACTIONS, sorted(lease.allowed_actions))
    check("a new lease is not revoked", lease.revoked is False)


def t_no_card_no_lease():
    cases = (
        ("denied", lambda *a, **k: _Said(False, "ask", "denied", "denied by a human")),
        ("timed out", lambda *a, **k: _Said(False, "ask", "timed_out", "nobody answered")),
        ("notify, with nobody asked", lambda *a, **k: _Said(True, "notify", "notify", "tier is notify")),
        ("auto, with nobody asked", lambda *a, **k: _Said(True, "auto", "auto", "tier is auto")),
    )
    for what, gate in cases:
        L._reset_for_tests()
        raised = ""
        try:
            L.create("do a thing", "browser", allowed_domains=["example.com"], gate=gate)
        except L.LeaseRefused as exc:
            raised = str(exc)
        check(f"a card answered {what} opens no lease",
              bool(raised) and not L._LEASES,
              f"raised={raised!r} leases={sorted(L._LEASES)}")


def t_a_gate_that_cannot_be_reached_refuses():
    L._reset_for_tests()

    def broken(*_a, **_k):
        raise ImportError("No module named 'jarvis_gate'")

    raised = ""
    try:
        L.create("do a thing", "browser", allowed_domains=["example.com"], gate=broken)
    except L.LeaseRefused as exc:
        raised = str(exc)
    check("a gate that raises opens nothing, and says what happened",
          "jarvis_gate" in raised and not L._LEASES, raised)

    # And the REAL default gate, with jarvis_gate made unimportable for the
    # duration. Not a stand-in for the call: the import itself is blocked,
    # which is the machine that has no gate on it at all.
    import builtins
    real_import = builtins.__import__
    saved = sys.modules.pop("jarvis_gate", None)

    def blocked(name, *a, **k):
        if name == "jarvis_gate":
            raise ImportError("No module named 'jarvis_gate'")
        return real_import(name, *a, **k)

    builtins.__import__ = blocked
    raised = ""
    try:
        L.create("do a thing", "browser", allowed_domains=["example.com"])
    except L.LeaseRefused as exc:
        raised = str(exc)
    finally:
        builtins.__import__ = real_import
        if saved is not None:
            sys.modules["jarvis_gate"] = saved
    check("with no jarvis_gate on the machine, create() refuses rather than opening",
          bool(raised) and not L._LEASES, raised)


# --------------------------------------------------------------------------
#   2. in-lease autonomy: the ordinary step is quiet
# --------------------------------------------------------------------------

def t_an_ordinary_step_inside_the_lease_is_allowed_and_spends_one():
    lease = fresh(goal="read the menu", max_steps=3)
    url = "https://example.com/menu"
    out = [L.check_step(lease.lease_id, {"action": "snapshot", "url": url})
           for _ in range(3)]
    check("every allowed step comes back allow_under_lease",
          [o["verdict"] for o in out] == [L.ALLOW] * 3, out)
    check("remaining_steps counts down from the budget",
          [o["remaining_steps"] for o in out] == [2, 1, 0], out)
    check("steps_used is the number of allows", lease.steps_used == 3, lease.steps_used)


def t_every_step_up_verb_stops_the_step():
    lease = fresh(goal="look at the page")
    words = ["Submit", "Pay", "Purchase", "Buy now", "Checkout", "Place order",
             "Send money", "Transfer", "Delete", "Erase", "Remove", "Uninstall",
             "Publish", "Post", "Send email", "Merge", "Confirm payment",
             "Authorize", "Grant access", "Allow"]
    for word in words:
        out = L.check_step(lease.lease_id,
                           {"action": "click_element", "url": "https://example.com/x",
                            "element": {"label": word}})
        check(f"a control whose own word is {word!r} is a step-up, not a click",
              out.get("verdict") == L.STEP_UP and "high-consequence" in out.get("reason", ""),
              out)
    check("and not one of those spent a step", lease.steps_used == 0, lease.steps_used)


def t_a_host_outside_the_allowed_sites_is_a_step_up():
    lease = fresh(goal="read the page",
                  allowed_domains=["example.com", "shop.example.org"])
    inside = {
        "the exact host": "https://example.com/cart",
        "a subdomain of it": "https://www.example.com/cart",
        "the second allowed site": "https://shop.example.org/item",
    }
    for what, url in inside.items():
        out = L.check_step(lease.lease_id, {"action": "snapshot", "url": url})
        check(f"{what} is inside the lease", out.get("verdict") == L.ALLOW, out)
    outside = {
        "another host entirely": "https://evil.com/x",
        "a host that merely ENDS with an allowed name": "https://notexample.com/x",
        "an allowed name used as a PREFIX of another site": "https://example.com.evil.com/x",
        "a scheme that is not http(s)": "javascript:alert(1)",
        "a file:// address": "file:///C:/Users/pcadmin/notes.txt",
        "an address with no host at all": "about:blank",
    }
    for what, url in outside.items():
        out = L.check_step(lease.lease_id, {"action": "snapshot", "url": url})
        check(f"{what} is refused", out.get("verdict") == L.STEP_UP, out)
    check("no refused step spent a step", lease.steps_used == 3, lease.steps_used)


def t_a_password_field_is_refused():
    lease = fresh(goal="fill in the form")
    cases = {
        "the field says its type is password": {"input_type": "password", "label": "Your name"},
        "the label says Password and the type is silent": {"label": "Password"},
        "the caller flags it as one": {"password": True, "label": "Secret"},
    }
    for what, el in cases.items():
        out = L.check_step(lease.lease_id,
                           {"action": "type_text", "url": "https://example.com/login",
                            "element": el})
        check(f"{what} - refused, and the reason says password",
              out.get("verdict") == L.STEP_UP and "password" in out.get("reason", ""), out)
    out = L.check_step(lease.lease_id,
                       {"action": "type_text", "url": "https://example.com/login",
                        "element": {"input_type": "text", "label": "Your name"}})
    check("an ordinary text box is still allowed", out.get("verdict") == L.ALLOW, out)


def t_a_card_or_file_control_is_refused():
    lease = fresh(goal="buy nothing")
    cases = {
        "a card number field": {"label": "Card number"},
        "the security code": {"label": "CVV"},
        "an expiry box": {"label": "Expiry date"},
        "a file chooser": {"input_type": "file", "label": "Photo"},
        "an Upload button": {"label": "Upload your ID"},
        "a Download link": {"label": "Download the invoice"},
        "a control the caller marks as a download": {"download": True, "label": "Get it"},
    }
    for what, el in cases.items():
        out = L.check_step(lease.lease_id,
                           {"action": "click_element", "url": "https://example.com/x",
                            "element": el})
        check(f"{what} - refused",
              out.get("verdict") == L.STEP_UP
              and ("card" in out.get("reason", "") or "file" in out.get("reason", "")),
              out)
    out = L.check_step(lease.lease_id,
                       {"action": "click_element", "url": "https://example.com/x",
                        "element": {"label": "Next page"}})
    check("an ordinary button is still allowed", out.get("verdict") == L.ALLOW, out)

    # `jarvis_browser_control._lease_payload` sends element["sensitive"] = True
    # for a field its own reader called sensitive (input_type in password,
    # hidden, file) and passes `input_type` through only for the password half.
    # A file input whose label is "Photo" is the case that needs this flag.
    out = L.check_step(lease.lease_id,
                       {"action": "click_element", "url": "https://example.com/x",
                        "element": {"name": "Photo", "sensitive": True}})
    check("a field the caller's own reader called sensitive is refused, even "
          "when its label says nothing",
          out.get("verdict") == L.STEP_UP and "sensitive" in out.get("reason", ""), out)


# --------------------------------------------------------------------------
#   3. the three ways a lease runs out
# --------------------------------------------------------------------------

def t_the_step_budget_is_a_real_ceiling():
    lease = fresh(goal="two clicks", max_steps=2)
    step = {"action": "click_element", "url": "https://example.com/x",
            "element": {"label": "Next"}}
    check("the first step is allowed", L.check_step(lease.lease_id, step)["verdict"] == L.ALLOW)
    check("the second step is allowed", L.check_step(lease.lease_id, step)["verdict"] == L.ALLOW)
    out = L.check_step(lease.lease_id, step)
    check("the step past the budget is refused, and names the budget",
          out.get("verdict") == L.STEP_UP and "2 steps" in out.get("reason", ""), out)
    check("and that refusal did not spend a step either", lease.steps_used == 2, lease.steps_used)
    fresh_lease = fresh(goal="one refusal", max_steps=1)
    L.check_step(fresh_lease.lease_id,
                 {"action": "click_element", "url": "https://example.com/x",
                  "element": {"label": "Delete"}})
    check("a refused step leaves the budget exactly where it was",
          fresh_lease.steps_used == 0 and fresh_lease.remaining_steps() == 1, fresh_lease)


def t_the_ttl_expires_and_a_longer_one_is_clamped():
    lease = fresh(goal="a short errand", ttl_seconds=60)
    check("a TTL inside the ceiling is honoured",
          round(lease.expires_at - lease.created_at) == 60, lease.expires_at - lease.created_at)
    long_one = fresh(goal="all day", ttl_seconds=86400)
    check("a TTL longer than the hard ceiling is CLAMPED to 900, not honoured",
          round(long_one.expires_at - long_one.created_at) == 900,
          long_one.expires_at - long_one.created_at)
    check("the hard ceiling really is 900 seconds", L.MAX_TTL_SECONDS == 900.0)
    tiny = fresh(goal="a moment", ttl_seconds=0)
    check("a TTL of zero is clamped UP, never to forever",
          round(tiny.expires_at - tiny.created_at) == 1,
          tiny.expires_at - tiny.created_at)
    # A lease of its own for this, because `fresh()` starts from no leases and
    # so the earlier one above is no longer in the module's dict.
    expiring = fresh(goal="expires now", ttl_seconds=30)
    expiring.expires_at = time.time() - 1
    out = L.check_step(expiring.lease_id, {"action": "snapshot", "url": "https://example.com/x"})
    check("an expired lease refuses every step, and says it expired",
          out.get("verdict") == L.STEP_UP and "expired" in out.get("reason", ""), out)


def t_revocation_is_immediate_and_one_way():
    lease = fresh(goal="stop it")
    check("revoke() reports that it revoked this lease", L.revoke(lease.lease_id) is True)
    out = L.check_step(lease.lease_id, {"action": "snapshot", "url": "https://example.com/x"})
    check("a revoked lease refuses every step, and says it was revoked",
          out.get("verdict") == L.STEP_UP and "revoked" in out.get("reason", ""), out)
    check("revoking it twice is not an error, and does nothing the second time",
          L.revoke(lease.lease_id) is False)
    check("revoking an id nobody opened reports that too", L.revoke("nope") is False)
    check("a lease that was never opened refuses too",
          L.check_step("nope", {"action": "snapshot", "url": "https://example.com/x"})
          .get("verdict") == L.STEP_UP)


# --------------------------------------------------------------------------
#   4. Jarvis's own surfaces are never a target
# --------------------------------------------------------------------------

def t_jarvis_own_window_is_never_a_target():
    lease = L.create("click the settings button", "desktop",
                     allowed_windows=[(4242, 1337), (99, 88)], gate=yes)
    for title in ("Jarvis", "Jarvis - Brain", "Jarvis Desktop Widget", "jarvis-desktop.exe"):
        out = L.check_step(lease.lease_id,
                           {"action": "snapshot", "pid": 4242, "hwnd": 1337,
                            "window_title": title})
        check(f"a lease over the window titled {title!r} is refused, whoever asked",
              out.get("verdict") == L.STEP_UP and "Jarvis's own" in out.get("reason", ""),
              out)
    out = L.check_step(lease.lease_id,
                       {"action": "snapshot", "pid": 99, "hwnd": 88,
                        "window_title": "Notepad"})
    check("an ordinary window inside the lease is still allowed",
          out.get("verdict") == L.ALLOW, out)

    hud = L.create("read the HUD", "browser",
                   allowed_domains=["127.0.0.1", "localhost"], gate=yes)
    out = L.check_step(hud.lease_id,
                       {"action": "snapshot", "url": "http://127.0.0.1:8765/jarvis_hud.html"})
    check("one of Jarvis's own pages is refused even on an allowed host",
          out.get("verdict") == L.STEP_UP and "Jarvis's own" in out.get("reason", ""), out)

    phone = L.create("look at the phone", "android", gate=yes)
    out = L.check_step(phone.lease_id, {"action": "snapshot", "package": "com.jarvis.client"})
    check("the phone's own Jarvis app is refused as a target",
          out.get("verdict") == L.STEP_UP and "Jarvis's own" in out.get("reason", ""), out)


def t_a_window_outside_the_lease_is_refused():
    lease = L.create("type in the notes app", "desktop", allowed_windows=[(10, 20)], gate=yes)
    cases = {
        "a window nobody named": {"pid": 11, "hwnd": 20},
        "the same pid with another window": {"pid": 10, "hwnd": 21},
        "a step that names no window at all": {},
        "a step that names only a pid": {"pid": 10},
    }
    for what, extra in cases.items():
        step = {"action": "snapshot", "window_title": "Notepad"}
        step.update(extra)
        out = L.check_step(lease.lease_id, step)
        check(f"{what} is refused", out.get("verdict") == L.STEP_UP, out)
    out = L.check_step(lease.lease_id,
                       {"action": "snapshot", "pid": 10, "hwnd": 20,
                        "window_title": "Notepad"})
    check("the (pid, hwnd) it does name is allowed", out.get("verdict") == L.ALLOW, out)


def t_an_android_step_is_refused_until_something_binds_its_target():
    lease = L.create("check the phone", "android", gate=yes)
    out = L.check_step(lease.lease_id, {"action": "snapshot", "label": "Messages"})
    check("an android lease opens, and refuses every step it cannot bind to a target",
          out.get("verdict") == L.STEP_UP and "android" in out.get("reason", ""), out)
    check("and the surface really is one of the three the module names",
          lease.surface in L.SURFACES, lease.surface)


# --------------------------------------------------------------------------
#   5. a lease carries no open-ended grant
# --------------------------------------------------------------------------

def t_a_lease_carries_no_open_ended_grant():
    empty = L.create("nothing in particular", "browser", allowed_domains=[], gate=yes)
    out = L.check_step(empty.lease_id, {"action": "snapshot", "url": "https://example.com/x"})
    check("a browser lease with no sites allows NOTHING - an empty list is not 'any site'",
          out.get("verdict") == L.STEP_UP, out)

    narrowed = fresh(goal="read only", allowed_actions=["snapshot"])
    out = L.check_step(narrowed.lease_id,
                       {"action": "click_element", "url": "https://example.com/x",
                        "element": {"label": "Next"}})
    check("an action the lease does not name is refused, and the reason names it",
          out.get("verdict") == L.STEP_UP and "click_element" in out.get("reason", ""), out)
    out = L.check_step(narrowed.lease_id, {"action": "snapshot", "url": "https://example.com/x"})
    check("the one action it does name is allowed", out.get("verdict") == L.ALLOW, out)
    out = L.check_step(narrowed.lease_id, {"action": "", "url": "https://example.com/x"})
    check("a step with no action at all is refused", out.get("verdict") == L.STEP_UP, out)


def t_create_refuses_what_it_cannot_bound():
    gate, calls = recording()
    cases = (
        ("a lease with no goal", dict(goal="", surface="browser", allowed_domains=["example.com"])),
        ("a surface that is not one of the three", dict(goal="x", surface="carrier-pigeon")),
        ("a step budget of zero",
         dict(goal="x", surface="browser", allowed_domains=["example.com"], max_steps=0)),
        ("an action this module has never heard of",
         dict(goal="x", surface="browser", allowed_domains=["example.com"],
              allowed_actions=["snapshot", "place_bet"])),
        ("no actions at all",
         dict(goal="x", surface="browser", allowed_domains=["example.com"],
              allowed_actions=[])),
        ("a site named as an address rather than a host",
         dict(goal="x", surface="browser", allowed_domains=["https://example.com"])),
        ("foreground delivery with nobody's explicit opt-in",
         dict(goal="x", surface="browser", allowed_domains=["example.com"],
              delivery_mode="foreground")),
        ("a delivery mode that is not background or foreground",
         dict(goal="x", surface="browser", allowed_domains=["example.com"],
              delivery_mode="telepathy")),
    )
    for what, kw in cases:
        L._reset_for_tests()
        raised = ""
        try:
            L.create(gate=gate, **kw)
        except ValueError as exc:
            raised = str(exc)
        check(f"{what} is refused", bool(raised) and not L._LEASES, raised)
    check("... and not one of those raised a card on the way out", calls == [], calls)

    fg = L.create(goal="watch it happen", surface="browser", allowed_domains=["example.com"],
                  delivery_mode="foreground", foreground_opt_in=True, gate=gate)
    check("foreground delivery IS allowed with the explicit opt-in",
          fg.delivery_mode == "foreground", fg.delivery_mode)


# --------------------------------------------------------------------------
#   6. the shape of a step, and the shape of the module
# --------------------------------------------------------------------------

def t_the_step_contract_is_read_the_way_it_is_documented():
    lease = fresh(goal="read a page")
    out = L.check_step(lease.lease_id,
                       {"action": "click_element", "url": "https://example.com/x",
                        "element": {"label": "Next page"}})
    check("an element described in its own `element` dict is read",
          out.get("verdict") == L.ALLOW, out)
    out = L.check_step(lease.lease_id,
                       {"action": "click_element", "url": "https://example.com/x",
                        "label": "Next page"})
    check("a step that is its own element description is read too",
          out.get("verdict") == L.ALLOW, out)
    out = L.check_step(lease.lease_id,
                       {"action": "click_element", "url": "https://example.com/x",
                        "element": {"label": "Continue"}, "value": "pay now"})
    check("the words a step would TYPE are checked, not only the control's label",
          out.get("verdict") == L.STEP_UP, out)
    out = L.check_step(lease.lease_id, "snapshot")
    check("a step that is not a dict is refused rather than raising",
          out.get("verdict") == L.STEP_UP, out)
    out = L.check_step(lease.lease_id, {"action": "snapshot"})
    check("a browser step that names no address is refused",
          out.get("verdict") == L.STEP_UP, out)


def t_the_two_copies_are_the_same_file():
    ours = Path(L.__file__).read_bytes().replace(b"\r\n", b"\n")
    base_path = REPO / "jarvis-backend" / "jarvis_task_lease.py"
    check("the published base holds this module too", base_path.is_file(), str(base_path))
    if base_path.is_file():
        base = base_path.read_bytes().replace(b"\r\n", b"\n")
        check("backend/ and jarvis-backend/ hold the same bytes (the twin rule)",
              ours == base, "the two copies differ")


def t_the_module_is_inert_and_imports_the_standard_library():
    L._reset_for_tests()
    check("no lease exists until one is opened", L._LEASES == {})
    fresh(goal="something")
    check("... and opening one keeps it in the module's own dict",
          len(L._LEASES) == 1, sorted(L._LEASES))
    L._reset_for_tests()
    check("the test hook clears them again", L._LEASES == {})

    tree = ast.parse(Path(L.__file__).read_text(encoding="utf-8"))
    # MODULE LEVEL only (tree.body). The lazy `import jarvis_gate` inside
    # `_default_gate` is checked separately below, and an ast.walk() would
    # report it here as though the module needed the gate to load.
    top = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            top.add(node.module.split(".")[0])
    outside = top - set(sys.stdlib_module_names)
    check("it imports the standard library and nothing else at module level",
          not outside, sorted(outside))
    check("... and jarvis_gate is NOT imported at module level",
          "jarvis_gate" not in top, sorted(top))
    fn = next((n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == "_default_gate"), None)
    lazy = fn is not None and any(
        isinstance(n, ast.Import) and any(a.name == "jarvis_gate" for a in n.names)
        for n in ast.walk(fn))
    check("jarvis_gate is imported lazily, inside _default_gate, so this module "
          "loads on a machine that has no gate", lazy)
    src = Path(L.__file__).read_text(encoding="utf-8")
    for banned in ("subprocess", "socket", "urllib.request", "requests"):
        check(f"it never names {banned}", banned not in top and banned not in src)


if __name__ == "__main__":
    for fn in (t_a_lease_opens_only_on_a_persons_yes,
               t_no_card_no_lease,
               t_a_gate_that_cannot_be_reached_refuses,
               t_an_ordinary_step_inside_the_lease_is_allowed_and_spends_one,
               t_every_step_up_verb_stops_the_step,
               t_a_host_outside_the_allowed_sites_is_a_step_up,
               t_a_password_field_is_refused,
               t_a_card_or_file_control_is_refused,
               t_the_step_budget_is_a_real_ceiling,
               t_the_ttl_expires_and_a_longer_one_is_clamped,
               t_revocation_is_immediate_and_one_way,
               t_jarvis_own_window_is_never_a_target,
               t_a_window_outside_the_lease_is_refused,
               t_an_android_step_is_refused_until_something_binds_its_target,
               t_a_lease_carries_no_open_ended_grant,
               t_create_refuses_what_it_cannot_bound,
               t_the_step_contract_is_read_the_way_it_is_documented,
               t_the_two_copies_are_the_same_file,
               t_the_module_is_inert_and_imports_the_standard_library):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
