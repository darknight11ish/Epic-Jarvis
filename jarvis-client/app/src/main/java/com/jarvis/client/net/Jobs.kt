package com.jarvis.client.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * Long Fuse's way IN and way OUT on the phone (2026-10-30): start ONE
 * background job from the owner's own words, and answer the ONE permission a
 * parked job is waiting on.
 *
 * **What this is.** The background queue ([JobRecord], "Long Fuse") has had a
 * read and a cancel on the phone for months. Until `backend/jobs-routes.patch`
 * there was no route that CREATED a job and none that ANSWERED a parked one:
 * a job only ever existed because code called `create()`, and a job waiting
 * for a permission waited for ever. The desktop got both routes first
 * (`brain.rs` `brain_create_job` / `brain_answer_job`, `src/brain.js`
 * `renderJobStart` / `jobGrantActions`); this file is the phone's half, built
 * against the same contracts (docs/JARVIS-API.md section 169).
 *
 * **NOTHING HERE APPROVES ANYTHING BY ITSELF.** Starting a job is the
 * owner-present call `create()` has always needed; the phone sends `needs: []`
 * on purpose, exactly as the desktop does, so a job starts with NO
 * capabilities and parks the moment it needs one. Answering is the owner's own
 * yes or no arriving over HTTP, for ONE job and ONE use: the grant is spent by
 * the handler's next `require()`, a second tap is a 409, and a No stops that
 * job at once and leaves no rule behind - the next job needing the same
 * action parks and asks again. There is deliberately no "always allow" and no
 * list form: that would be a standing rule, and the whole permission model is
 * one card per action (ARCHITECTURE.md section 3).
 *
 * **Held on a stale link, both writes.** Rule 4 blocks acting on a stream that
 * cannot be confirmed live, and both of these are actions. The read is not
 * held - reading claims nothing.
 *
 * Kept out of the screen ([com.jarvis.client.ui.screens.JobsSection]) so the
 * parsing, the two request bodies and every sentence can be tested on the JVM
 * without a running app, the way [Tasks] and [TaskControl] are.
 */
object Jobs {

    /** The GET the Work pane already made; now it also carries the grants. */
    const val PATH = "/api/jobs"

    /** The POST that answers one parked job's one grant. */
    const val ANSWER_PATH = "/api/jobs/answer"

    /** The phone's heading - the same words the desktop's Work tab uses. */
    const val HEADING = "Background jobs"

    // ------------------------------------------------- the words ----------------------------------
    // Where the desktop says it, these are its words (src/brain.js renderJobStart
    // and jobGrantActions), so the owner reads the same question in both apps.

    const val START_HEAD = "Start a background job"

    /** The one word on the button, the desktop's too. */
    const val START = "Start"

    const val WORDS_LABEL = "What is it? Your own words"

    /** What the one registered body is, when there is only one. */
    const val WHAT_IT_DOES = "What it does"

    /** The closed list's question, when the PC registered more than one body. */
    const val KIND_QUESTION = "What should it do?"

    /** Marks the chosen row in that list - by words, never by colour alone. */
    const val CHOSEN = "(chosen)"
    const val CHOOSE = "Choose"

    /**
     * The desktop's own sentence, word for word, under the Start button: a job
     * started here begins with nothing and asks at its first need.
     */
    const val START_NOTE = "It starts with no permissions. If it needs one it stops there and " +
        "waits for you, under the job."

    /** The PC's own line when it will not start one. Straight from the backend module. */
    const val NO_KINDS = "No job kinds are registered on this PC yet, so there is nothing to start."

    /**
     * `ticking: false` - the one heartbeat is off, so a job started now would
     * never run. The desktop words the same refusal; this one names the file
     * plainly instead of its `[initiative]` table key, because the phone is not
     * a config editor (CLAUDE.md) and the owner has to change it on the PC.
     */
    const val HEARTBEAT_OFF = "The background heartbeat is off, so a job started now would " +
        "never run. Turn it back on in jarvis-framework.toml on the PC first."

    /** After a start landed - the desktop's toast, word for word. */
    const val STARTED = "Started. It runs at the next background check, and waits for you if it " +
        "needs anything."

    /** After an Allow once. One use, spent by its next use - said, not implied. */
    const val ALLOWED_ONCE = "Allowed once. It carries on at the next check, and that permission " +
        "is spent by the one use."

    /** After a No. The job stops; the refusal is not a rule. */
    const val ANSWERED_NO = "No. That job stops here, and the next one asks again."

    /** Under a parked job whose grant is gone: the answer is in, the work waits. */
    const val ANSWERED_LINE = "Answered. It carries on at the next background check."

    /** The suffix under the action's own words. One answer, one job. */
    const val ONE_ANSWER = "One answer, and it counts for this job only."

    /** The empty list, the desktop's words. */
    const val EMPTY = "No background jobs."

    /** The action word on the affirmative button. */
    const val ALLOW_ONCE = "Allow once"

    /** The word on the negative button, the desktop's too. */
    const val NO = "No"

    /**
     * 404/503 on either write: this PC's backend predates the two routes. The
     * same shape as [Tasks.UPDATE], and the same remedy.
     */
    const val UPDATE = "This PC's Jarvis does not have starting a background job yet. " +
        "Update the backend by running apply-patches.ps1, then try again."

    /** The PC answered `ok: false` with no sentence of its own. Never left blank. */
    const val START_REFUSED = "Your PC did not start the job, and did not say why."
    const val ANSWER_REFUSED = "Your PC did not answer it, and did not say why."

    // ------------------------------------------------- what the GET carries ------------------------

    /**
     * One grant a parked job is waiting on: `jarvis_jobs.pending_grants()`,
     * joined to its job by [jobId]. An action name and a job id - the same
     * class of fact the job list already carries, never a param or a result.
     */
    @Serializable
    data class Grant(
        val id: String = "",
        @SerialName("job_id") val jobId: String = "",
        val action: String = "",
        val state: String = "pending",
    )

    /**
     * The parts of the GET's `status` object the Work pane uses. It carries a
     * lot more (counts, the database path, the config); `ignoreUnknownKeys`
     * means only what is read here has to be named.
     */
    @Serializable
    data class Status(val handlers: List<String> = emptyList())

    /**
     * The whole `GET /api/jobs` body, not just its rows.
     *
     * [grants] and [ticking] are `null` when the PC does not send them, and
     * that absence is LOAD-BEARING: `jobs-routes.patch` added both keys, so a
     * body without them is a backend that cannot answer either write, and
     * [readOf] says so in words rather than drawing a form that would 404.
     * A missing key is not the same fact as an empty list.
     */
    @Serializable
    data class Feed(
        val jobs: List<JobRecord> = emptyList(),
        val grants: List<Grant>? = null,
        val ticking: Boolean? = null,
        val status: Status = Status(),
    ) {
        /**
         * The pending grant for one job, or null. Matched by job id, so two
         * parked jobs can never have their buttons swapped - the answer names
         * the grant's own job.
         */
        fun grantFor(jobId: String): Grant? =
            grants?.firstOrNull { it.jobId == jobId && it.state == "pending" }

        /**
         * A parked job whose grant is already gone: the owner answered and the
         * job is waiting for the next background check to use the answer. Only
         * when the PC really sent a grants list - with no list, "no grant" is
         * not evidence of anything and this is false.
         */
        fun answered(job: JobRecord): Boolean =
            job.state == WAITING_APPROVAL && grants != null && grantFor(job.id) == null
    }

    /** The state a job is in while it waits for a person (jarvis_jobs.STATES). */
    const val WAITING_APPROVAL = "waiting_approval"

    /** What one read of the Work pane came back with. */
    sealed interface Read {
        /** Nothing asked yet; the screen asks as soon as it opens. */
        data object NotAsked : Read
        data object Reading : Read

        /** The PC has both writes, so the pane can offer its controls. */
        data class Loaded(val feed: Feed) : Read

        /**
         * The GET worked but the two writes are not on this PC: either the
         * route answered 404/503, or its body has no `ticking` (the key
         * `jobs-routes.patch` added). The job list is still shown - it was
         * always read-only here - with [UPDATE] instead of the form.
         */
        data class OlderBackend(val feed: Feed) : Read

        /** The read itself failed. */
        data class Failed(val reason: String) : Read
    }

    /** The rows a read holds, for the list half. Null while reading or after a failure. */
    fun feedOf(read: Read): Feed? = when (read) {
        is Read.Loaded -> read.feed
        is Read.OlderBackend -> read.feed
        else -> null
    }

    fun readOf(result: ApiResult<Feed>): Read = when (result) {
        is ApiResult.Ok -> {
            val feed = result.value
            // No `ticking`: this PC's GET predates jobs-routes.patch, so neither
            // POST exists either. Saying "nothing is registered" would be a
            // guess about a PC we have just proved does not tell us.
            if (feed.ticking == null) Read.OlderBackend(feed) else Read.Loaded(feed)
        }
        is ApiResult.Failed -> when (result.error) {
            ApiError.NotFound, ApiError.NotAvailable -> Read.OlderBackend(Feed())
            else -> Read.Failed(PlainErrors.forApiError(result.error).text)
        }
    }

    /** The line under the list, or null when there is nothing to say. */
    fun readLine(read: Read): String? = when (read) {
        Read.NotAsked -> null
        Read.Reading -> "Reading…"
        is Read.Loaded -> null
        is Read.OlderBackend -> UPDATE
        is Read.Failed -> read.reason
    }

    /**
     * Why the form is replaced by a sentence, or null when it should be
     * offered. Both refusals are the server's own facts, so the form never
     * promises a job that could not run.
     */
    fun startProblem(feed: Feed?): String? {
        if (feed == null) return null
        if (feed.status.handlers.isEmpty()) return NO_KINDS
        if (feed.ticking == false) return HEARTBEAT_OFF
        return null
    }

    // ------------------------------------------------- the request bodies --------------------------

    /**
     * `POST /api/jobs {"kind","text","needs":[]}`.
     *
     * `needs` is EMPTY on purpose, like the desktop's form: this screen is not
     * a capability picker, so a job started here runs with nothing frozen and
     * parks on its first need, where the owner answers one question at a time.
     * Nothing on this screen can widen the set.
     */
    fun startBody(kind: String, text: String): String =
        """{"kind":${JarvisApi.quote(kind)},"text":${JarvisApi.quote(text)},"needs":[]}"""

    /** `POST /api/jobs/answer {"id","approved"}` - ONE real boolean, never a guess. */
    fun answerBody(id: String, approved: Boolean): String =
        """{"id":${JarvisApi.quote(id)},"approved":${if (approved) "true" else "false"}}"""

    // ------------------------------------------------- what the answers mean -----------------------

    /** What a write came back with: a line to show, and whether anything changed. */
    sealed interface Said {
        /** The PC did it. [words] says what happened, in the form the owner expects. */
        data class Landed(val words: String) : Said

        /** Nothing changed. [words] is the PC's own sentence where it gave one. */
        data class Refused(val words: String) : Said
    }

    /**
     * What a start's answer means. `ok: true` is the job queued; `ok: false`
     * is the PC's own refusal (`handle_create`'s 400/503 sentences: no kind, an
     * unknown kind, a `never` action, the heartbeat off) and is shown as it
     * was written. A transport failure is put into plain words.
     */
    fun startSaid(reply: JsonObject?, error: ApiError? = null): Said {
        if (error != null) return Said.Refused(failureLine(error))
        return if (accepted(reply)) Said.Landed(STARTED)
        else Said.Refused(pcWords(reply) ?: START_REFUSED)
    }

    /**
     * What an answer's answer means. A No is not a failure: the PC decided the
     * grant `denied`, stopped that job, and said so - the line has to say both,
     * or "No" looks like it did nothing. An `ok: false` is a refusal (nothing
     * waiting, more than one, already answered, no such job) and keeps the
     * PC's sentence.
     */
    fun answerSaid(reply: JsonObject?, error: ApiError? = null): Said {
        if (error != null) return Said.Refused(failureLine(error))
        if (!accepted(reply)) return Said.Refused(pcWords(reply) ?: ANSWER_REFUSED)
        val state = ((reply?.get("grant") as? JsonObject)
            ?.get("state") as? JsonPrimitive)?.contentOrNull
        return Said.Landed(if (state == "denied") ANSWERED_NO else ALLOWED_ONCE)
    }

    /**
     * What a failed write says. A 404/503 means this PC has no such route -
     * an older backend, which has its own sentence and its own remedy - and
     * everything else is the plain words every failure uses.
     */
    fun failureLine(e: ApiError): String = when (e) {
        ApiError.NotFound, ApiError.NotAvailable -> UPDATE
        else -> PlainErrors.forApiError(e).text
    }

    /** The action's own words, the phone's own card wording (`CardWords.fallbackTitle`). */
    fun actionWords(action: String?): String = CardWords.fallbackTitle(action)

    /**
     * The sentence under a parked job: what it is asking for, then what one
     * answer means. [actionWords] is already a sentence ("Jarvis wants your OK
     * for \"send an email\""), so it is not prefixed with another "wants" -
     * the desktop's own line reads `wants: <the same words>`.
     */
    fun wantLine(grant: Grant): String = actionWords(grant.action) + ". " + ONE_ANSWER

    /** A job's state in the phone's plain words (its own [JobRecord.state]). */
    fun stateWords(state: String): String = when (state) {
        "queued" -> "waiting"
        "running" -> "running"
        WAITING_APPROVAL -> "waiting on you"
        "done" -> "done"
        "failed" -> "stopped"
        "cancelled" -> "cancelled"
        else -> state
    }

    private fun accepted(reply: JsonObject?): Boolean =
        (reply?.get("ok") as? JsonPrimitive)?.booleanOrNull == true

    /** The PC's own `error` sentence from an `ok: false` body, when it wrote one. */
    private fun pcWords(reply: JsonObject?): String? =
        (reply?.get("error") as? JsonPrimitive)
            ?.takeIf { it.isString }
            ?.contentOrNull
            ?.trim()
            ?.takeIf { it.isNotEmpty() }
}
