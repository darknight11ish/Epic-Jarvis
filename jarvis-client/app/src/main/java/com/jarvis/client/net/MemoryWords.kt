package com.jarvis.client.net

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull

/**
 * The memory words both apps use - the memory review of 2026-09-27, I8-I11.
 *
 * The desktop's `jarvis-desktop/src/memory-words.js` says exactly the same.
 * Both are held to `src/test/resources/contract/memory-words-cases.json`,
 * which tools/gen_memory_words_cases.py writes from the real backend
 * (jarvis_memory's status, jarvis_intake's older-news sentence);
 * MemoryWordsContractTest and the desktop's tests/memory-words.mjs read it.
 * Change a word here and that test fails until the generator (and so the
 * desktop) says it too.
 *
 * - [statusRows]: `GET /api/memory/status` -> the rows of the memory counts,
 *   including "Answer ordering (re-ranker)" and "Said again" (I8).
 * - [cardLines]: a review card's `auto_reason` -> its "Not saved
 *   automatically" line, and the "older news" warning on a line of its own
 *   with plain dates (I9).
 * - [plainDate] / [trueFromLine]: "2026-01-01" -> "1 January 2026" / "true
 *   from 1 January 2026" (I10).
 * - The one wording for a fact no longer in use (I11): [NO_LONGER_USED] in
 *   today's list (the desktop's; the phone has no such list), [TRUE_THEN] /
 *   [NO_LONGER_TRUE] when looking at a past date (both apps).
 *
 * Pure: no clock, no locale.
 */
object MemoryWords {
    val MONTHS: List<String> = listOf(
        "January", "February", "March", "April", "May", "June", "July",
        "August", "September", "October", "November", "December",
    )

    const val FACTS_IN_USE = "Facts in use"
    const val NO_LONGER_USED_COUNT = "No longer used"
    const val EMBEDDING = "Embedding"
    const val EMBEDDING_WORDS_ONLY = "(matches words only until the real embedding model has downloaded)"
    const val SEARCH_BY_MEANING = "Search by meaning"
    const val SEARCH_BY_MEANING_OFF = "off - facts are found by keyword"
    const val WAITING_TO_BE_INDEXED = "Waiting to be indexed"
    const val OVERNIGHT = "Overnight tidying"
    const val OVERNIGHT_ON = "switched on, but not built yet - nothing runs"
    const val OVERNIGHT_OFF = "off (not built yet)"
    const val RERANKER = "Answer ordering (re-ranker)"
    const val RERANKER_LOADING = "still loading - answers keep the old order until it is ready"
    const val RERANKER_NOT_STARTED = "not loaded yet - it starts loading with the first question"
    const val RERANKER_OFF_BY_SETTING = "turned off on the PC (JARVIS_MEMORY_RERANK=0)"
    const val SAID_AGAIN = "Said again"
    const val SAID_AGAIN_NONE = "nothing yet"
    const val REPEATS = "Repeated cards dropped"
    const val REASON_PREFIX = "Not saved automatically: "
    const val OLDER_NEWS_START = "It sounds older than what Jarvis knows"
    const val NO_LONGER_USED = "no longer used"
    const val TRUE_THEN = "true then"
    const val NO_LONGER_TRUE = "no longer true"
    const val TRUE_FROM = "true from"

    /** Every word above under the fixture's key, for the contract test. */
    val WORDS: Map<String, String> = mapOf(
        "facts_in_use" to FACTS_IN_USE,
        "no_longer_used_count" to NO_LONGER_USED_COUNT,
        "embedding" to EMBEDDING,
        "embedding_words_only" to EMBEDDING_WORDS_ONLY,
        "search_by_meaning" to SEARCH_BY_MEANING,
        "search_by_meaning_off" to SEARCH_BY_MEANING_OFF,
        "waiting_to_be_indexed" to WAITING_TO_BE_INDEXED,
        "overnight" to OVERNIGHT,
        "overnight_on" to OVERNIGHT_ON,
        "overnight_off" to OVERNIGHT_OFF,
        "reranker" to RERANKER,
        "reranker_loading" to RERANKER_LOADING,
        "reranker_not_started" to RERANKER_NOT_STARTED,
        "reranker_off_by_setting" to RERANKER_OFF_BY_SETTING,
        "said_again" to SAID_AGAIN,
        "said_again_none" to SAID_AGAIN_NONE,
        "repeats" to REPEATS,
        "reason_prefix" to REASON_PREFIX,
        "older_news_start" to OLDER_NEWS_START,
        "no_longer_used" to NO_LONGER_USED,
        "true_then" to TRUE_THEN,
        "no_longer_true" to NO_LONGER_TRUE,
        "true_from" to TRUE_FROM,
    )

    // [0-9], not \d, and matchEntire: the same days the desktop and the
    // generator accept, and no other.
    private val ISO = Regex("""([0-9]{4})-([0-9]{2})-([0-9]{2})""")
    private val ISO_IN_TEXT = Regex("""\b([0-9]{4}-[0-9]{2}-[0-9]{2})\b""")

    private fun daysIn(y: Int, m: Int): Int = when (m) {
        2 -> if ((y % 4 == 0 && y % 100 != 0) || y % 400 == 0) 29 else 28
        4, 6, 9, 11 -> 30
        else -> 31
    }

    /** "2026-01-01" -> "1 January 2026"; null for anything that is not a real day written exactly that way. */
    fun plainDate(iso: String?): String? {
        val m = iso?.let { ISO.matchEntire(it) } ?: return null
        val y = m.groupValues[1].toInt()
        val mo = m.groupValues[2].toInt()
        val d = m.groupValues[3].toInt()
        if (y < 1 || mo !in 1..12 || d < 1 || d > daysIn(y, mo)) return null
        return "$d ${MONTHS[mo - 1]} $y"
    }

    /** A `GET /api/memory/auto` row's `true_from` -> "true from 1 January 2026", or null. */
    fun trueFromLine(iso: String?): String? = plainDate(iso)?.let { "$TRUE_FROM $it" }

    private fun prim(e: JsonElement?): JsonPrimitive? = (e as? JsonPrimitive)?.takeIf { !it.isString }

    /** A real JSON number (never a string, never true/false), finite. */
    private fun number(e: JsonElement?): Double? {
        val p = prim(e) ?: return null
        if (p.booleanOrNull != null) return null
        return p.doubleOrNull?.takeIf { it.isFinite() }
    }

    /** A number as both apps show it: whole numbers without ".0". */
    private fun numText(e: JsonElement?): String? {
        val d = number(e) ?: return null
        return if (d == Math.floor(d)) d.toLong().toString() else d.toString()
    }

    /** A whole number of 0 or more, or null. */
    private fun count(e: JsonElement?): Long? {
        val d = number(e) ?: return null
        return if (d == Math.floor(d) && d >= 0) d.toLong() else null
    }

    /** true/false only when the PC sent a JSON boolean. */
    private fun bool(e: JsonElement?): Boolean? = prim(e)?.booleanOrNull

    private fun string(e: JsonElement?): String? = (e as? JsonPrimitive)?.takeIf { it.isString }?.content

    private fun times(n: Long): String = when (n) {
        1L -> "once"
        2L -> "twice"
        else -> "$n times"
    }

    /** The re-ranker's row value, or null when there is nothing to say. */
    fun rerankerValue(r: JsonElement?): String? {
        val o = r as? JsonObject ?: return null
        return when (string(o["state"])) {
            "on" -> {
                val parts = mutableListOf<String>()
                count(o["used"])?.let { used ->
                    parts += "used for $used ${if (used == 1L) "answer" else "answers"}"
                }
                val slow = count(o["slow"])
                if (slow != null && slow > 0) {
                    parts += "too slow ${times(slow)}, so " +
                        (if (slow == 1L) "that answer" else "those answers") + " kept the old order"
                }
                if (parts.isEmpty()) "on" else "on - " + parts.joinToString("; ")
            }
            "loading" -> RERANKER_LOADING
            "not started" -> RERANKER_NOT_STARTED
            "off" -> {
                var why = string(o["why"])?.trim().orEmpty()
                if (why == "JARVIS_MEMORY_RERANK=0") why = RERANKER_OFF_BY_SETTING
                if (why.isEmpty()) "off" else "off - $why"
            }
            else -> null
        }
    }

    /** "Said again": how many times the owner told Jarvis something it knew. */
    fun saidAgainValue(v: JsonElement?): String? {
        val n = count(v) ?: return null
        return if (n == 0L) SAID_AGAIN_NONE else times(n)
    }

    /**
     * The rows of the memory counts, label to value, in order. The desktop
     * also shows the store's file path ("Store"), which is a path on the PC
     * and is not shown here.
     */
    fun statusRows(s: JsonObject): List<Pair<String, String>> {
        if (bool(s["available"]) == false) return emptyList()
        val out = mutableListOf<Pair<String, String>>()
        numText(s["current"])?.let { out += FACTS_IN_USE to it }
        numText(s["retired"])?.let { out += NO_LONGER_USED_COUNT to it }
        string(s["embedder"])?.takeIf { it.isNotBlank() }?.let { e ->
            out += EMBEDDING to if (bool(s["semantic"]) == false) "$e $EMBEDDING_WORDS_ONLY" else e
        }
        if (bool(s["vector_search"]) == false) out += SEARCH_BY_MEANING to SEARCH_BY_MEANING_OFF
        number(s["unembedded"])?.takeIf { it > 0 }?.let {
            numText(s["unembedded"])?.let { n -> out += WAITING_TO_BE_INDEXED to n }
        }
        rerankerValue(s["reranker"])?.let { out += RERANKER to it }
        saidAgainValue(s["said_again"])?.let { out += SAID_AGAIN to it }
        (s["sleep_time"] as? JsonObject)?.let { st ->
            out += OVERNIGHT to if (bool(st["enabled"]) == true) OVERNIGHT_ON else OVERNIGHT_OFF
        }
        return out
    }

    /** A review card's two lines: the reason, and the older-news warning. Either may be null. */
    data class CardLines(val reason: String?, val older: String?)

    /**
     * `auto_reason` off a pending row. The PC's words are shown as they are,
     * trimmed and without a trailing full stop. The PC adds its "it sounds
     * older than what Jarvis knows" warning to the same field (memory idea
     * 4); it goes on a line of its own here, with plain dates.
     */
    fun cardLines(row: JsonObject?): CardLines {
        val raw = string(row?.get("auto_reason")).orEmpty()
        val i = raw.indexOf(OLDER_NEWS_START)
        val before = if (i >= 0) raw.substring(0, i) else raw
        val after = if (i >= 0) raw.substring(i).trim() else ""
        val reason = before.trim().trimEnd('.').trim()
        val older = after.takeIf { it.isNotEmpty() }?.let { text ->
            val dated = ISO_IN_TEXT.replace(text) { m -> plainDate(m.groupValues[1]) ?: m.value }
            if (dated.endsWith(".")) dated else "$dated."
        }
        return CardLines(reason.takeIf { it.isNotEmpty() }?.let { REASON_PREFIX + it }, older)
    }
}
