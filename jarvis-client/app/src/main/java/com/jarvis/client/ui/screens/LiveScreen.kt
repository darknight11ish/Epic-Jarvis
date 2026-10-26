package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.State
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.FaceState
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.data.LiveEnd
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.Face
import com.jarvis.client.face.FaceView
import com.jarvis.client.net.Provenance
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalRadii
import com.jarvis.client.voice.BargeIn
import com.jarvis.client.voice.LiveExtras
import com.jarvis.client.voice.LiveMicGate
import com.jarvis.client.voice.LiveRules
import com.jarvis.client.voice.VoiceSession
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Jarvis's own face on the Live screen, and the state it is in.
 *
 * Built by MainActivity from exactly the values Home hands `FaceView` - the
 * same `JarvisRuntime.face`/`faceOffline`/`faceFocusQuiet`/`faceSerious` and
 * the same microphone and speaker levels - so the two screens cannot drift
 * into two different faces. This is a holder for those values, never a second
 * face implementation: one source for the faces (docs/CRITTERS.md).
 *
 * App lock changes nothing here. The owner's decision of 2026-09-27 is that
 * neither face is hidden or blanked while locked, and that it shows the same
 * connectivity and listening state as always; [offline] is the same
 * `JarvisRuntime.faceOffline` Home reads, and `FaceShellRules` turns it into
 * the hollow ring and the words. Nothing in this file reads the lock.
 */
data class LiveFace(
    val state: FaceState,
    val face: Face,
    val bindings: Bindings,
    val offline: Boolean,
    val focusQuiet: Boolean,
    val serious: Boolean,
    /** Cards waiting: the still ring's marks, the same as Home's. */
    val notches: Int,
    val glow: Float,
    val calmMotion: Boolean,
    val stillAnimal: Boolean,
    val micLevel: State<Float>,
    val speechLevel: State<Float?>,
    val speechMouth: (FloatArray) -> Boolean,
)

/**
 * The face's share of the room below the status line, against the scrolling
 * remainder's 1: about three fifths of what is left, so it is clearly the
 * largest thing on the screen without pushing the talk button off a short one.
 */
private const val LIVE_FACE_WEIGHT = 1.6f

/**
 * The face, filling whatever the caller's [modifier] gives it.
 *
 * No tick ring and no tap-to-open-Brain here: Live is not Home, and a stray
 * tap on the face must not walk out of a live session. The face's own press
 * ring and petting still work, because FaceView answers its own touches.
 */
@Composable
private fun LiveFacePane(face: LiveFace, modifier: Modifier = Modifier) {
    val chrome = LocalChrome.current
    Box(
        modifier
            .padding(horizontal = 12.dp, vertical = 8.dp)
            .clip(LocalRadii.current.shellShape)
            .background(chrome.well),
        contentAlignment = Alignment.Center,
    ) {
        FaceView(
            state = face.state,
            notches = face.notches,
            face = face.face,
            bindings = face.bindings,
            offline = face.offline,
            focusQuiet = face.focusQuiet,
            serious = face.serious,
            glow = face.glow,
            calmMotion = face.calmMotion,
            stillMotion = face.stillAnimal,
            // Read from the frame loop, never in composition: the microphone
            // delivers about fifty levels a second (the same reason Home
            // passes lambdas).
            micLevel = { face.micLevel.value },
            speechLevel = { face.speechLevel.value },
            speechMouth = face.speechMouth,
            background = chrome.well,
            modifier = Modifier.fillMaxSize(),
        )
    }
}

/**
 * Jarvis Live on this phone (the owner's decision and answers of
 * 2026-09-28; docs/LIVE-DESIGN.md): a back-and-forth voice conversation the
 * owner starts and ends here. The sign is always on this screen, on Home and
 * in the notification while Live is on; the words are the PC's fixed ones
 * ([LiveRules.sign]).
 *
 * - Start (no card; held on a stale link; the PC refuses it until the
 *   owner's voice is trained - then a "Train my voice" button). End Live is
 *   never held, and never waits for another button's answer.
 * - Mic off closes the microphone; the session and its time carry on.
 * - "Heard you - thinking" at once when a sentence passed the voice check;
 *   "Didn't catch that - say a bit more" for a clip too short to check.
 * - JARVIS'S FACE IS THE SCREEN'S CENTRE OF GRAVITY (the owner, 2026-10-13:
 *   "when i start jarvis live, i dont see the face of jarvis, that is
 *   incredibly important and should be the largest part of my phone
 *   screen"). This screen drew no face at all before that. The face is the
 *   SAME `FaceView` Home draws, built from the same values MainActivity hands
 *   it ([LiveFace]) - one source for the faces, never a second implementation
 *   (docs/CRITTERS.md) - and it takes the larger share of the screen, with
 *   the sign, the captions and the buttons scrolling in what is left.
 * - This Live session's question and answer as captions (side talk shows
 *   "(not for Jarvis)"), and the tap buttons after a spoken question, which
 *   send those words as TYPED ones - answered on screen, keeping Live open.
 * - THERE IS NO TYPING BOX (the owner, 2026-10-13: "if im in jarvis live i
 *   probably dont need the type to jarvis typed answers stay on screen").
 *   Live is the face, the talk button and captions. The one way words that
 *   are not speech reach a Live turn is the "Shared text" chip below, handed
 *   over by "Talk about this in Live" in the Share sheet, which the owner
 *   taps Send on.
 * - A card of this session waiting: speech pauses and the microphone closes
 *   until it is decided - by tapping, on Home ("Show the card").
 * - Live on the PC: "Jarvis Live is on your PC" and "Move it here".
 * - The screen stays on while Live is on and this screen shows - never after
 *   it ends (the review's #1: it kept the phone awake and unlocked). The
 *   camera switch appears only when the PC says it is ready - it is off until
 *   the 12 GB graphics card is in and passes the photo test.
 * - The Live extras (the owner's decisions of 2026-09-28): which microphone
 *   it listens through (a Bluetooth headset's is preferred), what the
 *   headset button does, and text shared with "Talk about this in Live" -
 *   held here as a "Shared text" chip and sent, tagged "shared" (outside
 *   text), only when the owner taps Send.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun LiveScreen(
    onBack: () -> Unit,
    onOpenCards: () -> Unit,
    onTrainVoice: () -> Unit,
    /** Jarvis's own face, and the state it is in. Built by MainActivity. */
    face: LiveFace,
    /** Text shared with "Talk about this in Live", held until Send; or null. */
    shared: String? = null,
    onDropShared: () -> Unit = {},
    /** Checked when this card opens and on resume - a microphone can be auto-revoked (LM-3A). */
    onCheckPermission: () -> Unit = {},
    /** "[Allow microphone]": Android's own runtime ask; never starts Live on the grant. */
    onAskLiveMicrophone: () -> Unit = {},
    /** "[Open app permission settings]": the app's Android page, for a "don't ask again". */
    onOpenAppPermissionSettings: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val status by JarvisRuntime.liveStatus.collectAsState()
    val stale by JarvisRuntime.stale.collectAsState()
    val flash by JarvisRuntime.liveFlash.collectAsState()
    val move by JarvisRuntime.liveMove.collectAsState()
    val notice by JarvisRuntime.liveNoticeText.collectAsState()
    val micBlocked by JarvisRuntime.liveMicBlocked.collectAsState()
    val chips by JarvisRuntime.voice.liveChips.collectAsState()
    val phase by JarvisRuntime.voice.phase.collectAsState()
    val question by JarvisRuntime.chat.question.collectAsState()
    val reply by JarvisRuntime.chat.reply.collectAsState()
    val pending by JarvisRuntime.pending.collectAsState()
    val interrupt by JarvisRuntime.settings.interrupt.collectAsState()
    val security by JarvisRuntime.settings.security.collectAsState()
    val voiceStatus by JarvisRuntime.voice.status.collectAsState()
    val mic by JarvisRuntime.liveMic.collectAsState()
    // Temporary chat is on: a Live session is then not kept in History either
    // (the owner, 2026-09-29), so this screen says so - before it starts, too.
    val temporary by JarvisRuntime.chat.temporary.collectAsState()
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    // Ticks while a flash or an ended sign is up, so each goes away on time.
    var nowMs by remember { mutableLongStateOf(android.os.SystemClock.elapsedRealtime()) }

    LaunchedEffect(Unit) { JarvisRuntime.liveOpened() }
    // LM-3A: read the microphone FRESH each time this card opens (the owner may
    // have changed it in Android while the app was in the background).
    LaunchedEffect(Unit) { onCheckPermission() }
    LaunchedEffect(flash, status) {
        while (true) {
            nowMs = android.os.SystemClock.elapsedRealtime()
            val ended = (status?.get("state") as? kotlinx.serialization.json.JsonPrimitive)?.content == "ended"
            if (nowMs >= flash.until && !ended) break
            delay(if (nowMs < flash.until) 250 else 1000)
        }
    }
    // An old tap result does not stay for ever (the review's C8).
    LaunchedEffect(said) {
        if (said != null) {
            delay(10_000)
            said = null
        }
    }

    val on = LiveRules.onHere(status)
    // The screen stays on only while Live is on (the review's #1).
    val view = LocalView.current
    DisposableEffect(view, on) {
        view.keepScreenOn = on
        onDispose { view.keepScreenOn = false }
    }

    val flashing = nowMs < flash.until
    val cardHolds = remember(pending, status) { JarvisRuntime.liveCardHolds() }
    val sign = LiveRules.sign(
        status,
        stale = stale,
        thinking = flashing && flash.thinking,
        short = flashing && flash.short,
        cardShown = cardHolds,
        endedAgo = remember(status, nowMs) { JarvisRuntime.liveEndedAgo() },
    )
    val detail = sign.detail.ifEmpty {
        when {
            sign.stop.isEmpty() -> ""
            flashing && flash.trouble -> LiveRules.SEEN.getValue("trouble")
            flashing && flash.sideTalk -> LiveRules.SEEN.getValue("not_for_me")
            else -> ""
        }
    }
    fun act(block: suspend () -> String?) {
        if (busy) return
        busy = true
        scope.launch {
            said = block()
            busy = false
        }
    }

    Column(modifier.fillMaxSize().background(chrome.surface0).navigationBarsPadding().imePadding()) {
        TopBar(LiveRules.TITLE, onBack = onBack, subtitle = "Talk back and forth - no \"Hey Jarvis\" needed")
        // The face first, and the larger share of everything below the status
        // line: the sign, the captions and the buttons scroll in what is left.
        // Weighted rather than a fixed size, so a tall phone gives it more room
        // and a short one still keeps a whole face; FaceView draws from its
        // smaller side, so the box stays round.
        LiveFacePane(
            face = face,
            modifier = Modifier.fillMaxWidth().weight(LIVE_FACE_WEIGHT),
        )
        Column(
            Modifier.fillMaxWidth().weight(1f).verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Plate {
                Text(
                    if (sign.show) sign.title else LiveRules.TITLE,
                    style = MaterialTheme.typography.titleMedium,
                    color = chrome.textHi,
                )
                if (detail.isNotEmpty()) {
                    Gap(4)
                    // Said by TalkBack when it changes (the review's C11).
                    Text(
                        detail,
                        style = MaterialTheme.typography.bodyMedium,
                        color = chrome.textMid,
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                    )
                }
                if (on && detail.isEmpty()) {
                    Gap(4)
                    Text(
                        LiveRules.SEEN.getValue("end_hint"),
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                    )
                }
                if (temporary) {
                    Gap(4)
                    // Said by TalkBack when it appears, like the sign's detail.
                    Text(
                        LiveRules.SEEN.getValue("temporary_on"),
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textHi,
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                    )
                }
                Gap(12)
                if (sign.move || move.isNotEmpty()) {
                    // Live is on the PC: say so, and one tap moves it here -
                    // the same chat carries on here: the PC's status names
                    // the session's chat, and Home takes it over (the review's
                    // C3; the chat audit, 2026-09-28, which found the phone
                    // carrying on whatever chat Home was in instead).
                    if (!sign.move) {
                        Text(LiveRules.moveWords(move), style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                        Gap(8)
                    }
                    Primary(
                        "Move it here",
                        modifier = Modifier.fillMaxWidth(),
                        busy = busy,
                        onClick = { act { JarvisRuntime.liveStart(move = true); null } },
                    )
                } else if (!on) {
                    // LM-3A: no microphone, no start - the sentence and the
                    // two honest routes are drawn before the Start button.
                    micBlocked?.let { blocked ->
                        Gap(6)
                        Text(
                            blocked.banner,
                            style = MaterialTheme.typography.bodyMedium,
                            color = chrome.textHi,
                            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                        )
                        Gap(8)
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            if (blocked.offerAllow) {
                                Primary(LiveMicGate.ALLOW, onClick = onAskLiveMicrophone)
                            }
                            if (blocked.offerSettings) {
                                Secondary(LiveMicGate.OPEN_SETTINGS, onClick = onOpenAppPermissionSettings)
                            }
                        }
                        Gap(10)
                    }
                    Primary(
                        if (sign.resume) "Resume Live" else "Start Jarvis Live",
                        modifier = Modifier.fillMaxWidth(),
                        busy = busy,
                        onClick = { act { JarvisRuntime.liveStart(resume = sign.resume); null } },
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
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        // End Live never waits for another button (the
                        // review's B2), and ends here at once.
                        Primary(sign.stop, onClick = { JarvisRuntime.liveEndNow("owner") })
                        Secondary(sign.mute, onClick = {
                            act { JarvisRuntime.liveMute(sign.mute == LiveRules.MIC_OFF) }
                        })
                        if (sign.carryOn) {
                            Secondary("Carry on", onClick = { act { JarvisRuntime.liveCarryOn() } })
                        }
                        if (phase == VoiceSession.Phase.SPEAKING && interrupt != LiveRules.INTERRUPT_OFF) {
                            Secondary(LiveRules.STOP_TALKING, onClick = { JarvisRuntime.voice.stopSpeaking() })
                        }
                        if (sign.moreTime) {
                            Quiet(LiveRules.MORE_TIME, onClick = { act { JarvisRuntime.liveExtend(20) } })
                        }
                    }
                    if (sign.showCard) {
                        Gap(8)
                        Secondary("Show the card", onClick = onOpenCards)
                    }
                }
                notice?.let { n ->
                    Gap(8)
                    Text(n.text, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                    if (n.needsVoice) {
                        Gap(6)
                        Secondary("Train my voice", modifier = Modifier.fillMaxWidth(), onClick = onTrainVoice)
                    }
                }
                said?.let {
                    Gap(8)
                    Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                }
            }

            // This session's question and answer, as captions. Side talk is
            // never spoken, and shown as "(not for Jarvis)". Nothing from the
            // chat before Live started (a new Live session is a new chat).
            if (on) {
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
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            chips.forEach { chip ->
                                Secondary(chip, onClick = { JarvisRuntime.liveTap(chip) })
                            }
                        }
                    }
                }
            }

            // Text shared with "Talk about this in Live" (the owner's decision
            // of 2026-09-28; the Share sheet). It waits here as a chip and goes
            // to Jarvis only when the owner taps Send, tagged "shared" (outside
            // text, so the PC treats the chat as having read it).
            //
            // This is now the ONE way words that are not speech reach a Live
            // turn: the typing box that used to sit here was removed on the
            // owner's answer of 2026-10-13 ("if im in jarvis live i probably
            // dont need the type to jarvis typed answers stay on screen").
            // `liveType("")` with text held is the same call the box made.
            if (shared != null) {
                Plate {
                    Text(
                        Provenance.sharedLine(shared),
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textHi,
                    )
                    Gap(4)
                    Text(
                        "Shared from another app: outside text. It goes to Jarvis when you tap " +
                            "Send, then you can talk about it.",
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textMid,
                    )
                    Gap(6)
                    Secondary("Send", enabled = on, onClick = {
                        JarvisRuntime.liveType("", shared)
                        onDropShared()
                    })
                    Gap(6)
                    Quiet("Remove", onClick = onDropShared)
                }
            }

            // What the owner should know while Live is on: which microphone is
            // in use, App lock ends it (the review's #3), and interrupting by
            // voice needs an echo canceller on this phone and the PC's voice
            // check. The long headset-button explanation that used to open this
            // plate was removed on the owner's request of 2026-10-26 ("get rid
            // of the long explanation on jarvis live"): the button still does
            // the same things, it is just not explained on screen any more.
            if (on) {
                val notes = buildList {
                    mic?.let { add(it) }
                    if (security.appLock) {
                        add(
                            if (security.liveEnd == LiveEnd.SCREEN_LOCK) {
                                "App lock is on: Live ends when the phone's screen locks (\"End Live " +
                                    "when\" in Security)."
                            } else {
                                "App lock is on: Live ends when App lock would lock Jarvis again " +
                                    "(\"Lock again after\" in Security)."
                            },
                        )
                    }
                    if (interrupt == LiveRules.INTERRUPT_VOICE && !JarvisRuntime.settings.echoCanceller) {
                        add(BargeIn.describe(true, echoCancellerAvailable = false) + " Or use Stop talking.")
                    }
                    if (interrupt == LiveRules.INTERRUPT_VOICE && !voiceStatus.flow.bargeInUsable) {
                        add(
                            "Interrupting by voice is off on your PC right now, so talking over Jarvis does " +
                                "not stop it - use Stop talking.",
                        )
                    }
                }
                if (notes.isNotEmpty()) {
                    Plate {
                        notes.forEachIndexed { i, line ->
                            if (i > 0) Gap(6)
                            Text(line, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                        }
                    }
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
