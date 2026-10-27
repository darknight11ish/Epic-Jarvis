package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.LinkState
import com.jarvis.client.net.FocusPresets
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * The focus-preset selector (owner decision 2026-10-18). ONE contract
 * (`backend/jarvis_presets.py` -> `backend/fixtures/work_presets.json`) supplies
 * every word about a preset; this file adds only local UI labels.
 *
 * Two surfaces, the same list:
 *  - a chip above the composer, showing the current preset; tapping opens the
 *    list with one "Use this preset" button per preset;
 *  - a Settings -> Hardware "Focus presets" plate, replacing the old work
 *    setups plate in the same section.
 *
 * Nothing auto-applies: each button posts the contract's one apply action,
 * which raises the existing approval card (tier "ask"); the list is re-read
 * afterwards. Every press is disabled while the link is stale (rule 4), and a
 * pending preset shows the PC's "being prepared" words and no button.
 */
@Composable
fun FocusPresetChip(link: LinkState, stale: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val read by JarvisRuntime.focusPresets.collectAsState()
    var open by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf<String?>(null) }
    var notice by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) { JarvisRuntime.refreshFocusPresets() }
    val view = (read as? FocusPresets.Read.Loaded)?.view
    Column(Modifier.fillMaxWidth()) {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Quiet(
                if (view == null) FocusPresets.CHOOSE else FocusPresets.chipLabel(view),
                color = if (view?.current != null) chrome.okInk else chrome.textMid,
                onClick = { open = !open },
            )
            if (open) Quiet("Close", color = chrome.textLo, onClick = { open = false })
            if (read is FocusPresets.Read.Failed) {
                Quiet("Refresh", color = chrome.textMid) { scope.launch { JarvisRuntime.refreshFocusPresets() } }
            }
        }
        if (open) {
            Gap(6)
            FocusPresetList(
                view = view,
                link = link,
                stale = stale,
                busy = busy,
                notice = notice,
                onUse = { id ->
                    if (busy == null) {
                        busy = id
                        notice = null
                        scope.launch {
                            try {
                                notice = JarvisRuntime.useFocusPreset(id)
                                JarvisRuntime.refreshFocusPresets()
                            } finally {
                                busy = null
                            }
                        }
                    }
                },
            )
        }
        notice?.let {
            Text(
                it,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
                modifier = Modifier.liveStatus(),
            )
        }
    }
}

/**
 * "Focus presets" in Settings -> Hardware: the same contract words, with the
 * current preset marked and one asked action each. It replaces the old work
 * setups plate in [HardwarePlate], not a second catalogue.
 */
@Composable
internal fun FocusPresetsSection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val read by JarvisRuntime.focusPresets.collectAsState()
    var busy by remember { mutableStateOf<String?>(null) }
    var notice by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) { JarvisRuntime.refreshFocusPresets() }
    val view = (read as? FocusPresets.Read.Loaded)?.view
    Gap(12)
    Rule()
    Gap(8)
    Kicker(FocusPresets.TITLE, Modifier.semantics { heading() })
    Gap(4)
    Text(
        "Presets choose the local model and card for the work you are about to do. " +
            "Using one raises a single approval card on your PC; nothing changes until you approve it. " +
            "The Fast preset uses the 2080 SUPER.",
        style = MaterialTheme.typography.bodySmall,
        color = chrome.textMid,
    )
    if (view == null) {
        val currentRead = read
        val failure = when (currentRead) {
            is FocusPresets.Read.Failed -> currentRead.words
            FocusPresets.Read.NotAsked -> FocusPresets.ASKING
            else -> FocusPresets.UPDATE
        }
        Gap(8)
        Text(failure, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        Gap(6)
        Quiet("Try again", color = chrome.textMid) { scope.launch { JarvisRuntime.refreshFocusPresets() } }
        return
    }
    FocusPresetList(
        view = view,
        link = LinkState.CONNECTED,
        stale = !canAct,
        busy = busy,
        notice = notice,
        onUse = { id ->
            if (busy == null) {
                busy = id
                notice = null
                scope.launch {
                    try {
                        notice = JarvisRuntime.useFocusPreset(id)
                        JarvisRuntime.refreshFocusPresets()
                    } finally {
                        busy = null
                    }
                }
            }
        },
    )
    notice?.let {
        Gap(6)
        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk, modifier = Modifier.liveStatus())
    }
    // The PC's cloud setting, said once and read-only: the phone has no switch
    // for it (turning escalation on is a loosening that needs the PC's card).
    view.cloud?.let { cloud ->
        Gap(6)
        Text(
            FocusPresets.cloudLine(cloud),
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textMid,
        )
    }
}

@Composable
private fun FocusPresetList(
    view: FocusPresets.View?,
    link: LinkState,
    stale: Boolean,
    busy: String?,
    notice: String?,
    onUse: (String) -> Unit,
) {
    val chrome = LocalChrome.current
    if (view == null) {
        Text(FocusPresets.UPDATE, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        return
    }
    Gap(6)
    for (p in view.presets) {
        Gap(8)
        Rule()
        Gap(6)
        val title = buildString {
            append(p.title)
            if (view.chosen == p.id) append(" - ").append(FocusPresets.CHOSEN)
        }
        Text(title, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
        if (p.focus.isNotBlank()) {
            Text(p.focus, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        Text(p.what, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        Gap(2)
        Text(FocusPresets.modelLine(p), style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        FocusPresets.helperLine(p)?.let {
            Text(FocusPresets.HELPER + " " + it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
        if (p.what.isNotBlank()) {
            Text(FocusPresets.WHY, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        Text(p.cost, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        Text(FocusPresets.WORSE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        Text(p.worse, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        val blocker = FocusPresets.blocker(view, p, stale = stale, linkUp = link == LinkState.CONNECTED)
        Gap(6)
        if (blocker != null) {
            Text(blocker, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        } else {
            Secondary(
                text = if (busy == p.id) "Asking…" else FocusPresets.USE_THIS,
                enabled = busy == null,
                modifier = Modifier.fillMaxWidth(),
                onClick = { onUse(p.id) },
            )
        }
    }
    notice?.let { /* drawn by the caller, under the list */ }
    Gap(4)
    Text(
        "These are combinations of models already on your PC; there is no catalogue here and no search.",
        style = MaterialTheme.typography.labelSmall,
        color = chrome.textLo,
    )
}
