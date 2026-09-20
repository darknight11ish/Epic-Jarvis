"""jarvis_notes.py: searches the owner's own Joplin or Obsidian notes, and
the promise that `plan()` cannot touch the network and `run()` cannot be
tricked into it - and that the token never ends up on the card.

    python3 test_notes.py
"""
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _where import BACKEND, REPO  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_notes as N

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


def with_env(backend=None, joplin_url=None, joplin_token=None,
             obsidian_url=None, obsidian_key=None):
    class _Ctx:
        def __enter__(self2):
            keys = (N.BACKEND_ENV, N.JOPLIN_URL_ENV, N.JOPLIN_TOKEN_ENV,
                    N.OBSIDIAN_URL_ENV, N.OBSIDIAN_KEY_ENV)
            self2.saved = {k: os.environ.get(k) for k in keys}
            for k, v in zip(keys, (backend, joplin_url, joplin_token,
                                    obsidian_url, obsidian_key)):
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


# ── plan(): opens no socket, refuses cleanly with nothing configured ─────

with with_env():
    with NoNetwork():
        p_empty = N.plan("project plan")
    check("no backend configured -> backend is None", p_empty.backend is None)
    text = N.describe(p_empty)
    check("describe() says why, sends nothing",
          "no notes app configured" in text and "Nothing would be sent" in text)

with with_env():
    p_blank = N.plan("   ")
    check("a blank query refuses before picking a backend",
          p_blank.reason_empty == "the search query is empty")

# ── backend resolution: explicit override wins, otherwise whichever token exists ──

with with_env(joplin_token="tok123"):
    with NoNetwork():
        p = N.plan("meeting notes")
    check("plan() opens no socket", True)
    check("a Joplin token alone resolves to the joplin backend", p.backend == "joplin")
    check("the default Joplin URL is used when none is set",
          p.url.startswith("http://127.0.0.1:41184/search?query="))
    check("the token never appears in the plan's URL", "tok123" not in p.url)

with with_env(obsidian_key="key456"):
    p = N.plan("meeting notes")
    check("an Obsidian key alone resolves to the obsidian backend", p.backend == "obsidian")
    check("the default Obsidian URL is used when none is set",
          p.url.startswith("https://127.0.0.1:27124/search/simple/?query="))
    check("the key never appears in the plan's URL", "key456" not in p.url)

with with_env(backend="obsidian", joplin_token="tok123", obsidian_key="key456"):
    p = N.plan("meeting notes")
    check("an explicit backend override wins over which token exists",
          p.backend == "obsidian")

with with_env(joplin_token="tok123", joplin_url="http://localhost:9999"):
    p = N.plan("q")
    check("a custom Joplin URL is honoured", p.url.startswith("http://localhost:9999/search"))

check("limit is clamped above the cap",
      N.plan("q", limit=500).limit == N._MAX_RESULTS)
check("limit is clamped below 1", N.plan("q", limit=0).limit == 1)

# ── describe(): the literal request, never the credential ────────────────

with with_env(joplin_token="tok123"):
    text = N.describe(N.plan("budget"))
    check("describe() prints the literal (token-free) URL", "/search?query=budget" in text)
    check("authenticated() is true once a token is set", N.authenticated())
    check("describe() says a credential will be sent, never what it is",
          "will send the configured joplin" in text and "tok123" not in text)

with with_env():
    p_no_backend_but_query = N.plan("budget")
    text = N.describe(p_no_backend_but_query)
    check("with no backend configured, no auth claim is made either way",
          "will send the configured" not in text)

# ── run(): refuses without approval, normalises both backends ────────────

with with_env(joplin_token="tok123"):
    p = N.plan("budget", limit=5)

    unapproved = N.run(p)
    check("run() without approval does nothing", unapproved["ok"] is False)

    calls = []

    def fake_fetch(plan_obj):
        calls.append(plan_obj)
        return {"items": [
            {"id": "abc123", "title": "Q3 Budget", "body": "Numbers are looking good."},
            {"id": "def456", "title": "Q4 Budget draft", "body": "Still drafting this one."},
        ]}

    out = N.run(p, fetch=fake_fetch, approved=True)
    check("run() calls fetch exactly once", len(calls) == 1)
    check("run() succeeds when fetch succeeds", out["ok"] is True)
    check("both Joplin results are normalised", len(out["results"]) == 2)
    check("Joplin title/snippet/ref map correctly",
          out["results"][0] == {"title": "Q3 Budget", "snippet": "Numbers are looking good.",
                                 "ref": "abc123"})

    def failing_fetch(plan_obj):
        raise TimeoutError("connection timed out")

    failed = N.run(p, fetch=failing_fetch, approved=True)
    check("a request failure is reported, not raised", failed["ok"] is False)
    check("the failure reason is legible", "connection timed out" in failed["reason"])

with with_env(obsidian_key="key456"):
    p = N.plan("budget", limit=5)
    raw = [
        {"filename": "Budget/Q3.md", "matches": [{"context": "Numbers look solid this quarter."}]},
        {"filename": "Budget/Q4.md", "matches": []},
    ]
    out = N.run(p, fetch=lambda _p: raw, approved=True)
    check("both Obsidian results are normalised", len(out["results"]) == 2)
    check("Obsidian filename/context map correctly",
          out["results"][0] == {"title": "Budget/Q3.md",
                                 "snippet": "Numbers look solid this quarter.",
                                 "ref": "Budget/Q3.md"})
    check("a result with no matches gets an empty snippet, not an error",
          out["results"][1]["snippet"] == "")

# ── the cap: more results than the limit is truncated ─────────────────────

with with_env(joplin_token="tok123"):
    p = N.plan("q", limit=2)
    many = {"items": [{"id": str(i), "title": f"Note {i}", "body": "x"} for i in range(10)]}
    out = N.run(p, fetch=lambda _p: many, approved=True)
    check("normalisation respects the plan's limit, not the raw count",
          len(out["results"]) == 2)

print()
if FAILED:
    print(f"{len(FAILED)} failed: {', '.join(FAILED)}")
    sys.exit(1)
print(f"{len(PASSED)} passed - notes search is read-only, and the token never reaches the card")
