package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * "How Jarvis talks": warm and brief (the default), or plain (the owner's
 * decision of 2026-09-25; docs/JARVIS-API.md section 27; backend
 * `jarvis_manner.py`, `manner.patch`).
 *
 * Manner changes only how Jarvis words its answers - never what it does, asks
 * or remembers - so neither choice raises an approval card. It is still ONE
 * change sent to the PC, so it is held on a stale link like every other
 * (rule 4). The PC sends its own words with every `GET /api/manner` and Mind
 * shows those; the copies below are the same words (MannerTest checks them
 * against `contract/plain-error-cases.json`, made from the backend's own),
 * used only when an answer lacks them. The desktop's `manner.js` has the same.
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM.
 */
object Manner {
    const val PATH = "/api/manner"
    val MANNERS = listOf("warm", "plain")
    const val DEFAULT = "warm"

    const val TITLE = "How Jarvis talks"
    const val DETAIL =
        "Changes only how Jarvis words its answers. It never changes what Jarvis does, what it asks " +
            "you, or what it remembers."
    const val SPOKEN = "Spoken answers stay short and easy to listen to either way."
    val LABEL: Map<String, String> = linkedMapOf(
        "warm" to "Warm and brief (default)",
        "plain" to "Plain",
    )
    val WHY: Map<String, String> = linkedMapOf(
        "warm" to "Friendly and short, like a helpful person. No gushing, no filler and no emoji unless you use them.",
        "plain" to "Neutral and businesslike: just the answer, with no small talk.",
    )
    val SAID: Map<String, String> = linkedMapOf(
        "warm" to "Jarvis will now answer warmly and briefly.",
        "plain" to "Jarvis will now answer plainly.",
    )
    const val MISSING = "Your PC's Jarvis does not have this setting yet - run apply-patches.ps1 on the PC."

    data class Choice(val id: String, val label: String, val why: String)

    data class View(
        val manner: String,
        val title: String,
        val detail: String,
        val spoken: String,
        val choices: List<Choice>,
    )

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.takeIf { it.isNotBlank() }

    /** `GET /api/manner`, read - or null when it is not one (an older PC). */
    fun parse(body: JsonObject): View? {
        if ((body["available"] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == false) return null
        val given = (body["choices"] as? JsonArray) ?: return null
        val byId = given.mapNotNull { it as? JsonObject }.associateBy { it.text("id") }
        val choices = MANNERS.map { id ->
            val c = byId[id]
            Choice(id, c?.text("label") ?: LABEL.getValue(id), c?.text("why") ?: WHY.getValue(id))
        }
        return View(
            manner = body.text("manner")?.takeIf { it in MANNERS } ?: DEFAULT,
            title = body.text("title") ?: TITLE,
            detail = body.text("detail") ?: DETAIL,
            spoken = body.text("spoken") ?: SPOKEN,
            choices = choices,
        )
    }

    /** A read that failed because this PC has no manner setting. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    /** The ONE change: "warm" or "plain". Null for anything else. */
    fun body(manner: String): String? =
        if (manner in MANNERS) JsonObject(mapOf("manner" to JsonPrimitive(manner))).toString() else null

    /** What to say after a change: the PC's sentence, or the plain words of the failure. */
    fun replyLine(result: ApiResult<JsonObject>, manner: String): String = when (result) {
        is ApiResult.Ok -> result.value.text("said") ?: result.value.text("error") ?: SAID[manner].orEmpty()
        is ApiResult.Failed ->
            if (missing(result.error)) MISSING else PlainErrors.forApiError(result.error).text
    }
}
