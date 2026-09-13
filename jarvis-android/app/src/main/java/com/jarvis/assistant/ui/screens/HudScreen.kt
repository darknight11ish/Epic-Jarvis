package com.jarvis.assistant.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.jarvis.assistant.network.ApprovalRequestEvent
import com.jarvis.assistant.network.ConnectionState
import com.jarvis.assistant.network.DesktopTelemetryEvent
import com.jarvis.assistant.ui.theme.JarvisAmber
import com.jarvis.assistant.ui.theme.JarvisBlack
import com.jarvis.assistant.ui.theme.JarvisCyan
import com.jarvis.assistant.ui.theme.JarvisGreen
import com.jarvis.assistant.ui.theme.JarvisOutline
import com.jarvis.assistant.ui.theme.JarvisRed
import com.jarvis.assistant.ui.theme.JarvisSurface
import com.jarvis.assistant.ui.theme.JarvisTextMuted
import kotlin.math.roundToInt

/**
 * Everything the screen needs, hoisted into one immutable snapshot.
 *
 * Passing a single stable value keeps recomposition scoped to the cards whose
 * numbers actually moved rather than the whole tree on every telemetry frame.
 */
data class HudState(
    val connection: ConnectionState,
    val serverAddress: String,
    val micActive: Boolean,
    val micPermissionGranted: Boolean,
    val desktop: DesktopTelemetryEvent?,
    val approvals: List<ApprovalRequestEvent>,
    val statusText: String?,
    val lastError: String?,
    /** True once Android has been told to stop dozing this app. */
    val batteryExempt: Boolean,
)

data class HudActions(
    val onServerAddressChange: (String) -> Unit,
    val onReconnect: () -> Unit,
    val onToggleMic: () -> Unit,
    val onApprove: (String) -> Unit,
    val onReject: (String) -> Unit,
    val onRequestBatteryExemption: () -> Unit,
)

@Composable
fun HudScreen(state: HudState, actions: HudActions, modifier: Modifier = Modifier) {
    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .background(JarvisBlack)
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "header") {
            Spacer(Modifier.height(20.dp))
            ConnectionHeader(state.connection, state.lastError)
        }

        item(key = "server") {
            ServerAddressField(
                address = state.serverAddress,
                onCommit = actions.onServerAddressChange,
                onReconnect = actions.onReconnect,
            )
        }

        if (!state.batteryExempt) {
            item(key = "battery") {
                WarningCard(
                    text = "Android may sleep the link while locked. Allow unrestricted background battery usage.",
                    actionLabel = "Fix",
                    onAction = actions.onRequestBatteryExemption,
                )
            }
        }

        if (!state.micPermissionGranted) {
            item(key = "mic-permission") {
                WarningCard(
                    text = "Microphone access is denied, so voice input is unavailable.",
                    actionLabel = null,
                    onAction = null,
                )
            }
        }

        item(key = "desktop") {
            SectionLabel("DESKTOP")
            DesktopTelemetryRow(state.desktop)
        }

        if (state.approvals.isNotEmpty()) {
            item(key = "approvals-label") { SectionLabel("PENDING APPROVALS") }
            items(state.approvals, key = { it.id }) { request ->
                ApprovalCard(
                    request = request,
                    onApprove = { actions.onApprove(request.id) },
                    onReject = { actions.onReject(request.id) },
                )
            }
        }

        state.statusText?.let { status ->
            item(key = "status") {
                SectionLabel("STATUS")
                Text(
                    text = status,
                    style = MaterialTheme.typography.bodyMedium,
                    color = JarvisTextMuted,
                )
            }
        }

        item(key = "mic") {
            Spacer(Modifier.height(8.dp))
            MicButton(
                active = state.micActive,
                enabled = state.micPermissionGranted,
                onToggle = actions.onToggleMic,
            )
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun ConnectionHeader(state: ConnectionState, lastError: String?) {
    val (label, tint) = when (state) {
        ConnectionState.CONNECTED -> "CONNECTED" to JarvisGreen
        ConnectionState.RECONNECTING -> "RECONNECTING" to JarvisAmber
        ConnectionState.OFFLINE -> "OFFLINE" to JarvisRed
    }

    Column {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(10.dp)
                    .background(tint, CircleShape),
            )
            Spacer(Modifier.width(10.dp))
            Text(
                text = "JARVIS",
                style = MaterialTheme.typography.titleLarge,
                color = JarvisCyan,
            )
            Spacer(Modifier.width(10.dp))
            Text(
                text = label,
                style = MaterialTheme.typography.labelSmall,
                color = tint,
            )
        }
        if (state != ConnectionState.CONNECTED && !lastError.isNullOrBlank()) {
            Spacer(Modifier.height(4.dp))
            Text(
                text = lastError,
                style = MaterialTheme.typography.labelSmall,
                color = JarvisTextMuted,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun ServerAddressField(
    address: String,
    onCommit: (String) -> Unit,
    onReconnect: () -> Unit,
) {
    var draft by rememberSaveable(address) { mutableStateOf(address) }
    val keyboard = LocalSoftwareKeyboardController.current

    Row(verticalAlignment = Alignment.CenterVertically) {
        OutlinedTextField(
            value = draft,
            onValueChange = { draft = it },
            modifier = Modifier.weight(1f),
            singleLine = true,
            label = { Text("Desktop address", style = MaterialTheme.typography.labelSmall) },
            textStyle = MaterialTheme.typography.bodyMedium.copy(fontFamily = FontFamily.Monospace),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(
                onDone = {
                    keyboard?.hide()
                    onCommit(draft)
                },
            ),
            shape = RoundedCornerShape(10.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = JarvisCyan,
                unfocusedBorderColor = JarvisOutline,
                focusedContainerColor = JarvisSurface,
                unfocusedContainerColor = JarvisSurface,
            ),
        )
        Spacer(Modifier.width(8.dp))
        Button(
            onClick = {
                keyboard?.hide()
                if (draft.trim() != address) onCommit(draft) else onReconnect()
            },
            shape = RoundedCornerShape(10.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = JarvisSurface,
                contentColor = JarvisCyan,
            ),
        ) {
            Text("Link", style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun DesktopTelemetryRow(telemetry: DesktopTelemetryEvent?) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        StatTile("CPU", telemetry?.cpuPercent?.let { "${it.roundToInt()}%" }, Modifier.weight(1f))
        StatTile("GPU", telemetry?.gpuTempC?.let { "${it.roundToInt()}°C" }, Modifier.weight(1f))
        StatTile("VRAM", formatVram(telemetry), Modifier.weight(1f))
    }
}

private fun formatVram(telemetry: DesktopTelemetryEvent?): String? {
    val used = telemetry?.vramUsedMb ?: return null
    val total = telemetry.vramTotalMb
    return if (total != null && total > 0) {
        "${(used / 1024).roundToInt()}/${(total / 1024).roundToInt()}G"
    } else {
        "${used.roundToInt()}M"
    }
}

@Composable
private fun StatTile(label: String, value: String?, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .background(JarvisSurface, RoundedCornerShape(12.dp))
            .border(1.dp, JarvisOutline, RoundedCornerShape(12.dp))
            .padding(horizontal = 12.dp, vertical = 10.dp),
    ) {
        Text(label, style = MaterialTheme.typography.labelSmall, color = JarvisTextMuted)
        Spacer(Modifier.height(4.dp))
        Text(
            text = value ?: "—",
            style = MaterialTheme.typography.titleMedium,
            color = if (value == null) JarvisTextMuted else JarvisCyan,
            maxLines = 1,
        )
    }
}

@Composable
private fun ApprovalCard(
    request: ApprovalRequestEvent,
    onApprove: () -> Unit,
    onReject: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(JarvisSurface, RoundedCornerShape(12.dp))
            .border(1.dp, JarvisAmber.copy(alpha = 0.4f), RoundedCornerShape(12.dp))
            .padding(14.dp),
    ) {
        Text(request.title, style = MaterialTheme.typography.titleMedium, color = JarvisAmber)
        if (request.summary.isNotBlank()) {
            Spacer(Modifier.height(6.dp))
            Text(request.summary, style = MaterialTheme.typography.bodyMedium)
        }
        request.detail?.takeIf { it.isNotBlank() }?.let { detail ->
            Spacer(Modifier.height(6.dp))
            Text(
                text = detail,
                style = MaterialTheme.typography.bodyMedium.copy(fontFamily = FontFamily.Monospace),
                color = JarvisTextMuted,
            )
        }
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = onApprove,
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(10.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = JarvisGreen.copy(alpha = 0.16f),
                    contentColor = JarvisGreen,
                ),
            ) { Text("Approve") }

            Button(
                onClick = onReject,
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(10.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = JarvisRed.copy(alpha = 0.16f),
                    contentColor = JarvisRed,
                ),
            ) { Text("Reject") }
        }
    }
}

@Composable
private fun WarningCard(text: String, actionLabel: String?, onAction: (() -> Unit)?) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(JarvisSurface, RoundedCornerShape(12.dp))
            .border(1.dp, JarvisAmber.copy(alpha = 0.3f), RoundedCornerShape(12.dp))
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.bodyMedium,
            color = JarvisTextMuted,
            modifier = Modifier.weight(1f),
        )
        if (actionLabel != null && onAction != null) {
            Spacer(Modifier.width(8.dp))
            Text(
                text = actionLabel,
                style = MaterialTheme.typography.labelSmall,
                color = JarvisAmber,
                modifier = Modifier
                    .clickable(onClick = onAction)
                    .padding(horizontal = 10.dp, vertical = 6.dp),
            )
        }
    }
}

@Composable
private fun SectionLabel(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.labelSmall,
        color = JarvisTextMuted,
        modifier = Modifier.padding(top = 4.dp, bottom = 2.dp),
    )
}

@Composable
private fun MicButton(active: Boolean, enabled: Boolean, onToggle: () -> Unit) {
    val container: Color = if (active) JarvisCyan else JarvisSurface
    val content: Color = if (active) JarvisBlack else JarvisCyan

    Button(
        onClick = onToggle,
        enabled = enabled,
        modifier = Modifier
            .fillMaxWidth()
            .height(64.dp),
        shape = RoundedCornerShape(16.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = container,
            contentColor = content,
            disabledContainerColor = JarvisSurface,
            disabledContentColor = JarvisTextMuted,
        ),
    ) {
        Text(
            text = if (active) "LISTENING — TAP TO STOP" else "TAP TO TALK",
            style = MaterialTheme.typography.titleMedium,
        )
    }
}
