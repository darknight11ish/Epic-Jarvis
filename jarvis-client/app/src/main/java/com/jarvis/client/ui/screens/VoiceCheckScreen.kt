package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.client.net.VoiceStatus
import com.jarvis.client.net.VoiceStrict
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
 * "Voice check": how strict Jarvis is about the owner's voice, whether
 * private answers, answers that use memories, and answers that use
 * sensitive saved facts may be read aloud, how far a question started with
 * "Hey Jarvis" is trusted, the guided "how often would I have to say it
 * twice?" test, and how often that really happened.
 *
 * The settings follow the shape of every other switch that widens what
 * Jarvis does: the LOOSER choice (balanced; voice check is enough; read
 * aloud) asks -
 * one approval card on the PC, nothing changes until it is approved, and it
 * is held on a stale link. The STRICTER choice applies at once and always
 * goes. What is shown as chosen is what the PC last SAID, never what was
 * just tapped ([StrictVoice.isCurrent]); a card waiting is said in words.
 *
 * The test's recordings live in this screen's memory only, like "Train my
 * voice"'s, and are dropped when they are sent or the screen is left. The
 * PC scores them and keeps only the counts.
 */
@Composable
fun VoiceCheckScreen(
    status: VoiceStatus,
    strict: VoiceStrict.View,
    answered: Boolean,
    linkBlocker: String?,
    setSetting: suspend (setting: String, value: String) -> String,
    record: suspend (stop: () -> Boolean, onLevel: (Float) -> Unit) -> VoiceTraining.Take,
    measure: suspend (List<ByteArray>, List<Float>) -> StrictVoice.Tested,
    onRefresh: suspend () -> Unit,
    onAskMicrophone: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf<String?>(null) }
    var note by remember { mutableStateOf<Pair<String, String>?>(null) }

    val sentences = StrictVoice.MEASURE_SENTENCES
    val clips = remember { mutableStateListOf<VoiceTraining.Clip?>() }
    // -1: not started. 0 until 20: that sentence. 20: sending / result.
    var step by remember { mutableIntStateOf(-1) }
    var recording by remember { mutableStateOf<Int?>(null) }
    val stopFlag = remember { AtomicBoolean(false) }
    var level by remember { mutableFloatStateOf(0f) }
    var problem by remember { mutableStateOf<String?>(null) }
    var needsMic by remember { mutableStateOf(false) }
    var testing by remember { mutableStateOf(false) }
    var tested by remember { mutableStateOf<StrictVoice.Tested?>(null) }

    DisposableEffect(Unit) {
        onDispose {
            stopFlag.set(true)
            clips.clear()
        }
    }

    fun pick(setting: String, value: String) {
        if (busy != null || StrictVoice.isCurrent(setting, value, strict)) return
        val blocked = StrictVoice.blocker(setting, value, strict, linkBlocker)
        if (blocked != null) {
            note = setting to blocked
            return
        }
        busy = setting
        note = null
        scope.launch {
            val said = try {
                setSetting(setting, value)
            } finally {
                busy = null
            }
            note = setting to said
        }
    }

    fun startRecording(i: Int) {
        if (recording != null || testing) return
        problem = null
        needsMic = false
        stopFlag.set(false)
        recording = i
        scope.launch {
            val take = try {
                record({ stopFlag.get() }, { level = it })
            } finally {
                recording = null
                level = 0f
            }
            when (take) {
                is VoiceTraining.Take.Captured -> {
                    val bad = StrictVoice.measureClipProblem(take.seconds)
                    if (bad == null) {
                        if (i < clips.size) clips[i] = VoiceTraining.Clip(take.wav, take.seconds)
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

    fun runTest() {
        if (testing || clips.any { it == null }) return
        val wavs = clips.mapNotNull { it?.wav }
        val secs = clips.mapNotNull { it?.seconds }
        testing = true
        tested = null
        scope.launch {
            tested = try {
                measure(wavs, secs)
            } finally {
                testing = false
            }
            // Scored and thrown away on the PC; nothing kept here either.
            for (k in clips.indices) clips[k] = null
        }
    }

    Column(modifier.fillMaxSize().background(chrome.surface0).navigationBarsPadding()) {
        TopBar("Voice check", onBack = {
            stopFlag.set(true)
            onBack()
        }, subtitle = "How strict, and what may be read aloud")

        Column(
            Modifier
                .weight(1f)
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (step in sentences.indices) {
                SentencePlate(
                    index = step,
                    total = sentences.size,
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
                    onPrevious = {
                        problem = null
                        if (step == 0) {
                            clips.clear()
                            step = -1
                        } else {
                            step -= 1
                        }
                    },
                    onNext = {
                        problem = null
                        step += 1
                        if (step == sentences.size) runTest()
                    },
                    nextLabel = if (step == sentences.size - 1) "Check them on your PC" else "Next sentence",
                    heading = "Say it the way you would talk to Jarvis",
                )
                Quiet("Stop the test", onClick = {
                    stopFlag.set(true)
                    clips.clear()
                    step = -1
                })
            } else {
                CheckPlates(
                    status = status,
                    strict = strict,
                    answered = answered,
                    busy = busy,
                    note = note,
                    testing = testing,
                    tested = tested,
                    recordingAny = recording != null,
                    onPick = { s, v -> pick(s, v) },
                    onStartTest = {
                        tested = null
                        problem = null
                        clips.clear()
                        repeat(sentences.size) { clips.add(null) }
                        step = 0
                    },
                    onRefresh = { scope.launch { onRefresh() } },
                )
            }
        }
    }
}

/** Everything but the test's sentences: the check now, the two settings, the test, the numbers. */
@Composable
private fun CheckPlates(
    status: VoiceStatus,
    strict: VoiceStrict.View,
    answered: Boolean,
    busy: String?,
    note: Pair<String, String>?,
    testing: Boolean,
    tested: StrictVoice.Tested?,
    recordingAny: Boolean,
    onPick: (String, String) -> Unit,
    onStartTest: () -> Unit,
    onRefresh: () -> Unit,
) {
    val chrome = LocalChrome.current
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Plate {
                Text("The voice check now", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
                Gap(6)
                Text(
                    StrictVoice.nowLine(strict) ?: if (answered) StrictVoice.NOT_ON_THIS_PC else
                        "Your PC has not answered yet, so this is not known.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
                StrictVoice.lastLine(strict.last, strict)?.let {
                    Gap(4)
                    Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                }
                StrictVoice.modelLine(strict)?.let {
                    Gap(6)
                    Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                }
                // The PC's own words about the check (gate.note), as they are.
                strict.note.takeIf { it.isNotBlank() }?.let {
                    Gap(6)
                    Text(
                        "Your PC says: " + VoiceRounds.sentence(it),
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                    )
                }
            }

            if (strict.settings) {
                SettingPlate(
                    title = StrictVoice.STRICTNESS_TITLE,
                    setting = VoiceStrict.STRICTNESS,
                    choices = StrictVoice.STRICTNESS,
                    strict = strict,
                    busy = busy,
                    note = note?.takeIf { it.first == VoiceStrict.STRICTNESS }?.second,
                    onPick = onPick,
                )
                SettingPlate(
                    title = StrictVoice.PRIVACY_TITLE,
                    setting = VoiceStrict.PRIVACY,
                    choices = StrictVoice.PRIVACY,
                    strict = strict,
                    busy = busy,
                    note = note?.takeIf { it.first == VoiceStrict.PRIVACY }?.second,
                    onPick = onPick,
                )
                // Only when the PC reports it (a PC from before 2026-09-24 does not).
                if (strict.memory.isNotBlank()) {
                    SettingPlate(
                        title = StrictVoice.MEMORY_TITLE,
                        setting = VoiceStrict.MEMORY,
                        choices = StrictVoice.MEMORY,
                        strict = strict,
                        busy = busy,
                        note = note?.takeIf { it.first == VoiceStrict.MEMORY }?.second,
                        onPick = onPick,
                    )
                }
                // Sensitive saved facts (the owner's decision, 2026-09-24) -
                // only when the PC reports the setting. Always open: it holds
                // even under "voice check is enough".
                if (strict.sensitiveMemory.isNotBlank()) {
                    SettingPlate(
                        title = StrictVoice.SENSITIVE_MEMORY_TITLE,
                        setting = VoiceStrict.SENSITIVE_MEMORY,
                        choices = StrictVoice.SENSITIVE_MEMORY,
                        strict = strict,
                        busy = busy,
                        note = note?.takeIf { it.first == VoiceStrict.SENSITIVE_MEMORY }?.second,
                        onPick = onPick,
                    )
                }
                // Hands-free ("Hey Jarvis") (the owner's decision, 2026-09-24) -
                // only when the PC reports the setting. "Only trust the talk
                // button" applies at once; going back asks, and is held on a
                // stale link (StrictVoice.blocker).
                if (strict.handsFree.isNotBlank()) {
                    SettingPlate(
                        title = StrictVoice.HANDS_FREE_TITLE,
                        setting = VoiceStrict.HANDS_FREE,
                        choices = StrictVoice.HANDS_FREE,
                        strict = strict,
                        busy = busy,
                        note = note?.takeIf { it.first == VoiceStrict.HANDS_FREE }?.second,
                        onPick = onPick,
                    )
                }
                Text(
                    "Making it stricter applies at once. Making it looser asks first: an approval " +
                        "card on your PC or this phone's Home screen, and nothing changes until you " +
                        "approve it.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textMid,
                )
            }

            Plate {
                Text(
                    "How often would you have to say it twice?",
                    style = MaterialTheme.typography.titleSmall,
                    color = chrome.textHi,
                )
                Gap(6)
                val result = tested
                when {
                    testing -> Text(
                        "Checking on your PC...",
                        style = MaterialTheme.typography.bodyMedium,
                        color = chrome.textMid,
                    )
                    result != null -> result.lines.forEach {
                        Text(
                            it,
                            style = MaterialTheme.typography.bodyMedium,
                            color = if (result.ok) chrome.textHi else chrome.warnInk,
                        )
                        Gap(4)
                    }
                    strict.measureLast != null -> {
                        Text("Your last test:", style = MaterialTheme.typography.labelMedium, color = chrome.textMid)
                        Gap(4)
                        StrictVoice.measureLines(strict.measureLast).forEach {
                            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                            Gap(4)
                        }
                    }
                    else -> Text(
                        StrictVoice.MEASURE_INTRO,
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                    )
                }
                Gap(10)
                val canTest = strict.measure && status.gate.enrolled && !status.gate.needsRetraining
                Secondary(
                    text = if (tested != null || strict.measureLast != null) "Test again" else "Start the test",
                    enabled = canTest && !testing && !recordingAny,
                    modifier = Modifier.fillMaxWidth(),
                    onClick = onStartTest,
                )
                if (!strict.measure && answered) {
                    Gap(4)
                    Text(StrictVoice.NO_TEST_ON_THIS_PC, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                } else if (strict.measure && !status.gate.enrolled) {
                    Gap(4)
                    Text(
                        "Train your voice first - the test checks your sentences against it.",
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textMid,
                    )
                }
            }

            Plate {
                Text("Since your PC started", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
                Gap(6)
                val lines = StrictVoice.repeatLines(strict)
                if (lines.isEmpty()) {
                    Text(StrictVoice.REPEAT_NONE, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                } else {
                    lines.forEach {
                        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                        Gap(4)
                    }
                    Text(
                        "\"Again\" means your PC turned you away and then let you in within " +
                            "${strict.repeatWindowSeconds.toInt()} seconds. Kept in memory only.",
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textMid,
                    )
                }
                Gap(8)
                Quiet("Ask your PC again", onClick = onRefresh)
            }
    }
}

/** One setting: a choice per value, with what each does, and the PC's answer. */
@Composable
private fun SettingPlate(
    title: String,
    setting: String,
    choices: List<StrictVoice.Choice>,
    strict: VoiceStrict.View,
    busy: String?,
    note: String?,
    onPick: (String, String) -> Unit,
) {
    val chrome = LocalChrome.current
    // The memory setting while private answers are "voice check is enough":
    // both choices greyed out, with one note saying why.
    val open = StrictVoice.settingOpen(setting, strict)
    Plate {
        Text(title, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
        choices.forEach { c ->
            val onlyVeryStrict = setting == VoiceStrict.PRIVACY && c.value == VoiceStrict.VOICE_IS_ENOUGH &&
                !strict.isVeryStrict
            Gap(8)
            OptionChip(
                label = c.label,
                isSelected = StrictVoice.isCurrent(setting, c.value, strict),
                modifier = Modifier.fillMaxWidth(),
                enabled = busy == null && !onlyVeryStrict && open,
                onClick = { onPick(setting, c.value) },
            )
            Gap(4)
            Text(
                if (onlyVeryStrict) c.detail + " " + StrictVoice.PRIVACY_ONLY_VERY_STRICT else c.detail,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
            )
        }
        // Why the memory choices are greyed out, or that "Keep on screen"
        // for memories already covers sensitive saved facts.
        StrictVoice.plateNote(setting, strict)?.let {
            Gap(8)
            Text(
                it,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        }
        StrictVoice.waitingLine(setting, strict)?.let {
            Gap(8)
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
        }
        if (busy == setting) {
            Gap(8)
            Text("Asking your PC...", style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        note?.let {
            Gap(8)
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
        }
    }
}
