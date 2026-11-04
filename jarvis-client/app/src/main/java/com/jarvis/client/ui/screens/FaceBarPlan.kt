package com.jarvis.client.ui.screens

/**
 * The full-screen face bar's three cells (2026-11-02), and the one rule for
 * the words its typing box shows (2026-11-04).
 *
 * The bar is a row of three: the two left labels ("Show chat" and "More"), the
 * 48dp microphone, and the typing box with Stop. Each side cell is given half
 * of what is left beside the microphone (the same `Modifier.weight(1f)` on
 * both), so the microphone stays exactly in the middle. Since 2026-11-04 the
 * box also takes its whole cell instead of a fixed 48-96dp width, which is what
 * the owner asked for - "i want the blank box in this screenshot in the bottom
 * right corner to take up rhe remaining exmptyspace around it" - with the words
 * "Ask Jarvis" in it while it is empty.
 *
 * WHY IT IS A SEPARATE, PLAIN FILE. A Compose screen cannot be driven from this
 * project's JVM unit tests, so what a test can hold is numbers and one
 * predicate: [boxWidthDp] is what the bar's own weights come to at a given bar
 * width, and [placeholderVisible] is when the box shows [ASK_WORDS]. Plain
 * `Float`/`Boolean`/`String` values and no Compose types, so the test needs no
 * Android.
 *
 * [boxWidthDp] DOES NOT DECIDE THE WIDTH. The bar's `Row` does, with
 * `Modifier.weight(1f)` on the box, so the box follows whatever width the phone
 * gives it. [boxWidthDp] says what that weight comes to, so a test can prove
 * the box never narrows past a usable 48dp on the narrowest phone this app
 * supports, with Stop showing. `PhoneFaceBarTest` pins the modifier itself as
 * well, so this description cannot drift away from the layout in silence.
 *
 * What this does NOT answer is the LEFT cell: at the owner's larger text size
 * two labels need more than one side (about 159dp at 1.3x against 144dp at
 * 360dp), so they wrap onto two lines inside that cell rather than being cut -
 * see `VoiceBar`. The numbers here are what the box gets; they are not a claim
 * that the whole bar fits at every text size.
 */
internal object FaceBarPlan {

    /** The microphone's own width - `VoiceButton` is `size(48.dp)`. */
    const val MIC_DP = 48f

    /** The inset the box's own cell keeps before it, beside the microphone. */
    const val GAP_DP = 8f

    /** "Stop"'s own touch target, which the box's cell always leaves room for. */
    const val STOP_DP = 48f

    /**
     * The box's own 48dp touch target: the width below which the arithmetic
     * says the box has stopped being usable.
     *
     * It is not a clamp - the layout is whatever the phone measures - it is the
     * floor [PhoneFaceBarTest] holds the bar to at the narrowest phone this app
     * supports (320dp), where [boxWidthDp] still has 20dp of room above it even
     * while Stop is showing.
     */
    const val TYPE_MIN_DP = 48f

    /**
     * The words the empty box shows (the owner's ask of 2026-11-04: "with the
     * wording \"Ask Jarvis\" present"). The same words the chat's own box shows
     * above itself when it is empty, so the two boxes say the same thing.
     */
    const val ASK_WORDS = "Ask Jarvis"

    /**
     * Whether the box shows [ASK_WORDS]: while it holds nothing and the owner
     * is not in it.
     *
     * Tapping the box puts the cursor in it and opens the keyboard, and that is
     * exactly when the words go - "but it disseapars affer i tap the box". A
     * tap that leaves an empty box focused therefore shows NO words: an empty
     * box with a cursor in it is one the owner is about to type in, not an
     * invitation. They come back once the box is empty again and focus has
     * moved out of it.
     *
     * `isBlank`, not `isEmpty`, because the send path already treats a box of
     * spaces as nothing to send (`text.isNotBlank()` in `VoiceBar`): a box that
     * cannot send anything is empty, and should say so.
     */
    fun placeholderVisible(text: String, focused: Boolean): Boolean = text.isBlank() && !focused

    /** One side of the microphone: what each cell has when the two are equal. */
    fun sideDp(availableDp: Float): Float = ((availableDp - MIC_DP) / 2f).coerceAtLeast(0f)

    /**
     * The width the bar's own `weight(1f)` gives the box in [availableDp] of
     * bar, where `availableDp` is the bar's content width (the caller's 12dp
     * side padding already taken off).
     *
     * The box takes its whole cell, which is [sideDp], minus the [GAP_DP] inset
     * the cell keeps before it, minus [STOP_DP]'s room while [streaming] puts
     * Stop at the right edge. At 360dp that is 136dp on its own and 88dp while
     * an answer streams; at 320dp, 116dp and 68dp.
     *
     * Stop's real width is its own text plus its padding, so at a large text
     * size it can be a few dp wider than [STOP_DP] and the box a few dp
     * narrower than this; what the test holds is the floor, and the narrowest
     * supported phone still clears it by 20dp.
     */
    fun boxWidthDp(availableDp: Float, streaming: Boolean): Float =
        sideDp(availableDp) - GAP_DP - (if (streaming) STOP_DP else 0f)
}
