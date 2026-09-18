package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
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
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.jarvis.client.ui.T

/**
 * Host and token, and nothing else.
 *
 * The token field is write-only and masked: a stored token is never read back
 * into the UI. That is not theatre — it is the only secret this app holds, and
 * `JARVIS-API.md` §1 is explicit that for a native client it is the only thing
 * protecting the backend.
 */
@Composable
fun PairingScreen(
    initialHost: String,
    hasToken: Boolean,
    busy: Boolean,
    /** The last handshake failure, in words the user can act on. */
    notice: String?,
    onPair: (host: String, token: String) -> Unit,
    onOpenReadiness: () -> Unit,
    modifier: Modifier = Modifier,
) {
    // Keyed, so a host that changes underneath us (a fresh value read back from
    // settings) replaces the field instead of being ignored for the life of the
    // saved value.
    var host by rememberSaveable(initialHost) { mutableStateOf(initialHost) }

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
    var handedOver by remember { mutableStateOf(false) }

    Column(
        modifier
            .fillMaxSize()
            .background(T.Void)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 18.dp),
    ) {
        Spacer(Modifier.height(28.dp))
        Text("JARVIS", style = MaterialTheme.typography.titleLarge, color = T.Pick)
        Text(
            "Pair with your desktop",
            style = MaterialTheme.typography.labelSmall,
            color = T.Dim,
        )

        Spacer(Modifier.height(22.dp))
        OutlinedTextField(
            value = host,
            onValueChange = { host = it },
            singleLine = true,
            label = { Text("Desktop host", color = T.Dim) },
            placeholder = { Text("your-desktop.tailnet.ts.net:4719", color = T.Dim) },
            supportingText = {
                Text(
                    "Use the MagicDNS name, not the 100.x address — the network " +
                        "security config can permit a name but cannot express a CIDR range.",
                    color = T.Dim,
                    style = MaterialTheme.typography.labelSmall,
                )
            },
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Uri,
                imeAction = ImeAction.Next,
            ),
            colors = fieldColors(),
            modifier = Modifier.fillMaxWidth(),
        )

        Spacer(Modifier.height(14.dp))
        OutlinedTextField(
            value = token,
            onValueChange = { token = it },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            label = { Text(if (hasToken) "Replace token" else "Pairing token", color = T.Dim) },
            placeholder = { Text("HUD_TOKEN from the desktop", color = T.Dim) },
            supportingText = {
                Text(
                    if (hasToken) {
                        "A token is stored. Leave this blank to keep it."
                    } else {
                        "Stored encrypted by the Android Keystore, never in plain preferences."
                    },
                    color = T.Dim,
                    style = MaterialTheme.typography.labelSmall,
                )
            },
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Password,
                imeAction = ImeAction.Done,
            ),
            colors = fieldColors(),
            modifier = Modifier.fillMaxWidth(),
        )

        if (notice != null) {
            Spacer(Modifier.height(14.dp))
            Text(
                notice,
                style = MaterialTheme.typography.bodySmall,
                color = T.Bad,
                modifier = Modifier
                    .fillMaxWidth()
                    .background(T.Bad.copy(alpha = 0.10f), RoundedCornerShape(10.dp))
                    .padding(12.dp),
            )
        }

        Spacer(Modifier.height(20.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(
                onClick = {
                    onPair(host, token)
                    // Cleared the moment it is handed over. On success this
                    // screen leaves composition anyway; on failure the secret
                    // is already in the Keystore and does not need to sit in a
                    // text field on an unlocked phone waiting for a retry.
                    handedOver = handedOver || token.isNotBlank()
                    token = ""
                },
                enabled = !busy && host.isNotBlank() &&
                    (hasToken || handedOver || token.isNotBlank()),
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(10.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = T.Plate,
                    contentColor = T.Pick,
                ),
            ) {
                if (busy) {
                    CircularProgressIndicator(
                        strokeWidth = 2.dp,
                        color = T.Pick,
                        modifier = Modifier.height(16.dp),
                    )
                } else {
                    Text("Connect")
                }
            }

            Button(
                onClick = onOpenReadiness,
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(10.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = T.Plate,
                    contentColor = T.Dim,
                ),
            ) { Text("Platform checks") }
        }

        Spacer(Modifier.height(28.dp))
    }
}

@Composable
internal fun fieldColors() = OutlinedTextFieldDefaults.colors(
    focusedTextColor = T.Ink,
    unfocusedTextColor = T.Ink,
    focusedBorderColor = T.Pick,
    unfocusedBorderColor = T.Line,
    focusedContainerColor = T.Plate,
    unfocusedContainerColor = T.Plate,
    cursorColor = T.Pick,
)
