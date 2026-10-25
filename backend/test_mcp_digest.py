"""jarvis_mcp.py - the SHA-256 digest of each server's `tools/list`.

The start card remembers a 32-byte digest of the tools a server listed, so a
server whose tool list changes later asks again. Only the hex digest is
written down: never the tools/list text, a tool name or a description.

    python -B backend/test_mcp_digest.py

Every check drives the real fake server and reads what the bridge did, so
nothing here pins the module's source text.
"""
import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_mcp.py")
import jarvis_mcp as M  # noqa: E402

FAKE = str(HERE / "fake_mcp_server.py")
TMP = tempfile.mkdtemp(prefix="mcp-digest-test-")
SHA256_HEX = re.compile(r"\A[0-9a-f]{64}\Z")
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class V:
    """Shaped like jarvis_gate.Verdict after gate-outcome.patch."""

    def __init__(self, allowed, tier, action, outcome, request_id=None, reason=""):
        self.allowed, self.tier, self.action = allowed, tier, action
        self.outcome, self.request_id, self.reason = outcome, request_id, reason


class Gate:
    """Records every card. `mode` decides the answer."""

    def __init__(self, mode="approve"):
        self.mode, self.calls, self.n = mode, [], 0

    def __call__(self, action, detail, prompt=""):
        self.calls.append((action, detail, prompt))
        self.n += 1
        if self.mode == "approve":
            return V(True, "ask", action, "approved", request_id=f"r{self.n}")
        return V(False, "ask", action, "denied", request_id=f"r{self.n}",
                 reason="denied by a human")


def section(*extra):
    return {"enabled": True, "servers": {"fake": {
        "command": sys.executable, "args": [FAKE, *extra],
        "tools": {}, "env": {},
        "timeout_sec": 5, "start_timeout_sec": 10}}}


def bridge(store, gate, *extra):
    servers = M.parse_config(section(*extra))
    return M.Bridge(servers, gate_check=gate, work_root=TMP, approvals=store)


def const_fingerprint(*_args, **_kwargs):
    """A fixed fingerprint, so a test changes ONE thing: the tools/list."""
    return "sha256:" + "f" * 64


def t_the_digest_is_stored_and_no_tool_text_is():
    store = M.ApprovalStore(os.path.join(TMP, "digest-a.json"))
    g = Gate()
    b = bridge(store, g)
    res = b.start("fake")
    b.shutdown()
    got = store.get("fake") or {}
    check("a new server asks once, and the yes is remembered", res["ok"] and len(g.calls) == 1,
          (res, g.calls))
    sha = got.get("tools_sha")
    check("the approval stores a 64-character lowercase hex SHA-256 digest",
          isinstance(sha, str) and SHA256_HEX.match(sha) is not None, got)
    raw = open(store.path, encoding="utf-8").read()
    check("no tools/list text is stored - no tool name, description or schema",
          "echo" not in raw and "Echo text back" not in raw and "inputSchema" not in raw, raw)

    digest = getattr(M, "tools_digest", None)
    check("the module can digest a tools/list result", callable(digest))
    if callable(digest):
        one = digest([{"name": "x", "description": "one"},
                      {"name": "y", "description": "two"}])
        reordered = digest([{"name": "y", "description": "two"},
                            {"name": "x", "description": "one"}])
        check("the same tools in another order are the same digest", one == reordered,
              (one, reordered))
        check("a changed tool definition is a different digest",
              one != digest([{"name": "x", "description": "changed"},
                             {"name": "y", "description": "two"}]))


def t_the_same_tools_need_no_card():
    store = M.ApprovalStore(os.path.join(TMP, "digest-b.json"))
    real = M.fingerprint_of
    M.fingerprint_of = const_fingerprint
    try:
        g = Gate()
        b = bridge(store, g)
        b.start("fake")
        b.shutdown()
        first = (store.get("fake") or {}).get("tools_sha")
        check("the first start records the digest it saw",
              isinstance(first, str) and SHA256_HEX.match(first) is not None, first)

        g = Gate()
        b = bridge(store, g)
        res = b.start("fake")
        b.shutdown()
        check("the same tools/list later: started with no card",
              res["ok"] and res.get("remembered") and g.calls == [], (res, g.calls))
    finally:
        M.fingerprint_of = real


def t_a_changed_tools_list_asks_again():
    store = M.ApprovalStore(os.path.join(TMP, "digest-c.json"))
    real = M.fingerprint_of
    M.fingerprint_of = const_fingerprint
    try:
        b = bridge(store, Gate())
        b.start("fake")
        b.shutdown()
        first = (store.get("fake") or {}).get("tools_sha")

        # --desc-v2 changes one tool's description. The fingerprint is held
        # constant above, so the only thing that changed is tools/list.
        g = Gate()
        b = bridge(store, g, "--desc-v2")
        res = b.start("fake")
        b.shutdown()
        card = g.calls[0][1]["text"] if g.calls else ""
        check("a changed tools/list asks again", res["ok"] and len(g.calls) == 1,
              (res, g.calls))
        check("and the card says the list of tools changed", "list of tools" in card, card)
        second = (store.get("fake") or {}).get("tools_sha")
        check("the newly approved digest is what is remembered now",
              isinstance(second, str) and SHA256_HEX.match(second) is not None
              and second != first, (first, second))
    finally:
        M.fingerprint_of = real


def t_a_refused_change_is_not_written_down():
    store = M.ApprovalStore(os.path.join(TMP, "digest-d.json"))
    real = M.fingerprint_of
    M.fingerprint_of = const_fingerprint
    try:
        b = bridge(store, Gate())
        b.start("fake")
        b.shutdown()
        before = (store.get("fake") or {}).get("tools_sha")

        g = Gate("deny")
        b = bridge(store, g, "--desc-v2")
        res = b.start("fake")
        check("a refused change leaves the server stopped", b.running() == [], b.running())
        b.shutdown()
        after = store.get("fake")
        check("a refused tools/list change is not written down as approved",
              not res["ok"] and len(g.calls) == 1
              and (after is None or after.get("tools_sha") == before),
              (res, before, after))
    finally:
        M.fingerprint_of = real


def t_a_server_never_approved_gets_a_first_card():
    store = M.ApprovalStore(os.path.join(TMP, "digest-e.json"))
    g = Gate()
    b = bridge(store, g)
    res = b.start("fake")
    b.shutdown()
    check("a server with no stored digest asks (first approval)",
          res["ok"] and len(g.calls) == 1, (res, g.calls))
    check("... and that first yes records a digest, so the next start can compare",
          SHA256_HEX.match((store.get("fake") or {}).get("tools_sha") or "") is not None,
          store.get("fake"))


def t_a_missing_or_malformed_digest_fails_safe():
    real = M.fingerprint_of
    M.fingerprint_of = const_fingerprint
    try:
        for label, record in (
                ("missing", {"fingerprint": const_fingerprint(), "version": "1.0"}),
                ("malformed", {"fingerprint": const_fingerprint(), "version": "1.0",
                               "tools_sha": "not-a-digest"})):
            path = os.path.join(TMP, f"digest-f-{label}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"fake": record}, f)
            store = M.ApprovalStore(path)
            g = Gate()
            b = bridge(store, g)
            res = b.start("fake")
            b.shutdown()
            check(f"a {label} digest in an approval record asks again (fails safe)",
                  res["ok"] and len(g.calls) == 1, (res, g.calls))
            check(f"... and the new yes replaces the {label} digest with a real one",
                  SHA256_HEX.match((store.get("fake") or {}).get("tools_sha") or "") is not None,
                  store.get("fake"))
    finally:
        M.fingerprint_of = real


if __name__ == "__main__":
    for fn in (t_the_digest_is_stored_and_no_tool_text_is,
               t_the_same_tools_need_no_card,
               t_a_changed_tools_list_asks_again,
               t_a_refused_change_is_not_written_down,
               t_a_server_never_approved_gets_a_first_card,
               t_a_missing_or_malformed_digest_fails_safe):
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
