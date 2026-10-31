package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
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
import com.jarvis.client.net.Notes
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * The Notes editor on Mind - the whole Obsidian vault, from this phone
 * (`.dsh-scratch/NOTES-EDITOR-2026-10-31/CONTRACT.md`; the PC's half is
 * `jarvis_notes_edit.py`, the shapes are [com.jarvis.client.net.Notes]).
 *
 * The owner's decision, 2026-10-31, in his own words: **"The whole vault, both
 * apps"** - search and browse every note, open and edit any. This plate lists
 * the vault and opens one note into an editor. Save raises the PC's EXISTING
 * approval card (`edit_vault_note`, tier `ask`); this phone never approves it
 * and never writes the file itself. The line above the buttons is the PC's own
 * answer ([Notes.describe]): waiting / saved / denied / conflict, and only
 * `saved` ever says saved.
 *
 * No create, no delete, no rename in this slice (the contract's own limit).
 * Hidden lists and App lock keep their existing rules: [BrainScreen] draws
 * this plate only when the lists are shown, exactly as it draws the wiki's
 * plate (`privateHidden`), so nothing here is a new bypass.
 *
 * Reads and acts through [JarvisRuntime] directly, so [BrainScreen] needs one
 * line for it.
 */
@Composable
internal fun NotesSection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val job by JarvisRuntime.notesJob.collectAsState()

    var query by remember { mutableStateOf("") }
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Notes.View?>(null) }
    var listError by remember { mutableStateOf<String?>(null) }

    // The note being edited, and the text it was READ with: the difference
    // between them is the unsaved edit, and the read's sha256 is what the save
    // must start from (the PC refuses a stale one as `conflict`).
    var open by remember { mutableStateOf<Notes.Text?>(null) }
    var draft by remember { mutableStateOf("") }
    var readError by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }

    // Read the list when the plate opens, when Refresh is tapped, when the
    // search text settles, and when a save ends (the note's size and mtime
    // moved on the PC).
    val jobFinal = job?.second?.final
    LaunchedEffect(query, reads, jobFinal) {
        if (query.isNotEmpty()) delay(300)   // typing: one read, not one per key
        val r = JarvisRuntime.notesList(query)
        when (r) {
            is ApiResult.Ok -> {
                view = Notes.view(r.value)
                listError = null
            }
            is ApiResult.Failed -> listError = Notes.failure(r.error) ?: JarvisRuntime.noticeFor(r.error)
        }
    }

    // On a finished save, re-read the note: `saved` brings the new sha256 (the
    // next save must start from it), and a `conflict` is only worth acting on
    // with the newer text in hand. Denied and failed wrote nothing, so the
    // draft is kept exactly as it is.
    val said = job?.takeIf { it.first == open?.path }?.second
    LaunchedEffect(said?.final, said?.saved, said?.conflict, open?.path) {
        val note = open ?: return@LaunchedEffect
        if (said == null || !said.final) return@LaunchedEffect
        if (!said.saved && !said.conflict) return@LaunchedEffect
        when (val r = JarvisRuntime.notesRead(note.path)) {
            is ApiResult.Ok -> {
                val fresh = Notes.readNote(r.value)
                if (fresh != null) {
                    open = fresh
                    // A conflict keeps the owner's words on screen - only the
                    // hash is taken from the newer note, so a second Save is
                    // sent against the version the PC last had.
                    if (said.saved) draft = fresh.text
                }
            }
            is ApiResult.Failed -> readError = Notes.failure(r.error) ?: JarvisRuntime.noticeFor(r.error)
        }
        saving = false
    }

    Section("Notes", trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            val err = listError
            if (err != null) {
                Text(
                    "Couldn't read the notes: $err",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.warnInk,
                )
            }
            val note = open
            if (note == null) {
                NoteList(
                    query = query,
                    onQuery = { query = it },
                    view = view,
                    onOpen = { path ->
                        readError = null
                        saving = false
                        scope.launch {
                            when (val r = JarvisRuntime.notesRead(path)) {
                                is ApiResult.Ok -> Notes.readNote(r.value)?.let {
                                    open = it
                                    draft = it.text
                                } ?: run {
                                    readError = "The desktop's answer did not carry the note's text."
                                }
                                is ApiResult.Failed ->
                                    readError = Notes.failure(r.error) ?: JarvisRuntime.noticeFor(r.error)
                            }
                        }
                    },
                )
                readError?.let {
                    Gap(8)
                    Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                }
            } else {
                NoteEditor(
                    note = note,
                    draft = draft,
                    onDraft = { draft = it },
                    canAct = canAct,
                    saving = saving,
                    said = said,
                    readError = readError,
                    onSave = {
                        if (!saving) {
                            saving = true
                            readError = null
                            scope.launch {
                                // The PC answers waiting/saved/conflict/denied;
                                // the runtime follows the card. A refused
                                // request shows the runtime's own notesJob line.
                                if (!JarvisRuntime.saveNote(note.path, draft, note.sha256)) saving = false
                            }
                        }
                    },
                    onReload = {
                        readError = null
                        scope.launch {
                            when (val r = JarvisRuntime.notesRead(note.path)) {
                                is ApiResult.Ok -> Notes.readNote(r.value)?.let {
                                    open = it
                                    draft = it.text
                                } ?: run {
                                    readError = "The desktop's answer did not carry the note's text."
                                }
                                is ApiResult.Failed ->
                                    readError = Notes.failure(r.error) ?: JarvisRuntime.noticeFor(r.error)
                            }
                        }
                    },
                    onClose = {
                        open = null
                        draft = ""
                        readError = null
                        saving = false
                    },
                )
            }
        }
    }
}

/** The vault's note list, with its search box. */
@Composable
private fun NoteList(
    query: String,
    onQuery: (String) -> Unit,
    view: Notes.View?,
    onOpen: (String) -> Unit,
) {
    val chrome = LocalChrome.current
    TextInput(
        value = query,
        onValueChange = onQuery,
        label = "Search your notes",
        placeholder = "Part of a note's name or folder",
        singleLine = true,
    )
    Gap(10)
    val v = view
    if (v == null) {
        Text("Reading your notes…", style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
        return
    }
    if (v.notes.isEmpty()) {
        Text(
            if (query.trim().isEmpty()) {
                "No notes in the vault yet. This lists .md and .txt files in the Obsidian vault " +
                    "the PC is set up with."
            } else {
                "No note matches \"${query.trim()}\"."
            },
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textLo,
        )
        return
    }
    Text(
        if (v.truncated) {
            "Showing the newest ${Notes.MAX_LISTED} notes - use the search to find more."
        } else {
            "${v.count} note${if (v.count == 1) "" else "s"}"
        },
        style = MaterialTheme.typography.labelSmall,
        color = chrome.textMid,
    )
    Gap(6)
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        v.notes.forEach { note ->
            Column(Modifier.fillMaxWidth()) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        note.title,
                        style = MaterialTheme.typography.bodyMedium,
                        color = chrome.textHi,
                        modifier = Modifier.weight(1f),
                    )
                    Text(
                        Notes.sizeLabel(note.size),
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                }
                Text(
                    note.path,
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
                Quiet("Open", onClick = { onOpen(note.path) })
            }
        }
    }
}

/** One note, open for editing. */
@Composable
private fun NoteEditor(
    note: Notes.Text,
    draft: String,
    onDraft: (String) -> Unit,
    canAct: Boolean,
    saving: Boolean,
    said: Notes.Said?,
    readError: String?,
    onSave: () -> Unit,
    onReload: () -> Unit,
    onClose: () -> Unit,
) {
    val chrome = LocalChrome.current
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(
            note.path,
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textHi,
            modifier = Modifier.weight(1f),
        )
        Quiet("Close", onClick = onClose)
    }
    Gap(8)
    TextInput(
        value = draft,
        onValueChange = onDraft,
        label = "Note text",
        singleLine = false,
        maxLines = 14,
    )
    Gap(8)
    Text(
        "${draft.length} character${if (draft.length == 1) "" else "s"}",
        style = MaterialTheme.typography.labelSmall,
        color = chrome.textLo,
    )
    if (!canAct) {
        Gap(4)
        Text(Notes.STALE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    }
    readError?.let {
        Gap(6)
        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
    }
    said?.let {
        Gap(6)
        Text(
            it.text,
            style = MaterialTheme.typography.bodySmall,
            color = if (it.saved) {
                chrome.okInk
            } else if (it.final) {
                chrome.badInk
            } else {
                chrome.textHi
            },
            modifier = Modifier.liveStatus(),
        )
        if (it.conflict) {
            // Nothing was written. Reload takes the newer text and hash; the
            // owner's words are not overwritten until they tap it.
            Quiet("Reload the newer version", onClick = onReload)
        }
    }
    Gap(10)
    Primary(
        if (saving) "Saving…" else "Save",
        modifier = Modifier.fillMaxWidth(),
        busy = saving,
        onClick = onSave,
    )
    Gap(4)
    Text(
        "Save asks you first: one approval card on the PC, and nothing is written until you approve it. " +
            "Denied or expired leaves the note exactly as it was.",
        style = MaterialTheme.typography.labelSmall,
        color = chrome.textLo,
    )
}
