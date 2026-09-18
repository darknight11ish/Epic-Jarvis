"""jarvis_browser_control.py, and the promise that it never improvises a
step or floods the model with page content.

Four things are being proven, not just the happy path: plan() sends no
input at all, run() refuses without approval, run() STOPS the moment the
live page stops matching what was planned, and a `read` step's value is
capped rather than handed back whole.

    python3 test_browser_control.py
"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_browser_control as B

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def page(url="https://example.com/support", title="Support", elements=None):
    """A fake page snapshot: each element is (role, name, enabled)."""
    return {"url": url, "title": title,
            "elements": [{"role": r, "name": n, "text": n, "enabled": e}
                          for (r, n, e) in (elements or [])]}


class NoRealAction:
    """Fail loudly if the default (real, Playwright-backed) reader or actor
    is ever reached - proves every test below only exercises injected fakes."""

    def __enter__(self):
        self.real_read, self.real_act = B._default_read, B._default_act
        def boom_read(_s):
            raise AssertionError("the real page reader ran")
        def boom_act(_s):
            raise AssertionError("the real input-sender ran")
        B._default_read, B._default_act = boom_read, boom_act
        return self

    def __exit__(self, *a):
        B._default_read, B._default_act = self.real_read, self.real_act
        return False


def t_planning_sends_no_input():
    calls = []
    def read(session):
        calls.append(session)
        return page("https://example.com/support", "Support",
                     elements=[("textbox", "Message", True), ("button", "Send", True)])
    with NoRealAction():
        p = B.plan("get help with a late order", "support-chat",
                   [{"role": "textbox", "name": "Message", "action": "type",
                     "value": "my order hasn't arrived", "why": "state the problem",
                     "leaves_machine": True},
                    {"role": "button", "name": "Send", "action": "click",
                     "why": "send it", "leaves_machine": True}],
                   read=read)
    check("plan() only reads, once per session asked about", calls == ["support-chat"])
    check("both requests matched", len(p.steps) == 2, repr(p.steps))
    check("nothing unmatched", p.unmatched == [], repr(p.unmatched))
    check("both steps are marked heavy (leaves_machine)",
          all(s.heavy for s in p.steps), repr(p.steps))
    check("plan weight is heavy", p.weight == "heavy", p.weight)
    check("each step records the URL it was planned against",
          all(s.url == "https://example.com/support" for s in p.steps), repr(p.steps))


def t_unmatched_requests_do_not_become_steps():
    def read(session):
        return page(elements=[("button", "Send", True)])
    with NoRealAction():
        p = B.plan("send", "s", [{"role": "button", "name": "Send", "action": "click", "why": "x"},
                                  {"role": "button", "name": "Attach", "action": "click", "why": "y"}],
                   read=read)
    check("only the real element becomes a step", len(p.steps) == 1, repr(p.steps))
    check("the missing one is reported, not silently dropped",
          len(p.unmatched) == 1 and p.unmatched[0]["name"] == "Attach", repr(p.unmatched))
    card = B.describe(p)
    check("the card says what will NOT run", "NOT run" in card, card)
    check("the card names the missing element", "Attach" in card, card)


def t_disabled_element_is_treated_as_unmatched():
    def read(session):
        return page(elements=[("button", "Send", False)])
    with NoRealAction():
        p = B.plan("send", "s", [{"role": "button", "name": "Send", "action": "click", "why": "x"}],
                   read=read)
    check("a disabled element is not turned into a step", p.steps == [], repr(p.steps))
    check("and the reason says so", p.unmatched[0]["reason"] == "found but disabled", repr(p.unmatched))


def t_navigate_requires_http_or_https():
    def read(session):
        return page()
    with NoRealAction():
        p = B.plan("go somewhere odd", "s",
                   [{"action": "navigate", "value": "javascript:alert(1)", "why": "x"},
                    {"action": "navigate", "value": "file:///etc/passwd", "why": "x"},
                    {"action": "navigate", "value": "https://example.com/support", "why": "x"}],
                   read=read)
    check("only the http(s) navigate becomes a step", len(p.steps) == 1, repr(p.steps))
    check("javascript: and file: are both rejected, not attempted",
          len(p.unmatched) == 2, repr(p.unmatched))
    check("the reason names the scheme",
          any("scheme" in u["reason"] for u in p.unmatched), repr(p.unmatched))


def t_navigate_respects_allowed_domains():
    def read(session):
        return page()
    with NoRealAction():
        p = B.plan("go to support", "s",
                   [{"action": "navigate", "value": "https://support.example.com/chat", "why": "x"},
                    {"action": "navigate", "value": "https://evil.example.org/", "why": "y"}],
                   allowed_domains=["example.com"], read=read)
    check("the allowed subdomain becomes a step", len(p.steps) == 1, repr(p.steps))
    check("the other domain is rejected", len(p.unmatched) == 1, repr(p.unmatched))
    check("the reason names the domain check",
          "allowed_domains" in p.unmatched[0]["reason"], repr(p.unmatched))
    # CONTROL: with no allowed_domains given at all, nothing is restricted.
    with NoRealAction():
        p2 = B.plan("go anywhere", "s",
                    [{"action": "navigate", "value": "https://evil.example.org/", "why": "z"}],
                    read=read)
    check("CONTROL: no allowed_domains means no domain restriction",
          len(p2.steps) == 1, repr(p2.steps))


def t_the_card_prints_every_step_in_full():
    def read(session):
        return page(elements=[("button", "Send", True)])
    with NoRealAction():
        p = B.plan("send it", "support-chat",
                   [{"role": "button", "name": "Send", "action": "click",
                     "why": "because the draft is ready", "leaves_machine": True}],
                   read=read)
    card = B.describe(p)
    check("the element name is on the card", "Send" in card, card)
    check("the action is on the card", "click" in card, card)
    check("the reason is on the card", "because the draft is ready" in card, card)
    check("the session is named", "support-chat" in card, card)
    check("a leaves_machine step is flagged", "sends something to the other end" in card, card)
    check("the card says what refusing costs", "If you say no" in card, card)


def t_run_refuses_without_approval():
    def read(session):
        return page(elements=[("button", "Send", True)])
    with NoRealAction():
        p = B.plan("send", "s", [{"role": "button", "name": "Send", "action": "click", "why": "x"}],
                   read=read)
        out = B.run(p, read=read, act=lambda s: (_ for _ in ()).throw(
            AssertionError("act() ran without approval")))
    check("run() does nothing without approval", out["ok"] is False, repr(out))
    check("and says so plainly", "not approved" in out["reason"], out["reason"])


def t_run_re_verifies_before_every_step_and_stops_on_mismatch():
    # Both elements are there and enabled at plan() time. By the time run()
    # re-checks right before step 2, "Send" has become disabled - a captcha
    # appeared and is blocking it, say. run() must stop AT that step.
    plan_page = page(elements=[("textbox", "Message", True), ("button", "Send", True)])
    calls = {"n": 0}
    def read(session):
        calls["n"] += 1
        if calls["n"] == 1:
            return page(elements=[("textbox", "Message", True)])   # step 1 check: fine
        return page(elements=[("button", "Send", False)])            # step 2 check: now disabled
    acted = []
    with NoRealAction():
        p = B.plan("message and send", "s",
                   [{"role": "textbox", "name": "Message", "action": "type",
                     "value": "hi", "why": "x"},
                    {"role": "button", "name": "Send", "action": "click", "why": "y"}],
                   read=lambda _s: plan_page)
        out = B.run(p, read=read, act=lambda s: acted.append(s.name), approved=True)
    check("the first step, still valid, ran", acted == ["Message"], repr(acted))
    check("run() reports failure rather than pushing through", out["ok"] is False, repr(out))
    check("it names which step stopped it", "step 2" in out["reason"] and "Send" in out["reason"],
          out["reason"])
    check("exactly one step done, one not run",
          len(out["done"]) == 1 and len(out["not_run"]) == 1, repr(out))


def t_navigate_is_not_re_verified_against_a_prior_page():
    # navigate has nothing to re-check before it runs - it IS the check.
    with NoRealAction():
        p = B.plan("open the chat", "s",
                   [{"action": "navigate", "value": "https://example.com/support", "why": "x"}],
                   read=lambda _s: page())
        out = B.run(p, read=lambda _s: (_ for _ in ()).throw(
            AssertionError("navigate should not re-read before running")),
            act=lambda s: None, approved=True)
    check("navigate ran without a pre-step re-read", out["ok"] is True, repr(out))


def t_run_executes_the_approved_steps_in_order():
    live = page(elements=[("textbox", "Message", True), ("button", "Send", True)])
    acted = []
    with NoRealAction():
        p = B.plan("message and send", "s",
                   [{"role": "textbox", "name": "Message", "action": "type",
                     "value": "hi", "why": "x"},
                    {"role": "button", "name": "Send", "action": "click", "why": "y"}],
                   read=lambda _s: live)
        out = B.run(p, read=lambda _s: live, act=lambda s: acted.append((s.name, s.action)),
                    approved=True)
    check("CONTROL: an approved, still-matching plan runs every step",
          out["ok"] is True and acted == [("Message", "type"), ("Send", "click")],
          repr((out, acted)))
    check("done lists both steps, nothing left not-run",
          len(out["done"]) == 2 and out["not_run"] == [], repr(out))


def t_a_read_steps_value_is_capped_not_handed_back_whole():
    """The actual fix for the thing that killed the last attempt at this: a
    read step's value must never grow unbounded, even if the real page
    genuinely has a huge amount of text (a long chat transcript)."""
    live = page(elements=[("generic", "Transcript", True)])
    huge = "x" * (B._MAX_READ_VALUE_CHARS * 5)
    with NoRealAction():
        p = B.plan("check the transcript", "s",
                   [{"role": "generic", "name": "Transcript", "action": "read", "why": "x"}],
                   read=lambda _s: live)
        out = B.run(p, read=lambda _s: live, act=lambda s: huge, approved=True)
    check("the run succeeded", out["ok"] is True, repr(out))
    check("the value reaching the caller is capped",
          len(out["done"][0]["value"]) == B._MAX_READ_VALUE_CHARS, len(out["done"][0]["value"]))
    # CONTROL: a short value is not truncated or padded.
    with NoRealAction():
        p2 = B.plan("check", "s",
                    [{"role": "generic", "name": "Transcript", "action": "read", "why": "x"}],
                    read=lambda _s: live)
        out2 = B.run(p2, read=lambda _s: live, act=lambda s: "short", approved=True)
    check("CONTROL: a short read-back value survives untouched",
          out2["done"][0]["value"] == "short", repr(out2))


def t_announce_is_called_once_per_step_and_is_optional():
    live = page(elements=[("button", "Send", True)])
    heard = []
    with NoRealAction():
        p = B.plan("send", "s", [{"role": "button", "name": "Send", "action": "click", "why": "x"}],
                   read=lambda _s: live)
        out = B.run(p, read=lambda _s: live, act=lambda s: None, announce=heard.append,
                    approved=True)
    check("announce heard the step and a final message", len(heard) == 2, repr(heard))
    check("the step text names the element", "Send" in heard[0], heard[0])
    with NoRealAction():
        p2 = B.plan("send", "s", [{"role": "button", "name": "Send", "action": "click", "why": "x"}],
                    read=lambda _s: live)
        out2 = B.run(p2, read=lambda _s: live, act=lambda s: None, approved=True)
    check("CONTROL: no announce given still runs to completion", out2["ok"] is True, repr(out2))


if __name__ == "__main__":
    for fn in (t_planning_sends_no_input, t_unmatched_requests_do_not_become_steps,
               t_disabled_element_is_treated_as_unmatched,
               t_navigate_requires_http_or_https, t_navigate_respects_allowed_domains,
               t_the_card_prints_every_step_in_full, t_run_refuses_without_approval,
               t_run_re_verifies_before_every_step_and_stops_on_mismatch,
               t_navigate_is_not_re_verified_against_a_prior_page,
               t_run_executes_the_approved_steps_in_order,
               t_a_read_steps_value_is_capped_not_handed_back_whole,
               t_announce_is_called_once_per_step_and_is_optional):
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
