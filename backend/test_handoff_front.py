"""test_handoff_front.py - what a captcha does about the browser window it is
blocking: the owner's two choices, the default, and the card that guards the
one that takes the screen.

    python3 backend/test_handoff_front.py

THE OWNER'S DECISION (2026-10-09), in his own words: "1 by default with the
option for 2 in the settings of Jarvis". When a captcha or a sign-in page blocks
the browser window Jarvis is driving:

  * "Leave it where it is" (THE DEFAULT, and the narrower one): the window is not
    touched - it keeps its size, its place and whatever is in front of it - and
    the PC says plainly WHICH window Jarvis is stuck on, so the owner solves it
    there when they are ready.
  * "Bring it to the front": that one window is raised and activated the moment
    Jarvis is stuck. It takes the owner's screen and their keyboard away from
    whatever they were doing - MORE than Jarvis was doing before - so choosing it
    is ONE approval card, and (jarvis_owner_check.PC_ONLY_ACTIONS) it is approved
    on the PC with Windows Hello. Going back is instant.

No pytest, no network, no model, no real browser, and no window is ever raised
by this suite: only real files in a temporary folder for the setting itself, and
the gate and the tier are stand-ins, the same shape test_handoff_mode.py proves
that shape with.
"""
from __future__ import annotations

import ast
import json
import sys
import tempfile
import threading
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, SHIPPED, require_shipped  # noqa: E402

require_shipped("jarvis_handoff_front.py", "jarvis_handoff.py", "jarvis_chatbot.py",
                "jarvis_chatbot_routes.py", "jarvis_support.py", "jarvis_card_words.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-handoff-front-"))
AUDIT: list = []
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda kind, detail=None, *a, **k: AUDIT.append((kind, detail))
fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = fw

if str(HERE / "rebuilt") not in sys.path:
    sys.path.insert(1, str(HERE / "rebuilt"))

import jarvis_chatbot as CB  # noqa: E402
import jarvis_chatbot_routes as R  # noqa: E402
import jarvis_handoff as HO  # noqa: E402
import jarvis_handoff_front as HF  # noqa: E402
import jarvis_support as SUP  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# ==========================================================================
#   1. The two values and the default the owner was promised
# ==========================================================================

def fresh_settings_path() -> Path:
    d = Path(tempfile.mkdtemp(prefix="jarvis-handoff-front-cfg-", dir=_TMP))
    fw.CONFIG_DIR = d
    HF._reset_for_tests()
    return HF.settings_path()


def t_default_is_leave_in_place():
    fresh_settings_path()
    check("no file at all: 'Leave it where it is', the owner's default",
          HF.settings() == {"mode": "leave_in_place", "why": ""}, HF.settings())
    check("the two values are exactly the two the owner was offered",
          HF.MODES == ("leave_in_place", "bring_to_front")
          and HF.DEFAULT == "leave_in_place"
          and HF.BRING_TO_FRONT == "bring_to_front")
    check("the default touches no window and raises nothing",
          HF.brings_to_front() is False
          and HF.should_raise_now(stuck=True, handoff_active=False) is False)
    check("choosing 'Bring it to the front' raises it, and going back does not",
          HF.set_mode(HF.BRING_TO_FRONT)["mode"] == "bring_to_front"
          and HF.brings_to_front() is True
          and HF.should_raise_now(stuck=True, handoff_active=False) is True
          and HF.set_mode(HF.LEAVE_IN_PLACE)["mode"] == "leave_in_place"
          and HF.should_raise_now(stuck=True, handoff_active=False) is False)


def t_set_and_read_back():
    fresh_settings_path()
    check("chosen and saved",
          HF.set_mode(HF.BRING_TO_FRONT) == {"mode": "bring_to_front", "why": "", "ok": True})
    check("reads back", HF.settings()["mode"] == "bring_to_front" and HF.brings_to_front())
    check("a value that is not one of the two is refused",
          _raises(ValueError, lambda: HF.set_mode("always")))
    check("... and reading the file afterwards shows nothing changed",
          HF.settings()["mode"] == HF.BRING_TO_FRONT)
    check("the two settings never share a file",
          HF.settings_path().name == "handoff-front.json")


def _raises(kind, fn) -> bool:
    try:
        fn()
    except kind:
        return True
    except Exception:
        return False
    return False


def t_a_damaged_file_fails_closed():
    p = fresh_settings_path()
    for raw in ("not json", "[]", json.dumps({"mode": "always"}),
                json.dumps({"mode": None}), json.dumps({"mode": True})):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(raw, encoding="utf-8")
        st = HF.settings()
        check(f"{raw!r}: 'Leave it where it is', and why says so",
              st["mode"] == "leave_in_place" and st["why"], st)
    check("a damaged file never starts taking the owner's screen",
          HF.settings()["mode"] == HF.DEFAULT and HF.brings_to_front() is False
          and HF.should_raise_now(stuck=True, handoff_active=False) is False)
    check("the reason is plain English, not a stack trace",
          "damaged" in HF.settings()["why"] and "Traceback" not in HF.settings()["why"])
    check("the words for a damaged file are the same on both apps",
          HF.settings()["why"] == HF.WORDS["damaged"])


# ==========================================================================
#   2. When the window may be raised at all
# ==========================================================================

def t_raise_only_when_stuck_and_nobody_is_solving_it_on_the_phone():
    fresh_settings_path()
    HF.set_mode(HF.BRING_TO_FRONT)
    check("chosen, stuck, nobody on the phone: raise it",
          HF.should_raise_now(stuck=True, handoff_active=False) is True)
    check("the hand-off is being solved on the phone: raise nothing",
          HF.should_raise_now(stuck=True, handoff_active=True) is False)
    check("nothing is waiting for the owner: raise nothing",
          HF.should_raise_now(stuck=False, handoff_active=False) is False)
    check("a caller that cannot tell passes handoff_active=True: raise nothing",
          HF.should_raise_now(stuck=True, handoff_active=True) is False)


# ==========================================================================
#   3. request(): the looser value asks first, the stricter one is instant
# ==========================================================================

class V:
    def __init__(self, outcome, allowed=None, tier="ask"):
        self.outcome, self.tier = outcome, tier
        self.allowed = (outcome == "approved") if allowed is None else allowed
        self.reason = outcome


class World:
    def __init__(self, verdict=None, tier="ask"):
        fresh_settings_path()
        self.cards, self.later = [], []
        self.verdict, self.tier = verdict or V("approved"), tier

    def gate(self, action, detail, prompt):
        self.cards.append((action, detail))
        return self.verdict

    def tier_of(self, action):
        return self.tier

    def req(self, mode):
        return HF.request(mode, gate=self.gate, tier_of=self.tier_of,
                          spawn=self.later.append)

    def run_card(self):
        for fn in list(self.later):
            fn()
        self.later.clear()


def t_bring_to_front_asks_and_leave_in_place_is_instant():
    w = World()
    code, out = w.req(HF.BRING_TO_FRONT)
    check("'Bring it to the front' answers 202 waiting and changes nothing yet",
          code == 202 and out["waiting"] and out["mode"] == HF.LEAVE_IN_PLACE
          and HF.settings()["mode"] == HF.LEAVE_IN_PLACE and not w.cards, out)
    check("... and the window is still not raised while the card waits",
          HF.should_raise_now(stuck=True, handoff_active=False) is False)
    check("one card is queued, under the setting's own action", len(w.later) == 1)
    w.run_card()
    check("approved: the setting brings the window forward, once",
          w.cards and w.cards[0][0] == HF.ACTION == "handoff_bring_to_front"
          and w.cards[0][1]["leaves_this_pc"] is False
          and HF.settings()["mode"] == HF.BRING_TO_FRONT, (HF.settings(), w.cards))
    check("... so a stuck captcha now raises that one window",
          HF.should_raise_now(stuck=True, handoff_active=False) is True)
    check("status: not waiting, last card 'on'",
          HF.state()["waiting"] is False and HF.state()["last"]["outcome"] == "on")
    code, out = w.req(HF.LEAVE_IN_PLACE)
    check("'Leave it where it is': immediate, no card, and nothing is raised",
          code == 200 and len(w.cards) == 1 and out["waiting"] is False
          and HF.settings()["mode"] == HF.LEAVE_IN_PLACE
          and HF.should_raise_now(stuck=True, handoff_active=False) is False, out)


def t_no_yes_changes_nothing():
    for outcome in ("denied", "timed_out", "refused"):
        w = World(V(outcome))
        w.req(HF.BRING_TO_FRONT)
        w.run_card()
        check(f"{outcome}: the window still stays where it is",
              HF.settings()["mode"] == HF.LEAVE_IN_PLACE
              and HF.state()["last"]["outcome"] == outcome, HF.state())
    w = World(V("approved", tier="auto"))
    w.req(HF.BRING_TO_FRONT)
    w.run_card()
    check("a gate that answered at tier auto is not a person saying yes",
          HF.settings()["mode"] == HF.LEAVE_IN_PLACE
          and HF.state()["last"]["outcome"] == "refused")


def t_the_toml_cannot_make_it_automatic():
    for tier in ("auto", "notify", "never", "unreadable (KeyError)"):
        w = World(tier=tier)
        code, out = w.req(HF.BRING_TO_FRONT)
        check(f"tier {tier!r}: 503, no card, nothing applied",
              code == 503 and not w.later and "must be 'ask'" in out["error"], out)


def t_leave_in_place_while_waiting_withdraws_it():
    w = World()
    w.req(HF.BRING_TO_FRONT)
    w.req(HF.LEAVE_IN_PLACE)
    w.run_card()
    check("'Leave it where it is' while the card waited: approving it changes nothing",
          HF.settings()["mode"] == HF.LEAVE_IN_PLACE
          and HF.state()["last"]["outcome"] == "withdrawn", HF.state())
    w = World()
    w.req(HF.BRING_TO_FRONT)
    w.req(HF.LEAVE_IN_PLACE)
    check("after the default nothing is shown as waiting", HF.state()["waiting"] is False)
    code, out = w.req(HF.BRING_TO_FRONT)
    check("a second ask raises its own card", code == 202 and len(w.later) == 2
          and "already waiting" not in out["message"], (code, out, len(w.later)))
    w.later[1]()
    w.later[0]()
    check("the new card sets it; the old one ending later changes nothing shown",
          HF.settings()["mode"] == HF.BRING_TO_FRONT
          and HF.state()["last"]["outcome"] == "on", HF.state())


def t_leave_in_place_pressed_while_an_approved_card_writes_wins():
    """The same race jarvis_handoff_mode.py proves with its own pair: the
    narrower choice landing between the approved card's "was it withdrawn?"
    check and its write must not be overwritten by that card."""
    w = World()
    entered, release = threading.Event(), threading.Event()

    real = HF._save

    def slow(mode):
        if mode == HF.BRING_TO_FRONT:
            entered.set()
            release.wait(2)
        return real(mode)

    HF._save = slow
    try:
        HF.request(HF.BRING_TO_FRONT, gate=w.gate, tier_of=w.tier_of, spawn=w.later.append)
        card = threading.Thread(target=w.run_card)
        card.start()
        entered.wait(2)
        off = []
        t = threading.Thread(target=lambda: off.append(HF.request(HF.LEAVE_IN_PLACE)))
        t.start()
        t.join(0.3)
        early = bool(off)
        release.set()
        card.join(2)
        t.join(2)
    finally:
        HF._save = real
    check("'Leave it where it is' waits for the card's write, then the window stays put",
          off and off[0][0] == 200 and HF.settings()["mode"] == HF.LEAVE_IN_PLACE and not early,
          (off, HF.settings(), early))


def t_one_card_at_a_time():
    w = World()
    w.req(HF.BRING_TO_FRONT)
    code, out = w.req(HF.BRING_TO_FRONT)
    check("a second ask while one waits: no second card",
          code == 202 and len(w.later) == 1 and "already waiting" in out["message"], out)
    w2 = World()
    w2.req(HF.BRING_TO_FRONT)
    w2.run_card()
    code, out = w2.req(HF.BRING_TO_FRONT)
    check("already bringing it forward: nothing asked",
          code == 200 and "already" in out["message"], out)


def t_bad_input():
    w = World()
    for bad in ("yes", 1, None, "true", "", "raise", "leave_in_place "):
        code, out = w.req(bad)
        check(f"mode={bad!r} is refused", code == 400 and not w.later, out)


def t_the_last_card_in_plain_words():
    for verdict, outcome, words in (
            (V("approved", tier="auto"), "refused",
             "Your PC's settings do not let this be approved, so the window still stays where it "
             "is."),
            (V("denied"), "denied",
             "The card was turned down, so the window still stays where it is."),
            (V("approved"), "on",
             "You approved the card, so the window comes to the front when a captcha stops "
             "Jarvis.")):
        w = World(verdict)
        w.req(HF.BRING_TO_FRONT)
        w.run_card()
        last = HF.state()["last"]
        check(f"{outcome}: {words}", last["outcome"] == outcome and last["message"] == words
              and "why" in last, last)


# ==========================================================================
#   4. The view both apps read, and the route
# ==========================================================================

def t_the_view_carries_everything_both_apps_need():
    fresh_settings_path()
    v = HF.view()
    check("the mode, the two values and the default",
          v["mode"] == HF.LEAVE_IN_PLACE and v["modes"] == list(HF.MODES)
          and v["default"] == HF.LEAVE_IN_PLACE, v)
    check("every word the owner sees, word for word", v["words"] == HF.WORDS)
    check("it says this one is decided on the PC", v["pc_only"] is True)
    check("nothing is waiting and nothing was raised", v["waiting"] is False)
    HF.set_mode(HF.BRING_TO_FRONT)
    check("choosing 'Bring it to the front' shows up in the view",
          HF.view()["mode"] == HF.BRING_TO_FRONT
          and HF.view()["brings_to_front"] is True)


def t_the_route_is_installed_and_gated():
    check("the route has a home in the shipped routes",
          R.HANDOFF_FRONT_ROUTE == HF.PATH == "/api/chatbot/handoff_front")
    check("it is both a GET and a POST route",
          R.HANDOFF_FRONT_ROUTE in R.GET_ROUTES and R.HANDOFF_FRONT_ROUTE in R.POST_ROUTES)
    check("it is NOT one of the hand-off's own picture or input routes",
          not R.HANDOFF_FRONT_ROUTE.startswith("/api/chatbot/handoff/"))
    fresh_settings_path()
    code, out = R.handle_handoff_front_get()
    check("GET answers the view", code == 200 and out["mode"] == HF.LEAVE_IN_PLACE, out)
    later = []
    code, out = R.handle_handoff_front({"mode": "bring_to_front"}, spawn=later.append)
    check("POST goes through the module's own request()",
          code == 202 and out["waiting"] and len(later) == 1, out)
    code, out = R.handle_handoff_front({"mode": "always"}, spawn=later.append)
    check("POST refuses anything but the two names", code == 400, out)
    HF._reset_for_tests()


# ==========================================================================
#   5. The card, and what the setting never does
# ==========================================================================

def t_the_card_says_what_it_changes():
    fresh_settings_path()
    text = HF.card_text()
    check("the card says the window comes to the front",
          "to the front" in text and "captcha" in text)
    check("the card says plainly what it costs - the owner's screen and keyboard",
          "screen" in text and "keyboard" in text)
    check("the card says the default and how to go back",
          "left exactly where it is" in text and "Leave it where it is" in text
          and "instant" in text)
    check("the card says Jarvis still never solves the captcha",
          "never solves" in text)
    check("the card says what happens if the owner says no",
          "If you say no" in text and "stays where it is" in text)
    check("the card says nothing about this PC being left (nothing does)",
          "leaves this pc" not in text.lower())


def t_no_picture_and_no_window_ever_reaches_this_setting():
    """This module decides ONE word. It has no code that pictures a page, moves a
    mouse, types, or raises a window - and the hand-off module still opens no
    file of its own."""
    src = (HERE / "jarvis_handoff_front.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    bad = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call)
           and isinstance(n.func, ast.Attribute)
           and n.func.attr in ("screenshot", "click", "type", "press", "wheel", "goto",
                               "evaluate", "fill", "launch", "SetForegroundWindow",
                               "ShowWindow", "bring_to_front")}
    mouse = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "mouse"]
    check("no picture, no mouse, no page and no window call of its own",
          not bad and not mouse, bad)
    check("no window handle or title is ever read or held",
          "hwnd" not in src and "EnumWindows" not in src)
    check("it is shipped", "jarvis_handoff_front.py" in SHIPPED)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("apply-patches.ps1 ships it", "'jarvis_handoff_front.py'" in ps1)


def t_the_gate_side_is_wired():
    """The action is on the PC-only list (Windows Hello), it has a plain title
    for the card, and the shipped tier table says 'ask'."""
    import jarvis_owner_check as OC
    check("the action needs Windows Hello on this PC (PC_ONLY_ACTIONS)",
          HF.ACTION in OC.PC_ONLY_ACTIONS, sorted(OC.PC_ONLY_ACTIONS))
    import jarvis_card_words as W
    check("the card has a plain title", HF.ACTION in W.TITLES, W.TITLES.get(HF.ACTION))
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("the shipped tier table says 'ask'", f'{HF.ACTION} = "ask"' in toml)
    patch = (HERE / "handoff-front.patch").read_text(encoding="utf-8")
    check("handoff-front.patch adds the action to the gate's own tables",
          f'"{HF.ACTION}"' in patch and "jarvis_gate.py" in patch)


def t_the_asks_first_page_can_name_it():
    import jarvis_asks_first as AF
    ids = [a for _, rows in AF.GROUPS for a in rows]
    check("the loosening is a row on 'What asks first', so the page is complete",
          HF.ACTION in ids, [i for i in ids if i.startswith("handoff")])


def t_the_audit_line_carries_no_picture_and_no_token():
    """This module's own audit line carries an outcome word and nothing else."""
    fresh_settings_path()
    AUDIT.clear()
    HF.set_mode(HF.BRING_TO_FRONT)
    HF.request(HF.LEAVE_IN_PLACE, gate=lambda a, d, p: V("approved"),
               tier_of=lambda a: "ask", spawn=lambda fn: fn())
    kinds = {k for k, _ in AUDIT}
    check("the audit lines are this module's own kind",
          kinds <= {"chatbot.handoff_front"}, kinds)
    typed = json.dumps(AUDIT)
    check("no picture, no page and no token is in any audit line",
          "jpeg" not in typed and "hf_" not in typed and "s3cr3t" not in typed, typed)


# ==========================================================================

def main() -> int:
    tests = [t_default_is_leave_in_place, t_set_and_read_back, t_a_damaged_file_fails_closed,
             t_raise_only_when_stuck_and_nobody_is_solving_it_on_the_phone,
             t_bring_to_front_asks_and_leave_in_place_is_instant, t_no_yes_changes_nothing,
             t_the_toml_cannot_make_it_automatic, t_leave_in_place_while_waiting_withdraws_it,
             t_leave_in_place_pressed_while_an_approved_card_writes_wins,
             t_one_card_at_a_time, t_bad_input, t_the_last_card_in_plain_words,
             t_the_view_carries_everything_both_apps_need,
             t_the_route_is_installed_and_gated, t_the_card_says_what_it_changes,
             t_no_picture_and_no_window_ever_reaches_this_setting,
             t_the_gate_side_is_wired, t_the_asks_first_page_can_name_it,
             t_the_audit_line_carries_no_picture_and_no_token]
    for fn in tests:
        print(f"--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(f"{fn.__name__} ran without crashing")
            print(f"FAIL  {fn.__name__} ran without crashing\n{traceback.format_exc()}")
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + "; ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
