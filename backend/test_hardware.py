"""Finding the cards, the steps of a preset, making a tuned model, measuring,
the second card under a preset, and hardware.patch (jarvis_hardware.py).

    python3 test_hardware.py

Everything outside the module is replaced (tools/gen_hardware_cases.World):
Ollama's server.log, nvidia-smi and the registry are replayed as text in
their real formats, with MADE-UP values (none was captured on the owner's
PC); Ollama answers from a stand-in on 127.0.0.1; the approval gate is a
stand-in that records what it was asked. Nothing is started.

What it proves:
  - Ollama's log: only the most recent start-up counts; NVIDIA, ROCm and
    Vulkan devices; a dropped card and its reason; "user overrode visible
    devices"; its settings; the model-load lines the measuring step reads.
  - the registry's real 64-bit memory size, never the 4 GB-capped one.
  - the join: every card shown, with the source of each fact and, for an
    unused one, Ollama's reason in words.
  - GET /api/hardware: the owner's PC today reads "Custom (your own setup)",
    calculated about 0.6 GB over; nothing changes until a preset is chosen.
  - choosing a preset records it and nothing else; the steps come in order,
    each its own card; the second-card switch goes OFF when the extra
    features move.
  - making a tuned model: ONE card, action models_create, tier "ask" only;
    nothing is made before "approved"; never a download.
  - measuring: a spill drops that preset to the next size, which reopens
    its step.
  - jarvis_second_card under a preset: one card runs the lanes in the
    everyday Ollama (no second copy); two cards give the second Ollama the
    owner's 0.75 GB gap.
  - hardware.patch applies to what the earlier patches wrote, and reverses.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, missing  # noqa: E402

for p in (REPO / "tools", HERE / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.append(str(p))

import jarvis_compute as CP  # noqa: E402
import jarvis_hardware as H  # noqa: E402
import jarvis_profiles as P  # noqa: E402
import jarvis_second_card as SC  # noqa: E402
import gen_hardware_cases as G  # noqa: E402
import _stack  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


Verdict = G.Verdict
YES = lambda a, d, p: Verdict(True, "ask", "approved")  # noqa: E731
LOG1 = G.ollama_log([G.LOG_2080S])
LOG2 = G.ollama_log([G.LOG_2080S, G.LOG_2060])


# --------------------------------------------------------------------------
#   Parsing
# --------------------------------------------------------------------------

def t_ollama_log():
    log = H.parse_ollama_log(LOG2)
    check("two cards from the most recent start-up only (the older GTX 1060 block is ignored)",
          [d["description"] for d in log["devices"]]
          == ["NVIDIA GeForce RTX 2080 SUPER", "NVIDIA GeForce RTX 2060"], log["devices"])
    d = log["devices"][0]
    check("a device's route, generation, id, PCI id, total and free memory",
          d["library"] == "CUDA" and d["compute"] == "7.5" and d["uuid"] == G.U_2080S
          and d["pci_id"] == "0000:0a:00.0" and d["total_gib"] == 8.0
          and abs(d["available_gib"] - 6.9) < 1e-9, d)
    check("Ollama's version and its start-up settings", log["version"] == "0.12.3"
          and log["env"].get("OLLAMA_KV_CACHE_TYPE") == "q8_0", log["env"])
    check("the vram-based default context", log["default_ctx"] == 4096)
    rocm = H.parse_ollama_log(
        'time=x level=INFO source=routes.go:1 msg="server config" env="map[]"\n'
        'time=x level=INFO source=types.go:42 msg="inference compute" id=0 library=ROCm '
        'compute=gfx1102 name=ROCm0 description="AMD Radeon RX 7600" type=discrete '
        'total="8.0 GiB" available="7.4 GiB"\n'
        'time=x level=INFO source=amd.go:470 msg="dropping ROCm device - no rocblas support for '
        'gfx target" description="AMD Radeon RX 6600" gfx_target=gfx1032\n'
        'time=x level=INFO source=runner.go:720 msg="user overrode visible devices" '
        'HIP_VISIBLE_DEVICES=0\n')
    check("ROCm: the RX 7600 (gfx1102) is used", rocm["devices"][0]["library"] == "ROCm"
          and rocm["devices"][0]["compute"] == "gfx1102")
    check("a dropped gfx1032 card, with Ollama's reason in words",
          rocm["dropped"] and rocm["dropped"][0]["name"] == "AMD Radeon RX 6600"
          and "ROCm" in rocm["dropped"][0]["why"], rocm["dropped"])
    check("the \"user overrode visible devices\" line, with what was set",
          rocm["overrode"] == {"HIP_VISIBLE_DEVICES": "0"}, rocm["overrode"])
    vk = H.parse_ollama_log('msg="Listening on 127.0.0.1:11434 (version 0.13.0)"\n'
                            'msg="inference compute" id=0 library=vulkan name=Vulkan0 '
                            'description="Intel(R) Arc(TM) A750 Graphics" total="7936 MiB" '
                            'available="7.5 GiB"\n')
    check("a log cut short (no \"server config\" line) still reads from \"Listening on\"; "
          "Vulkan; memory in MiB", vk["version"] == "0.13.0" and vk["devices"][0]["library"] == "Vulkan"
          and abs(vk["devices"][0]["total_gib"] - 7.75) < 1e-9, vk)
    loads = H.parse_ollama_log(LOG1 + (
        'time=x level=INFO source=llama_server.go:436 msg="starting llama-server" '
        'cmd="C:\\\\ollama\\\\llama-server.exe --model x --ctx-size 8192 --cache-type-k q8_0 '
        '--cache-type-v q8_0"\n'
        'llama_context: enabling flash_attn since it is required for quantized V cache\n'
        'load_tensors: offloaded 33/37 layers to GPU\n'))
    check("the measuring step's lines: offloaded 33/37, flash attention forced on, q8_0",
          loads["offloaded"] == [33, 37] and loads["flash_forced"] is True
          and loads["cache_type_k"] == "q8_0", loads)
    check("an empty or missing log is read as nothing, never a crash",
          H.parse_ollama_log("")["devices"] == [] and H.parse_ollama_log(None)["devices"] == [])
    check("Go's quoted values keep their spaces and escaped quotes",
          H.parse_kv('a="x \\"y\\" z" b=2') == {"a": 'x "y" z', "b": "2"})


def t_registry():
    text = G.reg_text([G.REG_2080S, G.REG_2060, ("Old Card", "pci\\ven_10de&dev_0001", None)])
    rows = H.parse_reg(text)
    check("each adapter's name and real memory (64-bit), from reg query's own format",
          [(r["name"], r["total_gib"]) for r in rows[:2]]
          == [("NVIDIA GeForce RTX 2080 SUPER", 8.0), ("NVIDIA GeForce RTX 2060", 12.0)], rows)
    check("a card without the 64-bit size has no size, never a guessed one",
          rows[2]["total_gib"] is None)
    check("the Settings subkeys are not read as cards", len(rows) == 3)
    capped = H.parse_reg("HKEY_LOCAL_MACHINE\\X\\0000\n    DriverDesc    REG_SZ    Big\n"
                         "    HardwareInformation.MemorySize    REG_DWORD    0xffffffff\n")
    check("the old 32-bit memory value (it stops at 4 GB) is never used",
          capped[0]["total_gib"] is None)
    check("makers from names and PCI vendor ids",
          [H._vendor(*x) for x in (("AMD Radeon RX 6600", ""), ("x", "pci\\ven_8086&dev_1"),
                                   ("NVIDIA GeForce RTX 2060", ""))] == ["amd", "intel", "nvidia"])


def t_the_join():
    with G.World(smi=G.SMI_PAIR, log=LOG2, reg=G.reg_text([G.REG_2080S, G.REG_2060, G.REG_UHD]),
                 user_env=G.TODAY_ENV):
        det = H.detect(fresh=True)
    rows = det["cards"]
    check("three cards shown, two used by Ollama", len(rows) == 3
          and [r["used"] for r in rows] == [True, True, False], [r["name"] for r in rows])
    check("each used card joined across the three sources by its id and name",
          rows[0]["sources"] == ["Ollama's log", "nvidia-smi", "the registry"]
          and rows[0]["uuid"] == G.U_2080S and rows[1]["uuid"] == G.U_2060)
    check("built-in graphics: not used, with the reason", "does not list it" in rows[2]["why_unused"])
    check("the monitor comes from nvidia-smi", rows[0]["monitor"] is True and rows[1]["monitor"] is False)
    check("with nothing loaded, the desktop's share is measured from nvidia-smi",
          rows[0]["share_how"] == "measured now, with no model loaded"
          and abs(rows[0]["share_gib"] - (8192 - 6980) / 1024) < 1e-9)
    with G.World(smi=G.SMI_2080S, log=LOG1, reg=G.reg_text([G.REG_2080S]), user_env=G.TODAY_ENV,
                 loaded=[{"name": "jarvis-primary:latest", "size": 1, "size_vram": 1}]):
        det = H.detect(fresh=True)
    check("with a model loaded, the share is Ollama's own start-up reading instead",
          det["cards"][0]["share_how"] == "measured when Ollama started"
          and abs(det["cards"][0]["share_gib"] - 1.1) < 1e-9, det["cards"][0])
    with G.World(smi=G.SMI_2080S, log=None, reg=None, user_env={}, windows=False):
        det = H.detect(fresh=True)
    check("no Ollama log: nvidia-smi alone, and the sentence says it was assumed",
          len(det["planned"]) == 1 and "assumed" in det["found"]
          and det["sources"]["ollama_log"] == "not found", det["found"])
    with G.World(smi="", log=None, reg=G.reg_text([G.REG_RX6600]), user_env={}):
        det = H.detect(fresh=True)
    check("an AMD card with no Ollama log is shown, not planned for, and says what to do",
          det["planned"] == [] and "Start Ollama once" in det["cards"][0]["why_unused"])


# --------------------------------------------------------------------------
#   GET /api/hardware
# --------------------------------------------------------------------------

def t_status_today():
    data = json.loads(G.DESKTOP.read_text(encoding="utf-8"))["cases"]
    today = data["today_one_card"]
    check("today: \"Custom (your own setup)\", nothing chosen",
          today["now"]["label"] == "Custom (your own setup)" and today["chosen"] is None
          and today["applying"] is None)
    check("today's jarvis-primary (8B, 16K) at llama.cpp's 1 GB gap: calculated 0.60 GB over "
          "(design section 3, item 1)", today["now"]["bar"]["used_gib"] == 8.6
          and "0.60 GB over" in today["now"]["words"], today["now"])
    check("... and /api/ps's own numbers are said too (91% on the card, made up)",
          today["now"]["on_card_percent"] == 91 and "91%" in today["now"]["words"])
    check("three presets, with names, one-sentence summaries, and 'calculated, not measured'",
          [p["id"] for p in today["presets"]] == ["fast", "smart", "features"]
          and all(p["summary"] and p["measured_words"] == "calculated, not measured"
                  for p in today["presets"]))
    check("exactly one recommended, with one sentence why",
          sum(p["recommended"] for p in today["presets"]) == 1 and today["recommended"] == "smart"
          and next(p for p in today["presets"] if p["recommended"])["recommended_why"])
    check("the one command is there with its undo and the check line",
          today["command"]["line"] and today["command"]["undo"] and today["command"]["check"])
    check("Spark-X2.5 and Qwen 3.5 are listed to test later, not offered",
          len(today["test_later"]) == 2)
    blob = json.dumps(data)
    check("no token anywhere in any answer", "X-Jarvis-Token" not in blob
          and not re.search(r'"token"\s*:', blob))
    pair = data["planned_pair"]
    check("the planned pair: Most features recommended, chat on the 2080 SUPER because its "
          "memory is faster", pair["recommended"] == "features"
          and "faster" in pair["chat_card_why"], pair["chat_card_why"])
    feat = next(p for p in pair["presets"] if p["id"] == "features")
    check("... with the extra features on the 2060, each saying what it is",
          feat["long"]["card"] == "NVIDIA GeForce RTX 2060"
          and feat["pictures"]["card"] == "NVIDIA GeForce RTX 2060" and feat["ollamas"] == 2)
    vk = data["amd_vulkan"]
    check("AMD through Vulkan: best effort, f16, no Vulkan switch-off in the line",
          vk["cards"][0]["best_effort"] and vk["cards"][0]["conversation_format"] == "f16"
          and "OLLAMA_VULKAN" not in vk["command"]["line"])
    drop = data["card_dropped"]
    check("a dropped AMD card and unused built-in graphics, each in Ollama's words",
          "ROCm" in drop["cards"][1]["why_unused"] and "integrated" in drop["cards"][2]["why_unused"])


def t_nothing_changes_until_chosen():
    with G.World(smi=G.SMI_2080S, log=LOG1, reg=G.reg_text([G.REG_2080S]),
                 user_env=G.TODAY_ENV) as w:
        H.status()
        check("reading GET /api/hardware writes nothing and asks Ollama to make nothing",
              not any(w.dir.iterdir()) and not w.created
              and not any(u.endswith(("/api/create", "/api/pull", "/api/generate"))
                          for u, _ in w.http))
        check("with no preset chosen the second card is exactly as before", H.lane_plan() is None)


# --------------------------------------------------------------------------
#   Choosing, and the steps
# --------------------------------------------------------------------------

def t_choose():
    with G.World(smi=G.SMI_2080S, log=LOG1, reg=G.reg_text([G.REG_2080S]),
                 user_env=G.TODAY_ENV) as w:
        code, out = H.handle_apply({"preset": "turbo"})
        check("an unknown preset: 400 with the three names", code == 400 and "fast" in out["error"])
        code, out = H.handle_apply({})
        check("no preset field: 400", code == 400)
        code, out = H.choose("fast")
        ch = json.loads((w.dir / H.CHOICE_FILE).read_text())
        check("choosing records the preset, the cards, and the settings as they were",
              code == 200 and ch["preset"] == "fast" and "RTX 2080 SUPER" in ch["fingerprint"]
              and ch["before"] == G.TODAY_ENV, ch)
        check("... says nothing has changed yet, and makes nothing",
              "Nothing has changed yet" in out["message"] and not w.created)
        steps = out["applying"]["steps"]
        check("the steps, in the design's order: download, make, switch, the command",
              [s["kind"] for s in steps] == ["install", "create", "switch", "command"], steps)
        check("only the first is open; each later one waits for the one before",
              [s["state"] for s in steps] == ["next", "later", "later", "later"])
        check("every step names one of the four allowed routes (or none, for the command)",
              all(s["route"] in H.STEP_ROUTES or (s["kind"] == "command" and s["route"] is None)
                  for s in steps))
        check("the download step is the existing install route with the exact name",
              steps[0]["route"] == "/api/models/install" and steps[0]["body"] == {"ref": "qwen3:4b"})
        code, out = H.choose(None)
        check("clearing the choice: immediate, and the settings are left as they are",
              code == 200 and H.lane_plan() is None and "left" not in out.get("error", ""))


def t_steps_follow_the_pc():
    with G.World(smi=G.SMI_2080S, log=LOG1, reg=G.reg_text([G.REG_2080S]), user_env=G.TODAY_ENV,
                 installed=("jarvis-primary", "qwen3:8b")) as w:
        w.choose("smart")
        st = H.status()["applying"]["steps"]
        check("a base model already downloaded is done", st[0]["state"] == "done")
        code, _ = H.request_create("jarvis-chat", gate=YES)
        st = H.status()["applying"]["steps"]
        check("made: done; the switch is next", [s["state"] for s in st][:3]
              == ["done", "done", "next"], st)
        w.current = "jarvis-chat:latest"
        H._drop_cache()
        st = H.status()["applying"]["steps"]
        check("switched: done; the command is next", st[2]["state"] == "done"
              and st[3]["state"] == "next")
        for n, v in P.settings_for(P.plan(H.detect()["planned"], "smart")):
            w.user_env[n] = v
        H._drop_cache()
        s = H.status()
        check("the settings in place: every step done, and \"now\" reads the preset's name",
              s["applying"]["done"] is True and s["now"]["label"] == "Smartest answers", s["now"])
        check("the log still shows the old start-up settings: restart pending",
              s["applying"]["restart_pending"] is True)


def t_two_cards_lane_steps_and_the_switch_going_off():
    with G.World(smi=G.SMI_PAIR, log=LOG2, reg=G.reg_text([G.REG_2080S, G.REG_2060]),
                 user_env=G.TODAY_ENV) as w:
        w.switches(master=True, long_context=True)
        out = w.choose("smart")
        steps = out["applying"]["steps"]
        kinds = [s["id"] for s in steps]
        check("Smartest on the planned pair: chat 14B on the 2060, lanes on the 2080 SUPER",
              H.lane_plan()["lane_card"].name == "NVIDIA GeForce RTX 2080 SUPER"
              and H.lane_plan()["chat_card"].name == "NVIDIA GeForce RTX 2060")
        check("the lane steps are the existing second-card cards, main switch first",
              kinds.index("lane:master") < kinds.index("lane:long_context")
              < kinds.index("lane:vision") < kinds.index("command"), kinds)
        sw = json.loads((w.dir / "second-card.json").read_text())
        check("the extra features moved to another card: the main switch went OFF (the safe "
              "direction), so its card names the new card; the feature switches are kept",
              sw["master"] is False and sw["features"]["long_context"] is True
              and "turned off" in out["message"], out["message"])
        line = H.status()["command"]["line"]
        check("the one line pins the everyday Ollama to the 2060 (the chat card)",
              f"'CUDA_VISIBLE_DEVICES', '{G.U_2060}'" in line)
    with G.World(smi=G.SMI_PAIR, log=LOG2, reg=G.reg_text([G.REG_2080S, G.REG_2060]),
                 user_env=G.TODAY_ENV) as w:
        w.choose("smart")
        w.switches(master=True, long_context=True)
        code, out = H.choose(None)
        sw = json.loads((w.dir / "second-card.json").read_text())
        check("forgetting the setup moves the extra features back to where they ran before: "
              "the main switch goes OFF too, never on without a card",
              code == 200 and sw["master"] is False and "turned off" in out["message"], out)
    with G.World(smi=G.SMI_PAIR, log=LOG2, reg=G.reg_text([G.REG_2080S, G.REG_2060]),
                 user_env=G.TODAY_ENV) as w:
        w.switches(master=True, long_context=True)
        out = w.choose("features")
        sw = json.loads((w.dir / "second-card.json").read_text())
        check("Most features keeps the lanes on the 2060, where they already were: the main "
              "switch stays on", sw["master"] is True and "turned off" not in out["message"])


def t_a_card_already_up_is_seen():
    waiting = [("download_model", '{"ref": "qwen3:8b", "size": "5.0 GB"}'),
               ("switch_model", "switch to jarvis-chat:latest"),
               ("download_model", '{"ref": "qwen3:8b-instruct"}')]
    check("a download card for the exact model is seen as waiting",
          H._card_up(waiting, "download_model", "qwen3:8b"))
    check("... but not one for a longer name that starts the same",
          not H._card_up([waiting[2]], "download_model", "qwen3:8b"))
    check("a switch card naming jarvis-chat(:latest) is seen",
          H._card_up(waiting, "switch_model", "jarvis-chat"))
    check("... and never a card for another action",
          not H._card_up(waiting, "switch_model", "qwen3:8b"))
    with G.World(smi=G.SMI_2080S, log=LOG1, reg=G.reg_text([G.REG_2080S]), user_env=G.TODAY_ENV,
                 gate_waiting=waiting[:1]) as w:
        w.choose("smart")
        st = H.status()["applying"]["steps"]
        check("the download step then says it waits for approval, so it is not asked twice",
              st[0]["state"] == "waiting" and st[1]["state"] == "later", st[:2])


# --------------------------------------------------------------------------
#   Making a tuned model: one card
# --------------------------------------------------------------------------

def t_create():
    with G.World(smi=G.SMI_2080S, log=LOG1, reg=G.reg_text([G.REG_2080S]), user_env=G.TODAY_ENV,
                 installed=("qwen3:8b",)) as w:
        code, out = H.request_create("jarvis-chat", gate=YES)
        check("nothing chosen: refused (409), nothing made", code == 409 and not w.created)
        code, out = H.request_create("jarvis-primary", gate=YES)
        check("only the three tuned names; jarvis-primary is never made over (400)", code == 400)
        w.choose("fast")
        code, out = H.request_create("jarvis-chat", gate=YES)
        check("the base (qwen3:4b) is not downloaded: refused, and says making never downloads",
              code == 409 and "never downloads" in out["error"] and not w.created)
        w.choose("smart")
        seen = []
        gate = lambda a, d, p: seen.append((a, d, p)) or Verdict(True, "ask", "approved")  # noqa
        code, out = H.request_create("jarvis-chat", gate=gate, tier_of=lambda a: "notify")
        check("tier not \"ask\": refused before any card (503)", code == 503 and not seen)
        code, out = H.request_create("jarvis-chat", gate=gate)
        check("ONE card, action models_create", code == 200 and out["pending"] is True
              and len(seen) == 1 and seen[0][0] == "models_create")
        text = seen[0][2]
        check("the card shows the Modelfile word for word, says nothing downloads, and what "
              "saying no costs", "FROM qwen3:8b" in text and "PARAMETER num_ctx 8192" in text
              and "Nothing is downloaded" in text and "If you say no" in text)
        check("approved: Ollama on 127.0.0.1 is asked to make it, with the planned parameters",
              len(w.created) == 1 and w.created[0]["model"] == "jarvis-chat"
              and w.created[0]["from"] == "qwen3:8b"
              and w.created[0]["parameters"]["num_ctx"] == 8192, w.created)
        check("every request went to this PC only",
              all(u.startswith("http://127.0.0.1:") for u, _ in w.http))
        check("how it ended, in words", H.status()["last"]["outcome"] == "made")
    for label, v, outcome in (("denied", Verdict(False, "ask", "denied"), "denied"),
                              ("timed out", Verdict(False, "ask", "timed_out"), "timed_out"),
                              ("answered at tier auto", Verdict(True, "auto", "auto"), "refused"),
                              ("an old gate: allowed, no outcome, tier ask", Verdict(True, "ask"),
                               "made")):
        with G.World(smi=G.SMI_2080S, log=LOG1, reg=G.reg_text([G.REG_2080S]),
                     user_env=G.TODAY_ENV, installed=("qwen3:8b",)) as w:
            w.choose("smart")
            H.request_create("jarvis-chat", gate=lambda a, d, p, v=v: v)
            made = bool(w.created)
            check(f"{label}: {'made' if outcome == 'made' else 'nothing made'}",
                  made == (outcome == "made") and H.status()["last"]["outcome"] == outcome,
                  H.status()["last"])
    with G.World(smi=G.SMI_2080S, log=LOG1, reg=G.reg_text([G.REG_2080S]), user_env=G.TODAY_ENV,
                 installed=("qwen3:8b", "qwen3:4b"), spawn_now=False) as w:
        w.choose("smart")
        runs = []
        H.request_create("jarvis-chat", gate=YES, spawn=runs.append)
        code, out = H.request_create("jarvis-chat", gate=YES, spawn=runs.append)
        check("a second request while the card waits: 409", code == 409 and len(runs) == 1)
        w.choose("fast")
        runs[0]()
        check("the preset changed while the card waited: approving it makes nothing",
              not w.created and H.status()["last"]["outcome"] == "refused", H.status()["last"])


# --------------------------------------------------------------------------
#   Measuring
# --------------------------------------------------------------------------

def t_measure():
    with G.World(smi=G.SMI_2080S, log=LOG1 + "load_tensors: offloaded 33/37 layers to GPU\n",
                 reg=G.reg_text([G.REG_2080S]), user_env=G.TODAY_ENV,
                 installed=("qwen3:8b", "jarvis-chat"), current="jarvis-chat") as w:
        w.choose("smart", created={"jarvis-chat": {"from": "qwen3:8b", "num_ctx": 8192}})
        w.loaded = [{"name": "jarvis-chat:latest", "size": 6_000_000_000,
                     "size_vram": 5_400_000_000, "context_length": 8192}]
        asked = []
        fake = lambda model, url: asked.append((model, url)) or {  # noqa: E731
            "ok": True, "tokens_per_s": 61.0, "first_word_ms": 420}
        code, out = H.request_measure(measure=fake)
        check("measuring starts, and times the preset's chat model on this PC's Ollama",
              code == 200 and asked == [("jarvis-chat", "http://127.0.0.1:11434")], asked)
        row = json.loads((w.dir / H.MEASURED_FILE).read_text())["rows"][-1]
        role = row["roles"][0]
        check("it records the speed, how much is on the card (90%), and llama.cpp's own count",
              role["tokens_per_s"] == 61.0 and role["on_card_percent"] == 90
              and role["offloaded"] == [33, 37] and role["spilled"] is True, role)
        check("... and says so in words", "on the processor" in row["words"])
        s = H.status()
        smart = next(p for p in s["presets"] if p["id"] == "smart")
        check("the spill drops Smartest to the next size (8K -> 6K) instead of spilling",
              smart["chat"]["context"] == 6144, smart["chat"])
        make = next(x for x in s["applying"]["steps"] if x["kind"] == "create")
        check("... which opens its \"make\" step again (a new card)", make["state"] == "next"
              and "6,144" in make["title"], make)
        check("... and the preset is not called measured", smart["measured"] is False)
        w.loaded = [{"name": "jarvis-chat:latest", "size": 6, "size_vram": 6}]
        w.log = LOG1 + "load_tensors: offloaded 37/37 layers to GPU\n"
        H._drop_cache()
        ch = json.loads((w.dir / H.CHOICE_FILE).read_text())
        ch["created"]["jarvis-chat"] = {"from": "qwen3:8b", "num_ctx": 6144}
        (w.dir / H.CHOICE_FILE).write_text(json.dumps(ch))
        H.request_measure(measure=fake)
        s = H.status()
        smart = next(p for p in s["presets"] if p["id"] == "smart")
        check("measured again, all on the card: \"measured on this PC\", and the smaller size "
              "stays (the bigger one did not fit)",
              smart["measured"] is True and smart["chat"]["context"] == 6144, smart["chat"])
        code, _ = H.request_measure(measure=fake, spawn=lambda fn: None)
        code2, out2 = H.request_measure(measure=fake)
        check("one measurement at a time (409)", code == 200 and code2 == 409)
        saved = H._standby
        H._standby = lambda: True
        H._MEASURE.update(state="idle")
        try:
            code, out = H.request_measure(measure=fake)
        finally:
            H._standby = saved
        check("on standby (the card is kept free): measuring is refused, in words",
              code == 409 and "standby" in out["error"])


# --------------------------------------------------------------------------
#   The second card under a preset
# --------------------------------------------------------------------------

SMI_16 = f"0, {G.U_A}, NVIDIA RTX A4000, 16384, 15200, 8.6, Enabled\n"
LOG_16 = G.ollama_log([{"uuid": G.U_A, "library": "CUDA", "compute": "8.6",
                        "name": "NVIDIA RTX A4000", "total": "16.0 GiB", "available": "15.0 GiB"}])


def t_second_card_one_big_card():
    with G.World(smi=SMI_16, log=LOG_16, reg=None, user_env=G.TODAY_ENV,
                 installed=("jarvis-vision", "qwen2.5vl:3b")) as w:
        check("no preset: one card is not capable, exactly as before",
              SC.detect()["capable"] is False)
        w.choose("features")
        det = SC.detect()
        check("Most features on one 16 GB card: the lanes are capable, inside the everyday "
              "Ollama", det["capable"] is True and det["_main"] is True and det["_second"] is None,
              det["why"])
        check("pictures by jarvis-vision beside chat; long conversations are chat itself, so "
              "that switch cannot be turned on", SC._feature_model("vision", det)[0] == "jarvis-vision"
              and "long_context" in det["unsupported"])
        seen = []
        gate = lambda a, d, p: seen.append(p) or Verdict(True, "ask", "approved")  # noqa
        SC.request_change("master", True, gate=gate, spawn=lambda fn: fn())
        code, out = SC.request_change("long_context", True, gate=gate, spawn=lambda fn: fn())
        check("... turning it on is refused with the reason (503)", code == 503
              and "chat itself" in out["error"], out)
        check("the main switch's card says where, not \"the second graphics card\"",
              seen and seen[0].startswith("Let Jarvis run extra models beside chat on the "
                                          "NVIDIA RTX A4000"), seen[0][:200] if seen else seen)
        SC.request_change("vision", True, gate=gate, spawn=lambda fn: fn())
        check("the Pictures card says no second copy of Ollama starts, and where it runs",
              "no second copy is started" in seen[-1]
              and seen[-1].startswith('Turn on "Pictures" beside chat, on the same card?')
              and "beside chat, on the same card, on this PC" in seen[-1], seen[-1][:400])
        lane = SC.lane_for("vision")
        check("lane_for(\"vision\"): the everyday Ollama, jarvis-vision, 8K",
              lane is not None and lane.url == "http://127.0.0.1:11434"
              and lane.model == "jarvis-vision" and lane.num_ctx == 8192, lane)
        check("... and no second Ollama was started", SC._LANE.proc is None
              and SC._LANE.state == "off")
        row = next(f for f in SC.status()["features"] if f["id"] == "vision")
        check("the switch says where it runs", row["available"] is True
              and "everyday copy of Ollama" in row["why"], row["why"])
        check("lane_for(\"long_context\") is None: chat itself holds long conversations",
              SC.lane_for("long_context") is None)


def t_second_card_env_under_a_preset():
    env = SC.lane_env("GPU-8b7e2d44-1c9a-4f3e-a2b6-5e9d0c7f1a23", port=11435, num_ctx=16384,
                      base={}, fit_target="768")
    check("under a preset the second Ollama keeps the owner's 0.75 GB gap (768 MiB)",
          env["LLAMA_ARG_FIT_TARGET"] == "768" and env["OLLAMA_VULKAN"] == "0")
    env = SC.lane_env("GPU-8b7e2d44-1c9a-4f3e-a2b6-5e9d0c7f1a23", port=11435, num_ctx=16384,
                      base={})
    check("without one, nothing about the gap is set (today's behaviour)",
          "LLAMA_ARG_FIT_TARGET" not in env)
    try:
        SC.lane_env("GPU-8b7e2d44-1c9a-4f3e-a2b6-5e9d0c7f1a23", port=11435, num_ctx=1,
                    base={}, fit_target="1; rm")
        ok = False
    except ValueError:
        ok = True
    check("a gap that is not a whole number is refused", ok)
    with G.World(smi=G.SMI_PAIR, log=LOG2, reg=G.reg_text([G.REG_2080S, G.REG_2060]),
                 user_env=G.TODAY_ENV) as w:
        w.choose("features")
        plan = H.lane_plan()
        check("Most features on the planned pair: jarvis-long 16K and jarvis-vision 8K on the 2060",
              plan["lane_card"].name == "NVIDIA GeForce RTX 2060"
              and plan["long"][:2] == ("jarvis-long", 16384)
              and plan["pictures"][:2] == ("jarvis-vision", 8192) and plan["fit_target"] == "768",
              plan)
        det = SC.detect()
        check("the second card's detection follows it", det["capable"] and
              det["second"]["uuid"] == G.U_2060 and det["_second"].uuid == G.U_2060)


def t_both_apps_use_the_same_words():
    js = (REPO / "jarvis-desktop" / "src" / "hardware-panel.js").read_text(encoding="utf-8")
    kt = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client"
          / "net" / "Hardware.kt").read_text(encoding="utf-8")
    block = js[js.index("export const HW = {"):js.index("};", js.index("export const HW = {"))]
    desk = {k: v.replace('\\"', '"') for k, v in re.findall(r'(\w+): "((?:[^"\\]|\\.)*)"', block)}
    phone = {}
    for name, rhs in re.findall(r'const val (\w+) = ((?:"(?:[^"\\]|\\.)*"\s*(?:\+\s*)?)+)', kt):
        phone[name] = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', rhs)).replace('\\"', '"')
    pairs = {"useThis": "USE_THIS", "recommended": "RECOMMENDED", "chosen": "CHOSEN", "stop": "STOP",
             "ask": "ASK", "measure": "MEASURE", "stepDone": "STEP_DONE", "stepNext": "STEP_NEXT",
             "stepLater": "STEP_LATER", "stepCommand": "STEP_COMMAND", "asked": "ASKED",
             "noLong": "NO_LONG", "noPictures": "NO_PICTURES", "restart": "RESTART",
             "update": "UPDATE"}
    for js_key, kt_key in pairs.items():
        check(f"the desktop's and the phone's words are the same: {js_key}",
              desk.get(js_key) is not None and desk.get(js_key) == phone.get(kt_key),
              f"desktop {desk.get(js_key)!r}\n        phone   {phone.get(kt_key)!r}")
    check("both apps build a setup's lines the same way (the words for sharing a card)",
          all(w in js and w in kt for w in (
              " It stays loaded beside chat.",
              " It takes turns with chat: a picture unloads chat for a moment.",
              " It takes turns with the other extra model on that card.",
              "What is off, and why:", "Best effort, not tested: ")))
    check("both apps hide a step for 180 seconds after asking, so one tap is one card",
          "180 * 1000" in js and "ASKED_FOR_MS = 180_000L" in kt)
    check("both apps post a step only to the same four routes",
          all(r in js or r in (REPO / "jarvis-desktop" / "src-tauri" / "src" / "hardware.rs")
              .read_text(encoding="utf-8") for r in H.STEP_ROUTES)
          and '"/api/models/install", "/api/models/switch", CREATE_PATH, SecondCard.PATH' in kt)


def t_the_fixture():
    rc = G.main(["--check"])
    check("the golden files and both apps' copies equal a fresh run", rc == 0,
          "run python3 tools/gen_hardware_cases.py")
    check("the desktop's and the phone's copies are byte for byte the same",
          G.DESKTOP.read_bytes() == G.PHONE.read_bytes())


# --------------------------------------------------------------------------
#   hardware.patch
# --------------------------------------------------------------------------

def _rehearse():
    """(ok, why, before, after) for jarvis_hud.py and jarvis_gate.py: the
    stack before hardware.patch, then hardware.patch on it with plain `git
    apply` - its context must be what the earlier patches wrote."""
    order = _stack.order()
    if "hardware.patch" not in order:
        return False, "hardware.patch is not in apply-patches.ps1's list", {}, {}
    before_list = order[:order.index("hardware.patch")]
    patch = (HERE / "hardware.patch").read_text(encoding="utf-8")
    befores, afters = {}, {}
    git = shutil.which("git")
    for target in ("jarvis_hud.py", "jarvis_gate.py"):
        text, log = _stack.stand_in(target, before_list)
        if text is None:
            return False, "; ".join(log), {}, {}
        d = Path(tempfile.mkdtemp(prefix="jarvis-hw-patch-"))
        try:
            (d / target).write_text(text, encoding="utf-8", newline="\n")
            (d / "p.patch").write_text(patch, encoding="utf-8", newline="\n")
            r = subprocess.run([git, "apply", "--include", target, "p.patch"], cwd=d,
                               capture_output=True, text=True)
            if r.returncode != 0:
                return False, f"{target}: {r.stderr}", {}, {}
            after = (d / target).read_text(encoding="utf-8")
            r = subprocess.run([git, "apply", "-R", "--include", target, "p.patch"], cwd=d,
                               capture_output=True, text=True)
            if r.returncode != 0 or (d / target).read_text(encoding="utf-8") != text:
                return False, f"{target}: does not reverse cleanly: {r.stderr}", {}, {}
        finally:
            shutil.rmtree(d, ignore_errors=True)
        befores[target], afters[target] = text, after
    return True, "", befores, afters


def t_the_patch():
    if not shutil.which("git"):
        return check("SKIP - git is not installed", True)
    ok, why, before, after = _rehearse()
    check("hardware.patch applies to what the earlier patches wrote (no invented context), "
          "and reverses", ok, why)
    if not ok:
        return
    hud, gate = after["jarvis_hud.py"], after["jarvis_gate.py"]
    i = hud.index('        if path == "/api/hardware":')
    blk = hud[i:hud.index('        if path in ("/api/wiki"', i)]
    check("GET /api/hardware checks origin and token and answers status()",
          "_origin_ok(self)" in blk and "_token_ok(self)" in blk
          and "jarvis_hardware.status()" in blk)
    i = hud.index('        if route in ("/api/hardware/apply"')
    blk2 = hud[i:hud.index('        if route == "/api/wiki/ingest":', i)]
    check("the three POSTs check origin and token and hand the body over",
          "_origin_ok(self)" in blk2 and "_token_ok(self)" in blk2
          and "jarvis_hardware.handle_apply(body)" in blk2
          and "jarvis_hardware.handle_create(body)" in blk2
          and "jarvis_hardware.request_measure()" in blk2)
    for name, b in (("GET", blk), ("POST", blk2)):
        try:
            compile("def f(self, path, route):\n" + b, "<patched block>", "exec")
            check(f"the patched {name} block compiles", True)
        except SyntaxError as exc:
            check(f"the patched {name} block compiles", False, str(exc))
    check("second-card's blocks are untouched", before["jarvis_hud.py"].count(
        "jarvis_second_card.handle_post(body)") == hud.count("jarvis_second_card.handle_post(body)"))
    check("the approval notice knows models_create stays on this PC",
          '"models_create": ("yes", "local",' in gate)
    check("... and a \"no\" to it proposes no standing rule (the owner pressed a button)",
          '"models_create",' in gate[gate.index("_NO_RULE_FROM_DENIAL"):])
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    check("apply-patches.ps1 applies hardware.patch, after second-card and wiki",
          "hardware.patch" in names and names.index("wiki.patch") < names.index("hardware.patch"))
    shipped = ps1[ps1.index("$SHIPPED = @("):]
    import _where
    check("both new modules are copied in, in _where.SHIPPED too",
          "'jarvis_profiles.py'" in shipped and "'jarvis_hardware.py'" in shipped
          and "jarvis_profiles.py" in _where.SHIPPED and "jarvis_hardware.py" in _where.SHIPPED)
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check('the shipped toml has models_create = "ask"',
          re.search(r'^models_create\s*=\s*"ask"', toml, re.M) is not None)


def t_the_real_file():
    if missing("jarvis_hud.py"):
        return check("SKIP - no jarvis_hud.py here; the rehearsal above is the proof", True)
    s = (BACKEND / "jarvis_hud.py").read_text(encoding="utf-8")
    check("the backend's jarvis_hud.py has /api/hardware (hardware.patch applied)",
          '"/api/hardware"' in s and '"/api/hardware/apply"' in s)


def main():
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception as exc:  # pragma: no cover
                import traceback
                traceback.print_exc()
                check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
