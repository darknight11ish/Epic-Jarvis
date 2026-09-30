#!/usr/bin/env python3
"""Writes the "Spending summaries" contract file for both apps, and checks it.

    python3 tools/gen_spending_cases.py            # write both copies
    python3 tools/gen_spending_cases.py --check    # compare only

What the backend really answers (backend/jarvis_spending.py, spending.patch;
JARVIS-API section 100; docs/FINANCE-DESIGN.md "Slice contract (frozen)"), in
named situations, made by the real code from the invented files in
backend/fixtures/spending/ - nothing written by hand:

    jarvis-desktop/tests/fixtures/spending-cases.json
    jarvis-client/app/src/test/resources/contract/spending-cases.json

(byte-identical). It holds the words both apps show, the tables a chat answer
carries (`GET /api/chat/table`), what `GET /api/spending` says on the PC and on
the phone, and the column check's proposal. The desktop's tests and the phone's
tests build their renderers against it.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FIX = BACKEND / "fixtures" / "spending"
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-spending-cases-"))
_CONF = _TMP / "config"
_CONF.mkdir()
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_CONF)
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_documents as D  # noqa: E402
import jarvis_spending as SP  # noqa: E402

import datetime as _dt  # noqa: E402

D._config_dir = lambda: _CONF
SP._today = lambda: _dt.date(2026, 9, 30)      # a fixed day, so the file only changes when the backend does

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "spending-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "spending-cases.json")
COPIES = (DESKTOP, PHONE)

WORD_NAMES = (
    "TITLE", "DETAIL", "PC_ONLY", "NEEDS_SETUP_ON_PC", "EMPTY_PROFILES", "STARTER_NOTE",
    "HIDDEN_COLUMNS_NOTE", "TABLE_HIDDEN", "TABLE_GONE", "SPOKEN_LINE", "NO_SENTENCE_LINE",
    "DROPPED_LINE", "ROW_TOTAL", "ROW_UNCATEGORISED", "ROW_REFUNDS", "ROW_INCOME",
    "ROW_TRANSFERS_OUT", "ROW_TRANSFERS_IN", "CAV_ONCE", "CAV_ONCE_ONE", "CAV_SKIPPED",
    "CAV_SKIPPED_ONE", "CAV_UNCAT", "CAV_UNCAT_ONE", "CAV_CURRENCIES", "CAV_HIDDEN",
    "CAV_PENDING", "CAV_REFUNDS", "CAV_TRANSFERS", "CAV_FILES", "CAV_DATES", "STREAM_MARK",
)


def _work(name: str, *fixtures, text: dict = None) -> Path:
    p = _TMP / "home" / name
    shutil.rmtree(p, ignore_errors=True)
    p.mkdir(parents=True)
    for f in fixtures:
        shutil.copy(FIX / f, p / f)
    for n, body in (text or {}).items():
        (p / n).write_text(body, encoding="utf-8", newline="\n")
    return p


def _listed(*paths) -> None:
    D._save([{"path": os.path.realpath(str(p)), "added": 1.0} for p in paths])


def _fresh() -> None:
    SP._reset_for_tests()
    D._reset_for_tests()
    for f in _CONF.iterdir():
        f.unlink()


def _setup(path: Path) -> dict:
    got = SP.read_rows(str(path), roots=[str(path.parent)])
    prop = SP.propose_layout(got["rows"], name=path.name)
    body = dict(prop["guess"], confirm=True)
    SP.confirm(body, rows=got["rows"], name=path.name, real=got["real"])
    return prop


def _table(path: Path, **args) -> dict:
    a = {"action": "summary", "path": str(path)}
    a.update(args)
    return SP.run_tool(a, roots=[str(path.parent)])["_table"]


def example_tables() -> dict:
    """The tables a chat answer carries, one per shape."""
    _fresh()
    d = _work("Example", "a_signed.csv", "g_overlap_1.csv", "g_overlap_2.csv",
              text={"multi.csv": "Date,Payee,Amount,Currency\n2026-02-01,TESCO,-10.00,GBP\n"
                                 "2026-02-02,LIDL,-20.00,EUR\n2026-02-03,ALDI,-5.00,GBP\n"
                                 "2026-02-04,SALARY,100.00,GBP\n"})
    _listed(d)
    for n in ("a_signed.csv", "g_overlap_1.csv", "multi.csv"):
        _setup(d / n)
    out = {
        "by_category": _table(d / "a_signed.csv", period="2026-03"),
        "by_month": _table(d / "a_signed.csv", by="month"),
        "by_category_and_month": _table(d / "a_signed.csv", by="both"),
        "two_files_overlapping": SP.run_tool({"action": "summary", "all": True},
                                             roots=[str(d)])["_table"],
        "two_currencies": _table(d / "multi.csv"),
        "one_category": _table(d / "a_signed.csv", category="Food and groceries"),
    }
    _fresh()
    return out


def cases() -> dict:
    out = {"words": {n: getattr(SP, n) for n in WORD_NAMES},
           "sign_sentences": dict(SP.SIGN_SENTENCES),
           "errors": {k: SP.ERRORS[k] for k in ("needs_setup", "no_header", "unchecked", "too_big",
                                                "empty_period", "pc_only")},
           "tables": example_tables()}
    _fresh()
    d = _work("Views", "a_signed.csv", "b_debit_credit.csv", "h_ambiguous.csv")
    _listed(d)
    out["view_pc_nothing_saved"] = SP.view(here=True)
    out["view_phone_nothing_saved"] = SP.view(here=False)
    got = SP.read_rows(str(d / "h_ambiguous.csv"), roots=[str(d)])
    out["proposal_date_order_unsettled"] = _relative(SP.propose_layout(got["rows"], name="h_ambiguous.csv"))
    SP.run_tool({"action": "summary", "path": str(d / "b_debit_credit.csv")}, roots=[str(d)])
    out["view_pc_file_waiting"] = _relative(SP.view(here=True), str(d))
    out["view_phone_file_waiting"] = SP.view(here=False)
    prop = _setup(d / "a_signed.csv")
    out["proposal_signed_amount"] = _relative(prop)
    out["view_pc_one_layout"] = _relative(SP.view(here=True), str(d))
    out["view_phone_one_layout"] = SP.view(here=False)
    _fresh()
    return out


def _relative(obj, base: str = ""):
    """The machine's own folder in a path becomes a Windows path the same everywhere."""
    if not base:
        return obj
    text = json.dumps(obj, ensure_ascii=False)
    text = text.replace(json.dumps(base + os.sep)[1:-1], "C:\\\\Users\\\\owner\\\\Bank\\\\")
    return json.loads(text)


def render() -> str:
    return json.dumps(cases(), ensure_ascii=False, indent=1) + "\n"


def main(argv) -> int:
    text = render()
    shutil.rmtree(_TMP, ignore_errors=True)
    if "--check" in argv:
        stale = [str(c.relative_to(ROOT)) for c in COPIES
                 if not c.exists() or c.read_text(encoding="utf-8") != text]
        if stale:
            print("STALE " + ", ".join(stale) + " - run python3 tools/gen_spending_cases.py")
            return 1
        print("spending-cases.json: both copies match")
        return 0
    for c in COPIES:
        c.parent.mkdir(parents=True, exist_ok=True)
        c.write_text(text, encoding="utf-8", newline="\n")
        print("wrote", c.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
