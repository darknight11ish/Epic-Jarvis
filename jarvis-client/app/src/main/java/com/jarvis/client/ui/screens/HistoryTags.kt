package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ChatTags
import com.jarvis.client.ui.parts.Dot
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.TagIcon
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * The pieces of History's tags (docs/CHAT-TAGS-DESIGN.md sections 6 and 10):
 * the coloured section header, the filter chips, a row's tag and "Move to",
 * and the "Tags" editor. HistoryScreen.kt lays them out.
 *
 * Colour is never the only clue: every tag shows its ICON and its NAME (and,
 * in a header, its count). The colours are the shared eight, each with a
 * light and a dark ink that clears 4.5:1 on its own tint ([ChatTags]).
 */

/** A tag's ink for the current theme (light or dark ink from the shared table). */
@Composable
internal fun tagInk(colour: Int): Color {
    val dark = LocalChrome.current.dark
    return Color(0xFF000000.toInt() or ChatTags.ink(colour, dark))
}

/** The header tint: the ink at 12% (light) or 16% (dark), laid over the surface. */
@Composable
private fun tagTint(colour: Int): Color {
    val dark = LocalChrome.current.dark
    return tagInk(colour).copy(alpha = if (dark) ChatTags.TINT_DARK else ChatTags.TINT_LIGHT)
}

/** A tag as a small chip: icon, then name - for a row and for the "Move to" list. */
@Composable
internal fun TagChip(tag: ChatTags.Tag, modifier: Modifier = Modifier) {
    val ink = tagInk(tag.colour)
    Row(
        modifier
            .clip(RoundedCornerShape(50))
            .background(tagTint(tag.colour))
            .padding(horizontal = 9.dp, vertical = 4.dp)
            .semantics(mergeDescendants = true) { contentDescription = "Tag: ${tag.name}" },
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        TagIcon(tag.icon, ink, size = 14.dp)
        Text(tag.name, style = MaterialTheme.typography.labelSmall, color = ink, maxLines = 1)
    }
}

/**
 * One section's header: icon, name and count on the tint, a chevron in words
 * ("▾" open, "▸" shut). One control; TalkBack reads "Work, 12 chats,
 * collapsed" and it is a button.
 */
@Composable
internal fun TagSectionHeader(
    tag: ChatTags.Tag?,
    count: Int,
    expanded: Boolean,
    onToggle: () -> Unit,
) {
    val chrome = LocalChrome.current
    val name = tag?.name ?: ChatTags.UNTAGGED
    val ink = if (tag != null) tagInk(tag.colour) else chrome.textMid
    val tint = if (tag != null) tagTint(tag.colour) else chrome.surface1
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 48.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(tint)
            .pressable(role = Role.Button, onClick = onToggle)
            .padding(horizontal = 12.dp, vertical = 8.dp)
            .semantics(mergeDescendants = true) {
                contentDescription = ChatTags.headerSpoken(name, count, expanded)
            },
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        if (tag != null) TagIcon(tag.icon, ink)
        Text(
            ChatTags.header(name, count),
            style = MaterialTheme.typography.bodyMedium,
            color = ink,
            modifier = Modifier.weight(1f),
            maxLines = 1,
        )
        Text(if (expanded) "▾" else "▸", style = MaterialTheme.typography.bodyMedium, color = ink)
    }
}

/** "All" and one chip per tag: filters the list to one tag; "All" clears it. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun TagFilterChips(
    tags: List<ChatTags.Tag>,
    selected: String,
    onPick: (String) -> Unit,
) {
    val chrome = LocalChrome.current
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Quiet(
            if (selected.isEmpty()) "• ${ChatTags.ALL}" else ChatTags.ALL,
            color = if (selected.isEmpty()) chrome.textHi else chrome.textMid,
            modifier = Modifier.semantics {
                contentDescription = "Tag filter: ${ChatTags.ALL}" + if (selected.isEmpty()) ", chosen" else ""
            },
            onClick = { onPick("") },
        )
        tags.forEach { t ->
            val on = selected == t.id.toString()
            val ink = tagInk(t.colour)
            Row(
                Modifier
                    .heightIn(min = 48.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .pressable(role = Role.Button, onClick = { onPick(t.id.toString()) })
                    .padding(horizontal = 10.dp, vertical = 8.dp)
                    .semantics(mergeDescendants = true) {
                        contentDescription = "Tag filter: ${t.name}" + if (on) ", chosen" else ""
                    },
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(5.dp),
            ) {
                TagIcon(t.icon, ink, size = 16.dp)
                Text(
                    if (on) "• ${t.name}" else t.name,
                    style = MaterialTheme.typography.labelMedium,
                    color = ink,
                    maxLines = 1,
                )
            }
        }
    }
}

/**
 * "Move to": the tags and "No tag", as a plain list under the row (no popup,
 * so TalkBack walks it like any other list). The chat's own tag is marked.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun MoveToList(
    tags: List<ChatTags.Tag>,
    current: Int?,
    onPick: (Int?) -> Unit,
) {
    val chrome = LocalChrome.current
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        tags.forEach { t ->
            val here = t.id == current
            Row(
                Modifier
                    .heightIn(min = 48.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .pressable(role = Role.Button, onClick = { onPick(t.id) })
                    .padding(horizontal = 10.dp, vertical = 8.dp)
                    .semantics(mergeDescendants = true) {
                        contentDescription = "${ChatTags.MOVE_TO} ${t.name}" + if (here) ", current tag" else ""
                    },
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(5.dp),
            ) {
                TagIcon(t.icon, tagInk(t.colour), size = 16.dp)
                Text(
                    if (here) "• ${t.name}" else t.name,
                    style = MaterialTheme.typography.labelMedium,
                    color = tagInk(t.colour),
                    maxLines = 1,
                )
            }
        }
        Quiet(
            ChatTags.NO_TAG,
            color = if (current == null) chrome.textHi else chrome.textMid,
            enabled = current != null,
            modifier = Modifier.semantics {
                contentDescription = "${ChatTags.MOVE_TO}: ${ChatTags.NO_TAG}" + if (current == null) ", current" else ""
            },
            onClick = { onPick(null) },
        )
    }
}

/**
 * The "Tags" editor: add, rename, colour, icon, reorder, delete. Every change
 * is one request to the PC ([JarvisRuntime.tagsWrite]; no card, held on a
 * stale link) and [onChanged] reads the lists again afterwards. Deleting asks
 * first, in the shared words, and its chats become untagged.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun TagsEditor(
    view: ChatTags.View?,
    oldPc: Boolean,
    onChanged: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    var addText by remember { mutableStateOf("") }
    var openId by rememberSaveable { mutableStateOf<Int?>(null) }
    var renameText by remember { mutableStateOf("") }
    var confirmId by remember { mutableStateOf<Int?>(null) }

    fun send(json: String?, after: () -> Unit = {}) {
        if (json == null) {
            said = ChatTags.errorSentence("bad_name")
            return
        }
        busy = true
        said = null
        scope.launch {
            try {
                val w = JarvisRuntime.tagsWrite(json)
                if (w.ok) {
                    after()
                    onChanged()
                } else {
                    said = w.said ?: ChatTags.errorSentence(null)
                }
            } finally {
                busy = false
            }
        }
    }

    val tags = view?.tags.orEmpty()
    LazyColumn(
        modifier.fillMaxWidth(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "add") {
            Plate {
                if (oldPc) {
                    Text(ChatTags.OLD_PC, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                } else if (view == null) {
                    Text("Reading…", style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
                } else {
                    TextInput(
                        value = addText,
                        onValueChange = { addText = it.take(ChatTags.NAME_MAX) },
                        placeholder = ChatTags.NAME_PLACEHOLDER,
                        modifier = Modifier.semantics { contentDescription = ChatTags.ADD },
                    )
                    Gap(4)
                    Quiet(
                        ChatTags.ADD,
                        enabled = !busy && tags.size < ChatTags.MAX_TAGS && ChatTags.validName(addText) != null,
                        onClick = { send(ChatTags.addBody(addText)) { addText = "" } },
                    )
                    if (tags.size >= ChatTags.MAX_TAGS) {
                        Text(
                            ChatTags.errorSentence("too_many_tags"),
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textMid,
                        )
                    }
                }
                said?.let {
                    Gap(4)
                    Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk,
                        modifier = Modifier.liveStatus())
                }
            }
        }
        items(tags, key = { "tag-" + it.id }) { t ->
            val index = tags.indexOfFirst { it.id == t.id }
            val open = openId == t.id
            Plate {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TagIcon(t.icon, tagInk(t.colour))
                    Text(
                        t.name,
                        style = MaterialTheme.typography.bodyMedium,
                        color = tagInk(t.colour),
                        modifier = Modifier.weight(1f),
                    )
                    Text(
                        ChatTags.colourName(t.colour) + " · ${t.count}",
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                }
                Quiet(
                    if (open) "Done" else ChatTags.EDIT,
                    color = chrome.textMid,
                    modifier = Modifier.semantics { contentDescription = (if (open) "Close editing " else "Edit ") + t.name },
                    onClick = {
                        openId = if (open) null else t.id
                        renameText = t.name
                        confirmId = null
                        said = null
                    },
                )
                if (open) {
                    Gap(4)
                    TextInput(
                        value = renameText,
                        onValueChange = { renameText = it.take(ChatTags.NAME_MAX) },
                        placeholder = ChatTags.NAME_PLACEHOLDER,
                        modifier = Modifier.semantics { contentDescription = ChatTags.RENAME + " " + t.name },
                    )
                    Quiet(
                        ChatTags.RENAME,
                        enabled = !busy && ChatTags.validName(renameText) != null && renameText.trim() != t.name,
                        onClick = { send(ChatTags.renameBody(t.id, renameText)) },
                    )
                    Gap(4)
                    Text(ChatTags.COLOUR, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        ChatTags.COLOUR_NAMES.forEachIndexed { slot, colourName ->
                            val chosen = slot == t.colour
                            Row(
                                Modifier
                                    .heightIn(min = 48.dp)
                                    .clip(RoundedCornerShape(12.dp))
                                    .pressable(enabled = !busy, role = Role.Button, onClick = {
                                        if (!chosen) send(ChatTags.styleBody(t.id, colour = slot))
                                    })
                                    .padding(horizontal = 10.dp, vertical = 8.dp)
                                    .semantics(mergeDescendants = true) {
                                        contentDescription = "${ChatTags.COLOUR}: $colourName" + if (chosen) ", chosen" else ""
                                    },
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(5.dp),
                            ) {
                                Dot(tagInk(slot), size = 12)
                                Text(
                                    if (chosen) "• $colourName" else colourName,
                                    style = MaterialTheme.typography.labelMedium,
                                    color = chrome.textHi,
                                )
                            }
                        }
                    }
                    Gap(4)
                    Text(ChatTags.ICON, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        ChatTags.ICONS.forEach { icon ->
                            val chosen = icon == t.icon
                            Box(
                                Modifier
                                    .size(48.dp)
                                    .clip(RoundedCornerShape(12.dp))
                                    .then(
                                        if (chosen) Modifier.border(2.dp, tagInk(t.colour), RoundedCornerShape(12.dp))
                                        else Modifier,
                                    )
                                    .pressable(enabled = !busy, role = Role.Button, onClick = {
                                        if (!chosen) send(ChatTags.styleBody(t.id, icon = icon))
                                    })
                                    .semantics {
                                        contentDescription = "${ChatTags.ICON}: $icon" + if (chosen) ", chosen" else ""
                                    },
                                contentAlignment = Alignment.Center,
                            ) {
                                TagIcon(icon, tagInk(t.colour), size = 22.dp)
                            }
                        }
                    }
                    Gap(4)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Quiet(
                            ChatTags.MOVE_UP,
                            enabled = !busy && index > 0,
                            onClick = { send(ChatTags.moveUpBody(tags, t.id)) },
                        )
                        Quiet(
                            ChatTags.MOVE_DOWN,
                            enabled = !busy && index in 0 until tags.lastIndex,
                            onClick = { send(ChatTags.moveDownBody(tags, t.id)) },
                        )
                    }
                    Gap(4)
                    if (confirmId == t.id) {
                        Text(
                            ChatTags.deleteConfirm(t.name, t.count),
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.warnInk,
                        )
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Quiet("Yes, delete it", color = chrome.badInk, enabled = !busy, onClick = {
                                confirmId = null
                                send(ChatTags.deleteBody(t.id)) { openId = null }
                            })
                            Quiet("Keep it", onClick = { confirmId = null })
                        }
                    } else {
                        Quiet(
                            ChatTags.DELETE,
                            color = chrome.badInk,
                            enabled = !busy,
                            onClick = { confirmId = t.id },
                        )
                    }
                }
            }
        }
        item(key = "tail") { Gap(24) }
    }
}
