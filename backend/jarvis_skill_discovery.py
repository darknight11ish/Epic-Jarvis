"""jarvis_skill_discovery.py - notice a routine Jarvis keeps running, and offer
it, once, as a skill. Nothing is written until the owner says yes.

WHAT IT DOES, IN PLAIN WORDS
Every time the tool loop (jarvis_agent.run_local_turn) finishes a turn that
used tools, it writes ONE line to the audit log Jarvis already keeps: a random
turn id and the names of the tools, in order, with whether each one ran. No
arguments, no results, no words from the conversation - tool names only.

This module reads those lines back, counts which chains of tools (for example
"notes_search, then calendar_read") have run in several separate turns, and
when one has run often enough it raises ONE approval card: "save this as a
skill?". The card is the approval Jarvis already needs to change itself -
jarvis_gate action `modify_own_code`, the same action jarvis_skills.write_skill
and refine() gate on. Yes writes one new SKILL.md file. No writes nothing and
that chain is never offered again. Nobody answering writes nothing and it may
be offered again another day.

WHY THE ONE NEW LOG LINE WAS NEEDED
The research item (docs/LEARNING-RESEARCH-2026-09-23.md, item 7) asked first
whether the approval log already records which turn each action belonged to.
It does not. What exists, checked against the files in this repository:

  * approvals.db - `SELECT id,action,tier,detail,prompt,created,raised FROM
    approvals` (test_gate_egress.py). Only `ask`-tier actions get a row at all,
    so the read-only tools that run without asking never appear there, and
    there is no turn column.
  * the audit log - one JSON line per gate event, `{"t", "iso", "event",
    "detail"}` (rebuilt/jarvis_framework.py `audit_log`), with `detail` being
    `{"action", "detail"}` for gate.auto / gate.notify and `{"id", "action",
    "by"}` for gate.approved (gate-outcome.patch). A timestamp and an action
    name, no turn.

Grouping gate lines by time would guess at which actions belonged together,
and two turns a minute apart would merge. So the smallest record that makes
chains countable is one extra line per tool-using turn, written by the tool
loop, which is the only code that knows where a turn starts and ends. It goes
into the SAME audit log (same writer, same folder, same 90-day retention), so
there is still one log, not a second one.

RULES THIS MODULE KEEPS (each one has a test in test_skill_discovery.py)
  * Counting only. Nothing here opens a network connection.
  * Counts actions that ran without asking (tiers auto and notify) as well as
    approved ones - read-only tools never raise a card, and a routine made of
    them is still a routine. Refused, denied, timed-out and failed steps are
    not counted: a skill must not be built from something that did not work
    or that the owner said no to.
  * The skill text is built from tool NAMES and from the tool descriptions in
    jarvis_agent.TOOLS - text this project wrote. No message, argument or tool
    result is ever copied into it. There is none to copy: the log line holds
    none.
  * One card at a time, at most one offer a day, and never more than one
    chain per card. There is no "save all" and there will not be one.
  * `run()` writes only with `approved=True` given explicitly, only after the
    gate said a HUMAN approved (tier `ask`, outcome `approved`), and never
    over an existing folder. Nothing here deletes anything - a declined
    offer is recorded with its date and kept.
  * The model decides nothing here. Which chain, its name, its text, the
    permission tier and a turn's origin all come from the backend.

WHAT IS NOT VERIFIED (said here so nobody has to find out the hard way)
  * jarvis_skills.py is not in this repository, so where it loads skills from
    is not known. The file is written to `JARVIS_SKILLS_DIR` if that is set,
    otherwise `~/.openjarvis/skills/<name>/SKILL.md`. After writing, this
    module asks `jarvis_skills.cards()` whether the new skill is listed and
    records the answer (`listed`: true, false, or null if it could not ask).
    If it says false, set JARVIS_SKILLS_DIR to the folder jarvis_skills reads.
  * write_skill() is not called, on purpose: its signature is not in this
    repository, and it raises its own modify_own_code card, so calling it
    after this module's card would ask the owner twice about one file.
  * A "no" on this card also makes the gate propose a memory rule, because
    gate-outcome.patch turns every denial into a proposal ("I do not want
    Jarvis to modify own code without asking me first"). That is the gate's
    own behaviour, not this module's. It is only a proposal in the memory
    queue; Discard it if it is not what you meant.

Idea from OpenJarvis `learning/agents/skill_discovery.py` (Apache-2.0):
count contiguous tool sequences of length 2 to 4. No code was copied, and two
of its choices were deliberately NOT taken: it writes skills to disk with no
review, and it copies the user's past queries into the skill as examples.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# --------------------------------------------------------------------------
#   Constants
# --------------------------------------------------------------------------

#: The audit-log event name for one tool-using turn.
EVENT = "agent.chain"

#: The gate action a new skill goes through. It is the one jarvis_skills
#: already uses for write_skill() and refine() (backend/README.md,
#: skill-notes.patch), and jarvis-framework.toml sets it to "ask".
ACTION = "modify_own_code"

#: Gate outcomes that mean the tool actually ran (gate-outcome.patch).
#: "auto" and "notify" are here on purpose: those are the tools that ran
#: without asking, and a routine made of them is still a routine.
RAN_OUTCOMES = frozenset({"auto", "notify", "approved"})

#: Every outcome a record may carry. Anything else is stored as "unknown".
KNOWN_OUTCOMES = frozenset({"auto", "notify", "approved", "denied",
                            "timed_out", "refused", "unknown"})

#: A tool name as jarvis_agent.TOOLS spells them. Anything else - including a
#: name the model invented - is dropped before it reaches the log.
_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

MIN_LEN = 2               # one tool on its own is not a routine
MAX_LEN = 4
MAX_STEPS_PER_TURN = 32   # a bound on one log line, far above max_rounds

DEFAULT_MIN_REPEATS = 3   # separate turns before an offer
DEFAULT_WINDOW_DAYS = 30
DEFAULT_EVERY_HOURS = 24  # at most one card per this many hours

#: A chain whose latest decision is one of these is never offered again.
_FINAL = frozenset({"denied", "written", "already_exists"})

_IN_FLIGHT = threading.Lock()    # one card at a time, per process
_LEDGER_LOCK = threading.Lock()


# --------------------------------------------------------------------------
#   The framework, reached lazily so this file imports anywhere
# --------------------------------------------------------------------------

def _fw():
    import jarvis_framework
    return jarvis_framework


def _fw_audit(event: str, detail: dict) -> bool:
    return bool(_fw().audit_log(event, detail))


def _fw_tier(action: str) -> str:
    return str(_fw().action_tier(action))


def _settings() -> dict:
    """The optional `[skills]` keys this module reads. None of them has to
    exist; every one has a safe default."""
    try:
        cfg = _fw().load_framework().get("skills", {})
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}

    def _int(key, default, lo, hi):
        try:
            return max(lo, min(hi, int(cfg.get(key, default))))
        except (TypeError, ValueError):
            return default

    return {
        "enabled": bool(cfg.get("enabled", True)) and bool(cfg.get("suggest_skills", True)),
        # Clamped to at least 2: offering a routine after one run would be
        # offering every tool call.
        "min_repeats": _int("suggest_after_repeats", DEFAULT_MIN_REPEATS, 2, 1000),
        "window_days": _int("suggest_window_days", DEFAULT_WINDOW_DAYS, 1, 90),
        "every_hours": _int("suggest_every_hours", DEFAULT_EVERY_HOURS, 1, 24 * 90),
    }


# --------------------------------------------------------------------------
#   1. Recording - called by jarvis_agent at the end of a tool-using turn
# --------------------------------------------------------------------------

def record_turn(steps: list, *, origin: Optional[str] = None,
                audit: Optional[Callable[[str, dict], bool]] = None) -> bool:
    """Write one audit line for one turn. Returns whether it was written.

    `steps` is a list of `{"tool", "ran", "ok", "outcome"}` dicts in the
    order the tools were asked for. Only those four keys are kept, and only
    for tool names that look like tool names. There is no field here for an
    argument or a result, so none can be written by mistake.

    `origin` is for the backend to set, never the model: "owner" for a turn
    the owner typed or said. It is recorded only when given; a record that
    carries an origin other than "owner" is not counted (see read_turns).
    """
    clean = []
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        tool = str(s.get("tool") or "")
        if not _TOOL_NAME.match(tool):
            continue
        outcome = str(s.get("outcome") or "unknown")
        if outcome not in KNOWN_OUTCOMES:
            outcome = "unknown"
        clean.append({"tool": tool, "ran": s.get("ran") is True,
                      "ok": s.get("ok") is True, "outcome": outcome})
        if len(clean) >= MAX_STEPS_PER_TURN:
            break
    if not clean:
        return False
    row = {"turn": uuid.uuid4().hex, "steps": clean}
    if origin is not None:
        row["origin"] = str(origin)[:32]
    try:
        return bool((audit or _fw_audit)(EVENT, row))
    except Exception:
        return False


# --------------------------------------------------------------------------
#   2. Counting
# --------------------------------------------------------------------------

def _day_of(name: str) -> Optional[float]:
    """The UTC midnight of a `jarvis-YYYY-MM-DD.jsonl` file, or None."""
    m = re.match(r"^jarvis-(\d{4})-(\d{2})-(\d{2})\.jsonl$", name)
    if not m:
        return None
    try:
        import calendar
        return float(calendar.timegm((int(m[1]), int(m[2]), int(m[3]), 0, 0, 0)))
    except Exception:
        return None


def read_turns(days: int, *, log_dir=None, now: Optional[float] = None) -> list:
    """Every recorded tool-using turn in the last `days` days, oldest first.

    Each item is `{"turn", "t", "tools"}`, where `tools` holds only the steps
    that ran AND succeeded, with a tool repeated back-to-back collapsed to one
    ("search, search, read" is the same routine as "search, read").
    """
    now = time.time() if now is None else float(now)
    cutoff = now - days * 86400
    where = Path(log_dir) if log_dir is not None else Path(_fw().log_dir())
    try:
        files = sorted(where.glob("jarvis-*.jsonl"))
    except OSError:
        return []
    out, seen = [], set()
    for f in files:
        day = _day_of(f.name)
        # A day file can hold nothing newer than its own midnight + 1 day.
        if day is not None and day + 86400 < cutoff:
            continue
        try:
            fh = open(f, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"agent.chain"' not in line:     # cheap skip for every other event
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict) or row.get("event") != EVENT:
                    continue
                t = row.get("t")
                if not isinstance(t, (int, float)) or t < cutoff or t > now + 60:
                    continue
                det = row.get("detail")
                if not isinstance(det, dict):
                    continue
                origin = det.get("origin")
                if origin is not None and origin != "owner":
                    continue     # a turn Jarvis started itself is not the owner's routine
                turn = str(det.get("turn") or "")
                if not turn or turn in seen:
                    continue
                seen.add(turn)
                tools = []
                for s in det.get("steps") or []:
                    if not isinstance(s, dict):
                        continue
                    name = str(s.get("tool") or "")
                    if s.get("ran") is True and s.get("ok") is True and _TOOL_NAME.match(name):
                        if not tools or tools[-1] != name:
                            tools.append(name)
                out.append({"turn": turn, "t": float(t), "tools": tools})
    out.sort(key=lambda r: r["t"])
    return out


def count_chains(turns: list) -> dict:
    """{chain tuple: {"turns": n, "last_seen": t}} over every contiguous run
    of MIN_LEN..MAX_LEN tools. Counted once per TURN, not once per
    appearance: a turn that did "search, read" twice is one repeat, not two.
    """
    counts: dict = {}
    for r in turns:
        tools = r["tools"]
        subs = set()
        for n in range(MIN_LEN, MAX_LEN + 1):
            for i in range(0, len(tools) - n + 1):
                subs.add(tuple(tools[i:i + n]))
        for c in subs:
            e = counts.setdefault(c, {"turns": 0, "last_seen": 0.0})
            e["turns"] += 1
            e["last_seen"] = max(e["last_seen"], r["t"])
    return counts


def _is_sub(small: tuple, big: tuple) -> bool:
    """True if `small` sits contiguously inside `big` (and is shorter)."""
    if len(small) >= len(big):
        return False
    return any(big[i:i + len(small)] == small for i in range(len(big) - len(small) + 1))


def ranked(counts: dict, min_repeats: int) -> list:
    """Chains at or over the threshold, best first, with the ones that only
    ever ran as part of a longer chain removed - "search, read" seen 4 times,
    every time inside "search, read, draft", is the longer routine, not two.
    """
    over = {c: e for c, e in counts.items() if e["turns"] >= min_repeats}
    keep = []
    for c, e in over.items():
        if any(_is_sub(c, b) and eb["turns"] == e["turns"] for b, eb in over.items()):
            continue
        keep.append((c, e))
    keep.sort(key=lambda ce: (-ce[1]["turns"], -len(ce[0]), -ce[1]["last_seen"], ce[0]))
    return [{"chain": list(c), "turns": e["turns"], "last_seen": e["last_seen"]}
            for c, e in keep]


def _key(chain) -> str:
    return ">".join(chain)


# --------------------------------------------------------------------------
#   3. The ledger of offers - appended to, never rewritten or pruned
# --------------------------------------------------------------------------

class LedgerUnreadable(Exception):
    """The offers file exists and cannot be read. Nothing is offered then:
    not knowing what was declined must not turn into asking again."""


def _ledger_path() -> Path:
    return Path(_fw().CONFIG_DIR) / "skill-offers.json"


def load_ledger(path=None) -> list:
    p = Path(path) if path is not None else _ledger_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        rows = data.get("offers") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise ValueError("no offers list")
        return [r for r in rows if isinstance(r, dict)]
    except Exception as exc:
        raise LedgerUnreadable(f"{p}: {type(exc).__name__}: {exc}") from exc


def _append(path, entry: dict) -> None:
    """Add one entry. The file is rewritten whole through a temp file and a
    rename, so a crash leaves the old file or the new one, never half of one.
    Existing entries are carried over untouched - nothing is ever removed."""
    p = Path(path) if path is not None else _ledger_path()
    with _LEDGER_LOCK:
        rows = load_ledger(p)       # raises on a corrupt file: never overwrite one
        rows.append(entry)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({"version": 1, "offers": rows}, indent=1,
                                  ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)


def _decisions(rows: list) -> dict:
    """{chain key: latest decided outcome}."""
    out = {}
    for r in rows:
        if r.get("event") == "decided" and r.get("key"):
            out[str(r["key"])] = str(r.get("outcome") or "")
    return out


def _last_offer_at(rows: list) -> Optional[float]:
    ts = [r.get("at") for r in rows
          if r.get("event") == "offered" and isinstance(r.get("at"), (int, float))]
    return max(ts) if ts else None


def _status(chain: list, decisions: dict) -> Optional[str]:
    """Why a chain must not be offered, or None if it may be."""
    k = _key(chain)
    latest = decisions.get(k)
    if latest in _FINAL:
        return "declined" if latest == "denied" else "saved"
    # A shorter chain inside one the owner already declined or saved is
    # covered by that answer. Asking about its pieces one by one would be
    # asking the same question again.
    for dk, outcome in decisions.items():
        if outcome in _FINAL and _is_sub(tuple(chain), tuple(dk.split(">"))):
            return "covered"
    return None


# --------------------------------------------------------------------------
#   4. plan / describe / gate / run
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Plan:
    key: str
    chain: tuple
    turns: int
    window_days: int
    name: str
    path: str
    skill_md: str
    steps: tuple = field(default_factory=tuple)   # (tool, description) pairs


def _tool_descriptions() -> dict:
    """First sentence of each tool's own description in jarvis_agent.TOOLS -
    text this project wrote, never text from a conversation."""
    try:
        import jarvis_agent
        tools = jarvis_agent.TOOLS
    except Exception:
        return {}
    out = {}
    for name, tool in tools.items():
        d = " ".join(str(getattr(tool, "description", "") or "").split())
        first = re.split(r"(?<=[.!?])\s", d, maxsplit=1)[0] if d else ""
        if len(first) > 120:
            first = first[:117].rsplit(" ", 1)[0].rstrip(",;:") + "..."
        out[name] = first
    return out


def _skill_name(chain) -> str:
    slug = "-".join(t.replace("_", "-") for t in chain)[:40].strip("-")
    digest = hashlib.sha1(_key(chain).encode("utf-8")).hexdigest()[:6]
    return f"routine-{slug}-{digest}"


def _skills_dir() -> Path:
    env = os.environ.get("JARVIS_SKILLS_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(_fw().CONFIG_DIR) / "skills"


def _skill_md(name: str, chain, turns: int, days: int, descs: dict) -> str:
    """The whole file. Built from tool names, counts and this project's own
    tool descriptions - and nothing else."""
    readable = ", then ".join(chain)
    lines = [
        "---",
        f"name: {name}",
        f"description: A routine Jarvis has run in {turns} separate conversations "
        f"- {readable}. Use it when the owner asks for this routine.",
        "---",
        "",
        f"# Routine - {readable}",
        "",
        f"Jarvis used these tools in this order in {turns} separate "
        f"conversations in {days} days. When the owner asks for this routine, "
        f"use them in the same order:",
        "",
    ]
    for i, tool in enumerate(chain, 1):
        d = descs.get(tool, "")
        lines.append(f"{i}. `{tool}`" + (f" - {d}" if d else ""))
    lines += [
        "",
        "Every step still goes through the approval gate at its own tier. "
        "This skill grants no permission and skips no question.",
        "",
        "Written from a count of tool names only. No conversation text was "
        "used.",
        "",
    ]
    return "\n".join(lines)


def plan(*, now: Optional[float] = None, log_dir=None, ledger=None,
         skills_dir=None, settings: Optional[dict] = None) -> Optional[Plan]:
    """Work out the ONE chain to offer next, and the exact file that would be
    written. Touches nothing and opens no socket. None if there is nothing to
    offer, the feature is off, the last offer was too recent, or the ledger
    cannot be read."""
    s = settings or _settings()
    if not s["enabled"]:
        return None
    now = time.time() if now is None else float(now)
    try:
        rows = load_ledger(ledger)
    except LedgerUnreadable:
        return None
    last = _last_offer_at(rows)
    if last is not None and now - last < s["every_hours"] * 3600:
        return None
    decisions = _decisions(rows)
    turns = read_turns(s["window_days"], log_dir=log_dir, now=now)
    for cand in ranked(count_chains(turns), s["min_repeats"]):
        if _status(cand["chain"], decisions) is not None:
            continue
        chain = tuple(cand["chain"])
        name = _skill_name(chain)
        base = Path(skills_dir) if skills_dir is not None else _skills_dir()
        descs = _tool_descriptions()
        return Plan(key=_key(chain), chain=chain, turns=cand["turns"],
                    window_days=s["window_days"], name=name,
                    path=str(base / name / "SKILL.md"),
                    skill_md=_skill_md(name, chain, cand["turns"], s["window_days"], descs),
                    steps=tuple((t, descs.get(t, "")) for t in chain))
    return None


def describe(p: Plan) -> str:
    """The card, in full. The whole file that would be written is on it -
    summarising a request on the card that authorises it defeats the card."""
    steps = "\n".join(f"{i}. `{t}`" for i, t in enumerate(p.chain, 1))
    return (
        f"**Save a routine as a skill?**\n\n"
        f"Jarvis has run these tools in this order in {p.turns} separate "
        f"conversations in the last {p.window_days} days:\n\n{steps}\n\n"
        f"If you say yes, Jarvis writes this one new file, and nothing else:\n\n"
        f"`{p.path}`\n\n```\n{p.skill_md}```\n\n"
        f"The skill does nothing on its own. It is a note Jarvis reads when "
        f"you ask for this routine, and every step in it still asks at its own "
        f"tier. It was written from a count of tool names only - none of your "
        f"messages were copied into it.\n\n"
        f"If you say no: nothing is written, and Jarvis will not offer this "
        f"routine again. You can still ask for these steps yourself, as now."
    )


def run(p: Plan, *, approved: bool) -> dict:
    """Write the approved file. `approved` has no default: a module that can
    act must not be one call away from acting by accident.

    Writes exactly `p.skill_md`, the text that was on the card - never a
    value worked out again now - at exactly `p.path`, the path that was on the
    card. Never overwrites: if the folder exists, it is left alone and the
    answer says so.
    """
    if approved is not True:
        return {"ok": False, "reason": "not approved, so nothing was written"}
    target = Path(p.path)
    folder = target.parent
    try:
        folder.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return {"ok": False, "already_exists": True, "path": str(target),
                "reason": "a skill folder with this name already exists; it was "
                          "left exactly as it was"}
    tmp = folder / "SKILL.md.tmp"
    tmp.write_text(p.skill_md, encoding="utf-8", newline="\n")
    os.replace(tmp, target)
    return {"ok": True, "path": str(target), "listed": _listed(p.name)}


def _listed(name: str) -> Optional[bool]:
    """Whether jarvis_skills now lists the new skill. None if it cannot be
    asked - the module is not in this repository, so this is checked at run
    time rather than assumed."""
    try:
        import jarvis_skills
        return any(isinstance(c, dict) and c.get("name") == name
                   for c in jarvis_skills.cards())
    except Exception:
        return None


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def offer(p: Plan, *, gate: Optional[Callable] = None,
          tier_of: Optional[Callable[[str], str]] = None,
          audit: Optional[Callable[[str, dict], bool]] = None,
          ledger=None, now: Optional[float] = None) -> dict:
    """Raise ONE card for ONE plan and act on the answer. Blocks until the
    owner answers or the gate's own timeout passes, so call it off the
    request thread (maybe_offer_async does).

    Returns {"outcome": ..., ...}. The outcome is also appended to the ledger
    and to the audit log, by name only.
    """
    gate = gate or _gate
    tier_of = tier_of or _fw_tier
    audit = audit or _fw_audit
    now = time.time() if now is None else float(now)

    def _decide(outcome: str, **extra) -> dict:
        entry = {"event": "decided", "key": p.key, "chain": list(p.chain),
                 "outcome": outcome, "at": time.time(), **extra}
        try:
            _append(ledger, entry)
        except Exception as exc:
            entry["ledger_error"] = f"{type(exc).__name__}: {exc}"
        try:
            audit("skills.suggest.decided", {"key": p.key, "outcome": outcome,
                                             "name": p.name})
        except Exception:
            pass
        return entry

    # Checked before asking, so a card is never raised that could not end in
    # a person deciding. Checked again on the verdict below, which is the one
    # that matters: `allowed` is True on tiers auto and notify with nobody
    # asked, and a skill must not be written on that (skill-notes.patch).
    try:
        tier = tier_of(ACTION)
    except Exception as exc:
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        # Not written to the ledger: nothing was offered, and a ledger line
        # per tool-using turn while the tier is wrong would only grow a file.
        return {"event": "decided", "outcome": "refused",
                "reason": f"{ACTION} is tier {tier!r}; a new skill needs a person "
                          f"to say yes, so set it to 'ask' (or 'never' to stop "
                          f"these offers)"}

    try:
        _append(ledger, {"event": "offered", "key": p.key, "chain": list(p.chain),
                         "turns": p.turns, "name": p.name, "path": p.path, "at": now})
    except Exception as exc:
        # Not knowing that this was offered would let it be offered again
        # tomorrow as if new. Better not to ask at all.
        return {"event": "decided", "outcome": "refused",
                "reason": f"could not record the offer ({type(exc).__name__}: {exc})"}
    try:
        audit("skills.suggest.offered", {"key": p.key, "name": p.name, "turns": p.turns})
    except Exception:
        pass

    text = describe(p)
    detail = {"text": text, "skill": p.name, "chain": list(p.chain),
              "turns": p.turns, "path": p.path}
    try:
        v = gate(ACTION, detail, text)
    except Exception as exc:
        return _decide("refused", reason=f"the gate raised {type(exc).__name__}: {exc}")

    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        # A gate from before gate-outcome.patch: only allowed-on-ask can be
        # read as a human yes; anything else cannot be told apart from a
        # timeout, so it is treated as one (may be asked again later).
        outcome = "approved" if (allowed and vtier == "ask") else "refused"

    if vtier != "ask":
        return _decide("refused", reason=f"the gate answered at tier {vtier!r}, "
                                         f"which is not a person saying yes")
    if allowed and outcome == "approved":
        try:
            res = run(p, approved=True)
        except Exception as exc:
            return _decide("write_failed", reason=f"{type(exc).__name__}: {exc}",
                           request_id=getattr(v, "request_id", None))
        if res.get("already_exists"):
            return _decide("already_exists", path=res["path"],
                           request_id=getattr(v, "request_id", None))
        return _decide("written", path=res["path"], listed=res.get("listed"),
                       request_id=getattr(v, "request_id", None))
    if outcome == "denied":
        return _decide("denied", request_id=getattr(v, "request_id", None))
    if outcome == "timed_out":
        return _decide("timed_out", request_id=getattr(v, "request_id", None))
    return _decide("refused", reason=str(getattr(v, "reason", "refused"))[:200])


#: The longest a skill offer waits for the owner to stop chatting. After
#: that it gives up; the next tool-using turn may start another.
QUIET_WAIT_MAX = 30 * 60.0


def _backoff(kwargs: dict):
    """(the back-off, its fingerprint function), or (None, None) without
    jarvis_backoff.py - then offers work as they always did. A test passes
    `backoff=None` to leave it out, or its own."""
    try:
        import jarvis_backoff
    except Exception:
        return None, None
    bo = kwargs["backoff"] if "backoff" in kwargs else jarvis_backoff.get()
    return (bo, jarvis_backoff.fingerprint) if bo is not None else (None, None)


def _wait_for_quiet(bo, sleep) -> bool:
    """Wait until the owner has not chatted for two minutes. False if that
    did not happen within QUIET_WAIT_MAX."""
    waited = 0.0
    while True:
        left = bo.quiet_for()
        if left <= 0:
            return True
        if waited >= QUIET_WAIT_MAX:
            return False
        step = min(left + 1.0, 30.0)
        sleep(step)
        waited += step


def maybe_offer_async(**kwargs) -> bool:
    """Called after each tool-using turn. If no card is already waiting,
    starts ONE background thread that plans and, if there is something to
    offer, raises the card. Returns whether a thread was started. Never
    blocks the caller and never raises."""
    if not _IN_FLIGHT.acquire(blocking=False):
        return False

    def work():
        try:
            # Tier first, so nothing is even counted while an offer could not
            # end in a person deciding. offer() checks again; this only saves
            # the work.
            if (kwargs.get("tier_of") or _fw_tier)(ACTION) != "ask":
                return
            # The back-off (jarvis_backoff.py): this is an offer nobody asked
            # for, and it is started at the END of a chat turn - so it waits
            # until the owner has stopped chatting for two minutes, and asks
            # only while few other offers wait. A "no" here is already for
            # good (_FINAL, above), stricter than the back-off's 1/7/30 days,
            # so nothing is written to its file for this offer.
            bo, fpr = _backoff(kwargs)
            if bo is not None and not _wait_for_quiet(bo, kwargs.get("sleep") or time.sleep):
                return
            p = plan(**{k: v for k, v in kwargs.items()
                        if k in ("log_dir", "ledger", "skills_dir", "settings")})
            if p is None:
                return
            fp = fpr("skill_offer", p.key) if bo is not None else None
            if bo is not None:
                may, _why = bo.may_offer(fp)
                if not may:
                    return
                bo.opened(fp)
            try:
                offer(p, **{k: v for k, v in kwargs.items()
                            if k in ("gate", "tier_of", "audit", "ledger")})
            finally:
                if bo is not None:
                    bo.closed(fp)
        except Exception:
            pass
        finally:
            _IN_FLIGHT.release()

    try:
        threading.Thread(target=work, name="jarvis-skill-offer", daemon=True).start()
        return True
    except Exception:
        _IN_FLIGHT.release()
        return False


# --------------------------------------------------------------------------
#   5. What GET /api/skills/suggestions shows
# --------------------------------------------------------------------------

def view(*, now: Optional[float] = None, log_dir=None, ledger=None,
         settings: Optional[dict] = None, tier_of: Optional[Callable] = None) -> dict:
    """Read-only. What is being counted, what has been offered and what the
    owner said. Tool names and counts only - no conversation text exists in
    anything this reads."""
    s = settings or _settings()
    now = time.time() if now is None else float(now)
    try:
        tier = (tier_of or _fw_tier)(ACTION)
    except Exception:
        tier = "unknown"
    try:
        recording = bool(_fw().logging_enabled()) if log_dir is None else True
    except Exception:
        recording = False
    out = {
        "available": True,
        "enabled": s["enabled"],
        "recording": recording,
        "tier": tier,
        "min_repeats": s["min_repeats"],
        "window_days": s["window_days"],
        "every_hours": s["every_hours"],
        "in_flight": _IN_FLIGHT.locked(),
        "note": "Counted from tool names in the local audit log. No conversation "
                "text is read, stored or sent anywhere. An offer arrives as an "
                "ordinary approval card (action modify_own_code), one at a time.",
    }
    why_off = None
    if not s["enabled"]:
        why_off = "turned off in jarvis-framework.toml ([skills] enabled or suggest_skills)"
    elif not recording:
        why_off = "the audit log is off ([logging] enabled = false), so nothing is counted"
    elif tier != "ask":
        why_off = (f"{ACTION} is tier {tier!r}; offers need 'ask', so none are made")
    out["why_off"] = why_off
    try:
        rows = load_ledger(ledger)
        out["ledger_error"] = None
    except LedgerUnreadable as exc:
        rows = []
        out["ledger_error"] = str(exc)
    last = _last_offer_at(rows)
    out["next_offer_after"] = (last + s["every_hours"] * 3600) if last is not None else None
    decisions = _decisions(rows)
    counts = count_chains(read_turns(s["window_days"], log_dir=log_dir, now=now))
    top = ranked(counts, 1)[:20]
    chains = []
    for c in top:
        st = _status(c["chain"], decisions)
        if st is None:
            latest = decisions.get(_key(c["chain"]))
            st = ("eligible" if c["turns"] >= s["min_repeats"] else "counting")
            if latest in ("timed_out", "refused", "write_failed"):
                st = "asked_before"
        chains.append({**c, "status": st})
    out["chains"] = chains
    out["offers"] = list(reversed(rows[-50:]))
    return out
