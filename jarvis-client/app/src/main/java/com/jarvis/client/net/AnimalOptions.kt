package com.jarvis.client.net

import com.jarvis.client.data.FaceTuning
import com.jarvis.client.face.FrameRateTarget
import com.jarvis.client.face.QualityTier
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * "Animal options" (the owner's decisions of 2026-09-28; docs/JARVIS-API.md
 * section 60; backend `jarvis_animal.py`, `animal.patch`): every animal
 * option in one place, and Jarvis changing any of them when asked.
 *
 * WHERE EACH ONE LIVES
 *  - "Keep the animal still" and the behaviour switches ([SWITCHES]): on the
 *    PC, shared with the desktop - one change on either device, or by asking
 *    Jarvis, changes both. `GET /api/animal` hands them over with the PC's
 *    words; `GET /api/appearance` carries the values as `animal`, so the
 *    `appearance` event this phone already follows repaints the face
 *    ([com.jarvis.client.data.AppearanceStore.animal]). Cosmetic: no card
 *    either way; turning one on waits for a live link (rule 4, as the sky's
 *    switch does), turning one off never does.
 *  - The sun, moon and weather: on the PC too ([SkySettings]), shown in the
 *    same section.
 *  - Sharpness and frame rate: this phone only ([FaceTuning]). Jarvis names
 *    a change in X-Jarvis-Route (`face_tuning`, [fromRoute]) and this phone
 *    applies it to itself with [step] - the PC's own rule
 *    (`jarvis_animal.step_device`), held equal by the contract file
 *    `animal-cases.json` (AnimalOptionsTest).
 *
 * A new behaviour is one more entry in the PC's list and in [SWITCHES]; the
 * section draws whatever the PC lists.
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM.
 */
object AnimalOptions {
    const val PATH = "/api/animal"

    const val TITLE = "Animal options"
    const val INTRO = "Everything about the animal and robot faces, in one place. You can also ask Jarvis, " +
        "like \"keep the animal still\" or \"turn off the weather\"."
    const val SHARED_TITLE = "Shared with your phone"
    const val SHARED_NOTE = "Kept on your PC: a change here, on your phone or by asking Jarvis changes both. " +
        "No approval card - these only change how the animal moves."
    const val SERIOUS_NOTE = "\"Keep the animal still\" and serious moments (an approval, an error, a crisis " +
        "answer) switch the behaviours off; calm motion makes them smaller."
    const val COMING = "Coming in the next update: saved now, and the animal starts doing it then."
    const val MISSING = "Your PC's Jarvis cannot share the animal options yet - run apply-patches.ps1 on the PC."

    /** This phone's own words for the parts only it has. */
    const val DESKTOP_SHARED = "Shared with your desktop"
    const val LOCAL_ONLY = "Kept on this phone only until your PC's Jarvis is updated."
    const val DEVICE_TITLE = "Sharpness and frame rate on this phone"
    const val DEVICE_NOTE = "Each device keeps its own: what one graphics chip can draw says nothing about " +
        "another's. They apply to every face, not only the animals."
    const val VOICE_TITLE = "The face's voice"
    const val VOICE_NOTE = "Each character face - the animals and the robot - can speak in its own voice. It " +
        "is set with Jarvis's other voices: \"Voice follows the face\", and each face's own voice, pitch and pace."
    const val CALM_NOTE = "The faces move more calmly - smaller and slower - under Motion: Calm (in More " +
        "options, further down), or while the phone asks for less animation."

    data class Switch(
        val id: String,
        val label: String,
        val detail: String,
        val default: Boolean,
        /** False: stored and shared now; the animal starts doing it in a coming update. */
        val built: Boolean,
    )

    /** The PC's list (jarvis_animal.SWITCHES), word for word - AnimalOptionsTest holds it to the fixture. */
    val SWITCHES: List<Switch> = listOf(
        Switch(
            "still", "Keep the animal still",
            "It only breathes and blinks - no looking around, gestures or little idle events. For the " +
                "animal and robot faces; the others are not changed.",
            default = false, built = true,
        ),
        Switch(
            "nods", "Listening nods",
            "Small nods in your pauses while you talk, and gestures that land at the ends of Jarvis's " +
                "sentences.",
            default = true, built = true,
        ),
        Switch(
            "focus_buddy", "Focus buddy",
            "In a focus session the animal works quietly beside you and stretches at the end. It never " +
                "sees your screen and never scolds.",
            default = true, built = true,
        ),
        Switch(
            "acks", "Small acknowledgements",
            "A small nod when Jarvis saves a fact (not while App lock or \"Hide memory lists\" is on), and " +
                "a glow when a long answer is ready.",
            default = true, built = true,
        ),
        Switch(
            "petting", "Petting",
            "Stroke the animal and it leans in. On the PC: on the Widget's face, or press and hold, then " +
                "stroke, in the Faces window (the floating face and the HUD let clicks through). On the " +
                "phone it is a long press on the face, which does not open the Brain.",
            default = true, built = true,
        ),
        Switch(
            "cute_moments", "Cute idle moments",
            "Now and then, after the face has rested a while, one of its two short cute moments plays, " +
                "then it settles back. Never during an approval or an error.",
            default = true, built = true,
        ),
        Switch(
            "seasonal", "Seasonal touches",
            "Small touches for the time of year, from the date on your device. Off by default.",
            default = false, built = true,
        ),
    )

    val DEFAULTS: Map<String, Boolean> = SWITCHES.associate { it.id to it.default }

    /** The shared values, every switch present. */
    data class Shared(val values: Map<String, Boolean> = DEFAULTS) {
        val still: Boolean get() = values["still"] == true
        fun on(id: String): Boolean = values[id] ?: DEFAULTS[id] ?: false
    }

    /** Only a real true/false is read; anything else is that switch's default. */
    fun normalise(o: JsonObject?): Shared =
        Shared(SWITCHES.associate { s -> s.id to (o?.flag(s.id) ?: s.default) })

    data class View(
        val title: String,
        val intro: String,
        val sharedNote: String,
        val seriousNote: String,
        val coming: String,
        val switches: List<Switch>,
        val shared: Shared,
    )

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.takeIf { it.isNotBlank() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull

    /** `GET /api/animal`, read - or null when it is not one (an older PC). */
    fun parse(body: JsonObject): View? {
        if (body.flag("available") == false) return null
        val values = body["values"] as? JsonObject ?: return null
        val listed = (body["switches"] as? JsonArray)?.mapNotNull { it as? JsonObject } ?: return null
        val switches = listed.mapNotNull { o ->
            val id = o.text("id") ?: return@mapNotNull null
            val known = SWITCHES.firstOrNull { it.id == id }
            Switch(
                id,
                o.text("label") ?: known?.label ?: return@mapNotNull null,
                o.text("detail") ?: known?.detail ?: "",
                o.flag("default") ?: known?.default ?: false,
                o.flag("built") ?: known?.built ?: false,
            )
        }
        val shared = Shared(
            DEFAULTS + switches.associate { s -> s.id to (values.flag(s.id) ?: s.default) },
        )
        return View(
            title = body.text("title") ?: TITLE,
            intro = body.text("intro") ?: INTRO,
            sharedNote = body.text("shared_note") ?: SHARED_NOTE,
            seriousNote = body.text("serious_note") ?: SERIOUS_NOTE,
            coming = body.text("coming") ?: COMING,
            switches = switches,
            shared = shared,
        )
    }

    /** A read that failed because this PC has no animal options. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    /** ONE change; null for an id the PC does not list. */
    fun body(id: String, on: Boolean): String? =
        if (SWITCHES.any { it.id == id }) JsonObject(mapOf(id to JsonPrimitive(on))).toString() else null

    /** What to say after a change: the PC's sentence, or the plain words of the failure. */
    fun replyLine(result: ApiResult<JsonObject>): String = when (result) {
        is ApiResult.Ok -> result.value.text("said") ?: result.value.text("error") ?: "Done."
        is ApiResult.Failed -> if (missing(result.error)) MISSING else PlainErrors.forApiError(result.error).text
    }

    // ---- What the phone keeps (its own copy, and whether the old Still moved) --

    fun encode(s: Shared): String = JsonObject(s.values.mapValues { JsonPrimitive(it.value) }).toString()

    /** [encode] read back; null when nothing was ever heard from the PC. */
    fun decode(text: String?): Shared? {
        if (text.isNullOrBlank()) return null
        val o = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }.getOrNull() ?: return null
        return normalise(o)
    }

    /**
     * Whether the animal keeps still on this phone: the PC's value once the
     * phone has heard it; before that (an older PC) this phone's own old
     * switch (`Look.stillAnimal`). An old "on" that has not reached the PC yet
     * still counts, so nothing the owner chose goes away during the move -
     * the same rule as the desktop's animal-shared.js effectiveStill.
     */
    fun effectiveStill(shared: Shared?, legacyStill: Boolean, migrated: Boolean): Boolean =
        if (shared == null) legacyStill else shared.still || (legacyStill && !migrated)

    /**
     * Whether this phone's old "on" should still be sent: the PC answered,
     * its Still is off, and no switch has been changed there yet (`changed`
     * 0) - a choice made since is newer and wins. The desktop's
     * `animal.rs still_move_needed` is the same rule.
     */
    fun stillMoveNeeded(body: JsonObject): Boolean {
        if (body.flag("available") == false) return false
        val still = (body["values"] as? JsonObject)?.flag("still") ?: return false
        val changed = (body["changed"] as? JsonPrimitive)?.takeIf { !it.isString }?.contentOrNull
            ?.toDoubleOrNull() ?: 0.0
        return !still && changed <= 0.0
    }

    // ---- Per device: the one stepping rule (jarvis_animal.step_device) --------

    private val SHARP_ORDER = listOf("low", "medium", "high", "max")
    private val RATE_STEPS = listOf("30", "60", "90", "120", "max")

    /** Every `face_tuning` value the PC may send; anything else is ignored. */
    val DEVICE_CHANGES: List<String> = listOf("sharper", "softer", "smoother", "less_smooth", "auto") +
        QualityTier.entries.map { "sharpness:${it.id}" } +
        FrameRateTarget.entries.filter { it != FrameRateTarget.AUTO }.map { "frame_rate:${it.id}" }

    data class Step(val tuning: FaceTuning, val changed: Boolean, val line: String)

    private fun sharpLabel(id: String) = QualityTier.entries.firstOrNull { it.id == id }?.label ?: id
    private fun rateLabel(id: String) = FrameRateTarget.entries.firstOrNull { it.id == id }?.label ?: id

    /**
     * The change [change] makes to [tuning], with a line using "{device}". A
     * step picks a value, so Auto adjust goes off - as a tap on a level does;
     * while it is on, a step starts from High and 60, where Auto starts.
     * Speed and Battery saver are never touched.
     */
    fun step(tuning: FaceTuning, change: String): Step {
        val q = tuning.quality.id
        val f = tuning.frameRate.id
        val auto = tuning.autoAdjust
        val baseQ = if (auto) "high" else q
        val baseF = if (auto || f == "auto") "60" else f
        fun done(nq: String, nf: String, na: Boolean, line: String): Step {
            val next = tuning.copy(
                quality = QualityTier.byId(nq), frameRate = FrameRateTarget.byId(nf), autoAdjust = na,
            )
            return Step(next, nq != q || nf != f || na != auto, line)
        }
        when {
            change == "sharper" || change == "softer" -> {
                val i = SHARP_ORDER.indexOf(baseQ) + if (change == "sharper") 1 else -1
                if (i < 0 || i >= SHARP_ORDER.size) {
                    val end = sharpLabel(baseQ)
                    return if (!auto) done(q, f, auto, "Sharpness is already $end on {device}.")
                    else done(baseQ, f, false, "Sharpness on {device}: $end.")
                }
                return done(SHARP_ORDER[i], f, false, "Sharpness on {device}: ${sharpLabel(SHARP_ORDER[i])}.")
            }
            change == "smoother" || change == "less_smooth" -> {
                var j = RATE_STEPS.indexOf(baseF).let { if (it < 0) 1 else it }
                j += if (change == "smoother") 1 else -1
                if (j < 0 || j >= RATE_STEPS.size) {
                    val end = rateLabel(baseF)
                    return if (!auto && f != "auto") done(q, f, auto, "Frame rate is already $end on {device}.")
                    else done(q, baseF, false, "Frame rate on {device}: $end.")
                }
                return done(q, RATE_STEPS[j], false, "Frame rate on {device}: ${rateLabel(RATE_STEPS[j])}.")
            }
            change == "auto" ->
                return done(q, f, true, "Auto adjust is on for {device}: it picks sharpness and frame rate.")
            change.startsWith("sharpness:") && change.removePrefix("sharpness:") in SHARP_ORDER -> {
                val v = change.removePrefix("sharpness:")
                return done(v, f, false, "Sharpness on {device}: ${sharpLabel(v)}.")
            }
            change.startsWith("frame_rate:") &&
                FrameRateTarget.entries.any { it.id == change.removePrefix("frame_rate:") } -> {
                val v = change.removePrefix("frame_rate:")
                return done(q, v, false, "Frame rate on {device}: ${rateLabel(v)}.")
            }
        }
        return Step(tuning, false, "")
    }

    /**
     * "Make the animal sharper" (X-Jarvis-Route `face_tuning`,
     * docs/JARVIS-API.md section 60): the change the PC named, or null when
     * this answer named none or named something not on the list.
     */
    fun fromRoute(header: String?): String? {
        if (header.isNullOrBlank()) return null
        val o = runCatching { JarvisJson.parseToJsonElement(header.trim()) as? JsonObject }.getOrNull()
            ?: return null
        return o.text("face_tuning")?.takeIf { it in DEVICE_CHANGES }
    }
}
