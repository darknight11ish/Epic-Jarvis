package com.jarvis.client.widget

import android.content.Context
import androidx.compose.runtime.Composable
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
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.action.ActionCallback
import androidx.glance.appwidget.action.actionRunCallback
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.appwidget.updateAll
import androidx.glance.background
import androidx.glance.unit.ColorProvider
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
import androidx.compose.ui.graphics.Color
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.LinkState
import com.jarvis.client.MainActivity
import com.jarvis.client.net.PendingItem

/**
 * The oldest unresolved approval, on the home screen.
 *
 * Ported from the retired `jarvis-android/`'s own approval widget, with one
 * deliberate change from that original: this one **only ever lets Deny be a
 * one-tap widget action**. The old widget wired both Approve and Deny to the
 * same one-tap `ActionCallback` - which was fine for that app's own rules at
 * the time, but this app's `docs/ARCHITECTURE.md` (via the desktop thread)
 * states the rule this project actually runs on: *"Deny may be a
 * notification action. Approve may not... Approving means opening the
 * app."* `ApprovalNotifier.kt`'s own lock-screen action already only ever
 * wires Deny for exactly this reason. Copying the old widget's Approve
 * button verbatim would have been a real regression against that rule, not
 * a faithful port of it - so Approve here opens [MainActivity] instead,
 * where the real card and its biometric gate (`BiometricGate.kt`) decide
 * whether the tap actually counts.
 *
 * Holds no state of its own, on purpose - the same reasoning
 * `WidgetDataRepository`'s own doc comment gives in the retired app: a
 * second source of truth drifts from [JarvisRuntime] the moment an approval
 * resolves anywhere else, the lock-screen notification included. This reads
 * [JarvisRuntime.pending] fresh every time it draws and nothing more.
 */
class ApprovalWidget : GlanceAppWidget() {

    override val sizeMode: SizeMode = SizeMode.Exact

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        JarvisRuntime.initialize(context)
        val pending = if (JarvisRuntime.isInitialized) JarvisRuntime.pending.value else emptyList()
        val paired = JarvisRuntime.isInitialized && JarvisRuntime.isPaired()
        val connected = JarvisRuntime.isInitialized && JarvisRuntime.link.value == LinkState.CONNECTED
        val extra = (pending.size - 1).coerceAtLeast(0)

        provideContent {
            Box(
                modifier = GlanceModifier
                    .fillMaxSize()
                    .background(Palette.Background)
                    .cornerRadius(16.dp)
                    .padding(12.dp),
            ) {
                when {
                    pending.isEmpty() -> EmptyState(connected)
                    !paired -> MessageState("Approvals need a pairing token", "Tap to open Jarvis and pair")
                    !connected -> MessageState(
                        "Approvals pending — desktop unreachable",
                        "Tap to open Jarvis and reconnect",
                    )
                    else -> ActiveApproval(pending.first(), extra)
                }
            }
        }
    }

    @Composable
    private fun EmptyState(connected: Boolean) {
        Row(
            modifier = GlanceModifier.fillMaxSize().clickable(actionStartActivity<MainActivity>()),
            verticalAlignment = Alignment.CenterVertically,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = if (connected) "Nothing waiting" else "Nothing waiting — desktop unreachable",
                style = TextStyle(
                    color = if (connected) Palette.TextMuted else Palette.StatusBad,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                ),
            )
        }
    }

    /** Pairing or connectivity stands between here and a real decision - say
     *  so and open the app, rather than showing buttons that would refuse. */
    @Composable
    private fun MessageState(headline: String, sub: String) {
        Column(
            modifier = GlanceModifier.fillMaxSize().clickable(actionStartActivity<MainActivity>()),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = headline,
                style = TextStyle(color = Palette.StatusBad, fontSize = 12.sp, fontWeight = FontWeight.Bold),
            )
            Spacer(GlanceModifier.height(2.dp))
            Text(sub, style = TextStyle(color = Palette.TextMuted, fontSize = 11.sp))
        }
    }

    @Composable
    private fun ActiveApproval(item: PendingItem, extra: Int) {
        Column(modifier = GlanceModifier.fillMaxSize()) {
            Row(
                modifier = GlanceModifier.fillMaxWidth().clickable(actionStartActivity<MainActivity>()),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "Jarvis wants to:",
                    style = TextStyle(color = Palette.Accent, fontSize = 11.sp, fontWeight = FontWeight.Bold),
                )
                Spacer(GlanceModifier.defaultWeight())
                Badge(item.tier.uppercase())
            }

            Spacer(GlanceModifier.height(4.dp))

            Column(
                modifier = GlanceModifier.defaultWeight().fillMaxWidth()
                    .clickable(actionStartActivity<MainActivity>()),
            ) {
                Text(text = item.title, maxLines = 1, style = TextStyle(
                    color = Palette.TextHi, fontSize = 14.sp, fontWeight = FontWeight.Bold,
                ))
                if (item.summary.isNotBlank()) {
                    Text(
                        text = item.summary,
                        maxLines = 2,
                        style = TextStyle(color = Palette.TextMuted, fontSize = 11.sp),
                    )
                }
            }

            if (extra > 0) {
                Text(
                    text = "+$extra more waiting",
                    style = TextStyle(color = Palette.Accent, fontSize = 10.sp),
                )
                Spacer(GlanceModifier.height(4.dp))
            }

            Row(modifier = GlanceModifier.fillMaxWidth()) {
                // Approve opens the app - never a one-tap widget action. See
                // the class doc for why this is not the retired app's shape.
                PillButton(
                    label = "Review",
                    tint = Palette.StatusOk,
                    onClick = actionStartActivity<MainActivity>(),
                    modifier = GlanceModifier.defaultWeight(),
                )
                Spacer(GlanceModifier.width(8.dp))
                // Deny alone is a direct widget action - refusing is always
                // the safe direction, the same rule the lock-screen
                // notification's own Deny action already runs on.
                PillButton(
                    label = "Deny",
                    tint = Palette.StatusBad,
                    onClick = actionRunCallback<DenyActionCallback>(
                        actionParametersOf(DenyActionCallback.PARAM_ID to item.id),
                    ),
                    modifier = GlanceModifier.defaultWeight(),
                )
            }
        }
    }

    @Composable
    private fun Badge(label: String) {
        Box(
            modifier = GlanceModifier.background(Palette.Surface1).cornerRadius(4.dp)
                .padding(horizontal = 6.dp, vertical = 2.dp),
        ) {
            Text(label, style = TextStyle(color = Palette.Accent, fontSize = 10.sp, fontWeight = FontWeight.Bold))
        }
    }

    @Composable
    private fun PillButton(
        label: String,
        tint: ColorProvider,
        onClick: Action,
        modifier: GlanceModifier = GlanceModifier,
    ) {
        // `defaultWeight()` is a RowScope/ColumnScope-scoped extension, not a
        // free function - it only resolves where that scope's receiver is
        // implicitly in view. This function's own body is neither, so
        // callers apply it themselves (see the Row above) and pass the
        // result in, the same shape the retired app's own PillButton used.
        Box(
            modifier = modifier
                .background(Palette.Surface1)
                .cornerRadius(10.dp)
                .clickable(onClick)
                .padding(vertical = 8.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = label,
                style = TextStyle(color = tint, fontSize = 12.sp, fontWeight = FontWeight.Bold),
            )
        }
    }
}

/** A flat, static palette for the widget - Glance's own RemoteViews host has
 *  no access to this app's dynamic per-face [com.jarvis.client.ui.theme.Chrome],
 *  so this is deliberately a small, fixed set rather than an attempt to
 *  reach into that system from a different composition entirely. */
private object Palette {
    val Background = ColorProvider(Color(0xFF04070C))
    val Surface1 = ColorProvider(Color(0xFF0E1822))
    val TextHi = ColorProvider(Color(0xFFE6EEF7))
    val TextMuted = ColorProvider(Color(0xFF93A6BA))
    val Accent = ColorProvider(Color(0xFF63F7FF))
    val StatusOk = ColorProvider(Color(0xFF6EE7A8))
    val StatusBad = ColorProvider(Color(0xFFEF6E6E))
}

class ApprovalWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = ApprovalWidget()
}

/**
 * Denies one approval from the home screen, no confirmation beyond the tap.
 *
 * Deliberately the ONLY decision this widget can make directly - see
 * [ApprovalWidget]'s own doc comment. This does not build a second signing
 * path: [JarvisRuntime.decideDetached] is the same call the in-app card and
 * the lock-screen notification's own Deny action already use.
 */
class DenyActionCallback : ActionCallback {

    override suspend fun onAction(
        context: Context,
        glanceId: GlanceId,
        parameters: ActionParameters,
    ) {
        val id = parameters[PARAM_ID] ?: return
        JarvisRuntime.initialize(context)
        if (!JarvisRuntime.isInitialized) return
        val item = JarvisRuntime.pending.value.firstOrNull { it.id == id } ?: return
        JarvisRuntime.decideDetached(item, approve = false)
        // decide() calls refreshPending() itself, but that lands on the
        // runtime's own scope on its own schedule - redrawing here as well
        // means the widget does not sit showing an already-denied item until
        // that unrelated timing happens to catch up.
        ApprovalWidget().updateAll(context)
    }

    companion object {
        val PARAM_ID = ActionParameters.Key<String>("approval_id")
    }
}
