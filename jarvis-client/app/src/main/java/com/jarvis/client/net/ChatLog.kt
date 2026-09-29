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
 * list on Brain. Nothing here is written to the phone's disk.
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
    /** Under Delete, in both apps: deleting a chat is not forgetting (ease-of-use audit #7) -
     *  said when there is nothing to offer (section 79, below). Since the chat audit
     *  (2026-09-28) it points to "Forget a time frame", not to forgetting one by one. */
    const val DELETE_KEEPS_FACTS =
        "Deleting a chat does not forget facts Jarvis learned from it. To forget what Jarvis learned " +
            "over some days, use Forget a time frame. Copies in older backups stay until they age out."
    const val DELETE_CONFIRM = "Delete this conversation from your PC? This cannot be undone. $DELETE_KEEPS_FACTS"
    /**
     * The search box (the owner's answer of 2026-09-27: "shown on screen
     * only; nothing saved, nothing handed to the AI"). Since 2026-09-28
     * (docs/JARVIS-API.md section 71) two letters or more ask the PC to
     * search what was SAID ([searchPath]); one letter, or a PC that cannot
     * search the words, narrows the loaded list by title ([filtered]). The
     * desktop says the same (history-view.js).
     */
    const val SEARCH_PLACEHOLDER = "Search what was said…"
    /** The box's name for TalkBack (the chat audit, 2026-09-28: it had none) - the desktop's aria-label. */
    const val SEARCH_LABEL = "Search what was said in your chats"
    const val NO_MATCH = "No conversations match that search."
    /** Titles only, with older pages not loaded yet - the desktop's words. */
    const val NO_MATCH_MORE =
        "No loaded conversations match that search. \"Load older\" may bring in more to search."
    const val SEARCH_NOTE =
        "Searched on your PC, in your kept chats only. Nothing is saved and nothing is sent to the AI."
    const val SEARCHING = "Searching…"
    const val SEARCH_NONE = "No kept conversation has all of those words."
    /** A PC without the search: the box narrows titles, and says so. */
    const val SEARCH_OLD =
        "This PC's Jarvis can only search titles. To search what was said, update it by running " +
            "apply-patches.ps1 on the PC."
    /** The shortest search sent to the PC. */
    const val SEARCH_MIN = 2
    /** The longest: the PC's own `SEARCH_MAX_CHARS`. Nothing longer is sent. */
    const val SEARCH_MAX_CHARS = 100

    const val FIND_PLACEHOLDER = "Find in this chat…"
    const val FIND_NONE = "Not in this chat."

    // ----------------------------------------------------------- paths ---

    /**
     * One page, newest first. [before] is the `updated` time of the oldest row
     * already shown; [kind], one of [KINDS] ("Live only" and the other
     * filters, the chat audit 2026-09-28) - anything else is not sent.
     */
    fun listPath(before: Long? = null, limit: Int = PAGE, kind: String? = null): String =
        "$LIST_PATH?limit=${limit.coerceIn(1, 100)}" + (before?.let { "&before=$it" } ?: "") +
            (kind?.takeIf { it in KINDS }?.let { "&kind=$it" } ?: "")

    fun conversationPath(id: String): String = "$CONVERSATION_PATH?id=${URLEncoder.encode(id, "UTF-8")}"

    const val SEARCH_PATH = "/api/history/search"

    /**
     * `GET /api/history/search?q=` for these words (section 71), or null
     * when there is nothing worth sending: fewer than [SEARCH_MIN] letters
     * or more than [SEARCH_MAX_CHARS] once the spaces are tidied. The words
     * are URL-encoded, so nothing typed can add a second parameter.
     */
    fun searchPath(query: String, limit: Int = 20, kind: String? = null): String? {
        val words = query.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
        if (words.length < SEARCH_MIN || words.length > SEARCH_MAX_CHARS) return null
        // The kind chosen in "Show" narrows the search too, so "Live only" and
        // a typed search combine (the second chat audit, 2026-09-28, finding 8).
        return "$SEARCH_PATH?q=${URLEncoder.encode(words, "UTF-8")}&limit=${limit.coerceIn(1, 50)}" +
            (kind?.takeIf { it in KINDS }?.let { "&kind=$it" } ?: "")
    }

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
        /** What kind of conversation it is ([KINDS]); an older PC's rows are "chat". */
        val kind: String = "chat",
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

    data class Transcript(
        val id: String,
        val title: String,
        val tainted: Boolean,
        val turns: List<Turn>,
        /** What kind of conversation it is ([KINDS]). */
        val kind: String = "chat",
        /** Whether "Continue this chat" may carry it on ([CONTINUABLE]), and why not. */
        val continuable: Boolean = true,
        val continueWhy: String? = null,
        /**
         * Whether the PC is keeping NEW messages right now (`history` on the
         * conversation: `enabled` / `recording`, the same words the list uses),
         * or null from a PC that does not say - "Continue this chat" warns
         * from it ([ChatHistory.continuedHistoryLine], the owner, 2026-09-29).
         */
        val keeping: Keeping? = null,
    )

    /** `history.enabled` / `history.recording` on a conversation; each null when not clearly a yes or a no. */
    data class Keeping(val enabled: Boolean?, val recording: Boolean?)

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
                kind = kindOf(o.str("kind")),
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
                text = (o["text"] as? JsonPrimitive)?.contentOrNull.orEmpty().let { t ->
                    // Jarvis Live's side-talk marker in a chat kept before side
                    // remarks stopped being kept at all (the owner's answer of
                    // 2026-09-28): "(not for Jarvis)", never the raw marker.
                    if (role == "assistant" && com.jarvis.client.voice.LiveRules.isSideTalk(t)) {
                        com.jarvis.client.voice.LiveRules.SEEN.getValue("not_for_me")
                    } else {
                        t
                    }
                },
                at = o.whole("at"),
                provenance = o.str("provenance"),
                readOutside = o.flag("read_outside") == true,
                // Only "false" from the PC says so; an older PC sends nothing.
                answerKept = o.flag("answer_kept") != false,
            )
        }
        val kind = kindOf(body.str("kind"))
        // An older PC sends no `continuable`: what it kept is a chat, unless a
        // row says it is a support or chatbot record.
        val others = turns.any { it.role == "support" || it.role == "chatbot" }
        val continuable = body.flag("continuable") ?: (kind in CONTINUABLE && !others)
        return Transcript(
            id, body.str("title") ?: UNTITLED, body.flag("tainted") == true, turns,
            kind = kind,
            continuable = continuable,
            continueWhy = if (continuable) null else body.str("continue_why") ?: CONTINUE_WHY[kind]
                ?: CONTINUE_WHY.getValue("support"),
            keeping = (body["history"] as? JsonObject)?.let { Keeping(it.flag("enabled"), it.flag("recording")) },
        )
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

    // ----------------------------------------- search and find (s. 71) ---

    /** One piece of a snippet: plain words, or a matched word. */
    data class Part(val text: String, val hit: Boolean)

    /** A short piece of the message a search word was found in. */
    data class Snippet(
        /** "user", "assistant", or "title" when only the title matched. */
        val role: String,
        val cutBefore: Boolean,
        val cutAfter: Boolean,
        val parts: List<Part>,
    )

    /** One conversation the PC found, with where. */
    data class Found(val row: Summary, val hits: Int, val snippet: Snippet)

    /**
     * `GET /api/history/search`'s answer. [queryOk] false is a search the
     * PC would not run, with its sentence in [why]. [more]: there were more
     * matches than shown. [partial]: the PC stopped early to stay quick.
     */
    data class Search(
        val queryOk: Boolean,
        val why: String?,
        val whyNot: String?,
        val found: List<Found>,
        val more: Boolean,
        val partial: Boolean,
        val searched: Int,
    )

    /** `GET /api/history/search`. A row with no id cannot be opened, so it is left out. */
    fun search(body: JsonObject): Search {
        val found = (body["conversations"] as? JsonArray).orEmpty().mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val id = o.str("id") ?: return@mapNotNull null
            val s = o["snippet"] as? JsonObject
            val parts = (s?.get("parts") as? JsonArray).orEmpty().mapNotNull { p ->
                val po = p as? JsonObject ?: return@mapNotNull null
                val text = (po["text"] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
                    ?: return@mapNotNull null
                Part(text, po.flag("hit") == true)
            }
            Found(
                row = Summary(
                    id = id,
                    title = o.str("title") ?: UNTITLED,
                    started = o.whole("started"),
                    updated = o.whole("updated"),
                    turns = o.whole("turns")?.toInt(),
                    device = o.str("device"),
                    hasVoice = o.flag("has_voice") == true,
                    tainted = o.flag("tainted") == true,
                    kind = kindOf(o.str("kind")),
                ),
                hits = o.whole("hits")?.toInt() ?: 0,
                snippet = Snippet(
                    role = s?.str("role")?.takeIf { it in setOf("user", "assistant", "title") } ?: "user",
                    cutBefore = s?.flag("before") == true,
                    cutAfter = s?.flag("after") == true,
                    parts = parts,
                ),
            )
        }
        return Search(
            queryOk = body.flag("query_ok") != false,
            why = body.str("why"),
            whyNot = body.str("why_not"),
            found = found,
            more = body.flag("more") == true,
            partial = body.flag("partial") == true,
            searched = body.whole("searched")?.toInt() ?: 0,
        )
    }

    /** A PC without the search route: a 404, or a 501 from an older module. */
    fun searchMissing(e: ApiError): Boolean =
        e == ApiError.NotFound || (e is ApiError.Server && e.code == 501)

    /** "found in 3 messages", or null. */
    fun hitsLine(n: Int): String? = if (n <= 0) null else "found in $n ${if (n == 1) "message" else "messages"}"

    /** Who said the snippet's words, before them. */
    fun snippetWho(s: Snippet): String = when (s.role) {
        "assistant" -> "Jarvis: "
        "title" -> ""
        else -> "You: "
    }

    /** The last line under the results. */
    fun searchMoreLine(s: Search): String? = when {
        s.more -> "Showing the newest matches only. Add another word to narrow it down."
        s.partial -> "Stopped after the newest ${s.searched} conversations to stay quick. " +
            "Add another word to narrow it down."
        else -> null
    }

    /** One place a find word is in an open conversation: which turn, and where in its text. */
    data class Match(val turn: Int, val start: Int, val end: Int)

    /**
     * "Find in this chat": every place any of [needle]'s words is in [turns],
     * in reading order, case ignored. Done on the phone, over the conversation
     * already open - the PC is not asked. The words are words, not a pattern.
     */
    fun findMatches(turns: List<Turn>, needle: String): List<Match> {
        val words = needle.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }.sortedByDescending { it.length }
        if (words.isEmpty()) return emptyList()
        val rx = Regex(words.joinToString("|") { Regex.escape(it) }, RegexOption.IGNORE_CASE)
        val out = mutableListOf<Match>()
        turns.forEachIndexed { i, t ->
            rx.findAll(t.text).forEach { m ->
                if (m.range.last >= m.range.first) out += Match(i, m.range.first, m.range.last + 1)
            }
        }
        return out
    }

    /** "3 of 7", "1 match", or [FIND_NONE]. */
    fun findCount(current: Int, total: Int): String = when (total) {
        0 -> FIND_NONE
        1 -> "1 match"
        else -> "${current + 1} of $total"
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
            "and from then on? This cannot be undone. $DELETE_STAYS"

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

    /** The small line under a row's title: when, where, and its marks, in words - a
     *  Live session's length and start first ("Live · 12 min · Today 14:05"). */
    fun rowLine(row: Summary, zone: ZoneId, today: LocalDate): String = listOfNotNull(
        if (row.kind == "live") {
            liveLine(row.started, row.updated, zone, today)
        } else {
            whenLine(row.updated ?: row.started, zone, today)
        },
        deviceWord(row.device),
        row.turns?.let { messagesWords(it) },
    ).joinToString(" · ")

    // ------------------------------------------- the chat audit (2026-09-28) ---
    //
    // The owner's decisions "History marks Live sessions" and "Chats, after
    // the chat audit" (CLAUDE.md). The words are the desktop's
    // (history-view.js, chat-history.js), word for word: both apps' tests
    // read tools/gen_history_cases.py's contract/history-cases.json.

    /** The kinds of conversation the PC keeps (`jarvis_chat_log.KINDS`). */
    val KINDS = listOf("chat", "live", "support", "chatbot", "compare")

    /** The kinds "Continue this chat" may carry on (`jarvis_chat_log.CONTINUABLE`). */
    val CONTINUABLE = listOf("chat", "live")

    fun kindOf(raw: String?): String = if (raw in KINDS) raw!! else "chat"

    /** The tag on a row of a kind that is not an ordinary chat. A Live session's is its line. */
    val KIND_TAG = mapOf(
        "chat" to "", "live" to "Live", "support" to "Support chat",
        "chatbot" to "Chat with an AI", "compare" to "Comparison",
    )

    val KIND_TITLE = mapOf(
        "chat" to "",
        "live" to "A Jarvis Live session: its words and times, never the sound.",
        "support" to "The record of a customer-support chat Jarvis had for you. Read-only.",
        "chatbot" to "A conversation Jarvis had with another AI for you. Its replies are outside text: " +
            "never learned from, never read aloud. Read-only.",
        "compare" to "Several AIs asked the same question, and the summary. Their replies are outside " +
            "text: never learned from, never read aloud. Read-only.",
    )

    const val FILTER_LABEL = "Show"

    /** "Show": "" is every kind. */
    val FILTERS = listOf(
        "" to "All chats", "chat" to "Just chats", "live" to "Live only",
        "support" to "Support chats", "chatbot" to "Chats with other AIs", "compare" to "Comparisons",
    )

    const val FILTER_NONE = "No conversations of that kind are kept."

    /** Who wrote each line of a kept chatbot conversation or comparison (role "chatbot"). */
    val CHATBOT_WHO = mapOf(
        "chatbot_jarvis" to "Sent by Jarvis",
        "chatbot_reply" to "The other AI (outside text)",
        "chatbot_note" to "Note",
        "chatbot_summary" to "Summary (outside text)",
    )

    fun chatbotWho(provenance: String?): String =
        CHATBOT_WHO[provenance] ?: CHATBOT_WHO.getValue("chatbot_note")

    const val CONTINUE = "Continue this chat"
    const val CONTINUE_TITLE = "Carry on this conversation on Home."

    /** What every delete dialog says stays (the second chat audit, 2026-09-28) - the desktop's words. */
    const val DELETE_STAYS = "Facts Jarvis learned stay. Copies in older backups stay until they age out."

    /** The same, when the owner is also ticking facts to forget. */
    const val DELETE_STAYS_TICKED =
        "Facts you did not tick stay. Copies in older backups stay until they age out."

    /** The note under an opened record of outside words, when it is not an ordinary chat. */
    const val TAINT_SUPPORT =
        "This record holds the company's words, which are outside text: Jarvis never learns from " +
            "them or acts on them."
    const val TAINT_CHATBOT =
        "This record holds another AI's replies, which are outside text: Jarvis never learns from " +
            "them or acts on them."
    /**
     * Said on an opened chat that is the one Home is in (the second chat
     * audit, phone C5): Delete and Continue act on the chat on screen there.
     */
    const val HOME_CHAT_LINE =
        "This is the chat you are in on Home. Deleting it starts a new conversation there."

    /** The "History is on/off" line's button at the top: opens the settings at the bottom. */
    const val STATUS_CHANGE = "Change"
    const val STATUS_CHANGE_TITLE = "Change chat history settings."
    const val SETTINGS_SHOW_TITLE = "Show chat history settings"
    const val SETTINGS_HIDE_TITLE = "Hide chat history settings"

    /** Which note goes above an opened record that read outside text, by its kind. */
    fun taintNote(kind: String): String = when (kind) {
        "support" -> TAINT_SUPPORT
        "chatbot", "compare" -> TAINT_CHATBOT
        else -> TAINT_LINE
    }

    /**
     * Which turns carry "read outside text": the ANSWER that read it, not the
     * owner's own question beside "You" (the second chat audit, the desktop's
     * C1 - the same rule): each user turn that read outside text marks the
     * answer after it, or itself when there is none.
     */
    fun outsideMarks(turns: List<Turn>): Set<Int> {
        val out = mutableSetOf<Int>()
        turns.forEachIndexed { i, t ->
            if (t.role == "user" && t.readOutside) {
                out += if (turns.getOrNull(i + 1)?.role == "assistant") i + 1 else i
            }
        }
        return out
    }

    const val OPEN_IN_HISTORY = "Open in History"
    const val OPEN_IN_HISTORY_TITLE = "Read it, or delete it, in History."

    /** What an opened chat says about the facts it taught (section 79): read only. */
    fun chatFactsTaught(n: Int): String = when {
        n <= 0 -> "Jarvis is not using any fact it learned from this chat."
        n == 1 -> "Jarvis learned 1 fact from this chat, and still uses it:"
        else -> "Jarvis learned $n facts from this chat, and still uses them:"
    }

    fun chatFactsTaughtHidden(n: Int): String =
        "Jarvis learned $n ${if (n == 1) "fact" else "facts"} from this chat. " +
            "Your memory lists are hidden, so they are not shown here."

    /** Why a kind cannot be continued - jarvis_chat_log.CONTINUE_WHY, for an older PC. */
    val CONTINUE_WHY = mapOf(
        "support" to "A customer-support record can't be continued: it is the company's words and " +
            "what was sent in your name, kept as your record.",
        "chatbot" to "A chat with another AI can't be continued here: its replies are outside text, " +
            "not a conversation with Jarvis.",
        "compare" to "A comparison can't be continued here: its replies are outside text, not a " +
            "conversation with Jarvis.",
    )

    const val COPY = "Copy"
    const val COPY_TITLE = "Copy this answer."
    const val COPIED = "Copied."
    const val FORGET_RANGE_LINK = "Forget a time frame…"
    const val FORGET_RANGE_LINK_TITLE = "Forget what Jarvis learned, and delete chats, from some days."
    const val DELETE_SUPPORT =
        "This is the record of a customer-support chat - what the company said and what was sent in " +
            "your name. Delete it anyway?"
    const val KEEP_SUPPORT_NOTE =
        "Customer-support chat records are not deleted by this - delete one yourself in History if " +
            "you want it gone."
    const val NO_TITLE = "(no title)"
    const val HISTORY_SETTINGS = "History settings"
    const val HISTORY_SETTINGS_TITLE = "Keep chat history on this PC, and how long."

    /** "1 message", "12 messages" - never "turns". */
    fun messagesWords(n: Int): String = if (n == 1) "1 message" else "${n.coerceAtLeast(0)} messages"

    /** A Live session's line: "Live · 12 min · Today 14:05". */
    fun liveLine(started: Long?, updated: Long?, zone: ZoneId, today: LocalDate): String {
        val secs = if (started != null && updated != null) (updated - started).coerceAtLeast(0) else 0
        val length = if (secs < 60) "under 1 min" else "${Math.round(secs / 60.0)} min"
        return "Live · $length · ${whenLine(started ?: updated, zone, today)}"
    }

    private val HEADING = Regex("(?m)^\\s{0,3}#{1,6}\\s+")
    private val BULLET = Regex("(?m)^(\\s*)[-*+]\\s+")
    private val BOLD = Regex("\\*\\*(.+?)\\*\\*", RegexOption.DOT_MATCHES_ALL)
    private val BOLD_U = Regex("__(.+?)__", RegexOption.DOT_MATCHES_ALL)
    private val ITALIC = Regex("(?<![\\w*])\\*(?!\\s)(.+?)(?<!\\s)\\*(?![\\w*])")
    private val CODE = Regex("`([^`\\n]+)`")
    private val FENCE = Regex("(?m)^\\s*```[^\\n]*$\\n?")

    /**
     * An answer as plain text for History: headings, bold, italics, code
     * marks and list markers taken off (a bullet becomes "• "), so an old
     * answer does not show "**" and "#" (the chat audit, 2026-09-28). The
     * desktop draws the same answer with its markdown renderer instead.
     */
    fun plainAnswer(text: String): String {
        var out = text
        out = HEADING.replace(out, "")
        out = BULLET.replace(out) { m -> m.groupValues[1] + "• " }
        out = BOLD.replace(out) { it.groupValues[1] }
        out = BOLD_U.replace(out) { it.groupValues[1] }
        out = ITALIC.replace(out) { it.groupValues[1] }
        out = CODE.replace(out) { it.groupValues[1] }
        out = FENCE.replace(out, "")
        return out
    }

    // ------------------------------------- which chat a fact came from ---

    const val FACT_CHAT_PATH = "/api/memory/fact-chat"

    fun factChatPath(id: Long): String? = if (id > 0) "$FACT_CHAT_PATH?id=$id" else null

    /** The chat a fact came from: its id, title, last change and kind. */
    data class FactChat(val id: String, val title: String?, val updated: Long?, val kind: String = "chat")

    /**
     * `GET /api/memory/fact-chat`: [Pair.first] false from a PC that cannot
     * say; [Pair.second] the chat, or null when none is on record.
     */
    fun factChat(body: JsonObject): Pair<Boolean, FactChat?> {
        val c = body["conversation"] as? JsonObject ?: return true to null
        val id = c.str("id") ?: return true to null
        return true to FactChat(id, c.str("title"), c.whole("updated"), kindOf(c.str("kind")))
    }

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
    /**
     * Who wrote each line of a customer-support chat's record (role
     * "support"; "Chat with customer support for me"). The desktop's words
     * too (history-view.js SUPPORT_WHO).
     */
    val SUPPORT_WHO = mapOf(
        "support_company" to "The company (outside text)",
        "support_jarvis" to "Sent by Jarvis in your name",
        "support_owner" to "You",
        "support_note" to "Note",
    )

    fun supportWho(provenance: String?): String =
        SUPPORT_WHO[provenance] ?: SUPPORT_WHO.getValue("support_note")

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

    // ------------------------------------------- facts this chat taught ---
    //
    // Deleting a chat offers to forget the facts it taught (docs/JARVIS-API.md
    // section 79, the owner's choice of 2026-09-28). The desktop's
    // history-view.js says the same words (tests/history.mjs checks). NONE is
    // ticked to start with - deleting a chat never widens into forgetting by
    // itself - and each ticked fact is then forgotten through the ordinary
    // Forget, ONE fact per call (JarvisRuntime.forgetAutoFact). There is no
    // list form of Forget.

    const val FACTS_PATH = "/api/memory/conversation-facts"

    /** One fact the chat taught: its id and its words, as the PC keeps them. */
    data class TaughtFact(val id: Long, val text: String)

    /**
     * The PC's answer, read. [available] false: an older PC that cannot say
     * (404/501) - Delete then asks exactly as it always did. [hiddenCount]:
     * facts the PC held back while the memory lists are hidden.
     */
    data class Taught(val available: Boolean, val facts: List<TaughtFact>, val hiddenCount: Int = 0)

    private val CONVERSATION_ID = Regex("[A-Za-z0-9_-]{8,64}")

    /** `GET /api/memory/conversation-facts?conversation_id=`, or null for anything
     *  that is not a conversation id (JARVIS-API 18.1) - nothing is sent. */
    fun factsPath(conversationId: String): String? =
        if (CONVERSATION_ID.matches(conversationId)) "$FACTS_PATH?conversation_id=$conversationId" else null

    /** The facts in a 2xx answer - each a whole-number id above 0 with words. */
    fun taught(body: JsonObject): Taught {
        val facts = (body["facts"] as? JsonArray).orEmpty().mapNotNull { v ->
            val o = v as? JsonObject ?: return@mapNotNull null
            val id = o.whole("id") ?: return@mapNotNull null
            val words = o.str("text")?.trim().orEmpty()
            if (id <= 0 || words.isEmpty()) null else TaughtFact(id, words)
        }
        val hidden = if (body.flag("hidden") == true) (body.whole("hidden_count") ?: 0L).toInt() else 0
        return Taught(available = true, facts = facts, hiddenCount = hidden.coerceAtLeast(0))
    }

    /** Above the list, with how many facts the chat taught. */
    fun chatFactsIntro(n: Int): String = if (n == 1) {
        "Jarvis learned 1 fact from this chat. It is kept unless you tick it - a ticked fact is forgotten, like Forget in the Brain."
    } else {
        "Jarvis learned $n facts from this chat. They are kept unless you tick them - each ticked fact is forgotten, like Forget in the Brain."
    }

    /** While the memory lists are hidden: not shown, and kept. */
    fun chatFactsHiddenLine(n: Int): String =
        "Jarvis learned $n ${if (n == 1) "fact" else "facts"} from this chat. " +
            "Your memory lists are hidden, so they are kept. To forget any, show the memory lists first."

    /** The Delete button's words, with how many ticked facts go with it. */
    fun deleteChatButton(n: Int): String =
        if (n <= 0) "Delete the chat" else "Delete the chat and forget $n ${if (n == 1) "fact" else "facts"}"

    /** The "are you sure?" line above Yes, with how many ticked facts go. */
    fun deleteAndForgetConfirm(n: Int): String = if (n <= 0) {
        "Delete this conversation from your PC? This cannot be undone. $DELETE_STAYS"
    } else {
        "Delete this conversation and forget $n ${if (n == 1) "fact" else "facts"}? The chat cannot be " +
            "brought back. A forgotten fact is not used again; it stays in Jarvis's history until you erase its words. " +
            DELETE_STAYS_TICKED
    }

    /** What happened, in one sentence: [chatSaid] is the delete's own sentence. */
    fun deleteDoneWords(chatSaid: String, forgot: Int, failed: Int): String {
        val done = if (forgot > 0) " Forgot $forgot ${if (forgot == 1) "fact" else "facts"}." else ""
        val bad = if (failed > 0) {
            " $failed ${if (failed == 1) "fact" else "facts"} could not be forgotten - try Forget on " +
                "${if (failed == 1) "it" else "them"} in the Brain."
        } else ""
        return chatSaid + done + bad
    }

    /** Why the phone could not do something with History - in the PC's words when there are some. */
    fun failure(e: ApiError): String? = when (e) {
        ApiError.NotFound -> "That is not on your PC any more, or this PC's Jarvis has no chat history yet."
        ApiError.NotAvailable -> "Chat history is not running on your PC right now."
        else -> null
    }
}
