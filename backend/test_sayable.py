"""test_sayable.py - "Things you can say", the fixed list of real sentences
Jarvis answers WITHOUT the AI model (already approved as feasibility I116;
the ease-of-use audit's do-first table, row 4, 2026-09-27).

    python3 backend/test_sayable.py

What it proves:
  - the list has 5-8 sentences, and EVERY ONE of them, byte for byte as it
    is served, really is answered by jarvis_quick.py's own grammar with no
    model - not a guess about what the grammar covers;
  - the 3 walkthrough examples are a subset of the served list, and there
    are exactly 3;
  - the served view() carries the title, footer, help words and no secret,
    no setting and no card (it is fixed text, like jarvis_manner.py and
    jarvis_wellbeing.py - not something the owner can change or that raises
    a card either way);
  - "what can you do?" and close phrasings are answered by jarvis_quick.py
    from the same list, without the model; a near miss and pasted text go
    to the model instead;
  - without jarvis_sayable.py, the fast path says to run apply-patches.ps1,
    the same shape as jarvis_reach.py's own fallback;
  - sayable.patch applies to what the earlier patches wrote, reverses,
    checks the origin and the token, and its block runs;
  - both apps carry the PC's words, held to the generated contract fixture.
No network, no model.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_sayable.py", "jarvis_quick.py", "jarvis_schedule.py")

import jarvis_sayable as S  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_schedule as SCHED  # noqa: E402
import _stack  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class _Sched:
    """A real scheduler in a throwaway folder - every SENTENCES entry must
    run against a real one, not a mock, or "it matches the grammar" would
    prove nothing about whether it actually DOES anything."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.inner = SCHED.Scheduler(Path(self.tmp.name) / "schedule.json")

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def close(self):
        self.tmp.cleanup()


def t_the_list_shape():
    check("5 to 8 sentences", 5 <= len(S.SENTENCES) <= 8, len(S.SENTENCES))
    check("no duplicate", len(set(S.SENTENCES)) == len(S.SENTENCES))
    for s in S.SENTENCES:
        check(f"a real sentence, not empty: {s!r}", isinstance(s, str) and s.strip() == s and s)
    check("exactly 3 walkthrough examples", len(S.WALKTHROUGH_EXAMPLES) == 3,
          S.WALKTHROUGH_EXAMPLES)
    check("every walkthrough example is on the served list",
          set(S.WALKTHROUGH_EXAMPLES) <= set(S.SENTENCES))
    check("no duplicate walkthrough example", len(set(S.WALKTHROUGH_EXAMPLES)) == 3)


def t_every_sentence_really_works_with_no_model():
    """The one claim that matters: every served sentence, exactly as served,
    is answered by jarvis_quick.py - not "close to" one of its patterns."""
    now = time.time()
    sched = _Sched()
    try:
        for s in S.SENTENCES:
            intent = Q.match(s, now=now)
            check(f"matches the no-model grammar: {s!r}", intent is not None)
            if intent is None:
                continue
            result = Q.run(intent, sched, now)
            check(f"and really answers something, no model: {s!r}",
                  result is not None and isinstance(result.reply, str) and result.reply.strip(),
                  result)
    finally:
        sched.close()


def t_answer_turn_end_to_end():
    """The exact path a real chat turn takes (answer_turn), for one sentence
    from the list and for the intro line itself."""
    sched = _Sched()
    try:
        for prov in ("typed", "voice"):
            body = {"messages": [{"role": "user", "content": S.SENTENCES[0],
                                  "provenance": prov}], "stream": True}
            res = Q.answer_turn(body, sched=sched, now=time.time())
            check(f"a served sentence answers end to end ({prov})", res is not None
                  and res.reply.strip(), res)
        body = {"messages": [{"role": "user", "content": "what can you do?",
                              "provenance": "typed"}], "stream": True}
        res = Q.answer_turn(body, sched=sched, now=time.time())
        check("\"what can you do?\" answers end to end, no model",
              res is not None and res.intent == "sayable_help", res)
        for one in S.SENTENCES:
            check(f"the answer names {one!r}", one in res.reply, res.reply)
        check("the answer names the footer line", S.FOOTER in res.reply, res.reply)
    finally:
        sched.close()


def t_view_is_fixed_text_no_card_no_secret():
    code, v = S.handle_get()
    check("GET: 200, available", code == 200 and v["available"] is True)
    check("the title and footer are the audit's own words",
          v["title"] == "Things you can say"
          and v["footer"] == "More: right-click the Jarvis icon by the clock.")
    check("the served sentences are exactly SENTENCES, in order",
          v["sentences"] == list(S.SENTENCES))
    check("the served walkthrough examples are exactly WALKTHROUGH_EXAMPLES",
          v["walkthrough_examples"] == list(S.WALKTHROUGH_EXAMPLES))
    check("the help words are non-empty and name the list",
          bool(v["help_title"]) and all(s in v["help_body"] for s in S.SENTENCES))
    check("no card and no gate: fixed text only",
          "card" not in json.dumps(v).lower() and "waiting" not in v and "request_id" not in v)
    src = (HERE / "jarvis_sayable.py").read_text(encoding="utf-8")
    check("the module asks no gate and raises no card",
          "jarvis_gate" not in src and "gate(" not in src and "request_id" not in src)
    check("no setting is written: no settings_path, no config dir, no os.replace",
          "settings_path" not in src and "os.replace" not in src)


def t_the_quick_answer_and_near_misses():
    now = time.time()
    for text in ("what can you do?", "What can I say?", "what can jarvis do", "help",
                 "help me", "What should I say?", "What are your commands?",
                 "show me what I can say", "What can I ask?"):
        intent = Q.match(text, now=now)
        check(f"answered here, no model: {text!r}", intent is not None
              and intent.name == "sayable_help", intent)
    for text in ("what can you do about the weather", "help me move this table",
                 "what can you do for a living", "help me understand quantum physics"):
        intent = Q.match(text, now=now)
        check(f"a near miss goes to the model: {text!r}", intent is None
              or intent.name != "sayable_help", intent)
    body = {"messages": [{"role": "user", "content": "what can you do?",
                          "provenance": "pasted"}]}
    check("pasted text goes to the model", Q.answer_turn(body, sched=_Sched()) is None)
    saved = sys.modules.get("jarvis_sayable")
    sys.modules["jarvis_sayable"] = None
    try:
        r = Q.answer("what can you do?", sched=_Sched())
    finally:
        sys.modules["jarvis_sayable"] = saved
    check("without jarvis_sayable.py it says to run apply-patches.ps1",
          r is not None and r.reply == Q.SAYABLE_MISSING)


def _rehearse():
    order = _stack.order()
    if "sayable.patch" not in order:
        return False, "sayable.patch is not in apply-patches.ps1's list", ""
    before = order[:order.index("sayable.patch")]
    patch = (HERE / "sayable.patch").read_text(encoding="utf-8")
    text, log = _stack.stand_in("jarvis_hud.py", before)
    if text is None:
        return False, "; ".join(log), ""
    git = shutil.which("git")
    d = Path(tempfile.mkdtemp(prefix="jarvis-sayable-patch-"))
    try:
        (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
        (d / "p.patch").write_text(patch, encoding="utf-8", newline="\n")
        r = subprocess.run([git, "apply", "p.patch"], cwd=d, capture_output=True, text=True)
        if r.returncode != 0:
            return False, r.stderr, ""
        after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        r = subprocess.run([git, "apply", "-R", "p.patch"], cwd=d, capture_output=True, text=True)
        if r.returncode != 0 or (d / "jarvis_hud.py").read_text(encoding="utf-8") != text:
            return False, "does not reverse cleanly: " + r.stderr, ""
        return True, "", after
    finally:
        shutil.rmtree(d, ignore_errors=True)


class _Handler:
    def __init__(self):
        self.sent = None

    def _send(self, code, out):
        self.sent = (code, out)
        return self.sent


def t_the_patch():
    if not shutil.which("git"):
        return check("SKIP - git is not installed", True)
    ok, why, hud = _rehearse()
    check("sayable.patch applies to what the earlier patches wrote, and reverses", ok, why)
    if not ok:
        return
    i = hud.index('        if path == "/api/sayable":')
    j = hud.index('        if path == "/api/reach":', i)
    blk = hud[i:j]
    check("GET /api/sayable checks origin and token", "_origin_ok(self)" in blk
          and "_token_ok(self)" in blk)
    check("... and touches nothing else (the only file it patches is jarvis_hud.py)",
          (HERE / "sayable.patch").read_text(encoding="utf-8").count("+++ b/") == 1)
    ns = {}
    exec(compile("def f(self, path, _origin_ok, _token_ok):\n" + blk, "<GET>", "exec"), ns)
    h = _Handler()
    ns["f"](h, "/api/sayable", lambda s: True, lambda s: True)
    check("GET runs and answers the list", h.sent[0] == 200
          and h.sent[1]["sentences"] == list(S.SENTENCES), h.sent)
    ns["f"](h, "/api/sayable", lambda s: True, lambda s: False)
    check("... 401 without the token", h.sent[0] == 401)
    ns["f"](h, "/api/sayable", lambda s: False, lambda s: True)
    check("... 403 from another origin", h.sent[0] == 403)
    saved = sys.modules.get("jarvis_sayable")
    sys.modules["jarvis_sayable"] = None
    try:
        ns["f"](h, "/api/sayable", lambda s: True, lambda s: True)
    finally:
        sys.modules["jarvis_sayable"] = saved
    check("... 503 available:false without jarvis_sayable.py", h.sent[0] == 503
          and h.sent[1]["available"] is False)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    check("apply-patches.ps1 applies sayable.patch after draft-email.patch",
          names.index("draft-email.patch") < names.index("sayable.patch"))


def t_both_apps_carry_the_same_words():
    """Held to the generated contract fixture, the same shape as
    tools/gen_reach_cases.py and tools/gen_card_words_cases.py."""
    gen = REPO / "tools" / "gen_sayable_cases.py"
    check("the generator exists", gen.is_file())
    if not gen.is_file():
        return
    r = subprocess.run([sys.executable, str(gen), "--check"], cwd=REPO,
                       capture_output=True, text=True)
    check("both apps' fixture copies match the backend (run "
          "python3 tools/gen_sayable_cases.py if not)", r.returncode == 0, r.stdout + r.stderr)
    desktop = REPO / "jarvis-desktop" / "src" / "sayable.js"
    phone = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" /
             "client" / "net" / "Sayable.kt")
    check("the desktop's sayable.js exists", desktop.is_file())
    check("the phone's Sayable.kt exists", phone.is_file())
    if desktop.is_file():
        js = desktop.read_text(encoding="utf-8")
        for s in S.SENTENCES:
            check(f"sayable.js carries {s!r}", json.dumps(s) in js)
        check("sayable.js carries the footer", json.dumps(S.FOOTER) in js)
    if phone.is_file():
        kt = phone.read_text(encoding="utf-8")
        for s in S.SENTENCES:
            check(f"Sayable.kt carries {s!r}", json.dumps(s) in kt)
        check("Sayable.kt carries the footer", json.dumps(S.FOOTER) in kt)


def main():
    for fn in (t_the_list_shape, t_every_sentence_really_works_with_no_model,
               t_answer_turn_end_to_end, t_view_is_fixed_text_no_card_no_secret,
               t_the_quick_answer_and_near_misses, t_the_patch,
               t_both_apps_carry_the_same_words):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
