"""test_def068_entry.py - the Android app builder's way in, from a chat turn
(jarvis_agent.TOOLS["android_app"], DEF-068, 2026-11-14).

    python3 backend/test_def068_entry.py

THE DEFECT THIS SUITE IS FOR. `backend/jarvis_android_builder.py` has written,
built and installed a real Android app behind two risky `ask` cards since
2026-10-30 - and NOTHING in the tree called its four routes. The routes are
PC-only, a chat request carries no project id (the Projects page is a tab in the
Brain window with no chat box in it), and the fast-path answers only ANSWER
questions. So saying "build the Android app" in a project task did nothing.
DEF-068's row stays open until an entry point exists and is field tested; this
suite proves the entry point, never a build on the owner's PC.

WHAT IS PROVED HERE, and why each one is its own check:

  - THE TOOL IS REGISTERED AND DESCRIBED. It is in `jarvis_agent.TOOLS` with a
    schema the model can be sent, both of its acts resolve to the builder's
    REAL gate actions (`app_build_android` / `app_install_android`) in the
    published gate's `_TOOL_ACTIONS`, both actions ship "ask", both carry the
    builder's risky `_RISK` row and its no-rule-from-denial membership, and the
    tool is in NEEDS_A_PERSON - so a loosened tier cannot run a build with
    nobody asked.
  - prepare() MAKES THE PLAN WITHOUT SIDE EFFECTS. For a task that already has
    its project it returns the module's own CommandPlan and card words, runs no
    program, writes no file and raises no card. For a task with NO project it
    writes the module's fixed template (the module's own cardless act - the
    build cannot be planned until it exists) and still runs no program and
    raises no card.
  - ONE CARD PER ACT. A build asked for in chat raises EXACTLY ONE gate call,
    the card shows the module's own words (command, folder, SDK, JDK, the
    download disclosure), and the module's own card state stays empty - so the
    agent's card is the only one. The same for install.
  - execute() RUNS ONLY AFTER A YES. A denied card, a timed-out card, a stale
    event stream and a verdict at tier "auto" (nobody asked) all leave the
    world alone: zero processes, and the module's run function is never called.
  - AN AMBIGUOUS PROJECT OR TASK ASKS, NEVER GUESSES. No project, several
    projects and several open tasks all come back as ONE question naming the
    real choices, with zero cards, zero processes and zero bytes written.
  - THE TASK ID IS A FILENAME COMPONENT. A path-shaped or malformed task is
    refused before any file is touched, and a field the tool does not know (a
    "command", an "argv") is refused rather than run.

No Gradle, no adb, no phone, no model, no network. `A._run` - the module's one
process seam - is replaced on every path, so nothing real is ever started.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import socket
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_agent.py", "jarvis_android_builder.py",
                "jarvis_app_workspace.py", "jarvis_projects.py",
                "jarvis_child_env.py")

if shutil.which("git") is None:
    print("SKIP  git is not installed here - these tests create real app copies")
    sys.exit(0)

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-def068-"))
AUDIT = []
TIER = {"app_build_android": "ask", "app_install_android": "ask"}
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda event, detail=None: AUDIT.append((event, detail))
fw.action_tier = lambda action: TIER.get(action, "ask")
sys.modules["jarvis_framework"] = fw
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP)

_NET = []
_real_connect = socket.socket.connect


def _no_connect(self, *a, **k):
    _NET.append(a)
    raise OSError("test_def068_entry.py: no network")


socket.socket.connect = _no_connect

import jarvis_agent as AG  # noqa: E402
import jarvis_android_builder as A  # noqa: E402
import jarvis_app_workspace as W  # noqa: E402
import jarvis_projects as P  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    SKIPPED.append(name)
    print(f"SKIP {name}\n        {why}")


class Said:
    """What the approval gate hands back: the shape jarvis_gate.Verdict has.

    `outcome` is what gate-outcome.patch adds and what _a_person_said_yes reads:
    only "approved" is a person."""

    def __init__(self, outcome="approved", tier="ask", allowed=None, reason=""):
        self.outcome = outcome
        self.tier = tier
        self.allowed = (outcome == "approved") if allowed is None else allowed
        self.reason = reason
        self.action = ""
        self.request_id = "req-def068"


class Gate:
    """A fake approval gate that records every card it is asked about."""

    def __init__(self, answer=None):
        self.calls = []
        self.answer = answer if answer is not None else Said()

    def __call__(self, action, detail, prompt):
        self.calls.append({"action": action, "detail": detail, "prompt": prompt})
        return self.answer


class FakeToolchain:
    """A real SDK/JDK folder and a fake adb, so no test needs one installed."""

    def __init__(self, root: Path):
        self.sdk = root / "sdk"
        self.java = root / "jdk"
        self.adb = self.sdk / "platform-tools" / "adb.exe"
        for d in (self.sdk, self.java, self.adb.parent):
            d.mkdir(parents=True, exist_ok=True)
        self.adb.write_bytes(b"fake adb")
        self._saved = {}

    def __enter__(self):
        self._saved = {"sdk": A.sdk_root, "java": A.java_home, "adb": A.adb_path,
                       "win": A.WINDOWS}
        A.sdk_root = lambda: self.sdk
        A.java_home = lambda: self.java
        A.adb_path = lambda: self.adb
        A.WINDOWS = True
        return self

    def __exit__(self, *exc):
        A.sdk_root = self._saved["sdk"]
        A.java_home = self._saved["java"]
        A.adb_path = self._saved["adb"]
        A.WINDOWS = self._saved["win"]
        return False


class Ran:
    """A stand-in for `A._run`, the module's ONE process seam.

    It records the command and, for a build, makes the APK the module then looks
    for, so nothing real is ever executed and a later install has a file."""

    def __init__(self, code=0, make_apk=True):
        self.calls = []
        self.code = code
        self.make_apk = make_apk
        self._saved = None

    def __call__(self, argv, cwd, env, seconds, log):
        self.calls.append({"argv": list(argv), "cwd": Path(cwd)})
        Path(log).parent.mkdir(parents=True, exist_ok=True)
        Path(log).write_text("BUILD SUCCESSFUL\n", encoding="utf-8")
        if self.make_apk and len(argv) > 1 and argv[1] == A.GRADLE_TASK:
            apk = Path(cwd) / A.APK_REL
            apk.parent.mkdir(parents=True, exist_ok=True)
            apk.write_bytes(b"PK\x03\x04" + b"x" * 64)
        return self.code, Path(log)

    def __enter__(self):
        self._saved = A._run
        A._run = self
        return self

    def __exit__(self, *exc):
        A._run = self._saved
        return False


class NoProcess:
    """Fails the moment ANY command is attempted: proves a path ran nothing."""

    def __enter__(self):
        self._saved = A._run
        self.attempts = []

        def boom(argv, cwd, env, seconds, log):
            self.attempts.append(list(argv))
            raise AssertionError(f"a process was started: {argv}")
        A._run = boom
        return self

    def __exit__(self, *exc):
        A._run = self._saved
        return False


class OneCall:
    """One real `jarvis_agent._one_call`, with only the gate replaced.

    This is the exact path a chat turn takes: check_call -> prepare -> the
    sentinel branches -> the gate -> execute, with the result handed back to the
    model as the last message in `convo`."""

    def __init__(self, args, verdict=None):
        self.args, self.verdict = args, verdict or Said()
        self.gate_calls, self.convo, self.steps = [], [], []
        self._out = AG._Out(lambda data: None, False)

    def run(self):
        gate = Gate(self.verdict)
        call = {"id": "call-def068", "function": {
            "name": "android_app", "arguments": json.dumps(self.args)}}
        AG._one_call(call, ["android_app"], self.convo, self.steps, gate,
                     lambda text: None, self._out,
                     lambda event, name, **kw: None, watch=AG._TurnWatch())
        self.gate_calls = gate.calls
        return self

    @property
    def told(self) -> dict:
        if not self.convo:
            return {}
        try:
            return json.loads(self.convo[-1]["content"])
        except Exception:                                # noqa: BLE001
            return {"_raw": self.convo[-1]["content"]}


_N = [0]


def fresh_app(*, tasks=1, title=None) -> dict:
    """A real app project, made the way the Projects page makes one, plus its
    open task(s). Returns the project view and the task ids."""
    _N[0] += 1
    display = title or f"Weather App {_N[0]}"
    view = P.get().create({"name": display, "kind": "coding",
                           "app": {"type": "android"}}, here=True)
    app = P.get().app_of(view["id"])["app"]
    made = []
    for n in range(tasks):
        made.append(W.start_task(app, f"Build it {n + 1}", source="empty")["task"])
    return {"id": view["id"], "name": display, "app": app, "tasks": made}


def _snapshot(root: Path) -> dict:
    """Every file under `root` by path: (bytes, sha256). Used to prove a write
    did - or did not - happen."""
    out = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            out[str(path.relative_to(root))] = (len(data),
                                                hashlib.sha256(data).hexdigest())
    return out


def _write_page(app, task):
    """A written WebView project, with no card: the state a second build sees."""
    tdir = W.task_dir(app, task)
    A.write_template(A.plan_template(app, task))
    return tdir


# --------------------------------------------------------------------------
#   1. The tool is registered, and described the way the model is sent it
# --------------------------------------------------------------------------

def t_the_tool_is_registered_and_described():
    check("android_app is in jarvis_agent.TOOLS", "android_app" in AG.TOOLS,
          sorted(AG.TOOLS)[-4:])
    tool = AG.TOOLS["android_app"]
    check("its model-facing name is android_app", tool.name == "android_app", tool.name)
    told = tool.description
    check("the description says what it makes, in the owner's words",
          "Android app" in told and "fixed project" in told, told[:200])
    check("... that the model supplies only the page and a name",
          "page" in told and "optional name" in told, told)
    check("... that it builds ONE card's worth at a time and runs nothing before "
          "a yes", "One card before Gradle" in told
          and "nothing runs until the owner says yes" in told, told)
    check("... and that an ambiguous project must be ASKED about, never guessed",
          "ask instead of guessing" in told, told)
    check("... and that the app it writes gets no permission at all",
          "no permission" in told, told)
    check("its schema is one object with an action enum",
          tool.parameters.get("type") == "object"
          and tool.parameters["properties"]["action"]["enum"] == ["build", "install"],
          tool.parameters.get("properties", {}).get("action"))
    check("... every property is typed text, and nothing is required",
          all(p.get("type") == "string"
              for p in tool.parameters["properties"].values())
          and tool.parameters.get("required") == [],
          tool.parameters)
    check("... the page's three files are its own flat arguments",
          all(k in tool.parameters["properties"]
              for k in ("index_html", "app_js", "app_css")),
          sorted(tool.parameters["properties"]))


def t_the_schema_can_be_sent_and_checked():
    try:
        import jarvis_tool_schema as TS
    except Exception as exc:                             # noqa: BLE001
        skip("the schema guard", f"jarvis_tool_schema is not importable ({exc})")
        return
    problems = TS.guard_tool_schemas(AG.TOOLS)
    check("every tool's schema, this one included, uses only keywords that are "
          "really enforced", problems.get("ok") is True,
          problems.get("problems"))
    args, problem = AG.check_call("android_app", "{}", ["android_app"], AG.TOOLS)
    check("an empty call is a valid call: the defaults are the tool's job",
          problem is None and args == {}, (args, problem))
    args, problem = AG.check_call(
        "android_app", json.dumps({"action": "install", "project": "x"}),
        ["android_app"], AG.TOOLS)
    check("... and so is one naming its act and its project",
          problem is None and args.get("action") == "install", (args, problem))
    _args, problem = AG.check_call(
        "android_app", json.dumps({"action": "explode"}), ["android_app"], AG.TOOLS)
    check("the model cannot invent a third action", problem is not None, problem)


def t_both_acts_resolve_to_the_builders_real_gate_actions():
    tool = AG.TOOLS["android_app"]
    check("a build is put to the gate under the builder's OWN action name",
          tool.gate_lookup_name({}) == A.BUILD_ACTION == "app_build_android",
          tool.gate_lookup_name({}))
    check("an install under the builder's other own action name",
          tool.gate_lookup_name({"action": "install"}) == A.INSTALL_ACTION
          == "app_install_android",
          tool.gate_lookup_name({"action": "install"}))
    table = _base_gate_table("_TOOL_ACTIONS")
    if not table:
        skip("the published gate's table", "jarvis-backend/jarvis_gate.py is not here")
    else:
        for lookup in (A.BUILD_ACTION, A.INSTALL_ACTION):
            check(f"the published gate maps {lookup} to itself, so "
                  f"action_for_tool() answers the specific card",
                  table.get(lookup) == lookup, table.get(lookup))
    tiers = _shipped_tiers()
    if not tiers:
        skip("the shipped tiers", "the shipped jarvis-framework.toml is not here")
    else:
        check("the build action ships 'ask' in the shipped settings",
              tiers.get(A.BUILD_ACTION) == "ask", tiers.get(A.BUILD_ACTION))
        check("... and so does the install action",
              tiers.get(A.INSTALL_ACTION) == "ask", tiers.get(A.INSTALL_ACTION))
    risk = _base_gate_table("_RISK")
    if risk:
        for action in (A.BUILD_ACTION, A.INSTALL_ACTION):
            check(f"{action} carries the builder's own risky 'no' row",
                  action in risk and risk[action][0] == "no", risk.get(action))
    denial = _base_gate_names("_NO_RULE_FROM_DENIAL")
    if denial:
        for action in (A.BUILD_ACTION, A.INSTALL_ACTION):
            check(f"{action}: a denial is about that card, never a standing rule",
                  action in denial, sorted(denial)[:3])
    check("the tool is in NEEDS_A_PERSON, so a loosened tier still cannot run it "
          "with nobody asked", "android_app" in AG.NEEDS_A_PERSON,
          "android_app" in AG.NEEDS_A_PERSON)


def _base_gate_table(name: str) -> dict:
    """One dict from the published gate, read with `ast`, never text.

    The table as the GATE builds it, not as its literal reads: a later row is
    added by `<name>.update({...})` at module level (the shape handsfree,
    product-check, github-tools and android-builder-gate all use, because every
    line inside the literal is some earlier patch's hunk context), and that call
    runs at import exactly as if the rows sat inside the literal. Reading only
    the literal is what made this suite report "the published gate maps
    app_build_android to itself" FAIL on a tree where the gate answered
    correctly - measured on this branch, 2026-11-14."""
    path = REPO / "jarvis-backend" / "jarvis_gate.py"
    if not path.is_file():
        return {}
    body = ast.parse(path.read_text(encoding="utf-8")).body
    table = {}
    for node in body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id == name and isinstance(node.value, ast.Dict):
            table = ast.literal_eval(node.value)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict) \
                and any(isinstance(t, ast.Name) and t.id == name
                        for t in node.targets):
            table = ast.literal_eval(node.value)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) \
                and isinstance(node.value.func, ast.Attribute) \
                and node.value.func.attr == "update" \
                and isinstance(node.value.func.value, ast.Name) \
                and node.value.func.value.id == name \
                and len(node.value.args) == 1 \
                and isinstance(node.value.args[0], ast.Dict):
            table.update(ast.literal_eval(node.value.args[0]))
    return table


def _base_gate_names(name: str) -> set:
    """A frozenset name in the published gate, read with `ast`."""
    path = REPO / "jarvis-backend" / "jarvis_gate.py"
    if not path.is_file():
        return set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Set) \
                and any(isinstance(t, ast.Name) and t.id == name
                        for t in node.targets):
            return {n.value for n in node.value.elts
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id == name and isinstance(node.value, ast.Set):
            return {n.value for n in node.value.elts
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    return set()


def _shipped_tiers() -> dict:
    path = REPO / "backend" / "rebuilt" / "jarvis-framework.toml"
    if not path.is_file():
        return {}
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            return {}
    return (tomllib.loads(path.read_text(encoding="utf-8")).get("autonomy") or {}) \
        .get("tiers") or {}


# --------------------------------------------------------------------------
#   2. prepare(): the plan, no side effects, no card
# --------------------------------------------------------------------------

def t_prepare_makes_the_build_plan_and_writes_nothing():
    """A task that ALREADY has its Android project: preparing a second build
    changes nothing on disk and runs nothing."""
    app = fresh_app()
    tdir = _write_page(app["app"], app["tasks"][0])
    before = _snapshot(tdir)
    tool = AG.TOOLS["android_app"]
    with FakeToolchain(_TMP / "tc-a"), NoProcess() as np:
        state, text = tool.prepare({"project": app["name"], "task": app["tasks"][0]})
        own = A.plan_build(app["app"], app["tasks"][0]).says
        # Read the command HERE: the fake toolchain also fakes A.WINDOWS = True
        # (the module builds on Windows only), and `__exit__` restores the REAL
        # flag. Read outside this block on a Linux runner, build_command answers
        # `gradlew` while the plan was made for the Windows `gradlew.bat`.
        expected = A.build_command(tdir)
    check("a build plans as the module's own CommandPlan",
          isinstance(state, A.CommandPlan) and state.kind == "build", type(state))
    check("... for the project and task that were named",
          (state.project, state.task) == (app["app"], app["tasks"][0]),
          (state.project, state.task))
    check("... with the module's ONE build command",
          state.argv == expected, state.argv)
    check("the card's words are the module's own plan words",
          text.startswith('Build the Android app "'), text[:120])
    check("... naming the exact command, folder and toolchain",
          "gradlew.bat assembleDebug" in text and str(tdir) in text
          and "Android SDK:" in text and "Java:" in text, text[:500])
    check("... and the download disclosure, so the first build is not a surprise",
          "downloads the Gradle distribution" in text, text[-400:])
    check("... and it really is the module's own text, not a second copy",
          text == own, (text[:200], own[:200]))
    check("nothing ran", np.attempts == [], np.attempts)
    check("not one byte on disk changed", _snapshot(tdir) == before,
          sorted(set(_snapshot(tdir)) ^ set(before)))


def t_prepare_writes_the_fixed_project_and_raises_no_card():
    """A task with NO project: the module's own cardless template write, then
    the build plan. No program, and no card from the module."""
    app = fresh_app()
    tdir = W.task_dir(app["app"], app["tasks"][0])
    tool = AG.TOOLS["android_app"]
    with FakeToolchain(_TMP / "tc-b"), NoProcess() as np:
        state, text = tool.prepare({"project": app["name"], "task": app["tasks"][0],
                                    "title": "My Weather", "index_html": "<h1>hi</h1>",
                                    "app_js": "console.log(1)",
                                    "app_css": "body{color:red}"})
    check("a clean task plans a build", isinstance(state, A.CommandPlan)
          and state.kind == "build" and not state.refused, (state, text[:100]))
    check("the fixed project was written before the card",
          A.is_template(tdir) and (tdir / "settings.gradle.kts").is_file()
          and (tdir / "app/build.gradle.kts").is_file()
          and (tdir / A.ASSET_DIR / "index.html").is_file(), A.is_template(tdir))
    check("... with the page the model gave, not a placeholder",
          (tdir / A.ASSET_DIR / "index.html").read_text(encoding="utf-8")
          == "<h1>hi</h1>")
    check("... and the app name the model gave", "My Weather" in
          (tdir / "app/src/main/res/values/strings.xml").read_text(encoding="utf-8"))
    check("the card says the project was written first, so nothing appears "
          "unannounced", text.startswith("Jarvis writes this task's Android project"),
          text[:160])
    check("nothing ran", np.attempts == [], np.attempts)
    check("the MODULE raised no card: its own card state is empty",
          A._waiting(app["app"], app["tasks"][0]) is None and not A._S_STATE["pending"],
          A._S_STATE["pending"])
    check("no network was touched", _NET == [], _NET)
    A._reset_for_tests()


def t_a_task_that_already_has_the_project_is_not_rewritten():
    app = fresh_app()
    tdir = _write_page(app["app"], app["tasks"][0])
    before = _snapshot(tdir)
    tool = AG.TOOLS["android_app"]
    with FakeToolchain(_TMP / "tc-c"), NoProcess():
        state, text = tool.prepare({"project": app["name"], "task": app["tasks"][0]})
    check("the second build is planned against the project already there",
          isinstance(state, A.CommandPlan) and not state.refused, state)
    check("not one byte was rewritten", _snapshot(tdir) == before,
          sorted(set(_snapshot(tdir)) ^ set(before)))
    check("... and the card does NOT claim a template write",
          not text.startswith("Jarvis writes"), text[:120])


def t_a_native_screens_task_builds_what_it_has():
    """The task's own app.json chooses the native kind; no page is passed."""
    app = fresh_app()
    tdir = W.task_dir(app["app"], app["tasks"][0])
    spec = {"name": "Notes", "package_tail": "notes", "bg": "#101828",
            "accent": "#7cc4ff", "start": "home",
            "screens": [{"id": "home", "kind": "text", "title": "Home",
                         "body": ["Hello"]}]}
    (tdir / A.SPEC_FILE).write_text(json.dumps(spec), encoding="utf-8")
    tool = AG.TOOLS["android_app"]
    with FakeToolchain(_TMP / "tc-d"), NoProcess():
        state, text = tool.prepare({"project": app["name"], "task": app["tasks"][0]})
    check("a native task plans a native build", isinstance(state, A.CommandPlan)
          and not state.refused and state.app_kind == A.NATIVE, (state, text[:120]))
    check("... and its card says how many screens the phone will draw",
          "native screens" in text and "1 screen" in text, text[:220])
    check("the validated spec ships in the app's assets", (tdir / A.SPEC_ASSET).is_file())
    check("... and no web page was written into a native app",
          not any((tdir / A.ASSET_DIR / n).exists() for n in A.ASSETS))


# --------------------------------------------------------------------------
#   3. One card, and only after a yes
# --------------------------------------------------------------------------

def t_one_card_per_build_and_the_command_runs_once():
    app = fresh_app()
    tdir = W.task_dir(app["app"], app["tasks"][0])
    with FakeToolchain(_TMP / "tc-e"), Ran() as ran:
        call = OneCall({"project": app["name"], "task": app["tasks"][0],
                        "index_html": "<h1>hi</h1>"}).run()
        # As above: the command the module names while its Windows flag is
        # faked, not this PC's once `__exit__` has restored the real one.
        expected = A.build_command(tdir)
    check("one build asked the owner EXACTLY once", len(call.gate_calls) == 1,
          call.gate_calls)
    if call.gate_calls:
        card = call.gate_calls[0]
        check("... under the build action", card["action"] == A.BUILD_ACTION,
              card["action"])
        check("... showing the module's own plan words, not a tool-call line",
              "gradlew.bat assembleDebug" in card["prompt"]
              and "folder:" in card["prompt"], card["prompt"][:200])
        check("... and the detail the gate records names the command",
              card["detail"].get("text", "") == card["prompt"], card["detail"])
    check("the ONE documented command ran once, in the task's copy",
          len(ran.calls) == 1 and ran.calls[0]["argv"] == expected
          and ran.calls[0]["cwd"] == tdir, ran.calls)
    check("the answer says it BUILT and where the APK is",
          call.told.get("ok") is True and call.told.get("built") is True
          and call.told.get("apk") == str(tdir / A.APK_REL), call.told)
    check("... and says plainly that nothing is on the phone yet",
          "SECOND card" in str(call.told.get("note", "")), call.told.get("note"))
    check("the module's own card state stayed empty: the agent's card is the only "
          "one", A._waiting(app["app"], app["tasks"][0]) is None,
          A._S_STATE["pending"])
    A._reset_for_tests()


def t_a_denied_card_runs_nothing():
    app = fresh_app()
    _write_page(app["app"], app["tasks"][0])
    before = _snapshot(W.task_dir(app["app"], app["tasks"][0]))
    with FakeToolchain(_TMP / "tc-f"), NoProcess() as np:
        call = OneCall({"project": app["name"], "task": app["tasks"][0]},
                       Said(outcome="denied", allowed=False)).run()
    check("a denied card asked once", len(call.gate_calls) == 1, call.gate_calls)
    check("... and NOT ONE command ran", np.attempts == [], np.attempts)
    check("... and nothing on disk changed",
          _snapshot(W.task_dir(app["app"], app["tasks"][0])) == before)
    check("... and the model is told it was refused, not told it built",
          call.told.get("ok") is False and "refused" in str(call.told.get("error", "")),
          call.told)
    A._reset_for_tests()


def t_a_timed_out_card_runs_nothing():
    app = fresh_app()
    _write_page(app["app"], app["tasks"][0])
    with FakeToolchain(_TMP / "tc-g"), NoProcess() as np:
        call = OneCall({"project": app["name"], "task": app["tasks"][0]},
                       Said(outcome="timed_out", allowed=False)).run()
    check("a timed-out card ran nothing", np.attempts == [], np.attempts)
    check("... and was asked exactly once", len(call.gate_calls) == 1)
    check("... and the model was told", call.told.get("ok") is False, call.told)
    A._reset_for_tests()


def t_a_stale_event_stream_runs_nothing():
    """Rule 4: the app holds when the stream is stale, and the gate's verdict is
    that hold. Nothing may start on it."""
    app = fresh_app()
    _write_page(app["app"], app["tasks"][0])
    with FakeToolchain(_TMP / "tc-h"), NoProcess() as np:
        call = OneCall({"project": app["name"], "task": app["tasks"][0]},
                       Said(outcome="refused", allowed=False,
                            reason="the event stream is stale")).run()
    check("a stale stream ran no command", np.attempts == [], np.attempts)
    check("... and the refusal is the gate's own reason",
          "stale" in json.dumps(call.told), call.told)
    check("... and the step records a refusal", call.steps and
          call.steps[-1].get("outcome") == "refused", call.steps)
    A._reset_for_tests()


def t_a_verdict_without_a_person_is_not_a_yes():
    """The gate allowed it at tier "auto" - nobody was asked. NEEDS_A_PERSON is
    the belt: it does not run."""
    app = fresh_app()
    _write_page(app["app"], app["tasks"][0])
    with FakeToolchain(_TMP / "tc-i"), NoProcess() as np:
        call = OneCall({"project": app["name"], "task": app["tasks"][0]},
                       Said(outcome="auto", tier="auto", allowed=True)).run()
    check("nobody asked: the build did not run", np.attempts == [], np.attempts)
    check("... and the model is told why, naming the line to change",
          "without asking anyone" in json.dumps(call.told), call.told)
    A._reset_for_tests()


def t_a_failed_build_is_never_reported_as_a_build():
    app = fresh_app()
    _write_page(app["app"], app["tasks"][0])
    with FakeToolchain(_TMP / "tc-j"), Ran(code=1, make_apk=False) as ran:
        call = OneCall({"project": app["name"], "task": app["tasks"][0]}).run()
    check("the command did run", len(ran.calls) == 1, ran.calls)
    check("a non-zero build reports failure, never a build",
          call.told.get("ok") is False and call.told.get("built") is False,
          call.told)
    check("... and keeps the end of Gradle's own words for the owner",
          "BUILD SUCCESSFUL" in str(call.told.get("log", "")) or
          "exit code" in str(call.told.get("error", "")), call.told.get("error"))
    A._reset_for_tests()


def t_the_install_half_asks_its_own_card():
    app = fresh_app()
    tdir = W.task_dir(app["app"], app["tasks"][0])
    _write_page(app["app"], app["tasks"][0])
    apk = tdir / A.APK_REL
    apk.parent.mkdir(parents=True, exist_ok=True)
    apk.write_bytes(b"PK\x03\x04" + b"y" * 128)
    with FakeToolchain(_TMP / "tc-k") as tc, Ran() as ran:
        call = OneCall({"action": "install", "project": app["name"],
                        "task": app["tasks"][0]}).run()
    check("an install asks its OWN one card", len(call.gate_calls) == 1,
          call.gate_calls)
    if call.gate_calls:
        card = call.gate_calls[0]
        check("... under the install action", card["action"] == A.INSTALL_ACTION,
              card["action"])
        check("... naming the exact adb command and the file",
              "adb.exe" in card["prompt"] and "install -r" in card["prompt"]
              and str(apk) in card["prompt"], card["prompt"][:300])
        check("... and saying it is a sideload that never touches the Play Store",
              "SIDELOAD" in card["prompt"] and "Play Store" in card["prompt"])
    check("the ONE documented install command ran once",
          len(ran.calls) == 1
          and ran.calls[0]["argv"] == A.install_command(tc.adb, apk), ran.calls)
    check("the answer says installed, and claims nothing else",
          call.told.get("ok") is True and call.told.get("installed") is True,
          call.told)
    A._reset_for_tests()


def t_install_before_a_build_is_refused_with_no_card():
    app = fresh_app()
    _write_page(app["app"], app["tasks"][0])
    with FakeToolchain(_TMP / "tc-l"), NoProcess() as np:
        call = OneCall({"action": "install", "project": app["name"],
                        "task": app["tasks"][0]}).run()
    check("no APK: no card is raised", call.gate_calls == [], call.gate_calls)
    check("... nothing ran", np.attempts == [], np.attempts)
    check("... and the model is given the module's own sentence",
          "no APK to install yet" in json.dumps(call.told), call.told)
    A._reset_for_tests()


# --------------------------------------------------------------------------
#   4. Which project, and which task: ask, never guess
# --------------------------------------------------------------------------

def t_several_projects_ask_instead_of_guessing():
    """Two projects and no name: ONE question naming them, never a pick. The
    store is its own so the answer cannot be about projects other tests made."""
    store = P.Projects(path=_TMP / "two-projects.db")
    first = store.create({"name": "Weather App Alpha", "kind": "coding",
                          "app": {"type": "android"}}, here=True)
    second = store.create({"name": "Weather App Beta", "kind": "coding",
                           "app": {"type": "android"}}, here=True)
    before = _snapshot(W.root())
    real_get = P.get
    P.get = lambda: store
    try:
        with FakeToolchain(_TMP / "tc-m"), NoProcess() as np:
            call = OneCall({}).run()
    finally:
        P.get = real_get
    check("two projects and no name: no card at all", call.gate_calls == [],
          call.gate_calls)
    check("... nothing ran", np.attempts == [], np.attempts)
    check("... nothing was written", _snapshot(W.root()) == before)
    check("... and one QUESTION comes back", call.told.get("asked") is True,
          call.told)
    question = str(call.told.get("question", ""))
    check("... naming both real projects, so the owner can just answer",
          first["name"] in question and second["name"] in question, question)
    check("... and it is not dressed up as a refusal or a build",
          call.told.get("ok") is False and "built" not in call.told, call.told)
    check("the step says no card was needed", call.steps and
          call.steps[-1].get("outcome") == "no card needed", call.steps)
    A._reset_for_tests()


def t_no_projects_asks_for_one_in_plain_words():
    empty = P.Projects(path=_TMP / "empty-projects.db")
    real_get = P.get
    P.get = lambda: empty
    try:
        with FakeToolchain(_TMP / "tc-n"), NoProcess() as np:
            call = OneCall({}).run()
    finally:
        P.get = real_get
    check("no projects: no card", call.gate_calls == [], call.gate_calls)
    check("... nothing ran", np.attempts == [], np.attempts)
    check("... and the owner is told how to make one, not shown an error",
          call.told.get("asked") is True and "no projects yet" in str(
              call.told.get("question", "")).lower(), call.told)


def t_several_open_tasks_ask_instead_of_guessing():
    app = fresh_app(tasks=2)
    before = _snapshot(W.task_dir(app["app"], app["tasks"][0]))
    with FakeToolchain(_TMP / "tc-o"), NoProcess() as np:
        call = OneCall({"project": app["name"]}).run()
    check("two open tasks and no task id: no card", call.gate_calls == [],
          call.gate_calls)
    check("... nothing ran", np.attempts == [], np.attempts)
    check("... the first task's copy is untouched",
          _snapshot(W.task_dir(app["app"], app["tasks"][0])) == before)
    check("... and the question names both task ids",
          call.told.get("asked") is True
          and all(t in str(call.told.get("question", "")) for t in app["tasks"]),
          call.told)
    A._reset_for_tests()


def t_one_project_and_one_task_need_no_name():
    app = fresh_app()
    empty = P.Projects(path=_TMP / "one-project.db")
    empty.create({"name": app["name"], "kind": "coding",
                  "app": {"adopt": app["app"]}}, here=True)
    real_get = P.get
    P.get = lambda: empty
    try:
        with FakeToolchain(_TMP / "tc-p"), Ran() as ran:
            call = OneCall({}).run()
    finally:
        P.get = real_get
    check("the only project and its only task are used without being named",
          len(call.gate_calls) == 1 and len(ran.calls) == 1, (call.gate_calls,
                                                              ran.calls))
    check("... and the answer is a build", call.told.get("built") is True, call.told)
    A._reset_for_tests()


def t_a_project_id_is_accepted_as_well_as_a_name():
    app = fresh_app()
    _write_page(app["app"], app["tasks"][0])
    tool = AG.TOOLS["android_app"]
    with FakeToolchain(_TMP / "tc-q"), NoProcess():
        state, _text = tool.prepare({"project": app["id"],
                                     "task": app["tasks"][0]})
    check("a 32-hex project id resolves to the same app", isinstance(
        state, A.CommandPlan) and not state.refused and state.project == app["app"],
        state)
    with FakeToolchain(_TMP / "tc-r"), NoProcess():
        state, text = tool.prepare({"project": "No Such Project",
                                    "task": app["tasks"][0]})
    check("a name nothing matches is refused in words, before any card",
          isinstance(state, AG._AndroidRefused)
          and "there is no project called" in state.problem, (state, text[:80]))


def t_a_path_shaped_task_is_refused_before_any_write():
    app = fresh_app()
    tool = AG.TOOLS["android_app"]
    for bad in ("../../etc", "ABCDEF", "", "0" * 11, "0" * 13, "zzzzzzzzzzzz"):
        if bad == "":
            continue                     # "" means "the only open task" on purpose
        with FakeToolchain(_TMP / "tc-s"), NoProcess() as np:
            state, _text = tool.prepare({"project": app["name"], "task": bad})
        check(f"task {bad!r} is refused, not used as a path",
              isinstance(state, AG._AndroidRefused), state)
        check(f"... and nothing ran for {bad!r}", np.attempts == [], np.attempts)
    with FakeToolchain(_TMP / "tc-t"), NoProcess():
        state, _text = tool.prepare({"project": app["name"], "task": "0" * 12})
    check("a well-formed task id that is not open is refused as gone",
          isinstance(state, AG._AndroidRefused) and "gone" in state.problem,
          state)


def t_a_field_the_tool_does_not_know_is_refused_not_run():
    app = fresh_app()
    tool = AG.TOOLS["android_app"]
    for poison in ({"command": "rm -rf /"}, {"argv": ["powershell", "-c", "x"]},
                   {"action": "build", "extra": "x"}):
        with FakeToolchain(_TMP / "tc-u"), NoProcess() as np:
            state, _text = tool.prepare(
                dict(poison, project=app["name"], task=app["tasks"][0]))
        check(f"{sorted(poison)} is refused: the model cannot choose what runs",
              isinstance(state, AG._AndroidRefused)
              and "one app at a time" in state.problem, state)
        check(f"... and nothing ran for {sorted(poison)}", np.attempts == [],
              np.attempts)
    with FakeToolchain(_TMP / "tc-v"), NoProcess():
        state, _text = tool.prepare({"action": "rm -rf", "project": app["name"],
                                     "task": app["tasks"][0]})
    check('an invented action is refused with "build" or "install"',
          isinstance(state, AG._AndroidRefused) and '"build"' in state.problem,
          state)


def t_a_project_that_is_not_an_android_app_is_refused_in_the_modules_words():
    _N[0] += 1
    view = P.get().create({"name": f"Website {_N[0]}", "kind": "coding",
                           "app": {"type": "web"}}, here=True)
    app = P.get().app_of(view["id"])["app"]
    task = W.start_task(app, "Build it", source="empty")["task"]
    tool = AG.TOOLS["android_app"]
    with FakeToolchain(_TMP / "tc-w"), NoProcess():
        state, _text = tool.prepare({"project": view["name"], "task": task})
    check("a WebView app is refused as not an Android app",
          isinstance(state, AG._AndroidRefused)
          and "not an Android app" in state.problem, state)


def t_the_template_write_is_the_only_write_a_second_build_does_not_do():
    """The double-ask the design note calls the failure mode: if the module
    raised its own card too, one build would ask twice. Count for both acts."""
    app = fresh_app()
    _write_page(app["app"], app["tasks"][0])
    tdir = W.task_dir(app["app"], app["tasks"][0])
    apk = tdir / A.APK_REL
    apk.parent.mkdir(parents=True, exist_ok=True)
    apk.write_bytes(b"PK\x03\x04" + b"z" * 32)
    with FakeToolchain(_TMP / "tc-x"), Ran():
        build = OneCall({"project": app["name"], "task": app["tasks"][0]}).run()
        install = OneCall({"action": "install", "project": app["name"],
                           "task": app["tasks"][0]}).run()
    check("a build asks one card and an install asks one card: two acts, two "
          "cards, never four", len(build.gate_calls) == 1
          and len(install.gate_calls) == 1,
          (len(build.gate_calls), len(install.gate_calls)))
    check("... and the module never had a card of its own waiting",
          A._waiting(app["app"], app["tasks"][0]) is None, A._S_STATE["pending"])
    A._reset_for_tests()


def main():
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:             # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        socket.socket.connect = _real_connect
        A._reset_for_tests()
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
