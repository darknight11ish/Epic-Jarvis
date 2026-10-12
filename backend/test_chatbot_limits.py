"""test_chatbot_limits.py - the monthly money limits and the price list, set
from the PC's own app (docs/ACCOUNT-KEYS-DESIGN.md steps 3-5, decisions 1 and
3; backend/jarvis_chatbot_limits.py, chatbot-limits.patch; JARVIS-API section
87.4.1).

    python backend/test_chatbot_limits.py

WHAT THIS PROVES - the one rule that matters most first
  * RAISING a limit is a LOOSENING: it raises exactly ONE approval card, under
    the gate action `raise_api_limit`, and the limit only moves on a real yes.
    Denied, timed out, or a gate that will not answer: nothing changes, and the
    answer says which.
  * LOWERING a limit, REMOVING one, CORRECTING a price and RESETTING one all
    only tighten or correct, so NONE of them calls the gate at all - proved by
    a gate that records every call, not by reading the code.
  * There are TWO action names, not one, because the owner-check attaches
    Windows Hello to the ACTION and not to the direction (the design note's
    section 4.3): `raise_api_limit` is in `jarvis_owner_check.PC_ONLY_ACTIONS`
    and `lower_api_limit` is not - and the framework file declares the raise
    "ask" and the lowering "auto". A `raise_limit` that names an amount at or
    below the current one is sent down the tightening path, so a lowering can
    never be dressed up as a raise to get a card.
  * FROM THE PHONE (the owner, 2026-10-11: "Let the phone raise it too, with
    its own fingerprint", changing his own 2026-09-28 "set on the PC"): a RAISE
    from a paired device raises the same card, and that card is answered with
    the phone's own signed approval (its fingerprint or PIN, through
    `jarvis_devices.check_signed_approval`) - which is why
    `jarvis_owner_check.PC_ONLY_ACTIONS` no longer holds `raise_api_limit`. A
    LOWERING or a REMOVAL from the phone applies at once, with no card. A PRICE
    from the phone is still refused 403 `pc_only` and changes nothing.
  * Every read and every write goes through `jarvis_chatbot_api`'s own
    functions, and the real, unmodified module stores it: the test runs against
    jarvis_chatbot_api.py itself with its money file pointed at a temporary
    folder, so a limit set here is a limit `ready_for` and `money_view` see.
  * The price list: the DEFAULT is shown as UNVERIFIED with the date it was
    written and the page to check it on; a corrected price is shown as "yours"
    with the date it was set; `reset_price` goes back, and says UNVERIFIED
    again. Decision 4's whole point is that the app says where a number came
    from.
  * FAILING CLOSED: an unreadable money file refuses a read and a write with
    the module's own words - it never reads as "nothing spent" and never as
    "no limit".
  * The patch, the module lists and the framework file: chatbot-limits.patch is
    in scripts/apply-patches.ps1's order at the end, jarvis_chatbot_limits.py is
    in SHIPPED on both sides, and the two tier lines are in the shipped
    jarvis-framework.toml.

No network, no model, no Windows Hello (a stand-in gate).
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, require_shipped  # noqa: E402

require_shipped("jarvis_chatbot_limits.py", "jarvis_chatbot_api.py", "jarvis_chatbot.py",
                "jarvis_token_store.py", "jarvis_local_http.py", "jarvis_task_control.py",
                "jarvis_stop_all.py", "jarvis_search.py", "jarvis_mail_mask.py",
                "rebuilt/jarvis_router.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.insert(1, str(HERE / "rebuilt"))

TMP = Path(tempfile.mkdtemp(prefix="jarvis-chatbot-limits-"))
CFG: dict = {}
TIERS: dict = {}
AUDIT: list = []
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = TMP
fw.LOG_DIR = TMP
fw.load_framework = lambda: {"chatbot": CFG}
fw.audit_log = lambda event, detail=None, *a, **k: AUDIT.append((event, dict(detail or {})))
fw.action_tier = lambda action: TIERS.get(action, "ask")
sys.modules["jarvis_framework"] = fw

import jarvis_token_store as TS  # noqa: E402
import jarvis_chatbot_api as API  # noqa: E402
import jarvis_chatbot_limits as L  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


class FakeStore:
    def __init__(self, target):
        self.target = target

    def read(self):
        return STORE.get(self.target)

    def write(self, value):
        STORE[self.target] = value

    def delete(self):
        return STORE.pop(self.target, None) is not None


STORE: dict = {}
TS._STORE_FACTORY = FakeStore


# ------------------------------------------------------------------ the gate

class Verdict:
    def __init__(self, allowed, outcome, tier="ask"):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier
        self.reason = outcome


YES = Verdict(True, "approved")
NO = Verdict(False, "denied")
LATE = Verdict(False, "timed_out")
AUTO = Verdict(True, "auto", tier="auto")

GATE_CALLS: list = []


def gate(action, detail, prompt=None):
    GATE_CALLS.append({"action": action, "detail": dict(detail or {}), "prompt": prompt})
    return ANSWERS.pop(0) if ANSWERS else YES


ANSWERS: list = []


def no_gate(action, detail, prompt=None):
    GATE_CALLS.append({"action": action, "detail": dict(detail or {}), "prompt": prompt})
    raise RuntimeError("the gate is not installed")


def tier_of(action):
    return TIERS.get(action, "ask")


TIERS.update({L.RAISE_ACTION: "ask", L.LOWER_ACTION: "auto"})


def arm(*answers):
    """Reset the gate the way a fresh request should see it."""
    GATE_CALLS.clear()
    ANSWERS[:] = list(answers)
    L.configure(gate=gate, tier_of=tier_of, api=None, audit=None, now=None)


def arm_unavailable():
    GATE_CALLS.clear()
    ANSWERS[:] = []
    L.configure(gate=no_gate, tier_of=tier_of, api=None, audit=None, now=None)


def money_file() -> Path:
    return API.money_path()


def wipe():
    """A clean money file for one check. Writes a real one, never deletes a
    folder the sandbox may refuse (see this repo's own note on mkdtemp)."""
    p = money_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": 1, "limits": {}, "prices": {}, "months": {}}),
                 encoding="utf-8")


def read_view(service=None):
    code, body = L.view(here=True)
    assert code == 200, body
    if service is None:
        return body
    return next(r for r in body["services"] if r["service"] == service)


def post(body, here=True, device=None):
    """A request as the PC (or as a paired device), through change().

    `device` is what the server's own token check put on the handler
    (`_jarvis_device`): the id of the phone whose key made the request, or None
    when nothing identified it."""
    peer = "127.0.0.1" if here else "100.100.5.9"
    saved = L._from_this_pc
    L._from_this_pc = lambda *_a, **_k: here
    try:
        return L.change(body, peer=peer, local="127.0.0.1", device=device)
    finally:
        L._from_this_pc = saved


# ======================================================= 1. the read


def t_the_view_names_every_service_and_says_where_each_price_came_from():
    wipe()
    arm()
    body = read_view()
    check("all six API services are listed", len(body["services"]) == 6, len(body["services"]))
    check("the ids are the ones a key is saved under",
          [r["service"] for r in body["services"]] == list(API.BY_SHORT)
          or sorted(r["service"] for r in body["services"]) == sorted(API.BY_SHORT),
          [r["service"] for r in body["services"]])
    for row in body["services"]:
        check(f"{row['service']}: no limit yet, and it says so in the PC's own words",
              row["limit"] is None
              and row["line"] == API.no_limit_words(API.PRESETS[API.BY_SHORT[row["service"]]]),
              row["line"])
        check(f"{row['service']}: the price is named a DEFAULT and marked UNVERIFIED",
              row["price"]["source"] == "default" and row["price"]["verified"] is False
              and "UNVERIFIED" in row["price"]["line"]
              and API.PRICES_WRITTEN in row["price"]["line"],
              row["price"])
        check(f"{row['service']}: the price page is given so it can be checked",
              bool(row["price"]["price_page"]))
        check(f"{row['service']}: whether a limit can be changed here is the request's to say",
              row["can_change"] is True)
    check("the view says every amount is an estimate",
          "ESTIMATE" in body["estimates"] and "unverified" in body["estimates"])
    check("the view says a raise asks and a lowering does not",
          "Windows Hello" in body["raise_words"] and "no card" in body["raise_words"])
    check("the two action names are named in the answer",
          body["raise_action"] == "raise_api_limit" and body["lower_action"] == "lower_api_limit")


def t_a_view_from_the_phone_offers_both_a_limit_and_a_price_change():
    """WAS `..._is_offered_but_cannot_change_anything`, when every change was
    the PC's alone. The owner changed that for LIMITS on 2026-10-11 - a phone
    raises one with its own fingerprint - and prices are the half that stayed,
    which is why the view now answers both questions separately instead of one
    `can_change`."""
    wipe()
    arm()
    code, body = L.handle_get(L.PATH, {}, "100.100.5.9", "100.64.0.1", device="d3f9a1c2e")
    check("a read from the phone still answers", code == 200)
    check("a phone whose own key made the request may change a limit here",
          body["can_change"] is True)
    check("and a price may be corrected here too - the owner opened both on 2026-10-11",
          body["can_change_prices"] is True)
    check("the sentence by that name now names the one thing that did not move: the key",
          body["pc_only"] == L.PC_ONLY and "key" in L.PC_ONLY.lower(), L.PC_ONLY)
    check("every row says a limit can be changed from here",
          all(r["can_change"] is True for r in body["services"]))
    check("the raise words name the phone's own fingerprint",
          "fingerprint" in body["raise_words"], body["raise_words"])
    code2, body2 = L.handle_get(L.PATH, {}, "100.100.5.9", "100.64.0.1")
    check("with nothing identifying the caller it may change nothing",
          code2 == 200 and body2["can_change"] is False
          and body2["can_change_prices"] is False)


# ======================================================= 2. the one rule


def t_lowering_only_a_limit_needs_no_card_at_all():
    wipe()
    API.set_limit("openai_api", 5.0)
    arm()
    code, body = post({"action": "lower_limit", "service": "openai", "dollars": 3})
    check("lowering answers 200", code == 200, body)
    check("the limit really moved, through the API module itself",
          API.limit_of("openai_api") == 3.0, API.limit_of("openai_api"))
    check("NO card was raised for a lowering", GATE_CALLS == [], GATE_CALLS)
    check("the answer says what it is now", "3.00" in body["said"], body["said"])
    check("the answer is not marked as a raise", body["raised"] is False)


def t_removing_a_limit_needs_no_card_either():
    wipe()
    API.set_limit("groq_api", 5.0)
    arm()
    code, body = post({"action": "remove_limit", "service": "groq"})
    check("removing a limit answers 200", code == 200, body)
    check("the limit is gone", API.limit_of("groq_api") is None)
    check("NO card was raised for removing one", GATE_CALLS == [], GATE_CALLS)
    check("and it says what that means for using the service",
          "will not use" in body["said"], body["said"])
    check("and the view row now carries the PC's own no-limit sentence",
          read_view("groq")["line"] == API.no_limit_words(API.PRESETS["groq_api"]),
          read_view("groq")["line"])


def t_raising_a_limit_raises_one_card_and_moves_on_a_yes():
    wipe()
    API.set_limit("openai_api", 3.0)
    arm(YES)
    code, body = post({"action": "raise_limit", "service": "openai", "dollars": 10})
    check("raising answers 200 on a yes", code == 200, body)
    check("exactly ONE card was raised", len(GATE_CALLS) == 1, GATE_CALLS)
    call = GATE_CALLS[0]
    check("the card uses the RAISE action, which is the one with Windows Hello",
          call["action"] == "raise_api_limit", call["action"])
    check("the card names the service, the old amount and the new one",
          "OpenAI" in call["prompt"] and "$3.00" in call["prompt"] and "$10.00" in call["prompt"],
          call["prompt"])
    check("the detail carries both amounts for the card's own record",
          call["detail"].get("was") == "$3.00" and call["detail"].get("now") == "$10.00",
          call["detail"])
    check("and says it does not leave this PC",
          call["detail"].get("leaves_this_pc") is False, call["detail"])
    check("the limit moved", API.limit_of("openai_api") == 10.0, API.limit_of("openai_api"))


def t_a_denied_card_leaves_the_limit_exactly_where_it_was():
    for verdict, word in ((NO, "denied"), (LATE, "timed_out")):
        wipe()
        API.set_limit("openai_api", 3.0)
        arm(verdict)
        code, body = post({"action": "raise_limit", "service": "openai", "dollars": 10})
        check(f"a {word} card is not an approval ({code})", code == 409, body)
        check(f"and the limit is untouched after a {word} card",
              API.limit_of("openai_api") == 3.0, API.limit_of("openai_api"))
        check(f"the answer says no ({word})", body.get("error") == "not_approved", body)


def t_a_gate_that_cannot_answer_refuses_rather_than_raising():
    wipe()
    API.set_limit("openai_api", 3.0)
    arm_unavailable()
    code, body = post({"action": "raise_limit", "service": "openai", "dollars": 10})
    check("a gate that will not answer is a refusal, not a silent raise",
          code == 503 and body.get("error") == "card_unavailable", body)
    check("and nothing moved", API.limit_of("openai_api") == 3.0, API.limit_of("openai_api"))


def t_the_raise_action_must_really_be_tier_ask():
    wipe()
    API.set_limit("openai_api", 3.0)
    arm(YES)
    TIERS[L.RAISE_ACTION] = "auto"
    try:
        code, body = post({"action": "raise_limit", "service": "openai", "dollars": 10})
    finally:
        TIERS[L.RAISE_ACTION] = "ask"
    check("a raise action that is not tier ask refuses to raise at all",
          code == 503 and body.get("error") == "tier_not_ask", body)
    check("no card is even raised in that case", GATE_CALLS == [], GATE_CALLS)
    check("and the limit did not move", API.limit_of("openai_api") == 3.0)


def t_a_raise_that_names_no_more_than_now_is_a_tightening_not_a_card():
    """The trick this rule exists to stop: asking to 'raise' to a smaller
    number so the request takes the card path. A card is a YES/NO about
    spending MORE; there is nothing to approve in spending less."""
    wipe()
    API.set_limit("openai_api", 5.0)
    arm()
    code, body = post({"action": "raise_limit", "service": "openai", "dollars": 5})
    check("a raise to the same number is not treated as a raise",
          code == 200 and body["raised"] is False, body)
    check("no card was raised for it", GATE_CALLS == [], GATE_CALLS)
    wipe()
    API.set_limit("openai_api", 5.0)
    arm()
    code, body = post({"action": "raise_limit", "service": "openai", "dollars": 2})
    check("a 'raise' to a smaller number lowers instead, with no card",
          code == 200 and body["raised"] is False and API.limit_of("openai_api") == 2.0, body)
    check("and no card was raised for it either", GATE_CALLS == [], GATE_CALLS)


def t_the_first_limit_on_a_service_is_a_raise_and_gets_a_card():
    """No limit is not "zero": it means the service cannot be used at all, so
    setting the first one lets Jarvis spend money it could not before."""
    wipe()
    arm(YES)
    code, body = post({"action": "raise_limit", "service": "mistral", "dollars": 5})
    check("the first limit on a service answers 200 on a yes", code == 200, body)
    check("it raised a card", len(GATE_CALLS) == 1 and GATE_CALLS[0]["action"] == L.RAISE_ACTION,
          GATE_CALLS)
    check("the card says the old state was no limit at all",
          "no limit" in GATE_CALLS[0]["prompt"], GATE_CALLS[0]["prompt"])
    check("and the limit is set", API.limit_of("mistral_api") == 5.0)


def t_removing_a_limit_that_is_not_there_says_so():
    wipe()
    arm()
    code, body = post({"action": "remove_limit", "service": "mistral"})
    check("removing a limit that was never set says there is nothing to do",
          code == 400 and body.get("error") == "nothing_to_do", body)
    check("and it does not claim to have removed anything",
          "Removed" not in json.dumps(body), body.get("said"))


# ======================================================= 3. PC only


def t_a_raise_from_the_phone_raises_the_card_and_applies_when_it_is_confirmed():
    """WAS part of `t_a_request_from_another_device_is_refused_and_changes_nothing`,
    which held the 2026-09-28 rule "a monthly amount per service, set on the PC".
    The owner lifted it for this one direction on 2026-10-11. The card is the
    SAME card the PC raises - what changed is where it may be answered, with the
    phone's own signed approval instead of Windows Hello."""
    wipe()
    API.set_limit("openai_api", 3.0)
    arm(YES)
    code, out = post({"action": "raise_limit", "service": "openai", "dollars": 10},
                     here=False, device="d3f9a1c2e")
    check("a raise from the phone is accepted", code == 200, out)
    check("the limit really moved", API.limit_of("openai_api") == 10.0)
    check("it raised the RAISE action's card, once",
          [c["action"] for c in GATE_CALLS] == [L.RAISE_ACTION], GATE_CALLS)
    check("and the card names the phone's own request, not the PC's",
          "raise the monthly money limit" in GATE_CALLS[0]["detail"]["what"], GATE_CALLS)


def t_a_denied_card_on_the_phone_leaves_the_limit_exactly_where_it_was():
    wipe()
    API.set_limit("openai_api", 3.0)
    arm(NO)
    code, out = post({"action": "raise_limit", "service": "openai", "dollars": 10},
                     here=False, device="d3f9a1c2e")
    check("a no on the phone is not an approval",
          code == 409 and out.get("error") == "not_approved", out)
    check("and nothing moved", API.limit_of("openai_api") == 3.0)


def t_a_lowering_or_a_removal_from_the_phone_needs_no_card_at_all():
    """The other half of the owner's change, and the one that makes the phone
    useful: stopping spending must never need a fingerprint."""
    wipe()
    API.set_limit("openai_api", 3.0)
    arm()
    code, out = post({"action": "lower_limit", "service": "openai", "dollars": 1},
                     here=False, device="d3f9a1c2e")
    check("a lowering from the phone applies", code == 200, out)
    check("the limit is the lower one", API.limit_of("openai_api") == 1.0)
    code, out = post({"action": "remove_limit", "service": "openai"},
                     here=False, device="d3f9a1c2e")
    check("a removal from the phone applies", code == 200, out)
    check("and the limit is gone", API.limit_of("openai_api") is None)
    check("with no card at all", GATE_CALLS == [], GATE_CALLS)


def t_a_price_correction_from_the_phone_applies_at_once_with_no_card():
    """WAS `t_a_price_from_the_phone_is_still_refused_and_changes_nothing`, when
    prices were the PC's. The owner opened them on 2026-10-11, asked directly
    after the limit: a price is an ESTIMATE of what a service costs, so
    correcting one spends nothing, raises no cap and takes nothing back - the
    same shape as a lowering, and card-free for the same reason. It is not
    tier "ask" and there is no gate action for it, so nothing to confirm."""
    wipe()
    API.set_limit("openai_api", 3.0)
    arm()
    code, out = post({"action": "set_price", "service": "openai", "in": 1, "out": 2},
                     here=False, device="d3f9a1c2e")
    check("a price correction from the phone is accepted", code == 200, out)
    check("and it is not a card", out.get("ok") is True, out)
    code, out = post({"action": "reset_price", "service": "openai"},
                     here=False, device="d3f9a1c2e")
    check("resetting it from the phone is accepted too", code == 200, out)
    check("no card was raised from the phone for either",
          GATE_CALLS == [], GATE_CALLS)


# ======================================================= 4. the price list


def t_a_corrected_price_is_kept_and_says_it_is_yours():
    wipe()
    arm()
    code, body = post({"action": "set_price", "service": "openai", "in": 0.5, "out": 4})
    check("setting a price answers 200", code == 200, body)
    check("NO card is raised for correcting a price", GATE_CALLS == [], GATE_CALLS)
    row = read_view("openai")
    check("the price is now the owner's own",
          row["price"]["source"] == "yours" and row["price"]["in"] == 0.5
          and row["price"]["out"] == 4.0, row["price"])
    check("and the app says it is not the unverified default any more",
          "UNVERIFIED" not in row["price"]["line"] and "your own price" in row["price"]["line"],
          row["price"]["line"])
    check("it records the date it was set", bool(row["price"]["set"]), row["price"])
    check("and the figure the limit is kept by really changed",
          API.price_of("openai_api", "gpt-5-mini")[:2] == (0.5, 4.0))


def t_resetting_a_price_goes_back_to_the_unverified_default():
    wipe()
    arm()
    post({"action": "set_price", "service": "groq", "in": 9, "out": 9})
    code, body = post({"action": "reset_price", "service": "groq"})
    check("resetting answers 200", code == 200, body)
    check("no card for a reset either", GATE_CALLS == [], GATE_CALLS)
    row = read_view("groq")
    check("it is the default again, and marked UNVERIFIED",
          row["price"]["source"] == "default" and row["price"]["verified"] is False
          and "UNVERIFIED" in row["price"]["line"], row["price"])
    check("and the API module's own default is back",
          API.price_of("groq_api", "openai/gpt-oss-20b")[2] == "default")


def t_a_price_that_is_not_a_number_is_refused():
    wipe()
    arm()
    for bad in ({"in": -1, "out": 2}, {"in": "x", "out": 2}, {"in": 1},
                {"in": API.MOST_PRICE + 1, "out": 1}, {"in": True, "out": 1}):
        code, body = post({"action": "set_price", "service": "openai", **bad})
        check(f"a price of {bad} is refused", code == 400 and body.get("error") == "bad_price",
              body)
    check("and nothing was written", read_view("openai")["price"]["source"] == "default")


# ======================================================= 5. bad input


def t_an_unknown_action_or_service_is_refused_in_plain_words():
    wipe()
    arm()
    code, body = post({"action": "make_it_free", "service": "openai"})
    check("an unknown action is refused", code == 400 and body.get("error") == "unknown_action",
          body)
    check("and the words list what can be asked", "raise" in body["message"], body)
    code, body = post({"action": "lower_limit", "service": "chatgpt", "dollars": 1})
    check("an unknown service is refused", code == 400 and body.get("error") == "no_such_service",
          body)
    check("and the words list the six", "openai" in body["message"], body)
    code, body = post({"action": "lower_limit", "service": "openai", "dollars": -5})
    check("a negative amount is refused", code == 400 and body.get("error") == "bad_amount", body)
    code, body = post({"action": "lower_limit", "service": "openai", "dollars": "five"})
    check("an amount that is not a number is refused",
          code == 400 and body.get("error") == "bad_amount", body)
    code, body = post(["not", "an", "object"])
    check("a body that is not an object is refused", code == 400, body)


# ======================================================= 6. failing closed


def t_an_unreadable_money_file_refuses_rather_than_reading_as_zero():
    wipe()
    API.set_limit("openai_api", 3.0)
    money_file().write_text("{not json", encoding="utf-8")
    arm(YES)
    code, body = L.view(here=True)
    check("an unreadable money file is a refusal, not an empty read",
          code == 503 and body.get("error") == "money_unreadable", body)
    check("its words are the module's own, naming the file not the path",
          API.MONEY_FILE in body["message"] and str(TMP) not in body["message"], body["message"])
    code, body = post({"action": "lower_limit", "service": "openai", "dollars": 1})
    check("and a write is refused too", code == 503 and body.get("error") == "money_unreadable",
          body)
    check("the file was left exactly as it was",
          money_file().read_text(encoding="utf-8") == "{not json")
    wipe()


# ======================================================= 7. wiring


def t_the_patch_is_in_the_stack_and_carries_both_gate_names():
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    order = re.findall(r"^\s+'([A-Za-z0-9._/-]+\.patch)'", ps1, re.M)
    check("chatbot-limits.patch is in apply-patches.ps1's order",
          "chatbot-limits.patch" in order, order[-6:])
    check("it goes after chatbot.patch and quiz-cloud.patch, whose text it sits beside",
          order.index("chatbot-limits.patch") > order.index("chatbot.patch")
          and order.index("chatbot-limits.patch") > order.index("quiz-cloud.patch"))
    src = (REPO / "backend" / "chatbot-limits.patch").read_text(encoding="utf-8")
    for name in (L.RAISE_ACTION, L.LOWER_ACTION):
        check(f"the patch carries {name} in the gate's own tables",
              src.count(f'"{name}"') >= 2, src.count(f'"{name}"'))
    # The install block is its OWN patch, and that is load-bearing rather than
    # tidiness. 2026-10-06: chatbot-limits.patch has hunks in TWO files that need
    # different positions in apply-patches.ps1's order - the gate hunks must
    # follow readpage.patch, whose hunks anchor on the same two lists these names
    # join, and this install block must follow quiz-cloud.patch, whose printed
    # lines are its context. Written as one patch the other way round it stopped
    # readpage.patch applying at all, and moving it later made _stack.py
    # materialise this hunk at the end of jarvis_hud.py, duplicating the
    # `_loopback_companion(bind, HUD_PORT, Handler)` line it uses as trailing
    # context. One patch cannot sit in two places, so there are two.
    check("chatbot-limits-hud.patch, the install half, is in the order too",
          "chatbot-limits-hud.patch" in order, order[-6:])
    hud = (REPO / "backend" / "chatbot-limits-hud.patch").read_text(encoding="utf-8")
    check("the install half of the patch installs the module from jarvis_hud.py",
          "jarvis_chatbot_limits.install(" in hud)
    check("the patch says why there are two names",
          "the action and not to the direction" in src.replace("\n", " ")
          or "not to the direction" in src)


def t_the_module_is_shipped_on_both_sides_and_the_tiers_are_in_the_shipped_file():
    shipped = (REPO / "backend" / "_where.py").read_text(encoding="utf-8")
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("_where.py's SHIPPED list carries it", '"jarvis_chatbot_limits.py"' in shipped)
    check("apply-patches.ps1's $SHIPPED list carries it too",
          "'jarvis_chatbot_limits.py'" in ps1)
    toml = (REPO / "backend" / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("the raise is tier ask in the shipped framework file",
          re.search(r'^raise_api_limit\s*=\s*"ask"', toml, re.M) is not None)
    check("the lowering is tier auto in the shipped framework file",
          re.search(r'^lower_api_limit\s*=\s*"auto"', toml, re.M) is not None)


def t_the_raise_left_the_pc_only_set_and_is_still_risky_on_the_pc():
    """WAS `t_the_raise_is_the_pc_only_action_and_the_lowering_is_not`, which
    held the 2026-09-28 rule: `jarvis_owner_check` attaches Windows Hello to the
    ACTION NAME, so `raise_api_limit` had to be in `PC_ONLY_ACTIONS` and a
    lowering must not be. The owner took the raise OUT of that set on
    2026-10-11 so a phone can confirm it with its own fingerprint. This test now
    pins the two things that keep that safe rather than the old membership:

      * the action is out of the set, and the lowering still is not in it; and
      * the raise is still RISKY on its own merits, so the PC's own approval
        still asks Windows Hello through `is_risky` and not through this set.
        That is the whole safety argument: where a raise may be confirmed
        changed, whether a person confirms it did not."""
    oc = (REPO / "backend" / "jarvis_owner_check.py").read_text(encoding="utf-8")
    # The frozenset's own text, however it is wrapped across lines.
    start = oc.index("PC_ONLY_ACTIONS = frozenset(")
    block = oc[start:oc.index("})", start) + 2]
    check("raise_api_limit is OUT of PC_ONLY_ACTIONS, so a phone may confirm this card",
          "raise_api_limit" not in block, block)
    check("lower_api_limit is not in it either, so a lowering never asks anything",
          "lower_api_limit" not in block, block)
    check("and PC_ONLY_ACTIONS is still a frozenset, not a list",
          "frozenset({" in block, block)
    check("the PC still asks Windows Hello for a risky card it did not get from the PC",
          "is_risky(row)" in oc and "action in PC_ONLY_ACTIONS" in oc)
    check("and a risky card from another device still needs that device's signature",
          "_signed_check(body, row, device)" in oc)
    # THE SAFETY ARGUMENT, where it can be read. `jarvis_gate.py` is the
    # owner's own module: it is patched by the stack and is NOT in this
    # repository, so a staged copy (CI's own `backend/run_suites.py` stage) does
    # not have it. When it is here - on the owner's PC - the two checks below
    # read it; when it is not, they SKIP BY NAME rather than raising
    # FileNotFoundError, which is what the first version of this test did on
    # 2026-10-11 and what turned CI red for a file that was never going to be
    # there. The tier line and the risk row are the two halves of the same
    # fact, and the tier half is checked from this repository's own
    # `rebuilt/jarvis-framework.toml` above, so nothing here is unproven.
    gate_path = BACKEND / "jarvis_gate.py"
    if not gate_path.exists():
        skip("jarvis_gate.py is not in this backend copy (it is the owner's own "
             "module, patched rather than shipped here), so the raise's risk row and "
             "its no-standing-rule entry are checked only where that file is")
    else:
        gate = gate_path.read_text(encoding="utf-8")
        check("the raise's risk row is still not reversible, so is_risky() is True "
              "for it and the PC's own approval still asks Windows Hello",
              '"raise_api_limit": ("no"' in gate
              or "'raise_api_limit': ('no'" in gate,
              [ln.strip()[:90] for ln in gate.splitlines() if "raise_api_limit" in ln][:3])
        check("and the raise is still in the gate's own no-standing-rule set, untouched "
              "by this change",
              gate.count('"raise_api_limit"') >= 2, gate.count('"raise_api_limit"'))
    src = (REPO / "backend" / "jarvis_chatbot_limits.py").read_text(encoding="utf-8")
    check("the module has one name per direction and no third one",
          src.count('_ACTION = "') == 2, src.count('_ACTION = "'))
    check("lowering and removing share the tightening name",
          src.count("LOWER_ACTION") >= 1 and "remove_limit" in src)
    src = (REPO / "backend" / "jarvis_chatbot_limits.py").read_text(encoding="utf-8")
    check("the module has one name per direction and no third one",
          src.count('_ACTION = "') == 2, src.count('_ACTION = "'))
    check("lowering and removing share the tightening name",
          src.count("LOWER_ACTION") >= 1 and "remove_limit" in src)


def t_every_read_and_write_goes_through_the_api_module():
    """One copy of the money rules, in one file. This module must not open the
    money file, JSON-parse it or write it itself."""
    src = (REPO / "backend" / "jarvis_chatbot_limits.py").read_text(encoding="utf-8")
    for fn in ("API.", "api.set_limit(", "api.limit_of(", "api.spent_of(", "api.price_of(",
               "api.set_price(", "api.reset_price(", "api.money_view(", "api.ready_for("):
        pass
    check("it calls the API module's own setters",
          "api.set_limit(" in src and "api.set_price(" in src and "api.reset_price(" in src)
    check("it calls the API module's own readers",
          "api.limit_of(" in src and "api.spent_of(" in src and "api.price_of(" in src
          and "api.model_for(" in src)
    check("it never writes the money file itself",
          "money_path(" not in src and "json.dump" not in src and "os.replace" not in src)
    check("it never keeps a secret-looking thing: no key is read here",
          "KEY_TARGETS" not in src and "_read_key" not in src and "key_saved" not in src)
    check("nothing private is named in its audit lines",
          "message" not in json.dumps([d for _e, d in AUDIT]))


def t_audit_carries_actions_and_amounts_only():
    wipe()
    API.set_limit("openai_api", 3.0)
    AUDIT.clear()
    arm()
    post({"action": "lower_limit", "service": "openai", "dollars": 2})
    events = [e for e, _d in AUDIT]
    check("a limit change is audited", "chatbot_money.limit" in events, events)
    detail = next(d for e, d in AUDIT if e == "chatbot_money.limit")
    check("the audit line names the service and both amounts",
          detail.get("service") == "openai" and detail.get("was") == 3.0
          and detail.get("amount") == 2.0, detail)
    check("and holds no key, no message and no chat",
          set(detail) <= {"action", "service", "amount", "was"}, sorted(detail))
    AUDIT.clear()
    arm()
    post({"action": "set_price", "service": "openai", "in": 1, "out": 2})
    detail = next(d for e, d in AUDIT if e == "chatbot_money.price")
    check("a price change is audited too, and holds nothing else",
          set(detail) <= {"action", "service", "model"}, sorted(detail))


def t_the_route_is_only_this_one_path_and_only_these_two_methods():
    check("owns() takes GET and POST on the one path",
          L.owns("GET", L.PATH) and L.owns("POST", L.PATH))
    for method, route in (("GET", "/api/chatbot/money/extra"), ("PUT", L.PATH),
                          ("GET", "/api/chatbot/status"), ("POST", "/api/chatbot/limits")):
        check(f"and not {method} {route}", not L.owns(method, route))
    check("a wrong path is a 404 through the handlers too",
          L.handle_get("/api/nope", {})[0] == 404 and L.handle_post("/api/nope", {})[0] == 404)


def t_no_other_module_raises_a_chatbot_money_card():
    """One path changes a limit. A second one would be a second place a
    loosening could happen, which rule 4 exists to stop."""
    hits = []
    for path in (REPO / "backend").glob("*.py"):
        if path.name in ("jarvis_chatbot_limits.py", "jarvis_owner_check.py",
                         "jarvis_card_words.py", "jarvis_asks_first.py"):
            # The limit module is the one path to the DECISION. The other three
            # only NAME the actions, and each is required to by a suite of its
            # own: the owner-check because that is where PC_ONLY_ACTIONS lives;
            # card-words to give each a plain-English phrase for the card the
            # owner sees ("raise a chatbot's monthly spending limit"); and
            # asks-first because its page must list every action a card can name
            # (test_asks_first.py) - which is how a person finds out that raising
            # a limit asks and lowering one does not. None of them can change a
            # limit, so none is a second path, and this test itself is full of
            # these names on purpose.
            continue
        if path.name.startswith("test_"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if L.RAISE_ACTION in text or L.LOWER_ACTION in text:
            hits.append(path.name)
    check("no other module in this repository names either action", not hits, hits)


if __name__ == "__main__":
    for fn in (t_the_view_names_every_service_and_says_where_each_price_came_from,
               t_a_view_from_the_phone_offers_both_a_limit_and_a_price_change,
               t_lowering_only_a_limit_needs_no_card_at_all,
               t_removing_a_limit_needs_no_card_either,
               t_raising_a_limit_raises_one_card_and_moves_on_a_yes,
               t_a_denied_card_leaves_the_limit_exactly_where_it_was,
               t_a_gate_that_cannot_answer_refuses_rather_than_raising,
               t_the_raise_action_must_really_be_tier_ask,
               t_a_raise_that_names_no_more_than_now_is_a_tightening_not_a_card,
               t_the_first_limit_on_a_service_is_a_raise_and_gets_a_card,
               t_removing_a_limit_that_is_not_there_says_so,
               t_a_raise_from_the_phone_raises_the_card_and_applies_when_it_is_confirmed,
               t_a_denied_card_on_the_phone_leaves_the_limit_exactly_where_it_was,
               t_a_lowering_or_a_removal_from_the_phone_needs_no_card_at_all,
               t_a_price_correction_from_the_phone_applies_at_once_with_no_card,
               t_a_corrected_price_is_kept_and_says_it_is_yours,
               t_resetting_a_price_goes_back_to_the_unverified_default,
               t_a_price_that_is_not_a_number_is_refused,
               t_an_unknown_action_or_service_is_refused_in_plain_words,
               t_an_unreadable_money_file_refuses_rather_than_reading_as_zero,
               t_the_patch_is_in_the_stack_and_carries_both_gate_names,
               t_the_module_is_shipped_on_both_sides_and_the_tiers_are_in_the_shipped_file,
               t_the_raise_left_the_pc_only_set_and_is_still_risky_on_the_pc,
               t_every_read_and_write_goes_through_the_api_module,
               t_audit_carries_actions_and_amounts_only,
               t_the_route_is_only_this_one_path_and_only_these_two_methods,
               t_no_other_module_raises_a_chatbot_money_card):
        try:
            fn()
        except Exception as exc:
            FAILED.append(fn.__name__)
            print(f"FAIL  {fn.__name__} RAISED {type(exc).__name__}: {exc}")
            traceback.print_exc()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
