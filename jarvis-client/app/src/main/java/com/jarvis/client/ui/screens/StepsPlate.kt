package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.Steps
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome

/** How many of the kept lines are drawn - the newest. The rest stay in memory for Clear to drop. */
private const val SHOWN = 20

/**
 * "What Jarvis is doing" on Mind - the tool loop's `step` events, newest
 * last, the way the desktop's Brain → Live shows them
 * ([com.jarvis.client.net.Steps]). Tool names only. Clear forgets this
 * phone's copy and sends nothing.
 */
@Composable
internal fun StepsSection() {
    val chrome = LocalChrome.current
    val steps by JarvisRuntime.steps.collectAsState()
    Section(
        "What Jarvis is doing",
        trailing = {
            if (steps.isNotEmpty()) Quiet("Clear", onClick = { JarvisRuntime.clearSteps() })
        },
    ) {
        Plate {
            if (steps.isEmpty()) {
                Text(
                    "Nothing yet. Steps appear here while Jarvis answers with its tools.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
            }
            steps.takeLast(SHOWN).forEach { line ->
                Row(Modifier.fillMaxWidth()) {
                    Text(line.time, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    Spacer(Modifier.width(10.dp))
                    Text(line.text, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                }
            }
            Gap(6)
            Text(Steps.NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
    }
}
