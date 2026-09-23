"""jarvis_browser_control.py, and the promise that it never improvises a
step or floods the model with page content.

Four things are being proven, not just the happy path: plan() sends no
input at all, run() refuses without approval, run() STOPS the moment the
live page stops matching what was planned, and a `read` step's value is
capped rather than handed back whole.

And, for the parts ported from browser-use (2026-09-23): an ambiguous
element is never guessed at, a page that leaves the allowed sites or asks a
question or opens a tab or starts a download stops the run, a dialog is
never answered yes, a secret's real value reaches act() and nothing else,
`read_page` is capped and says so, and the CDP page reader keeps only what a
person could see and click - the last tested on hand-built CDP data, no
browser. test_browser_control_live.py runs the same promises against a real
headless Chromium.

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
        self.real = (B._default_read, B._default_act, B._default_observe)
        def boom_read(_s):
            raise AssertionError("the real page reader ran")
        def boom_act(_s):
            raise AssertionError("the real input-sender ran")
        def boom_observe(_s):
            raise AssertionError("the real after-step look ran")
        B._default_read, B._default_act, B._default_observe = boom_read, boom_act, boom_observe
        return self

    def __exit__(self, *a):
        B._default_read, B._default_act, B._default_observe = self.real
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
    # (What it DOES get is the after-step look every step now gets - where
    # did the tab land - so the fake reader only refuses to be called
    # BEFORE the navigate has happened.)
    acted = []
    def read(_s):
        if not acted:
            raise AssertionError("navigate should not re-read before running")
        return page("https://example.com/support")
    with NoRealAction():
        p = B.plan("open the chat", "s",
                   [{"action": "navigate", "value": "https://example.com/support", "why": "x"}],
                   read=lambda _s: page())
        out = B.run(p, read=read, act=lambda s: acted.append(s.action), approved=True)
    check("navigate ran without a pre-step re-read", out["ok"] is True, repr(out))
    check("and it did run", acted == ["navigate"], repr(acted))


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


def t_format_new_messages_returns_only_what_is_after_the_cursor():
    """_format_new_messages is the actual fix for "continue a conversation
    extremely long": pure, so the property is provable directly rather than
    only through a real Playwright container."""
    history = [f"message {i}" for i in range(5)]
    out = B._format_new_messages(history, since=3)
    check("only messages at or after the cursor are returned",
          out == "[3] message 3\n[4] message 4", repr(out))
    # CONTROL: a cursor of 0 (or omitted) returns everything, up to the cap.
    out0 = B._format_new_messages(history, since=0)
    check("CONTROL: cursor 0 returns from the start",
          out0 == "\n".join(f"[{i}] message {i}" for i in range(5)), repr(out0))


def t_format_new_messages_caps_and_says_so_rather_than_dropping_silently():
    history = [f"message {i}" for i in range(B._MAX_NEW_MESSAGES + 5)]
    out = B._format_new_messages(history, since=0)
    lines = out.split("\n")
    check("exactly the cap's worth of messages plus one trailer line",
          len(lines) == B._MAX_NEW_MESSAGES + 1, repr(len(lines)))
    check("the trailer names how many were left out",
          "5 more not shown" in lines[-1], out)
    check("the trailer gives a cursor to continue from",
          f"value={B._MAX_NEW_MESSAGES!r}" in lines[-1], out)
    # CONTROL: exactly at the cap, no trailer is added - nothing was left out.
    exact = B._format_new_messages([f"m{i}" for i in range(B._MAX_NEW_MESSAGES)], since=0)
    check("CONTROL: no trailer when nothing was actually dropped",
          "not shown" not in exact, exact)


def t_format_new_messages_caps_each_message_and_reports_no_new_ones():
    huge = ["x" * (B._MAX_MESSAGE_CHARS * 3)]
    out = B._format_new_messages(huge, since=0)
    check("a single oversized message is capped, not truncated by the caller",
          out == f"[0] {'x' * B._MAX_MESSAGE_CHARS}", len(out))
    empty_case = B._format_new_messages(["a", "b"], since=2)
    check("nothing new says so plainly, with the counts",
          empty_case == "(no new messages; 2 total, cursor was 2)", empty_case)


def t_read_new_step_is_planned_against_the_container_not_a_message():
    def read(session):
        return page(elements=[("log", "Conversation", True)])
    with NoRealAction():
        p = B.plan("check for a reply", "support-chat",
                   [{"role": "log", "name": "Conversation", "action": "read_new",
                     "value": "3", "why": "check for a reply"}],
                   read=read)
    check("the container becomes a step", len(p.steps) == 1, repr(p.steps))
    check("the cursor is carried as the step's value", p.steps[0].value == "3", repr(p.steps))
    card = B.describe(p)
    check("the card names the container and the cursor",
          "Conversation" in card and "since #3" in card, card)


def t_read_new_result_reaches_the_caller_unmodified_by_runs_own_cap():
    """run()'s own _MAX_READ_VALUE_CHARS slicing must NOT re-cut a read_new
    result - that could sever the "N more not shown" trailer silently,
    exactly the failure this whole action exists to avoid."""
    live = page(elements=[("log", "Conversation", True)])
    already_formatted = "[0] hi\n...(40 more not shown; call again with value=1 to continue from there)"
    with NoRealAction():
        p = B.plan("check for a reply", "s",
                   [{"role": "log", "name": "Conversation", "action": "read_new",
                     "value": "0", "why": "x"}],
                   read=lambda _s: live)
        out = B.run(p, read=lambda _s: live, act=lambda s: already_formatted, approved=True)
    check("the formatted result, trailer included, reaches the caller whole",
          out["done"][0]["value"] == already_formatted, repr(out))


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


def t_checkpoint_stop_ends_the_run_before_the_next_step():
    live = page(elements=[("textbox", "Message", True), ("button", "Send", True)])
    acted = []
    signals = iter([None, "stop"])
    with NoRealAction():
        p = B.plan("message and send", "s",
                   [{"role": "textbox", "name": "Message", "action": "type",
                     "value": "hi", "why": "x"},
                    {"role": "button", "name": "Send", "action": "click", "why": "y"}],
                   read=lambda _s: live)
        out = B.run(p, read=lambda _s: live, act=lambda s: acted.append(s.name),
                    checkpoint=lambda: next(signals), approved=True)
    check("only the first step ran", acted == ["Message"], repr(acted))
    check("run() reports not-ok", out["ok"] is False, repr(out))
    check("the reason names a stop", "stopped" in out["reason"], out["reason"])
    check("the send step is reported not-run", len(out["not_run"]) == 1, repr(out))


def t_checkpoint_pause_ends_the_run_and_says_so():
    live = page(elements=[("textbox", "Message", True), ("button", "Send", True)])
    acted = []
    signals = iter([None, "pause"])
    with NoRealAction():
        p = B.plan("message and send", "s",
                   [{"role": "textbox", "name": "Message", "action": "type",
                     "value": "hi", "why": "x"},
                    {"role": "button", "name": "Send", "action": "click", "why": "y"}],
                   read=lambda _s: live)
        out = B.run(p, read=lambda _s: live, act=lambda s: acted.append(s.name),
                    checkpoint=lambda: next(signals), approved=True)
    check("only the first step ran", acted == ["Message"], repr(acted))
    check("the result says paused", out.get("paused") is True, repr(out))
    check("the send step is still reported, ready to resume",
          len(out["not_run"]) == 1, repr(out))


def t_no_checkpoint_given_behaves_exactly_as_before():
    live = page(elements=[("button", "Send", True)])
    with NoRealAction():
        p = B.plan("send", "s", [{"role": "button", "name": "Send", "action": "click", "why": "x"}],
                   read=lambda _s: live)
        out = B.run(p, read=lambda _s: live, act=lambda s: None, approved=True)
    check("CONTROL: runs to completion with no checkpoint hook at all",
          out["ok"] is True and out["not_run"] == [], repr(out))


def t_the_checkpoint_is_read_before_the_step_is_announced():
    # `announce` is wired to a sticky set_activity, so announcing a step and
    # then pausing left the Brain window naming a step that never ran. Added
    # after a mutation run showed a straight revert of this ordering passing
    # the whole suite - the ui_control twin had a test, this one did not.
    live = page(elements=[("textbox", "Message", True), ("button", "Send", True)])
    heard, acted = [], []
    signals = iter([None, "pause"])
    with NoRealAction():
        p = B.plan("message and send", "s",
                   [{"role": "textbox", "name": "Message", "action": "type",
                     "value": "hi", "why": "x"},
                    {"role": "button", "name": "Send", "action": "click", "why": "y"}],
                   read=lambda _s: live)
        out = B.run(p, read=lambda _s: live, act=lambda s: acted.append(s.name),
                    announce=heard.append, checkpoint=lambda: next(signals),
                    approved=True)
    check("only the first step ran", acted == ["Message"], repr(acted))
    check("the paused step was never announced",
          not any("Send" in line for line in heard), repr(heard))
    check("the step that DID run was announced",
          any("Message" in line for line in heard), repr(heard))
    check("nothing claimed the run finished",
          not any("Done" in line for line in heard), repr(heard))


def t_a_stop_during_the_final_step_is_reported_not_swallowed():
    # The loop checks before each step, so a stop arriving while the last one
    # runs is never seen by it. It used to vanish entirely.
    live = page(elements=[("button", "Send", True)])
    signals = iter([None, "stop"])
    with NoRealAction():
        p = B.plan("send", "s", [{"role": "button", "name": "Send", "action": "click", "why": "x"}],
                   read=lambda _s: live)
        out = B.run(p, read=lambda _s: live, act=lambda s: None,
                    checkpoint=lambda: next(signals), approved=True)
    check("the plan really did finish", out["ok"] is True, repr(out))
    check("nothing is reported as not run", out["not_run"] == [], repr(out))
    check("the late stop is acknowledged", out.get("late_signal") == "stop", repr(out))


def t_an_ordinary_finish_carries_no_late_signal():
    live = page(elements=[("button", "Send", True)])
    with NoRealAction():
        p = B.plan("send", "s", [{"role": "button", "name": "Send", "action": "click", "why": "x"}],
                   read=lambda _s: live)
        out = B.run(p, read=lambda _s: live, act=lambda s: None,
                    checkpoint=lambda: None, approved=True)
    check("CONTROL: a clean run has no late_signal", "late_signal" not in out, repr(out))


# --------------------------------------------------------------------------
#   Ported from browser-use: ambiguity, the fence, page events, secrets,
#   read_page, and the CDP reader - all with injected fakes or plain data
# --------------------------------------------------------------------------

def rich(url="https://example.com/support", elements=None, events=None, omitted=0):
    """A fake page whose elements carry the reader's full record shape.
    Each element: (role, name, within_name, extra-dict)."""
    out = []
    for role, name, within, extra in (elements or []):
        e = {"role": role, "name": name, "text": name, "enabled": True,
             "interactive": True, "sensitive": False, "password": False,
             "within_role": "region" if within else "", "within_name": within}
        e.update(extra or {})
        out.append(e)
    return {"url": url, "title": "t", "elements": out, "events": list(events or []),
            "omitted": omitted}


TWO_REPLIES = [("button", "Reply", "Order 1", None), ("button", "Reply", "Order 2", None),
               ("button", "Send", "", None)]


def t_two_same_named_elements_are_ambiguous_not_first():
    live = rich(elements=TWO_REPLIES)
    with NoRealAction():
        p = B.plan("reply", "s", [{"role": "button", "name": "Reply", "action": "click",
                                   "why": "x"}], read=lambda _s: live)
    check("an ambiguous request does not become a step", p.steps == [], repr(p.steps))
    reason = p.unmatched[0]["reason"] if p.unmatched else ""
    check("the reason says ambiguous and how many", "ambiguous: 2 elements" in reason, reason)
    check("the reason names the containers that tell them apart",
          "'Order 1'" in reason and "'Order 2'" in reason and "within" in reason, reason)
    check("the card says it will not run", "ambiguous" in B.describe(p), B.describe(p))
    # Two matches with nothing to tell them apart: no hint to pick one.
    same = rich(elements=[("button", "Reply", "", None), ("button", "Reply", "", None)])
    with NoRealAction():
        p2 = B.plan("reply", "s", [{"role": "button", "name": "Reply", "action": "click",
                                    "why": "x"}], read=lambda _s: same)
    check("identical twins are ambiguous with no way offered to pick",
          p2.steps == [] and "nothing on the page tells them apart" in p2.unmatched[0]["reason"],
          repr(p2.unmatched))


def t_within_picks_one_and_run_re_checks_it():
    live = rich(elements=TWO_REPLIES)
    acted = []
    with NoRealAction():
        p = B.plan("reply", "s", [{"role": "button", "name": "Reply", "within": "Order 2",
                                   "action": "click", "why": "x"}], read=lambda _s: live)
        card = B.describe(p)
        out = B.run(p, read=lambda _s: live,
                    act=lambda s: acted.append((s.name, s.within_name)), approved=True)
    check("within makes it exactly one step", len(p.steps) == 1, repr(p.unmatched))
    check("the step carries the container", p.steps[0].within_name == "Order 2", repr(p.steps))
    check("the card says which one", 'inside region "Order 2"' in card, card)
    check("the act is told the container too", acted == [("Reply", "Order 2")], repr(acted))
    check("CONTROL: that run finishes", out["ok"] is True, repr(out))
    # By run time the page has re-rendered and Order 2 now shows two Reply
    # buttons: run() must stop, not take the first.
    doubled = rich(elements=[("button", "Reply", "Order 2", None), ("button", "Reply", "Order 2", None)])
    with NoRealAction():
        out2 = B.run(p, read=lambda _s: doubled, act=lambda s: acted.append("second"),
                     approved=True)
    check("a target that became ambiguous stops the run",
          out2["ok"] is False and "now matches 2 elements" in out2["reason"], repr(out2))
    check("and nothing was acted on", "second" not in acted, repr(acted))
    with NoRealAction():
        p3 = B.plan("reply", "s", [{"role": "button", "name": "Reply", "within": "Order 9",
                                    "action": "click", "why": "x"}], read=lambda _s: live)
    check("a within that matches nothing is reported, not ignored",
          p3.steps == [] and "inside 'Order 9'" in p3.unmatched[0]["reason"], repr(p3.unmatched))


def t_non_interactive_and_unknown_requests_are_refused():
    live = rich(elements=[("heading", "Support", "", {"interactive": False}),
                          ("log", "Conversation", "", {"interactive": False})])
    with NoRealAction():
        p = B.plan("x", "s", [{"role": "heading", "name": "Support", "action": "click", "why": "x"},
                              {"role": "log", "name": "Conversation", "action": "read_new",
                               "value": "0", "why": "x"},
                              {"role": "heading", "name": "Support", "action": "hover", "why": "x"}],
                   read=lambda _s: live)
    reasons = [u["reason"] for u in p.unmatched]
    check("clicking a non-interactive heading is refused",
          any("cannot" in r or "not something" in r for r in reasons), repr(reasons))
    check("an unknown action is refused at plan time", any("unknown action" in r for r in reasons),
          repr(reasons))
    check("CONTROL: reading a non-interactive container is fine",
          [s.action for s in p.steps] == ["read_new"], repr(p.steps))


def t_describe_names_the_fence():
    live = rich(elements=[("button", "Send", "", None)])
    with NoRealAction():
        p = B.plan("send", "s", [{"role": "button", "name": "Send", "action": "click", "why": "x"}],
                   read=lambda _s: live)
        p2 = B.plan("send", "s", [{"role": "button", "name": "Send", "action": "click", "why": "x"}],
                    allowed_domains=["example.com", "help.example.net"], read=lambda _s: live)
    check("with no allowed_domains the card names the plan's own site",
          "only the ones this plan names (example.com)" in B.describe(p), B.describe(p))
    check("with allowed_domains the card lists them",
          "Allowed sites: example.com, help.example.net" in B.describe(p2), B.describe(p2))


def run_two_steps(after_first: dict, *, allowed_domains=None, before_second=None):
    """Plan "type, then click" on example.com; run it with an after-step look
    that reports `after_first` once. Returns (result, acted)."""
    live = rich(elements=[("textbox", "Message", "", None), ("button", "Send", "", None)])
    acted, looks = [], []
    def observe(_s):
        looks.append(1)
        return after_first if len(looks) == 1 else {"url": live["url"], "events": []}
    with NoRealAction():
        p = B.plan("send", "s", [
            {"role": "textbox", "name": "Message", "action": "type", "value": "hi", "why": "x"},
            {"role": "button", "name": "Send", "action": "click", "why": "x"}],
            allowed_domains=allowed_domains, read=lambda _s: live)
        out = B.run(p, read=before_second or (lambda _s: live), observe=observe,
                    act=lambda s: acted.append(s.name), approved=True)
    return out, acted


def t_a_step_that_lands_outside_the_fence_stops_the_run():
    out, acted = run_two_steps({"url": "https://evil.example.org/phish", "events": []})
    check("the run stopped after the step that left", out["ok"] is False, repr(out))
    check("the reason names the foreign address",
          "evil.example.org" in out["reason"] and "outside the allowed sites" in out["reason"],
          out["reason"])
    check("the step that caused it is reported done, the rest not run",
          len(out["done"]) == 1 and len(out["not_run"]) == 1, repr(out))
    check("nothing was done on the foreign page", acted == ["Message"], repr(acted))
    # CONTROL: the same landing is fine when allowed_domains includes it.
    reads = []
    def before(_s):
        reads.append(1)
        if len(reads) == 1:
            return rich(elements=[("textbox", "Message", "", None), ("button", "Send", "", None)])
        return rich("https://evil.example.org/phish", elements=[("button", "Send", "", None)])
    out2, acted2 = run_two_steps({"url": "https://evil.example.org/phish", "events": []},
                                 allowed_domains=["example.com", "example.org"],
                                 before_second=before)
    check("CONTROL: inside an explicit allowed_domains, it carries on",
          out2["ok"] is True and acted2 == ["Message", "Send"], repr(out2))


def t_passing_through_a_foreign_site_stops_the_run_even_if_it_came_back():
    out, _ = run_two_steps({"url": "https://example.com/support", "events": [
        {"kind": "navigation", "url": "https://tracker.example.net/bounce"},
        {"kind": "navigation", "url": "https://example.com/support"}]})
    check("a redirect THROUGH a foreign site is caught",
          out["ok"] is False and "tracker.example.net" in out["reason"], repr(out))


def t_a_blocked_navigation_is_reported():
    out, _ = run_two_steps({"url": "https://example.com/support", "events": [
        {"kind": "blocked_navigation", "url": "https://evil.example.org/"}]})
    check("a navigation the browser blocked still stops the run and says so",
          out["ok"] is False and "blocked it before it loaded" in out["reason"], repr(out))


def t_a_page_that_moved_on_its_own_before_a_step_stops_it():
    live = rich(elements=[("button", "Send", "", None)])
    moved = rich("https://example.com/somewhere-else", elements=[("button", "Send", "", None)])
    acted = []
    with NoRealAction():
        p = B.plan("send", "s", [{"role": "button", "name": "Send", "action": "click", "why": "x"}],
                   read=lambda _s: live)
        out = B.run(p, read=lambda _s: moved, act=lambda s: acted.append(s.name), approved=True)
    check("run() stops before acting on a page at a different address",
          out["ok"] is False and acted == [], repr(out))
    check("the reason names both addresses",
          "changed from https://example.com/support to https://example.com/somewhere-else"
          in out["reason"], out["reason"])
    # CONTROL: only the #fragment changing is not a different page.
    same = rich("https://example.com/support#bottom", elements=[("button", "Send", "", None)])
    with NoRealAction():
        out2 = B.run(p, read=lambda _s: same, act=lambda s: None, approved=True)
    check("CONTROL: a changed #fragment alone does not stop it", out2["ok"] is True, repr(out2))


def t_a_confirm_dialog_stops_the_run_and_is_never_answered_yes():
    out, acted = run_two_steps({"url": "https://example.com/support", "events": [
        {"kind": "dialog", "type": "confirm", "message": "Cancel your subscription?"}]})
    check("the run stopped", out["ok"] is False and acted == ["Message"], repr(out))
    check("the reason quotes the question", "Cancel your subscription?" in out["reason"],
          out["reason"])
    check("the reason says it was answered Cancel, never yes",
          "answered Cancel" in out["reason"] and "never answers yes" in out["reason"],
          out["reason"])
    out_p, _ = run_two_steps({"url": "https://example.com/support", "events": [
        {"kind": "dialog", "type": "prompt", "message": "Your name?"}]})
    check("a prompt stops it too", out_p["ok"] is False and "Your name?" in out_p["reason"],
          repr(out_p))


def t_the_real_dialog_handler_only_ever_dismisses():
    """The listener the real browser uses, driven with a fake dialog object:
    it must call dismiss() and never accept(), for every kind of dialog."""
    class FakeDialog:
        def __init__(self, kind):
            self.type, self.message, self.calls = kind, f"a {kind}", []
        def accept(self, *a):
            self.calls.append("accept")
        def dismiss(self):
            self.calls.append("dismiss")

    class FakePage:
        main_frame = object()
        def __init__(self):
            self.handlers = {}
        def on(self, name, fn):
            self.handlers[name] = fn

    fake = FakePage()
    B._wire_page("dialogs", fake)
    dialogs = [FakeDialog(k) for k in ("alert", "confirm", "prompt", "beforeunload")]
    for d in dialogs:
        fake.handlers["dialog"](d)
    check("every dialog was dismissed, none accepted",
          all(d.calls == ["dismiss"] for d in dialogs), repr([d.calls for d in dialogs]))
    events = B._drain("dialogs")
    check("each one was recorded with its text",
          [e["type"] for e in events] == ["alert", "confirm", "prompt", "beforeunload"]
          and events[1]["message"] == "a confirm", repr(events))


def t_an_alert_is_noted_and_the_run_carries_on():
    out, acted = run_two_steps({"url": "https://example.com/support", "events": [
        {"kind": "dialog", "type": "alert", "message": "Message saved"}]})
    check("an alert does not stop the run", out["ok"] is True and acted == ["Message", "Send"],
          repr(out))
    check("its text is reported in the notes",
          any("Message saved" in n for n in out.get("notes", [])), repr(out))


def t_downloads_popups_and_crashes_stop_the_run():
    cases = [
        ({"kind": "download", "url": "https://example.com/invoice.pdf", "filename": "invoice.pdf"},
         ["invoice.pdf", "downloads are blocked", "nothing was saved"]),
        ({"kind": "popup", "url": "https://example.com/help"}, ["new tab or pop-up"]),
        ({"kind": "crash"}, ["crashed"]),
        ({"kind": "closed"}, ["was closed"]),
        ({"kind": "unresponsive"}, ["stopped responding"]),
    ]
    for event, words in cases:
        out, acted = run_two_steps({"url": "https://example.com/support", "events": [event]})
        check(f"a {event['kind']} stops the run after the step that caused it",
              out["ok"] is False and acted == ["Message"] and len(out["not_run"]) == 1, repr(out))
        check(f"and the reason says so ({event['kind']})",
              all(w in out["reason"] for w in words), out["reason"])


def t_the_real_download_handler_cancels():
    class FakeDownload:
        url, suggested_filename = "https://example.com/x.exe", "x.exe"
        def __init__(self):
            self.cancelled = False
        def cancel(self):
            self.cancelled = True

    class FakePage:
        main_frame = object()
        def __init__(self):
            self.handlers = {}
        def on(self, name, fn):
            self.handlers[name] = fn

    fake, dl = FakePage(), FakeDownload()
    B._wire_page("downloads", fake)
    fake.handlers["download"](dl)
    check("the download is cancelled", dl.cancelled is True)
    check("and recorded", B._drain("downloads") == [
        {"kind": "download", "url": "https://example.com/x.exe", "filename": "x.exe"}])


def t_things_the_page_did_during_plan_go_on_the_card():
    live = rich(elements=[("button", "Send", "", None)], omitted=12, events=[
        {"kind": "dialog", "type": "confirm", "message": "Stay signed in?"},
        {"kind": "navigation", "url": "https://example.com/support"}])
    with NoRealAction():
        p = B.plan("send", "s", [{"role": "button", "name": "Send", "action": "click", "why": "x"}],
                   read=lambda _s: live)
    card = B.describe(p)
    check("the dialog seen while planning is on the card", "Stay signed in?" in card, card)
    check("the element cap is on the card, with the count", "12 more element(s)" in card, card)
    check("a plain navigation is not noise on the card", "went to" not in card, card)


SECRET = "correct-horse-battery-staple"


def secret_plan(elements=None):
    live = rich(elements=elements or [("textbox", "Password", "", {"password": True, "sensitive": True}),
                                      ("button", "Log in", "", None)])
    with NoRealAction():
        p = B.plan("log in", "s", [
            {"role": "textbox", "name": "Password", "action": "type",
             "value": "<secret>shop_pw</secret>", "why": "log in"},
            {"role": "button", "name": "Log in", "action": "click", "why": "x"}],
            read=lambda _s: live)
    return p, live


def t_a_secret_placeholder_never_becomes_the_value_anywhere_but_act():
    p, live = secret_plan()
    card = B.describe(p)
    typed, asked = [], []
    def lookup(name, host):
        asked.append((name, host))
        return SECRET
    with NoRealAction():
        out = B.run(p, read=lambda _s: live, act=lambda s: typed.append(s.value),
                    secrets=lookup, approved=True)
    everything = card + repr(p.as_dict()) + repr(out)
    check("the plan holds the placeholder", p.steps[0].value == "<secret>shop_pw</secret>",
          repr(p.steps))
    check("a step typing a secret is heavy even if nobody said so", p.steps[0].heavy is True)
    check("the card shows the placeholder and explains it",
          "<secret>shop_pw</secret>" in card and "never shown here" in card, card)
    check("act() received the real value", typed[0] == SECRET, repr(typed))
    check("the lookup was asked for the name and the page's host",
          asked == [("shop_pw", "example.com")], repr(asked))
    check("the real value is nowhere in the plan, the card, or the result",
          SECRET not in everything)
    check("the result reports the placeholder",
          out["ok"] and out["done"][0]["value"] == "<secret>shop_pw</secret>", repr(out))


def t_a_secret_with_no_store_fails_closed():
    p, live = secret_plan()
    acted = []
    with NoRealAction():
        out = B.run(p, read=lambda _s: live, act=lambda s: acted.append(s.value), approved=True)
    check("with no secrets store the run stops", out["ok"] is False, repr(out))
    check("and says why", "no secret store" in out["reason"], out["reason"])
    check("nothing at all was typed", acted == [], repr(acted))
    with NoRealAction():
        out2 = B.run(p, read=lambda _s: live, act=lambda s: acted.append(s.value),
                     secrets=lambda name, host: None, approved=True)
    check("a store that does not have it stops the run too",
          out2["ok"] is False and "'shop_pw' is not available" in out2["reason"] and acted == [],
          repr(out2))


def t_a_secret_never_comes_back_through_a_read_or_an_error():
    live = rich(elements=[("textbox", "Name", "", None), ("textbox", "Echo", "", None)])
    with NoRealAction():
        p = B.plan("x", "s", [
            {"role": "textbox", "name": "Name", "action": "type",
             "value": "user <secret>tok</secret>", "why": "x"},
            {"role": "textbox", "name": "Echo", "action": "read", "why": "x"}],
            read=lambda _s: live)
        out = B.run(p, read=lambda _s: live, secrets=lambda n, h: SECRET, approved=True,
                    act=lambda s: f"the page now says {SECRET}" if s.action == "read" else None)
    check("a read-back containing the secret is redacted to the placeholder",
          out["ok"] and out["done"][1]["value"] == "the page now says <secret>tok</secret>",
          repr(out))
    with NoRealAction():
        p2 = B.plan("x", "s", [{"role": "textbox", "name": "Name", "action": "type",
                                "value": "<secret>tok</secret>", "why": "x"}],
                    read=lambda _s: live)
        def failing(s):
            raise RuntimeError(f"could not fill {s.value}")
        out2 = B.run(p2, read=lambda _s: live, secrets=lambda n, h: SECRET, act=failing,
                     approved=True)
    check("an error message that quotes the value is redacted too",
          out2["ok"] is False and SECRET not in out2["reason"]
          and "<secret>tok</secret>" in out2["reason"], out2["reason"])


def t_secret_placeholders_only_go_into_type_steps_and_passwords_need_one():
    live = rich(elements=[("textbox", "Password", "", {"password": True, "sensitive": True}),
                          ("combobox", "Country", "", None)])
    with NoRealAction():
        p = B.plan("x", "s", [
            {"action": "navigate", "value": "https://example.com/?t=<secret>tok</secret>", "why": "x"},
            {"role": "combobox", "name": "Country", "action": "select",
             "value": "<secret>tok</secret>", "why": "x"},
            {"role": "textbox", "name": "Password", "action": "type", "value": SECRET, "why": "x"},
            {"role": "textbox", "name": "Password", "action": "read", "why": "x"}],
            read=lambda _s: live)
    reasons = [u["reason"] for u in p.unmatched]
    check("no step was made from any of them", p.steps == [], repr(p.steps))
    check("a placeholder in a navigate or select is refused",
          sum("can only be typed" in r for r in reasons) == 2, repr(reasons))
    check("a literal password is refused", any("only takes a <secret>" in r for r in reasons),
          repr(reasons))
    check("reading a password field back is refused", any("never read back" in r for r in reasons),
          repr(reasons))
    check("the literal password is not on the card or in the plan",
          SECRET not in B.describe(p) and SECRET not in repr(p.as_dict()))
    with NoRealAction():
        p2 = B.plan("x", "s", [{"role": "combobox", "name": "Country", "action": "type",
                                "value": "<secret>not a name!</secret>", "why": "x"}],
                    read=lambda _s: live)
    check("a malformed placeholder is refused, not typed literally",
          p2.steps == [] and "malformed" in p2.unmatched[0]["reason"], repr(p2.unmatched))


def t_read_page_text_is_capped_and_says_so():
    text = "abcdefghij" * (B._MAX_PAGE_TEXT_CHARS // 5)     # twice the cap
    first = B._format_page_text(text, 0)
    body, _, trailer = first.rpartition("\n")
    check("the first window is exactly the cap", body == text[:B._MAX_PAGE_TEXT_CHARS], len(body))
    check("the trailer names how much is left and where to continue",
          trailer == (f"...({len(text) - B._MAX_PAGE_TEXT_CHARS} more characters not shown; "
                      f"call again with value={B._MAX_PAGE_TEXT_CHARS!r} to continue from there)"),
          trailer)
    second = B._format_page_text(text, B._MAX_PAGE_TEXT_CHARS)
    check("the second window is the rest, with no trailer",
          second == text[B._MAX_PAGE_TEXT_CHARS:], len(second))
    check("CONTROL: a short page has no trailer", B._format_page_text("short", 0) == "short")
    check("past the end says so", B._format_page_text("abc", 9)
          == "(no more page text; 3 characters total, offset was 9)")
    check("an empty page says so", B._format_page_text("", 0) == "(the page has no readable text)")


def t_read_page_is_a_step_and_its_result_is_not_re_cut():
    live = rich()
    already = "x" * B._MAX_PAGE_TEXT_CHARS + "\n...(99 more characters not shown; call again with value=1500 to continue from there)"
    with NoRealAction():
        p = B.plan("read", "s", [{"action": "read_page", "value": "0", "why": "look"},
                                 {"action": "read_page", "value": "abc", "why": "bad"}],
                   read=lambda _s: live)
    check("read_page becomes a step with its offset",
          len(p.steps) == 1 and p.steps[0].value == "0", repr(p.steps))
    check("a non-numeric offset is refused", "offset" in p.unmatched[0]["reason"], repr(p.unmatched))
    check("the card describes it", "read the page's text from character #0" in B.describe(p),
          B.describe(p))
    with NoRealAction():
        out = B.run(p, read=lambda _s: live, act=lambda s: already, approved=True)
    check("the capped text and its trailer reach the caller whole",
          out["done"][0]["value"] == already, repr(out)[:200])


def t_html_to_text_keeps_content_and_drops_the_rest():
    html = """<main><h1>Help</h1><p>Hello   <b>world</b></p>
      <script>var secretState = {"a": 1};</script><style>.x{color:red}</style>
      <ul><li>one</li><li>two<ol><li>nested</li></ol></li></ul>
      <table><tr><th>Item</th><th>Qty</th></tr><tr><td>Pen</td><td>2</td></tr></table>
      <input type="password" value="hunter2"><textarea>draft</textarea>
      <a href="https://example.com/very/long/url">a link</a> <img alt="logo" src="x.png">
      <p>{"props":{"pageProps":{"state":"%s"}}}</p></main>""" % ("z" * 200)
    text = B.html_to_text(html)
    lines = text.split("\n")
    check("headings become #", lines[0] == "# Help", repr(lines[:3]))
    check("inline text is joined and whitespace collapsed", "Hello world" in lines, repr(lines))
    check("list items become - and nest", "- one" in lines and "  1. nested" in lines, repr(lines))
    check("table cells are joined with |", "Item | Qty" in lines and "Pen | 2" in lines, repr(lines))
    check("scripts and styles are gone", "secretState" not in text and "color:red" not in text, text)
    check("a password field's value never appears", "hunter2" not in text, text)
    check("links keep their text, not their URL", "a link" in text and "very/long/url" not in text, text)
    check("images keep their alt text", "logo" in text, text)
    check("a big inline JSON blob is dropped", "pageProps" not in text, text)


# --- the CDP reader, on hand-built CDP data --------------------------------

def cdp(nodes):
    """Build (ax_nodes, snapshot) the shape Chrome returns. Each node:
    dict(bid, parent, tag, role=None, name=None, attrs={}, box=None,
    style={}, paint=1, props={}, type=1). A node with a role gets an AX
    node; AX parent links follow the DOM parent links."""
    strings = []

    def S(x):
        if x not in strings:
            strings.append(x)
        return strings.index(x)
    defaults = {"display": "block", "visibility": "visible", "opacity": "1",
                "cursor": "auto", "background-color": "rgba(0, 0, 0, 0)", "position": "static"}
    dn = {"parentIndex": [], "nodeType": [], "nodeName": [], "backendNodeId": [],
          "attributes": [], "isClickable": {"index": []}}
    lay = {"nodeIndex": [], "bounds": [], "styles": [], "paintOrders": []}
    ax = []
    index_of = {}
    for i, n in enumerate(nodes):
        index_of[n["bid"]] = i
        dn["parentIndex"].append(index_of.get(n.get("parent"), -1))
        dn["nodeType"].append(n.get("type", 1))
        dn["nodeName"].append(S(n.get("tag", "div").upper()))
        dn["backendNodeId"].append(n["bid"])
        flat = []
        for k, v in (n.get("attrs") or {}).items():
            flat += [S(k), S(v)]
        dn["attributes"].append(flat)
        if n.get("box") is not None:
            st = {**defaults, **(n.get("style") or {})}
            lay["nodeIndex"].append(i)
            lay["bounds"].append(list(n["box"]))
            lay["styles"].append([S(st[k]) for k in B._SNAPSHOT_STYLES])
            lay["paintOrders"].append(n.get("paint", 1))
    for n in nodes:
        if n.get("role"):
            ax.append({"nodeId": str(n["bid"]), "ignored": False,
                       "role": {"value": n["role"]}, "name": {"value": n.get("name", "")},
                       "backendDOMNodeId": n["bid"],
                       "properties": [{"name": k, "value": {"value": v}}
                                      for k, v in (n.get("props") or {}).items()],
                       "childIds": [str(c["bid"]) for c in nodes
                                    if c.get("parent") == n["bid"] and c.get("role")]})
    return ax, {"strings": strings, "documents": [{"nodes": dn, "layout": lay}]}


def page_nodes(*extra):
    return [{"bid": 1, "type": 9, "tag": "#document", "box": (0, 0, 1000, 700)},
            {"bid": 2, "parent": 1, "tag": "body", "box": (0, 0, 1000, 700)}, *extra]


def names_of(nodes):
    els, omitted = B._elements_from_cdp(*cdp(nodes))
    return {(e["role"], e["name"]): e for e in els}, omitted


def t_the_cdp_reader_keeps_visible_named_elements():
    found, omitted = names_of(page_nodes(
        {"bid": 10, "parent": 2, "tag": "button", "role": "button", "name": "  Send \n now ",
         "box": (10, 10, 60, 20), "props": {"focusable": True}},
        {"bid": 11, "parent": 2, "tag": "button", "role": "button", "name": "Gone",
         "box": (10, 40, 60, 20), "style": {"display": "none"}},
        {"bid": 12, "parent": 2, "tag": "button", "role": "button", "name": "Invisible",
         "box": (10, 70, 60, 20), "style": {"visibility": "hidden"}},
        {"bid": 13, "parent": 2, "tag": "div", "box": (0, 100, 200, 40), "style": {"opacity": "0"}},
        {"bid": 14, "parent": 13, "tag": "button", "role": "button", "name": "Faded",
         "box": (10, 110, 60, 20)},
        {"bid": 15, "parent": 2, "tag": "button", "role": "button", "name": "No layout"},
        {"bid": 16, "parent": 2, "tag": "span", "role": "StaticText", "name": "just text",
         "box": (0, 200, 50, 10)},
        {"bid": 17, "parent": 2, "tag": "h1", "role": "heading", "name": "Title",
         "box": (0, 220, 300, 30)},
        {"bid": 18, "parent": 2, "tag": "img", "role": "image", "name": "Logo",
         "box": (0, 260, 80, 80)}))
    check("a visible button is read, its name whitespace-normalised",
          ("button", "Send now") in found, sorted(found))
    for gone in ("Gone", "Invisible", "Faded", "No layout"):
        check(f"{gone!r} is not read", ("button", gone) not in found, sorted(found))
    check("CDP-internal roles like StaticText are not read",
          not any(r == "StaticText" for r, _ in found), sorted(found))
    check("a heading is read and marked not interactive",
          ("heading", "Title") in found and found[("heading", "Title")]["interactive"] is False)
    check("Chrome's 'image' role becomes ARIA 'img' for Playwright", ("img", "Logo") in found,
          sorted(found))
    check("nothing was left out", omitted == 0)


def t_the_cdp_reader_drops_what_is_painted_over():
    found, _ = names_of(page_nodes(
        {"bid": 10, "parent": 2, "tag": "button", "role": "button", "name": "Under",
         "box": (10, 10, 60, 20), "paint": 1},
        {"bid": 11, "parent": 2, "tag": "div", "box": (0, 0, 300, 100), "paint": 5,
         "style": {"background-color": "rgb(255, 255, 255)"}},
        {"bid": 20, "parent": 2, "tag": "button", "role": "button", "name": "Half covered",
         "box": (400, 10, 60, 20), "paint": 1},
        {"bid": 21, "parent": 2, "tag": "div", "box": (400, 0, 30, 100), "paint": 5,
         "style": {"background-color": "rgb(255, 255, 255)"}},
        {"bid": 30, "parent": 2, "tag": "button", "role": "button", "name": "Under glass",
         "box": (600, 10, 60, 20), "paint": 1},
        {"bid": 31, "parent": 2, "tag": "div", "box": (590, 0, 200, 100), "paint": 5},
        {"bid": 40, "parent": 2, "tag": "button", "role": "button", "name": "Own label",
         "box": (800, 10, 60, 20), "paint": 3,
         "style": {"background-color": "rgb(239, 239, 239)"}},
        {"bid": 41, "parent": 40, "tag": "span", "box": (800, 10, 60, 20), "paint": 4,
         "style": {"background-color": "rgb(239, 239, 239)"}},
        {"bid": 50, "parent": 2, "tag": "button", "role": "button", "name": "On top",
         "box": (10, 500, 60, 20), "paint": 9},
        {"bid": 51, "parent": 2, "tag": "div", "box": (0, 490, 300, 100), "paint": 2,
         "style": {"background-color": "rgb(0, 0, 0)"}}))
    check("an element fully covered by an opaque box painted after it is dropped",
          ("button", "Under") not in found, sorted(found))
    check("CONTROL: a partly covered element is kept", ("button", "Half covered") in found,
          sorted(found))
    check("CONTROL: a transparent box does not hide anything", ("button", "Under glass") in found,
          sorted(found))
    check("CONTROL: an element's own child does not hide it", ("button", "Own label") in found,
          sorted(found))
    check("CONTROL: a box painted BEFORE it does not hide it", ("button", "On top") in found,
          sorted(found))


def t_the_cdp_reader_knows_a_fixed_backdrop_covers_the_whole_page():
    found, _ = names_of(page_nodes(
        {"bid": 10, "parent": 2, "tag": "button", "role": "button", "name": "Far below",
         "box": (10, 3000, 60, 20), "paint": 1},
        {"bid": 11, "parent": 2, "tag": "div", "box": (0, 0, 1000, 700), "paint": 5,
         "style": {"position": "fixed", "background-color": "rgba(0, 0, 0, 0.5)"}},
        {"bid": 12, "parent": 2, "tag": "div", "role": "dialog", "name": "Cookies",
         "box": (100, 100, 300, 100), "paint": 6,
         "style": {"position": "fixed", "background-color": "rgb(255, 255, 255)"}},
        {"bid": 13, "parent": 12, "tag": "button", "role": "button", "name": "Accept",
         "box": (120, 120, 60, 20), "paint": 6}))
    check("a button far below a full-screen fixed backdrop is dropped",
          ("button", "Far below") not in found, sorted(found))
    check("CONTROL: the dialog's own button is kept", ("button", "Accept") in found, sorted(found))
    check("and it knows which dialog it is in",
          found[("button", "Accept")]["within_name"] == "Cookies"
          and found[("button", "Accept")]["within_role"] == "dialog", repr(found.get(("button", "Accept"))))
    # CONTROL: a fixed header bar is fixed but not full-screen.
    found2, _ = names_of(page_nodes(
        {"bid": 10, "parent": 2, "tag": "button", "role": "button", "name": "Far below",
         "box": (10, 3000, 60, 20), "paint": 1},
        {"bid": 11, "parent": 2, "tag": "div", "box": (0, 0, 1000, 60), "paint": 5,
         "style": {"position": "fixed", "background-color": "rgb(255, 255, 255)"}}))
    check("CONTROL: a fixed header does not hide the rest of the page",
          ("button", "Far below") in found2, sorted(found2))


def t_the_cdp_reader_flags_interactive_and_sensitive():
    found, _ = names_of(page_nodes(
        {"bid": 10, "parent": 2, "tag": "input", "role": "textbox", "name": "Password",
         "attrs": {"type": "password"}, "box": (0, 0, 100, 20), "props": {"editable": "plaintext"}},
        {"bid": 11, "parent": 2, "tag": "input", "role": "textbox", "name": "Card number",
         "attrs": {"autocomplete": "cc-number"}, "box": (0, 30, 100, 20)},
        {"bid": 12, "parent": 2, "tag": "div", "role": "generic", "name": "Open menu",
         "attrs": {"onclick": "x()"}, "box": (0, 60, 100, 20)},
        {"bid": 13, "parent": 2, "tag": "div", "role": "generic", "name": "Decoration",
         "box": (0, 90, 100, 20)},
        {"bid": 14, "parent": 2, "tag": "div", "role": "button", "name": "Custom button",
         "box": (0, 120, 100, 20), "style": {"cursor": "pointer"}},
        {"bid": 15, "parent": 2, "tag": "button", "role": "button", "name": "Off",
         "box": (0, 150, 100, 20), "props": {"disabled": True}}))
    pw = found.get(("textbox", "Password"), {})
    check("a password field is sensitive and marked password",
          pw.get("sensitive") is True and pw.get("password") is True, repr(pw))
    check("a card-number field is sensitive but not a password",
          found[("textbox", "Card number")]["sensitive"] is True
          and found[("textbox", "Card number")]["password"] is False)
    check("an onclick div with a name is kept as interactive",
          found.get(("generic", "Open menu"), {}).get("interactive") is True, sorted(found))
    check("a plain named div is not kept", ("generic", "Decoration") not in found, sorted(found))
    check("a role=button div is interactive", found[("button", "Custom button")]["interactive"])
    check("a disabled button is read as disabled", found[("button", "Off")]["enabled"] is False)


def t_the_cdp_reader_caps_and_counts_what_it_left_out():
    extra = [{"bid": 100 + k, "parent": 2, "tag": "h2", "role": "heading", "name": f"H{k}",
              "box": (0, 10 * k, 100, 10)} for k in range(B._MAX_ELEMENTS)]
    extra.append({"bid": 5000, "parent": 2, "tag": "button", "role": "button", "name": "Last button",
                  "box": (0, 99999, 100, 10)})
    els, omitted = B._elements_from_cdp(*cdp(page_nodes(*extra)))
    check("never more than _MAX_ELEMENTS", len(els) == B._MAX_ELEMENTS, len(els))
    check("the number left out is reported", omitted == 1, omitted)
    check("interactive elements are kept first when the cap bites",
          any(e["name"] == "Last button" for e in els))


if __name__ == "__main__":
    for fn in (t_planning_sends_no_input, t_unmatched_requests_do_not_become_steps,
               t_disabled_element_is_treated_as_unmatched,
               t_navigate_requires_http_or_https, t_navigate_respects_allowed_domains,
               t_the_card_prints_every_step_in_full, t_run_refuses_without_approval,
               t_run_re_verifies_before_every_step_and_stops_on_mismatch,
               t_navigate_is_not_re_verified_against_a_prior_page,
               t_run_executes_the_approved_steps_in_order,
               t_a_read_steps_value_is_capped_not_handed_back_whole,
               t_format_new_messages_returns_only_what_is_after_the_cursor,
               t_format_new_messages_caps_and_says_so_rather_than_dropping_silently,
               t_format_new_messages_caps_each_message_and_reports_no_new_ones,
               t_read_new_step_is_planned_against_the_container_not_a_message,
               t_read_new_result_reaches_the_caller_unmodified_by_runs_own_cap,
               t_announce_is_called_once_per_step_and_is_optional,
               t_checkpoint_stop_ends_the_run_before_the_next_step,
               t_checkpoint_pause_ends_the_run_and_says_so,
               t_no_checkpoint_given_behaves_exactly_as_before,
               t_the_checkpoint_is_read_before_the_step_is_announced,
               t_a_stop_during_the_final_step_is_reported_not_swallowed,
               t_an_ordinary_finish_carries_no_late_signal,
               t_two_same_named_elements_are_ambiguous_not_first,
               t_within_picks_one_and_run_re_checks_it,
               t_non_interactive_and_unknown_requests_are_refused,
               t_describe_names_the_fence,
               t_a_step_that_lands_outside_the_fence_stops_the_run,
               t_passing_through_a_foreign_site_stops_the_run_even_if_it_came_back,
               t_a_blocked_navigation_is_reported,
               t_a_page_that_moved_on_its_own_before_a_step_stops_it,
               t_a_confirm_dialog_stops_the_run_and_is_never_answered_yes,
               t_the_real_dialog_handler_only_ever_dismisses,
               t_an_alert_is_noted_and_the_run_carries_on,
               t_downloads_popups_and_crashes_stop_the_run,
               t_the_real_download_handler_cancels,
               t_things_the_page_did_during_plan_go_on_the_card,
               t_a_secret_placeholder_never_becomes_the_value_anywhere_but_act,
               t_a_secret_with_no_store_fails_closed,
               t_a_secret_never_comes_back_through_a_read_or_an_error,
               t_secret_placeholders_only_go_into_type_steps_and_passwords_need_one,
               t_read_page_text_is_capped_and_says_so,
               t_read_page_is_a_step_and_its_result_is_not_re_cut,
               t_html_to_text_keeps_content_and_drops_the_rest,
               t_the_cdp_reader_keeps_visible_named_elements,
               t_the_cdp_reader_drops_what_is_painted_over,
               t_the_cdp_reader_knows_a_fixed_backdrop_covers_the_whole_page,
               t_the_cdp_reader_flags_interactive_and_sensitive,
               t_the_cdp_reader_caps_and_counts_what_it_left_out):
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
