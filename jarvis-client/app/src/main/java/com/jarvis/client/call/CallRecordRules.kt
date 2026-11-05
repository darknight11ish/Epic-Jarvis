package com.jarvis.client.call

import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * Recording a phone call: the whole decision, in one pure file.
 *
 * WHAT THIS FEATURE IS, and the one thing it cannot do. The owner says
 * *"record call"* to Jarvis. The phone arms, waits for a call to start,
 * records the microphone while the call is on speaker, uploads the pieces to
 * the PC as they are made, and the PC turns them into words, dates them,
 * works out who was speaking and writes ONE note in the owner's Obsidian
 * vault. The phone never turns speech into words (a standing rule: a client
 * must not do speech-to-text) and never writes to the vault - it cannot even
 * see it. It sends PCM and a date; everything else is the PC's.
 *
 * WHY IT IS THE MICROPHONE AND NOT THE CALL. Android does not let a normal
 * app capture a call's own audio: `VOICE_CALL` is a privileged source, and a
 * sideloaded app cannot hold it. So the recording is the MICROPHONE while the
 * call is on speaker - both voices are captured acoustically, through the
 * air. That is the "speaker path", and it is why:
 *  - the recorder is opened as `UNPROCESSED` where the platform allows it and
 *    `MIC` otherwise. **Never `VOICE_COMMUNICATION`**: its echo canceller
 *    removes exactly the far end (the other person's voice) it was built to
 *    remove, so a call recorded on that source would be one-sided;
 *  - the service tries to put the call on speaker
 *    ([CallRecordRules.TRY_SPEAKER]) and, when the platform refuses, the
 *    notification says [SPEAKER_ASK] rather than claiming both sides were
 *    captured. A recording taken down the earpiece is the owner's voice and
 *    almost nothing of the other person's, and this app must never say
 *    otherwise.
 *
 * THE STATES. OFF -> ARMED -> RECORDING -> SENDING -> OFF. Every way a
 * recording can end (the call ends, the owner presses Stop, the phone's
 * battery is low, the headset is unplugged, the app is shut down) goes through
 * [Phase.SENDING], which is "the audio is finished and is being (or waiting to
 * be) uploaded": the pieces are already on disk, so nothing is lost by the
 * phone being killed at that moment - the queue is resumed next time.
 *
 * Pure Kotlin, no Android types, so `CallRecordRulesTest` runs every state,
 * every ending and the chunk arithmetic on a plain JVM. The service
 * (`service/CallRecordService.kt`) is only the executor of these [Effect]s.
 */
object CallRecordRules {

    // ------------------------------------------------------- the contract ---

    /** The four numbers the frozen PC contract names. */
    const val SAMPLE_RATE = 16_000
    const val CHANNELS = 1
    const val FORMAT = "s16le"
    const val DEVICE = "phone"

    /** 16 kHz, mono, PCM16LE: two bytes per sample, always. */
    const val BYTES_PER_SAMPLE = 2

    /**
     * The size of one uploaded piece: 64 KiB of PCM, inside the contract's
     * "~32-64 KB". It is a whole number of samples (32,768) and a whole number
     * of milliseconds (2,048 ms exactly), so a chunk boundary never splits a
     * sample and the running total always converts to a whole duration.
     */
    const val CHUNK_BYTES = 64 * 1024

    /** How many samples one chunk holds - 32,768. */
    const val CHUNK_SAMPLES = CHUNK_BYTES / BYTES_PER_SAMPLE

    /** What the phone says it is doing, in the contract's own words. */
    const val CONSENT_NOTICE = "on"

    /** The three routes, exactly as the PC declared them. */
    const val START_PATH = "/api/call/recording/start"
    const val CHUNK_PATH = "/api/call/recording/chunk"
    const val FINISH_PATH = "/api/call/recording/finish"

    /** The chat directive's key, inside the answer's `X-Jarvis-Route` header. */
    const val DIRECTIVE_KEY = "call_record"
    const val ACTION_ARM = "arm"
    const val ACTION_STOP = "stop"

    /**
     * Put the call on speaker before recording: `setCommunicationDevice` on
     * API 31+, `setSpeakerphoneOn(true)` below it. Decided here so the service
     * holds no judgement of its own, and so a test can see the intent without
     * an AudioManager.
     */
    const val TRY_SPEAKER = true

    /** The audio source to ask for first; echoed in the notification's honesty line. */
    const val SOURCE_PREFERRED = "UNPROCESSED"

    /** The source to fall back to when the platform will not open [SOURCE_PREFERRED]. */
    const val SOURCE_FALLBACK = "MIC"

    /**
     * The source that must never be used, named here so a source-pin test can
     * hold the reason next to the code: its echo canceller removes the far
     * end of the call, which is the one voice this feature exists to keep.
     */
    const val SOURCE_REFUSED = "VOICE_COMMUNICATION"

    // ------------------------------------------------------------- phases ---

    /**
     * Where the recorder is. [SENDING] is not "still recording": the
     * microphone is closed by then and only the upload is left.
     */
    enum class Phase {
        /** Nothing armed, no microphone, nothing waiting. */
        OFF,

        /** Armed by the owner (`"record call"`): the next call starts by itself. */
        ARMED,

        /** A call is on: the microphone is open and chunks are going up. */
        RECORDING,

        /** The audio is finished; the pieces are on disk until the PC takes them. */
        SENDING,
    }

    /** Everything that can happen to a recording. */
    enum class Event {
        /** `"call_record": {"action": "arm"}` from a reply, or the plate's button. */
        ARM,

        /** `"call_record": {"action": "stop"}`, or "Disarm" while only armed. */
        DISARM,

        /** `AudioManager.mode` became `MODE_IN_CALL` or `MODE_IN_COMMUNICATION`. */
        CALL_START,

        /** The audio mode went back to normal: the call is over. */
        CALL_END,

        /** The owner pressed Stop on the notification or the plate. */
        OWNER_STOP,

        /** `ACTION_BATTERY_LOW` - a long call can outlast the battery. */
        LOW_BATTERY,

        /** The headset was unplugged (`ACTION_AUDIO_BECOMING_NOISY`). */
        HEADSET_UNPLUGGED,

        /** The app is going away: finish what is held and leave the queue. */
        APP_SHUTDOWN,

        /** The platform refused the microphone (or the permission was taken away). */
        MIC_REFUSED,

        /** The PC took the finished recording (`finish` answered `ok: true`). */
        SENT,

        /** The PC could not be reached: keep the audio, say so, send it later. */
        UPLOAD_WAITING,

        /**
         * The recording was under a second. The PC refuses an empty recording
         * and nothing a note could be made from was said, so this is the ONE
         * way audio is deleted - and it is said out loud when it happens.
         */
        TOO_SHORT,
    }

    /**
     * What the executor must do. One list per step, in order; the service runs
     * them and holds no rules of its own.
     */
    enum class Effect {
        /** Claim the microphone for call recording (voice/MicOwner.kt). */
        CLAIM_MIC,

        /** Let the microphone go: the other capture paths may open it again. */
        RELEASE_MIC,

        /** Start the foreground service (armed, with its notification). */
        START_SERVICE,

        /** Open the microphone and begin cutting chunks. */
        START_CAPTURE,

        /** Close the microphone. The pieces already cut are kept. */
        STOP_CAPTURE,

        /** Upload what is left, then `POST .../finish`. */
        FINISH,

        /** Keep the audio and retry later - never throw a recording away. */
        KEEP_QUEUE,

        /** Delete the one recording that is too short to make a note from. The only delete there is. */
        DISCARD,

        /** Drop the foreground notification and stop the service. */
        STOP_SERVICE,

        /** "Call recording armed" - said once, in the notification and on the plate. */
        SAY_ARMED,

        /** "Recording - tell the other person." */
        SAY_RECORDING,

        /** "Call recording stopped." */
        SAY_STOPPED,

        /** "Sent to your PC." */
        SAY_SENT,

        /** "Kept on this phone. It will send when your PC answers." */
        SAY_WAITING,
    }

    /**
     * Everything the recorder knows. [startedAtMs] is the call's start
     * (wall-clock, milliseconds since the epoch) - the date the PC turns into
     * the note's name. [bytes] is what has been cut so far, which is what
     * `finish` reports as the duration.
     */
    data class State(
        val phase: Phase = Phase.OFF,
        val startedAtMs: Long = 0L,
        val session: String? = null,
        val bytes: Long = 0L,
    ) {
        val recording: Boolean get() = phase == Phase.RECORDING
        val armed: Boolean get() = phase == Phase.ARMED
        val busy: Boolean get() = phase != Phase.OFF

        /** Seconds recorded so far, for `finish.duration_sec` - never more than was cut. */
        val durationSec: Long get() = bytes / BYTES_PER_SAMPLE / SAMPLE_RATE
    }

    /** One step: the new state, and what to do to reach it. */
    data class Step(val state: State, val effects: List<Effect> = emptyList())

    /**
     * THE TABLE. One function, every transition, so the JVM tests can hold all
     * of them and the service cannot invent a sixth way to end.
     *
     * Anything not named here does nothing at all (the same state, no
     * effects): a Stop on an idle recorder must not start a service, and a
     * duplicate Arm from a second chat answer must not open two.
     */
    fun next(state: State, event: Event): Step = when (state.phase) {
        Phase.OFF -> when (event) {
            Event.ARM -> Step(
                state.copy(phase = Phase.ARMED),
                listOf(Effect.CLAIM_MIC, Effect.START_SERVICE, Effect.SAY_ARMED),
            )
            else -> Step(state)
        }

        Phase.ARMED -> when (event) {
            // The call is on: the date starts here, and so does the audio.
            Event.CALL_START -> Step(
                state.copy(phase = Phase.RECORDING, bytes = 0L),
                listOf(Effect.START_CAPTURE, Effect.SAY_RECORDING),
            )
            // Already armed: nothing to do, and no second notification.
            Event.ARM -> Step(state)
            Event.DISARM, Event.OWNER_STOP -> Step(
                State(),
                listOf(Effect.RELEASE_MIC, Effect.STOP_SERVICE, Effect.SAY_STOPPED),
            )
            // The platform refused the microphone before any call: armed is a
            // promise this phone can no longer keep, so it lets it go.
            Event.MIC_REFUSED -> Step(
                State(),
                listOf(Effect.RELEASE_MIC, Effect.STOP_SERVICE, Effect.SAY_STOPPED),
            )
            else -> Step(state)
        }

        Phase.RECORDING -> when (event) {
            Event.CALL_START -> Step(state)
            // Every ending is the same ending: close the microphone, finish
            // the upload. A recording is never thrown away, and the reason it
            // stopped is in the words beside it, not in a different path.
            Event.CALL_END, Event.OWNER_STOP, Event.LOW_BATTERY, Event.HEADSET_UNPLUGGED ->
                Step(state.copy(phase = Phase.SENDING), END_EFFECTS)
            Event.APP_SHUTDOWN -> Step(
                state.copy(phase = Phase.SENDING),
                listOf(Effect.STOP_CAPTURE, Effect.KEEP_QUEUE),
            )
            // Under a second: nothing a note could be made from. The one
            // ending that deletes audio, and the words say so.
            Event.TOO_SHORT -> Step(
                State(),
                listOf(Effect.STOP_CAPTURE, Effect.DISCARD, Effect.RELEASE_MIC, Effect.STOP_SERVICE, Effect.SAY_STOPPED),
            )
            // The microphone was taken away mid-call (a permission revoked,
            // another app, Android's own call UI). What was cut is kept and
            // sent; the PC is still able to make the note.
            Event.MIC_REFUSED -> Step(state.copy(phase = Phase.SENDING), END_EFFECTS)
            Event.DISARM -> Step(state)
            else -> Step(state)
        }

        Phase.SENDING -> when (event) {
            Event.SENT -> Step(
                State(),
                listOf(Effect.RELEASE_MIC, Effect.STOP_SERVICE, Effect.SAY_SENT),
            )
            Event.UPLOAD_WAITING -> Step(
                state,
                listOf(Effect.KEEP_QUEUE, Effect.RELEASE_MIC, Effect.STOP_SERVICE, Effect.SAY_WAITING),
            )
            Event.APP_SHUTDOWN -> Step(state, listOf(Effect.KEEP_QUEUE))
            // A Stop while the upload is running cannot un-send what the PC
            // already has, and it must not throw the rest away: it keeps the
            // rest on this phone and says so.
            Event.OWNER_STOP -> Step(
                state,
                listOf(Effect.KEEP_QUEUE, Effect.RELEASE_MIC, Effect.STOP_SERVICE, Effect.SAY_WAITING),
            )
            // While the upload of a new recording is running, arming again is
            // refused by the service, not queued here: one at a time.
            else -> Step(state)
        }
    }

    /** The effects of every ending: close the microphone, then finish the upload. */
    private val END_EFFECTS = listOf(Effect.STOP_CAPTURE, Effect.FINISH)

    // ------------------------------------------------------- the arithmetic ---

    /** Bytes in [samples] samples of mono PCM16. */
    fun bytesOf(samples: Int): Int = samples * BYTES_PER_SAMPLE

    /** The whole seconds in a byte count, truncated - what `finish.duration_sec` says. */
    fun durationSec(bytes: Long): Long = bytes / BYTES_PER_SAMPLE / SAMPLE_RATE

    /** The elapsed time as a notification shows it: `00:04:12`. */
    fun clock(ms: Long): String {
        val total = (ms / 1000L).coerceAtLeast(0L)
        val hours = total / 3600L
        val minutes = (total % 3600L) / 60L
        val seconds = total % 60L
        return "%02d:%02d:%02d".format(hours, minutes, seconds)
    }

    /** How many samples [ms] of audio holds at [SAMPLE_RATE]. */
    fun samplesForMs(ms: Long): Int = (ms * SAMPLE_RATE / 1000L).toInt()

    /**
     * The date the PC turns into the note's name: ISO 8601 with the phone's own
     * offset (`2026-11-04T13:41:39-08:00`), so the PC dates the call as the
     * owner lived it and never as UTC's day.
     */
    fun startedAt(epochMs: Long, zone: ZoneId = ZoneId.systemDefault()): String =
        DateTimeFormatter.ISO_OFFSET_DATE_TIME.format(Instant.ofEpochMilli(epochMs).atZone(zone))

    /**
     * The optional `title` sent with `finish`: one plain line the PC may use
     * for the note's heading, with the date and time in it. The PC names the
     * note - this is a suggestion, never a path, because the phone does not
     * know and must not guess where the vault is.
     */
    fun title(epochMs: Long, zone: ZoneId = ZoneId.systemDefault()): String {
        val at = Instant.ofEpochMilli(epochMs).atZone(zone)
        return "Call - " + DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm").format(at)
    }

    // -------------------------------------------------------------- words ---

    /** The notification's heading while armed. */
    const val ARMED_TITLE = "Call recording armed"

    /** The notification's line while armed: what it is and what it is not doing. */
    const val ARMED_TEXT =
        "The microphone is closed until a call starts. Say \"stop recording\" or press Stop to cancel."

    /** The notification's heading while recording. */
    const val RECORDING_TITLE = "Recording call"

    /**
     * The one-line consent reminder, and the contract's own flag name. It is
     * shown on the notification, on Android's own screen, for the whole call:
     * a recording the other person was not told about is not something this
     * app can make acceptable, so the reminder never goes away.
     */
    const val CONSENT_LINE = "Recording - tell the other person"

    /** Said when the platform would not put the call on speaker. Never a claim both sides were captured. */
    const val SPEAKER_ASK = "Turn the call on speaker so Jarvis can hear both sides"

    /** The heading of the "kept on this phone" notice, when the PC could not be reached. */
    const val WAITING_TITLE = "Call recording kept on this phone"

    /** Its line: nothing was lost, and it will go by itself. */
    const val WAITING_TEXT = "Your PC could not be reached. The recording will send when it answers."

    /** Said (and shown) when a finished recording reached the PC. */
    const val SENT_TEXT = "Sent to your PC. It will write the note there."

    /** Said when the recorder stopped. */
    const val STOPPED_TEXT = "Call recording stopped."

    /** The armed line on the app's own screen. */
    const val PLATE_ARMED = "Call recording armed"

    /** The recording line on the app's own screen, before the clock: `Recording call 00:04:12`. */
    const val PLATE_RECORDING = "Recording call"

    /** The plate's own heading. */
    const val PLATE_TITLE = "Call recording"

    /** The plate's explanation - one paragraph, in the owner's words. */
    const val PLATE_ABOUT =
        "Say \"record call\" to Jarvis, or press Arm here. The next call is recorded on this phone's " +
            "microphone - Android does not let an app record the call itself - so the call has to be on " +
            "speaker for both voices to be caught. The PC turns it into words, works out who was " +
            "speaking, and writes one note dated to the call. Nothing is written down on this phone, " +
            "and nothing leaves your own network."

    /** The one-line state shown for a phase, with the clock while recording. */
    fun line(phase: Phase, elapsedMs: Long = 0L): String = when (phase) {
        Phase.OFF -> "Off"
        Phase.ARMED -> PLATE_ARMED
        Phase.RECORDING -> "$PLATE_RECORDING ${clock(elapsedMs)}"
        Phase.SENDING -> "Sending the call recording to your PC"
    }

    /**
     * The notification's words, redacted on a locked phone by the ONE shared
     * rule every other Jarvis notice uses (`SecurityRules.notificationsLocked`).
     * A call recording is one of the most private things this app ever shows,
     * so with the lock on the notice says the app's name and one fixed line,
     * exactly like Live's.
     */
    fun noticeWords(locked: Boolean, appName: String, title: String, text: String): List<String> =
        if (locked) listOf(appName, LOCK_LINE) else listOf(title, text)

    /** The fixed line a locked phone shows instead of the title and text. */
    const val LOCK_LINE = "Call recording is on. Unlock your phone to see it."

    /**
     * The directive a chat answer may carry: `"call_record": {"action": "arm"}`
     * (or `"stop"`). Null when there is no directive, when the action is not
     * one of the two, or when nothing could be parsed - a malformed one is
     * silence, never a guess.
     */
    fun actionOf(raw: String?): String? {
        val action = raw?.trim()?.lowercase() ?: return null
        return if (action == ACTION_ARM || action == ACTION_STOP) action else null
    }

    /** The event a directive's action is, or null when it names nothing. */
    fun eventOf(action: String?): Event? = when (action) {
        ACTION_ARM -> Event.ARM
        ACTION_STOP -> Event.OWNER_STOP
        else -> null
    }
}
