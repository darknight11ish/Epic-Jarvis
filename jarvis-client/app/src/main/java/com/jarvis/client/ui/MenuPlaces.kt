package com.jarvis.client.ui

/**
 * Where each menu lives on the PHONE (docs/MENU-VISIBILITY-DESIGN.md sections 3e to 3g and 6),
 * by the `item(key = "...")` the screen draws it under. Pure - no Android - so
 * MenuVisibilityTest can hold it to the real screens' text and to the shared menu list:
 * a menu added to `backend/jarvis_menus.py` for the phone without a place here fails that test
 * rather than being silently un-hideable.
 *
 * Two jobs: (1) "open <a place>" by voice or chat ([com.jarvis.client.ui.OpenPlace]) to a
 * HIDDEN menu shows it for that visit only ([menuFor]); (2) the test's list of what is
 * drawn where. Nothing here decides who may hide what - that is
 * [com.jarvis.client.net.MenuLogic] and the never-hideable list.
 */
object MenuPlaces {

    /** SettingsScreen.kt `item(key = ...)` -> menu id. */
    val SETTINGS: Map<String, String> = mapOf(
        // The Voice item (SettingsScreen.kt, `item(key = "voice")`) holds TWO
        // hideable menus, and this map holds ONE id per item key. This line is
        // the item itself - the Voice section, `settings.voice`. The button
        // drawn INSIDE it, "Jarvis's voice" (`settings.voices`, read at
        // SettingsScreen.kt's `menus.shows("settings.voices")`), is in INSIDE
        // below, which is the place the phone-only `entry.voices` used to have
        // - now under the one id both apps use.
        //
        // Do NOT add a second `"voice" to ...` line here. `mapOf` takes a
        // duplicate key silently and keeps the LAST one, so the branch's
        // `"voice" to "settings.voices"` (2026-10-10) quietly deleted
        // `settings.voice` from this map and MenuVisibilityTest failed with
        // "no place in MenuPlaces for: [settings.voice, brain.work.briefing]".
        // A test below now fails on the duplicate line itself.
        "voice" to "settings.voice",
        "security" to "settings.security",
        "menu-visibility" to "settings.menu-visibility",
        "appearance" to "settings.appearance-card",
        // "Approval cards" (the owner's request of 2026-10-09): SettingsScreen
        // draws it behind `menus.shows("settings.approval-cards")` with a
        // MenuFrame of its own, so it needs a PLACE here - and its row would
        // otherwise be an undecided item key. MenuVisibilityTest checks both
        // halves, which is how the pair is kept in step.
        "approval-cards" to "settings.approval-cards",
        "floating-avatar" to "settings.floating-avatar",
        "manner" to "settings.manner",
        // "A new conversation starts after" (the audit of 2026-10-08): a
        // CLIENT-SIDE choice, so its row is this phone's own setting and its
        // menu id still needs a place here - MenuVisibilityTest fails without
        // this line, and the phone could otherwise not hide the row.
        "idle-new" to "settings.idle-new",
        "web-search" to "settings.web-search",
        "prompt-coach" to "settings.prompt-coach",
        "asks-first" to "settings.asks-first",
        "reach" to "settings.reach",
        // "Limits and frequency" (2026-10-08): the numbers the owner can change,
        // read and written through ONE table on the PC. SettingsScreen.kt draws
        // it behind `menus.shows("settings.limits")`; without this line the row
        // would have no PLACE and MenuVisibilityTest would say so, which is how
        // the pair is kept in step on both sides.
        "limits" to "settings.limits",
        "email-sending" to "settings.email-sending",
        "folders" to "settings.folders",
        "backup" to "settings.backup",
        "watch-notify" to "settings.watch-notify",
        "phone-notify" to "settings.phone-notify",
        "screen-look" to "settings.screen-look",
        "browser-engine" to "settings.browser-engine",
        // "When the phone does not answer" (2026-10-08): SettingsScreen.kt draws
        // it behind `menus.shows("settings.handoff")` with a MenuFrame of its
        // own, but without this line the new section had no PLACE here, so the
        // phone could not hide it and its row was an undecided item key -
        // MenuVisibilityTest caught both halves in CI.
        "handoff" to "settings.handoff",
        // "When a captcha stops Jarvis" (2026-10-09): SettingsScreen.kt draws it
        // behind `menus.shows("settings.handoff-front")` with a MenuFrame of its
        // own, and without this line the new section would have no PLACE here -
        // the phone could not hide it and its row would be an undecided item key
        // (MenuVisibilityTest checks both halves).
        "handoff-front" to "settings.handoff-front",
        "devices" to "settings.devices",
        "quick-tiles" to "settings.quick-tiles",
        // "Screen refresh rate" (2026-10-09): the panel's rate while Jarvis is
        // on screen. Its own row on the phone, and phone-only - there is no
        // desktop row to generate, because the desktop draws on a monitor whose
        // mode the Windows app already owns. Declared here rather than added to
        // MenuVisibilityTest's "not a menu" list, so the row is hideable like
        // every other section and the test's own rule is kept, not relaxed.
        "screen-rate" to "settings.screen-rate",
    )

    /** BrainScreen.kt `item(key = ...)` -> menu id (a key not listed is never hideable or is not a menu). */
    val BRAIN: Map<String, String> = mapOf(
        "doing" to "brain.now.right-now",
        "steps" to "brain.now.trace",
        "today" to "brain.work.today",
        "widgets" to "brain.work.widgets",
        "coming-up" to "brain.work.coming-up",
        "goals" to "brain.work.goals",
        "spending" to "settings.spending",
        "retirement" to "brain.work.retirement",
        "quiz" to "brain.work.quiz",
        "decks" to "brain.work.decks",
        "focus" to "brain.work.focus",
        "chatbot" to "brain.work.chatbot",
        "support" to "brain.work.support",
        // The Morning briefing plate is `brain.work.briefing` - BrainScreen.kt
        // guards this item with `menus.shows("brain.work.briefing")` and wraps
        // it in `MenuFrame(menus, "brain.work.briefing")`. The plate's
        // "When it arrives" half is a SECOND menu inside it,
        // `settings.briefing-settings`, and it is in INSIDE below. Pointing
        // this key at that half (as 2026-10-10 did) left the plate's own id
        // with no place at all.
        "briefing" to "brain.work.briefing",
        "progress" to "brain.projects.progress",
        "projects" to "brain.tab.projects",
        "attention" to "brain.now.budget",
        "jobs" to "brain.work.jobs",
        // The job list (2026-10-08, JARVIS-API section 118). Its own item key,
        // because it has to be drawn when there are no Long Fuse jobs at all,
        // but the same one menu decides both - they are two panes of the same
        // "what is the PC working on" answer, and hiding that hides both.
        "tasks" to "brain.work.jobs",
        "watch" to "brain.watch.watchlist",
        "initiative" to "brain.now.findings",
        "memory-counts" to "brain.memory.learning",
        "memory-auto" to "brain.memory.auto",
        "memory-profile" to "brain.memory.profile",
        "memory-shared" to "brain.memory.between-us",
        "topics" to "brain.memory.topics",
        "people-and-things" to "brain.memory.people-things",
        "history" to "entry.history",
        "forget-range" to "brain.history.forget-range",
        "memory" to "brain.memory.waiting",
        "wiki" to "brain.memory.wiki",
        "memory-as-of" to "brain.memory.as-of",
        "models" to "brain.model.models",
        "hardware" to "settings.hardware",
        "pc-help" to "brain.model.pc-help",
        "tutorials" to "brain.model.tutorials",
        "second-card" to "settings.second-card",
        "big-model" to "settings.big-model",
        "deep-questions" to "brain.memory.deep",
        "compute" to "brain.model.compute",
        "ledger" to "brain.trust.ledger",
        "skills" to "brain.model.skills",
        "capabilities" to "settings.backend-supports",
        "settings-entry" to "entry.settings",
    )

    /**
     * Menus drawn INSIDE another screen or item rather than under an item key of their own:
     * id -> where (a sentence; the test only needs the id to be listed).
     */
    val INSIDE: Map<String, String> = mapOf(
        "entry.appearance" to "HomeScreen: the Appearance button in the home row (six buttons since Settings joined it, 2026-10-08)",
        // "entry.voices" was here until 2026-10-10. It was one of TWO ids for
        // the same feature - this row and the desktop's own `settings.voices`
        // card - against backend/jarvis_menus.py's rule that one id means one
        // feature. The duplicate id is gone and the row KEEPS ITS PLACE HERE,
        // under the one id both apps use. It belongs in INSIDE and not in
        // SETTINGS: it is a button drawn inside the Voice item, so it has no
        // `item(key = ...)` of its own, and being in INSIDE is also what
        // exempts it from the MenuFrame rule (no screen wraps a button in one).
        "settings.voices" to "SettingsScreen: the Jarvis's voice button in the Voice item",
        // `settings.briefing-settings` (the parity audit of 2026-10-10): the
        // BOTH half of the morning briefing. The plate is `brain.work.briefing`
        // (BrainScreen.kt, item key "briefing"); this id hides only the "When
        // it arrives" block inside that plate (BriefingPlate.kt), which is why
        // it lives here rather than under the plate's own item key.
        "settings.briefing-settings" to "BriefingPlate: the When it arrives block inside the Morning briefing plate",
        // The other six of the eight ids the parity audit of 2026-10-10 turned
        // from desktop-only into features both apps have (`settings.voices` and
        // `settings.briefing-settings` are the two above). Every one of the
        // eight really is on the phone - that is what the correction says - and
        // none of them is drawn under an `item(key = ...)` of its own, so this
        // is where they belong. They are NOT hideable (`hide = false` in
        // backend/jarvis_menus.py, each with its own written reason), which is
        // why no screen reads `menus.shows(...)` for them and why
        // MenuVisibilityTest never asked for a place.
        //
        // `FindAnythingTest` reads this map too, and that is the point: the
        // phone's "Find anything" box lists what it can take the owner to, and
        // a menu drawn inside another card has no such place. A new phone menu
        // that is neither findable nor listed here fails that test by name, so
        // this map cannot quietly grow.
        //
        // Careful with the prose: `tools/check_feature_list.py` scans this file
        // for quoted menu ids, so a sentence that quotes one id and then
        // another as if it were a map entry is read as a menu id of its own and
        // fails that check. Naming ids in backticks, as above, is safe.
        "settings.animal-options" to "SettingsScreen: the animal options inside the Appearance item, which SETTINGS_ALIAS already opens for it",
        "settings.updates" to "ReadinessScreen: the Check for new versions row inside the This app card on Platform checks",
        "settings.about" to "FaqScreen: the About card at the end of Help",
        "brain.history.tags" to "HistoryScreen: the tag chips and the tag editor, which take that screen over",
        "brain.work.undo" to "InboxScreen: the undo shelf, above the Activity row",
        "brain.work.activity" to "InboxScreen: the Activity row, which opens Past approvals",
        "entry.voice-check" to "SettingsScreen: the Voice check button in the Voice item",
        "brain.history.tag-suggestions" to "HistoryTags: the last row, Suggest tags overnight",
        "settings.second-card.study-helper" to "SecondCardPlate: the Study helper switch",
        "settings.second-card.referee" to "SecondCardPlate: the Referee suggestions switch",
        "settings.second-card.third-card" to "SecondCardPlate: the Third graphics card section",
        "settings.second-card.chat-card" to "SecondCardPlate: the Everyday chat runs on row",
        "brain.work.quiz.youtube" to "QuizPlate: the YouTube link block",
    )

    /**
     * The menu a link should open for the visit: [screen] is the [Screen] name
     * (`SETTINGS` or `BRAIN`), [section] the item key OpenPlace sent, or null.
     */
    fun menuFor(screen: String, section: String?): String? {
        section ?: return null
        return when (screen) {
            "SETTINGS" -> SETTINGS[SETTINGS_ALIAS[section] ?: section]
            "BRAIN" -> BRAIN[section]
            else -> null
        }
    }

    /** OpenPlace sends the registry's ids; two of them are drawn under another item key. */
    val SETTINGS_ALIAS: Map<String, String> = mapOf(
        "appearance-card" to "appearance",
        "animal-options" to "appearance",
    )
}
