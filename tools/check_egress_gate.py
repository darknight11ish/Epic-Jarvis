#!/usr/bin/env python3
"""Every path to one of the six cloud hosts must name the egress gate.

    py -3 tools/check_egress_gate.py [-v]

WHAT THIS IS, IN PLAIN WORDS
Jarvis is local-first, but it is not local-only: four independent senders can
reach a company's language-model service on the internet. Until this lane there
was no single place that decided whether a request may leave. That place is
`backend/jarvis_egress_gate.py`; a sender asks it by calling `check_egress(...)`
before it opens a socket.

WHAT IT CHECKS
Every `.py` under `backend/`, `jarvis-backend/` and `tools/` that names one of
the six cloud hosts is either:

  * a file that also names `check_egress` in the same file - the sender has the
    gate in it; or
  * a file in ALLOWED below, with a one-line reason saying why its host name is
    not a way out of this PC.

WHY AN UNLISTED HIT IS A FAILURE, NOT A WARNING
This program's whole promise is that nothing leaves unless something decided
it could. A warning is a line a fast reader scrolls past; a new sender that
does not ask the gate would then arrive silently, ship, and look exactly like
every green run before it. The previous shape of this problem is why the lane
exists at all: six providers, four senders, each with its own rules. So a new
host name with no gate and no entry here fails the run, with the file and line
printed, and the fix is deliberate - wire the gate, or add an entry with the
reason the name cannot send anything.

WHAT IT CANNOT DECIDE, SAID OUT LOUD
This is a TEXT check. It proves `check_egress` is named in the same file as the
host; it cannot prove every branch calls it, and it cannot see a host built at
runtime (from a config file or from a string joined out of pieces). It is the
same limit `tools/check_invoke_grants.py` states about names built at runtime:
the list makes the gap deliberate rather than invisible. The suites that drive
the two wired senders prove the call actually refuses and actually allows.

WHY THE ALLOW-LIST IS THIS SHAPE
Each key is the exact repository path, never a glob, and each value is one
line. A new hit has to be added by a person who wrote down why. The list is
checked both ways: an entry whose file has gone, or which no longer names a
host, is reported too, so the reasons cannot quietly stop being true.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOTS = ("backend", "jarvis-backend", "tools")

#: The six hosts the chatbot driver's presets talk to. The same six names are
#: in `docs/ARCHITECTURE.md` section 4's list of named ways out.
HOSTS = (
    "api.openai.com",
    "api.deepseek.com",
    "api.mistral.ai",
    "openrouter.ai",
    "api.groq.com",
    "api.x.ai",
)

#: What a wired sender names. Kept as one constant so this file and its own
#: docstring use the same spelling.
GATE = "check_egress"

#: path -> one-line reason its host name is not a way out that skips the gate.
#: Every entry is an EXACT path. A suite is listed because its host strings are
#: fixtures and its transport is replaced; a production sender is listed only
#: because it belongs to the second lane, and the reason says so.
ALLOWED = {
    # A SUITE, not a sender (2026-11-17). test_speed_record.py builds a fake
    # usage record in order to price one answer: the host and url below are
    # fixture STRINGS that are never opened, and the request itself is stubbed.
    # Without this entry the census named two lines of a test and the `audit`
    # job went red on every branch built after #1337.
    "backend/test_speed_record.py":
        "a suite; its host and URL are fixture strings on a fake usage record, and no "
        "socket is opened",
    "backend/jarvis_search.py":
        "the web-search sender (second lane): it posts to DeepSeek's tools/search and "
        "is deliberately not wired in this PR; listed so the second lane cannot miss it",
    "jarvis-backend/jarvis_search.py":
        "the base's twin of the same web-search sender; same second-lane reason",
    "tools/gen_quiz_cloud_cases.py":
        "generates the recorded quiz-cloud cases; its host fields are fixture data and "
        "it opens no socket",
    "tools/check_egress_gate.py":
        "this checker itself: it names the six hosts only in order to search for them",
    "backend/test_agent.py":
        "a suite; the host appears in a comment about the cloud preset, not in a request",
    "backend/test_chatbot_api.py":
        "a suite; hosts are fixtures and assertions, and its provider is a fake "
        "127.0.0.1 server or a replaced HTTP hook",
    "backend/test_cloud_honesty_state.py":
        "a suite; the host is an expected value in an assertion on the driver's words",
    "backend/test_cloud_spend.py":
        "a suite; the host is in a fixture row whose transport is replaced",
    "backend/test_ollama_direct.py":
        "a suite; the host is the refused URL it checks is never the one sent",
    "backend/test_options_understanding.py":
        "a suite; hosts are preset fixtures and expected copy",
    "backend/test_presets_cloud.py":
        "a suite; the host is in the card text it asserts",
    "backend/test_presets_owner_ui.py":
        "a suite; the host is in a preset fixture row",
    "backend/test_quiz_cloud.py":
        "a suite; hosts are fixtures and assertions, and every request goes through a "
        "replaced HTTP hook",
    "backend/test_reach.py":
        "a suite; the host is in a reach-register fixture row",
    "backend/test_reasoning_fallback.py":
        "a suite; the host is in a fake cloud request row whose transport is replaced",
    "backend/test_runtime_identity.py":
        "a suite; the host appears in a comment about the cloud preset",
    "backend/test_web_search.py":
        "a suite; the host is an expected value for jarvis_search's own URL",
}

SKIP_DIRS = {"__pycache__", ".git"}


def python_files() -> list[Path]:
    """Every .py file under the three roots, sorted, with no build residue."""
    out: list[Path] = []
    for root in ROOTS:
        for path in sorted((REPO / root).rglob("*.py")):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            out.append(path)
    return out


def host_lines(text: str) -> list[tuple[int, str]]:
    """(line number, host) for every line that names one of the six hosts."""
    out: list[tuple[int, str]] = []
    low = text.lower()
    for host in HOSTS:
        start = 0
        while True:
            at = low.find(host, start)
            if at < 0:
                break
            out.append((low[:at].count("\n") + 1, host))
            start = at + len(host)
    return out


def main() -> int:
    verbose = "-v" in sys.argv
    seen_allowed: set[str] = set()
    wired: list[str] = []
    allowed: list[str] = []
    violations: list[tuple[str, int, str]] = []

    for path in python_files():
        rel = path.relative_to(REPO).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = host_lines(text)
        if not hits:
            continue
        if rel in ALLOWED:
            seen_allowed.add(rel)
            allowed.append(rel)
            continue
        if GATE in text:
            wired.append(rel)
            continue
        violations.extend((rel, line, host) for line, host in hits)

    problems: list[str] = []
    for rel in ALLOWED:
        if not (REPO / rel).is_file():
            problems.append(f"{rel} is on the allow-list but is not in this checkout "
                            f"- remove the entry or restore the file")
        elif rel not in seen_allowed:
            problems.append(f"{rel} is on the allow-list but no longer names a cloud host "
                            f"- remove the entry, it is no longer true")

    if violations:
        print("::error::a cloud host is named by a file that does not name "
              f"{GATE} - wire the gate or add the file to ALLOWED with a reason:",)
        for rel, line, host in violations:
            print(f"  {rel}:{line}: {host}")
    for problem in problems:
        print(f"::error::{problem}")

    if violations or problems:
        print(f"\nFAIL  {len(violations)} unaccounted host mention(s), "
              f"{len(problems)} stale allow-list entr(ies).")
        return 1

    print(f"{len(wired) + len(allowed)} file(s) name one of the six cloud hosts: "
          f"{len(wired)} name {GATE}, {len(allowed)} are on the allow-list with a reason.")
    print(f"The allow-list is {len(ALLOWED)} exact path(s); an unlisted host name would fail this run.")
    if verbose:
        for rel in sorted(allowed):
            print(f"  allowed  {rel}")
            print(f"           {ALLOWED[rel]}")
        for rel in sorted(wired):
            print(f"  wired    {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
