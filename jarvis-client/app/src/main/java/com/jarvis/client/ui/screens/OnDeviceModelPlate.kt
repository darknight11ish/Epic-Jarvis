package com.jarvis.client.ui.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.ai.MobileLlamaEngine
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.MobileLaneClient
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.Toggle
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * Settings plate for managing on-device AI models and offline sync on the Android companion phone.
 *
 * Allows loading compact GGUF models, adjusting GPU/CPU execution parameters,
 * and configuring two-way synchronization with the desktop PC.
 */
@Composable
fun OnDeviceModelPlate() {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val engineStatus by MobileLlamaEngine.status.collectAsState()
    val linkState by JarvisRuntime.link.collectAsState()

    var statusMessage by remember { mutableStateOf<String?>(null) }
    val modelStore = if (JarvisRuntime.isInitialized) JarvisRuntime.modelStore else null
    val offlineStore = if (JarvisRuntime.isInitialized) JarvisRuntime.offlineStore else null

    var activeModel by remember {
        mutableStateOf(modelStore?.activeModel())
    }

    val useVulkan = modelStore?.useVulkan?.collectAsState()?.value ?: true
    val threads = modelStore?.threads?.collectAsState()?.value ?: 4
    val contextSize = modelStore?.contextSize?.collectAsState()?.value ?: 2048
    val autoSync = modelStore?.autoSyncOnReconnect?.collectAsState()?.value ?: true
    val captureMemories = modelStore?.captureOfflineMemories?.collectAsState()?.value ?: true
    val batteryGuard = modelStore?.batteryGuard?.collectAsState()?.value ?: true

    val pendingTurns = remember(activeModel, engineStatus) {
        offlineStore?.pendingTurns()?.size ?: 0
    }
    val pendingMemories = remember(activeModel, engineStatus) {
        offlineStore?.pendingMemories()?.size ?: 0
    }

    val launcher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri != null && modelStore != null) {
            scope.launch {
                statusMessage = "Importing model..."
                val name = uri.lastPathSegment?.substringAfterLast('/') ?: "imported-model.gguf"
                val imported = modelStore.importFromUri(uri, name)
                if (imported != null) {
                    activeModel = imported
                    modelStore.applyCurrentConfig()
                    statusMessage = "Loaded '${imported.name}' successfully."
                    JarvisRuntime.registerMobileLaneIfConfigured()
                } else {
                    statusMessage = "Could not load file. Make sure it is a valid GGUF model."
                }
            }
        }
    }

    Section("On-device AI model") {
        Plate {
            Text(
                "Run a compact language model directly on your phone when away from your PC. Conversations and new memories are saved locally and automatically synced when you reconnect.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid
            )

            Gap(10)

            // Active model section
            if (activeModel != null) {
                Text(
                    "Active model: ${activeModel?.name}",
                    style = MaterialTheme.typography.titleSmall,
                    color = chrome.textHi
                )
                val sizeMb = (activeModel?.sizeBytes ?: 0L) / (1024 * 1024)
                Text(
                    "Size: ${sizeMb} MB • Quantization: ${activeModel?.quantization} • Status: ${engineStatus.name}",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid
                )
            } else {
                Text(
                    "No local model active. Tap below to select a .gguf file.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid
                )
            }

            Gap(10)

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Quiet(
                    text = "Load model (.gguf)",
                    onClick = { launcher.launch(arrayOf("*/*")) }
                )
                if (activeModel != null) {
                    Quiet(
                        text = "Unload",
                        onClick = {
                            MobileLlamaEngine.unload()
                            modelStore?.setActiveModel(null)
                            activeModel = null
                            statusMessage = "Model unloaded."
                        }
                    )
                }
                Quiet(
                    text = "Check PC for models",
                    enabled = linkState == com.jarvis.client.LinkState.CONNECTED,
                    onClick = {
                        scope.launch {
                            statusMessage = "Checking desktop for transfer models..."
                            when (val res = MobileLaneClient.fetchTransferModels(JarvisRuntime.api)) {
                                is ApiResult.Ok -> {
                                    val count = res.value.size
                                    statusMessage = "Desktop offers $count compatible models."
                                }
                                is ApiResult.Failed -> {
                                    statusMessage = "Could not query desktop models."
                                }
                            }
                        }
                    }
                )
            }

            Gap(14)
            Rule()
            Gap(10)

            // Hardware & Engine Settings
            Text(
                "Hardware & Inference Settings",
                style = MaterialTheme.typography.titleSmall,
                color = chrome.textHi
            )
            Gap(6)

            // Vulkan GPU toggle
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f).padding(end = 8.dp)) {
                    Text("Vulkan GPU acceleration", style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                    Text("Offloads layers to phone GPU (Pixel Mali-G715 / Adreno). Falls back to CPU when disabled.", style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                }
                Toggle(
                    checked = useVulkan,
                    onCheckedChange = { modelStore?.setUseVulkan(it) }
                )
            }

            Gap(10)

            // CPU Thread Count
            Text("CPU threads (NEON cores)", style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
            Text("Balance inference speed against thermal output and battery drain.", style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            Gap(4)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(2 to "2 (Battery)", 4 to "4 (Balanced)", 6 to "6 (Speed)").forEach { (cnt, label) ->
                    Quiet(
                        text = label,
                        enabled = threads != cnt,
                        onClick = { modelStore?.setThreads(cnt) }
                    )
                }
            }

            Gap(10)

            // Context Size
            Text("Context window size", style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
            Text("Maximum token context preserved in memory for conversation turns.", style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            Gap(4)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(1024 to "1024", 2048 to "2048 (Default)", 4096 to "4096").forEach { (sz, label) ->
                    Quiet(
                        text = label,
                        enabled = contextSize != sz,
                        onClick = { modelStore?.setContextSize(sz) }
                    )
                }
            }

            Gap(14)
            Rule()
            Gap(10)

            // Sync & Offline Behavior Settings
            Text(
                "Two-Way Sync & Memory",
                style = MaterialTheme.typography.titleSmall,
                color = chrome.textHi
            )
            Gap(6)

            // Auto-sync on reconnect toggle
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f).padding(end = 8.dp)) {
                    Text("Auto-sync on reconnect", style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                    Text("Automatically uploads pending offline turns and memories when reconnected.", style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                }
                Toggle(
                    checked = autoSync,
                    onCheckedChange = { modelStore?.setAutoSyncOnReconnect(it) }
                )
            }

            Gap(10)

            // Capture offline memories toggle
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f).padding(end = 8.dp)) {
                    Text("Capture offline memories", style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                    Text("Queues facts and details stated while offline to ingest into desktop brain.", style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                }
                Toggle(
                    checked = captureMemories,
                    onCheckedChange = { modelStore?.setCaptureOfflineMemories(it) }
                )
            }

            Gap(10)

            // Battery saver guard toggle
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f).padding(end = 8.dp)) {
                    Text("Battery saver guard", style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                    Text("Suspends heavy on-device model execution when battery is below 15%.", style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                }
                Toggle(
                    checked = batteryGuard,
                    onCheckedChange = { modelStore?.setBatteryGuard(it) }
                )
            }

            Gap(14)
            Rule()
            Gap(10)

            // Offline queue status and manual sync
            Text(
                "Offline Queue: $pendingTurns turns, $pendingMemories memories waiting to sync",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid
            )

            Gap(6)

            Quiet(
                text = "Sync now",
                enabled = linkState == com.jarvis.client.LinkState.CONNECTED,
                onClick = {
                    scope.launch {
                        JarvisRuntime.triggerOfflineSync()
                        statusMessage = "Sync triggered."
                    }
                }
            )

            statusMessage?.let { msg ->
                Gap(8)
                Text(
                    msg,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textHi
                )
            }
        }
    }
}
