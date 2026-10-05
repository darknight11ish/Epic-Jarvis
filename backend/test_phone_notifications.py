"""test_phone_notifications.py - the "read my phone's notifications"
setting: ON asks first, OFF is instant, and the route it answers at.

    python3 backend/test_phone_notifications.py

The owner's decision (CLAUDE.md, 2026-09-26, queued after the four
cutting-edge groups and the security audit; built 2026-09-28): "reading
phone notifications is added as an option. The safe version only: off by
default, turning it on raises an approval card, turning it off is
immediate; ... Jarvis never replies to or sends [a notification]."

Same shape as test_watch_notify.py, which this module's own docstring says
it deliberately copies: this test proves only the ON/OFF switch and its
card. Everything about redaction, the allow list, SMS exclusion and the
Android service is proved on the phone (jarvis-client's own
NotificationRedactorTest.kt / NotificationAllowListTest.kt) - this module
never sees a notification's text at all, so there is nothing of that kind
for a backend test to check.

No pytest, no network, no model. Real files in a temporary folder for the
setting itself; the gate, the tier and the clock are all stand-ins, the
same shape test_watch_notify.py already proves that shape with.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_phone_notifications.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-phone-notif-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
sys.modules.setdefault("jarvis_framework", fw)

import jarvis_phone_notifications as N  # noqa: E402
import _stack  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (It used to be check("SKIP - ...", True) - a condition of
    the constant True, so it printed as a pass and was counted as one.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


# ==========================================================================
#   1. The setting itself: default off, saved, fails closed
# ==========================================================================

def fresh_settings_path() -> Path:
    d = Path(tempfile.mkdtemp(prefix="jarvis-phone-notif-cfg-", dir=_TMP))
    fw.CONFIG_DIR = d
    return N.settings_path()


def t_default_is_off():
    fresh_settings_path()
    check("no file at all: off, the owner's default", N.settings() == {"enabled": False, "why": ""})


def t_set_and_read_back():
    fresh_settings_path()
    check("turned on and saved", N.set_enabled(True) == {"enabled": True, "why": "", "ok": True})
    check("reads back on", N.settings() == {"enabled": True, "why": ""})
    check("turned off again", N.set_enabled(False)["enabled"] is False)
    check("reads back off", N.settings()["enabled"] is False)


def t_a_damaged_file_fails_closed():
    p = fresh_settings_path()
    for raw in ("not json", "[]", json.dumps({"enabled": "yes"}), json.dumps({"enabled": None})):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(raw, encoding="utf-8")
        st = N.settings()
        check(f"{raw!r}: off, and why says so", st["enabled"] is False and st["why"], st)
    check("the reason is plain English, not a stack trace",
          "changed" in N.settings()["why"] or "damaged" in N.settings()["why"])


# ==========================================================================
#   2. request(): ON asks first, OFF is instant (the shape of
#      jarvis_watch_notify.py, proved the same way test_watch_notify.py
#      proves it)
# ==========================================================================

class V:
    def __init__(self, outcome, allowed=None, tier="ask"):
        self.outcome, self.tier = outcome, tier
        self.allowed = (outcome == "approved") if allowed is None else allowed
        self.reason = outcome


class World:
    def __init__(self, verdict=None, tier="ask"):
        N._reset_for_tests()
        self.applied, self.cards, self.later = [], [], []
        self.verdict, self.tier = verdict or V("approved"), tier

    def apply(self, on):
        self.applied.append(on)
        return {"ok": True, "enabled": on}

    def gate(self, action, detail, prompt):
        self.cards.append((action, detail))
        return self.verdict

    def tier_of(self, action):
        return self.tier

    def req(self, enabled):
        return N.request(enabled, self.apply, gate=self.gate, tier_of=self.tier_of,
                         spawn=self.later.append)

    def run_card(self):
        for fn in list(self.later):
            fn()
        self.later.clear()


def t_on_asks_and_off_is_instant():
    w = World()
    code, out = w.req(True)
    check("ON answers 202 waiting and changes nothing yet",
          code == 202 and out["waiting"] and out["enabled"] is False and w.applied == [], out)
    check("the card is raised under phone_notifications_read, and says nothing leaves",
          not w.cards and len(w.later) == 1)
    w.run_card()
    check("approved: the setting is turned on, once",
          w.applied == [True] and w.cards[0][0] == "phone_notifications_read"
          and w.cards[0][1]["leaves_this_pc"] is False, (w.applied, w.cards))
    check("status: not waiting, last card enabled",
          N.state()["waiting"] is False and N.state()["last"]["outcome"] == "enabled")
    code, out = w.req(False)
    check("OFF: immediate, no card", code == 200 and w.applied == [True, False]
          and len(w.cards) == 1 and out["waiting"] is False, out)


def t_no_yes_changes_nothing():
    for outcome in ("denied", "timed_out", "refused"):
        w = World(V(outcome))
        w.req(True)
        w.run_card()
        check(f"{outcome}: the setting stays off", w.applied == []
              and N.state()["last"]["outcome"] == outcome, N.state())
    w = World(V("approved", tier="auto"))
    w.req(True)
    w.run_card()
    check("a gate that answered at tier auto is not a person saying yes",
          w.applied == [] and N.state()["last"]["outcome"] == "refused")


def t_the_toml_cannot_make_it_automatic():
    for tier in ("auto", "notify", "never", "unreadable (KeyError)"):
        w = World(tier=tier)
        code, out = w.req(True)
        check(f"tier {tier!r}: 503, no card, nothing applied",
              code == 503 and not w.later and w.applied == [] and "must be 'ask'" in out["error"],
              out)


def t_off_while_waiting_withdraws_it():
    w = World()
    w.req(True)
    w.req(False)
    w.run_card()
    check("turned off while the card waited: approving it does not turn it on",
          w.applied == [False] and N.state()["last"]["outcome"] == "withdrawn", w.applied)
    w = World()
    w.req(True)
    w.req(False)
    check("after OFF nothing is shown as waiting", N.state()["waiting"] is False, N.state())
    code, out = w.req(True)
    check("a second ON raises its own card", code == 202 and len(w.later) == 2
          and "already waiting" not in out["message"], (code, out, len(w.later)))
    w.later[1]()
    w.later[0]()
    check("the new card turns it on; the old one ending later changes nothing shown",
          w.applied == [False, True] and N.state()["last"]["outcome"] == "enabled",
          (w.applied, N.state()))


def t_off_pressed_while_an_approved_card_writes_wins():
    """The same red team (R5) jarvis_learning_switch.py was fixed for, and
    jarvis_watch_notify.py already copies: OFF landing between the approved
    card's "was it withdrawn?" check and its apply(True) must not be
    overwritten by that card."""
    w = World()
    entered, release = threading.Event(), threading.Event()
    state = {"on": False}

    def apply(on):
        if on:
            entered.set()
            release.wait(2)
        state["on"] = on
        return {"ok": True, "enabled": on}

    N.request(True, apply, gate=w.gate, tier_of=w.tier_of, spawn=w.later.append)
    card = threading.Thread(target=w.run_card)
    card.start()
    entered.wait(2)
    off = []
    t = threading.Thread(target=lambda: off.append(N.request(False, apply)))
    t.start()
    t.join(0.3)
    early = bool(off)
    release.set()
    card.join(2)
    t.join(2)
    check("OFF waits for the card's write, then the setting is OFF",
          off and off[0][0] == 200 and state["on"] is False and not early,
          (off, state, early))


def t_the_last_card_in_plain_words():
    for verdict, outcome, words in (
            (V("approved", tier="auto"), "refused",
             "Your PC's settings do not let this be approved, so it stayed off."),
            (V("denied"), "denied",
             "The card was turned down, so nothing about your notifications changed."),
            (V("approved"), "enabled",
             "You approved the card, so your phone may read notifications from apps you choose.")):
        w = World(verdict)
        w.req(True)
        w.run_card()
        last = N.state()["last"]
        check(f"{outcome}: {words}", last["outcome"] == outcome and last["message"] == words
              and "why" in last, last)


def t_one_card_at_a_time():
    w = World()
    w.req(True)
    code, out = w.req(True)
    check("a second ON while one waits: no second card", code == 202 and len(w.later) == 1
          and "already waiting" in out["message"], out)


def t_bad_input():
    w = World()
    for bad in ("yes", 1, None, "true"):
        code, _ = w.req(bad)
        check(f"enabled={bad!r} is refused", code == 400 and w.applied == [] and not w.later)


def t_the_card_text_names_the_real_safety_rules():
    text = N.CARD_TEXT.lower()
    check("says a list of apps, empty until the owner adds one", "apps" in text and "choose" in text)
    check("says banking apps are blocked", "bank" in text)
    check("says one-time codes are blanked before saving",
          "code" in text and "before" in text)
    check("says text messages / SMS are never read", "sms" in text or "text message" in text)
    check("says it never replies to or acts on a notification",
          "never replies" in text or "never acts" in text or "acts on one" in text)
    check("says it is never saved as a fact", "fact" in text)
    check("says off is instant", "instant" in text)


# ==========================================================================
#   3. install() - the route it wraps the handler with (the shape of
#      jarvis_watch_notify.install())
# ==========================================================================

class FakeHandler:
    def __init__(self, path, body=b"{}", peer="127.0.0.1"):
        self.path = path
        self.body = body
        self.client_address = (peer, 5000)
        self.sent = None

    def do_GET(self):
        self.sent = ("original GET", None)

    def do_POST(self):
        self.sent = ("original POST", None)

    def _send(self, code, obj):
        self.sent = (code, obj)
        return self.sent


def t_the_routes():
    N._reset_for_tests()
    fresh_settings_path()

    class H(FakeHandler):
        pass
    line = N.install(H, origin_ok=lambda h: True, token_ok=lambda h: True,
                     read_body=lambda h: h.body)
    check("the banner line names it", line.startswith("  notif      Phone notifications"))
    check("off by default is on the banner", "off - never read" in line, line)
    h = H(N.PATH)
    H.do_GET(h)
    check("GET /api/notifications/phone answered here",
          h.sent[0] == 200 and h.sent[1] == {"enabled": False, "waiting": False, "last": None}, h.sent)
    h = H("/api/status")
    H.do_GET(h)
    check("any other GET goes to the server's own handler", h.sent[0] == "original GET")
    h = H("/api/stop_all")
    H.do_POST(h)
    check("any other POST too", h.sent[0] == "original POST")

    class Tok(FakeHandler):
        pass
    N.install(Tok, origin_ok=lambda h: True, token_ok=lambda h: False, read_body=lambda h: b"{}")
    h = Tok(N.PATH)
    Tok.do_POST(h)
    check("no token: 401, nothing done", h.sent[0] == 401)

    h = H(N.PATH, body=b"not json")
    H.do_POST(h)
    check("bad JSON body: 400 in words", h.sent[0] == 400, h.sent)

    class Origin(FakeHandler):
        pass
    N.install(Origin, origin_ok=lambda h: False, token_ok=lambda h: True, read_body=lambda h: b"{}")
    h = Origin(N.PATH)
    Origin.do_GET(h)
    check("another site's page is refused (403)", h.sent[0] == 403)

    check("install twice wraps once", "already on" in N.install(
        H, origin_ok=lambda h: True, token_ok=lambda h: True, read_body=lambda h: b"{}"))
    N._reset_for_tests()


def t_the_view_carries_why_when_damaged():
    N._reset_for_tests()
    p = fresh_settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not json", encoding="utf-8")

    class H(FakeHandler):
        pass
    N.install(H, origin_ok=lambda h: True, token_ok=lambda h: True, read_body=lambda h: h.body)
    h = H(N.PATH)
    H.do_GET(h)
    check("a damaged file's reason reaches the route too",
          h.sent[0] == 200 and h.sent[1]["enabled"] is False and h.sent[1].get("why"), h.sent)
    N._reset_for_tests()


# ==========================================================================
#   4. Listed in apply-patches.ps1's order, and the patch applies/reverses
# ==========================================================================

def t_listed_and_applies():
    order = _stack.order()
    at = order.index("phone-notifications.patch")
    check("phone-notifications.patch is in apply-patches.ps1's order, after plan-gate.patch",
          order.index("plan-gate.patch") < at, order[max(0, at - 2):at + 1])
    check("the module that does the work is shipped whole",
          "jarvis_phone_notifications.py" in __import__("_where").SHIPPED)
    patch = (HERE / "phone-notifications.patch").read_text(encoding="utf-8")
    check("it patches jarvis_gate.py and jarvis_hud.py and nothing else",
          sorted(set(line[6:].strip() for line in patch.splitlines() if line.startswith("+++ b/")))
          == ["jarvis_gate.py", "jarvis_hud.py"])
    git = shutil.which("git")
    if not git:
        return skip("git is not installed")
    for target in ("jarvis_gate.py", "jarvis_hud.py"):
        text, log = _stack.stand_in(target, order[:at])
        check(f"{target}: the stack before phone-notifications.patch builds", text is not None)
        if text is None:
            continue
        d = Path(tempfile.mkdtemp(prefix="jarvis-phone-notif-patch-"))
        try:
            (d / target).write_text(text, encoding="utf-8", newline="\n")
            one = "".join(h for h, _ in _stack.hunks(patch, target))
            (d / "p.patch").write_text(f"--- a/{target}\n+++ b/{target}\n{one}",
                                       encoding="utf-8", newline="\n")
            for extra in (["--check"], [], ["--check", "--reverse"], ["--reverse"], []):
                r = subprocess.run([git, "apply", *extra, "p.patch"], cwd=d, capture_output=True,
                                   text=True)
                check(f"git apply {' '.join(extra) or '(forwards)'} phone-notifications.patch "
                      f"({target})", r.returncode == 0, r.stderr.strip())
            full = _stack.stand_in(target, order[:at + 1])[0]
            check(f"forwards gives the stack's own text ({target})",
                  (d / target).read_text(encoding="utf-8") == full)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
