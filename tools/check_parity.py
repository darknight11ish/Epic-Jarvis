#!/usr/bin/env python3
"""Compare what the desktop can do against what the phone can do, and fail
when the answer has changed without anyone deciding about it.

    python3 tools/check_parity.py

The two apps are both clients of the same Python backend, so the set of
`/api/...` routes each one calls is a fair, machine-readable proxy for its
feature surface. That is the whole idea here: parity as a check rather than a
promise. A document saying "the phone is up to date" is worth nothing a week
later; this fails the build. CI runs it on every push (.github/workflows/ci.yml).

What it reads - all from THIS checkout:

  desktop  jarvis-desktop/src-tauri/src/**/*.rs   the Rust side
           jarvis-desktop/src/**/*.{js,mjs,html}   the windows, which call
                                                   routes themselves too
  phone    jarvis-client/app/src/main/java/**/*.kt

Comments are stripped before routes are collected, so a route a file only
TALKS about (a KDoc line, a "// /api/graph is desktop-only" note) does not
count as a call.

It used to read the desktop from a separate branch (claude/jarvis-desktop-
tauri-vey6bc, last touched 19 Sep) and only its Rust, so it checked a desktop
that no longer existed, missed every route the JavaScript calls, and still
called the model routes out of scope after the owner allowed them on the
phone (18 and 20 Sep).

Failures - each one means a decision is missing or has gone stale:

  1. The desktop calls a route that is not classified below.
  2. A route classified `ported` is not called by the phone.
  3. A route classified `deliberate` (kept OFF the phone) IS called by the
     phone. Either a rule was broken or the decision changed; say which.
  4. A classified route the desktop no longer calls.

A route marked `todo` that the phone has started calling is a warning, not
a failure: it means "reclassify as ported", which is good news.

A route marked `planned` is built on the backend and neither app calls it
yet (the backend is written first, then each app builds against it). It is
exempt from rule 4. The moment the desktop calls it, a warning says to
reclassify it (`ported` once the phone calls it too, else `todo`).
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESKTOP_DIRS = [
    ("jarvis-desktop/src-tauri/src", (".rs",)),
    ("jarvis-desktop/src", (".js", ".mjs", ".html")),
]
PHONE_DIRS = [("jarvis-client/app/src/main/java", (".kt",))]

ROUTE = re.compile(r"/api/[a-zA-Z0-9/_-]+")

# Every route the desktop calls, and what the phone does about it.
#
# "ported"       - the phone calls it too; checked
# "deliberate"   - a decision was made NOT to port it; the reason is the
#                  point, and the phone calling it is a failure
# "todo"         - portable and wanted, nobody has done it yet
# "not-backend"  - not a Jarvis route at all: the desktop calls Ollama's own
#                  API on loopback under the same /api/ prefix
# "planned"      - on the backend, for both apps, and neither calls it yet
CLASSIFICATION = {
    "/api/appearance": ("ported", ""),
    "/api/approve": ("ported", ""),
    "/api/attention": ("ported", ""),
    "/api/attention/mute": ("ported", ""),
    "/api/attention/unmute": ("ported", ""),
    "/api/chat": ("ported", ""),
    "/api/compute": ("ported", "Brain screen, read-only."),
    "/api/config": ("deliberate", "Deep config editing on the phone is explicitly out of scope (CLAUDE.md)."),
    "/api/content-risk": ("ported", "Brain screen, read-only."),
    "/api/deny": ("ported", ""),
    "/api/digest": ("ported", ""),
    "/api/digest/seen": ("ported", ""),
    "/api/events": ("ported", ""),
    "/api/feedback/mark": ("ported", ""),
    "/api/graph": ("deliberate", "The memory graph is explicitly out of scope on the phone (CLAUDE.md)."),
    "/api/holds/cancel": ("ported", ""),
    "/api/initiative": ("ported", "Brain screen, read-only."),
    "/api/jobs": ("ported", ""),
    "/api/jobs/cancel": ("ported", ""),
    "/api/ledger": ("ported", "Brain screen, read-only."),
    "/api/memory/decide": ("ported", "The review queue: one card, one decision."),
    "/api/memory/edit": ("deliberate", "Rewording stored facts is deep memory editing; it stays on the desktop's Memory tab."),
    "/api/memory/export": ("deliberate", "A copy of everything Jarvis knows does not belong on a phone that can be lost."),
    "/api/memory/facts": ("ported", ""),
    "/api/memory/forget": ("deliberate", "Deep memory editing; it stays on the desktop's Memory tab."),
    "/api/memory/keep_both": ("ported", ""),
    "/api/memory/learning": ("todo", "The learning on/off switch. Small and read/write; whether the phone gets it is being decided in the memory work."),
    "/api/memory/pending": ("ported", "The review queue."),
    "/api/memory/sleep_time": ("ported", ""),
    "/api/memory/status": ("todo", "Memory counts and whether search-by-meaning is on. Read-only; would suit the Brain screen."),
    "/api/models": ("ported", "Allowed by the owner 2026-09-18: the installed list, not a catalogue."),
    "/api/models/install": ("ported", "Allowed by the owner 2026-09-20: a typed name, raising an approval card."),
    "/api/models/rollback": ("ported", ""),
    "/api/models/switch": ("ported", "Allowed by the owner 2026-09-18, raising an approval card."),
    "/api/notes/capture": ("ported", ""),
    "/api/pending": ("ported", ""),
    "/api/power": ("ported", ""),
    "/api/second-card": ("ported", "The second graphics card's switches (backend/second-card.patch, 2026-09-24). Desktop: Settings, Second graphics card (vision.rs reads it for pictures). Phone: Mind screen's Second graphics card plate, and chat's photo button. What was found plus one switch at a time; each ON is an approval card."),
    "/api/retrieve": ("todo", "The HUD's retrieval trace (which facts an answer reached for). Not in JARVIS-API.md yet; decide what it should show before porting."),
    "/api/show": ("not-backend", "Ollama's /api/show on loopback: does the model take pictures (vision.rs)."),
    "/api/shutdown": ("deliberate", "Shutting the backend down from a phone is a foot-gun: the phone would then have nothing to reach and no way to undo it."),
    "/api/skills": ("ported", "Brain screen, read-only."),
    "/api/skills/decide": ("todo", "Removing a skill. Same gate as an approval, so it fits the existing inbox."),
    "/api/status": ("ported", ""),
    "/api/tags": ("not-backend", "Ollama's /api/tags on loopback: the installed model list (commands.rs). Not a Jarvis route."),
    "/api/task/note": ("ported", ""),
    "/api/task/pause": ("ported", ""),
    "/api/task/resume": ("ported", ""),
    "/api/task/stop": ("ported", ""),
    "/api/undo": ("ported", ""),
    "/api/undo/revert": ("ported", ""),
    "/api/version": ("ported", ""),
    "/api/visual-spec": ("deliberate", "The phone bundles its own copy of the spec and checks it in a unit test (SpecDriftTest); JARVIS-API.md: the phone never fetches it."),
    "/api/voice/say": ("ported", ""),
    "/api/voice/status": ("ported", ""),
    "/api/voice/utterance": ("ported", ""),
    "/api/voice/wake": ("ported", "The wake-word switch; turning it on raises an approval card."),
    "/api/watch": ("todo", "Watches - what Jarvis is keeping an eye on. Probably the single most useful unported feature."),
    "/api/watch/add": ("todo", "Creating a watch from the phone."),
    "/api/watch/remove": ("todo", "Removing a watch."),
    "/api/watch/report": ("todo", "A watch's findings."),
    "/api/watch/seen": ("todo", "Marking a watch report read."),
}
STATUSES = {"ported", "deliberate", "todo", "not-backend", "planned"}

_BLOCK = re.compile(r"/\*.*?\*/", re.S)
_HTML = re.compile(r"<!--.*?-->", re.S)
# `//` at the start of a line, or after whitespace - never the `//` inside
# "http://", which has a colon before it.
_LINE = re.compile(r"(^|\s)//.*$", re.M)


def strip_comments(text: str, ext: str) -> str:
    if ext == ".html":
        text = _HTML.sub("", text)
    return _LINE.sub(r"\1", _BLOCK.sub("", text))


def routes_in(text):
    return {m.rstrip("/") for m in ROUTE.findall(text)}


def scan(dirs):
    found = {}
    for rel, exts in dirs:
        base = os.path.join(ROOT, rel)
        if not os.path.isdir(base):
            print(f"::error::{rel} is not in this checkout; has it moved?")
            sys.exit(2)
        for dirpath, _, names in os.walk(base):
            if "node_modules" in dirpath:
                continue
            for n in names:
                ext = os.path.splitext(n)[1]
                if ext not in exts:
                    continue
                path = os.path.join(dirpath, n)
                with open(path, encoding="utf-8", errors="replace") as fh:
                    for r in routes_in(strip_comments(fh.read(), ext)):
                        found.setdefault(r, set()).add(os.path.relpath(path, ROOT))
    return found


def main():
    desk_at = scan(DESKTOP_DIRS)
    phone_at = scan(PHONE_DIRS)
    desk, phone = set(desk_at), set(phone_at)
    problems, warnings = [], []

    for r, (s, _) in CLASSIFICATION.items():
        if s not in STATUSES:
            problems.append(f"{r} has an unknown status {s!r}.")

    for r in sorted(desk - set(CLASSIFICATION)):
        problems.append(
            f"{r} is called by the desktop ({', '.join(sorted(desk_at[r]))}) and is not "
            "classified in tools/check_parity.py. Someone added a feature; decide whether "
            "the phone should have it.")

    by = lambda st: {r for r, (s, _) in CLASSIFICATION.items() if s == st}  # noqa: E731
    for r in sorted(by("ported") - phone):
        problems.append(
            f"{r} is classified 'ported' but the phone does not call it. "
            "The classification has drifted from the code.")
    for r in sorted(by("deliberate") & phone):
        problems.append(
            f"{r} is classified 'deliberate' (kept off the phone: {CLASSIFICATION[r][1]}) "
            f"but the phone calls it ({', '.join(sorted(phone_at[r]))}).")
    for r in sorted(by("todo") & phone):
        warnings.append(f"{r} is 'todo' but the phone now calls it - reclassify it as 'ported'.")
    for r in sorted(by("planned") & desk):
        warnings.append(f"{r} is 'planned' but the desktop now calls it - reclassify it as "
                        f"'ported' (if the phone calls it too) or 'todo'.")
    for r in sorted(by("planned") & phone - desk):
        warnings.append(f"{r} is 'planned' and the phone calls it; the desktop does not yet.")
    for r in sorted(set(CLASSIFICATION) - desk - by("planned")):
        problems.append(
            f"{r} is classified here but the desktop no longer calls it. "
            "Remove it, or find out where it went.")

    todo, no = sorted(by("todo")), sorted(by("deliberate"))
    print(f"desktop: {len(desk)} routes   phone: {len(phone)}   "
          f"ported: {len(by('ported'))}   not porting: {len(no)}   still to port: {len(todo)}   "
          f"not the backend's: {len(by('not-backend'))}   "
          f"planned (backend first): {len(by('planned'))}")
    if todo:
        print("\nStill to port:")
        for r in todo:
            print(f"  {r:<26} {CLASSIFICATION[r][1]}")
    ahead = sorted(phone - desk)
    if ahead:
        print("\nOn the phone and not the desktop (parity runs both ways):")
        for r in ahead:
            print(f"  {r}")
    for w in warnings:
        print(f"::warning::{w}")
    if problems:
        print("\n" + "=" * 60)
        for p in problems:
            print(f"::error::{p}")
        return 1
    print("\nNo undecided drift.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
