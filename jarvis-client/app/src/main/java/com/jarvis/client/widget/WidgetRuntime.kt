package com.jarvis.client.widget

import android.content.Context
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import kotlinx.serialization.json.JsonObject

/**
 * The only two things a home-screen widget ever waits for, each with a
 * ceiling, in one place so all five widgets share it.
 *
 * Why it exists: a Glance widget's `provideGlance` is a WorkManager job, and
 * anything it suspends on holds the widget's whole draw open. Before
 * 2026-10-27 both waits were unbounded - `JarvisRuntime.initialize` ran
 * synchronously on the composition's main thread, and the board widgets'
 * `GET /api/widgets/show` used the general HTTP client, whose read timeout is
 * 120 s on purpose (chat streams). Neither could hang for ever, but either
 * could sit there far longer than a home screen should say nothing, and a
 * widget that is waiting is indistinguishable from a widget that is broken -
 * which is exactly the report this fixes.
 *
 * Both calls now run through [WidgetStates.bounded], so the worst case is a
 * sentence: "Jarvis could not start" or "Could not reach your PC".
 *
 * Android types live here, not in `WidgetStates`, so the state machine stays
 * pure and JVM-testable.
 */
internal object WidgetRuntime {

    /**
     * Starts the app's runtime for a widget draw. `false` means it did not
     * finish inside [WidgetStates.INIT_TIMEOUT_MS] (or threw) - the caller
     * renders [WidgetStates.Approval.NOT_STARTED] rather than waiting.
     *
     * Never on the composition's main thread: `initialize` builds the API
     * client, the voice session and the settings stores and reads the models
     * cache, none of which needs the main thread, and blocking the main thread
     * there was a real (if brief) stall. [WidgetStates.bounded] starts it on
     * `Dispatchers.Default` and stops WAITING for it at the budget, so a
     * startup that never finishes is a sentence rather than a widget that
     * never draws. The abandoned work keeps running and is harmless:
     * `initialize` is idempotent and `@Synchronized`, so the next caller
     * simply finds it done.
     */
    suspend fun start(context: Context): Boolean =
        WidgetStates.bounded(WidgetStates.INIT_TIMEOUT_MS) {
            runCatching { JarvisRuntime.initialize(context) }.isSuccess
        } == true

    /**
     * One `GET /api/widgets/show` read for a "Jarvis widget" 1-3. `null` means
     * the PC did not answer inside [WidgetStates.READ_TIMEOUT_MS]; that is the
     * widget's `TIMED_OUT` state, not an empty widget.
     */
    suspend fun readWidget(id: String): ApiResult<JsonObject>? =
        WidgetStates.bounded(WidgetStates.READ_TIMEOUT_MS) { JarvisRuntime.widgetShow(id) }

    /**
     * One `GET /api/calendar?days=N` read for the calendar widget. `null` means
     * the PC did not answer inside the same budget, which is that widget's
     * `TIMED_OUT` state ("Could not reach your PC"), never "Nothing today" -
     * the two are different sentences and only one of them is true.
     *
     * A week is asked for and not a day: the widget draws today, and a week
     * costs the PC one small read while letting the launcher's own 30-minute
     * tick carry the list across midnight without a second route.
     */
    suspend fun readCalendar(days: Int = 7): ApiResult<JsonObject>? =
        WidgetStates.bounded(WidgetStates.READ_TIMEOUT_MS) { JarvisRuntime.calendar(days) }
}
