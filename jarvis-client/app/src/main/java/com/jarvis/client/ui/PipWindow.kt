package com.jarvis.client.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.client.FaceState
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.data.PipLayout
import com.jarvis.client.data.PipText
import com.jarvis.client.data.PipWords
import com.jarvis.client.face.FaceView
import com.jarvis.client.net.ChatHistory
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.screens.LiveFace
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.voice.LiveRules
import kotlinx.coroutines.launch

/**
 * The small Jarvis window, drawn INSIDE the activity while Android shows it in
 * picture-in-picture (`docs/PIP-DESIGN.md` §3).
 *
 * Android mirrors whatever the activity is showing into the window, so doing
 * nothing would put a shrunken Settings screen - or a shrunken History list -
 * into it. That is why `MainActivity` draws THIS instead of the current screen
 * while `isInPictureInPictureMode` is true: a layout of its own, fed by the
 * same [JarvisRuntime] flows the full screens already use, with the layout
 * chosen purely by `PipLayout.fromState` so the privacy rule is one function
 * and not a condition sprinkled through the drawing code.
 *
 * WHAT IT MAY SHOW, in the design's own list (§4): the face, ONE state word, the
 * first line of the current answer, the last few chat messages, or Live's
 * own controls - and NOTHING ELSE. No approval's title, body, plan, recipients,
 * search words or file names; no card; no setting; no pairing token, server
 * address or key. Nothing here approves, denies, sends or forgets anything: the
 * window's only system action is [PipWords.EXPAND], and a card still waits for
 * the owner in Jarvis, with the existing notification unchanged (§5). The
 * conversation source is [ChatHistory.Exchange] - chat text only - so there is
 * no field here a card could ride in on.
 *
 * While "Hide memory lists and chat history" or App lock hides content, the
 * layout is [PipLayout.HIDDEN] and this draws a dimmed neutral face and the
 * owner's own sentence, [PipWords.LOCKED] - never the answer, never the
 * conversation (§4, §9.1).
 *
 * The face is the SAME [FaceView] the app already draws, at a smaller size -
 * never a second face implementation - built from the same [LiveFace] holder
 * `MainActivity` already hands the Live screen, so the two cannot drift
 * (docs/CRITTERS.md). Whether the shader-heavy face holds its frame budget in a
 * PiP window is UNMEASURED (`docs/PIP-DESIGN.md` §8): it is not claimed here.
 */
@Composable
internal fun PipWindow(
    layout: PipLayout,
    face: LiveFace,
    /** The current answer so far ([com.jarvis.client.net.ChatSession.reply]). */
    answer: String,
    /** What the conversation shows ([com.jarvis.client.net.ChatSession.thread]). */
    thread: List<ChatHistory.Exchange>,
) {
    val chrome = LocalChrome.current
    Box(
        Modifier
            .fillMaxSize()
            .background(chrome.well),
        contentAlignment = Alignment.Center,
    ) {
        when (layout) {
            // The setting is Off: no window exists. Drawn only if Android keeps
            // one up while the owner changes the setting, so it says the truth
            // rather than a blank rectangle.
            PipLayout.OFF -> PipLine(PipWords.STANDING_BY, chrome.textLo)
            PipLayout.HIDDEN -> PipHidden(face)
            PipLayout.FACE -> PipAnswer(face, answer, extra = null)
            PipLayout.LIVE_OFF -> PipAnswer(face, answer, extra = PipWords.LIVE_OFF)
            PipLayout.THREAD -> PipThread(thread)
            PipLayout.LIVE -> PipLive()
        }
    }
}

/** A dimmed, neutral face and the owner's own "why is it empty" sentence. */
@Composable
private fun PipHidden(face: LiveFace) {
    val chrome = LocalChrome.current
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
        modifier = Modifier.fillMaxSize().padding(horizontal = 10.dp, vertical = 6.dp),
    ) {
        Box(Modifier.size(72.dp).alpha(DIM_ALPHA)) {
            PipFace(face, state = FaceState.STANDBY)
        }
        PipLine(PipWords.LOCKED, chrome.textMid)
    }
}

/**
 * Mode 1, and mode 3's fallback: the face, the state word and one answer line.
 * [extra] is the "Live is off." line, drawn ABOVE the answer slot (§2.4).
 */
@Composable
private fun PipAnswer(face: LiveFace, answer: String, extra: String?) {
    val chrome = LocalChrome.current
    val line = PipText.firstLine(answer)
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.fillMaxSize().padding(horizontal = 10.dp, vertical = 6.dp),
    ) {
        Box(Modifier.size(64.dp)) { PipFace(face) }
        Column(
            Modifier.padding(start = 10.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            PipLine(PipWords.state(face.state, face.offline, stale = false, approval = face.state == FaceState.APPROVAL), chrome.textHi)
            if (extra != null) PipLine(extra, chrome.textMid)
            if (line.isNotEmpty()) {
                Text(
                    line,
                    fontSize = 11.sp,
                    color = chrome.textHi,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

/** Mode 2: the last few messages, newest at the bottom, scrollable. */
@Composable
private fun PipThread(thread: List<ChatHistory.Exchange>) {
    val chrome = LocalChrome.current
    val rows = remember(thread) { PipText.threadRows(thread) }
    val scroll = rememberScrollState()
    // Scrolled to the bottom when it opens, and when a new message lands - the
    // newest is the one the owner is waiting for (§2.3). No input box and no
    // action: the window scrolls, and that is the only thing a touch can do.
    LaunchedEffect(rows.size) { scroll.scrollTo(scroll.maxValue) }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(scroll)
            .padding(horizontal = 10.dp, vertical = 6.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        if (rows.isEmpty()) {
            PipLine("Nothing here yet.", chrome.textLo)
            return@Column
        }
        for (row in rows) {
            Text(
                row.text,
                fontSize = 10.sp,
                color = if (row.fromOwner) chrome.textMid else chrome.textHi,
                textAlign = if (row.fromOwner) TextAlign.End else TextAlign.Start,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

/** Mode 3: Live at its smallest useful size - is it listening, and mute/end. */
@Composable
private fun PipLive() {
    val chrome = LocalChrome.current
    val status by JarvisRuntime.liveStatus.collectAsState()
    val stale by JarvisRuntime.stale.collectAsState()
    val on = LiveRules.onHere(status)
    val sign = remember(status, stale) {
        LiveRules.sign(
            status,
            stale = stale,
            thinking = false,
            short = false,
            cardShown = JarvisRuntime.liveCardHolds(),
            endedAgo = JarvisRuntime.liveEndedAgo(),
        )
    }
    // `liveMute` asks the PC, so it is a suspend call: the small window needs
    // its own scope rather than blocking the one frame it is drawing.
    val scope = rememberCoroutineScope()
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
        modifier = Modifier.fillMaxSize().padding(horizontal = 10.dp, vertical = 6.dp),
    ) {
        PipLine(
            when {
                !on -> PipWords.LIVE_ON_PC
                sign.title.isNotEmpty() -> sign.title
                else -> PipWords.LIVE_LISTENING
            },
            chrome.textHi,
        )
        if (on) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                modifier = Modifier.padding(top = 8.dp),
            ) {
                // End Live never waits for another button's answer - the same
                // call the Live screen makes.
                Quiet(sign.stop, onClick = { JarvisRuntime.liveEndNow("owner") })
                Quiet(sign.mute, onClick = {
                    scope.launch { JarvisRuntime.liveMute(sign.mute == LiveRules.MIC_OFF) }
                })
            }
        }
    }
}

/** The app's ONE face, at PiP size, from the same holder the Live screen uses. */
@Composable
private fun PipFace(face: LiveFace, state: FaceState = face.state) {
    val chrome = LocalChrome.current
    FaceView(
        state = state,
        notches = face.notches,
        face = face.face,
        bindings = face.bindings,
        offline = face.offline,
        focusQuiet = face.focusQuiet,
        serious = face.serious,
        glow = face.glow,
        calmMotion = face.calmMotion,
        stillMotion = face.stillAnimal,
        // Read from the frame loop, never in composition - the same reason
        // LiveScreen passes lambdas.
        micLevel = { face.micLevel.value },
        speechLevel = { face.speechLevel.value },
        speechMouth = face.speechMouth,
        background = chrome.well,
        modifier = Modifier.fillMaxSize(),
    )
}

@Composable
private fun PipLine(text: String, color: androidx.compose.ui.graphics.Color) {
    Text(
        text,
        style = MaterialTheme.typography.labelSmall,
        fontSize = 10.sp,
        color = color,
        maxLines = 2,
        overflow = TextOverflow.Ellipsis,
    )
}

/** The hidden layout's dimming: dimmed, not invisible - it still says why. */
private const val DIM_ALPHA = 0.45f
