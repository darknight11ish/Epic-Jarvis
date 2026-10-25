package com.jarvis.client.ui.screens

import android.content.ContentValues
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Pictures
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * "Ask for a picture, and keep it" — the owner's decision of 2026-09-27
 * (*"12 GB card: longer conversations with picture understanding first, and
 * making pictures too (swapped in when asked, since both cannot sit on the
 * card at once)"*), docs/JARVIS-API.md section 129.
 *
 * Brain -> Pictures. The owner types what the picture should show, taps Make,
 * and the PC draws it and keeps it. The gallery below shows each picture with
 * the words that made it, its seed and when it was made, a "Make another"
 * (the same words again) and **"Save to my phone"**, which reads the bytes and
 * writes the PNG into THIS phone's own Pictures collection.
 *
 * WHAT IS NOT ON THIS SCREEN, AND WHY
 *  - **No model, no drawing program, no catalogue.** The PC owns all of it;
 *    the phone sends words and reads a picture (CLAUDE.md: the model
 *    catalogue and deep configuration stay off the phone).
 *  - **No switch, no folder, no program picker.** Those are the PC's own
 *    business and the backend refuses them from anywhere else, so there is no
 *    control here that could try.
 *  - **No way out of the PC.** There is no share, no upload, no email and no
 *    send-to-anyone on this screen. "Save to my phone" is the owner's own
 *    device over Tailscale or Meshnet, which is not a way out.
 *
 * MAKING ONE NEEDS NO APPROVAL CARD: a picture is a new file in a folder on
 * the PC, from words the owner typed — the same shape as a timer or a note.
 * It is still held on a stale link (rule 4), because it does write a file, and
 * the buttons grey out with the rest of the app while the link is stale.
 *
 * WHEN THE CARD IS BUSY (added 2026-10-25). With the everyday chat on the
 * 12 GB card, one picture means the chat is set aside, drawn, and loaded back -
 * and only the PC can start that. The PC says so in its own sentence; this
 * plate shows that sentence word for word, adds the one line saying where the
 * step belongs ([Pictures.NEEDS_PC_WORDS]), and keeps the owner's typed words
 * in the box. There is no control here that could carry the step out from the
 * phone: the PC refuses it (`403 pc_only`) and the phone never asks.
 *
 * HIDDEN WITH THE PRIVATE THINGS. The prompts are the owner's own words, so
 * this whole section hides under "Hide memory lists and chat history" — added
 * to that rule rather than beside it. [hidden] is that switch: while it is on
 * this plate **fetches nothing at all** and draws one line saying so, so not
 * one prompt is even asked for.
 */
@Composable
internal fun PicturesSection(
    /** "Hide memory lists and chat history" (or App lock): fetch nothing. */
    hidden: Boolean,
    canAct: Boolean,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var reply by remember { mutableStateOf<Pictures.Reply?>(null) }
    var error by remember { mutableStateOf("") }
    var said by remember { mutableStateOf("") }
    /** The PC said the everyday chat has to be set aside first - a step the PC alone can start. */
    var needsPc by remember { mutableStateOf(false) }
    var asking by remember { mutableStateOf(false) }
    var prompt by remember { mutableStateOf("") }
    /** id -> the decoded picture, so a scroll back does not re-fetch. */
    val loaded = remember { androidx.compose.runtime.mutableStateMapOf<String, android.graphics.Bitmap>() }

    suspend fun load() {
        when (val r = JarvisRuntime.pictures()) {
            is ApiResult.Ok -> {
                reply = r.value
                error = ""
            }
            is ApiResult.Failed -> {
                error = JarvisRuntime.describe(r.error)
                reply = null
            }
        }
    }

    // While the private lists are hidden nothing is fetched, and the answer in
    // hand is thrown away so no prompt can be redrawn from it.
    LaunchedEffect(hidden) {
        if (hidden) {
            reply = null
            error = ""
            said = ""
            needsPc = false
            loaded.clear()
        } else {
            load()
        }
    }

    val r = reply
    Plate(Modifier.fillMaxWidth()) {
        Section(Pictures.WORDS.getValue("title")) {
            if (hidden) {
                // One line, and no fetch at all.
                Text(Pictures.WORDS.getValue("hidden_short"), style = MaterialTheme.typography.bodyMedium)
                return@Section
            }
            Text(Pictures.WORDS.getValue("under"), style = MaterialTheme.typography.bodySmall)
            Gap(8)

            if (error.isNotBlank()) {
                Quiet(error, enabled = false) { }
                return@Section
            }
            if (r == null) {
                Text("Asking Jarvis…", style = MaterialTheme.typography.bodySmall)
                return@Section
            }
            if (!r.available) {
                // An older PC: one sentence naming the fix, never a blank pane.
                Quiet(Pictures.WORDS.getValue("missing"), enabled = false) { }
                return@Section
            }

            // The PC's own one plain sentence: nothing set up, or the switch is
            // off. It is never an error banner and never a silent blank.
            if (r.words.isNotBlank()) {
                Text(r.words, style = MaterialTheme.typography.bodyMedium)
                Gap(8)
            }

            if (r.canAsk) {
                TextInput(
                    value = prompt,
                    onValueChange = { prompt = it },
                    label = Pictures.WORDS.getValue("ask_label"),
                    placeholder = "a red panda reading in a library, warm light",
                )
                Gap(8)
                Primary(
                    Pictures.WORDS.getValue("make"),
                    enabled = canAct && !asking && prompt.isNotBlank(),
                    busy = asking,
                ) {
                    asking = true
                    said = ""
                    needsPc = false
                    scope.launch {
                        val out = JarvisRuntime.makePicture(prompt)
                        said = out.said
                        needsPc = out.needsPc
                        asking = false
                        loaded.clear()
                        load()
                    }
                }
                Gap(4)
                Quiet(Pictures.WORDS.getValue("not_kept"), enabled = false) { }
                if (!canAct) {
                    Gap(4)
                    // The app's own sentence for a link that cannot be
                    // confirmed live (rule 4) - the same words Home uses.
                    Quiet("Catching up… the buttons come back when Jarvis is up to date.", enabled = false) { }
                }
                Gap(12)
            }

            Section("Your pictures") {
                if (r.shots.isEmpty()) {
                    Text(Pictures.WORDS.getValue("empty"), style = MaterialTheme.typography.bodySmall)
                }
                for (shot in r.shots) {
                    PictureRow(
                        shot = shot,
                        bitmap = loaded[shot.id],
                        canAct = canAct,
                        onLoad = {
                            scope.launch {
                                when (val got = JarvisRuntime.pictureBytes(shot.id)) {
                                    is ApiResult.Ok -> {
                                        val bitmap = withContext(Dispatchers.Default) {
                                            BitmapFactory.decodeByteArray(got.value, 0, got.value.size)
                                        }
                                        if (bitmap != null) loaded[shot.id] = bitmap
                                    }
                                    is ApiResult.Failed -> {
                                        said = JarvisRuntime.describe(got.error)
                                        needsPc = false
                                    }
                                }
                            }
                        },
                        onAnother = {
                            said = ""
                            needsPc = false
                            scope.launch {
                                val out = JarvisRuntime.makePicture(shot.prompt)
                                said = out.said
                                needsPc = out.needsPc
                                loaded.clear()
                                load()
                            }
                        },
                        onSave = {
                            scope.launch {
                                when (val got = JarvisRuntime.pictureBytes(shot.id)) {
                                    is ApiResult.Ok -> {
                                        val wrote = withContext(Dispatchers.IO) {
                                            saveToPhone(context, shot, got.value)
                                        }
                                        needsPc = false
                                        said = if (wrote) {
                                            Pictures.WORDS.getValue("saved_phone")
                                        } else {
                                            "Your phone would not let Jarvis save that picture."
                                        }
                                    }
                                    is ApiResult.Failed -> {
                                        said = JarvisRuntime.describe(got.error)
                                        needsPc = false
                                    }
                                }
                            }
                        },
                    )
                    Gap(10)
                }
                if (r.keep.isNotBlank()) {
                    Quiet(r.keep, enabled = false) { }
                }
            }

            if (said.isNotBlank()) {
                Gap(6)
                Text(said, style = MaterialTheme.typography.bodyMedium)
                if (needsPc) {
                    // The PC's sentence says the everyday chat has to be set
                    // aside; this one line says where that step belongs and
                    // where the picture will turn up. Nothing here offers to do
                    // it from the phone - the PC refuses that (403 pc_only).
                    Gap(4)
                    Text(Pictures.NEEDS_PC_WORDS, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

/** One picture: the picture, what made it, and what may be done with it. */
@Composable
private fun PictureRow(
    shot: Pictures.Shot,
    bitmap: android.graphics.Bitmap?,
    canAct: Boolean,
    onLoad: () -> Unit,
    onAnother: () -> Unit,
    onSave: () -> Unit,
) {
    // The bytes are fetched the first time this row draws, and kept for this
    // visit only - never written to disk by this layer.
    LaunchedEffect(shot.id) {
        if (bitmap == null) onLoad()
    }
    Column(Modifier.fillMaxWidth().semantics { contentDescription = shot.said() }) {
        val image = bitmap
        if (image != null) {
            Image(
                bitmap = image.asImageBitmap(),
                contentDescription = shot.prompt.ifBlank { "A picture Jarvis drew" },
                modifier = Modifier.size(220.dp),
            )
            Gap(6)
        } else {
            Text("Getting the picture…", style = MaterialTheme.typography.bodySmall)
            Gap(6)
        }
        Text(
            shot.prompt.ifBlank { Pictures.WORDS.getValue("no_record") },
            style = MaterialTheme.typography.bodyMedium,
        )
        val bits = buildList {
            if (shot.madeAtWords.isNotBlank()) add(shot.madeAtWords)
            shot.seed?.let { add("${Pictures.WORDS.getValue("seed_label")} $it") }
            if (shot.model.isNotBlank()) add(shot.model)
        }
        if (bits.isNotEmpty()) {
            Text(bits.joinToString(" · "), style = MaterialTheme.typography.bodySmall)
        }
        if (!shot.hasRecord) {
            Text(Pictures.WORDS.getValue("no_record"), style = MaterialTheme.typography.bodySmall)
        }
        Gap(6)
        Row(Modifier.fillMaxWidth()) {
            Primary(Pictures.WORDS.getValue("another"), enabled = canAct) { onAnother() }
            Gap(8)
            Quiet(Pictures.WORDS.getValue("save_phone"), enabled = canAct) { onSave() }
        }
    }
}

/**
 * Writes the PNG into this phone's own Pictures collection, under
 * `Pictures/Jarvis`. Android 10 and later need no storage permission for
 * this: an app writing its own picture into MediaStore is allowed. Returns
 * false when the phone refused, so the screen can say so rather than claim a
 * save that did not happen.
 */
private fun saveToPhone(
    context: android.content.Context,
    shot: Pictures.Shot,
    bytes: ByteArray,
): Boolean = runCatching {
    val values = ContentValues().apply {
        put(MediaStore.MediaColumns.DISPLAY_NAME, Pictures.fileName(shot))
        put(MediaStore.MediaColumns.MIME_TYPE, "image/png")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            put(MediaStore.MediaColumns.RELATIVE_PATH, "Pictures/Jarvis")
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
    }
    val resolver = context.contentResolver
    val uri: Uri = resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
        ?: return false
    resolver.openOutputStream(uri)?.use { out -> out.write(bytes) } ?: return false
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        val done = ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) }
        resolver.update(uri, done, null, null)
    }
    true
}.getOrDefault(false)
