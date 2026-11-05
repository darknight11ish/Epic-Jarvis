"""test_folder_restrictions.py - the owner's own words for "Protected from Jarvis".

    python -B backend/test_folder_restrictions.py

THE OWNER'S REQUEST (2026-11-04): folder-level restrictions settable by plain
chat, on the PC and on the phone. The feature already existed
(`jarvis_protection.py`, 2026-10-31) - a chat answer had failed to reflect it.
So this suite measures the exact sentences, not a paraphrase:

    "restrict the folder D:\\Photos from Jarvis"
    "stop Jarvis reading C:\\X"
    "don't let Jarvis touch the folder with my medical scans"
    "unrestrict D:\\Photos"
    "let Jarvis read that folder again"
    "what folders are restricted?"
    "is Jarvis blocked from C:\\X?"

WHAT THIS SUITE PROVES:

1. EVERY PHRASING BINDS to the protection action - the fast path's own grammar
   (`jarvis_quick.match`) and the model's tool diet (`jarvis_agent`). Before
   this change six of the seven matched nothing, and "restrict the folder ..."
   hid `protect_from_jarvis` from the model entirely (measured: matched 2,
   tools ['file_read', 'my_files']) - the wrong-answer path.
2. THE OLD WRONG ANSWER CANNOT COME BACK. A concrete change sentence used to
   be answered with the rule sentence ("Adding protection from chat raises one
   approval card") and nothing happened; its "is the tool offered" test compared
   gate ACTION names against a list of TOOL names, so it always said the tool
   was not offered. That branch is gone, and no owner sentence may ever be
   answered with it again.
3. THE REAL ROUTE RUNS, NOT A COPY: "restrict <path>" raises ONE
   `protect_item` card through `jarvis_protection.handle_propose`, and
   "unrestrict <path>" raises ONE `unprotect_item` card through
   `handle_remove` - the same functions the model tool and both apps use. The
   store changes only after the card's yes; a denied card changes nothing.
4. THE LIST QUESTION IS ANSWERED FROM REAL STATE, with NO card, and a named
   target gets a yes/no about that target.
5. THE TOOL'S THREE ACTIONS - add / remove / list - through `_one_call`: the
   list answers with no checker call, remove asks under `unprotect_item`, add
   asks under `protect_item`.
6. A PRIVATE CHAT REFUSES the change (it is a mutation), like every other.
7. ENFORCEMENT IS UNCHANGED: all eleven points named in the module's
   ENFORCEMENT list still import the protection module, and the two refusal
   functions still refuse blocked reads and read-only writes.
8. THE RECORDS: this tree's three changed modules are byte-identical to their
   published-base twins.

No network, no owner's files, no real card: a temporary settings folder, a
temporary work folder and a fake gate. `%TEMP%` is used with `mkdir` so the
suite runs under a confinement sandbox as well as CI.
"""
import json
import os
import secrets
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
os.environ.pop("JARVIS_BACKEND", None)

_TMP = Path(tempfile.gettempdir()) / ("jarvis-folder-restrict-" + secrets.token_hex(6))
_TMP.mkdir(parents=True, exist_ok=True)
CONFIG = _TMP / "config"
CONFIG.mkdir(parents=True, exist_ok=True)
WORK = _TMP / "work"
WORK.mkdir(parents=True, exist_ok=True)
STORE = CONFIG / "protected-items.json"
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONFIG)
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["JARVIS_PROTECTION_STORE"] = str(STORE)
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "receipts.db")

# ── a stub jarvis_framework, so nothing reads the owner's real settings ─────
FW = types.ModuleType("jarvis_framework")
FW.CONFIG_DIR = CONFIG
FW.LOG_DIR = _TMP / "log"
FW.audit_log = lambda event, detail=None: None
FW.load_framework = lambda: {"autonomy": {"tiers": {"protect_item": "ask",
                                                    "unprotect_item": "ask"}}}
sys.modules["jarvis_framework"] = FW

OWNC = types.ModuleType("jarvis_owner_check")
OWNC.from_this_pc = lambda peer, local=None, own=None: True
sys.modules["jarvis_owner_check"] = OWNC

import jarvis_agent as AG  # noqa: E402
import jarvis_protection as P  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED = []
FAILED = []


def check(name, cond, got=""):
    if cond:
        PASSED.append(name)
        print(f"ok   {name}")
    else:
        FAILED.append(name)
        print(f"FAIL {name}: {str(got)[:700]}")


def reset_store(items=()):
    P._reset_for_tests()
    P.save([dict(i) for i in items])


class NoSched:
    """What jarvis_quick.answer() asks of a scheduler for these answers."""

    def mark_command(self, *_a, **_k):
        pass

    def note_set(self, *_a, **_k):
        pass

    def forget_set(self, *_a, **_k):
        pass


class Verdict:
    """A gate verdict: allowed, and the outcome word every caller reads."""

    def __init__(self, allowed=True, outcome="approved"):
        self.allowed = allowed
        self.outcome = outcome
        self.tier = "ask"


GATE_CALLS = []


def fake_gate_module():
    """`jarvis_gate` as jarvis_protection's own fallback imports it."""
    mod = types.ModuleType("jarvis_gate")

    def _check(action, detail, prompt=""):
        GATE_CALLS.append({"action": action, "detail": dict(detail or {}),
                           "prompt": prompt})
        return Verdict()

    mod.check = _check
    return mod


def say(text, *, private=False):
    """One turn through the REAL fast path, with a recording fake gate."""
    GATE_CALLS.clear()
    saved = sys.modules.get("jarvis_gate")
    sys.modules["jarvis_gate"] = fake_gate_module()
    try:
        res = Q.answer(text, sched=NoSched(), now=1_800_000_000.0,
                       peer="127.0.0.1", local=True, private=private)
    finally:
        if saved is not None:
            sys.modules["jarvis_gate"] = saved
        else:
            sys.modules.pop("jarvis_gate", None)
    return res, list(GATE_CALLS)


#: The owner's exact sentences, with the shape each must reach. ``{p}`` is a
#: real folder on THIS machine (a Windows drive path at the owner's desk, a
#: POSIX path on Linux CI), so the same table runs in both places.
FOLDER = WORK / "Photos"
FOLDER.mkdir(exist_ok=True)
PATH = str(FOLDER)

CHANGES = (
    (f"restrict the folder {PATH} from Jarvis", "add", PATH),
    (f"restrict {PATH}", "add", PATH),
    # "stop Jarvis reading X" is a RESTRICTION request (the owner's own list
    # groups it with "restrict"), not a removal.
    (f"stop Jarvis reading {PATH}", "add", PATH),
    ("don't let Jarvis touch the folder with my medical scans", "add", ""),
    (f"unrestrict {PATH}", "remove", PATH),
    ("let Jarvis read that folder again", "remove", ""),
    ("protect my taxes folder", "add", ""),
)
READS = (
    ("what folders are restricted?", ""),
    ("which files are blocked?", ""),
    (f"is Jarvis blocked from {PATH}?", PATH),
)


# --------------------------------------------------------------------------
#   1. Every owner phrasing binds, in the fast path and in the tool diet
# --------------------------------------------------------------------------

def t_every_owner_phrasing_binds_to_the_protection_action():
    print("\n-- 1. the owner's own words bind --")
    for text, op, target in CHANGES:
        got = Q.match(text)
        check(f"{text!r} is a protection change (op {op})",
              got is not None and got.name == "protection_apply"
              and got.f.get("op") == op, None if got is None else (got.name, got.f))
        if got is not None and target:
            # The captured words may carry the sentence's wrapper ("the folder
            # ... from"); what is APPLIED is the path the extractor finds, and
            # it must be exactly the one the owner said.
            check("  ... and the path it names is the one that was said",
                  Q._protection_path(str(got.f.get("target") or "")).lower()
                  == target.strip().lower(), got.f)
        elif got is not None:
            # No path in the sentence: it must NOT invent one, so it falls to
            # the model, which can search the owner's folders for the described
            # one. A guessed path here would protect the wrong thing.
            check("  ... and it invents no path for a described folder",
                  Q._protection_path(str(got.f.get("target") or "")) == "",
                  got.f)
    for text, target in READS:
        got = Q.match(text)
        check(f"{text!r} is the protection read",
              got is not None and got.name == "honest_state"
              and got.f.get("shape") == "protection_read", None if got is None else got.name)
        if got is not None and target:
            check(f"  ... and it asks about {target!r}",
                  target.lower() in str(got.f.get("target") or "").lower(), got.f)

    # THE MEASURED WRONG-ANSWER PATH: a wording that matches only file_read's
    # and my_files' hints shows those tools and HIDES the protection tool, so
    # the model answers about "a folder" instead of using the real one.
    allowed = list(AG.TOOLS)
    for text, _op, _target in CHANGES:
        sel = AG.tool_diet_selection(text, allowed)
        check(f"the tool diet shows protect_from_jarvis for {text!r}",
              AG.PROTECT_TOOL in sel["tools"], sel)
    for text, _target in READS:
        sel = AG.tool_diet_selection(text, allowed)
        check(f"the tool diet shows protect_from_jarvis for {text!r}",
              AG.PROTECT_TOOL in sel["tools"], sel)


def t_the_old_rule_answer_cannot_come_back():
    print("\n-- 2. the old wrong answer cannot come back --")
    source = (HERE / "jarvis_quick.py").read_text(encoding="utf-8")
    check("the dead 'protection_change' branch is gone from jarvis_quick.py",
          "protection_change" not in source)
    check("its broken offered-test (gate action vs tool names) is gone",
          '"protect_item" in _enabled_tools_turn()' not in source)
    for text, _op, _target in CHANGES:
        res, _calls = say(text)
        reply = "" if res is None else str(res.reply)
        check(f"{text!r} is never answered with the old rule sentence",
              "raises one approval card" not in reply, reply)
        check(f"  ... and never claims a change it did not make",
              res is None or res.intent == "protection_apply",
              None if res is None else res.intent)


# --------------------------------------------------------------------------
#   3. The real route runs: one card, the store changes only after the yes
# --------------------------------------------------------------------------

def t_restrict_and_unrestrict_run_the_real_route():
    print("\n-- 3. restrict / unrestrict are the feature's own routes --")
    reset_store()
    res, calls = say(f"restrict the folder {PATH} from Jarvis")
    check("'restrict <path>' raises exactly ONE card",
          len(calls) == 1, calls)
    check("  ... under the feature's own action, protect_item",
          calls and calls[0]["action"] == P.ACTION_PROTECT, calls)
    check("  ... and the card names the target and the mode",
          calls and PATH.lower() in str(calls[0]["prompt"]).lower()
          and "blocked" in str(calls[0]["prompt"]).lower(), calls)
    check("  ... the entry is stored after the yes, as added_by chat",
          [i["target"] for i in P.items()] == [P.normal_path(P._real(PATH))]
          and P.items()[0]["added_by"] == "chat", P.items())
    check("  ... and the answer says it is done",
          res is not None and "Done" in str(res.reply), None if res is None else res.reply)

    res, calls = say(f"unrestrict {PATH}")
    check("'unrestrict <path>' raises exactly ONE card",
          len(calls) == 1, calls)
    check("  ... under unprotect_item (removing always asks)",
          calls and calls[0]["action"] == P.ACTION_UNPROTECT, calls)
    check("  ... and the entry is gone after the yes", P.items() == [], P.items())

    # A DENIED card changes nothing - the safe side, proved through the route.
    reset_store()
    P.add_item("folder", PATH, "blocked")
    denied = []

    class DeniedGate(types.ModuleType):
        def check(self, action, detail, prompt=""):
            denied.append(action)
            return Verdict(allowed=False, outcome="denied")

    saved = sys.modules.get("jarvis_gate")
    sys.modules["jarvis_gate"] = DeniedGate("jarvis_gate")
    try:
        res = Q.answer(f"unrestrict {PATH}", sched=NoSched(),
                       now=1_800_000_000.0, peer="127.0.0.1", local=True)
    finally:
        if saved is not None:
            sys.modules["jarvis_gate"] = saved
        else:
            sys.modules.pop("jarvis_gate", None)
    check("a DENIED removal card leaves the entry in place",
          [i["target"] for i in P.items()] == [P.normal_path(P._real(PATH))],
          P.items())
    check("  ... and chat says nothing was changed",
          res is not None and "Nothing was changed" in str(res.reply),
          None if res is None else res.reply)

    reset_store()
    res, calls = say(f"unrestrict {PATH}")
    check("removing protection that is not there is a plain answer, no card",
          calls == [] and res is not None
          and "not on your Protected" in str(res.reply), (calls, res))

    # A described folder has no path to act on. The answer ASKS for it and
    # quotes the sentence to repeat - never a guess at a target, and never a
    # generic "I cannot" (the failure the owner reported). It is deterministic,
    # so it also works on a default install where the model tool is not in
    # `[tools].enabled`.
    reset_store()
    for text in ("don't let Jarvis touch the folder with my medical scans",
                 "let Jarvis read that folder again",
                 "protect my taxes folder"):
        res, calls = say(text)
        check(f"{text!r} asks for the whole path, with no card",
              calls == [] and res is not None
              and "whole path" in str(res.reply)
              and "restrict the folder" in str(res.reply), (calls, res))
        check("  ... and it stored nothing", P.items() == [], P.items())
    reset_store()


# --------------------------------------------------------------------------
#   4. The list question comes from real state, with no card
# --------------------------------------------------------------------------

def t_the_list_answers_from_real_state_with_no_card():
    print("\n-- 4. the list, and one target's real state --")
    reset_store()
    res, calls = say("what folders are restricted?")
    check("an empty list says so", calls == [] and res is not None
          and "Nothing is protected" in str(res.reply), (calls, res))

    P.add_item("folder", PATH, "blocked")
    res, calls = say("what folders are restricted?")
    check("the real entry is listed, in the PC's own words",
          calls == [] and res is not None and PATH.lower() in str(res.reply).lower()
          and "Blocked - no access" in str(res.reply), (calls, res))

    res, calls = say(f"is Jarvis blocked from {PATH}?")
    check("'is Jarvis blocked from <path>?' answers YES from the store",
          calls == [] and res is not None
          and str(res.reply).startswith("Yes") and PATH.lower() in str(res.reply).lower(),
          (calls, res))

    other = WORK / "Photos2"
    other.mkdir(exist_ok=True)
    res, calls = say(f"is Jarvis blocked from {other}?")
    check("... and NO for a folder that is not on the list",
          calls == [] and res is not None and str(res.reply).startswith("No"),
          (calls, res))
    reset_store()


# --------------------------------------------------------------------------
#   5. The model tool's three actions, through _one_call
# --------------------------------------------------------------------------

def one_call(args, checker):
    """Drive the real `_one_call` for the protection tool and read the answer."""
    call = {"id": "call-1", "function": {"name": AG.PROTECT_TOOL,
                                        "arguments": json.dumps(args)}}
    convo, steps = [], []

    class Out:
        status = None
        gone = False

        def set_status(self, word):
            self.status = word

        def card_answered(self, verdict):
            pass

    AG._one_call(call, [AG.PROTECT_TOOL], convo, steps, checker,
                 lambda *_a, **_k: None, Out(), lambda *_a, **_k: None)
    result = json.loads(convo[-1]["content"]) if convo else {}
    return result, steps


def t_the_tool_has_three_actions_and_the_right_card_each():
    print("\n-- 5. the model tool: add, remove, list --")
    tool = AG.TOOLS[AG.PROTECT_TOOL]
    props = tool.schema()["function"]["parameters"]["properties"]
    check("the tool's schema offers add / remove / list",
          props.get("action", {}).get("enum") == ["add", "remove", "list"], props)
    check("add still needs kind, target and mode at prepare() time",
          "kind" in props and "target" in props and "mode" in props, props)

    reset_store()
    P.add_item("folder", PATH, "blocked")

    # list: no card at all, and the REAL entries come back.
    result, steps = one_call({"action": "list"}, checker=_never_a_card)
    check("action=list asks nobody (no gate call) and answers the real list",
          result.get("ok") is True and result.get("count") == 1
          and result["items"][0]["target"] == P.normal_path(P._real(PATH)),
          result)
    check("  ... and the step is recorded as 'no card needed'",
          steps and steps[-1]["outcome"] == "no card needed", steps)

    result, _steps = one_call({"action": "list", "target": PATH},
                              checker=_never_a_card)
    check("action=list with ONE target answers whether it is protected",
          result.get("ok") is True and result.get("check") is True
          and result.get("protected_item", {}).get("target")
          == P.normal_path(P._real(PATH)), result)

    # remove: ONE unprotect_item card, then the entry leaves.
    seen = []

    def remove_checker(action, detail, prompt):
        seen.append((action, detail, prompt))
        return Verdict()

    result, _steps = one_call({"action": "remove", "target": PATH}, remove_checker)
    check("action=remove asks under unprotect_item",
          len(seen) == 1 and seen[0][0] == P.ACTION_UNPROTECT, seen)
    # The card's own line is the plan text in `detail["text"]` (the gate shows
    # that as the card's body; `prompt` is the generic tool-call line).
    check("  ... the card says 'stop protecting' in plain words",
          seen and "stop protecting" in str(seen[0][1].get("text") or "").lower(),
          seen)
    check("  ... and the entry is gone only after that yes",
          P.items() == [] and result.get("ok") is True
          and result.get("removed", {}).get("target") == P.normal_path(P._real(PATH)),
          (P.items(), result))

    # remove of something not protected: a plain refusal, no card.
    result, steps = one_call({"action": "remove", "target": PATH}, _never_a_card)
    check("action=remove of an unprotected target asks nobody",
          result.get("ok") is False and "not on your Protected" in result.get("error", ""),
          result)
    check("  ... and the step is 'refused'",
          steps and steps[-1]["outcome"] == "refused", steps)

    # add: ONE protect_item card, then the entry is stored as chat's.
    seen = []

    def add_checker(action, detail, prompt):
        seen.append((action, prompt))
        return Verdict()

    result, _steps = one_call({"action": "add", "kind": "folder", "target": PATH,
                              "mode": "blocked"}, add_checker)
    check("action=add asks under protect_item",
          len(seen) == 1 and seen[0][0] == P.ACTION_PROTECT, seen)
    check("  ... and stores only after that yes, as added_by chat",
          result.get("ok") is True and P.items()
          and P.items()[0]["added_by"] == "chat", (result, P.items()))
    reset_store()


def _never_a_card(*_a, **_k):
    raise AssertionError("a card was raised where none was needed")


# --------------------------------------------------------------------------
#   6. A private chat refuses the change
# --------------------------------------------------------------------------

def t_a_private_chat_refuses_the_change():
    print("\n-- 6. a private chat refuses a change --")
    reset_store()
    res, calls = say(f"restrict the folder {PATH} from Jarvis", private=True)
    check("a private chat does not raise a card for a change",
          calls == [], calls)
    check("  ... it answers with the private refusal instead",
          res is not None and res.private is True, res)
    check("  ... and nothing was stored", P.items() == [], P.items())


# --------------------------------------------------------------------------
#   7. Enforcement is unchanged: all eleven points still ask the module
# --------------------------------------------------------------------------

#: The eleven enforcement points, by the module that owns each (the list in
#: jarvis_protection.py's ENFORCEMENT section). NONE of them was edited by this
#: change: the feature's own refusals are what they were.
ENFORCEMENT_MODULES = (
    "jarvis_documents.py",        # 1. the folders allow-list door
    "jarvis_agent.py",            # 2. file_read and my_files preflight
    "jarvis_note_capture.py",     # 3. the daily-note write
    "jarvis_notes.py",            # 4. the vault's guarded write door
    "jarvis_attached_file.py",    # 5. chat attachments
    "jarvis_file_guardian.py",    # 6. every guardian write / restore
    "jarvis_open.py",             # 7. opening a program
    "jarvis_ui_control.py",       # 8. looking at or acting in a window
    "jarvis_screen.py",           # 9. screen capture
    "jarvis_schedule.py",         # 10. a reminder that opens a file
    "jarvis_pictures.py",         # 11. a generated picture
)


def t_every_enforcement_point_still_asks_the_module():
    print("\n-- 7. every enforcement point still asks the module --")
    for name in ENFORCEMENT_MODULES:
        path = HERE / name
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        check(f"{name} still imports/asks jarvis_protection",
              "jarvis_protection" in text, name)
    doc = (HERE / "jarvis_protection.py").read_text(encoding="utf-8")
    check("the module still names eleven numbered enforcement points",
          all(f"\n  {n}." in doc for n in range(1, 12)), doc[:200])
    reset_store()
    P.add_item("folder", PATH, "blocked")
    check("a blocked folder still refuses a read (plain sentence, no card)",
          "will not read it" in P.path_refusal(PATH, what="read it")
          or "will not" in P.path_refusal(PATH), P.path_refusal(PATH))
    check("a blocked folder still refuses a write",
          bool(P.path_refusal(str(FOLDER / "x.txt"), write=True)))
    reset_store()
    P.add_item("folder", PATH, "readonly")
    check("a read-only folder still allows a read",
          P.path_refusal(PATH) == "")
    check("  ... and still refuses a write",
          bool(P.path_refusal(str(FOLDER / "x.txt"), write=True)))
    reset_store()


# --------------------------------------------------------------------------
#   8. The records: the three modules and their published-base twins
# --------------------------------------------------------------------------

def t_changed_modules_have_identical_twins():
    print("\n-- 8. every changed module's twin is byte-identical --")
    for name in ("jarvis_protection.py", "jarvis_agent.py", "jarvis_quick.py"):
        check(f"backend/{name} == jarvis-backend/{name}",
              (HERE / name).read_bytes()
              == (REPO / "jarvis-backend" / name).read_bytes(), name)


if __name__ == "__main__":
    for fn in (t_every_owner_phrasing_binds_to_the_protection_action,
               t_the_old_rule_answer_cannot_come_back,
               t_restrict_and_unrestrict_run_the_real_route,
               t_the_list_answers_from_real_state_with_no_card,
               t_the_tool_has_three_actions_and_the_right_card_each,
               t_a_private_chat_refuses_the_change,
               t_every_enforcement_point_still_asks_the_module,
               t_changed_modules_have_identical_twins):
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
