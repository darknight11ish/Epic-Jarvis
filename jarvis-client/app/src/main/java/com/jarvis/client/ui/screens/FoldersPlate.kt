package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
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
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Folders
import com.jarvis.client.net.NotionImport
import com.jarvis.client.net.Upload
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Folders Jarvis may look in" on Settings ([Folders], the owner's decisions
 * of 2026-09-26) - the desktop's Settings -> Folders Jarvis may look in, in
 * the same words.
 *
 * The list, the PC's line about reading PDF and Word files, and Remove on
 * each folder - at once, never held on a stale link. No Add: it is the PC's
 * alone (the PC refuses it from the phone), and the PC's own line says where.
 *
 * TWO DOORS OF ITS OWN, since the owner's ask of 2026-11-05:
 *  - **Send a document or a photo** ([Upload]): pick a document or a photo,
 *    choose one of the listed folders, and the PC puts it in `From my phone`
 *    inside that folder after its ONE card. A photo is a PLAIN FILE COPY - it
 *    is not the chat picture path, and no model is shown it (2026-11-13). The
 *    folder list is the PC's own (`GET /api/folders`), so the phone can only
 *    use a grant the owner already gave.
 *  - **Bring in a Notion export** ([NotionImport]): the owner exports from
 *    Notion himself and picks the `.zip`; the phone sends it to the PC, which
 *    plans the import, then asks for ONE card and writes the vault.
 *
 * Both are WRITES, so both are held on a stale link (rule 4) - the buttons are
 * disabled and the plate says why. Nothing here keeps a byte: the file is read
 * from Android's provider and streamed, and the outcome is one plain sentence.
 * A PC without the routes answers 404, and the door says so and sends nothing
 * ([Upload.NOT_HERE], [NotionImport.NOT_HERE]).
 */
@Composable
internal fun FoldersSection(
    canAct: Boolean = false,
    /** Launches the document picker for ONE listed folder's path, or null in a preview. */
    onSendDocument: ((String) -> Unit)? = null,
    /** Launches the `.zip` picker for ONE vault id, or null in a preview. */
    onPickNotionZip: ((String) -> Unit)? = null,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Folders.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    /** True while the owner is choosing which listed folder to send into. */
    var choosingFolder by remember { mutableStateOf(false) }

    // A folder's card answered on the PC changes the list: read it again when
    // the approval queue changes, as the desktop does (onQueue).
    val queue by JarvisRuntime.pending.collectAsState()
    val queueKey = queue.map { it.id }

    // The transfer's own state lives in the runtime, so leaving this screen
    // (or turning the phone) does not abandon a file that is already going.
    val uploadNow by JarvisRuntime.uploadNow.collectAsState()
    val uploadSaid by JarvisRuntime.uploadSaid.collectAsState()
    val notionNow by JarvisRuntime.notionNow.collectAsState()
    val notionBusy by JarvisRuntime.notionBusy.collectAsState()

    LaunchedEffect(reads, queueKey) {
        when (val r = JarvisRuntime.folders()) {
            is ApiResult.Ok -> {
                val v = Folders.parse(r.value)
                if (v == null) missing = true else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Folders.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    val sending = uploadNow != null
    Section(Folders.TITLE, trailing = {
        Quiet("Refresh", onClick = {
            reads += 1
            JarvisRuntime.clearUploadSaid()
        })
    }) {
        Plate {
            val v = view
            val err = readError
            when {
                missing -> Text(Folders.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                v == null -> Text(
                    if (err != null) "Couldn't ask Jarvis which folders it may look in: $err"
                    else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    Text(v.detail, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    if (v.folders.isEmpty()) {
                        Gap(8)
                        Text(v.why.ifEmpty { v.empty }, style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid)
                    }
                    v.folders.forEach { f ->
                        Gap(8)
                        Column {
                            Text(f.name, style = MaterialTheme.typography.titleSmall,
                                color = chrome.textHi)
                            Folders.lines(f).forEach {
                                Text(it, style = MaterialTheme.typography.labelSmall,
                                    color = if (it == Folders.NOT_HERE) chrome.warnInk else chrome.textMid)
                            }
                            // Removing only lets Jarvis see less: never held.
                            Quiet(v.removeLabel, enabled = !busy, onClick = {
                                if (!busy) {
                                    busy = true
                                    said = null
                                    scope.launch {
                                        try {
                                            said = JarvisRuntime.removeFolder(f.path)
                                        } finally {
                                            busy = false
                                            reads += 1
                                        }
                                    }
                                }
                            })
                        }
                    }
                    if (v.waiting.isNotEmpty()) {
                        Gap(6)
                        Text("${v.waitingWords} (${v.waiting})",
                            style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
                    }
                    Gap(8)
                    Text(v.phoneAdd, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                    if (v.documentsSaid.isNotEmpty()) {
                        Gap(4)
                        Text(v.documentsSaid, style = MaterialTheme.typography.labelSmall,
                            color = if (v.documentsReady) chrome.okInk else chrome.textMid)
                    }
                    said?.let {
                        Gap(6)
                        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }

                    // --------------------------------------- send a document ---
                    Gap(14)
                    Text(Upload.TITLE, style = MaterialTheme.typography.titleSmall,
                        color = chrome.textHi)
                    Gap(2)
                    Text(Upload.DETAIL, style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo)
                    Gap(6)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Quiet(
                            Upload.TITLE,
                            enabled = canAct && !sending && v.folders.isNotEmpty() &&
                                onSendDocument != null,
                            onClick = {
                                JarvisRuntime.clearUploadSaid()
                                choosingFolder = !choosingFolder
                            },
                        )
                        if (sending && uploadNow?.waiting == true) {
                            Spacer(Modifier.width(8.dp))
                            Text("Waiting on the PC…", style = MaterialTheme.typography.labelSmall,
                                color = chrome.warnInk)
                        }
                    }
                    val now = uploadNow
                    if (now != null) {
                        Gap(4)
                        Text(
                            if (now.waiting) Upload.waitingLine(now.name)
                            else if (now.total <= 0) Upload.preparing(now.name)
                            else Upload.progress(now.name, now.sent, now.total),
                            style = MaterialTheme.typography.labelSmall,
                            color = if (now.waiting) chrome.warnInk else chrome.textMid,
                        )
                    }
                    if (choosingFolder) {
                        Gap(4)
                        Text("Choose the folder to send into:", style = MaterialTheme.typography.labelSmall,
                            color = chrome.textMid)
                        v.folders.forEach { f ->
                            Quiet("Send into ${f.name}", enabled = canAct && !sending) {
                                choosingFolder = false
                                onSendDocument?.invoke(f.path)
                            }
                        }
                        Quiet(NotionImport.CANCEL, enabled = !sending) { choosingFolder = false }
                    }
                    uploadSaid?.let {
                        Gap(6)
                        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    if (!canAct) {
                        Gap(4)
                        Text(Upload.OFFLINE, style = MaterialTheme.typography.labelSmall,
                            color = chrome.textLo)
                    }

                    // --------------------------------- bring in a Notion export ---
                    Gap(14)
                    Text(v.notionTitle.ifBlank { NotionImport.TITLE },
                        style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
                    Gap(2)
                    Text(
                        v.notionDetail.ifBlank { NotionImport.HOW },
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                    Gap(6)
                    Quiet(
                        NotionImport.TITLE,
                        enabled = canAct && !sending && !notionBusy && onPickNotionZip != null,
                        onClick = { JarvisRuntime.loadNotionVaults() },
                    )
                    if (notionBusy && notionNow == null) {
                        Gap(4)
                        Text(NotionImport.CHECKING, style = MaterialTheme.typography.labelSmall,
                            color = chrome.textLo)
                    }
                    when (val n = notionNow) {
                        is JarvisRuntime.NotionNow.Vaults -> {
                            Gap(6)
                            Text(NotionImport.CHOOSE_VAULT, style = MaterialTheme.typography.labelSmall,
                                color = chrome.textMid)
                            n.vaults.forEach { vault ->
                                Quiet(vault.name, enabled = canAct && !sending && onPickNotionZip != null) {
                                    JarvisRuntime.clearNotion()
                                    onPickNotionZip?.invoke(vault.id)
                                }
                            }
                            n.said.takeIf { it.isNotBlank() }?.let {
                                Gap(4)
                                Text(it, style = MaterialTheme.typography.labelSmall,
                                    color = chrome.textLo)
                            }
                            Quiet(NotionImport.CANCEL, enabled = true) { JarvisRuntime.clearNotion() }
                        }
                        is JarvisRuntime.NotionNow.Plan -> {
                            Gap(6)
                            Text(NotionImport.planSentence(n.plan),
                                style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                            Gap(4)
                            Text(NotionImport.promise(), style = MaterialTheme.typography.labelSmall,
                                color = chrome.textLo)
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Quiet(NotionImport.CONFIRM, enabled = canAct && !notionBusy) {
                                    JarvisRuntime.confirmNotionImport()
                                }
                                Spacer(Modifier.width(8.dp))
                                Quiet(NotionImport.CANCEL, enabled = !notionBusy) {
                                    JarvisRuntime.clearNotion()
                                }
                            }
                        }
                        is JarvisRuntime.NotionNow.Said -> {
                            Gap(6)
                            Text(n.text, style = MaterialTheme.typography.bodySmall,
                                color = chrome.textMid)
                            Quiet(NotionImport.CANCEL, enabled = !notionBusy) {
                                JarvisRuntime.clearNotion()
                            }
                        }
                        null -> {}
                    }
                }
            }
        }
    }
}
