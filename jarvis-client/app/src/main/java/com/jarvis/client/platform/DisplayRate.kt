package com.jarvis.client.platform

import android.app.Activity
import android.os.Build
import android.util.Log
import android.view.Display
import android.view.View
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

        val best = rates.maxOrNull() ?: return
        _requestedHz.value = best

        if (Build.VERSION.SDK_INT >= 35 && view != null) {
            runCatching { view.requestedFrameRate = best }
                .onFailure { Log.w(TAG, "setRequestedFrameRate refused", it) }
            return
        }

        runCatching {
            val attrs = activity.window.attributes
            attrs.preferredRefreshRate = best
            activity.window.attributes = attrs
        }.onFailure { Log.w(TAG, "preferredRefreshRate refused", it) }
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

    fun reset() {
        estimate = 0f
        lastPublishNanos = 0L
        _achievedHz.value = 0f
    }

    /** The nearest rate the panel actually offers, for display. */
    fun snap(hz: Float): Float {
        val known = _modes.value.ifEmpty { KNOWN }
        return known.minByOrNull { abs(it - hz) } ?: hz
    }

    private val KNOWN = listOf(60f, 75f, 90f, 100f, 120f, 144f, 165f, 240f)

    /** Four publishes a second at most. Faster than a person can read anyway. */
    private const val MIN_PUBLISH_NANOS = 250_000_000L
    private const val TAG = "JarvisDisplayRate"
}
