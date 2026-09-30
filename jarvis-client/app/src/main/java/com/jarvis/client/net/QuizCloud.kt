package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.put

/**
 * "Grade this better" (docs/STUDY-FROM-TEXT-DESIGN.md section 15,
 * docs/JARVIS-API.md section 113; backend `jarvis_quiz_cloud.py`).
 *
 * Sends ONE text quiz to a cloud AI service to be marked more carefully than
 * the model on this PC can. It asks with an approval card first, every time,
 * listing exactly what would leave this PC.
 *
 * THIS PHONE KEEPS NOTHING: no key, no answer, no text leaves this phone other
 * than via the PC's own routes.
 */
object QuizCloud {
    const val PATH = "/api/quiz-cloud"
    const val GRADE_PATH = "/api/quiz-cloud/grade"

    // ---- Shared words (section 15) ----
    const val BUTTON = "Grade this better"
    const val TITLE = "Grade this better"
    const val INTRO = "Send this quiz to a cloud AI service that marks it more carefully than the model on " +
        "this PC. It asks with a card first, every time, and the card lists exactly what " +
        "would leave this PC."
    const val LEAVES = "This sends your questions, your answers and the passages to an outside company. It " +
        "costs a little money and is kept under that company's own terms. Nothing private " +
        "is ever sent."
    const val CANCEL = "Cancel"
    const val MARK_LABEL_PREFIX = "Marked by "
    const val MISSING = "Your PC's Jarvis does not have cloud quiz grading yet - run apply-patches.ps1 on the PC."

    // ---- Phone's own words ----
    const val STARTING = "Asking…"
    const val CANCELLING = "Cancelling…"
    const val UNREADABLE = "Your PC sent something this phone could not read."

    // ---- Small rules ----
    const val POLL_SECONDS = 2
    const val UNKNOWN_STATE_LIMIT_SECONDS = 180
    const val PAYLOAD_MAX = 60000

    // ---- States ----
    const val S_WAITING = "waiting"
    const val S_SENDING = "sending"
    const val S_READY = "ready"

    enum class Phase { WAITING, WORKING, READY, ENDED }

    fun phase(state: String?): Phase = when (state) {
        S_WAITING -> Phase.WAITING
        S_SENDING -> Phase.WORKING
        S_READY -> Phase.READY
        "denied", "timed_out", "withdrawn", "refused", "failed" -> Phase.ENDED
        else -> Phase.WORKING
    }

    fun isKnown(state: String?): Boolean = when (state) {
        S_WAITING, S_SENDING, S_READY, "denied", "timed_out", "withdrawn", "refused", "failed" -> true
        else -> false
    }

    fun keepPolling(p: Phase): Boolean = p == Phase.WAITING || p == Phase.WORKING

    fun giveUpOnUnknown(sinceMs: Long?, nowMs: Long): Boolean =
        sinceMs != null && nowMs - sinceMs >= UNKNOWN_STATE_LIMIT_SECONDS * 1000L

    private val ID = Regex("^[A-Za-z0-9_-]{1,64}$")

    fun validId(id: String?): Boolean = id != null && ID.matches(id)

    data class Service(
        val id: String,
        val short: String,
        val name: String,
        val host: String,
        val model: String,
        val ready: Boolean,
        val why: String,
        val money: String,
    )

    data class Request(
        val id: String,
        val state: String,
        val message: String,
        val quizId: String,
        val service: String,
        val host: String,
        val model: String,
        val chars: Int,
        val cost: String?,
        val error: String?,
        val quiz: Quiz.Session?,
    ) {
        val phase: Phase get() = phase(state)
    }

    data class Info(
        val available: Boolean,
        val ready: Boolean,
        val cheapest: String?,
        val services: List<Service>,
        val latest: Request?,
    )

    data class Outcome(
        val ok: Boolean,
        val request: Request?,
        val said: String,
        val code: String? = null,
        val gone: Boolean = false,
    )

    // ------------------------------------------------------------ parsing ----

    fun service(o: JsonObject): Service = Service(
        id = o.text("id").orEmpty(),
        short = o.text("short").orEmpty(),
        name = o.text("name").orEmpty(),
        host = o.text("host").orEmpty(),
        model = o.text("model").orEmpty(),
        ready = o.flag("ready") == true,
        why = o.text("why").orEmpty(),
        money = o.text("money").orEmpty(),
    )

    fun request(o: JsonObject): Request? {
        val id = o.text("id")?.takeIf { validId(it) } ?: return null
        val state = o.text("state") ?: return null
        return Request(
            id = id,
            state = state,
            message = o.text("message").orEmpty(),
            quizId = o.text("quiz_id").orEmpty(),
            service = o.text("service").orEmpty(),
            host = o.text("host").orEmpty(),
            model = o.text("model").orEmpty(),
            chars = o.num("chars")?.toInt() ?: 0,
            cost = o.text("cost"),
            error = o.text("error"),
            quiz = (o["quiz"] as? JsonObject)?.let(Quiz::session),
        )
    }

    fun parseRequest(body: JsonObject): Request? = (body["request"] as? JsonObject)?.let(::request)

    fun parseInfo(body: JsonObject): Info? {
        val available = body.flag("available") ?: return null
        val ready = body.flag("ready") == true
        val cheapest = body.text("cheapest")
        val services = (body["services"] as? JsonArray)?.mapNotNull { (it as? JsonObject)?.let(::service) }.orEmpty()
        return Info(available, ready, cheapest, services, (body["latest"] as? JsonObject)?.let(::request))
    }

    fun gradeBody(quizId: String): String = buildJsonObject {
        put("quiz_id", quizId.trim())
    }.toString()

    const val EMPTY_BODY = "{}"

    fun missing(reply: Quiz.Reply): Boolean = reply.code == 404 || reply.code == 501 || reply.code == 503

    private fun succeeded(reply: Quiz.Reply): Boolean =
        reply.code in 200..299 && reply.body?.flag("ok") != false

    fun refusalSaid(reply: Quiz.Reply, lead: String): String {
        val own = reply.body?.text("message")
        if (own != null) return own
        return when (reply.code) {
            404, 501 -> MISSING
            503 -> "$lead Your PC's Jarvis cannot do this right now."
            else -> "$lead Your PC answered ${reply.code}."
        }
    }

    private fun failed(reply: Quiz.Reply, lead: String): Outcome {
        val code = reply.body?.text("error")
        return Outcome(false, null, refusalSaid(reply, lead), code = code, gone = code == "request_not_found")
    }

    fun shown(r: Request): String = r.message.ifEmpty { STATE_FALLBACK[r.state].orEmpty() }

    private val STATE_FALLBACK = mapOf(
        S_WAITING to "Waiting for your yes on the approval card.",
        S_SENDING to "Sending the quiz to be marked...",
        S_READY to "Ready.",
        "denied" to "You said no, so nothing was sent.",
        "timed_out" to "Nobody answered the card in time, so nothing was sent.",
        "withdrawn" to "You cancelled before the card was answered, so nothing was sent.",
        "refused" to "The card could not be answered, so nothing was sent.",
        "failed" to "The quiz could not be marked by the cloud service. Your marks were not changed.",
    )

    fun requestSaid(reply: Quiz.Reply, lead: String): Outcome {
        if (succeeded(reply)) {
            val r = reply.body?.let(::parseRequest) ?: return Outcome(false, null, "$lead $UNREADABLE")
            return Outcome(true, r, shown(r))
        }
        return failed(reply, lead)
    }

    // ------------------------------------------------------------- helpers ----

    private fun JsonObject.num(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.doubleOrNull
            ?.takeIf { it.isFinite() }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
