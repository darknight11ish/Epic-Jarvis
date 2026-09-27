package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import java.net.URLEncoder
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Chat history on the PC - the phone's side of docs/JARVIS-API.md section
 * 18 ("Chat history", added 2026-09-24).
 *
 * The owner decided (CLAUDE.md, 2026-09-24) that chat history, voice
 * included, is kept ON THE PC by default, encrypted, with a switch to turn
 * it off. Turning it back on asks first, with an approval card; turning it
 * off is immediate - the same shape as the learning switch ([MemoryCounts]).
 *
 * THE PHONE STORES NO HISTORY. Everything on the History screen is read from
 * the PC when it is opened and dropped when it is left, like every other
 * list on Mind. Nothing here is written to the phone's disk.
 *
 * The routes, all with the pairing token like every other:
 * - `GET /api/history?limit=30&before=<updated>` - the switch, why nothing is
 *   being kept (if so), how long it is kept, and conversations newest first.
 * - `GET /api/history/conversation?id=` - one conversation, read-only.
 * - `POST /api/history/delete {"id"}` - one conversation. There is no
 *   "delete all" route, on purpose.
 * - `POST /api/history/settings` - `{"enabled"}` or `{"keep_days"}`.
 *
 * Pure Kotlin, no Android types, so `ChatLogTest` runs it on a plain JVM.
 */
object ChatLog {
    const val LIST_PATH = "/api/history"
    const val CONVERSATION_PATH = "/api/history/conversation"
    const val DELETE_PATH = "/api/history/delete"
    const val SETTINGS_PATH = "/api/history/settings"

    /** The gate action the PC raises the ON card under. */
    const val ENABLE_ACTION = "history_enable"

    /** Conversations per page. The PC takes 1-100 and defaults to 30. */
    const val PAGE = 30

    /** The only `keep_days` values the PC accepts: 0 is "until I delete them". */
    val KEEP_DAYS = listOf(0, 30, 90, 365)

    // ----------------------------------------------------------- words ---

    const val SWITCH = "Keep chat history on this PC"
    const val UNDER =
        "Your chats, including what you say to Jarvis by voice, are kept on this PC, " +
            "encrypted. Nothing is sent anywhere."
    const val OFF_SAID =
        "Chat history is off. Nothing new is kept. What is already kept stays until you delete it."
    const val KEEP_TITLE = "Delete conversations older than"
    const val WAITING = "Waiting for your approval to turn chat history on. ${Approvals.WHERE}"
    const val EMPTY = "No conversations are kept on your PC."
    /** Under Delete, in both apps: deleting a chat is not forgetting (ease-of-use audit #7). */
    const val DELETE_KEEPS_FACTS =
        "Deleting a chat does not forget facts Jarvis learned from it. Forget those one by one in the Brain."
    const val DELETE_CONFIRM = "Delete this conversation from your PC? This cannot be undone. $DELETE_KEEPS_FACTS"
    /** Search box, over the list already loaded (ease-of-use audit row 20;
     *  the owner's answer of 2026-09-27: "shown on screen only; nothing
     *  saved, nothing handed to the AI"). The desktop says the same
     *  (brain.js `paintHistoryList`). */
    const val SEARCH_PLACEHOLDER = "Search this list…"
    const val NO_MATCH = "No conversations match that search."

    // ----------------------------------------------------------- paths ---

    /** One page, newest first. [before] is the `updated` time of the oldest row already shown. */
    fun listPath(before: Long? = null, limit: Int = PAGE): String =
        "$LIST_PATH?limit=${limit.coerceIn(1, 100)}" + (before?.let { "&before=$it" } ?: "")

    fun conversationPath(id: String): String = "$CONVERSATION_PATH?id=${URLEncoder.encode(id, "UTF-8")}"

    fun deleteBody(id: String): String = buildJsonObject { put("id", id) }.toString()

    fun enabledBody(on: Boolean): String = "{\"enabled\":$on}"

    /** Null for a value the PC does not accept - nothing is sent. */
    fun keepDaysBody(days: Int): String? = if (days in KEEP_DAYS) "{\"keep_days\":$days}" else null

    // -------------------------------------------------------- reading ---

    /** The settings half of `GET /api/history`. A field the PC did not send is null. */
    data class Status(
        val enabled: Boolean?,
        val recording: Boolean?,
        val whyNot: String?,
        val waiting: Boolean,
        val keepDays: Int?,
        val encrypted: Boolean?,
    )

    /** One row of the list. */
    data class Summary(
        val id: String,
        val title: String,
        val started: Long?,
        val updated: Long?,
        val turns: Int?,
        val device: String?,
        val hasVoice: Boolean,
        /** A turn in it read text from outside (a tool ran): from that turn on. */
        val tainted: Boolean,
    )

    /** One page: the settings, its rows, and whether there may be older ones. */
    data class Page(val status: Status, val conversations: List<Summary>, val mayHaveOlder: Boolean)

    /** One message of an opened conversation. */
    data class Turn(
        val role: String,
        val text: String,
        val at: Long?,
        val provenance: String?,
        val readOutside: Boolean,
        /** False on a user turn whose answer the PC did not keep (a cloud answer, or one that did not finish). */
        val answerKept: Boolean = true,
    )

    data class Transcript(val id: String, val title: String, val tainted: Boolean, val turns: List<Turn>)

    private fun JsonObject.prim(key: String): JsonPrimitive? = this[key] as? JsonPrimitive

    private fun JsonObject.str(key: String): String? =
        prim(key)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? = prim(key)?.takeIf { !it.isString }?.booleanOrNull

    private fun JsonObject.whole(key: String): Long? = prim(key)?.takeIf { !it.isString }?.longOrNull

    fun status(body: JsonObject): Status = Status(
        enabled = body.flag("enabled"),
        recording = body.flag("recording"),
        whyNot = body.str("why_not"),
        waiting = body.flag("waiting") == true,
        keepDays = body.whole("keep_days")?.toInt(),
        encrypted = body.flag("encrypted"),
    )

    /**
     * `GET /api/history`. A row with no id cannot be opened or deleted, so it
     * is left out. [asked] is the `limit` that was sent: a full page means
     * there may be older conversations.
     */
    fun page(body: JsonObject, asked: Int = PAGE): Page {
        val rows = (body["conversations"] as? JsonArray).orEmpty().mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val id = o.str("id") ?: return@mapNotNull null
            Summary(
                id = id,
                title = o.str("title") ?: UNTITLED,
                started = o.whole("started"),
                updated = o.whole("updated"),
                turns = o.whole("turns")?.toInt(),
                device = o.str("device"),
                hasVoice = o.flag("has_voice") == true,
                tainted = o.flag("tainted") == true,
            )
        }
        val raw = (body["conversations"] as? JsonArray)?.size ?: 0
        return Page(status(body), rows, mayHaveOlder = raw >= asked)
    }

    /** `GET /api/history/conversation`, or null when it is not one. */
    fun transcript(body: JsonObject): Transcript? {
        val id = body.str("id") ?: return null
        val turns = (body["turns"] as? JsonArray).orEmpty().mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val role = o.str("role") ?: return@mapNotNull null
            Turn(
                role = role,
                text = (o["text"] as? JsonPrimitive)?.contentOrNull.orEmpty(),
                at = o.whole("at"),
                provenance = o.str("provenance"),
                readOutside = o.flag("read_outside") == true,
                // Only "false" from the PC says so; an older PC sends nothing.
                answerKept = o.flag("answer_kept") != false,
            )
        }
        return Transcript(id, body.str("title") ?: UNTITLED, body.flag("tainted") == true, turns)
    }

    const val UNTITLED = "Untitled conversation"

    /** [more] after [shown], without a row twice: two rows can share one `updated` second. */
    fun append(shown: List<Summary>, more: List<Summary>): List<Summary> {
        val seen = shown.mapTo(HashSet()) { it.id }
        return shown + more.filter { seen.add(it.id) }
    }

    /** What "Load older" asks for: rows updated before the oldest one shown. */
    fun olderThan(shown: List<Summary>): Long? = shown.mapNotNull { it.updated }.minOrNull()

    /**
     * The search box: [shown] narrowed to rows whose title has [needle],
     * case-insensitively. Pure, client-side, over the list already loaded -
     * no new route, nothing saved, nothing handed to the AI (the owner's
     * answer of 2026-09-27). A blank [needle] returns [shown] unchanged.
     */
    fun filtered(shown: List<Summary>, needle: String): List<Summary> {
        val n = needle.trim()
        if (n.isEmpty()) return shown
        return shown.filter { it.title.contains(n, ignoreCase = true) }
    }

    // --------------------------------------------------------- switch ---

    /** What the switch shows. */
    enum class Switch { ON, OFF, WAITING, UNKNOWN }

    /** Is the ON card in the approval queue? */
    fun cardWaiting(actions: List<String?>): Boolean = actions.any { it == ENABLE_ACTION }

    /**
     * ON only when the PC says it is on. Waiting while the ON card is in the
     * queue or the PC says it is waiting - never "on" before a real approval.
     */
    fun switchState(status: Status?, cardInQueue: Boolean): Switch = when {
        status?.enabled == true -> Switch.ON
        cardInQueue || status?.waiting == true -> Switch.WAITING
        status?.enabled == false -> Switch.OFF
        else -> Switch.UNKNOWN
    }

    /** The line under the switch. [why_not] is said plainly whenever nothing is being kept. */
    fun stateLine(switch: Switch, status: Status?): String = when (switch) {
        Switch.ON -> if (status?.recording == false) {
            "On, but nothing new is being kept right now. " +
                (status.whyNot?.let { DesktopWrite.asSentence(it) } ?: "Your PC did not say why.")
        } else {
            "On. New chats are kept on your PC, encrypted."
        }
        Switch.OFF -> "Off. Nothing new is kept. What is already kept stays until you delete it." +
            " Turning it on asks you first, with an approval card."
        Switch.WAITING -> WAITING
        Switch.UNKNOWN -> "Couldn't tell whether chat history is on."
    }

    /** What to say after the switch was pressed, from the PC's answer. */
    fun enableSaid(on: Boolean, outcome: DesktopWrite.Outcome): String = when (outcome) {
        is DesktopWrite.Outcome.Waiting -> WAITING
        is DesktopWrite.Outcome.Refused -> "Not changed. ${outcome.why}"
        is DesktopWrite.Outcome.Done -> outcome.said?.let { DesktopWrite.asSentence(it) }
            ?: if (on) "Chat history is on." else OFF_SAID
    }

    // --------------------------------------------------------- delete ---

    /** Said when the PC answers 404: it is gone either way. */
    const val ALREADY_GONE = "It was not on your PC any more."

    /**
     * After a 2xx from `/api/history/delete`: whether it is gone, and what to
     * say. `ok: false` is the PC saying no, in its own words.
     */
    fun deleteSaid(body: JsonObject): Pair<Boolean, String> =
        if (body.flag("ok") == false) {
            val why = body.str("error") ?: body.str("reason") ?: body.str("message")
            false to ("Not deleted. " + (why?.let { DesktopWrite.asSentence(it) } ?: "Your PC said no, without a reason."))
        } else {
            true to (body.str("message")?.let { DesktopWrite.asSentence(it) } ?: "Deleted from your PC.")
        }

    // ------------------------------------------------------ keep days ---

    fun keepLabel(days: Int): String = when (days) {
        0 -> "Never"
        365 -> "1 year"
        else -> "$days days"
    }

    /**
     * Whether choosing [to] deletes something now, and so asks first: any
     * limit, when there was none or a longer one. Going back to "Never", or to
     * a longer limit, deletes nothing.
     */
    fun keepNeedsConfirm(from: Int?, to: Int): Boolean =
        to != 0 && (from == null || from == 0 || to < from)

    fun keepConfirm(to: Int): String =
        "Delete every conversation older than ${keepLabel(to).lowercase(Locale.US)} from your PC now, " +
            "and from then on? This cannot be undone."

    /**
     * What to say after a `keep_days` change. The PC's own sentence first;
     * else its count of deleted conversations, when it sends one as
     * `deleted`; else a plain "done".
     */
    fun keepSaid(days: Int, body: JsonObject?): String {
        body?.str("message")?.let { return DesktopWrite.asSentence(it) }
        val deleted = body?.whole("deleted")
        val kept = if (days == 0) {
            "Conversations are kept until you delete them."
        } else {
            "Conversations older than ${keepLabel(days).lowercase(Locale.US)} are deleted."
        }
        return when (deleted) {
            null -> "Done. $kept"
            0L -> "Done. $kept None were old enough to delete now."
            1L -> "Done. $kept 1 conversation was deleted now."
            else -> "Done. $kept $deleted conversations were deleted now."
        }
    }

    // --------------------------------------------------------- showing ---

    private val TIME = DateTimeFormatter.ofPattern("HH:mm")
    // With the weekday, so "Tuesday's chat" can be found (ease-of-use audit #7).
    private val DAY = DateTimeFormatter.ofPattern("EEE d MMM", Locale.US)
    private val DAY_YEAR = DateTimeFormatter.ofPattern("EEE d MMM yyyy", Locale.US)

    /** "Today 14:05", "Yesterday 09:12", "Sat 12 Sep 18:30", "Fri 3 Jan 2025". */
    fun whenLine(epochSeconds: Long?, zone: ZoneId, today: LocalDate): String {
        if (epochSeconds == null) return "When unknown"
        val at = Instant.ofEpochSecond(epochSeconds).atZone(zone)
        val day = at.toLocalDate()
        val clock = TIME.format(at)
        return when {
            day == today -> "Today $clock"
            day == today.minusDays(1) -> "Yesterday $clock"
            day.year == today.year -> "${DAY.format(at)} $clock"
            else -> DAY_YEAR.format(at)
        }
    }

    /** The small line under a row's title: when, where, and its marks, in words. */
    fun rowLine(row: Summary, zone: ZoneId, today: LocalDate): String = listOfNotNull(
        whenLine(row.updated ?: row.started, zone, today),
        deviceWord(row.device),
        row.turns?.let { if (it == 1) "1 message" else "$it messages" },
    ).joinToString(" · ")

    /**
     * Which app a conversation was had in. The same words as the desktop's
     * History (one wording for both apps, fit audit 2026-09-24); a device
     * the PC did not name - or an older PC that sends none - is "unknown",
     * never left out.
     */
    fun deviceWord(device: String?): String = when (device) {
        "phone" -> "phone"
        "desktop" -> "PC"
        "hud" -> "HUD"
        else -> "unknown"
    }

    /**
     * The quiet mark on a user turn whose words were not the owner's own
     * typing or voice, or null for those two. Anything else - "unknown", a
     * tag this phone does not know, or no tag at all - is "not known where
     * from": never silence, because silence would read as "you typed it".
     * The same words as the desktop's History.
     */
    fun provenanceMark(provenance: String?): String? = when (provenance) {
        Provenance.TYPED, Provenance.VOICE -> null
        Provenance.SHARED -> "shared from another app"
        Provenance.PASTED -> "pasted"
        "clipboard" -> "from clipboard"
        Provenance.PICTURE_CAPTION -> "sent with a picture"
        "voice_unverified" -> "said aloud, but not confirmed by this PC"
        else -> UNKNOWN_MARK
    }

    /**
     * Under a question whose answer the PC did not keep (`answer_kept: false`):
     * a cloud model's answer, or one that did not finish. The PC does not say
     * which, so neither does this. The same sentence as the desktop's.
     */
    const val NOT_KEPT_LINE = "Jarvis's answer to this was not kept: it came from a cloud model, or it did not finish."

    const val UNKNOWN_MARK = "not known where from"
    const val VOICE_MARK = "voice"
    const val TAINT_MARK = "read outside text"

    /** Said once above a tainted transcript. The same sentence as the desktop's. */
    const val TAINT_LINE =
        "In this conversation Jarvis read text that did not come from you - a web page, a file, " +
            "an email or another tool's output - from the marked message on."

    /** Why the phone could not do something with History - in the PC's words when there are some. */
    fun failure(e: ApiError): String? = when (e) {
        ApiError.NotFound -> "That is not on your PC any more, or this PC's Jarvis has no chat history yet."
        ApiError.NotAvailable -> "Chat history is not running on your PC right now."
        else -> null
    }
}
