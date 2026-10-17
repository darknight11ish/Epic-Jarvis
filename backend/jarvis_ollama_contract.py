"""jarvis_ollama_contract.py - does Jarvis's picture of a model match the model?

    import jarvis_ollama_contract as contract

    report = contract.probe("qwen3:8b")          # once at start-up
    report = contract.probe("qwen3:8b")          # and again when the model changes
    print(contract.text(report))                 # one plain sentence for the owner

WHY THIS EXISTS

Jarvis is CAPABILITY-DRIVEN, NOT VERSION-GATED - a deliberate choice, and the
right one (`jarvis_hardware.py`, in `_limits`: "By the cards alone, so a new
Ollama version does not forget that a size did not fit"). Jarvis never branches
on Ollama's version number. It asks at runtime what a model can do, three
reads:

  * `_model_can_use_tools()`    - /api/show -> "capabilities" -> "tools"
    (`jarvis_agent.py:3666`, `:3668`)
  * `_model_can_see_pictures()` - /api/show -> "capabilities" -> "vision"
    (`jarvis_agent.py:5740`, `:5742`)
  * `supports_thinking()`       - /api/show -> "capabilities" -> "thinking"
    (`jarvis_thinking.py:249`)

THE HOLE THIS FILLS. `backend/test_ollama_capability_contract.py` (branch
`fix/ollama-capability-contract-guard`, PR #451) is the STATIC half: it reads
Jarvis's own source and fails if the vocabulary, the field name, the endpoint or
the three-state wiring changes. That is the right guard, and this module does
not repeat it. What a static pin cannot see is what OLLAMA SAID on this machine
today: a field that stops arriving, a capability name Jarvis has never heard of,
or a model that plainly has a capability while the list Jarvis reads does not
name it. This module is the RUNTIME half - the same contract, asked of the real
server. The two are meant to be read together, and
`backend/test_ollama_contract.py`'s `t_the_static_guard_agrees_when_it_is_here`
holds them together the moment PR #451 lands.

THE THREE OUTCOMES, AND WHAT EACH MEANS

  (a) UNDERSTOOD          - a capability list came back, Jarvis knows every name
                            on it, and nothing Jarvis uses is absent. Say
                            nothing; there is nothing to fix.
  (b) UNKNOWN_CAPABILITIES - the list carries at least one name Jarvis has never
                            heard of (Ollama grows new ones). LOG IT ONCE and
                            carry on. This is NOT an error and never blocks
                            anything: an extra name cannot take tools or vision
                            away, because those reads ask for one name each.
  (c) MISSING_EXPECTED    - a capability Jarvis USES, which this model's own
                            /api/show metadata plainly shows it has, is absent
                            from the list Jarvis reads. That is the under-use
                            this module exists to name: Jarvis will answer
                            without tools it could have offered, or drop a
                            picture it could have shown the model.

There is also a fourth state, and it is deliberately NOT an outcome:

  * `verdict is None`     - Ollama did not send a usable list at all (absent
                            field, a value that is not a list, or an empty one),
                            and the metadata shows nothing missing. Jarvis cannot
                            tell what this model can do. That is exactly the
                            state `_model_can_use_tools()` calls `None`...

WHY `None` IS NOT A FOURTH OUTCOME, SAID PLAINLY. The brief for this work asked
for exactly three outcomes, and there are exactly three VERDICTS. But "Ollama
did not answer" is not an answer, and folding it into UNDERSTOOD would be the
same class of false pass this project keeps writing down ("a missing summary is
NOT a pass"). It is reported as no verdict, it is logged once, and it never
reads as understood. `VERDICTS` below holds the three; `probe()` may return
`None` instead of one of them, and `Report.usable` says which happened.

WHY THE EVIDENCE IS CONSERVATIVE, ON PURPOSE

Outcome (c) is only reported when the SAME /api/show answer carries structural
evidence that the model has the capability - a `model_info` key naming a vision
encoder, a non-empty `projector_info`, or a chat template that branches on
`.Tools` or `enable_thinking`. Prose is not evidence. A missed detection leaves
the probe quiet (the old, silent behaviour); a wrong detection tells the owner
their model is being under-used when it is not. Given the choice, this probe
stays quiet - and says so, rather than pretending its silence is proof.

WHAT THIS CANNOT VERIFY, SAID PLAINLY. Ollama's own source is not in this
repository, so the FIELD NAMES this probe looks for as evidence (`model_info`,
`projector_info`, `template`) cannot be checked here, and neither can the
capability strings Ollama uses today. If Ollama names one of them differently,
`_plainly_has()` returns no evidence and outcome (c) simply never fires. That is
a false negative, never a false alarm - and it is recorded here rather than
papered over. The one thing this module CAN prove from a checkout is which
endpoint it asks and which strings it compares, and its suite pins exactly that
against `jarvis_agent.py` and `jarvis_thinking.py`.

WHAT IT DOES NOT DO. It downloads nothing, loads nothing, unloads nothing,
deletes nothing, writes no file, opens no route, raises no approval card, and
changes no setting. It makes ONE read-only POST to `/api/show`, which reads the
model's own metadata and loads nothing (`jarvis_big_coder.py:318-319`). It never
reads `/api/version`, and no version number is compared anywhere in this file -
see `t_no_version_is_read_or_compared` in its suite, which proves that by
behaviour and not only by reading the source.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.request
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

# --------------------------------------------------------------------------
#   THE CONTRACT - every literal here came from a line of Jarvis's own code
# --------------------------------------------------------------------------
#
# These are the SAME literals `backend/test_ollama_capability_contract.py`
# (PR #451) pins on the reader side. They live here too because the runtime
# probe has to speak the same vocabulary, and the suite fails if the two ever
# drift apart.

#: The one endpoint this probe asks. `jarvis_agent.py:3666`, `:5740`.
SHOW_ENDPOINT = "/api/show"

#: The field the capability list arrives in. `jarvis_agent.py:3666`, `:5740`.
SHOW_FIELD = "capabilities"

#: The three outcomes. Nothing else is a verdict.
UNDERSTOOD = "understood"
UNKNOWN_CAPABILITIES = "unknown_capabilities"
MISSING_EXPECTED = "missing_expected"
VERDICTS: Tuple[str, ...] = (UNDERSTOOD, UNKNOWN_CAPABILITIES, MISSING_EXPECTED)

#: The capability names JARVIS ITSELF reads - the only ones whose absence can
#: make Jarvis under-use a model. `tools` (jarvis_agent.py:3668), `vision`
#: (jarvis_agent.py:5742), `thinking` (jarvis_thinking.py:249).
JARVIS_USES: Tuple[str, ...] = ("tools", "vision", "thinking")

#: Names that are never news. `completion` is on every model Ollama serves; the
#: rest are the ones Jarvis reads. A name that is NOT here is logged once as
#: outcome (b) - which is the point of (b), not a fault.
KNOWN_CAPABILITIES: Tuple[str, ...] = ("completion",) + JARVIS_USES

#: Structural marks, in the answer, that a model plainly has a capability.
#: Deliberately narrow: see "WHY THE EVIDENCE IS CONSERVATIVE" above.
_VISION_MARKS = ("vision", "clip", "mmproj", "projector", "image_encoder")
_TOOLS_MARKS = (".tools", "tool_call")
_THINKING_MARKS = ("enable_thinking", ".thinking")

#: Where Ollama lives when nothing says otherwise. The same default
#: jarvis_thinking.py uses (`_ollama_url()`, line 210).
DEFAULT_URL = "http://127.0.0.1:11434"


class _Logged:
    """One finding is surfaced ONCE, not once per start-up.

    A plain dict of keys under a lock - the same shape as every other small
    cache in this backend. `forget()` is here for a long-running process whose
    owner has already seen the line, and for the suite.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._seen: set = set()

    def first_time(self, key) -> bool:
        with self._lock:
            if key in self._seen:
                return False
            self._seen.add(key)
            return True

    def clear(self) -> None:
        with self._lock:
            self._seen.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._seen)


_LOGGED = _Logged()


def forget() -> None:
    """Let every finding be surfaced once more. Nothing else is remembered."""
    _LOGGED.clear()


@dataclass(frozen=True)
class Report:
    """What one probe found. `verdict` is one of `VERDICTS`, or None for the
    honest "Ollama did not answer" state - which is never a pass."""

    model: str
    url: str
    said: Optional[Tuple[str, ...]]
    verdict: Optional[str]
    unknown: Tuple[str, ...] = ()
    missing: Tuple[str, ...] = ()
    note: str = ""
    when: str = ""

    @property
    def usable(self) -> bool:
        """Did Ollama send a capability list Jarvis can read at all?"""
        return self.said is not None

    @property
    def needs_saying(self) -> bool:
        """Should this be surfaced? Everything except plain "understood"."""
        return self.verdict != UNDERSTOOD


# --------------------------------------------------------------------------
#   Asking
# --------------------------------------------------------------------------

def default_url() -> str:
    """Where to ask: `OLLAMA_HOST` if it is set, otherwise loopback."""
    return (os.environ.get("OLLAMA_HOST") or DEFAULT_URL).rstrip("/")


def _ask(url: str, model: str, *, timeout: float = 3.0) -> Optional[dict]:
    """Ask `{url}/api/show` about `model`. The parsed body, or None.

    Read-only: /api/show reads the model's own metadata and loads nothing
    (`jarvis_big_coder.py:318-319`). Never raises - a probe that raised would
    take the start-up path down with it, which is worse than saying nothing.
    """
    try:
        request = urllib.request.Request(
            f"{str(url).rstrip('/')}{SHOW_ENDPOINT}",
            data=json.dumps({"model": model}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            body = json.loads(answer.read().decode("utf-8"))
        return body if isinstance(body, dict) else None
    except Exception:                                       # noqa: BLE001
        return None


# --------------------------------------------------------------------------
#   Reading the answer - no I/O, so the suite can drive every case
# --------------------------------------------------------------------------

def _capability_list(show) -> Optional[Tuple[str, ...]]:
    """The names Ollama listed, in its own order, deduped. None when it did not
    say.

    EXACTLY the rule Jarvis's own two reads use
    (`jarvis_agent.py:3667`, `:5741`: `isinstance(caps, list) and caps`): an
    absent field, a value that is not a list, and an EMPTY list all mean "Ollama
    did not say". None of them means "the model cannot" - that is what keeps a
    field-type change from silently removing every tool.
    """
    if not isinstance(show, dict):
        return None
    caps = show.get(SHOW_FIELD)
    # Spelled the same way the reader spells it, so the pin in the suite can be
    # the same pin: `isinstance(caps, list) and caps`.
    if not (isinstance(caps, list) and caps):
        return None
    names: List[str] = []
    for raw in caps:
        name = str(raw).strip().lower()
        if name and name not in names:
            names.append(name)
    return tuple(names) or None


def _plainly_has(show) -> frozenset:
    """The capabilities this answer's OWN metadata shows the model has.

    Structural evidence only, from the one response:
      * a `model_info` key naming a vision encoder (`clip.has_vision_encoder`
        and friends) - keys are matched, never prose;
      * a non-empty `projector_info` (a vision projector is attached);
      * a chat template or Modelfile that branches on `.Tools` / `tool_call`
        or on `enable_thinking` / `.thinking`.

    A field name this version of Ollama does not use yields NO evidence, so the
    probe stays quiet. See the module docstring: a false negative, never a false
    alarm.
    """
    out: set = set()
    if not isinstance(show, dict):
        return frozenset()

    info = show.get("model_info")
    if isinstance(info, dict):
        for key in info:
            text = str(key).lower()
            if any(mark in text for mark in _VISION_MARKS):
                out.add("vision")

    projector = show.get("projector_info")
    if isinstance(projector, dict) and projector:
        out.add("vision")

    body = " ".join(str(show.get(key) or "")
                    for key in ("template", "modelfile", "system")).lower()
    if any(mark in body for mark in _TOOLS_MARKS):
        out.add("tools")
    if any(mark in body for mark in _THINKING_MARKS):
        out.add("thinking")
    return frozenset(out)


def _note(verdict: Optional[str], said, missing, unknown) -> str:
    """One plain sentence, in the owner's words, for each outcome."""
    listed = ", ".join(said) if said else "nothing"
    if verdict == MISSING_EXPECTED:
        names = ", ".join(repr(name) for name in missing)
        return (f"Jarvis is about to under-use this model: Ollama's own answer "
                f"shows this model has {names}, but its {SHOW_FIELD} list "
                f"({listed}) does not name it, so Jarvis will do without it.")
    if verdict == UNKNOWN_CAPABILITIES:
        names = ", ".join(repr(name) for name in unknown)
        return (f"Ollama lists a capability Jarvis does not know - {names} - "
                f"beside the ones it does ({listed}). This is not an error: "
                f"Jarvis carries on and uses what it knows.")
    if verdict == UNDERSTOOD:
        return (f"Ollama says this model can do: {listed}. Jarvis knows every "
                f"one of those names.")
    return (f"Ollama sent no usable {SHOW_FIELD} list for this model, so Jarvis "
            f"cannot tell what it can do. Nothing is known to be missing, and "
            f"this is NOT a pass.")


def classify(show, *, model: str = "", url: str = "", when: str = "") -> Report:
    """Sort one /api/show answer into the three outcomes. No I/O, never raises.

    The precedence is deliberate: a capability Jarvis uses that the model
    plainly has comes first, because that is the one that costs the owner
    something. An unknown name is news, not a fault, so it comes next.
    """
    said = _capability_list(show)
    evidence = _plainly_has(show)
    known = set(KNOWN_CAPABILITIES)

    unknown = tuple(sorted(name for name in (said or ()) if name not in known))
    missing = tuple(sorted(name for name in JARVIS_USES
                           if name in evidence and (said is None or name not in said)))

    if missing:
        verdict: Optional[str] = MISSING_EXPECTED
    elif said is None:
        # Ollama did not answer a question Jarvis asked. Reported as no verdict,
        # never as "understood" - see the module docstring.
        verdict = None
    elif unknown:
        verdict = UNKNOWN_CAPABILITIES
    else:
        verdict = UNDERSTOOD

    return Report(model=str(model), url=str(url), said=said, verdict=verdict,
                  unknown=unknown, missing=missing,
                  note=_note(verdict, said, missing, unknown), when=str(when))


# --------------------------------------------------------------------------
#   The probe - what the two moments call
# --------------------------------------------------------------------------

def _log_line(report: Report) -> str:
    moment = f" ({report.when})" if report.when else ""
    return f"jarvis_ollama_contract: {report.model or 'this model'}{moment}: {report.note}"


def _to_stderr(line: str) -> None:
    """The default surface: one line where the backend's own output goes.

    Never a file, never a database, never a client. An unsolicited owner-facing
    notification is a decision for whoever wires this (jarvis_arbiter.deliver()
    is the one door for that), not something a probe does behind their back.
    """
    try:
        print(line, file=sys.stderr)
    except Exception:                                       # noqa: BLE001
        pass


def probe(model: str, url: Optional[str] = None, *,
          ask: Optional[Callable[[str, str], Optional[dict]]] = None,
          log: Optional[Callable[[str], None]] = None,
          when: str = "") -> Report:
    """Ask Ollama about `model` and say which of the three outcomes it is.

    Call this ONCE AT START-UP and AGAIN WHENEVER THE MODEL CHANGES - `when` is
    the moment, for the log line only ("startup", "model changed"). Everything
    else is returned, so a caller that wants the sentence in front of the owner
    can hand `text(report)` to the surface it already has.

    `ask` and `log` are injectable so the suite drives every case with no
    socket and no console. Never raises.
    """
    where = str(url or default_url())
    asked = ask or _ask
    try:
        show = asked(where, model)
    except Exception:                                       # noqa: BLE001
        show = None

    report = classify(show, model=model, url=where, when=when)

    if report.needs_saying:
        # ONCE per finding, so a start-up loop cannot fill the log with the same
        # line - and a genuinely new finding on another model still gets through.
        key = (report.url, report.model, report.verdict, report.unknown,
               report.missing)
        if _LOGGED.first_time(key):
            (log or _to_stderr)(_log_line(report))
    return report


def text(report: Report) -> str:
    """The plain sentence for the owner, naming the model it is about."""
    who = report.model or "this model"
    return f"{who}: {report.note}" if report.note else f"{who}: nothing to report."
