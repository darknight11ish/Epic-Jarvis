package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull

/*
 * The phone's half of the 2026-09-23 learning work - the pure rules only,
 * kept apart from Compose and OkHttp so the JVM unit tests can reach them.
 *
 *  - "That was right / that was wrong" on an answer (`feedback.patch`,
 *    items 1 and 8 of docs/LEARNING-RESEARCH-2026-09-23.md).
 *  - What a memory review card says and which answers it offers
 *    (`memory-intake.patch` items 2, 5 and 9, and feedback's
 *    "stop using this fact?" card).
 *
 * backend/README.md and docs/JARVIS-API.md are the contract. Every field
 * name below was read from `backend/jarvis_feedback.py`,
 * `backend/feedback.patch`, `backend/memory-intake.patch` and
 * `backend/jarvis_intake.py`, not guessed.
 */

/** The owner's mark on ONE answer. `wire` is exactly what the backend accepts. */
enum class AnswerMark(val wire: String) {
    RIGHT("right"),
    WRONG("wrong"),

    /** No mark, or a mark taken back. The backend supports sending this. */
    NONE("none"),
}

/**
 * What the answer's mark buttons show. Null on Home means "no buttons at
 * all": the answer carried no `turn_id` (an older backend, or recording
 * failed), so there is nothing the desktop could file a mark against.
 */
data class AnswerFeedback(
    /** The answer these buttons belong to. The tap sends THIS id, not whatever is newest. */
    val turnId: String,
    val mark: AnswerMark = AnswerMark.NONE,
    /** A mark is on its way to the desktop. Both buttons wait for it. */
    val busy: Boolean = false,
    /**
     * The desktop said it cannot take marks for this answer (the feedback
     * module is missing, or it does not know this answer). The buttons are
     * replaced by one quiet line rather than an error.
     */
    val unavailable: Boolean = false,
)

/** The runtime's record of the mark on one answer, keyed by that answer's id. */
data class AnswerMarkState(
    val turnId: String,
    val mark: AnswerMark = AnswerMark.NONE,
    val busy: Boolean = false,
    val unavailable: Boolean = false,
)

object Feedback {
    /** The response header an answer's id rides out in (`feedback.patch`). */
    const val ROUTE_HEADER = "X-Jarvis-Route"

    const val MARK_PATH = "/api/feedback/mark"

    /** `uuid.uuid4().hex` - the backend refuses anything else (`jarvis_feedback._TURN`). */
    private val TURN_ID = Regex("^[0-9a-f]{32}$")

    fun isTurnId(s: String?): Boolean = s != null && TURN_ID.matches(s)

    /**
     * The answer's `turn_id` from its `X-Jarvis-Route` header, or null.
     *
     * The header is a JSON object (`degrade-filter.patch` builds it with
     * `json.dumps`). Null for a missing header, one that is not an object, a
     * missing or non-string `turn_id`, or one that is not exactly 32
     * lowercase hex characters - the backend would refuse to mark it, so a
     * button for it would only ever fail.
     */
    fun turnIdFromRouteHeader(header: String?): String? {
        if (header.isNullOrBlank()) return null
        val obj = runCatching { JarvisJson.parseToJsonElement(header.trim()) as? JsonObject }
            .getOrNull() ?: return null
        val prim = obj["turn_id"] as? JsonPrimitive ?: return null
        if (prim is JsonNull || !prim.isString) return null
        return prim.content.takeIf { isTurnId(it) }
    }

    /**
     * The body for `POST /api/feedback/mark`: one id, one mark. There is no
     * list form on purpose - the backend refuses one, and a "mark all" would
     * move every counter at once on one tap. Null for an id the backend
     * would refuse anyway, so nothing is sent.
     */
    fun markBody(turnId: String, mark: AnswerMark): String? {
        if (!isTurnId(turnId)) return null
        return """{"turn_id":"$turnId","mark":"${mark.wire}"}"""
    }

    /**
     * What a tap sends. Tapping the mark already chosen takes it back
     * ("none"); tapping the other one replaces it. One mark per answer,
     * always changeable.
     */
    fun nextMark(current: AnswerMark, tapped: AnswerMark): AnswerMark =
        if (tapped == AnswerMark.NONE || tapped == current) AnswerMark.NONE else tapped

    /**
     * What Home shows for the answer whose id is [turnId], given the
     * runtime's [state]. Null - no buttons - when the answer has no id. A
     * state recorded for a DIFFERENT answer is ignored, so an old mark is
     * never shown beside a new answer.
     */
    fun viewFor(turnId: String?, state: AnswerMarkState?): AnswerFeedback? {
        if (turnId == null || !isTurnId(turnId)) return null
        val mine = state?.takeIf { it.turnId == turnId } ?: return AnswerFeedback(turnId)
        return AnswerFeedback(turnId, mark = mine.mark, busy = mine.busy, unavailable = mine.unavailable)
    }
}

/** Which of the three kinds of review card a row is. */
enum class MemoryCardKind {
    /** Something new to remember. Keep or Discard. */
    NEW_FACT,

    /** A new fact that would replace (retire) an old one. */
    CORRECTION,

    /**
     * "Stop using this fact?" - raised by `jarvis_feedback` when a fact keeps
     * turning up in answers marked wrong. ACCEPTING it retires the fact;
     * discarding it keeps the fact. So its buttons must never read Keep /
     * Discard, which would say the opposite of what they do.
     */
    RETIRE,
}

/** One memory review card, worked out from one `/api/memory/pending` row. */
data class MemoryCardView(
    /** The PROPOSAL id. Null: the card can be shown but not answered. */
    val id: Long?,
    val kind: MemoryCardKind,
    /** The fact the card is about: the new fact, or, on a RETIRE card, the fact in question. */
    val fact: String,
    /** CORRECTION: the old fact that Keep would retire. */
    val replaces: String?,
    /** RETIRE: the backend's own sentence on why it is asking. */
    val reason: String?,
    /** The label on the button that sends `accept: true`. */
    val acceptLabel: String,
    /** The label on the button that sends `accept: false`. */
    val discardLabel: String,
    /** One plain line under the buttons about what they do, or null. */
    val explainer: String?,
    /** Offer the third answer, "Both are true" (`POST /api/memory/keep_both`). */
    val bothAreTrue: Boolean,
    /** Planted-instruction warnings, one plain sentence each. Empty: none. */
    val warnings: List<String>,
    /**
     * False when the backend said it could NOT run the planted-instruction
     * check - not the same as "clean". Null when the backend does not report
     * it at all (a backend without memory-intake), which says nothing.
     */
    val checked: Boolean?,
    /** The owner's own words from a "Remember:" message. */
    val ownWords: Boolean,
    /** Where it came from, for the small "from ..." line, or null to show none. */
    val sourceLine: String?,
)

object MemoryCards {
    /** `jarvis_extract.RETIRE_SOURCE`. */
    const val RETIRE_SOURCE = "feedback_retire"

    /** `source` of a card queued from a "Remember:" message. */
    const val REMEMBER_SOURCE = "remember"

    /**
     * The review queue, asking for "stop using this fact?" cards too.
     *
     * The backend hides those cards from any client that does not ask with
     * `retire_cards=1` (exactly "1"), so an app still labelling every card
     * Keep / Discard can never retire a fact with a button that says Keep.
     * This app labels them for what they do - see [from] - so it asks.
     */
    const val PENDING_PATH = "/api/memory/pending?retire_cards=1"

    const val KEEP_BOTH_PATH = "/api/memory/keep_both"

    /** The heading on a RETIRE card, and the start of the backend's own reason text. */
    const val RETIRE_QUESTION = "Stop using this fact?"
    const val RETIRE_ACCEPT = "Stop using this fact"
    const val RETIRE_DISCARD = "Keep using it"
    const val RETIRE_EXPLAINER =
        "Stopping it does not delete it. The fact stays in the history - Jarvis just stops using it."
    const val BOTH_ARE_TRUE = "Both are true"
    const val CORRECTION_EXPLAINER =
        "Keep swaps the old fact for this one. The old one stays in the history."
    const val CORRECTION_EXPLAINER_BOTH =
        "Keep swaps the old fact for this one. Both are true keeps both."
    const val PLANTED_HEADLINE =
        "Careful: this may be an instruction someone slipped in, not a fact about you."
    const val PLANTED_ADVICE = "If you did not say this, discard it."
    const val NOT_CHECKED =
        "Jarvis could not check this card for slipped-in instructions."

    /** `{"id": <proposal id>}` - one id, one decision, like /api/memory/decide. */
    fun keepBothBody(id: Long): String = """{"id":$id}"""

    fun from(row: JsonObject): MemoryCardView {
        val id = row.str("id")?.toLongOrNull()
        val source = row.str("source")
        val text = row.str("text")
        // A card is a correction only when it names the stored fact it would
        // retire BY ID. `replaces` alone is the model's own description of
        // that fact, and `jarvis_extract._accept()` retires only by the id
        // recorded when the card was queued - so a card with words but no id
        // retires nothing, and must not claim it would.
        val replacesText = row.str("replaces_text") ?: row.str("replaces")
        val hasTarget = row.str("replaces_id")?.let { it != "0" } == true
        val kind = when {
            source == RETIRE_SOURCE -> MemoryCardKind.RETIRE
            hasTarget -> MemoryCardKind.CORRECTION
            else -> MemoryCardKind.NEW_FACT
        }
        // Belt and braces: the backend already sends keep_both_ok=false on a
        // retire card (test_learning_integration.py), and refuses the route
        // for one with a 409. The phone refuses to OFFER it as well, and
        // offers it only on a card it can actually answer.
        val bothOk = row.bool("keep_both_ok") == true &&
            kind == MemoryCardKind.CORRECTION && id != null
        val warnings = (row["flags"] as? JsonArray).orEmpty().mapNotNull { el ->
            when (el) {
                is JsonObject -> el.str("why") ?: el.str("code")?.let { "Flagged: $it" }
                is JsonPrimitive -> el.takeIf { it !is JsonNull }?.content?.takeIf { it.isNotBlank() }
                else -> null
            }
        }.distinct()
        val ownWords = row.bool("verbatim") == true || source == REMEMBER_SOURCE
        return when (kind) {
            MemoryCardKind.RETIRE -> MemoryCardView(
                id = id,
                kind = kind,
                fact = replacesText ?: "(the desktop did not say which fact)",
                replaces = null,
                // The card is headed "Stop using this fact?" already, so the
                // backend's sentence loses its own copy of that question.
                reason = text?.removePrefix(RETIRE_QUESTION)?.trim()?.takeIf { it.isNotEmpty() },
                acceptLabel = RETIRE_ACCEPT,
                discardLabel = RETIRE_DISCARD,
                explainer = RETIRE_EXPLAINER,
                bothAreTrue = false,
                warnings = warnings,
                checked = row.bool("flags_checked"),
                ownWords = false,
                sourceLine = null,
            )
            else -> MemoryCardView(
                id = id,
                kind = kind,
                fact = text ?: "(no text)",
                replaces = if (kind == MemoryCardKind.CORRECTION) {
                    replacesText ?: "(the desktop did not say which fact)"
                } else {
                    null
                },
                reason = null,
                acceptLabel = "Keep",
                discardLabel = "Discard",
                explainer = when {
                    kind != MemoryCardKind.CORRECTION -> null
                    bothOk -> CORRECTION_EXPLAINER_BOTH
                    else -> CORRECTION_EXPLAINER
                },
                bothAreTrue = bothOk,
                warnings = warnings,
                checked = row.bool("flags_checked"),
                ownWords = ownWords,
                // "your own words" says it better than "from remember".
                sourceLine = source?.takeIf { !ownWords }?.let { "from ${it.replace('_', ' ')}" },
            )
        }
    }

    /**
     * Plain lines from the queue's `setup` block worth showing under the
     * cards: why the last "Remember:" was NOT queued (a queued one is already
     * a card, labelled "your own words"), and how many repeat cards were
     * dropped. Both sentences are the backend's own, shown as they are.
     */
    fun setupNotes(payload: JsonObject?): List<String> {
        val setup = payload?.get("setup") as? JsonObject ?: return emptyList()
        val out = mutableListOf<String>()
        (setup["remember_last"] as? JsonObject)?.let { last ->
            val note = last.str("note")
            if (note != null && last.bool("queued") == false) {
                out += "Your last \"Remember:\" message: $note"
            }
        }
        setup.str("near_duplicates_note")?.let { out += it }
        return out
    }

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content?.takeIf { it.isNotBlank() }

    private fun JsonObject.bool(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.booleanOrNull
}
