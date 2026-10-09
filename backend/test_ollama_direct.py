"""Where each chat lane really goes: Ollama for the local one, and the
service behind it for a cloud one.

`/api/chat`'s completion request always went to `{JARVIS_URL}/v1/chat/completions`
- OpenJarvis's own port and API shape - whatever lane was chosen, local or
not. OpenJarvis was never actually installed as part of this setup, so every
local turn was one `_open()` call away from a 503 it could never recover
from. `ollama-direct.patch` added `_completions_url(lane)`, which sends the
local lane to Ollama's own OpenAI-compatible endpoint instead.

WHAT CHANGED ON 2026-10-06, AND WHY THIS TEST READS AS IT DOES. The cloud half
of that function was a placeholder: a non-local lane went to `JARVIS_URL` too,
and the patch's own comment called itself "the one place that needs a real
answer". The owner made that decision (docs/ACCOUNT-KEYS-DESIGN.md section 5
and part C): a cloud lane goes through `jarvis_chatbot_api.py`'s adapter family
- HTTPS to the service's own pinned host, the key from Windows Credential
Manager, the monthly money limit, the answer-length cap, and a redirect
refused - and the service behind it is DeepSeek. This test used to assert the
placeholder. It now asserts the real thing, which is not the same test with a
different string: a cloud lane reaches DeepSeek's own address, asks for
DeepSeek's own model name, carries DeepSeek's own key, and is answered LOCALLY
when the owner's monthly limit cannot pay for it - never sent to a paid
service, and never quietly reported as a cloud answer.

AND WHERE THAT DECISION NOW LIVES. The first version of it lived in the HUD:
`_completions_url` called `cloud_lane`, `lane_key`, `lane_service` and
`ready_for` itself and kept what it decided in three names of its own, which
`_auth_headers` then read - and the block that did it had grown to about sixty
added lines, all of it around `_open`, whose lines are `cloud-one-turn.patch`'s
context. Every one of those lines is a line a later patch has to anchor on, so
the resolution moved OUT to `jarvis_chatbot_api.py`'s ONE seam: `lane_state(lane)`
resolves a whole lane (service, model, address, key, cap, and the module's own
sentence for why it cannot be used) and remembers it on the calling THREAD;
`last_lane_state()` reads that back. `_completions_url` now asks once and puts
the answer's model on the request; `_auth_headers` reads the key back from the
same place rather than from a name in the HUD. `FakeApi` below is that seam,
which is why it stands in for two functions rather than four.

AND WHICH `body` THE MODEL GOES ON (2026-10-06, the same day). "Puts the
answer's model on the request" was not true of the first version of that
sentence's code: `_completions_url` is nested in `do_POST`, where a bare `body`
is do_POST's OWN PARSED REQUEST - so `body["model"] = _state["model"]` wrote the
service's model onto an object nothing serialises, and the request that went out
kept the LANE's name (`jarvis-escalate`). DeepSeek was reached correctly and
asked for a model that does not exist. That is why `_completions_url` takes the
body as a PARAMETER now, and why `_sent_by_open()` below runs the file's two
functions WHERE THEY REALLY LIVE: lifted on its own, `body` becomes a namespace
global (which is the wrong object by construction), and with no `body` at all
the lift dies with `NameError: name 'body' is not defined` - the same accident,
seen from the other side. `t_the_model_is_put_on_a_body_the_helper_owns()` is
the half that still runs on a machine with no `jarvis_hud.py`.

This test executes the real `_completions_url`, the real `_open` and the real
`_auth_headers`, lifted from the source with ast - the same technique
test_degrade_filter.py already uses on this exact file, for this exact reason.
It cannot start a real HTTP server or reach a real Ollama or DeepSeek; that part
only the owner's own machine can prove. What it does instead is run the lifted
text with a stand-in `jarvis_chatbot_api` in `sys.modules`, so the whole
decision can be exercised here, with no socket.

    python3 test_ollama_direct.py
"""
import ast
import json
import sys
import textwrap
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, missing, explain
import _stack
SRC = BACKEND / "jarvis_hud.py"

FAILED, PASSED = [], []
SKIPPED = []

LOCAL = "qwen3:8b"
LANE = "jarvis-escalate"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
PAIRING_TOKEN = "the-pairing-token"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (It used to be check("SKIP - ...", True) - a condition of
    the constant True, so it printed as a pass and was counted as one.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


class FakeApi:
    """What `jarvis_chatbot_api` hands back on a PC where DeepSeek is set up.

    The one seam, for a whole lane: `lane_state(lane)` resolves the service,
    the model the SERVICE is asked for, its pinned address, its key and its
    cap, and returns the module's own sentence (`why`) when the lane cannot be
    used at all. It remembers what it resolved for this thread, exactly as the
    real module does, and `last_lane_state()` reads it back - which is how the
    HUD's header builder gets the key without any caller passing it around.

    `calls` is what the HUD asked for, so a test can say that the LOCAL lane is
    asked for as the empty name (which is how the real module is told to clear
    a cloud lane's key off the thread)."""

    def __init__(self, *, ready=True, model="deepseek-flash",
                 key="the-deepseek-key", why="No monthly money limit is set for DeepSeek."):
        self.ready, self.model, self.key, self.why = ready, model, key, why
        self.calls = []
        self.state = {"lane": "", "pid": "", "model": "", "host": "", "url": "",
                      "key": "", "cap": 0, "problem": ""}

    def lane_state(self, lane):
        self.calls.append(lane)
        lane = str(lane or "")
        if not lane:
            self.state = {"lane": "", "pid": "", "model": "", "host": "", "url": "",
                          "key": "", "cap": 0, "problem": ""}
        elif not self.ready:
            self.state = {"lane": lane, "pid": "deepseek_api", "model": self.model,
                          "host": "", "url": "", "key": "", "cap": 0, "problem": self.why}
        else:
            self.state = {"lane": lane, "pid": "deepseek_api", "model": self.model,
                          "host": "api.deepseek.com", "url": DEEPSEEK_URL,
                          "key": self.key, "cap": 8000, "problem": ""}
        return dict(self.state)

    def last_lane_state(self):
        return dict(self.state)


def _lifted(source, name):
    """The one top-level `def name(` in `source`, as a compiled code object."""
    found = [n for n in ast.walk(ast.parse(source))
             if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(found) != 1:
        raise AssertionError(f"expected exactly one {name}, found {len(found)}")
    return compile(ast.Module(body=[found[0]], type_ignores=[]), "<lifted>", "exec")


def _with_api(api, fn):
    """Run `fn()` with a stand-in jarvis_chatbot_api installed in sys.modules,
    the way the real HUD has the real one."""
    saved = sys.modules.get("jarvis_chatbot_api")
    sys.modules["jarvis_chatbot_api"] = api
    try:
        return fn()
    finally:
        if saved is not None:
            sys.modules["jarvis_chatbot_api"] = saved
        else:
            sys.modules.pop("jarvis_chatbot_api", None)


def _completions(source, api, lane=LANE):
    """(url, body, api) after running the REAL `_completions_url` for `lane`.

    `body` is the request body the real `_open` has in hand - the same dict the
    helper is handed and may put the service's model on. It is passed in, as
    the file passes it, because it must be: the helper reads no `body` from
    around itself (see `_sent_by_open`)."""
    ns = {"OLLAMA_URL": "http://127.0.0.1:11434", "JARVIS_URL": "http://127.0.0.1:8000",
          "local_model": LOCAL, "body": {"model": lane}}
    _with_api(api, lambda: exec(_lifted(source, "_completions_url"), ns))
    url = _with_api(api, lambda: ns["_completions_url"](lane, ns["body"]))
    return url, ns["body"], api


def _nested(source, name):
    """(verbatim source, line) of the one `def name(` nested inside do_POST."""
    lines = source.splitlines()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == "do_POST":
            for kid in node.body:
                if isinstance(kid, ast.FunctionDef) and kid.name == name:
                    return "\n".join(lines[kid.lineno - 1:kid.end_lineno]), kid.lineno
    raise AssertionError(f"{name} is not nested in do_POST")


class _Request:
    """The one thing `_open` does with `urllib.request.Request`."""

    def __init__(self, url, data=None, headers=None, method=None):
        self.full_url, self.data, self.headers, self.method = url, data, headers, method


class _Sent:
    """Stands in for `urllib.request`: it keeps the request `_open` builds."""

    def __init__(self):
        self.url, self.headers, self.raw = None, {}, ""
        self.body = None

    def open(self, req, timeout=None):
        self.url, self.headers, self.raw = req.full_url, req.headers, req.data.decode("utf-8")
        self.body = json.loads(self.raw)
        return {"sent": True}


def _sent_by_open(source, api, lane=LANE):
    """(sent, outer_body) - the REAL `_open` run WHERE IT REALLY LIVES.

    `_completions_url` and `_open` are pasted back, verbatim, inside a stand-in
    outer function that holds do_POST's own parsed `body` - because that is the
    scope the file gives them, and the whole point of this check. Lifting
    `_completions_url` on its own (what every other cloud check here does) puts
    `body` in the namespace as a GLOBAL: the wrong object by construction, and
    the reason the first version of this helper could write the service's model
    onto do_POST's parsed request while a lift-only test watched the right dict
    and passed.

    `outer_body` is that parsed request, so a check can say the write did NOT
    land on it."""
    comp, _ = _nested(source, "_completions_url")
    opn, _ = _nested(source, "_open")
    sent = _Sent()
    request = json.dumps({"model": lane, "stream": True, "messages": [
        {"role": "user", "content": "explain in detail how they compare"}]})
    # Eight spaces in: these are methods' bodies, so the definitions go back at
    # exactly the depth they have in the file, and `body` is the outer local the
    # real do_POST has.
    wrapper = ("class _Handler:\n"
               "    def do_POST(self):\n"
               f"        raw = {request!r}.encode('utf-8')\n"
               "        body = json.loads(raw or b\"{}\")\n"
               f"{comp}\n"
               f"{opn}\n"
               f"        _open({lane!r})\n"
               "        return body\n")
    ns = {"OLLAMA_URL": "http://127.0.0.1:11434", "JARVIS_URL": "http://127.0.0.1:8000",
          "local_model": LOCAL, "JARVIS_API_KEY": PAIRING_TOKEN, "json": json,
          "isinstance": isinstance, "_CHAT_CLIENT_FIELDS": set(),
          "_chat_client_fields_off": lambda msgs: msgs,
          "payload": json.loads(request),
          "urllib": types.SimpleNamespace(
              request=types.SimpleNamespace(Request=_Request, urlopen=sent.open))}
    _with_api(api, lambda: exec(_lifted(source, "_auth_headers"), ns))
    _with_api(api, lambda: exec(compile(wrapper, "<do_POST-like>", "exec"), ns))
    outer = _with_api(api, lambda: ns["_Handler"]().do_POST())
    return sent, outer


def _auth(source, api):
    """The real `_auth_headers`, ready to call as many times as a request does.
    What it reads is `api`'s remembered state, so `_completions` must have run
    first for a cloud lane - exactly the order the real request uses."""
    ns = {"JARVIS_API_KEY": PAIRING_TOKEN}
    _with_api(api, lambda: exec(_lifted(source, "_auth_headers"), ns))
    return lambda extra=None: _with_api(api, lambda: ns["_auth_headers"](extra))


def t_local_lane_goes_to_ollama():
    if missing("jarvis_hud.py"):
        return skip(explain())
    src = SRC.read_text(encoding="utf-8")
    api = FakeApi(ready=False)
    url, body, _ = _completions(src, api, lane=LOCAL)
    check("the local lane resolves to Ollama's own endpoint",
          url == "http://127.0.0.1:11434/v1/chat/completions", url)
    check("... and it is asked for as the module's empty lane, which clears the thread's answer",
          api.calls == [""], api.calls)
    check("... and the request keeps the local model's own name", body["model"] == LOCAL, body)


def t_a_cloud_lane_goes_to_the_service_behind_it():
    """The real answer to the old placeholder. `jarvis-escalate` is a lane name
    from the shipped degrade_chain; once the service behind it is set up, the
    request goes to THAT service's own https address - not JARVIS_URL, not
    Ollama - and asks for THAT service's model."""
    if missing("jarvis_hud.py"):
        return skip(explain())
    src = SRC.read_text(encoding="utf-8")
    api = FakeApi()
    url, body, _ = _completions(src, api)
    check("a cloud lane resolves to the cloud service's own endpoint",
          url == DEEPSEEK_URL, url)
    check("... and not to JARVIS_URL's own port any more", "127.0.0.1:8000" not in url, url)
    check("... and not to Ollama, which has no such model", "11434" not in url, url)
    check("... and the request asks for the SERVICE's model, not the lane's name",
          body["model"] == "deepseek-flash", body)
    check("... because the HUD asked the module, and the lane's own name is what it asked with",
          api.calls == [LANE], api.calls)
    check("... and the module is where the key that goes with that address comes from",
          api.last_lane_state()["key"] == "the-deepseek-key", api.last_lane_state())


def t_a_lane_that_cannot_be_paid_for_is_answered_locally():
    """When `lane_state()` comes back with no address - no key saved, a model
    with no price, the month's money limit reached, a message it cannot pay for
    - nothing is sent to a paid service at all. The lane goes to the LOCAL
    address instead: this PC answers, nothing is spent, and the request keeps
    the lane's own name and Jarvis's own pairing token, exactly as a local turn
    always did."""
    if missing("jarvis_hud.py"):
        return skip(explain())
    src = SRC.read_text(encoding="utf-8")
    api = FakeApi(ready=False)
    url, body, _ = _completions(src, api)
    check("an unpaid-for cloud lane is answered on this PC's own Ollama",
          url == "http://127.0.0.1:11434/v1/chat/completions", url)
    check("... never sent to the cloud host without a resolved lane",
          "api.deepseek.com" not in url, url)
    check("... and no cloud key is left on the thread", api.last_lane_state()["key"] == "",
          api.last_lane_state())
    check("... and the module's own words for why are what the caller has to report",
          api.last_lane_state()["problem"] == "No monthly money limit is set for DeepSeek.",
          api.last_lane_state())
    check("... and the request keeps the lane's own name, because this PC answers it",
          body["model"] == LANE, body)


def t_the_request_uses_the_lane_key_not_the_pairing_token():
    """Rule 3. The pairing token authenticates THIS PC's own server; a cloud
    service must get that service's own key and nothing else. The one place any
    request's Authorization header is built reads back what the resolved lane
    left on this thread, and a local lane behaves exactly as it did before."""
    if missing("jarvis_hud.py"):
        return skip(explain())
    src = SRC.read_text(encoding="utf-8")
    api = FakeApi()
    auth = _auth(src, api)
    local = auth({"Content-Type": "application/json"})
    check("a local request still carries Jarvis's own pairing token",
          local.get("Authorization") == f"Bearer {PAIRING_TOKEN}", local)
    # What a resolved cloud lane leaves behind, a moment earlier in the request.
    _completions(src, api)
    cloud = auth({"Content-Type": "application/json"})
    check("a cloud request carries the SERVICE's key instead",
          cloud.get("Authorization") == "Bearer the-deepseek-key", cloud)
    check("... and the pairing token is not sent to the cloud service at all",
          PAIRING_TOKEN not in json.dumps(cloud), cloud)
    # A lane this PC cannot pay for goes to its OWN Ollama, which wants the
    # pairing token - so the empty key must not be mistaken for "no token".
    unpaid = FakeApi(ready=False)
    _completions(src, unpaid)
    check("... and a lane that could not be resolved leaves the pairing token alone",
          _auth(src, unpaid)({}).get("Authorization") == f"Bearer {PAIRING_TOKEN}",
          _auth(src, unpaid)({}))


def t_the_bytes_on_the_wire_name_the_services_model():
    """The headline of the whole cloud lane, checked on the bytes `_open`
    builds - not on a body handed to the helper by the test.

    `jarvis-escalate` is meant to reach DeepSeek and be asked for DeepSeek's own
    model. Until 2026-10-06 the request that really went out carried the LANE's
    name (`"model": "jarvis-escalate"`), because the helper wrote the resolved
    model onto do_POST's parsed request - an object nothing serialises - while
    every lift-only check here watched the dict it had passed in and passed.
    This runs the two functions in their own scope and reads the JSON."""
    if missing("jarvis_hud.py"):
        return skip(explain())
    src = SRC.read_text(encoding="utf-8")
    api = FakeApi()
    sent, outer = _sent_by_open(src, api)
    check("the bytes that go out ask the SERVICE for its model, not the lane's name",
          sent.body.get("model") == "deepseek-flash", sent.body)
    check("... and that is the model the module resolved for the lane it was asked about",
          api.calls == [LANE] and api.last_lane_state()["model"] == sent.body["model"],
          (api.calls, api.last_lane_state()))
    check("... so the lane's own name is on nothing that leaves the process",
          LANE not in sent.raw, sent.raw)
    check("... and the request is the cloud one, at the service's own address",
          sent.url == DEEPSEEK_URL, sent.url)
    check("... carrying the service's own key",
          sent.headers.get("Authorization") == "Bearer the-deepseek-key", sent.headers)
    check("... and do_POST's own parsed request was left alone (the model is not written to it)",
          outer.get("model") == LANE, outer)


def t_a_local_turn_is_completely_unchanged_by_that():
    """The same run for the LOCAL lane: Ollama's address, the local model's own
    name on the bytes, Jarvis's own pairing token, and nothing written to
    do_POST's parsed request either."""
    if missing("jarvis_hud.py"):
        return skip(explain())
    src = SRC.read_text(encoding="utf-8")
    api = FakeApi()
    sent, outer = _sent_by_open(src, api, lane=LOCAL)
    check("a local turn still goes to Ollama's own endpoint",
          sent.url == "http://127.0.0.1:11434/v1/chat/completions", sent.url)
    check("... keeps the local model's own name on the bytes",
          sent.body.get("model") == LOCAL, sent.body)
    check("... and still carries Jarvis's pairing token",
          sent.headers.get("Authorization") == f"Bearer {PAIRING_TOKEN}", sent.headers)
    check("... and nothing was written to do_POST's parsed request",
          outer.get("model") == LOCAL, outer)


def t_the_model_is_put_on_a_body_the_helper_owns():
    """The shape of that bug, read from the PATCH'S own text - the one check
    here that also runs on a machine with no `jarvis_hud.py`.

    A `body[...]` write inside `_completions_url` is only the request that is
    sent if `body` is one of the function's OWN parameters. With no parameter,
    the name is read from around the function - do_POST's parsed request - and
    the request goes out under the lane's name. Read from
    `ollama-direct.patch`'s added lines, this fails on the text that shipped the
    bug and passes on the fix."""
    direct = (HERE / "ollama-direct.patch").read_text(encoding="utf-8")
    added = [(hunk, lines) for hunk, lines in
             ((h, [l[1:] for l in h.splitlines() if l.startswith("+")])
              for h, _pre in _stack.hunks(direct, "jarvis_hud.py"))
             if any("def _completions_url(" in l for l in lines)]
    if not added:
        return check("ollama-direct.patch adds a `_completions_url`", False,
                     "no added `def _completions_url(` line in the patch")
    helper = ast.parse(textwrap.dedent("\n".join(added[0][1])))
    fn = [n for n in ast.walk(helper)
          if isinstance(n, ast.FunctionDef) and n.name == "_completions_url"][0]
    params = {a.arg for a in fn.args.args}
    writes = [n for n in ast.walk(fn)
              if isinstance(n, ast.Assign)
              and any(isinstance(t, ast.Subscript) and getattr(t.value, "id", "") == "body"
                      for t in n.targets)]
    check("the helper writes the resolved model to a name", bool(writes),
          "no `body[...] = ...` line found in the added helper")
    check("... and that name is the helper's OWN parameter, not a name read from around it",
          bool(writes) and "body" in params, f"parameters are {sorted(params)}")
    check("... and _open hands it the body it is about to send",
          "_completions_url(lane, body)," in "".join(
              l[1:] + "\n" for l in direct.splitlines()
              if l.startswith("+") and not l.startswith("+++")),
          "expected the call to read `_completions_url(lane, body),`")


def t_the_error_message_names_the_right_service():
    """The 503 the owner sees when a lane cannot be answered. The local half's
    advice has always been there; the cloud half's real wording belongs to
    `chat-stream.patch`, which rewrites that whole block later in the stack.
    `ollama-direct.patch` only LIFTS the block, word for word, so that patch has
    the text it anchors on - it no longer names a service or a reason here.

    Read from the patches rather than from the HUD: the words live in them, and
    on a machine with no `jarvis_hud.py` there is nothing else to read."""
    src = SRC.read_text(encoding="utf-8") if not missing("jarvis_hud.py") else ""
    direct = (HERE / "ollama-direct.patch").read_text(encoding="utf-8")
    stream = (HERE / "chat-stream.patch").read_text(encoding="utf-8")
    check("the local-lane failure mentions Ollama's own start command",
          "ollama serve" in stream, "expected the literal `ollama serve` advice in chat-stream.patch")
    check("the local-lane message is conditioned on lane == local_model, not unconditional",
          "if lane == local_model else" in stream,
          "expected the ternary picking the message by lane")
    check("ollama-direct no longer writes cloud-lane wording of its own",
          "_cloud_model" not in direct and "is not answering at" not in direct,
          "cloud wording found in ollama-direct.patch")
    check("... it only lifts the block, in the words the stack already had",
          "unreachable_msg = (" in direct
          and 'f"Ollama is not answering on {OLLAMA_URL}. "' in direct,
          "expected the 503 lifted with its own words")
    # WHAT THE SECOND HALF MUST ASK FOR (corrected 2026-10-09). It used to
    # require the literal absence of "answers at {JARVIS_URL}" - but the NEW,
    # correct cloud sentence contains that phrase: "The cloud model is not set
    # up on this PC - nothing answers at {JARVIS_URL}. Pick the local model and
    # ask again." So the check demanded the absence of a phrase that is inside
    # the very wording it was asking for, and could never pass on a machine with
    # a patched jarvis_hud.py. It passed in CI only because `src` is empty
    # there - green everywhere except the owner's PC, the one place this suite
    # exists to check.
    #
    # The sentence that really did tell the owner to act on JARVIS_URL alone is
    # the OLD one, and that is what is gone: "Jarvis is not answering on
    # {JARVIS_URL}. Start it with `uv run jarvis serve`." - a program this setup
    # never installs (chat-stream.patch's own comment says so).
    check("... so the cloud 503's wording is chat-stream's, and nothing in the HUD "
          "still tells the owner to act on JARVIS_URL alone",
          "The cloud model is not set up on this PC" in stream
          and (not src or "Jarvis is not answering on" not in src),
          "expected chat-stream.patch to carry the cloud half, and the old "
          "`Jarvis is not answering on {JARVIS_URL}` sentence to be gone")


if __name__ == "__main__":
    for fn in (t_local_lane_goes_to_ollama,
               t_a_cloud_lane_goes_to_the_service_behind_it,
               t_a_lane_that_cannot_be_paid_for_is_answered_locally,
               t_the_request_uses_the_lane_key_not_the_pairing_token,
               t_the_bytes_on_the_wire_name_the_services_model,
               t_a_local_turn_is_completely_unchanged_by_that,
               t_the_model_is_put_on_a_body_the_helper_owns,
               t_the_error_message_names_the_right_service):
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
