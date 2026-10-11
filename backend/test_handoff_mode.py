"""test_handoff_mode.py - how long "Solve it here" stays on offer: the
owner's two choices, the default, and the card that guards the longer one.

    python3 backend/test_handoff_mode.py

THE OWNER'S DECISION (CLAUDE.md, made 2026-10-08, his own words: "make this a
setting for both options with 1 as the default"; docs/CAPTCHA-HANDOFF-DESIGN.md
section 5). The captcha hand-off used to end after 45 s of no picture asked for
with a 15-minute ceiling - both chosen, neither measured. It is now a setting:

  * "Stop early" (the DEFAULT, and the stricter one): about a minute of no
    interaction ends the hand-off AND the PC says plainly that Jarvis is stuck
    on a puzzle in that window, naming it, leaving the window for the owner to
    solve there.
  * "Keep offering it": the live picture stays on offer for the full
    15-minute ceiling, so the owner can pick their phone up late. A window of
    theirs stays on offer fifteen times longer - MORE exposure - so choosing it
    is ONE approval card, and (jarvis_owner_check.PC_ONLY_ACTIONS) it is
    approved on the PC with Windows Hello. Going back is instant.

No pytest, no network, no model, no real browser. Real files in a temporary
folder for the setting itself; the gate and the tier are stand-ins, the same
shape test_watch_notify.py proves that shape with. The two clocks are measured
against jarvis_handoff.py's own stand-in window and a clock moved by hand.
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

require_shipped("jarvis_handoff_mode.py", "jarvis_handoff.py", "jarvis_chatbot.py",
                "jarvis_chatbot_routes.py", "jarvis_support.py", "jarvis_card_words.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-handoff-mode-"))
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
import jarvis_handoff_mode as HM  # noqa: E402
import jarvis_support as SUP  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: counted on its own, never a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


# ==========================================================================
#   1. The two values and the default the owner was promised
# ==========================================================================

def fresh_settings_path() -> Path:
    d = Path(tempfile.mkdtemp(prefix="jarvis-handoff-mode-cfg-", dir=_TMP))
    fw.CONFIG_DIR = d
    HM._reset_for_tests()
    return HM.settings_path()


def t_default_is_stop_early():
    fresh_settings_path()
    check("no file at all: 'Stop early', the owner's default",
          HM.settings() == {"mode": "stop_early", "why": ""}, HM.settings())
    check("the two values are exactly what the owner was promised",
          HM.MODES == ("stop_early", "keep_offering") and HM.DEFAULT == "stop_early"
          and HM.KEEP_OFFERING == "keep_offering")
    check("the default is the quick cut-off, about a minute",
          HM.idle_seconds() == HM.STOP_AFTER_S == 60.0)
    check("both choices share the 15-minute ceiling",
          HM.ceiling_seconds() == HM.CEILING_S == 900.0
          and HM.set_mode(HM.KEEP_OFFERING)["mode"] == "keep_offering"
          and HM.ceiling_seconds() == 900.0)
    check("'Keep offering it': the idle clock is the ceiling itself",
          HM.is_patient() and HM.idle_seconds() == 900.0)
    check("and back to 'Stop early' removes it again",
          HM.set_mode(HM.STOP_EARLY)["mode"] == "stop_early" and not HM.is_patient())


def t_set_and_read_back():
    fresh_settings_path()
    check("chosen and saved", HM.set_mode(HM.KEEP_OFFERING) == {"mode": "keep_offering",
                                                                "why": "", "ok": True})
    check("reads back", HM.settings()["mode"] == "keep_offering" and HM.is_patient())
    check("a value that is not one of the two is refused",
          _raises(ValueError, lambda: HM.set_mode("forever")))
    check("... and reading the file afterwards shows nothing changed",
          HM.settings()["mode"] == "keep_offering")


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
    for raw in ("not json", "[]", json.dumps({"mode": "forever"}),
                json.dumps({"mode": None}), json.dumps({"mode": True})):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(raw, encoding="utf-8")
        st = HM.settings()
        check(f"{raw!r}: 'Stop early', and why says so",
              st["mode"] == "stop_early" and st["why"], st)
    check("a damaged file never leaves the window on offer for 15 minutes",
          HM.settings()["mode"] == HM.DEFAULT and HM.idle_seconds() == HM.STOP_AFTER_S)
    check("the reason is plain English, not a stack trace",
          "damaged" in HM.settings()["why"] and "Traceback" not in HM.settings()["why"])
    check("the words for a damaged file are the same on both apps",
          HM.settings()["why"] == HM.WORDS["damaged"])


# ==========================================================================
#   2. request(): the looser value asks first, the stricter one is instant
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
        return HM.request(mode, gate=self.gate, tier_of=self.tier_of,
                          spawn=self.later.append)

    def run_card(self):
        for fn in list(self.later):
            fn()
        self.later.clear()


def t_keep_offering_asks_and_stop_early_is_instant():
    w = World()
    code, out = w.req(HM.KEEP_OFFERING)
    check("'Keep offering it' answers 202 waiting and changes nothing yet",
          code == 202 and out["waiting"] and out["mode"] == HM.STOP_EARLY
          and HM.settings()["mode"] == HM.STOP_EARLY and not w.cards, out)
    check("... and still stops early while the card waits",
          HM.idle_seconds() == HM.STOP_AFTER_S)
    check("one card is queued, under the hand-off's own action",
          len(w.later) == 1)
    w.run_card()
    check("approved: the setting is the patient one, once",
          w.cards and w.cards[0][0] == HM.ACTION == "handoff_keep_offering"
          and w.cards[0][1]["leaves_this_pc"] is False
          and HM.settings()["mode"] == HM.KEEP_OFFERING, (HM.settings(), w.cards))
    check("... so the idle clock is now the full ceiling",
          HM.idle_seconds() == HM.CEILING_S)
    check("status: not waiting, last card 'on'",
          HM.state()["waiting"] is False and HM.state()["last"]["outcome"] == "on")
    code, out = w.req(HM.STOP_EARLY)
    check("'Stop early': immediate, no card, and it is back to a minute",
          code == 200 and len(w.cards) == 1 and out["waiting"] is False
          and HM.settings()["mode"] == HM.STOP_EARLY
          and HM.idle_seconds() == HM.STOP_AFTER_S, out)


def t_no_yes_changes_nothing():
    for outcome in ("denied", "timed_out", "refused"):
        w = World(V(outcome))
        w.req(HM.KEEP_OFFERING)
        w.run_card()
        check(f"{outcome}: it still stops early",
              HM.settings()["mode"] == HM.STOP_EARLY
              and HM.state()["last"]["outcome"] == outcome, HM.state())
    w = World(V("approved", tier="auto"))
    w.req(HM.KEEP_OFFERING)
    w.run_card()
    check("a gate that answered at tier auto is not a person saying yes",
          HM.settings()["mode"] == HM.STOP_EARLY
          and HM.state()["last"]["outcome"] == "refused")


def t_the_toml_cannot_make_it_automatic():
    for tier in ("auto", "notify", "never", "unreadable (KeyError)"):
        w = World(tier=tier)
        code, out = w.req(HM.KEEP_OFFERING)
        check(f"tier {tier!r}: 503, no card, nothing applied",
              code == 503 and not w.later and "must be 'ask'" in out["error"], out)


def t_stop_early_while_waiting_withdraws_it():
    w = World()
    w.req(HM.KEEP_OFFERING)
    w.req(HM.STOP_EARLY)
    w.run_card()
    check("'Stop early' while the card waited: approving it changes nothing",
          HM.settings()["mode"] == HM.STOP_EARLY
          and HM.state()["last"]["outcome"] == "withdrawn", HM.state())
    w = World()
    w.req(HM.KEEP_OFFERING)
    w.req(HM.STOP_EARLY)
    check("after 'Stop early' nothing is shown as waiting", HM.state()["waiting"] is False)
    code, out = w.req(HM.KEEP_OFFERING)
    check("a second ask raises its own card", code == 202 and len(w.later) == 2
          and "already waiting" not in out["message"], (code, out, len(w.later)))
    w.later[1]()
    w.later[0]()
    check("the new card sets it; the old one ending later changes nothing shown",
          HM.settings()["mode"] == HM.KEEP_OFFERING
          and HM.state()["last"]["outcome"] == "on", HM.state())


def t_stop_early_pressed_while_an_approved_card_writes_wins():
    """The same red team (R5) jarvis_learning_switch.py was fixed for: 'Stop
    early' landing between the approved card's "was it withdrawn?" check and
    its write must not be overwritten by that card."""
    w = World()
    entered, release = threading.Event(), threading.Event()

    real = HM._save

    def slow(mode):
        if mode == HM.KEEP_OFFERING:
            entered.set()
            release.wait(2)
        return real(mode)

    HM._save = slow
    try:
        HM.request(HM.KEEP_OFFERING, gate=w.gate, tier_of=w.tier_of, spawn=w.later.append)
        card = threading.Thread(target=w.run_card)
        card.start()
        entered.wait(2)
        off = []
        t = threading.Thread(target=lambda: off.append(HM.request(HM.STOP_EARLY)))
        t.start()
        t.join(0.3)
        early = bool(off)
        release.set()
        card.join(2)
        t.join(2)
    finally:
        HM._save = real
    check("'Stop early' waits for the card's write, then the setting is 'Stop early'",
          off and off[0][0] == 200 and HM.settings()["mode"] == HM.STOP_EARLY and not early,
          (off, HM.settings(), early))


def t_one_card_at_a_time():
    w = World()
    w.req(HM.KEEP_OFFERING)
    code, out = w.req(HM.KEEP_OFFERING)
    check("a second ask while one waits: no second card",
          code == 202 and len(w.later) == 1 and "already waiting" in out["message"], out)
    w2 = World()
    w2.req(HM.KEEP_OFFERING)
    w2.run_card()
    code, out = w2.req(HM.KEEP_OFFERING)
    check("already patient: nothing asked", code == 200 and "already" in out["message"], out)


def t_bad_input():
    w = World()
    for bad in ("yes", 1, None, "true", "", "stop"):
        code, out = w.req(bad)
        check(f"mode={bad!r} is refused", code == 400 and not w.later, out)


def t_the_last_card_in_plain_words():
    for verdict, outcome, words in (
            (V("approved", tier="auto"), "refused",
             "Your PC's settings do not let this be approved, so it still stops early."),
            (V("denied"), "denied",
             "The card was turned down, so the hand-off still stops early."),
            (V("approved"), "on",
             "You approved the card, so the offer stays for the full 15 minutes.")):
        w = World(verdict)
        w.req(HM.KEEP_OFFERING)
        w.run_card()
        last = HM.state()["last"]
        check(f"{outcome}: {words}", last["outcome"] == outcome and last["message"] == words
              and "why" in last, last)


# ==========================================================================
#   3. The view both apps read
# ==========================================================================

def t_the_view_carries_everything_both_apps_need():
    fresh_settings_path()
    v = HM.view()
    check("the mode, the two values and the default",
          v["mode"] == HM.STOP_EARLY and v["modes"] == list(HM.MODES)
          and v["default"] == HM.STOP_EARLY, v)
    check("every word the owner sees, word for word", v["words"] == HM.WORDS)
    check("the two clocks, so an app never guesses",
          v["idle_s"] == HM.STOP_AFTER_S and v["ceiling_s"] == HM.CEILING_S, v)
    check("it says this one is decided on the PC", v["pc_only"] is True)
    HM.set_mode(HM.KEEP_OFFERING)
    check("choosing 'Keep offering it' shows up in the view",
          HM.view()["mode"] == HM.KEEP_OFFERING and HM.view()["patient"] is True)


# ==========================================================================
#   4. The hand-off itself: the two clocks come from the setting
# ==========================================================================

class _Page:
    def __init__(self, url):
        self.url = url
        self.mouse = types.SimpleNamespace(click=lambda x, y: None, wheel=lambda x, y: None)
        self.keyboard = types.SimpleNamespace(type=lambda t: None, press=lambda k: None)

    def screenshot(self, **kw):
        return b"\xff\xd8\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01\xff\xd9"


class _Window:
    def __init__(self, url, hosts, sign_in=()):
        self._page = _Page(url)
        self.chat_hosts = hosts
        self.sign_in_hosts = sign_in

    def _page_alive(self):
        return True

    def _call(self, fn, timeout):
        return fn()


class _Clock:
    t = 1000.0

    def __call__(self):
        return self.t


CLOCK = _Clock()
TIER = CB.Tier("one_card", "http://127.0.0.1:11434", "m", 4096)


def fresh_handoff():
    with CB._LOCK:
        CB._SESSIONS.clear()
    SUP._reset_for_tests()
    CLOCK.t = 1000.0
    HO._reset_for_tests(clock=CLOCK)


def session(code="captcha"):
    s = CB.Session(id="chat_000000000001", chatbot="gemini_web", goal="g",
                   limits=CB.Limits(5, 10), tier=TIER, state="paused", paused_code=code)
    s.adapter = _Window("https://gemini.google.com/app", ("gemini.google.com",),
                        ("accounts.google.com",))
    with CB._LOCK:
        CB._SESSIONS[s.id] = s
    return s


def t_default_ends_the_hand_off_at_about_a_minute_and_names_the_window():
    """The owner's first promise: under the default, an idle hand-off ends at
    about a minute AND the PC says plainly that Jarvis is stuck in that window,
    naming it."""
    fresh_settings_path()
    fresh_handoff()
    s = session()
    started = R.handle_post(R.HANDOFF_START_ROUTE, {"kind": "chatbot", "id": s.id})
    hid = started[1]["handoff"]
    check("the default start answer carries the owner's own numbers",
          started[1]["idle_s"] == 60.0 and started[1]["ceiling_s"] == 900.0
          and started[1]["patient"] is False, started[1])
    check("the hand-off is on offer, and says which window",
          HO.offer()["available"] is True and HO.offer()["site"] == "Gemini")
    # Just under a minute: still on offer.
    CLOCK.t += 59.0
    check("59 s with nobody looking: still on offer", HO.frame(hid)[0] == 200)
    # A whole minute with nothing asked for: it ends, and the PC says where.
    CLOCK.t += 61.0
    code, out = HO.frame(hid)
    check("a minute with nobody looking: it ends ('idle')",
          code == 410 and out["ended"] == "idle", (code, out))
    off = HO.offer()
    stuck = off.get("stuck")
    check("and the PC's own line names the window Jarvis is stuck on",
          isinstance(stuck, dict) and "Gemini" in stuck["title"]
          and "captcha" in stuck["text"] and "this PC" in stuck["title"], off)
    check("... and says the hand-off to the phone has ended",
          "has ended" in stuck["text"] and "Solve it here" in stuck["text"], stuck)
    check("the line is two fixed sentences, never a word from the page",
          stuck == HO.stuck_line("Gemini", "captcha"))
    check("a hand-off that ended for another reason carries no such line",
          _no_stuck_after("owner"))


def _no_stuck_after(why) -> bool:
    fresh_handoff()
    s = session()
    hid = R.handle_post(R.HANDOFF_START_ROUTE, {"kind": "chatbot", "id": s.id})[1]["handoff"]
    if why == "owner":
        HO.end(hid)
    else:
        s.state = "running"
        HO.frame(hid)
    return HO.offer().get("stuck") is None


def t_patient_keeps_it_on_offer_past_a_minute_and_up_to_the_ceiling():
    """The owner's second promise: under 'Keep offering it' the offer survives
    well past a minute, right up to the 15-minute ceiling."""
    fresh_settings_path()
    HM.set_mode(HM.KEEP_OFFERING)
    fresh_handoff()
    s = session()
    started = R.handle_post(R.HANDOFF_START_ROUTE, {"kind": "chatbot", "id": s.id})
    hid = started[1]["handoff"]
    check("the start answer says so, with the ceiling as the idle time",
          started[1]["patient"] is True and started[1]["idle_s"] == 900.0
          and started[1]["ceiling_s"] == 900.0, started[1])
    CLOCK.t += 61.0
    check("a minute with nobody looking: still on offer", HO.frame(hid)[0] == 200)
    CLOCK.t += 300.0
    check("six minutes in: still on offer (the owner picked their phone up late)",
          HO.offer()["available"] is True and HO.offer().get("stuck") is None)
    code, out = HO.frame(hid)
    check("... and a picture still comes back", code == 200 and out.get("jpeg"), code)
    check("nothing was said about being stuck, because it never stopped",
          HO.offer().get("stuck") is None and HO.offer()["patient"] is True)
    # Up to the ceiling: the picture keeps refreshing it, so the ceiling is the
    # end, exactly as promised.
    for _ in range(int(HM.CEILING_S // 30) + 3):
        CLOCK.t += 30
        code, out = HO.frame(hid)
        if code != 200:
            break
    check("however it goes, it ends at the 15-minute ceiling ('time'), not at a minute",
          code == 410 and out["ended"] == "time", (code, out))
    check("the ceiling ending is not the 'stuck' line either",
          HO.offer().get("stuck") is None)


def t_the_setting_is_read_at_every_check_not_once_at_start():
    fresh_settings_path()
    fresh_handoff()
    s = session()
    hid = R.handle_post(R.HANDOFF_START_ROUTE, {"kind": "chatbot", "id": s.id})[1]["handoff"]
    CLOCK.t += 61.0
    check("started under the default: a minute ends it", HO.frame(hid)[0] == 410)
    # The same hand-off, started under the patient choice, is not cut off at a
    # minute even if the setting was the default when start() read the clocks.
    HM.set_mode(HM.KEEP_OFFERING)
    fresh_handoff()
    s = session()
    hid = R.handle_post(R.HANDOFF_START_ROUTE, {"kind": "chatbot", "id": s.id})[1]["handoff"]
    CLOCK.t += 61.0
    check("and the choice made before it started is what counts", HO.frame(hid)[0] == 200)


def t_an_older_backend_reads_as_stop_early():
    """A PC whose backend is older than this setting: the hand-off module reads
    the safe fallback, never a crash and never the patient value."""
    fresh_settings_path()
    real = HO._mode
    HO._mode = lambda: None
    try:
        check("idle: the safe fallback, about a minute", HO.idle_seconds() == 60.0)
        check("ceiling: the 15-minute fallback", HO.ceiling_seconds() == 900.0)
        check("and it is never the patient one", HO.patient() is False)
    finally:
        HO._mode = real


# ==========================================================================
#   5. The route, the card's words, and the code-level promises
# ==========================================================================

def t_the_route_is_installed_and_gated():
    check("the setting's route is on the server's own lists",
          R.HANDOFF_MODE_ROUTE in R.GET_ROUTES and R.HANDOFF_MODE_ROUTE in R.POST_ROUTES)
    check("... and it is NOT one of the hand-off's picture or input routes",
          not R.HANDOFF_MODE_ROUTE.startswith("/api/chatbot/handoff/"),
          R.HANDOFF_MODE_ROUTE)
    code, out = R.handle_post(R.HANDOFF_MODE_ROUTE, {"mode": HM.STOP_EARLY})
    check("POST through the routes layer: at once, no card",
          code == 200 and out["ok"] is True and out["waiting"] is False, out)
    code, out = R.handle_post(R.HANDOFF_MODE_ROUTE, {"mode": "keep_offering"})
    check("... and 'Keep offering it' waits for a card", code == 202 and out["waiting"], out)
    R.handle_post(R.HANDOFF_MODE_ROUTE, {"mode": HM.STOP_EARLY})
    code, out = R.handle_handoff_mode_get()
    check("GET through the routes layer: the whole view",
          code == 200 and out["mode"] == HM.STOP_EARLY and out["words"] == HM.WORDS, out)
    check("a body with no mode at all is refused", R.handle_post(R.HANDOFF_MODE_ROUTE, {})[0] == 400)


def t_the_card_says_what_it_changes():
    text = HM.card_text()
    check("the card names the 15 minutes it is about", "15" in text)
    check("... says the picture is still never saved", "never saved" in text)
    check("... says turning it off again is instant", "instant" in text)
    check("... and says plainly what happens if the owner says no",
          "If you say no" in text and "about a minute" in text)
    check("the card says nothing about this PC being left (nothing does)",
          "leaves this pc" not in text.lower())


def t_no_picture_and_no_word_from_the_page_ever_reaches_this_setting():
    """This module decides ONE word. It has no code that pictures a page,
    moves a mouse or keeps a typed character, and the hand-off module still
    has no file access of its own."""
    src = (HERE / "jarvis_handoff_mode.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    bad = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call)
           and isinstance(n.func, ast.Attribute)
           and n.func.attr in ("screenshot", "click", "type", "press", "wheel", "goto",
                               "evaluate", "fill", "launch")}
    mouse = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "mouse"]
    check("no picture, no mouse, no page of its own", not bad and not mouse, bad)
    check("the hand-off module still opens no file of its own",
          "open(" not in _code_only((HERE / "jarvis_handoff.py").read_text(encoding="utf-8")))
    check("it is shipped", "jarvis_handoff_mode.py" in SHIPPED)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("apply-patches.ps1 ships it", "'jarvis_handoff_mode.py'" in ps1)


def _code_only(src: str) -> str:
    import io
    import tokenize
    tree = ast.parse(src)
    doc = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            doc.update(range(body[0].lineno, body[0].end_lineno + 1))
    return " ".join(t.string for t in tokenize.generate_tokens(io.StringIO(src).readline)
                    if t.type != tokenize.COMMENT and t.start[0] not in doc)


def t_the_gate_side_is_wired():
    """The action is on the PC-only list (Windows Hello), it has a plain title
    for the card, and the shipped tier table says 'ask'."""
    import jarvis_owner_check as OC
    check("the action needs Windows Hello on this PC (PC_ONLY_ACTIONS)",
          HM.ACTION in OC.PC_ONLY_ACTIONS, sorted(OC.PC_ONLY_ACTIONS))
    import jarvis_card_words as W
    check("the card has a plain title", HM.ACTION in W.TITLES, W.TITLES.get(HM.ACTION))
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("the shipped tier table says 'ask'",
          f'{HM.ACTION} = "ask"' in toml or f'{HM.ACTION} ' in toml and '"ask"' in toml)
    patch = (HERE / "handoff-mode.patch").read_text(encoding="utf-8")
    check("handoff-mode.patch adds the action to the gate's own tables",
          f'"{HM.ACTION}"' in patch and "jarvis_gate.py" in patch)


def t_the_asks_first_page_can_name_it():
    import jarvis_asks_first as AF
    ids = [a for _, rows in AF.GROUPS for a in rows]
    check("the loosening is a row on 'What asks first', so the page is complete",
          HM.ACTION in ids, [i for i in ids if i.startswith("handoff")])


def t_the_audit_line_carries_no_picture_and_no_token():
    """This module's own audit line carries an outcome word and nothing else."""
    fresh_settings_path()
    AUDIT.clear()
    HM.set_mode(HM.KEEP_OFFERING)
    HM.request(HM.STOP_EARLY, gate=lambda a, d, p: V("approved"),
               tier_of=lambda a: "ask", spawn=lambda fn: fn())
    kinds = {k for k, _ in AUDIT}
    check("the audit lines are this module's own kind",
          kinds <= {"chatbot.handoff_mode"}, kinds)
    typed = json.dumps(AUDIT)
    check("no picture, no page and no token is in any audit line",
          "jpeg" not in typed and "ho_" not in typed and "s3cr3t" not in typed, typed)


# ==========================================================================

def main() -> int:
    tests = [t_default_is_stop_early, t_set_and_read_back, t_a_damaged_file_fails_closed,
             t_keep_offering_asks_and_stop_early_is_instant, t_no_yes_changes_nothing,
             t_the_toml_cannot_make_it_automatic, t_stop_early_while_waiting_withdraws_it,
             t_stop_early_pressed_while_an_approved_card_writes_wins,
             t_one_card_at_a_time, t_bad_input, t_the_last_card_in_plain_words,
             t_the_view_carries_everything_both_apps_need,
             t_default_ends_the_hand_off_at_about_a_minute_and_names_the_window,
             t_patient_keeps_it_on_offer_past_a_minute_and_up_to_the_ceiling,
             t_the_setting_is_read_at_every_check_not_once_at_start,
             t_an_older_backend_reads_as_stop_early,
             t_the_route_is_installed_and_gated, t_the_card_says_what_it_changes,
             t_no_picture_and_no_word_from_the_page_ever_reaches_this_setting,
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
