package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
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
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.client.net.VoiceStatus
import com.jarvis.client.ui.parts.Dot
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.voice.VoiceTraining
import kotlinx.coroutines.launch
import java.util.concurrent.atomic.AtomicBoolean

/**
 * "Train my voice": read twelve short sentences, send them to the PC,
 * approve the card. Then, optionally, "check it with someone else".
 *
 * Three stages on one screen: a short explanation, then one sentence at a
 * time (tap Record, read it, tap Stop - each clip's length is shown and any
 * one can be redone), then a review with "Send to your PC". After sending,
 * the screen says to approve the card; the PC learns nothing until that card
 * is approved, and throws the recordings away either way.
 *
 * The clips live in this screen's memory and nowhere else. They are dropped
 * the moment the PC accepts them, and when the screen is left - there is no
 * file, no cache and no log line with audio in it. A rotation also drops
 * them (and starts again from the explanation): keeping audio across that
 * would mean saving it, which is the one thing this screen must not do.
 *
 * Tap-to-start and tap-to-stop rather than hold-to-talk: reading a whole
 * sentence off the screen while holding a button down is awkward, and the
 * recorder underneath is the same one the talk button uses, so the PC gets
 * the same 16 kHz WAV it checks every other time.
 *
 * "Check it with someone else" (only when the PC understands it, see
 * [VoiceTraining.canCheck]): another person reads three sentences; the PC
 * scores them against the owner's voice print, throws them away and says
 * whether they would have passed. When the owner's own training clips all
 * scored above every one of theirs, it suggests a stricter setting, and
 * the one button here that uses it ASKS - it raises an approval card, like
 * everything else that changes who Jarvis obeys.
 *
 * @param linkBlocker why nothing can be sent right now (link down or stale),
 *   or null. The same rule every other write on the phone follows.
 * @param record records one clip until `stop()` returns true.
 * @param send sends the clips; the answer says whether a card is now up.
 * @param checkOthers sends someone else's clips to be scored (changes nothing).
 * @param proposeThreshold asks for a card to use a stricter setting.
 * @param onAskMicrophone opens the system's microphone permission dialog.
 */
@Composable
fun VoiceTrainingScreen(
    status: VoiceStatus,
    answered: Boolean,
    linkBlocker: String?,
    record: suspend (stop: () -> Boolean, onLevel: (Float) -> Unit) -> VoiceTraining.Take,
    send: suspend (List<ByteArray>) -> VoiceTraining.SendResult,
    checkOthers: suspend (List<ByteArray>) -> VoiceTraining.CheckResult,
    proposeThreshold: suspend (Double) -> VoiceTraining.SendResult,
    onRefresh: suspend () -> Unit,
    onAskMicrophone: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    val sentences = VoiceTraining.SENTENCES
    val total = sentences.size
    val scope = rememberCoroutineScope()

    val clips = remember { mutableStateListOf<VoiceTraining.Clip?>().apply { repeat(total) { add(null) } } }
    // -1: the explanation. 0 until total: that sentence. total: the review.
    var step by remember { mutableIntStateOf(-1) }
    var recording by remember { mutableStateOf<Int?>(null) }
    val stopFlag = remember { AtomicBoolean(false) }
    var level by remember { mutableFloatStateOf(0f) }
    var problem by remember { mutableStateOf<String?>(null) }
    var needsMic by remember { mutableStateOf(false) }
    var sending by remember { mutableStateOf(false) }
    var sendNote by remember { mutableStateOf<String?>(null) }
    var sent by remember { mutableStateOf(false) }
    var refreshing by remember { mutableStateOf(false) }

    // "Check it with someone else": -1 not started, 0..2 that sentence,
    // 3 compare/result. Their clips live here only, like the owner's.
    val others = VoiceTraining.OTHER_SENTENCES
    val otherClips = remember {
        mutableStateListOf<VoiceTraining.Clip?>().apply { repeat(others.size) { add(null) } }
    }
    var checkStep by remember { mutableIntStateOf(-1) }
    var checking by remember { mutableStateOf(false) }
    var checkResult by remember { mutableStateOf<VoiceTraining.CheckResult?>(null) }
    var proposing by remember { mutableStateOf(false) }
    var proposeNote by remember { mutableStateOf<String?>(null) }

    // Leaving the screen stops the microphone and forgets every clip.
    DisposableEffect(Unit) {
        onDispose {
            stopFlag.set(true)
            clips.clear()
            otherClips.clear()
        }
    }

    /** Records into slot [i] of [into]; [key] tells the two lists' sentences apart. */
    fun startRecording(
        i: Int,
        into: MutableList<VoiceTraining.Clip?> = clips,
        key: Int = i,
    ) {
        if (recording != null || sending || checking) return
        problem = null
        needsMic = false
        stopFlag.set(false)
        recording = key
        scope.launch {
            val take = try {
                record({ stopFlag.get() }, { level = it })
            } finally {
                recording = null
                level = 0f
            }
            when (take) {
                is VoiceTraining.Take.Captured -> {
                    val bad = VoiceTraining.clipProblem(take.seconds)
                    if (bad == null) {
                        // Guarded: the list is emptied when the screen is left.
                        if (i < into.size) into[i] = VoiceTraining.Clip(take.wav, take.seconds)
                    } else {
                        problem = bad
                    }
                }
                is VoiceTraining.Take.Failed -> {
                    problem = take.message
                    needsMic = take.needsPermission
                }
            }
        }
    }

    fun compareOthers() {
        if (checking || otherClips.any { it == null }) return
        val payload = otherClips.mapNotNull { it?.wav }
        checking = true
        checkResult = null
        proposeNote = null
        scope.launch {
            val result = try {
                checkOthers(payload)
            } finally {
                checking = false
            }
            checkResult = result
            // Scored and thrown away on the PC; nothing kept here either.
            for (k in otherClips.indices) otherClips[k] = null
        }
    }

    fun sendAll() {
        val done = clips.count { it != null }
        val blocked = VoiceTraining.sendBlocker(done, total, linkBlocker, totalSeconds(clips))
        if (blocked != null || sending) {
            sendNote = blocked
            return
        }
        val payload = clips.mapNotNull { it?.wav }
        sending = true
        sendNote = null
        scope.launch {
            val result = try {
                send(payload)
            } finally {
                sending = false
            }
            sendNote = result.message
            if (result.accepted) {
                // Sent: this phone keeps no copy.
                for (k in clips.indices) clips[k] = null
                sent = true
                onRefresh()
            }
        }
    }

    Column(modifier.fillMaxSize().background(chrome.surface0).navigationBarsPadding()) {
        TopBar(
            "Train my voice",
            onBack = {
                stopFlag.set(true)
                onBack()
            },
            subtitle = "So Jarvis knows it is you",
        )

        Column(
            Modifier
                .weight(1f)
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            VoiceNowPlate(status, answered)

            when {
                checkStep in others.indices -> {
                    Text(
                        "Hand the phone to the other person.",
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                    )
                    SentencePlate(
                        index = checkStep,
                        total = others.size,
                        sentence = others[checkStep],
                        clip = otherClips.getOrNull(checkStep),
                        recordingThis = recording == OTHER_KEY + checkStep,
                        busy = recording != null && recording != OTHER_KEY + checkStep,
                        level = level,
                        problem = problem,
                        needsMic = needsMic,
                        onRecord = { startRecording(checkStep, otherClips, OTHER_KEY + checkStep) },
                        onStop = { stopFlag.set(true) },
                        onAskMicrophone = onAskMicrophone,
                        onPrevious = {
                            problem = null
                            if (checkStep == 0) {
                                for (k in otherClips.indices) otherClips[k] = null
                                checkStep = -1
                            } else {
                                checkStep -= 1
                            }
                        },
                        onNext = {
                            problem = null
                            checkStep += 1
                            if (checkStep == others.size) compareOthers()
                        },
                        nextLabel = if (checkStep == others.size - 1) "Compare with my voice" else "Next sentence",
                    )
                }

                checkStep == others.size -> Plate {
                    Text(
                        "Someone else's voice",
                        style = MaterialTheme.typography.titleSmall,
                        color = chrome.textHi,
                    )
                    Gap(6)
                    val result = checkResult
                    when {
                        checking || result == null -> Text(
                            "Comparing on your PC...",
                            style = MaterialTheme.typography.bodyMedium,
                            color = chrome.textMid,
                        )
                        else -> {
                            Text(
                                result.message,
                                style = MaterialTheme.typography.bodyMedium,
                                color = if (result.ok) chrome.textHi else chrome.warnInk,
                            )
                            val suggested = result.suggested
                            if (suggested != null) {
                                Gap(10)
                                Primary(
                                    text = "Use ${VoiceTraining.score(suggested)} (asks for approval)",
                                    busy = proposing,
                                    enabled = !proposing && linkBlocker == null,
                                    modifier = Modifier.fillMaxWidth(),
                                    onClick = {
                                        proposing = true
                                        scope.launch {
                                            val r = try {
                                                proposeThreshold(suggested)
                                            } finally {
                                                proposing = false
                                            }
                                            proposeNote = r.message
                                        }
                                    },
                                )
                                Gap(4)
                                Text(
                                    "Nothing changes until you approve the card.",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = chrome.textMid,
                                )
                            }
                            (proposeNote ?: linkBlocker?.takeIf { suggested != null })?.let {
                                Gap(6)
                                Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                            }
                        }
                    }
                    Gap(12)
                    Secondary(
                        text = "Done",
                        enabled = !checking && !proposing,
                        modifier = Modifier.fillMaxWidth(),
                        onClick = {
                            checkStep = -1
                            checkResult = null
                            proposeNote = null
                        },
                    )
                }

                sent -> Plate {
                    Text(
                        "Sent to your PC",
                        style = MaterialTheme.typography.titleSmall,
                        color = chrome.textHi,
                    )
                    Gap(6)
                    Text(
                        sendNote ?: VoiceTraining.AFTER_SENDING,
                        style = MaterialTheme.typography.bodyMedium,
                        color = chrome.textHi,
                    )
                    Gap(6)
                    Text(
                        "Nothing changes until the card is approved. If nobody answers it, it " +
                            "expires and the recordings are deleted.",
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                    )
                    Gap(12)
                    Secondary(
                        text = "Check whether it worked",
                        busy = refreshing,
                        enabled = !refreshing,
                        modifier = Modifier.fillMaxWidth(),
                        onClick = {
                            refreshing = true
                            scope.launch {
                                try {
                                    onRefresh()
                                } finally {
                                    refreshing = false
                                }
                            }
                        },
                    )
                    Gap(8)
                    Primary(text = "Done", modifier = Modifier.fillMaxWidth(), onClick = onBack)
                }

                step < 0 -> Plate {
                    Text(
                        VoiceTraining.INTRO,
                        style = MaterialTheme.typography.bodyLarge,
                        color = chrome.textHi,
                    )
                    Gap(8)
                    Text(
                        VoiceTraining.INTRO_DETAIL,
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                    )
                    Gap(12)
                    Primary(
                        text = "Start",
                        modifier = Modifier.fillMaxWidth(),
                        onClick = { step = 0 },
                    )
                }

                step < total -> SentencePlate(
                    index = step,
                    total = total,
                    sentence = sentences[step],
                    clip = clips.getOrNull(step),
                    recordingThis = recording == step,
                    busy = recording != null && recording != step,
                    level = level,
                    problem = problem,
                    needsMic = needsMic,
                    onRecord = { startRecording(step) },
                    onStop = { stopFlag.set(true) },
                    onAskMicrophone = onAskMicrophone,
                    onPrevious = if (step > 0) {
                        {
                            problem = null
                            step -= 1
                        }
                    } else {
                        null
                    },
                    onNext = {
                        problem = null
                        step += 1
                    },
                    nextLabel = if (step == total - 1) "Review" else "Next sentence",
                )

                else -> Plate {
                    Text(
                        "Check your recordings",
                        style = MaterialTheme.typography.titleSmall,
                        color = chrome.textHi,
                    )
                    Gap(6)
                    sentences.forEachIndexed { i, s ->
                        val c = clips.getOrNull(i)
                        Row(
                            Modifier.fillMaxWidth().padding(vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Dot(if (c != null) chrome.okInk else chrome.warnInk)
                            Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) {
                                Text(
                                    s,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = chrome.textHi,
                                )
                                Text(
                                    if (c != null) VoiceTraining.lengthLabel(c.seconds) else "Not recorded",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = chrome.textMid,
                                )
                            }
                            Quiet(if (c != null) "Redo" else "Record", enabled = !sending) {
                                problem = null
                                step = i
                            }
                        }
                    }
                    Gap(12)
                    val blocked = VoiceTraining.sendBlocker(
                        clips.count { it != null },
                        total,
                        linkBlocker,
                        totalSeconds(clips),
                    )
                    Primary(
                        text = "Send to your PC",
                        busy = sending,
                        enabled = blocked == null && !sending,
                        modifier = Modifier.fillMaxWidth(),
                        onClick = { sendAll() },
                    )
                    val note = sendNote ?: blocked
                    if (note != null) {
                        Gap(6)
                        Text(note, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                    }
                    Gap(6)
                    Text(
                        "Sending raises an approval card. Jarvis only learns your voice once " +
                            "you approve it.",
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textMid,
                    )
                }
            }

            // Offered from the first screen and after sending, never in the
            // middle of recording the owner's own sentences.
            if (checkStep < 0 && (step < 0 || sent) && VoiceTraining.canCheck(status, answered)) {
                Plate {
                    Text(
                        "Check it with someone else",
                        style = MaterialTheme.typography.titleSmall,
                        color = chrome.textHi,
                    )
                    Gap(6)
                    Text(
                        VoiceTraining.CHECK_INTRO,
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                    )
                    Gap(10)
                    Secondary(
                        text = "Start the check",
                        enabled = recording == null && !sending,
                        modifier = Modifier.fillMaxWidth(),
                        onClick = {
                            problem = null
                            checkResult = null
                            proposeNote = null
                            checkStep = 0
                        },
                    )
                }
            }
        }
    }
}

/** [recording] keys for the other person's sentences, apart from the owner's 0..11. */
private const val OTHER_KEY = 100

private fun totalSeconds(clips: List<VoiceTraining.Clip?>): Float = clips.sumOf { (it?.seconds ?: 0f).toDouble() }.toFloat()

/** What the PC says right now: trained or not, and with which check. */
@Composable
private fun VoiceNowPlate(status: VoiceStatus, answered: Boolean) {
    val chrome = LocalChrome.current
    val trained = answered && status.available && status.gate.enrolled && !status.gate.needsRetraining
    Plate {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Dot(if (trained) chrome.okInk else chrome.warnInk)
            Spacer(Modifier.width(10.dp))
            Text("Your voice now", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
        }
        Gap(6)
        Text(
            VoiceTraining.stateLine(status, answered),
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
        VoiceTraining.lastLine(status.gate.training.last)?.let {
            Gap(4)
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        VoiceTraining.desktopLine(status, answered)?.let {
            Gap(4)
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        VoiceTraining.basicCheckLine(status, answered)?.let {
            Gap(6)
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }
    }
}

@Composable
private fun SentencePlate(
    index: Int,
    total: Int,
    sentence: String,
    clip: VoiceTraining.Clip?,
    recordingThis: Boolean,
    busy: Boolean,
    level: Float,
    problem: String?,
    needsMic: Boolean,
    onRecord: () -> Unit,
    onStop: () -> Unit,
    onAskMicrophone: () -> Unit,
    onPrevious: (() -> Unit)?,
    onNext: () -> Unit,
    nextLabel: String,
) {
    val chrome = LocalChrome.current
    Plate {
        Text(
            "Sentence ${index + 1} of $total",
            style = MaterialTheme.typography.labelMedium,
            color = chrome.textMid,
        )
        Gap(8)
        Text(sentence, style = MaterialTheme.typography.titleMedium, color = chrome.textHi)
        Gap(12)

        if (recordingThis) {
            // A plain level bar, so the owner can see the phone is hearing them.
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(6.dp)
                    .background(chrome.surface2),
            ) {
                Box(
                    Modifier
                        .fillMaxHeight()
                        .fillMaxWidth((level * 4f).coerceIn(0.02f, 1f))
                        .background(chrome.okInk),
                )
            }
            Gap(8)
            Primary(
                text = "Stop",
                color = chrome.warnInk,
                modifier = Modifier.fillMaxWidth(),
                onClick = onStop,
            )
            Gap(4)
            Text(
                "Recording. Read the sentence, then tap Stop.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
            )
        } else {
            if (clip != null) {
                Text(
                    "Recorded: ${VoiceTraining.lengthLabel(clip.seconds)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.okInk,
                )
                Gap(8)
            }
            val recordText = if (clip != null) "Redo this one" else "Record"
            if (clip == null) {
                Primary(
                    text = recordText,
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth(),
                    onClick = onRecord,
                )
            } else {
                Secondary(
                    text = recordText,
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth(),
                    onClick = onRecord,
                )
            }
        }

        if (problem != null) {
            Gap(8)
            Text(problem, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
            if (needsMic) {
                Gap(6)
                Secondary(
                    text = "Allow the microphone",
                    modifier = Modifier.fillMaxWidth(),
                    onClick = onAskMicrophone,
                )
            }
        }

        Gap(12)
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            if (onPrevious != null) {
                Quiet("Back", enabled = !recordingThis, onClick = onPrevious)
            }
            Spacer(Modifier.weight(1f))
            if (clip != null && !recordingThis) {
                Primary(text = nextLabel, onClick = onNext)
            }
        }
    }
}
