package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.put

/**
 * The focus presets: combinations of local models, chosen for a kind of work,
 * each explained in the PC's own words before the owner uses it.
 *
 * ONE contract for both apps: `backend/jarvis_presets.py` supplies every word
 * here (`preset.title`, `focus`, `what`, `cost`, `worse`, the model and lane
 * labels); a client must never write its own description of a preset or name a
 * model itself. The generated fixture both apps build against is
 * `backend/fixtures/work_presets.json` (tools/gen_work_presets.py; regenerate,
 * never hand-edit), and [FocusPresetsTest] reads that real file.
 *
 * The new contract's answer carries the five `presets[]`, the PC's `hardware`
 * (with the `questionnaire`) and `recommendations`, plus the saved `chosen`
 * id when the PC has one. This object keeps those blocks so the client parses
 * the WHOLE shape rather than only the rows, but only [presets] and [chosen]
 * change what the screens draw; the chip and the plate render one row per
 * preset, never a hardcoded list.
 *
 * Generic over the list: the owner added `general_uncensored` as a fifth
 * preset and may change Agentic+Vision's model after a measurement, so this
 * object never hardcodes an id, a count, a model name or a lane. A
 * `pending: true` preset is drawn with the PC's own "being prepared" words and
 * no apply button.
 *
 * ONE action: using a preset posts the single apply action the contract names
 * (`apply.apply_route`, today `/api/work/apply`; an older contract only names
 * `switch_route`, which is the existing switch_model card). The body for the
 * apply route is `{"preset": "<id>"}` - the body its backend test expects -
 * and the fallback switch route keeps the existing `{"ref": "<model>"}` body.
 * Nothing is automatic ([Apply.auto] must be false), nothing is posted while
 * the link is stale, and a success never means the switch happened - the
 * caller re-reads the list.
 */
object FocusPresets {

    const val PATH = "/api/work"

    /** The contract's own apply route (presets.patch, 2026-10-18). */
    const val APPLY_PATH = "/api/work/apply"

    // ---- local UI labels only; every word about a preset comes from the contract ----
    const val TITLE = "Focus presets"
    const val KICKER = "What are you working on?"
    const val CHOOSE = "Choose a preset"
    const val NO_CHOICE = "No preset chosen"
    const val USE_THIS = "Use this preset"
    const val CHOSEN = "Current"
    const val WHY = "What it is for:"
    const val COST = "What it costs:"
    const val WORSE = "What it is worse at:"
    const val MODELS = "Model and card:"
    const val HELPER = "Second worker:"
    const val PENDING = "Being prepared"
    const val HEAVY =
        "This preset needs both cards at once as one pooled lane. Your PC refuses heavy mode " +
            "until that lane support lands, so it cannot be used from here yet."
    const val APPLY_UNPUBLISHED =
        "The PC has not published this preset's apply action yet, so nothing can be asked here."
    const val STALE =
        "Not connected to the desktop, so using a preset waits until the link is back."
    const val UPDATE =
        "This PC's Jarvis does not have focus presets yet. Update the backend, then open this again."
    const val WAITING =
        "Asked. Your PC raises one approval card; nothing changes until you approve it."
    const val NOTHING_CHANGED = "Nothing was changed."

    data class Lane(val key: String, val card: String, val port: Int?, val words: String)

    data class Helper(val model: String, val lane: Lane, val context: Int?)

    data class Measured(val tokensPerSecond: Double?, val sizeGib: Double?, val vramGib: Double?, val spillGib: Double?)

    /**
     * The ONE action for this preset, exactly as the contract names it. [route]
     * is the contract's own apply route when it publishes one; older contracts
     * only carry [switchRoute], which is the existing switch_model card, and
     * that is then the action. [auto] must stay false.
     */
    data class Apply(
        val action: String,
        val route: String?,
        val body: JsonObject?,
        val switchRoute: String?,
        val laneStart: Boolean,
        val auto: Boolean,
    ) {
        /** The route to post, or null when the contract names no action yet. */
        val postRoute: String? get() = route ?: switchRoute
    }
    data class Preset(
        val id: String,
        val title: String,
        val focus: String,
        val what: String,
        val cost: String,
        val worse: String,
        val model: String,
        val lane: Lane,
        val context: Int?,
        val helper: Helper?,
        val measured: Measured?,
        val pending: Boolean,
        /** true when the preset's model needs both cards together (the PC's words say why). */
        val heavyMode: Boolean,
        val apply: Apply,
    )

    data class View(
        val presets: List<Preset>,
        val chosen: String?,
        val found: String?,
        val switchPath: String?,
        /** The PC's own cards, as the answer sends them (`detected`). */
        val hardware: JsonObject? = null,
        /** The detected-card block, whichever shape carried it. */
        val detected: JsonObject? = null,
        /** focus/priority choices and answers (inside `hardware` in the fixture; top-level live). */
        val questionnaire: JsonObject? = null,
        /** The 1/2/3-GPU rows the PC worked out; parsed, not drawn by this feature yet. */
        val recommendations: JsonObject? = null,
        /** The lane the PC's chat points at right now, and the two contract paths. */
        val activeLane: JsonObject? = null,
        val applyPath: String? = null,
    ) {
        fun preset(id: String): Preset? = presets.firstOrNull { it.id == id }
        val current: Preset? get() = chosen?.let(::preset)
    }

    sealed interface Read {
        data object NotAsked : Read
        data class Loaded(val view: View) : Read
        data class Failed(val words: String) : Read
    }

    /** Parses the one contract shape. Null when there is no `presets` array. */
    fun parse(root: JsonObject): View? {
        val array = root["presets"] as? JsonArray ?: return null
        val presets = array.mapNotNull { element ->
            val o = element as? JsonObject ?: return@mapNotNull null
            val id = o.str("id") ?: return@mapNotNull null
            val title = o.str("title") ?: id
            val lane = parseLane(o.obj("lane")) ?: return@mapNotNull null
            val apply = parseApply(o.obj("apply")) ?: return@mapNotNull null
            Preset(
                id = id,
                title = title,
                focus = o.str("focus").orEmpty(),
                what = o.str("what").orEmpty(),
                cost = o.str("cost").orEmpty(),
                worse = o.str("worse").orEmpty(),
                model = o.str("model").orEmpty(),
                lane = lane,
                context = o.int("context"),
                helper = o.obj("helper")?.let { h ->
                    val helperLane = parseLane(h.obj("lane")) ?: return@let null
                    Helper(h.str("model").orEmpty(), helperLane, h.int("context"))
                },
                measured = o.obj("measured")?.let { m ->
                    Measured(
                        tokensPerSecond = m.double("tok_s"),
                        sizeGib = m.double("size_gib"),
                        vramGib = m.double("vram_gib"),
                        spillGib = m.double("spill_gib"),
                    )
                },
                pending = o.bool("pending") ?: false,
                heavyMode = o.bool("heavy_mode") ?: false,
                apply = apply,
            )
        }
        if (presets.isEmpty()) return null
        val chosen = root.str("chosen")
            ?: root.str("chosen_id")
            ?: root.str("current")
            ?: presets.firstOrNull { it.id == root.str("current_id") }?.id
            ?: presets.firstOrNull { root.bool("chosen") == true }?.id
        // The live GET /api/work answer (jarvis_presets.live_status) carries
        // `hardware` as the detected-card block and `questionnaire` beside it;
        // the generated fixture's `hardware` wraps both. Accept both, and keep
        // the active lane and apply path parsed so the live shape is checked
        // here. This feature draws only the preset rows and the chosen id.
        val hardware = root.obj("hardware")
        val detected = hardware?.obj("detected") ?: hardware
        val questionnaire = hardware?.obj("questionnaire") ?: root.obj("questionnaire")
        return View(
            presets = presets,
            chosen = chosen,
            found = root.str("found"),
            switchPath = root.str("switch_path"),
            hardware = hardware,
            detected = detected,
            questionnaire = questionnaire,
            recommendations = root.obj("recommendations"),
            activeLane = root.obj("active_lane"),
            applyPath = root.str("apply_path"),
        )
    }

    fun readOf(result: ApiResult<JsonObject>): Read = when (result) {
        is ApiResult.Ok -> parse(result.value)?.let { Read.Loaded(it) } ?: Read.Failed(UPDATE)
        is ApiResult.Failed -> when (val error = result.error) {
            ApiError.NotFound, ApiError.NotAvailable -> Read.Failed(UPDATE)
            is ApiError.Server ->
                if (error.code == 501) Read.Failed(UPDATE)
                else Read.Failed("Could not read the focus presets: $error")
            else -> Read.Failed("Could not read the focus presets: $error")
        }
    }

    /** Null when this preset may be used now, else the one sentence saying why not. */
    fun blocker(view: View, preset: Preset, stale: Boolean, linkUp: Boolean): String? = when {
        !linkUp -> STALE
        stale -> STALE
        preset.pending -> PENDING + ". " + preset.cost
        preset.heavyMode -> HEAVY
        preset.apply.auto -> APPLY_UNPUBLISHED
        preset.apply.postRoute == null -> APPLY_UNPUBLISHED
        else -> null
    }

    /**
     * The body for the contract's action: an explicit contract body wins; the
     * merged apply route takes `{"preset": "<id>"}` (the body its backend
     * test expects); the old switch fallback keeps `{"ref": "<model>"}`.
     */
    fun applyBody(preset: Preset): JsonObject {
        preset.apply.body?.let { return it }
        val route = preset.apply.postRoute ?: return buildJsonObject { }
        return if (route == APPLY_PATH || route.endsWith("/work/apply")) {
            buildJsonObject { put("preset", preset.id) }
        } else {
            buildJsonObject {
                if (preset.model.isNotBlank()) put("ref", preset.model)
            }
        }
    }

    fun applyRoute(preset: Preset): String? = preset.apply.postRoute

    /** A short line for the chat chip: the current preset's PC title, or a local prompt. */
    fun chipLabel(view: View?): String = view?.current?.title ?: NO_CHOICE

    /** One line per preset for a closed list: title, then the backend's focus words. */
    fun headLine(preset: Preset): String =
        if (preset.focus.isBlank()) preset.title else "${preset.title} - ${preset.focus}"

    /** Model/card words, assembled only from the contract's own strings. */
    fun modelLine(preset: Preset): String {
        val context = preset.context?.let { n -> ", ${"%,d".format(n)} tokens" }.orEmpty()
        return "${preset.model} on ${preset.lane.card} (${preset.lane.words})$context"
    }

    fun helperLine(preset: Preset): String? = preset.helper?.let { h ->
        "${h.model} on ${h.lane.card} (${h.lane.words})" +
            (h.context?.let { n -> ", ${"%,d".format(n)} tokens" }.orEmpty())
    }

    /** What the PC answered to the one apply POST, in its own words when it gives any. */
    fun replyLine(code: Int, body: JsonObject?): String = when (code) {
        200 -> body?.str("words") ?: body?.str("message") ?: body?.str("line")
            ?: if (body?.bool("changed") == true) {
                // The apply route's success body carries no sentence of its own.
                "Preset applied. Your PC switched its chat lane; nothing else changed."
            } else {
                WAITING
            }
        202 -> body?.str("words") ?: body?.str("message") ?: body?.str("line") ?: WAITING
        else -> body?.str("error")?.let { "Not changed. $it" } ?: NOTHING_CHANGED
    }

    /** What the PC answered, in the PC's words when it gives any. */
    fun replyLine(result: ApiResult<JsonObject>): String = when (result) {
        is ApiResult.Ok -> {
            val body = result.value
            body.str("words") ?: body.str("message") ?: body.str("line") ?: WAITING
        }
        is ApiResult.Failed -> when (val error = result.error) {
            ApiError.NotFound, ApiError.NotAvailable -> UPDATE
            is ApiError.Server -> if (error.code == 501) UPDATE else "Not changed. $error"
            else -> "Not changed. $error"
        }
    }

    // ------------------------------------------------------------------ json ----

    private fun parseLane(o: JsonObject?): Lane? = o?.let {
        Lane(
            key = it.str("key").orEmpty(),
            card = it.str("card").orEmpty(),
            port = it.int("port"),
            words = it.str("words").orEmpty(),
        )
    }

    private fun parseApply(o: JsonObject?): Apply? {
        if (o == null) return null
        fun routeOf(key: String): String? = (o[key] as? JsonPrimitive)?.contentOrNull
            ?.takeIf { it.startsWith("/api/") }
        return Apply(
            action = o.str("action") ?: USE_THIS,
            route = routeOf("route") ?: routeOf("path") ?: routeOf("apply_route"),
            body = o["body"] as? JsonObject,
            switchRoute = routeOf("switch_route"),
            laneStart = o.bool("lane_start") ?: false,
            auto = o.bool("auto") ?: false,
        )
    }

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.bool(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.booleanOrNull

    private fun JsonObject.int(key: String): Int? =
        (this[key] as? JsonPrimitive)?.intOrNull

    private fun JsonObject.double(key: String): Double? =
        (this[key] as? JsonPrimitive)?.doubleOrNull

    private fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject
}
