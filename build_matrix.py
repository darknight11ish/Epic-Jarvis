"""Build the evidence index for the field-test matrix.

    py -3 build_matrix.py

Reads features/features.json (127 entries) and searches the DATED artifacts in
the owner's checkout for each feature's own words + a small alias table. Writes
.matrix.json beside this file. NO verdict is decided here: this only finds
candidates WITH their file and line, so every verdict in the document can name
where it came from.

Evidence tiers, by path:
  DEVICE  a record of the app actually running on a device (a tour, a pass, an
          audit that drove it) - the only tier that can make FIELD-TESTED
  REPORT  an audit or review document (read, not driven)
  SUITE   a backend suite in this repository that names the feature
  XMLNAME a uiautomator dump whose FILENAME names a screen (weak: the screen
          existed on the phone; it does not prove the feature worked)

Files over 512 KB are skipped, and logcat dumps are skipped outright - they are
45 MB of unrelated noise and would drown every match.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

MAIN = Path(r"C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main")
#: THIS worktree's own committed list (127 at main 70077268). The main
#: checkout's WORKING copy is being edited by another teammate right now and
#: read 122 when this was first run - never take the list from there.
HERE = Path(__file__).resolve().parent
FEATURES = HERE / "features" / "features.json"

DEVICE_DIRS = ("phone-pass-2026-10-11", "desktop-pass-2026-10-11", "device-tour",
               "device-audit", "multi-device")
REPORT_DIRS = ("surfaces-audit", "settings-audit", "audit-findings")

#: THE tight device set: the two PASS records that ran the app and wrote down a
#: result per feature. A mention in a tour or audit document is a REVIEW, not a
#: run, so those are REPORT tier here - the loose first pass matched copied .kt
#: files and called 118 features tested, which was wrong.
DEVICE_FILES = (
    "phone-pass-2026-10-11/README.md",
    "desktop-pass-2026-10-11/FINDINGS.md",
    "desktop-pass-2026-10-11/gap-table.md",
    "desktop-pass-2026-10-11/chat-turn.log",
    "desktop-pass-2026-10-11/sweep-results.tsv",
)
#: A tour document names what was SEEN, which is one step short of a per-feature
#: pass; it is kept in the REPORT tier on purpose.
DEVICE_DOC_FILES = ()
DEVICE_DOCS = ()
REPORT_DOCS = ("BUG-AUDIT", "AUDIT-PASS", "SESSION-HANDOFF", "FEATURE-AUDIT",
               "ANDROID-TOUR", "ANDROID-DEVICE-AUDIT", "ANDROID-AUDIT")
TEXT_EXT = {".md", ".txt", ".json", ".log", ".tsv", ".ps1", ".kt", ".py"}
MAX_BYTES = 512 * 1024

STOP = set("""the a an and or of to in on for with your you it is are was were be been
this that these those from at as by not no all any some more most other into out up
down over under again then once here there when where why how what which who whom
while about after before between during through above below off very own same so than
too can will just should now each few both own s t don t jarvis""".split())

#: ids whose own words are too common to search for on their own
GENERIC = set("""typing voice search answer help home brain now settings phone device
desktop app cards card list run start stop open close show hide test send read write
save forget remember ask card speak talk live look watch focus timer alarm model
models memory note notes email mail calendar inbox tidy rule rules""".split())

#: extra words that mean THIS feature, per id. Kept short and distinctive.
ALIAS = {
    "typing": ["type a question", "the jarvis bar", "alt+space"],
    "voice-in": ["hold to talk", "talk button", "push to talk"],
    "hands-free": ["hey jarvis", "wake word", "hands-free"],
    "live": ["jarvis live", "live session"],
    "look-at-this": ["look at this"],
    "watch-with-me": ["watch with me"],
    "coach": ["coach this", "prompt coach"],
    "focus": ["focus session", "focus buddy"],
    "timers": ["timer", "set a timer"],
    "reminders": ["remind me", "reminder"],
    "alarms": ["alarm"],
    "memory": ["saved fact", "remember that", "memory list"],
    "forget": ["forget a time frame", "erase the words"],
    "crisis": ["crisis", "988"],
    "inbox-tidy": ["inbox tidy", "archive", "mark read"],
    "web-search": ["web search", "searxng"],
    "model-switch": ["models/switch", "switch model"],
    "model-install": ["models/install", "install a model"],
    "from-now-on": ["from now on"],
    "what-asks-first": ["what asks first"],
    "email-read": ["read my email", "morning briefing"],
    "calendar": ["calendar", "ical"],
    "notes": ["obsidian", "logseq", "joplin"],
    "startup": ["first run", "setup wizard"],
    "pairing": ["pair", "qr code", "pairing"],
    "approvals": ["approval card", "approve"],
    "widget": ["widget"],
    "notifications": ["notification"],
    "smartwatch": ["smartwatch", "watch notification"],
    "backup": ["backup"],
    "updater": ["updater", "update"],
    "plugin": ["plugin", "mcp"],
    "screen": ["look at the screen", "screen picture"],
    "second-card": ["second card", "second graphics"],
    "hardware": ["hardware", "graphics card"],
    "models": ["model list", "ollama"],
    "profiles": ["profile"],
    "quartz": ["quartz"],
}


def terms_for(f: dict) -> list:
    out = []
    fid = str(f.get("id") or "")
    if fid:
        out.append(fid.replace("-", " "))
        if "-" in fid:
            out.append(fid.replace("-", "_"))
    for w in re.split(r"[^A-Za-z0-9+]+", str(f.get("title") or "")):
        w = w.strip()
        if len(w) >= 6 and w.lower() not in STOP:
            out.append(w)
    out.extend(ALIAS.get(fid, []))
    seen, keep = set(), []
    for t in out:
        t = t.lower().strip()
        if len(t) < 4 or t in seen:
            continue
        # a single generic word on its own proves nothing; require the alias or
        # a phrase. Single words are kept only when they are >= 7 chars.
        if " " not in t and (t in GENERIC or t in STOP):
            continue
        seen.add(t)
        keep.append(t)
    return keep


def tier_of(path: Path) -> str:
    s = path.as_posix()
    if "/.dsh-scratch/" in s:
        rel = s.split("/.dsh-scratch/", 1)[1]
        if rel in DEVICE_FILES or (False and rel.startswith("device-tour/transcript-")
                                   and rel.endswith(".txt")):
            return "DEVICE"
        name = rel.split("/")[0]
        if name in REPORT_DIRS or name in DEVICE_DIRS:
            return "REPORT"
        return "OTHER"
    if "/docs/" in s:
        if path.name in DEVICE_DOC_FILES:
            return "DEVICE"
        base = path.name
        if any(base.startswith(x) for x in DEVICE_DOCS):
            return "DEVICE"
        if any(base.startswith(x) for x in REPORT_DOCS):
            return "REPORT"
    return "OTHER"


def corpus():
    files = []
    for d in DEVICE_DIRS + REPORT_DIRS:
        root = MAIN / ".dsh-scratch" / d
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in TEXT_EXT:
                continue
            if p.name.startswith("logcat") or p.suffix == ".kt":
                continue
            try:
                if p.stat().st_size > MAX_BYTES:
                    continue
            except OSError:
                continue
            files.append(p)
    docs = MAIN / "docs"
    for p in docs.glob("*.md"):
        if p.stat().st_size > MAX_BYTES:
            continue
        if tier_of(p) in ("DEVICE", "REPORT"):
            files.append(p)
    return files


def xml_names():
    """Filenames of the uiautomator dumps - a WEAK signal: the screen was on the
    phone. Only the phone-pass and tour dumps count."""
    out = []
    for d in ("phone-pass-2026-10-11", "device-tour", "device-audit"):
        root = MAIN / ".dsh-scratch" / d
        if root.is_dir():
            for p in root.rglob("*.xml"):
                out.append(p.name.lower())
    return out


def suites():
    out = {}
    for root in (MAIN / "backend", MAIN / "tools"):
        if not root.is_dir():
            continue
        for p in root.glob("*"):
            if p.is_file() and p.suffix in (".py",):
                out[p.name.lower()] = p
    return out


def main() -> int:
    feats = json.loads(FEATURES.read_text(encoding="utf-8"))
    files = corpus()
    names = xml_names()
    suite_files = suites()

    all_terms = {}
    per_feature = {}
    for f in feats:
        tl = terms_for(f)
        per_feature[f["id"]] = tl
        for t in tl:
            all_terms.setdefault(t, []).append(f["id"])
    pattern = re.compile("|".join(re.escape(t) for t in sorted(all_terms, key=len, reverse=True)))

    hits = {f["id"]: {"DEVICE": [], "REPORT": [], "OTHER": []} for f in feats}
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        tier = tier_of(p)
        if tier not in hits[feats[0]["id"]]:
            tier = "OTHER"
        rel = str(p).replace(str(MAIN), "").replace("\\", "/")
        for m in pattern.finditer(text):
            term = m.group(0)
            line = text.count("\n", 0, m.start()) + 1
            for fid in all_terms[term]:
                slot = hits[fid][tier]
                if len(slot) < 4 and not any(h["file"] == rel for h in slot):
                    slot.append({"file": rel, "line": line, "term": term})

    rows = []
    for f in feats:
        fid = f["id"]
        sname = [n for n in suite_files
                 if fid.replace("-", "_") in n or fid.replace("-", "") in n.replace("_", "")]
        xml = sorted({n for n in names
                      if fid.replace("-", "") in n.replace("-", "").replace("_", "")})
        rows.append({"id": fid, "group": f.get("group"), "title": f.get("title"),
                     "surface": f.get("surface"),
                     "terms": per_feature[fid],
                     "device": hits[fid]["DEVICE"], "report": hits[fid]["REPORT"],
                     "suite": sname[:4], "xml": xml[:4]})

    (HERE / ".matrix.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    nd = sum(1 for r in rows if r["device"])
    nr = sum(1 for r in rows if not r["device"] and r["report"])
    ns = sum(1 for r in rows if not r["device"] and not r["report"] and r["suite"])
    nn = sum(1 for r in rows if not (r["device"] or r["report"] or r["suite"]))
    print(f"files searched: {len(files)}   xml names: {len(names)}   suite files: {len(suite_files)}")
    print(f"with a DEVICE hit: {nd}   REPORT only: {nr}   SUITE only: {ns}   nothing: {nn}")
    print("wrote .matrix.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
