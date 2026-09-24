package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull

/**
 * The stricter voice check (docs/JARVIS-API.md section 16), as the PC
 * reports it in `GET /api/voice/status` and answers it on
 * `POST /api/voice/enroll`: very strict or balanced, whether private answers
 * may be read aloud, training in rounds, the guided repeat test, and how
 * often the owner has had to say something twice.
 *
 * WHY THIS IS READ BY HAND, not by adding fields to [VoiceStatus]. Two
 * reasons, both about not breaking what already works:
 *
 * 1. `VoiceStatus` is what decides whether the talk button shows. A decode
 *    that fails there hides the button (the refusing default). Several of
 *    the new fields are sent only sometimes, some as `null` - so here every
 *    field is read on its own, and one odd value costs that value, never
 *    the talk button.
 * 2. `backend/test_voice_contract.py` checks that the PC sends every field
 *    `VoiceModels.kt` declares. `measure_last`, `kind` and `setting` are sent
 *    only after a test or while a card waits, so declaring them there would
 *    fail that suite for a correct PC.
 *
 * Everything here is pure (no Android), so `VoiceStrictTest` reads the PC's
 * real answers from `contract/phone-voice-cases.json`
 * (tools/gen_phone_voice_cases.py) - no shape here is typed to suit this
 * client.
 */
object VoiceStrict {

    const val VERY_STRICT = "very_strict"
    const val BALANCED = "balanced"
    const val PRIVATE_ON_SCREEN = "private_on_screen"
    const val VOICE_IS_ENOUGH = "voice_is_enough"
    /** Answers that use what Jarvis remembers (the owner's choice, 2026-09-24): aloud by default. */
    const val MEMORY_ALOUD = "memory_aloud"
    const val MEMORY_ON_SCREEN = "memory_on_screen"
    /**
     * Answers that use a SENSITIVE saved fact (the owner's decision,
     * 2026-09-24): kept on screen by default, even when memories are read
     * aloud; "read aloud" is the looser choice and asks first.
     */
    const val SENSITIVE_ON_SCREEN = "sensitive_on_screen"
    const val SENSITIVE_ALOUD = "sensitive_aloud"

    /** The `mode`s that change a setting, and what each value is called on the wire. */
    const val STRICTNESS = "strictness"
    const val PRIVACY = "privacy"
    const val MEMORY = "memory"
    const val SENSITIVE_MEMORY = "sensitive_memory"

    /** `repeat.very_strict` / `repeat.balanced` - since the PC's voice module started. */
    data class Counts(
        val accepted: Int = 0,
        val refused: Int = 0,
        val tooShort: Int = 0,
        val refusedThenAccepted: Int = 0,
    )

    /** One setting's result in the guided repeat test. */
    data class Tally(val passed: Int = 0, val of: Int = 0, val tooShort: Int = 0)

    /** The guided test's result: both settings, from the owner's own sentences. */
    data class Measured(
        val clips: Int = 0,
        val strongModel: Boolean = false,
        val veryStrict: Tally = Tally(),
        val balanced: Tally = Tally(),
    )

    /** A clip the PC left out of the voice print: round, and clip counted from 1 in it. */
    data class Outlier(val round: Int, val clip: Int)

    /** A round the PC is holding in memory, before the card. */
    data class HeldRound(val round: Int, val condition: String, val clips: Int, val seconds: Double)

    /** `training.session`: rounds held on the PC, no card yet. Counts only - never audio. */
    data class Session(
        val mic: String = "",
        val add: Boolean = false,
        val rounds: List<HeldRound> = emptyList(),
        val clips: Int = 0,
        val expiresIn: Int = 0,
    )

    /** How the last voice card (a training, or a setting) ended - `training.last`. */
    data class Last(
        val outcome: String = "",
        val reason: String = "",
        val samples: Int = 0,
        val added: Boolean = false,
        val outliers: List<Outlier> = emptyList(),
        val setting: String = "",
        val value: String = "",
    )

    /** The PC's limits for a training (`training.limits`). Today's numbers are the defaults. */
    data class Limits(
        val minClips: Int = 3,
        val maxClips: Int = 12,
        val maxTotalSeconds: Double = 80.0,
        val rounds: Int = 3,
        val measureMaxClips: Int = 20,
        val sessionSeconds: Double = 900.0,
    )

    /**
     * Everything the phone's voice screens read about the stricter check.
     * The defaults are an older PC's: none of the new modes, no settings.
     */
    data class View(
        /** "very_strict", "balanced", or "" from a PC older than the stricter check. */
        val strictness: String = "",
        val privacy: String = "",
        /** "memory_aloud", "memory_on_screen", or "" from a PC older than that setting. */
        val memory: String = "",
        /**
         * "sensitive_on_screen", "sensitive_aloud", or "" from a PC older than
         * that setting (the screen then does not offer it). Any other value
         * the PC sends is read as the strict one.
         */
        val sensitiveMemory: String = "",
        val voiceIsEnoughAllowed: Boolean = false,
        /** A spoken command needs at least this many seconds of speech (0 = not said). */
        val minCommandSeconds: Double = 0.0,
        /** The PC understands `mode: train` (rounds, add, finish, cancel). */
        val rounds: Boolean = false,
        /** The PC understands `mode: strictness` and `mode: privacy`. */
        val settings: Boolean = false,
        /** The PC understands `mode: measure`. */
        val measure: Boolean = false,
        /** "strong", "small", or "" - which voice-ID model very strict uses. */
        val veryStrictModel: String = "",
        val strongInstalled: Boolean = false,
        val smallInstalled: Boolean = false,
        val veryStrict: Counts = Counts(),
        val balanced: Counts = Counts(),
        val repeatWindowSeconds: Double = 10.0,
        val session: Session? = null,
        val measureLast: Measured? = null,
        /** While a voice card waits: "enroll", "threshold" or "setting". */
        val pendingKind: String = "",
        /** While a setting card waits: which setting, and the value it would set. */
        val pendingSetting: String = "",
        val pendingValue: String = "",
        val last: Last? = null,
        /** What each round asks for, from the PC ("1" -> "normal, close to the microphone"). */
        val roundAsks: Map<Int, String> = emptyMap(),
        val limits: Limits = Limits(),
        /** `gate.note`: the PC's own words about the check. Shown as it is. */
        val note: String = "",
    ) {
        val isVeryStrict: Boolean get() = strictness == VERY_STRICT
        val isBalanced: Boolean get() = strictness == BALANCED
    }

    // ------------------------------------------------------------ reading --

    private fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject

    private fun JsonObject.str(key: String): String =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content?.trim().orEmpty()

    private fun JsonObject.flag(key: String): Boolean =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull ?: false

    private fun JsonObject.int(key: String): Int {
        val p = (this[key] as? JsonPrimitive)?.takeIf { !it.isString } ?: return 0
        return p.intOrNull ?: p.doubleOrNull?.takeIf { it.isFinite() }?.toInt() ?: 0
    }

    private fun JsonObject.num(key: String): Double {
        val p = (this[key] as? JsonPrimitive)?.takeIf { !it.isString } ?: return 0.0
        return p.doubleOrNull?.takeIf { it.isFinite() } ?: 0.0
    }

    private fun counts(o: JsonObject?): Counts = if (o == null) {
        Counts()
    } else {
        Counts(o.int("accepted"), o.int("refused"), o.int("too_short"), o.int("refused_then_accepted"))
    }

    private fun tally(o: JsonObject?): Tally =
        if (o == null) Tally() else Tally(o.int("passed"), o.int("of"), o.int("too_short"))

    /** `measure_last`, or the guided test's own 200 answer - the same keys. */
    fun measured(o: JsonObject?): Measured? {
        if (o == null || o["very_strict"] !is JsonObject) return null
        return Measured(o.int("clips"), o.flag("strong_model"), tally(o.obj("very_strict")), tally(o.obj("balanced")))
    }

    private fun outliers(e: JsonElement?): List<Outlier> =
        (e as? JsonArray).orEmpty().mapNotNull { row ->
            val o = row as? JsonObject ?: return@mapNotNull null
            val r = o.int("round")
            val c = o.int("clip")
            if (r > 0 && c > 0) Outlier(r, c) else null
        }

    /** `training.session`, or a 409's `session` - the same shape. */
    fun session(o: JsonObject?): Session? {
        if (o == null) return null
        val rounds = (o["rounds"] as? JsonArray).orEmpty().mapNotNull { row ->
            val r = row as? JsonObject ?: return@mapNotNull null
            HeldRound(r.int("round"), r.str("condition"), r.int("clips"), r.num("seconds"))
        }
        return Session(o.str("mic"), o.flag("add"), rounds, o.int("clips"), o.int("expires_in"))
    }

    /**
     * `gate.sensitive_memory` as the screen reads it: "" (an older PC - not
     * offered) stays "", the two known values stay, and anything else is the
     * strict one - never read as "aloud" by accident.
     */
    fun sensitiveMemory(raw: String): String = when (raw) {
        "" -> ""
        SENSITIVE_ALOUD -> SENSITIVE_ALOUD
        else -> SENSITIVE_ON_SCREEN
    }

    /** Reads the stricter check out of a whole `/api/voice/status` body. Never throws. */
    fun parse(status: JsonObject?): View {
        val gate = status?.obj("gate") ?: return View()
        val settings = gate.obj("settings")
        val models = gate.obj("models")
        val repeat = gate.obj("repeat")
        val training = gate.obj("training")
        val last = training?.obj("last")
        val limits = training?.obj("limits")
        val asks = training?.obj("round_asks")?.entries?.mapNotNull { (k, v) ->
            val n = k.toIntOrNull() ?: return@mapNotNull null
            val words = (v as? JsonPrimitive)?.takeIf { it.isString }?.content?.trim().orEmpty()
            if (words.isEmpty()) null else n to words
        }?.toMap().orEmpty()
        return View(
            strictness = gate.str("strictness"),
            privacy = gate.str("privacy"),
            memory = gate.str("memory"),
            sensitiveMemory = sensitiveMemory(gate.str("sensitive_memory").ifEmpty {
                settings?.str("sensitive_memory").orEmpty()
            }),
            voiceIsEnoughAllowed = settings?.flag("voice_is_enough_allowed") ?: false,
            minCommandSeconds = settings?.num("min_command_seconds") ?: 0.0,
            rounds = training?.flag("rounds") ?: false,
            settings = training?.flag("settings") ?: false,
            measure = training?.flag("measure") ?: false,
            veryStrictModel = models?.str("very_strict_model").orEmpty(),
            strongInstalled = models?.obj("strong")?.flag("installed") ?: false,
            smallInstalled = models?.obj("small")?.flag("installed") ?: false,
            veryStrict = counts(repeat?.obj(VERY_STRICT)),
            balanced = counts(repeat?.obj(BALANCED)),
            repeatWindowSeconds = repeat?.num("window_seconds")?.takeIf { it > 0 } ?: 10.0,
            session = session(training?.obj("session")),
            measureLast = measured(training?.obj("measure_last")),
            pendingKind = if (training?.flag("pending") == true) training.str("kind") else "",
            pendingSetting = training?.obj("setting")?.str("name").orEmpty(),
            pendingValue = training?.obj("setting")?.str("value").orEmpty(),
            last = last?.let {
                Last(
                    outcome = it.str("outcome"),
                    reason = it.str("reason"),
                    samples = it.int("samples"),
                    added = it.flag("added"),
                    outliers = outliers(it["outliers"]),
                    setting = it.str("setting"),
                    value = it.str("value"),
                )
            },
            roundAsks = asks,
            limits = if (limits == null) {
                Limits()
            } else {
                Limits(
                    minClips = limits.int("min_clips").takeIf { it > 0 } ?: 3,
                    maxClips = limits.int("max_clips").takeIf { it > 0 } ?: 12,
                    maxTotalSeconds = limits.num("max_total_seconds").takeIf { it > 0 } ?: 80.0,
                    rounds = limits.int("rounds").takeIf { it > 0 } ?: 3,
                    measureMaxClips = limits.int("measure_max_clips").takeIf { it > 0 } ?: 20,
                    sessionSeconds = limits.num("session_seconds").takeIf { it > 0 } ?: 900.0,
                )
            },
            note = gate.str("note"),
        )
    }

    /**
     * `/api/voice/status`, read once into both halves: the [VoiceStatus] the
     * talk button and the Checks screen have always read, and the [View]
     * above. The same rules as the plain read it replaces - `available:
     * false` is "the voice part is not running", not a status to show.
     */
    fun read(body: JsonObject): ApiResult<Pair<VoiceStatus, View>> {
        if ((body["available"] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == false) {
            return ApiResult.Failed(ApiError.NotAvailable)
        }
        val status = runCatching { JarvisJson.decodeFromJsonElement(VoiceStatus.serializer(), body) }
            .getOrElse { return ApiResult.Failed(ApiError.Malformed(it.message ?: "bad voice status")) }
        return ApiResult.Ok(status to parse(body))
    }

    // ------------------------------------------------------------ writing --

    /**
     * One training round: `{"mode": "train", "round": n, "mic", "clips",
     * "add", "finish"}`. Built by hand like [enrollRequestBody], for the same
     * reasons (base64 needs no escaping; a few megabytes are not copied
     * through a JSON tree). `mic` is this app's own fixed word.
     */
    fun trainBody(round: Int, clips: List<ByteArray>, mic: String, add: Boolean, finish: Boolean): String {
        val enc = java.util.Base64.getEncoder()
        val head = "{\"mode\":\"train\",\"round\":$round,\"mic\":\"$mic\",\"add\":$add,\"finish\":$finish,\"clips\":["
        return clips.joinToString(prefix = head, postfix = "]}", separator = ",") {
            "\"" + enc.encodeToString(it) + "\""
        }
    }

    /** Drops every round the PC is holding. Never raises a card, so it is never held back. */
    const val CANCEL_BODY = "{\"mode\":\"train\",\"cancel\":true}"

    /** Each setting's two values, strict first. */
    private val VALUES: Map<String, Set<String>> = mapOf(
        STRICTNESS to setOf(VERY_STRICT, BALANCED),
        PRIVACY to setOf(PRIVATE_ON_SCREEN, VOICE_IS_ENOUGH),
        MEMORY to setOf(MEMORY_ON_SCREEN, MEMORY_ALOUD),
        SENSITIVE_MEMORY to setOf(SENSITIVE_ON_SCREEN, SENSITIVE_ALOUD),
    )

    /**
     * `{"mode": "strictness" | "privacy" | "memory" | "sensitive_memory",
     * "value": ...}`. Only this app's fixed words go in, and only a value of
     * that setting's own.
     */
    fun settingBody(setting: String, value: String): String {
        val values = requireNotNull(VALUES[setting]) { "not a voice setting: $setting" }
        require(value in values) { "not a value of $setting: $value" }
        return "{\"mode\":\"$setting\",\"value\":\"$value\"}"
    }

    /** Whether choosing [value] for [setting] LOOSENS it - which is the one that asks first. */
    fun isLoosening(setting: String, value: String): Boolean =
        (setting == STRICTNESS && value == BALANCED) || (setting == PRIVACY && value == VOICE_IS_ENOUGH) ||
            (setting == MEMORY && value == MEMORY_ALOUD) ||
            (setting == SENSITIVE_MEMORY && value == SENSITIVE_ALOUD)

    // ------------------------------------------------------------ answers --

    /**
     * What `POST /api/voice/enroll` said to a round, a cancel, a setting or
     * a test, read the same way whatever the mode. The PC's sentences are
     * kept as they are: every refusal has `error`, written for the owner.
     */
    data class Answer(
        val code: Int,
        val ok: Boolean,
        /** A card is up (a 202). */
        val pending: Boolean,
        val error: String,
        val message: String,
        /** The PC's round answer: the rounds it now holds. */
        val held: Session? = null,
        val nextRound: Int = 0,
        /** A setting answer: whether anything changed. */
        val changed: Boolean = false,
        /** A 409 because a training is held from elsewhere: what it holds. */
        val session: Session? = null,
        /** A test answer's counts. */
        val measured: Measured? = null,
        val needsModel: Boolean = false,
    ) {
        /** The request did what it asked, or a card is up for it. */
        val accepted: Boolean get() = code in 200..299 && error.isEmpty() && (ok || pending)
    }

    fun answer(code: Int, body: JsonObject?): Answer {
        val b = body ?: JsonObject(emptyMap())
        return Answer(
            code = code,
            ok = b.flag("ok"),
            pending = code == 202 || b.flag("pending") && code in 200..299,
            error = b.str("error"),
            message = b.str("message"),
            held = session(b.obj("held")),
            nextRound = b.int("next_round"),
            changed = b.flag("changed"),
            session = session(b.obj("session")),
            measured = if (code in 200..299) measured(b) else null,
            needsModel = b.flag("needs_model"),
        )
    }
}
