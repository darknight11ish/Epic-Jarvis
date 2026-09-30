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
 * saved unless the owner chooses Keep (questions go to a review deck on the
 * PC), nothing is learned and nothing leaves the PC: the whole quiz lives in
 * the PC's memory and ends on Finish, Stop, a PC restart or 60 minutes unused.
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
        "model on this PC. Nothing is saved unless you choose Keep, nothing is learned, and nothing leaves this PC."
    const val START = "Write questions"
    const val ANSWER = "Check my answer"
    const val GOT_IT = "Got it"
    const val PARTLY = "Partly"
    const val NOT_YET = "Not yet"
    const val GUESS = "Jarvis's guess"
    const val FINISH = "Finish"
    const val STOP = "Stop and forget this quiz"
    const val CLOSE = "Close"
    const val HIDDEN_TEXT = "(hidden)"
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
    // Word for word the desktop's line (src/quiz.js QUIZ_MISSING).
    const val MISSING = "Your PC's Jarvis does not have Quiz yet - run apply-patches.ps1 on the PC."
    const val TOO_OLD = MISSING
    const val UNREADABLE = "Your PC sent something this phone could not read."

    // ---- Review decks and Spanish practice (docs/QUIZ-DECKS-DESIGN.md, Slice contract C2-C5). ----
    const val MODE_TEXT = "text"
    const val MODE_SPANISH = "spanish"
    const val MODE_TEXT_LABEL = "Text"
    const val MODE_SPANISH_LABEL = "Spanish practice"
    const val LEVEL_HEADING = "Level (roughly)"
    const val EXERCISE_HEADING = "Exercise"
    const val TOPIC_LABEL = "Topic (optional)"
    const val SPANISH_HINT = "Paste Spanish text (optional)"
    const val EXAMPLE_LABEL = "Example sentence"
    const val ANSWER_PREFIX = "Answer: "
    const val ACCENT_ROW_LABEL = "Spanish letters"
    // Word for word the contract's line for a PC that sends no "mode" (C2).
    const val OLD_PC = "Your PC's Jarvis does not have Spanish practice yet - run apply-patches.ps1 on the PC."
    const val KEEP_OPEN = "Keep these questions"
    const val KEEP_DO = "Keep and finish"
    const val CANCEL = "Cancel"
    const val KEEP_HINT = "Type the answer in your own words"
    const val KEEP_HIDDEN = "Turn off Hide memory lists to keep questions"
    const val KEEPING = "Keeping…"
    const val NEW_DECK = Decks.NEW_DECK
    const val DECK_NAME = Decks.DECK_NAME
    const val CHOOSE_DECK = Decks.CHOOSE_DECK

    const val MAX_TOPIC = 60
    const val MAX_DECK_NAME = 60
    const val DEFAULT_LEVEL = "A2"
    const val DEFAULT_EXERCISE = "mixed"

    /** The six levels, in order (C2). The level is a request, not a measurement. */
    val LEVELS = listOf("A1", "A2", "B1", "B2", "C1", "C2")

    /** The exercise choices: the wire word and the label (C5), in the contract's order. */
    val EXERCISES = listOf(
        "translate" to "Translate",
        "blank" to "Fill the blank",
        "complete" to "Finish the sentence",
        "mixed" to "Mixed",
    )

    /** The nine accent buttons, in the contract's order (C2). */
    val ACCENTS = listOf("á", "é", "í", "ó", "ú", "ñ", "ü", "¿", "¡")

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

    /**
     * [markedBy] is "code" only when the PC says so; anything else (a missing
     * field included) reads as "model", so the honest "Jarvis's guess" label
     * fails toward being shown. [expected] and [keyLabel] are Spanish practice's.
     */
    data class Mark(
        val level: String,
        val comment: String,
        val passage: String,
        val markedBy: String = "model",
        val expected: String? = null,
        val keyLabel: String? = null,
        val service: String? = null,
    )

    data class Question(val n: Int, val kind: String, val prompt: String, val mark: Mark?)

    data class Session(
        val id: String,
        val title: String,
        val graderVerified: Boolean,
        val questions: List<Question>,
        val answered: Int,
        /** "text" or "spanish". */
        val mode: String = MODE_TEXT,
        /** False when the PC's reply had no "mode": an older PC (C2). */
        val modeKnown: Boolean = true,
        val level: String? = null,
        /** "text" (the owner's own Spanish) or "model" (the model wrote it); null in Text mode. */
        val keySource: String? = null,
        /** The backend's Spanish crisis-words notice; never a copy in this app. */
        val notice: String? = null,
        /** "youtube" for a quiz made from a video's captions (JARVIS-API 112); null otherwise. */
        val source: String? = null,
    )

    /** One card to keep: the question's number and the owner's own words for the back. */
    data class KeepCard(val n: Int, val answer: String)

    /** What `finish` answered: a summary (and how many were kept), or a crisis answer with the quiz still open. */
    data class Finished(val summary: Summary?, val kept: Int?, val crisis: String?, val quiz: Session?)

    /**
     * One answer's result: either a [mark], or (a crisis answer, JARVIS-API
     * 98.4) the PC's own help words in [crisis] and NO mark. The quiz is the
     * PC's view after the call; a crisis answer leaves its question unanswered.
     */
    data class Answer(val mark: Mark?, val crisis: String?, val quiz: Session)

    /** A run of the help message: its words, and whether they are bold (`**988**`). */
    data class Run(val text: String, val bold: Boolean)

    data class Summary(val gotIt: Int, val partly: Int, val notYet: Int, val again: List<Int>)

    /** What the PC answered a call, kept whole: the status and the JSON body, if any. */
    data class Reply(val code: Int, val body: JsonObject?)

    /** One call's outcome: [gone] is true when the PC no longer has this quiz. */
    data class Outcome<out T>(
        val ok: Boolean,
        val value: T?,
        val said: String,
        val gone: Boolean = false,
        /** The PC's error code, when it sent one. */
        val code: String? = null,
    )

    // ------------------------------------------------------------ parsing ----

    private fun mark(el: Any?): Mark? {
        val o = el as? JsonObject ?: return null
        val level = o.text("level") ?: return null
        if (level != "got_it" && level != "partly" && level != "not_yet") return null
        val markedBy = when (o.text("marked_by")) {
            "code" -> "code"
            "cloud" -> "cloud"
            else -> "model"
        }
        return Mark(
            level, o.text("comment").orEmpty(), o.text("passage").orEmpty(),
            markedBy = markedBy,
            expected = o.text("expected"),
            keyLabel = o.text("key_label"),
            service = o.text("service"),
        )
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
        val modeRaw = o.text("mode")
        val mode = if (modeRaw == MODE_SPANISH) MODE_SPANISH else MODE_TEXT
        return Session(
            id = id,
            title = o.text("title").orEmpty(),
            // Missing means "not verified": the label stays on (fail toward honesty).
            graderVerified = o.flag("grader_verified") == true,
            questions = qs,
            answered = answered,
            mode = mode,
            modeKnown = modeRaw != null,
            level = o.text("level")?.takeIf { it in LEVELS },
            keySource = o.text("key_source")?.takeIf { it == "text" || it == "model" },
            notice = if (mode == MODE_SPANISH) o.text("notice") else null,
            source = o.text("source")?.takeIf { it == "youtube" },
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

    /**
     * The result of an answer: a mark (`{"mark","quiz"}`) or a crisis answer
     * (`{"crisis":true,"message":"<the PC's words>","quiz"}`). A crisis flag
     * without words, or without a quiz, is unreadable (null) - the help
     * words are the PC's, never written on this phone.
     */
    fun parseAnswer(body: JsonObject): Answer? {
        if (body.flag("crisis") == true) {
            val words = body.text("message") ?: return null
            val q = parseQuiz(body) ?: return null
            return Answer(null, words, q)
        }
        val (m, q) = parseAnswered(body) ?: return null
        return Answer(m, null, q)
    }

    /**
     * The PC's help message as paragraphs of runs, so it can be drawn as text
     * only: `**bold**` becomes a bold run, a blank line a new paragraph.
     * Word for word the desktop's crisisParagraphs (src/quiz.js).
     */
    fun crisisParagraphs(message: String): List<List<Run>> =
        message.split(Regex("\\n{2,}")).map { it.trim() }.filter { it.isNotEmpty() }.map { para ->
            para.split("**").mapIndexed { i, t -> Run(t, i % 2 == 1) }.filter { it.text.isNotEmpty() }
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

    /** Spanish practice: the text is optional (blank means the model writes the sentences). */
    fun validSpanishText(text: String): Boolean = text.isBlank() || validText(text)

    /**
     * The body of `POST /api/quiz` in Spanish mode (C2): `mode`, `level`,
     * `exercise`, an optional `topic` (60 characters at most) and an optional
     * `text`. A level or exercise this phone does not know is not sent (the
     * PC then uses its default).
     */
    fun startSpanishBody(
        text: String,
        level: String,
        exercise: String,
        topic: String,
        count: Int = DEFAULT_COUNT,
    ): String = buildJsonObject {
        put("mode", MODE_SPANISH)
        if (level in LEVELS) put("level", level)
        if (EXERCISES.any { it.first == exercise }) put("exercise", exercise)
        val t = topic.trim().take(MAX_TOPIC).trim()
        if (t.isNotEmpty()) put("topic", t)
        if (text.isNotBlank()) put("text", text.trim())
        put("count", count)
    }.toString()

    /**
     * The body of `finish` with a `keep` (C2): only `n` and `answer` per card,
     * for an existing [deck] or (deck null) a [newDeck] name. Null when
     * nothing is ticked, a back is over 2,000 characters, or neither a deck
     * nor a usable new-deck name is given.
     */
    fun keepBody(deck: String?, newDeck: String?, cards: List<KeepCard>): String? {
        if (cards.isEmpty()) return null
        if (cards.any { it.answer.length > MAX_ANSWER }) return null
        if (cards.map { it.n }.distinct().size != cards.size) return null
        val name = newDeck?.trim().orEmpty()
        if (deck != null) {
            if (!Decks.validId(deck)) return null
        } else if (name.isEmpty() || name.length > MAX_DECK_NAME) {
            return null
        }
        return buildJsonObject {
            put("keep", buildJsonObject {
                if (deck != null) put("deck", deck) else {
                    put("deck", JsonNull)
                    put("new_deck", name)
                }
                put("cards", JsonArray(cards.map { c ->
                    buildJsonObject {
                        put("n", c.n)
                        put("answer", c.answer)
                    }
                }))
            })
        }.toString()
    }

    /** "Kept 3 questions" / "Kept 1 question" (C3). */
    fun keptLine(n: Int): String = if (n == 1) "Kept 1 question" else "Kept $n questions"

    /** "Level B1 (roughly)". */
    fun levelLine(level: String): String = "Level $level (roughly)"

    /** The heading over a passage: "Example sentence" when the model wrote it, else "From the text". */
    fun passageHeading(q: Session): String = if (q.keySource == "model") EXAMPLE_LABEL else PASSAGE_LABEL

    /**
     * [ch] typed into [text] at the selection [start]..[end] (either order):
     * the new text and where the cursor goes. Null when the box would go
     * over [max] characters, so nothing is cut silently.
     */
    fun insertAt(text: String, start: Int, end: Int, ch: String, max: Int = MAX_ANSWER): Pair<String, Int>? {
        val a = start.coerceIn(0, text.length)
        val b = end.coerceIn(0, text.length)
        val lo = minOf(a, b)
        val hi = maxOf(a, b)
        val next = text.substring(0, lo) + ch + text.substring(hi)
        if (next.length > max) return null
        return next to (lo + ch.length)
    }

    /** The new-deck name the Keep sheet starts with: the quiz title, trimmed to 60. */
    fun defaultDeckName(title: String): String = title.trim().take(MAX_DECK_NAME).trim()

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
        E_MODEL -> "The model on this PC did not answer. Nothing was changed - try again in a moment."
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
        Outcome(false, null, refusalSaid(reply, lead), gone = errorCode(reply) == E_NOT_FOUND, code = errorCode(reply))

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
    fun answeredSaid(reply: Reply): Outcome<Answer> {
        if (succeeded(reply)) {
            val a = reply.body?.let(::parseAnswer)
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

    /** The plain words for a Keep refusal whose body has no message of its own (C2's table). */
    fun keepMessageFor(code: String?): String? = when (code) {
        "nothing_to_keep" -> "Tick at least one question to keep."
        "bad_question" -> "One of those questions cannot be kept."
        "answer_empty" -> "One of those answers is empty."
        "answer_too_long" -> messageFor(E_ANSWER_LONG)
        "bad_deck_name" -> "Give the deck a name of 1 to 60 characters."
        "deck_not_found" -> "That deck is not there any more. Choose another."
        "duplicate_card" -> "One of those questions is already in that deck."
        "too_many_decks" -> "There are already 20 decks. Delete one first."
        "deck_full" -> "Your decks are full (1,000 cards). Delete some cards first."
        "deck_unavailable" -> "Study decks are not set up on your PC."
        E_NOT_FOUND -> messageFor(E_NOT_FOUND)
        else -> null
    }

    /**
     * Finishing WITH a keep (C2/C3). Success is a summary and the count kept, or
     * a crisis answer (`crisis: true`, the PC's own help words, nothing kept and
     * the quiz still open). A failure keeps the quiz open: the PC's own
     * `message` is shown word for word ("deck_unavailable" says which
     * thing is missing), with this table only when it sent none.
     */
    fun finishedKeepSaid(reply: Reply): Outcome<Finished> {
        if (succeeded(reply)) {
            val body = reply.body
            if (body?.flag("crisis") == true) {
                val words = body.text("message")
                val q = parseQuiz(body)
                return if (words != null && q != null) Outcome(true, Finished(null, null, words, q), "")
                else Outcome(false, null, "Not kept. $UNREADABLE")
            }
            val s = body?.let(::parseSummary)
            val kept = body?.num("kept")?.toInt()?.coerceAtLeast(0)
            return if (s != null) Outcome(true, Finished(s, kept, null, null), "")
            else Outcome(false, null, "Not kept. $UNREADABLE")
        }
        val code = errorCode(reply)
        val said = reply.body?.text("message")?.replaceFirstChar { it.uppercase() }
            ?: keepMessageFor(code)
            ?: refusalSaid(reply, "Not kept.")
        return Outcome(false, null, said, gone = code == E_NOT_FOUND, code = code)
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
        "apply" -> "Apply"
        "translate" -> "Translate"
        "blank" -> "Fill the blank"
        "complete" -> "Finish the sentence"
        else -> ""
    }

    /**
     * "Question 2 of 5 · 1 answered", or "All 5 answered" when nothing is left.
     * Word for word the desktop's progress line (src/quiz.js progressLine).
     */
    fun progressLine(q: Session?): String {
        if (q == null || q.questions.isEmpty()) return ""
        val total = q.questions.size
        val upNext = next(q) ?: return "All $total answered"
        val done = q.questions.count { it.mark != null }
        return "Question ${upNext.n} of $total · $done answered"
    }

    /** "2 Got it · 1 Partly · 0 Not yet": counts in words, never a percentage. */
    fun countsLine(s: Summary): String = "${s.gotIt} $GOT_IT · ${s.partly} $PARTLY · ${s.notYet} $NOT_YET"

    /**
     * One line of "Look at these again": "3. The question's words". A skipped
     * question is listed like any other; a question the phone no longer has
     * the words of (hidden) shows [HIDDEN_TEXT].
     */
    fun againLine(n: Int, questions: List<Question>, hidden: Boolean): String {
        val prompt = questions.firstOrNull { it.n == n }?.prompt
        return "$n. " + if (hidden || prompt.isNullOrEmpty()) HIDDEN_TEXT else prompt
    }

    /** The length the PC checks: the text after trimming. Never cut short here. */
    fun textLength(text: String): Int = text.trim().length

    /**
     * The count line under the paste box, word for word the desktop's
     * (src/quiz.js textCount): "0 / 20,000 characters · at least 200 needed",
     * or "... · too long" over the limit.
     */
    fun textNote(text: String): String {
        val n = textLength(text)
        val us = java.util.Locale.US
        var note = String.format(us, "%,d / %,d characters", n, MAX_TEXT)
        if (n < MIN_TEXT) note += " · at least $MIN_TEXT needed"
        else if (n > MAX_TEXT) note += " · too long"
        return note
    }

    /** The count line under the answer box ("12 / 2000 characters"), the desktop's words. */
    fun answerNote(answer: String): String = "${answer.length} / $MAX_ANSWER characters"

    /**
     * The words beside a mark: "Got it", plus " - Jarvis's guess" only when the
     * model marked it and the grader has not been measured on this PC. A mark
     * made by code (a Spanish fill-the-blank) never carries the label.
     */
    fun markLine(mark: Mark, verified: Boolean): String {
        val base = levelWords(mark.level)
        val cloud = if (mark.markedBy == "cloud" && !mark.service.isNullOrEmpty()) " · Marked by ${mark.service}" else ""
        val guess = if (verified || mark.markedBy == "code") "" else " - $GUESS"
        return base + cloud + guess
    }

    /** The quiz with every question's words and marks replaced, for while the lists are hidden. */
    fun hide(q: Session): Session = q.copy(
        title = "",
        questions = q.questions.map { it.copy(prompt = HIDDEN_TEXT, mark = it.mark?.copy(comment = "", passage = "", expected = null)) },
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
