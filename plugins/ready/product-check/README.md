# product-check

**Check one Amazon product page for sponsored-review and incentive patterns.**
The owner's choice of 2026-11-04, in their own words: *"Wire the existing
product check into Jarvis"* - the engine, the read half and the capture seam
had shipped, and nothing imported them.

**Drop-in.** Copy this folder into the backend's `jarvis_plugins\` folder (or
run `scripts\add-plugin.ps1 -Name product-check`) and restart Jarvis. The module
it names ships with this repository (`backend/jarvis_product_check.py`), copied
into the backend by `scripts/apply-patches.ps1`; this folder adds no patch to
`jarvis_hud.py`. (One small patch, `product-check.patch`, adds the gate's own
`_TOOL_ACTIONS` line and `_RISK` row for the action.)

## The route

```
POST /api/product/check {"url": "https://www.amazon.com/dp/..."}   the report
```

The core's own origin + token checks, then **PC-only**: a caller over the mesh
gets `403` before the body is read, because the browser window and the signed-in
profile are on this PC. The request waits for the one approval card (the
desktop is the only caller and the card is on its screen) and answers with the
JSON report after the yes; a denial or a lapse is `403` in plain words and
nothing is read. `503` means the feature is switched off, in the module's own
sentence.

## The one card

The model tool `product_check` (and the route) raise ONE card naming the page in
full:

> Read this product page in your own browser session? Read-only; nothing is
> bought or added to a cart.

The action is `product_check`, tier `ask`, and it is in
`jarvis_owner_check.PC_ONLY_ACTIONS`: only this PC can approve it, with Windows
Hello. Both apps hold Approve on a stale link like every card (rule 4). A cart,
checkout, order, account, payment or sign-in address is refused by its shape
**before** the card, and a non-Amazon address or a product URL without an ASIN
is refused too - nobody is asked about something that cannot happen.

## What the read does

After the yes: ONE page, in the owner's own visible Chromium
(`jarvis_browser_control.read_page_html`, a documented public read-only seam),
using a persistent profile in the config folder so a sign-in the owner completed
once is still there after a restart. One navigation, one read of the loaded
document. No click, no typing, no form, no download, no second page, no CAPTCHA
solved and no retry against a challenge. If Amazon asks for a sign-in, the
window stays open for the owner and the answer says so; Jarvis never sees or
types the password.

The page's words are outside text: never learned, never acted on, and nothing
about the page is stored. The one thing kept is the browser's own sign-in
profile, so the one-time login works.

## The report

`jarvis_product_read.assemble_report()` -> the engine's reasons report:

- the **sample caveat first** ("This is what Amazon chose to show, not all of
  the reviews");
- the listing facts and how well the page could be read;
- the **eight signals** with counts, thresholds, examples and the reviews each
  one flagged;
- **every set-aside review with its reasons** (nothing is removed from the
  counts);
- the model's validated aspects (quotes must be real substrings) and what could
  not be checked;
- a verdict in words, with what would change it.

**Never a trust score. Never a per-review fake/real verdict.** The report has no
field for either, and the answer the owner reads is written by code
(`jarvis_product_check.chat_answer`), not by the model - so a model cannot add
one. The measured reason is in `docs/DESIGN-PRODUCT-RESEARCH.md`.

## The switch

`[product_check] enabled = false` in both shipped settings copies. Missing
reads as off. While it is off the model is not even offered the tool, and the
route answers "off". Turning it on is one hand edit of
`jarvis-framework.toml`; there is no in-app switch and no card for the switch.

## See also

- `backend/jarvis_product_check.py` - the wiring, card words and route
- `backend/jarvis_product_capture.py` - the read-only URL policy and the driver
- `backend/jarvis_product_read.py` - one page's HTML -> listing + reviews
- `backend/jarvis_product_research.py` - the eight signals and the report
- `docs/DESIGN-PRODUCT-RESEARCH.md` - the design contract and honest limits
- `docs/JARVIS-API.md` - the tool and the route
