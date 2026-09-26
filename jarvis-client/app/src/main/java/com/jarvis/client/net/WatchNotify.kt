package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * The smartwatch notification setting (docs/JARVIS-API.md; the owner's
 * decision, 2026-09-25, the competitiveness audit; reconfirmed 2026-09-27,
 * Q17): "Smartwatch: every notification stays on the phone by default, with
 * a setting to let them all show on a compatible watch (turning it on
 * raises a card, turning it off is instant)."
 *
 * OFF (the default) is what every notification builder already does
 * (`ApprovalNotifier`, `ScheduleNotifier`, `EventService`, `WakeWordService`
 * - `.setLocalOnly(true)` unless [ClientSettings.watchNotifications] says
 * otherwise). This object is the phone's side of the SWITCH itself: turning
 * it ON on the PC (an approval card, the same shape as [MemoryCounts]'s
 * learning switch) so that side's `.setLocalOnly(...)` calls stop refusing
 * Android's own, already-built-in notification bridging. There is no
 * Jarvis watch app and none is needed - Android does the copying to
 * whatever companion device is paired.
 *
 * - `GET /api/notifications/watch` - `{"enabled", "waiting", "last", "why"}`.
 * - `POST /api/notifications/watch {"enabled": bool}` - ON is 202
 *   `{"waiting": true}` while one approval card (action
 *   [ACTION]) is up; OFF is 200 at once, and withdraws a waiting ON card.
 *
 * A route this old does not have (a PC without `watch-notifications.patch`)
 * answers 404, which [JarvisRuntime] reads as "not on this PC's version of
 * Jarvis yet" - the same way every other switch here degrades.
 *
 * THE PHONE STORES THE LAST KNOWN ANSWER ONLY, IN [ClientSettings], so a
 * notification can be built without a network round trip; it is a CACHE of
 * what the PC said, refreshed whenever this is read, never the setting's
 * only copy. Unknown or stale reads as OFF (`.setLocalOnly(true)`) - the
 * safe direction, since staying on the phone leaks nothing.
 */
object WatchNotify {
    const val PATH = "/api/notifications/watch"

    /** The approval action the PC raises the ON card under. */
    const val ACTION = "watch_notifications_enable"

    fun enabledBody(on: Boolean): String = "{\"enabled\":$on}"

    /** Is the ON card still in the approval queue? */
    fun cardWaiting(actions: List<String?>): Boolean = actions.any { it == ACTION }

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.flag(key: String): Boolean? = (this[key] as? JsonPrimitive)?.booleanOrNull

    /** `GET /api/notifications/watch`'s `enabled`, or null if the PC did not say. */
    fun enabled(status: JsonObject): Boolean? = status.flag("enabled")

    /** The PC's own reason when its settings file is damaged (both then read off), or null. */
    fun whyLine(status: JsonObject): String? = status.str("why")?.takeIf { it.isNotBlank() }

    /** What to say after the switch was pressed, from the PC's answer. */
    fun said(on: Boolean, outcome: DesktopWrite.Outcome): String = when (outcome) {
        is DesktopWrite.Outcome.Waiting -> waitingLine()
        is DesktopWrite.Outcome.Refused -> "Not changed. ${outcome.why}"
        is DesktopWrite.Outcome.Done -> outcome.said
            ?: if (on) "Notifications may now show on a compatible watch."
               else "Notifications stay on the phone only."
    }

    fun waitingLine(): String =
        "Waiting for your approval to let notifications show on a watch. ${Approvals.WHERE}"

    /** The line under the switch when it is neither waiting nor busy. */
    fun stateLine(on: Boolean?): String = when (on) {
        true -> "Every notification may also show on a paired, compatible smartwatch - " +
            "Android's own notification bridging, not a Jarvis watch app."
        false -> "Every notification (approval cards, timers, reminders, \"tell me when\") " +
            "stays on this phone only."
        null -> "Couldn't tell whether notifications may show on a watch."
    }
}
