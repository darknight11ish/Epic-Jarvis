#!/usr/bin/env python3
"""Compare what the desktop can do against what the phone can do, and fail
when the answer has changed without anyone deciding about it.

The two apps are both clients of the same Python backend, so the set of
`/api/...` routes each one calls is a fair, machine-readable proxy for its
feature surface. That is the whole idea here: parity as a check rather than a
promise. A document saying "the phone is up to date" is worth nothing a week
later; this fails the build.

Two failure modes, and the second is the one that keeps the first honest:

  1. The desktop calls a route that is not classified below. Somebody added a
     feature and nobody decided whether the phone should have it.
  2. A route classified `ported` is not actually called by the phone. The
     classification has drifted from the code and is now a lie.

The desktop lives on its own branch, so this fetches it. That is deliberate:
pinning a copy of the desktop's route list into this repo would be one more
thing to go stale, which is the exact failure being guarded against.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESKTOP_BRANCH = os.environ.get("JARVIS_DESKTOP_REF", "origin/claude/jarvis-desktop-tauri-vey6bc")
DESKTOP_PATH = "jarvis-desktop/src-tauri/src"
PHONE_PATH = "jarvis-client/app/src/main/java/com/jarvis/client"

ROUTE = re.compile(r"/api/[a-zA-Z0-9/_-]+")

# Every route the desktop calls, and what the phone does about it.
#
# "ported"       - the phone calls it too; the check verifies that is still true
# "deliberate"   - a decision was made NOT to port it; the reason is the point
# "todo"         - portable and wanted, nobody has done it yet
CLASSIFICATION = {
    "/api/appearance": ("todo", "Sync the face, theme and state bindings. The route already exists - see docs/APPEARANCE-SYNC-PROPOSAL.md, which was written believing it did not."),
    "/api/approve": ("ported", ""),
    "/api/attention": ("ported", ""),
    "/api/attention/mute": ("ported", ""),
    "/api/attention/unmute": ("ported", ""),
    "/api/chat": ("ported", ""),
    "/api/compute": ("todo", "Compute/resource telemetry. Read-only and small; would suit the brain screen."),
    "/api/config": ("deliberate", "Deep config editing on the phone is explicitly out of scope."),
    "/api/content-risk": ("todo", "Risk classification for content. Relevant to how approvals are presented."),
    "/api/deny": ("ported", ""),
    "/api/digest": ("ported", ""),
    "/api/digest/seen": ("ported", ""),
    "/api/events": ("ported", ""),
    "/api/graph": ("deliberate", "The memory graph is explicitly out of scope on the phone."),
    "/api/holds/cancel": ("ported", ""),
    "/api/initiative": ("todo", "What Jarvis proposes on its own. Arguably belongs next to approvals."),
    "/api/jobs": ("ported", ""),
    "/api/jobs/cancel": ("ported", ""),
    "/api/ledger": ("todo", "The record of what Jarvis has done. A natural phone screen."),
    "/api/memory/decide": ("deliberate", "Memory graph, out of scope."),
    "/api/memory/pending": ("deliberate", "Memory graph, out of scope."),
    "/api/memory/status": ("deliberate", "Memory graph, out of scope."),
    "/api/models": ("deliberate", "The model catalogue is explicitly out of scope on the phone."),
    "/api/models/install": ("deliberate", "Model catalogue, out of scope."),
    "/api/models/rollback": ("deliberate", "Model catalogue, out of scope."),
    "/api/models/switch": ("deliberate", "Model catalogue, out of scope."),
    "/api/pending": ("ported", ""),
    "/api/shutdown": ("deliberate", "Shutting the backend down from a phone is a foot-gun: the phone would then have nothing to reach and no way to undo it."),
    "/api/skills": ("todo", "Which skills are installed. Read-only view is portable; installing is not."),
    "/api/skills/decide": ("todo", "Approving a skill. Same gate as an approval, so it fits the existing inbox."),
    "/api/status": ("ported", ""),
    "/api/tags": ("todo", "Tag vocabulary. Small, and makes the digest more legible."),
    "/api/undo": ("ported", ""),
    "/api/undo/revert": ("ported", ""),
    "/api/version": ("ported", ""),
    "/api/watch": ("todo", "Watches - what Jarvis is keeping an eye on. Probably the single most useful unported feature."),
    "/api/watch/add": ("todo", "Creating a watch from the phone."),
    "/api/watch/remove": ("todo", "Removing a watch."),
    "/api/watch/report": ("todo", "A watch's findings."),
    "/api/watch/seen": ("todo", "Marking a watch report read."),
}


def routes_in(text):
    return {m.rstrip("/") for m in ROUTE.findall(text)}


def desktop_routes():
    try:
        listing = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", DESKTOP_BRANCH, "--", DESKTOP_PATH],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    except subprocess.CalledProcessError:
        print(f"::error::cannot read {DESKTOP_BRANCH}. Fetch it, or set JARVIS_DESKTOP_REF.")
        sys.exit(2)
    if not listing:
        print(f"::error::{DESKTOP_BRANCH} has no files under {DESKTOP_PATH}; has the desktop moved?")
        sys.exit(2)
    found = set()
    for f in listing:
        blob = subprocess.run(["git", "show", f"{DESKTOP_BRANCH}:{f}"],
                              cwd=ROOT, capture_output=True, text=True)
        if blob.returncode == 0:
            found |= routes_in(blob.stdout)
    return found


def phone_routes():
    found = set()
    for dirpath, _, names in os.walk(os.path.join(ROOT, PHONE_PATH)):
        for n in names:
            if n.endswith(".kt"):
                with open(os.path.join(dirpath, n), encoding="utf-8") as fh:
                    found |= routes_in(fh.read())
    return found


def main():
    desk = desktop_routes()
    phone = phone_routes()
    problems = []

    unclassified = sorted(desk - set(CLASSIFICATION))
    for r in unclassified:
        problems.append(
            f"{r} is called by the desktop and is not classified in tools/check_parity.py. "
            "Someone added a feature; decide whether the phone should have it.")

    claimed = {r for r, (s, _) in CLASSIFICATION.items() if s == "ported"}
    for r in sorted(claimed - phone):
        problems.append(
            f"{r} is classified 'ported' but the phone does not call it. "
            "The classification has drifted from the code.")

    stale = sorted(set(CLASSIFICATION) - desk)
    for r in stale:
        problems.append(
            f"{r} is classified here but the desktop no longer calls it. "
            "Remove it, or find out where it went.")

    todo = sorted(r for r, (s, _) in CLASSIFICATION.items() if s == "todo")
    no = sorted(r for r, (s, _) in CLASSIFICATION.items() if s == "deliberate")
    print(f"desktop: {len(desk)} routes   phone: {len(phone)}   "
          f"ported: {len(claimed)}   not porting: {len(no)}   still to port: {len(todo)}")
    if todo:
        print("\nStill to port:")
        for r in todo:
            print(f"  {r:<26} {CLASSIFICATION[r][1]}")
    ahead = sorted(phone - desk)
    if ahead:
        print("\nOn the phone and not the desktop (parity runs both ways):")
        for r in ahead:
            print(f"  {r}")

    if problems:
        print("\n" + "=" * 60)
        for p in problems:
            print(f"::error::{p}")
        return 1
    print("\nNo undecided drift.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
