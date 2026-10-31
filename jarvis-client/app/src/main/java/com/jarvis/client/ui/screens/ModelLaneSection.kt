package com.jarvis.client.ui.screens

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ModelLane
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * Settings' "The local model" card: the automatic-restart door, moved here from
 * the top of Home on 2026-10-31.
 *
 * WHY IT MOVED. The owner sent a screenshot of Home carrying, permanently, the
 * PC's own paragraph "Jarvis is not starting the local model by itself:
 * automatic restarting is off." and its "Restart it automatically again"
 * button, under the connection dot - and said the wording at the top of the
 * screen was unnecessary and should be in settings. Home now keeps only its
 * compact link indicator (the dot and "Connected") and this card owns the
 * sentence and the switch. The feature is NOT removed: it is one Settings
 * section, findable by its own search and jump rows ("The local model").
 *
 * WHAT IT DRAWS, in the same words Home used: the section's one explanatory
 * line ([ModelLane.SECTION_ABOUT]), the PC's own sentence when it has one
 * ([ModelLane.notice], drawn verbatim - never composed here), a press refusal
 * in the same place, and the switch itself ([ModelLane.switchWords] -
 * "Don't restart it for me" while automatic restarting is on, "Restart it
 * automatically again" while it is off). The press calls the same
 * [JarvisRuntime.setLaneAuto] the Home switch called, and the switch is drawn
 * from the PC's own answer, never from what the press claimed. No card is
 * raised (a dead process cannot say whether it crashed or was stopped on
 * purpose), which is why this is a switch and not an approval.
 */
@Composable
internal fun ModelLaneSection() {
    val chrome = LocalChrome.current
    val info by JarvisRuntime.modelLane.collectAsState()
    val busy by JarvisRuntime.laneAutoBusy.collectAsState()
    val failure by JarvisRuntime.laneAutoFailure.collectAsState()
    val scope = rememberCoroutineScope()
    Section("The local model") {
        Text(
            ModelLane.SECTION_ABOUT,
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
        val note = failure ?: ModelLane.notice(info)
        if (note.isNotEmpty()) {
            Text(
                note,
                style = MaterialTheme.typography.bodySmall,
                color = if (failure != null) chrome.warnInk else chrome.textMid,
            )
        }
        val words = ModelLane.switchWords(info)
        if (words.isNotEmpty()) {
            Quiet(
                text = words,
                enabled = !busy && failure == null,
                color = chrome.textMid,
                onClick = {
                    // The PC decides; this only asks the same question the
                    // Home switch asked. Nothing is claimed until it answers.
                    ModelLane.switchAsks(info)?.let { on ->
                        scope.launch { JarvisRuntime.setLaneAuto(on) }
                    }
                },
            )
        }
    }
}
