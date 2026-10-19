"""The named-lane starter the preset apply route uses (no HUD changes yet)."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_model_lanes as L  # noqa: E402

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
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
