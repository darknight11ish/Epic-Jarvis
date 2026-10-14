package com.jarvis.client

/**
 * "The local model isn't running on your PC", said on the phone before and
 * without a question.
 *
 * WHY THIS EXISTS. On 2026-10-13 both of the owner's Ollama lanes (the
 * everyday model on 11436, the coding model on 11435) were dead from about
 * 16:30 until about 21:5x. Neither app said so. The PC's own `GET /api/status`
 * carried `"ollama": false` the whole time - the phone was asking for that
 * route already and simply had no field for it - and Jarvis only admitted it
 * when he asked a question, with the chat error `model_not_running`.
 *
 * IT IS ITS OWN STATE, not "Jarvis isn't connected" ([FaceShellRules.OFFLINE],
 * [LinkWords]). The two mean opposite things about the PC: "isn't connected"
 * is this phone unable to reach the PC at all, so nothing on it can be
 * trusted, while this one is the PC answering perfectly and its own model
 * server being down. The Home status line draws them in different colours for
 * the same reason - red for a link that is gone, amber for a PC that is
 * answering and cannot think.
 *
 * THE WORDS, and why these. The owner is a beginner developer learning as he
 * goes, so the sentence is plain and names no product in the status line; the
 * full line names Ollama once, in brackets, and only to say which program to
 * open. Calm, not alarming: a dead lane is not a crash, and the app carries on
 * and offers the rest of itself while it is dead. Nothing here acts - it does
 * not start, restart or change anything, on this phone or on the PC. The owner
 * starts his lanes; this tells him they are down.
 *
 * Pure, so [ModelWordsTest] can hold it to those rules without a phone.
 */
object ModelWords {

    /**
     * How often `JarvisRuntime.refreshModelState()` runs on its own, in
     * milliseconds, so the warning appears and clears without the owner doing
     * anything.
     *
     * Ninety seconds: the same number the two desktop windows use
     * (`jarvis-desktop/src/lane-warning.js` `HEALTH_BEAT_MS`), because all
     * three are watching one fact, and a phone and a PC disagreeing about how
     * often to look would only ever show as one of them being behind.
     *
     * It only runs on a connected link, and it is one small read of one route
     * that already answers a handful of other questions. The incident this
     * exists for lasted about five hours, so a minute and a half is far faster
     * than the thing it is watching changes, and slow enough not to be a
     * battery story.
     */
    const val POLL_MS = 90_000L

    /**
     * The warning on Home's own status line, after the state word - it reads
     * "Connected · Model not running". No stop, no exclamation, and no "PC":
     * the line it sits on is already about the PC.
     */
    const val HOME_SUFFIX = "Model not running"

    /**
     * The whole sentence, for anywhere with room for one - the same words the
     * desktop windows show (`jarvis-desktop/src/lane-warning.js`
     * `LANE_DOWN_WORDS`), so the two apps cannot come to different wording for
     * one fact.
     */
    const val DOWN =
        "The local model isn't running on your PC. Open Ollama on the PC, or run ollama serve there."

    /**
     * Whether [ollama] - `GET /api/status`'s own field, held by
     * [com.jarvis.client.net.StatusInfo.ollama] - is the PC saying its model is
     * not running.
     *
     * Only a plain `false` is. `true` is the model answering, and `null` is the
     * PC not having said - an older backend with no such field, or a read that
     * was refused or failed, which this field never fills in either way. Drawing
     * the warning from a null would be inventing a fact the PC never sent, and a
     * warning that appears when nothing is wrong is one the owner learns to
     * ignore - which is exactly how the five silent hours happened in the first
     * place.
     */
    fun isDown(ollama: Boolean?): Boolean = ollama == false

    /**
     * What to add to Home's status line while the model is down, or null while
     * it is not. The same one place the rest of that line is built
     * (`ui/screens/HomeScreen.kt` `StatusLine`).
     */
    fun homeSuffix(ollama: Boolean?): String? = if (isDown(ollama)) HOME_SUFFIX else null
}
