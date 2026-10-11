package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Row
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.jarvis.client.net.ChatHistory
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "A new conversation starts after ..." (the audit of 2026-10-08): how long a
 * conversation can sit idle before the next question starts a new one - the one
 * timing the owner could not change anywhere, because it was a constant in each
 * client and nothing else.
 *
 * A CLIENT-SIDE choice, saved on THIS PHONE only ([ChatHistory.IDLE_NEW_KEY],
 * com.jarvis.client.data.ClientSettings): the PC serves no route for it
 * (`backend/jarvis_limits.py` says so in its own words), so there is no
 * request, no approval card and no stale-link hold here - one tap is one
 * change. The desktop keeps its own choice of the same five, with the same
 * ids and numbers (jarvis-desktop/src/chat-history.js).
 *
 * 30 minutes is the DEFAULT and stays the default: a missing, empty, unknown or
 * unreadable stored value reads as 30 minutes, never as "never"
 * ([ChatHistory.idleNewChoice]). The owner's decision of 2026-09-28 is
 * unchanged - the old conversation stays in History, and "Continue this chat"
 * brings it back. The "Never" row says plainly what it means: a conversation
 * then only ends when the owner starts a new one.
 */
@Composable
internal fun IdleNewSection(choice: String, onChange: (String) -> Unit) {
    val chrome = LocalChrome.current
    // A value this build does not know draws as the default it really is, so the
    // tick is always on a row the owner can see.
    val chosen = ChatHistory.idleNewChoice(choice)
    Section(ChatHistory.IDLE_NEW_TITLE) {
        Plate {
            Text(
                ChatHistory.IDLE_NEW_DETAIL,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            ChatHistory.IDLE_NEW_CHOICES.forEach { c ->
                Gap(8)
                val inUse = c.id == chosen
                Row(verticalAlignment = Alignment.CenterVertically) {
                    // "(in use)" as well as the colour: not by colour alone.
                    Text(
                        if (inUse) "${c.label} (in use)" else c.label,
                        style = MaterialTheme.typography.titleSmall,
                        color = if (inUse) chrome.okInk else chrome.textHi,
                        modifier = Modifier.weight(1f),
                    )
                    if (!inUse) {
                        Quiet("Use this", onClick = { onChange(c.id) })
                    }
                }
                Text(c.why, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
            Gap(8)
            Text(
                ChatHistory.IDLE_NEW_TAIL,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
        }
    }
}
