package com.jarvis.client.widget

import android.content.Context
import android.content.Intent
import android.widget.Toast
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.action.Action
import androidx.glance.action.ActionParameters
import androidx.glance.action.actionParametersOf
import androidx.glance.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.LinearProgressIndicator
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.action.ActionCallback
import androidx.glance.appwidget.action.actionRunCallback
import androidx.glance.appwidget.action.actionStartActivity as actionStartActivityIntent
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.appwidget.updateAll
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
import androidx.glance.layout.width
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.LinkState
import com.jarvis.client.MainActivity
import com.jarvis.client.data.QuickTiles
import com.jarvis.client.data.TileAction
import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisWidgets
import com.jarvis.client.net.PlainErrors
import com.jarvis.client.service.EventService
import com.jarvis.client.service.QuickTileService

/**
 * "Jarvis widget" 1, 2 and 3 on the home screen: each draws the saved widget
 * the owner gave its slot under Brain, Widgets ([JarvisWidgets],
 * docs/JARVIS-API.md section 87). The same shape as the Quick Settings tile
 * slots: Android cannot add a widget type at run time, so the app ships
 * three and the owner assigns each one.
 *
 * It draws blocks natively from the PC's filled-in answer, through
 * [JarvisWidgets.viewOf] - the rule the desktop and the PC share - so only
 * the five block kinds and the five tile buttons can ever appear, whatever
 * the PC sends.
 *
 * THE HOME SCREEN IS PUBLIC. Anyone holding the phone sees it without
 * unlocking Jarvis, so while App lock or "Hide memory lists and chat
 * history" is on, every private block (reminders, timers, Today cards,
 * to-do items, what is playing) shows its label and "Hidden - open Jarvis to
 * see it." instead of its words ([JarvisWidgets.hide]). Counts, the disk and
 * the focus countdown stay.
 *
 * READ ONLY ON A LIVE LINK. Like [ApprovalWidget], a process the launcher
 * woke only to draw this has no link: then it says "Not up to date" and
 * opens the app, rather than draw something it has not checked. Nothing is
 * kept on the phone between draws - not the widget, not its words.
 *
 * BUTTONS follow the tiles exactly: [QuickTiles.decide] decides, and
 * [QuickTileService.perform] does it - held on a stale link (rule 4) except
 * Stop everything, "Brief me" only opens the app (behind App lock). Never
 * Approve or Deny.
 */
open class JarvisBoardWidget(private val slot: Int) : GlanceAppWidget() {

    override val sizeMode: SizeMode = SizeMode.Exact

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val ready = runCatching { JarvisRuntime.initialize(context) }.isSuccess &&
            JarvisRuntime.isInitialized
        val paired = ready && JarvisRuntime.isPaired()
        val live = ready && !JarvisRuntime.stale.value && JarvisRuntime.link.value == LinkState.CONNECTED
        val chosen = if (ready) JarvisRuntime.settings.homeWidgets.value.getOrNull(slot) else null
        val security = if (ready) JarvisRuntime.settings.security.value else null
        // Fails closed: settings that cannot be read count as hidden.
        val hideWords = security == null || security.appLock || security.privateLists

        var view: JarvisWidgets.View? = null
        var message: Pair<String, String>? = null
        when {
            !ready -> message = JarvisWidgets.W_NOT_STARTED to JarvisWidgets.W_NOT_STARTED_SUB
            !paired -> message = JarvisWidgets.W_NOT_PAIRED to JarvisWidgets.W_NOT_PAIRED_SUB
            chosen == null -> message = JarvisWidgets.W_NONE to JarvisWidgets.W_NONE_SUB
            !live -> message = JarvisWidgets.W_STALE to JarvisWidgets.W_STALE_SUB
            else -> when (val r = JarvisRuntime.widgetShow(chosen)) {
                is ApiResult.Ok -> {
                    val v = JarvisWidgets.viewOf(r.value)
                    if (v == null) {
                        message = JarvisWidgets.W_FAILED to JarvisWidgets.W_STALE_SUB
                    } else {
                        view = if (hideWords) JarvisWidgets.hide(v) else v
                    }
                }
                is ApiResult.Failed -> message = if (r.error == ApiError.NotFound) {
                    JarvisWidgets.W_GONE to JarvisWidgets.W_NONE_SUB
                } else {
                    JarvisWidgets.W_FAILED to JarvisWidgets.W_STALE_SUB
                }
            }
        }

        provideContent {
            Box(
                modifier = GlanceModifier
                    .fillMaxSize()
                    .background(BoardPalette.Background)
                    .cornerRadius(16.dp)
                    .padding(12.dp),
            ) {
                val m = message
                val v = view
                if (m != null || v == null) {
                    MessageState(m?.first ?: JarvisWidgets.W_FAILED, m?.second ?: JarvisWidgets.W_STALE_SUB)
                } else {
                    Board(context, v)
                }
            }
        }
    }

    @Composable
    private fun MessageState(headline: String, sub: String) {
        Column(
            modifier = GlanceModifier.fillMaxSize().clickable(actionStartActivity<MainActivity>()),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = headline,
                style = TextStyle(color = BoardPalette.TextHi, fontSize = 12.sp, fontWeight = FontWeight.Bold),
            )
            Spacer(GlanceModifier.height(2.dp))
            Text(sub, style = TextStyle(color = BoardPalette.TextMuted, fontSize = 11.sp))
        }
    }

    @Composable
    private fun Board(context: Context, view: JarvisWidgets.View) {
        val buttons = view.blocks.filterIsInstance<JarvisWidgets.Block.Button>()
        Column(modifier = GlanceModifier.fillMaxSize()) {
            Column(
                modifier = GlanceModifier.defaultWeight().fillMaxWidth()
                    .clickable(actionStartActivity<MainActivity>()),
            ) {
                for (b in view.blocks) {
                    when (b) {
                        is JarvisWidgets.Block.Title -> Text(
                            b.text, maxLines = 1,
                            style = TextStyle(color = BoardPalette.TextHi, fontSize = 14.sp, fontWeight = FontWeight.Bold),
                        )
                        is JarvisWidgets.Block.Count -> {
                            Row(modifier = GlanceModifier.fillMaxWidth()) {
                                Text(b.label, maxLines = 1, style = small(BoardPalette.TextMuted))
                                Spacer(GlanceModifier.defaultWeight())
                                if (b.value.isNotEmpty()) {
                                    Text(b.value, style = TextStyle(color = BoardPalette.Accent, fontSize = 13.sp, fontWeight = FontWeight.Bold))
                                }
                            }
                            if (b.note.isNotEmpty()) Text(b.note, maxLines = 1, style = small(BoardPalette.TextMuted))
                        }
                        is JarvisWidgets.Block.Items -> {
                            Text(b.label, maxLines = 1, style = small(BoardPalette.TextMuted))
                            for ((words, whenWords) in b.items) {
                                Text(
                                    if (whenWords.isEmpty()) words else "$whenWords  $words",
                                    maxLines = 1, style = small(BoardPalette.TextHi),
                                )
                            }
                            if (b.more > 0) Text("+${b.more} more", style = small(BoardPalette.Accent))
                            if (b.items.isEmpty() && b.note.isEmpty() && b.empty.isNotEmpty()) {
                                Text(b.empty, maxLines = 1, style = small(BoardPalette.TextMuted))
                            }
                            if (b.note.isNotEmpty()) Text(b.note, maxLines = 1, style = small(BoardPalette.TextMuted))
                        }
                        is JarvisWidgets.Block.Progress -> {
                            Row(modifier = GlanceModifier.fillMaxWidth()) {
                                Text(b.label, maxLines = 1, style = small(BoardPalette.TextMuted))
                                Spacer(GlanceModifier.defaultWeight())
                                if (b.value.isNotEmpty()) Text(b.value, maxLines = 1, style = small(BoardPalette.TextHi))
                            }
                            LinearProgressIndicator(
                                progress = b.fraction.toFloat(),
                                modifier = GlanceModifier.fillMaxWidth().height(4.dp),
                                color = BoardPalette.Accent,
                                backgroundColor = BoardPalette.Surface1,
                            )
                            if (b.note.isNotEmpty()) Text(b.note, maxLines = 1, style = small(BoardPalette.TextMuted))
                        }
                        is JarvisWidgets.Block.Button -> Unit
                    }
                    Spacer(GlanceModifier.height(3.dp))
                }
            }
            // Two to a row, so four still fit a 4x2 widget.
            for (pair in buttons.chunked(2)) {
                Spacer(GlanceModifier.height(4.dp))
                Row(modifier = GlanceModifier.fillMaxWidth()) {
                    pair.forEachIndexed { i, b ->
                        if (i > 0) Spacer(GlanceModifier.width(6.dp))
                        PillButton(b.label, press(context, b.action), GlanceModifier.defaultWeight())
                    }
                }
            }
        }
    }

    private fun small(color: ColorProvider) = TextStyle(color = color, fontSize = 11.sp)

    /** "Brief me" opens the app straight from the tap (the tile's own
     *  OpenBriefing); every other button goes through [BoardButtonCallback]. */
    private fun press(context: Context, action: TileAction): Action =
        if (action == TileAction.BRIEF_ME) {
            actionStartActivityIntent(
                Intent(context, MainActivity::class.java)
                    .setAction(MainActivity.ACTION_OPEN_BRIEFING)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            )
        } else {
            actionRunCallback<BoardButtonCallback>(actionParametersOf(BoardButtonCallback.PARAM_ACTION to action.wire))
        }

    @Composable
    private fun PillButton(label: String, onClick: Action, modifier: GlanceModifier) {
        Box(
            modifier = modifier
                .background(BoardPalette.Surface1)
                .cornerRadius(10.dp)
                .clickable(onClick)
                .padding(vertical = 8.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(label, maxLines = 1, style = TextStyle(color = BoardPalette.Accent, fontSize = 12.sp, fontWeight = FontWeight.Bold))
        }
    }
}

/** Slot 1 ("Jarvis widget 1" in the launcher's widget list). */
class JarvisBoardWidgetOne : JarvisBoardWidget(0)

/** Slot 2. */
class JarvisBoardWidgetTwo : JarvisBoardWidget(1)

/** Slot 3. */
class JarvisBoardWidgetThree : JarvisBoardWidget(2)

class JarvisBoardWidgetOneReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = JarvisBoardWidgetOne()
}

class JarvisBoardWidgetTwoReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = JarvisBoardWidgetTwo()
}

class JarvisBoardWidgetThreeReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = JarvisBoardWidgetThree()
}

/** Redraws all three slots (each reads the PC again when it draws). */
object JarvisBoardWidgets {
    suspend fun updateAll(context: Context) {
        runCatching { JarvisBoardWidgetOne().updateAll(context) }
        runCatching { JarvisBoardWidgetTwo().updateAll(context) }
        runCatching { JarvisBoardWidgetThree().updateAll(context) }
    }
}

/**
 * One button on a home-screen Jarvis widget: the Quick Settings tile's own
 * decision ([QuickTiles.decide]) and action ([QuickTileService.perform]).
 * A widget cannot ask for the phone's unlock the way a tile can, so App
 * lock with a locked phone says so instead; the home screen is only seen
 * unlocked, so that is rare.
 */
class BoardButtonCallback : ActionCallback {

    override suspend fun onAction(context: Context, glanceId: GlanceId, parameters: ActionParameters) {
        val action = TileAction.fromWire(parameters[PARAM_ACTION]) ?: return
        val app = context.applicationContext
        runCatching { JarvisRuntime.initialize(app) }
        if (!JarvisRuntime.isInitialized) return
        val paired = JarvisRuntime.isPaired()
        val decision = QuickTiles.decide(
            action = action,
            paired = paired,
            connected = JarvisRuntime.link.value == LinkState.CONNECTED,
            stale = JarvisRuntime.stale.value,
            appLock = JarvisRuntime.settings.security.value.appLock,
            phoneLocked = QuickTileService.phoneLocked(app),
            staleWords = PlainErrors.shown("link_stale").text,
        )
        when (decision) {
            QuickTiles.Decision.Run -> QuickTileService.perform(app, action)
            is QuickTiles.Decision.Held -> QuickTileService.say(app, decision.why)
            QuickTiles.Decision.Reconnect -> {
                if (paired) EventService.start(app)
                QuickTileService.say(app, JarvisWidgets.W_STALE_SUB)
            }
            QuickTiles.Decision.UnlockThenRun -> QuickTileService.say(app, UNLOCK_FIRST)
            // Not reached: "Brief me" opens the app from the tap itself, and
            // a button always has an action.
            QuickTiles.Decision.OpenBriefing, QuickTiles.Decision.OpenChooser ->
                runCatching { Toast.makeText(app, JarvisWidgets.W_STALE_SUB, Toast.LENGTH_SHORT).show() }
        }
    }

    companion object {
        val PARAM_ACTION = ActionParameters.Key<String>("board_action")
        const val UNLOCK_FIRST = "Unlock your phone first, then tap it again."
    }
}

/** The widget's own fixed colours - [ApprovalWidget]'s set, for the same reason. */
private object BoardPalette {
    val Background = ColorProvider(Color(0xFF04070C))
    val Surface1 = ColorProvider(Color(0xFF0E1822))
    val TextHi = ColorProvider(Color(0xFFE6EEF7))
    val TextMuted = ColorProvider(Color(0xFF93A6BA))
    val Accent = ColorProvider(Color(0xFF63F7FF))
}
