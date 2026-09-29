"""test_lockdown.py - Lockdown: one tap makes every way out of this PC ask
first, or stop (jarvis_asks_first.py; the owner's choice of the research
audit's idea 10, 2026-09-28).

    python3 backend/test_lockdown.py

Runs anywhere; no model, no network, no Windows Hello (each is faked). What
it proves:

1. The setting: no file is off; a file that cannot be read, or says
   anything but true/false, is ON (fails closed).
2. It bites through the tier table: while it is on, every way out whose
   line says "auto" or "notify" is "ask" in jarvis_framework.action_tier -
   so the gate asks, and whatever runs by itself stops - while the file's
   own line (file_action_tier) is untouched. "never" stays "never"; nothing
   else changes.
3. ON is at once, from any device, with no card, and rings the "lockdown"
   doorbell; OFF is the PC only, needs the backend's own Windows Hello
   check, and is ONE card of the existing loosening action - only a
   person's "approved" turns it off; denied, timed out, or ON pressed again
   while the card waits leaves it on.
4. While it is on: nothing can be loosened, the lights setting cannot be
   turned on, and "Lights, plugs and fans without a card" does not apply;
   "What asks first" says so on each row it changed.
5. The ways out the tier table cannot reach: no cloud AI model (the
   router's gate "lockdown", no offer), every web search asks, a "tell me
   when" does not look, a plug-in program asks at every start, and
   checking for tool updates asks again.
6. The fast path: "lockdown" turns it on at once; "turn off lockdown" from
   the phone says where to do it; "is lockdown on?" says.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_asks_first.py", "jarvis_agent.py", "jarvis_quick.py",
                "jarvis_tellme.py", "jarvis_mcp.py", "jarvis_tool_updates.py")
TMP = Path(tempfile.mkdtemp(prefix="jarvis-lockdown-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_SCHEDULE_DB"] = str(TMP / "schedule.db")
TOML = TMP / "jarvis-framework.toml"
TOML.write_text(
    "[autonomy]\nunknown_action_tier = \"ask\"\n\n[autonomy.tiers]\n"
    "web_research = \"auto\"\ncalendar_read = \"auto\"\nnews_read = \"notify\"\n"
    "post_to_external_service = \"never\"\nrollback_model = \"auto\"\n"
    "append_obsidian_daily = \"auto\"\nloosen_what_asks_first = \"ask\"\n"
    "change_own_config = \"ask\"\n", encoding="utf-8")
os.environ["JARVIS_FRAMEWORK_TOML"] = str(TOML)
sys.path.append(str(HERE / "rebuilt"))
import jarvis_framework as fw  # noqa: E402
import jarvis_asks_first as AF  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_router as R  # noqa: E402

AF._config_dir = lambda: TMP
PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Verdict:
    def __init__(self, allowed, tier, outcome):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.reason, self.action, self.request_id = outcome, "x", None


def off():
    AF._reset_for_tests()
    try:
        AF.lockdown_path().unlink()
    except FileNotFoundError:
        pass
    AF.set_lights(False)


def on():
    AF.set_lockdown(True)


# ======================================================== 1. the setting

def t_the_setting_fails_closed():
    off()
    check("no file: off", AF.lockdown_on() is False)
    AF.lockdown_path().write_text("not json", encoding="utf-8")
    st = AF.lockdown_setting()
    check("a damaged file: ON, and says why", st["on"] is True and "could not be read" in st["why"])
    AF.lockdown_path().write_text(json.dumps({"on": "yes"}), encoding="utf-8")
    check("anything but true/false: ON", AF.lockdown_on() is True)
    AF.set_lockdown(False)
    check("written off: off", AF.lockdown_on() is False)
    AF.set_lockdown(True)
    check("written on: on (the cache follows the file)", AF.lockdown_on() is True)
    off()


# ======================================================== 2. the tier table

def t_it_bites_through_the_tier_table():
    off()
    fw.reload_framework()
    check("off: the file's own tier", fw.action_tier("web_research") == "auto"
          and fw.action_tier("news_read") == "notify")
    on()
    check("on: a way out on 'auto' asks", fw.action_tier("web_research") == "ask")
    check("on: a way out on 'notify' asks", fw.action_tier("news_read") == "ask")
    check("on: calendar reads ask (so the briefing leaves the calendar out)",
          fw.action_tier("calendar_read") == "ask")
    check("on: 'never' stays never", fw.action_tier("post_to_external_service") == "never")
    check("on: something that stays on this PC is untouched",
          fw.action_tier("rollback_model") == "auto" and fw.action_tier("append_obsidian_daily") == "auto")
    check("on: a plug-in program's tool is a way out", AF.lockdown_tier("mcp__x__y", "auto") == "ask")
    check("the file itself is untouched", fw.file_action_tier("web_research") == "auto"
          and "web_research = \"auto\"" in TOML.read_text(encoding="utf-8"))
    check("only ever stricter", all(AF.lockdown_tier(a, "ask") == "ask"
                                    for a in AF.LOCKDOWN_ACTIONS))
    check("no way out is something the owner may loosen from an app... except the reads",
          set(AF.LOCKDOWN_ACTIONS) & set(AF.SWITCHABLE) ==
          {"calendar_read", "email_read", "home_read"})
    off()


# ======================================================== 3. on and off

def t_on_at_once_off_one_card_on_the_pc():
    off()
    rang = []
    import jarvis_events_stub  # noqa: F401  (see below)
    jarvis_events_stub.EVENTS.clear()
    code, out = AF.request_tier({"action": "lockdown", "ask": True}, here=False)
    check("ON from the phone: at once, no card", code == 200 and out["changed"] is True
          and AF.lockdown_on(), str(out))
    check("... rings the lockdown doorbell, with nothing but on/off",
          jarvis_events_stub.EVENTS == [("lockdown", {"on": True})], str(jarvis_events_stub.EVENTS))
    code, out = AF.request_tier({"action": "lockdown", "ask": False}, here=False)
    check("OFF from the phone: refused, the PC only", code == 403 and out.get("pc_only") is True
          and out["error"] == AF.LOCKDOWN_PC_ONLY)
    code, out = AF.request_lockdown(False, here=True, armed=lambda: False)
    check("OFF without the backend's own Windows Hello check: refused", code == 503)
    spawned = []
    asked = []

    def gate(action, detail, prompt):
        asked.append((action, detail))
        return Verdict(False, "ask", "denied")
    code, out = AF.request_lockdown(False, here=True, armed=lambda: True, gate=gate,
                                    tier_of=lambda a: "ask", spawn=spawned.append)
    check("OFF from the PC: ONE card, waiting", code == 202 and out["waiting"] is True
          and len(spawned) == 1)
    code2, out2 = AF.request_lockdown(False, here=True, armed=lambda: True, gate=gate,
                                      tier_of=lambda a: "ask", spawn=spawned.append)
    check("one card at a time", code2 == 409)
    spawned[0]()
    check("the card is the existing loosening action (Windows Hello, the PC only)",
          asked and asked[0][0] == AF.LOOSEN_ACTION == "loosen_what_asks_first"
          and "Turn off Lockdown?" in asked[0][1]["text"])
    check("denied: still on", AF.lockdown_on() is True
          and AF.lockdown_status()["last"]["outcome"] == "denied")
    spawned.clear()
    AF.request_lockdown(False, here=True, armed=lambda: True, tier_of=lambda a: "ask",
                        gate=lambda a, d, p: Verdict(True, "ask", "approved"),
                        spawn=spawned.append)
    AF.request_tier({"action": "lockdown", "ask": True}, here=True)
    spawned[0]()
    check("ON pressed while the card waited: approving it changes nothing",
          AF.lockdown_on() is True and AF.lockdown_status()["last"]["outcome"] == "withdrawn")
    spawned.clear()
    AF.request_lockdown(False, here=True, armed=lambda: True, tier_of=lambda a: "ask",
                        gate=lambda a, d, p: Verdict(True, "auto", "auto"),
                        spawn=spawned.append)
    spawned[0]()
    check("a yes with nobody asked (tier auto) is not a person: still on",
          AF.lockdown_on() is True and AF.lockdown_status()["last"]["outcome"] == "refused")
    spawned.clear()
    jarvis_events_stub.EVENTS.clear()
    AF.request_lockdown(False, here=True, armed=lambda: True, tier_of=lambda a: "ask",
                        gate=lambda a, d, p: Verdict(True, "ask", "approved"),
                        spawn=spawned.append)
    spawned[0]()
    check("a person's 'approved': off", AF.lockdown_on() is False
          and AF.lockdown_status()["last"]["outcome"] == "off")
    check("... and the doorbell says so", jarvis_events_stub.EVENTS == [("lockdown", {"on": False})])
    code, out = AF.request_lockdown(False, here=True)
    check("off already: said, no card", code == 200 and out["changed"] is False)
    check("a bad body is refused", AF.request_tier({"action": "lockdown", "ask": "yes"})[0] == 400)
    off()


# ======================================================== 4. while it is on

def t_while_on_nothing_loosens():
    off()
    on()
    code, out = AF.request_tier({"action": "calendar_read", "ask": False}, here=True)
    check("loosening is refused", code == 409 and out["error"] == AF.LOCKDOWN_NO_LOOSEN)
    code, out = AF.request_lights(True)
    check("the lights setting cannot be turned on", code == 409)
    AF.set_lights(True)
    check("'lights without a card' does not apply",
          AF.lights_without_card(object(), "turn off the kitchen light", shaped="")
          == "Lockdown is on")
    AF.set_lights(False)
    AF._tier = lambda a: fw.action_tier(a)
    AF._file_tiers = lambda: fw.all_tiers()
    v = AF.view(here=True)
    rows = {r["id"]: r for g in v["groups"] for r in g["rows"]}
    cal = rows["calendar_read"]
    check("the page says Lockdown on each row it changed",
          cal.get("lockdown") is True and AF.LOCKDOWN_ROW_NOTE in cal["note"]
          and cal["says"] == AF.SAYS["ask"], json.dumps(cal))
    check("... and offers no loosening, even on the PC",
          cal["switch"]["can_loosen"] is False)
    check("a row Lockdown did not change says nothing of it",
          "lockdown" not in rows["append_obsidian_daily"])
    check("the page carries Lockdown itself",
          v["lockdown"]["on"] is True and v["lockdown"]["can_turn_off"] is True
          and v["lockdown"]["says"] == AF.LOCKDOWN_ON_SAYS)
    check("from the phone it cannot be turned off",
          AF.view(here=False)["lockdown"]["can_turn_off"] is False)
    code, out = AF.request_tier({"action": "append_obsidian_daily", "ask": True}, here=False,
                                write=lambda a, t: None)
    check("making something stricter still works", code == 200 and out["ok"] is True)
    off()


# ======================================================== 5. the rest

def t_the_ways_out_the_table_cannot_reach():
    off()
    d = R.choose("please write a long detailed essay comparing three economic theories in "
                 "depth with many examples and citations", local_model="jarvis-primary",
                 lanes=["cloud-big"], owner_said_yes=True)
    check("off: Lockdown is not the reason (the other gates decide, as before)",
          d.gate != "lockdown", d.gate)
    on()
    d = R.choose("please write a long detailed essay comparing three economic theories in "
                 "depth with many examples and citations", local_model="jarvis-primary",
                 lanes=["cloud-big"], owner_said_yes=True)
    check("on: no cloud AI model, and none offered", d.gate == "lockdown"
          and d.lane == "jarvis-primary" and not getattr(d, "offer", None), d.gate)

    class Watch:
        read, tainted, memory, facts, provenance, app_context = {}, False, False, [], None, False
        owner_words = ""
    lines = AG.web_search_card_lines(Watch(), False, "kokoro voices")
    check("every web search asks", AG.WEB_SEARCH_LOCKDOWN in lines, str(lines))
    import jarvis_tellme as TM
    check("a 'tell me when' does not look", TM.readiness("page") == TM.LOCKDOWN_WORDS
          and TM.readiness("search") == TM.LOCKDOWN_WORDS)
    import jarvis_mcp as MCP
    check("a plug-in program asks at every start", MCP.card_every_start() is True)
    import jarvis_tool_updates as TU
    real = TU.approved
    TU.approved = lambda: True
    spawned = []
    try:
        code, out = TU.request_check(gate=lambda *a: None, tier_of=lambda a: "ask",
                                     spawn=spawned.append, write=lambda: None,
                                     run=lambda: {})
    finally:
        TU.approved = real
    check("checking for tool updates asks again", code == 202 and out.get("waiting") is True,
          str(out))
    off()
    check("off: plug-in programs back to the owner's setting",
          MCP.card_every_start() is bool(MCP.CARD_EVERY_START))
    lines = AG.web_search_card_lines(Watch(), False, "kokoro voices")
    check("off: a search from the owner's own question runs without a card", lines == [])


def t_turning_it_on_stops_what_is_already_talking():
    """Security audit 2026-09-28 #2: ON ends a running chatbot conversation
    or comparison at once (each module's stop_for_lockdown), and the words
    and the card name chatbots and the online weather."""
    off()
    called = []
    saved = {n: sys.modules.get(n) for n in AF.LOCKDOWN_STOPPERS}
    try:
        for n in AF.LOCKDOWN_STOPPERS:
            m = type(sys)(n)
            m.stop_for_lockdown = (lambda n=n: called.append(n) or f"{n} stopped")
            sys.modules[n] = m
        boom = type(sys)("jarvis_chatbot")
        code, out = AF.request_lockdown(True, here=True)
        check("ON calls every stopper once", sorted(called) == sorted(AF.LOCKDOWN_STOPPERS)
              and code == 200, called)
        off()
        called.clear()

        def raises():
            raise RuntimeError("broken")
        boom.stop_for_lockdown = raises
        sys.modules["jarvis_chatbot"] = boom
        code, out = AF.request_lockdown(True, here=True)
        check("a stopper that raises does not stop Lockdown coming on",
              code == 200 and AF.lockdown_on() and "jarvis_chatbot_compare" in called, called)
        off()
        called.clear()
        for n in AF.LOCKDOWN_STOPPERS:
            sys.modules.pop(n, None)
        code, out = AF.request_lockdown(True, here=True)
        check("nothing loaded: nothing imported just to stop it",
              code == 200 and not any(n in sys.modules for n in AF.LOCKDOWN_STOPPERS))
    finally:
        for n, m in saved.items():
            if m is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = m
        off()
    check("the words name chatbots and the online weather",
          "chatbot" in AF.LOCKDOWN_DETAIL and "weather" in AF.LOCKDOWN_DETAIL
          and "chatbot" in AF.LOCKDOWN_ON_SAYS and "weather" in AF.LOCKDOWN_CARD)


# ======================================================== 6. the fast path

def t_the_fast_path():
    off()
    res = Q.answer("lockdown")
    check("'lockdown' turns it on at once", res is not None and AF.lockdown_on()
          and res.reply == AF.LOCKDOWN_DONE, res and res.reply)
    res = Q.answer("is lockdown on")
    check("'is lockdown on?' says", res is not None and res.reply == AF.LOCKDOWN_ON_SAYS)
    AF._from_this_pc = lambda peer, local: False
    res = Q.answer("turn off lockdown", peer="100.64.0.2", local="100.64.0.1")
    check("'turn off lockdown' from the phone: where to do it", res is not None
          and AF.lockdown_on() and res.reply == AF.LOCKDOWN_PC_ONLY, res and res.reply)
    off()


# A stand-in for the event bus: rebuilt/jarvis_events is heavy to start, and
# this proves only WHAT is published.
class _Bus:
    def publish(self, kind, data):
        EVENTS.append((kind, dict(data)))


EVENTS: list = []
stub = type(sys)("jarvis_events_stub")
stub.EVENTS = EVENTS
sys.modules["jarvis_events_stub"] = stub
events_mod = type(sys)("jarvis_events")
events_mod.BUS = _Bus()
sys.modules["jarvis_events"] = events_mod


if __name__ == "__main__":
    for fn in (t_the_setting_fails_closed, t_it_bites_through_the_tier_table,
               t_on_at_once_off_one_card_on_the_pc, t_while_on_nothing_loosens,
               t_the_ways_out_the_table_cannot_reach,
               t_turning_it_on_stops_what_is_already_talking, t_the_fast_path):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    off()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
