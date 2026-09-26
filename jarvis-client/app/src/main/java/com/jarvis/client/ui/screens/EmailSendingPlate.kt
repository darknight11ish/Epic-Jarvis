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
import com.jarvis.client.net.EmailSending
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Sending email" on Mind ([EmailSending], the owner's decision of
 * 2026-09-25) - the desktop's Settings -> Sending email, in the same words.
 *
 * One line, the PC's own: whether Jarvis can send email, from which address
 * and through which server - never the password. Nothing to change here: the
 * account is set on the PC, and every email is its own approval card, shown
 * in full in the approval list like any other card.
 */
@Composable
internal fun EmailSendingSection() {
    val chrome = LocalChrome.current
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<EmailSending.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.emailSending()) {
            is ApiResult.Ok -> {
                val v = EmailSending.parse(r.value)
                if (v == null) missing = true else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (EmailSending.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    Section(EmailSending.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(EmailSending.NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            val v = view
            val err = readError
            when {
                missing -> Text(EmailSending.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                v == null -> Text(
                    if (err != null) "Couldn't read whether Jarvis can send email: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> Text(v.said, style = MaterialTheme.typography.bodySmall,
                    color = if (v.ready) chrome.okInk else chrome.textMid)
            }
        }
    }
}
