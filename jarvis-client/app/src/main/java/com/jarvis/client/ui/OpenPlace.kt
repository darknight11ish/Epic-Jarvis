package com.jarvis.client.ui

/**
 * Where "open <a settings section>" goes ON THE PHONE.
 *
 * Saying "open help", "the FAQ", "connection", "morning briefing", "about"
 * or "Jarvis's voices" (jarvis_settings_registry.py's `SECTIONS`,
 * docs/JARVIS-API.md section 58.1) used to open the phone's Settings screen
 * at the top, every time (phone walk-through, 2026-09-27): the backend
 * names one section id for both apps, and the phone only knew the ids of
 * the rows on its own Settings screen. Many of those places live somewhere
 * else on the phone - Help, Checks, Brain, "Jarvis's voice" - and a few do
 * not exist on the phone at all.
 *
 * So each id the registry can send now has a decision here, made once:
 *  - [Where.Go]: the phone's own screen for it, and the item on that screen
 *    to bring into view (its `item(key = ...)`), or null for the top.
 *  - [Where.OnPc]: there is no phone equivalent. The phone says so in one
 *    plain sentence instead of opening a screen that does not have it.
 *
 * **Since F6 (2026-11-03) the same closed decision table also names whole
 * SCREENS and MENUS, not only settings sections.** The PC's deterministic
 * "open <a place>" quick path (jarvis_quick.py, section 58.1) used to answer
 * only with settings-section ids; an id naming a place of its own - "chat",
 * "live", "memory", "history", "approvals", "appointments" - used to land at
 * the top of Settings, which has none of them. The ids are resolved in this
 * order, and each step is tested:
 *  1. [PLACES] - the settings-registry ids this file has always decided;
 *  2. [AREAS] - a screen id or a place name ("chat", "live", "memory", ...);
 *  3. the shared MENU ids from [MenuPlaces] ("settings.voice",
 *     "brain.memory.waiting") - the same ids `backend/jarvis_menus.py`
 *     exports, so "open the web-search menu" can name the row directly;
 *  4. [PHONE_MISSING] - a real place this build of the app has no screen for
 *     yet: the honest refusal, never a wrong screen (habits, mood, plugins);
 *  5. [PC_ONLY] - a place only the desktop app has at all;
 *  6. anything newer: the old, harmless behaviour - open Settings, which
 *     scrolls nowhere for an id it has no row for.
 * Nothing new is added to the [Screen] enum for this, and no second
 * navigation mechanism: MainActivity's existing `openSettings` one-time
 * request carries the id here and `initialSection` scrolls the screen.
 *
 * Pure - no Android - so `OpenPlaceTest` can hold it to the registry's real
 * list: a section added there without a decision here fails that test
 * rather than quietly landing at the top of Settings again. Pure navigation
 * either way: nothing here changes a setting.
 */
object OpenPlace {

    sealed interface Where {
        /** Open [screen], and bring the item keyed [section] into view (null: the top). */
        data class Go(val screen: Screen, val section: String?) : Where

        /** Nothing like it on the phone - show [notice] and stay where we are. */
        data class OnPc(val notice: String) : Where
    }

    /** The one sentence for a place that exists only in the PC app. */
    const val ON_PC =
        "That setting is only in Jarvis on your PC, not on this phone. Open Jarvis on your PC to change it."

    /**
     * Every registry id with a place of its own on the phone, and the item
     * key there. Settings' own rows keep their ids unchanged: they are
     * SettingsScreen.kt's `SETTINGS_ITEM_INDEX` keys, as before.
     */
    private val PLACES: Map<String, Where.Go> = mapOf(
        // Settings' own rows (SettingsScreen.kt, SETTINGS_ITEM_INDEX).
        "voice" to Where.Go(Screen.SETTINGS, "voice"),
        "security" to Where.Go(Screen.SETTINGS, "security"),
        "appearance-card" to Where.Go(Screen.SETTINGS, "appearance-card"),
        // "Animal options" is a card of its own on the desktop; on the phone it
        // is inside Appearance, so the same row is where it opens.
        "animal-options" to Where.Go(Screen.SETTINGS, "appearance-card"),
        // "Approval cards" (the owner's request of 2026-10-09): its own row on
        // Settings, right under Appearance, and the setting itself is the PC's
        // (GET/POST /api/card-prefs) - so "open approval cards" lands on the
        // row that changes it.
        "approval-cards" to Where.Go(Screen.SETTINGS, "approval-cards"),
        // "File from your PC" (2026-10-31): its own row on the phone's Settings
        // screen, keyed "files" - so "open my files" / "what did Jarvis send me"
        // lands on the row that lists the one approved file.
        "files" to Where.Go(Screen.SETTINGS, "files"),
        // "Protected from Jarvis" (2026-10-31): its own row on the phone's
        // Settings screen, keyed "protection" like the desktop card's id, so
        // "open protected from jarvis" lands on the row that reads the list.
        "protection" to Where.Go(Screen.SETTINGS, "protection"),
        // "The local model" (2026-10-31): the automatic-restart sentence and
        // switch moved off Home into this Settings card.
        "model-lane" to Where.Go(Screen.SETTINGS, "model-lane"),
        "manner" to Where.Go(Screen.SETTINGS, "manner"),
        "web-search" to Where.Go(Screen.SETTINGS, "web-search"),
        // The prompt coach's master switch (docs/PROMPT-COACH-DESIGN.md,
        // docs/JARVIS-API.md section 119): its own row on Settings.
        "prompt-coach" to Where.Go(Screen.SETTINGS, "prompt-coach"),
        "asks-first" to Where.Go(Screen.SETTINGS, "asks-first"),
        "reach" to Where.Go(Screen.SETTINGS, "reach"),
        "email-sending" to Where.Go(Screen.SETTINGS, "email-sending"),
        "folders" to Where.Go(Screen.SETTINGS, "folders"),
        "backup" to Where.Go(Screen.SETTINGS, "backup"),
        "watch-notify" to Where.Go(Screen.SETTINGS, "watch-notify"),
        "phone-notify" to Where.Go(Screen.SETTINGS, "phone-notify"),
        // "Notifications" (2026-10-29, the settings wrong-app audit's finding 7):
        // the registry now says this section is on BOTH apps, because the phone
        // changes the PC's own seven notification kinds in its "Notifications
        // from Jarvis" row (SettingsScreen.kt's PcNotifySection, every line saying
        // "(on your PC)"). So "open notifications" lands on that row rather than
        // answering "only in Jarvis on your PC" - which is what it used to do
        // while `notifications` sat in PC_ONLY.
        "notifications" to Where.Go(Screen.SETTINGS, "jarvis-notify"),
        // "Look at this and Watch with me": picture mode's switch (2026-09-29).
        "screen-look" to Where.Go(Screen.SETTINGS, "screen-look"),
        // The headless browser (Obscura): its switch, default and install line (2026-09-29).
        "browser-engine" to Where.Go(Screen.SETTINGS, "browser-engine"),
        // "When the phone does not answer" (2026-10-08): the registry's own
        // Section for the captcha hand-off. It is an ordinary Settings row on
        // the phone (SettingsScreen.kt, item "handoff"), which is what makes
        // "open the captcha hand-off" land on it instead of the top of Settings
        // - OpenPlaceTest's new-section check is what caught it missing.
        "handoff" to Where.Go(Screen.SETTINGS, "handoff"),
        // "When a captcha stops Jarvis" (2026-10-09): the registry's own Section
        // for what a captcha does about the browser window it is blocking. An
        // ordinary Settings row on the phone (SettingsScreen.kt, item
        // "handoff-front"), which is what makes "open the captcha window
        // setting" land on it instead of the top of Settings -
        // OpenPlaceTest's new-section check is what caught it missing for the
        // row above.
        "handoff-front" to Where.Go(Screen.SETTINGS, "handoff-front"),
        // Settings -> Devices (docs/PAIRING-DESIGN.md section 7.2).
        "devices" to Where.Go(Screen.SETTINGS, "devices"),
        // The phone's Quick Settings tiles (SettingsScreen.kt, item "quick-tiles").
        "quick-tiles" to Where.Go(Screen.SETTINGS, "quick-tiles"),
        // "Screen refresh rate" (2026-10-09): the panel's rate while Jarvis is
        // on screen. Phone-only - the registry marks it app="phone" - and an
        // ordinary Settings row (SettingsScreen.kt, item "screen-rate"), so
        // "open the screen refresh rate" lands on it rather than the top of
        // Settings. OpenPlaceTest's new-section check is what would catch it
        // missing.
        "screen-rate" to Where.Go(Screen.SETTINGS, "screen-rate"),
        // Floating Jarvis (SettingsScreen.kt, item "floating-avatar", saved on
        // this phone only). It is a registry Section since 2026-10-08 - before
        // that "open Floating Jarvis" answered with the raw id - and
        // OpenPlaceTest requires every phone-relevant Section to have a place
        // here, which is what caught this missing line in CI.
        "floating-avatar" to Where.Go(Screen.SETTINGS, "floating-avatar"),
        // "Picture-in-picture" (2026-10-30, docs/PIP-DESIGN.md): the phone-only
        // Settings row (SettingsScreen.kt, item "pip-mode") for the small window
        // that stays over other apps. A registry Section since this slice, so
        // "open picture-in-picture" lands on the row rather than the top of
        // Settings - OpenPlaceTest's new-section check is what requires this
        // line for every Section.
        "pip-mode" to Where.Go(Screen.SETTINGS, "pip-mode"),
        // Hidden navigation menus section (SettingsScreen.kt, item "menu-visibility").
        "menu-visibility" to Where.Go(Screen.SETTINGS, "menu-visibility"),
        // "Limits and how often Jarvis does things" (2026-10-08): the PC's own
        // backend/jarvis_limits.py table, as a Settings row of its own on the
        // phone (SettingsScreen.kt, item "limits"; LimitsPlate.kt). So "open
        // limits" lands on it instead of the top of Settings.
        "limits" to Where.Go(Screen.SETTINGS, "limits"),
        // "To-do list carry-over" (2026-11-02, the todo-carry-over lane;
        // JARVIS-API section 179): a card of its own in the PC's Settings, and on
        // the phone the same two choices are drawn INSIDE the "Limits and how
        // often Jarvis does things" row (SettingsScreen.kt's
        // TodoCarryoverSection, right under LimitsSection; TodoCarryoverPlate.kt).
        // So "open the to-do list carry-over" lands on that row - there is no
        // `todo-carryover` item key of its own, and none is owed: the control is
        // drawn one tap inside it, from the same PC route.
        "todo-carryover" to Where.Go(Screen.SETTINGS, "limits"),
        // "A new conversation starts after" (the audit of 2026-10-08): a
        // CLIENT-SIDE choice with its own Settings row on the phone
        // (SettingsScreen.kt, item "idle-new"; IdleNewPlate.kt), so "open a new
        // conversation starts after" lands on it rather than the top of
        // Settings. OpenPlaceTest's own new-section check is what requires a
        // decision here for every registry Section.
        "idle-new" to Where.Go(Screen.SETTINGS, "idle-new"),
        // "Data and maths sandbox" (LM-1C, 2026-10-18): the registry's own
        // Section for the switch that offers the small read-only Python tool to
        // the AI model. An ordinary Settings row on the phone
        // (SettingsScreen.kt, item "sandbox"), so "open the data sandbox" lands
        // on it instead of the top of Settings.
        "sandbox" to Where.Go(Screen.SETTINGS, "sandbox"),
        // "Learning" (2026-10-28, the settings audit's G1): the two learning
        // switches now have their own Settings row on both apps
        // (SettingsScreen.kt, item "learning"), so "open learning" lands on it
        // rather than the top of Settings. Before this the section did not
        // exist and the switches could only be found in the Brain.
        "learning" to Where.Go(Screen.SETTINGS, "learning"),
        // "First-time setup" (S2, 2026-10-20; JARVIS-API section 147): the PC's
        // fourteen questions and its read-only plan. An ordinary Settings row
        // on the phone (SettingsScreen.kt, item "setup-questionnaire", always
        // drawn), so "open first time setup" lands on it rather than the top of
        // Settings; the changes themselves are made on the PC.
        "setup-questionnaire" to Where.Go(Screen.SETTINGS, "setup-questionnaire"),
        // "All features and abilities" (2026-10-22, #749): the phone's own
        // directory row (SettingsScreen.kt, item "all-features"), so "open all
        // features and abilities" lands on it. A PHONE-ONLY registry Section:
        // the desktop's directory card has no id of its own (it is a generated
        // read-only index, not a settings section), so there is no desktop row
        // for this id to name. It changes nothing - the screen only lists.
        "all-features" to Where.Go(Screen.SETTINGS, "all-features"),
        // "Jarvis Calendar" (2026-10-29; the owner's ask: a full calendar of
        // Jarvis's own, ON by default and disableable): its one Settings row is
        // the feature's own ON/OFF switch (SettingsScreen.kt, item "calendar",
        // always drawn; CalendarSettingsPlate.kt), so "open the calendar" - and
        // the calendar widget's off-state tap - land on it rather than at the
        // top of Settings. A PHONE-ONLY registry Section in this slice: the
        // desktop's own Settings card arrives with the HUD half of the feature.
        "calendar" to Where.Go(Screen.SETTINGS, "calendar"),
        // "Platform checks": its Connection card, and "This app" with the
        // phone's own "Check for new versions" (the desktop's "updates" card
        // is the desktop app's; this is the nearest thing the phone has).
        "connection" to Where.Go(Screen.CHECKS, "connection"),
        "updates" to Where.Go(Screen.CHECKS, "this-app"),
        // Help: the FAQ, and "About Jarvis" at its end (FaqScreen.kt).
        "faq" to Where.Go(Screen.FAQ, null),
        "about" to Where.Go(Screen.FAQ, "about"),
        // "Jarvis's voice" - custom voices, its own screen (VoicesScreen.kt).
        "voices" to Where.Go(Screen.VOICES, null),
        // Brain (BrainScreen.kt). The registry marks hardware, second-card,
        // big-model and backend-supports "desktop" only, but the phone's
        // Brain has a plate for each of them - "backend-supports" is its
        // "This backend" plate, keyed "capabilities".
        "briefing-settings" to Where.Go(Screen.BRAIN, "briefing"),
        "hardware" to Where.Go(Screen.BRAIN, "hardware"),
        // Focus presets are drawn INSIDE the phone's Hardware plate
        // (HardwarePlate.kt's FocusPresetsSection), so "open focus presets"
        // lands on that plate rather than the top of Settings.
        "focus-presets" to Where.Go(Screen.BRAIN, "hardware"),
        "second-card" to Where.Go(Screen.BRAIN, "second-card"),
        "big-model" to Where.Go(Screen.BRAIN, "big-model"),
        "backend-supports" to Where.Go(Screen.BRAIN, "capabilities"),
        // Spending summaries (2026-10-08): the phone draws this plate itself
        // (BrainScreen.kt `item(key = "spending")`, menu "settings.spending",
        // which `contract/menu-cases.json` marks available on the phone). It
        // sat in [PC_ONLY] instead, so "open spending" answered "only in
        // Jarvis on your PC" with the plate one tap away.
        "spending" to Where.Go(Screen.BRAIN, "spending"),
        // "Pictures" (the owner's decision of 2026-09-27; JARVIS-API section
        // 129): the registry's Section for "Making pictures" is a CARD on the
        // PC's Settings screen - the switch, the drawing program and the folder
        // are the PC's own and the backend refuses them from the phone. The
        // phone's half of the feature IS the gallery, drawn on the Brain
        // (BrainScreen.kt `item(key = "pictures")`, PicturesPlate.kt), so "open
        // my pictures" lands there rather than on the top of Settings. This
        // line is what OpenPlaceTest's new-section check requires.
        "pictures" to Where.Go(Screen.BRAIN, "pictures"),
        // "Forget a time frame" (2026-09-28): not a settings section - the
        // place "forget what you learned last week" opens, named by the
        // answer's `open_brain` (net/ForgetRange.kt, ChatSession).
        com.jarvis.client.net.ForgetRange.PLACE to Where.Go(Screen.BRAIN, "forget-range"),
        // "Switch off my work topic" (2026-09-30): not a settings section - the place
        // named by the answer's `open_brain` (net/Topics.kt, ChatSession).
        com.jarvis.client.net.Topics.PLACE to Where.Go(Screen.BRAIN, "topics"),
        // The Galaxy (the owner's request of 2026-10-11: "the galaxy on the
        // android app should be a direct button thr main screen if the app").
        // Its phone home is the Brain's own "people-and-things" plate
        // (`PeopleAndThingsSection`, EntitiesPlate.kt), so "open the galaxy"
        // goes there rather than answering "only in Jarvis on your PC" - the
        // same defect the "spending" line above was added to fix. The plate
        // itself carries the "Hide memory lists and chat history" guard, so
        // this opens the prompt while the lists are hidden and never shows a
        // name.
        "galaxy" to Where.Go(Screen.BRAIN, "people-and-things"),
        "brain.tab.galaxy" to Where.Go(Screen.BRAIN, "people-and-things"),
    )

    /**
     * Registry ids with no phone equivalent at all: keyboard shortcuts,
     * account secrets (the owner is never asked for one on the phone), the
     * PC's tool-update check, "More options" (startup and logs), starting
     * Jarvis with Windows, the first-run setup page (2026-10-06), which
     * is a card on the PC's Settings screen only, and "The big HUD window"
     * (2026-10-06), which is a switch for a button in a window only the PC
     * has - the big "Jarvis" window and its own chat box are the PC's.
     */
    val PC_ONLY: Set<String> = setOf(
        "shortcuts",
        "account-secrets",
        // "Chatbot API keys" (docs/ACCOUNT-KEYS-DESIGN.md steps 1-2,
        // 2026-10-06): the six chatbot services' keys. They go straight into
        // Windows Credential Manager from the PC's own Rust, so there is no
        // version of this screen that could work on the phone.
        "chatbot-api-keys",
        "tool-updates",
        "more-options",
        "crash-notes",
        "start-jarvis",
        // Notifications was here until 2026-10-29 (the settings wrong-app audit's
        // finding 7): the phone does have the PC's seven kinds, in its
        // "Notifications from Jarvis" row, so it has a place in PLACES now
        // rather than an honest-sounding refusal. (No quoted id is written in
        // this comment on purpose - the registry's own checker scans this block
        // as text, and a quoted id here would read as a member of the set.)
        "first-run",
        "hud-window",
        // "Searchable recordings and videos" (F5 S2, 2026-10-19; S3 added the
        // video on-screen text, 2026-10-20; JARVIS-API section 149): the
        // desktop's Settings card holds the disclosure, the switch, the counts
        // and the one Delete; the index itself lives on the PC. The phone has
        // NO Settings card for it - its chat path and the spoken switch do
        // work - and S3 keeps that one-sided on purpose rather than adding a
        // control that cannot work: the menu row (`settings.media-index`) is
        // desktop-only, and docs/ARCHITECTURE.md section 8 records the
        // follow-up honestly. So "open searchable recordings" answers with the
        // honest PC-only sentence rather than opening a screen that does not
        // have it.
        "media-index",
        // The skills menu (2026-11-02, JARVIS-API section 178): install a skill
        // from a folder or a .zip, import what is in the PC's own Hermes
        // folder, turn one off and back on, and edit its SKILL.md. Every one
        // of those doors runs the PC's scanner and raises ONE card on the PC,
        // and the sources are files on that PC - so there is no version of
        // this screen that could work on the phone. The phone keeps the list
        // and Remove it always had. "open skills" answers with the honest
        // PC-only sentence, and docs/ARCHITECTURE.md section 8 records it.
        "skills-menu",
    )

    /**
     * Whole places, by the id the PC names them with (the second decision
     * step - see this file's own doc): a SCREEN of this app, or a screen plus
     * the item on it that the owner means by that name.
     *
     * These are the names the PC's deterministic "open <a place>" path can
     * answer with, plus the names the owner uses for the Brain's plates. They
     * are decided here once, and `OpenPlaceTest` holds every section to a real
     * `item(key = ...)` on the screen it names - so a plate renamed on the
     * Brain fails the test rather than landing at the top of it.
     *
     * `habits` and `mood` are deliberately NOT here: see [PHONE_MISSING].
     */
    private val AREAS: Map<String, Where.Go> = mapOf(
        // ---------------------------------------------------------- screens ---
        "home" to Where.Go(Screen.HOME, null),
        "chat" to Where.Go(Screen.HOME, null),
        "brain" to Where.Go(Screen.BRAIN, null),
        "mind" to Where.Go(Screen.BRAIN, null),
        "inbox" to Where.Go(Screen.INBOX, null),
        "settings" to Where.Go(Screen.SETTINGS, null),
        "reminders" to Where.Go(Screen.REMINDERS, null),
        "approvals" to Where.Go(Screen.APPROVALS, null),
        "past-approvals" to Where.Go(Screen.APPROVALS, null),
        "history" to Where.Go(Screen.HISTORY, null),
        "conversations" to Where.Go(Screen.HISTORY, null),
        "chats" to Where.Go(Screen.HISTORY, null),
        "live" to Where.Go(Screen.LIVE, null),
        "pins" to Where.Go(Screen.PINS, null),
        "pinned" to Where.Go(Screen.PINS, null),
        "features" to Where.Go(Screen.FEATURES, null),
        "all-features" to Where.Go(Screen.FEATURES, null),
        "find" to Where.Go(Screen.FIND, null),
        "search" to Where.Go(Screen.FIND, null),
        "help" to Where.Go(Screen.FAQ, null),
        "checks" to Where.Go(Screen.CHECKS, null),
        "readiness" to Where.Go(Screen.CHECKS, null),
        "platform-checks" to Where.Go(Screen.CHECKS, null),
        "appearance" to Where.Go(Screen.APPEARANCE, null),
        "voice-check" to Where.Go(Screen.VOICE_CHECK, null),
        "train-voice" to Where.Go(Screen.VOICE, null),
        "lock" to Where.Go(Screen.SECURITY, null),
        "handoff" to Where.Go(Screen.HANDOFF, null),
        "solve-it-here" to Where.Go(Screen.HANDOFF, null),
        "edit-hud" to Where.Go(Screen.EDIT_HUD, null),
        "home-screen" to Where.Go(Screen.EDIT_HUD, null),
        // ------------------- the Brain's plates, named as places of their own ---
        // The value is the `item(key = ...)` BrainScreen.kt draws the plate
        // under (BrainSections.kt's plate recorder); the same keys the
        // Brain-language links already send.
        "memory" to Where.Go(Screen.BRAIN, "memory"),
        "memories" to Where.Go(Screen.BRAIN, "memory"),
        "models" to Where.Go(Screen.BRAIN, "models"),
        "model" to Where.Go(Screen.BRAIN, "models"),
        "jobs" to Where.Go(Screen.BRAIN, "jobs"),
        "tasks" to Where.Go(Screen.BRAIN, "tasks"),
        "goals" to Where.Go(Screen.BRAIN, "goals"),
        "progress" to Where.Go(Screen.BRAIN, "progress"),
        "today" to Where.Go(Screen.BRAIN, "today"),
        "briefing" to Where.Go(Screen.BRAIN, "briefing"),
        "projects" to Where.Go(Screen.BRAIN, "projects"),
        "focus" to Where.Go(Screen.BRAIN, "focus"),
        "pictures" to Where.Go(Screen.BRAIN, "pictures"),
        "wiki" to Where.Go(Screen.BRAIN, "wiki"),
        "quiz" to Where.Go(Screen.BRAIN, "quiz"),
        "decks" to Where.Go(Screen.BRAIN, "decks"),
        "retirement" to Where.Go(Screen.BRAIN, "retirement"),
        "skills" to Where.Go(Screen.BRAIN, "skills"),
        "people-and-things" to Where.Go(Screen.BRAIN, "people-and-things"),
        // ----------------------------------- Settings rows named as areas ---
        // A Settings ROW the PC can name as a place. "notifications" is the
        // row that changes the PC's own seven notification kinds; the rest
        // are rows this app already has under the same name.
        "notifications" to Where.Go(Screen.SETTINGS, "jarvis-notify"),
        "model-lane" to Where.Go(Screen.SETTINGS, "model-lane"),
    )

    /**
     * Real places the PC has, which THIS BUILD of the app has no screen for
     * yet - the honest refusal rather than opening a screen that does not
     * draw them.
     *
     * The words come from `jarvis-client/app/src/main/assets/features.json`:
     * the Habits and Mood records say "Neither app has a screen for it yet -
     * the Habits/Mood section on the Reminders screen is the next lane", and
     * plugins are chat-only on the phone (the drop-in modules are listed and
     * switched on by asking Jarvis). When a later slice builds those screens,
     * the id moves to [AREAS] and this entry goes.
     */
    private val PHONE_MISSING: Map<String, String> = mapOf(
        "habits" to NOT_HERE_YET.format("habits"),
        "mood" to NOT_HERE_YET.format("mood"),
        "plugins" to
            "Plugins are turned on and off by asking Jarvis in chat. There is no Plugins screen in this app yet.",
    )

    /**
     * The one sentence for a place the owner can reach only by another door on
     * the phone. `%s` is the place's name, said the way the owner says it.
     */
    private const val NOT_HERE_YET =
        "There is no %s screen in this app yet, so there is nothing to open. " +
            "Jarvis on your PC keeps it until there is."

    /**
     * The MENU a place id names, from [MenuPlaces]' own tables - the ids
     * `backend/jarvis_menus.py` exports for both apps ("settings.voice",
     * "brain.memory.waiting"). Null when the id is not a menu.
     *
     * This is what makes a menu nameable as a place: the PC's registry can
     * hand over either the phone's own item key or the shared menu id, and
     * both land on the same row.
     */
    private fun forMenu(id: String): Where.Go? {
        MenuPlaces.SETTINGS.entries.firstOrNull { it.value == id }
            ?.let { return Where.Go(Screen.SETTINGS, it.key) }
        MenuPlaces.BRAIN.entries.firstOrNull { it.value == id }
            ?.let { return Where.Go(Screen.BRAIN, it.key) }
        return null
    }

    /** Every id this file has made a decision about - for the test. */
    val KNOWN: Set<String> get() = PLACES.keys + PC_ONLY + AREAS.keys + PHONE_MISSING.keys

    /**
     * The decision, in the order this file's doc states: a known settings
     * section, then a whole place, then a shared menu id, then the honest
     * refusals, then the old harmless fallback.
     */
    fun whereFor(id: String): Where {
        val key = id.trim()
        PLACES[key]?.let { return it }
        AREAS[key]?.let { return it }
        forMenu(key)?.let { return it }
        PHONE_MISSING[key]?.let { return Where.OnPc(it) }
        return if (key in PC_ONLY) {
            Where.OnPc(ON_PC)
        } else {
            // An id newer than this app: the old, harmless behaviour - open
            // Settings, which scrolls nowhere for an id it has no row for.
            // (A newer desktop/phone place with no screen here is said in
            // words only when it is listed in PHONE_MISSING above, because
            // this fallback is also what keeps a new *settings row* working.)
            Where.Go(Screen.SETTINGS, key)
        }
    }
}
