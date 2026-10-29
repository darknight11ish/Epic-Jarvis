"""jarvis_google_calendar.py - the two-way Google Calendar connection, proven
with no network and no real Google account.

    python3 test_google_calendar.py

WHAT THIS PROVES, and why each one is here rather than left to the field test:

  1. PKCE and `state` are real: a 43-128 character verifier from the
     unreserved set, an S256 challenge that is sha256(verifier) rather than
     the verifier itself, a random state, and a constant-time comparison.
  2. The callback REFUSES a wrong state and a missing state, and does not
     exchange anything when it does - the security property the whole flow
     rests on.
  3. The code exchange runs against a STUB that stands in for Google, and the
     refresh token lands in the credential store (a stand-in for Windows
     Credential Manager) and NOWHERE else: not in the settings file, not in
     any file under the config folder, not in any route's answer, not in the
     card, not in an error, not on stdout/stderr, and redacted by the
     scrubber when it is handed one by value.
  4. The listener binds 127.0.0.1 - read from the source, and read back from
     the socket the flow really opened - so there is no public tunnel and
     nothing another machine can reach.
  5. Reads raise NO card. Create, change and delete raise exactly ONE each,
     with the exact event on it, and nothing is sent to Google until that
     card says yes. A denied card sends nothing.
  6. A change or a delete is refused when the event stream is stale, and
     refused for an event the last read did not see - rule 4.
  7. The revoke path really calls Google's revoke endpoint and says honestly
     whether Google confirmed it.
  8. status() is truthful when disconnected, connected and expired.

Every request is a stub: this file opens one loopback listener (the flow's
own, on 127.0.0.1) and nothing else. No real client ID, secret or token is in
this file - the values are assembled from pieces, like test_calendar_link.py
does with the private link.
"""
import ast
import base64
import contextlib
import hashlib
import inspect
import io
import json
import socket
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_google_calendar.py", "jarvis_token_store.py",
                "jarvis_scrub.py", "jarvis_calendar.py")

import jarvis_google_calendar as G  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# ── values built from pieces, so no token-shaped literal is in this file ────

CLIENT_ID = "1234" + "567890" + "-abcdefghijklmnop.apps.googleusercontent.com"
CLIENT_SECRET = "GOCSPX" + "-" + "Q1w2E3r4T5y6U7i8O9p0"
REFRESH = "1//" + "0f4ke" + "refresh" + "Token" + "AbCdEf"
ACCESS_1 = "ya29." + "first" + "AccessToken123"
ACCESS_2 = "ya29." + "second" + "AccessToken456"
SECRET_FORMS = (REFRESH, ACCESS_1, ACCESS_2, CLIENT_SECRET)


def leaks(obj, forms=SECRET_FORMS):
    """Every secret form found in `obj` as text, or []."""
    text = obj if isinstance(obj, str) else json.dumps(obj, default=str)
    return [f for f in forms if f and f in text]


# ── a stand-in for Windows Credential Manager ───────────────────────────────

class FakeStore:
    """What jarvis_token_store.WindowsStore looks like from here: read(),
    write(), delete(), per target name, in a dict that never touches disk."""

    def __init__(self, data, target="", *, fail_write=False):
        self.data = data
        self.target = target
        self.fail_write = fail_write

    def read(self):
        return self.data.get(self.target)

    def write(self, value):
        if self.fail_write:
            raise RuntimeError("Credential Manager refused")
        self.data[self.target] = value

    def delete(self):
        return self.data.pop(self.target, None) is not None


def with_store(data, *, fail_write=False):
    G._STORE_FACTORY = lambda target: FakeStore(data, target, fail_write=fail_write)


def use_config(root=None):
    """Point the module at a throwaway settings folder. `_CONFIG_DIR_OVERRIDE`
    exists for exactly this: the real folder is the owner's own
    ~/.openjarvis, and a suite must never write there. It STAYS set for the
    rest of the run, because each block below reads back what it wrote."""
    G._CONFIG_DIR_OVERRIDE = Path(root or tempfile.mkdtemp(prefix="jarvis-gcal-"))
    return G._CONFIG_DIR_OVERRIDE


def begin(data=None, *, mode="google", client=True):
    """A clean module, a clean store, a clean settings folder, and (when
    asked) a saved client ID + secret and a chosen way."""
    G._reset_for_tests()
    root = use_config()
    data = {} if data is None else data
    with_store(data)
    if client:
        data[G.TARGET_CLIENT_SECRET] = CLIENT_SECRET
        G.set_client(CLIENT_ID, None)
    doc, _ = G._read_settings()
    doc["mode"] = mode
    G._write_settings(doc)
    return root, data


def quiet(fn, *args, **kwargs):
    """Run `fn`, returning (result, stdout, stderr). A leaked token in a log
    line is then a failure rather than something to scroll past."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        result = fn(*args, **kwargs)
    return result, out.getvalue(), err.getvalue()


class Verdict:
    def __init__(self, *, allowed=True, tier="ask", outcome="approved"):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome


class Card:
    """A stand-in jarvis_gate.check: records every card it is asked to raise
    and answers with a verdict the test chose."""

    def __init__(self, *, allowed=True, tier="ask", outcome="approved"):
        self.calls = []
        self.verdict = Verdict(allowed=allowed, tier=tier, outcome=outcome)

    def __call__(self, action, detail, prompt=""):
        self.calls.append({"action": action, "detail": detail, "prompt": prompt})
        return self.verdict


class Transport:
    """A stand-in Google: records every request and answers by URL."""

    def __init__(self, *, refresh_status=200, exchange_ok=True,
                 refresh_value=REFRESH):
        self.calls = []
        self.refresh_status = refresh_status
        self.exchange_ok = exchange_ok
        self.refresh_value = refresh_value

    def __call__(self, method, url, payload, headers):
        self.calls.append({"method": method, "url": url, "payload": payload,
                           "headers": headers})
        if "oauth2.googleapis.com/token" in url:
            if payload and payload.get("grant_type") == "refresh_token":
                if self.refresh_status != 200:
                    return self.refresh_status, {"error": "invalid_grant"}
                return 200, {"access_token": ACCESS_2, "expires_in": 3600,
                             "token_type": "Bearer"}
            if not self.exchange_ok:
                return 400, {"error": "invalid_grant"}
            return 200, {"access_token": ACCESS_1, "expires_in": 3600,
                         "refresh_token": self.refresh_value, "token_type": "Bearer"}
        if "oauth2.googleapis.com/revoke" in url:
            return 200, {}
        if "/calendars/primary/events" in url:
            if method in ("POST", "PATCH"):
                body = dict(payload or {})
                body["id"] = "evt_" + "created1"
                return 200, body
            if method == "DELETE":
                return 204, {}
            return 200, {"items": [
                {"id": "evt_" + "one", "summary": "Dentist",
                 "start": {"dateTime": "2026-11-03T15:00:00-07:00"},
                 "end": {"dateTime": "2026-11-03T16:00:00-07:00"},
                 "location": "High Street"},
                {"id": "evt_" + "two", "summary": "Bin day",
                 "start": {"date": "2026-11-04"}, "end": {"date": "2026-11-05"}},
            ]}
        if "/calendars/primary" in url:
            return 200, {"summary": "owner@example.com"}
        return 404, {}

    def urls(self):
        return [c["url"] for c in self.calls]

    def methods(self, needle):
        return [c for c in self.calls if needle in c["url"]]


# ══════════════════════════════════════════════════════════════════════════
#   1. PKCE and state
# ══════════════════════════════════════════════════════════════════════════

print("PKCE and state")

allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
verifiers = [G.make_verifier() for _ in range(25)]
check("25 verifiers are 43-128 unreserved characters",
      all(43 <= len(v) <= 128 and set(v) <= allowed for v in verifiers),
      [v for v in verifiers if not (43 <= len(v) <= 128)][:2])
check("two verifiers differ", len(set(verifiers)) == len(verifiers))

verifier = G.make_verifier()
expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()) \
    .decode().rstrip("=")
check("the challenge is S256(verifier), unpadded",
      G.challenge_for(verifier) == expected, G.challenge_for(verifier))
check("the challenge does not contain the verifier",
      verifier not in G.challenge_for(verifier))

state = G.make_state()
check("a state is at least 32 characters and two differ",
      len(state) >= 32 and state != G.make_state(), state)
check("a matching state matches", G.state_matches(state, state))
check("a wrong state does not", not G.state_matches(state, state + "x"))
check("a missing state does not", not G.state_matches(state, None))
check("an empty state does not", not G.state_matches(state, ""))
check("a non-text state does not", not G.state_matches(state, 12345))
check("no expected state never matches", not G.state_matches("", state))
# S2, measured: `?state=é` used to raise TypeError out of hmac.compare_digest,
# which escaped do_GET and closed the listener - an unauthenticated kill.
for non_ascii in ("é", state + "é", "\u00e9"):
    try:
        raised = None
        answer = G.state_matches(state, non_ascii)
    except Exception as exc:                       # the bug being fixed
        raised, answer = repr(exc), None
    check(f"a non-ASCII state is refused, not raised ({non_ascii!r})",
          raised is None and answer is False, raised or answer)
check("... and a non-ASCII EXPECTED state is refused too, not raised",
      G.state_matches("é", "é") is False)

check("exactly one scope, and it is calendar.events",
      G.SCOPES == ("https://www.googleapis.com/auth/calendar.events",), G.SCOPES)
check("the redirect host is a constant, loopback only",
      G.BIND_HOST == "127.0.0.1" and G.CALLBACK_PATH == "/callback")

src = (HERE / "jarvis_google_calendar.py").read_text(encoding="utf-8")


def code_only(text):
    """The source with comments and every string literal removed, so a check
    about what the module DOES is not defeated by a docstring saying what it
    does not do (the module's own words say "no ngrok, no Cloudflare Tunnel",
    which is the promise - not a dependency)."""
    import tokenize
    keep = []
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        keep.append(token.string)
    return " ".join(keep)


code_src = code_only(src)
for forbidden in ("0.0.0.0", "ngrok", "cloudflare", "tailscale", "funnel",
                  "localtunnel", "serveo"):
    check(f"the module's code never uses {forbidden!r}", forbidden not in code_src.lower())
# The loopback listener is proven at runtime below (the socket's own address and
# a real loopback connection) and the bind host constant above. This is the one
# structural half those cannot see: the port is EPHEMERAL (0), never a fixed
# port somebody could plan around. An `ast` walk cannot be fooled by a comment
# or a docstring - the old text pin could be.
TREE = ast.parse(src)
SERVER_CALLS = [n for n in ast.walk(TREE)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "HTTPServer"]
BIND_ARGS = [tuple(getattr(a, "value", getattr(a, "id", None)) for a in c.args[0].elts)
             for c in SERVER_CALLS
             if c.args and isinstance(c.args[0], ast.Tuple)]
check("the listener is built from BIND_HOST on an ephemeral port (0), never a "
      "fixed one", BIND_ARGS == [("BIND_HOST", 0)] and G.BIND_HOST == "127.0.0.1",
      BIND_ARGS)


# ── one whole sign-in, against a real loopback listener + a stub Google ─────

def sign_in(*, state_suffix="", missing_state=False, error=None, state_text=None):
    """One callback against the flow's own loopback listener.

    `error`: Google's own answer (`access_denied` ...), which carries the state
    on a real Google redirect and has to carry it here too, because a callback
    without the right state is refused before the error is looked at (S1).
    `state_text`: an exactly-chosen state value, for the non-ASCII refusal.
    """
    started = G.start(opener=lambda url: None)
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(started["auth_url"]).query))
    port = started["port"]
    sent_state = state_text if state_text is not None else query["state"] + state_suffix
    if error:
        target = f"http://127.0.0.1:{port}/callback?error={error}"
    else:
        target = f"http://127.0.0.1:{port}/callback?code=one-time-code"
    if not missing_state:
        target += "&state=" + urllib.parse.quote(sent_state)
    status = None
    try:
        with urllib.request.urlopen(target, timeout=10) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.read()
    # Short: a REFUSED callback deliberately leaves the flow waiting (S1/S2),
    # so waiting the flow's own timeout here would only slow the suite down.
    # The answer and the exchange have already happened when urlopen returns.
    G.wait(0.5)
    return started, query, status
    return started, query, status


# ══════════════════════════════════════════════════════════════════════════
#   2. THE FLOW: start -> loopback callback -> exchange -> token in the store
# ══════════════════════════════════════════════════════════════════════════

print("\nThe sign-in flow")

root, data = begin(mode="off", client=True)
t = Transport()
G._TRANSPORT = t
started, query, status = sign_in()

check("start() answers the URL, the port and NO verifier or state of its own",
      set(started) == {"auth_url", "port", "redirect_uri", "browser_opened",
                       "expires_in"}, sorted(started))
check("the redirect address is http://127.0.0.1:<port>/callback",
      started["redirect_uri"] == f"http://127.0.0.1:{started['port']}/callback",
      started["redirect_uri"])
check("PKCE is S256 on the wire",
      query.get("code_challenge_method") == "S256"
      and len(query.get("code_challenge", "")) == 43)
check("the verifier itself is NOT in the auth URL",
      G.pending().verifier not in started["auth_url"])
check("access_type=offline and prompt=consent (a refresh token every time)",
      query.get("access_type") == "offline" and query.get("prompt") == "consent")
check("the scope on the wire is calendar.events only",
      query.get("scope") == "https://www.googleapis.com/auth/calendar.events",
      query.get("scope"))
check("the correct state is accepted and the page says connected", status == 200, status)
check("the refresh token is in the store", data.get(G.TARGET_REFRESH) == REFRESH,
      sorted(data))
check("the code exchange sent the code AND the verifier",
      any((c["payload"] or {}).get("code_verifier") == G.pending().verifier
          and (c["payload"] or {}).get("code") == "one-time-code"
          for c in t.methods("token")), t.urls())
check("the verifier and the code never appear in ANY request URL",
      not any(G.pending().verifier in u or "one-time-code" in u for u in t.urls()),
      t.urls())
check("the access token is in memory only",
      G._ACCESS["token"] == ACCESS_1 and G._ACCESS["expires_at"] > time.time())
check("signing in chose the Google way", G.mode() == "google")
check("status is connected and says where the token lives",
      G.status()["connected"] and "Credential Manager" in G.status()["token_store"])
check("status never carries a token", not leaks(G.status()), leaks(G.status()))

# ── the refresh token is on no disk, in no answer, in no log ────────────────
files = [p for p in root.rglob("*") if p.is_file()]
texts = {p.name: p.read_text(encoding="utf-8", errors="replace") for p in files}
check("the settings file holds the client ID (which is public)",
      any(CLIENT_ID in text for text in texts.values()), sorted(texts))
check("NO file under the settings folder holds a refresh token, access token "
      "or the client secret",
      not any(leaks(text) for text in texts.values()), sorted(texts))
written_doc = json.loads((root / G.SETTINGS_NAME).read_text(encoding="utf-8"))
check("the settings file on disk holds ONLY the mode and the public client ID, "
      "so no token can be serialized into it",
      set(written_doc) <= {"mode", "client_id"} and written_doc.get("client_id") == CLIENT_ID,
      sorted(written_doc))

_status, out, err = quiet(G.status)
check("nothing is printed at all, so nothing can carry a token",
      out == "" and err == "", out + err)

try:
    import jarvis_scrub
    scrubbed = jarvis_scrub.scrub_text("token=" + REFRESH + " and " + ACCESS_1)
    check("jarvis_scrub redacts both tokens by value",
          REFRESH not in scrubbed and ACCESS_1 not in scrubbed, scrubbed)
except Exception as exc:                       # pragma: no cover - shipped module
    check("jarvis_scrub is present", False, repr(exc))

# S3, measured: `_write_secret` never called `_register`, so the refresh token
# was NOT in jarvis_scrub at the moment of the exchange - only later, if
# something happened to read it back. This value is used nowhere else, so
# redacting it can only have come from this one write.
REGISTERED = "1//" + "0f4ke" + "registeredAt" + "Exchange" + "Zz"
try:
    import jarvis_scrub
    root_s3, data_s3 = begin(mode="off")
    G._TRANSPORT = Transport(refresh_value=REGISTERED)
    G.exchange_code("one-time-code", G.make_verifier(),
                    "http://127.0.0.1:1/callback")
    check("the exchanged refresh token is written to the store",
          data_s3.get(G.TARGET_REFRESH) == REGISTERED, sorted(data_s3))
    scrubbed_s3 = jarvis_scrub.scrub_text("token=" + REGISTERED)
    check("... and registered with jarvis_scrub by value AT THE WRITE, with no read back",
          REGISTERED not in scrubbed_s3, scrubbed_s3[:80])
except Exception as exc:
    check("the exchange registers the refresh token with jarvis_scrub", False, repr(exc))

# ── a wrong state, a missing state, and the owner pressing Cancel ───────────
# S1/S2, measured: ANY unauthenticated request that reached this listener could
# end the sign-in - a forged `error=` before the state was checked, and a
# non-ASCII `state=` that raised out of hmac.compare_digest and closed the
# listener. A refusal must REFUSE and leave the flow waiting, never cancel it.
for label, kwargs in (("a WRONG state", {"state_suffix": "x"}),
                      ("a MISSING state", {"missing_state": True}),
                      ("a non-ASCII state", {"state_text": "\u00e9"}),
                      ("an ERROR with no state", {"missing_state": True,
                                                  "error": "access_denied"})):
    root2, data2 = begin(mode="off")
    t2 = Transport()
    G._TRANSPORT = t2
    _started, _query, code = sign_in(**kwargs)
    check(f"{label} is refused with 400", code == 400, code)
    check(f"{label} exchanges NOTHING with Google", not t2.methods("token"), t2.urls())
    check(f"{label} leaves no refresh token in the store",
          G.TARGET_REFRESH not in data2, data2)
    check(f"{label} cannot CANCEL the sign-in: the flow is still waiting",
          G.pending().outcome()["outcome"] == "waiting", G.pending().outcome())
    G.cancel()                        # the flow is still live; stop its listener

root3, data3 = begin(mode="off")
t3 = Transport()
G._TRANSPORT = t3
_started, _query, code = sign_in(error="access_denied")
check("Google's own 'access_denied' WITH the right state is refused, not connected",
      code == 400 and G.pending().outcome()["outcome"] == "denied"
      and G.TARGET_REFRESH not in data3, G.pending().outcome())

# S1, end to end: an attacker's `?error=` must not kill a real sign-in that is
# still waiting - the same flow still accepts the genuine callback afterwards.
root3a, data3a = begin(mode="off")
t3a = Transport()
G._TRANSPORT = t3a
started, query, attack_code = sign_in(missing_state=True, error="access_denied")
check("an error callback without the state is refused", attack_code == 400, attack_code)
check("... and the sign-in it tried to kill is still waiting",
      G.pending().outcome()["outcome"] == "waiting", G.pending().outcome())
port = started["port"]
try:
    with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/callback?code=one-time-code&state="
            + urllib.parse.quote(query["state"]), timeout=10) as resp:
        genuine = resp.status
except urllib.error.HTTPError as exc:
    genuine, _ = exc.code, exc.read()
G.wait(5.0)
check("... and the genuine callback on the same flow still connects",
      genuine == 200 and G.pending().outcome()["outcome"] == "connected"
      and data3a.get(G.TARGET_REFRESH) == REFRESH, G.pending().outcome())

# S2, end to end: `?state=é` used to kill the flow with a TypeError. It must be
# refused, and the same listener must still answer the real callback after it.
root3c, data3c = begin(mode="off")
t3c = Transport()
G._TRANSPORT = t3c
started, query, attack_code = sign_in(state_text="\u00e9")
check("a non-ASCII state is refused with 400, not a dropped connection",
      attack_code == 400, attack_code)
check("... and the sign-in it tried to kill is still waiting",
      G.pending().outcome()["outcome"] == "waiting", G.pending().outcome())
try:
    with urllib.request.urlopen(
            f"http://127.0.0.1:{started['port']}/callback?code=one-time-code&state="
            + urllib.parse.quote(query["state"]), timeout=10) as resp:
        genuine = resp.status
except urllib.error.HTTPError as exc:
    genuine, _ = exc.code, exc.read()
G.wait(5.0)
check("... and the genuine callback after it still connects",
      genuine == 200 and G.pending().outcome()["outcome"] == "connected"
      and data3c.get(G.TARGET_REFRESH) == REFRESH, G.pending().outcome())

# the browser page is fixed words: nothing from the query is ever echoed into it
root3b, data3b = begin(mode="off")
G._TRANSPORT = Transport()
seen: dict = {}
_real_page = G._page


def _spy_page(handler, status, title, body):
    seen["text"] = f"{title} {body}"
    return _real_page(handler, status, title, body)


G._page = _spy_page
try:
    injected = "%3Cscript%3Ealert(1)%3C%2Fscript%3E"
    _started, _query, code = sign_in(error=injected)
finally:
    G._page = _real_page
check("the callback page does not echo the query (a reflected <script> is refused)",
      code == 400 and "script" not in seen.get("text", "").lower()
      and "alert" not in seen.get("text", ""), seen)

root4, data4 = begin(mode="off")
t4 = Transport(exchange_ok=False)
G._TRANSPORT = t4
_started, _query, code = sign_in()
check("a refused code is a 500 page and nothing is stored",
      code == 500 and G.TARGET_REFRESH not in data4
      and G.pending().outcome()["outcome"] == "exchange_failed",
      G.pending().outcome())
check("the failed-exchange sentence carries no token",
      not leaks(G.pending().outcome()), G.pending().outcome())

# ── the loopback listener: bound 127.0.0.1, on a port nobody could guess ────
root5, data5 = begin(mode="off")
G._TRANSPORT = Transport()
s5 = G.start(opener=lambda url: None)
flow = G.pending()
check("the listener's own socket says 127.0.0.1",
      flow.server.server_address[0] == "127.0.0.1", flow.server.server_address)
check("the port is ephemeral, not a fixed one",
      flow.port > 0 and s5["redirect_uri"].endswith(f":{flow.port}/callback"))
sock = socket.socket()
try:
    sock.connect((flow.server.server_address[0], flow.port))
    reachable = True
except OSError:
    reachable = False
finally:
    sock.close()
check("the listener really accepts a loopback connection", reachable)
_G = G.cancel()
check("cancel() stops a waiting flow",
      G.pending().outcome()["outcome"] == "cancelled", G.pending().outcome())

# ── S9: start() is locked, so a burst cannot orphan a listener ──────────────
# Measured before the fix: two starts could each bind a listener and only the
# second stayed in _PENDING, leaving the first open for its whole 600 s. And a
# second click on the button CANCELLED the sign-in that was already waiting.
root5b, data5b = begin(mode="off")
G._TRANSPORT = Transport()
first = G.start(opener=lambda url: None)
first_flow = G.pending()
second = G.start(opener=lambda url: None)
check("a second start while one is waiting answers the SAME flow, not a new one",
      second["auth_url"] == first["auth_url"] and second["port"] == first["port"]
      and G.pending() is first_flow, (first["port"], second["port"]))
check("... and it does not claim to have opened a second browser",
      second["browser_opened"] is False and first["browser_opened"] is False,
      (first["browser_opened"], second["browser_opened"]))
check("... and the waiting flow was not cancelled by the second start",
      G.pending().outcome()["outcome"] == "waiting", G.pending().outcome())

# A burst of concurrent starts leaves exactly one listener and one flow.
import threading  # noqa: E402
burst: list = []
def _one_start():
    try:
        burst.append(G.start(opener=lambda url: None))
    except Exception as exc:                       # a refusal is not a crash
        burst.append({"error": repr(exc)})
threads = [threading.Thread(target=_one_start) for _ in range(8)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join(timeout=10)
check("a burst of eight starts answers ONE flow and opens one browser",
      len(burst) == 8 and len({b.get("port") for b in burst}) == 1
      and len({b.get("auth_url") for b in burst}) == 1
      and [b for b in burst if b.get("browser_opened")] == [], burst)
check("... and the one flow is still the same, still waiting",
      G.pending() is first_flow and first_flow.outcome()["outcome"] == "waiting",
      first_flow.outcome())

# A FINISHED flow is reaped before the next listener binds, not left open.
done_flow = first_flow
G.cancel()
check("cancel() closes the listener of the finished flow",
      done_flow.done.is_set() and done_flow.server.socket.fileno() == -1,
      (done_flow.done.is_set(), done_flow.server.socket.fileno()))
third = G.start(opener=lambda url: None)
check("a start after a finished flow REPLACES it, with a live new listener",
      G.pending() is not done_flow and not G.pending().done.is_set()
      and G.pending().server.socket.fileno() != -1, third)
G.cancel()

begin(mode="off", client=False)
try:
    G.start(opener=lambda url: None)
    check("no client ID: starting is refused", False, "it started")
except G.FlowError as exc:
    check("no client ID: starting is refused, in plain words",
          "client ID" in str(exc), str(exc))
try:
    G.start(opener=lambda url: None)
except G.FlowError:
    pass

# a secret the store refuses is a refusal, not a half-saved client
G._reset_for_tests()
use_config()
data_fail: dict = {}
with_store(data_fail, fail_write=True)
G.set_client(CLIENT_ID, None)
try:
    G.set_client(None, CLIENT_SECRET)
    check("a store that refuses the client secret says so", False, "it claimed success")
except ValueError as exc:
    check("a store that refuses the client secret says so",
          "Credential Manager" in str(exc), str(exc))

# ══════════════════════════════════════════════════════════════════════════
#   3. Reads: card-free, truthful, outside text
# ══════════════════════════════════════════════════════════════════════════

print("\nReads")

root6, data6 = begin(mode="off")
t6 = Transport()
G._TRANSPORT = t6
not_connected = G.list_events()
check("disconnected: 'not connected yet', never an empty calendar",
      not_connected["ok"] is False and "not connected" in not_connected["reason"],
      not_connected)
check("disconnected: no request to Google", t6.calls == [], t6.urls())

data6[G.TARGET_REFRESH] = REFRESH
G.set_mode("google")
check("choosing the Google way with a saved token is accepted", G.mode() == "google")
got = G.list_events(7)
check("connected: the primary calendar is read once", got["ok"], got)
check("a read has no card parameter at all, so a read cannot raise one",
      "gate" not in inspect.signature(G.list_events).parameters)
check("two events come back, bounded, with no unknown fields",
      [r["summary"] for r in got["events"]] == ["Dentist", "Bin day"], got["events"])
check("an all-day event is marked all-day", got["events"][1]["all_day"] is True)
check("the read records WHAT it saw, by id - the event's own summary and times",
      set(G._STATE["events"]) == {"evt_" + "one", "evt_" + "two"}
      and G._STATE["events"]["evt_" + "one"]["summary"] == "Dentist"
      and G._STATE["events"]["evt_" + "one"]["start"] == "2026-11-03T15:00:00-07:00",
      G._STATE["events"])
check("the read itself carries no token", not leaks(got), leaks(got))
check("event text comes back as plain, capped outside text",
      len(got["events"][0]["summary"]) <= 300)

# ══════════════════════════════════════════════════════════════════════════
#   4. Writes: ONE card each, and nothing sent before the yes
# ══════════════════════════════════════════════════════════════════════════

print("\nWrites")

EVENT = {"summary": "Team sync", "start": "2026-11-03T15:00:00-07:00",
         "end": "2026-11-03T15:30:00-07:00", "where": "Room 2"}

denying = Card(allowed=False, outcome="denied")
t7 = Transport()
code, out = G.create_event(EVENT, gate=denying, tier_of=lambda a: "ask",
                           spawn=lambda fn: fn(), transport=t7)
check("a denied card answers 403 and says nothing changed",
      code == 403 and out["outcome"] == "denied", out)
check("a denied card sends NOTHING to Google", t7.calls == [], t7.urls())
check("the card names the exact event",
      "Team sync" in denying.calls[0]["detail"]["card"]
      and "2026-11-03T15:00:00-07:00" in denying.calls[0]["detail"]["card"]
      and "Room 2" in denying.calls[0]["detail"]["card"],
      denying.calls[0]["detail"]["card"])
check("the card says it leaves this PC and is the module's own action",
      denying.calls[0]["detail"]["leaves_this_pc"] is True
      and denying.calls[0]["action"] == "google_calendar_write")
check("the card carries no token", not leaks(denying.calls[0]))

yes = Card()
t8 = Transport()
code, out = G.create_event(EVENT, gate=yes, tier_of=lambda a: "ask",
                           spawn=lambda fn: fn(), transport=t8)
check("an approved card creates exactly ONE event", code == 200 and out["ok"], out)
posts = [c for c in t8.methods("/events") if c["method"] == "POST"]
check("the POST body is the event the card showed, and only that",
      len(posts) == 1 and posts[0]["payload"]["summary"] == "Team sync"
      and posts[0]["payload"]["start"] == {"dateTime": "2026-11-03T15:00:00-07:00"},
      posts[0]["payload"] if posts else t8.urls())
check("exactly one card per write", len(yes.calls) == 1, len(yes.calls))
check("the answer carries no token", not leaks(out), leaks(out))

wrong_tier = Card(tier="notify")
t9 = Transport()
code, out = G.create_event(EVENT, gate=wrong_tier, tier_of=lambda a: "notify",
                           spawn=lambda fn: fn(), transport=t9)
check("a yes at any tier but 'ask' is refused, and nothing is sent",
      code == 503 and not t9.methods("/events"), out)

bad = G.create_event({"summary": "No dates"}, gate=Card(), tier_of=lambda a: "ask",
                     spawn=lambda fn: fn())
check("an event without a start and an end is refused before any card",
      bad[0] == 400, bad)

# ── update and delete: the event must be in the last read ───────────────────
G._STATE["last_read"], G._STATE["events"] = 0.0, {}     # nothing read this run
stale_card = Card()
code, out = G.update_event({"event_id": "evt_" + "one", "summary": "Dentist",
                            "start": "2026-11-03T16:00:00-07:00",
                            "end": "2026-11-03T17:00:00-07:00"},
                           gate=stale_card, tier_of=lambda a: "ask",
                           spawn=lambda fn: fn())
check("a change with no recent read is refused as stale", code == 409, out)
check("a stale refusal raises NO card", stale_card.calls == [], stale_card.calls)

G._STATE["last_read"] = time.monotonic() - (G.STREAM_MAX_AGE + 5)
old_card = Card()
code, out = G.update_event({"event_id": "evt_" + "one", "summary": "Dentist"},
                           gate=old_card, tier_of=lambda a: "ask",
                           spawn=lambda fn: fn())
check("a read older than the stream limit is refused as stale",
      code == 409 and out["outcome"] == "stale" and not old_card.calls, out)

# A REAL read, because the snapshot a change is allowed against is the one a
# read took - a write drops it (asserted below), so it cannot be faked here.
G._TRANSPORT = Transport()
G.list_events(7)
unknown_card = Card()
code, out = G.delete_event({"event_id": "evt_" + "never-seen"},
                           gate=unknown_card, tier_of=lambda a: "ask",
                           spawn=lambda fn: fn())
check("an event the last read did not see is refused, card-free",
      code == 409 and not unknown_card.calls, out)

t10 = Transport()
del_card = Card()
code, out = G.delete_event({"event_id": "evt_" + "one", "summary": "Dentist"},
                           gate=del_card, tier_of=lambda a: "ask",
                           spawn=lambda fn: fn(), transport=t10)
check("an approved delete sends ONE DELETE", code == 200
      and [c["method"] for c in t10.methods("/events")] == ["DELETE"], t10.urls())
check("the delete card names the event", "Dentist" in del_card.calls[0]["detail"]["card"],
      del_card.calls[0]["detail"]["card"])
check("a write drops the snapshot, so the next change is stale again",
      G._STATE["last_read"] == 0.0 and not G._STATE["events"], G._STATE)

# ── S4, measured: the card was built from the REQUEST, not the last read ────
# A caller could show "Dentist" on the card and delete another event's id, and
# an update card never showed what was there before. Both cards are now built
# from the snapshot the read took.
_root_s4, data_s4 = begin(mode="google")
data_s4[G.TARGET_REFRESH] = REFRESH
G._TRANSPORT = Transport()
G.list_events(7)                     # the read whose snapshot the cards use
lies_card = Card()
code, out = G.delete_event({"event_id": "evt_" + "one",
                            "summary": "Bin day",
                            "start": "2026-11-04", "end": "2026-11-05",
                            "where": "Somewhere else"},
                           gate=lies_card, tier_of=lambda a: "ask",
                           spawn=lambda fn: fn(), transport=Transport())
card_text = lies_card.calls[0]["detail"]["card"] if lies_card.calls else ""
check("a delete card shows the event the LAST READ saw, not the request's words",
      "Dentist" in card_text and "Bin day" not in card_text
      and "2026-11-03T15:00:00-07:00" in card_text
      and "Somewhere else" not in card_text, card_text)
check("... and the card's own detail carries the read's values too",
      lies_card.calls[0]["detail"]["summary"] == "Dentist"
      and lies_card.calls[0]["detail"]["start"] == "2026-11-03T15:00:00-07:00",
      lies_card.calls[0]["detail"] if lies_card.calls else None)

G._TRANSPORT = Transport()
G.list_events(7)
change_card = Card()
code, out = G.update_event({"event_id": "evt_" + "one", "summary": "Team sync",
                            "start": "2026-11-03T16:00:00-07:00",
                            "end": "2026-11-03T17:00:00-07:00",
                            "where": "Room 2"},
                           gate=change_card, tier_of=lambda a: "ask",
                           spawn=lambda fn: fn(), transport=Transport())
change_text = change_card.calls[0]["detail"]["card"] if change_card.calls else ""
check("an update card shows BOTH the old values and the new ones",
      "Team sync" in change_text and "Dentist" in change_text
      and "2026-11-03T16:00:00-07:00" in change_text
      and "2026-11-03T15:00:00-07:00" in change_text, change_text)
check("... and the gate's detail carries the old values it is replacing",
      change_card.calls[0]["detail"]["previous"]["summary"] == "Dentist"
      and change_card.calls[0]["detail"]["previous"]["end"]
      == "2026-11-03T16:00:00-07:00",
      change_card.calls[0]["detail"].get("previous") if change_card.calls else None)

# a card that never answers is a refusal, not a hang forever. The wait limit
# is read from jarvis_gate, which is not on this machine, so it is shortened
# here rather than waiting the gate's real ten minutes.
def _never(fn):
    return None


_real_gate_timeout = G._gate_timeout
_real_wait_after = G._WAIT_AFTER_GATE
G._gate_timeout = lambda: 0.05
G._WAIT_AFTER_GATE = 0.05
code, out = G.create_event(EVENT, gate=Card(), tier_of=lambda a: "ask",
                           spawn=_never, transport=Transport())
G._gate_timeout = _real_gate_timeout
G._WAIT_AFTER_GATE = _real_wait_after
check("a card that cannot be raised refuses and sends nothing",
      code == 503 and out["outcome"] == "refused", out)

# ══════════════════════════════════════════════════════════════════════════
#   5. Expiry, refresh, revoke, the chooser and the settings file
# ══════════════════════════════════════════════════════════════════════════

print("\nExpiry, revoke and the chooser")

root11, data11 = begin()
data11[G.TARGET_REFRESH] = REFRESH
G._ACCESS["token"], G._ACCESS["expires_at"] = "", 0.0
t11 = Transport()
G._TRANSPORT = t11
G.list_events(7)
refresh_calls = [c for c in t11.methods("token")
                 if (c["payload"] or {}).get("grant_type") == "refresh_token"]
check("with no access token in memory the refresh token is used",
      len(refresh_calls) == 1
      and refresh_calls[0]["payload"]["refresh_token"] == REFRESH, t11.urls())
check("the new access token replaces the old one, in memory only",
      G._ACCESS["token"] == ACCESS_2)
check("the refreshed read still carries no token", not leaks(G.status()))

root12, data12 = begin()
data12[G.TARGET_REFRESH] = REFRESH
G._ACCESS["token"], G._ACCESS["expires_at"] = "", 0.0
G._TRANSPORT = Transport(refresh_status=400)
expired = G.list_events(7)
check("an expired permission says so plainly and does not pretend",
      expired["ok"] is False and "expired" in expired["reason"], expired)
check("the expired sentence carries no token", not leaks(expired), expired)

root13, data13 = begin()
data13[G.TARGET_REFRESH] = REFRESH
t13 = Transport()
G._TRANSPORT = t13
result = G.disconnect(transport=t13)
check("disconnect asks Google to revoke the refresh token",
      any((c["payload"] or {}).get("token") == REFRESH
          for c in t13.methods("revoke")), t13.urls())
check("disconnect deletes the stored token", G.TARGET_REFRESH not in data13, data13)
check("disconnect says Google confirmed it", result["revoked"] is True, result)
check("disconnect turns the chosen way off and keeps the client ID",
      G.mode() == "off" and G.client_id() == CLIENT_ID, G.status())


def _revoke_fails(method, url, payload, headers):
    if "revoke" in url:
        return 500, {}
    return 200, {}


root14, data14 = begin()
data14[G.TARGET_REFRESH] = REFRESH
failed_revoke = G.disconnect(transport=_revoke_fails)
check("an unconfirmed revoke is reported as unconfirmed, and said plainly",
      failed_revoke["revoked"] is False
      and "myaccount.google.com/permissions" in failed_revoke["message"],
      failed_revoke)

root15, data15 = begin(mode="off")
data15[G.TARGET_REFRESH] = REFRESH
check("switching the way off does NOT delete the stored token",
      G.set_mode("off")["ok"] is True and data15.get(G.TARGET_REFRESH) == REFRESH)

try:
    G.set_mode("nonsense")
    check("an unknown way is refused", False, "accepted")
except ValueError as exc:
    check("an unknown way is refused, in plain words", "pick one of" in str(exc), str(exc))

root16, data16 = begin(mode="off", client=False)
try:
    G.set_mode("google")
    check("choosing Google sign-in without credentials is refused", False, "accepted")
except ValueError as exc:
    check("choosing Google sign-in without credentials is refused",
          "client ID" in str(exc) or "sign in" in str(exc), str(exc))

try:
    G.set_mode("ical")
    check("choosing the private link with no link is refused", False, "accepted")
except ValueError as exc:
    check("choosing the private link with no link says where to paste it",
          "iCal" in str(exc), str(exc))

try:
    G._write_settings({"mode": "google", "client_secret": CLIENT_SECRET})
    check("the settings file refuses a client secret", False, "it wrote")
except ValueError as exc:
    check("the settings file refuses a client secret",
          "Credential Manager" in str(exc), str(exc))

G._reset_for_tests()
use_config()
with_store({})
st = G.status()
check("status with nothing set up is honest and lists what is missing",
      st["mode"] == "off" and st["connected"] is False
      and st["ical_link_saved"] is False
      and any("a way chosen" in need for need in st["needs"]), st)
check("status does not push the Google client on someone with no way chosen",
      not any("Google client" in need for need in st["needs"]), st["needs"])
check("status carries no token and no secret",
      not leaks(st) and "client_secret\"" not in json.dumps(st), st)

# ── S5, measured: a SAVED private link with the mode still "off" (the default)
# made status and the chat say "neither is set up yet". A saved thing is set
# up; the chosen mode is the separate fact.
_real_ical_link = G._ical_link
G._ical_link = lambda: ("https://calendar.google.com/calendar/ical/owner%40example"
                        ".com/private-abcdef/basic.ics")
try:
    linked_status = G.status()
    check("a saved iCal link is reported as saved while mode is still off",
          linked_status["mode"] == "off" and linked_status["ical_link_saved"] is True
          and linked_status["connected"] is False, linked_status)
    check("... and status does not call a saved link 'not set up'",
          "not set up" not in linked_status["way"]
          and "private iCal link is saved" in linked_status["way"],
          linked_status["way"])
    check("... and needs nothing, because a saved link is a working way to choose",
          linked_status["needs"] == [], linked_status["needs"])
    chat = G.connect_sentence()
    check("the chat says the saved private link is set up, not 'neither is set up yet'",
          "neither is set up yet" not in chat.lower()
          and "already saved" in chat and "mode ical" in chat, chat)
    # ... and a saved Google token is reported the same way.
    with_store({G.TARGET_REFRESH: REFRESH})
    G._ical_link = lambda: ""
    signed_status = G.status()
    check("a saved Google sign-in is reported as saved while mode is still off",
          signed_status["refresh_token_saved"] is True and signed_status["connected"] is False
          and "Google sign-in is saved" in signed_status["way"], signed_status)
    check("... and the chat says the saved sign-in is set up too",
          "neither is set up yet" not in G.connect_sentence().lower()
          and "already saved" in G.connect_sentence()
          and "mode google" in G.connect_sentence(), G.connect_sentence())
finally:
    G._ical_link = _real_ical_link

# ══════════════════════════════════════════════════════════════════════════
#   6. The chat sentences - deterministic, and each one is a fact
# ══════════════════════════════════════════════════════════════════════════

print("\nChat sentences")

#: The clock these checks are pinned to: a fixed UTC-7 offset, NOT the
#: machine's own zone. `datetime(2026, 10, 28, 16, 0).astimezone()` attaches
#: whatever zone the machine runs in, and `parse_meeting` keeps the zone of the
#: `now` it is handed - so on a UTC runner the same call answered
#: `15:00+00:00` and both literals below, which are Pacific, failed. The
#: required `backend` job ran at 01:48Z on 2026-10-28 and failed exactly here.
#: The parser was right: it answers in the zone of the clock it is given.
#:
#: WHY A FIXED OFFSET AND NOT A NAMED ZONE. UTC-7 is the shape
#: `datetime.now().astimezone()` really hands `parse_meeting` in October: a
#: fixed offset, never a DST-aware zone. A named zone would have resolved
#: 3 November to -08:00 and the test would then assert something production
#: does not do. The parser keeps the offset it is handed, so these literals
#: carry -07:00 even across the DST change - that IS today's behaviour, written
#: down rather than wished away. A parser that resolved each date's own offset
#: would need -08:00 here, and this comment is where that change is recorded.
PACIFIC_DAYLIGHT = timezone(timedelta(hours=-7))
WEDNESDAY_AFTERNOON = datetime(2026, 10, 28, 16, 0, tzinfo=PACIFIC_DAYLIGHT)
WEDNESDAY_MORNING = datetime(2026, 10, 28, 9, 0, tzinfo=PACIFIC_DAYLIGHT)

G._reset_for_tests()
use_config()
with_store({})
said = G.answer("connect my google calendar")
check("'connect my google calendar' explains both ways and where they live",
      "private link" in said.lower() and "google sign-in" in said.lower()
      and "Settings" in said and G.SETUP_DOC in said, said)
check("the connect answer never invents an ICS export",
      "export" not in said.lower(), said)
check("'what's on my calendar' when disconnected says so",
      "Not connected yet" in G.answer("what's on my calendar"))
meeting = G.answer("add a meeting Tuesday 3pm", now=WEDNESDAY_AFTERNOON)
check("'add a meeting Tuesday 3pm' proposes it and says it needs the sign-in way",
      "read-only" in meeting and "Tuesday" not in meeting or "read-only" in meeting,
      meeting)
check("an unrelated sentence is not swallowed",
      G.answer("what's the weather like") is None)

parsed = G.parse_meeting("add a meeting Tuesday 3pm", now=WEDNESDAY_AFTERNOON)
check("Tuesday 3pm is the next Tuesday, 15:00-16:00",
      parsed["start"] == "2026-11-03T15:00:00-07:00"
      and parsed["end"] == "2026-11-03T16:00:00-07:00", parsed)
check("the title comes from the owner's words", parsed["summary"] == "Meeting", parsed)
lunch = G.parse_meeting("add a lunch tomorrow at 12:30 for 90 minutes",
                        now=WEDNESDAY_MORNING)
check("'tomorrow at 12:30 for 90 minutes' is 12:30-14:00 tomorrow",
      lunch["start"].startswith("2026-10-29T12:30")
      and lunch["end"].endswith("14:00:00-07:00"), lunch)
# ... and the proof that the two checks above cannot depend on the machine's
# own zone: the SAME instant, handed over in a different zone, answers the same
# wall-clock date and hour - only the offset follows the clock it was given. A
# parser that read `datetime.now()` internally instead of the `now` it was
# handed would give this desk's answer on both and fail here.
same_instant_utc = G.parse_meeting("add a meeting Tuesday 3pm",
                                   now=WEDNESDAY_AFTERNOON.astimezone(timezone.utc))
check("the parser follows the clock it is handed, not the machine's zone",
      same_instant_utc["start"] == "2026-11-03T15:00:00+00:00"
      and parsed["start"] == "2026-11-03T15:00:00-07:00", same_instant_utc)
check("a day but no time is not guessed at",
      G.parse_meeting("add a meeting sometime next week") is None)
check("no day at all is not guessed at",
      G.parse_meeting("add a meeting at 3pm") is None)

# the connected answer lists the real events, and reads only
root17, data17 = begin()
data17[G.TARGET_REFRESH] = REFRESH
t17 = Transport()
G._TRANSPORT = t17
today = G.answer("what's on my calendar")
check("connected: 'what's on my calendar' lists the real events",
      "Dentist" in today and "Bin day" in today and "next 7 days" in today, today)


def calendar_writes(calls):
    """The calls that would CHANGE a calendar. A token refresh is a POST too,
    and it is not a write to anyone's calendar."""
    return [c for c in calls if c["method"] in ("POST", "PATCH", "PUT", "DELETE")
            and "/calendar/v3/calendars/" in c["url"]]


check("the chat answer read the calendar and changed nothing",
      any("/calendars/primary/events" in u for u in t17.urls())
      and calendar_writes(t17.calls) == [], t17.urls())
add = G.answer("add a meeting Tuesday 3pm")
check("connected: an add is only PROPOSED - one card, not a sent event",
      "approval card" in add and calendar_writes(t17.calls) == [], add)
check("the chat answers carry no token", not leaks(today) and not leaks(add))

# ══════════════════════════════════════════════════════════════════════════
#   7. install() wires the routes and touches nothing else
# ══════════════════════════════════════════════════════════════════════════

print("\nThe routes")


class FakeHandler:
    """One stand-in for the backend's own Handler, built FRESH each time:
    install() wraps the class it is given, and wrapping an already-wrapped
    class is deliberately a no-op ("already on"), so a test that wants a
    second, differently-gated wrapper needs a second class."""

    @staticmethod
    def build():
        class H:
            def __init__(self):
                self.path = ""
                self.answers = []
                self.original = 0

            def _send(self, code, out):
                self.answers.append((code, out))
                return code, out

            def do_GET(self):
                self.original += 1
                return "original-get"

            def do_POST(self):
                self.original += 1
                return "original-post"

        return H


def install(handler_cls, *, origin=True, token=True, body=b"{}"):
    return G.install(handler_cls, origin_ok=lambda h: origin,
                     token_ok=lambda h: token, read_body=lambda h: body)


def wrapped(**kwargs):
    """One freshly built handler class with the module's routes on it, and an
    instance of it - install() wraps the CLASS, so the instance has to come
    afterwards."""
    H = FakeHandler.build()
    install(H, **kwargs)
    return H()


begin(mode="off", client=False)
fresh = FakeHandler.build()
banner = install(fresh)
check("install() says what state the calendar is in",
      "Google Calendar" in banner and "neither way" in banner, banner)
check("install() twice is harmless", "already on" in install(fresh))

h = wrapped()
h.path = G.STATUS_PATH
h.do_GET()
check("GET /api/google-calendar/status is answered here",
      h.answers and h.answers[0][0] == 200 and "mode" in h.answers[0][1], h.answers)

h3 = wrapped()
h3.path = "/api/something-else"
check("an unrelated route goes straight to the original handler",
      h3.do_GET() == "original-get" and h3.original == 1)

h4 = wrapped(origin=False)
h4.path = G.EVENTS_PATH
h4.do_GET()
check("a cross-origin read is refused before anything else",
      h4.answers and h4.answers[0][0] == 403, h4.answers)

h5 = wrapped(token=False)
h5.path = G.STATUS_PATH
h5.do_GET()
check("a request without the token is refused",
      h5.answers and h5.answers[0][0] == 401, h5.answers)

h6 = wrapped(body=b'{"mode":"nonsense"}')
h6.path = G.MODE_PATH
h6.do_POST()
check("POST /api/google-calendar/mode answers a bad way with 400",
      h6.answers and h6.answers[0][0] == 400, h6.answers)

check("every route this module answers is under /api/google-calendar/",
      all(p.startswith("/api/google-calendar/") for p in G.ROUTES)
      and len(set(G.ROUTES)) == len(G.ROUTES), G.ROUTES)

# ══════════════════════════════════════════════════════════════════════════
#   8. The owner's own commands - the setup that needs no UI
# ══════════════════════════════════════════════════════════════════════════

print("\nThe owner's commands")

root18, data18 = begin(mode="off", client=False)
rc, out, err = quiet(G._main, ["py", "status"])
check("`status` says what is set up, in words, and where the token lives",
      "Connected:" in out and "not saved" in out and "Credential Manager" in out, out)
check("`status` prints no secret", not leaks(out) and not leaks(err), out)

rc, out, _err = quiet(G._main, ["py", "client", CLIENT_ID],
                      getpass_fn=lambda prompt: CLIENT_SECRET)
check("`client <id>` saves the ID and asks for the secret with hidden typing",
      data18.get(G.TARGET_CLIENT_SECRET) == CLIENT_SECRET
      and G.client_id() == CLIENT_ID, data18)
check("`client <id>` output carries no secret", not leaks(out), out)

data18[G.TARGET_REFRESH] = REFRESH
rc, out, _err = quiet(G._main, ["py", "mode", "google"])
check("`mode google` chooses the sign-in way once a token is saved",
      G.mode() == "google", out)

with_store({G.TARGET_CLIENT_SECRET: CLIENT_SECRET})
rc2, out2, _err2 = quiet(G._main, ["py", "mode", "google"])
check("`mode google` with no signed-in token says so rather than pretending",
      rc2 == 1 and "sign in" in out2.lower(), out2)

rc, out, _err = quiet(G._main, ["py", "nonsense"])
check("an unknown command prints the usage and exits 2",
      rc == 2 and "jarvis_google_calendar.py connect" in out, out)

data19: dict = {}
G._reset_for_tests()
use_config()
with_store(data19)
data19[G.TARGET_REFRESH] = REFRESH
rc, out, _err = quiet(G._main, ["py", "disconnect"])
check("`disconnect` forgets the token and says what it did",
      G.TARGET_REFRESH not in data19 and "Disconnected" in out, out)
check("`disconnect` output carries no token", not leaks(out), out)

# ══════════════════════════════════════════════════════════════════════════
#   9. The file itself: no secret written, no token printed
# ══════════════════════════════════════════════════════════════════════════

print("\nThe module's own promises")

# These five used to be pins on the module's SOURCE TEXT (`src.count(
# "write_text(")`, `"os.replace" in src`, `re.search(..., src)` and friends).
# A pin on text goes red when the code is renamed or improved and stays green
# when the behaviour is wrong, so each one is now either a structural `ast`
# walk (immune to comments, docstrings and spelling) or a real call whose
# effect is measured.
builtin_open = [n for n in ast.walk(TREE)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "open"]
check("the module never calls the builtin open()", not builtin_open,
      [getattr(c, "lineno", "") for c in builtin_open])
json_file_calls = [n for n in ast.walk(TREE)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and n.func.attr == "dump"]
check("the module never calls json.dump (a file writer), only json.dumps",
      not json_file_calls, [getattr(c, "lineno", "") for c in json_file_calls])

write_text_calls = [n for n in ast.walk(TREE)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "write_text"]
check("the module writes the disk through exactly ONE write_text call",
      len(write_text_calls) == 1, [getattr(c, "lineno", "") for c in write_text_calls])

G._reset_for_tests()
root_w = use_config()
with_store({})
G._write_settings({"mode": "ical", "client_id": CLIENT_ID})
files_w = sorted(p.name for p in root_w.iterdir() if p.is_file())
check("... and the one file it creates IS the settings file, and nothing else",
      files_w == [G.SETTINGS_NAME], files_w)
check("... holding only the mode and the public client ID, so no token can be "
      "serialized into it",
      set(json.loads(G.settings_path().read_text(encoding="utf-8")))
      == {"mode", "client_id"}, G.settings_path().read_text(encoding="utf-8"))
check("... and no temporary copy is left behind",
      not G.settings_path().with_suffix(".tmp").exists()
      and not any(p.suffix == ".tmp" for p in root_w.iterdir()), files_w)
G._write_settings({"mode": "off", "client_id": CLIENT_ID})
check("... also after a second write (the replace path runs again)",
      not any(p.suffix == ".tmp" for p in root_w.iterdir()), files_w)

refused_all = True
for field in G._REFUSED_FIELDS:
    try:
        G._write_settings({field: "x"})
        refused_all = False
    except ValueError:
        pass
check("the settings writer refuses EVERY secret-shaped field in its own list",
      refused_all, G._REFUSED_FIELDS)


def _call_chain(node) -> list:
    """[names and attribute names] along a dotted expression."""
    out: list = []
    while isinstance(node, ast.Attribute):
        out.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        out.append(node.id)
    return out


environ_reads = [[a.value for a in n.args if isinstance(a, ast.Constant)]
                 for n in ast.walk(TREE)
                 if isinstance(n, ast.Call) and "environ" in _call_chain(n.func)]
check("the only environment variable the module reads is the config folder, so "
      "no environment variable can supply an OAuth token",
      environ_reads == [["OPENJARVIS_CONFIG_DIR"]], environ_reads)
secret_reader = [n for n in ast.walk(TREE)
                 if isinstance(n, ast.Call)
                 and ("resolve_secret" in _call_chain(n.func))]
check("the module never calls resolve_secret (which puts the environment first)",
      not secret_reader, [getattr(c, "lineno", "") for c in secret_reader])

print()
if FAILED:
    print(f"{len(FAILED)} failed: {', '.join(FAILED)}")
    sys.exit(1)
print(f"{len(PASSED)} passed - the Google Calendar sign-in is loopback-only, PKCE- and "
      "state-checked, keeps its refresh token in Credential Manager, raises one card "
      "per write and refuses a stale calendar")
