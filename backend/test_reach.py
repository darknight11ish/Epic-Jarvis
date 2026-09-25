"""test_reach.py - "What Jarvis can reach", written by code from the PC's
settings, never by the model (the Muse audit, idea 1).

    python3 backend/test_reach.py

What it proves:
  - every way out is a row, in KINDS order, each with on/off, where it goes
    (a host only), whether it asks first and one plain line;
  - NO SECRET reaches the list, the spoken answer or the route: fake
    passwords, keys, tokens, a private calendar link and an ntfy topic
    (built by concatenation) are set, and none of them appears;
  - "asks first" follows the real rules: the six tools that only run on a
    person's yes say "every time" whatever the tier; "never" is "blocked";
    note writes say they ask after outside text; web search says when it
    asks;
  - the tools offered are jarvis_agent.offered_tools()'s list;
  - it only reads: no socket, no file written, the second card is not
    woken or probed;
  - sending email is a row of its own ("not set up"), one KINDS entry;
  - "what can you reach?" and close phrasings are answered by
    jarvis_quick.py from the same list, without the model; near misses and
    pasted text go to the model;
  - reach.patch applies to what the earlier patches wrote, reverses, checks
    the origin and the token, and its block runs;
  - both apps carry the PC's words for the parts of the screen.
No network, no model.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import traceback
import types
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-reach-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
(_TMP / "config").mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_reach.py", "jarvis_quick.py", "jarvis_agent.py", "jarvis_search.py",
                "jarvis_second_card.py", "jarvis_big_model.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_reach as R  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import _stack  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# Fake secrets, built by concatenation so nothing here is shaped like a real one.
FAKE_PASSWORD = "hunter" + "2-" + "fake-mail-pw"
FAKE_ICS = ("https://calendar.google.com/calendar/ical/me%40example.com/private-"
            + "0123abcd" + "4567ef89" + "0123abcd" + "4567ef89" + "/basic.ics")
FAKE_CALDAV = "https://owner:" + "caldav-" + "fake-pw" + "@dav.example.org/cal/me/"
FAKE_TOPIC = "jarvis-" + "topic-" + "q8w7e6r5"
FAKE_HOME = "eyJ" + "hbGciOi" + "fakehometoken0123"
FAKE_GITHUB = "gh" + "p_" + "fake" + "0123456789abcdef0123456789abcd"
FAKE_JOPLIN = "jop" + "lin" + "fake0123456789"
FAKE_OBSIDIAN = "obs" + "idian-" + "fake-key-0123"
FAKE_TAVILY = "tv" + "ly-" + "fake" + "0123456789ab"
SECRETS = (FAKE_PASSWORD, "private-0123abcd", "0123abcd4567ef89", FAKE_TOPIC, FAKE_HOME,
           FAKE_GITHUB, FAKE_JOPLIN, FAKE_OBSIDIAN, FAKE_TAVILY, "caldav-fake-pw", "owner:")

ENV = {
    "JARVIS_IMAP_HOST": "imap.example.com", "JARVIS_IMAP_USER": "me@example.com",
    "JARVIS_IMAP_PASSWORD": FAKE_PASSWORD,
    "JARVIS_CALENDAR_ICS_SECRET_URL": FAKE_ICS, "JARVIS_CALDAV_URL": FAKE_CALDAV,
    "JARVIS_CALDAV_PASSWORD": FAKE_PASSWORD,
    "JARVIS_HOME_URL": "http://homeassistant.local:8123/api", "JARVIS_HOME_TOKEN": FAKE_HOME,
    "JARVIS_NTFY_TOPIC": FAKE_TOPIC, "JARVIS_GITHUB_TOKEN": FAKE_GITHUB,
    "JARVIS_JOPLIN_TOKEN": FAKE_JOPLIN, "JARVIS_OBSIDIAN_API_KEY": FAKE_OBSIDIAN,
}


class Env:
    def __init__(self, values):
        self.values, self.saved = values, {}

    def __enter__(self):
        for k, v in self.values.items():
            self.saved[k] = os.environ.get(k)
            os.environ[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def ctx(enabled=(), tiers=None, **kw):
    tiers = tiers or {}
    base = dict(enabled=set(enabled), tier=lambda a: tiers.get(a, "auto"),
                env=lambda n: str(os.environ.get(n, "") or "").strip(),
                lanes=[], providers=[],
                search={"provider": "searxng", "searxng_url": "http://127.0.0.1:8888",
                        "ask_every_time": False, "why": ""},
                key_saved=lambda p: None, second_card={"master": False, "features": {}},
                big_model={"master": False}, gate_action=lambda lookup: None)
    base.update(kw)
    return R.Ctx(**base)


ALL = set(R.TOOL_NAMES)


def row(v, id_):
    return next(r for r in v["rows"] if r["id"] == id_)


def t_rows_and_order():
    v = R.view(ctx())
    check("one row per way out, in KINDS order", [r["id"] for r in v["rows"]]
          == [k for k, _ in R.KINDS])
    need = {"id", "name", "state", "on", "state_words", "where", "asks", "line"}
    check("every row has on/off, where, asks and a line",
          all(need <= set(r) and r["line"] and r["state"] in R.STATE_WORDS for r in v["rows"]))
    ids = {k for k, _ in R.KINDS}
    for want in ("cloud_model", "web_search", "calendar", "email_read", "email_send",
                 "home_read", "home_control", "notes_read", "notes_write", "github",
                 "phone_push", "computer", "browser", "phone_control", "second_card",
                 "big_model"):
        check(f"there is a row for {want}", want in ids)
    check("with nothing set up, nothing is on", v["on"] == 0 and v["tools"] == [], v["on"])
    check("the view says it was written by code", v["written_by"] == "code"
          and v["title"] == R.TITLE and v["detail"] == R.DETAIL)


def t_no_secret_anywhere():
    with Env(ENV):
        c = ctx(ALL, lanes=["jarvis-escalate"], providers=["openrouter"],
                search={"provider": "tavily", "searxng_url": "http://127.0.0.1:8888",
                        "ask_every_time": False, "why": ""}, key_saved=lambda p: True)
        v = R.view(c)
        text = json.dumps(v) + R.sentence(v)
        leaked = [s for s in SECRETS if s in text]
        check("no password, key, token, private link or topic in the list or the answer",
              not leaked, leaked)
        check("the calendar's private link: its host only",
              row(v, "calendar")["where"] == "calendar.google.com", row(v, "calendar"))
        check("the email: host and user only", row(v, "email_read")["where"]
              == "imap.example.com (as me@example.com)")
        check("a key: saved yes/no only", "A key is saved on this PC." in row(v, "web_search")["line"])
        check("ntfy: the server's host, never the topic", row(v, "phone_push")["where"] == "ntfy.sh")
        check("Home Assistant: host only", row(v, "home_read")["where"] == "homeassistant.local")
        check("GitHub: a token is 'saved', never shown", "token is saved" in row(v, "github")["line"])
    with Env(dict(ENV, JARVIS_CALENDAR_ICS_SECRET_URL="")):
        v = R.view(ctx(ALL))
        check("a CalDAV address with a password in it: host only",
              row(v, "calendar")["where"] == "dav.example.org", row(v, "calendar"))
        check("... nothing of the password", "caldav-fake-pw" not in json.dumps(v))
    # The real jarvis_search key check, with a fake Credential Manager.
    import jarvis_search as WS

    class Store:
        def __init__(self, target):
            self.target = target

        def read(self):
            return FAKE_TAVILY
    saved = WS._STORE_FACTORY
    WS._STORE_FACTORY = Store
    try:
        v = R.view(ctx({"web_search"}, key_saved=None, search={
            "provider": "tavily", "searxng_url": "http://127.0.0.1:8888",
            "ask_every_time": False, "why": ""}))
    finally:
        WS._STORE_FACTORY = saved
    check("with a real key check: 'saved', and the key nowhere",
          FAKE_TAVILY not in json.dumps(v) and "A key is saved" in row(v, "web_search")["line"])


def t_asks_follows_the_rules():
    with Env(ENV):
        v = R.view(ctx(ALL, second_card={"master": True, "features": {
            "long_context": True, "browser_control": True}}))
    for id_ in ("computer", "phone_control", "shell", "home_control", "github", "browser"):
        check(f"{id_}: every time, even at tier auto (a person's yes only)",
              row(v, id_)["asks"] == R.ASK_EVERY, row(v, id_))
    check("a read at tier auto does not ask", row(v, "email_read")["asks"] == R.ASK_NO)
    check("note writes: no, but yes after outside text",
          row(v, "notes_write")["asks"].startswith("No - but yes after"))
    with Env(ENV):
        v = R.view(ctx(ALL, tiers={"email_read": "never", "calendar_read": "notify",
                                   "control_computer": "never"}))
    check("a tier of never: blocked, and says so", row(v, "email_read")["state"] == "blocked"
          and not row(v, "email_read")["on"])
    check("... also for a tool that needs a person", row(v, "computer")["state"] == "blocked")
    check("notify: told afterwards", row(v, "calendar")["asks"] == R.ASK_TOLD)
    s = ctx({"web_search"}, search={"provider": "searxng", "searxng_url": "http://127.0.0.1:8888",
                                    "ask_every_time": True, "why": ""})
    check("web search with 'Ask before every web search': every search",
          row(R.view(s), "web_search")["asks"].startswith("Yes, every search"))
    check("web search by default: only when private things could slip in",
          row(R.view(ctx({"web_search"})), "web_search")["asks"].startswith("Only when private"))
    check("SearXNG on this PC says so", row(R.view(ctx({"web_search"})), "web_search")["where"]
          .startswith("this PC (SearXNG"))
    v = R.view(ctx({"web_search"}, search={"provider": None, "searxng_url": "x",
                                           "ask_every_time": True, "why": "damaged"}))
    check("a damaged search settings file: blocked", row(v, "web_search")["state"] == "blocked")
    check("the cloud lane, when there is one, asks every question",
          row(R.view(ctx(lanes=["jarvis-escalate"])), "cloud_model")["asks"]
          == "Yes, every question")
    check("the gate's own action table is used when it is there",
          R.action_of("email_check", ctx(gate_action=lambda lk: "mine")) == "mine"
          and R.action_of("email_check", ctx()) == "email_read")


def t_tools_are_the_tool_loops_own_list():
    for enabled in (set(), {"calculator", "web_search"}, ALL - {"browser_control"},
                    {"not_a_tool", "email_check"}):
        got = [t["id"] for t in R.view(ctx(enabled))["tools"]]
        check(f"tools offered = jarvis_agent.offered_tools({sorted(enabled)[:3]}...)",
              got == AG.offered_tools(enabled), got)
    got = [t["id"] for t in R.view(ctx({"browser_control"}))["tools"]]
    check("browser control is not listed while the second card's switch is off", got == [])
    got = [t["id"] for t in R.view(ctx({"browser_control"}, second_card={
        "master": True, "features": {"long_context": True, "browser_control": True}}))["tools"]]
    check("... and is, when it is on", got == ["browser_control"])
    check("every tool has a plain name", all(n in R.TOOL_NAMES for n in AG.TOOLS),
          [n for n in AG.TOOLS if n not in R.TOOL_NAMES])


class NoSockets:
    def __enter__(self):
        self.tried = []
        self.saved = socket.socket.connect

        def refuse(sock, addr):
            self.tried.append(addr)
            raise OSError("no sockets in this test")
        socket.socket.connect = refuse
        return self

    def __exit__(self, *a):
        socket.socket.connect = self.saved


def t_it_only_reads():
    import jarvis_second_card as SC
    import jarvis_big_model as BM
    called = []
    saved = (SC.lane_for, SC.wake, SC.detect, BM.detect)
    SC.lane_for = lambda *a, **k: called.append("lane_for")
    SC.wake = lambda *a, **k: called.append("wake")
    SC.detect = lambda *a, **k: called.append("detect") or {}
    BM.detect = lambda *a, **k: called.append("bm.detect") or {}
    before = sorted(p.name for p in (_TMP / "config").rglob("*"))
    try:
        with Env(ENV), NoSockets() as ns:
            v = R.view(R.Ctx(enabled=ALL))
            s = R.sentence(v)
    finally:
        SC.lane_for, SC.wake, SC.detect, BM.detect = saved
    after = sorted(p.name for p in (_TMP / "config").rglob("*"))
    check("no socket is opened", not ns.tried, ns.tried)
    check("the second card and the big model are not woken or probed", not called, called)
    check("no file is written", before == after, (before, after))
    check("the default reading (the real settings) works", len(v["rows"]) == len(R.KINDS) and s)


def t_sending_email_is_one_entry():
    r = row(R.view(ctx()), "email_send")
    check("sending email: its own row, not set up without an email account",
          r["state"] == "not_set_up" and "sending" in r["line"])
    env = {"JARVIS_IMAP_HOST": "imap.example.com", "JARVIS_IMAP_USER": "me@example.com",
           "JARVIS_IMAP_PASSWORD": "pw" + "-for-the-test"}
    on = row(R.view(ctx({"send_email"}, env=lambda n: env.get(n, ""))), "email_send")
    check("... and on, through smtp.example.com, when the account is set up and "
          "send_email is offered", on["state"] == "on" and "smtp.example.com" in on["where"]
          and ("pw" + "-for-the-test") not in json.dumps(on), on)
    saved = R.KINDS
    try:
        R.KINDS = tuple((k, (lambda c: R._row("email_send", "Email (sending)", "on",
                                              "smtp.example.com", R.ASK_EVERY, "Sends.")))
                        if k == "email_send" else (k, f) for k, f in saved)
        check("replacing one entry changes that row only",
              row(R.view(ctx()), "email_send")["where"] == "smtp.example.com")
    finally:
        R.KINDS = saved


def t_never_raises():
    saved = R.KINDS
    try:
        R.KINDS = saved + (("broken", lambda c: 1 / 0),)
        v = R.view(ctx())
        check("a row that cannot be read says so, and the rest still show",
              row(v, "broken")["line"].startswith("Could not be read")
              and len(v["rows"]) == len(saved) + 1)
    finally:
        R.KINDS = saved


def t_cloud_lanes_are_the_servers_own():
    fake = types.ModuleType("jarvis_hud")
    fake._lane_names = lambda: ["jarvis-escalate", "jarvis-bulk"]
    sys.modules["jarvis_hud"] = fake
    try:
        r = row(R.view(ctx(lanes=None)), "cloud_model")
    finally:
        sys.modules.pop("jarvis_hud", None)
    check("inside the server: _lane_names(), the chat route's own list",
          r["on"] and "jarvis-escalate, jarvis-bulk" in r["line"], r)
    (_TMP / "config" / "litellm-proxy.yaml").write_text(
        "model_list:\n  - model_name: jarvis-critic\n    litellm_params:\n"
        "      model: openrouter/some-model\n      api_key: os.environ/OPENROUTER_API_KEY\n",
        encoding="utf-8")
    try:
        r = row(R.view(ctx(lanes=None, providers=None)), "cloud_model")
    finally:
        (_TMP / "config" / "litellm-proxy.yaml").unlink()
    check("outside it: the same file, read for names and providers only",
          r["on"] and "jarvis-critic" in r["line"] and r["where"] == "openrouter"
          and "OPENROUTER_API_KEY" not in json.dumps(r), r)


class _Sched:
    def mark_command(self, text):
        pass


def t_the_quick_answer():
    said = ("What can you reach?", "what can Jarvis access", "Jarvis, what do you have access to right now?",
            "what are you connected to", "which services can you access", "show me what you can reach",
            "what has Jarvis got access to", "what can you access right now",
            "what can you reach outside this pc", "list what jarvis has access to")
    for s in said:
        i = Q.match(s)
        check(f"{s!r} is answered without the model", i is not None and i.name == "reach_list")
    for s in ("what can you reach on the top shelf", "can you reach the shelf", "what can I access",
              "what is access control", "how do I access my email", "what do I have access to",
              "what can you do"):
        i = Q.match(s)
        check(f"{s!r} goes to the model", i is None or i.name != "reach_list")
    with Env(ENV):
        r = Q.answer("what can you reach?", sched=_Sched())
        want = R.sentence()
    check("the answer is the list's own sentence", r is not None and r.reply == want, r and r.reply)
    check("... with no secret in it", not [s for s in SECRETS if s in r.reply])
    check("... and no account name (host names only)", "me@example.com" not in r.reply)
    body = {"messages": [{"role": "user", "content": "what can you reach?",
                          "provenance": "pasted"}]}
    check("pasted text goes to the model", Q.answer_turn(body, sched=_Sched()) is None)
    saved = sys.modules.get("jarvis_reach")
    sys.modules["jarvis_reach"] = None
    try:
        r = Q.answer("what can you reach?", sched=_Sched())
    finally:
        sys.modules["jarvis_reach"] = saved
    check("without jarvis_reach.py it says to run apply-patches.ps1",
          r is not None and r.reply == Q.REACH_MISSING)


def _rehearse():
    order = _stack.order()
    if "reach.patch" not in order:
        return False, "reach.patch is not in apply-patches.ps1's list", ""
    before = order[:order.index("reach.patch")]
    patch = (HERE / "reach.patch").read_text(encoding="utf-8")
    text, log = _stack.stand_in("jarvis_hud.py", before)
    if text is None:
        return False, "; ".join(log), ""
    git = shutil.which("git")
    d = Path(tempfile.mkdtemp(prefix="jarvis-reach-patch-"))
    try:
        (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
        (d / "p.patch").write_text(patch, encoding="utf-8", newline="\n")
        r = subprocess.run([git, "apply", "p.patch"], cwd=d, capture_output=True, text=True)
        if r.returncode != 0:
            return False, r.stderr, ""
        after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        r = subprocess.run([git, "apply", "-R", "p.patch"], cwd=d, capture_output=True, text=True)
        if r.returncode != 0 or (d / "jarvis_hud.py").read_text(encoding="utf-8") != text:
            return False, "does not reverse cleanly: " + r.stderr, ""
        return True, "", after
    finally:
        shutil.rmtree(d, ignore_errors=True)


class _Handler:
    def __init__(self):
        self.sent = None

    def _send(self, code, out):
        self.sent = (code, out)
        return self.sent


def t_the_patch():
    if not shutil.which("git"):
        return check("SKIP - git is not installed", True)
    ok, why, hud = _rehearse()
    check("reach.patch applies to what the earlier patches wrote, and reverses", ok, why)
    if not ok:
        return
    i = hud.index('        if path == "/api/reach":')
    blk = hud[i:hud.index('        if path == "/api/schedule":', i)]
    check("GET /api/reach checks origin and token", "_origin_ok(self)" in blk
          and "_token_ok(self)" in blk)
    check("... and touches nothing else (the only file it patches is jarvis_hud.py)",
          (HERE / "reach.patch").read_text(encoding="utf-8").count("+++ b/") == 1)
    ns = {}
    exec(compile("def f(self, path, _origin_ok, _token_ok):\n" + blk, "<GET>", "exec"), ns)
    h = _Handler()
    with Env(ENV):
        ns["f"](h, "/api/reach", lambda s: True, lambda s: True)
    check("GET runs and answers the list", h.sent[0] == 200
          and [r["id"] for r in h.sent[1]["rows"]] == [k for k, _ in R.KINDS], h.sent)
    check("... with no secret in it", not [s for s in SECRETS if s in json.dumps(h.sent[1])])
    ns["f"](h, "/api/reach", lambda s: True, lambda s: False)
    check("... 401 without the token", h.sent[0] == 401)
    ns["f"](h, "/api/reach", lambda s: False, lambda s: True)
    check("... 403 from another origin", h.sent[0] == 403)
    saved = sys.modules.get("jarvis_reach")
    sys.modules["jarvis_reach"] = None
    try:
        ns["f"](h, "/api/reach", lambda s: True, lambda s: True)
    finally:
        sys.modules["jarvis_reach"] = saved
    check("... 503 available:false without jarvis_reach.py", h.sent[0] == 503
          and h.sent[1]["available"] is False)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    # The one real dependency: its context is web-search's GET block.
    check("apply-patches.ps1 applies reach.patch after web-search.patch",
          names.index("web-search.patch") < names.index("reach.patch"))


def _const(src: str, name: str) -> str:
    """A string constant from JavaScript or Kotlin source, with `+`-joined
    pieces put together."""
    m = re.search(name + r"\s*=\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+)", src)
    if not m:
        return ""
    return "".join(json.loads(f'"{p}"') for p in re.findall(r"\"((?:[^\"\\]|\\.)*)\"",
                                                             m.group(1))).replace("\\$", "$")


def t_both_apps_say_the_same_words():
    js = (REPO / "jarvis-desktop" / "src" / "reach.js").read_text(encoding="utf-8")
    kt = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" /
          "client" / "net" / "Reach.kt").read_text(encoding="utf-8")
    for name, want in (("TITLE", R.TITLE), ("DETAIL", R.DETAIL), ("MISSING", R.MISSING),
                       ("TOOLS_TITLE", R.TOOLS_TITLE), ("TOOLS_NONE", R.TOOLS_NONE),
                       ("EVERYTHING_ELSE", R.EVERYTHING_ELSE)):
        check(f"desktop {name} is the PC's words", _const(js, name) == want, _const(js, name))
        check(f"phone {name} is the PC's words", _const(kt, name) == want, _const(kt, name))


if __name__ == "__main__":
    for fn in (t_rows_and_order, t_no_secret_anywhere, t_asks_follows_the_rules,
               t_tools_are_the_tool_loops_own_list, t_it_only_reads, t_sending_email_is_one_entry,
               t_never_raises, t_cloud_lanes_are_the_servers_own, t_the_quick_answer,
               t_the_patch, t_both_apps_say_the_same_words):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
