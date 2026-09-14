package com.jarvis.assistant.widget.launcher

import android.content.Context
import android.content.Intent
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.action.Action
import androidx.glance.action.actionStartActivity
import androidx.glance.appwidget.action.actionStartActivity as actionStartActivityIntent
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.layout.Alignment
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.padding
import androidx.glance.layout.width
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import com.jarvis.assistant.MainActivity
import com.jarvis.assistant.data.repository.WidgetDataRepository
import com.jarvis.assistant.widget.PillButton
import com.jarvis.assistant.widget.StatusDot
import com.jarvis.assistant.widget.theme.JarvisGlanceTheme

/** Link status plus the four things worth reaching without opening the app. */
class QuickLauncherWidget : GlanceAppWidget() {

    override val sizeMode: SizeMode = SizeMode.Exact

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        // Deliberately does not probe latency here. Doing so was a feedback loop:
        // the pong wrote a new round-trip time, the repository observed it and
        // called updateAll, which re-ran this function, which probed again. Round
        // trips jitter by a millisecond nearly every time, so nothing upstream
        // conflated it away. The value shown is whatever the last connect or the
        // last real traffic measured.
        val status = WidgetDataRepository.getConnectionStatus()

        provideContent {
            Row(
                modifier = GlanceModifier
                    .fillMaxSize()
                    .background(JarvisGlanceTheme.Background)
                    .cornerRadius(24.dp)
                    .padding(horizontal = 14.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                StatusDot(online = status.online)
                Spacer(GlanceModifier.width(8.dp))
                Text(
                    text = when {
                        !status.online -> "Offline"
                        status.latencyMs != null -> "${status.latencyMs}ms"
                        else -> "Linked"
                    },
                    style = TextStyle(
                        color = JarvisGlanceTheme.TextMuted,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Medium,
                    ),
                )

                Spacer(GlanceModifier.defaultWeight())

                ActionPill("Mic", JarvisGlanceTheme.Primary, route(context, MainActivity.ACTION_START_VOICE))
                Spacer(GlanceModifier.width(6.dp))
                ActionPill("#log", JarvisGlanceTheme.TextPrimary, capture(context, "logseq"))
                Spacer(GlanceModifier.width(6.dp))
                ActionPill("#joplin", JarvisGlanceTheme.TextPrimary, capture(context, "joplin"))
                Spacer(GlanceModifier.width(6.dp))
                ActionPill("HUD", JarvisGlanceTheme.TextMuted, actionStartActivity<MainActivity>())
            }
        }
    }

    @Composable
    private fun ActionPill(label: String, tint: androidx.glance.unit.ColorProvider, onClick: Action) {
        PillButton(
            label = label,
            tint = tint,
            background = JarvisGlanceTheme.SurfaceRaised,
            onClick = onClick,
        )
    }

    private fun route(context: Context, action: String): Action =
        actionStartActivityIntent(
            Intent(context, MainActivity::class.java)
                .setAction(action)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
        )

    private fun capture(context: Context, target: String): Action =
        actionStartActivityIntent(
            Intent(context, MainActivity::class.java)
                .setAction(MainActivity.ACTION_QUICK_CAPTURE)
                .putExtra(MainActivity.EXTRA_CAPTURE_TARGET, target)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
        )
}
