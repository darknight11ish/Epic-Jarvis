package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Manner
import com.jarvis.client.net.WriteLikeMe
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "How Jarvis talks" on Mind ([Manner], the owner's decision of 2026-09-25) -
 * the desktop's Settings -> How Jarvis talks, in the same words: on the
 * phone, settings for a PC feature live on Mind.
 *
 * Two choices, each with the PC's own "why" line: "Warm and brief (default)"
 * and "Plain". Wording only - never what Jarvis does, asks or remembers - so
 * neither raises an approval card. ONE tap is ONE change, held on a stale
 * link ([JarvisRuntime.setManner]).
 */
@Composable
internal fun MannerSection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Manner.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    var humorBusy by remember { mutableStateOf(false) }
    // "Write like me" (jarvis_voiceprint.py): the samples and their ON/OFF
    // switch, drawn under this same card by VoiceprintPlate.kt. A READ is
    // never held; the three writes are held on a stale link, here through the
    // runtime ([JarvisRuntime.setVoiceprintEnabled] and friends) and again on
    // the PC. No approval card anywhere: these are local settings.
    var vpReads by remember { mutableIntStateOf(0) }
    var vpView by remember { mutableStateOf<WriteLikeMe.View?>(null) }
    var vpMissing by remember { mutableStateOf(false) }
    var vpReadError by remember { mutableStateOf<String?>(null) }
    var vpBusy by remember { mutableStateOf(false) }
    var vpSaid by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(vpReads) {
        when (val r = JarvisRuntime.voiceprint()) {
            is ApiResult.Ok -> {
                val v = WriteLikeMe.parse(r.value)
                if (v == null) {
                    vpMissing = true
                } else {
                    vpView = v
                    vpMissing = false
                }
                vpReadError = null
            }
            is ApiResult.Failed -> if (WriteLikeMe.missing(r.error)) {
                vpMissing = true
                vpReadError = null
            } else {
                vpReadError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.manner()) {
            is ApiResult.Ok -> {
                val v = Manner.parse(r.value)
                if (v == null) missing = true else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Manner.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    fun choose(id: String) {
        if (busy) return
        busy = true
        said = null
        scope.launch {
            try {
                said = JarvisRuntime.setManner(id)
            } finally {
                busy = false
                reads += 1
            }
        }
    }

    // Humour (the owner's decision, 2026-09-27): a second, independent
    // switch on this same screen - off to start, no card either way.
    fun toggleHumor(on: Boolean) {
        if (humorBusy) return
        humorBusy = true
        said = null
        scope.launch {
            try {
                said = JarvisRuntime.setHumor(on)
            } finally {
                humorBusy = false
                reads += 1
            }
        }
    }

    // ONE tap is ONE change for "Write like me" too; the runtime holds each of
    // the three writes on a stale link and the PC holds them again. The re-read
    // after every write keeps the switch and the list the PC's truth.
    fun voiceprintWrite(action: suspend () -> String) {
        if (vpBusy) return
        vpBusy = true
        vpSaid = null
        scope.launch {
            try {
                vpSaid = action()
            } finally {
                vpBusy = false
                vpReads += 1
            }
        }
    }

    Section(Manner.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            val v = view
            val err = readError
            Text(v?.detail ?: Manner.DETAIL, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            when {
                missing -> Text(Manner.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                v == null -> Text(
                    if (err != null) "Couldn't read it: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    v.choices.forEach { c ->
                        Gap(8)
                        val chosen = c.id == v.manner
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            // "(in use)" as well as the colour: not by colour alone.
                            Text(if (chosen) "${c.label} (in use)" else c.label,
                                style = MaterialTheme.typography.titleSmall,
                                color = if (chosen) chrome.okInk else chrome.textHi,
                                modifier = Modifier.weight(1f))
                            if (!chosen) {
                                Quiet("Use this", enabled = canAct && !busy, onClick = { choose(c.id) })
                            }
                        }
                        Text(c.why, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    Gap(8)
                    Text(v.spoken, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    Gap(12)
                    // One switch with its words: the row takes the taps and TalkBack
                    // reads the title with its on/off state.
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .toggleable(
                                value = v.humor,
                                enabled = canAct && !humorBusy,
                                role = Role.Switch,
                                onValueChange = { toggleHumor(it) },
                            ),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(v.humorTitle, style = MaterialTheme.typography.titleSmall,
                            color = chrome.textHi, modifier = Modifier.weight(1f))
                        Switch(checked = v.humor, enabled = canAct && !humorBusy,
                            onCheckedChange = null)
                    }
                    Text(v.humorDetail, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    Gap(12)
                    // "Write like me" (PR #665's UI): the owner's own samples
                    // and their switch, under the same "How Jarvis talks"
                    // card. An older PC says so in one line instead of drawing
                    // controls that could only fail.
                    val vpErr = vpReadError
                    when {
                        vpMissing -> Text(WriteLikeMe.MISSING,
                            style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                        vpView == null && vpErr != null -> Text(
                            "Couldn't read it: $vpErr",
                            style = MaterialTheme.typography.bodySmall, color = chrome.warnInk,
                        )
                        vpView == null -> Text("Reading…",
                            style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
                        else -> VoiceprintPlate(
                            canAct = canAct,
                            view = vpView,
                            busy = vpBusy,
                            said = vpSaid,
                            onToggle = { on -> voiceprintWrite { JarvisRuntime.setVoiceprintEnabled(on) } },
                            onAdd = { text -> voiceprintWrite { JarvisRuntime.addVoiceprint(text) } },
                            onForget = { sample -> voiceprintWrite { JarvisRuntime.forgetVoiceprint(sample.id) } },
                        )
                    }
                }
            }
            said?.let {
                Gap(6)
                Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus())
            }
        }
    }
}
