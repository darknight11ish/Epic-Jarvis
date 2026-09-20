package com.jarvis.client.widget

import android.content.Context
import android.content.Intent
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.action.Action
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
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.padding
import androidx.glance.layout.width
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.LinkState
import com.jarvis.client.MainActivity

/**
 * Link status plus a one-tap Mic, on the home screen.
 *
 * Ported from the retired `jarvis-android/`'s own `QuickLauncherWidget`, cut
 * down to what this app can actually back. The original also carried two
 * capture buttons that filed straight to Logseq and Joplin - that app's own
 * backend implemented those; this app's does not, `net/ApiModels.kt` has no
 * note-capture endpoint at all, and a button wired to nothing would be worse
 * than no button. Only the two actions every desktop already supports made
 * the cut: opening the app, and starting the mic.
 *
 * Mic does not record from here - a Glance worker has no microphone access
 * of its own, and would not survive the seconds a capture takes even if it
 * did. It opens [MainActivity] with [MainActivity.ACTION_START_VOICE], which
 * brings the app up on Home with the mic button under the thumb.
 *
 * It does NOT start a capture, and this comment used to claim it "runs the
 * exact same permission-checked MainActivity path the in-app mic button
 * uses". It ran half of that path - the half that opens the microphone.
 * `VoiceSession.begin` stops recording when `releaseRequested` is set, and
 * only [VoiceButton]'s press-and-hold gesture ever sets it; a tap on a tile
 * has no release, so the recorder ran to its 1-120s cap and uploaded the
 * result. Starting the mic from any surface that cannot also END it is the
 * bug, not the wiring, so the tile stops one step short and lets the hold do
 * what only a hold can.
 */
class QuickLinkWidget : GlanceAppWidget() {

    override val sizeMode: SizeMode = SizeMode.Exact

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        // Same guard ApprovalWidget uses, for the same reason: called bare
        // from a Glance worker, a Keystore or preferences failure here is an
        // uncaught exception in the update coroutine, not a screen this app
        // controls.
        val ready = runCatching { JarvisRuntime.initialize(context) }.isSuccess &&
            JarvisRuntime.isInitialized
        val link = if (ready) JarvisRuntime.link.value else LinkState.OFFLINE

        provideContent {
            Row(
                modifier = GlanceModifier
                    .fillMaxSize()
                    .background(QuickLinkPalette.Background)
                    .cornerRadius(24.dp)
                    .padding(horizontal = 14.dp, vertical = 6.dp)
                    .clickable(actionStartActivity<MainActivity>()),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                StatusDot(link)
                Spacer(GlanceModifier.width(8.dp))
                Text(
                    text = when (link) {
                        LinkState.CONNECTED -> "Linked"
                        LinkState.RECONNECTING -> "Reconnecting"
                        LinkState.OFFLINE -> "Offline"
                    },
                    style = TextStyle(
                        color = QuickLinkPalette.TextMuted,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Medium,
                    ),
                )

                Spacer(GlanceModifier.defaultWeight())

                // Reachable even off the link: opening the app to a dropped
                // connection is still useful (Checks screen explains why),
                // where a Deny-style direct action would just fail silently.
                PillButton(label = "Mic", tint = QuickLinkPalette.Accent, onClick = startVoice(context))
            }
        }
    }

    @Composable
    private fun StatusDot(link: LinkState) {
        Box(
            modifier = GlanceModifier
                .background(
                    when (link) {
                        LinkState.CONNECTED -> QuickLinkPalette.StatusOk
                        LinkState.RECONNECTING -> QuickLinkPalette.StatusWarn
                        LinkState.OFFLINE -> QuickLinkPalette.StatusBad
                    },
                )
                .cornerRadius(4.dp)
                .padding(horizontal = 4.dp, vertical = 4.dp),
        ) {}
    }

    @Composable
    private fun PillButton(label: String, tint: ColorProvider, onClick: Action) {
        Box(
            modifier = GlanceModifier
                .background(QuickLinkPalette.Surface1)
                .cornerRadius(10.dp)
                .clickable(onClick)
                .padding(horizontal = 12.dp, vertical = 8.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = label,
                style = TextStyle(color = tint, fontSize = 12.sp, fontWeight = FontWeight.Bold),
            )
        }
    }

    private fun startVoice(context: Context): Action =
        actionStartActivityIntent(
            Intent(context, MainActivity::class.java)
                .setAction(MainActivity.ACTION_START_VOICE)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
        )
}

/**
 * Same fixed set [ApprovalWidget] uses, and for the same reason: a Glance
 * RemoteViews host cannot reach this app's dynamic per-face `Chrome`.
 *
 * Its own object, not `ApprovalWidget`'s `Palette` - a top-level `private`
 * declaration is private to its *file*, but Kotlin still compiles it as an
 * ordinary top-level class, so two files in the same package both naming
 * one `Palette` is a real class-name collision (`Redeclaration`) at compile
 * time, not two independently-scoped names the way the `private` keyword
 * suggests.
 */
private object QuickLinkPalette {
    val Background = ColorProvider(Color(0xFF04070C))
    val Surface1 = ColorProvider(Color(0xFF0E1822))
    val TextMuted = ColorProvider(Color(0xFF93A6BA))
    val Accent = ColorProvider(Color(0xFF63F7FF))
    val StatusOk = ColorProvider(Color(0xFF6EE7A8))
    val StatusWarn = ColorProvider(Color(0xFFE7C76E))
    val StatusBad = ColorProvider(Color(0xFFEF6E6E))
}

class QuickLinkWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = QuickLinkWidget()
}
