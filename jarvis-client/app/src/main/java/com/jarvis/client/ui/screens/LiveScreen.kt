package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.voice.LiveRules
import com.jarvis.client.voice.VoiceSession
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Jarvis Live on this phone (the owner's decision and answers of
 * 2026-09-28; docs/LIVE-DESIGN.md): a back-and-forth voice conversation the
 * owner starts and ends here. The sign is always on this screen and in the
 * notification while Live is on; the words are the PC's fixed ones
 * ([LiveRules.sign]).
 *
 * - Start (no card; held on a stale link; the PC refuses it until the
 *   owner's voice is trained). End is never held.
 * - Mute closes the microphone; the session and its time carry on.
 * - "Heard you - thinking" at once when a sentence passed the voice check;
 *   "Didn't catch that - say a bit more" for a clip too short to check.
 * - The last question and answer as captions (side talk shows "(not for
 *   Jarvis)"), the tap buttons after a spoken question (sent as TYPED words),
 *   and a text box: typed questions get typed answers, on screen.
 * - A card waiting: speech pauses and the microphone closes until it is
 *   decided - by tapping, on Home ("Show the card").
 * - The screen stays on while this screen shows. The camera switch appears
 *   only when the PC says it is ready - it is off until the 12 GB graphics
 *   card is in and passes the photo test.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun LiveScreen(
    onBack: () -> Unit,
    onOpenCards: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val status by JarvisRuntime.liveStatus.collectAsState()
    val stale by JarvisRuntime.stale.collectAsState()
    val flash by JarvisRuntime.liveFlash.collectAsState()
    val move by JarvisRuntime.liveMove.collectAsState()
    val notice by JarvisRuntime.liveNoticeText.collectAsState()
    val chips by JarvisRuntime.voice.liveChips.collectAsState()
    val phase by JarvisRuntime.voice.phase.collectAsState()
    val question by JarvisRuntime.chat.question.collectAsState()
    val reply by JarvisRuntime.chat.reply.collectAsState()
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    var typed by rememberSaveable { mutableStateOf("") }
    // Ticks while a "Heard you" flash is up, so it goes away on time.
    var nowMs by remember { mutableLongStateOf(android.os.SystemClock.elapsedRealtime()) }

    LaunchedEffect(Unit) { JarvisRuntime.liveOpened() }
    LaunchedEffect(flash) {
        while (android.os.SystemClock.elapsedRealtime() < flash.until) {
            nowMs = android.os.SystemClock.elapsedRealtime()
            delay(250)
        }
        nowMs = android.os.SystemClock.elapsedRealtime()
    }
    // The screen stays on while Live's screen shows (C11 of the voice review).
    val view = LocalView.current
    DisposableEffect(view) {
        view.keepScreenOn = true
        onDispose { view.keepScreenOn = false }
    }

    val on = LiveRules.onHere(status)
    val flashing = nowMs < flash.until
    val sign = LiveRules.sign(status, stale = stale, thinking = flashing && flash.thinking, short = flashing && flash.short)
    val cardPause = (status?.get("paused") as? kotlinx.serialization.json.JsonPrimitive)?.content in LiveRules.CARD_PAUSES
    fun act(block: suspend () -> String?) {
        if (busy) return
        busy = true
        scope.launch {
            said = block()
            busy = false
        }
    }

    Column(modifier.fillMaxSize().background(chrome.surface0).navigationBarsPadding()) {
        TopBar(LiveRules.TITLE, onBack = onBack, subtitle = "Talk back and forth - no wake word")
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Plate {
                Text(
                    if (sign.show) sign.title else LiveRules.TITLE,
                    style = MaterialTheme.typography.titleMedium,
                    color = chrome.textHi,
                )
                if (sign.detail.isNotEmpty()) {
                    Gap(4)
                    Text(sign.detail, style = MaterialTheme.typography.bodyMedium, color = chrome.textMid)
                }
                if (on && sign.detail.isEmpty()) {
                    Gap(4)
                    Text(
                        LiveRules.SEEN.getValue("end_hint"),
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                    )
                }
                Gap(12)
                if (!on) {
                    Primary(
                        if (sign.resume) "Resume Live" else "Start Jarvis Live",
                        modifier = Modifier.fillMaxWidth(),
                        busy = busy,
                        onClick = { act { JarvisRuntime.liveStart() } },
                    )
                    Gap(6)
                    Text(
                        "Jarvis listens after every answer until you end it, say \"Okay Jarvis, " +
                            "that's all for now\", or it has been quiet for 90 seconds. Every sentence " +
                            "is checked for your voice on your PC before any words are made of it.",
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textMid,
                    )
                } else {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Primary(sign.stop, onClick = { act { JarvisRuntime.liveStop("owner") } })
                        Secondary(sign.mute, onClick = {
                            act { JarvisRuntime.liveMute(sign.mute == "Mute") }
                        })
                        if (sign.carryOn) {
                            Secondary("Carry on", onClick = { act { JarvisRuntime.liveCarryOn() } })
                        }
                        if (phase == VoiceSession.Phase.SPEAKING) {
                            Secondary(LiveRules.STOP_TALKING, onClick = { JarvisRuntime.voice.stopSpeaking() })
                        }
                        Quiet("20 more minutes", onClick = { act { JarvisRuntime.liveExtend(20) } })
                    }
                    if (cardPause) {
                        Gap(8)
                        Secondary("Show the card", onClick = onOpenCards)
                    }
                }
                if (move.isNotEmpty()) {
                    Gap(8)
                    Secondary(
                        LiveRules.SEEN.getValue("move").replace("{device}", move),
                        modifier = Modifier.fillMaxWidth(),
                        onClick = { act { JarvisRuntime.liveStart() } },
                    )
                }
                (said ?: notice)?.let {
                    Gap(8)
                    Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                }
            }

            // The last question and answer, as captions. Side talk is never
            // spoken, and shown as "(not for Jarvis)".
            if (on || !question.isNullOrBlank()) {
                Plate {
                    question?.takeIf { it.isNotBlank() }?.let {
                        Text(it, style = MaterialTheme.typography.bodyMedium, color = chrome.textMid)
                        Gap(6)
                    }
                    val shown = when {
                        LiveRules.isSideTalk(reply) -> LiveRules.SEEN.getValue("not_for_me")
                        LiveRules.couldBeSideTalk(reply) -> ""
                        else -> reply
                    }
                    if (shown.isNotBlank()) {
                        Text(shown, style = MaterialTheme.typography.bodyLarge, color = chrome.textHi)
                    }
                    if (chips.isNotEmpty()) {
                        Gap(8)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            chips.forEach { chip ->
                                Secondary(chip, onClick = { JarvisRuntime.liveTap(chip) })
                            }
                        }
                    }
                }
            }

            // Typing in Live: a typed question, answered on screen.
            if (on) {
                Plate {
                    TextInput(
                        value = typed,
                        onValueChange = { typed = it },
                        modifier = Modifier.fillMaxWidth(),
                        placeholder = "Type to Jarvis - typed answers stay on screen",
                        singleLine = false,
                        maxLines = 4,
                    )
                    Gap(6)
                    Secondary("Send", enabled = typed.isNotBlank(), onClick = {
                        JarvisRuntime.liveType(typed)
                        typed = ""
                    })
                }
            }

            // The camera: only when the PC says it is ready, which it will
            // not be until the 12 GB graphics card is in and passes the photo
            // test (the owner's answer of 2026-09-28). Nothing is shown before.
            if (LiveRules.cameraShown(status)) {
                Plate {
                    Text(
                        "The camera is ready on your PC. Showing it to Jarvis from this phone comes " +
                            "in a later update.",
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                    )
                }
            }
            Gap(24)
        }
    }
}
