"""jarvis_product_check.py - the wiring for the product check: ONE card, one
read-only browser read, and the reasons report back in plain words.

WHY THIS EXISTS (2026-11-04, the owner's choice: "wire the existing product
check"). The engine (`jarvis_product_research.py`), the read half
(`jarvis_product_read.py`) and the capture seam (`jarvis_product_capture.py`)
shipped between 2026-10-25 and 2026-10-26, and **nothing imported them**: no
route, no chat tool, no approval card, no Settings row and no app screen. So
the owner could not ask Jarvis to check a product at all. This module is the
door, and nothing else: it adds no new analysis, no new rule and no new
network code.

WHAT THE OWNER GETS
  1. They give Jarvis one Amazon product link.
  2. ONE approval card names the page in full and says exactly what happens:
     "Read this product page in your own browser session? Read-only; nothing
     is bought or added to a cart." The card is PC-only (it is this PC's
     signed-in browser window), and the apps hold Approve on a stale link like
     every card.
  3. Only after that yes, ONE page is opened in the owner's own visible,
     signed-in Chromium (`jarvis_browser_control.read_page_html`, the browser
     module's public read seam) and read.
  4. The engine's report comes back: the sample caveat FIRST, the listing
     facts, the eight signals with their counts and examples, every set-aside
     review with its reasons, the verdict in words, and what could not be
     checked.

WHAT IT NEVER DOES, AND WHY EACH IS A RULE RATHER THAN A HOPE
  * **No trust score and no per-review fake/real verdict.** The engine has no
    field for either, and this module adds none: people and LLMs are at chance
    telling AI-written reviews from real ones (the design contract's measured
    reason), so a number or a label would be false precision. The report shows
    patterns, counts and reasons.
  * **Nothing is removed from the sample.** A set-aside review stays in every
    count and is listed with its reasons; the owner can overrule any flag.
  * **Never buys, orders, signs in, types or clicks.** The URL is checked
    against the read-only policy BEFORE a card; the browser seam does one
    navigation and one read; a cart/checkout/order/account/payment/sign-in
    address is refused by shape.
  * **Never solves a CAPTCHA and never retries one.** A challenge page raises
    `ChallengeDetected` and the owner is told to open the page themselves.
  * **Never opens a second page.** The read is one address, no links followed.
  * **Nothing is stored.** No file, no cache, no database, no log of the page:
    the report lives in the answer (and in the route's response) and nowhere
    else. The one thing kept is the browser's own sign-in profile, in the
    config folder, which is what makes the one-time login work.
  * **Off by default.** `[product_check] enabled = false` in both shipped
    settings copies; a missing section reads as OFF (fail closed). The tool is
    not even offered to the model while it is off, and the route answers "off".

THE ACTION AND THE TIER
The tool asks the gate under its OWN action name, `product_check`, whose
shipped tier is "ask" (`[autonomy.tiers]` in both settings copies). The action
is in `jarvis_owner_check.PC_ONLY_ACTIONS`, so only this PC can approve it,
with Windows Hello - the browser window and the signed-in profile are here, so
a phone's yes would promise a read nothing on the phone can perform. A model
call can ask for that card and never decide it (`jarvis_agent.NEEDS_A_PERSON`).

THE ROUTE
POST /api/product/check  {"url": "..."} -> the JSON report (200), after the
same ONE card. PC-only, refused from another device before the body is read.
The route WAITS for the card, because the desktop is the only caller and the
card is on its screen; a denial or a lapse returns 403 with plain words and
nothing is read. The chat tool is the other door to the same plan/run code.

    py -3 -B backend/test_product_check_wiring.py
"""
from __future__ import annotations

import datetime as _dt
import json

import jarvis_product_capture as CAPTURE
import jarvis_product_read as READ
import jarvis_product_research as ENGINE

#: The settings-file section. Same shape as `[price_radar]`: a hand-edited
#: line, off in both shipped copies, missing-as-off.
SWITCH_SECTION = "product_check"

#: The model-facing tool name and the gate action. One name for both, which is
#: `Tool`'s own default when no `gate_lookup_name` is given.
TOOL_NAME = "product_check"
ACTION = "product_check"

#: The one route. See the module docstring.
PATH = "/api/product/check"

#: The question on the card, word for word (the owner's brief, 2026-11-04).
CARD_QUESTION = ("Read this product page in your own browser session? "
                 "Read-only; nothing is bought or added to a cart.")

#: What the tool/route says when the switch is off. Read fresh every time.
#: Plain words on purpose: the zero-jargon scanner counts a settings key named
#: in a user-facing sentence as developer jargon (`tools/check_zero_jargon.py`,
#: "config key"), and this sentence is shown to the owner.
OFF_WORDS = ("The product check is switched off. Turn it on in Jarvis's settings "
             "file on this PC, then try again. Nothing was opened and nothing "
             "was read.")

#: What the route says to a caller that is not this PC.
PC_ONLY_WORDS = ("The product check reads this PC's own signed-in browser "
                 "window, so only the PC can run it. Nothing was opened and "
                 "nothing was read.")

#: The tool description the model reads lives in `jarvis_agent` beside the
#: Tool entry (PRODUCT_CHECK_DESCRIPTION): it is measured with every other
#: tool's text by `backend/test_tool_text.py`, and a second copy here would be
#: a copy that can drift. Nothing in this module shows words to the model.


#: One line per signal, for the plain-words answer. The engine's own names are
#: code names; these are the words a person reads.
SIGNAL_WORDS = {
    "verified_purchase_share": "Verified Purchase badges",
    "vine_share": "Vine reviews",
    "incentive_language": "Incentive wording in the reviews",
    "near_duplicate_wording": "Near-duplicate wording",
    "date_burstiness": "Bursts of reviews on one day",
    "rating_histogram": "The rating shape",
    "stylometry": "Generic-sounding prose (a weak cue)",
    "review_product_mismatch": "Reviews that do not match this product",
}

#: The closing line of every answer. The report must never be read as a score.
NO_SCORE_LINE = ("No trust score and no fake/real verdict for any review: these "
                 "are patterns with counts and reasons, not proof.")

#: The sentence a page that cannot be read gets. It names the one-time login
#: and says what to do, never a credential.
LOGIN_HINT = ("If Amazon asks you to sign in, sign in once in the browser window "
              "that just opened; Jarvis never sees or types the password. Then "
              "ask for the check again.")

#: How many characters of one snippet the plain answer shows.
SNIPPET_CHARS = 160


class CheckRefused(Exception):
    """Nothing was opened and nobody was asked; `why` is in plain words."""

    def __init__(self, why: str, *, kind: str = "refused") -> None:
        super().__init__(why)
        self.why = str(why)
        self.kind = str(kind or "refused")


class ProductPagePlan:
    """One address to read, decided before the card. No network, no browser."""

    def __init__(self, url: str) -> None:
        self.url = url

    def __repr__(self) -> str:                       # pragma: no cover - debugging
        return f"ProductPagePlan({self.url!r})"


# --------------------------------------------------------------------------
#   The switch
# --------------------------------------------------------------------------

def enabled() -> bool:
    """`[product_check] enabled`, read fresh. False when it cannot be read.

    Fail closed: a missing settings file, a missing section, a broken file or a
    value that is not a real `true` all mean off - the same rule
    `jarvis_price_radar.enabled()` uses, and the reason a fresh install reads
    exactly the shipped `false` line."""
    try:
        import jarvis_framework as fw
        section = (fw.load_framework() or {}).get(SWITCH_SECTION) or {}
        return section.get("enabled") is True
    except Exception:
        return False


# --------------------------------------------------------------------------
#   Plan (before the card) and run (after the yes)
# --------------------------------------------------------------------------

def plan(url) -> ProductPagePlan:
    """Decide one address is a readable Amazon product page, or refuse.

    Runs BEFORE any card and BEFORE any browser: a bad shape, a non-Amazon
    host, a product URL without an ASIN or a cart/checkout/order/account/
    payment/sign-in address raises `CheckRefused` in plain words, and nobody is
    asked about something that cannot happen."""
    if not isinstance(url, str) or not url.strip():
        raise CheckRefused("Give the product page's full address, starting with "
                           "https:// - nothing was opened and nobody was asked.")
    cleaned = url.strip()
    problem = CAPTURE.product_address_problem(cleaned)
    if problem:
        raise CheckRefused(problem)
    return ProductPagePlan(cleaned)


def card_text(plan_obj: ProductPagePlan) -> str:
    """The words on the ONE card: the offer, the address in full, and what the
    read does and does not do. No secrets, no page content - it is written
    before anything is opened."""
    return (
        CARD_QUESTION + "\n\n"
        "Page: " + plan_obj.url + "\n\n"
        "Jarvis opens that one page in its own visible browser window, using the "
        "signed-in profile you used once for Amazon. It reads the page and builds "
        "a reasons report. Nothing is typed, clicked, bought, ordered, added to a "
        "cart, saved or sent anywhere; no CAPTCHA is solved and no second page is "
        "opened. The page's words are outside text: never learned, never acted on.\n\n"
        "The report shows what Amazon chose to show, with counts, examples and "
        "every review set aside and why - never a trust score and never a "
        "fake/real verdict for one review.")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def run(plan_obj: ProductPagePlan, *, driver=None) -> dict:
    """Read the page in the owner's own browser and return the report.

    `driver` is the capture seam's injection point; omitted, it is the real
    browser-session driver (`jarvis_product_capture.real_driver`). Every
    refusal is a `CheckRefused` carrying the plain sentence the owner reads -
    this function never raises a bare exception for a page it could not read."""
    if not isinstance(plan_obj, ProductPagePlan):
        raise CheckRefused("There is no product page to read. Nothing was opened.",
                           kind="no_plan")
    html = _capture(plan_obj.url, driver)
    try:
        assembled = READ.assemble_report(html, source_url=plan_obj.url,
                                         captured_at=_now())
        report = assembled["report"]
        return _public_report(report, assembled)
    except Exception as exc:
        raise CheckRefused(
            "The page was read but the report could not be built "
            f"({type(exc).__name__}). Nothing was stored; try the check again.",
            kind="report_failed") from exc


def _capture(url: str, driver=None) -> str:
    use = driver if driver is not None else CAPTURE.real_driver()
    try:
        return CAPTURE.capture_page(url, driver=use)
    except CAPTURE.OwnerLoginRequired as exc:
        raise CheckRefused(str(exc) + " " + LOGIN_HINT, kind="owner_login_required") from exc
    except CAPTURE.ChallengeDetected as exc:
        raise CheckRefused(str(exc), kind="challenge") from exc
    except CAPTURE.CaptureUnavailable as exc:
        raise CheckRefused(str(exc), kind="unavailable") from exc


def _public_report(report: dict, assembled: dict) -> dict:
    """The report the route returns and the answer is rendered from.

    The engine's report, unchanged, plus the honest capture block and the
    read-half's listing/warnings. The raw review records are deliberately NOT
    included: nothing needs them, and this way a page's words never ride out
    of the process inside a debug field."""
    report = dict(report or {})
    report["ok"] = True
    report["source_url"] = assembled.get("source_url")
    report["listing"] = dict(assembled.get("listing") or {})
    report["warnings"] = list(assembled.get("warnings") or [])
    report["capture"] = {
        "browser": "the owner's own signed-in browser session, one page",
        "read_only": True,
        "stored": False,
        "network": False,
    }
    return report


# --------------------------------------------------------------------------
#   The chat answer, in plain words
# --------------------------------------------------------------------------

def _short(text, limit: int = SNIPPET_CHARS) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[:limit - 1].rstrip() + "…"


def _listing_lines(report: dict) -> list:
    listing = report.get("listing") or {}
    lines = []
    title = listing.get("title")
    lines.append("Product: " + (str(title) if title else "(the page did not show a title)"))
    rating = listing.get("star_rating")
    count = listing.get("rating_count")
    facts = []
    if rating is not None:
        facts.append(f"{rating} out of 5 stars")
    if isinstance(count, int):
        facts.append(f"{count:,} ratings on the page")
    if listing.get("asin"):
        facts.append("ASIN " + str(listing["asin"]))
    lines.append("Listing: " + (", ".join(facts) if facts else
                                "the page did not show a star rating or a count"))
    lines.append("Address: " + str(report.get("source_url") or ""))
    return lines


def _signal_lines(report: dict) -> list:
    signals = report.get("signals") or {}
    if isinstance(signals, dict):
        # The engine's own fixed order, by name: the report's `signals` is a
        # mapping, never a list, and the order is part of the report contract.
        ordered = [signals[name] for name in ENGINE.SIGNAL_NAMES if signals.get(name)]
    else:
        ordered = list(signals)
    lines = []
    for signal in ordered:
        name = signal.get("signal") or "signal"
        label = SIGNAL_WORDS.get(name, name.replace("_", " "))
        if not signal.get("available"):
            lines.append(f"- {label}: not checked - {_short(signal.get('why'), 220)}")
            continue
        counts = signal.get("counts") or {}
        shown = ", ".join(f"{key.replace('_', ' ')} {value}"
                          for key, value in counts.items())
        line = f"- {label}: {shown or 'no counts were possible'}"
        examples = []
        for example in (signal.get("examples") or [])[:2]:
            if isinstance(example, dict):
                bits = [str(value) for key, value in example.items()
                        if key in ("why", "reviewer", "reviewers", "snippet",
                                   "value", "date") and value]
                if bits:
                    examples.append(_short(" - ".join(bits), 120))
            elif example:
                examples.append(_short(example, 120))
        if examples:
            line += " Examples: " + " | ".join(examples)
        if signal.get("note"):
            line += " Note: " + _short(signal["note"], 200)
        lines.append(line)
    return lines


def _set_aside_lines(report: dict) -> list:
    block = report.get("set_aside") or {}
    items = block.get("reviews") or []
    if not items:
        return ["No review was set aside by the engine's rules."]
    lines = []
    for item in items:
        bits = [str(item.get("reviewer") or "a review")]
        if item.get("rating") is not None:
            bits.append(f"{item['rating']} stars")
        if item.get("date"):
            bits.append(str(item["date"]))
        head = " - ".join(bits)
        reasons = "; ".join(str(r) for r in (item.get("reasons") or []))
        snippet = item.get("snippet")
        line = f"- {head}: {_short(reasons, 240)}"
        if snippet:
            line += f'  ("{_short(snippet, 90)}")'
        lines.append(line)
    more = int(block.get("more") or 0)
    if more:
        lines.append(f"({more} more set-aside review(s) are counted above but not "
                     "listed here, because the report shows at most "
                     f"{len(items) + more} rows at once.)")
    return lines


def chat_answer(report: dict) -> str:
    """The report the owner reads, in plain words.

    The engine's SAMPLE caveat is the FIRST line, always; then the listing
    facts, what each rule counted, every set-aside review with its reasons,
    what could not be checked and the verdict in words. It ends with the
    no-score line, so the answer can never be read as a trust rating."""
    if not isinstance(report, dict) or not report.get("ok"):
        return "The product check did not finish, so there is no report."
    sample = report.get("sample") or {}
    words = report.get("plain_words") or {}
    lines = [str(sample.get("caveat") or ENGINE.SAMPLE_CAVEAT), ""]
    lines += _listing_lines(report)
    if sample:
        lines.append(
            f"Sample: {sample.get('readable', 0)} readable review(s) of "
            f"{sample.get('raw', 0)} read from the page; "
            f"{sample.get('with_text', 0)} have review text, "
            f"{sample.get('dated', 0)} have dates.")
        if isinstance(sample.get("listing_review_count"), int):
            lines.append(f"The page's own review count: "
                         f"{sample['listing_review_count']:,}.")
    warnings = report.get("warnings") or []
    if warnings:
        lines.append("")
        lines.append("How well the page could be read:")
        lines += [f"- {_short(w.get('words') or w.get('code'), 220)}"
                  for w in warnings]
    lines.append("")
    lines.append("What the rules counted (evidence, never proof):")
    lines += _signal_lines(report)
    lines.append("")
    lines.append("What buyers said, as the local model read it (quotes are checked "
                 "against the page; none may be invented):")
    for key, label in (("agreed", "Agree"), ("complained", "Complain"),
                       ("mixed", "Mixed")):
        for text in (words.get(key) or []):
            lines.append(f"- {text}" if str(text).startswith(("Not checked", "No ")) else
                         f"- {label}: {text}")
    lines.append("")
    lines.append("Reviews set aside, and why (none was removed from the counts):")
    lines += _set_aside_lines(report)
    lines.append("")
    lines.append("What could not be checked:")
    for item in (report.get("could_not_check") or []):
        lines.append(f"- {_short(item, 300)}")
    lines.append("")
    verdict = report.get("verdict") or {}
    lines.append("What all this adds up to: " + str(verdict.get("words") or ""))
    for item in verdict.get("what_would_change_it") or []:
        lines.append(f"- What would change it: {_short(item, 240)}")
    lines.append("")
    lines.append(NO_SCORE_LINE)
    return "\n".join(line for line in lines if line is not None)


# --------------------------------------------------------------------------
#   The route
# --------------------------------------------------------------------------

def _peer_local(handler) -> tuple:
    """(the address the request came from, the address it was made to) - the
    pair `jarvis_owner_check.from_this_pc` reads. The same two lines other
    route modules use."""
    peer = (getattr(handler, "client_address", None) or ("",))[0]
    try:
        local = handler.connection.getsockname()[0]
    except Exception:
        local = None
    return peer, local


def _from_this_pc(peer, local) -> bool:
    """True when the request came from this PC. Fails CLOSED: a peer that
    cannot be placed is not this PC."""
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local))
    except Exception:
        return False


def _person_said_yes(v) -> bool:
    """The gate's own reading (jarvis_quiz_cloud.py's helper): allowed, at the
    "ask" tier, with the outcome "approved". Anything else - including an
    auto-tier pass - is NOT a person saying yes."""
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


def _gate_card():
    """The real gate, built here because a drop-in module is handed only the
    core's origin/token/body callbacks. Returns (gate, tier_of)."""
    def gate(action: str, detail=None, text: str = ""):
        import jarvis_gate
        return jarvis_gate.check(action, detail=detail if isinstance(detail, dict) else {},
                                 prompt=str(text or ""))

    def tier_of(action: str) -> str:
        try:
            import jarvis_gate
            return str(jarvis_gate._tiers().get(action, "unknown"))
        except Exception:
            return "unknown"

    return gate, tier_of


def handle_post(body, *, here: bool = False, gate=None, tier_of=None,
                driver=None) -> tuple:
    """POST /api/product/check -> (HTTP status, body).

    `here` is whether the request came from this PC (the install wrapper
    computes it; the suites pass it). PC-only, off-by-default, one card, then
    the report. `gate`/`tier_of`/`driver` are the tests' injection points; the
    real ones are the gate and the browser-session driver."""
    if not here:
        return 403, {"ok": False, "error": PC_ONLY_WORDS, "pc_only": True}
    if not enabled():
        return 503, {"ok": False, "error": OFF_WORDS, "enabled": False}
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object with one product address"}
    try:
        plan_obj = plan(body.get("url"))
    except CheckRefused as exc:
        return 400, {"ok": False, "error": exc.why, "kind": exc.kind}
    if gate is None or tier_of is None:
        built_gate, built_tier = _gate_card()
        gate = gate or built_gate
        tier_of = tier_of or built_tier
    # A settings file that loosened the action raises no card and reads
    # nothing: checked BEFORE the gate, so the refusal is ours and not a
    # confusing "allowed without asking" from a card that was never shown.
    if tier_of(ACTION) != "ask":
        return 503, {"ok": False,
                     "error": "the product check's action is not at the \"ask\" tier "
                              "in this settings file, so no card could be raised and "
                              "nothing was opened"}
    text = card_text(plan_obj)
    detail = {"url": plan_obj.url, "text": text, "leaves_this_pc": False}
    try:
        verdict = gate(ACTION, detail, text)
    except Exception as exc:
        return 503, {"ok": False,
                     "error": f"the approval card could not be raised "
                              f"({type(exc).__name__}), so nothing was opened"}
    tier = str(getattr(verdict, "tier", "") or "")
    if tier != "ask":
        return 503, {"ok": False,
                     "error": "the product check's action is not at the \"ask\" tier "
                              "in this settings file, so no card could be raised and "
                              "nothing was opened"}
    if not _person_said_yes(verdict):
        why = ("You said no, so nothing was opened and nothing was read."
               if getattr(verdict, "outcome", "") == "denied" else
               "The card was not approved, so nothing was opened and nothing was "
               "read.")
        return 403, {"ok": False, "error": why,
                     "kind": str(getattr(verdict, "outcome", "") or "not_approved")}
    try:
        report = run(plan_obj, driver=driver)
    except CheckRefused as exc:
        return 502, {"ok": False, "error": exc.why, "kind": exc.kind}
    return 200, report


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap the core's Handler so POST /api/product/check is answered here.

    After the server's own origin and token checks - the same pair every other
    route uses - and PC-ONLY: a caller over the mesh gets 403 before the body
    is read. Installed by the drop-in folder `plugins/ready/product-check`, so
    this feature adds no patch to `jarvis_hud.py`. Every other request goes
    straight to the original handler."""
    post0 = handler_cls.do_POST
    if getattr(post0, "_jarvis_product_check", False):
        return "  product    Product check from one Amazon page (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_POST(self):
        from urllib.parse import urlsplit
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"ok": False, "error": type(exc).__name__})
        try:
            code, out = handle_post(body, here=_from_this_pc(*_peer_local(self)))
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_POST._jarvis_product_check = True
    handler_cls.do_POST = do_POST
    return "  product    Product check: one Amazon page, read-only (one card)"


def _reset_for_tests() -> None:
    """Nothing is cached in this module by design; kept so a suite can say so
    explicitly, the same shape the drop-in modules use."""
    return None
