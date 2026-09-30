"""test_settings_switches.py - the two settings-audit fixes of 2026-09-30.

    python3 backend/test_settings_switches.py

1. The reading-tool switches (jarvis_asks_first.TOOLS_SWITCHABLE). The page
   lists four rows by their GATE ACTION names; [tools].enabled holds the
   model's TOOL names. For the email row the two differ ("email_read" vs
   "email_check"), so switching email on wrote a name the model was never
   offered: the page said On, jarvis_reach said Off, and the tool was not
   there. Proven here end to end - through the real route, a real settings
   file and the real loader - for EVERY row, plus an old file that already
   holds the wrong name.
2. The web search on/off switch: OFF is immediate, ON is one approval card,
   and "off" is read at use time (the tool is not offered, every path that
   plans a search refuses in plain words).

No network, no model, no Windows.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-switches-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
(_TMP / "config").mkdir(parents=True, exist_ok=True)
_TOML = _TMP / "jarvis-framework.toml"
os.environ["JARVIS_FRAMEWORK_TOML"] = str(_TOML)

sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_asks_first.py", "jarvis_agent.py", "jarvis_reach.py",
                "jarvis_search.py", "jarvis_settings_registry.py", "jarvis_quick.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_framework as FW  # noqa: E402
import jarvis_asks_first as AF  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import jarvis_reach as R  # noqa: E402
import jarvis_search as WS  # noqa: E402
import jarvis_settings_registry as REG  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import _stack  # noqa: E402

AF._config_dir = lambda: _TMP / "config"
WS._config_dir = lambda: _TMP / "config"

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Verdict:
    def __init__(self, allowed, tier, outcome):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.reason, self.action, self.request_id = outcome, "x", None


def approve(a, d, p):
    return Verdict(True, "ask", "approved")


def deny(a, d, p):
    return Verdict(False, "ask", "denied")


def ask_tier(a):
    return "ask"


def write_toml(enabled):
    items = ", ".join(f'"{x}"' for x in enabled)
    _TOML.write_text('[autonomy.tiers]\nenable_reading_tool = "ask"\n\n'
                     f'[tools]\nenabled = [{items}]\n', encoding="utf-8")
    FW.reload_framework()


def enabled_in_file():
    return set(FW.load_framework().get("tools", {}).get("enabled") or [])


def route(tool, on):
    """POST /api/asks_first/tools, as the PC, with the card approved at once."""
    AF._reset_for_tests()
    return AF.request_tool_enable(
        {"tool": tool, "enabled": on}, here=True, tier_of=ask_tier, gate=approve,
        spawn=lambda fn: fn(), armed=lambda: True)


def reach_rows(enabled):
    env = {"JARVIS_IMAP_HOST": "imap.example.com", "JARVIS_IMAP_USER": "me@example.com",
           "JARVIS_IMAP_PASSWORD": "x" * 12, "JARVIS_HOME_URL": "http://192.168.1.5:8123"}
    ctx = R.Ctx(enabled=set(enabled), env=lambda k: env.get(k, ""), tier=lambda a: "auto",
                lanes=[], providers=[], key_saved=lambda p: None,
                second_card={"master": False, "features": {}}, big_model={"master": False},
                gate_action=lambda lookup: None)
    return {r["id"]: r for r in R.view(ctx)["rows"]}


# ======================================================== 1. the reading-tool switches

#: The reach row each switchable tool feeds (None: its row needs setup this
#: test does not fake - the tool-name mapping is still proven for it).
ROW_OF = {"email_check": "email_read", "home_read": "home_read"}


def t_every_switch_writes_the_tool_the_model_is_offered():
    check("four rows, in the page's order", AF.TOOLS_SWITCHABLE ==
          ("calendar_read", "email_read", "notes_search", "home_read"))
    for action in AF.TOOLS_SWITCHABLE:
        real = AF.TOOL_NAME[action]
        check(f"{action}: the tool it switches ({real}) is a real tool in jarvis_agent.TOOLS",
              real in AG.TOOLS, sorted(AG.TOOLS)[:8])
        write_toml(["calculator"])
        code, out = route(action, True)
        check(f"{action}: ON through the real route writes the settings file",
              code == 202 or code == 200, (code, out))
        got = enabled_in_file()
        check(f"{action}: the file now lists {real} (and never the action's own name if that differs)",
              real in got and (action == real or action not in got), got)
        check(f"{action}: the model is offered it (jarvis_agent.offered_tools)",
              real in AG.offered_tools(got), AG.offered_tools(got))
        st = AF.tools_status(here=True)
        item = next(i for i in st["items"] if i["id"] == action)
        check(f"{action}: the page says On", item["on"] is True, item)
        check(f"{action}: jarvis_reach knows it can be switched on from an app",
              R._tool_switchable(real) is True)
        code, out = route(action, False)
        got = enabled_in_file()
        check(f"{action}: OFF is instant and removes it",
              code == 200 and real not in got and "calculator" in got, (code, got))
        check(f"{action}: ... and the model is no longer offered it",
              real not in AG.offered_tools(got))


def t_the_page_and_reach_agree_for_email():
    write_toml(["calculator"])
    route("email_read", True)
    rows = reach_rows(R._tools_enabled())
    check("reach lists an email (reading) row", "email_read" in rows, list(rows)[:6])
    row = rows.get("email_read", {})
    check("after switching email on from the page, reach says On", row.get("state") == "on", row)
    st = AF.tools_status(here=True)
    check("... and the page says On too",
          next(i for i in st["items"] if i["id"] == "email_read")["on"] is True)
    route("email_read", False)
    rows = reach_rows(R._tools_enabled())
    row = rows.get("email_read", {})
    check("after switching it off, reach says Off, in words that name the app switch "
          "(not 'file-only')", row.get("state") == "off" and "file-only" not in row.get("line", "")
          and "What asks first" in row.get("line", ""), row)


def t_an_old_file_with_the_wrong_name_keeps_working():
    write_toml(["calculator", "email_read"])
    got = AF.tools_enabled_set()
    check("the old entry counts as the email tool", "email_check" in got, got)
    check("the model is offered the email tool", "email_check" in AG.offered_tools(enabled_in_file()))
    rows = reach_rows(R._tools_enabled())
    check("reach says On for it", rows.get("email_read", {}).get("state") == "on",
          rows.get("email_read"))
    code, out = route("email_read", False)
    check("switching it off removes the old entry too", code == 200
          and "email_read" not in enabled_in_file() and "email_check" not in enabled_in_file(),
          enabled_in_file())
    write_toml(["email_read", "calculator"])
    route("email_read", True)  # already on: nothing to do
    write_toml(["email_read"])
    AF.set_tools_enabled("email_check", False)
    FW.reload_framework()
    check("switching the real name off also clears the old entry",
          not enabled_in_file() & {"email_read", "email_check"}, enabled_in_file())


def t_the_card_names_the_real_line():
    text = AF.tool_enable_card("email_read")
    check("the card says which line is added (email_check)", '"email_check" is added' in text, text)
    check("... and still calls it reading your email", "read your email" in text.lower(), text)


# ======================================================== 2. the web search switch

def fresh_search():
    WS.settings_path().parent.mkdir(parents=True, exist_ok=True)
    if WS.settings_path().exists():
        WS.settings_path().unlink()
    WS._reset_for_tests()


def t_web_search_ships_on_and_off_is_instant():
    fresh_search()
    check("no file: web search is on", WS.settings()["enabled"] is True)
    code, out = WS.handle_settings({"enabled": False})
    check("OFF: 200, at once, no card", code == 200 and out["ok"] and out["enabled"] is False
          and out["enable_waiting"] is False, (code, out.get("said")))
    check("... written to the file, other choices kept", WS.settings()["enabled"] is False
          and WS.settings()["provider"] == "searxng")
    code, out = WS.handle_settings({"enabled": False})
    check("OFF again: 'already off'", code == 200 and "already off" in out["said"])
    code, out = WS.handle_settings({"enabled": "no"})
    check("a non-boolean is refused", code == 400)
    code, out = WS.handle_settings({"enabled": False, "provider": "duckduckgo"})
    check("two changes in one request are refused", code == 400)


def t_off_is_read_at_use_time():
    fresh_search()
    WS.handle_settings({"enabled": False})
    p = WS.plan("weather in Paris")
    check("plan(): refused with the plain 'turned off' words", p.state == "turned_off"
          and "switched off" in p.problem and "Settings" in p.problem, p.as_dict())
    out = WS.run(p, approved=True)
    check("run(): nothing is sent, same words", out["ok"] is False and out["state"] == "turned_off"
          and out["error"] == WS.OFF_SAID, out)
    check("... and what the model reads tells it not to search another way",
          "tell_the_owner" in WS.tool_result(out))
    # A plan made while ON, run after it was switched off, is stopped too.
    fresh_search()
    live = WS.plan("weather in Paris")
    WS.handle_settings({"enabled": False})
    out = WS.run(live, approved=True)
    check("a plan made while on is refused if it is switched off before it runs",
          out["ok"] is False and out["state"] == "turned_off", out)
    check("the model is not offered web_search while it is off",
          "web_search" not in AG.offered_tools(["web_search", "calculator"]))
    fresh_search()
    check("... and is offered it again while on",
          "web_search" in AG.offered_tools(["web_search", "calculator"]))


def t_a_damaged_switch_fails_closed():
    fresh_search()
    WS.settings_path().write_text(json.dumps({"provider": "searxng", "enabled": "yes"}))
    s = WS.settings()
    check("a switch that is not true/false counts as off", s["enabled"] is False and s["why"], s)
    check("... so nothing is searched", WS.plan("hello").problem != "")
    fresh_search()


def t_turning_it_back_on_is_one_card():
    fresh_search()
    WS.handle_settings({"enabled": False})
    asked = []

    def gate(a, d, p):
        asked.append((a, d, p))
        return Verdict(True, "ask", "approved")

    code, out = WS.request_enabled(True, gate=gate, tier_of=ask_tier, spawn=lambda fn: fn())
    check("ON: 202 and exactly ONE card, web_search_enable", code == 202
          and [a for a, _, _ in asked] == ["web_search_enable"], (code, asked))
    check("the card says what it changes and that nothing is searched by it",
          "Turn web search back on?" in asked[0][2] and "Nothing is searched" in asked[0][2]
          and "If you say no" in asked[0][2])
    check("approved by a person: it is on again", WS.settings()["enabled"] is True)
    check("... and the page says so", WS.view()["enable_last"]["outcome"] == "changed")
    for verdict, name in ((Verdict(False, "ask", "denied"), "denied"),
                          (Verdict(False, "ask", "timed_out"), "timed out"),
                          (Verdict(True, "auto", "auto"), "allowed at auto - nobody asked")):
        fresh_search()
        WS.handle_settings({"enabled": False})
        WS.request_enabled(True, gate=lambda a, d, p, v=verdict: v, tier_of=ask_tier,
                           spawn=lambda fn: fn())
        check(f"{name}: stays off", WS.settings()["enabled"] is False)
    fresh_search()
    WS.handle_settings({"enabled": False})
    code, out = WS.request_enabled(True, gate=approve, tier_of=lambda a: "auto",
                                   spawn=lambda fn: fn())
    check("the card's own tier not 'ask': 503, stays off",
          code == 503 and WS.settings()["enabled"] is False)
    code, out = WS.request_enabled(True, gate=approve, tier_of=ask_tier,
                                   spawn=lambda fn: fn())
    check("already on: nothing asked", WS.settings()["enabled"] is True)
    code, out = WS.request_enabled(True, gate=lambda *a: (_ for _ in ()).throw(AssertionError("card")),
                                   tier_of=ask_tier, spawn=lambda fn: fn())
    check("ON while on: 200, no card", code == 200 and "already on" in out["said"])
    # Switching off while the card waits withdraws it.
    fresh_search()
    WS.handle_settings({"enabled": False})
    held = []
    WS.request_enabled(True, gate=approve, tier_of=ask_tier, spawn=held.append)
    check("the page shows the card waiting", WS.view()["enable_waiting"] is True)
    WS.request_enabled(False)
    held[0]()
    check("off while the card waited: approving it later changes nothing",
          WS.settings()["enabled"] is False
          and WS.view()["enable_last"]["outcome"] == "withdrawn", WS.view()["enable_last"])
    fresh_search()


def t_the_view_and_reach_say_it_plainly():
    fresh_search()
    v = WS.view()
    check("the view carries the switch and its words",
          v["enabled"] is True and v["enabled_label"] == "Web search"
          and "approval card" in v["enabled_detail"])
    WS.handle_settings({"enabled": False})
    rows = {r["id"]: r for r in R.view(R.Ctx(enabled={"web_search"}))["rows"]}
    row = rows["web_search"]
    check("reach: Off, and says how to turn it back on", row["state"] == "off"
          and "Settings, Web search" in row["line"] and "card" in row["line"], row)
    fresh_search()
    rows = {r["id"]: r for r in R.view(R.Ctx(enabled=set()))["rows"]}
    line = rows["web_search"]["line"]
    check("reach: missing from the settings file's list says so in plain words, no 'add ... by hand'",
          rows["web_search"]["state"] == "off" and "settings file on your PC" in line
          and "by hand" not in line, line)


def t_the_second_door_by_voice_or_chat():
    fresh_search()
    i = Q.match("turn off web search")
    check("'turn off web search' is the registry's web_search setting",
          i is not None and i.name == "settings_bool" and i.f == {"key": "web_search", "on": False}, i)
    i = Q.match("turn on web search")
    check("'turn on web search' too", i is not None and i.f == {"key": "web_search", "on": True}, i)
    out = REG.set_web_search(False)
    check("registry OFF: at once", out.ok and WS.settings()["enabled"] is False, out)
    out = REG.set_web_search(True)
    check("registry ON: never a silent flip - a card (or a refusal in this bare test), "
          "and still off until a person approves", WS.settings()["enabled"] is False, out)
    WS._reset_for_tests()
    fresh_search()


def t_open_devices_crash_notes_and_look_at_this():
    for phrase, sid in (("open devices", "devices"), ("open paired devices", "devices"),
                        ("open crash notes", "crash-notes"),
                        ("open look at this", "screen-look"),
                        ("open quick tiles", "quick-tiles")):
        i = Q.match(phrase)
        check(f"{phrase!r} opens {sid}", i is not None and i.name == "settings_open"
              and i.f == {"id": sid}, i)


def t_the_gate_lines_and_the_tables():
    text, log = _stack.stand_in("jarvis_gate.py")
    check("the whole patch stack builds jarvis_gate.py", text is not None, "\n".join(log[-3:]))
    if text is None:
        return
    check("web-search-switch.patch applied to real context (nothing materialised)",
          not any(l.startswith("web-search-switch.patch") for l in log), log[-3:])
    check("the action has its own risk line, local and undoable",
          '"web_search_enable": ("yes", "local",' in text)
    check("... and is in the 'a no is not a standing rule' list exactly once",
          text.count('"web_search_enable",  # jarvis_search.py acts only on tier "ask"') == 1)
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("the shipped settings file keeps it at tier ask",
          'web_search_enable                         = "ask"' in toml)
    check("it is a hard limit and must-ask in the What asks first tables",
          "web_search_enable" in AF.HARD_LIMITS and "web_search_enable" in AF.MUST_ASK)
    import jarvis_card_words as W
    check("its card has a title in plain words", "turn web search back on" in
          W.title_for("web_search_enable").lower(), W.title_for("web_search_enable"))


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("t_") and callable(v)]
    for t in tests:
        print(f"--- {t.__name__} ---")
        try:
            t()
        except Exception as exc:  # a crash is a failure, with its trace
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} ran to the end", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFAILED:")
        for f in FAILED:
            print(f"  {f}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
