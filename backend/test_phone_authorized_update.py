"""test_phone_authorized_update.py - the phone asks for a desktop update, and ONE
card decides (2026-11-18; backend/jarvis_update.py).

    python -B backend/test_phone_authorized_update.py

The owner's ask: "the desktop program can update itself, but only at the PC,
and only after Windows Hello there. I want the phone to be able to ask for that
same update, with the phone's own fingerprint."

NO REAL NETWORK, NO POWERSHELL, NO CARD ANSWERED. Every version read is a fake
this file supplies, every gate call is a fake, and the detached helper is a
recorder, so a run of this suite downloads nothing, installs nothing and starts
nothing. What it proves, in the order the brief asks for it:

 1. THE REQUEST RAISES A CARD AND DOWNLOADS NOTHING BEFORE THE YES. One
    `jarvis_gate.check` call under `desktop_update` at tier "ask", the card's
    words are the module's own, and the update starts only after the gate
    answered "approved".
 2. A REFUSED REQUEST INSTALLS NOTHING AND SAYS SO. A denied card, a timed-out
    card, a gate that raised, a loosened tier, a request with nothing newer, a
    second request while one is waiting, an update already running, a lock the
    desktop holds - each changes nothing, starts nothing, and says why in
    words.
 3. THE PHONE'S ALLOWLIST AND THE CORE'S TOKEN/ORIGIN GATE ARE ENFORCED. Both
    routes go through the loader's own `origin_ok`/`token_ok` callbacks, both
    refuse a cross-origin request and a bad token, no route is keyless, and the
    phone's own copy of the PC-only set (`PcOnlyActions` / the generated
    contract) no longer holds `desktop_update` - which is what lets its
    fingerprint approve it - while the action stays risky for everyone else.
 4. THE ACTION IS `desktop_update`, TIER `ask`, ASSERTED FROM THE CLASSIFICATION
    ITSELF (`jarvis_framework.action_tier`, the shipped TOML, `HARD_LIMITS`,
    `MUST_ASK`), never from a sentence in a doc.
 5. THE CARD'S WORDS ARE THE ONES A PERSON READS. The exact string is asserted,
    the gate's own title and summary are the written ones, and a jargon list is
    refused.
 6. NO PATH IN THE MODULE CAN START AN UPDATE WITHOUT AN APPROVAL. Every
    verdict that is not a person's yes is walked, and the module's own source is
    read to prove the only start sits after that check.

    python -B backend/jarvis_update.py        # the same status, for a person
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

# Hermetic, like the rest of the suite: this suite's state file, its locks and
# (if anything ever wrote one) its audit log land in TMP, never in the owner's
# own folder. Set BEFORE the first import of anything that reads them.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-phone-update-"))
os.environ["OPENJARVIS_HOME"] = str(_TMP)
os.environ["JARVIS_HOME"] = str(_TMP)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE / "rebuilt"))

from _where import require_shipped  # noqa: E402

require_shipped("jarvis_update.py")
import jarvis_update as U  # noqa: E402
import jarvis_owner_check as OC  # noqa: E402
import jarvis_card_words as W  # noqa: E402
import jarvis_asks_first as AF  # noqa: E402

SHIPPED_TOML = HERE / "rebuilt" / "jarvis-framework.toml"
BASE_TOML = ROOT / "jarvis-backend" / "jarvis-framework.toml"
BASE_GATE = ROOT / "jarvis-backend" / "jarvis_gate.py"
UPDATE_SCRIPT = ROOT / "scripts" / "update-jarvis.ps1"
APPLY_SCRIPT = ROOT / "scripts" / "apply-patches.ps1"
API_DOC = ROOT / "docs" / "JARVIS-API.md"
ARCH_DOC = ROOT / "docs" / "ARCHITECTURE.md"
CONTRACT = ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / \
    "contract" / "card-words-cases.json"

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


# ---------------------------------------------------------------------------
# The fakes: every version, gate, spawn and helper this suite uses
# ---------------------------------------------------------------------------

INSTALLED = {"version": "0.2.456", "why": ""}
PUBLISHED = {"version": "0.2.460", "why": ""}


def versions(installed=None, published=None, calls=None):
    """The two version reads, as callables the module can inject."""
    def installed_now():
        if calls is not None:
            calls.append("installed")
        return dict(INSTALLED if installed is None else installed)

    def published_now():
        if calls is not None:
            calls.append("published")
        return dict(PUBLISHED if published is None else published)
    return installed_now, published_now


class Verdict:
    """What `jarvis_gate.check` returns, in the shape the module reads."""

    def __init__(self, allowed=False, tier="ask", outcome="denied", reason="",
                 request_id="req-1"):
        self.allowed = allowed
        self.tier = tier
        self.outcome = outcome
        self.reason = reason
        self.request_id = request_id


def gate_returning(verdict=None, record=None, raises=None):
    """A stand-in gate: records its call, then answers (or raises)."""
    def gate(action, detail, prompt):
        if record is not None:
            record.append({"action": action, "detail": dict(detail),
                           "prompt": prompt})
        if raises is not None:
            raise raises
        return verdict if verdict is not None else Verdict()
    return gate


def run_inline(fn):
    """`spawn`: run the card thread here, so every case is deterministic."""
    fn()


def helper_recorder(why=None):
    """A stand-in for the detached helper: records, starts nothing."""
    calls = []

    def start(doc):
        calls.append(dict(doc))
        return why
    start.calls = calls
    return start


def clean_files():
    """No state, lock or helper file left by an earlier case."""
    for path in (U.state_path(), U.helper_lock_path(), U.shared_lock_path()):
        try:
            path.unlink()
        except OSError:
            pass


def reset_module():
    """The two memory slots this module keeps, cleared between cases."""
    U._PENDING = None
    U._LAST = None


def ask(**kw):
    """`request()` with every dependency injected and nothing real touched."""
    clean_files()
    reset_module()
    installed_now, published_now = kw.pop("versions_pair", versions())
    kw.setdefault("installed_now", installed_now)
    kw.setdefault("published_now", published_now)
    kw.setdefault("backend", lambda: Path("C:/fake/backend"))
    kw.setdefault("script", lambda: Path("C:/fake/repo/scripts/update-jarvis.ps1"))
    kw.setdefault("state", {})
    kw.setdefault("spawn", run_inline)
    return U.request(**kw)


# ---------------------------------------------------------------------------
# 1. the request raises a card, and downloads nothing before the yes
# ---------------------------------------------------------------------------

def t_the_request_raises_one_card_under_the_action_that_exists():
    seen, helper = [], helper_recorder()
    state = {}
    code, out = ask(body={}, gate=gate_returning(
        Verdict(allowed=True, tier="ask", outcome="approved"), record=seen),
        spawn_helper=helper, state=state)

    check("the request is accepted with a waiting card (202)", code == 202, (code, out))
    check("the answer names the action that already exists",
          out.get("action") == "desktop_update", out)
    check("the answer says a card is waiting", out.get("pending") is True, out)
    check("exactly ONE card is raised", len(seen) == 1, seen)
    check("the card is raised under desktop_update, at tier 'ask' (the gate's)",
          seen and seen[0]["action"] == "desktop_update", seen)
    check("the card's own words are the module's one sentence",
          seen and seen[0]["prompt"] == U.describe("0.2.456", "0.2.460"),
          seen[0]["prompt"] if seen else None)
    check("the card says the download leaves this PC (it fetches the release)",
          seen and seen[0]["detail"].get("leaves_this_pc") is True, seen)
    check("the card carries no field a command, path or version could ride in",
          seen and set(seen[0]["detail"]) == {
              "text", "from", "to", "what", "leaves_this_pc", "raised_by"},
          sorted(seen[0]["detail"]) if seen else None)
    check("... and the module's own script path is not on the card either",
          seen and "script" not in seen[0]["detail"]
          and "backend" not in seen[0]["detail"])
    check("the update starts only after the approval: the helper saw one doc",
          len(helper.calls) == 1, helper.calls)
    check("the helper was given the script and the backend this module resolved",
          helper.calls and helper.calls[0]["script"].endswith("update-jarvis.ps1")
          and helper.calls[0]["backend"] == str(Path("C:/fake/backend")),
          helper.calls[0] if helper.calls else None)
    check("the helper was given the card's own id, from the gate's verdict",
          helper.calls and helper.calls[0]["request_id"] == "req-1", helper.calls)
    check("the card's outcome is recorded as started, not as an update",
          U._LAST and U._LAST.get("outcome") == "started", U._LAST)


def t_nothing_downloads_or_runs_before_the_yes():
    """The module itself fetches nothing and runs nothing but the one script."""
    src = (HERE / "jarvis_update.py").read_text(encoding="utf-8")
    code = src.split('"""', 2)[-1]          # the docstring says what it does not do
    for forbidden in ("urllib.request", "urllib.error", "http.client", "requests.",
                      "urlopen", "socket", "Invoke-WebRequest", "Start-BitsTransfer",
                      "DownloadFile", "msiexec", "installer.exe", "os.system",
                      "shell=True"):
        check(f"the module's code never mentions {forbidden!r}",
              forbidden not in code, [l for l in code.splitlines() if forbidden in l][:3])
    check("the one urllib import is the string parser (parsing a path, no network)",
          code.count("urllib") == 1
          and "from urllib.parse import urlsplit" in code,
          [l.strip() for l in code.splitlines() if "urllib" in l])
    check("'subprocess' is used at the two places that start the helper, and "
          "nowhere else", code.count("subprocess.Popen(") == 2,
          [l.strip() for l in code.splitlines() if "subprocess." in l])
    tree = ast.parse(src)
    starts = [n for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr in ("Popen", "run", "call") and isinstance(
                  n.func.value, ast.Name) and n.func.value.id == "subprocess"]
    check("... and both are Popen (no shell, no check=True, no captured pipe "
          "from a request)", len(starts) == 2 and all(
              isinstance(n.func, ast.Attribute) and n.func.attr == "Popen"
              for n in starts), [n.func.attr for n in starts])


def t_the_request_body_cannot_change_what_runs():
    seen, helper = [], helper_recorder()
    code, out = ask(body={"script": "C:\\evil.ps1", "backend": "C:\\Windows",
                          "version": "9.9.9", "cmd": "format c: /q"},
                    gate=gate_returning(Verdict(allowed=True, tier="ask",
                                               outcome="approved"), record=seen),
                    spawn_helper=helper)
    check("a body full of arguments is accepted and ignored", code == 202, (code, out))
    joined = json.dumps(seen[0]["detail"]) if seen else ""
    check("nothing from the body reaches the card",
          "evil" not in joined and "format" not in joined and "9.9.9" not in joined,
          joined[:300])
    check("the helper still got the module's own script and backend",
          helper.calls and helper.calls[0]["script"].endswith("update-jarvis.ps1")
          and helper.calls[0]["backend"] == str(Path("C:/fake/backend")), helper.calls)


# ---------------------------------------------------------------------------
# 2. a refused request installs nothing, and says so
# ---------------------------------------------------------------------------

def _not_started(gate=None, **kw):
    helper = helper_recorder()
    installed_now, published_now = versions()
    code, out = ask(gate=gate, spawn_helper=helper,
                    installed_now=kw.pop("installed_now", installed_now),
                    published_now=kw.pop("published_now", published_now), **kw)
    return code, out, helper, helper.calls


def t_a_denied_card_installs_nothing():
    code, out, helper, calls = _not_started(
        gate=gate_returning(Verdict(allowed=False, tier="ask", outcome="denied")))
    check("a denied card starts nothing", calls == [], calls)
    check("... and the module records the denial, never 'started'",
          U._LAST and U._LAST.get("outcome") == "denied", U._LAST)
    check("... and the request itself had already returned its waiting answer",
          code == 202, (code, out))


def t_a_timed_out_card_installs_nothing():
    code, out, helper, calls = _not_started(
        gate=gate_returning(Verdict(allowed=False, tier="ask", outcome="timed_out")))
    check("a card nobody answered starts nothing", calls == [], calls)
    check("... and it is recorded as timed out, not refused",
          U._LAST and U._LAST.get("outcome") == "timed_out", U._LAST)


def t_a_gate_that_raises_installs_nothing():
    code, out, helper, calls = _not_started(
        gate=gate_returning(raises=RuntimeError("no gate here")))
    check("a gate that fails starts nothing", calls == [], calls)
    check("... and says the gate failed rather than that a person said yes",
          U._LAST and U._LAST.get("outcome") == "refused"
          and "gate" in str(U._LAST.get("reason")), U._LAST)


def t_a_loosened_tier_installs_nothing():
    for tier in ("auto", "notify", "never", "unknown"):
        code, out, helper, calls = _not_started(
            gate=gate_returning(Verdict(allowed=True, tier=tier, outcome="approved")))
        check(f"a gate that answered at tier {tier!r} starts nothing", calls == [], calls)
        check(f"... and that one is refused, not approved, in words",
              U._LAST and U._LAST.get("outcome") == "refused"
              and tier in str(U._LAST.get("reason")), U._LAST)


def t_an_allowed_flag_alone_is_not_an_approval():
    for allowed, outcome, label in (
            (False, "approved", "allowed False but outcome approved"),
            (True, "refused", "allowed True but outcome refused"),
            (True, None, "allowed True with no outcome and a loose tier")):
        tier = "ask" if outcome else "auto"
        verdict = Verdict(allowed=allowed, tier=tier, outcome=outcome)
        if outcome is None:
            verdict.outcome = None
        code, out, helper, calls = _not_started(gate=gate_returning(verdict))
        check(f"nothing starts when {label}", calls == [], calls)


def t_every_refusal_says_why_and_starts_nothing():
    cases = [
        ("nothing newer", dict(versions_pair=versions(
            {"version": "0.2.460", "why": ""}, {"version": "0.2.460", "why": ""})),
         "there is nothing newer"),
        ("a version neither side can read", dict(versions_pair=versions(
            {"version": None, "why": "cannot tell: no recorded version"},
            PUBLISHED)), "cannot tell whether there is a newer version"),
        ("no backend folder", dict(backend=lambda: None),
         "cannot find the Jarvis backend folder"),
        ("no updater script", dict(script=lambda: None),
         "cannot find the folder this repository is cloned into"),
        ("a tier that is not ask", dict(tier_of=lambda action: "auto"),
         "needs a person to say yes"),
    ]
    for label, kw, expected in cases:
        seen, helper = [], helper_recorder()
        installed_now, published_now = kw.pop("versions_pair", versions())
        code, out = ask(gate=gate_returning(record=seen), spawn_helper=helper,
                        installed_now=installed_now, published_now=published_now,
                        **kw)
        check(f"{label}: refused with 409", code == 409, (code, out))
        check(f"{label}: says {expected!r}", expected in str(out.get("error")), out)
        check(f"{label}: no card was raised", seen == [], seen)
        check(f"{label}: nothing was started", helper.calls == [], helper.calls)
        check(f"{label}: the answer says ok is False", out.get("ok") is False, out)


def t_a_second_request_while_one_waits_changes_nothing():
    clean_files()
    reset_module()
    installed_now, published_now = versions()
    # A card already waiting is the module's own memory slot; put one there and
    # leave it, exactly as a real pending request would (`ask()` would clear it).
    U._PENDING = {"id": "waiting", "from": "0.2.456", "to": "0.2.460",
                  "script": "s", "backend": "b",
                  "since": __import__("time").time(),
                  "since_m": __import__("time").monotonic(), "timeout": 900.0}
    seen, helper = [], helper_recorder()
    code, out = U.request(gate=gate_returning(record=seen), spawn_helper=helper,
                          installed_now=installed_now,
                          published_now=published_now,
                          backend=lambda: Path("C:/fake/backend"),
                          script=lambda: Path("C:/fake/repo/scripts/update-jarvis.ps1"),
                          state={})
    check("a second ask while one card waits is refused (409)", code == 409, (code, out))
    check("... and says which card to answer", "already waiting" in str(out.get("error")),
          out)
    check("... and marks it as pending, with the seconds left",
          out.get("pending") is True and isinstance(out.get("expires_in"), int), out)
    check("... and raises no second card", seen == [], seen)
    check("... and starts nothing", helper.calls == [], helper.calls)
    reset_module()


def t_a_running_or_locked_update_is_refused():
    reset_module()
    live = {"phase": "patching", "pid": os.getpid(), "started_at": 1.0,
            "updated_at": __import__("time").time()}
    code, out, helper, calls = _not_started(gate=gate_returning(), state=live)
    check("a state file in flight with a live pid refuses a new ask (409)",
          code == 409, (code, out))
    check("... and names the phase in plain words",
          out.get("phase") == "patching"
          and out.get("what") == U.PHASE_WORDS["patching"], out)
    check("... and starts nothing", calls == [], calls)

    # The PC's shared lock, held by a live pid with a fresh heartbeat. Called
    # through `U.request` and not `ask()`, because `ask()` clears this file.
    clean_files()
    reset_module()
    now = __import__("time").time()
    U._write_json(U.shared_lock_path(),
                  {"pid": os.getpid(), "started_at": now - 60,
                   "updated_at": now - 5, "pace": "balanced"})
    installed_now, published_now = versions()
    helper = helper_recorder()
    code, out = U.request(gate=gate_returning(), spawn_helper=helper,
                          installed_now=installed_now,
                          published_now=published_now,
                          backend=lambda: Path("C:/fake/backend"),
                          script=lambda: Path("C:/fake/repo/scripts/update-jarvis.ps1"),
                          state={})
    check("the desktop's own update lock refuses a new ask (409)", code == 409,
          (code, out))
    check("... and says the PC is already updating",
          "already updating" in str(out.get("error")), out)
    check("... and starts nothing", helper.calls == [], helper.calls)
    clean_files()
    reset_module()


# ---------------------------------------------------------------------------
# 3. the phone's allowlist and the core's token/origin gate
# ---------------------------------------------------------------------------

def _handler_class(sent, original):
    class Handler:
        path = "/"

        def _send(self, code, payload):
            sent.append((code, payload))
            return (code, payload)

        def do_GET(self):
            return original

        def do_POST(self):
            return original
    return Handler


def t_both_routes_go_through_the_cores_own_checks():
    sent = []
    H = _handler_class(sent, "ORIGINAL")
    banner = U.install(H, origin_ok=lambda h: True, token_ok=lambda h: True,
                       read_body=lambda h: b"{}")
    check("install() returns one banner line naming both routes",
          "GET status" in banner and "POST request" in banner, banner)
    check("install() does not disturb the class it wrapped",
          H.do_GET.__name__ == "do_GET" and callable(H.do_POST))

    # A cross-origin request is refused before anything else. The refusal is
    # SENT (`_send`) and the wrapper returns None, so the test reads what was
    # sent, exactly as a real request would.
    outs = []
    HC = _handler_class(outs, "ORIGINAL")
    U.install(HC, origin_ok=lambda x: False, token_ok=lambda x: True,
              read_body=lambda x: b"{}")
    refused = HC()
    refused.path = U.STATUS_PATH
    refused.do_GET()
    code, body = outs[-1]
    check("a cross-origin GET is refused with 403", code == 403, (code, body))
    check("... and says why, in the same words as every other route",
          body.get("error") == "cross-origin request refused", body)

    for path, method in ((U.STATUS_PATH, "GET"), (U.REQUEST_PATH, "POST")):
        outs = []
        HC = _handler_class(outs, "ORIGINAL")
        U.install(HC, origin_ok=lambda x: True, token_ok=lambda x: False,
                  read_body=lambda x: b"{}")
        hc = HC()
        hc.path = path
        getattr(hc, "do_GET" if method == "GET" else "do_POST")()
        code, body = outs[-1]
        check(f"a bad token refuses {method} {path} with 401", code == 401,
              (code, body))
        check(f"... naming the token header for {path}",
              body.get("error") == "bad or missing X-Jarvis-Token", body)

    # Another route is not ours and reaches the original handler untouched.
    HC = _handler_class([], "ORIGINAL")
    U.install(HC, origin_ok=lambda x: True, token_ok=lambda x: True,
              read_body=lambda x: b"{}")
    other = HC()
    other.path = "/api/something-else"
    check("another GET path reaches the original handler",
          other.do_GET() == "ORIGINAL")
    check("another POST path reaches the original handler",
          other.do_POST() == "ORIGINAL")

    # A second install is a no-op: one wrapping, one banner.
    again = U.install(HC, origin_ok=lambda x: True, token_ok=lambda x: True,
                      read_body=lambda x: b"{}")
    check("installing twice does not wrap twice", "already on" in again, again)


def t_the_routes_answer_when_the_core_says_yes():
    real_status, real_request = U.status, U.request
    asked = []

    def fake_status():
        return {"ok": True, "can_request": True, "why_not": ""}

    def fake_request(body=None):
        asked.append(body)
        return 202, {"ok": True, "pending": True}

    try:
        U.status, U.request = fake_status, fake_request
        sent = []
        H = _handler_class(sent, "ORIGINAL")
        U.install(H, origin_ok=lambda h: True, token_ok=lambda h: True,
                  read_body=lambda h: b'{"ignored": true}')
        h = H()
        h.path = U.STATUS_PATH
        got = h.do_GET()
        check("GET /api/update/status answers 200 through the wrapper",
              got[0] == 200 and got[1].get("ok") is True, got)
        p = H()
        p.path = U.REQUEST_PATH
        got = p.do_POST()
        check("POST /api/update/request answers the route's own status",
              got[0] == 202, got)
        check("the body is handed over as the dict it is (and read for nothing)",
              asked == [{"ignored": True}], asked)
        q = H()
        q.path = U.REQUEST_PATH + "/"
        check("a trailing slash is the same route", q.do_POST()[0] == 202)
    finally:
        U.status, U.request = real_status, real_request


def t_the_phone_may_approve_it_and_the_pc_still_asks_windows_hello():
    """The change that lets the phone's fingerprint decide, and what holds."""
    check("desktop_update is NOT in PC_ONLY_ACTIONS any more",
          U.ACTION not in OC.PC_ONLY_ACTIONS, sorted(OC.PC_ONLY_ACTIONS))
    check("... and no other PC-only action was touched",
          sorted(OC.PC_ONLY_ACTIONS) == sorted([
              "loosen_what_asks_first", "restore_backup", "pair_device",
              "unretire_shared_key", "register_approval_key",
              "handoff_keep_offering", "handoff_bring_to_front",
              "product_check", "change_approval_policy"]),
          sorted(OC.PC_ONLY_ACTIONS))

    row = _update_card_row()
    check("the gate still classifies it RISKY, so nothing was loosened by name",
          OC.is_risky(row) is True, row["risk"])
    check("... and it can never be approved with a swipe",
          row["risk"].get("swipe_ok") is False, row["risk"])

    # From a paired phone with no approval key: refused, with the sentence that
    # tells the owner how to turn signing on.
    got = OC.approve_check({"id": "c1"}, peer="100.64.0.9", local="100.64.0.1",
                           pending=lambda: [row], own=(), device="phone-1")
    check("a phone with no approval key cannot approve it (403)", got is not None
          and got[0] == 403, got)
    check("... and is told to turn signed approvals on, in the existing words",
          got is not None and got[1].get("owner_check") == "no_approval_key"
          and got[1].get("error") ==
          __import__("jarvis_devices").SIGN_WORDS["no_approval_key"], got)

    # On the PC the same card still asks Windows Hello - no Windows Hello is a
    # refusal, not a pass.
    _fresh_stamps()
    OC.set_verifier(lambda message, seconds: OC.UNAVAILABLE)
    try:
        got = OC.approve_check({"id": "c1"}, peer="127.0.0.1",
                               pending=lambda: [row], own=())
    finally:
        OC.set_verifier(None)
    check("the PC refuses it when Windows Hello is not set up (403)",
          got is not None and got[0] == 403
          and got[1].get("owner_check") == "not_set_up", got)

    _fresh_stamps()
    OC.set_verifier(lambda message, seconds: OC.CANCELLED_)
    try:
        got = OC.approve_check({"id": "c1"}, peer="127.0.0.1",
                               pending=lambda: [row], own=())
    finally:
        OC.set_verifier(None)
    check("the PC refuses it when the Hello prompt is dismissed (403)",
          got is not None and got[0] == 403
          and got[1].get("owner_check") == "cancelled", got)

    _fresh_stamps()
    OC.set_verifier(lambda message, seconds: OC.CONFIRMED)
    try:
        got = OC.approve_check({"id": "c1"}, peer="127.0.0.1",
                               pending=lambda: [row], own=())
        stamped = OC.take_stamp("c1", U.ACTION)
    finally:
        OC.set_verifier(None)
    check("on the PC, Windows Hello confirmed is what approves it",
          got is None and stamped is True, (got, stamped))


def _update_card_row() -> dict:
    """The `/api/pending` row the gate sends for this action, as it sends it.

    The risk half is read from the PUBLISHED BASE rather than typed here: the
    action has no `_RISK` row today, so the gate gives it its worst case
    (`_UNKNOWN_RISK`: permanent and outbound, `classified` False), and if a
    later change gives it a row this helper follows that instead of pinning a
    wart. What the suite then asserts is the invariant either way: the row is
    RISKY, and a swipe cannot decide it.
    """
    text = BASE_GATE.read_text(encoding="utf-8")
    found = re.search(r'"desktop_update"\s*:\s*\("(yes|no)",\s*"(local|outbound)"',
                      text)
    if found:
        risk = {"reversible": found.group(1), "reach": found.group(2),
                "swipe_ok": found.group(1) == "yes" and found.group(2) == "local",
                "why": "the update card", "classified": True}
    else:
        warning = re.search(r'UNCLASSIFIED_WARNING = \((.*?)\)\n', text, re.S)
        why = " ".join(re.findall(r'"([^"]*)"', warning.group(1))) if warning \
            else "Unclassified action"
        risk = {"reversible": "no", "reach": "outbound", "swipe_ok": False,
                "why": why, "classified": False}
    return {"id": "c1", "action": U.ACTION, "risk": risk,
            "notice": {"title": W.title_for(U.ACTION),
                       "summary": W.summary_for(U.ACTION)}}


def t_the_phones_copy_of_the_pc_only_set_agrees():
    """The generated contract is the phone's allowlist of cards it may answer."""
    doc = json.loads(CONTRACT.read_text(encoding="utf-8"))
    listed = doc.get("pc_only_actions")
    check("the generated contract carries the PC's own set",
          listed == sorted(OC.PC_ONLY_ACTIONS), (listed, sorted(OC.PC_ONLY_ACTIONS)))
    check("... and desktop_update is NOT in the phone's copy any more",
          "desktop_update" not in (listed or []), listed)
    check("... while the cards the PC keeps are all still there",
          {"loosen_what_asks_first", "restore_backup", "pair_device",
           "product_check", "change_approval_policy"} <= set(listed or []), listed)


# ---------------------------------------------------------------------------
# 4. the action, the tier, and the page rows - asserted, not described
# ---------------------------------------------------------------------------

def t_the_action_is_desktop_update_at_tier_ask():
    import jarvis_framework as FW
    check("the module's action is the literal the gate knows",
          U.ACTION == "desktop_update", U.ACTION)
    import jarvis_quick as Q
    check("... and it is jarvis_quick's own name for the card, not a second one",
          U.ACTION == Q.UPDATE_ACTION, (U.ACTION, Q.UPDATE_ACTION))

    check("the tier table says 'ask' (read through the framework, not a regex)",
          FW.action_tier(U.ACTION) == "ask", FW.action_tier(U.ACTION))
    shipped = SHIPPED_TOML.read_text(encoding="utf-8")
    base = BASE_TOML.read_text(encoding="utf-8")
    row = re.search(r'^desktop_update\s*=\s*"([a-z]+)"', shipped, re.M)
    check("the shipped settings copy carries the same line",
          row is not None and row.group(1) == "ask", row.group(0) if row else None)
    check("the published base carries it too",
          row is not None and row.group(0) in base)
    check("the action can never be loosened from an app (HARD_LIMITS)",
          U.ACTION in AF.HARD_LIMITS)
    check("... nor made instant by a settings edit (MUST_ASK)",
          U.ACTION in AF.MUST_ASK)


# ---------------------------------------------------------------------------
# 5. the card's words
# ---------------------------------------------------------------------------

EXPECTED_CARD = """Update Jarvis on the PC from 0.2.456 to 0.2.460?

If you say yes: Jarvis on the PC closes while the update is applied - a few minutes, because every change is tried on a throwaway copy first and the tests run - and then starts again on the new version. This phone's link drops while that happens and comes back by itself; you do not need to pair again.

The desktop app's installer is checked against Jarvis's own signing key before it is run, and the backend folder is changed only by this repository's own update script, which keeps a backup and refuses to leave it half done.

Nothing else on the PC changes: no other program is installed, and none of your documents, mail, notes, photos or saved memory is touched. Only Jarvis's own files and its logs are written.

If you say no: nothing changes, and nothing is downloaded."""


def t_the_card_says_exactly_what_a_person_reads():
    text = U.describe("0.2.456", "0.2.460")
    check("the card's sentence is asserted word for word (so it cannot drift)",
          text == EXPECTED_CARD,
          [line for line in text.splitlines()
           if line not in EXPECTED_CARD.splitlines()][:2])
    check("it names both versions and the move", "from 0.2.456 to 0.2.460" in text)
    check("it says the PC closes and starts again",
          "closes" in text and "starts again" in text)
    check("it says the phone's link drops and comes back",
          "phone's link" in text and "comes back by itself" in text)
    check("it says the installer's signature is checked",
          "signing key" in text)
    check("it says what refusing costs", "If you say no" in text and
          "nothing is downloaded" in text)
    jargon = ("tier", "gate", "action", "handler", "endpoint", "json", "api",
              "dispatch", "subprocess", "patch stack", "rollout", "webhook",
              "payload", "argv", "stdout", "mutex", "regex")
    low = text.lower()
    words = set(re.findall(r"[a-z]+", low))
    hits = [word for word in jargon
            if (word in words if " " not in word else word in low)]
    check("the card reads in plain words, with no jargon in it", hits == [], hits)
    check("an unreadable installed version still reads as a sentence",
          U.describe(None, "0.2.460").startswith("Update Jarvis on the PC to 0.2.460?"))

    check("the gate's own title is the one written for this action",
          W.title_for(U.ACTION) ==
          "Jarvis wants to update Jarvis itself - the backend first, then this app",
          W.title_for(U.ACTION))
    check("... its short summary is the written one too",
          W.summary_for(U.ACTION) == "Jarvis wants to update Jarvis, then restart it.",
          W.summary_for(U.ACTION))
    check("... and it has written words, not the fallback", W.has_written_title(U.ACTION))
    what = U.CARD_WHAT.lower()
    words = set(re.findall(r"[a-z]+", what))
    check("the card's 'what' line is plain words too",
          not (words & set(jargon)), U.CARD_WHAT)


# ---------------------------------------------------------------------------
# 6. no path in the module can start an update without an approval
# ---------------------------------------------------------------------------

def t_only_a_persons_yes_reaches_the_start():
    src = (HERE / "jarvis_update.py").read_text(encoding="utf-8")
    dec = src.split("def _decide(", 1)[1].split("\ndef ", 1)[0]
    at_check = dec.index('if not (allowed and outcome == "approved")')
    at_tier = dec.index('if vtier != "ask"')
    at_start = dec.index("spawn_helper or _start_helper")
    check("the tier check comes before the start", at_tier < at_start, (at_tier, at_start))
    check("the approval check comes before the start", at_check < at_start,
          (at_check, at_start))
    check("the start is the last thing the card thread does",
          "spawn_helper or _start_helper" in dec
          and dec.index("spawn_helper or _start_helper") > at_check)
    # `request()` cannot start anything itself: its only spawn is the card
    # thread, and the helper is never named there.
    req = src.split("def request(", 1)[1].split("\ndef ", 1)[0]
    check("request() names no helper and no script program",
          "_start_helper" not in req and "subprocess" not in req, req[:200])
    check("request()'s only thread is the card's own", req.count("spawn(") >= 1)


def t_the_status_route_reads_and_changes_nothing():
    clean_files()
    reset_module()

    def exploding_gate(*a, **k):
        raise AssertionError("status must not raise or answer a card")

    real_gate = U._gate
    U._gate = exploding_gate
    before = sorted(p.name for p in _TMP.rglob("*") if p.is_file())
    try:
        installed_now, published_now = versions()
        got = U.status(installed_now=installed_now, published_now=published_now,
                       backend=lambda: Path("C:/fake/backend"),
                       script=lambda: Path("C:/fake/repo/scripts/update-jarvis.ps1"),
                       state={})
    finally:
        U._gate = real_gate
    after = sorted(p.name for p in _TMP.rglob("*") if p.is_file())
    check("status() answers without raising a card", got.get("ok") is True, got)
    check("... and writes no file at all", before == after, (before, after))
    check("... and reports the action that would be raised",
          got.get("action") == "desktop_update", got)
    check("... and says it is not PC-only any more", got.get("pc_only") is False)
    check("... and that a request is possible now", got.get("can_request") is True,
          got.get("why_not"))
    check("... with no 'available' flag that could be read as 'an update exists'",
          "available" not in got, sorted(got))

    # With the phone's own blocker: the version it cannot read.
    installed_now, published_now = versions(
        {"version": None, "why": "cannot tell: no recorded version"})
    got = U.status(installed_now=installed_now, published_now=published_now,
                   backend=lambda: Path("C:/fake/backend"),
                   script=lambda: Path("C:/fake/repo/scripts/update-jarvis.ps1"),
                   state={})
    check("status() says why it cannot offer an update, in the same words",
          got.get("can_request") is False
          and "cannot tell whether there is a newer version" in got.get("why_not", ""),
          got.get("why_not"))
    check("... and repeats the detail that says what to fix",
          "no recorded version" in got.get("why_not_detail", ""), got)


def t_the_status_and_the_request_cannot_disagree():
    """One `obstacle()` decides both, so a greyed button names the same reason."""
    clean_files()
    reset_module()
    cases = [
        ("nothing newer", dict(versions_pair=versions(
            {"version": "0.2.460", "why": ""}, {"version": "0.2.460", "why": ""}))),
        ("unreadable version", dict(versions_pair=versions(
            {"version": None, "why": "cannot tell: x"}, PUBLISHED))),
        ("no backend", dict(backend=lambda: None)),
        ("no script", dict(script=lambda: None)),
        ("not ask", dict(tier_of=lambda action: "auto")),
    ]
    for label, kw in cases:
        installed_now, published_now = kw.pop("versions_pair", versions())
        common = dict(installed_now=installed_now, published_now=published_now,
                      backend=kw.get("backend",
                                     lambda: Path("C:/fake/backend")),
                      script=kw.get("script",
                                    lambda: Path("C:/fake/repo/scripts/update-jarvis.ps1")),
                      tier_of=kw.get("tier_of", U._tier_of), state={})
        helper = helper_recorder()
        code, out = ask(gate=gate_returning(), spawn_helper=helper, **dict(common))
        got = U.status(installed_now=common["installed_now"],
                       published_now=common["published_now"],
                       backend=common["backend"], script=common["script"],
                       tier_of=common["tier_of"], state={})
        check(f"{label}: request refuses with the same sentence status shows",
              got.get("why_not") == out.get("error"), (got.get("why_not"), out.get("error")))
        check(f"{label}: status says it cannot offer the button",
              got.get("can_request") is False, got)


def t_a_finished_update_is_reported_from_the_state_file():
    clean_files()
    reset_module()
    dead_pid = 999999999
    U._write_json(U.state_path(), {
        "phase": "checking", "pid": dead_pid, "started_at": 100.0,
        "updated_at": 200.0, "finished_at": None, "from": "0.2.456",
        "to": "0.2.460", "ending": " ALL DONE", "reason": "", "tail": "step 6"})
    installed_now, published_now = versions()
    got = U.status(installed_now=installed_now, published_now=published_now,
                   backend=lambda: Path("C:/fake/backend"),
                   script=lambda: Path("C:/fake/repo/scripts/update-jarvis.ps1"),
                   state=U.read_state())
    check("a state whose writer is gone is reported as failed, never as progress",
          got.get("phase") == "failed", got.get("phase"))
    check("... and the reason is in words, not only a phase name",
          "did not finish" in got.get("what", ""), got.get("what"))
    check("... and the phone is still told what it was moving to",
          got.get("to") == "0.2.460", got)
    check("... and the caught reason (or its absence) comes through as text",
          isinstance(got.get("reason"), str), got.get("reason"))
    clean_files()
    reset_module()


# ---------------------------------------------------------------------------
# 7. the helper, the locks, and the updater's own words
# ---------------------------------------------------------------------------

def t_the_helper_argv_is_fixed_and_owned_by_this_module():
    argv = U._updater_argv(Path("C:/repo/scripts/update-jarvis.ps1"),
                           Path("C:/backend"))
    check("the updater is run by powershell, with the one script",
          argv[0] == "powershell.exe" and
          argv[argv.index("-File") + 1].endswith("update-jarvis.ps1"), argv)
    check("the backend folder is the one this module found",
          argv[argv.index("-BackendPath") + 1] == "C:\\backend"
          or argv[argv.index("-BackendPath") + 1] == "C:/backend", argv)
    check("it closes a running Jarvis rather than waiting for a person",
          "-Force" in argv, argv)
    for skipped in ("-SkipTests", "-SkipDesktop", "-NoCheck"):
        check(f"it never passes {skipped} (the card promised a proven update)",
              skipped not in argv, argv)
    child = U.helper_argv(state=Path("s"), script=Path("x"), backend=Path("b"),
                          from_version="0.2.456", to_version="0.2.460")
    check("the helper's command line has no free-form part",
          child[:3] == [sys.executable, "-c",
                        "import jarvis_update; jarvis_update.helper_main()"], child)
    check("... and its four pairs are the ones it was given",
          child[3:] == ["--state", "s", "--script", "x", "--backend", "b",
                        "--from", "0.2.456", "--to", "0.2.460"], child)


def t_no_child_of_the_updater_is_given_the_pairing_token():
    """A sentinel token in this process's environment must not reach a child.

    `_start_helper` used to copy `os.environ` and hide the copy inside a
    `**kwargs` dict, so the detached helper - which outlives the backend and is
    watched by nobody - started holding the pairing token (`HUD_TOKEN` /
    `JARVIS_TOKEN`). The environment is built from an allowlist now; this proves
    it on the helper, on the updater script it runs, and on a REAL child asked
    what it can see.
    """
    src = (HERE / "jarvis_update.py").read_text(encoding="utf-8")
    secrets = {
        "HUD_TOKEN": "sentinel-hud-token-31c0",
        "JARVIS_TOKEN": "sentinel-jarvis-token-31c0",
        "OPENAI_API_KEY": "sentinel-api-key-31c0",
        "JOPLIN_TOKEN": "sentinel-joplin-token-31c0",
    }
    saved = {name: os.environ.get(name) for name in secrets}
    seen = {"calls": []}

    class FakePopen:
        """Stands in for `subprocess.Popen`, remembering what it was handed."""

        def __init__(self, argv, **kwargs):
            seen["calls"].append({"argv": list(argv), "kwargs": kwargs})
            self.argv, self.stdout, self.pid = list(argv), [], os.getpid()

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return 0

    real_popen = U.subprocess.Popen
    os.environ.update(secrets)
    try:
        allowed = U.child_env()
        U.subprocess.Popen = FakePopen
        clean_files()
        try:
            why = U._start_helper({
                "script": str(Path("C:/fake/repo/scripts/update-jarvis.ps1")),
                "backend": str(Path("C:/fake/backend")),
                "from": "0.2.456", "to": "0.2.460",
                "request_id": "req-sentinel"})
            helper_code = U.helper_main([
                "--state", str(U.state_path()),
                "--script", str(Path("C:/fake/repo/scripts/update-jarvis.ps1")),
                "--backend", str(Path("C:/fake/backend"))])
        finally:
            U.subprocess.Popen = real_popen
            clean_files()
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    check("no copy of this process's environment is built anywhere",
          "os.environ.copy()" not in src,
          [l.strip() for l in src.splitlines() if "os.environ.copy" in l])
    calls = seen["calls"]
    check("both children are started with env= written where a reader sees it",
          len(calls) == 2 and all("env" in c["kwargs"] for c in calls), len(calls))
    check("the detached helper was started", why is None, why)
    check("... and the updater script ran to its own ending", helper_code == 0,
          helper_code)
    for call in calls:
        env = call["kwargs"].get("env") or {}
        label = Path(call["argv"][0]).name if call["argv"] else "child"
        for name, value in secrets.items():
            check(f"{label}: the child's environment drops {name}",
                  name not in env, sorted(env))
            check(f"{label}: ... and carries none of that value",
                  all(value not in str(v) for v in env.values()))
        check(f"{label}: ... while keeping the settings the updater reads",
              env.get("JARVIS_CONFIG_DIR") == os.environ.get("JARVIS_CONFIG_DIR")
              and env.get(U.PATCHER_ENV) == "1", sorted(env))

    # The dict is what the module builds; a REAL process is what a child is.
    probe = "import json, os; print(json.dumps(dict(os.environ)))"
    done = U.subprocess.run([sys.executable, "-c", probe], env=allowed,
                            capture_output=True, text=True, timeout=120)
    check("a real child started with child_env() exits cleanly",
          done.returncode == 0, (done.returncode, (done.stderr or "")[-300:]))
    can_see = json.loads(done.stdout or "{}")
    for name, value in secrets.items():
        check(f"a real child cannot see {name}", name not in can_see)
        check(f"... nor its value", value not in (done.stdout or ""))
    check("... and it does get the settings the updater reads",
          can_see.get("JARVIS_CONFIG_DIR") == os.environ.get("JARVIS_CONFIG_DIR")
          and can_see.get(U.PATCHER_ENV) == "1",
          can_see.get("JARVIS_CONFIG_DIR"))


def t_the_locks_are_shared_and_never_stolen():
    clean_files()
    now = __import__("time").time()
    check("a free PC takes the shared lock", U.take_shared_lock(os.getpid(), now) is True)
    check("... and a second taker is refused while its writer is alive",
          U.take_shared_lock(4242, now) is False)
    check("... and the lock reads back as held",
          (U.held_lock(now) or {}).get("pid") == os.getpid())
    U.release_shared_lock(os.getpid())
    check("releasing it leaves nothing behind", U.held_lock(now) is None)

    U._write_json(U.shared_lock_path(), {"pid": 4242, "started_at": now - 5,
                                         "updated_at": now - 5, "pace": "phone"})
    check("a lock whose writer is gone is not 'an update running'",
          U.held_lock(now) is None)
    check("... and the next update may take it",
          U.take_shared_lock(os.getpid(), now) is True)
    U.release_shared_lock(os.getpid())

    U._write_json(U.shared_lock_path(), {"pid": os.getpid(),
                                         "started_at": now - 60 * 60,
                                         "updated_at": now - 60 * 60,
                                         "pace": "balanced"})
    check("a heartbeat an hour old is stale, not an update", U.held_lock(now) is None)
    check("... and its words are not claimed as running", U.desktop_lock_words(now) == "")
    U._write_json(U.shared_lock_path(), {"pid": os.getpid(),
                                         "started_at": now - 60,
                                         "updated_at": now - 5,
                                         "pace": "balanced"})
    words = U.desktop_lock_words(now)
    check("a live lock gives the plain 'already updating' sentence",
          "already updating" in words and "balanced" in words, words)
    clean_files()


def t_a_liveness_probe_never_ends_the_process_it_asks_about():
    check("this PC's own process is alive", U._pid_alive(os.getpid()) is True)
    check("a pid that cannot exist is not", U._pid_alive(999999999) is False)
    for bad in (0, -1, "123", None, True, 1.5):
        check(f"{bad!r} is not a process id", U._pid_alive(bad) is False)
    src = (HERE / "jarvis_update.py").read_text(encoding="utf-8")
    body = src.split("def _pid_alive(", 1)[1].split("\ndef ", 1)[0]
    after_doc = body.split('"""', 2)[-1]      # the docstring NAMES os.kill on purpose
    check("on Windows it asks OpenProcess/GetExitCodeProcess, never os.kill",
          "OpenProcess" in after_doc and "GetExitCodeProcess" in after_doc
          and after_doc.index("OpenProcess") < after_doc.index("os.kill"),
          after_doc[:300])
    check("... and the reason is written beside it",
          "ends the process" in body or "would kill" in body, body[:300])


def t_the_helper_refuses_to_run_beside_another_update():
    clean_files()
    now = __import__("time").time()
    U._write_json(U.shared_lock_path(), {"pid": os.getpid(), "started_at": now - 5,
                                         "updated_at": now - 5, "pace": "balanced"})
    code = U.helper_main(["--state", str(U.state_path()),
                          "--script", str(Path("C:/nope/update-jarvis.ps1")),
                          "--backend", str(Path("C:/nope"))])
    state = U.read_state()
    check("the helper refuses (exit 3) when the PC's lock is held", code == 3, code)
    check("... and writes a failure with the reason, never a phase in flight",
          state.get("phase") == "failed" and "already running" in
          str(state.get("reason")), state)
    check("... and leaves no helper lock behind", not U.helper_lock_path().is_file())
    check("... and does not release somebody else's lock",
          (U.held_lock() or {}).get("pid") == os.getpid())
    clean_files()

    U._write_json(U.helper_lock_path(), {"pid": os.getpid(), "at": now})
    code = U.helper_main(["--state", str(U.state_path()),
                          "--script", str(Path("C:/nope/update-jarvis.ps1")),
                          "--backend", str(Path("C:/nope"))])
    check("a second helper refuses (exit 2) while this one is alive", code == 2, code)
    check("... and touches no state file", U.read_state() == {}, U.read_state())
    clean_files()


def t_every_phase_the_helper_can_report_has_words():
    for phase in U.PHASES + (U.DONE, U.FAILED, U.IDLE):
        check(f"phase {phase!r} has one plain sentence",
              isinstance(U.PHASE_WORDS.get(phase), str)
              and len(U.PHASE_WORDS[phase]) > 12
              and U.PHASE_WORDS[phase].endswith("."), U.PHASE_WORDS.get(phase))
    jargon = ("tier", "gate", "endpoint", "payload", "subprocess", "argv", "pid")
    for phase, words in U.PHASE_WORDS.items():
        words_found = set(re.findall(r"[a-z]+", words.lower()))
        hits = [w for w in jargon if w in words_found]
        check(f"the words for {phase!r} carry no jargon", hits == [], (hits, words))


def t_the_step_markers_are_the_scripts_own_titles():
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    for marker, phase in U._STEP_MARKERS:
        check(f"the script still has a step titled {marker!r}",
              marker in script.lower(), marker)
    check("every marker maps to a phase the module knows",
          all(phase in U.PHASES for _, phase in U._STEP_MARKERS),
          [phase for _, phase in U._STEP_MARKERS])
    check("every phase is reachable from some marker",
          set(U.PHASES) <= {phase for _, phase in U._STEP_MARKERS},
          sorted(set(U.PHASES) - {phase for _, phase in U._STEP_MARKERS}))
    for line, expected in (
            ("[1/6] Finding the backend folder", "starting"),
            ("[2/6] Getting the newest code", "starting"),
            ("[3/6] Closing Jarvis", "closing"),
            ("[4/6] Patching the backend", "patching"),
            ("[5/6] Updating the desktop app", "installing"),
            ("[6/6] Starting Jarvis and checking it", "restarting"),
            ("Running the live check (it changes nothing).", "checking"),
            ("  ok    something else", None)):
        check(f"{line!r} maps to {expected!r}", U.phase_for_line(line) == expected,
              U.phase_for_line(line))


def t_a_failure_is_never_reported_as_done():
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    for banner in ("DONE WITH PROBLEMS - do not trust this update yet",
                   "NOT DONE - nothing was changed",
                   "the desktop app was NOT updated"):
        check(f"the script still prints its own {banner!r}",
              banner in script, banner)
    cases = [
        ("a run with problems", 1,
         " DONE WITH PROBLEMS - do not trust this update yet", U.FAILED),
        ("a stopped run", 1, " NOT DONE - nothing was changed", U.FAILED),
        ("a backend-only ending", 0,
         " DONE - the backend is patched, but the desktop app was NOT updated",
         U.FAILED),
        ("both halves done", 0,
         " ALL DONE - the backend is patched and the desktop app is up to date",
         U.DONE),
        ("an unexplained exit 1", 1, "  ok    something", U.FAILED),
    ]
    for label, code, output, expected in cases:
        phase, reason = U.outcome_from(code, output)
        check(f"{label}: reported as {expected!r}", phase == expected, (phase, reason))
        if expected == U.FAILED:
            check(f"{label}: with a reason in words", len(reason) > 20, reason)
        else:
            check(f"{label}: with no invented failure", reason == "", reason)
    check("the last real line is what the phone is shown",
          U._last_line(" a\n b \n\n") == "b", U._last_line(" a\n b \n\n"))


# ---------------------------------------------------------------------------
# 8. the two files, the shipping lists, and the written record
# ---------------------------------------------------------------------------

def t_the_two_copies_are_one_file():
    a = (HERE / "jarvis_update.py").read_bytes()
    b = (ROOT / "jarvis-backend" / "jarvis_update.py").read_bytes()
    check("jarvis-backend/jarvis_update.py is byte-identical", a == b)


def t_the_module_is_on_both_shipped_lists():
    from _where import SHIPPED
    check("backend/_where.py lists the module", "jarvis_update.py" in SHIPPED)
    script = APPLY_SCRIPT.read_text(encoding="utf-8")
    check("scripts/apply-patches.ps1 copies it too",
          "'jarvis_update.py'" in script or '"jarvis_update.py"' in script)
    check("the drop-in folder names this module",
          (ROOT / "plugins" / "ready" / "update" / "plugin.json").is_file()
          and json.loads((ROOT / "plugins" / "ready" / "update" /
                          "plugin.json").read_text(encoding="utf-8")).get("module")
          == "jarvis_update")


def t_the_routes_are_in_the_api_document():
    api = API_DOC.read_text(encoding="utf-8")
    check("JARVIS-API.md documents GET /api/update/status",
          U.STATUS_PATH in api, U.STATUS_PATH)
    check("... and POST /api/update/request", U.REQUEST_PATH in api)
    check("... with the action it raises", "desktop_update" in api)


def t_the_architecture_records_the_phone_screen_as_one_sided_for_now():
    arch = ARCH_DOC.read_text(encoding="utf-8")
    section = arch.split("### One-sided on purpose", 1)
    check("ARCHITECTURE.md still has its one-sided section", len(section) == 2)
    body = section[1] if len(section) == 2 else arch
    check("... and it records the phone's update screen as one-sided for now",
          "phone" in body.lower() and "update" in body.lower()
          and "2026-11-18" in body, "2026-11-18" in body)


def _fresh_stamps():
    """No approval stamp from an earlier case can be read as this one's."""
    try:
        OC._STAMPS.clear()                     # noqa: SLF001 - the test's own reset
    except Exception:
        pass


if __name__ == "__main__":
    for fn in (
            t_the_request_raises_one_card_under_the_action_that_exists,
            t_nothing_downloads_or_runs_before_the_yes,
            t_the_request_body_cannot_change_what_runs,
            t_a_denied_card_installs_nothing,
            t_a_timed_out_card_installs_nothing,
            t_a_gate_that_raises_installs_nothing,
            t_a_loosened_tier_installs_nothing,
            t_an_allowed_flag_alone_is_not_an_approval,
            t_every_refusal_says_why_and_starts_nothing,
            t_a_second_request_while_one_waits_changes_nothing,
            t_a_running_or_locked_update_is_refused,
            t_both_routes_go_through_the_cores_own_checks,
            t_the_routes_answer_when_the_core_says_yes,
            t_the_phone_may_approve_it_and_the_pc_still_asks_windows_hello,
            t_the_phones_copy_of_the_pc_only_set_agrees,
            t_the_action_is_desktop_update_at_tier_ask,
            t_the_card_says_exactly_what_a_person_reads,
            t_only_a_persons_yes_reaches_the_start,
            t_the_status_route_reads_and_changes_nothing,
            t_the_status_and_the_request_cannot_disagree,
            t_a_finished_update_is_reported_from_the_state_file,
            t_the_helper_argv_is_fixed_and_owned_by_this_module,
            t_no_child_of_the_updater_is_given_the_pairing_token,
            t_the_locks_are_shared_and_never_stolen,
            t_a_liveness_probe_never_ends_the_process_it_asks_about,
            t_the_helper_refuses_to_run_beside_another_update,
            t_every_phase_the_helper_can_report_has_words,
            t_the_step_markers_are_the_scripts_own_titles,
            t_a_failure_is_never_reported_as_done,
            t_the_two_copies_are_one_file,
            t_the_module_is_on_both_shipped_lists,
            t_the_routes_are_in_the_api_document,
            t_the_architecture_records_the_phone_screen_as_one_sided_for_now,
    ):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed"
          + (f", {len(SKIPPED)} skipped (never a pass)" if SKIPPED else ""))
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(1 if FAILED else 0)
