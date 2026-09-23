package com.jarvis.client.platform

import android.app.Activity
import android.content.Context
import android.os.Build
import android.os.PowerManager
import android.util.Log
import android.view.Display
import android.view.View
import androidx.core.content.ContextCompat
import com.jarvis.client.FaceState
import com.jarvis.client.face.Spec
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlin.math.abs
import kotlin.math.roundToInt

/**
 * Asking the panel for its real refresh rate, and measuring what we got.
 *
 * **A high-refresh panel does not give an app the high rate unless it asks.**
 * Most phones sold recently have a 90, 120 or 144 Hz screen and render an app
 * at 60 until it says otherwise, so a reactor face that was carefully paced
 * against `withFrameNanos` was still being handed 60 vsyncs a second on
 * hardware capable of twice that.
 *
 * Two numbers, kept apart on purpose:
 *
 * - [panelHz] is what the display is running at, read from the platform. On
 *   Android this is simply available, which is worth saying because the spec's
 *   advice to "measure on empty frames at startup and only revise upward" is
 *   about the *web*, where there is no API and a busy frame makes the app
 *   measure its own slowness. Here there is an API, so guessing would be a
 *   worse answer than asking.
 * - [achievedHz] is what the face actually sustained, from the frame clock.
 *   Lower than the panel means the draw is the limit; equal means it is not.
 *
 * Nothing here can *guarantee* a rate. Battery saver caps it, LTPO panels
 * float it by content cadence, many OEMs drop to 60 at low brightness, and
 * thermal throttling ignores all of it — and there is no API that reports why
 * a request was refused. So this asks, then reports what happened.
 */
object DisplayRate {

    private val _panelHz = MutableStateFlow(0f)
    val panelHz: StateFlow<Float> = _panelHz.asStateFlow()

    private val _achievedHz = MutableStateFlow(0f)
    val achievedHz: StateFlow<Float> = _achievedHz.asStateFlow()

    private val _requestedHz = MutableStateFlow(0f)
    val requestedHz: StateFlow<Float> = _requestedHz.asStateFlow()

    private val _modes = MutableStateFlow<List<Float>>(emptyList())

    /** Every rate the panel offers at the current resolution. */
    val modes: StateFlow<List<Float>> = _modes.asStateFlow()

    /** The fastest same-resolution mode, found by [request]. 0 until then. */
    @Volatile private var bestHz = 0f

    /**
     * Asks for the highest rate the panel offers **at the current resolution**.
     *
     * Deliberately not `preferredDisplayModeId`: that can also change the
     * resolution, which is a far bigger hammer than "please run the screen
     * faster", and Google has discouraged it since Android 11 because the
     * platform cannot see the app's rendering intent through it.
     *
     * On API 35+ the cooperative `View.setRequestedFrameRate` is used instead —
     * it votes among views and feeds Adaptive Refresh Rate rather than pinning
     * a number, which is the right shape for one animated surface on a screen
     * full of static text.
     */
    fun request(activity: Activity, view: View?) {
        val display = runCatching { activity.display }.getOrNull() ?: return
        val current = display.mode ?: return

        // Same resolution only. A mode with a different size would resize the
        // window to get a faster clock, which is not the trade being made.
        val sameSize = display.supportedModes.orEmpty().filter {
            it.physicalWidth == current.physicalWidth && it.physicalHeight == current.physicalHeight
        }
        val rates = sameSize.map { it.refreshRate }.distinct().sorted()
        _modes.value = rates
        _panelHz.value = display.refreshRate
        bestHz = rates.maxOrNull() ?: 0f
        // Nothing is asked for here any more - see [setHigh]. This used to
        // pin the panel at its maximum for the life of the activity, across
        // the nine tenths of screen-on time the face draws at 30, 15 or 2
        // frames a second. On a 120 Hz panel that is a measurable battery
        // cost for frames nothing was drawing.
    }

    /**
     * Asks for the panel's fastest rate while [high] and lets go of it
     * otherwise.
     *
     * Whether to ask is [wantsHigh]'s decision, not this function's: this one
     * only carries the answer to the platform. Repeated calls with the same
     * answer are free; the request is only re-sent when it changes.
     */
    fun setHigh(activity: Activity, view: View?, high: Boolean) {
        val best = bestHz
        if (best <= 0f) return
        val want = if (high) best else 0f
        if (_requestedHz.value == want) return
        _requestedHz.value = want

        if (Build.VERSION.SDK_INT >= 35 && view != null) {
            runCatching {
                view.requestedFrameRate =
                    // `requestedFrameRate` is Float; the category constants are
                    // Int, and Kotlin does not widen one to the other. Caught
                    // by reading, not by a compiler - there is none on this
                    // branch.
                    if (high) best else View.REQUESTED_FRAME_RATE_CATEGORY_DEFAULT.toFloat()
            }.onFailure { Log.w(TAG, "setRequestedFrameRate refused", it) }
            return
        }

        runCatching {
            val attrs = activity.window.attributes
            // 0 means "no preference", which hands the choice back to the OS.
            attrs.preferredRefreshRate = want
            activity.window.attributes = attrs
        }.onFailure { Log.w(TAG, "preferredRefreshRate refused", it) }
    }

    /**
     * Whether the panel should be asked for its fastest rate right now.
     *
     * This used to be "whenever the face wants every frame" and nothing else,
     * which asked for 120 or 144 Hz in three places it bought nothing:
     *
     * - **On screens with no face.** The request followed the face's STATE,
     *   not whether the face was on screen, so reading the Inbox during a long
     *   THINKING task held the panel at its top rate for a screen of still text.
     * - **In ERROR.** ERROR lasts until someone fixes whatever is wrong, and
     *   after its short hitch it is a slow crawl that 60 Hz draws just as well.
     * - **In battery saver, or when the phone is hot.** The owner (or Android)
     *   has already said "spend less", and a request for more frames argues
     *   with that. On API 33/34 the request pins the whole window, so it is
     *   not a polite vote there.
     *
     * So now: only with the face on screen, only while it is listening or
     * speaking, THINKING for its first [THINKING_HIGH_MS] (the part where the
     * motion is changing; after that it settles into a steady loop), and never
     * when [constrained]. [Spec.fpsFor] is still consulted, but only as a
     * floor - a state the spec draws at 30 or less never asks - and it is not
     * edited: it is transcribed from the shared spec and drift-tested.
     *
     * Pure, so it is unit-testable without a phone.
     *
     * @param faceOnScreen true only while Home is showing. Appearance draws a
     *   small preview of the face too, but a preview does not need 120 Hz.
     * @param msInState how long [state] has been the face's state.
     * @param constrained [constrained] of the current context, passed in so
     *   this stays pure.
     * @param pref how hard the owner wants the panel driven, from the face
     *   editor's Frame rate and Battery saver (see FaceBudget.smoothFor).
     *   Defaults to AUTO, which is the behaviour above.
     */
    fun wantsHigh(
        state: FaceState,
        faceOnScreen: Boolean,
        msInState: Long,
        constrained: Boolean,
        pref: SmoothMotion = SmoothMotion.AUTO,
    ): Boolean {
        if (!faceOnScreen || constrained || pref == SmoothMotion.OFF) return false
        if (Spec.fpsFor(state) != 0) return false
        return when (state) {
            FaceState.LISTENING, FaceState.SPEAKING -> true
            // ALWAYS lifts the time limit on THINKING and nothing else. ERROR
            // stays out even then: a slow crawl gains nothing from 120 Hz.
            FaceState.THINKING -> pref == SmoothMotion.ALWAYS || msInState < THINKING_HIGH_MS
            else -> false
        }
    }

    /**
     * Whether [wantsHigh] could ever say yes for this state and screen, with
     * time passing. False means the caller can stop re-checking until one of
     * them changes; true means the answer can still flip on its own (the
     * THINKING time limit, battery saver, heat), so it is worth polling.
     */
    fun couldWantHigh(state: FaceState, faceOnScreen: Boolean, pref: SmoothMotion = SmoothMotion.AUTO): Boolean =
        faceOnScreen && pref != SmoothMotion.OFF && Spec.fpsFor(state) == 0 &&
            (state == FaceState.LISTENING || state == FaceState.SPEAKING || state == FaceState.THINKING)

    /**
     * True when the phone has asked apps to spend less: battery saver is on,
     * or the phone is at least moderately hot.
     *
     * Read fresh each time rather than listened for. Both are one binder call,
     * and the only caller asks every couple of seconds while the face is in a
     * state that might want a high rate - so a change is picked up within that,
     * without a listener to register and remember to remove.
     */
    fun constrained(context: Context): Boolean {
        val pm = ContextCompat.getSystemService(context, PowerManager::class.java) ?: return false
        if (runCatching { pm.isPowerSaveMode }.getOrDefault(false)) return true
        val thermal = runCatching { pm.currentThermalStatus }
            .getOrDefault(PowerManager.THERMAL_STATUS_NONE)
        return thermal >= PowerManager.THERMAL_STATUS_MODERATE
    }

    /** Re-reads what the display settled on. Cheap; call on resume. */
    fun refresh(activity: Activity) {
        runCatching { activity.display?.refreshRate }.getOrNull()?.let { _panelHz.value = it }
    }

    /**
     * Records a frame interval and keeps a running estimate.
     *
     * Fed from the face's own frame loop, so it measures the surface that
     * actually matters. Outliers in EITHER direction are dropped rather than
     * averaged in.
     *
     * Both tails, because the case this names — the odd 200 ms stall — makes
     * `hz` small, and the guard used to test only `hz > prev * 2`. So every
     * stall it was written for went straight in while harmless fast samples
     * were rejected. Ten hitches during a scroll dragged a 120 Hz estimate down
     * to about 80, and this screen then reported the face was missing frames it
     * was not — the exact diagnosis it exists to provide, inverted.
     */
    fun sample(deltaNanos: Long) {
        if (deltaNanos <= 0) return
        lastSampleNanos = System.nanoTime()
        val hz = 1_000_000_000f / deltaNanos
        if (hz < 5f || hz > 400f) return
        val prev = estimate
        estimate = when {
            prev <= 0f -> hz
            hz > prev * 2f || hz < prev * 0.5f -> prev
            else -> prev + (hz - prev) * 0.05f
        }
        publish()
    }

    /**
     * Moves the measurement onto the StateFlow, rarely.
     *
     * The measurement above is a few floating-point operations on a value
     * nobody is watching, which is cheap enough to do every frame. Writing
     * [_achievedHz] is not: it is a StateFlow the Checks screen collects, so
     * every write recomposes that screen. [sample] runs from the face's frame
     * loop at the panel rate, so with the Checks screen open a completely idle
     * face produced ~120 emissions and ~120 recompositions a second - on a
     * screen whose whole purpose is to say the app is not working the device
     * hard.
     *
     * Two gates, both about what a person can actually see: nothing is
     * published unless the value a human reads (whole Hz) has changed, and
     * never more often than [MIN_PUBLISH_NANOS]. The number is published
     * rounded so the comparison and the value agree - a float that keeps
     * drifting in the third decimal would pass StateFlow's own equality check
     * every time and republish for ever.
     */
    private fun publish() {
        val rounded = estimate.roundToInt()
        if (rounded == _achievedHz.value.roundToInt()) return
        val now = System.nanoTime()
        if (now - lastPublishNanos < MIN_PUBLISH_NANOS) return
        lastPublishNanos = now
        _achievedHz.value = rounded.toFloat()
    }

    /**
     * The running estimate, kept off the StateFlow. See [publish].
     *
     * Not @Volatile and not synchronised: [sample] is only ever called from the
     * face's frame callback, which is the main thread.
     */
    private var estimate = 0f
    private var lastPublishNanos = 0L

    /**
     * When the face last drew a frame, or 0 if it never has in this process.
     *
     * The face runs on Home (and as a preview in Appearance), never on the
     * Checks screen that shows [achievedHz] - so that screen is always
     * looking at a number measured somewhere else, some time ago.
     * Without a time beside it, that number looked like a live measurement.
     * Volatile because the Checks screen reads it from its own ticker, while
     * [sample] writes it from the frame loop.
     */
    @Volatile private var lastSampleNanos = 0L

    /** Milliseconds since the face last drew a frame, or null if it never has. */
    fun msSinceLastSample(): Long? {
        val at = lastSampleNanos
        if (at == 0L) return null
        return (System.nanoTime() - at) / 1_000_000L
    }

    fun reset() {
        estimate = 0f
        lastPublishNanos = 0L
        lastSampleNanos = 0L
        _achievedHz.value = 0f
    }

    /** The nearest rate the panel actually offers, for display. */
    fun snap(hz: Float): Float {
        val known = _modes.value.ifEmpty { KNOWN }
        return known.minByOrNull { abs(it - hz) } ?: hz
    }

    private val KNOWN = listOf(60f, 75f, 90f, 100f, 120f, 144f, 165f, 240f)

    /**
     * How long THINKING keeps the high rate under AUTO. The first seconds are
     * where the face's motion is changing; a long task after that is a steady
     * loop, and 60 Hz draws a steady loop just as well for less battery.
     */
    const val THINKING_HIGH_MS = 10_000L

    /** Four publishes a second at most. Faster than a person can read anyway. */
    private const val MIN_PUBLISH_NANOS = 250_000_000L
    private const val TAG = "JarvisDisplayRate"
}

/**
 * The owner's choice for how hard to drive the screen, worked out from the
 * face editor's Frame rate and Battery saver by FaceBudget.smoothFor: OFF for
 * a chosen 60 or battery saver, ALWAYS for Max, AUTO otherwise. Neither choice can
 * speed the face itself up - this is the panel's refresh rate, not the
 * face's motion - and ALWAYS still never asks in battery saver or when hot.
 */
enum class SmoothMotion { OFF, AUTO, ALWAYS }
