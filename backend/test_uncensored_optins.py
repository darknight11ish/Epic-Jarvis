"""test_uncensored_optins.py - the uncensored opt-ins' way IN.

    python3 backend/test_uncensored_optins.py

THE OWNER'S DECISION (2026-10-10, "Decision 5" -
`.dsh-scratch/QUEUE-OWNER-DECISIONS-2026-10-10.md`): "Uncensored: both of
these - (a) one clearly-labelled opt-in model for fiction/role-play, never the
everyday assistant and never a default, and (b) make the abliterated models
already on disk usable as opt-in choices rather than downloading anything
new." `jarvis_optin_models.py` builds both halves; THIS suite proves the part
that makes them usable at all, which is the part PR #231 left out:

  * OFF BY DEFAULT, and ON IS ONE APPROVAL CARD. Turning either switch on
    raises exactly ONE card, under `uncensored_models_enable` /
    `fiction_roleplay_enable`, at tier "ask" in the gate's own tables - and
    nothing changes if that card is denied, times out, is refused, or the
    setting is turned back off while it waits. Turning either one OFF is
    instant and asks nothing. This is the project's standing rule for
    anything that loosens a limit (`jarvis_gate.py`'s tier table is where it
    is expressed, and `uncensored-optins.patch` is where it is written down).
  * THE ROUTE. `GET`/`POST /api/models/uncensored` - one route, wrapped round
    the running server's handler the way `jarvis_phone_notifications.install`
    already does it: origin and token checked first, any other path passed
    straight through.
  * RULE 1, IN CODE. With the model store somewhere other than this PC,
    nothing is offered, the fiction lane refuses, and an ON is refused BEFORE
    any card - so there is nothing to approve. Nothing private, and nothing
    at all, is ever handed to a model that is not the local one.
  * THE WIRING IS REALLY THERE: the two tier lines in the shipped settings
    template, the two gate-table entries in `uncensored-optins.patch`, the
    patch registered last in `apply-patches.ps1`, and the patch applying,
    reversing and building the patch stack's own text - and, when the live
    `jarvis_gate.py` is present, the real gate's own `_RISK` table answering.

No model, no network, no Ollama and no live backend. The gate, the tier and
the thread a card is raised on are all stand-ins, which is the shape
`test_phone_notifications.py` already proves that shape with.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

#: A folder THIS test made, before the module is imported: the two switches are
#: real files, and the owner's own ~/.openjarvis must not be read or written.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-uncensored-optins-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
(_TMP / "config").mkdir(parents=True, exist_ok=True)
os.environ.pop("JARVIS_OPTIN_MODEL_ROOTS", None)

#: `jarvis_optin_models.py` is required BY PATH, not with `require_shipped`
#: (the way test_optin_models.py already does it, and for the same reason): on
#: the owner's PC the deployed copy is the one from before this change until
#: `apply-patches.ps1` is next run, and a suite that refuses to start there
#: would prove nothing about the repository's own copy.
if not (HERE / "jarvis_optin_models.py").is_file():
    print("FAIL  backend/jarvis_optin_models.py is missing from this repository")
    sys.exit(1)

import jarvis_optin_models as M  # noqa: E402
import _stack  # noqa: E402
import _where  # noqa: E402

PATCH = HERE / "uncensored-optins.patch"
PS1 = HERE.parent / "scripts" / "apply-patches.ps1"
TOML = HERE / "rebuilt" / "jarvis-framework.toml"

PASSED, FAILED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this checkout cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def fresh_config():
    d = Path(tempfile.mkdtemp(prefix="cfg-", dir=_TMP))
    os.environ["OPENJARVIS_CONFIG_DIR"] = str(d)
    M._reset_for_tests()
    return d


# ==========================================================================
#   The stand-ins: a gate, a tier, and a thread a card is raised on
# ==========================================================================

class V:
    def __init__(self, outcome, allowed=None, tier="ask"):
        self.outcome, self.tier = outcome, tier
        self.allowed = (outcome == "approved") if allowed is None else allowed
        self.reason = outcome


class World:
    """One run of the route's own logic, with the gate handed in.

    `spawn` is what the module hands a card to; collecting the callables
    instead of starting threads keeps the test deterministic, which is what
    test_phone_notifications.py does for the same reason.
    """

    def __init__(self, verdict=None, tier="ask"):
        fresh_config()
        self.cards, self.later = [], []
        self.verdict, self.tier = verdict or V("approved"), tier

    def gate(self, action, detail, prompt):
        self.cards.append({"action": action, "detail": detail, "prompt": prompt})
        return self.verdict

    def tier_of(self, action):
        return self.tier

    def req(self, body):
        return M.request(body, gate=self.gate, tier_of=self.tier_of,
                         spawn=self.later.append)

    def run_card(self):
        for fn in list(self.later):
            fn()
        self.later.clear()


# ==========================================================================
#   1. Off by default, on this PC, and unwired until the patch says otherwise
# ==========================================================================

def t_off_by_default():
    fresh_config()
    v = M.view()
    check("a machine that has never run this: both switches off",
          v["on"] is False and v["fiction"]["on"] is False, v)
    check("...nothing is offered", v["choices"] == [], v["choices"])
    check("...no card is waiting", not any(v["waiting"].values()), v["waiting"])
    check("...and the empty screen says why in plain words",
          "off" in v["off"].lower() and "download" in v["off"].lower(), v["off"])
    check("the fiction lane refuses while it is off",
          M.ensure_fiction_allowed()["ok"] is False)
    check("the route's own state names both switches, never one shared flag",
          sorted(M.state()["waiting"]) == sorted([M.ACTION_MODELS, M.ACTION_FICTION]),
          M.state()["waiting"])
    check("the two actions are two names", M.ACTION_MODELS != M.ACTION_FICTION)


# ==========================================================================
#   2. Turning either one ON is ONE card; OFF is instant (the shape
#      test_phone_notifications.py already proves for its own setting)
# ==========================================================================

def t_on_raises_exactly_one_card():
    w = World()
    code, out = w.req({"on": True})
    check("ON: 202 waiting, and nothing changed yet",
          code == 202 and out["waiting"] is True
          and out["uncensored_choices_offered"] is False
          and M._flag("uncensored_choices_offered") is False
          and w.cards == [] and len(w.later) == 1, out)
    w.run_card()
    check("approved: the uncensored list is ON",
          M._flag("uncensored_choices_offered") is True, M.state())
    check("...the card was raised under the gate's own action name",
          w.cards[0]["action"] == M.ACTION_MODELS, w.cards)
    check("...and the card says this does not leave the PC",
          w.cards[0]["detail"]["leaves_this_pc"] is False, w.cards[0]["detail"])
    check("...and it is the CARD's text that was handed to the gate, not a summary",
          w.cards[0]["prompt"] == M.CARD_MODELS, w.cards[0]["prompt"][:80])
    check("...and the last card is reported as enabled",
          M.state()["last"][M.ACTION_MODELS]["outcome"] == "enabled", M.state())

    w = World()
    code, out = w.req({"fiction": True})
    check("the OTHER switch raises its own card, under its own action",
          code == 202 and len(w.later) == 1, out)
    w.run_card()
    check("approved: the fiction lane is ON",
          M._flag("fiction_roleplay_on") is True, M.state())
    check("...under fiction_roleplay_enable, not the other one",
          w.cards[0]["action"] == M.ACTION_FICTION, w.cards)


def t_no_yes_changes_nothing():
    for outcome in ("denied", "timed_out", "refused"):
        w = World(V(outcome))
        w.req({"on": True})
        w.run_card()
        check(f"uncensored list: {outcome} leaves it OFF",
              M._flag("uncensored_choices_offered") is False
              and M.state()["last"][M.ACTION_MODELS]["outcome"] == outcome,
              M.state())
    for outcome in ("denied", "timed_out", "refused"):
        w = World(V(outcome))
        w.req({"fiction": True})
        w.run_card()
        check(f"fiction lane: {outcome} leaves it OFF",
              M._flag("fiction_roleplay_on") is False
              and M.state()["last"][M.ACTION_FICTION]["outcome"] == outcome,
              M.state())
    w = World(V("approved", tier="auto"))
    w.req({"on": True})
    w.run_card()
    check("a gate that answered at tier auto is not a person saying yes",
          M._flag("uncensored_choices_offered") is False
          and M.state()["last"][M.ACTION_MODELS]["outcome"] == "refused", M.state())


def t_the_settings_file_cannot_make_it_automatic():
    for tier in ("auto", "notify", "never", "unreadable (KeyError)"):
        w = World(tier=tier)
        code, out = w.req({"on": True})
        check(f"tier {tier!r}: 503, no card, nothing applied",
              code == 503 and not w.later and not w.cards
              and M._flag("uncensored_choices_offered") is False
              and "must be 'ask'" in out["error"], out)


def t_off_is_instant_and_withdraws():
    w = World()
    w.req({"on": True})
    code, out = w.req({"on": False})
    check("OFF: immediate, no second card",
          code == 200 and out["waiting"] is False and len(w.later) == 1, out)
    check("...and it is off", M._flag("uncensored_choices_offered") is False)
    w.run_card()
    check("...and approving the card that was waiting changes nothing",
          M._flag("uncensored_choices_offered") is False
          and M.state()["last"][M.ACTION_MODELS]["outcome"] == "withdrawn", M.state())
    w = World()
    w.req({"fiction": True})
    w.req({"fiction": False})
    w.run_card()
    check("the fiction lane withdraws the same way",
          M._flag("fiction_roleplay_on") is False
          and M.state()["last"][M.ACTION_FICTION]["outcome"] == "withdrawn", M.state())


def t_one_card_at_a_time_per_switch():
    w = World()
    w.req({"on": True})
    code, out = w.req({"on": True})
    check("a second ON while one waits: no second card",
          code == 202 and len(w.later) == 1 and "already waiting" in out["message"], out)
    code, out = w.req({"fiction": True})
    check("...but the OTHER switch is not blocked by it",
          code == 202 and len(w.later) == 2, (code, out))
    w.run_card()
    check("both cards applied, each to its own switch",
          M._flag("uncensored_choices_offered") is True
          and M._flag("fiction_roleplay_on") is True, M.state())


def t_turning_one_on_does_not_turn_the_other_on():
    w = World()
    w.req({"on": True})
    w.run_card()
    check("the uncensored list is on and the fiction lane is still off",
          M._flag("uncensored_choices_offered") is True
          and M._flag("fiction_roleplay_on") is False, M.state())


def t_bad_input():
    w = World()
    for bad in ({}, {"on": "yes"}, {"fiction": 1}, {"on": None}, {"on": True, "fiction": "x"}):
        code, out = w.req(bad)
        check(f"{bad!r} is refused", code == 400 and not w.later and not w.cards, out)
    code, out = M.request("not a body")
    check("a body that is not an object is refused", code == 400, out)


# ==========================================================================
#   3. The card's own words: what it does, and what it never does
# ==========================================================================

def t_the_card_text_names_the_real_rules():
    text = M.CARD_MODELS
    low = text.lower()
    check("says these are models already on this PC", "already on this pc" in low)
    check("says NOTHING IS DOWNLOADED, in those words", "nothing is downloaded" in low)
    check("says the weights are copied and need disk space", "copies" in low and "disk" in low)
    check("carries the measured cost, all of it",
          all(p in text for p in M.MEASURED_COST), text)
    check("says it is never the everyday assistant and never a default",
          "never your everyday assistant" in low and "default" in low)
    check("says choosing one is a separate decision with its own card",
          "separate decision" in low and "own card" in low)
    check("says off is instant", "instant" in low)
    check("says nothing leaves this PC", "nothing leaves this pc" in low)
    check("says what happens if you say no", "nothing about your models changes" in low)

    text = M.CARD_FICTION
    low = text.lower()
    check("fiction: says it is never the everyday assistant",
          "never your everyday assistant" in low)
    check("fiction: says nothing from a scene is saved or learned",
          "saved or learned" in low)
    check("fiction: says no tool is used from a scene", "no tool is used" in low)
    check("fiction: keeps the real-distress rule", "real distress" in low)
    check("fiction: says words inside the story cannot change the rules",
          "cannot change any of that" in low)
    check("fiction: says it runs on this PC and sends nothing anywhere",
          "runs on this pc" in low and "sends nothing anywhere" in low)
    check("fiction: says off is instant", "instant" in low)

    check("neither card text names a file the gate protects",
          "jarvis-" not in M.CARD_MODELS.lower() and "jarvis-" not in M.CARD_FICTION.lower(),
          "a card that names a protected filename is refused at tier never")


# ==========================================================================
#   4. The route: one path, origin and token first, everything else passed on
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


def t_the_route():
    fresh_config()

    class H(FakeHandler):
        pass
    line = M.install(H, origin_ok=lambda h: True, token_ok=lambda h: True,
                     read_body=lambda h: h.body)
    check("the banner line names the route", line.startswith("  optin"), line)
    check("the banner says both switches start off", "off by default" in line, line)

    h = H(M.PATH)
    H.do_GET(h)
    check("GET /api/models/uncensored is answered here",
          h.sent[0] == 200 and h.sent[1]["on"] is False
          and h.sent[1]["choices"] == [] and h.sent[1]["fiction"]["on"] is False,
          h.sent)
    check("...and it carries the measured cost and the never-a-default line",
          all(p in h.sent[1]["measured_cost"] for p in M.MEASURED_COST)
          and "never the everyday" in h.sent[1]["never_default"].lower(), h.sent[1])

    h = H("/api/models")
    H.do_GET(h)
    check("any other GET goes to the server's own handler", h.sent[0] == "original GET")
    h = H("/api/models/switch")
    H.do_POST(h)
    check("any other POST too", h.sent[0] == "original POST")

    h = H(M.PATH + "/?x=1")
    H.do_GET(h)
    check("a query string on the same path still reaches it", h.sent[0] == 200, h.sent)

    h = H(M.PATH, body=b"not json")
    H.do_POST(h)
    check("bad JSON body: 400", h.sent[0] == 400, h.sent)
    h = H(M.PATH, body=json.dumps({"nope": 1}).encode())
    H.do_POST(h)
    check("a body with neither switch named: 400", h.sent[0] == 400, h.sent)
    h = H(M.PATH, body=json.dumps({"on": False}).encode())
    H.do_POST(h)
    check("OFF through the route: 200, instant", h.sent[0] == 200 and h.sent[1]["waiting"] is False,
          h.sent)

    class Tok(FakeHandler):
        pass
    M.install(Tok, origin_ok=lambda h: True, token_ok=lambda h: False, read_body=lambda h: b"{}")
    h = Tok(M.PATH)
    Tok.do_POST(h)
    check("no token: 401, nothing done", h.sent[0] == 401, h.sent)

    class Origin(FakeHandler):
        pass
    M.install(Origin, origin_ok=lambda h: False, token_ok=lambda h: True, read_body=lambda h: b"{}")
    h = Origin(M.PATH)
    Origin.do_GET(h)
    check("another site's page is refused (403)", h.sent[0] == 403, h.sent)

    check("install twice wraps once", "already on" in M.install(
        H, origin_ok=lambda h: True, token_ok=lambda h: True, read_body=lambda h: b"{}"))


def t_the_route_reaches_the_card():
    """The route's POST must call the module's own request(), fakes and all -
    proved by handing request() its stand-ins through the module's own names,
    which is how the product resolves them."""
    fresh_config()
    cards, later = [], []

    class H(FakeHandler):
        pass
    M.install(H, origin_ok=lambda h: True, token_ok=lambda h: True, read_body=lambda h: h.body)

    class V2:
        tier, allowed, outcome, reason = "ask", True, "approved", "approved"
    real = (M._gate, M._tier, M._spawn)
    M._gate = lambda action, detail, prompt: (cards.append(action), V2())[1]
    M._tier = lambda action: "ask"
    M._spawn = later.append
    try:
        h = H(M.PATH, body=json.dumps({"on": True}).encode())
        H.do_POST(h)
        check("POST ON through the route: 202 waiting", h.sent[0] == 202
              and h.sent[1]["waiting"] is True, h.sent)
        check("...and it raised the card on the module's own thread",
              len(later) == 1, later)
        later[0]()
        check("...and approving it turned the choice on",
              M._flag("uncensored_choices_offered") is True and cards == [M.ACTION_MODELS],
              (cards, M.state()))
    finally:
        M._gate, M._tier, M._spawn = real
    check("the module's own names are back", M._spawn is real[2])


def t_rule_1_a_store_that_is_not_on_this_pc_is_refused():
    fresh_config()
    M.enable_uncensored_choices(True)      # ON, so the list WOULD be offered
    saved_present = "jarvis_models" in sys.modules
    saved = sys.modules.get("jarvis_models")
    remote = types.ModuleType("jarvis_models")
    remote.OLLAMA = "http://192.168.1.9:11434"
    sys.modules["jarvis_models"] = remote

    class H(FakeHandler):
        pass
    try:
        M.install(H, origin_ok=lambda h: True, token_ok=lambda h: True, read_body=lambda h: h.body)
        h = H(M.PATH)
        H.do_GET(h)
        check("a model store that is not on this PC: no list at all",
              h.sent[0] == 200 and h.sent[1]["choices"] == []
              and h.sent[1]["local_only"] is False, h.sent)
        check("...and the screen says why, in plain words",
              "not served from this PC" in h.sent[1]["off"], h.sent[1]["off"])
        h = H(M.PATH, body=json.dumps({"fiction": True}).encode())
        H.do_POST(h)
        check("...the fiction lane is refused too (503)",
              h.sent[0] == 503 and "not served from this PC" in h.sent[1]["error"], h.sent)
        code, out = M.request({"on": True}, gate=lambda *a: None, tier_of=lambda a: "ask",
                              spawn=lambda fn: None)
        check("...and an ON is refused BEFORE any card, so there is nothing to approve",
              code == 503 and "not served from this PC" in out["error"], (code, out))
        check("...nothing was turned on by any of that",
              M._flag("fiction_roleplay_on") is False, M.state())
    finally:
        if saved_present:
            sys.modules["jarvis_models"] = saved
        else:
            sys.modules.pop("jarvis_models", None)


# ==========================================================================
#   5. The wiring: the patch, the tier lines, and the gate's own tables
# ==========================================================================

def t_the_patch_wires_both_actions_into_the_gate():
    if not PATCH.is_file():
        check("backend/uncensored-optins.patch exists", False)
        return
    patch = PATCH.read_text(encoding="utf-8")
    added = [l for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++")]
    text = "\n".join(added)
    for action in (M.ACTION_MODELS, M.ACTION_FICTION):
        check(f"{action} joins the gate's \"acts only on tier ask\" set",
              f'    "{action}",  #' in text, text[:200])
        check(f"{action} gets a _RISK row",
              f'    "{action}": (' in text, text[:200])
    check("both _RISK rows are reversible and stay on this PC",
          text.count('("yes", "local"') == 2, text.count('("yes", "local"'))
    check("the patch touches jarvis_gate.py and jarvis_hud.py and nothing else",
          sorted(set(l[6:].strip() for l in patch.splitlines() if l.startswith("+++ b/")))
          == ["jarvis_gate.py", "jarvis_hud.py"],
          [l for l in patch.splitlines() if l.startswith("+++ b/")])


def t_the_shipped_settings_template_asks():
    if not TOML.is_file():
        check("backend/rebuilt/jarvis-framework.toml exists", False)
        return
    toml = TOML.read_text(encoding="utf-8")
    for action in (M.ACTION_MODELS, M.ACTION_FICTION):
        check(f'{action} is "ask" in the shipped settings template',
              bool(re.search(rf'^{action}\s*=\s*"ask"', toml, re.M)))
    check("...and that is the file apply-patches.ps1 merges the missing tier lines FROM",
          "$CONFIG_SRC  = 'rebuilt/jarvis-framework.toml'" in PS1.read_text(encoding="utf-8"),
          "the tier lines have to be in the file the script reads, or the owner's "
          "own file never learns them")
    check("...and a tier line the owner set themselves is never overwritten",
          "--only-missing" in (HERE / "_apply_toml_tiers.py").read_text(encoding="utf-8")
          or "only keys that are MISSING" in PS1.read_text(encoding="utf-8"))


def t_the_patch_stack_builds_the_wiring():
    """What the whole patch stack leaves, walked patch by patch - the check
    test_phone_notifications.py makes for its own patch, for the same reason:
    `jarvis_gate.py` is not in this repository, so the walk is the only thing
    in a checkout that can hold the wiring to account."""
    if not PATCH.is_file():
        return
    gate, _log = _stack.stand_in("jarvis_gate.py")
    if gate is None:
        return skip("the jarvis_gate.py stand-in could not be built (git is missing)")
    for action in (M.ACTION_MODELS, M.ACTION_FICTION):
        check(f"the patch stack's own jarvis_gate.py holds {action} in both tables",
              gate.count(f'"{action}"') == 2, gate.count(f'"{action}"'))
    hud, _log = _stack.stand_in("jarvis_hud.py")
    if hud is None:
        return skip("the jarvis_hud.py stand-in could not be built (git is missing)")
    check("the patch stack's own jarvis_hud.py installs the module",
          "jarvis_optin_models.install(Handler" in hud)
    check("...in front of the loader, which stays the last block before the socket is bound",
          hud.index("jarvis_optin_models.install(Handler")
          < hud.index("jarvis_plugins.install(Handler")
          < hud.index("_loopback_companion(bind, HUD_PORT, Handler)"))


def t_the_live_gate_knows_both_actions():
    """Only when the owner's own `jarvis_gate.py` is readable. It answers
    `_RISK` questions without raising a card, so it is safe to ask; a live
    copy from before `apply-patches.ps1` is next run is reported as such
    rather than counted as a pass."""
    try:
        import jarvis_gate as G
    except Exception as exc:
        return skip(f"jarvis_gate.py is not in this backend ({type(exc).__name__}); the "
                    f"patch text and the patch-stack walk above are what this checkout "
                    f"can prove")
    for action in (M.ACTION_MODELS, M.ACTION_FICTION):
        if action not in getattr(G, "_RISK", {}):
            skip(f"the live backend has not had uncensored-optins.patch applied yet, so "
                 f"{action} is not in its _RISK table")
            continue
        risk = G.risk_for(action)
        check(f"the real gate knows {action} and that it never leaves this PC",
              risk["classified"] is True and risk["reach"] == "local", risk)
        check(f"...and it is reversible in one tap, so a card is all it needs",
              risk["reversible"] == "yes", risk)
        check(f"...and nothing about it says it opens a way out",
              "outbound" not in json.dumps(risk), risk)


# ==========================================================================
#   6. Registered in apply-patches.ps1, last, and it applies and reverses
# ==========================================================================

def t_listed_and_applies():
    if not PATCH.is_file():
        return
    order = _stack.order()
    at = order.index("uncensored-optins.patch")
    loader = order.index("plugin-loader.patch")
    # POSITION, NOT ADJACENCY, and that is the honest reading of what actually
    # depends on where this patch sits.
    #
    # It must be in the list and in front of the loader, and the loader must be
    # last of all - all three are checked here or just below. It does NOT have
    # to be the loader's immediate predecessor: `gate-touches.patch` (PR #249,
    # merged 2026-10-11) sits in front of the loader too, and it writes NO
    # jarvis_hud.py line, so the loader's hunk still finds the lines THIS patch
    # printed. That is what the two checks below actually prove - the loader's
    # re-anchored text, and the stack built up to and including this patch -
    # and the whole-stack build in CI proves it end to end. Asserting adjacency
    # would be asserting a fact about the list's shape that nothing depends on,
    # and it would collide with the suite that pins the other patch's place.
    check("uncensored-optins.patch is in apply-patches.ps1's order, before the loader",
          at < loader, order[-3:])
    check("...so the loader stays LAST, which is the repository's own rule for it "
          "(everything after the loader must be a drop-in folder, never a core patch)",
          order[-1] == "plugin-loader.patch", order[-1])
    # The anchor moved twice, and this patch is not at fault either time: the
    # "ask for a picture" patch (pictures.patch, section 129) joined the install
    # CHAIN between this patch's block and the loader on 2026-10-11, and "Start
    # the local model" (model-lanes.patch, section 133) joined it after that
    # block on 2026-10-13 - so the loader's hunk now finds model-lanes.patch's
    # last two printed lines. Which patch it must anchor on is derived from the
    # patch text by tools/check_plugins.py, which fails if the two ever disagree
    # - so this check names the derived answer rather than losing its teeth: the
    # loader is anchored on the block it now follows, not invented from nothing.
    check("...and the loader's own hunk was re-anchored onto the block it now follows",
          "until jarvis_setup.py is back"
          in (HERE / "plugin-loader.patch").read_text(encoding="utf-8"),
          "setup.patch (2026-10-20, the setup questionnaire) is now the LAST "
          "block in the install chain before the loader; tools/check_plugins.py "
          "derives that anchor from the patch text, and fails if it drifts")
    check("a core patch in front of the loader is named in the plug-in catalogue",
          "uncensored-optins.patch" in (HERE.parent / "plugins" / "registry.json")
          .read_text(encoding="utf-8"))
    check("the module that does the work is shipped whole",
          "jarvis_optin_models.py" in _where.SHIPPED)
    check("...and the two published copies of it are one file, not two",
          (HERE / "jarvis_optin_models.py").read_bytes().replace(b"\r\n", b"\n")
          == (HERE.parent / "jarvis-backend" / "jarvis_optin_models.py")
          .read_bytes().replace(b"\r\n", b"\n"))

    git = shutil.which("git")
    if not git:
        return skip("git is not installed")
    for target in ("jarvis_gate.py", "jarvis_hud.py"):
        text, log = _stack.stand_in(target, order[:at])
        check(f"{target}: the stack before uncensored-optins.patch builds", text is not None,
              "\n".join(log))
        if text is None:
            continue
        d = Path(tempfile.mkdtemp(prefix="jarvis-optin-patch-"))
        try:
            (d / target).write_text(text, encoding="utf-8", newline="\n")
            one = "".join(h for h, _ in _stack.hunks(PATCH.read_text(encoding="utf-8"), target))
            (d / "p.patch").write_text(f"--- a/{target}\n+++ b/{target}\n{one}",
                                       encoding="utf-8", newline="\n")
            for extra in (["--check"], [], ["--check", "--reverse"], ["--reverse"], []):
                r = subprocess.run([git, "apply", *extra, "p.patch"], cwd=d,
                                   capture_output=True, text=True)
                check(f"git apply {' '.join(extra) or '(forwards)'} "
                      f"uncensored-optins.patch ({target})", r.returncode == 0, r.stderr.strip())
            full = _stack.stand_in(target, order[:at + 1])[0]
            got = (d / target).read_text(encoding="utf-8").replace("\r\n", "\n")
            check(f"forwards gives the stack's own text ({target})", got == full)
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
    if SKIPPED:
        print("Skipped (not failures):")
        for s in SKIPPED:
            print("  - " + s)
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
