package com.jarvis.assistant.data.repository

import android.content.Context
import androidx.glance.appwidget.updateAll
import com.jarvis.assistant.JarvisRuntime
import com.jarvis.assistant.network.ApprovalRequestEvent
import com.jarvis.assistant.network.ConnectionState
import com.jarvis.assistant.widget.approval.ApprovalWidget
import com.jarvis.assistant.widget.launcher.QuickLauncherWidget
import com.jarvis.assistant.widget.telemetry.TelemetryWidget
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

/**
 * Bridges live app state onto the home screen.
 *
 * Deliberately holds no state of its own. An earlier design kept its own
 * approval list and telemetry snapshot, which is a second source of truth that
 * drifts from [JarvisRuntime] the moment an approval resolves anywhere else —
 * from the lock-screen notification, say. This reads the runtime's flows and
 * pushes a redraw when they change, so widgets cannot disagree with the app.
 *
 * Nothing polls. Redraws happen only when an event actually moves the state.
 */
object WidgetDataRepository {

    data class ApprovalItem(
        val id: String,
        val action: String,
        val tier: String,
        val detail: String,
        val target: String? = null,
    )

    data class TelemetrySnapshot(
        val gpuTempC: Int? = null,
        val gpuPercent: Int? = null,
        val vramUsedMb: Int? = null,
        val vramTotalMb: Int? = null,
        val cpuPercent: Int? = null,
        val routeLane: String? = null,
        val model: String? = null,
        val isOnline: Boolean = false,
    ) {
        val hasData: Boolean
            get() = gpuTempC != null || cpuPercent != null || vramUsedMb != null
    }

    data class LinkStatus(val online: Boolean, val latencyMs: Long?)

    /** GPU designs throttle around here, so it is the point worth flagging. */
    const val GPU_WARN_C = 75

    fun getPendingApprovals(): List<ApprovalItem> {
        if (!JarvisRuntime.isInitialized) return emptyList()
        return JarvisRuntime.pendingApprovals.value.map(::toItem)
    }

    fun getTelemetry(): TelemetrySnapshot {
        if (!JarvisRuntime.isInitialized) return TelemetrySnapshot()
        val desktop = JarvisRuntime.desktopTelemetry.value
        val online = JarvisRuntime.socket.state.value == ConnectionState.CONNECTED
        return TelemetrySnapshot(
            gpuTempC = desktop?.gpuTempC?.toInt(),
            gpuPercent = desktop?.gpuPercent?.toInt(),
            vramUsedMb = desktop?.vramUsedMb?.toInt(),
            vramTotalMb = desktop?.vramTotalMb?.toInt(),
            cpuPercent = desktop?.cpuPercent?.toInt(),
            routeLane = desktop?.routeLane,
            model = desktop?.model,
            isOnline = online,
        )
    }

    fun getConnectionStatus(): LinkStatus {
        if (!JarvisRuntime.isInitialized) return LinkStatus(online = false, latencyMs = null)
        val online = JarvisRuntime.socket.state.value == ConnectionState.CONNECTED
        return LinkStatus(online, JarvisRuntime.latencyMs.value.takeIf { online })
    }

    /** True when signing is impossible, so the widget can say so instead of failing silently. */
    fun isUnpaired(): Boolean =
        JarvisRuntime.isInitialized && JarvisRuntime.settings.sharedSecret.isEmpty()

    private fun toItem(event: ApprovalRequestEvent) = ApprovalItem(
        id = event.id,
        action = event.title,
        tier = event.tier,
        detail = event.summary.ifBlank {
            event.note?.markdown ?: event.note?.after ?: event.detail.orEmpty()
        },
        target = event.note?.let { if (it.isJoplin) "JOPLIN" else "LOGSEQ" },
    )

    /**
     * Starts pushing redraws. Called once from the runtime; each widget family
     * is woken only by the state it actually renders.
     */
    fun observe(context: Context, scope: CoroutineScope) {
        val app = context.applicationContext

        scope.launch {
            JarvisRuntime.pendingApprovals
                .map { list -> list.map(ApprovalRequestEvent::id) }
                .distinctUntilChanged()
                .collect { ApprovalWidget().updateAll(app) }
        }

        scope.launch {
            // No distinctUntilChanged: a StateFlow already conflates equal values,
            // and kotlinx deprecates the operator on StateFlow at ERROR level.
            JarvisRuntime.desktopTelemetry
                .collect { TelemetryWidget().updateAll(app) }
        }

        scope.launch {
            combine(
                JarvisRuntime.socket.state,
                JarvisRuntime.latencyMs,
            ) { state, latency -> state to latency }
                .distinctUntilChanged()
                .collect {
                    QuickLauncherWidget().updateAll(app)
                    // Connectivity gates the telemetry card's live/stale styling.
                    TelemetryWidget().updateAll(app)
                }
        }
    }
}
