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
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
