package com.jarvis.client.assistant

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.service.voice.VoiceInteractionSession
import com.jarvis.client.MainActivity

/**
 * The session a long-press of home, or an OEM's assist gesture, creates.
 *
 * Does nothing but open [MainActivity] and end itself immediately - no
 * custom session window, no on-screen UI of its own, no listening. That is
 * not a placeholder for something fuller later; it is the whole point.
 * `AndroidManifest.xml`'s own comment on the plain `ACTION_ASSIST`
 * intent-filter this supplements still holds word for word: "picking Jarvis
 * here just means... opens this activity like any other launch. Nothing
 * about what happens once it opens changes." Building a real
 * `VoiceInteractionSession` UI - a floating panel, an on-screen mic, a
 * transcript - would be a second, parallel entry point into this app with
 * its own state and its own edge cases, for a role most Android builds
 * already reach through the plain intent-filter. This class exists only so
 * the OEMs and gestures that require a `VoiceInteractionService` - not
 * just an `ACTION_ASSIST` activity - to appear in `RoleManager.ROLE_ASSISTANT`
 * have one to find.
 */
class JarvisVoiceInteractionSession(
    // Stored explicitly: a primary-constructor parameter with no val/var is
    // only in scope for property initialisers, not for member functions
    // like onShow() below - it has to be a real property to be usable there.
    private val appContext: Context,
) : VoiceInteractionSession(appContext) {

    override fun onShow(args: Bundle?, showFlags: Int) {
        super.onShow(args, showFlags)
        val intent = Intent(appContext, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        // startAssistantActivity is the documented way for a voice
        // interaction session to hand off to a real activity - a plain
        // startActivity from here would not carry the assistant's own
        // launch semantics (which task it lands in, how it composes with
        // whatever was already on screen).
        runCatching { startAssistantActivity(intent) }
            .onFailure { runCatching { appContext.startActivity(intent) } }
        // Ends the session the instant the handoff is requested - this
        // class does not sit around holding a session open for a UI it
        // never draws.
        finish()
    }
}
