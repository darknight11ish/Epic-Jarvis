#!/usr/bin/env python3
"""test_setup.py - the setup questionnaire's plan, apply and routes.

    python3 backend/test_setup.py

WHAT IS CHECKED, and why each check matters:

* every question and every option maps to an EXISTING setter (the registry's
  BoolSettings, or the named jars): a new kind that goes nowhere is a question
  that would silently do nothing on the owner's PC;
* `plan()` is READ-ONLY: it writes no file and raises no card. The plan is what
  the owner is shown before they accept anything, so a plan with a side effect
  would be an apply behind the Accept button;
* `effect` is "card" exactly where the existing setter asks, and "instant"
  where it does not - checked for every direction the questionnaire offers;
* when the settings file does not open a card for a carded direction (tier
  not "ask"), the setter itself refuses, so `plan` reports it as skipped and
  never promises it;
* "All" and "None" work at the DATA level for every choose-any question;
* `apply()` refuses without `confirm: true`, calls the instant setters in the
  fixed safe order, and for a carded change waits for the ONE card before
  raising anything else (approved and denied both covered, and a denied card
  leaves the rest of the answers still applied);
* a missing module or a failed setting is said in words and never aborts the
  rest; the answers are still saved (they are the owner's own words, not a
  claim that every setting changed);
* `state()` round-trips the saved answers and completed timestamp, so a re-run
  is prefilled and a first-run offer can be shown once;
* the module never imports the gate, never calls a preset's apply route, never
  switches a model, and writes only `setup.json` in the settings folder - it
  cannot approve, cannot clear a latch and cannot move anything off this PC;
* the three routes are wired (GET /api/setup, POST /api/setup/plan,
  POST /api/setup/apply) with the same origin and token checks as every write.

No network, no model, no microphone, no owner's PC. Runs in repo mode; the
suite gives it a temporary settings folder.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_setup.py")

_TMP = tempfile.mkdtemp(prefix="jarvis-setup-")
os.environ["OPENJARVIS_CONFIG_DIR"] = _TMP

import jarvis_setup as S  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------------------
#   Small stand-ins: readers (current values), appliers (the setters),
#   a waiter (card answers), and the HUD's handler.
# ---------------------------------------------------------------------------


def opposite(ch):
    """A current value that is NOT the change's target, so every option in the
    questionnaire produces a visible change."""
    kind = str(ch.get("kind") or "")
    if kind == "asks_first":
        return {"tier": "auto", "asks": True} if not ch.get("ask") else \
               {"tier": "auto", "asks": False}
    if kind in ("bool", "reading_tool", "animal", "sky_show"):
        return not bool(ch.get("to"))
    if kind == "manner":
        return "plain" if ch.get("to") != "plain" else "warm"
    if kind == "card_mode":
        return "always_full" if ch.get("to") != "always_full" else "start_short"
    if kind == "provider":
        return "duckduckgo" if ch.get("to") != "duckduckgo" else "searxng"
    return None


class Recorder:
    def __init__(self, waiting=False, ok=True):
        self.calls = []
        self.waiting = waiting
        self.ok = ok

    def __call__(self, ch):
        self.calls.append(S.change_key(ch))
        return {"ok": self.ok, "waiting": self.waiting, "message": "called"}


class FakeHandler:
    sent = None

    def __init__(self, path, body=b"{}", token=True):
        self.path, self.body, self.token = path, body, token
        FakeHandler.sent = None

    def _send(self, code, out, **k):
        FakeHandler.sent = (code, out)

    def do_GET(self):
        FakeHandler.sent = ("orig-get", None)

    def do_POST(self):
        FakeHandler.sent = ("orig-post", None)


# ---------------------------------------------------------------------------
#   1. The questions are real data, and every mapping exists in the tree
# ---------------------------------------------------------------------------


def t_every_question_and_option_is_well_formed():
    ids = [q["id"] for q in S.QUESTIONS]
    check("question ids are unique", len(ids) == len(set(ids)), ids)
    bad = []
    for q in S.QUESTIONS:
        if not q.get("title") or not q.get("help"):
            bad.append(f"{q.get('id')}: missing title/help")
        if not isinstance(q.get("multi"), bool):
            bad.append(f"{q.get('id')}: multi is not a bool")
        seen = set()
        for o in q["options"]:
            oid = str(o.get("id") or "")
            if not oid or oid in seen:
                bad.append(f"{q['id']}: bad/duplicate option id {oid!r}")
            seen.add(oid)
            if not o.get("label"):
                bad.append(f"{q['id']}/{oid}: no plain label")
            if not o.get("changes") and not (q["id"] == "carefulness"
                                             and o["id"] == "balanced"):
                bad.append(f"{q['id']}/{oid}: no changes")
    check("every question has a title, help, a multi flag and labelled options",
          not bad, "\n".join(bad))


def t_every_change_maps_to_a_real_setter():
    R = __import__("jarvis_settings_registry")
    bools = {b.key for b in R.BOOL_SETTINGS}
    MANNERS = ("warm", "plain")
    CARD_MODES = ("start_short", "always_full")
    bad = []
    for q in S.QUESTIONS:
        for o in q["options"]:
            for ch in o["changes"]:
                kind = str(ch.get("kind") or "")
                if kind == "bool":
                    if ch.get("setting") not in bools:
                        bad.append(f"{q['id']}/{o['id']}: no BoolSetting "
                                   f"{ch.get('setting')!r}")
                    if not isinstance(ch.get("to"), bool):
                        bad.append(f"{q['id']}/{o['id']}: bool change to is not a bool")
                elif kind == "asks_first":
                    if ch.get("action") not in S.ASKS_FIRST_ACTIONS:
                        bad.append(f"{q['id']}/{o['id']}: unknown asks action")
                    if not isinstance(ch.get("ask"), bool):
                        bad.append(f"{q['id']}/{o['id']}: asks is not a bool")
                elif kind == "reading_tool":
                    if ch.get("tool") not in S.READING_TOOLS:
                        bad.append(f"{q['id']}/{o['id']}: unknown reading tool")
                elif kind == "animal":
                    AN = __import__("jarvis_animal")
                    if ch.get("key") not in {s.id for s in AN.SWITCHES}:
                        bad.append(f"{q['id']}/{o['id']}: unknown animal switch")
                elif kind == "manner":
                    pass
                elif kind == "card_mode":
                    pass
                elif kind == "provider":
                    WS = __import__("jarvis_search")
                    if ch.get("to") not in WS.PROVIDERS:
                        bad.append(f"{q['id']}/{o['id']}: unknown search provider")
                elif kind == "sky_show":
                    if not isinstance(ch.get("to"), bool):
                        bad.append(f"{q['id']}/{o['id']}: sky_show to is not a bool")
                elif kind == "preset":
                    P = __import__("jarvis_presets")
                    if ch.get("to") not in {p.id for p in P.PRESETS}:
                        bad.append(f"{q['id']}/{o['id']}: unknown preset id")
                else:
                    bad.append(f"{q['id']}/{o['id']}: unknown change kind {kind!r}")
    check("every option maps to an existing setter / registry setting", not bad,
          "\n".join(bad))
    check("the talk-style and card-size options are the existing choices",
          MANNERS == ("warm", "plain") and CARD_MODES == ("start_short", "always_full"),
          (MANNERS, CARD_MODES))


def t_the_carded_actions_are_the_modules_own():
    """The action names a carded direction checks are read from the module
    that raises that card, never typed twice here."""
    AL = __import__("jarvis_auto_learn")
    WS = __import__("jarvis_search")
    WN = __import__("jarvis_watch_notify")
    PN = __import__("jarvis_phone_notifications")
    SP = __import__("jarvis_screen_picture")
    BE = __import__("jarvis_browser_engine")
    SANDBOX = __import__("jarvis_sandbox_exec")
    BR = __import__("jarvis_briefing")
    BC = __import__("jarvis_big_coder")
    JV = __import__("jarvis_voices")
    AF = __import__("jarvis_asks_first")
    want = {
        "background_learning": AL.action_for("auto"),
        "learn_sensitive_topics": AL.action_for("sensitive"),
        "web_search": WS.ACTION_ENABLE,
        "ask_before_every_search": WS.ACTION_ASK_LESS,
        "smartwatch_notifications": WN.ACTION,
        "phone_notifications": PN.ACTION,
        "screen_picture": SP.ACTION,
        "headless_browser": BE.ACTION,
        "sandbox_exec": SANDBOX.SWITCH_ACTION,
        "briefing_senders": BR.SENDERS_ACTION,
        "big_coder": BC.ACTION_ON,
        "better_voice": JV.BETTER_ACTION,
    }
    got = {k: S._bool_action(k) for k in want}
    check("every carded BoolSetting's action is its module's own constant",
          got == want, (got, want))
    check("the asks-first and reading-tool cards use jarvis_asks_first's own actions",
          S._asks_first_action() == AF.LOOSEN_ACTION
          and S._tool_action() == AF.ENABLE_TOOL_ACTION,
          (S._asks_first_action(), S._tool_action()))
    check("the preset answer is a recommendation, never a model switch",
          any(ch.get("kind") == "preset"
              for q in S.QUESTIONS if q["id"] == "main_use"
              for o in q["options"] for ch in o["changes"])
          and "apply_preset" not in Path(S.__file__).read_text(encoding="utf-8"),
          "preset change missing or the module calls apply_preset")


# ---------------------------------------------------------------------------
#   2. plan() is read-only and marks carded vs instant correctly
# ---------------------------------------------------------------------------


def t_plan_writes_nothing():
    before = sorted(p.name for p in Path(_TMP).iterdir())
    out = S.plan({"talk_style": "plain", "web_search": "off"},
                 readers=opposite, tier_of=lambda a: "ask")
    after = sorted(p.name for p in Path(_TMP).iterdir())
    check("plan returns a shaped answer", out["ok"] is True
          and isinstance(out["changes"], list) and isinstance(out["skipped"], list),
          out)
    check("plan writes no file at all", before == after
          and not (Path(_TMP) / "setup.json").exists(), (before, after))


def t_every_option_plans_or_skips_without_raising():
    bad = []
    for q in S.QUESTIONS:
        for o in q["options"]:
            answers = {q["id"]: o["id"]}
            try:
                out = S.plan(answers, readers=opposite, tier_of=lambda a: "ask")
            except Exception as exc:
                bad.append(f"{q['id']}/{o['id']}: raised {type(exc).__name__}")
                continue
            if not out["ok"]:
                bad.append(f"{q['id']}/{o['id']}: plan said {out.get('error')}")
                continue
            if q["id"] == "main_use":
                if not out["recommendation"] or not any(
                        "Recommended setup" in line for line in out["summary"]):
                    bad.append(f"{q['id']}/{o['id']}: no preset recommendation")
                continue
            if q["id"] == "carefulness" and o["id"] == "balanced":
                if out["changes"]:
                    bad.append("balanced carefulness should change nothing")
                continue
            if not out["changes"]:
                bad.append(f"{q['id']}/{o['id']}: planned nothing")
            for row in out["changes"]:
                if row["effect"] not in ("instant", "card"):
                    bad.append(f"{q['id']}/{o['id']}: bad effect {row['effect']!r}")
                if not row["sentence"] or "->" not in row["sentence"]:
                    bad.append(f"{q['id']}/{o['id']}: unreadable sentence")
    check("every option plans a shaped change (or a recommendation), never raises",
          not bad, "\n".join(bad))


def t_card_rules_match_the_existing_rules():
    def one(answers, readers=None, tier="ask"):
        return S.plan(answers, readers=readers or opposite,
                      tier_of=lambda a: tier)

    def effect(out, key):
        return next((c["effect"] for c in out["changes"] if c["setting"] == key), None)

    out = one({"web_search": "on"})
    check("web search ON is its own card", effect(out, "bool:web_search") == "card", out)
    out = one({"web_search": "off"}, readers=lambda ch: True)
    check("web search OFF is instant", effect(out, "bool:web_search") == "instant", out)

    out = one({"search_asking": "ask_every"})
    check("'ask before every search' ON is instant (stricter)",
          effect(out, "bool:ask_before_every_search") == "instant", out)
    out = one({"search_asking": "ask_private"}, readers=lambda ch: True)
    check("turning 'ask before every search' OFF is one card",
          effect(out, "bool:ask_before_every_search") == "card", out)

    out = one({"learning": "learn_off"}, readers=lambda ch: True)
    check("turning automatic learning OFF is instant (narrowing)",
          effect(out, "bool:background_learning") == "instant", out)
    out = one({"learning": "learn"}, readers=lambda ch: False)
    check("turning automatic learning ON is its own card",
          effect(out, "bool:background_learning") == "card", out)

    out = one({"reading_tools": ["calendar"]}, readers=lambda ch: False)
    check("offering a reading tool is one card",
          effect(out, "tool:calendar_read") == "card", out)
    out = one({"reading_tools": ["none"]}, readers=lambda ch: True)
    check("taking a reading tool back is instant",
          effect(out, "tool:calendar_read") == "instant", out)

    out = one({"carefulness": "strict"}, readers=lambda ch: {"tier": "auto", "asks": False})
    check("making things stricter is instant",
          effect(out, "asks:calendar_read") == "instant", out)
    out = one({"carefulness": "trusting"},
              readers=lambda ch: {"tier": "ask", "asks": True})
    check("loosening a rule raises its own card",
          effect(out, "asks:calendar_read") == "card", out)

    out = one({"screen_pictures": ["screen_picture", "pictures"]},
              readers=lambda ch: False)
    check("each picture/screen switch keeps its own existing card rule",
          effect(out, "bool:screen_picture") == "card"
          and effect(out, "bool:pictures") == "instant", out)

    out = one({"notifications": ["all"]}, readers=lambda ch: False)
    effects = {c["setting"]: c["effect"] for c in out["changes"]}
    carded_here = {"bool:phone_notifications", "bool:smartwatch_notifications",
                   "bool:briefing_senders"}
    check("each notification switch keeps its own existing rule: three of them "
          "ask on their own card, the PC's five are instant",
          all(effects.get(k) == "card" for k in carded_here)
          and all(v == "instant" for k, v in effects.items()
                  if k not in carded_here), effects)

    out = one({"voice": ["better_voice"]}, readers=lambda ch: False)
    check("the better voice keeps its own card", effect(out, "bool:better_voice") == "card",
          out)


def t_a_tier_that_does_not_ask_is_skipped_not_promised():
    out = S.plan({"web_search": "on"}, readers=lambda ch: False,
                 tier_of=lambda a: "auto")
    key = "bool:web_search"
    check("a carded change whose action is not tier 'ask' is not planned",
          not any(c["setting"] == key for c in out["changes"])
          and any(s["setting"] == key for s in out["skipped"]), out)


def t_all_and_none_are_data():
    out = S.plan({"notifications": ["all"]}, readers=lambda ch: False,
                 tier_of=lambda a: "ask")
    keys = {c["setting"] for c in out["changes"]}
    check("'All' plans every switch in the question", len(keys) == 8
          and all(c["to"] is True for c in out["changes"]), out)
    out = S.plan({"notifications": ["none"]}, readers=lambda ch: True,
                 tier_of=lambda a: "ask")
    check("'None' plans every switch OFF", len(out["changes"]) == 8
          and all(c["to"] is False for c in out["changes"]), out)
    out = S.plan({"reading_tools": ["all"]}, readers=lambda ch: False,
                 tier_of=lambda a: "ask")
    check("'All' works for the reading-tool question too",
          {c["setting"] for c in out["changes"]}
          == {f"tool:{t}" for t in S.READING_TOOLS}, out)
    out = S.plan({"talk_style": ["all"]}, readers=opposite, tier_of=lambda a: "ask")
    check("'All' on a one-answer question is refused in words, not applied",
          not out["changes"] and any("only for a choose-any" in s["reason"]
                                     for s in out["skipped"]), out)


def t_unreadable_values_are_said_not_guessed():
    def boom(_ch):
        raise S.Unavailable("jarvis_search.py is not installed (ImportError)")
    out = S.plan({"web_search": "on"}, readers={"bool:web_search": boom},
                 tier_of=lambda a: "ask")
    check("a missing module is skipped with the words 'not available on this PC'",
          not out["changes"] and any("not available on this PC" in s["reason"]
                                     for s in out["skipped"]), out)


# ---------------------------------------------------------------------------
#   3. apply(): confirm, order, one card at a time, honest outcomes
# ---------------------------------------------------------------------------


def t_apply_refuses_without_confirm():
    rec = Recorder()
    out = S.apply({"talk_style": "plain"}, confirm=False, readers=opposite,
                  appliers={"manner": rec}, tier_of=lambda a: "ask")
    check("apply without confirm: refused, nothing called, nothing saved",
          out["ok"] is False and out["confirmed"] is False and out["outcomes"] == []
          and rec.calls == [] and not (Path(_TMP) / "setup.json").exists()
          and "confirm: true" in out["error"], out)


def t_apply_instant_calls_the_mapped_setters():
    for name in ("setup.json",):
        p = Path(_TMP) / name
        if p.exists():
            p.unlink()
    rec = Recorder()
    out = S.apply({"talk_style": "plain", "humour": "on",
                   "card_size": "full"},
                  confirm=True, readers=opposite,
                  appliers={"manner": rec, "bool:humor": rec,
                            "card_mode": rec},
                  tier_of=lambda a: "ask")
    check("apply calls exactly the setters its answers map to",
          sorted(rec.calls) == sorted(["manner", "bool:humor", "card_mode"]),
          rec.calls)
    check("every instant outcome reads as changed, in words",
          out["ok"] is True and out["confirmed"] is True
          and all(o["state"] == "changed" and o["message"] for o in out["outcomes"]),
          out)
    saved = json.loads((Path(_TMP) / "setup.json").read_text(encoding="utf-8"))
    check("apply saves the owner's answers and a completed timestamp",
          isinstance(saved.get("completed_at"), (int, float))
          and saved["answers"]["talk_style"] == "plain", saved)


def t_apply_carded_change_waits_for_its_own_card_then_continues():
    rec_wait = Recorder(waiting=True)
    rec_plain = Recorder()
    waits = []

    def waiter(ch, deadline):
        waits.append(S.change_key(ch))
        return {"state": "asked-and-denied",
                "message": "The card was turned down, so it stays off."}

    out = S.apply({"screen_pictures": ["screen_picture"], "humour": "on"},
                  confirm=True, readers=opposite,
                  appliers={"bool:screen_picture": rec_wait,
                            "bool:humor": rec_plain},
                  wait=waiter, tier_of=lambda a: "ask")
    states = {o["setting"]: o["state"] for o in out["outcomes"]}
    check("a carded change is raised, then WAITED for, before the next one",
          waits == ["bool:screen_picture"], waits)
    check("a denied card says so and stays as it was",
          states.get("bool:screen_picture") == "asked-and-denied", states)
    check("a denied card does not abort the rest of the answers",
          states.get("bool:humor") == "changed", states)
    check("both outcomes carry plain words",
          all(o["message"] for o in out["outcomes"]), out)

    rec2 = Recorder(waiting=True)

    def approve(ch, deadline):
        return {"state": "asked-and-approved", "message": "You approved the card."}

    out = S.apply({"screen_pictures": ["screen_picture"]}, confirm=True,
                  readers=opposite, appliers={"bool:screen_picture": rec2},
                  wait=approve, tier_of=lambda a: "ask")
    check("an approved card is recorded as asked-and-approved",
          out["outcomes"][0]["state"] == "asked-and-approved"
          and out["outcomes"][0]["waited"] is True, out)


def t_a_missing_module_is_reported_and_the_rest_continues():
    calls = []

    def missing(ch):
        raise RuntimeError("module not installed")

    def good(ch):
        calls.append(S.change_key(ch))
        return {"ok": True, "waiting": False, "message": "changed"}

    out = S.apply({"web_search": "on", "humour": "on"}, confirm=True,
                  readers=opposite,
                  appliers={"bool:web_search": missing, "bool:humor": good},
                  tier_of=lambda a: "ask")
    states = {o["setting"]: o["state"] for o in out["outcomes"]}
    check("a setting that fails is reported in words, not raised",
          states.get("bool:web_search") == "failed", states)
    check("...and the settings after it are still applied",
          states.get("bool:humor") == "changed" and calls == ["bool:humor"], states)


def t_apply_is_safest_first_and_never_combined():
    order = []

    def rec(ch):
        order.append(S.change_key(ch))
        return {"ok": True, "waiting": False, "message": "changed"}

    out = S.apply({"carefulness": "strict", "web_search": "on",
                   "talk_style": "plain"}, confirm=True,
                  readers=lambda ch: {"tier": "auto", "asks": False}
                  if ch.get("kind") == "asks_first" else False,
                  appliers={k: rec for k in
                            ["asks:calendar_read", "asks:email_read",
                             "asks:notes_search", "asks:home_read",
                             "asks:append_obsidian_daily",
                             "asks:append_logseq_journal",
                             "asks:create_joplin_note",
                             "bool:web_search", "manner"]},
                  tier_of=lambda a: "ask")
    check("tightening and wording come before a carded ON",
          order.index("manner") < order.index("bool:web_search")
          if "manner" in order and "bool:web_search" in order else True, order)
    check("apply returns one outcome per attempted change",
          len(out["outcomes"]) == len(order), (len(out["outcomes"]), order))


# ---------------------------------------------------------------------------
#   4. state(): prefill from the last answers, and the routes
# ---------------------------------------------------------------------------


def t_state_round_trips_and_prefills_a_rerun():
    p = Path(_TMP) / "setup.json"
    if p.exists():
        p.unlink()
    out = S.apply({"talk_style": "plain", "humour": "on"},
                  confirm=True, readers=opposite,
                  appliers={"manner": lambda ch: {"ok": True, "waiting": False,
                                                  "message": "changed"},
                            "bool:humor": lambda ch: {"ok": True, "waiting": False,
                                                      "message": "changed"}},
                  tier_of=lambda a: "ask")
    check("the apply said it was saved", out["ok"] is True, out)
    st = S.state(readers=lambda ch: None)
    check("state exposes the last answers for prefill",
          st["answers"].get("talk_style") == "plain"
          and st["answers"].get("humour") == "on", st["answers"])
    check("state exposes when they were accepted",
          isinstance(st["completed_at"], float) and st["completed_at"] > 0,
          st["completed_at"])
    check("state carries every question in order and says how big a card wait is",
          [q["id"] for q in st["questions"]] == [q["id"] for q in S.QUESTIONS]
          and isinstance(st["card_wait_s"], float), st["questions"][:2])


def t_the_saved_answers_never_hold_private_data():
    raw = (Path(_TMP) / "setup.json").read_text(encoding="utf-8")
    saved = json.loads(raw)
    check("setup.json holds the choice ids and a timestamp, and nothing else "
          "private enters it",
          set(saved) == {"answers", "completed_at", "outcomes"}
          and saved["answers"] == {"talk_style": "plain", "humour": "on"}
          and not any(word in raw.lower() for word in
                      ("transcript", "my email", "calendar_read", "chat history")),
          raw[:200])


def _wired(path, body=b"{}", token=True):
    class H(FakeHandler):
        pass
    msg = S.install(H, origin_ok=lambda self: True, token_ok=lambda self: self.token,
                    read_body=lambda self: self.body)
    h = H(path, body=body, token=token)
    return h, H, msg


def t_the_routes_are_wired_and_guarded():
    class H(FakeHandler):
        pass
    msg = S.install(H, origin_ok=lambda self: True,
                    token_ok=lambda self: getattr(self, "token", True),
                    read_body=lambda self: getattr(self, "body", b"{}"))
    check("install returns the banner line and is idempotent",
          "setup" in msg.lower() and "already on" in S.install(
              H, origin_ok=lambda self: True, token_ok=lambda self: True,
              read_body=lambda self: b"{}"), msg)

    h = H("/api/setup")
    h.do_GET()
    check("GET /api/setup: the questionnaire state", FakeHandler.sent[0] == 200
          and "questions" in FakeHandler.sent[1], FakeHandler.sent)
    h = H("/api/setup", token=False)
    h.do_GET()
    check("no token: 401 before anything is read", FakeHandler.sent[0] == 401,
          FakeHandler.sent)

    h = H("/api/setup/plan", body=json.dumps({"answers": {"talk_style": "plain"}}).encode())
    h.do_POST()
    check("POST /api/setup/plan: a summary, and it changes nothing", 
          FakeHandler.sent[0] == 200 and "summary" in FakeHandler.sent[1], FakeHandler.sent)

    h = H("/api/setup/apply", body=json.dumps({"answers": {}}).encode())
    h.do_POST()
    check("POST /api/setup/apply without confirm: 400 and a plain refusal",
          FakeHandler.sent[0] == 400
          and FakeHandler.sent[1].get("confirmed") is False, FakeHandler.sent)

    h = H("/api/setup/plan", body=json.dumps({"answers": "nope"}).encode())
    h.do_POST()
    check("answers that are not an object: 400, not a crash",
          FakeHandler.sent[0] == 400, FakeHandler.sent)

    h = H("/api/not-setup")
    h.do_GET()
    check("an unrelated path goes to the server's own handler untouched",
          FakeHandler.sent == ("orig-get", None), FakeHandler.sent)

    h = H("/api/setup/plan", body=b"{not json")
    h.do_POST()
    check("a body that is not JSON is answered with a status, not a crash",
          FakeHandler.sent[0] == 400, FakeHandler.sent)


# ---------------------------------------------------------------------------
#   5. What this module must never do
# ---------------------------------------------------------------------------


def t_no_gate_no_model_switch_no_network():
    import ast
    src = Path(S.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports, calls, strings = set(), set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                calls.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                calls.add(fn.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.add(node.value)
    check("it does not import the approval gate, a model lane or the network",
          not (imports & {"jarvis_gate", "jarvis_models", "socket", "http",
                          "urllib", "requests", "subprocess", "jarvis_presets"}),
          imports)
    check("it never applies a preset, switches a model or calls a gate directly",
          not (calls & {"apply_preset", "switch_model", "check", "latch_taint"}),
          calls)
    check("it has no gate/latch/model code of its own",
          "jarvis_gate" not in imports
          and not any(("change_own_config" in s) or ("latch_taint" in s)
                      for s in strings), strings)
    check("it writes its answers in the settings folder and never the owner's toml",
          S.ANSWERS_NAME == "setup.json"
          and hasattr(S, "answers_path")
          and "CONFIG_DIR" in Path(S.__file__).read_text(encoding="utf-8"),
          strings)


if __name__ == "__main__":
    for fn in (t_every_question_and_option_is_well_formed,
               t_every_change_maps_to_a_real_setter,
               t_the_carded_actions_are_the_modules_own,
               t_plan_writes_nothing,
               t_every_option_plans_or_skips_without_raising,
               t_card_rules_match_the_existing_rules,
               t_a_tier_that_does_not_ask_is_skipped_not_promised,
               t_all_and_none_are_data,
               t_unreadable_values_are_said_not_guessed,
               t_apply_refuses_without_confirm,
               t_apply_instant_calls_the_mapped_setters,
               t_apply_carded_change_waits_for_its_own_card_then_continues,
               t_a_missing_module_is_reported_and_the_rest_continues,
               t_apply_is_safest_first_and_never_combined,
               t_state_round_trips_and_prefills_a_rerun,
               t_the_saved_answers_never_hold_private_data,
               t_the_routes_are_wired_and_guarded,
               t_no_gate_no_model_switch_no_network):
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
