package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
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
 * How fast Jarvis speaks is the PC's own three choices: no card either way,
 * held on a stale link like every change sent to the PC.
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
    setSpeed: suspend (id: String) -> CustomVoices.Answer?,
    setSpeaker: suspend (id: String) -> CustomVoices.Answer?,
    setFace: suspend (on: Boolean) -> CustomVoices.Answer?,
    /** The one-time "Use it" / "Keep my voice" answer for [face]: true is "Use it". */
    answerFaceOffer: suspend (face: String, use: Boolean) -> CustomVoices.Answer? = { _, _ -> null },
    /** One animal's voice, or its reset: the body is CustomVoices.animalBody / animalResetBody. */
    setAnimal: suspend (json: String) -> CustomVoices.Answer?,
    /**
     * "Try it": plays the PC's line in that animal's voice; told the words
     * to show as it starts playing, and returns the words to show after.
     */
    tryAnimal: suspend (face: String, name: String, playing: (String) -> Unit) -> String,
    /**
     * "Hear it" on a built-in voice: plays the PC's fixed line in that voice
     * (by its id) and changes nothing; told the words to show as it starts
     * playing, and returns the words to show after (CustomVoices `HEAR_*`).
     */
    hearVoice: suspend (id: String, label: String, playing: (String) -> Unit) -> String,
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
            // A "Hear it" sample must not keep playing after this screen is left.
            runCatching { JarvisRuntime.voice.stopSamples() }
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
                    "Asking your PC…",
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

                    s.speed?.let { sp ->
                        SpeedPlate(sp, busy, linkBlocker, onSet = { id -> act { setSpeed(id) } })
                    }
                    s.speaker?.let { sk ->
                        SpeakerPlate(
                            sk,
                            busy,
                            linkBlocker,
                            onSet = { id -> act { setSpeaker(id) } },
                            onHear = hearVoice,
                        )
                    }
                    s.faceVoice?.let { fv ->
                        // The one-time question, right above the switch it turns on.
                        fv.offer?.let { offer ->
                            FaceVoiceOfferPlate(offer, busy, linkBlocker, onAnswer = { use ->
                                act { answerFaceOffer(offer.face, use) }
                            })
                        }
                        FaceVoicePlate(fv, busy, linkBlocker, onSet = { on -> act { setFace(on) } })
                        if (fv.animals.isNotEmpty()) {
                            AnimalVoicesPlate(
                                fv,
                                busy,
                                linkBlocker,
                                onSet = { json -> act { setAnimal(json) } },
                                onTry = tryAnimal,
                                onAnswer = { face, use -> act { answerFaceOffer(face, use) } },
                            )
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
                            Text(CustomVoices.TIMINGS_TITLE, style = MaterialTheme.typography.labelMedium, color = chrome.textMid)
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

/**
 * "How fast Jarvis speaks": the PC's own choices and words. No card either
 * way; held on a stale link, like every change sent to the PC.
 */
@Composable
private fun SpeedPlate(
    sp: CustomVoices.Speed,
    busy: Boolean,
    linkBlocker: String?,
    onSet: (String) -> Unit,
) {
    ChoicePlate(
        title = sp.title,
        detail = sp.detail,
        note = sp.note,
        choices = sp.choices.map { it.id to it.label },
        choice = sp.choice,
        busy = busy,
        linkBlocker = linkBlocker,
        onSet = onSet,
    )
}

/**
 * "Jarvis's built-in voice": which of Kokoro's own voices - the PC's own
 * choices (by name) and words, the same title, detail, choice and note as
 * [SpeedPlate] right next to it, but one ROW per voice: the choice chip and a
 * "Hear it" button beside it (2026-09-29). No card either way; held on a stale
 * link, like every change sent to the PC. "Hear it" changes nothing, so it is
 * not held on a stale link; it plays the PC's sample and says what it is doing
 * in the desktop's words (`CustomVoices.HEAR_*`).
 */
@Composable
private fun SpeakerPlate(
    sk: CustomVoices.Speaker,
    busy: Boolean,
    linkBlocker: String?,
    onSet: (String) -> Unit,
    onHear: suspend (id: String, label: String, playing: (String) -> Unit) -> String,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    // Which voice is being heard, and the words that go under THAT voice's row.
    var hearing by remember { mutableStateOf<String?>(null) }
    var said by remember { mutableStateOf("") }
    var saidFor by remember { mutableStateOf<String?>(null) }
    Plate {
        Text(sk.title, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
        if (sk.detail.isNotBlank()) {
            Gap(4)
            Text(sk.detail, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
        Gap(8)
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (c in sk.choices) {
                // A row, and under it the PC's one plain line when it has one
                // (only Ashby and Clara, the voices made for Jarvis, do).
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OptionChip(
                            c.label,
                            modifier = Modifier.weight(1f),
                            isSelected = c.id == sk.choice,
                            enabled = !busy && linkBlocker == null,
                            onClick = { if (c.id != sk.choice) onSet(c.id) },
                        )
                        Quiet(
                            if (hearing == c.id) "Playing..." else CustomVoices.HEAR_LABEL,
                            modifier = Modifier.semantics { contentDescription = "Hear ${c.label}" },
                            enabled = hearing == null,
                            onClick = {
                                hearing = c.id
                                saidFor = c.id
                                said = CustomVoices.TRY_ASKING
                                scope.launch {
                                    try {
                                        said = onHear(c.id, c.label) { words -> said = words }
                                    } finally {
                                        hearing = null
                                    }
                                }
                            },
                        )
                    }
                    if (c.detail.isNotBlank()) {
                        Text(c.detail, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                    }
                    // What happened when THIS voice's button was pressed, right
                    // under it - not only below a long list.
                    if (said.isNotBlank() && saidFor == c.id) {
                        Text(said, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                    }
                }
            }
        }
        if (sk.note.isNotBlank()) {
            Gap(6)
            Text(sk.note, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
        if (linkBlocker != null) {
            Gap(4)
            Text(linkBlocker, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
        }
    }
}

/**
 * The plate speed and the built-in-voice choice share: a title, a detail
 * line, one chip per choice - wrapped in a [FlowRow] rather than a plain
 * Row, since the built-in voice offers many more of them than speed's
 * three and a Row does not wrap (BrainScreen.kt's FlowChips, same reason)
 * - and an optional note.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ChoicePlate(
    title: String,
    detail: String,
    note: String,
    choices: List<Pair<String, String>>,
    choice: String,
    busy: Boolean,
    linkBlocker: String?,
    onSet: (String) -> Unit,
) {
    val chrome = LocalChrome.current
    Plate {
        Text(title, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
        if (detail.isNotBlank()) {
            Gap(4)
            Text(detail, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
        Gap(8)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for ((id, label) in choices) {
                OptionChip(
                    label,
                    isSelected = id == choice,
                    enabled = !busy && linkBlocker == null,
                    onClick = { if (id != choice) onSet(id) },
                )
            }
        }
        if (note.isNotBlank()) {
            Gap(6)
            Text(note, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
        if (linkBlocker != null) {
            Gap(4)
            Text(linkBlocker, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
        }
    }
}

/**
 * The one-time question the first time the owner picks an animal face
 * (owner, 2026-09-28): "The panda has its own voice. Use it?" with "Use it"
 * and "Keep my voice" - every word the PC's own, shown as sent. The PC
 * remembers the answer per face. No card either way; both buttons are held
 * on a stale link (rule 4), like the switch below it.
 */
@Composable
internal fun FaceVoiceOfferPlate(
    offer: CustomVoices.FaceOffer,
    busy: Boolean,
    linkBlocker: String?,
    onAnswer: (use: Boolean) -> Unit,
) {
    val chrome = LocalChrome.current
    Plate {
        Text(offer.question, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
        Gap(8)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Secondary(offer.use, enabled = !busy && linkBlocker == null, onClick = { onAnswer(true) })
            Quiet(offer.keep, enabled = !busy && linkBlocker == null, onClick = { onAnswer(false) })
        }
        if (linkBlocker != null) {
            Gap(4)
            Text(linkBlocker, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
        }
    }
}

/**
 * [FaceVoiceOfferPlate] where a face is picked (Appearance): reads the PC's
 * voices answer the runtime already holds, and answers through
 * [JarvisRuntime.answerFaceVoiceOffer]. Draws nothing when no question is
 * waiting, or on a PC too old to ask one.
 */
@Composable
internal fun FaceVoiceOfferFromPc(linkBlocker: String?) {
    val read by JarvisRuntime.customVoices.collectAsState()
    val offer = (read as? CustomVoices.Read.Loaded)?.status?.faceVoice?.offer ?: return
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    FaceVoiceOfferPlate(offer, busy, linkBlocker, onAnswer = { use ->
        if (!busy) {
            busy = true
            scope.launch {
                try {
                    JarvisRuntime.answerFaceVoiceOffer(offer.face, use)
                } finally {
                    busy = false
                }
            }
        }
    })
}

/**
 * "Voice follows the face": with an animal face showing, the built-in voice
 * becomes that animal's. An on/off switch right under the built-in voice it
 * changes, the PC's own words, and the PC's line saying what is happening
 * now. No card either way; held on a stale link, like every change sent to
 * the PC - the same switch the better voice uses below.
 */
@Composable
private fun FaceVoicePlate(
    fv: CustomVoices.FaceVoice,
    busy: Boolean,
    linkBlocker: String?,
    onSet: (Boolean) -> Unit,
) {
    val chrome = LocalChrome.current
    Plate {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(fv.title, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
                if (fv.detail.isNotBlank()) {
                    Text(fv.detail, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                }
            }
            Toggle(
                checked = fv.enabled,
                enabled = !busy && linkBlocker == null,
                onCheckedChange = { on -> onSet(on) },
                // Named for TalkBack, as Parts.kt asks of every Toggle.
                modifier = Modifier.semantics { contentDescription = fv.title },
            )
        }
        if (fv.line.isNotBlank()) {
            Gap(6)
            Text(fv.line, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        if (linkBlocker != null) {
            Gap(4)
            Text(linkBlocker, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
        }
    }
}

/**
 * Each animal's voice, under "Voice follows the face": for the red panda,
 * pygmy owl and sea otter, one of the built-in voices, a pitch (deeper or
 * higher) and a pace - the PC's own choices and words - with "Try it" and
 * "Reset to its own voice". Every change goes at once, no card either way,
 * and is held on a stale link like every change sent to the PC. Try it
 * changes nothing, so it is not held.
 *
 * The voice list is folded away behind "Voice: <name>" (eleven chips for
 * each of four animals would bury the rest of the screen); the pitch is two
 * buttons either side of its value, which TalkBack reads as words ("2 steps
 * higher") - the desktop draws it as a slider.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AnimalVoicesPlate(
    fv: CustomVoices.FaceVoice,
    busy: Boolean,
    linkBlocker: String?,
    onSet: (String) -> Unit,
    onTry: suspend (face: String, name: String, playing: (String) -> Unit) -> String,
    onAnswer: (face: String, use: Boolean) -> Unit,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var open by remember { mutableStateOf<String?>(null) }
    var trying by remember { mutableStateOf<String?>(null) }
    var said by remember { mutableStateOf<Pair<String, String>?>(null) }
    val canChange = !busy && linkBlocker == null
    val c = fv.choices
    Plate {
        Text(fv.animalsTitle, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
        if (fv.animalsDetail.isNotBlank()) {
            Gap(4)
            Text(fv.animalsDetail, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
        for (a in fv.animals) {
            fun send(speaker: String = a.speaker, semitones: Double = a.semitones, pace: String = a.pace) =
                onSet(CustomVoices.animalBody(a.face, speaker, semitones, pace))
            Gap(12)
            Text(a.name, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
            if (a.line.isNotBlank()) {
                Text(a.line, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
            }
            val voiceName = c.voices.firstOrNull { it.id == a.speaker }?.label ?: a.speaker
            Quiet(
                if (open == a.face) "Voice: $voiceName (close)" else "Voice: $voiceName",
                modifier = Modifier.semantics {
                    contentDescription = "${a.name}'s voice: $voiceName. " +
                        if (open == a.face) "Close the list." else "Choose another."
                },
                enabled = canChange,
                onClick = { open = if (open == a.face) null else a.face },
            )
            if (open == a.face) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (v in c.voices) {
                        OptionChip(
                            v.label,
                            isSelected = v.id == a.speaker,
                            enabled = canChange,
                            onClick = {
                                open = null
                                if (v.id != a.speaker) send(speaker = v.id)
                            },
                        )
                    }
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Pitch", style = MaterialTheme.typography.labelMedium, color = chrome.textMid)
                Spacer(Modifier.width(8.dp))
                val deeper = CustomVoices.nextPitch(a.semitones, up = false, c)
                val higher = CustomVoices.nextPitch(a.semitones, up = true, c)
                Quiet(
                    "Deeper",
                    modifier = Modifier.semantics { contentDescription = "Make the ${a.name}'s voice deeper" },
                    enabled = canChange && deeper != null,
                    onClick = { deeper?.let { send(semitones = it) } },
                )
                Text(
                    CustomVoices.pitchShort(a.semitones),
                    modifier = Modifier.semantics {
                        contentDescription = "${a.name}'s pitch: " + CustomVoices.pitchWords(a.semitones)
                    },
                    style = MaterialTheme.typography.labelLarge,
                    color = chrome.textHi,
                )
                Quiet(
                    "Higher",
                    modifier = Modifier.semantics { contentDescription = "Make the ${a.name}'s voice higher" },
                    enabled = canChange && higher != null,
                    onClick = { higher?.let { send(semitones = it) } },
                )
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for (pc in c.paces) {
                    OptionChip(
                        pc.label,
                        modifier = Modifier.semantics { contentDescription = "${a.name}'s pace: ${pc.label}" },
                        isSelected = pc.id == a.pace,
                        enabled = canChange,
                        onClick = { if (pc.id != a.pace) send(pace = pc.id) },
                    )
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Quiet(
                    "Try it",
                    modifier = Modifier.semantics { contentDescription = "Try the ${a.name}'s voice" },
                    enabled = trying == null,
                    onClick = {
                        trying = a.face
                        // The desktop's words, step by step (CustomVoices `TRY_*`).
                        said = a.face to CustomVoices.TRY_ASKING
                        scope.launch {
                            try {
                                said = a.face to onTry(a.face, a.name) { words -> said = a.face to words }
                            } finally {
                                trying = null
                            }
                        }
                    },
                )
                Spacer(Modifier.weight(1f))
                Quiet(
                    "Reset to its own voice",
                    modifier = Modifier.semantics { contentDescription = "Reset the ${a.name} to its own voice" },
                    enabled = canChange && a.changed,
                    onClick = { onSet(CustomVoices.animalResetBody(a.face)) },
                )
            }
            // Change the one-time answer later (owner, 2026-09-28): nothing until answered.
            CustomVoices.changeMindLabel(a.answer)?.let { label ->
                Quiet(
                    label,
                    modifier = Modifier.semantics { contentDescription = "$label for the ${a.name}" },
                    enabled = canChange,
                    onClick = { CustomVoices.changeMindUse(a.answer)?.let { use -> onAnswer(a.face, use) } },
                )
            }
            said?.takeIf { it.first == a.face }?.let { (_, words) ->
                Text(words, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
            }
        }
        if (linkBlocker != null) {
            Gap(6)
            Text(linkBlocker, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
        }
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
                    modifier = Modifier.semantics { contentDescription = "The better voice" },
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
