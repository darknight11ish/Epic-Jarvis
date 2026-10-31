package com.jarvis.client.ui.screens

import android.content.ActivityNotFoundException
import android.content.ContentValues
import android.content.Context
import android.content.Intent
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
import androidx.compose.runtime.LaunchedEffect
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
import kotlinx.coroutines.launch
import java.io.File

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
 * - **View** writes the one received file into this app's private cache and
 *   hands it to Android's viewer through a `FileProvider` (`ACTION_VIEW`, the
 *   right MIME type, a read grant for that one URI). App-private storage, so no
 *   other app can write there.
 * - **Save to Downloads** writes it into the phone's own Downloads collection
 *   under `Downloads/Jarvis` through `MediaStore.Downloads`. This app's
 *   `minSdk` is 33, so that is the only path needed - there is no legacy
 *   external-files branch.
 *
 * The PC's own rules are only STATED here, never reinterpreted: one file at a
 * time, 10 MiB, ten minutes, one download. A second fetch is the PC's 404
 * sentence ("the ten-minute window passed or it was already downloaded").
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
 * Downloads, the PC's limits in one line, and what the phone did. [compact] is
 * the Coming up block's shape - no heading, and nothing at all when there is
 * nothing waiting.
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
    // A waiting file lives ten minutes: keep the list true while it is open.
    LaunchedEffect(privateHidden) {
        while (true) {
            delay(SendFile.REFRESH_MS)
            if (!privateHidden) reads += 1
        }
    }

    fun act(file: SendFile.Waiting, view: Boolean) {
        if (busyId != null) return
        busyId = file.id
        said = null
        scope.launch {
            try {
                when (val r = JarvisRuntime.downloadFile(file.id)) {
                    is ApiResult.Ok -> when (val f = r.value) {
                        is SendFile.Fetched.Got -> said =
                            if (view) openReceived(context, f) else saveToDownloads(context, f)
                        is SendFile.Fetched.Refused -> said = f.said
                    }
                    is ApiResult.Failed -> said = JarvisRuntime.noticeFor(r.error)
                }
                // The id is single use: whatever happened, the list is not what
                // it was a moment ago (usually the file is gone).
                reads += 1
            } finally {
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
                "View opens it here; Save to Downloads keeps a copy.",
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
                        Quiet("View", enabled = canAct && busyId == null) { act(file, view = true) }
                        Spacer(Modifier.width(8.dp))
                        Quiet("Save to Downloads", enabled = canAct && busyId == null) {
                            act(file, view = false)
                        }
                        if (busyId == file.id) {
                            Spacer(Modifier.width(8.dp))
                            Text("Fetching…", style = MaterialTheme.typography.labelSmall,
                                color = chrome.textLo)
                        }
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
 * Writes the received bytes into this app's private cache and hands them to
 * Android's viewer through the app's own `FileProvider` (`${applicationId}
 * .sendfile`, `res/xml/send_file_paths.xml`): `cache-path` is app-private, so
 * no other app can write there, and the URI is granted read-only for this one
 * intent. Says what happened in plain words; never claims an open that failed.
 */
private fun openReceived(context: Context, file: SendFile.Fetched.Got): String {
    val safe = SendFile.nameForDisk(file.name)
    return try {
        val dir = File(context.cacheDir, "received").apply { mkdirs() }
        val written = File(dir, safe)
        written.writeBytes(file.bytes)
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.sendfile", written)
        val intent = Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, SendFile.mimeOr(file.mime))
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
        "Opening ${file.name}."
    } catch (e: ActivityNotFoundException) {
        SendFile.NO_VIEWER
    } catch (e: IllegalArgumentException) {
        SendFile.NO_VIEWER
    } catch (e: Exception) {
        SendFile.SAVE_FAILED
    }
}

/**
 * Writes the received bytes into the phone's own Downloads collection, under
 * `Downloads/Jarvis`, through `MediaStore.Downloads`. `minSdk` is 33, so this
 * is the only path this app needs (no legacy external-files branch).
 */
private fun saveToDownloads(context: Context, file: SendFile.Fetched.Got): String {
    val safe = SendFile.nameForDisk(file.name)
    return runCatching {
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, safe)
            put(MediaStore.MediaColumns.MIME_TYPE, SendFile.mimeOr(file.mime))
            put(
                MediaStore.MediaColumns.RELATIVE_PATH,
                Environment.DIRECTORY_DOWNLOADS + "/Jarvis",
            )
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        val resolver = context.contentResolver
        val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: return SendFile.SAVE_FAILED
        resolver.openOutputStream(uri)?.use { out -> out.write(file.bytes) }
            ?: return SendFile.SAVE_FAILED
        val done = ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) }
        resolver.update(uri, done, null, null)
        "Saved to Downloads/Jarvis as $safe."
    }.getOrDefault(SendFile.SAVE_FAILED)
}
