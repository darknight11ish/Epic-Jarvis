package com.jarvis.client.ui.screens

import android.content.ActivityNotFoundException
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Environment
import android.provider.MediaStore
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.SendFile
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch

/**
 * "File from your PC" - the phone half of the owner's ask of 2026-10-31:
 * *"am i able to ask jarvis to search for a file for me and send it to the
 * jarvis android app to view and or download directly? this would be a file on
 * the desktop"*. Backend and contract: `backend/jarvis_send_file.py`,
 * docs/JARVIS-API.md section 172; the shapes and the PC's sentences are
 * [com.jarvis.client.net.SendFile].
 *
 * THE CARD IS THE PC'S, NEVER THIS SCREEN'S. A file appears here only after
 * the owner approved Jarvis's own `send_file_to_phone` card on the PC; nothing
 * here can create, approve or extend one, and no path ever crosses the wire.
 * The two phone steps are the phone's own:
 *
 * - **View** hands the verified download to Android's viewer through a
 *   `FileProvider` (`ACTION_VIEW`, the right MIME type, a read grant for that
 *   one URI). The file is assembled in this app's private cache - the folder
 *   the provider exposes - so no other app can write there, and a small file
 *   still opens exactly as it did before the 2 GiB change. View is offered
 *   only at or under [SendFile.VIEW_MAX_BYTES] (200 MiB, Gemini's Q3); above
 *   that the row says [SendFile.VIEW_USE_SAVE] where the button would be, so a
 *   big video is never handed to a viewer to sit in this cache.
 * - **Save to Downloads** streams the verified file into the phone's own
 *   Downloads collection under `Downloads/Jarvis` through
 *   `MediaStore.Downloads`, and only after the whole file has arrived and its
 *   sha256 matched. This app's `minSdk` is 33, so that is the only path
 *   needed - there is no legacy external-files branch. The verified cache copy
 *   is deleted once the save lands, and any copy still in the cache when this
 *   plate leaves the screen is deleted too - except one this plate just handed
 *   to a viewer, which must not be pulled out from under it (Q3: "clean up
 *   cache copies promptly").
 *
 * A big file comes down in 1 MiB pieces with a progress line (bytes received
 * and percent) under its row; the buttons stay disabled until it is done. A
 * failure deletes the cache copy and says the PC's own sentence, or a plain
 * one - nothing partial is left in Downloads. The phone's own free-space
 * refusal comes back from the runtime before the first slice and is shown in
 * the same line as every other refusal.
 *
 * The PC's own rules are only STATED here, never reinterpreted: one file at a
 * time, 2 GiB, ten minutes, one completed transfer. A file over the PC's
 * `cap_bytes` is not fetched at all, and the row says why.
 *
 * While "Hide memory lists and chat history" is on the route is not even
 * asked ([JarvisRuntime.sendFiles] refuses): a file's name is the owner's
 * words, so this screen shows only [SendFile.HIDDEN_NAMES] then.
 */
@Composable
internal fun SendFileSection(canAct: Boolean, privateHidden: Boolean) {
    Section("File from your PC") {
        Plate {
            SendFileBody(canAct = canAct, privateHidden = privateHidden, compact = false)
        }
    }
}

/**
 * The same list as one small block, for the Coming up plate on Brain - the
 * visible place where a waiting file is actually noticed, rather than a row
 * the owner has to remember to open. Draws NOTHING unless a file is really
 * waiting, and nothing while the private lists are hidden, so a name never
 * leaks.
 */
@Composable
internal fun SendFileWaitingBlock(canAct: Boolean, privateHidden: Boolean) {
    if (privateHidden) return
    SendFileBody(canAct = canAct, privateHidden = false, compact = true)
}

/**
 * The list itself: the PC's sentence, each waiting file with View and Save to
 * Downloads, the progress line while a download runs, the PC's limits in one
 * line, and what the phone did. [compact] is the Coming up block's shape - no
 * heading, and nothing at all when there is nothing waiting.
 */
@Composable
private fun SendFileBody(canAct: Boolean, privateHidden: Boolean, compact: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var reply by remember { mutableStateOf<SendFile.ListReply?>(null) }
    var readError by remember { mutableStateOf<String?>(null) }
    var reads by remember { mutableIntStateOf(0) }
    var busyId by remember { mutableStateOf<String?>(null) }
    var said by remember { mutableStateOf<String?>(null) }
    // Written from the download's IO thread, read by composition: a
    // MutableStateFlow is safe to hand across the two, a Compose state write
    // is not what the runtime promises from a background dispatcher.
    val progress = remember { MutableStateFlow<SendFile.Progress?>(null) }
    val now by progress.collectAsState()

    LaunchedEffect(reads, privateHidden) {
        if (privateHidden) {
            reply = null
            readError = null
            return@LaunchedEffect
        }
        when (val r = JarvisRuntime.sendFiles()) {
            is ApiResult.Ok -> {
                reply = r.value
                readError = null
            }
            is ApiResult.Failed -> {
                reply = null
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }
    // A waiting file lives ten minutes: keep the list true while it is open,
    // but not while a download is running - the PC consumes the id on the last
    // slice, and a refresh then would snatch the row (and its progress line)
    // away while the phone is still checking the file it just received.
    LaunchedEffect(privateHidden) {
        while (true) {
            delay(SendFile.REFRESH_MS)
            if (!privateHidden && busyId == null) reads += 1
        }
    }
    // Q3: whatever is still in the app's cache when this plate goes is deleted
    // - a big file must not sit there once the owner has moved on. The runtime
    // keeps any file this plate just handed to another app's viewer, so a sweep
    // can never pull one out from under it.
    DisposableEffect(Unit) {
        onDispose { JarvisRuntime.sweepReceivedCopies() }
    }

    fun act(file: SendFile.Waiting, view: Boolean) {
        if (busyId != null) return
        val ready = reply as? SendFile.ListReply.Ready
        val cap = ready?.capBytes ?: SendFile.MAX_BYTES
        // The phone's own pre-check, from the PC's own `cap_bytes`: an over-cap
        // row is never fetched at all.
        if (!SendFile.fitsCap(file.sizeBytes, cap)) {
            said = SendFile.overCapWords(file.sizeBytes, cap)
            return
        }
        busyId = file.id
        said = null
        progress.value = null
        scope.launch {
            try {
                when (val r = JarvisRuntime.downloadFile(
                    id = file.id,
                    sizeBytes = file.sizeBytes,
                    chunkBytes = ready?.chunkBytes ?: SendFile.CHUNK_BYTES,
                    onProgress = { progress.value = it },
                )) {
                    is ApiResult.Ok -> when (val f = r.value) {
                        is SendFile.Fetched.Got -> said =
                            if (view) openReceived(context, f) else saveToDownloads(context, f)
                        is SendFile.Fetched.Refused -> said = f.said
                    }
                    is ApiResult.Failed -> said = JarvisRuntime.noticeFor(r.error)
                }
                // The id is consumed by a completed transfer: whatever happened,
                // the list is not what it was a moment ago.
                reads += 1
            } finally {
                progress.value = null
                busyId = null
            }
        }
    }

    // The compact block is part of Coming up: silent unless a file is waiting.
    if (compact) {
        val ready = reply as? SendFile.ListReply.Ready
        if (privateHidden || ready == null || ready.files.isEmpty()) return
    }

    if (!compact) {
        Text(
            "A file Jarvis sent from your PC, after you approved its own card. " +
                "View opens it here; Save to Downloads keeps a copy. A big file comes down " +
                "in pieces, and the line under its row shows how far it has got.",
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
        Gap(6)
    } else {
        Text(
            "File from your PC",
            style = MaterialTheme.typography.labelMedium,
            color = chrome.textMid,
        )
    }
    if (privateHidden) {
        Text(SendFile.HIDDEN_NAMES, style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid)
        return
    }
    val err = readError
    when (val r = reply) {
        null -> Text(
            if (err != null) "Couldn't read the files: $err" else "Reading…",
            style = MaterialTheme.typography.bodySmall,
            color = if (err != null) chrome.warnInk else chrome.textLo,
        )
        is SendFile.ListReply.Missing -> if (!compact) {
            Text(SendFile.MISSING, style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid)
        }
        is SendFile.ListReply.Refused -> Text(
            r.said,
            style = MaterialTheme.typography.bodySmall,
            color = chrome.warnInk,
        )
        is SendFile.ListReply.Ready -> {
            if (!compact && r.said.isNotBlank()) {
                Text(r.said, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                Gap(6)
            }
            if (r.files.isEmpty() && !compact) {
                Text(SendFile.NOTHING_WAITING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
            }
            r.files.forEach { file ->
                val fits = SendFile.fitsCap(file.sizeBytes, r.capBytes)
                Gap(10)
                Column(Modifier.fillMaxWidth()) {
                    Text(file.name, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                    Text(
                        listOf(file.folder, SendFile.sizeWords(file.sizeBytes))
                            .filter { it.isNotBlank() }.joinToString(" · "),
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                    Text(
                        "${SendFile.mimeOr(file.mime)} · ${SendFile.expiryWords(file.expiresIn)}",
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        // Q3: View is offered only at or under 200 MiB. Above
                        // that the row says to use Save instead - a 2 GiB video
                        // in this app's cache, held open by a viewer, is
                        // exactly what this gate stops. An over-cap row keeps
                        // its dimmed View; its own sentence below says why
                        // nothing can be fetched at all.
                        when {
                            !fits -> Quiet("View", enabled = false) { act(file, view = true) }
                            SendFile.canView(file.sizeBytes) -> Quiet(
                                "View",
                                enabled = canAct && busyId == null,
                            ) { act(file, view = true) }
                            else -> Text(
                                SendFile.VIEW_USE_SAVE,
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textLo,
                            )
                        }
                        Spacer(Modifier.width(8.dp))
                        Quiet("Save to Downloads", enabled = canAct && busyId == null && fits) {
                            act(file, view = false)
                        }
                    }
                    if (!fits) {
                        Gap(4)
                        Text(
                            SendFile.overCapWords(file.sizeBytes, r.capBytes),
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.warnInk,
                        )
                    } else if (busyId == file.id) {
                        Gap(4)
                        Text(
                            progressLine(now, file.sizeBytes),
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textLo,
                            modifier = Modifier.liveStatus(),
                        )
                    }
                }
            }
            if (!compact) {
                Gap(10)
                Text(SendFile.LIMITS, style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo)
            }
        }
    }
    said?.let {
        Gap(6)
        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid,
            modifier = Modifier.liveStatus())
    }
    if (!canAct && !compact) {
        Gap(4)
        Text(
            "Not connected to the desktop, so a file cannot be fetched until the link is back.",
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
    }
}

/**
 * The one line under a downloading row. Before the first slice says
 * "Starting…", then the bytes received and percent; once the last slice is
 * written the runtime is reading the file back for its sha256, and the line
 * says so instead of pretending a file that is still being checked is kept.
 */
private fun progressLine(progress: SendFile.Progress?, listedSize: Long): String = when {
    progress == null -> "Starting…"
    progress.total > 0 && progress.received >= progress.total ->
        "Checking the whole file before it is kept…"
    progress.total > 0 -> SendFile.progressWords(progress.received, progress.total)
    // No `size_bytes` yet on the first answer that had data but no readable
    // size; the list's own size is the honest fallback (never claimed as the
    // PC's total once it sends one).
    else -> SendFile.progressWords(progress.received, listedSize)
}

/**
 * Hands the verified download to Android's viewer through the app's own
 * `FileProvider` (`${applicationId}.sendfile`, `res/xml/send_file_paths.xml`):
 * `cache-path` is app-private, so no other app can write there, and the URI is
 * granted read-only for this one intent. The assembly happened in the runtime;
 * this step opens that already-checked file, so a small file still opens the
 * way it always did. Says what happened in plain words; never claims an open
 * that failed.
 *
 * TWO GATES before the viewer sees anything. The size checked here is the one
 * the whole-file SHA-256 verified, not the list's - no file above
 * [SendFile.VIEW_MAX_BYTES] is ever opened (Q3), whatever the row said a moment
 * earlier. A file that IS opened is recorded with the runtime
 * ([JarvisRuntime.noteOpenedForViewer]) so the leaving sweep keeps it for the
 * app that is reading it.
 */
private fun openReceived(context: Context, file: SendFile.Fetched.Got): String = try {
    if (!SendFile.canView(file.sizeBytes)) {
        SendFile.VIEW_USE_SAVE
    } else {
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.sendfile", file.file)
        val intent = Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, SendFile.mimeOr(file.mime))
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
        // A viewer holds this file now: the plate's leaving sweep must keep it.
        JarvisRuntime.noteOpenedForViewer(file.file)
        "Opening ${file.name}."
    }
} catch (e: ActivityNotFoundException) {
    SendFile.NO_VIEWER
} catch (e: IllegalArgumentException) {
    SendFile.NO_VIEWER
} catch (e: Exception) {
    SendFile.SAVE_FAILED
}

/**
 * Streams the verified file into the phone's own Downloads collection, under
 * `Downloads/Jarvis`, through `MediaStore.Downloads`. The row is inserted
 * pending and only published once every byte has been copied, so a failure
 * mid-copy leaves nothing visible; the pending row is deleted on the way out.
 * `minSdk` is 33, so this is the only path this app needs (no legacy
 * external-files branch). Once the save lands, the verified copy in the app's
 * cache is deleted at once (Q3).
 */
private fun saveToDownloads(context: Context, file: SendFile.Fetched.Got): String {
    val safe = SendFile.nameForDisk(file.name)
    val resolver = context.contentResolver
    var uri: Uri? = null
    var saved = false
    try {
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, safe)
            put(MediaStore.MediaColumns.MIME_TYPE, SendFile.mimeOr(file.mime))
            put(
                MediaStore.MediaColumns.RELATIVE_PATH,
                Environment.DIRECTORY_DOWNLOADS + "/Jarvis",
            )
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        val inserted = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: return SendFile.SAVE_FAILED
        uri = inserted
        val stream = resolver.openOutputStream(inserted) ?: return SendFile.SAVE_FAILED
        stream.use { out ->
            file.file.inputStream().use { input -> input.copyTo(out, 64 * 1024) }
        }
        // The row becomes visible only when this lands. If it does not, the
        // save is not claimed and the pending row is removed below.
        val done = ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) }
        saved = resolver.update(inserted, done, null, null) > 0
    } catch (e: Exception) {
        saved = false
    } finally {
        // Nothing partial may be left in Downloads, and once a save has landed
        // the app's cache copy is no longer needed (Q3: clean up cache copies
        // promptly). A save that FAILED keeps its verified copy for the
        // leaving sweep instead, so this path can never delete a file another
        // app's viewer was handed, and the sweep still guarantees it goes.
        if (!saved) uri?.let { runCatching { resolver.delete(it, null, null) } }
        if (saved) runCatching { file.file.delete() }
    }
    return if (saved) "Saved to Downloads/Jarvis as $safe." else SendFile.SAVE_FAILED
}
