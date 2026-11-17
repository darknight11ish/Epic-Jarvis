"""The disposable repository the coding tiers run against.

WHY A BUILT FIXTURE AND NOT A CHECKOUT OF THIS REPOSITORY. The benchmark's
golden rule is that every coding test runs in a throwaway `git worktree` or a
disposable repository, never against `origin/main` or the owner's live notes.
The simplest way to guarantee that is to have no remote at all: `build()`
writes a small Python project into a NEW folder under the run's own scratch
root, makes it a fresh `git init` with one commit, and the harness only ever
runs `git` inside that folder. The project has no remote, so `git push`,
`fetch` and `checkout` of anything shared are not merely avoided - there is
nowhere for them to go.

THE PROJECT. `bench-shop` is a tiny basket/search library with a real pytest
suite and a real ruff config. It carries the three defects the spec names,
on purpose, each with one failing test:

  * an OR-query bug in `src/shop/search.py` (`match="any"` joins with AND);
  * a missing dict key in `src/shop/pricing.py` (`"gift-card"` is not
    normalised, so `PRICE_BOOK["gift-card"]` raises KeyError);
  * an off-by-one in `src/shop/paginate.py` (the first page starts at -1).

It also carries the four-file float -> integer-cents refactor T2.3 needs
(`money.py`, `cart.py`, `checkout.py`, `report.py`), whose tests fail until all
four files agree.

A test's pass criterion is its own exact command - e.g.
`pytest -q tests/test_search.py`. The other defects are deliberately still
there, because the spec names three and a later test fixes a different one;
the report says which command it ran and prints both that command's exit code
and the whole suite's, so nothing is hidden.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

#: The branch and identity of every disposable repo. Nothing here is a person.
BRANCH = "main"
AUTHOR = "Jarvis Benchmark"
EMAIL = "benchmark@jarvis.invalid"

_FILES: dict[str, str] = {}


def _add(path: str, text: str) -> None:
    _FILES[path] = text.lstrip("\n")


# ---------------------------------------------------------------------------
#   the project files
# ---------------------------------------------------------------------------

_add(".gitignore", '''
# The benchmark runs pytest and ruff inside this repository; neither output
# belongs in a git-status reading of what the answer touched.
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
''')

_add("README.md", '''
# bench-shop

A tiny basket and search library that the Jarvis coding benchmark owns. It is
not part of Jarvis and nothing in it is imported by the product.

    py -3 -m pytest -q
    py -3 -m ruff check src tests

The suite is the specification: a test that passes is the pass criterion.
''')

_add("pyproject.toml", '''
[project]
name = "bench-shop"
version = "0.1.0"
description = "a disposable project for the Jarvis coding benchmark"
requires-python = ">=3.10"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.ruff]
line-length = 88
target-version = "py310"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "W", "I"]
''')

_add("tests/conftest.py", '''
"""Make `src/` importable without installing the project."""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
''')

_add("src/shop/__init__.py", '''
"""bench-shop: a tiny basket and search library (disposable benchmark fixture).

The package deliberately imports nothing here. The four-file refactor's target
API does not exist yet, so importing it from the package would make every
`from shop.search import ...` fail for a reason that has nothing to do with the
test being run. Tests import the module they test.
"""
''')

# --- the OR-query bug -------------------------------------------------------
_add("src/shop/search.py", '''
"""Turn a plain phrase into one catalogue query clause.

The catalogue understands two shapes:

    build_query("coffee tea", match="all")  ->  "coffee AND tea"
    build_query("coffee tea", match="any")  ->  "coffee OR tea"

A term may name a field - `"title:coffee"` - and a quoted term is kept as an
exact phrase. Stop words are dropped, duplicates are removed, and at most
`MAX_TERMS` terms are kept so one pasted paragraph cannot become a query
thousands of characters long.

This module is the fixture's OR-query defect: `join_clauses` joins with AND
whatever the caller asked for, so `match="any"` is silently the same query as
`match="all"`. `tests/test_search.py` has the failing case.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: Words that carry no search meaning on their own.
STOP_WORDS = frozenset(
    {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is",
     "it", "of", "on", "or", "that", "the", "this", "to", "was", "with"}
)

#: A pasted paragraph is not a query; keep at most this many terms.
MAX_TERMS = 12

_WORD = re.compile(r"[a-z0-9][a-z0-9'_-]*")


def normalise(text: str) -> str:
    """Lower-case and collapse whitespace; never None."""
    return " ".join(str(text or "").lower().split())


def tokenise(text: str) -> list[str]:
    """Every word in `text`, in order, with no punctuation around it."""
    return _WORD.findall(normalise(text))


def meaningful_terms(text: str, *, limit: int = MAX_TERMS) -> list[str]:
    """Drop stop words and duplicates, keep the first `limit` useful words."""
    kept: list[str] = []
    for word in tokenise(text):
        if word in STOP_WORDS or len(word) < 2:
            continue
        if word not in kept:
            kept.append(word)
        if len(kept) >= limit:
            break
    return kept


def escape_term(term: str) -> str:
    """Escape the two characters the catalogue's query syntax gives meaning."""
    return re.sub(r'(["\\\\])', r"\\\\\\1", term)


def quote(term: str) -> str:
    """Quote one term as an exact phrase."""
    return f'"{escape_term(term)}"'


@dataclass(frozen=True)
class Clause:
    """One term of a query, optionally scoped to a field."""

    field: str
    term: str
    exact: bool = False

    def render(self) -> str:
        value = quote(self.term) if self.exact else self.term
        return f"{self.field}:{value}" if self.field else value


def parse_clause(text: str) -> Clause | None:
    """Read `field:value`, a quoted phrase, or a bare term; None for empty."""
    raw = str(text or "").strip()
    if not raw:
        return None
    if ":" in raw:
        field, _, value = raw.partition(":")
        field = field.strip().lower()
        value = value.strip()
        if field and value:
            exact = value.startswith('"') and value.endswith('"') and len(value) > 1
            return Clause(field=field, term=value.strip('"'), exact=exact)
    exact = raw.startswith('"') and raw.endswith('"') and len(raw) > 1
    return Clause(field="", term=raw.strip('"'), exact=exact)


def build_clause(term: str, *, field: str = "") -> Clause | None:
    """Build one clause, applying `field` when the term names none."""
    clause = parse_clause(term)
    if clause is None:
        return None
    if field and not clause.field:
        return Clause(field=field, term=clause.term, exact=clause.exact)
    return clause


def join_clauses(clauses: list[Clause], match: str) -> str:
    """Join the clauses with the connector `match` asks for.

    `match="any"` must use OR; every other value means AND.
    """
    rendered = [clause.render() for clause in clauses if clause is not None]
    if not rendered:
        return ""
    if len(rendered) == 1:
        return rendered[0]
    joiner = " AND "
    return joiner.join(rendered)


def build_query(terms: list[str] | str, *, match: str = "all", field: str = "") -> str:
    """Turn a phrase or a list of terms into one catalogue query clause."""
    if isinstance(terms, str):
        terms = meaningful_terms(terms)
    match = "any" if str(match or "").lower() == "any" else "all"
    clauses: list[Clause] = []
    for term in terms:
        clause = build_clause(term, field=field)
        if clause is not None:
            clauses.append(clause)
    return join_clauses(clauses, match)


def describe(query: str) -> str:
    """One plain sentence about a built query, for a log line."""
    if not query:
        return "the query is empty"
    connector = " OR " if " OR " in query else " AND " if " AND " in query else ""
    if connector:
        return f"{query.count(connector) + 1} clauses joined with {connector.strip()}"
    return "one clause"
''')

_add("tests/test_search.py", '''
"""The specification for `shop.search`; one case fails on the seeded defect."""
from shop.search import build_query, describe, meaningful_terms, quote


def test_empty_phrase_builds_an_empty_query():
    assert build_query("") == ""


def test_stop_words_and_duplicates_are_dropped():
    assert meaningful_terms("the coffee and the coffee for me") == ["coffee", "me"]


def test_all_match_joins_with_and():
    assert build_query("coffee tea", match="all") == "coffee AND tea"


def test_any_match_joins_with_or():
    assert build_query("coffee tea", match="any") == "coffee OR tea"


def test_a_field_prefix_is_kept():
    assert build_query(["title:coffee", "tea"]) == "title:coffee AND tea"


def test_a_quoted_term_stays_one_phrase():
    assert build_query(['"dark roast"', "tea"]) == '"dark roast" AND tea'


def test_one_term_has_no_connector():
    assert build_query("coffee", match="any") == "coffee"


def test_max_terms_keeps_the_first_twelve():
    terms = [f"w{i}" for i in range(20)]
    assert len(meaningful_terms(" ".join(terms))) == 12


def test_quote_escapes_quotes():
    assert quote('a"b') == '"a\\\\"b"'
    assert describe("coffee OR tea") == "2 clauses joined with OR"
''')

# --- the missing-dict-key bug ----------------------------------------------
_add("src/shop/pricing.py", '''
"""The shop's price book.

SKUs are written by people, so the same product arrives as "Gift Card",
"gift-card", "gift card" and "gift_card". `normalise_sku` is the one place
that decides what a SKU is, and every lookup goes through it. This module is
the fixture's missing-dict-key defect: it does not turn a hyphen into an
underscore, so `unit_price("gift-card")` raises KeyError while
`unit_price("gift_card")` works.
"""
from __future__ import annotations

PRICE_BOOK: dict[str, int] = {
    "coffee": 350,
    "tea": 275,
    "mug": 1200,
    "gift_card": 5000,
    "notebook": 800,
}


class UnknownSku(KeyError):
    """Raised for a SKU the price book does not carry."""


def normalise_sku(sku: str) -> str:
    """The canonical form of a SKU: lower case, spaces as underscores."""
    return str(sku or "").strip().lower().replace(" ", "_")


def unit_price(sku: str) -> int:
    """The price of one unit, in integer cents."""
    key = normalise_sku(sku)
    try:
        return PRICE_BOOK[key]
    except KeyError:
        raise UnknownSku(sku) from None


def known_skus() -> list[str]:
    """Every SKU the price book carries, sorted."""
    return sorted(PRICE_BOOK)


def line_total(sku: str, quantity: int) -> int:
    """The price of `quantity` units, in integer cents."""
    if quantity < 0:
        raise ValueError("quantity cannot be negative")
    return unit_price(sku) * quantity
''')

_add("tests/test_pricing.py", '''
"""The specification for `shop.pricing`; one case fails on the seeded defect."""
import pytest

from shop.pricing import UnknownSku, line_total, normalise_sku, unit_price


def test_plain_sku():
    assert unit_price("coffee") == 350


def test_spaces_become_underscores():
    assert unit_price("Gift Card") == 5000


def test_hyphenated_alias_finds_the_gift_card():
    assert unit_price("gift-card") == 5000


def test_line_total_multiplies():
    assert line_total("mug", 3) == 3600


def test_unknown_sku_is_plain():
    with pytest.raises(UnknownSku):
        unit_price("not a product")


def test_normalise_is_stable():
    assert normalise_sku("  MUG ") == "mug"
''')

# --- the off-by-one ---------------------------------------------------------
_add("src/shop/paginate.py", '''
"""Page a list into fixed-size slices.

Pages are numbered from 1. `page_slice(items, size, page)` returns the items
on that page and `page_count(items, size)` says how many pages there are.
This module is the fixture's off-by-one defect: the first page starts one
item too early (at -1), so page 1 repeats an item and the last page is short
by one.
"""
from __future__ import annotations

from typing import Sequence, TypeVar

T = TypeVar("T")


def _check(size: int) -> None:
    if size <= 0:
        raise ValueError("page size must be at least 1")


def page_count(items: Sequence[T], size: int) -> int:
    """How many pages `items` needs at `size` per page."""
    _check(size)
    if not items:
        return 0
    return (len(items) + size - 1) // size


def page_slice(items: Sequence[T], size: int, page: int) -> list[T]:
    """The items on `page` (1-based), at most `size` of them."""
    _check(size)
    if page < 1:
        raise ValueError("pages start at 1")
    start = (page - 1) * size - 1
    return list(items[start:start + size])


def pages(items: Sequence[T], size: int) -> list[list[T]]:
    """Every page, in order."""
    _check(size)
    return [page_slice(items, size, number)
            for number in range(1, page_count(items, size) + 1)]
''')

_add("tests/test_paginate.py", '''
"""The specification for `shop.paginate`; one case fails on the seeded defect."""
import pytest

from shop.paginate import page_count, page_slice, pages


def test_page_count_rounds_up():
    assert page_count(list(range(7)), 3) == 3


def test_page_slice_first_page_starts_at_the_first_item():
    assert page_slice(list(range(7)), 3, 1) == [0, 1, 2]


def test_page_slice_second_page():
    assert page_slice(list(range(7)), 3, 2) == [3, 4, 5]


def test_last_page_is_short_not_missing():
    assert page_slice(list(range(7)), 3, 3) == [6]


def test_pages_cover_every_item_once():
    assert pages(list(range(7)), 3) == [[0, 1, 2], [3, 4, 5], [6]]


def test_bad_size_is_refused():
    with pytest.raises(ValueError):
        page_count([1], 0)
''')

# --- the pure function T1.2 writes tests for --------------------------------
_add("src/shop/discount.py", '''
"""A pure function the unit-test-generation test writes tests for.

`progressive_discount` returns the discount in integer cents for an order
total and a loyalty tier. It has no I/O, no clock and no randomness, so four
edge-case tests are enough to pin it down.

The rules, which the tests must not change:

    negative cents          ValueError
    tier 0, or zero cents   0
    tier 1                  10% of the total, rounded down
    tier 2                  20% of the total, capped at 2,000 cents
    tier 3                  25% of the total, capped at 5,000 cents
    any other tier          ValueError
"""
from __future__ import annotations


def progressive_discount(cents: int, tier: int) -> int:
    """The discount, in integer cents, for an order total and loyalty tier."""
    if isinstance(cents, bool) or not isinstance(cents, int):
        raise TypeError("cents must be an integer number of cents")
    if cents < 0:
        raise ValueError("an order total cannot be negative")
    if tier not in (0, 1, 2, 3):
        raise ValueError("tier must be 0, 1, 2 or 3")
    if cents == 0 or tier == 0:
        return 0
    if tier == 1:
        return cents // 10
    if tier == 2:
        return min(cents // 5, 2_000)
    return min(cents // 4, 5_000)
''')

_add("tests/test_discount.py", '''
"""The small baseline suite T1.2 must leave alone."""
from shop.discount import progressive_discount


def test_a_plain_tier_one_order():
    assert progressive_discount(2_000, 1) == 200


def test_zero_is_zero():
    assert progressive_discount(0, 3) == 0
''')

# --- the four-file refactor T2.3 needs --------------------------------------
_add("src/shop/money.py", '''
"""Money helpers. The shop's public unit is the integer cent.

`format_money` is the only place that turns cents into text, so every screen
and report formats the same way: a dollar sign, thousands separators and two
decimal places.
"""
from __future__ import annotations


def dollars_to_cents(value: float) -> int:
    """An amount in dollars, as integer cents (half-up at the half cent)."""
    return int(round(float(value) * 100))


def cents_to_dollars(cents: int) -> float:
    """Integer cents as a float number of dollars - for display only."""
    return round(int(cents) / 100.0, 2)


def format_money(cents: int) -> str:
    """`123456` -> `"$1,234.56"`."""
    cents = int(cents)
    sign = "-" if cents < 0 else ""
    whole, part = divmod(abs(cents), 100)
    return f"{sign}${whole:,}.{part:02d}"
''')

_add("src/shop/cart.py", '''
"""A basket of line items. This is the T2.3 refactor's first file.

THE SEEDED STATE: the cart stores each unit price in FLOAT DOLLARS, and
`subtotal_dollars` is the only subtotal it offers. `tests/test_checkout.py`
asks for integer cents (`subtotal_cents`, and an `add` that takes cents).
The refactor makes the cart store integer cents and offer `subtotal_cents`;
`subtotal_dollars` may stay as a display helper.
"""
from __future__ import annotations

from .money import cents_to_dollars


class Cart:
    """A list of (sku, unit price, quantity) lines."""

    def __init__(self) -> None:
        self._lines: list[dict] = []

    def add(self, sku: str, unit_cents: int, quantity: int = 1) -> None:
        if quantity < 0:
            raise ValueError("quantity cannot be negative")
        self._lines.append(
            {"sku": sku, "unit_dollars": cents_to_dollars(unit_cents),
             "quantity": quantity}
        )

    @property
    def lines(self) -> list[dict]:
        return list(self._lines)

    def subtotal_dollars(self) -> float:
        total = sum(line["unit_dollars"] * line["quantity"] for line in self._lines)
        return round(total, 2)

    def is_empty(self) -> bool:
        return not self._lines
''')

_add("src/shop/checkout.py", '''
"""Turning a cart into a total. This is the T2.3 refactor's second file.

THE SEEDED STATE: every amount is a float number of dollars. The tests ask
for `checkout_total_cents(cart, shipping_cents=0)` returning integer cents,
with 8.25% tax rounded half-up to the nearest cent, applied to the subtotal
before shipping is added.
"""
from __future__ import annotations

from .cart import Cart

TAX_RATE = 0.0825


def tax_dollars(subtotal_dollars: float) -> float:
    """The tax on a subtotal, in dollars."""
    return round(float(subtotal_dollars) * TAX_RATE, 2)


def checkout_total_dollars(cart: Cart, shipping_dollars: float = 0.0) -> float:
    """The whole total, in dollars."""
    subtotal = cart.subtotal_dollars()
    return round(subtotal + tax_dollars(subtotal) + float(shipping_dollars), 2)
''')

_add("src/shop/report.py", '''
"""The invoice text. This is the T2.3 refactor's third file.

THE SEEDED STATE: the invoice is formatted from float dollars, so a total of
12.34 can print as "$12.34" or "$12.339999" depending on the arithmetic.
The tests ask for `invoice_total_line(cart, shipping_cents=0)`, using
`shop.money.format_money`, and for `invoice_rows(cart)` to name each line's
own amount in integer cents.
"""
from __future__ import annotations

from .cart import Cart
from .checkout import checkout_total_dollars


def invoice_rows(cart: Cart) -> list[dict]:
    """One row per line: the sku, the quantity and the money figures."""
    return [
        {"sku": line["sku"], "quantity": line["quantity"],
         "unit_dollars": line["unit_dollars"],
         "line_dollars": round(line["unit_dollars"] * line["quantity"], 2)}
        for line in cart.lines
    ]


def invoice_total_line(cart: Cart, shipping_dollars: float = 0.0) -> str:
    """The final invoice line, in dollars."""
    total = checkout_total_dollars(cart, shipping_dollars)
    return f"Total: ${total:,.2f}"
''')

_add("tests/test_checkout.py", '''
"""The specification for the four-file money refactor (T2.3).

The public unit is the integer cent. A cart added up in cents and a total
computed in cents must not depend on float rounding, and the invoice text must
come from `shop.money.format_money`.
"""
from shop.cart import Cart
from shop.checkout import checkout_total_cents
from shop.money import format_money
from shop.report import invoice_rows, invoice_total_line


def make_cart() -> Cart:
    cart = Cart()
    cart.add("coffee", 350, 2)
    cart.add("mug", 1_200, 1)
    return cart


def test_subtotal_is_integer_cents():
    assert make_cart().subtotal_cents() == 1_900


def test_checkout_adds_tax_in_cents():
    # 8.25% of 1,900 is 156.75 cents, half-up to 157.
    assert checkout_total_cents(make_cart()) == 2_057


def test_checkout_adds_shipping_after_tax():
    assert checkout_total_cents(make_cart(), shipping_cents=500) == 2_557


def test_invoice_rows_are_in_cents():
    assert invoice_rows(make_cart())[0] == {
        "sku": "coffee", "quantity": 2, "unit_cents": 350, "line_cents": 700,
    }


def test_invoice_total_line_uses_format_money():
    assert invoice_total_line(make_cart(), shipping_cents=500) == "Total: $25.57"


def test_format_money_is_exact():
    assert format_money(123_456) == "$1,234.56"
    assert format_money(-5) == "-$0.05"
''')

#: The file a single-file test names, and the one path its answer may write.
SINGLE_FILE_TASKS = {
    "or_query": "src/shop/search.py",
    "missing_key": "src/shop/pricing.py",
    "off_by_one": "src/shop/paginate.py",
}

#: The file each seeded defect's failing test lives in.
DEFECT_TESTS = {
    "or_query": "tests/test_search.py",
    "missing_key": "tests/test_pricing.py",
    "off_by_one": "tests/test_paginate.py",
}


def files() -> dict[str, str]:
    """The fixture's files, path -> text. A copy; callers cannot change it."""
    return dict(_FILES)


def digest(path: str) -> str:
    """The SHA-256 of one fixture file, for the unchanged-source check."""
    return hashlib.sha256(_FILES[path].encode("utf-8")).hexdigest()


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "core.autocrlf=false", *args],
        capture_output=True, text=True, timeout=120,
    )
    if check and done.returncode != 0:
        raise RuntimeError(
            "git " + " ".join(args) + " failed: "
            + (done.stderr.strip() or done.stdout.strip() or f"exit {done.returncode}")
        )
    return done


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def build(root: Path, *, name: str = "bench-shop") -> Path:
    """Write the fixture into `root/name`, commit it, and return the repo path.

    The root must NOT be inside this repository. That is not a convention
    here; it is refused, because the golden rule says the benchmark never
    writes a file in the checkout it is developed in.
    """
    here = Path(__file__).resolve().parents[2]
    repo = Path(root) / name
    if _inside(repo, here):
        raise ValueError(
            f"refusing to build a disposable repo inside the checkouts tree: {repo}"
        )
    if repo.exists():
        raise FileExistsError(f"the disposable repo already exists: {repo}")
    repo.mkdir(parents=True)
    for relative, text in _FILES.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    # A marker file so a stray copy is recognisable as benchmark scratch.
    (repo / ".bench-coding-repo").write_text(
        "This repository was made by tools/bench_coding for one benchmark test.\n"
        "It has no remote and is safe to delete.\n",
        encoding="utf-8", newline="\n",
    )
    _git(repo, "init", "-q", "-b", BRANCH)
    _git(repo, "config", "user.name", AUTHOR)
    _git(repo, "config", "user.email", EMAIL)
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "bench: the fixture as the benchmark starts")
    return repo


def make_scratch(prefix: str = "jarvis-bench-coding-") -> Path:
    """A new temporary folder, preferring the local app data area on Windows."""
    base = os.environ.get("LOCALAPPDATA")
    if base and Path(base).is_dir():
        parent = Path(base) / "Jarvis" / "bench-coding" / "tmp"
        parent.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix=prefix, dir=str(parent)))
    return Path(tempfile.mkdtemp(prefix=prefix))


def remove(path: Path) -> None:
    """Delete a disposable repo, with a guard that it really is one."""
    import stat  # noqa: PLC0415 - only needed for the Windows read-only .git files

    path = Path(path)
    if not path.exists():
        return
    if not ((path / ".bench-coding-repo").exists()
            or path.name.startswith(("jarvis-bench-coding-", "bench-shop"))):
        raise ValueError(
            f"refusing to delete a folder that is not a benchmark repo: {path}")

    def _force(function, failed_path, _exception):
        try:
            os.chmod(failed_path, stat.S_IWRITE)
            function(failed_path)
        except OSError:
            pass

    shutil.rmtree(path, onerror=_force)


if __name__ == "__main__":  # a manual look at the fixture
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else make_scratch()
    built = build(target)
    print(built)
    print("\n".join(sorted(str(p.relative_to(built)) for p in built.rglob("*")
                           if p.is_file() and ".git" not in p.parts)))
