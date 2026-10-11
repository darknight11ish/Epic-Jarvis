package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject

/**
 * The PC's Notifications card, on the phone: the same seven values the
 * desktop's own card draws, read and written through the same route.
 *
 * WHERE THESE COME FROM, AND WHY THAT IS THE HONEST ANSWER. The desktop's
 * "Notifications" card (`jarvis-desktop/src/settings.html` :1073-1153) covers
 * seven values - four per-kind switches, the quiet-hours switch and its two
 * times. Since the owner's decision of 2026-10-08 those seven are rows in the
 * PC's OWN limits table (`backend/jarvis_limits.py`'s `_NOTIFY_ROWS`,
 * `backend/jarvis_notify_prefs.py` owns the file), and BOTH apps reach them
 * through the one limits route:
 *
 *   GET  [Limits.PATH]        -> the rows, with what the PC says now
 *   POST [Limits.WRITE_PATH]  -> ONE row, `{"key": ..., "value": ...}`
 *
 * The desktop's card reads and writes exactly that route
 * (`jarvis-desktop/src/notifications-prefs.js`'s `NOTIF_ROWS`,
 * `readFromBackend`, `writeToBackend`), which is why this phone card invents no
 * API of its own: it draws the same seven rows, in the same order, from the
 * same answer, and posts its changes to the same place.
 *
 * WHAT IS NOT COPIED. The rows' titles and notes are NOT repeated here: they
 * arrive with the answer, in the PC's own words, and every one of them says
 * "(on your PC)" on purpose (`jarvis_limits.py` :416-419) so that a reader can
 * never mistake the PC's notification settings for this phone's. The phone's
 * own notifications are Android's, are a different feature, and are reached
 * from the "Notifications from Jarvis" row above this card.
 *
 * WHAT THIS PHONE CANNOT DO, SAID PLAINLY. The desktop card's Test button asks
 * Windows to show a sample toast. No route lets this phone do that (the desktop
 * calls the Tauri command `notify_user`), so [TEST_LINE] says so and the button
 * that carries the same desktop words tests THIS phone's own alerts instead -
 * which is the thing a person holding the phone can actually check.
 *
 * Pure Kotlin, no Android types, so a plain JVM test can hold the keys against
 * the desktop's own list and against the PC's table.
 */
object NotifyRows {

    /**
     * The card's title on the phone. The desktop's card is called
     * "Notifications" and this one is that same card - but on the phone that
     * bare name would sit directly under "Notifications from Jarvis" and read
     * as this phone's own settings, which it is not. The PC's own rows all say
     * "(on your PC)"; the title says it too.
     */
    const val TITLE = "Notifications on your PC"

    /**
     * The desktop's own note, with one word changed: "this PC" becomes
     * "your PC", because on a phone the reader is not sitting at it. Every
     * other word, and the promise in the second sentence, is the card's own.
     */
    const val NOTE =
        "Choose what Jarvis notifies you about on your PC. Decisions waiting for your yes " +
            "always notify you and cannot be turned off."

    /** The desktop card's three subheadings, word for word. */
    const val SUBHEAD_KINDS = "What notifies you"
    const val SUBHEAD_QUIET = "Quiet hours"
    const val SUBHEAD_TEST = "Test notifications"

    /**
     * Said under [NOTE], above the rows. It claims no direction (the PC decides
     * per row whether a change applies at once or raises a card) and it names
     * whose settings these are, which is the one thing a reader must not get
     * wrong here.
     */
    const val LINE =
        "These are your PC's settings, in the PC's own words. The PC answers every change, and " +
            "its own answer is shown under the list."

    /** The desktop's Test button, word for word, and what it does on a phone. */
    const val TEST_LABEL = "Send test notification"
    const val TEST_LINE =
        "Send a sample notification to make sure this phone's notifications and sounds are " +
            "working. The PC has its own test button, on the PC: nothing on this phone can make " +
            "Windows show a notification."

    /** A PC whose limits table answers, but without these seven rows (an older table). */
    const val NO_ROWS =
        "Your PC's Jarvis does not have its notification settings in this table yet - run " +
            "apply-patches.ps1 on the PC."

    /** A read that failed for any other reason. */
    fun readFailed(reason: String): String = "Couldn't read the PC's notification settings: $reason"

    /**
     * The seven rows, in the desktop card's own order and under the keys the
     * desktop's card uses (`notifications-prefs.js`'s `NOTIF_ROWS`), which are
     * also the PC's table keys (`jarvis_limits.py`'s `f"notif_{pref_key}"`).
     *
     * THIS LIST IS THE WIRING. One added, renamed or reordered key here would
     * point the phone's card at something the desktop's card does not own, and
     * `NotifyRowsTest` holds all three sides - this list, the desktop's own
     * list, and the PC's table - to each other.
     */
    val KEYS: List<String> = listOf(
        "notif_alarms",
        "notif_reminders",
        "notif_briefing",
        "notif_handoff",
        "notif_quiet_enabled",
        "notif_quiet_start",
        "notif_quiet_end",
    )

    /** The five on/off rows: the four kinds, then quiet hours itself. */
    val SWITCHES: List<String> = KEYS.take(5)

    /** The two clock-time rows, the quiet window's ends. */
    val TIMES: List<String> = KEYS.drop(5)

    /**
     * The seven rows as the PC sent them, in [KEYS] order, and only the rows
     * the PC lets this phone draw ([Limits.offered]: a row marked `pc_only` can
     * never appear, even if a PC sends one).
     *
     * A key the PC did not send is simply absent - an older PC keeps its own
     * defaults rather than being shown a value this phone made up - and the
     * order is this card's, not the answer's, so the card reads the same however
     * the table happens to be sorted.
     */
    fun rows(body: JsonObject): List<Limits.Row> {
        val offered = Limits.offered(body).associateBy { it.key }
        return KEYS.mapNotNull { offered[it] }
    }

    /** The four kinds, then the quiet group (its switch and its two times). */
    fun kindRows(rows: List<Limits.Row>): List<Limits.Row> = rows.filter { it.key in KEYS.take(4) }

    fun quietRows(rows: List<Limits.Row>): List<Limits.Row> = rows.filter { it.key in KEYS.drop(4) }
}
