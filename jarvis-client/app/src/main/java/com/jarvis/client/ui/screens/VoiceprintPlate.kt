package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.jarvis.client.net.WriteLikeMe

/**
 * "Write like me", drawn under the existing "How Jarvis talks" card by
 * [MannerPlate]'s `MannerSection` - the same card the desktop puts it in
 * (JARVIS-API section 133). The state and the calls come from `MannerSection`
 * ([com.jarvis.client.JarvisRuntime.voiceprint] and friends), which holds each
 * write on a stale link.
 *
 * Renderer only: the values and every call arrive as parameters, so all the
 * rules here can be read in one file. Each tap is ONE change; Forget opens the
 * "are you sure?" dialog and only the dialog's yes calls `onForget`. No
 * approval card is raised anywhere: this is a local setting, and the PC's
 * route is loopback-only.
 */
@Composable
internal fun VoiceprintPlate(
    canAct: Boolean,
    view: WriteLikeMe.View?,
    busy: Boolean,
    said: String?,
    onToggle: (Boolean) -> Unit,
    onAdd: (String) -> Unit,
    onForget: (WriteLikeMe.Sample) -> Unit,
) {
    var draft by remember { mutableStateOf("") }
    var pendingForget by remember { mutableStateOf<WriteLikeMe.Sample?>(null) }
    var problem by remember { mutableStateOf<String?>(null) }

    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
        Text(WriteLikeMe.TITLE, style = MaterialTheme.typography.titleMedium)
        Text(WriteLikeMe.DETAIL, style = MaterialTheme.typography.bodySmall)
        Row(
            modifier = Modifier.fillMaxWidth()
                .toggleable(
                    value = view?.enabled == true,
                    enabled = canAct && !busy,
                    role = Role.Switch,
                    onValueChange = { onToggle(it) },
                )
                .padding(vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(WriteLikeMe.SWITCH_LABEL, modifier = Modifier.weight(1f))
            Switch(
                checked = view?.enabled == true,
                onCheckedChange = { onToggle(it) },
                enabled = canAct && !busy,
            )
        }
        Text(WriteLikeMe.SWITCH_DETAIL, style = MaterialTheme.typography.bodySmall)
        OutlinedTextField(
            value = draft,
            onValueChange = { draft = it; problem = null },
            label = { Text("A message you wrote") },
            supportingText = { Text(problem ?: WriteLikeMe.SAMPLE_HINT) },
            isError = problem != null,
            enabled = canAct && !busy,
            modifier = Modifier.fillMaxWidth(),
            maxLines = 6,
        )
        Button(
            enabled = canAct && !busy && draft.isNotBlank(),
            onClick = {
                val why = WriteLikeMe.sampleProblem(draft)
                if (why != null) problem = why else {
                    onAdd(draft.trim())
                    draft = ""
                    problem = null
                }
            },
        ) { Text("Keep this sample") }
        said?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
        val samples = view?.samples.orEmpty()
        if (samples.isEmpty()) {
            Text(WriteLikeMe.EMPTY, style = MaterialTheme.typography.bodySmall)
        }
        for (sample in samples) {
            Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(sample.text, modifier = Modifier.weight(1f))
                TextButton(
                    enabled = canAct && !busy,
                    onClick = { pendingForget = sample },
                ) { Text(WriteLikeMe.FORGET_LABEL) }
            }
        }
    }

    // The owner kept the question (2026-09-24): forgetting cannot be undone.
    val asking = pendingForget
    if (asking != null) {
        AlertDialog(
            onDismissRequest = { pendingForget = null },
            title = { Text("Forget this sample?") },
            text = { Text(WriteLikeMe.forgetAsk(asking)) },
            confirmButton = {
                TextButton(onClick = {
                    val sample = asking
                    pendingForget = null
                    onForget(sample)
                }) { Text("Forget") }
            },
            dismissButton = {
                TextButton(onClick = { pendingForget = null }) { Text("Keep it") }
            },
        )
    }
}
