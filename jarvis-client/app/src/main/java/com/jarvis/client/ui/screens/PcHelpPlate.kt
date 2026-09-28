package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.PcHelp
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "PC help" on the Brain screen, under Hardware (docs/JARVIS-API.md section
 * 84): five plain answers about the PC - why it is slow, how full its drives
 * are, what is using the graphics card, how hot it is, and when it last
 * restarted. The desktop shows the same answers in Settings, Hardware and
 * models.
 *
 * READ-ONLY: nothing here changes anything, so there is no card, and "Check
 * now" works on a stale link too - it only reads. The PC is asked only when
 * the owner taps it, never on a timer. The answer is held by this screen
 * alone (not [JarvisRuntime]) and is gone when the screen closes: it can
 * name programs on the PC. Every sentence is the PC's own; the labels are
 * [PcHelp]'s, which are the desktop's.
 */
@Composable
internal fun PcHelpSection() {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var read by remember { mutableStateOf<PcHelp.Read>(PcHelp.Read.NotAsked) }
    val checking = read is PcHelp.Read.Checking

    Section(PcHelp.HEADING) {
        Plate {
            val loaded = read as? PcHelp.Read.Loaded
            if (loaded == null) {
                Text(PcHelp.INTRO, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            } else {
                loaded.answer.sections.forEachIndexed { i, s ->
                    if (i > 0) {
                        Gap(6)
                        Rule()
                        Gap(6)
                    }
                    Kicker(s.title, Modifier.semantics { heading() })
                    Gap(2)
                    Text(s.words, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                }
                for (note in loaded.answer.notes) {
                    Gap(8)
                    Text(note, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                }
            }
            PcHelp.readLine(read)?.let {
                Gap(8)
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (read is PcHelp.Read.Checking) chrome.textMid else chrome.warnInk,
                    modifier = Modifier.liveStatus(),
                )
            }
            Gap(8)
            Secondary(
                text = PcHelp.CHECK,
                enabled = !checking,
                busy = checking,
                modifier = Modifier.fillMaxWidth(),
                onClick = {
                    if (!checking) {
                        read = PcHelp.Read.Checking
                        scope.launch { read = JarvisRuntime.pcHelp() }
                    }
                },
            )
        }
    }
}
