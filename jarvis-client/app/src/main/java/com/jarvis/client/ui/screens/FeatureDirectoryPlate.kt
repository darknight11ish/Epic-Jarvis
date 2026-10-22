package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.jarvis.client.net.FeatureDirectory
import com.jarvis.client.net.FeatureSearch
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "All features and abilities" - the phone's searchable directory of the 139
 * features the PC knows about (jarvis_feature_guide.abilities_directory()).
 *
 * It is a DIRECTORY, not a control panel (owner ruling, 2026-10-22): every row
 * carries the PC's own label among exactly five, and only a row the PC says is
 * a real switch offers one. A Command-Only or Always-On row is drawn with its
 * example phrase and screen path and NO toggle; a PC-Only row says it is
 * changed on the PC; a multi-field row whose typed path is still being wired
 * says so plainly ("Settings control today; typed path still being wired").
 *
 * Everything shown comes from [FeatureDirectory] (generated from the PC's own
 * data - never hand-typed here). The search box filters with [FeatureSearch],
 * which is pure and tested on the JVM. Nothing here calls the PC.
 */
@Composable
internal fun FeatureDirectorySection() {
    val chrome = LocalChrome.current
    var query by remember { mutableStateOf("") }
    val rows = FeatureSearch.search(query)
    val labels = FeatureDirectory.LABELS

    Section("All features and abilities") {
        Plate {
            Text(
                "Every feature Jarvis knows about, in the PC's own words. " +
                    "A switch is only shown where the PC really has one - the rest " +
                    "say what they are and where to find them.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(8)
            TextInput(
                value = query,
                onValueChange = { query = it },
                placeholder = "Search abilities: voice, backup, timer, galaxy...",
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            )
            Gap(6)
            Text(
                if (query.isBlank()) "${rows.size} features"
                else "${rows.size} of ${FeatureDirectory.COUNT} features",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
            if (rows.isEmpty()) {
                Gap(8)
                Text(
                    "Nothing matches that. Try a word from a feature's name, " +
                        "or what you want to do.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
            }
            // Groups in the PC's own label order, so a label is never invented.
            for (label in labels) {
                val group = rows.filter { it.label == label }
                if (group.isEmpty()) continue
                Gap(14)
                Text(
                    label,
                    style = MaterialTheme.typography.labelMedium,
                    color = chrome.textMid,
                )
                for (row in group) {
                    Gap(10)
                    Column(Modifier.fillMaxWidth()) {
                        Text(
                            row.name,
                            style = MaterialTheme.typography.bodyMedium,
                            color = chrome.textHi,
                        )
                        Text(
                            row.why,
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid,
                        )
                        if (row.exampleWords.isNotBlank()) {
                            Text(
                                row.exampleWords,
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textLo,
                            )
                        }
                        Text(
                            row.settingsPath,
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textLo,
                        )
                        if (row.plannedWords.isNotBlank()) {
                            Text(
                                row.plannedWords,
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.warnInk,
                            )
                        }
                        // A switch row names its switch; nothing here draws a
                        // control, because this screen owns no setting and
                        // would be a fake toggle if it did.
                        if (row.isToggle && row.switchKeys.isNotEmpty()) {
                            Text(
                                "Switch: " + row.switchKeys.joinToString(", "),
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textLo,
                            )
                        }
                    }
                }
            }
            Gap(10)
            Text(
                "Only Settings changes a setting. This list never does; it says " +
                    "where the control is.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
        }
    }
}
