package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Devices
import com.jarvis.client.net.SignedApproval
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Refuse
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Settings -> Devices (docs/PAIRING-DESIGN.md §7.2): every device with a key
 * of its own, "This phone" marked, each with Remove - which asks "are you
 * sure?" right here first, like Forget - and the old shared key's row.
 *
 * Remove and "Retire for other devices" only take access away, so they are
 * immediate on the PC and not held on a stale link (design §12, rule 4).
 * "Bring it back" is on the PC only (a loosening, with Windows Hello), so it
 * is not offered here - one-sided on purpose (design §12).
 *
 * Removing this phone itself: its key stops working at once, and the event
 * stream is restarted so the refusal ("This phone's key was removed ...")
 * brings back the pairing screen, as for any refused key.
 */
@Composable
internal fun DevicesSection() {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Devices.View?>(null) }
    var readError by remember { mutableStateOf<String?>(null) }
    var missing by remember { mutableStateOf(false) }
    var asking by remember { mutableStateOf<String?>(null) }
    var askingRetire by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    var local by remember { mutableStateOf(SignedApproval.Local.NONE) }

    // Signed approvals (design §11): waiting for the owner's yes on the PC
    // is re-read every few seconds until the PC says it is on.
    val signedState = view?.let { v ->
        SignedApproval.stateOf(v.usesOwnKey, v.devices.firstOrNull { it.thisDevice }?.approvalKey, local)
    }
    val signedWaiting = signedState == SignedApproval.State.WAITING
    LaunchedEffect(reads, signedWaiting) {
        if (signedWaiting) {
            delay(3_000)
            reads += 1
        }
    }

    LaunchedEffect(reads) {
        local = JarvisRuntime.approvalKeyLocal()
        when (val r = JarvisRuntime.devices()) {
            is ApiResult.Ok -> {
                view = Devices.parse(r.value)
                missing = false
                readError = null
            }
            is ApiResult.Failed -> {
                missing = r.error == ApiError.NotFound
                readError = if (missing) null else JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    Section("Devices") {
        Plate {
            Text(
                "The devices that can reach Jarvis, each with its own key. Removing one cuts it off at " +
                    "once; the others carry on. To add a phone, press Pair a phone in Settings, Devices, " +
                    "on your PC.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            if (missing) {
                Gap(8)
                Text(Devices.MISSING, style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
            }
            readError?.let {
                Gap(8)
                Text("Couldn't read the list: $it", style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
                Gap(4)
                Quiet("Try again", color = chrome.textMid) { reads += 1 }
            }
            val v = view
            if (!missing && v != null) {
                val nowSec = System.currentTimeMillis() / 1000L

                for (d in v.devices) {
                    Gap(10)
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Column(Modifier.weight(1f)) {
                            Text(
                                if (d.thisDevice) "${d.name} (${Devices.THIS_PHONE.lowercase()})" else d.name,
                                style = MaterialTheme.typography.labelLarge,
                                color = chrome.textHi,
                            )
                            Text(
                                Devices.detailLine(d, nowSec),
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textLo,
                            )
                        }
                        if (d.removable && asking != d.id) {
                            Quiet("Remove", color = chrome.badInk, enabled = !busy) {
                                asking = d.id
                                askingRetire = false
                                said = null
                            }
                        }
                    }
                    if (asking == d.id) {
                        Gap(6)
                        Text(Devices.removeQuestion(d), style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                        Gap(6)
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Secondary("Cancel", modifier = Modifier.weight(1f)) { asking = null }
                            Refuse("Remove", enabled = !busy) {
                                busy = true
                                scope.launch {
                                    try {
                                        val (words, wasThisPhone) = JarvisRuntime.removeDevice(d)
                                        said = words
                                        if (wasThisPhone) {
                                            // The key is dead now: let the stream hear so, which
                                            // brings the pairing screen back with the PC's reason.
                                            JarvisRuntime.startStream(force = true)
                                        }
                                    } finally {
                                        busy = false
                                        asking = null
                                        reads += 1
                                    }
                                }
                            }
                        }
                    }
                }

                if (signedState != null &&
                    signedState != SignedApproval.State.UNSUPPORTED &&
                    signedState != SignedApproval.State.NOT_PAIRED
                ) {
                    Gap(14)
                    Text("Signed approvals", style = MaterialTheme.typography.labelLarge, color = chrome.textHi)
                    Text(signedState.line, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    Gap(4)
                    Text(
                        "Risky approvals from this phone are signed with your fingerprint or PIN, and your " +
                            "PC checks the signature. Without it, this phone cannot approve risky cards.",
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                    )
                    Gap(6)
                    val turnOnLabel =
                        if (signedState == SignedApproval.State.AGAIN) "Turn on signed approvals again" else SignedApproval.TURN_ON
                    if (signedState == SignedApproval.State.OFF || signedState == SignedApproval.State.AGAIN) {
                        Secondary(turnOnLabel, enabled = !busy, modifier = Modifier.fillMaxWidth()) {
                            busy = true
                            scope.launch {
                                try {
                                    said = JarvisRuntime.turnOnSignedApprovals()
                                } finally {
                                    busy = false
                                    reads += 1
                                }
                            }
                        }
                    }
                    if (signedState == SignedApproval.State.ON || signedState == SignedApproval.State.WAITING ||
                        (signedState == SignedApproval.State.AGAIN && local != SignedApproval.Local.NONE)
                    ) {
                        Quiet(SignedApproval.TURN_OFF, color = chrome.textMid, enabled = !busy) {
                            busy = true
                            scope.launch {
                                try {
                                    said = JarvisRuntime.turnOffSignedApprovals()
                                } finally {
                                    busy = false
                                    reads += 1
                                }
                            }
                        }
                    }
                }

                v.pairingWhyNot?.let {
                    Gap(10)
                    Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                }

                v.shared?.let { shared ->
                    Gap(14)
                    Text(Devices.SHARED_ROW, style = MaterialTheme.typography.labelLarge, color = chrome.textHi)
                    Text(
                        Devices.sharedLine(shared, nowSec),
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                    // Only when this phone has a key of its own - retiring the
                    // shared key from a phone that uses it would cut it off (the
                    // PC refuses that anyway, design §6.4). Not offered once the
                    // first device has its own key either: the shared key already
                    // works from this PC only, so the button would change nothing
                    // (backend, 2026-10-05).
                    if (!shared.retired && !shared.firstPairOnly && v.usesOwnKey) {
                        if (signedState == SignedApproval.State.ON) {
                            Gap(4)
                            Text(
                                Devices.SHARED_PROMPT_RETIRE,
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.warnInk,
                            )
                        }
                        Gap(6)
                        if (!askingRetire) {
                            Secondary("Retire for other devices", enabled = !busy, modifier = Modifier.fillMaxWidth()) {
                                askingRetire = true
                                asking = null
                                said = null
                            }
                        } else {
                            Text(
                                Devices.retireQuestion(shared, nowSec),
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.textMid,
                            )
                            Gap(6)
                            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                Secondary("Cancel", modifier = Modifier.weight(1f)) { askingRetire = false }
                                Refuse("Retire", enabled = !busy) {
                                    busy = true
                                    scope.launch {
                                        try {
                                            said = JarvisRuntime.retireSharedKey()
                                        } finally {
                                            busy = false
                                            askingRetire = false
                                            reads += 1
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

            }

            said?.let {
                Gap(8)
                Text(
                    it,
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textMid,
                    modifier = Modifier.liveStatus(),
                )
            }
        }
    }
}
