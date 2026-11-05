"""test_approval_policy.py - changing what needs a card, a second yes or
Windows Hello by talking to Jarvis (jarvis_approval_policy.py; the owner's
ask of 2026-11-05).

    python3 backend/test_approval_policy.py

Runs anywhere; no model, no Windows Hello child, no network. What it proves:

1. The three things default to the shipped answer (one yes, no extra check),
   and a line that cannot be read counts as the STRICTER answer, always.
2. MORE asking - a card where there was none, a second yes, Windows Hello -
   is instant, raises no card, and calls nobody.
3. LESS asking is refused from another device, without the PC's own Windows
   Hello check, and when the card that would ask less is not set to ask; and
   otherwise it raises ONE card whose words name the action in the owner's
   words and no file the gate protects. Only a person's "approved" writes.
4. An unknown action is refused before any card, in one sentence that names
   the nearest real actions - and the same answer is a read, never a change.
5. One action and one thing at a time: a body naming a second dimension is
   refused before anything is read or raised.
6. The writer changes ONE line - or adds one, or removes one - and keeps
   every other byte (comments, CRLF, a byte-order mark). An unusual file is
   refused, and nothing is written.
7. The second confirmation is REAL: the first yes approves nothing (no stamp,
   so the gate still waits), and only the second yes stamps it.
8. Windows Hello is REAL for the action the owner set it on: refused from the
   phone, asked on the PC even for a card that would otherwise be "small",
   and a cancelled prompt approves nothing.
9. The card action itself always asks (PC_ONLY_ACTIONS, HARD_LIMITS,
   MUST_ASK), so "stop asking" can never be switched off.
10. The page reads it (a row's own note field, both apps, no new control),
    the model has ONE tool for it, and the shipped settings file knows both
    the card's action and the tool.
"""
from __future__ import annotations

import ast
import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_approval_policy.py", "jarvis_asks_first.py",
                "jarvis_owner_check.py", "jarvis_agent.py", "jarvis_card_words.py")
sys.path.append(str(HERE / "rebuilt"))
import jarvis_agent as AG  # noqa: E402
import jarvis_approval_policy as AP  # noqa: E402
import jarvis_asks_first as AF  # noqa: E402
import jarvis_card_words as W  # noqa: E402
import jarvis_owner_check as OC  # noqa: E402

FAILED, PASSED = [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-approval-policy-"))
CFG = TMP / "jarvis-framework.toml"
SAMPLE = (
    "\ufeff# my settings\r\n"
    "[autonomy]\r\n"
    "unknown_action_tier = \"ask\"\r\n"
    "\r\n"
    "[autonomy.tiers]\r\n"
    "send_email                = \"ask\"   # I like this one\r\n"
    "email_read                = \"auto\"\r\n"
    "\r\n"
    "[self_modification]\r\n"
    "enabled = true\r\n"
)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _parsed(text):
    import tomllib
    return tomllib.loads(text.lstrip("\ufeff"))


#: The test's own settings file: the real writer writes it, and every read
#: parses it again - so a change has to survive a round trip to be seen.
def _section(name):
    import tomllib
    try:
        doc = tomllib.loads(CFG.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    got = doc.get("autonomy", {}).get(name, {})
    return got if isinstance(got, dict) else {}


AP._config_path = lambda: CFG
AP._section = _section
AP.fw = None                     # no audit log, no framework module needed
AP._reload = lambda: None


class Verdict:
    def __init__(self, allowed=True, tier="ask", outcome="approved", reason=""):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.reason = reason


class Writer:
    def __init__(self):
        self.calls = []

    def __call__(self, action, field, value):
        self.calls.append((action, field, value))
        return {"ok": True, "changed": True}


class Gate:
    def __init__(self, verdict=None):
        self.calls = []
        self.verdict = verdict or Verdict()

    def __call__(self, action, detail, prompt):
        self.calls.append({"action": action, "detail": detail, "prompt": prompt})
        return self.verdict


def _reset():
    AP._reset_for_tests()
    CFG.write_text(SAMPLE, encoding="utf-8", newline="")


def _with_policy(*, confirmations=None, hello=None):
    """The file, with send_email already made stricter - what a loosening has
    to remove, or it would be "already so" and raise no card."""
    extra = ""
    if confirmations is not None:
        extra += f"\n[autonomy.confirmations]\nsend_email = {confirmations}\n"
    if hello is not None:
        extra += f"\n[autonomy.windows_hello]\nsend_email = {'true' if hello else 'false'}\n"
    CFG.write_text(SAMPLE + extra, encoding="utf-8", newline="")
    AP._reset_for_tests()


def _change(body, *, gate=None, here=True, armed=True, writer=None, tier="ask"):
    gate = gate or Gate()
    writer = writer or Writer()
    code, out = AP.request_change(body, gate=gate, tier_of=lambda a: tier,
                                  spawn=lambda fn: fn(), write=writer,
                                  armed=lambda: armed, here=here)
    return code, out, gate, writer


# ================================================ 1. the defaults, read strictly

def t_the_three_things_default_to_the_shipped_answer():
    _reset()
    AP._section = lambda name: {}
    try:
        check("no lines: one yes, no Windows Hello",
              AP.approval_needs("send_email") == {"confirmations": 1,
                                                  "windows_hello": False})
    finally:
        AP._section = _section
    _reset()
    CFG.write_text(SAMPLE + "\n[autonomy.confirmations]\n"
                            "send_email = \"two\"\n", encoding="utf-8", newline="")
    check("a line that cannot be read as 2 counts as 2 (fails closed)",
          AP.approval_needs("send_email")["confirmations"] == 2,
          AP.approval_needs("send_email"))
    CFG.write_text(SAMPLE + "\n[autonomy.windows_hello]\n"
                            "send_email = \"of course\"\n", encoding="utf-8", newline="")
    check("a Windows Hello line that cannot be read counts as REQUIRED",
          AP.approval_needs("send_email")["windows_hello"] is True)
    CFG.write_text(SAMPLE + "\n[autonomy.confirmations]\nsend_email = 2\n"
                            "[autonomy.windows_hello]\nsend_email = false\n",
                   encoding="utf-8", newline="")
    check("a real 2 and a real false are read exactly",
          AP.approval_needs("send_email") == {"confirmations": 2,
                                              "windows_hello": False})


# ======================================== 2. more asking is instant and cardless

def t_more_asking_is_instant_and_cardless():
    _reset()
    gate = Gate()
    code, out, gate, writer = _change(
        {"action": "send_email", "field": "confirmations", "value": "2"}, gate=gate)
    check("a second yes: 200 at once, changed", code == 200 and out.get("changed"), out)
    check("... and it is written", writer.calls == [("send_email", "confirmations", 2)],
          writer.calls)
    check("... no card was raised, and the gate was not called",
          gate.calls == [] and out.get("waiting") is not True)
    code, out, gate, writer = _change(
        {"action": "send_email", "field": "windows_hello", "value": "true"}, gate=gate)
    check("Windows Hello: 200 at once, written",
          code == 200 and writer.calls == [("send_email", "windows_hello", True)],
          (code, writer.calls))
    check("... no card either", gate.calls == [])
    CFG.write_text(SAMPLE + "\n[autonomy.windows_hello]\nsend_email = true\n",
                   encoding="utf-8", newline="")
    gate, writer = Gate(), Writer()
    code, out = AP.request_change(
        {"action": "send_email", "field": "windows_hello", "value": "true"},
        gate=gate, tier_of=lambda a: "ask", spawn=lambda fn: fn(),
        write=writer, armed=lambda: True, here=True)
    check("asked again for something already so: no write, no card",
          code == 200 and out.get("changed") is False
          and writer.calls == [] and gate.calls == [], (code, out, writer.calls))


# ==================================== 3. less asking: the PC, one card, Hello

def t_less_asking_needs_the_pc_and_a_hello_card():
    _with_policy(confirmations=2, hello=True)
    code, out, gate, writer = _change(
        {"action": "send_email", "field": "windows_hello", "value": "false"},
        here=False)
    check("from another device: 403 pc_only, no card, nothing written",
          code == 403 and out.get("pc_only") is True and gate.calls == []
          and writer.calls == [], (code, out))
    code, out, gate, writer = _change(
        {"action": "send_email", "field": "windows_hello", "value": "false"},
        armed=False)
    check("without the PC's own Windows Hello check: 503, no card",
          code == 503 and gate.calls == [], (code, out))
    code, out, gate, writer = _change(
        {"action": "send_email", "field": "windows_hello", "value": "false"},
        tier="auto")
    check("when the card itself is not set to ask: 503, no card",
          code == 503 and gate.calls == [], (code, out))
    code, out, gate, writer = _change(
        {"action": "send_email", "field": "confirmations", "value": "1"})
    check("otherwise ONE card, action change_approval_policy, 202",
          code == 202 and out.get("waiting") is True
          and len(gate.calls) == 1 and gate.calls[0]["action"] == AP.ACTION,
          (code, out, gate.calls))
    prompt = gate.calls[0]["prompt"]
    check("the card names the action in the owner's words",
          W.TITLES["send_email"].lower() in prompt.lower(), prompt)
    check("the card says exactly what stops being asked",
          "second confirmation" in prompt.lower(), prompt)
    check("the card is one of the PC-only, Windows Hello cards",
          AP.ACTION in OC.PC_ONLY_ACTIONS)
    check("... and the gate was handed the detail beside it",
          isinstance(gate.calls[0]["detail"], dict)
          and gate.calls[0]["detail"].get("setting") == "send_email")
    # Nothing is written while the card WAITS: spawn is not run at all here.
    _with_policy(confirmations=2)
    gate, writer, waiting = Gate(), Writer(), []
    code, out = AP.request_change(
        {"action": "send_email", "field": "confirmations", "value": "1"},
        gate=gate, tier_of=lambda a: "ask", spawn=lambda fn: waiting.append(fn),
        write=writer, armed=lambda: True, here=True)
    check("a waiting card writes nothing, and one is waiting",
          code == 202 and out.get("waiting") is True
          and writer.calls == [] and len(waiting) == 1, (code, writer.calls))
    check("only one loosening card can wait at a time",
          AP.request_change({"action": "send_email", "field": "confirmations",
                             "value": "1"}, gate=gate, tier_of=lambda a: "ask",
                            spawn=lambda fn: waiting.append(fn), write=writer,
                            armed=lambda: True, here=True)[0] == 409)


def t_only_a_persons_yes_writes_it():
    for outcome, want in (("denied", 0), ("timed_out", 0), ("refused", 0),
                          ("approved", 1)):
        _with_policy(confirmations=2)
        verdict = Verdict(allowed=(outcome == "approved"), outcome=outcome)
        gate = Gate(verdict)
        writer = Writer()
        code, out, gate, writer = _change(
            {"action": "send_email", "field": "confirmations", "value": "1"},
            gate=gate, writer=writer)
        note = ("wrote it" if want else "wrote nothing")
        check(f"a card answered {outcome!r}: {note}",
              len(writer.calls) == want, (outcome, writer.calls))
        if want:
            check("... and the last words say so",
                  "changed" in (AP.last() or {}).get("message", ""), AP.last())


# =========================================== 4. an unknown action, before a card

def t_unknown_action_is_refused_before_any_card():
    _reset()
    code, out, gate, writer = _change(
        {"action": "the door", "field": "windows_hello", "value": "true"})
    check("409 before any card, nothing written, the gate not called",
          code == 409 and gate.calls == [] and writer.calls == [], (code, out))
    check("one sentence naming the nearest real action in plain words",
          "nearest" in out.get("error", "").lower()
          and W.TITLES["home_control"].lower() in out["error"].lower(),
          out.get("error"))
    check("the real name is in the data, not the prose (a model can read it)",
          out.get("nearest") == ["home_control"], out.get("nearest"))
    code, out = AP.read_request({"action": "the door"})
    check("a read of an unknown action changes nothing and says the same",
          code == 200 and out.get("known") is False and out.get("nearest") == ["home_control"])
    code, out, gate, writer = _change(
        {"action": "send an email", "field": "confirmations", "value": "2"})
    check("the card's own words resolve to the one real action",
          code == 200 and writer.calls == [("send_email", "confirmations", 2)],
          (code, writer.calls))


# ================================== 5. one action and one thing, never in bulk

def t_one_action_one_thing_and_nothing_in_bulk():
    _reset()
    gate = Gate()
    code, out, gate, writer = _change(
        {"action": "send_email", "field": "confirmations", "value": "2",
         "windows_hello": True}, gate=gate)
    check("a second dimension in one body: 400, nothing read or raised",
          code == 400 and out.get("one_at_a_time") is True
          and gate.calls == [] and writer.calls == [], (code, out))
    check("no field: 400",
          _change({"action": "send_email"})[0] == 400)
    check("a value outside the three: 400",
          _change({"action": "send_email", "field": "card", "value": "maybe"})[0] == 400)
    check("two yeses is only ever 1 or 2",
          _change({"action": "send_email", "field": "confirmations",
                   "value": "3"})[0] == 400)


# ==================================================== 6. the writer, one line

def t_the_writer_changes_one_line_and_nothing_else():
    body = SAMPLE.lstrip("\ufeff")     # set_policy strips a BOM before this
    out = AP.rewrite_policy(body, "confirmations", "send_email", 2)
    check("CRLF line endings are kept", "\r\n" in out)
    check("the line is added under its own table",
          "send_email = 2" in out and "[autonomy.confirmations]" in out)
    added = out.split("\r\n")
    inserted = [ln for ln in added if ln.startswith("send_email = 2")]
    without = [ln for ln in added if not ln.startswith("send_email = 2")
               and ln != "[autonomy.confirmations]"]
    before = [ln for ln in body.split("\r\n") if ln]
    check("exactly one line is added, plus its table's header, and no other "
          "line changes",
          len(inserted) == 1 and [ln for ln in without if ln] == before,
          (inserted, [ln for ln in without if ln][:6], before[:6]))
    check("removing it takes the line away",
          "send_email = 2" not in AP.rewrite_policy(out, "confirmations",
                                                    "send_email", None))
    check("... and the file still parses with the one table",
          _parsed(out)["autonomy"]["confirmations"] == {"send_email": 2})
    check("the tier table is untouched",
          _parsed(out)["autonomy"]["tiers"] == _parsed(body)["autonomy"]["tiers"])
    # The file itself, through set_policy: the byte-order mark and the line
    # endings are the file's, not the writer's.
    _reset()
    AP.set_policy("send_email", "confirmations", 2)
    raw = CFG.read_bytes()
    check("set_policy keeps the byte-order mark", raw.startswith(b"\xef\xbb\xbf"))
    check("set_policy keeps CRLF", b"\r\n" in raw)
    AP.set_policy("send_email", "confirmations", None)
    check("set_policy removes the line again",
          b"send_email = 2" not in CFG.read_bytes())
    weird = body.replace("[autonomy.tiers]", "[autonomy.tiers]\nsend_email = 2")
    try:
        AP.rewrite_policy(weird, "tiers", "send_email", 2)
        check("a table the writer does not own is refused", False)
    except AP.PolicyError:
        check("a table the writer does not own is refused", True)
    twice = body + "\n[autonomy.confirmations]\nsend_email = 2\n"
    try:
        AP.rewrite_policy(twice + "send_email = 2\n", "confirmations",
                          "send_email", 1)
        check("the same line twice is refused", False)
    except AP.PolicyError:
        check("the same line twice is refused", True)


# ============================== 7. the second confirmation is really enforced

def _row(action, *, risk=None):
    return {"id": "r-" + action, "action": action, "expires_in": 100,
            "risk": risk or {"classified": True, "reach": "local",
                             "reversible": "yes", "why": "a test"}}


def t_second_confirmation_really_needs_a_second_yes():
    keep = AP.approval_needs
    AP.approval_needs = lambda action: (
        {"confirmations": 2, "windows_hello": False}
        if action == "send_email" else {"confirmations": 1, "windows_hello": False})
    asked = []
    OC.set_verifier(lambda m, t: (asked.append(m), OC.CONFIRMED)[1])
    try:
        row = _row("send_email")
        first = OC.approve_check({"id": row["id"]}, peer="127.0.0.1",
                                 pending=lambda: [row])
        check("the first yes: 202, and it says nothing is approved yet",
              first is not None and first[0] == 202
              and first[1].get("first_yes") is True, first)
        check("... and it stamped NOTHING, so the gate still waits",
              OC.take_stamp(row["id"], "send_email") is False)
        second = OC.approve_check({"id": row["id"]}, peer="127.0.0.1",
                                  pending=lambda: [row])
        check("the second yes: allowed through", second is None, second)
        check("... and it stamped the approval the gate believes",
              OC.take_stamp(row["id"], "send_email") is True)
        check("the phone cannot answer a two-yes card",
              OC.approve_check({"id": row["id"]}, peer="100.64.0.9",
                               local="100.64.0.2", pending=lambda: [row],
                               own=["100.64.0.2"])[0] == 403)
    finally:
        OC.set_verifier(None)
        AP.approval_needs = keep


# ================================== 8. Windows Hello is really demanded for it

def t_windows_hello_is_really_demanded_for_that_action():
    keep = AP.approval_needs
    AP.approval_needs = lambda action: (
        {"confirmations": 1, "windows_hello": True}
        if action == "send_email" else {"confirmations": 1, "windows_hello": False})
    asked = []
    OC.set_verifier(lambda m, t: (asked.append(m), OC.CONFIRMED)[1])
    try:
        row = _row("send_email")
        got = OC.approve_check({"id": row["id"]}, peer="100.64.0.9",
                               local="100.64.0.2", pending=lambda: [row],
                               own=["100.64.0.2"])
        check("from the phone: 403 pc_only, and no prompt", got[0] == 403 and asked == [],
              (got, asked))
        check("from this PC: allowed, and Windows Hello was really asked",
              OC.approve_check({"id": row["id"]}, peer="127.0.0.1",
                               pending=lambda: [row]) is None and len(asked) == 1,
              asked)
        OC.set_verifier(lambda m, t: OC.CANCELLED_)
        check("a cancelled prompt approves nothing",
              OC.approve_check({"id": row["id"]}, peer="127.0.0.1",
                               pending=lambda: [row])[0] == 403)
        # a card that is otherwise "small" no longer skips the check
        small = next(iter(OC.SMALL_ACTIONS))
        keep_small = AP.approval_needs
        AP.approval_needs = lambda action: {"confirmations": 1,
                                            "windows_hello": True}
        n = len(asked)
        OC.set_verifier(lambda m, t: (asked.append(m), OC.CONFIRMED)[1])
        small_row = _row(small)
        got = OC.approve_check({"id": small_row["id"]}, peer="127.0.0.1",
                               pending=lambda: [small_row])
        check("a small card the owner made stricter still asks Windows Hello",
              got is None and len(asked) == n + 1, (got, len(asked) - n))
        AP.approval_needs = keep_small
    finally:
        OC.set_verifier(None)
        AP.approval_needs = keep


# =========================== 9. the card that asks less always asks itself

def t_the_action_that_can_loosen_always_asks():
    check("change_approval_policy is a PC-only card", AP.ACTION in OC.PC_ONLY_ACTIONS)
    check("... and can never be loosened by an app switch",
          AP.ACTION in AF.HARD_LIMITS and AP.ACTION in AF.MUST_ASK)
    shipped = (REPO / "jarvis-backend" / "jarvis-framework.toml").read_text(
        encoding="utf-8-sig")
    check("... the shipped settings file sets it to ask",
          f'{AP.ACTION}    = "ask"' in shipped)


# ============================== 10. the page, the model tool, the shipped file

def t_the_page_shows_it_read_only():
    _reset()
    CFG.write_text(SAMPLE + "\n[autonomy.confirmations]\nsend_email = 2\n"
                            "[autonomy.windows_hello]\nsend_email = true\n",
                   encoding="utf-8", newline="")
    row = {"action": "send_email", "title": "Send an email", "note": "a note"}
    AP.decorate(row)
    check("a row carries the two extra answers",
          row["confirmations"] == 2 and row["windows_hello"] is True, row)
    check("... and says them in its own note field (both apps draw that)",
          "asks you twice" in row["note"] and "Windows Hello" in row["note"], row)
    check("no write control is added: the row is the same dict plus fields",
          set(row) == {"action", "title", "note", "confirmations", "windows_hello"})
    check("the module exposes no route and no installer",
          not hasattr(AP, "install") and not hasattr(AP, "handle_post"))


def t_the_model_has_one_tool_for_it():
    check("the tool exists", "approval_policy" in AG.TOOLS)
    tool = AG.TOOLS["approval_policy"]
    props = tool.parameters["properties"]
    check("it names the one action, the one thing, and the new value",
          set(props) == {"action", "field", "value"}, set(props))
    check("only the three dimensions can be named",
          props["field"]["enum"] == ["card", "confirmations", "windows_hello"])
    check("the description does not claim a loosening is done",
          "never done" in tool.description.lower(), tool.description)
    check("the tool is never a plan step", "approval_policy" in AG._PLAN_EXCLUDED_STEPS)
    check("reaching the generic path changes nothing",
          AG._run_approval_policy({}).get("changed") is False)
    check("... and its prepare is a normal prepare (the call path is the door)",
          AG._prepare_approval_policy({})[0] is None)


def t_the_shipped_settings_file_knows_it():
    shipped = (REPO / "jarvis-backend" / "jarvis-framework.toml").read_text(
        encoding="utf-8-sig")
    check("the shipped file offers the tool to the model",
          '"approval_policy"' in shipped)
    check("its card's own action is a tier of its own, set to ask",
          f'{AP.ACTION}    = "ask"' in shipped)
    check("the two extra tables ship empty",
          "[autonomy.confirmations]" in shipped
          and "[autonomy.windows_hello]" in shipped)
    check("the card words know it",
          W.has_written_title(AP.ACTION))
    row = AF._row(AP.ACTION, here=True)
    check("the page can draw it as an action that always asks",
          row.get("fixed") is False and row.get("says") == AF.SAYS["ask"], row)


#: The files the gate refuses to let anything modify. Read from the published
#: copy with `ast`, never imported and never hand-copied (test_asks_first.py's
#: own pattern): the card text is handed to the gate as its `prompt`, and a
#: prompt that names one is refused at "never", so no card is ever raised.
def _protected_names() -> set:
    src = (REPO / "jarvis-backend" / "jarvis_gate.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_PROTECTED"
                for t in node.targets):
            return set(ast.literal_eval(node.value))
    return set()


def t_the_card_never_names_a_protected_file():
    names = _protected_names()
    check("the gate's protected list could be read", bool(names))
    _with_policy(confirmations=2)
    gate = Gate()
    code, out, gate, writer = _change(
        {"action": "send_email", "field": "confirmations", "value": "1"},
        gate=gate)
    prompt = gate.calls[0]["prompt"] if gate.calls else ""
    detail = json.dumps(gate.calls[0]["detail"]) if gate.calls else ""
    check("the loosening card reached the gate", code == 202 and bool(prompt),
          (code, out))
    check("... and names no file the gate protects",
          not [n for n in names if n.lower() in (prompt + detail).lower()],
          [n for n in names if n.lower() in (prompt + detail).lower()])




def t_the_card_floor_refuses_a_must_ask_action():
    """The card dimension's floor is the existing one: a MUST_ASK/HARD_LIMITS
    action can never lose its card (jarvis_asks_first.request_tier refuses it),
    so this feature can never be used to make those cardless."""
    _reset()
    check("send_email is in both lists that cannot lose a card",
          "send_email" in AF.MUST_ASK and "send_email" in AF.HARD_LIMITS)
    gate, writer = Gate(), Writer()
    code, out = AP.request_change(
        {"action": "send_email", "field": "card", "value": "auto"},
        gate=gate, tier_of=lambda a: "ask", spawn=lambda fn: fn(),
        write=writer, armed=lambda: True, here=True)
    check("asking to remove its card is refused before any card is raised",
          code != 202 and bool(out.get("error"))
          and not gate.calls and not writer.calls, (code, out))
    check("... and the refusal is one sentence, in plain words",
          len(str(out.get("error") or "")) > 40, out)

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
