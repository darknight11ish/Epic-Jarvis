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
 * The second graphics card: what the PC found, and its switches.
 *
 * `GET /api/second-card` and `POST /api/second-card` - `backend/second-card.patch`
 * and `backend/jarvis_second_card.py`, docs/JARVIS-API.md section 12, the
 * owner's guide docs/SECOND-CARD.md. Everything here is OFF until the owner
 * turns it on, and it can only be turned on once the PC has found a capable
 * second card (Turing or newer, at least 8 GB; an 8 GB card runs fewer of the switches).
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

    /**
     * "One bigger model on both cards" (the third mode, 2026-09-26): its own
     * id in `POST` and in `pending`, a sibling of [MASTER] - it does not
     * compose with [MASTER] or the features below (it needs both cards to
     * itself), so it is never in [Status.features].
     */
    const val COMBINED = "combined"

    /** The Pictures feature: the only one the phone's chat looks at. */
    const val VISION = "vision"

    /**
     * A third graphics card (2026-09-28): its own id in `POST` and in
     * `pending` - never one of [Status.features], and never [MASTER]/
     * [COMBINED] either. Moving a switch here does not turn it on or off
     * (the switches above still do that) - it only says WHICH physical
     * card an already-on switch runs on, alongside the second card's own
     * lane, never instead of it. See
     * docs/GPU-SUPPORT-RESEARCH-2026-09-27.md section 1.3: never a
     * default, always a named choice.
     */
    const val THIRD = "third"

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
        /**
         * True for a switch that loads no model at all (Referee suggestions).
         * Optional: an older PC sends nothing, which reads as false.
         */
        val modelFree: Boolean = false,
    )

    data class Status(
        val capable: Boolean,
        val detectedWhy: String,
        val cards: List<Card>,
        /** The main switch. */
        val enabled: Boolean,
        val active: Boolean,
        /** Switches with a card waiting, "master" and "combined" included. */
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
        /**
         * Whether the PC reads the WORDS in a picture itself when the model
         * cannot see it (backend `jarvis_ocr.py`, 2026-09-26) - null from an
         * older PC. The PC reads them and marks them as outside text; this
         * app only decides whether to offer the Photo button.
         */
        val pictureText: PictureText? = null,
        /**
         * "One bigger model on both cards" (2026-09-26) - null from an older
         * PC. Not one of [features]: it ties up both cards, so it cannot run
         * at the same time as any of them, and it gets its own row.
         */
        val combined: Combined? = null,
        /**
         * "When to suggest the bigger model" (2026-09-27) - null from an
         * older PC, which then shows neither switch. Whether Jarvis may
         * OFFER [combined] on its own; never what it may do without a
         * person's yes, so unlike every switch above, changing one of
         * these raises NO approval card either way.
         */
        val suggest: Suggest? = null,
        /**
         * A third graphics card (2026-09-28) - null from an older PC. Not
         * one of [features]: it is not itself a switch, it says WHICH card
         * an already-on feature's switch runs on.
         */
        val third: ThirdCard? = null,
    ) {
        fun feature(id: String): Feature? = features.firstOrNull { it.id == id }
    }

    /** `status()["suggest"]`: the two "suggest the bigger model" switches. */
    data class Suggest(val title: String, val detail: String, val signals: List<Signal>)

    /** One suggestion signal: [id] is `"struggle"` or `"correction"`. */
    data class Signal(val id: String, val label: String, val why: String, val enabled: Boolean)

    /**
     * `status()["combined"]`: the third mode. [capable] is about the TWO
     * cards this needs (Turing or newer, big enough together) - a
     * different question from [Status.capable], which is only about the
     * second card alone. [conflict] is true while a switch in [features]
     * is genuinely on, which this cannot share both cards with.
     */
    data class Combined(
        val name: String,
        val what: String,
        val enabled: Boolean,
        val capable: Boolean,
        val capableWhy: String,
        val conflict: Boolean,
        val active: Boolean,
        val available: Boolean,
        val model: String?,
        val context: Int?,
        val memoryGib: Double?,
        val why: String,
    )

    /**
     * `status()["third"]` (2026-09-28): a third, genuinely capable graphics
     * card, and which of [Status.features] (if any) is moved onto it. Never
     * a default: [assigned] is null until the owner names one, even with a
     * capable [cardName] sitting right there. Runs at the same time as the
     * second card's own lane - a feature moved here does not stop working
     * on account of the switches above; it only runs somewhere else.
     */
    data class ThirdCard(
        /** A genuinely capable third card is here right now. */
        val capable: Boolean,
        /** Null when [capable] is false. */
        val cardName: String?,
        val cardTotalMb: Int?,
        /** One of [Status.features]' ids, or null: nothing is moved here. */
        val assigned: String?,
        /** Which switches could be moved here right now - already on. */
        val assignable: List<String>,
        val pending: Boolean,
        /** "off", "starting", "running" or "failed". */
        val laneState: String,
        val laneWhy: String,
        /** Null unless [assigned] names a feature. */
        val model: String?,
        val context: Int?,
        val memoryGib: Double?,
        val modelInstalled: Boolean?,
        val why: String,
    )

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

    /** `status()["picture_text"]`: can the PC read the words in a picture, and why not. */
    data class PictureText(val available: Boolean, val why: String)

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
            pictureText = (obj["picture_text"] as? JsonObject)?.let {
                PictureText(available = it.bool("available") == true, why = it.str("why").orEmpty())
            },
            combined = (obj["combined"] as? JsonObject)?.let { c ->
                Combined(
                    name = c.str("name") ?: "One bigger model on both cards",
                    what = c.str("what").orEmpty(),
                    enabled = c.bool("enabled") ?: false,
                    capable = c.bool("capable") ?: false,
                    capableWhy = c.str("capable_why").orEmpty(),
                    conflict = c.bool("conflict") ?: false,
                    active = c.bool("active") ?: false,
                    available = c.bool("available") ?: false,
                    model = c.str("model"),
                    context = c.int("context"),
                    memoryGib = (c["memory_gib"] as? JsonPrimitive)?.doubleOrNull,
                    why = c.str("why").orEmpty(),
                )
            },
            third = (obj["third"] as? JsonObject)?.let { t ->
                val card = t["card"] as? JsonObject
                ThirdCard(
                    capable = t.bool("capable") ?: false,
                    cardName = card?.str("name"),
                    cardTotalMb = card?.int("total_mb"),
                    assigned = t.str("assigned"),
                    assignable = (t["assignable"] as? JsonArray).orEmpty().mapNotNull { it.asString() },
                    pending = t.bool("pending") ?: false,
                    laneState = (t["lane"] as? JsonObject)?.str("state") ?: "off",
                    laneWhy = (t["lane"] as? JsonObject)?.str("why").orEmpty(),
                    model = t.str("model"),
                    context = t.int("context"),
                    memoryGib = (t["memory_gib"] as? JsonPrimitive)?.doubleOrNull,
                    modelInstalled = t.bool("model_installed"),
                    why = t.str("why").orEmpty(),
                )
            },
            suggest = (obj["suggest"] as? JsonObject)?.let { sug ->
                val signals = (sug["signals"] as? JsonArray).orEmpty().mapNotNull { el ->
                    val sig = el as? JsonObject ?: return@mapNotNull null
                    val id = sig.str("id") ?: return@mapNotNull null
                    Signal(
                        id = id,
                        label = sig.str("label") ?: id,
                        why = sig.str("why").orEmpty(),
                        enabled = sig.bool("enabled") ?: true,
                    )
                }
                Suggest(
                    title = sug.str("title") ?: "When to suggest the bigger model",
                    detail = sug.str("detail").orEmpty(),
                    signals = signals,
                )
            },
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
                    modelFree = f.bool("model_free") ?: false,
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

    /** True only when the PC said, on the last read, that it reads the words in a picture. */
    fun pictureTextAvailable(read: Read): Boolean =
        (read as? Read.Loaded)?.status?.pictureText?.available == true

    /**
     * Whether a picture sent now is of any use: the second card's picture
     * model sees it, or the PC reads the words in it (2026-09-26). The Photo
     * button and every send go by this.
     */
    fun picturesTaken(read: Read): Boolean = visionAvailable(read) || pictureTextAvailable(read)

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

    /**
     * "One bigger model on both cards" (the third mode), the same
     * [SwitchView] shape as [master] and [view] - null on an older PC that
     * sends no `combined`. Not one of [switches]: it ties up both cards, so
     * it cannot compose with them, and it never needs [MASTER] on first.
     */
    fun combinedSwitch(s: Status): SwitchView? {
        val c = s.combined ?: return null
        val waiting = COMBINED in s.pending
        return SwitchView(
            id = COMBINED,
            name = c.name,
            what = c.what,
            on = c.enabled,
            waiting = waiting,
            line = if (waiting) WAITING else c.why,
            blocked = when {
                !c.capable -> "Needs two capable graphics cards: ${c.capableWhy}."
                c.conflict -> "Turn off the switches above first - this needs both cards to itself."
                else -> null
            },
            modelLine = combinedModelLine(c),
            needsLine = null,
            lastLine = lastLine(s.last, COMBINED, c.name, on = c.enabled, waiting = waiting),
        )
    }

    /** [modelLine]'s shape for [Combined]: also says the room it has and that it is split. */
    fun combinedModelLine(c: Combined): String? {
        val model = c.model ?: return null
        val ctx = c.context?.let { " Room for ${"%,d".format(java.util.Locale.ROOT, it)} tokens." }.orEmpty()
        val size = c.memoryGib?.let {
            " Uses about ${"%.1f".format(java.util.Locale.ROOT, it)} GB, split across both cards."
        }.orEmpty()
        return "Model: $model.$ctx$size"
    }

    /** One choice on the third-card plate: [value] null means "Not used". */
    data class ThirdOption(val value: String?, val label: String, val selected: Boolean)

    /**
     * The third card's own options: "Not used" plus one per switch that is
     * actually on right now ([ThirdCard.assignable]) - a switch the owner
     * has not turned on cannot be moved here (its own switch above turns it
     * on; this only ever says where). If [ThirdCard.assigned] names a
     * switch that fell out of `assignable` since (turned off again), it is
     * still offered, selected, so the list never silently shows the wrong
     * thing. Null when there is no [Status.third] at all (an older PC).
     */
    fun thirdOptions(s: Status): List<ThirdOption>? {
        val t = s.third ?: return null
        val ids = if (t.assigned != null && t.assigned !in t.assignable) {
            t.assignable + t.assigned
        } else {
            t.assignable
        }
        val options = mutableListOf(ThirdOption(null, "Not used", selected = t.assigned == null))
        for (id in ids) {
            options += ThirdOption(id, s.feature(id)?.name ?: id, selected = t.assigned == id)
        }
        return options
    }

    /** Whether the third-card plate can be changed right now. */
    fun thirdCanChange(s: Status): Boolean {
        val t = s.third ?: return false
        return t.capable && !t.pending
    }

    /** The line under the third-card plate: waiting, why it cannot be moved, or the PC's own why. */
    fun thirdLine(s: Status): String {
        val t = s.third ?: return ""
        return if (t.pending) WAITING else t.why
    }

    /** [modelLine]'s shape for [ThirdCard]: null unless a feature is assigned. */
    fun thirdModelLine(t: ThirdCard): String? {
        val model = t.model ?: return null
        val size = t.memoryGib?.let { " Uses about ${"%.1f".format(java.util.Locale.ROOT, it)} GB of the third card." }
            .orEmpty()
        return when (t.modelInstalled) {
            true -> "Model: $model (installed).$size"
            false -> "Model: $model - not installed on your PC yet. To install it, type " +
                "$model into the Install box under Model above. Nothing downloads until you " +
                "approve that card.$size"
            null -> "Model: $model (your PC could not tell whether it is installed).$size"
        }
    }

    /** [lastLine]'s shape for the third card, whose "name" depends on which feature was asked for. */
    fun thirdLastLine(s: Status): String? {
        val last = s.last ?: return null
        val t = s.third
        if (last.feature != THIRD || t?.pending == true || t?.assigned != null) return null
        last.why?.let { return it }
        return when (last.outcome) {
            "denied" -> "You said no, so it stays where it was."
            "timed_out", "expired" -> "Nobody answered the card in time, so it stays where it was."
            "withdrawn" -> "You changed it while its card was waiting, so approving that card changed nothing."
            "failed" -> "It could not be moved."
            "refused" -> "It was not moved: your PC refused it."
            else -> "The last card for the third card ended: ${last.outcome.replace('_', ' ')}."
        }
    }

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
        if (f.modelFree) return null
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
     * `{"feature": "third", "assign": "<feature id>" | null}` (2026-09-28) -
     * moves a switch onto the third card ([assign] a feature id), or moves
     * it back off ([assign] null). Built as JSON, never glued.
     */
    fun postThirdBody(assign: String?): String = buildJsonObject {
        put("feature", THIRD)
        if (assign == null) put("assign", JsonNull) else put("assign", assign)
    }.toString()

    /**
     * The path for "When to suggest the bigger model"'s one write - spelled
     * out literally, not built from [PATH] by concatenation, so
     * `tools/check_parity.py` (which finds a route by its literal
     * `/api/...` text in the source) sees it as the distinct route it is.
     */
    const val SUGGEST_PATH = "/api/second-card/suggest"

    /**
     * `{"signal": "struggle"|"correction", "enabled": true|false}` for
     * [SUGGEST_PATH] - NO approval card either way (`jarvis_second_card.py`'s
     * own docstring: this only changes whether Jarvis may offer [combined]
     * on its own, never what it may do without a person's yes).
     */
    fun postSuggestBody(signal: String, enabled: Boolean): String = buildJsonObject {
        put("signal", signal)
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
