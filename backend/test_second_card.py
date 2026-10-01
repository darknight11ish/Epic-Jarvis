"""The second graphics card: detection, the switches, the second Ollama, the
hooks, and the patch.

    python3 test_second_card.py

What this proves (all without a graphics card, a real Ollama or the
owner's PC - nvidia-smi's output is replayed in its real CSV format, Ollama
answers from a stand-in on 127.0.0.1, and starting a process is recorded,
never done):

  - nvidia-smi parsing: one card; 2080 Super + 2060; 2080 Super + 2080 Ti;
    + a P100; an old driver with no compute_cap (retried, then looked up by
    name); garbage. The everyday ("primary") card by its rule.
  - every capable / not-capable reason, in words.
  - a switch: ON raises exactly one card, action second_card_enable; a
    second ON while it waits is refused (409); OFF is at once; ON is refused
    when not capable, when the main switch or a dependency is off, or when
    the tier is not "ask". Only "ask" + "approved" turns it on.
  - the second Ollama's command line and environment: 127.0.0.1 only, the
    card pinned by its id; a port someone else holds is left alone; it is
    stopped when everything is off, and only it.
  - lane_for() is None in every not-ready state.
  - the hooks do nothing when off: history trimming, a picture turn, the
    learner, browser_control; and what they do when on.
  - jarvis_compute's ranking fix.
  - second-card.patch applies to what the earlier patches wrote, and
    reverses; the install lists have it.
  - the committed jarvis-desktop fixture equals a fresh run.
"""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, missing  # noqa: E402

for p in (REPO / "tools", HERE / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.append(str(p))

import jarvis_compute as CP  # noqa: E402
import jarvis_second_card as SC  # noqa: E402
import jarvis_agent as AG  # noqa: E402
# The owner's manner line (jarvis_manner.py) has its own suite, test_manner.py;
# this one checks the rest of the request word for word, so it is left out here.
AG._manner_now = lambda *a, **k: None
import jarvis_intake as IN  # noqa: E402
import gen_second_card_cases as G  # noqa: E402
import _ollama_wire as W  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Verdict:
    def __init__(self, allowed, tier="ask", outcome=None, request_id="r1", reason=""):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.request_id, self.reason = request_id, reason


# ------------------------------------------------------------ parsing --


#: A parent environment with the owner's secrets in it, beside what a program
#: really needs (bug audit 3, CONN-2). Windows spellings as Python on Windows
#: stores them (upper-case) and as written (mixed case) - both must work.
_CHILD_BASE = {
    "HUD_TOKEN": "pair-1", "JARVIS_TOKEN": "pair-2", "JARVIS_JOPLIN_TOKEN": "jt",
    "JARVIS_OBSIDIAN_API_KEY": "ok", "GITHUB_TOKEN": "gh", "OPENAI_API_KEY": "sk",
    "SMTP_PASSWORD": "pw", "CLIENT_SECRET": "cs", "OLLAMA_API_KEY": "ol",
    "CUDA_SNEAKY_TOKEN": "ct", "AWS_SECRET_ACCESS_KEY": "aws", "RANDOM_SETTING": "x",
    "SYSTEMROOT": "C:\\Windows", "WINDIR": "C:\\Windows", "PATH": "/bin", "PATHEXT": ".EXE",
    "TEMP": "t", "TMP": "t", "USERPROFILE": "u", "LOCALAPPDATA": "l", "APPDATA": "a",
    "HOMEDRIVE": "C:", "HOMEPATH": "\\u", "COMPUTERNAME": "pc", "USERNAME": "me",
    "PROCESSOR_ARCHITECTURE": "AMD64", "NUMBER_OF_PROCESSORS": "8", "OS": "Windows_NT",
    "PROGRAMFILES": "p", "ProgramFiles(x86)": "p86", "ProgramData": "pd",
    "SystemDrive": "C:", "COMSPEC": "cmd", "HOME": "/h", "LANG": "C", "LC_ALL": "C",
    "OLLAMA_MODELS": "D:\\models", "CUDA_PATH": "C:\\cuda",
}
_CHILD_SECRETS = ("HUD_TOKEN", "JARVIS_TOKEN", "JARVIS_JOPLIN_TOKEN", "JARVIS_OBSIDIAN_API_KEY",
                  "GITHUB_TOKEN", "OPENAI_API_KEY", "SMTP_PASSWORD", "CLIENT_SECRET",
                  "OLLAMA_API_KEY", "CUDA_SNEAKY_TOKEN", "AWS_SECRET_ACCESS_KEY")
_CHILD_ESSENTIALS = ("SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP", "USERPROFILE",
                     "LOCALAPPDATA", "APPDATA", "HOMEDRIVE", "HOMEPATH", "COMPUTERNAME",
                     "USERNAME", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS", "OS",
                     "PROGRAMFILES", "ProgramFiles(x86)", "ProgramData", "SystemDrive",
                     "COMSPEC", "HOME", "LANG", "LC_ALL")


def _leaked(env):
    """Names in `env` that are one of _CHILD_BASE's secrets, or carry one's value."""
    vals = {_CHILD_BASE[s] for s in _CHILD_SECRETS}
    return sorted(k for k in env if k in _CHILD_SECRETS or env[k] in vals)

def t_parsing():
    one = CP.parse_smi(G.SMI["one_card"])
    check("one card: parsed", len(one) == 1 and one[0].name == "NVIDIA GeForce RTX 2080 SUPER"
          and one[0].total_mb == 8192 and one[0].compute_cap == 7.5
          and one[0].display_active is True and one[0].uuid == G.U_2080S, repr(one))
    two = CP.parse_smi(G.SMI["2080s_2060"])
    check("2080 Super + 2060: both, in nvidia-smi order",
          [d.name for d in two] == ["NVIDIA GeForce RTX 2080 SUPER", "NVIDIA GeForce RTX 2060"]
          and two[1].total_mb == 12288 and two[1].display_active is False)
    ti = CP.parse_smi(G.SMI["2080s_2080ti"])
    check("2080 Super + 2080 Ti: 11,264 MiB", ti[1].total_mb == 11264 and ti[1].compute_cap == 7.5)
    p100 = CP.parse_smi(G.SMI["2080s_p100"])
    check("+ a P100: compute 6.0", p100[1].compute_cap == 6.0 and p100[1].total_mb == 16384)
    old = CP.parse_smi(G.SMI_OLD_DRIVER, CP.FIELDS_OLD)
    check("old driver, no compute_cap column: generation looked up by name",
          [d.compute_cap for d in old] == [7.5, 7.5], repr(old))
    check("a name nobody listed: unknown, not guessed",
          CP.compute_from_name("NVIDIA Quadro P6000 Special") is None)
    check("garbage parses to nothing",
          CP.parse_smi("Failed to initialize NVML: Driver/library version mismatch\n") == []
          and CP.parse_smi("0, x, y\n,,,,,,\n") == []
          and CP.parse_smi("0, GPU-1, A, [N/A], 1, 7.5, Enabled") == [])
    check("[N/A] free memory reads as 0, not a crash",
          CP.parse_smi("0, GPU-ab, X, 8192, [N/A], 7.5, [N/A]")[0].free_mb == 0)
    # The query ladder: an old driver refuses the full query; the one without
    # compute_cap is used, and the result says capable.
    with G.World(G.SMI["2080s_2060"], old_driver=G.SMI_OLD_DRIVER):
        det = SC.detect(fresh=True)
    check("old driver: the full query refused, the next one used, still capable",
          det["capable"] is True and det["second"]["name"] == "NVIDIA GeForce RTX 2060", det["why"])
    with G.World("garbage\nmore garbage\n"):
        det = SC.detect(fresh=True)
    check("garbage from nvidia-smi: not capable, and says so",
          det["capable"] is False and "no NVIDIA graphics card" in det["why"], det["why"])


def t_primary_rule():
    devs = CP.parse_smi(G.SMI["2060_first"])
    p, why = CP.primary(devs, configured="")
    check("the monitor decides, whatever the numbering",
          p.name == "NVIDIA GeForce RTX 2080 SUPER" and "monitor" in why, why)
    p, why = CP.primary(devs, configured=G.U_2060)
    check("[compute] primary_gpu by id wins", p.uuid == G.U_2060 and "id" in why, why)
    p, why = CP.primary(devs, configured="1")
    check("[compute] primary_gpu by number works, and says an id is safer",
          p.index == 1 and "safer" in why, why)
    p, why = CP.primary(devs, configured="GPU-deadbeef-0000")
    check("a primary_gpu that is not here is ignored, and said to be",
          p.name == "NVIDIA GeForce RTX 2080 SUPER" and "ignored" in why, why)
    nodisp = [CP.Device(0, "A", 8192, 1), CP.Device(1, "B", 12288, 12000)]
    p, why = CP.primary(nodisp, configured="")
    check("no monitor seen: nvidia-smi's first card", p.index == 0 and "first" in why, why)
    check("no cards: None", CP.primary([], configured="")[0] is None)


def t_capable_and_not():
    cases = [
        ("one_card", False, "only one graphics card found"),
        ("2080s_2060", True, "RTX 2060 (12 GB) can take"),
        ("2060_first", True, "RTX 2060 (12 GB) can take"),
        ("2080s_2080ti", True, "2080 Ti (11 GB) can take"),
        ("2080s_p100", False, "P100-PCIE-16GB is older than Turing"),
        ("2080s_1080", False, "GTX 1080 is older than Turing"),
        ("2080s_2060_6gb", False, "6 GB, which is not enough"),
    ]
    for name, capable, words in cases:
        with G.World(G.SMI[name]):
            det = SC.detect(fresh=True)
        check(f"{name}: capable={capable}, because '{words}'",
              det["capable"] is capable and words in det["why"], det["why"])
    with G.World(G.SMI["2080s_p100"]):
        det = SC.detect(fresh=True)
    check("the P100's reason points at MODEL-TOPOLOGY", "MODEL-TOPOLOGY" in det["why"])
    roles = {c["name"]: c["role"] for c in det["cards"]}
    check("cards[] names the P100 unused and the 2080 Super primary",
          roles == {"NVIDIA GeForce RTX 2080 SUPER": "primary", "Tesla P100-PCIE-16GB": "unused"})
    unknown = "0, GPU-aa11bb22-0000, NVIDIA GeForce RTX 2080 SUPER, 8192, 6000, 7.5, Enabled\n" \
              "1, GPU-cc33dd44-0000, Mystery Card 9000, 16384, 16000, [N/A], Disabled\n"
    with G.World(unknown):
        det = SC.detect(fresh=True)
    check("an unknown generation is 'not capable', in words",
          det["capable"] is False and "could not tell which generation" in det["why"], det["why"])
    noid = "0, , NVIDIA GeForce RTX 2080 SUPER, 8192, 6000, 7.5, Enabled\n" \
           "1, , NVIDIA GeForce RTX 2060, 12288, 12000, 7.5, Disabled\n"
    with G.World(noid):
        det = SC.detect(fresh=True)
    check("no card id: not capable (work is only ever pointed at a card by id)",
          det["capable"] is False and "id" in det["why"], det["why"])
    with G.World(G.SMI["2080s_2060"]):
        det = SC.detect(fresh=True)
    check("the 12 GB card gets qwen3:8b at 32K (7.69 GiB): HARDWARE-PROFILES 4.4, and more "
          "room than the main card's 16K (T3)",
          SC._feature_model("long_context", det) == ("qwen3:8b", 32768, 7.69))
    with G.World(G.SMI["2080s_2080ti"]):
        det = SC.detect(fresh=True)
    check("the 11 GB 2080 Ti gets qwen3:8b at 32K (7.69 GiB)",
          SC._feature_model("long_context", det) == ("qwen3:8b", 32768, 7.69))
    check("the arithmetic in the comment holds: 8B cache at 32K is 2.39 GiB; 7.36 needed "
          "(HARDWARE-PROFILES 8.2) + 0.33 start-up = 7.69; it fits a 12 GB card's 10.32",
          round(2 * 36 * 8 * 128 * 1.0625 * 32768 / 2 ** 30, 2) == 2.39
          and round(4.67 + 2.39 + 0.30, 2) == 7.36 and round(7.36 + 0.33, 2) == 7.69
          and round(12 - 0.60 - 0.33 - 0.75, 2) == 10.32)


# ------------------------------------------------------- a third card --
#
# docs/GPU-SUPPORT-RESEARCH-2026-09-27.md's recommendation #1: reshape
# detection to keep every capable extra card, not just the biggest, with
# NO behaviour change on a 1- or 2-card PC. What is checked here:
#
#   - 0 cards (t_capable_and_not's "garbage" case already covers this: no
#     card at all), 1, 2 and 3 detected, each with the right det["_lanes"].
#   - a third card that is too old (below Turing) is correctly EXCLUDED
#     from _lanes and still explained in cards[]'s own "why", by the exact
#     same words a not-capable second card already gets.
#   - det["second"] / det["_second"] / det["cards"] (the public contract)
#     are BYTE-FOR-BYTE the same with 3 cards present as they would be if
#     the third card were not read at all - proving the reshape changed
#     nothing a PC with fewer cards, or today's 2-card owner, can see.
#   - extra_lanes() surfaces the third (and beyond) card, in the same
#     plain-dict shape det["second"] already uses.

#: A third capable card (a second 2080 Ti, distinct id) for the tests below.
U_2080TI_2 = "GPU-51c0e8aa-6d2f-4b19-8e37-2a4c9f0b6d59"
#: Three capable cards: the primary, the second (the 2060, more memory) and
#: a third (the second 2080 Ti) - shared by t_third_card_reshape and the
#: third-card-lane tests below.
SMI_THREE = (f"0, {G.U_2080S}, NVIDIA GeForce RTX 2080 SUPER, 8192, 6120, 7.5, Enabled\n"
            f"1, {G.U_2060}, NVIDIA GeForce RTX 2060, 12288, 12030, 7.5, Disabled\n"
            f"2, {U_2080TI_2}, NVIDIA GeForce RTX 2080 Ti, 11264, 11010, 7.5, Disabled\n")


def t_third_card_reshape():
    # Two capable extra cards: the 2060 (12,288 MB) and a 2080 Ti (11,264 MB).
    # "second" must still be the 2060 (more memory) - completely unchanged
    # from today's single-candidate rule.
    three = (f"0, {G.U_2080S}, NVIDIA GeForce RTX 2080 SUPER, 8192, 6120, 7.5, Enabled\n"
             f"1, {G.U_2060}, NVIDIA GeForce RTX 2060, 12288, 12030, 7.5, Disabled\n"
             f"2, {U_2080TI_2}, NVIDIA GeForce RTX 2080 Ti, 11264, 11010, 7.5, Disabled\n")
    with G.World(three):
        det3 = SC.detect(fresh=True)
    with G.World(G.SMI["2080s_2060"]):
        det2 = SC.detect(fresh=True)
    check("3 capable-extra cards: still capable, 'second' is unchanged (the 2060)",
          det3["capable"] is True and det3["second"]["name"] == "NVIDIA GeForce RTX 2060")
    check("the public contract (second/cards/why) is untouched by a 3rd capable card: "
          "same second, same why, same primary as the 2-card case",
          det3["second"] == det2["second"] and det3["why"] == det2["why"]
          and det3["primary"] == det2["primary"])
    check("cards[] still says the SAME thing about the 2080 Ti it always would have: "
          "'unused', 'capable, but the RTX 2060 has more memory'",
          next(c for c in det3["cards"] if "2080 Ti" in c["name"])
          == {"index": 2, "uuid": U_2080TI_2, "name": "NVIDIA GeForce RTX 2080 Ti",
              "total_mb": 11264, "free_mb": 11010, "compute_cap": 7.5,
              "display_active": False, "role": "unused",
              "why": "capable, but the NVIDIA GeForce RTX 2060 has more memory"})
    check("det['_lanes'] (internal) now keeps BOTH capable extra cards, best memory first",
          [c.name for c in det3["_lanes"]]
          == ["NVIDIA GeForce RTX 2060", "NVIDIA GeForce RTX 2080 Ti"])
    check("det['_lanes'][0] IS the same object as det['_second'] - 'second' really is lanes[0]",
          det3["_lanes"][0] is det3["_second"])
    extra = SC.extra_lanes(det3)
    check("extra_lanes() surfaces exactly the third card, in second's own plain-dict shape",
          extra == [{"uuid": U_2080TI_2, "index": 2, "name": "NVIDIA GeForce RTX 2080 Ti",
                    "total_mb": 11264, "compute_cap": 7.5}])
    check("a 2-card PC has no extra lanes at all", SC.extra_lanes(det2) == [])


#: A second RTX 2060, tying the first one's memory exactly (12,288 MB each) -
#: for t_third_card_memory_tie below (2026-09-28 hardware-detection audit,
#: finding #2).
U_2060_TIE = "GPU-7d2c1e04-9a3b-4f6e-8c15-b0e2a41d7f93"


def t_third_card_memory_tie():
    # Two capable extra cards with the SAME memory (12,288 MB): the 2060 at
    # index 1 and a second 2060 at index 2. The tie-break (index) still
    # picks index 1 as "second" - unchanged - but the OTHER one's "why"
    # must say they tied, never claim the picked card "has more memory"
    # when it does not.
    tie = (f"0, {G.U_2080S}, NVIDIA GeForce RTX 2080 SUPER, 8192, 6120, 7.5, Enabled\n"
           f"1, {G.U_2060}, NVIDIA GeForce RTX 2060, 12288, 12030, 7.5, Disabled\n"
           f"2, {U_2060_TIE}, NVIDIA GeForce RTX 2060, 12288, 12010, 7.5, Disabled\n")
    with G.World(tie):
        det = SC.detect(fresh=True)
    check("tied memory: 'second' is still the lower-index card, unchanged",
          det["second"]["uuid"] == G.U_2060)
    check("the tied card's 'why' says they tied, never the false 'has more memory'",
          next(c for c in det["cards"] if c["uuid"] == U_2060_TIE)["why"]
          == "capable, but the NVIDIA GeForce RTX 2060 has the same amount of "
             "memory and was already picked")

    # A third card that is genuinely NOT capable (below Turing): excluded
    # from _lanes, and cards[] gives its REAL reason, never the generic
    # "more memory" line a merely-smaller capable card would get.
    old_third = (f"0, {G.U_2080S}, NVIDIA GeForce RTX 2080 SUPER, 8192, 6120, 7.5, Enabled\n"
                 f"1, {G.U_2060}, NVIDIA GeForce RTX 2060, 12288, 12030, 7.5, Disabled\n"
                 f"2, {G.U_P100}, Tesla P100-PCIE-16GB, 16384, 16270, 6.0, Disabled\n")
    with G.World(old_third):
        det_old = SC.detect(fresh=True)
    check("an incapable 3rd card does not change 'second' or capability",
          det_old["capable"] is True and det_old["second"]["name"] == "NVIDIA GeForce RTX 2060")
    check("the incapable 3rd card is excluded from _lanes",
          [c.name for c in det_old["_lanes"]] == ["NVIDIA GeForce RTX 2060"])
    check("extra_lanes() leaves the incapable 3rd card out entirely",
          SC.extra_lanes(det_old) == [])
    p100_row = next(c for c in det_old["cards"] if "P100" in c["name"])
    check("cards[] gives the P100's REAL reason (older than Turing), not 'more memory'",
          p100_row["role"] == "unused" and "older than Turing" in p100_row["why"]
          and "more memory" not in p100_row["why"], p100_row["why"])

    # 0 and 1 card: _lanes is always [], never missing or None.
    with G.World("garbage only\n"):
        det0 = SC.detect(fresh=True)
    check("no card at all: _lanes is [], not missing", det0.get("_lanes") == [])
    with G.World(G.SMI["one_card"]):
        det1 = SC.detect(fresh=True)
    check("one card: _lanes is [] (nothing else to be a lane)", det1["_lanes"] == [])
    check("one card: extra_lanes() is []", SC.extra_lanes(det1) == [])

    # extra_lanes() never raises on a bad/missing det.
    check("extra_lanes({}) is [] (no '_lanes' key at all)", SC.extra_lanes({}) == [])
    check("extra_lanes(None-ish) never raises", SC.extra_lanes({"_lanes": None}) == [])


def t_third_card_under_a_preset():
    """_detect_preset's own mirror of _lanes - a preset has exactly one lane
    slot (jarvis_hardware.py's own two-slot design, left unchanged - see the
    module docstring), so this only proves _lanes is always present and
    always matches the one lane card a preset can have (or [] when the
    lanes run inside the everyday Ollama, or there is no lane at all)."""
    import types
    chat_dev = CP.Device(index=0, name="NVIDIA GeForce RTX 2080 SUPER", total_mb=8192,
                         free_mb=6000, uuid=G.U_2080S, compute_cap=7.5, display_active=True)
    lane_dev = CP.Device(index=1, name="NVIDIA GeForce RTX 2060", total_mb=12288,
                         free_mb=12000, uuid=G.U_2060, compute_cap=7.5, display_active=False)
    chat_card = types.SimpleNamespace(uuid=G.U_2080S, name=chat_dev.name, total_gib=8.0)
    lane_card = types.SimpleNamespace(uuid=G.U_2060, name=lane_dev.name, total_gib=12.0)
    base = {"preset": "features", "long": ("qwen3:8b", 32768, 7.69), "pictures": None,
            "pictures_mode": None, "fit_target": None, "why_none": {}}
    with mock.patch.object(SC, "_cards", return_value=[chat_dev, lane_dev]):
        plan_with_lane = dict(base, chat_card=chat_card, lane_card=lane_card)
        det = SC._detect_preset(plan_with_lane, fresh=True)
        check("a preset with a real lane card: _lanes is exactly that one card",
              [c.name for c in det["_lanes"]] == ["NVIDIA GeForce RTX 2060"]
              and det["_lanes"][0] is lane_dev)
        check("extra_lanes() is [] under a preset (only one lane slot exists)",
              SC.extra_lanes(det) == [])
        plan_main = dict(base, chat_card=chat_card, lane_card=None)
        det_main = SC._detect_preset(plan_main, fresh=True)
        check("a preset with no separate lane card (main=True): _lanes is []",
              det_main["_lanes"] == [] and det_main["_main"] is True)


# ------------------------------------------------ a third card's own lane --
#
# The follow-up pass the reshape above deliberately left for later
# (jarvis_second_card.py's module docstring, "A THIRD CARD'S OWN LANE"):
# assigning one of the five features to a genuinely capable third card,
# its own approval card (THIRD_ACTION), and its own lane process
# (_THIRD_LANE), running alongside the second card's own lane - never
# instead of it, and never a default winner.

def t_third_port_never_shares_the_second_lanes_port():
    """Bug audit 2026-09-29: a [second_card] port of 11436 (the third lane's
    own default) made _third_port() fall back to that same 11436, so the two
    Ollama copies, which run at the same time, would fight over one port."""
    def with_cfg(cfg):
        return mock.patch.object(SC, "_cfg", lambda k, d=None: cfg.get(k, d))
    for cfg, label in (({}, "no config"),
                       ({"port": SC.DEFAULT_THIRD_PORT}, "second port = the third's default"),
                       ({"third_port": SC.DEFAULT_PORT}, "third port = the second's default"),
                       ({"third_port": SC.MAIN_OLLAMA_PORT}, "third port = the main Ollama's"),
                       ({"port": SC.DEFAULT_THIRD_PORT, "third_port": 11436}, "both set to 11436")):
        with with_cfg(cfg):
            t, sec = SC._third_port(), SC._port()
            check(f"{label}: the third lane's port is its own",
                  t not in (sec, SC.MAIN_OLLAMA_PORT) and 1024 <= t <= 65535, (t, sec))


def t_third_card_no_default_winner():
    with G.World(SMI_THREE) as w:
        w.switches(master=True, long_context=True)
        st = SC.status()
        check("a capable third card sits there, unassigned, and does nothing",
              st["third"]["capable"] is True and st["third"]["assigned"] is None
              and st["third"]["lane"]["state"] == "off"
              and "Assign one of the switches above" in st["third"]["why"], st["third"])
        check("only ONE process was started (the second lane, for long_context)",
              len(w.started) == 1)
        check("assignable lists only the switches that are actually on",
              st["third"]["assignable"] == ["long_context"])
        card = st["third"]["card"]
        check("the third card is the 2080 Ti, not the 2060 (still 'second')",
              card is not None and card["uuid"] == U_2080TI_2
              and st["detected"]["second"]["uuid"] == G.U_2060)
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, long_context=True)
        st = SC.status()
        check("only two cards: no capable third card, in words",
              st["third"]["capable"] is False and st["third"]["card"] is None
              and "No capable third graphics card" in st["third"]["why"])


def t_third_card_assign_needs_feature_on_first():
    with G.World(SMI_THREE) as w:
        code, out = SC.request_change("third", assign="vision")
        check("assigning a feature that is not on yet: 400, in words, no card",
              code == 400 and "Turn" in out["error"] and "Pictures" in out["error"], out)
        code, out = SC.request_change("third", assign="nope")
        check("an unknown feature id: 400", code == 400 and "second-card feature" in out["error"])
        code, out = SC.request_change("third", assign=123)
        check("assign must be a string or null", code == 400 and "assign" in out["error"])
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, long_context=True)
        code, out = SC.request_change("third", assign="long_context")
        check("no capable third card: 503, in words",
              code == 503 and "no capable third graphics card" in out["error"], out)


def t_third_card_approval_card():
    with G.World(SMI_THREE) as w:
        w.switches(master=True, long_context=True)
        seen = []
        gate = lambda a, d, p: seen.append((a, d, p)) or Verdict(True, "ask", "approved")
        code, out = SC.request_change("third", assign="long_context", gate=gate,
                                      spawn=lambda fn: None)
        check("assigning: a card is raised, nothing moved yet",
              code == 200 and out["pending"] is True and out["assigned"] is None
              and SC._read_switches()["third_feature"] is None, out)
        check("status lists 'third' as pending",
              "third" in SC.status()["pending"])
        code2, out2 = SC.request_change("third", assign="long_context", gate=gate,
                                        spawn=lambda fn: None)
        check("a second ask while the card waits: 409",
              code2 == 409 and "already waiting" in out2["error"])
        code, out = SC.request_change("third", assign=None)
        check("unassigning while waiting withdrew the card, at once, no card",
              code == 200 and out["assigned"] is None and not seen)
        check("status no longer lists it as pending", "third" not in SC.status()["pending"])
        # The real thing: the card is answered yes.
        code, out = SC.request_change("third", assign="long_context", gate=gate)
        check("approved: exactly one card, action second_card_third_assign",
              len(seen) == 1 and seen[0][0] == SC.THIRD_ACTION, seen)
        action, detail, text = seen[0]
        check("the card names BOTH cards, says instead-of, says at the same time, "
              "says 127.0.0.1 only, and that nothing leaves",
              "Longer conversations" in text and "2080 Ti" in text and "2060" in text
              and "instead of" in text and "AT THE SAME TIME" in text
              and "127.0.0.1:11436" in text and "Nothing leaves this PC" in text
              and "If you say no" in text and detail["leaves_this_pc"] is False, text)
        check("and the assignment is set", SC._read_switches()["third_feature"] == "long_context")
        code, out = SC.request_change("third", assign="long_context")
        check("asking again for the SAME assignment: already on, no card",
              code == 200 and out["pending"] is False and out["assigned"] == "long_context", out)
        seen.clear()
        # Denied: stays unassigned.
        SC.request_change("third", assign=None)
        code, out = SC.request_change("third", assign="vision", gate=gate)
        check("vision is not on yet: refused before any card",
              code == 400 and not seen, out)
        w.switches(master=True, long_context=True, vision=True)
        deny = lambda a, dd, p: Verdict(False, "ask", "denied")
        SC.request_change("third", assign="vision", gate=deny)
        check("denied: stays unassigned", SC._read_switches()["third_feature"] is None)
        # Withdrawn mid-flight: answered yes, but changed while it waited.
        held = []
        SC.request_change("third", assign="vision",
                          gate=lambda a, dd, p: Verdict(True, "ask", "approved"),
                          spawn=held.append)
        SC.request_change("third", assign=None)
        held[0]()
        check("approved after being changed while it waited: stays unassigned",
              SC._read_switches()["third_feature"] is None
              and SC._LAST["third"]["outcome"] == "withdrawn")
        # The feature is turned off while its own third-card card waits.
        held2 = []
        SC.request_change("third", assign="vision",
                          gate=lambda a, dd, p: Verdict(True, "ask", "approved"),
                          spawn=held2.append)
        SC.request_change("vision", False)
        held2[0]()
        check("the feature went off while the card waited: refused, stays unassigned",
              SC._read_switches()["third_feature"] is None
              and SC._LAST["third"]["outcome"] == "refused"
              and "Pictures" in SC._LAST["third"]["reason"], SC._LAST.get("third"))
        code, out = SC.request_change("third", assign="long_context", gate=gate,
                                      tier_of=lambda a: "auto")
        check("tier not 'ask': refused before any card",
              code == 503 and "must be 'ask'" in out["error"])


def t_third_card_lane_independent():
    with G.World(SMI_THREE, installed=("qwen3:8b", "qwen3:14b", "qwen2.5vl:7b")) as w:
        w.switches(master=True, long_context=True, vision=True, third_feature="vision",
                   third_card=U_2080TI_2)
        st = SC.status()
        check("both lanes are running: the second (long_context) and the third (vision)",
              st["lane"]["state"] == "running" and st["third"]["lane"]["state"] == "running",
              (st["lane"], st["third"]))
        check("two SEPARATE processes were started, on two different ports",
              len(w.started) == 2)
        ports = sorted(p.kwargs["env"]["OLLAMA_HOST"] for p in w.started)
        check("11435 (the second lane) and 11436 (the third lane), never the same port",
              ports == ["127.0.0.1:11435", "127.0.0.1:11436"], ports)
        third_env = next(p.kwargs["env"] for p in w.started
                         if p.kwargs["env"]["OLLAMA_HOST"] == "127.0.0.1:11436")
        check("the third lane is pinned to the THIRD card's id, not the second's",
              third_env["CUDA_VISIBLE_DEVICES"] == U_2080TI_2
              and G.U_2060 not in third_env["CUDA_VISIBLE_DEVICES"])
        lc = SC.lane_for("long_context")
        vi = SC.lane_for("vision")
        check("long_context still answers from the second card's own lane",
              lc is not None and lc.url == "http://127.0.0.1:11435")
        check("vision answers from the THIRD card's lane, at the same time",
              vi is not None and vi.url == "http://127.0.0.1:11436"
              and "third graphics card" in vi.why, vi)
        # Turning vision off stops ONLY the third lane; long_context (still on
        # the second) keeps running - the two lanes are independent.
        SC.request_change("vision", False)
        st = SC.status()
        check("vision off: only the third lane stops; the second keeps running",
              st["third"]["lane"]["state"] == "off" and st["lane"]["state"] == "running")
        check("the assignment itself is kept (vision could be turned back on)",
              SC._read_switches()["third_feature"] == "vision")
        check("status says the assignment is kept but the feature is off",
              "is off" in st["third"]["why"], st["third"]["why"])
    # Everything on the second card moved to the third: the second lane does
    # not start at all - starting it would hold the second card open for
    # nothing (2026-09-28's fix to _wanted()).
    with G.World(SMI_THREE) as w:
        w.switches(master=True, long_context=True, third_feature="long_context",
                   third_card=U_2080TI_2)
        st = SC.status()
        check("moved entirely to the third card: the second lane stays off, in words",
              st["lane"]["state"] == "off" and "moved to the third card" in st["lane"]["why"],
              st["lane"])
        check("only ONE process was started (the third lane)", len(w.started) == 1)
        check("the third lane is running, and lane_for('long_context') uses it",
              st["third"]["lane"]["state"] == "running"
              and SC.lane_for("long_context").url == "http://127.0.0.1:11436")


def t_switches():
    with G.World(G.SMI["2080s_2060"]) as w:
        seen = []
        gate = lambda a, d, p: seen.append((a, d, p)) or Verdict(True, "ask", "approved")
        code, out = SC.request_change("long_context", True, gate=gate)
        check("a feature before the main switch: refused, in words",
              code == 400 and "main switch" in out["error"] and not seen, out)
        code, out = SC.request_change("master", True, gate=gate, spawn=lambda fn: None)
        check("master ON: a card is raised, nothing is on yet",
              code == 200 and out == {"ok": True, "enabled": False, "pending": True,
                                      "message": out["message"]}
              and SC._read_switches()["master"] is False)
        code2, out2 = SC.request_change("master", True, gate=gate, spawn=lambda fn: None)
        check("a second ON while the card waits: 409", code2 == 409 and "already waiting" in out2["error"])
        check("status lists it as pending", SC.status()["pending"] == ["master"])
        code, out = SC.request_change("master", False)
        check("OFF is at once and needs no card", code == 200 and out["enabled"] is False and not seen)
        check("OFF withdrew the waiting card", SC.status()["pending"] == [])
        # Now the real thing: the card is answered yes.
        code, out = SC.request_change("master", True, gate=gate)
        check("approved: exactly one card, action second_card_enable",
              len(seen) == 1 and seen[0][0] == "second_card_enable", seen)
        d, text = seen[0][1], seen[0][2]
        check("the card names the card, says 127.0.0.1 only, and that nothing leaves",
              "RTX 2060" in text and "127.0.0.1:11435" in text and "Nothing leaves this PC" in text
              and "If you say no" in text and d["leaves_this_pc"] is False, text)
        check("and the main switch is on", SC._read_switches()["master"] is True)
        seen.clear()
        code, out = SC.request_change("browser_control", True, gate=gate)
        check("browser_control without long_context: refused, no card",
              code == 400 and "Longer conversations" in out["error"] and not seen, out)
        code, out = SC.request_change("long_context", True, gate=gate)
        check("long_context: one card, with the model and memory on it",
              code == 200 and len(seen) == 1 and "qwen3:8b" in seen[0][2]
              and "7.7 GB" in seen[0][2] and seen[0][1]["model"] == "qwen3:8b")
        check("long_context is on", SC._read_switches()["features"]["long_context"] is True)
        # A "yes" that is not a person: refused.
        for label, v in (("tier notify", Verdict(True, "notify", "notify")),
                         ("tier auto", Verdict(True, "auto", "auto")),
                         ("denied", Verdict(False, "ask", "denied")),
                         ("timed out", Verdict(False, "ask", "timed_out")),
                         ("old gate, allowed on auto", Verdict(True, "auto", None))):
            SC.request_change("vision", False)
            SC.request_change("vision", True, gate=lambda a, dd, p, v=v: v)
            check(f"{label}: vision stays off", SC._read_switches()["features"]["vision"] is False)
        # Switched off while the card waited, then approved: stays off.
        held = []
        SC.request_change("vision", True, gate=lambda a, dd, p: Verdict(True, "ask", "approved"),
                          spawn=lambda fn: held.append(fn))
        SC.request_change("vision", False)
        held[0]()
        check("OFF while waiting, then approved: the later OFF wins",
              SC._read_switches()["features"]["vision"] is False)
        # AP-5: two full rounds; the first card is answered last.
        cards = []
        yes = lambda a, dd, p: Verdict(True, "ask", "approved")
        SC.request_change("vision", True, gate=yes, spawn=cards.append)
        SC.request_change("vision", False)
        SC.request_change("vision", True, gate=yes, spawn=cards.append)
        SC.request_change("vision", False)
        cards[0]()
        check("two ON/OFF rounds, the FIRST card approved: the later OFF still wins",
              len(cards) == 2 and SC._read_switches()["features"]["vision"] is False)
        cards[1]()
        check("... and the second card too",
              SC._read_switches()["features"]["vision"] is False)
        code, out = SC.request_change("vision", True, gate=gate, tier_of=lambda a: "auto")
        check("tier not 'ask': refused before any card", code == 503 and "must" in out["error"]
              and "be 'ask'" in out["error"])
        check("unknown feature: 400", SC.request_change("nope", True)[0] == 400)
        check("enabled must be a boolean", SC.handle_post({"feature": "vision", "enabled": "yes"})[0] == 400)
        check("a body that is not an object: 400", SC.handle_post([1])[0] == 400)
    with G.World(G.SMI["one_card"]) as w:
        seen = []
        code, out = SC.request_change("master", True, gate=lambda *a: seen.append(a))
        check("ON with no capable card: 503 with the reason, no card",
              code == 503 and "only one graphics card" in out["error"] and not seen, out)
    with G.World(G.SMI["2080s_1080"]):
        code, out = SC.request_change("master", True, gate=lambda *a: None)
        check("ON with an old second card: 503, says why", code == 503 and "older than Turing" in out["error"])
    # AP-4: the cards say exactly what starts if the owner says yes.
    with G.World(G.SMI["2080s_2060"]) as w:
        seen = []
        gate = lambda a, d, p: seen.append(p) or Verdict(True, "ask", "approved")
        w.switches(master=True, long_context=True, browser_control=True)
        SC.request_change("master", False)
        check("master OFF keeps the owner's feature choices",
              SC._read_switches()["features"]["long_context"] is True
              and SC._read_switches()["features"]["browser_control"] is True)
        SC.request_change("master", True, gate=gate)
        check("master card with features left on: names them, never 'nothing starts yet'",
              seen and "nothing starts yet" not in seen[0]
              and "\"Longer conversations\" and \"Browser control\" start working again at once"
              in seen[0], seen)
        check("... and approving it really starts the lane (the card was true)",
              len(w.started) == 1 and w.running())
        seen.clear()
        SC.request_change("long_context", False)
        check("Longer conversations OFF keeps Browser control's choice",
              SC._read_switches()["features"]["browser_control"] is True)
        SC.request_change("long_context", True, gate=gate)
        check("the long_context card says Browser control comes back too",
              seen and "\"Browser control\" is still switched on from before, so it starts "
              "working again too" in seen[0], seen)
        seen.clear()
        w.switches(master=False)
        SC.request_change("master", True, gate=gate)
        check("master card with nothing left on: 'nothing starts yet'",
              seen and "nothing starts yet" in seen[0], seen)
        # A feature's card answered after the main switch went off.
        held = []
        SC.request_change("vision", True, gate=lambda a, dd, p: Verdict(True, "ask", "approved"),
                          spawn=held.append)
        SC.request_change("master", False)
        held[0]()
        check("feature approved after master went OFF: stays off, refused with the reason",
              SC._read_switches()["features"]["vision"] is False
              and SC._LAST["vision"]["outcome"] == "refused"
              and "main second-card switch was turned off" in SC._LAST["vision"]["reason"],
              SC._LAST.get("vision"))
    # The approval must never be automatic: the module never calls approve.
    src = (HERE / "jarvis_second_card.py").read_text(encoding="utf-8")
    code_only = re.sub(r'(?s)""".*?"""', "", src)
    check("no auto-approve anywhere in the module",
          "auto_approve" not in code_only and "confirm_auto" not in code_only)


# ---------------------------------------------------------- the process --

def t_the_second_ollama():
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, long_context=True)
        st = SC.status()
        check("master + a feature on: the second Ollama is started, and running",
              len(w.started) == 1 and st["lane"]["state"] == "running", st["lane"])
        p = w.started[0]
        env = p.kwargs["env"]
        check("the command is `ollama serve`", p.args == ["/usr/local/bin/ollama", "serve"])
        check("it listens on 127.0.0.1:11435 only", env["OLLAMA_HOST"] == "127.0.0.1:11435")
        check("it sees only the second card, by its id",
              env["CUDA_VISIBLE_DEVICES"] == G.U_2060 and G.U_2080S not in env["CUDA_VISIBLE_DEVICES"])
        check("PCI order, q8_0 cache, one model, one conversation, 32K",
              env["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID" and env["OLLAMA_KV_CACHE_TYPE"] == "q8_0"
              and env["OLLAMA_MAX_LOADED_MODELS"] == "1" and env["OLLAMA_NUM_PARALLEL"] == "1"
              and env["OLLAMA_CONTEXT_LENGTH"] == "32768")
        check("flash attention left to Ollama's auto (MODEL-TOPOLOGY: do not force it)",
              "OLLAMA_FLASH_ATTENTION" not in env)
        lane = SC.lane_for("long_context")
        check("lane_for: the loopback lane, the model, 32K",
              lane is not None and lane.url == "http://127.0.0.1:11435"
              and lane.model == "qwen3:8b" and lane.num_ctx == 32768, repr(lane))
        check("asking again does not start a second one", len(w.started) == 1)
        SC.request_change("long_context", False)
        check("everything off: it is stopped - that one, and only that one",
              w.killed == [p] and SC._LANE.state == "off")
    for bad in (dict(host="0.0.0.0"), dict(host="192.168.1.5")):
        try:
            SC.lane_env(G.U_2060, port=11435, num_ctx=16384, base={}, **bad)
            check(f"lane_env refuses host {bad['host']}", False)
        except ValueError:
            check(f"lane_env refuses host {bad['host']}", True)
    for bad_id in ("1", "0", "", "GPU-x; rm -rf"):
        try:
            SC.lane_env(bad_id, port=11435, num_ctx=16384, base={})
            check(f"lane_env refuses the card id {bad_id!r}", False)
        except ValueError:
            check(f"lane_env refuses the card id {bad_id!r}", True)
    try:
        SC.lane_env(G.U_2060, port=11434, num_ctx=1, base={})
        check("lane_env refuses the everyday Ollama's port", False)
    except ValueError:
        check("lane_env refuses the everyday Ollama's port", True)
    env = SC.lane_env(G.U_2060, port=11435, num_ctx=1, base={
        "OLLAMA_HOST": "0.0.0.0:11434", "OLLAMA_ORIGINS": "*", "OLLAMA_SCHED_SPREAD": "1",
        "OLLAMA_FLASH_ATTENTION": "1", "PATH": "/bin"})
    check("inherited settings that would widen it are dropped",
          env["OLLAMA_HOST"] == "127.0.0.1:11435" and "OLLAMA_ORIGINS" not in env
          and "OLLAMA_SCHED_SPREAD" not in env and "OLLAMA_FLASH_ATTENTION" not in env
          and env["PATH"] == "/bin")
    # CONN-2: built from an allowlist, so no secret of Jarvis's goes to Ollama.
    env = SC.lane_env(G.U_2060, port=11435, num_ctx=1, base=_CHILD_BASE)
    check("lane_env: no token, key, password or secret of Jarvis's reaches the second Ollama",
          not _leaked(env), repr(_leaked(env)))
    check("lane_env: what Windows needs to start a program is kept, and OLLAMA_MODELS",
          all(env.get(k) == _CHILD_BASE[k] for k in _CHILD_ESSENTIALS + ("OLLAMA_MODELS",)),
          repr(sorted(set(_CHILD_ESSENTIALS) - set(env))))
    check("lane_env: an unrelated setting is not inherited",
          "RANDOM_SETTING" not in env and "CUDA_PATH" not in env)
    # Vulkan is on in Ollama by default and ignores CUDA_VISIBLE_DEVICES, so
    # removing GGML_VK_VISIBLE_DEVICES alone left the other card reachable.
    check("lane_env switches Ollama's Vulkan route off (OLLAMA_VULKAN=0)",
          env.get("OLLAMA_VULKAN") == "0" and "GGML_VK_VISIBLE_DEVICES" not in env, env)
    check("lane_env makes the second Ollama refuse cloud models itself (OLLAMA_NO_CLOUD=1)",
          env.get("OLLAMA_NO_CLOUD") == "1", env)
    check("...even when the owner's own environment turns it on",
          SC.lane_env(G.U_2060, port=11435, num_ctx=1,
                      base={"OLLAMA_VULKAN": "1"}).get("OLLAMA_VULKAN") == "0")
    check("flash attention 'on' in the toml is honoured",
          SC.lane_env(G.U_2060, port=11435, num_ctx=1, base={}, flash="on")["OLLAMA_FLASH_ATTENTION"] == "1")
    # flash_attention = "off" with the lane's q8_0 cache: llama.cpp refuses
    # to load the model (llama-context.cpp ~3737-3741). Refused, in words.
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, long_context=True)
        cfg = {"flash_attention": "off"}
        with mock.patch.object(SC, "_cfg", lambda key, default=None: cfg.get(key, default)):
            st = SC.status()
        check("flash_attention 'off': not started, and says why and what to do",
              not w.started and st["lane"]["state"] == "failed"
              and "flash_attention is \"off\"" in st["lane"]["why"]
              and "q8_0" in st["lane"]["why"] and "Delete that line" in st["lane"]["why"],
              st["lane"])
        cfg["flash_attention"] = "on"
        SC._LANE.failed_at = -1e9
        with mock.patch.object(SC, "_cfg", lambda key, default=None: cfg.get(key, default)):
            st = SC.status()
        check("flash_attention 'on' still starts it",
              len(w.started) == 1 and st["lane"]["state"] == "running", st["lane"])
    with G.World(G.SMI["2080s_2060"], foreign_on_port=True) as w:
        w.switches(master=True, long_context=True)
        st = SC.status()
        check("an Ollama Jarvis did not start holds the port: not used, not stopped",
              st["lane"]["state"] == "failed" and "did not start it" in st["lane"]["why"]
              and not w.started and not w.killed, st["lane"])
        check("and lane_for is None", SC.lane_for("long_context") is None)
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, long_context=True)
        SC._which = lambda name: None
        st = SC.status()
        check("no ollama on PATH: failed, said plainly",
              st["lane"]["state"] == "failed" and "PATH" in st["lane"]["why"])
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, long_context=True)
        SC.status()
        w.started[0].alive = False
        SC._LANE.failed_at = -1e9
        st = SC.status()
        check("it stopped by itself: failed, with the reason",
              st["lane"]["state"] == "failed" and "stopped by itself" in st["lane"]["why"])
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, long_context=True)
        SC.status()
        w.smi = G.SMI["one_card"]
        CP._cache.update(at=-1e9, cards=None)
        st = SC.status()
        check("the card disappears: the lane is stopped, the choice kept",
              w.killed and st["lane"]["state"] == "off" and st["enabled"] is True
              and st["active"] is False and st["features"][0]["enabled"] is True
              and st["features"][0]["active"] is False
              and "choice is kept" in st["features"][0]["why"])


class _FakeColibri:
    """A colibri process as jarvis_big_model records one: alive, never real."""
    pid = 900003

    def poll(self):
        return None


def _colibri_on(uuid):
    """jarvis_big_model's engine, loaded on `uuid` with cuda = "on", the way
    _Engine._start leaves it (the claim included)."""
    import jarvis_big_model as BM
    BM._reset_for_tests()
    BM._ENGINE.state, BM._ENGINE.card, BM._ENGINE.proc = "ready", uuid, _FakeColibri()
    CP.claim_card(uuid, "big_model")
    return BM


def t_big_model_holds_the_card():
    # AP-1: the lane used to start on the card colibri was using. Only the
    # reverse (colibri refusing while the lane runs) was guarded.
    import jarvis_big_model as BM
    kill = BM._kill_tree
    BM._kill_tree = lambda p: None
    try:
        with G.World(G.SMI["2080s_2060"]) as w:
            w.switches(master=True, long_context=True)
            _colibri_on(G.U_2060)
            st = SC.status()
            check("colibri on the second card: the lane is not started on it",
                  not w.started and st["lane"]["state"] == "off", st["lane"])
            check("and says why, in words",
                  st["lane"]["why"] == ("the big model is using the NVIDIA GeForce RTX 2060; "
                                        "it stops after 10 idle minutes"), st["lane"]["why"])
            check("engine_card() names the card, and reads only",
                  BM.engine_card() == {"uuid": G.U_2060, "state": "ready", "idle_minutes": 10})
            check("lane_for is None meanwhile", SC.lane_for("long_context") is None
                  and not w.started)
            code, out = SC.request_change("vision", True, gate=lambda *a: Verdict(True))
            check("ON while colibri holds it: 409 with the same sentence, no card",
                  code == 409 and out["error"] == ("Not now: the big model is using the NVIDIA "
                                                   "GeForce RTX 2060; it stops after 10 idle "
                                                   "minutes."), (code, out))
            BM._reset_for_tests()          # colibri stopped: the claim goes with it
            check("colibri stopped: its claim is given back", CP.card_holder(G.U_2060) is None)
            st = SC.status()
            check("and the lane starts on the next look",
                  len(w.started) == 1 and st["lane"]["state"] == "running", st["lane"])
            check("the lane holds the card's claim while it runs",
                  CP.card_holder(G.U_2060) == "second_card")
            SC.request_change("long_context", False)
            check("the lane stopped: its claim is given back", CP.card_holder(G.U_2060) is None)
        # The race: colibri has taken the claim and is starting, but its state
        # is not yet readable. The claim alone keeps the lane off the card.
        with G.World(G.SMI["2080s_2060"]) as w:
            w.switches(master=True, long_context=True)
            BM._reset_for_tests()
            CP.claim_card(G.U_2060, "big_model")
            try:
                st = SC.status()
                check("the claim alone (colibri mid-start): the lane does not start",
                      not w.started and st["lane"]["state"] == "off"
                      and "big model" in st["lane"]["why"], st["lane"])
            finally:
                CP.release_card(G.U_2060, "big_model")
        with G.World(G.SMI["2080s_2060"]) as w:
            w.switches(master=True)
            seen = []
            with mock.patch.object(BM, "_cuda_setting", lambda: "on"):
                SC.request_change("long_context", True,
                                  gate=lambda a, d, p: seen.append(p) or Verdict(True))
            check("with [big_model] cuda = \"on\", the card says they never share it",
                  seen and "They never share it" in seen[0], seen)
    finally:
        BM._kill_tree = kill
        BM._reset_for_tests()


def t_browser_control_card_is_honest():
    # AP-9: the Browser control card said "Nothing leaves this PC", but the
    # feature drives web pages. It now has its own action and true words.
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, long_context=True)
        seen = []
        gate = lambda a, d, p: seen.append((a, d, p)) or Verdict(True, "ask", "approved")
        code, out = SC.request_change("browser_control", True, gate=gate)
        check("Browser control's card is raised under its own action",
              code == 200 and seen and seen[0][0] == "second_card_browser_enable", seen[:1])
        a, d, text = seen[0]
        check("its card does not say 'Nothing leaves this PC', and says the pages are online",
              "Nothing leaves this PC" not in text and "reaches that website" in text
              and d["leaves_this_pc"] is True, text)
        check("and it is on", SC._read_switches()["features"]["browser_control"] is True)
        row = next(r for r in SC.status()["features"] if r["id"] == "browser_control")
        check("its 'what' says the pages are on the internet", "on the internet" in row["what"])
        seen.clear()
        SC.request_change("vision", True, gate=gate)
        check("the other switches keep second_card_enable and 'Nothing leaves this PC'",
              seen[0][0] == "second_card_enable" and "Nothing leaves this PC" in seen[0][2]
              and seen[0][1]["leaves_this_pc"] is False)
        SC.request_change("browser_control", False)
        tiers = {"second_card_enable": "ask", "second_card_browser_enable": "notify"}
        code, out = SC.request_change("browser_control", True, gate=gate,
                                      tier_of=lambda act: tiers[act])
        check("its own tier is the one checked: not 'ask' -> 503 naming that action",
              code == 503 and "second_card_browser_enable is tier 'notify'" in out["error"], out)
        # The master card, with Browser control left on, says so too.
        seen.clear()
        w.switches(master=False, long_context=True, browser_control=True)
        SC.request_change("master", True, gate=gate)
        check("the master card with Browser control left on does not say nothing leaves",
              "Nothing leaves this PC" not in seen[0][2] and "reaches that website" in seen[0][2]
              and seen[0][0] == "second_card_enable")


def t_combined_mode():
    # The third mode (2026-09-26): "One bigger model on both cards" - off by
    # default, ties up both cards, mutually exclusive with the five features.
    with G.World(G.SMI["2080s_2060"]) as w:
        seen = []
        gate = lambda a, d, p: seen.append((a, d, p)) or Verdict(True, "ask", "approved")
        code, out = SC.request_change("combined", True, gate=gate)
        check("combined ON: one card, action second_card_combined_enable",
              code == 200 and out["pending"] is True and len(seen) == 1
              and seen[0][0] == "second_card_combined_enable", (code, out, seen))
        a, d, text = seen[0]
        check("the card names both cards, the model, and warns about pace and being unmeasured",
              "RTX 2080 SUPER" in text and "RTX 2060" in text and "qwen3:14b" in text
              and "bigger, slower card" in text and "not measured yet" in text
              and d["leaves_this_pc"] is False, text)
        check("combined is on", SC._read_switches()["combined"] is True)
        st = SC.status()
        check("status shows it active and working",
              st["combined"]["active"] is True and st["combined"]["why"].startswith("Working"),
              st["combined"])
        check("the classic per-card lane is untouched", st["lane"]["state"] == "off")
        # Mutual exclusion, both directions.
        code, out = SC.request_change("long_context", True, gate=gate)
        check("a feature while combined is on: refused (409), combined off first",
              code == 409 and "Turn that off first" in out["error"], out)
        code, out = SC.request_change("master", True, gate=gate)
        check("master while combined is on: refused too, same reason",
              code == 409 and "Turn that off first" in out["error"], out)
        SC.request_change("combined", False)
        check("combined OFF is at once, and the combined Ollama stops",
              SC._read_switches()["combined"] is False and w.killed)
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, long_context=True)
        code, out = SC.request_change("combined", True, gate=lambda *a: Verdict(True))
        check("combined while a feature is genuinely on: refused (409), no card",
              code == 409 and "both cards to itself" in out["error"], out)
    with G.World(G.SMI["one_card"]) as w:
        code, out = SC.request_change("combined", True, gate=lambda *a: None)
        check("combined with only one card: 503, says why",
              code == 503 and "needs two graphics cards" in out["error"], out)
    with G.World(G.SMI["2080s_2060"]) as w:
        code, out = SC.request_change("combined", True, gate=gate, spawn=lambda fn: None)
        code2, out2 = SC.request_change("combined", True, gate=gate, spawn=lambda fn: None)
        check("a second ON while its card waits: 409",
              code2 == 409 and "already waiting" in out2["error"])


def t_a_feature_card_approved_after_combined_turns_on_is_refused():
    # Bug audit 2026-09-27, finding #5: _decide (a feature's own approval,
    # not combined's) re-checked the main switch and this feature's own
    # "needs" list against state as it is NOW, not as it was when the card
    # went up - but never re-checked "combined". Approving "combined"
    # while a feature's card was still waiting used to leave BOTH switches
    # on, and _wanted/_combined_wanted then refuse each other in
    # _reconcile/_reconcile_combined, running neither - exactly the state
    # the 409 "Turn that off first" refusal exists to prevent.
    with G.World(G.SMI["2080s_2060"]):
        approve = lambda a, d, p: Verdict(True, "ask", "approved")
        SC.request_change("master", True, gate=approve)
        captured = []
        code, out = SC.request_change("long_context", True, gate=approve,
                                      spawn=captured.append)
        check("long_context's own card is raised and left waiting",
              code == 200 and out["pending"] is True and len(captured) == 1, out)
        code2, out2 = SC.request_change("combined", True, gate=approve)
        check("meanwhile, combined is asked for and approved for real",
              code2 == 200 and SC._read_switches()["combined"] is True, out2)
        captured[0]()   # long_context's own decision work, run now, on purpose
        check("long_context's card, decided AFTER combined came on, is refused",
              SC._read_switches()["features"].get("long_context") is not True,
              SC._read_switches())
        sw = SC._read_switches()
        check("never both on at once", not (sw["combined"] and sw["features"].get("long_context")),
              sw)


def t_combined_capable_arithmetic():
    A = {"role": "primary", "name": "Card A", "uuid": "GPU-aaaa0000-0000-0000-0000-000000000000",
         "total_mb": 8192, "compute_cap": 7.5}
    B = {"role": "second", "name": "Card B", "uuid": "GPU-bbbb0000-0000-0000-0000-000000000000",
         "total_mb": 10240, "compute_cap": 7.5}
    check("8 + 10 = 18 GiB: exactly the floor, capable",
          SC._combined_capable({"cards": [A, B]}) == (True, ""))
    ok, why = SC._combined_capable({"cards": [A, dict(B, total_mb=10176)]})
    check("one MiB under the floor: not capable, says why",
          ok is False and "not the 18 GB" in why, why)
    ok, why = SC._combined_capable({"cards": [dict(A, compute_cap=6.1), B]})
    check("the everyday card older than Turing: not capable, names it",
          ok is False and "the everyday card" in why and "older than Turing" in why, why)
    ok, why = SC._combined_capable({"cards": [A, dict(B, compute_cap=6.1)]})
    check("the second card older than Turing: not capable, names it",
          ok is False and "the second card" in why, why)
    check("only a primary row, no second: not capable, plain reason",
          SC._combined_capable({"cards": [A]}) == (False, "needs two graphics cards; only one "
                                                     "is here"))
    check("no card ids at all: the same plain reason",
          SC._combined_capable({"cards": []}) == (False, "needs two graphics cards; only one "
                                                    "is here"))


def t_combined_lane_env_and_lane_for():
    env = SC.lane_env((G.U_2080S, G.U_2060), port=11435, num_ctx=32768, base={}, spread=True)
    check("lane_env joins multiple ids and sets OLLAMA_SCHED_SPREAD=1 when asked",
          env["CUDA_VISIBLE_DEVICES"] == f"{G.U_2080S},{G.U_2060}"
          and env["OLLAMA_SCHED_SPREAD"] == "1", env)
    env2 = SC.lane_env((G.U_2080S, G.U_2060), port=11435, num_ctx=32768, base={})
    check("without spread, OLLAMA_SCHED_SPREAD is not set", "OLLAMA_SCHED_SPREAD" not in env2)
    check("a single id still works exactly as before (str, not a tuple)",
          SC.lane_env(G.U_2060, port=11435, num_ctx=1, base={})["CUDA_VISIBLE_DEVICES"]
          == G.U_2060)
    for bad in ((G.U_2080S, "not-an-id"), ()):
        try:
            SC.lane_env(bad, port=11435, num_ctx=1, base={})
            check(f"lane_env refuses {bad!r}", False)
        except ValueError:
            check(f"lane_env refuses {bad!r}", True)
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(combined=True)
        lane = SC.combined_lane()
        check("combined_lane(): the loopback lane, the model, 32K",
              lane is not None and lane.url == "http://127.0.0.1:11435"
              and lane.model == "qwen3:14b" and lane.num_ctx == 32768, repr(lane))
        check("the combined Ollama sees both cards, by id, comma-joined",
              w.started and w.started[0].kwargs["env"]["CUDA_VISIBLE_DEVICES"]
              == f"{G.U_2080S},{G.U_2060}", w.started[0].kwargs["env"] if w.started else None)
    with G.World(G.SMI["2080s_2060"]) as w:
        check("combined off (the default): combined_lane() is None", SC.combined_lane() is None)
        check("and nothing started", not w.started)
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, long_context=True)
        check("a feature genuinely on: combined_lane() is None even if combined were on",
              SC.combined_lane() is None)
    with G.World(G.SMI["one_card"]) as w:
        w.switches(combined=True)
        check("only one card: combined_lane() is None, never raises", SC.combined_lane() is None)


def t_last_card():
    # AP-6: _LAST was written and never read. status()["last"] says how the
    # most recent card ended, so the apps can say what really happened.
    with G.World(G.SMI["2080s_2060"]) as w:
        check("no card has ended yet: last is null", SC.status()["last"] is None)
        SC.request_change("master", True, gate=lambda *a: Verdict(True, "ask", "approved"))
        last = SC.status()["last"]
        check("approved: enabled, with the switch and a sentence",
              set(last) == {"feature", "outcome", "why", "at"} and last["feature"] == "master"
              and last["outcome"] == "enabled" and last["why"] == "The second graphics card "
              "was turned on." and isinstance(last["at"], int), last)
        for v, want, words in ((Verdict(False, "ask", "denied"), "denied", "You said no"),
                               (Verdict(False, "ask", "timed_out"), "timed_out",
                                "Nobody answered the card in time"),
                               (Verdict(True, "auto", "auto"), "refused", "not a person saying yes")):
            SC.request_change("vision", True, gate=lambda *a, v=v: v)
            last = SC.status()["last"]
            check(f"{want}: said as {want}, in words",
                  last["feature"] == "vision" and last["outcome"] == want and words in last["why"],
                  last)
        held = []
        SC.request_change("vision", True, gate=lambda *a: Verdict(True, "ask", "approved"),
                          spawn=held.append)
        SC.request_change("vision", False)
        held[0]()
        last = SC.status()["last"]
        check("withdrawn: said as withdrawn", last["outcome"] == "withdrawn"
              and "while its card was waiting" in last["why"], last)


def t_standby_frees_the_second_card():
    # Standby promised to free "the graphics card" and freed only the main
    # one. And a stopped lane has to STAY stopped: both apps poll
    # GET /api/second-card, which reconciles - without the asleep flag the
    # next poll started it again.
    import jarvis_power as PW
    try:
        with G.World(G.SMI["2080s_2060"]) as w:
            w.switches(master=True, long_context=True, learning=True)
            SC.status()
            p = w.started[0]
            PW.set_mode("standby", why="test")
            out = SC.sleep()
            check("sleep: the second Ollama is stopped, and it says so",
                  out["stopped"] and w.killed == [p] and SC._LANE.state == "off"
                  and "second graphics card" in out["sentence"], (out, SC._LANE.state))
            for _ in range(3):
                st = SC.status()
            check("the apps' polling does not start it again while asleep",
                  len(w.started) == 1 and st["lane"]["state"] == "off"
                  and "asleep" in st["lane"]["why"], st["lane"])
            check("background learning does not wake it",
                  SC.lane_for("learning") is None and len(w.started) == 1)
            SC.lane_for("long_context")
            check("the owner using a feature wakes it, on demand",
                  len(w.started) == 2 and not SC.asleep())
        with G.World(G.SMI["2080s_2060"]) as w:
            w.switches(master=True, long_context=True)
            PW.set_mode("standby", why="test")
            out = SC.sleep()
            check("nothing running: stopped is False, and nothing is said",
                  out == {"stopped": False, "sentence": ""}, out)
            SC.status()
            check("still asleep while Jarvis is on standby", not w.started)
            PW.set_mode("active", why="test")
            SC.status()
            check("Jarvis leaving standby wakes it by itself",
                  len(w.started) == 1 and not SC.asleep())
        with G.World(G.SMI["2080s_2060"]) as w:
            w.switches(master=True, long_context=True)
            PW.set_mode("active", why="test")
            SC.sleep()
            SC.status()
            check("sleep() while Jarvis is not on standby does not stick",
                  len(w.started) == 1 and not SC.asleep())
    finally:
        PW.set_mode("active", why="test")
        SC.wake()


def t_lane_for_is_none_when_not_ready():
    def ready(**kw):
        return G.World(G.SMI["2080s_2060"], **kw)
    with ready() as w:
        check("everything off (the default): None", SC.lane_for("long_context") is None)
        check("and nothing started, nothing asked", not w.started and not w.http)
    with ready() as w:
        w.switches(master=False, long_context=True)
        check("feature on, main switch off: None", SC.lane_for("long_context") is None)
    with ready() as w:
        w.switches(master=True)
        check("main switch on, feature off: None", SC.lane_for("long_context") is None)
    with ready() as w:
        w.switches(master=True, browser_control=True)
        check("browser_control without long_context: None", SC.lane_for("browser_control") is None)
    with G.World(G.SMI["one_card"]) as w:
        w.switches(master=True, long_context=True)
        check("no capable card: None", SC.lane_for("long_context") is None and not w.started)
    with ready(spawn_now=False) as w:
        w.switches(master=True, long_context=True)
        check("still starting: None", SC.lane_for("long_context") is None
              and SC._LANE.state == "starting")
    with ready(lane_answers=False) as w:
        w.switches(master=True, long_context=True)
        check("never answered: None, and failed", SC.lane_for("long_context") is None
              and SC._LANE.state == "failed")
    with ready(installed=("qwen3:14b",)) as w:
        w.switches(master=True, long_context=True)
        check("model not installed: None", SC.lane_for("long_context") is None)
        st = SC.status()
        check("and status says how to install it",
              st["features"][0]["model_installed"] is False
              and "ollama pull qwen3:8b" in st["features"][0]["why"])
    with ready(tags_answer=False) as w:
        w.switches(master=True, long_context=True)
        check("cannot ask whether it is installed: None", SC.lane_for("long_context") is None)
    with ready() as w:
        w.switches(master=True, long_context=True)
        check("an unknown feature: None", SC.lane_for("everything") is None)
        with mock.patch.object(SC, "detect", side_effect=RuntimeError("boom")):
            check("never raises", SC.lane_for("long_context") is None)


def t_status_shape_and_no_secrets():
    with G.World(G.SMI["2080s_2060"], windows=True) as w:
        os.environ["HUD_TOKEN_TEST_PROBE"] = "s3cr3t-token-value"
        try:
            st = SC.status()
        finally:
            os.environ.pop("HUD_TOKEN_TEST_PROBE", None)
    check("status() has exactly the contract's keys",
          set(st) == {"detected", "enabled", "active", "pending", "lane", "main_ollama_pinned",
                      "pin_note", "pin_command", "features", "last", "picture_text",
                      "combined", "third", "suggest"}, sorted(st))
    check("suggest has exactly its keys, both signals on by default",
          set(st["suggest"]) == {"available", "title", "detail", "signals"}
          and all(s["enabled"] is True for s in st["suggest"]["signals"])
          and {s["id"] for s in st["suggest"]["signals"]} == {"struggle", "correction"},
          st["suggest"])
    check("combined has exactly its keys",
          set(st["combined"]) == {"id", "name", "what", "enabled", "capable", "capable_why",
                                  "conflict", "active", "available", "model", "context",
                                  "memory_gib", "why"}, sorted(st["combined"]))
    check("detected has exactly its keys",
          set(st["detected"]) == {"capable", "why", "primary", "second", "cards"})
    check("each feature row has exactly its keys",
          all(set(f) == {"id", "name", "what", "enabled", "active", "available", "needs", "model",
                         "model_installed", "memory_gib", "why", "model_free"} for f in st["features"]))
    check("model_free is true for referee (loads no model) and false for every other row",
          all(f["model_free"] is (f["id"] == "referee") for f in st["features"]),
          [(f["id"], f["model_free"]) for f in st["features"]])
    check("the seven feature ids, in order (study and referee since 2026-09-30)",
          [f["id"] for f in st["features"]] == ["long_context", "vision", "learning",
                                                 "browser_control", "wiki", "study", "referee"])
    text = json.dumps(st)
    check("no token or key in it", "s3cr3t" not in text and "token" not in text.lower())
    check("pin_command is ONE line, 5.1-safe (no ?? and no newline)",
          "\n" not in st["pin_command"] and "??" not in st["pin_command"]
          and G.U_2080S in st["pin_command"] and "'User'" in st["pin_command"])
    check("pin_command also switches the everyday Ollama's Vulkan route off",
          "[Environment]::SetEnvironmentVariable('OLLAMA_VULKAN', '0', 'User');"
          in st["pin_command"], st["pin_command"])
    check("a card id that is not one gets no command", SC.pin_command("GPU-1'; Remove-Item x") is None)


def t_main_ollama_pin():
    apps = f"4242, ollama_llama_server.exe, {G.U_2060}, 5200\n"
    with G.World(G.SMI["2080s_2060"], windows=True, apps=apps, user_env=G.U_2080S):
        st = SC.status()
    check("the everyday Ollama seen on the second card: false, says so",
          st["main_ollama_pinned"] is False and "using the NVIDIA GeForce RTX 2060" in st["pin_note"])
    with G.World(G.SMI["2080s_2060"], windows=True, user_env=G.U_2080S):
        st = SC.status()
    check("pinned to the main card in the user settings: true", st["main_ollama_pinned"] is True)
    with G.World(G.SMI["2080s_2060"], windows=True,
                 user_env={"CUDA_VISIBLE_DEVICES": G.U_2080S}):
        st = SC.status()
    check("pinned by the OLDER one-setting command (Vulkan still on): false, and says why",
          st["main_ollama_pinned"] is False and "Vulkan" in st["pin_note"], st["pin_note"])
    with G.World(G.SMI["2080s_2060"], windows=True,
                 user_env={"CUDA_VISIBLE_DEVICES": G.U_2080S, "OLLAMA_VULKAN": "1"}):
        st = SC.status()
    check("Vulkan switched ON by hand: false", st["main_ollama_pinned"] is False)
    with G.World(G.SMI["2080s_2060"], windows=True,
                 user_env={"CUDA_VISIBLE_DEVICES": G.U_2080S, "OLLAMA_VULKAN": "0"}):
        st = SC.status()
    check("both settings: true", st["main_ollama_pinned"] is True, st["pin_note"])
    with G.World(G.SMI["2080s_2060"], windows=True, user_env=G.U_2060):
        st = SC.status()
    check("pinned to the wrong card: false", st["main_ollama_pinned"] is False)
    with G.World(G.SMI["2080s_2060"], windows=True, user_env=None):
        st = SC.status()
    check("not pinned on Windows: false", st["main_ollama_pinned"] is False)
    with G.World(G.SMI["2080s_2060"], windows=False, user_env=None):
        st = SC.status()
    check("cannot tell: null, with a sentence",
          st["main_ollama_pinned"] is None and st["pin_note"])
    # Our own runner on the second card is not the everyday Ollama.
    with G.World(G.SMI["2080s_2060"], windows=True, user_env=G.U_2080S) as w:
        w.switches(master=True, long_context=True)
        SC.status()
        w.apps = f"{w.started[0].pid}, ollama.exe, {G.U_2060}, 9000\n"
        with mock.patch.object(SC, "_tree", lambda pid: {pid}):
            st = SC.status()
    check("our own second Ollama on the second card does not count against the pin",
          st["main_ollama_pinned"] is True, st["pin_note"])
    # Bug audit 2026-09-27, backend finding #7: the combined lane's own
    # Ollama runs on the second card BY DESIGN, and used to be mistaken for
    # the everyday one crowding it.
    with G.World(G.SMI["2080s_2060"], windows=True, user_env=G.U_2080S) as w:
        w.switches(combined=True)
        SC.combined_lane()
        w.apps = f"{w.started[0].pid}, ollama.exe, {G.U_2060}, 9000\n"
        with mock.patch.object(SC, "_tree", lambda pid: {pid}):
            st = SC.status()
    check("the combined lane's own Ollama on the second card does not count "
          "against the pin either",
          st["main_ollama_pinned"] is True, st["pin_note"])


# ------------------------------------------------------------- the hooks --

def _turn(messages, *, lane_for=None, combined_lane_for=None, enabled=None,
          context_length=2048, lane_choice="auto"):
    sent = []

    def opener(url, body):
        sent.append((url, body))
        return W.FakeResponse(W.stream([("content", "ok"), ("done", "stop")]))
    patches = [mock.patch.object(AG, "_second_card_lane", lane_for or (lambda f: None)),
              mock.patch.object(AG, "_combined_second_card_lane", combined_lane_for or (lambda: None))]
    with patches[0], patches[1]:
        AG.run_local_turn(messages, "qwen3:8b", ollama_url="http://127.0.0.1:11434",
                          stream_out=lambda b: None, open_stream=opener,
                          enabled_tools=enabled, context_length=context_length,
                          on_step=lambda s: None, record_chain=lambda s: None,
                          keepalive_seconds=60, status_delay=60, lane_choice=lane_choice)
    return sent


def _long_history(n=20):
    msgs = [{"role": "system", "content": "persona"}]
    for i in range(n):
        msgs.append({"role": "user", "content": f"question {i} " + "word " * 120})
        msgs.append({"role": "assistant", "content": f"answer {i} " + "word " * 120})
    msgs.append({"role": "user", "content": "and now?"})
    return msgs


LANE14 = SC.Lane("http://127.0.0.1:11435", "qwen3:14b", 16384, "test")
LANEVL = SC.Lane("http://127.0.0.1:11435", "qwen2.5vl:7b", 16384, "test")


def t_hooks_are_no_ops_when_off():
    msgs = _long_history()
    base = _turn(msgs, lane_choice=None)
    off = _turn(msgs)
    check("long history, second card off: the same request as before, to the same place",
          off == base and off[0][0] == "http://127.0.0.1:11434/v1/chat/completions"
          and off[0][1]["model"] == "qwen3:8b")
    check("and it was trimmed, as before", len(off[0][1]["messages"]) < len(msgs))
    calls = []
    with mock.patch.object(AG, "_context_length", lambda *a: calls.append(a) or 4096):
        AG.choose_lane(msgs, "qwen3:8b", ollama_url="http://127.0.0.1:11434",
                       lane_for=lambda f: None)
    check("with it off, Ollama is not even asked for the context length", calls == [])
    pic = [{"role": "user", "content": [{"type": "text", "text": "what is this?"},
                                         {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]}]
    # Since the owner's "Yes, clean them too" (2026-09-29) every attached picture is checked for
    # secrets first, so this PC's text reader must be able to read it: a stand-in that finds no
    # words at all (nothing to hide) lets the picture go on exactly as it came.
    nothing_to_hide = {"ok": True, "text": "", "left_out": 0, "why": "", "lines": [], "size": None}
    with mock.patch.object(AG, "_read_picture", lambda image: dict(nothing_to_hide)):
        sent = _turn(pic, enabled={"calculator"})
    check("a picture, second card off: the main model gets it exactly as before, tools and all",
          sent[0][0].startswith("http://127.0.0.1:11434") and sent[0][1]["model"] == "qwen3:8b"
          and sent[0][1]["messages"] == pic and "tools" in sent[0][1])
    with mock.patch.object(AG, "_read_picture", lambda image: {"ok": False, "why": "no reader here"}):
        sent = _turn(pic, enabled={"calculator"})
    check("... but a picture that cannot be checked for secrets is not sent to the model at all",
          not any(AG._image_part(p) for m in sent[0][1]["messages"] if isinstance(m["content"], list)
                  for p in m["content"]))
    import jarvis_router as R
    d = R.choose("look", local_model="qwen3:8b", lanes=["jarvis-escalate"], has_image=True)
    check("the router still keeps a picture local (unchanged)", d.lane == "qwen3:8b" and d.gate == "image")
    check("browser_control listed but no second-card lane: not offered",
          AG.offered_tools({"browser_control", "calculator"}) == ["calculator"])
    with mock.patch.object(AG, "_second_card_lane", lambda f: LANE14 if f == "browser_control" else None):
        check("with the lane working: offered",
              "browser_control" in AG.offered_tools({"browser_control", "calculator"}))
    check("offered_tools(None) (every tool, for tests) is unchanged",
          AG.offered_tools(None) == list(AG.TOOLS))
    asked = []
    llm = lambda prompt: asked.append(prompt) or '{"facts": []}'
    with mock.patch.object(SC, "lane_for", lambda f: None):
        wrapped = SC.learning_llm(llm)
    check("learner, second card off: the same model call, untouched", wrapped is llm)
    with mock.patch.object(SC, "lane_for", lambda f: None):
        check("and the quiet wait is unchanged", SC.learning_idle_seconds(45.0) == 45.0)


def t_long_context_needs_more_room():
    # T3: a long turn moved to the second card although its lane had the
    # SAME room as the main model (16,384 each), and was trimmed there just
    # the same. The audit's shape, at the real 16,384.
    msgs = [{"role": "system", "content": "recalled facts"}]
    for i in range(10):
        msgs.append({"role": "user", "content": f"q{i} " + "word " * 1100})
        msgs.append({"role": "assistant", "content": f"a{i} " + "word " * 1100})
    msgs.append({"role": "user", "content": "and now?"})
    same = SC.Lane("http://127.0.0.1:11435", "qwen3:14b", 16384, "test")
    bigger = SC.Lane("http://127.0.0.1:11435", "qwen3:8b", 32768, "test")
    lc = AG.choose_lane(msgs, "jarvis-primary", ollama_url="x", context_length=16384,
                        lane_for=lambda f: same if f == "long_context" else None)
    check("lane with the same 16,384 as the main model: the turn stays on the main card",
          lc is None, repr(lc))
    lc = AG.choose_lane(msgs, "jarvis-primary", ollama_url="x", context_length=16384,
                        lane_for=lambda f: bigger if f == "long_context" else None)
    check("lane with 32,768 against the main model's 16,384: the turn moves",
          lc is not None and lc.feature == "long_context" and lc.context_length == 32768, repr(lc))
    sent = _turn(msgs, context_length=16384,
                 lane_for=lambda f: same if f == "long_context" else None)
    check("... and the request really goes to the main card",
          sent[0][0] == "http://127.0.0.1:11434/v1/chat/completions")
    with G.World(G.SMI["2080s_2060"]):
        det = SC.detect(fresh=True)
    check("the 12 GB card's planned lane has more room than jarvis-primary's 16,384",
          SC._feature_model("long_context", det)[1] > 16384)


def t_learning_on_a_lane_that_does_not_answer():
    # K13: the pause was cut to 10 s because the lane existed, and when the
    # lane then failed (here a stand-in second Ollama answering 404) the
    # pass fell back to the MAIN card after only those 10 s.
    import urllib.error
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, learning=True)
        real = w.http_json

        def http(url, payload=None, timeout=2.0):
            if url.endswith("/api/generate"):
                w.http.append((url, payload))
                raise urllib.error.HTTPError(url, 404, "model not found", None, None)
            return real(url, payload, timeout)
        SC._http_json = http
        main = []
        llm = lambda p: main.append(p) or "from the main card"
        check("the lane is there: the pause is shortened to 10 s",
              SC.learning_idle_seconds(45.0) == 10.0)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            out = SC.learning_llm(llm)("remember this")
        check("the lane answers 404 after that short pause: the pass is skipped, the main "
              "card is NOT asked", out is None and main == [], (out, main))
        check("... and it says so", "this pass was skipped" in err.getvalue())
        check("the next pass waits the full time", SC.learning_idle_seconds(45.0) == 45.0)
        check("... and then uses the main card, exactly as before the second card",
              SC.learning_llm(llm) is llm)
        SC._LEARN["failed_at"] -= SC.LEARN_RETRY_SECONDS + 1
        check("after LEARN_RETRY_SECONDS the second card is tried again",
              SC.learning_idle_seconds(45.0) == 10.0)
        SC._LEARN["short"] = False
        main.clear()
        out = SC.learning_llm(llm)("x")
        check("a pass that had the full wait may still fall back to the main card",
              out == "from the main card" and main == ["x"], (out, main))


def t_hooks_when_on():
    msgs = _long_history()
    sent = _turn(msgs, lane_for=lambda f: LANE14 if f == "long_context" else None)
    check("long history, long_context working: sent to the second card, whole",
          sent[0][0] == "http://127.0.0.1:11435/v1/chat/completions"
          and sent[0][1]["model"] == "qwen3:14b"
          and sent[0][1]["messages"] == [{"role": "system", "content": AG.LANE_SYSTEM}] + msgs)
    short = [{"role": "user", "content": "hi"}]
    sent = _turn(short, lane_for=lambda f: LANE14 if f == "long_context" else None)
    check("a short conversation stays on the main card", sent[0][0].startswith("http://127.0.0.1:11434"))
    pic = [{"role": "user", "content": [{"type": "text", "text": "what is this?"},
                                         {"type": "image_url", "image_url": {"url": "data:,"}}]}]
    sent = _turn(pic, enabled={"calculator"}, lane_for=lambda f: LANEVL if f == "vision" else None)
    check("a picture, vision working: the picture model on the second card, no tools",
          sent[0][0].startswith("http://127.0.0.1:11435") and sent[0][1]["model"] == "qwen2.5vl:7b"
          and "tools" not in sent[0][1])
    lc = AG.choose_lane(pic, "qwen3:8b", ollama_url="http://x", lane_for=lambda f: LANEVL)
    check("choose_lane says which feature moved it", lc is not None and lc.feature == "vision")
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, learning=True)
        asked = []
        llm = lambda prompt: asked.append(prompt) or "from the main card"
        out = SC.learning_llm(llm)("remember this")
        gen = [u for (u, p) in w.http if u.endswith("/api/generate")]
        check("learner, learning working: asked on 127.0.0.1:11435, not the main card",
              gen == ["http://127.0.0.1:11435/api/generate"] and not asked
              and out == '{"facts": []}', (gen, asked, out))
        body = [p for (u, p) in w.http if u.endswith("/api/generate")][0]
        check("with the lane's context size, so the model is never reloaded",
              body["options"]["num_ctx"] == 32768 and body["model"] == "qwen3:8b")
        check("and the learner's quiet wait shortens to 10 s", SC.learning_idle_seconds(45.0) == 10.0)
    # jarvis_intake.propose() goes through it.
    seen = []

    class Extract:
        def propose(self, messages, llm=None, source="conversation"):
            seen.append(llm("prompt text"))
            return []
    with mock.patch.object(SC, "lane_for", lambda f: None):
        IN.propose(Extract(), [{"role": "user", "content": "x"}], lambda p: "main", store=_NoStore())
    check("jarvis_intake.propose, off: the main model answers", seen == ["main"])


def t_combined_is_the_fallback_when_vision_and_long_context_say_no():
    # Bug audit 2026-09-27, finding #3: combined_lane() had no caller at
    # all, so saying yes to "One bigger model on both cards" changed no
    # answer. choose_lane() now asks it once vision and long_context have
    # both said no - never instead of either, and never for a picture turn
    # whose own vision lane is unavailable (the combined model cannot see).
    combined = SC.Lane("http://127.0.0.1:11436", "qwen3:14b", 32768, "combined test")
    short = [{"role": "user", "content": "hi"}]
    lc = AG.choose_lane(short, "qwen3:8b", ollama_url="http://x",
                        lane_for=lambda f: None, combined_lane_for=lambda: combined)
    check("an ordinary short turn, nothing else available: goes to combined",
          lc is not None and lc.feature == "combined" and lc.model == "qwen3:14b", repr(lc))
    sent = _turn(short, combined_lane_for=lambda: combined)
    check("... and the real request really goes there",
          sent[0][0] == "http://127.0.0.1:11436/v1/chat/completions"
          and sent[0][1]["model"] == "qwen3:14b")
    pic = [{"role": "user", "content": [{"type": "text", "text": "what is this?"},
                                         {"type": "image_url", "image_url": {"url": "data:,"}}]}]
    lc = AG.choose_lane(pic, "qwen3:8b", ollama_url="http://x",
                        lane_for=lambda f: None, combined_lane_for=lambda: combined)
    check("a picture, no vision lane: stays home - never falls through to combined",
          lc is None, repr(lc))
    msgs = _long_history()
    same = SC.Lane("http://127.0.0.1:11435", "qwen3:14b", 16384, "test")
    lc = AG.choose_lane(msgs, "jarvis-primary", ollama_url="x", context_length=16384,
                        lane_for=lambda f: same if f == "long_context" else None,
                        combined_lane_for=lambda: combined)
    check("long_context available but no bigger than the main model: falls through to combined",
          lc is not None and lc.feature == "combined", repr(lc))
    lc = AG.choose_lane(short, "qwen3:8b", ollama_url="http://x",
                        lane_for=lambda f: None, combined_lane_for=lambda: None)
    check("combined off too: the turn really stays on the main card", lc is None, repr(lc))


class _NoStore:
    semantic = False

    def search(self, *a, **k):
        return []

    def nearest(self, *a, **k):
        return []


# --------------------------------------------------------- jarvis_compute --

def t_compute_ranking():
    devs = CP.parse_smi(G.SMI["2060_first"])
    with mock.patch.object(CP, "devices", return_value=devs), \
            mock.patch.object(CP, "_cfg", lambda k, d=None: d):
        p = CP.plan("qwen3:8b")
    check("everyday chat on the 2080 Super, not the 2060 with more free memory",
          p.text_on == "cuda:1" and p.devices[0]["name"] == "NVIDIA GeForce RTX 2080 SUPER", p.why)
    check("and it says why", "monitor" in p.why)
    check("voice is not claimed to be on a card", p.tts_resident is False)
    fake = [CP.Device(0, "NVIDIA GeForce RTX 2080 SUPER", 8192, 1944),
            CP.Device(1, "NVIDIA GeForce RTX 2060", 12288, 11000)]
    with mock.patch.object(CP, "devices", return_value=fake), \
            mock.patch.object(CP, "_cfg", lambda k, d=None: d):
        p = CP.plan("qwen3:8b")
    check("the old way ranked by free memory (the 2060); the rule picks index 0 here",
          p.text_on == "cuda:0")
    d = p.as_dict()
    check("plan()'s fields are all still there",
          {"text_model", "text_on", "vision_resident", "tts_resident", "simulated", "prefer",
           "devices", "why", "total_mb"} <= set(d) and d["total_mb"] == 20480)


# ------------------------------------------------------------- the patch --

def _stand_in():
    import _skeleton
    import test_task_control as TT
    git = shutil.which("git")

    def apply(text, names):
        d = Path(tempfile.mkdtemp(prefix="jarvis-sc-"))
        try:
            with open(d / "jarvis_hud.py", "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            for n in names:
                lf = d / n
                lf.write_bytes((HERE / n).read_bytes().replace(b"\r\n", b"\n"))
                r = subprocess.run([git, "apply", "--include=jarvis_hud.py", str(lf)], cwd=d,
                                   capture_output=True, text=True)
                if r.returncode != 0:
                    raise AssertionError(f"{n}: {r.stderr}")
            return (d / "jarvis_hud.py").read_text(encoding="utf-8")
        finally:
            shutil.rmtree(d, ignore_errors=True)
    # The learner and the routes (extraction-wiring, feedback, memory-intake,
    # task-control, note-capture, power-mode), then the chat turn (gpu-offload,
    # ollama-direct, tool-calling-wiring, speed-record, chat-stream) - in the
    # order they sit in jarvis_hud.py.
    a = apply(TT.stack_skeleton(), ["task-control.patch", "note-capture.patch", "power-mode.patch"])
    b = apply(_skeleton.build("gpu-offload.patch", "ollama-direct.patch",
                              "tool-calling-wiring.patch"), ["speed-record.patch", "chat-stream.patch"])
    return a + b


def t_the_patch():
    git = shutil.which("git")
    if not git:
        return check("SKIP - git is not installed", True)
    import _skeleton
    start = _stand_in()
    d = Path(tempfile.mkdtemp(prefix="jarvis-sc-"))
    try:
        with open(d / "jarvis_hud.py", "w", encoding="utf-8", newline="\n") as f:
            f.write(start)
        gate = _skeleton.build("ui-control-wiring.patch", target="jarvis_gate.py")
        (d / "jarvis_gate.py").write_text(gate, encoding="utf-8")
        nc = d / "nc.patch"
        nc.write_bytes((HERE / "note-capture.patch").read_bytes().replace(b"\r\n", b"\n"))
        r = subprocess.run([git, "apply", "--include=jarvis_gate.py", str(nc)], cwd=d,
                           capture_output=True, text=True)
        check("stand-in jarvis_gate.py: note-capture's half applied", r.returncode == 0, r.stderr)
        gate_start = (d / "jarvis_gate.py").read_text(encoding="utf-8")
        lf = d / "second-card.patch"
        lf.write_bytes((HERE / "second-card.patch").read_bytes().replace(b"\r\n", b"\n"))
        steps = [["apply", "--check", str(lf)], ["apply", str(lf)],
                 ["apply", "--check", "--reverse", str(lf)]]
        ok, err = True, ""
        for args in steps:
            r = subprocess.run([git] + args, cwd=d, capture_output=True, text=True)
            if r.returncode != 0:
                ok, err = False, f"git {' '.join(args[:-1])}: {r.stderr}"
                break
            if args == ["apply", str(lf)]:
                after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
                gate_after = (d / "jarvis_gate.py").read_text(encoding="utf-8")
        check("second-card.patch applies to what the earlier patches wrote, and reverses",
              ok, err)
        if not ok:
            return
        r = subprocess.run([git, "apply", "--reverse", str(lf)], cwd=d, capture_output=True, text=True)
        check("reversing gives back exactly the starting text",
              r.returncode == 0 and (d / "jarvis_hud.py").read_text(encoding="utf-8") == start
              and (d / "jarvis_gate.py").read_text(encoding="utf-8") == gate_start, r.stderr)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    i = after.index('if path == "/api/second-card":')
    w = after[i:i + 900]
    check("GET /api/second-card checks origin and token, and answers status()",
          "_origin_ok(self)" in w and "_token_ok(self)" in w and "jarvis_second_card.status()" in w)
    i = after.index('if route == "/api/second-card":')
    w = after[i:i + 1600]
    check("POST /api/second-card checks origin and token, and hands the body over",
          "_origin_ok(self)" in w and "_token_ok(self)" in w
          and "jarvis_second_card.handle_post(body)" in w)
    check("the POST route sits after /api/power",
          after.index('if route == "/api/power":') < after.index('if route == "/api/second-card":'))
    check("the chat turn asks choose_lane and passes it on",
          "jarvis_agent.choose_lane(" in after and '{"lane_choice": _lane2}' in after)
    check("'where' stays 'local' on a second-card turn; 'second_card' is added",
          len(re.findall(r'route_header\["where"\] = "local"\n', after)) == 1
          and 'route_header["second_card"] = _lane2.feature' in after)
    check("the learner's quiet wait asks jarvis_second_card",
          "jarvis_second_card.learning_idle_seconds(EXTRACT_IDLE)" in after
          and "self._woken.wait(_idle)" in after)
    check("the approval notice knows the action stays on this PC",
          '"second_card_enable": ("yes", "local",' in gate_after)
    check("... and that Browser control's action reaches the internet (AP-9)",
          '"second_card_browser_enable": ("yes", "outbound",' in gate_after)
    # The patched chat block still compiles as Python (the ** in the call).
    i = after.index("_turn = jarvis_agent.run_local_turn(")
    call = after[i:after.index("announce=lambda text", i)] + "announce=None)"
    try:
        compile("def f():\n    " + call.replace("\n", "\n    ") + "\n", "<patched call>", "exec")
        check("the patched run_local_turn call is valid Python", True)
    except SyntaxError as exc:
        check("the patched run_local_turn call is valid Python", False, str(exc))
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start_ = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start_:ps1.index("\n)", start_)].splitlines()
             if l.strip().startswith("'")]
    # Last until wiki.patch (2026-09-24), whose context is this patch's own
    # route blocks, so it must come after this one - test_wiki.py checks that.
    check("apply-patches.ps1 applies it, after the patches its context comes from",
          names and "second-card.patch" in names
          and all(names.index(p) < names.index("second-card.patch")
                  for p in ("chat-stream.patch", "power-mode.patch", "note-capture.patch")))
    check("apply-patches.ps1 copies jarvis_second_card.py in",
          "'jarvis_second_card.py'" in ps1[ps1.index("$SHIPPED = @("):])
    import _where
    check("_where.SHIPPED has it too", "jarvis_second_card.py" in _where.SHIPPED)


def t_the_toml():
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("the shipped toml has second_card_enable = \"ask\"",
          re.search(r'^second_card_enable\s*=\s*"ask"', toml, re.M) is not None)
    check("the shipped toml has second_card_browser_enable = \"ask\" (AP-9)",
          re.search(r'^second_card_browser_enable\s*=\s*"ask"', toml, re.M) is not None)
    check("the shipped toml has second_card_combined_enable = \"ask\"",
          re.search(r'^second_card_combined_enable\s*=\s*"ask"', toml, re.M) is not None)
    check("the shipped toml has a [second_card] section", "\n[second_card]\n" in toml)
    check("and no switch lives in it (the switches are in second-card.json)",
          not re.search(r"^\s*(master|long_context|vision|learning|browser_control|wiki|study|referee)\s*=",
                        toml[toml.index("\n[second_card]\n"):].split("\n[", 2)[1], re.M))


# ------------------------------------------- 8 GB and bigger extra cards --
#
# 2026-09-30, the owner: "make sure if the second and/or 3rd GPUs are only 8 GB
# VRAM each that they are able to be utilized fully" (and 16 / 24 GB cards may
# come). Every number is CALCULATED, not measured - no extra card is installed.

U_8A = "GPU-8a8a8a8a-1111-4111-8111-aaaaaaaaaaa1"
U_8B = "GPU-8b8b8b8b-2222-4222-8222-bbbbbbbbbbb2"
U_10 = "GPU-10101010-3333-4333-8333-ccccccccccc3"
U_12 = "GPU-12121212-4444-4444-8444-ddddddddddd4"
U_16 = "GPU-16161616-5555-4555-8555-eeeeeeeeeee5"
U_24 = "GPU-24242424-6666-4666-8666-fffffffffff6"


def smi(*cards):
    """nvidia-smi's real CSV for these (name, MiB, uuid, display) cards, the
    first being the everyday card (a monitor on it)."""
    lines = []
    for i, (name, mib, uid, *rest) in enumerate(cards):
        disp = "Enabled" if (i == 0 or (rest and rest[0])) else "Disabled"
        lines.append(f"{i}, {uid}, {name}, {mib}, {mib - 300}, 7.5, {disp}\n")
    return "".join(lines)


PRIM = ("NVIDIA GeForce RTX 2080 SUPER", 8192, G.U_2080S)


def t_small_card_floor_edges():
    def det_for(mib):
        with G.World(smi(PRIM, ("NVIDIA GeForce RTX 2060", mib, U_8A))):
            return SC.detect(fresh=True)
    check("8,192 MiB (a card sold as 8 GB) is capable", det_for(8192)["capable"] is True)
    check("8,188 MiB (a driver that reports a few MiB less) is capable",
          det_for(8188)["capable"] is True)
    check("7,680 MiB, the floor itself, is capable", det_for(7680)["capable"] is True)
    d = det_for(7679)
    check("7,679 MiB is not, in words that now say 8 GB",
          d["capable"] is False and "at least 8 GB" in d["why"], d["why"])
    d = det_for(6144)
    check("a 6 GB card (6,144 MiB) is still refused, and says why",
          d["capable"] is False and "6 GB" in d["why"] and "at least 8 GB" in d["why"], d["why"])
    check("the old wording 'at least 10 GB' is gone",
          "at least 10 GB" not in d["why"])
    with G.World(smi(PRIM, ("Old", 8192, U_8A))) as w:
        w.smi = f"0, {G.U_2080S}, NVIDIA GeForce RTX 2080 SUPER, 8192, 6000, 7.5, Enabled\n" \
                f"1, {U_8A}, GTX 1080, 8192, 8000, 6.1, Disabled\n"
        d = SC.detect(fresh=True)
    check("an 8 GB card below Turing is still refused", d["capable"] is False
          and "older than Turing" in d["why"], d["why"])
    with G.World(smi(PRIM, ("NVIDIA GeForce RTX 2060", 8192, ""))) as w:
        d = SC.detect(fresh=True)
    check("an 8 GB card with no id is still refused (work is only pointed at an id)",
          d["capable"] is False and "id" in d["why"], d["why"])


def t_small_card_arithmetic():
    kv16 = 2 * 36 * 8 * 128 * 1.0625 * 16384 / 2 ** 30
    kv8 = 2 * 36 * 8 * 128 * 1.0625 * 8192 / 2 ** 30
    check("the 8B cache is 78,336 bytes a token: 1.20 GiB at 16K, 0.60 at 8K",
          2 * 36 * 8 * 128 * 1.0625 == 78336 and round(kv16, 2) == 1.20 and round(kv8, 2) == 0.60)
    check("need @16K = 4.67 + 1.20 + 0.30 + 0.33 = 6.50; @8K = 5.90",
          SC._small_8b_need(16384) == 6.50 and SC._small_8b_need(8192) == 5.90,
          (SC._small_8b_need(16384), SC._small_8b_need(8192)))
    check("room: 8,192 MiB no monitor 6.65, with monitor 6.15; 7,680 no monitor 6.15",
          SC._room_gib(8192, False) == 6.65 and SC._room_gib(8192, True) == 6.15
          and SC._room_gib(7680, False) == 6.15)
    check("the picture model @8K needs 5.59 + 0.23 + 0.63 = 6.45 (16K would be 6.68)",
          SC._vision_gib(8192) == 6.45 and SC._vision_gib(16384) == 6.68,
          (SC._vision_gib(8192), SC._vision_gib(16384)))

    class Card:
        def __init__(self, mib, mon=False):
            self.total_mb, self.display_active, self.name = mib, mon, "X"
    check("8,192 MiB, no monitor: the 8B at 16,384 (6.50, fits 6.65)",
          SC._small_8b_plan(8192, False) == ("qwen3:8b", 16384, 6.50))
    check("8,188 MiB, no monitor: still 16,384 (7.996 - 1.35 = 6.65 after rounding)",
          SC._small_8b_plan(8188, False) == ("qwen3:8b", 16384, 6.50))
    check("8,192 MiB WITH a monitor on it: 8,192 tokens (5.90 fits 6.15), not 16K",
          SC._small_8b_plan(8192, True) == ("qwen3:8b", 8192, 5.90))
    check("7,680 MiB no monitor: 8,192 tokens (16K needs 6.50 > 6.15)",
          SC._small_8b_plan(7680, False) == ("qwen3:8b", 8192, 5.90))
    check("7,680 MiB with a monitor: nothing fits (5.65 < 5.90)",
          SC._small_8b_plan(7680, True) == (None, None, None))
    check("pictures: fit at 8,192 with no monitor, not with one",
          SC._small_vision_plan(8192, False) == ("qwen2.5vl:7b", 8192, 6.45)
          and SC._small_vision_plan(8192, True) == (None, None, None))
    check("from 10,240 MiB up nothing changed: the 12 GB card still gets LONG_BIG",
          SC._long_context_plan(12288) == SC.LONG_BIG and SC._long_context_plan(10240) == SC.LONG_SMALL
          and SC.LONG_BIG == ("qwen3:8b", 32768, 7.69))
    check("no refusal at all for a 10 GB or bigger card, for any of the five",
          all(SC._small_card_refusal(f, Card(m)) is None
              for f in SC.FEATURE_IDS for m in (10240, 12288, 16376, 24564)))


def t_8gb_second_card_features():
    with G.World(smi(PRIM, ("NVIDIA GeForce RTX 2060 SUPER", 8192, U_8A)),
                 installed=("qwen3:8b", "qwen2.5vl:7b")) as w:
        det = SC.detect(fresh=True)
        check("8 + 8: capable, says which features it can take and which stay off",
              det["capable"] is True and "some of the extra-card features" in det["why"]
              and "Learning in the background" in det["why"]
              and "Longer conversations" in det["why"] and "stay off" in det["why"], det["why"])
        plans = {f: SC._feature_model(f, det) for f in SC.FEATURE_IDS}
        check("learning and the wiki: qwen3:8b at 16,384 (6.50 GiB)",
              plans["learning"] == ("qwen3:8b", 16384, 6.50)
              and plans["wiki"] == ("qwen3:8b", 16384, 6.50), plans)
        check("pictures: qwen2.5vl:7b at 8,192 (6.45 GiB, a guess)",
              plans["vision"] == ("qwen2.5vl:7b", 8192, 6.45), plans["vision"])
        check("'Longer conversations' and 'Browser control' have NO plan on an 8 GB card",
              plans["long_context"] == (None, None, None)
              and plans["browser_control"] == (None, None, None))
        for f, words in (("long_context", "holds no more conversation than your main card"),
                         ("browser_control", "Browser control needs room")):
            code, out = SC.request_change(f, True)
            check(f"turning on {f} is refused before any card, in words",
                  code == 503 and words in out["error"], out)
        rows = {r["id"]: r for r in SC.status()["features"]}
        check("the 'Longer conversations' row says why, in plain words, and is not offered",
              "16,384 tokens" in rows["long_context"]["why"]
              and "cannot be turned on with this card" in rows["long_context"]["why"]
              and rows["long_context"]["model"] is None, rows["long_context"]["why"])
        # The features that ARE offered: one card each.
        seen = []
        gate = lambda a, d, p: seen.append((a, d, p)) or Verdict(True, "ask", "approved")
        SC.request_change("master", True, gate=gate)
        code, out = SC.request_change("learning", True, gate=gate)
        check("Learning: one card, action second_card_enable, names 8 GB, the model, the "
              "16,384 tokens and says it is calculated, not measured",
              code == 200 and seen[-1][0] == SC.ACTION
              and "8 GB" in seen[-1][2] and "qwen3:8b" in seen[-1][2] and "16,384" in seen[-1][2]
              and "calculated from the model's size, not measured" in seen[-1][2], seen[-1][2])
        st = SC.status()
        check("the lane is running, started with 16,384 tokens of room",
              st["lane"]["state"] == "running"
              and w.started[-1].kwargs["env"]["OLLAMA_CONTEXT_LENGTH"] == "16384", st["lane"])
        lane = SC.lane_for("learning")
        check("lane_for('learning') is a real lane at 16,384 on the second card",
              lane is not None and lane.num_ctx == 16384 and lane.model == "qwen3:8b", lane)
        check("lane_for('long_context') stays None even if a stale switch says on",
              (w.switches(master=True, long_context=True, learning=True) or True)
              and SC.lane_for("long_context") is None)
        check("and the row for it is not 'active'",
              not next(r for r in SC.status()["features"] if r["id"] == "long_context")["active"])
        w.switches(master=True, browser_control=True, long_context=True)
        check("browser_control on top of a stale long_context is still not offered",
              SC.lane_for("browser_control") is None)
        w.switches(master=True, vision=True)
        v = SC.lane_for("vision")
        check("Pictures: a lane at 8,192 on an 8 GB card with no monitor",
              v is not None and v.num_ctx == 8192 and v.model == "qwen2.5vl:7b", v)


def t_8gb_card_with_a_monitor():
    with G.World(smi(PRIM, ("NVIDIA GeForce RTX 2060 SUPER", 8192, U_8A, True)),
                 installed=("qwen3:8b", "qwen2.5vl:7b")) as w:
        det = SC.detect(fresh=True)
        check("a monitor on the 8 GB card: learning drops to 8,192 tokens (5.90)",
              SC._feature_model("learning", det) == ("qwen3:8b", 8192, 5.90))
        check("and Pictures is refused, in words that say plug the monitors into the main card",
              SC._feature_model("vision", det) == (None, None, None)
              and "plug the monitors into the main card" in SC._unsupported("vision", det),
              SC._unsupported("vision", det))
        w.switches(master=True, learning=True)
        SC.status()
        check("the lane starts at 8,192",
              w.started and w.started[-1].kwargs["env"]["OLLAMA_CONTEXT_LENGTH"] == "8192")


def t_bigger_cards_by_band():
    for name, mib, uid, gb in (("RTX 4060 Ti 16GB", 16376, U_16, "16 GB"),
                               ("RTX 3090", 24564, U_24, "24 GB"),
                               ("RTX 2060 12GB", 12288, U_12, "12 GB"),
                               ("RTX 2080 Ti", 11264, U_10, "11 GB")):
        with G.World(smi(PRIM, (name, mib, uid))) as w:
            det = SC.detect(fresh=True)
            check(f"{mib} MiB reads as {gb} and is capable",
                  det["capable"] is True and f"({gb})" in det["why"], det["why"])
            check(f"{mib} MiB: the full plan, unchanged - qwen3:8b at 32K, 7.69 GiB",
                  SC._feature_model("long_context", det) == ("qwen3:8b", 32768, 7.69)
                  and SC._feature_model("browser_control", det) == ("qwen3:8b", 32768, 7.69))
            check(f"{mib} MiB: Pictures at 32K (7.15 GiB), nothing refused",
                  SC._feature_model("vision", det) == ("qwen2.5vl:7b", 32768, 7.15)
                  and all(SC._unsupported(f, det) is None for f in SC.FEATURE_IDS))
    check("16 GB and 24 GB: room 14.64 and 22.64 GiB, so the 8B plan leaves lots spare",
          SC._room_gib(16376, False) == 14.64 and SC._room_gib(24564, False) == 22.64)
    check("qwen3:14b @ 32K needs 11.71 GiB (fits both, NOT switched on: owner decision)",
          round(8.42 + 2 * 40 * 8 * 128 * 1.0625 * 32768 / 2 ** 30 + 0.30 + 0.33, 2) == 11.71)
    # "One bigger model on both cards" with these sizes.
    for mib, uid, note in ((16376, U_16, True), (24564, U_24, True), (12288, U_12, False)):
        with G.World(smi(PRIM, ("Card", mib, uid))) as w:
            det = SC.detect(fresh=True)
            ok, why = SC._combined_capable(det)
            text = SC._describe_combined(det)
            check(f"combined with an 8 GB main card and {mib} MiB: allowed "
                  f"({8192 + mib} MiB together is over the 18,432 floor)", ok is True, why)
            check(f"combined card: alone-has-room note {'present' if note else 'absent'}",
                  ("alone has room for qwen3:14b" in text) is note, text)
    with G.World(smi(PRIM, ("Card", 8192, U_8A))) as w:
        ok, why = SC._combined_capable(SC.detect(fresh=True))
        check("combined with 8 + 8 GB: refused (16 GB together is under 18 GB)",
              ok is False and "not the 18 GB" in why, why)
    with G.World(smi(PRIM, ("Card", 10240, U_10))) as w:
        ok, why = SC._combined_capable(SC.detect(fresh=True))
        check("combined with 8 + 10 GB: exactly the floor, allowed", ok is True, why)


def t_mixed_extra_cards():
    E8 = ("NVIDIA GeForce RTX 2060 SUPER", 8192, U_8A)
    E8b = ("NVIDIA GeForce RTX 2070", 8192, U_8B)
    # 8 + 8 + 8: second = lower index, third = the other 8 GB card.
    with G.World(smi(PRIM, E8, E8b), installed=("qwen3:8b", "qwen2.5vl:7b")) as w:
        det = SC.detect(fresh=True)
        check("8+8+8: second is the first 8 GB card, third the other",
              det["second"]["uuid"] == U_8A and det["_third"].uuid == U_8B)
        w.switches(master=True, learning=True, wiki=True)
        st = SC.status()
        t = st["third"]
        check("the third 8 GB card: capable, 'Longer conversations' and 'Browser control' are "
              "not assignable, learning and wiki are",
              t["capable"] is True and t["assignable"] == ["learning", "wiki"]
              and set(t["unavailable"]) == {"long_context", "browser_control"}, t)
        code, out = SC.request_change("third", assign="long_context")
        check("assigning 'Longer conversations' to an 8 GB third card: refused in words",
              code == 400 or code == 503, (code, out))
        w.switches(master=True, learning=True, wiki=True, long_context=True)
        code, out = SC.request_change("third", assign="long_context")
        check("even with its switch stale-on: 503, 'holds no more conversation'",
              code == 503 and "holds no more conversation" in out["error"], out)
        seen = []
        gate = lambda a, d, p: seen.append((a, d, p)) or Verdict(True, "ask", "approved")
        code, out = SC.request_change("third", assign="wiki", gate=gate)
        sw = SC._read_switches()
        check("assigning the wiki to the third 8 GB card: one card naming it, saved WITH the "
              "card's id", code == 200 and sw["third_feature"] == "wiki"
              and sw["third_card"] == U_8B and "calculated" in seen[-1][2]
              and "one more copy of Ollama" in seen[-1][2] and "fourth" not in seen[-1][2],
              (sw, seen[-1][2]))
        st = SC.status()
        check("second lane (learning) and third lane (wiki) both run, on two ports",
              st["lane"]["state"] == "running" and st["third"]["lane"]["state"] == "running"
              and st["third"]["model"] == "qwen3:8b" and st["third"]["context"] == 16384,
              (st["lane"], st["third"]))
    # 8 primary + 12 + 8: second is the 12 GB card, third the 8 GB one.
    with G.World(smi(PRIM, ("RTX 2060 12GB", 12288, U_12), E8),
                 installed=("qwen3:8b", "qwen2.5vl:7b")) as w:
        det = SC.detect(fresh=True)
        check("8 + 12 + 8: second is the 12 GB, third the 8 GB",
              det["second"]["uuid"] == U_12 and det["_third"].uuid == U_8A)
        check("the second (12 GB) still gets everything: nothing refused",
              all(SC._unsupported(f, det) is None for f in SC.FEATURE_IDS))
        w.switches(master=True, long_context=True, browser_control=True, learning=True)
        code, out = SC.request_change("third", assign="browser_control")
        check("Browser control cannot move to the 8 GB third card (its own reason)",
              code == 503 and "Browser control needs room" in out["error"], out)
        code, out = SC.request_change("third", assign="learning",
                                      gate=lambda a, d, p: Verdict(True, "ask", "approved"))
        check("Learning can", code == 200 and SC._read_switches()["third_feature"] == "learning")
        st = SC.status()
        check("12 GB second runs long_context at 32K, 8 GB third runs learning at 16K",
              st["third"]["context"] == 16384
              and SC.lane_for("long_context").num_ctx == 32768
              and SC.lane_for("learning").num_ctx == 16384)
    # 8 primary + 10 + 8.
    with G.World(smi(PRIM, ("RTX 3080 10GB", 10240, U_10), E8),
                 installed=("qwen3:8b",)) as w:
        det = SC.detect(fresh=True)
        check("8 + 10 + 8: second is the 10 GB (full plan), third the 8 GB (small plan)",
              det["second"]["uuid"] == U_10 and det["_third"].uuid == U_8A
              and SC._feature_model("long_context", det) == ("qwen3:8b", 32768, 7.69)
              and SC._feature_model("learning", det, card=det["_third"])
              == ("qwen3:8b", 16384, 6.50))


def t_third_card_identity():
    E8 = ("NVIDIA GeForce RTX 2060 SUPER", 8192, U_8A)
    E8b = ("NVIDIA GeForce RTX 2070", 8192, U_8B)
    E8c = ("NVIDIA GeForce RTX 2070 SUPER", 8192, "GPU-8c8c8c8c-7777-4777-8777-ggggggggggg7")
    with G.World(smi(PRIM, E8, E8b), installed=("qwen3:8b",)) as w:
        w.switches(master=True, learning=True, wiki=True, third_feature="wiki", third_card=U_8B)
        st = SC.status()
        check("the same card still in the third slot: the choice is acted on, the lane starts",
              st["third"]["assigned"] == "wiki" and st["third"]["lane"]["state"] == "running"
              and len(w.started) == 2, st["third"])
        check("its uuid survives a status() round trip (state file keeps third_card)",
              SC._read_switches()["third_card"] == U_8B)
        # The card in the third slot changes (the old one is pulled, another added).
        w.smi = smi(PRIM, E8, E8c)
        w.started.clear()
        SC._reset_for_tests()
        CP._cache.update(at=-1e9, cards=None, fields="")
        st = SC.status()
        third = st["third"]
        check("a DIFFERENT card in the third slot: nothing is assigned to it, in words",
              third["capable"] is True and third["assigned"] is None
              and "different graphics card" in third["why"] and "approve" in third["why"],
              third["why"])
        check("...and no lane was started on the card the owner did not approve",
              third["lane"]["state"] == "off"
              and not any("GPU-8c8c" in p.kwargs["env"].get("CUDA_VISIBLE_DEVICES", "")
                          for p in w.started), [p.kwargs["env"] for p in w.started])
        check("the choice is KEPT in the file (only acted on again when re-approved)",
              SC._read_switches()["third_feature"] == "wiki"
              and SC._read_switches()["third_card"] == U_8B)
        check("lane_for('wiki') falls back to the second card, not the unapproved one",
              (SC.lane_for("wiki") or SC.Lane("", "", 0, "")).url == "http://127.0.0.1:11435")
        # Asking for the same feature again is NOT 'already on the third card'.
        code, out = SC.request_change("third", assign="wiki", spawn=lambda fn: None)
        check("asking again for the same feature raises a card (not 'already on')",
              code == 200 and out["pending"] is True, out)
        # Approved: the new card's id is stored.
        SC.request_change("third", assign=None)
        code, out = SC.request_change("third", assign="wiki",
                                      gate=lambda a, d, p: Verdict(True, "ask", "approved"))
        check("approved for the new card: its id is stored and the lane runs there",
              SC._read_switches()["third_card"] == E8c[2]
              and SC.status()["third"]["assigned"] == "wiki")
        # The card in the slot changes WHILE the approval card waits.
        SC.request_change("third", assign=None)
        w.smi = smi(PRIM, E8, E8b)
        CP._cache.update(at=-1e9, cards=None, fields="")

        def swap_then_yes(a, d, p):
            w.smi = smi(PRIM, E8, E8c)
            CP._cache.update(at=-1e9, cards=None, fields="")
            return Verdict(True, "ask", "approved")
        SC.request_change("third", assign="learning", gate=swap_then_yes)
        check("the slot changed while the card waited: refused, nothing saved",
              SC._read_switches()["third_feature"] is None
              and SC._LAST["third"]["outcome"] == "refused"
              and "third slot changed" in SC._LAST["third"]["reason"], SC._LAST.get("third"))
    # A file from before the card id was kept: ask again (the safe way).
    with G.World(smi(PRIM, E8, E8b), installed=("qwen3:8b",)) as w:
        w.switches(master=True, learning=True, wiki=True, third_feature="wiki")   # no third_card
        st = SC.status()
        check("a legacy file (no card id) is NOT acted on for whichever card is third now",
              st["third"]["assigned"] is None and st["third"]["lane"]["state"] == "off"
              and "before Jarvis kept track" in st["third"]["why"]
              and "approve the move again" in st["third"]["why"], st["third"]["why"])
        check("the legacy choice is kept, and the feature keeps working on the second card",
              SC._read_switches()["third_feature"] == "wiki"
              and SC._read_switches()["third_card"] is None
              and SC.lane_for("wiki") is not None)
        check("the id is compared case-blind",
              (w.switches(master=True, wiki=True, third_feature="wiki", third_card=U_8B.upper())
               or True) and SC.status()["third"]["assigned"] == "wiki")
    # Unassigning clears the id.
    with G.World(smi(PRIM, E8, E8b)) as w:
        w.switches(master=True, wiki=True, third_feature="wiki", third_card=U_8B)
        SC.request_change("third", assign=None)
        raw = json.loads((w.dir / "second-card.json").read_text(encoding="utf-8"))
        check("unassigning clears both the feature and the card id",
              raw["third_feature"] is None and raw["third_card"] is None, raw)


def t_wording_for_extra_cards():
    with G.World(SMI_THREE) as w:
        w.switches(master=True, long_context=True)
        seen = []
        SC.request_change("third", assign="long_context",
                          gate=lambda a, d, p: seen.append(p) or Verdict(True, "ask", "approved"))
        check("the third card's card does not say 'fourth copy'",
              seen and "fourth" not in seen[0] and "one more copy of Ollama" in seen[0], seen)
    src = (BACKEND / "jarvis_second_card.py").read_text(encoding="utf-8")
    check("no user-facing '10 GB' floor sentence is left in the not-capable reason",
          "need at least 10 GB" not in src)


def t_the_fixture():
    rc = G.main(["--check"])
    check("second-card-cases.json (the desktop's and the phone's copy) equals a fresh run",
          rc == 0, "run python3 tools/gen_second_card_cases.py")
    data = json.loads(G.FIXTURE.read_text(encoding="utf-8"))["cases"]
    check("the eight named cases are there",
          set(data) == {"one_card", "capable_off", "capable_pending", "running_long_context",
                        "card_missing_but_enabled", "not_capable_old_card",
                        "one_card_reads_words", "combined_running"}, sorted(data))


def t_the_real_file():
    if missing("jarvis_hud.py"):
        return check("SKIP - no jarvis_hud.py here; the rehearsal above is the proof", True)
    s = (BACKEND / "jarvis_hud.py").read_text(encoding="utf-8")
    check("the backend's jarvis_hud.py has /api/second-card (second-card.patch applied)",
          '"/api/second-card"' in s)


# ------------------------------------------- "Study helper" and "Referee suggestions" --
# 2026-09-30, JARVIS-API section 108. Two more switches, built OFF like the rest.

def _row(st, fid):
    return next(f for f in st["features"] if f["id"] == fid)


def t_study_and_referee_rows():
    with G.World(G.SMI["one_card"]) as w:
        st = SC.status()
        for fid in ("study", "referee"):
            r = _row(st, fid)
            check(f"{fid}: on a one-card PC it is off and says why (the same words as the rest)",
                  r["enabled"] is False and r["active"] is False and r["available"] is False
                  and r["why"].startswith("Needs a capable second graphics card: only one "
                                          "graphics card found"), r["why"])
        check("study: the row's what names the quiz and says it stays on the PC",
              "Quiz questions are written" in _row(st, "study")["what"]
              and "stay on this PC" in _row(st, "study")["what"])
        check("referee: the row's what says only your tap ticks, never a test",
              "Only your tap ticks it" in _row(st, "referee")["what"]
              and "never runs a test" in _row(st, "referee")["what"])
        check("the switches did not start anything", not w.started)
    with G.World(G.SMI["2080s_2060"]) as w:
        st = SC.status()
        check("capable card, everything off (the default): both off, 'Off.'",
              _row(st, "study")["why"] == "Off." and _row(st, "referee")["why"] == "Off."
              and _row(st, "study")["model"] == "qwen3:8b" and _row(st, "study")["memory_gib"] == 7.69,
              (_row(st, "study"), _row(st, "referee")))
        r = _row(st, "referee")
        check("referee carries no model and no memory (it loads none)",
              r["model"] is None and r["memory_gib"] is None and r["model_installed"] is None
              and r["needs"] == [], r)
        w.switches(master=True, referee=True)
        st = SC.status()
        r = _row(st, "referee")
        check("referee ON: working at once, no lane needed, no Ollama started, no model installed check",
              r["enabled"] and r["active"] and r["available"] and not w.started
              and r["why"].startswith("Working: it compares the numbers you log with your targets")
              and "loads no model" in r["why"], r)
        check("... and the second lane says nothing is switched on for it",
              st["lane"]["state"] == "off" and SC.lane_for("referee") is None and not w.started)
        w.switches(master=True, study=True)
        st = SC.status()
        r = _row(st, "study")
        check("study ON: the second Ollama starts (it has a model to serve) and the row is working",
              len(w.started) == 1 and r["available"] is True
              and r["why"].startswith("Working: qwen3:8b on the NVIDIA GeForce RTX 2060"), r["why"])
    with G.World(G.SMI["2080s_2060"], installed=("qwen3:14b",)) as w:
        w.switches(master=True, study=True)
        r = _row(SC.status(), "study")
        check("study with its model missing: says how to install it, not working",
              r["model_installed"] is False and r["available"] is False
              and "ollama pull qwen3:8b" in r["why"], r)
    with G.World(G.SMI["one_card"]) as w:
        w.switches(master=True, study=True, referee=True)
        st = SC.status()
        check("both saved ON but the card is gone: 'Your choice is kept', neither active",
              all(_row(st, f)["enabled"] and not _row(st, f)["active"]
                  and "Your choice is kept" in _row(st, f)["why"] for f in ("study", "referee")))
        check("and referee_active reads false without the card", SC.feature_active("referee") is False
              and SC.feature_active("study") is False and not w.started)


def t_study_and_referee_cards():
    with G.World(G.SMI["2080s_2060"]) as w:
        seen = []
        gate = lambda a, d, p: seen.append((a, d, p)) or Verdict(True, "ask", "approved")
        SC.request_change("master", True, gate=gate)
        seen.clear()
        code, out = SC.request_change("study", True, gate=gate)
        check("study ON: one card, action second_card_enable, tier ask path",
              code == 200 and len(seen) == 1 and seen[0][0] == "second_card_enable", seen)
        d, text = seen[0][1], seen[0][2]
        check("the study card names the card, the model, the quiz and that nothing leaves",
              "Turn on \"Study helper\" on the second graphics card?" in text
              and "RTX 2060" in text and "qwen3:8b" in text and "Quiz questions are written" in text
              and "Nothing leaves this PC" in text and "If you say no" in text
              and d["model"] == "qwen3:8b" and d["feature"] == "study"
              and d["leaves_this_pc"] is False, text)
        check("study is on after the yes", SC._read_switches()["features"]["study"] is True
              and len(w.started) == 1)
        seen.clear()
        with mock.patch.dict(sys.modules, {"jarvis_referee": mock.Mock()}) as _m:
            code, out = SC.request_change("referee", True, gate=gate)
            ref_calls = sys.modules["jarvis_referee"].ensure_job.call_count
        d, text = seen[0][1], seen[0][2]
        check("referee ON: one card, the same action (second_card_enable), tier ask",
              code == 200 and len(seen) == 1 and seen[0][0] == "second_card_enable", seen)
        check("the referee card says plainly: no model yet, no second Ollama, your tap ticks",
              "Turn on \"Referee suggestions\"?" in text and "RTX 2060" in text
              and "Which model: none yet" in text and "no second copy of Ollama" in text
              and "Your tap ticks the step" in text and "never runs a test" in text
              and "at most a few cards a day" in text and d["model"] is None
              and d["memory_gib"] is None and d["leaves_this_pc"] is False, text)
        check("... and it never says qwen3 or any memory figure", "qwen3" not in text
              and " GB of the card" not in text, text)
        check("referee is on, and turning it on tells the scheduler to add its hourly look",
              SC._read_switches()["features"]["referee"] is True and ref_calls >= 1, ref_calls)
        n_started = len(w.started)
        # OFF is immediate, no card, and also tells the scheduler.
        seen.clear()
        with mock.patch.dict(sys.modules, {"jarvis_referee": mock.Mock()}):
            code, out = SC.request_change("referee", False)
            off_calls = sys.modules["jarvis_referee"].ensure_job.call_count
        check("referee OFF: at once, no card, and the scheduler is told",
              code == 200 and out["enabled"] is False and not seen and off_calls == 1
              and SC._read_switches()["features"]["referee"] is False)
        code, out = SC.request_change("study", False)
        check("study OFF: at once, no card", code == 200 and not seen
              and SC._read_switches()["features"]["study"] is False)
        check("the lane stopped when the last lane-using switch went off",
              w.running() is False and len(w.started) == n_started)
        # A yes that is not a person: refused for both.
        for fid in ("study", "referee"):
            for label, v in (("tier notify", Verdict(True, "notify", "notify")),
                             ("denied", Verdict(False, "ask", "denied")),
                             ("timed out", Verdict(False, "ask", "timed_out"))):
                SC.request_change(fid, True, gate=lambda a, dd, p, v=v: v)
                check(f"{fid}, {label}: stays off", SC._read_switches()["features"][fid] is False)
        code, out = SC.request_change("study", True, gate=gate, tier_of=lambda a: "auto")
        check("tier not 'ask': refused before any card", code == 503 and "be 'ask'" in out["error"])
        w.switches(master=False)
        seen.clear()
        code, out = SC.request_change("referee", True, gate=gate)
        check("referee before the main switch: refused in words, no card",
              code == 400 and "main switch" in out["error"] and not seen, out)
    with G.World(G.SMI["one_card"]):
        seen = []
        for fid in ("study", "referee"):
            code, out = SC.request_change(fid, True, gate=lambda *a: seen.append(a))
            check(f"{fid} ON with no capable card: 503 with the reason, no card",
                  code == 503 and "only one graphics card" in out["error"] and not seen, out)


def t_referee_takes_no_lane_and_blocks_nothing():
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, referee=True)
        st = SC.status()
        check("referee alone starts no second Ollama and holds no card",
              not w.started and SC.lane_state() == "off")
        check("... and it does not stop 'One bigger model on both cards' from being turned on",
              SC._combined_conflict(SC._read_switches()) is False
              and st["combined"]["conflict"] is False)
        gate = lambda a, d, p: Verdict(True, "ask", "approved")
        code, out = SC.request_change("combined", True, gate=gate)
        check("combined ON with referee on: a card is raised and it turns on",
              code == 200 and SC._read_switches()["combined"] is True, out)
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, study=True)
        check("study (it has a model) DOES conflict with combined, as the other features do",
              SC._combined_conflict(SC._read_switches()) is True)
        code, out = SC.request_change("combined", True, gate=lambda a, d, p: Verdict(True, "ask", "approved"))
        check("combined ON with study on: refused (409)", code == 409, out)
        w.switches(master=True, combined=True, study=True)
        cst = SC.status()["combined"]
        check("... and with both saved on, the combined row names Study helper among the "
              "switches to turn off", cst["conflict"] is True and "Study helper" in cst["why"], cst)
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, referee=True)
        code, out = SC.request_change("third", assign="referee")
        check("referee cannot be moved to a third card: it loads no model",
              code == 400 and "loads no model" in out["error"], out)


def t_study_call_routes_to_the_lane():
    import jarvis_quiz as JQ
    chats = []
    real = None

    def http(url, payload=None, timeout=2.0):
        if url.endswith("/api/chat"):
            chats.append((url, payload))
            return {"done_reason": "stop", "message": {"content": '{"questions": []}'}}
        return real(url, payload, timeout)

    fallback = mock.Mock(return_value='{"from": "everyday"}')
    with G.World(G.SMI["2080s_2060"]) as w:
        real = SC._http_json            # the World's stand-in, installed just now
        call = SC.study_call(fallback)
        with mock.patch.object(SC, "_http_json", http):
            out = call("sys", "usr", {"type": "object"}, 300)
        check("study OFF (the default): the everyday call answers, the lane is never asked",
              out == '{"from": "everyday"}' and not chats and fallback.call_count == 1
              and not w.started)
        w.switches(master=True, study=True)
        with mock.patch.object(SC, "_http_json", http):
            out = call("sys", "usr", {"type": "object"}, 300)
        check("study ON with the lane up: the second card answers, on 127.0.0.1:11435",
              out == '{"questions": []}' and len(chats) == 1
              and chats[0][0] == "http://127.0.0.1:11435/api/chat" and fallback.call_count == 1, chats)
        body = chats[0][1]
        check("... with the lane's model and context, the schema as the format, no other model",
              body["model"] == "qwen3:8b" and body["options"]["num_ctx"] == 32768
              and body["format"] == {"type": "object"} and body["stream"] is False
              and body["messages"][0] == {"role": "system", "content": "sys"}
              and body["messages"][1] == {"role": "user", "content": "usr"}, body)
        check("the model that answered is recorded for the grader check",
              call.active_model() == "qwen3:8b")
        check("... and rides on the reply itself (per call, not a shared global)",
              getattr(out, "model", None) == "qwen3:8b")
        import threading as _th
        seen_other = []
        _t = _th.Thread(target=lambda: seen_other.append(call.active_model()))
        _t.start()
        _t.join(5)
        check("another thread's call never sees this thread's model", seen_other == [""], str(seen_other))
        # The lane does not answer: fall back to today's behaviour, this call only.
        def broken(url, payload=None, timeout=2.0):
            if url.endswith("/api/chat"):
                raise OSError("down")
            return real(url, payload, timeout)
        with mock.patch.object(SC, "_http_json", broken):
            out = call("sys", "usr", {"type": "object"}, 300)
        check("the lane fails: the everyday call answers instead (unchanged local behaviour)",
              out == '{"from": "everyday"}' and fallback.call_count == 2
              and call.active_model() == "")
        # A cut-short reply from the lane is a failure too.
        def cut(url, payload=None, timeout=2.0):
            if url.endswith("/api/chat"):
                return {"done_reason": "length", "message": {"content": "{"}}
            return real(url, payload, timeout)
        with mock.patch.object(SC, "_http_json", cut):
            out = call("sys", "usr", {"type": "object"}, 300)
        check("a reply cut short is not used", fallback.call_count == 3)
        # No fallback at all: an error, which the quiz turns into model_unavailable.
        try:
            SC.study_call(None)("s", "u", {}, 10)
            raised = False
        except Exception:
            raised = True
        check("with study off and no fallback, it raises (the quiz says model_unavailable)", raised)
        w.switches(master=True, study=True, third_feature="study")
        check("never a non-loopback lane",
              SC._study_chat(SC.Lane("http://10.0.0.5:11435", "qwen3:8b", 32768, "x"),
                             "s", "u", {}, 10) is None)


def t_wire_study_into_the_quiz():
    import jarvis_quiz as JQ
    JQ._reset_for_tests()
    try:
        keep = lambda spec, cards: 0
        JQ.configure(keep=keep)
        banner = SC.wire_study()
        check("wire_study hands the quiz a call and says so in one banner line",
              banner.startswith("  study      Study helper wired") and JQ._STATE["call"] is not None
              and JQ._STATE["call"].__name__ == "call", banner)
        check("... and leaves the deck 'keep' function alone", JQ._STATE["keep"] is keep)
        # The quiz end to end, study ON: questions are written by the lane's model.
        replies = []
        real = None

        def http(url, payload=None, timeout=2.0):
            if url.endswith("/api/chat"):
                replies.append((url, payload["model"]))
                if "questions" in json.dumps(payload["format"]):
                    return {"done_reason": "stop", "message": {"content": json.dumps(
                        {"questions": [{"kind": "recall", "prompt": "What is Ohm's law?",
                                        "passage": PASSAGE}]})}}
                return {"done_reason": "stop", "message": {"content": json.dumps(
                    {"level": "got_it", "comment": "You said what the passage says."})}}
            return real(url, payload, timeout)
        PASSAGE = ("Ohm's law says the voltage across a resistor equals the current through "
                   "it times its resistance.")
        text = (PASSAGE + " ") * 4
        with G.World(G.SMI["2080s_2060"]) as w:
            real = SC._http_json
            w.switches(master=True, study=True)
            with mock.patch.object(SC, "_http_json", http):
                code, out = JQ.handle_post("/api/quiz", {"text": text, "count": 1})
                qid = out["quiz"]["id"] if code == 200 else None
                code2, out2 = JQ.handle_post(f"/api/quiz/{qid}/answer",
                                             {"n": 1, "answer": "voltage is current times resistance"})
            check("study ON: the quiz was written AND marked on the second card's model",
                  code == 200 and code2 == 200 and len(replies) == 2
                  and all(u == "http://127.0.0.1:11435/api/chat" and m == "qwen3:8b"
                          for u, m in replies), (code, code2, replies))
            check("... and 'grader_verified' stays false: no grader result exists for this model",
                  out2["quiz"]["grader_verified"] is False)
            # A result measured on THIS model vouches for it; one measured on another does not.
            import tempfile
            with tempfile.TemporaryDirectory() as td:
                res = Path(td) / "quiz_grader_results.json"
                base = {"total": 20, "correct": 19, "injection_cases": 3, "injection_wins": 0}
                with mock.patch.object(JQ, "RESULTS_PATH", res):
                    res.write_text(json.dumps(dict(base, model="jarvis-primary")), encoding="utf-8")
                    check("a result measured on the everyday model, quiz on the lane's: not verified",
                          JQ.grader_verified() is False)
                    res.write_text(json.dumps(dict(base, model="qwen3:8b")), encoding="utf-8")
                    check("a result measured on qwen3:8b: verified while it is the lane answering",
                          JQ.grader_verified() is True)
                    SC._STUDY.model = ""
                    res.write_text(json.dumps(dict(base, model="jarvis-primary")), encoding="utf-8")
                    check("... and the everyday model's own result counts again when it answers",
                          JQ.grader_verified() is True)
        # Study OFF again: the default call runs, i.e. the everyday model (a stand-in here).
        seen = []
        JQ.configure(call=SC.study_call(lambda s, u, sc, n: seen.append(n) or json.dumps(
            {"questions": [{"kind": "recall", "prompt": "What is Ohm's law?",
                            "passage": PASSAGE}]})))
        with G.World(G.SMI["2080s_2060"]) as w:
            code, out = JQ.handle_post("/api/quiz", {"text": text, "count": 1})
            check("study OFF: the quiz runs on the everyday call, nothing asked of the lane",
                  code == 200 and len(seen) == 1 and not w.http and not w.started)
    finally:
        JQ._reset_for_tests()
    # jarvis_quiz keeps its import rule: it does not import this module.
    src = (HERE / "jarvis_quiz.py").read_text(encoding="utf-8")
    imports = re.findall(r"^\s*(?:import|from)\s+(jarvis_\w+)", src, re.M)
    check("jarvis_quiz.py still imports only jarvis_local_http and jarvis_wellbeing",
          set(imports) <= {"jarvis_local_http", "jarvis_wellbeing"}, imports)
    check("... and never the second-card module", "jarvis_second_card" not in re.sub(
        r'(?s)""".*?"""', "", src.replace("second_card.study_call", "")).replace(
        "# jarvis_second_card", ""), "the quiz names the second card")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("t_") and callable(v)]
    for fn in tests:
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
