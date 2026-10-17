"""test_chatbot_privacy.py - what must never leave this PC for another AI.

    python3 backend/test_chatbot_privacy.py

WHY THIS EXISTS. The feature page says, of "Talk to a chatbot for me", in plain
words: **"Nothing private - email, files, credentials, memory - goes into those
chats."** (`features/features.json`, the `chatbot` entry's `limit`). That is a
promise to the owner, and `docs/DECISIONS.md` records the owner saying the same
of the whole feature: *"Rule 1 is unchanged: nothing private (email, files,
credentials, memory) goes into those chats"* (2026-09-27 and 2026-09-28, and
again under "Stealth on for everything", 2026-09-29).

`backend/test_chatbot.py` already pins most of it, and well:
  * `t_clean_context` (line 665) replaces ELEVEN private modules - memory,
    email, notes, calendar, chat history, documents, recall, intake, extract,
    home, past - with objects that RECORD the touch and then raise, so a read
    is a failure even when the code swallows the exception (line 660's
    `FORBIDDEN`, the trap at 652-657, the check at 681-682);
  * the same test seeds five saved facts and proves none reaches the driver
    prompt (line 696-697), and pins the module's only `jarvis_memory` import to
    the last check's own fact reader (line 725-727);
  * the last check's own strand - "does this message repeat a saved fact?" -
    is pinned by `t_last_check.`* (removing it fails twelve checks).

WHAT IT DOES NOT PIN, AND WHY THIS FILE EXISTS. That list of eleven is a list
written by hand in 2026-10, and a private store arrived afterwards: the owner's
own writing, `voiceprint.db` (#436, 2026-10-14, `jarvis_voiceprint.py`). It is
not on the list, and no test seeds it. MEASURED, not argued (2026-10-16): with
the driver's prompt changed to prepend `jarvis_voiceprint.samples(3)` - the
owner's own words, the most private text this PC holds - the sample DID reach
the driver model's request body and `backend/test_chatbot.py` was still GREEN,
232 passed, 0 failed. That is a guard pinned by nothing: exactly the shape
#496 found twice. The same experiment against `jarvis_memory` (saved facts and
the pinned "Always keep in mind" facts) is caught at once by the trap above, so
the memory half of the promise was already safe.

So this file pins the promise from the OUTSIDE, in the two ways that do not go
stale when the next private store lands:

  1. SEED AND LOOK. A fake memory (one saved fact, one pinned fact) and a fake
     voiceprint (one sample of the owner's own writing) are installed where the
     driver would really find them, a whole conversation runs, and NOT ONE of
     the three seeds may appear in any driver-model request body or in anything
     the chatbot was sent. This is behavioural, so a lookup written inside
     `try/except` cannot hide from it - the text would still be in the payload.
  2. TRAP AND COUNT. The same stores are installed as objects that RECORD every
     attribute touched and then raise, so any future read - even one whose
     exception is swallowed - is a failure that names what was touched. This is
     the module-trap idea `test_chatbot.py` uses, extended to the two stores
     that are new since it was written.

Neither of them is a duplicate of `test_chatbot.py`: (1) seeds nothing that
suite seeds (a PINNED fact and a voiceprint sample; that suite seeds saved
facts, which are a different table and a different code path), and (2) names
the style store, which that suite does not name at all. Both were BITTEN
before being committed - see `BITE PROOF` below.

BITE PROOF (both measured in the review worktree on 2026-10-16, each a
temporary edit to `backend/jarvis_chatbot.py` and its `jarvis-backend/` twin,
restored afterwards):
  * `jarvis_voiceprint.samples(3)` prepended in `context_text`: the sample
    reached the request body, `test_chatbot.py` stayed green at 232/0, and
    THIS suite went red - on "no style sample reaches the driver model" and on
    "jarvis_voiceprint was never touched".
  * pinned + saved facts prepended in `context_text`: both reached the request
    body and THIS suite went red on the same two tests.

NOTHING HERE TOUCHES THE OWNER'S PC. Every store is a stand-in, no store on
disk is opened, no socket is opened, no model is called and no browser window
exists. The driver itself is the real `jarvis_chatbot.py`; its model and its
chatbot are the suite's stand-ins, the same way `test_chatbot.py` drives it.

Standard library only. No network beyond nothing at all.
"""
from __future__ import annotations

import ast
import json
import sys
import tempfile
import types
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_chatbot.py", "jarvis_task_control.py", "jarvis_stop_all.py",
                "jarvis_search.py", "jarvis_mail_mask.py", "rebuilt/jarvis_router.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.insert(1, str(HERE / "rebuilt"))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-chatbot-privacy-"))
CFG: dict = {}
TIERS: dict = {}
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: CFG
fw.audit_log = lambda *a, **k: None
fw.action_tier = lambda action: TIERS.get(action, "ask")
sys.modules["jarvis_framework"] = fw

import jarvis_stop_all as SA  # noqa: E402,F401
import jarvis_task_control as TC  # noqa: E402
import jarvis_chatbot as CB  # noqa: E402
import jarvis_support as SUP  # noqa: E402
import jarvis_chatbot_routes as R  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


#: Built by joining strings, so no real-looking secret sits whole in this file
#: for a scanner to trip on - the same rule test_chatbot.py follows.
PINNED = "The owner's passport lives in the blue " + "drawer"
SAVED = "The owner's sister is called Zyl" + "vana"
SAMPLE = "I reckon we ought to give it another go next week, " + "love"

GOAL = "Find out whether a north-facing window is enough for a snake plant."
QUESTIONS = ["Which plants cope best with a north-facing window?",
             "What sources support the claim about snake plants?"]
REPLIES = ["Snake plants and ZZ plants tolerate dim corners remarkably well.",
           "Extension services publish guidance about sansevieria resilience."]

#: The two private stores this file exists for. The first half is the module
#: `test_chatbot.py` already names; the second is the one it does not.
NEW_STORES = ("jarvis_memory", "jarvis_voiceprint")


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = float(t)

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(0.0, float(s))


class Verdict:
    def __init__(self, allowed, outcome, tier="ask"):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier


CARDS: list = []
AUDIT: list = []


def approve(action, detail, prompt):
    CARDS.append((action, detail, prompt))
    return Verdict(True, "approved")


class Model:
    """The driver model's stand-in: every request kept, verbatim."""

    def __init__(self):
        self.bodies: list = []
        self.urls: list = []
        self.n = 0

    def __call__(self, url, body):
        self.urls.append(url)
        self.bodies.append(json.loads(json.dumps(body)))
        if body.get("format") == CB.SUMMARY_SCHEMA:
            return {"message": {"content": json.dumps(
                {"answer": "A north-facing window can suit snake plants.",
                 "claims": [{"claim": "Snake plants tolerate low light",
                             "source_given": False}],
                 "open": ["Which lamp to buy"]})}, "done_reason": "stop"}
        self.n += 1
        move = {"move": "deeper", "message": QUESTIONS[(self.n - 1) % len(QUESTIONS)],
                "reason": "", "notes": f"note {self.n}"}
        return {"message": {"content": json.dumps(move)}, "done_reason": "stop"}


def replies(text, n):
    return REPLIES[(n - 1) % len(REPLIES)]


def deps(model=None, bot=None):
    clock = Clock()
    return CB.Deps(model=model or Model(), saved_facts=lambda m: [],
                   names_for_facts=lambda f: {}, owner_busy=lambda: False,
                   second_lane=lambda: None, full_version_on=lambda: False,
                   main_lane=lambda: ("http://127.0.0.1:11434", "jarvis-primary"),
                   tier_of=lambda a: TIERS.get(a, "ask"), gate=approve,
                   activity=lambda s, d="": None,
                   audit=lambda e, d: AUDIT.append((e, d)), clock=clock,
                   sleep=clock.sleep,
                   make_adapter=(lambda cid: bot) if bot is not None else None,
                   allow_test_adapters=True, lockdown_on=lambda: False)


def clean():
    CB._reset_for_tests()
    with TC._lock:
        TC._running.clear()
        TC._paused.clear()
        TC._signals.clear()
        TC._notes.clear()
        TC._resuming.clear()
    CARDS.clear()
    AUDIT.clear()
    TIERS.clear()
    CFG.clear()


def conversation(model):
    """One whole conversation with the real driver. Returns (session, chatbot)."""
    clean()
    bot = CB.FakeChatbot(replies=replies)
    d = deps(model=model, bot=bot)
    s = CB.plan("fake", GOAL, deps=d, max_turns=2)
    code, out = CB.start(s, deps=d, wait=True)
    return s, bot, code, out


class _Guard:
    """Swap modules in `sys.modules` for the length of one test, then back."""

    def __init__(self, replacements: dict):
        self.replacements = dict(replacements)
        self.saved: dict = {}

    def __enter__(self):
        for name, module in self.replacements.items():
            self.saved[name] = sys.modules.get(name)
            sys.modules[name] = module
        return self

    def __exit__(self, *exc):
        for name, module in self.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        return False


def fake_memory():
    """A jarvis_memory stand-in that answers with a SAVED and a PINNED fact."""

    class Store:
        def search(self, *a, **k):
            return [{"text": SAVED}]

        def profile(self):
            return [{"id": 1, "text": PINNED, "added": "2026-10-01", "how": "owner"}]

        def is_pinned(self, fact_id):
            return int(fact_id) == 1

    module = types.ModuleType("jarvis_memory")
    module.store = lambda: Store()
    module.with_profile = lambda st, hits, k, manner=None: [
        {"id": 1, "text": PINNED, "pinned": True, "current": True}]
    return module


def fake_voiceprint():
    """A jarvis_voiceprint stand-in that answers with a SAMPLE of his writing."""
    module = types.ModuleType("jarvis_voiceprint")
    module.samples = lambda limit=50: [{"id": "s1", "kind": "sample", "prompt": "",
                                        "text": SAMPLE}]
    module.prompt_block = lambda about, k=None, store=None: (
        "SAMPLES OF THE OWNER'S OWN WRITING (match this style):\n" + SAMPLE)
    module.exemplars = lambda about, k=None, store=None: [{"text": SAMPLE}]
    return module


class Recorder(types.ModuleType):
    """A module whose every attribute is a FAILURE, recorded before it raises -
    so a read inside `try/except` still fails the test that owns it."""

    def __init__(self, name, touched):
        super().__init__(name)
        self._touched = touched

    def __getattr__(self, attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        self._touched.append(f"{self.__name__}.{attr}")
        raise AssertionError(f"{self.__name__}.{attr} was touched")


# ==========================================================================
#   1. the promise itself: seed the private text and look in the payload
# ==========================================================================

def t_no_private_text_reaches_the_driver_or_the_chatbot():
    """A saved fact, a pinned fact and a sample of the owner's writing are all
    available to the driver; none of the three may be in what it is shown or
    in what the chatbot is sent."""
    model = Model()
    with _Guard({"jarvis_memory": fake_memory(),
                 "jarvis_voiceprint": fake_voiceprint()}):
        s, bot, code, _out = conversation(model)
    bodies = json.dumps(model.bodies, ensure_ascii=False)
    sent = json.dumps(bot.sent, ensure_ascii=False)

    # The control: a conversation that never ran would pass the three checks
    # below by having nothing to look at. This is what stops that.
    check("a whole conversation ran, with requests AND messages sent",
          len(model.bodies) >= 2 and len(bot.sent) == 2 and s.turns_used == 2,
          (len(model.bodies), len(bot.sent), s.turns_used))
    check("no saved fact reaches the driver model",
          SAVED not in bodies, bodies[:1200])
    check("no pinned fact (\"Always keep in mind\") reaches the driver model",
          PINNED not in bodies, bodies[:1200])
    check("no sample of the owner's own writing reaches the driver model",
          SAMPLE not in bodies, bodies[:1200])
    check("... and none of the three is typed into the chatbot either",
          not any(seed in sent for seed in (SAVED, PINNED, SAMPLE)), sent[:800])


def t_a_saved_fact_puts_nothing_on_the_wire_even_by_the_back_door():
    """The same seeds again, but asked of the two things the last check and the
    summary do with a finished conversation - a saved fact must not appear in
    the session view or the summary either (both are shown to the owner, and
    the summary is written by the driver model)."""
    model = Model()
    with _Guard({"jarvis_memory": fake_memory(),
                 "jarvis_voiceprint": fake_voiceprint()}):
        s, _bot, _code, _out = conversation(model)
    view = json.dumps(CB.view(s.id), ensure_ascii=False)
    check("the saved fact is nowhere in the session view the apps draw",
          SAVED not in view and PINNED not in view, view[:800])
    check("... and the summary the apps show carries none of it either",
          SAVED not in json.dumps(s.summary) and SAMPLE not in json.dumps(s.summary),
          s.summary)


# ==========================================================================
#   2. the trap: no future read of either store, even a swallowed one
# ==========================================================================

def t_the_private_stores_are_never_touched():
    """Memory and the owner's own writing store are objects that record a touch
    and then raise. Any read during a whole conversation fails here, and the
    failure names what was read - which is how a lookup inside `try/except`
    cannot hide from this test."""
    touched: list = []
    model = Model()

    class Guarded(types.ModuleType):
        def __getattr__(self, attr):
            if attr.startswith("__"):
                raise AttributeError(attr)
            touched.append(f"{self.__name__}.{attr}")
            raise AssertionError(f"{self.__name__}.{attr} was touched")

        def __bool__(self):
            return True

    with _Guard({name: Guarded(name) for name in NEW_STORES}):
        s, bot, code, _out = conversation(model)
    check("neither memory nor the writing store was touched at all",
          not touched, touched)
    check("... and that is a real conversation, not one that stopped before it ran",
          len(model.bodies) >= 2 and len(bot.sent) == 2, (len(model.bodies), bot.sent))

    # A store that is MISSING entirely must not change the answer either: an
    # absent module is not a licence to fall back to reading a file directly.
    touched.clear()
    model = Model()
    with _Guard({name: None for name in NEW_STORES}):
        s, bot, code, _out = conversation(model)
    check("with neither store installed the conversation still runs and sends",
          len(bot.sent) == 2 and len(model.bodies) >= 2, (bot.sent, len(model.bodies)))
    check("... and still nothing private is in the request",
          SAVED not in json.dumps(model.bodies) and SAMPLE not in json.dumps(model.bodies),
          json.dumps(model.bodies)[:800])


# ==========================================================================
#   3. the source: the driver cannot reach a private reader by import
# ==========================================================================

def t_the_module_imports_no_reader_of_private_text():
    """A source pin, so a module cannot be reached around the traps by importing
    it at module level and caching a store at import time. `jarvis_memory` gets
    its ONE allowed lazy import (the last check's own fact reader, which is
    what keeps a saved fact out); the writing store has no business here at
    all."""
    src = (HERE / "jarvis_chatbot.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = set()
    top_level = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module.split(".")[0])
    check("the driver never imports the owner's writing store",
          "jarvis_voiceprint" not in imported and "jarvis_style" not in imported,
          sorted(imported & {"jarvis_voiceprint", "jarvis_style"}))
    check("the driver never imports the chat agent, which is what styles a turn",
          "jarvis_agent" not in imported, sorted(imported & {"jarvis_agent"}))
    check("no private store is imported at module level (nothing cached early)",
          not (top_level & {"jarvis_memory", "jarvis_voiceprint", "jarvis_style"}),
          sorted(top_level & {"jarvis_memory", "jarvis_voiceprint", "jarvis_style"}))
    check("jarvis_memory is imported ONCE, inside the last check's own fact reader",
          src.count("import jarvis_memory") == 1
          and "def _default_saved_facts" in src.split("import jarvis_memory")[0][-400:])


# ==========================================================================
#   4. the shape: what the driver request may contain at all
# ==========================================================================

def t_the_driver_request_is_the_fixed_shape():
    """The control under all of the above: if the request grew a field (tools,
    a second system message, a context block), every check above could still
    pass while the driver was being handed something else entirely."""
    model = Model()
    s, bot, code, _out = conversation(model)
    keys = {"model", "stream", "think", "format", "messages", "options"}
    check("every request has exactly the fixed fields - no tools, ever",
          bool(model.bodies) and all(set(b) == keys for b in model.bodies),
          [sorted(b) for b in model.bodies])
    check("every request goes to a model on this PC",
          all(CB._is_loopback(u) for u in model.urls), model.urls)
    check("each request is the fixed instruction, then one message from the session",
          all([m["role"] for m in b["messages"]] == ["system", "user"]
              and b["messages"][0]["content"] in (CB.FIXED_INSTRUCTION,
                                                  CB.SUMMARY_INSTRUCTION)
              for b in model.bodies), [b.get("format") for b in model.bodies])


# ==========================================================================
#   5. the support chat's export: the optional scrubbed copy
# ==========================================================================

#: Built by joining strings, the same rule the rest of this file follows.
KEY = "AK" + "IA" + "FAKE0123456789AB"
EMAIL = "zyl" + "vana" + "@" + "example.org"
ORDER = "ORDER-" + "123456"


def _exported_chat():
    """A finished support chat as `export_text` sees it - it only reads fields,
    so a plain namespace is enough and no live chat, widget or store is built."""
    return types.SimpleNamespace(
        created=1_000_000.0, company_name="Acme", help_url="https://help.acme.test",
        goal="Get a refund for the order I placed last week",
        details=(("Order number", ORDER), ("Email", EMAIL)),
        transcript=[
            {"who": "jarvis", "at": 1_000_100.0,
             "text": f"It is {ORDER} and the account is {EMAIL}"},
            {"who": "company", "at": 1_000_200.0,
             "text": f"Thanks. I can see the key {KEY} on the account."}],
        offers=[], reference="", ended_words="")


def t_the_support_export_has_a_scrubbed_copy():
    """The promise the page makes is "the transcript can be exported as a file
    that is NOT encrypted" - and that stays true. The scrubbed copy is the
    option that makes such a file safe to keep or send: the VALUES the owner
    allowed are replaced, and a key, password or one-time code cannot ride
    along, in either side's words."""
    c = _exported_chat()
    plain = SUP.export_text(c)
    safe = SUP.export_text(c, scrub=True)
    check("the plain copy keeps the whole chat and still says it is NOT encrypted",
          "NOT encrypted" in plain and ORDER in plain and EMAIL in plain and KEY in plain,
          plain[:500])
    check("the scrubbed copy says what was taken out, and still says not encrypted",
          "SCRUBBED" in safe and "NOT encrypted" in safe, safe[:600])
    check("... the values of the details the owner allowed are GONE from it",
          ORDER not in safe and EMAIL not in safe, safe[:900])
    check("... but their NAMES stay, so a reader knows what Jarvis could give",
          "Order number" in safe and "Email" in safe, safe[:500])
    check("... and a key-shaped value is gone from the COMPANY's own words too",
          KEY not in safe, safe[:900])
    check("... and it is still the conversation, not an empty file",
          "Thanks" in safe and "[outside text]" in safe, safe[:900])


def t_a_scrubbed_copy_is_refused_when_the_scrubber_is_missing():
    """No scrubber, no scrubbed copy. A plain file handed over under the
    scrubbed note is exactly the "it says it did, and it did not" failure this
    project has paid for more than once, so the answer is a refusal."""
    c = _exported_chat()
    real = SUP._scrubber
    SUP._scrubber = lambda: None
    raised, words = False, ""
    try:
        SUP.export_text(c, scrub=True)
    except RuntimeError as exc:
        raised, words = True, str(exc)
    finally:
        SUP._scrubber = real
    check("with no scrubber the scrubbed copy is REFUSED, not quietly plain",
          raised and "not there" in words and "Nothing was exported" in words, words)
    check("... and the plain copy still works, so the owner is not stuck",
          ORDER in SUP.export_text(c))


def t_the_route_passes_scrub_through():
    """`?scrub=1` on the export route must reach the export; anything else -
    absent, empty, `0` - must ask for the plain copy the desktop's button
    already shows. The route reports what the export answered, nothing else."""
    seen: list = []
    real = SUP.export

    def spy(sid, *, scrub=False):
        seen.append((sid, scrub))
        return 200, {"ok": True, "filename": "x.txt", "text": "", "note": ""}
    SUP.export = spy
    try:
        code1, _ = R.handle_export("id=sup_000000000abc&scrub=1")
        code2, _ = R.handle_export("id=sup_000000000abc")
        code3, _ = R.handle_export("id=sup_000000000abc&scrub=0")
        code4, _ = R.handle_export("id=sup_000000000abc&scrub=")
    finally:
        SUP.export = real
    check("the route asks for the scrubbed copy only when it is told to",
          [s for _sid, s in seen] == [True, False, False, False], seen)
    check("... and every call was answered 200", (code1, code2, code3, code4) == (200,) * 4,
          (code1, code2, code3, code4))
    check("... with a bad id still refused as 400",
          R.handle_export("id=../x&scrub=1")[0] == 400)


if __name__ == "__main__":
    for fn in (t_no_private_text_reaches_the_driver_or_the_chatbot,
               t_a_saved_fact_puts_nothing_on_the_wire_even_by_the_back_door,
               t_the_private_stores_are_never_touched,
               t_the_module_imports_no_reader_of_private_text,
               t_the_driver_request_is_the_fixed_shape,
               t_the_support_export_has_a_scrubbed_copy,
               t_a_scrubbed_copy_is_refused_when_the_scrubber_is_missing,
               t_the_route_passes_scrub_through):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
