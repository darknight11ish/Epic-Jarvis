"""The named-lane starter the preset apply route uses, and the pin that keeps a
preset and the lane that really serves it from drifting apart.
"""
import dataclasses
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_model_lanes as L  # noqa: E402
import jarvis_presets as P  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name + (f"\n        {detail}" if detail and not cond else ""))



def t_every_preset_lane_maps_to_a_real_model_lane():
    import jarvis_presets as P
    real = L.start_lane
    seen = []
    try:
        L.start_lane = lambda key: (seen.append(key), (200, {"ok": True, "changed": False}))[1]
        for preset in P.PRESETS:
            if preset.heavy_mode:
                continue  # heavy mode has no single-card lane to start
            mapped = P.LANE_START_KEYS[preset.lane]
            check(f"{preset.id}: lane {preset.lane!r} maps to the starter's {mapped!r}",
                  mapped in {lane.key for lane in L.LANES}
                  and L.lane_by_key(mapped) is not None,
                  (preset.lane, mapped, [lane.key for lane in L.LANES]))
        code, body = P._default_start_lane("main")
        check("... and the DEFAULT start path passes 'everyday', never a fake 'main'",
              code == 200 and seen == ["everyday"] and L.lane_by_key("main") is None,
              (code, seen))
        code, body = P._default_start_lane("coding")
        check("... and 'coding' passes straight through", code == 200 and seen[-1] == "coding", seen)
        code, body = P._default_start_lane("not-a-lane")
        check("... an unknown lane is refused, not guessed", code == 409, body)
    finally:
        L.start_lane = real

def _lane_disagreements(presets, lanes, big):
    """Every way a preset's lane/model can disagree with the lane table that
    really pauses and restores those lanes (`jarvis_big_coder.LANES`).

    Returns plain sentences; an empty list means the two agree. The two sides
    are ARGUMENTS so the check below can prove it catches a moved preset - a
    comparison that can never report anything would pass for the wrong reason.
    """
    problems = []
    by_port = {int(lane.port): lane for lane in lanes}
    used_ports = set()
    for p in presets:
        info = P.LANES.get(p.lane)
        if info is None:
            problems.append(f"{p.id}: lane {p.lane!r} is not a key of "
                            f"jarvis_presets.LANES")
            continue
        port = int(info.get("port") or 0)
        if p.lane == "pooled":
            if port != int(big.BIG_PORT):
                problems.append(f"{p.id}: the pooled lane's port {port} is not "
                                f"jarvis_big_coder.BIG_PORT {big.BIG_PORT}")
            used_ports.add(port)
            continue
        lane = by_port.get(port)
        if lane is None:
            problems.append(f"{p.id}: lane {p.lane!r} is port {port}, and "
                            f"jarvis_big_coder has no lane on that port (it pauses "
                            f"and restores {sorted(by_port)})")
            continue
        used_ports.add(port)
        # "general" is the preset that names the everyday lane's OWN resident
        # model, so it is the one that must match the lane exactly. A preset
        # that applies a different model to the same lane (Fast, Agentic) is
        # allowed to, and the lane is what carries it.
        if p.id == "general" and (p.model != lane.model or p.context != lane.ctx):
            problems.append(f"general: names {p.model} at {p.context}, but the lane "
                            f"on port {port} holds {lane.model} at {lane.ctx}")
    for lane in lanes:
        if int(lane.port) not in used_ports:
            problems.append(f"jarvis_big_coder lane {lane.port} ({lane.model}) is "
                            f"named by no preset")
    return problems


def t_every_preset_agrees_with_the_lane_that_serves_it():
    """2026-11-18: a preset may not move without the lane moving with it.

    The owner's decision is "each preset should be dedicated to one preset
    local ai model", and the everyday model is `gemma4:26b-a4b-it-qat` at a
    32,768-token window on the ONE everyday lane. `jarvis_big_coder.LANES` is the
    table that really pauses and restores that lane (port 11436), so it is the
    authority here: this test fails when a preset's `lane`/`model` and that
    table disagree in EITHER direction - a preset moved onto a lane the
    big-coder does not know, a lane the big-coder restores that no preset
    names, or the everyday preset's model/window changed without the lane (or
    the other way round).
    """
    import jarvis_big_coder as BC
    problems = _lane_disagreements(P.PRESETS, BC.LANES, BC)
    check("every preset's lane/model agrees with jarvis_big_coder.LANES",
          not problems, problems)
    check("... the everyday lane is the ONE lane big-coder pauses and restores",
          len(BC.LANES) == 1 and BC.LANES[0].port == P.LANES["main"]["port"],
          BC.LANES)
    check("... and the pooled lane is the big-coder's own server port",
          P.LANES["pooled"]["port"] == BC.BIG_PORT,
          (P.LANES["pooled"], BC.BIG_PORT))
    check("... and no preset names a second (helper) model",
          all(not p.helper_model for p in P.PRESETS),
          [p.id for p in P.PRESETS if p.helper_model])

    # PROOF THE CHECK HAS TEETH - the three drifts this test exists for must be
    # CAUGHT by the same function, not merely not-present today.
    gen = P.by_id("general")
    moved_model = dataclasses.replace(gen, model="qwen3.5:9b")
    check("... a preset whose model moved without the lane is CAUGHT",
          bool(_lane_disagreements([moved_model], BC.LANES, BC)),
          _lane_disagreements([moved_model], BC.LANES, BC))
    moved_window = dataclasses.replace(gen, context=196608)
    check("... a preset whose window moved without the lane is CAUGHT",
          bool(_lane_disagreements([moved_window], BC.LANES, BC)),
          _lane_disagreements([moved_window], BC.LANES, BC))
    moved_lane = dataclasses.replace(gen, lane="coding")
    check("... a preset moved onto the retired coding lane is CAUGHT",
          bool(_lane_disagreements([moved_lane], BC.LANES, BC)),
          _lane_disagreements([moved_lane], BC.LANES, BC))
    second_lane = BC.LANES[0]._replace(port=11435, model="qwen3:8b", ctx=16384)
    check("... a second lane no preset names is CAUGHT",
          bool(_lane_disagreements(P.PRESETS, list(BC.LANES) + [second_lane], BC)),
          _lane_disagreements(P.PRESETS, list(BC.LANES) + [second_lane], BC))


def main() -> int:
    check("the lane table is everyday :11436 and coding :11435",
          L.lane_by_key("everyday").port == 11436 and L.lane_by_key("coding").port == 11435)
    check("the owner's task names are stated for the card words",
          L.LANE_TASKS["everyday"] == "Jarvis Ollama - Everyday model (RTX 2060)"
          and L.LANE_TASKS["coding"] == "Jarvis Ollama - Coding model (RTX 2080 Super)")
    check("the matcher keeps using the stable task prefix, not the full name",
          L.lane_by_key("everyday").task_prefix == "Jarvis Ollama - Everyday model"
          and L.lane_by_key("coding").task_prefix == "Jarvis Ollama - Coding model")
    code, body = L.start_lane("coding", probe_fn=lambda lane: True)
    check("a lane that already answers starts nothing (200, changed false)",
          code == 200 and body.get("changed") is False and True,
          (code, body))
    code, body = L.start_lane("nope", probe_fn=lambda lane: True)
    check("an unknown lane key is refused, never guessed", code == 409 and "no lane called" in body.get("reason", ""), body)
    check("the old single default target still resolves from the chat URL",
          L.target(url="http://127.0.0.1:11436").key == "everyday")
    t_every_preset_lane_maps_to_a_real_model_lane()
    t_every_preset_agrees_with_the_lane_that_serves_it()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
