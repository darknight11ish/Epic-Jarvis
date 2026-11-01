package com.jarvis.client.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.material3.Icon
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.client.FaceState
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.R
import com.jarvis.client.data.PipLayout
import com.jarvis.client.data.PipText
import com.jarvis.client.data.PipWords
import com.jarvis.client.face.FaceView
import com.jarvis.client.net.ChatHistory
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
 * WHAT IT MAY SHOW, in the design's own list (§4): the face, and - in Jarvis
 * Live - its status line and two ICON controls (end, mute). It draws NO answer
 * text and NO state word in the normal window (the owner's revision of
 * 2026-10-31: "just keep the model there without the wording", after seeing the
 * face squeezed beside "Standing by" and a cut-off sentence), and nothing else.
 * No approval's title, body, plan, recipients, search words or file names; no
 * card; no setting; no pairing token, server address or key. Nothing here
 * approves, denies, sends or forgets anything: the window's only system action
 * is [PipWords.EXPAND], and a card still waits for the owner in Jarvis, with the
 * existing notification unchanged (§5). The conversation source is
 * [ChatHistory.Exchange] - chat text only - so there is no field here a card
 * could ride in on.
 *
 * While "Hide memory lists and chat history" or App lock hides content, the
 * layout is [PipLayout.HIDDEN] and this draws a dimmed neutral face and the
 * owner's own sentence, [PipWords.LOCKED] - never the answer, never the
 * conversation (§4, §9.1). That half is untouched by the 2026-10-31 revision.
 *
 * The face is the SAME [FaceView] the app already draws, now filling the
 * window - never a second face implementation - built from the same [LiveFace]
 * holder `MainActivity` already hands the Live screen, so the two cannot drift
 * (docs/CRITTERS.md). Whether the shader-heavy face holds its frame budget in a
 * PiP window is UNMEASURED (`docs/PIP-DESIGN.md` §8): it is not claimed here.
 */
@Composable
internal fun PipWindow(
    layout: PipLayout,
    face: LiveFace,
    /** The current answer so far ([com.jarvis.client.net.ChatSession.reply]).
     *  No layout draws it any more (2026-10-31) - kept in the signature so the
     *  caller stays one shape and the thread layout can keep its own source. */
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
            // Mode 1: the model only, filling the window. No state word, no
            // answer line (2026-10-31, the owner's own request).
            PipLayout.FACE -> PipFaceOnly(face)
            // Mode 3 with no Live session: face-first, with its ONE fixed
            // short line - no answer text and no invented words.
            PipLayout.LIVE_OFF -> PipFaceLine(face, PipWords.LIVE_OFF)
            PipLayout.THREAD -> PipThread(thread)
            PipLayout.LIVE -> PipLive(face)
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

/** Mode 1: the model only, filling the window - no wording at all. */
@Composable
private fun PipFaceOnly(face: LiveFace) {
    Box(Modifier.fillMaxSize()) {
        PipFace(face)
    }
}

/** Mode 3's fallback: the face, with one short fixed line at the bottom. */
@Composable
private fun PipFaceLine(face: LiveFace, line: String) {
    val chrome = LocalChrome.current
    Box(Modifier.fillMaxSize()) {
        PipFace(face)
        Box(
            Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .background(chrome.well.copy(alpha = OVERLAY_ALPHA))
                .padding(horizontal = 8.dp, vertical = 3.dp),
            contentAlignment = Alignment.Center,
        ) {
            PipLine(line, chrome.textMid, maxLines = 1)
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

/**
 * Mode 3: Live at its smallest useful size. The face fills the window; the
 * status line and the two controls sit in one small overlay along the bottom.
 *
 * The controls are ICONS since 2026-10-31 (the owner's revision): "End Live"
 * and "Mic off"/"Mic on" were text links beside a shrunken face, and he asked
 * for the model to take most of the window with icons instead. They call the
 * same two runtime doors the text buttons called, and each carries its words as
 * its `contentDescription`, so a screen reader still says exactly what the old
 * buttons said.
 */
@Composable
private fun PipLive(face: LiveFace) {
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
    val micIsOff = sign.mute == LiveRules.MIC_OFF
    Box(Modifier.fillMaxSize()) {
        PipFace(face)
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .background(chrome.well.copy(alpha = OVERLAY_ALPHA))
                .padding(horizontal = 8.dp, vertical = 3.dp),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            PipLine(
                when {
                    !on -> PipWords.LIVE_ON_PC
                    sign.title.isNotEmpty() -> sign.title
                    else -> PipWords.LIVE_LISTENING
                },
                chrome.textHi,
                maxLines = 1,
            )
            if (on) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(18.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    // End Live never waits for another button's answer - the
                    // same call the Live screen makes.
                    PipControlIcon(
                        drawable = R.drawable.ic_pip_end_live,
                        description = sign.stop,
                        onClick = { JarvisRuntime.liveEndNow("owner") },
                    )
                    PipControlIcon(
                        drawable = if (micIsOff) R.drawable.ic_pip_mic_on
                        else R.drawable.ic_pip_mic_off,
                        description = sign.mute,
                        onClick = {
                            scope.launch { JarvisRuntime.liveMute(micIsOff) }
                        },
                    )
                }
            }
        }
    }
}

/** One icon control: a real tappable target, and its words for a screen reader. */
@Composable
private fun PipControlIcon(drawable: Int, description: String, onClick: () -> Unit) {
    val chrome = LocalChrome.current
    Icon(
        painter = painterResource(drawable),
        contentDescription = description,
        tint = chrome.textHi,
        modifier = Modifier
            .size(34.dp)
            .clickable(onClick = onClick)
            .padding(5.dp),
    )
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
private fun PipLine(
    text: String,
    color: Color,
    maxLines: Int = 2,
) {
    Text(
        text,
        style = MaterialTheme.typography.labelSmall,
        fontSize = 10.sp,
        color = color,
        maxLines = maxLines,
        overflow = TextOverflow.Ellipsis,
    )
}

/** The hidden layout's dimming: dimmed, not invisible - it still says why. */
private const val DIM_ALPHA = 0.45f

/** A light wash behind the one allowed line / the two icons, so both stay readable. */
private const val OVERLAY_ALPHA = 0.72f
