package com.jarvis.assistant.widget.approval

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.action.actionParametersOf
import androidx.glance.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.action.actionRunCallback
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
import androidx.glance.layout.width
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import com.jarvis.assistant.MainActivity
import com.jarvis.assistant.data.repository.WidgetDataRepository
import com.jarvis.assistant.widget.PillButton
import com.jarvis.assistant.widget.StatusDot
import com.jarvis.assistant.widget.theme.JarvisGlanceTheme

/** The oldest unresolved `ask` request, with the decision buttons attached. */
class ApprovalWidget : GlanceAppWidget() {

    override val sizeMode: SizeMode = SizeMode.Exact

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val pending = WidgetDataRepository.getPendingApprovals()
        val unpaired = WidgetDataRepository.isUnpaired()
        val deliverable = WidgetDataRepository.canDecideNow()
        val extra = (pending.size - 1).coerceAtLeast(0)

        provideContent {
            Box(
                modifier = GlanceModifier
                    .fillMaxSize()
                    .background(JarvisGlanceTheme.Background)
                    .cornerRadius(16.dp)
                    .padding(12.dp),
            ) {
                when {
                    pending.isEmpty() -> EmptyState()
                    unpaired -> UnpairedState()
                    // The runtime refuses to sign a decision it cannot deliver, so
                    // buttons here would buzz and do nothing.
                    !deliverable -> OfflineState()
                    else -> ActiveApproval(pending.first(), extra)
                }
            }
        }
    }

    @Composable
    private fun EmptyState() {
        Row(
            modifier = GlanceModifier.fillMaxSize(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            StatusDot(online = true, size = 8)
            Spacer(GlanceModifier.width(8.dp))
            Text(
                text = "Systems nominal · No pending approvals",
                style = TextStyle(
                    color = JarvisGlanceTheme.TextMuted,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                ),
            )
        }
    }

    /**
     * Signing is impossible without a secret, so the widget says so rather than
     * showing buttons that would silently refuse.
     */
    @Composable
    private fun UnpairedState() {
        Column(
            modifier = GlanceModifier
                .fillMaxSize()
                .clickable(actionStartActivity<MainActivity>()),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "Approvals need a pairing secret",
                style = TextStyle(
                    color = JarvisGlanceTheme.StatusBad,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                ),
            )
            Spacer(GlanceModifier.height(2.dp))
            Text("Tap to set one in the HUD", style = JarvisGlanceTheme.Label)
        }
    }

    /**
     * Pending approvals exist but the link is down.
     *
     * Showing Approve and Deny here would be a tap that appears to answer and does
     * not: the decision cannot be signed and delivered while the event stream is
     * stale, so the widget names the reason and opens the HUD instead.
     */
    @Composable
    private fun OfflineState() {
        Column(
            modifier = GlanceModifier
                .fillMaxSize()
                .clickable(actionStartActivity<MainActivity>()),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "Approvals pending — desktop unreachable",
                style = TextStyle(
                    color = JarvisGlanceTheme.StatusBad,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                ),
            )
            Spacer(GlanceModifier.height(2.dp))
            Text("Tap to open the HUD and reconnect", style = JarvisGlanceTheme.Label)
        }
    }

    @Composable
    private fun ActiveApproval(item: WidgetDataRepository.ApprovalItem, extra: Int) {
        Column(modifier = GlanceModifier.fillMaxSize()) {
            Row(
                modifier = GlanceModifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "Jarvis wants to:",
                    style = TextStyle(
                        color = JarvisGlanceTheme.Primary,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                    ),
                )
                Spacer(GlanceModifier.defaultWeight())
                item.target?.let {
                    Badge(it, JarvisGlanceTheme.Primary)
                    Spacer(GlanceModifier.width(4.dp))
                }
                Badge(item.tier.uppercase(), JarvisGlanceTheme.AccentGold)
            }

            Spacer(GlanceModifier.height(4.dp))

            Text(text = item.action, maxLines = 1, style = JarvisGlanceTheme.Title)

            Text(
                text = item.detail,
                maxLines = 2,
                modifier = GlanceModifier.defaultWeight(),
                style = TextStyle(color = JarvisGlanceTheme.TextMuted, fontSize = 11.sp),
            )

            if (extra > 0) {
                Text(
                    text = "+$extra more waiting",
                    style = TextStyle(color = JarvisGlanceTheme.AccentGold, fontSize = 10.sp),
                )
                Spacer(GlanceModifier.height(4.dp))
            }

            Row(modifier = GlanceModifier.fillMaxWidth()) {
                PillButton(
                    label = "Approve",
                    tint = JarvisGlanceTheme.StatusOk,
                    background = JarvisGlanceTheme.SurfaceRaised,
                    onClick = actionRunCallback<ApprovalActionCallback>(
                        actionParametersOf(
                            ApprovalActionCallback.PARAM_ID to item.id,
                            ApprovalActionCallback.PARAM_DECISION to true,
                        ),
                    ),
                    modifier = GlanceModifier.defaultWeight(),
                )
                Spacer(GlanceModifier.width(8.dp))
                PillButton(
                    label = "Deny",
                    tint = JarvisGlanceTheme.StatusBad,
                    background = JarvisGlanceTheme.SurfaceRaised,
                    onClick = actionRunCallback<ApprovalActionCallback>(
                        actionParametersOf(
                            ApprovalActionCallback.PARAM_ID to item.id,
                            ApprovalActionCallback.PARAM_DECISION to false,
                        ),
                    ),
                    modifier = GlanceModifier.defaultWeight(),
                )
            }
        }
    }

    @Composable
    private fun Badge(label: String, tint: androidx.glance.unit.ColorProvider) {
        Box(
            modifier = GlanceModifier
                .background(JarvisGlanceTheme.SurfaceRaised)
                .cornerRadius(4.dp)
                .padding(horizontal = 6.dp, vertical = 2.dp),
        ) {
            Text(
                text = label,
                style = TextStyle(color = tint, fontSize = 10.sp, fontWeight = FontWeight.Bold),
            )
        }
    }
}
