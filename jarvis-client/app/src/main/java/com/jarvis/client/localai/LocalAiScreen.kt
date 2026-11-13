package com.jarvis.client.localai

import android.content.ContentResolver
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.Toggle
import com.jarvis.client.ui.screens.TopBar
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * "Local AI" - a model running on this phone, in its own screen.
 *
 * ## What is drawn, and what is not
 *
 * The screen opens with a switch that is **off**. While it is off there is no
 * engine, no model and no file picker: only the explanation, the one permanent
 * label and the switch. Turning it on shows the models already on the phone
 * and an Import button; loading a model is a separate tap, and only a full
 * conversation with a loaded model draws the chat.
 *
 * Nothing downloads. The only way a model arrives is the owner picking a
 * `.gguf` file they already put on the phone. Nothing loads by itself: the
 * engine is created inside the Load tap.
 *
 * ## Leaving the screen frees the model
 *
 * [DisposableEffect] calls `controller.close()` when the screen leaves the
 * composition, which destroys the native handle. A model is hundreds of
 * megabytes; keeping it alive on the way back to Home is how the next app on
 * the phone gets killed. That is the memory-saving rule that matters, and it
 * had to stay while the idle rule changed: within the screen, five minutes
 * with nothing asked (or typed) frees the model too (`LocalEnginePolicy`).
 *
 * ## The keyboard must not hide the input or Send (field test, 2026-11-13)
 *
 * The chat used to be one plate at the end of the scrolling list, so with the
 * keyboard up the list clipped it and `Send` left the accessibility tree
 * entirely - the tester could only send after pressing BACK. The chat history
 * still scrolls (it is a list item), but the composer (field, Send, Clear) is
 * now pinned below the list, inside the app's root `imePadding()`, so the
 * keyboard shrinks the screen and the composer stays on it. The permanent
 * label is pinned above the list for the same reason: it must be readable
 * even while a question is being typed.
 *
 * ## The file picker is the one step that needs exact words
 *
 * Android's document picker is a different app. The Import plate therefore
 * says exactly what to tap - the button, the picker, then Open - because
 * "import a model" alone is not enough for a beginner holding a phone.
 */
@Composable
fun LocalAiScreen(
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val controller = remember(context) {
        LocalAiController(
            engineFactory = { LlamaEngine() },
            store = ModelStoreAndroid.forApp(context),
            tier = DeviceTiersAndroid.read(context),
            settings = LocalAiSettings(SharedPrefsLocalAiFlags(context)),
        )
    }
    val state by controller.state.collectAsState()

    var draft by rememberSaveable { mutableStateOf("") }
    var pickerNotice by remember { mutableStateOf<String?>(null) }
    var pendingDelete by remember { mutableStateOf<String?>(null) }

    DisposableEffect(controller) {
        onDispose { controller.close() }
    }

    // Re-read the folder when the switch goes on, and after an import the
    // controller refreshes on its own.
    LaunchedEffect(state.switchOn) {
        if (state.switchOn) controller.refreshModels()
    }

    // The screen's heartbeat. It is the only caller of tick(), so the
    // five-minute idle unload and the 180-second cap exist exactly while this
    // screen does.
    LaunchedEffect(state.switchOn) {
        if (!state.switchOn) return@LaunchedEffect
        while (true) {
            delay(TICK_MILLIS)
            controller.tick()
        }
    }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        if (uri == null) return@rememberLauncherForActivityResult
        val picked = queryPicked(context.contentResolver, uri)
        if (picked == null) {
            pickerNotice = "Jarvis could not read that file's name. Tap Import a model and pick it again."
        } else {
            pickerNotice = null
            scope.launch {
                controller.importModel(picked.name, picked.size) {
                    runCatching { context.contentResolver.openInputStream(uri) }.getOrNull()
                }
            }
        }
    }

    fun send() {
        val text = draft.trim()
        if (text.isEmpty() || !state.switchOn) return
        draft = ""
        scope.launch { controller.send(text) }
    }

    // The chat exists once a model is loaded (or is being loaded, or a reply
    // is running). It decides whether the composer is pinned at the bottom of
    // the screen; the history itself stays in the scrolling list above it.
    val chatVisible = state.loadedModel != null || state.engine == EngineState.READY ||
        state.engine == EngineState.GENERATING

    Column(modifier.fillMaxSize().background(chrome.surface0)) {
        TopBar(LocalAiWords.TITLE, onBack, subtitle = LocalAiWords.SUBTITLE)

        // The permanent label, pinned above the scrolling list rather than
        // living in it. It is drawn on every visit, on and off, because the
        // one thing this screen must never blur is which machine is
        // answering - and when the keyboard is up the list scrolls, so a
        // label inside it is exactly the thing that would scroll away.
        Column(
            Modifier.fillMaxWidth().padding(horizontal = 18.dp).padding(top = 4.dp),
        ) {
            Plate {
                Text(
                    LocalAiWords.PERMANENT_LABEL,
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textHi,
                    modifier = Modifier.semantics {
                        contentDescription = LocalAiWords.PERMANENT_LABEL
                    },
                )
            }
        }

        LazyColumn(
            verticalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 18.dp),
        ) {
            item(key = "switch") {
                Plate {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(
                                LocalAiWords.SWITCH_LABEL,
                                style = MaterialTheme.typography.bodyLarge,
                                color = chrome.textHi,
                            )
                            Text(
                                if (state.switchOn) {
                                    LocalAiWords.SWITCH_ON_DETAIL
                                } else {
                                    LocalAiWords.SWITCH_OFF_DETAIL
                                },
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textMid,
                            )
                        }
                        Toggle(
                            checked = state.switchOn,
                            enabled = !state.generating && !state.busy,
                            onCheckedChange = { on -> scope.launch { controller.setSwitch(on) } },
                        )
                    }
                }
            }

            val notice = state.notice
            if (notice != null) {
                item(key = "notice") {
                    StatusLine(
                        text = notice,
                        problem = state.noticeIsProblem,
                        onDismiss = {
                            controller.dismissNotice()
                            pickerNotice = null
                        },
                    )
                }
            }
            val localNotice = pickerNotice
            if (localNotice != null) {
                item(key = "picker-notice") {
                    StatusLine(
                        text = localNotice,
                        problem = true,
                        onDismiss = { pickerNotice = null },
                    )
                }
            }

            if (!state.switchOn) {
                item(key = "off") {
                    Plate {
                        Text(
                            LocalAiWords.INTRO,
                            style = MaterialTheme.typography.bodyMedium,
                            color = chrome.textMid,
                        )
                        Gap(8)
                        Text(
                            LocalAiWords.OFF_NOTE,
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid,
                        )
                        Gap(10)
                        Text(
                            controller.tier.summary,
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textLo,
                        )
                        Gap(8)
                        Text(
                            LocalAiWords.BRING_YOUR_OWN,
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid,
                        )
                    }
                }
            } else {
                item(key = "models-heading") {
                    Kicker(LocalAiWords.MODELS)
                }

                item(key = "import") {
                    Plate {
                        Primary(
                            LocalAiWords.IMPORT,
                            enabled = !state.busy && !state.generating,
                            busy = state.busy && state.importName != null,
                            onClick = { picker.launch(arrayOf("*/*")) },
                        )
                        Gap(6)
                        Text(
                            LocalAiWords.IMPORT_HELP,
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textMid,
                        )
                    }
                }

                if (state.busy && state.importName != null) {
                    item(key = "import-progress") {
                        Text(
                            LocalAiWords.progressLine(state.importCopied, state.importTotal),
                            style = MaterialTheme.typography.bodyMedium,
                            color = chrome.textHi,
                        )
                    }
                }

                if (state.models.isEmpty() && !(state.busy && state.importName != null)) {
                    item(key = "no-models") {
                        Text(
                            LocalAiWords.NO_MODELS,
                            style = MaterialTheme.typography.bodyMedium,
                            color = chrome.textMid,
                        )
                    }
                }

                items(state.models, key = { it.name }) { model ->
                    ModelRow(
                        model = model,
                        loaded = state.loadedModel == model.name,
                        engineState = state.engine,
                        busy = state.busy || state.generating,
                        onLoad = { scope.launch { controller.load(model.name) } },
                        onUnload = { scope.launch { controller.unload() } },
                        onDelete = { pendingDelete = model.name },
                    )
                }

                if (state.engine == EngineState.UNAVAILABLE) {
                    item(key = "no-engine") {
                        Text(
                            LocalAiWords.NO_ENGINE_NOTE,
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid,
                        )
                    }
                }

                if (chatVisible) {
                    item(key = "chat") {
                        ChatHistoryPlate(state)
                    }
                }
            }

            item(key = "space-bottom") { Spacer(Modifier.height(12.dp)) }
        }

        // The composer lives OUTSIDE the scrolling list and after it, so it is
        // pinned just above the bottom of the screen. The root's `imePadding`
        // is what keeps this Column above the keyboard (MainActivity applies
        // it once, app-wide); a list item could be scrolled or clipped out of
        // the tree, and with the keyboard up that is exactly what used to
        // happen to the field and to Send. Never add a second `imePadding`
        // here - the root already pays that inset.
        if (chatVisible) {
            ChatComposer(
                state = state,
                draft = draft,
                onDraftChange = {
                    draft = it
                    controller.noteTyping()
                },
                onSend = { send() },
                onClear = { draft = "" },
                modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
            )
            Spacer(Modifier.height(8.dp))
        }
    }

    val deleteName = pendingDelete
    if (deleteName != null) {
        Dialog(onDismissRequest = { pendingDelete = null }) {
            Plate(Modifier.fillMaxWidth()) {
                Text(
                    LocalAiWords.DELETE,
                    style = MaterialTheme.typography.titleMedium,
                    color = chrome.textHi,
                )
                Gap(6)
                Text(
                    LocalAiWords.deleteQuestion(deleteName),
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textMid,
                )
                Gap(10)
                Row(horizontalArrangement = Arrangement.End, modifier = Modifier.fillMaxWidth()) {
                    Quiet(LocalAiWords.CANCEL, color = chrome.textMid) { pendingDelete = null }
                    Quiet(LocalAiWords.DELETE_YES, color = chrome.warnInk) {
                        pendingDelete = null
                        scope.launch { controller.deleteModel(deleteName) }
                    }
                }
            }
        }
    }
}

/** One model: what it is, whether it fits, and the three things to do with it. */
@Composable
private fun ModelRow(
    model: LocalAiModel,
    loaded: Boolean,
    engineState: EngineState,
    busy: Boolean,
    onLoad: () -> Unit,
    onUnload: () -> Unit,
    onDelete: () -> Unit,
) {
    val chrome = LocalChrome.current
    val fits = model.verdict.fits
    Plate {
        Text(
            model.name,
            style = MaterialTheme.typography.bodyLarge,
            color = chrome.textHi,
        )
        Gap(2)
        Text(
            LocalAiWords.modelDetail(model),
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textMid,
        )
        Gap(4)
        Text(
            model.verdict.words,
            style = MaterialTheme.typography.bodySmall,
            color = if (fits) chrome.textMid else chrome.warnInk,
        )
        if (!fits) {
            Gap(2)
            Text(
                LocalAiWords.TOO_BIG_ACTION,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
        }
        Gap(6)
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (loaded) {
                Secondary(LocalAiWords.UNLOAD, enabled = !busy, onClick = onUnload)
            } else {
                Primary(
                    if (engineState == EngineState.LOADING && busy) {
                        LocalAiWords.LOADING
                    } else {
                        LocalAiWords.LOAD
                    },
                    enabled = fits && !busy && engineState != EngineState.UNAVAILABLE &&
                        engineState != EngineState.LOADING,
                    onClick = onLoad,
                )
            }
            Spacer(Modifier.weight(1f))
            Quiet(LocalAiWords.DELETE, color = chrome.textMid, enabled = !busy, onClick = onDelete)
        }
    }
}

/** The conversation so far: a scrolling list item above the pinned composer. */
@Composable
private fun ChatHistoryPlate(state: LocalAiState) {
    val chrome = LocalChrome.current
    Plate {
        Kicker(LocalAiWords.CHAT)
        Gap(6)
        if (state.lines.isEmpty() && state.streamingText.isEmpty() && !state.generating) {
            Text(
                LocalAiWords.CHAT_EMPTY,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        }
        for (line in state.lines) {
            ChatLineView(line)
        }
        if (state.generating || state.streamingText.isNotEmpty()) {
            Text(
                if (state.streamingText.isEmpty()) LocalAiWords.THINKING else state.streamingText,
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textHi,
            )
        }
    }
}

/**
 * The pinned composer: the draft field, Send and Clear.
 *
 * It sits outside the scrolling list so the keyboard cannot take it away.
 * `maxLines = 3` rather than the list version's 4 because this box is pinned:
 * a four-line draft plus the button row would push the composer past the
 * space the keyboard leaves on a small phone.
 *
 * Clear discards the draft. The draft is `rememberSaveable` and survives
 * leaving the screen, which the 2026-11-13 field test found had no way out
 * except killing the app; it is placed beside Send so the row's height does
 * not change.
 */
@Composable
private fun ChatComposer(
    state: LocalAiState,
    draft: String,
    onDraftChange: (String) -> Unit,
    onSend: () -> Unit,
    onClear: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    Plate(modifier) {
        TextInput(
            value = draft,
            onValueChange = onDraftChange,
            placeholder = LocalAiWords.ASK_PLACEHOLDER,
            singleLine = false,
            maxLines = 3,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
            keyboardActions = KeyboardActions(onSend = { onSend() }),
        )
        Gap(6)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Primary(
                LocalAiWords.SEND,
                enabled = state.engine == EngineState.READY && !state.busy && draft.isNotBlank(),
                onClick = onSend,
            )
            Spacer(Modifier.width(6.dp))
            Quiet(
                LocalAiWords.CLEAR,
                color = chrome.textMid,
                enabled = draft.isNotEmpty(),
                onClick = onClear,
            )
        }
        Gap(6)
        Text(
            LocalAiWords.CHAT_NOTE,
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
    }
}

/** One message, and for the phone's replies the measured speed. */
@Composable
private fun ChatLineView(line: ChatLine) {
    val chrome = LocalChrome.current
    val fromPhone = line.from == ChatLine.From.PHONE
    Text(
        if (fromPhone) "On this phone" else "You",
        style = MaterialTheme.typography.labelSmall,
        color = if (fromPhone) chrome.textLo else chrome.textMid,
    )
    Text(
        line.text,
        style = MaterialTheme.typography.bodyMedium,
        color = chrome.textHi,
    )
    if (fromPhone) {
        Text(
            LocalAiWords.speedLine(line.tokensPerSecond),
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
        if (line.stoppedAtTimeLimit) {
            Text(
                LocalAiWords.HARD_CAP_SHORT,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
        }
    }
    Gap(6)
}

/** A notice line with a Dismiss, in the app's own plate shape. */
@Composable
private fun StatusLine(text: String, problem: Boolean, onDismiss: () -> Unit) {
    val chrome = LocalChrome.current
    Plate(tone = if (problem) chrome.warnInk.copy(alpha = 0.10f) else chrome.surface1) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text,
                style = MaterialTheme.typography.bodySmall,
                color = if (problem) chrome.warnInk else chrome.textMid,
                modifier = Modifier.weight(1f),
            )
            Quiet("Dismiss", color = chrome.textMid, onClick = onDismiss)
        }
    }
}

/** The SAF document's display name and reported size, or null when it has no name. */
private fun queryPicked(resolver: ContentResolver, uri: Uri): Picked? {
    var name: String? = null
    var size: Long? = null
    runCatching {
        resolver.query(
            uri,
            arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE),
            null,
            null,
            null,
        )?.use { cursor ->
            if (cursor.moveToFirst()) {
                val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (nameIndex >= 0) name = cursor.getString(nameIndex)
                val sizeIndex = cursor.getColumnIndex(OpenableColumns.SIZE)
                if (sizeIndex >= 0 && !cursor.isNull(sizeIndex)) size = cursor.getLong(sizeIndex)
            }
        }
    }
    val fallback = uri.lastPathSegment?.substringAfterLast('/')
    val chosen = (name ?: fallback)?.trim()
    if (chosen.isNullOrEmpty()) return null
    return Picked(chosen, size)
}

private data class Picked(val name: String, val size: Long?)

/** Twice a second is enough for a five-minute rule and cheap for the battery. */
private const val TICK_MILLIS = 500L
