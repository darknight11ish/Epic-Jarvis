package com.jarvis.client.ui.parts

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.disabled
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalRadii

/**
 * Hold to talk. Slide away to cancel.
 *
 * Hold rather than tap-to-start/tap-to-stop, and that is a privacy decision
 * rather than an idiom: while the button is down the microphone is open, and
 * when it is not, it is not. There is no state in which the app is listening
 * and the owner has to remember that it is. A phone travels — pocket, car,
 * other people's houses — which is the same reason the wake word ships off.
 *
 * Sliding away cancels because a hold is easy to start by accident and an
 * utterance cannot be unsent once the desktop has verified it.
 */
@Composable
fun VoiceButton(
    enabled: Boolean,
    capturing: Boolean,
    /**
     * Read inside `drawBehind`, never in composition. A microphone delivers
     * around fifty levels a second; reading it in the composable body would
     * recompose this row fifty times a second while the reactor is drawing on
     * the same thread.
     */
    micLevel: State<Float>,
    onBegin: () -> Unit,
    onRelease: () -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val haptics = LocalHapticFeedback.current
    var wouldCancel by remember { mutableStateOf(false) }
    val cancelPx = with(LocalDensity.current) { CANCEL_SLIDE_DP.dp.toPx() }

    Box(
        modifier
            .size(48.dp)
            .clip(CircleShape)
            .background(
                when {
                    !enabled -> chrome.surface2
                    wouldCancel -> chrome.badInk.copy(alpha = 0.20f)
                    capturing -> accent.copy(alpha = 0.22f)
                    else -> chrome.surface2
                },
            )
            .then(
                if (capturing) Modifier.border(
                    1.5.dp,
                    if (wouldCancel) chrome.badMark else accent,
                    CircleShape,
                ) else Modifier,
            )
            // The ring grows with the owner's voice. A draw-phase read of the
            // level, so a loud syllable costs one draw and no recomposition.
            .drawBehind {
                if (!capturing) return@drawBehind
                val level = micLevel.value.coerceIn(0f, 1f)
                if (level <= 0.02f) return@drawBehind
                drawCircle(
                    color = accent.copy(alpha = 0.18f + 0.22f * level),
                    radius = size.minDimension / 2f * (0.55f + 0.45f * level),
                )
            }
            .pointerInput(enabled) {
                if (!enabled) return@pointerInput
                awaitEachGesture {
                    val down = awaitFirstDown(requireUnconsumed = false)
                    down.consume()
                    wouldCancel = false
                    haptics.performHapticFeedback(HapticFeedbackType.LongPress)
                    onBegin()
                    var cancelled = false
                    // Set only by the loop below finishing on its own terms,
                    // which is the one thing that distinguishes a finger
                    // actually coming off the glass from this coroutine being
                    // torn down under it. `cancelled` cannot carry that: it
                    // tracks the slide-up gesture, and a teardown slides
                    // nothing, so it is false in exactly the case the comment
                    // below says must never send.
                    var released = false
                    // try/finally, because this coroutine is cancellable and the
                    // thing it owns is an open microphone.
                    //
                    // `pointerInput(enabled)` restarts whenever `enabled`
                    // changes, and enabled is `link == CONNECTED && !streaming`.
                    // So a link blip mid-hold — which happens every time the
                    // server recycles the hour-long SSE connection — tore this
                    // coroutine down between `onBegin()` and the release. With
                    // the release never delivered, `releaseRequested` stayed
                    // false, the recorder ran to its 30-second cap with the
                    // finger long since lifted, and then SENT it. The doc at the
                    // top of this file promises that when the button is not held
                    // the microphone is not open; without this it was a promise
                    // the code did not keep.
                    try {
                        while (true) {
                            val event = awaitPointerEvent()
                            val change = event.changes.firstOrNull { it.id == down.id } ?: break
                            val nowCancelled = (down.position.y - change.position.y) > cancelPx
                            // Fires once, on the transition into "would cancel" -
                            // not on every event while the finger sits past the
                            // threshold, which is most of them.
                            if (nowCancelled && !cancelled) {
                                haptics.performHapticFeedback(HapticFeedbackType.Reject)
                            }
                            cancelled = nowCancelled
                            wouldCancel = cancelled
                            if (!change.pressed) { change.consume(); break }
                            change.consume()
                        }
                        released = true
                    } finally {
                        wouldCancel = false
                        // A torn-down gesture is a cancel, never a send: audio
                        // captured while nobody was holding the button must not
                        // reach the desktop.
                        //
                        // Which is why this asks `released` and not just
                        // `cancelled`. Testing `cancelled` alone sent on every
                        // teardown — the link blip described above reached the
                        // `else` branch with `cancelled` false and uploaded the
                        // half-held clip, which is the exact outcome the
                        // try/finally was added to prevent.
                        if (released && !cancelled) onRelease() else onCancel()
                    }
                }
            }
            // What TalkBack says (a11y-10).
            //
            // The node used to carry "Hold to talk" and nothing else: no
            // role, and no word about how a screen-reader user actually
            // holds something. With TalkBack on, the way to hold is
            // double-tap-and-hold, so the description now says exactly that,
            // and the button role makes it announce as a control. A
            // disabled button says so rather than going silent.
            //
            // Words only - no accessibility ACTION is added, deliberately.
            // The audit suggested `onLongClick(label = "talk") { false }`,
            // which would make TalkBack speak its own "double-tap and hold"
            // hint. Whether TalkBack then passes the real press through to
            // the pointerInput above, or performs that do-nothing action
            // INSTEAD of passing it through, has not been checked on a
            // phone, and the second outcome would break voice input under
            // TalkBack. A sentence cannot change what the gesture does.
            // There is no onClick either: a tap-to-start toggle is what the
            // hold design exists to avoid (a press with no release once
            // uploaded up to two minutes of audio - see MainActivity).
            .semantics {
                contentDescription = if (capturing) {
                    "Recording. Lift your finger to send, or slide up to cancel."
                } else {
                    "Talk to Jarvis. Double-tap and hold, speak, then lift your finger to send."
                }
                role = Role.Button
                if (!enabled) disabled()
            },
        contentAlignment = Alignment.Center,
    ) {
        // A drawn glyph rather than an icon dependency: a capsule on a stand,
        // which is a microphone everywhere.
        val tint = when {
            !enabled -> chrome.textLo
            wouldCancel -> chrome.badInk
            capturing -> accent
            else -> chrome.textMid
        }
        Box(
            Modifier
                .size(width = 10.dp, height = 17.dp)
                .clip(RoundedCornerShape(percent = 50))
                .background(tint),
        )
        Box(
            Modifier
                .padding(top = 22.dp)
                .size(width = 16.dp, height = 2.dp)
                .background(tint),
        )
    }
}

/** The strip above the composer while a turn is in flight. */
@Composable
fun VoiceStrip(
    label: String,
    tone: androidx.compose.ui.graphics.Color? = null,
    onDismiss: (() -> Unit)? = null,
) {
    val chrome = LocalChrome.current
    val colour = tone ?: LocalAccent.current
    Row(
        Modifier
            .fillMaxWidth()
            .clip(LocalRadii.current.controlShape)
            .background(colour.copy(alpha = 0.10f))
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Dot(colour)
        Spacer(Modifier.width(10.dp))
        Text(
            label,
            style = MaterialTheme.typography.bodyMedium,
            color = chrome.textHi,
            modifier = Modifier.weight(1f),
        )
        if (onDismiss != null) {
            Spacer(Modifier.width(8.dp))
            Quiet("Dismiss", color = chrome.textMid, onClick = onDismiss)
        }
    }
    Spacer(Modifier.height(8.dp))
}

/** How far up the finger must travel before a release cancels instead of sends. */
private const val CANCEL_SLIDE_DP = 64
