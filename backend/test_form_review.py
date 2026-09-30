"""Fill in the form, show me, then send it (the owner's decision of 2026-09-30;
docs/FORM-REVIEW-DESIGN.md): jarvis_browser_control.py's `final` step and
`review` hook, jarvis_form_review.py (the second card, the picture, the
route) and jarvis_agent.py's wiring of both.

What is proven, each with the real code and injected fakes (no browser, no
network, no model):

  - a request may mark ONE final click; only a click, only the last step,
    otherwise it is unmatched in words; a plan with no final step is
    unchanged;
  - run() does the fields, STOPS, takes one picture, asks the review hook,
    and only on an explicit yes - and a page still exactly as it was (address,
    the button, every field, a deeper fingerprint) - clicks;
  - no hook, a hook that raises, a denial, a timeout, a "yes" that is not
    exactly True, a page that changed while the picture was taken, a page
    that changed after the owner looked, a Stop that arrived while the card
    waited: each sends NOTHING;
  - a saved secret appears on the card by name only;
  - the picture: in memory only (nothing written anywhere, nothing printed
    or logged, nothing on a socket), never given to a model (nothing it
    imports or calls could), one at a time, dropped when the card is decided
    (even when the gate raises) and when it expires, served only while its
    card waits and only behind the origin and token checks;
  - the agent refuses a final step outright on a turn that read outside
    text, or a model that is not on this PC, and a headless browser gets no
    picture but still the second card.

    python3 test_form_review.py
"""
import ast
import base64
import builtins
import contextlib
import io
import json
import logging
import os
import socket
import sys
import tempfile
import traceback
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _where import BACKEND, REPO, require_shipped  # noqa: E402
require_shipped("jarvis_browser_control.py", "jarvis_form_review.py", "jarvis_agent.py")
import jarvis_browser_control as B  # noqa: E402
import jarvis_form_review as FR  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   A fake form page
# --------------------------------------------------------------------------

class Form:
    """A booking form. `read` is what the page reader would return, `act` what
    a browser would do; clicking Submit records a SEND - the thing that must
    not happen without a yes."""

    def __init__(self, url="https://clinic.example/book", password=False):
        self.url = url
        self.values = {"Name": "", "Phone": ""}
        self.password = "" if password else None
        self.sent = []
        self.submit = True
        self.submit_enabled = True
        self.order = []

    def elements(self):
        els = [{"role": "textbox", "name": n, "text": v or n, "enabled": True}
               for n, v in self.values.items()]
        if self.password is not None:
            els.append({"role": "textbox", "name": "Password", "text": "Password",
                        "enabled": True, "password": True, "sensitive": True})
        if self.submit:
            els.append({"role": "button", "name": "Submit", "text": "Submit",
                        "enabled": self.submit_enabled})
        return els

    def read(self, session):
        return {"url": self.url, "title": "Book", "elements": self.elements(), "events": []}

    def observe(self, session):
        return {"url": self.url, "events": []}

    def act(self, step):
        self.order.append(f"act:{step.action}:{step.name}")
        if step.action == "type":
            if step.name == "Password":
                self.password = step.value
            else:
                self.values[step.name] = step.value
        elif step.action == "click" and step.name == "Submit":
            self.sent.append(dict(self.values))
        return None


REQS = [
    {"role": "textbox", "name": "Name", "action": "type", "value": "Alex Kim", "why": "name"},
    {"role": "textbox", "name": "Phone", "action": "type", "value": "555 0100", "why": "phone"},
    {"role": "button", "name": "Submit", "action": "click", "why": "send it",
     "leaves_machine": True, "final": True},
]


def make_plan(form, reqs=REQS, **kw):
    return B.plan("book a visit", "s", [dict(r) for r in reqs], read=form.read, **kw)


def go(form, plan, **kw):
    return B.run(plan, read=form.read, act=form.act, observe=form.observe, approved=True, **kw)


def yes(info):
    return {"approved": True, "reason": ""}


def no_click(form):
    return form.sent == []


# --------------------------------------------------------------------------
#   plan() and describe()
# --------------------------------------------------------------------------

def t_a_final_click_is_planned_and_the_card_says_it_waits_for_a_second_card():
    f = Form()
    p = make_plan(f)
    check("all three requests became steps", len(p.steps) == 3 and not p.unmatched, repr(p.unmatched))
    check("only the click is final, and it is marked heavy",
          [s.final for s in p.steps] == [False, False, True] and p.steps[2].heavy)
    card = B.describe(p)
    check("the plan card says the last step waits for a SECOND card",
          "SECOND" in card and "FINAL STEP" in card and "nothing is sent unless you approve" in card.lower(),
          card)
    check("the step dict carries final", p.steps[2].as_dict()["final"] is True)


def t_final_is_only_a_click_only_one_and_only_last():
    f = Form()
    p = make_plan(f, [dict(REQS[0], final=True), REQS[2]])
    check("a final TYPE is unmatched, in words",
          any("only a click" in u["reason"] for u in p.unmatched), repr(p.unmatched))
    check("the final click itself still stands", [s.final for s in p.steps] == [True])
    p = make_plan(f, [REQS[0], dict(REQS[2]), dict(REQS[2], name="Submit")])
    check("two finals: none is kept (no telling which was meant)",
          not any(s.final for s in p.steps) and len(p.unmatched) == 2
          and all("only one" in u["reason"] for u in p.unmatched), repr((p.steps, p.unmatched)))
    p = make_plan(f, [REQS[2], REQS[0]])
    check("a final that is not last is unmatched, in words, and the other step stays",
          len(p.steps) == 1 and p.steps[0].action == "type" and len(p.unmatched) == 1
          and "LAST" in p.unmatched[0]["reason"], repr((p.steps, p.unmatched)))
    p = make_plan(f, [REQS[0], dict(REQS[2], final="yes")])
    check("a final that is not a real boolean is unmatched",
          any("true or false" in u["reason"] for u in p.unmatched), repr(p.unmatched))
    p = make_plan(f, [REQS[0], dict(REQS[2], final=False)])
    check("final false is an ordinary click", len(p.steps) == 2 and not p.steps[1].final)


def t_a_plan_without_final_is_unchanged():
    f = Form()
    reqs = [REQS[0], REQS[1], {k: v for k, v in REQS[2].items() if k != "final"}]
    p = make_plan(f, reqs)
    card = B.describe(p)
    check("no second-card wording on a plan without a final step",
          "SECOND" not in card and "FINAL" not in card, card)
    calls = []
    out = go(f, p, review=lambda i: calls.append(i) or {"approved": False},
             snapshot=lambda s: calls.append("snap"))
    check("it runs to the end exactly as before, the hooks are never used",
          out["ok"] is True and f.sent == [{"Name": "Alex Kim", "Phone": "555 0100"}] and calls == []
          and "form_review" not in out, repr(out))


def t_a_hand_built_plan_with_a_misplaced_final_is_refused_whole():
    f = Form()
    p = make_plan(f)
    p.steps.reverse()
    out = go(f, p, review=yes)
    check("refused whole, nothing done", out["ok"] is False and out["done"] == [] and no_click(f)
          and f.order == [], repr(out))


# --------------------------------------------------------------------------
#   run(): the stop, the picture, the second question, the last check
# --------------------------------------------------------------------------

def t_run_fills_stops_shows_asks_then_clicks_in_that_order():
    f = Form()
    p = make_plan(f)
    seen = {}

    def snapshot(session):
        f.order.append("snapshot")
        return {"jpeg": b"PIC", "width": 10, "height": 10}

    def review(info):
        f.order.append("review")
        seen.update(info)
        return {"approved": True, "reason": ""}

    out = go(f, p, review=review, snapshot=snapshot)
    check("fields, then the picture, then the question, then the click",
          f.order == ["act:type:Name", "act:type:Phone", "snapshot", "review", "act:click:Submit"],
          repr(f.order))
    check("sent exactly once, with the typed values", f.sent == [{"Name": "Alex Kim", "Phone": "555 0100"}])
    check("the run finished and says it was shown and approved",
          out["ok"] is True and out["form_review"] == {"shown": True, "approved": True}, repr(out))
    check("the review got the site, every typed word, the button and the picture",
          seen["site"] == "clinic.example"
          and [(s["action"], s["name"], s["value"]) for s in seen["steps"]]
          == [("type", "Name", "Alex Kim"), ("type", "Phone", "555 0100")]
          and seen["final"]["name"] == "Submit" and seen["picture"]["jpeg"] == b"PIC"
          and seen["no_picture"] == "", repr(seen))


def t_nothing_is_sent_without_a_yes():
    cases = {
        "no hook at all": dict(),
        "a hook that raises": dict(review=lambda i: (_ for _ in ()).throw(RuntimeError("boom"))),
        "a denial": dict(review=lambda i: {"approved": False, "reason": "you said no"}),
        "a hook that returns nothing": dict(review=lambda i: None),
        "a truthy yes that is not True": dict(review=lambda i: {"approved": "yes"}),
        "a bare True (not the dict)": dict(review=lambda i: True),
    }
    for label, kw in cases.items():
        f = Form()
        out = go(f, make_plan(f), **kw)
        check(f"{label}: nothing is sent", no_click(f) and out["ok"] is False
              and out.get("submitted") is False, repr(out))
        check(f"{label}: the earlier fields WERE filled and the final step is reported not run",
              f.values["Name"] == "Alex Kim" and out["not_run"][-1]["name"] == "Submit"
              and "nothing was sent" in out["reason"].lower(), repr(out))
    f = Form()
    out = go(f, make_plan(f))
    check("no hook: says plainly there is no way to show the form",
          "no way here to show" in out["reason"], out["reason"])
    f = Form()
    out = go(f, make_plan(f), review=lambda i: {"approved": False, "reason": "you said no"})
    check("a denial leaves the form open for the owner, and says so",
          "still open" in out["reason"] and out["form_review"] == {"shown": True, "approved": False},
          repr(out))


def t_a_page_that_changes_after_the_owner_looked_is_not_submitted():
    def tamper(label, fn, words):
        f = Form()

        def review(info):
            fn(f)
            return {"approved": True, "reason": ""}
        out = go(f, make_plan(f), review=review, snapshot=lambda s: {"jpeg": b"x", "width": 1, "height": 1})
        check(f"{label}: nothing is sent", no_click(f) and out["ok"] is False, repr(out))
        check(f"{label}: the reason says the page changed after the owner looked",
              words in out["reason"], out["reason"])

    tamper("a field was edited", lambda f: f.values.__setitem__("Phone", "999 9999"),
           "changed after you looked")
    tamper("a field was added", lambda f: f.values.__setitem__("Extra", ""), "changed after you looked")
    tamper("the address changed", lambda f: setattr(f, "url", "https://clinic.example/other"),
           "changed after you looked")
    tamper("the button went away", lambda f: setattr(f, "submit", False),
           "no longer there exactly once")
    tamper("the button was disabled", lambda f: setattr(f, "submit_enabled", False),
           "no longer there exactly once")
    tamper("it moved to another site", lambda f: setattr(f, "url", "https://evil.example/"),
           "outside the allowed sites")


def t_the_deeper_fingerprint_catches_what_the_page_reader_cannot_see():
    f = Form(password=True)
    box = {"pw": "one"}
    reqs = [REQS[0], {"role": "textbox", "name": "Password", "action": "type",
                      "value": "<secret>pw</secret>", "why": "log in"}, REQS[2]]
    p = make_plan(f, reqs)
    out = go(f, p, review=lambda i: box.__setitem__("pw", "two") or {"approved": True},
             snapshot=lambda s: {"jpeg": b"x", "width": 1, "height": 1},
             fingerprint=lambda s: box["pw"], secrets=lambda n, h: "sekrit")
    check("a field only the deeper look can see changed: nothing is sent",
          no_click(f) and out["ok"] is False and "changed after you looked" in out["reason"],
          repr(out))
    f = Form(password=True)
    out = go(f, make_plan(f, reqs), review=lambda i: {"approved": True},
             snapshot=lambda s: {"jpeg": b"x", "width": 1, "height": 1},
             fingerprint=lambda s: "same", secrets=lambda n, h: "sekrit")
    check("CONTROL: an unchanged deeper fingerprint goes through", out["ok"] is True and len(f.sent) == 1, repr(out))
    f = Form(password=True)

    def broken(session):
        raise RuntimeError("cannot look")
    out = go(f, make_plan(f, reqs), review=lambda i: {"approved": True},
             snapshot=lambda s: {"jpeg": b"x", "width": 1, "height": 1},
             fingerprint=broken, secrets=lambda n, h: "sekrit")
    check("a deeper look that cannot be taken stops the run before anyone is asked",
          no_click(f) and out["ok"] is False and "could not be checked" in out["reason"]
          and out.get("form_review", {}).get("shown") is False, repr(out))


def t_a_page_that_moves_while_the_picture_is_taken_stops_before_the_question():
    f = Form()
    asked = []

    def snapshot(session):
        f.values["Name"] = "Someone else"
        return {"jpeg": b"x", "width": 1, "height": 1}
    out = go(f, make_plan(f), review=lambda i: asked.append(1) or {"approved": True},
             snapshot=snapshot)
    check("the owner is never shown a picture of a page that moved under it",
          asked == [] and no_click(f) and "changed while" in out["reason"], repr(out))


def t_a_stop_that_arrives_while_the_card_waits_wins_over_the_yes():
    f = Form()
    sig = {"v": None}
    out = go(f, make_plan(f), review=lambda i: sig.__setitem__("v", "stop") or {"approved": True},
             checkpoint=lambda: sig["v"])
    check("stopped: nothing is sent", no_click(f) and out["ok"] is False
          and "stopped by request" in out["reason"], repr(out))


def t_a_saved_secret_is_shown_by_name_only():
    f = Form(password=True)
    reqs = [REQS[0], {"role": "textbox", "name": "Password", "action": "type",
                      "value": "<secret>clinic_pw</secret>", "why": "log in"}, REQS[2]]
    got = {}
    out = go(f, make_plan(f, reqs), secrets=lambda n, h: "hunter2-REAL",
             review=lambda info: got.update(info) or {"approved": True})
    shown = json.dumps(got, default=str)
    check("the review info names the secret and never holds its value",
          "clinic_pw" in shown and "hunter2-REAL" not in shown, shown)
    card = FR.card_text(got, has_picture=False)
    check("the card names it, never shows it", "clinic_pw" in card and "hunter2-REAL" not in card, card)
    check("the result holds no secret", "hunter2-REAL" not in json.dumps(out, default=str))
    check("it was typed for real, into the page", f.password == "hunter2-REAL")


def t_a_browser_with_no_window_asks_the_same_question_with_no_picture():
    f = Form()
    got = {}
    out = go(f, make_plan(f), review=lambda info: got.update(info) or {"approved": True})
    check("no snapshot hook: no picture, and it says why", got["picture"] is None
          and "no window" in got["no_picture"], repr(got))
    check("the second question was still asked before the click", out["ok"] is True
          and out["form_review"]["shown"] is True)
    card = FR.card_text(got, has_picture=False)
    check("the card says there is no picture and to read the words",
          "No picture - this browser has no window" in card and "Read the words" in card, card)
    f = Form()
    got = {}

    def boom(session):
        raise FR.NoPicture("the page is too big to show in one picture here")
    go(f, make_plan(f), review=lambda info: got.update(info) or {"approved": True}, snapshot=boom)
    check("a picture that cannot be made is explained in the words written for the owner",
          got["picture"] is None and "too big" in got["no_picture"], repr(got))
    f = Form()
    got = {}

    def odd(session):
        raise ValueError("SECRET PAGE WORDS")
    go(f, make_plan(f), review=lambda info: got.update(info) or {"approved": True}, snapshot=odd)
    check("any other error is named by its type only, never its text",
          "SECRET PAGE WORDS" not in got["no_picture"] and "ValueError" in got["no_picture"],
          got["no_picture"])


# --------------------------------------------------------------------------
#   jarvis_form_review: the card, the store, the picture
# --------------------------------------------------------------------------

class Verdict:
    def __init__(self, allowed=True, outcome="approved", tier="ask", reason=""):
        self.allowed, self.outcome, self.tier, self.reason = allowed, outcome, tier, reason


def fake_jpeg(w=800, h=600, size=None):
    body = (b"\xff\xd8" + b"\xff\xc0" + (17).to_bytes(2, "big") + b"\x08"
            + h.to_bytes(2, "big") + w.to_bytes(2, "big") + b"\x03" + b"\x00" * 9)
    if size and len(body) < size:
        body += b"\x00" * (size - len(body))
    return body


def sample_info(picture=True, **over):
    info = {"site": "clinic.example", "goal": "book", "engine": "visible",
            "steps": [{"action": "type", "role": "textbox", "name": "Name", "within": "",
                       "value": "Alex Kim"},
                      {"action": "type", "role": "textbox", "name": "Phone", "within": "",
                       "value": "555 0100"}],
            "final": {"role": "button", "name": "Submit", "within": "", "why": "send"},
            "picture": ({"jpeg": fake_jpeg(), "width": 800, "height": 600} if picture else None),
            "no_picture": "" if picture else FR.NO_WINDOW}
    info.update(over)
    return info


def t_the_second_card_shows_the_site_every_word_and_the_button():
    card = FR.card_text(sample_info(), has_picture=True)
    check("the site is named", "clinic.example" in card, card)
    check("every typed value is on the card as text", "'Alex Kim'" in card and "'555 0100'" in card, card)
    check('it ends with what will be clicked and that it cannot be undone',
          'Jarvis will now click button "Submit". It cannot be undone.' in card, card)
    check("it says the picture is unhidden and to check every detail",
          "nothing in it is hidden" in card, card)
    check("it says what a no does", "If you say no: nothing is sent" in card, card)


def t_the_hook_raises_the_card_with_the_picture_id_and_drops_the_picture_after():
    FR._reset_for_tests()
    calls, during = [], {}

    def checker(action, detail, prompt):
        calls.append((action, detail, prompt))
        pid = detail.get("picture")
        during["code"], during["body"] = FR.handle_get(f"id={pid}")
        during["held"] = FR.held()
        return Verdict(True, "approved")
    review = FR.make_review(checker, tier_of=lambda a: "ask")
    verdict = review(sample_info())
    check("approved on a person's yes", verdict == {"approved": True, "reason": ""}, repr(verdict))
    check("the card is the gate action browser_form_submit, tier ask",
          calls[0][0] == "browser_form_submit" == FR.ACTION)
    detail = calls[0][1]
    check("detail is the text and the picture id, nothing else",
          set(detail) == {"text", "picture"} and isinstance(detail["picture"], str)
          and len(detail["picture"]) >= 16 and "clinic.example" in detail["text"], repr(detail)[:200])
    check("while the card waited the picture was served",
          during["code"] == 200 and during["body"]["ok"] is True
          and base64.b64decode(during["body"]["jpeg"]) == fake_jpeg()
          and (during["body"]["width"], during["body"]["height"]) == (800, 600), repr(during)[:200])
    check("one picture held during the card", during["held"] == 1)
    check("after the decision it is dropped, and the route is a 404",
          FR.held() == 0 and FR.handle_get(f"id={detail['picture']}") == (404, {"ok": False}))


def t_no_picture_means_no_picture_key_and_the_card_says_why():
    FR._reset_for_tests()
    calls = []
    review = FR.make_review(lambda a, d, p: calls.append(d) or Verdict(True), tier_of=lambda a: "ask")
    review(sample_info(picture=False))
    check("no picture key on the detail when there is none", set(calls[0]) == {"text"}, repr(calls[0])[:100])
    check("and the card says there is no window", "No picture - this browser has no window" in calls[0]["text"])


def t_denied_timed_out_and_not_ask_tier_never_approve():
    FR._reset_for_tests()
    for verdict, words in ((Verdict(False, "denied"), "you said no"),
                           (Verdict(False, "timed_out"), "ran out of time"),
                           (Verdict(True, "auto", tier="auto"), ""),
                           (Verdict(True, None, tier="notify"), "")):
        r = FR.make_review(lambda a, d, p, v=verdict: v, tier_of=lambda a: "ask")(sample_info())
        check(f"{verdict.outcome}/{verdict.tier}: not approved", r["approved"] is False
              and words in r["reason"], repr(r))
    asked = []
    r = FR.make_review(lambda *a: asked.append(1) or Verdict(True), tier_of=lambda a: "auto")(sample_info())
    check("a tier that is not ask raises no card at all", asked == [] and r["approved"] is False
          and "not set to" in r["reason"], repr(r))
    r = FR.make_review(lambda *a: asked.append(1) or Verdict(True), tier_of=lambda a: "ask",
                       cannot_ask=lambda: "too many cards")(sample_info())
    check("the turn's card limit refuses without a card", asked == [] and r["reason"] == "too many cards")
    long_info = sample_info()
    long_info["steps"] = [dict(long_info["steps"][0], value="x" * 5000)]
    r = FR.make_review(lambda *a: asked.append(1) or Verdict(True), tier_of=lambda a: "ask")(long_info)
    check("a form too long to show whole is refused, never cut", asked == [] and "too long" in r["reason"],
          repr(r))
    check("nothing was held for any of these", FR.held() == 0)


def t_the_picture_is_dropped_even_when_the_gate_raises():
    FR._reset_for_tests()

    def checker(a, d, p):
        raise RuntimeError("gate down")
    try:
        FR.make_review(checker, tier_of=lambda a: "ask")(sample_info())
        raised = False
    except RuntimeError:
        raised = True
    check("the error reaches run() (which then sends nothing)", raised)
    check("and no picture is left behind", FR.held() == 0)


def t_one_picture_at_a_time_and_ten_minutes_at_most():
    FR._reset_for_tests()
    now = [1000.0]
    FR._clock = lambda: now[0]
    try:
        a = FR.put(b"A", 1, 1)
        b = FR.put(b"B", 1, 1)
        check("a new review drops the old picture", FR.get(a) is None and FR.get(b) is not None
              and FR.held() == 1)
        now[0] += FR.KEEP_SECONDS - 1
        check("still there just inside ten minutes", FR.get(b) is not None)
        now[0] += 2
        check("gone after ten minutes", FR.get(b) is None and FR.held() == 0
              and FR.handle_get(f"id={b}") == (404, {"ok": False}))
        check("ten minutes is what the design says", FR.KEEP_SECONDS == 600)
    finally:
        FR._reset_for_tests()


def t_the_route_answers_only_for_an_id_whose_card_waits():
    FR._reset_for_tests()
    pid = FR.put(fake_jpeg(), 800, 600)
    check("a real id is served", FR.handle_get(f"id={pid}")[0] == 200)
    for label, q in (("no id", ""), ("a guess", "id=" + "a" * 24), ("a short id", "id=abc"),
                     ("a path trick", "id=../../etc/passwd")):
        code, body = FR.handle_get(q)
        check(f"{label}: 404 and {{'ok': false}} only", (code, body) == (404, {"ok": False}), repr((code, body)))
    FR.drop(pid)
    check("a decided card's id is a 404", FR.handle_get(f"id={pid}") == (404, {"ok": False}))


class H:
    """A stand-in for the server's request handler."""
    def __init__(self, path):
        self.path = path
        self.sent = None

    def _send(self, code, body):
        self.sent = (code, body)

    def do_GET(self):
        self.sent = ("original", self.path)


def t_the_route_sits_behind_the_origin_and_token_checks():
    FR._reset_for_tests()
    ok = {"origin": True, "token": True}

    class Hd(H):
        pass
    line = FR.install(Hd, origin_ok=lambda s: ok["origin"], token_ok=lambda s: ok["token"])
    check("install says it is on", "Form review" in line, line)
    check("installing twice is harmless", "already on" in FR.install(
        Hd, origin_ok=lambda s: True, token_ok=lambda s: True))
    pid = FR.put(fake_jpeg(), 800, 600)
    h = Hd(f"/api/form-review/picture?id={pid}")
    h.do_GET()
    check("both checks pass: the picture", h.sent[0] == 200 and h.sent[1]["ok"] is True, repr(h.sent)[:100])
    ok["origin"] = False
    h = Hd(f"/api/form-review/picture?id={pid}")
    h.do_GET()
    check("a foreign origin is a 403 and no picture", h.sent[0] == 403 and "jpeg" not in h.sent[1])
    ok["origin"], ok["token"] = True, False
    h = Hd(f"/api/form-review/picture?id={pid}")
    h.do_GET()
    check("a bad token is a 401 and no picture", h.sent[0] == 401 and "jpeg" not in h.sent[1])
    ok["token"] = True
    h = Hd("/api/form-review/picture?id=" + "z" * 24)
    h.do_GET()
    check("a wrong id is a 404 {'ok': false}", h.sent == (404, {"ok": False}), repr(h.sent))
    h = Hd("/api/status")
    h.do_GET()
    check("every other route goes straight to the original", h.sent == ("original", "/api/status"))


def t_capture_takes_one_whole_page_jpeg_inside_the_caps():
    shots = []

    class Page:
        def screenshot(self, **kw):
            shots.append(kw)
            return fake_jpeg(1200, 900)
    B._sessions["fr-test"] = Page()
    try:
        pic = FR.capture("fr-test")
    finally:
        B._sessions.pop("fr-test", None)
    check("a whole-page JPEG at quality 70", shots[0]["type"] == "jpeg" and shots[0]["quality"] == 70
          and shots[0]["full_page"] is True, repr(shots))
    check("a picture inside the caps is used as taken", pic["width"] == 1200 and pic["height"] == 900
          and pic["jpeg"] == fake_jpeg(1200, 900))
    for label, data in (("too tall", fake_jpeg(800, 4000)), ("too many bytes", fake_jpeg(800, 600, FR.MAX_BYTES + 10))):
        try:
            import PIL  # noqa: F401
            have_pil = True
        except Exception:
            have_pil = False
        try:
            FR.fit(data)
            scaled = True
        except FR.NoPicture as exc:
            scaled, why = False, exc.plain
        if have_pil:
            check(f"{label}: Pillow present - not refused for size alone", True)
        else:
            check(f"{label}: with no Pillow it is refused in words, never sent unscaled",
                  scaled is False and "too big" in why, why if not scaled else "was sent")
    try:
        FR.fit(b"not a jpeg")
        bad = False
    except FR.NoPicture:
        bad = True
    check("something that is not a JPEG is refused", bad)
    try:
        FR.capture("no-such-tab")
        none = False
    except FR.NoPicture as exc:
        none = "not open" in exc.plain
    check("no open tab: no picture, in words", none)
    check("the caps are the design's",
          (FR.MAX_SIDE, FR.JPEG_QUALITY, FR.MAX_BYTES) == (1600, 70, int(1.5 * 1024 * 1024)))


def t_fingerprint_hashes_every_fields_content_and_keeps_none_of_it():
    rows = {"v": [["INPUT", "text", "n", "i", "abc", "false"]]}

    class Page:
        def evaluate(self, js):
            return rows["v"]
    B._sessions["fr-fp"] = Page()
    try:
        a = FR.fingerprint("fr-fp")
        rows["v"] = [["INPUT", "text", "n", "i", "abd", "false"]]
        b = FR.fingerprint("fr-fp")
    finally:
        B._sessions.pop("fr-fp", None)
    check("a hash that changes when a field does, and is not the content",
          a != b and len(a) == 64 and "abc" not in a)


# --------------------------------------------------------------------------
#   Memory only, never a model, never logged
# --------------------------------------------------------------------------

def t_the_picture_lives_in_memory_only_and_reaches_nothing_but_the_route():
    FR._reset_for_tests()
    pic_bytes = fake_jpeg(800, 600, 4000)
    pic_b64 = base64.b64encode(pic_bytes).decode("ascii")
    writes, sockets = [], []
    real_open, real_io_open, real_os_open = builtins.open, io.open, os.open
    real_connect = socket.socket.connect

    def spy(real):
        def inner(file, mode="r", *a, **k):
            if isinstance(mode, str) and any(c in mode for c in "wax+"):
                writes.append(str(file))
            return real(file, mode, *a, **k)
        return inner

    def spy_os(path, flags, *a, **k):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND):
            writes.append(str(path))
        return real_os_open(path, flags, *a, **k)

    def spy_connect(self, addr):
        sockets.append(addr)
        raise OSError("no network in this test")

    records = []

    class Grab(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())
    grab = Grab(level=logging.DEBUG)
    logging.getLogger().addHandler(grab)
    old_level = logging.getLogger().level
    logging.getLogger().setLevel(logging.DEBUG)
    out_buf, err_buf = io.StringIO(), io.StringIO()
    env_before = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE", "TMPDIR", "TEMP", "TMP")}
    with tempfile.TemporaryDirectory() as tmp:
        for k in env_before:
            os.environ[k] = tmp
        builtins.open, io.open, os.open = spy(real_open), spy(real_io_open), spy_os
        socket.socket.connect = spy_connect
        try:
            with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
                f = Form()
                seen = {}

                def checker(action, detail, prompt):
                    seen["detail"], seen["prompt"] = detail, prompt
                    seen["served"] = FR.handle_get(f"id={detail['picture']}")
                    return Verdict(True, "approved")
                review = FR.make_review(checker, tier_of=lambda a: "ask")
                out = go(f, make_plan(f), review=review,
                         snapshot=lambda s: {"jpeg": pic_bytes, "width": 800, "height": 600})
        finally:
            builtins.open, io.open, os.open = real_open, real_io_open, real_os_open
            socket.socket.connect = real_connect
            logging.getLogger().removeHandler(grab)
            logging.getLogger().setLevel(old_level)
            for k, v in env_before.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        left = list(Path(tmp).rglob("*"))
    check("the flow really ran and the picture was really served", out["ok"] is True
          and seen["served"][0] == 200 and seen["served"][1]["jpeg"] == pic_b64)
    check("nothing was opened for writing anywhere", writes == [], repr(writes))
    check("nothing appeared in the temp folder or the home folder", left == [], repr(left))
    check("no network connection was tried", sockets == [], repr(sockets))
    check("nothing was printed", pic_b64 not in out_buf.getvalue() + err_buf.getvalue()
          and b"\xff\xd8" not in (out_buf.getvalue() + err_buf.getvalue()).encode("latin-1", "ignore"))
    check("nothing was logged", not any(pic_b64[:40] in r or "jpeg" in r.lower() for r in records),
          repr(records)[:200])
    check("the gate's detail and prompt hold the id and words, never the picture",
          pic_b64[:40] not in json.dumps(seen["detail"]) + seen["prompt"]
          and pic_b64[:40] not in json.dumps(out, default=str))
    check("and the store is empty again", FR.held() == 0)


def t_the_picture_module_cannot_reach_a_model_the_disk_or_a_log():
    src = (BACKEND / "jarvis_form_review.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported, names, calls = set(), set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.add(node.func.id)
    top = {m.split(".")[0] for m in imported}
    check("it imports nothing that talks to a network or a model",
          not (top & {"requests", "socket", "jarvis_screen", "jarvis_picture", "jarvis_models",
                      "jarvis_agent", "jarvis_ocr", "jarvis_screen_picture", "jarvis_chatbot",
                      "ollama", "logging", "subprocess", "http"})
          and "urllib.request" not in imported, repr(sorted(imported)))
    check("it never cleans, writes, prints or logs a picture",
          not (names & {"clean_picture", "write_bytes", "write_text", "urlopen", "getLogger",
                        "NamedTemporaryFile", "mkstemp", "TemporaryDirectory"})
          and not (calls & {"open", "print"}),
          repr(sorted((names | calls) & {"clean_picture", "write_bytes", "write_text", "print", "open"})))


# --------------------------------------------------------------------------
#   The agent's wiring
# --------------------------------------------------------------------------

def _agent():
    return __import__("jarvis_agent")


LOCAL = {"url": "http://127.0.0.1:11434", "model": "qwen3:8b"}


def _watch(AG, *, tainted=False, lane=LOCAL, provenance="typed"):
    msgs = [{"role": "user", "content": "book me a visit"}]
    w = AG._TurnWatch(msgs, {"messages": [dict(msgs[0], provenance=provenance)]}, tainted=tainted)
    w.lane = lane
    return w


def t_the_agent_refuses_a_final_step_on_an_outside_text_turn_or_a_non_local_model():
    AG = _agent()
    args = {"goal": "book", "session": "s", "requests": [dict(r) for r in REQS]}
    plain = {"goal": "book", "session": "s", "requests": [dict(REQS[0])]}
    check("a clean typed turn on this PC's model: allowed",
          AG._form_review_refusal(args, _watch(AG)) == "")
    check("no final step: nothing to refuse, even on a tainted turn",
          AG._form_review_refusal(plain, _watch(AG, tainted=True)) == "")
    w = _watch(AG, tainted=True)
    check("a tainted conversation is refused", AG._form_review_refusal(args, w) == AG.FORM_REVIEW_OUTSIDE)
    w = _watch(AG)
    w.read["web_search"] = 1
    check("a turn that read outside text is refused", AG._form_review_refusal(args, w) == AG.FORM_REVIEW_OUTSIDE)
    check("a pasted message is refused",
          AG._form_review_refusal(args, _watch(AG, provenance="pasted")) == AG.FORM_REVIEW_OUTSIDE)
    w = _watch(AG)
    w.app_context = True
    check("text the app added is refused", AG._form_review_refusal(args, w) == AG.FORM_REVIEW_OUTSIDE)
    check("a model that is not on this PC is refused",
          AG._form_review_refusal(args, _watch(AG, lane={"url": "https://api.example.com", "model": "x"}))
          == AG.FORM_REVIEW_NOT_LOCAL)
    check("an unknown lane is refused (fails closed)",
          AG._form_review_refusal(args, _watch(AG, lane=None)) == AG.FORM_REVIEW_NOT_LOCAL)


class _Real:
    """Swap the real page reader/actor/observer of jarvis_browser_control for a
    fake form, and a fake Playwright page the picture is taken from."""

    def __init__(self, form, jpeg):
        self.form, self.jpeg = form, jpeg

    def __enter__(self):
        self.saved = (B._default_read, B._default_act, B._default_observe)
        B._default_read = self.form.read
        B._default_act = self.form.act
        B._default_observe = self.form.observe
        shots = self.shots = []
        jpeg = self.jpeg

        class Page:
            def screenshot(self, **kw):
                shots.append(kw)
                return jpeg

            def evaluate(self, js):
                return [["INPUT", "text", "n", "i", "v", "false"]]
        B._sessions["s"] = Page()
        return self

    def __exit__(self, *a):
        B._default_read, B._default_act, B._default_observe = self.saved
        B._sessions.pop("s", None)
        B._fences.pop("s", None)
        B._guards.pop("s", None)
        return False


def _one_call(AG, form, args, gate, *, watch):
    tool = __import__("copy").copy(AG.TOOLS["browser_control"])
    tool.prepare = lambda a: (B.plan(a["goal"], a["session"], a["requests"], read=form.read),
                              "PLAN CARD")
    convo, stp = [], []
    AG._one_call({"id": "1", "function": {"name": "browser_control", "arguments": json.dumps(args)}},
                 ["browser_control"], convo, stp, gate, None, AG._Out(lambda b: None, sse=False),
                 lambda *a, **k: None, watch=watch, tools={"browser_control": tool})
    return json.loads(convo[-1]["content"]) if convo else None, stp


def t_a_full_turn_asks_the_plan_card_then_the_form_card_then_clicks():
    AG = _agent()
    FR._reset_for_tests()
    f = Form()
    gates = []

    def gate(action, detail, prompt):
        gates.append((action, detail))
        return Verdict(True, "approved")
    args = {"goal": "book", "session": "s", "requests": [dict(r) for r in REQS]}
    with _Real(f, fake_jpeg(900, 700)) as env:
        result, _ = _one_call(AG, f, args, gate, watch=_watch(AG))
    actions = [g[0] for g in gates]
    check("two cards, the plan's own then the form's",
          len(actions) == 2 and actions[1] == "browser_form_submit", repr(actions))
    check("the form card carries the picture id and the words",
          "picture" in gates[1][1] and "Alex Kim" in gates[1][1]["text"]
          and "Submit" in gates[1][1]["text"], repr(gates[1])[:200])
    check("the plan card never carried a picture", "picture" not in gates[0][1])
    check("the form was sent once, with what was typed", f.sent == [{"Name": "Alex Kim", "Phone": "555 0100"}])
    check("the answer to the model says it finished", result.get("ok") is True
          and result.get("form_review", {}).get("approved") is True, repr(result)[:200])
    check("one picture was taken, of the whole page", len(env.shots) == 1 and env.shots[0]["full_page"])
    check("nothing is held afterwards", FR.held() == 0)
    check("the answer the model reads holds no picture", "jpeg" not in json.dumps(result))


def t_denying_the_form_card_sends_nothing_and_tells_the_model():
    AG = _agent()
    FR._reset_for_tests()
    f = Form()

    def gate(action, detail, prompt):
        return Verdict(True, "approved") if action != "browser_form_submit" else Verdict(False, "denied")
    args = {"goal": "book", "session": "s", "requests": [dict(r) for r in REQS]}
    with _Real(f, fake_jpeg()):
        result, _ = _one_call(AG, f, args, gate, watch=_watch(AG))
    check("nothing was sent", f.sent == [])
    check("the model is told, in words, nothing was sent",
          result.get("ok") is False and "nothing was sent" in result.get("reason", "").lower(), repr(result)[:300])
    check("the fields were filled and the tab left as it was", f.values["Name"] == "Alex Kim")


def t_a_tainted_turn_reaches_no_page_and_no_card():
    AG = _agent()
    f = Form()
    gates = []
    args = {"goal": "book", "session": "s", "requests": [dict(r) for r in REQS]}
    with _Real(f, fake_jpeg()):
        result, stp = _one_call(AG, f, args, lambda *a: gates.append(a) or Verdict(True),
                                watch=_watch(AG, tainted=True))
    check("refused before any card or page read, in words",
          gates == [] and f.order == [] and result["ok"] is False and "refused" in result["error"]
          and "sends a form" in result["error"], repr(result))
    check("the step log says refused", stp[-1]["outcome"] == "refused" and stp[-1]["ran"] is False)


def t_reading_the_forms_own_page_does_not_block_submit_but_other_reads_do():
    """The owner's answer of 2026-09-30: the booking page Jarvis opened itself is
    not 'outside text' for the final click. Email, files, notes, other sites and
    memories still are."""
    AG = _agent()
    args = {"goal": "book", "session": "s", "requests": [dict(r) for r in REQS]}
    w = _watch(AG)
    w.read["browser_control"] = 2
    check("reads by browser_control alone do not refuse a final step",
          AG._form_review_refusal(args, w) == "")
    w.read["web_search"] = 1
    check("a web search as well: refused", AG._form_review_refusal(args, w) == AG.FORM_REVIEW_OUTSIDE)
    w = _watch(AG)
    w.read["browser_control"] = 1
    w.read["read_email"] = 1
    check("an email read as well: refused", AG._form_review_refusal(args, w) == AG.FORM_REVIEW_OUTSIDE)
    w = _watch(AG, tainted=True)
    w.read["browser_control"] = 1
    check("an earlier conversation that read outside text: still refused",
          AG._form_review_refusal(args, w) == AG.FORM_REVIEW_OUTSIDE)
    # took_in remembers the sites browser_control read, hosts only.
    w = _watch(AG)
    w.took_in("browser_control", {"ok": True, "done": [
        {"action": "navigate", "url": "about:blank", "value": "https://clinic.example/book?name=Jo"},
        {"action": "click", "url": "https://clinic.example/book"}], "not_run": []})
    check("took_in records host names only", w.browser_hosts == {"clinic.example"}, repr(w.browser_hosts))
    check("...and counts as a browser read", w.read.get("browser_control") == 1)


def t_a_different_site_read_earlier_in_the_turn_refuses_the_form():
    AG = _agent()
    FR._reset_for_tests()
    seen = {}
    real_run = B.run
    B.run = lambda plan, **kw: seen.update(kw) or {"ok": True}
    try:
        f = Form()
        p = make_plan(f)
        same = _watch(AG)
        same.browser_hosts = {"clinic.example"}
        out = AG._run_browser_control({}, p, checker=lambda *a: Verdict(True), watch=same, out=None)
        check("only the form's own site read earlier: it runs", out == {"ok": True} and "review" in seen)
        seen.clear()
        other = _watch(AG)
        other.browser_hosts = {"clinic.example", "news.example"}
        out = AG._run_browser_control({}, p, checker=lambda *a: Verdict(True), watch=other, out=None)
        check("another site read earlier: refused in words, nothing run",
              out.get("ok") is False and out.get("submitted") is False
              and out.get("error") == AG.FORM_REVIEW_OTHER_SITE and not seen, repr(out))
    finally:
        B.run = real_run


def t_the_headless_browser_gets_no_picture_hooks_but_still_the_second_card():
    AG = _agent()
    FR._reset_for_tests()
    seen = {}
    real_run = B.run
    B.run = lambda plan, **kw: seen.update(kw) or {"ok": True}
    try:
        f = Form()
        p = make_plan(f)
        for engine in ("headless", "visible"):
            seen.clear()
            p.engine = engine
            AG._run_browser_control({}, p, checker=lambda *a: Verdict(True), watch=_watch(AG),
                                    out=AG._Out(lambda b: None, sse=False))
            check(f"{engine}: the review hook is always passed", callable(seen.get("review")))
            if engine == "headless":
                check("headless: no picture and no deeper look", seen.get("snapshot") is None
                      and seen.get("fingerprint") is None)
            else:
                check("visible: the picture and the deeper look are FR's own",
                      seen.get("snapshot") is FR.capture and seen.get("fingerprint") is FR.fingerprint)
        seen.clear()
        AG._run_browser_control({}, p, checker=None, watch=None, out=None)
        check("no gate wiring: no review hook, so run() sends nothing", seen.get("review") is None)
        seen.clear()
        p2 = make_plan(f, [REQS[0]])
        AG._run_browser_control({}, p2, checker=lambda *a: Verdict(True), watch=_watch(AG), out=None)
        check("a plan with no final step gets no review hook at all", seen.get("review") is None
              and seen.get("snapshot") is None)
    finally:
        B.run = real_run


def t_a_form_cannot_be_a_step_of_a_plan():
    AG = _agent()
    step = types.SimpleNamespace(tool="browser_control", why="x", needs_own_card=False,
                                 args={"goal": "g", "session": "s",
                                       "requests": [dict(r) for r in REQS]})
    gate_check, _ = AG._plan_step_dispatch(AG.TOOLS, ["browser_control"], lambda *a: Verdict(True),
                                           _watch(AG), None, None, AG._Out(lambda b: None, sse=False))
    verdict = gate_check(step)
    check("refused as a plan step, with the reason", verdict.allowed is False
          and "cannot be a step" in verdict.reason, repr(getattr(verdict, "reason", verdict)))


def t_the_tool_schema_offers_final_and_the_tables_know_the_action():
    AG = _agent()
    props = AG.TOOLS["browser_control"].parameters["properties"]["requests"]["items"]["properties"]
    check("the request schema has a boolean `final`", props.get("final", {}).get("type") == "boolean")
    toml = (BACKEND / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8") \
        if (BACKEND / "rebuilt" / "jarvis-framework.toml").is_file() else \
        (REPO / "backend" / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check('the shipped config sets browser_form_submit to "ask"', 'browser_form_submit = "ask"' in toml)
    import jarvis_card_words as W
    import jarvis_asks_first as AF
    check("the card has plain words", "browser_form_submit" in W.TITLES
          and W.title_for("browser_form_submit").startswith("Jarvis wants to "), W.title_for("browser_form_submit"))
    check("it is on the page's must-ask and never-loosen lists",
          "browser_form_submit" in AF.MUST_ASK and "browser_form_submit" in AF.HARD_LIMITS)
    check("the tool's own plan step is unchanged", AG.NEEDS_A_PERSON.get("browser_control"))


if __name__ == "__main__":
    for name, fn in [(n, f) for n, f in sorted(globals().items()) if n.startswith("t_")]:
        print(f"\n--- {name} ---")
        try:
            fn()
        except Exception:
            FAILED.append(name)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
