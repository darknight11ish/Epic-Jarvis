package com.jarvis.client.ui.screens

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Backup
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Backups" ([Backup], the owner's decision of 2026-09-27) - read-only on
 * the phone, on purpose. Choosing a folder, backing up now, seeing a
 * recovery code and restoring all happen on the PC, in Jarvis Desktop's
 * Settings - Windows' own folder picker, and restoring needs Windows Hello
 * there (docs/ARCHITECTURE.md section 8). This shows only when the last
 * backup was made.
 */
@Composable
internal fun BackupSection() {
    val chrome = LocalChrome.current
    var reads by remember { mutableIntStateOf(0) }
    var status by remember { mutableStateOf<Backup.Status?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.backup()) {
            is ApiResult.Ok -> {
                val v = Backup.parse(r.value)
                if (v == null) missing = true else {
                    status = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Backup.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    Section(Backup.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(Backup.DETAIL, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            val v = status
            val err = readError
            when {
                missing -> Text(Backup.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                v == null -> Text(
                    if (err != null) "Couldn't read it: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    Text(Backup.line(v), style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                    if (v.pendingDeleteOlder) {
                        Gap(4)
                        Text("A card to delete older backups is waiting on your PC.",
                            style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                    } else if (!v.lastDeleteOlder?.message.isNullOrBlank()) {
                        Gap(4)
                        Text(v.lastDeleteOlder!!.message!!, style = MaterialTheme.typography.bodySmall,
                            color = if (v.lastDeleteOlder.outcome == "deleted") chrome.okInk else chrome.textMid)
                    }
                    if (!v.eraseLimit.isNullOrBlank()) {
                        Gap(6)
                        Text(v.eraseLimit, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        Gap(4)
                        Text("To delete older backup copies now, use Delete older backups in Jarvis Desktop (Settings > Backups).",
                            style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                }
            }
        }
    }
}
