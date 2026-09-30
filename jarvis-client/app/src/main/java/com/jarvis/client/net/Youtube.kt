package com.jarvis.client.net

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.put

/**
 * "Quiz me on a YouTube video" (docs/STUDY-FROM-TEXT-DESIGN.md section 14,
 * docs/JARVIS-API.md section 112; backend `jarvis_youtube.py`).
 *
 * The owner pastes a YouTube link on the Quiz page. The PC raises ONE approval
 * card for that link (a risky approval, decided in the ordinary approval
 * screens - never here), and only after a yes fetches the video's CAPTION TEXT
 * (never the video or its sound), writes questions with the local model and
 * hands back an ordinary quiz marked as outside text. This phone polls the
 * request about every [POLL_SECONDS] seconds while it waits.
 *
 * THIS PHONE KEEPS NOTHING: the link is sent once, in the request body, and the
 * field is cleared the moment the card is raised. It is never in a URL, a
 * notification, a log, a saved draft or an error sentence. Every refusal and
 * failure sentence is the PC's own, shown as it came; this phone writes none of
 * its own for the YouTube part (the contract's one missing-feature line aside).
 *
 * Everything here is pure (no Android, no network), so YoutubeTest.kt can run it.
 */
object Youtube {
    const val PATH = "/api/youtube"
    const val QUIZ_PATH = "/api/youtube/quiz"

    // ---- The shared words (section 14 "Shared words"), word for word; YoutubeTest
    // ---- holds them to contract/youtube-cases.json, which the desktop reads too.
    const val TITLE = "Quiz me on a YouTube video"
    const val INTRO = "Paste a YouTube link and Jarvis reads the video's captions (the words shown as subtitles), " +
        "then quizzes you on them. It asks with a card first, every time."
    const val TERMS = "This breaks YouTube's terms and may be blocked. Only the caption text is fetched - " +
        "never the video or its sound. The link tells YouTube which video you are studying."
    const val OUTSIDE = "The captions are treated as outside text: Jarvis never learns facts from them. " +
        "Your answers are marked by the model on this PC."
    const val PLACEHOLDER = "Paste a YouTube video link"
    const val START = "Read the captions and write questions"
    const val CANCEL = "Cancel"
    const val LABEL = "From YouTube captions"
    const val MISSING = "Your PC's Jarvis does not have YouTube quizzes yet - run apply-patches.ps1 on the PC."

    // ---- This phone's own words (not in the contract's list). ----
    const val STARTING = "Asking…"
    const val CANCELLING = "Cancelling…"
    const val UNREADABLE = "Your PC sent something this phone could not read."
    const val WORDS_HIDDEN = "Words hidden. Tap Show and confirm it is you."

    // ---- The small rules. ----
    const val POLL_SECONDS = 2
    const val UNKNOWN_STATE_LIMIT_SECONDS = 180
    const val LINK_MAX = 300

    // ---- States (section 112.1). ----
    const val S_WAITING = "waiting"
    const val S_FETCHING = "fetching"
    const val S_WRITING = "writing"
    const val S_READY = "ready"

    /** How an app treats a request: [WAITING] also offers Cancel; [WORKING] keeps polling. */
    enum class Phase { WAITING, WORKING, READY, ENDED }

    /**
     * The phase of a state word. An unknown word is still WORKING (decode
     * leniently); [isKnown] tells the caller so it can stop after
     * [UNKNOWN_STATE_LIMIT_SECONDS] with the PC's last message.
     */
    fun phase(state: String?): Phase = when (state) {
        S_WAITING -> Phase.WAITING
        S_FETCHING, S_WRITING -> Phase.WORKING
        S_READY -> Phase.READY
        "denied", "timed_out", "withdrawn", "refused", "failed" -> Phase.ENDED
        else -> Phase.WORKING
    }

    fun isKnown(state: String?): Boolean = when (state) {
        S_WAITING, S_FETCHING, S_WRITING, S_READY, "denied", "timed_out", "withdrawn", "refused", "failed" -> true
        else -> false
    }

    /** Whether polling should go on for this phase. */
    fun keepPolling(p: Phase): Boolean = p == Phase.WAITING || p == Phase.WORKING

    /**
     * Whether to stop polling a state this phone does not know: true once it
     * has been seen for [UNKNOWN_STATE_LIMIT_SECONDS]. [sinceMs] is when it was
     * first seen (null when the state is known or was not seen yet).
     */
    fun giveUpOnUnknown(sinceMs: Long?, nowMs: Long): Boolean =
        sinceMs != null && nowMs - sinceMs >= UNKNOWN_STATE_LIMIT_SECONDS * 1000L

    private val ID = Regex("^[A-Za-z0-9_-]{1,64}$")

    /** Whether [id] is safe to put in a URL path. */
    fun validId(id: String?): Boolean = id != null && ID.matches(id)

    /**
     * One request as the PC describes it. [link] is the canonical address the
     * card shows: it may be drawn while the lists are not hidden, and only
     * for the moments a request is open; never kept, never logged.
     */
    data class Request(
        val id: String,
        val state: String,
        val message: String,
        val link: String?,
        val truncated: Boolean,
        val minutes: Int?,
        val error: String?,
        val quiz: Quiz.Session?,
    ) {
        val phase: Phase get() = phase(state)
    }

    /** `GET /api/youtube`: whether the feature is there, and the newest request. */
    data class Info(val available: Boolean, val linkMax: Int, val latest: Request?)

    /** One call's outcome: [request] on success, else the sentence to show. */
    data class Outcome(
        val ok: Boolean,
        val request: Request?,
        val said: String,
        /** The PC's error code, when it sent one. */
        val code: String? = null,
        /** True when the PC no longer has this request. */
        val gone: Boolean = false,
    )

    // ------------------------------------------------------------ parsing ----

    /**
     * A request from its own object; null when it has no usable id or state.
     * Unknown keys are ignored. A `quiz` that cannot be read leaves [Request.quiz] null.
     */
    fun request(o: JsonObject): Request? {
        val id = o.text("id")?.takeIf { validId(it) } ?: return null
        val state = o.text("state") ?: return null
        return Request(
            id = id,
            state = state,
            message = o.text("message").orEmpty(),
            link = o.text("link"),
            truncated = o.flag("truncated") == true,
            minutes = o.num("minutes")?.toInt()?.takeIf { it >= 1 },
            error = o.text("error"),
            quiz = (o["quiz"] as? JsonObject)?.let(Quiz::session),
        )
    }

    /** `{"ok":true,"request":{...}}` -> the request. */
    fun parseRequest(body: JsonObject): Request? = (body["request"] as? JsonObject)?.let(::request)

    /** `GET /api/youtube` -> the feature's presence, the link limit and the newest request. */
    fun parseInfo(body: JsonObject): Info? {
        val available = body.flag("available") ?: return null
        val limit = ((body["limits"] as? JsonObject)?.num("link")?.toInt())?.takeIf { it in 1..10000 } ?: LINK_MAX
        return Info(available, limit, (body["latest"] as? JsonObject)?.let(::request))
    }

    // ------------------------------------------------------------- bodies ----

    /** Whether the field holds something to send. The phone does not judge the link itself. */
    fun canStart(link: String): Boolean = link.trim().isNotEmpty()

    /** The body of `POST /api/youtube/quiz`: only the link and the question count. */
    fun startBody(link: String, count: Int = Quiz.DEFAULT_COUNT): String = buildJsonObject {
        put("url", link.trim())
        put("count", count)
    }.toString()

    /** `cancel` takes a plain empty object. */
    const val EMPTY_BODY = "{}"

    // ------------------------------------------------------------ messages ----

    /** A read of `GET /api/youtube` that failed because this PC does not have the feature. */
    fun missing(reply: Quiz.Reply): Boolean = reply.code == 404 || reply.code == 501 || reply.code == 503

    private fun succeeded(reply: Quiz.Reply): Boolean =
        reply.code in 200..299 && reply.body?.flag("ok") != false

    /**
     * The sentence for a refused call: the PC's own `message`, word for word,
     * never rewritten (the contract: an app shows it as it came). Only a body with no
     * message of its own gets a generic sentence, and none of them names the link.
     */
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
        return Outcome(false, null, refusalSaid(reply, lead), code = code, gone = code == "not_found")
    }

    /**
     * What to show for a request: the PC's message, and if it has none its
     * state's reference words (an end state must never be blank).
     */
    fun shown(r: Request): String = r.message.ifEmpty { STATE_FALLBACK[r.state].orEmpty() }

    private val STATE_FALLBACK = mapOf(
        S_WAITING to "Waiting for your yes on the approval card.",
        S_FETCHING to "Reading the captions from YouTube...",
        S_WRITING to "Writing the questions...",
        S_READY to "Ready.",
        "denied" to "You said no, so nothing was fetched.",
        "timed_out" to "Nobody answered the card in time, so nothing was fetched.",
        "withdrawn" to "You cancelled before the card was answered, so nothing was fetched.",
        "refused" to "The card could not be answered, so nothing was fetched.",
        "failed" to "Could not make a quiz from that video.",
    )

    /** Any call that answers with a request (start, read, cancel). */
    fun requestSaid(reply: Quiz.Reply, lead: String): Outcome {
        if (succeeded(reply)) {
            val r = reply.body?.let(::parseRequest)
            if (r == null) return Outcome(false, null, "$lead $UNREADABLE")
            // A "ready" with no readable quiz is not a quiz: say so rather than open nothing.
            if (r.phase == Phase.READY && (r.quiz == null || r.quiz.questions.isEmpty())) {
                return Outcome(false, r, "$lead $UNREADABLE")
            }
            return Outcome(true, r, shown(r))
        }
        return failed(reply, lead)
    }

    fun startedSaid(reply: Quiz.Reply): Outcome = requestSaid(reply, "Not started.")
    fun readSaid(reply: Quiz.Reply): Outcome = requestSaid(reply, "Not read.")
    fun cancelledSaid(reply: Quiz.Reply): Outcome = requestSaid(reply, "Not cancelled.")

    // ------------------------------------------------------------- display ----

    /**
     * The line above the questions of a quiz that came from captions and covers
     * only the first part: the PC's own message, or null when the whole video
     * was covered.
     */
    fun truncatedNote(r: Request): String? = if (r.truncated) shown(r) else null

    /** Whether a quiz came from YouTube captions (it carries `source: "youtube"`). */
    fun fromCaptions(q: Quiz.Session?): Boolean = q?.source == "youtube"

    // ------------------------------------------------------------- helpers ----

    private fun JsonObject.num(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.doubleOrNull
            ?.takeIf { it.isFinite() }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
