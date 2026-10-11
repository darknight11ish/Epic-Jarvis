package com.jarvis.client.ui

import com.jarvis.client.net.MenuCatalog
import com.jarvis.client.net.MenuLogic
import com.jarvis.client.net.MenuView

/**
 * "Find anything" - the phone's half of the desktop's command palette
 * (`jarvis-desktop/src/palette.js`, `palette-ui.js`: Alt+Space, then type).
 *
 * WHY THIS EXISTS. The parity audit of 2026-10-10
 * (`.dsh-scratch/android-verify/PARITY-AUDIT-2026-10-10.md`, row 244 and gap
 * 8) found the desktop's typed search over every place had no phone
 * counterpart: the phone could reach a place only by already knowing which
 * screen it is on, or by saying "open ..." out loud. Settings grew its own
 * search box on 2026-10-09 ([SettingsSearch]), but that one only ever looks at
 * Settings' own rows - the Brain, History, the Inbox and every screen with no
 * settings card of its own were still unfindable by typing.
 *
 * WHERE EVERY NAME COMES FROM: THE REAL CATALOGUE, never a second copy - the
 * same rule `palette.js` follows, for the same reason (a hand-typed list
 * drifts within a week and sends the owner to a card that no longer exists).
 *
 *  - The titles and the one-line descriptions are [MenuCatalog]'s, which
 *    `tools/gen_menu_cases.py` generates from `backend/jarvis_menus.py` - the
 *    same list "Show or hide menus", the desktop's palette and Jarvis's own
 *    voice all read.
 *  - WHERE each one opens is [MenuPlaces]' own answer (`item(key = ...)` on
 *    the phone), so a menu whose place moves moves here too, and
 *    `MenuVisibilityTest` already fails if a phone menu has no place at all.
 *  - A Settings row is also searched by [SettingsSearch]'s own words for it
 *    (its controls' names, like "SearXNG" or "Obsidian"), because that is the
 *    phone's existing vocabulary for Settings - there is deliberately no
 *    second one here.
 *  - A feature group ("Study", "Chatbots") is [MenuCatalog.GROUPS]' own title
 *    and one-line description, and its row opens the first member this phone
 *    has ([GROUPS]).
 *  - A menu is also searched by [MenuCatalog.Menu.names], the names Jarvis
 *    already answers to ("app lock", "study decks", "the menu list"). Those
 *    are the same aliases the desktop's palette matches, and they reach the
 *    Kotlin catalogue through the same generator that writes it - they used to
 *    be written only into the JSON fixture and the desktop's own copy, so the
 *    phone had the menus but not their names.
 *
 * A ROW OPENS WHAT IT SAYS, and nothing else: this object holds no switch, no
 * value and no request to the PC. `FindAnythingTest` walks every row and
 * checks its `section` is a real `item(key = ...)` on the screen it names.
 *
 * TWO THINGS STAY HIDDEN (the phone's rule is stricter than the desktop's,
 * which lists a menu hidden with "Show or hide menus" and marks it "Hidden on
 * this computer"):
 *
 *  1. **A menu the owner hid never appears** ([MenuView.shows]). Searching for
 *     it finds nothing until it is shown again, so this can never become the
 *     way round "Show or hide menus" that the hiding was meant to close.
 *  2. **The memory lists and chat history never appear while "Hide memory
 *     lists and chat history" is on** ([PRIVATE_IDS]). That switch is a
 *     privacy one - it is what the owner turns on when someone else can see
 *     the screen - so a typed search must not put those rows back on it.
 *     Every row here holds only a menu's own title and one-line description,
 *     never a fact, a chat or a card's words, so nothing else can leak.
 *
 * The places whose *contents* that switch hides in place (Goals, the morning
 * briefing, Coming up, My study decks, Today, Projects, Spending, the
 * chatbot and support chats) stay findable by name: their own plates already
 * say "Hidden while memory lists and chat history are hidden" and ask for the
 * fingerprint before showing anything, so reaching one of them shows nothing.
 * They are not memory lists or chat history themselves, they are the screens
 * that hold some.
 *
 * Pure - no Android - so [FindAnythingTest] runs on a plain JVM. The search
 * box itself is `ui/screens/FindScreen.kt`.
 */
object FindAnything {

    /**
     * One place the owner can go.
     *
     * @param id the menu id this row IS, or `place.<name>` for a screen with
     *   no menu id of its own (the Inbox, Live, ...), or
     *   `settings-row.<key>` for a Settings row nothing may hide. Only a real
     *   menu id can be hidden, which is what [menu] says.
     * @param title the words the app itself shows for it.
     * @param about the catalogue's own one-line description; empty when the
     *   app has none for this row.
     * @param screen the phone's screen it opens.
     * @param section the `item(key = ...)` to bring into view on that screen,
     *   or null for the top of it - exactly what "open <a place>" by voice
     *   passes ([OpenPlace]).
     * @param words extra words a search may find it by, always the app's own:
     *   the names Jarvis already answers to (the catalogue's `names`, e.g.
     *   "app lock" for Security), and for a Settings row the control names and
     *   detail sentences [SettingsSearch] already holds for it.
     * @param menu true when "Show or hide menus" can hide this row.
     * @param kind the catalogue's own `kind` (`card`, `row`, `tab`, `entry`),
     *   or `screen` for a phone screen with no menu, or `group` for a feature
     *   group: with [screen], what picks the heading a result is drawn under.
     * @param shownBy the menu id whose visibility decides this row
     *   ([MenuView.shows]). The row's own [id] for everything but a group: a
     *   group is a hiding unit rather than a menu, so what decides whether its
     *   row may be shown is the member it would open.
     */
    data class Row(
        val id: String,
        val title: String,
        val about: String,
        val screen: Screen,
        val section: String?,
        val words: String,
        val menu: Boolean,
        val kind: String,
        val shownBy: String = id,
    ) {
        /** The heading this row is drawn under. */
        val heading: String get() = headingOf(screen, kind)
    }

    // ------------------------------------------------------------ the index --

    /**
     * Menu id -> the Settings row's own `item(key = ...)`, from [MenuPlaces].
     * A menu id listed twice keeps its FIRST key (`brain.work.jobs` is drawn
     * as both "jobs" and "tasks"; either one lands on the same card).
     */
    private val SETTINGS_ITEM: Map<String, String> = invert(MenuPlaces.SETTINGS)

    /** Menu id -> the Brain row's own `item(key = ...)`, from [MenuPlaces]. */
    private val BRAIN_ITEM: Map<String, String> = invert(MenuPlaces.BRAIN)

    private fun invert(places: Map<String, String>): Map<String, String> {
        val out = LinkedHashMap<String, String>()
        for ((key, id) in places) out.putIfAbsent(id, key)
        return out
    }

    /**
     * Menus whose place is a screen of their own rather than an `item(key)`
     * on one - the entries in the phone's navigation. Each is where the
     * owner really lands when they tap that entry, which is what
     * `MenuPlaces.INSIDE` says in words.
     */
    private val ENTRY_PLACES: Map<String, Pair<Screen, String?>> = mapOf(
        // The status line at the top of Home opens Platform checks, whose
        // Connection card is the phone's connection status.
        "entry.checks" to (Screen.CHECKS to "connection"),
        // The phone's Help is its FAQ screen ("Tutorials and the FAQ" is the
        // Brain's own card for the same thing, `brain.model.tutorials`).
        "entry.help" to (Screen.FAQ to null),
        "entry.settings" to (Screen.SETTINGS to null),
        "entry.appearance" to (Screen.APPEARANCE to null),
        "entry.voices" to (Screen.VOICES to null),
        "entry.voice-check" to (Screen.VOICE_CHECK to null),
        // A menu drawn inside something that is not a menu itself, so the
        // walk up the parents has nothing to land on: `MenuPlaces.INSIDE`
        // says in words that this one is "HistoryTags: the last row, Suggest
        // tags overnight", and History's own `item(key = "settings")` is the
        // section the tags and that switch are set in (HistoryScreen.kt).
        "brain.history.tag-suggestions" to (Screen.HISTORY to "settings"),
    )

    /**
     * Phone screens that are not menus and must never be hidden: a row for
     * each is the honest half of "find anything", because a search that
     * cannot find the Inbox is not one. Nothing here is a menu id, so
     * "Show or hide menus" has nothing to hide and never needed a line in
     * [MenuPlaces] for them (which is why they are written down here).
     */
    private val SCREENS: List<Row> = listOf(
        Row(
            id = "place.home", title = "Home",
            about = "The face, your own chat, and what needs you.",
            screen = Screen.HOME, section = null, words = "", menu = false,
            kind = "screen",
        ),
        Row(
            id = "place.inbox", title = "Inbox",
            about = "Approval cards waiting for your yes or no.",
            screen = Screen.INBOX, section = null, words = "", menu = false,
            kind = "screen",
        ),
        Row(
            id = "place.live", title = "Jarvis Live",
            about = "Talk back and forth, with no \"Hey Jarvis\" needed.",
            screen = Screen.LIVE, section = null, words = "", menu = false,
            kind = "screen",
        ),
        Row(
            id = "place.approvals", title = "Past approvals",
            about = "The cards you have already decided, and how each one ended.",
            screen = Screen.APPROVALS, section = null, words = "", menu = false,
            kind = "screen",
        ),
        Row(
            id = "place.features", title = "Everything Jarvis can do",
            about = "Every feature, in plain words. This screen only reads.",
            screen = Screen.FEATURES, section = null, words = "", menu = false,
            kind = "screen",
        ),
        Row(
            id = "place.train-voice", title = "Train my voice",
            about = "Read short sentences so Jarvis learns your voice.",
            screen = Screen.VOICE, section = null, words = "", menu = false,
            kind = "screen",
        ),
    )

    /**
     * Settings rows that are not menus at all, so [MenuPlaces] leaves them
     * out (nothing may hide them). Their titles come from [SettingsSearch],
     * and their `about` is empty because the app has no one-line description
     * of them - the plate's own sentences are still searched, through
     * [SettingsSearch.wordsFor].
     */
    private val LOOSE_SETTINGS: List<Row> = SettingsSearch.SECTION_KEYS
        .filter { key -> SETTINGS_ITEM.values.none { it == key } }
        .mapNotNull { key ->
            val row = SettingsSearch.row(key) ?: return@mapNotNull null
            Row(
                id = "settings-row.$key", title = row.title, about = "",
                screen = Screen.SETTINGS, section = key,
                words = SettingsSearch.wordsFor(key), menu = false,
                kind = "card",
            )
        }

    /**
     * The feature groups themselves ([MenuCatalog.GROUPS]) - the desktop's
     * palette lists them first, and they are "what Jarvis itself answers to by
     * voice". A group is a HIDING unit rather than a place (["Show or hide
     * menus"] hides a whole group as one switch), so a group row opens the
     * first member this phone has - the same thing the desktop's own
     * `placeFor` does with a group, and for the same reason: a row that goes
     * nowhere is worse than no row.
     *
     * [Row.shownBy] is that member, so a hidden member takes the group row
     * with it: hiding the group hides every member, and hiding the one member
     * the row would open hides the row too. Nothing here can lead to a place
     * the owner has hidden.
     */
    private val GROUPS: List<Row> = MenuCatalog.GROUPS.mapNotNull { group ->
        val first = MenuLogic.members(group.id, MenuLogic.PHONE).firstOrNull { placeOf(it) != null }
            ?: return@mapNotNull null
        val (screen, section) = placeOf(first) ?: return@mapNotNull null
        Row(
            id = group.id, title = group.title, about = group.about,
            screen = screen, section = section, words = "",
            menu = true, kind = "group", shownBy = first,
        )
    }

    /**
     * Every place, in the order it should be read: the feature groups first
     * (they are what Jarvis itself answers to by voice), then the screens with
     * no menu, then every menu this phone has in catalogue order - the same
     * shape and the same order as the desktop's own list.
     */
    val ROWS: List<Row> = buildList {
        addAll(GROUPS)
        addAll(SCREENS)
        for (m in MenuCatalog.MENUS) {
            if (!m.phone) continue
            // `safety.*` is the catalogue's own bookkeeping for things that
            // must never be hidden (approval cards, the stale-link banner,
            // the crisis-help line). None of them is a place a screen can
            // open - the desktop's palette skips exactly these - and offering
            // one would be a row that does nothing. The two ENTRIES filed
            // under `safety` are the exception on both apps: they are ways in
            // (the status line, the Settings entry), not banners.
            if (m.area == "safety" && m.kind != "entry") continue
            val (screen, section) = placeOf(m.id) ?: continue
            // A Settings row is shown under the heading the Settings screen
            // really draws, which is not always the catalogue's own title for
            // the same menu: the catalogue calls `settings.limits` "Limits and
            // frequency" and the phone's screen says "Limits and how often
            // Jarvis does things" (SettingsJump, SettingsSearch). A finder that
            // answered with a heading the owner cannot see on the screen would
            // send them looking for it. The one-line description is the
            // catalogue's either way, and both sources are held to the screens
            // by their own tests.
            val settingsHeading =
                if (screen == Screen.SETTINGS && section != null) SettingsSearch.row(section)?.title else null
            add(
                Row(
                    id = m.id, title = settingsHeading ?: m.title, about = m.about,
                    screen = screen, section = section,
                    // The catalogue's own aliases first - "app lock", "study
                    // decks", "the menu list" - then a Settings row's own
                    // control names, which is where "SearXNG" and "Obsidian"
                    // come from.
                    words = buildList {
                        addAll(m.names)
                        if (screen == Screen.SETTINGS && section != null) {
                            add(SettingsSearch.wordsFor(section))
                        }
                    }.joinToString(" "),
                    menu = true, kind = m.kind,
                ),
            )
        }
        // A place whose own card moved: `settings.connection` has no Settings
        // row on this phone (it is never hideable, which is why `MenuPlaces`
        // omits it), so its place is the entry above - Platform checks'
        // Connection card - and there is deliberately no second row for it.
        addAll(LOOSE_SETTINGS)
    }

    /**
     * Where one menu opens on this phone, or null when the phone has no place
     * for it. The same chain `MenuPlaces` describes in prose: the entries
     * first (a way IN is its own screen, not the row that offers it), then
     * the menu's own row, then - for a row drawn INSIDE another card - the
     * nearest parent that has one (the desktop's `placeFor` walks up the same
     * way).
     */
    private fun placeOf(menuId: String): Pair<Screen, String?>? {
        // Before the rows: `entry.settings` is ALSO the Brain's "settings-entry"
        // row, and the desktop's own palette opens the Settings window for it
        // rather than the row that offers it. Someone typing "settings" means
        // the screen.
        ENTRY_PLACES[menuId]?.let { return it }
        SETTINGS_ITEM[menuId]?.let { return Screen.SETTINGS to it }
        BRAIN_ITEM[menuId]?.let { return Screen.BRAIN to it }
        val parent = MenuLogic.menu(menuId)?.parent ?: return null
        return placeOf(parent)
    }

    // --------------------------------------------------------- what is shown --

    /**
     * Menu ids that are the owner's memory lists and chat history - the rows
     * "Hide memory lists and chat history" hides. Each one is a list of the
     * owner's own words, or the way into one:
     *
     *  - "Learning", "Saved automatically", "Always keep in mind",
     *    "Between us", "People and things", "Waiting for you", "Wiki",
     *    "Deep questions", "What did I believe on this date?" and "Topics"
     *    are the Brain's memory lists (each plate hides its own words under
     *    the same switch: `ProfilePlate.kt`, `AutoLearnPlate.kt`,
     *    `SharedPlate.kt`, `EntitiesPlate.kt`, `TopicsPlate.kt`, ...);
     *  - "Chat history and conversations" and "Forget a time frame" are the
     *    owner's past chats, and the tag suggestions are drawn from them;
     *  - the History entry is the way into all of it.
     */
    val PRIVATE_IDS: Set<String> = setOf(
        "entry.history",
        "brain.memory.learning",
        "brain.memory.auto",
        "brain.memory.profile",
        "brain.memory.between-us",
        "brain.memory.people-things",
        "brain.memory.waiting",
        "brain.memory.wiki",
        "brain.memory.deep",
        "brain.memory.as-of",
        "brain.memory.topics",
        "brain.history.forget-range",
        "brain.history.tag-suggestions",
    )

    /**
     * The rows that may be shown right now: everything the owner has not
     * hidden with "Show or hide menus", and - while "Hide memory lists and
     * chat history" is on - nothing from [PRIVATE_IDS]. A row is judged by
     * [Row.shownBy], which is its own id for every row but a group's. Order is
     * [ROWS]'.
     */
    fun visible(menus: MenuView, privateHidden: Boolean): List<Row> =
        ROWS.filter { row ->
            if (row.menu && !menus.shows(row.shownBy)) return@filter false
            !(privateHidden && row.id in PRIVATE_IDS)
        }

    /**
     * The heading a row is drawn under: the desktop's own four, read off THIS
     * phone's shape - the catalogue's `kind` for a way in ("entry"), then
     * which screen the row opens.
     *
     * The catalogue's `area` is not used, and that is the point: it says where
     * the DESKTOP draws a card (its Settings page), which is not where the
     * phone does. The hardware, second-card, spending, limits and "What this
     * backend supports" cards are all Settings cards on the PC and all Brain
     * rows here, so a heading read off `area` would file them under a screen
     * they are not on.
     */
    fun headingOf(screen: Screen, kind: String): String = when {
        kind == "entry" -> FindWords.ACTIONS
        screen == Screen.SETTINGS -> FindWords.SETTINGS
        // History is the Brain's own "Earlier chats" on this phone:
        // `MenuPlaces.BRAIN` maps it to `entry.history`.
        screen == Screen.BRAIN || screen == Screen.HISTORY -> FindWords.BRAIN
        else -> FindWords.SCREENS
    }

    // ------------------------------------------------------------- searching --

    /**
     * Case- and punctuation-blind, so "What asks first?" and "what asks
     * first" are the same search. This IS [SettingsSearch.normalise]: the
     * phone keeps one fold for both boxes rather than two that can disagree.
     */
    fun fold(text: String): String = SettingsSearch.normalise(text)

    /** Where `needle` sits inside `hay`: 0 at the very start, then by word
     *  start, then anywhere. `-1` when it is not there at all. */
    private fun rankAt(hay: String, needle: String): Int {
        if (hay.isEmpty() || needle.isEmpty()) return -1
        val at = hay.indexOf(needle)
        if (at < 0) return -1
        if (at == 0) return 0
        return if (hay[at - 1] == ' ') 1 else 2
    }

    /**
     * Ranks one row against an already-folded query. Lower is better; -1 is
     * no match. A title that starts with the words beats a title that
     * contains them, which beats the names Jarvis already answers to, which
     * beats the one-line description - the same order, and the same numbers,
     * as the desktop's `scoreItem`.
     *
     * One difference from the desktop, and it is only ever a tie-break: the
     * desktop ranks each alias on its own, and here they are joined into
     * [Row.words] and ranked as one run of text. A title match wins before
     * this is ever reached, so the two orders agree on what the owner sees
     * first.
     */
    fun score(row: Row, query: String): Int {
        val q = fold(query)
        if (q.isEmpty()) return 0
        val title = fold(row.title)
        val titleAt = rankAt(title, q)
        if (titleAt == 0) return 0
        if (titleAt == 1) return 1
        if (titleAt == 2) return 2
        val wordsAt = rankAt(fold(row.words), q)
        if (wordsAt >= 0) return 3 + wordsAt
        val aboutAt = rankAt(fold(row.about), q)
        if (aboutAt >= 0) return 6 + aboutAt
        val idAt = rankAt(fold(row.id.replace('.', ' ')), q)
        if (idAt >= 0) return 9 + idAt
        return -1
    }

    /**
     * The rows the search shows, best first. Ties keep the index order, so
     * the list never shuffles between two keystrokes. An empty query shows
     * nothing here: the screen says what it searches and lists everything
     * instead, which is a different sentence from "these matched".
     */
    fun results(query: String, menus: MenuView, privateHidden: Boolean): List<Row> {
        val q = fold(query)
        if (q.isEmpty()) return emptyList()
        val shown = visible(menus, privateHidden)
        return shown
            .mapIndexedNotNull { index, row ->
                val score = score(row, q)
                if (score < 0) null else Triple(row, score, index)
            }
            .sortedWith(
                compareBy({ it.second }, { it.first.title.length }, { it.third }),
            )
            .map { it.first }
    }

    /** Every row that may be shown right now, in index order - the empty box's list. */
    fun all(menus: MenuView, privateHidden: Boolean): List<Row> = visible(menus, privateHidden)

    /** How many rows the box would show with nothing typed. */
    fun count(menus: MenuView, privateHidden: Boolean): Int = visible(menus, privateHidden).size

    /** One row by id, or null - for tests and for a screen that names a place. */
    fun row(id: String): Row? = ROWS.firstOrNull { it.id == id }
}

/**
 * The words the phone's "Find anything" says. Kept in one place so the screen
 * and [FindAnythingTest] cannot disagree, and so the two apps describe the
 * same box in the same words where the box really is the same.
 *
 * [SAME] carries the words that ARE the desktop's, word for word, read out of
 * `jarvis-desktop/src/palette.js` by the test. [PHONE] carries the two that
 * are the same idea in this phone's own words, each with its reason - the
 * desktop's own sentence names its window (and its Jarvis bar), and this app
 * has screens instead. Anything the desktop's `WORDS` grows that is in
 * neither is a word this phone has not answered, and the test says so.
 */
object FindWords {

    /** The screen's name, and what the button that opens it says - the desktop's own. */
    const val TITLE = "Find anything"
    const val BUTTON = "Find"

    /** The field's own name, for a screen reader. */
    const val LABEL = "Search what Jarvis can do"
    const val PLACEHOLDER = "Type a few letters - a screen, a setting, an action…"

    /**
     * Emptying the box. Deliberately the same word Settings' own box uses
     * (SettingsSearchWords.CLEAR): one app, one word for the same control.
     */
    const val CLEAR = "Clear"

    /** What the box searches, said before anything is typed (never a blank list). */
    const val SEARCHES =
        "Searches every screen, every setting and everything else this app can open. " +
            "It only takes you there: nothing here changes anything."

    /** The list with nothing typed: a plain count, not a bare number. */
    const val ALL_ONE = "1 thing Jarvis can do"
    const val ALL_MANY = "{n} things Jarvis can do"

    /** A search that matched nothing. */
    const val NONE_TITLE = "Nothing matches that."
    const val NONE_BODY =
        "Try the name you see on the screen, or a word from its one-line description."

    /** A screen with nothing at all to list - never expected, said plainly. */
    const val EMPTY_TITLE = "There is nothing to list yet."
    const val EMPTY_BODY =
        "The list is built from the app's own menus, and none of them reached this screen."

    /** What a screen reader hears when the list changes. */
    const val RESULTS_ONE = "1 match"
    const val RESULTS_MANY = "{n} matches"
    const val RESULTS_NONE = "Nothing matches that"

    /** The headings the results are drawn under - the desktop's own four. */
    const val SCREENS = "Screens"
    const val SETTINGS = "Settings"
    const val BRAIN = "Brain"
    const val ACTIONS = "Actions"

    /** Fill `{n}` (or any other single key) - the desktop's own `fill`. */
    fun fill(text: String, vars: Map<String, Any>): String =
        Regex("\\{(\\w+)\\}").replace(text) { m ->
            val key = m.groupValues[1]
            if (vars.containsKey(key)) vars.getValue(key).toString() else m.value
        }

    /** What a screen reader hears when the list changes. */
    fun line(query: String, shown: Int): String = when {
        query.isBlank() -> SEARCHES
        shown == 0 -> ""
        shown == 1 -> RESULTS_ONE
        else -> fill(RESULTS_MANY, mapOf("n" to shown))
    }

    /** The count over the list with nothing typed. */
    fun allLine(shown: Int): String =
        if (shown == 1) ALL_ONE else fill(ALL_MANY, mapOf("n" to shown))

    /** The words that are the desktop's, word for word: `palette.js` key -> ours. */
    val SAME: Map<String, String> = mapOf(
        "title" to TITLE,
        "search_label" to LABEL,
        "placeholder" to PLACEHOLDER,
        "all_one" to ALL_ONE,
        "all_many" to ALL_MANY,
        "none_title" to NONE_TITLE,
        "empty_title" to EMPTY_TITLE,
        "results_one" to RESULTS_ONE,
        "results_many" to RESULTS_MANY,
        "results_none" to RESULTS_NONE,
    )

    /** The same idea in this phone's own words: `palette.js` key -> ours. */
    val PHONE: Map<String, String> = mapOf(
        // The desktop's sentence says "the name you see in the window"; this
        // app's windows are screens, and the phone has none.
        "none_body" to NONE_BODY,
        // ...and the desktop's empty list says "none of them reached this
        // bar", which is the PC's Jarvis bar.
        "empty_body" to EMPTY_BODY,
    )

    /**
     * The desktop's words this phone has no use for, each with its reason.
     * The test fails if `palette.js` grows a word that is in neither this,
     * [SAME] nor [PHONE] - so the two apps cannot drift apart quietly.
     */
    val NOT_ON_PHONE: Map<String, String> = mapOf(
        // "Type / to find anything": a phone has no "/" key, and its way in is
        // the labelled Find button on Home.
        "hint" to "the desktop's own key (\"/\") and its bar",
        // "↑ ↓ to move · Enter to open · Esc to close": no arrow, Enter or Esc
        // key exists on a phone; the rows are tapped.
        "keys" to "arrow, Enter and Esc keys, which a phone does not have",
        // "Find anything, {n} things. Type to search." - what the desktop's
        // screen reader says as the palette opens. This app announces through
        // live regions on the line under the box instead (Modifier.liveStatus),
        // which is how every other screen here speaks.
        "opened" to "announced on opening; this app uses live regions",
        "opened_one" to "announced on opening; this app uses live regions",
        "opened_none" to "announced on opening; this app uses live regions",
    )
}
