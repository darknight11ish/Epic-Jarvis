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
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Pictures
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * "Ask for a picture, and keep it" — the owner's decision of 2026-09-27
 * (*"12 GB card: longer conversations with picture understanding first, and
 * making pictures too (swapped in when asked, since both cannot sit on the
 * card at once)"*), docs/JARVIS-API.md section 129.
 *
 * Brain -> Pictures, headed **"Image mode"** (2026-10-25) because that is the
 * owner's own name for it and this is the one place it lives on the phone - a
 * heading, not a second entry and not a button. The owner types what the
 * picture should show, taps Make, and the PC draws it and keeps it. The gallery
 * below shows each picture with the words that made it, its seed and when it
 * was made, a "Make another" (the same words again) and **"Save to my phone"**,
 * which reads the bytes and writes the PNG into THIS phone's own Pictures
 * collection.
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
 * WHEN THE CARD IS BUSY (the final contract, 2026-10-25). With the everyday
 * chat on the 12 GB card, one picture means the chat is set aside, drawn, and
 * loaded back. The FIRST request moves nothing: the PC answers **409
 * `needs: "free_card"`** with its own sentence and its own minutes, and this
 * plate draws that sentence word for word with the PC's two answers -
 * **"Set the chat aside and draw (about N minutes)"** and **"Not now"**. Only
 * that tap sends the same body plus `free_card: true` (either app may confirm
 * it: the owner's decision of 2026-10-24), and it is ONE long request, so the
 * screen shows a waiting sentence that lasts minutes and the button is gone
 * while it runs. **Nothing is ever re-sent on its own:** a timeout says the PC
 * may still be drawing and offers no confirm again, and a `409 needs:
 * "drawing"` is the PC's own "wait for that one" sentence, shown as sent. An
 * OLDER PC's `403 pc_only` is its sentence plus one line saying it needs the
 * newer Jarvis - never a raw code.
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
    /** The PC's own sentence for the last answer - shown word for word. */
    var said by remember { mutableStateOf("") }
    /** The PC's 409 question, word for word. Blank = there is no question. */
    var question by remember { mutableStateOf("") }
    /** The words the confirm would send; blank = no question is waiting. */
    var confirmPrompt by remember { mutableStateOf("") }
    /** The PC's own minutes estimate for that question. */
    var minutes by remember { mutableStateOf<Int?>(null) }
    /** True while the ONE long confirming request runs. */
    var confirming by remember { mutableStateOf(false) }
    /** True while the first (short) request runs. */
    var asking by remember { mutableStateOf(false) }
    /** The PC is older than the phone: show its sentence plus [Pictures.OLD_PC_WORDS]. */
    var oldPc by remember { mutableStateOf(false) }
    var prompt by remember { mutableStateOf("") }
    /**
     * The hiding switch as it is NOW, not as it was when a request started: a
     * draw can run for minutes, and the owner may hide the lists while it does.
     * Its answer must not fetch the gallery then ([load] is guarded on this).
     */
    var hiddenNow by remember { mutableStateOf(hidden) }
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
    // hand is thrown away so no prompt can be redrawn from it. A request that
    // was in flight cannot be unsent, but its answer is not kept either.
    LaunchedEffect(hidden) {
        hiddenNow = hidden
        if (hidden) {
            reply = null
            error = ""
            said = ""
            question = ""
            confirmPrompt = ""
            minutes = null
            oldPc = false
            asking = false
            confirming = false
            loaded.clear()
        } else {
            load()
        }
    }

    /** ONE request at a time: the Make button and every row's actions wait. */
    val busy = asking || confirming

    /**
     * The FIRST request: the owner's words ALONE. It never sends `free_card`;
     * when the PC answers its 409 question, this only draws the question.
     */
    suspend fun ask(text: String) {
        asking = true
        said = ""
        question = ""
        confirmPrompt = ""
        minutes = null
        oldPc = false
        try {
            val out = JarvisRuntime.makePicture(text)
            if (out.needsConfirm) {
                // NOTHING WAS DRAWN, so the gallery is not read again: the
                // question is the whole answer, and a refresh must not replace
                // it with a failure line.
                confirmPrompt = text
                question = out.said
                minutes = out.minutes
            } else {
                said = out.said
                oldPc = out.oldPc
                loaded.clear()
                // A request can outlast the owner hiding the lists; then
                // nothing is fetched. The rule is "fetch nothing while it is
                // on", and this covers a draw that finishes after the switch.
                if (!hiddenNow) load()
            }
        } finally {
            asking = false
        }
    }

    /**
     * The owner's tap on the PC's question: the SAME words plus
     * `free_card: true`, ONE long request. The question is cleared BEFORE the
     * call, so a second tap cannot send the same confirmation twice; it is not
     * put back on a timeout, because the PC may still be drawing.
     */
    suspend fun confirmNow() {
        val text = confirmPrompt
        if (text.isBlank()) {
            confirming = false
            return
        }
        confirmPrompt = ""
        question = ""
        oldPc = false
        said = ""
        try {
            val out = JarvisRuntime.makePicture(text, confirm = true)
            if (out.needsConfirm) {
                // The chat grabbed the card again between the yes and the
                // draw. Ask again - never loop on its own, and read nothing.
                confirmPrompt = text
                question = out.said
                minutes = out.minutes
            } else {
                said = out.said
                oldPc = out.oldPc
                loaded.clear()
                // A picture may have been drawn even when the phone stopped
                // waiting, so the gallery is read back either way - but never
                // while the private lists are hidden.
                if (!hiddenNow) load()
            }
        } finally {
            confirming = false
        }
    }

    val r = reply
    Plate(Modifier.fillMaxWidth()) {
        Section(Pictures.WORDS.getValue("title")) {
            if (hidden) {
                // One line, and no fetch at all.
                Text(Pictures.WORDS.getValue("hidden_short"), style = MaterialTheme.typography.bodySmall)
                return@Section
            }
            // The owner's own name for the feature, so this one screen is
            // findable by the words they use. A heading, never a control: the
            // switch is the PC's, and a button here would be a fake one.
            Kicker(Pictures.IMAGE_MODE, Modifier.semantics { heading() })
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
                    enabled = canAct && !busy && prompt.isNotBlank(),
                    busy = asking,
                ) {
                    val text = prompt
                    if (text.isNotBlank() && !busy) {
                        // Claimed BEFORE the coroutine starts, so a double tap
                        // cannot send two first requests.
                        asking = true
                        scope.launch { ask(text) }
                    }
                }

                if (confirming) {
                    // The one long request. Minutes, not seconds, and no button
                    // while it runs - so it cannot be sent a second time.
                    Gap(8)
                    Text(
                        Pictures.confirmingWords(minutes),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Gap(4)
                    Text(
                        "The picture appears below when your PC has finished.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                } else if (confirmPrompt.isNotBlank()) {
                    // The PC's own 409 question, drawn where Make was. Its
                    // sentence is shown word for word; the minutes are the
                    // PC's own estimate, never a guess here.
                    Gap(8)
                    Text(question, style = MaterialTheme.typography.bodyMedium)
                    Gap(8)
                    Row(Modifier.fillMaxWidth()) {
                        Primary(
                            Pictures.confirmLabel(minutes),
                            enabled = canAct && !busy,
                        ) {
                            // Claimed BEFORE the coroutine starts, so a double
                            // tap cannot send the same confirmation twice.
                            if (confirmPrompt.isNotBlank() && !busy) {
                                confirming = true
                                scope.launch { confirmNow() }
                            }
                        }
                        Gap(8)
                        Quiet(
                            Pictures.WORDS.getValue("set_aside_no"),
                            enabled = !busy,
                        ) {
                            // The owner said no: NOTHING is sent, and the words
                            // they typed stay in the box above.
                            confirmPrompt = ""
                            question = ""
                            minutes = null
                            said = Pictures.WORDS.getValue("set_aside_stopped")
                        }
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
                        canAct = canAct && !busy,
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
                                        oldPc = false
                                    }
                                }
                            }
                        },
                        onAnother = {
                            // "Make another" goes through the SAME two-step
                            // flow: the first request only, never a confirm.
                            scope.launch { ask(shot.prompt) }
                        },
                        onSave = {
                            scope.launch {
                                when (val got = JarvisRuntime.pictureBytes(shot.id)) {
                                    is ApiResult.Ok -> {
                                        val wrote = withContext(Dispatchers.IO) {
                                            saveToPhone(context, shot, got.value)
                                        }
                                        oldPc = false
                                        said = if (wrote) {
                                            Pictures.WORDS.getValue("saved_phone")
                                        } else {
                                            "Your phone would not let Jarvis save that picture."
                                        }
                                    }
                                    is ApiResult.Failed -> {
                                        said = JarvisRuntime.describe(got.error)
                                        oldPc = false
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
                if (oldPc) {
                    // The PC's own sentence first, then the fact that this PC
                    // needs the newer Jarvis. No code and nothing sent again:
                    // this phone's confirm cannot work there until the PC is
                    // updated.
                    Gap(4)
                    Text(Pictures.OLD_PC_WORDS, style = MaterialTheme.typography.bodySmall)
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
