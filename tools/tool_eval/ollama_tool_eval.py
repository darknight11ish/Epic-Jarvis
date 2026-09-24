"""Measure how well a local model picks and fills Jarvis's tools. Standard library only.

Sends each test sentence to Ollama the SAME way Jarvis does
(POST /v1/chat/completions, tools = Jarvis's real tool list, reasoning_effort
"none"), once per model, and counts:

  right_tool    the tool it picked is the one expected (or: no tool, when none fits)
  args_ok       the arguments pass the tool's own schema (required fields, types, enums)
  false_call    it called a tool for a sentence that needed none
  crash         Ollama answered with an error (e.g. a tool call it could not parse)
  fixed_by_retry  with --repair: a wrong/invalid call became right after ONE
                  retry that tells the model exactly what was wrong

Nothing is run: tool calls are only read and scored. Nothing leaves this PC:
the script only talks to the Ollama address given (default 127.0.0.1:11434).

Run on the PC (one line; results print on screen and are saved next to the
script as tool_eval_results.json):
  py -3 ollama_tool_eval.py --models qwen3:8b qwen3.5:9b qwen3.5:4b --repair

Self-test with a fake Ollama (no model needed):
  python3 ollama_tool_eval.py --selftest
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from jarvis_tool_cases import CASES, HELD_OUT  # noqa: E402



def _live_tools():
    """Jarvis's real tool list, read from backend/jarvis_agent.py in this
    repository, so the test never drifts from what Jarvis offers. The
    browser tool is left out (it is off until the second card is in). Falls
    back to the saved copy in jarvis_tools.json when the backend cannot be
    imported."""
    repo = os.path.dirname(os.path.dirname(HERE))
    for sub in ("backend", os.path.join("backend", "rebuilt")):
        sys.path.insert(0, os.path.join(repo, sub))
    sys.dont_write_bytecode = True
    try:
        import jarvis_agent
        out = [t.schema() if callable(getattr(t, "schema", None)) else t.schema
               for n, t in jarvis_agent.TOOLS.items() if n != "browser_control"]
        if out and all(isinstance(x, dict) and "function" in x for x in out):
            return out
    except Exception:
        pass
    return json.load(open(os.path.join(HERE, "jarvis_tools.json"), encoding="utf-8"))


TOOLS = _live_tools()
BY_NAME = {t["function"]["name"]: t for t in TOOLS}
SYSTEM = ("You are Jarvis, a private assistant running on this PC. Use a tool only when "
          "the request needs one; otherwise just answer.")
_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool,
          "array": list, "object": dict}


def check_args(name, args):
    """Problems with `args` against the tool's schema, as plain sentences. [] = fine."""
    tool = BY_NAME.get(name)
    if tool is None:
        return [f"there is no tool called {name!r}; the tools are: {', '.join(BY_NAME)}"]
    if not isinstance(args, dict):
        return ["the arguments must be a JSON object"]
    params = tool["function"]["parameters"]
    props = params.get("properties", {})
    out = []
    for req in params.get("required", []):
        if req not in args or args[req] in ("", None, []):
            out.append(f"{req!r} is required")
    for key, val in args.items():
        spec = props.get(key)
        if spec is None:
            out.append(f"{key!r} is not an argument of {name}; allowed: {', '.join(props)}")
            continue
        want = _TYPES.get(spec.get("type"))
        if want and (not isinstance(val, want) or (spec.get("type") in ("integer", "number")
                                                     and isinstance(val, bool))):
            out.append(f"{key!r} must be a {spec.get('type')}")
        if "enum" in spec and val not in spec["enum"]:
            out.append(f"{key!r} must be one of {spec['enum']}")
    return out


def post(url, body, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    # No proxy, ever: this is a loopback address.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ask(base, model, messages):
    body = {"model": model, "messages": messages, "tools": TOOLS, "stream": False,
            "temperature": 0.7, "top_p": 0.8, "max_tokens": 512, "reasoning_effort": "none"}
    t0 = time.time()
    try:
        resp = post(f"{base}/v1/chat/completions", body)
    except urllib.error.HTTPError as exc:
        return {"crash": exc.read().decode("utf-8", "replace")[:300], "secs": time.time() - t0}
    msg = (resp.get("choices") or [{}])[0].get("message") or {}
    calls = []
    for c in msg.get("tool_calls") or []:
        fn = c.get("function") or {}
        raw = fn.get("arguments")
        try:
            args = raw if isinstance(raw, dict) else json.loads(raw or "{}")
            bad_json = None
        except ValueError as exc:
            args, bad_json = None, str(exc)
        calls.append({"name": fn.get("name", ""), "args": args, "bad_json": bad_json,
                      "id": c.get("id", "")})
    return {"content": msg.get("content") or "", "calls": calls, "secs": time.time() - t0}


def score(expected, required, r):
    if "crash" in r:
        return {"right_tool": False, "args_ok": False, "false_call": False, "crash": True}
    call = r["calls"][0] if r["calls"] else None
    if expected is None:
        return {"right_tool": call is None, "args_ok": True, "false_call": call is not None,
                "crash": False}
    right = call is not None and call["name"] == expected
    ok = right and call["bad_json"] is None and not check_args(call["name"], call["args"])
    for k, typ in required.items():
        ok = ok and isinstance((call["args"] or {}).get(k), typ)
    return {"right_tool": right, "args_ok": ok, "false_call": False, "crash": False}


def repair_messages(utt, r):
    """The one retry: tell the model exactly what was wrong (the pattern
    recommended for jarvis_agent._one_call)."""
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": utt}]
    if "crash" in r:
        msgs.append({"role": "system", "content":
                     "Your last tool call could not be read (it was not valid JSON). "
                     "If a tool is needed, call it again with valid JSON arguments."})
        return msgs
    call = r["calls"][0]
    problems = ([f"the arguments were not valid JSON ({call['bad_json']})"] if call["bad_json"]
                else check_args(call["name"], call["args"]))
    msgs.append({"role": "assistant", "content": r["content"], "tool_calls": [{
        "id": call["id"] or "call_0", "type": "function",
        "function": {"name": call["name"], "arguments": json.dumps(call["args"] or {})}}]})
    msgs.append({"role": "tool", "tool_call_id": call["id"] or "call_0", "content": json.dumps(
        {"ok": False, "error": "Nothing ran. Fix and call again: " + "; ".join(problems)})})
    return msgs


def run(base, models, repair, cases):
    results = {}
    for model in models:
        rows = []
        for utt, expected, required in cases:
            r = ask(base, model, [{"role": "system", "content": SYSTEM},
                                  {"role": "user", "content": utt}])
            s = score(expected, required, r)
            s["fixed_by_retry"] = False
            needs_fix = expected is not None and (s["crash"] or (r.get("calls") and not s["args_ok"]))
            if repair and needs_fix:
                r2 = ask(base, model, repair_messages(utt, r))
                s2 = score(expected, required, r2)
                s["fixed_by_retry"] = s2["args_ok"]
            picked = [c["name"] for c in r.get("calls", [])]
            rows.append({"utt": utt, "expected": expected, "picked": picked,
                         "secs": round(r["secs"], 2), **s})
        n = len(rows)
        tot = {k: sum(1 for x in rows if x[k]) for k in
               ("right_tool", "args_ok", "false_call", "crash", "fixed_by_retry")}
        n_none = sum(1 for x in rows if x["expected"] is None)
        print(f"\n{model}: right tool {tot['right_tool']}/{n}, args ok {tot['args_ok']}/{n - n_none}"
              f" (+{tot['fixed_by_retry']} after one retry), false calls {tot['false_call']}/{n_none},"
              f" crashes {tot['crash']}, median {sorted(x['secs'] for x in rows)[n // 2]} s")
        for x in rows:
            if not (x["right_tool"] and x["args_ok"]):
                print(f"   miss: expected {x['expected']}, got {x['picked'] or 'no tool'} <- {x['utt']!r}")
        results[model] = rows
    return results


def selftest():
    """A scripted fake Ollama: proves the scoring and the retry path, not any model."""
    import http.server
    import threading

    class Fake(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            user = body["messages"][1]["content"]
            retry = len(body["messages"]) > 2
            if "joke" in user:
                msg = {"role": "assistant", "content": "Why did the cat..."}
            elif "percent" in user:
                msg = {"tool_calls": [{"id": "a", "function": {
                    "name": "calculator", "arguments": '{"expression": "0.175*2340"}'}}]}
            elif "schedule" in user and not retry:          # wrong type, fixed on retry
                msg = {"tool_calls": [{"id": "b", "function": {
                    "name": "calendar_read", "arguments": '{"days_ahead": "one"}'}}]}
            elif "schedule" in user:
                msg = {"tool_calls": [{"id": "b", "function": {
                    "name": "calendar_read", "arguments": '{"days_ahead": 1}'}}]}
            elif "mail" in user:                            # Ollama's parse failure
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b'{"error":{"message":"failed to parse JSON"}}')
                return
            else:
                msg = {"tool_calls": [{"id": "c", "function": {
                    "name": "notes_search", "arguments": "{}"}}]}
            out = json.dumps({"choices": [{"message": msg}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

    srv = http.server.HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    cases = [c for c in CASES if any(w in c[0] for w in ("joke", "percent", "schedule", "any new mail", "sister"))]
    res = run(f"http://127.0.0.1:{srv.server_port}", ["fake"], True, cases)["fake"]
    by = {r["utt"]: r for r in res}
    assert by["tell me a joke about cats"]["right_tool"]
    assert by["what's 17.5 percent of 2340"]["args_ok"]
    sched = by["what's on my schedule tomorrow"]
    assert sched["right_tool"] and not sched["args_ok"] and sched["fixed_by_retry"]
    assert by["any new mail?"]["crash"]
    sis = by["what did I tell you about my sister's birthday"]
    assert not sis["right_tool"] and not sis["args_ok"]
    assert check_args("notes_search", {}) == ["'query' is required"]
    assert check_args("control_phone", {"device": "p", "goal": "g", "requests": [], "x": 1})[-1].startswith("'x' is not")
    srv.shutdown()
    print("\nselftest ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:11434")
    ap.add_argument("--models", nargs="+", default=["jarvis-primary"])
    ap.add_argument("--repair", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        sys.exit(0)
    if not a.url.startswith(("http://127.0.0.1", "http://localhost")):
        sys.exit("Only a local Ollama address is allowed.")
    out = run(a.url.rstrip("/"), a.models, a.repair, CASES + HELD_OUT)
    path = os.path.join(HERE, "tool_eval_results.json")
    json.dump(out, open(path, "w", encoding="utf-8"), indent=1)
    print(f"\nSaved: {path}")
