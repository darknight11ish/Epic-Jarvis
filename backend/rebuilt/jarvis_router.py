"""jarvis_router.py - which lane answers, and what it is allowed to see.

REBUILT. The original is gone. Five call sites pin the interface:

    Budget.load().status()                              jarvis_hud:1475
    budget = Budget.load()                              jarvis_hud:1705
    choose(query, local_model=, lanes=, has_image=, ...) jarvis_hud:1707
    degrade(lane, lanes, local_model)                   jarvis_hud:1846
    Decision(chosen, "you chose this lane", "manual", 0.0, inject_memory=...)
                                                        jarvis_hud:2115
    _PRIVATE.search(joined)                             jarvis_hud:2024

and `decision.lane / .reason / .gate / .inject_memory / .as_dict` are all
read. `[budget]` and `[routing]` in the config supply the numbers.

THE RULE THIS MODULE EXISTS TO ENFORCE, from JARVIS-FRAMEWORK.md section 1:

    "cloud turns get your raw question and nothing else. Local turns get your
     question plus whatever stored facts are actually relevant to it. There is
     no third option where a cloud model quietly receives your memory."

So `inject_memory` is FALSE on every cloud lane, computed from the lane rather
than passed in - a caller cannot ask for memory on a cloud turn, because the
bug that started all this (`context_from_memory = true` injecting memory into
every request, before routing even ran) was exactly a caller being trusted.

AND THE ONE THAT WAS BROKEN THE LONGEST: degrade() "has always described that
chain; nothing ever called it, so the documented behaviour did not exist"
(jarvis_hud:1820). It is called now. It walks DOWNWARD only and never returns
the lane it was given, because a degrade that can return its input is an
infinite retry loop against a service that is already refusing.
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore


def _cfg(section: str, key: str, default=None):
    if fw is None:
        return default
    try:
        return fw.load_framework().get(section, {}).get(key, default)
    except Exception:
        return default


# --------------------------------------------------------------------------
#   What must never go to a cloud lane
# --------------------------------------------------------------------------
#
# jarvis_hud:2024 uses this as `jarvis_router._PRIVATE.search(joined)`, so it
# is a compiled regex with .search, matched against joined message text.
#
# It is a BACKSTOP, not the mechanism. JARVIS-FRAMEWORK.md is explicit: "It's a
# backstop, not the primary mechanism - the primary mechanism is that cloud
# lanes are never handed memory in the first place, so even a topic missing
# from this list can't leak your stored facts, only your literal typed words."
# Anything that relies on this list being complete is designed wrong.
_PRIVATE_TERMS = [
    r"\bpassword\b", r"\bpassphrase\b", r"\bapi[ _-]?key\b", r"\bsecret\b",
    r"\btoken\b", r"\bcredential\b", r"\bprivate key\b", r"\bseed phrase\b",
    r"\bssn\b", r"\bsocial security\b", r"\bpassport\b", r"\bdriver'?s licence\b",
    r"\biban\b", r"\bsort code\b", r"\brouting number\b", r"\baccount number\b",
    r"\bcredit card\b", r"\bcvv\b",
    r"\bdiagnos\w*\b", r"\bprescription\b", r"\bbiopsy\b", r"\bmedical record\b",
    r"\bsalary\b", r"\bbank statement\b", r"\btax return\b",
]
_PRIVATE = re.compile("|".join(_PRIVATE_TERMS), re.I)


def is_private(text: str) -> bool:
    return bool(_PRIVATE.search(str(text or "")))


# --------------------------------------------------------------------------
#   The budget
# --------------------------------------------------------------------------

@dataclass
class Budget:
    """Cloud requests per minute and per day, counted on disk.

    On disk rather than in memory because the limit is meant to survive a
    restart. A per-process counter resets every time the backend is restarted,
    which on a desktop is several times a day - and a daily cap you can clear
    by restarting is not a cap.
    """

    per_minute: int = 15
    per_day: int = 800
    minute_hits: list = field(default_factory=list)
    day_hits: list = field(default_factory=list)
    path: Optional[Path] = None

    _lock = threading.RLock()

    @classmethod
    def _store_path(cls) -> Path:
        base = Path(fw.CONFIG_DIR) if fw is not None else Path.home() / ".openjarvis"
        return base / "budget.json"

    @classmethod
    def load(cls) -> "Budget":
        b = cls(per_minute=int(_cfg("budget", "requests_per_minute", 15) or 15),
                per_day=int(_cfg("budget", "requests_per_day", 800) or 800),
                path=cls._store_path())
        try:
            raw = json.loads(b.path.read_text(encoding="utf-8"))
            # Each list separately: one corrupt element in `minute` used to
            # discard a perfectly good `day` array, and `day` is the cap that
            # matters.
            for key, dest in (("minute", "minute_hits"), ("day", "day_hits")):
                try:
                    setattr(b, dest, [float(x) for x in (raw.get(key) or [])])
                except (TypeError, ValueError):
                    continue
        except Exception:
            # A missing or corrupt budget file means "no cloud calls recorded",
            # which is the permissive direction - but the alternative is
            # refusing every cloud turn because a JSON file has a stray comma,
            # and the cap is a cost control, not a safety control.
            pass
        b._prune()
        return b

    def _prune(self) -> None:
        now = time.time()
        self.minute_hits = [t for t in self.minute_hits if now - t < 60]
        self.day_hits = [t for t in self.day_hits if now - t < 86400]

    def save(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"minute": self.minute_hits,
                                       "day": self.day_hits}), encoding="utf-8")
            tmp.replace(self.path)          # atomic; a torn file reads as empty
        except Exception:
            pass

    def spend(self, n: int = 1) -> None:
        """Record cloud requests, re-reading the file first.

        jarvis_hud calls Budget.load() PER REQUEST on a threading server, so
        several Budget objects exist at once, each holding a snapshot. Without
        the re-read, two of them each spending five wrote five to disk instead
        of ten - half the day's usage lost, and a cap that does not cap.
        """
        with self._lock:
            now = time.time()
            fresh = {"minute": [], "day": []}
            if self.path is not None:
                try:
                    fresh = json.loads(self.path.read_text(encoding="utf-8"))
                except Exception:
                    fresh = {"minute": list(self.minute_hits),
                             "day": list(self.day_hits)}
            try:
                self.minute_hits = [float(x) for x in fresh.get("minute", [])]
                self.day_hits = [float(x) for x in fresh.get("day", [])]
            except (TypeError, ValueError):
                pass
            for _ in range(max(1, n)):
                self.minute_hits.append(now)
                self.day_hits.append(now)
            self._prune()
            self.save()

    def minute_exceeded(self) -> bool:
        self._prune()
        return len(self.minute_hits) >= self.per_minute

    def day_exceeded(self) -> bool:
        self._prune()
        return len(self.day_hits) >= self.per_day

    def allows_cloud(self) -> bool:
        return not (self.minute_exceeded() or self.day_exceeded())

    def status(self) -> dict:
        self._prune()
        return {
            "per_minute": self.per_minute,
            "per_day": self.per_day,
            "used_this_minute": len(self.minute_hits),
            "used_today": len(self.day_hits),
            "minute_exceeded": self.minute_exceeded(),
            "day_exceeded": self.day_exceeded(),
            "cloud_allowed": self.allows_cloud(),
        }


# --------------------------------------------------------------------------
#   The decision
# --------------------------------------------------------------------------

@dataclass
class Decision:
    lane: str
    reason: str
    gate: str
    complexity: float = 0.0
    inject_memory: bool = False
    tainted: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def is_local_lane(lane: str, local_model: str = "") -> bool:
    """Is this lane running on this machine?

    Name-based, and that is a weakness worth stating: a lane called
    "jarvis-local" that someone pointed at a remote Ollama would read as local
    here. backend/README.md already records the same hazard for OLLAMA_URL -
    "the local model is ALSO egress if OLLAMA_URL does not point at this
    machine" - and the loopback assertion for that lives with the caller that
    opens the socket, which is the only place it can be checked honestly.
    """
    lane = str(lane or "")
    if local_model and lane == local_model:
        return True
    return bool(re.search(r"local|jarvis-primary|ollama", lane, re.I))


def complexity(query: str) -> float:
    """A rough 0-1 score. Longer, more clause-heavy questions score higher.

    INFERRED - only the threshold survived (`[routing] complexity_threshold =
    0.40`, "enforced today by choose() gate 2"). The scale is therefore known
    to be 0-1 with 0.40 meaning "hard enough to consider escalating", and the
    formula below is this file's, not the original's. It is deliberately dull:
    a clever scorer that nobody can predict makes routing feel random.
    """
    q = " ".join(str(query or "").split())
    if not q:
        return 0.0
    words = len(q.split())
    score = min(words / 120.0, 0.6)
    score += 0.1 * min(q.count(",") + q.count(";"), 2)
    if re.search(r"\b(why|how|compare|explain|design|prove|trade-?off)\b", q, re.I):
        score += 0.15
    if re.search(r"\b(step by step|in detail|thoroughly)\b", q, re.I):
        score += 0.1
    return round(min(score, 1.0), 3)


def choose(query: str, local_model: str = "", lanes: Optional[list] = None,
           has_image: bool = False, conversation_tainted: bool = False,
           budget: Optional[Budget] = None, tainted: Optional[bool] = None,
           **_extra) -> Decision:
    """Which lane answers this turn.

    Five gates, in this order, and the order is the policy. Each one can only
    send the answer DOWNWARD toward local - none of them can escalate past a
    gate that already refused.

      0. no cloud lanes offered      -> local
      1. the conversation is tainted -> local, unconditionally
      2. private content matched     -> local
      3. not complex enough          -> local
      4. budget spent                -> local
      otherwise                      -> the first cloud lane

    THE PARAMETER IS `conversation_tainted`, AND THAT IS NOT A DETAIL.

    This was called `tainted`, with `**_extra` to absorb anything unexpected.
    jarvis_hud.py:1714 passes `conversation_tainted=tainted`, so `**_extra`
    silently ate it and gate 1 - the one described here as "local,
    unconditionally" - NEVER FIRED from the only production caller. A
    conversation that had read outside text went to a cloud lane, with
    `decision.tainted` reported False so the route header agreed. No
    exception, no log line.

    That is the whole argument against a permissive `**kwargs` on a function
    that makes a privacy decision: it converts a TypeError at startup, which
    someone fixes in a minute, into an open gate nobody can see. `**_extra`
    is still here so an unknown argument cannot take down every chat turn -
    but anything it catches is now RECORDED, because a silently ignored
    argument to this function is exactly the bug above.
    """
    if tainted is not None:
        # The older spelling, kept working rather than broken.
        conversation_tainted = bool(conversation_tainted) or bool(tainted)
    if _extra:
        try:
            if fw is not None:
                fw.audit_log("router.unknown_argument",
                             {"names": sorted(_extra.keys())})
        except Exception:
            pass
    lanes = list(lanes or [])
    c = complexity(query)
    local = local_model or "local"
    # Whether the "local" lane IS local, rather than assuming it. `local_model`
    # comes from a state file (jarvis_models.current_model()), not a constant,
    # so a caller can hand this function a CLOUD model as its "local" lane.
    # Computing inject_memory from the gate meant every safe-looking gate then
    # returned that cloud lane WITH memory attached - the exact thing the
    # module docstring promises cannot happen. Computed from the lane now.
    local_is_local = is_local_lane(local, local_model)

    def local_decision(gate: str, why: str) -> Decision:
        return Decision(local, why, gate, c,
                        inject_memory=local_is_local,
                        tainted=conversation_tainted)

    if not lanes:
        # "unavailable", not "no-lanes": jarvis_hud.py:1717 tests for exactly
        # this string to rewrite the reason when Jarvis is injecting memory
        # itself. A different name left that branch dead.
        return local_decision("unavailable", "no cloud lane was offered")
    if conversation_tainted:
        return local_decision(
            "taint",
            "this conversation has read outside text, so it stays on this machine")
    if is_private(query):
        return local_decision("private", "the question matches the private-topic backstop")
    if c < float(_cfg("routing", "complexity_threshold", 0.40) or 0.40):
        return local_decision("complexity", f"complexity {c} is under the threshold")

    b = budget or Budget.load()
    if not b.allows_cloud():
        which = "daily" if b.day_exceeded() else "per-minute"
        return local_decision("budget", f"the {which} cloud budget is spent")

    lane = lanes[0]
    if has_image and len(lanes) > 1:
        vision = next((l for l in lanes if re.search(r"vision|vl|image", l, re.I)), None)
        if vision:
            lane = vision
    return Decision(lane, f"complexity {c} and budget available", "escalate", c,
                    inject_memory=False, tainted=conversation_tainted)


def degrade(lane: str, lanes: Optional[list] = None,
            local_model: str = "") -> Optional[str]:
    """One step down from `lane`, or None if there is nowhere lower.

    NEVER returns `lane`. jarvis_hud calls this after a lane refused and
    retries with the result; returning the input would retry the refusing lane
    for ever. The caller checks `if not nxt or nxt == lane: break` as a second
    guard, and that guard should never fire.

    The chain is `[budget].degrade_chain` when the current lane is in it,
    otherwise the caller's own `lanes` list, and local is always the floor.
    """
    lane = str(lane or "")
    local = local_model or "local"
    chain = list(_cfg("budget", "degrade_chain", []) or [])
    order = chain if lane in chain else list(lanes or [])

    # Seen lanes are skipped, so a chain that lists a lane twice - or a
    # `lanes` list that CONTAINS local_model, which jarvis_hud:1738 shows is a
    # real state - cannot produce a 2-cycle. It could before: degrade("a",
    # ["a","b"], "a") gave "b" and degrade("b", ["a","b"], "a") gave "a",
    # which never returns its own input and so slipped past the caller's
    # `nxt == lane` guard while re-opening a lane that had just refused.
    if lane in order:
        seen = {lane}
        for nxt in order[order.index(lane) + 1:]:
            if nxt and nxt not in seen:
                return nxt
            seen.add(nxt)
    # Bottom of the chain, or a lane nobody listed. Local is always the floor,
    # and the floor has nothing below it.
    return local if lane != local else None


def status() -> dict:
    return {"budget": Budget.load().status(),
            "complexity_threshold": _cfg("routing", "complexity_threshold", 0.40),
            "degrade_chain": _cfg("budget", "degrade_chain", []),
            "private_terms": len(_PRIVATE_TERMS)}


if __name__ == "__main__":
    for k, v in status().items():
        print(f"  {k:<22} {v}")
