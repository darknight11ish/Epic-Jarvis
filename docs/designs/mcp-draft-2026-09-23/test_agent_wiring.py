"""jarvis-agent-mcp.patch - an MCP tool, driven by the real jarvis_agent loop.

Takes jarvis_agent.py from the repository (read-only; it is copied), and
runs `run_local_turn` twice with a scripted model asking for an MCP tool:

  * UNPATCHED: the call must be REFUSED. jarvis_gate.action_for_tool folds
    the MCP action into "unclassified_tool", and the verdict never reaches
    jarvis_mcp.run(), which therefore fails closed. This is the control: it
    proves the patch is needed and that the unpatched path is safe.
  * PATCHED: the gate is asked about "mcp__fake__echo" by name, the verdict
    reaches run(), and the tool runs once.

    python3 test_agent_wiring.py [path/to/Epic-Jarvis/backend/jarvis_agent.py]
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_mcp as M          # noqa: E402
import test_mcp as T            # noqa: E402  (fixtures only)

AGENT = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    HERE / "jarvis_agent.py" if (HERE / "jarvis_agent.py").exists()
    else Path("/home/user/Epic-Jarvis/backend/jarvis_agent.py"))
PATCH = HERE / "jarvis-agent-mcp.patch"
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def load_agent(patched: bool):
    d = tempfile.mkdtemp(prefix="agent-")
    shutil.copy(AGENT, os.path.join(d, "jarvis_agent.py"))
    if patched:
        # git apply works outside a repository, and the owner has git.
        r = subprocess.run(["git", "apply", str(PATCH)], cwd=d,
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("patch did not apply: " + r.stdout + r.stderr)
    spec = importlib.util.spec_from_file_location(f"jarvis_agent_{patched}",
                                                  os.path.join(d, "jarvis_agent.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake_gate_module():
    """Stands in for jarvis_gate's action_for_tool: a static table, and
    anything unknown becomes "unclassified_tool" (backend/README.md, the
    `github_search` section, and jarvis_agent.py's Tool docstring)."""
    g = types.ModuleType("jarvis_gate")
    g.action_for_tool = lambda name, args: (
        {"calculator": "calculator"}.get(name, "unclassified_tool"), None)
    return g


class Stream:
    def __init__(self):
        self.buf = b"final answer"
        self.pos = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n):
        chunk, self.pos = self.buf[self.pos:self.pos + n], self.pos + n
        return chunk


def drive(agent, bridge, gate):
    agent.TOOLS.update(M.agent_tools(bridge, agent.Tool))
    rounds = iter([
        {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "mcp_fake__echo", "arguments": json.dumps({"text": "hi"})}}]}}]},
        {"choices": [{"message": {"role": "assistant", "content": "done"}}]},
    ])
    seen_convo = []

    def post(url, payload):
        seen_convo.append(list(payload["messages"]))
        return next(rounds)
    out = []
    agent.run_local_turn([{"role": "user", "content": "echo hi"}], "m", ollama_url="http://127.0.0.1:11434",
                         stream_out=out.append, enabled_tools={"mcp_fake__echo"},
                         post=post, gate_check=gate, open_stream=lambda u, p: Stream())
    tool_msgs = [m for m in seen_convo[-1] if m.get("role") == "tool"]
    return json.loads(tool_msgs[0]["content"]) if tool_msgs else None


def t_unpatched_refuses_and_patched_runs():
    sys.modules["jarvis_gate"] = fake_gate_module()
    try:
        for patched in (False, True):
            agent = load_agent(patched)
            gate = T.Gate("approve")
            b = T.bridge(gate=gate, tools=T.tools("echo"))
            b.start("fake")
            start_calls = len(gate.calls)
            result = drive(agent, b, gate)
            asked = [c[0] for c in gate.calls[start_calls:]]
            label = "patched" if patched else "UNPATCHED"
            if not patched:
                check(f"{label}: the gate is asked about 'unclassified_tool', not the MCP tool",
                      asked == ["unclassified_tool"], asked)
                check(f"{label}: and the call is refused, not run",
                      result and result.get("ok") is False, result)
            else:
                check(f"{label}: the gate is asked about mcp__fake__echo by name",
                      asked == ["mcp__fake__echo"], asked)
                check(f"{label}: the card it saw prints the arguments in full",
                      '"text": "hi"' in gate.calls[start_calls][1]["text"],
                      gate.calls[start_calls][1])
                check(f"{label}: the verdict reached run() and the tool ran",
                      result and result.get("ok") and result.get("content") == "echo: hi", result)
                check(f"{label}: and the model was told it is untrusted",
                      result and result.get("untrusted") is True, result)
            b.shutdown()
        # Tier notify on an ask-floor tool, through the patched loop: refused.
        agent = load_agent(True)
        gate = T.Gate(lambda a: "approve" if a.startswith("mcp_start__") else "notify")
        b = T.bridge(gate=gate, tools=T.tools("echo"))
        b.start("fake")
        result = drive(agent, b, gate)
        check("patched: a notify-tier verdict on an ask-floor tool is still refused",
              result and result.get("ok") is False and "ask" in result.get("error", ""), result)
        b.shutdown()
    finally:
        sys.modules.pop("jarvis_gate", None)


if __name__ == "__main__":
    for fn in (t_unpatched_refuses_and_patched_runs,):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)
