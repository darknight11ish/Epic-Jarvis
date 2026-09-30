# Fill a form, show me, then submit - design (2026-09-30)

Owner's request: "fill out forms and book appointments for me ... send me a
screenshot of all the details it filled in for me to check and approve."
Owner's answers, 2026-09-30:

1. **A picture of the filled form is shown, exactly as the page shows it**
   (nothing blacked out - the owner needs to read the name, phone and email to
   check them). The picture goes only to the owner's own PC and phone.
2. **A separate card just for the final Submit click**, after the picture.
3. **Build it now**, before the second card is installed; no pull request to
   `main` until the owner asks.

## What already exists (do not rebuild it)

`backend/jarvis_browser_control.py` plans steps against one browser page, each
bound to one named element, and `run()` re-checks the page before every step.
One card lists the whole plan. It is offered only when the second card's
"Browser control" switch works (or, for reading only, the headless engine).
Nothing in the repo shows a picture on an approval card.

## The new flow

```
plan card (as today)  ->  Jarvis fills the fields  ->  STOPS before the step
marked "final"  ->  takes ONE picture of the page  ->  SECOND card
("Jarvis wants to submit this form"), with the picture + the values as text
->  Approve: the final step runs (re-checked like every step)  /  Deny: nothing
is sent
```

* **`final`.** A request may say `"final": true`. It marks the click that
  sends the form. `plan()` copies it onto the `Step`. Only `click` steps can be
  final; at most ONE per plan, and it must be the LAST step (else the request
  is reported unmatched, in words). A plan with no final step behaves exactly
  as before.
* **The stop.** `run()` gets a new hook, `review(info) -> dict`. Before the
  final step, `run()` re-reads the page, then calls it. `info` carries the
  site (host), the steps already done (values as text, `<secret>` names never
  their values), and the final step's label. The hook returns
  `{"approved": bool, "reason": str}`. **No hook, or a hook that raises =
  refused** (fail closed): the run stops before the final step and says so.
  A denial stops the run, nothing is sent, the tab is left open for the owner.
* **After a yes, before the click**, `run()` re-reads the page and confirms the
  page address, the target element (still one, still enabled) AND the page's
  field fingerprint are the same as when the picture was taken. A page that
  changed after the owner looked stops the run ("the page changed after you
  looked at it - nothing was sent").
* **The second card is a new gate action, `browser_form_submit`**, tier `ask`,
  risky (outbound, cannot be undone), never `auto`/`notify`, never
  "always allow", decided by tapping only. Its text: the site, then every
  value that was typed or chosen, as text, then "Jarvis will now click
  "<name>". It cannot be undone." A picture id rides in `detail.picture`.
  Outside-text and tainted-turn rules: a turn that read outside text refuses a
  `final` step outright, the way `send_email` does (the card would otherwise
  submit values the owner did not write).
* **The picture.** Visible browser only (Playwright `page.screenshot`, the
  whole page, JPEG). The headless engine has no pixels: its card says "No
  picture - this browser has no window" and still needs the second card.
  Kept in memory only (never written to disk, never logged, never given to any
  model, never put in an event), keyed by a random id, dropped when the card is
  decided, expires, or after 10 minutes, whichever is first. One review at a
  time. Size capped (longest side 1600 px, JPEG quality 70, at most 1.5 MiB;
  bigger is scaled down, not refused).
* **Route.** `GET /api/form-review/picture?id=<id>` -> `{"ok": true, "jpeg":
  "<base64>", "width", "height"}`; 404 `{"ok": false}` when gone. Token +
  origin like every route; a read, so it is not held on a stale link. Only
  answers for an id that belongs to a card still waiting.
* **Apps.** Both show the picture on the card in full-size view (tap to
  enlarge), fetching it when `detail.picture` is set. Not on the desktop's
  widget, not in a notification, not on the phone's home-screen widget (those
  stay title-only, as for every card). While App lock is on, the picture shows
  only inside the unlocked app. The phone blocks screenshots of Jarvis while
  it shows. If the picture cannot be fetched the card says so in words and
  Approve stays available only if the owner reads the text values (never
  silently approved without either).

## Rules check

* Rule 1: the typed values go to the site the owner names, nothing else; the
  picture goes to the owner's devices only. The local model plans; nothing is
  sent to a cloud model.
* Rule 4: the plan card AND the submit card are decided by the owner; the app
  never auto-approves; a stale event stream blocks both.
* The picture is not cleaned (owner's answer 1). It is the one place a screen
  picture is shown without `jarvis_screen.clean_picture`, because it never
  reaches a model. A test asserts it is never passed to any model call and is
  never written to disk.
* Secrets: a `<secret>` value is typed by the browser as a password box and the
  page shows it as dots; that is what the picture shows.
* Not built: no "always submit for me", no submit by voice, no bulk approve.

## Slices

1. Backend: `final` in `jarvis_browser_control.py`, `jarvis_form_review.py`
   (store + picture + route + the review hook), gate action, card words, risk,
   reach tables, patches, tests.
2. Desktop: card shows the picture (JS + the Rust read allowlist).
3. Phone: card shows the picture (Kotlin).
4. Docs: `JARVIS-API.md`, `ARCHITECTURE.md`, `CLAUDE.md` decision entry,
   `tools/check_parity.py` if a route is listed.
