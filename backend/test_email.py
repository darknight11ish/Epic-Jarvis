"""jarvis_email.py: reads the owner's own IMAP inbox, and the promise that
`plan()` cannot touch the network and `run()` cannot be tricked into it.

    python3 test_email.py
"""
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _where import BACKEND, REPO  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_email as E

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class NoNetwork:
    def __enter__(self):
        self.real = socket.socket.connect

        def boom(*a, **k):
            raise AssertionError("a socket was opened")

        socket.socket.connect = boom
        return self

    def __exit__(self, *a):
        socket.socket.connect = self.real
        return False


def with_env(host=None, port=None, user=None, password=None, mailbox=None):
    class _Ctx:
        def __enter__(self2):
            keys = (E.HOST_ENV, E.PORT_ENV, E.USER_ENV, E.PASSWORD_ENV, E.MAILBOX_ENV)
            self2.saved = {k: os.environ.get(k) for k in keys}
            for k, v in zip(keys, (host, port, user, password, mailbox)):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            return self2

        def __exit__(self2, *a):
            for k, v in self2.saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            return False
    return _Ctx()


def raw_message(from_="Alice <alice@example.com>", subject="Hello",
                 date="Tue, 15 Sep 2026 12:00:00 +0000",
                 body="Just checking in about the thing we discussed.\n"
                      "Let me know if this works for you."):
    return (
        f"From: {from_}\r\n"
        f"Subject: {subject}\r\n"
        f"Date: {date}\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        f"{body}\r\n"
    ).encode("utf-8")


# ── plan(): opens no socket, refuses cleanly with nothing configured ─────

with with_env(host=None):
    with NoNetwork():
        p_empty = E.plan(10)
    check("no host configured -> not configured", not p_empty.configured)
    text = E.describe(p_empty)
    check("describe() says why, sends nothing",
          "not set" in text and "Nothing would be sent" in text)

with with_env(host="mail.example.com"):
    with NoNetwork():
        p = E.plan(10, unread_only=True)
    check("plan() opens no socket", True)
    check("a plan is built once the host is configured", p.configured)
    check("default port is 993", p.port == 993)
    check("default mailbox is INBOX", p.mailbox == "INBOX")
    check("unread_only maps to the UNSEEN criterion", p.criterion == "UNSEEN")
    check("unread_only=False maps to ALL", E.plan(10, unread_only=False).criterion == "ALL")
    check("limit is clamped above the cap",
          E.plan(500).limit == E._MAX_MESSAGES)
    check("limit is clamped below 1", E.plan(0).limit == 1)

with with_env(host="mail.example.com", port="143", mailbox="Archive"):
    p = E.plan(5)
    check("a custom port is read from the environment", p.port == 143)
    check("a custom mailbox is read from the environment", p.mailbox == "Archive")

# ── describe(): the literal connection, never a summary of it ────────────

with with_env(host="mail.example.com", user=None):
    text = E.describe(E.plan(7))
    check("describe() prints the literal host and port", "mail.example.com:993" in text)
    check("describe() prints the mailbox", "INBOX" in text)
    check("unauthenticated calls this out rather than staying silent",
          "No credentials are configured" in text)
    check("describe() states the preview cap plainly",
          str(E._MAX_PREVIEW_CHARS) in text)
    check("describe() says full bodies are never read",
          "Full message bodies" in text)

with with_env(host="mail.example.com", user="alice", password="hunter2"):
    text = E.describe(E.plan(7))
    check("authenticated() is true once a username is set", E.authenticated())
    check("describe() says a credential will be sent, never what it is",
          "with the configured" in text and "hunter2" not in text)

# ── run(): refuses without approval, parses without one extra socket ─────

with with_env(host="mail.example.com"):
    p = E.plan(5)

    unapproved = E.run(p)
    check("run() without approval does nothing", unapproved["ok"] is False)

    calls = []

    def fake_fetch(plan_obj):
        calls.append(plan_obj)
        return [raw_message(), raw_message(subject="Second one", from_="Bob <bob@example.com>")]

    out = E.run(p, fetch_messages=fake_fetch, approved=True)
    check("run() calls fetch_messages exactly once", len(calls) == 1)
    check("run() succeeds when fetch succeeds", out["ok"] is True)
    check("both messages are parsed", len(out["messages"]) == 2)
    check("From is decoded correctly", out["messages"][0]["from"] == "Alice <alice@example.com>")
    check("Subject is decoded correctly", out["messages"][1]["subject"] == "Second one")
    check("a plain-text preview is extracted",
          "checking in about the thing" in out["messages"][0]["preview"])

    def failing_fetch(plan_obj):
        raise ConnectionRefusedError("connection refused")

    failed = E.run(p, fetch_messages=failing_fetch, approved=True)
    check("a connection failure is reported, not raised", failed["ok"] is False)
    check("the failure reason is legible", "connection refused" in failed["reason"])

# ── the preview: capped, plain-text only, HTML-only gets nothing ─────────

with with_env(host="mail.example.com"):
    p = E.plan(5)
    long_body = "word " * 500  # far past _MAX_PREVIEW_CHARS
    out = E.run(p, fetch_messages=lambda _p: [raw_message(body=long_body)], approved=True)
    check("a long body is capped, not sent in full",
          len(out["messages"][0]["preview"]) <= E._MAX_PREVIEW_CHARS)

    html_only = (
        "From: Alice <alice@example.com>\r\n"
        "Subject: Newsletter\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "\r\n"
        "<html><body><h1>Hi</h1></body></html>\r\n"
    ).encode("utf-8")
    out2 = E.run(p, fetch_messages=lambda _p: [html_only], approved=True)
    check("an HTML-only message gets no preview rather than raw markup",
          out2["messages"][0]["preview"] == "")

# ── one bad charset must not break the whole mailbox ──────────────────────

# `errors="replace"` covers bytes that are not valid IN a codec. It does
# nothing at all when the CODEC ITSELF does not exist: a header naming a
# charset Python has never heard of raises LookupError from inside
# .decode(). That escaped _decode, escaped the message loop, and failed the
# entire read - so one malformed header from one sender broke every
# email_check until that message was deleted by hand.

with with_env(host="imap.example.com", user="me@example.com", password="pw"):
    p = E.plan(limit=5)
    hostile = (
        "From: =?unicode?q?Bob?= <bob@example.com>\r\n"
        "Subject: =?definitely-not-a-charset?q?Quarterly_report?=\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Body text.\r\n"
    ).encode("utf-8")
    ordinary = (
        "From: Alice <alice@example.com>\r\n"
        "Subject: Lunch\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "One o'clock?\r\n"
    ).encode("utf-8")

    out = E.run(p, fetch_messages=lambda _p: [hostile, ordinary], approved=True)
    check("an unknown charset does not fail the whole read", out["ok"] is True, repr(out))
    check("both messages still came back", len(out.get("messages", [])) == 2,
          repr(out.get("messages")))
    subjects = [m["subject"] for m in out.get("messages", [])]
    check("the readable part of the bad header survived",
          any("Quarterly" in s for s in subjects), repr(subjects))
    check("CONTROL: the ordinary message beside it is untouched",
          any(s == "Lunch" for s in subjects), repr(subjects))

    # And the decoder itself, directly.
    check("_decode falls back rather than raising LookupError",
          "Bob" in E._decode("=?no-such-charset?q?Bob?="),
          repr(E._decode("=?no-such-charset?q?Bob?=")))


# ── senders(): the From line only, with PEEK, one connection ─────────────
# The morning briefing's "3 unread emails - From Alex, Your Bank and
# GitHub" (the owner's decision of 2026-09-25). The real IMAP conversation
# is run against a stand-in imaplib that records every command, so "nothing
# is marked as read" is a fact about what was sent, not a comment.

import imaplib as _imaplib


class _FakeIMAP:
    made = []

    def __init__(self, host, port, timeout=None, ssl_context=None):
        self.calls = [("connect", host, port, timeout)]
        self.ssl_context = ssl_context
        _FakeIMAP.made.append(self)

    def login(self, user, password):
        self.calls.append(("login",))
        return "OK", [b""]

    def select(self, mailbox, readonly=False):
        self.calls.append(("select", mailbox, readonly))
        return "OK", [b"7"]

    def search(self, charset, criterion):
        self.calls.append(("search", criterion))
        return "OK", [b"3 5 8 9 11 12 20"]

    def fetch(self, msg_id, what):
        self.calls.append(("fetch", msg_id, what))
        names = {b"20": b"Alex <alex@example.com>", b"12": b'"Your Bank" <a@bank.example>',
                 b"11": b"noreply@github.com", b"9": b"Alex <alex@example.com>",
                 b"8": b"=?UTF-8?Q?Jos=C3=A9?= <j@example.com>"}
        head = b"From: " + names[msg_id] + b"\r\n\r\n"
        return "OK", [(msg_id + b" (BODY[HEADER.FIELDS (FROM)] {%d}" % len(head), head), b")"]

    def close(self):
        self.calls.append(("close",))

    def logout(self):
        self.calls.append(("logout",))


with with_env(host="imap.example.com", user="me@example.com", password="pw"):
    p = E.plan(1)
    check("senders() without approval reads nothing",
          E.senders(p)["ok"] is False and _FakeIMAP.made == [])
    real = _imaplib.IMAP4_SSL
    _imaplib.IMAP4_SSL = _FakeIMAP
    try:
        out = E.senders(p, approved=True)
    finally:
        _imaplib.IMAP4_SSL = real
    conn = _FakeIMAP.made[-1] if _FakeIMAP.made else None
    calls = conn.calls if conn else []
    check("ONE connection", len(_FakeIMAP.made) == 1, len(_FakeIMAP.made))
    import ssl as _ssl
    ctx = conn.ssl_context if conn else None
    check("the mail server's certificate and name are checked (imaplib alone checks "
          "neither)", ctx is not None and ctx.verify_mode == _ssl.CERT_REQUIRED
          and ctx.check_hostname is True, ctx)
    local = E.tls_context("127.0.0.1")
    check("... except a mail program on this PC itself (a bridge's own certificate)",
          local.verify_mode == _ssl.CERT_NONE and E.tls_context("imap.example.com").verify_mode
          == _ssl.CERT_REQUIRED)
    check("the mailbox is opened read-only", ("select", "INBOX", True) in calls, calls)
    fetches = [c for c in calls if c[0] == "fetch"]
    check("only the newest five, newest first",
          [c[1] for c in fetches] == [b"20", b"12", b"11", b"9", b"8"], fetches)
    check("each asks for the From line only, with PEEK (nothing marked as read)",
          all(c[2] == "(BODY.PEEK[HEADER.FIELDS (FROM)])" for c in fetches), fetches)
    check("nothing else is asked: no STORE, no flags, no body",
          {c[0] for c in calls} == {"connect", "login", "select", "search", "fetch", "close",
                                    "logout"}, calls)
    check("the count, and the names - decoded, each once, newest first; no name: the address",
          out.get("ok") is True and out["count"] == 7 and out["looked_at"] == 5
          and out["senders"] == ["Alex", "Your Bank", "noreply@github.com", "José"], out)

    def refused(plan_obj, newest):
        raise _imaplib.IMAP4.error("LOGIN failed for me@example.com")
    bad = E.senders(p, fetch=refused, approved=True)
    check("a failure is its exception's NAME only - never the server's words",
          bad["ok"] is False and "me@example.com" not in bad["reason"], bad)
    check("a From line with no name shows the whole address, not just 'noreply'",
          E.sender_name(b"From: noreply@github.com\r\n\r\n") == "noreply@github.com")
    check("a name with a direction-override character loses it",
          E.sender_name("=?utf-8?q?Pay=E2=80=AEnow?= <x@example.com>") == "Pay now")
    check("an empty From line gives nothing", E.sender_name(b"From: \r\n\r\n") == "")

print()
if FAILED:
    print(f"{len(FAILED)} failed: {', '.join(FAILED)}")
    sys.exit(1)
print(f"{len(PASSED)} passed - the inbox is read-only, and reads nothing without a socket to prove it")
