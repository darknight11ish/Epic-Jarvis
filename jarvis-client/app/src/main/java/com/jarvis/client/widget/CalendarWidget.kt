package com.jarvis.client.widget

import android.content.Context
import android.content.Intent
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.action.actionStartActivity as actionStartActivityIntent
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.layout.Alignment
import androidx.glance.layout.Box
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.LinkState
import com.jarvis.client.MainActivity
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Calendar
import com.jarvis.client.service.EventService
import kotlinx.serialization.json.JsonObject

/**
 * Today, at a glance: the date, then today's next three events, on the home
 * screen (the owner's ask of 2026-10-29; design brief Part 5.7; API section
 * 163). The sixth Jarvis widget and the only one that shows the plan for the
 * day.
 *
 * IT ALWAYS SAYS SOMETHING. Every draw ends in one of [WidgetStates.Cal]'s
 * states, and every state has words ([WidgetStates.calendarWords]) - there is
 * no "loading" state anywhere in this file, for the reason the other five
 * widgets' shared state machine spells out: a spinner is a promise that
 * something is on its way, and a widget nobody updates cannot keep it. With
 * real events it draws them; with none it draws "Nothing today", which is a
 * true sentence and not an error.
 *
 * **THE HOME SCREEN IS PUBLIC.** Anyone holding the phone sees it without
 * unlocking Jarvis, so:
 *  - under App lock or "Hide memory lists and chat history" it draws ONE
 *    sentence, [Calendar.HIDDEN], and no title at all - not even a count of the
 *    day's events, because "3 events" plus a locked phone still says the owner
 *    has a busy day (this is stricter than the board widget, which keeps its
 *    counts; an event TITLE is the whole point of this widget, so a redacted
 *    one is better replaced by a sentence);
 *  - with the feature switched off it stays on the home screen and says
 *    [Calendar.OFF_WIDGET], with a tap that opens Settings - design decision
 *    D5. A widget that vanishes, or an empty square, both read as a fault;
 *  - on a link that is down or catching up it says [Calendar.STALE] rather
 *    than drawing yesterday's list as if it were today's.
 *
 * READ ONLY, AND ONLY ON A LIVE LINK. Nothing is kept on the phone between
 * draws: no events, no titles. A process the launcher woke only to draw this
 * has no link, so it says "Not up to date" and opens the app instead of
 * guessing.
 *
 * WHEN IT REDRAWS, SAID HONESTLY. While Jarvis runs, [JarvisRuntime] redraws it
 * whenever the link, the calendar or the two privacy switches change.
 * `updatePeriodMillis` (30 minutes) is the launcher's floor and the only thing
 * that redraws it with the app closed - so **just after midnight it can still
 * show yesterday for up to half an hour**. Fixing that needs an AlarmManager
 * wake-up, which is not in this slice; it is written here rather than left to
 * be discovered, and it is the reason the date line is drawn from the PC's own
 * list rather than from the phone's clock: the widget can only ever be as wrong
 * as the launcher's tick, never twice wrong.
 */
class CalendarWidget : GlanceAppWidget() {

    override val sizeMode: SizeMode = SizeMode.Exact

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        // Bounded, and terminal in every branch - the startup guard every other
        // widget uses, for the same reason: a Keystore or preferences failure
        // called bare from a Glance worker is an uncaught exception in the
        // update coroutine, not a square this app controls.
        val ready = WidgetRuntime.start(context) && JarvisRuntime.isInitialized
        val paired = ready && JarvisRuntime.isPaired()
        val live = ready && !JarvisRuntime.stale.value && JarvisRuntime.link.value == LinkState.CONNECTED
        val security = if (ready) JarvisRuntime.settings.security.value else null
        // Fails closed: settings that cannot be read count as hidden.
        val hideWords = security == null || security.appLock || security.privateLists
        // What the link was for the two states that need no read at all. `off`
        // is only known from a read, so it is filled in below.
        var off = false
        var view: Calendar.View? = null
        var read = WidgetStates.Read.CONTENT
        if (ready && paired) {
            val answer = WidgetRuntime.readCalendar()
            when (answer) {
                null -> read = WidgetStates.Read.TIMED_OUT
                is ApiResult.Ok<JsonObject> -> {
                    view = Calendar.parse(answer.value)
                    // The switch lives on the PC and rides on the same read. A
                    // read that came back but could not be parsed is a failure,
                    // not "off".
                    if (view == null) {
                        read = WidgetStates.Read.FAILED
                    } else if (!view.on) {
                        off = true
                    }
                }
                is ApiResult.Failed -> read = if (Calendar.missing(answer.error)) {
                    // A PC without the calendar at all: the feature is not
                    // there, which for the widget reads the same as off - tap
                    // to open Jarvis and see why.
                    off = true
                    WidgetStates.Read.CONTENT
                } else {
                    WidgetStates.Read.FAILED
                }
            }
        }
        val state = WidgetStates.calendar(
            ready = ready,
            paired = paired,
            off = off,
            hidden = hideWords,
            live = live,
            read = read,
        )
        val today = Calendar.todayNow()
        val lines = if (state == WidgetStates.Cal.CONTENT && view != null) {
            Calendar.widgetLines(view, today, hidden = false)
        } else {
            emptyList()
        }
        val dateLine = Calendar.datedWords(today, today)
        // The tap: Settings when the feature is off (the one thing to fix), and
        // the calendar itself in every other state.
        val tap = if (state == WidgetStates.Cal.OFF) openSettings(context) else openCalendar()

        provideContent {
            Column(
                modifier = GlanceModifier
                    .fillMaxSize()
                    .background(CalendarPalette.Background)
                    .cornerRadius(16.dp)
                    .padding(12.dp)
                    .clickable(tap),
            ) {
                Row(modifier = GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        dateLine,
                        maxLines = 1,
                        style = TextStyle(
                            color = CalendarPalette.TextHi,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold,
                        ),
                    )
                    Spacer(GlanceModifier.defaultWeight())
                    Text(
                        Calendar.TITLE,
                        maxLines = 1,
                        style = TextStyle(color = CalendarPalette.Accent, fontSize = 11.sp),
                    )
                }
                Spacer(GlanceModifier.height(6.dp))
                if (state == WidgetStates.Cal.CONTENT) {
                    for (line in lines) {
                        Text(
                            line,
                            maxLines = 1,
                            style = TextStyle(color = CalendarPalette.TextHi, fontSize = 12.sp),
                        )
                        Spacer(GlanceModifier.height(3.dp))
                    }
                } else {
                    val words = WidgetStates.calendarWords(state)
                    Text(
                        words.first,
                        maxLines = 2,
                        style = TextStyle(
                            color = CalendarPalette.TextHi,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                        ),
                    )
                    Spacer(GlanceModifier.height(2.dp))
                    Text(
                        words.second,
                        maxLines = 1,
                        style = TextStyle(color = CalendarPalette.TextMuted, fontSize = 11.sp),
                    )
                }
            }
        }
    }

    /** A tap in any ordinary state: the app, on the Calendar screen. */
    private fun openCalendar(): androidx.glance.action.Action =
        actionStartActivity<MainActivity>()

    /**
     * A tap while the feature is off: the app, on Settings at the calendar's own
     * row. An `Intent` action rather than a plain activity start, so the screen
     * that opens is the one that fixes the thing the widget just said.
     */
    private fun openSettings(context: Context): androidx.glance.action.Action =
        actionStartActivityIntent(
            Intent(context, MainActivity::class.java)
                .setAction(MainActivity.ACTION_OPEN_CALENDAR_SETTINGS)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
        )

    // Kept for symmetry with the other widgets' own comments: the event stream
    // service is what makes a live link live, and a widget never starts it. A
    // draw that finds no link says so and offers the tap - it does not open a
    // foreground service from a home screen, which is the same rule
    // QuickLinkWidget's "Talk" button follows.
    @Suppress("unused")
    private fun wouldStartService(context: Context) = EventService.start(context)
}

/**
 * One widget class, one receiver: Android addresses an app widget from the
 * launcher's own process, so the receiver has to be exported for the same
 * reason the five existing ones are.
 */
class CalendarWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = CalendarWidget()
}

/**
 * The widget's own fixed colours - [com.jarvis.client.widget.ApprovalWidget]'s
 * set, for the same reason: a Glance RemoteViews host in another process
 * cannot reach this app's dynamic per-face `Chrome`. Its own object rather
 * than a shared one, because two top-level `private` objects with one name in
 * the same package is a real `Redeclaration` at compile time.
 */
private object CalendarPalette {
    val Background = ColorProvider(Color(0xFF04070C))
    val Surface1 = ColorProvider(Color(0xFF0E1822))
    val TextHi = ColorProvider(Color(0xFFE6EEF7))
    val TextMuted = ColorProvider(Color(0xFF93A6BA))
    val Accent = ColorProvider(Color(0xFF63F7FF))
}
