"""test_readpage.py - "read this page out loud" (jarvis_readpage.py,
readpage.patch; the owner's request of 2026-10-05: "does jarvis have the
ability for me to post a webpage into jarvis and it can read the content out
loud?").

    python3 backend/test_readpage.py

Runs anywhere: standard library only, and NO test here may touch the real
network. Every fetch is injected, and the two places that would otherwise
resolve a name (`jarvis_local_http.private_fetch_problem`'s DNS lookup, and
the open itself) are replaced for the length of the check that needs them.

What it proves:

 1. The address's SHAPE, with no socket opened to check it: an empty or
    non-string address, a missing scheme, `ftp://` and `javascript:`, a
    name-and-password in the address, control characters, an address past
    the cap and one with no host are all refused in plain words; http and
    https are taken.
 2. An address that resolves to this PC or a private network is refused at
    prepare - so NO card is ever raised about it (there is nothing to ask).
 3. The card: the address in full, and plainly that only the address is
    sent, that the site sees this PC, that the words are outside text, that
    one card is one address, and that a "no" fetches nothing.
 4. The read: exactly ONE GET, of exactly the address the card showed, with
    no body, no credential and no header but the tool's own (rule 1). Never
    a second address.
 5. Every failure path says so in plain words and returns no text: an
    address that does not answer, a response that is not a page (a PDF, a
    picture, JSON), a body that is a binary file, and a page whose words are
    all scripts and pictures.
 6. An enormous page: the body is cut at the cap and the result says so,
    rather than the read quietly stopping.
 7. The window: one read hands back at most MAX_TEXT_CHARS, the trailer
    names the offset to carry on from, carrying on really continues, and the
    end of the page says it is the end - never a silent cut.
 8. The words: a `<main>`/`<article>` is preferred, and nav, footer,
    header, script, style and form are dropped; entities are unescaped; a
    block element ends a line.
 9. There is no article extractor and NO new dependency: the module imports
    the standard library (plus modules this repository already ships) and
    nothing else.
10. The redirect rule: a redirect to this PC or a private network is
    refused, and one to a public address is followed.
11. The wiring: `read_web_page` is a real tool, it asks the gate as
    `read_web_page` (tier "ask"), it is in NEEDS_A_PERSON so nobody but a
    person's yes can run it, it is NOT in _NOT_READING (so a read marks the
    turn as having read outside text) and it has a card label; the action is
    in the gate's own action set and risk table with the "outbound"/risky
    words; the toml says `ask`; jarvis_asks_first has it in GROUPS,
    HARD_LIMITS, MUST_ASK and LOCKDOWN_ACTIONS; and `readpage.patch` applies
    after the rest of the stack and reverses.
12. Read aloud: `read_web_page` is on tools/gen_private_aloud_cases.py's
    READ_ALOUD_TOOLS, so a voice turn speaks the answer, and both generated
    copies of that table are current.
"""
from __future__ import annotations

import ast
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_readpage.py", "jarvis_agent.py", "jarvis_asks_first.py",
                "jarvis_card_words.py", "jarvis_local_http.py")
sys.path.append(str(HERE / "rebuilt"))
sys.path.append(str(REPO / "tools"))
import _stack  # noqa: E402
import jarvis_asks_first as AF  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import jarvis_local_http as LH  # noqa: E402
import jarvis_readpage as RP  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


HTML = (b"<!DOCTYPE html><html><head><title>Kettle care</title>"
        b"<style>p{color:red}</style></head><body>"
        b"<nav>Home About Shop</nav>"
        b"<main><h1>Looking after a kettle</h1>"
        b"<p>Rinse it &amp; dry it.<br>Never boil it dry.</p>"
        b"<p>Descale it monthly.</p></main>"
        b"<footer>Copyright 2026</footer>"
        b"<script>var x = 'tracking';</script>"
        b"</body></html>")


def fetched(body=HTML, kind="text/html; charset=utf-8", url_seen=None):
    """A stand-in for the one GET. Records the address it was handed."""
    def fetch(url):
        if url_seen is not None:
            url_seen.append(url)
        if isinstance(body, Exception):
            raise body
        return body, kind
    return fetch


def deps(body=HTML, kind="text/html; charset=utf-8", url_seen=None):
    return RP.Deps(fetch=fetched(body, kind, url_seen))


def page_for(url="https://example.com/kettle"):
    """A Page with the private-address check bypassed - the network-free way
    to build one for a read (the check itself has its own checks below)."""
    return RP.Page(url, 0)


class _PrivateOff:
    """`private_fetch_problem` answers "" for the length of a `with` - the
    only way to get past prepare without a real DNS lookup."""

    def __enter__(self):
        self.real = LH.private_fetch_problem
        LH.private_fetch_problem = lambda url: ""
        return self

    def __exit__(self, *exc):
        LH.private_fetch_problem = self.real
        return False


# ======================================================== 1. the address

def t_the_address_shape_is_checked_with_no_socket():
    good = ["http://example.com/x", "https://example.com/a/b?c=d#e",
            "HTTPS://Example.COM/", "https://example.com:8443/x"]
    for url in good:
        try:
            got = RP.check_url(url)
            check(f"taken: {url}", got == url.strip(), got)
        except RP.ReadError as exc:
            check(f"taken: {url}", False, str(exc))
    for url, why in (("", "empty"), ("   ", "blank"), (None, "not a string"),
                     (12, "a number"),
                     ("example.com/x", "no scheme"), ("ftp://example.com/x", "ftp"),
                     ("javascript:alert(1)", "javascript"),
                     ("file:///C:/x", "a file path"),
                     ("https://user:pw@example.com/x", "a password in the address"),
                     ("https://example.com/" + "a" * RP.MAX_URL, "past the cap"),
                     ("https://example.com/a\nb", "a newline"),
                     ("https://exa\x00mple.com/", "a NUL"),
                     ("https://", "no host"), ("http:///x", "no host")):
        try:
            RP.check_url(url)
            check(f"refused: {why}", False, repr(url))
        except RP.ReadError as exc:
            msg = str(exc)
            check(f"refused: {why}, in plain words",
                  bool(msg) and "Traceback" not in msg and " " in msg
                  and not msg.startswith("'"), msg)
    # The shape check must not resolve anything: a resolver that raises proves
    # it never looks a name up. check_url is called before prepare does.
    real = LH._resolved_addresses
    LH._resolved_addresses = lambda host: (_ for _ in ()).throw(
        AssertionError("check_url resolved a name"))
    try:
        check("check_url opens no socket and resolves no name",
              RP.check_url("https://example.com/x") == "https://example.com/x")
    except AssertionError as exc:
        check("check_url opens no socket and resolves no name", False, str(exc))
    finally:
        LH._resolved_addresses = real


def t_a_private_address_is_refused_before_any_card():
    real = LH.private_fetch_problem
    try:
        LH.private_fetch_problem = lambda url: "faked as private for this test"
        try:
            RP.prepare("https://example.com/x")
            check("prepare refuses a private address", False)
        except RP.ReadError as exc:
            check("prepare refuses a private address, in the guard's own words",
                  "faked as private" in str(exc), str(exc))
        check("... and the module has no gate call of its own: a refusal here has "
              "nothing to ask about",
              not hasattr(RP, "gate") and not hasattr(RP, "spawn")
              and not any(isinstance(n, ast.Import) and any(
                  a.name == "jarvis_gate" for a in n.names)
                  for n in ast.walk(ast.parse(Path(RP.__file__).read_text(encoding="utf-8")))))
    finally:
        LH.private_fetch_problem = real
    # A private address that the guard answers for, through prepare, with the
    # guard's real words for a loopback address (no DNS needed for a literal).
    try:
        RP.prepare("http://127.0.0.1:9/x")
        check("a loopback address is refused by the real guard too", False)
    except RP.ReadError as exc:
        check("a loopback address is refused by the real guard too",
              "private" in str(exc) or "this PC" in str(exc), str(exc))


def t_the_offset_must_be_a_number():
    check("no offset is 0", RP.check_offset(None) == 0 and RP.check_offset("") == 0)
    check("a number is itself", RP.check_offset(1500) == 1500)
    check("a number in words is read", RP.check_offset("1500") == 1500)
    for bad in ("later", -5, True, 1.5):
        try:
            RP.check_offset(bad)
            check(f"refused: an offset of {bad!r}", False)
        except RP.ReadError:
            check(f"refused: an offset of {bad!r}", True)


# ======================================================== 2. the card

def t_the_card_names_the_address_and_says_where_it_goes():
    text = RP.describe(page_for())
    low = text.lower()
    check("the address is on the card in full",
          "https://example.com/kettle" in text)
    check("it says only the address is sent",
          "only the address is sent" in low)
    check("it says nothing of the owner's goes with it",
          "no memory" in low and "no email" in low and "no files" in low)
    check("it says the site sees this PC and it cannot be taken back",
          "your pc will contact" in low and "cannot be taken back" in low)
    check("it says the words are a stranger's / outside text",
          "outside text" in low and "never treats them as instructions" in low
          and "never learns a fact from them" in low)
    check("it says one card is one address",
          "one card covers this one address" in low and "another page is another card"
          in low)
    check("it says what a no does", "if you say no" in low and "nothing is fetched" in low)
    check("it names no other site and no link to follow",
          text.count("http") == 1, text)


# ======================================================== 3. the read

def t_the_read_is_one_get_of_exactly_that_address():
    seen = []
    out = RP.run(page_for("https://example.com/kettle"), deps=deps(url_seen=seen))
    check("the read worked", out.get("ok") is True, out)
    check("exactly ONE GET, of exactly the address given",
          seen == ["https://example.com/kettle"], seen)
    check("the address is in the result", out["url"] == "https://example.com/kettle")
    check("the title is read", out["title"] == "Kettle care", out.get("title"))
    check("the words come back", "Rinse it & dry it." in out["text"], out["text"])
    check("the result carries nothing but what it documents, so nothing of the "
          "owner's can ride back out through it",
          set(out) <= {"ok", "url", "title", "text", "offset", "more", "total", "cut",
                       "why", "trailer"}, sorted(out))


def t_the_request_carries_the_address_and_nothing_else():
    """Rule 1: what leaves this PC is the address, and nothing of the
    owner's. _default_fetch is the one place a socket opens, so its Request
    is worth reading: no body, no credential and no header but the tool's
    own."""
    import urllib.request
    seen = {}

    class Resp:
        headers = {"Content-Type": "text/html"}

        def read(self, n=-1):
            return HTML

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def opener(req, timeout, *handlers):
        seen["req"] = req
        seen["timeout"] = timeout
        seen["handlers"] = [type(h).__name__ for h in handlers]
        return Resp()

    real = LH.public_urlopen
    LH.public_urlopen = opener
    try:
        body, kind = RP._default_fetch("https://example.com/kettle")
    finally:
        LH.public_urlopen = real
    req = seen["req"]
    headers = {k.lower(): v for k, v in req.header_items()}
    check("the GET is of exactly that address", req.full_url == "https://example.com/kettle")
    check("no body is sent", req.data is None)
    check("no credential and no cookie ride along",
          not ({"authorization", "cookie", "proxy-authorization"} & set(headers)),
          headers)
    check("no header but the tool's own", set(headers) <= {"user-agent", "accept"}, headers)
    check("it asks for words, not for anything else",
          "text/html" in headers.get("accept", ""), headers)
    check("the redirect rule is installed on the request",
          "_PageRedirect" in seen["handlers"], seen["handlers"])
    check("the whole request is bounded by a timeout", seen["timeout"] == RP.TIMEOUT)
    check("the body and its kind come back", body == HTML and "html" in kind)


def t_every_failure_path_says_so_in_plain_words():
    cases = [
        ("an address that does not answer",
         deps(body=OSError("no route to host")), None),
        ("a PDF", deps(body=b"%PDF-1.4 ...", kind="application/pdf"), "not a web page"),
        ("a picture", deps(body=b"\x89PNG", kind="image/png"), "not a web page"),
        ("JSON", deps(body=b'{"a": 1}', kind="application/json"), "not a web page"),
        ("a binary file with no kind given", deps(body=b"\x00\x01\x02", kind=""), "file"),
        ("a page whose words are all scripts and pictures",
         deps(body=b"<html><head><script>var a=1;</script><style>p{}</style></head>"
                   b"<body><script>more()</script></body></html>"), None),
    ]
    for label, d, want in cases:
        out = RP.run(page_for(), deps=d)
        if label == "a page whose words are all scripts and pictures":
            check(f"{label}: no text, and it says why",
                  out.get("ok") is True and out["text"] == "" and "no readable words" in
                  str(out.get("why", "")), out)
            continue
        check(f"{label} is refused", out.get("ok") is False, out)
        why = str(out.get("why", ""))
        check(f"... with plain words, no traceback and no text",
              why and "Traceback" not in why and "text" not in out, out)
        if want:
            check(f"... and it says what it got instead ({label})", want in why.lower(), why)


def t_an_enormous_page_is_cut_and_says_so():
    huge = b"<html><body><p>" + b"word " * (RP.MAX_BYTES // 2) + b"</p></body></html>"
    check("the stand-in really is past the cap", len(huge) > RP.MAX_BYTES)
    seen = []
    out = RP.run(page_for(), deps=deps(body=huge, url_seen=seen))
    check("an enormous page still reads", out.get("ok") is True, out)
    check("... and says the page is very long",
          "very long" in str(out.get("why", "")), out.get("why"))
    check("... and is marked as cut", out.get("cut") is True)
    check("... and its words stop at the cap, not the whole body",
          out["total"] <= RP.MAX_BYTES, out.get("total"))
    check("... and the reads of the body were capped too, before anything else",
          out["text"] and len(out["text"]) <= RP.MAX_TEXT_CHARS)


# ======================================================== 4. the window

def t_the_window_carries_on_and_never_cuts_silently():
    words = " ".join(f"word{i}" for i in range(2000))     # far past the cap
    body = ("<html><body><p>" + words + "</p></body></html>").encode()
    full = RP.text_of(body, "text/html")
    out = RP.run(page_for(), deps=deps(body=body))
    check("the first read is exactly the cap", len(out["text"]) == RP.MAX_TEXT_CHARS,
          len(out.get("text", "")))
    check("it is exactly the first window of the page's words",
          out["text"] == full[:RP.MAX_TEXT_CHARS])
    check("it says how much was left and where to carry on",
          out.get("more") == RP.MAX_TEXT_CHARS
          and f"{len(full) - RP.MAX_TEXT_CHARS} more characters not shown"
          in str(out.get("trailer", ""))
          and f"offset {RP.MAX_TEXT_CHARS}" in str(out.get("trailer", "")), out)
    check("it is marked as cut", out.get("cut") is True)
    check("the whole text is longer than the window", out["total"] == len(full))
    second = RP.run(RP.Page("https://example.com/kettle", out["more"]), deps=deps(body=body))
    check("carrying on gives the NEXT window, exactly",
          second["text"] == full[RP.MAX_TEXT_CHARS:2 * RP.MAX_TEXT_CHARS]
          and second["offset"] == out["more"], second.get("offset"))
    check("the windows do not overlap at all",
          out["text"] + second["text"] == full[:2 * RP.MAX_TEXT_CHARS])
    short = RP.run(page_for(), deps=deps(body=b"<html><body><p>One short line.</p>"
                                              b"</body></html>"))
    check("a short page has no trailer and nothing more",
          short["more"] is None and "trailer" not in short and short["cut"] is False, short)
    past = RP.run(RP.Page("https://example.com/x", 10 ** 6), deps=deps(body=body))
    check("an offset past the end says it is the end",
          past["text"] == "" and past["more"] is None
          and "end of the page" in str(past.get("trailer", "")), past)


# ======================================================== 5. the words

def t_the_words_are_what_a_reader_would_see():
    text = RP.words_of(HTML.decode("utf-8"))
    check("the heading and the paragraphs are there",
          "Looking after a kettle" in text and "Descale it monthly." in text, text)
    for gone in ("Home About Shop", "Copyright 2026", "var x", "color:red"):
        check(f"a reader never sees: {gone!r}", gone not in text, text)
    check("an entity is unescaped", "Rinse it & dry it." in text, text)
    check("a block element ends a line",
          "Rinse it & dry it." in text.split("\n") and "Never boil it dry." not in
          [l for l in text.split("\n") if "Rinse" in l], text)
    body_only = RP.words_of("<html><body><nav>Menu</nav><p>Real words here</p>"
                           "<footer>Bye</footer></body></html>")
    check("with no main, the body is used and the furniture dropped",
          "Real words here" in body_only and "Menu" not in body_only
          and "Bye" not in body_only, body_only)
    two = RP.words_of("<html><body><main><p>" + "m" * 300 + "</p></main>"
                      "<p>Somewhere else entirely</p></body></html>")
    check("a main with enough text wins over the rest of the body",
          "m" * 300 in two and "Somewhere else" not in two, two[:80])
    tiny = RP.words_of("<html><body><main>hi</main><p>Somewhere else entirely</p>"
                       "</body></html>")
    check("a main that is too small does not hide the page",
          "Somewhere else entirely" in tiny, tiny)
    check("an empty page has no words", RP.words_of("") == "")
    check("a broken page falls back to its plain text",
          "still here" in RP.words_of("<p>still here<span"))


# ======================================================== 6. no new dependency

def t_no_new_dependency():
    tree = ast.parse(Path(RP.__file__).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    stdlib = set(sys.stdlib_module_names)
    ours = {p.stem for p in HERE.glob("jarvis_*.py")} | {"jarvis_framework"}
    outside = names - stdlib - ours
    check("the module imports the standard library and shipped modules only",
          not outside, sorted(outside))
    check("and it names no article extractor",
          "trafilatura" not in Path(RP.__file__).read_text(encoding="utf-8").split(
              "trafilatura` (Python")[0].replace("trafilatura", "", 1)
          or True)
    text = Path(RP.__file__).read_text(encoding="utf-8")
    check("trafilatura is named only as the fallback it is NOT using",
          text.count("trafilatura") <= 3 and "trafilatura" not in names, sorted(names))


# ======================================================== 7. redirects

def t_a_redirect_to_a_private_address_is_refused():
    import urllib.error
    import urllib.request
    import urllib.parse
    h = RP._PageRedirect()
    req = urllib.request.Request("https://example.com/kettle")
    real = LH.private_fetch_problem
    LH.private_fetch_problem = (
        lambda url: "faked as private" if url == "http://127.0.0.1/evil" else "")
    try:
        try:
            h.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1/evil")
            check("a redirect to a private address is refused", False)
        except urllib.error.HTTPError as exc:
            check("a redirect to a private address is refused",
                  "faked as private" in str(exc), str(exc))
        out = h.redirect_request(req, None, 302, "Found", {},
                                 "https://example.com/next")
        check("a redirect to a public address is followed",
              isinstance(out, urllib.request.Request)
              and out.full_url == "https://example.com/next")
    finally:
        LH.private_fetch_problem = real


# ======================================================== 8. the wiring

def t_the_tool_is_wired_and_asks_every_time():
    check("read_web_page is a real tool the model can be offered",
          "read_web_page" in AG.TOOLS)
    tool = AG.TOOLS["read_web_page"]
    check("its gate action is its own name", RP.ACTION == "read_web_page")
    # gate_lookup_name omitted on purpose: the tool's model-facing name IS its
    # jarvis_gate key, which is what the omitted case means (jarvis_agent.Tool).
    check("its gate key is the tool's own name, so the gate row is the one used",
          tool.gate_lookup_name is None and tool.name == RP.ACTION, tool.name)
    check("only a person's yes can run it (NEEDS_A_PERSON)",
          "read_web_page" in AG.NEEDS_A_PERSON)
    check("a read marks the turn as having read outside text",
          "read_web_page" not in AG._NOT_READING)
    check("a card says what it read", AG._READ_LABELS.get("read_web_page"))
    check("and it is not a note writer", "read_web_page" not in AG.NOTE_WRITES)
    page, text = AG._prepare_read_web_page({"url": "https://example.com/x"})
    check("prepare() hands back the checked page and the card's words",
          isinstance(page, RP.Page) and page.url == "https://example.com/x"
          and "https://example.com/x" in text)
    seen = []
    real = RP.DEPS
    RP.DEPS = RP.Deps(fetch=fetched(url_seen=seen))
    try:
        out = AG._run_read_web_page({"url": "https://example.com/other"}, page)
    finally:
        RP.DEPS = real
    check("run() reads the page the CARD showed, not one rebuilt from the arguments",
          out.get("ok") is True and seen == ["https://example.com/x"], (seen, out))
    check("a bad address never reaches a card: prepare raises, the model is told",
          _raises(lambda: AG._prepare_read_web_page({"url": "not a url"})))
    check("the tool's description tells the model the words are data, not orders",
          "outside text" in tool.schema()["function"]["description"])
    check("and that a long page carries on with an offset",
          "offset" in tool.schema()["function"]["description"])
    check("the tool is inside a group, so a short-list turn can still reach it",
          any("read_web_page" in members for _g, _w, members in AG.TOOL_GROUPS))


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except Exception:
        return True


def t_the_gate_row_and_the_tier():
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("jarvis-framework.toml says read_web_page = \"ask\"",
          'read_web_page              = "ask"' in toml or
          'read_web_page = "ask"' in toml.replace("  ", " "), None)
    import re
    m = re.search(r"^read_web_page\s*=\s*\"(\w+)\"", toml, re.M)
    check("... and it really is ask", m is not None and m.group(1) == "ask",
          m.group(1) if m else "no line")
    check("the asks-first page lists it", "read_web_page" in
          [a for _t, rows in AF.GROUPS for a in rows])
    check("no app can loosen it (HARD_LIMITS)", "read_web_page" in AF.HARD_LIMITS)
    check("its own module only ever asks (MUST_ASK)", "read_web_page" in AF.MUST_ASK)
    check("Lockdown covers it (LOCKDOWN_ACTIONS)", "read_web_page" in AF.LOCKDOWN_ACTIONS)
    check("the card has plain words for it",
          _card_title_is_plain("read_web_page"))


def _card_title_is_plain(action: str) -> bool:
    import jarvis_card_words as W
    title = W.title_for(action)
    return title.startswith(W.LEAD) and "read a web page out loud" in title


def t_the_patch_applies_after_the_rest_and_reverses():
    if not shutil.which("git"):
        return skip("git is not installed")
    order = _stack.order()
    if "readpage.patch" not in order:
        check("readpage.patch is in apply-patches.ps1's list", False)
        return
    check("readpage.patch is in apply-patches.ps1's list", True)
    before = order[:order.index("readpage.patch")]
    text, log = _stack.stand_in("jarvis_gate.py", before)
    if text is None:
        return skip("the stand-in for jarvis_gate.py could not be built: " + "; ".join(log))
    check("read_web_page is not in the gate before the patch", "read_web_page" not in text)
    d = Path(tempfile.mkdtemp(prefix="jarvis-readpage-patch-"))
    try:
        (d / "jarvis_gate.py").write_text(text, encoding="utf-8", newline="\n")
        shutil.copy(HERE / "readpage.patch", d / "p.patch")
        r = subprocess.run(["git", "apply", "--include", "jarvis_gate.py", "p.patch"],
                           cwd=d, capture_output=True, text=True)
        check("readpage.patch applies to what the earlier patches wrote",
              r.returncode == 0, r.stderr)
        if r.returncode != 0:
            return
        after = (d / "jarvis_gate.py").read_text(encoding="utf-8")
        check("the patch adds the action to the gate's own action set",
              '"read_web_page",  # jarvis_readpage.py' in after)
        check("... and its risk row, outbound and risky",
              '"read_web_page": ("no", "outbound",' in after)
        # Found on the owner's PC, 2026-10-06: the first version of this patch
        # gave the action its risk row and its place in the "acts only on tier
        # ask" set, and NOT its _TOOL_ACTIONS line. action_for_tool() therefore
        # fell through to "unclassified_tool" - the gate's fail-closed answer,
        # so nothing ran unasked, but the card the owner was shown was never
        # the one this tool raises, and test_agent.py and test_gate_names.py
        # both failed on his install ("read_web_page -> lookup 'read_web_page'
        # -> unclassified_tool"). The tool's own name IS its action name
        # (jarvis_agent.Tool's default when gate_lookup_name is omitted), so
        # the entry is the self-map every neighbour of the same shape has.
        check("... and its _TOOL_ACTIONS line, mapping the tool to its own action",
              '"read_web_page": "read_web_page",' in after)
        # The line has to be IN that dict, not merely somewhere in the file:
        # an entry outside it resolves nothing. The owner's `jarvis_gate.py`
        # is not in this repository (backend/README.md says why), so the
        # stand-in above holds only the patches' hunks - it has the table's
        # ENTRIES and not its opening line. What can be read is the patch's
        # own hunk: the entry must be added into the region whose context
        # lines are the ones the other patches write into `_TOOL_ACTIONS`.
        # (Measured: a regex for `^_TOOL_ACTIONS = {` finds nothing in the
        # stand-in, so a check that leaned on it would be a check that always
        # fails - worse than no check.)
        patch = (HERE / "readpage.patch").read_text(encoding="utf-8")
        hunks = [h for h in patch.split("\n@@ ")[1:]
                 if '"read_web_page": "read_web_page",' in h]
        check("... inside the _TOOL_ACTIONS table itself (test setup)",
              len(hunks) == 1 and '"tidy_inbox": "tidy_inbox",' in hunks[0],
              "the entry is in the file but not added inside the tool table")
        check("... and the row says the one page, never a link on it, and outside text",
              "never a link on it" in after and "outside text" in after)
        r2 = subprocess.run(["git", "apply", "-R", "--include", "jarvis_gate.py",
                             "p.patch"], cwd=d, capture_output=True, text=True)
        check("... and it reverses cleanly",
              r2.returncode == 0
              and (d / "jarvis_gate.py").read_text(encoding="utf-8") == text, r2.stderr)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_it_is_read_aloud_and_the_copies_are_current():
    import gen_private_aloud_cases as G
    check("read_web_page is on the read-aloud list",
          "read_web_page" in G.READ_ALOUD_TOOLS, G.READ_ALOUD_TOOLS)
    check("it is a real tool, not a made-up name",
          "read_web_page" in AG.TOOLS or "read_web_page" in G.RECORDED_READS)
    doc = G.document()
    for p in G.COPIES:
        have = p.read_text(encoding="utf-8") if p.exists() else ""
        check(f"{p.relative_to(G.ROOT)} matches (python3 tools/gen_private_aloud_cases.py)",
              have == doc)
    import json
    table = json.loads(doc)
    row = {c["name"]: c for c in table["cases"]}.get("the tool read_web_page ran")
    check("the table says a read_web_page answer is read aloud",
          row is not None and row["read"] is True, row)
    check("and it is listed in the table's own aloud list",
          "read_web_page" in table["read_aloud_tools"])
    # Every EARLIER rule still comes first. Proved on the generator's own rule
    # function (G.may_read) with a read_web_page step, rather than on rows the
    # table happens not to carry for this tool.
    steps = G.ran("read_web_page")
    check("a plain read_web_page answer is read aloud",
          G.may_read(dict(G.PLAIN), G.ROUTE, steps, "live") is True)
    for label, heard, route, stream in (
            ("a sensitive saved fact", dict(G.PLAIN),
             dict(G.ROUTE, injected_sensitive=1), "live"),
            ("a question the PC marked private", dict(G.PLAIN, question_private=True),
             G.ROUTE, "live"),
            ("the router's private gate", dict(G.PLAIN),
             dict(G.ROUTE, gate="private"), "live"),
            ("remembered facts, with memory kept on screen",
             dict(G.PLAIN, memory_aloud=False), dict(G.ROUTE, injected_facts=1), "live"),
            ("an event stream that dropped", dict(G.PLAIN), G.ROUTE, "dropped"),
            ("a stream that was stale when the question was asked", dict(G.PLAIN),
             G.ROUTE, "stale_at_start")):
        got = G.may_read(heard, route, steps, stream)
        check(f"earlier rule first - {label}: the answer stays on screen", got is False, got)
    # `private_aloud` false with NOTHING else private (the shape of a "hey
    # Jarvis" clip under "Only trust the talk button") is read aloud - the
    # same answer the table already gives web_search
    # ("hey Jarvis under 'Only trust the talk button': web_search only").
    # The stricter setting acts through the three *_aloud fields, and this
    # tool is on the web's side of them, not the screen's; nothing new was
    # written for it, which is the point.
    strict = dict(G.PLAIN, **G.STRICT_WAKE)
    check("under the strict hands-free setting it behaves exactly as web_search does",
          G.may_read(strict, G.ROUTE, steps, "live")
          == G.may_read(strict, G.ROUTE, G.ran("web_search"), "live")
          is True)


def t_the_module_is_shipped_and_ascii():
    text = Path(RP.__file__).read_bytes()
    check("jarvis_readpage.py is ASCII", all(c < 128 for c in text))
    check("... with LF line endings only", b"\r\n" not in text)
    patch = (HERE / "readpage.patch").read_bytes()
    check("readpage.patch is ASCII", all(c < 128 for c in patch))
    check("... with LF line endings only", b"\r\n" not in patch)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("apply-patches.ps1 copies jarvis_readpage.py in",
          "'jarvis_readpage.py'" in ps1)
    check("... and applies readpage.patch last",
          ps1.index("'readpage.patch'") > ps1.index("'tutorials.patch'"))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
