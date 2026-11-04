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
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * "Personalize Jarvis" on the phone (docs/JARVIS-API.md section 147; the PC's
 * module is `backend/jarvis_setup.py`, its routes are installed by
 * `setup.patch`).
 *
 * READ-ONLY, ON PURPOSE. The phone reads the same questions the PC has, in the
 * PC's own sections - the current values and the last accepted answers - and it
 * may ask the PC for the read-only plan (`POST /api/setup/plan` writes nothing
 * and raises no card), so the owner can see what their answers would change and
 * what each change costs: instant, one of the PC's own approval cards, or
 * blocked on this PC. It also reads the answered count and where the PC's own
 * card has got to ([progressWords]) - a reading of the card's state, never a
 * write to it: `POST /api/setup/progress` is deliberately not in this file,
 * because where the owner is in the card is the card's own state, and the
 * phone shows it and does not move it.
 *
 * IT NEVER APPLIES ANYTHING. `POST /api/setup/apply` is deliberately not in
 * this file: applying works through the changes one at a time, waits on each
 * existing card, and some of them (a loosening rule, offering a reading tool)
 * can only be changed from the PC. A phone button that posted it would either
 * fail halfway or sit for minutes behind cards it cannot answer. So the last
 * step stays on the PC, and this screen says so in plain words ([PLAIN_ONLY]).
 * `SetupQuestionnaireTest` reads this file back as text and fails if an apply
 * path, a `confirm` body or a progress write ever appears.
 *
 * Pure Kotlin, no Android types and no HTTP: `JarvisApi` sends the two reads,
 * `JarvisRuntime` holds them behind the link, and `SetupQuestionnairePlate`
 * draws them. Every question, choice, help line and sentence comes from the
 * PC; the copies below are only the words this app needs when an answer lacks
 * its own, the same shape [PromptCoach] uses.
 */
object SetupQuestionnaire {
    /** The reading, and the read-only plan. There is no apply or progress write here. */
    const val PATH = "/api/setup"
    const val PLAN_PATH = "/api/setup/plan"

    // This screen's own words. Every question, choice and section title is the PC's.
    const val HEADING = "Personalize Jarvis"
    const val TITLE = "Personalize Jarvis"
    const val KICKER =
        "Questions about how you want Jarvis to behave, in short sections. Every answer " +
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

    // Sections and the one progress line. The data is the PC's; only these
    // connecting words are this screen's own.
    const val ALL_SECTIONS = "All sections"
    const val NOT_FINISHED = "Not finished"
    const val FINISHED = "Finished"

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
        /** The PC's own `section` id. Empty on a PC from before sections existed. */
        val section: String = "",
    )

    /** One of the PC's sections, with the questions it holds in the PC's order. */
    data class Section(
        val id: String,
        val title: String,
        val questions: List<Question>,
    )

    /** Where the PC's own card is: the question it is showing, if it names one. */
    data class Progress(val section: String, val question: String)

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
        val sections: List<Section>,
        val answers: Map<String, List<String>>,
        val completedAt: Double?,
        val lastOutcomes: List<Outcome>,
        val cardWaitS: Int?,
        val about: String,
        val storage: String,
        /** The PC's question-set version, and the one the owner last finished. */
        val version: Int?,
        val completedVersion: Int?,
        /** How many questions the PC has an answer for, saved or drafted. */
        val answeredCount: Int?,
        val progress: Progress?,
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

    /** A 404/501 answer is an older backend - the same rule [PromptCoach] and
     *  [WebSearch] use. The route was added on 2026-10-20, so a PC from before
     *  that day has no setup questionnaire. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    /** `GET /api/setup`, as the small reading this screen draws. */
    fun parse(body: JsonObject?): View? {
        body ?: return null
        val available = body.flag("available") ?: true
        val questions = (body["questions"] as? JsonArray).orEmpty().mapNotNull { row ->
            question(row)
        }
        val declared = sectionTitles(body["sections"])
        return View(
            available = available,
            reason = if (available) {
                body.text("error") ?: ""
            } else {
                body.text("why") ?: UPDATE_WORDS
            },
            questions = questions,
            sections = groupSections(questions, declared),
            answers = answers(body["answers"]),
            completedAt = (body["completed_at"] as? JsonPrimitive)
                ?.takeIf { !it.isString }?.contentOrNull?.toDoubleOrNull(),
            lastOutcomes = (body["last_outcomes"] as? JsonArray).orEmpty()
                .mapNotNull { outcome(it) },
            cardWaitS = (body["card_wait_s"] as? JsonPrimitive)
                ?.takeIf { !it.isString }?.intOrNull,
            about = body.text("about") ?: "",
            storage = body.text("storage") ?: "",
            version = body.integer("version"),
            completedVersion = body.integer("completed_version"),
            answeredCount = body.integer("answered_count"),
            progress = inProgress(body["in_progress"]),
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
            section = body.text("section")?.trim().orEmpty(),
        )
    }

    /**
     * The PC's declared section titles, by id, in its own order. Three shapes
     * are read because the PC's own shape is the PC's to choose:
     * `[{"id": …, "title": …}]`, `[[id, title]]` and `{"id": "title"}`. A PC
     * that sends none simply has one unnamed group.
     */
    private fun sectionTitles(body: JsonElement?): Map<String, String> {
        val out = LinkedHashMap<String, String>()
        when (body) {
            is JsonArray -> for (row in body) {
                when (row) {
                    is JsonObject -> {
                        val id = row.text("id")?.trim().orEmpty()
                        if (id.isNotEmpty()) out[id] = row.text("title")?.trim().orEmpty()
                    }
                    is JsonArray -> {
                        val id = (row.getOrNull(0) as? JsonPrimitive)
                            ?.takeIf { it.isString }?.contentOrNull?.trim().orEmpty()
                        val title = (row.getOrNull(1) as? JsonPrimitive)
                            ?.takeIf { it.isString }?.contentOrNull?.trim().orEmpty()
                        if (id.isNotEmpty()) out[id] = title
                    }
                    else -> Unit
                }
            }
            is JsonObject -> for ((id, value) in body) {
                val key = id.trim()
                if (key.isEmpty()) continue
                out[key] = (value as? JsonPrimitive)?.takeIf { it.isString }
                    ?.contentOrNull?.trim().orEmpty()
            }
            else -> Unit
        }
        return out
    }

    /**
     * The questions split by the PC's `section` value, in the PC's own order: a
     * declared section stays where the PC declared it even while it holds no
     * question; a section the PC did not declare comes where its first question
     * does. A question with no section is ONE unnamed group, so a PC from
     * before sections existed draws exactly as it did then.
     */
    private fun groupSections(
        questions: List<Question>,
        declared: Map<String, String>,
    ): List<Section> {
        val groups = LinkedHashMap<String, MutableList<Question>>()
        for (id in declared.keys) groups[id] = mutableListOf()
        for (question in questions) {
            groups.getOrPut(question.section) { mutableListOf() }.add(question)
        }
        return groups.mapNotNull { (id, rows) ->
            if (rows.isEmpty()) null else Section(id, declared[id] ?: "", rows)
        }
    }

    /** `in_progress`, when the PC says where its card is. */
    private fun inProgress(body: JsonElement?): Progress? {
        val row = body as? JsonObject ?: return null
        val question = row.text("question")?.trim().orEmpty()
        val section = row.text("section")?.trim().orEmpty()
        if (question.isEmpty() && section.isEmpty()) return null
        return Progress(section = section, question = question)
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

    // -- Sections, and the one progress line (all readings) --------------------

    /** A section's word on a tab or a heading: the PC's title, else the id it sent. */
    fun sectionWords(section: Section): String =
        section.title.ifBlank { section.id }.ifBlank { ALL_SECTIONS }

    /** The 1-based place of the question the PC's card is on, or null when it says none. */
    fun questionNumber(view: View): Int? {
        val id = view.progress?.question.orEmpty()
        if (id.isEmpty()) return null
        val index = view.questions.indexOfFirst { it.id == id }
        return if (index >= 0) index + 1 else null
    }

    /**
     * Is the question set the PC has NOW finished? `completed_version` against
     * the PC's `version` is the truth while both are sent: a file completed
     * before the new questions (1 against 2) is NOT finished, which is the
     * same re-offer the desktop's card makes. A PC from before versions
     * existed sends neither, so its `completed_at` is the only sign it has.
     */
    fun finished(view: View): Boolean {
        val done = view.completedVersion
        val current = view.version
        return when {
            done != null && current != null -> done >= current
            // The PC names one of the two but not both: no version can be
            // compared, so this never claims "finished".
            done != null || current != null -> false
            else -> view.completedAt != null
        }
    }

    /**
     * The ONE read-only progress line: whether the PC's question set is
     * finished (and when), how many of its questions have an answer, and which
     * question its own card is on. Empty when the PC sends nothing to say - an
     * older backend - so this screen never invents a position or a count.
     */
    fun progressWords(view: View): String {
        val total = view.questions.size
        if (finished(view)) {
            val on = dateText(view.completedAt)
            return if (on != null) "$FINISHED $on." else "$FINISHED."
        }
        val at = questionNumber(view)
        val answered = view.answeredCount
        if (at == null && answered == null) return ""
        val head = if (answered != null && total > 0) {
            "$NOT_FINISHED - $answered of $total answered"
        } else {
            NOT_FINISHED
        }
        val where = if (at != null && total > 0) {
            "On the PC this is at question $at of $total."
        } else {
            ""
        }
        return if (where.isEmpty()) "$head." else "$head. $where"
    }

    /** Seconds since 1970 as "31 Oct 2026", or null when there is no time. */
    fun dateText(epochSeconds: Double?): String? {
        if (epochSeconds == null || !epochSeconds.isFinite() || epochSeconds <= 0) return null
        return runCatching {
            DateTimeFormatter.ofPattern("d MMM yyyy", Locale.ENGLISH)
                .format(Instant.ofEpochSecond(epochSeconds.toLong()).atZone(ZoneId.systemDefault()))
        }.getOrNull()
    }

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

/** A whole number, never a string that looks like one. */
private fun JsonObject.integer(key: String): Int? {
    val prim = this[key] as? JsonPrimitive ?: return null
    if (prim is JsonNull || prim.isString) return null
    return prim.intOrNull
}
