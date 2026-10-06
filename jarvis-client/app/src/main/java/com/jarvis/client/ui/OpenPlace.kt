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
        "manner" to Where.Go(Screen.SETTINGS, "manner"),
        "web-search" to Where.Go(Screen.SETTINGS, "web-search"),
        "asks-first" to Where.Go(Screen.SETTINGS, "asks-first"),
        "reach" to Where.Go(Screen.SETTINGS, "reach"),
        "email-sending" to Where.Go(Screen.SETTINGS, "email-sending"),
        "folders" to Where.Go(Screen.SETTINGS, "folders"),
        "backup" to Where.Go(Screen.SETTINGS, "backup"),
        "watch-notify" to Where.Go(Screen.SETTINGS, "watch-notify"),
        "phone-notify" to Where.Go(Screen.SETTINGS, "phone-notify"),
        // "Look at this and Watch with me": picture mode's switch (2026-09-29).
        "screen-look" to Where.Go(Screen.SETTINGS, "screen-look"),
        // The headless browser (Obscura): its switch, default and install line (2026-09-29).
        "browser-engine" to Where.Go(Screen.SETTINGS, "browser-engine"),
        // Settings -> Devices (docs/PAIRING-DESIGN.md section 7.2).
        "devices" to Where.Go(Screen.SETTINGS, "devices"),
        // The phone's Quick Settings tiles (SettingsScreen.kt, item "quick-tiles").
        "quick-tiles" to Where.Go(Screen.SETTINGS, "quick-tiles"),
        // Hidden navigation menus section (SettingsScreen.kt, item "menu-visibility").
        "menu-visibility" to Where.Go(Screen.SETTINGS, "menu-visibility"),
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
        "second-card" to Where.Go(Screen.BRAIN, "second-card"),
        "big-model" to Where.Go(Screen.BRAIN, "big-model"),
        "backend-supports" to Where.Go(Screen.BRAIN, "capabilities"),
        // "Forget a time frame" (2026-09-28): not a settings section - the
        // place "forget what you learned last week" opens, named by the
        // answer's `open_brain` (net/ForgetRange.kt, ChatSession).
        com.jarvis.client.net.ForgetRange.PLACE to Where.Go(Screen.BRAIN, "forget-range"),
        // "Switch off my work topic" (2026-09-30): not a settings section - the place
        // named by the answer's `open_brain` (net/Topics.kt, ChatSession).
        com.jarvis.client.net.Topics.PLACE to Where.Go(Screen.BRAIN, "topics"),
    )

    /**
     * Registry ids with no phone equivalent at all: keyboard shortcuts,
     * account secrets (the owner is never asked for one on the phone), the
     * PC's tool-update check, "More options" (startup and logs), starting
     * Jarvis with Windows, and the first-run setup page (2026-10-06), which
     * is a card on the PC's Settings screen only.
     */
    val PC_ONLY: Set<String> = setOf(
        "shortcuts",
        "account-secrets",
        "tool-updates",
        "more-options",
        "crash-notes",
        "start-jarvis",
        "spending",
        "notifications",
        "first-run",
    )

    /** Every id this file has made a decision about - for the test. */
    val KNOWN: Set<String> get() = PLACES.keys + PC_ONLY

    fun whereFor(id: String): Where = PLACES[id]
        ?: if (id in PC_ONLY) {
            Where.OnPc(ON_PC)
        } else {
            // An id newer than this app: the old, harmless behaviour - open
            // Settings, which scrolls nowhere for an id it has no row for.
            Where.Go(Screen.SETTINGS, id)
        }
}
