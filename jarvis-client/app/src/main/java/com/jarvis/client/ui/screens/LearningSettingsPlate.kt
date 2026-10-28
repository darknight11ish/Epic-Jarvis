package com.jarvis.client.ui.screens

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.MemoryCounts
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * The section's own note, as one constant so the search index can hold its
 * words (`ui/SettingsSearch.kt`, the "learning" row) to the screen's words.
 */
internal const val LEARNING_NOTE =
    "Jarvis learns facts about you and your projects from your own words only - " +
        "never from web pages, emails, documents or notes. These are the same " +
        "switches as the Brain's Memory tab."

/**
 * "Learning" on the phone's Settings (2026-10-28, the settings audit's G1).
 *
 * WHY THIS EXISTS. `background_learning` and `learn_sensitive_topics` were
 * real switches with a real route, a spoken name and an approval card, and
 * their ONLY control was the Brain's Memory tab - no Settings row on either
 * app, which is the one true "feature switch that is not in the Settings
 * menu" the audit found. This is the phone's half of the fix; the desktop's
 * is `settings.html#learning` + `learning-settings.js`.
 *
 * THE ONE PATH. The background switch is [MemoryCounts]' own
 * (`JarvisRuntime.memoryLearning` / `setLearning`, POST /api/memory/learning),
 * and the two automatic-learning switches below it are [AutoLearnSwitches]
 * reused EXACTLY as the Brain draws them - so this card, the Brain and the
 * typed sentence are one write path, one card, one rule. ON raises one
 * approval card on the PC and reads as "waiting" until it is answered; OFF is
 * immediate and never held. Nothing here approves anything.
 *
 * @param canAct whether the link can carry a write now; ON is held on a stale
 *   link (rule 4) and OFF is not.
 */
@Composable
internal fun LearningSection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var learning by remember { mutableStateOf<Boolean?>(null) }
    var said by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val queue by JarvisRuntime.pending.collectAsState()
    val cardWaiting = MemoryCounts.learningCardWaiting(queue.map { it.action })
    // A card raised anywhere (this phone, the Brain or a desktop) counts.
    LaunchedEffect(cardWaiting) { if (!cardWaiting) reads += 1 }
    LaunchedEffect(reads) { learning = JarvisRuntime.memoryLearning() }

    // Waiting shows the switch in the position it was asked for, so it can be
    // turned OFF - which takes the request back. The line says "waiting".
    val checked = learning == true || cardWaiting
    Section("Learning") {
        Text(
            LEARNING_NOTE,
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textLo,
        )
        Gap(8)
        SwitchRow(
            title = "Background learning",
            detail = MemoryCounts.learningLine(learning),
            checked = checked,
            // ON needs a live link (it raises a card); OFF never waits.
            enabled = !busy && (canAct || checked),
            onChange = { want ->
                if (!busy) {
                    busy = true
                    said = null
                    scope.launch {
                        try {
                            said = JarvisRuntime.setLearning(want)
                        } finally {
                            busy = false
                            reads += 1
                        }
                    }
                }
            },
        )
        if (busy) {
            Text("Asking your PC…", style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        if (cardWaiting) {
            Text(
                MemoryCounts.waitingLine(),
                style = MaterialTheme.typography.bodySmall,
                color = chrome.warnInk,
            )
        }
        Gap(8)
        AutoLearnSwitches(canAct = canAct, learningOn = learning, refresh = reads)
        said?.let {
            Text(
                it,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
                modifier = Modifier.liveStatus(),
            )
        }
    }
}
