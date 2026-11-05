package com.jarvis.client.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.Handsfree
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.ui.Modifier
import kotlinx.coroutines.launch

/**
 * Hands-free: the one switch, what it does in plain words, and what it is doing
 * now (the owner's request, 2026-11-04).
 *
 * The row is deliberately three sentences before the switch: what it does
 * ([Handsfree.ABOUT]), exactly when the microphone opens
 * ([Handsfree.WHEN_LISTENING]), and - once it can - what the phone needs
 * permission for. The owner asked for a setting he can turn OFF, and a setting
 * that opens a microphone has to say so on the screen that offers it, not in a
 * dialog after a tap.
 *
 * THE PERMISSIONS, and why they are asked here. Turning the switch ON asks
 * Android for the microphone, `SEND_SMS` and `READ_CONTACTS` in one dialog
 * sequence, with the sentences above already on screen. The switch is then set
 * from what the PC says, never from the dialog: a granted permission is not a
 * mode that is on. Refusing any of them is not a dead end - the mode still
 * reads cards out and still takes a spoken answer if the microphone was
 * granted, and the line under the switch says which part is missing
 * ([SmsSend.NO_PERMISSION], [SmsSend.NO_CONTACTS_PERMISSION]).
 *
 * WHAT IT CANNOT DO, said plainly rather than drawn as a broken switch: on a PC
 * that answers 404 the row says [Handsfree.NOT_HERE] and there is no switch at
 * all - there is nothing on that PC to turn on, and a switch that posts into a
 * 404 is the failure this project keeps writing down.
 *
 * @param canAct the link is up and fresh. Turning it ON waits for that (ON
 *   changes what Jarvis does); turning it OFF never does, because OFF only ever
 *   narrows.
 */
@Composable
internal fun HandsfreeSection(canAct: Boolean = false) {
    val chrome = LocalChrome.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val read by JarvisRuntime.handsfree.collectAsState()
    val missing by JarvisRuntime.handsfreeMissing.collectAsState()
    val now by JarvisRuntime.handsfreeNow.collectAsState()
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    // Read the PC's state when the row is first drawn, so the switch is never a
    // guess from this phone's own memory. `refreshAll` also reads it on every
    // open; this is what makes opening Settings itself authoritative.
    LaunchedEffect(Unit) { runCatching { JarvisRuntime.refreshHandsfree() } }

    fun set(on: Boolean) {
        if (busy) return
        busy = true
        scope.launch {
            try {
                said = JarvisRuntime.setHandsfree(on)
            } finally {
                busy = false
            }
        }
    }

    // The three the mode can need. Asked together, once, at the moment the
    // owner turns it on - never at launch, and never again behind his back.
    val ask = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { granted ->
        // Whatever he answered, the PC is still asked: the switch reflects the
        // PC's own state, and the lines below say what the phone cannot do with
        // a permission missing.
        if (granted.values.any { it } || granted.isEmpty()) set(true)
    }

    fun requestThenSet() {
        val wanted = PERMISSIONS.filter {
            ContextCompat.checkSelfPermission(context, it) != PackageManager.PERMISSION_GRANTED
        }
        if (wanted.isEmpty()) set(true) else ask.launch(wanted.toTypedArray())
    }

    val armed = read?.enabled == true
    val canRecord = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
        PackageManager.PERMISSION_GRANTED
    val canText = ContextCompat.checkSelfPermission(context, Manifest.permission.SEND_SMS) ==
        PackageManager.PERMISSION_GRANTED
    val canLookUp = ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CONTACTS) ==
        PackageManager.PERMISSION_GRANTED

    Section(Handsfree.SECTION) {
        Plate {
            Text(
                Handsfree.ABOUT,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(4)
            Text(
                Handsfree.WHEN_LISTENING,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
            Gap(8)
            if (missing) {
                // The honest degradation: no switch, one sentence. Both halves
                // of this feature ship together, so a PC without it is a
                // desktop that has not been updated - not a broken phone.
                Text(
                    Handsfree.NOT_HERE,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textHi,
                )
            } else {
                SwitchRow(
                    title = if (armed) Handsfree.ON else Handsfree.OFF,
                    detail = null,
                    checked = armed,
                    // OFF is always available, ON waits for a fresh link: the
                    // same rule every other switch on this screen follows.
                    enabled = !busy && (armed || canAct),
                    onChange = { on -> if (on) requestThenSet() else set(false) },
                )
                Text(
                    when {
                        busy -> "Asking your PC…"
                        said != null -> said!!
                        now.line != null -> now.line!!
                        armed -> read?.why ?: Handsfree.ON_DONE
                        else -> read?.why ?: Handsfree.OFF
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = if (now.listening) chrome.warnInk else chrome.textMid,
                )
                if (armed && read?.voicePrint.isNullOrBlank()) {
                    // Section 186.5 step 5: with no enrolled print the PC
                    // refuses a spoken YES outright, because it cannot tell the
                    // owner from a recording. Saying so here is the difference
                    // between a mode that looks broken and one that tells the
                    // owner what to do first.
                    Gap(4)
                    Text(
                        Handsfree.NO_PRINT,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textMid,
                    )
                }
                if (armed && !canRecord) {
                    Gap(4)
                    Text(
                        "Microphone permission is off, so Jarvis can read a card out but " +
                            "cannot hear your answer. Allow it in Android's settings for this app.",
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.warnInk,
                    )
                }
                if (armed && (!canText || !canLookUp)) {
                    Gap(4)
                    Text(
                        if (!canText) com.jarvis.client.net.SmsSend.NO_PERMISSION
                        else com.jarvis.client.net.SmsSend.NO_CONTACTS_PERMISSION,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.warnInk,
                    )
                    Secondary(
                        "Allow text messages",
                        modifier = Modifier.fillMaxWidth(),
                        onClick = {
                            ask.launch(
                                PERMISSIONS.filter {
                                    ContextCompat.checkSelfPermission(context, it) !=
                                        PackageManager.PERMISSION_GRANTED
                                }.toTypedArray(),
                            )
                        },
                    )
                }
            }
        }
    }
}

/** The three the mode can ask for, in the order Android shows them. */
private val PERMISSIONS = listOf(
    Manifest.permission.RECORD_AUDIO,
    Manifest.permission.SEND_SMS,
    Manifest.permission.READ_CONTACTS,
)
