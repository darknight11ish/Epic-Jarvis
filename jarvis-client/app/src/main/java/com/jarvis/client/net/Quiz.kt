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
 * "Quiz me on a text" (Slice A of docs/STUDY-FROM-TEXT-DESIGN.md, contract in
 * its section 11; backend `jarvis_quiz.py`).
 *
 * The owner pastes some text, the PC's local model writes a few questions
 * about it, the owner types an answer to each, one at a time, and the model
 * marks each answer against the passage the question came from. Nothing is
 * saved or learned and nothing leaves the PC: the whole quiz lives in the
 * PC's memory and ends on Finish, Stop, a PC restart or 60 minutes unused.
 * THIS PHONE KEEPS NOTHING EITHER: no file, no preference, no database -
 * the session is held in memory by [com.jarvis.client.JarvisRuntime] only.
 *
 * Answers are typed. A client must not do speech-to-text.
 *
 * The pasted text is outside text ([OUTSIDE_TEXT]): Jarvis never learns facts
 * from it. A mark is never a fact about the owner, and there is no streak,
 * no letter grade and no number shown as if it were exact.
 *
 * Everything here is pure (no Android, no network), so QuizTest.kt can run it.
 */
object Quiz {
    const val PATH = "/api/quiz"

    // ---- The shared words (docs/STUDY-FROM-TEXT-DESIGN.md section 11), word for word. ----
    const val TITLE = "Quiz me on a text"
    const val INTRO = "Paste some text and Jarvis writes a few questions about it. Your answers are marked by the " +
        "model on this PC. Nothing is saved or learned, and nothing leaves this PC."
    const val START = "Write questions"
    const val ANSWER = "Check my answer"
    const val GOT_IT = "Got it"
    const val PARTLY = "Partly"
    const val NOT_YET = "Not yet"
    const val GUESS = "Jarvis's guess"
    const val FINISH = "Finish"
    const val STOP = "Stop and forget this quiz"
    const val SUMMARY_TITLE = "Look at these again"
    const val SUMMARY_EMPTY = "Nothing to look at again."
    const val OUTSIDE_TEXT = "This text is treated as outside text: Jarvis never learns facts from it."

    // ---- This phone's own words. ----
    const val STARTING = "Writing questions…"
    const val CHECKING = "Checking…"
    const val PASTE_HINT = "Paste the text here"
    const val ANSWER_HINT = "Type your answer"
    const val PASSAGE_LABEL = "From the text"
    const val NEXT = "Next question"
    const val HIDDEN_TEXT = "(hidden)"
    const val MISSING = "Your PC's Jarvis does not have quizzes yet - run apply-patches.ps1 on the PC."
    const val TOO_OLD = "Not done. Your PC's Jarvis does not have quizzes yet - run apply-patches.ps1 on the PC."
    const val UNREADABLE = "Your PC sent something this phone could not read."

    const val MIN_TEXT = 200
    const val MAX_TEXT = 20000
    const val MAX_ANSWER = 2000
    const val MIN_COUNT = 1
    const val MAX_COUNT = 10
    const val DEFAULT_COUNT = 5

    /** What a plain-words message says for each contract error code (section 11). */
    const val E_TEXT_SHORT = "text_too_short"
    const val E_TEXT_LONG = "text_too_long"
    const val E_BAD_COUNT = "bad_count"
    const val E_TOO_MANY = "too_many_quizzes"
    const val E_NOT_FOUND = "not_found"
    const val E_BAD_QUESTION = "bad_question"
    const val E_ANSWERED = "already_answered"
    const val E_ANSWER_EMPTY = "answer_empty"
    const val E_ANSWER_LONG = "answer_too_long"
    const val E_MODEL = "model_unavailable"

    private val ID = Regex("^[A-Za-z0-9_-]{1,64}$")

    /** Whether [id] is safe to put in a URL path. */
    fun validId(id: String?): Boolean = id != null && ID.matches(id)

    data class Mark(val level: String, val comment: String, val passage: String)

    data class Question(val n: Int, val kind: String, val prompt: String, val mark: Mark?)

    data class Session(
        val id: String,
        val title: String,
        val graderVerified: Boolean,
        val questions: List<Question>,
        val answered: Int,
    )

    data class Summary(val gotIt: Int, val partly: Int, val notYet: Int, val again: List<Int>)

    /** What the PC answered a call, kept whole: the status and the JSON body, if any. */
    data class Reply(val code: Int, val body: JsonObject?)

    /** One call's outcome: [gone] is true when the PC no longer has this quiz. */
    data class Outcome<out T>(val ok: Boolean, val value: T?, val said: String, val gone: Boolean = false)

    // ------------------------------------------------------------ parsing ----

    private fun mark(el: Any?): Mark? {
        val o = el as? JsonObject ?: return null
        val level = o.text("level") ?: return null
        if (level != "got_it" && level != "partly" && level != "not_yet") return null
        return Mark(level, o.text("comment").orEmpty(), o.text("passage").orEmpty())
    }

    private fun question(el: Any?): Question? {
        val o = el as? JsonObject ?: return null
        val n = o.num("n")?.toInt()?.takeIf { it >= 1 } ?: return null
        val prompt = o.text("prompt") ?: return null
        return Question(n, o.text("kind").orEmpty(), prompt, mark(o["mark"]))
    }

    /** One quiz from its own object; null when it has no usable id or no question list. */
    fun session(o: JsonObject): Session? {
        val id = o.text("id")?.takeIf { validId(it) } ?: return null
        val list = o["questions"] as? JsonArray ?: return null
        val qs = list.mapNotNull { question(it) }.sortedBy { it.n }
        // "answered" is trusted only as far as it can be checked against the marks.
        val answered = o.num("answered")?.toInt()?.coerceIn(0, qs.size) ?: qs.count { it.mark != null }
        return Session(
            id = id,
            title = o.text("title").orEmpty(),
            // Missing means "not verified": the label stays on (fail toward honesty).
            graderVerified = o.flag("grader_verified") == true,
            questions = qs,
            answered = answered,
        )
    }

    /** `{"ok":true,"quiz":{...}}` -> the quiz. */
    fun parseQuiz(body: JsonObject): Session? = (body["quiz"] as? JsonObject)?.let(::session)

    /** `{"ok":true,"mark":{...},"quiz":{...}}` -> the mark and the quiz. Both are needed. */
    fun parseAnswered(body: JsonObject): Pair<Mark, Session>? {
        val m = mark(body["mark"]) ?: return null
        val q = parseQuiz(body) ?: return null
        return m to q
    }

    /** `{"ok":true,"summary":{...}}` -> the summary; "again" numbers are kept sorted and de-duplicated. */
    fun parseSummary(body: JsonObject): Summary? {
        val s = body["summary"] as? JsonObject ?: return null
        val counts = s["counts"] as? JsonObject ?: return null
        val again = (s["again"] as? JsonArray)
            ?.mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> p !is JsonNull && !p.isString }?.doubleOrNull?.toInt() }
            ?.filter { it >= 1 }?.distinct()?.sorted().orEmpty()
        return Summary(
            gotIt = counts.num("got_it")?.toInt()?.coerceAtLeast(0) ?: 0,
            partly = counts.num("partly")?.toInt()?.coerceAtLeast(0) ?: 0,
            notYet = counts.num("not_yet")?.toInt()?.coerceAtLeast(0) ?: 0,
            again = again,
        )
    }

    /** The first question with no mark yet, or null when all are answered. */
    fun next(q: Session?): Question? = q?.questions?.firstOrNull { it.mark == null }

    // ------------------------------------------------------------- bodies ----

    fun validText(text: String): Boolean = text.trim().length in MIN_TEXT..MAX_TEXT
    fun validAnswer(answer: String): Boolean = answer.trim().length in 1..MAX_ANSWER
    fun validCount(count: Int): Boolean = count in MIN_COUNT..MAX_COUNT

    /** The body of `POST /api/quiz`. */
    fun startBody(text: String, count: Int = DEFAULT_COUNT): String = buildJsonObject {
        put("text", text.trim())
        put("count", count)
    }.toString()

    /** The body of `POST /api/quiz/{id}/answer`. */
    fun answerBody(n: Int, answer: String): String = buildJsonObject {
        put("n", n)
        put("answer", answer.trim())
    }.toString()

    /** `finish` and `stop` take no body: a plain empty object. */
    const val EMPTY_BODY = "{}"

    // ------------------------------------------------------------ messages ----

    /** A read that failed because this PC has no quizzes: a 404 or a 501. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || (error is ApiError.Server && error.code == 501)

    /** The error code in a refusal body, if it has one. */
    fun errorCode(reply: Reply): String? = reply.body?.text("error")

    /** Plain words for each contract error code; null for a code this phone does not know. */
    fun messageFor(code: String?): String? = when (code) {
        E_TEXT_SHORT -> "That text is too short. Paste at least $MIN_TEXT characters."
        E_TEXT_LONG -> "That text is too long. Paste at most 20,000 characters."
        E_BAD_COUNT -> "Ask for between $MIN_COUNT and $MAX_COUNT questions."
        E_TOO_MANY -> "Three quizzes are already open on your PC. Stop one before starting another."
        E_NOT_FOUND -> "That quiz is not there any more. It ends after 60 minutes without use. Start a new one."
        E_BAD_QUESTION -> "That question is not part of this quiz."
        E_ANSWERED -> "You already answered that question."
        E_ANSWER_EMPTY -> "Type an answer first."
        E_ANSWER_LONG -> "That answer is too long. Keep it under 2,000 characters."
        E_MODEL -> "The AI model on your PC did not answer. Nothing was lost - try again in a moment."
        else -> null
    }

    /** The sentence for a refused or failed call, [lead] first ("Not started."). */
    fun refusalSaid(reply: Reply, lead: String): String {
        val code = errorCode(reply)
        messageFor(code)?.let { return it }
        return when {
            reply.code == 404 || reply.code == 501 -> TOO_OLD
            reply.code == 503 -> "$lead Your PC's Jarvis cannot do this right now."
            else -> {
                val own = reply.body?.text("message")
                "$lead " + (own?.replaceFirstChar { it.uppercase() } ?: "Your PC answered ${reply.code}.")
            }
        }
    }

    private fun succeeded(reply: Reply): Boolean =
        reply.code in 200..299 && reply.body?.flag("ok") != false

    private fun <T> failed(reply: Reply, lead: String): Outcome<T> =
        Outcome(false, null, refusalSaid(reply, lead), gone = errorCode(reply) == E_NOT_FOUND)

    /** Writing the questions. */
    fun startedSaid(reply: Reply): Outcome<Session> {
        if (succeeded(reply)) {
            val q = reply.body?.let(::parseQuiz)
            return if (q != null && q.questions.isNotEmpty()) Outcome(true, q, "")
            else Outcome(false, null, "Not started. $UNREADABLE")
        }
        return failed(reply, "Not started.")
    }

    /** Reading a quiz again. */
    fun readSaid(reply: Reply): Outcome<Session> {
        if (succeeded(reply)) {
            val q = reply.body?.let(::parseQuiz)
            return if (q != null) Outcome(true, q, "") else Outcome(false, null, "Not read. $UNREADABLE")
        }
        return failed(reply, "Not read.")
    }

    /** Checking one answer. */
    fun answeredSaid(reply: Reply): Outcome<Pair<Mark, Session>> {
        if (succeeded(reply)) {
            val a = reply.body?.let(::parseAnswered)
            return if (a != null) Outcome(true, a, "") else Outcome(false, null, "Not checked. $UNREADABLE")
        }
        return failed(reply, "Not checked.")
    }

    /** Finishing. */
    fun finishedSaid(reply: Reply): Outcome<Summary> {
        if (succeeded(reply)) {
            val s = reply.body?.let(::parseSummary)
            return if (s != null) Outcome(true, s, "") else Outcome(false, null, "Not finished. $UNREADABLE")
        }
        return failed(reply, "Not finished.")
    }

    /** Stopping: only "ok" matters. */
    fun stoppedSaid(reply: Reply): Outcome<Unit> {
        if (succeeded(reply)) return Outcome(true, Unit, "Stopped. Nothing was kept.")
        return failed(reply, "Not stopped.")
    }

    // ------------------------------------------------------------- display ----

    /** The mark's words for a level. */
    fun levelWords(level: String): String = when (level) {
        "got_it" -> GOT_IT
        "partly" -> PARTLY
        "not_yet" -> NOT_YET
        else -> ""
    }

    /** What kind of question, in plain words. */
    fun kindWords(kind: String): String = when (kind) {
        "recall" -> "Remember"
        "explain" -> "Explain why"
        "apply" -> "Apply it"
        else -> ""
    }

    /** "Question 2 of 5". */
    fun position(n: Int, total: Int): String = "Question $n of $total"

    /**
     * The words beside a mark: "Got it", plus " - Jarvis's guess" while the
     * grader has not been measured on this PC.
     */
    fun markLine(mark: Mark, verified: Boolean): String =
        levelWords(mark.level) + if (verified) "" else " - $GUESS"

    /** The quiz with every question's words and marks replaced, for while the lists are hidden. */
    fun hide(q: Session): Session = q.copy(
        title = "",
        questions = q.questions.map { it.copy(prompt = HIDDEN_TEXT, mark = it.mark?.copy(comment = "", passage = "")) },
    )

    // ------------------------------------------------------------- helpers ----

    private fun JsonObject.num(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.doubleOrNull
            ?.takeIf { it.isFinite() }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
