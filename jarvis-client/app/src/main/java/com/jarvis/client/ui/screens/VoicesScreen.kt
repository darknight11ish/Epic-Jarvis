package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.client.net.CustomVoices
import com.jarvis.client.ui.parts.Dot
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Notice
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.Toggle
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.voice.VoiceTraining
import kotlinx.coroutines.launch
import java.util.concurrent.atomic.AtomicBoolean

/**
 * "Jarvis's voice": which voice Jarvis speaks in, the owner's custom voices,
 * adding one, and "the better voice" (docs/JARVIS-API.md section 15).
 *
 * The same permission shape as everything else: adding a voice, switching
 * to a custom one and turning the better voice ON each raise ONE approval
 * card on the PC and change nothing until it is approved - held on a stale
 * link. Going back to the built-in voice, deleting a voice (after asking
 * here) and turning the better voice OFF happen at once, and always go.
 *
 * Adding a voice: either someone reads a sentence this screen SHOWS - and
 * the words sent are that sentence, because this phone never turns speech
 * into text - or the owner picks an audio file and types exactly what is
 * said in it. The recording is held in this screen's memory until it is
 * sent, then dropped; the PC keeps it only once the card is approved.
 *
 * What is shown is what the PC last said ([CustomVoices.Status]), never
 * what was just tapped; the PC rings the `voices` event when a card ends,
 * and the runtime reads the list again.
 */
@Composable
fun VoicesScreen(
    read: CustomVoices.Read,
    note: String?,
    linkBlocker: String?,
    picked: CustomVoices.Picked?,
    record: suspend (stop: () -> Boolean, onLevel: (Float) -> Unit) -> VoiceTraining.Take,
    add: suspend (name: String, clip: ByteArray, transcript: String) -> CustomVoices.Answer?,
    switchTo: suspend (id: String) -> CustomVoices.Answer?,
    delete: suspend (id: String) -> CustomVoices.Answer?,
    setBetter: suspend (on: Boolean) -> CustomVoices.Answer?,
    onPickFile: () -> Unit,
    onClearPicked: () -> Unit,
    onRefresh: suspend () -> Unit,
    onDismissNote: () -> Unit,
    onAskMicrophone: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf<String?>(null) }

    // Adding a voice. The recording lives here only.
    var adding by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }
    var fromFile by remember { mutableStateOf(false) }
    var sentenceIndex by remember { mutableIntStateOf(0) }
    var clip by remember { mutableStateOf<VoiceTraining.Clip?>(null) }
    var typed by remember { mutableStateOf("") }
    var recording by remember { mutableStateOf(false) }
    val stopFlag = remember { AtomicBoolean(false) }
    var level by remember { mutableFloatStateOf(0f) }
    var problem by remember { mutableStateOf<String?>(null) }
    var needsMic by remember { mutableStateOf(false) }

    DisposableEffect(Unit) {
        onDispose {
            stopFlag.set(true)
            clip = null
            onClearPicked()
        }
    }

    fun act(block: suspend () -> Unit) {
        if (busy) return
        busy = true
        onDismissNote()
        scope.launch {
            try {
                block()
            } finally {
                busy = false
            }
        }
    }

    fun resetAdd() {
        adding = false
        name = ""
        clip = null
        typed = ""
        fromFile = false
        problem = null
        onClearPicked()
    }

    Column(modifier.fillMaxSize().background(chrome.surface0).navigationBarsPadding()) {
        TopBar("Jarvis's voice", onBack = {
            stopFlag.set(true)
            onBack()
        }, subtitle = "Which voice Jarvis speaks in")

        Column(
            Modifier
                .weight(1f)
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            note?.let { Notice(it, onDismiss = onDismissNote) }

            when (read) {
                CustomVoices.Read.Loading -> Text(
                    "Asking your PC...",
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textMid,
                )
                is CustomVoices.Read.Missing -> Plate {
                    Text(read.why, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                }
                is CustomVoices.Read.Failed -> Plate {
                    Text(read.why, style = MaterialTheme.typography.bodyMedium, color = chrome.warnInk)
                    Gap(8)
                    Secondary("Ask again", modifier = Modifier.fillMaxWidth(), onClick = {
                        scope.launch { onRefresh() }
                    })
                }
                is CustomVoices.Read.Loaded -> {
                    val s = read.status

                    Plate {
                        Text(CustomVoices.nowLine(s), style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                        CustomVoices.fallbackLine(s)?.let {
                            Gap(6)
                            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                        }
                        CustomVoices.pendingLine(s)?.let {
                            Gap(6)
                            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                        }
                        CustomVoices.lastLine(s)?.let {
                            Gap(6)
                            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                        }
                    }

                    Plate {
                        Text("Voices", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
                        s.voices.forEach { v ->
                            Gap(8)
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Dot(if (v.id == s.active) chrome.okInk else if (v.ready) chrome.textLo else chrome.warnInk)
                                Spacer(Modifier.width(10.dp))
                                Column(Modifier.weight(1f)) {
                                    Text(v.name, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                                    Text(
                                        when {
                                            v.id == s.active -> "In use"
                                            !v.ready -> CustomVoices.sentence(v.why.ifBlank { "Not ready." })
                                            v.builtin -> "Always there"
                                            else -> CustomVoices.length(v.seconds) + " recording"
                                        },
                                        style = MaterialTheme.typography.labelSmall,
                                        color = if (v.ready) chrome.textMid else chrome.warnInk,
                                    )
                                }
                                if (v.id != s.active && v.ready) {
                                    Quiet(
                                        if (v.builtin) "Use" else "Use (asks)",
                                        enabled = !busy,
                                        onClick = { act { switchTo(v.id) } },
                                    )
                                }
                                if (!v.builtin) {
                                    Quiet("Delete", enabled = !busy, onClick = { confirmDelete = v.id })
                                }
                            }
                            if (confirmDelete == v.id) {
                                Gap(6)
                                Text(
                                    CustomVoices.deleteQuestion(v, s),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = chrome.textHi,
                                )
                                Row {
                                    Quiet("Keep it", onClick = { confirmDelete = null })
                                    Spacer(Modifier.weight(1f))
                                    Quiet("Delete", color = chrome.warnInk, enabled = !busy, onClick = {
                                        confirmDelete = null
                                        act { delete(v.id) }
                                    })
                                }
                            }
                        }
                        Gap(8)
                        Text(
                            "Switching to one of your voices asks first, on an approval card. Going " +
                                "back to the built-in voice, and deleting, happen at once.",
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textMid,
                        )
                    }

                    if (!adding) {
                        Primary(
                            text = "Add a voice",
                            enabled = !busy && s.pending == null && s.custom.size < s.limits.maxVoices,
                            modifier = Modifier.fillMaxWidth(),
                            onClick = {
                                resetAdd()
                                adding = true
                                sentenceIndex = 0
                            },
                        )
                    } else {
                        AddVoicePlate(
                            s = s,
                            name = name,
                            onName = { name = it.take(s.limits.maxNameChars) },
                            fromFile = fromFile,
                            onFromFile = {
                                fromFile = it
                                clip = null
                                problem = null
                                onClearPicked()
                            },
                            sentence = s.sentences.getOrNull(sentenceIndex).orEmpty(),
                            onAnotherSentence = {
                                if (s.sentences.isNotEmpty()) sentenceIndex = (sentenceIndex + 1) % s.sentences.size
                                clip = null
                            },
                            clip = clip,
                            recording = recording,
                            level = level,
                            problem = problem,
                            needsMic = needsMic,
                            onRecord = {
                                if (!recording) {
                                    problem = null
                                    needsMic = false
                                    stopFlag.set(false)
                                    recording = true
                                    scope.launch {
                                        val take = try {
                                            record({ stopFlag.get() }, { level = it })
                                        } finally {
                                            recording = false
                                            level = 0f
                                        }
                                        when (take) {
                                            is VoiceTraining.Take.Captured -> {
                                                val bad = CustomVoices.recordingProblem(take.seconds, s.limits)
                                                if (bad == null) clip = VoiceTraining.Clip(take.wav, take.seconds) else problem = bad
                                            }
                                            is VoiceTraining.Take.Failed -> {
                                                problem = take.message
                                                needsMic = take.needsPermission
                                            }
                                        }
                                    }
                                }
                            },
                            onStop = { stopFlag.set(true) },
                            onAskMicrophone = onAskMicrophone,
                            picked = picked,
                            onPickFile = onPickFile,
                            typed = typed,
                            onTyped = { typed = it.take(s.limits.maxTranscriptChars + 20) },
                            busy = busy,
                            linkBlocker = linkBlocker,
                            onSend = { bytes, words ->
                                act {
                                    val answer = add(name, bytes, words)
                                    // Sent: this phone keeps no copy. Kept only when the
                                    // PC refused it for something the owner can fix here.
                                    if (answer?.accepted == true) resetAdd()
                                }
                            },
                            onCancel = { resetAdd() },
                        )
                    }

                    BetterVoicePlate(s, busy, linkBlocker, onSet = { on -> act { setBetter(on) } })

                    Plate {
                        Text("How Jarvis speaks", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
                        Gap(6)
                        CustomVoices.engineLines(s).forEach { line ->
                            Text(line, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                            Gap(4)
                        }
                        val times = CustomVoices.timingLines(s)
                        if (times.isNotEmpty()) {
                            Gap(6)
                            Text("Recently", style = MaterialTheme.typography.labelMedium, color = chrome.textMid)
                            times.forEach {
                                Gap(4)
                                Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun AddVoicePlate(
    s: CustomVoices.Status,
    name: String,
    onName: (String) -> Unit,
    fromFile: Boolean,
    onFromFile: (Boolean) -> Unit,
    sentence: String,
    onAnotherSentence: () -> Unit,
    clip: VoiceTraining.Clip?,
    recording: Boolean,
    level: Float,
    problem: String?,
    needsMic: Boolean,
    onRecord: () -> Unit,
    onStop: () -> Unit,
    onAskMicrophone: () -> Unit,
    picked: CustomVoices.Picked?,
    onPickFile: () -> Unit,
    typed: String,
    onTyped: (String) -> Unit,
    busy: Boolean,
    linkBlocker: String?,
    onSend: (ByteArray, String) -> Unit,
    onCancel: () -> Unit,
) {
    val chrome = LocalChrome.current
    Plate {
        Text("Add a voice", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
        Gap(6)
        Text(CustomVoices.CONSENT, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        Gap(10)
        TextInput(value = name, onValueChange = onName, label = "Name", placeholder = "Grandpa")
        Gap(10)
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            OptionChip("Record a sentence", isSelected = !fromFile, modifier = Modifier.weight(1f), onClick = { onFromFile(false) })
            OptionChip("Pick a file", isSelected = fromFile, modifier = Modifier.weight(1f), onClick = { onFromFile(true) })
        }
    }

    val bytes: ByteArray?
    val seconds: Double?
    val words: String
    if (!fromFile) {
        SentencePlate(
            index = 0,
            total = 1,
            sentence = sentence,
            clip = clip,
            recordingThis = recording,
            busy = busy,
            level = level,
            problem = problem,
            needsMic = needsMic,
            onRecord = onRecord,
            onStop = onStop,
            onAskMicrophone = onAskMicrophone,
            onPrevious = null,
            onNext = onAnotherSentence,
            nextLabel = "Another sentence",
            heading = "Have the person read this sentence, 3 to 10 seconds, in their normal voice",
        )
        bytes = clip?.wav
        seconds = clip?.seconds?.toDouble()
        // The words ARE the sentence shown: the phone never turns speech into text.
        words = sentence
    } else {
        Plate {
            Secondary(
                text = if (picked == null) "Pick an audio file (.wav)" else "Pick another file",
                enabled = !busy,
                modifier = Modifier.fillMaxWidth(),
                onClick = onPickFile,
            )
            Gap(6)
            val pickProblem: String? = picked?.problem
            val pickSeconds: Double? = picked?.seconds
            when {
                picked == null -> Text(
                    "A WAV file with 3 to 10 seconds of one person speaking.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textMid,
                )
                pickProblem != null -> Text(pickProblem, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                else -> Text(
                    "Picked: ${CustomVoices.length(pickSeconds ?: 0.0)} of sound.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.okInk,
                )
            }
            Gap(10)
            TextInput(
                value = typed,
                onValueChange = onTyped,
                label = "Exactly what is said in it",
                placeholder = "Every word, and nothing else",
                singleLine = false,
                maxLines = 5,
            )
        }
        bytes = picked?.takeIf { it.problem == null }?.bytes
        seconds = picked?.seconds
        words = typed
    }

    Plate {
        val blocked = CustomVoices.createBlocker(name, words, bytes, seconds, s, linkBlocker)
        Primary(
            text = "Add this voice (asks for approval)",
            busy = busy,
            enabled = blocked == null && !busy && !recording,
            modifier = Modifier.fillMaxWidth(),
            onClick = { if (bytes != null) onSend(bytes, words) },
        )
        if (blocked != null) {
            Gap(6)
            Text(blocked, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }
        Gap(6)
        Text(
            "Your PC shows an approval card with the words and the length. Nothing is kept until " +
                "you approve it, and Jarvis does not start speaking in the voice until you switch to it.",
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textMid,
        )
        Gap(4)
        Quiet("Cancel", enabled = !busy, onClick = onCancel)
    }
}

/** The better voice's switch: ON asks (a card), OFF is at once. Offered only on a PC that can. */
@Composable
private fun BetterVoicePlate(
    s: CustomVoices.Status,
    busy: Boolean,
    linkBlocker: String?,
    onSet: (Boolean) -> Unit,
) {
    val chrome = LocalChrome.current
    val b = s.better
    Plate {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("The better voice", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
                Text(
                    "A more natural copy of your custom voice, made on the second graphics card.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textMid,
                )
            }
            if (b.canTurnOn || b.enabled) {
                Toggle(
                    checked = b.enabled,
                    // Turning it on asks, so it is held on a stale link and while a card waits.
                    enabled = !busy && (b.enabled || (!b.pending && linkBlocker == null)),
                    onCheckedChange = { on -> onSet(on) },
                )
            }
        }
        Gap(6)
        Text(CustomVoices.betterLine(s), style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        if (!b.files && (b.canTurnOn || b.enabled)) {
            Gap(4)
            Text(CustomVoices.sentence(b.filesWhy), style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
        b.lastWhy.takeIf { it.isNotBlank() }?.let {
            Gap(4)
            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
        if (!b.enabled && b.canTurnOn && linkBlocker != null) {
            Gap(4)
            Text(linkBlocker, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
        }
    }
}
