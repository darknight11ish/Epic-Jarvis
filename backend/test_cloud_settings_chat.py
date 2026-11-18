"""test_cloud_settings_chat.py - the hybrid/cloud settings, from chat.

    python -B backend/test_cloud_settings_chat.py

WHAT THIS PROVES, with the REAL jarvis_quick.py and jarvis_cloud_settings
over a TEMPORARY settings folder (never the owner's real files):

1. THE QUESTIONS are answered from the PC's own three files, in the owner's
   own words, and every answer names the file it read and when that file was
   last saved:
      "which cloud provider am I using?" / "am I on cloud?"
      "is escalation on?" / "will you send things to the cloud by yourself?"
      "what's my cap?" / "how much have I spent this month?"
      "what does escalation actually do?" (and what it still refuses:
      email, files, notes, credentials, stored memory)
   A missing file says "not set up" in plain words and what that means, never
   an empty or confident answer. No answer quotes a key or a fragment.
2. THE MATCHER IS NARROW. Existing doors keep their sentences ("which cloud
   providers are supported" is still the provider list, "are you using the
   cloud right now?" is still cloud_honesty, "how much did I spend last month"
   is still the spending door, "turn on cloud escalation" is still its own
   switch), and unrelated sentences are not captured.
3. THE CHANGES go through the doors that already exist, and nothing is
   written before a card's yes:
      * the standing switch ON raises exactly ONE `change_own_config` card and
        writes nothing when it is denied; OFF is instant and cardless (the
        existing rule); a question is never read as a change.
      * an unknown provider name is refused with the list read from
        `jarvis_chatbot_api.PRESETS`, raises no card and writes nothing.
      * a chosen provider goes through `jarvis_presets.apply_cloud`: ONE card,
        `cloud-choice.json` only after the yes.
      * the cap goes through `jarvis_chatbot_limits.change` (the door behind
        POST /api/chatbot/money): a raise over the current cap raises exactly
        ONE `raise_api_limit` card (tier ask) and writes nothing when denied;
        a lowering writes at once and raises no card.
4. NO KEY STORE. This module never reads Windows Credential Manager and never
   shows a key: it imports no key function and its files never hold a secret.

The gate, the key store's presence check and the money-file rules are the real
modules with their own functions monkeypatched, so the code paths under test are
the real ones - and the suite never reads the owner's real credentials.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
TMP = Path(tempfile.mkdtemp(prefix="jarvis-cloud-settings-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_SUITE_RUNNING"] = "1"
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""

import jarvis_chatbot_api as API  # noqa: E402
import jarvis_chatbot_limits as L  # noqa: E402
import jarvis_cloud_settings as CS  # noqa: E402
import jarvis_presets as P  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------------------
#   The temporary settings folder, and the real modules pointed at it
# ---------------------------------------------------------------------------

CHOICE = TMP / P.CLOUD_CHOICE_FILE
SWITCH = TMP / P.CLOUD_ESCALATE_FILE
MONEY = TMP / "chatbot" / "api-money.json"

P._config_dir = lambda: TMP
API.money_path = lambda: MONEY


def clean():
    """An empty settings folder: nothing chosen, nothing saved, no ledger.

    The key store is stood in for as well: `ready_for` is the one read that
    would otherwise touch Windows Credential Manager through the existing
    provider/cap routes' own view(), and this suite must never read the
    owner's real credentials."""
    for path in (CHOICE, SWITCH, MONEY):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    API.ready_for = lambda pid: ""
    L.configure(gate=None, tier_of=None, spawn=None, api=None, audit=None, now=None)
    P._gate = _real_gate


def write_json(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def money_doc(*, cap=10.0, months=None, service="deepseek_api"):
    return {"version": 1,
            "limits": ({} if cap is None else {service: cap}),
            "prices": {service: {"deepseek-flash": {"in": 0.3, "out": 1.2,
                                                    "set": "2026-10-31"}}},
            "months": months or {}}


class Verdict:
    """The shape jarvis_gate.check returns: allowed/outcome (and a tier)."""

    def __init__(self, allowed, outcome=None, tier="ask"):
        self.allowed = allowed
        self.outcome = outcome
        self.tier = tier


_real_gate = P._gate


def card_no(*_a, **_k):
    return Verdict(False, "denied")


def card_yes(*_a, **_k):
    return Verdict(True, "approved")


def say(sentence):
    """The whole fast-path answer the apps would get for one sentence."""
    got = Q.match(sentence, now=0)
    if got is None:
        return None, None
    return got.name, Q.answer(sentence, now=0, peer="127.0.0.1", local="127.0.0.1")


def words(sentence):
    name, res = say(sentence)
    if res is None:
        return None
    return res.reply


# ---------------------------------------------------------------------------
#   1. The questions, in the owner's own words, from the files
# ---------------------------------------------------------------------------

def t_provider_set_is_read_from_the_file_and_says_so():
    clean()
    write_json(CHOICE, {"provider": "deepseek_api"})
    for sentence in ("which cloud provider am i using?",
                     "what cloud provider am i using?",
                     "which cloud service is chosen?"):
        r = words(sentence) or ""
        check(f"{sentence!r} -> the chosen service, from cloud-choice.json",
              "DeepSeek" in r and "deepseek-flash" in r
              and "cloud-choice.json" in r and "saved " in r, r)
    r = words("which cloud provider am i using?") or ""
    check("... and it says a choice is not a connection",
          "nothing is sent by itself" in r.lower(), r)
    check("... no key or fragment appears",
          "sk-" not in r and "api key" not in r.lower(), r)


def t_provider_absent_says_not_set_up_and_what_that_means():
    clean()
    for sentence in ("which cloud provider am i using?", "am i on cloud?"):
        r = words(sentence) or ""
        check(f"{sentence!r} with no file -> 'not set up' in plain words",
              "not set up" in r and "cloud-choice.json is not there" in r, r)
    r = words("which cloud provider am i using?") or ""
    check("... and it says what that means: no cloud path at all, everything local",
          "no cloud path at all" in r and "written by the model on this PC" in r, r)


def t_am_i_on_cloud_answers_from_the_reality():
    clean()
    write_json(CHOICE, {"provider": "deepseek_api"})
    r = words("am i on cloud?") or ""
    check("'am I on cloud?' -> this answer is local, the chosen service sends nothing "
          "by itself while the switch is off",
          "written on this PC" in r and "nothing is sent by itself" in r.lower()
          and "every cloud turn waits for your yes" in r
          and "cloud-choice.json" in r, r)
    write_json(SWITCH, {"on": True})
    r = words("am i on cloud?") or ""
    check("... with the standing switch on, it says a hard question may go without "
          "asking first, and never claims nothing is sent",
          "standing switch is ON" in r and "without asking you first" in r
          and "nothing is sent by itself" not in r.lower(), r)


def t_escalation_state_off_is_plain():
    clean()
    write_json(CHOICE, {"provider": "deepseek_api"})
    r = words("is escalation on?") or ""
    check("'is escalation on?' with no switch file -> off, and the file is named",
          "escalation is off" in r and "escalate-cloud.json is not there" in r, r)
    check("... and it says I never send to the cloud by myself",
          "never send anything to the cloud by myself" in r, r)
    check("... and names what never goes even with the switch on",
          "email" in r and "files" in r and "notes" in r and "stored memory" in r, r)
    write_json(SWITCH, {"on": False})
    r = words("is escalation on?") or ""
    check("... a file saying off is reported as off, with the file named",
          "escalation is off" in r and "says off" in r, r)


def t_escalation_state_on_is_plain():
    clean()
    write_json(CHOICE, {"provider": "deepseek_api"})
    write_json(SWITCH, {"on": True})
    r = words("is escalation on?") or ""
    check("'is escalation on?' with the file on -> on, and the file is named",
          "Escalation is ON" in r and "escalate-cloud.json" in r, r)
    check("... it says money may be spent and words sent without asking first",
          "spend money" in r and "without asking you first" in r, r)
    check("... and it names the provider the messages would go to", "DeepSeek" in r, r)
    check("... and how to stop it", "turn escalation off" in r, r)
    r = words("will you send things to the cloud by yourself?") or ""
    check("'will you send things to the cloud by yourself?' -> the same real state, "
          "never read as the command to start", "Escalation is ON" in r, r)
    got = Q.match("will you send things to the cloud by yourself?", now=0)
    check("... and it is a QUESTION intent, never a change",
          got is not None and got.name == "cloud_settings"
          and got.f.get("shape") == "escalation", (got and (got.name, dict(got.f))))


def t_cap_and_spend_are_read_from_the_ledger():
    clean()
    write_json(CHOICE, {"provider": "deepseek_api"})
    month = API.month_key()
    write_json(MONEY, money_doc(cap=10.0, months={
        month: {"deepseek_api": {"dollars": 0.1234, "requests": 2,
                                 "prompt_tokens": 100, "completion_tokens": 50}},
        "2026-10": {"deepseek_api": {"dollars": 0.0099141, "requests": 4}},
    }))
    r = words("what's my cap?") or ""
    check("'what's my cap?' -> the cap, from chatbot\\api-money.json",
          "$10.00 a month" in r and "DeepSeek" in r
          and "chatbot\\api-money.json" in r and "saved " in r, r)
    r = words("how much have I spent this month?") or ""
    check("'how much have I spent this month?' -> this month's recorded total",
          "about $0.12" in r and "2 answers" in r and "November" in r, r)
    check("... it names the file and when it was saved",
          "chatbot\\api-money.json" in r and "saved " in r, r)
    check("... and it says what the cap leaves (the DeepSeek line)",
          "of its $10.00 cap" in r, r)
    r = words("how much have I spent?") or ""
    check("... the bare question is the same month's answer",
          "about $0.12" in r, r)


def t_cap_absent_says_not_set_up_and_means_not_allowed():
    clean()
    r = words("what's my cap?") or ""
    check("no money file -> 'No cap is set up' and the file is named",
          "No cap is set up" in r and "chatbot\\api-money.json is not there" in r, r)
    check("... and it says what that means: that service is not used at all",
          "can be used at all" in r, r)
    write_json(CHOICE, {"provider": "deepseek_api"})
    write_json(MONEY, money_doc(cap=None))
    r = words("what's my cap?") or ""
    check("a service chosen with no cap -> no cap set, and it is NOT 'unlimited'",
          "No monthly cap is set" in r and "not used at all" in r
          and "does not mean unlimited" in r, r)


def t_what_escalation_does_names_the_refusals():
    clean()
    write_json(SWITCH, {"on": False})
    r = words("what does escalation actually do?") or ""
    low = r.lower()
    check("'what does escalation actually do?' -> what it does, and the switch file",
          "standing switch" in r and "escalate-cloud.json" in r, r)
    for subject in ("email", "files", "notes", "credentials", "stored memory",
                    "private question", "pasted secret", "picture", "your screen"):
        check(f"... it still refuses {subject}", subject in low, r)
    check("... and says it is off right now", "OFF right now" in r, r)
    r = words("what can go to the cloud?") or ""
    check("'what can go to the cloud?' -> the same refusal list",
          "never go to the cloud" in r and "email" in r.lower(), r)


# ---------------------------------------------------------------------------
#   2. The matcher: narrow, and the older doors keep their sentences
# ---------------------------------------------------------------------------

def t_the_older_doors_keep_their_own_sentences():
    clean()
    write_json(CHOICE, {"provider": "deepseek_api"})
    cases = (
        ("which cloud providers can I use", "cloud_provider_list"),
        ("what cloud providers are supported", "cloud_provider_list"),
        ("can i use chatgpt", "cloud_provider_list"),
        ("are you using the cloud right now?", "cloud_honesty"),
        ("what gets sent when you use the cloud?", "cloud_honesty"),
        ("what never gets sent?", "cloud_honesty"),
        ("which provider is the cloud preset using?", "cloud_honesty"),
        ("how much did I spend last month", "honest_chat"),
        ("switch to openrouter", "cloud_provider_choose"),
        ("use mistral as my cloud provider", "cloud_provider_choose"),
        ("turn on cloud escalation", "cloud_escalation_set"),
        ("turn cloud escalation off", "cloud_escalation_set"),
        ("is cloud escalation on?", "cloud_settings"),
        ("what is the cloud?", "feature_explain"),
    )
    for sentence, name in cases:
        got = Q.match(sentence, now=0)
        found = None if got is None else got.name
        check(f"{sentence!r} keeps its own door ({name})", found == name, found)


def t_unrelated_sentences_are_not_captured():
    clean()
    for sentence in ("what is the weather?", "set a timer for 5 minutes",
                     "turn on the kitchen light", "change my zoom level to 5",
                     "how much does a plane ticket cost?", "what is my disk space?",
                     "is the cloud on?"):
        got = Q.match(sentence, now=0)
        check(f"{sentence!r} is not a cloud-settings sentence",
              got is None or got.name != "cloud_settings",
              None if got is None else (got.name, dict(got.f)))


def t_the_questions_are_marked_read_only():
    check("the read answer is marked read-only (no 'cancel that' loss)",
          "cloud_settings" in Q.READ_ONLY_INTENTS)
    check("... and is deterministic in a PRIVATE chat too",
          "cloud_settings" in Q._PRIVATE_DETERMINISTIC_READS)
    check("the CHANGE is deliberately NOT read-only",
          "cloud_settings_change" not in Q.READ_ONLY_INTENTS)


# ---------------------------------------------------------------------------
#   3. The changes: the existing doors, one card, nothing before a yes
# ---------------------------------------------------------------------------

def t_escalation_on_is_one_card_and_writes_nothing_before_yes():
    clean()
    write_json(CHOICE, {"provider": "deepseek_api"})
    P._gate = card_no
    got = Q.match("turn escalation on", now=0)
    check("'turn escalation on' (no 'cloud' word) reaches the cloud-settings change",
          got is not None and got.name == "cloud_settings_change"
          and got.f.get("kind") == "escalation" and got.f.get("on") is True,
          None if got is None else (got.name, dict(got.f)))
    out = Q.run(got, None, 0, peer="127.0.0.1", local="127.0.0.1") if got else None
    check("... denied: the answer says it was NOT turned on, in the door's own words",
          out is not None and "Not turned on" in out.reply, None if out is None else out.reply)
    check("... and escalate-cloud.json was NOT written before the yes",
          not SWITCH.exists(), sorted(p.name for p in TMP.iterdir()))
    check("... and the switch still reads off in the PC's state", not P.escalate_on())

    P._gate = card_yes
    out = Q.run(got, None, 0, peer="127.0.0.1", local="127.0.0.1") if got else None
    check("... approved: the switch is ON, and the answer is the door's own sentence",
          out is not None and "without asking first" in out.reply
          and P.escalate_on() is True, None if out is None else out.reply)


def t_escalation_off_is_instant_and_cardless():
    clean()
    write_json(CHOICE, {"provider": "deepseek_api"})
    write_json(SWITCH, {"on": True})
    cards = []
    P._gate = lambda *a, **k: cards.append(a) or Verdict(True, "approved")
    got = Q.match("turn escalation off", now=0)
    out = Q.run(got, None, 0, peer="127.0.0.1", local="127.0.0.1") if got else None
    check("'turn escalation off' -> OFF at once with NO card (the existing rule)",
          cards == [] and P.escalate_on() is False, cards)
    check("... and the answer says every cloud turn asks again",
          out is not None and "asks before every cloud turn" in out.reply,
          None if out is None else out.reply)


def t_unknown_provider_is_refused_with_the_list_and_no_card():
    clean()
    write_json(CHOICE, {"provider": "deepseek_api"})
    cards = []
    P._gate = lambda *a, **k: cards.append(a) or Verdict(True, "approved")
    got = Q.match("change my cloud provider to anthropic", now=0)
    check("an unknown provider name reaches the cloud-settings change",
          got is not None and got.name == "cloud_settings_change"
          and got.f.get("kind") == "provider", None if got is None else got)
    out = Q.run(got, None, 0, peer="127.0.0.1", local="127.0.0.1") if got else None
    r = None if out is None else out.reply
    check("... it is REFUSED, and the refusal lists the services from PRESETS",
          r is not None and "there is no cloud service called" in r
          and all(p.company in r for p in API.PRESETS.values()), r)
    check("... no card was raised and cloud-choice.json was not touched",
          cards == [] and json.loads(CHOICE.read_text())["provider"] == "deepseek_api",
          cards)


def t_a_chosen_provider_is_its_own_door_with_one_card():
    clean()
    write_json(CHOICE, {"provider": "deepseek_api"})
    API.ready_for = lambda pid: ""
    cards = []
    P._gate = lambda action, detail, prompt="": (
        cards.append((action, detail, prompt)) or Verdict(False, "timed_out"))
    status, body = CS.set_provider("mistral_api")
    check("CS.set_provider -> exactly ONE change_own_config card",
          len(cards) == 1 and cards[0][0] == "change_own_config", cards[:1])
    check("... denied: nothing was written, and the body says so",
          status == 200 and body.get("changed") is not True
          and json.loads(CHOICE.read_text())["provider"] == "deepseek_api", body)
    check("... and the chat words never claim a change",
          "not" in CS.change_words("provider", status, body).lower()
          and "done" not in CS.change_words("provider", status, body).lower(),
          CS.change_words("provider", status, body))
    P._gate = lambda *a, **k: Verdict(True, "approved")
    status, body = CS.set_provider("mistral_api")
    check("... approved: cloud-choice.json now names Mistral",
          status == 200 and body.get("changed") is True
          and json.loads(CHOICE.read_text())["provider"] == "mistral_api", body)
    check("... and the chat words say done, naming the company",
          "done" in CS.change_words("provider", status, body)
          and "Mistral" in CS.change_words("provider", status, body),
          CS.change_words("provider", status, body))


def t_a_cap_raise_is_one_card_and_writes_nothing_before_yes():
    clean()
    write_json(CHOICE, {"provider": "deepseek_api"})
    write_json(MONEY, money_doc(cap=10.0))
    cards = []

    def gate_no(action, detail, prompt=""):
        cards.append((action, detail, prompt))
        return Verdict(False, "denied")

    L.configure(gate=gate_no, tier_of=lambda action: "ask", audit=lambda *a, **k: None)
    got = Q.match("set my cap to $50", now=0)
    check("'set my cap to $50' -> the cloud-settings change, cap 50",
          got is not None and got.name == "cloud_settings_change"
          and got.f.get("kind") == "cap" and got.f.get("dollars") == 50.0,
          None if got is None else (got.name, dict(got.f)))
    out = Q.run(got, None, 0, peer="127.0.0.1", local="127.0.0.1") if got else None
    r = None if out is None else out.reply
    check("... a RAISE raises exactly ONE raise_api_limit card, tier ask",
          len(cards) == 1 and cards[0][0] == "raise_api_limit", cards[:1])
    check("... the card names the service, the old cap and the new one",
          "DeepSeek" in str(cards[0][1].get("text")) and "$10.00" in str(cards[0][1].get("text"))
          and "$50.00" in str(cards[0][1].get("text")), cards[:1])
    check("... denied: the money file still says $10.00 and the answer says not raised",
          json.loads(MONEY.read_text())["limits"]["deepseek_api"] == 10.0
          and r is not None and "not raised" in r, (r, MONEY.read_text()[:80]))

    L.configure(gate=lambda *a, **k: Verdict(True, "approved"),
                tier_of=lambda action: "ask", audit=lambda *a, **k: None)
    got = Q.match("set my cap to $50", now=0)
    out = Q.run(got, None, 0, peer="127.0.0.1", local="127.0.0.1") if got else None
    check("... approved: the cap really is $50 and the answer is the money module's line",
          json.loads(MONEY.read_text())["limits"]["deepseek_api"] == 50.0
          and out is not None and "$50.00" in out.reply, None if out is None else out.reply)


def t_a_cap_lowering_is_instant_and_cardless():
    clean()
    write_json(CHOICE, {"provider": "deepseek_api"})
    write_json(MONEY, money_doc(cap=10.0))
    cards = []
    L.configure(gate=lambda *a, **k: cards.append(a) or Verdict(True, "approved"),
                tier_of=lambda action: "ask", audit=lambda *a, **k: None)
    got = Q.match("lower my cap to $5", now=0)
    out = Q.run(got, None, 0, peer="127.0.0.1", local="127.0.0.1") if got else None
    check("a LOWERING applies at once with no card (it only spends less)",
          cards == [] and json.loads(MONEY.read_text())["limits"]["deepseek_api"] == 5.0,
          cards)
    check("... and the answer is the money module's own 'at most' sentence",
          out is not None and "$5.00 a month" in out.reply, None if out is None else out.reply)


def t_the_cap_can_be_named_and_over_the_top_is_refused():
    clean()
    write_json(CHOICE, {"provider": "openai_api"})
    write_json(MONEY, money_doc(cap=10.0, service="openai_api"))
    got = Q.match("set my openai cap to $5", now=0)
    check("'set my openai cap to $5' reads the service as well as the amount",
          got is not None and got.name == "cloud_settings_change"
          and got.f.get("kind") == "cap" and got.f.get("dollars") == 5.0
          and API.BY_SHORT.get("openai") == "openai_api",
          None if got is None else (got.name, dict(got.f)))
    got = Q.match("set my cap to 999999", now=0)
    out = Q.run(got, None, 0, peer="127.0.0.1", local="127.0.0.1") if got else None
    r = None if out is None else out.reply
    check("an amount over the money module's own most-limit is refused, not clamped",
          r is not None and "Nothing was changed" in r, r)


def t_no_single_service_asks_which_and_raises_nothing():
    clean()
    write_json(MONEY, money_doc(cap=10.0, service="deepseek_api"))
    write_json(MONEY, money_doc(cap=None))
    cards = []
    L.configure(gate=lambda *a, **k: cards.append(a) or Verdict(True, "approved"),
                tier_of=lambda action: "ask", audit=lambda *a, **k: None)
    got = Q.match("set my cap to $5", now=0)
    out = Q.run(got, None, 0, peer="127.0.0.1", local="127.0.0.1") if got else None
    r = None if out is None else out.reply
    check("with no chosen service and no single cap, it ASKS which service",
          r is not None and "say which cloud service" in r.lower() and cards == [], (r, cards))


# ---------------------------------------------------------------------------
#   4. Nothing secret, and the source is honest about the three files
# ---------------------------------------------------------------------------

def t_a_private_chat_answers_the_reads_and_refuses_the_change():
    clean()
    write_json(CHOICE, {"provider": "deepseek_api"})
    write_json(SWITCH, {"on": True})
    write_json(MONEY, money_doc(cap=10.0))
    out = Q.answer("is escalation on?", now=0, private=True,
                   peer="127.0.0.1", local="127.0.0.1")
    check("a PRIVATE chat still answers the cloud-settings read from this PC",
          out is not None and out.intent == "cloud_settings"
          and "Escalation is ON" in out.reply,
          None if out is None else (out.intent, out.reply[:120]))
    out = Q.answer("turn escalation off", now=0, private=True,
                   peer="127.0.0.1", local="127.0.0.1")
    check("... and a CHANGE is refused there: it changes settings, and the switch "
          "is untouched", out is not None and out.intent == "cloud_settings_change"
          and "doesn't change settings" in out.reply and P.escalate_on() is True,
          None if out is None else (out.intent, out.reply[:160]))


def t_no_key_store_and_no_key_words():
    """The runtime seam: no answer may READ the key store, and none may show a
    key. The store is a spy here, so a future answer that reaches for it fails
    on WHAT WAS CALLED, not on how the source is spelled."""
    calls = []
    real = API.key_saved
    API.key_saved = lambda pid: (calls.append(pid) or False)
    try:
        clean()
        write_json(CHOICE, {"provider": "deepseek_api"})
        write_json(SWITCH, {"on": True})
        write_json(MONEY, money_doc(cap=10.0))
        replies = []
        for sentence in ("which cloud provider am i using?", "am i on cloud?",
                         "is escalation on?",
                         "will you send things to the cloud by yourself?",
                         "what's my cap?", "how much have I spent this month?",
                         "what does escalation actually do?"):
            replies.append((sentence, words(sentence) or ""))
    finally:
        API.key_saved = real
    check("no answer reads the key store (the spy was called)",
          calls == [], calls)
    for sentence, r in replies:
        check(f"{sentence!r} carries no key or fragment",
              "sk-" not in r and "api key" not in r.lower(), r)


def main():
    for fn in (t_provider_set_is_read_from_the_file_and_says_so,
               t_provider_absent_says_not_set_up_and_what_that_means,
               t_am_i_on_cloud_answers_from_the_reality,
               t_escalation_state_off_is_plain,
               t_escalation_state_on_is_plain,
               t_cap_and_spend_are_read_from_the_ledger,
               t_cap_absent_says_not_set_up_and_means_not_allowed,
               t_what_escalation_does_names_the_refusals,
               t_the_older_doors_keep_their_own_sentences,
               t_unrelated_sentences_are_not_captured,
               t_the_questions_are_marked_read_only,
               t_escalation_on_is_one_card_and_writes_nothing_before_yes,
               t_escalation_off_is_instant_and_cardless,
               t_unknown_provider_is_refused_with_the_list_and_no_card,
               t_a_chosen_provider_is_its_own_door_with_one_card,
               t_a_cap_raise_is_one_card_and_writes_nothing_before_yes,
               t_a_cap_lowering_is_instant_and_cardless,
               t_the_cap_can_be_named_and_over_the_top_is_refused,
               t_no_single_service_asks_which_and_raises_nothing,
               t_a_private_chat_answers_the_reads_and_refuses_the_change,
               t_no_key_store_and_no_key_words):
        try:
            fn()
        except Exception as exc:                             # noqa: BLE001
            failed = f"{fn.__name__} raised {type(exc).__name__}: {exc}"
            FAILED.append(failed)
            print(f"FAIL  {failed}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
