package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * The "read my phone's notifications" setting (docs/JARVIS-API.md §61; the
 * owner's decision, CLAUDE.md 2026-09-26; built 2026-09-28). Same shape as
 * [WatchNotify] on purpose, both here and on the backend
 * (`backend/jarvis_phone_notifications.py`'s own docstring says the same):
 * off by default, ON is one approval card, OFF is instant, and only this
 * phone ever acts on the switch even though the PC decides it.
 *
 * WHAT THIS OBJECT IS, AND WHAT IT IS NOT. This is the PC-decided master
 * switch only - whether the phone may even try to read notifications at
 * all. It carries no notification text, ever: this backend module never
 * sees one. The rest of the feature is entirely local to this phone:
 *   - [NotificationAllowListStore] - which apps (empty by default; never
 *     a banking or SMS app, blocked outright);
 *   - [com.jarvis.client.data.NotificationRedactor] - blanking a one-time
 *     code before anything is stored;
 *   - [com.jarvis.client.service.PhoneNotificationListenerService] - the
 *     actual Android `NotificationListenerService`, gated on both of the
 *     above AND on this switch being ON;
 *   - [com.jarvis.client.data.CapturedNotifications] - the local store,
 *     and the "shared text" the owner can attach to a chat question
 *     themselves (never sent on its own - see that class's own doc).
 *
 * - `GET /api/notifications/phone` - `{"enabled", "waiting", "last", "why"}`.
 * - `POST /api/notifications/phone {"enabled": bool}` - ON is 202
 *   `{"waiting": true}` while one approval card (action [ACTION]) is up;
 *   OFF is 200 at once, and withdraws a waiting ON card.
 *
 * A route this old does not have (a PC without `phone-notifications.patch`)
 * answers 404, which [com.jarvis.client.JarvisRuntime] reads as "not on
 * this PC's version of Jarvis yet" - the same way every other switch here
 * degrades.
 *
 * THE PHONE STORES THE LAST KNOWN ANSWER ONLY, IN [com.jarvis.client.data.
 * ClientSettings], so the listener service can decide without a network
 * round trip on every notification. Unknown or stale reads as OFF - the
 * safe direction, since staying off reads nothing.
 */
object PhoneNotifications {
    const val PATH = "/api/notifications/phone"

    /** The approval action the PC raises the ON card under. */
    const val ACTION = "phone_notifications_read"

    fun enabledBody(on: Boolean): String = "{\"enabled\":$on}"

    /** Is the ON card still in the approval queue? */
    fun cardWaiting(actions: List<String?>): Boolean = actions.any { it == ACTION }

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.flag(key: String): Boolean? = (this[key] as? JsonPrimitive)?.booleanOrNull

    /** `GET /api/notifications/phone`'s `enabled`, or null if the PC did not say. */
    fun enabled(status: JsonObject): Boolean? = status.flag("enabled")

    /** The PC's own reason when its settings file is damaged (both then read off), or null. */
    fun whyLine(status: JsonObject): String? = status.str("why")?.takeIf { it.isNotBlank() }

    /** What to say after the switch was pressed, from the PC's answer. */
    fun said(on: Boolean, outcome: DesktopWrite.Outcome): String = when (outcome) {
        is DesktopWrite.Outcome.Waiting -> waitingLine()
        is DesktopWrite.Outcome.Refused -> "Not changed. ${outcome.why}"
        is DesktopWrite.Outcome.Done -> outcome.said
            ?: if (on) "Your phone may now read notifications from apps you choose."
               else "Jarvis will not read your phone's notifications."
    }

    fun waitingLine(): String =
        "Waiting for your approval to let your phone read notifications. ${Approvals.WHERE}"

    /** The line under the switch when it is neither waiting nor busy. */
    fun stateLine(on: Boolean?): String = when (on) {
        true -> "Your phone may read notifications from apps you choose (none, until you " +
            "add one below) and offer them to Jarvis only when you ask."
        false -> "Jarvis never sees a phone notification."
        null -> "Couldn't tell whether your phone may read notifications."
    }
}
