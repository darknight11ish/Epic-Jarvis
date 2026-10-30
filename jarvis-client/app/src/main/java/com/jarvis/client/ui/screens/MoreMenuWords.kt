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
     *
     * Since 2026-10-27 the chat's own three doors open here, first - the owner
     * asked where the old chats are and how to start a new one, so the line
     * that was about presets alone now leads with the chats.
     */
    const val SUBTITLE =
        "Your chats, the presets, and the chat controls that used to sit around " +
            "the box. Only what this PC offers is listed."

    /**
     * "New chat" - starts a fresh conversation, the same mechanism the idle
     * timer uses ([com.jarvis.client.net.ChatSession.newConversationSaid]).
     * The owner's question of 2026-10-27: "how do i open new ones?".
     */
    const val NEW_CHAT = "New chat"

    /** Under "New chat": what a new chat does to the one before it. */
    const val NEW_CHAT_DETAIL = "A fresh conversation. The last one stays in History."

    /**
     * Under "Earlier chats" ([com.jarvis.client.net.ChatHistory.EARLIER_CHATS],
     * which was already here but unlabelled): where that row really goes, so
     * the owner's other question of 2026-10-27 - "where can i find old jarvis
     * chats?" - is answered by the menu that holds it.
     */
    const val EARLIER_DETAIL = "Every chat your PC kept, in History"

    /** Under "Pinned messages" ([com.jarvis.client.data.ChatPins.TITLE]). */
    const val PINNED_DETAIL = "Messages you pinned, newest first"

    /**
     * The line above the box while NOTHING has been said yet. It is the one
     * moment the owner is looking at an empty chat with no idea where the old
     * ones went - the question he asked on 2026-10-27 - so the answer is
     * written where he was already looking.
     */
    const val EMPTY_HINT = "Old chats are in More, under Earlier chats. New chat is there too."

    /** "Jarvis Presets" (the owner's words) - opens the Brain's Hardware plate. */
    const val PRESETS = "Jarvis Presets"

    /** The line under the row: where the presets really are, so the next screen is not a surprise. */
    const val PRESETS_DETAIL = "In Brain, under Hardware"

    /** The Photo key that used to sit at the start of the composer row. */
    const val PHOTO = "Photo"

    /**
     * "Attach a file" (2026-10-29): one PDF, Word, Excel, PowerPoint, text,
     * Markdown or CSV file, read on the owner's PC within the question it is
     * sent with. No new permission, no upload route and no switch.
     */
    const val FILE = "Attach a file"

    /**
     * Under "Attach a file": what really happens to it, so the row is not
     * mistaken for an upload that is kept somewhere. The chip above the box
     * says the rest (the outside-text sentence).
     */
    const val FILE_DETAIL = "PDF, Word, Excel, PowerPoint, text, Markdown or CSV, up to 2.5 MB. Read on your PC."

    /** The Notifications key while phone notifications are on and one was captured. */
    const val NOTIFICATIONS = "Notifications"

    /** "Quick note" - opens the note plate in the conversation. */
    const val QUICK_NOTE = "Quick note"

    /** The dialog's own close, the app's word for it everywhere. */
    const val CLOSE = "Close"
}
