package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull

/**
 * The job list: work that outlives one chat turn - a task is a named job with
 * steps, one step runs per tick, and the list remembers where it got to
 * through a restart.
 *
 * `GET /api/tasks`, `POST /api/tasks/act` - backend/jarvis_tasks.py (the
 * module) and tasks.patch (the routes); docs/JARVIS-API.md section 118.
 *
 * **WHAT THIS CANNOT SHOW, ON PURPOSE.** The reply is counted only: ids,
 * states, kinds, step counts, tool names and whether a job needs the owner.
 * There is **no task title and no step text in it at all** - the same rule
 * `jarvis_task_control.status()` follows - so this screen has nothing private
 * in it to hide, and [Row] has no field for a title because there is nothing
 * to put in one. The readable feed stays on the PC's own window.
 *
 * **NOTHING HERE APPROVES ANYTHING.** Pause and Cancel stop something
 * unfinished. Resume puts a job back in the queue and Retry tries an
 * interrupted step again; either way every step still raises its own approval
 * card when its turn comes, through the same gate as any ordinary tool call.
 * There is no route here that could say yes to a card.
 *
 * Kept apart from the screen so the parsing, the four steers and the two
 * request bodies can be tested on the JVM without a running app
 * (TasksTest.kt), the way TaskControl and PcHelp are.
 */
object Tasks {

    const val PATH = "/api/tasks"
    const val ACT_PATH = "/api/tasks/act"
    const val INPUT_PATH = "/api/tasks/input"

    /** The label, word for word the desktop's ("Job list"). */
    const val HEADING = "Job list"

    const val INTRO = "Work that keeps going on your PC: a job runs one step at a time, " +
        "each step still asks you before it acts, and it carries on where it left off even " +
        "after a restart."

    const val UPDATE = "This PC's Jarvis does not have the job list yet. Update the backend " +
        "by running apply-patches.ps1, then try again."

    /** A 409 from /api/tasks/act: the job was not in the state the button assumed. */
    const val NOT_IN_THAT_STATE = "That job is not in that state any more - it may have " +
        "finished, or something else already steered it."

    /** The four steers, in the order the screen shows them. */
    val ACTS = listOf("pause", "resume", "cancel", "retry")

    /** The owner's words for each steer. */
    fun actWords(act: String): String = when (act) {
        "pause" -> "Pause"
        "resume" -> "Resume"
        "cancel" -> "Cancel"
        "retry" -> "Retry"
        else -> act
    }

    /** The words for a job's state, from the state the PC sent. */
    fun stateWords(state: String): String = when (state) {
        "queued" -> "waiting"
        "running" -> "running"
        "waiting_approval" -> "waiting on you"
        "waiting_input" -> "needs an answer"
        "paused" -> "paused"
        "scheduled" -> "scheduled"
        "blocked" -> "needs you"
        "succeeded" -> "done"
        "failed" -> "stopped"
        "cancelled" -> "cancelled"
        else -> state
    }

    /**
     * Which steers make sense for a job in this state.
     *
     * A job that is moving can be paused or cancelled; a paused one can be
     * resumed or cancelled; one that has stopped - blocked by an interrupted
     * step, failed or cancelled - can be retried. A finished job offers
     * nothing: there is nothing left to steer.
     */
    fun actsFor(state: String): List<String> = when (state) {
        "queued", "running", "waiting_approval", "waiting_input" -> listOf("pause", "cancel")
        "paused" -> listOf("resume", "cancel")
        "blocked", "failed", "cancelled" -> listOf("retry")
        else -> emptyList()
    }

    /** One job, as much of it as the PC will say. No title: it does not send one. */
    data class Row(
        val id: String,
        val state: String,
        val kind: String,
        val step: Int,
        val steps: Int,
        val attempts: Int,
        val tools: List<String>,
        val needsAttention: Boolean,
        /** The PC's own sentence about an interrupted step. Never the owner's words. */
        val question: String,
    ) {
        /** "step 2 of 3 - web_search, send_email", the shape of the work. */
        fun shape(): String {
            val where = if (steps > 0) "step ${step.coerceAtLeast(1)} of $steps" else "no steps"
            return if (tools.isEmpty()) where else "$where - ${tools.joinToString(", ")}"
        }
    }

    data class Answer(
        val waiting: Int,
        val running: Int,
        val blocked: Int,
        val stop: Boolean,
        val rows: List<Row>,
    ) {
        /** "2 waiting, 1 running, 1 needs you", or null when there are none. */
        fun headline(): String? {
            if (rows.isEmpty()) return null
            val bits = mutableListOf("$waiting waiting", "$running running")
            if (blocked > 0) bits.add("$blocked needs you")
            if (stop) bits.add("stopped")
            return bits.joinToString(", ")
        }
    }

    sealed interface Read {
        /** Nothing asked yet. The screen asks as soon as it opens. */
        data object NotAsked : Read
        data object Reading : Read
        data class Loaded(val answer: Answer) : Read
        /** 404 or 503: the PC's backend predates the job list. */
        data object OlderBackend : Read
        data class Failed(val reason: String) : Read
    }

    /** The PC's answer, or null when it is not a shape this screen can read. */
    fun parse(obj: JsonObject): Answer? {
        val array = obj["tasks"] as? JsonArray ?: return null
        val rows = array.mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val id = o.str("id") ?: return@mapNotNull null
            Row(
                id = id,
                state = o.str("state").orEmpty(),
                kind = o.str("kind").orEmpty(),
                step = o.int("step"),
                steps = o.int("steps"),
                attempts = o.int("attempts"),
                tools = o.strList("tools"),
                needsAttention = o.bool("needs_attention"),
                question = o.str("question").orEmpty(),
            )
        }
        return Answer(
            waiting = obj.int("waiting"),
            running = obj.int("running"),
            blocked = obj.int("blocked"),
            stop = obj.bool("stop"),
            rows = rows,
        )
    }

    fun readOf(result: ApiResult<JsonObject>): Read = when (result) {
        is ApiResult.Ok -> parse(result.value)?.let { Read.Loaded(it) }
            ?: Read.Failed("Your PC answered, but not in a shape this screen can read.")
        is ApiResult.Failed -> when (val e = result.error) {
            // "Not on this backend" and "no such route" mean the same thing
            // here: this PC has not had the job list installed yet.
            ApiError.NotFound, ApiError.NotAvailable -> Read.OlderBackend
            else -> Read.Failed(failureLine(e))
        }
    }

    /** The line under the list, or null when there is nothing to say. */
    fun readLine(read: Read): String? = when (read) {
        Read.NotAsked -> null
        Read.Reading -> "Reading…"
        is Read.Loaded -> null
        Read.OlderBackend -> UPDATE
        is Read.Failed -> read.reason
    }

    /** `{"id":...,"act":...}` for POST /api/tasks/act. */
    fun actBody(id: String, act: String): String =
        """{"id":${JarvisApi.quote(id)},"act":${JarvisApi.quote(act)}}"""

    /**
     * `{"id":...,"answer":...}` for POST /api/tasks/input, or null when the
     * answer is blank: an empty answer is not sent, the same rule
     * [NoteCapture.body] follows. This is the only request here that carries
     * the owner's own words, and it carries them into the job list, never out
     * of the PC.
     */
    fun inputBody(id: String, answer: String): String? {
        val text = answer.trim()
        if (text.isEmpty()) return null
        return """{"id":${JarvisApi.quote(id)},"answer":${JarvisApi.quote(text)}}"""
    }

    /**
     * What a failed steer means, where the generic wording would be wrong.
     * `null` means "use the generic sentence" - the same shape
     * [TaskControl.failure] uses, and for the same reason: a 409 from these
     * routes is not "already handled elsewhere".
     */
    fun failure(e: ApiError): String? = when (e) {
        ApiError.NotFound, ApiError.NotAvailable -> UPDATE
        ApiError.AlreadyHandled -> NOT_IN_THAT_STATE
        else -> null
    }

    /** Always a sentence for a failed steer: the two above, or the generic one. */
    fun actFailureLine(e: ApiError): String = failure(e) ?: PlainErrors.forApiError(e).text

    private fun failureLine(e: ApiError): String = when (e) {
        is ApiError.Unreachable, ApiError.BadToken, is ApiError.Server, is ApiError.Malformed ->
            PlainErrors.forApiError(e).text
        ApiError.NotFound, ApiError.NotAvailable -> UPDATE
        ApiError.AlreadyHandled -> NOT_IN_THAT_STATE
    }

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.int(key: String): Int =
        (this[key] as? JsonPrimitive)?.intOrNull ?: 0

    private fun JsonObject.bool(key: String): Boolean =
        (this[key] as? JsonPrimitive)?.booleanOrNull ?: false

    private fun JsonObject.strList(key: String): List<String> =
        (this[key] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }
            ?: emptyList()
}
