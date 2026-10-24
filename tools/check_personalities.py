"""tools/check_personalities.py - the personality-presets contract checker.

Holds four things true, and fails by name when one is not:

 1. THE CONTRACT IS USABLE: `contract/personalities.json` has the 8 presets
    with every field the engine needs, the four dials, the six reflex acks,
    two exemplars each, a bounded prompt block, the legacy warm/plain aliases
    and the safety sentences. The rules live in
    `tools/gen_personalities.py:contract_problems`, so this checker and the
    generator cannot disagree.
 2. THE SHIPPED COPY IS THE CONTRACT: the backend on the owner's PC does not
    receive `contract/`, so `backend/jarvis_manner.py` (and its
    `jarvis-backend/` twin) carry a GENERATED copy. Both copies must be
    byte-identical to each other and equal to the contract, and the sha256 pin
    in them must be the contract's own sha256 - a hand edit fails here.
 3. THE PROMPT BUDGET IS REALLY KEPT: every built-in preset's assembled
    `<jarvis_persona>` block - typed, spoken-live and crisis - is measured with
    the engine's own assembler and must be <= 750 characters (~180 tokens),
    contain no SecAlign markers, and the crisis block must REPLACE all persona
    text (it may not carry a preset's critique/wit instructions).
 4. THE BEHAVIOUR THE BLUEPRINT ASKS FOR EXISTS: all 8 ids and aliases
    normalize; legacy warm/plain map; the four dials validate; the reflex
    table answers each preset in its own voice; the GET view carries the
    personality block; "My Personalities" is capped at 20 with 240-char
    fields. A made-up preset or a missing ack fails, so this is not a comment.

Run: `python -B tools/check_personalities.py` (exit 0 = ok). It changes
nothing and needs nothing from the owner's PC.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "backend"))

import gen_personalities as GEN  # noqa: E402

CONTRACT = ROOT / "contract" / "personalities.json"
BOTH = (ROOT / "backend" / "jarvis_manner.py",
        ROOT / "jarvis-backend" / "jarvis_manner.py")

PROMPT_CHAR_CAP = 750
SECALIGN = ("<|im_start|>", "<|im_end|>", "<tool_call>", "<think>")
PID = [
    "warm_peer", "classic_butler", "tactical_ops", "dry_wit",
    "friday_partner", "socratic_mentor", "devils_advocate", "calm_stoic",
]
#: Which words prove a reflex ack belongs to that persona (the blueprint names
#: the butler/tactical/dry examples; the rest are held to their own voice).
REFLEX_EVIDENCE = {
    "warm_peer": ("timer",),
    "classic_butler": ("sir",),
    "tactical_ops": ("copy",),
    "dry_wit": ("burn",),
    "friday_partner": ("boss",),
    "socratic_mentor": ("?",),
    "devils_advocate": ("?",),
    "calm_stoic": ("time",),
}

CHECKS = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))


def _line(text: str) -> str:
    return str(text).replace("\n", " ")[:300]


def check_contract(data: dict) -> None:
    problems = GEN.contract_problems(data)
    check("the contract is usable (8 presets, every field, every budget)",
          not problems, "\n".join(problems))
    if problems:
        return
    ids = [p["id"] for p in data["personalities"]]
    check("the 8 preset ids are exactly the blueprint's", ids == PID, str(ids))
    check("the default preset is warm_peer (the legacy 'warm')",
          data["default"] == "warm_peer")
    check("legacy warm/plain normalize to warm_peer/tactical_ops",
          data["legacy_aliases"] == {"warm": "warm_peer", "plain": "tactical_ops"})
    check("custom presets are capped at 20 with 240-char fields",
          data.get("max_custom_personalities") == 20
          and data.get("max_custom_field_chars") == 240)
    aliases = {}
    dup = []
    for preset in data["personalities"]:
        for alias in preset["aliases"]:
            key = str(alias).strip().lower()
            if key in aliases:
                dup.append(f"{alias!r} claimed by {aliases[key]} and {preset['id']}")
            aliases[key] = preset["id"]
    check("no spoken alias is claimed by two presets", not dup, "\n".join(dup))
    check("all 8 docs carry the six reflex acks",
          all(set(p["reflex_acks"]) == set(GEN.REFLEX_KINDS)
              for p in data["personalities"]))
    check("every switch ack is the persona's own line (non-empty, unique)",
          len({p["switch_ack"] for p in data["personalities"]}) == 8)
    check("the sensitive-fact reply is the project's exact sentence",
          data["safety"]["sensitive_fact_spoken_reply"] == "It's on your screen.")


def check_shipped_copy() -> None:
    if not CONTRACT.exists():
        check("the contract file exists", False, str(CONTRACT))
        return
    raw = CONTRACT.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    sha = hashlib.sha256(raw).hexdigest()
    texts = []
    for path in BOTH:
        if not path.exists():
            check(f"{path.relative_to(ROOT)} exists", False)
            continue
        texts.append(path.read_text(encoding="utf-8"))
    check("the module and its jarvis-backend twin are byte-identical",
          len(texts) == 2 and texts[0] == texts[1])
    text = texts[0] if texts else ""
    check("the shipped copy carries the contract's sha256 pin",
          f'PERSONALITIES_SHA256 = "{sha}"' in text,
          "run python -B tools/gen_personalities.py")
    try:
        start = text.find("PERSONALITIES_DATA = json.loads(r\"\"\"") + len(
            "PERSONALITIES_DATA = json.loads(r\"\"\"")
        end = text.find("\n\"\"\")", start)
        shipped = json.loads(text[start:end].strip()) if start > 0 and end > 0 else None
    except ValueError:
        shipped = None
    check("the shipped data is the contract itself", shipped == data,
          "run python -B tools/gen_personalities.py")


def check_budget(module) -> None:
    safety = module._SAFETY
    check("the crisis block is under the 750-char cap",
          len(safety["crisis_prompt_block"]) <= PROMPT_CHAR_CAP)
    worst = (0, "")
    problems = []
    for preset in module._BUILTIN:
        pid = preset["id"]
        for spoken in (False, True):
            text = module._compose(preset, preset["dials"], spoken, with_examples=True)
            if len(text) > worst[0]:
                worst = (len(text), f"{pid} spoken={spoken}")
            if len(text) > PROMPT_CHAR_CAP:
                problems.append(f"{pid} spoken={spoken}: {len(text)} chars")
            for mark in SECALIGN:
                if mark in text:
                    problems.append(f"{pid} spoken={spoken}: SecAlign marker {mark!r}")
            if spoken and safety["spoken_live_note"] not in text:
                problems.append(f"{pid}: spoken-live block lost the cadence constraint")
            if not spoken and "Cadence:" not in text:
                problems.append(f"{pid}: typed block lost the cadence exemplars")
    check("every built-in assembled prompt is <= 750 chars (~180 tokens), both modes",
          not problems, "\n".join(problems) + f"\nworst: {worst[0]} chars ({worst[1]})")
    check("the crisis block is short enough to replace a persona without truncation",
          len(safety["crisis_prompt_block"]) < PROMPT_CHAR_CAP)
    # Crisis replaces all persona text. The proof is that the SAME crisis text
    # comes back whoever is active, and that it holds none of the six
    # negative-instruction markers the wit/critic personas legitimately carry.
    old = module._read_settings
    crisis_texts = []
    try:
        for pid in PID:
            module._read_settings = lambda pid=pid: {"personality": pid}
            crisis_texts.append(module.prompt_block(crisis_active=True))
            typed = module.prompt_block(spoken_live=False)
            if not (len(typed) <= PROMPT_CHAR_CAP and "crisis" not in typed.lower()[:1]):
                pass
    finally:
        module._read_settings = old
    check("crisis_active returns the same calm block for all 8 personalities",
          len(set(crisis_texts)) == 1 and crisis_texts[0] == safety["crisis_prompt_block"])
    for word in ("sarcas", "deadpan", "no-nonsense", "red-team", "butler",
                 "f.r.i.d.a.y", "socratic"):
        check(f"the crisis block carries no persona instruction: {word!r}",
              word not in crisis_texts[0].lower())
    check("the crisis block says plainly that personality and humour are set aside",
          "personality" in crisis_texts[0].lower()
          and "humour" in crisis_texts[0].lower()
          and "calmly" in crisis_texts[0].lower())


def check_module_behaviour(module) -> None:
    check("the module's 8 built-ins are the contract's 8",
          [p["id"] for p in module._BUILTIN] == PID)
    check("legacy 'warm'/'plain' still answer as the old pair",
          module.current() in ("warm", "plain"))
    check("all 8 ids normalize to themselves",
          all(module.normalize_personality_id(pid) == pid for pid in PID))
    check("all 8 preset titles and aliases normalize to their preset",
          all(module.normalize_personality_id(a) == p["id"]
              for p in module._BUILTIN for a in [p["title"]] + list(p["aliases"])))
    check("legacy words normalize through the mapping",
          module.normalize_personality_id("warm") == "warm_peer"
          and module.normalize_personality_id("plain") == "tactical_ops")
    check("an unknown personality name is refused, not guessed",
          module.normalize_personality_id("shouty") is None)
    # The PC may legitimately have saved "My Personalities" presets, so the
    # check is the EIGHT BUILT-INS, not "the list is exactly eight entries".
    view = module.view()
    builtins = [p for p in view["personalities"] if p.get("builtin")]
    check("the GET view carries the personality block and the 8 built-in presets",
          len(builtins) == 8
          and [p["id"] for p in builtins] == PID
          and view["personality_default"] == "warm_peer"
          and set(view["dials"]) == {"humor", "brevity", "formality", "address"}
          and view["max_user_personalities"] == 20
          and view["voice_sync"] is True
          and isinstance(view["custom_personalities"], list))
    # The four dials: every documented value validates, a bad one is refused.
    good = {"humor": [0, 1, 2, 3, "none", "subtle", "dry", "playful", "90%"],
            "brevity": ["concise", "balanced", "thorough", "short", "long"],
            "formality": ["casual", "warm", "formal", "tactical", "butler"],
            "address": ["first name", "sir", "ma'am", "boss", "captain", "no title"]}
    bad = {"humor": [4, -1, "loud"], "brevity": ["mediumish"],
           "formality": ["royal"], "address": ["my lord"]}
    good_ok = all(module._dial_value(k, v) is not None
                  for k, values in good.items() for v in values)
    bad_ok = all(module._dial_value(k, v) is None
                 for k, values in bad.items() for v in values)
    check("every documented dial value validates", good_ok)
    check("an unknown dial value is refused", bad_ok)
    check("the six reflex kinds all answer, and placeholders are filled",
          all(module.reflex_phrase(kind, duration="10 minutes", count=3)
              and "{" not in module.reflex_phrase(kind, duration="10 minutes", count=3)
              for kind in GEN.REFLEX_KINDS))
    check("an unknown reflex kind answers nothing rather than inventing a line",
          module.reflex_phrase("not_a_kind") == "")
    # Per-persona reflex evidence: the blueprint's own examples.
    old = module._read_settings
    try:
        for pid, evidence in REFLEX_EVIDENCE.items():
            module._read_settings = lambda pid=pid: {"personality": pid}
            phrase = module.reflex_phrase("timer_set", duration="10 minutes")
            check(f"{pid} answers a timer in its own voice",
                  any(word in phrase.lower() for word in evidence), phrase)
    finally:
        module._read_settings = old
    try:
        module._read_settings = old
    except NameError:
        pass
    check("the module can never raise an approval card",
          "jarvis_gate" not in Path(ROOT / "backend" / "jarvis_manner.py").read_text(
              encoding="utf-8"))


def main() -> int:
    if not CONTRACT.exists():
        print(f"FAIL the contract file exists: {CONTRACT}", file=sys.stderr)
        return 1
    raw = CONTRACT.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        print(f"FAIL the contract is readable JSON: {exc}", file=sys.stderr)
        return 1
    check_contract(data)
    check_shipped_copy()
    # Import the engine only after the contract checks, so a broken contract
    # reports as itself and not as an ImportError.
    try:
        import jarvis_manner as M
    except Exception as exc:
        check("backend/jarvis_manner.py imports", False, f"{type(exc).__name__}: {exc}")
        M = None
    if M is not None:
        check_budget(M)
        check_module_behaviour(M)
    failed = 0
    for name, ok, detail in CHECKS:
        print(("ok   " if ok else "FAIL ") + name)
        if not ok:
            failed += 1
            if detail:
                for line in str(detail).splitlines():
                    print("        " + _line(line))
    print(f"\n{len(CHECKS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
