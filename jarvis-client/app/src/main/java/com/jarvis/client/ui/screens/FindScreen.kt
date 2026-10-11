package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.jarvis.client.net.MenuView
import com.jarvis.client.ui.FindAnything
import com.jarvis.client.ui.FindWords
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalRadii

/**
 * "Find anything" - the phone's typed search over every place in the app
 * (the parity audit of 2026-10-10, gap 8; the desktop's
 * `jarvis-desktop/src/palette.js`).
 *
 * EVERYTHING IT SHOWS COMES FROM THE APP ITSELF: [FindAnything] builds its
 * list from the same menu catalogue "Show or hide menus" reads and the same
 * `item(key = ...)` places "open <a place>" goes to. There is no second index
 * here to drift, and nothing on this screen is written by a model.
 *
 * IT NAVIGATES AND NOTHING ELSE. No switch, no value, no card and no request
 * to the PC is raised from here: a tap goes where the row says, exactly as if
 * the owner had walked there themselves. It is also held to the two hiding
 * rules - a menu the owner hid, and the memory lists and chat history while
 * "Hide memory lists and chat history" is on, are not in the list at all
 * ([FindAnything.visible]), which is stricter than the desktop's own palette.
 *
 * WHAT IT SAYS WHEN THERE IS NOTHING. With nothing typed it explains what it
 * searches rather than showing a blank screen; a search that matches nothing
 * says so in words, because a blank list reads as "that thing does not exist".
 */
@Composable
fun FindScreen(
    /** "Show or hide menus" and the memory-lists switch, as the other screens read them. */
    menus: MenuView,
    privateHidden: Boolean,
    /** Where a row goes. The screen navigates; nothing here opens by itself. */
    onOpen: (FindAnything.Row) -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    var query by rememberSaveable { mutableStateOf("") }

    val shown = remember(query, menus, privateHidden) {
        if (query.isBlank()) {
            FindAnything.all(menus, privateHidden)
        } else {
            FindAnything.results(query, menus, privateHidden)
        }
    }
    val searching = query.isNotBlank()

    Column(
        modifier
            .fillMaxSize()
            .background(chrome.surface0)
            .imePadding(),
    ) {
        TopBar(FindWords.TITLE, onBack)

        FindField(
            query = query,
            onQueryChange = { query = it },
            shown = shown.size,
            searching = searching,
        )

        if (shown.isEmpty()) {
            // Nothing matched, or the app has nothing to list at all - said in
            // words either way, never left as a blank page.
            Column(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 6.dp)) {
                Text(
                    if (searching) FindWords.NONE_TITLE else FindWords.EMPTY_TITLE,
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textHi,
                )
                Gap(6)
                Text(
                    if (searching) FindWords.NONE_BODY else FindWords.EMPTY_BODY,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
            }
        } else {
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 18.dp),
            ) {
                // With nothing typed, the count the desktop shows over its own
                // list. While a search is on, the line under the box carries it.
                if (!searching) {
                    item(key = "all-count") {
                        Text(
                            FindWords.allLine(shown.size),
                            style = MaterialTheme.typography.labelMedium,
                            color = chrome.textMid,
                        )
                    }
                }
                items(headed(shown), key = { it.second.id }) { (heading, row) ->
                    if (heading != null) {
                        Text(
                            heading,
                            style = MaterialTheme.typography.titleSmall,
                            color = chrome.textMid,
                            modifier = Modifier.padding(top = 8.dp).semantics { heading() },
                        )
                    }
                    FindRow(row, onOpen)
                }
                item(key = "bottom-space") { Spacer(Modifier.height(8.dp)) }
            }
        }
    }
}

/**
 * The rows with the heading each one is drawn under, worked out here rather
 * than counted inside the list: which heading a row gets comes off the
 * catalogue's own `area`/`kind` ([FindAnything.headingOf]), and a heading is
 * emitted only where it changes.
 */
private fun headed(rows: List<FindAnything.Row>): List<Pair<String?, FindAnything.Row>> {
    var last: String? = null
    return rows.map { row ->
        val heading = if (row.heading == last) null else row.heading
        last = row.heading
        heading to row
    }
}

/**
 * The box, in the same shape as every other field in this app - a flat sunken
 * box with a hairline edge and no Material container - with Clear beside it
 * and one line under it that says what the search found. The shape and the
 * colours are Settings' own box (`SettingsScreen.kt`, `SettingsSearchField`);
 * drawn here because that one is private to that screen and carries that
 * box's words, which are a different box's.
 *
 * The line under it is a polite live region, so TalkBack hears the count when
 * it changes - once per answer, because the words change only when the answer
 * does.
 */
@Composable
private fun FindField(
    query: String,
    onQueryChange: (String) -> Unit,
    shown: Int,
    searching: Boolean,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val radii = LocalRadii.current
    var focused by remember { mutableStateOf(false) }
    // The keyboard is up on arrival: this screen exists to be typed into.
    val focus = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { focus.requestFocus() } }

    Column(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .weight(1f)
                    .clip(radii.controlShape)
                    .background(chrome.surface2)
                    .border(
                        width = if (focused) 2.dp else 1.dp,
                        color = if (focused) accent else chrome.hairlineFocus,
                        shape = radii.controlShape,
                    )
                    .padding(14.dp, 12.dp),
            ) {
                if (query.isEmpty()) {
                    Text(
                        FindWords.PLACEHOLDER,
                        style = MaterialTheme.typography.bodyLarge,
                        color = chrome.textLo,
                    )
                }
                BasicTextField(
                    value = query,
                    onValueChange = onQueryChange,
                    singleLine = true,
                    textStyle = MaterialTheme.typography.bodyLarge.copy(color = chrome.textHi),
                    cursorBrush = SolidColor(accent),
                    modifier = Modifier
                        .fillMaxWidth()
                        .focusRequester(focus)
                        .onFocusChanged { focused = it.isFocused }
                        .semantics { contentDescription = FindWords.LABEL },
                )
            }
            if (query.isNotEmpty()) {
                Quiet(FindWords.CLEAR, onClick = { onQueryChange("") })
            }
        }
        Gap(6)
        Text(
            if (searching) FindWords.line(query, shown) else FindWords.SEARCHES,
            style = MaterialTheme.typography.labelMedium,
            color = chrome.textMid,
            modifier = Modifier.liveStatus(),
        )
    }
}

/** One place: what it is called, and the app's own one-line description of it. */
@Composable
private fun FindRow(row: FindAnything.Row, onOpen: (FindAnything.Row) -> Unit) {
    val chrome = LocalChrome.current
    Column(
        Modifier
            .fillMaxWidth()
            .clip(LocalRadii.current.cardShape)
            .background(chrome.surface1)
            .pressable(onClick = { onOpen(row) })
            .padding(14.dp),
    ) {
        Text(
            row.title,
            style = MaterialTheme.typography.titleSmall,
            color = chrome.textHi,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        if (row.about.isNotEmpty()) {
            Gap(2)
            Text(
                row.about,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        }
    }
}
