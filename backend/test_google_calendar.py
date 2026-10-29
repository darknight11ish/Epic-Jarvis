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
import base64
import contextlib
import hashlib
import inspect
import io
import json
import re
import socket
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
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

    def __init__(self, *, refresh_status=200, exchange_ok=True):
        self.calls = []
        self.refresh_status = refresh_status
        self.exchange_ok = exchange_ok

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
                         "refresh_token": REFRESH, "token_type": "Bearer"}
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
check("the listener is built from BIND_HOST, never a literal 0",
      'HTTPServer((BIND_HOST, 0)' in src and 'BIND_HOST = "127.0.0.1"' in src)


# ── one whole sign-in, against a real loopback listener + a stub Google ─────

def sign_in(*, state_suffix="", missing_state=False, error=None):
    started = G.start(opener=lambda url: None)
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(started["auth_url"]).query))
    port = started["port"]
    if error:
        target = f"http://127.0.0.1:{port}/callback?error={error}"
    else:
        target = f"http://127.0.0.1:{port}/callback?code=one-time-code"
        if not missing_state:
            target += "&state=" + query["state"] + state_suffix
    status = None
    try:
        with urllib.request.urlopen(target, timeout=10) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.read()
    G.wait(5.0)
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

# ── a wrong state, a missing state, and the owner pressing Cancel ───────────
for label, kwargs in (("a WRONG state", {"state_suffix": "x"}),
                      ("a MISSING state", {"missing_state": True})):
    root2, data2 = begin(mode="off")
    t2 = Transport()
    G._TRANSPORT = t2
    _started, _query, code = sign_in(**kwargs)
    check(f"{label} is refused with 400", code == 400, code)
    check(f"{label} exchanges NOTHING with Google", not t2.methods("token"), t2.urls())
    check(f"{label} leaves no refresh token in the store",
          G.TARGET_REFRESH not in data2, data2)
    check(f"{label} reports bad_state, never 'connected'",
          G.pending().outcome()["outcome"] == "bad_state", G.pending().outcome())

root3, data3 = begin(mode="off")
t3 = Transport()
G._TRANSPORT = t3
_started, _query, code = sign_in(error="access_denied")
check("Google's own 'access_denied' is refused, not connected",
      code == 400 and G.pending().outcome()["outcome"] == "denied"
      and G.TARGET_REFRESH not in data3, G.pending().outcome())

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
check("the read records the snapshot a change may be allowed against",
      G._STATE["read_ok"] and "evt_" + "one" in G._STATE["ids"], list(G._STATE["ids"]))
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
G._STATE["last_read"] = 0.0
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

G._STATE["last_read"] = time.monotonic()
unknown_card = Card()
code, out = G.delete_event({"event_id": "evt_" + "never-seen"},
                           gate=unknown_card, tier_of=lambda a: "ask",
                           spawn=lambda fn: fn())
check("an event the last read did not see is refused, card-free",
      code == 409 and not unknown_card.calls, out)

G._STATE["last_read"] = time.monotonic()
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
      G._STATE["last_read"] == 0.0 and not G._STATE["read_ok"], G._STATE)

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
      and "the Google client ID" in st["needs"], st)
check("status carries no token and no secret",
      not leaks(st) and "client_secret\"" not in json.dumps(st), st)

# ══════════════════════════════════════════════════════════════════════════
#   6. The chat sentences - deterministic, and each one is a fact
# ══════════════════════════════════════════════════════════════════════════

print("\nChat sentences")

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
meeting = G.answer("add a meeting Tuesday 3pm",
                   now=datetime(2026, 10, 28, 16, 0).astimezone())
check("'add a meeting Tuesday 3pm' proposes it and says it needs the sign-in way",
      "read-only" in meeting and "Tuesday" not in meeting or "read-only" in meeting,
      meeting)
check("an unrelated sentence is not swallowed",
      G.answer("what's the weather like") is None)

parsed = G.parse_meeting("add a meeting Tuesday 3pm",
                         now=datetime(2026, 10, 28, 16, 0).astimezone())
check("Tuesday 3pm is the next Tuesday, 15:00-16:00",
      parsed["start"] == "2026-11-03T15:00:00-07:00"
      and parsed["end"] == "2026-11-03T16:00:00-07:00", parsed)
check("the title comes from the owner's words", parsed["summary"] == "Meeting", parsed)
lunch = G.parse_meeting("add a lunch tomorrow at 12:30 for 90 minutes",
                        now=datetime(2026, 10, 28, 9, 0).astimezone())
check("'tomorrow at 12:30 for 90 minutes' is 12:30-14:00 tomorrow",
      lunch["start"].startswith("2026-10-29T12:30")
      and lunch["end"].endswith("14:00:00-07:00"), lunch)
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

import ast  # noqa: E402

tree = ast.parse(src)
builtin_open = [n for n in ast.walk(tree)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "open"]
check("the module writes ONE file, and it is the settings file",
      src.count("write_text(") == 1 and "SETTINGS_NAME" in src)
check("the module never calls the builtin open()", not builtin_open,
      [getattr(c, "lineno", "") for c in builtin_open])
check("a refresh token is never inside json.dumps or a file writer",
      not re.search(r"json\.dumps\([^)]*refresh", src, re.I))
check("no environment variable can supply an OAuth token",
      "resolve_secret" not in code_src
      and not re.search(r"environ[^\n]{0,120}(?:token|secret|refresh|access)",
                        code_src, re.I),
      re.findall(r"environ[^\n]{0,60}", code_src, re.I)[:4])
check("the temporary settings copy is replaced, not left behind",
      "os.replace" in src)

print()
if FAILED:
    print(f"{len(FAILED)} failed: {', '.join(FAILED)}")
    sys.exit(1)
print(f"{len(PASSED)} passed - the Google Calendar sign-in is loopback-only, PKCE- and "
      "state-checked, keeps its refresh token in Credential Manager, raises one card "
      "per write and refuses a stale calendar")
