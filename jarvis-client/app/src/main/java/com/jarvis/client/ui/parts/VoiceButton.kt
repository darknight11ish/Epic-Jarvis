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
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.contentDescription
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
                    onBegin()
                    var cancelled = false
                    while (true) {
                        val event = awaitPointerEvent()
                        val change = event.changes.firstOrNull { it.id == down.id } ?: break
                        cancelled = (down.position.y - change.position.y) > cancelPx
                        wouldCancel = cancelled
                        if (!change.pressed) { change.consume(); break }
                        change.consume()
                    }
                    wouldCancel = false
                    if (cancelled) onCancel() else onRelease()
                }
            }
            .semantics {
                contentDescription =
                    if (capturing) "Recording. Release to send, slide up to cancel." else "Hold to talk"
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
