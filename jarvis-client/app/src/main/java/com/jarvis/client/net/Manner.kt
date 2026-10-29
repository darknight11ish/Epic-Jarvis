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
 * shows those; the copies below are the same words (PlainErrorsTest checks
 * them against `contract/plain-error-cases.json`, made from the backend's
 * own), used only when an answer lacks them. The desktop's `manner.js` has
 * the same.
 *
 * SINCE 2026-10-28 THE SAME ANSWER CARRIES THE PERSONALITY PRESETS (§27.7:
 * ten built-ins plus the owner's saved ones). The warm/plain pair is the
 * LEGACY shape, kept for a PC that does not send the list; when it does send
 * one, that list is the screen and the two choices are not drawn at all -
 * exactly what the desktop's Settings panel does (`manner-settings.js`
 * `paintPersona()` hides the same list). Why it matters: `manner` is DERIVED
 * on the PC (`jarvis_manner.current()`: warm only for `warm_peer`, plain for
 * every other preset), so a screen that marks "Plain" while the PC is
 * Classic British Butler is naming a preset that is not in use. The mark must
 * come from the PC's `personality`, never from `manner`.
 *
 * The list, the names, the order and the descriptions are the PC's
 * (`jarvis_manner.view_personalities()`), read through this one GET: nothing
 * here writes its own copy of a preset, and the only write is one field
 * (`{"personality": "<id>"}`), which is cardless on the PC because a
 * personality changes wording only.
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM.
 */
object Manner {
    const val PATH = "/api/manner"
    val MANNERS = listOf("warm", "plain")
    const val DEFAULT = "warm"

    /** The backend's event kind for "how Jarvis talks" changed somewhere. */
    const val EVENT = "manner"

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

    /**
     * The four dials are the desktop editor's (docs/ARCHITECTURE.md §8 says
     * why). The phone says where they are instead of drawing a second, weaker
     * control that could disagree with the PC's own.
     */
    const val DIALS_ON_PC =
        "Wit, answer length, formality and how Jarvis addresses you are set on your PC, " +
            "in Settings \u2192 How Jarvis talks."

    /** The list's heading on Mind, above the PC's presets. */
    const val PERSONALITIES_TITLE = "Personalities"

    // Humour (the owner's decision, 2026-09-27): "a switch in 'How Jarvis
    // talks', off to start; never on cards, errors or serious topics." A
    // second, independent switch beside manner, on the SAME `/api/manner`
    // route, so setting one never resets the other.
    const val HUMOR_TITLE = "Humour"
    const val HUMOR_DETAIL =
        "Off by default. Never as part of an approval, an error message, or a serious or " +
            "sensitive topic."
    val HUMOR_SAID: Map<Boolean, String> = mapOf(
        true to "Jarvis may now use a little humour, when it fits.",
        false to "Jarvis will not use humour.",
    )

    data class Choice(val id: String, val label: String, val why: String)

    /**
     * ONE personality preset, exactly as the PC lists it (§27.7). [title] and
     * [description] are the PC's own words - this app never writes its own.
     * [builtin] is false for a "My personalities" preset the owner saved.
     */
    data class Personality(
        val id: String,
        val title: String,
        val description: String,
        val builtin: Boolean = true,
    )

    data class View(
        val manner: String,
        val title: String,
        val detail: String,
        val spoken: String,
        val choices: List<Choice>,
        val humor: Boolean = false,
        val humorTitle: String = HUMOR_TITLE,
        val humorDetail: String = HUMOR_DETAIL,
        /**
         * The PC's personality presets, in the PC's order - ten built-ins then
         * the owner's saved ones. Empty on a PC older than §27.7, and then the
         * screen keeps the legacy warm/plain pair.
         */
        val personalities: List<Personality> = emptyList(),
        /** The preset the PC is really using; "" when the answer names none. */
        val personality: String = "",
    ) {
        /** True when the PC answered with its personality list (the new shape). */
        val hasPersonalities: Boolean get() = personalities.isNotEmpty()

        /** The preset the PC marks as in use, or null when it names none. */
        val activePersonality: Personality?
            get() = personalities.firstOrNull { it.id == personality }

        /** The one marked row - never derived from the legacy manner word. */
        fun isCurrent(preset: Personality): Boolean = preset.id == personality
    }

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
        // The personality list (§27.7). A row with no id is not a preset, and
        // the PC's order is kept as sent - sorting or re-naming here would be
        // this app disagreeing with the screen next to it.
        val personalities = (body["personalities"] as? JsonArray)
            ?.mapNotNull { row ->
                val o = row as? JsonObject ?: return@mapNotNull null
                val id = o.text("id") ?: return@mapNotNull null
                Personality(
                    id = id,
                    title = o.text("title") ?: id,
                    description = o.text("description").orEmpty(),
                    builtin = (o["builtin"] as? JsonPrimitive)?.booleanOrNull ?: true,
                )
            }
            .orEmpty()
        // Only an id the list really carries counts as the active preset: an
        // answer naming a preset it does not list marks nothing rather than
        // marking a row that is not there.
        val personality = body.text("personality")
            ?.takeIf { wanted -> personalities.any { it.id == wanted } }
            .orEmpty()
        return View(
            manner = body.text("manner")?.takeIf { it in MANNERS } ?: DEFAULT,
            title = body.text("title") ?: TITLE,
            detail = body.text("detail") ?: DETAIL,
            spoken = body.text("spoken") ?: SPOKEN,
            choices = choices,
            humor = (body["humor"] as? JsonPrimitive)?.booleanOrNull ?: false,
            humorTitle = body.text("humor_title") ?: HUMOR_TITLE,
            humorDetail = body.text("humor_detail") ?: HUMOR_DETAIL,
            personalities = personalities,
            personality = personality,
        )
    }

    /** A read that failed because this PC has no manner setting. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    /** The ONE change: "warm" or "plain". Null for anything else. */
    fun body(manner: String): String? =
        if (manner in MANNERS) JsonObject(mapOf("manner" to JsonPrimitive(manner))).toString() else null

    /**
     * The ONE field that switches to a personality preset (§27.7) - the same
     * body the desktop sends (`personalities.js` `usePresetBody`). Never a
     * `manner` word: sending `{"manner": "plain"}` would flatten the PC's
     * chosen preset to `tactical_ops` AND reset the four dials
     * (`jarvis_manner.handle_set`'s legacy branch), which is exactly the
     * disagreement this screen must not cause.
     */
    fun personalityBody(id: String): String? =
        id.trim().takeIf { it.isNotEmpty() }
            ?.let { JsonObject(mapOf("personality" to JsonPrimitive(it))).toString() }

    /** Humour on or off, at once, no card either way - the SAME route
     * ([body]'s), so setting one never resets the other. */
    fun humorBody(on: Boolean): String = JsonObject(mapOf("humor" to JsonPrimitive(on))).toString()

    /** What to say after a change: the PC's sentence, or the plain words of the failure. */
    fun replyLine(result: ApiResult<JsonObject>, manner: String): String = when (result) {
        is ApiResult.Ok -> result.value.text("said") ?: result.value.text("error") ?: SAID[manner].orEmpty()
        is ApiResult.Failed ->
            if (missing(result.error)) MISSING else PlainErrors.forApiError(result.error).text
    }

    /**
     * What to say after switching a personality: the PC's own switch line
     * (its preset's `switch_ack`) when it sends one. The fallback names the
     * preset the owner tapped, never a word this app invented about it.
     */
    fun personalityReplyLine(result: ApiResult<JsonObject>, title: String): String = when (result) {
        is ApiResult.Ok -> result.value.text("said") ?: result.value.text("error")
            ?: "Switched to $title."
        is ApiResult.Failed ->
            if (missing(result.error)) MISSING else PlainErrors.forApiError(result.error).text
    }

    /** What to say after changing humour: the same shape as [replyLine]. */
    fun humorReplyLine(result: ApiResult<JsonObject>, on: Boolean): String = when (result) {
        is ApiResult.Ok -> result.value.text("said") ?: result.value.text("error") ?: HUMOR_SAID[on].orEmpty()
        is ApiResult.Failed ->
            if (missing(result.error)) MISSING else PlainErrors.forApiError(result.error).text
    }
}
