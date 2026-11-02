package com.jarvis.client.ui.screens

/**
 * The arithmetic of the full-screen face bar's three cells (2026-11-02).
 *
 * The bar is a row of three: the two left labels ("Show chat" and "More"), the
 * 48dp microphone, and the small typing box with Stop. The microphone stays
 * exactly in the middle only while the two sides are equal, so the box's
 * width is "one side, minus the gap before it, minus Stop's own 48dp" - and at
 * 360dp that is the 88dp the bar's own comment has always claimed.
 *
 * WHY IT IS A SEPARATE, PLAIN FILE. The width could only be reasoned about in
 * a JVM test as numbers, and `PhoneFaceBarTest` holds these at a computed
 * 360dp: the box is 88dp, the two sides are 144dp each, and the sum of box +
 * gap + Stop is exactly one side with nothing left to overlap the microphone.
 * Plain `Float` dp values and no Compose types, so the test needs no Android.
 *
 * What this does NOT answer is the LEFT cell: at the owner's larger text size
 * two labels need more than one side (about 159dp at 1.3x against 144dp at
 * 360dp), so they wrap onto two lines inside that cell rather than being cut
 * - see `VoiceBar`. The numbers here are what the box may take; they are not
 * a claim that the whole bar fits at every text size.
 */
internal object FaceBarPlan {

    /** The microphone's own width - `VoiceButton` is `size(48.dp)`. */
    const val MIC_DP = 48f

    /** The inset between the microphone's cell and the box, and between stoppable things. */
    const val GAP_DP = 8f

    /** "Stop"'s own touch target, which the right cell must always leave room for. */
    const val STOP_DP = 48f

    /** The box never narrows past its own 48dp touch target. */
    const val TYPE_MIN_DP = 48f

    /** ...and is never a second composer. */
    const val TYPE_MAX_DP = 96f

    /** One side of the microphone: what each cell has when the two are equal. */
    fun sideDp(availableDp: Float): Float = ((availableDp - MIC_DP) / 2f).coerceAtLeast(0f)

    /**
     * How wide the typing box may be in [availableDp] of bar, where
     * `availableDp` is the bar's content width (the caller's 12dp side
     * padding already taken off).
     *
     * When the result is not clamped, `typeWidthDp + GAP_DP + STOP_DP` is
     * exactly [sideDp], so the box and Stop can never run into the microphone.
     * The clamp at [TYPE_MIN_DP] is where that stops being true - below about
     * a 300dp-wide phone - and the bar's minimum supported width (320dp) is
     * above it, which `PhoneFaceBarTest` pins.
     */
    fun typeWidthDp(availableDp: Float): Float =
        (sideDp(availableDp) - GAP_DP - STOP_DP).coerceIn(TYPE_MIN_DP, TYPE_MAX_DP)
}
