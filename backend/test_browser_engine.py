"""test_browser_engine.py - which browser Jarvis uses for a web task: the visible
one or the headless one (Obscura). jarvis_browser_engine.py, its hooks into
jarvis_browser_control.py and jarvis_agent.py's browser_control tool (the owner's
decision of 2026-09-29).

    python3 backend/test_browser_engine.py

No real Obscura and no real Playwright: backend/_fake_obscura.py answers as
Obscura's MCP server would (as a REAL child process, over standard input and
output), and the visible engine is a fake page. What it proves:

  - OFF by default; a damaged file reads as off; ON is ONE approval card
    (gate action obscura_enable, tier ask) and changes NOTHING until a person says
    yes; denied, timed out, refused, withdrawn and a tier that is not "ask" all
    leave it off; OFF is immediate and stops the program; the card's words;
  - the mode rule: visible / headless / auto, the owner's default, what happens
    when headless cannot run (refused in words for an explicit ask, a visible
    fallback that SAYS so for a default) - never silent;
  - the engine only acts inside an approved plan: a bare open/click/fill/text call
    is refused; a plan on the headless engine names the engine on the card's first
    line, refuses a saved secret and a message list at plan time, and its steps are
    the same steps, re-checked before each one, with the same fence;
  - a click that would leave the allowed sites (a link, a form's address, a
    mailto:) is refused BEFORE it is made; an address on this PC, the home
    network, Tailscale or Meshnet is refused before Obscura is asked;
  - a captcha, an "are you human" page or a sign-in page STOPS the run and says,
    in words, to use the visible browser - nothing is solved, nothing typed;
  - a page it reads is outside text (the same took_in as every tool), never a
    fact; a headless run that can no longer run stops in words and never opens
    the other browser;
  - the routes and the panel both apps show; no proxy setting exists anywhere;
  - the review of 2026-09-29 (section 6 below): the switch is re-checked on every call
    and the program cannot be restarted while it is off; the click fence reads an
    address as a browser does (backslashes, name@host, <base href>, role=button with an
    address, formaction, form=) and refuses anything it cannot read; a redirect or a
    page that moves itself is stopped, but only after the load - said and pinned; the
    program is stopped after idle time by a watchdog; hidden text in a page does not
    reach the model; upper-case password boxes; sign-in wording in English, Spanish,
    German and French, also for the "Headless" default; more captcha wording and
    email-first sign-ins; a click lands on the box that was approved; rule 1 for typed
    words and addresses; a check that cannot read its answer refuses.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import threading
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, SHIPPED, require_shipped  # noqa: E402

require_shipped("jarvis_browser_engine.py", "jarvis_obscura.py", "jarvis_browser_control.py",
                "jarvis_child_env.py", "jarvis_local_http.py", "jarvis_agent.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-browser-engine-"))
CFG: dict = {}
AUDIT: list = []
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: CFG
fw.audit_log = lambda event, detail=None, **k: AUDIT.append((event, detail))
fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = fw

import jarvis_browser_control as B  # noqa: E402
import jarvis_browser_engine as E  # noqa: E402
import jarvis_obscura as OB  # noqa: E402

FAKE = HERE / "_fake_obscura.py"
PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


_REAL_CHILD_ENV = OB.child_env
import jarvis_local_http as LH  # noqa: E402

_REAL_RESOLVE = LH._resolved_addresses
_REAL_VISIBLE = E.visible_available


def _fake_resolve(host):
    """No network here: a literal address is itself, localhost is this PC, and
    every made-up *.test name is a public address."""
    import ipaddress
    ip = LH._as_address(host)
    if ip is not None:
        return [ip]
    if host == "localhost":
        return [ipaddress.ip_address("127.0.0.1")]
    if host.endswith(".test"):
        return [ipaddress.ip_address("93.184.216.34")]
    return []


LH._resolved_addresses = _fake_resolve


def fresh():
    d = Path(tempfile.mkdtemp(prefix="cfg-", dir=_TMP))
    fw.CONFIG_DIR = d
    CFG.clear()
    AUDIT.clear()
    OB._DIGEST_CACHE.update(key=None, digest="")
    E._reset_for_tests()
    E.HEADLESS._driver = None
    E.HEADLESS._fence = None
    OB.child_env = _REAL_CHILD_ENV
    E.visible_available = lambda: (True, "")      # the second card's lane is a separate rule
    return d


def install_program():
    """A pretend Obscura file, checked, so the driver's own checks pass."""
    exe = OB.exe_path()
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"MZ-pretend-obscura")
    OB.save_check({"version": "0.0.0-test", "digest": OB.digest_of(exe), "at": time.time(),
                   "stealth_ok": True, "private_refused": True})
    return exe


def rig(mode="", *, on=True, installed=True, log=None):
    """Settings folder, a checked program file, the switch, and the engine wired
    to the stand-in program."""
    fresh()
    if installed:
        install_program()
    if on:
        E.set_obscura(True)
    env_log = str(log) if log else ""

    def env(base=None):
        e = _REAL_CHILD_ENV(base)
        e["FAKE_MODE"], e["FAKE_LOG"] = mode, env_log
        return e
    OB.child_env = env
    d = OB.Driver(command_fn=lambda: [sys.executable, str(FAKE), "--stealth", "mcp"], verify=False)
    E.HEADLESS._driver = d
    return d


def calls(log: Path) -> list:
    try:
        return [json.loads(l) for l in log.read_text().splitlines() if '"call"' in l]
    except OSError:
        return []


def run_plan(goal, requests, *, mode="headless", allowed=None, approved=True):
    """Plan and run through the real functions, the way jarvis_agent does."""
    pick = E.choose(mode, goal=goal, requests=requests)
    assert not pick["refused"], pick
    p = B.plan(goal, "s1", requests, allowed_domains=allowed, engine=pick["engine"],
               engine_why=pick["why"])
    return p, B.run(p, approved=approved)


NAV = {"action": "navigate", "value": "https://example.test/", "why": "open it"}


# ==========================================================================
#   1. The switch
# ==========================================================================

def t_off_by_default_and_damaged_means_off():
    fresh()
    check("no file: off, Automatic", E.settings() == {"obscura": False, "mode": "auto", "why": ""})
    check("off means headless is not offered and cannot run",
          E.headless_offered() is False and E.ready()[0] is False and "off" in E.ready()[1])
    p = E.settings_path()
    for raw in ("not json", "[]", json.dumps({"obscura": "yes"}), json.dumps({"obscura": None})):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(raw, encoding="utf-8")
        st = E.settings()
        check(f"a damaged file {raw!r}: off, and why says so", st["obscura"] is False and st["why"], st)
    p.write_text(json.dumps({"obscura": True, "mode": "banana"}), encoding="utf-8")
    check("an unknown mode reads as Automatic", E.settings()["mode"] == "auto"
          and E.settings()["obscura"] is True)


class V:
    def __init__(self, outcome, allowed=None, tier="ask"):
        self.outcome, self.tier = outcome, tier
        self.allowed = (outcome == "approved") if allowed is None else allowed
        self.reason = outcome


class Card:
    def __init__(self, verdict=None, tier="ask"):
        fresh()
        self.applied, self.cards, self.later = [], [], []
        self.verdict, self.tier = verdict or V("approved"), tier

    def apply(self, on):
        self.applied.append(on)
        return E.set_obscura(on)

    def gate(self, action, detail, prompt):
        self.cards.append((action, detail, prompt))
        return self.verdict

    def req(self, enabled):
        return E.request(enabled, self.apply, gate=self.gate, tier_of=lambda a: self.tier,
                         spawn=self.later.append)

    def run(self):
        for fn in list(self.later):
            fn()
        self.later.clear()


def t_on_raises_one_card_and_changes_nothing_until_yes():
    c = Card()
    code, out = c.req(True)
    check("ON answers 202 waiting, not 'on'", code == 202 and out["waiting"] and out["obscura"] is False, out)
    check("nothing is written before the card is answered",
          E.settings()["obscura"] is False and not c.applied and not c.cards)
    code2, _ = c.req(True)
    check("a second ON while the card waits raises no second card", code2 == 202 and len(c.later) == 1)
    c.run()
    check("ONE card, under the action obscura_enable", len(c.cards) == 1
          and c.cards[0][0] == E.ACTION == "obscura_enable")
    check("approved: only now is it on", E.settings()["obscura"] is True and c.applied == [True])
    check("the card says it leaves this PC (a new way onto the web)", c.cards[0][1]["leaves_this_pc"] is True
          and c.cards[0][1]["stealth"] is True)
    check("the last card's outcome is kept in words", E.view()["last"]["outcome"] == "enabled")
    code3, out3 = c.req(True)
    check("already on: 200, no second card", code3 == 200 and out3["obscura"] is True and not c.later)


def t_the_card_says_what_it_does():
    c = Card()
    c.req(True)
    c.run()
    text = c.cards[0][2]
    low = text.lower()
    for name, needle in [
        ("that it is a new program on this PC", "new program on your pc"),
        ("that it is open source Apache-2.0", "apache-2.0"),
        ("that every page/click/box still gets its own card", "still listed on its own approval card"),
        ("that what it reads is outside text", "outside text"),
        ("that it pretends to be an ordinary Chrome", "pretends to be an ordinary chrome"),
        ("that it never solves a captcha", "never solves a captcha"),
        ("that a site can still block it", "does not stop a site from blocking it"),
        ("that signing in could get an account closed", "closing an account you sign in to"),
        ("that it never types a password and stops at a sign-in page it recognises",
         "never types a password with it"),
        ("that it stops at a captcha and hands over", "hands the job to the visible browser"),
        ("that a sign-in starting with only a username may not be spotted", "may not be spotted"),
        ("what it checks in typed words and addresses", "looks like a password or key is refused"),
        ("that a redirect or a page that moves itself is noticed only after it has loaded",
         "can only be noticed after it has loaded"),
        ("the real time limits", "3 idle minutes and after 10 minutes in all"),
        ("that it cannot reach the owner's own network", "will not open this pc, your home network"),
        ("that no proxy is used", "no proxy is used"),
        ("that nothing is saved", "no cookies, no files"),
        ("that the card downloads nothing", "downloads nothing"),
        ("that off is instant", "instant"),
        ("what saying no costs", "if you say no: nothing changes"),
        ("the 'if you did not ask' line", "if you did not just ask for this, say no"),
    ]:
        check("the card says " + name, needle in low, needle)
    E.OB.exe_path().parent.mkdir(parents=True, exist_ok=True)
    check("not installed: the card says the switch will be on but it waits for the owner's own install",
          "not installed yet" in E.describe_on().lower())
    install_program()
    check("installed: the card says so", "already installed and checked" in E.describe_on())


def t_denied_timed_out_refused_withdrawn_all_leave_it_off():
    for outcome in ("denied", "timed_out", "refused"):
        c = Card(V(outcome))
        c.req(True)
        c.run()
        check(f"a card that ends {outcome}: still off, nothing written",
              E.settings()["obscura"] is False and c.applied == [])
    c = Card(V("approved", allowed=False))
    c.req(True)
    c.run()
    check("approved but not allowed: still off", E.settings()["obscura"] is False)
    c = Card(V("approved", tier="notify"))
    c.req(True)
    c.run()
    check("a yes at a tier that is not 'ask' is not a person saying yes", E.settings()["obscura"] is False)
    c = Card()
    c.req(True)
    code, out = c.req(False)
    c.run()
    check("turned off while the card waited: approving it changes nothing",
          code == 200 and E.settings()["obscura"] is False and c.applied == [False], (code, out))
    c = Card(tier="auto")
    code, out = c.req(True)
    check("a tier that is not 'ask' raises no card, and says why",
          code == 503 and not c.later and "must ask you first" in out["error"] or "It must ask you first" in out["error"], (code, out))
    check("a non-boolean is refused", Card().req("yes")[0] == 400)
    c = Card()
    c.gate = lambda *a: (_ for _ in ()).throw(RuntimeError("no queue"))
    c.req(True)
    c.run()
    check("a gate that breaks leaves it off", E.settings()["obscura"] is False)


def t_off_is_immediate_and_stops_the_program():
    d = rig()
    d.call("browser_navigate", {"url": "https://example.test/"})
    proc = d.proc
    check("running before", d.alive())
    code, out = E.request(False, E.set_obscura)
    check("OFF is 200 at once", code == 200 and out["obscura"] is False and out["waiting"] is False, out)
    check("... and the program is stopped", proc.poll() is not None and not d.alive())
    check("... and headless can no longer run", E.ready()[0] is False)


# ==========================================================================
#   2. Which browser
# ==========================================================================

READ = [dict(NAV), {"action": "read_page", "value": "0", "why": "read"}]


def t_the_mode_rule():
    rig()
    c = lambda mode=None, goal="read the news page", reqs=None: E.choose(mode, goal=goal, requests=reqs or READ)
    check("auto + plain reading + headless on -> headless", c()["engine"] == "headless" and not c()["refused"])
    check("an explicit visible is always visible", c("visible")["engine"] == "visible")
    check("an explicit headless is headless", c("headless")["engine"] == "headless")
    for goal in ("log in to my bank", "sign in and read my orders", "check out the basket",
                 "buy the book", "solve the captcha", "read my account page", "pay the bill"):
        check(f"auto + {goal!r} -> visible (the owner may need to take over)",
              c(goal=goal)["engine"] == "visible", c(goal=goal))
    check("auto + a request that names a sign-in box -> visible",
          c(reqs=READ + [{"action": "click", "role": "button", "name": "Log in", "why": "x"}])["engine"]
          == "visible")
    sec = READ + [{"action": "type", "role": "textbox", "name": "Note", "value": "<secret>pw</secret>"}]
    check("auto + a saved secret -> visible", c(reqs=sec)["engine"] == "visible")
    check("a headless ASK with a saved secret is refused in words (not moved quietly)",
          c("headless", reqs=sec)["refused"] and "visible" in c("headless", reqs=sec)["refused"])
    rn = READ + [{"action": "read_new", "role": "log", "name": "Chat", "value": "0"}]
    check("auto + reading a message list -> visible", c(reqs=rn)["engine"] == "visible")
    check("the owner's default 'visible' wins over auto", (E.set_mode("visible"), c())[1]["engine"] == "visible")
    check("'Always the visible browser' wins over a request for the headless one (both apps promise it)",
          c("headless")["engine"] == "visible" and "always the visible" in c("headless")["why"]
          and not c("headless")["refused"], c("headless"))
    check("the owner's default 'headless' is followed when it can run",
          (E.set_mode("headless"), c())[1]["engine"] == "headless")
    check("a default of 'headless' is followed for plain reading", c()["engine"] == "headless")
    check("... but NOT for a task that looks like a sign-in or a payment: the mode help says so, and the words "
          "test applies to this default too (this replaces a check that asserted the opposite - the help text "
          "promised 'not for a sign-in' and the code did not keep it)",
          c(goal="buy the book")["engine"] == "visible" and "sign in" in c(goal="buy the book")["why"])
    check("a bad mode is refused and changes nothing",
          E.set_mode("stealthy")["ok"] is False and E.settings()["mode"] == "headless")
    E.set_mode("auto")
    # headless cannot run
    E.set_obscura(False)
    r = c("headless")
    check("headless asked for, switch OFF: refused in words, and NOT silently visible",
          r["refused"] and "off" in r["refused"].lower() and "did not switch to the visible browser" in r["refused"], r)
    r = c()
    check("auto with the switch off: visible, with nothing to explain on every card",
          r["engine"] == "visible" and r["why"] == "" and not r["refused"], r)
    E.set_obscura(True)
    E.set_mode("headless")
    OB.exe_path().write_bytes(b"MZ-swapped")
    r = c()
    check("a default 'headless' that cannot run (file changed) falls back to visible AND says so",
          r["engine"] == "visible" and "cannot run right now" in r["why"] and "not the one Jarvis checked" in r["why"], r)
    r = c("headless")
    check("...but an explicit headless ask with a changed file is refused", r["refused"] and "not the one Jarvis checked" in r["refused"])
    line = E.card_line("visible", r["why"])
    check("the card's first line names the engine and why", line.startswith("Browser: visible")
          and E.card_line("headless", "x").startswith("Browser: no window (Obscura)"))
    check("the headless line says stealth is on, that it can still be blocked, and that it stops at captchas",
          "pretends to be an ordinary Chrome" in E.card_line("headless", "x") and "does not stop a site blocking it"
          in E.card_line("headless", "x") and "stops at any captcha" in E.card_line("headless", "x"))


# ==========================================================================
#   3. Acting only inside an approved plan
# ==========================================================================

def t_no_action_outside_an_approved_plan():
    log = _TMP / "log-bare.jsonl"
    d = rig(log=log)
    eng = E.HEADLESS
    for name, fn in (("open", lambda: eng.open("https://example.test/")), ("text", eng.text),
                     ("snapshot", eng.snapshot), ("markdown", eng.markdown), ("links", eng.links),
                     ("screenshot", eng.screenshot), ("click", lambda: eng.click("link", "About us")),
                     ("fill", lambda: eng.fill("textbox", "Search", "x")),
                     ("submit", lambda: eng.submit("button", "Go")),
                     ("select", lambda: eng.select("combobox", "Colour", "red")),
                     ("value_of", lambda: eng.value_of("textbox", "Search"))):
        try:
            fn()
            check(f"a bare {name}() is refused", False)
        except E.EngineRefused:
            check(f"a bare {name}() is refused", True)
    check("...and the program was never started nor asked anything", not d.alive() and not calls(log))
    vis = E.VISIBLE
    refused = []
    for name, fn in (("open", lambda: vis.open("https://example.test/")), ("text", vis.text),
                     ("click", lambda: vis.click("link", "x")), ("fill", lambda: vis.fill("textbox", "x", "y")),
                     ("screenshot", vis.screenshot), ("links", vis.links), ("snapshot", vis.snapshot)):
        try:
            fn()
        except E.EngineRefused:
            refused.append(name)
    check("the visible engine's interface is held to the same rule", len(refused) == 7, refused)
    out = B.run(B.plan("g", "s", [], read=lambda s: {}), approved=False)
    check("a plan that was not approved does nothing (unchanged)", out["ok"] is False and "not approved" in out["reason"])
    with E.approved_run():
        check("only inside approved_run does the door open", getattr(E._APPROVED, "on", False) is True)
    check("... and it closes again", getattr(E._APPROVED, "on", False) is False)


def t_a_headless_plan_end_to_end():
    log = _TMP / "log-e2e.jsonl"
    d = rig(log=log)
    p, out = run_plan("read the example site", [dict(NAV), {"action": "read_page", "value": "0", "why": "read"}])
    text = B.describe(p)
    check("the card's FIRST line names the browser, no window, and that it pretends to be Chrome",
          text.split("\n\n")[1].startswith("Browser: no window (Obscura)")
          and "pretends to be an ordinary Chrome" in text, text[:300])
    check("the plan is on the headless engine", p.engine == "headless")
    check("the run finished", out["ok"] is True and len(out["done"]) == 2, out)
    page = out["done"][1]["value"]
    check("the page's words came back in a small piece, with a trailer saying where to continue",
          "Welcome to the example page." in page and "more" in page.lower() and
          len(page) < B._MAX_PAGE_TEXT_CHARS + 400, page[-160:])
    check("the program was started with --stealth and the standard-input server only",
          json.loads(log.read_text().splitlines()[0])["argv"] == ["--stealth", "mcp"])
    # follow a link on the same site
    p2, out2 = run_plan("go to the about page", [{"role": "link", "name": "About us", "action": "click",
                                                  "why": "follow it"}])
    check("a link on the same site is followed", out2["ok"] is True, out2)
    p3, out3 = run_plan("read it", [{"action": "read_page", "value": "0", "why": "read"}])
    check("the next plan reads the page it landed on", "Founded in a shed" in out3["done"][0]["value"], out3)
    # fill, select and read back
    run_plan("home", [{"action": "navigate", "value": "https://example.test/", "why": "back"}])
    p4, out4 = run_plan("search", [
        {"role": "textbox", "name": "Search", "action": "type", "value": "hedgehogs", "why": "type"},
        {"role": "combobox", "name": "Colour", "action": "select", "value": "red", "why": "pick"},
        {"role": "textbox", "name": "Search", "action": "read", "why": "check"}])
    check("filling, selecting and reading a box back all work", out4["ok"] is True
          and out4["done"][2]["value"] == "hedgehogs", out4)
    typed = [c for c in calls(log) if c["call"] == "browser_fill"]
    check("the typed words reached the box exactly", typed and typed[-1]["args"]["value"] == "hedgehogs")
    check("only listed tools were ever called", all(c["call"] in OB.ALLOWED_TOOLS for c in calls(log)))
    check("evaluate and cookie tools were never called",
          not any("evaluate" in c["call"] or "cookie" in c["call"] for c in calls(log)))
    p5, out5 = run_plan("go", [{"role": "button", "name": "Go", "action": "click", "why": "submit the search"}])
    check("a button whose form goes to the same site is pressed", out5["ok"] is True, out5)
    d.stop("t")


def t_the_fence_holds_before_a_click():
    log = _TMP / "log-fence.jsonl"
    d = rig(log=log)
    run_plan("open", [dict(NAV)])
    n0 = len([c for c in calls(log) if c["call"] == "browser_click"])
    for label, req, words in (
        ("a link to another site", {"role": "link", "name": "Elsewhere", "action": "click", "why": "x"},
         "outside the allowed sites"),
        ("a mailto: link", {"role": "link", "name": "Mail me", "action": "click", "why": "x"},
         "does not open a web address"),
        ("a button that sends its form to another site", {"role": "button", "name": "Send away",
                                                           "action": "click", "why": "x"},
         "sends its form to"),
    ):
        p, out = run_plan("try", [req])
        check(f"{label}: the run stops in words", out["ok"] is False and words in out["reason"], out)
        check(f"{label}: and the click was NEVER made",
              len([c for c in calls(log) if c["call"] == "browser_click"]) == n0)
    p, out = run_plan("try", [{"role": "link", "name": "Elsewhere", "action": "click", "why": "x"}],
                      allowed=["example.test", "other.test"])
    check("a plan that NAMED the other site as allowed may follow it", out["ok"] is True, out)
    d.stop("t")


def t_own_network_addresses_are_refused_before_obscura_is_asked():
    log = _TMP / "log-private.jsonl"
    d = rig(log=log)
    for url in ("http://127.0.0.1:8080/", "http://localhost/", "http://192.168.1.5/router",
                "http://10.0.0.1/", "http://100.64.3.4/", "http://172.16.0.9/", "http://169.254.169.254/",
                "http://[::1]/"):
        p, out = run_plan("look", [{"action": "navigate", "value": url, "why": "x"}])
        check(f"{url} is refused in words", out["ok"] is False and "did not open that address" in out["reason"], out)
    check("...and Obscura was never even asked to navigate",
          not [c for c in calls(log) if c["call"] == "browser_navigate"])
    p, out = run_plan("look", [{"action": "navigate", "value": "file:///C:/secrets.txt", "why": "x"}])
    check("a file: address never becomes a step", not p.steps and p.unmatched and "scheme" in p.unmatched[0]["reason"])
    p, out = run_plan("look", [{"action": "navigate", "value": "https://93.184.216.34/", "why": "x"}])
    check("a public address that Obscura cannot load is reported in words, not as a crash",
          out["ok"] is False and "step 1 failed" in out["reason"], out)
    d.stop("t")


def t_a_captcha_or_sign_in_page_hands_the_job_over():
    d = rig()
    p, out = run_plan("read it", [{"action": "navigate", "value": "https://challenge.test/", "why": "x"}],
                      allowed=["challenge.test"])
    check("a captcha / 'just a moment' page stops the run", out["ok"] is False, out)
    r = out["reason"]
    check("...and says why, and how to carry on in the visible browser",
          "captcha" in r and "no window" in r and "never solves" in r and "use the visible browser" in r, r)
    check("the step that landed there is reported as done, nothing after it ran", len(out["done"]) == 1)
    p, out = run_plan("read it", [{"action": "navigate", "value": "https://example.test/login", "why": "x"}])
    check("a sign-in page (it has a password box) stops the run too",
          out["ok"] is False and "sign-in page" in out["reason"] and "use the visible browser" in out["reason"], out)
    d.stop("t")
    d = rig("captcha")
    p, out = run_plan("read it", [dict(NAV)])
    check("a page that is a captcha whatever the address is caught too", out["ok"] is False and "captcha" in out["reason"])
    d.stop("t")
    log = _TMP / "log-signin-fill.jsonl"
    d = rig(log=log)
    run_plan("open the sign-in page", [{"action": "navigate", "value": "https://example.test/login", "why": "x"}])
    pw = B.plan("t", "s1", [{"role": "textbox", "name": "Email", "action": "type", "value": "a@b.test", "why": "x"}],
                engine="headless")
    check("(this replaces a check that only asserted True) a plan made ON a sign-in page carries the hand-over "
          "words among its notices - it does NOT refuse the box at plan time",
          any("sign-in page" in n and "use the visible browser" in n for n in pw.notices) and len(pw.steps) == 1,
          (pw.notices, pw.steps))
    out = B.run(pw, approved=True)
    check("... and running it stops before anything is typed: the page wants a person",
          out["ok"] is False and out["done"] == [] and "sign-in page" in out["reason"], out)
    check("... nothing was filled in", not [c for c in calls(log) if c["call"] == "browser_fill"])
    d.stop("t")
    check("the words of the hand-over are fixed and plain", "no window" in E.HANDOVER
          and "never types a password and never solves a captcha" in E.HANDOVER)


def t_secrets_passwords_and_message_lists_never_headless():
    d = rig()
    p, _ = run_plan("open", [dict(NAV)])
    reqs = [
        {"role": "textbox", "name": "Search", "action": "type", "value": "<secret>mail_pw</secret>", "why": "x"},
        {"action": "read_new", "role": "log", "name": "Chat", "value": "0", "why": "x"},
    ]
    p = B.plan("g", "s1", reqs, engine="headless")
    check("a <secret> step is refused at plan time, its value withheld",
          not p.steps and "never types a saved secret" in p.unmatched[0]["reason"]
          and p.unmatched[0]["value"] == "(withheld)", p.unmatched)
    check("a message list ('read_new') is refused at plan time in words",
          "cannot read a message list" in p.unmatched[1]["reason"])
    d.stop("t")
    # A stray space in the action name must not skip the checks (plan() strips it).
    JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    for act in ("navigate", " navigate", "navigate ", "\tnavigate"):
        p = B.plan("g", "s1", [{"action": act, "value": "https://a.test/?token=" + JWT, "why": "x"}],
                   engine="headless")
        check(f"a token in an address is refused at plan time for action {act!r}", not p.steps, p.steps)
    # ... and the engine itself refuses to open such an address, whatever reached it.
    d = rig()
    run_plan("open", [dict(NAV)])
    with E.approved_run():
        E.HEADLESS.set_fence(lambda host: True)
        try:
            E.HEADLESS.open("https://a.test/?token=" + JWT)
            check("open() refuses an address holding a token", False)
        except RuntimeError as exc:
            check("open() refuses an address holding a token, by itself", "password, key or token" in str(exc), str(exc))
    d.stop("t")
    # an engine-level guard as well: a password box is never typed into
    d = rig()
    run_plan("open login", [{"action": "navigate", "value": "https://example.test/login", "why": "x"}])
    with E.approved_run():
        try:
            E.HEADLESS.fill("textbox", "Password", "hunter2")
            check("typing into a password box is refused", False)
        except RuntimeError as exc:
            check("typing into a password box is refused by the engine itself", "never types into a password" in str(exc))
    d.stop("t")


def t_a_run_that_cannot_run_stops_in_words_and_never_opens_the_other_browser():
    d = rig()
    p = B.plan("read", "s1", [dict(NAV)], engine="headless", engine_why="x")
    E.set_obscura(False)
    trap = []
    real = (B._default_act, B._default_read, B._page_for)
    B._default_act = lambda step: trap.append("visible act")
    B._default_read = lambda s: trap.append("visible read") or {}
    B._page_for = lambda *a, **k: trap.append("visible page")
    try:
        out = B.run(p, approved=True)
    finally:
        B._default_act, B._default_read, B._page_for = real
    check("switched off after the card: the run stops in words", out["ok"] is False and "off" in out["reason"].lower(), out)
    check("nothing ran and every step is reported as not run", out["done"] == [] and len(out["not_run"]) == 1)
    check("and the visible browser was NEVER used instead", trap == [], trap)
    try:
        B.plan("read", "s1", [dict(NAV)], engine="headless")
        check("planning for a headless engine that cannot run is refused", False)
    except RuntimeError as exc:
        check("planning for a headless engine that cannot run is refused, in words", "off" in str(exc).lower())
    E.set_obscura(True)
    OB.exe_path().write_bytes(b"MZ-changed")
    out = B.run(p, approved=True)
    check("a program that changed after the card is not started", out["ok"] is False and "not the one Jarvis checked" in out["reason"], out)
    check("nothing was started", not d.alive())


def t_off_is_not_held_up_by_a_call_in_flight():
    """A call can wait up to CALL_TIMEOUT_S; turning the switch off or Stop everything
    must not wait for it (the program is killed first, without the call's lock)."""
    real = OB.CALL_TIMEOUT_S
    OB.CALL_TIMEOUT_S = 30.0
    d = rig("hang")
    out = {}

    def call():
        try:
            d.call("browser_navigate", {"url": "https://example.test/"})
        except OB.ObscuraError as exc:
            out["code"] = exc.code
    t = threading.Thread(target=call, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not d.alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    time.sleep(0.5)                      # the call is now waiting on the program
    t0 = time.monotonic()
    code, resp = E.request(False, E.set_obscura)
    took = time.monotonic() - t0
    t.join(10)
    OB.CALL_TIMEOUT_S = real
    check("turning it off answered at once, not after the call's own time limit",
          code == 200 and took < 5, f"took {took:.1f}s")
    check("the waiting call ended, saying the program died - not hung", out.get("code") == "died", out)
    check("and nothing is running", not d.alive())


def t_stop_everything_and_limits():
    d = rig()
    run_plan("open", [dict(NAV)])
    check("running", d.alive())
    proc = d.proc
    import jarvis_stop_all as SA
    check("the headless browser is on Stop everything's list once installed",
          E.register_stopper() and "headless_browser" in SA._stoppers)
    said = SA._stoppers["headless_browser"]()
    check("Stop everything kills the headless program and says so",
          proc.poll() is not None and not d.alive() and said == "The windowless browser was stopped.", said)
    check("with nothing running it says nothing", SA._stoppers["headless_browser"]() is None)
    SA.unregister("headless_browser")
    d = rig()
    run_plan("open", [dict(NAV)])
    proc = d.proc
    E.stop_all("Stop everything")
    check("stop_all itself kills it too", proc.poll() is not None and not d.alive())
    real = OB.PAGE_CALLS_MAX
    OB.PAGE_CALLS_MAX = 2
    try:
        p, out = run_plan("a lot", [dict(NAV), {"action": "navigate", "value": "https://example.test/about", "why": "x"},
                                    {"action": "navigate", "value": "https://example.test/", "why": "x"}])
        check("the page cap stops a plan mid-way, in words", out["ok"] is False and "limit of pages" in out["reason"]
              and len(out["done"]) == 2, out)
    finally:
        OB.PAGE_CALLS_MAX = real
    d.stop("t")


def t_nothing_is_learned_from_a_page():
    """The result of a headless plan goes through the same took_in as the visible
    one: outside text, the conversation is marked, never a fact."""
    import jarvis_agent as A
    d = rig()
    p, out = run_plan("read it", [dict(NAV), {"action": "read_page", "value": "0", "why": "x"}])
    watch = A._TurnWatch() if callable(getattr(A, "_TurnWatch", None)) else None
    if watch is None:
        check("jarvis_agent has _TurnWatch", False)
        return
    res = watch.took_in("browser_control", out)
    check("a headless page read is labelled outside text", A.OUTSIDE_FIELD in res)
    check("... and counted as a read this turn (a note written afterwards asks)",
          watch.read.get("browser_control") == 1 and bool(watch.note_needs_a_person()))
    src = (HERE / "jarvis_browser_engine.py").read_text()
    check("the engine module never writes to memory (no memory/learn import)",
          not re.search(r"import jarvis_memory|import jarvis_auto_learn|jarvis_extract", src))
    d.stop("t")


# ==========================================================================
#   4. The agent's tool
# ==========================================================================

def t_the_agent_tool():
    import jarvis_agent as A
    d = rig()
    args = {"goal": "read the example site", "session": "s1", "requests": [dict(NAV)]}
    state, text = A._prepare_browser_control(dict(args))
    check("auto + plain reading + headless on: the plan is headless and the card says so",
          state.engine == "headless" and "Browser: no window (Obscura)" in text)
    state, text = A._prepare_browser_control(dict(args, mode="visible", requests=[dict(NAV)]))
    check("mode 'visible' is passed through (and needs no engine hooks)", state.engine == "visible"
          and "Browser: visible" in text, text[:200])
    E.set_obscura(False)
    state, text = A._prepare_browser_control(dict(args, mode="headless"))
    check("headless asked for but off: a refusal that carries its plain words, not a plan",
          isinstance(state, A._NoBrowser) and "cannot run" in state.problem and "Nothing" not in state.problem, text)
    check("running such a plan says why and does nothing", A._run_browser_control(args, state)["ok"] is False)
    check("headless can be asked for in the tool's schema, with the rule in its words",
          "mode" in A.TOOLS["browser_control"].parameters["properties"]
          and A.TOOLS["browser_control"].parameters["properties"]["mode"]["enum"] == ["auto", "headless", "visible"])
    # offering the tool
    check("with the headless engine off and no second card the browser tool is NOT offered",
          "browser_control" not in A.offered_tools({"browser_control"}))
    E.set_obscura(True)
    check("with the headless engine on and ready it IS offered (no second card needed)",
          "browser_control" in A.offered_tools({"browser_control"}))
    check("...and only if the owner listed it in [tools].enabled",
          "browser_control" not in A.offered_tools({"calculator"}))
    check("browser_control is still a tool that needs a person (its card, every time)",
          "browser_control" in A.NEEDS_A_PERSON)
    d.stop("t")


# ==========================================================================
#   5. What the apps read, the routes, and what is NOT there
# ==========================================================================

def t_view_and_panel():
    fresh()
    v = E.view()
    check("off: the view says so, in the fixed words", v["obscura"] is False and v["line"] == E.WORDS["off_line"]
          and v["stealth"] is True and v["modes"] == ["auto", "visible", "headless"], v)
    check("it carries the install line and where it comes from", "Invoke-WebRequest" in v["install_line"]
          and v["download_from"].startswith("https://github.com/h4ckf0r0day/obscura") and v["licence"] == "Apache-2.0")
    check("not installed: the status line says so", v["status_line"] == "Obscura is not installed on this PC yet.")
    install_program()
    E.set_obscura(True)
    v = E.view()
    check("on and installed: ready, with the version and date in words",
          v["ready"] is True and "version 0.0.0-test" in v["status_line"] and "last checked" in v["status_line"], v)
    OB.exe_path().write_bytes(b"changed!")
    v = E.view()
    check("a changed file: on, but not working yet, in words",
          v["ready"] is False and "not working yet" in v["line"] and "not the one Jarvis checked" in v["status_line"], v)
    words = json.dumps(v)
    check("the view carries no word from any web page (only state and fixed words)",
          "Welcome to the example" not in words)
    pn = E.panel(v)
    check("the panel: available, on, line, status, install line", pn["available"] and pn["obscura"]
          and pn["status"] and pn["install_line"] and pn["mode"] == "auto")
    check("a payload that is not the shape reads as 'could not read'",
          E.panel({"x": 1}) == {"available": False, "obscura": False, "waiting": False, "checked": False,
                                "mode": "auto", "line": E.WORDS["unread"], "status": "", "install_line": ""})
    w = E.panel({"obscura": False, "waiting": True, "line": ""})
    check("while the card waits the switch looks on but the line says it is only waiting",
          w["checked"] is True and w["waiting"] is True and w["line"] == E.WORDS["waiting_line"])
    check("an unknown mode in a payload shows as Automatic", E.panel({"obscura": True, "mode": "x"})["mode"] == "auto")


def t_routes():
    fresh()
    sent = []

    class H:
        path = E.PATH

        def do_GET(self):
            sent.append(("orig-get", self.path))

        def do_POST(self):
            sent.append(("orig-post", self.path))

        def _send(self, code, body):
            sent.append((code, body))
    banner = E.install(H, origin_ok=lambda h: True, token_ok=lambda h: True,
                       read_body=lambda h: json.dumps(h.body).encode())
    check("install() answers with a banner line saying it is off", "off" in banner and "browser" in banner)
    check("installing twice is harmless", "already on" in E.install(H, origin_ok=lambda h: True,
                                                                    token_ok=lambda h: True, read_body=None))
    h = H()
    h.do_GET()
    check("GET /api/browser/engine answers the view", sent[-1][0] == 200 and sent[-1][1]["obscura"] is False)
    h.path = "/api/other"
    h.do_GET()
    check("any other route goes straight to the original", sent[-1] == ("orig-get", "/api/other"))
    h.path = E.PATH
    h.body = {"mode": "visible"}
    h.do_POST()
    check("POST {mode} is saved at once, no card", sent[-1][0] == 200 and E.settings()["mode"] == "visible")
    h.body = {"mode": "nonsense"}
    h.do_POST()
    check("a bad mode is a 400", sent[-1][0] == 400)
    h.body = {"obscura": "sure"}
    h.do_POST()
    check("a non-boolean switch is a 400", sent[-1][0] == 400)

    class Deny:
        def __init__(self, ok):
            self.ok = ok

    H2 = type("H2", (), {"do_GET": lambda s: None, "do_POST": lambda s: None,
                         "_send": lambda s, c, b: sent.append((c, b)), "path": E.PATH})
    E.install(H2, origin_ok=lambda h: False, token_ok=lambda h: True, read_body=lambda h: b"{}")
    H2().do_GET()
    check("a cross-origin request is refused with 403", sent[-1][0] == 403)
    E.install(type("H3", (), {"do_GET": lambda s: None, "do_POST": lambda s: None,
                              "_send": lambda s, c, b: sent.append((c, b)), "path": E.PATH}),
              origin_ok=lambda h: True, token_ok=lambda h: False, read_body=lambda h: b"{}")


def t_no_proxy_and_nothing_hidden():
    src = (HERE / "jarvis_browser_engine.py").read_text() + (HERE / "jarvis_obscura.py").read_text()
    for bad in ('"--proxy"', "'--proxy'", '"OBSCURA_PROXY":', "proxy=", "set_proxy", "proxy_url"):
        check(f"nothing in the code passes or stores {bad}", bad not in src)
    keys = set(json.loads(json.dumps(E.settings())).keys())
    check("the settings hold only the switch, the mode and a reason - never a proxy or an address",
          keys == {"obscura", "mode", "why"})
    check("the view offers no way to set a proxy", not any("proxy" in k for k in E.view()))
    import jarvis_local_http
    check("the address check is the shared one (this PC, home, Tailscale and Meshnet all refused)",
          callable(jarvis_local_http.private_fetch_problem))
    # (The chatbot files keep the visible browser: t_the_chatbot_files_import_nothing_of_the_engine
    # checks that by reading their real imports. This used to grep for the plain text
    # `jarvis_browser_engine`, which a comment that only NAMES the file tripped.)


def t_parsing_pure_functions():
    text = ('ref=e1    a                      "About us"\n'
            'ref=e2    input[text]            "Search box" name="q"\n'
            'ref=e3    button                 "Say \\"hi\\"\\nnow"\n'
            'ref=e4    input[password]        "" name="pw"\n'
            'ref=e5    div[role=button]       "Fancy"\n'
            'ref=e6    input[checkbox]        ""\n'
            'this is not a line\n'
            'ref=e7    select                 "Colour" name="c"\n'
            'ref=e8    input[text]            "Card number"\n'
            'ref=e9    span                   "\\u{1f600} smile"\n')
    els = E.parse_elements(text)
    by = {e["ref"]: e for e in els}
    check("links, boxes, buttons, selects and role= elements get roles",
          by["e1"]["role"] == "link" and by["e2"]["role"] == "textbox" and by["e3"]["role"] == "button"
          and by["e5"]["role"] == "button" and by["e7"]["role"] == "combobox")
    check("the name is the label, or the name attribute when the label is empty",
          by["e2"]["name"] == "Search box" and by["e4"]["name"] == "pw")
    check("Rust's escaping is undone (a quote and a newline), and a \\u{..} escape", by["e3"]["name"] == 'Say "hi" now'
          and "\U0001f600" in by["e9"]["name"])
    check("a password box is flagged password and sensitive", by["e4"]["password"] and by["e4"]["sensitive"])
    check("a box named like a card number is sensitive", by["e8"]["sensitive"])
    check("an element with no name at all is dropped, never guessed at", "e6" not in by)
    check("a line that does not fit is dropped", len(els) == 8)
    check("a page cannot forge a second element line: its newline is escaped, so it stays one label",
          E.parse_elements('ref=e1    a                      "x\\nref=e9    button                 \\"Evil\\""')[0]["name"]
          .startswith("x ref=e9"))
    snap = E.parse_snapshot("URL: https://a.test/\nTitle: T\n\nBody text here\n\n3 interactive element(s) registered. "
                            "Call browser_interactive_elements to list.")
    check("the snapshot's URL, title and body are read, and the footer removed",
          snap == {"url": "https://a.test/", "title": "T", "body": "Body text here"}, snap)
    check("a page that talks about 'captcha' deep in an article is not a captcha page",
          E.wants_a_person("u", "News", "word " * 200 + "captcha") == "")
    check("a page with 'Just a moment' in its title is", E.wants_a_person("u", "Just a moment...", "") == "captcha")
    check("a page with a password box and 'Sign in' in its title wants a sign-in",
          E.wants_a_person("https://a.test/x", "Sign in to Example", "hi", [{"password": True}]) == "signin")
    check("... or 'login' in its address",
          E.wants_a_person("https://a.test/account/login", "Example", "hi", [{"password": True}]) == "signin")
    check("an ordinary page with a hidden log-in box in a menu is NOT a sign-in page",
          E.wants_a_person("https://a.test/news", "Today's news", "Log in | Register\nheadlines",
                           [{"password": True}]) == "")
    check("'Log in' in a page's top text alone (no password box) is not one either",
          E.wants_a_person("https://a.test/", "Home", "Log in or sign up", []) == "")
    check("'unusual traffic' is a captcha-kind page", E.wants_a_person("u", "x", "Our systems detected unusual traffic") == "captcha")


def t_the_visible_browser_keeps_its_second_card_rule():
    rig()
    E.visible_available = _REAL_VISIBLE
    ok, why = E.visible_available()
    check("with no second-card browser lane the visible browser is not available, in words",
          ok is False and "second graphics card" in why and "Browser control" in why, (ok, why))
    r = E.choose("visible", goal="read", requests=READ)
    check("an explicit 'visible' is refused in words, nothing opened",
          r["refused"] and "Nothing was opened" in r["refused"] and "second graphics card" in r["refused"], r)
    check("plain reading in Automatic still works headless without the second card",
          E.choose(None, goal="read the page", requests=READ)["engine"] == "headless")
    r = E.choose(None, goal="log in and read my orders", requests=READ)
    check("a task that needs the visible browser (a sign-in) is refused rather than run headless",
          r["refused"] and "sign in" in r["refused"] and "second graphics card" in r["refused"], r)
    E.set_mode("visible")
    check("a default of 'visible' is refused the same way", bool(E.choose(None, goal="read", requests=READ)["refused"]))
    E.set_obscura(False)
    E.set_mode("auto")
    r = E.choose(None, goal="read", requests=READ)
    check("with the headless browser off too, the answer is still a plain refusal, not a crash",
          r["refused"] and "visible browser" in r["refused"], r)
    E.visible_available = lambda: (True, "")
    check("with the lane working the visible browser is chosen as before",
          E.choose("visible", goal="read", requests=READ)["engine"] == "visible")


class FakePage:
    def __init__(self):
        self.went, self.shots = [], 0
        self.url = "about:blank"

    def goto(self, url, **kw):
        self.went.append((url, kw))
        self.url = url

    def evaluate(self, script, *a):
        if "document.links" in script:
            return [{"text": "A", "href": "https://x.test/a"}]
        return "<html><body><p>Hello there</p></body></html>"

    def screenshot(self):
        self.shots += 1
        return b"\x89PNG"


def t_the_visible_engine_behind_the_same_interface():
    fresh()
    page = FakePage()
    real = B._page_for
    B._page_for = lambda session, create=False: page
    try:
        v = E.VISIBLE
        with E.approved_run():
            v.open("https://x.test/")
            txt = v.text()
            links = v.links()
            png = v.screenshot()
            try:
                v.open("file:///etc/passwd")
                bad = False
            except E.EngineRefused:
                bad = True
    finally:
        B._page_for = real
    check("open goes through Playwright's goto with the shared timeout",
          page.went and page.went[0][0] == "https://x.test/" and page.went[0][1]["timeout"] == B._NAV_TIMEOUT_MS)
    check("text, links and a screenshot come back", "Hello there" in txt and links[0]["href"] == "https://x.test/a"
          and png.startswith(b"\x89PNG"))
    check("a file: address is never opened by the visible engine either", bad)
    check("hooks('visible') is None: browser_control's own Playwright code is unchanged", E.hooks("visible") is None)
    check("engine_for maps the names", E.engine_for("headless") is E.HEADLESS and E.engine_for("visible") is E.VISIBLE)
    check("the visible engine reports itself ready (its own rule is the second card)", E.VISIBLE.status()["ready"])


def t_wiring_the_gate_lines_the_fixtures_and_the_docs():
    import ast
    import _stack
    gate, log = _stack.stand_in("jarvis_gate.py")
    check("the gate stand-in builds from the whole patch stack", gate is not None, "\n".join(log))
    if gate is None:
        return
    check("browser-engine.patch applies cleanly to the stack (nothing of its context had to be invented)",
          not [l for l in log if "browser-engine" in l], [l for l in log if "browser-engine" in l])
    check("the action is on the 'a no is not a standing rule' list",
          re.search(r'^    "obscura_enable",\s+#', gate, re.M) is not None)
    m = re.search(r'^    "obscura_enable":\s*(\(.*\)),\s*$', gate, re.M)
    risk = ast.literal_eval(m.group(1)) if m else None
    check("its _RISK line says it leaves this PC ('outbound', a risky approval) and undoable",
          risk is not None and risk[0] == "yes" and risk[1] == "outbound", risk)
    if risk:
        low = risk[2].lower()
        check("... and its words say what matters: a program on this PC, ordinary Chrome, each step still a card, "
              "never types a password / solves a captcha, stops at a sign-in page it recognises, own network, "
              "instant off",
              all(w in low for w in ("no window", "ordinary chrome", "its own card", "never types a password",
                                     "solves a captcha", "sign-in", "recognises", "your own network", "instant"))
              and "never signs in" not in low, risk[2])
    hud, _ = _stack.stand_in("jarvis_hud.py")
    i = hud.index("jarvis_browser_engine.install(Handler")
    check("the install block sits after screen.patch's block and before the socket opens",
          hud.index("jarvis_screen.install(Handler") < i < hud.index("_loopback_companion(bind, HUD_PORT, Handler)"))
    check("... and hands install() the server's own origin and token checks",
          "origin_ok=_origin_ok" in hud[i:i + 300] and "token_ok=_token_ok" in hud[i:i + 300])
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("apply-patches.ps1 applies the patch last and ships both modules",
          ps1.index("'browser-engine.patch'") > ps1.index("'screen-picture.patch'")
          and "'jarvis_obscura.py'" in ps1 and "'jarvis_browser_engine.py'" in ps1)
    for mod in ("jarvis_obscura.py", "jarvis_browser_engine.py"):
        check(f"{mod} is in the shipped list", mod in SHIPPED)
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("the settings file ships the action at tier ask", re.search(r'^obscura_enable = "ask"', toml, re.M) is not None)
    import jarvis_asks_first as AF
    import jarvis_card_words as CW
    check("'What asks first' never lets it be loosened from an app and says it must stay 'ask'",
          "obscura_enable" in AF.HARD_LIMITS and "obscura_enable" in AF.MUST_ASK)
    check("the card's own words exist", bool(CW.TITLES.get("obscura_enable")))
    import jarvis_settings_registry as REG
    b = REG.find_bool_setting("the headless browser")
    check("'the headless browser' is a setting Jarvis can change when asked, through the same card",
          b is not None and b.key == "headless_browser" and b.section == "browser-engine")
    c = Card()
    real = (E._gate, E._tier, E._spawn)
    E._gate, E._tier, E._spawn = c.gate, (lambda a: "ask"), c.later.append
    try:
        REG.set_browser_engine(True)
    finally:
        E._gate, E._tier, E._spawn = real
    check("asking for ON by voice raises the SAME card and changes nothing yet",
          len(c.later) == 1 and E.settings()["obscura"] is False)
    check("asking for OFF is immediate", REG.set_browser_engine(False) is not None and E.settings()["obscura"] is False)
    check("the registry has the section", REG.section_by_id("browser-engine") is not None)


def t_both_apps_fixtures_are_current():
    sys.path.insert(0, str(REPO / "tools"))
    import gen_browser_cases as G
    want = G.document()
    for path in G.COPIES:
        check(f"{path.name} in {'desktop' if 'desktop' in str(path) else 'phone'} is current",
              path.exists() and path.read_text(encoding="utf-8") == want,
              "run python3 tools/gen_browser_cases.py")
    check("the two copies are byte-identical", G.DESKTOP.read_bytes() == G.PHONE.read_bytes())
    doc = json.loads(want)
    check("the words in the table are the module's own", doc["words"] == E.WORDS)


def t_what_jarvis_can_reach_says_which_browser():
    import jarvis_reach as RE

    def row(sc, eng, enabled=("browser_control",)):
        return RE._browser(RE.Ctx(enabled=set(enabled), second_card=sc, browser_engine=eng))
    no_card = {"master": False, "features": {}}
    card = {"master": True, "features": {"browser_control": True, "long_context": True}}
    r = row(no_card, {"enabled": True, "ready": True})
    check("headless on and ready, no second card: the row is on, and says plain reading only, with Obscura's name",
          r["state"] == "on" and "browser with no window (Obscura" in r["line"] and "plain reading only" in r["line"], r)
    check("... and that sign-in needs the visible browser, which needs the second card",
          "needs the visible browser" in r["line"] and "second graphics card" in r["line"])
    r = row(card, {"enabled": True, "ready": True})
    check("both browsers: the row says Jarvis picks per task and names which on the card",
          r["state"] == "on" and "picks for each task" in r["line"], r)
    r = row(card, {"enabled": False, "ready": False})
    check("only the visible browser: as it always said", r["state"] == "on" and "browser window you can see" in r["line"]
          and "headless" not in r["line"], r)
    r = row(no_card, {"enabled": True, "ready": False})
    check("headless on but not ready and no second card: off, naming both ways",
          r["state"] == "off" and "browser with no window (Obscura)" in r["line"], r)
    check("a tool not listed in [tools].enabled stays off whatever else is on",
          row(card, {"enabled": True, "ready": True}, enabled=())["state"] == "off")
    check("the tools list offers browser_control when headless is ready (no second card)",
          any(t["id"] == "browser_control" for t in RE.tools_offered(
              RE.Ctx(enabled={"browser_control"}, second_card=no_card,
                     browser_engine={"enabled": True, "ready": True}))))


# ==========================================================================
#   6. The review's findings (2026-09-29): switch, fence, limits, hidden text,
#      words, rule 1, fail-closed reads
# ==========================================================================

def clicks(log: Path) -> list:
    return [c for c in calls(log) if c["call"] == "browser_click"]


def starts(log: Path) -> list:
    try:
        return [json.loads(l) for l in log.read_text().splitlines() if '"start"' in l]
    except OSError:
        return []


def t_turning_the_switch_off_between_two_steps_stops_the_next_one():
    log = _TMP / "log-midoff.jsonl"
    d = rig(log=log)
    two = [{"action": "navigate", "value": "https://example.test/", "why": "one"},
           {"action": "navigate", "value": "https://example.test/about", "why": "two"}]
    p = B.plan("two pages", "s1", two, engine="headless", engine_why="x")
    seen = {"n": 0}

    def checkpoint():
        seen["n"] += 1
        if seen["n"] == 2:                       # just before step 2: the owner turns it off
            E.set_obscura(False)
        return None
    out = B.run(p, approved=True, checkpoint=checkpoint)
    check("switched off between the two steps: the run stops, in words, after the first",
          out["ok"] is False and len(out["done"]) == 1 and "switched off" in out["reason"].lower(), out)
    check("... the second navigate was never sent to any program",
          len([c for c in calls(log) if c["call"] == "browser_navigate"]) == 1)
    check("... and NO second program was started (the program the switch stopped stayed stopped)",
          len(starts(log)) == 1 and not d.alive(), len(starts(log)))
    try:
        d.call("browser_snapshot", {})
        check("even a direct call to the driver cannot start it while the switch is off", False)
    except OB.ObscuraError as exc:
        check("even a direct call to the driver cannot start it while the switch is off",
              exc.code == "switched_off" and len(starts(log)) == 1 and not d.alive(), exc.code)
    try:
        E.HEADLESS.read("s1")
        E.HEADLESS._call("browser_snapshot", {})
        check("every engine call re-checks the switch", False)
    except RuntimeError as exc:
        check("every engine call re-checks the switch", "switched off" in str(exc).lower(), str(exc))


def t_the_fence_cannot_be_walked_around():
    log = _TMP / "log-walk.jsonl"
    d = rig(log=log)
    run_plan("open", [{"action": "navigate", "value": "https://example.test/tricky", "why": "x"}],
             allowed=["example.test"])
    n0 = len(clicks(log))
    for label, name, role, words in (
        ("a link written /\\other.test/x (a backslash is a slash)", "Backslash", "link", "outside the allowed sites"),
        ("an address written https://other.test\\@example.test/", "Userinfo", "link", "outside the allowed sites"),
        ("an address with a name@host part", "At sign", "link", "name@"),
        ("a link made a button with role=button", "Pseudo button", "button", "outside the allowed sites"),
        ("a button with a formaction of its own", "Alt send", "button", "formaction"),
        ("a button that belongs to a form elsewhere (form=)", "Far away", "button", "form= box"),
    ):
        p, out = run_plan("try", [{"role": role, "name": name, "action": "click", "why": "x"}],
                          allowed=["example.test"])
        check(f"{label}: refused in words", out["ok"] is False and words in out["reason"], out)
        check(f"{label}: and the click was NEVER made", len(clicks(log)) == n0)
    p, out = run_plan("try", [{"role": "link", "name": "Spaced", "action": "click", "why": "x"}],
                      allowed=["example.test"])
    check("a plain link written with stray spaces and a tab is read as a browser reads it, and followed "
          "(the fence is not just refusing everything)", out["ok"] is True and len(clicks(log)) == n0 + 1, out)
    run_plan("open", [{"action": "navigate", "value": "https://example.test/tricky", "why": "x"}],
             allowed=["example.test"])
    p, out = run_plan("try", [{"role": "link", "name": "Empty", "action": "click", "why": "x"}],
                      allowed=["example.test"])
    check("a link with an empty address means this same page, which is inside the fence, and is followed",
          out["ok"] is True, out)
    # <base href>
    run_plan("open", [{"action": "navigate", "value": "https://example.test/based", "why": "x"}],
             allowed=["example.test"])
    n1 = len(clicks(log))
    p, out = run_plan("try", [{"role": "link", "name": "Docs", "action": "click", "why": "x"}],
                      allowed=["example.test"])
    check("a page's <base href> that turns /x into another site is honoured by the fence, and the click refused",
          out["ok"] is False and "https://other.test/x" in out["reason"] and len(clicks(log)) == n1, out)
    # the raw resolver and the address check, on their own
    for raw, base, ok in (("/\\evil.test/x", "https://good.test/", "evil.test"),
                          ("https://evil.test\\@good.test/", "https://good.test/", "evil.test"),
                          ("//evil.test/x", "https://good.test/", "evil.test"),
                          ("/about", "https://good.test/a/b", "good.test"),
                          ("\thttps://ev\nil.test/", "https://good.test/", "evil.test")):
        got = E._resolve_address(raw, base)
        check(f"a browser would read {raw!r} as going to {ok}", urllib_host(got) == ok, got)
    for raw in ("javascript:alert(1)", "data:text/html,x", "https://a@evil.test/", "https://\x01evil.test/"):
        try:
            E._resolve_address(raw, "https://good.test/")
            check(f"{raw!r} is refused", False)
        except RuntimeError:
            check(f"{raw!r} is refused", True)
    check("a navigate step's address with a backslash, a name@ part or a control character is refused at plan time",
          all(E.reject_request("headless", {"action": "navigate", "value": u})
              for u in ("https://evil.test\\@good.test/", "https://good.test@evil.test/",
                        "https://good.test/\x07")))
    check("... and an ordinary one is not", E.reject_request("headless",
          {"action": "navigate", "value": "https://good.test/a?b=c#d"}) is None)
    d.stop("t")


def t_a_redirect_or_a_page_that_moves_itself_is_stopped_but_only_after_the_load():
    log = _TMP / "log-redirect.jsonl"
    d = rig(log=log)
    p, out = run_plan("look", [{"action": "navigate", "value": "https://example.test/moved", "why": "x"}],
                      allowed=["example.test"])
    check("a redirect out of the fence is caught from the navigate's own reply, in words",
          out["ok"] is False and "sent the windowless browser on to https://other.test/x" in out["reason"]
          and "already been loaded" in out["reason"], out)
    check("... and the program was stopped, so nothing more can happen on that page", not d.alive())
    check("... the plain truth: the redirected-to page WAS fetched before it could be stopped "
          "(it is in the program's own record of what it loaded)",
          [c for c in calls(log) if c["call"] == "browser_navigate"][0]["args"]["url"]
          == "https://example.test/moved")
    d = rig(log=_TMP / "log-jumpy.jsonl")
    p, out = run_plan("look", [{"action": "navigate", "value": "https://example.test/jumpy", "why": "x"}],
                      allowed=["example.test"])
    check("a page that moves itself after loading (a meta refresh or a script) is seen at the look after "
          "the step and the run stops there",
          out["ok"] is False and "outside the allowed sites" in out["reason"] and len(out["done"]) == 1, out)
    check("... and the same words are on the card the owner approved", "only noticed after that page has "
          "loaded" in B.describe(p))
    d.stop("t")


def urllib_host(u):
    import urllib.parse
    return urllib.parse.urlsplit(u).hostname


def t_a_read_that_cannot_be_understood_refuses_the_click():
    for mode, req, words in (
        ("badforms", {"role": "button", "name": "Go", "action": "click", "why": "x"},
         "could not read the page's forms"),
        ("attrerror", {"role": "link", "name": "About us", "action": "click", "why": "x"},
         "could not read"),
    ):
        log = _TMP / f"log-bad-{mode}.jsonl"
        d = rig(mode, log=log)
        run_plan("open", [dict(NAV)])
        p, out = run_plan("try", [req])
        check(f"{mode}: a reply that is not understood refuses the click, in words",
              out["ok"] is False and words in out["reason"], out)
        check(f"{mode}: and no click was made", not clicks(log))
        d.stop("t")
    d = rig()
    real = sys.modules.get("jarvis_local_http")
    sys.modules["jarvis_local_http"] = None          # an import that fails
    try:
        why = E._private_problem("https://example.test/")
    finally:
        sys.modules["jarvis_local_http"] = real
    check("when the shared address check cannot be loaded, EVERY address is refused (not allowed)",
          why and "not available" in why, why)
    d.stop("t")


def t_no_fence_means_refuse_and_a_fence_belongs_to_one_run():
    log = _TMP / "log-nofence.jsonl"
    d = rig(log=log)
    run_plan("open", [dict(NAV)])
    check("after a run the fence is gone", E.HEADLESS._fence is None)
    n0 = len(clicks(log))
    with E.approved_run():
        for name, fn in (("click", lambda: E.HEADLESS.click("link", "About us")),
                         ("open", lambda: E.HEADLESS.open("https://example.test/about"))):
            try:
                fn()
                check(f"{name} with no fence is refused", False)
            except RuntimeError as exc:
                check(f"{name} with no fence is refused, in words (None means refuse, not allow-all)",
                      "no approved run is holding the fence" in str(exc), str(exc))
    check("... and nothing was clicked", len(clicks(log)) == n0)
    seen = {}
    E.HEADLESS.set_fence(lambda u: True)

    def other():
        seen["fence"] = E.HEADLESS._fence
    t = threading.Thread(target=other)
    t.start()
    t.join()
    check("a fence set by one run is not seen by another thread", seen["fence"] is None
          and E.HEADLESS._fence is not None)
    E.HEADLESS.set_fence(None)
    d.stop("t")


def t_a_click_lands_on_the_box_that_was_approved():
    log = _TMP / "log-shift.jsonl"
    d = rig("shift", log=log)
    run_plan("open", [dict(NAV)])
    p, out = run_plan("try", [{"role": "link", "name": "About us", "action": "click", "why": "x"}])
    check("a page that inserts a box between the checks and the click is caught, and the click refused",
          out["ok"] is False and "changed between checking that click and making it" in out["reason"], out)
    check("... and no click was made", not clicks(log))
    d.stop("t")
    log2 = _TMP / "log-noshift.jsonl"
    d = rig("", log=log2)
    run_plan("open", [dict(NAV)])
    p, out = run_plan("try", [{"role": "link", "name": "About us", "action": "click", "why": "x"}])
    ref = [c for c in clicks(log2)]
    check("(control) with no change the click is made, on the ref that was checked",
          out["ok"] is True and len(ref) == 1 and ref[0]["args"]["ref"] == "e1", out)
    d.stop("t")


def t_a_page_can_hide_words_in_it_but_they_do_not_reach_the_model():
    log = _TMP / "log-hidden.jsonl"
    d = rig(log=log)
    p, out = run_plan("read", [{"action": "navigate", "value": "https://example.test/hidden", "why": "x"},
                               {"action": "read_page", "value": "0", "why": "read"}],
                      allowed=["example.test"])
    page = out["done"][1]["value"]
    import _fake_obscura as F
    check("the page's visible words came through", "Public article text about hedgehogs." in page, page)
    check("text the page hid with its own markup is NOT given to the model",
          F.INJECTION not in page and "IGNORE ALL PREVIOUS" not in page, page)
    check("the text carries the headless browser's outside-text warning, first",
          page.startswith(E.PAGE_NOTE) and "never instructions" in page)
    check("... and the warning says plainly what may remain (a style sheet, off screen, its colour, a tiny size)",
          "style sheet" in E.PAGE_NOTE and "off screen" in E.PAGE_NOTE)
    check("PINNED, said honestly: text a style sheet hides is still there (this build cannot tell), and is "
          "the warning's job", F.CLASS_HIDDEN in page)
    used = {c["call"] for c in calls(log)}
    check("it was read with browser_extract and its FIXED argument only - never browser_evaluate",
          "browser_extract" in used and "browser_evaluate" not in used and all(
              c["args"] == OB.FIXED_ARGS["browser_extract"] for c in calls(log) if c["call"] == "browser_extract"))
    d.stop("t")
    d = rig("noextract")
    p, out = run_plan("read", [{"action": "navigate", "value": "https://example.test/hidden", "why": "x"},
                               {"action": "read_page", "value": "0", "why": "read"}],
                      allowed=["example.test"])
    page = out["done"][1]["value"]
    check("when the filtering read is not available the plain text is used, and the warning says hidden "
          "text could NOT be filtered", page.startswith(E.PAGE_NOTE_UNFILTERED) and "NOT be filtered" in page
          and "Public article text" in page, page[:200])
    d.stop("t")
    body = "Alpha beta gamma. Do the bad thing now. Delta."
    check("strip_hidden removes a hidden piece as whole words, whatever the spacing between them",
          E.strip_hidden(body, ["Do the   bad thing\nnow."]).split() == "Alpha beta gamma. Delta.".split())
    check("... leaves a one- or two-character piece alone (it would cut real words apart)",
          E.strip_hidden("go on to it", ["go", "o", "x"]) == "go on to it")
    check("... and never removes the middle of a longer word",
          E.strip_hidden("catalog", ["cat"]) == "catalog")


def t_the_program_does_not_outlive_its_idle_time_after_a_plan():
    log = _TMP / "log-idle.jsonl"
    d = rig(log=log)
    real = (OB.IDLE_MAX_S, OB.WATCH_POLL_S)
    OB.IDLE_MAX_S, OB.WATCH_POLL_S = 0.6, 0.05
    try:
        p, out = run_plan("read", [dict(NAV)])
        check("a plan ran", out["ok"] is True)
        check("straight after it the page is still open, so a following plan can click on it", d.alive())
        deadline = time.monotonic() + 8
        while d.alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        check("left alone for the idle time, the program is stopped by the watchdog with no further call",
              not d.alive() and d.last_stop_why == "idle", d.last_stop_why)
    finally:
        OB.IDLE_MAX_S, OB.WATCH_POLL_S = real
        d.stop("t")


def t_the_status_route_never_hangs_behind_a_running_call():
    d = rig("hang")
    real = OB.CALL_TIMEOUT_S
    OB.CALL_TIMEOUT_S = 30.0

    def call():
        try:
            d.call("browser_navigate", {"url": "https://example.test/"})
        except OB.ObscuraError:
            pass
    t = threading.Thread(target=call, daemon=True)
    t.start()
    try:
        deadline = time.monotonic() + 10
        while not d.alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        time.sleep(0.5)
        t0 = time.monotonic()
        code, v = E.handle_get()
        took = time.monotonic() - t0
        check("GET /api/browser/engine answers at once with a call hung on the program",
              code == 200 and took < 2.0 and v["lane"]["running"] is True, f"took {took:.1f}s")
    finally:
        d.stop("t")
        t.join(10)
        OB.CALL_TIMEOUT_S = real


def t_password_boxes_are_read_in_any_case():
    els = E.parse_elements('ref=e1    input[Password]        "Secret code"\n'
                           'ref=e2    input[PASSWORD]        ""\n'
                           'ref=e3    input[File]            "Attach"\n'
                           'ref=e4    INPUT[Hidden]          "h"\n'
                           'ref=e5    input[text]            ""\n')
    by = {e["ref"]: e for e in els}
    check("type=\"Password\" (capital) is a password box", by["e1"]["password"] and by["e1"]["sensitive"])
    check("an upper-case PASSWORD box with no label is kept (named as unnamed) and is a password",
          by["e2"]["password"] and by["e2"]["name"] == "(unnamed password box)")
    check("File and Hidden boxes in any case are sensitive", by["e3"]["sensitive"] and by["e4"]["sensitive"])
    check("a plain text box with no name is still dropped", "e5" not in by)
    check("role_for reads the type in lower case", E.role_for("input[Password]")[:3] == ("textbox", True, True)
          and E.role_for("INPUT[SUBMIT]")[0] == "button")
    d = rig()
    run_plan("open", [{"action": "navigate", "value": "https://example.test/pwcap", "why": "x"}])
    with E.approved_run():
        for name in ("Secret code", "Attach"):
            try:
                E.HEADLESS.fill("textbox", name, "abc")
                check(f"the engine will not type into {name!r}", False)
            except RuntimeError as exc:
                check(f"the engine will not type into {name!r}", "never types into a password" in str(exc), str(exc))
    d.stop("t")


def t_sign_in_wording_sends_a_task_to_the_visible_browser():
    rig()
    positives = [
        "sign into my bank", "log into the portal", "I was signed in earlier", "check my orders",
        "look at my passwords", "buy the book", "buying a ticket", "paid the bill", "pay for it",
        "read sign_in help", "sign-in page", "log in", "login", "my account page", "my accounts",
        "place an order", "order it now", "order history", "checkout", "checking out", "purchased",
        "iniciar sesión en mi cuenta", "contraseña", "comprar entradas", "mi cuenta",
        "anmelden", "einloggen bei", "mein Konto", "Passwort", "bezahlen", "bestellen",
        "se connecter", "mot de passe", "acheter un billet", "mon compte", "paiement", "mes commandes",
        "verify my email", "the verification code", "2FA", "one-time code", "sign up for the newsletter",
    ]
    for w in positives:
        check(f"the word test catches {w!r}", E._SIGN_WORDS.search(w) is not None)
    negatives = [
        "read the news about the order of the Roman emperors", "in order to read it", "what is a bank account",
        "design in Paris", "assign in the document", "the payroll report", "a design signature",
        "open the wikipedia page for hedgehogs", "read the weather forecast", "look up the opening hours",
        "an article about the account of the battle", "order of operations",
    ]
    for w in negatives:
        check(f"the word test leaves {w!r} alone", E._SIGN_WORDS.search(w) is None, w)
    # the "Headless" default no longer skips the words test (its help text says "not for a sign-in")
    E.set_mode("headless")
    r = E.choose(None, goal="sign into my bank and read my orders", requests=READ)
    check("a default of 'headless' with a sign-in task goes to the visible browser, and says why",
          r["engine"] == "visible" and "your setting is the windowless browser, but" in r["why"]
          and "sign in" in r["why"], r)
    check("... and a plain lookup with that default stays headless",
          E.choose(None, goal="read the news page", requests=READ)["engine"] == "headless")
    check("only an explicit mode 'headless' from the model skips the words test (its plan-time and "
          "run-time refusals still apply)",
          E.choose("headless", goal="buy the book", requests=READ)["engine"] == "headless")
    E.set_mode("auto")
    check("Automatic: 'my orders' goes visible", E.choose(None, goal="check my orders", requests=READ)["engine"]
          == "visible")
    check("Automatic: a plain lookup that says 'in order to' stays headless",
          E.choose(None, goal="find the page that explains in order to", requests=READ)["engine"] == "headless")
    check("the mode help no longer promises 'never for a sign-in' beyond what the test does",
          "never for a sign-in" not in E.WORDS["mode_help"]["headless"])


def t_pages_that_want_a_person_are_recognised():
    for title, body in (("Verifying you are human", ""), ("Example", "Enable JavaScript and cookies to continue"),
                        ("Pardon Our Interruption", ""), ("Just a moment...", ""),
                        ("Security check", ""), ("One more step", "Please complete the security check"),
                        ("Example", "Please wait while we verify your browser"),
                        ("Human verification", ""), ("Robot check", "")):
        check(f"{title!r} / {body[:30]!r} is a captcha-kind page", E.wants_a_person("https://a.test/", title, body) == "captcha")
    check("a page that only mentions 'security check' deep in its text is not one",
          E.wants_a_person("https://a.test/", "Airports", "x" * 300 + " the security check takes a while") == "")
    check("an article that mentions one more step in its middle is not one",
          E.wants_a_person("https://a.test/", "Recipe", "Mix the flour. " * 20 + "one more step: bake") == "")
    els = E.parse_elements('ref=e1    input[password]        ""\n')
    check("a bare password box (no label, no name) is kept, so it can tell a sign-in page",
          els and els[0]["password"] and E.wants_a_person("https://a.test/login", "Sign in", "", els) == "signin")
    email = E.parse_elements('ref=e1    input[email]           "Email or username" name="user"\n')
    check("an email-first sign-in (no password box yet) is recognised when the title says sign-in",
          E.wants_a_person("https://a.test/x", "Log in to Example", "", email) == "signin")
    check("... but a newsletter sign-UP page with an email box is not a sign-in",
          E.wants_a_person("https://a.test/newsletter", "Sign up for updates", "", email) == "")
    check("... nor an ordinary page with an email box", E.wants_a_person("https://a.test/contact", "Contact us", "",
                                                                          email) == "")
    for url, words in (("https://verifying.test/", "captcha"), ("https://cookies.test/", "captcha"),
                       ("https://example.test/login-first", "sign-in page"),
                       ("https://example.test/login-bare", "sign-in page")):
        d = rig()
        p, out = run_plan("read it", [{"action": "navigate", "value": url, "why": "x"}],
                          allowed=[urllib_host(url)])
        check(f"{url}: the run stops and hands over", out["ok"] is False and words in out["reason"]
              and "use the visible browser" in out["reason"], out)
        d.stop("t")


def t_a_big_page_is_counted_and_a_twin_past_the_cap_is_found():
    log = _TMP / "log-big.jsonl"
    d = rig(log=log)
    run_plan("open", [{"action": "navigate", "value": "https://big.test/", "why": "x"}], allowed=["big.test"])
    p = B.plan("click", "s1", [{"role": "link", "name": "Item 5", "action": "click", "why": "x"}],
               allowed_domains=["big.test"], engine="headless", engine_why="x")
    check("the plan says how many boxes and links it did not read (360 on the page, 300 read)", any(
        "more element(s) than Jarvis reads at once" in n and " 60 " in n for n in p.notices), p.notices)
    check("the click on 'Item 5' became a step (the first 300 hold one)", len(p.steps) == 1)
    out = B.run(p, approved=True)
    check("a box that appears twice, the twin past the plan's cap, is found at click time and the click refused",
          out["ok"] is False and "matches 2 elements" in out["reason"], out)
    check("... and no click was made", not clicks(log))
    d.stop("t")


class Verdict:
    def __init__(self, allowed, tier, outcome, reason=""):
        self.allowed, self.tier, self.outcome, self.reason = allowed, tier, outcome, reason
        self.action, self.request_id = "browser_control", None


def t_rule_1_typed_words_and_addresses():
    import jarvis_scrub
    token = "hunter2-Very-Secret-Value-9x"
    jarvis_scrub.register_secret(token)
    d = rig()
    run_plan("open", [dict(NAV)])
    cases = [
        ("a typed value with a labelled password", {"action": "type", "role": "textbox", "name": "Search",
                                                    "value": "password: hunter2xyz", "why": "x"}),
        ("a typed value that is a secret this PC holds", {"action": "type", "role": "textbox", "name": "Search",
                                                          "value": f"find {token}", "why": "x"}),
        ("a chosen value with a private key", {"action": "select", "role": "combobox", "name": "Colour",
                                               "value": "-----BEGIN PRIVATE KEY-----", "why": "x"}),
        ("a web address with a secret in its query", {"action": "navigate",
                                                       "value": f"https://example.test/search?q={token}", "why": "x"}),
        ("a web address with a secret in its path", {"action": "navigate",
                                                      "value": f"https://example.test/{token}", "why": "x"}),
        ("a web address with a secret in its fragment", {"action": "navigate",
                                                          "value": f"https://example.test/#{token}", "why": "x"}),
    ]
    for label, req in cases:
        p = B.plan("g", "s1", [req], engine="headless", engine_why="x")
        u = p.unmatched[0] if p.unmatched else {}
        card = B.describe(p)
        check(f"{label}: refused at plan time, before any card", not p.steps and u.get("reason")
              and "password, key or token" in u["reason"], u)
        check(f"{label}: its value is withheld and never on the card or in the plan",
              u.get("value") == "(withheld)" and token not in card and "hunter2xyz" not in card
              and token not in json.dumps(p.as_dict()) and "PRIVATE KEY" not in card, card[-400:])
    ok = B.plan("g", "s1", [{"action": "type", "role": "textbox", "name": "Search", "value": "hedgehogs",
                             "why": "x"},
                            {"action": "navigate", "value": "https://example.test/search?q=hedgehogs#top",
                             "why": "x"}], engine="headless", engine_why="x")
    check("(control) ordinary words in a box and an ordinary query are planned", len(ok.steps) == 2, ok.unmatched)
    with E.approved_run():
        for fn, label in ((lambda: E.HEADLESS.fill("textbox", "Search", "password: hunter2xyz"), "fill"),
                          (lambda: E.HEADLESS.select("combobox", "Colour", "password: hunter2xyz"), "select")):
            try:
                fn()
                check(f"the engine itself refuses a secret at run time ({label})", False)
            except RuntimeError as exc:
                check(f"the engine itself refuses a secret at run time ({label})", "password, key or token" in str(exc))
    # what repeats a saved fact (the half that needs this turn's facts)
    fact = "My home address is 14 Elm Road, Springfield"

    def steps_for(*reqs):
        return B.plan("g", "s1", list(reqs), engine="headless", engine_why="x").steps
    typed = steps_for({"action": "type", "role": "textbox", "name": "Search", "value": "14 Elm Road Springfield",
                       "why": "x"})
    why = E.private_words_problem(typed, facts=[fact])
    check("a typed value that repeats a saved fact is refused, in words, without repeating the fact",
          why and "repeat something you told Jarvis" in why and "Elm" not in why, why)
    query = steps_for({"action": "navigate", "value": "https://example.test/search?q=14+Elm+Road", "why": "x"})
    check("an address whose query repeats a saved fact is refused too",
          bool(E.private_words_problem(query, facts=[fact])))
    plain = steps_for({"action": "type", "role": "textbox", "name": "Search", "value": "hedgehogs", "why": "x"},
                      {"action": "navigate", "value": "https://example.test/about", "why": "x"})
    check("ordinary words and an address with no query are fine", E.private_words_problem(plain, facts=[fact]) == "")
    check("saved memories were recalled but the facts could not be read: refuse what it would type",
          "could not compare" in E.private_words_problem(typed, facts=[], memory=True))
    check("no memories in the turn: nothing to compare, fine", E.private_words_problem(typed, facts=[], memory=False) == "")
    check("a step that types nothing is fine even when memories were recalled",
          E.private_words_problem(steps_for(dict(NAV)), facts=[], memory=True) == "")
    real = sys.modules.get("jarvis_search")
    sys.modules["jarvis_search"] = None
    try:
        broken = E.private_words_problem(typed, facts=[fact])
    finally:
        sys.modules["jarvis_search"] = real
    check("when the comparison itself cannot run, it refuses (fails closed)", "could not be checked" in broken, broken)
    d.stop("t")
    # the agent's loop: the same refusal before any card, and the card line
    import jarvis_agent as A
    msgs = [{"role": "system", "content": "---FACTS---\n- [2026-09-20] " + fact + "\n---END FACTS---"},
            {"role": "user", "content": "look up hedgehog food"}]
    req = {"messages": [dict(msgs[1], provenance="typed")]}
    d = rig()
    for label, requests, wants_card in (
        ("a typed value repeating the saved address",
         [{"action": "navigate", "value": "https://example.test/", "why": "x"},
          {"action": "type", "role": "textbox", "name": "Search", "value": "14 Elm Road", "why": "x"}], False),
        ("a search that does not", [dict(NAV)], True),
    ):
        watch = A._TurnWatch(msgs, req, tainted=False)
        gates, convo, stp = [], [], []

        def gate(*a):
            gates.append(a)
            return Verdict(True, "ask", "approved")
        args = {"goal": "look it up", "session": "s1", "mode": "headless", "requests": requests}
        with_typed = any(r.get("action") == "type" for r in requests)
        if with_typed:
            # the type step needs the page: open it first, so the box exists
            run_plan("open", [dict(NAV)])
        A._one_call({"id": "1", "function": {"name": "browser_control", "arguments": json.dumps(args)}},
                    ["browser_control"], convo, stp, gate, None, A._Out(lambda b: None, sse=False),
                    lambda *a, **k: None, watch=watch)
        said = convo[-1]["content"] if convo else ""
        if with_typed:
            check(f"{label}: refused before any card, in words, without the fact",
                  not gates and "repeat something you told Jarvis" in said and "Elm" not in said, said)
        else:
            check(f"{label}: goes to a card as usual", bool(gates), said)
    # outside text shaped the turn and the plan types words: the card says so at the top
    d = rig()
    run_plan("open", [dict(NAV)])
    watch = A._TurnWatch([{"role": "user", "content": "look up hedgehog food"}],
                         {"messages": [{"role": "user", "content": "x", "provenance": "typed"}]}, tainted=True)
    gates, convo, stp = [], [], []
    args = {"goal": "look it up", "session": "s1", "mode": "headless",
            "requests": [{"action": "type", "role": "textbox", "name": "Search", "value": "hedgehogs", "why": "x"}]}

    def gate2(*a):
        gates.append(a)
        return Verdict(False, "ask", "denied")
    A._one_call({"id": "1", "function": {"name": "browser_control", "arguments": json.dumps(args)}},
                ["browser_control"], convo, stp, gate2, None, A._Out(lambda b: None, sse=False),
                lambda *a, **k: None, watch=watch)
    card = gates[0][1]["text"] if gates else ""
    check("after outside text, a plan that types words has the plain outside-text line at the top of its card",
          card.startswith(A.BROWSER_OUTSIDE_LINE), card[:200])
    d.stop("t")


def t_the_chatbot_files_import_nothing_of_the_engine():
    """No chatbot file may IMPORT the headless engine or the driver. (This used to grep for
    the plain text `jarvis_browser_engine`, which failed on a comment that only names the
    file; the intent is about imports, so it reads them.)"""
    import ast
    files = sorted(HERE.glob("jarvis_chatbot_*.py")) + [HERE / "jarvis_support_widget.py",
                                                         HERE / "jarvis_handoff.py"]
    bad = []
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            elif isinstance(node, ast.Call) and getattr(node.func, "id", "") == "__import__" and node.args \
                    and isinstance(node.args[0], ast.Constant):
                names = [str(node.args[0].value)]
            elif isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "import_module" and node.args \
                    and isinstance(node.args[0], ast.Constant):
                names = [str(node.args[0].value)]
            for n in names:
                if n.split(".")[0] in ("jarvis_browser_engine", "jarvis_obscura"):
                    bad.append((f.name, n))
    check("no chatbot, support or handoff file imports the engine or the driver (read as code, not text)",
          not bad and len(files) > 3, bad)
    probe = ast.parse("import jarvis_browser_engine as E\nx = 1  # jarvis_browser_engine in a comment\n")
    check("(the reader itself: a real import is seen, a comment is not)",
          sum(isinstance(n, ast.Import) for n in ast.walk(probe)) == 1)


def t_the_words_are_soft_where_the_code_is():
    src = " ".join([E.WORDS["stealth"], E.describe_on(), E.HANDOVER, E.card_line("headless", "x")]).lower()
    check("nowhere does it promise 'never signs in': the code stops at a sign-in page it recognises",
          "never signs in" not in src and "never types a password" in src and "recognise" in src, src[:300])
    check("the card says a redirect or a page that moves itself is noticed only after it loaded",
          "after that page has loaded" in E.card_line("headless", "x") or "after it has loaded" in E.describe_on())
    check("the card says the program is stopped after 3 idle minutes and 10 in all, not 'a few minutes'",
          "3 idle minutes" in E.describe_on() and "10 minutes in all" in E.describe_on()
          and "a few minutes" not in E.describe_on())
    check("the stand-in visible-browser wording: the headless browser has stealth, the visible one is a plain real "
          "browser (in the chatbot file's own words)",
          "headless browser runs with stealth on" in (HERE / "jarvis_chatbot_web.py").read_text()
          and "visible browser is a plain real browser" in (HERE / "jarvis_chatbot_web.py").read_text())
    check("the mode help says what the test really does", "looks like a sign-in" in E.WORDS["mode_help"]["headless"])
    check("the install note says nothing is run before the owner has compared the checksums",
          "does not run the program" in E.WORDS["steps_note"] and "compare" in E.WORDS["steps_note"])


def t_the_docs_say_it():
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    check("JARVIS-API section 97 exists and names the route, the action and what was not verified",
          "## 97. The headless browser" in api and "/api/browser/engine" in api and "obscura_enable" in api
          and "NOT verified" in api and "PINNED_DIGEST" in api)
    arch = (REPO / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    check("ARCHITECTURE section 4 names it as a way out of the PC, with what it gets and what stops it",
          "**the headless browser, Obscura**" in arch and "obscura_enable" in arch)
    check("ARCHITECTURE section 8 says why the chatbot driver keeps the visible browser",
          "headless browser" in arch.lower() and "chatbot driver" in arch.split("One-sided on purpose")[1].lower())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
            finally:
                try:
                    E.HEADLESS.driver.stop("test")
                except Exception:
                    pass
                OB.child_env = _REAL_CHILD_ENV
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
