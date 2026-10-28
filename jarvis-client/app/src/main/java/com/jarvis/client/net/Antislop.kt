package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull

/**
 * "Anti-Slop filter": the master switch and the During/After mode, under
 * Settings -> "How Jarvis talks" (2026-10-28; docs/JARVIS-API.md section 159;
 * backend `jarvis_antislop.py`).
 *
 * The rules it filters against are the MIT-licensed `miqdadbadjuber/anti-slop`
 * ruleset, distilled on the PC to the few that fit a local model's prompt
 * budget. ON changes only the WORDING of an answer - never what Jarvis does,
 * asks or remembers - so neither direction raises an approval card. OFF costs
 * 0 prompt tokens and rewrites nothing.
 *
 * WHAT THE PHONE HAS, AND WHAT IT DELIBERATELY DOES NOT. The desktop's card
 * also carries the three scopes, the Delivery Gate switch and the three
 * Liveliness dials; the phone has the master switch and the mode only. That is
 * a settings MIRROR, not a second editor: it is the same pair of controls the
 * phone already keeps for "How Jarvis talks" and Voice, in the same words. It
 * adds no model list, no preset browser and no new route (ARCHITECTURE
 * section 8's one-sided-on-purpose note, and `tools/check_parity.py`).
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM (AntislopTest).
 */
object Antislop {
    const val PATH = "/api/antislop"
    const val TITLE = "Anti-Slop filter"

    val MODES = listOf("during", "after")
    const val DEFAULT_MODE = "during"

    const val DETAIL =
        "Checks what Jarvis writes against the anti-slop rules and takes out the tells that " +
            "read as machine-made: em-dashes in prose, AI buzzwords, decorative comment " +
            "banners, dead buttons and unreadable contrast."
    const val OFF_NOTE =
        "Off: costs 0 prompt tokens. Nothing is added to a prompt and no answer is rewritten."
    const val MISSING =
        "Your PC's Jarvis cannot filter AI slop yet - run apply-patches.ps1 on the PC."

    /** What each mode is called, in the desktop card's own words. */
    val MODE_LABEL: Map<String, String> = linkedMapOf(
        "during" to "During - filter as Jarvis writes",
        "after" to "After - audit and list numbered findings",
    )
    val MODE_WHY: Map<String, String> = linkedMapOf(
        "during" to "The rules go into the turn and the answer is cleaned before you read it. " +
            "This is the default.",
        "after" to "Jarvis changes nothing and shows a numbered list of what is wrong, so you " +
            "pick what to fix.",
    )

    val SAID: Map<Boolean, String> = mapOf(
        true to "Anti-Slop filter is on. Answers are filtered from the next turn.",
        false to "Anti-Slop filter is off. That costs 0 prompt tokens: nothing is added to a " +
            "prompt and nothing is rewritten.",
    )
    val MODE_SAID: Map<String, String> = mapOf(
        "during" to "Anti-Slop will filter while Jarvis writes.",
        "after" to "Anti-Slop will audit and list findings, and change nothing.",
    )

    /** The half of the PC's answer this screen shows. */
    data class View(
        val enabled: Boolean,
        val mode: String,
        val detail: String = DETAIL,
        val offNote: String = OFF_NOTE,
    )

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.takeIf { it.isNotBlank() }

    /**
     * `GET /api/antislop`, read - or null when it is not one (an older PC).
     *
     * A body with no `enabled` yes-or-no is NOT read as "off": that is a state
     * nobody could read, and the caller shows [MISSING] rather than a switch
     * sitting at "off" over a route that is not there.
     */
    fun parse(body: JsonObject): View? {
        if ((body["available"] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == false) {
            return null
        }
        val enabled = (body["enabled"] as? JsonPrimitive)?.booleanOrNull ?: return null
        val mode = body.text("mode")?.takeIf { it in MODES } ?: DEFAULT_MODE
        return View(
            enabled = enabled,
            mode = mode,
            detail = body.text("detail") ?: DETAIL,
            offNote = body.text("off_note") ?: OFF_NOTE,
        )
    }

    /** A read that failed because this PC has no anti-slop route. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    /** The ONE change the switch sends. */
    fun enabledBody(on: Boolean): String = buildJsonObject {
        put("enabled", JsonPrimitive(on))
    }.toString()

    /** The ONE change the mode sends. Null for anything that is not a mode. */
    fun modeBody(mode: String): String? =
        if (mode in MODES) buildJsonObject { put("mode", JsonPrimitive(mode)) }.toString() else null

    /** What to say after a change: the PC's sentence, or the plain words of the failure. */
    fun replyLine(result: ApiResult<JsonObject>, on: Boolean): String = when (result) {
        is ApiResult.Ok -> (result.value["said"] as? JsonPrimitive)?.contentOrNull
            ?: (result.value["error"] as? JsonPrimitive)?.contentOrNull
            ?: SAID.getValue(on)
        is ApiResult.Failed ->
            if (missing(result.error)) MISSING else PlainErrors.forApiError(result.error).text
    }

    /** The same shape for the mode radio. */
    fun modeReplyLine(result: ApiResult<JsonObject>, mode: String): String = when (result) {
        is ApiResult.Ok -> (result.value["said"] as? JsonPrimitive)?.contentOrNull
            ?: (result.value["error"] as? JsonPrimitive)?.contentOrNull
            ?: MODE_SAID.getValue(mode)
        is ApiResult.Failed ->
            if (missing(result.error)) MISSING else PlainErrors.forApiError(result.error).text
    }
}
