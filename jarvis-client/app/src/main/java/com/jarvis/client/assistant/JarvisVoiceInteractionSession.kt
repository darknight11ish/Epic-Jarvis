package com.jarvis.client.assistant

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.service.voice.VoiceInteractionSession
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.MainActivity
import com.jarvis.client.net.ScreenLook

/**
 * The session a long-press of home, or an OEM's assist gesture, creates.
 *
 * WHAT IT DOES: opens [MainActivity], as it always has - and, only when the
 * owner turned on "Let the assistant gesture read the screen" (Settings,
 * Security; off by default, and turning it on asked for the fingerprint or
 * PIN), it first waits for Android to hand over the screen in front, so the
 * next question can be about it ("Look at this", the owner's decision of
 * 2026-09-28, docs/SCREEN-DESIGN.md section 3). It listens to nothing, draws
 * no window and records no audio: "rule: no client-side speech-to-text" holds
 * exactly as before.
 *
 * THE WAIT. The system delivers the screen AFTER [onShow], through
 * [onHandleAssist] (`AssistState`: the text and layout of the app in front).
 * Before this feature the session finished at once, which is why nothing was
 * ever received. Now, with the setting on, it stays open until the screen
 * arrives, or [WAIT_MS] - then hands over to [MainActivity] and finishes. With
 * the setting off it finishes at once, exactly as before.
 *
 * WHAT IS READ ([LookGate]): the app in front is checked against the Never
 * look at list (Jarvis, password managers, bank-looking apps and the owner's
 * own) BEFORE any word is kept; password fields and the words in them are left
 * out ([com.jarvis.client.net.ScreenText]); an app that blocks assistance
 * (`FLAG_SECURE`) gives nothing. What is kept is held in memory
 * ([ScreenLook]) for two minutes of follow-up questions, and goes only to the
 * PC, inside the next question, where it is labelled outside text. A screenshot
 * is never asked for ([onHandleScreenshot] is not overridden: the phone's
 * "Use screenshot" setting is not used - words only, until the PC has the
 * 12 GB card and picture understanding is measured).
 *
 * UNVERIFIED on a real phone: how complete the screen text is on Android
 * 14/15, on GrapheneOS, and for Compose, Flutter or web content (the design
 * says so).
 */
class JarvisVoiceInteractionSession(
    // Stored explicitly: a primary-constructor parameter with no val/var is
    // only in scope for property initialisers, not for member functions
    // like onShow() below - it has to be a real property to be usable there.
    private val appContext: Context,
) : VoiceInteractionSession(appContext) {

    private val handler = Handler(Looper.getMainLooper())

    /** True from [onShow] until the screen arrived, or the wait ran out. */
    private var waiting = false

    /** The first screen delivered, kept only in case none is marked focused. */
    private var firstSeen: AssistState? = null

    private val giveUp = Runnable { finishWith(null) }

    /**
     * Turns the session's own window off before it can ever be created.
     *
     * Without this there is a visible blank flash on every assist
     * invocation. `doShow()` runs `ensureWindowAdded()` -> `onShow()` ->
     * `showWindow()`, and `finish()` is an async IPC to the system service -
     * so the session's scrim window (with an empty content frame, since this
     * class draws no UI of its own) is added and shown AFTER `onShow`
     * returns, and is only torn down when the finish round-trips. The user
     * sees a dim empty overlay on top of MainActivity launching.
     *
     * `setUiEnabled` only takes effect while the window is not yet visible,
     * which is exactly why this belongs in `onCreate` and not in `onShow`.
     */
    override fun onCreate() {
        super.onCreate()
        setUiEnabled(false)
    }

    override fun onShow(args: Bundle?, showFlags: Int) {
        super.onShow(args, showFlags)
        handler.removeCallbacks(giveUp)
        waiting = false
        firstSeen = null
        val withScreen = (showFlags and SHOW_WITH_ASSIST) != 0
        if (!LookGate.readingOn()) {
            // As before this feature: open Jarvis and end at once.
            openJarvis(withLook = false)
            finish()
            return
        }
        if (!withScreen) {
            // Reading is on, but Android is not handing screens to this
            // assistant: say so, instead of a silent nothing.
            JarvisRuntime.setNotice(LookGate.NO_SCREEN)
            openJarvis(withLook = true)
            finish()
            return
        }
        waiting = true
        handler.postDelayed(giveUp, WAIT_MS)
    }

    /**
     * The screen in front arrives (one call for the app in front; on some
     * phones one more for each app under it - only the focused one, or else
     * the first, is used).
     */
    override fun onHandleAssist(state: AssistState) {
        super.onHandleAssist(state)
        if (!waiting) return
        if (firstSeen == null) firstSeen = state
        val last = state.index >= state.count - 1
        if (state.isFocused) finishWith(state) else if (last) finishWith(firstSeen)
    }

    override fun onHide() {
        handler.removeCallbacks(giveUp)
        waiting = false
        firstSeen = null
        super.onHide()
    }

    private fun finishWith(state: AssistState?) {
        if (!waiting) return
        waiting = false
        handler.removeCallbacks(giveUp)
        val structure = state?.assistStructure
        firstSeen = null
        if (state == null) {
            // Nothing came within the wait.
            JarvisRuntime.setNotice(LookGate.NO_SCREEN)
            openJarvis(withLook = true)
            finish()
            return
        }
        val outcome = LookGate.decide(appContext, structure)
        when (outcome) {
            is LookGate.Outcome.Off -> Unit
            is LookGate.Outcome.Refused -> JarvisRuntime.setNotice(outcome.said)
            is LookGate.Outcome.Looked -> ScreenLook.hold(
                app = outcome.app,
                words = outcome.words.text,
                shown = false, // Jarvis shows the chip once it is open and unlocked
            )
        }
        openJarvis(withLook = outcome !is LookGate.Outcome.Off)
        finish()
    }

    /** Opens Jarvis; [withLook] tells it a look (or the reason for none) is waiting on Home. */
    private fun openJarvis(withLook: Boolean) {
        val intent = Intent(appContext, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        if (withLook) intent.action = MainActivity.ACTION_OPEN_LOOK
        // startAssistantActivity is the documented way for a voice
        // interaction session to hand off to a real activity - a plain
        // startActivity from here would not carry the assistant's own
        // launch semantics (which task it lands in, how it composes with
        // whatever was already on screen).
        runCatching { startAssistantActivity(intent) }
            .onFailure { runCatching { appContext.startActivity(intent) } }
    }

    private companion object {
        /** How long the screen may take to arrive before Jarvis opens without it. */
        const val WAIT_MS = 2_000L
    }
}
