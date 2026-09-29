package com.jarvis.client

/**
 * The two app-icon shortcuts that ask Jarvis a question (res/xml/shortcuts.xml):
 * "Brief me now" and "What did I miss?". Pure, so `AppShortcutsTest` can
 * check it without a phone.
 *
 * Both used to open Brain at the top (phone walk-through, 2026-09-27), with
 * the briefing somewhere below the fold - the owner long-pressed "Brief me
 * now" and got a screen full of other things instead of a briefing. Now each
 * one asks its fixed sentence on Home, exactly as if the owner had typed it
 * into the box and pressed Send (`ChatSession.send`, the composer's own
 * path), and the answer appears where every answer does.
 *
 * Why these two sentences are safe to send from a shortcut: both are on the
 * "Things you can say" list ([com.jarvis.client.net.Sayable.SENTENCES],
 * held to the backend by SayableContractTest), and both are answered on the
 * PC WITHOUT the AI model by jarvis_quick.py's own grammar - "brief me now"
 * puts a briefing together and "what did I miss?" lists what happened since
 * the owner last looked. Both only read; neither changes a setting, raises a
 * card or approves anything. The briefing's one side effect - a calendar it
 * quotes is marked as read - is the same one the "Brief me now" button on
 * Brain already has.
 *
 * MainActivity is exported (it is the launcher's), so any app on the phone
 * could fire these actions, exactly as it already could fire the widget's
 * Talk and Note actions. The worst that does is ask one of these two
 * read-only questions, and the answer is shown on this phone's own screen,
 * behind App lock: MainActivity waits until the app is unlocked before
 * sending anything.
 */
object AppShortcuts {

    /** The "Brief me now" shortcut. */
    const val ACTION_ASK_BRIEF = "com.jarvis.client.action.ASK_BRIEF_ME"

    /** The "What did I miss?" shortcut. */
    const val ACTION_ASK_MISSED = "com.jarvis.client.action.ASK_WHAT_DID_I_MISS"

    /** jarvis_sayable.SENTENCES' own words, character for character. */
    const val BRIEF_ME = "Brief me now."
    const val WHAT_DID_I_MISS = "What did I miss?"

    /** The sentence a shortcut's intent action asks, or null for any other action. */
    fun questionFor(action: String?): String? = when (action) {
        ACTION_ASK_BRIEF -> BRIEF_ME
        ACTION_ASK_MISSED -> WHAT_DID_I_MISS
        else -> null
    }
}
