package com.jarvis.client.ui.screens

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome

/**
 * Settings plate that says, plainly, that the Android app can run a model on
 * the phone itself, where that screen lives, and what it needs.
 *
 * The feature is built and ships in this build: `LocalAiScreen` runs a `.gguf`
 * model on the phone with no PC reachable. This plate used to deny that the
 * feature existed while Home -> More -> Local AI answered from the same APK;
 * corrected 2026-11-13 (DEF-065), after the screen was driven on the owner's
 * phone.
 *
 * It has NO controls on purpose. The earlier version of this plate offered a model
 * import, Vulkan/threads/context switches, an auto-sync switch, an offline-memory
 * switch and a battery guard; none of them changed any behaviour, and a switch
 * that promises something and does nothing is worse than no switch at all. This
 * plate only points at the Local AI screen, which owns every control.
 */
@Composable
fun OnDeviceModelPlate() {
    val chrome = LocalChrome.current
    Section("On-device AI model") {
        Plate {
            Text(
                "Available in this build: open Home → More → Local AI.",
                style = MaterialTheme.typography.titleSmall,
                color = chrome.textHi
            )
            Gap(6)
            Text(
                "That screen runs a model file you supply yourself on this phone, and " +
                    "it never sends anything anywhere.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid
            )
            Gap(6)
            Text(
                "It needs a model file you import first - nothing is downloaded for you.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid
            )
        }
    }
}
