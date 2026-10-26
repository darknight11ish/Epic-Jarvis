#!/usr/bin/env python3
"""Writes backend/jarvis_feature_catalogue.py from features/features.json.

    python3 tools/gen_feature_guide_catalogue.py            # write it (both copies)
    python3 tools/gen_feature_guide_catalogue.py --check    # compare only

WHAT THIS IS FOR. The owner's feature list (`features/features.json`, 140 rows:
id, group, title, what, where, asks, limit, surface, covers) is the ONE place
the apps' Features pages draw from. It lives in this repository, NOT in the
backend folder an installer ships to the PC - so a backend module cannot read it
at run time. The feature guide ("what is this feature?", "is it on?") must
answer on the owner's PC with no repository around it, so the list is turned
into plain Python data that rides beside the other shipped modules
(`backend/jarvis_feature_guide.py` imports it).

WHY A GENERATED MODULE AND NOT A COPY OF THE JSON. The generated copy is
checked by `backend/test_feature_guide.py`, which runs `--check`: change
features.json without re-running this tool and that suite fails. A hand-copied
JSON would drift silently, which is exactly the failure the three existing
copies of features.json already have a checker for
(`tools/check_feature_list.py`).

WHAT IT WRITES, and nothing else: the three copies stay in step because this
module is generated from the same source, not typed. `jarvis-backend/` gets the
same bytes (the two-file rule for shipped modules).

Exit 0 when the committed copies are current; 1 when they are not (with the
reason printed).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "features" / "features.json"
OUT = ROOT / "backend" / "jarvis_feature_catalogue.py"
TWIN = ROOT / "jarvis-backend" / "jarvis_feature_catalogue.py"

#: The keys a row must have, in the order they are written. A missing one is a
#: broken list; an UNKNOWN one is refused rather than dropped, so a new field
#: added to features.json has to be looked at here instead of quietly vanishing.
REQUIRED = ("id", "group", "title", "what", "where", "asks", "limit", "surface")
#: A key the source carries and this catalogue deliberately does NOT: the guide
#: answers "what is this feature, and is it on?", never "how do I learn it", so
#: the teaching words would be the checker's own bookkeeping inside a runtime
#: module. It is NAMED here rather than left unknown, because the refusal below
#: exists so a new field has to be looked at by a person - and this is that
#: looking, written down (2026-10-25, rule 7 of tools/check_feature_list.py).
NOT_CARRIED = ("must_mention",)
OPTIONAL = ("surface_reason", "covers")

HEADER = '''"""GENERATED FILE - do not edit by hand.

The owner's feature list, as data: {count} rows from features/features.json.
Regenerate with `python3 tools/gen_feature_guide_catalogue.py`; the check for a
stale copy is in `backend/test_feature_guide.py`. The source file is
`features/features.json` (sha256 {sha}); the apps' Features pages read their own
copies of it, and `tools/check_feature_list.py` keeps those three in step.

WHY THIS COPY EXISTS: features.json is not shipped to the owner's PC (it lives
in this repository), so `backend/jarvis_feature_guide.py` - which answers "what
is this feature?" and "is it on?" on the PC - needs the rows beside it.
"""
from __future__ import annotations

#: sha256 of the features/features.json this file was generated from.
SOURCE_SHA256 = "{sha}"

#: The feature groups, in the order the list first names them.
GROUPS = {groups}

#: The rows, in the source file's order. Every value is exactly the source
#: file's own words - nothing here is reworded.
FEATURES = (
{rows})
'''


def load_rows() -> tuple:
    """(rows, sha256 hex, group order) from features/features.json."""
    try:
        raw = SOURCE.read_bytes()
    except OSError as exc:
        raise SystemExit(f"cannot read {SOURCE}: {exc}")
    sha = hashlib.sha256(raw).hexdigest()
    try:
        rows = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise SystemExit(f"{SOURCE} is not JSON: {exc}")
    if not isinstance(rows, list) or not rows:
        raise SystemExit(f"{SOURCE} must be a non-empty array of rows")
    seen, groups, clean = set(), [], []
    for n, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise SystemExit(f"{SOURCE}: row {n} is not an object")
        missing = [k for k in REQUIRED if k not in row]
        if missing:
            raise SystemExit(f"{SOURCE}: row {n} has no {', '.join(missing)}")
        unknown = sorted(set(row) - set(REQUIRED) - set(OPTIONAL) - set(NOT_CARRIED))
        if unknown:
            raise SystemExit(f"{SOURCE}: row {n} has unknown key(s) {unknown} - add them "
                             f"to this tool on purpose, in the right order")
        for key in ("id", "group", "title", "what", "where", "asks", "surface"):
            if not isinstance(row[key], str) or not row[key].strip():
                raise SystemExit(f"{SOURCE}: row {n} ({row.get('id')!r}) has an empty {key}")
        # `limit` is allowed to be empty: 17 rows have none to state, and the
        # guide says exactly that ("the list gives no limit for this one")
        # rather than inventing one.
        if not isinstance(row["limit"], str):
            raise SystemExit(f"{SOURCE}: row {n} ({row.get('id')!r}) limit is not text")
        rid = row["id"]
        if rid in seen:
            raise SystemExit(f"{SOURCE}: duplicate id {rid!r}")
        seen.add(rid)
        if row["surface"] not in ("both", "desktop", "phone"):
            raise SystemExit(f"{SOURCE}: row {n} ({rid!r}) has surface {row['surface']!r}")
        covers = row.get("covers", [])
        if not isinstance(covers, list) or not all(isinstance(c, str) for c in covers):
            raise SystemExit(f"{SOURCE}: row {n} ({rid!r}) covers is not a list of strings")
        if row["group"] not in groups:
            groups.append(row["group"])
        out = {k: row[k] for k in REQUIRED}
        out["covers"] = list(covers)
        if row.get("surface_reason"):
            out["surface_reason"] = row["surface_reason"]
        clean.append(out)
    return clean, sha, groups


def _row_text(row: dict) -> str:
    """One row as a dict literal, keys in a fixed order, source words verbatim."""
    lines = ["    {"]
    for key in REQUIRED + OPTIONAL:
        if key == "covers":
            if row.get("covers"):
                lines.append(f'        "covers": {json.dumps(row["covers"], ensure_ascii=True)},')
            else:
                lines.append('        "covers": [],')
            continue
        if key not in row:
            continue
        lines.append(f'        {json.dumps(key)}: '
                     f'{json.dumps(row[key], ensure_ascii=True)},')
    lines.append("    },")
    return "\n".join(lines) + "\n"


def render() -> str:
    rows, sha, groups = load_rows()
    body = "".join(_row_text(r) for r in rows)
    return HEADER.format(count=len(rows), sha=sha,
                         groups=json.dumps(tuple(groups), ensure_ascii=True),
                         rows=body)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Write the feature guide's catalogue module.")
    ap.add_argument("--check", action="store_true",
                    help="compare the committed copies instead of writing them")
    args = ap.parse_args(argv)
    text = render()
    if args.check:
        bad = []
        for path in (OUT, TWIN):
            try:
                got = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
            except OSError:
                got = ""
            if got != text:
                bad.append(path.relative_to(ROOT).as_posix())
        if bad:
            print("FAIL  the feature catalogue is not what features/features.json says; "
                  "run python3 tools/gen_feature_guide_catalogue.py: "
                  + ", ".join(bad))
            return 1
        print(f"ok    the feature catalogue matches features/features.json "
              f"({len(json.loads(SOURCE.read_text(encoding='utf-8')))} rows)")
        return 0
    _write(OUT, text)
    _write(TWIN, text)
    print(f"wrote {OUT.relative_to(ROOT).as_posix()}")
    print(f"wrote {TWIN.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
