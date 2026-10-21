"""test_tellme_price_radar.py - Price-watch Slice 1 (2026-10-21): the
page-watch snapshot reads the price/stock a shop marks for MACHINES (the
schema.org JSON-LD `price_of()` already used, and the OpenGraph/meta tags
beside it), and the zero-dependency fetch hygiene the radar will use:
a tracking-URL canonicaliser, a coherent browser-header builder and a
jittered scheduling helper.

    python3 backend/test_tellme_price_radar.py

WHAT IS PROVED HERE, with plain code and no network:

  * JSON-LD Product / AggregateOffer / Flight prices, top-level lists,
    `@graph`, `offers`, `lowPrice`, `<!-- -->` wrappers - and one malformed
    block never hides the good ones;
  * INTEGER whole cents, exactly: "$1,249.99" and the JSON number 1249.99
    are both 124999, never a float artefact, on both sides of the merge;
  * NO double count: a machine-marked price the visible words repeat is
    listed ONCE, and machine prices come before the shown ones;
  * schema.org availability -> the existing vocabulary (InStock/
    LimitedAvailability -> in_stock, OutOfStock/SoldOut -> out_of_stock,
    PreOrder -> unknown, left to the visible words), machine state wins when
    definite;
  * determinism: the same page always gives the same snapshot, and changing
    only the machine markup leaves `clean_sha256` alone (it is not page
    words);
  * REGRESSION: `price_of()` still prefers JSON-LD over meta and still
    returns the same float/None contract, so the price-watch path is
    untouched;
  * the canonicaliser: utm/gclid/fbclid/... stripped, product params
    (id/sku/model/pid/variant) kept, host/path/order/fragment kept,
    idempotent, relative/empty left alone;
  * the header profiles: no Cookie/If-None-Match/If-Modified-Since ever,
    every Sec-CH-UA platform and mobile hint matching its own User-Agent,
    no client hints from Firefox/Safari/iOS, referrer mode;
  * the scheduler helper: +/-30% jitter, the 300 s floor, determinism
    under an injected RNG.
"""
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

sys.path.insert(0, str(HERE / "rebuilt"))
require_shipped("jarvis_tellme.py")
import jarvis_tellme as TM  # noqa: E402

FAILED, PASSED = [], []


def check(what, ok, detail=""):
    if ok:
        PASSED.append(what)
        print(f"  ok    {what}")
    else:
        FAILED.append(what)
        print(f"  FAIL  {what}" + (f" - {detail}" if detail else ""))


def _ld(doc, extra="") -> str:
    return (f'<html><body><script type="application/ld+json">'
            f'{json.dumps(doc)}</script>{extra}</body></html>')


def _page(signals: dict) -> str:
    return _ld({"@type": "Product", "name": "Kettle", "offers": {
        "@type": "Offer", "price": signals.get("price", "249.99"),
        "priceCurrency": "USD",
        "availability": signals.get("availability", "https://schema.org/InStock"),
    }}, extra=f'<p>Now ${signals.get("shown", "249.99")} - In stock</p>')


# ------------------------------------------------------------------ JSON-LD --


def t_jsonld_product_price_is_exact_integer_cents():
    sig = TM.extract_watch_signals(_page({}))
    check("a Product/Offer JSON-LD price is read, in whole cents",
          sig["prices_cents"] == [24999], sig)
    check("it is an int, never a float",
          all(isinstance(c, int) for c in sig["prices_cents"]), sig)
    check("its availability is read (schema.org InStock -> in_stock)",
          sig["stock_state"] == "in_stock", sig)

    by_string = TM.extract_watch_signals(_ld({
        "@type": "Offer", "price": "$1,249.99", "availability": "InStock"}))
    check('a string "$1,249.99" is exactly 124999',
          by_string["prices_cents"] == [124999], by_string)
    by_number = TM.extract_watch_signals(_ld({
        "@type": "Offer", "price": 1249.99}))
    check("the JSON NUMBER 1249.99 is exactly 124999 (Decimal, no float artefact)",
          by_number["prices_cents"] == [124999], by_number)
    european = TM.extract_watch_signals(_ld({"@type": "Offer", "price": "1.299,99"}))
    check('European "1.299,99" is exactly 129999',
          european["prices_cents"] == [129999], european)
    too_small = TM.extract_watch_signals(_ld({"@type": "Offer", "price": "0"}))
    check("a zero price is not a price",
          too_small["prices_cents"] == [], too_small)


def t_aggregate_graph_and_flight():
    graph = {"@context": "https://schema.org", "@graph": [
        {"@type": "Product", "name": "Kettle"},
        {"@type": "AggregateOffer", "lowPrice": "899.00", "highPrice": "1299.00",
         "priceCurrency": "USD", "availability": "https://schema.org/OutOfStock"},
    ]}
    machine = TM._machine_watch_signals(_ld(graph))
    check("an AggregateOffer's lowPrice is read in whole cents",
          machine[0] == [89900], machine)
    check("highPrice is not read as a second (wrong) price",
          129900 not in machine[0], machine)
    sig = TM.extract_watch_signals(_ld(graph, extra="<p>Was $1,299.00</p>"))
    check("the shown range is still collected as a visible price",
          sig["prices_cents"] == [89900, 129900], sig)
    check("an @graph's availability is read", sig["stock_state"] == "out_of_stock", sig)
    top_list = [{"@type": "Product", "offers": {"@type": "Offer", "price": "77.70"}}]
    check("a top-level LIST of JSON-LD documents is read",
          TM.extract_watch_signals(_ld(top_list))["prices_cents"] == [7770])
    flight = {"@type": "Flight", "flightNumber": "BA1", "offers": {
        "@type": "Offer", "price": "450.00"}}
    check("a Flight's offer price is read too",
          TM.extract_watch_signals(_ld(flight))["prices_cents"] == [45000])
    malformed = ('<script type="application/ld+json">{not json at all</script>'
                 '<script type="application/ld+json">{"@type": "Offer", "price": "12.34"}'
                 '</script>')
    good = TM.extract_watch_signals(f"<html>{malformed}</html>")
    check("one malformed block never hides a good one",
          good["prices_cents"] == [1234], good)
    wrapped = ('<script type="application/ld+json"><!-- {"@type": "Offer",'
               ' "price": "5.00"} --></script>')
    check("a <!-- -->-wrapped block is tolerated",
          TM.extract_watch_signals(f"<html>{wrapped}</html>")["prices_cents"] == [500])


def t_no_double_count_with_visible_and_meta():
    same = TM.extract_watch_signals(_page({}))
    check("JSON-LD 249.99 + meta-less visible $249.99 is listed ONCE",
          same["prices_cents"] == [24999], same)

    meta_page = ('<html><head>'
                 '<meta property="product:price:amount" content="1,249.99">'
                 '</head><body><p>Now $1,249.99</p></body></html>')
    meta = TM.extract_watch_signals(meta_page)
    check("a meta price is read too, once, and beats the visible repeat",
          meta["prices_cents"] == [124999], meta)

    both = ('<html><head><meta property="og:price:amount" content="1249.99"></head>'
            '<body><script type="application/ld+json">'
            '{"@type": "Offer", "price": "1249.99"}</script>'
            '<p>$1,249.99</p></body></html>')
    check("JSON-LD + meta + visible, all the same amount: ONE entry",
          TM.extract_watch_signals(both)["prices_cents"] == [124999])

    different = _page({"price": "10.00", "shown": "12.00"})
    sig = TM.extract_watch_signals(different)
    check("machine prices come FIRST, then shown ones not already counted",
          sig["prices_cents"] == [1000, 1200], sig)


def t_availability_mapping_is_the_existing_vocabulary():
    cases = [
        ("https://schema.org/InStock", "in_stock"),
        ("InStock", "in_stock"),
        ("https://schema.org/LimitedAvailability", "in_stock"),
        ("https://schema.org/OutOfStock", "out_of_stock"),
        ("OutOfStock", "out_of_stock"),
        ("https://schema.org/SoldOut", "out_of_stock"),
    ]
    for value, want in cases:
        got = TM.extract_watch_signals(
            _ld({"@type": "Offer", "price": "1.00", "availability": value}))
        check(f"availability {value!r} -> {want}", got["stock_state"] == want, got)
    preorder = TM.extract_watch_signals(
        _ld({"@type": "Offer", "price": "1.00",
             "availability": "https://schema.org/PreOrder"}))
    check("PreOrder is not claimed as in_stock or out_of_stock",
          preorder["stock_state"] == "unknown", preorder)
    marked_out = _page({})   # visible words say In stock...
    marked_out = marked_out.replace("https://schema.org/InStock",
                                    "https://schema.org/OutOfStock")
    check("a definite machine state wins over contradicting visible words",
          TM.extract_watch_signals(marked_out)["stock_state"] == "out_of_stock")
    preorder_with_words = _ld(
        {"@type": "Offer", "price": "1.00",
         "availability": "PreOrder"}, extra="<p>In stock</p>")
    check("an UNKNOWN machine state does not hide the visible answer",
          TM.extract_watch_signals(preorder_with_words)["stock_state"] == "in_stock")


def t_deterministic_and_machine_markup_is_not_page_words():
    text = _page({})
    once = TM.extract_watch_signals(text)
    twice = TM.extract_watch_signals(text)
    check("the same page gives the same snapshot twice", once == twice, once)
    plain_visible = ("<html><body><p>Now $249.99 - In stock</p></body></html>")
    with_markup = _page({})
    check("a JSON-LD block does not move clean_sha256 (it is not page words)",
          TM.extract_watch_signals(plain_visible)["clean_sha256"]
          == TM.extract_watch_signals(with_markup)["clean_sha256"])
    changed = TM.extract_watch_signals(_page({"price": "199.99"}))
    check("but a changed machine price IS a different snapshot",
          changed["prices_cents"] != once["prices_cents"], changed)


def t_snapshot_kind_moved_so_an_upgrade_does_not_ring():
    old = ("t2:" + json.dumps({"prices_cents": [24999], "versions": [],
                               "stock_state": "in_stock", "clean_sha256": "a" * 64,
                               "words": "", "last_good_at": 1}))
    check("a pre-machine-markup t2 snapshot is now an OLD kind",
          TM._print_kind(old) == "", TM._print_kind(old))
    fresh = TM._page_state(_page({}).encode("utf-8"), "text/html")
    check("the snapshot a look keeps now is the t3 kind",
          TM._print_kind(fresh) == TM.PAGE_STATE and fresh.startswith(TM.PAGE_STATE),
          fresh[:12])
    check("t2 and t3 are NOT the same kind (so the first look re-baselines silently)",
          TM._print_kind(old) != TM._print_kind(fresh))


# ------------------------------------------------- price-watch REGRESSION ---


def t_price_of_still_prefers_json_ld():
    html = _ld({"@type": "Offer", "price": "10.00"},
               extra='<meta property="product:price:amount" content="99.00">')
    got = TM.price_of(html.encode("utf-8"), "text/html")
    check("price_of() still returns the JSON-LD price, not the meta one",
          got == 10.0 and isinstance(got, float), repr(got))
    meta_only = ('<html><head><meta property="product:price:amount" content="99.00">'
                 '</head></html>')
    check("meta-only pages still answer from the meta tag",
          TM.price_of(meta_only.encode("utf-8"), "text/html") == 99.0)
    shown_only = "<html><body><p>£5.50</p></body></html>"
    check("the visible-price fallback is unchanged",
          TM.price_of(shown_only.encode("utf-8"), "text/html") == 5.5)
    check("no price at all is still None",
          TM.price_of(b"<html><body>nothing</body></html>", "text/html") is None)


# ------------------------------------------------------------ canonical URL --


def t_canonicalizer_table():
    cases = [
        ("https://shop.example/p/1?utm_source=news&utm_medium=email&id=7&sku=A1",
         "https://shop.example/p/1?id=7&sku=A1"),
        ("https://shop.example/p/1?gclid=xyz&fbclid=a&msclkid=b&mc_eid=c&_ga=d",
         "https://shop.example/p/1"),
        ("https://shop.example/p/1?ref=home&ref_src=nav&tag=aff&ascsubtag=s&psc=1",
         "https://shop.example/p/1"),
        ("https://shop.example/p/1?pf_rd_r=AAA&pd_rd_x=BBB&model=K1",
         "https://shop.example/p/1?model=K1"),
        ("https://shop.example/p/1?id=7&pid=9&variant=red&sku=A1#reviews",
         "https://shop.example/p/1?id=7&pid=9&variant=red&sku=A1#reviews"),
        ("https://shop.example/p/1?UTM_Source=x&ID=keep", "https://shop.example/p/1?ID=keep"),
    ]
    for before, want in cases:
        got = TM.canonicalize_watch_url(before)
        check(f"canonicalise keeps the product and drops the tracking: {before[:44]}",
              got == want, got)
    for before, _ in cases:
        once = TM.canonicalize_watch_url(before)
        check(f"idempotent: {before[:44]}",
              TM.canonicalize_watch_url(once) == once, once)
    clean = "https://shop.example/p/1?id=7&variant=red"
    check("a URL with no tracking is returned exactly as it was",
          TM.canonicalize_watch_url(clean) == clean)
    for value in ("", "   ", "/p/1?utm_source=x", "not a url", "https://[bad"):
        check(f"an address with nothing to canonicalise is left alone: {value!r}",
              TM.canonicalize_watch_url(value) == (value or "").strip())


# ---------------------------------------------------------------- headers ---


def t_header_profiles_are_coherent_and_never_send_state():
    profiles = len(TM._HEADER_PROFILES)
    check("seven browser profiles", profiles == 7, profiles)
    forbidden = ("cookie", "if-none-match", "if-modified-since")
    seen_platforms = set()
    for index in range(profiles):
        headers = TM.build_decoupled_headers(index)
        lowered = {k.lower() for k in headers}
        check(f"profile {index}: never Cookie/If-None-Match/If-Modified-Since",
              not any(name in lowered for name in forbidden), sorted(lowered))
        ua = headers.get("User-Agent", "")
        check(f"profile {index}: a real browser User-Agent", bool(ua) and "Mozilla/5.0" in ua, ua)
        check(f"profile {index}: Accept-Language a browser sends",
              headers.get("Accept-Language", "").startswith("en-US"), headers.get("Accept-Language"))
        check(f"profile {index}: Sec-Fetch-Dest is a document navigation",
              headers.get("Sec-Fetch-Dest") == "document"
              and headers.get("Sec-Fetch-Mode") == "navigate", headers.get("Sec-Fetch-Dest"))
        hint = headers.get("Sec-CH-UA", "")
        platform = headers.get("Sec-CH-UA-Platform", "")
        mobile = headers.get("Sec-CH-UA-Mobile", "")
        chromium = "Chrome/" in ua and "Chromium" in hint
        # A browser that is not Chromium (Firefox, Safari, iOS) sends no
        # client hints at all - the profiles say the same.
        firefox_or_safari = "Chrome/" not in ua
        if firefox_or_safari:
            check(f"profile {index}: Firefox/Safari sends NO client hints",
                  not hint and not platform and not mobile, (hint, platform, mobile))
            continue
        check(f"profile {index}: a Chromium profile carries its client hints",
              chromium and bool(platform) and bool(mobile), (ua, hint))
        if mobile:
            seen_platforms.add(platform)
        # The hint must name the same platform the User-Agent does.
        if "Windows NT" in ua:
            check(f"profile {index}: Windows UA has a Windows hint",
                  platform == '"Windows"' and mobile == "?0", (platform, mobile))
        elif "Macintosh" in ua:
            check(f"profile {index}: macOS UA has a macOS hint",
                  platform == '"macOS"' and mobile == "?0", (platform, mobile))
        elif "Android" in ua:
            check(f"profile {index}: Android UA has an Android hint and mobile ?1",
                  platform == '"Android"' and mobile == "?1", (platform, mobile))
        else:
            check(f"profile {index}: UA and hint agree", False, ua)
    check("all three client-hint platforms are represented",
          seen_platforms == {'"Windows"', '"macOS"', '"Android"'}, seen_platforms)


def t_header_builder_selection_and_referrer():
    check("no persona index is the first profile, deterministically",
          TM.build_decoupled_headers() == TM.build_decoupled_headers(0))
    check("an index wraps like a stable job id",
          TM.build_decoupled_headers(7) == TM.build_decoupled_headers(0)
          and TM.build_decoupled_headers(-1) == TM.build_decoupled_headers(6))
    check("no Referer by default",
          "Referer" not in TM.build_decoupled_headers(0))
    check("search_comparison sends exactly a Google search referrer",
          TM.build_decoupled_headers(0, "search_comparison").get("Referer")
          == "https://www.google.com/")
    check("an unknown referrer mode sends none",
          "Referer" not in TM.build_decoupled_headers(0, "somewhere_private"))
    first = TM.build_decoupled_headers(0)
    first["Cookie"] = "leaked=1"
    check("the builder returns a copy - a caller cannot poison the profile",
          "Cookie" not in TM.build_decoupled_headers(0))


# --------------------------------------------------------------- scheduler --


def t_jitter_bounds_determinism_and_floor():
    now = 1_000_000.0
    seen = set()
    ok_bounds = True
    for seed in range(200):
        ts = TM.next_poll_timestamp(600, rng=random.Random(seed), now=now)
        interval = ts - now
        seen.add(round(interval, 3))
        if not (420.0 <= interval <= 780.0):
            ok_bounds = False
    check("200 seeded looks all stay inside +/-30% of a 600 s base", ok_bounds)
    check("...and the jitter really varies", len(seen) > 100, len(seen))
    small = [TM.next_poll_timestamp(60, rng=random.Random(seed), now=now) - now
             for seed in range(50)]
    check("the 300 s floor holds for a small base interval",
          all(i >= 300.0 for i in small), min(small))
    one = TM.next_poll_timestamp(600, rng=random.Random(3), now=now)
    two = TM.next_poll_timestamp(600, rng=random.Random(3), now=now)
    check("the same RNG state gives the same timestamp (deterministic)", one == two)
    check("a different RNG state gives a different timestamp",
          len({TM.next_poll_timestamp(600, rng=random.Random(seed), now=now)
               for seed in range(10)}) > 1)

    class Fixed:
        def __init__(self):
            self.calls = []

        def uniform(self, a, b):
            self.calls.append((a, b))
            return 0.0

    fixed = Fixed()
    got = TM.next_poll_timestamp(600, rng=fixed, now=now)
    check("an injected RNG is really used, with -30%..+30% bounds",
          fixed.calls == [(-0.30, 0.30)] and got == now + 600.0, (fixed.calls, got))
    check("a nonsense base interval still respects the floor",
          TM.next_poll_timestamp(None, rng=random.Random(1), now=now) - now >= 300.0
          and TM.next_poll_timestamp(-5, rng=random.Random(1), now=now) - now >= 300.0)


if __name__ == "__main__":
    for fn in (t_jsonld_product_price_is_exact_integer_cents,
               t_aggregate_graph_and_flight,
               t_no_double_count_with_visible_and_meta,
               t_availability_mapping_is_the_existing_vocabulary,
               t_deterministic_and_machine_markup_is_not_page_words,
               t_snapshot_kind_moved_so_an_upgrade_does_not_ring,
               t_price_of_still_prefers_json_ld,
               t_canonicalizer_table,
               t_header_profiles_are_coherent_and_never_send_state,
               t_header_builder_selection_and_referrer,
               t_jitter_bounds_determinism_and_floor):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            import traceback
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
