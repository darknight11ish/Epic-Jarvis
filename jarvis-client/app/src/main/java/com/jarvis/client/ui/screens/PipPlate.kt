package com.jarvis.client.ui.screens

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.jarvis.client.data.PipMode
import com.jarvis.client.data.PipWords
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Picture-in-picture" (Settings -> This app; `data/PipMode.kt`,
 * `docs/PIP-DESIGN.md` §2.1): a small Jarvis window that stays on screen while
 * the owner uses other apps - Android's own picture-in-picture, like the
 * next-turn box in Maps.
 *
 * Its own row, next to "Floating Jarvis" - the owner's choice of 2026-10-11
 * (§9.3), over folding it into that row as a third value. The two are separate
 * and may BOTH be on (§2.2): the floating face is a way to talk to Jarvis
 * without opening it; this is a way to see something after leaving it. Nothing
 * here turns the other setting off - and the plate says what happens on screen
 * when both are on, rather than pretending they never meet.
 *
 * Saved on this phone only ([com.jarvis.client.data.ClientSettings.pipMode], key
 * `pip_mode`), so unlike most of this screen it never checks `canAct`.
 *
 * The four values are the design's table (§2.1): Off, the face and the answer
 * (the default), the conversation, and Jarvis Live. [Choices] is the same
 * control the Floating Jarvis row and the Security screen already use - no new
 * control was invented for this row.
 */
@Composable
internal fun PipSection(
    mode: PipMode,
    onModeChange: (PipMode) -> Unit,
) {
    val chrome = LocalChrome.current
    Section(PipWords.TITLE) {
        Plate {
            Text(
                "A small Jarvis window that stays on screen while you use other apps - like the " +
                    "next-turn box in Google Maps. It can never approve anything. Tapping it brings " +
                    "Jarvis back.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(10)
            Choices(
                options = PipMode.entries,
                isSelected = { it == mode },
                label = { it.label },
                onPick = onModeChange,
            )
            Gap(10)
            when (mode) {
                PipMode.OFF -> Text(
                    "Off. Leaving Jarvis just puts it in the background.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
                PipMode.FACE -> Text(
                    "The face, one word for what Jarvis is doing, and the first line of the newest " +
                        "answer. Only the first line - a longer answer stays in Jarvis.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
                PipMode.THREAD -> Text(
                    "The last few messages, the newest at the bottom. The window scrolls if you " +
                        "drag it; there is no box to type in, so a stray tap cannot send anything.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
                PipMode.LIVE -> Text(
                    "Jarvis Live at its smallest: whether it is listening, and Mute and End. If Live " +
                        "is not running the window shows the face with a line saying so - it does not " +
                        "close. While a Live session runs it takes the window whatever is chosen above, " +
                        "and gives it back when Live ends.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
            }
            Gap(10)
            // §5, in the owner's own words rather than a claim in code: the
            // window is a glance, not a decision, and it cannot be a second
            // Settings screen either.
            Text(
                "It never approves anything and it cannot change a setting: a card still waits for " +
                    "you in Jarvis, and the notification is unchanged. It also shows nothing while " +
                    "Jarvis is locked or \"Hide memory lists and chat history\" is on - it says " +
                    "\"${PipWords.LOCKED}\" instead, so an empty window never looks like a broken one.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textLo,
            )
            Gap(8)
            // §2.2, said plainly (§8's own risk note asks for exactly this):
            // both can be on, and what the owner will actually see.
            Text(
                "Floating Jarvis and this can both be on. While this window is up, the floating face " +
                    "hides itself and comes back when the window closes - one Jarvis on screen, and " +
                    "it is the one showing you something. A bubble lives in Android's own bubble " +
                    "stack, so a bubble may still be there too.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textLo,
            )
            Gap(8)
            Text(
                "Android draws the small window itself: it has its own close button and its own " +
                    "Expand, and Jarvis cannot change how they look. Everything here is drawn inside " +
                    "the box Android gives it.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
        }
    }
}
