"""jarvis_browser_control.py against a REAL browser, on pages served from
this machine only.

test_browser_control.py proves the logic with injected fakes. This file is
the other half: the real CDP page reader, the real Playwright actions, and
the real listeners for dialogs, pop-ups, downloads, crashes and navigations
- against small local pages served by Python's own http.server on
127.0.0.1. Nothing here touches the internet.

Two host names reach the same local server, which is what lets the domain
fence be tested with no second machine: "localhost" is the allowed site,
"127.0.0.1" plays a foreign one.

SKIPS (exit 0) when Playwright is not installed, or when no Chromium can be
launched - it is an optional dependency this project has not switched on.
To run it for real:

    pip install playwright
    playwright install chromium
    python test_browser_control_live.py

It runs the browser headless via the module's test-only `_HEADLESS` switch;
the module's own default stays a visible window.
"""
import glob
import json
import os
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import playwright.sync_api  # noqa: F401
except Exception as exc:  # pragma: no cover - the skip path
    print(f"SKIP: playwright is not installed ({type(exc).__name__}) - "
          "nothing to test against a real browser")
    sys.exit(0)

import jarvis_browser_control as B

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


LONG_TEXT = " ".join(f"sentence{i} of a long help article." for i in range(200))

CHAT = """<!doctype html><html><head><title>Support</title></head><body>
<nav><a href="/chat">Home</a></nav>
<main>
  <h1>Support chat</h1>
  <div role="log" aria-label="Conversation" id="log"><p>Agent: hello</p><p>Agent: how can I help?</p></div>
  <label>Message <input id="msg" type="text"></label>
  <button id="send" onclick="var m=document.getElementById('msg');var p=document.createElement('p');p.textContent='You: '+m.value;document.getElementById('log').appendChild(p);m.value='';">Send</button>
  <button onclick="setTimeout(function(){var p=document.createElement('p');p.textContent='Agent: a slow reply';document.getElementById('log').appendChild(p);},300)">Ask</button>
  <button disabled>Attach</button>
  <button style="display:none">Hidden thing</button>
  <div style="opacity:0"><button>Faded</button></div>
  <label>Password <input id="pw" type="password"></label>
  <button onclick="document.getElementById('pwlen').value=String(document.getElementById('pw').value.length)">Check password</button>
  <output id="pwlen" aria-label="Password length"></output>
  <section aria-label="Order 1"><h2>Order 1</h2><button onclick="document.title='replied 1'">Reply</button></section>
  <section aria-label="Order 2"><h2>Order 2</h2><button onclick="document.title='replied 2'">Reply</button></section>
  <a href="http://127.0.0.1:{PORT}/foreign">Leave site</a>
  <a href="/redir">Redirect away</a>
  <button onclick="document.title='answered '+confirm('Delete your account?')">Delete account</button>
  <button onclick="alert('Saved');document.title='saved'">Save</button>
  <a href="/file.bin">Get file</a>
  <a href="/help" target="_blank">Open help</a>
  <button onclick="window.open('http://127.0.0.1:{PORT}/foreign')">Open foreign</button>
  <button onclick="var f=document.createElement('iframe');f.src='http://127.0.0.1:{PORT}/widget';f.title='Widget';document.body.appendChild(f);">Load widget</button>
  <article><p>{LONG}</p></article>
  <script>window.secretState = {"x": 1};</script>
</main>
<button style="position:absolute;top:900px;left:20px">Covered</button>
<div style="position:absolute;top:880px;left:0;width:600px;height:80px;background:#fff">cookie banner</div>
</body></html>"""

MODAL = """<!doctype html><html><head><title>Modal</title></head><body>
<button>Behind</button>
<div style="height:3000px">tall page</div>
<button>Far below</button>
<div style="position:fixed;inset:0;background:rgba(0,0,0,0.5)"></div>
<div role="dialog" aria-label="Cookies" style="position:fixed;top:100px;left:100px;background:#fff;padding:20px">
  <button>Accept only necessary</button>
</div>
</body></html>"""


def make_server():
    pages = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/redir":
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{port}/foreign")
                self.end_headers()
                return
            if path == "/file.bin":
                body = b"x" * 64
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", "attachment; filename=file.bin")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = pages.get(path, f"<p>other page {path}</p>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    pages["/chat"] = CHAT.replace("{PORT}", str(port)).replace("{LONG}", LONG_TEXT)
    pages["/modal"] = MODAL
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def start_browser() -> str:
    """Launch through the module itself (headless), falling back to a
    Chromium build on disk if Playwright's own expected build is missing.
    Returns "" on success, or why it could not."""
    B._HEADLESS = True
    tried = []
    candidates = [{}]
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or ""
    for pattern in ("chromium-*/chrome-linux*/chrome", "chromium-*/chrome-win*/chrome.exe"):
        for exe in sorted(glob.glob(os.path.join(root, pattern)) if root else []):
            candidates.append({"executable_path": exe})
    for options in candidates:
        B._LAUNCH_OPTIONS = options
        try:
            B._page_for("probe", create=True)
            B.close("probe")
            return ""
        except Exception as exc:
            tried.append(f"{options or 'default'}: {str(exc).splitlines()[0][:160]}")
            if B._playwright is not None and B._browser is None:
                try:
                    B._playwright.stop()
                except Exception:
                    pass
                B._playwright = None
    return "; ".join(tried)


BASE = ""


def fresh(session: str, path: str = "/chat"):
    """A session on a freshly loaded page, through a real (approved)
    navigate step - the same way a real plan would get there."""
    B.close(session)
    p = B.plan("open", session, [{"action": "navigate", "value": BASE + path, "why": "x"}])
    out = B.run(p, approved=True)
    assert out["ok"], out
    return B._sessions[session]


def t_the_reader_sees_what_a_person_sees():
    fresh("read")
    page = B._default_read("read")
    names = {(e["role"], e["name"]) for e in page["elements"]}
    check("the reader returns the page's URL", page["url"].startswith(BASE), page["url"])
    check("a visible textbox is read", ("textbox", "Message") in names, sorted(names))
    check("a visible button is read", ("button", "Send") in names, sorted(names))
    check("the chat log container is read", ("log", "Conversation") in names, sorted(names))
    check("a display:none button is NOT read", ("button", "Hidden thing") not in names)
    check("a button inside an opacity:0 wrapper is NOT read", ("button", "Faded") not in names)
    check("a button fully covered by a banner painted over it is NOT read",
          ("button", "Covered") not in names, sorted(names))
    attach = [e for e in page["elements"] if e["name"] == "Attach"]
    check("a disabled button is read as disabled",
          len(attach) == 1 and attach[0]["enabled"] is False, repr(attach))
    pw = [e for e in page["elements"] if e["role"] == "textbox" and e["name"] == "Password"]
    check("a password field is flagged sensitive and password",
          len(pw) == 1 and pw[0]["sensitive"] and pw[0]["password"], repr(pw))
    heading = [e for e in page["elements"] if e["role"] == "heading" and e["name"] == "Support chat"]
    check("a heading is read but not marked interactive",
          len(heading) == 1 and heading[0]["interactive"] is False, repr(heading))
    replies = [e for e in page["elements"] if e["name"] == "Reply"]
    check("both Reply buttons are read, each with the section it is in",
          sorted(e["within_name"] for e in replies) == ["Order 1", "Order 2"], repr(replies))
    check("every record is the compact shape, no HTML",
          all(set(e) == {"role", "name", "text", "enabled", "interactive", "sensitive",
                         "password", "within_role", "within_name"} for e in page["elements"]),
          repr(page["elements"][:2]))


def t_a_fixed_modal_hides_what_is_behind_it():
    fresh("modal", "/modal")
    page = B._default_read("modal")
    names = {(e["role"], e["name"]) for e in page["elements"]}
    check("the modal's own button is readable",
          ("button", "Accept only necessary") in names, sorted(names))
    check("the button behind the modal backdrop is NOT offered",
          ("button", "Behind") not in names, sorted(names))
    p = B.plan("x", "modal", [{"role": "button", "name": "Behind", "action": "click", "why": "x"}])
    check("so a plan to click it is unmatched, not a step", p.steps == [], repr(p.steps))
    # The backdrop is position:fixed and fills the viewport, so it stays over
    # everything as the page scrolls - including a button 3000px down, whose
    # document position is well outside the backdrop's own box.
    check("a button far below the fold, behind the same fixed backdrop, is NOT offered",
          ("button", "Far below") not in names, sorted(names))
    page2 = B._sessions["modal"]
    page2.evaluate("window.scrollTo(0, 2000)")
    names2 = {(e["role"], e["name"]) for e in B._default_read("modal")["elements"]}
    check("still true after the page has been scrolled",
          ("button", "Far below") not in names2 and ("button", "Behind") not in names2
          and ("button", "Accept only necessary") in names2, sorted(names2))


def t_ambiguity_is_reported_and_within_resolves_it():
    fresh("amb")
    p = B.plan("reply", "amb", [{"role": "button", "name": "Reply", "action": "click", "why": "x"}])
    check("two same-named buttons are NOT turned into a step", p.steps == [], repr(p.steps))
    check("the reason says ambiguous and names the sections",
          p.unmatched and "ambiguous" in p.unmatched[0]["reason"]
          and "Order 2" in p.unmatched[0]["reason"], repr(p.unmatched))
    p2 = B.plan("reply", "amb", [{"role": "button", "name": "Reply", "within": "Order 2",
                                  "action": "click", "why": "x"}])
    check("with within, exactly one step", len(p2.steps) == 1, repr(p2.unmatched))
    out = B.run(p2, approved=True)
    title = B._sessions["amb"].title()
    check("the run clicked the Reply inside Order 2, not Order 1",
          out["ok"] and title == "replied 2", repr((out, title)))


def t_a_real_chat_round_trip():
    fresh("chat")
    p = B.plan("say hello", "chat", [
        {"role": "textbox", "name": "Message", "action": "type", "value": "hello there",
         "why": "x", "leaves_machine": True},
        {"role": "button", "name": "Send", "action": "click", "why": "x", "leaves_machine": True},
        {"role": "log", "name": "Conversation", "action": "read_new", "value": "2", "why": "x"},
    ])
    check("all three steps planned", len(p.steps) == 3, repr(p.unmatched))
    out = B.run(p, approved=True)
    check("the run finished", out["ok"] is True, repr(out))
    check("read_new returns only the new message", out["done"][2]["value"] == "[2] You: hello there",
          repr(out["done"][2]["value"]))


def t_the_page_settles_before_the_next_step():
    fresh("settle")
    p = B.plan("ask", "settle", [
        {"role": "button", "name": "Ask", "action": "click", "why": "x"},
        {"role": "log", "name": "Conversation", "action": "read_new", "value": "2", "why": "x"},
    ])
    out = B.run(p, approved=True)
    check("a reply that arrives 300ms after the click is seen by the next step",
          out["ok"] and "a slow reply" in out["done"][1]["value"], repr(out))


def t_read_page_is_clean_capped_and_continues():
    fresh("text")
    p = B.plan("read", "text", [{"action": "read_page", "value": "0", "why": "x"}])
    out = B.run(p, approved=True)
    text = out["done"][0]["value"] if out.get("ok") else ""
    check("read_page ran", out["ok"] is True, repr(out))
    check("it starts with the main heading", text.startswith("# Support chat"), text[:200])
    check("no script content leaks into it", "secretState" not in text, text[:400])
    check("the nav outside <main> is not included", "Home" not in text.split("\n")[0], text[:200])
    body, _, trailer = text.rpartition("\n")
    check("it is capped, and the trailer says how much is left",
          len(body) == B._MAX_PAGE_TEXT_CHARS and "more characters not shown" in trailer,
          repr(trailer))
    p2 = B.plan("read more", "text", [{"action": "read_page",
                                        "value": str(B._MAX_PAGE_TEXT_CHARS), "why": "x"}])
    out2 = B.run(p2, approved=True)
    check("the next window continues where the first stopped",
          out2["ok"] and out2["done"][0]["value"] != text, repr(out2)[:300])


def t_a_click_to_a_foreign_site_is_blocked_before_it_loads():
    fresh("fence")
    p = B.plan("leave", "fence", [{"role": "link", "name": "Leave site", "action": "click", "why": "x"},
                                  {"role": "button", "name": "Send", "action": "click", "why": "x"}])
    out = B.run(p, approved=True)
    url = B._sessions["fence"].url
    check("the run stopped", out["ok"] is False, repr(out))
    check("the reason names the foreign address and says it was blocked",
          "127.0.0.1" in out["reason"] and "blocked" in out["reason"], out["reason"])
    check("the tab never left the allowed site", url.startswith(BASE), url)
    check("the step after it did not run", len(out["not_run"]) == 1, repr(out))


def t_a_redirect_to_a_foreign_site_is_caught_after_it_lands():
    fresh("redir")
    p = B.plan("go", "redir", [{"role": "link", "name": "Redirect away", "action": "click", "why": "x"},
                               {"role": "button", "name": "Send", "action": "click", "why": "x"}])
    out = B.run(p, approved=True)
    check("the run stopped", out["ok"] is False, repr(out))
    check("the reason names the foreign address", "127.0.0.1" in out["reason"]
          and "outside the allowed sites" in out["reason"], out["reason"])
    check("the step after it did not run", len(out["not_run"]) == 1, repr(out))


def t_explicit_allowed_domains_is_the_fence():
    fresh("fence2")
    p = B.plan("go", "fence2", [{"role": "link", "name": "Redirect away", "action": "click", "why": "x"}],
               allowed_domains=["localhost", "127.0.0.1"])
    out = B.run(p, approved=True)
    check("CONTROL: a redirect inside allowed_domains is fine", out["ok"] is True, repr(out))


def t_a_confirm_is_never_answered_yes_and_stops_the_run():
    fresh("confirm")
    p = B.plan("delete", "confirm", [
        {"role": "button", "name": "Delete account", "action": "click", "why": "x"},
        {"role": "button", "name": "Send", "action": "click", "why": "x"}])
    out = B.run(p, approved=True)
    title = B._sessions["confirm"].title()
    check("the run stopped", out["ok"] is False, repr(out))
    check("the reason quotes the question and says Cancel",
          "Delete your account?" in out["reason"] and "Cancel" in out["reason"], out["reason"])
    check("the page really got 'no' from confirm()", title == "answered false", title)
    check("the next step did not run", len(out["not_run"]) == 1, repr(out))


def t_an_alert_is_closed_noted_and_the_run_goes_on():
    fresh("alert")
    p = B.plan("save", "alert", [
        {"role": "button", "name": "Save", "action": "click", "why": "x"},
        {"role": "textbox", "name": "Message", "action": "type", "value": "after", "why": "x"}])
    out = B.run(p, approved=True)
    check("the run finished", out["ok"] is True, repr(out))
    check("the alert's text is in the notes", any("Saved" in n for n in out.get("notes", [])),
          repr(out.get("notes")))


def t_a_download_is_blocked_and_stops_the_run():
    fresh("dl")
    p = B.plan("get", "dl", [{"role": "link", "name": "Get file", "action": "click", "why": "x"},
                             {"role": "button", "name": "Send", "action": "click", "why": "x"}])
    out = B.run(p, approved=True)
    check("the run stopped", out["ok"] is False, repr(out))
    check("the reason names the file and says nothing was saved",
          "file.bin" in out["reason"] and "nothing was saved" in out["reason"], out["reason"])


def t_a_popup_stops_the_run():
    fresh("pop")
    p = B.plan("help", "pop", [{"role": "link", "name": "Open help", "action": "click", "why": "x"},
                               {"role": "button", "name": "Send", "action": "click", "why": "x"}])
    out = B.run(p, approved=True)
    check("the run stopped", out["ok"] is False, repr(out))
    check("the reason says a new tab opened", "new tab" in out["reason"], out["reason"])


def t_a_popup_to_a_foreign_site_is_blocked_too():
    fresh("pop2")
    p = B.plan("open", "pop2", [{"role": "button", "name": "Open foreign", "action": "click",
                                  "why": "x"}])
    out = B.run(p, approved=True)
    urls = [pg.url for pg in B._sessions["pop2"].context.pages]
    check("the run stopped", out["ok"] is False, repr(out))
    check("the new tab never loaded the foreign site",
          not any(u.startswith("http://127.0.0.1") for u in urls), repr(urls))


def t_a_foreign_iframe_is_not_blocked():
    # A chat widget is very often an iframe from another domain. The fence
    # is for where the TAB goes, not for what a page embeds.
    fresh("frame")
    p = B.plan("load", "frame", [{"role": "button", "name": "Load widget", "action": "click",
                                   "why": "x"}])
    out = B.run(p, approved=True)
    frames = [f.url for f in B._sessions["frame"].frames]
    check("CONTROL: adding a foreign iframe does not stop the run", out["ok"] is True, repr(out))
    check("and the iframe really loaded", any(u.endswith("/widget") for u in frames), repr(frames))


def t_a_crash_stops_the_run():
    page = fresh("crash")
    p = B.plan("send", "crash", [{"role": "button", "name": "Send", "action": "click", "why": "x"}])
    try:
        page.goto("chrome://crash", timeout=3000)
    except Exception:
        pass
    out = B.run(p, approved=True)
    check("the run stopped", out["ok"] is False, repr(out))
    check("the reason says the tab crashed", "crashed" in out["reason"], out["reason"])
    B.close("crash")


def t_a_page_that_moved_on_its_own_stops_the_run():
    page = fresh("moved")
    p = B.plan("send", "moved", [{"role": "button", "name": "Send", "action": "click", "why": "x"}])
    page.evaluate("history.pushState({}, '', '/chat?elsewhere=1')")
    out = B.run(p, approved=True)
    check("the run stopped before acting", out["ok"] is False and out["done"] == [], repr(out))
    check("the reason names both addresses",
          "changed from" in out["reason"] and "elsewhere=1" in out["reason"], out["reason"])


def t_a_secret_is_typed_but_never_returned():
    fresh("secret")
    real = "hunter2-zebra"
    literal = B.plan("log in", "secret", [{"role": "textbox", "name": "Password", "action": "type",
                                            "value": real, "why": "x"}])
    check("a literal password is refused at plan time", literal.steps == [], repr(literal.steps))
    check("and the card does not print it", real not in B.describe(literal), B.describe(literal))
    p = B.plan("log in", "secret", [
        {"role": "textbox", "name": "Password", "action": "type",
         "value": "<secret>shop_pw</secret>", "why": "x"},
        {"role": "button", "name": "Check password", "action": "click", "why": "x"},
        {"role": "status", "name": "Password length", "action": "read", "why": "x"},
        {"role": "textbox", "name": "Password", "action": "read", "why": "x"}])
    card = B.describe(p)
    asked = []
    out = B.run(p, approved=True, secrets=lambda name, host: asked.append((name, host)) or real)
    blob = json.dumps(out) + card + json.dumps(p.as_dict())
    check("the secret was looked up once, for the page's host",
          asked == [("shop_pw", "localhost")], repr(asked))
    check("reading a password field back is refused at plan time",
          any("never read back" in u["reason"] for u in p.unmatched), repr(p.unmatched))
    check("the real value reached the page (its length was read back)",
          out["ok"] and out["done"][2]["value"] == str(len(real)), repr(out))
    check("the real value is nowhere in the plan, the card, or the result", real not in blob)
    check("the placeholder is what the result shows",
          out["done"][0]["value"] == "<secret>shop_pw</secret>", repr(out["done"][0]))


def t_a_secret_with_no_store_types_nothing():
    fresh("nostore")
    p = B.plan("log in", "nostore", [{"role": "textbox", "name": "Password", "action": "type",
                                       "value": "<secret>shop_pw</secret>", "why": "x"}])
    out = B.run(p, approved=True)
    value = B._sessions["nostore"].locator("#pw").input_value()
    check("the run stopped", out["ok"] is False, repr(out))
    check("nothing was typed", value == "", repr(value))


TESTS = (t_the_reader_sees_what_a_person_sees, t_a_fixed_modal_hides_what_is_behind_it,
         t_ambiguity_is_reported_and_within_resolves_it, t_a_real_chat_round_trip,
         t_the_page_settles_before_the_next_step, t_read_page_is_clean_capped_and_continues,
         t_a_click_to_a_foreign_site_is_blocked_before_it_loads,
         t_a_redirect_to_a_foreign_site_is_caught_after_it_lands,
         t_explicit_allowed_domains_is_the_fence,
         t_a_confirm_is_never_answered_yes_and_stops_the_run,
         t_an_alert_is_closed_noted_and_the_run_goes_on,
         t_a_download_is_blocked_and_stops_the_run, t_a_popup_stops_the_run,
         t_a_popup_to_a_foreign_site_is_blocked_too, t_a_foreign_iframe_is_not_blocked,
         t_a_crash_stops_the_run, t_a_page_that_moved_on_its_own_stops_the_run,
         t_a_secret_is_typed_but_never_returned, t_a_secret_with_no_store_types_nothing)


if __name__ == "__main__":
    why = start_browser()
    if why:
        print(f"SKIP: playwright is installed but no Chromium could be launched ({why})")
        sys.exit(0)
    server, port = make_server()
    BASE = f"http://localhost:{port}"
    try:
        for fn in TESTS:
            print(f"\n--- {fn.__name__} ---")
            try:
                fn()
            except Exception:
                FAILED.append(fn.__name__)
                traceback.print_exc()
    finally:
        try:
            B.close()
        finally:
            server.shutdown()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
