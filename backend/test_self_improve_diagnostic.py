"""test_self_improve_diagnostic.py - the two READ-ONLY routes, and the walls
around them.

    python3 backend/test_self_improve_diagnostic.py

WHAT THIS PROVES, AND WHY EACH CHECK CAN FAIL

`jarvis_self_improve.install()` is what the drop-in folder
`plugins/ready/self-improve/` calls. It adds two GET routes and nothing else:

    GET /api/self-improve/diagnose?q=<question>
    GET /api/self-improve/contract?model=<name>

The suite drives the route's whole answer through a stand-in for the core's
Handler (the same shape `test_jarvis_plugins.py` and `test_receipts.py` use),
so no owner's PC, no Ollama and no socket is needed:

  * the routes are answered only AFTER the core's own origin and token checks,
    and both refusals are plain;
  * a question that is empty or longer than the module's own limit is a 400 and
    NOTHING is read (a spy proves the source was never searched); a question at
    exactly the limit IS read, so the boundary is the limit and not an accident;
  * a happy diagnosis carries a citation whose quote is re-read from disk, and
    a citation's quote is SCRUBBED before it is returned - the raw citation
    field would be a second display path with one fewer guard. The same is
    proved end to end through the INSTALLED Handler's `do_GET`, with the whole
    JSON reply checked for the secret (Q8 hardening on #549);
  * "could not establish it" (no answer, model down) is an ordinary answer with
    `found` False and a plain `why`, never a made-up citation;
  * the Ollama contract route reports all three outcomes, and the honest
    "Ollama did not answer" state is `verdict` None, `usable` False, and its own
    sentence says "NOT a pass" - it never reads as understood;
  * every other request - another feature's path, an unknown
    `/api/self-improve/...` path, any POST - reaches the core's own handler
    untouched. `do_POST` is never wrapped, so a read cannot be reached by POST;
  * installing twice returns the "already on" banner and does not double-wrap;
  * the drop-in folder names this module, has an `install()` to call, and its
    README states the same loader position as its manifest - and says plainly
    what it does NOT do.

BITE. Two of these checks are the named targets of the PR's deliberate
breakages (the PR body carries the red lines): removing the scrubber from the
citation view turns the citation-scrub check red, and removing the question
limit/refusal turns the refusal check red.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_self_improve as M  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   Fixtures and the stand-in for the core's Handler
# --------------------------------------------------------------------------

_ALPHA = """\
# the backup retry loop stops after three tries
def retry_backup(times=3):
    return times
"""

#: One line that answers a question AND carries something the scrubber must
#: hide. The route must return the answer without the e-mail address.
_SECRET_LINE = ("# the backup retry loop is described at help@example.com "
                "in the notes\n")


def _fixture_tree(text=_ALPHA) -> Path:
    """A throwaway backend holding one file the routes can read.

    Named `jarvis-...` and removed in each test's `finally`: this repository's
    suites run in sandboxes that allow writes inside the checkout's temp
    redirect, and `test_suites_staging.py` fails a run that leaves a `jarvis-*`
    folder behind.
    """
    root = Path(tempfile.mkdtemp(prefix="jarvis-self-improve-route-"))
    (root / "alpha.py").write_text(text, encoding="utf-8", newline="\n")
    return root


class Stand:
    """A stand-in for the core's Handler and its three callbacks - exactly the
    shape `jarvis_plugins.py` calls `install()` with."""

    def __init__(self, origin=True, token=True):
        self.calls = []            # what reached the CORE's own handlers
        self.sent = []             # what the feature answered
        self.origin, self.token = origin, token
        core = self

        class Handler:
            def __init__(self, path="/", body=b"{}"):
                self.path, self.body = path, body

            def do_GET(self):
                core.calls.append(("GET", self.path))

            def do_POST(self):
                core.calls.append(("POST", self.path))

            def _send(self, code, payload):
                core.sent.append((code, payload))
                return payload

        self.Handler = Handler

    def origin_ok(self, req):
        return self.origin

    def token_ok(self, req):
        return self.token

    def read_body(self, req):
        return req.body

    def install(self) -> str:
        return M.install(self.Handler, origin_ok=self.origin_ok,
                         token_ok=self.token_ok, read_body=self.read_body)

    def get(self, path):
        self.Handler(path).do_GET()
        return self.sent[-1] if self.sent else (None, None)

    def post(self, path, body=b"{}"):
        self.Handler(path, body).do_POST()
        return self.sent[-1] if self.sent else (None, None)


def _answer(explanation="The retry loop stops after three tries."):
    """One reply in the module's own protocol, citing the first evidence line."""
    return f"ANSWER: {explanation}\nCITE: 1\n"


# ==========================================================================
#   1. the diagnosis route, end to end through the core's Handler
# ==========================================================================

def t_install_answers_the_diagnosis_route_with_a_real_citation():
    """The wiring: a drop-in install() call makes the route live, and its answer
    is `diagnose()`'s - a real file:line whose quote was re-read from disk."""
    root = _fixture_tree()
    real_roots, real_run = M.default_roots, M._run
    asked = []

    def fake_run(prompt, *, model=None, url=None, timeout=120.0):
        asked.append(prompt)
        return _answer()

    M.default_roots = lambda: (root,)
    M._run = fake_run
    try:
        stand = Stand()
        line = stand.install()
        check("install() returns a banner line naming the feature",
              isinstance(line, str) and "self-improve" in line, line)
        code, body = stand.get("/api/self-improve/diagnose"
                               "?q=where+is+the+backup+retry+loop")
        check("GET /api/self-improve/diagnose answers 200", code == 200,
              f"{code} {str(body)[:300]}")
        check("... with an established answer", body.get("found") is True, str(body))
        check("... and the model's explanation is returned",
              "retry loop" in str(body.get("answer")), str(body.get("answer")))
        citations = body.get("citations") or []
        check("... and it carries a citation naming the real file",
              bool(citations) and citations[0].get("path") == "alpha.py",
              str(citations))
        # #540's DEFINITION_BONUS ranks the `def retry_backup(` definition
        # above the comment that names the question; both are real lines from
        # the fixture, so this asserts the property (a real line re-read from
        # disk), not which matching line wins the retrieval order.
        real_lines = {ln.strip() for ln in _ALPHA.splitlines() if ln.strip()}
        check("... whose quote is a real line re-read from disk",
              bool(citations) and str(citations[0].get("quote", "")).strip()
              in real_lines, str(citations))
        check("... and the plain-words rendering is there too",
              "alpha.py:" in str(body.get("words")), str(body.get("words")))
        check("... and the model was asked exactly once, with the question in the prompt",
              len(asked) == 1 and "backup retry loop" in asked[0],
              f"asked {len(asked)} time(s)")
        check("... and the answer says plainly it read only",
              body.get("read_only") is True, str(body.get("read_only")))
        check("... and no raw evidence field is returned",
              "evidence" not in body, str(sorted(body)))
    finally:
        M._run, M.default_roots = real_run, real_roots
        shutil.rmtree(root, ignore_errors=True)


def t_a_question_that_is_empty_or_too_long_is_refused_and_nothing_is_read():
    """Both refusals are decided BEFORE a search or a model call, and the limit
    itself is a limit: one character more is refused, exactly at it is read."""
    root = _fixture_tree()
    real_roots, real_retrieve, real_run = M.default_roots, M.retrieve, M._run
    searched = []

    def spy_retrieve(*args, **kwargs):
        searched.append(args)
        return real_retrieve(*args, **kwargs)

    def no_model(*args, **kwargs):
        raise AssertionError("a refused request asked the model")

    M.default_roots = lambda: (root,)
    M.retrieve = spy_retrieve
    M._run = no_model
    try:
        stand = Stand()
        stand.install()
        code, body = stand.get("/api/self-improve/diagnose")
        check("a missing question is a 400, not a search",
              code == 400 and body.get("ok") is False, f"{code} {body}")
        check("... and the refusal says the question is empty",
              "empty" in str(body.get("error")), str(body))
        code, body = stand.get("/api/self-improve/diagnose?q=")
        check("an empty `q=` is the same 400", code == 400, f"{code} {body}")
        code, body = stand.get("/api/self-improve/diagnose?q=%20%20")
        check("a question of only spaces is the same 400", code == 400,
              f"{code} {body}")
        long_one = "x" * (M.MAX_QUESTION_CHARS + 1)
        code, body = stand.get("/api/self-improve/diagnose?q=" + long_one)
        check(f"a question longer than {M.MAX_QUESTION_CHARS} characters is a 400",
              code == 400 and "too long" in str(body.get("error")), f"{code} {body}")
        check("CONTROL: none of those refusals searched the source or asked the model",
              searched == [], f"searched {len(searched)} time(s)")

        at_limit = "y" * M.MAX_QUESTION_CHARS
        code, body = stand.get("/api/self-improve/diagnose?q=" + at_limit)
        check(f"CONTROL: a question at exactly {M.MAX_QUESTION_CHARS} characters IS read",
              code == 200 and isinstance(body, dict), f"{code} {str(body)[:200]}")
        check("... so the boundary is the limit, not a shorter accident",
              len(searched) == 1, f"searched {len(searched)} time(s)")
    finally:
        M.default_roots, M.retrieve, M._run = real_roots, real_retrieve, real_run
        shutil.rmtree(root, ignore_errors=True)


def t_a_citation_quote_is_scrubbed_before_it_is_returned():
    """The route must scrub citation quotes itself.

    `Citation.text` is the line re-read from disk; `text()` scrubs it when it
    displays it. A route that serialised the dataclass field would be a second
    display path with one fewer guard - so this line carries an e-mail address
    and the route must not hand it out.
    """
    root = _fixture_tree(_SECRET_LINE)
    real_roots, real_run = M.default_roots, M._run
    M.default_roots = lambda: (root,)
    M._run = lambda *a, **k: _answer()
    try:
        code, body = M.handle_get(M.DIAGNOSE_PATH,
                                  "q=where+is+the+backup+retry+loop+described")
        check("the diagnosis is found", code == 200 and body.get("found") is True,
              f"{code} {str(body)[:300]}")
        citations = body.get("citations") or []
        quote = str(citations[0].get("quote")) if citations else ""
        check("the citation quote does NOT carry the e-mail address",
              "help@example.com" not in quote, quote)
        check("... and it is scrubbed, not dropped: the line is there in its place",
              "retry loop" in quote and "[redacted: e-mail]" in quote, quote)
    finally:
        M._run, M.default_roots = real_run, real_roots
        shutil.rmtree(root, ignore_errors=True)


def t_the_installed_handler_never_returns_the_secret_end_to_end():
    """The route driven through the installed Handler - the way the core does it.

    Gemini's hardening request on #549 (Q8): drive `do_GET(
    "/api/self-improve/diagnose?q=...")` against a line containing a test secret
    and prove that removing the citation scrub breaks THIS test, not only a
    unit-level call to `handle_get`. `Stand.get` calls the installed
    `Handler.do_GET` after the real origin/token checks, so this is the whole
    path the core takes; the whole JSON reply, every field, must be free of the
    address, and the core's own handlers must never be reached.
    """
    root = _fixture_tree(_SECRET_LINE)
    real_roots, real_run = M.default_roots, M._run
    M.default_roots = lambda: (root,)
    M._run = lambda *a, **k: _answer()
    try:
        stand = Stand()
        stand.install()
        code, body = stand.get("/api/self-improve/diagnose"
                               "?q=where+is+the+backup+retry+loop+described")
        whole = json.dumps(body, ensure_ascii=False, sort_keys=True)
        check("E2E: the installed do_GET answers the diagnosis route 200",
              code == 200 and isinstance(body, dict) and body.get("found") is True,
              f"{code} {whole[:300]}")
        check("E2E: the core's own handlers were never reached",
              stand.calls == [], str(stand.calls))
        check("E2E: no field of the whole reply carries the e-mail address",
              "help@example.com" not in whole, whole[:400])
        citations = body.get("citations") or []
        quote = str(citations[0].get("quote")) if citations else ""
        check("E2E: the citation is still there and scrubbed in place",
              "retry loop" in quote and "[redacted: e-mail]" in quote, quote)
        check("E2E: the plain-words rendering is scrubbed too",
              "help@example.com" not in str(body.get("words")),
              str(body.get("words"))[:300])
    finally:
        M._run, M.default_roots = real_run, real_roots
        shutil.rmtree(root, ignore_errors=True)


# ==========================================================================
#   2. an honest "could not establish it" is not a fake answer
# ==========================================================================

def t_a_diagnosis_that_cannot_be_established_is_answered_plainly():
    """No answer, a model that fails, a model that says it cannot: each is a
    200 with `found` False and a plain `why` - never a citation invented to
    fill the space, and never a 5xx that reads as a broken route."""
    root = _fixture_tree()
    real_roots = M.default_roots
    M.default_roots = lambda: (root,)
    outcomes = []
    try:
        question, _ = M._asked("q=where+is+the+backup+retry+loop")

        code, body = M.handle_get(M.DIAGNOSE_PATH, "q=where+is+the+backup+retry+loop",
                                  ask=lambda prompt: "CANNOT: there is no such code here\n")
        outcomes.append(body)
        check("a model that names what is missing is a 200 with found False",
              code == 200 and body.get("found") is False, f"{code} {body}")
        check("... and its own reason is carried back",
              "no such code here" in str(body.get("why")), str(body.get("why")))
        check("... and there is no citation to mistake for an answer",
              body.get("citations") == [] and "alpha.py" not in str(body.get("words")),
              str(body))
        check("... and the plain rendering says it could not establish it",
              str(body.get("words")).startswith("Could not establish this"),
              str(body.get("words")))

        def broken(prompt):
            raise RuntimeError("the model is down")

        code, body = M.handle_get(M.DIAGNOSE_PATH, "q=where+is+the+backup+retry+loop",
                                  ask=broken)
        outcomes.append(body)
        check("a model that raises is an honest refusal, not a 5xx from the route",
              code == 200 and body.get("found") is False, f"{code} {body}")
        check("... and it says the local model could not be asked",
              "local model could not be asked" in str(body.get("why")),
              str(body.get("why")))

        code, body = M.handle_get(M.DIAGNOSE_PATH, "q=where+is+the+backup+retry+loop",
                                  ask=lambda prompt: "")
        outcomes.append(body)
        check("a model that says nothing is the same honest refusal",
              code == 200 and body.get("found") is False
              and "did not answer" in str(body.get("why")), f"{code} {body}")
        check("THE WALL: no 'could not establish' path ever reports found True",
              len(outcomes) == 3 and not any(b.get("found") for b in outcomes),
              [b.get("found") for b in outcomes])
        check("... and the question is echoed so a caller knows what was asked",
              body.get("question") == question, str(body.get("question")))
    finally:
        M.default_roots = real_roots
        shutil.rmtree(root, ignore_errors=True)


# ==========================================================================
#   3. the Ollama contract route: the three outcomes, and the fourth state
# ==========================================================================

def t_the_contract_route_reports_all_three_outcomes():
    """One fake /api/show answer per outcome. The names are the contract module's
    own, so a client reads the same vocabulary the module documents."""
    model = "qwen3:8b"
    code, body = M.handle_get(
        M.CONTRACT_PATH, f"model={model}",
        ask_ollama=lambda url, name: {"capabilities":
                                      ["completion", "tools", "vision", "thinking"]})
    check("a complete, known capability list is the 200 understood outcome",
          code == 200 and body.get("verdict") == "understood", f"{code} {body}")
    check("... and it says what Ollama said", body.get("said") ==
          ["completion", "tools", "vision", "thinking"], str(body.get("said")))
    check("... and it echoes the model it is about", body.get("model") == model,
          str(body.get("model")))
    check("... and the plain sentence names the model too",
          str(body.get("words")).startswith(model), str(body.get("words")))
    check("... and it asked the loopback address only",
          "127.0.0.1" in str(body.get("url")) or "localhost" in str(body.get("url")),
          str(body.get("url")))
    check("... and it says plainly it read only", body.get("read_only") is True)

    code, body = M.handle_get(
        M.CONTRACT_PATH, f"model={model}",
        ask_ollama=lambda url, name: {"capabilities": ["completion", "telepathy"]})
    check("a capability Jarvis has never heard of is the unknown outcome",
          code == 200 and body.get("verdict") == "unknown_capabilities",
          f"{code} {body}")
    check("... and the unknown name is named", body.get("unknown") == ["telepathy"],
          str(body.get("unknown")))
    check("... and the plain sentence says it is not an error",
          "not an error" in str(body.get("note")), str(body.get("note")))

    code, body = M.handle_get(
        M.CONTRACT_PATH, f"model={model}",
        ask_ollama=lambda url, name: {
            "capabilities": ["completion"],
            "model_info": {"clip.has_vision_encoder": True},
            "projector_info": {},
        })
    check("a capability the model plainly has but Ollama's list omits is the third outcome",
          code == 200 and body.get("verdict") == "missing_expected", f"{code} {body}")
    check("... and the missing name is named", body.get("missing") == ["vision"],
          str(body.get("missing")))
    check("... and the plain sentence says Jarvis would under-use the model",
          "under-use" in str(body.get("note")), str(body.get("note")))


def t_a_contract_ollama_did_not_answer_is_never_a_pass():
    """Ollama not answering is its own state, and the whole point is that it
    does not read as 'understood'. A missing model= names the module's default."""
    code, body = M.handle_get(M.CONTRACT_PATH, "model=qwen3:8b",
                              ask_ollama=lambda url, name: None)
    check("Ollama sending nothing is still a 200 answer from the route",
          code == 200, f"{code} {body}")
    check("... with verdict None - it is not one of the three outcomes",
          body.get("verdict") is None, str(body.get("verdict")))
    check("... and usable False, which is how a caller knows",
          body.get("usable") is False, str(body.get("usable")))
    check("... and the plain sentence says NOT a pass",
          "NOT a pass" in str(body.get("note")), str(body.get("note")))
    check("... and nothing anywhere in it claims 'understood'",
          "understood" not in json.dumps(body).lower(), json.dumps(body)[:300])

    def example_down(url, name):
        raise ConnectionError("no Ollama here")

    code, body = M.handle_get(M.CONTRACT_PATH, "model=qwen3:8b",
                              ask_ollama=example_down)
    check("a probe that cannot even ask is the same honest state",
          code == 200 and body.get("verdict") is None
          and body.get("usable") is False, f"{code} {body}")

    seen = []

    def show(url, name):
        seen.append(name)
        return {"capabilities": ["completion"]}

    code, body = M.handle_get(M.CONTRACT_PATH, "", ask_ollama=show)
    check("a missing model= asks the module's own default, not an empty name",
          code == 200 and bool(seen) and seen[0] == M._model_name(None),
          f"{code} {seen}")
    check("... and that default is a real model name", bool(M._model_name(None)),
          M._model_name(None))


# ==========================================================================
#   4. the walls: origin, token, and every other request
# ==========================================================================

def t_the_two_routes_check_origin_and_token_before_anything():
    """Every module's install() goes through the core's own two checks first.
    Origin is checked before token - the order the core itself uses."""
    def no_model(*args, **kwargs):
        raise AssertionError("a refused request asked the model")

    real_run = M._run
    M._run = no_model
    try:
        cross = Stand(origin=False)
        cross.install()
        code, body = cross.get("/api/self-improve/diagnose?q=anything")
        check("a cross-origin request to the diagnosis route is a 403",
              code == 403, f"{code} {body}")
        check("... and the refusal is plain",
              "cross-origin" in str(body.get("error")), str(body))
        check("... and no diagnosis leaked into it",
              "found" not in body and "citations" not in body, str(sorted(body)))
        code, body = cross.get("/api/self-improve/contract?model=x")
        check("... and the contract route refuses it the same way",
              code == 403, f"{code} {body}")

        both_off = Stand(origin=False, token=False)
        both_off.install()
        code, body = both_off.get("/api/self-improve/diagnose?q=anything")
        check("origin is checked BEFORE the token (both bad -> 403)",
              code == 403, f"{code} {body}")

        wrong = Stand(token=False)
        wrong.install()
        code, body = wrong.get("/api/self-improve/diagnose?q=anything")
        check("a bad or missing token is a 401", code == 401, f"{code} {body}")
        check("... naming the token that is missing",
              "X-Jarvis-Token" in str(body.get("error")), str(body))
        check("... and the core never saw the request",
              wrong.calls == [], str(wrong.calls))
    finally:
        M._run = real_run


def t_every_other_request_reaches_the_core_untouched():
    """The two exact paths are ours. Everything else - another feature's path, an
    unknown path under our own prefix, any POST - is the core's."""
    stand = Stand()
    stand.install()
    stand.get("/api/other")
    check("an unrelated GET reaches the core", stand.calls[-1] == ("GET", "/api/other"),
          str(stand.calls))
    stand.post("/api/other")
    check("... and so does an unrelated POST",
          stand.calls[-1] == ("POST", "/api/other"), str(stand.calls))
    stand.get("/api/receipts")
    check("... and another drop-in feature's path",
          stand.calls[-1] == ("GET", "/api/receipts"), str(stand.calls))
    stand.get("/api/self-improve/draft")
    check("an unknown path under /api/self-improve/ is passed through, not invented",
          stand.calls[-1] == ("GET", "/api/self-improve/draft"), str(stand.calls))
    stand.post("/api/self-improve/diagnose", b"{}")
    check("POSTing to a read-only route reaches the core, so no read is a write",
          stand.calls[-1] == ("POST", "/api/self-improve/diagnose"), str(stand.calls))
    check("... and the feature itself answered none of them, so nothing was read",
          stand.sent == [], str(stand.sent))

    code, _body = stand.get("/api/self-improve/diagnose/")
    check("a trailing slash on the route is still ours (and still refuses no question)",
          code == 400, f"{code}")


def t_installing_twice_does_not_double_wrap_and_adds_no_write_route():
    """The loader and a patch could both call install(); the second call must
    report 'already on' and change nothing. And the class must gain no POST."""
    stand = Stand()
    post0 = stand.Handler.do_POST
    get0 = stand.Handler.do_GET
    first = stand.install()
    second = stand.install()
    check("the first install() returns a banner line",
          isinstance(first, str) and "on" in first, first)
    check("the second install() says it is already on", "already on" in second, second)
    check("... and it added no POST handler, because both routes are reads",
          stand.Handler.do_POST is post0)
    check("... and it really did wrap do_GET", stand.Handler.do_GET is not get0)
    before = len(stand.sent)
    code, _body = stand.get("/api/self-improve/diagnose")
    check("one request is answered once, not twice",
          len(stand.sent) == before + 1, f"sent {len(stand.sent) - before} answer(s)")
    check("... and it stayed out of the core", stand.calls == [], str(stand.calls))


# ==========================================================================
#   5. the drop-in folder, its manifest and its README
# ==========================================================================

def t_the_plugin_folder_the_module_and_the_docs_agree():
    """A folder the loader would call must name the module THIS suite proves has
    install(), declare a loader position its README agrees with, and say
    honestly what it does not do."""
    folder = HERE.parent / "plugins" / "ready" / "self-improve"
    manifest = folder / "plugin.json"
    check("the drop-in folder is there", manifest.is_file(), str(manifest))
    if not manifest.is_file():
        return
    data = json.loads(manifest.read_text(encoding="utf-8"))
    check("it names this module, to be called with the core's Handler",
          data.get("module") == "jarvis_self_improve"
          and data.get("install") == "handler", str(data))
    check("it has a name, a summary and a loader position",
          data.get("name") == "self-improve" and bool(data.get("summary"))
          and isinstance(data.get("stack_order"), int), str(data))
    check("... and it replaces no patch, which is why it is a folder at all",
          "replaces_patch" not in data, str(sorted(data)))
    check("the module it names really has install()",
          callable(getattr(M, "install", None)))

    readme = folder / "README.md"
    check("the folder has a README in plain words", readme.is_file())
    if not readme.is_file():
        return
    text = readme.read_text(encoding="utf-8")
    stated = re.search(r"Position in the loader'?s order:\s*\*{0,2}\s*(\d+)", text)
    check("its README states the same loader position as plugin.json",
          bool(stated) and int(stated.group(1)) == data.get("stack_order"),
          f"README says {stated.group(1) if stated else None}, manifest says "
          f"{data.get('stack_order')}")
    check("... and the README says plainly which routes it serves",
          "/api/self-improve/diagnose" in text and "/api/self-improve/contract" in text)
    check("... and it says plainly there is no POST route and no draft route",
          "No `POST` route" in text and "draft" in text)
    check("... and that nothing is written, approved, started or sent off this PC",
          "approves" in text and "leave this PC" in text)


# ==========================================================================
#   main
# ==========================================================================

def main() -> int:
    funcs = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("t_") and callable(fn)]
    for name, fn in funcs:
        try:
            fn()
        except Exception as exc:                            # noqa: BLE001
            check(f"{name} raised", False,
                  f"{type(exc).__name__}: {exc}\n" + traceback.format_exc())
    print(f"\n{len(PASSED)} passed, 0 skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + "\n        ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
