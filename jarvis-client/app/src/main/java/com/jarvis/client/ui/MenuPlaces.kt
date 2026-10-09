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
        "voice" to "settings.voice",
        "security" to "settings.security",
        "menu-visibility" to "settings.menu-visibility",
        "appearance" to "settings.appearance-card",
        "floating-avatar" to "settings.floating-avatar",
        "manner" to "settings.manner",
        "web-search" to "settings.web-search",
        "prompt-coach" to "settings.prompt-coach",
        "asks-first" to "settings.asks-first",
        "reach" to "settings.reach",
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
        "devices" to "settings.devices",
        "quick-tiles" to "settings.quick-tiles",
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
        "entry.voices" to "SettingsScreen: the Jarvis's voice button in the Voice item",
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
