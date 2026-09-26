"""jarvis_skill_tools.py: a skill runs only through the gate, only with a person's yes.

What is proven, not just the happy path:
  - discovery and planning run nothing and open no socket
  - arguments are typed strictly: "5" is not an integer, true is not a number
  - the tier/action is a function of trust and effects; nothing the model
    sends and nothing the skill says about its own trust can change it
  - a gate answer of auto, notify, timed_out or denied never runs anything
  - a file changed after the card was shown never runs
  - the child gets no tokens from the environment, and is stopped on time
  - wired into the REAL jarvis_agent.py: refused without the verdict
    hand-off, runs with it only on an approved `ask`

    python3 test_skill_tools.py
"""
import ast
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_skill_tools as ST

REPO_BACKEND = Path(os.environ.get("JARVIS_REPO_BACKEND", "/home/user/Epic-Jarvis/backend"))

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    SKIPPED.append(name)
    print(f"SKIP  {name}: {why}")


# ---------------------------------------------------------------- fixtures

def clean_scanner(text, label):
    return []


def Finding(severity, reason):
    return SimpleNamespace(severity=severity, reason=reason)


def trust(mapping):
    return lambda name: mapping.get(name, "third_party")


def never_tainted():
    return False


DOUBLE_PY = textwrap.dedent('''\
    import json, sys
    data = json.load(sys.stdin)
    print(json.dumps({"doubled": data["amount"] * 2, "unit": data.get("unit")}))
''')

DOUBLE_TOML = textwrap.dedent('''\
    entrypoint = "scripts/run.py"
    timeout_seconds = 10
    effects = ["compute"]

    [params.amount]
    type = "number"
    required = true
    minimum = 0
    maximum = 1000000

    [params.unit]
    type = "string"
    enum = ["km", "mi"]
    default = "km"
''')


def make_skill(root, name, *, py=DOUBLE_PY, toml=DOUBLE_TOML, fm_extra="",
               folder=None, description="Doubles a distance. Use for tests.",
               extra_files=None):
    d = Path(root) / (folder or name)
    (d / "scripts").mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n{fm_extra}---\n\n# {name}\n",
        encoding="utf-8")
    (d / "scripts" / "run.py").write_text(py, encoding="utf-8")
    if toml is not None:
        (d / ST.TOOL_FILE).write_text(toml, encoding="utf-8")
    for rel, content in (extra_files or {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content, encoding="utf-8")
    return d


def load(root, name, t="local", scanner=clean_scanner):
    return ST.load_skill(Path(root) / name, scanner=scanner, trust_of=trust({name: t}))


def rejected_reason(root, folder, scanner=clean_scanner, t=None):
    found, rejected = ST.discover(root, scanner=scanner, trust_of=trust(t or {}))
    for f, r in rejected:
        if f == folder:
            return r
    return None


def V(tier="ask", outcome="approved", allowed=True, action=ST.ACTION_LOCAL, reason="approved by a human"):
    return SimpleNamespace(tier=tier, outcome=outcome, allowed=allowed, action=action, reason=reason)


class Recorder:
    """A spawn that records instead of starting anything."""
    def __init__(self):
        self.calls = []

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        Path(kw["out"]).write_text('{"fake": true}')
        Path(kw["err"]).write_text("")
        return {"exit_code": 0, "timed_out": False}


class NothingRuns:
    """No socket and no child process, inside this block."""
    def __enter__(self):
        self.c, self.p = socket.socket.connect, subprocess.Popen
        def boom(*a, **k):
            raise AssertionError("a socket or a process was opened")
        socket.socket.connect = boom
        subprocess.Popen = boom
        return self

    def __exit__(self, *a):
        socket.socket.connect, subprocess.Popen = self.c, self.p
        return False


def tmp():
    return Path(tempfile.mkdtemp(prefix="skilltest-"))


# ---------------------------------------------------------------- discovery

def t_discovery_runs_nothing():
    root = tmp()
    make_skill(root, "double-it")
    (root / "notes-only").mkdir()
    (root / "notes-only" / "SKILL.md").write_text("---\nname: notes-only\ndescription: x\n---\n")
    with NothingRuns():
        found, rejected = ST.discover(root, scanner=clean_scanner, trust_of=trust({}))
        s = found.get("double-it")
        p = ST.plan(s, {"amount": 3}, taint=never_tainted) if s else None
        card = ST.describe(p) if p else ""
    check("a valid skill is discovered with nothing run and no socket", s is not None, repr(rejected))
    check("an instruction-only skill (no jarvis-tool.toml) is left to jarvis_skills",
          "notes-only" not in found and not any(f == "notes-only" for f, _ in rejected))
    check("a plan and its card are built with nothing run", bool(card) and not p.refused, p and p.refused)


def t_folder_rules():
    root = tmp()
    make_skill(root, "right-name", folder="wrong-folder")
    check("the name must match its folder (agentskills.io spec)",
          "must match its folder" in (rejected_reason(root, "wrong-folder") or ""))

    root = tmp()
    make_skill(root, "Upper", folder="Upper")
    check("an uppercase name is rejected", "a-z" in (rejected_reason(root, "Upper") or ""))

    root = tmp()
    cyr = "аbc"          # Cyrillic a: reads as "abc"
    make_skill(root, cyr, folder=cyr)
    check("a look-alike Unicode name is rejected (ASCII only, stricter than skills-ref)",
          rejected_reason(root, cyr) is not None)

    root = tmp()
    make_skill(root, "bin-inside", extra_files={"scripts/helper.exe": b"MZ\x00"})
    check("a non-text file (an .exe) in a code skill is rejected",
          "helper.exe" in (rejected_reason(root, "bin-inside") or ""))

    root = tmp()
    make_skill(root, "pyc-inside", extra_files={"scripts/__pycache__/x.py": "x=1"})
    check("compiled-Python folders are rejected (only source is on the card)",
          "__pycache__" in (rejected_reason(root, "pyc-inside") or ""))

    root = tmp()
    d = make_skill(root, "has-link")
    try:
        os.symlink("/etc/hostname", d / "scripts" / "linked.txt")
        check("a symlink inside a skill is rejected",
              "link" in (rejected_reason(root, "has-link") or ""))
    except (OSError, NotImplementedError) as exc:
        skip("a symlink inside a skill is rejected", f"cannot make a symlink here: {exc}")

    root = tmp()
    make_skill(root, "escapes", toml=DOUBLE_TOML.replace("scripts/run.py", "../other/run.py"))
    check("an entrypoint outside the folder is rejected",
          "leaves the skill folder" in (rejected_reason(root, "escapes") or ""))

    root = tmp()
    make_skill(root, "big-md", fm_extra="", description="x" * 1025)
    check("a description over 1024 characters is rejected",
          "1-1024" in (rejected_reason(root, "big-md") or ""))

    root = tmp()
    make_skill(root, "huge-code", py="x = 1\n" * 10000)
    check("more Python than fits on a card is rejected",
          "too long to read" in (rejected_reason(root, "huge-code") or ""))


def t_frontmatter_is_strict():
    cases = {
        "claims-trust": "trust: local\n",
        "claims-tier": "tier: auto\n",
        "anchor": "license: &a MIT\n",
        "block": "compatibility: |\n",
        "dupe": "license: MIT\nlicense: GPL\n",
    }
    root = tmp()
    for folder, extra in cases.items():
        make_skill(root, folder, fm_extra=extra)
    r = {f: rejected_reason(root, f) or "" for f in cases}
    check("a skill cannot claim its own trust in SKILL.md", "never read from a skill" in r["claims-trust"], r["claims-trust"])
    check("a skill cannot claim its own tier in SKILL.md", "never read from a skill" in r["claims-tier"], r["claims-tier"])
    check("YAML anchors are refused", "YAML feature" in r["anchor"], r["anchor"])
    check("YAML block text is refused", "YAML feature" in r["block"], r["block"])
    check("a duplicated key is refused, not last-one-wins", "twice" in r["dupe"], r["dupe"])

    root = tmp()
    make_skill(root, "tool-claims", toml='tier = "auto"\n' + DOUBLE_TOML)
    check("jarvis-tool.toml cannot set a tier either",
          "not a skill's to set" in (rejected_reason(root, "tool-claims") or ""))
    make_skill(root, "param-claims", toml=DOUBLE_TOML + 'trust = "local"\n')
    check("nor smuggle one into a parameter table",
          "unknown keys" in (rejected_reason(root, "param-claims") or ""))

    root = tmp()
    make_skill(root, "odd-effect", toml=DOUBLE_TOML.replace('["compute"]', '["harmless"]'))
    check("an effect outside the closed list is rejected",
          "not known" in (rejected_reason(root, "odd-effect") or ""))
    root = tmp()
    make_skill(root, "no-effect", toml=DOUBLE_TOML.replace('["compute"]', '[]'))
    check("an empty effects list is rejected (say what it does)",
          "non-empty" in (rejected_reason(root, "no-effect") or ""))


# ---------------------------------------------------------------- typing

def t_arguments_are_typed_strictly():
    root = tmp()
    toml = textwrap.dedent('''\
        entrypoint = "scripts/run.py"
        effects = ["compute"]
        [params.count]
        type = "integer"
        required = true
        minimum = 1
        maximum = 10
        [params.ratio]
        type = "number"
        [params.flag]
        type = "boolean"
        [params.tags]
        type = "string_list"
        max_items = 2
        max_length = 5
    ''')
    make_skill(root, "typed", toml=toml)
    s = load(root, "typed")
    ok = lambda a: ST.validate_args(s, a)[1]
    check("a whole number is accepted", ok({"count": 3}) == [])
    check('"5" is not an integer', ok({"count": "5"}) != [])
    check("5.0 is not an integer", ok({"count": 5.0}) != [])
    check("true is not an integer", ok({"count": True}) != [])
    check("true is not a number", ok({"count": 1, "ratio": True}) != [])
    check("NaN is not a number", ok({"count": 1, "ratio": float("nan")}) != [])
    check("infinity is not a number", ok({"count": 1, "ratio": float("inf")}) != [])
    check("1 is not a boolean", ok({"count": 1, "flag": 1}) != [])
    check("minimum is enforced", ok({"count": 0}) != [])
    check("maximum is enforced", ok({"count": 11}) != [])
    check("a missing required parameter is an error", ok({}) != [])
    check("an undeclared key is an error, not ignored", ok({"count": 1, "extra": 1}) != [])
    check("a list longer than max_items is an error", ok({"count": 1, "tags": ["a", "b", "c"]}) != [])
    check("a list item longer than max_length is an error", ok({"count": 1, "tags": ["abcdef"]}) != [])
    check("a non-object is an error", ok([1, 2]) != [])
    errs = ok({"count": "5"})
    check("the error tells the model what was expected, so it can retry",
          any("whole number" in e and "str" in e for e in errs), repr(errs))

    make_skill(root, "defaults")
    d = load(root, "defaults")
    clean, errs = ST.validate_args(d, {"amount": 2})
    check("a default is filled in, so the card shows everything the code gets",
          clean == {"amount": 2, "unit": "km"}, repr(clean))
    check("an enum value outside the list is refused",
          ST.validate_args(d, {"amount": 2, "unit": "furlong"})[1] != [])
    check("the model-facing schema forbids extra keys",
          d.schema()["additionalProperties"] is False and d.schema()["required"] == ["amount"])


# ---------------------------------------------------------------- tiers

NET_PY = "import urllib.request, json, sys\nprint(urllib.request.urlopen('https://example.com').read()[:10])\n"
EXEC_PY = "import sys\nexec(sys.stdin.read())\n"
UNKNOWN_PY = "import requests_toolbelt\n"
WRITE_PY = "import json, sys\nopen('out.txt', 'w').write('x')\n"
ALIAS_PY = "import os as o\no.system('calc')\n"
PATHOPEN_PY = "from pathlib import Path\nPath('x').open('w')\n"
OPEN_VALUE_PY = "f = open\nf('x', 'w')\n"
HANDLERS_PY = "from logging import handlers\n"


def t_tier_is_code_not_claims():
    root = tmp()
    make_skill(root, "net-hidden", py=NET_PY)                       # says compute
    make_skill(root, "net-said", py=NET_PY, toml=DOUBLE_TOML.replace('["compute"]', '["network"]'))
    make_skill(root, "exec-it", py=EXEC_PY)
    make_skill(root, "mystery", py=UNKNOWN_PY)
    make_skill(root, "writes", py=WRITE_PY)
    make_skill(root, "private-net", py=NET_PY,
               toml=DOUBLE_TOML.replace('["compute"]', '["private_data", "network"]'))
    make_skill(root, "plain")

    tp = lambda n: load(root, n, t="third_party")
    lo = lambda n: load(root, n, t="local")

    check("outside code that hides a network call is refused",
          "reach the internet" in tp("net-hidden").refused, tp("net-hidden").refused)
    check("outside code that DECLARES network is still refused",
          tp("net-said").refused != "")
    check("outside code using exec() is refused", tp("exec-it").refused != "")
    check("outside code importing something unrecognised is refused", tp("mystery").refused != "")
    check("outside code that understates its effects is refused",
          "also does" in tp("writes").refused, tp("writes").refused)
    check("private data + network is refused even for your own code",
          "Private data stays" in lo("private-net").refused, lo("private-net").refused)

    check("your own compute-only skill -> skill_run_local", lo("plain").action == ST.ACTION_LOCAL and not lo("plain").refused)
    check("your own networked skill -> skill_run_local_network (its own switch)",
          lo("net-hidden").action == ST.ACTION_LOCAL_NETWORK and not lo("net-hidden").refused)
    check("your own skill's undeclared write is added, not trusted away",
          "write_files" in lo("writes").effects_detected and not lo("writes").refused)
    check("outside compute-only code -> skill_run_untrusted", tp("plain").action == ST.ACTION_UNTRUSTED and not tp("plain").refused)
    check("a skill Jarvis wrote (trust self) is treated as outside code",
          load(root, "plain", t="self").action == ST.ACTION_UNTRUSTED)
    check("an unrecognised trust value is treated as third_party",
          load(root, "plain", t="bundled").trust == "third_party")

    for name, py, eff in [("alias", ALIAS_PY, "run_programs"), ("pathopen", PATHOPEN_PY, "write_files"),
                          ("openvalue", OPEN_VALUE_PY, "write_files"), ("handlers", HANDLERS_PY, "network")]:
        eff_found, _ = ST.detect_effects({"scripts/run.py": py})
        check(f"the scan sees {name} as {eff}", eff in eff_found, repr(eff_found))
    eff_found, _ = ST.detect_effects({"scripts/run.py": "import json, math\nprint(json.dumps(math.pi))\n"})
    check("plain json + math is seen as nothing", eff_found == set(), repr(eff_found))
    eff_found, _ = ST.detect_effects({"scripts/run.py": "from pathlib import Path\nPath('x').read_text()\n"})
    check("a read is seen as a read, not a write", eff_found == {"read_files"}, repr(eff_found))


def t_the_model_cannot_choose():
    root = tmp()
    make_skill(root, "plain")
    s = load(root, "plain", t="third_party")
    p = ST.plan(s, {"amount": 1, "tier": "auto", "action": ST.ACTION_LOCAL}, taint=never_tainted)
    check("an argument named tier/action is an error, never a setting",
          p.refused and any("tier" in e for e in p.errors), repr(p.errors))
    a = ST.plan(s, {"amount": 1}, taint=never_tainted).action
    b = ST.plan(s, {"amount": 999}, taint=never_tainted).action
    check("the action does not depend on the arguments", a == b == ST.ACTION_UNTRUSTED)
    import inspect
    params = set(inspect.signature(ST.plan).parameters)
    check("plan() takes no tier, trust or action from anyone", params == {"skill", "args", "taint"}, repr(params))


def t_scanner_is_required():
    root = tmp()
    make_skill(root, "plain")
    check("no scanner available -> refused (fails closed)",
          "not available" in load(root, "plain", scanner=None).refused if ST._default_scanner() is None else True)
    blocked = load(root, "plain", scanner=lambda t, l: [Finding("block", "curl | bash")] if l == "SKILL.md" else [])
    check("a scanner block refuses the skill", "curl | bash" in blocked.refused, blocked.refused)
    warned = load(root, "plain", scanner=lambda t, l: [Finding("warn", "mentions sudo")] if l == "SKILL.md" else [])
    card = ST.describe(ST.plan(warned, {"amount": 1}, taint=never_tainted))
    check("a scanner warning goes on the card", "mentions sudo" in card and not warned.refused)
    raising = load(root, "plain", scanner=lambda t, l: 1 / 0)
    check("a scanner that crashes refuses rather than passes", raising.refused != "")


def t_taint_blocks_reaching_out():
    root = tmp()
    make_skill(root, "net", py=NET_PY)
    s = load(root, "net", t="local")
    check("a networked skill is not offered while the conversation is tainted",
          ST.plan(s, {"amount": 1}, taint=lambda: True).refused != "")
    check("...nor when taint cannot be checked",
          ST.plan(s, {"amount": 1}, taint=lambda: None).refused != "")
    check("...and is offered when it is clear",
          ST.plan(s, {"amount": 1}, taint=never_tainted).refused == "")
    make_skill(root, "plain")
    check("a compute skill does not care about taint (it goes nowhere)",
          ST.plan(load(root, "plain"), {"amount": 1}, taint=lambda: True).refused == "")


# ---------------------------------------------------------------- the card

def t_the_card_shows_everything():
    root = tmp()
    make_skill(root, "plain", fm_extra="allowed-tools: Bash(git:*) Read\n")
    s = load(root, "plain", t="third_party")
    p = ST.plan(s, {"amount": 7}, taint=never_tainted)
    card = ST.describe(p)
    check("the exact input is on the card", '"amount": 7' in card and '"unit": "km"' in card)
    check("the whole source of what runs is on the card", DOUBLE_PY.strip() in card)
    check("every file's fingerprint is on the card", all(h in card for h in p.files.values()) and len(p.files) == 3)
    check("the card says what it cannot promise", "cannot stop it" in card)
    check("the card says what refusing costs", "If you say no:" in card)
    check("allowed-tools is shown and explicitly ignored", "never pre-approves" in card and "Bash(git:*)" in card)
    check("who wrote it is on the card", "came from outside" in card)
    check("the input sent is exactly the input shown", json.loads(p.input_json) == {"amount": 7, "unit": "km"})


# ---------------------------------------------------------------- run

def t_only_a_persons_yes_runs_it():
    root = tmp()
    make_skill(root, "plain")
    s = load(root, "plain")
    p = ST.plan(s, {"amount": 2}, taint=never_tainted)
    cases = [
        ("no verdict at all", None),
        ("tier auto (nobody asked)", V(tier="auto", outcome="auto")),
        ("tier notify (told after)", V(tier="notify", outcome="notify")),
        ("timed out", V(allowed=False, outcome="timed_out", reason="nobody answered")),
        ("denied", V(allowed=False, outcome="denied", reason="denied by a human")),
        ("an approval for a different action", V(action="send_email")),
        ("ask, but outcome not approved", V(outcome="auto")),
        ("a bare object with allowed=True only", SimpleNamespace(allowed=True)),
    ]
    for label, v in cases:
        rec = Recorder()
        out = ST.run(p, v, spawn=rec, taint=never_tainted)
        check(f"does not run: {label}", not rec.calls and not out["ran"] and not out["ok"], repr(out))
    rec = Recorder()
    out = ST.run(p, V(), spawn=rec, taint=never_tainted)
    check("runs: tier ask, approved by a person", len(rec.calls) == 1 and out["ran"], repr(out))
    rec = Recorder()
    out = ST.run(p, V(action="unclassified_tool"), spawn=rec, taint=never_tainted)
    check("runs: approved under the gate's unclassified_tool name (still ask)", len(rec.calls) == 1)
    msg = ST.run(p, V(tier="auto", outcome="auto"), spawn=Recorder(), taint=never_tainted)["error"]
    check("the auto-tier refusal tells the owner which toml line to change",
          "skill_run_local" in msg and '"ask"' in msg, msg)
    argv = rec.calls[0][0]
    check("argv is a list with no shell and the entrypoint last",
          isinstance(argv, list) and argv[-1].endswith("run.py") and "-E" in argv and "-s" in argv)
    check("result is marked as untrusted output", out.get("untrusted_output") is True)


def t_a_file_changed_after_the_scan_is_not_offered():
    root = tmp()
    d = make_skill(root, "plain")
    s = load(root, "plain", t="third_party")          # scanned: compute only
    (d / "scripts" / "run.py").write_text("import socket\n")
    p = ST.plan(s, {"amount": 1}, taint=never_tainted)
    check("an edit between the scan and the plan -> refused, not re-shown",
          "changed since it was scanned" in p.refused, p.refused)
    check("the card never shows bytes the scan did not read", "import socket" not in ST.describe(p))


def t_a_changed_file_never_runs():
    root = tmp()
    d = make_skill(root, "plain")
    s = load(root, "plain")
    p = ST.plan(s, {"amount": 2}, taint=never_tainted)
    (d / "scripts" / "run.py").write_text(DOUBLE_PY + "\nimport os\nos.system('calc')\n")
    rec = Recorder()
    out = ST.run(p, V(), spawn=rec, taint=never_tainted)
    check("an edited file after the card -> refused", not rec.calls and "changed" in out["error"], repr(out))
    d2 = make_skill(tmp(), "plain")
    p2 = ST.plan(ST.load_skill(d2, scanner=clean_scanner, trust_of=trust({"plain": "local"})),
                 {"amount": 2}, taint=never_tainted)
    (d2 / "scripts" / "extra.py").write_text("x = 1\n")
    rec = Recorder()
    out = ST.run(p2, V(), spawn=rec, taint=never_tainted)
    check("an added file after the card -> refused", not rec.calls and "extra.py" in out["error"], repr(out))


def t_real_child_process():
    root = tmp()
    make_skill(root, "plain")
    s = load(root, "plain")
    p = ST.plan(s, {"amount": 21}, taint=never_tainted)
    out = ST.run(p, V(), taint=never_tainted)
    check("a real run gets the typed input on stdin and returns JSON",
          out["ok"] and out["output"] == {"doubled": 42, "unit": "km"}, repr(out))

    env_py = ("import json, os\nprint(json.dumps(sorted(k for k in os.environ "
              "if 'TOKEN' in k.upper() or 'KEY' in k.upper() or 'PASS' in k.upper())))\n")
    make_skill(root, "env-peek", py=env_py)
    os.environ["JARVIS_GITHUB_TOKEN"] = "ghp_should_never_arrive"
    os.environ["HUD_TOKEN"] = "hud_should_never_arrive"
    os.environ["JARVIS_IMAP_PASSWORD"] = "pw_should_never_arrive"
    try:
        out = ST.run(ST.plan(load(root, "env-peek"), {"amount": 1}, taint=never_tainted), V(), taint=never_tainted)
    finally:
        for k in ("JARVIS_GITHUB_TOKEN", "HUD_TOKEN", "JARVIS_IMAP_PASSWORD"):
            os.environ.pop(k, None)
    check("the child sees no token, key or password variables", out["ok"] and out["output"] == [], repr(out))

    slow = DOUBLE_TOML.replace("timeout_seconds = 10", "timeout_seconds = 1")
    make_skill(root, "slow", py="import time\ntime.sleep(30)\n", toml=slow)
    out = ST.run(ST.plan(load(root, "slow"), {"amount": 1}, taint=never_tainted), V(), taint=never_tainted)
    check("a skill past its time limit is stopped and reported", out["timed_out"] and not out["ok"], repr(out))

    make_skill(root, "loud", py="import sys\nsys.stdout.write('x' * 1000000)\n")
    out = ST.run(ST.plan(load(root, "loud"), {"amount": 1}, taint=never_tainted), V(), taint=never_tainted)
    check("output past the cap is cut and says so",
          out["output_truncated"] and len(out["output"]) == ST.OUTPUT_MAX_BYTES, repr({k: v for k, v in out.items() if k != "output"}))

    sib = "from helper import twice\nimport json, sys\nprint(json.dumps(twice(json.load(sys.stdin)['amount'])))\n"
    make_skill(root, "sibling", py=sib, extra_files={"scripts/helper.py": "def twice(x):\n    return 2 * x\n"})
    out = ST.run(ST.plan(load(root, "sibling"), {"amount": 4}, taint=never_tainted), V(), taint=never_tainted)
    check("a skill can import its own sibling file", out["ok"] and out["output"] == 8, repr(out))


def t_invoke_asks_every_time():
    root = tmp()
    make_skill(root, "plain")
    s = load(root, "plain")
    asked = []

    def gate(action, detail, prompt):
        asked.append((action, detail["text"]))
        return V()
    rec = Recorder()
    ST.invoke(s, {"amount": 1}, gate_check=gate, spawn=rec, taint=never_tainted)
    ST.invoke(s, {"amount": 1}, gate_check=gate, spawn=rec, taint=never_tainted)
    check("two uses, two questions - nothing is remembered as a grant", len(asked) == 2 and len(rec.calls) == 2)
    check("the gate is asked about the computed action, with the full card",
          asked[0][0] == ST.ACTION_LOCAL and DOUBLE_PY.strip() in asked[0][1])
    asked.clear()
    out = ST.invoke(s, {"amount": "lots"}, gate_check=gate, spawn=rec, taint=never_tainted)
    check("a refused plan never reaches the approval queue", asked == [] and not out["ran"])
    out = ST.invoke(s, {"amount": 1}, gate_check=None, spawn=Recorder(), taint=never_tainted)
    check("with no jarvis_gate importable, invoke refuses", not out["ran"] and "refused" in out["error"], repr(out))


def _code_only(text):
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant):
                node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def t_no_standing_grant_in_code():
    code = _code_only((HERE / "jarvis_skill_tools.py").read_text(encoding="utf-8"))
    banned = ["approve_all", "approveAll", "allow_all", "allowAll", "yolo", "autoApprove",
              "bypass_approvals", "always_allow", "remember_approval", "approved=True"]
    found = [b for b in banned if b in code]
    check("no blanket-grant identifier exists in the code (comments stripped)", not found, repr(found))
    import inspect
    check("run() has no `approved` flag to pass", "approved" not in inspect.signature(ST.run).parameters)


# ---------------------------------------------------------------- jarvis_agent

def _apply_unified(src_text, diff_text):
    """Minimal applier for the one-hunk diff shipped beside this test."""
    old, new, in_hunk = [], [], False
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk or line.startswith(("---", "+++")):
            continue
        if line.startswith("+"):
            new.append(line[1:])
        elif line.startswith("-"):
            old.append(line[1:])
        else:
            old.append(line[1:])
            new.append(line[1:])
    o, n = "".join(old), "".join(new)
    assert src_text.count(o) == 1, "diff context not found exactly once"
    return src_text.replace(o, n)


def _load_agent(patched):
    src = (REPO_BACKEND / "jarvis_agent.py").read_text(encoding="utf-8")
    if patched:
        src = _apply_unified(src, (HERE / "jarvis_agent-verdict.diff").read_text(encoding="utf-8"))
    d = tmp()
    (d / "jarvis_agent.py").write_text(src, encoding="utf-8")
    sys.modules.pop("jarvis_agent", None)
    sys.path.insert(0, str(d))
    try:
        import jarvis_agent
        return jarvis_agent
    finally:
        sys.path.remove(str(d))


class FakeStream:
    def __init__(self, chunks):
        self._c = list(chunks) + [b""]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, _n=1024):
        return self._c.pop(0) if self._c else b""


def _turn(AG, tools, verdict, args):
    AG.TOOLS.update(tools)
    name = next(iter(tools))
    replies = [
        {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "function": {"name": name, "arguments": json.dumps(args)}}]}}]},
        {"choices": [{"message": {"role": "assistant", "content": "done"}}]},
    ]
    seen = []

    def post(url, payload):
        seen.append(payload)
        return replies.pop(0)
    gates = []

    def gate(action, detail, prompt):
        gates.append(action)
        return verdict
    out = []
    AG.run_local_turn([{"role": "user", "content": "go"}], "m", ollama_url="http://127.0.0.1:11434",
                      stream_out=out.append, enabled_tools={name}, post=post, gate_check=gate,
                      open_stream=lambda u, p: FakeStream([b"ok"]))
    tool_msgs = [m for m in seen[-1]["messages"] if m.get("role") == "tool"]
    return gates, json.loads(tool_msgs[0]["content"]) if tool_msgs else None, seen


def t_wired_into_the_real_agent_loop():
    if not (REPO_BACKEND / "jarvis_agent.py").is_file():
        skip("jarvis_agent integration", f"no {REPO_BACKEND / 'jarvis_agent.py'}")
        return
    root = tmp()
    make_skill(root, "plain")
    common = dict(scanner=clean_scanner, trust_of=trust({"plain": "local"}), taint=never_tainted)

    AG = _load_agent(patched=False)
    rec = Recorder()
    tools = ST.agent_tools(root, spawn=rec, **common)
    gates, result, seen = _turn(AG, tools, V(), {"amount": 2})
    check("UNPATCHED jarvis_agent: approved call still refused (no verdict hand-off)",
          not rec.calls and result and "no approval reached" in result.get("error", ""), repr(result))
    schema = [t for t in seen[0]["tools"] if t["function"]["name"] == "skill__plain"]
    check("the model is offered the typed schema with no extra keys allowed",
          schema and schema[0]["function"]["parameters"]["additionalProperties"] is False)

    AG = _load_agent(patched=True)
    rec = Recorder()
    tools = ST.agent_tools(root, spawn=rec, **common)
    gates, result, _ = _turn(AG, tools, V(tier="auto", outcome="auto"), {"amount": 2})
    check("PATCHED jarvis_agent: tier auto -> the skill does not run", not rec.calls and not result["ran"], repr(result))
    gates, result, _ = _turn(AG, tools, V(), {"amount": 2})
    check("PATCHED jarvis_agent: an approved ask runs it, once", len(rec.calls) == 1 and result["ran"], repr(result))
    check("jarvis_agent asked the gate about the computed action", gates == [ST.ACTION_LOCAL], repr(gates))
    gates, result, _ = _turn(AG, tools, V(), {"amount": "two"})
    check("PATCHED jarvis_agent: a badly typed call raises no card and runs nothing",
          gates == [] and len(rec.calls) == 1 and "could not accept" in result.get("error", ""), repr(result))
    sys.modules.pop("jarvis_agent", None)


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("t_") and callable(v)]
    for t in tests:
        try:
            t()
        except Exception:
            FAILED.append(t.__name__)
            print(f"FAIL  {t.__name__} raised\n{traceback.format_exc()}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
