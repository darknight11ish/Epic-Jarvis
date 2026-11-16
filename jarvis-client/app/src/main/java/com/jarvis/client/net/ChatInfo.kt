package com.jarvis.client.net

import java.time.LocalDate
import java.time.ZoneId

/**
 * "About this conversation" - the one compact card a History row's small "i"
 * opens. The phone's half of the owner's ask of 2026-11-15, in his words:
 *
 * > "does chat history have in both jarvis desktop and app have an info menu
 * > that i can click show (or a symbol or something) om each comversation that
 * > i can look at? that includes info like if the chat was on which device
 * > (phone or laptop) andmoree? without this being overwhelming"
 *
 * He chose a small "i" that opens one card which closes itself, so the rows
 * stay exactly as clean as they were. The card says the row's OWN facts, one
 * line each, in this order: which app it was had in, "Started", "Last used"
 * (left out when it is the same minute as Started), the message count, and
 * then only the marks the chat carries - said aloud, read outside text, its
 * tag, pinned, archived. Nothing is fetched and nothing is written: every
 * fact here is already in [ChatLog.Summary], which the list read, so this
 * adds no route, no request, no permission and no approval card.
 *
 * THE WORDS ARE THE DESKTOP'S, CHARACTER FOR CHARACTER. Its half of this
 * feature (jarvis-desktop, PR #1278) keeps the same table in
 * `src/history-view.js` (`INFO_TITLE` ... `INFO_NODATE`, `DEVICE_TAGS`,
 * `chatInfoCard`) and pins every line in `tests/chat-info.mjs`; this file is
 * that block, transliterated. `ChatInfoTest` pins the same sentences here, so
 * a re-word on one side fails a test rather than drifting quietly. If a word
 * ever should change, it changes in both halves in the same breath - never
 * here alone.
 *
 * ONE SOURCE FOR THE SHARED WORDS. The time words are [ChatLog.whenLine]'s
 * and the count's are [ChatLog.messagesWords]'s - the same functions the
 * row's own line uses - rather than a second copy. Only the sentences this
 * card alone says live here.
 *
 * WHY THE TAG LINE HAS A SWITCH. A tag's NAME is only known when this screen
 * may read the tag list at all: while App lock or "Hide memory lists and chat
 * history" is on (Security), the phone is not given tag names, and this card
 * must not imply one. So [card] takes `tagsKnown` and, with it false, says
 * NOTHING about filing - "Not filed under a tag." would be a claim about a
 * filing the phone cannot see. With the list readable every row says which it
 * is: "Filed under: Work" or "Not filed under a tag."
 *
 * Pure Kotlin, no Android types, so `ChatInfoTest` runs it on a plain JVM.
 */
object ChatInfo {

    // ------------------------------------------------------------- words ---

    /** The card's heading and its one button, word for word in both apps. */
    const val TITLE = "About this conversation"
    const val CLOSE = "Close"

    /** The two dates, each one label plus the PC's own time words. */
    const val STARTED = "Started: "
    const val USED = "Last used: "

    /** Said only when the row carries the mark it describes. */
    const val VOICE = "Some of it was said aloud."
    const val OUTSIDE =
        "It read text that did not come from you: a web page, a file, an email or another tool's output."
    const val PIN = "Pinned to the top."
    const val ARCHIVE = "In Archived."

    /** The tag line, filed or not (both apps). */
    const val TAG_FILED = "Filed under: "
    const val TAG_NONE = "Not filed under a tag."

    /** In place of a date the PC did not send - never a guess, never silence. */
    const val NODATE = "The PC did not say when."

    /**
     * Which app a conversation was had in, as the card's first line - the
     * desktop's `DEVICE_TAGS` words, character for character. The row's own
     * short tag is [ChatLog.deviceWord] ("PC", "HUD", "phone", "unknown");
     * `ChatInfoTest` holds the two tables to each other so neither drifts.
     */
    fun deviceWords(device: String?): String = when (device) {
        "desktop" -> "Had in the Jarvis bar on this PC."
        "hud" -> "Had in the HUD window on this PC."
        "phone" -> "Had on your phone."
        else -> "The PC did not say which app this was had in."
    }

    /** "Filed under: Work" - the tag's name as the PC spells it, never re-worded. */
    fun filedUnderWords(name: String): String = TAG_FILED + name.trim()

    /**
     * The name for a row's "i" for TalkBack: "About Dentist on Tuesday", the
     * same shape the desktop gives its button (`aria-label="About <title>"`)
     * and the shape this screen already uses for its other row actions
     * ([HistoryView.actionsFor]).
     */
    fun aboutFor(title: String): String = "About $title"

    // ------------------------------------------------------------- lines ---

    /** The card for ONE conversation row, as drawn: its heading, its button and its lines. */
    data class Card(val title: String, val close: String, val lines: List<String>)

    /**
     * [at] in the app's own time words, or "" for a time it cannot use.
     *
     * [ChatLog.whenLine] is the one source of "Today 14:05" / "Yesterday 09:12"
     * / "Sat 12 Sep 18:30" / "Fri 3 Jan 2025" (the desktop's `whenLine`, word
     * for word). It answers "When unknown" for a missing time because a ROW
     * must not go silent; this card says [NODATE] instead, and the desktop's
     * own `whenLine` returns "" for null and for 0 or less. Both are honoured
     * here: a moment the PC did not send, or sent as 0, is "did not say when",
     * never 1970.
     */
    private fun whenWords(at: Long?, zone: ZoneId, today: LocalDate): String =
        if (at == null || at <= 0L) "" else ChatLog.whenLine(at, zone, today)

    /**
     * The card for ONE conversation row: the device, "Started", "Last used"
     * (left out when it is the same minute as Started), the message count,
     * then only the marks it has - said aloud, read outside text, the tag,
     * pinned, archived.
     *
     * Nothing else is shown, and nothing here is a guess: no line names the
     * chat's kind (the row already carries its kind mark), and a time the PC
     * did not send says [NODATE] rather than a date this phone made up.
     *
     * [zone] and [today] are parameters so the words do not drift with the day
     * a test runs - [ChatLog.whenLine]'s own two, as the row passes them.
     * `tagName` / `tagsKnown` decide the tag line; see the block comment above.
     */
    fun card(
        row: ChatLog.Summary,
        zone: ZoneId,
        today: LocalDate,
        tagName: String? = null,
        tagsKnown: Boolean = false,
    ): Card {
        val started = whenWords(row.started, zone, today)
        val used = whenWords(row.updated, zone, today)
        val lines = ArrayList<String>(9)
        lines += deviceWords(row.device)
        lines += STARTED + (started.ifEmpty { NODATE })
        // One line per fact: a chat used in the minute it started has ONE time,
        // not the same words twice under two labels.
        if (used != started) lines += USED + (used.ifEmpty { NODATE })
        lines += ChatLog.messagesWords(row.turns ?: 0)
        if (row.hasVoice) lines += VOICE
        if (row.tainted) lines += OUTSIDE
        if (tagsKnown) {
            val name = tagName?.trim().orEmpty()
            lines += if (name.isEmpty()) TAG_NONE else filedUnderWords(name)
        }
        if (row.pinned) lines += PIN
        if (row.archived) lines += ARCHIVE
        return Card(TITLE, CLOSE, lines)
    }
}
