#!/usr/bin/env python3
"""Writes the "what is new on my watchlist" contract file for both apps, and
checks it.

    python3 tools/gen_watch_report_cases.py            # write both copies
    python3 tools/gen_watch_report_cases.py --check    # compare only

What `GET /api/watch/report` really answers, made by running the module itself
(`backend/jarvis_watch.py`) against a temporary database - nothing written by
hand:

    jarvis-desktop/tests/fixtures/watch-report-cases.json
    jarvis-client/app/src/test/resources/contract/watch-report-cases.json

(byte-identical).

THE POINT OF THIS FILE (2026-10-09). Both apps used to read `findings`/`items`
from this route and title every row with `full_name`/`name`. The route has
never served any of those four keys: it serves `new` and `updated`, split by
`kind`, and a repository is named `repo`. So every successful read came back as
the empty list and both screens said "Nothing new since you last marked the
list read." over a list they had never read - while the badge above could say
"Watches - 3 new" at the same moment. The desktop's UI fixture did not catch it
because the fixture was hand-written to match the bug: it invented
`{"available": true, "findings": [...]}`.

A hand-written fixture can always be edited to agree with a broken client, so
this one is produced by the module and nothing else. Rename a key on either
side and the file stops matching: the client's read comes back empty and
`jarvis-desktop/tests/watch-report.mjs` fails, instead of the screen quietly
saying there is nothing new.

The seeding goes through `check(fetcher=...)`, which is the module's own
supported seam for a test double, so the rows are made by the same code that
makes them on the owner's PC. Times are fixed, so the file only changes when
the module's answer does.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
_CONF = tempfile.mkdtemp(prefix="jarvis-watch-cases-")
os.environ["OPENJARVIS_CONFIG_DIR"] = _CONF
# `DB_PATH` is read once at import and honours this, so it must be set first.
os.environ["JARVIS_WATCH_DB"] = str(Path(_CONF) / "watch.db")
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_watch as W  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "watch-report-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "watch-report-cases.json")
COPIES = (DESKTOP, PHONE)

#: One fixed moment, so the file is stable and `at` never drifts.
AT = 1790000000.0
LATER = AT + 3600.0

FACES = "local llm ui"
TRAY = "tauri plugins"


def _repo(rid, full_name, *, stars=0, licence="", archived=False, descr=""):
    """One item of a GitHub search answer, in GitHub's own field names - the
    shape `jarvis_watch._parse` reads."""
    item = {"id": rid, "full_name": full_name, "stargazers_count": stars,
            "archived": archived, "pushed_at": "2026-10-01T09:00:00Z",
            "description": descr, "topics": []}
    if licence:
        item["license"] = {"spdx_id": licence, "key": licence.lower()}
    return item


def _answer(*items):
    """A stub search answer: `check` reads `.items` out of the JSON text."""
    return json.dumps({"total_count": len(items), "items": list(items)})


def _fresh(items_by_topic, *, topics=(FACES, TRAY)):
    """A temporary watchlist with one check already absorbed.

    Nothing is carried between cases: the database is emptied first, so each
    answer below is a picture of exactly the rows named for it.
    """
    for t in W.topics():
        W.remove(t["name"])
    for name in topics:
        W.add(name, notify=(name == FACES))
    for name, items in items_by_topic.items():
        W.check(name, fetcher=lambda _url, _a=_answer(*items): _a, now=AT)


def cases() -> dict:
    out = {}

    # An empty watchlist: the route's real "nothing new" - the ONLY answer the
    # all-clear sentence may be drawn for.
    _fresh({}, topics=())
    empty = W.report(mark=False)

    # Three new repositories, one of them with no licence file. The module sends
    # the two words "none stated" for that one - not an empty string - which is
    # the value the old `^(none|unknown|null)$` filter let through as a settled
    # licence, so the "no permission to use it" warning never drew.
    _fresh({
        FACES: [
            _repo(1, "example/reactor-faces", stars=1284, licence="MIT",
                  descr="Twenty animated status faces for a desktop assistant."),
            _repo(2, "example/vec0", stars=4102, licence="Apache-2.0",
                  descr="A vector search extension for SQLite."),
        ],
        TRAY: [
            _repo(3, "example/tauri-tray-badge", stars=96,
                  descr="Numeric badges on the Windows tray icon."),
        ],
    })
    new_only = W.report(mark=False)

    # One row of each kind in ONE answer, which is the shape that decides the
    # order the screen draws them in: the module's own consumer reads
    # `peek["new"] + peek["updated"]` (jarvis_watch.py:524), and a client that
    # reads only one of the two loses half the list silently.
    _fresh({FACES: [_repo(7, "example/quiet-harbour", stars=310,
                          descr="A tray badge with no dependencies.")]}, topics=(FACES,))
    W.check(FACES, fetcher=lambda _url: _answer(
        _repo(7, "example/quiet-harbour", stars=980, licence="MIT", archived=True,
              descr="A tray badge with no dependencies, now MIT."),
        _repo(8, "example/harbour-lights", stars=44, licence="0BSD",
              descr="A second project on the same topic.")), now=LATER)
    # `updated_one_repo` is the same peek narrowed to the row that moved.
    both = W.report(mark=False)
    only_updated = dict(both, new=[], count=len(both["updated"]))

    # The state right after "Mark these read": the same rows, marked, so a
    # second peek is a real empty answer rather than a shape the app cannot
    # read. `mark=False` is what the route uses; this is the consume.
    W.report()
    after_mark = W.report(mark=False)

    return {
        "cases": {"empty": empty, "new_only": new_only,
                  "new_and_updated": both, "updated_only": only_updated,
                  "after_mark_read": after_mark},
        # The route the apps call is a peek: `report(mark=False)`. Named here so
        # a test can assert the client never reads a consuming shape.
        "peek": {"mark": False, "limit": 50},
        # What `GET /api/watch/report` answers on a PC with no jarvis_watch.py.
        "missing": {"status": 404, "body": {"error": "not found"}},
        # Every top-level key the ROUTE serves. The module's own `report()`
        # returns the five below; the route wrapper adds `available`, which the
        # owner's running backend was seen sending on 2026-10-09. A client
        # reading a key that is not in this list is reading a shape the backend
        # does not serve - which is exactly the bug of 2026-10-09, where both
        # apps read `findings`/`items` and neither has ever existed.
        "top_level_keys": sorted([*empty, "available"]),
        # And every key of one row, for the same reason. Note there is no
        # `note`, no `descr` and no `full_name`: the desktop's old fixture
        # invented all three.
        "row_keys": sorted(new_only["new"][0]),
    }


def render() -> str:
    return json.dumps(cases(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        stale = []
        for path in COPIES:
            have = path.read_text(encoding="utf-8") if path.is_file() else ""
            if have.replace("\r\n", "\n") != text:
                stale.append(path)
        for path in stale:
            print(f"{path.relative_to(ROOT)} is out of date: run "
                  f"python3 tools/gen_watch_report_cases.py")
        if stale:
            return 1
        print("watch-report-cases.json matches the producer (desktop and phone copies).")
        return 0
    for path in COPIES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
