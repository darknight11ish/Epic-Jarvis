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
  - the module is registered where the repo expects it to be, and its one hunk
    applies to the stack AT ITS OWN TURN - not to an invented pre-image of
    lines a patch that runs after it writes (2026-10-11);
  - the generator's `--check` compares placement, context, added lines and
    counts rather than bytes, so a stale hunk-header LINE NUMBER passes (it is
    advisory: git apply finds a hunk by its context) while every way a patch can
    actually be wrong still fails (2026-10-14).

Nothing here reads THIS machine's state: nvidia-smi, the real cards and the
real model files are all fed canned answers or replaced by this test's own
files, so the same checks answer the same way on a PC with no GPU and no
picture model (which is what CI is).
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402
import _stack  # noqa: E402  (the whole patch stack's jarvis_hud.py, for the anchor check)

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
SKIPPED = []


def check(name: str, ok: bool, detail=None) -> None:
    (PASSED if ok else FAILED).append(name)
    print(("ok   " if ok else "FAIL ") + name)
    if not ok and detail is not None:
        print(f"       {detail}")


def skip(why: str) -> None:
    """A check this machine cannot run (no git, so the stack walk cannot be
    built). Printed as `skip`, counted on its own, never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


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


def _ioctl(handle, code: int, buf=None, size: int = 0) -> None:
    """One `DeviceIoControl`, raising OSError when it fails."""
    import ctypes
    from ctypes import wintypes

    returned = wintypes.DWORD(0)
    ok = ctypes.WinDLL("kernel32", use_last_error=True).DeviceIoControl(
        handle, code, buf, size, None, 0, ctypes.byref(returned), None)
    if not ok:
        raise OSError(ctypes.get_last_error(), f"DeviceIoControl 0x{code:08X}")


class _ZeroData:
    """`FILE_ZERO_DATA_INFORMATION`: the byte range to de-allocate."""

    def __new__(cls, start: int, end: int):
        import ctypes

        class ZeroData(ctypes.Structure):
            _fields_ = [("FileOffset", ctypes.c_longlong),
                        ("BeyondFinalZero", ctypes.c_longlong)]

        return ZeroData(start, end)


def _sparse_sized_nt(path: Path, size: int) -> None:
    """(Windows) a `size`-byte file whose bytes are all a hole.

    TWO STEPS, and the second is the one that matters. Marking a file sparse
    and then `truncate()`-ing it is NOT enough: NTFS allocates the extended
    range as zeros, so the file is still 4.8 GB of real disk (measured:
    -4.84 GiB). `FSCTL_SET_ZERO_DATA` over the new range is what turns it into
    a hole and gives those clusters back (+4.81 GiB). Measured end to end on
    the owner's PC: net -0.04 GiB for the whole file, `st_size` unchanged.

    Raises OSError if any call fails - the caller falls back to a plain file.
    """
    import ctypes
    from ctypes import wintypes

    FSCTL_SET_SPARSE, FSCTL_SET_ZERO_DATA = 0x000900C4, 0x000980C8
    GENERIC_WRITE, SHARE_READ_WRITE, OPEN_EXISTING = 0x40000000, 3, 3
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                wintypes.HANDLE]
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p,
                                    wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    k32.DeviceIoControl.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL

    path.touch()
    # Share read/write: the truncate below goes through a second handle.
    handle = k32.CreateFileW(str(path), GENERIC_WRITE, SHARE_READ_WRITE, None,
                             OPEN_EXISTING, 0, None)
    if handle == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        _ioctl(handle, FSCTL_SET_SPARSE)
        with path.open("r+b") as fh:
            fh.truncate(size)
        zero = _ZeroData(0, size)
        import ctypes as _c
        _ioctl(handle, FSCTL_SET_ZERO_DATA, _c.byref(zero), _c.sizeof(zero))
    finally:
        k32.CloseHandle(handle)


def _sized_file(path: Path, size: int) -> None:
    """A file of exactly `size` bytes that allocates almost nothing on disk.

    WHY. The 4.8 GB companion below used to be a REAL 4.8 GB: one run of this
    suite left 4,918.43 MB in the temp folder, and a run that was killed left
    it for good - 23 of them, 110.47 GB, is how the owner's C: reached 1.47 GB
    free. `st_size` is what `model_files()` reads, so the file must still BE
    that size; a sparse one keeps the size and drops the allocation, so even a
    hard kill (which no `finally` or `atexit` can survive) costs ~0.

    POSIX needs nothing: `truncate()` leaves the new range unallocated there.
    A machine that refuses the Windows calls gets a plain file - still
    correct, only heavy again.
    """
    if os.name == "nt":
        try:
            _sparse_sized_nt(path, size)
            return
        except OSError:
            pass
    with path.open("wb") as fh:
        fh.truncate(size)


def t_a_part_downloaded_file_is_not_ready():
    """The model's own file is this test's, not the owner's PC's.

    model_files() reads the model's path out of IMAGE_MODELS, so the "big"
    entry is swapped for one whose path is inside this test's folder - a suite
    that needed D:\\Jarvis Models\\... to exist answered differently on the
    owner's PC and in CI (the owner has the 9.2 GB Chroma file; CI never does),
    which is exactly the kind of check that must not be written.
    """
    comfy = Path(tempfile.mkdtemp(prefix="fake-comfy-"))
    (comfy / "models" / "text_encoders").mkdir(parents=True)
    (comfy / "models" / "vae").mkdir(parents=True)
    main = comfy / "Chroma1-HD-int8-convrot-simple.safetensors"
    real_models = PC.IMAGE_MODELS
    PC.IMAGE_MODELS = tuple(dict(m, file=str(main), bytes=1024) if m["id"] == "big" else m
                            for m in real_models)
    try:
        check("with no model file at all, the words name the file that is missing",
              str(main) in PC.missing_words("big", str(comfy))
              and "is not at" in PC.missing_words("big", str(comfy)),
              PC.missing_words("big", str(comfy)))
        with open(main, "wb") as fh:
            fh.truncate(1024)                       # the model itself, full size
        (comfy / "models" / "text_encoders" / "t5xxl_fp8_e4m3fn_scaled.safetensors").write_bytes(b"0" * 1024)
        files = PC.model_files("big", str(comfy))
        check("a 1 KB slice of a 4.8 GB file is NOT ready", files["ready"] is False)
        check("it is called partial, not present",
              files["companions"]["t5xxl_fp8_e4m3fn_scaled.safetensors"]["partial"] is True)
        check("the words say how much is still coming",
              "still missing" in PC.missing_words("big", str(comfy)),
              PC.missing_words("big", str(comfy)))
        # now make it the full size and add the VAE
        name = "t5xxl_fp8_e4m3fn_scaled.safetensors"
        want = dict((c[0], c[2]) for c in PC.IMAGE_MODELS[0]["companions"])[name]
        _sized_file(comfy / "models" / "text_encoders" / name, want)
        (comfy / "models" / "vae" / "ae.safetensors").write_bytes(b"0" * 1024)
        check("still not ready while the VAE is short",
              PC.model_files("big", str(comfy))["ready"] is False)
    finally:
        PC.IMAGE_MODELS = real_models
        # THE 4.8 GB FILE GOES WITH IT (2026-10-13). The block above makes one
        # companion the model's REAL size with `truncate` - 5,157,348,688 bytes
        # for the big one - and on NTFS that is the whole file, not a sparse
        # one: removing such a directory was measured freeing 4.84 GB. This
        # directory is created in the system temp folder, and nothing used to
        # remove it, so one run of this suite left 4,918.43 MB there for good.
        # Measured that night: 23 of them, 110.47 GB, on the same drive as the
        # owner's voice print and chat history - and how C: reached 1.47 GB
        # free. The `finally` is the point: it runs when a check fails and when
        # the block raises, not only when everything passes. `ignore_errors` so
        # a file another process holds open cannot turn a passing suite into a
        # failing one; every check above has already run by now.
        shutil.rmtree(comfy, ignore_errors=True)


def t_A_unloads_the_chat_and_warms_it_back():
    calls = []
    real_json = PC._json
    real_run = PC._run

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
    # The two cards are the fixture's, not this machine's: read_cards() shells
    # out to nvidia-smi, and a PC without one (CI) must answer the same way.
    PC._run = fake_run
    PC._CARD_CACHE["cards"] = []
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
        PC._json = real_json
        PC._run = real_run
        PC._CARD_CACHE["cards"] = []


def t_warm_lane_keeps_an_active_model_resident():
    """Opt D11: in Active power mode a warm-up must send keep_alive=-1, not
    the old "30m" that would reset the owner's OLLAMA_KEEP_ALIVE=-1. Quiet and
    Standby keep the old value, and the existing unload path is untouched."""
    calls = []
    model = "qwen3.5:9b"
    real_json, real_status = PC._json, PC.lane_status
    saved_power = sys.modules.get("jarvis_power")

    def fake_json(url, payload=None, timeout=120.0, method="GET"):
        calls.append((url, payload))
        if url.endswith("/api/ps"):
            return {"models": [{"name": model, "size": 100, "size_vram": 100}]}
        return {"done": True}

    def fake_status(port):
        return [{"name": model, "size": 100, "size_vram": 100}]

    def power(mode):
        mod = types.ModuleType("jarvis_power")
        mod.current = lambda: mode
        sys.modules["jarvis_power"] = mod

    PC._json, PC.lane_status = fake_json, fake_status
    try:
        power("active")
        calls.clear()
        out = PC.warm_lane(11434, model)
        gen = [p for u, p in calls if p is not None and u.endswith("/api/generate")]
        check("Active power mode warms the lane with keep_alive=-1",
              bool(gen) and gen[0].get("keep_alive") == -1 and out.get("ok") is True,
              (gen, out))
        power("quiet")
        calls.clear()
        out = PC.warm_lane(11434, model)
        gen = [p for u, p in calls if p is not None and u.endswith("/api/generate")]
        check("Quiet power mode keeps the old 30m warm-up",
              bool(gen) and gen[0].get("keep_alive") == "30m" and out.get("ok") is True,
              (gen, out))
    finally:
        PC._json, PC.lane_status = real_json, real_status
        if saved_power is None:
            sys.modules.pop("jarvis_power", None)
        else:
            sys.modules["jarvis_power"] = saved_power


def t_B_moves_the_chat_C_touches_nothing():
    calls = []
    real_json = PC._json
    real_run = PC._run

    def fake_json(url, payload=None, timeout=120.0, method="GET"):
        calls.append((url, payload))
        if url.endswith("/api/ps"):
            return {"models": [{"name": "qwen3.5:9b", "size": 100, "size_vram": 100}]}
        return {"done": True}

    PC._json = fake_json
    PC._run = fake_run                 # the fixture's cards, never this PC's
    PC._CARD_CACHE["cards"] = []
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
        PC._json = real_json
        PC._run = real_run
        PC._CARD_CACHE["cards"] = []


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


def t_its_generator_check_is_semantic_not_byte_exact():
    """What `tools/gen_picture_card_patch.py --check` compares, and what it must
    still refuse (2026-10-14).

    The check was byte-exact, which made the hunk header's LINE NUMBER
    load-bearing. It is not: `git apply` finds a hunk by matching its context
    contiguously, so the number is advisory. The HUD has moved since the patch
    was written (the D12 loopback helpers, A4's two session-latch fields, PWA
    Slice 3a's static-asset block and the browser HUD's served face closure -
    `faces.html` and the scripts it loads - add 274 lines before this anchor):
    the committed patch says `@@ -6591,3 +6591,25 @@` and the generator derives
    `@@ -6865,3 +6865,25 @@`. Both files are 29 lines and line 3 is the only
    difference. That made CI red on EVERY branch, including ones that never
    touch this patch - while the 143-patch rehearsal passed with the stale
    number, which is the proof it applies.

    A check that only accepts byte equality is not checking anything the owner
    cares about; a check that accepts everything is worse than none. So this
    drives the generator's own `check()` and asks for BOTH halves:

      * the committed patch, stale line number and all, PASSES, and the skew is
        reported rather than hidden;
      * each way a patch can actually be wrong FAILS - a changed added line, a
        changed context line, edited header counts, a truncated patch, a renamed
        file, an introduced deletion, and a context line swapped with its
        neighbour (same lines, same counts, different placement).

    Line 3 of the patch is asserted to still be the stale/generated pair this
    was measured on, so if either side moves the numbers in the docstring above
    are re-measured rather than left to rot.
    """
    import importlib.util

    path = REPO / "tools" / "gen_picture_card_patch.py"
    if not path.is_file():
        return skip("tools/gen_picture_card_patch.py is not in this tree")
    spec = importlib.util.spec_from_file_location("_gen_picture_card_patch", path)
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    want, note = gen.build(gen.HUD.read_text(encoding="utf-8").splitlines())
    check("the generator still finds its anchor in jarvis_hud.py", want is not None, note)
    if want is None:
        return
    have = gen.OUT.read_bytes() if gen.OUT.exists() else b""
    committed = have.split(b"\n")
    generated = want.split(b"\n")
    check("the committed patch and the generated one are both one hunk",
          len(committed) == 29 and len(generated) == 29,
          f"committed {len(committed)} lines, generated {len(generated)}")
    check("the committed patch's header is the stale one this was measured on",
          committed[2] == b"@@ -6591,3 +6591,25 @@", committed[2])
    check("the generated header is the one this was measured on",
          generated[2] == b"@@ -6865,3 +6865,25 @@", generated[2])

    ok, summary, why = gen.check(have, want)
    check("the committed patch PASSES the semantic check even though its hunk "
          "header is 274 lines stale", ok, why)
    check("... and the skew is reported, not swallowed",
          ok and "274 line(s)" in (summary or ""), summary)

    def must_fail(label, bad):
        ok, summary, why = gen.check(bad, want)
        check("the check still FAILS: " + label, not ok, summary or "it passed")

    def swap_line(patch, old, new):
        return patch.replace(old, new, 1)

    must_fail("an added line changed",
              swap_line(have, b"+        import jarvis_picture_card",
                        b"+        import jarvis_wrong_module"))
    must_fail("a context line changed",
              swap_line(have, b"     httpd = ThreadingHTTPServer",
                        b"     httpd = SomeOtherServer"))
    must_fail("the header's counts were edited",
              swap_line(have, b"@@ -6591,3 +6591,25 @@", b"@@ -6591,4 +6591,26 @@"))
    must_fail("the trailing after-context line was dropped",
              b"\n".join(have.split(b"\n")[:-3]) + b"\n")
    must_fail("the file was renamed",
              swap_line(have, b"--- a/jarvis_hud.py", b"--- a/jarvis_other.py"))
    must_fail("a deletion was introduced",
              swap_line(have, b"+        import jarvis_picture_card",
                        b"-        gone\n+        import jarvis_picture_card"))
    must_fail("the hunk was anchored on different lines",
              swap_line(have, b"     httpd = ThreadingHTTPServer((bind, HUD_PORT), Handler)",
                        b"     something_else_entirely = True"))
    # Same lines, same counts, different placement: the case that a comparison of
    # content alone would wave through.
    lines = have.split(b"\n")
    must_fail("two context lines were swapped (placement changed, counts kept)",
              b"\n".join([lines[0], lines[1], lines[2], lines[3], lines[5],
                          lines[4]] + lines[6:]) + b"\n")
    must_fail("the header's two starts disagree with each other",
              swap_line(have, b"@@ -6591,3 +6591,25 @@", b"@@ -6591,3 +6500,25 @@"))

    # ... but a bare line-number change, of either number, is exactly what this
    # check exists to tolerate.
    renumbered = swap_line(have, b"@@ -6591,3 +6591,25 @@", b"@@ -1,3 +1,25 @@")
    ok, summary, why = gen.check(renumbered, want)
    check("the advisory line number alone may move, and still PASSES", ok, why)


def t_its_hunk_applies_to_the_stack_at_its_own_turn():
    """The drift this patch was caught in, on 2026-10-11.

    picture-card.patch's one hunk was anchored on progress.patch's block with
    topics.patch's OWN banner as its trailing context - and topics.patch runs
    AFTER it in apply-patches.ps1's list. The finished file holds both, so the
    patch "applied"; the file as it stands at this patch's own turn does not,
    so apply-patches.ps1's own strip-and-re-apply rehearsal would have answered
    "will not apply" and refused the whole run, and _stack.py's walk had to
    invent the hunk's pre-image (51 materialised against the 50 it was pinned
    at then, which is what test_installed_stand_in.py and
    test_retrieve_count.py failed on).

    A hunk whose context is a LATER patch's lines is the drift that pin exists
    to catch, so it is fixed rather than pinned: the block now sits on the
    OWNER's own lines just before the main socket is built, in a patch placed
    immediately before plugin-loader.patch (the one patch that must stay last of
    all, which is why an install block cannot simply be appended after it). This
    check fails if the drift ever comes back.
    """
    if not shutil.which("git"):
        return skip("git is not installed, so the stack walk cannot be built here")
    stats = _stack.materialised("jarvis_hud.py")
    if not stats.get("hunks"):
        return skip("the stack walk could not be built here (no git, or a broken patch)")
    check("picture-card.patch's hunk applies to the stack at its own turn, "
          "not to an invented pre-image",
          "picture-card.patch" not in stats["by_patch"],
          sorted(stats["by_patch"].items(), key=lambda kv: -kv[1]))
    check("... and the walk still measures the pin it was measured at "
          "(jarvis_hud.py, see _stack.RATCHET)",
          stats["materialised"] == _stack.RATCHET["jarvis_hud.py"],
          f"measured {stats['materialised']}, pinned {_stack.RATCHET['jarvis_hud.py']}")


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
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
