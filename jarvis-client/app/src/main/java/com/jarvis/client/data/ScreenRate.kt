package com.jarvis.client.data

import kotlin.math.abs
import kotlin.math.roundToInt

/**
 * The phone's **screen** refresh rate: "while Jarvis is on screen, ask the
 * screen for this rate".
 *
 * ## What this can and cannot do - verified on the owner's phone, not assumed
 *
 * (OnePlus CPH2419, OxygenOS/ColorOS on Android 15 / API 35, 1080x2412,
 * 480 dpi. `adb shell dumpsys display` on 2026-10-09, and the platform's own
 * `DisplayManager`/`Display` sources.)
 *
 * A normally sideloaded app **cannot change the phone's system-wide refresh
 * rate.** That is a protected setting:
 *  - `Settings.System.PEAK_REFRESH_RATE` / `MIN_REFRESH_RATE` need
 *    `WRITE_SECURE_SETTINGS`, which adb or root grants and a plain install
 *    never gets; and
 *  - the real API for it, `DisplayManager.setUserPreferredDisplayMode()`
 *    (Android 12 / API 31+), is gated on the privileged
 *    `CAPABILITY_CONTROL_DISPLAY_MODES` capability, which only a system or
 *    carrier app holds. From an ordinary app it fails with
 *    `SecurityException` - verified by reading the platform's own capability
 *    gate, and by the fact that this app's install holds neither.
 *
 * What an ordinary app **can** do is ask for a display mode **for its own
 * window**: `WindowManager.LayoutParams.preferredDisplayModeId` or
 * `preferredRefreshRate` (both API 23+), and on API 35+
 * `View.setRequestedFrameRate`. The system *may* honour that while the window
 * is in front, and may equally ignore it: the OEM's own display policy and the
 * owner's own "peak refresh rate" setting both outrank an app's request. On
 * this particular phone they do - `dumpsys display` reports
 * `mIgnorePreferredRefreshRate: true` and `mRefreshRateChangeable: false`,
 * so ColorOS ignores an app's window request outright, and the owner's system
 * peak is currently 60 Hz on a 120 Hz panel. **No API reports why a request
 * was refused**, so the only honest thing to do is ask, read back what the
 * panel actually settled on, and say plainly whether it took - see [took] and
 * [tookNote].
 *
 * So the promise this setting makes, and the only one it may ever make, is
 * **"while Jarvis is on screen, ask for this rate"**. It must never promise to
 * change the phone, and the wording in `ui/screens/ScreenRatePlate.kt` says so
 * in the owner's own words.
 *
 * ## NOT the face's frame rate - do not merge these two
 *
 * This is a different setting from the face editor's Frame rate
 * ([com.jarvis.client.face.FrameRateTarget], saved in [FaceTuning]). Both have
 * a number of Hz in them and both live on this phone, and a future agent will
 * otherwise assume one duplicates the other:
 *  - the face's Frame rate is how often the animal is **drawn**. It is a
 *    budget for Jarvis's own animation, saved per device, and picking 30 there
 *    makes the animal move at 30 frames a second on a panel that is still
 *    running at 120.
 *  - this is what the **panel** is asked to run at. It changes nothing about
 *    how fast the animal animates.
 * Merging them would either animate the face at the panel's rate whatever the
 * owner chose, or ask the panel for a rate only because the owner wanted a
 * slower animal. They stay two settings.
 *
 * ## Rounding up, never down
 *
 * The house rule (CLAUDE.md; the owner's own decision of 2026-09-28, already
 * the doctrine of the face's Frame rate: "a picked frame rate rounds UP when
 * the screen cannot match it exactly - never slower than the pick") applies
 * here too, and [choose] is that rule. An exact rate is used as it is; an
 * unavailable pick takes the **next rate up**; a pick above every rate the
 * panel has takes the panel's **highest, and says so** rather than quietly
 * capping.
 *
 * Pure Kotlin, no Android imports, so a JVM unit test holds every case
 * (`ScreenRateTest`).
 */
object ScreenRate {

    /**
     * Saved when the owner has not picked a rate: the phone's own display
     * policy decides, exactly as it did before this setting existed. This is
     * the way back to whatever the phone was using.
     */
    const val FOLLOW_PHONE = "follow"

    /**
     * The distinct rates [modes] offers, in Hz, ascending.
     *
     * Every real panel reports floats that are almost but not exactly a whole
     * number - this phone reports 120.00001, 60.000004 and 90.0 - so each mode
     * is rounded to whole Hz **before** deduplicating. Without that, 59.94 and
     * 60.000004 would be two rows in the picker for what is one rate. Anything
     * not finite or not positive is dropped: a mode the platform reported
     * wrongly must not become something the owner can choose.
     */
    fun rates(modes: List<Float>): List<Float> =
        modes.filter { it.isFinite() && it > 0f }
            .map { it.roundToInt().toFloat() }
            .distinct()
            .sorted()

    /** What the owner's pick turned into, before the panel has been asked. */
    enum class Settled {
        /** No pick: the phone's own choice is left alone. */
        FOLLOW_PHONE,

        /** The panel offers exactly this rate. */
        EXACT,

        /** The panel cannot do the pick exactly; the next rate UP is asked for instead. */
        ROUNDED_UP,

        /** The pick is above every rate the panel has; the highest is asked for instead. */
        ABOVE_TOP,

        /** The panel reported no usable rate at all, so there is nothing to ask for. */
        NOTHING,
    }

    /**
     * What to ask the panel for, and the one plain line to show the owner about
     * it. [hz] is null when there is nothing to ask for ([Settled.FOLLOW_PHONE]
     * or [Settled.NOTHING]).
     */
    data class Ask(val hz: Float?, val settled: Settled, val note: String)

    /**
     * The rate to ask the panel for, from the owner's [pick] and the rates the
     * panel actually [available] - the rounding-up rule in this file's own doc.
     *
     * [pick] is normalised the same way [rates] normalises a mode, so a saved
     * 120.00001 and a listed 120 are the same choice. A [pick] that is null,
     * not finite or not positive is [Settled.FOLLOW_PHONE]: an unreadable
     * preference must never become a wrong request.
     */
    fun choose(pick: Float?, available: List<Float>): Ask {
        val list = rates(available)
        if (pick == null || !pick.isFinite() || pick <= 0f) {
            return Ask(null, Settled.FOLLOW_PHONE, followNote())
        }
        if (list.isEmpty()) {
            return Ask(null, Settled.NOTHING, nothingNote())
        }
        val want = pick.roundToInt().toFloat()
        list.firstOrNull { it == want }?.let {
            return Ask(it, Settled.EXACT, exactNote(it))
        }
        // The next rate UP - never slower than the pick. A pick below every
        // rate the panel has lands here too (30 on a 60/90/120 panel asks for
        // 60), which is the same rule read in the same direction.
        list.firstOrNull { it > want }?.let {
            return Ask(it, Settled.ROUNDED_UP, roundedUpNote(want, it))
        }
        // Above every rate the panel has: the highest, and SAY SO rather than
        // silently capping.
        val top = list.last()
        return Ask(top, Settled.ABOVE_TOP, aboveTopNote(want, top))
    }

    /**
     * Whether the panel really settled on [asked], once the request has been
     * made and the display re-read.
     *
     * A tolerance rather than equality because a mode's own reported rate is
     * never exactly the number on the label (this phone's 120 Hz mode reports
     * 120.00001). [TOLERANCE_HZ] is far smaller than the gap between any two
     * rates a panel really offers - the smallest common step is 30 Hz - so it
     * cannot mistake one mode for another.
     *
     * There is no API that says whether a request was accepted; this compares
     * what was asked for against what the panel ended up doing, which is the
     * only evidence there is.
     */
    fun took(asked: Float, actual: Float, toleranceHz: Float = TOLERANCE_HZ): Boolean =
        asked.isFinite() && actual.isFinite() && abs(actual - asked) <= toleranceHz

    /**
     * What to tell the owner after asking - and when it did **not** take, it
     * says so, in those words, rather than leaving them believing it did. This
     * is the whole reason [took] exists.
     */
    fun tookNote(asked: Float, actual: Float): String = if (took(asked, actual)) {
        "Jarvis asked the screen for ${label(asked)} Hz and it is running at ${label(actual)} Hz."
    } else {
        "Jarvis asked the screen for ${label(asked)} Hz, but it is running at ${label(actual)} Hz - " +
            "so the change did not take effect. Your phone's own display settings decide the real " +
            "rate; an app can only ask."
    }

    /** A whole-number label: "90", never "90.0". */
    fun label(hz: Float): String = hz.roundToInt().toString()

    /** The one line under the picker, for a pick that has not been applied yet. */
    fun pickNote(pick: Float?, available: List<Float>): String = choose(pick, available).note

    // ------------------------------------------------------------- sentences --

    /**
     * Every sentence below says "ask", never "change": see this file's doc for
     * why that word is the honest one.
     */
    private fun followNote(): String =
        "Jarvis leaves the screen's refresh rate to your phone, exactly as it was before this setting."

    private fun nothingNote(): String =
        "This phone has not reported any refresh rates, so there is nothing for Jarvis to ask for."

    private fun exactNote(hz: Float): String =
        "This screen offers ${label(hz)} Hz. Jarvis asks for it while the app is on screen."

    private fun roundedUpNote(want: Float, got: Float): String =
        "This screen has no ${label(want)} Hz. Jarvis asks for the next rate up, ${label(got)} Hz - " +
            "never a slower one."

    private fun aboveTopNote(want: Float, top: Float): String =
        "This screen's highest rate is ${label(top)} Hz. You picked ${label(want)} Hz, which is " +
            "above it, so Jarvis asks for ${label(top)} Hz - the fastest this screen can do."

    /**
     * Two rates closer than this are the same mode. Well under the 30 Hz
     * smallest real step, so no two modes can be confused.
     */
    const val TOLERANCE_HZ = 1.5f

    // ------------------------------------------------------------ the setting --

    /**
     * The saved preference as one string: [FOLLOW_PHONE], or the whole number
     * of Hz. Anything unreadable is [FOLLOW_PHONE] - a corrupt preference must
     * never turn into a wrong request.
     */
    fun encode(hz: Float?): String =
        if (hz == null || !hz.isFinite() || hz <= 0f) FOLLOW_PHONE else label(hz)

    /** [encode]'s other half. */
    fun decode(raw: String?): Float? {
        if (raw.isNullOrBlank() || raw == FOLLOW_PHONE) return null
        val hz = raw.trim().toFloatOrNull() ?: return null
        return if (hz.isFinite() && hz > 0f) hz else null
    }

    /** The per-device store's file, the same one the face editor's own tuning lives in. */
    const val PREFS_KEY = "screen_rate_hz"

    /** One honest line about what a higher rate costs. Never a claim that it is free. */
    const val BATTERY_NOTE =
        "A higher refresh rate uses more battery. The screen redraws more often, and that is " +
            "power the phone spends whether or not anything on it is moving."

    /**
     * What the setting can actually do, in the owner's own words - shown at the
     * top of the plate so the promise is never wider than the truth.
     */
    const val HONEST_NOTE =
        "While Jarvis is on screen, Jarvis asks the screen for this rate. It cannot change your " +
            "phone's own display setting - that belongs to the phone, and only the phone's own " +
            "Settings or a system app can change it. If the screen does not take the rate, this " +
            "screen will say so."
}
