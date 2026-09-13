package com.jarvis.assistant.widget.telemetry

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.layout.Alignment
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
import com.jarvis.assistant.MainActivity
import com.jarvis.assistant.data.repository.WidgetDataRepository
import com.jarvis.assistant.widget.theme.JarvisGlanceTheme
import kotlin.math.roundToInt

/** Desktop vitals from `desktop_telemetry` frames. */
class TelemetryWidget : GlanceAppWidget() {

    override val sizeMode: SizeMode = SizeMode.Exact

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val snapshot = WidgetDataRepository.getTelemetry()

        provideContent {
            Column(
                modifier = GlanceModifier
                    .fillMaxSize()
                    .background(JarvisGlanceTheme.Background)
                    .cornerRadius(16.dp)
                    .clickable(actionStartActivity<MainActivity>())
                    .padding(12.dp),
            ) {
                Row(
                    modifier = GlanceModifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("WORKSTATION", style = JarvisGlanceTheme.Label)
                    Spacer(GlanceModifier.defaultWeight())
                    Text(
                        text = if (snapshot.isOnline) "LIVE" else "OFFLINE",
                        style = TextStyle(
                            color = if (snapshot.isOnline) {
                                JarvisGlanceTheme.StatusOk
                            } else {
                                JarvisGlanceTheme.StatusBad
                            },
                            fontSize = 9.sp,
                            fontWeight = FontWeight.Bold,
                        ),
                    )
                }

                Spacer(GlanceModifier.height(8.dp))

                if (!snapshot.hasData) {
                    Text(
                        text = if (snapshot.isOnline) "Awaiting telemetry" else "Desktop offline",
                        style = TextStyle(color = JarvisGlanceTheme.TextMuted, fontSize = 12.sp),
                    )
                    return@Column
                }

                val hot = (snapshot.gpuTempC ?: 0) >= WidgetDataRepository.GPU_WARN_C
                Metric(
                    label = "GPU",
                    value = snapshot.gpuTempC?.let { "$it°C" } ?: "—",
                    tint = if (hot) JarvisGlanceTheme.StatusBad else JarvisGlanceTheme.Primary,
                    // Stale numbers styled as live numbers is the failure mode
                    // worth avoiding on an always-visible surface.
                    stale = !snapshot.isOnline,
                )
                Spacer(GlanceModifier.height(6.dp))
                val vramTight = isVramTight(snapshot.vramUsedMb, snapshot.vramTotalMb)
                Metric(
                    label = "VRAM",
                    value = formatVram(snapshot.vramUsedMb, snapshot.vramTotalMb),
                    tint = if (vramTight) {
                        JarvisGlanceTheme.StatusBad
                    } else {
                        JarvisGlanceTheme.TextPrimary
                    },
                    stale = !snapshot.isOnline,
                )
                Spacer(GlanceModifier.height(6.dp))
                val cpuBusy = (snapshot.cpuPercent ?: 0) >= WidgetDataRepository.CPU_WARN_PERCENT
                Metric(
                    label = "CPU",
                    value = snapshot.cpuPercent?.let { "$it%" } ?: "—",
                    tint = if (cpuBusy) {
                        JarvisGlanceTheme.StatusBad
                    } else {
                        JarvisGlanceTheme.TextPrimary
                    },
                    stale = !snapshot.isOnline,
                )

                Spacer(GlanceModifier.defaultWeight())

                val cloud = snapshot.routeLane.equals("cloud", ignoreCase = true)
                Text(
                    text = buildString {
                        append(if (cloud) "Cloud" else "Local")
                        snapshot.model?.let { append(": ").append(it) }
                    },
                    maxLines = 1,
                    style = TextStyle(
                        color = if (cloud) JarvisGlanceTheme.AccentGold else JarvisGlanceTheme.StatusOk,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Medium,
                    ),
                )
            }
        }
    }

    @Composable
    private fun Metric(label: String, value: String, tint: ColorProvider, stale: Boolean) {
        Row(
            modifier = GlanceModifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(label, style = JarvisGlanceTheme.Label)
            Spacer(GlanceModifier.defaultWeight())
            Text(
                text = value,
                maxLines = 1,
                style = TextStyle(
                    color = if (stale) JarvisGlanceTheme.TextMuted else tint,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                ),
            )
        }
    }

    private fun isVramTight(usedMb: Int?, totalMb: Int?): Boolean {
        if (usedMb == null || totalMb == null || totalMb <= 0) return false
        return usedMb.toDouble() / totalMb >= WidgetDataRepository.VRAM_WARN_FRACTION
    }

    private fun formatVram(usedMb: Int?, totalMb: Int?): String {
        if (usedMb == null) return "—"
        val used = (usedMb / 1024.0 * 10).roundToInt() / 10.0
        if (totalMb == null || totalMb <= 0) return "$used GB"
        val total = (totalMb / 1024.0 * 10).roundToInt() / 10.0
        return "$used / $total GB"
    }
}
