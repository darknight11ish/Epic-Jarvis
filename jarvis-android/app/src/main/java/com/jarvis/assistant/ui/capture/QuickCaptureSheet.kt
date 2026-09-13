package com.jarvis.assistant.ui.capture

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import com.jarvis.assistant.network.QuickNoteMessage
import com.jarvis.assistant.ui.theme.JarvisAmber
import com.jarvis.assistant.ui.theme.JarvisBlack
import com.jarvis.assistant.ui.theme.JarvisCyan
import com.jarvis.assistant.ui.theme.JarvisGreen
import com.jarvis.assistant.ui.theme.JarvisOutline
import com.jarvis.assistant.ui.theme.JarvisSurface
import com.jarvis.assistant.ui.theme.JarvisTextMuted

enum class CaptureTarget(val wire: String, val label: String) {
    LOGSEQ(QuickNoteMessage.TARGET_LOGSEQ, "Logseq Journal"),
    JOPLIN(QuickNoteMessage.TARGET_JOPLIN, "Joplin Vault"),
}

/**
 * Frictionless capture: open, type, send.
 *
 * The point is to outrun the thought, so the keyboard is up on arrival and the
 * send path never blocks on the network — an offline note is queued and
 * acknowledged rather than refused.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun QuickCaptureSheet(
    connected: Boolean,
    initialText: String = "",
    initialTarget: CaptureTarget = CaptureTarget.LOGSEQ,
    micActive: Boolean,
    micPermissionGranted: Boolean,
    queuedCount: Int,
    onSend: (CaptureTarget, String) -> Unit,
    onToggleMic: () -> Unit,
    onDismiss: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val focusRequester = remember { FocusRequester() }

    var target by rememberSaveable(initialTarget) { mutableStateOf(initialTarget) }
    // Keyed on the seed so a fresh share replaces the field rather than
    // appending to whatever the last capture left behind.
    var text by rememberSaveable(initialText) { mutableStateOf(initialText) }

    LaunchedEffect(Unit) {
        // The sheet has to be laid out before the field can take focus.
        runCatching { focusRequester.requestFocus() }
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = JarvisBlack,
        scrimColor = JarvisBlack.copy(alpha = 0.7f),
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp)
                .navigationBarsPadding()
                .imePadding(),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = "QUICK CAPTURE",
                    style = MaterialTheme.typography.labelSmall,
                    color = JarvisTextMuted,
                    modifier = Modifier.weight(1f),
                )
                if (!connected) {
                    Text(
                        text = if (queuedCount > 0) "OFFLINE · $queuedCount QUEUED" else "OFFLINE",
                        style = MaterialTheme.typography.labelSmall,
                        color = JarvisAmber,
                    )
                }
            }

            Spacer(Modifier.height(10.dp))

            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                CaptureTarget.entries.forEachIndexed { index, option ->
                    SegmentedButton(
                        selected = target == option,
                        onClick = { target = option },
                        shape = SegmentedButtonDefaults.itemShape(
                            index = index,
                            count = CaptureTarget.entries.size,
                        ),
                        colors = SegmentedButtonDefaults.colors(
                            activeContainerColor = JarvisCyan.copy(alpha = 0.16f),
                            activeContentColor = JarvisCyan,
                            activeBorderColor = JarvisCyan,
                            inactiveContainerColor = JarvisSurface,
                            inactiveContentColor = JarvisTextMuted,
                            inactiveBorderColor = JarvisOutline,
                        ),
                    ) {
                        Text(option.label, style = MaterialTheme.typography.labelSmall)
                    }
                }
            }

            Spacer(Modifier.height(12.dp))

            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 120.dp)
                    .focusRequester(focusRequester),
                placeholder = {
                    Text(
                        text = if (target == CaptureTarget.LOGSEQ) {
                            "Appends to today's journal"
                        } else {
                            "Creates a note in your vault"
                        },
                        style = MaterialTheme.typography.bodyMedium,
                    )
                },
                textStyle = MaterialTheme.typography.bodyMedium,
                keyboardOptions = KeyboardOptions(
                    capitalization = KeyboardCapitalization.Sentences,
                    imeAction = ImeAction.Default,
                ),
                shape = RoundedCornerShape(12.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = JarvisCyan,
                    unfocusedBorderColor = JarvisOutline,
                    focusedContainerColor = JarvisSurface,
                    unfocusedContainerColor = JarvisSurface,
                ),
            )

            Spacer(Modifier.height(12.dp))

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = onToggleMic,
                    enabled = micPermissionGranted,
                    modifier = Modifier.height(52.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (micActive) JarvisCyan else JarvisSurface,
                        contentColor = if (micActive) JarvisBlack else JarvisCyan,
                        disabledContainerColor = JarvisSurface,
                        disabledContentColor = JarvisTextMuted,
                    ),
                ) {
                    Text(
                        text = if (micActive) "STOP" else "TALK",
                        style = MaterialTheme.typography.labelSmall,
                    )
                }

                Spacer(Modifier.width(0.dp))

                Button(
                    onClick = {
                        onSend(target, text.trim())
                        text = ""
                        onDismiss()
                    },
                    enabled = text.isNotBlank(),
                    modifier = Modifier
                        .weight(1f)
                        .height(52.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = JarvisGreen.copy(alpha = 0.18f),
                        contentColor = JarvisGreen,
                        disabledContainerColor = JarvisSurface,
                        disabledContentColor = JarvisTextMuted,
                    ),
                ) {
                    Text(
                        text = if (connected) "Send to Jarvis" else "Queue for Jarvis",
                        style = MaterialTheme.typography.titleMedium,
                    )
                }
            }

            Spacer(Modifier.height(20.dp))
        }
    }
}
