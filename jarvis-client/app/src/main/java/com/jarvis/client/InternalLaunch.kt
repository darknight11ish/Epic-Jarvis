package com.jarvis.client

import android.content.Context
import android.content.Intent
import java.security.MessageDigest
import java.security.SecureRandom

/**
 * Proof that a launch of [MainActivity] came from THIS app.
 *
 * Why this exists: MainActivity is exported (it is the launcher's activity),
 * so any other app on the phone can send it any intent action. Three actions
 * do real things - "start Jarvis Live" (opens the microphone), "resume Live"
 * and "open the Solve it here screen" - so they are honoured only when the
 * intent carries a secret only this app knows. This app's own Live tile,
 * "Live ended - Resume" notification and "a website needs you" alert put it
 * in their PendingIntents; nothing else can, because the secret sits in this
 * app's private storage.
 *
 * The secret is random, made once and kept (not per process): a notification
 * posted before the app was restarted still carries the same secret, so
 * tapping it still works. It is checked, never logged, never sent anywhere.
 *
 * Static launcher shortcuts (res/xml/shortcuts.xml) cannot carry a secret, so
 * none of them uses these actions: "Live" there is OPEN_LIVE, which only opens
 * the Live screen (the owner presses Start, behind App lock). START_VOICE
 * only opens Home; ASK_BRIEF_ME / ASK_WHAT_DID_I_MISS ask one fixed sentence
 * ([AppShortcuts]) and read no text from the intent; QUICK_NOTE only opens
 * the note box. None of them opens the microphone or sends anything else.
 *
 * The decision itself is pure ([decide]) so InternalLaunchTest can check it.
 */
object InternalLaunch {

    /** The intent extra that carries the secret. */
    const val EXTRA_PROOF = "com.jarvis.client.extra.INTERNAL_PROOF"

    private const val PREFS = "internal_launch"
    private const val KEY = "proof"

    /** What MainActivity should do with a Live/handoff intent. */
    enum class Launch { IGNORE, OPEN_LIVE_SCREEN, START_LIVE, RESUME_LIVE, OPEN_HANDOFF }

    /** True only if [presented] is non-empty and equals [expected] (compared in constant time). */
    fun proves(presented: String?, expected: String?): Boolean {
        if (presented.isNullOrEmpty() || expected.isNullOrEmpty()) return false
        return MessageDigest.isEqual(presented.toByteArray(), expected.toByteArray())
    }

    /**
     * What to do with an intent whose action is [action] and which carries
     * [presented] as its proof. [fresh] is false when the activity is being
     * re-created from saved state (a rotation must not start Live again).
     *
     * OPEN_LIVE (the notification / shortcut) is harmless and needs no proof.
     * START / RESUME without proof fall back to just opening the Live screen -
     * the owner then presses Start themselves. OPEN_HANDOFF without proof is
     * ignored.
     */
    fun decide(action: String?, presented: String?, expected: String?, fresh: Boolean): Launch {
        val ok = proves(presented, expected)
        return when (action) {
            MainActivity.ACTION_OPEN_LIVE -> Launch.OPEN_LIVE_SCREEN
            MainActivity.ACTION_START_LIVE ->
                if (ok && fresh) Launch.START_LIVE else Launch.OPEN_LIVE_SCREEN
            MainActivity.ACTION_RESUME_LIVE ->
                if (ok && fresh) Launch.RESUME_LIVE else Launch.OPEN_LIVE_SCREEN
            MainActivity.ACTION_OPEN_HANDOFF -> if (ok) Launch.OPEN_HANDOFF else Launch.IGNORE
            else -> Launch.IGNORE
        }
    }

    /** The secret, made on first use. */
    @Synchronized
    fun token(context: Context): String {
        val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        prefs.getString(KEY, null)?.takeIf { it.length >= 32 }?.let { return it }
        val bytes = ByteArray(32).also { SecureRandom().nextBytes(it) }
        val made = bytes.joinToString("") { "%02x".format(it) }
        prefs.edit().putString(KEY, made).apply()
        return made
    }

    /** Puts the proof on an intent this app is about to send to itself. Returns the same intent. */
    fun stamp(context: Context, intent: Intent): Intent = intent.putExtra(EXTRA_PROOF, token(context))
}
