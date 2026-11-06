"""test_phone_app_allowlist.py: adding and removing a phone app, card first.

The owner asked (2026-11-02, their words): "any apps that i ask if to open or do
something with. i would need to approve a card with the apps i would like it to
manipulate first and i can remove or add any android app to that list any time
with an approval card... or by going to the settings and changing it there too."
PR #1067 added `[phone_apps]` (friendly name -> package) and it ships EMPTY, so
until this module existed the only way to fill it was to hand-edit
`jarvis-framework.toml`. This suite proves the management:

  * NOTHING is written without a card. A denied card, and a call refused before
    a card exists, both leave the file's bytes exactly as they were.
  * An APPROVED add writes exactly ONE line, and the real phone tool then opens
    (and searches in) that app - the reader in jarvis_android_control.py, not a
    stand-in.
  * An APPROVED remove takes that line out again and the app stops opening.
  * A REJECTED remove changes nothing: the app is still allowed afterwards.
  * The CARD names both the friendly name and the exact package id, for an add
    and for a remove, under the existing `change_own_config` action.
  * NO BULK: one name and one package, a list where a string belongs is
    refused before any card, and the tool's schema has no array for apps.
  * An applied add and an applied remove each write ONE audit line.
  * The new tool action maps to a REAL gate action (`change_own_config`, the
    same one `connect_account` maps to) and the mapping is load-bearing: the
    tool's own name is NOT a `_TOOL_ACTIONS` key, so without the mapping the
    gate would answer `unclassified_tool`. Pre-fix this suite fails because
    `phone_apps` is not in `jarvis_agent.TOOLS` at all.

    python -B backend/test_phone_app_allowlist.py
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE / "rebuilt"))

TMP = Path(tempfile.mkdtemp(prefix="jarvis-phone-apps-"))
SHIPPED_TOML = HERE / "rebuilt" / "jarvis-framework.toml"
BASE_TOML = REPO / "jarvis-backend" / "jarvis-framework.toml"
GATE_BASE = REPO / "jarvis-backend" / "jarvis_gate.py"
API_DOC = REPO / "docs" / "JARVIS-API.md"

#: A settings file with the two tables the write path needs, and an EMPTY
#: [phone_apps], so "the list starts empty" is a fact of the fixture and not of
#: whatever this PC happens to hold. The writer must work on the owner's real
#: file too, so `t_the_owners_own_shape_is_left_alone` uses the shipped one.
MINIMAL = """# a fixture, not the owner's file
[tools]
enabled = ["web_search", "change_setting"]

[autonomy.tiers]
change_own_config = "ask"

[phone_apps]
"""
TOML = TMP / "jarvis-framework.toml"
TOML.write_text(MINIMAL, encoding="utf-8")
# Both config variables, before the framework is imported: the module must read
# the temp file and write it, never a copy beside the modules.
os.environ["JARVIS_FRAMEWORK_TOML"] = str(TOML)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_LOG_DIR"] = str(TMP / "logs")

import jarvis_framework as FW  # noqa: E402
import jarvis_phone_apps as PA  # noqa: E402
import jarvis_android_control as A  # noqa: E402
import jarvis_agent as AG  # noqa: E402

try:
    import tomllib
except ModuleNotFoundError:                      # Python < 3.11
    try:
        import tomli as tomllib                  # type: ignore
    except ModuleNotFoundError:
        tomllib = None

FAILED, PASSED, SKIPPED = [], [], []
PKG = "com.google.android.apps.youtube.music"
NAME = "YouTube Music"

GATE = str(GATE_BASE)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, its own count, never
    a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


class Verdict:
    """What a jarvis_gate verdict looks like to this module and to _one_call."""

    def __init__(self, allowed=True, tier="ask", action="change_own_config",
                 outcome="approved", reason=""):
        self.allowed, self.tier, self.action = allowed, tier, action
        self.outcome, self.reason = outcome, reason
        self.request_id = "req-1"


def fresh(text=MINIMAL):
    """Write the temp settings file, reload the framework, and point the writer
    at it. Returns the file's path.

    The audit folder is cleared too, so "no line was written" is a fact of THIS
    test and not of an earlier one in the same process."""
    TOML.write_text(text, encoding="utf-8")
    shutil.rmtree(TMP / "logs", ignore_errors=True)
    FW.reload_framework()
    PA.configure(path=TOML)
    return TOML


def with_gate(verdict, calls):
    """Install a gate stub that records every card it is asked for."""
    def gate(action, detail, prompt):
        calls.append({"action": action, "detail": detail, "prompt": prompt})
        return verdict

    PA.configure(path=TOML, gate=gate, tier_of=lambda action: "ask")
    return calls


def audit_lines():
    """Every audit line written under the temp log folder, as dicts."""
    out = []
    folder = TMP / "logs"
    if not folder.is_dir():
        return out
    for p in sorted(folder.glob("*")):
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    out.append(json.loads(line))
        except Exception:
            continue
    return out


def audit_events():
    return [row.get("event") for row in audit_lines()]


def changed_lines(before: str, after: str) -> list:
    """The line numbers whose text differs, as lists of strings."""
    b, a = before.splitlines(), after.splitlines()
    return [(i, x, y) for i, (x, y) in enumerate(zip(b, a), start=1) if x != y]


def plan(action_request):
    return A.plan("EMULATOR123", "the owner's words", [action_request])


# --------------------------------------------------------------------------
#   1. The honest empty state
# --------------------------------------------------------------------------
def t_an_empty_list_is_honest_and_opens_nothing():
    fresh()
    view = PA.view()
    check("an empty [phone_apps] is drawn as empty, not as unavailable",
          view.get("available") is True and view.get("empty") is True
          and view.get("apps") == [] and view.get("count") == 0, view)
    check("... and says in plain words that nothing is allowed",
          "No apps are allowed yet" in str(view.get("note")), view.get("note"))
    check("the phone tool reads the same empty list", A.phone_apps() == {})
    p = plan({"action": "open_app", "app": NAME})
    check("so opening an app is refused, in the owner's words",
          p.steps == [] and "no apps are allowed" in
          str(p.rejected[0].get("reason")).lower(), repr(p.rejected))


# --------------------------------------------------------------------------
#   2. Card first: nothing is written without it
# --------------------------------------------------------------------------
def t_a_denied_card_writes_nothing():
    fresh()
    before = TOML.read_bytes()
    calls = []
    with_gate(Verdict(allowed=False, outcome="denied", reason="not now"), calls)
    code, out = PA.change({"action": "add", "name": NAME, "package": PKG})
    check("a denied card answers 409 and says so", code == 409
          and out.get("ok") is False and out.get("changed") is False, (code, out))
    check("... naming the owner's refusal, not a traceback",
          "You said no" in str(out.get("error")), out)
    check("the settings file is byte-for-byte unchanged",
          TOML.read_bytes() == before)
    check("exactly ONE card was asked for", len(calls) == 1, calls)
    check("... under the existing change_own_config action",
          calls and calls[0]["action"] == "change_own_config", calls)
    check("... and it named the package being added",
          calls and calls[0]["detail"].get("package") == PKG, calls)
    check("nothing was written to the audit log", audit_events() == [], audit_events())
    check("the list is still empty where the phone tool reads it", A.phone_apps() == {})


def t_a_bad_request_is_refused_before_a_card_exists():
    fresh()
    before = TOML.read_bytes()
    calls = []
    with_gate(Verdict(), calls)
    bad = [
        ("com.jarvis. itself", {"action": "add", "name": "Jarvis",
                                "package": "com.jarvis.client"}),
        ("a package that is not a package", {"action": "add", "name": "TikTok",
                                             "package": "tiktok; rm -rf /"}),
        ("an empty name", {"action": "add", "name": "", "package": PKG}),
        ("a name that is not one line", {"action": "add", "name": "a\nb",
                                         "package": PKG}),
        ("removing an app that is not listed", {"action": "remove",
                                                "name": "TikTok"}),
        ("an action that is neither add nor remove", {"action": "bulk",
                                                      "name": NAME}),
    ]
    for label, body in bad:
        code, out = PA.change(body)
        check(f"{label}: refused with 400 and nothing changed",
              code == 400 and out.get("changed") is False, (label, code, out))
    check("not one of those six raised a card", calls == [], calls)
    check("the settings file is byte-for-byte unchanged",
          TOML.read_bytes() == before)


# --------------------------------------------------------------------------
#   3. An approved add: one line, and the app opens
# --------------------------------------------------------------------------
def t_an_approved_add_writes_one_line_and_the_app_opens():
    fresh()
    before = TOML.read_text(encoding="utf-8")
    calls = []
    with_gate(Verdict(), calls)
    code, out = PA.change({"action": "add", "name": NAME, "package": PKG})
    after = TOML.read_text(encoding="utf-8")
    check("an approved add answers 200 and reports the change", code == 200
          and out.get("ok") is True and out.get("changed") is True, (code, out))
    check("exactly one card was asked for", len(calls) == 1, calls)
    check("... and the answer says what happened in words",
          "Added" in str(out.get("said")), out.get("said"))
    added = [line for line in after.splitlines() if PKG in line]
    check("exactly ONE line was added, and it is the app",
          len(added) == 1 and added[0].strip() == f'"{NAME}" = "{PKG}"', added)
    check("the file's own comments and blank lines are all still there",
          before.count("#") == after.count("#")
          and len(after.splitlines()) == len(before.splitlines()) + 1,
          (before.count("#"), after.count("#"),
           len(before.splitlines()), len(after.splitlines())))
    # The REAL readers, not a stand-in: the framework re-read it, the phone
    # tool's own allow-list shows it, and a plan builds the launcher command.
    check("the framework was reloaded, so the phone tool sees it at once",
          A.phone_apps() == {NAME: PKG}, A.phone_apps())
    p = plan({"action": "open_app", "app": NAME})
    check("the app can now be OPENED, with the package on the command",
          len(p.steps) == 1
          and p.steps[0].argv[-6:] == ["monkey", "-p", PKG, "-c",
                                       "android.intent.category.LAUNCHER", "1"],
          repr([s.argv for s in p.steps]))
    play = plan({"action": "play", "app": NAME, "query": "The Weeknd"})
    check("... and SEARCHED in, through the address Jarvis knows for it",
          len(play.steps) == 1 and PKG in play.steps[0].argv
          and any("music.youtube.com/search?q=The%20Weeknd" in str(part)
                  for part in play.steps[0].argv),
          repr([s.argv for s in play.steps]))
    check("ONE audit line says it was added, naming the app and the package",
          audit_events() == ["phone_apps.added"]
          and audit_lines()[0].get("detail", {}).get("package") == PKG,
          audit_lines())


# --------------------------------------------------------------------------
#   4. An approved remove takes it away again
# --------------------------------------------------------------------------
def t_an_approved_remove_breaks_it_again():
    fresh()
    calls = []
    with_gate(Verdict(), calls)
    PA.change({"action": "add", "name": NAME, "package": PKG})
    before_remove = TOML.read_text(encoding="utf-8")
    code, out = PA.change({"action": "remove", "name": NAME})
    check("an approved remove answers 200 and reports the change", code == 200
          and out.get("changed") is True, (code, out))
    check("... under a SECOND card, naming the app being removed",
          len(calls) == 2 and calls[1]["action"] == "change_own_config"
          and calls[1]["detail"].get("package") == PKG, calls)
    check("the line is gone and the rest of the file is exactly as it was",
          TOML.read_text(encoding="utf-8") == MINIMAL,
          repr(TOML.read_text(encoding="utf-8")))
    check("the phone tool's own allow-list is empty again", A.phone_apps() == {})
    p = plan({"action": "open_app", "app": NAME})
    check("and the app no longer opens", p.steps == []
          and "no apps are allowed" in str(p.rejected[0].get("reason")).lower(),
          repr(p.rejected))
    check("an audit line says it was removed",
          audit_events() == ["phone_apps.added", "phone_apps.removed"],
          audit_events())


def t_a_rejected_remove_changes_nothing():
    fresh()
    calls = []
    with_gate(Verdict(), calls)
    PA.change({"action": "add", "name": NAME, "package": PKG})
    before = TOML.read_bytes()
    with_gate(Verdict(allowed=False, outcome="denied"), calls)
    code, out = PA.change({"action": "remove", "name": NAME})
    check("a rejected remove answers 409, not a quiet success",
          code == 409 and out.get("changed") is False, (code, out))
    check("the file is byte-for-byte unchanged",
          TOML.read_bytes() == before)
    check("the app is STILL allowed, and still opens",
          A.phone_apps() == {NAME: PKG} and len(plan(
              {"action": "open_app", "app": NAME}).steps) == 1)
    check("no removed audit line was written", "phone_apps.removed" not in
          audit_events(), audit_events())


# --------------------------------------------------------------------------
#   5. The card names the app, for an add AND a remove
# --------------------------------------------------------------------------
def t_the_card_names_the_name_and_the_package_both_ways():
    fresh()
    calls = []
    with_gate(Verdict(), calls)
    PA.change({"action": "add", "name": NAME, "package": PKG})
    PA.change({"action": "remove", "name": NAME})
    check("two cards, one per change", len(calls) == 2, calls)
    add_text = str((calls[0]["detail"] or {}).get("text") if calls else "")
    rm_text = str((calls[1]["detail"] or {}).get("text") if len(calls) > 1 else "")
    for label, text in (("add", add_text), ("remove", rm_text)):
        check(f"the {label} card names the friendly name", f'"{NAME}"' in text, text)
        check(f"the {label} card names the exact package id", PKG in text, text)
        check(f"the {label} card says nothing is written until approval",
              "until you approve" in text, text)
    check("the add card says what it adds, in one line", "ONE line" in add_text,
          add_text)
    check("the remove card says it stops Jarvis opening the app",
          "Stop Jarvis opening" in rm_text, rm_text)
    check("the prompt handed to the gate is the same card text",
          calls and calls[0]["prompt"] == add_text, calls)


# --------------------------------------------------------------------------
#   6. No bulk, anywhere
# --------------------------------------------------------------------------
def t_there_is_no_bulk_path():
    fresh()
    before = TOML.read_bytes()
    calls = []
    with_gate(Verdict(), calls)
    code, out = PA.change({"action": "add", "name": [NAME, "TikTok"],
                           "package": [PKG, "com.zhiliaoapp.musically"]})
    check("a LIST where a name belongs is refused", code == 400, (code, out))
    check("... and raises no card", calls == [], calls)
    check("the schema takes ONE name and ONE package - no array field",
          not any(p.get("type") == "array" for p in
                  AG.TOOLS["phone_apps"].schema()["function"]["parameters"][
                      "properties"].values()))
    state, _text = AG._prepare_phone_apps({"action": "add", "name": NAME,
                                           "package": PKG, "apps": [NAME, "TikTok"]})
    check("the model's own call is refused when it names a second app",
          isinstance(state, AG._PhoneAppsRefused), state)
    check("the settings file is byte-for-byte unchanged",
          TOML.read_bytes() == before)


# --------------------------------------------------------------------------
#   7. The tool action maps to a REAL gate action, and the mapping matters
# --------------------------------------------------------------------------
def _gate_tool_actions() -> dict:
    """`_TOOL_ACTIONS` from the published gate base, read structurally.

    `ast`, never the file's text: a suite that pins source spelling goes red
    when the code is merely reformatted (tools/check_no_source_pins.py), and
    this asks a question about a table, not about formatting."""
    tree = ast.parse(GATE_BASE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id == "_TOOL_ACTIONS" and isinstance(node.value, ast.Dict):
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict) \
                and any(isinstance(t, ast.Name) and t.id == "_TOOL_ACTIONS"
                        for t in node.targets):
            return ast.literal_eval(node.value)
    return {}


def t_the_new_tool_maps_to_the_real_gate_action():
    check("the tool is in jarvis_agent.TOOLS", "phone_apps" in AG.TOOLS,
          sorted(AG.TOOLS)[:5])
    tool = AG.TOOLS["phone_apps"]
    lookup = tool.gate_lookup_name({}) if tool.gate_lookup_name else "phone_apps"
    check("its gate lookup name is change_setting (an EXISTING key)",
          lookup == "change_setting", lookup)
    table = _gate_tool_actions()
    check("the gate base maps that key to change_own_config",
          table.get(lookup) == "change_own_config", table.get(lookup))
    check("... which is the SAME action the other settings changes map to "
          "(one permission model, not a second)",
          table.get("persona_write") == "change_own_config"
          or table.get("connect_account") == "change_own_config",
          (table.get("persona_write"), table.get("connect_account")))
    check("the tool's OWN name is NOT a gate key - so the mapping is what "
          "makes it real, not the name", "phone_apps" not in table)
    check("without the mapping the gate would answer unclassified_tool (the "
          "pre-fix shape this test exists to catch)",
          table.get("phone_apps", "unclassified_tool") == "unclassified_tool")
    tiers = tomllib.loads(SHIPPED_TOML.read_text(encoding="utf-8"))[
        "autonomy"]["tiers"] if tomllib else {}
    check("that action owns the ask tier in the shipped settings",
          tiers.get("change_own_config") == "ask", tiers.get("change_own_config"))
    try:
        import jarvis_gate
    except Exception:
        skip("jarvis_gate is not importable here (the owner's own file is not "
             "in this repository); the table above is the CI-visible half")
    else:
        action, _risky = jarvis_gate.action_for_tool(lookup, {})
        check("on a PC with the gate, action_for_tool really answers "
              "change_own_config", action == "change_own_config", action)


# --------------------------------------------------------------------------
#   8. The chat/Live path: one card, and the write only after a yes
# --------------------------------------------------------------------------
class NoRealProcess:
    """Fail loudly if real adb ever runs: this suite plans, it never touches a
    phone."""

    def __enter__(self):
        self.real = A._real_adb

        def boom(argv, timeout=15.0):
            raise AssertionError(f"a real process was started: {argv}")
        A._real_adb = boom
        return self

    def __exit__(self, *a):
        A._real_adb = self.real
        return False


class OneCall:
    """One real `jarvis_agent._one_call`, with only the gate replaced."""

    def __init__(self, args, verdict=None):
        self.args, self.verdict = args, verdict or Verdict()
        self.gate_calls, self.convo, self.steps = [], [], []
        self._out = AG._Out(lambda data: None, False)

    def run(self):
        def gate(action, detail, prompt):
            self.gate_calls.append({"action": action, "detail": detail,
                                    "prompt": prompt})
            return self.verdict

        call = {"id": "call-1", "function": {"name": "phone_apps",
                                             "arguments": json.dumps(self.args)}}
        AG._one_call(call, ["phone_apps"], self.convo, self.steps, gate,
                     lambda text: None, self._out,
                     lambda event, name, **kw: None, watch=AG._TurnWatch())
        return self

    @property
    def told(self):
        if not self.convo:
            return {}
        try:
            return json.loads(self.convo[-1]["content"])
        except Exception:
            return {"_raw": self.convo[-1]["content"]}


def t_the_chat_tool_asks_one_card_and_writes_only_after_a_yes():
    fresh()
    before = TOML.read_bytes()
    args = {"action": "add", "name": NAME, "package": PKG}
    denied = OneCall(args, Verdict(allowed=False, outcome="denied")).run()
    check("a denied chat card writes nothing",
          TOML.read_bytes() == before and A.phone_apps() == {})
    check("... and the model is told it was refused",
          denied.told.get("ok") is False, denied.told)
    check("... under the same one gate action (the mapping key here, which "
          "the gate resolves to change_own_config)",
          len(denied.gate_calls) == 1
          and denied.gate_calls[0]["action"] in ("change_setting",
                                                 "change_own_config"),
          denied.gate_calls)
    approved = OneCall(args, Verdict()).run()
    check("an approved chat card writes the one line",
          A.phone_apps() == {NAME: PKG}, A.phone_apps())
    check("... exactly one card was asked for", len(approved.gate_calls) == 1,
          approved.gate_calls)
    check("... and the result says the list changed",
          approved.told.get("ok") is True and approved.told.get("changed") is True,
          approved.told)
    check("the card the owner was shown names both", approved.gate_calls
          and PKG in str(approved.gate_calls[0]["prompt"])
          and NAME in str(approved.gate_calls[0]["prompt"]), approved.gate_calls)


def t_listing_costs_no_card_and_a_refusal_costs_none_either():
    fresh()
    before = TOML.read_bytes()
    listed = OneCall({"action": "list"}).run()
    check("a list call raises NO card", listed.gate_calls == [], listed.gate_calls)
    check("... answers from the settings file, honestly empty",
          listed.told.get("ok") is True and listed.told.get("apps") == [],
          listed.told)
    check("... and writes nothing", TOML.read_bytes() == before)
    refused = OneCall({"action": "add", "name": "Jarvis",
                       "package": "com.jarvis.client"}).run()
    check("an add of Jarvis's own app raises NO card (refused before one "
          "exists)", refused.gate_calls == [], refused.gate_calls)
    check("... and says why in the owner's words",
          "does not start its own app" in str(refused.told.get("error")),
          refused.told)
    extra = OneCall({"action": "add", "name": NAME, "package": PKG,
                     "also": "TikTok"}).run()
    check("a call naming a second app raises NO card and changes nothing",
          extra.gate_calls == [] and TOML.read_bytes() == before, extra.gate_calls)


# --------------------------------------------------------------------------
#   8b. The owner's own question, asked in chat (Q7, 2026-11-03)
#
# THE GAP, MEASURED. The catalogue's own phone-apps row says "Ask in chat on
# the PC or the phone - "which apps can you open on my phone?" lists them", and
# it did not: "which apps on my phone may you open" matched nothing and reached
# the local model (which has no phone-apps tool), and "what can you open on my
# phone" was answered with the generic feature-capability sentence, which names
# no app. The answer must come from the SAME table this suite's writer edits,
# raise no card, and write nothing.
# --------------------------------------------------------------------------
def t_the_question_in_chat_lists_the_same_table():
    import jarvis_quick as Q
    fresh()
    before = TOML.read_bytes()
    for words in ("which apps on my phone may you open",
                  "which apps can you open on my phone",
                  "what can you open on my phone",
                  "what apps do you allow on my phone"):
        got = Q.match(words)
        check(f"'{words}' is answered by the fast path (Q7)",
              got is not None and got.name == "phone_apps_list",
              None if got is None else got.name)
        res = Q.run(got, None, 1793505565.0) if got is not None else None
        check(f"...and it reads the real empty table, honestly: {words!r}",
              res is not None and "No apps are allowed yet" in res.reply,
              res.reply if res is not None else None)
        check(f"...and it raises no card and writes nothing: {words!r}",
              TOML.read_bytes() == before
              and (res is None or getattr(res, "read", []) == []), words)
    # One app in the owner's own table: the answer names it, and still no card.
    fresh(MINIMAL.replace("[phone_apps]\n", f'[phone_apps]\n"{NAME}" = "{PKG}"\n'))
    got = Q.match("which apps on my phone may you open")
    res = Q.run(got, None, 1793505565.0) if got is not None else None
    check("with one allowed app the answer names it",
          res is not None and NAME in res.reply, res.reply if res is not None else None)
    check("...and never prints the package id",
          res is not None and PKG not in res.reply,
          res.reply if res is not None else None)
    check("...and names where the list really lives",
          res is not None and "[phone_apps]" in res.reply
          and "jarvis-framework.toml" in res.reply,
          res.reply if res is not None else None)
    # A near miss keeps its own path: this is a question about an app, not the
    # list, and nothing here may answer it.
    got = Q.match("open youtube on my phone")
    check("near miss: 'open youtube on my phone' is not the list",
          got is None or got.name != "phone_apps_list", got)


# --------------------------------------------------------------------------
#   9. The owner's own file, and the line it already has
# --------------------------------------------------------------------------
def t_the_owners_own_shape_is_left_alone():
    """The shipped template, not the fixture: comment count, line endings and
    every other table must survive one add and one remove."""
    fresh(SHIPPED_TOML.read_text(encoding="utf-8"))
    before = TOML.read_text(encoding="utf-8")
    calls = []
    with_gate(Verdict(), calls)
    PA.change({"action": "add", "name": NAME, "package": PKG})
    added = TOML.read_text(encoding="utf-8")
    check("on the real template: one line added",
          len(added.splitlines()) == len(before.splitlines()) + 1,
          (len(before.splitlines()), len(added.splitlines())))
    check("... and every comment is still there",
          added.count("#") == before.count("#"),
          (before.count("#"), added.count("#")))
    PA.change({"action": "remove", "name": NAME})
    check("... and removing it gives the original text back exactly",
          TOML.read_text(encoding="utf-8") == before)


def t_a_line_written_by_hand_in_either_quote_style_can_be_removed():
    hand = MINIMAL.replace("[phone_apps]\n",
                           "[phone_apps]\n'YouTube Music' = 'com.google.android.apps.youtube.music'\n")
    fresh(hand)
    calls = []
    with_gate(Verdict(), calls)
    code, out = PA.change({"action": "remove", "name": NAME})
    check("a single-quoted line the owner wrote by hand is found and removed",
          code == 200 and out.get("changed") is True, (code, out))
    check("... and the file is exactly the fixture again",
          TOML.read_text(encoding="utf-8") == MINIMAL,
          repr(TOML.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------
#   10. It ships on, the phone tool stays opt-in, and the route is documented
# --------------------------------------------------------------------------
def t_it_ships_on_and_that_is_the_decision():
    for label, path in (("shipped template", SHIPPED_TOML), ("published base", BASE_TOML)):
        cfg = tomllib.loads(path.read_text(encoding="utf-8")) if tomllib else {}
        enabled = list((cfg.get("tools") or {}).get("enabled") or [])
        check(f"{label}: phone_apps is offered on a fresh install",
              "phone_apps" in enabled, enabled)
        check(f"{label}: control_phone is still opt-in (it can open apps; this "
              f"tool only manages the list)", "control_phone" not in enabled,
              enabled)
        check(f"{label}: [phone_apps] still ships empty",
              (cfg.get("phone_apps") or {}) == {}, cfg.get("phone_apps"))
    if not tomllib:
        skip("no tomllib/tomli, so the two shipped settings files could not be read")
        return
    doc = API_DOC.read_text(encoding="utf-8") if API_DOC.is_file() else ""
    check("the read route is documented in docs/JARVIS-API.md",
          "GET /api/phone/apps" in doc, "GET /api/phone/apps")
    check("the write route is documented too",
          "POST /api/phone/apps" in doc, "POST /api/phone/apps")


def t_the_patch_is_registered_and_has_no_gate_hunk():
    import _stack
    order = _stack.order()
    check("phone-apps.patch is in apply-patches.ps1's order",
          "phone-apps.patch" in order, order[-3:])
    check("... and the loader still comes last of all",
          order[-1] == "plugin-loader.patch", order[-3:])
    # It used to assert phone-apps.patch was IMMEDIATELY before the loader. A
    # patch appended after it (bench.patch, 2026-11-04) legitimately sits
    # between them - the rule that matters is that the loader is last and that
    # nothing but a patch written after this one is after this one.
    # packs-tamper-on-load.patch (2026-11-05) is the second such patch: it is
    # last of the core patches, immediately before the loader, and its one hunk
    # is in jarvis_skills.py - no gate row and no HUD route at all.
    check("... with only the patches written after this one between it and "
          "the loader",
          "phone-apps.patch" in order
          and order[order.index("phone-apps.patch") + 1] == "bench.patch"
          and order[order.index("bench.patch") + 1:]
          == ["packs-tamper-on-load.patch", "plugin-loader.patch"],
          order[-3:])
    # handsfree.patch (2026-11-04, hands-free mode) is NOT appended after this
    # patch. Its three `jarvis_gate.py` rows are ONE end-of-file hunk, and it is
    # applied BEFORE web-search-grant.patch so unknown-risk-approvable.patch
    # stays the LAST patch that writes jarvis_gate.py - the ordering
    # backend/test_gate_unknown_risk.py pins with no whitelist. So what this
    # suite checks is that it is in the stack at all, and on the right side of
    # web-search-grant.patch, and that it adds nothing between this patch and
    # the loader.
    check("handsfree.patch is in the stack, on the near side of "
          "web-search-grant.patch, and adds nothing after this patch",
          "handsfree.patch" in order
          and order.index("handsfree.patch") + 1 == order.index("web-search-grant.patch")
          and order.index("handsfree.patch") < order.index("phone-apps.patch"),
          order[-5:])
    patch = (HERE / "phone-apps.patch").read_text(encoding="utf-8")
    check("the patch touches jarvis_hud.py only - no jarvis_gate.py hunk, "
          "because the mapping ships in the gate base",
          "jarvis_gate.py" not in patch and "jarvis_hud.py" in patch, patch[:200])


if __name__ == "__main__":
    for fn in (t_an_empty_list_is_honest_and_opens_nothing,
               t_a_denied_card_writes_nothing,
               t_a_bad_request_is_refused_before_a_card_exists,
               t_an_approved_add_writes_one_line_and_the_app_opens,
               t_an_approved_remove_breaks_it_again,
               t_a_rejected_remove_changes_nothing,
               t_the_card_names_the_name_and_the_package_both_ways,
               t_there_is_no_bulk_path,
               t_the_new_tool_maps_to_the_real_gate_action,
               t_the_chat_tool_asks_one_card_and_writes_only_after_a_yes,
               t_listing_costs_no_card_and_a_refusal_costs_none_either,
               t_the_question_in_chat_lists_the_same_table,
               t_the_owners_own_shape_is_left_alone,
               t_a_line_written_by_hand_in_either_quote_style_can_be_removed,
               t_it_ships_on_and_that_is_the_decision,
               t_the_patch_is_registered_and_has_no_gate_hunk):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if SKIPPED:
        print(f"{len(SKIPPED)} skipped (never counted as a pass): " + "; ".join(SKIPPED))
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
