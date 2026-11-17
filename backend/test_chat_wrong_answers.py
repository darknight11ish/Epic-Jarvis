"""test_chat_wrong_answers.py - seven measured wrong answers on the chat fast path.

    python -B backend/test_chat_wrong_answers.py

WHY THIS SUITE EXISTS (2026-11-16). The owner measured six sentences against
the live install (VERSION 0.2.456, commit b1547d74c) that the deterministic
fast path got wrong. Each is proved here by BEHAVIOUR - the intent the matcher
returns and the words the answer says - never by reading the module's source:

1. "stop" / "stop it" / "be quiet" / "enough" reached the model (no intent at
   all) although the tray has a real "Stop everything". One intent now calls
   `jarvis_stop_all.stop_all()` - the same function POST /api/stop_all calls -
   with NO approval card, and it never swallows "stop the reminder",
   "stop listening", "stop the timer" or "stop recording".
2. "show my github pull requests" was refused with "No - I never copy a
   repository to this PC" because the word "pull" in "pull request" was read
   as a clone/push/pull verb. "pull request(s)" is a noun now; "pull my
   repository", "clone my repo" and "check out my repo" still refuse.
3. "approve that pull request" answered "Yes." - the merge shape's own
   opening - although Jarvis can never approve a pull request. It now gets its
   own deterministic refusal, and the ban list the gate consults carries
   "approve" already (this suite proves both).
4. "pin a note" was read as a note called "a". It now asks which note, writing
   nothing, in the same fixed words the create path uses to ask for a name.
5. "favourite my workout log note" (and "favorite") had no intent. Favourite is
   its own `favorite: true` property - never an alias of `pinned` - settable
   and removable on an existing note (one edit_vault_note card, as pin), and
   settable on a new note ("make a note called X and favourite it").
6. "is my workout log note pinned" had no intent either. The read-back answers
   pinned and favourited from the note's own front matter, read-only.

7. "delete the repo" / "delete this repo" / "delete the Epic-Jarvis
   repository" / "remove the repository" / "close all the pull requests"
   answered "Yes - with ONE approval card per merge, and merge commit only."
   - the worst sentence this app says - although Jarvis has no tool that
   deletes a repository and bulk close is banned. An independent audit the
   same day found three siblings still on that merge sentence: "close the
   repo" (closing a repository is destruction), "delete the pull request" and
   "delete all the pull requests"; and "close pull request 1299" was answered
   as if closing one pull request were a merge. Each now has its own permanent
   refusal, and the repository ban it cites is read from `jarvis_github.NEVER`
   at answer time (this suite proves the set carries it).

A NOTE ON THE PERMISSION MODEL. A new note is card-free (the owner's decision
of 2026-10-31) and pinning/favouriting an EXISTING note is an edit, so it keeps
the one `edit_vault_note` card, the File Guardian copy and the Undo - the
suite drives a fake card and proves exactly one is asked. Stopping asks for
none, because a stop only ever makes Jarvis do less.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
# The live backend's copy is older than this branch until the deploy pass, and
# `require_shipped` would refuse to run for that reason alone. This suite is
# about the repository's own code, so the ambient install is ignored exactly as
# the notes suites ignore it.
os.environ.pop("JARVIS_BACKEND", None)
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_notes_edit.py", "jarvis_stop_all.py")

_TMP = Path(tempfile.gettempdir()) / ("jarvis-chat-wrong-" + secrets.token_hex(6))
_TMP.mkdir(parents=True, exist_ok=True)
VAULT = _TMP / "vault"
(VAULT / ".obsidian").mkdir(parents=True, exist_ok=True)
CONF = _TMP / "config"
CONF.mkdir(exist_ok=True)
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONF)
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "receipts.db")
os.environ["JARVIS_OBSIDIAN_VAULT"] = str(VAULT)
os.environ.setdefault("HF_HUB_OFFLINE", "1")

FW = types.ModuleType("jarvis_framework")
FW.CONFIG_DIR = CONF
FW.LOG_DIR = _TMP / "log"
FW_STATE = {"notes": {"obsidian": {"vault_directory": str(VAULT)}}}
FW.load_framework = lambda: json.loads(json.dumps(FW_STATE))
FW.action_tier = lambda action: "ask" if action == "edit_vault_note" else "auto"
AUDIT = []
FW.audit_log = lambda event, detail: AUDIT.append((event, detail))
sys.modules["jarvis_framework"] = FW

_GATE_MODULE = types.ModuleType("jarvis_gate")


class _Approved:
    allowed = True
    outcome = "approved"
    tier = "auto"
    reason = ""


_GATE_MODULE.check = lambda *a, **k: _Approved()
_GATE_MODULE.taint_active = lambda: False
sys.modules["jarvis_gate"] = _GATE_MODULE

import jarvis_grants as JG  # noqa: E402
import jarvis_notes_edit as E  # noqa: E402
import jarvis_quick as Q  # noqa: E402

#: A fixed clock, so nothing here depends on the day the suite runs.
NOW = time.mktime(time.strptime("2026-11-16 10:30:00", "%Y-%m-%d %H:%M:%S"))

FAILED, PASSED, SKIPPED = [], [], []


def skip(name: str, why: str) -> None:
    SKIPPED.append(name)
    print(f"skip  {name}: {why}")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if not cond else ""))


class Stub:
    """The scheduler the fast path needs; it records nothing and runs nothing."""

    def mark_command(self, text):
        pass

    def forget_set(self, conversation):
        pass


def reset_vault() -> None:
    for child in list(VAULT.iterdir()):
        if child.name == ".obsidian":
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    E._reset_for_tests()


def write_note(rel: str, text: str) -> Path:
    p = VAULT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def read(rel: str) -> str:
    return (VAULT / rel).read_text(encoding="utf-8")


def ask(text: str):
    return Q.answer(text, sched=Stub(), now=NOW, peer="127.0.0.1", local=True)


class Verdict:
    def __init__(self, allowed, tier="ask", outcome="approved", reason=""):
        self.allowed = allowed
        self.tier = tier
        self.outcome = outcome
        self.reason = reason


class Gate:
    """A fake approval card: records every call, answers without a person."""

    def __init__(self, allowed=True, outcome="approved"):
        self.allowed = allowed
        self.outcome = outcome
        self.calls = []

    def __call__(self, action, detail, prompt):
        self.calls.append((action, dict(detail or {}), prompt))
        return Verdict(self.allowed, "ask", self.outcome)


def set_gate(gate) -> None:
    E._gate_check = gate                 # the module's own fail-closed wrapper


# --------------------------------------------------------------------------
# 1. "stop" reaches Stop everything, and nothing else
# --------------------------------------------------------------------------
STOP_SENTENCES = ("stop", "stop it", "be quiet", "enough", "Stop.", "stop everything",
                  "that's enough", "shut up")
STOP_NEAR_MISSES = ("stop the reminder", "stop listening", "stop the timer",
                    "stop recording", "stop watching")


def t_stop_is_one_deterministic_intent():
    for said in STOP_SENTENCES:
        got = Q.match(said)
        check(f"stop: {said!r} is the one stop intent",
              got is not None and got.name == "stop_all",
              got.name if got else "model")
    for said in STOP_NEAR_MISSES:
        got = Q.match(said)
        check(f"stop: {said!r} is NOT the stop-everything intent",
              getattr(got, "name", None) != "stop_all",
              got.name if got else "model")


def t_stop_calls_stop_all_and_asks_no_card():
    calls, cards = [], []
    fake = types.ModuleType("jarvis_stop_all")
    fake.NOTHING = "Nothing was running, so there was nothing to stop."
    fake.stop_all = lambda by="": (calls.append(by)
                                   or {"message": "Stopped everything. The task that "
                                                  "was running stops before its next step."})
    gate = Gate()
    gate_calls = []

    def _card(action, detail, prompt):
        gate_calls.append(action)
        return gate(action, detail, prompt)

    saved_mod, saved_gate = sys.modules.get("jarvis_stop_all"), E._gate_check
    sys.modules["jarvis_stop_all"], E._gate_check = fake, _card
    try:
        got = ask("stop")
    finally:
        if saved_mod is None:
            sys.modules.pop("jarvis_stop_all", None)
        else:
            sys.modules["jarvis_stop_all"] = saved_mod
        E._gate_check = saved_gate
    check("stop: the answer is the stop-everything intent",
          got is not None and got.intent == "stop_all",
          got.intent if got else "model")
    check("stop: it calls the module's own stop_all()",
          calls == ["chat"], calls)
    check("stop: it says what the module said",
          got is not None and "Stopped everything." in got.reply,
          got.reply if got else "")
    check("stop: NO approval card is asked, and the gate is not consulted",
          gate_calls == [], gate_calls)
    check("stop: the intent is not classified read-only (it stops, it does not read)",
          "stop_all" not in Q.READ_ONLY_INTENTS)


def t_stop_says_so_when_the_module_is_absent():
    # `None` in sys.modules is Python's own "this import must fail" marker, so
    # a PC without jarvis_stop_all is simulated even though this folder is on
    # sys.path (popping it would just re-import the real module).
    saved = sys.modules.get("jarvis_stop_all")
    sys.modules["jarvis_stop_all"] = None
    try:
        got = ask("stop")
    finally:
        if saved is None:
            sys.modules.pop("jarvis_stop_all", None)
        else:
            sys.modules["jarvis_stop_all"] = saved
    check("stop: a backend without jarvis_stop_all says nothing was stopped",
          got is not None and got.intent == "stop_all_refused"
          and "nothing was stopped" in got.reply.lower(),
          (got.intent, got.reply) if got else "model")


# --------------------------------------------------------------------------
# 2. "pull request" is a noun, not a clone/push/pull request
# --------------------------------------------------------------------------
PERMITTED = ("show my github pull requests", "show my pull requests",
             "list my open pull requests", "what are my pull requests",
             "show my pull request", "how many pull requests do i have")
REFUSED = ("pull my repository", "clone my repo", "check out my repo",
           "can you clone my repository", "push my code", "pull my repo")


def _never_shape(got) -> bool:
    return bool(got is not None and got.name == "github_connect_receipt"
                and got.f.get("shape") == "never")


def t_pull_requests_are_never_a_code_copy_request():
    for said in PERMITTED:
        got = Q.match(said)
        check(f"github: {said!r} is not the copy refusal", not _never_shape(got),
              got)
        res = ask(said)
        check(f"github: {said!r} never answers the copy refusal",
              res is None or ("never copy a repository"
                              not in str(res.reply).lower()),
              res.reply[:200] if res is not None else "model")
    for said in REFUSED:
        got = Q.match(said)
        check(f"github: {said!r} still gets the refusal", _never_shape(got), got)
        res = ask(said)
        check(f"github: {said!r} says the refusal in words",
              res is not None and "never copy a repository" in res.reply.lower(),
              (res.intent, res.reply[:160]) if res is not None else "model")


# --------------------------------------------------------------------------
# 3. "approve a pull request" is refused, never "Yes."
# --------------------------------------------------------------------------
APPROVE_SENTENCES = ("approve that pull request", "approve the pull request",
                     "approve my pull request", "approve PR 12",
                     "can you approve this pull request")


def t_approving_a_pull_request_is_refused():
    for said in APPROVE_SENTENCES:
        got = Q.match(said)
        check(f"approve: {said!r} is its own refusal shape",
              bool(got is not None and got.name == "github_self"
                   and got.f.get("shape") == "approve"), got)
    res = ask("approve that pull request")
    low = str(res.reply if res is not None else "").lower()
    check("approve: the answer does not begin with Yes",
          res is not None and not low.startswith("yes"), low[:80])
    check("approve: it says Jarvis never approves a pull request",
          "never approve a pull request" in low, low[:200])
    check("approve: it says the APPROVE verdict itself is refused",
          "approve verdict" in low and "permanently banned" in low, low[:300])
    check("approve: it says nothing was approved",
          "nothing was approved" in low, low[-200:])


def t_the_ban_list_carries_approve():
    check("approve: the gate's ban list maps approve_pr to the approve ban",
          JG.BANNED_ACTIONS.get("approve_pr") == "approve"
          and JG.BANNED_ACTIONS.get("approve") == "approve",
          {k: v for k, v in JG.BANNED_ACTIONS.items() if "approve" in k})
    try:
        import jarvis_github as GH
    except Exception:                       # noqa: BLE001 - module absent on an old PC
        skip("approve: jarvis_github's own never set", "module not installed")
    else:
        check("approve: the GitHub module's never set keeps approve_pr",
              "approve_pr" in GH.NEVER, sorted(GH.NEVER))


def t_a_merge_question_still_gets_the_merge_answer():
    res = ask("can you merge a pull request?")
    low = str(res.reply if res is not None else "").lower()
    check("merge: the merge question still says yes, on one card",
          res is not None and low.startswith("yes") and "one approval card" in low
          and "merge commit" in low, low[:200])
    check("merge: a past-tense approval sentence is not the refusal shape",
          not (Q.match("i approved that pull request yesterday") is not None
               and Q.match("i approved that pull request yesterday").f.get("shape")
               == "approve"),
          Q.match("i approved that pull request yesterday"))


def t_an_informational_approval_question_keeps_its_own_path():
    for said in ("how do i approve a pull request",
                 "should i approve this pull request",
                 "which pull request should i approve",
                 "can i approve that pull request"):
        got = Q.match(said)
        check(f"approve: {said!r} is not Jarvis being asked to approve",
              not (got is not None and got.f.get("shape") == "approve"), got)


# --------------------------------------------------------------------------
# 3b. Repository destruction and bulk closing are refused, never "Yes."
# --------------------------------------------------------------------------
DESTROY_SENTENCES = ("delete the repo", "delete this repo",
                     "delete the Epic-Jarvis repository", "remove the repository",
                     "delete my repository", "can you delete the repo",
                     "destroy the repo", "wipe the repository", "drop the repo",
                     "nuke the repository",
                     # The audit's additions (2026-11-16): closing a repository
                     # IS repository destruction, and a pull request has no
                     # delete tool either.
                     "close the repo", "close the repository",
                     "delete the pull request", "delete pr 12")
BULK_CLOSE_SENTENCES = ("close all the pull requests", "close all the issues",
                        "close every pull request", "close all my pull requests",
                        "close both pull requests", "can you close every issue",
                        "delete all the pull requests", "delete every issue")
BULK_CLOSE_BEFORE = ("close pull request 1299", "close the pull request",
                     "close pr 12", "can you close pull request 1299")
#: Reads: an information question never becomes a request to Jarvis.
DESTRUCTION_READS = ("how do i delete a repo", "can a repository be deleted",
                     "what deletes a pull request",
                     "how do i close all the issues", "should i delete my repo")
#: Real deletions that are not a repository, and the two words that only
#: discard the last thing said. None may be swallowed by the new shapes.
OTHER_DELETIONS = ("delete my note called Groceries", "delete the file report.txt",
                   "delete my to-do called milk", "delete the calendar event at 3",
                   "delete that", "forget that")


def _github_shape(got):
    return got.f.get("shape") if got is not None else None


def t_repository_destruction_is_refused():
    for said in DESTROY_SENTENCES:
        got = Q.match(said)
        check(f"destroy: {said!r} is its own refusal shape",
              bool(got is not None and got.name == "github_self"
                   and got.f.get("shape") == "destroy"), got)
        res = ask(said)
        low = str(res.reply if res is not None else "").lower()
        check(f"destroy: {said!r} never opens with Yes",
              res is not None and not low.startswith("yes"), low[:80])


def t_the_destruction_answer_says_what_is_banned():
    res = ask("delete the repo")
    low = str(res.reply if res is not None else "").lower()
    check("destroy: the answer opens with No", low.startswith("no"), low[:80])
    check("destroy: it says Jarvis never deletes a repository",
          "never delete a repository" in low, low[:220])
    check("destroy: it says the ban is permanent",
          "permanently banned" in low, low[:320])
    check("destroy: it says no approval card can lift that ban",
          "no approval card" in low and "lift that ban" in low, low[:320])
    check("destroy: it says nothing was deleted",
          "nothing was deleted" in low, low[-220:])
    check("destroy: the shape is read-only (no card, no write)",
          "github_self" in Q.READ_ONLY_INTENTS)
    try:
        import jarvis_github as GH
    except Exception:                       # noqa: BLE001 - module absent on an old PC
        skip("destroy: jarvis_github's own never set", "module not installed")
    else:
        check("destroy: the module's never set keeps delete_repository",
              "delete_repository" in GH.NEVER, sorted(GH.NEVER))
        check("destroy: the answer cites that never-list by name",
              "own never-list" in low and "delete_repository" in low,
              low[-320:])


def t_the_destruction_refusal_stands_without_the_github_module():
    """The fixed half must not depend on a module it may not have.

    `None` in sys.modules is Python's own "this import must fail" marker, so an
    older PC with no jarvis_github is simulated even though this folder is on
    sys.path. The refusal is still true there - there is no tool to call - and
    it must not cite a never-list it could not read.
    """
    saved = sys.modules.get("jarvis_github")
    sys.modules["jarvis_github"] = None
    try:
        res = ask("delete the repo")
    finally:
        if saved is None:
            sys.modules.pop("jarvis_github", None)
        else:
            sys.modules["jarvis_github"] = saved
    low = str(res.reply if res is not None else "").lower()
    check("destroy: without jarvis_github the fixed refusal still says the ban",
          res is not None and low.startswith("no")
          and "never delete a repository" in low
          and "nothing was deleted" in low, low[:240])
    check("destroy: ... and it does not cite a never-list it cannot read",
          "own never-list" not in low, low[-240:])


def t_bulk_close_is_refused():
    for said in BULK_CLOSE_SENTENCES:
        got = Q.match(said)
        check(f"bulk close: {said!r} is its own refusal shape",
              bool(got is not None and got.name == "github_self"
                   and got.f.get("shape") == "bulk_close"), got)
    res = ask("close all the pull requests")
    low = str(res.reply if res is not None else "").lower()
    check("bulk close: the answer opens with No", low.startswith("no"), low[:80])
    check("bulk close: it says Jarvis never closes or deletes things in bulk",
          "never close or delete things in bulk" in low, low[:220])
    check("bulk close: it says one-at-a-time is a real carded action",
          "closing one issue is a real action with its own approval card" in low,
          low[:420])
    check("bulk close: it does not promise closing a pull request",
          "never close a pull request" in low, low[:520])
    check("bulk close: it says nothing was closed or deleted",
          "nothing was closed or deleted" in low, low[-220:])
    try:
        import jarvis_github as GH
    except Exception:                       # noqa: BLE001 - module absent on an old PC
        skip("bulk close: jarvis_github's own never set", "module not installed")
    else:
        check("bulk close: the module's never set keeps bulk_close",
              "bulk_close" in GH.NEVER, sorted(GH.NEVER))


def t_closing_one_pull_request_is_refused():
    for said in BULK_CLOSE_BEFORE:
        got = Q.match(said)
        check(f"close pr: {said!r} is its own refusal shape",
              bool(got is not None and got.name == "github_self"
                   and got.f.get("shape") == "close_pr"), got)
    res = ask("close pull request 1299")
    low = str(res.reply if res is not None else "").lower()
    check("close pr: the answer opens with No", low.startswith("no"), low[:80])
    check("close pr: it says Jarvis never closes a pull request",
          "never close a pull request" in low, low[:220])
    check("close pr: it says no card offers a close on a pull request",
          "none of my cards offers a close on a pull request" in low,
          low[:440])
    check("close pr: it names the merge as a separate one-card action",
          "merge one pull request with one merge commit" in low, low[:560])
    check("close pr: it says nothing was closed",
          "nothing was closed" in low, low[-220:])


def t_the_destruction_controls_keep_their_own_path():
    for said in DESTRUCTION_READS + OTHER_DELETIONS:
        got = Q.match(said)
        check(f"destroy controls: {said!r} is NOT a destruction refusal",
              _github_shape(got) not in ("destroy", "bulk_close", "close_pr"),
              got)
    # The two deletions that already have a deterministic answer keep it.
    check("destroy controls: deleting a named note keeps its own refusal",
          getattr(Q.match("delete my note called Groceries"), "name", None)
          == "note_change_refused",
          Q.match("delete my note called Groceries"))
    check("destroy controls: 'delete that' keeps the undo path",
          getattr(Q.match("delete that"), "name", None) == "undo",
          Q.match("delete that"))


def t_the_github_controls_keep_their_shapes():
    for said in ("show my github pull requests", "reopen that issue"):
        got = Q.match(said)
        check(f"github controls: {said!r} is NOT a new refusal",
              _github_shape(got) not in ("destroy", "bulk_close", "close_pr"),
              got)
    for said in ("merge a pull request", "can you merge a pull request?"):
        got = Q.match(said)
        check(f"github controls: {said!r} still gets the merge shape",
              _github_shape(got) == "merge", got)
    got = Q.match("approve that pull request")
    check("github controls: 'approve that pull request' still gets approve",
          _github_shape(got) == "approve", got)
    # The brief's own three: no fast-path intent, the model declines in its own
    # words, exactly as measured on the live install.
    for said in ("auto-merge it", "force push to main", "close all"):
        got = Q.match(said)
        check(f"github controls: {said!r} still has NO fast-path intent",
              got is None, got)


def t_the_merge_and_approve_wording_is_unchanged():
    res = ask("merge a pull request")
    merge = str(res.reply if res is not None else "")
    check("kept words: the merge shape still opens 'Yes - with ONE approval "
          "card per merge, and merge commit only.'",
          merge.startswith("Yes - with ONE approval card per merge, and merge "
                           "commit only."), merge[:140])
    res = ask("approve that pull request")
    approve = str(res.reply if res is not None else "")
    check("kept words: the approve shape still opens its own No",
          approve.startswith("No - I never approve a pull request, and asking "
                             "me to cannot change that."), approve[:140])


# --------------------------------------------------------------------------
# 4. "pin a note" asks which note
# --------------------------------------------------------------------------
def t_pin_a_note_asks_which_note():
    reset_vault()
    set_gate(Gate())
    got = Q.match("pin a note")
    check("pin: 'pin a note' is the which-note ask",
          got is not None and got.name == "note_customize_ask"
          and got.f.get("verb") == "pin", got)
    check("pin: it is NOT a customize of a note called 'a'",
          not (got is not None and got.name == "note_customize"
               and str(got.f.get("name") or "").strip().lower() == "a"), got)
    gate = Gate()
    set_gate(gate)
    res = ask("pin a note")
    check("pin: the answer asks which note",
          res is not None and "which note" in res.reply.lower(), res.reply if res else "model")
    check("pin: it names the shape to use",
          res is not None and '"pin my Workout Log note"' in res.reply,
          res.reply if res else "")
    check("pin: nothing was written and no card was asked",
          gate.calls == [] and not list(VAULT.glob("*.md")), gate.calls)
    # A pronoun is NOT a note name and keeps the model: "pin it" about
    # anything else must not become a note question.
    for said in ("pin it", "favourite it"):
        check(f"pin: {said!r} keeps its own path (no note is named)",
              getattr(Q.match(said), "name", None) is None, Q.match(said))
    # The named sentence still works, so the ask did not replace the edit.
    write_note("Workout Log.md", "squats")
    gate = Gate()
    set_gate(gate)
    res = ask("pin my Workout Log note")
    check("pin: 'pin my Workout Log note' still edits the one note",
          res is not None and res.intent == "note_customized"
          and "pinned: true" in read("Workout Log.md")
          and len(gate.calls) == 1,
          (res.intent if res else "model", read("Workout Log.md")))


# --------------------------------------------------------------------------
# 5. Favourite is its own property
# --------------------------------------------------------------------------
def t_favourite_is_its_own_property():
    reset_vault()
    for said in ("favourite my workout log note", "favorite my workout log note"):
        got = Q.match(said)
        check(f"favourite: {said!r} sets the favourite property",
              got is not None and got.name == "note_customize"
              and got.f.get("op") == "set_property"
              and got.f.get("key") == "favorite"
              and str(got.f.get("value")) == "true"
              and got.f.get("name") == "workout log", got)
    for said in ("unfavourite my workout log note", "unfavorite my workout log note"):
        got = Q.match(said)
        check(f"favourite: {said!r} removes the favourite property",
              got is not None and got.name == "note_customize"
              and got.f.get("op") == "remove_property"
              and got.f.get("key") == "favorite", got)
    got = Q.match("pin my workout log note")
    check("favourite: the pin sentence still sets 'pinned', not 'favorite'",
          got is not None and got.name == "note_customize"
          and got.f.get("key") == "pinned", got)


def t_favourite_on_an_existing_note_is_one_card():
    reset_vault()
    set_gate(Gate())
    ask("create a note called Workout Log and add squats")
    check("favourite existing: the note starts with no front matter",
          read("Workout Log.md") == "squats", repr(read("Workout Log.md")))
    gate = Gate()
    set_gate(gate)
    got = ask("favourite my Workout Log note")
    check("favourite existing: the sentence rides the customize door",
          got is not None and got.intent == "note_customized",
          got.intent if got else "model")
    check("favourite existing: exactly ONE edit_vault_note card was asked",
          len(gate.calls) == 1 and gate.calls[0][0] == "edit_vault_note",
          gate.calls)
    text = read("Workout Log.md")
    check("favourite existing: the note has favorite: true and keeps its body",
          "favorite: true" in text and text.endswith("squats"), repr(text))
    check("favourite existing: the pinned property was NOT written too",
          "pinned:" not in text, repr(text))
    check("favourite existing: the reply says it can be undone",
          got is not None and "You can undo it" in got.reply,
          got.reply if got else "")
    # Setting it twice is setting it once: no second card.
    gate2 = Gate()
    set_gate(gate2)
    got = ask("favorite my Workout Log note")
    check("favourite existing: favouriting again asks NO card",
          got is not None and gate2.calls == [] and "favorite: true" in read("Workout Log.md"),
          f"{got.intent if got else 'model'} {gate2.calls}")
    # Remove: one more card, and the note is byte-for-byte what it was.
    gate3 = Gate()
    set_gate(gate3)
    got = ask("unfavourite my Workout Log note")
    check("favourite existing: exactly ONE card is asked to remove it",
          got is not None and len(gate3.calls) == 1, gate3.calls)
    check("favourite existing: the property is gone and the body is as it was",
          read("Workout Log.md") == "squats", repr(read("Workout Log.md")))
    gate4 = Gate()
    set_gate(gate4)
    got = ask("unfavorite my Workout Log note")
    check("favourite existing: removing it when it is not set asks NO card",
          got is not None and gate4.calls == [], got.intent if got else "model")


def t_favourite_can_be_set_on_a_new_note():
    reset_vault()
    gate = Gate()
    set_gate(gate)
    got = ask("make a note called Groceries and favourite it")
    check("favourite create: the title is the note's name and nothing else",
          got is not None and got.intent == "note_created"
          and (VAULT / "Groceries.md").is_file(),
          sorted(p.name for p in VAULT.glob("*.md")))
    check("favourite create: one brand-new note is card-free",
          gate.calls == [], gate.calls)
    text = read("Groceries.md") if (VAULT / "Groceries.md").is_file() else ""
    check("favourite create: the note carries favorite: true",
          "favorite: true" in text and "pinned:" not in text, repr(text))
    check("favourite create: the reply says it is favourited",
          got is not None and "favourited" in got.reply.lower(),
          got.reply if got else "")
    # The British spelling and a pin in the same sentence keep their own keys.
    reset_vault()
    got = ask("make a note called Gym and favourite it and pin it")
    text = read("Gym.md") if (VAULT / "Gym.md").is_file() else ""
    check("favourite create: both properties can be asked for in one sentence",
          got is not None and "favorite: true" in text and "pinned: true" in text,
          repr(text))
    # A body-only create keeps the older words and gains the property.
    reset_vault()
    got = ask("write a note for me about the gym trip, favourite it")
    made = next((p for p in VAULT.glob("*.md")), None)
    check("favourite create: a body-only create can be favourited too",
          got is not None and made is not None
          and "favorite: true" in made.read_text(encoding="utf-8"),
          repr(made.read_text(encoding="utf-8")) if made else "missing")


# --------------------------------------------------------------------------
# 6. The read-back: is it pinned / favourited?
# --------------------------------------------------------------------------
def t_the_flags_are_read_back_from_the_note():
    reset_vault()
    write_note("Workout Log.md", "---\npinned: true\nfavorite: true\n---\nsquats")
    got = Q.match("is my workout log note pinned")
    check("flag: 'is my workout log note pinned' is the read-back",
          got is not None and got.name == "note_flag"
          and got.f.get("flag") == "pinned"
          and got.f.get("name") == "workout log", got)
    got = Q.match("is my workout log note favourited")
    check("flag: 'is my workout log note favourited' is the read-back",
          got is not None and got.name == "note_flag"
          and got.f.get("flag") == "favorite", got)
    gate = Gate()
    set_gate(gate)
    res = ask("is my workout log note pinned")
    check("flag: a pinned note answers Yes, naming the note",
          res is not None and res.intent == "note_flag"
          and res.reply.startswith('Yes - "Workout Log" is pinned'),
          res.reply if res else "model")
    check("flag: the pinned answer offers the unpin sentence",
          res is not None and 'Say "unpin my Workout Log note"' in res.reply,
          res.reply if res else "")
    res = ask("is my workout log note favourited")
    check("flag: a favourited note answers Yes",
          res is not None and res.reply.startswith('Yes - "Workout Log" is favourited'),
          res.reply if res else "model")
    check("flag: NO card and NO write for a read-back",
          gate.calls == [] and read("Workout Log.md").startswith("---\npinned: true"),
          gate.calls)
    # A note with neither property answers No - for both questions.
    reset_vault()
    write_note("Shopping.md", "milk and eggs")
    res = ask("is my shopping note pinned")
    check("flag: a note with no front matter is not pinned",
          res is not None and res.reply.startswith('No - "Shopping" is not pinned'),
          res.reply if res else "model")
    res = ask("is my shopping note favourited")
    check("flag: ... and it is not favourited",
          res is not None and res.reply.startswith('No - "Shopping" is not favourited'),
          res.reply if res else "model")
    # The two properties are SEPARATE: pinned alone is not favourited.
    reset_vault()
    write_note("Workout Log.md", "---\npinned: true\n---\nsquats")
    res = ask("is my workout log note favourited")
    check("flag: pinned is not an alias of favourite",
          res is not None and res.reply.startswith('No - "Workout Log" is not favourited'),
          res.reply if res else "model")
    # A hand-written British property still reads true.
    write_note("Gym.md", "---\nfavourite: true\n---\nlifted")
    res = ask("is my gym note favourite")
    check("flag: a hand-written 'favourite:' property reads true too",
          res is not None and res.reply.startswith('Yes - "Gym" is favourited'),
          res.reply if res else "model")
    # No such note is said plainly, never guessed.
    res = ask("is my tax return note pinned")
    check("flag: an unknown note is named as not found",
          res is not None and "No note in your vault is called" in res.reply,
          res.reply if res else "model")
    # Hidden lists: refused in words, naming no title.
    reset_vault()
    write_note("Workout Log.md", "---\npinned: true\n---\nsquats")
    old = Q._calendar_hidden
    try:
        Q._calendar_hidden = lambda: (True, "Words hidden.")
        res = ask("is my workout log note pinned")
    finally:
        Q._calendar_hidden = old
    check("flag: with lists hidden it names no title",
          res is not None and "Workout Log" not in res.reply,
          res.reply if res else "model")


# --------------------------------------------------------------------------
# 7. The second card is called free only when the free figure supports it
# --------------------------------------------------------------------------
def _how_running_with(free_gb, total_gb=8.0, card_count=2):
    """The real `_how_running_words`, with invented hardware readings."""
    presets = types.ModuleType("jarvis_presets")
    presets.choice = lambda: ""
    rows = [{"name": "NVIDIA GeForce RTX 2080 Super", "total_gb": 8.0,
             "free_gb": 7.9}]
    rows.append({"name": "NVIDIA GeForce RTX 2060", "total_gb": total_gb,
                 "free_gb": free_gb})
    hw = types.ModuleType("jarvis_hardware")
    hw.status = lambda: {"available": True, "cards": rows[:card_count]}
    sc = types.ModuleType("jarvis_second_card")
    sc.FEATURES = ()
    sc._read_switches = lambda: {"features": {}, "combined": False}
    saved = {n: sys.modules.get(n) for n in
             ("jarvis_presets", "jarvis_hardware", "jarvis_second_card")}
    sys.modules.update({"jarvis_presets": presets, "jarvis_hardware": hw,
                        "jarvis_second_card": sc})
    real_model, real_row = Q._model_record, Q._preset_row
    Q._model_record, Q._preset_row = (lambda: ""), (lambda _id: {})
    try:
        return Q._how_running_words()
    finally:
        Q._model_record, Q._preset_row = real_model, real_row
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def t_the_second_card_free_claim_is_derived():
    busy = _how_running_with(1.5, 8.0)
    check("second card: 1.5 of 8.0 GB free is said as busy",
          "second card is busy right now" in busy
          and "1.5 GB of 8.0 GB is free" in busy, busy)
    check("second card: ... and it does NOT say the card is free",
          "free right now" not in busy and "so the second card is free" not in busy,
          busy)
    free = _how_running_with(7.4, 8.0)
    check("second card: a mostly-free card is called free, with its numbers",
          "second card is free right now" in free
          and "7.4 GB of 8.0 GB is free" in free, free)
    unknown = _how_running_with(None, 8.0)
    check("second card: an unreadable free figure is said as unknown",
          "free right now" not in unknown
          and "will not say whether it is free" in unknown, unknown)
    one = _how_running_with(7.4, 8.0, card_count=1)
    check("second card: one card means there is no second card to call free",
          "no second card" in one.lower() and "free right now" not in one, one)
    # The claim is derived, so a full card is busy however the switch says off.
    full = _how_running_with(0.0, 8.0)
    check("second card: a finished reading (0.0 GB free) is busy, not free",
          "busy right now" in full and "0.0 GB of 8.0 GB is free" in full, full)


# --------------------------------------------------------------------------
# The clarification the fast path asks: which note?
# --------------------------------------------------------------------------
def t_the_ambiguous_note_question_is_answerable():
    """2026-11-16: two notes whose titles lowercase to the same string.

    Measured on the live install: "read my workout log note" answered
    '"workout log" matches 2 notes. "Workout Log" (---); "Workout log" (Nov 15).
    Tell me which one to read.' Saying either title back re-asked the identical
    sentence, and the first-line facts selected nothing. The answer now prints
    each note's FOLDER and asks for the folder and the name, which the
    resolver's exact-path tier accepts - so the clarification really selects one
    note.
    """
    reset_vault()
    write_note("Private & Shared/Workout/Workout Log.md", "day one")
    write_note("Notes/Workout log.md", "Nov 15")
    res = ask("read my workout log note")
    reply = str(res.reply if res is not None else "")
    check("which note: the ambiguous read is the read lane's ask",
          res is not None and res.intent == "note_read", res.intent if res else "model")
    check("which note: it says how many notes match",
          "matches 2 notes" in reply, reply[:300])
    check("which note: each candidate carries its FOLDER",
          '"Workout Log" in Private & Shared/Workout' in reply
          and '"Workout log" in Notes' in reply, reply[:400])
    check("which note: it asks for the folder and the name, in the resolver's words",
          reply.endswith("Say the folder and the note's name, so one is chosen."),
          reply[-160:])
    check("which note: the old title-only 'Tell me which one to read' is gone",
          "Tell me which one" not in reply, reply[:400])
    # The sentence it asks for must actually resolve to ONE note.
    res = ask("read my Private & Shared/Workout/Workout Log note")
    reply = str(res.reply if res is not None else "")
    check("which note: naming the folder and the name reads exactly one note",
          res is not None and res.intent == "note_read"
          and '"Workout Log" says' in reply and "day one" in reply,
          reply[:300])


def t_the_flag_read_takes_the_folder_it_was_given():
    """2026-11-17, field-tested: the flag read could not be told WHICH note.

    Measured on the live install (FIELD-TEST-ALL-2026-11-17, Step 4 row 6):
    "is my workout log note pinned" refused with "that name matches 2 notes ...
    so nothing was changed" - false about a read, and it asked for a shape that
    did not reach the matcher - and the sentence its own remedy recommended,
    "is my Workout Log note in Private & Shared/Workout pinned", matched NO
    intent at all, so the 8B model answered that it could not see the notes.

    Two things are proved here: the folder the sentence names is carried into
    the resolver's exact-path tier, and the ambiguity is answered by the READ
    lane's own chooser (folder beside each candidate, the resolver's ask) rather
    than by the write lane's "nothing was changed" sentence.
    """
    reset_vault()
    write_note("Private & Shared/Workout/Workout Log.md",
               "---\npinned: true\n---\nday one")
    write_note("Notes/Workout log.md", "---\npinned: false\n---\nNov 15")
    # The matcher now reaches the folder-qualified sentence at all.
    got = Q.match("is my Workout Log note in Private & Shared/Workout pinned")
    check("flag folder: the folder-qualified sentence is the read-back",
          got is not None and got.name == "note_flag"
          and got.f.get("name") == "Workout Log"
          and got.f.get("folder") == "Private & Shared/Workout", got)
    got = Q.match("is my Workout Log note in Private & Shared/Workout favourited")
    check("flag folder: ... and the favourite spelling carries it too",
          got is not None and got.name == "note_flag"
          and got.f.get("flag") == "favorite"
          and got.f.get("folder") == "Private & Shared/Workout", got)
    # The plain question on the same two notes: the read lane's chooser, in
    # read words, each candidate beside its folder.
    gate = Gate()
    set_gate(gate)
    res = ask("is my workout log note pinned")
    reply = str(res.reply if res is not None else "")
    check("flag folder: an ambiguous flag read says how many notes match",
          res is not None and "matches 2 notes" in reply, reply[:300])
    check("flag folder: ... it lists each candidate's folder",
          '"Workout Log" in Private & Shared/Workout' in reply
          and '"Workout log" in Notes' in reply, reply[:400])
    check("flag folder: ... it never claims something was changed",
          "nothing was changed" not in reply.lower(), reply[:400])
    check("flag folder: ... and it asks in the resolver's own words",
          reply.endswith("Say the folder and the note's name, so one is chosen."),
          reply[-160:])
    # The remedy that answer gives now works, and reads the RIGHT note.
    res = ask("is my Workout Log note in Private & Shared/Workout pinned")
    reply = str(res.reply if res is not None else "")
    check("flag folder: the folder the answer asks for selects one note",
          res is not None and res.intent == "note_flag"
          and reply.startswith('Yes - "Workout Log" is pinned'), reply[:200])
    check("flag folder: still no card and no write",
          gate.calls == []
          and read("Private & Shared/Workout/Workout Log.md")
          .startswith("---\npinned: true"), gate.calls)


# --------------------------------------------------------------------------
# The records: jarvis_quick.py and its published twin
# --------------------------------------------------------------------------
def t_the_twin_is_byte_identical():
    a, b = HERE / "jarvis_quick.py", REPO / "jarvis-backend" / "jarvis_quick.py"
    check("records: jarvis_quick.py has a byte-identical published twin",
          a.is_file() and b.is_file()
          and a.read_bytes().replace(b"\r\n", b"\n")
          == b.read_bytes().replace(b"\r\n", b"\n"),
          f"{a} vs {b}")


TESTS = [
    t_stop_is_one_deterministic_intent,
    t_stop_calls_stop_all_and_asks_no_card,
    t_stop_says_so_when_the_module_is_absent,
    t_pull_requests_are_never_a_code_copy_request,
    t_approving_a_pull_request_is_refused,
    t_the_ban_list_carries_approve,
    t_a_merge_question_still_gets_the_merge_answer,
    t_an_informational_approval_question_keeps_its_own_path,
    t_repository_destruction_is_refused,
    t_the_destruction_answer_says_what_is_banned,
    t_the_destruction_refusal_stands_without_the_github_module,
    t_bulk_close_is_refused,
    t_closing_one_pull_request_is_refused,
    t_the_destruction_controls_keep_their_own_path,
    t_the_github_controls_keep_their_shapes,
    t_the_merge_and_approve_wording_is_unchanged,
    t_pin_a_note_asks_which_note,
    t_favourite_is_its_own_property,
    t_favourite_on_an_existing_note_is_one_card,
    t_favourite_can_be_set_on_a_new_note,
    t_the_flags_are_read_back_from_the_note,
    t_the_ambiguous_note_question_is_answerable,
    t_the_flag_read_takes_the_folder_it_was_given,
    t_the_second_card_free_claim_is_derived,
    t_the_twin_is_byte_identical,
]


def main():
    print("=" * 74)
    print("jarvis_quick - seven measured wrong answers on the chat fast path")
    print("=" * 74)
    for test in TESTS:
        print()
        print("--", test.__name__, "-" * max(0, 60 - len(test.__name__)))
        try:
            test()
        except Exception:                                   # noqa: BLE001
            FAILED.append(test.__name__ + " (exception)")
            import traceback
            traceback.print_exc()
    print()
    print("=" * 74)
    print(f"PASS {len(PASSED)}  FAIL {len(FAILED)}  SKIP {len(SKIPPED)}")
    for name in FAILED:
        print("  FAIL:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
