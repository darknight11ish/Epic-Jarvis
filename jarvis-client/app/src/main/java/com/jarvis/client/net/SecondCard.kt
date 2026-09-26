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
import kotlinx.serialization.json.put

/**
 * The second graphics card: what the PC found, and its switches.
 *
 * `GET /api/second-card` and `POST /api/second-card` - `backend/second-card.patch`
 * and `backend/jarvis_second_card.py`, docs/JARVIS-API.md section 12, the
 * owner's guide docs/SECOND-CARD.md. Everything here is OFF until the owner
 * turns it on, and it can only be turned on once the PC has found a capable
 * second card (Turing or newer, at least 10 GB).
 *
 * WHAT THE PHONE DOES WITH IT. A handful of switches, one at a time, and
 * nothing else - not deep config editing. Turning a switch ON raises ONE
 * approval card on the PC (action `second_card_enable`), decided on the PC or
 * in this phone's own approval list like any other card; nothing is approved
 * from here. OFF is immediate. The state shown is always what the PC last
 * reported, never what was just asked for - the same rule as the wake word.
 *
 * Kept apart from the screen and the runtime so it can be tested on the JVM
 * against `contract/second-card-cases.json`, the REAL `status()` output that
 * tools/gen_second_card_cases.py writes for both apps.
 */
object SecondCard {

    const val PATH = "/api/second-card"

    /** The main switch's id in `POST` and in `pending`. */
    const val MASTER = "master"

    /** The Pictures feature: the only one the phone's chat looks at. */
    const val VISION = "vision"

    /** The words for the main switch. The backend has no row for it. */
    const val MASTER_NAME = "Use the second graphics card"
    const val MASTER_WHAT =
        "The main switch. None of the features below can run unless this is on. " +
            "Turning it off stops everything on the second card."

    /** While a card to turn something on is waiting. Same line for every switch. */
    const val WAITING = "Waiting for your approval. " + Approvals.WHERE

    /** Where the pin command lives, since the phone does not show it. */
    const val PIN_ON_PC =
        "The command is for your PC, so it is not shown here. Run it there: " +
            "desktop app → Settings → Second graphics card has a Copy button."

    data class Card(
        val index: Int?,
        val name: String,
        val totalMb: Int?,
        /** "primary", "second" or "unused". */
        val role: String,
        val why: String?,
    )

    data class Feature(
        val id: String,
        val name: String,
        val what: String,
        /** The owner's switch. Kept on even while the card is missing. */
        val enabled: Boolean,
        /** The switch, the main switch, its needs and a capable card. */
        val active: Boolean,
        /** Active and actually working (second Ollama up, model installed). */
        val available: Boolean,
        val needs: List<String>,
        /** Null when there is no capable card to size one for. */
        val model: String?,
        /** Null when the PC could not tell. */
        val modelInstalled: Boolean?,
        val memoryGib: Double?,
        /** The PC's own sentence for the line under the switch. */
        val why: String,
    )

    data class Status(
        val capable: Boolean,
        val detectedWhy: String,
        val cards: List<Card>,
        /** The main switch. */
        val enabled: Boolean,
        val active: Boolean,
        /** Switches with a card waiting, "master" included. */
        val pending: List<String>,
        /** "off", "starting", "running" or "failed". */
        val laneState: String,
        val laneWhy: String,
        val mainOllamaPinned: Boolean?,
        val pinNote: String?,
        /** Whether there is a pin command at all. The phone never shows it. */
        val hasPinCommand: Boolean,
        val features: List<Feature>,
        /** How the last approval card ended, any switch; null when none has, or an older PC. */
        val last: LastCard? = null,
    ) {
        fun feature(id: String): Feature? = features.firstOrNull { it.id == id }
    }

    /**
     * `status()["last"]` (AP-6, since 2026-09-24): the most recent approval
     * card to END, whichever switch it was for. The big model sends the same
     * shape. [why] is the PC's own sentence, meant to be shown as it is.
     *
     * [outcome] is one of `enabled`, `denied`, `timed_out` (nobody answered),
     * `refused`, `failed`, `withdrawn` (switched off while the card waited) -
     * kept as a string, so a word added later is shown, not dropped.
     */
    data class LastCard(val feature: String, val outcome: String, val why: String?)

    /** How the last read came back. The screen draws each one differently. */
    sealed interface Read {
        /** Not asked yet on this run of the app. */
        data object NotAsked : Read

        data class Loaded(val status: Status) : Read

        /** 404: the PC's backend predates the second-card patch. */
        data object OlderBackend : Read

        /** 503: the route is there, but `jarvis_second_card.py` could not be loaded. */
        data object NotInstalled : Read

        data class Failed(val reason: String) : Read
    }

    // ---------------------------------------------------------------- read --

    /**
     * The PC's answer, or null when it is not the shape `status()` makes -
     * which is then shown as a failed read, never as "no second card".
     */
    fun parse(obj: JsonObject): Status? {
        val detected = obj["detected"] as? JsonObject ?: return null
        val features = obj["features"] as? JsonArray ?: return null
        val lane = obj["lane"] as? JsonObject
        return Status(
            capable = detected.bool("capable") ?: false,
            detectedWhy = detected.str("why").orEmpty(),
            cards = (detected["cards"] as? JsonArray).orEmpty().mapNotNull { el ->
                val c = el as? JsonObject ?: return@mapNotNull null
                Card(
                    index = c.int("index"),
                    name = c.str("name") ?: "a graphics card",
                    totalMb = c.int("total_mb"),
                    role = c.str("role") ?: "unused",
                    why = c.str("why"),
                )
            },
            enabled = obj.bool("enabled") ?: false,
            active = obj.bool("active") ?: false,
            pending = (obj["pending"] as? JsonArray).orEmpty().mapNotNull { it.asString() },
            laneState = lane?.str("state") ?: "off",
            laneWhy = lane?.str("why").orEmpty(),
            mainOllamaPinned = obj.bool("main_ollama_pinned"),
            pinNote = obj.str("pin_note"),
            hasPinCommand = obj.str("pin_command") != null,
            last = lastCard(obj),
            features = features.mapNotNull { el ->
                val f = el as? JsonObject ?: return@mapNotNull null
                val id = f.str("id") ?: return@mapNotNull null
                Feature(
                    id = id,
                    name = f.str("name") ?: id,
                    what = f.str("what").orEmpty(),
                    enabled = f.bool("enabled") ?: false,
                    active = f.bool("active") ?: false,
                    available = f.bool("available") ?: false,
                    needs = (f["needs"] as? JsonArray).orEmpty().mapNotNull { it.asString() },
                    model = f.str("model"),
                    modelInstalled = f.bool("model_installed"),
                    memoryGib = (f["memory_gib"] as? JsonPrimitive)?.doubleOrNull,
                    why = f.str("why").orEmpty(),
                )
            },
        )
    }

    /** A GET's result, as the screen's four states. */
    fun readOf(result: ApiResult<JsonObject>): Read = when (result) {
        is ApiResult.Ok -> parse(result.value)?.let { Read.Loaded(it) }
            ?: Read.Failed("Your PC answered, but not in a shape this screen can read.")
        is ApiResult.Failed -> when (val e = result.error) {
            ApiError.NotFound -> Read.OlderBackend
            ApiError.NotAvailable -> Read.NotInstalled
            else -> Read.Failed(failureLine(e))
        }
    }

    /** The sentence for a read that did not come back as the switches. */
    fun readLine(read: Read): String? = when (read) {
        Read.NotAsked -> "Asking your PC…"
        is Read.Loaded -> null
        Read.OlderBackend ->
            "Your PC's Jarvis is older than this screen, so it has no second-card " +
                "switches yet. Update the backend on the PC with apply-patches.ps1, then tap Refresh."
        Read.NotInstalled ->
            "Jarvis on your PC could not load its second-card part (jarvis_second_card.py). " +
                "Running apply-patches.ps1 on the PC again puts it back."
        is Read.Failed -> read.reason
    }

    /** True only when the PC said, on the last read, that Pictures is working. */
    fun visionAvailable(read: Read): Boolean =
        (read as? Read.Loaded)?.status?.feature(VISION)?.available == true

    // ------------------------------------------------------------ switches --

    /** One row on the plate: the main switch, or a feature. */
    data class SwitchView(
        val id: String,
        val name: String,
        val what: String,
        /** What the PC reports. Never the value just asked for. */
        val on: Boolean,
        val waiting: Boolean,
        /** The line under the switch, in the PC's own words where it has them. */
        val line: String,
        /** Why it cannot be turned on right now, or null when it can. */
        val blocked: String?,
        /** Model, installed or not - null for the main switch or no card. */
        val modelLine: String?,
        /** The features it needs, by name - null when none. */
        val needsLine: String?,
        /**
         * How this switch's last card ended, when that is news: it was not
         * turned on, and no newer card waits. Null otherwise, and always on
         * a PC that does not send `last` - the plate then reads as before.
         */
        val lastLine: String? = null,
    ) {
        /** OFF always goes; ON only when nothing blocks it and no card waits. */
        val canTurnOn: Boolean get() = !on && !waiting && blocked == null
    }

    fun master(s: Status): SwitchView {
        val waiting = MASTER in s.pending
        return SwitchView(
            id = MASTER,
            name = MASTER_NAME,
            what = MASTER_WHAT,
            on = s.enabled,
            waiting = waiting,
            line = when {
                waiting -> WAITING
                s.enabled && s.active -> "On."
                s.enabled -> "On, but it cannot run: ${s.detectedWhy}. Your choice is kept."
                !s.capable -> "Needs a capable second graphics card: ${s.detectedWhy}."
                else -> "Off. Turn this on first, then the features you want."
            },
            blocked = if (!s.capable) "Needs a capable second graphics card: ${s.detectedWhy}." else null,
            modelLine = null,
            needsLine = null,
            lastLine = lastLine(s.last, MASTER, MASTER_NAME, on = s.enabled, waiting = waiting),
        )
    }

    fun switches(s: Status): List<SwitchView> = s.features.map { f -> view(s, f) }

    fun view(s: Status, f: Feature): SwitchView {
        val waiting = f.id in s.pending
        val missing = f.needs.filter { need -> s.feature(need)?.enabled != true }
        return SwitchView(
            id = f.id,
            name = f.name,
            what = f.what,
            on = f.enabled,
            waiting = waiting,
            line = if (waiting) WAITING else f.why,
            blocked = when {
                !s.capable -> "Needs a capable second graphics card: ${s.detectedWhy}."
                !s.enabled -> "Turn on \"$MASTER_NAME\" above first."
                missing.isNotEmpty() -> "Turn on ${names(s, missing)} first."
                else -> null
            },
            modelLine = modelLine(f),
            needsLine = if (f.needs.isEmpty()) null else "Needs: ${names(s, f.needs)}.",
            lastLine = lastLine(s.last, f.id, f.name, on = f.enabled, waiting = waiting),
        )
    }

    // ----------------------------------------------------------- last card --

    /** `last` from a status answer, or null: absent, `null`, or not the shape. */
    fun lastCard(obj: JsonObject): LastCard? {
        val l = obj["last"] as? JsonObject ?: return null
        val feature = l.str("feature")?.takeIf { it.isNotBlank() } ?: return null
        val outcome = l.str("outcome")?.takeIf { it.isNotBlank() } ?: return null
        return LastCard(feature, outcome, l.str("why")?.trim()?.takeIf { it.isNotEmpty() })
    }

    /**
     * What to say under switch [id] about how its last card ended, or null.
     *
     * Before `last` existed, a card that was denied, timed out or failed
     * left the switch reading plain "Off." - as if nothing had been asked.
     * Said only when the last card to end was THIS switch's, it did not turn
     * it on, the switch is off and no newer card waits. "Turned on" is not
     * repeated: the switch's own "On." says it. The PC's own sentence is
     * used when it sends one; these are the fallbacks.
     */
    fun lastLine(last: LastCard?, id: String, name: String, on: Boolean, waiting: Boolean): String? {
        if (last == null || last.feature != id || waiting || on || last.outcome == "enabled") return null
        last.why?.let { return it }
        val q = "\"$name\""
        return when (last.outcome) {
            "denied" -> "You said no, so $q stays off."
            "timed_out", "expired" -> "Nobody answered the card in time, so $q stays off."
            "withdrawn" -> "You turned $q off while its card was waiting, so approving that card changed nothing."
            "failed" -> "$q could not be turned on."
            "refused" -> "$q was not turned on: your PC refused it."
            else -> "The last card for $q ended: ${last.outcome.replace('_', ' ')}."
        }
    }

    /**
     * Which model the feature uses, and whether the PC has it. Not installed:
     * the exact name to type into the Install box under Model - the same box
     * as any other model. There is no catalogue to pick it from.
     */
    fun modelLine(f: Feature): String? {
        val model = f.model ?: return null
        val size = f.memoryGib?.let { " Uses about ${"%.1f".format(java.util.Locale.ROOT, it)} GB of the second card." }
            .orEmpty()
        return when (f.modelInstalled) {
            true -> "Model: $model (installed).$size"
            false -> "Model: $model - not installed on your PC yet. To install it, type " +
                "$model into the Install box under Model above (or run ollama pull $model " +
                "on your PC). Nothing downloads until you approve that card.$size"
            null -> "Model: $model (your PC could not tell whether it is installed).$size"
        }
    }

    // ------------------------------------------------------ what was found --

    /** One line per card, in plain words: which it is and what it is for. */
    fun cardLines(s: Status): List<String> = s.cards.map { c ->
        val size = c.totalMb?.let { " (${(it + 512) / 1024} GB)" }.orEmpty()
        val role = when (c.role) {
            "primary" -> "main card"
            "second" -> "second card"
            else -> "not used"
        }
        "${c.name}$size - $role" + (c.why?.let { ": $it" } ?: "")
    }

    /** The second copy of Ollama, in words. */
    fun laneLine(s: Status): String {
        val state = when (s.laneState) {
            "off" -> "Not running"
            "starting" -> "Starting"
            "running" -> "Running"
            "failed" -> "Stopped with a problem"
            else -> s.laneState
        }
        return if (s.laneWhy.isBlank()) state else "$state: ${s.laneWhy}"
    }

    /**
     * Whether to add [PIN_ON_PC] after the PC's pin note: only when there is
     * a command, and the PC does not already say it is done.
     */
    fun pinNeedsPc(s: Status): Boolean = s.hasPinCommand && s.mainOllamaPinned != true

    private fun names(s: Status, ids: List<String>): String =
        ids.joinToString(" and ") { id -> "\"${s.feature(id)?.name ?: id}\"" }

    // ---------------------------------------------------------------- write --

    /** `{"feature": "...", "enabled": true|false}` - built as JSON, never glued. */
    fun postBody(feature: String, enabled: Boolean): String = buildJsonObject {
        put("feature", feature)
        put("enabled", enabled)
    }.toString()

    /**
     * A POST's answer. The route explains its refusals in `error` (400 a
     * needed switch is off, 409 a card already waits, 503 no capable card),
     * and those sentences are the most useful thing to show, so they come
     * back as `Ok` to be shown word for word. A bad token, a missing route
     * (404, an older backend) and a module that did not load
     * (`{"available": false}`) stay failures.
     */
    fun classifyPost(code: Int, body: JsonObject?): ApiResult<JsonObject> = when {
        code == 401 || code == 403 -> ApiResult.Failed(ApiError.BadToken)
        code == 404 -> ApiResult.Failed(ApiError.NotFound)
        body?.bool("available") == false -> ApiResult.Failed(ApiError.NotAvailable)
        code in 200..299 && body != null -> ApiResult.Ok(body)
        body?.str("error") != null -> ApiResult.Ok(body)
        code == 503 -> ApiResult.Failed(ApiError.NotAvailable)
        code == 409 -> ApiResult.Failed(ApiError.AlreadyHandled)
        code in 200..299 -> ApiResult.Failed(ApiError.Malformed("no answer body"))
        else -> ApiResult.Failed(ApiError.Server(code, ""))
    }

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

    private fun failureLine(e: ApiError): String = when (e) {
        // The plain words both apps use (PlainErrors): what happened, then
        // what to do - never the raw error or a status number.
        is ApiError.Unreachable, ApiError.BadToken, is ApiError.Server, is ApiError.Malformed ->
            PlainErrors.forApiError(e).text
        ApiError.NotFound -> readLine(Read.OlderBackend)!!
        ApiError.NotAvailable -> readLine(Read.NotInstalled)!!
        ApiError.AlreadyHandled -> "Already handled elsewhere."
    }

    // ---------------------------------------------------------------- route --

    /** A turn the second card answered: which feature moved it there, and the model. */
    data class Route(val feature: String, val model: String?)

    /**
     * `second_card` in the chat's `X-Jarvis-Route` header (a JSON object,
     * `second-card.patch`): present only on a turn the second card answered,
     * where `where` stays "local" and `lane` is the model really answering.
     * Null on every other turn, and on anything that is not that JSON.
     */
    fun routeFromHeader(header: String?): Route? {
        if (header.isNullOrBlank()) return null
        val obj = runCatching { JarvisJson.parseToJsonElement(header.trim()) as? JsonObject }
            .getOrNull() ?: return null
        val feature = obj.str("second_card")?.takeIf { it.isNotBlank() } ?: return null
        return Route(feature.take(40), obj.str("lane")?.takeIf { it.isNotBlank() }?.take(80))
    }

    /** The line under an answer the second card wrote. */
    fun routeNote(route: Route): String {
        val model = route.model?.let { " ($it)" }.orEmpty()
        return when (route.feature) {
            "long_context" ->
                "Answered on the second graphics card$model: the conversation was too long for the main one."
            VISION -> "Answered on the second graphics card$model, which can see pictures."
            else -> "Answered on the second graphics card$model."
        }
    }

    // -------------------------------------------------------------- helpers --

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.bool(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull

    private fun JsonObject.int(key: String): Int? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.intOrNull

    private fun JsonElement.asString(): String? =
        (this as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
}
