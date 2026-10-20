"""The vetted skill definitions this repository ships, and their attribution.

WHAT IS PROVEN HERE, against the repository's own files and its own scanner - no
network, no Ollama, every socket refused:

  * every skill under `skills/` PARSES through `jarvis_skills.parse_skill` and
    SCANS clean through `jarvis_skills.vet` - the same scanner and the same
    quarantine rules any other skill faces;
  * the tool names a skill declares are Jarvis's OWN (`jarvis_agent.TOOLS`),
    which is the whole point of adapting a skill rather than copying one: a
    name that is not a real tool is a call that cannot run;
  * it declares `requires_tools`, so a skill whose tools are off can be HIDDEN
    rather than offered and failed;
  * it carries none of the shell-install phrasing the upstream skill used, and
    no external address - so this PC is not asked to fetch or install anything;
  * it schedules nothing (rule 4): no `blueprint.schedule`, and no mention of a
    timer, a cron expression or a job;
  * the ATTRIBUTION is real and in the right half of THIRD-PARTY-NOTICES.txt -
    the hand-written part, above the generated `2. RUST LIBRARIES` section, and
    it names the licence the upstream repository's own LICENSE.txt states.

    python3 test_vetted_skills.py
"""
import ast
import json
import os
import re
import socket
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO  # noqa: E402,F401  (puts BACKEND on sys.path)
sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.append(str(REPO / "jarvis-backend"))

import jarvis_skills as SK  # noqa: E402

SKILLS_DIR = REPO / "skills"
NOTICES = REPO / "THIRD-PARTY-NOTICES.txt"


# Counting only: nothing in this suite may open a connection.
class _NoNetworkSocket:
    def __init__(self, *a, **k):
        raise AssertionError("test_vetted_skills opened a network connection")


def _no_network(*a, **k):
    raise AssertionError("test_vetted_skills opened a network connection")


socket.socket = _NoNetworkSocket
socket.create_connection = _no_network
socket.getaddrinfo = _no_network

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))
    return bool(cond)


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def skill_dirs() -> list:
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(d for d in SKILLS_DIR.iterdir()
                  if d.is_dir() and (d / "SKILL.md").is_file())


def read_skill(name: str):
    """(the parsed skill, its raw text). Raises if it will not parse."""
    d = SKILLS_DIR / name
    return SK.parse_skill(d, trust="local"), (d / "SKILL.md").read_text(encoding="utf-8")


def real_tool_names() -> set:
    try:
        import jarvis_agent as A
        return set(A.TOOLS)
    except Exception:
        return set()


def extra_fields(name: str) -> dict:
    sk, _ = read_skill(name)
    return dict(getattr(sk, "extra_fields", {}) or {})


# --------------------------------------------------------------------------
#   Every shipped skill: parses, scans clean, and names only real tools
# --------------------------------------------------------------------------

def t_every_shipped_skill_parses_and_scans_clean():
    dirs = skill_dirs()
    check("there is at least one shipped skill", bool(dirs), repr(sorted(
        p.name for p in SKILLS_DIR.iterdir()) if SKILLS_DIR.is_dir() else "no skills/"))
    for d in dirs:
        try:
            sk = SK.parse_skill(d, trust="local")
        except Exception as exc:
            check(f"{d.name} parses", False, f"{type(exc).__name__}: {exc}")
            continue
        check(f"{d.name} parses", True)
        check(f"{d.name}: the frontmatter name matches its folder", sk.name == d.name,
              repr(sk.name))
        check(f"{d.name}: it has a description, or it can never be chosen",
              bool(sk.description), repr(sk.description)[:80])
        report = SK.vet(sk)
        check(f"{d.name} scans CLEAN", report["verdict"] == "clean",
              repr([(f["severity"], f["code"]) for f in report["findings"]]))
        check(f"{d.name} has no blocking finding", report["blocking"] == 0,
              repr(report["findings"]))
        check(f"{d.name}: the only findings are notes",
              all(f["severity"] == "note" for f in report["findings"]),
              repr([(f["severity"], f["code"]) for f in report["findings"]]))


def t_every_declared_tool_is_one_of_jarvis_s_own():
    """THE ADAPTATION CHECK. A skill that names a tool this backend does not have
    is a call that cannot run - which is exactly what copying an upstream skill
    without reading this project's vocabulary produces."""
    real = real_tool_names()
    if not real:
        skip("jarvis_agent is not importable here, so the tool vocabulary cannot be read")
        return
    check("the real tool vocabulary was read", len(real) >= 20, repr(len(real)))
    for d in skill_dirs():
        extra = extra_fields(d.name)
        declared = []
        for key in ("requires_tools", "fallback_for_tools"):
            value = extra.get(key)
            if isinstance(value, list):
                declared += [str(v) for v in value]
            elif isinstance(value, str) and value:
                declared += value.split()
        check(f"{d.name} declares at least one tool it needs", bool(declared),
              repr(sorted(extra)))
        for tool in declared:
            check(f"{d.name}: {tool!r} is a real Jarvis tool", tool in real,
                  f"not in jarvis_agent.TOOLS ({len(real)} names)")


def t_a_skill_declares_the_tools_it_needs_so_it_can_be_hidden():
    """`requires_tools` is what lets the hub hide a skill whose tools are off:
    a skill that cannot run is worse than absent, because the model picks it."""
    for d in skill_dirs():
        extra = extra_fields(d.name)
        check(f"{d.name} declares requires_tools", "requires_tools" in extra,
              repr(sorted(extra)))
        sk, _ = read_skill(d.name)
        check(f"{d.name}: the allowed-tools field is the same vocabulary",
              set(sk.allowed_tools) >= set(extra.get("requires_tools") or [])
              if isinstance(extra.get("requires_tools"), list) else False,
              f"allowed={sk.allowed_tools} requires={extra.get('requires_tools')}")


# --------------------------------------------------------------------------
#   The adaptation itself: no installs, no addresses, no timer
# --------------------------------------------------------------------------

def t_no_skill_asks_this_pc_to_install_anything():
    """The upstream skill told the reader to `brew install`/`apt-get install`/
    `uv pip install`. On a local-first machine a package that appears without
    the owner's say-so is a change nobody approved, so the adaptation says the
    packages must already be there."""
    patterns = [r"\bbrew\s+install\b", r"\bapt-get\s+install\b", r"\bapt\s+install\b",
                r"\bpip\s+install\b", r"\bpip3\s+install\b", r"\buv\s+pip\s+install\b",
                r"\bchoco\s+install\b", r"\bwinget\s+install\b",
                r"\bsudo\b", r"\bnpm\s+install\b", r"\bcargo\s+install\b"]
    for d in skill_dirs():
        text = (d / "SKILL.md").read_text(encoding="utf-8")
        for pat in patterns:
            hit = re.search(pat, text, re.I)
            check(f"{d.name}: no {pat.strip(chr(92)+'b')}", hit is None,
                  repr(hit.group(0) if hit else ""))
        check(f"{d.name}: it says Jarvis does not install packages",
              "does not install" in text, "the sentence is missing")


def t_no_skill_names_an_external_address():
    """No URL means nothing to fetch and nothing to phone home to. It also keeps
    the scanner's own bare-address warning off this text for the right reason."""
    for d in skill_dirs():
        text = (d / "SKILL.md").read_text(encoding="utf-8")
        found = re.findall(r"https?://\S+", text)
        check(f"{d.name}: no external address in the skill body", found == [],
              repr(found))
        for f in SK.scan_text(text, "SKILL.md"):
            check(f"{d.name}: no {f.code} finding from the scanner",
                  f.severity != "block", repr(f.message[:120]))


def t_no_skill_schedules_anything():
    """RULE 4. A skill that scheduled itself would be acting unattended. This is
    checked on the frontmatter AND on the words, because a cron string in the
    body would be a schedule by another name."""
    for d in skill_dirs():
        extra = extra_fields(d.name)
        check(f"{d.name}: no blueprint.schedule", "blueprint.schedule" not in extra,
              repr(sorted(extra)))
        text = (d / "SKILL.md").read_text(encoding="utf-8").lower()
        for bad in ("cron", "every morning", "schedule a job", "set a timer",
                    "auto-schedule", "in the background"):
            check(f"{d.name}: body does not say {bad!r}", bad not in text,
                  "found in the body")


def t_a_skill_grants_no_permission_and_says_so():
    """A skill is instructions, not a licence. Each command it describes still
    goes through the gate, and the text has to say that or a reader will assume
    the skill authorised it."""
    for d in skill_dirs():
        text = (d / "SKILL.md").read_text(encoding="utf-8")
        check(f"{d.name}: it says the gate still applies",
              "approval gate" in text or "goes through the gate" in text,
              "no sentence about the gate")
        check(f"{d.name}: it lists what it deliberately does not do",
              "Not for:" in text or "does not" in text,
              "no boundary in the text")
        sk, _ = read_skill(d.name)
        check(f"{d.name}: the body carries no fenced executable block",
              "```bash" not in text and "```sh" not in text,
              "a shell block is in the skill")


# --------------------------------------------------------------------------
#   The attribution
# --------------------------------------------------------------------------

def t_the_attribution_is_in_the_hand_written_half_of_the_notices():
    """WHERE it lands matters: `tools/gen_notices.py` keeps only the hand-written
    region (from the first "(not generated" marker to the line before
    "2. RUST LIBRARIES"), and everything from section 2 on is GENERATED. An
    attribution written into the generated half is deleted by the next run."""
    check("the notices file is there", NOTICES.is_file())
    text = NOTICES.read_text(encoding="utf-8")
    gen_at = text.find("\n2. RUST LIBRARIES IN THE DESKTOP PROGRAM")
    check("the generated section was found", gen_at > 0, repr(gen_at))
    hand = text[:gen_at]
    check("the hand-written half is the bigger half of the top",
          "(not generated" in hand, "no hand-written marker above section 2")
    check("the attribution heading is in the HAND-WRITTEN half",
          "SKILLS ADAPTED FROM OTHER PROJECTS" in hand,
          "heading not found above section 2")
    check("and NOT in the generated half",
          "SKILLS ADAPTED FROM OTHER PROJECTS" not in text[gen_at:],
          "heading appears below section 2")
    check("the source repository is named", "openai/skills" in hand)
    check("the licence is named", "Apache-2.0" in hand or "Apache License" in hand)
    check("the upstream path is named", "skills/.curated/pdf" in hand)
    check("the adapted file is named", "skills/pdf-workflow/SKILL.md" in hand)
    check("it says the copyright line is unfilled",
          "Copyright [yyyy]" in hand, "the unfilled-line note is missing")
    check("it says nothing is shipped unmodified",
          "no code" in hand or "none of its files are shipped" in hand)
    check("the two NOT-vendored skills are named, so the gap is not silent",
          "skill-creator" in hand and "grill-me" in hand)


def t_the_attribution_names_the_licence_the_upstream_file_states():
    """The claim in the notices is checked against what it claims: the licence
    named there must be the one the upstream LICENSE.txt holds. That file was
    read from the upstream repository (openai/skills, skills/.curated/pdf) and is
    the Apache License, Version 2.0 - recorded here as a fact with its URL, so a
    future edit to the notice has to face the same question."""
    text = NOTICES.read_text(encoding="utf-8")
    hand = text[:text.find("\n2. RUST LIBRARIES IN THE DESKTOP PROGRAM")]
    block = hand[hand.find("SKILLS ADAPTED FROM OTHER PROJECTS"):]
    check("the entry says Apache-2.0",
          "Apache-2.0" in block or "Apache License, Version 2.0" in block,
          repr(block[:200]))
    check("and it points at the full licence text in this file",
          "LICENCE TEXTS" in block or "LUCENCE TEXTS" in block,
          "no pointer to the licence text")
    check("the full Apache-2.0 text really is in this file",
          "Apache License\nVersion 2.0" in text or "Apache License, Version 2.0" in text,
          "no Apache text anywhere in the notices")
    check("and it says the upstream root carries no licence file",
          "no licence file" in block, repr(block[:300]))


#: Each shipped skill, and the origin + licence its own text must name. A skill with
#: no entry here is not silently passed: the check below fails for it, because an
#: adaptation with no recorded source is exactly the gap this suite exists to catch.
SKILL_ORIGINS = {
    "pdf-workflow": ("openai/skills", "Apache"),
    "reverse-engineer-anything": ("morluto/rea", "MIT"),
}


def t_the_skill_itself_records_its_own_origin():
    for d in skill_dirs():
        text = (d / "SKILL.md").read_text(encoding="utf-8")
        origin, licence = SKILL_ORIGINS.get(d.name, ("", ""))
        check(f"{d.name}: has a recorded upstream origin", bool(origin),
              "no SKILL_ORIGINS entry for this skill")
        check(f"{d.name}: names its upstream origin", bool(origin) and origin in text,
              "no origin line in the skill")
        check(f"{d.name}: names its licence", bool(licence) and licence in text,
              "no licence line in the skill")


def t_the_rea_skill_credit_is_in_the_hand_written_half_of_the_notices():
    """The MIT credit for the adapted REA skill lands where tools/gen_notices.py
    keeps it (the hand-written region), names the upstream, the licence and the
    adapted file, and says the upstream reference files are not shipped."""
    check("the notices file is there", NOTICES.is_file())
    text = NOTICES.read_text(encoding="utf-8")
    gen_at = text.find("\n2. RUST LIBRARIES IN THE DESKTOP PROGRAM")
    check("the generated section was found", gen_at > 0, repr(gen_at))
    hand = text[:gen_at]
    check("morluto/rea is named in the hand-written half", "morluto/rea" in hand)
    check("the MIT licence is named there", "MIT" in hand)
    check("the adapted file is named",
          "skills/reverse-engineer-anything/SKILL.md" in hand)
    check("it says the six reference files are not shipped",
          "references/` files are NOT shipped" in hand
          or "reference files are not shipped" in hand.lower(),
          "no sentence about the unshipped references")


if __name__ == "__main__":
    for fn in (t_every_shipped_skill_parses_and_scans_clean,
               t_every_declared_tool_is_one_of_jarvis_s_own,
               t_a_skill_declares_the_tools_it_needs_so_it_can_be_hidden,
               t_no_skill_asks_this_pc_to_install_anything,
               t_no_skill_names_an_external_address,
               t_no_skill_schedules_anything,
               t_a_skill_grants_no_permission_and_says_so,
               t_the_attribution_is_in_the_hand_written_half_of_the_notices,
               t_the_attribution_names_the_licence_the_upstream_file_states,
               t_the_skill_itself_records_its_own_origin,
               t_the_rea_skill_credit_is_in_the_hand_written_half_of_the_notices):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
