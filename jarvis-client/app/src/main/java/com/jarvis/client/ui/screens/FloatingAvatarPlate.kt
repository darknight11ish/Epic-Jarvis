package com.jarvis.client.ui.screens

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.jarvis.client.data.FloatingAvatarMode
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Floating Jarvis" (Settings -> This app; `data/FloatingAvatar.kt`,
 * `docs/JARVIS-API.md` section 56): a small avatar that stays on screen
 * while using other apps, so the owner can talk to Jarvis without switching
 * back to it. Voice only - no text box, and it never asks for anything or
 * shows a card; it only opens the real app.
 *
 * Saved on this phone only ([com.jarvis.client.data.ClientSettings.floatingAvatar]);
 * nothing here reaches the PC, so unlike most of this screen it never checks
 * `canAct`.
 *
 * The Overlay option asks for a real system permission, and CLAUDE.md's
 * whole style is to explain a technical thing before asking for it - so the
 * plain-language paragraph below is shown BEFORE [onRequestOverlay] is ever
 * called, never after.
 */
@Composable
internal fun FloatingAvatarSection(
    mode: FloatingAvatarMode,
    onModeChange: (FloatingAvatarMode) -> Unit,
    /** `Settings.canDrawOverlays(context)`, re-read on resume - the phone can revoke it any time. */
    overlayGranted: Boolean,
    /** Opens Android's own "draw over other apps" screen for this app. */
    onRequestOverlay: () -> Unit,
    /** Opens Android's own per-app "Allow bubbles" screen for this app. */
    onOpenBubbleSettings: () -> Unit,
) {
    val chrome = LocalChrome.current
    Section("Floating Jarvis") {
        Plate {
            Text(
                "A small Jarvis avatar that stays on your screen while you use other " +
                    "apps. Voice only - there is no text box on it, and it cannot change a " +
                    "setting or approve a card. Say \"open a chat\" (or tap it) to bring up " +
                    "the real app.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(10)
            Choices(
                options = FloatingAvatarMode.entries,
                isSelected = { it == mode },
                label = { it.label },
                onPick = onModeChange,
            )
            Gap(10)
            when (mode) {
                FloatingAvatarMode.OFF -> Text(
                    "Off. Nothing floats over other apps.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
                FloatingAvatarMode.BUBBLE -> BubbleExplainer(onOpenBubbleSettings)
                FloatingAvatarMode.OVERLAY -> OverlayExplainer(overlayGranted, onRequestOverlay)
            }
            Gap(8)
            Text(
                "Either way, it only works while \"Listen on this phone\" is on (Settings, " +
                    "Voice - the wake-word switch below the desktop's own). With that off there is " +
                    "nothing for the avatar to hear, and it says so plainly rather than " +
                    "sitting there looking like it is listening.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textLo,
            )
        }
    }
}

/**
 * Android's own chat-bubble notification (`Notification.BubbleMetadata`). No
 * dialog from this app - the one thing standing in the way is Android's own,
 * separate "Allow bubbles" switch for Jarvis, which nothing in this app can
 * flip for the owner. Said plainly rather than glossed over: the bubble may
 * simply not appear until that switch, too, is on.
 */
@Composable
private fun BubbleExplainer(onOpenBubbleSettings: () -> Unit) {
    val chrome = LocalChrome.current
    Text(
        "Ties into the same notification \"Listen on this phone\" already shows: it " +
            "gets a small floating circle you can drag around, that opens into a " +
            "little Jarvis window. Android also has its own switch for this, " +
            "separate from Jarvis's - \"Allow bubbles\" - and it can be off even " +
            "when everything here is right.",
        style = MaterialTheme.typography.bodySmall,
        color = chrome.textMid,
    )
    Gap(8)
    Quiet("Check Android's bubble setting for Jarvis", onClick = onOpenBubbleSettings)
    Gap(8)
    // Android 17 (docs/JARVIS-API.md section 81.4). Help only: nothing in
    // this app changed. MainActivity is resizeable, which that feature needs.
    Text(
        ANDROID_17_BUBBLE_LINE,
        style = MaterialTheme.typography.bodySmall,
        color = chrome.textLo,
    )
}

/**
 * Android 17's own "Bubble" for any app: long-press the app icon. Not
 * checked on a real phone yet, so it says "try".
 */
internal const val ANDROID_17_BUBBLE_LINE =
    "On Android 17 and later you can also try Android's own way: touch and hold " +
        "the Jarvis app icon and choose \"Bubble\". If that option is not there, " +
        "your phone does not offer it."

/**
 * `TYPE_APPLICATION_OVERLAY` - a window Jarvis draws on top of every other
 * app. Explained, in full, before [onRequestOverlay] is ever called: what
 * the permission means, why Jarvis wants it, and the honest caveat that
 * Android shows its own warning screen for it too, because some
 * advertising-heavy apps have misused exactly this permission.
 */
@Composable
private fun OverlayExplainer(granted: Boolean, onRequestOverlay: () -> Unit) {
    val chrome = LocalChrome.current
    if (granted) {
        Text(
            "Allowed. A small draggable Jarvis avatar sits on top of whatever app " +
                "you are using.",
            style = MaterialTheme.typography.bodySmall,
            color = chrome.okInk,
        )
        return
    }
    Text(
        "\"Draw over other apps\" lets Jarvis paint a small window on top of " +
            "whatever you are looking at - the same permission a video-call app's " +
            "floating picture uses. Jarvis asks for it only to show the avatar " +
            "itself; it cannot see or touch anything else on your screen with it.",
        style = MaterialTheme.typography.bodySmall,
        color = chrome.textMid,
    )
    Gap(6)
    Text(
        "Some ad-heavy apps have misused this same permission to cover your " +
            "screen with things you did not ask for, so Android shows its own " +
            "warning screen before you can turn it on for any app, Jarvis " +
            "included. That warning is Android's, not a sign Jarvis is doing " +
            "something wrong.",
        style = MaterialTheme.typography.bodySmall,
        color = chrome.textMid,
    )
    Gap(8)
    Quiet("Allow \"draw over other apps\"", onClick = onRequestOverlay)
}
