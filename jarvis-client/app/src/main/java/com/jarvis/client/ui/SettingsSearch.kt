package com.jarvis.client.ui

/**
 * Search inside Settings - the phone's half of the desktop's search box
 * (`jarvis-desktop/src/settings-search.js`; `docs/SETTINGS-UX-DESIGN.md`).
 *
 * The owner's request of 2026-10-09: "a lot more visually simple, with a
 * search bar in settings. I still want everything adjustable, just easier to
 * find and more efficient." Settings had grown to twenty sections with a
 * "Jump to:" list over four lines at the top; the list is the fastest way to
 * a section you already know, and this is the way to one you do not.
 *
 * Pure - no Android - so [SettingsSearchTest] can hold three things that
 * would otherwise drift:
 *
 *  1. **The words are the same as the desktop's.** [SettingsSearchWords]
 *     carries the box's name, the placeholder, the hint, the empty state and
 *     the two count lines, and the test reads both copies. Two apps that say
 *     different things about the same feature is exactly the drift the
 *     open-chat phrase list already cost this project once.
 *  2. **Every section on the screen can be found.** [ROWS] is one entry per
 *     `item(key = ...)` in `SettingsScreen.kt`, and the test holds it to that
 *     screen's own rows - a section added without a line here fails.
 *  3. **The quotes are really what the app says.** Every `quotes` phrase must
 *     appear in that section's own source, so an index cannot describe a
 *     screen that no longer exists. This is the phone's answer to the
 *     desktop's "the words are read off the page" - Compose cannot hand a
 *     test its rendered text, so the test reads the composables instead.
 *
 * It changes nothing: no section, switch or value is touched, and clearing
 * the box puts every row back. Nothing here calls the network or the desktop.
 */
object SettingsSearch {

    /**
     * One section, and the words a search may find it by.
     *
     * @param key the `item(key = ...)` `SettingsScreen.kt` draws it under.
     * @param title the section's own heading, in the app's words.
     * @param label extra words for the controls that have no heading of their
     *   own ("Train my voice", "Think through complex questions").
     * @param quotes the detail sentences under those controls, the same
     *   words the screen shows. Each one must appear in [source].
     * @param source the files `SettingsSearchTest` looks for those quotes in.
     */
    data class Row(
        val key: String,
        val title: String,
        val label: String,
        val quotes: List<String>,
        val source: List<String>,
    )

    /** Where a title is checked, relative to `jarvis-client/.../com/jarvis/client/`. */
    private val SCREEN = listOf("ui/screens/SettingsScreen.kt")
    private val JUMP = listOf("ui/SettingsJump.kt")
    private val PLATES = "ui/screens/"

    /**
     * In the order the screen draws them. "appearance" and "floating-avatar"
     * are the screen's own keys (the registry calls the first
     * "appearance-card"; `MenuPlaces.SETTINGS_ALIAS` maps it), and every
     * other key is the same one the desktop's own card carries.
     *
     * `source` is where the title and quotes are looked for. Where the words
     * live in `SettingsJump.ENTRIES` rather than in a section body - the
     * sections that hold one button or one plate - that file is named
     * instead, because those entries ARE the app's words for that section.
     */
    val ROWS: List<Row> = listOf(
        Row(
            key = "voice", title = "Voice",
            label = "Train my voice; Voice check; Jarvis's voice; Listen on this phone",
            quotes = listOf(
                "Whether Jarvis knows your voice, how strict that check is, and ",
                "Pair with your desktop first - these settings live on it.",
            ),
            source = SCREEN,
        ),
        Row(
            key = "security", title = "Security",
            label = "Lock and fingerprint settings; App lock; screen lock; approvals",
            quotes = listOf("Lock and fingerprint settings"),
            source = SCREEN,
        ),
        Row(
            key = "menu-visibility", title = "Show or hide menus",
            label = "Hide a menu; show a menu; fold a card away; the " +
                "three hidden - Show line",
            quotes = listOf("Show or hide menus"),
            source = JUMP + SCREEN,
        ),
        Row(
            key = "appearance", title = "Appearance",
            label = "Theme; colours; face; animal options; sharpness; frame rate",
            quotes = listOf(
                "Theme, the reactor's face, the animal options, and how it all looks.",
                "Pair with your desktop first - Appearance shares the face and ",
            ),
            source = SCREEN,
        ),
        Row(
            key = "floating-avatar", title = "Floating Jarvis",
            label = "Floating face; bubble mode; draw over other apps; overlay",
            quotes = listOf("Floating Jarvis"),
            source = JUMP + listOf(PLATES + "FloatingAvatarPlate.kt"),
        ),
        Row(
            key = "manner", title = "How Jarvis talks",
            label = "Manner; plain answers; humour; thinking levels; deep thinking",
            quotes = listOf("How Jarvis talks"),
            source = JUMP + listOf(PLATES + "MannerPlate.kt"),
        ),
        Row(
            key = "web-search", title = "Web search",
            label = "Search providers; SearXNG; DuckDuckGo; Exa; Tavily; Brave; API keys",
            quotes = listOf("Web search"),
            source = JUMP + listOf(PLATES + "WebSearchPlate.kt"),
        ),
        Row(
            key = "prompt-coach", title = "Prompt coach",
            label = "Coach this; rewrite a question; score a prompt",
            quotes = listOf("Prompt coach"),
            source = JUMP + listOf(PLATES + "PromptCoachPlate.kt"),
        ),
        Row(
            key = "asks-first", title = "What asks first",
            label = "Approval cards; ask me first; what needs your OK; lights without a card",
            quotes = listOf("What asks first"),
            source = JUMP + listOf(PLATES + "AsksFirstPlate.kt"),
        ),
        Row(
            key = "reach", title = "What Jarvis can reach",
            label = "Home Assistant; calendar; email; notes; tools; what Jarvis may read",
            quotes = listOf("What Jarvis can reach"),
            source = listOf(PLATES + "ReachPlate.kt"),
        ),
        Row(
            key = "email-sending", title = "Sending email",
            label = "Send email; drafts; recipients; reply",
            quotes = listOf("Sending email"),
            source = JUMP + listOf(PLATES + "EmailSendingPlate.kt"),
        ),
        Row(
            key = "folders", title = "Folders Jarvis may look in",
            label = "Which folders Jarvis may read; Obsidian; Logseq; Joplin; Notion",
            quotes = listOf("Folders Jarvis may look in"),
            source = JUMP + listOf(PLATES + "FoldersPlate.kt"),
        ),
        Row(
            key = "backup", title = "Backups",
            label = "Back up Jarvis; locked backup file; recovery code; restore",
            quotes = listOf("Backups"),
            source = JUMP + listOf(PLATES + "BackupPlate.kt"),
        ),
        Row(
            key = "watch-notify", title = "Smartwatch notifications",
            label = "Smartwatch; watch; notifications on a watch",
            quotes = listOf("Smartwatch notifications"),
            source = JUMP + listOf(PLATES + "WatchNotifyPlate.kt"),
        ),
        Row(
            key = "phone-notify", title = "Phone notifications",
            label = "Read phone notifications; notification access; hide one-time codes; " +
                "which apps may send them",
            quotes = listOf("Phone notifications"),
            source = JUMP + listOf(PLATES + "PhoneNotificationsPlate.kt"),
        ),
        Row(
            key = "screen-look", title = "Look at this and Watch with me",
            label = "Screen; camera; picture mode; look at my screen",
            quotes = listOf("Look at this and Watch with me"),
            source = JUMP + listOf(PLATES + "LookPlate.kt"),
        ),
        Row(
            key = "browser-engine", title = "Browser without a window",
            label = "Headless browser; Obscura; read a page; no window",
            quotes = listOf("Browser without a window (Obscura)"),
            // The section's heading is the words module's own constant, so
            // the quote is looked for there rather than in the plate.
            source = JUMP + listOf("net/BrowserEngine.kt"),
        ),
        Row(
            key = "handoff", title = "When the phone does not answer",
            label = "Captcha hand-off; keep offering it; how long the offer stays",
            quotes = listOf("When the phone does not answer"),
            source = JUMP + listOf("net/HandoffMode.kt"),
        ),
        Row(
            key = "devices", title = "Devices",
            label = "Paired devices; each device's own key; pair a phone; remove a device",
            quotes = listOf("Devices"),
            source = JUMP + listOf(PLATES + "DevicesPlate.kt"),
        ),
        Row(
            key = "quick-tiles", title = "Quick Settings tiles",
            label = "Android Quick Settings; tile; pull down the shade",
            quotes = listOf("Quick Settings tiles"),
            source = JUMP + listOf(PLATES + "QuickTilesPlate.kt"),
        ),
    ) + listOf(
        // The search box itself is a `LazyColumn` item, so SettingsJumpTest
        // sees it as a row; it is a control, not a section, and it is never
        // filtered out (there would be no way back to the box).
        Row(
            key = SettingsJump.SEARCH_KEY, title = SettingsSearchWords.LABEL,
            label = SettingsSearchWords.PLACEHOLDER, quotes = emptyList(),
            source = SCREEN,
        ),
    )

    /** The section keys that can be hidden by a search - everything but the box. */
    val SECTION_KEYS: Set<String> = ROWS.map { it.key }.toSet() - SettingsJump.SEARCH_KEY

    /** The row for a section key, or null for one this app does not draw. */
    fun row(key: String): Row? = ROWS.firstOrNull { it.key == key }

    /** What one section is searched by: its heading and then its own words. */
    fun wordsFor(key: String): String {
        val r = row(key) ?: return ""
        return listOf(r.title, r.label).plus(r.quotes).joinToString(" ")
    }

    /** The keys matching [query], in screen order. Empty query: nothing matched yet. */
    fun matching(query: String): List<String> {
        if (normalise(query).isEmpty()) return emptyList()
        return ROWS.map { it.key }.filter { matches(it, query) }
    }

    /**
     * Does this section match? THE one rule, and the same three steps as the
     * desktop's `rank` (`settings-search.js`): the heading is a stronger
     * match than the text, and both sides go through [normalise] first - so
     * "wi fi" finds "Wi-Fi" and "cafe" finds "café" on both apps.
     */
    fun matches(key: String, query: String): Boolean {
        val q = normalise(query)
        if (q.isEmpty()) return false
        val r = row(key) ?: return false
        if (normalise(r.title).contains(q)) return true
        return normalise(wordsFor(key)).contains(q)
    }

    /**
     * The same folding as the desktop's `normalise`: lower case, accents
     * dropped, every run of punctuation and space collapsed to one space.
     *
     * Kotlin has no Unicode normaliser in the standard library, so an
     * accented letter is folded by hand instead of by `NFD`. The page's own
     * accented words are few, and the ones that exist are named here rather
     * than pulled in as a dependency for four characters.
     */
    fun normalise(text: String): String {
        val folded = buildString(text.length) {
            for (ch in text.lowercase()) append(FOLD[ch] ?: ch)
        }
        return folded
            .map { if (it.isLetterOrDigit()) it else ' ' }
            .joinToString("")
            .split(' ')
            .filter { it.isNotEmpty() }
            .joinToString(" ")
    }

    /** Letters the app actually uses, and their unaccented forms. */
    private val FOLD: Map<Char, Char> = mapOf(
        'á' to 'a', 'à' to 'a', 'â' to 'a', 'ä' to 'a', 'ã' to 'a', 'å' to 'a',
        'é' to 'e', 'è' to 'e', 'ê' to 'e', 'ë' to 'e',
        'í' to 'i', 'ì' to 'i', 'î' to 'i', 'ï' to 'i',
        'ó' to 'o', 'ò' to 'o', 'ô' to 'o', 'ö' to 'o', 'õ' to 'o',
        'ú' to 'u', 'ù' to 'u', 'û' to 'u', 'ü' to 'u',
        'ç' to 'c', 'ñ' to 'n', 'ß' to 's',
        // The curly quotes and dashes the app's own strings use, so a pasted
        // word with a typographic apostrophe still matches.
        '’' to '\'', '‘' to '\'', '“' to ' ', '”' to ' ', '–' to ' ', '—' to ' ',
    )
}

/**
 * The words the search feature says, one copy per app. The desktop's
 * `settings-search.js` exports the same list, and `SettingsSearchTest` reads
 * both files and fails if any of them differs - so the two apps cannot
 * describe the same box in two different ways.
 */
object SettingsSearchWords {
    const val LABEL = "Search settings"
    const val PLACEHOLDER = "Search settings…"
    const val CLEAR = "Clear"
    const val HINT = "Type a word to show only the settings that match."

    /** Nothing matched. `{q}` is replaced with the words typed. */
    const val NONE = "Nothing here matches “{q}”."

    /** The line under it, so a miss never reads as "that setting does not exist". */
    const val NONE_BACK = "Clear the box and everything comes back."

    /** The live count. `{n}` is how many sections are left showing. */
    const val ONE = "1 setting matches."
    const val MANY = "{n} settings match."

    /** [HINT], [NONE] or a count - what the line under the box says. */
    fun line(query: String, shown: Int): String = when {
        query.isBlank() -> HINT
        shown == 0 -> ""
        shown == 1 -> ONE
        else -> MANY.replace("{n}", shown.toString())
    }

    /** The empty state's own words, quoting what was typed. */
    fun none(query: String): String = NONE.replace("{q}", query.trim())
}
