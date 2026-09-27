"""test_media.py - music and video control on this PC (jarvis_media.py,
media.patch; the owner's decision of 2026-09-27, feasibility I91: "no card,
only from the owner's own words").

    python3 backend/test_media.py

Runs anywhere; no Windows, no winrt, no real media session (every call is
injected through Deps). What it proves:

1. control()/now_playing() never raise, whatever `deps` gives back, and
   never import jarvis_gate at all (grep-checked): this feature has NO
   card, by design, not by an omitted check.
2. Play/pause/next/previous each say a plain sentence on success, and a
   plain reason (not a stack trace) when Windows' media controls are
   missing, not on Windows, refuse, or there is nothing playing.
3. now_playing() marks its answer as outside text (READ_MARK) only when it
   really names a title or artist - never when there is nothing playing or
   the call failed.
4. jarvis_quick.py's fast path: "pause the music", "next song", "what's
   playing" and close phrasings match; bare "pause"/"resume" (the focus
   session's own words while a session is running) are left alone.
5. The route and the patch: install() answers GET /api/media and POST
   /api/media/control after the server's own checks (never a card) and
   passes everything else on; media.patch applies after the rest of the
   stack and reverses; the module is shipped.
"""
from __future__ import annotations

import ast
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_media.py")
import _stack  # noqa: E402
import jarvis_media as M  # noqa: E402
import jarvis_quick as Q  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond
                                                        else ""))


def t_never_a_card_by_construction():
    src = (HERE / "jarvis_media.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n.names[0].asname or n.names[0].name for n in ast.walk(tree)
             if isinstance(n, ast.Import)} | {
        n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    check("jarvis_media.py never imports jarvis_gate at all",
          "jarvis_gate" not in names and "import jarvis_gate" not in src)


def t_control_success_and_failure_words():
    for action, said in M._SAID.items():
        out = M.control(action, deps=M.Deps(control=lambda a: {"ok": True}))
        check(f"control({action}) success says '{said}'",
              out == {"ok": True, "said": said})
    out = M.control("play", deps=M.Deps(control=lambda a: {"ok": False, "reason": "nothing"}))
    check("nothing playing: a plain sentence, not a raise",
          out["ok"] is False and "playing" in out["said"].lower())
    out2 = M.control("pause", deps=M.Deps(control=lambda a: {"ok": False,
                                                             "reason": "not_installed"}))
    check("winrt missing: says so plainly", "winrt-Windows.Media.Control" in out2["said"])

    def boom(a):
        raise RuntimeError("boom")

    out3 = M.control("next", deps=M.Deps(control=boom))
    check("a raising control() never propagates - a plain sentence instead",
          out3["ok"] is False and isinstance(out3["said"], str))
    check("an unknown action is refused without calling control() at all",
          M.control("seek")["ok"] is False)


def t_now_playing_marks_outside_text_only_when_real():
    out = M.now_playing(deps=M.Deps(now_playing=lambda: {"ok": True, "playing": True,
                                                          "title": "Song", "artist": "Band"}))
    check("title and artist said, and read names READ_MARK",
          "Song" in out["said"] and "Band" in out["said"] and out["read"] == [M.READ_MARK])
    out2 = M.now_playing(deps=M.Deps(now_playing=lambda: {"ok": True, "playing": False,
                                                          "title": "", "artist": ""}))
    check("nothing playing: no outside text (nothing was really read)",
          out2["read"] == [] and "nothing" in out2["said"].lower())
    out3 = M.now_playing(deps=M.Deps(now_playing=lambda: {"ok": False, "reason": "not_windows"}))
    check("failure: no outside text either", out3["read"] == [] and out3["ok"] is False)
    out4 = M.now_playing(deps=M.Deps(now_playing=lambda: {"ok": True, "playing": True,
                                                          "title": "Only Title", "artist": ""}))
    check("a title with no artist still reads", out4["read"] == [M.READ_MARK])


def t_fast_path_matches_and_leaves_focus_words_alone():
    for text, action in (("pause the music", "media_pause"), ("play the song", "media_play"),
                         ("resume the video", "media_play"), ("next song", "media_next"),
                         ("skip this track", "media_next"), ("skip it", "media_next"),
                         ("previous track", "media_previous"),
                         ("what's playing", "media_now"), ("now playing", "media_now"),
                         ("what song is this", "media_now")):
        got = Q.match(text)
        check(f"{text!r} -> {action}", got is not None and got.name == action,
              repr(got))
    check("bare 'pause' alone is NOT ours (the focus session's, or nothing)",
          Q.match("pause") is None or Q.match("pause").name != "media_pause")
    check("'play chess with me' is not a media command", Q.match("play chess with me") is None
          or not Q.match("play chess with me").name.startswith("media_"))


def t_run_media_calls_the_module():
    import jarvis_quick as QQ
    real = None
    try:
        real = sys.modules.get("jarvis_media")
        sys.modules["jarvis_media"] = M

        class FakeM:
            @staticmethod
            def control(action):
                return {"ok": True, "said": f"did {action}"}

            @staticmethod
            def now_playing():
                return {"ok": True, "said": "Playing: X", "read": [M.READ_MARK]}

        sys.modules["jarvis_media"] = FakeM
        res = QQ.run(QQ.Intent("media_pause"), sched=None, now=0.0)
        check("run() dispatches media_pause through jarvis_media.control",
              res is not None and res.reply == "did pause")
        res2 = QQ.run(QQ.Intent("media_now"), sched=None, now=0.0)
        check("run() dispatches media_now and carries the read marker",
              res2 is not None and res2.reply == "Playing: X" and res2.read == [M.READ_MARK])
    finally:
        if real is not None:
            sys.modules["jarvis_media"] = real
        else:
            sys.modules.pop("jarvis_media", None)


def t_install_wraps_the_routes():
    hits = []

    class H:
        def __init__(self):
            self.sent = None
            self._body = b'{"action": "pause"}'

        def do_GET(self):
            hits.append("get0")

        def do_POST(self):
            hits.append("post0")

        def _send(self, code, out):
            self.sent = (code, out)
            return self.sent

    M.DEPS = M.Deps(control=lambda a: {"ok": True}, now_playing=lambda: {"ok": True,
                                                                         "playing": False,
                                                                         "title": "",
                                                                         "artist": ""})
    line = M.install(H, origin_ok=lambda self: True, token_ok=lambda self: True,
                     read_body=lambda self: self._body)
    check("install returns a banner line naming the feature", "Music and video" in line)

    h = H()
    h.path = M.PATH
    h.do_GET()
    check("GET /api/media is answered here", h.sent[0] == 200 and h.sent[1]["ok"] is True)

    h2 = H()
    h2.path = "/api/something/else"
    h2.do_GET()
    check("any other GET passes through", hits == ["get0"])

    h3 = H()
    h3.path = M.CONTROL_ROUTE
    h3.do_POST()
    check("POST /api/media/control is answered here, no card, no gate",
          h3.sent[0] == 200 and h3.sent[1]["ok"] is True)

    h4 = H()
    h4.path = M.CONTROL_ROUTE
    h4._body = b'{"action": "seek"}'
    h4.do_POST()
    check("an unknown action is refused with 400", h4.sent[0] == 400)

    h5 = H()
    h5.path = "/api/something/else"
    h5.do_POST()
    check("any other POST passes through", "post0" in hits)
    check("install twice wraps once", "already on" in M.install(
        H, origin_ok=lambda self: True, token_ok=lambda self: True,
        read_body=lambda self: self._body))
    M.DEPS = M.Deps()


def t_the_patch():
    order = _stack.order()
    at = order.index("media.patch")
    check("media.patch is in apply-patches.ps1's list, after watch-notifications.patch",
          order.index("watch-notifications.patch") < at, order[max(0, at - 2):at + 1])
    patch = (HERE / "media.patch").read_text(encoding="utf-8")
    check("it patches jarvis_hud.py only",
          [l[6:].strip() for l in patch.splitlines() if l.startswith("+++ b/")]
          == ["jarvis_hud.py"])
    git = shutil.which("git")
    if not git:
        return check("git is here to apply it", False)
    text, log = _stack.stand_in("jarvis_hud.py", order[:at])
    check("the stack before media.patch builds", text is not None, "; ".join(log))
    if text is None:
        return
    d = Path(tempfile.mkdtemp(prefix="jarvis-media-patch-"))
    try:
        (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
        (d / "p.patch").write_text(patch, encoding="utf-8", newline="\n")
        r = subprocess.run([git, "apply", "p.patch"], cwd=d, capture_output=True, text=True)
        check("git apply (forwards) media.patch", r.returncode == 0, r.stderr)
        after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        r2 = subprocess.run([git, "apply", "-R", "p.patch"], cwd=d, capture_output=True,
                            text=True)
        back = (d / "jarvis_hud.py").read_text(encoding="utf-8") == text
        check("applies to what the earlier patches wrote, and reverses",
              r.returncode == 0 and r2.returncode == 0 and back,
              f"forward={r.returncode} reverse={r2.returncode} back-matches={back}")
        if r.returncode == 0:
            i = after.index("# media.patch")
            j = after.index("# Before the main socket", i)
            blk = after[i:j]
            check("the added block passes origin_ok/token_ok/read_body into jarvis_media.install",
                  "import jarvis_media" in blk and "origin_ok=_origin_ok" in blk
                  and "token_ok=_token_ok" in blk and "read_body=_read_body" in blk)
            try:
                compile("def f(self, bind, Handler):\n" + blk, "<patched block>", "exec")
                check("the patched block compiles", True)
            except SyntaxError as exc:
                check("the patched block compiles", False, str(exc))
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    for fn in (t_never_a_card_by_construction, t_control_success_and_failure_words,
               t_now_playing_marks_outside_text_only_when_real,
               t_fast_path_matches_and_leaves_focus_words_alone, t_run_media_calls_the_module,
               t_install_wraps_the_routes, t_the_patch):
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
