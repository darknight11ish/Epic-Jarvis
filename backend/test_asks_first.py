"""test_asks_first.py - "What asks first" and "Lights, plugs and fans without
a card" (jarvis_asks_first.py, asks-first.patch; the owner's decisions of
2026-09-26, after the approvals audit).

    python3 backend/test_asks_first.py

Runs anywhere; no Home Assistant, no model and no network. What it proves:

1. The page lists every action an approval card can name
   (jarvis_card_words.TITLES), grouped, with its tier in plain words, and
   says which ones always ask.
2. The short safe list never meets NEEDS_A_PERSON's actions, the hard
   limits, or the actions whose module accepts only "ask" - and the wiki is
   not on it (it is written only on a person's yes).
3. Writing the settings file changes ONE line - or adds one - and keeps
   every other byte (comments, CRLF line endings, a byte-order mark). An
   unusual file is refused, and nothing is written.
4. Stricter is immediate from anywhere; looser is refused from another
   device, off the list, without the backend's Windows Hello check, or when
   the card's own tier is not "ask" - and otherwise waits for ONE card, and
   only a person's "approved" writes the line.
5. jarvis_owner_check: a loosening card is approved on this PC only, and
   always with Windows Hello.
6. The lights setting: off by default, ON through one card, OFF at once.
7. The chat loop: with the setting on, named lights in a clean turn run
   with no card; a lock, a garage "switch", an unnamed device, or a turn
   after outside text still gets its card.
8. The patch: applies after focus.patch, reverses, and touches only
   jarvis_hud.py and jarvis_gate.py; the module is shipped.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_asks_first.py", "jarvis_home.py", "jarvis_agent.py",
                "jarvis_owner_check.py", "jarvis_card_words.py", "jarvis_local_http.py")
sys.path.append(str(HERE / "rebuilt"))
import _stack  # noqa: E402
import jarvis_asks_first as AF  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import jarvis_card_words as W  # noqa: E402
import jarvis_home as H  # noqa: E402
import jarvis_owner_check as OC  # noqa: E402

FAILED, PASSED = [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-asks-first-"))
AF._config_dir = lambda: TMP


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Verdict:
    def __init__(self, allowed, tier, outcome):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.reason, self.action, self.request_id = outcome, "x", None


SAMPLE = (
    "# my settings\r\n"
    "[autonomy]\r\n"
    "unknown_action_tier = \"ask\"\r\n"
    "\r\n"
    "[autonomy.tiers]\r\n"
    "web_research              = \"auto\"\r\n"
    "calendar_read             = \"auto\"   # I like this one\r\n"
    "email_read = 'auto'\r\n"
    "# a comment in the middle\r\n"
    "append_obsidian_daily     = \"auto\"\r\n"
    "\r\n"
    "# ---- 3. the next section ----\r\n"
    "[self_modification]\r\n"
    "enabled = true\r\n"
)


# ======================================================== 1. the page

def t_the_page_lists_every_action():
    ids = [a for _, rows in AF.GROUPS for a in rows]
    check("every action a card can name is on the page",
          not [a for a in W.TITLES if a not in ids], [a for a in W.TITLES if a not in ids])
    check("each is listed once", len(ids) == len(set(ids)))
    v = AF.view(here=False)
    rows = {r["id"]: r for g in v["groups"] for r in g["rows"]}
    check("the page's words", v["title"] == "What asks first" and v["switch_label"] == "Ask me first"
          and v["can_loosen"] is False and v["available"] is True)
    check("a row's title is its card's own words",
          rows["calendar_read"]["title"] == "Read your calendar"
          and rows["send_email"]["title"] == "Send an email", rows["calendar_read"])
    check("sending email always asks, and says it cannot be changed from an app",
          rows["send_email"]["note"] == AF.NOTE_ALWAYS and "switch" not in rows["send_email"])
    check("home control always asks; the lights row is its own",
          "switch" not in rows["home_control"] and rows["fixed:lights"]["lights"] is True
          and rows["fixed:lights"]["says"] == AF.SAYS["ask"])
    check("plain repeats: 'Does it without asking' (2026-09-26)",
          rows["fixed:repeats"]["says"] == "Does it without asking")
    check("the wiki says why it cannot be loosened", rows["wiki_update"]["note"] == AF.NOTE_WIKI)
    check("from the phone, a switch cannot loosen",
          all(r["switch"]["can_loosen"] is False for r in rows.values() if r.get("switch")))
    rows_pc = {r["id"]: r for g in AF.view(here=True)["groups"] for r in g["rows"]}
    check("from the PC it can", all(r["switch"]["can_loosen"] is True for r in rows_pc.values()
                                    if r.get("switch")))
    check("the switches are exactly the short safe list",
          sorted(r["id"] for r in rows_pc.values() if r.get("switch")) == sorted(AF.SWITCHABLE))
    keep = AF._tier
    AF._tier = lambda a: "auto"
    try:
        r = AF._row("send_email", here=True)
        check("an always-ask action set looser in the file says it is refused, not 'does it'",
              r["says"] == AF.SAYS_REFUSED, r)
    finally:
        AF._tier = keep


def t_the_safe_list_never_meets_the_hard_limits():
    s = set(AF.SWITCHABLE)
    check("the short safe list is the owner's: reads and note writes",
          s == {"calendar_read", "email_read", "notes_search", "home_read",
                "append_obsidian_daily", "append_logseq_journal", "create_joplin_note"}, s)
    check("... never a hard limit", not s & AF.HARD_LIMITS)
    check("... never an action whose module accepts only 'ask'", not s & AF.MUST_ASK)
    person = set()
    for tool in AG.NEEDS_A_PERSON:
        person.add(tool)
        t = AG.TOOLS.get(tool)
        if t is not None and t.gate_lookup_name:
            person.add(t.gate_lookup_name({}))
    person |= {"home_control", "send_email", "control_computer", "control_phone",
               "control_browser", "run_shell_on_host", "web_research"}
    check("... never the action of a tool that only runs on a person's yes", not s & person)
    check("... and not the wiki (written only on a person's yes, security audit L1)",
          "wiki_update" not in s and "wiki_update" in AF.MUST_ASK)
    check("the loosening card's own action is a hard limit and must ask",
          AF.LOOSEN_ACTION in AF.HARD_LIMITS and AF.LOOSEN_ACTION in AF.MUST_ASK)
    check("loosening writes back the shipped tier, never 'auto' for a Joplin note",
          AF.LOOSE["create_joplin_note"] == "notify"
          and all(t in ("auto", "notify") for t in AF.LOOSE.values()))
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("the shipped settings file has loosen_what_asks_first = \"ask\"",
          'loosen_what_asks_first    = "ask"' in toml)


# ======================================================== 3. the file

def t_one_line_changes_and_every_other_byte_stays():
    out = AF.rewrite(SAMPLE, "calendar_read", "ask")
    a, b = SAMPLE.split("\r\n"), out.split("\r\n")
    changed = [(x, y) for x, y in zip(a, b) if x != y]
    check("exactly one line changed, and only its value", len(a) == len(b) and changed == [
        ('calendar_read             = "auto"   # I like this one',
         'calendar_read             = "ask"   # I like this one')], changed)
    check("CRLF line endings kept", out.count("\r\n") == SAMPLE.count("\r\n")
          and "\n" not in out.replace("\r\n", ""))
    out = AF.rewrite(SAMPLE, "email_read", "ask")
    check("a single-quoted value keeps its quotes", "email_read = 'ask'" in out)
    out = AF.rewrite(SAMPLE, "home_read", "ask")
    lines = out.split("\r\n")
    at = lines.index('home_read = "ask"' + AF._INSERTED_NOTE)
    check("a missing line is added after the table's last line, and nothing else moves",
          lines[at - 1].startswith("append_obsidian_daily") and
          [x for x in lines if not x.startswith("home_read")] == SAMPLE.split("\r\n"), lines)
    for label, text in (
            ("the table twice", SAMPLE + "[autonomy.tiers]\r\n"),
            ("the key twice", SAMPLE.replace('web_research              = "auto"',
                                             'calendar_read = "auto"')),
            ("an inline table", "[autonomy]\ntiers = { calendar_read = \"auto\" }\n"),
            ("no table at all", "[autonomy]\nx = 1\n")):
        try:
            AF.rewrite(text, "calendar_read", "ask")
            check(f"{label}: refused", False)
        except AF.TierFileError as exc:
            check(f"{label}: refused, with how to do it by hand",
                  "by hand" in str(exc) or "mistake" in str(exc), str(exc))
    try:
        AF.rewrite("[autonomy.tiers\nbroken", "calendar_read", "ask")
        check("a file with a mistake: refused", False)
    except AF.TierFileError as exc:
        check("a file with a mistake: refused", "mistake" in str(exc), str(exc))


def t_set_tier_writes_atomically_and_keeps_a_bom():
    p = TMP / "jarvis-framework.toml"
    raw = b"\xef\xbb\xbf" + SAMPLE.encode("utf-8")
    p.write_bytes(raw)
    got = AF.set_tier("calendar_read", "ask", path=p)
    new = p.read_bytes()
    check("set_tier answers from and to", got == {"ok": True, "from": "auto", "to": "ask"}, got)
    check("the byte-order mark is kept", new.startswith(b"\xef\xbb\xbf"))
    check("only that line differs, byte for byte",
          new.replace(b'calendar_read             = "ask"', b'calendar_read             = "auto"')
          == raw)
    check("no temporary file is left behind",
          sorted(x.name for x in TMP.iterdir() if x.name.startswith("jarvis-framework.toml"))
          == ["jarvis-framework.toml"])
    p.write_bytes(b"[autonomy.tiers]\nx = \"\xff\"\n")
    before = p.read_bytes()
    try:
        AF.set_tier("calendar_read", "ask", path=p)
        check("not UTF-8: refused", False)
    except AF.TierFileError:
        check("not UTF-8: refused, and the file is untouched", p.read_bytes() == before)
    try:
        AF.set_tier("calendar_read", "ask", path=TMP / "nowhere.toml")
        check("no file: refused", False)
    except AF.TierFileError as exc:
        check("no file: refused in words", "could not find" in str(exc))


# ======================================================== 4. stricter and looser

class Tiers:
    def __init__(self, **t):
        self.t = dict(t)
        self.t.setdefault(AF.LOOSEN_ACTION, "ask")
        self.writes = []

    def __call__(self, action):
        return self.t.get(action, "ask")

    def write(self, action, tier):
        self.writes.append((action, tier))
        self.t[action] = tier


def _req(body, tiers, *, here, gate=None, armed=True, spawn=None):
    AF._reset_for_tests()
    return AF.request_tier(body, here=here, tier_of=tiers, write=tiers.write,
                           gate=gate or (lambda a, d, p: Verdict(True, "ask", "approved")),
                           spawn=spawn or (lambda fn: fn()), armed=lambda: armed)


def t_stricter_is_immediate_from_either_app():
    for here in (False, True):
        tiers = Tiers(calendar_read="auto")
        asked = []
        code, out = _req({"action": "calendar_read", "ask": True}, tiers, here=here,
                         gate=lambda a, d, p: asked.append(a))
        check(f"stricter from {'the PC' if here else 'the phone'}: 200, written 'ask', no card",
              code == 200 and tiers.writes == [("calendar_read", "ask")] and asked == [],
              (code, out))
    tiers = Tiers(calendar_read="ask")
    code, out = _req({"action": "calendar_read", "ask": True}, tiers, here=False)
    check("already asks: nothing written", code == 200 and tiers.writes == []
          and out["changed"] is False)
    code, out = _req({"action": "send_email", "ask": True}, Tiers(), here=True)
    check("stricter on something off the list: refused too (the app only switches its list)",
          code == 403)


def t_looser_only_on_the_pc_only_from_the_list_only_with_a_card():
    tiers = Tiers(calendar_read="ask")
    code, out = _req({"action": "calendar_read", "ask": False}, tiers, here=False)
    check("from the phone: 403, the PC only, nothing written",
          code == 403 and out.get("pc_only") is True and tiers.writes == [], out)
    for action in ("send_email", "home_control", "write_notes_after_outside_text",
                   "wiki_update", "run_shell_on_host", "search_the_web", AF.LOOSEN_ACTION,
                   "spend_money", "delete_file", "learning_sensitive_enable", "nonsense"):
        tiers = Tiers(**{action: "ask"})
        code, out = _req({"action": action, "ask": False}, tiers, here=True)
        check(f"{action}: cannot be loosened from an app (403), nothing written",
              code == 403 and tiers.writes == [] and out["error"] == AF.NOT_ON_LIST, (code, out))
    tiers = Tiers(calendar_read="ask")
    code, out = _req({"action": "calendar_read", "ask": False}, tiers, here=True, armed=False)
    check("without the backend's own Windows Hello check: 503, nothing written",
          code == 503 and tiers.writes == [] and "Windows Hello" in out["error"])
    tiers = Tiers(calendar_read="ask", **{AF.LOOSEN_ACTION: "auto"})
    code, out = _req({"action": "calendar_read", "ask": False}, tiers, here=True)
    check("the card's own tier not 'ask': 503 - a line is not a yes", code == 503
          and tiers.writes == [])
    asked = []
    tiers = Tiers(calendar_read="ask")
    code, out = _req({"action": "calendar_read", "ask": False}, tiers, here=True,
                     gate=lambda a, d, p: (asked.append((a, d, p)),
                                           Verdict(True, "ask", "approved"))[1])
    check("from the PC: ONE card, loosen_what_asks_first", code == 202
          and [a for a, _, _ in asked] == [AF.LOOSEN_ACTION], (code, asked))
    card = asked[0][2] if asked else ""
    check("the card says what, the exact line, Windows Hello, and what no means",
          card.startswith("Let Jarvis read your calendar without asking you first?")
          and 'calendar_read = "auto"' in card and "Windows Hello" in card
          and "If you say no: nothing changes" in card, card)
    check("approved by a person: the line goes back to the shipped tier",
          tiers.writes == [("calendar_read", "auto")])
    check("... and the page says so", AF._L_STATE["last"].get("outcome") == "loosened")
    for verdict, why in ((Verdict(False, "ask", "denied"), "denied"),
                         (Verdict(False, "ask", "timed_out"), "timed out"),
                         (Verdict(True, "auto", "auto"), "allowed at 'auto' (nobody asked)"),
                         (Verdict(True, "notify", "notify"), "allowed at 'notify'")):
        tiers = Tiers(calendar_read="ask")
        _req({"action": "calendar_read", "ask": False}, tiers, here=True,
             gate=lambda a, d, p, v=verdict: v)
        check(f"{why}: nothing written", tiers.writes == [])
    tiers = Tiers(create_joplin_note="ask")
    _req({"action": "create_joplin_note", "ask": False}, tiers, here=True)
    check("a Joplin note goes back to 'notify' (told afterwards), not 'auto'",
          tiers.writes == [("create_joplin_note", "notify")])
    # A stricter press while the card waits withdraws it.
    held = []
    tiers = Tiers(calendar_read="ask")
    AF._reset_for_tests()
    AF.request_tier({"action": "calendar_read", "ask": False}, here=True, tier_of=tiers,
                    write=tiers.write, gate=lambda a, d, p: Verdict(True, "ask", "approved"),
                    spawn=held.append, armed=lambda: True)
    code, out = AF.request_tier({"action": "calendar_read", "ask": True}, here=False,
                                tier_of=tiers, write=tiers.write, armed=lambda: True)
    held[0]()
    check("stricter while the card waited: approving it later changes nothing",
          tiers.writes == [] and AF._L_STATE["last"].get("outcome") == "withdrawn",
          (tiers.writes, AF._L_STATE["last"]))
    tiers = Tiers(calendar_read="never")
    code, out = _req({"action": "calendar_read", "ask": True}, tiers, here=True)
    check("'never' in the file: left alone either way (409)", code == 409 and tiers.writes == [])
    code, out = AF.request_tier({"action": "calendar_read"}, here=True)
    check("a body without ask: 400", code == 400)


# ======================================================== 5. the approval

def t_a_loosening_card_is_approved_on_the_pc_only_with_windows_hello():
    row = {"id": "r1", "action": AF.LOOSEN_ACTION, "expires_in": 100,
           "risk": {"classified": True, "reach": "local", "reversible": "yes"}}
    asked = []
    OC.set_verifier(lambda m, t: (asked.append(m), OC.CONFIRMED)[1])
    try:
        got = OC.approve_check({"id": "r1"}, peer="100.64.0.9", local="100.64.0.2",
                               pending=lambda: [row], own=["100.64.0.2"])
        check("approved from another device (the phone): 403, nothing asked",
              got is not None and got[0] == 403 and got[1]["owner_check"] == "pc_only"
              and asked == [], got)
        got = OC.approve_check({"id": "r1"}, peer="127.0.0.1", pending=lambda: [row])
        check("from this PC: Windows Hello, even though the card is not risky",
              got is None and len(asked) == 1)
        OC.set_verifier(lambda m, t: OC.UNAVAILABLE)
        got = OC.approve_check({"id": "r1"}, peer="127.0.0.1", pending=lambda: [row])
        check("no Windows Hello: refused", got is not None and got[0] == 403)
        other = dict(row, action="wiki_update")
        OC.set_verifier(lambda m, t: (asked.append(m), OC.CONFIRMED)[1])
        n = len(asked)
        got = OC.approve_check({"id": "r1"}, peer="100.64.0.9", local="100.64.0.2",
                               pending=lambda: [other], own=["100.64.0.2"])
        check("any other card from the phone is as before (stamped, no prompt here)",
              got is None and len(asked) == n)
    finally:
        OC.set_verifier(None)
    check("the card has a title in plain words",
          W.title_for(AF.LOOSEN_ACTION) == "Jarvis wants to let one action go ahead without "
                                           "asking you first")


# ======================================================== 6. the lights setting

def t_the_lights_setting():
    AF._reset_for_tests()
    (TMP / "asks_first.json").unlink(missing_ok=True)
    check("off by default", AF.lights_setting() == {"on": False, "why": ""} and not AF.lights_on())
    asked = []
    code, out = AF.request_lights(True, gate=lambda a, d, p: (asked.append((a, p)),
                                                             Verdict(True, "ask", "approved"))[1],
                                  tier_of=lambda a: "ask", spawn=lambda fn: fn())
    check("ON: 202, ONE card, change_own_config", code == 202
          and [a for a, _ in asked] == ["change_own_config"], (code, asked))
    check("the card says only lights, plugs and fans, named, and what always asks",
          "Only lights, plugs" in asked[0][1] and "Locks, doors, alarms, covers" in asked[0][1]
          and "outside text" in asked[0][1] and "If you say no" in asked[0][1])
    check("approved: on", AF.lights_on())
    code, out = AF.request_lights(False)
    check("OFF: at once, no card", code == 200 and not AF.lights_on())
    for v in (Verdict(False, "ask", "denied"), Verdict(True, "auto", "auto")):
        AF.request_lights(True, gate=lambda a, d, p, v=v: v, tier_of=lambda a: "ask",
                          spawn=lambda fn: fn())
        check(f"a card that ends {v.outcome!r}: still off", not AF.lights_on())
    code, out = AF.request_lights(True, tier_of=lambda a: "auto", spawn=lambda fn: fn())
    check("change_own_config not 'ask': 503", code == 503 and not AF.lights_on())
    held = []
    AF.request_lights(True, gate=lambda a, d, p: Verdict(True, "ask", "approved"),
                      tier_of=lambda a: "ask", spawn=held.append)
    AF.request_lights(False)
    held[0]()
    check("turned off while the card waited: approving it changes nothing", not AF.lights_on())
    (TMP / "asks_first.json").write_text("{not json", encoding="utf-8")
    check("a damaged file: off, and it says why", AF.lights_setting()["on"] is False
          and "damaged" in AF.lights_setting()["why"])
    (TMP / "asks_first.json").unlink()


def t_what_counts_as_named_and_everyday():
    check("'turn off the kitchen light' names light.kitchen",
          AF.named_in("light.kitchen", "turn off the kitchen light"))
    check("... and light.kitchen_light", AF.named_in("light.kitchen_light", "kitchen light off"))
    check("... but not light.kitchen_ceiling", not AF.named_in("light.kitchen_ceiling",
                                                                "turn off the kitchen light"))
    check("plurals: 'the hall lights' names light.hall",
          AF.named_in("light.hall", "turn off the hall lights"))
    check("'all the lights' names nobody", not AF.named_in("light.hall", "turn off all the lights"))
    check("an id with only device words is never named", not AF.named_in("light.light", "light"))
    from test_home_several import Env
    with Env():
        cases = (("lights off", H.plan_services("light", "turn_off",
                                                 ["light.kitchen", "light.hall"]), ""),
                 ("a fan on", H.plan_service("fan", "turn_on", "fan.bedroom",
                                             {"percentage": 40}), ""),
                 ("a plug toggled", H.plan_service("switch", "toggle", "switch.kettle"), ""),
                 ("a lock", H.plan_service("lock", "unlock", "lock.front_door"), "x"),
                 ("a garage opener that is a switch",
                  H.plan_service("switch", "turn_on", "switch.garage_door"), "x"),
                 ("homeassistant.turn_off on a light (forwards to anything)",
                  H.plan_service("homeassistant", "turn_off", "light.kitchen"), "x"),
                 ("a cover", H.plan_service("cover", "open_cover", "cover.blinds"), "x"),
                 ("a scene", H.plan_service("scene", "turn_on", "scene.movie"), "x"),
                 ("light.turn_on with a strange data key",
                  H.plan_service("light", "turn_on", "light.kitchen", {"flash": "long"}), "x"),
                 ("a light's service on a switch",
                  H.plan_service("light", "turn_on", "switch.kettle"), "x"))
        for label, plan, want in cases:
            got = H.everyday_problem(plan)
            check(f"{label}: {'no card' if not want else 'a card'}", bool(got) == bool(want), got)


# ======================================================== 7. the chat loop

def _turn(args, gate, *, words="turn off the kitchen and hall lights", prov="typed",
          extra_messages=(), request=None):
    from test_agent import NoRealIO, scripted_stream
    responses = [{"choices": [{"message": {"role": "assistant", "tool_calls": [
        {"id": "1", "function": {"name": "home_control", "arguments": json.dumps(args)}}]}}]},
                 {"choices": [{"message": {"role": "assistant", "content": "done"}}]}]
    opener, bodies = scripted_stream(responses)
    real_tier = AG._tier_of
    AG._tier_of = lambda action: "ask"
    try:
        with NoRealIO():
            AG.run_local_turn(list(extra_messages) + [{"role": "user", "content": words,
                                                       "provenance": prov}],
                              "qwen3:8b", ollama_url="http://127.0.0.1:11434",
                              stream_out=lambda x: None, gate_check=gate, open_stream=opener,
                              enabled_tools={"home_control"}, request=request)
    finally:
        AG._tier_of = real_tier


def t_the_loop_switches_named_lights_without_a_card():
    from test_home_several import Env, Recorder, Gate
    lights = {"domain": "light", "service": "turn_off",
              "entity_ids": ["light.kitchen", "light.hall"]}
    AF.set_lights(False)
    gate = Gate(Verdict(True, "ask", "approved"))
    with Env(), Recorder() as rec:
        _turn(lights, gate)
    check("setting off (the default): a card, as before", len(gate.asked) == 1 and
          len(rec.sent) == 2)
    AF.set_lights(True)
    try:
        audit = []
        keep = AF._audit
        AF._audit = lambda e, d: audit.append((e, d))
        gate = Gate(Verdict(False, "ask", "denied"))
        with Env(), Recorder() as rec:
            _turn(lights, gate)
        AF._audit = keep
        check("setting on, named lights, a clean typed turn: NO card, both switched",
              gate.asked == [] and [b["entity_id"] for _, _, b in rec.sent]
              == ["light.kitchen", "light.hall"], (gate.asked, rec.sent))
        check("... and the audit log names the devices and the service",
              audit and audit[-1][0] == "asks_first.lights.no_card"
              and audit[-1][1]["entities"] == ["light.kitchen", "light.hall"]
              and audit[-1][1]["service"] == "light/turn_off", audit)
        for label, args, kw in (
                ("a lock", {"domain": "lock", "service": "unlock",
                            "entity_id": "lock.front_door"}, {"words": "unlock the front door"}),
                ("a garage switch", {"domain": "switch", "service": "turn_on",
                                     "entity_id": "switch.garage_door"},
                 {"words": "open the garage door"}),
                ("a light the owner did not name", lights, {"words": "turn off the lights"}),
                ("pasted words", lights, {"prov": "pasted"}),
                ("a voice turn this PC could not check", lights, {"prov": "voice_unverified"}),
                ("an app's own text with the message", lights,
                 {"request": {"messages": [
                     {"role": "system", "content": "clipboard: x"},
                     {"role": "user", "content": "turn off the kitchen and hall lights",
                      "provenance": "typed"}]}})):
            gate = Gate(Verdict(False, "ask", "denied"))
            with Env(), Recorder() as rec:
                _turn(args, gate, **kw)
            check(f"{label}: still a card, and denied sends nothing",
                  len(gate.asked) == 1 and rec.sent == [], (gate.asked, rec.sent))
        with Env():
            one = H.plan_services("light", "turn_off", ["light.kitchen"])
        check("the plain check: named, clean turn, setting on - no card",
              AF.lights_without_card(one, "kitchen light off", shaped="") == "")
        check("after outside text: never", AF.lights_without_card(
            one, "kitchen light off", shaped=AG.NOTE_AFTER_READING) != "")
        w = AG._TurnWatch([{"role": "user", "content": "Kitchen light off",
                            "provenance": "voice"}], tainted=False)
        check("said aloud by the owner counts as their own words",
              w.newest_own_words == "kitchen light off" and w.note_needs_a_person() == "")
        w = AG._TurnWatch([{"role": "user", "content": "kitchen light off",
                            "provenance": "shared"}], tainted=False)
        check("shared words are not the owner's", w.newest_own_words == "")
        check("home_control is still in NEEDS_A_PERSON", "home_control" in AG.NEEDS_A_PERSON)
    finally:
        AF.set_lights(False)


# ======================================================== 8. the patch

def t_the_patch():
    order = _stack.order()
    check("asks-first.patch is last in apply-patches.ps1's list", order[-1] == "asks-first.patch",
          order[-3:])
    patch = (HERE / "asks-first.patch").read_text(encoding="utf-8")
    check("it patches jarvis_hud.py and jarvis_gate.py and nothing else",
          sorted(l[6:].strip() for l in patch.splitlines() if l.startswith("+++ b/"))
          == ["jarvis_gate.py", "jarvis_hud.py"])
    git = shutil.which("git")
    if not git:
        check("git is here to apply it", False)
        return
    for target in ("jarvis_hud.py", "jarvis_gate.py"):
        text, log = _stack.stand_in(target, order[:-1])
        if text is None:
            check(f"a stand-in of {target} could be built", False, log)
            continue
        d = Path(tempfile.mkdtemp(prefix="jarvis-asks-first-patch-"))
        try:
            (d / target).write_text(text, encoding="utf-8", newline="\n")
            one = "".join(_stack.hunks(patch, target) and
                          [h for h, _ in _stack.hunks(patch, target)])
            (d / "p.patch").write_text(f"--- a/{target}\n+++ b/{target}\n{one}",
                                       encoding="utf-8", newline="\n")
            r = subprocess.run([git, "apply", "p.patch"], cwd=d, capture_output=True, text=True)
            ok = r.returncode == 0
            r2 = subprocess.run([git, "apply", "-R", "p.patch"], cwd=d, capture_output=True,
                                text=True)
            back = (d / target).read_text(encoding="utf-8") == text
            check(f"{target}: applies to what the earlier patches wrote, and reverses",
                  ok and r2.returncode == 0 and back, (r.stderr, r2.stderr))
        finally:
            shutil.rmtree(d, ignore_errors=True)
    import _where
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("the module is shipped: apply-patches.ps1 and _where.SHIPPED",
          "'jarvis_asks_first.py'" in ps1[ps1.index("$SHIPPED = @("):]
          and "jarvis_asks_first.py" in _where.SHIPPED)
    # The notice (a card's bottom line, and the lock screen's words) must not
    # contradict the card above it: a "tell me when" signs in to the owner's
    # mail server every few minutes, and a briefing reads the calendar.
    line = next((l for l in patch.splitlines()
                 if l.startswith('+    "schedule_repeat": (')), "")
    check("schedule_repeat's notice says each run reads the owner's own servers, "
          "and never 'sends nothing anywhere'",
          "sends nothing anywhere" not in line and "calendar and email" in line
          and "own mail server or Home Assistant" in line
          and "deleting it is immediate" in line, line)
    check("the route answers GET and POST", '"/api/asks_first"' in patch
          and '"/api/asks_first/tier"' in patch and '"/api/asks_first/lights"' in patch)


def t_the_shipped_settings_and_the_case_table_agree():
    """The page's cases (tools/gen_asks_first_cases.py SHIPPED) are the
    shipped settings file's tiers, line for line. And draft_email - on the
    never-loosened list - ships asking (feasibility audit step 0.3,
    2026-09-26: it shipped "auto")."""
    import ast
    import tomllib
    toml = tomllib.loads((REPO / "backend" / "rebuilt" / "jarvis-framework.toml")
                         .read_text(encoding="utf-8"))
    tiers = toml["autonomy"]["tiers"]
    src = (REPO / "tools" / "gen_asks_first_cases.py").read_text(encoding="utf-8")
    shipped = next(ast.literal_eval(n.value) for n in ast.parse(src).body
                   if isinstance(n, ast.Assign)
                   and any(getattr(t, "id", "") == "SHIPPED" for t in n.targets))
    differ = {a: (t, tiers.get(a)) for a, t in shipped.items() if tiers.get(a) != t}
    check("every tier in the case table is the shipped file's", not differ, differ)
    check("draft_email ships as \"ask\" (a card), in the file and the case table",
          tiers.get("draft_email") == "ask" and shipped.get("draft_email") == "ask",
          (tiers.get("draft_email"), shipped.get("draft_email")))
    check("... and stays on the never-loosened list", "draft_email" in AF.HARD_LIMITS
          and "draft_email" not in AF.SWITCHABLE)
    loose = {a for a, t in tiers.items() if t in ("auto", "notify")}
    # web_research ships "auto" on purpose (jarvis-framework.toml's own
    # test pins it); the tool loop still puts it to a person
    # (jarvis_agent.NEEDS_A_PERSON), so it never runs unasked.
    check("nothing on the never-loosened list ships looser than \"ask\" "
          "(web_research aside: the tool loop always asks a person for it)",
          not (loose & AF.HARD_LIMITS) - {"web_research"}, sorted(loose & AF.HARD_LIMITS))


def t_both_apps_read_the_current_contract():
    r = subprocess.run([sys.executable, str(REPO / "tools" / "gen_asks_first_cases.py"),
                        "--check"], capture_output=True, text=True, timeout=120,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    check("asks-first-cases.json (desktop and phone) is what the backend says today "
          "(python3 tools/gen_asks_first_cases.py)", r.returncode == 0, r.stdout + r.stderr)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
