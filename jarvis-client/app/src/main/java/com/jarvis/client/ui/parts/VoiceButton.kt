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
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalRadii

/**
 * Tap to talk; tap again, or wait for the Smart Turn pause, to send. A hold
 * still works — keep it down, speak, let go to send. Slide away to cancel.
 *
 * Tapping starts a recording that outlives the tap, so the old guarantee is
 * spent: the microphone is no longer open only while a finger is down. What
 * replaces it is the visible recording state until the clip goes, the Stop
 * path that sends early, and the time limit that closes the microphone
 * whether or not the owner remembers it is open.
 *
 * The pause ends the clip by itself (the on-phone Smart Turn model, else the
 * old fixed second of quiet). Sliding away cancels because a tap is easy to
 * start by accident and an utterance cannot be unsent once the desktop has
 * verified it.
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
    val isCapturing = capturing

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
            .pointerInput(enabled, isCapturing) {
                if (!enabled) return@pointerInput
                awaitEachGesture {
                    val down = awaitFirstDown(requireUnconsumed = false)
                    down.consume()
                    wouldCancel = false
                    val downTime = System.currentTimeMillis()
                    val wasCapturingAtDown = isCapturing

                    if (!wasCapturingAtDown) {
                        haptics.performHapticFeedback(HapticFeedbackType.LongPress)
                        onBegin()
                    }

                    var cancelled = false
                    var released = false
                    try {
                        while (true) {
                            val event = awaitPointerEvent()
                            val change = event.changes.firstOrNull { it.id == down.id } ?: break
                            val nowCancelled = (down.position.y - change.position.y) > cancelPx
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
                        val duration = System.currentTimeMillis() - downTime
                        if (cancelled) {
                            onCancel()
                        } else if (released) {
                            if (wasCapturingAtDown) {
                                // Second tap while capturing: stop and send.
                                onRelease()
                            } else if (duration >= HOLD_THRESHOLD_MS) {
                                // Sustained hold-to-talk released: send.
                                onRelease()
                            }
                            // Otherwise, a quick tap (< 400ms) entered capturing mode;
                            // recording continues until second tap or Smart Turn pause detection.
                        } else {
                            // Torn down gesture without release: cancel.
                            onCancel()
                        }
                    }
                }
            }
            .semantics {
                contentDescription = if (capturing) {
                    "Recording. Tap to send, or wait for pause to send automatically. Slide up to cancel."
                } else {
                    "Talk to Jarvis. Tap or hold to speak."
                }
                role = Role.Button
                if (!enabled) disabled()
                onClick(label = if (capturing) "Stop and send" else "Talk to Jarvis") {
                    if (capturing) onRelease() else onBegin()
                    true
                }
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

/** Sustained press duration that distinguishes hold-to-talk from tap-to-talk. */
private const val HOLD_THRESHOLD_MS = 400L
