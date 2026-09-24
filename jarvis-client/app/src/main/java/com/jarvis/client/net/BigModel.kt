package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import java.util.Locale

/**
 * The big model (slow): what the PC found, its three switches, and deep
 * questions.
 *
 * `GET`/`POST /api/big-model`, `GET /api/deep` and `POST /api/deep/ask` -
 * `backend/big-model.patch` and `backend/jarvis_big_model.py`, docs/JARVIS-API.md
 * section 14, the owner's guide docs/BIG-MODEL.md. colibri, a separate engine
 * the PC starts only when a background job needs it, runs a model far bigger
 * than the graphics card holds - slowly. It is used for two background jobs
 * only: the wiki builder and deep questions. Never chat, voice or approvals.
 *
 * WHAT THE PHONE DOES WITH IT. The same as the second-card plate
 * ([SecondCard]): a handful of switches, one at a time, and nothing else - no
 * config editing and no command lines. Everything is OFF until the owner
 * turns it on, and the main switch can only be turned on once the PC says
 * `detected.capable`. ON raises ONE approval card on the PC (action
 * `big_model_enable`), decided on the PC or in this phone's own approval list
 * like any other card; nothing is approved from here. OFF is immediate. The
 * switch shows what the PC last REPORTED, never what was just asked for.
 *
 * Deep questions: a text box and "Ask slowly". No card per question (the
 * switch was approved, and a question acts on nothing), but the ask is held
 * on a stale link all the same (rule 4). The answer is the owner's own and
 * is shown as plain text, only when the PC says `done`.
 *
 * Nobody has measured the speed on the owner's PC, so "not measured on this
 * PC yet" is shown until the PC reports a real number, and the PC's own
 * `unverified` sentence always sits beside the speeds.
 *
 * Kept apart from the screen and the runtime so it can be tested on the JVM
 * against `contract/big-model-cases.json`, the REAL output that
 * tools/gen_big_model_cases.py writes for both apps.
 */
object BigModel {

    const val PATH = "/api/big-model"
    const val DEEP_PATH = "/api/deep"
    const val ASK_PATH = "/api/deep/ask"

    /** The main switch's id in `POST` and in `pending`. */
    const val MASTER = "master"
    const val WIKI = "wiki"
    const val DEEP = "deep_questions"

    /** The words for the main switch. The backend has no row for it. */
    const val MASTER_NAME = "Use the big model (slow)"
    const val MASTER_WHAT =
        "The main switch. It lets Jarvis use a much bigger model than the graphics card " +
            "holds, for background jobs only - never chat, voice or approvals. Expect minutes " +
            "per answer. The jobs below need this on first."

    /** While a card to turn something on is waiting. The second card's words exactly. */
    const val WAITING = SecondCard.WAITING

    /** Until the PC has a real number for a job. The owner's decision: always visible. */
    const val NOT_MEASURED = "not measured on this PC yet"

    /** Re-read `GET /api/deep` this often while a question is waiting or running. */
    const val DEEP_POLL_MS = 20_000L

    /** The states a question is still going in. */
    val RUNNING_STATES = setOf("queued", "loading", "thinking")

    // ---------------------------------------------------------------- read --

    /** One model the PC is set up for, and whether it can be used. */
    data class Model(
        val id: String,
        val name: String,
        /** "medium" or "giant". */
        val kind: String,
        /** "D:", or empty when the PC could not tell. */
        val drive: String,
        /** "NVMe", "SATA SSD", ... or "unknown". */
        val driveType: String,
        /** Free space on that drive; null when unknown. */
        val freeGb: Double?,
        /** Memory it needs while it runs. */
        val needGb: Double?,
        val found: Boolean,
        val usable: Boolean,
        val canStartNow: Boolean,
        val why: String,
        /** A warning, for example a giant model on a SATA drive. */
        val note: String?,
    )

    data class Found(
        val capable: Boolean,
        val why: String,
        val colibriFound: Boolean,
        val colibriWhy: String,
        val pythonFound: Boolean,
        val pythonWhy: String,
        val ramTotalGb: Double?,
        val ramAvailableGb: Double?,
        val models: List<Model>,
    ) {
        fun model(id: String?): Model? = id?.let { m -> models.firstOrNull { it.id == m } }
    }

    data class Engine(
        /** "off", "loading", "ready" or "failed". */
        val state: String,
        val why: String,
        val model: String?,
        val busy: Boolean,
    )

    /** One job's switch: `wiki` or `deep_questions`. */
    data class Job(
        val id: String,
        val name: String,
        val what: String,
        /** The owner's switch. Stays on while its model has gone. */
        val enabled: Boolean,
        /** Can run now, or as soon as a job asks (colibri starts on demand). */
        val available: Boolean,
        val model: String?,
        val modelName: String?,
        /** The PC's own sentence for the line under the switch. */
        val why: String,
    )

    /** A job the PC timed. `seconds` includes reading the question. */
    data class Measured(
        val model: String?,
        val seconds: Double?,
        val tokens: Int?,
        val tokensPerS: Double?,
        val words: Int?,
        val wordsPerS: Double?,
    )

    data class Status(
        val found: Found,
        /** The main switch. */
        val enabled: Boolean,
        /** The main switch on AND capable. */
        val active: Boolean,
        /** Switches with a card waiting, "master" included. */
        val pending: List<String>,
        val engine: Engine,
        /** "off" or "on". */
        val cudaSetting: String,
        val cudaUsable: Boolean,
        val cudaWhy: String,
        val jobs: List<Job>,
        /** Keyed by job id; a missing or null entry is "not measured". */
        val measured: Map<String, Measured>,
        /** The PC's sentence that its speeds are not verified. Shown always. */
        val unverified: String,
    ) {
        fun job(id: String): Job? = jobs.firstOrNull { it.id == id }
    }

    /** How the last read came back. The screen draws each one differently. */
    sealed interface Read<out T> {
        /** Not asked yet on this run of the app. */
        data object NotAsked : Read<Nothing>

        data class Loaded<T>(val value: T) : Read<T>

        /** 404: the PC's backend predates big-model.patch. */
        data object OlderBackend : Read<Nothing>

        /** 503: the route is there, but `jarvis_big_model.py` could not be loaded. */
        data object NotInstalled : Read<Nothing>

        data class Failed(val reason: String) : Read<Nothing>
    }

    /**
     * The PC's answer, or null when it is not the shape `status()` makes -
     * which is then shown as a failed read, never as "nothing found".
     */
    fun parse(obj: JsonObject): Status? {
        val detected = obj["detected"] as? JsonObject ?: return null
        val switches = obj["switches"] as? JsonArray ?: return null
        val colibri = detected["colibri"] as? JsonObject
        val python = detected["python"] as? JsonObject
        val ram = detected["ram"] as? JsonObject
        val engine = obj["engine"] as? JsonObject
        val cuda = obj["cuda"] as? JsonObject
        val measured = obj["measured"] as? JsonObject
        return Status(
            found = Found(
                capable = detected.bool("capable") ?: false,
                why = detected.str("why").orEmpty(),
                colibriFound = colibri?.bool("found") ?: false,
                colibriWhy = colibri?.str("why").orEmpty(),
                pythonFound = python?.bool("found") ?: false,
                pythonWhy = python?.str("why").orEmpty(),
                ramTotalGb = ram?.num("total_gb"),
                ramAvailableGb = ram?.num("available_gb"),
                models = (detected["models"] as? JsonArray).orEmpty().mapNotNull { el ->
                    val m = el as? JsonObject ?: return@mapNotNull null
                    val id = m.str("id") ?: return@mapNotNull null
                    Model(
                        id = id,
                        name = m.str("name") ?: id,
                        kind = m.str("kind").orEmpty(),
                        drive = m.str("drive").orEmpty(),
                        driveType = m.str("drive_type") ?: "unknown",
                        freeGb = m.num("free_gb"),
                        needGb = m.num("need_gb"),
                        found = m.bool("found") ?: false,
                        usable = m.bool("usable") ?: false,
                        canStartNow = m.bool("can_start_now") ?: false,
                        why = m.str("why").orEmpty(),
                        note = m.str("note")?.takeIf { it.isNotBlank() },
                    )
                },
            ),
            enabled = obj.bool("enabled") ?: false,
            active = obj.bool("active") ?: false,
            pending = (obj["pending"] as? JsonArray).orEmpty().mapNotNull { it.asString() },
            engine = Engine(
                state = engine?.str("state") ?: "off",
                why = engine?.str("why").orEmpty(),
                model = engine?.str("model"),
                busy = engine?.bool("busy") ?: false,
            ),
            cudaSetting = cuda?.str("setting") ?: "off",
            cudaUsable = cuda?.bool("usable") ?: true,
            cudaWhy = cuda?.str("why").orEmpty(),
            jobs = switches.mapNotNull { el ->
                val j = el as? JsonObject ?: return@mapNotNull null
                val id = j.str("id") ?: return@mapNotNull null
                Job(
                    id = id,
                    name = j.str("name") ?: id,
                    what = j.str("what").orEmpty(),
                    enabled = j.bool("enabled") ?: false,
                    available = j.bool("available") ?: false,
                    model = j.str("model"),
                    modelName = j.str("model_name"),
                    why = j.str("why").orEmpty(),
                )
            },
            measured = measured.orEmpty().mapNotNull { (job, el) ->
                val m = el as? JsonObject ?: return@mapNotNull null
                job to Measured(
                    model = m.str("model"),
                    seconds = m.num("seconds"),
                    tokens = m.int("tokens"),
                    tokensPerS = m.num("tokens_per_s"),
                    words = m.int("words"),
                    wordsPerS = m.num("words_per_s"),
                )
            }.toMap(),
            unverified = obj.str("unverified").orEmpty(),
        )
    }

    /** A GET's result, as the screen's states. */
    fun readOf(result: ApiResult<JsonObject>): Read<Status> = readWith(result) { parse(it) }

    /** The sentence for a read that did not come back as the switches. */
    fun readLine(read: Read<*>): String? = when (read) {
        Read.NotAsked -> "Asking your PC…"
        is Read.Loaded<*> -> null
        Read.OlderBackend ->
            "Your PC's Jarvis is older than this screen, so it has no big model yet. " +
                "Update the backend on the PC with apply-patches.ps1, then tap Refresh."
        Read.NotInstalled ->
            "Jarvis on your PC could not load its big-model part (jarvis_big_model.py). " +
                "Running apply-patches.ps1 on the PC again puts it back."
        is Read.Failed -> read.reason
    }

    private fun <T> readWith(result: ApiResult<JsonObject>, parse: (JsonObject) -> T?): Read<T> =
        when (result) {
            is ApiResult.Ok -> parse(result.value)?.let { Read.Loaded(it) }
                ?: Read.Failed("Your PC answered, but not in a shape this screen can read.")
            is ApiResult.Failed -> when (val e = result.error) {
                ApiError.NotFound -> Read.OlderBackend
                ApiError.NotAvailable -> Read.NotInstalled
                else -> Read.Failed(failureLine(e))
            }
        }

    // ------------------------------------------------------------ switches --

    /**
     * The main switch as a row. The row type is the second card's, so both
     * plates draw switches the same way and share one row composable.
     */
    fun master(s: Status): SecondCard.SwitchView {
        val waiting = MASTER in s.pending
        val notReady = "Can be switched on once your PC has everything it needs: ${s.found.why}."
        return SecondCard.SwitchView(
            id = MASTER,
            name = MASTER_NAME,
            what = MASTER_WHAT,
            on = s.enabled,
            waiting = waiting,
            line = when {
                waiting -> WAITING
                s.enabled && s.active -> "On."
                s.enabled -> "On, but it cannot run: ${s.found.why}. Your choice is kept."
                !s.found.capable -> notReady
                else -> "Off. Turn this on first, then the jobs you want."
            },
            // The owner's decision: never offered until the PC says capable.
            blocked = if (!s.found.capable) notReady else null,
            modelLine = null,
            needsLine = null,
        )
    }

    fun switches(s: Status): List<SecondCard.SwitchView> = s.jobs.map { j -> view(s, j) }

    fun view(s: Status, j: Job): SecondCard.SwitchView {
        val waiting = j.id in s.pending
        // One of the PC's lines ends in two full stops ("... or wait..").
        val why = j.why.replace(TRAILING_DOTS, ".")
        return SecondCard.SwitchView(
            id = j.id,
            name = j.name,
            what = j.what,
            on = j.enabled,
            waiting = waiting,
            line = if (waiting) WAITING else why,
            // The PC's own line already says why in each of these, so the
            // row does not repeat it (it hides `blocked` when equal to `line`).
            blocked = when {
                !s.found.capable -> why
                !s.enabled -> why.ifBlank { "Turn on \"$MASTER_NAME\" above first." }
                j.model == null -> why
                else -> null
            },
            modelLine = modelLine(s, j),
            needsLine = null,
        )
    }

    private val TRAILING_DOTS = Regex("\\.{2,}$")

    /** Which model the job uses, and on which drive - in words. */
    fun modelLine(s: Status, j: Job): String? {
        val name = j.modelName ?: j.model ?: return null
        val m = s.found.model(j.model)
        val where = m?.let { " (${it.kind.ifBlank { "model" }}, ${driveWords(it)})" }.orEmpty()
        return "Model: $name$where."
    }

    // ------------------------------------------------------ what was found --

    /**
     * The PC's one-line verdict: what it found and can use, or the first
     * thing missing. The main switch is offered only when it is the former.
     */
    fun summaryLine(s: Status): String =
        if (s.found.capable) "Ready: ${ending(s.found.why)}" else "Not ready yet: ${ending(s.found.why)}"

    /** colibri, Python and memory, one line each, in the PC's words where it has them. */
    fun foundLines(s: Status): List<String> {
        val f = s.found
        val colibri = f.colibriWhy.ifBlank { if (f.colibriFound) "colibri found" else "colibri not found" }
        // Python is not checked until colibri is found; the PC then says so
        // itself ("not checked (colibri first)"), which needs a subject.
        val python = f.pythonWhy.ifBlank { if (f.pythonFound) "found" else "not found" }
        val memory = when {
            f.ramTotalGb != null && f.ramAvailableGb != null ->
                "${gb(f.ramTotalGb)} in this PC, ${gb(f.ramAvailableGb)} free right now"
            f.ramTotalGb != null -> "${gb(f.ramTotalGb)} in this PC; how much is free is not known"
            else -> "your PC could not tell"
        }
        return listOf(
            ending(colibri),
            ending(if (python.contains("Python")) python else "Python 3: $python"),
            "Memory: ${ending(memory)}",
        )
    }

    /** One model: where it is, the space and memory, and the PC's verdict. */
    data class ModelView(val title: String, val detail: String, val why: String, val warning: String?)

    fun modelViews(s: Status): List<ModelView> = s.found.models.map { m ->
        val kind = if (m.kind.isBlank()) "" else " (${m.kind})"
        val free = m.freeGb?.let { "${gb(it)} free on the drive" } ?: "free space on the drive not known"
        val need = m.needGb?.let { "needs about ${gb(it)} of memory while it runs" }
            ?: "memory needed not known"
        ModelView(
            title = "${m.name}$kind",
            detail = "On ${driveWords(m)}: $free; $need.",
            why = sentence(m.why),
            warning = m.note,
        )
    }

    private fun driveWords(m: Model): String {
        val drive = m.drive.ifBlank { "its drive" }
        val type = if (m.driveType.isBlank() || m.driveType == "unknown") "drive type unknown" else m.driveType
        return "$drive, $type"
    }

    /** colibri itself, in words. `loading` can last minutes. */
    fun engineLine(s: Status): String {
        val e = s.engine
        val base = when {
            e.state == "failed" -> "Stopped with a problem" + (if (e.why.isBlank()) "." else ": ${ending(e.why)}")
            // The PC's sentence already names the state: "not running - it
            // starts only when...", "loading ... - this can take several
            // minutes", "running ... on 127.0.0.1:8765 (this PC only)".
            e.why.isNotBlank() -> sentence(e.why)
            e.state == "off" -> "Not running."
            e.state == "loading" -> "Starting. This can take minutes."
            e.state == "ready" -> "Running."
            else -> sentence(e.state)
        }
        return if (e.busy) "$base Working on a job now." else base
    }

    /**
     * Only when the graphics-card setting is on: then it matters, and the
     * PC's sentence says whether it can be used. Off is the default and
     * means the processor only, which [CPU_ONLY] says in plain words.
     */
    fun cudaLine(s: Status): String =
        if (s.cudaSetting == "on") "Graphics card: ${sentence(s.cudaWhy)}" else CPU_ONLY

    const val CPU_ONLY = "Runs on this PC's processor and SSD. No graphics card is used."

    // --------------------------------------------------------------- speed --

    /**
     * One line per job, in the switches' order: its measured speed, or
     * [NOT_MEASURED]. Never a number the PC did not send.
     */
    fun speedLines(s: Status): List<String> {
        val order = s.jobs.map { it.id }.ifEmpty { listOf(WIKI, DEEP) }
        return order.map { id ->
            val name = s.job(id)?.name ?: id
            val m = s.measured[id]
            if (m == null || (m.wordsPerS == null && m.tokensPerS == null)) {
                "$name: $NOT_MEASURED."
            } else {
                val model = s.found.model(m.model)?.name ?: m.model
                val speed = listOfNotNull(
                    m.wordsPerS?.let { "${num(it)} words a second" },
                    m.tokensPerS?.let { "${num(it)} tokens a second" },
                ).joinToString(", ")
                val last = listOfNotNull(m.seconds?.let { "took ${duration(it)}" }, model?.let { "on $it" })
                "$name: $speed." + (if (last.isEmpty()) "" else " Last job " + last.joinToString(", ") + ".")
            }
        }
    }

    /** True while no job has a real number yet. */
    fun nothingMeasured(s: Status): Boolean = s.measured.values.none { it.wordsPerS != null || it.tokensPerS != null }

    // ---------------------------------------------------------------- write --

    /** `{"switch": "...", "enabled": true|false}` - built as JSON, never glued. */
    fun postBody(switch: String, enabled: Boolean): String = buildJsonObject {
        put("switch", switch)
        put("enabled", enabled)
    }.toString()

    /**
     * A POST's answer: the same rules as the second card's route, so the
     * same classification - explained refusals (400, 409, 503 with `error`)
     * come back as `Ok` to be shown word for word; a bad token, a missing
     * route and a module that did not load stay failures.
     */
    fun classifyPost(code: Int, body: JsonObject?): ApiResult<JsonObject> =
        SecondCard.classifyPost(code, body)

    /**
     * What to tell the owner after asking, or null when the plate itself
     * says it (a card is up, or the switch is off). The switch's state is
     * then re-read from the PC; this never claims anything turned on.
     */
    fun replyLine(result: ApiResult<JsonObject>): String? = when (result) {
        is ApiResult.Ok -> result.value.str("error")
        is ApiResult.Failed -> when (val e = result.error) {
            ApiError.NotFound -> readLine(Read.OlderBackend)
            ApiError.NotAvailable -> readLine(Read.NotInstalled)
            ApiError.AlreadyHandled -> "A card for that switch is already waiting - approve or deny that one."
            else -> "Nothing changed. " + failureLine(e)
        }
    }

    // -------------------------------------------------------- deep questions --

    data class DeepJob(
        val id: String,
        val question: String,
        /** "queued", "loading", "thinking", "done" or "failed". */
        val state: String,
        val seconds: Double?,
        val tokens: Int?,
        val wordsPerS: Double?,
        val tokensPerS: Double?,
        val model: String?,
        /** The PC's sentence for the line under it. */
        val why: String,
        /** Only when [state] is "done". */
        val answer: String?,
    ) {
        val running: Boolean get() = state in RUNNING_STATES
    }

    data class Deep(
        val available: Boolean,
        val why: String,
        val enabled: Boolean,
        /** Newest first, at most 20. */
        val jobs: List<DeepJob>,
        val questionChars: Int,
        val queue: Int,
    ) {
        val runningCount: Int get() = jobs.count { it.running }
        val anyRunning: Boolean get() = runningCount > 0
        val queueFull: Boolean get() = runningCount >= queue
    }

    /** `GET /api/deep`'s answer, or null when it is not that shape. */
    fun parseDeep(obj: JsonObject): Deep? {
        val jobs = obj["jobs"] as? JsonArray ?: return null
        val limits = obj["limits"] as? JsonObject
        return Deep(
            available = obj.bool("available") ?: false,
            why = obj.str("why").orEmpty(),
            enabled = obj.bool("enabled") ?: false,
            jobs = jobs.mapNotNull { el ->
                val j = el as? JsonObject ?: return@mapNotNull null
                val id = j.str("id") ?: return@mapNotNull null
                val state = j.str("state").orEmpty()
                DeepJob(
                    id = id,
                    question = j.str("question").orEmpty(),
                    state = state,
                    seconds = j.num("seconds"),
                    tokens = j.int("tokens"),
                    wordsPerS = j.num("words_per_s"),
                    tokensPerS = j.num("tokens_per_s"),
                    model = j.str("model"),
                    why = j.str("why").orEmpty(),
                    // The PC sends it only when done; checked here too.
                    answer = if (state == "done") j.str("answer") else null,
                )
            },
            questionChars = limits?.int("question_chars") ?: 4000,
            queue = limits?.int("queue") ?: 3,
        )
    }

    fun deepReadOf(result: ApiResult<JsonObject>): Read<Deep> = readWith(result) { parseDeep(it) }

    /** A question's state, in words. */
    fun stateLabel(state: String): String = when (state) {
        "queued" -> "Waiting its turn"
        "loading" -> "Starting the big model"
        "thinking" -> "Thinking"
        "done" -> "Answered"
        "failed" -> "Not answered"
        else -> state
    }

    /** Time taken and speed, or null while there is nothing measured. */
    fun jobMeta(j: DeepJob): String? {
        val parts = listOfNotNull(
            j.seconds?.let { "took ${duration(it)}" },
            j.wordsPerS?.let { "${num(it)} words a second" },
        )
        return if (parts.isEmpty()) null else parts.joinToString(", ").replaceFirstChar { it.uppercase() } + "."
    }

    /** Paragraphs of a finished answer, split the way chat splits a reply. */
    fun paragraphs(answer: String): List<String> =
        answer.trim().split(PARAGRAPH_BREAK).map { it.trim() }.filter { it.isNotEmpty() }

    private val PARAGRAPH_BREAK = Regex("\n\\s*\n")

    /**
     * Why the typed question cannot be sent, or null when it can. The PC
     * checks again (it trims and counts the same way); this only saves a
     * round trip for the two things the phone can see for itself.
     */
    fun askProblem(question: String, limit: Int): String? {
        val q = question.trim().replace("\r\n", "\n")
        return when {
            q.isEmpty() -> "Type a question first."
            q.length > limit ->
                "The question is ${"%,d".format(Locale.ROOT, q.length)} characters; at most " +
                    "${"%,d".format(Locale.ROOT, limit)}."
            else -> null
        }
    }

    /** `{"question": "..."}`, trimmed, or null when there is nothing to ask. */
    fun askBody(question: String): String? {
        val q = question.trim()
        if (q.isEmpty()) return null
        return buildJsonObject { put("question", q) }.toString()
    }

    /**
     * What to show after "Ask slowly". The PC's own sentence either way:
     * `message` when it queued the question, `error` when it refused.
     */
    data class Asked(val text: String, val queued: Boolean)

    fun askReply(result: ApiResult<JsonObject>): Asked = when (result) {
        is ApiResult.Ok -> {
            val body = result.value
            if (body.bool("ok") == true && body.str("state") == "queued") {
                Asked(body.str("message") ?: "Queued. The answer appears in the list when it is done.", true)
            } else {
                Asked(body.str("error") ?: body.str("message") ?: "Your PC did not queue it.", false)
            }
        }
        is ApiResult.Failed -> Asked(
            when (val e = result.error) {
                ApiError.NotFound -> readLine(Read.OlderBackend)!!
                ApiError.NotAvailable -> readLine(Read.NotInstalled)!!
                else -> "Not asked. " + failureLine(e)
            },
            false,
        )
    }

    // -------------------------------------------------------------- helpers --

    private fun failureLine(e: ApiError): String = when (e) {
        is ApiError.Unreachable ->
            "Could not reach your PC: ${e.detail}. Check your private network (Tailscale or " +
                "NordVPN Meshnet) is up on both ends, then tap Refresh."
        ApiError.BadToken -> "Your PC refused this phone's token. Pair the phone again."
        is ApiError.Server -> "Your PC answered ${e.code}, which this screen cannot read."
        is ApiError.Malformed -> "Your PC answered, but not in a shape this screen can read."
        ApiError.NotFound -> readLine(Read.OlderBackend)!!
        ApiError.NotAvailable -> readLine(Read.NotInstalled)!!
        ApiError.AlreadyHandled -> "Already handled elsewhere."
    }

    /** "8 s", "12 min 5 s", "1 h 3 min". */
    fun duration(seconds: Double): String {
        val s = Math.round(seconds).coerceAtLeast(0L)
        return when {
            s < 90 -> "$s s"
            s < 3600 -> "${s / 60} min" + (if (s % 60 != 0L) " ${s % 60} s" else "")
            else -> "${s / 3600} h" + (if ((s % 3600) / 60 != 0L) " ${(s % 3600) / 60} min" else "")
        }
    }

    /** "1.12", "1.5", "3" - at most two decimals, never a trailing zero. */
    private fun num(x: Double): String {
        val r = String.format(Locale.ROOT, "%.2f", x).trimEnd('0').trimEnd('.')
        return r.ifEmpty { "0" }
    }

    /** "24 GB", "25.3 GB", "3,100 GB". */
    fun gb(x: Double): String {
        val whole = x == Math.floor(x)
        return if (whole) "%,d GB".format(Locale.ROOT, x.toLong()) else "%,.1f GB".format(Locale.ROOT, x)
    }

    /** The PC's words, capitalised, ending in exactly one full stop. */
    private fun sentence(s: String): String = ending(s).replaceFirstChar { it.uppercase() }

    /**
     * The PC's words ending in exactly one full stop, first letter as sent
     * ("colibri" stays lower case). Most of its lines end in none, some in
     * one, and one in two ("... or wait.."); all come out the same.
     */
    private fun ending(s: String): String {
        val t = s.trim().trimEnd('.')
        return if (t.isEmpty()) "" else "$t."
    }

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.bool(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull

    private fun JsonObject.int(key: String): Int? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.let { it.intOrNull ?: it.longOrNull?.toInt() }

    private fun JsonObject.num(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull

    private fun JsonElement.asString(): String? =
        (this as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
}
