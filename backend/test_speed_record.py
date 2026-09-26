"""How fast each answer was, and the speed check on a model switch - numbers only.

    python3 test_speed_record.py

No pytest, no Ollama, no network: a socket opened by anything under test is a
failure. Streams are canned bytes in the three shapes /api/chat relays, split
at awkward places, and the clock is a fake one the test moves by hand.

What matters most, and is checked from more than one side: NO WORDS OF THE
CONVERSATION REACH THE FILE. A stream full of a distinctive secret sentence is
timed, and then the file is searched for every word of it.

Four parts:
  1. jarvis_speed.py's answer timing (item 11).
  2. jarvis_speed.py's model-switch speed check (item 12).
  3. speed-record.patch's context against what earlier patches wrote - git.
  4. The patched jarvis_hud.py - only where it exists (the owner's PC).
"""
import ast
import json
import socket
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, missing, explain  # noqa: E402

# jarvis_speed.py is OURS - it ships in this repository. This folder first
# for it, so a stale copy in the backend folder cannot shadow it.
sys.path.insert(0, str(HERE))
# On a real install (JARVIS_BACKEND set), the backend's own copy must be
# there and be this one - see _where.require_shipped.
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_speed.py")
import jarvis_speed as S  # noqa: E402
import _skeleton  # noqa: E402

SRC = BACKEND / "jarvis_hud.py"
FAILED, PASSED = [], []
SECRET = "Mario's bank PIN is 4471 and his sister lives on Rua Augusta"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class NoNetwork:
    """Any socket at all, in this block, is a failure."""

    def __enter__(self):
        self.real = socket.socket.connect

        def boom(*a, **k):
            raise AssertionError("a socket was opened")
        socket.socket.connect = boom
        return self

    def __exit__(self, *a):
        socket.socket.connect = self.real
        return False


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def sse(pieces, usage=None):
    out = []
    for p in pieces:
        out.append("data: " + json.dumps({"choices": [{"delta": {"content": p}}]}) + "\n\n")
    if usage:
        out.append("data: " + json.dumps({"choices": [], "usage": usage}) + "\n\n")
    out.append("data: [DONE]\n\n")
    return "".join(out).encode("utf-8")


def chop(b, n):
    return [b[i:i + n] for i in range(0, len(b), n)]


def tmplog():
    return S.SpeedLog(Path(tempfile.mkdtemp(prefix="jarvis-speed-")) / "speed.jsonl")


def t_timing_an_answer():
    clk = Clock()
    log = tmplog()
    with NoNetwork():
        m = S.Meter("jarvis-primary", clock=clk)
        clk.t += 0.8                                    # prompt being read
        # "Hello there, friend" split mid-word across pieces, and the bytes
        # chopped every 7 so JSON lines arrive in fragments.
        body = sse(["Hel", "lo there,", " fri", "end"])
        chunks = chop(body, 7)
        m.feed(chunks[0])
        clk.t += 0.0
        for c in chunks[1:]:
            m.feed(c)
            clk.t += 0.01
        row = m.finish(log=log, gpu=lambda name: 100, background=False)
    check("a streamed answer is timed", row is not None, f"{row}")
    check("first word is when the first piece arrived, not when asked",
          row["first_word_ms"] >= 800, f"{row.get('first_word_ms')}")
    check("a word split across two pieces counts once", row["words"] == 3,
          f"words={row.get('words')}")
    check("tokens are counted from the stream pieces", row["tokens"] == 4
          and row["token_source"] == "deltas", f"{row}")
    check("and a rate is worked out", isinstance(row.get("tokens_per_s"), float))
    check("the graphics-card share is recorded", row.get("on_gpu_percent") == 100)
    check("it says streaming was on", row["streamed"] is True)
    rows = log.tail()
    check("exactly one row is on file", len(rows) == 1, f"{rows}")
    check("finishing twice does not write twice",
          m.finish(log=log, background=False) is None and len(log.tail()) == 1)


def t_no_words_ever_reach_the_file():
    log = tmplog()
    with NoNetwork():
        m = S.Meter("m", clock=Clock())
        for c in chop(sse([SECRET[i:i + 5] for i in range(0, len(SECRET), 5)]), 11):
            m.feed(c)
        m.finish(log=log, background=False)
        # And if a caller hands text in by mistake, it is dropped, not written.
        log.append({"kind": "answer", "model": "m", "text": SECRET,
                    "question": SECRET, "answer": SECRET, "note": SECRET,
                    "words": 3, "first_word_ms": SECRET})
        log.append({"kind": SECRET, "model": "m"})
    raw = log.path.read_text(encoding="utf-8")
    leaked = [w for w in SECRET.replace("'", " ").split() if len(w) > 3 and w in raw]
    check("NOT ONE WORD of the answer is in the file", not leaked, f"found {leaked}")
    check("a text field handed in by mistake is dropped", "text" not in raw
          and "question" not in raw)
    check("a row with an unknown kind is not written at all",
          all(r.get("kind") in ("answer", "bench", "switch") for r in log.tail()))
    check("the model name is the only string that is not a fixed word",
          all(set(r) <= S._NUMBER_FIELDS | S._BOOL_FIELDS | S._NAME_FIELDS
              | set(S._ENUM_FIELDS) for r in log.tail()))


def t_prompt_reuse_is_recorded():
    """I03 (feasibility audit step 0, 2026-09-26): how much of each prompt
    Ollama reused instead of reading again - numbers only."""
    log = tmplog()
    with NoNetwork():
        # A relayed stream that carries OpenAI's usage chunk (choices empty).
        m = S.Meter("m", clock=Clock())
        for c in chop(sse(["Hi", " there"], usage={
                "prompt_tokens": 900, "completion_tokens": 2,
                "prompt_tokens_details": {"cached_tokens": 850}}), 9):
            m.feed(c)
        row = m.finish(log=log, gpu=lambda n: None, background=False)
    check("a relayed stream's reused prompt tokens are recorded",
          row and row.get("prompt_tokens") == 900 and row.get("cached_tokens") == 850, row)

    # The chat tool loop: start() on the request thread, the loop's own
    # totals through note_prompt(), then the hook's finish().
    with NoNetwork():
        m = S.start("jarvis-primary")
        ok = S.note_prompt(prompt_tokens=4200, cached_tokens=3900, rounds=2)
        m.feed(sse(["Done", "."]))
        row = m.finish(log=log, gpu=lambda n: None, background=False)
    check("note_prompt() reaches the answer being timed on this thread", ok is True)
    check("... and its row has the turn's prompt, reused and request counts",
          row and row.get("prompt_tokens") == 4200 and row.get("cached_tokens") == 3900
          and row.get("prompt_rounds") == 2, row)
    check("after finish, nothing is being timed here: note_prompt() keeps nothing",
          S.note_prompt(prompt_tokens=1, cached_tokens=1, rounds=1) is False)
    m2 = S.start("x")
    S.note_prompt(prompt_tokens="a secret sentence", cached_tokens=-4, rounds=True)
    m2.feed(sse(["ok", "ay"]))
    bad = m2.finish(log=log, gpu=lambda n: None, background=False)
    check("anything but a whole number is dropped, never written",
          bad and "prompt_tokens" not in bad and "cached_tokens" not in bad
          and "prompt_rounds" not in bad, bad)
    raw = log.path.read_text(encoding="utf-8")
    check("no words in the file", "secret" not in raw and "there" not in raw)


def t_the_tool_loop_asks_for_and_hands_over_prompt_reuse():
    """jarvis_agent asks Ollama for the usage chunk on every streamed round,
    sums prompt and reused tokens over the turn's rounds, returns them, and
    hands them to the answer being timed on this thread."""
    require_shipped("jarvis_agent.py")
    import jarvis_agent as AG

    class Fake:
        def __init__(self, body):
            self._chunks = [body, b""]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, _n=1024):
            return self._chunks.pop(0) if self._chunks else b""

    def chunk(delta, finish=None):
        return {"id": "c1", "object": "chat.completion.chunk", "created": 1,
                "model": "m", "choices": [{"index": 0, "delta": delta,
                                           "finish_reason": finish}]}

    def body(chunks, prompt, cached):
        lines = [json.dumps(c) for c in chunks]
        lines.append(json.dumps({"id": "c1", "choices": [], "usage": {
            "prompt_tokens": prompt, "completion_tokens": 3,
            "prompt_tokens_details": {"cached_tokens": cached}}}))
        return ("".join(f"data: {x}\n\n" for x in lines) + "data: [DONE]\n\n").encode()

    rounds = [
        body([chunk({"role": "assistant", "tool_calls": [{"id": "t1", "index": 0,
              "type": "function", "function": {"name": "calculator",
                                               "arguments": "{\"expression\": \"2+2\"}"}}]}),
              chunk({}, "tool_calls")], 3000, 0),
        body([chunk({"role": "assistant", "content": "It is 4."}), chunk({}, "stop")],
             3100, 2990),
    ]
    sent = []

    def opener(url, payload):
        sent.append(payload)
        return Fake(rounds[len(sent) - 1])

    def allow(*_a, **_k):
        class _Ok:
            allowed, reason, outcome, tier = True, "approved", "approved", "auto"
        return _Ok()

    real_rec, real_pub = AG._record_chain, AG._publish_step
    AG._record_chain = lambda steps: None
    AG._publish_step = lambda step: None
    try:
        meter = S.start("m")
        turn = AG.run_local_turn(
            [{"role": "user", "content": "what is 2+2"}], "m",
            # As jarvis_hud.py wires it: what the app is sent is fed to the meter.
            ollama_url="http://127.0.0.1:1", stream_out=meter.feed, gate_check=allow,
            open_stream=opener, context_length=4096, lane_choice=None,
            model_waking=lambda u, m: False, manner=None)
        row = meter.finish(log=tmplog(), gpu=lambda n: None, background=False)
    finally:
        AG._record_chain, AG._publish_step = real_rec, real_pub
    check("every streamed round asks Ollama for the usage chunk",
          len(sent) == 2 and all(p.get("stream_options") == {"include_usage": True}
                                 for p in sent), [p.get("stream_options") for p in sent])
    check("the turn returns its prompt and reused tokens, summed over its rounds",
          turn.get("prompt_tokens") == 6100 and turn.get("cached_tokens") == 2990, turn)
    check("... and the speed row gets them, with the number of requests",
          row and row.get("prompt_tokens") == 6100 and row.get("cached_tokens") == 2990
          and row.get("prompt_rounds") == 2, row)
    check("the answer itself is unchanged", turn.get("answer") == "It is 4.", turn)


def t_the_other_stream_shapes():
    clk = Clock()
    with NoNetwork():
        # OpenAI-style, with usage at the end - the exact count wins.
        m = S.Meter("m", clock=clk)
        m.feed(sse(["a b", " c"], usage={"completion_tokens": 9, "prompt_tokens": 40}))
        clk.t += 1.0
        r = m.row()
        check("usage.completion_tokens is used when sent",
              r["tokens"] == 9 and r["token_source"] == "usage", f"{r}")
        check("and the prompt size", r.get("prompt_tokens") == 40)

        # Ollama's own newline-delimited JSON, with its exact timings.
        m = S.Meter("m", clock=clk)
        lines = [{"message": {"content": "one two"}, "done": False},
                 {"message": {"content": " three"}, "done": False},
                 {"message": {"content": ""}, "done": True, "eval_count": 50,
                  "eval_duration": 2_000_000_000, "prompt_eval_count": 12,
                  "prompt_eval_duration": 100_000_000, "load_duration": 0}]
        m.feed(("\n".join(json.dumps(x) for x in lines) + "\n").encode())
        r = m.row()
        check("Ollama's own timing is used when it is there",
              r["token_source"] == "ollama" and r["tokens_per_s"] == 25.0, f"{r}")
        check("and words are still counted from the text", r["words"] == 3)

        # Streaming off: one JSON body.
        m = S.Meter("m", clock=clk)
        body = json.dumps({"choices": [{"message": {"content": "just four words here"}}],
                           "usage": {"completion_tokens": 5}}).encode()
        for c in chop(body, 13):
            m.feed(c)
        clk.t += 2.0
        r = m.row()
        check("a non-streamed answer is still counted", r["words"] == 4, f"{r}")
        check("and claims no first-word time it did not see",
              "first_word_ms" not in r and r["streamed"] is False, f"{r}")

        # Garbage never raises.
        m = S.Meter("m", clock=clk)
        for junk in (b"\xff\xfe", b"data: {not json\n", b"data: [1,2]\n", "text",
                     None, b"{\"choices\": 5}\n"):
            m.feed(junk)
        check("garbage in the stream never raises", m.finish(background=False,
              log=tmplog()) is None)


def t_tools_and_summaries():
    rows = []
    # More tool answers than plain ones, so a median that let them in would
    # land on the minute-long wait, not on 400 ms.
    for i in range(4):
        rows.append({"kind": "answer", "model": "a", "tools": False,
                     "first_word_ms": 400, "tokens_per_s": 40.0, "on_gpu_percent": 100})
    for i in range(5):
        rows.append({"kind": "answer", "model": "a", "tools": True,
                     "first_word_ms": 60000, "tokens_per_s": 40.0})
    s = S.summary(rows)["a"]
    check("an answer that waited for your approval does not count as a slow first word",
          s["median_first_word_ms"] == 400, f"{s}")
    check("but it does count as an answer", s["answers"] == 9)

    before = [{"kind": "answer", "model": "a", "tokens_per_s": 40.0}] * 20
    after = [{"kind": "answer", "model": "a", "tokens_per_s": 20.0}] * 10
    sd = S.slowdown(before + after, "a")
    check("half the speed over the last ten answers is flagged", sd and sd["slower"],
          f"{sd}")
    check("with the size of the drop", sd and sd["change_percent"] == -50.0, f"{sd}")
    check("no verdict from too few answers", S.slowdown(after, "a") is None)
    same = S.slowdown(before + before[:10], "a")
    check("CONTROL: no change is not flagged", same and not same["slower"], f"{same}")

    log = tmplog()
    for r in before + after:
        log.append(r)
    v = S.view(limit=5, log=log, current={"ref": "a"})
    check("the screen view is available", v["available"] is True, f"{v}")
    check("recent is capped at the limit asked", len(v["recent"]) == 5)
    check("the slowdown is in the words on the screen",
          "slower" in v["note"] and v["slowdown"]["slower"], v.get("note"))
    v2 = S.view(log=S.SpeedLog(Path(tempfile.mkdtemp()) / "nothing-here.jsonl"))
    check("an empty history is not an error", v2["available"] is True
          and v2["recent"] == [] and v2["last_switch"] is None, f"{v2}")


def t_the_file_never_breaks_an_answer():
    d = Path(tempfile.mkdtemp())
    (d / "afile").write_text("x")
    bad = S.SpeedLog(d / "afile" / "speed.jsonl")         # parent is a file
    check("an unwritable place returns False instead of raising",
          bad.append({"kind": "answer", "model": "m", "words": 1}) is False)
    check("and reading it returns nothing instead of raising", bad.tail() == [])
    m = S.Meter("m", clock=Clock())
    m.feed(sse(["a b c"]))
    check("finish on an unwritable log still returns",
          m.finish(log=bad, background=False) is not None)

    def gpu_breaks(_):
        raise RuntimeError("ollama gone")
    log = tmplog()
    m = S.Meter("m", clock=Clock())
    m.feed(sse(["a b c"]))
    m.finish(log=log, gpu=gpu_breaks, background=False)
    got = log.tail()
    check("a failed graphics-card lookup still records the answer",
          len(got) == 1 and "on_gpu_percent" not in got[0], f"{got}")

    # A big file: only the end is read, and a half line at the cut is skipped.
    log = tmplog()
    with open(log.path, "w", encoding="utf-8") as f:
        for i in range(20000):
            f.write(json.dumps({"kind": "answer", "model": "m", "words": i}) + "\n")
    tail = log.tail(3, max_bytes=4096)
    check("the tail of a big file is read", [r["words"] for r in tail] == [19997, 19998, 19999],
          f"{tail}")


def t_the_switch_speed_check():
    reply = {"eval_count": 64, "eval_duration": 1_600_000_000,
             "prompt_eval_duration": 50_000_000, "load_duration": 3_000_000_000,
             "prompt_eval_count": 20}
    t = S.timing_from_reply(reply)
    check("Ollama's reply timings are read", t and t["tokens_per_s"] == 40.0
          and t["load_ms"] == 3000 and t["first_word_ms"] == 3050, f"{t}")
    check("a reply without them gives None, not a guess",
          S.timing_from_reply({"choices": [{"message": {"content": "hi"}}]}) is None)

    log = tmplog()
    sp = S.SwitchSpeed("old:8b", "new:8b")
    for tps in (40, 41, 39):
        sp.add("old", {"eval_count": 40 * 1, "eval_duration": int(40 / tps * 1e9)})
    for tps in (20, 21, 19):
        sp.add("new", {"eval_count": 40, "eval_duration": int(40 / tps * 1e9),
                       "load_duration": 5_000_000_000})
    sp.add("sideways", reply)                               # ignored
    res = sp.finish(log=log)
    check("the old and new speeds are both there",
          res["old"]["tokens_per_s"] == 40.0 and res["new"]["tokens_per_s"] == 20.0, f"{res}")
    check("the change is worked out", res["change_percent"] == -50.0)
    check("and said in words", "slower" in res["note"] and "40" in res["note"]
          and "20" in res["note"], res["note"])
    check("and it says plainly it cannot judge quality",
          "speed only" in res["quality_note"])
    kinds = [r["kind"] for r in log.tail()]
    check("a switch row and a bench row for the new model are on file",
          kinds == ["bench", "switch"], f"{kinds}")

    # Next switch, away from new:8b, without measuring it again: the stored
    # bench row is used, and the result says so.
    sp2 = S.SwitchSpeed("new:8b", "third:8b")
    sp2.add("new", {"eval_count": 30, "eval_duration": 1_000_000_000})
    res2 = sp2.finish(log=log)
    check("the old model's number can come from its last measurement",
          res2["old"]["source"] == "stored" and res2["old"]["tokens_per_s"] == 20.0, f"{res2}")
    check("and the words say where it came from", "last time it was measured" in res2["note"])
    v = S.view(log=log)
    check("the Models screen gets the last switch, with its sentence ready-made",
          v["last_switch"]["new_model"] == "third:8b"
          and "50% faster" in v["last_switch_note"]
          and "speed only" in v["last_switch_note"], f"{v.get('last_switch_note')}")

    sp3 = S.SwitchSpeed("never-seen", "x")
    sp3.add("new", {"eval_count": 30, "eval_duration": 1_000_000_000})
    res3 = sp3.finish(log=tmplog())
    check("with nothing on file, it says there is nothing to compare with",
          res3["old"] is None and "no earlier measurement" in res3["note"], f"{res3}")

    clk = Clock()
    sp4 = S.SwitchSpeed("a", "b", clock=clk)

    def probe():
        clk.t += 1.5
        return {"choices": [{"message": {"content": "ok"}}]}
    out = sp4.timed("new", probe)
    check("timed() hands the reply back untouched", out["choices"][0]["message"]["content"] == "ok")
    check("and, with no Ollama timings, records the wall clock only",
          sp4._samples["new"] == [{"first_word_ms": 1500, "tokens_per_s": None}],
          f"{sp4._samples}")


class FakePost:
    def __init__(self):
        self.calls = []

    def __call__(self, url, payload):
        self.calls.append((url, payload))
        return {"eval_count": 64, "eval_duration": 2_000_000_000,
                "prompt_eval_duration": 10_000_000, "load_duration": 0}


def t_measure_stays_on_this_pc():
    p = FakePost()
    with NoNetwork():
        out = S.measure("jarvis-primary", base="http://192.168.1.20:11434", post=p,
                        log=tmplog())
    check("a non-local Ollama address is refused before anything is sent",
          out["ok"] is False and p.calls == [], f"{out} {p.calls}")
    for base in ("http://10.0.0.1:11434", "http://example.com:11434",
                 "http://100.64.0.1:11434"):
        check(f"refused: {base}", S.measure("m", base=base, post=p,
                                            log=tmplog())["ok"] is False and not p.calls)

    log = tmplog()
    with NoNetwork():
        out = S.measure("jarvis-primary", base="http://127.0.0.1:11434", post=p, log=log)
    check("on this PC it measures", out["ok"] and out["tokens_per_s"] == 32.0, f"{out}")
    check("it only ever calls /api/generate",
          {u for u, _ in p.calls} == {"http://127.0.0.1:11434/api/generate"})
    check("only the fixed prompts are sent - nothing from any conversation",
          [b["prompt"] for _, b in p.calls] == list(S.FIXED_PROMPTS))
    check("it never sends num_ctx, which would reload the model",
          all("num_ctx" not in (b.get("options") or {}) and "num_ctx" not in b
              for _, b in p.calls))
    check("and a bench row is on file", [r["kind"] for r in log.tail()] == ["bench"])

    seen = []

    def get(url):
        seen.append(url)
        return {"models": [{"name": "jarvis-primary:latest"}]}
    check("is_loaded reads /api/ps", S.is_loaded("jarvis-primary", base="http://localhost:11434",
                                                 get=get) is True and seen == [
        "http://localhost:11434/api/ps"])
    check("is_loaded will not ask another machine",
          S.is_loaded("m", base="http://10.1.1.1:11434", get=get) is None and len(seen) == 1)


def t_the_patch_context():
    ok, out = _skeleton.rehearse("speed-record.patch",
                                 "gpu-offload.patch", "tool-calling-wiring.patch")
    if ok is None:
        return check("SKIP - " + out, True)
    check("speed-record.patch applies to what gpu-offload and tool-calling-wiring wrote",
          ok is True, out)
    if ok:
        check("both answer paths are timed", out.count("_speed.feed(chunk)") == 2
              and out.count("_speed.finish(lane") == 2, "")
        check("the models screen gets the speed block", '"speed": speed,' in out)


def t_the_real_file():
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    src = SRC.read_text(encoding="utf-8")
    if "jarvis_speed" not in src:
        return check("speed-record.patch is applied to jarvis_hud.py", False,
                     "run scripts/apply-patches.ps1 first")
    tree = ast.parse(src)
    mv = next((n for n in tree.body if isinstance(n, ast.FunctionDef)
               and n.name == "_models_view"), None)
    check("_models_view asks jarvis_speed for the speed block",
          mv is not None and "jarvis_speed.view" in ast.unparse(mv))
    check("both answer paths feed the meter", src.count("_speed.feed(chunk)") == 2)
    check("both answer paths record a finished answer",
          src.count("_speed.finish(lane") == 2)
    # A cut-off stream must not be recorded: no finish inside an except.
    bad = [h for h in ast.walk(tree) if isinstance(h, ast.ExceptHandler)
           and "_speed.finish" in ast.unparse(h)]
    check("a stream cut off mid-answer is never recorded", not bad)


if __name__ == "__main__":
    for fn in (t_timing_an_answer, t_no_words_ever_reach_the_file,
               t_prompt_reuse_is_recorded, t_the_tool_loop_asks_for_and_hands_over_prompt_reuse,
               t_the_other_stream_shapes, t_tools_and_summaries,
               t_the_file_never_breaks_an_answer, t_the_switch_speed_check,
               t_measure_stays_on_this_pc, t_the_patch_context, t_the_real_file):
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
