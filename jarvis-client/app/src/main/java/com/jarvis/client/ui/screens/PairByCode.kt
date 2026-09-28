package com.jarvis.client.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.data.BaseUrl
import com.jarvis.client.net.Pairing
import com.jarvis.client.net.PairingFlow
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome

/** Where the owner is in scanning or typing the code, before the PC is asked anything. */
private enum class CodeStep { START, EXPLAIN_CAMERA, SCANNING, TYPING, CONFIRM }

/**
 * "Scan the code on your PC" and "Type the code instead" - the top of the
 * pairing screen (docs/PAIRING-DESIGN.md §7.2).
 *
 * The order is always: read the code (camera or typed) -> "Connect to
 * <name>?" with this phone's name -> the four words, while the PC's card
 * waits -> the key, handed to [onDeviceKey], which saves it, shakes hands,
 * and only then drops the old key (MainActivity's pairing branch). The
 * "Connect to ...?" question is asked every time, so a code someone else
 * printed cannot quietly point this phone at a different PC.
 *
 * The code and the secret it holds are kept in plain `remember` only -
 * never saved state - and the attempt itself in [JarvisRuntime.pairing],
 * in memory. [onSecretShown] is told true whenever a code, the camera
 * (which shows the code) or the words are on screen, so the caller blocks
 * screenshots meanwhile (FLAG_SECURE, like "Show token").
 *
 * @param address the pairing screen's own address field, reused for the typed code.
 * @param busy the saved key's handshake is running (MainActivity).
 */
@Composable
internal fun CodePairingSection(
    address: String,
    onAddressChange: (String) -> Unit,
    busy: Boolean,
    onDeviceKey: (address: String, key: String) -> Unit,
    onSecretShown: (Boolean) -> Unit,
) {
    val chrome = LocalChrome.current
    val context = LocalContext.current
    val flow = JarvisRuntime.pairing
    val state by flow.state.collectAsState()

    var step by remember { mutableStateOf(CodeStep.START) }
    var code by remember { mutableStateOf("") }
    var target by remember { mutableStateOf<Pairing.Target?>(null) }
    var name by remember { mutableStateOf(Pairing.suggestedName(android.os.Build.MODEL)) }
    var message by remember { mutableStateOf<String?>(null) }
    var scanMessage by remember { mutableStateOf<String?>(null) }

    val secret = step != CodeStep.START || state !is PairingFlow.State.Idle
    LaunchedEffect(secret) { onSecretShown(secret) }

    fun backToStart(withMessage: String? = null) {
        step = CodeStep.START
        code = ""
        target = null
        scanMessage = null
        message = withMessage
    }

    val cameraPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) {
            scanMessage = null
            step = CodeStep.SCANNING
        } else {
            backToStart(Pairing.CAMERA_REFUSED)
        }
    }
    fun cameraAllowed(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

    // The PC approved: the key goes straight on to be saved and checked,
    // and this flow lets go of it.
    LaunchedEffect(state) {
        if (state is PairingFlow.State.Approved) {
            flow.takeKey()?.let { (addr, key) ->
                backToStart()
                onDeviceKey(addr, key)
            }
        }
    }

    Column(Modifier.fillMaxWidth()) {
        when (val s = state) {
            is PairingFlow.State.Asking -> {
                Text(
                    "Asking your PC at ${s.address}…",
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textMid,
                    modifier = Modifier.liveStatus(),
                )
                Gap(10)
                Quiet("Cancel", color = chrome.textMid) { flow.cancel(); backToStart() }
            }
            is PairingFlow.State.Words -> {
                Text(
                    "Check the words",
                    style = MaterialTheme.typography.labelLarge,
                    color = chrome.textHi,
                )
                Gap(8)
                Text(
                    Pairing.wordsLine(s.words),
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.SemiBold,
                    color = chrome.textHi,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth(),
                )
                Gap(10)
                Text(Pairing.APPROVE_IF_SAME, style = MaterialTheme.typography.bodyMedium, color = chrome.textMid)
                Gap(4)
                Text(
                    "Waiting for the card on your PC. If the words are different, deny it there.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                    modifier = Modifier.liveStatus(),
                )
                Gap(10)
                Quiet("Cancel", color = chrome.textMid) { flow.cancel(); backToStart() }
            }
            is PairingFlow.State.Approved -> {
                Text(
                    "Approved on your PC. Connecting with this phone's new key…",
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textMid,
                    modifier = Modifier.liveStatus(),
                )
            }
            is PairingFlow.State.Ended -> {
                Text(
                    s.message,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.badInk,
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(chrome.badInk.copy(alpha = 0.10f), RoundedCornerShape(10.dp))
                        .padding(12.dp)
                        .liveStatus(),
                )
                Gap(10)
                Secondary("Start again", modifier = Modifier.fillMaxWidth()) { flow.cancel(); backToStart() }
            }
            PairingFlow.State.Idle -> when (step) {
                CodeStep.START -> {
                    if (busy) {
                        Text(
                            "Connecting…",
                            style = MaterialTheme.typography.bodyMedium,
                            color = chrome.textMid,
                            modifier = Modifier.liveStatus(),
                        )
                        Gap(10)
                    }
                    Primary(
                        "Scan the code on your PC",
                        enabled = !busy,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        message = null
                        val hasCamera = context.packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY)
                        when {
                            !hasCamera -> message = "This phone has no camera Jarvis can use. Type the code instead."
                            cameraAllowed() -> step = CodeStep.SCANNING
                            else -> step = CodeStep.EXPLAIN_CAMERA
                        }
                    }
                    Gap(8)
                    Secondary("Type the code instead", enabled = !busy, modifier = Modifier.fillMaxWidth()) {
                        message = null
                        step = CodeStep.TYPING
                    }
                    Gap(6)
                    Text(
                        "On your PC: Settings, Devices, Pair a phone.",
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                    message?.let {
                        Gap(8)
                        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                    }
                }
                CodeStep.EXPLAIN_CAMERA -> {
                    Text(Pairing.CAMERA_WHY, style = MaterialTheme.typography.bodyMedium, color = chrome.textMid)
                    Gap(10)
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Primary("Continue", modifier = Modifier.weight(1f)) {
                            cameraPermission.launch(Manifest.permission.CAMERA)
                        }
                        Secondary("Type the code instead", modifier = Modifier.weight(1f)) {
                            step = CodeStep.TYPING
                        }
                    }
                }
                CodeStep.SCANNING -> {
                    Text(
                        "Point the camera at the QR code on your PC.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = chrome.textMid,
                    )
                    Gap(8)
                    QrScanner(
                        onText = { text ->
                            when (val parsed = Pairing.parseQr(text)) {
                                is Pairing.Parsed.Ok -> {
                                    target = parsed.target
                                    scanMessage = null
                                    step = CodeStep.CONFIRM
                                }
                                is Pairing.Parsed.Bad -> scanMessage = parsed.message
                            }
                        },
                        onError = {
                            backToStart("The camera could not be started. Type the code instead.")
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(280.dp),
                    )
                    scanMessage?.let {
                        Gap(8)
                        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                    }
                    Gap(8)
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Quiet("Type the code instead", color = chrome.textMid) { step = CodeStep.TYPING }
                        Quiet("Cancel", color = chrome.textMid) { backToStart() }
                    }
                }
                CodeStep.TYPING -> {
                    TextInput(
                        value = address,
                        onValueChange = onAddressChange,
                        label = "Your PC's Tailscale or Meshnet name",
                        placeholder = "your-pc.tailnet.ts.net  (or ….nord)",
                        supportingText = "The name the Tailscale or NordVPN app shows for your PC. " +
                            "Leave off :4719 and it is added for you.",
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Uri,
                            imeAction = ImeAction.Next,
                        ),
                    )
                    Gap(10)
                    TextInput(
                        value = code,
                        onValueChange = { code = it.take(12) },
                        label = "Code (8 letters)",
                        placeholder = "K7QM-4TXD",
                        supportingText = "Under the QR code on your PC. It works once, for 10 minutes.",
                        // No suggestions, and the keyboard does not learn it.
                        keyboardOptions = KeyboardOptions(
                            capitalization = KeyboardCapitalization.Characters,
                            keyboardType = KeyboardType.Password,
                            imeAction = ImeAction.Done,
                        ),
                    )
                    message?.let {
                        Gap(8)
                        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                    }
                    Gap(10)
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Primary(
                            "Next",
                            enabled = address.isNotBlank() && code.isNotBlank(),
                            modifier = Modifier.weight(1f),
                        ) {
                            when (val parsed = Pairing.typedTarget(address, code, BaseUrl.DEFAULT_PORT)) {
                                is Pairing.Parsed.Ok -> {
                                    target = parsed.target
                                    code = ""
                                    message = null
                                    step = CodeStep.CONFIRM
                                }
                                is Pairing.Parsed.Bad -> message = parsed.message
                            }
                        }
                        Secondary("Cancel", modifier = Modifier.weight(1f)) { backToStart() }
                    }
                }
                CodeStep.CONFIRM -> {
                    val t = target
                    if (t == null) {
                        // Only after a rotation: the code was never saved, so read it again.
                        LaunchedEffect(Unit) { backToStart() }
                    } else {
                        Text("Connect to ${t.host}?", style = MaterialTheme.typography.titleMedium, color = chrome.textHi)
                        Gap(6)
                        Text(
                            "Only if that is your PC. Your PC will show an approval card; nothing is " +
                                "handed over until you approve it there.",
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid,
                        )
                        Gap(10)
                        val nameProblem = Pairing.nameProblem(name.trim())
                        TextInput(
                            value = name,
                            onValueChange = { name = it.take(40) },
                            label = "Name for this phone",
                            supportingText = nameProblem ?: "Shown on your PC's card and in its list of devices.",
                            supportingColor = if (nameProblem != null) chrome.warnInk else null,
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                        )
                        Gap(10)
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Primary("Connect", enabled = nameProblem == null, modifier = Modifier.weight(1f)) {
                                flow.start(t, name.trim())
                                target = null
                                step = CodeStep.START
                            }
                            Secondary("Cancel", modifier = Modifier.weight(1f)) { backToStart() }
                        }
                    }
                }
            }
        }
    }
}
