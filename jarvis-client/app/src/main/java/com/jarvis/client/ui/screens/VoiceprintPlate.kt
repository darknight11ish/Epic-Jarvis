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
import com.jarvis.client.net.Voiceprint

/**
 * "Write like me", shown under the existing "How Jarvis talks" section
 * ([MannerPlate]'s `MannerSection`) once the Lead clears the wiring. NEW FILE:
 * `SettingsScreen.kt` is not edited yet - the exact hunk is in the PR body.
 *
 * Renderer only: the values and all four calls arrive as parameters, so this
 * file compiles now and the wiring decides where they come from. Each tap is
 * ONE change; Forget opens the "are you sure?" dialog and only the dialog's
 * yes calls `onForget`. No approval card is raised anywhere: this is a local
 * setting, and the PC's route is loopback-only.
 */
@Composable
internal fun VoiceprintPlate(
    canAct: Boolean,
    view: Voiceprint.View?,
    busy: Boolean,
    said: String?,
    onToggle: (Boolean) -> Unit,
    onAdd: (String) -> Unit,
    onForget: (Voiceprint.Sample) -> Unit,
) {
    var draft by remember { mutableStateOf("") }
    var pendingForget by remember { mutableStateOf<Voiceprint.Sample?>(null) }
    var problem by remember { mutableStateOf<String?>(null) }

    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
        Text(Voiceprint.TITLE, style = MaterialTheme.typography.titleMedium)
        Text(Voiceprint.DETAIL, style = MaterialTheme.typography.bodySmall)
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
            Text(Voiceprint.SWITCH_LABEL, modifier = Modifier.weight(1f))
            Switch(
                checked = view?.enabled == true,
                onCheckedChange = { onToggle(it) },
                enabled = canAct && !busy,
            )
        }
        Text(Voiceprint.SWITCH_DETAIL, style = MaterialTheme.typography.bodySmall)
        OutlinedTextField(
            value = draft,
            onValueChange = { draft = it; problem = null },
            label = { Text("A message you wrote") },
            supportingText = { Text(problem ?: Voiceprint.SAMPLE_HINT) },
            isError = problem != null,
            enabled = canAct && !busy,
            modifier = Modifier.fillMaxWidth(),
            maxLines = 6,
        )
        Button(
            enabled = canAct && !busy && draft.isNotBlank(),
            onClick = {
                val why = Voiceprint.sampleProblem(draft)
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
            Text(Voiceprint.EMPTY, style = MaterialTheme.typography.bodySmall)
        }
        for (sample in samples) {
            Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(sample.text, modifier = Modifier.weight(1f))
                TextButton(
                    enabled = canAct && !busy,
                    onClick = { pendingForget = sample },
                ) { Text(Voiceprint.FORGET_LABEL) }
            }
        }
    }

    // The owner kept the question (2026-09-24): forgetting cannot be undone.
    val asking = pendingForget
    if (asking != null) {
        AlertDialog(
            onDismissRequest = { pendingForget = null },
            title = { Text("Forget this sample?") },
            text = { Text(Voiceprint.forgetAsk(asking)) },
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
