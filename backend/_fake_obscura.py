"""A stand-in for `obscura --stealth mcp`, for the tests only (never shipped).

It speaks the same thing Obscura's MCP server does over standard input and
output - one JSON message per line - and answers the tools jarvis_obscura.py may
call, from a small made-up web. It runs no page script and needs no network.

The formats copy what crates/obscura-mcp/src/lib.rs prints (read on 2026-09-29):
browser_snapshot -> "URL: ..\\nTitle: ..\\n\\n<body>\\n\\nN interactive element(s)
registered. Call browser_interactive_elements ...", browser_interactive_elements
-> `ref=e3    input[text]            "Search" name="q"` (the label with Rust's
{:?} escaping), browser_links -> one JSON object per line, and errors come back
as {"isError": true} with "Error: ...". Anything the real program does that this
does not is NOT covered by the tests - that is what tools/check_obscura.py is for.

Environment (set by a test):
  FAKE_LOG    a file: one JSON line per event ("start" with argv and environment
              NAMES, then every tools/call).
  FAKE_MODE   "" (normal), "hang" (never answers a tool call), "die" (exits after
              the handshake), "big" (answers a snapshot with a huge line),
              "captcha" (every page is a "Just a moment..." page),
              "visit_private" (does NOT refuse private addresses: the guard is off).
"""
import base64
import json
import os
import re
import sys
import time

MODE = os.environ.get("FAKE_MODE", "")
LOG = os.environ.get("FAKE_LOG", "")

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\0" * 32).decode()

SITE = {
    "https://example.test/": {
        "title": "Example home",
        "body": "Welcome to the example page. " + "Lorem ipsum dolor sit amet. " * 120,
        "els": [
            {"kind": "a", "label": "About us", "href": "/about"},
            {"kind": "a", "label": "Elsewhere", "href": "https://other.test/x"},
            {"kind": "a", "label": "Mail me", "href": "mailto:a@b.test"},
            {"kind": "input[text]", "label": "Search", "name": "q"},
            {"kind": "button", "label": "Go", "form": "https://example.test/search"},
            {"kind": "button", "label": "Send away", "form": "https://other.test/post"},
            {"kind": "select", "label": "Colour", "name": "c"},
            {"kind": "input[password]", "label": "", "name": "pw", "skip": True},
        ],
    },
    "https://example.test/about": {
        "title": "About",
        "body": "About the example. Founded in a shed.",
        "els": [{"kind": "a", "label": "Home", "href": "/"}],
    },
    "https://example.test/search": {
        "title": "Results",
        "body": "Results for your search.",
        "els": [],
    },
    "https://example.test/login": {
        "title": "Sign in",
        "body": "Please sign in to continue.",
        "els": [{"kind": "input[text]", "label": "Email", "name": "email"},
                {"kind": "input[password]", "label": "Password", "name": "pw"},
                {"kind": "button", "label": "Sign in", "form": "https://example.test/session"}],
    },
    "https://other.test/x": {"title": "Other", "body": "Another site.", "els": []},
    "https://other.test/post": {"title": "Posted", "body": "Posted.", "els": []},
    "https://challenge.test/": {"title": "Just a moment...",
                                "body": "Checking your browser before accessing challenge.test.",
                                "els": []},
    "https://busy.test/": {
        "title": "Busy",
        "body": "Lots of things.",
        "els": [{"kind": "button", "label": "Same", "form": "https://busy.test/a"},
                {"kind": "button", "label": "Same", "form": "https://busy.test/b"}],
    },
}

state = {"url": "about:blank", "history": [], "values": {}}


def log(event):
    if LOG:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")


def esc(s):
    """Rust's {:?} on a string."""
    out = []
    for ch in s:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 32:
            out.append("\\u{%x}" % ord(ch))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def private(url):
    return bool(re.match(r"https?://(127\.|10\.|192\.168\.|localhost|169\.254\.|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.)", url))


def page():
    if MODE == "captcha":
        return SITE["https://challenge.test/"]
    return SITE.get(state["url"], {"title": "", "body": "", "els": []})


def elements():
    return [e for e in page()["els"] if not e.get("skip")]


def text(s, is_error=False):
    r = {"content": [{"type": "text", "text": s}]}
    if is_error:
        r["isError"] = True
    return r


def go(url):
    state["history"].append(state["url"])
    state["url"] = url


def call(name, a):
    els = elements()
    if name == "browser_navigate":
        url = a.get("url", "")
        if url.startswith("file:"):
            return text("Error: file:// navigation is disabled for MCP", True)
        if url.startswith("data:"):
            state["url"] = url
            SITE[url] = {"title": "Jarvis check",
                         "body": "Hello from a test page",
                         "els": [{"kind": "input[text]", "label": "Search", "name": "q"}]}
            return text(f'Navigated to {url} — "Jarvis check"')
        if private(url) and MODE == "visit_private":
            state["url"] = url
            SITE[url] = {"title": "x", "body": "check-page-marker", "els": []}
            return text(f'Navigated to {url} — "x"')
        if private(url):
            return text("Error: request blocked: address is private or loopback", True)
        if url not in SITE:
            return text("Error: could not load " + url, True)
        go(url)
        return text(f'Navigated to {url} — "{page()["title"]}"')
    if name == "browser_snapshot":
        n = a.get("max_chars", 4000)
        body = page()["body"].strip()
        if MODE == "big":
            body = "x" * 200000
            sys.stdout.write("x" * 13_000_000 + "\n")
            sys.stdout.flush()
        if len(body) > n:
            body = body[:n] + f"\n...(truncated, {len(body) - n} more chars)"
        tail = (f"\n\n{len(els)} interactive element(s) registered. Call browser_interactive_"
                f"elements to list, or pass `ref` to browser_click/browser_fill/browser_type."
                if els else "")
        return text(f"URL: {state['url']}\nTitle: {page()['title']}\n\n{body}{tail}")
    if name == "browser_interactive_elements":
        if not els:
            return text("No interactive elements on this page.")
        lines = []
        for i, e in enumerate(els[: a.get("limit", 100)], 1):
            label = e["label"]
            det = f" name={esc(e['name'])}" if e.get("name") else ""
            lines.append(f"ref=e{i:<4} {e['kind']:<22} {esc(label)}{det}")
        return text("\n".join(lines))
    if name in ("browser_click", "browser_fill", "browser_get_attribute", "browser_select_option"):
        ref = a.get("ref")
        if ref is None and a.get("selector"):
            m = re.search(r'data-obscura-ref="(e\d+)"', a["selector"])
            ref = m.group(1) if m else None
        m = re.fullmatch(r"e(\d+)", str(ref or ""))
        if not m or not (1 <= int(m.group(1)) <= len(els)):
            return text(f"Error: unknown ref '{ref}'; call browser_snapshot first", True)
        e = els[int(m.group(1)) - 1]
        if name == "browser_click":
            if e["kind"] == "a":
                href = e["href"]
                if href.startswith("/"):
                    href = "https://example.test" + href
                if href.startswith("mailto:"):
                    return text(f"Clicked '{ref}'")
                if href in SITE:
                    go(href)
            elif e.get("form"):
                if e["form"] in SITE:
                    go(e["form"])
            return text(f"Clicked '{ref}'")
        if name == "browser_fill":
            state["values"][e["label"] or e.get("name", "")] = a.get("value", "")
            return text("Filled with value")
        if name == "browser_select_option":
            state["values"][e["label"]] = a.get("value", "")
            return text(f"Selected '{a.get('value')}'")
        attr = a.get("attribute")
        if attr == "href":
            return text(e.get("href", ""))
        if attr == "value":
            return text(state["values"].get(e["label"] or e.get("name", ""), ""))
        return text("")
    if name == "browser_detect_forms":
        forms = {}
        for i, e in enumerate(els, 1):
            if e.get("form"):
                forms.setdefault(e["form"], []).append({"tag": "button", "type": "submit",
                                                        "ref": f"e{i}"})
        if not forms:
            return text("No forms found.")
        return text(json.dumps([{"index": k, "action": act, "method": "get", "fields": f}
                                for k, (act, f) in enumerate(forms.items())], indent=2))
    if name == "browser_links":
        out = []
        for e in els:
            if e["kind"] == "a":
                out.append(json.dumps({"text": e["label"], "href": e["href"]}))
        return text("\n".join(out) or "No links found.")
    if name == "browser_markdown":
        return text("# " + page()["title"] + "\n\n" + page()["body"][: a.get("max_chars", 4000)])
    if name == "browser_screenshot":
        return {"content": [{"type": "image", "data": PNG, "mimeType": "image/png"}]}
    if name == "browser_back":
        if state["history"]:
            state["url"] = state["history"].pop()
        return text("Went back")
    if name == "browser_wait_for_text":
        return text("found")
    if name == "browser_close":
        state["url"] = "about:blank"
        return text("closed")
    return text(f"Error: Unknown tool: {name}", True)


def main():
    log({"start": True, "argv": sys.argv[1:], "env": sorted(os.environ)})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if "id" not in msg:
            continue
        method, params, rid = msg.get("method"), msg.get("params") or {}, msg["id"]
        if method == "initialize":
            res = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                   "serverInfo": {"name": "obscura-mcp", "version": "0.0.0-test"}}
        elif method == "tools/call":
            log({"call": params.get("name"), "args": params.get("arguments")})
            if MODE == "hang":
                time.sleep(3600)
            res = call(params.get("name"), params.get("arguments") or {})
        else:
            res = {}
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": res}) + "\n")
        sys.stdout.flush()
        if MODE == "die" and method == "initialize":
            sys.exit(0)


if __name__ == "__main__":
    main()
