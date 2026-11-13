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
 * (thinkOffered, the coach's route + switch, notificationsAttachable). So a
 * PC that never offered a control still cannot see it here. The Photos gate
 * is the one that moved: since 2026-11-01 it lives inside the Attach row's
 * own picker (`AttachFile.mimeTypes`), not on a row of its own.
 */
internal object MoreMenuWords {

    /** The button beside the composer and the face bar, and the dialog's title. */
    const val MORE = "More"

    /**
     * One line under the title, said in plain words because a menu that is
     * suddenly the only door to the chat's controls is worth opening with an
     * explanation: only the controls this PC really offers are listed.
     *
     * Since the owner's choice of 2026-10-30 the chat half is short on purpose:
     * five rows at most. The three chat modes (Think, Coach this, Incognito)
     * moved one tap further, behind [MODES]. Since 2026-11-10 the Home screen's
     * top strip is split: its informational cards are the section above these
     * rows, and its two safety cards stay on Home (drawn compact there), which
     * is why the sentence names the two halves it has.
     */
    const val SUBTITLE =
        "The Home cards that are not safety controls, then the chat's own " +
            "controls, the modes, and what you can send with a question. Only " +
            "what this PC offers is listed."

    /**
     * "New chat" - starts a fresh conversation, the same mechanism the idle
     * timer uses ([com.jarvis.client.net.ChatSession.newConversationSaid]).
     * The owner's question of 2026-10-27: "how do i open new ones?".
     */
    const val NEW_CHAT = "New chat"

    /** Under "New chat": what a new chat does to the one before it. */
    const val NEW_CHAT_DETAIL = "A fresh conversation. The last one stays in History."

    /**
     * "History" - past conversations, one tap away (the owner's ask of
     * 2026-11-10: the phone should be able to reach old chats easily). It opens
     * the SAME HistoryScreen the status line's own "History" link opens; the
     * status line's one-tap door is kept, so this is a second, more discoverable
     * way to the one surface, not a second list.
     */
    const val HISTORY = "History"

    /** Under "History": what the screen holds, and that it is the PC's own list. */
    const val HISTORY_DETAIL = "Every chat your PC kept."

    /**
     * The one row that holds the chat's three modes now (the owner's choice of
     * 2026-10-30: "Tuck the rare ones behind one Filters button" was about
     * History; the same wish shortened this menu). It opens a small sub-sheet
     * with Think, Coach this and Incognito - each acting exactly as it did when
     * it was a row here.
     */
    const val MODES = "Modes"

    /** Under "Modes": the sub-sheet is the three one-question switches, nothing more. */
    const val MODES_SUBTITLE = "One question at a time. Each works exactly as it did in More."

    /** Under "Modes": what the three switches are, in a phrase that fits every PC. */
    const val MODES_DETAIL = "The chat's one-question switches"

    /** The sub-sheet's way back to the short menu, beside Close. */
    const val MODES_BACK = "Back"

    /**
     * Under "Earlier chats" ([com.jarvis.client.net.ChatHistory.EARLIER_CHATS]),
     * which was already here but unlabelled: where that row really goes, so
     * the owner's other question of 2026-10-27 - "where can i find old jarvis
     * chats?" - is answered by the menu that holds it.
     *
     * NO LONGER DRAWN (2026-10-30): it opened History, and History is the list -
     * Home's status line now opens it in one tap, so the row said nothing the
     * screen did not. The words are kept here so the sentence the owner was
     * told has one home, not none.
     */
    const val EARLIER_DETAIL = "Every chat your PC kept, in History"

    /**
     * Under "Pinned messages" ([com.jarvis.client.data.ChatPins.TITLE]).
     *
     * NO LONGER DRAWN (2026-10-30): the list moved into History's header as one
     * compact "Pinned" action, the same screen one tap away.
     */
    const val PINNED_DETAIL = "Messages you pinned, newest first"

    /**
     * The line above the box while NOTHING has been said yet. It is the one
     * moment the owner is looking at an empty chat with no idea where the old
     * ones went - the question he asked on 2026-10-27 - so the answer is
     * written where he was already looking. Corrected 2026-10-30: Earlier chats
     * left the More menu, so this line no longer sends him there.
     */
    const val EMPTY_HINT =
        "Old chats are in History, one tap away. New chat is in More, or under a finished answer."

    /**
     * "Jarvis Presets" (the owner's words) - opens the Brain's Hardware plate.
     *
     * NO LONGER DRAWN IN MORE (2026-10-30): Home already has a one-tap
     * "Presets →" door in ModelDoorsRow beside the Galaxy (2026-10-27), so this
     * row was the second way to the same plate and left the short menu.
     */
    const val PRESETS = "Jarvis Presets"

    /** The line under the row: where the presets really are, so the next screen is not a surprise. */
    const val PRESETS_DETAIL = "In Brain, under Hardware"

    /**
     * "Attach a file" (2026-10-29; the ONE way to send a document OR a photo
     * since 2026-11-01, when the separate Photo row went). A document is one
     * PDF, Word, Excel, PowerPoint, text, Markdown or CSV file, read on the
     * owner's PC within the question it is sent with. A photo picked here
     * goes down its own picture path, exactly as the Photo row did. No new
     * permission, no upload route and no switch.
     */
    const val FILE = "Attach a file"

    /**
     * Under "Attach a file": what really happens to it, so the row is not
     * mistaken for an upload that is kept somewhere. Every kind and every
     * cap is named - the documents' 2.5 MB is `AttachFile.MAX_BYTES`, and the
     * photo's 1.5 MB is `ChatPicture.MAX_JPEG_BYTES`, which the phone shrinks
     * the photo to fit rather than a limit on what may be picked. The chip
     * above the box says the rest (the outside-text sentence).
     */
    const val FILE_DETAIL =
        "PDF, Word, Excel, PowerPoint, text, Markdown, CSV or a photo. " +
            "A document up to 2.5 MB; a photo is shrunk to fit 1.5 MB. Read on your PC."

    /** The Notifications key while phone notifications are on and one was captured. */
    const val NOTIFICATIONS = "Notifications"

    /** "Quick note" - opens the note plate in the conversation. */
    const val QUICK_NOTE = "Quick note"

    /** The dialog's own close, the app's word for it everywhere. */
    const val CLOSE = "Close"
}
