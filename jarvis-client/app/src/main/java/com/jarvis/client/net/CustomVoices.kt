package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import java.util.Locale

/**
 * Custom voices: Jarvis speaking in a voice the owner recorded
 * (docs/JARVIS-API.md section 15, `backend/jarvis_voices.py`).
 *
 * The PC does all of it - the recording is held there until an approval
 * card is answered and kept there after; the voice is made there, on its
 * processor (ZipVoice) or, with "the better voice" on, on the second
 * graphics card (F5-TTS). The phone only lists, asks and records:
 *
 * - ADD a voice: a recording of someone reading a sentence the phone SHOWS
 *   (the words sent are that sentence - the phone never turns speech into
 *   text, CLAUDE.md), or an audio file picked on the phone with its words
 *   typed by the owner. One card; nothing is kept until it is approved.
 * - SWITCH to a custom voice: one card. Back to the built-in voice: at once.
 * - DELETE a voice: at once (it only takes something away), after a
 *   confirmation on the phone.
 * - THE BETTER VOICE: ON is a card (only offered when a capable second card
 *   is there); OFF is at once.
 * - HOW FAST JARVIS SPEAKS: Slower, Normal or Faster - the PC's own choices
 *   and words (`speed`), no card either way; like every change sent to the
 *   PC, held on a stale link.
 *
 * Every card-raising request is held on a stale link (rule 4); the ones
 * that only narrow (built-in voice, delete, better voice off) always go.
 * A voice that sounds like the OWNER is refused by the PC: Jarvis speaking
 * in the owner's voice could pass its own "is it the owner?" check.
 *
 * Pure: `CustomVoicesTest` reads the PC's real answers from
 * `contract/phone-voice-cases.json` (tools/gen_phone_voice_cases.py).
 */
object CustomVoices {

    const val PATH = "/api/voice/voices"
    const val CREATE_PATH = "/api/voice/voices/create"
    const val ACTIVE_PATH = "/api/voice/voices/active"
    const val DELETE_PATH = "/api/voice/voices/delete"
    const val BETTER_PATH = "/api/voice/voices/better"
    const val SPEED_PATH = "/api/voice/voices/speed"

    /** The speed plate's heading when the PC sends none - the desktop's words. */
    const val SPEED_TITLE = "How fast Jarvis speaks"

    const val BUILTIN = "builtin"

    data class Voice(
        val id: String,
        val name: String,
        val builtin: Boolean,
        val ready: Boolean,
        val why: String,
        val seconds: Double,
        val transcript: String,
    )

    data class Better(
        val enabled: Boolean = false,
        val pending: Boolean = false,
        val canTurnOn: Boolean = false,
        val why: String = "",
        val files: Boolean = false,
        val filesWhy: String = "",
        val state: String = "off",
        val stateWhy: String = "",
        val lastWhy: String = "",
    )

    data class Pending(val kind: String, val voice: String, val name: String, val expiresIn: Int)

    /** One speaking speed the PC offers: its id, and the word shown. */
    data class SpeedChoice(val id: String, val label: String)

    /**
     * "How fast Jarvis speaks": the PC's own choices and words (a new choice
     * needs no phone release). [note] is the PC's extra line, or "".
     */
    data class Speed(
        val choice: String = "",
        val choices: List<SpeedChoice> = emptyList(),
        val title: String = SPEED_TITLE,
        val detail: String = "",
        val note: String = "",
    )

    /** One engine on the PC: can it speak, and why not. */
    data class Engine(val available: Boolean, val why: String)

    data class Last(val kind: String, val voice: String, val outcome: String, val why: String)

    /** One `say()`: which engine, how long it took, and why a custom voice was not used. */
    data class Timing(
        val engine: String,
        val voice: String,
        val chars: Int,
        val seconds: Double,
        val audioSeconds: Double,
        val fallback: String,
        val note: String,
        val failed: String,
    )

    data class Limits(
        val minSeconds: Double = 3.0,
        val maxSeconds: Double = 10.0,
        val maxClipBytes: Int = 2_900_000,
        val maxTranscriptChars: Int = 300,
        val maxNameChars: Int = 40,
        val maxVoices: Int = 20,
    )

    data class Status(
        val active: String = BUILTIN,
        val activeName: String = "Built-in voice",
        val speakingWith: String = "kokoro",
        val fallback: String = "",
        val voices: List<Voice> = emptyList(),
        /** "kokoro", the processor's engine ("zipvoice", or "pocket" if it replaced it), "f5". */
        val engines: Map<String, Engine> = emptyMap(),
        val better: Better = Better(),
        val pending: Pending? = null,
        val last: Last? = null,
        val timings: List<Timing> = emptyList(),
        val sentences: List<String> = emptyList(),
        val limits: Limits = Limits(),
        /** Null on a PC too old to have the speaking-speed setting: nothing is shown. */
        val speed: Speed? = null,
    ) {
        val custom: List<Voice> get() = voices.filter { !it.builtin }
    }

    /** What the Voices screen shows, and why when it cannot. */
    sealed interface Read {
        data object Loading : Read
        data class Loaded(val status: Status) : Read

        /** The PC has no custom voices (an older PC, or the module is missing): [why] says which. */
        data class Missing(val why: String) : Read
        data class Failed(val why: String) : Read
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

    /** `GET /api/voice/voices`, read one field at a time. Null when it is not that answer at all. */
    fun parse(o: JsonObject?): Status? {
        if (o == null || !o.flag("available") || o["voices"] !is JsonArray) return null
        val voices = (o["voices"] as JsonArray).mapNotNull { e ->
            val v = e as? JsonObject ?: return@mapNotNull null
            val id = v.str("id").ifBlank { return@mapNotNull null }
            Voice(
                id = id,
                name = v.str("name").ifBlank { id },
                builtin = v.flag("builtin") || id == BUILTIN,
                ready = v.flag("ready"),
                why = v.str("why"),
                seconds = v.num("seconds"),
                transcript = v.str("transcript"),
            )
        }
        val b = o.obj("better_voice")
        val lim = o.obj("limits")
        return Status(
            active = o.str("active").ifBlank { BUILTIN },
            activeName = o.str("active_name").ifBlank { "Built-in voice" },
            speakingWith = o.str("speaking_with"),
            fallback = o.str("fallback"),
            voices = voices,
            engines = o.obj("engines")?.entries?.mapNotNull { (k, v) ->
                val e = v as? JsonObject ?: return@mapNotNull null
                k to Engine(e.flag("available"), e.str("why"))
            }?.toMap().orEmpty(),
            better = if (b == null) {
                Better()
            } else {
                Better(
                    enabled = b.flag("enabled"),
                    pending = b.flag("pending"),
                    canTurnOn = b.flag("can_turn_on"),
                    why = b.str("why"),
                    files = b.flag("files"),
                    filesWhy = b.str("files_why"),
                    state = b.str("state").ifBlank { "off" },
                    stateWhy = b.str("state_why"),
                    lastWhy = b.obj("last")?.str("why").orEmpty(),
                )
            },
            pending = o.obj("pending")?.let {
                Pending(it.str("kind"), it.str("voice"), it.str("name"), it.int("expires_in"))
            },
            last = o.obj("last")?.let { Last(it.str("kind"), it.str("voice"), it.str("outcome"), it.str("why")) },
            timings = (o["timings"] as? JsonArray).orEmpty().mapNotNull { e ->
                val t = e as? JsonObject ?: return@mapNotNull null
                Timing(
                    t.str("engine"), t.str("voice"), t.int("chars"), t.num("seconds"),
                    t.num("audio_seconds"), t.str("fallback"), t.str("note"), t.str("failed"),
                )
            },
            sentences = (o["sentences"] as? JsonArray).orEmpty().mapNotNull {
                (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.content?.trim()?.takeIf { s -> s.isNotEmpty() }
            },
            limits = if (lim == null) {
                Limits()
            } else {
                Limits(
                    minSeconds = lim.num("min_seconds").takeIf { it > 0 } ?: 3.0,
                    maxSeconds = lim.num("max_seconds").takeIf { it > 0 } ?: 10.0,
                    maxClipBytes = lim.int("max_clip_bytes").takeIf { it > 0 } ?: 2_900_000,
                    maxTranscriptChars = lim.int("max_transcript_chars").takeIf { it > 0 } ?: 300,
                    maxNameChars = lim.int("max_name_chars").takeIf { it > 0 } ?: 40,
                    maxVoices = lim.int("max_voices").takeIf { it > 0 } ?: 20,
                )
            },
            speed = o.obj("speed")?.let { parseSpeed(it) },
        )
    }

    /** The `speed` block, or null when it offers no choice this phone can show. */
    private fun parseSpeed(sp: JsonObject): Speed? {
        val choices = (sp["choices"] as? JsonArray).orEmpty().mapNotNull { e ->
            val c = e as? JsonObject ?: return@mapNotNull null
            val id = c.str("id").ifBlank { return@mapNotNull null }
            val label = c.str("label").ifBlank { return@mapNotNull null }
            SpeedChoice(id, label)
        }
        if (choices.isEmpty()) return null
        return Speed(
            choice = sp.str("choice"),
            choices = choices,
            title = sp.str("title").ifBlank { SPEED_TITLE },
            detail = sp.str("detail"),
            note = sp.str("note"),
        )
    }

    /** The GET's answer, or why there is none, from the HTTP result. */
    fun read(result: ApiResult<JsonObject>): Read = when (result) {
        is ApiResult.Ok -> {
            val o = result.value
            if (o.flag("available").not() && o.containsKey("available")) {
                Read.Missing(
                    o.str("error").ifBlank { o.str("reason") }.ifBlank {
                        "Custom voices are not installed on your PC."
                    }.let(::sentence),
                )
            } else {
                parse(o)?.let { Read.Loaded(it) } ?: Read.Failed("Your PC's answer about voices could not be read.")
            }
        }
        is ApiResult.Failed -> when (result.error) {
            ApiError.NotFound ->
                Read.Missing("Your PC does not have custom voices yet. Run the patch script on the PC first.")
            ApiError.NotAvailable -> Read.Missing("Custom voices are not installed on your PC.")
            ApiError.BadToken -> Read.Failed("The desktop refused this phone's pairing token.")
            is ApiError.Unreachable -> Read.Failed("Could not reach your PC to ask about voices.")
            else -> Read.Failed("Your PC could not answer about voices right now.")
        }
    }

    // ------------------------------------------------------------ writing --

    /**
     * `{"name", "clip", "transcript"}`. The name and the words are the
     * owner's own text, so they are JSON-escaped; the clip is base64, which
     * needs none.
     */
    fun createBody(name: String, clip: ByteArray, transcript: String): String =
        "{\"name\":" + JarvisApi.quote(name.trim()) +
            ",\"transcript\":" + JarvisApi.quote(transcript.trim()) +
            ",\"clip\":\"" + java.util.Base64.getEncoder().encodeToString(clip) + "\"}"

    fun activeBody(id: String): String = "{\"voice\":" + JarvisApi.quote(id) + "}"

    fun deleteBody(id: String): String = "{\"voice\":" + JarvisApi.quote(id) + "}"

    fun betterBody(on: Boolean): String = "{\"enabled\":$on}"

    /** `{"speed": "<id>"}` - one of the ids the PC offered. */
    fun speedBody(id: String): String = "{\"speed\":" + JarvisApi.quote(id) + "}"

    // ------------------------------------------------------------ answers --

    /** A POST's answer, whatever the route. `error` is the PC's own sentence. */
    data class Answer(
        val code: Int,
        val ok: Boolean,
        val pending: Boolean,
        val error: String,
        val message: String,
        /** "owner_voice", "owner_check_failed", "no_voice_check", or "". */
        val refused: String,
        val active: String,
    ) {
        val accepted: Boolean get() = code in 200..299 && ok
    }

    fun answer(code: Int, body: JsonObject?): Answer {
        val b = body ?: JsonObject(emptyMap())
        return Answer(
            code = code,
            ok = b.flag("ok"),
            pending = code == 202 || (code in 200..299 && b.flag("pending")),
            error = b.str("error"),
            message = b.str("message"),
            refused = b.str("refused"),
            active = b.str("active"),
        )
    }

    /** The head line for the "it sounds like you" refusal - the owner's wording. */
    const val SOUNDS_LIKE_YOU = "This sounds like you, so Jarvis won't copy it."

    /**
     * The head line when the PC could not run the "is this your own voice?"
     * check at all (`owner_check_failed`: the recording could not be
     * compared; `no_voice_check`: the voice check is not installed). The
     * recording is refused either way. The desktop's words.
     */
    const val OWNER_CHECK_FAILED =
        "Jarvis could not make sure this is not your own voice, so it won't copy it."

    /** What to show after a POST, from the PC's answer. The PC's words are kept as they are. */
    fun answerLine(a: Answer): String = when {
        a.refused == "owner_voice" -> headed(SOUNDS_LIKE_YOU, a.error)
        a.refused == "owner_check_failed" || a.refused == "no_voice_check" -> headed(OWNER_CHECK_FAILED, a.error)
        a.error.isNotBlank() -> sentence(a.error)
        a.pending -> a.message.ifBlank { "A card is waiting." }.let {
            if (it.contains("Approve", ignoreCase = true)) it else "$it " + Approvals.WHERE
        }
        else -> a.message.ifBlank { "Done." }
    }

    /** [head], then the PC's own sentence when it sent one. */
    private fun headed(head: String, pc: String): String =
        sentence(pc).let { if (it.isEmpty()) head else "$head $it" }

    // --------------------------------------------------------------- rules --

    /**
     * Why a request cannot be sent now, or null. [raisesCard] is true for
     * adding a voice, switching to a custom one and turning the better voice
     * on: those are held on a stale link. The others only narrow what Jarvis
     * does, so they always go.
     */
    fun blocker(raisesCard: Boolean, linkBlocker: String?, status: Status?): String? = when {
        raisesCard && linkBlocker != null -> linkBlocker
        raisesCard && status?.pending != null ->
            "A voice card is already waiting. Approve or deny it first. " + Approvals.WHERE
        else -> null
    }

    /**
     * Why "Add this voice" cannot be pressed, or null. Checked here so the
     * owner fixes it while still holding the phone; the PC checks it all
     * again.
     */
    fun createBlocker(
        name: String,
        transcript: String,
        clip: ByteArray?,
        clipSeconds: Double?,
        status: Status,
        linkBlocker: String?,
    ): String? {
        val lim = status.limits
        val n = name.trim()
        val words = transcript.trim()
        return when {
            linkBlocker != null -> linkBlocker
            status.pending != null -> "A voice card is already waiting. Approve or deny it first."
            status.custom.size >= lim.maxVoices -> "There are already ${lim.maxVoices} voices. Delete one first."
            n.isEmpty() -> "Give the voice a name."
            n.length > lim.maxNameChars -> "The name is too long (at most ${lim.maxNameChars} characters)."
            status.voices.any { it.name.equals(n, ignoreCase = true) } -> "There is already a voice called \"$n\"."
            clip == null -> "Record the sentence, or pick an audio file."
            words.isEmpty() -> "Type exactly what is said in the recording."
            words.length > lim.maxTranscriptChars ->
                "The words are too long (at most ${lim.maxTranscriptChars} characters)."
            clip.size > lim.maxClipBytes ->
                "The recording is too big (at most ${String.format(Locale.US, "%.1f", lim.maxClipBytes / 1e6)} MB)."
            clipSeconds != null && clipSeconds < lim.minSeconds ->
                "The recording is too short: it needs at least ${lim.minSeconds.toInt()} seconds of speech."
            clipSeconds != null && clipSeconds > lim.maxSeconds + 2.0 ->
                "The recording is too long: at most ${lim.maxSeconds.toInt()} seconds of speech."
            else -> null
        }
    }

    /**
     * Checks a picked file is a WAV the PC can read: RIFF/WAVE, plain PCM,
     * 16- or 24-bit, 8 to 48 kHz, mono or stereo. Returns its length in
     * seconds, or the reason it cannot be used.
     */
    sealed interface WavCheck {
        data class Ok(val seconds: Double) : WavCheck
        data class Bad(val why: String) : WavCheck
    }

    fun checkWav(bytes: ByteArray, maxBytes: Int = Limits().maxClipBytes): WavCheck {
        if (bytes.size > maxBytes) {
            return WavCheck.Bad("That file is too big (at most ${String.format(Locale.US, "%.1f", maxBytes / 1e6)} MB).")
        }
        fun tag(at: Int) = if (at + 4 <= bytes.size) String(bytes, at, 4, Charsets.US_ASCII) else ""
        fun u16(at: Int) = (bytes[at].toInt() and 0xFF) or ((bytes[at + 1].toInt() and 0xFF) shl 8)
        fun u32(at: Int) = u16(at).toLong() or (u16(at + 2).toLong() shl 16)
        if (tag(0) != "RIFF" || tag(8) != "WAVE") {
            return WavCheck.Bad("That file is not a WAV recording. Pick a .wav file.")
        }
        var at = 12
        var format = -1
        var channels = 0
        var rate = 0L
        var bits = 0
        while (at + 8 <= bytes.size) {
            val id = tag(at)
            val size = u32(at + 4)
            val body = at + 8
            if (id == "fmt " && body + 16 <= bytes.size) {
                format = u16(body)
                channels = u16(body + 2)
                rate = u32(body + 4)
                bits = u16(body + 14)
                if (format == 0xFFFE && size >= 40 && body + 26 <= bytes.size) format = u16(body + 24)
            } else if (id == "data") {
                if (format == -1) return WavCheck.Bad("That WAV file is damaged (no format before the sound).")
                val usable = minOf(size, (bytes.size - body).toLong())
                val frame = channels * (bits / 8)
                return when {
                    format != 1 -> WavCheck.Bad("That WAV file is compressed. It needs to be plain (PCM) sound.")
                    bits != 16 && bits != 24 -> WavCheck.Bad("That WAV file is $bits-bit. It needs to be 16- or 24-bit.")
                    rate !in 8_000..48_000 -> WavCheck.Bad("That WAV file is $rate Hz. It needs to be 8 to 48 kHz.")
                    channels !in 1..2 -> WavCheck.Bad("That WAV file has $channels channels. It needs to be mono or stereo.")
                    frame <= 0 || usable <= 0 -> WavCheck.Bad("That WAV file has no sound in it.")
                    else -> WavCheck.Ok(usable.toDouble() / frame / rate)
                }
            }
            if (size < 0 || body + size > Int.MAX_VALUE) break
            at = body + size.toInt() + (size.toInt() and 1)
        }
        return WavCheck.Bad("That WAV file is damaged (no sound found in it).")
    }

    /**
     * An audio file the owner picked on the phone, read into memory (never
     * copied anywhere) and checked: its length, or why it cannot be used.
     */
    class Picked(val bytes: ByteArray, val seconds: Double?, val problem: String?)

    fun picked(bytes: ByteArray, maxBytes: Int = Limits().maxClipBytes): Picked =
        when (val c = checkWav(bytes, maxBytes)) {
            is WavCheck.Ok -> Picked(bytes, c.seconds, null)
            is WavCheck.Bad -> Picked(ByteArray(0), null, c.why)
        }

    /** A recording made on the phone for a voice that is too short or too long, or null. */
    fun recordingProblem(seconds: Float, limits: Limits = Limits()): String? = when {
        seconds < limits.minSeconds ->
            "That was too short: read the whole sentence, at least ${limits.minSeconds.toInt()} seconds."
        seconds > limits.maxSeconds + 2.0 ->
            "That was too long: at most ${limits.maxSeconds.toInt()} seconds of speech."
        else -> null
    }

    /** Said beside "Add a voice", always - the same words as the desktop's. */
    const val CONSENT =
        "Only add the voice of someone who has agreed to it. A recording that sounds like you is " +
            "refused. The recording stays on your PC; nothing is sent anywhere else."

    /** The heading over the recent timings ([timingLines]) - the desktop's words. */
    const val TIMINGS_TITLE = "How long speaking took"

    // --------------------------------------------------------------- words --

    /** The engine, in plain words. */
    fun engineWords(engine: String): String = when (engine) {
        "kokoro" -> "the built-in voice (Kokoro, on your PC)"
        "zipvoice" -> "ZipVoice, on your PC's processor"
        // Built, not switched on: it would REPLACE ZipVoice if the owner's
        // bake-off says so - then the PC names it here, never beside ZipVoice.
        "pocket" -> "Pocket TTS, on your PC's processor"
        "f5" -> "the better voice (F5-TTS, on the second graphics card)"
        "none" -> "nothing - no voice could speak"
        "" -> "not known"
        else -> engine
    }

    /** One line: which voice Jarvis speaks in, and with what. */
    fun nowLine(s: Status): String =
        if (s.active == BUILTIN) {
            "Jarvis speaks in its built-in voice."
        } else {
            "Jarvis speaks in \"${s.activeName}\", made by ${engineWords(s.speakingWith)}."
        }

    /** Why the built-in voice is used instead of the chosen one, or null. */
    fun fallbackLine(s: Status): String? =
        s.fallback.takeIf { it.isNotBlank() && s.active != BUILTIN }
            ?.let { "Jarvis is using its built-in voice instead, because " + it.trim().trimEnd('.') + "." }

    /** A card is waiting: one line, or null. */
    fun pendingLine(s: Status): String? {
        val p = s.pending ?: return null
        val what = when (p.kind) {
            "create" -> "to add \"${p.name}\""
            "switch" -> "to switch to \"${p.name}\""
            else -> "for a voice"
        }
        return "Waiting for your approval $what. " + Approvals.WHERE
    }

    /** How the last voice card ended - the PC's sentence, as it is. */
    fun lastLine(s: Status): String? = s.last?.why?.takeIf { it.isNotBlank() }

    /**
     * Each engine, one line: ready, or the PC's reason it is not. F5-TTS
     * ("the better voice") says its state, which is what the owner can act on.
     */
    fun engineLines(s: Status): List<String> {
        fun line(label: String, key: String): String {
            val e = s.engines[key] ?: return "$label: not reported by your PC."
            return "$label: " + if (e.available) "ready." else sentence(e.why.ifBlank { "not available" })
        }
        // The one engine on the processor the PC reports: ZipVoice today.
        val processor = if ("pocket" in s.engines) "pocket" else "zipvoice"
        return listOf(
            line("Built-in voice (Kokoro)", "kokoro"),
            line(engineWords(processor), processor),
            "Better voice (F5-TTS), on the second graphics card: " +
                sentence(s.better.stateWhy.ifBlank { s.better.state }),
        )
    }

    /** One line per recent `say()`, newest first. Never the text - the PC never sends it. */
    fun timingLines(s: Status, max: Int = 5): List<String> = s.timings.takeLast(max).reversed().map { t ->
        val head = when (t.engine) {
            "none" -> "Nothing was said"
            else -> engineName(t.engine)
        }
        buildString {
            append(head)
            if (t.engine != "none") {
                append(": ").append(t.chars).append(" characters, ready in ")
                append(String.format(Locale.US, "%.1f", t.seconds)).append(" s for ")
                append(String.format(Locale.US, "%.1f", t.audioSeconds)).append(" s of speech")
            }
            if (t.failed.isNotBlank()) append(" - ").append(t.failed.trimEnd('.'))
            if (t.fallback.isNotBlank()) append(" - built-in voice used because ").append(t.fallback.trimEnd('.'))
            if (t.note.isNotBlank()) append(" - ").append(t.note.trimEnd('.'))
            append(".")
        }
    }

    private fun engineName(engine: String): String = when (engine) {
        "kokoro" -> "Built-in voice"
        "zipvoice" -> "ZipVoice"
        "pocket" -> "Pocket TTS"
        "f5" -> "Better voice (F5-TTS)"
        else -> engine.replaceFirstChar { it.uppercase() }
    }

    /** "5.3 s" - always a dot. */
    fun length(seconds: Double): String = String.format(Locale.US, "%.1f s", seconds)

    /** What deleting [v] does, asked before it is done. */
    fun deleteQuestion(v: Voice, s: Status): String =
        "Delete the voice \"${v.name}\"? Its recording is deleted from your PC and cannot be " +
            "brought back." + (if (s.active == v.id) " Jarvis goes back to its built-in voice." else "")

    /** The better voice's switch: the line under it. */
    fun betterLine(s: Status): String {
        val b = s.better
        return when {
            b.pending -> "Waiting for your approval to turn it on. " + Approvals.WHERE
            b.enabled -> sentence(b.stateWhy.ifBlank { "On." })
            !b.canTurnOn -> sentence(b.why.ifBlank { "It needs a capable second graphics card." })
            else -> sentence(b.why)
        }
    }

    /** The PC's fragment as a sentence: first letter raised, a full stop at the end. */
    fun sentence(s: String): String {
        val t = s.trim()
        if (t.isEmpty()) return t
        val raised = t.replaceFirstChar { it.uppercase() }
        return if (raised.last() in ".!?") raised else "$raised."
    }
}
