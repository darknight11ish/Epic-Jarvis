"""jarvis_money_parse.py - reading money, dates and a bank file's header, exactly.

NEW MODULE, shipped whole. Pure functions, standard library only, no file and
no network. `jarvis_spending.py` (spending summaries, JARVIS-API section 100)
uses it now; the retirement what-if (section 103) is meant to use it for the
numbers the owner types, so both read a number the same way
(docs/FINANCE-DESIGN.md sections 3.2 and 4).

THE RULES THAT MATTER
  * Money is whole minor units (cents) in a Python int, parsed with
    `decimal.Decimal`. A float never touches an amount: a total that is one
    cent out is a bug a test can find (test_spending.py checks the source of
    this file and of jarvis_spending.py for the word "float").
  * A number that cannot be read is None - never 0, never a guess. In
    particular a mark used the wrong way round is refused: with "." as the
    decimal mark, "1.234,56" is not a number (its commas do not sit in groups
    of three before a final dot), so the row is counted as unreadable instead
    of quietly becoming 1.23456.
  * `guess_decimal` answers "." or "," only when the column decides it, and
    None when it cannot ("1,234" alone is either a thousand or one and a bit).
    The owner is asked; nothing here ever guesses an ambiguous case.
  * `guess_date_order` does the same for day-first against month-first: any
    first part over 12 means day-first, any second part over 12 means
    month-first, both or neither means None (ask). A wrong guess would move a
    month's spending without a word.

WHAT A NUMBER MAY LOOK LIKE
  1,234.56   1.234,56   1 234,56   1'234.56   (45.10) = negative   45.10-
  -45.10   -£45.10   £-45.10   $45   45.10 CR = money in   45.10 DR = money out
"""
from __future__ import annotations

import datetime as _dt
import re
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional

_SPACES = "    "
_CURRENCY_SYMBOLS = {"$": "$", "£": "£", "€": "€", "¥": "¥", "₹": "₹", "₩": "₩", "₽": "₽",
                     "kr": "kr", "zł": "zł"}
_CODES = ("USD", "GBP", "EUR", "JPY", "CAD", "AUD", "CHF", "SEK", "NOK", "DKK", "NZD", "INR",
          "PLN", "CZK", "HUF", "MXN", "BRL", "ZAR", "CNY", "HKD", "SGD")
_CODE_RE = re.compile(r"(?<![A-Za-z])(" + "|".join(_CODES) + r")(?![A-Za-z])")
_SYMBOL_RE = re.compile("[" + re.escape("$£€¥₹₩₽") + "]")

# Whole-number groups of three: 1,234,567  1 234 567  1'234'567 (and the
# same with dots for the other mark).
_GROUPED_DOT = re.compile(r"^\d{1,3}(?:,\d{3})*(?:\.\d+)?$|^\d+(?:\.\d+)?$|^\.\d+$")
_GROUPED_COMMA = re.compile(r"^\d{1,3}(?:\.\d{3})*(?:,\d+)?$|^\d+(?:,\d+)?$|^,\d+$")


def currency_hint(text) -> str:
    """The currency a cell names by a symbol or a three-letter code ("£",
    "GBP"), or "". Never converts anything."""
    t = str(text or "")
    m = _SYMBOL_RE.search(t)
    if m:
        return _CURRENCY_SYMBOLS[m.group(0)]
    m = _CODE_RE.search(t.upper())
    return m.group(1) if m else ""


def _strip(text) -> tuple:
    """(digits-and-marks text, negative, direction) from a cell: the currency
    words, brackets, signs and CR/DR taken off. direction is "in" for a CR
    suffix, "out" for DR, "" otherwise. ("", False, "") when nothing is left."""
    t = str(text if text is not None else "").strip()
    for ch in _SPACES:
        t = t.replace(ch, " ")
    t = t.replace("−", "-").replace("–", "-").replace("—", "-")
    t = _CODE_RE.sub("", t.upper() if _CODE_RE.search(t.upper()) else t)
    t = _SYMBOL_RE.sub("", t)
    for word in _CURRENCY_SYMBOLS:
        if len(word) > 1:
            t = re.sub(r"(?i)(?<![A-Za-z])" + re.escape(word) + r"(?![A-Za-z])", "", t)
    t = t.strip()
    direction = ""
    m = re.search(r"(?i)\b(CR|DR)\.?$", t)
    if m:
        direction = "in" if m.group(1).upper() == "CR" else "out"
        t = t[: m.start()].strip()
    negative = False
    if t.startswith("(") and t.endswith(")"):
        negative, t = True, t[1:-1].strip()
    if t.startswith("-"):
        negative, t = True, t[1:].strip()
    elif t.startswith("+"):
        t = t[1:].strip()
    if t.endswith("-"):
        negative, t = True, t[:-1].strip()
    elif t.endswith("+"):
        t = t[:-1].strip()
    # A symbol between the sign and the digits ("-£45" was handled; "£-45"
    # leaves "-45" here).
    if t.startswith("-"):
        negative, t = True, t[1:].strip()
    return t, negative, direction


def _digits_text(t: str, decimal: str) -> Optional[str]:
    """`t` (no sign, no symbol) as a plain "123.45" string, or None when it is
    not a number written with `decimal` as its decimal mark."""
    if not t:
        return None
    # Thousands may be separated by spaces or apostrophes: only in groups of 3.
    if " " in t or "'" in t or "’" in t:
        sep = " " if " " in t else ("'" if "'" in t else "’")
        head, _, tail = t.partition(decimal) if decimal in t else (t, "", "")
        groups = head.split(sep)
        if not (groups and groups[0].isdigit() and 1 <= len(groups[0]) <= 3
                and all(g.isdigit() and len(g) == 3 for g in groups[1:])):
            return None
        t = "".join(groups) + (decimal + tail if tail or decimal in t else "")
    if decimal == ".":
        if not _GROUPED_DOT.match(t):
            return None
        return t.replace(",", "")
    if decimal == ",":
        if not _GROUPED_COMMA.match(t):
            return None
        return t.replace(".", "").replace(",", ".")
    return None


def to_cents(dec: Decimal) -> Optional[int]:
    """Whole cents from a Decimal, or None when it has more than two decimal
    places (a price per litre is not money to add up)."""
    cents = dec * 100
    if cents != cents.to_integral_value():
        return None
    return int(cents)


def parse_money(text, decimal: str = ".") -> Optional[int]:
    """The amount in a cell as signed cents, or None. Negative for brackets,
    a leading or trailing minus, or a DR suffix; a CR suffix is money in."""
    t, negative, direction = _strip(text)
    plain = _digits_text(t, decimal)
    if plain is None:
        return None
    try:
        dec = Decimal(plain)
    except InvalidOperation:
        return None
    cents = to_cents(dec)
    if cents is None:
        return None
    if direction == "out":
        negative = True
    elif direction == "in":
        negative = False
    return -cents if negative else cents


def looks_numeric(text) -> bool:
    """Does the cell look like an amount in either style? (Header and date
    finding use it; a date such as 04/03/2026 is not an amount.)"""
    t, _n, _d = _strip(text)
    return bool(t) and bool(re.fullmatch(r"[\d.,' ’]+", t)) and bool(re.search(r"\d", t)) \
        and not re.fullmatch(r"\d{1,4}[./-]\d{1,2}[./-]\d{1,4}", t)


def guess_decimal(values: Iterable) -> Optional[str]:
    """"." or "," when the column settles which is the decimal mark, else None.
    All whole numbers (no mark anywhere) count as ".": nothing depends on it."""
    votes = set()
    seen_mark = False
    for v in values:
        t, _n, _d = _strip(v)
        if not t or not re.search(r"\d", t) or not re.fullmatch(r"[\d.,' ’]+", t):
            continue
        t = t.replace(" ", "").replace("'", "").replace("’", "")
        dots, commas = t.count("."), t.count(",")
        if not dots and not commas:
            continue
        seen_mark = True
        if dots and commas:
            votes.add("." if t.rfind(".") > t.rfind(",") else ",")
        elif dots > 1:
            votes.add(",")           # 1.234.567: the dot groups thousands
        elif commas > 1:
            votes.add(".")
        else:
            mark = "." if dots else ","
            after = t.split(mark)[1]
            if len(after) == 3 and after.isdigit() and t.split(mark)[0] not in ("", "0"):
                continue             # 1,234 or 1.234: a thousand or one and a bit
            votes.add(mark)
    if len(votes) == 1:
        return next(iter(votes))
    if not votes and not seen_mark:
        return "."
    return None


# --------------------------------------------------------------------------
#   Dates
# --------------------------------------------------------------------------

_MONTHS = {m: i for i, names in enumerate((
    ("jan", "january", "januar", "enero", "janvier", "gennaio"),
    ("feb", "february", "februar", "febrero", "fevrier", "février", "febbraio"),
    ("mar", "march", "märz", "marzo", "mars"),
    ("apr", "april", "abril", "avril", "aprile"),
    ("may", "mai", "mayo", "maggio"),
    ("jun", "june", "juni", "junio", "juin", "giugno"),
    ("jul", "july", "juli", "julio", "juillet", "luglio"),
    ("aug", "august", "agosto", "aout", "août"),
    ("sep", "sept", "september", "septiembre", "septembre", "settembre"),
    ("oct", "october", "oktober", "octubre", "octobre", "ottobre"),
    ("nov", "november", "noviembre", "novembre"),
    ("dec", "december", "dezember", "diciembre", "décembre", "dicembre")), 1) for m in names}

ORDERS = ("dmy", "mdy", "ymd")

_ISO = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?"
                  r"(?:Z|[+-]\d{2}:?\d{2})?)?$")
_NUMERIC = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2}|\d{4})(?:[T ]\d{1,2}:\d{2}(?::\d{2})?)?$")
_TEXT_DMY = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)?[ \-./,]+([A-Za-zÀ-ÿ]{3,10})\.?[ \-./,]+(\d{2}|\d{4})$")
_TEXT_MDY = re.compile(r"^([A-Za-zÀ-ÿ]{3,10})\.?[ \-./]+(\d{1,2})(?:st|nd|rd|th)?,?[ \-./]+(\d{2}|\d{4})$")


def _year(y: str) -> int:
    n = int(y)
    return n if len(y) == 4 else 2000 + n


def _make(y: int, m: int, d: int) -> Optional[_dt.date]:
    try:
        return _dt.date(y, m, d)
    except ValueError:
        return None


def parse_date(text, order: str = "dmy") -> Optional[_dt.date]:
    """A date in a cell, or None. ISO and written-out months need no order;
    a numeric day/month date uses `order` ("dmy" or "mdy"). A time on the end
    is ignored."""
    t = str(text if text is not None else "").strip()
    if not t or len(t) > 40:
        return None
    m = _ISO.match(t)
    if m:
        return _make(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _NUMERIC.match(t)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), _year(m.group(3))
        if order == "mdy":
            return _make(y, a, b)
        if order == "dmy":
            return _make(y, b, a)
        return None
    m = _TEXT_DMY.match(t)
    if m:
        mon = _MONTHS.get(m.group(2).lower())
        return _make(_year(m.group(3)), mon, int(m.group(1))) if mon else None
    m = _TEXT_MDY.match(t)
    if m:
        mon = _MONTHS.get(m.group(1).lower())
        return _make(_year(m.group(3)), mon, int(m.group(2))) if mon else None
    return None


def guess_date_order(values: Iterable) -> Optional[str]:
    """"dmy", "mdy" or "ymd" (also the answer for all-ISO and all-written-out
    columns, which need no order), or None when the column cannot say. Never
    guesses: every numeric date with both parts 12 or under is ambiguous."""
    day_first = month_first = False
    numeric = other = 0
    for v in values:
        t = str(v if v is not None else "").strip()
        if not t:
            continue
        m = _NUMERIC.match(t)
        if m:
            numeric += 1
            a, b = int(m.group(1)), int(m.group(2))
            if a > 12 and b <= 12:
                day_first = True
            elif b > 12 and a <= 12:
                month_first = True
            elif a > 12 and b > 12:
                return None          # not a date in either order
            continue
        if _ISO.match(t) or _TEXT_DMY.match(t) or _TEXT_MDY.match(t):
            other += 1
    if day_first and month_first:
        return None
    if day_first:
        return "dmy"
    if month_first:
        return "mdy"
    if numeric:
        return None
    return "ymd" if other else None


# --------------------------------------------------------------------------
#   The header of a bank export
# --------------------------------------------------------------------------

def words(cell) -> list:
    return [w for w in re.split(r"[^\w]+", str(cell or "").casefold()) if w]


DATE_WORDS = ("date", "posted", "datum", "fecha", "booking", "buchungstag", "data", "fecha")
AMOUNT_WORDS = ("amount", "debit", "credit", "withdrawal", "withdrawals", "deposit", "deposits",
                "value", "betrag", "importe", "sum", "paid", "charge", "money", "montant")
DESCRIPTION_WORDS = ("description", "details", "detail", "payee", "memo", "narrative",
                     "merchant", "particulars", "transaction", "text", "beschreibung",
                     "concepto", "reference", "name", "verwendungszweck", "libelle")
DEBIT_PHRASES = ("debit", "debits", "withdrawal", "withdrawals", "paid out", "money out",
                 "outgoing", "spent", "out")
CREDIT_PHRASES = ("credit", "credits", "deposit", "deposits", "paid in", "money in", "incoming",
                  "received", "in")
DRCR_PHRASES = ("dr/cr", "cr/dr", "debit/credit", "credit/debit", "indicator", "dr cr",
                "transaction type", "type", "sign")
BALANCE_WORDS = ("balance", "saldo", "solde")
#: A column whose name says this is never shown, whatever it holds.
PRIVATE_COLUMN_WORDS = ("account", "iban", "card", "sort", "bic", "swift", "routing", "pan",
                        "acct", "konto", "cuenta")


def _has_word(cell, vocabulary) -> bool:
    ws = words(cell)
    return any(w in vocabulary for w in ws)


def is_private_column(cell) -> bool:
    """Is this header cell the name of an account, card or sort-code column?"""
    ws = words(cell)
    if any(w in PRIVATE_COLUMN_WORDS for w in ws):
        # "Account type" is the kind of account, not a number: still hidden,
        # because hiding a harmless column costs nothing.
        return True
    return False


def find_header(rows: list, *, look: int = 40) -> Optional[int]:
    """The index of the header row: the first row (of the first `look`) with
    at least three non-empty cells, one holding a date word and one an amount
    word. None when there is none - the owner then names it."""
    for i, row in enumerate(rows[:look]):
        cells = [c for c in row if str(c or "").strip()]
        if len(cells) < 3:
            continue
        if any(_has_word(c, DATE_WORDS) for c in cells) and any(
                _has_word(c, AMOUNT_WORDS) for c in cells):
            return i
    return None


def guess_columns(header: list, sample: list) -> dict:
    """{"date", "description", "amount", "debit", "credit", "drcr", "currency",
    "balance", "private": [indexes]} - each a column index or None, from the
    header's words. `sample` (data rows) settles a Dr/Cr column."""
    n = len(header)
    out = {"date": None, "description": None, "amount": None, "debit": None, "credit": None,
           "drcr": None, "currency": None, "balance": None, "private": []}
    names = [str(c or "").strip().casefold() for c in header]

    def first(pred, taken=()):
        for i in range(n):
            if i not in taken and names[i] and pred(names[i], header[i]):
                return i
        return None
    out["private"] = [i for i in range(n) if names[i] and is_private_column(header[i])]
    taken = set(out["private"])
    # Date: prefer a column called just "date" / "transaction date" over "value date".
    date_i = first(lambda nm, h: _has_word(h, DATE_WORDS) and "value" not in nm
                   and "valuta" not in nm, taken)
    if date_i is None:
        date_i = first(lambda nm, h: _has_word(h, DATE_WORDS), taken)
    out["date"] = date_i
    taken.add(date_i) if date_i is not None else None
    bal = first(lambda nm, h: _has_word(h, BALANCE_WORDS), taken)
    out["balance"] = bal
    taken.add(bal) if bal is not None else None
    deb = first(lambda nm, h: nm in DEBIT_PHRASES or any(p in nm for p in DEBIT_PHRASES[:7]), taken)
    cre = first(lambda nm, h: nm in CREDIT_PHRASES or any(p in nm for p in CREDIT_PHRASES[:8]),
                taken | ({deb} if deb is not None else set()))
    if deb is not None and cre is not None and deb != cre:
        out["debit"], out["credit"] = deb, cre
        taken |= {deb, cre}
    amt = None
    if out["debit"] is None:
        amt = first(lambda nm, h: _has_word(h, AMOUNT_WORDS) and not _has_word(h, BALANCE_WORDS),
                    taken)
        out["amount"] = amt
        taken.add(amt) if amt is not None else None
    cur = first(lambda nm, h: nm in ("currency", "ccy", "cur", "währung", "moneda", "devise"),
                taken)
    out["currency"] = cur
    taken.add(cur) if cur is not None else None
    desc = first(lambda nm, h: _has_word(h, DESCRIPTION_WORDS) and nm not in ("type",), taken)
    out["description"] = desc
    taken.add(desc) if desc is not None else None
    if out["amount"] is not None:
        d = first(lambda nm, h: nm in DRCR_PHRASES or any(p in nm for p in DRCR_PHRASES[:6]),
                  taken)
        if d is not None:
            vals = {str(r[d]).strip().casefold() for r in sample if d < len(r) and str(r[d]).strip()}
            if vals and vals <= {"dr", "cr", "d", "c", "debit", "credit", "db", "cd"}:
                out["drcr"] = d
    return out
