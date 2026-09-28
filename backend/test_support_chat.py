"""test_support_chat.py - "Chat with customer support for me" (jarvis_support.py
and its routes in jarvis_chatbot_routes.py), without a browser: a stand-in
chat widget (jarvis_support.FakeWidget), a stand-in driver model, a
stand-in approval gate and a clock moved by hand. The real window against
fake vendor pages is test_support_widget.py.

    python3 backend/test_support_chat.py

The owner's decisions (CLAUDE.md, "Customer-support chats", 2026-09-28) it
holds the code to:
  - ONE details card per chat lists exactly which details Jarvis may give;
    passwords, PINs, card numbers, security answers and ID numbers are
    refused on the card and blocked in every message;
  - the support last check: planted card numbers, SSN-shaped numbers,
    passwords, keys, one-time codes, unlisted emails, phones and addresses
    are blocked; the listed values pass; nothing harmless is blocked;
  - "are you a bot?" (and "am I talking to Alex?") is caught by plain code
    and handed to the owner: nothing is sent, and no message saying it is
    a person can ever leave; there is no opening "I'm an AI" line;
  - EVERY offer gets its own card, detected over 100 written agent lines;
    nothing is accepted without that card's yes (a typed "yes" is refused,
    a late yes accepts nothing); holding lines and the time-out;
  - identity checks and details not on the card are handed to the owner;
  - queue, handover, menu buttons (a button with offer words gets a card),
    "chat ended", a quiet agent, a chat never opened, Take over and Resume,
    Stop and Stop everything;
  - the encrypted "Support chat" record (role "support", never "user"),
    the export, and the learner learning nothing from it;
  - the routes, the card words, and that it is shipped and documented.
No pytest, no network, no model.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import tomllib
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, SHIPPED, require_shipped  # noqa: E402

require_shipped("jarvis_support.py", "jarvis_support_widget.py", "jarvis_chatbot.py",
                "jarvis_chatbot_routes.py", "jarvis_chat_log.py", "jarvis_task_control.py",
                "jarvis_stop_all.py", "jarvis_search.py", "jarvis_mail_mask.py",
                "rebuilt/jarvis_router.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.insert(1, str(HERE / "rebuilt"))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-support-"))
TIERS: dict = {}
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
fw.action_tier = lambda action: TIERS.get(action, "ask")
sys.modules["jarvis_framework"] = fw

import jarvis_stop_all as SA  # noqa: E402
import jarvis_task_control as TC  # noqa: E402
import jarvis_chatbot as CB  # noqa: E402
import jarvis_chatbot_routes as R  # noqa: E402
import jarvis_support as S  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   Planted fakes, built by joining strings (nothing real-looking sits
#   whole in this file for a scanner to trip on).
# --------------------------------------------------------------------------

ORDER = "4481" + "902217"                       # 10 digits: blocked unless listed
EMAIL = "alex.q" + "@" + "example.net"
OTHER_EMAIL = "someone.else" + "@" + "example.org"
PHONE = "(415) 555-" + "0188"
NAME = "Alex " + "Quinlan"
CARD = "4111 " + "1111 1111 " + "1111"           # passes the card checksum
CARD_DASH = "5500-" + "0055-5555-" + "5559"
SSN = "123-" + "45-" + "6789"
PASSWORD_LINE = "my pass" + "word is Hunter2"
LABELLED = "pass" + "word = " + "Hunter2Fake0123456"
FAKE_KEY = "sk-" + "proj-" + "fakefakefake0123456789"
STREET = "12 Old " + "Mill Road"
DETAILS = [{"name": "Order number", "value": ORDER}, {"name": "Email", "value": EMAIL},
           {"name": "Name", "value": NAME}]
GOAL = ("Get a refund for order " + ORDER + ": the spa closed before I could use the "
        "voucher.")
OPENING = f"Hi, I bought a spa voucher (order {ORDER}) and the spa has closed. Could I get a refund?"
SUMMARY = {"answer": "Groupon agreed to a full refund of $45.", "agreed": ["A $45 refund"],
           "open": []}


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = float(t)

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(0.0, float(s))


class Verdict:
    def __init__(self, allowed, outcome, tier="ask"):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier


class Model:
    """The driver model: hands back the moves it was given, in order, then
    "wait"; the summary when asked for one."""

    def __init__(self, moves=()):
        self.moves = list(moves)
        self.bodies: list = []

    def __call__(self, url, body):
        self.bodies.append(body)
        if body.get("format") == S.SUMMARY_SCHEMA:
            return {"message": {"content": json.dumps(SUMMARY)}}
        mv = {"move": "wait", "message": "", "option": "", "reason": "", "notes": ""}
        if self.moves:
            mv.update(self.moves.pop(0))
        return {"message": {"content": json.dumps(mv)}}


def reply(text):
    return {"move": "reply", "message": text}


CARDS: list = []
AUDIT: list = []
KEPT: list = []


def approve(action, detail, prompt):
    CARDS.append((action, detail, prompt))
    return Verdict(True, "approved")


def deny_offers(action, detail, prompt):
    CARDS.append((action, detail, prompt))
    return Verdict(action == S.ACTION, "approved" if action == S.ACTION else "denied")


def fresh():
    S._reset_for_tests()
    CB._reset_for_tests()
    R._reset_for_tests()
    with TC._lock:
        TC._running.clear()
        TC._paused.clear()
        TC._signals.clear()
        TC._notes.clear()
        TC._resuming.clear()
    CARDS.clear()
    AUDIT.clear()
    KEPT.clear()
    TIERS.clear()


def world(widget, *, moves=(), gate=approve, spawn=None, facts=None, history=None):
    clock = Clock()
    d = S.Deps(model=Model(moves), saved_facts=lambda m: list(facts or []),
               names_for_facts=lambda f: {}, owner_busy=lambda: False,
               second_lane=lambda: None, full_version_on=lambda: False,
               main_lane=lambda: ("http://127.0.0.1:11434", "jarvis-primary"),
               tier_of=lambda a: TIERS.get(a, "ask"), gate=gate,
               activity=lambda s, dt="": None, audit=lambda e, dt: AUDIT.append((e, dt)),
               clock=clock, sleep=clock.sleep, make_widget=lambda c: widget,
               spawn=spawn or (lambda fn: fn()),
               history=history or (lambda rec: KEPT.append(rec) or ""))
    S.DEPS = d
    return d


def go(widget, *, details=DETAILS, goal=GOAL, company="groupon", **kw):
    d = world(widget, **kw)
    c = S.plan(company, goal, details=details, deps=d)
    assert not c.problem, c.problem
    code, _ = S.start(c, deps=d, wait=True)
    assert code == 202
    return c, d


def whos(c):
    return [t["who"] for t in c.transcript]


# ==========================================================================
#   The support last check
# ==========================================================================

def t_last_check_blocks_planted_values():
    fresh()
    d = world(S.FakeWidget())
    c = S.plan("groupon", GOAL, details=DETAILS, deps=d)
    check("a plan with three details has no problem", not c.problem, c.problem)
    blocked = {
        "a card number": f"You can charge {CARD} again if needed.",
        "a card number with dashes": f"The card was {CARD_DASH}.",
        "an SSN-shaped number": f"My SSN is {SSN}.",
        "a password": PASSWORD_LINE,
        "a labelled secret": LABELLED,
        "an API key": f"Use {FAKE_KEY} for that.",
        "a one-time code": "The verification code is 482913.",
        "an unlisted email": f"Please write to {OTHER_EMAIL} instead.",
        "an unlisted phone number": f"Call me on {PHONE}.",
        "an unlisted street address": f"Send it to {STREET}, please.",
        "a PIN mentioned": "My PIN is the usual one.",
        "a security answer": "My security answer is my first pet.",
        "a health word": "I missed it because of my diagnosis.",
        "saying it is a person": "Don't worry, I'm a real person.",
        "saying it is not a bot": "I am not a bot, I promise.",
        "a longer unlisted number": "Order " + "7719" + "334410 too.",
    }
    for what, text in blocked.items():
        chk = S.support_check(text, c, deps=d)
        check(f"blocked: {what}", not chk.ok, chk)
        check(f"...and the reason never repeats the value ({what})",
              all(v not in chk.why for v in (CARD, SSN, OTHER_EMAIL, PHONE, FAKE_KEY)))
    passes = [f"My order number is {ORDER}.", f"The email on my account is {EMAIL}.",
              f"It's {EMAIL.upper()}.", f"My name is {NAME}.",
              f"Order {ORDER}, and my email is {EMAIL}."]
    for text in passes:
        chk = S.support_check(text, c, deps=d)
        check(f"a listed value passes: {text[:40]}", chk.ok, chk)
    harmless = [
        "Hi, I bought a spa voucher and the spa has closed. Could I get a refund?",
        "Could the refund go back to my original payment method?",
        "Thank you, that's very helpful.", "Is a credit to my account possible instead?",
        "When will the refund arrive in my bank?", "I haven't used the voucher at all.",
        "The spa's website says they closed in August.", "Could you send the invoice by email?",
        "I'd rather have the money back than a voucher, please.",
        "Can you explain why the refund would take 5 to 7 days?",
        "I bought it on 3 March for $45.", "Is there anything else you need from me?",
        "I can wait a moment, no problem.", "Could I have a reference number for this chat?",
        "The deal was for two people.", "I tried to book twice in September.",
        "What are my options if they reopen later?", "Does the promo value expire?",
        "Could you check the order again, please?", "Thanks for your help today.",
        "I paid with a credit card.", "That's fine, I'll wait for the email confirmation.",
        "Sorry, could you repeat that?", "The voucher code is on the order page.",
        "I'd like to cancel the other booking too, if possible.",
        "Can the credit be used on any deal?", "Which files do you need me to upload?",
        "I don't have the receipt any more.", "It was a gift for my sister's birthday.",
        "Please let me know when it's done.",
    ]
    false_blocks = [t for t in harmless if not S.support_check(t, c, deps=d).ok]
    check(f"no false blocks over {len(harmless)} harmless support lines", not false_blocks,
          false_blocks)
    d2 = world(S.FakeWidget(), facts=["The owner is allergic to peni" + "cillin"])
    chk = S.support_check("By the way I'm allergic to peni" + "cillin.", c, deps=d2)
    check("a saved fact about the owner is blocked", not chk.ok and chk.kind == "saved_fact",
          chk)
    d3 = world(S.FakeWidget())
    d3.saved_facts = lambda m: (_ for _ in ()).throw(RuntimeError("no memory"))
    chk = S.support_check("Thanks!", c, deps=d3)
    check("a check that cannot run blocks (fail closed)", not chk.ok and chk.kind == "unchecked")


def t_details_card_rows():
    fresh()
    refused = [("Password", "Hunter2"), ("PIN", "4471"), ("Card number", "1234"),
               ("Security answer", "Rex"), ("SSN", "12345"), ("Passport", "X1"),
               ("Payment", CARD), ("Social", SSN), ("Key", FAKE_KEY),
               ("Last 4 digits of card", "1111"), ("Bank account", "12345678")]
    for name, value in refused:
        rows, why = S.clean_details([{"name": name, "value": value}])
        check(f"refused on the card: {name}", not rows and why, why)
    rows, why = S.clean_details(DETAILS)
    check("the ordinary details are kept exactly as typed",
          not why and rows == tuple((r["name"], r["value"]) for r in DETAILS), (rows, why))
    _, why = S.clean_details([{"name": "Email", "value": EMAIL},
                              {"name": "email", "value": EMAIL}])
    check("a detail listed twice is refused", "twice" in why, why)
    _, why = S.clean_details([{"name": "x", "value": "y"}] * 13)
    check("at most 12 details", why, why)


def t_topics_exclusions_are_real():
    import jarvis_router
    missing = [t for t in S.TOPICS_ALLOWED if t not in jarvis_router._PRIVATE_TERMS]
    check("every topic left out for support chats is really in the chatbot mode's list",
          not missing, missing)


# ==========================================================================
#   Reading the company's words
# ==========================================================================

BOT_QUESTIONS = [
    "Am I talking to a bot?", "Quick check - are you a real person?",
    "Is this an automated reply?", "Are you a human?", "Am I chatting with an AI?",
    "Is this a bot or a real person?", "Are you a robot?", "Is this a real person?",
    "Who am I talking to right now?", "Are you using AI to write these?",
    "Hmm, am I speaking with a machine?", "Are you real?",
]
NOT_BOT = [
    "I'm a virtual assistant; a person will join shortly.", "Our bot can help with FAQs.",
    "Please hold while I check your order.", "Are you still there?",
    "Are you happy with that?", "Is this the right order?",
]


def t_bot_question_detector():
    for q in BOT_QUESTIONS:
        check(f"caught: {q}", S.asks_if_bot(q) != "", q)
    for q in NOT_BOT:
        check(f"not a bot question: {q}", S.asks_if_bot(q) == "", q)
    check("'am I talking to Alex?' is the same question, by the listed name",
          S.asks_if_bot("Thanks! Am I talking to Alex?", ("Alex Quinlan", "Alex")) != ""
          and S.asks_if_bot("Is this Alex?", ("Alex",)) != "")


IDENTITY = [
    "For security, please confirm the last 4 digits of the card you paid with.",
    "What is the answer to your security question?", "Please give me the verification code we just sent.",
    "Can you confirm your date of birth?", "I'll need the code we texted to you.",
    "Please provide your password so I can log in.", "What's the CVV on the card?",
    "Could you verify your identity for me?", "Please share the card number.",
]


def t_identity_detector():
    for q in IDENTITY:
        check(f"identity check caught: {q[:50]}", S.asks_identity(q) != "", q)
    for q in ["Could I have your order number?", "What's the email on the account?",
              "Thanks for confirming."]:
        check(f"not an identity check: {q}", S.asks_identity(q) == "", q)


OFFERS = [
    "I can offer you a full refund of $45. Would you like that?",
    "We can issue a refund to your original payment method or as Groupon Bucks. Which would you prefer?",
    "I'd be happy to give you a $20 credit instead.",
    "Would you like me to cancel the order?", "Shall I go ahead and process the refund?",
    "I can extend the voucher's expiry by 3 months if that works for you.",
    "We could exchange it for another deal of the same value.",
    "Do you agree to a partial refund of $30?", "Please confirm that you'd like to cancel.",
    "I'll refund the full amount now, is that okay?", "How about a replacement voucher?",
    "We can reschedule your booking for next week.", "Can I change the delivery address for you?",
    "I can offer a 50% discount on your next purchase.", "Type YES to accept the refund.",
    "Would store credit work for you?", "We'd be happy to reimburse the booking fee.",
    "Let me know if you want the refund or a new voucher.",
    "I can upgrade you to the premium package at no cost. Interested?",
    "As a goodwill gesture we can add $10 in Groupon Bucks. Would you like that?",
    "I can process the cancellation right away. Do you want me to proceed?",
    "Is it alright if I refund to the original card?", "Should I cancel the subscription?",
    "We're able to give you a full refund. Just reply yes to confirm.",
    "Would you prefer a refund or a credit?", "Do you want me to apply the promo code?",
    "I could waive the fee this time, does that sound good?",
    "We can swap it for a different spa nearby. Would that work?",
    "If you'd like, I can cancel it and refund you in full.", "Shall we rebook for Saturday?",
    "I can send a replacement - is that fine?", "Do you accept the $15 partial refund?",
    "We can offer compensation of $25.", "Could I change the order date for you?",
    "Would a refund of €40 be acceptable?", "I'll cancel it for you now, OK?",
    "I can approve a refund once you confirm.", "Would you like a voucher extension?",
    "I can offer a new voucher worth £30.", "Are you happy for me to cancel the booking?",
    "Can I go ahead with the refund?", "Do you want the Groupon Bucks instead of cash?",
    "Please let me know if you agree to these terms.", "I can refund the $45 today. Okay?",
    "We'll need you to confirm the cancellation.", "Want me to extend it to December?",
    "I can offer a 10 dollars credit. Would you accept that?",
    "Would you like to exchange it for a massage instead?",
    "The best I can do is a $35 credit. Does that work?",
    "Would you like me to change the reservation to 4pm?",
    "I'm able to refund it to your Groupon balance, if you prefer.",
    "We could cancel and rebook it for you. Let me know.",
    "Can you confirm you want a refund to the original payment method?",
    "Is a replacement okay with you?", "I will process a refund of $45. Is that alright?",
]
NOT_OFFERS = [
    "Hi, thanks for contacting Groupon support!", "Let me look into that for you.",
    "One moment please.", "Could I have your order number?", "Thanks, I found your order.",
    "I'm sorry to hear the spa closed.", "Your refund has been processed.",
    "I have processed the refund.", "The refund will arrive in 5 to 7 business days.",
    "Your order number is shown in your account.", "The merchant closed in August.",
    "I understand how frustrating that must be.", "Please hold on while I check.",
    "I've checked with my team.", "You are number 3 in the queue.",
    "Priya joined the chat.", "Great, thank you for waiting.", "Is there anything else I can help with?",
    "Have a great day!", "Your reference number is GRP48213.",
    "I can see you bought it on 3 March.", "The voucher was bought as a gift.",
    "Our policy allows refunds within 3 days of purchase.", "Refunds normally take a week.",
    "The deal expired on 1 September.", "I see two vouchers on your account.",
    "That voucher has already been redeemed.", "Your account email ends in example.net.",
    "Thank you for your patience.", "I'm checking with the merchant now.",
    "Your credit has been added to your account.", "The cancellation was completed.",
    "Is there anything else I can do for you today?", "Please don't close this window.",
    "Our team is working on it.", "Sorry for the wait.", "I've noted that on your account.",
    "Hello! My name is Priya.", "Just a moment while I pull up the details.",
    "That's all sorted now.", "The spa's owner told us they are closed.",
    "Thanks for letting us know.", "Understood.", "I see what happened here.",
    "I'll be right back with an update.",
]


def t_offer_detection_over_100_lines():
    check("100 written agent lines", len(OFFERS) + len(NOT_OFFERS) == 100,
          (len(OFFERS), len(NOT_OFFERS)))
    missed = [x for x in OFFERS if not S.offer_in(x)]
    check(f"every one of {len(OFFERS)} offers raises a card (none missed)", not missed, missed)
    extra = [x for x in NOT_OFFERS if S.offer_in(x)]
    print(f"        (offer detector: {len(extra)} card(s) over {len(NOT_OFFERS)} "
          f"non-offers: {extra})")
    check("few needless cards over the non-offers (if in doubt, a card)", len(extra) <= 3,
          extra)


def t_other_detectors():
    check("queue position", S.queue_position("You are number 3 in the queue.") == 3
          and S.queue_position("There are 12 people ahead of you") == 12
          and S.queue_position("Hello") is None)
    check("queue words", S.is_queue_line("All of our agents are currently busy.")
          and S.is_queue_line("An agent will be with you shortly."))
    check("a person joined", S.joined_name("Priya joined the chat.") == "Priya"
          and S.joined_name("You're now chatting with Marco") == "Marco")
    check("the chat ended", S.is_ended("This chat has ended.") and S.is_ended(
        "Priya has left the conversation") and not S.is_ended("The deal ended in May."))
    check("'anything else?' is closing, not an offer",
          S.is_closing("Is there anything else I can help you with today?")
          and not S.offer_in("Is there anything else I can help you with today?"))
    check("a reference number", S.reference_in("Your reference number is GRP48213.")
          == "GRP48213" and S.reference_in("Case #: 00417731") == "00417731"
          and S.reference_in("For reference, the spa closed.") == "")
    q, kind = S.asks_unlisted("Could you tell me the email address on your account?",
                              (("Order number", ORDER),))
    check("a detail not on the card is noticed", kind == "email" and q)
    q, kind = S.asks_unlisted("Could you tell me the email address on your account?",
                              (("Email", EMAIL),))
    check("a detail on the card is not handed over", not q and not kind)
    check("claims to be human: caught", S.claims_human("I'm a real person")
          and S.claims_human("I am not an AI") and not S.claims_human("I'm happy with that"))


# ==========================================================================
#   The card
# ==========================================================================

def t_the_details_card():
    fresh()
    d = world(S.FakeWidget())
    c = S.plan("groupon", GOAL, details=DETAILS, deps=d)
    card = S.describe(c)
    check("the card lists every detail word for word",
          all(f"{r['name']}: {r['value']}" in card for r in DETAILS))
    check("the card names the company, its help page and the terms risk",
          "Groupon" in card and S.COMPANIES["groupon"].help_url in card
          and "Terms risk:" in card and "could be" in card)
    check("the card: the goal word for word", ("\n" + GOAL + "\n") in card)
    check("the card: no opening AI line; never claims to be a person",
          "no opening line saying it is an AI" in card and "never claims to be a person" in card)
    check("the card: every offer its own card; identity checks handed over",
          "own approval card" in card and "identity checks" in card)
    check("the card: what saying no costs", card.rstrip().endswith(S.IF_REFUSED))
    check("the card: the version", "one graphics card" in card)
    c2 = S.plan("groupon", GOAL, details=[{"name": "Card number", "value": "x"}], deps=d)
    check("a card number row: refused before any card", c2.problem and c2.state == "refused")
    c3 = S.plan("groupon", f"Refund, and my SSN is {SSN}", details=DETAILS, deps=d)
    check("a goal with an SSN in it is refused before any card", "cannot be used" in c3.problem,
          c3.problem)
    c4 = S.plan("other", GOAL, address="http://help.example.com", deps=d)
    check("another company: https only", "https" in c4.problem, c4.problem)
    c5 = S.plan("other", GOAL, address="https://192.168.1.4/help", deps=d)
    check("another company: a public name, never an IP address", c5.problem, c5.problem)
    c6 = S.plan("other", GOAL, address="https://help.example.com/chat", details=DETAILS,
                deps=d)
    check("another company: its own host is the only host",
          not c6.problem and c6.hosts == ("help.example.com",) and c6.terms == S.OTHER_TERMS,
          c6.problem)
    c7 = S.plan("amazon", GOAL, deps=d)
    check("no company preset beyond Groupon without the owner's OK", c7.problem, c7.problem)
    c8 = S.plan("groupon", GOAL, max_messages=26, deps=d)
    check("the one-card version's most messages", "at most 25" in c8.problem, c8.problem)
    TIERS[S.OFFER_ACTION] = "auto"
    check("an offer tier other than ask switches it off",
          "support_offer" in S.tier_problem(d))
    TIERS.clear()
    fresh()
    d = world(S.FakeWidget(), gate=lambda a, dt, p: Verdict(False, "denied"))
    c = S.plan("groupon", GOAL, details=DETAILS, deps=d)
    S.start(c, deps=d, wait=True)
    check("a card that says no: nothing opened, nothing sent",
          c.state == "refused" and c.widget is None)


# ==========================================================================
#   Whole chats against the stand-in widget
# ==========================================================================

AGENT_ORDER_Q = "Hi, I'm Priya from Groupon. Could I have your order number please?"
AGENT_OFFER = ("Thank you. I can offer you a full refund of $45 to your original payment "
               "method. Would you like me to go ahead?")


def t_a_whole_chat():
    fresh()
    w = S.FakeWidget({
        1: ["You are number 2 in the queue.", "Priya joined the chat.", AGENT_ORDER_Q],
        2: [AGENT_OFFER],
        3: ["Done, the refund is on its way. Is there anything else I can help you with "
            "today?"],
        4: ["Of course. Your reference number is GRP48213. Summary: a full refund of $45 "
            "to your original payment method.", "Is there anything else?"],
    })
    c, d = go(w, moves=[reply(OPENING), reply(f"It's {ORDER}."), {"move": "wait"}])
    check("the chat finished by itself", c.state == "done" and c.ended_code == "finished",
          (c.state, c.ended_code, c.ended_words))
    check("exactly these went out, in this order: the opening, the listed order number, "
          "the accepting line (after the card), the reference request, thanks",
          w.sent == [OPENING, f"It's {ORDER}.", S.ACCEPT_LINE, S.CLOSING_ASK, S.THANKS],
          w.sent)
    check("no opening 'I'm an AI' line was sent",
          not any(re.search(r"\bAI\b|assistant|bot", x) for x in w.sent))
    kinds = [a for a, _, _ in CARDS]
    check("two cards: the details card, then ONE offer card", kinds == [S.ACTION,
                                                                      S.OFFER_ACTION], kinds)
    offer_text = CARDS[1][1]["text"]
    check("the offer card: the agent's words and the reply, word for word",
          AGENT_OFFER in offer_text and S.ACCEPT_LINE in offer_text
          and "Terms risk" in offer_text)
    check("the queue and the person who joined were followed",
          c.agent == "Priya" and not c.in_queue)
    check("the reference number was kept", c.reference == "GRP48213", c.reference)
    check("the company's words are outside text, marked with their source",
          all(t["outside_text"] and t["source"] == S.SOURCE for t in c.transcript
              if t["who"] in ("company", "system")))
    check("the queue and 'joined' lines are notices", whos(c).count("system") == 2, whos(c))
    check("Jarvis's own messages are not outside text",
          all(t["outside_text"] is False for t in c.transcript if t["who"] == "jarvis"))
    sent_audit = [dt for e, dt in AUDIT if e == "support.detail_sent"]
    check("each detail sent is logged by NAME, never its value",
          [x["detail"] for x in sent_audit] == ["Order number", "Order number"]
          and ORDER not in json.dumps(AUDIT) and EMAIL not in json.dumps(AUDIT)
          and GOAL not in json.dumps(AUDIT), sent_audit)
    check("the summary: written on this PC, outside text, never read aloud",
          c.summary["by_model"] and c.summary["outside_text"] and not c.summary["read_aloud"]
          and c.summary["reference"] == "GRP48213")
    check("the chat was kept (the history's record)", c.saved == "yes" and len(KEPT) == 1)
    rec = KEPT[0]
    provs = [r["provenance"] for r in rec["rows"]]
    check("the record: the details card first, every line with its author",
          provs[0] == "support_note" and "support_company" in provs
          and "support_jarvis" in provs and rec["title"].startswith("Support chat with Groupon"))
    check("the window was closed", w.closed == 1)
    body = d.model.bodies[0]
    check("the driver: no tools, the fixed instruction, the goal and the details only",
          "tools" not in body and body["messages"][0]["content"] == S.SUPPORT_INSTRUCTION
          and GOAL in body["messages"][1]["content"]
          and f"Email: {EMAIL}" in body["messages"][1]["content"]
          and len(body["messages"]) == 2)


def t_one_card_sees_six_turns():
    fresh()
    d = world(S.FakeWidget())
    c = S.plan("groupon", GOAL, details=DETAILS, deps=d)
    for i in range(10):
        c.transcript.append({"who": "company", "text": f"line number {i}", "at": 0})
    text = S.context_text(c, [])
    check("one graphics card: only the last six lines reach the driver",
          "line number 4" in text and "line number 3" not in text)


def t_are_you_a_bot():
    fresh()
    w = S.FakeWidget({1: ["Thanks! Before we go on - am I talking to a bot or a real person?"]})
    c, d = go(w, moves=[reply(OPENING), reply("Yes, I'm a real person.")])
    check("'are you a bot?': paused and handed to the owner",
          c.state == "paused" and c.paused_code == "bot_question"
          and "bot or a real person" in c.question, (c.state, c.paused_code))
    check("...and nothing at all was sent after it", w.sent == [OPENING], w.sent)
    check("...the driver was not even asked", len(d.model.bodies) == 1)
    check("...the pause says Jarvis never claims to be a person",
          "never claims to be a person" in c.paused_why)
    check("...the task can be resumed with its own card",
          (TC.paused() or {}).get("tool") == S.TASK_TOOL)
    fresh()
    w = S.FakeWidget({1: ["Hi! Am I talking to Alex?"]})
    c, _ = go(w, moves=[reply(OPENING)])
    check("'am I talking to Alex?' is handed over too", c.paused_code == "bot_question")
    fresh()
    w = S.FakeWidget({1: ["Are you a human?"]})
    c, _ = go(w, moves=[reply(OPENING)])
    check("'are you a human?' too", c.paused_code == "bot_question")
    fresh()
    w = S.FakeWidget({1: ["How can I help?"]})
    c, _ = go(w, moves=[reply(OPENING), reply("I'm a real person, just so you know."),
                        reply("I am not a bot.")])
    check("a message claiming to be a person never leaves; twice pauses the chat",
          w.sent == [OPENING] and c.paused_code == "blocked", (w.sent, c.paused_code))


def t_identity_and_unlisted_details_are_handed_over():
    fresh()
    w = S.FakeWidget({1: ["For security, please confirm the last 4 digits of the card you "
                          "paid with."]})
    c, d = go(w, moves=[reply(OPENING), reply("It's 1111.")])
    check("an identity check: paused, handed to the owner, nothing sent",
          c.paused_code == "identity" and w.sent == [OPENING] and "last 4 digits" in c.question)
    fresh()
    w = S.FakeWidget({1: ["Could you tell me the phone number on your account?"]})
    c, d = go(w, moves=[reply(OPENING), reply(f"It's {PHONE}")])
    check("a detail not on the card: paused, nothing sent",
          c.paused_code == "unlisted" and w.sent == [OPENING]
          and "a phone number" in c.paused_why, c.paused_why)
    fresh()
    w = S.FakeWidget({1: ["Could you tell me the email address on your account?"],
                      2: ["Thanks. This chat has ended."]})
    c, d = go(w, moves=[reply(OPENING), reply(f"Sure, it's {EMAIL}.")])
    check("a detail that IS on the card is given, exactly as listed",
          w.sent == [OPENING, f"Sure, it's {EMAIL}."] and c.ended_code == "chat_ended",
          (w.sent, c.ended_code))


def t_offer_card_denied_then_decline():
    fresh()
    holder = {}

    def on_read(n):
        c = holder.get("c")
        if c is None or c.offer is None or holder.get("done"):
            return
        if c.offer.get("verdict") and c.offer["verdict"] != "approved":
            holder["done"] = True
            holder["accept"] = S.answer(c.id, c.offer["id"], "accept")
            holder["yes"] = S.answer(c.id, c.offer["id"], "say", "Yes please, go ahead.")
            holder["leak"] = S.answer(c.id, c.offer["id"], "say", f"Email {OTHER_EMAIL}")
            holder["stale"] = S.answer(c.id, 99, "decline")
            holder["decline"] = S.answer(c.id, c.offer["id"], "decline")
    w = S.FakeWidget({1: [AGENT_OFFER], 2: ["No problem. This chat has ended."]},
                     on_read=on_read)
    d = world(w, moves=[reply(OPENING)], gate=deny_offers)
    c = S.plan("groupon", GOAL, details=DETAILS, deps=d)
    holder["c"] = c
    S.start(c, deps=d, wait=True)
    check("a card that says no accepts nothing; Decline sends the polite no",
          w.sent == [OPENING, S.DECLINE_LINE], w.sent)
    check("'accept' is not an answer here: accepting is only the card",
          holder["accept"][0] == 400)
    check("a typed 'yes' is refused: the only yes is one a card showed",
          holder["yes"][0] == 400 and "approve the offer card" in holder["yes"][1]["error"])
    check("typed words meet the same last check", holder["leak"][0] == 400)
    check("an answer to an offer that is not the waiting one is refused",
          holder["stale"][0] == 409)
    check("Decline was taken", holder["decline"][0] == 202)
    check("the offer's history says declined",
          [o["state"] for o in c.offers] == ["declined"], c.offers)


def t_holding_lines_and_time_out():
    fresh()
    later = []
    w = S.FakeWidget({1: [AGENT_OFFER]})
    c, d = go(w, moves=[reply(OPENING)], spawn=later.append)
    check("the card never answered: three holding lines, then the last one and a pause",
          w.sent == [OPENING, S.HOLD_LINE, S.HOLD_LINE, S.HOLD_LINE, S.FINAL_HOLD]
          and c.paused_code == "offer_timeout", (w.sent, c.paused_code))
    check("nothing was accepted", S.ACCEPT_LINE not in w.sent)
    gaps = [b["at"] - a["at"] for a, b in zip(
        [t for t in c.transcript if t.get("move") == "hold"],
        [t for t in c.transcript if t.get("move") == "hold"][1:])]
    check("holding lines at most every 2 minutes", all(g >= S.HOLD_EVERY for g in gaps), gaps)
    later[0]()
    check("a yes that comes after the pause accepts nothing",
          c.offers[0].get("late") == "approved" and S.ACCEPT_LINE not in w.sent)


def t_menu_buttons():
    fresh()
    w = S.FakeWidget({1: ["Connecting you to an agent.", "Hi, how can I help?"],
                      2: ["Thanks. This chat has ended."]},
                     menus={0: ["Refund", "Talk to an agent", "Other"], 1: []})
    c, d = go(w, moves=[{"move": "menu", "option": "Talk to an agent"}, reply(OPENING)])
    check("a menu button is pressed, exactly the label on screen",
          w.chosen == ["Talk to an agent"] and w.sent == [OPENING], (w.chosen, w.sent))
    check("...and it is in the transcript as a button Jarvis pressed",
          any(t.get("button") for t in c.transcript))
    fresh()
    w = S.FakeWidget({1: ["Your refund request is in. This chat has ended."]},
                     menus={0: ["Accept $45 refund", "Talk to an agent"]})
    c, d = go(w, moves=[{"move": "menu", "option": "Accept $45 refund"}])
    offer = [x for a, x, _ in CARDS if a == S.OFFER_ACTION]
    check("a button with offer words gets its own card first",
          offer and "presses exactly this button" in offer[0]["text"]
          and "Accept $45 refund" in offer[0]["text"])
    check("...and is pressed only after that card's yes", w.chosen == ["Accept $45 refund"])
    fresh()
    w = S.FakeWidget({}, menus={0: ["Talk to an agent"]})
    c, d = go(w, moves=[{"move": "menu", "option": "Cancel my order"},
                        {"move": "menu", "option": "Delete account"}])
    check("a button the chat does not show is never pressed", not w.chosen
          and c.paused_code == "blocked", (w.chosen, c.paused_code))


def t_a_chat_that_does_not_mark_own_lines():
    fresh()

    class Unmarked(S.FakeWidget):
        """Every line comes back as the company's, Jarvis's own included."""

        def read_new(self):
            return [dict(x, who="company") for x in super().read_new()]
    w = Unmarked({1: ["Thanks. This chat has ended."]})
    c, d = go(w, moves=[reply(OPENING), reply("A second message nobody asked for.")])
    check("Jarvis's own words coming back unmarked are still its own - it never answers "
          "itself", w.sent == [OPENING] and whos(c).count("company") == 0
          and c.ended_code == "chat_ended", (w.sent, whos(c)))


def t_quiet_agent_queue_and_no_chat():
    fresh()
    w = S.FakeWidget({1: ["Let me look into that for you."]})
    c, d = go(w, moves=[reply(OPENING)])
    check("a quiet agent: 'Are you still there?' once, then a pause",
          w.sent == [OPENING, S.STILL_THERE] and c.paused_code == "quiet",
          (w.sent, c.paused_code))
    fresh()
    w = S.FakeWidget({1: ["You are number 5 in the queue."]})
    c, d = go(w, moves=[reply(OPENING)])
    check("nobody answers: the queue's limit ends it; chat minutes not counted",
          c.ended_code == "limit_queue" and c.chat_seconds == 0.0 and c.queue_position == 5,
          (c.ended_code, c.chat_seconds))
    fresh()
    w = S.FakeWidget(statuses={0: CB.Status("needs_owner", S.NO_CHAT)})
    c, d = go(w, moves=[reply(OPENING)])
    check("the chat never opened: ends after the wait, nothing sent",
          c.ended_code == "no_chat" and w.sent == [] and not d.model.bodies[:-1],
          (c.ended_code, w.sent))
    fresh()
    w = S.FakeWidget({1: ["Hello?"]}, statuses={1: CB.Status("needs_owner", "captcha")})
    c, d = go(w, moves=[reply(OPENING)])
    check("a captcha pauses; Jarvis never solves it", c.paused_code == "captcha"
          and w.sent == [OPENING])
    fresh()
    w = S.FakeWidget(statuses={0: CB.Status("needs_owner", "a chat window from x.example, "
                                                           "which Jarvis does not recognise")})
    c, d = go(w)
    check("a chat window from an unknown host pauses, nothing typed",
          c.paused_code == "other" and w.sent == [] and "x.example" in c.paused_why)


def t_takeover_resume_and_stop():
    fresh()
    state = {}

    def on_read(n):
        c = state.get("c")
        if c is not None and n == 1 and not state.get("took"):
            state["took"] = True
            state["answer"] = S.takeover(c.id)
    w = S.FakeWidget({1: ["Hi, how can I help?"]}, on_read=on_read)
    d = world(w, moves=[reply(OPENING), {"move": "wait"}])
    c = S.plan("groupon", GOAL, details=DETAILS, deps=d)
    state["c"] = c
    S.start(c, deps=d, wait=True)
    check("Take over: Jarvis pauses and sends nothing more",
          c.state == "paused" and c.paused_code == "takeover" and w.sent == [OPENING]
          and state["answer"][0] == 200, (c.state, c.paused_code, w.sent))
    v = S.chat_view(c)
    check("both apps see 'take_over'", v["take_over"] is True)
    w.push("Actually the spa closed on 2 August, I checked.", who="own")
    d.clock.sleep(20 * 60)            # the owner took their time in the window
    w.push("Thanks for checking. This chat has ended.")
    rec = TC.paused()
    text = TC.resume_card_text(rec["id"], TC._paused[rec["id"]], S)
    check("Resume is its own card, in this chat's words",
          "Groupon's customer support" in text and "kept as yours" in text)
    code, _ = TC.resume(gate_check=lambda a, dt, p: Verdict(True, "approved"), wait=True)
    owner = [t for t in c.transcript if t["who"] == "owner"]
    check("after a long pause, Resume does not greet the agent with 'Are you still there?'",
          S.STILL_THERE not in w.sent, w.sent)
    check("what the owner typed in the window is kept as theirs, not Jarvis's",
          code == 202 and owner and owner[0]["outside_text"] is False
          and owner[0]["move"] == "window", (code, owner))
    fresh()
    w = S.FakeWidget({1: ["Let me check."]})
    w.on_read = lambda n: n == 1 and SA.stop_all("test")
    c, d = go(w, moves=[reply(OPENING)])
    check("Stop everything ends a support chat", c.state == "stopped" and w.closed == 1,
          c.state)
    check("the stopper is registered", S.STOPPER in SA.registered())
    fresh()
    w = S.FakeWidget({1: ["Are you a bot?"]})
    c, d = go(w, moves=[reply(OPENING)])
    code, _ = S.stop(c.id, deps=d)
    check("Stop on a paused chat ends it at once and closes the window",
          code == 200 and c.state == "stopped" and w.closed == 1)


def t_takeover_while_the_card_waits_and_a_waiting_driver():
    fresh()
    holder = {}

    def gate(action, detail, prompt):
        CARDS.append((action, detail, prompt))
        if action == S.ACTION:
            holder["take"] = S.takeover(holder["c"].id)
        return Verdict(True, "approved")
    w = S.FakeWidget({1: ["Hi"]})
    d = world(w, moves=[reply(OPENING)], gate=gate)
    c = S.plan("groupon", GOAL, details=DETAILS, deps=d)
    holder["c"] = c
    S.start(c, deps=d, wait=True)
    check("Take over pressed while the card waited: paused before anything is sent",
          holder["take"][0] == 200 and c.paused_code == "takeover" and w.sent == [],
          (holder["take"], c.paused_code, w.sent))
    fresh()
    w = S.FakeWidget({})
    c, d = go(w, moves=[{"move": "wait"}] * 50)
    asked = [b for b in d.model.bodies if b.get("format") == S.MOVE_SCHEMA]
    check("a driver that waits instead of writing the opening is asked once, and a chat "
          "that stays quiet ends like one never opened", len(asked) == 1
          and c.ended_code == "no_chat" and w.sent == [], (len(asked), c.ended_code))


def t_one_window_at_a_time():
    fresh()
    w = S.FakeWidget({1: ["Are you a bot?"]})
    c, d = go(w, moves=[reply(OPENING)])
    s = CB.plan("gemini_web", "What is a fern?", deps=CB.Deps(
        saved_facts=lambda m: [], make_adapter=lambda cid: CB.FakeChatbot(),
        allow_test_adapters=True))
    check("a chatbot conversation cannot start while a support chat is going",
          s.problem, s.problem)
    c2 = S.plan("groupon", GOAL, deps=d)
    check("nor a second support chat", "another support chat" in c2.problem, c2.problem)
    code, out = R.handle_post(R.START_ROUTE, {"chatbot": "fake", "goal": "x"}, deps=d)
    check("the chatbot route says why", code == 409 and "customer-support" in out["error"],
          out)


# ==========================================================================
#   The record, the export and the learner
# ==========================================================================

def t_history_record_export_and_learner():
    fresh()
    import jarvis_chat_log as CL
    folder = _TMP / "history"
    log = CL.ChatLog(folder / "h.db", folder / "h.json", lambda: bytes(range(32)))
    CL.use(log)
    try:
        w = S.FakeWidget({1: ["Could I have your order number?"],
                          2: ["Thanks. This chat has ended."]})
        c, d = go(w, moves=[reply(OPENING), reply(f"It's {ORDER}.")],
                  history=S._default_history)
        check("kept in the encrypted chat history", c.saved == "yes", c.saved)
        got = log.get("support-" + c.id)
        roles = {t["role"] for t in got["turns"]}
        check("every row is role 'support' - never 'user'", roles == {"support"}, roles)
        provs = [t["provenance"] for t in got["turns"]]
        check("each row says who wrote it", {"support_note", "support_jarvis",
                                             "support_company"} <= set(provs), provs)
        check("the whole record is marked as outside text", got["tainted"] is True)
        check("it is listed in History with its title",
              any(x["title"].startswith("Support chat with Groupon")
                  for x in log.list()["conversations"]))
        raw = (folder / "h.db").read_bytes()
        check("the words are encrypted on disk", ORDER.encode() not in raw
              and b"Could I have your order" not in raw)
        check("nothing entered the live-turn registry (the learner's record of the owner's "
              "own words)", log.live_turn_any(OPENING) is None
              and log.live_turn_any("Could I have your order number?") is None)
        import jarvis_auto_learn as AL
        check("the learner refuses the support chat's source",
              AL.check_source(S.SOURCE) != "")
        import jarvis_intake as IN
        msgs = [{"role": t["role"], "content": t["text"]} for t in got["turns"]]
        check("the learner reads nothing from the record (eval_learner's 'reads' rule)",
              IN.owner_turns(msgs, IN.ORIGIN_OWNER) == [])
        CL.use(log)
        log.set_enabled(False)
        c2 = S.SupportChat(id="sup_000000000abc", company="groupon", company_name="Groupon",
                           help_url="", hosts=(), goal="g", details=(),
                           limits=S.Limits(1, 1, 1), tier=c.tier,
                           transcript=[{"who": "company", "text": "hi", "at": 1}])
        why = S._keep(c2, d)
        check("history off: nothing kept, and it says why", why != "yes" and "off" in why, why)
    finally:
        CL.use(None)
    code, out = S.export(c.id)
    check("the export: the whole chat as text, saying it is not encrypted",
          code == 200 and out["filename"].startswith("jarvis-support-groupon-")
          and "NOT encrypted" in out["text"] and OPENING in out["text"]
          and "[outside text]" in out["text"])


# ==========================================================================
#   Routes
# ==========================================================================

def t_routes():
    fresh()
    w = S.FakeWidget({1: [AGENT_OFFER]})
    later = []
    d = world(w, moves=[reply(OPENING)], spawn=later.append)
    code, out = R.handle_post(R.SUPPORT_START_ROUTE, {"company": "groupon", "goal": GOAL,
                                                      "details": DETAILS}, deps=d, wait=True)
    check("start: 202, nothing sent before the card", code == 202 and out["asking"], out)
    sid = out["support"]
    code, st = R.handle_get(f"support={sid}", deps=d)
    sv = st["support"]
    check("status carries the chat, the companies and the version",
          code == 200 and sv["id"] == sid and sv["company_name"] == "Groupon"
          and [x["id"] for x in st["companies"]] == ["groupon", "other"]
          and st["support_tier"]["messages_max"] == 25, st.get("support_tier"))
    check("the view: never read aloud, details listed, the transcript",
          sv["read_aloud"] is False and sv["details"][0]["name"] == "Order number"
          and sv["transcript"])
    code, out = R.handle_post(R.SUPPORT_START_ROUTE, {"company": "groupon", "goal": GOAL,
                                                      "details": [{"name": "PIN",
                                                                   "value": "1"}]}, deps=d)
    check("a second chat while one is going is refused", code == 409, out)
    code, out = R.handle_post(R.SUPPORT_ANSWER_ROUTE, {"id": sid, "offer": 1,
                                                       "choice": "accept"}, deps=d)
    check("answer: accepting is refused (the card only)", code == 400, out)
    code, out = R.handle_post(R.SUPPORT_TAKEOVER_ROUTE, {"id": sid}, deps=d)
    check("take over on a paused chat says so", code == 200, out)
    code, out = R.handle_export(f"id={sid}")
    check("export: a read", code == 200 and "text" in out)
    code, out = R.handle_post(R.SUPPORT_STOP_ROUTE, {"id": sid}, deps=d)
    check("stop: 200", code == 200, out)
    check("bad ids are refused", R.handle_post(R.SUPPORT_STOP_ROUTE, {"id": "../x"}, deps=d)[0]
          == 400 and R.handle_get("support=nope", deps=d)[0] == 400
          and R.handle_export("id=x")[0] == 400)
    fresh()
    d = world(S.FakeWidget())
    code, out = R.handle_post(R.SUPPORT_START_ROUTE, {"company": "groupon", "goal": GOAL,
                                                      "details": [{"name": "Password",
                                                                   "value": "x"}]}, deps=d)
    check("a refused detail: 400, no card, the reason in a sentence",
          code == 400 and not CARDS and out["error"].endswith("."), out)
    TIERS[S.ACTION] = "never"
    code, out = R.handle_post(R.SUPPORT_START_ROUTE, {"company": "groupon", "goal": GOAL},
                              deps=d)
    check("switched off in the settings file: 409 saying so", code == 409
          and "switched off" in out["error"], out)


# ==========================================================================
#   Shipped and documented
# ==========================================================================

def t_shipped_and_documented():
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    for m in ("jarvis_support.py", "jarvis_support_widget.py"):
        check(f"shipped: {m} in _where.SHIPPED and apply-patches.ps1",
              m in SHIPPED and f"'{m}'" in ps1)
    check("support-chat.patch is in the patch list", "'support-chat.patch'" in ps1)
    patch = (HERE / "support-chat.patch").read_text(encoding="utf-8")
    check("the gate's risk lines: both cards leave the PC and cannot be taken back",
          '"support_chat": ("no", "outbound",' in patch
          and '"support_offer": ("no", "outbound",' in patch)
    start = ps1.index("$PATCHES = @(")
    names = [ln.strip().strip("'") for ln in ps1[start:ps1.index("\n)", start)].splitlines()
             if ln.strip().startswith("'")]
    # Right after forget-range.patch (its context in jarvis_gate.py). The
    # patches after it since GitHub's main was merged (brain-reads ->
    # history-import, 2026-09-28) touch jarvis_hud.py only, never the gate.
    at = names.index("support-chat.patch") if "support-chat.patch" in names else -1
    later_gate = [n for n in names[at + 1:]
                  if "+++ b/jarvis_gate.py" in (HERE / n).read_text(encoding="utf-8")] if at >= 0 else []
    check("support-chat.patch comes right after forget-range.patch (its context), "
          "and no later patch touches jarvis_gate.py",
          at > 0 and names[at - 1] == "forget-range.patch" and not later_gate,
          (names[at - 1:at + 2], later_gate))
    try:
        import _stack
        text, log = _stack.stand_in("jarvis_gate.py")
        mine = [ln for ln in log if ln.startswith("support-chat")]
        check("support-chat.patch applies to jarvis_gate.py on the whole stack",
              text is not None and '"support_offer": ("no", "outbound"' in text
              and '"support_chat",  # jarvis_support.py' in text and not mine,
              (log[-3:], mine))
    except Exception as exc:
        check("the stack could be rehearsed", False, repr(exc))
    import jarvis_card_words as W
    import jarvis_asks_first as AF
    for a in (S.ACTION, S.OFFER_ACTION):
        check(f"{a}: a plain card title", W.title_for(a).startswith("Jarvis wants to"),
              W.title_for(a))
        check(f"{a}: 'What asks first' lists it, always asks, never loosened",
              a in AF.HARD_LIMITS and a in AF.MUST_ASK
              and any(a in rows for _, rows in AF.GROUPS) and a not in AF.SWITCHABLE)
    toml = tomllib.loads((HERE / "rebuilt" / "jarvis-framework.toml").read_text("utf-8"))
    check("the shipped tiers are ask", toml["autonomy"]["tiers"].get(S.ACTION) == "ask"
          and toml["autonomy"]["tiers"].get(S.OFFER_ACTION) == "ask")
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    check("JARVIS-API.md has the section with every route",
          "## 65. Customer-support chats" in api
          and all(r in api for r in (R.SUPPORT_START_ROUTE, R.SUPPORT_STOP_ROUTE,
                                     R.SUPPORT_TAKEOVER_ROUTE, R.SUPPORT_ANSWER_ROUTE,
                                     R.SUPPORT_EXPORT_ROUTE)))
    import jarvis_reach as RE
    check("'What Jarvis can reach' has a row for it", any(k == "support_chat"
                                                          for k, _ in RE.KINDS))


def main():
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:  # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        import shutil
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
