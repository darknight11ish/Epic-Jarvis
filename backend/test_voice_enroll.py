""""Train my voice": POST /api/voice/enroll stages clips and raises ONE card.

    python3 test_voice_enroll.py

No pytest, no network, no microphone. Clips are synthesised WAVs. The gate
is a stand-in that answers the way jarvis_gate.check() does (a Verdict with
allowed / tier / outcome / request_id); the enrolment is the REAL
jarvis_voice.enroll() writing a real profile into a temp folder.

What it proves:
  1. Staging never enrols - with the card still unanswered, no profile
     exists and enroll() was never called.
  2. Approving enrols, from the staged clips, and then the clips are gone.
  3. Denying, a timeout, a refusal, or a verdict at the wrong tier: nothing
     is enrolled and the clips are gone.
  4. The limits: clip count, length, format, silence, base64, JSON - each a
     400 with a sentence naming the clip.
  5. One at a time: a second training while a card waits is a 409.
  6. Nothing logs audio or tokens: the audit lines, the card's text and
     detail, stdout/stderr, and the module's own source are checked.
  7. The real enrolment path picks the embedder hear() picks, and still
     works with a jarvis_voice.py from before `sample_rate` existed.
  8. With a real sherpa-onnx speaker model (JARVIS_TEST_SPEAKER_MODEL, only
     where one is available): status, enrolment and hear() all use it.
  9. voice-enroll.patch applies to what voice-503 and appearance wrote, and leaves
     test_voice_503.py's four _no_speech call sites at four.
 10. The patched jarvis_hud.py - only where it exists (the owner's PC).
"""
import array
import ast
import base64
import contextlib
import io
import json
import math
import sys
import tempfile
import threading
import traceback
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, missing, explain, require_shipped  # noqa: E402

# jarvis_voice_enroll.py is OURS; jarvis_voice.py is a rebuilt module. This
# folder and rebuilt/ first, so a stale copy elsewhere cannot shadow them.
sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
require_shipped("jarvis_voice_enroll.py")
import jarvis_voice_enroll as E  # noqa: E402
import jarvis_voice as V  # noqa: E402
import _skeleton  # noqa: E402

SRC = BACKEND / "jarvis_hud.py"
FAILED, PASSED = [], []

# Every enrolment here, real or fake, lands in a temporary folder. Approving
# a card also rebuilds (or deletes) the "hey Jarvis" verifier that sits
# beside the voice print, and this suite, run on the owner's PC, must never
# touch theirs.
V.PROFILE_PATH = Path(tempfile.mkdtemp(prefix="jarvis-enrol-suite-")) / "owner.json"
TOKEN = "tok_SECRET_do_not_log_4471"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------- helpers --

def wav(seconds=2.0, freq=180.0, rate=16000, chans=1, width=2, amp=0.4) -> bytes:
    n = int(seconds * rate)
    # A voice-ish signal: a fundamental plus two harmonics, slowly wobbling,
    # so the spectral fallback has something to embed.
    s = array.array("h", [
        int(amp * 32767 * (0.6 * math.sin(2 * math.pi * freq * i / rate)
                           + 0.3 * math.sin(2 * math.pi * 2 * freq * i / rate)
                           + 0.1 * math.sin(2 * math.pi * 3 * freq * i / rate))
            * (0.8 + 0.2 * math.sin(2 * math.pi * 3 * i / rate)))
        for i in range(n)])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(chans)
        w.setsampwidth(width)
        w.setframerate(rate)
        if width == 2:
            data = s.tobytes()
            if chans == 2:
                data = b"".join(data[i:i + 2] * 2 for i in range(0, len(data), 2))
            w.writeframes(data)
        else:
            w.writeframes(bytes(n * width * chans))
    return buf.getvalue()


def body(clips) -> bytes:
    return json.dumps({"clips": [base64.b64encode(c).decode() for c in clips]}).encode()


def five():
    return [wav(2.0 + i * 0.3, 170 + i * 3) for i in range(5)]


class Verdict:
    def __init__(self, allowed, tier="ask", outcome=None, rid="req-1", reason=""):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.request_id, self.reason = rid, reason


class Gate:
    """Answers like jarvis_gate.check(). Records what the card carried."""

    def __init__(self, verdict):
        self.verdict, self.calls = verdict, []

    def __call__(self, action, detail, prompt):
        self.calls.append((action, detail, prompt))
        return self.verdict


class HeldGate(Gate):
    """A card nobody has answered yet: blocks until released."""

    def __init__(self, verdict):
        super().__init__(verdict)
        self.release = threading.Event()
        self.asked = threading.Event()

    def __call__(self, action, detail, prompt):
        self.calls.append((action, detail, prompt))
        self.asked.set()
        self.release.wait(10)
        return self.verdict


class Enrol:
    """The real jarvis_voice.enroll(), into a temp profile, counted."""

    def __init__(self):
        self.path = Path(tempfile.mkdtemp(prefix="jarvis-enrol-")) / "owner.json"
        self.calls = 0
        self.seen = []

    def __call__(self, clips):
        self.calls += 1
        self.seen = [len(c) for c in clips]
        return V.enroll(clips, embedder=V.Embedder(), path=self.path, sample_rate=16000)


def run_sync(fn):
    fn()


def ask(_action):
    return "ask"


@contextlib.contextmanager
def audited():
    lines = []
    keep = E._audit
    E._audit = lambda event, detail: lines.append((event, json.dumps(detail)))
    try:
        yield lines
    finally:
        E._audit = keep


def fresh():
    E._reset_for_tests()


# ------------------------------------------------------------------ tests --

def t_staging_never_enrols():
    fresh()
    gate, enrol = HeldGate(Verdict(True, outcome="approved")), Enrol()
    code, out = E.stage(body(five()), gate=gate, tier_of=ask, enroll=enrol)
    check("staging answers 202", code == 202, f"{code} {out}")
    check("and says a card is waiting", out.get("pending") is True and out.get("clips") == 5, f"{out}")
    check("the card was raised", gate.asked.wait(5))
    check("with the change_own_config action", gate.calls and gate.calls[0][0] == "change_own_config")
    st = E.state()
    check("status shows it pending", st["pending"] is True and st["clips"] == 5, f"{st}")
    check("NOTHING enrolled while the card waits", enrol.calls == 0 and not enrol.path.exists())
    gate.verdict = Verdict(False, outcome="denied")
    gate.release.set()
    for _ in range(100):
        if not E.state()["pending"]:
            break
        threading.Event().wait(0.05)
    check("a denial after waiting still enrols nothing", enrol.calls == 0 and not enrol.path.exists())


def t_approve_enrols_and_drops_the_clips():
    fresh()
    gate, enrol = Gate(Verdict(True, outcome="approved")), Enrol()
    captured = {}
    real_decide = E._decide

    def spy(pid, **kw):
        captured["list"] = E._PENDING["clips"]      # the staged list object itself
        return real_decide(pid, **kw)
    E._decide = spy
    try:
        with audited() as lines:
            code, out = E.stage(body(five()), gate=gate, tier_of=ask, enroll=enrol,
                                spawn=run_sync)
    finally:
        E._decide = real_decide
    check("202", code == 202, f"{code} {out}")
    check("enroll ran once, on the five staged clips", enrol.calls == 1 and len(enrol.seen) == 5,
          f"{enrol.calls} {enrol.seen}")
    check("a real profile was written", enrol.path.is_file())
    prof = V.load_profile(enrol.path)
    check("it loads, with five samples", prof is not None and prof.samples == 5, f"{prof}")
    check("the staged clips are GONE (the list is emptied)", captured.get("list") == [],
          f"{len(captured.get('list') or [])} left")
    st = E.state()
    check("nothing pending afterwards", st["pending"] is False, f"{st}")
    check("and the last outcome is 'enrolled', 5 samples",
          st.get("last", {}).get("outcome") == "enrolled" and st["last"].get("samples") == 5, f"{st}")
    check("the audit says staged and decided, nothing more",
          [e for e, _ in lines] == ["voice.training.staged", "voice.training.decided"], f"{lines}")


def t_every_other_answer_drops_the_clips():
    cases = [("denied", Verdict(False, outcome="denied"), "denied"),
             ("timed out", Verdict(False, outcome="timed_out"), "timed_out"),
             ("refused by the gate", Verdict(False, outcome="refused", reason="no queue"), "refused"),
             ("allowed at tier auto, nobody asked", Verdict(True, tier="auto", outcome="auto"), "refused"),
             ("allowed at tier notify", Verdict(True, tier="notify", outcome="notify"), "refused"),
             ("an old gate: allowed but no outcome, tier ask", Verdict(True, outcome=None), "enrolled"),
             ("an old gate: not allowed, no outcome", Verdict(False, outcome=None), "refused")]
    for label, verdict, want in cases:
        fresh()
        enrol = Enrol()
        E.stage(body(five()), gate=Gate(verdict), tier_of=ask, enroll=enrol, spawn=run_sync)
        st = E.state()
        got = st.get("last", {}).get("outcome")
        check(f"{label}: outcome {want}", got == want, f"{st}")
        if want != "enrolled":
            check(f"{label}: nothing enrolled", enrol.calls == 0 and not enrol.path.exists())
        check(f"{label}: nothing left staged", st["pending"] is False and E._PENDING is None)

    fresh()

    def boom(action, detail, prompt):
        raise RuntimeError("queue locked")
    enrol = Enrol()
    E.stage(body(five()), gate=boom, tier_of=ask, enroll=enrol, spawn=run_sync)
    check("a gate that raises refuses, enrols nothing, keeps nothing",
          E.state()["last"]["outcome"] == "refused" and enrol.calls == 0 and E._PENDING is None)

    fresh()

    def bad_enrol(clips):
        raise ValueError("no usable audio in those clips")
    E.stage(body(five()), gate=Gate(Verdict(True, outcome="approved")), tier_of=ask,
            enroll=bad_enrol, spawn=run_sync)
    last = E.state()["last"]
    check("an enrolment that fails says why, and keeps nothing",
          last["outcome"] == "failed" and "no usable audio" in last["reason"] and E._PENDING is None,
          f"{last}")


def t_the_tier_must_be_ask():
    for tier in ("auto", "notify", "never"):
        fresh()
        gate = Gate(Verdict(True, tier=tier, outcome="auto"))
        code, out = E.stage(body(five()), gate=gate, tier_of=lambda a, t=tier: t,
                            enroll=Enrol(), spawn=run_sync)
        check(f"tier {tier}: 409 before any card", code == 409 and not gate.calls, f"{code} {out}")
        check(f"tier {tier}: it says what to change", "'ask'" in out.get("error", ""), f"{out}")
        check(f"tier {tier}: nothing staged", E._PENDING is None)


def t_the_limits():
    fresh()
    bad = [
        ("two clips (too few)", body(five()[:2]), "between 3 and 8"),
        ("nine clips (too many)", body([wav()] * 9), "between 3 and 8"),
        ("a clip under a second", body([wav(), wav(0.5), wav()]), "clip 2 is too short"),
        ("a clip over ten seconds", body([wav(), wav(), wav(10.5)]), "clip 3 is longer"),
        ("44.1 kHz", body([wav(), wav(rate=44100), wav()]), "clip 2 must be 16 kHz"),
        ("stereo", body([wav(chans=2), wav(), wav()]), "clip 1 must be 16 kHz, 16-bit, mono"),
        ("silence", body([wav(), wav(), wav(amp=0.0)]), "clip 3 is silent"),
        ("an empty clip", json.dumps({"clips": ["", base64.b64encode(wav()).decode(),
                                                base64.b64encode(wav()).decode()]}).encode(),
         "clip 1 is empty"),
        ("not base64", json.dumps({"clips": ["%%%", "a", "b"]}).encode(), "clip 1 is not valid base64"),
        ("not a WAV", body([b"RIFFnonsense" * 20, wav(), wav()]), "clip 1 is not a WAV"),
        ("not JSON", b"\x00\x01 raw audio", "send {\"clips\""),
        ("JSON without clips", b'{"audio": []}', "send {\"clips\""),
        ("a number where a clip should be", b'{"clips": [1, 2, 3]}', "clip 1 is not base64 text"),
        ("empty body", b"", "send {\"clips\""),
    ]
    for label, b, want in bad:
        gate = Gate(Verdict(True, outcome="approved"))
        code, out = E.stage(b, gate=gate, tier_of=ask, enroll=Enrol(), spawn=run_sync)
        check(f"{label}: 400 '{want}'", code == 400 and want in out.get("error", ""),
              f"{code} {out}")
        check(f"{label}: no card, nothing staged", not gate.calls and E._PENDING is None)

    # An oversized clip is refused on its TEXT length, before decoding.
    huge = "A" * (E.MAX_CLIP_BYTES * 2)
    decoded = []
    keep = base64.b64decode
    base64.b64decode = lambda *a, **k: decoded.append(1) or keep(*a, **k)
    try:
        code, out = E.stage(json.dumps({"clips": [huge, "a", "b"]}).encode(),
                            gate=Gate(None), tier_of=ask, enroll=Enrol(), spawn=run_sync)
    finally:
        base64.b64decode = keep
    check("an oversized clip is refused before it is decoded",
          code == 400 and "clip 1 is longer" in out["error"] and not decoded, f"{code} {out}")

    code, out = E.stage(body([wav(1.0), wav(9.9), wav(5.0)]), gate=Gate(Verdict(False, outcome="denied")),
                        tier_of=ask, enroll=Enrol(), spawn=run_sync)
    check("the edges are inside the limits (1 s and 9.9 s)", code == 202, f"{code} {out}")
    check("eight clips is fine", E.stage(body([wav()] * 8), gate=Gate(Verdict(False, outcome="denied")),
                                         tier_of=ask, enroll=Enrol(), spawn=run_sync)[0] == 202)


def t_one_at_a_time():
    fresh()
    gate = HeldGate(Verdict(False, outcome="denied"))
    code, _ = E.stage(body(five()), gate=gate, tier_of=ask, enroll=Enrol())
    gate.asked.wait(5)
    code2, out2 = E.stage(body(five()), gate=Gate(Verdict(True, outcome="approved")),
                          tier_of=ask, enroll=Enrol(), spawn=run_sync)
    check("a second training while a card waits is 409", code == 202 and code2 == 409, f"{code2} {out2}")
    check("and says a card is waiting, with how long is left",
          out2.get("pending") is True and isinstance(out2.get("expires_in"), int), f"{out2}")
    check("the waiting clips were not replaced", E._PENDING is not None and E._PENDING["count"] == 5)
    gate.release.set()
    for _ in range(100):
        if E._PENDING is None:
            break
        threading.Event().wait(0.05)
    check("once answered, a new one is accepted",
          E.stage(body(five()), gate=Gate(Verdict(False, outcome="denied")), tier_of=ask,
                  enroll=Enrol(), spawn=run_sync)[0] == 202)


def t_nothing_logs_audio_or_tokens():
    fresh()
    clips = five()
    b64 = [base64.b64encode(c).decode() for c in clips]
    gate = Gate(Verdict(True, outcome="approved"))
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with audited() as lines, contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        E.stage(body(clips), gate=gate, tier_of=ask, enroll=Enrol(), spawn=run_sync)
        E.stage(b"not json " + TOKEN.encode(), gate=gate, tier_of=ask, enroll=Enrol(),
                spawn=run_sync)
    printed = out_buf.getvalue() + err_buf.getvalue()
    check("nothing is printed", printed == "", printed[:200])
    blob = json.dumps(lines)
    check("the audit carries no audio (no base64 of any clip)",
          not any(s[:40] in blob for s in b64), blob[:300])
    check("the audit carries counts only", all(len(d) < 200 for _, d in lines), blob[:300])
    _, detail, prompt = gate.calls[0]
    card = json.dumps(detail) + prompt
    check("the card carries no audio", not any(s[:40] in card for s in b64))
    check("the card says how many clips and what it replaces",
          "5 clips" in prompt and "Replace the voice Jarvis listens for" in prompt, prompt)
    check("the card says what refusing costs", "If you say no" in prompt)
    check("no token anywhere", TOKEN not in blob + card + printed)
    st = json.dumps(E.state())
    check("status carries no audio either", not any(s[:40] in st for s in b64) and len(st) < 600, st)

    # The module's source: no print, no logging, no file writes. The clips
    # live in memory only - "never written to disk" is checked, not claimed.
    # ONE write is allowed, and pinned: _wake_verifier saves the "hey
    # Jarvis" verifier - json.dumps of build_verifier's doc, weights and
    # counts, never audio (what that doc holds is checked in
    # test_wakeword.py's verifier tests).
    tree = ast.parse((HERE / "jarvis_voice_enroll.py").read_text(encoding="utf-8"))
    saver = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name == "_wake_verifier")
    saver_nodes = {id(n) for n in ast.walk(saver)}
    # wave.open(io.BytesIO(...)) reads a clip that is already in memory;
    # every other open() would be a file.
    calls = {getattr(n.func, "id", None) or getattr(n.func, "attr", None)
             for n in ast.walk(tree) if isinstance(n, ast.Call) and id(n) not in saver_nodes
             and not (isinstance(n.func, ast.Attribute) and n.func.attr == "open"
                      and getattr(n.func.value, "id", "") == "wave"
                      and n.args and isinstance(n.args[0], ast.Call)
                      and getattr(n.args[0].func, "attr", "") == "BytesIO")}
    bad = calls & {"print", "open", "write_bytes", "write_text", "mkstemp", "NamedTemporaryFile",
                   "info", "debug", "warning", "exception", "error"}
    check("jarvis_voice_enroll.py has no print, logging or file write", not bad, f"{bad}")
    writes = [ast.unparse(n) for n in ast.walk(saver) if isinstance(n, ast.Call)
              and getattr(n.func, "attr", "") in ("write_text", "write_bytes", "open")]
    check("...except the verifier, which writes json.dumps(out['doc']) and nothing else",
          writes == ["tmp.write_text(json.dumps(out['doc']), encoding='utf-8')"], writes)
    imports = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
               for a in n.names} | {n.module for n in ast.walk(tree)
                                    if isinstance(n, ast.ImportFrom) and n.module}
    check("and does not import logging or tempfile", not imports & {"logging", "tempfile"},
          f"{imports}")


def t_the_real_enrolment_path():
    """E._enroll, the default: the same embedder choice hear() makes, a real
    profile, and it still works with a jarvis_voice.py from before
    `sample_rate` existed (the PC may hold that one)."""
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-enrol-real-")) / "owner.json"
    keep = V.PROFILE_PATH
    V.PROFILE_PATH = tmp
    try:
        pcm = [E._read_clip(i + 1, c)[0] for i, c in enumerate(five())]
        prof = E._enroll(pcm)
        check("the default enrolment writes a profile hear() can use",
              tmp.is_file() and V.load_profile(tmp) is not None and prof.samples == 5, f"{prof}")
        expected = "spectral-v1"
        try:
            expected = V.EcapaEmbedder().name
        except Exception:
            pass
        check("made with the same embedder hear() would pick", prof.embedder == expected,
              f"{prof.embedder} vs {expected}")

        real = V.enroll
        seen = {}

        def old_enroll(clips, embedder=None, path=None):     # no sample_rate
            seen["n"] = len(clips)
            return real(clips, embedder=embedder, path=path)
        V.enroll = old_enroll
        try:
            prof = E._enroll(pcm)
        finally:
            V.enroll = real
        check("an older jarvis_voice.enroll (no sample_rate) still works", seen.get("n") == 5
              and prof.samples == 5)
    finally:
        V.PROFILE_PATH = keep


def t_with_the_better_model():
    """Only where a sherpa-onnx speaker model is available to the test:
    set JARVIS_TEST_SPEAKER_MODEL to the .onnx file. Proves the whole path -
    status reports it, enrolment uses it, and the voice that trained passes
    the check in jarvis_speech.hear()."""
    import os
    model = os.environ.get("JARVIS_TEST_SPEAKER_MODEL", "")
    try:
        import sherpa_onnx  # noqa: F401
    except Exception:
        return check("SKIP - sherpa_onnx is not installed here", True)
    if not model or not Path(model).is_file():
        return check("SKIP - set JARVIS_TEST_SPEAKER_MODEL to a sherpa-onnx speaker model", True)
    import jarvis_speech as SP
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-model-"))
    keep_cfg, keep_path = V._cfg, V.PROFILE_PATH
    V._cfg = lambda k, d=None: {"speaker_model": model, "enabled": True,
                                "mode": "owner", "threshold": 0.35}.get(k, d)
    V.PROFILE_PATH = tmp / "owner.json"
    try:
        st = V.status()
        check("status reports the speaker model", st["speaker_model"] is True
              and st["embedder"].startswith("sherpa-onnx:"), f"{st}")
        clips = five()
        prof = E._enroll([E._read_clip(i + 1, c)[0] for i, c in enumerate(clips)])
        check("enrolment used it", prof.embedder == st["embedder"], prof.embedder)
        heard = SP.hear(clips[0])
        check("the voice that trained passes the check", heard.is_owner is True, heard.reason)
        check("and says so on both clients' fields",
              heard.as_dict()["owner"] is True and heard.as_dict()["is_owner"] is True)
    finally:
        V._cfg, V.PROFILE_PATH = keep_cfg, keep_path


def _stand_in() -> str:
    """The stretch of jarvis_hud.py this patch touches, as the patches before
    it leave it: voice-503's end of the /api/voice/say branch, followed by
    the models tuple as appearance.patch left it (it adds "/api/appearance"
    to that tuple). The two hunks share their `if route in (...` line, so
    they are joined there - that is how the real file reads, and it gives
    the patch three lines of real context on each side, which GNU `patch`
    (the script's fallback) needs to apply it without fuzz."""
    base = _skeleton.build("voice-503.patch")
    app = next(lines for _, lines in _skeleton.hunks("appearance.patch")
               if any(l.strip() == '"/api/appearance",' for l in lines))
    anchor = next(l for l in app if l.strip().startswith('if route in ("/api/models/install"'))
    i = base.index(anchor + "\n")
    tail = app[app.index(anchor):]
    return base[:i] + "\n".join(tail) + "\n" + base[i + len(anchor) + 1:]


def _rehearse():
    """(ok, patched text or error). ok is None without git - a skip."""
    import shutil
    import subprocess
    git = shutil.which("git")
    if not git:
        return None, "git is not installed, so the rehearsal could not run"
    d = Path(tempfile.mkdtemp(prefix="jarvis-enrol-skel-"))
    try:
        with open(d / "jarvis_hud.py", "w", encoding="utf-8", newline="\n") as f:
            f.write(_stand_in())
        lf = d / "new.patch"
        lf.write_bytes((HERE / "voice-enroll.patch").read_bytes().replace(b"\r\n", b"\n"))
        for args in (["apply", "--check"], ["apply"], ["apply", "--check", "--reverse"]):
            r = subprocess.run([git] + args + [str(lf)], cwd=d, capture_output=True, text=True)
            if r.returncode != 0:
                return False, f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}"
        return True, (d / "jarvis_hud.py").read_text(encoding="utf-8")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _added_lines(patch: str) -> str:
    return "\n".join(l[1:] for l in (HERE / patch).read_text(encoding="utf-8").splitlines()
                     if l.startswith("+") and not l.startswith("+++"))


def t_the_patch():
    added = _added_lines("voice-enroll.patch")
    check("the route checks origin and token before reading the body",
          added.index("_origin_ok(self)") < added.index("_read_body(self)")
          and added.index("_token_ok(self)") < added.index("_read_body(self)"))
    check("the route logs nothing and reads no header",
          "print(" not in added and "log" not in added.replace("logged", "")
          and "self.headers" not in added, added)
    check("a failure is named, never quoted (no str(exc) in a reply)",
          "str(exc)" not in added and "{exc}" not in added)
    check("it calls jarvis_voice_enroll.stage and nothing that enrols",
          "jarvis_voice_enroll.stage(raw)" in added and "enroll(" not in added.replace(
              "voice_enroll", ""))
    check("it does not add a _no_speech call (test_voice_503 counts four)",
          "_no_speech(" not in added)

    ok, out = _rehearse()
    if ok is None:
        return check("SKIP - " + out, True)
    check("voice-enroll.patch applies to what voice-503 and appearance wrote, and reverses",
          ok is True, out)
    if ok:
        check("the route sits after /api/voice/say and before the models tuple",
              out.index('ctype="audio/wav"') < out.index('route == "/api/voice/enroll"')
              < out.index('if route in ("/api/models/install"'))
        check("still exactly four _no_speech call sites", out.count("_no_speech(") - 1 == 4,
              f"{out.count('_no_speech(')} including the def")


def t_the_real_file():
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    src = SRC.read_text(encoding="utf-8")
    if "/api/voice/enroll" not in src:
        return check("voice-enroll.patch is applied to jarvis_hud.py", False,
                     "run scripts/apply-patches.ps1 first")
    ast.parse(src)
    i = src.index('route == "/api/voice/enroll"')
    seg = src[i:i + 2500]
    check("the patched route is there and stages through jarvis_voice_enroll",
          "jarvis_voice_enroll.stage(raw)" in seg)
    check("and checks the token", "_token_ok(self)" in seg[:seg.index("_read_body")])


if __name__ == "__main__":
    for fn in (t_staging_never_enrols, t_approve_enrols_and_drops_the_clips,
               t_every_other_answer_drops_the_clips, t_the_tier_must_be_ask, t_the_limits,
               t_one_at_a_time, t_nothing_logs_audio_or_tokens, t_the_real_enrolment_path,
               t_with_the_better_model, t_the_patch, t_the_real_file):
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
