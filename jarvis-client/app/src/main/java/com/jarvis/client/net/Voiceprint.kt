package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull

/**
 * "Write like me" (jarvis_voiceprint.py): the owner's own writing samples, the
 * ON/OFF switch, and the question Forget asks first.
 *
 * Pure Kotlin, no Android types - the JVM test (`VoiceprintTest`) runs it on a
 * plain JVM. The desktop page (src/voiceprint-settings.js) renders the same
 * words; both send ONE change per tap and neither raises an approval card -
 * these are local settings, so rule 4's "held on a stale link" is the only
 * holding that applies.
 */
object Voiceprint {
    const val PATH = "/api/voiceprint"
    const val SAMPLE_PATH = "/api/voiceprint/sample"
    const val FORGET_PATH = "/api/voiceprint/forget"
    const val ENABLED_PATH = "/api/voiceprint/enabled"
    const val MAX_TEXT = 4000

    const val TITLE = "Write like me"
    const val DETAIL =
        "Teach Jarvis how you write - sentence length, contractions, words you never use, and " +
            "examples of your own messages - so drafts sound like you, not a chatbot."
    const val SWITCH_LABEL = "Write like me when drafting"
    const val SWITCH_DETAIL =
        "Off by default. Adds a short style block to local drafts only; never to Temporary chat " +
            "or to an external chatbot."
    const val EMPTY = "No samples yet. Paste one above to begin."
    const val SAMPLE_HINT =
        "Paste a message or email you wrote. Names, dates, amounts, links and numbers are removed " +
            "before it is kept."
    const val FORGET_LABEL = "Forget this sample"
    const val MISSING = "Your PC's Jarvis does not have Write like me yet - run apply-patches.ps1 on the PC."

    /** One sample the PC has already stripped. */
    data class Sample(val id: String, val text: String, val kind: String)

    data class View(
        val enabled: Boolean,
        val samples: List<Sample>,
        val count: Int,
        val message: String,
        val scrubber: Boolean,
    )

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.takeIf { it.isNotBlank() }

    private fun JsonObject.flag(key: String): Boolean =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == true

    /** `GET /api/voiceprint`, or null when this is not one (an older PC). */
    fun parse(body: JsonObject): View? {
        if ((body["available"] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == false) return null
        val rows = (body["samples"] as? JsonArray) ?: JsonArray(emptyList())
        val samples = rows.mapNotNull { row ->
            val o = row as? JsonObject ?: return@mapNotNull null
            val id = o.text("id") ?: return@mapNotNull null
            Sample(id, o.text("text") ?: "", o.text("kind") ?: "sample")
        }
        val count = (body["count"] as? JsonPrimitive)?.takeIf { !it.isString }?.intOrNull ?: samples.size
        val message = if (samples.isEmpty()) EMPTY else oMessage(body)
        return View(
            enabled = body.flag("enabled"),
            samples = samples,
            count = count,
            message = message,
            scrubber = body.flag("scrubber") || (body["scrubber"] as? JsonPrimitive) == null,
        )
    }

    private fun oMessage(body: JsonObject): String =
        (body["message"] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.takeIf { it.isNotBlank() } ?: ""

    fun sampleProblem(text: String): String? {
        val t = text.trim()
        return when {
            t.isEmpty() -> "Write or paste something first."
            t.length > MAX_TEXT -> "That is too long - at most $MAX_TEXT characters."
            else -> null
        }
    }

    /** The question Forget always asks; the desktop says the same in its own words. */
    fun forgetAsk(sample: Sample): String {
        val words = sample.text.trim().take(60)
        return "Forget this sample?" + if (words.isEmpty()) "" else "\n\n\"$words\"" +
            "\n\nIt asks first because it cannot be undone."
    }

    /** The body ONE switch tap sends. The command answers only when the PC accepted it. */
    fun enabledBody(on: Boolean): JsonObject =
        JsonObject(mapOf("enabled" to JsonPrimitive(on)))
}
