# What the desktop half of "approval cards read short" still needs

Written 2026-10-10 for the conversation that owns `jarvis-desktop/` and
`src-tauri/`. **Nothing in those two folders was edited by the branch that
wrote this page** (`feat/cards-read-short`) - the owner's brief for that branch
says they are another conversation's surface. What that branch did build is the
half both apps share: the PC's own setting, the short summary on every card,
and the phone's card.

Everything below is what is left, in the smallest pieces it can be done in.
The PC's side is **already running on any machine that has had
`apply-patches.ps1` run over it**: `GET /api/card-prefs` answers, and every
pending row already carries `notice.summary` and `notice.full`. The desktop
needs no new route, no new patch and no new module - only to draw what it is
already being sent, and to offer the one switch.

## 1. The one thing to change: the card's own text

**File:** `jarvis-desktop/src/main.js`
**Function:** `refreshApproval(approval)` - the block at the bottom that paints
`dom.approvalPreview` (today, roughly lines 2238-2241; the email card's branch
just above it).

Today, folded or not, it draws the whole thing:

```js
dom.approvalPreview.innerHTML = renderMarkdown(approvalPreview(approval));
```

What it should draw instead, when the PC's setting is "start short":

* **one line** - `approval.notice.summary`, the PC's own short words
  ("Jarvis wants to send the email shown.");
* a control under it reading **`Explain more`** (and `Show less` to close);
* then what the control reveals, which is what is drawn today: the whole card.

Both texts are already on the row the desktop reads. `jarvis-link.js`'s
`normaliseApproval` builds `notice` from the wire row and currently keeps
`title` and `body` only - **add `summary` and `full` there**, next to them:

```js
notice: notice ? {
  title: String(notice.title || ""),
  summary: String(notice.summary || ""),   // NEW - the short line
  full: String(notice.full || ""),         // NEW - the whole card
  body: String(notice.body || ""),         // unchanged; equals `full`
  weight: String(notice.weight || "heavy"),
} : null,
```

`body` and `full` are **the same words** - the PC sets both, so a desktop that
never learns about the control shows exactly what it showed before. Nothing
else about the card changes: the title, the raised-quote block, the options,
the note field and both buttons stay where they are and keep behaving as they
do.

### The one rule to keep

`jarvis-desktop/src/main.js` also feeds `HeavyGate` (Feasibility I110, "slower
Approve on risky cards"), which holds a heavy card's Approve grey until
`#approval-preview` has been in view. `heaviness` currently reads the whole
preview. Under "start short" the whole text is folded away at first, so
**"in view" has to mean "opened at least once"** while folded, in both
directions - the phone does exactly this, in `ApprovalCard.kt`:

```kotlin
var heavyTextSeen by remember(item.id) { mutableStateOf(!heavy || !shown.control) }
```

...and the control's own click sets `heavyTextSeen = true` and never unsets it,
so closing the card again does not re-lock Approve. One-way, like the phone.

**Never** make the control the only way to read the card before deciding:
Deny stays available either way, exactly as now.

### Where the control sits, and what it is called

* Use the page's ordinary text-button/`<details>`-style control, not a new
  widget. `settings.html` already has a folded pattern
  (`<details class="raised-context" id="raised-context-wrap">` with
  `<summary>Show the surrounding text</summary>`); the card's own control
  belongs in `index.html` beside `#approval-preview`, right after it.
* The words are `Explain more` and `Show less`. They are the PC's own, sent by
  `GET /api/card-prefs` as `more_label` / `less_label`; use those if the read
  succeeded, and these two literals if it did not. They match
  `card-words.js`'s neighbours and the phone's `CardSummary.MORE_LABEL`.
* **Per card, not global.** One card's open/closed state must not move another
  card's. The desktop shows one card at a time in `#approval`, so this is
  simply: reset the control when a *different* id opens, exactly as
  `dom.approvalNoteInput.value = ""` is already guarded by `fresh` in
  `refreshApproval`. Do not reset it for the same card's own re-render - the
  queue subscription calls `refreshApproval()` again on every resync.

## 2. The one control to add: Settings

**File:** `jarvis-desktop/src/settings.html`, in the **"Everyday"** band.
**Place:** its own card, `<section class="card" id="approval-cards">`, right
after the Appearance card - what it changes is how much of a card is drawn,
which is what the neighbouring display preferences are about.

This is the piece that makes the desktop match the phone: the phone has the row
today (`jarvis-client`'s Settings, "Approval cards", `item(key =
"approval-cards")`), and the backend's registry has the section
(`jarvis_settings_registry.SECTIONS`) as **phone-only on purpose** until this
card exists. When this card lands:

1. `jarvis_settings_registry.py` - change that one `Section(...)`'s
   `app="phone"` to `app="both"` (one word; the long comment above it says so);
2. `backend/jarvis_menus.py` - the `settings.approval-cards` row's
   `(PHONE,)` becomes `(DESKTOP, PHONE)`;
3. regenerate `jarvis-desktop/src/menu-catalog.js` and
   `jarvis-desktop/tests/fixtures/menu-cases.json` from that module the way the
   other generated files are, and add the jump-list link in `settings.html`.

Nothing else in the registry changes: `jarvis_settings_registry.set_card_mode`
and `find_card_mode` already exist and already reach the PC's one function, so
the spoken sentence works the day the card does.

### The field it reads

**Route:** `GET /api/card-prefs` - answered by `jarvis_card_summary.py`
(`card-prefs.patch` wraps it round the HUD's Handler, after the server's own
origin and token checks). Same shape as the desktop's existing animal-options
read.

```json
{
  "available": true,
  "title": "Approval cards",
  "lead": "Cards that ask for your OK. This only changes how much of a card is shown at first - the same card, the same words underneath, the same buttons.",
  "mode": "start_short",
  "default": "start_short",
  "stored": false,
  "choices": [
    {"id": "start_short", "label": "Start short (default)", "detail": "...", "default": true},
    {"id": "always_full", "label": "Always show everything",  "detail": "...", "default": false}
  ],
  "more_label": "Explain more",
  "less_label": "Show less",
  "missing": "Your PC's Jarvis cannot keep this card setting yet - run apply-patches.ps1 on the PC."
}
```

**The field the desktop card draws from is `mode`.** Everything else on that
object is words to show as they arrive, so the desktop and the phone cannot word
the same two choices differently.

* `mode == "start_short"` (or the key missing, or the whole read failing):
  cards start folded, with the control.
* `mode == "always_full"`: every card is drawn open, exactly as today, and
  **no control is drawn at all** - there is nothing folded away.
* `stored` is `false` when nothing has been chosen yet, so the card can say
  "nothing chosen yet, so cards start short" rather than claiming a choice.
* A 404 is an older PC with no such route: draw cards as they always were, and
  the settings card says the `missing` line. Never a blank card.

**Changing it:** `POST /api/card-prefs` with `{"mode": "start_short"}` or
`{"mode": "always_full"}`. Cosmetic, so **both directions are immediate with no
approval card** and no stale-link hold - the same rule the animal options
follow. `{"changed": false}` means it was already set; `said` is the one
sentence to show, in the PC's own words.

Read it once when Settings opens, and read it again after a change rather than
assuming - that is what the phone does
(`ui/screens/ApprovalCardsPlate.kt`), and it means a refusal cannot leave the
screen claiming something the PC did not save.

## 3. What is NOT needed

* **No new patch, no new shipped module, no new Rust command.** The route
  exists and the two texts are already on every pending row.
* **No second copy of any words.** The summary is
  `backend/jarvis_card_words.py`'s (`SUMMARY` / `summary_for`), the whole card
  is the gate's own `full`, and the two choice labels are the PC's. A desktop
  string that repeats one of them is a string that will drift.
* **Nothing on the lock screen or in the widget.** The widget shows the title
  only, deliberately (`widget.js`), and stays that way; the toast, if there is
  one, is unchanged.
* **No change to what Approve or Deny do.** This is a display setting. It
  approves nothing, starts nothing and reaches nothing.

## 4. How to know it is right

The phone's own test, `jarvis-client`'s `CardSummaryTest.kt`, is the pattern:
eleven checks over the PC's real words, in `contract/card-words-cases.json`,
which `tools/gen_card_words_cases.py` writes from `jarvis_card_words.py` and
the real `notice_for`. That fixture already carries, for every action, the
`notice.summary` and `notice.full` a card is sent, plus a `card_prefs` block
with both choices and both labels - so a desktop test can hold itself to the
PC's own words the same way without a new fixture.

Worth pinning on the desktop side, at least:

1. folded, `#approval-preview` shows `notice.summary` and **not**
   `notice.full`;
2. after the control is clicked, it shows `notice.full`, word for word,
   including "Nothing else in it changes", the Windows Hello line where the row
   carries one, and "If you say no: nothing changes";
3. `mode: "always_full"` draws the whole card and **no** control;
4. opening one card does not open the next one the queue hands over;
5. an older PC (404, or a row with no `notice.summary`) draws what it always
   drew and is never blank - `card-words.js`'s `fallbackTitle` already covers
   the title half of that rule.

## 5. The one thing that is genuinely missing today

`jarvis_settings_registry`'s `set_card_mode` and `find_card_mode` exist on the
PC, and `jarvis_quick.py`'s grammar reaches them, so **"always show me the
whole approval card" already works by voice** - it changes `mode` at once, with
no card, and answers in one sentence. What does not exist yet is the desktop's
own switch, which is section 2 above. Until it lands, a desktop owner can only
change this by asking Jarvis or by using the phone.
