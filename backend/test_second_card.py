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


# ------------------------------------------------------------ switches --

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
                      "pin_note", "pin_command", "features", "last"}, sorted(st))
    check("detected has exactly its keys",
          set(st["detected"]) == {"capable", "why", "primary", "second", "cards"})
    check("each feature row has exactly its keys",
          all(set(f) == {"id", "name", "what", "enabled", "active", "available", "needs", "model",
                         "model_installed", "memory_gib", "why"} for f in st["features"]))
    check("the five feature ids, in order",
          [f["id"] for f in st["features"]] == ["long_context", "vision", "learning",
                                                 "browser_control", "wiki"])
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


# ------------------------------------------------------------- the hooks --

def _turn(messages, *, lane_for=None, enabled=None, context_length=2048, lane_choice="auto"):
    sent = []

    def opener(url, body):
        sent.append((url, body))
        return W.FakeResponse(W.stream([("content", "ok"), ("done", "stop")]))
    patch = mock.patch.object(AG, "_second_card_lane", lane_for or (lambda f: None))
    with patch:
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
    sent = _turn(pic, enabled={"calculator"})
    check("a picture, second card off: the main model gets it exactly as before, tools and all",
          sent[0][0].startswith("http://127.0.0.1:11434") and sent[0][1]["model"] == "qwen3:8b"
          and sent[0][1]["messages"] == pic and "tools" in sent[0][1])
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
    check("the shipped toml has a [second_card] section", "\n[second_card]\n" in toml)
    check("and no switch lives in it (the switches are in second-card.json)",
          not re.search(r"^\s*(master|long_context|vision|learning|browser_control|wiki)\s*=",
                        toml[toml.index("\n[second_card]\n"):].split("\n[", 2)[1], re.M))


def t_the_fixture():
    rc = G.main(["--check"])
    check("second-card-cases.json (the desktop's and the phone's copy) equals a fresh run",
          rc == 0, "run python3 tools/gen_second_card_cases.py")
    data = json.loads(G.FIXTURE.read_text(encoding="utf-8"))["cases"]
    check("the six named cases are there",
          set(data) == {"one_card", "capable_off", "capable_pending", "running_long_context",
                        "card_missing_but_enabled", "not_capable_old_card"}, sorted(data))


def t_the_real_file():
    if missing("jarvis_hud.py"):
        return check("SKIP - no jarvis_hud.py here; the rehearsal above is the proof", True)
    s = (BACKEND / "jarvis_hud.py").read_text(encoding="utf-8")
    check("the backend's jarvis_hud.py has /api/second-card (second-card.patch applied)",
          '"/api/second-card"' in s)


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
