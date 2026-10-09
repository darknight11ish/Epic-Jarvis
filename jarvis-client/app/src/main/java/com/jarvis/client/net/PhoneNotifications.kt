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

    // "Delete captured notifications" (audit A3): asks "are you sure?"
    // first, like Forget, because it cannot be undone. Phone-only: the
    // captured copies live on this phone alone and the PC never sees them.
    const val DELETE_LABEL = "Delete captured notifications"
    const val DELETE_YES = "Yes, delete them"
    const val DELETE_NO = "Keep them"
    const val DELETED = "Deleted. No captured notifications are left on this phone."
    const val NONE_KEPT = "No captured notifications are kept on this phone."

    /** The "are you sure?" before deleting. */
    fun deleteQuestion(count: Int): String =
        "Delete the $count captured notification" + (if (count == 1) "" else "s") +
            " kept on this phone? This cannot be undone."

    /** How many are kept, under the Delete button. */
    fun keptLine(count: Int): String =
        if (count <= 0) NONE_KEPT
        else "$count captured notification" + (if (count == 1) " is" else "s are") +
            " kept on this phone, for up to 7 days. Turning the switch off deletes them."

    /** The line under the switch when it is neither waiting nor busy. */
    fun stateLine(on: Boolean?): String = when (on) {
        true -> "Your phone may read notifications from apps you choose (none, until you " +
            "add one below) and offer them to Jarvis only when you ask."
        false -> "Jarvis never sees a phone notification."
        null -> "Couldn't tell whether your phone may read notifications."
    }

    // "Send test" on Settings -> Phone notifications (Android audit
    // 2026-10-08). The button set its own success flag whatever happened, so
    // it said TEST_SENT in exactly the state where
    // [com.jarvis.client.service.ScheduleNotifier.post] returns early and
    // every approval notification is dropped too. The words now come from
    // whether the notification was actually posted, and the failure says
    // what that means and where to unblock it - the row's own "Android
    // notification settings" button - the same shape [PlatformReadiness]'s
    // notifications check uses for the same state.
    const val TEST_SENT = "Test notification sent."

    const val TEST_BLOCKED =
        "Nothing was sent: notifications are switched off for Jarvis on this phone, so no " +
            "reminder, timer, alarm or approval alert can appear. Tap \"Android notification " +
            "settings\" above and turn notifications on, then press Send test again."

    /** What to say under "Send test", from whether a notification was really posted. */
    fun testWords(posted: Boolean): String = if (posted) TEST_SENT else TEST_BLOCKED
}
