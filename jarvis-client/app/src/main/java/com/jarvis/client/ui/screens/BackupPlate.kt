package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Backup
import com.jarvis.client.net.ScreenPlateText
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Backups" ([Backup], the owner's decision of 2026-09-27 for the feature; his
 * request of 2026-10-10, "a Back up now button on the phone", answered for real
 * on 2026-10-13; docs/JARVIS-API.md section 45).
 *
 * WHAT IT SHOWS. The state of the folder on the PC, read from
 * `GET /api/backup/status`: when the last backup was made, which folder it went
 * to (its last segment - never the whole path, which names the owner's Windows
 * account), how many are kept, and what the PC's own check of the newest file
 * found. The PC's sentences are drawn word for word ([Backup.checkLine] prefers
 * them) so the two apps cannot drift. A failed attempt is drawn too
 * ([Backup.attemptLine]) - a screen that only ever says "fine" is the one thing
 * this feature may not be.
 *
 * WHAT IT CAN DO. One control, "Back up now", and it is TWO calls on purpose
 * ([Backup]'s own comment has the whole reasoning). Tapping it asks the PC for
 * a backup (`prepare`), which mints this run's one-time recovery code and
 * writes NOTHING. The code is then shown full-screen, in four groups of five,
 * and the run CANNOT be finished until the owner ticks that he has saved it.
 * Only then does the phone say "write it" (`commit`) and the PC writes the file.
 *
 * WHY THE CODE IS DRAWN THIS LOUDLY. A backup is locked with its own code, the
 * code is stored nowhere, and a new backup deletes the oldest of five. So a run
 * whose code was never read would not just add a file nobody can open - it
 * would push out an older backup whose own code still works. The tick is the
 * fix: no tick, no file, and the folder is exactly as it was.
 *
 * THE ONE THING IT CANNOT DO, said on the screen ([Backup.checkLine]'s limit):
 * nothing here can prove a backup OPENS. Only the recovery code opens one, and
 * codes are only ever typed on the PC. A pass here means the file is complete
 * and well formed - not "this backup works".
 *
 * What stays the PC's alone: choosing the folder, restoring, and deleting older
 * copies (docs/ARCHITECTURE.md section 8). The phone also never holds a code
 * anywhere but this screen's own state, and never logs it.
 *
 * @param canAct the link is up and fresh. [commitBackup] is held on it, because
 *   it is the call that writes into the PC's folder; ASKING for a backup is
 *   not held, because it writes nothing anywhere.
 */
@Composable
internal fun BackupSection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var status by remember { mutableStateOf<Backup.Status?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var asking by remember { mutableStateOf(false) }
    var writing by remember { mutableStateOf(false) }
    // The run in hand: the code the PC minted and the id it goes back with.
    // Held HERE and nowhere else - never a store, never a log.
    var run by remember { mutableStateOf<Backup.Prepared?>(null) }
    var said by remember { mutableStateOf<String?>(null) }
    val tick by JarvisRuntime.backupTick.collectAsState()

    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.backupStatus()) {
            is ApiResult.Ok -> {
                val v = Backup.parse(r.value)
                if (v == null) {
                    missing = true
                } else {
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
                missing -> Text(
                    Backup.MISSING,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
                v == null -> Text(
                    if (err != null) "Couldn't read it: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    // When and how much, in the PC's own numbers.
                    Text(
                        Backup.line(v),
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textHi,
                        modifier = Modifier.liveStatus(),
                    )
                    Backup.folderLine(v)?.let {
                        Gap(2)
                        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    Backup.keptLine(v)?.let {
                        Gap(2)
                        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    // What the PC's check of the newest file found, in the PC's
                    // own sentence, and then the limit of that check said
                    // plainly rather than left to be assumed.
                    val check = v.check
                    if (check != null && v.lastBackupAt != null) {
                        Gap(6)
                        Text(
                            Backup.checkLine(v).orEmpty(),
                            style = MaterialTheme.typography.bodySmall,
                            color = if (Backup.verifies(v)) chrome.textHi else chrome.warnInk,
                            modifier = Modifier.liveStatus(),
                        )
                        if (check.limit.isNotBlank()) {
                            Gap(2)
                            Text(
                                check.limit,
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textLo,
                            )
                        }
                    }
                    // A run that FAILED, said rather than swallowed.
                    val attempt = v.attempt
                    if (attempt != null && !attempt.ok) {
                        Gap(6)
                        Text(
                            Backup.attemptLine(v).orEmpty(),
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.warnInk,
                            modifier = Modifier.liveStatus(),
                        )
                    }
                }
            }

            Gap(10)
            Text(
                Backup.CODE_WARNING,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.warnInk,
            )

            // The one control. It asks; it does not write. The write happens
            // when the code has been shown and kept, one screen below.
            Gap(10)
            Primary(
                text = if (asking) "Asking your PC…" else "Back up now",
                modifier = Modifier.fillMaxWidth(),
                enabled = !asking && !writing && run == null && !missing,
                busy = asking,
                onClick = {
                    if (!asking && run == null) {
                        asking = true
                        said = null
                        scope.launch {
                            try {
                                when (val a = JarvisRuntime.prepareBackup()) {
                                    is Backup.Asked.Ready -> run = a.prepared
                                    is Backup.Asked.Refused -> said = a.words
                                }
                            } finally {
                                asking = false
                            }
                        }
                    }
                },
            )
            if (run == null) {
                Gap(4)
                Text(
                    Backup.NEEDS_THE_PC,
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
            said?.let {
                Gap(6)
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.warnInk,
                    modifier = Modifier.liveStatus(),
                )
            }
        }
    }

    // The code, full screen, and the run cannot be finished without the tick.
    // A dialog rather than a strip: a code that can be scrolled past is a code
    // that gets missed, and a missed code is an unopenable backup.
    run?.let { prepared ->
        RecoveryCodeDialog(
            prepared = prepared,
            canAct = canAct && !writing,
            writing = writing,
            onFinish = {
                if (!writing) {
                    writing = true
                    said = null
                    scope.launch {
                        try {
                            val words = JarvisRuntime.commitBackup(prepared.id, prepared.code)
                            said = words
                            // A code with no file behind it is a code shown for
                            // nothing; keep the screen open so the words can be
                            // read, and let the next read say what landed.
                            run = null
                            reads += 1
                        } finally {
                            writing = false
                        }
                    }
                }
            },
            onCancel = {
                // Nothing was written; there is nothing to undo. The PC drops
                // the run on its own when the next ask arrives or it expires.
                run = null
                said = "Cancelled. Nothing was written to your PC, and your backups are " +
                    "exactly as they were."
            },
        )
    }
}

/**
 * The recovery code, in the owner's face: four groups of five, selectable so it
 * can be copied, with the warning above it and a tick that must be set before
 * the write can happen. Dismissing it writes nothing.
 */
@Composable
private fun RecoveryCodeDialog(
    prepared: Backup.Prepared,
    canAct: Boolean,
    writing: Boolean,
    onFinish: () -> Unit,
    onCancel: () -> Unit,
) {
    val chrome = LocalChrome.current
    var saved by remember { mutableStateOf(false) }
    val clipboard = LocalClipboardManager.current

    Dialog(
        onDismissRequest = { if (!writing) onCancel() },
        // Not dismissible by a stray tap outside: the whole point of this
        // screen is that the code is read before anything is written.
        properties = DialogProperties(dismissOnClickOutside = false),
    ) {
        Plate {
            Column(modifier = Modifier.heightIn(max = 520.dp).verticalScroll(rememberScrollState())) {
                Text(
                    "Recovery code for this backup",
                    style = MaterialTheme.typography.titleSmall,
                    color = chrome.textHi,
                )
                Gap(6)
                Text(
                    Backup.CODE_NOW,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.warnInk,
                )
                Gap(12)
                Text(
                    prepared.code,
                    // Big, monospaced and letter-spaced: a code that is
                    // misread is a backup that cannot be opened.
                    style = MaterialTheme.typography.headlineSmall.copy(
                        fontFamily = FontFamily.Monospace,
                        letterSpacing = 2.sp,
                    ),
                    color = chrome.textHi,
                    modifier = Modifier
                        .fillMaxWidth()
                        // One node for TalkBack, so the code is read out as the
                        // one thing it is rather than four loose groups.
                        .semantics(mergeDescendants = true) {}
                        .background(chrome.surface1)
                        .padding(12.dp),
                )
                Gap(6)
                Quiet("Copy the code", onClick = {
                    clipboard.setText(AnnotatedString(prepared.code))
                })
                Gap(6)
                Text(
                    prepared.words,
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textMid,
                )
                Gap(12)
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .toggleable(value = saved, enabled = canAct && !writing,
                            onValueChange = { saved = it }),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.Start,
                ) {
                    Checkbox(checked = saved, onCheckedChange = null, enabled = canAct && !writing)
                    Gap(4)
                    Text(
                        Backup.SAVED_TICK,
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textHi,
                    )
                }
                Gap(10)
                Primary(
                    text = if (writing) "Writing it on your PC…" else Backup.COMMIT_LABEL,
                    modifier = Modifier.fillMaxWidth(),
                    // The tick is the gate: without it there is no way to write
                    // a file whose code has not been read.
                    enabled = saved && canAct && !writing,
                    busy = writing,
                    onClick = onFinish,
                )
                Gap(6)
                Quiet(
                    Backup.CANCEL_LABEL,
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !writing,
                    onClick = onCancel,
                )
                Gap(6)
                if (!canAct) {
                    Text(
                        ScreenPlateText.WAITING_LINK,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                }
                Gap(6)
                Text(
                    Backup.DONE_LEAD,
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
    }
}
