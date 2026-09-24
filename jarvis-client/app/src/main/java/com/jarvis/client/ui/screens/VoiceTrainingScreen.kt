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
import com.jarvis.client.net.VoiceStrict
import com.jarvis.client.ui.parts.Dot
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.voice.StrictVoice
import com.jarvis.client.voice.VoiceRounds
import com.jarvis.client.voice.VoiceTraining
import kotlinx.coroutines.launch
import java.util.concurrent.atomic.AtomicBoolean

/**
 * "Train my voice": read short sentences, send them to the PC, approve the
 * card. Then, optionally, "check it with someone else".
 *
 * HOW MANY SENTENCES depends on the PC's voice check ([VoiceRounds.plan]):
 * balanced keeps one round of twelve; very strict asks for three rounds of
 * the same twelve, in three conditions (close; further away or quieter;
 * another time or room). Each round is sent as it is finished and HELD on
 * the PC, in memory, with no card; the last one raises ONE approval card for
 * all of them. An older PC gets today's single round.
 *
 * Also here: "Train more" (one more round in a condition Jarvis struggles
 * with, ADDED to the voice), "Record them again" (the recordings the PC left
 * out because they did not sound like the rest), picking up an unfinished
 * training the PC is still holding, and Cancel, which deletes everything
 * recorded so far - on this phone and on the PC.
 *
 * The clips live in this screen's memory and nowhere else. They are dropped
 * the moment the PC accepts a round, and when the screen is left - there is
 * no file, no cache and no log line with audio in it. A rotation also drops
 * them: keeping audio across that would mean saving it, which is the one
 * thing this screen must not do. Rounds already sent stay on the PC (it
 * deletes them 15 minutes after the last one), so coming back offers
 * "Continue with round N".
 *
 * "Check it with someone else" (only when the PC understands it, see
 * [VoiceTraining.canCheck]): another person reads three sentences; the PC
 * scores them against the owner's voice print, throws them away and says
 * whether they would have passed.
 *
 * @param linkBlocker why nothing can be sent right now (link down or stale),
 *   or null. The same rule every other write on the phone follows.
 * @param sentPlan the training this phone last finished sending, so the
 *   PC's "round 2, clip 5" can be turned back into the sentence to redo.
 * @param record records one clip until `stop()` returns true.
 * @param sendRound sends one round; the answer says whether the PC took it.
 * @param cancelRounds deletes whatever the PC is holding; never held back.
 */
@Composable
fun VoiceTrainingScreen(
    status: VoiceStatus,
    strict: VoiceStrict.View,
    answered: Boolean,
    linkBlocker: String?,
    sentPlan: VoiceRounds.Plan?,
    record: suspend (stop: () -> Boolean, onLevel: (Float) -> Unit) -> VoiceTraining.Take,
    sendRound: suspend (VoiceRounds.Plan, Int, List<ByteArray>) -> VoiceRounds.Result,
    cancelRounds: suspend () -> String,
    checkOthers: suspend (List<ByteArray>) -> VoiceTraining.CheckResult,
    proposeThreshold: suspend (Double) -> VoiceTraining.SendResult,
    onRefresh: suspend () -> Unit,
    onAskMicrophone: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()

    // The training being recorded, or null on the first screen.
    var plan by remember { mutableStateOf<VoiceRounds.Plan?>(null) }
    var roundIndex by remember { mutableIntStateOf(0) }
    val clips = remember { mutableStateListOf<VoiceTraining.Clip?>() }
    // -1: the round's own first screen. 0 until total: that sentence. total: the review.
    var step by remember { mutableIntStateOf(0) }
    var recording by remember { mutableStateOf<Int?>(null) }
    val stopFlag = remember { AtomicBoolean(false) }
    var level by remember { mutableFloatStateOf(0f) }
    var problem by remember { mutableStateOf<String?>(null) }
    var needsMic by remember { mutableStateOf(false) }
    var sending by remember { mutableStateOf(false) }
    var sendNote by remember { mutableStateOf<String?>(null) }
    // The PC's words after the round before this one was held.
    var roundNote by remember { mutableStateOf<String?>(null) }
    var sent by remember { mutableStateOf(false) }
    var refreshing by remember { mutableStateOf(false) }
    // The PC said another training is held (a 409 with `session`).
    var heldElsewhere by remember { mutableStateOf(false) }
    var confirmCancel by remember { mutableStateOf(false) }
    var cancelling by remember { mutableStateOf(false) }
    var cancelNote by remember { mutableStateOf<String?>(null) }

    val sentences: List<String> = plan?.rounds?.getOrNull(roundIndex)?.sentences
        ?.map { VoiceTraining.SENTENCES[it] }.orEmpty()
    val total = sentences.size

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

    fun resetClips(n: Int) {
        clips.clear()
        repeat(n) { clips.add(null) }
    }

    fun begin(p: VoiceRounds.Plan, index: Int = 0) {
        plan = p
        roundIndex = index
        resetClips(p.rounds[index].sentences.size)
        // Rounds each get a first screen saying where to record them; one
        // round starts on its first sentence, as it always has.
        step = if (p.kind == VoiceRounds.Kind.EXTENDED) -1 else 0
        roundNote = null
        sendNote = null
        sent = false
        heldElsewhere = false
        confirmCancel = false
        cancelNote = null
        problem = null
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

    fun sendThisRound() {
        val p = plan ?: return
        val index = roundIndex
        val blocked = VoiceRounds.sendBlocker(
            p, index, clips.count { it != null }, totalSeconds(clips), linkBlocker, strict.limits,
        )
        if (blocked != null || sending) {
            sendNote = blocked
            return
        }
        val payload = clips.mapNotNull { it?.wav }
        sending = true
        sendNote = null
        scope.launch {
            val result = try {
                sendRound(p, index, payload)
            } finally {
                sending = false
            }
            heldElsewhere = result.heldElsewhere
            if (!result.accepted) {
                sendNote = result.message
                return@launch
            }
            // Sent: this phone keeps no copy.
            for (k in clips.indices) clips[k] = null
            if (result.finished) {
                sendNote = result.message
                sent = true
                plan = null
                onRefresh()
            } else {
                roundIndex = index + 1
                resetClips(p.rounds[index + 1].sentences.size)
                step = -1
                roundNote = result.message
            }
        }
    }

    /** Deletes everything recorded so far - here, and whatever the PC holds. */
    fun cancelAll() {
        val onPc = (plan != null && roundIndex > 0) || heldElsewhere || strict.session != null
        stopFlag.set(true)
        plan = null
        clips.clear()
        step = 0
        roundIndex = 0
        confirmCancel = false
        sendNote = null
        roundNote = null
        problem = null
        if (!onPc) {
            cancelNote = VoiceRounds.cancelledLine(null)
            return
        }
        cancelling = true
        scope.launch {
            cancelNote = try {
                cancelRounds()
            } finally {
                cancelling = false
            }
            heldElsewhere = false
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
            VoiceNowPlate(status, strict, answered)

            val current = plan
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
                    Gap(4)
                    Quiet("Back to training", onClick = {
                        sent = false
                        sendNote = null
                    })
                }

                current == null -> {
                    cancelNote?.let {
                        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    StartPlates(
                        status = status,
                        strict = strict,
                        answered = answered,
                        sentPlan = sentPlan,
                        busy = cancelling,
                        onBegin = { p, i -> begin(p, i) },
                        onDeleteHeld = { cancelAll() },
                    )
                }

                current != null && step < 0 -> Plate {
                    Text(
                        VoiceRounds.roundTitle(current, roundIndex, strict),
                        style = MaterialTheme.typography.titleSmall,
                        color = chrome.textHi,
                    )
                    roundNote?.let {
                        Gap(6)
                        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    Gap(8)
                    Text(
                        if (roundIndex == 0) ROUND_FIRST else ROUND_AGAIN,
                        style = MaterialTheme.typography.bodyMedium,
                        color = chrome.textHi,
                    )
                    Gap(12)
                    Primary(
                        text = "Start round ${roundIndex + 1}",
                        modifier = Modifier.fillMaxWidth(),
                        onClick = { step = 0 },
                    )
                }

                current != null && step < total -> SentencePlate(
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
                    heading = VoiceRounds.roundTitle(current, roundIndex, strict)
                        .takeIf { current.kind != VoiceRounds.Kind.SINGLE && current.kind != VoiceRounds.Kind.SINGLE_OLD },
                )

                current != null -> Plate {
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
                    val blocked = VoiceRounds.sendBlocker(
                        current,
                        roundIndex,
                        clips.count { it != null },
                        totalSeconds(clips),
                        linkBlocker,
                        strict.limits,
                    )
                    Primary(
                        text = VoiceRounds.sendLabel(current, roundIndex),
                        busy = sending,
                        enabled = blocked == null && !sending,
                        modifier = Modifier.fillMaxWidth(),
                        onClick = { sendThisRound() },
                    )
                    val note = sendNote ?: blocked
                    if (note != null) {
                        Gap(6)
                        Text(note, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                    }
                    Gap(6)
                    Text(
                        if (VoiceRounds.isLast(current, roundIndex)) {
                            "Sending raises an approval card. Jarvis only learns your voice once " +
                                "you approve it."
                        } else {
                            "This round is kept in your PC's memory until the last one is sent. " +
                                "Nothing changes yet."
                        },
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textMid,
                    )
                }
            }

            // Cancel, while a training is being recorded.
            if (current != null && !sent && checkStep < 0) {
                Plate {
                    if (confirmCancel) {
                        Text(
                            VoiceRounds.CANCEL_NOTE,
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textHi,
                        )
                        Gap(10)
                        Primary(
                            text = "Delete the recordings",
                            color = chrome.warnInk,
                            busy = cancelling,
                            enabled = !sending && !cancelling,
                            modifier = Modifier.fillMaxWidth(),
                            onClick = { cancelAll() },
                        )
                        Gap(4)
                        Quiet("Keep going", onClick = { confirmCancel = false })
                    } else {
                        Quiet("Cancel this training", enabled = !sending, onClick = { confirmCancel = true })
                    }
                }
            }

            // Offered from the first screen and after sending, never in the
            // middle of recording the owner's own sentences.
            if (checkStep < 0 && (current == null || sent) && VoiceTraining.canCheck(status, answered)) {
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

/** The first of three rounds: what to do now. */
private const val ROUND_FIRST =
    "Hold the phone the way you usually do and read each sentence in your normal voice. " +
        "Tap Record, read it, then tap Stop."

/** Between rounds: what to do now. */
private const val ROUND_AGAIN =
    "Read the same 12 sentences again, in this new place or way. Take a break first if you " +
        "like - your PC keeps the earlier rounds for 15 minutes."

/**
 * The first screen: start a training, pick up one the PC is holding, record
 * again what the PC left out, or train more.
 */
@Composable
private fun StartPlates(
    status: VoiceStatus,
    strict: VoiceStrict.View,
    answered: Boolean,
    sentPlan: VoiceRounds.Plan?,
    busy: Boolean,
    onBegin: (VoiceRounds.Plan, Int) -> Unit,
    onDeleteHeld: () -> Unit,
) {
    val chrome = LocalChrome.current
    val first = VoiceRounds.plan(strict)

    // An unfinished training on the PC (sent before the app was closed, say).
    VoiceRounds.unfinishedLine(strict)?.let { line ->
        Plate {
            Text("Unfinished training", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
            Gap(6)
            Text(line, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            Gap(10)
            VoiceRounds.resume(strict, VoiceTraining.MIC)?.let { (p, next) ->
                Primary(
                    text = "Continue with round ${next + 1}",
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth(),
                    onClick = { onBegin(p, next) },
                )
                Gap(8)
            }
            Secondary(
                text = "Delete them",
                busy = busy,
                enabled = !busy,
                modifier = Modifier.fillMaxWidth(),
                onClick = onDeleteHeld,
            )
        }
    }

    // The recordings the PC left out of the last training.
    VoiceRounds.outliersLine(strict.last, sentPlan)?.let { line ->
        Plate {
            Text(line, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
            val redo = VoiceRounds.redo(strict, strict.last, sentPlan)
            Gap(10)
            if (redo != null) {
                Primary(
                    text = "Record them again",
                    modifier = Modifier.fillMaxWidth(),
                    onClick = { onBegin(redo, 0) },
                )
                Gap(4)
                Text(
                    VoiceRounds.introDetail(redo),
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textMid,
                )
            } else {
                Text(
                    "This phone does not know which sentences those were (it was restarted, or " +
                        "the training came from elsewhere). Use Train more below, or train again.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textMid,
                )
            }
        }
    }

    Plate {
        Text(VoiceRounds.intro(first), style = MaterialTheme.typography.bodyLarge, color = chrome.textHi)
        Gap(8)
        Text(VoiceRounds.introDetail(first), style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        Gap(12)
        Primary(
            text = "Start",
            enabled = !busy && strict.session == null,
            modifier = Modifier.fillMaxWidth(),
            onClick = { onBegin(first, 0) },
        )
        if (strict.session != null) {
            Gap(4)
            Text(
                "Finish or delete the unfinished training above first.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
            )
        }
    }

    // "Train more": only once there is a voice to add to.
    val trained = answered && status.available && status.gate.enrolled && !status.gate.needsRetraining
    if (trained && strict.rounds && strict.session == null) {
        Plate {
            Text("Train more", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
            Gap(6)
            Text(
                "Does Jarvis turn you away in one place more than others? Add 12 more " +
                    "recordings made that way. Nothing it has now is deleted. Pick one:",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            for (round in 1..3) {
                val more = VoiceRounds.more(strict, round) ?: continue
                Gap(8)
                Secondary(
                    text = VoiceRounds.ask(strict, round).replaceFirstChar { it.uppercase() },
                    modifier = Modifier.fillMaxWidth(),
                    onClick = { onBegin(more, 0) },
                )
            }
        }
    }
}

/** [recording] keys for the other person's sentences, apart from the owner's 0..11. */
private const val OTHER_KEY = 100

private fun totalSeconds(clips: List<VoiceTraining.Clip?>): Float = clips.sumOf { (it?.seconds ?: 0f).toDouble() }.toFloat()

/** What the PC says right now: trained or not, and with which check. */
@Composable
private fun VoiceNowPlate(status: VoiceStatus, strict: VoiceStrict.View, answered: Boolean) {
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
        StrictVoice.nowLine(strict)?.let {
            Gap(4)
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        VoiceTraining.lastLine(status.gate.training.last, strict.last)?.let {
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
        StrictVoice.modelLine(strict)?.let {
            Gap(6)
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }
    }
}

/**
 * One sentence to read: Record / Stop with a level bar, the length once
 * recorded, and Back / Next. Shared with the guided repeat test
 * ([VoiceCheckScreen]) and adding a custom voice ([VoicesScreen]), so all
 * three record the same way.
 */
@Composable
internal fun SentencePlate(
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
    /** A line above the counter - which round, or what this recording is for. */
    heading: String? = null,
) {
    val chrome = LocalChrome.current
    Plate {
        if (heading != null) {
            Text(heading, style = MaterialTheme.typography.labelMedium, color = chrome.textHi)
            Gap(4)
        }
        if (total > 1) {
            Text(
                "Sentence ${index + 1} of $total",
                style = MaterialTheme.typography.labelMedium,
                color = chrome.textMid,
            )
            Gap(8)
        }
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
