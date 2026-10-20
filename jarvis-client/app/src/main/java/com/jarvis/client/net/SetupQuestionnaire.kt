package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.put

/**
 * The setup questionnaire on the phone (docs/JARVIS-API.md section 147; the
 * PC's module is `backend/jarvis_setup.py`, its routes are installed by
 * `setup.patch`).
 *
 * READ-ONLY, ON PURPOSE. The phone reads the same fourteen questions, the
 * current values and the last accepted answers, and it may ask the PC for the
 * read-only plan (`POST /api/setup/plan` writes nothing and raises no card), so
 * the owner can see what their answers would change and what each change
 * costs: instant, one of the PC's own approval cards, or blocked on this PC.
 *
 * IT NEVER APPLIES ANYTHING. `POST /api/setup/apply` is deliberately not in
 * this file: applying works through the changes one at a time, waits on each
 * existing card, and some of them (a loosening rule, offering a reading tool)
 * can only be changed from the PC. A phone button that posted it would either
 * fail halfway or sit for minutes behind cards it cannot answer. So the last
 * step stays on the PC, and this screen says so in plain words ([PLAIN_ONLY]).
 * `SetupQuestionnaireTest` reads this file back as text and fails if an apply
 * path or a `confirm` body ever appears.
 *
 * Pure Kotlin, no Android types and no HTTP: `JarvisApi` sends the two reads,
 * `JarvisRuntime` holds them behind the link, and `SetupQuestionnairePlate`
 * draws them. Every question, choice, help line and sentence comes from the
 * PC; the copies below are only the words this app needs when an answer lacks
 * its own, the same shape [PromptCoach] uses.
 */
object SetupQuestionnaire {
    /** The reading, and the read-only plan. There is no apply path here. */
    const val PATH = "/api/setup"
    const val PLAN_PATH = "/api/setup/plan"

    // This screen's own words. Every question and choice is the PC's.
    const val HEADING = "First-time setup"
    const val TITLE = "First-time setup"
    const val KICKER =
        "Fourteen questions about how you want Jarvis to behave. Every answer " +
            "changes settings that already exist; nothing here is a new kind of rule."
    const val HELP =
        "Pick the answers that sound like you, then read what would change. " +
            "Anything that loosens a rule still shows its own approval card on the PC, " +
            "one at a time."
    const val PLAIN_ONLY =
        "This screen only shows what your answers would change. The changes are " +
            "made on the PC, in the same card there; nothing is applied from here."
    const val UPDATE_WORDS =
        "This PC's Jarvis does not have the setup questionnaire yet. Update the " +
            "backend by running apply-patches.ps1 on the PC, then open this again."
    const val MISSING = UPDATE_WORDS
    const val NOTHING_CHANGED =
        "Nothing has been changed. Pick answers to see the plan below; applying " +
            "them is a step on the PC."
    const val CHOOSE_FIRST = "Pick at least one answer to see what it would change."
    const val NOTHING_TO_APPLY =
        "Nothing would change with these answers. Choose something different on the PC."
    const val PLAN_HEADING = "What would change"
    const val SKIPPED_HEADING = "What would not change"
    const val RECOMMENDATION_HEADING = "Recommended setup"
    const val LAST_RUN_HEADING = "Last time, on your PC"
    const val ALL = "All"
    const val NONE = "None"
    const val REFRESH = "Refresh"
    const val PLAN_ACTION = "See what this would change"
    const val PLAN_READING = "Working out what would change…"

    /** The PC decides which of these a change has. */
    val EFFECT_WORDS: Map<String, String> = mapOf(
        "instant" to "Instant",
        "card" to "Asks you on a card",
        "blocked" to "Blocked",
    )

    /** The PC's own outcome states, in the owner's language. */
    val OUTCOME_WORDS: Map<String, String> = mapOf(
        "changed" to "Changed.",
        "asked-and-approved" to "Changed - you approved its card.",
        "asked-and-denied" to "Not changed - the card was not approved.",
        "asked-no-answer" to "Still waiting: answer its card on the PC and it changes.",
        "not-available" to "Not available on this PC.",
        "not-changed" to "Not changed.",
        "failed" to "Did not change.",
    )

    data class Option(val id: String, val label: String, val detail: String)

    data class Question(
        val id: String,
        val title: String,
        val help: String,
        val multi: Boolean,
        val allNone: Boolean,
        val options: List<Option>,
    )

    data class Outcome(
        val setting: String,
        val label: String,
        val effect: String,
        val state: String,
        val message: String,
    )

    data class View(
        val available: Boolean,
        val reason: String,
        val questions: List<Question>,
        val answers: Map<String, List<String>>,
        val completedAt: Double?,
        val lastOutcomes: List<Outcome>,
        val cardWaitS: Int?,
        val about: String,
        val storage: String,
    )

    data class Change(
        val setting: String,
        val label: String,
        val question: String,
        val from: String,
        val to: String,
        val effect: String,
        val sentence: String,
    )

    data class Skipped(val setting: String, val reason: String)

    data class Recommendation(val id: String, val title: String, val why: String)

    data class Plan(
        val ok: Boolean,
        val error: String,
        val changes: List<Change>,
        val summary: List<String>,
        val skipped: List<Skipped>,
        val recommendation: Recommendation?,
    )

    /** The effect word, or the PC's own word when it is not one this app knows. */
    fun effectWords(effect: String?): String {
        val key = effect.orEmpty().trim().lowercase()
        return EFFECT_WORDS[key] ?: key.ifEmpty { "Unknown" }
    }

    /** One outcome's fixed words, or empty for a state this app does not know. */
    fun outcomeWords(state: String?): String =
        OUTCOME_WORDS[state.orEmpty().trim().lowercase()].orEmpty()

    /** "Each approval card can wait up to 5 minutes for you before the
     *  questionnaire moves on." Never seconds. */
    fun cardWaitWords(seconds: Int?): String {
        val minutes = if (seconds != null && seconds > 0) {
            maxOf(1, Math.round(seconds / 60.0).toInt())
        } else {
            5
        }
        val unit = if (minutes == 1) "minute" else "minutes"
        return "Each approval card can wait up to $minutes $unit for you before the " +
            "questionnaire moves on."
    }

    /** "on"/"off" for a boolean change, else the PC's own word. */
    fun valueWords(value: JsonElement?): String {
        val prim = value as? JsonPrimitive ?: return "not set"
        if (prim is JsonNull) return "not set"
        if (prim.isString) return prim.contentOrNull.orEmpty().ifEmpty { "not set" }
        return prim.booleanOrNull?.let { if (it) "on" else "off" }
            ?: prim.contentOrNull.orEmpty().ifEmpty { "not set" }
    }

    /** [path] with a 404/501 or "missing feature" answer is an older backend. */
    fun missing(error: String?): Boolean {
        val text = error.orEmpty()
        return text.contains("404") || text.contains("501") ||
            text.contains(MISSING, ignoreCase = true) ||
            text.contains("missing this feature", ignoreCase = true)
    }

    /** `GET /api/setup`, as the small reading this screen draws. */
    fun parse(body: JsonObject?): View? {
        body ?: return null
        val available = body.flag("available") ?: true
        val questions = (body["questions"] as? JsonArray).orEmpty().mapNotNull { row ->
            question(row)
        }
        return View(
            available = available,
            reason = if (available) {
                body.text("error") ?: ""
            } else {
                body.text("why") ?: UPDATE_WORDS
            },
            questions = questions,
            answers = answers(body["answers"]),
            completedAt = (body["completed_at"] as? JsonPrimitive)
                ?.takeIf { !it.isString }?.contentOrNull?.toDoubleOrNull(),
            lastOutcomes = (body["last_outcomes"] as? JsonArray).orEmpty()
                .mapNotNull { outcome(it) },
            cardWaitS = (body["card_wait_s"] as? JsonPrimitive)
                ?.takeIf { !it.isString }?.intOrNull,
            about = body.text("about") ?: "",
            storage = body.text("storage") ?: "",
        )
    }

    private fun question(row: JsonElement?): Question? {
        val body = row as? JsonObject ?: return null
        val id = body.text("id")?.trim().orEmpty()
        if (id.isEmpty()) return null
        val options = (body["options"] as? JsonArray).orEmpty().mapNotNull { option(it) }
        if (options.isEmpty()) return null
        val multi = body.flag("multi") == true
        return Question(
            id = id,
            title = body.text("title") ?: id,
            help = body.text("help") ?: "",
            multi = multi,
            allNone = body.flag("all_none") == true || multi,
            options = options,
        )
    }

    private fun option(row: JsonElement?): Option? {
        val body = row as? JsonObject ?: return null
        val id = body.text("id")?.trim().orEmpty()
        if (id.isEmpty()) return null
        return Option(
            id = id,
            label = body.text("label") ?: id,
            detail = body.text("detail") ?: "",
        )
    }

    private fun outcome(row: JsonElement?): Outcome? {
        val body = row as? JsonObject ?: return null
        val setting = body.text("setting")?.trim().orEmpty()
        if (setting.isEmpty()) return null
        return Outcome(
            setting = setting,
            label = body.text("label") ?: setting,
            effect = body.text("effect") ?: "",
            state = body.text("state") ?: "",
            message = body.text("message") ?: "",
        )
    }

    /** The answers object, where a one-choice answer may be a bare string. */
    fun answers(body: JsonElement?): Map<String, List<String>> {
        val obj = body as? JsonObject ?: return emptyMap()
        val out = LinkedHashMap<String, List<String>>()
        for ((key, value) in obj) {
            val values = when (value) {
                is JsonArray -> value.mapNotNull { prim ->
                    (prim as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
                }
                is JsonPrimitive -> listOfNotNull(
                    value.takeIf { it.isString }?.contentOrNull,
                )
                else -> emptyList()
            }
            val picked = values.filter { it.isNotBlank() }
            if (picked.isNotEmpty()) out[key] = picked
        }
        return out
    }

    /** The draft to start from: the last accepted answers this PC still offers. */
    fun initialDraft(view: View): Map<String, List<String>> {
        val out = LinkedHashMap<String, List<String>>()
        for (question in view.questions) {
            val saved = view.answers[question.id] ?: continue
            val known = question.options.map { it.id }.toSet()
            val picked = if (question.multi) {
                saved.filter { it in known || it == "all" || it == "none" }
            } else {
                saved.filter { it in known }
            }
            if (picked.isNotEmpty()) out[question.id] = if (question.multi) picked else picked.take(1)
        }
        return out
    }

    /** Is this choice on in the draft? "all" means every choice is on. */
    fun picked(draft: Map<String, List<String>>, question: Question, optionId: String): Boolean {
        val value = draft[question.id] ?: return false
        if (value.isEmpty()) return false
        if (value.size == 1 && value[0] == "all") return true
        if (value.size == 1 && value[0] == "none") return false
        return optionId in value
    }

    /** "all", "none", or "" for the All/None pressed state. */
    fun allNoneState(draft: Map<String, List<String>>, questionId: String): String {
        val value = draft[questionId] ?: return ""
        return if (value.size == 1 && (value[0] == "all" || value[0] == "none")) value[0] else ""
    }

    /** One answer to a one-choice question. Returns a new draft. */
    fun chooseOne(
        draft: Map<String, List<String>>,
        questionId: String,
        optionId: String,
    ): Map<String, List<String>> {
        val next = LinkedHashMap(draft)
        if (optionId.isBlank()) next.remove(questionId) else next[questionId] = listOf(optionId)
        return next
    }

    /** "All" for a choose-any question: the PC expands it, both apps agree. */
    fun chooseAll(draft: Map<String, List<String>>, questionId: String): Map<String, List<String>> =
        LinkedHashMap(draft).also { it[questionId] = listOf("all") }

    /** "None" for a choose-any question. */
    fun chooseNone(draft: Map<String, List<String>>, questionId: String): Map<String, List<String>> =
        LinkedHashMap(draft).also { it[questionId] = listOf("none") }

    /**
     * Flip ONE choice of a choose-any question, returning a new draft. The same
     * rule as the desktop's `toggleOption`: from "All", unticking one is the
     * concrete rest; from "None", ticking one is that one.
     */
    fun toggle(
        draft: Map<String, List<String>>,
        question: Question,
        optionId: String,
    ): Map<String, List<String>> {
        if (optionId.isBlank()) return draft
        val value = draft[question.id].orEmpty()
        val pickedSet = when {
            value.size == 1 && value[0] == "all" ->
                question.options.map { it.id }.filter { it != optionId }.toMutableList()
            value.isEmpty() || (value.size == 1 && value[0] == "none") ->
                mutableListOf(optionId)
            else -> {
                val current = value.toMutableList()
                if (optionId in current) current.remove(optionId) else current.add(optionId)
                current
            }
        }
        val next = LinkedHashMap(draft)
        if (pickedSet.isEmpty()) next.remove(question.id)
        else next[question.id] = pickedSet
        return next
    }

    /** How many questions the draft has answered. */
    fun answeredCount(draft: Map<String, List<String>>): Int =
        draft.values.count { it.isNotEmpty() && !(it.size == 1 && it[0] == "none") }

    /**
     * `POST /api/setup/plan`'s body. READ-ONLY on the PC: the answers and
     * nothing else. There is no `confirm` field in it at all, so this body can
     * never change a setting.
     */
    fun planBody(
        draft: Map<String, List<String>>,
        multiIds: Set<String>,
    ): String = buildJsonObject {
        put("answers", buildJsonObject {
            for ((questionId, values) in draft) {
                val picked = values.filter { it.isNotBlank() }
                if (picked.isEmpty()) continue
                if (questionId in multiIds) {
                    put(questionId, JsonArray(picked.map { JsonPrimitive(it) }))
                } else {
                    put(questionId, JsonPrimitive(picked.first()))
                }
            }
        })
    }.toString()

    /** `POST /api/setup/plan`'s answer, as the plan this screen draws. */
    fun parsePlan(body: JsonObject?): Plan {
        body ?: return failedPlan("The plan could not be read.")
        if (body.flag("ok") == false) {
            return failedPlan(body.text("error") ?: "The plan could not be read.")
        }
        val changes = (body["changes"] as? JsonArray).orEmpty().mapNotNull { row ->
            val change = row as? JsonObject ?: return@mapNotNull null
            val setting = change.text("setting")?.trim().orEmpty()
            if (setting.isEmpty()) return@mapNotNull null
            Change(
                setting = setting,
                label = change.text("label") ?: setting,
                question = change.text("question") ?: "",
                from = valueWords(change["from"]),
                to = valueWords(change["to"]),
                effect = change.text("effect") ?: "",
                sentence = change.text("sentence") ?: "",
            )
        }
        val skipped = (body["skipped"] as? JsonArray).orEmpty().mapNotNull { row ->
            val skip = row as? JsonObject ?: return@mapNotNull null
            Skipped(
                setting = skip.text("setting") ?: "",
                reason = skip.text("reason") ?: "Not changing.",
            )
        }
        val rec = body["recommendation"] as? JsonObject
        return Plan(
            ok = true,
            error = "",
            changes = changes,
            summary = (body["summary"] as? JsonArray).orEmpty().mapNotNull { prim ->
                (prim as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
            },
            skipped = skipped,
            recommendation = rec?.let {
                Recommendation(
                    id = it.text("id") ?: "",
                    title = it.text("title") ?: it.text("id") ?: "",
                    why = it.text("why") ?: "",
                )
            },
        )
    }

    private fun failedPlan(error: String): Plan =
        Plan(ok = false, error = error, changes = emptyList(), summary = emptyList(),
            skipped = emptyList(), recommendation = null)
}

private fun JsonObject.text(key: String): String? {
    val prim = this[key] as? JsonPrimitive ?: return null
    if (prim is JsonNull || !prim.isString) return null
    return prim.contentOrNull
}

private fun JsonObject.flag(key: String): Boolean? {
    val prim = this[key] as? JsonPrimitive ?: return null
    if (prim is JsonNull || prim.isString) return null
    return prim.booleanOrNull
}
