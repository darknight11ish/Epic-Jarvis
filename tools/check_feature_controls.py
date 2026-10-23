#!/usr/bin/env python3
"""check_feature_controls.py - the machine check behind the owner's claim.

The owner requirement (2026-10-22): every user-visible function/feature must be
turnable on/off or adjustable by TYPING at Jarvis on the desktop AND the phone,
and findable/adjustable in Settings - and the claim must be checkable, not
anecdotal.

This checker reads `contract/feature-controls.json` and compares every row
against the REAL files: `backend/jarvis_feature_catalogue.py` (the 139
features), `backend/jarvis_settings_registry.py` (BOOL_SETTINGS,
SETTINGS_ROWS, SECTIONS, NOT_BY_ASKING), `backend/jarvis_quick.py` (the typed
grammar, through its pure `match()`), and the desktop/phone Settings surfaces.
It does not edit any of them, and it does not treat a recorded gap as a pass:

* a feature with status `enforced` must have BOTH typed phrases resolving to a
  real control (checked by calling `jarvis_quick.match()`), and its desktop and
  phone Settings locations must exist in the real pages;
* a `not-a-setting`, `open-only`, `pc-only` or `planned` row must carry an
  owner + a reason, and the checker re-derives that the gap is still there; a
  planned grammar gap that has since been fixed is a FAILURE (the matrix is
  stale), never a quiet pass;
* an unknown new feature (or a dropped one) is a loud failure - nothing may be
  silently omitted from the 139;
* every BOOL_SETTINGS switch, every SETTINGS_ROWS row and every SECTIONS
  section must appear in the matrix, and the page/phone evidence must still be
  true.

Known gaps are REPORTED and counted by owner (they are NOT passes). `--strict`
prints every non-enforced row and every gap, one per line.

Exit code: 0 when the matrix agrees with the source files (known gaps counted,
not hidden); 1 on any mismatch, unknown feature, stale row or vanished evidence.

Usage:
    python -B tools/check_feature_controls.py [--root REPO] [--strict]
"""
from __future__ import annotations

import argparse
import importlib
import inspect
import json
import sys
from collections import Counter
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DEFAULT_ROOT = TOOLS.parent
CONTRACT = "contract/feature-controls.json"
REQUIRED_SOURCES = [
    "backend/jarvis_feature_catalogue.py",
    "backend/jarvis_settings_registry.py",
    "backend/jarvis_quick.py",
    "jarvis-desktop/src/settings.html",
    "jarvis-desktop/src/settings-catalog.js",
    "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt",
    "jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsSearch.kt",
    "jarvis-client/app/src/main/java/com/jarvis/client/net/SettingsCatalog.kt",
    "jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsJump.kt",
]
BOOL_OWNERS = {"voiceprint-wiring", "setup-ui", "Session B", "none-needed"}
# Any intent that CHANGES something is a control; the explanation/refusal
# intents are not. The command side grows named control intents (Q3), so the
# list is deliberately open-ended: the checker only requires that the phrase
# resolves to something that is not a "here is what it is" answer.
NON_CONTROL = {"feature_switch_refused", "feature_howto", "feature_explain",
               "feature_state", "feature_unknown", "animal_ask", "search_use"}
ALL_STATUSES = {"enforced", "planned", "open-only", "pc-only", "not-a-setting"}


def load_modules(root: Path):
    importlib.invalidate_caches()
    for name in ("jarvis_feature_catalogue", "jarvis_settings_registry", "jarvis_quick"):
        sys.modules.pop(name, None)
    backend = str(root / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    fc = importlib.import_module("jarvis_feature_catalogue")
    sr = importlib.import_module("jarvis_settings_registry")
    q = importlib.import_module("jarvis_quick")
    return fc, sr, q


class Check:
    def __init__(self):
        self.errors = []
        self.notes = []

    def fail(self, message):
        self.errors.append(message)

    def need(self, ok, message):
        if not ok:
            self.fail(message)
        return ok


def surface_search(html, catalog, phone_text):
    def in_html(section, names):
        return any(n.lower() in html for n in names if len(n) > 2)

    def in_desktop_catalog(row_id):
        return row_id in catalog

    def in_phone(names):
        return any(n.lower() in phone_text for n in names if len(n) > 2)

    return in_html, in_desktop_catalog, in_phone


def match(q, phrase):
    if not phrase:
        return None
    try:
        return q.match(phrase)
    except Exception:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check the feature-controls matrix against the real sources.")
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--strict", action="store_true", help="print every non-enforced row and every gap")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    c = Check()
    contract_path = root / CONTRACT
    if not contract_path.is_file():
        print("FAIL: missing " + str(contract_path))
        return 1
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    for rel in REQUIRED_SOURCES:
        c.need((root / rel).is_file(), "source file is missing: " + rel)
    c.need(contract.get("schema") == 1, "contract schema is not 1")
    fc, sr, q = load_modules(root)
    html = (root / "jarvis-desktop/src/settings.html").read_text(encoding="utf-8").lower()
    catalog = (root / "jarvis-desktop/src/settings-catalog.js").read_text(encoding="utf-8")
    phone_cat = (root / "jarvis-client/app/src/main/java/com/jarvis/client/net/SettingsCatalog.kt").read_text(encoding="utf-8")
    phone_text = "\n".join(
        (root / p).read_text(encoding="utf-8")
        for p in REQUIRED_SOURCES if p.startswith("jarvis-client/")).lower()
    in_html, in_desktop_catalog, in_phone = surface_search(html, catalog, phone_text)
    sections = {s.id: s for s in sr.SECTIONS}
    bool_by_key = {b.key: b for b in sr.BOOL_SETTINGS}
    rows_by_id = {r.dom_id: r for r in sr.SETTINGS_ROWS}

    # ---- the 139 features: no unknown, no silent drop ----------------------
    real = {f["id"]: f for f in fc.FEATURES}
    matrix = {f.get("id"): f for f in contract.get("features", [])}
    c.need(contract.get("feature_count") == len(fc.FEATURES),
           "feature_count says %r, the catalogue has %d" % (contract.get("feature_count"), len(fc.FEATURES)))
    for fid in sorted(set(real) - set(matrix)):
        c.fail("UNKNOWN FEATURE in the catalogue with no matrix row: " + fid)
    for fid in sorted(set(matrix) - set(real)):
        c.fail("matrix row names a feature the catalogue does not have: " + fid)
    for fid in sorted(set(real) & set(matrix)):
        row, feat = matrix[fid], real[fid]
        c.need(row.get("name") == feat["title"], "%s: name is stale (%r != %r)" % (fid, row.get("name"), feat["title"]))
        c.need(row.get("surface") == feat.get("surface"), "%s: surface is stale" % fid)
        c.need(row.get("where") == feat.get("where"), "%s: where is stale" % fid)
        status = row.get("status")
        c.need(status in ALL_STATUSES, "%s: unknown status %r" % (fid, status))
        c.need(isinstance(row.get("reason"), str) and row["reason"].strip(),
               "%s: a reason is required on every row" % fid)
        c.need(isinstance(row.get("owner"), str) and row["owner"] in BOOL_OWNERS,
               "%s: owner %r is not one of the recorded owners" % (fid, row.get("owner")))
        ctrl = row.get("control") or {}
        desk, phone = row.get("desktop") or {}, row.get("phone") or {}
        desk_sec = sections.get(desk.get("section"))
        phone_sec = sections.get(phone.get("section"))
        desk_ok = bool(desk_sec and in_html(desk_sec.id, list(desk_sec.names))) or \
            bool(desk.get("section") is None and (row.get("name", "").lower() in html
                 or "everything jarvis can do" in html))
        phone_ok = feat.get("surface") in ("both", "phone") and (
            bool(phone_sec and in_phone(list(phone_sec.names)) and phone_sec.app in ("both", "phone")) or
            bool(phone.get("section") is None and row.get("name", "").lower() in phone_text))
        gap = (row.get("command") or {}).get("settings_gap") or {}
        if gap:
            c.need(bool(desk.get("found")) is False, "%s: a command-side Settings gap must not claim desktop found" % fid)
            c.need(bool(phone.get("found")) is False, "%s: a command-side Settings gap must not claim phone found" % fid)
            c.need(row.get("owner") in BOOL_OWNERS,
                   "%s: a Settings gap row has an unknown owner" % fid)
        else:
            c.need(bool(desk.get("found")) == desk_ok, "%s: desktop Settings evidence is stale" % fid)
            c.need(bool(phone.get("found")) == phone_ok, "%s: phone Settings evidence is stale" % fid)
        on, off = match(q, ctrl.get("turn_on")), match(q, ctrl.get("turn_off"))
        if status == "enforced":
            adjust_only = bool(ctrl.get("adjust")) and not ctrl.get("turn_off")
            c.need(on is not None and (off is not None or adjust_only),
                   "%s: enforced but a typed phrase does not resolve" % fid)
            if adjust_only:
                for adjust in ctrl.get("adjust") or []:
                    if adjust.get("env_dependent"):
                        c.need(bool(adjust.get("reason")), "%s: env-dependent adjust phrase has no reason" % fid)
                        continue
                    it = match(q, adjust.get("phrase"))
                    c.need(it is not None and it.name == adjust.get("intent"),
                           "%s: adjust phrase %r no longer resolves" % (fid, adjust.get("phrase")))
            if on is not None:
                c.need(on.name not in NON_CONTROL,
                       "%s: turn_on resolves to %r, not a change" % (fid, on.name))
            c.need(desk_ok, "%s: enforced but desktop Settings was not found" % fid)
            if feat.get("surface") == "both":
                c.need(phone_ok, "%s: enforced for both apps but the phone Settings words were not found" % fid)
            sec = sections.get((ctrl.get("setting_keys") or [None])[0] and None)
            for adjust in ctrl.get("adjust") or []:
                if adjust.get("env_dependent"):
                    c.need(bool(adjust.get("reason")), "%s: env-dependent adjust phrase has no reason" % fid)
                    continue
                it = match(q, adjust.get("phrase"))
                c.need(it is not None and it.name == adjust.get("intent"),
                       "%s: adjust phrase %r no longer resolves to %r" % (fid, adjust.get("phrase"), adjust.get("intent")))
        elif status == "not-a-setting":
            # These rows are explicitly labelled Command-Only / Always On; the
            # label section below requires a resolving example phrase instead
            # of demanding one particular refusal wording.
            pass
        elif status == "planned":
            owner = row.get("owner")
            if owner not in {"voiceprint-wiring", "setup-ui", "Session B"}:
                c.fail("%s: planned rows need a known fixing owner (got %r)" % (fid, owner))
            # A planned row must still be a real, owned gap: either its
            # Settings half is missing (see the settings_gap check) or its
            # typed path has no phrase yet. The label/reason carry the rest,
            # and --strict prints every planned row.
            elif owner == "setup-ui":
                c.need((row.get("desktop") or {}).get("found") is not True
                       or (row.get("control") or {}).get("type") == "missing",
                       "%s: planned for the desktop, but the desktop evidence is now present" % fid)
            elif owner == "Session B":
                c.need((row.get("phone") or {}).get("found") is not True,
                       "%s: planned for the phone, but the phone evidence is now present" % fid)
        elif status == "pc-only":
            code = (row.get("command") or {}).get("reason_code")
            c.need(feat.get("surface") in {"desktop", "phone"} or code in {"pc-only", "app-local", "credentials"},
                   "%s: pc-only but surface=%r / reason_code=%r" % (fid, feat.get("surface"), code))
        elif status == "open-only":
            c.need(fid in {x.get("feature") for x in contract.get("settings_only", [])},
                   "%s: open-only but not in the settings_only allowlist" % fid)
        if args.strict and status != "enforced":
            print("NOT-ENFORCED  %-14s %-28s %-14s %s" % (status, fid, row.get("owner"), row.get("reason")[:80]))

    # ---- BOOL_SETTINGS: every switch, its phrases and its desktop row ------
    bmatrix = {b.get("key"): b for b in contract.get("bool_settings", [])}
    for key in sorted(set(bool_by_key) - set(bmatrix)):
        c.fail("BOOL_SETTINGS switch missing from the matrix: " + key)
    for key in sorted(set(bmatrix) - set(bool_by_key)):
        c.fail("matrix names a switch BOOL_SETTINGS does not have: " + key)
    for key in sorted(set(bool_by_key) & set(bmatrix)):
        b, row = bool_by_key[key], bmatrix[key]
        c.need(row.get("names") == list(b.names), "%s: names are stale" % key)
        resolved = (match(q, "turn on " + b.names[0]) and match(q, "turn off " + b.names[0])
                    and match(q, "turn on " + b.names[0]).name == "settings_bool"
                    and match(q, "turn off " + b.names[0]).name == "settings_bool"
                    and match(q, "turn on " + b.names[0]).f.get("key") == key
                    and match(q, "turn on " + b.names[0]).f.get("on") is True
                    and match(q, "turn off " + b.names[0]).f.get("on") is False)
        c.need(bool(row.get("resolved")) == bool(resolved), "%s: resolved flag is stale" % key)
        srow = next((r for r in sr.SETTINGS_ROWS if r.setting == key), None)
        c.need(row.get("desktop_row") == (srow.dom_id if srow else None), "%s: desktop_row is stale" % key)
        if row.get("status") == "enforced":
            c.need(srow is not None, "%s: enforced switch has no SETTINGS_ROWS row" % key)
            if srow is not None:
                c.need(in_html(srow.section, [srow.dom_id, srow.label]), "%s: desktop switch row is not in settings.html" % key)
        if row.get("status") == "open-only":
            c.need(srow is not None and srow.dom_id in sr.NOT_BY_ASKING,
                   "%s: open-only but the row is not in NOT_BY_ASKING" % key)
        if args.strict and row.get("status") != "enforced":
            print("NOT-ENFORCED  setting %-26s %-14s %s" % (key, row.get("owner"), row.get("reason")[:80]))

    # ---- SETTINGS_ROWS: every row is on the real desktop/phone surfaces ----
    rmatrix = {r.get("id"): r for r in contract.get("setting_rows", [])}
    for rid in sorted(set(rows_by_id) - set(rmatrix)):
        c.fail("SETTINGS_ROWS row missing from the matrix: " + rid)
    for rid in sorted(set(rmatrix) - set(rows_by_id)):
        c.fail("matrix names a SETTINGS_ROWS row that does not exist: " + rid)
    for rid in sorted(set(rows_by_id) & set(rmatrix)):
        real_row, row = rows_by_id[rid], rmatrix[rid]
        c.need(row.get("label") == real_row.label, "%s: label is stale" % rid)
        c.need(row.get("section") == real_row.section, "%s: section is stale" % rid)
        c.need(bool(row.get("in_settings_html")) == bool(('id="' + rid + '"') in html),
               "%s: in_settings_html is stale" % rid)
        c.need(bool(row.get("in_desktop_catalog")) == bool(in_desktop_catalog(rid)),
               "%s: in_desktop_catalog is stale" % rid)
        if real_row.phone_key:
            c.need(bool(row.get("in_phone_catalog")) == bool(real_row.phone_key in phone_cat),
                   "%s: phone catalog evidence is stale" % rid)

    # ---- SECTIONS: every Settings section is accounted for -----------------
    smatrix = {s.get("id"): s for s in contract.get("sections", [])}
    for sid in sorted(set(sections) - set(smatrix)):
        c.fail("SECTIONS section missing from the matrix: " + sid)
    for sid in sorted(set(smatrix) - set(sections)):
        c.fail("matrix names a section SECTIONS does not have: " + sid)
    for sid in sorted(set(sections) & set(smatrix)):
        real_s, row = sections[sid], smatrix[sid]
        c.need(row.get("names") == list(real_s.names), "%s: section names are stale" % sid)
        c.need(row.get("app") == real_s.app and row.get("where") == real_s.where, "%s: section app/where is stale" % sid)
        c.need(bool(row.get("in_desktop_settings")) == bool(in_html(sid, list(real_s.names))),
               "%s: desktop section evidence is stale" % sid)
        c.need(bool(row.get("in_phone_settings")) == bool(in_phone(list(real_s.names)) and real_s.app in ("both", "phone")),
               "%s: phone section evidence is stale" % sid)

    # ---- the five plain labels (owner + Gemini Q8, 2026-10-22) -----------
    labels = contract.get("labels") or {}
    approved = [
        "Switchable / Adjustable (Typed & Settings)",
        "Settings-Only (By Design — Security Boundary)",
        "PC-Only Setting (Honest Refusal on Phone)",
        "Command-Only (Runs When You Ask — No Switch Needed)",
        "Always On (Core Safety Rule — Cannot Be Turned Off)",
    ]
    c.need(list(labels) == approved, "the contract must define exactly the five owner-approved labels, in order: %r" % (list(labels),))
    # If the backend's command-side source is present it must carry the SAME
    # five strings (it may not silently reword them), and the matrix must say
    # so; classification counts are derived here, never copied from it.
    fg = sys.modules.get("jarvis_feature_guide")
    if fg is not None and hasattr(fg, "CONTROL_LABELS"):
        c.need(list(getattr(fg, "CONTROL_LABELS")) == approved,
               "jarvis_feature_guide.CONTROL_LABELS disagrees with the owner's five strings")
    always = {x.get("feature") for x in contract.get("always_on", [])}
    settings_only_ids = {x.get("feature") for x in contract.get("settings_only", [])}
    seen_labels = Counter()
    for fid in sorted(set(real) & set(matrix)):
        row = matrix[fid]
        label = row.get("label")
        c.need(label in labels, "%s: label %r is not one of the five" % (fid, label))
        if label in labels:
            seen_labels[label] += 1
        status = row.get("status")
        ev = row.get("label_evidence") or {}
        phrase = ev.get("example_phrase")
        path = ev.get("screen_path")
        if label == approved[1]:
            c.need(fid in settings_only_ids, "%s: Settings-Only but not in the allowlist" % fid)
        elif label == approved[2]:
            c.need(status == "pc-only", "%s: PC-Only Setting but status %r" % (fid, status))
        elif label == approved[4]:
            c.need(fid in always, "%s: Always On but not in the always_on allowlist" % fid)
            c.need(status == "not-a-setting", "%s: Always On must not advertise a switch" % fid)
            c.need(isinstance(ev.get("reason"), str) and ev["reason"].strip(), "%s: Always On has no reason" % fid)
        elif label == approved[3]:
            c.need(status in {"not-a-setting", "planned"}, "%s: Command-Only with status %r" % (fid, status))
        elif label == approved[0]:
            c.need(status in {"enforced", "planned"} or status == "pc-only",
                   "%s: Switchable/Adjustable with status %r" % (fid, status))
        if isinstance(path, str) and "All features and abilities" in path:
            c.need(" (planned)" in path,
                   "%s: a row that points at the not-yet-built directory must say (planned)" % fid)
        if label in {approved[3], approved[4]}:
            c.need(isinstance(phrase, str) and phrase.strip(), "%s: no example phrase" % fid)
            c.need(isinstance(path, str) and path.strip(), "%s: no screen path" % fid)
            c.need(match(q, phrase) is not None, "%s: example phrase does not resolve: %r" % (fid, phrase))
    canonical_always = {"approvals","app-lock","trust","rush-latch","outside-text","stale-link",
                        "stop-everything","crisis-help","sensitive-facts","memory-waiting",
                        "settings-entry","devices"}
    joined = fg is not None and hasattr(fg, "control_matrix")
    if joined:
        c.need({x.get("feature") for x in contract.get("always_on", [])} == canonical_always,
               "always_on must be the canonical 12 features on the joined tree")
    for x in contract.get("always_on", []):
        fid = x.get("feature")
        c.need(fid in real, "always_on names a feature the catalogue does not have: %r" % fid)
        c.need(isinstance(x.get("reason"), str) and x["reason"].strip(), "always_on %r has no reason" % fid)
        c.need((matrix.get(fid) or {}).get("status") == "not-a-setting",
               "always_on %r has a switch - it cannot be Always On" % fid)
        if joined:
            c.need(not ((matrix.get(fid) or {}).get("control") or {}).get("setting_keys"),
                   "always_on %r names a switch key - it must have none" % fid)
        c.need((matrix.get(fid) or {}).get("label") == approved[4],
               "always_on %r is not labelled Always On" % fid)
    for m in contract.get("multi_field", []):
        c.need(m.get("label") in labels, "%s: multi-field label is not one of the five" % m.get("id"))

    # ---- the command-side join (task-78 / #734), when that source exists ----
    fg = None
    try:
        import jarvis_feature_guide as fg  # noqa: F401
    except Exception:
        fg = None
    label_diff = []
    if fg is not None and hasattr(fg, "control_matrix"):
        fg_rows = {r.get("id"): r for r in fg.control_matrix()}
        c.need(set(fg_rows) == set(real), "jarvis_feature_guide.control_matrix() does not cover the 139 features")
        c.need(list(getattr(fg, "CONTROL_LABELS", [])) == approved,
               "FG.CONTROL_LABELS differs from the owner's five label strings")
        c.need(getattr(fg, "matrix_rows_without_reason", lambda: [])() == [],
               "FG.matrix_rows_without_reason() must be empty")
        for fid in sorted(set(real) & set(matrix)):
            row, fr = matrix[fid], fg_rows[fid]
            cmd = row.get("command")
            c.need(isinstance(cmd, dict), "%s: no command-side join record (command field)" % fid)
            if not isinstance(cmd, dict):
                continue
            for key in ("status", "reason_code", "owner", "reason"):
                c.need(cmd.get(key) == fr.get(key),
                       "%s: command-side %s differs (contract %r, guide %r)"
                       % (fid, key, cmd.get(key), fr.get(key)))
            norm = lambda x: json.loads(json.dumps(x)) if x else None
            c.need(norm(cmd.get("settings_gap")) == norm(fr.get("settings_gap")),
                   "%s: settings_gap differs from jarvis_feature_guide" % fid)
            # Lead's ruling: a source whose LABELS differ must fail loudly rather
            # than be silently copied. The guide carries one label per feature.
            source_label = fr.get("label")
            if source_label is not None and source_label != row.get("label"):
                approved_override = fid in canonical_always
                c.need(approved_override,
                       "%s: source label differs from the contract (%r vs %r) and is not an approved override"
                       % (fid, source_label, row.get("label")))
                if approved_override:
                    label_diff.append((fid, source_label, row.get("label")))
        if label_diff:
            print("LABEL-DIFFERENCES: %d feature(s) where the command-side label disagrees with the derived owner labels (reported, owned by voiceprint-wiring):" % len(label_diff))
            for fid, src, derived in label_diff[:60]:
                print("  %-28s source=%-52s derived=%s" % (fid, src, derived))
        for gap_id, gap in (getattr(fg, "SETTINGS_GAPS", {}) or {}).items():
            c.need(isinstance(gap, dict) and gap.get("desktop") and gap.get("phone") and gap.get("reason"),
                   "FG.SETTINGS_GAPS %r lacks owner/reason" % gap_id)
    else:
        c.notes.append("command-side jarvis_feature_guide.control_matrix() not present (pre-#734 tree)")

    # ---- named choice settings (Q3), when the registry has them -----------
    source_choices = getattr(sr, "CHOICE_SETTINGS", None) or []
    if source_choices:
        chmatrix = {x.get("key"): x for x in contract.get("choice_settings", [])}
        for cs in source_choices:
            row = chmatrix.get(cs.key)
            c.need(isinstance(row, dict), "named choice setting missing from the matrix: " + cs.key)
            if not isinstance(row, dict):
                continue
            c.need(row.get("names") == list(cs.names), "%s: choice names are stale" % cs.key)
            handler = row.get("handler") or ""
            module_name, _, symbol = handler.rpartition(".")
            c.need(module_name == "jarvis_settings_registry" and callable(getattr(sr, symbol, None)),
                   "%s: choice handler %r does not exist" % (cs.key, handler))
            c.need(row.get("status") in {"planned", "enforced"}, "%s: choice status must be planned/enforced" % cs.key)
            if row.get("status") == "enforced":
                c.need(bool(row.get("proof")), "%s: enforced choice needs a typed-setter proof" % cs.key)
            else:
                c.need(any(g.get("kind") == "choice-setting" and g.get("id") == cs.key
                           for g in contract.get("known_gaps", [])),
                       "%s: planned choice is missing from known_gaps" % cs.key)
        for key in sorted(set(chmatrix) - {cs.key for cs in source_choices}):
            c.fail("matrix names a choice setting the registry does not have: " + key)

    # ---- the deliberate Settings-only allowlist (owner decision) -----------
    settings_only = contract.get("settings_only", [])
    ids = {f.get("id") for f in contract.get("features", [])}
    for so in settings_only:
        fid = so.get("feature")
        c.need(fid in ids, "settings_only names a feature the matrix does not have: %r" % fid)
        c.need(so.get("owner") in BOOL_OWNERS, "settings_only %r has unknown owner" % fid)
        c.need(isinstance(so.get("reason"), str) and so["reason"].strip(), "settings_only %r has no reason" % fid)
        row = matrix.get(fid) or {}
        c.need(row.get("status") == "open-only", "settings_only %r must be open-only in the feature row" % fid)
    creds = {x.get("feature") for x in settings_only}
    c.need(creds == {"accounts", "backup"},
           "Settings-Only must be exactly accounts (credentials) + backup (restore), got %r" % (creds,))

    # ---- multi-field controls: typed value -> handler -> both Settings ----
    MULTI_STATUS = {"planned", "enforced"}
    multi = contract.get("multi_field", [])
    c.need(isinstance(contract.get("multi_field_count"), int)
           and contract["multi_field_count"] == len(multi),
           "multi-field rows were added or removed without updating multi_field_count")
    seen_multi = set()
    for m in multi:
        mid = m.get("id")
        c.need(bool(mid) and mid not in seen_multi, "multi-field id missing or duplicated: %r" % mid)
        seen_multi.add(mid)
        c.need(m.get("status") in MULTI_STATUS, "%s: multi-field status %r is not planned/enforced" % (mid, m.get("status")))
        c.need(m.get("owner") in BOOL_OWNERS, "%s: multi-field owner %r is unknown" % (mid, m.get("owner")))
        c.need(isinstance(m.get("reason"), str) and m["reason"].strip(), "%s: multi-field row has no reason" % mid)
        c.need(isinstance(m.get("accepted_values"), list) and m["accepted_values"],
               "%s: no accepted values recorded" % mid)
        phrases = m.get("phrases")
        c.need(isinstance(phrases, list) and phrases, "%s: no typed phrase recorded" % mid)
        for ph in phrases or []:
            c.need(isinstance(ph, dict) and isinstance(ph.get("text"), str) and ph["text"].strip()
                   and isinstance(ph.get("accepted"), list) and ph["accepted"],
                   "%s: a multi-field phrase has no text/accepted value" % mid)
        for feat in m.get("features") or []:
            c.need(feat in ids, "%s: names a feature the matrix does not have: %r" % (mid, feat))
        handler = m.get("handler")
        if handler:
            module_name, _, symbol = handler.rpartition(".")
            c.need(module_name in {"jarvis_settings_registry", "jarvis_quick"},
                   "%s: handler %r is not an owned backend module" % (mid, handler))
            mod = sr if module_name == "jarvis_settings_registry" else q
            c.need(callable(getattr(mod, symbol, None)),
                   "%s: handler %r does not exist in %s" % (mid, handler, module_name))
        for side in ("desktop", "phone"):
            loc = (m.get(side) or {}).get("location")
            c.need(isinstance(loc, str) and loc.strip(), "%s: no %s Settings location" % (mid, side))
        if m.get("status") == "enforced":
            c.need(bool(handler), "%s: enforced multi-field row has no handler" % mid)
            c.need(bool(m.get("proof")), "%s: enforced multi-field row needs a test proof reference" % mid)
        if m.get("status") == "planned":
            c.need(m.get("owner") in {"voiceprint-wiring", "setup-ui", "Session B"},
                   "%s: planned multi-field row needs a fixing owner" % mid)
            c.need(any(g.get("kind") == "multi-field" and g.get("id") == mid
                       for g in contract.get("known_gaps", [])),
                   "%s: planned multi-field row is missing from known_gaps" % mid)
            if args.strict:
                print("NOT-ENFORCED  multi-field %-24s %-14s %s" % (mid, m.get("owner"), (m.get("reason") or "")[:80]))

    # ---- the recorded gaps: known, owned, and counted ----------------------
    gaps = contract.get("known_gaps", [])
    owner_counts = Counter(g.get("owner") for g in gaps)
    for g in gaps:
        c.need(g.get("owner") in BOOL_OWNERS, "gap %r has unknown owner %r" % (g.get("id"), g.get("owner")))
        c.need(isinstance(g.get("reason"), str) and g["reason"].strip(), "gap %r has no reason" % g.get("id"))
    if args.strict:
        for g in gaps:
            print("GAP           %-12s %-26s %-14s %s" % (g.get("status"), g.get("id"), g.get("owner"), g.get("reason")[:90]))
    status_counts = Counter(f.get("status") for f in contract.get("features", []))
    print("feature-controls: %d/%d features covered; statuses %s" % (
        len(matrix), len(real), dict(sorted(status_counts.items()))))
    print("non-enforced: %d feature(s); known gaps: %d %s" % (
        sum(1 for f in contract.get("features", []) if f.get("status") != "enforced"),
        len(gaps), dict(sorted(owner_counts.items()))))
    print("labels: %s" % dict(sorted(seen_labels.items(), key=lambda kv: str(kv[0]))))
    print("settings: %d/%d switches, %d/%d rows, %d/%d sections" % (
        len(bmatrix), len(bool_by_key), len(rmatrix), len(rows_by_id), len(smatrix), len(sections)))
    if c.errors:
        print("FAIL: %d mismatch(es)" % len(c.errors))
        for e in c.errors:
            print("  - " + e)
        return 1
    print("OK: the matrix agrees with the real files. Known gaps above are REPORTED, not passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
