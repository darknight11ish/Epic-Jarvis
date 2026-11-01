#!/usr/bin/env python3
"""Is "Everything Jarvis can do" complete, and is every line on it still true?

    python3 tools/check_feature_list.py

The owner asked, 2026-10-08: *"is there a button where I can find the entire
feature set of Jarvis on my desktop or android phone? It's important I can know
all the features, with an extend button on each feature where I can get
additional info."*  `features/features.json` is that list, and this is the
check that keeps it honest (docs/FEATURES-LIST-DESIGN.md).

BOTH DIRECTIONS, which is the whole point:

  1. NOBODY ADDED A FEATURE AND FORGOT THE LIST. Every route section the
     desktop's Brain may read (`jarvis-desktop/src-tauri/src/brain/routes.rs`,
     READ_ROUTES) and every menu id either app draws
     (`jarvis-desktop/src/menu-catalog.js`, the registry
     `menu-visibility-settings.js` renders; and
     `jarvis-client/.../ui/MenuPlaces.kt`, where each phone menu lives) is
     either named in some entry's `covers` list or named in `INTERNAL` below
     with a one-line reason. A new pane, command or menu that nobody listed
     FAILS here.

  2. NOBODY REMOVED A FEATURE AND LEFT THE LINE BEHIND. Every id in a `covers`
     list must still exist in the code, and every `INTERNAL` id must too. A
     page that promises a button which is gone is worse than no page.

  3. EVERY ENTRY IS READABLE. Each one has a non-empty `what`, `where` and
     `asks` - the three questions a beginner actually has - and a `group` from
     the fixed list, in the fixed order.

  4. THE THREE COPIES ARE ONE FILE. `features/features.json` is the source;
     `jarvis-desktop/src/features.json` and
     `jarvis-client/app/src/main/assets/features.json` are byte-identical
     copies of it, read at run time by each app with no bundler and no build
     step. The same rule `backend/test_base_matches_repo.py` already applies to
     the backend copies, so this is one precedent rather than a new idea.

  5. A ONE-SIDED CLAIM CARRIES ITS REASON. An entry whose `surface` is
     `"phone"` says the DESKTOP does not have that feature - the claim that
     misinformed the owner three times (see below) - so it must carry a
     `surface_reason`: one sentence saying why, quoted from
     `docs/ARCHITECTURE.md` section 8's one-sided table where the table has it.
     Since 2026-10-26 the same rule covers `"desktop"` entries: the chat answer
     tells the owner why the phone has none, so that sentence has to exist too.
     The value alone is not a reason ("phone only" is refused).

  6. EVERY LESSON IS CLAIMED BY A FEATURE ROW, OR EXEMPT WITH A REASON
     (reverse completeness). Rule 1 asks "is every menu/route listed?", rules 2
     and 6 ask "is every row's line still true?", and rule 6's forward half
     asks "is every feature taught?". None of them could see the remaining
     hole: a feature ROW vanishes (or is renamed) while its lesson stays in
     `jarvis_tutorials.py`. The old summary printed that as "information, not a
     failure", which is exactly how a silent loss reads. Now every catalogued
     lesson id must appear in at least one row's `covers`, unless
     `LESSON_UNCOVERED` names it with the reason it is deliberately not a
     feature - and that exemption itself fails when it goes stale (a lesson
     deleted, or one that a row now claims). A tutorial the list no longer
     points at is a feature the page has stopped telling the owner about.

  7. A TAUGHT ENTRY NAMES WORDS ITS OWN LESSON REALLY USES. Rule 6 asks whether
     every feature HAS a lesson and every lesson a feature; it could not see
     the lie left over: a row that names a lesson which never mentions the
     feature. The row "Save a draft to your Drafts folder" can name
     `home-calendar-email` and pass every rule above while that lesson's steps
     never say "draft" - so "it is taught" was a claim nothing tested. Every
     taught row now carries either `must_mention` or a `TEACHING_GAP` line:
     `must_mention` is 1-3 lowercase words or short phrases that must occur,
     whole-word and case-insensitively, in the step `title`+`body` text of the
     lessons that row names. A missing word FAILS, naming the feature, the
     lesson(s) and the word. So does a taught row with neither of the two (the
     gate cannot be skipped) and a `must_mention` on a row no lesson teaches
     (a stale field).

WHAT RULE 7 CANNOT JUDGE, AND WHAT IT DOES ABOUT THAT

It can see that a word OCCURS. It cannot see that the word is the right word:
`["card"]` appears in 28 of the 36 lessons (measured 2026-10-25), so on its own
it would prove nothing. Two things keep that honest rather than pretending a
checker can judge meaning:

  * the list is read by a person in a diff, which is why it is 1-3 short plain
    words and not a score, and why `surface_reason`'s precedent applies -
    "only its SHAPE can be checked; the sentence has to exist for a person to
    read" is the same limit one rule over; and
  * `TEACHING_GAP` below is where a row is recorded when its lesson genuinely
    does not teach it, so no row can pass by carrying a word that happens to be
    nearby. That list is the honest answer to "what does this gate still not
    know", and it empties itself: a row that gains `must_mention` fails until
    its gap line is deleted.

The 14 rows in `TEACHING_GAP` were measured on 2026-10-25 by searching each
row's lesson text for the feature's own subject - "draft", "archive",
"captcha", "github", "version", "camera", "rush", "app lock", "update" - and
finding none of them. They are a work list for the teaching side, not a
silence: each line names the lesson and what it leaves out.

WHAT `surface` IS NOT CHECKED AGAINST, AND WHY NOT (2026-10-16)

`surface` is only required to be one of `("desktop", "phone", "both")` - never
to be TRUE. That gap let three entries say `"phone"` for weeks while the
desktop had the feature: PC help (`jarvis-desktop/src/pc-help.js`, Settings ->
Hardware and models), "What did I believe on this date?" (`brain.js:2501`,
`:3018`) and the rush-latch banner (`brain.js:1274-1290`). All three were
corrected by hand; nothing here could have caught them. Two cross-checks were
MEASURED before one was written, and both fail:

  * `covers` ids that are a route in `tools/check_parity.py`: **0 of 131
    entries.** The ids are menu ids (`brain.model.pc-help`) or the Brain's read
    section names (`memory`, `models`, `skills`), so a direct match finds
    nothing at all.
  * Linked indirectly - a `covers` id that is a READ_ROUTES section name, then
    its route, then the parity status: **10 of 131 entries (7.6%)**. On those it
    is wrong in both directions. It flags `memory-tab` (a false positive:
    `memory` there is the section name of the Memory TAB, not a claim about
    `/api/memory/status`), and it cannot see either drift that motivated the
    idea: `brain.model.pc-help` and `brain.trust.rush-latch` appear **0 times**
    in READ_ROUTES, because PC help reaches `/api/pc/help` through
    `hardware.rs` and the banner is drawn by `brain.js`. A check that stays
    green through the case it exists for, and lies on the one case it reaches,
    buys false confidence - which is why there is no such check here.

What is true, for anyone weighing the alternative: 113 of the 140 entries are
`"both"` and 27 are not (19 `"desktop"`, 8 `"phone"`, measured 2026-10-26).
Each of those 27 is a claim that ONE APP LACKS A FEATURE - exactly the claim
that misinformed the owner here.

WHY THE RULE NOW COVERS `desktop` AS WELL AS `phone` (2026-10-26)

Rule 5 was one-directional for a year, and this is why that changed:

  * `"phone"` has EVIDENCE OF HARM. Three entries said `"phone"` while the
    desktop had the feature - PC help, "What did I believe on this date?" and
    the rush-latch banner - and each told the owner his PC was missing
    something it had. A `surface_reason` makes that negative claim a sentence
    somebody had to write and a reader can weigh.
  * `"desktop"` claims the phone lacks the feature, and from 2026-10-26 that
    claim is SPOKEN, not just drawn on a page: the chat answer for a one-sided
    row says "It is on the PC only: <reason>". Told without a reason, that is
    the same thin answer the owner's field test complained about, so every
    desktop-only row now carries one (19 were written on 2026-10-26 from the
    row's own `limit`/`where` or from the app structure, and a reader can
    disagree with any of them in a diff).
  * The old objection - no honest sentence without a fresh survey of the phone,
    one row at a time - is still true in the sense that a checker cannot judge
    the sentence. That is why only its SHAPE is checked, exactly as for
    `"phone"`: the sentence has to exist for a person to read.
  * Three `"phone"` entries were once exempt through `REASON_PENDING` for the
    same honesty: their claim was FALSE on that tree (the desktop had all
    three), so no sentence saying the desktop lacked them would have been true.
    That list is empty and empties itself - an id in it that stops being a
    one-sided entry FAILS, with the line to delete named.

WHY `INTERNAL` AND NOT "one entry per route": 249 backend routes are not 249
features to a person - most are plumbing behind a button that IS listed. The
allow-list below is what keeps "curated for reading" from meaning
"incomplete": every id in it says, in one line, what it is and why the owner
never presses it directly. It is deliberately as small as the truth allows.

Run through `backend/run_suites.py test_feature_list.py`, which is how CI runs
it with the other Python suites.
"""
import ast
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SOURCE = ROOT / "features" / "features.json"
COPIES = (
    ROOT / "jarvis-desktop" / "src" / "features.json",
    ROOT / "jarvis-client" / "app" / "src" / "main" / "assets" / "features.json",
)
ROUTES_RS = ROOT / "jarvis-desktop" / "src-tauri" / "src" / "brain" / "routes.rs"
MENU_CATALOG = ROOT / "jarvis-desktop" / "src" / "menu-catalog.js"
MENU_PLACES = (
    ROOT / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
    / "client" / "ui" / "MenuPlaces.kt"
)
TUTORIALS_PY = ROOT / "backend" / "jarvis_tutorials.py"
SETTINGS_REGISTRY = ROOT / "backend" / "jarvis_settings_registry.py"
JARVIS_API = ROOT / "docs" / "JARVIS-API.md"
FRAMEWORK_TOML = ROOT / "backend" / "rebuilt" / "jarvis-framework.toml"

#: Rule 8: what a row may point at as evidence. A FILE that exists, a SYMBOL
#: that is really defined inside the file named before it, or a ROUTE the API
#: doc really lists. Never a line number: this repository is worked in parallel
#: worktrees and the lines move under every edit, so a line is not evidence of
#: anything - only the file, the symbol and the route are.
_PATH_ANCHOR = re.compile(
    r"(?<![\w/.-])((?:backend|jarvis-desktop|jarvis-client|jarvis-backend|docs|"
    r"tools|features|contract|scripts|plugins)/[\w./-]+\.(?:py|mjs|js|kt|rs|md|"
    r"json|toml|html|css|ps1))", re.I)
_ROUTE_ANCHOR = re.compile(r"/api/[A-Za-z0-9_./{}:<>-]+")
_LINE_ANCHOR = re.compile(
    r"\b[\w./-]+\.(?:py|mjs|js|kt|rs|md|json|toml|html|css|ps1):\d+")
_SYMBOL_ANCHOR = re.compile(r"`([a-z_][a-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)`")

#: Rule 9: a row that says its feature raises an approval card must name the
#: GATE ACTION that card is written under (`gate` in features.json), and that
#: action must resolve to tier `ask` in the shipped settings. A card in the
#: prose and no action behind it is a claim nothing can check; an action whose
#: tier is `auto`/`never` means the sentence is false.
_CARD_CLAIM = re.compile(
    r"(?<![A-Za-z])(?:one approval card|one card|"
    r"raises (?:(?:a|an|one)\s+)?(?:approval\s+)?card|asks you first|"
    r"(?<!what )asks first)", re.I)
#: Phrases that make a nearby "card"/"asks" sentence a NEGATIVE claim ("no card
#: to look", "raises no card", "asks nothing") - those need no gate action.
_CARD_NEGATIVE = re.compile(
    r"\b(?:no|never|not|nothing|without|none)\b", re.I)

#: Rule 9's recorded gaps: rows that claim a card whose gate action has not been
#: mapped to a real action yet. It is a measured work list, not a pass, and it
#: empties itself: a row that gains `gate` fails until its line is deleted, a
#: row whose prose stops claiming a card fails the same way, and an id that is
#: no longer a row fails too.
CARD_GATE_GAP = {
    "memory-waiting": "the per-fact card is raised by the memory store's own pending queue, "
    "not by an action in [autonomy.tiers]; the exact gate name is not recorded yet",
    "memory-people": "Forget on a fact is memory-store code, and its gate action is not "
    "recorded in the shipped tiers",
    "between-us": "Forget on a fact is memory-store code, and its gate action is not "
    "recorded in the shipped tiers",
    "sensitive-facts": "the per-fact sensitive card is the memory store's pending queue, "
    "not an action in [autonomy.tiers]",
    "quiz": "the YouTube quiz link's card is raised by the quiz module; its gate action "
    "is not recorded in the shipped tiers",
    "approvals": "the approvals row is the card mechanism itself; its prose describes "
    "the general shape, not one feature's gate action",
}

#: The groups, in the order both apps draw them (docs/FEATURES-LIST-DESIGN.md).
GROUPS = [
    "Talking",
    "Memory",
    "Screen and pictures",
    "Notes and files",
    "Money and health",
    "Home",
    "Phone",
    "The PC itself",
    "Safety",
]

SURFACES = ("desktop", "phone", "both")

#: Rule 5: how a `surface_reason` is judged. Only its SHAPE can be checked - no
#: checker can tell whether a sentence is true, which is exactly why the
#: sentence has to exist for a person to read.
REASON_MIN_WORDS = 6

#: Values that are the `surface` said again rather than a reason for it.
_VALUE_ECHO = {"phone", "phone only", "phone-only", "desktop", "desktop only",
               "desktop-only", "both", "only on the phone", "only on the desktop"}


def reason_is_a_sentence(text: str) -> bool:
    """Is this a sentence somebody wrote, rather than the value restated?"""
    words = str(text or "").split()
    return (len(words) >= REASON_MIN_WORDS
            and " ".join(words).lower().rstrip(".") not in _VALUE_ECHO)


#: Rule 5's exemptions, each with the one line saying why it is here rather
#: than carrying a sentence. Every one is a `"phone"` entry whose claim is
#: FALSE on the tree it was written against - the desktop has the feature - so
#: a `surface_reason` for it would be a lie. `pending_problems()` FAILS the
#: moment one stops being a `"phone"` entry, so this list empties itself
#: instead of rotting.
#:
#: **IT IS EMPTY, AND THAT IS THE MECHANISM WORKING (2026-10-16).** It held
#: three when this rule was written - `pc-help`, `memory-as-of` and
#: `rush-latch` - and PR #495 corrected all three to `"both"` the same day.
#: The checker then failed with, for each one, `delete its line (the entry has
#: been corrected)`, naming the desktop file that has the feature. Deleting
#: them was the whole resolution, and it took one command. **The dict stays,
#: empty, because the next false claim needs exactly this shape**: a place to
#: record "this is deliberately unhandled, and here is what un-handles it"
#: that cannot quietly become permanent.
REASON_PENDING = {}

#: Ids that are real but are never a row of their own, each with the one-line
#: reason the owner never presses it. Keyed by the id exactly as the code
#: spells it. An entry here that no longer exists in the code fails too.
INTERNAL = {
    "attention": "the interruption-budget read; the card 'attention-budget' names it",
    "compute": "the graphics-card plan is drawn inside the Models/Compute card the 'Compute' entry names",
    "config": "the settings file's own read; the card that shows and changes it is 'settings-file'",
    "digest": "the daily brief is drawn in the Jarvis bar's own waiting line, not a screen of its own; 'attention-budget' names it",
    "gate_history": "read-only past approvals; the card is 'past-approvals'",
    "initiative": "what Jarvis noticed by itself, drawn in the Now pane 'now' names",
    "jobs": "the background-job list is one pane of the Work tab; the 'jobs' entry names it",
    "ledger": "the audit chain, read and drawn inside the Trust tab 'trust' names",
    "memory": "the memory counts read behind the Learning card; 'memory-learning' names it",
    "memory_entities": "the people-and-things read behind the list; 'memory-people' names it",
    "memory_facts": "the whole fact store read behind the list; 'memory-known' names it",
    "memory_pending": "the cards waiting for a yes; 'memory-waiting' names it",
    "content_risk": "the scanner's own read; its results are drawn in the Trust tab 'trust' names",
    "status": "the connection and model status read; the 'connection' entry names the line it feeds",
    "undo": "the undo shelf's own read; the 'undo' entry names the pane",
    "watch": "the GitHub watchlist's own read; 'github-watchlist' names the feature",
    "watch_report": "the GitHub watchlist's read-only peek; 'github-watchlist' names the feature",
    # 2026-10-23, #749: the phone's "All features and abilities" row is the
    # directory OF this list - every ability it indexes already has its own
    # feature row above, so a row for the index itself would list the list. It
    # is a Settings menu id (never hideable: it is the phone's map of where each
    # control lives), not an ability of its own.
    "settings.all-features": "the phone directory row itself: it indexes the 140 features, and every ability it lists has its own row",
}

#: The lessons a feature may be taught by, read from the real catalogue. A
#: `covers` list now holds two kinds of id - the menus and routes a feature is
#: reachable through (checked against the registries above) and the tutorials
#: that TEACH it (checked against this). Nothing else distinguishes them, which
#: is the design's own choice (docs/EDUCATION-TAB-DESIGN.md section 8 step 2):
#: "It gains the lessons that teach it, in the same list."
#:
#: The list is read from `backend/jarvis_tutorials.py` itself, so a lesson
#: renamed there cannot be left behind in a `covers` list, and a feature cannot
#: claim a lesson that does not exist.
LESSON_EXEMPT = {
    "typing": "the box you type in; the app's own prompt field is the lesson",
    # The Jarvis calendar's store and routes land before either screen, so
    # there is nothing to teach yet: the Calendar screens (HUD card, phone
    # plate, widget) are the next slice, and their lesson lands with them.
    "jarvis-calendar": "the store and routes come first; the screens and their lesson are the next slice",
    "interrupt": "the talk button stops the answer; there is nothing to learn",
    "temporary-chat": "one switch in the chat head; its own label is the lesson",
    "private-chat": "one chip in the chat head, and its own strip line says what it does: no memory, nothing kept, no tools, no changes",
    "history-search": "a search box over the list it is above",
    "file-history": "the drawer explains itself: it lists the copies Jarvis "
                    "took and asks before a restore",
    "people-dossier": "clicking a name in People and things opens it; the card "
                      "names the person and says it is read-only",
    "media-read": "it is one sentence in a chat - name a file and read the "
                  "answer; the module docstring and the tool description are the lesson",
    "quiz": "the deck screen explains itself; it is revision, not a Jarvis feature",
    "decks": "the deck screen explains itself; a deck is yours, not Jarvis's",
    "pc-help": "five answers on one card; the card is the lesson",
    "web-search": "a switch in Settings and a sentence saying search leaves the PC",
    "browser-engine": "a switch in Settings; the card says what it does",
    "support": "one button that starts a support session, and a log to send",
    "settings-by-asking": "saying a setting in words; the reply names the setting",
    "settings-entry": "the way into Settings; the tray row and Ctrl+K say where",
    "start-the-model-lane": "one button on the standing line, which names the lane that is down and says what pressing it does",
    "restart-the-model-lane": "automatic and nothing to press; the line says what Jarvis did, in its own words",
    "data-sandbox": "one switch in Settings whose card says what it does; the PC's own line says what the last card did",
    "focus-presets": "the preset card explains itself in the PC's own words; its one action stays disabled until the lane/apply patch, so a lesson would teach a button that does nothing yet",
    "cloud-escalation": "the Cloud row's own apply card and the one standing-switch card say what they change, where the key lives and what still must not leave; the fixed chat answers now do the teaching, so a separate lesson would repeat the cards",
    "write-like-me": "the training screen it would teach is the next UI slice; this row is the catalogue half, so a lesson now would teach a screen that is not built yet",
    "setup-questionnaire": "the card explains itself: fourteen questions in the owner's own words, a read-only plan naming each effect, and one Apply that asks twice; a lesson would repeat the card",
    "reminder-actions": "the Reminders lesson was written before a reminder could carry an action and does not teach it; this is a work item for the teaching side, and until then the HUD's own Then row says, in one sentence under the field, what will happen when the reminder goes off",
    "anti-slop": "one switch, one mode and one line saying what OFF costs, on the How Jarvis talks card that already has its own lesson; a lesson would repeat the card's own words, and the card is the lesson",
}

#: Rule 6's exemptions: lessons that are deliberately NOT a feature row, each
#: with the one line saying why nobody reaches it from this list. The reverse of
#: `LESSON_EXEMPT` above (which is keyed by FEATURE id and says "this feature
#: needs no lesson"): this one is keyed by LESSON id and says "this lesson is
#: not any feature's page". A stale line is itself an error - a lesson that no
#: longer exists, a lesson whose reason is empty, or a lesson a feature row now
#: claims all FAIL, so the list empties itself instead of becoming a hiding
#: place (the same shape REASON_PENDING already has).
#:
#: **IT IS EMPTY, AND THAT IS THE MECHANISM WORKING (2026-10-18).** The audit
#: that added the reverse check found the last two unclaimed lessons -
#: `phone-talking` (the phone's hold-to-talk button, which the "talk-button" row
#: describes) and `phone-stays-on-pc` (the "phone-limits" row's own subject) -
#: and named them from those rows instead of exempting them, because a feature
#: row genuinely teaches each. The dict stays, empty: the next lesson that is a
#: cross-cutting rule rather than a feature needs exactly this place, and its
#: entry must carry the sentence saying which rule.
LESSON_UNCOVERED = {}

#: Rule 7's honest limit, written down rather than hidden: the rows whose lesson
#: does NOT teach the feature, so there is no word to name. Each entry is
#: `feature id -> (lesson id the row names, what that lesson leaves out)`.
#:
#: **This list is a work list for the teaching side, not an exemption for this
#: list.** Every entry was measured on 2026-10-25 by searching the row's own
#: lesson text for the feature's subject words and finding none: `home-calendar-email`
#: has no "draft", no "archive", no "trash" and no "tidy"; `when-something-is-wrong`
#: has no "rush", no "latch" and no "banner"; `limits-and-notes` has no "update",
#: "version" or "release". The alternative - giving those rows a word that does
#: occur nearby, like "email" or "card" - would have made the gate green while
#: proving exactly nothing, which is the failure this rule was added to stop.
#:
#: It empties itself the way every other list here does. A gap line FAILS when
#: the row gains `must_mention` ("delete the line - the row has words now"),
#: when the row stops naming the lesson, when the feature row is gone, and when
#: the reason is empty. Closing a gap is therefore two edits in one commit: the
#: lesson step, then the deletion of its line here.
TEACHING_GAP = {
    "talk-to-type": (
        "how-it-talks",
        "teaches personality, voice, interrupting, the voice print and the "
        "prompt coach - nothing about holding a key to type what you say"),
    "about": (
        "intro",
        "teaches what Jarvis is and the five rules it will not break; the About "
        "page's own subject - the version, the licences and the credits - is in "
        "no step"),
    "photo-reminder": (
        "screens-and-pictures",
        "teaches looking, watching, what is kept and asking for a picture; "
        "nothing reads dates off a photo and offers a reminder"),
    "live-camera": (
        "phone-live",
        "teaches the Live conversation, the tile, the headset and the controls; "
        "the word camera appears in no step (and the row itself says the "
        "feature is not built yet)"),
    "github-watchlist": (
        "work-and-attention",
        "neither lesson it names contains 'github', 'watch' or 'topic' - the "
        "feature is named by its registry ids only"),
    "email-drafts": (
        "home-calendar-email",
        "teaches reading email and sending it, one card per email; saving a "
        "DRAFT to the owner's Drafts folder is in no step"),
    "inbox-tidy": (
        "home-calendar-email",
        "teaches reading and sending; no step mentions archiving, starring, "
        "marking read, Trash or tidying"),
    "news-and-page-watches": (
        "work-and-attention",
        "the only 'news' in either lesson is the morning briefing's own line; "
        "feeds and watched pages are in no step"),
    "updates": (
        "limits-and-notes",
        "teaches limits, starting Jarvis, logs and crash notes; no step "
        "mentions an update, a version or a release page"),
    "tool-updates": (
        "model-page",
        "the only 'tool' is 'a tool that is not installed' under what the "
        "backend supports; checking a package is out of date is in no step"),
    "app-lock": (
        "phone-limits",
        "neither lesson it names mentions App lock, a fingerprint, a PIN or "
        "hidden memory lists - the nearest sentence lives in the sibling "
        "lesson phone-stays-on-pc, which this row does not name"),
    "captcha-handoff": (
        "phone-approvals",
        "teaches deciding a card on the phone; no step mentions a captcha, a "
        "solve-it-here hand-off or a stuck browser window"),
    "stale-link": (
        "when-something-is-wrong",
        "teaches the error ring, 'not connected', the slow model, stopping and "
        "crisis help; the stale event stream and the block on acting are in no "
        "step"),
    "rush-latch": (
        "when-something-is-wrong",
        "no step mentions the rush-latch banner, outside text trying to hurry "
        "an approval, or the fact that no control clears it"),
    # Added with the feature (2026-10-30, docs/PIP-DESIGN.md). It covers the
    # phone-extras lesson because that is where a phone-only extra belongs, and
    # it is a recorded gap for the reason the gate exists: the lesson teaches
    # the floating face, the quick tiles and the screen rate, and none of its
    # steps mentions Android's own picture-in-picture window. A work item for
    # the teaching side, not an exemption.
    "phone-pip": (
        "phone-extras",
        "teaches the phone's floating face, quick tiles and screen rate; "
        "nothing about Android's own picture-in-picture window, what it shows "
        "or that it never approves anything"),
}

#: Rule 7: how a `must_mention` list is judged. Only its SHAPE, plus whether
#: the words occur - no checker can tell whether a word is a good choice, which
#: is why the list is short enough to read in a diff and why TEACHING_GAP
#: exists for the rows where no honest word exists.
KEYWORDS_MIN = 1
KEYWORDS_MAX = 3
_KEYWORD_SHAPE = re.compile(r"^[a-z0-9][a-z0-9' -]*$")


def catalogue_lessons() -> tuple:
    """Every lesson the catalogue really defines, as data, in file order.

    Read as a Python LITERAL rather than by importing the module: this checker
    runs in CI beside every other one and must not need the backend's runtime
    (the module imports `jarvis_framework` when it is there). `ast.literal_eval`
    refuses anything that is not plain data, so a catalogue that stops being a
    tuple of dicts fails loudly here instead of being guessed at - the same
    "refuse to guess" the parses below already follow.
    """
    text = TUTORIALS_PY.read_text(encoding="utf-8")
    start = text.index("CATALOGUE = (")
    opened = text.index("(", start)
    closed = text.index("\n)\n", start) + 2
    got = ast.literal_eval(text[opened:closed])
    if not isinstance(got, tuple) or len(got) < 20:
        raise AssertionError(
            f"read {len(got) if isinstance(got, tuple) else type(got).__name__} "
            "lessons from jarvis_tutorials.py - the parse broke")
    return got


def lesson_ids() -> list:
    """Every tutorial id the catalogue really defines, in file order."""
    return [lesson["id"] for lesson in catalogue_lessons()]


def settings_section_ids() -> list:
    """Every Settings-registry section id, in file order (ruling (c), 2026-10-31).

    THE FOURTH KIND OF COVER ID, and the difference matters. A `covers` id may
    name a screen/menu/route (checked against the three registries), a LESSON,
    or now a real `jarvis_settings_registry.SECTIONS` section id. Gemini's
    ruling (c) of 2026-10-31 requires the "Protected from Jarvis" feature row to
    carry BOTH its section id (`protection`) and its Settings menu id
    (`settings.protection`): the section is the thing the row IS, the menu id is
    where it opens.

    These ids are real (read from the registry's own `SECTIONS`, with `ast`, the
    same refuse-to-guess parse the lesson catalogue uses), so a cover naming one
    is not a phantom. They are NOT added to `known_ids()`: that dict is the set
    of route sections and menu ids that every one of them must be COVERED by a
    row (rule 1), and a settings section is not a screen that needs its own line
    - most sections are already named by the feature rows that own them, and
    requiring all 56 would be a different rule than the one this checker's
    docstring states. A cover id that no longer exists fails: this function
    re-reads the registry every run.
    """
    text = SETTINGS_REGISTRY.read_text(encoding="utf-8")
    tree = ast.parse(text)
    found = None
    for node in tree.body:
        if (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
                and node.target.id == "SECTIONS" and isinstance(node.value, ast.Tuple)):
            found = node.value
            break
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "SECTIONS"
                and isinstance(node.value, ast.Tuple)):
            found = node.value
            break
    if found is None:
        raise AssertionError(
            "could not read SECTIONS from jarvis_settings_registry.py - the parse broke")
    ids = []
    for element in found.elts:
        if (isinstance(element, ast.Call) and isinstance(element.func, ast.Name)
                and element.func.id == "Section" and element.args
                and isinstance(element.args[0], ast.Constant)
                and isinstance(element.args[0].value, str)):
            ids.append(element.args[0].value)
    if len(ids) < 20:
        raise AssertionError(
            f"read only {len(ids)} settings section ids from jarvis_settings_registry.py "
            "- the parse broke")
    return ids


def lesson_text(lesson: dict) -> str:
    """The words a lesson teaches with: every step's `title` and `body`.

    `where` is deliberately NOT read. It names a place in an app ("Settings →
    Voice"), and a row could then match a keyword against a place-name while the
    lesson itself taught nothing - the same false comfort rule 7 exists to
    remove. A row's `must_mention` has to be earned by a sentence, not by a
    breadcrumb.
    """
    return "\n".join(f"{step['title']}\n{step['body']}" for step in lesson["steps"])


def source_bytes() -> bytes:
    return SOURCE.read_bytes()


def entries() -> list:
    """The list, as checked in."""
    got = json.loads(SOURCE.read_text(encoding="utf-8"))
    if not isinstance(got, list):
        raise AssertionError("features/features.json must be an array of entries")
    return got


def route_sections() -> list:
    """Every route section the Brain window may read, by name, in file order.

    READ_ROUTES is the allow-list itself (`("status", "/api/status")`); this
    reads the names only, and refuses to guess if the shape changed - a parse
    that quietly found nothing would make every "is it covered" answer yes.
    """
    text = ROUTES_RS.read_text(encoding="utf-8")
    start = text.index("const READ_ROUTES")
    block = text[start:text.index("];", start)]
    names = []
    for line in block.splitlines():
        # `    ("status", "/api/status"),` and the one wrapped entry, which puts
        # only the name on its own line. Comments start with `//`, never `"`.
        m = re.match(r'\s*\(?\s*"([a-z_]+)",', line)
        if m:
            names.append(m.group(1))
    if len(names) < 10:
        raise AssertionError(f"read only {len(names)} route sections from READ_ROUTES - the parse broke")
    return names


def desktop_menu_ids() -> list:
    """Every menu id the desktop's registry holds, in file order.

    `menu-visibility-settings.js` - the file the design note names - holds no
    ids at all: it renders the registry `menu-catalog.js` exports, which is
    generated from `backend/jarvis_menus.py` by `tools/gen_menu_cases.py`. The
    registry is read here for that reason, and `menu-catalog.js` is the same
    list the phone's MenuCatalog.kt is held to.
    """
    text = MENU_CATALOG.read_text(encoding="utf-8")
    start = text.index("export const MENUS")
    block = text[start:text.index("export const NEVER_HIDE", start)]
    ids = re.findall(r'\n    "id": "([^"]+)"', block)
    if len(ids) < 50:
        raise AssertionError(f"read only {len(ids)} menu ids from menu-catalog.js - the parse broke")
    return ids


def phone_menu_ids() -> list:
    """Every menu id the phone's own places name (`ui/MenuPlaces.kt`).

    SETTINGS and BRAIN map an `item(key = ...)` to a menu id, so the id is on
    the right of `to`; INSIDE is keyed BY the id, so it is on the left. Both
    halves are read, in that order.

    SETTINGS_ALIAS is deliberately NOT read: it maps a *settings-registry*
    section id ("appearance-card") to the item key that draws it, and neither
    side of it is a menu id. MenuVisibilityTest holds the places - SETTINGS,
    BRAIN and INSIDE - to the same registry this does.
    """
    text = MENU_PLACES.read_text(encoding="utf-8")
    ids = []
    for name, side in (("SETTINGS", "right"), ("BRAIN", "right"),
                       ("INSIDE", "left")):
        at = text.index(f"val {name}: Map<String, String> = mapOf(")
        block = text[at:text.index("\n    )", at)]
        for m in re.finditer(r'"([^"]+)"\s+to\s+"([^"]*)"', block):
            ids.append(m.group(2) if side == "right" else m.group(1))
    if len(ids) < 50:
        raise AssertionError(f"read only {len(ids)} menu ids from MenuPlaces.kt - the parse broke")
    return ids


def known_ids() -> dict:
    """id -> where it came from, for everything that must be covered."""
    out = {}
    for name in route_sections():
        out[name] = "jarvis-desktop/src-tauri/src/brain/routes.rs (READ_ROUTES)"
    for name in desktop_menu_ids():
        out.setdefault(name, "jarvis-desktop/src/menu-catalog.js (MENUS)")
    for name in phone_menu_ids():
        out.setdefault(name, "jarvis-client .../ui/MenuPlaces.kt")
    return out


def field_problems(got: list) -> list:
    """Rule 3: every entry is a readable row with an id, a group and a surface."""
    bad = []
    seen = set()
    for i, e in enumerate(got):
        if not isinstance(e, dict):
            bad.append(f"entry {i} is not an object")
            continue
        where = e.get("id") or f"entry {i}"
        for key in ("id", "group", "title", "what", "where", "asks", "limit", "surface", "covers"):
            if key not in e:
                bad.append(f"{where}: no `{key}`")
        if where in seen:
            bad.append(f"{where}: listed twice")
        seen.add(where)
        for key in ("what", "where", "asks"):
            if not str(e.get(key) or "").strip():
                bad.append(f"{where}: `{key}` is empty")
        if e.get("group") not in GROUPS:
            bad.append(f"{where}: group `{e.get('group')}` is not one of the nine")
        if e.get("surface") not in SURFACES:
            bad.append(f"{where}: surface `{e.get('surface')}` is not one of {SURFACES}")
        # Rule 5: a one-sided entry claims the OTHER app lacks the feature, so
        # it must say why - unless REASON_PENDING has already said why no
        # sentence is owed (see that dict and the docstring above).
        if e.get("surface") in ("phone", "desktop") and where not in REASON_PENDING:
            reason = str(e.get("surface_reason") or "").strip()
            missing = "the desktop" if e.get("surface") == "phone" else "the phone"
            if not reason:
                bad.append(f"{where}: says `{e.get('surface')}` with no "
                           f"`surface_reason` - add one sentence saying why "
                           f"{missing} does not have it")
            elif not reason_is_a_sentence(reason):
                bad.append(f"{where}: `surface_reason` is not a reason, it is the value "
                           f"said again: {reason!r}")
        if not isinstance(e.get("limit"), str):
            bad.append(f"{where}: `limit` must be a string (empty when there is none)")
        if not isinstance(e.get("covers"), list) or any(not isinstance(c, str) for c in e.get("covers") or []):
            bad.append(f"{where}: `covers` must be a list of ids")
    # The group order is the design note's, and the file is written in it.
    order = [e.get("group") for e in got if isinstance(e, dict)]
    firsts = [g for i, g in enumerate(order) if i == 0 or order[i - 1] != g]
    if firsts != [g for g in GROUPS if g in set(firsts)]:
        bad.append(f"the groups are not in the fixed order: {firsts}")
    return bad


def phantom_covers(got: list, known: dict) -> list:
    """Rule 2: a `covers` id that is no longer in the code (or in INTERNAL).

    Four real kinds are accepted: a registry id (route section or menu id), an
    INTERNAL id, a lesson id, and a Settings-registry section id (ruling (c),
    2026-10-31 - see `settings_section_ids()`), which is re-read every run so a
    section that is deleted fails here.
    """
    bad = []
    lessons = set(lesson_ids())
    sections = set(settings_section_ids())
    for e in got:
        for c in e.get("covers") or []:
            if c in known or c in INTERNAL:
                continue
            if c in lessons:
                continue
            if c in sections:
                continue
            bad.append(f"{e.get('id')}: covers `{c}`, which is in no registry, "
                       "in no lesson, in no settings section and in INTERNAL")
    return bad


def teaching_problems(got: list, known: dict) -> list:
    """Rule 6: every feature is taught by a lesson, or exempted with a reason.

    THE POINT OF THE WHOLE EXERCISE (docs/EDUCATION-TAB-DESIGN.md section 8):
    "A new feature with neither a lesson nor an exemption becomes a red check,
    not a note nobody reads." The exemption is the project's existing pattern -
    a short list, each entry with a reason, and a stale entry is itself an
    error (INTERNAL above, PHONE_LACKS in check_registry_phone.py, KNOWN_DRIFT
    in check_tutorial_places.py).

    The two kinds of id are told apart by looking the id up, and a name that
    exists in BOTH is not an error: it is a lesson. `memory` is the real case -
    a route section in `READ_ROUTES` and a tutorial id - and a `covers` list
    naming it is a claim about the tutorial, which is what this rule is for. A
    registry id is still checked where a registry id belongs, by rules 1 and 2.
    """
    bad = []
    lessons = set(lesson_ids())
    seen = {e.get("id") for e in got if isinstance(e, dict)}
    for fid, why in LESSON_EXEMPT.items():
        if not str(why).strip():
            bad.append(f"LESSON_EXEMPT `{fid}` has no reason")
        if fid not in seen:
            bad.append(f"LESSON_EXEMPT lists `{fid}`, which is not a feature any "
                       "more - delete the line")
        else:
            entry = next(e for e in got if e.get("id") == fid)
            taught = [c for c in (entry.get("covers") or []) if c in lessons]
            if taught:
                bad.append(f"{fid} is in LESSON_EXEMPT and also names the lesson(s) "
                           f"{', '.join(taught)} - one or the other")
    for e in got:
        fid = e.get("id")
        taught = [c for c in (e.get("covers") or []) if c in lessons]
        if taught or fid in LESSON_EXEMPT:
            continue
        bad.append(f"{fid}: no lesson teaches it and it is not in LESSON_EXEMPT - "
                   "name the lesson in `covers`, or add it to LESSON_EXEMPT with "
                   "the one-line reason teaching it is not useful")
    return bad


def lesson_problems(got: list, lessons=None, exempt=None) -> list:
    """Rule 6, reverse completeness: a lesson with no feature row is an orphan.

    THE HOLE THIS CLOSES (Gemini's ruling, Part II, on Session B section 11.3).
    Every direction except this one was already checked: a feature the code has
    but the list omits; a `covers` id the code no longer has; a feature row with
    no lesson. What nothing could see was a feature ROW disappearing while its
    lesson stayed in `jarvis_tutorials.py` - the checker's own summary printed
    "lessons no feature names (information, not a failure)", so the one loss
    this list exists to prevent was the one nobody would act on. Now an
    unclaimed lesson FAILS, naming the lesson and the two honest fixes: name it
    from the feature row that teaches it, or record in `LESSON_UNCOVERED` why it
    is a cross-cutting rule rather than a feature.

    `lessons` and `exempt` are injectable so the suite can prove the rule bites
    without editing the catalogue or the real list (the same way the other
    problems() helpers are called with made-up input).
    """
    lesson_list = list(lessons if lessons is not None
                       else lesson_ids())
    exempt_map = dict(LESSON_UNCOVERED if exempt is None else exempt)
    bad = []
    claimed_by = {}
    for e in got:
        if not isinstance(e, dict):
            continue
        for c in e.get("covers") or []:
            if c in lesson_list:
                claimed_by.setdefault(c, []).append(str(e.get("id")))
    for lesson in lesson_list:
        if lesson in claimed_by:
            if lesson in exempt_map:
                bad.append(f"LESSON_UNCOVERED `{lesson}` is exempt, but `{claimed_by[lesson][0]}` "
                           "names the lesson now - delete the exemption line (it is covered)")
            continue
        if lesson not in exempt_map:
            bad.append(f"lesson `{lesson}` is in jarvis_tutorials.py, but no feature row's "
                       "`covers` names it - name it in the feature row that teaches it, or add "
                       "it to LESSON_UNCOVERED with the reason it is deliberately not a feature")
    for lesson, why in exempt_map.items():
        if lesson not in lesson_list:
            bad.append(f"LESSON_UNCOVERED `{lesson}` is not a lesson in jarvis_tutorials.py any "
                       "more - delete the line")
        elif not str(why).strip():
            bad.append(f"LESSON_UNCOVERED `{lesson}` has no reason")
    return bad


def keyword_present(word: str, text: str) -> bool:
    """Does this word or phrase occur in `text`, whole-word, case-insensitively?

    The phrase is split and escaped word by word on purpose: `re.escape` escapes
    the SPACE itself in Python 3.7+ ("\\ "), so escaping "talk button" whole and
    then replacing spaces with `\\s+` finds nothing at all - measured the hard
    way while writing this rule. Lowercasing both sides is the "case-insensitive"
    half; the `(?<![a-z0-9])` guards are the "whole word" half, so "card" does
    not match "cards" (a row that claims "card" must be answered by a step that
    says "card").
    """
    parts = [re.escape(part) for part in str(word).lower().split()]
    if not parts:
        return False
    pattern = r"(?<![a-z0-9])" + r"\s+".join(parts) + r"(?![a-z0-9])"
    return re.search(pattern, " ".join(text.lower().split())) is not None


def keyword_shape_problems(fid: str, words) -> list:
    """Rule 7's shape half: a list of 1-3 lowercase words or short phrases."""
    bad = []
    if not isinstance(words, list):
        return [f"{fid}: `must_mention` must be a list of "
                f"{KEYWORDS_MIN}-{KEYWORDS_MAX} lowercase words or short phrases"]
    if not KEYWORDS_MIN <= len(words) <= KEYWORDS_MAX:
        bad.append(f"{fid}: `must_mention` holds {len(words)} word(s) - it must hold "
                   f"{KEYWORDS_MIN} to {KEYWORDS_MAX} (a short list a person can read "
                   "in a diff, not a word cloud)")
    for word in words:
        if not isinstance(word, str) or not word.strip():
            bad.append(f"{fid}: `must_mention` holds {word!r}, which is not a word")
        elif word != word.lower():
            bad.append(f"{fid}: `must_mention` says {word!r} - write it lowercase "
                       "(the check is case-insensitive, so the capital proves nothing)")
        elif not _KEYWORD_SHAPE.match(word) or "  " in word or word != word.strip():
            bad.append(f"{fid}: `must_mention` says {word!r} - that is not a plain "
                       "word or short phrase (lowercase letters, digits, spaces, "
                       "hyphens and apostrophes only)")
    return bad


def keyword_problems(got: list, catalogue=None, gaps=None) -> list:
    """Rule 7: a taught entry names words its own lesson really uses.

    THE HOLE THIS CLOSES. Rules 2 and 6 keep the LIST true about the code, and
    rule 6 keeps a lesson tied to a row - but nothing compared the two texts. A
    row could name a lesson that never mentions it and every rule stayed green
    ("Save a draft to your Drafts folder" taught by a lesson with no "draft" in
    it). The row then tells the owner he can read how to do something when the
    lesson, which he is about to read, does not say it.

    THE THREE WAYS IT BITES, all of them on purpose:

      * a keyword that is absent from every lesson the row names FAILS, naming
        the feature, the lesson(s) and the missing word, so the fix is one line
        in one of two files and the message says which;
      * a TAUGHT row with no `must_mention` FAILS, because otherwise the whole
        rule is skippable by writing nothing - the gate-every-feature half of
        docs/EDUCATION-TAB-DESIGN.md section 8, applied to the words;
      * `must_mention` on a row that no lesson teaches FAILS, because that is a
        field left behind by a lesson that moved - the same "a stale exemption
        fails" shape as INTERNAL, REASON_PENDING and LESSON_UNCOVERED.

    TEACHING_GAP is the one recorded exception, and it is not a silence: see its
    own comment for why 14 rows have no honest word and what happens when a
    lesson finally teaches one of them.

    `catalogue` and `gaps` are injectable so the suite can prove the rule bites
    on made-up lessons and rows without editing `jarvis_tutorials.py` or the
    real list - the same shape `lesson_problems` already has.
    """
    lessons = {lesson["id"]: lesson
               for lesson in (catalogue if catalogue is not None
                              else catalogue_lessons())}
    gap_map = dict(TEACHING_GAP if gaps is None else gaps)
    bad = []
    for e in got:
        if not isinstance(e, dict):
            continue
        fid = e.get("id")
        taught = [c for c in (e.get("covers") or []) if c in lessons]
        words = e.get("must_mention")
        if words is None:
            if taught and fid not in gap_map:
                bad.append(
                    f"{fid}: names the lesson(s) {', '.join(taught)} but has no "
                    "`must_mention` - add 1-3 words those steps really use, or "
                    "record in TEACHING_GAP what the lesson leaves out")
            continue
        bad.extend(keyword_shape_problems(fid, words))
        if not taught:
            bad.append(
                f"{fid}: has `must_mention` but no lesson teaches it - delete the "
                "field (an exempt row has no lesson text to check a word against)")
            continue
        haystack = "\n".join(lesson_text(lessons[c]) for c in taught)
        for word in words if isinstance(words, list) else []:
            if isinstance(word, str) and word.strip() and not keyword_present(word, haystack):
                bad.append(
                    f"{fid}: `must_mention` says {word!r}, which is in none of the "
                    f"lesson(s) it names ({', '.join(taught)}) - use a word those "
                    "steps really use, or fix the lesson, not this list")
    for fid, entry in gap_map.items():
        lesson_id, why = entry if isinstance(entry, tuple) and len(entry) == 2 else (None, None)
        row = next((e for e in got if isinstance(e, dict) and e.get("id") == fid), None)
        if row is None:
            bad.append(f"TEACHING_GAP lists `{fid}`, which is not a feature row any "
                       "more - delete the line")
            continue
        if not str(why or "").strip():
            bad.append(f"TEACHING_GAP `{fid}` has no reason - say what the lesson leaves out")
        if lesson_id not in lessons:
            bad.append(f"TEACHING_GAP `{fid}` names `{lesson_id}`, which is not a lesson "
                       "in jarvis_tutorials.py - name the lesson that should teach it")
        elif lesson_id not in (row.get("covers") or []):
            bad.append(f"TEACHING_GAP `{fid}` names `{lesson_id}`, but the row does not "
                       "name that lesson in `covers` - name one it does")
        if row.get("must_mention") is not None:
            bad.append(f"TEACHING_GAP `{fid}` is recorded as a gap, but the row has "
                       "`must_mention` now - delete the gap line (the lesson teaches it)")
    return bad


def uncovered(got: list, known: dict) -> list:
    """Rule 1: an id nobody listed - a feature added without being written down."""
    covered = set()
    for e in got:
        covered.update(e.get("covers") or [])
    return sorted(i for i in known if i not in covered and i not in INTERNAL)


def internal_problems(known: dict) -> list:
    """The allow-list itself: every id in it real, every reason non-empty."""
    bad = []
    for i, why in INTERNAL.items():
        if i not in known:
            bad.append(f"INTERNAL lists `{i}`, which is in no registry any more")
        if not str(why).strip():
            bad.append(f"INTERNAL `{i}` has no reason")
    return bad


def copy_problems() -> list:
    """Rule 4: the source and its two copies are one file."""
    bad = []
    want = source_bytes()
    for path in COPIES:
        if not path.is_file():
            bad.append(f"{path.relative_to(ROOT)} is missing")
        elif path.read_bytes() != want:
            bad.append(f"{path.relative_to(ROOT)} differs from features/features.json "
                       "(copy it again - the two apps read their own copy)")
    return bad


def pending_problems(got: list) -> list:
    """Rule 5's other half: an exemption that is no longer needed FAILS.

    `REASON_PENDING` names the entries that cannot carry a true one-sided
    sentence yet. The moment one of them stops being a one-sided entry it has
    been corrected (`#495`), so its line is stale - the same rule `INTERNAL`
    already follows for a line whose id is gone. That is what keeps the list
    from becoming a permanent hiding place."""
    one_sided = {e.get("id") for e in got
                 if isinstance(e, dict) and e.get("surface") in ("phone", "desktop")}
    return [f"REASON_PENDING names `{name}`, which is no longer a one-sided entry - "
            f"delete its line (the entry has been corrected): {why}"
            for name, why in sorted(REASON_PENDING.items()) if name not in one_sided]


def _row_text(row: dict) -> str:
    """The four sentences a person reads, joined for the evidence scan."""
    return " ".join(str(row.get(k, "")) for k in ("what", "where", "asks", "limit"))


def _documented_routes(root: Path = ROOT) -> set:
    """Every route shape this repository really carries, punctuation stripped.

    The API doc is the first witness, but a plugin route can be documented in
    its own design note (`docs/DOCKER-INTEGRATION-DESIGN.md`) and defined in its
    shipped module (`backend/jarvis_docker.py`'s PATH_* constants) rather than
    in JARVIS-API.md - all three are real evidence that the route exists. A
    route none of them carries is invented or undocumented, and either way the
    row is not answerable.
    """
    routes = set()
    folders = [root / "docs", root / "backend"]
    files = []
    for folder in folders:
        if folder.is_dir():
            files.extend(sorted(folder.glob("*.md"))[:200])
            files.extend(sorted(folder.glob("*.py"))[:300])
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in re.finditer(r"/api/[A-Za-z0-9_./{}<>:-]+", text):
            routes.add(m.group(0).rstrip(".,;`"))
    return routes


def _route_is_documented(anchor: str, routes: set) -> bool:
    anchor = anchor.rstrip(".,;`")
    for route in routes:
        if route == anchor or route.startswith(anchor + "/") or route.startswith(anchor):
            return True
    return False


def _symbol_is_real(module: str, symbol: str, root: Path = ROOT) -> bool:
    """Is `module.symbol` really defined in the module named?"""
    for folder, suffix in (("backend", ".py"), ("jarvis-backend", ".py"),
                           ("jarvis-desktop/src", ".js")):
        path = root / folder / (module + suffix)
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        pattern = (r"\bdef\s+" + re.escape(symbol) + r"\b"
                   r"|\bclass\s+" + re.escape(symbol) + r"\b"
                   r"|\b(?:const|let|var|function)\s+" + re.escape(symbol) + r"\b"
                   r"|^" + re.escape(symbol) + r"\s*[:=]")
        if re.search(pattern, text, re.M):
            return True
    return False


def anchor_problems(rows: list, root: Path = ROOT) -> list:
    """Rule 8: file, symbol and route evidence is real; a line number never is.

    This is the rule that makes a feature row answerable: the sentence can say
    "the memory plate" only if it also names where that is, and the thing it
    names must exist in this tree. The API doc is the route evidence; a route
    the doc does not list is either undocumented or invented, and both have to
    be fixed before the row is trusted.
    """
    bad = []
    routes = _documented_routes(root)
    for row in rows:
        if not isinstance(row, dict):
            continue
        fid = row.get("id", "?")
        text = _row_text(row)
        line = _LINE_ANCHOR.search(text)
        if line:
            bad.append(f"{fid}: names {line.group(0)!r} as evidence - a line "
                       "number is not evidence (it moves under every edit); name "
                       "the file and the symbol or route instead")
        for m in _PATH_ANCHOR.finditer(text):
            path = m.group(1).rstrip(".,;")
            if not (root / path).is_file():
                bad.append(f"{fid}: names {path!r}, which is not a file in this tree")
        for m in _ROUTE_ANCHOR.finditer(text):
            route = m.group(0).rstrip(".,;`")
            if not _route_is_documented(route, routes):
                bad.append(f"{fid}: names route {route!r}, which docs/JARVIS-API.md "
                           "does not list - document it or fix the row")
        for m in _SYMBOL_ANCHOR.finditer(text):
            module, symbol = m.group(1), m.group(2)
            if not _symbol_is_real(module, symbol, root):
                bad.append(f"{fid}: names `{module}.{symbol}`, but no {module} file in "
                           "this tree defines it")
    return bad


def lesson_anchor_problems(rows: list, lessons=None) -> list:
    """Rule 9's first half (Gemini round 2, ruling 6): a row's lesson must exist.

    Every row may carry `lesson_id` (the one lesson the page's own "Learn
    this" button opens). It must name a lesson that really exists in
    `backend/jarvis_tutorials.py`; a made-up or renamed lesson id fails. The
    lessons a row names through `covers` are checked by the reverse-completeness
    rules already; this makes the row's PRIMARY lesson an explicit anchor.
    """
    known = set(lesson_ids() if lessons is None else lessons)
    bad = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        fid = row.get("id", "?")
        lid = row.get("lesson_id")
        if lid is None:
            continue
        if not isinstance(lid, str) or not lid.strip():
            bad.append(f"{fid}: `lesson_id` is empty - name the one lesson this "
                       "row's Learn button opens, or delete the field")
        elif lid not in known:
            bad.append(f"{fid}: `lesson_id` names {lid!r}, which is not a lesson in "
                       f"backend/jarvis_tutorials.py ({len(known)} lessons) - name a "
                       "real lesson or fix the catalogue")
    return bad


def settings_covers_problems(rows: list, known_settings=None) -> list:
    """Rule 9's second half (Gemini round 2, ruling 6): `settings.*` is real.

    A `settings.*` token in `covers` is a claim that the row is reachable from a
    named row in one app's Settings/menu registry. Those ids are read from the
    two real registries (`menu-catalog.js`, `MenuPlaces.kt`); an invented
    `settings.something` fails rather than sitting in the list as a dead pointer.
    """
    known = set()
    if known_settings is not None:
        known = set(known_settings)
    else:
        known = set(desktop_menu_ids()) | set(phone_menu_ids())
    bad = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        fid = row.get("id", "?")
        for cid in row.get("covers") or []:
            if isinstance(cid, str) and cid.startswith("settings.") and cid not in known:
                bad.append(f"{fid}: covers names {cid!r}, which is not a settings/menu "
                           "id in the desktop menu catalogue or the phone's "
                           "MenuPlaces.kt - name a real row or drop the token")
    return bad


def card_claim(row: dict) -> bool:
    """Does this row's prose positively promise an approval card?

    Sentences, not the whole field: "No card to look. Forget on a fact asks
    first" is a negative and a positive side by side, and the positive half is
    a real claim. A negative word only cancels a phrase when it comes BEFORE it
    ("never asks first", "no card"); a qualifier after it ("one card ... never
    by voice") does not.
    """
    text = _row_text(row)
    for sentence in re.split(r"(?<=[.;])\s+", text):
        for m in _CARD_CLAIM.finditer(sentence):
            before = sentence[max(0, m.start() - 25):m.start()].lower()
            if _CARD_NEGATIVE.search(before):
                continue
            return True
    return False


def _gate_tiers(root: Path = ROOT) -> dict:
    try:
        data = tomllib.loads((root / "backend" / "rebuilt" / "jarvis-framework.toml")
                             .read_text(encoding="utf-8"))
        return dict(data.get("autonomy", {}).get("tiers", {}))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def gate_problems(rows: list, root: Path = ROOT, gaps=None, tiers=None) -> list:
    """Rule 9: a promised card names the gate action it is written under, and
    that action is really a card (`ask`) in the shipped settings.

    `tiers` is for the suite: it can hand the rule a synthetic tier map instead
    of writing a fake repository tree (the sandbox's temp folder is not always
    writable)."""
    gaps = CARD_GATE_GAP if gaps is None else gaps
    bad = []
    tiers = _gate_tiers(root) if tiers is None else tiers
    by_id = {}
    for row in rows:
        if isinstance(row, dict):
            by_id[row.get("id")] = row
    for fid in gaps:
        row = by_id.get(fid)
        if row is None:
            bad.append(f"CARD_GATE_GAP names `{fid}`, which is not a feature row "
                       "any more - delete the line")
        elif not card_claim(row):
            bad.append(f"CARD_GATE_GAP names `{fid}`, whose prose no longer claims a "
                       "card - delete the gap line")
        elif row.get("gate"):
            bad.append(f"CARD_GATE_GAP names `{fid}`, but the row has `gate` now - "
                       "delete the gap line (the card has an action behind it)")
    for row in rows:
        if not isinstance(row, dict):
            continue
        fid = row.get("id", "?")
        gate = row.get("gate")
        claims = card_claim(row)
        if claims and not gate and fid not in gaps:
            bad.append(f"{fid}: says it raises an approval card, but names no `gate` "
                       "action - add the gate action the card is written under, or "
                       "record it in CARD_GATE_GAP with the reason")
        if not claims and gate:
            bad.append(f"{fid}: carries `gate` but its prose claims no card - delete "
                       "the field (or fix the sentence it was meant to back)")
        for action in gate or []:
            if not isinstance(action, str) or not action:
                bad.append(f"{fid}: `gate` has an empty/non-string entry")
            elif action not in tiers:
                bad.append(f"{fid}: `gate` names {action!r}, which is not an action in "
                           "the shipped [autonomy.tiers] - name a real action")
            elif str(tiers[action]) != "ask":
                bad.append(f"{fid}: `gate` names {action!r}, whose tier is "
                           f"{tiers[action]!r}, not 'ask' - the card sentence is false")
    return bad


def problems() -> list:
    """Everything wrong, in one list, each line naming what to fix."""
    got = entries()
    known = known_ids()
    return (field_problems(got) + phantom_covers(got, known) + uncovered(got, known)
            + internal_problems(known) + copy_problems() + teaching_problems(got, known)
            + lesson_problems(got) + pending_problems(got) + keyword_problems(got)
            + anchor_problems(got) + gate_problems(got)
            + lesson_anchor_problems(got) + settings_covers_problems(got))


def main() -> int:
    got = entries()
    known = known_ids()
    lessons = set(lesson_ids())
    keyworded = sum(1 for e in got if isinstance(e, dict) and e.get("must_mention") is not None)
    total_words = sum(len(e["must_mention"]) for e in got if isinstance(e, dict)
                      and e.get("must_mention"))
    checks = [
        (f"{len(got)} entries, each with what / where / asks / limit / surface, and a "
         f"`surface_reason` where it claims the other app lacks it",
         field_problems(got)),
        ("every `covers` id is a real registry id, a real lesson, or in INTERNAL",
         phantom_covers(got, known)),
        (f"every one of the {len(known)} route sections and menu ids is covered or in INTERNAL",
         uncovered(got, known)),
        (f"INTERNAL's {len(INTERNAL)} lines are real, with reasons", internal_problems(known)),
        ("the three copies of features.json are byte-identical", copy_problems()),
        (f"a `phone` reason is owed, never dropped: REASON_PENDING's "
         f"{len(REASON_PENDING)} line(s) are self-emptying", pending_problems(got)),
        (f"every feature is taught by one of the {len(lessons)} lessons, or exempt with a reason",
         teaching_problems(got, known)),
        (f"every one of the {len(lessons)} lessons is named by a feature row or in "
         f"LESSON_UNCOVERED ({len(LESSON_UNCOVERED)} exempt) - reverse completeness",
         lesson_problems(got)),
        (f"every taught feature names words its lesson really uses, or is a "
         f"recorded teaching gap - {keyworded} with `must_mention`, "
         f"{len(TEACHING_GAP)} recorded as a teaching gap",
         keyword_problems(got)),
        ("every file, symbol and route a row names is real, and no row names a "
         "line number as evidence", anchor_problems(got)),
        (f"every row that claims a card names the gate action behind it, and that "
         f"action really resolves to tier ask ({len(CARD_GATE_GAP)} recorded gap(s))",
         gate_problems(got)),
        (f"every row's `lesson_id` names a real lesson in jarvis_tutorials.py "
         f"({len(lessons)} lessons)", lesson_anchor_problems(got)),
        ("every `settings.*` token in `covers` is a real settings/menu id in one "
         "app's registry", settings_covers_problems(got)),
    ]
    failed = 0
    for name, bad in checks:
        print(("ok   " if not bad else "FAIL ") + name)
        for line in bad:
            print(f"        {line}")
        failed += bool(bad)
    covered = set()
    taught = 0
    by_lesson = {}
    for e in got:
        covered.update(e.get("covers") or [])
        named = [c for c in (e.get("covers") or []) if c in lessons]
        if named:
            taught += 1
        for lesson in named:
            by_lesson[lesson] = by_lesson.get(lesson, 0) + 1
    print(f"\n{len(got)} entries in {len(GROUPS)} groups; "
          f"{len(covered & set(known))} of {len(known)} route sections and menu ids covered, "
          f"{len(INTERNAL)} named in INTERNAL")
    print(f"{taught} of {len(got)} features are taught by a lesson; "
          f"{len(LESSON_EXEMPT)} are exempt with a reason; "
          f"{len(by_lesson)} of the {len(lessons)} lessons are named by a feature")
    print(f"{keyworded} of those {taught} taught features name words their lesson really "
          f"uses ({total_words} words in all); {len(TEACHING_GAP)} are recorded in "
          "TEACHING_GAP as lessons that do not teach their row")
    if TEACHING_GAP:
        print("teaching gaps (a work list for the lessons, not a pass): "
              + ", ".join(sorted(TEACHING_GAP)))
    lesson_rows = [e for e in got if isinstance(e, dict) and e.get("lesson_id")]
    settings_tokens = sorted({c for e in got if isinstance(e, dict)
                              for c in (e.get("covers") or [])
                              if isinstance(c, str) and c.startswith("settings.")})
    print(f"{len(lesson_rows)} rows name a primary `lesson_id` "
          f"({len(lessons)} lessons in jarvis_tutorials.py); "
          f"{len(settings_tokens)} distinct `settings.*` covers tokens, all real")
    claimed = [e.get("id") for e in got if isinstance(e, dict) and card_claim(e)]
    gated = [e.get("id") for e in got if isinstance(e, dict) and card_claim(e) and e.get("gate")]
    print(f"{len(gated)} of {len(claimed)} card-claiming features name their gate action; "
          f"{len(CARD_GATE_GAP)} recorded in CARD_GATE_GAP as not yet mapped (a work "
          "list, not a pass)")
    if CARD_GATE_GAP:
        print("card gate gaps (a work list for the catalogue, not a pass): "
              + ", ".join(sorted(CARD_GATE_GAP)))
    unclaimed = sorted(lessons - set(by_lesson) - set(LESSON_UNCOVERED))
    if unclaimed:
        print("lessons no feature names (FAILED above, listed so the fix is one line each): "
              + ", ".join(unclaimed))
    print(f"{len(checks) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
