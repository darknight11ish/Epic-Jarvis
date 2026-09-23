"""The connection handshake and the Brain's Compute pane, checked against the
field names the two clients actually read.

    python3 test_connection_contract.py

WHY THIS EXISTS. Three mismatches, each invisible because every client field
has a default (found by the 2026-09-23 audit):

1. The phone synced its face with the desktop only when `/api/version` listed
   an `appearance` capability (JarvisRuntime.refreshAppearance, pushAppearance).
   The rebuilt `jarvis_events.hello()` never listed one, so it never synced.
2. The desktop read `activity` and `capabilities.power.mode` / `set_by` from
   `/api/version` at connect time (stream.rs prime_from_version). hello() had
   no `activity` and `capabilities.power` was a bare `true` - so the desktop
   showed "active" through quiet hours until the mode next changed.
3. The desktop's Compute pane (brain.js renderCompute) read plan / gpu /
   vram_total_mb / gpu_layers / context / note. `jarvis_compute.Plan.as_dict()`
   sends none of those, so the pane always said "No compute plan reported."

So, in the manner of test_voice_contract.py, this runs the REAL producers -
the rebuilt jarvis_events.hello() and jarvis_compute.plan() - and checks their
output against the clients' OWN SOURCE: the Kotlin capability rule, the Rust
keys stream.rs reads, and the JS keys brain.js reads. A key renamed on either
side fails here.
"""
import json
import os
import re
import sys
import tempfile
import traceback
import types
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

# The rebuilt modules are the producers under test; first on the path.
sys.path.insert(0, str(HERE / "rebuilt"))
os.environ.setdefault("JARVIS_NO_EMBED", "1")
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", tempfile.mkdtemp(prefix="jarvis-contract-"))

import jarvis_events as EV  # noqa: E402
import jarvis_power as PW  # noqa: E402
import jarvis_compute as CO  # noqa: E402

CLIENT = REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client"
API_MODELS = CLIENT / "net" / "ApiModels.kt"
RUNTIME = CLIENT / "JarvisRuntime.kt"
STREAM_RS = REPO / "jarvis-desktop" / "src-tauri" / "src" / "stream.rs"
BRAIN_JS = REPO / "jarvis-desktop" / "src" / "brain.js"
APPEARANCE_PATCH = HERE / "appearance.patch"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def _block(src: str, start: str) -> str:
    """From `start` to the end of the brace block that opens after it."""
    i = src.index(start)
    j = src.index("{", i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError(f"unclosed block after {start!r}")


# ----------------------------------------------- the phone's capability rule --

def phone_capability_flag():
    """The phone's `asCapabilityFlag`, read from ApiModels.kt and turned into
    Python - so a change to that rule changes what this test expects."""
    src = _strip_comments(API_MODELS.read_text(encoding="utf-8"))
    fn = src[src.index("fun JsonElement.asCapabilityFlag()"):]
    fn = fn[:fn.index("\n}") + 2]
    obj_rule = re.search(r"is JsonObject -> (\w+)\(\)", fn)
    prim_rule = "booleanOrNull ?: (isString && content.isNotEmpty() && content != \"false\")" in fn
    if not (obj_rule and obj_rule.group(1) == "isNotEmpty" and prim_rule):
        raise AssertionError("ApiModels.kt asCapabilityFlag changed shape; update this test:\n" + fn)

    def flag(v):
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return bool(v) and v != "false"
        if isinstance(v, dict):
            return len(v) > 0
        return False
    return flag


def _with_hud(has_appearance: bool):
    """A `jarvis_hud` module in sys.modules, with or without the REAL
    `_appearance_view` lifted from appearance.patch's added lines."""
    mod = types.ModuleType("jarvis_hud")
    if has_appearance:
        added = [line[1:] for line in APPEARANCE_PATCH.read_text(encoding="utf-8").splitlines()
                 if line.startswith("+") and not line.startswith("+++")]
        text = "\n".join(added)
        start = text.index("def _appearance_view(")
        lines = text[start:].splitlines()
        body = [lines[0]]
        for line in lines[1:]:
            if line and not line[0].isspace():
                break
            body.append(line)
        exec("\n".join(body), mod.__dict__)
    return mock.patch.dict(sys.modules, {"jarvis_hud": mod})


def t_appearance_is_advertised_when_the_route_is_there():
    flag = phone_capability_flag()
    with _with_hud(True):
        caps = EV.hello("hud")["capabilities"]
    check("hello() lists `appearance` when appearance.patch is in the server",
          "appearance" in caps, sorted(caps))
    check("and the phone's can(\"appearance\") reads it as true",
          flag(caps.get("appearance")) is True, repr(caps.get("appearance")))
    with _with_hud(False):
        caps = EV.hello("hud")["capabilities"]
    check("CONTROL: without the route it is false, so the phone hides nothing it has",
          flag(caps.get("appearance")) is False, repr(caps.get("appearance")))
    # Every other capability the phone gates on still reads the same way.
    for name in ("approvals", "memory", "models", "skills", "power", "voice", "persona"):
        check(f"hello() still carries `{name}`", name in caps)


def t_the_phone_tries_the_route_when_the_flag_is_absent():
    src = _strip_comments(RUNTIME.read_text(encoding="utf-8"))
    refresh = _block(src, "suspend fun refreshAppearance()")
    push = _block(src, "suspend fun pushAppearance()")
    check("refreshAppearance no longer returns on the flag alone",
          "if (!can(\"appearance\")) return" not in refresh
          and "appearanceRoute == false" in refresh, refresh)
    check("a 404 is remembered as 'not on this server'",
          "ApiError.NotFound -> appearanceRoute = false" in src)
    check("pushAppearance asks first, without applying the reply",
          "noteAppearanceRoute(api.getAppearance())" in push
          and "applySyncDocument" not in push, push)


# -------------------------------------------- the desktop's connect-time read --

def desktop_prime_reads():
    """The keys stream.rs prime_from_version / power_mode / power_set_by read."""
    src = _strip_comments(STREAM_RS.read_text(encoding="utf-8"))
    prime = _block(src, "async fn prime_from_version(")
    mode = _block(src, "fn power_mode(")
    set_by = _block(src, "fn power_set_by(")
    return {
        "version_top": set(re.findall(r'version\["(\w+)"\]', prime)),
        "power_path": re.findall(r'version\["capabilities"\]\["power"\]', prime),
        "mode_keys": set(re.findall(r'value\["(\w+)"\]', mode)),
        "set_by_keys": set(re.findall(r'value\["(\w+)"\]', set_by)),
    }


def t_the_desktop_gets_activity_and_power_from_hello():
    reads = desktop_prime_reads()
    check("stream.rs reads activity and capabilities from /api/version",
          {"activity", "capabilities"} <= reads["version_top"], reads["version_top"])
    check("and the power block under capabilities.power", bool(reads["power_path"]))
    hello = EV.hello("hud")
    check("hello() carries a top-level `activity` string",
          isinstance(hello.get("activity"), str) and hello["activity"], repr(hello.get("activity")))
    power = hello["capabilities"]["power"]
    check("capabilities.power is jarvis_power.status(), not a bare flag",
          isinstance(power, dict), repr(power))
    if not isinstance(power, dict):
        return
    for key in reads["mode_keys"]:
        check(f"power_mode's key `{key}` is in the real power status", key in power, sorted(power))
    check("the mode is one jarvis_power knows", power.get("mode") in PW.MODES, power.get("mode"))
    # power_set_by derives "who set it" from these; set_by itself is optional.
    for key in reads["set_by_keys"] - {"set_by"}:
        check(f"power_set_by's key `{key}` is in the real power status", key in power, sorted(power))


def t_quiet_hours_reach_the_desktop_at_connect():
    with mock.patch.object(PW, "in_quiet_hours", return_value=True):
        power = EV.hello("hud")["capabilities"]["power"]
    check("inside quiet hours hello() says quiet, not active",
          isinstance(power, dict) and power.get("mode") == "quiet", repr(power))
    check("and says it is quiet hours, which the desktop shows as 'quiet hours'",
          isinstance(power, dict) and power.get("quiet_hours") is True)


# ------------------------------------------------------ the Compute pane --

def t_the_compute_pane_reads_what_the_plan_sends():
    fake = [CO.Device(0, "NVIDIA GeForce RTX 2080 SUPER", 8192, 1944),
            CO.Device(1, "NVIDIA GeForce RTX 2060", 12288, 11000)]
    with mock.patch.object(CO, "devices", return_value=fake):
        body = CO.plan("qwen3:8b").as_dict()
    js = _strip_comments(BRAIN_JS.read_text(encoding="utf-8"))
    fn = _block(js, "function renderCompute()")
    read = set(re.findall(r"body\.(\w+)", fn))
    device_read = set(re.findall(r"\bd\.(\w+)", fn))
    shown = {"text_model", "text_on", "vision_resident", "tts_resident", "prefer",
             "devices", "why", "simulated", "total_mb"}
    missing = shown - read
    check("renderCompute reads every field Plan.as_dict() sends", not missing,
          f"not read: {sorted(missing)}")
    check("every one of those is really in Plan.as_dict()", shown <= set(body),
          f"plan keys: {sorted(body)}")
    real_device = set(body["devices"][0])
    check("each device field the pane reads is in the real device rows",
          device_read <= real_device, f"reads {sorted(device_read)}, rows have {sorted(real_device)}")
    old_only = {"plan", "gpu", "vram_total_mb", "gpu_layers", "context", "note"} & set(body)
    check("CONTROL: the plan really does not send the old keys the pane used to rely on",
          not old_only, sorted(old_only))


if __name__ == "__main__":
    for fn in (t_appearance_is_advertised_when_the_route_is_there,
               t_the_phone_tries_the_route_when_the_flag_is_absent,
               t_the_desktop_gets_activity_and_power_from_hello,
               t_quiet_hours_reach_the_desktop_at_connect,
               t_the_compute_pane_reads_what_the_plan_sends):
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
