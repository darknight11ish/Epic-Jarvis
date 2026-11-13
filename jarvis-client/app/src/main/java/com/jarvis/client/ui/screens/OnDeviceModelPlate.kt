package com.jarvis.client.ui.screens

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome

/**
 * Settings plate that says, plainly, that the Android app has no on-device AI.
 *
 * The feature was designed (`docs/MOBILE HARNESS WORK/ON-DEVICE-AI-OFFLINE-SYNC-DESIGN.md`)
 * but not built: no model runtime ships in the APK, so the phone cannot answer while
 * the PC is unreachable, and nothing is captured or synced offline yet.
 *
 * It has NO controls on purpose. The earlier version of this plate offered a model
 * import, Vulkan/threads/context switches, an auto-sync switch, an offline-memory
 * switch and a battery guard; none of them changed any behaviour, and the model
 * import ended at a native library that is not in this project. A switch that
 * promises something and does nothing is worse than no switch at all.
 */
@Composable
fun OnDeviceModelPlate() {
    val chrome = LocalChrome.current
    Section("On-device AI model") {
        Plate {
            Text(
                "Not available in this build.",
                style = MaterialTheme.typography.titleSmall,
                color = chrome.textHi
            )
            Gap(6)
            Text(
                "The app cannot answer questions while your PC is unreachable: no model " +
                    "runtime ships inside it, and nothing is captured or synced offline " +
                    "yet. When the PC cannot be reached, chat says so instead of answering.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid
            )
            Gap(6)
            Text(
                "Running a small local model is designed, not built - the design names " +
                    "the native work as a later step.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid
            )
        }
    }
}
