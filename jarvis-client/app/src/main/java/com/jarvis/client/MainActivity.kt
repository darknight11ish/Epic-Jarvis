package com.jarvis.client

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.client.platform.PlatformReadiness
import com.jarvis.client.platform.ReadinessItem
import com.jarvis.client.service.EventService

private val Void = Color(0xFF05070B)
private val Plate = Color(0xFF0A1119)
private val Line = Color(0xFF17293A)
private val Ink = Color(0xFFDBE7F2)
private val Dim = Color(0xFF8FA3B8)
private val Pick = Color(0xFF6FE3FF)
private val Ok = Color(0xFF5FE0A8)
private val Warn = Color(0xFFFFB648)

/**
 * Step 0 only. Nothing here talks to the network - the whole point of §3.1 is
 * that three of its four items fail silently and look like a network problem,
 * so they are made visible before any request is ever sent.
 */
class MainActivity : ComponentActivity() {

    private val permissionTick = mutableIntStateOf(0)

    private val notificationPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { permissionTick.intValue += 1 }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            val tick = permissionTick.intValue
            // rememberSaveable: a rotation, or process death behind the permission
            // dialog, wiped the typed host and snapped the readiness list back to
            // "No host set yet" — on the one screen whose job is capturing it.
            var host by rememberSaveable { mutableStateOf("") }
            val items = remember(tick, host) { PlatformReadiness.report(this, host) }

            Column(
                Modifier
                    .fillMaxSize()
                    .background(Void)
                    .windowInsetsPadding(WindowInsets.systemBars)
                    .padding(horizontal = 18.dp),
            ) {
                Spacer(Modifier.height(22.dp))
                Text(
                    "JARVIS",
                    style = MaterialTheme.typography.titleLarge,
                    color = Pick,
                )
                Text(
                    "Step 0 — platform configuration",
                    style = MaterialTheme.typography.labelSmall,
                    color = Dim,
                )

                Spacer(Modifier.height(16.dp))

                OutlinedTextField(
                    value = host,
                    onValueChange = { host = it },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    label = { Text("Desktop host", color = Dim) },
                    placeholder = { Text("your-desktop.tailnet.ts.net", color = Dim) },
                    textStyle = MaterialTheme.typography.bodyMedium
                        .copy(fontFamily = FontFamily.Monospace, color = Ink),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                    shape = RoundedCornerShape(10.dp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = Pick,
                        unfocusedBorderColor = Line,
                        focusedContainerColor = Plate,
                        unfocusedContainerColor = Plate,
                    ),
                )

                Spacer(Modifier.height(14.dp))

                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                    modifier = Modifier.weight(1f),
                ) {
                    items(items, key = { it.title }) { ReadinessCard(it) }
                }

                Spacer(Modifier.height(12.dp))

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    // Derived from the already-remembered list rather than re-read
                    // from PackageManager in composition: a bare system read has no
                    // snapshot subscription and only refreshed here because `tick`
                    // happened to be read in the same restart scope.
                    val notificationsItem = items.firstOrNull { it.title == "Notifications" }
                    if (notificationsItem?.state == ReadinessItem.State.WARN) {
                        Button(
                            onClick = {
                                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                                    notificationPermission.launch(
                                        Manifest.permission.POST_NOTIFICATIONS,
                                    )
                                }
                            },
                            modifier = Modifier.weight(1f),
                            shape = RoundedCornerShape(10.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = Plate,
                                contentColor = Warn,
                            ),
                        ) { Text("Allow notifications") }
                    }

                    val batteryItem = items.firstOrNull { it.title == "Background restart" }
                    if (batteryItem?.state == ReadinessItem.State.WARN) {
                        Button(
                            onClick = { requestBatteryExemption() },
                            modifier = Modifier.weight(1f),
                            shape = RoundedCornerShape(10.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = Plate,
                                contentColor = Warn,
                            ),
                        ) { Text("Keep link alive") }
                    }

                    Button(
                        onClick = { EventService.start(this@MainActivity) },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(10.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Plate,
                            contentColor = Pick,
                        ),
                    ) { Text("Start link service") }
                }

                Spacer(Modifier.height(18.dp))
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // Notification permission and the battery exemption can both be changed in
        // Settings while we are away.
        permissionTick.intValue += 1
    }

    /**
     * Opens the platform's own exemption dialog. Never granted silently, and the
     * screen keeps reporting the real state either way.
     */
    private fun requestBatteryExemption() {
        val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            .setData(Uri.parse("package:$packageName"))
        runCatching { startActivity(intent) }.onFailure {
            // Some builds hide the per-app dialog; fall back to the list.
            runCatching { startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)) }
        }
    }
}

@Composable
private fun ReadinessCard(item: ReadinessItem) {
    val tint = when (item.state) {
        ReadinessItem.State.OK -> Ok
        ReadinessItem.State.WARN -> Warn
        ReadinessItem.State.INFO -> Dim
    }
    Column(
        Modifier
            .fillMaxWidth()
            .background(Plate, RoundedCornerShape(12.dp))
            .padding(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Spacer(
                Modifier
                    .size(8.dp)
                    .background(tint, CircleShape),
            )
            Spacer(Modifier.width(10.dp))
            Text(
                item.title,
                style = MaterialTheme.typography.titleMedium.copy(fontSize = 14.sp),
                color = Ink,
            )
        }
        Spacer(Modifier.height(6.dp))
        Text(
            item.detail,
            style = MaterialTheme.typography.bodyMedium.copy(fontSize = 13.sp),
            color = Dim,
        )
    }
}
