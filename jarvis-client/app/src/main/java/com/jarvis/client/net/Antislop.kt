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
 * WHAT THE PHONE HAS, AND WHAT IT DELIBERATELY DOES NOT. The phone has the
 * master switch, the em-dash exemption and the During/After mode. The desktop's
 * card also carries the three scopes, the Delivery Gate switch and the three
 * Liveliness dials, and those stay there. That is a settings MIRROR, not a
 * second editor: it is the same shape the phone already keeps for "How Jarvis
 * talks" and Voice, in the same words. The em-dash exemption is on the phone
 * because it is the owner's own writing voice rather than tuning, and the same
 * one-line explanation rides with it (2026-10-28, Gemini review Q3). It adds no
 * model list, no preset browser and no new route (ARCHITECTURE section 8's
 * one-sided-on-purpose note, and `tools/check_parity.py`).
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM (AntislopTest).
 */
object Antislop {
    const val PATH = "/api/antislop"
    const val TITLE = "Anti-Slop filter"

    /**
     * The frame the PC publishes when the filter changed anywhere else - chat,
     * the desktop card, another phone (`jarvis_antislop._publish`: one kind per
     * feature, carrying the whole state). The phone takes it as a doorbell like
     * every other kind: the plate re-reads [PATH] rather than parsing a second
     * shape, and only while that plate is open (JarvisRuntime.antislopTick).
     */
    const val EVENT = "antislop"

    val MODES = listOf("during", "after")
    const val DEFAULT_MODE = "during"

    const val DETAIL =
        "Watches what Jarvis writes for the tells that read as machine-made: em-dashes in " +
            "prose, AI buzzwords, decorative comment banners, dead buttons and unreadable " +
            "contrast."
    const val OFF_NOTE =
        "Off: costs 0 prompt tokens. Nothing is added to a prompt and no answer is rewritten."
    const val MISSING =
        "Your PC's Jarvis cannot filter AI slop yet - run apply-patches.ps1 on the PC."

    /**
     * What is really enforced, in ONE sentence (2026-10-28, Gemini review Q1),
     * in the desktop card's own words. The rules split two ways and the screen
     * may not blur them: the fixed list (em-dashes, buzzwords, comment banners,
     * dead buttons, contrast, focus rings, glass and glow caps) is checked in
     * code on the PC, while layout, taste and rendered sizes are guidance that
     * only a real browser or a person can judge. `AntislopTest` fails if the
     * sentence stops saying "guidance only".
     */
    const val REALITY =
        "Guides what Jarvis writes, then checks a fixed list in code (em-dashes, buzzwords, " +
            "comment banners, dead buttons, contrast, focus rings, glass and glow caps); " +
            "layout, taste and rendered sizes are guidance only."

    /**
     * The em-dash exemption (2026-10-28, Gemini review Q3; `R-02` vs `R-37`).
     * OFF is the PC's default. It is NOT the voiceprint rule: Write Like Me
     * already wins on its own when the owner's samples use em-dashes, whatever
     * this says - this is the blanket "keep them everywhere" on top.
     */
    const val EM_DASH_LABEL = "Allow em-dashes (\u2014)"
    const val EM_DASH_DETAIL =
        "Write Like Me's own em-dash habit already wins; this keeps them everywhere."

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
    val EM_DASH_SAID: Map<Boolean, String> = mapOf(
        true to "Em-dashes are allowed everywhere now.",
        false to "Em-dashes are stripped from prose again.",
    )

    /** The half of the PC's answer this screen shows. */
    data class View(
        val enabled: Boolean,
        val mode: String,
        val allowEmDashes: Boolean = false,
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
            // OFF unless the PC says a real `true`: a backend that predates the
            // field paints the box unticked, which is the state it holds. A
            // JSON string ("true") is not a yes - a stray string must not tick
            // a box the owner never ticked.
            allowEmDashes = (body["allow_em_dashes"] as? JsonPrimitive)
                ?.takeIf { !it.isString }
                ?.booleanOrNull == true,
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

    /**
     * The ONE change the em-dash exemption sends, in the PC's own spelling
     * (`allow_em_dashes`). Ticking it never resets the switch or the mode.
     */
    fun emDashBody(on: Boolean): String = buildJsonObject {
        put("allow_em_dashes", JsonPrimitive(on))
    }.toString()

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

    /** The same shape for the em-dash exemption. */
    fun emDashReplyLine(result: ApiResult<JsonObject>, on: Boolean): String = when (result) {
        is ApiResult.Ok -> (result.value["said"] as? JsonPrimitive)?.contentOrNull
            ?: (result.value["error"] as? JsonPrimitive)?.contentOrNull
            ?: EM_DASH_SAID.getValue(on)
        is ApiResult.Failed ->
            if (missing(result.error)) MISSING else PlainErrors.forApiError(result.error).text
    }
}
