package com.jarvis.client.data

import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import java.security.MessageDigest

/*
 * Pinned chat messages (the owner's request of 2026-10-27): "along with a pin
 * message button that pins the message and remembers it and can be found
 * easily in a new menu".
 *
 * PURE KotLIN, no Compose and no Android, for two reasons:
 *  - the JVM unit tests can hold the rules still without a phone or an
 *    emulator (this app has no local Android build - CI's phone-unit-tests is
 *    the first compiler - so the pure half is the half that gets proved);
 *  - [com.jarvis.client.data.PinnedChatStore] is then only the thin
 *    SharedPreferences wrapper, the same split [com.jarvis.client.net.CachedModels]
 *    and [com.jarvis.client.data.ModelsCacheStore] already use.
 *
 * WHAT IS KEPT, AND WHERE. One row per pinned message: the message's own
 * words, which chat it came from (its conversation id and the owner's
 * question, which is what makes "which chat" readable), and when it was
 * pinned. On THIS PHONE ONLY, in a private SharedPreferences file - no route
 * is added, nothing is sent to the PC, and the desktop's chat history is not
 * touched. The owner's own rule that "the phone keeps no history of its own"
 * (HistoryScreen) is about the PC's kept chats; this is the phone's own small
 * list of things the owner asked to keep in front of them, and it is gated by
 * the same "Hide memory lists and chat history" switch - [PinnedScreen] shows
 * [com.jarvis.client.ui.screens.HiddenSection] while that is on, exactly as
 * History and Brain's memory lists do.
 *
 * A PIN IS NOT A MARK. Marking an answer right or wrong (`feedback.patch`)
 * tells the PC something about its answer and never changes memory; pinning
 * touches nothing on the PC at all and is the owner's own bookmark.
 */

/**
 * One pinned message.
 *
 * [key] is the pin's identity, and the whole of "is this message already
 * pinned?": [ChatPins.key]. It is derived from the chat and the words, so the
 * same message cannot be pinned twice - by pinning it again from the answer on
 * screen, or from the same answer once it has moved into the thread above
 * (whose words are the same words, however the whitespace shifted).
 */
data class PinnedMessage(
    val key: String,
    /** The message's words, as kept. Never longer than [ChatPins.MAX_TEXT]. */
    val text: String,
    /** The conversation it came from, or "" when this chat is not kept in History. */
    val chatId: String,
    /** The owner's question that this answer replied to, one line, or "". */
    val chatLabel: String,
    /** When it was pinned, in epoch milliseconds ([System.currentTimeMillis]). */
    val atMs: Long,
)

object ChatPins {

    // ---- The words on screen ------------------------------------------------
    //
    // Kept here so a JVM test can hold them still, the same as ChatMark's and
    // ChatHistory's own words. Nothing in this object decides whether a row is
    // DRAWN - HomeScreen and PinnedScreen ask the state first.

    /** The screen's title. Since 2026-10-30 its way in is History's header. */
    const val TITLE = "Pinned messages"

    /**
     * The compact action in History's header (the owner's choice of
     * 2026-10-30: the list moved out of the More menu and into History).
     */
    const val ACTION = "Pinned"

    /** What that action does, for TalkBack - the list is the screen above, not a copy. */
    const val ACTION_TITLE = "Messages you pinned, newest first."

    /** One line at the top of the screen: what it is, and where it lives. */
    const val LEAD = "Messages you pinned, newest first. Kept on this phone only."

    /** Nothing pinned yet: where the control is, in plain words. */
    const val EMPTY =
        "Nothing pinned yet. Open an answer's chevron beside \"Jarvis\" and tap Pin message."

    /** The per-message menu's title - which message this menu is about. */
    const val MENU_TITLE = "This answer"

    /** Under the title: the menu is about one message, never the whole chat. */
    const val MENU_SUB = "One message: a mark, or a pin."

    /** The pin action, and the same row once the message is pinned. */
    const val PIN = "Pin message"
    const val UNPIN = "Unpin message"

    /** Under "Pin message": what pinning does, and where the list is. */
    const val PIN_DETAIL = "Kept on this phone. In History, under Pinned."

    /** Under "Unpin message". */
    const val UNPIN_DETAIL = "It goes from the list at once. Nothing else changes."

    /** A pin taken, and a pin taken back - said on Home, the app's own notice. */
    const val PIN_DONE = "Pinned. It is in History, under Pinned."
    const val UNPIN_DONE = "Unpinned."

    /**
     * A temporary chat: the PC keeps nothing of it, so the phone must not keep
     * a copy of it either. The row is drawn with this sentence instead of the
     * pin action - a control that silently did nothing would be worse.
     */
    const val TEMPORARY = "Temporary chat, so nothing here is pinned or kept."

    /** On the list: a pin whose chat is not kept in History (an older chat, or one deleted). */
    const val CHAT_NOT_KEPT = "From a chat that is not kept"

    /** "From your chat: <the question>" - which chat a pin came from. */
    const val CHAT_PREFIX = "From your chat: "

    /** The chat's id is known but its question was blank: still says which chat. */
    const val CHAT_ON_PC = "From a chat on your PC"

    /** The button that opens the chat a pin came from. */
    const val OPEN_CHAT = "Open chat"

    /** The sentence under the list: where the other chats are, since the owner asked. */
    const val WHERE_CHATS_ARE =
        "Earlier chats are in History, one tap from Home. New chat starts a fresh one."

    /** How many pins the phone keeps: past this, pinning waits for an unpin. */
    const val CAP = 100

    /** The most of one message the phone keeps. A longer one is cut at this, with "…". */
    const val MAX_TEXT = 2000

    /** The most of the owner's question kept as "which chat". One line, this long. */
    const val MAX_LABEL = 90

    /** How much of a message a list row draws before "…". */
    const val ROW_TEXT = 240

    /** What the menu and the notice say when the list is full. There is no silent drop. */
    fun full(): String = "You can pin up to $CAP messages. Unpin one to make room."

    // ---- Identity -----------------------------------------------------------

    private val WHITESPACE = Regex("\\s+")

    /**
     * One message's words with every run of whitespace made one space, and both
     * ends trimmed.
     *
     * This is the form the identity digest is taken over, so the answer on
     * screen and the same answer once it has moved into the thread above (a
     * different paragraph break, a trailing newline) are ONE message, not two.
     * It is also what a row draws, and what a temporary chat's refusal is
     * measured against.
     */
    fun normalise(text: String): String = text.trim().replace(WHITESPACE, " ")

    /**
     * The first [max] characters of [text] as one line, with "…" when it was
     * cut. Never longer than max + 1.
     */
    fun snippet(text: String, max: Int = ROW_TEXT): String {
        val flat = normalise(text)
        if (flat.length <= max) return flat
        return flat.take(max).trimEnd() + "…"
    }

    /**
     * The identity of the pin for [text] in the chat [chatId]: the chat id plus
     * 16 hex characters of a SHA-256 over the normalised words.
     *
     * Two different messages can in principle collide (64 bits), which would
     * cost one duplicate pin - never a lost message, since the row keeps its
     * own words. A whole message as the key would grow without bound in a
     * SharedPreferences file; this does not.
     */
    fun key(chatId: String, text: String): String {
        val digest = MessageDigest.getInstance("SHA-256")
            .digest(normalise(text).toByteArray(Charsets.UTF_8))
        val hex = digest.take(8).joinToString("") { "%02x".format(it) }
        return "$chatId#$hex"
    }

    /** [label] (the owner's question) as "which chat": one line, at most [MAX_LABEL]. */
    fun chatLabel(question: String?): String = snippet(question.orEmpty(), MAX_LABEL)

    // ---- The list -----------------------------------------------------------

    /** True when this exact message is already pinned. */
    fun has(rows: List<PinnedMessage>, chatId: String, text: String): Boolean {
        if (normalise(text).isEmpty()) return false
        val wanted = key(chatId, text)
        return rows.any { it.key == wanted }
    }

    /** True when no more pins fit - the menu says [full] instead of offering a pin. */
    fun full(rows: List<PinnedMessage>): Boolean = rows.size >= CAP

    /**
     * The list with [text] pinned at the top, or the SAME list when nothing
     * changed: blank words, a message already pinned (pinning twice is not two
     * pins), or a list already at [CAP].
     *
     * The cap REFUSES rather than dropping the oldest: a list that quietly
     * forgets what the owner pinned is worse than one that says why it cannot
     * take another. The caller draws [full] in place of the pin action.
     */
    fun pin(
        rows: List<PinnedMessage>,
        chatId: String,
        // The owner's question: what the list shows as "which chat".
        label: String,
        text: String,
        atMs: Long,
    ): List<PinnedMessage> {
        val words = normalise(text)
        if (words.isEmpty()) return rows
        if (full(rows)) return rows
        val pinKey = key(chatId, text)
        if (rows.any { it.key == pinKey }) return rows
        val kept = if (words.length <= MAX_TEXT) words else words.take(MAX_TEXT).trimEnd() + "…"
        val row = PinnedMessage(
            key = pinKey,
            text = kept,
            chatId = chatId,
            chatLabel = chatLabel(label),
            atMs = atMs,
        )
        return newestFirst(listOf(row) + rows)
    }

    /**
     * The same list without the pin [key], or the SAME list when it was not
     * there - the caller tells "something changed" from "nothing changed" by
     * identity, so an unpin of a pin that has already gone is not written to
     * disk and says nothing.
     */
    fun unpin(rows: List<PinnedMessage>, key: String): List<PinnedMessage> {
        if (rows.none { it.key == key }) return rows
        return rows.filterNot { it.key == key }
    }

    /**
     * Newest first. Sorting by the pin's own moment keeps the list in the order
     * the owner pinned things, even after a restart; `sortedByDescending` is
     * stable, so two pins made in the same millisecond keep the order they were
     * added in.
     */
    fun newestFirst(rows: List<PinnedMessage>): List<PinnedMessage> =
        rows.sortedByDescending { it.atMs }

    // ---- What a row says ----------------------------------------------------

    /**
     * How long ago [atMs] was, in plain words - "just now", "3 minutes ago",
     * "2 days ago", "over a year ago".
     *
     * Deliberately arithmetic only: no time zone, no locale, no calendar. A
     * clock that has gone backwards (an NTP correction, a time the owner set)
     * reads "just now" rather than "-2 minutes ago".
     */
    fun ageLine(atMs: Long, nowMs: Long): String {
        val ms = nowMs - atMs
        if (ms < 60_000L) return "just now"
        val minutes = ms / 60_000L
        if (minutes < 60L) return counted(minutes, "minute")
        val hours = minutes / 60L
        if (hours < 24L) return counted(hours, "hour")
        val days = hours / 24L
        if (days < 7L) return counted(days, "day")
        val weeks = days / 7L
        if (weeks < 5L) return counted(weeks, "week")
        // Past five weeks the months line takes over; it is never 0 here
        // (35 days is one month), so there is no "0 months ago".
        val months = days / 30L
        return if (months < 12L) counted(months, "month") else "over a year ago"
    }

    private fun counted(n: Long, unit: String): String =
        if (n == 1L) "1 $unit ago" else "$n ${unit}s ago"

    /**
     * Which chat a pin came from, in one line: the owner's question when the
     * phone kept it, otherwise that it was a chat on the PC, otherwise that the
     * chat is not kept at all (a temporary chat, or a conversation deleted
     * since).
     */
    fun chatLine(row: PinnedMessage): String = when {
        row.chatLabel.isNotEmpty() -> CHAT_PREFIX + row.chatLabel
        row.chatId.isNotEmpty() -> CHAT_ON_PC
        else -> CHAT_NOT_KEPT
    }

    /** A row's second line: which chat, then how long ago. */
    fun whereLine(row: PinnedMessage, nowMs: Long): String =
        chatLine(row) + " · " + ageLine(row.atMs, nowMs)

    /** True when the row offers [OPEN_CHAT] - the chat has an id History can be asked for. */
    fun opens(row: PinnedMessage): Boolean = row.chatId.isNotEmpty()

    // ---- Kept on disk -------------------------------------------------------
    //
    // One JSON array under one key (PinnedChatStore). The shape is this app's
    // own private format - no route, no contract, nothing the PC reads - so it
    // is named in this file and nowhere else.

    /** The pins as the one string the store keeps. */
    fun toJson(rows: List<PinnedMessage>): String = buildJsonArray {
        for (row in rows) {
            add(
                buildJsonObject {
                    put("key", row.key)
                    put("text", row.text)
                    put("chat_id", row.chatId)
                    put("chat_label", row.chatLabel)
                    put("at_ms", row.atMs)
                },
            )
        }
    }.toString()

    /**
     * The pins back from the store: newest first, at most [CAP], and never a
     * throw. A file that cannot be read, a shape this version does not know, a
     * row missing its words or its key - each reads as "not a pin", so a
     * corrupt file costs the rows it damaged and never the screen.
     */
    fun fromJson(raw: String?): List<PinnedMessage> {
        if (raw.isNullOrBlank()) return emptyList()
        val array = runCatching { JarvisJson.parseToJsonElement(raw) as? JsonArray }.getOrNull()
            ?: return emptyList()
        val byKey = LinkedHashMap<String, PinnedMessage>()
        for (element in array) {
            val o = element as? JsonObject ?: continue
            val key = o.str("key")?.takeIf { it.isNotBlank() } ?: continue
            val text = o.str("text")?.takeIf { it.isNotBlank() } ?: continue
            byKey[key] = PinnedMessage(
                key = key,
                text = text,
                chatId = o.str("chat_id").orEmpty(),
                chatLabel = o.str("chat_label").orEmpty(),
                atMs = o.long("at_ms") ?: 0L,
            )
        }
        return newestFirst(byKey.values.toList()).take(CAP)
    }

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content

    private fun JsonObject.long(key: String): Long? =
        (this[key] as? JsonPrimitive)?.longOrNull
}
