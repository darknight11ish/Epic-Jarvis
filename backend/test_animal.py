"""test_animal.py - every animal option in one place, and Jarvis changing
them when asked (jarvis_animal.py, animal.patch, the animal part of
jarvis_settings_registry.py and jarvis_quick.py; the owner's decisions of
2026-09-28).

    python3 backend/test_animal.py

Runs anywhere; no model, no network (the Open-Meteo card's gate is
injected and nothing is ever fetched). What it proves:

1. The shared switches start at the owner's chosen defaults (nods, focus
   buddy, small acknowledgements and petting on; "Keep the animal still"
   and seasonal touches off), a damaged file is the defaults, and every
   switch has words, a default and at least one spoken name - so a new
   behaviour is ONE entry in SWITCHES.
2. One change at a time, at once, no card; saved in animal.json (never in
   appearance.json, which the Faces window rewrites); a change rings the
   `appearance` doorbell with the new values; the same value again says
   "already".
3. The per-device words (sharpness, frame rate) are the apps' own ids and
   labels (face-tuning.js, the phone's FaceBudget.kt), and step_device()
   is the one stepping rule.
4. Asking Jarvis: every switch turns on and off by each of its names;
   "keep the animal still", "stop the animal's nodding", "turn off the
   weather", "turn on the sun and moon", "use Open-Meteo for the weather"
   (ONE card - nothing changes until it is approved), "make the animal
   sharper/smoother" (X-Jarvis-Route `face_tuning`, the PC stores nothing),
   and an unclear request is asked back, never guessed. Pasted words act on
   nothing. Nothing here collides with the older grammar or the registry.
5. The route and the patch: install() answers /api/animal after the
   server's own checks and passes everything else on; animal.patch applies
   after the rest of the stack (sky.patch included), reverses, and its
   blocks compile; the module is shipped.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_animal.py", "jarvis_sky.py", "jarvis_sky_places.py", "jarvis_quick.py",
                "jarvis_settings_registry.py", "jarvis_schedule.py", "jarvis_owner_check.py")
sys.path.append(str(HERE / "rebuilt"))

TMP = Path(tempfile.mkdtemp(prefix="jarvis-animal-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(TMP)
_TOML = TMP / "jarvis-framework.toml"
shutil.copyfile(HERE / "rebuilt" / "jarvis-framework.toml", _TOML)
os.environ["JARVIS_FRAMEWORK_TOML"] = str(_TOML)

import _stack  # noqa: E402
import jarvis_animal as AN  # noqa: E402
import jarvis_sky as SK  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402

AN._config_dir = lambda: TMP
SK._config_dir = lambda: TMP
AN._audit = lambda *a: None
SK._audit = lambda *a: None
RUNG = []
AN.publish = lambda kind, data: RUNG.append((kind, data))
SK.publish = lambda kind, data: RUNG.append((kind, data))

FAILED, PASSED = [], []
PC, PHONE = "127.0.0.1", "100.100.5.9"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def fresh():
    for p in (AN.settings_path(), SK.settings_path()):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    SK._reset_for_tests()
    RUNG.clear()


def go(text, *, provenance="typed", peer=PHONE, local="127.0.0.1"):
    body = {"messages": [{"role": "user", "content": text, "provenance": provenance}]}
    return Q.answer_turn(body, now=time.time(), peer=peer, local=local)


def one_sentence(reply: str) -> bool:
    # One short plain sentence: a question or a statement, no list.
    body = reply.rstrip(".?")
    return bool(reply) and len(reply) <= 200 and "\n" not in reply and ". " not in body


# ============================================================ 1. defaults


def t_defaults():
    fresh()
    v = AN.values()
    check("the owner's defaults: nods, focus buddy, acks, petting, cute moments on; still, "
          "seasonal off",
          v == {"still": False, "nods": True, "focus_buddy": True, "acks": True,
                "petting": True, "cute_moments": True, "seasonal": False}, v)
    AN.settings_path().write_text("{not json", encoding="utf-8")
    check("a damaged file is the defaults", AN.values() == AN.DEFAULTS)
    AN.settings_path().write_text(json.dumps({"switches": {"still": "yes", "nods": False}}),
                                  encoding="utf-8")
    check("only a real true/false is read; the rest are defaults",
          AN.values()["still"] is False and AN.values()["nods"] is False)
    fresh()
    for s in AN.SWITCHES:
        check(f"{s.id}: words, a default and a spoken name",
              s.label and s.detail and isinstance(s.default, bool) and s.names
              and s.on_said and s.off_said)
    ids = [s.id for s in AN.SWITCHES]
    check("switch ids are unique", len(ids) == len(set(ids)))
    names = [AN._bare(n) for s in AN.SWITCHES for n in s.names]
    check("no spoken name is claimed by two switches", len(names) == len(set(names)))
    built = {s.id: s.built for s in AN.SWITCHES}
    check("every behaviour is built now (2026-09-28): nothing says it is coming",
          built == {"still": True, "nods": True, "focus_buddy": True, "acks": True,
                    "petting": True, "cute_moments": True, "seasonal": True}, built)
    check("and no switch's words promise a next update",
          not any("next update" in (s.on_said + s.off_said + s.detail) for s in AN.SWITCHES))
    v = AN.view()
    check("the view lists every switch, in order, with its value",
          [s["id"] for s in v["switches"]] == ids and v["values"] == AN.DEFAULTS
          and all("coming" not in s for s in v["switches"]) and v["coming"])


# ============================================================ 2. changes


def t_changes_at_once():
    fresh()
    code, out = AN.handle_post({"still": True})
    check("still on: 200, at once", code == 200 and out["ok"] and AN.values()["still"] is True,
          out)
    check("it says so, for both devices, in one sentence",
          "PC and phone" in out["said"] and one_sentence(out["said"]), out["said"])
    check("the appearance doorbell rang with the new values",
          RUNG and RUNG[-1][0] == "appearance" and RUNG[-1][1]["part"] == "animal"
          and RUNG[-1][1]["animal"]["still"] is True, RUNG)
    RUNG.clear()
    code, out = AN.handle_post({"still": True})
    check("the same again: 'already on', no doorbell",
          code == 200 and out["said"] == "Keep the animal still: already on." and not RUNG, out)
    check("saved in animal.json, never appearance.json",
          AN.settings_path().name == "animal.json"
          and json.loads(AN.settings_path().read_text())["switches"]["still"] is True
          and not (TMP / "appearance.json").exists())
    check("two changes at once are refused", AN.handle_post({"still": False, "nods": False})[0]
          == 400)
    check("an unknown option is refused", AN.handle_post({"sparkles": True})[0] == 400)
    check("a non-boolean is refused", AN.handle_post({"nods": "off"})[0] == 400)
    code, out = AN.handle_post({"seasonal": True})
    check("a built behaviour says it is on, with no 'next update'",
          code == 200 and "next update" not in out["said"] and "on for your PC and phone" in out["said"]
          and one_sentence(out["said"]), out)
    fresh()


# ============================================================ 3. per device


def _js_list(name):
    src = (REPO / "jarvis-desktop" / "src" / "face-tuning.js").read_text(encoding="utf-8")
    block = src[src.index(f"export const {name}"):]
    block = block[:block.index("];")]
    return re.findall(r'id:\s*"([^"]+)",\s*label:\s*"([^"]+)"', block)


def t_device_words_and_steps():
    check("sharpness ids and labels are face-tuning.js QUALITIES'",
          [tuple(x) for x in _js_list("QUALITIES")] == list(AN.SHARPNESS), _js_list("QUALITIES"))
    check("frame rates are face-tuning.js FRAME_RATES'",
          [tuple(x) for x in _js_list("FRAME_RATES")] == list(AN.FRAME_RATES))
    kt = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client"
          / "face" / "FaceBudget.kt").read_text(encoding="utf-8")
    q = kt[kt.index("enum class QualityTier"):kt.index("enum class FrameRateTarget")]
    tiers = re.findall(r'^\s+(?:LOW|MEDIUM|HIGH|MAX)\(\s*"(\w+)",\s*"(\w+)"', q, re.M)
    check("sharpness is the phone's QualityTier too", tiers == list(AN.SHARPNESS), tiers)
    rates = re.findall(r'^\s+\w+\("(\w+)", "(\w+)", [\d.]+f\)', kt, re.M)
    check("frame rates are the phone's FrameRateTarget too", rates == list(AN.FRAME_RATES), rates)
    auto = {"quality": "high", "frameRate": "auto", "autoAdjust": True}
    s = AN.step_device(auto, "sharper")
    check("sharper from Auto: Maximum, Auto adjust off",
          s["tuning"] == {"quality": "max", "frameRate": "auto", "autoAdjust": False}
          and s["changed"] and "{device}" in s["line"], s)
    s = AN.step_device(auto, "smoother")
    check("smoother from Auto: 90", s["tuning"]["frameRate"] == "90"
          and s["tuning"]["autoAdjust"] is False, s)
    s = AN.step_device({"quality": "low", "frameRate": "30", "autoAdjust": False}, "softer")
    check("softer at Lower: already, nothing changes", not s["changed"] and "already" in s["line"],
          s)
    s = AN.step_device({"quality": "max", "frameRate": "max", "autoAdjust": False}, "smoother")
    check("smoother at Max: already", not s["changed"] and "already" in s["line"], s)
    s = AN.step_device({"quality": "medium", "frameRate": "60", "autoAdjust": False}, "auto")
    check("auto: Auto adjust back on, the picks kept",
          s["tuning"] == {"quality": "medium", "frameRate": "60", "autoAdjust": True}, s)
    s = AN.step_device(auto, "frame_rate:120")
    check("an exact frame rate", s["tuning"]["frameRate"] == "120"
          and s["tuning"]["autoAdjust"] is False)
    check("every DEVICE_CHANGE has an answer", all(c in AN.DEVICE_SAID for c in AN.DEVICE_CHANGES))
    check("every answer says 'on this device only'",
          all("this device only" in AN.DEVICE_SAID[c] for c in AN.DEVICE_CHANGES))


# ============================================================ 4. asking Jarvis


def t_every_switch_by_every_name():
    fresh()
    bad = []
    for s in AN.SWITCHES:
        for name in s.names:
            for phrase, on in ((f"turn on {name}", True), (f"turn off {name}", False),
                               (f"disable {name}", False), (f"enable {name}", True)):
                i = Q.match(phrase)
                if i is None or i.name != "animal_switch" or i.f != {"key": s.id, "on": on}:
                    bad.append((phrase, i and (i.name, i.f)))
    check("every switch turns on and off by each of its names", not bad, bad[:6])


def t_asking_changes_the_pc():
    fresh()
    r = go("keep the animal still")
    check("'keep the animal still': at once, one sentence",
          r and r.intent == "animal_switch" and AN.values()["still"] is True
          and one_sentence(r.reply), r and r.reply)
    r = go("let the animal move again")
    check("'let the animal move again': Still off", AN.values()["still"] is False, r and r.reply)
    r = go("stop the animal's nodding")
    check("'stop the animal's nodding': nods off", AN.values()["nods"] is False
          and "off" in r.reply, r and r.reply)
    r = go("turn on seasonal touches")
    check("'turn on seasonal touches': on at once, no 'next update'",
          AN.values()["seasonal"] is True and "next update" not in r.reply and one_sentence(r.reply),
          r and r.reply)
    r = go("turn off the cute moments")
    check("'turn off the cute moments': off at once (owner, 2026-09-28)",
          AN.values()["cute_moments"] is False and one_sentence(r.reply), r and r.reply)
    i = Q.match("keep the robot still")
    check("the robot is named like the animals (a fifth face)", i and i.name == "animal_switch"
          and i.f == {"key": "still", "on": True}, i)
    r = go("turn on the sun and moon")
    check("'turn on the sun and moon': the sky's own switch, at once",
          SK.load()["show"] is True and one_sentence(r.reply), r and r.reply)
    r = go("hide the sun and moon")
    check("'hide the sun and moon': off", SK.load()["show"] is False, r and r.reply)
    SK.handle_post({"place": "Denver"}, here=True)
    SK.handle_post({"weather": "home_assistant"}, here=True)
    r = go("turn off the weather")
    check("'turn off the weather': off at once, from the phone too",
          SK.load()["weather"] == "off" and one_sentence(r.reply), r and r.reply)
    r = go("turn on the weather")
    check("'turn on the weather' names no source: asked, nothing changed",
          r.intent == "animal_ask" and "?" in r.reply and SK.load()["weather"] == "off",
          r and r.reply)
    fresh()


def t_open_meteo_still_raises_its_card():
    fresh()
    SK.handle_post({"place": "Denver"}, here=True)
    held, gates = [], []
    real_spawn, real_gate, real_tier = SK._spawn, SK._gate, SK._tier
    SK._spawn = held.append

    class Yes:
        allowed, outcome, tier, reason = True, "approved", "ask", "approved"

    SK._gate = lambda *a, **k: (gates.append(a), Yes())[1]
    SK._tier = lambda action: "ask"
    try:
        r = go("use open-meteo for the weather")
        check("asking for Open-Meteo raises the card and changes nothing yet",
              r and held and SK.load()["weather"] == "off" and "approv" in r.reply.lower(),
              r and r.reply)
        check("the answer is one plain sentence about the card", one_sentence(r.reply), r.reply)
        held[0]()
        check("only the card's yes switches it on", SK.load()["weather"] == "open_meteo"
              and gates and gates[0][0] == SK.CARD_ACTION)
        r = go("turn off the weather")
        check("turning it off again is at once", SK.load()["weather"] == "off", r and r.reply)
    finally:
        SK._spawn, SK._gate, SK._tier = real_spawn, real_gate, real_tier
    fresh()


def t_per_device_goes_in_the_header():
    fresh()
    before = AN.values()
    for phrase, change in (("make the animal sharper", "sharper"),
                           ("make the panda smoother", "smoother"),
                           ("make the robot sharper", "sharper"),
                           ("make the animal less sharp", "softer"),
                           ("set the animal's frame rate to 60", "frame_rate:60"),
                           ("set the sharpness to maximum", "sharpness:max"),
                           ("turn on auto adjust", "auto")):
        r = go(phrase)
        rf = Q.route_fields(r) if r else {}
        check(f"{phrase!r}: face_tuning={change!r} in X-Jarvis-Route, 'this device only'",
              r and r.face_tuning == change and rf.get("face_tuning") == change
              and "this device only" in r.reply, (r and r.reply, rf))
    check("the PC stored nothing for them", AN.values() == before
          and not AN.settings_path().exists())
    r = go("set the frame rate to 45")
    check("an unknown rate is asked back", r.intent == "animal_ask" and "?" in r.reply, r.reply)
    rf = Q.route_fields(go("set a timer for 5 minutes"))
    check("an ordinary quick answer carries no face_tuning", "face_tuning" not in rf, rf)


def t_unclear_is_asked_never_guessed():
    fresh()
    for phrase in ("turn off the animal", "make the animal bigger", "change the animal"):
        r = go(phrase)
        check(f"{phrase!r} is asked back", r and r.intent == "animal_ask" and "?" in r.reply
              and AN.values() == AN.DEFAULTS, r and r.reply)
    for phrase in ("turn off the lights", "stop", "what's the weather",
                   "remind me to feed the animal at 5pm", "open the door",
                   "turn on background learning", "stop focus"):
        i = Q.match(phrase)
        check(f"{phrase!r} is not taken for an animal option",
              i is None or not i.name.startswith("animal_"), i and i.name)


def t_only_the_owners_own_words():
    fresh()
    r = go("keep the animal still", provenance="shared")
    check("pasted or shared words change nothing", r is None and AN.values()["still"] is False)


def t_registry_and_sections():
    s = R.find_section("animal options")
    check("'open animal options' is a section", s is not None and s.id == "animal-options")
    i = Q.match("open animal options")
    check("... and opens it", i and i.name == "settings_open" and i.f["id"] == "animal-options")
    bool_names = {R._bare(n) for b in R.BOOL_SETTINGS for n in b.names}
    sec_names = {R._bare(n) for sct in R.SECTIONS for n in sct.names}
    clash = [n for sw in AN.SWITCHES for n in sw.names
             if AN._bare(n) in bool_names or AN._bare(n) in sec_names]
    check("no animal name is also a setting's or a section's", not clash, clash)
    check("is_command, so the learner skips them",
          all(Q.is_command(p) for p in ("keep the animal still", "turn off the weather",
                                        "make the animal sharper", "turn off the animal")))


# ============================================================ 5. route and patch


def t_install_wraps_the_route():
    fresh()
    hits = []

    class H:
        def __init__(self):
            self.sent = None
            self._body = b"{}"
            self.client_address = ("127.0.0.1", 5555)

        def do_GET(self):
            hits.append("get0")

        def do_POST(self):
            hits.append("post0")

        def _send(self, code, out):
            self.sent = (code, out)
            return self.sent

    ok = {"token": True}
    line = AN.install(H, origin_ok=lambda self: True, token_ok=lambda self: ok["token"],
                      read_body=lambda self: self._body)
    check("install returns a banner line", "Animal options" in line, line)
    h = H()
    h.path = "/api/animal"
    h.do_GET()
    check("GET /api/animal is answered here", h.sent[0] == 200 and h.sent[1]["available"])
    h = H()
    h.path = "/api/animal"
    h._body = json.dumps({"petting": False}).encode()
    h.do_POST()
    check("POST one change", h.sent[0] == 200 and AN.values()["petting"] is False, h.sent)
    ok["token"] = False
    h = H()
    h.path = "/api/animal"
    h.do_GET()
    check("a bad token is refused", h.sent[0] == 401)
    h2 = H()
    h2.path = "/api/sky"
    h2.do_GET()
    h2.do_POST()
    check("other routes pass through", hits == ["get0", "post0"], hits)
    check("installing twice is harmless", "already on" in AN.install(
        H, origin_ok=lambda self: True, token_ok=lambda self: True, read_body=lambda s: b""))
    fresh()


def t_the_patch():
    git = shutil.which("git")
    if not git:
        return check("SKIP - git is not installed", True)
    order = _stack.order()
    check("animal.patch is in apply-patches.ps1's list, after sky.patch",
          "animal.patch" in order and order.index("animal.patch") > order.index("sky.patch"))
    text, log = _stack.stand_in("jarvis_hud.py", order[:order.index("animal.patch")])
    check("the stand-in was built", text is not None, log)
    d = Path(tempfile.mkdtemp(prefix="jarvis-animal-patch-"))
    try:
        (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
        shutil.copyfile(HERE / "animal.patch", d / "p.patch")
        r = subprocess.run([git, "apply", "--include", "jarvis_hud.py", "p.patch"], cwd=d,
                           capture_output=True, text=True)
        check("animal.patch applies to what the earlier patches wrote", r.returncode == 0,
              r.stderr)
        after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        r = subprocess.run([git, "apply", "-R", "--include", "jarvis_hud.py", "p.patch"], cwd=d,
                           capture_output=True, text=True)
        check("... and reverses cleanly", r.returncode == 0
              and (d / "jarvis_hud.py").read_text(encoding="utf-8") == text, r.stderr)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    i = after.index("# animal.patch", after.index("def _appearance_view"))
    j = after.index("    try:\n        if APPEARANCE_FILE", i)
    blk = after[i:j]
    try:
        compile("def f():\n    doc = {}\n" + blk, "<view block>", "exec")
        check("the _appearance_view block compiles", "jarvis_animal.values()" in blk)
    except SyntaxError as exc:
        check("the _appearance_view block compiles", False, str(exc))
    i = after.index("# animal.patch (the owner's decisions of 2026-09-28, \"Animal options\"):\n"
                    "    # GET /api/animal")
    j = after.index("# Before the main socket", i)
    blk = after[i:j]
    check("the start-up block passes origin_ok/token_ok/read_body into jarvis_animal.install",
          "origin_ok=_origin_ok" in blk and "token_ok=_token_ok" in blk
          and "read_body=_read_body" in blk)
    try:
        compile("def f(self, bind, Handler):\n    " + blk, "<start-up block>", "exec")
        check("the start-up block compiles", True)
    except SyntaxError as exc:
        check("the start-up block compiles", False, str(exc))
    # The values really ride along in the appearance document.
    start = after.index("APPEARANCE_FILE = CONFIG_DIR")
    end = after.index("def _appearance_check")
    ns = {"json": json, "time": time, "Path": Path, "os": os, "CONFIG_DIR": TMP}
    exec(compile(after[start:end], "view", "exec"), ns)
    fresh()
    AN.set_switch("still", True)
    doc = ns["_appearance_view"]()
    check("GET /api/appearance carries the animal values", doc.get("animal", {}).get("still")
          is True, doc)
    import _where
    check("the module is shipped", "jarvis_animal.py" in _where.SHIPPED)
    fresh()


if __name__ == "__main__":
    for fn in (t_defaults, t_changes_at_once, t_device_words_and_steps,
               t_every_switch_by_every_name, t_asking_changes_the_pc,
               t_open_meteo_still_raises_its_card, t_per_device_goes_in_the_header,
               t_unclear_is_asked_never_guessed, t_only_the_owners_own_words,
               t_registry_and_sections, t_install_wraps_the_route, t_the_patch):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFAILED:")
        for f in FAILED:
            print(f"  {f}")
    sys.exit(1 if FAILED else 0)
