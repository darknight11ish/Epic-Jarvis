package com.jarvis.client.net

import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * The DeepSeek-shaped History list the owner asked for (2026-10-27): pinned
 * chats first, then one collapsible section per chat tag (the owner's
 * "projects"), then the chats in no project; rows carry the conversation's
 * kind, its title and its age, and long sections say "Show N more".
 *
 * Pure Kotlin, no Android types, so `HistoryViewTest` runs it on a plain JVM.
 * Nothing here reads or writes the PC, and nothing here keeps a word of a
 * chat: [ChatLog] and [ChatTags] hold the wire shapes, this file only arranges
 * rows already read.
 *
 * TWO RULES DECIDED HERE, both tested:
 * - A pinned chat appears ONCE, in Pinned, never again in its tag's section.
 *   A tag's count therefore has the loaded pinned rows taken off it, so
 *   "Work (9)" counts the 9 Work chats under Work.
 * - "Show N more" only ever opens rows the phone ALREADY has. A section's
 *   header may count more than are loaded (that is the PC's own number);
 *   "Load older" is still the way to bring more in.
 */
object HistoryView {

    // ------------------------------------------------------------ words ---

    /** The Pinned section's title, and its key in the folded-sections store. */
    const val PINNED = "Pinned"

    /** The folded-sections key for Pinned (a tag id is positive, Untagged is -1). */
    const val PINNED_KEY = -2

    /** The one section shown when the PC has no tags at all. */
    const val CHATS = "Chats"

    /** How many rows a section shows before "Show N more". */
    const val SECTION_LIMIT = 5

    /** A row's markers and the overflow menu's words. */
    const val CURRENT = "You're here"
    const val PINNED_MARK = "Pinned"
    const val MENU = "Chat actions"
    const val OPEN = "Open"
    const val PIN = "Pin to top"
    const val UNPIN = "Unpin"
    const val DELETE = "Delete"

    /** What the PC's answer means, in one sentence. */
    const val PIN_SAVED = "Pinned to the top."
    const val UNPIN_SAVED = "Pin taken off."

    /** The sort control's three orders, in the order its tap cycles through them. */
    enum class Sort(val id: String, val label: String, val short: String) {
        NEWEST("newest", "Newest first", "Newest"),
        OLDEST("oldest", "Oldest first", "Oldest"),
        TITLE("title", "Title A-Z", "A-Z"),
    }

    /** A stored sort id, or Newest first for anything this build does not know. */
    fun sortOf(id: String?): Sort = Sort.values().firstOrNull { it.id == id } ?: Sort.NEWEST

    /** The next order a tap on the sort control picks. */
    fun nextSort(sort: Sort): Sort = Sort.values()[(sort.ordinal + 1) % Sort.values().size]

    /** "Sort: Newest first. Tap to change." - the control's name for TalkBack. */
    fun sortTitle(sort: Sort): String = "Sort: ${sort.label}. Tap to change."

    fun pinSaid(pinned: Boolean): String = if (pinned) PIN_SAVED else UNPIN_SAVED

    /** "Show 7 more" - only ever about rows already loaded. */
    fun showMore(n: Int): String = "Show $n more"

    fun showMoreTitle(section: String, n: Int): String = "Show $n more in $section"

    /** "Pinned (3)" and its spoken form: "Pinned, 3 chats, expanded" ("1 chat" for one). */
    fun pinnedHeader(count: Int): String = "$PINNED ($count)"

    fun pinnedHeaderSpoken(count: Int, expanded: Boolean): String =
        "$PINNED, $count ${if (count == 1) "chat" else "chats"}, ${if (expanded) "expanded" else "collapsed"}"

    /** The overflow trigger's name: "Chat actions for Dentist on Tuesday". */
    fun actionsFor(title: String): String = "$MENU for $title"

    /** A row's age in the DeepSeek list's short form: "now", "25min", "7d". */
    fun age(at: Long?, nowSeconds: Long): String {
        if (at == null) return ""
        val s = (nowSeconds - at).coerceAtLeast(0L)
        return when {
            s < 60L -> "now"
            s < 3_600L -> "${s / 60L}min"
            s < 86_400L -> "${s / 3_600L}h"
            s < 7L * 86_400L -> "${s / 86_400L}d"
            s < 30L * 86_400L -> "${s / (7L * 86_400L)}w"
            s < 365L * 86_400L -> "${s / (30L * 86_400L)}mo"
            else -> "${s / (365L * 86_400L)}y"
        }
    }

    // ------------------------------------------------------- one answer ---

    // "Sat 31 Oct, 21:10" - the desktop HUD's own answer-time shape
    // (`hud_bootstrap.js`'s `answerWhenWords`: weekday, day, month, hour,
    // minute, 24-hour clock), in English so both apps read the same.
    private val ANSWER_TIME = DateTimeFormatter.ofPattern("EEE dd MMM, HH:mm", Locale.UK)

    /**
     * The answer's own date and time, for the ONE read-only line at the top of
     * the per-answer menu (the desktop HUD shows the same line in the same
     * place; the phone had none until the owner's field test of 2026-11-01).
     *
     * Empty - not "unknown" - when the moment is not known ([atMs] null or 0),
     * so the menu draws nothing at all rather than a line about not knowing.
     *
     * [atMs] is milliseconds since the epoch, the unit
     * [ChatSession.answerAt] keeps. [zone] is a parameter so a test can hold
     * one place still, exactly like [age] takes `nowSeconds`.
     */
    fun answerTime(atMs: Long?, zone: ZoneId = ZoneId.systemDefault()): String {
        if (atMs == null || atMs == 0L) return ""
        return ANSWER_TIME.format(Instant.ofEpochMilli(atMs).atZone(zone))
    }

    // ---------------------------------------------------------- sorting ---

    /** [rows] in [sort] order. A row with no time is last in both time orders. */
    fun sortRows(rows: List<ChatLog.Summary>, sort: Sort): List<ChatLog.Summary> = when (sort) {
        Sort.NEWEST -> rows.sortedWith(
            compareByDescending<ChatLog.Summary> { it.updated ?: it.started ?: Long.MIN_VALUE }
                .thenByDescending { it.started ?: Long.MIN_VALUE },
        )
        Sort.OLDEST -> rows.sortedWith(
            compareBy<ChatLog.Summary> { it.updated ?: it.started ?: Long.MAX_VALUE }
                .thenBy { it.started ?: Long.MAX_VALUE },
        )
        Sort.TITLE -> rows.sortedWith(
            compareBy<ChatLog.Summary, String>(String.CASE_INSENSITIVE_ORDER) { it.title }
                .thenByDescending { it.updated ?: it.started ?: Long.MIN_VALUE },
        )
    }

    /**
     * [rows]' pinned ones in the one order a pin means: `pinned_at DESC,
     * updated_at DESC` (docs/JARVIS-API.md section 18.3) - the newest pin
     * first, two pins in the same moment newest chat first. The sort control
     * never touches this order: a pin is a place, not a preference. A row
     * with no pin moment (an older PC) sorts as the oldest pin, so it cannot
     * claim to have been pinned after one that says when it was.
     */
    fun pinnedRows(rows: List<ChatLog.Summary>): List<ChatLog.Summary> = rows
        .filter { it.pinned }
        .sortedWith(
            compareByDescending<ChatLog.Summary> { it.pinnedAt ?: 0L }
                .thenByDescending { it.updated ?: it.started ?: 0L }
                .thenBy { it.title },
        )

    // --------------------------------------------------------- sections ---

    /**
     * One section of the list. [tag] is the tag it stands for, or null for
     * Pinned and for the chats in no project. [count] is what the header says:
     * the PC's own number when nothing narrows the list, never less than the
     * rows loaded; the rows shown otherwise (the rule the tag chips narrow by).
     */
    data class Section(
        /** Stable for LazyColumn keys and the "Show N more" memory: "pinned", "t3", "untagged". */
        val id: String,
        val title: String,
        val tag: ChatTags.Tag?,
        val pinned: Boolean,
        val rows: List<ChatLog.Summary>,
        val count: Int,
    )

    /** The folded-sections key of a section: Pinned -2, a tag's id, Untagged -1. */
    fun prefsKey(section: Section): Int = when {
        section.pinned -> PINNED_KEY
        section.tag != null -> section.tag.id
        else -> ChatTags.UNTAGGED_KEY
    }

    private fun idOf(tag: ChatTags.Tag?): String = tag?.let { "t${it.id}" } ?: "untagged"

    /**
     * [rows] in the DeepSeek order: Pinned first, then one section per tag in
     * the owner's order, then Untagged last. A pinned row appears only in
     * Pinned, and Pinned is ordered by the pin itself ([pinnedRows]), never by
     * [sort]. [only] narrows to one tag id or [ChatTags.UNTAGGED_KEY], the
     * same filter the chips send. With no tags at all there is one "Chats"
     * section (plus Pinned, when anything is pinned).
     *
     * [exact] false is a narrowed list ("Show" or the title words): a header
     * then counts the rows shown, never the PC's whole number.
     */
    fun sections(
        rows: List<ChatLog.Summary>,
        tags: List<ChatTags.Tag>,
        untagged: Int,
        only: Int? = null,
        exact: Boolean = true,
        sort: Sort = Sort.NEWEST,
    ): List<Section> {
        val known = tags.mapTo(HashSet()) { it.id }
        fun loose(r: ChatLog.Summary): Boolean {
            val t = r.tagId
            return t == null || t !in known
        }
        fun belongs(r: ChatLog.Summary): Boolean = when (only) {
            null -> true
            ChatTags.UNTAGGED_KEY -> loose(r)
            else -> r.tagId == only
        }
        val mine = rows.filter(::belongs)
        val pinned = pinnedRows(mine)
        val rest = sortRows(mine.filterNot { it.pinned }, sort)
        val out = ArrayList<Section>()
        if (pinned.isNotEmpty()) {
            out += Section("pinned", PINNED, null, true, pinned, pinned.size)
        }
        if (tags.isEmpty()) {
            if (rest.isNotEmpty()) {
                val count = if (exact) maxOf(untagged - rows.count { it.pinned }, rest.size) else rest.size
                out += Section("untagged", CHATS, null, false, rest, count)
            }
            return out
        }
        for (t in tags) {
            if (only != null && only != t.id) continue
            val mine = rest.filter { it.tagId == t.id }
            // Pinned rows are not shown under their tag, so the PC's count has
            // the loaded pinned ones taken off. A pinned chat not loaded yet is
            // the one case a header can still be one high - said in the PR.
            val pinnedHere = rows.count { it.pinned && it.tagId == t.id }
            val count = if (exact) maxOf(t.count - pinnedHere, mine.size) else mine.size
            if (mine.isNotEmpty() || count > 0) out += Section(idOf(t), t.name, t, false, mine, count)
        }
        if (only == null || only == ChatTags.UNTAGGED_KEY) {
            val looseRows = rest.filter(::loose)
            val pinnedLoose = rows.count { it.pinned && loose(it) }
            val count = if (exact) maxOf(untagged - pinnedLoose, looseRows.size) else looseRows.size
            if (looseRows.isNotEmpty() || count > 0) {
                out += Section("untagged", ChatTags.UNTAGGED, null, false, looseRows, count)
            }
        }
        return out
    }

    /** Whether [section] is short enough to draw all of it: [revealed] or within [limit]. */
    fun isShort(section: Section, revealed: Boolean, limit: Int = SECTION_LIMIT): Boolean =
        revealed || section.rows.size <= limit

    /** The rows a section draws: all of them once opened, else the first [limit]. */
    fun shown(section: Section, revealed: Boolean, limit: Int = SECTION_LIMIT): List<ChatLog.Summary> =
        if (isShort(section, revealed, limit)) section.rows else section.rows.take(limit)

    /** How many loaded rows "Show N more" would add: 0 once opened or when all fit. */
    fun hidden(section: Section, revealed: Boolean, limit: Int = SECTION_LIMIT): Int =
        if (isShort(section, revealed, limit)) 0 else (section.rows.size - limit).coerceAtLeast(0)

    // ------------------------------------------------------------- menu ---

    /** One row of the overflow menu, in drawing order. */
    enum class Action { OPEN, PIN, MOVE, ARCHIVE, DELETE }

    /**
     * A row's overflow actions: Open, Pin/Unpin, Move to (only when the PC has
     * tags), Archive/Unarchive (the owner's request of 2026-10-29) and Delete.
     * Empty while a "file it under" banner is up: there a tap on the row files
     * it, and an extra menu would be two meanings for one row.
     *
     * The actions are the same list in both views; only the Archive row's word
     * changes (Unarchive on an archived chat - [actionLabel]). Delete stays
     * last: it is the only one that cannot be undone, and it keeps its confirm.
     */
    fun menu(tags: List<ChatTags.Tag>, filing: Boolean): List<Action> {
        if (filing) return emptyList()
        val out = mutableListOf(Action.OPEN, Action.PIN)
        if (tags.isNotEmpty()) out += Action.MOVE
        out += Action.ARCHIVE
        out += Action.DELETE
        return out
    }

    /** The word on a menu row: Pin reads "Unpin" already pinned, Archive reads "Unarchive" archived. */
    fun actionLabel(action: Action, pinned: Boolean, archived: Boolean = false): String = when (action) {
        Action.OPEN -> OPEN
        Action.PIN -> if (pinned) UNPIN else PIN
        Action.MOVE -> ChatTags.MOVE_TO
        Action.ARCHIVE -> if (archived) ChatLog.UNARCHIVE else ChatLog.ARCHIVE
        Action.DELETE -> DELETE
    }

    // -------------------------------------------- pin, in the loaded list ---

    /**
     * [rows] with one row's pin changed - only the PC's answer ever calls
     * this. [at] is the pin moment the PC echoed (its `pinned_at`, unix
     * seconds), or the phone's own clock when an older PC echoed none; it is
     * what puts the row where the pin means, and is dropped on an unpin.
     */
    fun withPin(
        rows: List<ChatLog.Summary>,
        id: String,
        pinned: Boolean,
        at: Long? = null,
    ): List<ChatLog.Summary> =
        rows.map {
            if (it.id == id) it.copy(pinned = pinned, pinnedAt = if (pinned) at else null) else it
        }

    /** The same for a word-the-PC search's results, where the row may not be loaded. */
    fun withPin(
        found: ChatLog.Search,
        id: String,
        pinned: Boolean,
        at: Long? = null,
    ): ChatLog.Search = found.copy(
        found = found.found.map { hit ->
            if (hit.row.id == id) {
                hit.copy(row = hit.row.copy(pinned = pinned, pinnedAt = if (pinned) at else null))
            } else {
                hit
            }
        },
    )

    // ------------------------------------------ archive, in the loaded list ---

    /**
     * [rows] with one row's archived state changed - only the PC's answer ever
     * calls this (the owner's request of 2026-10-29). The screen then keeps the
     * rows of the view it is showing ([ChatLog.inView]), so a chat that was
     * archived leaves the live list and one that was unarchived leaves the
     * archived view - and a refusal changes nothing at all.
     */
    fun withArchive(rows: List<ChatLog.Summary>, id: String, archived: Boolean): List<ChatLog.Summary> =
        rows.map { if (it.id == id) it.copy(archived = archived) else it }

    /** A row's age from the list's own timestamp; a Live session's end, else its start. */
    fun rowAge(row: ChatLog.Summary, nowSeconds: Long): String =
        age(row.updated ?: row.started, nowSeconds)

    /** The type icon's name for TalkBack; the row's own kind mark follows it in words. */
    fun kindSpoken(kind: String): String = when (kind) {
        "live" -> "Live session"
        "support" -> "Support chat"
        "chatbot" -> "Chat with another AI"
        "compare" -> "Comparison"
        else -> "Chat"
    }
}
