package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.TextInput

/**
 * Host and token, and nothing else.
 *
 * The token field is write-only and masked: a stored token is never read back
 * into the UI. That is not theatre — it is the only secret this app holds, and
 * `JARVIS-API.md` §1 is explicit that for a native client it is the only thing
 * protecting the backend.
 *
 * Also the screen for pairing AGAIN. Once paired there used to be no way back
 * here at all, while the app's own error told the owner to "paste it again" -
 * so a changed token, or a move to NordVPN Meshnet (which gives the desktop a
 * new name), was a dead end short of clearing the app's storage. When
 * [onCancel] is set, this is that second visit: the saved desktop and token
 * are still in use, and they stay in use until the new ones connect.
 */
@Composable
fun PairingScreen(
    /** The host to show. When [onHostChange] is set this IS the field's value. */
    initialHost: String,
    hasToken: Boolean,
    busy: Boolean,
    /** The last handshake failure, in words the user can act on. */
    notice: String?,
    onPair: (host: String, token: String) -> Unit,
    onOpenReadiness: () -> Unit,
    modifier: Modifier = Modifier,
    /**
     * Hands every edit of the host up to the caller, which then owns it.
     *
     * The host used to live only in this screen's own saved state, seeded from
     * the saved setting and written back only on Connect. Opening Platform
     * checks took this screen out of composition, so the address being typed
     * was gone when the owner came back - and Checks had reported on the old,
     * usually blank, one. Owned by the caller, it survives the visit and Checks
     * can judge it. Null keeps the old self-contained behaviour.
     */
    onHostChange: ((String) -> Unit)? = null,
    /** Opens Help. Null hides it. Help answers "do I need Tailscale?", which is
     *  a question someone asks BEFORE they can pair, not after. */
    onOpenHelp: (() -> Unit)? = null,
    /** Set when a desktop is already paired: leaves this screen and keeps it. */
    onCancel: (() -> Unit)? = null,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current

    // Keyed, so a host that changes underneath us (a fresh value read back from
    // settings) replaces the field instead of being ignored for the life of the
    // saved value. Only used when the caller does not own the host.
    var localHost by rememberSaveable(initialHost) { mutableStateOf(initialHost) }
    val host = if (onHostChange != null) initialHost else localHost
    val setHost: (String) -> Unit = { value ->
        if (onHostChange != null) {
            onHostChange(value)
        } else {
            localHost = value
        }
    }

    // `remember`, NEVER `rememberSaveable`.
    //
    // rememberSaveable writes its value into the Activity's saved-instance
    // Bundle, which is handed to system_server and kept across rotation and
    // process death. That put the pairing token - the one secret this app holds,
    // and per JARVIS-API.md §1 the only thing protecting the backend - in plain
    // text outside the app's own storage and outside the Keystore that exists
    // precisely to hold it. The cost of not saving it is that a rotation
    // mid-typing clears the field, which is the right trade for a secret.
    var token by remember { mutableStateOf("") }

    // Set once the token has been handed over, so the field can be emptied
    // without disabling Connect. `hasToken` is read once by the caller and does
    // not update, and MainActivity stores the token BEFORE the handshake - so
    // after a failed handshake a token IS stored, and the retry must stay
    // available with the field blank.
    //
    // Re-pairing differs in one way: a failed attempt puts the OLD token back
    // (see MainActivity's onPair), so a blank retry sends the old token with
    // whatever address is typed. That is what the field's own "leave this
    // blank to keep it" already promises, so it needs no extra wording.
    var handedOver by remember { mutableStateOf(false) }

    Column(
        modifier
            .fillMaxSize()
            .background(chrome.surface0)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 18.dp),
    ) {
        Spacer(Modifier.height(28.dp))
        Text("JARVIS", style = MaterialTheme.typography.titleLarge, color = accent)
        Text(
            if (onCancel != null) "Change desktop or token" else "Pair with your desktop",
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textMid,
        )
        if (onCancel != null) {
            Spacer(Modifier.height(10.dp))
            Text(
                "Your current desktop and token stay saved and in use until the new " +
                    "ones connect. If they do not, nothing changes.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        }

        Spacer(Modifier.height(22.dp))
        TextInput(
            value = host,
            onValueChange = setHost,
            label = "Desktop address",
            placeholder = "your-desktop.tailnet.ts.net:4719  (or ….nord for Meshnet)",
            // Plain words first. The old text ended on "the network security
            // config can permit a name but cannot express a CIDR range", which
            // is true and useless to someone who has not written an Android
            // manifest. Platform checks keeps the technical version.
            supportingText = "The desktop's name on your private network: its " +
                "Tailscale name (ends in .ts.net) or its NordVPN Meshnet name (ends " +
                "in .nord). A number like 100.x will not work, because Android only " +
                "lets this app use names it has been told about.",
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Uri,
                imeAction = ImeAction.Next,
            ),
        )

        Spacer(Modifier.height(14.dp))
        TextInput(
            value = token,
            onValueChange = { token = it },
            password = true,
            label = if (hasToken) "Replace token" else "Pairing token",
            placeholder = "The token from the desktop's HUD settings",
            supportingText = if (hasToken) {
                "A token is stored. Leave this blank to keep it."
            } else {
                "Kept encrypted on this phone, in Android's secure key storage."
            },
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Password,
                imeAction = ImeAction.Done,
            ),
        )

        if (notice != null) {
            Spacer(Modifier.height(14.dp))
            Text(
                notice,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.badInk,
                modifier = Modifier
                    .background(chrome.badInk.copy(alpha = 0.10f), RoundedCornerShape(10.dp))
                    .padding(12.dp),
            )
        }

        Spacer(Modifier.height(20.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Primary(
                text = "Connect",
                busy = busy,
                enabled = !busy && host.isNotBlank() &&
                    (hasToken || handedOver || token.isNotBlank()),
                modifier = Modifier.weight(1f),
                onClick = {
                    onPair(host, token)
                    // Cleared the moment it is handed over. On success this
                    // screen leaves composition anyway; on failure the secret
                    // is already in the Keystore and does not need to sit in a
                    // text field on an unlocked phone waiting for a retry.
                    handedOver = handedOver || token.isNotBlank()
                    token = ""
                },
            )

            // Secondary, not Primary (visual-5): Connect is the one action
            // this screen is for, so it is the only filled button on it.
            Secondary(
                text = "Platform checks",
                color = chrome.textMid,
                modifier = Modifier.weight(1f),
                onClick = onOpenReadiness,
            )
        }

        if (onOpenHelp != null || onCancel != null) {
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                if (onOpenHelp != null) {
                    Quiet("Help", color = chrome.textMid, onClick = onOpenHelp)
                }
                if (onCancel != null) {
                    // Disabled while busy. During an attempt the new address
                    // and token are already the saved ones, and if the attempt
                    // then connected, the new desktop would be kept - the
                    // opposite of what this button says. Once the attempt
                    // ends (at most the short call timeout), leaving works
                    // again, with the old pair back in place if it failed.
                    Quiet(
                        "Keep current desktop",
                        color = chrome.textMid,
                        enabled = !busy,
                        onClick = onCancel,
                    )
                }
            }
        }

        Spacer(Modifier.height(28.dp))
    }
}
