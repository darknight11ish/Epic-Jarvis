package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * "What Jarvis can reach" (the Muse audit, 2026-09-25; docs/JARVIS-API.md
 * section 24; backend `jarvis_reach.py`, `reach.patch`).
 *
 * Every way Jarvis can reach something outside itself, whether each is on,
 * where it goes (a host name only), whether it asks first, one plain line,
 * and the tools the AI model is offered. The PC writes every word of it
 * from its own settings - the AI model never does - and Mind shows the
 * PC's words as they are. The constants below are only the parts of the
 * screen, and the same as the PC's and the desktop's `reach.js`
 * (backend/test_reach.py checks all three).
 *
 * A read: nothing here changes a setting, so it is not held on a stale link.
 * No password, key, private link or ntfy topic is in the answer.
 *
 * Pure Kotlin, no Android types, so `ReachTest` runs it on a plain JVM
 * against `contract/reach-cases.json` - the PC's real answers.
 */
object Reach {
    const val PATH = "/api/reach"

    const val TITLE = "What Jarvis can reach"
    const val DETAIL =
        "Every way Jarvis can reach something outside itself, and whether each one is " +
            "on right now. The PC writes this list from its own settings - the AI model does " +
            "not write it, so it cannot be talked into saying something else. Passwords, keys " +
            "and private links are never shown."
    const val MISSING =
        "Your PC's Jarvis cannot list what it can reach yet - run apply-patches.ps1 on " +
            "the PC."
    const val TOOLS_TITLE = "Tools the AI model is offered"
    const val TOOLS_NONE = "None: the AI model is offered no tools, so it can only write answers."
    const val EVERYTHING_ELSE = "Anything not on this list stays on this PC."
    const val WHERE_LABEL = "Goes to"
    const val ASKS_LABEL = "Asks you first"

    private val STATES = setOf("on", "off", "not_set_up", "blocked")

    data class Row(
        val id: String,
        val name: String,
        val state: String,
        val on: Boolean,
        val stateWords: String,
        val where: String,
        val asks: String,
        val line: String,
    )

    data class Tool(val id: String, val name: String)

    data class View(
        val title: String,
        val detail: String,
        val rows: List<Row>,
        val tools: List<Tool>,
        val toolsTitle: String,
        val toolsNone: String,
        val everythingElse: String,
        val whereLabel: String,
        val asksLabel: String,
        val on: Int,
    )

    /** `GET /api/reach`, read - or null when it is not one (an older PC). */
    fun parse(body: JsonObject): View? {
        if (body.flag("available") == false) return null
        val rows = (body["rows"] as? JsonArray)?.mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val id = o.text("id") ?: return@mapNotNull null
            val name = o.text("name") ?: return@mapNotNull null
            val state = o.text("state")?.takeIf { it in STATES } ?: "off"
            Row(
                id = id,
                name = name,
                state = state,
                on = o.flag("on") == true && state == "on",
                stateWords = o.text("state_words") ?: state,
                where = o.text("where") ?: "",
                asks = o.text("asks") ?: "",
                line = o.text("line") ?: "",
            )
        } ?: return null
        if (rows.isEmpty()) return null
        val tools = (body["tools"] as? JsonArray)?.mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val id = o.text("id") ?: return@mapNotNull null
            Tool(id, o.text("name") ?: id)
        } ?: emptyList()
        return View(
            title = body.text("title") ?: TITLE,
            detail = body.text("detail") ?: DETAIL,
            rows = rows,
            tools = tools,
            toolsTitle = body.text("tools_title") ?: TOOLS_TITLE,
            toolsNone = body.text("tools_none") ?: TOOLS_NONE,
            everythingElse = body.text("everything_else") ?: EVERYTHING_ELSE,
            whereLabel = body.text("where_label") ?: WHERE_LABEL,
            asksLabel = body.text("asks_label") ?: ASKS_LABEL,
            on = rows.count { it.on },
        )
    }

    /** A read that failed because this PC cannot list what it can reach. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    /** The heading of a row: its name and its state, as the desktop shows it. */
    fun heading(r: Row): String = "${r.name} - ${r.stateWords}"

    /** The lines under a row's name: where it goes and whether it asks (only
     *  when it is on), then its plain line - the desktop's `rowLines`. */
    fun lines(r: Row, v: View): List<String> = buildList {
        if (r.on && r.where.isNotEmpty()) add("${v.whereLabel}: ${r.where}")
        if (r.on && r.asks.isNotEmpty() && r.asks != "-") add("${v.asksLabel}: ${r.asks}")
        if (r.line.isNotEmpty()) add(r.line)
    }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
