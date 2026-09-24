package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.Skills
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject

/**
 * Installed skills on Mind, with Remove - the desktop's Brain window,
 * Faculties, Skills ([com.jarvis.client.net.Skills]).
 *
 * Remove asks "are you sure" in place, in the desktop's words, then goes -
 * never held on a stale link, because it only takes something away. If the
 * PC raises an approval card for it, the line under the list says so and
 * where the card is. There is no Install: no app can install a skill.
 *
 * When the answer has not come back, or holds no list, [fallback] draws the
 * section as before (the raw keys, "Reading…", "Not on this backend").
 */
@Composable
internal fun SkillsSection(data: JsonObject?, fallback: @Composable () -> Unit) {
    val skills = remember(data) { data?.let { Skills.read(it) } }
    if (skills == null) {
        fallback()
        return
    }
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var confirm by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    Section("Skills") {
        Plate {
            Text(
                "Installed, with what the safety scanner said about each.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
            Gap(8)
            if (skills.isEmpty()) {
                Text(
                    "No skills installed, or the scanner has quarantined them all.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
            }
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                skills.forEach { s ->
                    Column(Modifier.fillMaxWidth()) {
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Text(s.title, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi,
                                modifier = Modifier.weight(1f))
                            Text(s.verdict, style = MaterialTheme.typography.labelSmall,
                                color = if (s.clean) chrome.okInk else chrome.warnInk)
                        }
                        s.lines.forEach {
                            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        }
                        val name = s.name
                        if (name != null) {
                            if (confirm == name) {
                                Text(Skills.removeWarning(name), style = MaterialTheme.typography.bodySmall,
                                    color = chrome.warnInk)
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Quiet("Yes, remove it", color = chrome.badInk, enabled = !busy, onClick = {
                                        confirm = null
                                        busy = true
                                        scope.launch {
                                            said = JarvisRuntime.removeSkill(name)
                                            busy = false
                                        }
                                    })
                                    Quiet("Keep it", onClick = { confirm = null })
                                }
                            } else {
                                Quiet("Remove", color = chrome.badInk, enabled = !busy,
                                    onClick = { confirm = name })
                            }
                        }
                    }
                }
            }
            said?.let {
                Gap(6)
                Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textHi,
                    modifier = Modifier.liveStatus())
            }
        }
    }
}
