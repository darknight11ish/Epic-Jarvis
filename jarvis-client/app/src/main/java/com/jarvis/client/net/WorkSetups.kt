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
 * The work setups: combinations of local models, each chosen for a kind of
 * work, each explained in plain words **before** the owner starts.
 *
 * `GET /api/work`, `POST /api/work/choose` -
 * `backend/work.patch` and `backend/jarvis_work.py`, and the design note
 * `.dsh-scratch/android-verify/WORK-SETUPS-DESIGN-2026-10-10.md`. The owner
 * asked for it on 2026-10-10: *"like if i was going to code an android app, or
 * work on admin stuff from my own life. and have these as selectable options
 * that explain what they do before i start work. and jarvis can also recommend
 * loading up certain combos if i talk about work i'd like to do."*
 *
 * WHAT THIS DOES. It shows the five setups the PC worked out for ITS OWN cards
 * - building an Android app, admin and paperwork, long conversations and big
 * documents, everyday quick answers, and a coding specialist - with, for each
 * one, what it is for, which model goes on which card, what it costs and what
 * it is honestly worse at. Choosing one remembers the choice and nothing else.
 *
 * WHAT IT DELIBERATELY DOES NOT DO.
 *
 *  - It never switches a model by itself. The one step a setup can need is the
 *    model switch the owner already knows ([SWITCH_PATH], `/api/models/switch`),
 *    which raises its own approval card - and it is posted only from
 *    [stepRequest], only for the step the PC itself said is next.
 *  - It never downloads anything. A setup whose model is not on the PC says so,
 *    in the PC's own words, and points at the ordinary download card; there is
 *    no download route here to post to.
 *  - It never asks the PC what to suggest. The dead phone-side work-offer
 *    surface (`POST /api/work/recommend`) was removed on 2026-10-22 (F11):
 *    neither app called it and it can never populate. The PC's own
 *    `POST /api/work/choose` is the one write this file posts.
 *  - It is not a catalogue. Five combinations of models already on this PC,
 *    as words the PC wrote - no list of what could be installed, no search
 *    (CLAUDE.md), and [STEP_ROUTES] is the only set of routes a step may name.
 *
 * Every sentence about the setups is the PC's own, word for word. Kept apart
 * from the screen so it is tested on the JVM against
 * `contract/work-setups-cases.json`, the REAL answers
 * `tools/gen_work_cases.py` writes (WorkSetupsContractTest).
 */
object WorkSetups {

    const val PATH = "/api/work"
    const val CHOOSE_PATH = "/api/work/choose"

    /** The model switch the owner already approves. The only step route. */
    const val SWITCH_PATH = "/api/models/switch"

    /** The routes a step of a work setup may ever name - the backend's own set. */
    val STEP_ROUTES = listOf(SWITCH_PATH)

    /** The five ids, in the order the PC sends them. A guard, not a catalogue. */
    val IDS = listOf("everyday", "coding", "admin", "long", "specialist")

    // Where it lives, and what the screen says around it.
    const val TITLE = "Work setups"
    const val KICKER = "What are you about to work on?"
    const val HOW_TO =
        "Pick the one that matches the work. Jarvis shows what each one is for, which " +
            "models it uses and what it costs before you choose anything. Choosing only " +
            "remembers the choice - switching a model still asks you with its own card."
    const val NOT_A_CATALOGUE =
        "These are combinations of models already on your PC. There is no list here of " +
            "models you could download, and no search."
    const val USE_THIS = "Use this setup"
    const val CHOSEN = "Your choice"
    const val STOP = "Stop using a setup"
    const val WHY_TITLE = "Why this one:"
    const val COST_TITLE = "What it costs:"
    const val WORSE_TITLE = "What it is worse at:"
    const val USES_TITLE = "Both cards:"
    const val THINKING_TITLE = "Before you start:"
    const val MODELS_TITLE = "Models and cards:"
    const val PLACES_TITLE = "Where each model goes:"
    const val READY = "Ready"
    const val NEEDS_DOWNLOAD = "Needs a download"
    const val COULD_NOT_ASK = "Could not ask Ollama"

    /** While the link is stale: rule 4 - nothing that asks is drawn as pressable. */
    const val STALE =
        "Not connected to the desktop, so choosing a setup and its step wait until the " +
            "link is back."

    /** The PC's backend predates work.patch. */
    const val UPDATE =
        "This PC's Jarvis does not have the work setups yet. Update the backend by " +
            "running apply-patches.ps1, then open this again."

    /** While a step's card waits. The same line as every other card on the phone. */
    const val WAITING = "Waiting for your approval. " + Approvals.WHERE
    const val ASKED =
        "Asked. Your PC raises its approval card; nothing changes until you approve it."

    /**
     * A step just asked for reads as waiting this long, even when the PC cannot
     * see its card: the gate's own wait is 180 seconds. One tap is one card.
     */
    const val ASKED_FOR_MS = 180_000L

    data class Place(
        val role: String,
        val model: String,
        val card: String,
        val context: Int?,
        val contextWords: String?,
        val vramGib: Double?,
        val speed: Double?,
        val spills: Boolean,
        /** The PC's own words for what this model is doing in this setup. */
        val words: String,
    )

    data class Step(
        /** none, missing, switch, unknown */
        val kind: String,
        val title: String,
        val detail: String?,
        val route: String?,
        val body: JsonObject?,
        val done: Boolean?,
        val words: String,
    )

    data class Setup(
        val id: String,
        val name: String,
        val work: String,
        val what: String,
        val cost: String,
        val worse: String,
        val uses: String,
        val why: String,
        val thinking: String,
        val bothCards: Boolean,
        val summary: String,
        val places: List<Place>,
        /** ready, partial, missing, unknown */
        val ready: String,
        val readyWords: String,
        val have: List<String>,
        val need: List<String>,
        val mainModel: String,
        val step: Step,
        val cardWords: String,
    ) {
        fun place(role: String): Place? = places.firstOrNull { it.role == role }
    }

    data class Status(
        val found: String,
        val setups: List<Setup>,
        val chosen: String?,
        val chosenName: String?,
        val currentModel: String?,
        val ollamaSeen: Boolean,
        val howTo: String,
        val notACatalogue: String,
    ) {
        fun setup(id: String): Setup? = setups.firstOrNull { it.id == id }
        val chosenSetup: Setup? get() = chosen?.let { setup(it) }
    }

    /** How the last read came back. The screen draws each one differently. */
    sealed interface Read {
        data object NotAsked : Read
        data class Loaded(val status: Status) : Read
        /** 404: the PC's backend predates work.patch. */
        data object OlderBackend : Read
        /** 503: the route is there, but `jarvis_work.py` could not be loaded. */
        data object NotInstalled : Read
        data class Failed(val reason: String) : Read
    }

    // ---------------------------------------------------------------- read --

    /** The PC's answer, or null when it is not the shape `status()` makes. */
    fun parse(obj: JsonObject): Status? {
        val setups = obj["setups"] as? JsonArray ?: return null
        return Status(
            found = obj.str("found").orEmpty(),
            setups = setups.mapNotNull { el ->
                val s = el as? JsonObject ?: return@mapNotNull null
                val id = s.str("id") ?: return@mapNotNull null
                Setup(
                    id = id,
                    name = s.str("name") ?: return@mapNotNull null,
                    work = s.str("work").orEmpty(),
                    what = s.str("what").orEmpty(),
                    cost = s.str("cost").orEmpty(),
                    worse = s.str("worse").orEmpty(),
                    uses = s.str("uses").orEmpty(),
                    why = s.str("why").orEmpty(),
                    thinking = s.str("thinking").orEmpty(),
                    bothCards = s.bool("both_cards") ?: false,
                    summary = s.str("summary").orEmpty(),
                    places = (s["places"] as? JsonArray).orEmpty().mapNotNull { p ->
                        val o = p as? JsonObject ?: return@mapNotNull null
                        Place(
                            role = o.str("role").orEmpty(),
                            model = o.str("model") ?: return@mapNotNull null,
                            card = o.str("card").orEmpty(),
                            context = o.int("context"),
                            contextWords = o.str("context_words"),
                            vramGib = o.dbl("vram_gib"),
                            speed = o.dbl("speed_tokens_per_s"),
                            spills = o.bool("clean") == false,
                            words = o.str("words").orEmpty(),
                        )
                    },
                    ready = s.str("ready") ?: "unknown",
                    readyWords = s.str("ready_words").orEmpty(),
                    have = strings(s["have"]),
                    need = strings(s["need"]),
                    mainModel = s.str("main_model").orEmpty(),
                    step = step(s["step"] as? JsonObject),
                    cardWords = s.str("card_words").orEmpty(),
                )
            },
            chosen = obj.str("chosen"),
            chosenName = obj.str("chosen_name"),
            currentModel = obj.str("current_model"),
            ollamaSeen = obj.bool("ollama_seen") == true,
            howTo = obj.str("how_to").orEmpty().ifBlank { HOW_TO },
            notACatalogue = obj.str("not_a_catalogue").orEmpty().ifBlank { NOT_A_CATALOGUE },
        )
    }

    private fun step(o: JsonObject?): Step {
        if (o == null) {
            return Step("unknown", "What would change could not be read", null, null, null,
                null, "Nothing to do yet: the PC did not say what this setup needs.")
        }
        return Step(
            kind = o.str("kind") ?: "unknown",
            title = o.str("title").orEmpty(),
            detail = o.str("detail"),
            route = o.str("route"),
            body = o["body"] as? JsonObject,
            done = o.bool("done"),
            words = o.str("words").orEmpty(),
        )
    }

    /** A GET's result, as the screen's states. */
    fun readOf(result: ApiResult<JsonObject>): Read = when (result) {
        is ApiResult.Ok -> parse(result.value)?.let { Read.Loaded(it) }
            ?: Read.Failed("Your PC answered, but not in a shape this screen can read.")
        is ApiResult.Failed -> when (val e = result.error) {
            ApiError.NotFound, ApiError.NotAvailable -> Read.NotInstalled
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

    /** "qwen3.5:9b on the RTX 2060, 192K, 44.9 tokens a second" - the PC's numbers. */
    fun placeLine(p: Place): String {
        val bits = mutableListOf("${p.model} on the ${p.card}")
        p.contextWords?.let { bits += it }
        p.speed?.let { bits += "${number(it)} tokens a second" }
        val line = bits.joinToString(", ")
        return if (p.spills) "$line - part of it is on the processor, which is much slower"
        else line
    }

    /** What each model is for, in the PC's own words. */
    fun placeWords(p: Place): String = p.words.takeIf { it.isNotBlank() }?.let { "$it." }.orEmpty()

    /** "Everyday quick answers - short questions, writing, checking things." */
    fun setupLine(s: Setup): String = "${s.name} - ${s.work}."

    fun readyLine(s: Setup): String = when (s.ready) {
        "ready" -> READY
        "missing", "partial" -> NEEDS_DOWNLOAD
        else -> COULD_NOT_ASK
    }

    /** The one line under a setup's name: what it is for, and whether it is here. */
    fun headLine(s: Setup): String = "${readyLine(s)}. ${s.what}"

    /** The step's own line, in the shape every other card on the phone uses. */
    fun stepWords(s: Step, askedAtMs: Long?, nowMs: Long): String = when {
        s.kind == "none" -> s.words
        s.kind == "missing" || s.kind == "unknown" -> s.words
        s.done == true -> s.words
        askedAtMs != null && nowMs - askedAtMs < ASKED_FOR_MS -> WAITING
        else -> s.words.ifBlank { ASKED }
    }

    /** Whether "Use this setup" can be pressed for [s]. */
    fun canChoose(status: Status, s: Setup): Boolean = status.chosen != s.id

    /** Is [s] the setup the owner has chosen? */
    fun isChosen(status: Status, s: Setup): Boolean = status.chosen == s.id

    /**
     * The step's route and body, from the PC's own answer - never made up here.
     *
     * Four refusals, and each one is a rule rather than a formality: the setup
     * must be the one the owner CHOSE (a suggestion is never a switch), the step
     * must be one that can still be taken, the route must be one this app asks
     * for ([STEP_ROUTES]), and the body must be an object the PC itself wrote.
     */
    sealed interface StepAsk {
        data class Post(val route: String, val body: String) : StepAsk
        data class No(val reason: String) : StepAsk
    }

    fun stepRequest(status: Status, s: Setup): StepAsk {
        // The one the owner chose. The same step arrives on every setup in the
        // PC's answer, so without this an offer, or a setup nobody picked,
        // could switch a model - which is exactly what must never happen.
        if (!isChosen(status, s)) {
            return StepAsk.No(
                "That is not the setup you chose, so there is nothing to ask for. " +
                    "Choose it first; choosing changes no model.")
        }
        val step = s.step
        when (step.kind) {
            "switch" -> Unit
            "none" -> return StepAsk.No(step.words.ifBlank { "Nothing needs changing." })
            "missing" -> return StepAsk.No(
                "That model is not downloaded yet, so there is nothing to switch to.")
            else -> return StepAsk.No(
                step.words.ifBlank { "The PC did not say what this setup needs." })
        }
        val route = step.route?.takeIf { it in STEP_ROUTES }
            ?: return StepAsk.No("That step is not one this app asks for.")
        val body = step.body ?: return StepAsk.No("That step is not one this app asks for.")
        // Belt and braces: a switch step must name the model it switches TO.
        if (route == SWITCH_PATH && body.str("ref").isNullOrBlank()) {
            return StepAsk.No("That step does not say which model to switch to.")
        }
        return StepAsk.Post(route, body.toString())
    }

    // -------------------------------------------------------------- write --

    /** `{"setup": "coding"}` or `{"setup": null}`, built as JSON. */
    fun chooseBody(id: String?): String = buildJsonObject {
        if (id == null) put("setup", JsonNull) else put("setup", id)
    }.toString()

    /** A POST's answer, as the screen's states - the same rules as Hardware's. */
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

    /** What to tell the owner after choosing or asking. Never claims a change. */
    fun replyLine(result: ApiResult<JsonObject>): String = when (result) {
        is ApiResult.Ok -> result.value.str("error")?.let { sentence(it) }
            ?: result.value.str("message") ?: ASKED
        is ApiResult.Failed -> "Nothing changed. " + failureLine(result.error)
    }

    private fun failureLine(e: ApiError): String = when (e) {
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
        (el as? JsonArray).orEmpty().mapNotNull {
            (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.contentOrNull
        }

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.bool(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull

    private fun JsonObject.int(key: String): Int? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.intOrNull

    private fun JsonObject.dbl(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull
}
