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
 * "Backups" ([Backup], the owner's decision of 2026-09-27) - what a phone can
 * see, and plainly what it cannot.
 *
 * It shows one thing the PC tells a phone: when the last backup was made
 * ([Backup.line]). Making one, choosing the folder, restoring and deleting
 * older copies all happen on the PC, in Jarvis Desktop's Settings - Windows'
 * own folder picker, and a restore needs Windows Hello there
 * (docs/ARCHITECTURE.md section 8).
 *
 * THE OWNER ASKED FOR A "BACK UP NOW" BUTTON HERE (2026-10-10) and this screen
 * says why it is not here instead of drawing one that cannot work: the PC
 * refuses `/api/backup/now` from anything but itself, so a phone over Tailscale
 * or NordVPN Meshnet gets 403 every time ([Backup.PC_ONLY] has the words and
 * the evidence). The recovery code is named too ([Backup.CODE_WARNING]) - it
 * is shown once, on the PC, and a backup whose code is lost can never be
 * opened.
 *
 * The three lines this plate used to draw for a waiting delete-older card, the
 * last delete's outcome and the erase limit are GONE rather than left in
 * place: the PC sends those to this PC only, so on a phone they were branches
 * that could never run ([Backup]'s own comment).
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
                else -> Text(Backup.line(v), style = MaterialTheme.typography.bodySmall,
                    color = chrome.textHi)
            }
            // Said whichever way the read went: these two are the PC's own
            // rules, not the answer to a request that could have failed.
            Gap(8)
            Text(Backup.PC_ONLY, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            Gap(6)
            Text(Backup.CODE_WARNING, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }
    }
}
