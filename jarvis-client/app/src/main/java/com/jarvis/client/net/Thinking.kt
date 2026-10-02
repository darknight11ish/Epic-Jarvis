package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * Per-model thinking levels (Section 5.5; backend `jarvis_thinking.py`, `thinking.patch`).
 *
 * Lets Jarvis think through complex questions before answering. Thinking
 * spends conversation room (tokens).
 * Levels: Off / Quick / Deep / Auto per running model.
 * Changing levels needs NO approval card.
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM.
 */
object Thinking {
    const val PATH = "/api/thinking"
    val LEVELS = listOf("off", "quick", "deep", "auto")
    const val DEFAULT = "off"

    const val TITLE = "Thinking levels"
    const val DETAIL =
        "Lets Jarvis think through complex questions before answering. " +
            "Thinking spends some of your conversation room."
    const val NOTICE =
        "Thinking uses conversation room: when Jarvis thinks before answering, " +
            "the thinking tokens take up part of the conversation room."
    const val MISSING =
        "Your PC's Jarvis does not have thinking controls yet - run apply-patches.ps1 on the PC."

    val LEVEL_LABELS: Map<String, String> = linkedMapOf(
        "off" to "Off",
        "quick" to "Quick",
        "deep" to "Deep",
        "auto" to "Automatic",
    )

    val WHY: Map<String, String> = linkedMapOf(
        "off" to "Off. Answers directly without an extra thinking step.",
        "quick" to "Quick thinking. Takes a brief thinking pass before answering.",
        "deep" to "Deep thinking. Takes more time and room to think through complex problems.",
        "auto" to "Automatic. Decides whether to think based on the question (simple questions stay fast, complex questions think deeply).",
    )

    data class ModelRow(
        val role: String,
        val name: String,
        val model: String,
        val level: String,
        val supported: List<String>,
        val why: String,
    )

    data class View(
        val title: String,
        val detail: String,
        val notice: String,
        val models: List<ModelRow>,
    )

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.takeIf { it.isNotBlank() }

    /** `GET /api/thinking`, read - or null when it is not one (an older PC). */
    fun parse(body: JsonObject): View? {
        if ((body["available"] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == false) return null
        val rawModels = (body["models"] as? JsonArray) ?: return null
        val models = rawModels.mapNotNull { it as? JsonObject }.map { m ->
            val role = m.text("role") ?: "everyday"
            val name = m.text("name") ?: role
            val model = m.text("model") ?: ""
            val level = m.text("level")?.takeIf { it in LEVELS } ?: DEFAULT
            val supported = (m["supported"] as? JsonArray)
                ?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }
                ?.filter { it in LEVELS }
                ?: listOf(DEFAULT)
            val why = m.text("why") ?: WHY[level] ?: ""
            ModelRow(role, name, model, level, supported, why)
        }
        return View(
            title = body.text("title") ?: TITLE,
            detail = body.text("detail") ?: DETAIL,
            notice = body.text("notice") ?: NOTICE,
            models = models,
        )
    }

    /** A read that failed because this PC has no thinking setting. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && (error.code == 404 || error.code == 501 || error.code == 503))

    /** `POST /api/thinking` body string for changing a model's thinking level. */
    fun bodyString(role: String, level: String): String {
        require(level in LEVELS) { "unknown thinking level: $level" }
        return JsonObject(
            mapOf(
                "role" to JsonPrimitive(role),
                "level" to JsonPrimitive(level),
            )
        ).toString()
    }

    /** What to say after a change: the PC's sentence, or the plain words of the failure. */
    fun replyLine(result: ApiResult<JsonObject>, level: String): String = when (result) {
        is ApiResult.Ok -> result.value.text("message") ?: result.value.text("said") ?: result.value.text("error") ?: "Thinking set to $level."
        is ApiResult.Failed ->
            if (missing(result.error)) MISSING else PlainErrors.forApiError(result.error).text
    }
}
