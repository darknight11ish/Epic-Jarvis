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
 * The same reasoning the desktop's HUD window already runs on
 * (`docs/ARCHITECTURE.md` section 8: the HUD is covered by App lock, unlike
 * the widget, which stays visible but shows less): the floating avatar is
 * this app's OWN drawn surface, on top of every other app, not a launcher
 * widget - so while the owner has asked for App lock, it follows the HUD's
 * rule rather than the widget's. It does not disappear (Overlay and Bubble
 * both persist through everything else the owner does with the phone;
 * flickering in and out on every relock would be its own nuisance and,
 * unlike a window, cannot simply not be shown while still doing its job),
 * but it never shows a word Jarvis heard, said or is about, while locked.
 *
 * Tapping it always opens the real app, whose own App-lock screen decides
 * next - this only decides what the small floating surface itself may say
 * before that tap.
 */
fun floatingAvatarShowsContent(appLockOn: Boolean): Boolean = !appLockOn
