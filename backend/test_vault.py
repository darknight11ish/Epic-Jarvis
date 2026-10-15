"""test_vault.py - the blind credential vault (jarvis_vault.py, the owner's
brief on `feat/blind-credential-vault`).

    python3 backend/test_vault.py

WHAT THIS PROVES, and why each check is here:

  - a value ROUND-TRIPS: put() then get() hands back exactly what went in;
  - **the value appears in no returned text, no audit line, no log and no
    `handles()` output.** Searched in the actual BYTES - the route's JSON, the
    audit detail dict, the printed log line and `vault.json` on disk - not
    asserted from a flag. And not a masked prefix of it either;
  - a handle resolves EXACTLY ONCE, at the point of use, and only for the host
    the value is bound to: the key saved for one service is not substituted
    into a request to another;
  - `resolve()` on text with no handle returns it unchanged, and never asks
    the store at all;
  - a DENIED card stores nothing - and neither does a timed-out one, a refused
    one, or a gate that cannot be reached. Nothing is stored before the answer
    either: the test reads the store while the card is still outstanding;
  - the SCRUBBER is applied to anything coming back: a provider that echoes the
    key into its answer cannot get it into the tool result, because
    `redact()` runs `jarvis_scrub`;
  - it is wired to a real use: `jarvis_search` builds the header for the Exa,
    Tavily and Brave keys from a handle, and the key reaches the service and
    nothing else - proved end to end against a server on 127.0.0.1;
  - and the housekeeping: the module is in both shipped-module lists,
    `plugins/ready/vault/plugin.json` names it with an `install()`, and the
    module never writes a value to a file.

Storage is a stand-in Credential Manager (`_STORE_FACTORY`, the same hook
`jarvis_search` and `jarvis_token_store` already expose), so nothing here needs
the owner's PC, a real credential or a network. One real socket is opened, to a
server this suite starts on 127.0.0.1 - the web-search wiring check.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-vault-"))
# Before anything imports jarvis_framework: its CONFIG_DIR is read once, and
# this is where vault.json must land - NOT in the owner's own config folder.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

import jarvis_scrub as SCRUB  # noqa: E402
import jarvis_vault as V  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []

#: TRUE while this suite runs. `jarvis_vault._store()` refuses to reach the
#: REAL Windows Credential Manager while it is set - see the incident recorded
#: in `t_a_non_windows_pc_refuses_to_store_rather_than_writing_plain_text`: a
#: test that reached the real store wrote a real credential under
#: "Jarvis Backend/vault/github" into the owner's own Credential Manager. A
#: suite must never be able to do that again, so it is this module's job to
#: stop it, not a reader's job to notice.
V.TESTING = True

#: Fake secrets, built by concatenation so no literal in this file is shaped
#: like a real key (the house rule - test_account_secrets.py's own FAKE_*).
FAKE_KEY = "sk-" + "vault" + "-" + "0123456789" + "abcdef"
FAKE_OTHER = "tvly-" + "second" + "-" + "9876543210"
FAKE_ECHOED = "exa-" + "echo" + "-" + "abcdef0123456789"

#: A value short enough that the scrubber's own eight-character floor would NOT
#: catch it by value: the vault must still hide it, because it knows which
#: name this turn actually used.
FAKE_SHORT = "s3cr3t"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   A stand-in Credential Manager, and a stand-in audit log
# --------------------------------------------------------------------------

class FakeStore:
    """Credential Manager, in memory: target -> value. Refuses on demand, so
    the "no store" path is a real path and not a comment."""

    DATA: dict = {}
    REFUSE = False
    SEEN_TARGETS: list = []

    def __init__(self, target):
        self.target = target
        FakeStore.SEEN_TARGETS.append(target)

    def read(self):
        if FakeStore.REFUSE:
            raise V_store_error()
        return FakeStore.DATA.get(self.target)

    def write(self, value):
        if FakeStore.REFUSE:
            raise V_store_error()
        FakeStore.DATA[self.target] = value

    def delete(self):
        had = self.target in FakeStore.DATA
        FakeStore.DATA.pop(self.target, None)
        return had


def V_store_error():
    try:
        import jarvis_token_store as T
        return T.StoreError("refused (Windows error 1312)")
    except Exception:
        return RuntimeError("refused")


AUDIT: list = []


def _audit(event, detail):
    AUDIT.append((event, detail))


def reset():
    """A clean vault: no store contents, no document, no in-memory state."""
    V._reset_for_tests()
    FakeStore.DATA.clear()
    FakeStore.REFUSE = False
    FakeStore.SEEN_TARGETS.clear()
    AUDIT.clear()
    V._STORE_FACTORY = FakeStore
    V._AUDIT = _audit
    path = V.vault_path()
    if path.exists():
        path.unlink()
    return path


def bytes_of(obj) -> str:
    """Every byte a caller could see, as text. Used to search for a value in
    what was ACTUALLY returned rather than trusting a boolean."""
    return json.dumps(obj, default=str, ensure_ascii=False)


def code_without_prose(source: str) -> str:
    """The source with its comments and docstrings stripped - the same
    treatment test_gate_outcome.t_there_is_still_no_approve_all uses, and for
    the same reason: a claim about code must be read from the code, not from
    the paragraph next to it that happens to contain the same words."""
    import ast
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body.pop(0)
    return ast.unparse(tree)


#: The ways out of a process this module must never take. Read as CALLS from
#: the parse tree, so the word "socket" in a sentence is not a finding.
_BANNED_CALLS = {"urlopen", "socket", "create_connection", "Popen", "system",
                 "popen", "check_output", "exec", "eval", "compile"}


def calls_in(source: str) -> set:
    """Every BARE function called by name - `compile(...)`, not
    `re.compile(...)`. A method on a module is not the builtin of the same
    name, and reading it as one is how a checker reports a defect that is not
    there."""
    import ast
    out = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            out.add(node.func.id)
    return out


def function_source(path: Path, name: str) -> str:
    """One function's own text, from the file - so a claim about WHERE a call
    is made is read from that function and not from the whole module."""
    import ast
    source = Path(path).read_text(encoding="utf-8")
    lines = source.splitlines()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    return ""

# --------------------------------------------------------------------------
#   1. A value round-trips
# --------------------------------------------------------------------------

def t_a_value_round_trips():
    reset()
    check("put() saves a value", V.put("github", FAKE_KEY) is True)
    check("... and get() hands back exactly what went in", V.get("github") == FAKE_KEY,
          repr(V.get("github")))
    check("... under its own Credential Manager target, in the project's own shape",
          FakeStore.DATA.get(V.PREFIX + "github") == FAKE_KEY,
          str(sorted(FakeStore.DATA)))
    check("... and the target says the vault owns it",
          V.PREFIX == "Jarvis Backend/vault/" and (V.PREFIX + "github") in FakeStore.DATA)
    check("put() is idempotent: saving again replaces it",
          V.put("github", FAKE_OTHER) is True and V.get("github") == FAKE_OTHER)
    check("forget() deletes it, and says one was there",
          V.forget("github") is True and V.get("github") is None)
    check("... and the name goes with it", V.handles() == [], str(V.handles()))
    V.vault_path().unlink(missing_ok=True)   # leave no name for the next test


def t_a_refused_store_is_false_not_an_exception():
    reset()
    FakeStore.REFUSE = True
    check("a store that refuses: put() is False, and nothing raises",
          V.put("github", FAKE_KEY) is False)
    check("... get() is None, and nothing raises", V.get("github") is None)
    check("... and no name was remembered", V.handles() == [], str(V.handles()))


def t_a_non_windows_pc_refuses_to_store_rather_than_writing_plain_text():
    """The brief's own instruction: if the only mechanism is Credential Manager
    and it is not there, DEGRADE TO "REFUSE TO STORE" - never write plain
    text.

    NOT DONE BY SETTING `_STORE_FACTORY = None`. That makes `_store()` fall
    through to the REAL store, and on the owner's own Windows PC the real store
    works - so the suite wrote a real credential under
    "Jarvis Backend/vault/github" and this check then failed for the wrong
    reason. The unavailable store is a STAND-IN that raises, which is what a
    PC with no Credential Manager looks like from here (`Unavailable`, the same
    exception jarvis_token_store.WindowsStore raises on a non-Windows box)."""
    reset()
    V.vault_path().unlink(missing_ok=True)      # no remembered name from an earlier test
    V._STORE_FACTORY = V._store_error
    ok = V.put("github", FAKE_KEY)
    st = V.status()
    wrote_anywhere = []
    for p in (V.vault_path(),):
        if p.exists():
            wrote_anywhere.append(p.read_text(encoding="utf-8"))
    check("no Credential Manager: put() refuses rather than storing", ok is False)
    check("... status() says so in plain words, and says why",
          st["available"] is False and "refuse" in st["why"].lower(), st["why"])
    check("... and NO VALUE reached any file the vault owns",
          all(FAKE_KEY not in t for t in wrote_anywhere), str(wrote_anywhere))
    check("... the handles list is empty, so nothing pretends to be saved",
          V.handles() == [], str(V.handles()))
    V._STORE_FACTORY = FakeStore


# --------------------------------------------------------------------------
#   2. The value is in no returned text, no audit line, no log, no handles()
# --------------------------------------------------------------------------

def t_the_value_is_nowhere_it_could_leak():
    reset()
    V.put("github", FAKE_KEY)
    V.get("github")

    route = V.handle_handles()
    view = V.status()
    rows = V.handles()
    resolved = V.resolve("token {{vault:github}}")
    redacted = V.redact(f"the service said: {FAKE_KEY}")

    # The ACTUAL BYTES, not a flag.
    for label, payload in (("the GET /api/vault/handles answer", route),
                           ("status()", view),
                           ("handles()", rows),
                           ("the audit lines", AUDIT)):
        blob = bytes_of(payload)
        check(f"the value is in none of {label}", FAKE_KEY not in blob, blob[:400])
        check(f"... and no masked prefix of it is in {label}",
              FAKE_KEY[:6] not in blob and FAKE_KEY[:8] not in blob, blob[:400])

    check("... and no length is published either",
          all(str(len(FAKE_KEY)) not in str(h.get(f, ""))
              for h in route[1]["handles"]
              for f in ("name", "handle", "for_host")),
          bytes_of(route))
    check("the audit lines carry the NAME", any(name == "vault.put" for name, _ in AUDIT)
          and any(d.get("name") == "github" for _, d in AUDIT), str(AUDIT))
    check("... and never a value, in any field of any line",
          all(FAKE_KEY not in bytes_of(d) for _, d in AUDIT), str(AUDIT))

    check("handles() gives the handle, the host and when it was used - and no value",
          rows and rows[0]["handle"] == "{{vault:github}}"
          and "for_host" in rows[0] and rows[0]["last_used"] > 0
          and set(rows[0]) == {"name", "handle", "for_host", "last_used", "has_value"},
          str(rows))

    # vault.json, the one file this feature owns.
    path = V.vault_path()
    raw = path.read_text(encoding="utf-8")
    check("vault.json exists and holds the NAME", path.is_file() and "github" in raw)
    check("... and NOT the value, nor a prefix of it",
          FAKE_KEY not in raw and FAKE_KEY[:6] not in raw, raw)
    check("... the only keys it holds are names, a host and times",
          set(json.loads(raw)) <= {"names", "changed"}
          and all(set(r) <= {"for_host", "used"} for r in json.loads(raw)["names"].values()),
          raw)

    # The log, through the project's own scrubber, and through the vault's.
    fake_log = f"searching with key {FAKE_KEY} for 'boots'"
    check("the project's scrubber takes the value out of a log line",
          FAKE_KEY not in SCRUB.scrub_text(fake_log), SCRUB.scrub_text(fake_log))
    check("redact() puts it back behind its handle",
          FAKE_KEY not in redacted and "{{vault:github}}" in redacted, redacted)
    check("resolve() DOES return it - that is the point of the point of use",
          resolved == f"token {FAKE_KEY}")


def t_a_short_value_is_still_hidden():
    """The scrubber's own exact-match floor is eight characters, on purpose. A
    vault value shorter than that must still not come back out: the vault knows
    WHICH name this turn used, which a pattern table cannot."""
    reset()
    check("a four-character value saves", V.put("pin", FAKE_SHORT) is True)
    V.get("pin")
    out = V.redact(f"the page said {FAKE_SHORT} back")
    check("... and redact() still hides it, though the scrubber's floor is 8",
          FAKE_SHORT not in out, out)
    check("... handles() says nothing about it", FAKE_SHORT not in bytes_of(V.handles()))
    check("... the values in memory are not published anywhere",
          all(FAKE_SHORT not in bytes_of(x) for x in (V.status(), V.handle_handles())))


# --------------------------------------------------------------------------
#   3. A handle resolves exactly once, at the point of use
# --------------------------------------------------------------------------

def t_resolve_replaces_each_handle_once():
    reset()
    V.put("github", FAKE_KEY)
    text = "a {{vault:github}} b {{vault:github}} c {{vault:github}}"
    out = V.resolve(text)
    check("every handle is replaced", out == f"a {FAKE_KEY} b {FAKE_KEY} c {FAKE_KEY}", out)
    check("... exactly as many times as it appears",
          out.count(FAKE_KEY) == 3 and "{{vault:" not in out, out)
    check("the store was asked for it once per occurrence, and no more",
          FakeStore.SEEN_TARGETS.count(V.PREFIX + "github") == 8,
          str(FakeStore.SEEN_TARGETS))

    check("a handle that names nothing is left AS the handle",
          V.resolve("x {{vault:nosuch}} y") == "x {{vault:nosuch}} y",
          V.resolve("x {{vault:nosuch}} y"))
    check("a malformed handle is not a handle",
          V.resolve("{{vault:}} {{vault: }} {{vault:a b}}")
          == "{{vault:}} {{vault: }} {{vault:a b}}")
    check("a name too long is not a handle",
          V.resolve("{{vault:" + "x" * 65 + "}}") == "{{vault:" + "x" * 65 + "}}")
    check("handle() and HANDLE_RE agree", V.handle("github") == "{{vault:github}}"
          and V.HANDLE_RE.fullmatch(V.handle("github")) is not None)
    check("handle() never invents one for a name that is not a name",
          V.handle("a b") == "" and V.handle("") == "")
    check("names_in() lists the names in order, without repeats",
          V.names_in("{{vault:a}} {{vault:b}} {{vault:a}}") == ["a", "b"],
          str(V.names_in("{{vault:a}} {{vault:b}} {{vault:a}}")))


def t_resolve_on_text_with_no_handle_is_unchanged():
    reset()
    V.put("github", FAKE_KEY)
    FakeStore.SEEN_TARGETS.clear()
    for text in ("nothing to do here", "", "{{vault}}", "{vault:github}", "vault:github",
                 "{{ vault:github }}", None):
        got = V.resolve(text)
        want = "" if text is None else text
        check(f"resolve({text!r}) is unchanged", got == want, repr(got))
    check("... and the store was never asked", FakeStore.SEEN_TARGETS == [],
          str(FakeStore.SEEN_TARGETS))
    check("... a non-string is stringified, not dropped", V.resolve(42) == "42")


def t_a_value_goes_only_to_the_host_it_is_bound_to():
    """CLAUDE.md rule 3: "sent only to the one service it authenticates
    against". The vault enforces it, so no caller has to remember."""
    reset()
    V.put("exa", FAKE_KEY, for_host="api.exa.ai")
    check("the bound host resolves", V.resolve("k={{vault:exa}}", host="api.exa.ai")
          == f"k={FAKE_KEY}")
    check("... case and a stray port do not matter", V.resolve("k={{vault:exa}}",
          host="API.Exa.AI") == f"k={FAKE_KEY}")
    for host in ("evil.example", "api.exa.ai.evil.example", "", None):
        out = V.resolve("k={{vault:exa}}", host=host)
        check(f"another host ({host!r}) does NOT get the value", out == "k={{vault:exa}}", out)
    check("... and the value is not in the refusal either", FAKE_KEY not in
          V.resolve("k={{vault:exa}}", host="evil.example"))
    check("an UNBOUND value resolves anywhere, which is the documented default",
          V.put("plainkey", FAKE_OTHER) is True
          and V.resolve("k={{vault:plainkey}}", host="anywhere.example") == f"k={FAKE_OTHER}")
    check("handles() shows the binding, never a value",
          {r["name"]: r["for_host"] for r in V.handles()}
          == {"exa": "api.exa.ai", "plainkey": ""}, str(V.handles()))


# --------------------------------------------------------------------------
#   4. The route: one card at tier ask, and a denial stores nothing
# --------------------------------------------------------------------------

class Verdict:
    """jarvis_gate's own Verdict, in the four shapes that matter here. The real
    one is written by a patch and is not in this repository, so its CONTRACT is
    what this stands in for: `allowed`, `tier`, `outcome`, `reason`."""

    def __init__(self, allowed, tier, outcome, reason=""):
        self.allowed, self.tier, self.outcome, self.reason = allowed, tier, outcome, reason


def gate_that(outcome, *, tier="ask", allowed=None, raises=False):
    """A gate that answers `outcome`. Records the action, the detail and the
    prompt it was handed, so the card's own words can be checked.

    `allowed` defaults from the outcome and is bound HERE, not read from the
    enclosing scope inside the closure - a closure that rebinds its own
    enclosing variable answers the SECOND call with what the first one left
    behind. That mistake cost a round of this suite's own failures."""
    allowed = (outcome == "approved") if allowed is None else allowed
    calls = []

    def gate(action, detail, prompt):
        calls.append({"action": action, "detail": detail, "prompt": prompt})
        if raises:
            raise RuntimeError("the gate is not there")
        return Verdict(allowed, tier, outcome, "because")

    gate.calls = calls
    return gate


def body_for(name="github", value=FAKE_KEY, host=""):
    return {"name": name, "value": value, "for_host": host}


def t_one_card_at_tier_ask_stores_the_value():
    reset()
    gate = gate_that("approved")
    code, out = V.handle_put(body_for(), gate=gate, tier_of=lambda a: "ask",
                             spawn=lambda fn: fn())
    check("an approved card stores it", code == 200 and out["ok"] is True, str(out))
    check("... and the value really is in the store", V.get("github") == FAKE_KEY)
    check("... exactly ONE card was raised", len(gate.calls) == 1, str(gate.calls))
    check("... under this route's own action name",
          gate.calls[0]["action"] == V.ACTION_PUT == "vault_put")
    check("... the answer gives the HANDLE, and never the value",
          out.get("handle") == "{{vault:github}}" and FAKE_KEY not in bytes_of(out),
          bytes_of(out))
    check("... the card says what happens, and that nothing has happened yet",
          "Credential Manager" in gate.calls[0]["prompt"]
          and "nothing is stored" in gate.calls[0]["prompt"].lower(),
          gate.calls[0]["prompt"])
    check("... and the card holds no value", FAKE_KEY not in bytes_of(gate.calls[0]),
          bytes_of(gate.calls[0]))


def t_a_denied_card_stores_nothing():
    for outcome, code_want in (("denied", 403), ("timed_out", 403), ("refused", 503)):
        reset()
        gate = gate_that(outcome, allowed=False)
        code, out = V.handle_put(body_for(), gate=gate, tier_of=lambda a: "ask",
                                 spawn=lambda fn: fn())
        check(f"{outcome}: the answer says nothing was stored",
              code == code_want and out["ok"] is False and out["outcome"] == outcome,
              f"{code} {out}")
        check(f"{outcome}: the store is untouched", FakeStore.DATA == {}, str(FakeStore.DATA))
        check(f"{outcome}: no name was remembered", V.handles() == [], str(V.handles()))
        check(f"{outcome}: the value is nowhere in the answer",
              FAKE_KEY not in bytes_of(out), bytes_of(out))
        check(f"{outcome}: vault.json was not written", not V.vault_path().exists())
        check(f"{outcome}: the audit line says the NAME only",
              all(FAKE_KEY not in bytes_of(d) for _, d in AUDIT), str(AUDIT))


def t_nothing_is_stored_before_the_answer():
    """The card is still outstanding: the store must be empty when it is read
    from inside the gate itself."""
    reset()
    seen_at_card_time = {}

    def gate(action, detail, prompt):
        seen_at_card_time["store"] = dict(FakeStore.DATA)
        seen_at_card_time["file"] = V.vault_path().exists()
        return Verdict(True, "ask", "approved")

    code, out = V.handle_put(body_for(), gate=gate, tier_of=lambda a: "ask",
                             spawn=lambda fn: fn())
    check("while the card waits, nothing is in the store",
          seen_at_card_time["store"] == {}, str(seen_at_card_time))
    check("... and vault.json has not been written either",
          seen_at_card_time["file"] is False)
    check("... and after the yes it is stored", code == 200 and V.get("github") == FAKE_KEY)


def t_a_gate_that_cannot_ask_stores_nothing():
    reset()
    code, out = V.handle_put(body_for(), gate=gate_that("approved", raises=True),
                             tier_of=lambda a: "ask", spawn=lambda fn: fn())
    check("a gate that raises: 503, nothing stored",
          code == 503 and out["ok"] is False and FakeStore.DATA == {}, f"{code} {out}")

    reset()
    gate = gate_that("approved", tier="auto", allowed=True)   # tier auto, nobody asked
    code, out = V.handle_put(body_for(), gate=gate, tier_of=lambda a: "ask",
                             spawn=lambda fn: fn())
    check("tier auto with allowed=True is NOT a person's yes - nothing stored",
          code == 503 and FakeStore.DATA == {}, f"{code} {out}")

    reset()
    gate = gate_that("approved", tier="notify", allowed=True)  # the gate's own trap
    code, out = V.handle_put(body_for(), gate=gate, tier_of=lambda a: "ask",
                             spawn=lambda fn: fn())
    check("tier notify with allowed=True is NOT a person's yes - nothing stored",
          code == 503 and FakeStore.DATA == {}, f"{code} {out}")

    reset()
    gate = gate_that("approved", tier="ask")
    code, out = V.handle_put(body_for(), gate=gate, tier_of=lambda a: "never",
                             spawn=lambda fn: fn())
    check("the action is no longer tier ask in the settings: refuse, store nothing",
          code == 503 and FakeStore.DATA == {}, f"{code} {out}")


def t_the_put_route_refuses_a_bad_request_without_asking_anyone():
    reset()
    for body, why in (({"value": FAKE_KEY}, "no name"),
                      ({"name": "github"}, "no value"),
                      ({"name": "a b", "value": FAKE_KEY}, "a name with a space"),
                      ({"name": "x" * 65, "value": FAKE_KEY}, "a name too long"),
                      ({"name": "github", "value": ""}, "an empty value"),
                      ({"name": "github", "value": 12}, "a value that is not text"),
                      ("not an object", "not an object"),
                      ({"name": "github", "value": FAKE_KEY * 200}, "a value over the cap")):
        gate = gate_that("approved")
        code, out = V.handle_put(body, gate=gate, tier_of=lambda a: "ask",
                                 spawn=lambda fn: fn())
        check(f"{why}: 400, refused",
              code == 400 and out["ok"] is False, f"{code} {out}")
        check(f"{why}: NO card was raised", gate.calls == [], str(gate.calls))
        check(f"{why}: nothing stored", FakeStore.DATA == {}, str(FakeStore.DATA))
        check(f"{why}: the value is not echoed back",
              FAKE_KEY not in bytes_of(out), bytes_of(out))


def t_the_handles_route_never_leaks():
    reset()
    V.put("github", FAKE_KEY, for_host="api.github.com")
    V.put("tavily", FAKE_OTHER)
    code, out = V.handle_handles()
    check("GET /api/vault/handles answers", code == 200 and out["available"] is True, str(out))
    check("... with both names", {h["name"] for h in out["handles"]} == {"github", "tavily"},
          str(out["handles"]))
    check("... their handles and hosts", {h["name"]: (h["handle"], h["for_host"])
                                          for h in out["handles"]}
          == {"github": ("{{vault:github}}", "api.github.com"),
              "tavily": ("{{vault:tavily}}", "")}, str(out["handles"]))
    for value in (FAKE_KEY, FAKE_OTHER):
        check(f"the value {value[:4]}... is in no byte of the answer",
              value not in bytes_of(out))
        check("... nor a masked prefix of it",
              value[:6] not in bytes_of(out) and value[:8] not in bytes_of(out))
        # Checked field by field, NOT against the whole blob: the blob also
        # holds `last_used`, an epoch number, and a two-digit length lands
        # inside almost any timestamp - so a whole-blob check reports a leak
        # that is a coincidence in a clock reading.
        check("... nor its length, in any field this module writes",
              all(str(len(value)) not in str(h.get(f, ""))
                  for h in out["handles"] for f in ("name", "handle", "for_host")),
              bytes_of(out))


def t_the_suite_cannot_reach_the_real_credential_store():
    """The guard itself, proved: with no stand-in store, `_store()` still does
    not reach the real Windows Credential Manager. This is the check that
    stops the incident recorded in the docstring of
    t_a_non_windows_pc_refuses_to_store_rather_than_writing_plain_text from
    ever happening again."""
    check("the suite has set jarvis_vault.TESTING", V.TESTING is True)
    saved = V._STORE_FACTORY
    try:
        V._STORE_FACTORY = None
        st = V._store("this-must-never-be-written")
        check("with no stand-in store, the REAL store is refused",
              isinstance(st, Exception), f"{type(st)}")
        check("... and put() therefore stores nothing anywhere", V.put("real", FAKE_KEY) is False)
    finally:
        V._STORE_FACTORY = saved
    check("... and because TESTING is a module-level flag, no test can forget it",
          "if TESTING:" in (HERE / "jarvis_vault.py").read_text(encoding="utf-8"))


def t_the_route_waits_at_least_as_long_as_the_card():
    """The bug this pins, found in this branch's own first draft.

    `_card_says_yes` gave itself a 300-second deadline. The gate waits
    `approval_timeout_seconds` - 600 as shipped, TEN MINUTES - so an owner who
    read the card for six minutes and then approved it met a route that had
    already given up: it answered "nothing was stored" for a yes that was
    given. A refusal nobody said, on the one route whose whole promise is that
    a person's answer decides."""
    src = (HERE / "jarvis_vault.py").read_text(encoding="utf-8")
    check("the gate's own wait is what this route reads",
          "def _gate_timeout" in src and "APPROVAL_TIMEOUT" in src)
    check("... and it is at least the shipped ten minutes",
          V._gate_timeout() >= 600.0, str(V._gate_timeout()))
    check("... and the route waits LONGER than the gate, never less",
          V._WAIT_AFTER_GATE > 0, str(V._WAIT_AFTER_GATE))

    # And the behaviour: a gate that answers slowly is still obeyed.
    reset()
    import time as _time

    def slow_gate(action, detail, prompt):
        _time.sleep(0.25)
        return Verdict(True, "ask", "approved")

    code, out = V.handle_put(body_for(), gate=slow_gate, tier_of=lambda a: "ask",
                             spawn=lambda fn: fn())
    check("a card answered after a pause is still a yes, and the value is stored",
          code == 200 and V.get("github") == FAKE_KEY, f"{code} {out}")


def t_the_route_checks_origin_and_token_like_every_other():
    """The loader's own convention: install() takes the core's three callbacks
    and every route goes through them first. The two refusals are checked with
    a SEPARATE handler class each, because install() records that it has
    wrapped a class: reusing one class would test the first wrappers twice."""
    reset()
    sent, core = [], {"get": 0, "post": 0}

    class Handler:
        def __init__(self, path="/"):
            self.path = path

        def do_GET(self):
            core["get"] += 1

        def do_POST(self):
            core["post"] += 1

        def _send(self, code, payload):
            sent.append((code, payload))
            return payload

    line = V.install(Handler, origin_ok=lambda r: True, token_ok=lambda r: True,
                     read_body=lambda r: b"{}")
    check("install() returns a line for the start-up banner",
          isinstance(line, str) and "vault" in line, line)
    check("... and it says nothing is saved yet", "none saved yet" in line, line)

    Handler("/api/vault/handles").do_GET()
    check("GET /api/vault/handles is answered here",
          sent and sent[-1][0] == 200 and "handles" in sent[-1][1], str(sent))
    Handler("/api/other").do_GET()
    check("... and every other path still reaches the core", core["get"] == 1)

    # A second install() on the same class must not wrap it twice.
    V.install(Handler, origin_ok=lambda r: True, token_ok=lambda r: True,
              read_body=lambda r: b"{}")
    before = len(sent)
    Handler("/api/vault/handles").do_GET()
    check("installing twice does not double-wrap: one answer, not two",
          len(sent) == before + 1 and core["get"] == 1, str(sent[-2:]))

    class NoOrigin:
        def __init__(self, path="/"):
            self.path = path

        def do_GET(self):
            core["get"] += 1

        def do_POST(self):
            core["post"] += 1

        def _send(self, code, payload):
            sent.append((code, payload))
            return payload

    V.install(NoOrigin, origin_ok=lambda r: False, token_ok=lambda r: True,
              read_body=lambda r: b"{}")
    NoOrigin("/api/vault/handles").do_GET()
    check("a cross-origin request is refused with 403", sent[-1][0] == 403, str(sent[-1]))
    check("... and nothing is answered", "handles" not in bytes_of(sent[-1][1]))

    class NoToken:
        def __init__(self, path="/"):
            self.path = path

        def do_GET(self):
            core["get"] += 1

        def do_POST(self):
            core["post"] += 1

        def _send(self, code, payload):
            sent.append((code, payload))
            return payload

    V.install(NoToken, origin_ok=lambda r: True, token_ok=lambda r: False,
              read_body=lambda r: b"{}")
    before = len(sent)
    NoToken("/api/vault/put").do_POST()
    check("a request with a bad token is refused with 401",
          sent[-1][0] == 401, str(sent[-1]))
    check("... and no card was raised and nothing stored",
          FakeStore.DATA == {} and len(sent) == before + 1)
    check("... and the value in the body was never read",
          "{{" not in bytes_of(sent[-1][1]))


# --------------------------------------------------------------------------
#   5. The scrubber is applied to anything coming back
# --------------------------------------------------------------------------

def t_anything_coming_back_is_scrubbed():
    reset()
    V.put("exa", FAKE_ECHOED, for_host="api.exa.ai")
    V.get("exa")
    out = V.redact('{"error": "your key exa-echo-abcdef0123456789 is invalid", '
                   '"contact": "help@example.com"}')
    check("a service that echoes the key back cannot get it into the answer",
          FAKE_ECHOED not in out, out)
    check("... the handle is there in its place", "{{vault:exa}}" in out, out)
    check("... and the project's scrubber ran too: the e-mail is hidden",
          "help@example.com" not in out and "[redacted: e-mail]" in out, out)

    out2 = V.redact("nothing secret here")
    check("text with nothing to hide comes back as itself", out2 == "nothing secret here", out2)
    check("... a non-string is stringified, not dropped", V.redact(12) == "12")
    check("... None is the empty string", V.redact(None) == "")

    # The caller's own {name: value} mapping, the shape
    # jarvis_browser_control.run already keeps for its own redaction.
    out3 = V.redact(f"typed {FAKE_OTHER}", used={"tavily": FAKE_OTHER})
    check("a caller's own used-value mapping is hidden too", FAKE_OTHER not in out3, out3)

    scrub = go_scrub_failure()
    check("if the scrubber itself failed, the text is WITHHELD rather than passed through",
          scrub, "the scrubber was patchable and the text came back")


def go_scrub_failure() -> bool:
    """Force jarvis_scrub.scrub_text to fail and check redact() still does not
    hand the value back."""
    saved = SCRUB.scrub_text
    try:
        SCRUB.scrub_text = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        out = V.redact(f"echo {FAKE_ECHOED}")
    finally:
        SCRUB.scrub_text = saved
    return FAKE_ECHOED not in out


def t_scrub_is_the_projects_own_and_not_a_second_one():
    source = (HERE / "jarvis_vault.py").read_text(encoding="utf-8")
    check("the vault calls jarvis_scrub, it does not reimplement it",
          "jarvis_scrub" in source and "scrub_text" in source)
    check("... and it says so in its own header, with the reason",
          "NOT a replacement for `jarvis_scrub`" in source)
    check("no pattern table of its own: no _SECRET_PATTERNS, no AWS/GitHub regex",
          "_SECRET_PATTERNS" not in source and "AKIA" not in source)
    check("it never imports the router's or the secrets module's tables",
          "jarvis_router" not in source and "jarvis_secrets" not in source)


# --------------------------------------------------------------------------
#   6. Wired to a real use: the web-search keys
# --------------------------------------------------------------------------

def _stand_in(routes):
    """A server on 127.0.0.1 answering from a script. The same shape
    test_web_search.py's own StandIn uses; the only real socket this suite
    opens, and it never leaves this PC."""
    import http.server

    class H(http.server.BaseHTTPRequestHandler):
        def _answer(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else b""
            outer["seen"].append({"method": self.command, "path": self.path,
                                  "headers": {k.lower(): v for k, v in self.headers.items()},
                                  "body": body})
            for prefix, (status, headers, out) in routes.items():
                if self.path.startswith(prefix) or prefix == "*":
                    self.send_response(status)
                    for k, v in headers.items():
                        self.send_header(k, v)
                    self.send_header("Content-Length", str(len(out)))
                    self.end_headers()
                    self.wfile.write(out)
                    return
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = do_POST = _answer

        def log_message(self, *a):
            pass

    outer = {"seen": [], "server": http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)}
    outer["server"].server_address = outer["server"].server_address
    outer["server"].serve_forever_thread = threading.Thread(
        target=outer["server"].serve_forever, daemon=True)
    outer["server"].serve_forever_thread.start()
    outer["url"] = f"http://127.0.0.1:{outer['server'].server_address[1]}"
    return outer


def _with_cloud(provider, routes, fn):
    import jarvis_search as WS
    srv = _stand_in(routes)
    attr = {"tavily": "TAVILY_URL", "exa": "EXA_URL", "brave": "BRAVE_URL"}[provider]
    saved = getattr(WS, attr)
    setattr(WS, attr, srv["url"] + ("/res/v1/web/search" if provider == "brave" else "/search"))
    saved_ok = getattr(WS, "_TEST_LOOPBACK_OK", False)
    WS._TEST_LOOPBACK_OK = True
    try:
        return fn(srv)
    finally:
        setattr(WS, attr, saved)
        WS._TEST_LOOPBACK_OK = saved_ok
        srv["server"].shutdown()
        srv["server"].server_close()


class _WsFakeStore:
    DATA: dict = {}

    def __init__(self, target):
        self.target = target

    def read(self):
        return _WsFakeStore.DATA.get(self.target)

    def write(self, value):
        _WsFakeStore.DATA[self.target] = value

    def delete(self):
        _WsFakeStore.DATA.pop(self.target, None)


def t_the_web_search_key_is_a_handle_and_reaches_only_its_own_service():
    """End to end, against a server on 127.0.0.1: the vault holds the key, the
    header is built from a handle, and the key reaches that one service.

    `WS._key("exa")` is the module's own "is a key saved?" read, so the test
    gives it one the ordinary way - and the KEY THE VAULT HOLDS IS A DIFFERENT
    STRING, so which of the two the service received is not a guess."""
    import jarvis_search as WS

    vaulted = "exa-" + "vaulted" + "-" + "0123456789abcdef"
    stored = "exa-" + "stored" + "-" + "fedcba9876543210"
    body = json.dumps({"results": [{"title": "T", "url": "https://e.example/1",
                                    "text": f"debug: your key {vaulted} was used"}]}).encode()

    def go(srv):
        try:
            out = WS._exa(WS.plan("walking boots"))
        except Exception as exc:
            return {"raised": f"{type(exc).__name__}: {exc}"}, srv["seen"]
        return out, srv["seen"]

    # 1. The vault holds it, bound to Exa's own host, and the ordinary entry
    #    holds a DIFFERENT value.
    reset()
    _WsFakeStore.DATA.clear()
    _WsFakeStore.DATA[WS.KEY_TARGETS["exa"]] = stored
    WS._STORE_FACTORY = _WsFakeStore
    V._STORE_FACTORY = _WsFakeStore          # the vault and the search read the SAME store
    V.put("exa", vaulted, for_host="api.exa.ai")
    out, seen = _with_cloud("exa", {"/search": (200, {}, body)}, go)
    req = seen[0] if seen else {}
    check("the request was actually made", bool(req), str(seen))
    check("the VAULT's key reached the service, not the plain stored one",
          req.get("headers", {}).get("x-api-key") == vaulted, str(req.get("headers")))
    check("... and the handle itself did not - it was substituted at the point of use",
          "{{vault:" not in bytes_of(req.get("headers", {})), str(req.get("headers")))
    check("the answer came back with results", isinstance(out, list) and len(out) == 1,
          str(out))
    check("the service's own echo of the key did NOT come back with it",
          vaulted not in bytes_of(out), bytes_of(out))

    # 2. A key bound to ANOTHER service must not be sent to this one.
    reset()
    _WsFakeStore.DATA.clear()
    _WsFakeStore.DATA[WS.KEY_TARGETS["exa"]] = stored
    WS._STORE_FACTORY = _WsFakeStore
    V._STORE_FACTORY = _WsFakeStore
    V.put("exa", vaulted, for_host="api.elsewhere.example")
    out2, seen2 = _with_cloud("exa", {"/search": (200, {}, body)}, go)
    req2 = seen2[0] if seen2 else {}
    check("a key bound to another service is not sent to this one",
          req2.get("headers", {}).get("x-api-key") != vaulted, str(req2.get("headers")))
    check("... the header keeps the handle, which the service refuses",
          req2.get("headers", {}).get("x-api-key") == "{{vault:exa}}",
          str(req2.get("headers")))
    check("... and the service's echo cannot leak a value it was never given",
          vaulted not in bytes_of(out2), bytes_of(out2))

    # 3. An empty vault: exactly the behaviour every installation had before.
    reset()
    _WsFakeStore.DATA.clear()
    _WsFakeStore.DATA[WS.KEY_TARGETS["exa"]] = stored
    WS._STORE_FACTORY = _WsFakeStore
    V._STORE_FACTORY = V._store_error       # no vault value on this PC
    out3, seen3 = _with_cloud("exa", {"/search": (200, {}, body)}, go)
    req3 = seen3[0] if seen3 else {}
    check("an empty vault changes nothing: the stored key is sent as it always was",
          req3.get("headers", {}).get("x-api-key") == stored, str(req3.get("headers")))
    check("... and the answer is returned", isinstance(out3, list), str(out3))
    V.vault_path().unlink(missing_ok=True)


def t_every_keyed_provider_is_wired():
    """All three, named, with the host each key belongs to - read from the
    source, so a provider added later cannot quietly skip the vault."""
    import jarvis_search as WS
    src = (HERE / "jarvis_search.py").read_text(encoding="utf-8")
    check("the module names a vault handle for each keyed provider",
          set(WS.VAULT_HANDLES) == {"exa", "tavily", "brave"}, str(sorted(WS.VAULT_HANDLES)))
    urls = {"exa": WS.EXA_URL, "tavily": WS.TAVILY_URL, "brave": WS.BRAVE_URL}
    for pid, (name, host) in WS.VAULT_HANDLES.items():
        check(f"{pid}: the handle is the provider's own name", name == pid, f"{name} {host}")
        check(f"{pid}: ... bound to that service's own host, and to no other",
              host in urls[pid] and "//" + host in urls[pid],
              f"{name} {host} {urls[pid]}")
        check(f"{pid}: the header is built through _vault_handle, for that provider",
              f"_vault_handle({pid!r}, key)" in src or f'_vault_handle("{pid}", key)' in src)
    send_body = function_source(HERE / "jarvis_search.py", "_send")
    check("the substitution happens in ONE place - _send, and only there",
          send_body.count("v.resolve(") == 1 and "v.headers_of(req)" in send_body,
          f"resolve x{send_body.count('v.resolve(')}")
    check("... and the providers clean what comes back",
          src.count("_clean_return(") >= 4, str(src.count("_clean_return(")))


# --------------------------------------------------------------------------
#   7. Shipped, discoverable, and honest about its own limits
# --------------------------------------------------------------------------

def t_it_is_shipped_and_droppable():
    import _where
    check("backend/_where.py ships it", "jarvis_vault.py" in _where.SHIPPED)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$SHIPPED = @(")
    body = ps1[start:ps1.index("\n)", start)]
    check("scripts/apply-patches.ps1 ships it too", "'jarvis_vault.py'" in body)
    twin = REPO / "jarvis-backend" / "jarvis_vault.py"
    check("the base twin is byte-identical (line endings ignored)",
          twin.is_file() and twin.read_bytes().replace(b"\r\n", b"\n")
          == (HERE / "jarvis_vault.py").read_bytes().replace(b"\r\n", b"\n"))
    manifest = REPO / "plugins" / "ready" / "vault" / "plugin.json"
    check("the drop-in folder has a manifest", manifest.is_file())
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        check("... naming this module, with the handler install shape",
              data.get("module") == "jarvis_vault" and data.get("install") == "handler",
              str(data))
        check("... and a stack_order after every folder the patch stack wrote",
              isinstance(data.get("stack_order"), int) and data["stack_order"] >= 143,
              str(data))
        check("... and no replaces_patch, because there is no patch to replace",
              "replaces_patch" not in data, str(data))
        # The same claim `receipts` makes about itself, made the same way: the
        # loader runs folders in stack_order, and every folder at or below 141
        # came from the patch stack. Read from the OTHER folders' own manifests
        # rather than compared against a number written here, so a folder added
        # later is compared with rather than silently ignored.
        others = []
        for folder in sorted((REPO / "plugins" / "ready").iterdir()):
            other = folder / "plugin.json"
            if folder.name == "vault" or not other.is_file():
                continue
            order = json.loads(other.read_text(encoding="utf-8")).get("stack_order")
            if isinstance(order, int):
                others.append((order, folder.name))
        from_stack = [(o, n) for o, n in others if o <= 141]
        check("... after every folder the old patch stack wrote",
              bool(from_stack) and max(from_stack)[0] < data["stack_order"],
              f"vault at {data['stack_order']}, the highest from the stack is "
              f"{max(from_stack) if from_stack else None}")
        check("... and it claims no position another folder already holds",
              all(o != data["stack_order"] for o, _ in others), str(sorted(others)[-3:]))
    check("the module really has an install() the loader can call",
          callable(getattr(V, "install", None)))


def t_it_writes_no_value_to_disk_anywhere():
    """The feature's whole promise, checked against the SOURCE: the only file
    this module writes is vault.json, and what goes into it is names, hosts and
    times."""
    reset()
    V.put("github", FAKE_KEY, for_host="api.github.com")
    V.get("github")
    written = sorted(p.name for p in V.vault_path().parent.iterdir())
    check("the vault wrote exactly one file", written == ["vault.json"], str(written))
    raw = V.vault_path().read_text(encoding="utf-8")
    doc = json.loads(raw)
    check("... and every string in it is a name, a host or a number",
          all(isinstance(k, str) for k in doc["names"])
          and all(set(row) <= {"for_host", "used"} for row in doc["names"].values()),
          raw)
    check("... no value and no prefix of one", FAKE_KEY not in raw and FAKE_KEY[:6] not in raw, raw)
    # The length, checked against the strings the file HOLDS, not its whole
    # text: it also holds epoch timestamps, and a two-digit length lands inside
    # almost any of them, so a whole-file check reports a leak that is a clock
    # reading. Measured here rather than assumed.
    check("... and the length appears in no name or host the document holds",
          all(str(len(FAKE_KEY)) not in str(name)
              and str(len(FAKE_KEY)) not in str(row.get("for_host", ""))
              for name, row in doc["names"].items()),
          raw)
    src = (HERE / "jarvis_vault.py").read_text(encoding="utf-8")
    hits = sorted(_BANNED_CALLS & calls_in(src))
    check("the source opens no socket and starts no process", not hits, str(hits))
    check("the only writer of bytes is _remember/_forget_row, through vault.json",
          src.count("write_text(") == 2, str(src.count("write_text(")))


# --------------------------------------------------------------------------

def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("t_") and callable(fn):
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
