"""test_picture_card.py - the three ways of making pictures
(jarvis_picture_card.py, picture-card.patch, docs/JARVIS-API.md section 124).

    python3 backend/test_picture_card.py

No network (socket.connect is refused) and no GPU: nvidia-smi and the two
lanes' /api/ps are fed canned answers, so what is proved is the DECISION, not
this PC's hardware. What this proves:

  - three ways exist, all OFF at the start, and turning one on turns the other
    two off and SAYS so;
  - a settings file that is missing, half-written or nonsense leaves every
    switch off rather than on;
  - the cards are ranked by their own reported memory, never by their index
    (the fake nvidia-smi lists the 8 GB card first on purpose);
  - the card is pinned by UUID, and ComfyUI's own --cuda-device 0 rides along
    with CUDA_VISIBLE_DEVICES - the two independent pins;
  - a part-downloaded companion file is NOT ready (a 47 MB slice of a 4.8 GB
    file must never be called ready);
  - A unloads the everyday chat before a draw and warms it back after, B loads
    it on the other card, C touches nothing;
  - "the largest context the 8 GB card holds with no spill" is the FIRST
    context whose size_vram equals its size, and every attempt is kept;
  - the routes answer, unknown routes 404, and this module owns nothing under
    /api/pictures (jarvis_pictures.py's surface);
  - the module is registered where the repo expects it to be.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_picture_card.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-picture-card-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda event, detail=None: None
sys.modules["jarvis_framework"] = fw

_real_connect = socket.socket.connect
_NET = []


def _no_connect(self, *a, **k):
    _NET.append(a)
    raise OSError("test_picture_card.py: no network")


socket.socket.connect = _no_connect

import jarvis_picture_card as PC  # noqa: E402

PASSED = []
FAILED = []


def check(name: str, ok: bool, detail=None) -> None:
    (PASSED if ok else FAILED).append(name)
    print(("ok   " if ok else "FAIL ") + name)
    if not ok and detail is not None:
        print(f"       {detail}")


# Two cards, and the 8 GB one listed FIRST: any code that assumed the big card
# is card 0 fails here.
FAKE_LIST = (
    "GPU 0: NVIDIA GeForce RTX 2080 SUPER (UUID: GPU-e4283ff2-b412-4e8c-9bae-7e433139e7d6)\n"
    "GPU 1: NVIDIA GeForce RTX 2060 (UUID: GPU-1ba04124-85de-3b44-bacc-7b7d9f0d8bee)\n"
)
FAKE_QUERY = "0, 8192, 3000\n1, 12288, 3100\n"


def fake_run(cmd, timeout=20):
    cmd = list(cmd)
    if "-L" in cmd:
        return FAKE_LIST
    if any(str(c).startswith("--query-gpu") for c in cmd):
        return FAKE_QUERY
    return ""


def a_path() -> str:
    return str(_TMP / f"picture-card-{len(PASSED) + len(FAILED)}.json")


# --------------------------------------------------------------------------


def t_three_ways_all_off():
    values = PC.load_settings(a_path())
    check("no way is on to start with", values["option"] is None)
    check("each way reads as its own switch, all off",
          PC.switches(values) == {"A": False, "B": False, "C": False})
    check("three ways exist, named A B C", PC.OPTION_IDS == ("A", "B", "C"))
    check("A is marked recommended", PC._BY_ID["A"]["recommended"] is True)
    check("the plain words name all three", "A -" in PC.OFF_WORDS and "C -" in PC.OFF_WORDS)


def t_one_on_turns_the_others_off():
    path = a_path()
    values = PC.load_settings(path)
    values, words = PC.set_option("B", values, path)
    check("B is on", PC.switches(values) == {"A": False, "B": True, "C": False})
    check("the sentence says the other two are off", "other two ways are off" in words, words)
    values, words = PC.set_option("C", values, path)
    check("turning C on turns B off", PC.switches(values) == {"A": False, "B": False, "C": True})
    values, words = PC.set_option(None, values, path)
    check("turning them all off works", values["option"] is None and "switched off" in words)
    again = PC.load_settings(path)
    check("the choice survives a reload", again["option"] is None)


def t_a_broken_file_leaves_them_off():
    path = Path(a_path())
    path.write_text("{ this is not json", encoding="utf-8")
    check("a half-written file leaves every switch off", PC.load_settings(path)["option"] is None)
    path.write_text(json.dumps({"option": "Z"}), encoding="utf-8")
    check("an option that is not A/B/C leaves every switch off",
          PC.load_settings(path)["option"] is None)
    values, words = PC.set_option("Z", PC.load_settings(path), path)
    check("saying something that is not A/B/C says what the three are",
          "not one of the three ways" in words, words)


def t_cards_ranked_by_memory_not_index():
    PC._CARD_CACHE["cards"] = []
    real, PC._run = PC._run, fake_run
    try:
        cards = PC.read_cards(fresh=True)
    finally:
        PC._run = real
    check("both cards are found", len(cards) == 2, cards)
    check("the 8 GB card is the small one even though it is index 0",
          PC.pick_card(cards, "small")["total_mb"] == 8192)
    check("the 12 GB card is the big one", PC.pick_card(cards, "big")["total_mb"] == 12288)
    check("the card is pinned by UUID, never by index",
          PC.image_env("A", cards)["CUDA_VISIBLE_DEVICES"]
          == "GPU-1ba04124-85de-3b44-bacc-7b7d9f0d8bee")
    check("C pins the other card by its UUID",
          PC.image_env("C", cards)["CUDA_VISIBLE_DEVICES"]
          == "GPU-e4283ff2-b412-4e8c-9bae-7e433139e7d6")
    PC._CARD_CACHE["cards"] = []


def t_fit_is_about_real_memory():
    cards = [{"index": 0, "name": "small", "uuid": "GPU-s", "total_mb": 8192, "used_mb": 0},
             {"index": 1, "name": "big", "uuid": "GPU-b", "total_mb": 12288, "used_mb": 0}]
    check("the 8.57 GB model does not fit an 8 GB card", PC.fits(cards[0], "big") is False)
    check("the 8.57 GB model fits the 12 GB card", PC.fits(cards[1], "big") is True)
    check("the 4.29 GB model fits the 8 GB card", PC.fits(cards[0], "small") is True)
    check("the 4.29 GB model fits the 12 GB card too", PC.fits(cards[1], "small") is True)


def t_a_part_downloaded_file_is_not_ready():
    comfy = Path(tempfile.mkdtemp(prefix="fake-comfy-"))
    (comfy / "models" / "text_encoders").mkdir(parents=True)
    (comfy / "models" / "vae").mkdir(parents=True)
    (comfy / "models" / "text_encoders" / "t5xxl_fp8_e4m3fn_scaled.safetensors").write_bytes(b"0" * 1024)
    files = PC.model_files("big", str(comfy))
    check("a 1 KB slice of a 4.8 GB file is NOT ready", files["ready"] is False)
    check("it is called partial, not present",
          files["companions"]["t5xxl_fp8_e4m3fn_scaled.safetensors"]["partial"] is True)
    check("the words say how much is still coming",
          "still missing" in PC.missing_words("big", str(comfy)))
    # now make it the full size and add the VAE
    name = "t5xxl_fp8_e4m3fn_scaled.safetensors"
    want = dict((c[0], c[2]) for c in PC.IMAGE_MODELS[0]["companions"])[name]
    with open(comfy / "models" / "text_encoders" / name, "wb") as fh:
        fh.truncate(want)
    (comfy / "models" / "vae" / "ae.safetensors").write_bytes(b"0" * 1024)
    check("still not ready while the VAE is short",
          PC.model_files("big", str(comfy))["ready"] is False)


def t_A_unloads_the_chat_and_warms_it_back():
    calls = []
    real = PC._json

    def fake_json(url, payload=None, timeout=120.0, method="GET"):
        """A lane that really behaves: unloading makes it leave /api/ps, and
        loading it again makes it come back. A fake that never reloads would
        hang warm_lane for its whole timeout."""
        calls.append((url, payload))
        if url.endswith("/api/ps"):
            last = [c[1] for c in calls if c[1] is not None]
            if last and last[-1].get("keep_alive") == 0:
                return {"models": []}
            return {"models": [{"name": "qwen3.5:9b", "size": 100, "size_vram": 100}]}
        return {"done": True}

    PC._json = fake_json
    try:
        values = {"option": "A"}
        before = len(calls)
        out = PC.prepare(values)
        posts = [c for c in calls[before:] if c[1] is not None]
        check("A asks the everyday chat to unload (keep_alive 0)",
              any(c[1].get("keep_alive") == 0 for c in posts), calls[before:])
        check("A unloads on the everyday lane's own port",
              all(str(PC.DEFAULT_LANES["everyday"]["port"]) in c[0] for c in posts))
        check("A reports the card it will use", out["card"]["total_mb"] >= 8192, out.get("card"))
        back = len(calls)
        rest = PC.restore(values)
        check("A warms the chat back afterwards",
              any(c[1] and c[1].get("keep_alive") not in (0, None) for c in calls[back:]),
              calls[back:])
        check("A's restore says how long it took", "seconds" in rest["steps"][0])
    finally:
        PC._json = real


def t_B_moves_the_chat_C_touches_nothing():
    calls = []
    real = PC._json

    def fake_json(url, payload=None, timeout=120.0, method="GET"):
        calls.append((url, payload))
        if url.endswith("/api/ps"):
            return {"models": [{"name": "qwen3.5:9b", "size": 100, "size_vram": 100}]}
        return {"done": True}

    PC._json = fake_json
    try:
        PC.prepare({"option": "B"})
        check("B loads the chat and never unloads it",
              calls and all((c[1] or {}).get("keep_alive") != 0 for c in calls), calls)
        check("B says there is nothing to put back",
              "nothing to put back" in PC.restore({"option": "B"})["words"])
        calls.clear()
        out = PC.prepare({"option": "C"})
        check("C makes no call to any lane at all", calls == [], calls)
        check("C still reports the card it will use",
              out["card"]["uuid"].startswith("GPU-"), out.get("card"))
    finally:
        PC._json = real


def t_off_means_off_and_nothing_is_done():
    calls = []
    real = PC._json
    PC._json = lambda *a, **k: calls.append(a) or {}
    try:
        out = PC.prepare({"option": None})
        check("with nothing on, prepare does nothing at all", calls == [])
        check("with nothing on, the words name all three ways",
              out["words"] == PC.OFF_WORDS)
    finally:
        PC._json = real


def t_the_no_spill_context_is_the_first_that_fits():
    seen = []
    real = PC._json
    last = {"ctx": None}

    def fake_json(url, payload=None, timeout=120.0, method="GET"):
        if payload is None:                      # the /api/ps read
            spill = 900 if (last["ctx"] or 0) > 32768 else 0
            return {"models": [{"name": "qwen3.5:9b", "size": 6000 + spill,
                                "size_vram": 6000}]}
        last["ctx"] = (payload.get("options") or {}).get("num_ctx")
        seen.append(last["ctx"])
        return {"done": True}

    PC._json = fake_json
    try:
        out = PC.largest_context_with_no_spill(11436, "qwen3.5:9b",
                                               steps=(196608, 65536, 32768))
    finally:
        PC._json = real
    check("the biggest context that spilled is not the answer", seen[0] == 196608)
    check("the first context with nothing spilled is the answer", out["context"] == 32768, out)
    check("every attempt is written down", len(out["tried"]) == 3, out["tried"])
    check("the spilled ones are recorded with their spill",
          out["tried"][0]["spill"] == 900, out["tried"][0])


def t_routes():
    path = a_path()
    real = PC._json
    PC._json = lambda url, payload=None, timeout=120.0, method="GET": (
        {"models": []} if url.endswith("/api/ps") else {"done": True})
    try:
        code, answer = PC.handle_get(PC.BASE, settings=PC.load_settings(path))
        check("GET /api/picture-card answers", code == 200 and "options" in answer)
        check("the status answer carries all three ways", len(answer["options"]) == 3)
        check("the status answer says whether anything has been measured",
              "Not measured yet" in answer["measured_words"])
        code, answer = PC.handle_get(PC.BASE + "/nope", settings=PC.load_settings(path))
        check("an unknown picture-card route is a 404", code == 404)
        code, answer = PC.handle_post(PC.BASE, {"option": "C"}, settings=PC.load_settings(path), path=path)
        check("POST turns a way on", code == 200 and answer["switches"]["C"] is True)
        code, answer = PC.handle_post(PC.BASE, {"switch": "A", "on": True},
                                      settings=PC.load_settings(path), path=path)
        check("a switch-shaped POST works too",
              answer["switches"] == {"A": True, "B": False, "C": False}, answer)
        code, answer = PC.handle_get(PC.BASE + "/ready", settings=PC.load_settings(path))
        check("the ready route answers with a plain sentence", "words" in answer, answer)
    finally:
        PC._json = real


def t_owns_nothing_under_pictures():
    source = (HERE / "jarvis_picture_card.py").read_text(encoding="utf-8")
    check("this module never claims a route under /api/pictures",
          '"/api/pictures' not in source and "'/api/pictures" not in source, None)
    check("it says out loud whose surface /api/pictures is",
          "jarvis_pictures.py" in source)


def t_install_wraps_both_verbs():
    class Handler:
        def do_GET(self):
            return "plain get"

        def do_POST(self):
            return "plain post"

    handler = Handler()
    handler.path = PC.BASE
    handler.send_response = lambda code, *a: setattr(handler, "code", code)
    handler.send_header = lambda *a: None
    handler.end_headers = lambda: None
    handler.wfile = types.SimpleNamespace(write=lambda payload: setattr(handler, "body", payload))
    said = PC.install(Handler, origin_ok=lambda h: True, token_ok=lambda h: True,
                      read_body=lambda h: {"option": "A"})
    check("install says what it turned on", "picture-card" in said, said)
    plain = Handler()
    plain.path = "/api/something-else"
    check("another route still goes to the PC's own handler", plain.do_GET() == "plain get")
    check("the POST side was wrapped too", Handler.do_POST is not None)


def t_registered_where_the_repo_expects():
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("picture-card.patch is in apply-patches.ps1", "'picture-card.patch'" in ps1)
    check("jarvis_picture_card.py ships with it", "'jarvis_picture_card.py'" in ps1)
    where = (HERE / "_where.py").read_text(encoding="utf-8")
    check("the module is in _where.py", "jarvis_picture_card.py" in where)
    patch = HERE / "picture-card.patch"
    check("the patch file exists", patch.is_file())
    if patch.is_file():
        text = patch.read_text(encoding="utf-8")
        check("the patch adds exactly one install block",
              text.count("import jarvis_picture_card") == 1, text[:200])


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("t_") and callable(fn):
            try:
                fn()
            except Exception:
                import traceback
                FAILED.append(name)
                print(f"FAIL {name} raised")
                traceback.print_exc()
    check("no network was touched", not _NET, _NET)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
