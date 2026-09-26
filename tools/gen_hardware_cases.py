#!/usr/bin/env python3
"""Writes the hardware presets' golden files, and checks them.

    python3 tools/gen_hardware_cases.py            # write every file
    python3 tools/gen_hardware_cases.py --check    # compare only

Three outputs, all made by the real code - nothing is written by hand:

1. backend/fixtures/hardware_cases.json - jarvis_profiles.plan() for every
   hardware case in docs/HARDWARE-PROFILES.md section 4.4, times the three
   presets, at the owner's 0.75 GB gap (decision 1). backend/test_profiles.py
   fails when the planner and this file disagree.

2. The table in docs/HARDWARE-PROFILES.md between the markers
   "hardware-cases:begin" and "hardware-cases:end" - rendered from that same
   file, so the document and the code cannot drift (design, build step 4).

3. jarvis-desktop/tests/fixtures/hardware-cases.json and the phone's
   byte-identical copy, contract/hardware-cases.json: what GET /api/hardware
   and the three POSTs really answer (jarvis_hardware), in named situations.
   Both apps build against it (as for the second card).

WHAT THE INPUTS ARE. Card names, memory sizes, ids, Ollama log lines,
nvidia-smi lines and registry lines are all MADE UP to look like real ones,
in the formats the design read from source. None was captured on the owner's
PC; that output has not been seen yet.
"""
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_compute as CP  # noqa: E402
import jarvis_profiles as P  # noqa: E402
import jarvis_hardware as H  # noqa: E402
import jarvis_second_card as SC  # noqa: E402

PLAN_FIXTURE = BACKEND / "fixtures" / "hardware_cases.json"
DOC = ROOT / "docs" / "HARDWARE-PROFILES.md"
BEGIN = "<!-- hardware-cases:begin (tools/gen_hardware_cases.py writes this; do not edit) -->"
END = "<!-- hardware-cases:end -->"
DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "hardware-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "hardware-cases.json")

U_2080S = "GPU-3f2a9c1e-7b1d-4e8a-9c55-0d4b2e6a8f10"
U_2060 = "GPU-8b7e2d44-1c9a-4f3e-a2b6-5e9d0c7f1a23"
U_2080TI = "GPU-51c0e8aa-6d2f-4b19-8e37-2a4c9f0b6d58"
U_A = "GPU-0a9d3b72-e4c1-4a6f-b85e-7c2d1f9e4b36"
U_B = "GPU-c6e1f057-3a8b-49d2-9f14-b0e7a25d8c61"


# --------------------------------------------------------------------------
#   1. The planner's cases (design section 4.4)
# --------------------------------------------------------------------------

def _card(key, name, gb, monitor, *, route="CUDA", compute="7.5", vendor="nvidia", uuid="",
          speed=None):
    return {"key": key, "name": name, "total_gib": gb, "monitor": monitor, "route": route,
            "compute": compute, "vendor": vendor, "uuid": uuid, "speed_gbs": speed}


def _one(gb, name=None, **kw):
    return [_card("a", name or f"{gb} GB card", gb, True, uuid=U_A, **kw)]


#: (id, the design's heading, cards). "A" is the faster card where the design
#: says so; speeds for made-up cards are made up to put them in that order.
PLAN_CASES = (
    ("one_6gb", "6 GB", _one(6)),
    ("one_8gb", "8 GB - the owner's PC today", _one(8, "RTX 2080 SUPER", speed=496.0)),
    ("one_10gb", "10 GB", _one(10)),
    ("one_11gb", "11 GB", _one(11)),
    ("one_12gb", "12 GB", _one(12)),
    ("one_16gb", "16 GB", _one(16)),
    ("one_24gb", "24 GB", _one(24)),
    ("one_8gb_pascal", "GTX 1080, 8 GB (Pascal)", _one(8, "GTX 1080", compute="6.1")),
    ("one_8gb_maxwell", "An older 8 GB NVIDIA card (Maxwell, before GTX 10)",
     _one(8, "Quadro M5000", compute="5.2")),
    ("one_8gb_rocm", "RX 7600, 8 GB (ROCm)",
     [_card("a", "RX 7600", 8, True, route="ROCm", compute="gfx1102", vendor="amd")]),
    ("one_8gb_vulkan_amd", "RX 6600, 8 GB (Vulkan)",
     [_card("a", "RX 6600", 8, True, route="Vulkan", compute="", vendor="amd")]),
    ("one_8gb_vulkan_intel", "Intel Arc, 8 GB (Vulkan)",
     [_card("a", "Arc A750", 8, True, route="Vulkan", compute="", vendor="intel")]),
    ("two_8_8", "8 + 8 GB, monitor on one of them",
     [_card("a", "8 GB card A", 8, False, uuid=U_A, speed=496.0),
      _card("b", "8 GB card B", 8, True, uuid=U_B, speed=496.0)]),
    ("two_8_10_mon8", "8 + 10 GB, monitor on the 8",
     [_card("a", "8 GB card", 8, True, uuid=U_A, speed=496.0),
      _card("b", "10 GB card", 10, False, uuid=U_B, speed=448.0)]),
    ("two_8_10_mon10", "8 + 10 GB, monitor on the 10",
     [_card("a", "8 GB card", 8, False, uuid=U_A, speed=496.0),
      _card("b", "10 GB card", 10, True, uuid=U_B, speed=448.0)]),
    ("two_8_11_mon8", "8 + 11 GB, monitor on the 8 (the 11 GB card slower)",
     [_card("a", "8 GB card", 8, True, uuid=U_A, speed=496.0),
      _card("b", "11 GB card", 11, False, uuid=U_B, speed=448.0)]),
    ("two_2080s_2080ti", "RTX 2080 SUPER + RTX 2080 Ti (11 GB, the faster), monitor on the 8",
     [_card("a", "RTX 2080 SUPER", 8, True, uuid=U_2080S),
      _card("b", "RTX 2080 Ti", 11, False, uuid=U_2080TI)]),
    ("two_2080s_2060_mon8", "RTX 2080 SUPER + RTX 2060 12 GB, monitor on the 2080 SUPER - "
                            "the planned pair",
     [_card("a", "RTX 2080 SUPER", 8, True, uuid=U_2080S),
      _card("b", "RTX 2060", 12, False, uuid=U_2060)]),
    ("two_2080s_2060_mon12", "RTX 2080 SUPER + RTX 2060 12 GB, monitor on the 2060",
     [_card("a", "RTX 2080 SUPER", 8, False, uuid=U_2080S),
      _card("b", "RTX 2060", 12, True, uuid=U_2060)]),
    ("two_8_16_mon8", "8 + 16 GB, monitor on the 8",
     [_card("a", "8 GB card", 8, True, uuid=U_A, speed=496.0),
      _card("b", "16 GB card", 16, False, uuid=U_B, speed=448.0)]),
    ("two_8_16_mon16", "8 + 16 GB, monitor on the 16",
     [_card("a", "8 GB card", 8, False, uuid=U_A, speed=496.0),
      _card("b", "16 GB card", 16, True, uuid=U_B, speed=448.0)]),
    ("two_12_12", "12 + 12 GB, monitor on one of them",
     [_card("a", "12 GB card A", 12, False, uuid=U_A, speed=336.0),
      _card("b", "12 GB card B", 12, True, uuid=U_B, speed=336.0)]),
    ("two_8_rx7600", "RTX 2080 SUPER + RX 7600 (the second card not NVIDIA)",
     [_card("a", "RTX 2080 SUPER", 8, True, uuid=U_2080S),
      _card("b", "RX 7600", 8, False, route="ROCm", compute="gfx1102", vendor="amd")]),
)


def cards_of(case_cards) -> list:
    return [P.Card(key=c["key"], name=c["name"], total_gib=float(c["total_gib"]),
                   monitor=c["monitor"], route=c["route"], compute=c["compute"],
                   vendor=c["vendor"], uuid=c["uuid"], speed_gbs=c["speed_gbs"])
            for c in case_cards]


def _role(r):
    if r is None:
        return None
    return {"model": r.model.ref, "context": r.ctx, "format": r.kv, "card": r.card.key,
            "mode": r.mode, "need_gib": round(r.need, 2)}


def plan_view(lay: P.Layout) -> dict:
    long = _role(lay.long)
    if long is None and lay.long_is_chat:
        long = "chat"
    return {
        "chat": _role(lay.chat), "long": long, "pictures": _role(lay.pictures),
        "bars": [{"card": b.card.key, "models_gib": round(b.models_gib, 2),
                  "fixed_gib": round(b.fixed_gib, 2), "used_gib": round(b.used_gib, 2),
                  "total_gib": b.card.total_gib, "blocks": b.blocks} for b in lay.bars],
        "off": lay.off, "notes": lay.notes, "best_effort": bool(lay.best_effort),
        "settings": [[n, v] for n, v in P.settings_for(lay)],
    }


def plan_cases() -> dict:
    out = {}
    for cid, title, case_cards in PLAN_CASES:
        cards = cards_of(case_cards)
        lays = {pid: P.plan(cards, pid) for pid in P.PRESET_IDS}
        rec, why = P.recommended(lays)
        out[cid] = {"title": title, "cards": case_cards,
                    "presets": {pid: plan_view(lays[pid]) for pid in P.PRESET_IDS},
                    "recommended": rec, "recommended_why": why}
    return out


def render_plans() -> str:
    body = {"_about": ("jarvis_profiles.plan() for every hardware case in "
                       "docs/HARDWARE-PROFILES.md section 4.4 and the three presets, at the "
                       "owner's 0.75 GB gap. Calculated, not measured. Made by "
                       "tools/gen_hardware_cases.py; do not edit by hand."),
            "gap_gib": P.GAP_GIB, "cases": plan_cases()}
    return json.dumps(body, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def _cell(r, cards) -> str:
    if r is None:
        return "off"
    if r == "chat":
        return "chat itself"
    name = next(c["name"] for c in cards if c["key"] == r["card"])
    mode = {"beside": ", beside chat", "swap": ", by swapping with chat",
            "turns": ", taking turns"}.get(r["mode"], "")
    return f"{r['model']}, {r['context'] // 1024}K{'' if r['format'] == 'q8_0' else ' f16'} - " \
           f"{r['need_gib']:.2f} ({name}{mode})"


def render_doc_table(data: dict) -> str:
    lines = [BEGIN, "",
             "Generated from `backend/fixtures/hardware_cases.json` - the planner's own output "
             f"at the owner's {data['gap_gib']:.2f} GB gap. Calculated, not measured. "
             "\"(rec.)\" marks the recommended preset.", ""]
    for cid, case in data["cases"].items():
        cards = case["cards"]
        lines.append(f"**{case['title']}** (`{cid}`)")
        lines.append("")
        lines.append("| Preset | Chat | Long context | Pictures | Memory |")
        lines.append("|---|---|---|---|---|")
        for pid in P.PRESET_IDS:
            p = case["presets"][pid]
            name = next(x["name"] for x in P.PRESETS if x["id"] == pid)
            if case["recommended"] == pid:
                name += " (rec.)"
            mem = " · ".join(
                f"`{b['blocks']}` {b['models_gib']:.2f} + {b['fixed_gib']:.2f} = "
                f"{b['used_gib']:.2f} / {b['total_gib']:g}" for b in p["bars"] if b["models_gib"])
            lines.append(f"| {name} | {_cell(p['chat'], cards)} | {_cell(p['long'], cards)} | "
                         f"{_cell(p['pictures'], cards)} | {mem or '-'} |")
        lines.append("")
    lines.append(END)
    return "\n".join(lines)


def doc_with_table(doc: str, table: str) -> str:
    if BEGIN in doc and END in doc:
        a = doc.index(BEGIN)
        b = doc.index(END) + len(END)
        return doc[:a] + table + doc[b:]
    raise SystemExit(f"{DOC.relative_to(ROOT)} has no {BEGIN!r} marker")


# --------------------------------------------------------------------------
#   3. What GET /api/hardware answers (jarvis_hardware), in named situations
# --------------------------------------------------------------------------

T0 = "2026-09-24T09:00:00.000+01:00"


def ollama_log(devices, *, dropped=(), env=None, version="0.12.3", after=()) -> str:
    """Made-up server.log lines, in the shape the design read from Ollama's
    source (docs/HARDWARE-PROFILES.md 2.1). An older start-up first, so the
    parser must take only the most recent one."""
    env = env if env is not None else {"OLLAMA_KV_CACHE_TYPE": "q8_0", "OLLAMA_VULKAN": "true",
                                       "CUDA_VISIBLE_DEVICES": ""}
    em = " ".join(f"{k}:{v}" for k, v in sorted(env.items()))
    old = [f'time={T0} level=INFO source=routes.go:1400 msg="server config" env="map[]"',
           f'time={T0} level=INFO source=types.go:42 msg="inference compute" id=0 '
           f'library=CUDA compute=6.1 name=CUDA0 description="NVIDIA GeForce GTX 1060" '
           f'type=discrete total="6.0 GiB" available="5.5 GiB"']
    lines = old + [f'time={T0} level=INFO source=routes.go:1400 msg="server config" '
                   f'env="map[{em}]"',
                   f'time={T0} level=INFO source=routes.go:1450 msg="Listening on '
                   f'127.0.0.1:11434 (version {version})"']
    for d in dropped:
        lines.append(f'time={T0} level=INFO source=runner.go:400 msg="{d[0]}" '
                     f'description="{d[1]}"')
    for i, d in enumerate(devices):
        lines.append(
            f'time={T0} level=INFO source=types.go:42 msg="inference compute" id={i} '
            + (f'filter_id={d["uuid"]} ' if d.get("uuid") else "")
            + f'library={d["library"]} compute={d["compute"]} name={d["library"]}{i} '
            f'description="{d["name"]}" libdirs=cuda_v13 driver=13.0 '
            f'pci_id=0000:{10 + i:02x}:00.0 type=discrete total="{d["total"]}" '
            f'available="{d["available"]}"')
    lines.append(f'time={T0} level=INFO source=routes.go:2100 msg="vram-based default context" '
                 f'total_vram="8.0 GiB" default_num_ctx=4096')
    lines += list(after)
    return "\n".join(lines) + "\n"


def reg_text(adapters) -> str:
    """Made-up `reg query <class key> /s` output: 4-space indents, as reg prints."""
    out = []
    for i, (name, dev, gib) in enumerate(adapters):
        out.append(f"HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Control\\Class\\"
                   f"{{4d36e968-e325-11ce-bfc1-08002be10318}}\\{i:04d}")
        out.append(f"    DriverDesc    REG_SZ    {name}")
        out.append(f"    MatchingDeviceId    REG_SZ    {dev}")
        if gib is not None:
            out.append(f"    HardwareInformation.qwMemorySize    REG_QWORD    "
                       f"0x{int(gib * 1024 ** 3):x}")
        out.append("")
        out.append(f"HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Control\\Class\\"
                   f"{{4d36e968-e325-11ce-bfc1-08002be10318}}\\{i:04d}\\Settings")
        out.append("")
    return "\n".join(out) + "\n"


SMI_2080S = f"0, {U_2080S}, NVIDIA GeForce RTX 2080 SUPER, 8192, 6980, 7.5, Enabled\n"
SMI_PAIR = (SMI_2080S + f"1, {U_2060}, NVIDIA GeForce RTX 2060, 12288, 11650, 7.5, Disabled\n")
#: The health query's answer (jarvis_hardware.HEALTH_FIELDS), made up in
#: nvidia-smi's own format: the 2080 SUPER busy and warm; the 2060 idle, its
#: fan stopped, which some cards report as "[N/A]".
HEALTH_2080S = f"0, {U_2080S}, 67, 182.40, 250.00, 48, 91, Not Active, Not Active\n"
HEALTH_PAIR = (f"0, {U_2080S}, 84, 247.10, 250.00, 78, 99, Active, Not Active\n"
               f"1, {U_2060}, 38, 9.85, 184.00, [N/A], 0, Not Active, Not Active\n")
LOG_2080S = {"uuid": U_2080S, "library": "CUDA", "compute": "7.5",
             "name": "NVIDIA GeForce RTX 2080 SUPER", "total": "8.0 GiB",
             "available": "6.9 GiB"}
LOG_2060 = {"uuid": U_2060, "library": "CUDA", "compute": "7.5",
            "name": "NVIDIA GeForce RTX 2060", "total": "12.0 GiB", "available": "11.4 GiB"}
REG_2080S = ("NVIDIA GeForce RTX 2080 SUPER", "pci\\ven_10de&dev_1e81", 8.0)
REG_2060 = ("NVIDIA GeForce RTX 2060", "pci\\ven_10de&dev_1f15", 12.0)
REG_UHD = ("Intel(R) UHD Graphics 630", "pci\\ven_8086&dev_3e92", 1.0)
REG_RX6600 = ("AMD Radeon RX 6600", "pci\\ven_1002&dev_73ff", 8.0)
PRIMARY_SHOW = {"details": {"family": "qwen3", "parameter_size": "8.2B"},
                "parameters": "num_ctx                        16384\nnum_batch 512\n"}


class Verdict:
    def __init__(self, allowed, tier="ask", outcome=None):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.request_id, self.reason = "r1", ""


class World:
    """Everything outside jarvis_hardware, replaced. Used by this tool and by
    backend/test_hardware.py."""

    def __init__(self, *, smi="", log=None, reg=None, installed=("jarvis-primary",),
                 loaded=(), current="jarvis-primary", windows=True, user_env=None,
                 shows=None, ollama_up=True, spawn_now=True, gate_waiting=(), health=""):
        self.smi, self.log, self.reg = smi, log, reg
        self.health = health
        self.installed, self.loaded = list(installed), [dict(x) for x in loaded]
        self.current, self.windows = current, windows
        self.user_env = dict(user_env or {})
        self.shows = dict(shows or {"jarvis-primary": PRIMARY_SHOW})
        self.ollama_up, self.spawn_now = ollama_up, spawn_now
        self.gate_waiting = list(gate_waiting)
        self.created, self.http = [], []
        self.dir = Path(tempfile.mkdtemp(prefix="jarvis-hardware-"))
        self._saved = {}

    def run_smi(self, args):
        q = args[0] if args else ""
        if q == f"--query-gpu={CP.FIELDS_FULL}":
            return self.smi or None
        if q == f"--query-gpu={H.HEALTH_FIELDS}":
            return self.health or None
        return None

    def http_json(self, url, payload=None, timeout=2.0):
        self.http.append((url, payload))
        if not url.startswith("http://127.0.0.1:"):
            raise AssertionError("a non-loopback address was asked: " + url)
        if not self.ollama_up or url.startswith("http://127.0.0.1:11435"):
            raise OSError("connection refused")
        if url.endswith("/api/tags"):
            return {"models": [{"name": n, "model": n} for n in self.installed]}
        if url.endswith("/api/ps"):
            return {"models": self.loaded}
        if url.endswith("/api/version"):
            return {"version": "0.12.3"}
        if url.endswith("/api/show"):
            s = self.shows.get((payload or {}).get("model"))
            if s is None:
                raise OSError("404")
            return s
        if url.endswith("/api/create"):
            self.created.append(payload)
            self.installed.append(payload["model"])
            self.shows[payload["model"]] = {"parameters": f"num_ctx {payload['parameters']['num_ctx']}"}
            return {"status": "success"}
        raise OSError("not answered here")

    def install(self):
        H._reset_for_tests()
        SC._reset_for_tests()
        CP._cache.update(at=-1e9, cards=None, fields="")
        repl = {
            (CP, "_run_smi"): self.run_smi,
            (H, "_read_log"): lambda: self.log,
            (H, "_read_lane_log"): lambda: None,
            (H, "_reg_text"): lambda: self.reg,
            (H, "_user_env"): lambda name: self.user_env.get(name),
            (H, "_on_windows"): lambda: self.windows,
            (H, "_http_json"): self.http_json,
            (H, "_current_model"): lambda: self.current,
            (H, "_config_dir"): lambda: self.dir,
            (H, "_primary_setting"): lambda: "",
            (H, "_gate_waiting"): lambda: list(self.gate_waiting),
            (H, "_audit"): lambda event, detail: None,
            (H, "_tier"): lambda action: "ask",
            (H, "_main_url"): lambda: "http://127.0.0.1:11434",
            (H, "_spawn"): (lambda fn: fn()) if self.spawn_now else (lambda fn: None),
            (SC, "_state_path"): lambda: self.dir / "second-card.json",
            (SC, "_log_path"): lambda: self.dir / "second-card-ollama.log",
            (SC, "_primary"): lambda cards: CP.primary(cards, configured=""),
            (SC, "_cfg"): lambda key, default=None: default,
            (SC, "_http_json"): self.http_json,
            (SC, "_audit"): lambda event, detail: None,
            (SC, "_spawn"): lambda fn: None,
            (SC, "_popen"): lambda *a, **k: (_ for _ in ()).throw(AssertionError("no start")),
            (SC, "_which"): lambda name: None,
            (SC, "_main_ollama_url"): lambda: "http://127.0.0.1:11434",
            (SC, "_user_env"): lambda name: self.user_env.get(name),
        }
        for (mod, name), val in repl.items():
            self._saved[(mod, name)] = getattr(mod, name)
            setattr(mod, name, val)
        return self

    def remove(self):
        try:
            H._reset_for_tests()
            SC._reset_for_tests()
        finally:
            for (mod, name), val in self._saved.items():
                setattr(mod, name, val)
            CP._cache.update(at=-1e9, cards=None, fields="")

    def choose(self, preset, **extra):
        code, body = H.choose(preset)
        assert code == 200, body
        if extra:
            ch = json.loads((self.dir / H.CHOICE_FILE).read_text(encoding="utf-8"))
            ch.update(extra)
            (self.dir / H.CHOICE_FILE).write_text(json.dumps(ch), encoding="utf-8")
            H._drop_cache()
        return body

    def switches(self, master=False, **features):
        data = {"master": master, "features": {f: bool(features.get(f)) for f in SC.FEATURE_IDS}}
        (self.dir / "second-card.json").write_text(json.dumps(data), encoding="utf-8")

    def __enter__(self):
        return self.install()

    def __exit__(self, *exc):
        self.remove()


TODAY_ENV = {"OLLAMA_KV_CACHE_TYPE": "q8_0", "OLLAMA_KEEP_ALIVE": "-1"}


def status_cases() -> dict:
    out = {}
    # The owner's PC today: one 2080 SUPER, jarvis-primary (Qwen 3 8B, 16K),
    # the two settings MODEL-TOPOLOGY asks for. Nothing chosen.
    with World(smi=SMI_2080S, log=ollama_log([LOG_2080S]), reg=reg_text([REG_2080S, REG_UHD]),
               user_env=TODAY_ENV, health=HEALTH_2080S,
               loaded=[{"name": "jarvis-primary:latest", "size": 6_620_000_000,
                        "size_vram": 6_020_000_000, "context_length": 16384}]):
        out["today_one_card"] = H.status()
    # The planned pair: the 2060 12 GB in, monitor on the 2080 SUPER.
    with World(smi=SMI_PAIR, log=ollama_log([LOG_2080S, LOG_2060]),
               reg=reg_text([REG_2080S, REG_2060]), user_env=TODAY_ENV, health=HEALTH_PAIR):
        out["planned_pair"] = H.status()
    # One card, "Fastest answers" chosen: qwen3:4b is not downloaded yet.
    with World(smi=SMI_2080S, log=ollama_log([LOG_2080S]), reg=reg_text([REG_2080S]),
               user_env=TODAY_ENV) as w:
        w.choose("fast")
        out["chosen_first_step"] = H.status()
    # "Smartest answers" chosen, halfway: downloaded and made, not switched;
    # a card to make it again is not waiting.
    with World(smi=SMI_2080S, log=ollama_log([LOG_2080S]), reg=reg_text([REG_2080S]),
               user_env=TODAY_ENV, installed=("jarvis-primary", "qwen3:8b")) as w:
        w.choose("smart")
        H.request_create("jarvis-chat", gate=lambda a, d, p: Verdict(True, "ask", "approved"))
        out["chosen_halfway"] = H.status()
    # A card to make jarvis-chat is up and waiting.
    with World(smi=SMI_2080S, log=ollama_log([LOG_2080S]), reg=reg_text([REG_2080S]),
               user_env=TODAY_ENV, installed=("jarvis-primary", "qwen3:8b"),
               spawn_now=False) as w:
        w.choose("smart")
        H.request_create("jarvis-chat")
        out["create_waiting"] = H.status()
    # An AMD card through Vulkan: best effort, the larger conversation format.
    with World(smi="", log=ollama_log([{"uuid": "", "library": "Vulkan", "compute": "",
                                        "name": "AMD Radeon RX 6600", "total": "8.0 GiB",
                                        "available": "7.1 GiB"}],
                                      env={"OLLAMA_VULKAN": "true"}),
               reg=reg_text([REG_RX6600]), user_env={}, current=None, installed=()):
        out["amd_vulkan"] = H.status()
    # No Ollama log (Ollama never started on this account): nvidia-smi alone.
    with World(smi=SMI_2080S, log=None, reg=None, windows=False, user_env={}):
        out["no_ollama_log"] = H.status()
    # Two cards, one of them dropped by Ollama (an old driver), plus
    # built-in graphics it does not use.
    with World(smi=SMI_2080S, log=ollama_log([LOG_2080S], dropped=[
            ("dropping ROCm device - no rocblas support for gfx target", "AMD Radeon RX 6600"),
            ("dropping integrated GPU; to enable, set OLLAMA_IGPU_ENABLE=1",
             "Intel(R) UHD Graphics 630")]),
               reg=reg_text([REG_2080S, REG_RX6600, REG_UHD]), user_env=TODAY_ENV):
        out["card_dropped"] = H.status()
    # What each POST answers.
    with World(smi=SMI_2080S, log=ollama_log([LOG_2080S]), reg=reg_text([REG_2080S]),
               user_env=TODAY_ENV) as w:
        out["post_apply_ok"] = _answer(H.handle_apply({"preset": "features"}))
        out["post_apply_unknown"] = _answer(H.handle_apply({"preset": "turbo"}))
        out["post_create_not_downloaded"] = _answer(H.handle_create({"name": "jarvis-chat"}))
        out["post_apply_clear"] = _answer(H.handle_apply({"preset": None}))
    with World(smi=SMI_2080S, log=ollama_log([LOG_2080S]), reg=reg_text([REG_2080S]),
               user_env=TODAY_ENV, installed=("qwen3:8b",), spawn_now=False) as w:
        w.choose("smart")
        out["post_create_pending"] = _answer(H.handle_create({"name": "jarvis-chat"}))
        out["post_measure_started"] = _answer(H.request_measure())
    return out


def _answer(pair) -> dict:
    code, body = pair
    if isinstance(body, dict) and "applying" in body:
        body = dict(body)
        body["applying"] = "(the same as GET /api/hardware's applying)"
    return {"status": code, "body": body}


def _scrub(obj):
    """Times vary from run to run; the files must not."""
    if isinstance(obj, dict):
        return {k: (0 if k in ("at", "chosen_at") and isinstance(v, (int, float)) else _scrub(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(x) for x in obj]
    return obj


def render_status() -> str:
    body = {"_about": ("Real output of backend/jarvis_hardware.py - GET /api/hardware "
                       "(status()) and the POST answers - one per named case, made by "
                       "tools/gen_hardware_cases.py. The Ollama log, nvidia-smi and registry "
                       "lines behind them are made up, in the formats the design read from "
                       "source; none was captured on the owner's PC. Do not edit by hand."),
            "cases": _scrub(status_cases())}
    return json.dumps(body, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------

def outputs() -> dict:
    plans = render_plans()
    table = render_doc_table(json.loads(plans))
    doc = doc_with_table(DOC.read_text(encoding="utf-8"), table)
    status = render_status()
    return {PLAN_FIXTURE: plans, DOC: doc, DESKTOP: status, PHONE: status}


def main(argv) -> int:
    outs = outputs()
    if "--check" in argv:
        stale = [p for p, text in outs.items()
                 if (p.read_text(encoding="utf-8").replace("\r\n", "\n") if p.is_file() else "")
                 != text]
        for p in stale:
            print(f"{p.relative_to(ROOT)} is out of date: run python3 tools/gen_hardware_cases.py")
        if stale:
            return 1
        print("hardware cases match the producer (plans, the design's table, desktop and phone "
              "copies).")
        return 0
    for p, text in outs.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
