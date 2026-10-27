package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.client.data.ChatPins
import com.jarvis.client.data.PinnedMessage
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.rememberTickingNow
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Pinned messages" (the owner's request of 2026-10-27: a pin that "can be
 * found easily in a new menu").
 *
 * The list the phone keeps itself ([com.jarvis.client.data.ChatPins],
 * [com.jarvis.client.data.PinnedChatStore]) - newest first, each row showing
 * the pinned words and which chat they came from, with Unpin and Open chat.
 * Open chat goes to History, opened at that one conversation: History is not
 * copied here (the same rule as the More menu's Earlier chats row), and a chat
 * the PC no longer keeps shows History's own sentence rather than a second
 * one invented here.
 *
 * "Hide memory lists and chat history" (Security) hides the list exactly as it
 * hides History's conversations and Brain's memory lists: [HiddenSection] with
 * a Show that asks for the fingerprint or PIN, then the rows. The title and
 * this screen's own way in stay visible, for the same reason History keeps its
 * settings visible - they say nothing about what is in the list.
 *
 * Nothing on this screen sends anything anywhere: unpinning is a local edit,
 * and opening a chat is History's own read.
 */
@Composable
fun PinnedScreen(
    /** The pins, newest first - [com.jarvis.client.data.ChatPins.newestFirst]. */
    pins: List<PinnedMessage>,
    onUnpin: (key: String) -> Unit,
    /** Opens that conversation in History. Called only for a pin with a chat id. */
    onOpenChat: (chatId: String) -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    /** "Hide memory lists and chat history" is on: the list stays hidden until Show. */
    privateHidden: Boolean = false,
    onShowPrivate: () -> Unit = {},
    showPrivateBusy: Boolean = false,
) {
    val chrome = LocalChrome.current
    // A ticking clock, so "2 minutes ago" does not sit there wrong for as long
    // as the screen is open. The same 15s beat Home's own freshness lines use.
    val now = rememberTickingNow(pins.size)

    Column(modifier.fillMaxSize().background(chrome.surface0)) {
        TopBar(
            ChatPins.TITLE,
            onBack,
            subtitle = if (pins.size == 1) "1 pinned message" else "${pins.size} pinned messages",
        )

        if (privateHidden) {
            HiddenSection(ChatPins.TITLE, busy = showPrivateBusy, onShow = onShowPrivate)
            return@Column
        }

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item(key = "lead") {
                Plate {
                    Text(
                        ChatPins.LEAD,
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                    )
                    Gap(4)
                    // The owner asked on 2026-10-27 where the old chats and the
                    // new ones are: said here, at the bottom of the list he
                    // opened to find his own pins, in the words of the menu.
                    Text(
                        ChatPins.WHERE_CHATS_ARE,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                }
            }

            if (pins.isEmpty()) {
                item(key = "empty") {
                    Text(
                        ChatPins.EMPTY,
                        style = MaterialTheme.typography.bodyMedium,
                        color = chrome.textMid,
                    )
                }
            }

            items(pins, key = { it.key }) { row ->
                PinRow(
                    row = row,
                    nowMs = now,
                    onUnpin = { onUnpin(row.key) },
                    onOpenChat = { onOpenChat(row.chatId) },
                )
            }
        }
    }
}

/**
 * One pinned message: its words, which chat and when, then Unpin and - only
 * when that chat has an id History can be asked for - Open chat.
 *
 * The words are cut at [ChatPins.ROW_TEXT] and the whole message is kept
 * behind them; nothing is re-fetched, and no control here rewrites the message
 * itself (editing it would quietly disagree with the answer it came from).
 */
@Composable
private fun PinRow(
    row: PinnedMessage,
    nowMs: Long,
    onUnpin: () -> Unit,
    onOpenChat: () -> Unit,
) {
    val chrome = LocalChrome.current
    Plate {
        Text(
            ChatPins.snippet(row.text),
            style = MaterialTheme.typography.bodyMedium,
            color = chrome.textHi,
        )
        Gap(4)
        Text(
            ChatPins.whereLine(row, nowMs),
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textMid,
        )
        Gap(6)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Quiet(ChatPins.UNPIN, color = chrome.textMid, onClick = onUnpin)
            if (ChatPins.opens(row)) {
                Quiet(ChatPins.OPEN_CHAT, color = chrome.textMid, onClick = onOpenChat)
            }
        }
    }
}
