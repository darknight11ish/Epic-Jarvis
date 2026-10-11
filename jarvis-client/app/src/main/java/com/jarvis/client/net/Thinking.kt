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
 * AND WHEN thinking happens at all is the owner's own choice (2026-10-11):
 * "Only when I ask" (ordinary answers are written straight away; Jarvis
 * thinks on the questions the owner asks him to) or "Always". That choice is
 * the PC's, made from either app, and [ONE_SHOT] is the one-question version
 * of asking for it - see its own doc.
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

    // ------------------------------------------- when Jarvis thinks (2026-10-11) ---
    //
    // The owner's choice, in two plain words, stored on the PC
    // (`jarvis_thinking.set_when`, in the same small `thinking.json` the levels
    // live in) and drawn on Settings. The names are the backend's own ids, so
    // nothing is translated on the way through.

    const val WHEN_ASKED = "when_asked"
    const val ALWAYS = "always"
    val WHEN_MODES = listOf(WHEN_ASKED, ALWAYS)

    /** The choice a PC that never mentions one reads as - the safe one: an
     *  ordinary answer is written straight away rather than thinking first,
     *  because thinking on is what returns an empty answer. */
    const val WHEN_DEFAULT = WHEN_ASKED

    const val WHEN_TITLE = "When Jarvis thinks"
    const val WHEN_DETAIL =
        "Thinking is the extra step some models take before answering. " +
            "It spends part of your conversation room."

    /** What the PC did not say: kept here so an older backend still draws the
     *  same two choices, in the same words. */
    val WHEN_LABELS: Map<String, String> = linkedMapOf(
        WHEN_ASKED to "Only when I ask",
        ALWAYS to "Always",
    )

    val WHEN_WHY: Map<String, String> = linkedMapOf(
        WHEN_ASKED to "Ordinary answers are written straight away. Jarvis thinks " +
            "only on the questions you ask him to think about.",
        ALWAYS to "Jarvis may think before every answer. Answers can take longer, " +
            "and thinking uses part of your conversation room.",
    )

    // ------------------------------------------- one question at a time (2026-10-11) ---
    //
    // The per-question control: "Think about this one". It sends ONE field on
    // ONE question's request and then forgets it. It is not a setting, it is
    // never stored, and it never changes the choice above - so it cannot be
    // the reason a later message behaves differently.

    /** The `/api/chat` body's field: present, and true, only on a question the
     *  owner asked Jarvis to think about - never sent as `false`, so an
     *  ordinary question is exactly what it was (the same rule
     *  [TemporaryChat.FIELD] follows). */
    const val ONE_SHOT = "think"

    /** `/api/version`'s `capabilities` name: true once the PC's chat turn
     *  really sends thinking for a question carrying [ONE_SHOT]. The button is
     *  offered only when this is true - see [offered]. */
    const val CAPABILITY = "think_per_question"

    const val ONE_SHOT_LABEL = "Think"

    /** What the button says it will do, for the screen reader and for anyone
     *  who long-presses. One question, then back to normal. */
    const val ONE_SHOT_WHY =
        "Think about this one question before answering. " +
            "Only this question - the next one is ordinary again."

    /** Is the one-question control offered on this PC? */
    fun offered(can: (String) -> Boolean): Boolean = can(CAPABILITY)

    data class ModelRow(
        val role: String,
        val name: String,
        val model: String,
        val level: String,
        val supported: List<String>,
        val why: String,
    )

    /** One of [WHEN_MODES]: what it is called, what it does, and whether it is
     *  the one now in force. */
    data class WhenChoice(
        val id: String,
        val label: String,
        val why: String,
        val selected: Boolean,
    )

    data class View(
        val title: String,
        val detail: String,
        val notice: String,
        val models: List<ModelRow>,
        val whenTitle: String = WHEN_TITLE,
        val whenDetail: String = WHEN_DETAIL,
        val whenChoices: List<WhenChoice> = defaultWhenChoices(),
    ) {
        /** The choice in force, or [WHEN_DEFAULT] when the PC did not mark one.
         *  Called `mode` rather than `when`: `when` is a Kotlin keyword and
         *  cannot be a name. */
        val mode: String get() = whenChoices.firstOrNull { it.selected }?.id ?: WHEN_DEFAULT
    }

    /** The two choices, in the order the row offers them, with [selected] on
     *  the one the PC says is in force. Used for a PC that answers no WHEN
     *  fields at all (an older backend), so the row still appears and still
     *  reads the same. */
    fun defaultWhenChoices(selected: String = WHEN_DEFAULT): List<WhenChoice> =
        WHEN_MODES.map { id ->
            WhenChoice(
                id = id,
                label = WHEN_LABELS.getValue(id),
                why = WHEN_WHY.getValue(id),
                selected = id == selected,
            )
        }

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
        // The WHEN choice, as the PC sent it. A PC that answers none of it
        // gets the same two rows in the same words, marked with the safe one -
        // never an empty panel, and never a choice the owner did not make.
        val asked = body.text("when")?.takeIf { it in WHEN_MODES }
        val rawChoices = (body["when_choices"] as? JsonArray)
            ?.mapNotNull { it as? JsonObject }
            ?.mapNotNull { c ->
                val id = c.text("id")?.takeIf { it in WHEN_MODES } ?: return@mapNotNull null
                WhenChoice(
                    id = id,
                    label = c.text("label") ?: WHEN_LABELS.getValue(id),
                    why = c.text("why") ?: WHEN_WHY.getValue(id),
                    selected = (c["selected"] as? JsonPrimitive)
                        ?.takeIf { !it.isString }?.booleanOrNull == true,
                )
            }
        val choices = when {
            rawChoices.isNullOrEmpty() -> defaultWhenChoices(asked ?: WHEN_DEFAULT)
            rawChoices.none { it.selected } && asked != null ->
                rawChoices.map { it.copy(selected = it.id == asked) }
            else -> rawChoices
        }
        return View(
            title = body.text("title") ?: TITLE,
            detail = body.text("detail") ?: DETAIL,
            notice = body.text("notice") ?: NOTICE,
            models = models,
            whenTitle = body.text("when_title") ?: WHEN_TITLE,
            whenDetail = body.text("when_detail") ?: WHEN_DETAIL,
            whenChoices = choices,
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

    /** `POST /api/thinking` body string for the owner's WHEN choice. One small
     *  object with one key, and no card either way. */
    fun whenBodyString(mode: String): String {
        require(mode in WHEN_MODES) { "unknown when: $mode" }
        return JsonObject(mapOf("when" to JsonPrimitive(mode))).toString()
    }

    /** What to say after a change: the PC's sentence, or the plain words of the failure. */
    fun replyLine(result: ApiResult<JsonObject>, level: String): String = when (result) {
        is ApiResult.Ok -> result.value.text("message") ?: result.value.text("said") ?: result.value.text("error") ?: "Thinking set to $level."
        is ApiResult.Failed ->
            if (missing(result.error)) MISSING else PlainErrors.forApiError(result.error).text
    }

    /** What to say after a WHEN change: the PC's own sentence, or the plain
     *  words of the failure - exactly as [replyLine] does for a level. */
    fun whenReplyLine(result: ApiResult<JsonObject>, mode: String): String = when (result) {
        is ApiResult.Ok -> result.value.text("message")
            ?: result.value.text("said")
            ?: result.value.text("error")
            ?: "Jarvis thinks ${WHEN_LABELS[mode]?.lowercase() ?: mode}."
        is ApiResult.Failed ->
            if (missing(result.error)) MISSING else PlainErrors.forApiError(result.error).text
    }
}
