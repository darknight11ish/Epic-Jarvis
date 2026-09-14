package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
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
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.minimumInteractiveComponentSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.jarvis.client.platform.ReadinessItem
import com.jarvis.client.ui.T

/**
 * The four §3.1 items, reported rather than assumed — plus the two the audit
 * added.
 *
 * Three of the originals fail silently and look like something else: cleartext
 * looks like a network outage, a denied notification looks like the service not
 * running, and Doze looks like the backend going away. This screen exists so
 * they are visible on the device rather than inferred from a symptom.
 */
@Composable
fun ReadinessScreen(
    items: List<ReadinessItem>,
    onRequestNotifications: () -> Unit,
    onRequestBatteryExemption: () -> Unit,
    onStartService: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier.fillMaxSize().background(T.Void).padding(horizontal = 18.dp)) {
        Spacer(Modifier.height(20.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Platform checks", style = MaterialTheme.typography.titleLarge, color = T.Pick)
                Text(
                    "What the device will and will not allow",
                    style = MaterialTheme.typography.labelSmall,
                    color = T.Dim,
                )
            }
            Text(
                "Back",
                style = MaterialTheme.typography.labelMedium,
                color = T.Pick,
                modifier = Modifier
                    .clickable(role = Role.Button, onClick = onBack)
                    .minimumInteractiveComponentSize()
                    .padding(6.dp),
            )
        }

        Spacer(Modifier.height(16.dp))
        LazyColumn(
            verticalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.weight(1f),
        ) {
            items(items, key = { it.title }) { ReadinessCard(it) }
        }

        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val notifications = items.firstOrNull { it.title == "Notifications" }
            if (notifications?.state == ReadinessItem.State.WARN) {
                Button(
                    onClick = onRequestNotifications,
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(10.dp),
                    colors = ButtonDefaults.buttonColors(T.Plate, T.Warn),
                ) { Text("Allow notifications") }
            }
            val battery = items.firstOrNull { it.title == "Background restart" }
            if (battery?.state == ReadinessItem.State.WARN) {
                Button(
                    onClick = onRequestBatteryExemption,
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(10.dp),
                    colors = ButtonDefaults.buttonColors(T.Plate, T.Warn),
                ) { Text("Keep link alive") }
            }
            Button(
                onClick = onStartService,
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(10.dp),
                colors = ButtonDefaults.buttonColors(T.Plate, T.Pick),
            ) { Text("Start link") }
        }
        Spacer(Modifier.height(18.dp))
    }
}

@Composable
private fun ReadinessCard(item: ReadinessItem) {
    val tint = when (item.state) {
        ReadinessItem.State.OK -> T.Ok
        ReadinessItem.State.WARN -> T.Warn
        ReadinessItem.State.INFO -> T.Dim
    }
    Column(
        Modifier
            .fillMaxWidth()
            .background(T.Plate, RoundedCornerShape(12.dp))
            .padding(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(8.dp).background(tint, CircleShape))
            Spacer(Modifier.width(10.dp))
            Text(item.title, style = MaterialTheme.typography.titleSmall, color = T.Ink)
        }
        Spacer(Modifier.height(6.dp))
        Text(item.detail, style = MaterialTheme.typography.bodySmall, color = T.Dim)
    }
}
