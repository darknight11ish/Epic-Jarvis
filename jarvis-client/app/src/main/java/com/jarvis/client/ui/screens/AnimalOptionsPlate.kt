package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
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
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.LinkState
import com.jarvis.client.data.FaceTuning
import com.jarvis.client.face.FrameRateTarget
import com.jarvis.client.face.QualityTier
import com.jarvis.client.net.AnimalOptions
import com.jarvis.client.net.ApiResult
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/**
 * Appearance -> "Animal options" (the owner's decisions of 2026-09-28;
 * [AnimalOptions]) - the desktop's Settings -> "Animal options", in the same
 * words (the PC's own). Every animal option in one place:
 *
 *  - "Shared with your desktop": "Keep the animal still" and the behaviour
 *    switches, kept on the PC - a change here, on the desktop or by asking
 *    Jarvis changes both. No card either way; turning one ON waits for a live
 *    link (rule 4), turning one OFF never does. The rows are whatever the PC
 *    lists, so a new behaviour needs no change here. On a PC too old to share
 *    them, only "Keep the animal still" is offered, on this phone only.
 *  - The sun, moon and weather ([SkySection], unchanged; Open-Meteo still
 *    raises its ONE approval card).
 *  - "Sharpness and frame rate on this phone": this phone's own
 *    ([FaceTuning]); the Face editor above has the rest (Auto adjust's
 *    detail, speed, Battery saver).
 *  - A way to the animal's voice, and where calm motion comes from.
 */
@Composable
internal fun AnimalOptionsSection(
    faceTuning: FaceTuning,
    onFaceTuningChange: (FaceTuning) -> Unit,
    phoneBatterySaver: Boolean,
    /** This phone's old Still ([com.jarvis.client.data.Look.stillAnimal]), offered only for an older PC. */
    legacyStill: Boolean,
    onLegacyStill: (Boolean) -> Unit,
    /** Null: not paired, so there are no voices to go to. */
    onOpenVoices: (() -> Unit)?,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val link by JarvisRuntime.link.collectAsState()
    val stale by JarvisRuntime.stale.collectAsState()
    val canAct = link == LinkState.CONNECTED && !stale
    // The PC's values as this phone keeps them: a change made on the desktop
    // or by asking Jarvis arrives with the appearance event and shows here
    // at once, without a new read.
    val sharedFlow = remember<StateFlow<AnimalOptions.Shared?>> {
        if (JarvisRuntime.isInitialized) JarvisRuntime.appearance.animal else MutableStateFlow<AnimalOptions.Shared?>(null)
    }
    val kept by sharedFlow.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<AnimalOptions.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads) {
        if (!JarvisRuntime.isInitialized) {
            missing = true
            return@LaunchedEffect
        }
        when (val r = JarvisRuntime.animalOptions()) {
            is ApiResult.Ok -> {
                val v = AnimalOptions.parse(r.value)
                if (v == null) missing = true else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (AnimalOptions.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    fun send(id: String, on: Boolean) {
        if (busy) return
        busy = true
        said = null
        scope.launch {
            try {
                said = JarvisRuntime.setAnimalOption(id, on)
            } finally {
                busy = false
                reads += 1
            }
        }
    }

    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(20.dp)) {
        val v = view
        Section(v?.title ?: AnimalOptions.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
            Plate {
                Text(v?.intro ?: AnimalOptions.INTRO, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                Gap(12)
                Text(AnimalOptions.DESKTOP_SHARED, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
                val err = readError
                when {
                    missing -> {
                        Text(AnimalOptions.MISSING, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                        Gap(6)
                        // An older PC: Still stays usable on this phone, as before.
                        val still = AnimalOptions.SWITCHES.first { it.id == "still" }
                        SwitchRow(
                            title = still.label,
                            detail = "${still.detail} ${AnimalOptions.LOCAL_ONLY}",
                            checked = legacyStill,
                            onChange = onLegacyStill,
                        )
                    }
                    v == null -> Text(
                        if (err != null) "Couldn't read them: $err" else "Reading…",
                        style = MaterialTheme.typography.bodySmall,
                        color = if (err != null) chrome.warnInk else chrome.textLo,
                    )
                    else -> {
                        Text(v.sharedNote, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        v.switches.forEach { sw ->
                            Gap(4)
                            val on = kept?.on(sw.id) ?: v.shared.on(sw.id)
                            SwitchRow(
                                title = sw.label,
                                detail = listOf(sw.detail, if (sw.built) "" else v.coming)
                                    .filter { it.isNotBlank() }.joinToString(" "),
                                checked = on,
                                onChange = { send(sw.id, it) },
                                // Turning one on waits for a live link; off never does.
                                enabled = !busy && (on || canAct),
                            )
                        }
                        Gap(6)
                        Text(v.seriousNote, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    }
                }
                said?.let {
                    Gap(6)
                    Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid, modifier = Modifier.liveStatus())
                }
            }
        }

        // The sun, moon and weather: kept on the PC and shared, as before.
        SkySection()

        // This phone only.
        val saver = faceTuning.batterySaver || phoneBatterySaver
        val auto = faceTuning.autoAdjust
        Section(AnimalOptions.DEVICE_TITLE) {
            Plate {
                Text(AnimalOptions.DEVICE_NOTE, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                Gap(10)
                Setting(
                    title = "Sharpness",
                    caption = when {
                        saver -> "Battery saver is on, so the face is drawn at its lightest."
                        auto -> "Auto adjust is choosing. Picking one turns Auto adjust off."
                        else -> null
                    },
                ) {
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        QualityTier.entries.chunked(2).forEach { row ->
                            Choices(
                                options = row,
                                isSelected = { !saver && !auto && it == faceTuning.quality },
                                label = { it.label },
                                onPick = { onFaceTuningChange(faceTuning.copy(quality = it, autoAdjust = false)) },
                                enabled = !saver,
                            )
                        }
                    }
                }
                Gap(10)
                Setting(title = "Frame rate", caption = FrameRateTarget.NOTE) {
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        FrameRateTarget.entries.chunked(3).forEach { row ->
                            Choices(
                                options = row,
                                isSelected = {
                                    !saver && (if (auto) it == FrameRateTarget.AUTO else it == faceTuning.frameRate)
                                },
                                label = { it.label },
                                onPick = { onFaceTuningChange(faceTuning.copy(frameRate = it, autoAdjust = false)) },
                                enabled = !saver,
                            )
                        }
                    }
                }
                Gap(6)
                Text(
                    "Auto adjust, speed and Battery saver are in the Face editor above. You can also ask " +
                        "Jarvis: \"make the animal sharper\" or \"make the animal smoother\" changes the " +
                        "device you ask from.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }

        Section(AnimalOptions.VOICE_TITLE) {
            Plate {
                Text(AnimalOptions.VOICE_NOTE, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                val open = onOpenVoices
                if (open != null) {
                    Gap(4)
                    Quiet("Go to the face's voice", onClick = open)
                }
                Gap(8)
                Text(AnimalOptions.CALM_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            }
        }
    }
}
