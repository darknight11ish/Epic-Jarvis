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

    // Call recording (2026-11-04): the one ongoing notice while a call is
    // recorded - armed, then recording with the clock, then Stop.
    const val CALL_RECORD = 0x4A5A

    // Hands-free (2026-11-04): the service's own ongoing line, the card waiting
    // to be answered, and the one line about a text message. Three numbers,
    // never one: cancelling the card's notification must not take the
    // service's own with it (a foreground service whose notification is
    // cancelled is killed by Android on some builds), and a "sent to Alex" line
    // must survive the card that prompted it. They start after call recording's
    // 0x4A5A, which landed first.
    const val HANDSFREE = 0x4A5D
    const val HANDSFREE_CARD = 0x4A5E
    const val HANDSFREE_SMS = 0x4A5F

    // Reminders and alarms (also given a tag per job, but kept distinct anyway).
    const val SCHEDULE = 0x3100

    // Notifiers.
    const val CHATBOT = 0x3200
    const val SUPPORT_CHAT = 0x3201
    const val HANDOFF = 0x3202
    const val WAKE_RESUME = 0x3203

    // "Call recording kept on this phone": a finished recording the PC has not
    // taken yet, kept on this phone until it can be sent.
    const val CALL_RECORD_WAITING = 0x3204

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
        "CALL_RECORD" to CALL_RECORD,
        "HANDSFREE" to HANDSFREE,
        "HANDSFREE_CARD" to HANDSFREE_CARD,
        "HANDSFREE_SMS" to HANDSFREE_SMS,
        "SCHEDULE" to SCHEDULE,
        "CHATBOT" to CHATBOT,
        "SUPPORT_CHAT" to SUPPORT_CHAT,
        "HANDOFF" to HANDOFF,
        "WAKE_RESUME" to WAKE_RESUME,
        "CALL_RECORD_WAITING" to CALL_RECORD_WAITING,
        "APPROVAL_SUMMARY" to APPROVAL_SUMMARY,
        "APPROVAL_FIRST" to APPROVAL_FIRST,
    )
}
