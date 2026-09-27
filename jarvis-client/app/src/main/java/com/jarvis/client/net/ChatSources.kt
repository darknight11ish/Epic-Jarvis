package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * "Where this came from", and the quote check - feasibility I42/I132
 * (docs/CUTTING-EDGE-2026-09-26-round3-knowledge.md detail 1;
 * docs/JARVIS-API.md section 55).
 *
 * Only saved facts were ever listed under an answer ("Used in this answer",
 * [MemoryUsed]). A note, a wiki page, a web result or a file the model read
 * was not listed anywhere at all ("No tool receipt", docs/JARVIS-API.md
 * section 4). When the owner opens "Where this came from" under an answer,
 * its own reading-tool receipts are read from the PC by the SAME `turn_id`
 * [Feedback] and [MemoryUsed] already use: `GET /api/chat/sources?turn_id=`.
 * A read - this fetches nothing new, it only reads back what a tool already
 * fetched during that turn.
 *
 * There is no cheap COUNT for this the way [MemoryUsed.idsFromRouteHeader]
 * gives "Used in this answer" one: a tool's result is only known once the
 * tool loop finishes, long after `X-Jarvis-Route` (which carries `turn_id`)
 * was already sent. So the caller fetches this once, quietly, right when an
 * answer finishes, and shows anything only if there is something to show.
 *
 * "Hide memory lists and chat history" (Security) hides this the same way
 * it hides [MemoryUsed]'s lists - the PC itself takes every reference out
 * while that setting is on (`brain/sources.rs` on the desktop, the same
 * gate `/api/chat/sources` answers behind on the PC either way) - so the
 * phone need not, and does not, hide anything of its own here.
 *
 * The desktop says the same words (jarvis-desktop/src/memory-used.js). Pure
 * Kotlin, no Android types, so a JVM unit test runs it without a device.
 */
object ChatSources {
    const val PATH = "/api/chat/sources"

    /** The list's title under an answer - both apps. */
    const val TITLE = "Where this came from"

    /** A PC without the read route (a 404 or a 501). The desktop says the same. */
    const val MISSING =
        "Your PC's Jarvis cannot show where this answer came from yet - run apply-patches.ps1 on " +
            "the PC to update it."

    /** Beside a quoted phrase the PC could not find in what it read this turn. */
    const val QUOTE_WARNING_LABEL = "not found in what Jarvis read"

    /** The plain-English label for each kind `jarvis_sources.py` gives out. */
    private val KIND_LABEL = mapOf(
        "note" to "Note",
        "wiki" to "Wiki page",
        "web" to "Web",
        "file" to "File",
    )

    /** One thing a reading tool actually returned this turn, by reference only. */
    data class Source(
        val kind: String,
        val ref: String? = null,
        val url: String? = null,
        val path: String? = null,
        val title: String? = null,
    )

    data class View(val sources: List<Source>, val quotes: List<String>)

    /** What one read came to. */
    sealed interface Read {
        data class Shown(val view: View) : Read
        /** A PC without the route. */
        data object Missing : Read
        data class Failed(val why: String) : Read
    }

    /** The read for this answer, or null when there is no real id to ask by. */
    fun path(turnId: String?): String? {
        if (!Feedback.isTurnId(turnId)) return null
        return "$PATH?turn_id=$turnId"
    }

    /**
     * `GET /api/chat/sources`, read - or null when it is not that answer (no
     * `sources` array). A source of an unknown kind, or with none of
     * `ref`/`url`/`path`, is dropped, never guessed at.
     */
    fun parse(body: JsonObject): View? {
        val raw = body["sources"] as? JsonArray ?: return null
        val sources = raw.mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val kind = o.text("kind")?.takeIf { it in KIND_LABEL } ?: return@mapNotNull null
            val s = Source(kind, o.text("ref"), o.text("url"), o.text("path"), o.text("title"))
            s.takeIf { it.ref != null || it.url != null || it.path != null }
        }
        val quotes = (body["unverified_quotes"] as? JsonArray).orEmpty().mapNotNull {
            (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.contentOrNull?.takeIf { q -> q.isNotBlank() }
        }
        return View(sources, quotes)
    }

    /** A read that failed because this PC has no such route: a 404 or a 501. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || (error is ApiError.Server && error.code == 501)

    /**
     * One source's plain line: the kind, then whatever is safe to show. A
     * web source shows its HOST only (never the full link, never a title a
     * website chose); a note, wiki page or file shows its title when there
     * is one, else its reference.
     */
    fun line(s: Source): String {
        val label = KIND_LABEL[s.kind] ?: "Source"
        if (s.kind == "web") return "$label: ${hostOf(s.url)}"
        val shown = s.title ?: s.ref ?: s.path
        return if (shown != null) "$label: $shown" else label
    }

    /** A web source's host only. Jarvis never fetches the page to preview
     *  it, and neither does this app: the full link is handed to the real
     *  browser only once the owner taps it ([isOpenable]). */
    fun hostOf(url: String?): String {
        val u = url.orEmpty()
        return runCatching { java.net.URI(u).host ?: u }.getOrDefault(u).ifBlank { u }
    }

    /** True only for a web source with a real http(s) link - the one kind
     *  that may ever become a tap-to-open row. */
    fun isOpenable(s: Source): Boolean =
        s.kind == "web" && s.url != null && Regex("^https?://", RegexOption.IGNORE_CASE).containsMatchIn(s.url)

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
}
