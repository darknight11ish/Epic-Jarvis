package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.data.NotificationAllowListStore
import com.jarvis.client.data.ScreenNever
import com.jarvis.client.data.Security
import com.jarvis.client.net.ScreenPlateText
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Looking at your screen" on the Security screen (the owner's decision of
 * 2026-09-28, docs/SCREEN-DESIGN.md sections 3 and 4): the one switch that
 * lets the phone's assistant gesture read the words on the screen in front,
 * and the phone's "Never look at" list.
 *
 * Like everything on [SecurityScreen], this hands the WHOLE new settings
 * record to [onChange] and saves nothing itself: turning the switch ON, and
 * taking an app OFF the list, are loosenings and wait for the fingerprint or
 * PIN ([com.jarvis.client.data.SecurityRules.loosens]); turning it off and
 * adding an app are instant. The words are [ScreenNever]'s, so a test holds
 * them.
 */
@Composable
internal fun LookSection(
    security: Security,
    busy: Boolean,
    onChange: (Security) -> Unit,
) {
    val chrome = LocalChrome.current
    Section("Looking at your screen") {
        Plate {
            SwitchRow(
                title = ScreenNever.SETTING_TITLE,
                detail = ScreenNever.SETTING_DETAIL,
                checked = security.screenRead,
                enabled = !busy,
                onChange = { onChange(security.copy(screenRead = it)) },
            )
            Gap(6)
            Text(ScreenPlateText.LOOK_POINTER, style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
            Gap(12)
            Text(ScreenNever.LIST_TITLE, style = MaterialTheme.typography.labelLarge, color = chrome.textHi)
            Gap(4)
            Text(ScreenNever.LIST_DETAIL, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            Gap(8)
            NeverList(security, busy, onChange)
        }
    }
}

@Composable
private fun NeverList(security: Security, busy: Boolean, onChange: (Security) -> Unit) {
    val chrome = LocalChrome.current
    val context = LocalContext.current
    val store = remember { NotificationAllowListStore(context) }
    var picking by remember { mutableStateOf(false) }
    var query by remember { mutableStateOf("") }
    val listed = security.neverApps.sorted()

    if (listed.isEmpty()) {
        Text(ScreenNever.LIST_EMPTY, style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
    } else {
        listed.forEach { pkg ->
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                Text(
                    labelOf(context, pkg),
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textHi,
                    modifier = Modifier.weight(1f),
                )
                // A loosening: SecurityRules.loosens sees an app leave the list,
                // and the caller asks for the fingerprint or PIN first.
                Quiet(
                    "Remove",
                    modifier = Modifier.semantics { contentDescription = ScreenPlateText.removeLabel(labelOf(context, pkg)) },
                    enabled = !busy,
                    onClick = {
                        onChange(security.copy(neverApps = security.neverApps - pkg))
                    },
                )
            }
        }
    }
    Gap(8)
    Secondary(
        if (picking) "Close the list" else "Add an app",
        modifier = Modifier.fillMaxWidth(),
        enabled = !busy,
        onClick = { picking = !picking; query = "" },
    )
    if (picking) {
        Gap(8)
        val candidates = remember(security.neverApps) {
            store.installedApps(skipNotificationList = false)
                .filter { it.packageName !in security.neverApps }
                // Already always refused (password managers and bank-looking
                // apps): adding them would say nothing.
                .filter { ScreenNever.blocked(it.packageName, emptySet()) == null }
        }
        if (security.neverApps.size >= ScreenNever.MAX_APPS) {
            Text(
                "The list is full (${ScreenNever.MAX_APPS} apps).",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textLo,
            )
        } else if (candidates.isEmpty()) {
            Text("No other apps found to add.", style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
        } else {
            TextInput(value = query, onValueChange = { query = it }, placeholder = "Search apps")
            Gap(8)
            val shown = ScreenPlateText.filterApps(candidates, query, { it.label }, { it.packageName })
            if (shown.isEmpty()) {
                Text("No app matches that.", style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
            }
            LazyColumn(Modifier.fillMaxWidth().heightIn(max = 240.dp)) {
                items(shown, key = { it.packageName }) { app ->
                    Row(
                        Modifier.fillMaxWidth().heightIn(min = 48.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Text(
                            app.label,
                            style = MaterialTheme.typography.bodyMedium,
                            color = chrome.textHi,
                            modifier = Modifier.weight(1f),
                        )
                        // Adding is stricter, so it is instant.
                        Quiet(
                            "Add",
                            modifier = Modifier.semantics { contentDescription = ScreenPlateText.addLabel(app.label) },
                            enabled = !busy,
                            onClick = {
                                onChange(security.copy(neverApps = security.neverApps + app.packageName))
                                picking = false
                            },
                        )
                    }
                }
            }
        }
    }
}

/** The app's name as the owner knows it, or its package name when Android will not say. */
internal fun labelOf(context: android.content.Context, pkg: String): String = runCatching {
    val pm = context.packageManager
    pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString()
}.getOrNull()?.takeIf { it.isNotBlank() } ?: pkg
