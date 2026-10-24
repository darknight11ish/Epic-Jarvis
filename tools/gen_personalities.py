"""tools/gen_personalities.py - write the personality data the engine ships with.

`contract/personalities.json` is the source of truth (the 9 presets, the dials,
the safety sentences). The Python backend on the owner's PC does NOT receive
`contract/` - only the `backend/` modules are shipped - so `jarvis_manner.py`
carries a GENERATED copy of that contract, between two markers:

    # ---- BEGIN GENERATED PERSONALITY DATA (do not edit by hand) ----
    ...
    # ---- END GENERATED PERSONALITY DATA ----

This tool reads the contract, checks it, and rewrites that block in BOTH the
module and its `jarvis-backend/` twin (they are kept byte-identical). With
`--check` it changes nothing and exits 1 if either copy is stale, naming the
file - the same shape as the repo's other generators.

    python -B tools/gen_personalities.py            # write both copies
    python -B tools/gen_personalities.py --check    # prove both are current
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONTRACT = ROOT / "contract" / "personalities.json"

BOTH = (
    ROOT / "backend" / "jarvis_manner.py",
    ROOT / "jarvis-backend" / "jarvis_manner.py",
)

BEGIN = "# ---- BEGIN GENERATED PERSONALITY DATA (do not edit by hand) ----"
END = "# ---- END GENERATED PERSONALITY DATA ----"

REQUIRED_KEYS = (
    "id", "title", "description", "aliases", "prompt_block", "examples",
    "post_history_hint", "dials", "voice_blend", "voice_fallback",
    "voice_speed", "greeting_subtitle", "switch_ack", "reflex_acks",
)
REFLEX_KINDS = ("timer_set", "reminder_saved", "done", "stopped", "muted", "walk_queued")
SECALIGN = ("<|im_start|>", "<|im_end|>", "<tool_call>", "<think>")
DIAL_SPECS = {
    "humor": {"type": "int", "min": 0, "max": 3},
    "brevity": {"type": "enum", "values": ["concise", "balanced", "thorough"]},
    "formality": {"type": "enum",
                  "values": ["casual", "warm_peer", "formal_butler", "tactical"]},
    "address": {"type": "enum",
                "values": ["first_name", "sir", "ma'am", "boss", "captain", "none"]},
}


def fail(message: str) -> None:
    print(f"gen_personalities: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_contract() -> tuple:
    if not CONTRACT.exists():
        fail(f"{CONTRACT.relative_to(ROOT)} is missing - it is the source of truth "
             "for the personality presets.")
    raw = CONTRACT.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        fail(f"{CONTRACT.relative_to(ROOT)} is not readable JSON ({exc})")
    problems = contract_problems(data)
    if problems:
        fail("the contract is not usable:\n  " + "\n  ".join(problems))
    return data, raw


def contract_problems(data: dict) -> list:
    """Everything wrong with `data` as the personality contract, by name.

    Shared with `tools/check_personalities.py` (which also holds it to the
    shipped copy), so the generator and the checker cannot disagree about what
    a usable contract is."""
    bad = []
    if not isinstance(data, dict):
        return ["the contract is not an object"]
    if data.get("schema") != 1:
        bad.append(f"schema is {data.get('schema')!r}, expected 1")
    presets = data.get("personalities")
    if not isinstance(presets, list):
        return bad + ["personalities is not a list"]
    if len(presets) != 9:
        bad.append(f"expected 9 built-in presets, found {len(presets)}")
    ids, aliases = [], []
    for row in presets:
        if not isinstance(row, dict):
            bad.append("a preset is not an object")
            continue
        pid = row.get("id")
        if not isinstance(pid, str) or not pid:
            bad.append("a preset has no id")
            continue
        ids.append(pid)
        for key in REQUIRED_KEYS:
            if key not in row:
                bad.append(f"{pid}: missing {key}")
        text = str(row.get("prompt_block") or "")
        if not text.strip():
            bad.append(f"{pid}: empty prompt_block")
        if len(text) > 750:
            bad.append(f"{pid}: prompt_block is {len(text)} chars (the hard ceiling is 750)")
        for mark in SECALIGN:
            if mark in text:
                bad.append(f"{pid}: prompt_block contains the SecAlign marker {mark!r}")
        examples = row.get("examples")
        if not isinstance(examples, list) or len(examples) != 2:
            bad.append(f"{pid}: needs exactly 2 cadence exemplars")
        else:
            for i, ex in enumerate(examples):
                if (not isinstance(ex, dict) or not str(ex.get("user") or "").strip()
                        or not str(ex.get("jarvis") or "").strip()):
                    bad.append(f"{pid}: exemplar {i + 1} needs a non-empty user and jarvis line")
        hint = str(row.get("post_history_hint") or "")
        if not hint.strip():
            bad.append(f"{pid}: no post_history_hint")
        if len(hint) > 220:
            bad.append(f"{pid}: post_history_hint is {len(hint)} chars (cap 220)")
        dials = row.get("dials")
        if not isinstance(dials, dict) or set(dials) != set(DIAL_SPECS):
            bad.append(f"{pid}: dials must carry exactly {sorted(DIAL_SPECS)}")
        else:
            for name, spec in DIAL_SPECS.items():
                value = dials[name]
                if spec["type"] == "int":
                    if not (isinstance(value, int) and not isinstance(value, bool)
                            and spec["min"] <= value <= spec["max"]):
                        bad.append(f"{pid}: dial {name}={value!r} is not {spec['min']}..{spec['max']}")
                elif value not in spec["values"]:
                    bad.append(f"{pid}: dial {name}={value!r} is not one of {spec['values']}")
        for key in ("title", "description", "voice_blend", "voice_fallback",
                    "greeting_subtitle", "switch_ack"):
            if not str(row.get(key) or "").strip():
                bad.append(f"{pid}: no {key}")
        speed = row.get("voice_speed")
        if not (isinstance(speed, (int, float)) and not isinstance(speed, bool)
                and 0.5 <= float(speed) <= 1.5):
            bad.append(f"{pid}: voice_speed={speed!r} is outside 0.5..1.5")
        acks = row.get("reflex_acks")
        if not isinstance(acks, dict) or set(acks) != set(REFLEX_KINDS):
            bad.append(f"{pid}: reflex_acks must carry exactly {list(REFLEX_KINDS)}")
        elif not all(str(acks.get(k) or "").strip() for k in REFLEX_KINDS):
            bad.append(f"{pid}: a reflex ack is empty")
        row_aliases = row.get("aliases")
        if not isinstance(row_aliases, list):
            bad.append(f"{pid}: aliases is not a list")
        else:
            aliases.extend(str(a).strip().lower() for a in row_aliases if str(a).strip())
    if len(set(ids)) != len(ids):
        bad.append("a preset id is used twice")
    if len(set(aliases)) != len(aliases):
        bad.append("an alias is claimed by two presets")
    legacy = data.get("legacy_aliases")
    if not isinstance(legacy, dict) or legacy.get("warm") != "warm_peer" \
            or legacy.get("plain") != "tactical_ops":
        bad.append("legacy_aliases must map warm->warm_peer and plain->tactical_ops")
    default = data.get("default")
    if default not in ids:
        bad.append(f"default {default!r} is not a preset id")
    safety = data.get("safety")
    if not isinstance(safety, dict):
        bad.append("no safety block")
    else:
        for key in ("crisis_prompt_block", "spoken_live_note", "sensitive_fact_spoken_reply"):
            if not str(safety.get(key) or "").strip():
                bad.append(f"safety: no {key}")
        if len(str(safety.get("crisis_prompt_block") or "")) > 750:
            bad.append("safety: crisis_prompt_block is over the 750-char ceiling")
    return bad


def render_block(data: dict, raw: bytes) -> str:
    pretty = json.dumps(data, indent=2, ensure_ascii=False)
    sha = hashlib.sha256(raw).hexdigest()
    return (f"{BEGIN}\n"
            f"PERSONALITIES_SHA256 = \"{sha}\"\n"
            "PERSONALITIES_DATA = json.loads(r\"\"\"\n"
            f"{pretty}\n"
            "\"\"\")\n"
            f"{END}\n")


def replace_region(text: str, block: str, path: Path) -> str:
    start = text.find(BEGIN)
    end = text.find(END)
    if start < 0 or end < 0 or end < start:
        fail(f"{path.relative_to(ROOT)} has no generated-personality-data markers")
    return text[:start] + block + text[end + len(END) + 1:]


def main(argv: list) -> int:
    check = "--check" in argv
    data, raw = read_contract()
    block = render_block(data, raw)
    stale = []
    for path in BOTH:
        if not path.exists():
            fail(f"{path.relative_to(ROOT)} is missing")
        text = path.read_text(encoding="utf-8")
        want = replace_region(text, block, path)
        if check:
            if want != text:
                stale.append(path.relative_to(ROOT))
        else:
            path.write_text(want, encoding="utf-8", newline="\n")
            print(f"wrote the generated personality data into {path.relative_to(ROOT)}")
    if check:
        if stale:
            print("STALE " + ", ".join(str(p) for p in stale)
                  + " - run python -B tools/gen_personalities.py", file=sys.stderr)
            return 1
        print(f"personalities: both module copies match {CONTRACT.relative_to(ROOT)} "
              f"({len(data['personalities'])} presets, sha256 {hashlib.sha256(raw).hexdigest()[:12]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
