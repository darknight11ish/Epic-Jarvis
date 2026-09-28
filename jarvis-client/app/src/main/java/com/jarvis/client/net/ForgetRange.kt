package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put

/**
 * "Forget a time frame" - the owner's decision of 2026-09-28, and
 * docs/JARVIS-API.md section 64 (`/api/memory/forget_range`).
 *
 * The owner picks some days; the PC lists what Jarvis learned and the chats
 * from then, each ticked; the owner unticks any to keep and taps "Forget
 * these"; the PC raises ONE approval card listing every item, decided by a
 * tap - never by voice. Approved: the facts are forgotten (as Forget does)
 * and the chats deleted, with 10 minutes to Undo (one tap, no card).
 *
 * What asks first is the PC's to decide, never this app's. The phone keeps
 * nothing of the list: it reads it from the PC each time.
 *
 * The desktop says the same words (jarvis-desktop/src/forget-range.js); both
 * are checked against `contract/forget-range-cases.json`, made by
 * tools/gen_forget_range_cases.py from the real backend.
 *
 * Pure Kotlin, no Android types, so `ForgetRangeTest` runs it on a plain JVM.
 */
object ForgetRange {
    const val PATH = "/api/memory/forget_range"
    const val PREVIEW_PATH = "/api/memory/forget_range/preview"
    const val UNDO_PATH = "/api/memory/forget_range/undo"

    /** The Brain item "forget what you learned last week" opens (`open_brain`). */
    const val PLACE = "forget-range"

    /** The screens' own words, both apps, word for word (the contract's `words`). */
    val WORDS: Map<String, String> = mapOf(
        "asked" to "You asked Jarvis to forget {said}. Check the list below.",
        "bad_date" to "Type the dates like 2026-09-01.",
        "between_us" to "Between us",
        "chats_head" to "Chats from then",
        "custom" to "Choose the dates",
        "date_hint" to "A date like 2026-09-01",
        "erase_note" to "Facts are forgotten, as Forget does: they stop being used and stay in the history. To wipe a fact's words for good, use Erase the words on that fact.",
        "facts_head" to "What Jarvis learned then",
        "forget" to "Forget these",
        "from" to "From",
        "kind_chats" to "Chats",
        "kind_facts" to "What Jarvis learned",
        "kinds" to "What to look for",
        "locked" to "Unlock Jarvis to see this list.",
        "missing" to "Your PC's Jarvis cannot forget a time frame yet - run apply-patches.ps1 on the PC.",
        "none_ticked" to "Tick at least one thing to forget.",
        "pinned" to "Always kept in mind",
        "show" to "Show the list",
        "spills" to "Also has messages from outside these days - the whole chat is deleted.",
        "stale" to "The connection to Jarvis is catching up, so nothing can be sent until it does.",
        "title" to "Forget a time frame",
        "to" to "To",
        "under" to "Choose some days. Jarvis lists what it learned and your chats from then - untick anything you want to keep, then tap Forget these. Nothing is removed until you approve the card, and for 10 minutes one tap on Undo puts it all back.",
        "undo" to "Undo",
        "undo_left" to "{minutes} min left to undo",
        "waiting" to "Waiting for your yes on the approval card. Nothing is removed until you approve it - saying yes out loud does not.",
    )

    /** One of [WORDS]. */
    fun w(key: String): String = WORDS.getValue(key)

    /** `{said}` and friends filled in. */
    fun fill(template: String, vararg values: Pair<String, Any>): String {
        var out = template
        for ((k, v) in values) out = out.replace("{$k}", v.toString())
        return out
    }

    val MISSING: String get() = w("missing")

    data class Preset(val id: String, val label: String)

    /** The PC's quick choices, in its order, for before it has said them. */
    val PRESETS: List<Preset> = listOf(
        Preset("today", "Today"),
        Preset("yesterday", "Yesterday"),
        Preset("this_week", "This week"),
        Preset("last_week", "Last week"),
        Preset("last_7_days", "The last 7 days"),
        Preset("this_month", "This month"),
        Preset("last_month", "Last month"),
    )

    // ------------------------------------------------------------ shapes ----

    data class Undo(val secondsLeft: Int, val minutesLeft: Int, val facts: Int, val chats: Int, val said: String)

    data class Asked(val id: String, val from: String, val to: String, val said: String, val kinds: List<String>)

    data class Last(val outcome: String, val message: String)

    data class Status(
        val available: Boolean,
        val why: String,
        val waiting: Boolean,
        val undo: Undo?,
        val last: Last?,
        val asked: Asked?,
        val maxItems: Int,
        val presets: List<Preset>,
    )

    data class Fact(val id: Long, val text: String, val label: String, val pinned: Boolean, val betweenUs: Boolean)

    data class Chat(val id: String, val title: String, val label: String, val spills: Boolean)

    data class Preview(
        val available: Boolean,
        val why: String,
        val from: String,
        val to: String,
        val frameSaid: String,
        val kinds: List<String>,
        val facts: List<Fact>,
        val chats: List<Chat>,
        val factsCount: Int,
        val chatsCount: Int,
        val tooMany: Boolean,
        val empty: Boolean,
        val said: String,
        val chatsWhy: String,
    )

    // ------------------------------------------------------------ reading ---

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.flag(key: String): Boolean =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == true

    private fun JsonObject.whole(key: String): Int =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString && it !is JsonNull }?.intOrNull ?: 0

    private fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject

    private fun JsonObject.list(key: String): List<JsonObject> =
        (this[key] as? JsonArray)?.mapNotNull { it as? JsonObject }.orEmpty()

    private fun JsonObject.words(key: String): List<String> =
        (this[key] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.contentOrNull }
            .orEmpty()

    private val WHEN = Regex("""\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?""")

    /** "2026-09-01" or "2026-09-28T09:30" - what the PC reads and writes. */
    fun isWhen(s: String?): Boolean = s != null && WHEN.matches(s)

    private fun unavailable(why: String?) = Status(false, why ?: MISSING, false, null, null, null, 200, PRESETS)

    /** `GET /api/memory/forget_range`. */
    fun parseStatus(o: JsonObject?): Status {
        if (o == null) return unavailable(null)
        if ((o["available"] as? JsonPrimitive)?.booleanOrNull == false) return unavailable(o.text("why"))
        val u = o.obj("undo")
        val a = o.obj("asked")
        val l = o.obj("last")
        val presets = o.list("presets").mapNotNull { p ->
            p.text("id")?.let { Preset(it, p.text("label").orEmpty()) }
        }
        return Status(
            available = true,
            why = "",
            waiting = o.flag("waiting"),
            undo = u?.let {
                Undo(it.whole("seconds_left"), it.whole("minutes_left"), it.whole("facts"), it.whole("chats"),
                    it.text("said").orEmpty())
            },
            last = l?.let { Last(it.text("outcome").orEmpty(), it.text("message").orEmpty()) },
            asked = a?.takeIf { isWhen(it.text("from")) && isWhen(it.text("to")) }?.let {
                Asked(it.text("id").orEmpty(), it.text("from")!!, it.text("to")!!, it.text("said").orEmpty(),
                    it.words("kinds").filter { k -> k == "facts" || k == "chats" })
            },
            maxItems = o.whole("max_items").takeIf { it > 0 } ?: 200,
            presets = presets.ifEmpty { PRESETS },
        )
    }

    /** `GET /api/memory/forget_range/preview`. */
    fun parsePreview(o: JsonObject?): Preview {
        if (o == null || (o["available"] as? JsonPrimitive)?.booleanOrNull == false) {
            return Preview(false, o?.text("why") ?: MISSING, "", "", "", emptyList(), emptyList(), emptyList(),
                0, 0, false, false, "", "")
        }
        val f = o.obj("frame")
        val counts = o.obj("counts")
        val facts = o.list("facts").mapNotNull { x ->
            val id = (x["id"] as? JsonPrimitive)?.takeIf { !it.isString }?.longOrNull ?: return@mapNotNull null
            Fact(id, x.text("text").orEmpty(), x.text("label").orEmpty(), x.flag("pinned"), x.flag("between_us"))
        }
        val chats = o.list("chats").mapNotNull { x ->
            val id = x.text("id") ?: return@mapNotNull null
            Chat(id, x.text("title").orEmpty(), x.text("label").orEmpty(), x.flag("spills"))
        }
        return Preview(
            available = true,
            why = "",
            from = f?.text("from").orEmpty(),
            to = f?.text("to").orEmpty(),
            frameSaid = f?.text("said").orEmpty(),
            kinds = o.words("kinds").ifEmpty { listOf("facts", "chats") },
            facts = facts,
            chats = chats,
            factsCount = counts?.whole("facts") ?: 0,
            chatsCount = counts?.whole("chats") ?: 0,
            tooMany = o.flag("too_many"),
            empty = o.flag("empty"),
            said = o.text("said").orEmpty(),
            chatsWhy = o.text("chats_why").orEmpty(),
        )
    }

    // ----------------------------------------------------------- asking ----

    private val PRESET_IDS = PRESETS.map { it.id }.toSet()

    /**
     * The preview's path for a quick choice (`preset`) or two typed dates;
     * null when a date is not written like 2026-09-01, or no kind is chosen.
     */
    fun previewPath(preset: String?, from: String?, to: String?, kinds: Set<String>): String? {
        val k = listOf("facts", "chats").filter { it in kinds }
        if (k.isEmpty()) return null
        val kq = k.joinToString(",")
        if (preset != null) {
            return if (preset in PRESET_IDS) "$PREVIEW_PATH?preset=$preset&kinds=$kq" else null
        }
        if (!isWhen(from) || !isWhen(to)) return null
        return "$PREVIEW_PATH?from=$from&to=$to&kinds=$kq"
    }

    /** Every item ticked: "fact:<id>" and "chat:<id>" - how a fresh list starts. */
    fun allTicked(p: Preview): Set<String> =
        p.facts.map { "fact:${it.id}" }.toSet() + p.chats.map { "chat:${it.id}" }.toSet()

    fun tickedCount(p: Preview, ticked: Set<String>): Int =
        p.facts.count { "fact:${it.id}" in ticked } + p.chats.count { "chat:${it.id}" in ticked }

    /** "Forget these": the ids still ticked, in the list's order, and the PC's own two dates. */
    fun forgetBody(p: Preview, ticked: Set<String>): String = buildJsonObject {
        put("from", p.from)
        put("to", p.to)
        put("facts", JsonArray(p.facts.filter { "fact:${it.id}" in ticked }.map { JsonPrimitive(it.id) }))
        put("chats", JsonArray(p.chats.filter { "chat:${it.id}" in ticked }.map { JsonPrimitive(it.id) }))
    }.toString()

    /** "Forget these (3)". */
    fun forgetLabel(n: Int): String = "${w("forget")} ($n)"

    /** The Undo line: what was done, and how long is left. */
    fun undoLine(u: Undo): String =
        "${u.said} ${fill(w("undo_left"), "minutes" to (if (u.minutesLeft > 0) u.minutesLeft else 1))}."

    /** "Forget these" waits for a live link (rule 4); Undo never does - it only puts back. */
    fun heldOnStale(action: String): Boolean = action == "forget"

    /**
     * "forget what you learned last week", said or typed: [PLACE] when the
     * answer's `X-Jarvis-Route` says `open_brain: "forget-range"`, else
     * null. Pure navigation - nothing is removed by opening the list.
     */
    fun openFromRoute(header: String?): String? {
        if (header.isNullOrBlank()) return null
        val o = runCatching { JarvisJson.parseToJsonElement(header.trim()) as? JsonObject }.getOrNull()
            ?: return null
        return o.text("open_brain")?.takeIf { it == PLACE }
    }

    // --------------------------------------------------------- answers ----

    data class Reply(val code: Int, val body: JsonObject?)

    /** How a change went: [waiting] a card is up; [done] something changed (Undo). */
    data class Outcome(val done: Boolean, val waiting: Boolean, val said: String, val listChanged: Boolean = false)

    /** A PC without the routes: a 404 that jarvis_forget_range did not send. */
    fun isMissing(reply: Reply): Boolean =
        (reply.code == 404 && (reply.body?.get("ok") as? JsonPrimitive)?.booleanOrNull != false) || reply.code == 501

    private fun sentence(s: String): String =
        s.replaceFirstChar { it.uppercase() }.let { if (it.isEmpty() || it.last() in ".!?") it else "$it." }

    /** Reads a "forget" or "undo" answer: the PC's own sentence either way. */
    fun said(reply: Reply, done: String): Outcome {
        val b = reply.body
        val error = b?.text("error")?.let { sentence(it) }
        return when {
            isMissing(reply) -> Outcome(false, false, MISSING)
            reply.code in 200..299 -> Outcome(
                done = true,
                waiting = reply.code == 202 || b?.flag("waiting") == true,
                said = b?.text("message") ?: done,
            )
            else -> Outcome(false, false, error ?: "Not done. Your PC said no (HTTP ${reply.code}).",
                listChanged = b?.flag("changed") == true)
        }
    }
}
