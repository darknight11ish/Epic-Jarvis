package com.jarvis.client.data

/**
 * "Floating Jarvis" (Settings -> This app): a small Jarvis avatar that stays
 * on screen while using other apps, so the owner can talk to Jarvis without
 * switching back to it. Voice only - it never shows a text box, and it is
 * never a way to change a setting or approve a card; it only listens, shows
 * whether Jarvis is reachable, and opens the real app (`docs/JARVIS-API.md`
 * section 56).
 *
 * Off by default (this project's house style for anything new). Two ways to
 * turn it on, because they trade off differently and the owner said to build
 * both (2026-09-27) rather than pick one:
 *
 * - [BUBBLE]: Android's own chat-bubble notification (`Notification.BubbleMetadata`,
 *   API 30+). No extra permission dialog from this app - only Android's own
 *   per-app "Allow bubbles" switch, which this app cannot turn on for the
 *   owner (`FloatingAvatarPlate.kt` links to it). Tied to the existing
 *   "hey Jarvis" listening notification ([com.jarvis.client.service.WakeWordService]);
 *   with listening off there is nothing to bubble.
 * - [OVERLAY]: a window drawn on top of every app (`TYPE_APPLICATION_OVERLAY`),
 *   gated behind the owner granting "draw over other apps"
 *   (`Settings.ACTION_MANAGE_OVERLAY_PERMISSION`) - explained in plain words
 *   before that system screen opens, in [FloatingAvatarPlate.kt].
 *
 * Saved on this phone only ([ClientSettings.floatingAvatar]), like every
 * other display setting - nothing about it is sent to the PC.
 */
enum class FloatingAvatarMode(val wire: String, val label: String) {
    OFF("off", "Off"),
    BUBBLE("bubble", "Bubble"),
    OVERLAY("overlay", "Overlay"),
    ;

    companion object {
        fun fromWire(s: String?): FloatingAvatarMode = entries.firstOrNull { it.wire == s } ?: OFF
    }
}

/**
 * Whether [FloatingAvatarMode] should show real content (the link's state, a
 * short "listening"/"heard you" status) or stay neutral - no words, no
 * status, just an idle mark.
 *
 * Always `true`: App lock does not change what this surface shows (owner's
 * decision, 2026-09-27, cross-cutting audit finding #7 - matching the
 * desktop's own floating face, whose surfaceState keeps showing link,
 * approval and error state regardless of App lock). What it shows is only
 * connectivity and "am I listening right now" - never a word Jarvis heard,
 * said or is about, never an approval's own text, and there is no button to
 * act on any of it - so showing it while locked reveals nothing the desktop
 * doesn't already, and the widget and tray already show this much on the
 * PC while locked too.
 *
 * Tapping it always opens the real app, whose own App-lock screen decides
 * next - this only decides what the small floating surface itself may say
 * before that tap. The parameter is kept (rather than dropping it and every
 * caller's App lock argument) so a caller reads as "this is where App lock
 * was considered", not as if App lock was never thought about here.
 */
@Suppress("UNUSED_PARAMETER")
fun floatingAvatarShowsContent(appLockOn: Boolean): Boolean = true
