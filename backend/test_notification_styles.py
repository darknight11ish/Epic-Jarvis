"""test_notification_styles.py - "Notification styles you describe"
(jarvis_notification_styles.py; the owner's ask of 2026-10-30; docs/JARVIS-API.md
section 167).

    python -B backend/test_notification_styles.py

Runs anywhere; no model, no network (the model is a stand-in). What it proves:

1. A style on the menu is kept and cleaned; ANYTHING off the menu - an unknown
   key (a colour value, a font, a layout, an image, a URL, code, an onclick),
   an unknown theme/figure/motion/speed/kind, a missing key, a web address in
   the name, a repeated key, NaN, prose around the JSON, a far too long answer
   - is refused, with a reason, and nothing is made.
2. The spec has nowhere to put private data: the six keys are the whole
   vocabulary, and a `kinds` value is two words at most.
3. A draft is made only from the owner's own typed or spoken words: pasted
   words and a tainted chat are refused; no model, or a model answer off the
   menu, makes nothing. The prompt holds the owner's words and the menu only.
4. The store: Add keeps the draft EXACTLY as previewed, drafts expire and are
   capped, styles are capped, Delete is immediate, and a hand-edited file is
   checked again on every read.
5. Which style is LIVE for each kind is the newest one that claims it - the
   same answer on every device, every time.
6. Chat: "make my notifications look like ..." makes a PREVIEW only, is
   refused in a tainted chat, and reuses jarvis_widgets' taint rule.
7. The routes: behind the token and origin checks, a body size cap, switched
   on by jarvis_brain_reads.install(), and every other route passes through.
8. Nothing here can approve, deny, open a URL or carry a token.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_notification_styles.py", "jarvis_quick.py", "jarvis_brain_reads.py",
                "jarvis_widgets.py")
TMP = Path(tempfile.mkdtemp(prefix="jarvis-notifstyles-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_NOTIFICATION_STYLES_FILE"] = str(TMP / "notification_styles.json")
sys.path.append(str(HERE / "rebuilt"))
import jarvis_notification_styles as N  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_widgets as W  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def refused(obj) -> str:
    try:
        N.validate(obj)
    except N.Refused as exc:
        return str(exc) or "refused"
    return ""


def refused_raw(raw) -> str:
    try:
        N.parse_model(raw)
    except N.Refused as exc:
        return str(exc) or "refused"
    return ""


GOOD = {"name": "Ember pulse", "theme": "ember", "figure": "spark",
        "motion": "pulse", "speed": "normal", "kinds": ["approval", "reminder"]}


def fresh_store(clock=None) -> N.Store:
    """A fresh FOLDER per store, from tempfile.mkdtemp - never a shared file
    (jarvis_widgets' test explains why: two stores in one test must not see
    each other)."""
    folder = Path(tempfile.mkdtemp(dir=str(TMP)))
    return N.Store(path=folder / "notification_styles.json", clock=clock or __import__("time").time)


def fake_ask(answer):
    seen = []

    def ask(text):
        seen.append(text)
        return answer
    ask.seen = seen
    return ask


# ================================================== 1. the menu

def t_on_the_menu_is_kept():
    got = N.validate(GOOD)
    check("a style on the menu is kept, key for key",
          got == {"name": "Ember pulse", "theme": "ember", "figure": "spark",
                  "motion": "pulse", "speed": "normal", "kinds": ["approval", "reminder"]}, got)
    dup = dict(GOOD, kinds=["approval", "approval", "reminder"])
    check("a kind named twice is one kind", N.validate(dup)["kinds"] == ["approval", "reminder"])
    oner = dict(GOOD, kinds=["reminder"])
    check("a style for one kind is a style", N.validate(oner)["kinds"] == ["reminder"])
    every = dict(GOOD, kinds=list(N.KINDS))
    check("both kinds named together are both kept", N.validate(every)["kinds"] == ["approval", "reminder"])
    named = dict(GOOD, name="  Red   panda\t\tpulse  ")
    check("the name is cleaned to plain words", N.validate(named)["name"] == "Red panda pulse")
    long = dict(GOOD, name="x" * 80)
    check("a name is cut to its cap", len(N.validate(long)["name"]) == N.MAX_NAME)
    for t in ("ice", "azure", "indigo", "ember", "rose", "mono"):
        check(f"the theme {t} is on the menu", N.validate(dict(GOOD, theme=t))["theme"] == t)
    for f in N.FIGURES:
        check(f"the figure {f} is on the menu", N.validate(dict(GOOD, figure=f))["figure"] == f)
    for m in N.MOTIONS:
        check(f"the motion {m} is on the menu", N.validate(dict(GOOD, motion=m))["motion"] == m)
    for s in N.SPEEDS:
        check(f"the speed {s} is on the menu", N.validate(dict(GOOD, speed=s))["speed"] == s)


def t_off_the_menu_is_refused():
    bad = [
        ("an unknown key", dict(GOOD, html="<b>hi</b>")),
        ("a colour value", dict(GOOD, colour="#ff0000")),
        ("a font", dict(GOOD, font="Comic Sans")),
        ("a layout", dict(GOOD, layout="res/layout/x.xml")),
        ("an image", dict(GOOD, image="file:///sdcard/x.png")),
        ("an onclick", dict(GOOD, onclick="approve()")),
        ("code", dict(GOOD, code="doIt()")),
        ("a sound", dict(GOOD, sound="alarm.mp3")),
        ("a web address key", dict(GOOD, url="https://example.com")),
        ("a style type of its own", dict(GOOD, theme="rainbow")),
        ("an unknown figure", dict(GOOD, figure="dragon")),
        ("an unknown motion", dict(GOOD, motion="lottie")),
        ("an unknown speed", dict(GOOD, speed="instant")),
        ("an unknown kind", dict(GOOD, kinds=["chatbot"])),
        ("a kind that is not text", dict(GOOD, kinds=[1])),
        ("no kinds at all", dict(GOOD, kinds=[])),
        ("kinds is not a list", dict(GOOD, kinds="approval")),
        ("a missing theme", {k: v for k, v in GOOD.items() if k != "theme"}),
        ("a missing name", {k: v for k, v in GOOD.items() if k != "name"}),
        ("a name of nothing but spaces", dict(GOOD, name="   ")),
        ("a web address as the name", dict(GOOD, name="see example.com/x")),
        ("a name that is not text", dict(GOOD, name=5)),
        ("a theme that is not text", dict(GOOD, theme=["ember"])),
        ("not a style at all", ["ember"]),
    ]
    for why, obj in bad:
        got = refused(obj)
        check(f"refused: {why}", bool(got), obj)


def t_text_is_cleaned():
    check("control characters leave the name",
          N.validate(dict(GOOD, name="a\u0000b\u202ec"))["name"] == "abc")
    check("markup punctuation leaves the name",
          N.validate(dict(GOOD, name="<b>bold</b>"))["name"] == "bbold/b")
    check("a newline becomes a space", N.validate(dict(GOOD, name="a\nb"))["name"] == "a b")


def t_raw_json_is_strict():
    good = json.dumps(GOOD)
    check("a JSON answer on the menu is kept", N.parse_model(good)["theme"] == "ember")
    check("a repeated key is refused", bool(refused_raw('{"name":"a","name":"b",' + good[1:])))
    check("NaN is refused", bool(refused_raw(good.replace('"ember"', 'NaN'))))
    check("Infinity is refused", bool(refused_raw(good.replace('"normal"', 'Infinity'))))
    check("prose around the JSON is refused", bool(refused_raw("Here you go: " + good)))
    check("a far too long answer is refused", bool(refused_raw("{" + " " * N.MAX_RAW + "}")))
    check("an empty answer is refused", bool(refused_raw("")))
    check("a non-text answer is refused", bool(refused_raw(None)))


def t_no_room_for_private_data():
    """The spec has nowhere to put an email, a fact, a file or a token."""
    check("the whole vocabulary is the six keys", N.STYLE_KEYS ==
          ("name", "theme", "figure", "motion", "speed", "kinds"), N.STYLE_KEYS)
    check("every key is required", N.REQUIRED == N.STYLE_KEYS)
    check("only approvals and reminders can be styled", N.KINDS == ("approval", "reminder"))
    for forbidden in ("email", "sender", "memory", "fact", "file", "path", "token", "html",
                      "javascript", "intent", "url", "layout", "bitmap", "drawable"):
        check(f"a style cannot carry {forbidden}",
              bool(refused(dict(GOOD, **{forbidden: "x"}))))
    src = (HERE / "jarvis_notification_styles.py").read_text("utf-8")
    for forbidden in ("jarvis_email", "jarvis_memory", "PendingIntent", "startActivity",
                      "WebView", "import subprocess", "import socket"):
        check(f"the module never uses {forbidden}", forbidden not in src)


# ================================================== 3. drafts

def t_drafts_from_own_words_only():
    st = fresh_store()
    ask = fake_ask(json.dumps(GOOD))
    code, out = N.draft("warm orange, a spark, pulsing", provenance="typed", ask=ask, st=st)
    check("a typed description makes a preview", code == 200 and out["ok"], out)
    check("the preview carries the sentence and the parts",
          "spark" in out["draft"]["said"] and len(out["draft"]["parts"]) == 5, out["draft"])
    check("a preview says there is no approval card", out["card"] is False and "No approval card" in out["no_card"])
    check("a preview says nothing is applied yet", "tap Add" in out["said"], out["said"])
    check("the draft is held, not saved", st.styles() == [] and len(st.drafts()) == 1)
    check("pasted words are refused",
          N.draft("x", provenance="pasted", ask=ask, st=st)[0] == 400)
    check("shared words are refused",
          N.draft("x", provenance="shared", ask=ask, st=st)[0] == 400)
    check("a tainted chat is refused",
          N.draft("warm orange", provenance="voice", tainted=True, ask=ask, st=st)[0] == 409)
    check("empty words are refused", N.draft("  ", provenance="typed", ask=ask, st=st)[0] == 400)
    check("far too many words are refused",
          N.draft("x" * (N.MAX_WORDS + 1), provenance="typed", ask=ask, st=st)[0] == 400)
    off = fake_ask(json.dumps(dict(GOOD, theme="rainbow")))
    code, out = N.draft("rainbow", provenance="typed", ask=off, st=st)
    check("a model answer off the menu makes nothing", code == 422 and out["ok"] is False, out)
    check("... and says why, in words", bool(out.get("why")), out)
    check("... and adds no draft", len(st.drafts()) == 1, len(st.drafts()))
    boom = fake_ask(None)
    check("no answer from the model makes nothing",
          N.draft("warm orange", provenance="typed", ask=boom, st=st)[0] == 503)


def t_the_model_is_asked_only_on_this_pc():
    ask, why = N.default_ask()
    check("with no local model there is no ask", ask is None and why, (ask, why))
    words = "warm orange, a spark, pulsing"
    p = N.prompt(words)
    check("the prompt holds the owner's words", words in p)
    check("the prompt offers the whole menu", all(k in p for k in N.THEMES) and
          all(k in p for k in N.FIGURES) and all(k in p for k in N.MOTIONS))
    check("the prompt forbids what is off the menu", "photo" in p and "code" in p)
    check("the schema offers every choice as an enum",
          N.SCHEMA["properties"]["theme"]["enum"] == list(N.THEMES) and
          N.SCHEMA["properties"]["kinds"]["items"]["enum"] == list(N.KINDS))
    check("the schema allows nothing else",
          N.SCHEMA["additionalProperties"] is False and
          N.SCHEMA["properties"]["name"]["maxLength"] == N.MAX_NAME)


# ================================================== 4. the store

def t_the_store():
    st = fresh_store()
    d = st.add_draft(N.validate(GOOD))
    s, why = st.keep(d["id"])
    check("Add keeps the draft exactly as previewed",
          s is not None and all(s[k] == GOOD[k] for k in N.STYLE_KEYS), (s, why))
    check("... with an id and a created time", s["id"].startswith("s") and s["created"] > 0)
    check("a kept style is listed", [x["id"] for x in st.styles()] == [s["id"]])
    check("keeping the same draft twice does nothing the second time",
          st.keep(d["id"]) == (None, N.DRAFT_GONE))
    check("a made-up draft id is refused", st.keep("d0000000000") == (None, N.DRAFT_GONE))
    check("discard drops one", st.discard(st.add_draft(N.validate(GOOD))["id"]) is True)
    check("delete is immediate", st.delete(s["id"]) is True and st.styles() == [])
    check("deleting nothing says so", st.delete(s["id"]) is False)
    check("a made-up id is not found", st.delete("s0000000000") is False)
    many = fresh_store()
    for i in range(N.MAX_STYLES):
        got, _ = many.keep(many.add_draft(N.validate(dict(GOOD, name=f"Style {i}")))["id"])
        check(f"style {i + 1} is kept", got is not None)
    extra, why = many.keep(many.add_draft(N.validate(dict(GOOD, name="One too many")))["id"])
    check("a ninth style is refused, in words", extra is None and why == N.TOO_MANY, why)
    expired = fresh_store(clock=lambda: 1000.0)
    did = expired.add_draft(N.validate(GOOD))["id"]
    expired.clock = lambda: 1000.0 + N.DRAFT_TTL + 1
    check("an old preview expires", expired.keep(did) == (None, N.DRAFT_GONE))
    check("... and is gone from the list", expired.drafts() == [])
    capped = fresh_store()
    for i in range(N.MAX_DRAFTS + 2):
        capped.add_draft(N.validate(dict(GOOD, name=f"Preview {i}")))
    check("previews are capped", len(capped.drafts()) == N.MAX_DRAFTS, len(capped.drafts()))
    # a hand edit smuggles nothing in
    p = Path(tempfile.mkdtemp(dir=str(TMP))) / "hand.json"
    p.write_text(json.dumps({"version": 1, "styles": [
        {"id": "s0123456789", "name": "Hand", "theme": "ember", "figure": "spark",
         "motion": "pulse", "speed": "normal", "kinds": ["approval"], "created": 1},
        {"id": "s1111111111", "name": "Sneaky", "theme": "<script>", "figure": "spark",
         "motion": "pulse", "speed": "normal", "kinds": ["approval"], "created": 2},
        {"id": "nope", "name": "Bad id", "theme": "ice", "figure": "spark",
         "motion": "none", "speed": "slow", "kinds": ["reminder"], "created": 3},
    ]}), encoding="utf-8")
    hand = N.Store(path=p)
    rows = hand.styles()
    check("a hand-edited file keeps only what is on the menu", [r["name"] for r in rows] == ["Hand"], rows)


def t_which_style_is_live():
    st = fresh_store()
    a, _ = st.keep(st.add_draft(N.validate(dict(GOOD, name="First", kinds=["reminder"])))["id"])
    b, _ = st.keep(st.add_draft(N.validate(dict(GOOD, name="Second", kinds=["reminder"])))["id"])
    check("the newest style that claims a kind is live", N.resolve(st.styles())["reminder"]["id"] == b["id"])
    check("... and a kind nobody claims is not live", "approval" not in N.resolve(st.styles()))
    check("the answer is the same every time",
          N.resolve(st.styles()) == N.resolve(st.styles()))
    st.delete(b["id"])
    check("deleting the newest falls back to the older one",
          N.resolve(st.styles())["reminder"]["id"] == a["id"])
    st2 = fresh_store()
    s, _ = st2.keep(st2.add_draft(N.validate(dict(GOOD, kinds=["approval", "reminder"])))["id"])
    live = N.resolve(st2.styles())
    check("one style can be live for both kinds",
          live["approval"]["id"] == s["id"] and live["reminder"]["id"] == s["id"])


# ================================================== 6. chat

def t_chat():
    st = fresh_store()
    ask = fake_ask(json.dumps(GOOD))
    said = N.from_chat("make my Jarvis notifications look like a warm orange pulse",
                       messages=[{"role": "user", "content": "hi"}], ask=ask, st=st)
    check("chat makes a preview", "Made a style preview" in said, said)
    check("... and applies nothing", st.styles() == [])
    check("chat asks the model the owner's own words",
          "make my Jarvis notifications look like" in (ask.seen[-1] if ask.seen else ""))
    tainted = N.from_chat("make my notifications orange",
                          messages=[{"role": "tool", "content": "email body"}], ask=ask, st=st)
    check("a tainted chat is refused", tainted == N.TAINTED, tainted)
    check("a tainted refusal reuses jarvis_widgets' rule",
          N.chat_tainted is not None and W.chat_tainted([], [{"role": "tool", "content": "x"}]) is True)
    check("nothing that failed reached the store", st.styles() == [])


# ================================================== 7. routes

class FakeHandler:
    def __init__(self, path, body=b"{}"):
        self.path = path
        self.body = body
        self.sent = []
        self.other = 0

    def _send(self, code, out):
        self.sent.append((code, out))

    def do_GET(self):
        self.other += 1

    def do_POST(self):
        self.other += 1


def t_routes():
    N._STORE = None
    try:
        good = lambda s: True
        class H(FakeHandler):
            pass
        N.install(H, origin_ok=good, token_ok=good, read_body=lambda s: s.body)
        h = H(N.LIST_PATH)
        h.do_GET()
        check("GET the list", h.sent and h.sent[0][0] == 200 and h.sent[0][1]["ok"] is True)
        check("the list says what is live and what the menu is",
              "active" in h.sent[0][1] and "themes" in h.sent[0][1] and "motions" in h.sent[0][1])
        check("the list carries no token", "token" not in json.dumps(h.sent[0][1]).lower())
        body = json.dumps({"words": "warm orange", "provenance": "typed"}).encode()
        h = H(N.DRAFT_PATH, body)
        h.do_POST()
        check("a draft route answers 503 with no model", h.sent and h.sent[0][0] == 503, h.sent)
        h = H("/api/widgets", b"{}")
        h.do_GET()
        check("another route passes straight through", h.other == 1 and h.sent == [])
        h = H("/api/notification-styles/add", b"{}")
        h.do_POST()
        check("add with no draft: 404", h.sent and h.sent[0][0] == 404)
        h = H(N.LIST_PATH)
        h.do_GET()
        check("install is idempotent", N.install(H, origin_ok=good, token_ok=good,
                                                 read_body=lambda s: s.body).endswith("(already on)"))
        class Locked(FakeHandler):
            pass
        N.install(Locked, origin_ok=good, token_ok=lambda s: False, read_body=lambda s: s.body)
        h = Locked(N.LIST_PATH)
        h.do_GET()
        check("no token: 401", h.sent[0][0] == 401)
        class Foreign(FakeHandler):
            pass
        N.install(Foreign, origin_ok=lambda s: False, token_ok=good, read_body=lambda s: s.body)
        h = Foreign(N.LIST_PATH)
        h.do_GET()
        check("another origin: 403", h.sent[0][0] == 403)
        class Big(FakeHandler):
            pass
        N.install(Big, origin_ok=good, token_ok=good, read_body=lambda s: s.body)
        h = Big(N.DRAFT_PATH, b"{}" + b" " * 9000)
        h.do_POST()
        check("a body over the cap: 413", h.sent[0][0] == 413)
    finally:
        N._STORE = None


# ================================================== 8. the typed grammar

def t_the_grammar():
    st = fresh_store()
    for phrase in ("make my Jarvis notifications look like warm orange",
                   "make my notifications look like a warm orange pulse",
                   "change how notifications look to warm orange",
                   "style my notifications like a warm orange pulse"):
        got = Q.match(phrase)
        check(f"the grammar catches: {phrase}",
              got is not None and got.name == "notify_style", got)
    check("the widget question is still the widget one",
          Q.match("make me a widget showing my next 3 reminders").name == "widget_make")
    check("an ordinary sentence is not ours",
          Q.match("what is the weather") is None or Q.match("what is the weather").name != "notify_style")


def t_docs_say_the_same_thing():
    """The API doc and the module agree about the six keys and the routes."""
    api = (HERE.parent / "docs" / "JARVIS-API.md").read_text("utf-8")
    if "notification-styles" not in api:
        skip("docs/JARVIS-API.md does not describe the routes yet (this run is before the doc edit)")
        return
    check("the doc names every route", all(p in api for p in
          (N.LIST_PATH, N.DRAFT_PATH, N.ADD_PATH, N.DISCARD_PATH, N.DELETE_PATH)))
    for key in N.STYLE_KEYS:
        check(f"the doc names the key {key}", f"`{key}`" in api or f"\"{key}\"" in api)


if __name__ == "__main__":
    for fn in (t_on_the_menu_is_kept, t_off_the_menu_is_refused, t_text_is_cleaned,
               t_raw_json_is_strict, t_no_room_for_private_data, t_drafts_from_own_words_only,
               t_the_model_is_asked_only_on_this_pc, t_the_store, t_which_style_is_live,
               t_chat, t_routes, t_the_grammar, t_docs_say_the_same_thing):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
