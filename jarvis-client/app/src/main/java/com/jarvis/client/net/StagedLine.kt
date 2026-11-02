package com.jarvis.client.net

/**
 * The strip under the composer for a file or a picture that has been picked
 * but NOT sent: what it says, and when it must come back.
 *
 * A picked attachment rides with the NEXT question ([AttachFile],
 * [ChatPicture], docs/JARVIS-API.md section 163). Choosing it sends nothing,
 * and with no words typed Send is disabled - so the strip is the only thing
 * on screen. On 2026-11-02 the owner attached a photo and a document,
 * expected an analysis, and sent this screenshot: the two strips under the
 * chat, an empty box, and no answer. They read as Jarvis's reply because
 * nothing in them said they had not been sent.
 *
 * So every staged strip now opens with [HEAD] - the same sentence for a file
 * and a picture - and its action says [REMOVE]: the owner's own attachment is
 * removed, not a message dismissed.
 *
 * [comesBack] is the send half. A send returns null both when it failed (the
 * chat puts an error on screen, [com.jarvis.client.net.ChatSession.error]) and
 * when the owner pressed Stop. Stop is not a failure: the bytes were already
 * on their way, so the strip must not come back and invite a second copy. In
 * the failure case the question never reached the PC, and the bytes are held
 * nowhere else ([AttachFile]'s promise), so the strip is put back rather than
 * silently lost.
 */
object StagedLine {

    /**
     * The first sentence of every staged strip. It says the two things the
     * 2026-11-02 screen did not: nothing has been sent, and the next move is
     * the owner's - type the question, then press Send.
     */
    const val HEAD = "Attached to your next question \u2014 not sent yet. Type it and press Send."

    /** What the strip's action says: the attachment is removed, not a message. */
    const val REMOVE = "Remove"

    /**
     * Whether a staged attachment must be put back under the composer after
     * a send returns [answer].
     *
     * [answer] is the send's own return: null means it finished without an
     * answer. [errorShown] is what the chat put on screen for it - true only
     * for a real failure, never for the owner's Stop.
     */
    fun comesBack(answer: String?, errorShown: Boolean): Boolean = answer == null && errorShown
}
