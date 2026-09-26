package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.put

/**
 * The graphics cards on the PC, and the three setups Jarvis offers for them.
 *
 * `GET /api/hardware`, `POST /api/hardware/apply`, `/create`, `/measure` -
 * `backend/hardware.patch` and `backend/jarvis_hardware.py`, the design
 * docs/HARDWARE-PROFILES.md (section 4.6, "Phone"), docs/JARVIS-API.md
 * section 20.
 *
 * WHAT THE PHONE DOES WITH IT. It shows the cards (names and memory), what
 * runs now, the three setups the PC worked out for ITS cards - never a list
 * of models that could be installed, never a search, never a picker: the
 * PC sends three setup ids with their words (CLAUDE.md: no model catalogue
 * on the phone) - and "Use this". Choosing changes nothing by itself: the
 * PC lists the steps, and each step is ONE tap that asks for that step, and
 * the PC raises that step's own approval card (the existing model download
 * and switch cards, the second-card cards, or "make a model"). Only the
 * next step can be asked for; there is no "do them all". The step's route
 * and body are read from the PC's own answer ([stepRequest]), never made
 * up here, and only four routes are ever posted to ([STEP_ROUTES]).
 *
 * The PowerShell line is for the PC: the phone shows it to read, not to run.
 *
 * Every sentence about the cards and setups is the PC's own; the labels
 * below are the desktop's (hardware-panel.js `HW`) word for word -
 * backend/test_hardware.py checks.
 *
 * Kept apart from the screen so it is tested on the JVM against
 * `contract/hardware-cases.json`, the REAL answers tools/gen_hardware_cases.py
 * writes for both apps (HardwareContractTest).
 */
object Hardware {

    const val PATH = "/api/hardware"
    const val APPLY_PATH = "/api/hardware/apply"
    const val CREATE_PATH = "/api/hardware/create"
    const val MEASURE_PATH = "/api/hardware/measure"

    /** The only routes a step may name - the backend's `STEP_ROUTES`. */
    val STEP_ROUTES = listOf("/api/models/install", "/api/models/switch", CREATE_PATH, SecondCard.PATH)

    // The labels, word for word the desktop's.
    const val USE_THIS = "Use this"
    const val RECOMMENDED = "(recommended)"
    const val CHOSEN = "Your choice"
    const val STOP = "Stop using this setup"
    const val ASK = "Ask"
    const val MEASURE = "Measure"
    const val STEP_DONE = "Done."
    const val STEP_NEXT = "Next. It raises its own approval card."
    const val STEP_LATER = "Waits for the step before it."
    const val STEP_COMMAND = "Run the one command below on your PC, then restart Ollama."
    const val ASKED = "Asked. Your PC raises its approval card; nothing changes until you approve it."

    /**
     * A step just asked for reads as waiting this long, even when the PC
     * cannot see its card (a download's or a switch's card is shaped by the
     * owner's own backend file): the gate's own wait is 180 seconds. Its
     * button stays hidden, so one tap is one card. The desktop does the same.
     */
    const val ASKED_FOR_MS = 180_000L
    const val NO_LONG = "Long conversations: no separate model."
    const val NO_PICTURES = "Pictures: off."
    const val OFF_TITLE = "What is off, and why:"
    const val RESTART = "Ollama has not picked these settings up yet. Quit Ollama (right-click " +
        "its icon by the clock, then Quit Ollama) and start it again from the Start menu."
    const val UPDATE = "This PC's Jarvis does not have the hardware part yet. Update the backend " +
        "by running apply-patches.ps1, then open this again."

    /** The phone's own line under the command: it is for the PC. */
    const val COMMAND_ON_PC = "This line is for your PC. Read it here; to run it, use the Copy " +
        "button in the desktop app (Settings, Hardware and models)."

    /** While a step's card waits. The same line as every other card on the phone. */
    const val WAITING = "Waiting for your approval. " + Approvals.WHERE

    data class Card(val name: String, val totalGb: Double?, val used: Boolean, val whyUnused: String?)

    data class Role(
        val words: String,
        val contextWords: String?,
        /** own, beside, swap, turns - or null for "chat itself". */
        val mode: String?,
        val sameAsChat: Boolean,
    )

    data class Preset(
        val id: String,
        val name: String,
        val summary: String,
        val recommended: Boolean,
        val recommendedWhy: String?,
        val measured: Boolean,
        val measuredWords: String,
        val chat: Role?,
        val long: Role?,
        val pictures: Role?,
        val off: List<String>,
        val notes: List<String>,
        val bestEffortWhy: List<String>,
    )

    data class Step(
        val id: String,
        val kind: String,
        val title: String,
        val detail: String?,
        /** done, next, waiting, later */
        val state: String,
        val route: String?,
        val body: JsonObject?,
    )

    data class Applying(val preset: String, val name: String, val steps: List<Step>, val restartPending: Boolean?)

    data class Status(
        val found: String,
        val cards: List<Card>,
        val nowLabel: String,
        val nowWords: String,
        val nowOnCardPercent: Int?,
        val presets: List<Preset>,
        val recommended: String?,
        val chosen: String?,
        val chosenStale: String?,
        val applying: Applying?,
        val commandLine: String?,
        val undoLine: String?,
        val checkLine: String?,
        val restartPending: Boolean?,
        val measureState: String,
        val measureWhy: String,
        val measureRoles: List<String>,
        val measureSpilled: Boolean,
    ) {
        fun preset(id: String): Preset? = presets.firstOrNull { it.id == id }
        val waiting: Boolean get() = applying?.steps?.any { it.state == "waiting" } == true
    }

    /** How the last read came back. The screen draws each one differently. */
    sealed interface Read {
        data object NotAsked : Read
        data class Loaded(val status: Status) : Read
        /** 404: the PC's backend predates hardware.patch. */
        data object OlderBackend : Read
        /** 503: the route is there, but `jarvis_hardware.py` could not be loaded. */
        data object NotInstalled : Read
        data class Failed(val reason: String) : Read
    }

    // ---------------------------------------------------------------- read --

    /** The PC's answer, or null when it is not the shape `status()` makes. */
    fun parse(obj: JsonObject): Status? {
        val presets = obj["presets"] as? JsonArray ?: return null
        val cards = obj["cards"] as? JsonArray ?: return null
        val now = obj["now"] as? JsonObject
        val command = obj["command"] as? JsonObject
        val applying = (obj["applying"] as? JsonObject)?.let { a ->
            Applying(
                preset = a.str("preset").orEmpty(),
                name = a.str("name").orEmpty(),
                steps = (a["steps"] as? JsonArray).orEmpty().mapNotNull { el ->
                    val s = el as? JsonObject ?: return@mapNotNull null
                    Step(
                        id = s.str("id") ?: return@mapNotNull null,
                        kind = s.str("kind").orEmpty(),
                        title = s.str("title").orEmpty(),
                        detail = s.str("detail"),
                        state = s.str("state") ?: "later",
                        route = s.str("route"),
                        body = s["body"] as? JsonObject,
                    )
                },
                restartPending = a.bool("restart_pending"),
            )
        }
        val measure = obj["measure"] as? JsonObject
        val lastRow = measure?.get("last") as? JsonObject
        val roles = (lastRow?.get("roles") as? JsonArray).orEmpty().mapNotNull { it as? JsonObject }
        return Status(
            found = obj.str("found").orEmpty(),
            cards = cards.mapNotNull { el ->
                val c = el as? JsonObject ?: return@mapNotNull null
                Card(
                    name = c.str("name") ?: "a graphics card",
                    totalGb = (c["total_gb"] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull,
                    used = c.bool("used") ?: false,
                    whyUnused = c.str("why_unused"),
                )
            },
            nowLabel = now?.str("label") ?: "Custom (your own setup)",
            nowWords = now?.str("words").orEmpty(),
            nowOnCardPercent = now?.int("on_card_percent"),
            presets = presets.mapNotNull { el ->
                val p = el as? JsonObject ?: return@mapNotNull null
                Preset(
                    id = p.str("id") ?: return@mapNotNull null,
                    name = p.str("name") ?: return@mapNotNull null,
                    summary = p.str("summary").orEmpty(),
                    recommended = p.bool("recommended") ?: false,
                    recommendedWhy = p.str("recommended_why"),
                    measured = p.bool("measured") ?: false,
                    measuredWords = p.str("measured_words") ?: "calculated, not measured",
                    chat = role(p["chat"]),
                    long = role(p["long"]),
                    pictures = role(p["pictures"]),
                    off = strings(p["off"]),
                    notes = strings(p["notes"]),
                    bestEffortWhy = strings(p["best_effort_why"]),
                )
            },
            recommended = obj.str("recommended"),
            chosen = obj.str("chosen"),
            chosenStale = obj.str("chosen_stale"),
            applying = applying,
            commandLine = command?.str("line"),
            undoLine = command?.str("undo"),
            checkLine = command?.str("check"),
            restartPending = applying?.restartPending ?: command?.bool("restart_pending"),
            measureState = measure?.str("state") ?: "idle",
            measureWhy = measure?.str("why").orEmpty(),
            measureRoles = roles.map { r ->
                buildList {
                    add(r.str("model") ?: "a model")
                    (r["tokens_per_s"] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull?.let {
                        add("${number(it)} tokens a second")
                    }
                    r.int("on_card_percent")?.let { add("$it% on the card") }
                    r.str("note")?.let { add(it) }
                }.joinToString(", ") + "."
            },
            measureSpilled = lastRow?.bool("ok") == false && roles.any { it.bool("spilled") == true },
        )
    }

    private fun role(el: JsonElement?): Role? {
        val r = el as? JsonObject ?: return null
        return Role(
            words = r.str("words").orEmpty(),
            contextWords = r.str("context_words"),
            mode = r.str("mode"),
            sameAsChat = r.bool("same_as_chat") == true,
        )
    }

    /** A GET's result, as the screen's states. */
    fun readOf(result: ApiResult<JsonObject>): Read = when (result) {
        is ApiResult.Ok -> parse(result.value)?.let { Read.Loaded(it) }
            ?: Read.Failed("Your PC answered, but not in a shape this screen can read.")
        is ApiResult.Failed -> when (val e = result.error) {
            ApiError.NotFound -> Read.OlderBackend
            ApiError.NotAvailable -> Read.NotInstalled
            else -> Read.Failed(failureLine(e))
        }
    }

    fun readLine(read: Read): String? = when (read) {
        Read.NotAsked -> "Asking your PC…"
        is Read.Loaded -> null
        Read.OlderBackend, Read.NotInstalled -> UPDATE
        is Read.Failed -> read.reason
    }

    // --------------------------------------------------------------- words --

    /** "NVIDIA GeForce RTX 2080 SUPER, 8 GB" - names and memory only. */
    fun cardLine(c: Card): String {
        val size = c.totalGb?.let { ", ${Math.round(it)} GB" }.orEmpty()
        return "${c.name}$size" + if (c.used) "" else " - not used by Ollama"
    }

    /** The same sentence the desktop builds for a role. */
    fun roleLine(label: String, r: Role?): String? {
        if (r == null) return null
        if (r.sameAsChat) return "$label: ${r.words}."
        val how = when (r.mode) {
            "beside" -> " It stays loaded beside chat."
            "swap" -> " It takes turns with chat: a picture unloads chat for a moment."
            "turns" -> " It takes turns with the other extra model on that card."
            else -> ""
        }
        val ctx = r.contextWords?.let { " It $it." }.orEmpty()
        return "$label: ${r.words}.$ctx$how"
    }

    /** Chat, long conversations and pictures, as the desktop lists them. */
    fun presetLines(p: Preset): List<String> = listOfNotNull(
        roleLine("Chat", p.chat),
        if (p.long != null) roleLine("Long conversations", p.long) else NO_LONG,
        if (p.pictures != null) roleLine("Pictures", p.pictures) else NO_PICTURES,
    )

    /** The line for a card or setup that is best effort (the owner's decision 2). */
    fun bestEffortLine(why: String): String = "Best effort, not tested: $why."

    /** "Calculated, not measured." / "Measured on this PC." */
    fun measuredLine(p: Preset): String = sentence(p.measuredWords)

    /** [s] as the screen shows it: "waiting" for a while after it was asked for. */
    fun shown(s: Step, askedAtMs: Long?, nowMs: Long): Step =
        if (s.state == "next" && askedAtMs != null && nowMs - askedAtMs < ASKED_FOR_MS) {
            s.copy(state = "waiting")
        } else {
            s
        }

    fun stepWords(s: Step): String = when {
        s.kind == "command" && s.state != "done" -> STEP_COMMAND
        s.state == "done" -> STEP_DONE
        s.state == "waiting" -> WAITING
        s.state == "next" -> STEP_NEXT
        else -> STEP_LATER
    }

    /** Whether the Use this button can be pressed for [p]. */
    fun canChoose(s: Status, p: Preset): Boolean = s.chosen != p.id && p.chat != null

    fun measureLine(s: Status): String {
        val bits = mutableListOf<String>()
        if (s.measureState == "running") bits += "Measuring…" else if (s.measureWhy.isNotBlank()) bits += s.measureWhy
        bits += s.measureRoles
        return bits.joinToString(" ").ifBlank { "Not measured yet: every number above is calculated." }
    }

    // ---------------------------------------------------------------- write --

    /** `{"preset": "fast" | "smart" | "features" | null}`, built as JSON. */
    fun applyBody(preset: String?): String = buildJsonObject {
        if (preset == null) put("preset", JsonNull) else put("preset", preset)
    }.toString()

    /** What asking for one step posts, or why it cannot be asked for. */
    sealed interface StepAsk {
        data class Post(val route: String, val body: String) : StepAsk
        data class No(val reason: String) : StepAsk
    }

    /**
     * Step [id]'s route and body, read from the PC's own answer - the same
     * rules as the desktop's hardware.rs `step_request`: only the step that
     * is next, only [STEP_ROUTES], and the body must be an object.
     */
    fun stepRequest(s: Status, id: String): StepAsk {
        val steps = s.applying?.steps ?: return StepAsk.No("No setup is chosen, so there is no step to ask for.")
        val step = steps.firstOrNull { it.id == id }
            ?: return StepAsk.No("That step is not in the chosen setup any more.")
        when (step.state) {
            "next" -> Unit
            "done" -> return StepAsk.No("That step is already done.")
            "waiting" -> return StepAsk.No("That step's approval card is already waiting - approve or deny that one.")
            else -> return StepAsk.No("That step waits for the one before it.")
        }
        val route = step.route?.takeIf { it in STEP_ROUTES }
            ?: return StepAsk.No("That step is not one this app asks for.")
        val body = step.body ?: return StepAsk.No("That step is not one this app asks for.")
        return StepAsk.Post(route, body.toString())
    }

    /**
     * A POST's answer. The routes explain their refusals in `error` (400 an
     * unknown setup, 409 a card already waits or the model is not downloaded,
     * 503 the tier or Ollama), and those sentences are shown word for word,
     * so they come back as `Ok`. A bad token, a missing route and a module
     * that did not load stay failures.
     */
    fun classifyPost(code: Int, body: JsonObject?): ApiResult<JsonObject> = when {
        code == 401 || code == 403 -> ApiResult.Failed(ApiError.BadToken)
        code == 404 && body?.str("error") == null -> ApiResult.Failed(ApiError.NotFound)
        body?.bool("available") == false -> ApiResult.Failed(ApiError.NotAvailable)
        code in 200..299 && body != null -> ApiResult.Ok(body)
        body?.str("error") != null -> ApiResult.Ok(body)
        code == 503 -> ApiResult.Failed(ApiError.NotAvailable)
        code == 409 -> ApiResult.Failed(ApiError.AlreadyHandled)
        code in 200..299 -> ApiResult.Ok(JsonObject(emptyMap()))
        else -> ApiResult.Failed(ApiError.Server(code, ""))
    }

    /** What to tell the owner after asking. Never claims anything happened. */
    fun replyLine(result: ApiResult<JsonObject>): String = when (result) {
        is ApiResult.Ok -> result.value.str("error")?.let { sentence(it) }
            ?: if (result.value.bool("pending") == true) WAITING
            else result.value.str("message") ?: ASKED
        is ApiResult.Failed -> when (val e = result.error) {
            ApiError.NotFound, ApiError.NotAvailable -> UPDATE
            ApiError.AlreadyHandled -> "A card for that is already waiting - approve or deny that one."
            else -> "Nothing changed. " + failureLine(e)
        }
    }

    private fun failureLine(e: ApiError): String = when (e) {
        // The plain words both apps use (PlainErrors): what happened, then
        // what to do - never the raw error or a status number.
        is ApiError.Unreachable, ApiError.BadToken, is ApiError.Server, is ApiError.Malformed ->
            PlainErrors.forApiError(e).text
        ApiError.NotFound, ApiError.NotAvailable -> UPDATE
        ApiError.AlreadyHandled -> "Already handled elsewhere."
    }

    // -------------------------------------------------------------- helpers --

    /** First letter up, one full stop - the desktop's `sentence`. */
    fun sentence(text: String): String {
        val s = text.trim().trimEnd('.', ' ')
        return if (s.isEmpty()) "" else s.replaceFirstChar { it.uppercase() } + "."
    }

    private fun number(d: Double): String =
        if (d == Math.floor(d)) d.toLong().toString() else d.toString()

    private fun strings(el: JsonElement?): List<String> =
        (el as? JsonArray).orEmpty().mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.contentOrNull }

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.bool(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull

    private fun JsonObject.int(key: String): Int? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.intOrNull
}
