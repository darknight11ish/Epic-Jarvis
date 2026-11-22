"""Every cloud turn carries ONE fixed identity sentence. A local turn carries none.

    python3 test_cloud_turn_identity.py

THE DEFECT THIS PROVES AWAY (measured on the live app, 2026-11-22). A cloud
turn carried no identity at all, and the model filled the gap by guessing:
asked "what do you know about your own GitHub repository" it answered "I don't
have a GitHub repository of my own", and asked to compare itself with another
agent it described itself as "Me (OpenAI model via API/ChatGPT)" - on a PC
whose chosen provider is `deepseek_api`.

THE FIX: the request body's messages, assembled in `_open()` in
`jarvis_hud.py`, now begin with ONE fixed system message:

    You are Atlas, answering an escalated complex question via the user's
    configured cloud provider with no local tools or private files.

It is a literal in this repository, not something a model writes, and it
claims nothing the lane does not have. It is added AFTER the cloud cut that
keeps only the newest user turn, because a system message added before that
cut would be dropped.

HOW THIS SUITE READS IT. `jarvis_hud.py` is the backend's entry point and this
repository holds its own copy only as the published base
(`jarvis-backend/jarvis_hud.py`) - the owner's live file is not in a checkout.
So the suite parses that file, takes `_open` itself out of it with `ast`, and
runs the REAL function against a fake `urllib` that records the exact request
body. Nothing here copies the code it is testing, and no socket is opened.

WHAT THIS SUITE HOLDS
  1. the sentence is ONE fixed string literal in the base file - not an
     f-string, not a format call, not a model output;
  2. every cloud lane's request carries it exactly once, first, and it says
     no tools and no private files (it cannot invite a false claim);
  3. a degraded hop (a second cloud request) still carries it exactly once;
  4. a LOCAL turn carries none of it, and keeps its whole conversation;
  5. the earlier turns still do not ride along on the cloud request.

What it does NOT prove: what a real provider answered. That needs a live call,
which this repository does not make here.
"""
from __future__ import annotations

import ast
import json
import sys
import textwrap
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASE_HUD = REPO / "jarvis-backend" / "jarvis_hud.py"

FAILED, PASSED = [], []
SKIPPED = []

#: The one sentence, pinned word for word. This is the second copy on purpose:
#: it is the contract, and a change to the sentence has to be made in both
#: places with a reason.
SENTENCE = ("You are Atlas, answering an escalated complex question via the "
            "user's configured cloud provider with no local tools or private "
            "files.")

LOCAL = "qwen3.5:9b"
#: The cloud lanes the live PC can offer (`$PATCHES`/`_lane_names()` names).
CLOUD_LANES = ("jarvis-escalate", "jarvis-vision", "jarvis-bulk")

#: What a client sends now: the conversation so far, then the new question.
CONVERSATION = [
    {"role": "user", "content": "my salary is 91,000 and my bank is Nordea"},
    {"role": "assistant", "content": "On 91,000, a modest one, yes."},
    {"role": "system", "content": "Things you know about the user:\n- banks with Nordea"},
    {"role": "user", "content": "explain in detail how electric and hybrid cars "
                                "compare on running costs, step by step"},
]
NEWEST = CONVERSATION[-1]


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this checkout cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def _hud_source() -> str:
    return BASE_HUD.read_text(encoding="utf-8")


def _open_node():
    """The `_open` function node from the base HUD, or None."""
    tree = ast.parse(_hud_source())
    return next((n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == "_open"), None)


class _Request:
    def __init__(self, url, data=None, headers=None, method=None):
        self.url, self.data, self.headers, self.method = url, data, headers, method


class _UrlOpen:
    """Stands in for urllib.request.urlopen and records every request body."""

    def __init__(self):
        self.bodies = []
        self.urls = []

    def __call__(self, request, timeout=None):
        self.bodies.append(json.loads(request.data.decode("utf-8")))
        self.urls.append(request.url)
        return object()


def _open_function(capture, conversation=None):
    """The REAL `_open`, lifted out of the base HUD and runnable.

    `_open` is nested inside the request handler, so the code is taken from
    the file itself with `ast.unparse` and given the few module-level names it
    reads. Nothing about the identity sentence is re-implemented here: the
    function under test is the text this repository ships.
    """
    node = _open_node()
    if node is None:
        raise AssertionError("jarvis-backend/jarvis_hud.py has no _open")
    code = textwrap.dedent(ast.unparse(node))
    fake_urllib = types.SimpleNamespace(
        request=types.SimpleNamespace(Request=_Request, urlopen=capture))
    fake_agent = types.ModuleType("jarvis_agent")
    fake_agent.keep_rules_first = lambda messages: list(messages)
    old = sys.modules.get("jarvis_agent")
    sys.modules["jarvis_agent"] = fake_agent
    try:
        ns = {
            "urllib": fake_urllib,
            "json": json,
            "_CHAT_CLIENT_FIELDS": set(),
            "_chat_client_fields_off": lambda messages: list(messages),
            "_completions_url": lambda lane: "http://127.0.0.1:8000/v1/chat/"
                                             "completions",
            "_auth_headers": lambda headers: dict(headers),
            "payload": {"model": LOCAL,
                        "messages": list(CONVERSATION if conversation is None
                                         else conversation),
                        "stream": True},
            "local_model": LOCAL,
        }
        exec(compile(code, "<jarvis_hud._open>", "exec"), ns)
        return ns["_open"]
    finally:
        if old is None:
            sys.modules.pop("jarvis_agent", None)
        else:
            sys.modules["jarvis_agent"] = old


def _identity_messages(messages):
    return [m for m in messages
            if isinstance(m, dict) and "You are Atlas" in str(m.get("content"))]


# ==========================================================================
#  1. the sentence is one fixed literal in the file, not something generated
# ==========================================================================

def t_the_sentence_is_one_fixed_literal():
    if not BASE_HUD.is_file():
        return skip(f"{BASE_HUD} is not in this checkout")
    node = _open_node()
    if node is None:
        return check("the base HUD has an _open", False)
    assigned = [n for n in ast.walk(node)
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "cloud_identity"
                        for t in n.targets)]
    check("_open builds the identity message itself, before the body", bool(assigned))
    if not assigned:
        return
    value = assigned[0].value
    check("... as a dict literal (role/content), not a call", isinstance(value, ast.Dict),
          type(value).__name__)
    content = None
    if isinstance(value, ast.Dict):
        for key, val in zip(value.keys, value.values):
            if isinstance(key, ast.Constant) and key.value == "content":
                content = val
    check("... whose content is ONE plain string constant - no f-string, no "
          "format call, no model output",
          isinstance(content, ast.Constant) and isinstance(content.value, str),
          "" if content is None else type(content).__name__)
    check("... and it is the pinned sentence, word for word",
          isinstance(content, ast.Constant) and content.value == SENTENCE,
          "" if content is None else repr(content.value))
    check("... it says the lane has NO tools and NO private files",
          "no local tools" in SENTENCE and "private files" in SENTENCE)
    # It must not claim what the lane does not have: a sentence that promised
    # files or a repository would be exactly the guess this fix exists to stop.
    for claim in ("you have access", "you can read", "your files",
                  "your repository", "you have tools"):
        check(f"... and it does not claim {claim!r}", claim not in SENTENCE.lower())


# ==========================================================================
#  2. every cloud request carries it exactly once, first, and only once
# ==========================================================================

def t_every_cloud_lane_carries_it_exactly_once():
    if not BASE_HUD.is_file():
        return skip(f"{BASE_HUD} is not in this checkout")
    for lane in CLOUD_LANES:
        capture = _UrlOpen()
        _open_function(capture)(lane)
        if len(capture.bodies) != 1:
            check(f"{lane}: one request was sent", False, repr(capture.urls))
            continue
        messages = capture.bodies[0]["messages"]
        found = _identity_messages(messages)
        check(f"{lane}: exactly one identity message", len(found) == 1,
              json.dumps(messages)[:400])
        check(f"{lane}: at the very front, a system message",
              bool(messages) and messages[0].get("role") == "system"
              and messages[0].get("content") == SENTENCE,
              json.dumps(messages[:1])[:300])
        text = json.dumps(messages)
        check(f"{lane}: the sentence appears exactly once in the whole request",
              text.count(SENTENCE) == 1, str(text.count(SENTENCE)))


def t_the_newest_question_is_still_the_only_user_turn():
    capture = _UrlOpen()
    _open_function(capture)("jarvis-escalate")
    messages = capture.bodies[0]["messages"]
    users = [m for m in messages if m.get("role") == "user"]
    check("the cloud request still carries exactly one user turn",
          len(users) == 1, json.dumps(messages)[:400])
    check("... and it is the newest question, unchanged", users == [NEWEST],
          json.dumps(users)[:300])
    sent = json.dumps(messages)
    check("... the earlier private question did not ride along",
          "91,000" not in sent and "Nordea" not in sent)


def t_a_second_hop_carries_it_once_and_not_twice():
    # The degrade loop calls `_open` again with a lower lane and a rebuilt
    # payload. Each request is assembled fresh, so a second hop gets its own
    # copy and never two.
    capture = _UrlOpen()
    open_fn = _open_function(capture)
    open_fn("jarvis-escalate")
    open_fn("jarvis-bulk")
    check("two cloud hops sent two requests", len(capture.bodies) == 2)
    for i, body in enumerate(capture.bodies):
        check(f"hop {i + 1}: the sentence appears exactly once",
              json.dumps(body["messages"]).count(SENTENCE) == 1,
              json.dumps(body["messages"])[:300])


def t_the_sentence_does_not_depend_on_the_question():
    # It is fixed: two very different questions get the same identity, in the
    # same place. Anything that changed with the question would be generated.
    other_question = [
        {"role": "user", "content": "why is the sky blue at dusk?"},
    ]
    first = _UrlOpen()
    _open_function(first)("jarvis-escalate")
    other = _UrlOpen()
    _open_function(other, conversation=other_question)("jarvis-vision")
    a = _identity_messages(first.bodies[0]["messages"])
    b = _identity_messages(other.bodies[0]["messages"])
    check("the identity is identical whatever the lane and question",
          len(a) == 1 and a == b and a[0]["content"] == SENTENCE,
          json.dumps([a, b])[:400])
    check("... and the second question is still the newest turn, after it",
          other.bodies[0]["messages"][-1] == other_question[0],
          json.dumps(other.bodies[0]["messages"])[:300])


# ==========================================================================
#  3. a LOCAL turn carries none of it and keeps its conversation
# ==========================================================================

def t_a_local_turn_carries_none():
    if not BASE_HUD.is_file():
        return skip(f"{BASE_HUD} is not in this checkout")
    capture = _UrlOpen()
    _open_function(capture)(LOCAL)
    body = capture.bodies[0]
    sent = json.dumps(body["messages"])
    check("a local turn's request does not contain the sentence",
          SENTENCE not in sent and "You are Atlas, answering" not in sent,
          sent[:400])
    users = [m for m in body["messages"] if m.get("role") == "user"]
    check("... and it keeps the whole conversation, both user turns",
          len(users) == 2, json.dumps(body["messages"])[:400])
    check("... including the earlier one the cloud cut would have removed",
          any("91,000" in str(m.get("content")) for m in users),
          json.dumps(users)[:300])


# ==========================================================================
#  4. the base file is the one this repository ships, and the fix is in it
# ==========================================================================

def t_the_fix_is_in_the_shipped_base():
    if not BASE_HUD.is_file():
        return skip(f"{BASE_HUD} is not in this checkout")
    src = _hud_source()
    check("the base HUD names cloud-turn-identity where the fix lives",
          "cloud-turn-identity" in src)
    check("... it is added AFTER the cloud cut, never before it",
          src.index("cloud_identity = {") < src.index("body[\"messages\"] = [cloud_identity]"))
    check("... and the cut it rides on is still there (cloud-one-turn.patch)",
          "said[-1:]" in src)
    node = _open_node()
    check("the identity is referenced only inside the non-local branch",
          node is not None
          and ast.unparse(node).count("[cloud_identity]") == 1)


if __name__ == "__main__":
    for fn in (t_the_sentence_is_one_fixed_literal,
               t_every_cloud_lane_carries_it_exactly_once,
               t_the_newest_question_is_still_the_only_user_turn,
               t_a_second_hop_carries_it_once_and_not_twice,
               t_the_sentence_does_not_depend_on_the_question,
               t_a_local_turn_carries_none,
               t_the_fix_is_in_the_shipped_base):
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
