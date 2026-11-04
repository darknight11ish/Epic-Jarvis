package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.jarvis.client.call.CallRecordNow
import com.jarvis.client.call.CallRecordRules
import com.jarvis.client.ui.parts.Dot
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Call recording", in Settings under Voice (the owner's request of
 * 2026-11-04).
 *
 * This is the ONE place to arm and disarm it, and the line that shows what it
 * is doing - "Call recording armed" or "Recording call 00:04:12" - from
 * [CallRecordNow], the same state the phone's notification draws. The words
 * are plain, and the paragraph says the thing that decides whether the
 * recording is any good: Android will not let an app record the call itself,
 * so the microphone records the room and the call has to be on speaker.
 *
 * The armed state is deliberately LOUD here: while it is armed, the other
 * three microphone paths on this phone are paused (voice/MicOwner.kt), which
 * is a real cost the owner should be able to see and undo in one tap.
 *
 * Nothing here records, sends or reads anything by itself: the buttons start
 * the foreground service, which owns all of it, and the state shown is always
 * what that service last reported - never what a button just hoped for.
 */
@Composable
internal fun CallRecordCard() {
    val context = LocalContext.current
    val status by CallRecordNow.status.collectAsState()
    val chrome = LocalChrome.current

    // The queue on disk is the truth about what is still waiting, not a
    // number left over from a service that has since stopped. Not re-read
    // while the service runs: it knows, and it keeps the count current.
    LaunchedEffect(status.phase) {
        if (status.phase == CallRecordRules.Phase.OFF) CallRecordNow.refreshWaiting(context)
    }

    val tint = when (status.phase) {
        CallRecordRules.Phase.RECORDING -> chrome.warnInk
        CallRecordRules.Phase.ARMED -> chrome.warnInk
        CallRecordRules.Phase.SENDING -> chrome.textMid
        CallRecordRules.Phase.OFF -> chrome.textMid
    }

    Plate {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Dot(tint)
            Spacer(Modifier.width(10.dp))
            Text(CallRecordRules.PLATE_TITLE, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
            Spacer(Modifier.weight(1f))
            Text(
                CallRecordRules.line(status.phase, status.elapsedMs),
                style = MaterialTheme.typography.labelMedium,
                color = tint,
            )
        }
        Gap(6)
        Text(CallRecordRules.PLATE_ABOUT, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)

        // Said once, and only while it is true: the recording is running and
        // the platform would not put the call on speaker, so one side of the
        // conversation is probably missing. Never softened, never hidden.
        if (status.phase == CallRecordRules.Phase.RECORDING && !status.speaker) {
            Gap(8)
            Text(CallRecordRules.SPEAKER_ASK, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }

        if (status.phase == CallRecordRules.Phase.RECORDING) {
            Gap(8)
            Text(CallRecordRules.CONSENT_LINE, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
        }

        if (status.said != null) {
            Gap(8)
            Text(status.said.orEmpty(), style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }

        Gap(12)
        when (status.phase) {
            CallRecordRules.Phase.OFF -> {
                Primary(
                    text = "Arm call recording",
                    modifier = Modifier.fillMaxWidth(),
                    onClick = {
                        CallRecordNow.consumeSaid()
                        if (CallRecordNow.arm(context)) {
                            CallRecordNow.say(CallRecordRules.PLATE_ARMED)
                        } else {
                            CallRecordNow.say(
                                "Android did not let it start. A microphone service can only start with " +
                                    "Jarvis open on screen.",
                            )
                        }
                    },
                )
                Gap(4)
                Text(
                    "The microphone stays closed until a call starts. Say \"record call\" to Jarvis to do " +
                        "this from the chat.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textMid,
                )
            }
            CallRecordRules.Phase.ARMED -> {
                Secondary(
                    text = "Disarm - stop waiting for a call",
                    modifier = Modifier.fillMaxWidth(),
                    onClick = { CallRecordNow.disarm(context) },
                )
            }
            CallRecordRules.Phase.RECORDING -> {
                Primary(
                    text = "Stop recording",
                    color = chrome.warnInk,
                    modifier = Modifier.fillMaxWidth(),
                    onClick = { CallRecordNow.stop(context) },
                )
            }
            CallRecordRules.Phase.SENDING -> {
                Text(
                    "Sending the recording to your PC. If it cannot be reached, the audio stays on this " +
                        "phone and goes by itself next time.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
            }
        }

        // Anything finished that the PC has not taken. Nothing is ever thrown
        // away because a network was down, so this is the one place it is
        // offered again.
        if (status.waiting > 0) {
            Gap(8)
            Text(
                if (status.waiting == 1) {
                    "1 recorded call is waiting on this phone to be sent."
                } else {
                    "${status.waiting} recorded calls are waiting on this phone to be sent."
                },
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(6)
            Secondary(
                text = "Send it now",
                modifier = Modifier.fillMaxWidth(),
                onClick = { CallRecordNow.sendWaiting(context) },
            )
        }
    }
}
