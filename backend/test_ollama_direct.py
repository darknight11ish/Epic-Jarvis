"""Where each chat lane really goes: Ollama for the local one, and the
service behind it for a cloud one.

`/api/chat`'s completion request always went to `{JARVIS_URL}/v1/chat/completions`
- OpenJarvis's own port and API shape - whatever lane was chosen, local or
not. OpenJarvis was never actually installed as part of this setup, so every
local turn was one `_open()` call away from a 503 it could never recover
from. `ollama-direct.patch` added `_completions_url(lane)`, which sends the
local lane to Ollama's own OpenAI-compatible endpoint instead.

WHAT CHANGED ON 2026-10-06, AND WHY THIS TEST READS AS IT DOES. The cloud
half of that function was a placeholder: a non-local lane went to `JARVIS_URL`
too, and the patch's own comment called itself "the one place that needs a
real answer". The owner made that decision (docs/ACCOUNT-KEYS-DESIGN.md
section 5 and part C): a cloud lane goes through `jarvis_chatbot_api.py`'s
adapter family - HTTPS to the service's own pinned host, the key from Windows
Credential Manager, the monthly money limit, the answer-length cap, and a
redirect refused - and the service behind it is DeepSeek. This test used to
assert the placeholder ("a cloud lane still resolves to JARVIS_URL -
unimplemented, not silently redirected"). It now asserts the real thing,
which is not the same test with a different string: a cloud lane reaches
DeepSeek's own address, asks for DeepSeek's own model name, carries DeepSeek's
own key, and is answered LOCALLY when the owner's monthly limit cannot pay
for it - never sent to a paid service, and never quietly reported as a cloud
answer.

This test executes the real `_completions_url`, lifted from the source with
ast - the same technique test_degrade_filter.py already uses on this exact
file, for this exact reason. It cannot start a real HTTP server or reach a
real Ollama or DeepSeek; that part only the owner's own machine can prove.
What it does instead is run the lifted text inside a wrapper that declares the
per-request names it binds with `nonlocal`, so the whole decision can be
exercised here, with no socket.

    python3 test_ollama_direct.py
"""
import ast
import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, missing, explain
SRC = BACKEND / "jarvis_hud.py"

FAILED, PASSED = [], []
SKIPPED = []

LOCAL = "qwen3:8b"
LANE = "jarvis-escalate"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


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
    `why` is the real module's own sentence for a lane that cannot be used."""

    def __init__(self, *, ready=True, model="deepseek-flash",
                 key="the-deepseek-key", why="No monthly money limit is set for DeepSeek."):
        self.ready, self.model, self.key, self.why = ready, model, key, why

    def cloud_lane(self, lane, **kw):
        if not self.ready:
            return None
        return {"pid": "deepseek_api", "model": self.model, "host": "api.deepseek.com",
                "url": DEEPSEEK_URL, "cap": 8000, "why": ""}

    def lane_key(self, lane):
        return self.key if self.ready else ""

    def lane_service(self, lane):
        return ("deepseek_api", self.model)

    def ready_for(self, pid):
        return "" if self.ready else self.why


def _lift_completions(source: str):
    """The real `_completions_url`, made runnable on its own.

    It binds three names with `nonlocal`, so it cannot simply be exec'd: the
    lifted text goes inside a wrapper that declares those three, runs the
    function once for LANE, leaves what the function set in `_out`, and
    returns the URL. `body` is the request body the real `_open` has in hand.
    """
    tree = ast.parse(source)
    found = [n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "_completions_url"]
    if len(found) != 1:
        raise AssertionError(f"expected exactly one _completions_url, found {len(found)}")
    ns = {"OLLAMA_URL": "http://127.0.0.1:11434", "JARVIS_URL": "http://127.0.0.1:8000",
          "local_model": LOCAL, "body": {"model": LANE}, "_out": {}}
    wrapper = ("def _run():\n"
               "    _cloud_model, _cloud_key, _cloud_problem = {}, '', ''\n"
               + "".join(f"    {line}\n"
                         for line in ast.unparse(found[0]).splitlines())
               + "    return (_completions_url(%r), _cloud_model, _cloud_key, "
                 "_cloud_problem)\n" % LANE)
    exec(compile(wrapper, "<lifted>", "exec"), ns)
    url, model, key, problem = ns["_run"]()
    return url, model, key, problem, ns["body"]


def _lift_auth(source: str):
    """The real `_auth_headers`, with the key a resolved cloud lane leaves."""
    tree = ast.parse(source)
    found = [n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "_auth_headers"]
    if len(found) != 1:
        raise AssertionError(f"expected exactly one _auth_headers, found {len(found)}")
    ns = {"JARVIS_API_KEY": "the-pairing-token", "_cloud_key": ""}
    exec(compile(ast.Module(body=[found[0]], type_ignores=[]), "<lifted>", "exec"), ns)
    return ns["_auth_headers"]


def _with_api(source: str, api, fn):
    """Run `fn` with a stand-in jarvis_chatbot_api installed in sys.modules."""
    saved = sys.modules.get("jarvis_chatbot_api")
    sys.modules["jarvis_chatbot_api"] = api
    try:
        return fn(source)
    finally:
        if saved is not None:
            sys.modules["jarvis_chatbot_api"] = saved
        else:
            sys.modules.pop("jarvis_chatbot_api", None)


def t_local_lane_goes_to_ollama():
    if missing("jarvis_hud.py"):
        return skip(explain())
    src = SRC.read_text(encoding="utf-8")
    url, _, _, _, _ = _with_api(src, FakeApi(ready=False),
                                lambda s: _lift_completions(s.replace(LANE, LOCAL)))
    check("the local lane resolves to Ollama's own endpoint",
          url == "http://127.0.0.1:11434/v1/chat/completions", url)


def t_a_cloud_lane_goes_to_the_service_behind_it():
    """The real answer to the old placeholder. `jarvis-escalate` is a lane name
    from the shipped degrade_chain; once the service behind it is set up, the
    request goes to THAT service's own https address - not JARVIS_URL, not
    Ollama - and asks for THAT service's model."""
    if missing("jarvis_hud.py"):
        return skip(explain())
    src = SRC.read_text(encoding="utf-8")
    url, model, key, problem, body = _with_api(src, FakeApi(), _lift_completions)
    check("a cloud lane resolves to the cloud service's own endpoint",
          url == DEEPSEEK_URL, url)
    check("... and not to JARVIS_URL's own port any more", "127.0.0.1:8000" not in url, url)
    check("... and not to Ollama, which has no such model", "11434" not in url, url)
    check("... and the request asks for the SERVICE's model, not the lane's name",
          body["model"] == "deepseek-flash", body)
    check("... and the service's own key is what the request will carry",
          key == "the-deepseek-key", key)
    check("... and nothing is reported as a problem", problem == "", problem)


def t_a_lane_that_cannot_be_paid_for_is_answered_locally():
    """When `cloud_lane()` returns None - no key saved, a model with no price,
    the month's money limit reached, a message it cannot pay for - nothing is
    sent to a paid service at all. The lane goes to the LOCAL address instead:
    this PC answers, nothing is spent, and the request keeps the local model's
    name and Jarvis's own pairing token, exactly as a local turn always did."""
    if missing("jarvis_hud.py"):
        return skip(explain())
    src = SRC.read_text(encoding="utf-8")
    url, model, key, problem, body = _with_api(src, FakeApi(ready=False), _lift_completions)
    check("an unpaid-for cloud lane is answered on this PC's own Ollama",
          url == "http://127.0.0.1:11434/v1/chat/completions", url)
    check("... never sent to the cloud host without a resolved lane",
          "api.deepseek.com" not in url, url)
    check("... and no cloud key is attached", key == "", key)
    check("... and it says why, in the module's own words",
          problem == "No monthly money limit is set for DeepSeek.", problem)


def t_the_request_uses_the_lane_key_not_the_pairing_token():
    """Rule 3. The pairing token authenticates THIS PC's own server; a cloud
    service must get that service's own key and nothing else. The one place
    any request's Authorization header is built switches on what the resolved
    lane left behind, and a local lane behaves exactly as it did before."""
    if missing("jarvis_hud.py"):
        return skip(explain())
    src = SRC.read_text(encoding="utf-8")
    fn = _lift_auth(src)
    local = fn({"Content-Type": "application/json"})
    check("a local request still carries Jarvis's own pairing token",
          local.get("Authorization") == "Bearer the-pairing-token", local)
    # What a resolved cloud lane leaves behind, a moment later in the request.
    ns = {"JARVIS_API_KEY": "the-pairing-token", "_cloud_key": "the-deepseek-key"}
    tree = ast.parse(src)
    node = [n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "_auth_headers"][0]
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<lifted>", "exec"), ns)
    cloud = ns["_auth_headers"]({"Content-Type": "application/json"})
    check("a cloud request carries the SERVICE's key instead",
          cloud.get("Authorization") == "Bearer the-deepseek-key", cloud)
    check("... and the pairing token is not sent to the cloud service at all",
          "the-pairing-token" not in json.dumps(cloud), cloud)


def t_the_error_message_names_the_right_service():
    """A local-lane failure has to say Ollama and how to start it. A cloud
    lane's failure has to name the service it really tried, and a lane that
    could not be set up has to say what is missing - never blame a program
    that was never supposed to be running. That string is what a confused
    owner would actually go and act on."""
    if missing("jarvis_hud.py"):
        return skip(explain())
    src = SRC.read_text(encoding="utf-8")
    check("mentions Ollama's own start command for the local-lane failure",
          "ollama serve" in src, "expected the literal `ollama serve` advice somewhere")
    check("the local-lane message is conditioned on lane == local_model, not unconditional",
          "if lane == local_model else" in src or "if lane == local_model\n" in src,
          "expected the ternary picking the message by lane")
    check("the cloud failure names the host the lane really tried",
          "is not answering at {_cloud_model['host']}" in src
          or 'is not answering at {_cloud_model["host"]}' in src,
          "expected the cloud branch to name the resolved lane's host")
    check("... and a lane that could not be set up repeats the module's own "
          "words for why, not a wrong address",
          "{_cloud_problem} (Details: {exc})" in src)
    check("the cloud failure no longer tells the owner to go to JARVIS_URL",
          "answers at {JARVIS_URL}" not in src)


if __name__ == "__main__":
    for fn in (t_local_lane_goes_to_ollama,
               t_a_cloud_lane_goes_to_the_service_behind_it,
               t_a_lane_that_cannot_be_paid_for_is_answered_locally,
               t_the_request_uses_the_lane_key_not_the_pairing_token,
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
