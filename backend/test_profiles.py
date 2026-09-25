"""The three presets' arithmetic, choices and words (jarvis_profiles.py).

    python3 test_profiles.py

What this proves, with no graphics card and no Ollama:

  - the model sizes and the room per card agree with the design's appendix
    (docs/HARDWARE-PROFILES.md 8.1 and 8.2), to the hundredth of a GB;
  - at llama.cpp's own 1 GB gap, the planner gives EVERY row of the design's
    section 4.4 tables - model, context, card, long lane, pictures and how
    they share, and each card's memory bar - so the code is the design;
  - at the owner's 0.75 GB gap it gives exactly the committed golden file
    (backend/fixtures/hardware_cases.json), and the design's generated table
    is that file (tools/gen_hardware_cases.py --check);
  - the special cases the build plan names: Ollama's own check refusing a
    14B beside chat on 24 GB, 6 GB refusing pictures, Vulkan -> the larger
    format, older-than-Pascal NVIDIA -> the larger format and never q8_0;
  - which card chat goes on (the fastest, never "the one with the monitor");
  - the one PowerShell line: only the allowed names and values, 5.1-safe,
    one line, always with its undo line - and PowerShell itself parses every
    generated line when /opt/pwsh/pwsh is there;
  - the tuned models keep jarvis-primary's rules word for word.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

for p in (REPO / "tools", HERE / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.append(str(p))

import jarvis_profiles as P  # noqa: E402
import gen_hardware_cases as G  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def nv(key, name, gb, **kw):
    """An NVIDIA Turing card unless told otherwise."""
    kw.setdefault("compute", "7.5")
    return P.Card(key, name, gb, **kw)


def near(a, b, tol=0.011):
    return a is not None and b is not None and abs(a - b) <= tol


# --------------------------------------------------------------------------

def t_model_sizes_match_the_appendix():
    # docs/HARDWARE-PROFILES.md 8.2: (model, context, format, need, Ollama's guess)
    rows = [("qwen3:4b", 8192, "q8_0", 3.14, 3.00), ("qwen3:4b", 12288, "q8_0", 3.44, None),
            ("qwen3:4b", 16384, "q8_0", 3.74, 3.70), ("qwen3:4b", 32768, "q8_0", 4.94, 5.11),
            ("qwen3:4b", 16384, "f16", 4.79, None),
            ("qwen3:8b", 6144, "q8_0", 5.42, None), ("qwen3:8b", 8192, "q8_0", 5.57, 5.80),
            ("qwen3:8b", 12288, "q8_0", 5.87, None), ("qwen3:8b", 16384, "q8_0", 6.17, 6.92),
            ("qwen3:8b", 32768, "q8_0", 7.36, 9.17), ("qwen3:8b", 8192, "f16", 6.10, None),
            ("qwen3:14b", 8192, "q8_0", 9.44, 9.67), ("qwen3:14b", 12288, "q8_0", 9.77, None),
            ("qwen3:14b", 16384, "q8_0", 10.10, 10.92), ("qwen3:14b", 32768, "q8_0", 11.43, 13.42),
            ("qwen2.5vl:3b", 4096, "q8_0", 3.58, 3.14), ("qwen2.5vl:3b", 8192, "q8_0", 3.65, 3.28),
            ("qwen2.5vl:7b", 8192, "q8_0", 6.38, 6.04)]
    for ref, ctx, kv, need, guess in rows:
        m = P.MODELS[ref]
        check(f"{ref} @ {ctx:,} {kv}: need {need}", near(m.need(ctx, kv), need),
              f"got {m.need(ctx, kv):.4f}")
        if guess is not None:
            check(f"{ref} @ {ctx:,}: Ollama's guess {guess}", near(m.ollama_guess(ctx), guess),
                  f"got {m.ollama_guess(ctx):.4f}")
    # 2.8: cache per token and computed downloads
    for ref, q8, f16 in (("qwen3:4b", 78336, 147456), ("qwen3:8b", 78336, 147456),
                         ("qwen3:14b", 87040, 163840), ("qwen2.5vl:3b", 19584, 36864),
                         ("qwen2.5vl:7b", 30464, 57344)):
        m = P.MODELS[ref]
        check(f"{ref}: {q8:,} B a token (q8_0), {f16:,} (f16)",
              m.kv_bytes("q8_0") == q8 and m.kv_bytes("f16") == f16)
    for ref, gb in (("qwen3:4b", 2.46), ("qwen3:8b", 5.02), ("qwen3:14b", 9.05),
                    ("qwen2.5vl:3b", 3.22), ("qwen2.5vl:7b", 6.01)):
        check(f"{ref}: about {gb} GB to download (computed)",
              near(P.MODELS[ref].download_gb, gb), f"{P.MODELS[ref].download_gb:.4f}")
    check("Qwen 3 4B's parameters, counted from its shape, are 4.02 billion",
          round(P.MODELS["qwen3:4b"].params / 1e9, 2) == 4.02)
    check("... and Qwen 3 14B's 14.77 billion",
          round(P.MODELS["qwen3:14b"].params / 1e9, 2) == 14.77)


def t_room_per_card_matches_the_appendix():
    # 8.1, at llama.cpp's 1 GB: total -> (monitor 1, monitor 2, none 1, none 2)
    table = {6: (3.57, 3.24, None, None), 8: (5.57, 5.24, 6.07, 5.74),
             10: (7.57, 7.24, 8.07, 7.74), 11: (8.57, 8.24, 9.07, 8.74),
             12: (9.57, 9.24, 10.07, 9.74), 16: (13.57, 13.24, 14.07, 13.74),
             24: (21.57, 21.24, None, None)}
    for gb, want in table.items():
        for (mon, procs), w in zip(((True, 1), (True, 2), (False, 1), (False, 2)), want):
            if w is None:
                continue
            c = nv("x", f"{gb} GB", gb, monitor=mon)
            check(f"{gb} GB, {'monitor' if mon else 'no monitor'}, {procs} model(s): room {w}",
                  near(P.room(c, procs, P.LLAMA_DEFAULT_GAP_GIB), w, 0.005))
    c = nv("x", "RTX 2080 SUPER", 8, monitor=True)
    check("the owner's 2080 SUPER at the decided 0.75 GB gap: 5.82 GB of room (4.2 at 0.75)",
          near(P.room(c), 5.82, 0.005))
    check("a measured desktop share replaces the placeholder",
          near(P.room(nv("x", "c", 8, monitor=True, share_gib=0.8)), 8 - 0.8 - 0.33 - 0.75))
    check("the gap is the owner's 0.75 GB (decision 1)", P.GAP_GIB == 0.75)


# (model, K, card) or None; long: "chat", None or (model, K, card); pictures:
# None or (model, K, mode, card); bars: {card: used GB}. Transcribed from the
# design's section 4.4 as written (at 1 GB).
EIGHT = {"fast": (("qwen3:4b", 32, "a"), "chat", None, {"a": 7.37}),
         "smart": (("qwen3:8b", 6, "a"), None, None, {"a": 7.85}),
         "features": (("qwen3:4b", 32, "a"), "chat", ("qwen2.5vl:3b", 8, "swap", "a"),
                      {"a": 7.37})}
TEN = {"fast": (("qwen3:4b", 32, "a"), "chat", None, {"a": 7.37}),
       "smart": (("qwen3:8b", 32, "a"), "chat", None, {"a": 9.79}),
       "features": (("qwen3:8b", 32, "a"), "chat", ("qwen2.5vl:3b", 8, "swap", "a"), {"a": 9.79})}
VULKAN = {"fast": (("qwen3:4b", 16, "a"), "chat", None, {"a": 7.22}),
          "smart": (("qwen3:4b", 16, "a"), "chat", None, {"a": 7.22}),
          "features": (("qwen3:4b", 16, "a"), "chat", ("qwen2.5vl:3b", 8, "swap", "a"),
                       {"a": 7.22})}
DOC_4_4 = {
    "one_6gb": {p: (("qwen3:4b", 12, "a"), "chat", None, {"a": 5.87})
                for p in ("fast", "smart", "features")},
    "one_8gb": EIGHT, "one_8gb_pascal": EIGHT, "one_8gb_rocm": EIGHT,
    "one_10gb": TEN, "one_11gb": TEN,
    "one_12gb": {"fast": (("qwen3:4b", 32, "a"), "chat", None, {"a": 7.37}),
                 "smart": (("qwen3:14b", 8, "a"), None, None, {"a": 11.87}),
                 "features": (("qwen3:8b", 32, "a"), "chat", ("qwen2.5vl:3b", 8, "swap", "a"),
                              {"a": 9.79})},
    "one_16gb": {"fast": (("qwen3:4b", 32, "a"), "chat", None, {"a": 7.37}),
                 "smart": (("qwen3:14b", 32, "a"), "chat", None, {"a": 13.86}),
                 "features": (("qwen3:8b", 32, "a"), "chat",
                              ("qwen2.5vl:3b", 8, "beside", "a"), {"a": 13.77})},
    "one_24gb": {"fast": (("qwen3:4b", 32, "a"), "chat", None, {"a": 7.37}),
                 "smart": (("qwen3:14b", 32, "a"), "chat", None, {"a": 13.86}),
                 "features": (("qwen3:8b", 32, "a"), "chat",
                              ("qwen2.5vl:7b", 8, "beside", "a"), {"a": 16.51})},
    "one_8gb_vulkan_amd": VULKAN, "one_8gb_vulkan_intel": VULKAN,
    "two_8_8": {"fast": (("qwen3:4b", 32, "a"), "chat", ("qwen2.5vl:3b", 8, "own", "b"),
                         {"a": 6.87, "b": 6.08}),
                "smart": (("qwen3:8b", 12, "a"), ("qwen3:4b", 32, "b"),
                          ("qwen2.5vl:3b", 8, "turns", "b"), {"a": 7.80, "b": 7.37})},
    "two_8_10_mon8": {"fast": (("qwen3:4b", 32, "a"), "chat", ("qwen2.5vl:7b", 8, "own", "b"),
                               {"a": 7.37, "b": 8.31}),
                      "smart": (("qwen3:8b", 32, "b"), "chat", ("qwen2.5vl:3b", 8, "own", "a"),
                                {"a": 6.08, "b": 9.29}),
                      "features": (("qwen3:8b", 6, "a"), ("qwen3:8b", 32, "b"),
                                   ("qwen2.5vl:7b", 8, "turns", "b"), {"a": 7.85, "b": 9.29})},
    "two_8_10_mon10": {"fast": (("qwen3:4b", 32, "a"), "chat", ("qwen2.5vl:7b", 8, "own", "b"),
                                {"a": 6.87, "b": 8.81}),
                       "smart": (("qwen3:8b", 12, "a"), ("qwen3:8b", 32, "b"),
                                 ("qwen2.5vl:7b", 8, "turns", "b"), {"a": 7.80, "b": 9.79})},
    "two_2080s_2080ti": {"fast": (("qwen3:4b", 32, "b"), "chat", ("qwen2.5vl:3b", 8, "own", "a"),
                                  {"a": 6.08, "b": 6.87}),
                         "smart": (("qwen3:8b", 32, "b"), "chat", ("qwen2.5vl:3b", 8, "own", "a"),
                                   {"a": 6.08, "b": 9.29}),
                         "features": (("qwen3:8b", 32, "b"), "chat",
                                      ("qwen2.5vl:3b", 8, "own", "a"), {"a": 6.08, "b": 9.29})},
    "two_2080s_2060_mon8": {
        "fast": (("qwen3:4b", 32, "a"), "chat", ("qwen2.5vl:7b", 8, "own", "b"),
                 {"a": 7.37, "b": 8.31}),
        "smart": (("qwen3:14b", 12, "b"), ("qwen3:4b", 32, "a"), ("qwen2.5vl:3b", 8, "turns", "a"),
                  {"a": 7.37, "b": 11.70}),
        "features": (("qwen3:8b", 6, "a"), ("qwen3:14b", 12, "b"),
                     ("qwen2.5vl:7b", 8, "turns", "b"), {"a": 7.85, "b": 11.70})},
    "two_2080s_2060_mon12": {
        "fast": (("qwen3:4b", 32, "a"), "chat", ("qwen2.5vl:7b", 8, "own", "b"),
                 {"a": 6.87, "b": 8.81}),
        "smart": (("qwen3:14b", 8, "b"), ("qwen3:4b", 32, "a"), ("qwen2.5vl:3b", 8, "turns", "a"),
                  {"a": 6.87, "b": 11.87}),
        "features": (("qwen3:8b", 12, "a"), ("qwen3:8b", 32, "b"),
                     ("qwen2.5vl:7b", 8, "turns", "b"), {"a": 7.80, "b": 9.79})},
    "two_8_16_mon8": {
        "fast": (("qwen3:4b", 32, "a"), "chat", ("qwen2.5vl:7b", 8, "own", "b"),
                 {"a": 7.37, "b": 8.31}),
        "smart": (("qwen3:14b", 32, "b"), "chat", ("qwen2.5vl:3b", 8, "own", "a"),
                  {"a": 6.08, "b": 13.36}),
        "features": (("qwen3:8b", 6, "a"), ("qwen3:14b", 16, "b"),
                     ("qwen2.5vl:7b", 8, "turns", "b"), {"a": 7.85, "b": 12.03})},
    "two_8_16_mon16": {
        "fast": (("qwen3:4b", 32, "a"), "chat", ("qwen2.5vl:7b", 8, "own", "b"),
                 {"a": 6.87, "b": 8.81}),
        "smart": (("qwen3:14b", 32, "b"), "chat", ("qwen2.5vl:3b", 8, "own", "a"),
                  {"a": 5.58, "b": 13.86}),
        "features": (("qwen3:8b", 12, "a"), ("qwen3:14b", 16, "b"),
                     ("qwen2.5vl:7b", 8, "turns", "b"), {"a": 7.80, "b": 12.53})},
    "two_12_12": {
        "fast": (("qwen3:4b", 32, "a"), "chat", ("qwen2.5vl:7b", 8, "own", "b"),
                 {"a": 6.87, "b": 8.81}),
        "smart": (("qwen3:14b", 12, "a"), ("qwen3:8b", 32, "b"), ("qwen2.5vl:7b", 8, "turns", "b"),
                  {"a": 11.70, "b": 9.79}),
        "features": (("qwen3:8b", 32, "a"), "chat", ("qwen2.5vl:7b", 8, "own", "b"),
                     {"a": 9.29, "b": 8.81})},
}
# "Same as Smartest" in the design:
DOC_4_4["two_8_8"]["features"] = DOC_4_4["two_8_8"]["smart"]
DOC_4_4["two_8_10_mon10"]["features"] = DOC_4_4["two_8_10_mon10"]["smart"]
# "8 + 11 GB - the same rows as 8 + 10" (the 11 GB card the slower one).
DOC_4_4["two_8_11_mon8"] = {p: (c, l, pi, {"a": b["a"], "b": b["b"]})
                            for p, (c, l, pi, b) in DOC_4_4["two_8_10_mon8"].items()}


def _got(lay):
    chat = (lay.chat.model.ref, lay.chat.ctx // 1024, lay.chat.card.key) if lay.chat else None
    if lay.long is not None:
        long = (lay.long.model.ref, lay.long.ctx // 1024, lay.long.card.key)
    else:
        long = "chat" if lay.long_is_chat else None
    pics = ((lay.pictures.model.ref, lay.pictures.ctx // 1024, lay.pictures.mode,
             lay.pictures.card.key) if lay.pictures else None)
    bars = {b.card.key: round(b.used_gib, 2) for b in lay.bars if b.models_gib}
    return chat, long, pics, bars


def t_every_row_of_the_design_at_1gb():
    cases = {cid: G.cards_of(cards) for cid, _, cards in G.PLAN_CASES}
    n = 0
    for cid, presets in DOC_4_4.items():
        for pid, (chat, long, pics, bars) in presets.items():
            lay = P.plan(cases[cid], pid, gap=P.LLAMA_DEFAULT_GAP_GIB)
            gchat, glong, gpics, gbars = _got(lay)
            ok = (gchat == chat and glong == long and gpics == pics
                  and set(gbars) == set(bars) and all(near(gbars[k], v) for k, v in bars.items()))
            n += 1
            check(f"design 4.4 at 1 GB: {cid} / {pid}", ok,
                  f"want {chat} {long} {pics} {bars}\n        got  {gchat} {glong} {gpics} {gbars}")
    check("every hardware case in the design's tables is checked (at least 60 rows)", n >= 60, n)


def t_bars_are_16_blocks():
    lay = P.plan(G.cards_of(dict((c[0], c[2]) for c in G.PLAN_CASES)["one_8gb"]), "fast",
                 gap=P.LLAMA_DEFAULT_GAP_GIB)
    check("8 GB fastest at 1 GB draws 15 of 16 blocks, as the design does",
          lay.bars[0].blocks == "\u2588" * 15 + "\u2591")
    over = P.Bar(nv("x", "c", 8, monitor=True), 7.0, 1, 1.0)
    check("a bar that is over the card is 16 full blocks, never more", over.blocks == "\u2588" * 16)


def t_the_golden_file_and_the_design_table():
    data = json.loads(G.PLAN_FIXTURE.read_text(encoding="utf-8"))
    check("the golden file is at the owner's 0.75 GB gap", data["gap_gib"] == 0.75)
    fresh = json.loads(G.render_plans())
    for cid in fresh["cases"]:
        check(f"golden: {cid} equals a fresh run of the planner",
              fresh["cases"][cid] == data["cases"].get(cid))
    check("the golden file names every case, no more, no fewer",
          set(fresh["cases"]) == set(data["cases"]))
    doc = G.DOC.read_text(encoding="utf-8")
    table = G.render_doc_table(data)
    check("docs/HARDWARE-PROFILES.md carries the generated table, word for word",
          table in doc, "run python3 tools/gen_hardware_cases.py")
    check("every file the tool writes matches (--check)", G.main(["--check"]) == 0)
    # What the owner will see on the PC today, at 0.75 GB:
    own = data["cases"]["one_8gb"]["presets"]
    check("the owner's 8 GB: Smartest is qwen3:8b with 8K (was 6K at 1 GB)",
          own["smart"]["chat"]["model"] == "qwen3:8b" and own["smart"]["chat"]["context"] == 8192)
    check("... and Smartest is the recommendation there (Most features would drop to the 4B)",
          data["cases"]["one_8gb"]["recommended"] == "smart")
    pair = data["cases"]["two_2080s_2060_mon8"]
    check("the planned pair: Most features keeps chat on the 2080 SUPER and is recommended",
          pair["presets"]["features"]["chat"]["card"] == "a" and pair["recommended"] == "features")


def t_the_named_special_cases():
    c24 = nv("a", "24 GB card", 24, monitor=True)
    lay = P.plan([c24], "features", gap=P.LLAMA_DEFAULT_GAP_GIB)
    free = 24 - 1.10 - 2 * 0.33 - lay.chat.need - lay.pictures.need
    check("24 GB: Ollama's own check would refuse a 14B wiki lane beside chat and pictures "
          "(10.92 predicted > 0.8 x 8.50), so none is planned",
          near(free, 8.50) and P.MODELS["qwen3:14b"].ollama_guess(16384) > 0.8 * free
          and lay.long is None, f"free {free:.2f}")
    c16 = nv("a", "16 GB card", 16, monitor=True)
    chat16 = P.plan([c16], "features", gap=P.LLAMA_DEFAULT_GAP_GIB).chat
    check("16 GB: Ollama's check passes the small picture model beside chat (3.28 <= 0.8 x 7.21)",
          P._gate_ok(chat16, P.MODELS["qwen2.5vl:3b"], 8192, c16))
    c6 = nv("a", "6 GB card", 6, monitor=True)
    lay6 = P.plan([c6], "features", gap=P.LLAMA_DEFAULT_GAP_GIB)
    check("6 GB at 1 GB: pictures refused, even swapping (3.58 at 4K > 3.47), said in words",
          lay6.pictures is None and any("does not fit" in o for o in lay6.off), lay6.off)
    check("6 GB at 0.75 GB: the small picture model fits by swapping",
          P.plan([c6], "features").pictures.mode == "swap")
    vk = nv("a", "RX 6600", 8, monitor=True, route="Vulkan", vendor="amd")
    lay = P.plan([vk], "smart")
    check("Vulkan: the larger format (f16), and the 8B does not fit at all",
          lay.chat.kv == "f16" and lay.chat.model.ref == "qwen3:4b")
    check("... and the one line sets f16 and does NOT switch Vulkan off on an AMD PC",
          ("OLLAMA_KV_CACHE_TYPE", "f16") in P.settings_for(lay)
          and all(n != "OLLAMA_VULKAN" for n, _ in P.settings_for(lay)))
    mx = nv("a", "Quadro M5000", 8, monitor=True, compute="5.2")
    lay = P.plan([mx], "fast")
    check("older than Pascal (5.2): f16, never q8_0 - q8_0 would stop models loading",
          lay.chat.kv == "f16" and ("OLLAMA_KV_CACHE_TYPE", "q8_0") not in P.settings_for(lay))
    check("Jetson's 7.2 is refused q8_0 too", P.kv_type(nv("a", "x", 8, compute="7.2"))[0] == "f16")
    check("Pascal gets q8_0, marked best effort, not tested",
          P.kv_type(nv("a", "GTX 1080", 8, compute="6.1"))[0] == "q8_0"
          and P.best_effort(nv("a", "GTX 1080", 8, compute="6.1")))
    check("AMD and Intel presets are marked best effort, not tested (decision 2)",
          P.plan([vk], "fast").best_effort and "not been tested" in P.plan([vk], "fast").best_effort[0])
    check("a Turing card is not marked best effort", not P.best_effort(nv("a", "x", 8)))
    unknown = P.kv_type(P.Card("a", "NVIDIA card", 8))
    check("an NVIDIA card whose generation could not be read gets f16, and says why",
          unknown[0] == "f16" and "could not tell" in unknown[1])
    none = P.plan([], "fast")
    check("no card at all: chat on the processor, said plainly", none.chat is None and
          "processor" in none.off[0])
    rx = dict((c[0], c[2]) for c in G.PLAN_CASES)["two_8_rx7600"]
    lay = P.plan(G.cards_of(rx), "features")
    check("NVIDIA + AMD: chat stays on the NVIDIA card (the AMD one is best effort)",
          lay.chat.card.name == "RTX 2080 SUPER", lay.chat.card.name)
    check("... and the AMD card gets no extra features, with the reason",
          lay.long is None and lay.pictures is None
          and any("only on an NVIDIA card" in o for o in lay.off), lay.off)


def t_which_card_chat_goes_on():
    s, t = nv("s", "RTX 2080 SUPER", 8, monitor=True, uuid="GPU-1111aaaa"), \
        nv("t", "RTX 2060", 12, monitor=False, uuid="GPU-2222bbbb")
    order, why = P.rank([t, s])
    check("the 2080 SUPER is first by published memory speed, even listed second, and even "
          "with the monitor on it", order[0] is s and "faster" in why, why)
    order, why = P.rank([s, t], primary="GPU-2222BBBB")
    check("[compute] primary_gpu overrides everything, by id", order[0] is t and "primary_gpu" in why)
    a, b = nv("a", "card", 8, monitor=True), nv("b", "card", 8, monitor=False)
    order, why = P.rank([a, b])
    check("two equal cards: the one with more room (no monitor)", order[0] is b, why)
    old, new = nv("o", "x", 8, compute="6.1"), nv("n", "y", 8, compute="8.6")
    check("unknown speeds: the newer generation", P.rank([old, new])[0][0] is new)
    check("the 2060 Super is not given the 2060's speed", P.published_speed("RTX 2060 SUPER") is None)


def t_measured_limits_drop_a_size():
    c = nv("a", "RTX 2080 SUPER", 8, monitor=True)
    lay = P.plan([c], "smart", limits={"chat": 6144})
    check("a measured spill caps chat to the next size down (8K -> 6K), not the processor",
          lay.chat.model.ref == "qwen3:8b" and lay.chat.ctx == 6144)
    lay = P.plan([c], "fast", limits={"chat": 16384})
    check("... for any preset", lay.chat.ctx == 16384)


ALLOWED_PART = re.compile(
    r"\[Environment\]::SetEnvironmentVariable\('([A-Z_]+)', ('[^']*'|\$null), 'User'\)"
    r"|Write-Host '[^']*'")


def _lines():
    """Every line the generator can emit for the committed cases."""
    data = json.loads(G.PLAN_FIXTURE.read_text(encoding="utf-8"))
    out = []
    for cid, case in data["cases"].items():
        for pid, p in case["presets"].items():
            settings = [tuple(x) for x in p["settings"]]
            out.append((f"{cid}/{pid}", P.one_line(settings), P.undo_line(settings),
                        P.undo_line(settings, {"OLLAMA_KV_CACHE_TYPE": "q8_0",
                                               "OLLAMA_KEEP_ALIVE": "-1"})))
    return out


def t_the_one_line():
    lines = _lines()
    bad = []
    for name, line, undo, undo2 in lines:
        for text in (line, undo, undo2):
            if text is None:
                continue
            parts = text.split("; ")
            if "\n" in text or "??" in text or "?." in text or "&&" in text or "||" in text:
                bad.append((name, "operator or newline", text))
            if not all(ALLOWED_PART.fullmatch(p) for p in parts):
                bad.append((name, "a part that is not allowed", text))
            names = [m.group(1) for p in parts for m in [ALLOWED_PART.fullmatch(p)] if m and m.group(1)]
            if not set(names) <= set(P.ALLOWED):
                bad.append((name, "a name that is not allowed", names))
            if sum(1 for p in parts if p.startswith("Write-Host")) != 1:
                bad.append((name, "not exactly one Write-Host", text))
    check("every generated line is one line of SetEnvironmentVariable(..., 'User') and one "
          "Write-Host, allowed names only, no PowerShell-7-only operators", not bad, bad[:3])
    check("every preset that sets something has an undo line",
          all((line is None) == (undo is None) for _, line, undo, _ in lines))
    pair = next(l for n, l, _, _ in lines if n == "two_2080s_2060_mon8/features")
    check("the planned pair's line, exactly: q8_0, keep-alive, the chat card's id, Vulkan off, "
          "the 0.75 GB gap (768 MiB)",
          pair == ("[Environment]::SetEnvironmentVariable('OLLAMA_KV_CACHE_TYPE', 'q8_0', 'User'); "
                   "[Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE', '-1', 'User'); "
                   f"[Environment]::SetEnvironmentVariable('CUDA_VISIBLE_DEVICES', '{G.U_2080S}', "
                   "'User'); [Environment]::SetEnvironmentVariable('OLLAMA_VULKAN', '0', 'User'); "
                   "[Environment]::SetEnvironmentVariable('LLAMA_ARG_FIT_TARGET', '768', 'User'); "
                   "Write-Host 'Saved 5 settings for your Windows user (nothing was written to a "
                   "file). Now quit Ollama (right-click its icon by the clock, then Quit Ollama) "
                   "and start it again from the Start menu.'"), pair)
    one = next(l for n, l, _, _ in lines if n == "one_8gb/smart")
    check("one card: no CUDA_VISIBLE_DEVICES (nothing to keep apart)",
          "CUDA_VISIBLE_DEVICES" not in one and "OLLAMA_VULKAN', '0'" in one)
    smart_pair = json.loads(G.PLAN_FIXTURE.read_text())["cases"]["two_2080s_2060_mon8"][
        "presets"]["smart"]["settings"]
    check("chat on the 2060 (Smartest, the planned pair): the everyday Ollama is pinned to the "
          "2060's id", ["CUDA_VISIBLE_DEVICES", G.U_2060] in smart_pair, smart_pair)
    undo = P.undo_line([("OLLAMA_KV_CACHE_TYPE", "q8_0"), ("OLLAMA_VULKAN", "0")],
                       {"OLLAMA_KV_CACHE_TYPE": "q8_0"})
    check("the undo puts back what was there before, and removes what was not",
          "'OLLAMA_KV_CACHE_TYPE', 'q8_0', 'User')" in undo
          and "'OLLAMA_VULKAN', $null, 'User')" in undo)
    undo = P.undo_line([("OLLAMA_KV_CACHE_TYPE", "q8_0")], {"OLLAMA_KV_CACHE_TYPE": "x'); evil"})
    check("... but never a value that does not look right: that one is removed instead",
          "evil" not in undo and "$null" in undo)
    for n, v in (("CUDA_VISIBLE_DEVICES", "GPU-1234abcd'; Remove-Item C:\\"),
                 ("OLLAMA_KV_CACHE_TYPE", "q4_0"), ("OLLAMA_HOST", "0.0.0.0"),
                 ("LLAMA_ARG_FIT_TARGET", "-1")):
        try:
            P.one_line([(n, v)])
            refused = False
        except ValueError:
            refused = True
        check(f"refused: {n}={v!r}", refused)
    check("the read-only check line is one line and names the five settings",
          "\n" not in P.CHECK_LINE and all(n in P.CHECK_LINE for n in P.ALLOWED))


def t_powershell_parses_every_line():
    pwsh = "/opt/pwsh/pwsh"
    if not os.path.exists(pwsh):
        return check("SKIP - no PowerShell here to parse the lines", True)
    texts = [P.CHECK_LINE]
    for _, line, undo, undo2 in _lines():
        texts += [t for t in (line, undo, undo2) if t]
    texts = sorted(set(texts))
    d = Path(tempfile.mkdtemp(prefix="jarvis-ps-"))
    src = d / "lines.json"
    src.write_text(json.dumps(texts), encoding="utf-8")
    probe = (f"$bad = 0; foreach ($s in (Get-Content -Raw -LiteralPath '{src}' | ConvertFrom-Json)) "
             "{ $t = $null; $e = $null; "
             "[void][System.Management.Automation.Language.Parser]::ParseInput($s, [ref]$t, [ref]$e); "
             "if ($e.Count -gt 0) { $bad++; Write-Output ('PARSE ' + $s) }; "
             "foreach ($k in $t) { if (@('QuestionQuestion','QuestionQuestionEquals','QuestionDot',"
             "'QuestionLBracket','AndAnd','OrOr') -contains $k.Kind.ToString()) "
             "{ $bad++; Write-Output ('PS7 ' + $k.Kind + ' ' + $s) } } }; Write-Output \"bad=$bad\"")
    try:
        r = subprocess.run([pwsh, "-NoProfile", "-NonInteractive", "-Command", probe],
                           capture_output=True, text=True, timeout=120)
    except Exception as exc:
        return check("SKIP - PowerShell would not start here", True, str(exc))
    check(f"PowerShell parses all {len(texts)} generated lines, with no PowerShell-7-only "
          f"token in any", r.stdout.strip().endswith("bad=0"), (r.stdout + r.stderr)[-800:])


def t_tuned_models_keep_jarvis_rules():
    mf = (HERE / "jarvis-primary.Modelfile").read_text(encoding="utf-8")
    m = re.search(r'SYSTEM """(.*?)"""', mf, re.S)
    check("jarvis-chat's rules are jarvis-primary's, word for word",
          m is not None and m.group(1) == P.JARVIS_SYSTEM)
    c = nv("a", "RTX 2080 SUPER", 8, monitor=True)
    lay = P.plan([c], "smart")
    text = P.modelfile(lay.chat)
    check("the Modelfile names its base and its context, and pins num_batch 512",
          text.startswith("FROM qwen3:8b\n") and "PARAMETER num_ctx 8192" in text
          and "PARAMETER num_batch 512" in text)
    for k in ("temperature 0.7", "top_p 0.8", "top_k 20", "repeat_penalty 1.05",
              'stop "<|im_end|>"'):
        check(f"... and keeps jarvis-primary's {k.split()[0]}", f"PARAMETER {k}" in text
              and f"PARAMETER {k}" in mf)
    req = P.create_request(lay.chat)
    check("Ollama's create request: the tuned name, the base, the same parameters",
          req["model"] == "jarvis-chat" and req["from"] == "qwen3:8b"
          and req["parameters"]["num_ctx"] == 8192 and req["stream"] is False
          and req["system"] == P.JARVIS_SYSTEM)
    check("a preset never overwrites jarvis-primary (4.8)", "jarvis-primary" not in P.TUNED.values())


def t_test_later_not_in_presets():
    check("Spark-X2.5 and Qwen 3.5 are listed to test later (decision 4, research 2026-09-24)",
          any("Spark-X2.5" in m for m, _ in P.TEST_LATER)
          and any("qwen3.5" in m for m, _ in P.TEST_LATER))
    data = G.render_plans()
    check("... and no preset uses either", "spark" not in data.lower() and "qwen3.5" not in data)
    check("only models the design justifies are in the table",
          set(P.MODELS) == {"qwen3:4b", "qwen3:8b", "qwen3:14b", "qwen2.5vl:3b", "qwen2.5vl:7b"})


def t_words():
    c = nv("a", "RTX 2080 SUPER", 8, monitor=True)
    d = P.describe(P.plan([c], "fast"))
    check("context in plain words: 32K is about 24 pages (an estimate, said so)",
          "about 24 pages" in d["chat"]["context_words"] and "estimate" in d["chat"]["context_words"])
    check("every preset says what is off, and why", all(
        P.describe(P.plan([c], p))["off"] for p in P.PRESET_IDS))
    check("the details say everything is calculated, not measured",
          d["details"][-1] == "Everything above is calculated, not measured.")
    check("no preset text carries a token-shaped string",
          not re.search(r"(?i)token['\"]?\s*[:=]|X-Jarvis-Token", json.dumps(d)))


def main():
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception as exc:  # pragma: no cover - a crash is a failure
                import traceback
                traceback.print_exc()
                check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
