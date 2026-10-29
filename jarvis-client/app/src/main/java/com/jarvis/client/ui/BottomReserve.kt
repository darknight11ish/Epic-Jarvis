package com.jarvis.client.ui

/**
 * How much room a scrolling screen must keep under its last row so the fixed
 * "Needs your OK" line never sits on top of a control (Gemini's `F4`,
 * 2026-10-28, measured on the owner's phone).
 *
 * THE DEFECT. `MainActivity` draws `CardWaitingLine` in a `Box` filled to the
 * screen, aligned to the bottom, on every screen but Home - it is an OVERLAY,
 * so it takes no room from the screen under it. Settings' own list padded its
 * bottom by 16 dp (`SettingsScreen.kt`, `contentPadding`), which leaves the
 * last card's last control exactly where the line lands: at max scroll the
 * bottom of Devices, "Unpair & clear the token", showed as a 6 px sliver with
 * an approval card waiting, and could not be pressed. The line's top sits
 * `EDGE_DP + its own height` above the bottom of the safe area, so anything
 * whose bottom padding is smaller than that is covered. Both numbers were
 * measured on a 1080x2412 phone (density 480, 3 px to the dp): the line's own
 * top at `y = 2064` is 348 px - 116 dp - above the screen's bottom, which is
 * 104 dp of line over the 12 dp gap, and the Unpair button's bottom at
 * `y = 2202` is 70 dp above it. 116 - 70 = 46 dp of a 48 dp button covered.
 *
 * WHY THE HEIGHT IS MEASURED RATHER THAN TYPED. The line draws the PC's own
 * card title, which wraps to two lines on a narrow phone and carries an extra
 * "and N more" line when several cards wait, so a single hand-picked number
 * would be too small exactly when it matters. `MainActivity` measures the
 * drawn line (`onSizeChanged`) and asks [forBanner] for the room it needs; the
 * screens add that to their own bottom padding.
 *
 * This is arithmetic only - no Android, no Compose types - so
 * `BottomReserveTest` can hold the geometry in the JVM suite, which is the
 * only test runner this app has.
 */
object BottomReserve {

    /**
     * The gap the line keeps from the screen's own edges - the `padding` on
     * the `Box` that draws it in `MainActivity`, and the reason the covered
     * band is the line's height plus this. Written as one constant so the
     * drawing side and the reserve cannot drift apart.
     */
    const val EDGE_DP = 12

    /**
     * Air between the top of the line and the last control's bottom: text
     * flush against a card edge reads as broken, and a control whose edge is
     * within a thumb's wobble of another touchable thing is a mis-tap waiting
     * to happen.
     */
    const val GAP_DP = 10

    /**
     * The room to reserve under a scrolling screen's content while the line is
     * drawn: its measured height, the edge gap it sits in, and [GAP_DP] of
     * air. Zero when the line is not drawn - a screen with no approval card
     * waiting must not carry blank space.
     *
     * @param lineHeightDp the height `MainActivity` measured for the line, in
     *   dp. A negative or nonsense value is read as zero rather than letting a
     *   measurement glitch pull the reserve below the edge gap.
     */
    fun forBanner(lineHeightDp: Float): Float =
        (if (lineHeightDp > 0f) lineHeightDp else 0f) + EDGE_DP + GAP_DP

    /**
     * How far the line reaches UP from the bottom of the safe area: its own
     * height plus the edge gap. This is the band a screen's bottom padding has
     * to clear, and it is what [BottomReserveTest] compares against - the two
     * sides written down separately so the comparison is arithmetic and not
     * one expression checked against itself.
     */
    fun coveredDp(lineHeightDp: Float): Float =
        (if (lineHeightDp > 0f) lineHeightDp else 0f) + EDGE_DP
}
