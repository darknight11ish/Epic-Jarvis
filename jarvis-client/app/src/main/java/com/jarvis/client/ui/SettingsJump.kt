package com.jarvis.client.ui

/**
 * The jump list at the top of the phone's Settings - the same idea as the
 * desktop's "Jump to:" bar (settings.html), and every row of the screen is in
 * it (settings audit 2026-09-30: Settings had grown to seventeen sections with
 * no way to see them all or reach the last one without scrolling past the
 * rest).
 *
 * Pure - no Android - so `SettingsJumpTest` can hold it to the screen's real
 * `item(key = ...)` rows: a section added to Settings without a line here
 * fails that test.
 *
 * The keys are SettingsScreen.kt's item keys; the labels are the words the
 * desktop's own list uses where the two apps have the same section.
 */
object SettingsJump {
    const val TITLE = "Jump to:"

    /** The row that holds this list, and the closing spacer: not sections. */
    const val LIST_KEY = "jump-list"
    const val TAIL_KEY = "tail"

    /**
     * The search box's own row (2026-10-09). It is the FIRST `item(key = ...)`
     * on the screen, so it is a row like any other - but it is a control, not
     * a section, so it is never in [ENTRIES] and never filtered out by the
     * search itself. Same shape as [LIST_KEY] and [TAIL_KEY], and
     * `SettingsSearch` carries its words.
     */
    const val SEARCH_KEY = "search"

    /**
     * Where [SEARCH_KEY] sits in `SettingsScreen.kt`'s `SETTINGS_ITEM_INDEX`:
     * the first row, above [LIST_KEY]. Named here so the screen and the test
     * that reads that map cannot disagree about it.
     */
    const val SEARCH_KEY_INDEX = 0

    data class Entry(val label: String, val key: String)

    /** In the order the sections appear on the screen. */
    val ENTRIES: List<Entry> = listOf(
        Entry("Voice", "voice"),
        Entry("Security", "security"),
        Entry("Show or hide menus", "menu-visibility"),
        Entry("Appearance", "appearance"),
        Entry("Floating Jarvis", "floating-avatar"),
        Entry("How Jarvis talks", "manner"),
        Entry("Web search", "web-search"),
        Entry("Prompt coach", "prompt-coach"),
        Entry("What asks first", "asks-first"),
        Entry("What Jarvis can reach", "reach"),
        Entry("Sending email", "email-sending"),
        Entry("Folders Jarvis may look in", "folders"),
        Entry("Backups", "backup"),
        Entry("Smartwatch notifications", "watch-notify"),
        Entry("Phone notifications", "phone-notify"),
        // "Notifications from Jarvis" (the owner's decision of 2026-10-09): the
        // phone's own per-kind switches are Android's, so this row points at
        // Android's screen instead of copying the PC's card. It sits with the
        // other notification rows on the screen, so it goes here.
        Entry("Notifications from Jarvis", "jarvis-notify"),
        Entry("Look at this and Watch with me", "screen-look"),
        Entry("Browser without a window", "browser-engine"),
        // "When the phone does not answer" (2026-10-08): the new captcha hand-off
        // row sits between these two on the screen (SettingsScreen.kt), so it
        // goes between them here too - the label is the desktop jump list's own
        // words for the same section (settings.html, `#handoff`).
        Entry("When the phone does not answer", "handoff"),
        // "When a captcha stops Jarvis" (2026-10-09): the new captcha-window row
        // sits between these two on the screen (SettingsScreen.kt), so it goes
        // between them here too - the label is the desktop jump list's own words
        // for the same section (settings.html, `#handoff-front`).
        Entry("When a captcha stops Jarvis", "handoff-front"),
        Entry("Devices", "devices"),
        Entry("Quick Settings tiles", "quick-tiles"),
        // "Screen refresh rate" (2026-10-09): its own Settings row, right after
        // Quick Settings tiles on the screen (SettingsScreen.kt), so it is next
        // to it here too. Phone-only: the desktop draws on a monitor, so no
        // desktop jump entry exists to copy words from, and the label is this
        // section's own title.
        Entry("Screen refresh rate", "screen-rate"),
        // "Limits and how often Jarvis does things" (the PC's own
        // backend/jarvis_limits.py table, 2026-10-08): the last row on the
        // screen, so it is the last entry here too. The desktop has no jump
        // entry for these yet, so the words are this section's own title.
        Entry("Limits and how often Jarvis does things", "limits"),
        // "A new conversation starts after" (the audit of 2026-10-08): the one
        // timing the owner could not change anywhere. It is the LAST row on the
        // screen, so it is the last entry here too - the label is the desktop
        // jump list's own words for the same section (settings.html,
        // `#idle-new`).
        Entry("A new conversation starts after", "idle-new"),
    )
}
