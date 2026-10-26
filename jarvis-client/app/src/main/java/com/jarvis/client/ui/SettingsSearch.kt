package com.jarvis.client.ui

/**
 * Search inside Settings - the phone's half of the desktop's search box
 * (`jarvis-desktop/src/settings-search.js`; `docs/SETTINGS-UX-DESIGN.md`).
 *
 * The owner's request of 2026-10-09: "a lot more visually simple, with a
 * search bar in settings. I still want everything adjustable, just easier to
 * find and more efficient." Settings had grown to twenty-one sections with a
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
 *  3. **The words really are the app's words.** Every `quotes` phrase and every
 *     `titles` name must appear in that section's own source, so an index
 *     cannot describe a screen that no longer exists. This is the phone's
 *     answer to the desktop's "the words are read off the page" - Compose
 *     cannot hand a test its rendered text, so the test reads the composables
 *     instead.
 *
 *  `titles` is the half of that which was missing until 2026-10-13, and the
 *  owner's own defect: the box knew a section's heading and its prose, and not
 *  the names of the switches drawn on it. Typing **"Hide memory lists and chat
 *  history"** - the switch's own words, four steps down in Security - answered
 *  **"Nothing here matches that."** (`SettingsSearchTest`'s "a switch is found
 *  by the words printed on it" measures exactly that, and its "the indexed
 *  switch names are the app's own, and no switch of theirs is missing" reads
 *  the named sources for every `SwitchRow(title = ...)` so a section cannot
 *  quietly grow a switch the index does not know.)
 *
 * It changes nothing: no section, switch or value is touched, and clearing
 * the box puts every row back. Nothing here calls the network or the desktop.
 *
 * HOW A QUERY MATCHES (2026-10-13). The box used to be one strict substring
 * test, so ONE typo found nothing: "notifcation" hid the very section it
 * should have found. It now tokenises the query, needs EVERY word typed to be
 * found (AND, not OR), ranks a heading word above a body word, and reaches
 * "the closest recognised wording" only as a last step after exact and prefix
 * have both failed - see [rank], [rankPart], [tokenTier] and [fuzzyHit], where
 * the four tiers, the edit-distance table and the two-character prefix guard
 * are written down with their reasons. This is the phone's half of the
 * owner's "find settings by the closest recognised wording" request; the
 * desktop's `rank` (`jarvis-desktop/src/settings-search.js`) carries the same
 * rule, and the SHARED fixture
 * (`jarvis-desktop/tests/fixtures/settings-search-cases.json`, generated from
 * the desktop engine) is read by [SettingsSearchTest] so the two cannot drift
 * on the rules - two clients that describe one box differently is the drift
 * this repository has already paid for once.
 */
object SettingsSearch {

    /**
     * One section, and the words a search may find it by.
     *
     * @param key the `item(key = ...)` `SettingsScreen.kt` draws it under.
     * @param title the section's own heading, in the app's words.
     * @param label extra words for the controls that have no heading of their
     *   own ("Train my voice", "Think through complex questions").
     * @param titles THE NAMES OF THE CONTROLS DRAWN UNDER THIS SECTION - the
     *   exact words a `SwitchRow`, a sub-section or a plate puts on the screen
     *   ("Hide memory lists and chat history", "Follow the system"). Each one
     *   must appear in [source] as the literal the control is really drawn
     *   with, so the index cannot quote a switch the screen no longer has.
     *   This is the field the defect of 2026-10-13 asked for: a switch was
     *   findable by the names Jarvis answers to and by the section's prose, and
     *   NOT by the words printed on it. Defaulted, so a row that draws no
     *   control of its own says nothing rather than an empty list twice.
     * @param quotes the detail sentences under those controls, the same
     *   words the screen shows. Each one must appear in [source].
     * @param source the files `SettingsSearchTest` looks for those titles and
     *   quotes in, and - for a row that names a switch - the files it reads to
     *   prove no switch of that section was left out of the index.
     */
    data class Row(
        val key: String,
        val title: String,
        val label: String,
        val titles: List<String> = emptyList(),
        val quotes: List<String>,
        val source: List<String>,
    )

    /** Where a title is checked, relative to `jarvis-client/.../com/jarvis/client/`. */
    private val SCREEN = listOf("ui/screens/SettingsScreen.kt")

    /**
     * The four ways a word typed can be found, strongest first - the same
     * numbers the desktop's `settings-search.js` uses (`EXACT`, `PREFIX`,
     * `FUZZY`, `DETAIL`), so a rank from either app means the same thing.
     * See [rank] for what each one matches.
     */
    private const val EXACT = 4
    private const val PREFIX = 3
    private const val FUZZY = 2
    private const val DETAIL = 1
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
            // The names the Security screen prints, in the order it draws them
            // (SecurityScreen.kt: app-lock, live-end, approvals, private,
            // method). "Hide memory lists and chat history" is the switch the
            // owner typed in full on 2026-10-13 and got "Nothing here matches
            // that" - the section's heading and prose never carried it, so the
            // very words on the screen could not find it. The two fingerprints
            // are the sub-headings the switches sit under, which is what he
            // called the place when he described it.
            titles = listOf(
                "App lock",
                "Lock Jarvis",
                "Fingerprint for approvals",
                "Fingerprint for private lists",
                "Hide memory lists and chat history",
                "What counts as you",
            ),
            quotes = listOf("Lock and fingerprint settings"),
            // The switches are DRAWN in SecurityScreen.kt, which is the file
            // their `title = "..."` literals live in - the same reason the
            // browser row names net/BrowserEngine.kt for its heading.
            source = SCREEN + listOf(PLATES + "SecurityScreen.kt"),
        ),
        // "App control" (the owner's decision of 2026-10-19: "enable
        // accessibility service with control by jarvis as an option in the
        // android app"). No `titles`: its one switch's title is drawn from
        // data/AppControl.kt's constants rather than a literal in the plate,
        // and the switch-name walk only covers the two rows it lists.
        Row(
            key = "app-control", title = "App control",
            label = "Accessibility service; let Jarvis control this phone; " +
                "apps Jarvis may act in; allow-list; one approval card per step",
            quotes = listOf(
                "Off by default. Jarvis can only act while this is on, only in the apps " +
                    "you add below, and only after you approve ONE step on your PC. " +
                    "Android's own Accessibility switch is separate and must be on too.",
            ),
            source = SCREEN + listOf(PLATES + "AppControlPlate.kt", "data/AppControl.kt"),
        ),
        Row(
            key = "menu-visibility", title = "Show or hide menus",
            // "Fold a card away" was the phrase here until 2026-10-13, found by
            // the sweep that followed the switch-title defect: no screen has
            // ever said it. The plate's own two states are `MenuWords.FOLDED_LINE`
            // ("Folded. Tap Open to see it.") and `MenuWords.STATE_EXPANDED`
            // ("Expanded"), so those are the words this row offers now, and
            // `source` names the plate they live in.
            label = "Hide a menu; show a menu; folded; expanded; the " +
                "three hidden - Show line",
            quotes = listOf("Show or hide menus"),
            source = JUMP + SCREEN + listOf(PLATES + "MenuVisibilityPlate.kt"),
        ),
        Row(
            key = "appearance", title = "Appearance",
            label = "Theme; colours; face; animal options; sharpness; frame rate",
            // The screen's own "More options" fold (AppearanceScreen.kt) plus
            // the face editor it draws (FaceEditor.kt). The device cards these
            // switches belong to are what makes "Follow the system" and
            // "Battery saver" findable here, where a person would look for them.
            titles = listOf(
                "Follow the system",
                "More options",
                "Make room for approvals",
                "Shrink the face while typing",
                "Follow the reply",
                "Face editor",
                "Auto adjust",
                "Battery saver",
            ),
            quotes = listOf(
                "Theme, the reactor's face, the animal options, and how it all looks.",
                "Pair with your desktop first - Appearance shares the face and ",
            ),
            source = SCREEN + listOf(PLATES + "AppearanceScreen.kt", PLATES + "FaceEditor.kt"),
        ),
        Row(
            // "Approval cards" (the owner's request of 2026-10-09: "a more simple
            // summary, with an explain more button ... and approval card
            // preferences such as this should be changeable in the settings").
            // The heading and both choice lines are net/CardSummary.kt's own
            // constants, so the quote is looked for there, like the browser
            // heading - and the value is the PC's, so the row is the same
            // setting on the desktop.
            key = "approval-cards", title = "Approval cards",
            label = "Explain more; the short summary; the whole card; how much of a card " +
                "is shown; always show everything; start short",
            quotes = listOf("Nothing is hidden from you - it is one tap away."),
            source = JUMP + listOf("net/CardSummary.kt", PLATES + "ApprovalCardsPlate.kt"),
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
            label = "Search providers; SearXNG; DuckDuckGo; Exa; Tavily; Brave; DeepSeek; API keys",
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
            // "Notifications from Jarvis" (the owner's decision of 2026-10-09):
            // one line and one button into Android's own per-app notification
            // screen, which is where this phone's per-kind switches really are.
            key = "jarvis-notify", title = "Notifications from Jarvis",
            label = "Android's own notification switches; alarms; reminders; approvals; " +
                "which kinds this phone shows",
            quotes = listOf(
                "Android decides whether this phone shows what Jarvis sends from your ",
            ),
            source = JUMP + listOf(PLATES + "JarvisNotifyPlate.kt"),
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
            // What a captcha does about the browser window it is blocking (the
            // owner's decision of 2026-10-09). Its heading and both choice lines
            // are net/HandoffFront.kt's own constants, so the quote is looked
            // for there, like the browser heading.
            key = "handoff-front", title = "When a captcha stops Jarvis",
            // Both choice lines are `HandoffFront.LEAVE_IN_PLACE_LABEL` and
            // `BRING_TO_FRONT_LABEL` word for word, so the words the box answers
            // to are the words the two buttons carry ("Leave it where it is" -
            // the index used to say "leave the window where it is", which no
            // screen has ever printed).
            label = "A captcha or a sign-in page blocking a window; leave it where it is; " +
                "bring it to the front",
            quotes = listOf("When a captcha stops Jarvis"),
            source = JUMP + listOf("net/HandoffFront.kt"),
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
        Row(
            // "Screen refresh rate" (2026-10-09): the rate the PANEL is asked to
            // run at while Jarvis is on screen (ui/screens/ScreenRatePlate.kt,
            // data/ScreenRate.kt). Phone-only - the panel's own modes come from
            // this phone's Display API, so there is no desktop row to copy words
            // from - and NOT the animal's frame rate, which is how often the
            // animal is DRAWN; ScreenRate.kt's own doc says why the two must
            // never be merged.
            key = "screen-rate", title = "Screen refresh rate",
            label = "The panel's refresh rate while Jarvis is on screen; follow the phone; " +
                "60, 90 or 120; asks the screen, never changes your phone's own display setting, " +
                "and says when the rate did not take effect",
            quotes = listOf(
                // `ScreenRate.HONEST_NOTE` and `ScreenRate.BATTERY_NOTE`, which the
                // plate shows as they are - so the quotes are looked for in the
                // module that owns them, the way the browser row names
                // net/BrowserEngine.kt. Both are written as two literals there;
                // wordsOf folds them back into one sentence.
                "While Jarvis is on screen, Jarvis asks the screen for this rate. It cannot change " +
                    "your phone's own display setting - that belongs to the phone, and only the " +
                    "phone's own Settings or a system app can change it. If the screen does not " +
                    "take the rate, this screen will say so.",
                "A higher refresh rate uses more battery. The screen redraws more often, and that " +
                    "is power the phone spends whether or not anything on it is moving.",
            ),
            source = JUMP + listOf("data/ScreenRate.kt", PLATES + "ScreenRatePlate.kt"),
        ),
        Row(
            // The PC's own limit table, on the phone (LimitsPlate.kt; the
            // owner's decision of 2026-10-08). It is the last section on the
            // screen, so it is last here too.
            key = "limits", title = "Limits and how often Jarvis does things",
            label = "How much Jarvis does at once; how long you can undo; how long it waits " +
                "before it reads something of yours; changing something here may take " +
                "effect at once or ask you on the PC first",
            // The heading and both sentences are `net/Limits.kt`'s own
            // constants - the plate draws them rather than writing its own -
            // so the quotes are looked for there, like the browser heading.
            //
            // The second quote is `LOOSEN_NOTE` as it reads now. It used to say
            // "Turning something up asks you on the PC first", which stopped
            // being true of every row under it: on the voice check's bar it is
            // *lowering* the bar that asks (a lower bar means more clips count
            // as the owner's voice), so the line above the rows had to say only
            // what holds for all of them. The screen changed and this index did
            // not, which is the drift `SettingsSearchTest` exists to catch - it
            // caught it on `main` on 2026-10-10.
            //
            // The same sentence was still in this row's `label`, as the
            // paraphrase "turning something up asks you on the PC" - the old
            // `LOOSEN_NOTE`, one wording behind, and no screen says it any more.
            // Found on 2026-10-13 by the sweep that followed the switch-title
            // defect, and replaced with the line the plate really carries, so
            // the words the box answers to are the words the section prints.
            // (No test holds the rest of `label` this way - see the note above
            // the typo contract in `SettingsSearchTest` for why that check
            // cannot be written honestly.)
            quotes = listOf(
                "How much Jarvis does at once, how long you can undo, and how long it waits before it ",
                "Changing something here may take effect at once or ask you on the PC first, and " +
                    "nothing changes until you answer there.",
            ),
            source = JUMP + listOf("net/Limits.kt"),
        ),
    ) + listOf(
        // The search box itself is a `LazyColumn` item, so SettingsJumpTest
        // sees it as a row; it is a control, not a section, and it is never
        // filtered out (there would be no way back to the box).
        Row(
            // "A new conversation starts after ..." (the audit of 2026-10-08): a
            // CLIENT-SIDE choice saved on this phone only, so its heading is
            // ChatHistory's own constant. It is the last section the screen
            // draws, so it is last here too - under "limits", as on the screen.
            key = "idle-new", title = "A new conversation starts after",
            label = "How long a chat can sit idle before the next message starts a new one",
            quotes = listOf("A new conversation starts after"),
            source = JUMP + listOf("net/ChatHistory.kt"),
        ),
        Row(
            // "Data and maths sandbox" (LM-1C, 2026-10-18): the switch that
            // offers the small read-only Python tool to the AI model. The
            // section's heading is SandboxExec's own constant, so the quote is
            // looked for there rather than in the plate.
            key = "sandbox", title = "Data and maths sandbox",
            label = "Python; maths; data; sums; averages; script; sandbox; sandboxed code",
            quotes = listOf("Data and maths sandbox"),
            source = JUMP + listOf("net/SandboxExec.kt"),
        ),
        Row(
            // "First-time setup" (S2, 2026-10-20; JARVIS-API section 147): the
            // PC's fourteen questions and its READ-ONLY plan. The heading, the
            // kicker and the "changes are made on the PC" line are
            // SetupQuestionnaire's own constants, so the quotes are looked for
            // there.
            key = "setup-questionnaire", title = "First-time setup",
            label = "Setup questionnaire; first-time setup; how Jarvis behaves; starting out; " +
                "recommended setup; what would change",
            quotes = listOf(
                "Fourteen questions about how you want Jarvis to behave.",
                "This screen only shows what your answers would change.",
            ),
            source = JUMP + listOf("net/SetupQuestionnaire.kt"),
        ),
        Row(
            // "All features and abilities" (2026-10-22): the phone directory of
            // the 140 features, in the PC's five labels (FeatureDirectory.kt is
            // GENERATED from contract/feature-controls.json by
            // jarvis-client/tools/gen_feature_directory.py).
            key = "all-features", title = "All features and abilities",
            label = "All features; abilities; what can Jarvis do; feature list; " +
                "typed commands; switches; safety rules; where to change a setting; " +
                // The BOOL_SETTINGS names that have no Settings row of their own
                // on the phone: Brain (memory/history), a plate, or the PC. The
                // directory says where each one lives, so typing its name finds
                // that answer instead of "Nothing here matches that" (2026-10-22).
                "background learning; sensitive topics; ask before every search; " +
                "sandbox; media index; searchable recordings; pictures; briefing " +
                "senders; big coder; big model; alarm sounds; reminder sounds; " +
                "briefing notification; handoff notification; quiet hours; voice " +
                "follows the face; better voice; write like me; second card; " +
                // The phone-owned gaps: browser-engine and the notification rows.
                "browser without a window; windowless browser; Obscura; browser " +
                "engine; phone notifications; smartwatch notifications; watch " +
                "notifications; notifications on a watch",
            quotes = listOf(
                "All features and abilities",
                "Every feature Jarvis knows about, in the PC's own words.",
            ),
            // The quotes live in the plate; PLATES is the plates' folder and the
            // source list is relative to it, so the folder prefix is not itself
            // an entry.
            source = listOf(PLATES + "FeatureDirectoryPlate.kt"),
        ),
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

    /** What one section is searched by: its heading, its own words, and the words it prints. */
    fun wordsFor(key: String): String {
        val r = row(key) ?: return ""
        return listOf(r.title, r.label).plus(r.titles).plus(r.quotes).joinToString(" ")
    }

    /** The keys matching [query], in screen order. Empty query: nothing matched yet. */
    fun matching(query: String): List<String> {
        if (normalise(query).isEmpty()) return emptyList()
        return ROWS.map { it.key }.filter { matches(it, query) }
    }

    /**
     * Does this section match, and how strongly? The same four numbers as the
     * desktop's `rank` (`jarvis-desktop/src/settings-search.js`), because the
     * two apps must not describe one search box in two different ways:
     *
     *  - **4 EXACT** - a word typed IS one of the heading's own words
     *    ("voice" finds "Voice");
     *  - **3 PREFIX** - a word typed starts one of the heading's words
     *    ("voic" finds "Voice");
     *  - **2 FUZZY** - a word typed is a near miss of one of the heading's
     *    words ("voise" finds "Voice");
     *  - **1 DETAIL** - a word typed is found in the section's own text at
     *    large, the heading's words included ("search" finds "Web search");
     *  - **0** - no match.
     *
     * A section's rank is the WEAKEST of its words typed (see [tokens]), so
     * one exact word beside one near miss ranks as the near miss, and one word
     * finding nothing makes the whole query find nothing: typing more words
     * narrows, never widens. That is what keeps the heading stronger than the
     * body - a heading word is worth 4, 3 or 2 where the same word in a
     * paragraph is worth 1.
     *
     * Both sides go through [normalise] first, so "wi fi" finds "Wi-Fi" and
     * "cafe" finds "café" on both apps.
     */
    fun rank(key: String, query: String): Int {
        val r = row(key) ?: return 0
        return rankPart(
            r.title,
            r.label + " " + r.titles.joinToString(" ") + " " + r.quotes.joinToString(" "),
            query,
        )
    }

    /**
     * [rank]'s rule on one part named by its words rather than by a section
     * key: `label` is the heading side, `text` everything else the part says.
     * It is the same shape as the desktop's `rank(label, text, query)`, which
     * is what lets the phone be held to the shared cross-app fixture
     * (`jarvis-desktop/tests/fixtures/settings-search-cases.json`) - a fixture
     * of made-up parts has no settings key to look up.
     */
    fun rankPart(label: String, text: String, query: String): Int {
        val tokens = tokens(query)
        if (tokens.isEmpty()) return 0
        val heading = normalise(label)
        val detail = normalise(text)
        var weakest = EXACT
        for (token in tokens) {
            val tier = tokenTier(token, heading, detail)
            if (tier == 0) return 0
            if (tier < weakest) weakest = tier
        }
        return weakest
    }

    /**
     * Does this section match the query at all? True when [rank] is above
     * zero - the four tiers are [rank]'s job, and [matching] uses it only to
     * keep the section.
     */
    fun matches(key: String, query: String): Boolean = rank(key, query) > 0

    /** The query's words, already folded: the query side of the rule. */
    private fun tokens(query: String): List<String> =
        normalise(query).split(' ').filter { it.isNotEmpty() }

    /** The words of one side of a section, already folded. */
    private fun words(text: String): List<String> =
        normalise(text).split(' ').filter { it.isNotEmpty() }

    /**
     * The best ONE word typed can do against ONE section: a tier, or 0.
     *
     * The heading's own words are tried first and are worth the most. The
     * detail side is the floor, and it is two separate tests, exactly as the
     * desktop's `tokenTier` has them: the word typed is one of the detail's
     * whole words, or it is a near miss of one. It is NOT "the detail text
     * contains these letters", which the box used to do and which is a
     * footgun on short tokens - "voice" appeared inside "conVersation" and
     * showed a card about starting a new conversation. Matching the suffix of
     * an unrelated word is the behaviour "find by the closest recognised
     * wording" replaces, so it is deliberately gone.
     */
    private fun tokenTier(token: String, heading: String, detail: String): Int {
        val names = words(heading)
        if (names.contains(token)) return EXACT
        if (names.any { it.startsWith(token) }) return PREFIX
        if (names.any { fuzzyHit(token, it) }) return FUZZY
        val body = words(detail)
        if (body.contains(token)) return DETAIL
        if (body.any { fuzzyHit(token, it) }) return DETAIL
        return 0
    }

    /**
     * [tokenTier] pointed at one word a caller names, so a test can ask what
     * "cat" does against "chat" without the app having to say "chat" on any
     * of its screens. Both sides are folded first.
     */
    fun wordMatches(queryToken: String, word: String): Boolean =
        tokenTier(normalise(queryToken), normalise(word), "") > 0

    /**
     * The typo step: the last thing tried, and only after equal and prefix
     * have both failed.
     *
     * It allows an edit distance (insert, delete or substitute - plus ONE
     * transposition of two touching letters, counted as one edit, so "voise"
     * for "voice" is a single mistake) of:
     *
     *  - **0 for tokens of 1-3 characters**: one edit in "cat" is "chat",
     *    "cut", "car" or "at", so any tolerance at this length turns a short
     *    word into a different one;
     *  - **at most 1 for 4-7 characters**: long enough that one mistake is
     *    still recognisably the same word;
     *  - **at most 2 for 8 or more**: a long word can carry two and stay
     *    itself, and at this length two edits are a small fraction of it.
     *
     * PLUS THE PREFIX GUARD: the token and the word must agree on their
     * FIRST TWO CHARACTERS. That is what stops "cat" ever reaching "chat"
     * (the distance is 1 as well, but a short token is refused by the table;
     * the guard is what keeps whole families of unrelated words apart) and
     * keeps "backup" from leaping to "pack up" or "security" from matching a
     * word that merely shares its shape further in. Typing the first two
     * letters right is the cheapest evidence a person means this word.
     *
     * A word shorter than the token is never a fuzzy match: with the prefix
     * guard in place its distance is always at least the length gap, which the
     * table above already refuses. The check says so out loud rather than
     * leaning on the arithmetic.
     */
    private fun fuzzyHit(token: String, word: String): Boolean {
        val tank = when {
            token.length >= 8 -> 2
            token.length >= 4 -> 1
            else -> 0
        }
        if (tank == 0) return false
        if (token.length < 2 || word.length < 2) return false
        if (token[0] != word[0] || token[1] != word[1]) return false
        if (word.length < token.length) return false
        return typoDistance(token, word) <= tank
    }

    /**
     * Edit distance where insert, delete and substitute cost 1 and ONE
     * transposition of two touching characters also costs 1 - the true
     * Damerau-Levenshtein distance, not the cheaper "did the pair sit next to
     * each other on the diagonal" form. The difference is real and was caught
     * here: that cheaper form reads "securtiy" -> "security" as two edits
     * (substitute, substitute) and refuses it, because the pair is transposed
     * across the far side of a longer word. A swapped pair is one mistake
     * wherever it sits, so the matrix keeps each letter's last row and looks
     * a transposition up there.
     *
     * Written out rather than pulled in: the file stays pure, adds no
     * dependency, and is short enough to read.
     */
    private fun typoDistance(a: String, b: String): Int {
        val rows = Array(a.length + 2) { IntArray(b.length + 2) }
        val edge = a.length + b.length
        rows[0][0] = edge
        for (i in 0..a.length) {
            rows[i + 1][0] = edge
            rows[i + 1][1] = i
        }
        for (j in 0..b.length) {
            rows[0][j + 1] = edge
            rows[1][j + 1] = j
        }
        // The ROW each letter of `b` was last seen on - a row index, not a
        // column. That is what the swap term needs (`rows[same]`), and it is
        // safe to look up because it is only ever written at the end of a row
        // that has already been filled in. An earlier version stored the
        // COLUMN and blew up on "notifcation" against "notifications":
        // `lastB['s']` still held 14 from the row above while the matrix had
        // only 13 rows.
        val lastRowOf = HashMap<Char, Int>()
        for (i in 1..a.length) {
            // The column where THIS row last matched, for the swap's column.
            var lastMatch = 0
            for (j in 1..b.length) {
                val same = lastRowOf[b[j - 1]] ?: 0
                val other = lastMatch
                var cost = 1
                if (a[i - 1] == b[j - 1]) {
                    cost = 0
                    lastMatch = j
                }
                rows[i + 1][j + 1] = minOf(
                    rows[i][j] + cost, // substitute or keep the letter
                    rows[i + 1][j] + 1, // insert
                    rows[i][j + 1] + 1, // delete
                    // Swap the pair: the letters between the two rows and the
                    // two columns are deleted and inserted, and the swap costs 1.
                    rows[same][other] + (i - same - 1) + 1 + (j - other - 1),
                )
            }
            lastRowOf[a[i - 1]] = i
        }
        return rows[a.length + 1][b.length + 1]
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
