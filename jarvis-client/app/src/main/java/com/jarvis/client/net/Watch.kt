package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.put

/**
 * Watches - the GitHub topics Jarvis keeps an eye on, from the phone. The
 * desktop's Brain window, Watch tab (`jarvis-desktop/src/brain.js`,
 * `renderWatch` / `renderWatchReport`; `src-tauri/src/brain.rs`,
 * `brain_watch_add` / `_remove` / `_seen`), on the same five routes:
 *
 * - `GET /api/watch` - the topics.
 * - `GET /api/watch/report` - what is new. A peek: reading it marks nothing.
 * - `POST /api/watch/add` - watch a topic.
 * - `POST /api/watch/remove` - forget a topic and everything remembered about it.
 * - `POST /api/watch/seen` - mark what is new as read. A POST on purpose, so
 *   nothing that merely opens a link can clear the list.
 *
 * The module behind them (`jarvis_watch.py`) is on the owner's PC and not in
 * this repository, so every field name here is the desktop's reading of it,
 * not a documented shape (docs/ARCHITECTURE.md section 10: "the exact shape of
 * the routes they serve, is unverified from here"). Anything missing reads as
 * absent, never as a guess.
 */
object Watch {
    const val PATH = "/api/watch"
    const val REPORT_PATH = "/api/watch/report"
    const val ADD_PATH = "/api/watch/add"
    const val REMOVE_PATH = "/api/watch/remove"
    const val SEEN_PATH = "/api/watch/seen"

    data class Topic(
        val name: String,
        val query: String?,
        val error: String?,
        /** When it was last checked, in seconds since 1970, or null for never. */
        val checked: Double?,
        val notify: Boolean,
    )

    data class View(
        val topics: Int,
        val tracking: Int,
        val rateLimit: String?,
        val list: List<Topic>,
        /** The desktop's badge count: findings not yet marked read. */
        val waitingForYou: Int,
    )

    data class Finding(
        val title: String,
        val description: String,
        val stars: String?,
        val topic: String?,
        val archived: Boolean,
        /** The licence as stated, or null when none is. */
        val licence: String?,
        /** The scanner's note, if it made one. */
        val note: String?,
    )

    private fun JsonObject.text(key: String): String? = when (val v = this[key]) {
        is JsonPrimitive -> v.contentOrNull?.trim()?.takeIf { it.isNotEmpty() && it != "null" }
        else -> null
    }

    private fun JsonObject.number(key: String): Double? = (this[key] as? JsonPrimitive)?.let {
        if (it.isString) null else it.doubleOrNull
    }

    private fun JsonObject.truthy(key: String): Boolean = when (val v = this[key]) {
        is JsonPrimitive -> v.booleanOrNull ?: (!v.isString && (v.doubleOrNull ?: 0.0) != 0.0)
        else -> false
    }

    private fun count(obj: JsonObject, key: String): Int = obj.number(key)?.toInt() ?: 0

    /** `GET` [PATH]'s answer, read as the desktop reads it. */
    fun read(answer: JsonObject): View {
        val list = (answer["list"] as? JsonArray).orEmpty().mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val name = o.text("name") ?: return@mapNotNull null
            Topic(
                name = name,
                query = o.text("query"),
                error = o.text("error"),
                checked = o.number("checked")?.takeIf { it > 0 },
                notify = o.truthy("notify"),
            )
        }
        return View(
            topics = count(answer, "topics"),
            tracking = count(answer, "tracking"),
            rateLimit = answer.text("rate_limit"),
            list = list,
            waitingForYou = count(answer, "waiting_for_you"),
        )
    }

    /** `GET` [REPORT_PATH]'s answer: `findings`, or `items`, as the desktop accepts either. */
    fun findings(answer: JsonObject): List<Finding> {
        val arr = (answer["findings"] as? JsonArray) ?: (answer["items"] as? JsonArray) ?: return emptyList()
        return arr.mapNotNull { el: JsonElement ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val stated = (o.text("licence") ?: o.text("license"))
                ?.takeUnless { Regex("^(none|unknown|null)$", RegexOption.IGNORE_CASE).matches(it) }
            Finding(
                title = o.text("full_name") ?: o.text("name") ?: "(repository)",
                description = o.text("descr") ?: o.text("description") ?: "",
                stars = if (o.containsKey("stars")) o.text("stars") ?: "?" else null,
                topic = o.text("topic"),
                archived = o.truthy("archived"),
                licence = stated,
                note = o.text("note"),
            )
        }
    }

    /** The line above the topics - the desktop's, in words. */
    fun headLine(v: View): String = listOfNotNull(
        "${v.topics} ${if (v.topics == 1) "topic" else "topics"} · " +
            "${v.tracking} ${if (v.tracking == 1) "project" else "projects"} known",
        v.rateLimit,
    ).joinToString(" · ")

    /** "3m ago" - the desktop's `ago()`, from seconds since 1970. */
    fun ago(epochSeconds: Double, nowSeconds: Double): String {
        val s = maxOf(0L, Math.round(nowSeconds - epochSeconds))
        return when {
            s < 60 -> "${s}s ago"
            s < 3600 -> "${Math.round(s / 60.0)}m ago"
            s < 86400 -> "${Math.round(s / 3600.0)}h ago"
            else -> "${Math.round(s / 86400.0)}d ago"
        }
    }

    /** The small lines under one topic, in the desktop's order. */
    fun topicLines(t: Topic, nowSeconds: Double): List<String> = listOfNotNull(
        t.query?.takeIf { it != t.name }?.let { "Searching for: $it" },
        t.error,
        listOf(
            t.checked?.let { "checked ${ago(it, nowSeconds)}" } ?: "never checked",
            if (t.notify) "notify on" else "notify off",
        ).joinToString(" · "),
    )

    /** The small lines under one finding. No licence stated means no permission - said so. */
    fun findingLines(f: Finding): List<String> = listOfNotNull(
        f.description.takeIf { it.isNotEmpty() },
        listOfNotNull(
            f.stars?.let { "★ $it" },
            f.topic?.let { "topic: $it" },
            "archived".takeIf { f.archived },
            if (f.licence == null) "no licence stated - no permission to use it" else "licence: ${f.licence}",
        ).joinToString(" · "),
        f.note?.let { "scanner: $it" },
    )

    /**
     * The add body: what the desktop sends. The name alone is the query
     * when no query is typed - the server does that with a missing one.
     * Null when there is no name, or the minimum stars is not a whole number.
     */
    fun addBody(name: String, query: String, minStars: String, language: String, notify: Boolean): String? {
        val n = name.trim()
        if (n.isEmpty()) return null
        val stars = minStars.trim()
        val starsNumber = if (stars.isEmpty()) null else stars.toIntOrNull()?.takeIf { it >= 0 } ?: return null
        return buildJsonObject {
            put("name", n)
            query.trim().takeIf { it.isNotEmpty() }?.let { put("query", it) }
            starsNumber?.let { put("min_stars", it) }
            language.trim().takeIf { it.isNotEmpty() }?.let { put("language", it) }
            put("notify", notify)
        }.toString()
    }

    fun removeBody(name: String): String = buildJsonObject { put("name", name) }.toString()

    /** Everything new, as the desktop's "Mark these read" sends it. */
    const val SEEN_BODY = "{}"

    /** The warning before Forget - the desktop's own, in plainer words. */
    fun forgetWarning(name: String): String =
        "Forget \"$name\"? Everything Jarvis remembers about this topic goes with it - which " +
            "projects it has already seen, and what it already told you. Adding it back " +
            "starts from nothing."

    /** What to say after asking the PC to watch [name]. */
    fun addSaid(name: String, o: DesktopWrite.Outcome): String = when (o) {
        is DesktopWrite.Outcome.Done -> o.said ?: "Watching $name."
        is DesktopWrite.Outcome.Waiting ->
            "Waiting for your approval to watch $name. ${Approvals.WHERE} Nothing is watched until you do."
        is DesktopWrite.Outcome.Refused -> "Not added. ${o.why}"
    }

    /** What to say after asking the PC to forget [name]. */
    fun removeSaid(name: String, o: DesktopWrite.Outcome): String = when (o) {
        is DesktopWrite.Outcome.Done -> o.said ?: "Forgot $name."
        is DesktopWrite.Outcome.Waiting ->
            "Waiting for your approval to forget $name. ${Approvals.WHERE}"
        is DesktopWrite.Outcome.Refused -> "Not forgotten. ${o.why}"
    }

    /** What to say after "Mark these read". */
    fun seenSaid(o: DesktopWrite.Outcome): String = when (o) {
        is DesktopWrite.Outcome.Done -> o.said ?: "Marked read."
        is DesktopWrite.Outcome.Waiting -> "Waiting for your approval. ${Approvals.WHERE}"
        is DesktopWrite.Outcome.Refused -> "Not marked read. ${o.why}"
    }

    /** A request that failed before the PC could answer it, in words. Null means use the generic one. */
    fun failure(e: ApiError): String? = when (e) {
        ApiError.NotFound, ApiError.NotAvailable ->
            "Your PC's Jarvis has no watch list (jarvis_watch.py is not there)."
        else -> null
    }
}
