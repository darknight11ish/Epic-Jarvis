package com.jarvis.client.call

import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.core.content.ContextCompat
import com.jarvis.client.service.CallRecordService
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Call recording as the rest of the app sees it: one state, one place to arm
 * it, and the last thing said about it.
 *
 * The RULES are in [CallRecordRules] and the microphone's arbitration is in
 * [com.jarvis.client.voice.MicNow]; the WORK is in
 * `service/CallRecordService.kt`, which publishes back through [publish].
 * This object exists so a screen, a chat directive and a notification button
 * all reach the same recorder, and so one line of state ("Call recording
 * armed" / "Recording call 00:04:12") has one source.
 *
 * WHAT CAN ARM IT (the owner's two ways, and nothing else):
 *  - the chat directive `"call_record": {"action": "arm"}` in an answer's
 *    `X-Jarvis-Route` header, which the runtime applies;
 *  - the button on the plate ([arm]), which is the owner's own tap.
 * A widget, a tile, an intent from another app or a boot broadcast cannot:
 * opening a microphone is the owner's act, and the caller here is always one
 * of those two.
 *
 * Nothing here is a server call and nothing here is a permission decision:
 * arming only claims the microphone and starts the service, which is refused
 * by Android exactly like Live is when it cannot start a microphone service.
 */
object CallRecordNow {

    private const val TAG = "JarvisCallRecord"

    /**
     * What the phone shows. [elapsedMs] is the recording clock, published by
     * the service about once a second while it records; [waiting] is how many
     * finished recordings are still on this phone; [said] is the last
     * one-line notice, cleared by the screen once it has been read.
     */
    data class Status(
        val phase: CallRecordRules.Phase = CallRecordRules.Phase.OFF,
        val startedAtMs: Long = 0L,
        val elapsedMs: Long = 0L,
        val waiting: Int = 0,
        val said: String? = null,
        /** Did the platform let the call go on speaker? False = both sides were probably NOT captured. */
        val speaker: Boolean = true,
    ) {
        /** The one line a screen shows: "Call recording armed" / "Recording call 00:04:12". */
        val line: String get() = CallRecordRules.line(phase, elapsedMs)

        val busy: Boolean get() = phase != CallRecordRules.Phase.OFF
    }

    private val _status = MutableStateFlow(Status())

    /** The recorder's state, for the plate and for anything else that wants to show it. */
    val status: StateFlow<Status> = _status.asStateFlow()

    /** The service's own reporter: it owns the truth, screens only read it. */
    fun publish(status: Status) {
        _status.value = status
    }

    /** One more line to say (a stop, a send, a refusal). Never a notification on its own. */
    fun say(text: String) {
        _status.value = _status.value.copy(said = text)
    }

    /**
     * Re-read the queue on disk, so the card's "waiting to send" line is the
     * truth after the app restarts (the service keeps it current while it
     * runs, and the disk is what survives a restart).
     */
    fun refreshWaiting(context: Context) {
        val count = runCatching { CallRecordService.waitingCount(context) }.getOrDefault(0)
        if (_status.value.waiting != count) _status.value = _status.value.copy(waiting = count)
    }

    /** The screen has shown [Status.said]; forget it so it is not shown twice. */
    fun consumeSaid() {
        if (_status.value.said != null) _status.value = _status.value.copy(said = null)
    }

    // ------------------------------------------------------------- actions ---

    /**
     * Arm call recording and wait for a call. Starting a microphone foreground
     * service needs this app in front on Android 14+, which is true for both
     * ways this is reached (the plate's tap, and an answer arriving in the
     * app's own chat). False means Android refused to start it - the caller
     * says so, and nothing was armed.
     */
    fun arm(context: Context): Boolean = runCatching {
        ContextCompat.startForegroundService(
            context,
            Intent(context, CallRecordService::class.java).setAction(CallRecordService.ACTION_ARM),
        )
    }.onFailure { Log.w(TAG, "could not arm call recording", it) }.isSuccess

    /** Stop the recording (or the arming) and let the audio finish uploading. */
    fun stop(context: Context) {
        runCatching {
            context.startService(
                Intent(context, CallRecordService::class.java).setAction(CallRecordService.ACTION_STOP),
            )
        }.onFailure { Log.w(TAG, "could not stop call recording", it) }
    }

    /** Disarm without recording anything, or stop a recording - the same Stop, from a screen. */
    fun disarm(context: Context) = stop(context)

    /**
     * Try to send everything waiting on this phone now. The plate's "Send it
     * now" button; also what the service does by itself when it next starts.
     */
    fun sendWaiting(context: Context) {
        runCatching {
            ContextCompat.startForegroundService(
                context,
                Intent(context, CallRecordService::class.java).setAction(CallRecordService.ACTION_SEND_WAITING),
            )
        }.onFailure { Log.w(TAG, "could not start the resend", it) }
    }

    /**
     * DELETE the recordings this phone is still holding and the PC never took -
     * the owner's own discard, reached only through the plate's confirmed
     * Delete (the privacy audit's D7: a denied or unsendable recording must
     * not be stuck on the phone for ever).
     *
     * A plain started service, not a foreground one: no microphone is opened
     * and no notification is needed, so this works while the app is in front -
     * which it is, because the button is on the plate. Nothing the PC has
     * acknowledged can be deleted ([CallRecordStore.discardUnsent]), and the
     * last thing said is the count, in words.
     */
    fun discard(context: Context) {
        runCatching {
            context.startService(
                Intent(context, CallRecordService::class.java).setAction(CallRecordService.ACTION_DISCARD),
            )
        }.onFailure { Log.w(TAG, "could not delete the waiting recordings", it) }
    }

    /**
     * A chat directive: `arm` arms, and `stop` stops a recording in progress
     * or cancels an arming. An action this app does not know is null, and a
     * null event does nothing at all.
     */
    fun onDirective(event: CallRecordRules.Event?, context: Context) {
        when (event) {
            CallRecordRules.Event.ARM -> if (!arm(context)) {
                say("Android did not let call recording start. A microphone service can only start with Jarvis open on screen.")
            }
            CallRecordRules.Event.OWNER_STOP -> stop(context)
            else -> Unit
        }
    }
}
