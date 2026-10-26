package com.jarvis.client.ui.screens

/**
 * The words of the one "More" menu (the owner's ask of 2026-10-25).
 *
 * Pure Kotlin with no Compose and no Android, for the same reason
 * [com.jarvis.client.ui.FindWords] and [com.jarvis.client.ui.SettingsJump] are
 * pure: a JVM unit test can hold the words still, and the source-pin test can
 * name them once instead of retyping them. The controls' own words stay in
 * their own homes where one exists (`TemporaryChat.START`/`END`,
 * `ChatHistory.EARLIER_CHATS`, `Thinking.ONE_SHOT_LABEL`,
 * `FocusPresets`); this object only names the labels that were plain text in
 * the composer before the move.
 *
 * NOTHING in this file decides whether a row is drawn - `HomeMoreMenu` asks
 * the same state gates the controls carried when they sat around the box
 * (pictureOffered, thinkOffered, the coach's route + switch,
 * notificationsAttachable). So a PC that never offered a control still cannot
 * see it here.
 */
internal object MoreMenuWords {

    /** The button beside the composer and the face bar, and the dialog's title. */
    const val MORE = "More"

    /**
     * One line under the title, said in plain words because a menu that is
     * suddenly the only door to nine controls is worth opening with an
     * explanation: only the controls this PC really offers are listed.
     */
    const val SUBTITLE =
        "Presets and the chat controls that used to sit around the box. " +
            "Only what this PC offers is listed."

    /** "Jarvis Presets" (the owner's words) - opens the Brain's Hardware plate. */
    const val PRESETS = "Jarvis Presets"

    /** The line under the row: where the presets really are, so the next screen is not a surprise. */
    const val PRESETS_DETAIL = "In Brain, under Hardware"

    /** The Photo key that used to sit at the start of the composer row. */
    const val PHOTO = "Photo"

    /** The Notifications key while phone notifications are on and one was captured. */
    const val NOTIFICATIONS = "Notifications"

    /** "Quick note" - opens the note plate in the conversation. */
    const val QUICK_NOTE = "Quick note"

    /** The dialog's own close, the app's word for it everywhere. */
    const val CLOSE = "Close"
}
