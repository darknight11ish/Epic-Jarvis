package com.jarvis.client.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.jarvis.client.Activity
import com.jarvis.client.FaceState
import com.jarvis.client.LinkState
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.Face
import com.jarvis.client.face.FaceView
import com.jarvis.client.net.Attention
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.StatusInfo
import com.jarvis.client.ui.approval.ApprovalCard
import com.jarvis.client.ui.parts.Dot
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.VoiceButton
import com.jarvis.client.ui.parts.VoiceStrip
import com.jarvis.client.voice.VoiceSession
import androidx.compose.runtime.State
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalMotion
import com.jarvis.client.ui.theme.LocalRadii

@Immutable
data class HomeState(
    val link: LinkState,
    val linkDetail: String?,
    val stale: Boolean,
    val activity: Activity,
    val faceState: FaceState,
    val power: String,
    val status: StatusInfo?,
    val pending: List<PendingItem>,
    val attention: Attention,
    val notice: String?,
    val streaming: Boolean,
    val draft: String,
    val face: Face,
    val bindings: Bindings,
    /** OFF unless a voice turn is in flight. */
    val voicePhase: VoiceSession.Phase,
    /**
     * Whether to show the microphone at all.
     *
     * False hides it rather than showing one that posts audio into a 404 —
     * §2's rule is that a capability reporting false means hide the UI for it.
     */
    val voiceOffered: Boolean,
    /** What the desktop heard, so a mis-hearing is visible rather than silent. */
    val transcript: String?,
    val voiceNotice: String?,
    /**
     * The desktop is running without its approval gate.
     *
     * Said out loud rather than shown as an empty list: "nothing is waiting for
     * you" and "nothing can wait for you, because nothing is asking" are
     * opposite facts that look identical.
     */
    val approvalsOff: Boolean,
)

@Immutable
data class HomeActions(
    val onDraftChange: (String) -> Unit,
    val onSend: () -> Unit,
    val onInterrupt: () -> Unit,
    val onApprove: (PendingItem) -> Unit,
    val onDeny: (PendingItem) -> Unit,
    val onReconnect: () -> Unit,
    val onDismissNotice: () -> Unit,
    val onOpenChecks: () -> Unit,
    val onOpenInbox: () -> Unit,
    val onOpenBrain: () -> Unit,
    val onOpenAppearance: () -> Unit,
    val blockerFor: (PendingItem) -> String?,
    val onVoiceBegin: () -> Unit,
    val onVoiceRelease: () -> Unit,
    val onVoiceCancel: () -> Unit,
    val onDismissVoiceNotice: () -> Unit,
)

@Composable
fun HomeScreen(
    state: HomeState,
    actions: HomeActions,
    /**
     * The streamed reply, read as a lambda rather than passed as a value.
     *
     * Every token used to rebuild HomeState, which recomposed the link bar, the
     * whole list and the composer while the face was drawing at 60fps on the
     * same thread. Reading it inside the one composable that draws it keeps a
     * streaming reply from touching anything else.
     */
    reply: () -> String,
    /** Read in the draw phase only — see VoiceButton. */
    micLevel: State<Float>,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    Column(
        modifier
            .fillMaxSize()
            .background(chrome.surface0)
            .navigationBarsPadding()
            .imePadding(),
    ) {
        LinkBar(state, actions)

        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item(key = "face") {
                FaceBlock(state, actions)
            }

            if (state.notice != null) {
                item(key = "notice") { Notice(state.notice, actions.onDismissNotice) }
            }

            if (state.approvalsOff) {
                item(key = "approvals-off") {
                    Plate(outline = chrome.warnInk.copy(alpha = 0.35f)) {
                        Kicker("Approvals are off", color = chrome.warnInk)
                        Gap(6)
                        Text(
                            "The desktop is running without its permission gate, so nothing " +
                                "will ever arrive here to approve.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = chrome.textMid,
                        )
                    }
                }
            }

            if (state.pending.isNotEmpty()) {
                item(key = "approvals-label") {
                    Kicker(
                        if (state.pending.size == 1) "Waiting on you" else "${state.pending.size} waiting on you",
                        color = chrome.warnInk,
                    )
                }
                items(state.pending, key = { it.id }) { item ->
                    ApprovalCard(
                        item = item,
                        blocker = actions.blockerFor(item),
                        onApprove = { actions.onApprove(item) },
                        onDeny = { actions.onDeny(item) },
                    )
                }
            }

            item(key = "reply") { Reply(reply, state.streaming) }
        }

        Composer(state, actions, micLevel)
    }
}

/**
 * The face, with a radial lift behind it.
 *
 * The lift is a cached bitmap, not a per-frame Brush — see FaceView. Tapping it
 * opens the brain: the face is the only thing on screen that is obviously
 * *Jarvis*, so it is the right door to what Jarvis is doing.
 */
@Composable
private fun FaceBlock(state: HomeState, actions: HomeActions) {
    val chrome = LocalChrome.current
    Box(
        Modifier
            .fillMaxWidth()
            .aspectRatio(1.15f)
            .clip(LocalRadii.current.shellShape)
            .pressable(onClick = actions.onOpenBrain),
        contentAlignment = Alignment.Center,
    ) {
        FaceView(
            state = state.faceState,
            face = state.face,
            bindings = state.bindings,
            notches = state.attention.pending,
            modifier = Modifier.size(260.dp),
        )
        Column(
            Modifier.align(Alignment.BottomCenter).padding(bottom = 4.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            // The lane, which the phone parsed and threw away. "This left your
            // machine" is the single most consequential fact the UI carries and
            // it had no representation here at all.
            LaneChip(state.status)
            Gap(6)
            Text(
                "State of mind →",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
        }
    }
}

@Composable
private fun LaneChip(status: StatusInfo?) {
    val chrome = LocalChrome.current
    val lane = status?.lane?.lowercase()
    val model = status?.model
    when (lane) {
        // violet-4 is the desktop's `--cloud`, and it means the same thing on
        // both: this is leaving the local lane.
        "cloud" -> Pill("Cloud" + (model?.let { " · $it" } ?: ""), color = com.jarvis.client.face.Palette.VIOLET_4)
        "offline" -> Pill("Offline", color = chrome.badInk)
        "local" -> Pill("Local" + (model?.let { " · $it" } ?: ""), color = chrome.okInk)
        else -> if (model != null) Pill(model, color = chrome.textMid)
    }
}

@Composable
private fun LinkBar(state: HomeState, actions: HomeActions) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current

    // Two different facts, never merged into one word: whether the stream is up,
    // and whether Jarvis is busy. Collapsing them is how a client ends up
    // showing "thinking" at a desktop that went away ten minutes ago.
    val (dot, label) = when {
        state.link != LinkState.CONNECTED -> chrome.badMark to (state.linkDetail ?: "Offline")
        state.stale -> chrome.warnMark to "Stale — reconnecting"
        else -> when (state.activity) {
            Activity.LISTENING -> chrome.warnMark to "Listening"
            Activity.THINKING, Activity.WORKING -> accent to "Thinking"
            Activity.SPEAKING -> accent to "Speaking"
            Activity.ERROR -> chrome.badMark to "Error on the desktop"
            else -> chrome.okMark to when (state.power) {
                "quiet" -> "Linked · quiet"
                "standby" -> "Linked · standby"
                else -> "Linked"
            }
        }
    }

    Row(
        Modifier
            .fillMaxWidth()
            .background(chrome.surface1)
            .padding(horizontal = 8.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // The status is itself the way to the checks. You tap the thing that is
        // wrong to find out why, and it is present whether or not the link is
        // up — which the old Checks link was not.
        Row(
            Modifier
                .weight(1f)
                .clip(LocalRadii.current.insetShape)
                .pressable(onClick = actions.onOpenChecks)
                .padding(horizontal = 8.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Dot(dot)
            Spacer(Modifier.width(10.dp))
            Text(
                label,
                style = MaterialTheme.typography.labelMedium,
                color = chrome.textHi,
            )
        }

        if (state.link != LinkState.CONNECTED) {
            Quiet("Retry", onClick = actions.onReconnect)
        }
        Quiet(
            if (state.attention.pending > 0) "Inbox · ${state.attention.pending}" else "Inbox",
            color = if (state.attention.pending > 0) chrome.warnInk else chrome.textMid,
            onClick = actions.onOpenInbox,
        )
        Quiet("Look", color = chrome.textMid, onClick = actions.onOpenAppearance)
    }
}

@Composable
private fun Notice(text: String, onDismiss: () -> Unit) {
    val chrome = LocalChrome.current
    Plate(tone = chrome.warnInk.copy(alpha = 0.10f), outline = chrome.warnInk.copy(alpha = 0.35f)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text,
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.warnInk,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            Quiet("Dismiss", onClick = onDismiss)
        }
    }
}

@Composable
private fun Reply(reply: () -> String, streaming: Boolean) {
    val chrome = LocalChrome.current
    val motion = LocalMotion.current
    val text = reply()
    AnimatedVisibility(
        visible = text.isNotBlank() || streaming,
        enter = fadeIn(motion.enter()),
        exit = fadeOut(motion.micro()),
    ) {
        Plate {
            if (streaming) {
                Kicker("Jarvis", color = LocalAccent.current)
                Gap(6)
            }
            Text(
                text.ifBlank { "…" },
                style = MaterialTheme.typography.bodyLarge,
                color = chrome.textHi,
            )
        }
    }
}

@Composable
private fun Composer(state: HomeState, actions: HomeActions, micLevel: State<Float>) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val radii = LocalRadii.current
    val canSend = state.draft.isNotBlank() && state.link == LinkState.CONNECTED

    Column(
        Modifier
            .fillMaxWidth()
            .background(chrome.surface1)
            .padding(horizontal = 12.dp, vertical = 10.dp),
    ) {
    when (state.voicePhase) {
        VoiceSession.Phase.CAPTURING ->
            VoiceStrip("Listening — release to send, slide up to cancel")
        VoiceSession.Phase.VERIFYING ->
            // Named for what it is. The desktop checks whose voice this is
            // BEFORE transcribing, so that a voice that is not his is never
            // turned into words at all.
            VoiceStrip("Checking it's you…")
        VoiceSession.Phase.THINKING -> VoiceStrip("Thinking…")
        VoiceSession.Phase.SPEAKING -> VoiceStrip("Speaking")
        VoiceSession.Phase.OFF -> Unit
    }
    if (state.transcript != null && state.voicePhase != VoiceSession.Phase.CAPTURING) {
        VoiceStrip("“${state.transcript}”", tone = chrome.textMid)
    }
    if (state.voiceNotice != null) {
        VoiceStrip(state.voiceNotice, tone = chrome.warnInk, onDismiss = actions.onDismissVoiceNotice)
    }
    Row(
        Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.Bottom,
    ) {
        // BasicTextField rather than OutlinedTextField: the Material one brings
        // its own container, its own 56dp minimum, its own label animation and
        // its own notched outline, none of which belong in a design made of
        // flat plates and hairlines.
        Box(
            Modifier
                .weight(1f)
                .clip(radii.controlShape)
                .background(chrome.surface2)
                .padding(horizontal = 14.dp, vertical = 12.dp),
        ) {
            if (state.draft.isEmpty()) {
                Text(
                    "Ask Jarvis",
                    style = MaterialTheme.typography.bodyLarge,
                    color = chrome.textLo,
                )
            }
            BasicTextField(
                value = state.draft,
                onValueChange = actions.onDraftChange,
                textStyle = LocalTextStyle.current.merge(
                    MaterialTheme.typography.bodyLarge.copy(color = chrome.textHi),
                ),
                cursorBrush = SolidColor(accent),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                maxLines = 5,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        Spacer(Modifier.width(10.dp))
        Box(
            Modifier
                .height(48.dp)
                .clip(radii.controlShape)
                .background(
                    when {
                        state.streaming -> chrome.badInk.copy(alpha = 0.16f)
                        canSend -> accent
                        else -> chrome.surface2
                    },
                )
                .pressable(
                    enabled = state.streaming || canSend,
                    onClick = if (state.streaming) actions.onInterrupt else actions.onSend,
                )
                .padding(horizontal = 18.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                // Interrupt is the same button, because it is the same action's
                // other half: cancelling the HTTP call is what stops generation.
                if (state.streaming) "Stop" else "Send",
                style = MaterialTheme.typography.labelLarge,
                color = when {
                    state.streaming -> chrome.badInk
                    canSend -> chrome.surface0
                    else -> chrome.textLo
                },
            )
        }
        if (state.voiceOffered) {
            Spacer(Modifier.width(8.dp))
            VoiceButton(
                enabled = state.link == LinkState.CONNECTED && !state.streaming,
                capturing = state.voicePhase == VoiceSession.Phase.CAPTURING,
                micLevel = micLevel,
                onBegin = actions.onVoiceBegin,
                onRelease = actions.onVoiceRelease,
                onCancel = actions.onVoiceCancel,
            )
        }
    }
    }
}
