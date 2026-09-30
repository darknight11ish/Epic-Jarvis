package com.jarvis.client.service

/**
 * Every notification id and foreground-service id this app uses, in ONE place.
 *
 * Why: Android tells notifications apart by their number (plus an optional
 * tag). Two notifications with the same number replace each other, and
 * cancelling one removes the other. That already happened twice: the chatbot
 * line and the "Hey Jarvis is off since the phone restarted" notice both used
 * 0x3200, and the wake-word service and the screen-watch service both used
 * 0x4A57 as their foreground-service notification. Keeping the numbers side by
 * side makes a clash visible, and `NotificationIdsTest` fails if two are equal.
 *
 * A new notification adds its number HERE (and to [ALL]), never in its own file.
 *
 * [APPROVAL_FIRST] and up is [ApprovalNotifier]'s own running range (one number
 * per waiting approval), so every other id must stay below it.
 */
object NotificationIds {
    // Live (foreground service, the offer, and "Live ended - Resume").
    const val LIVE = 0x4A4C
    const val LIVE_OFFER = 0x4A4D
    const val LIVE_RESUME = 0x4A4E

    // Foreground-service notifications of the other services.
    const val EVENT_LINK = 0x4A56
    const val WAKE_WORD = 0x4A57
    const val AVATAR_OVERLAY = 0x4A58
    const val SCREEN_WATCH = 0x4A59

    // Reminders and alarms (also given a tag per job, but kept distinct anyway).
    const val SCHEDULE = 0x3100

    // Notifiers.
    const val CHATBOT = 0x3200
    const val SUPPORT_CHAT = 0x3201
    const val HANDOFF = 0x3202
    const val WAKE_RESUME = 0x3203

    // Approvals: one summary line, then one number per waiting card from FIRST up.
    const val APPROVAL_SUMMARY = 0x4AFF
    const val APPROVAL_FIRST = 0x4B00

    /** Every id above by name, for the test that checks none is used twice. */
    val ALL: List<Pair<String, Int>> = listOf(
        "LIVE" to LIVE,
        "LIVE_OFFER" to LIVE_OFFER,
        "LIVE_RESUME" to LIVE_RESUME,
        "EVENT_LINK" to EVENT_LINK,
        "WAKE_WORD" to WAKE_WORD,
        "AVATAR_OVERLAY" to AVATAR_OVERLAY,
        "SCREEN_WATCH" to SCREEN_WATCH,
        "SCHEDULE" to SCHEDULE,
        "CHATBOT" to CHATBOT,
        "SUPPORT_CHAT" to SUPPORT_CHAT,
        "HANDOFF" to HANDOFF,
        "WAKE_RESUME" to WAKE_RESUME,
        "APPROVAL_SUMMARY" to APPROVAL_SUMMARY,
        "APPROVAL_FIRST" to APPROVAL_FIRST,
    )
}
