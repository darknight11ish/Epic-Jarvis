package com.jarvis.client.data

import com.jarvis.client.face.FrameRateTarget
import com.jarvis.client.face.QualityTier

/**
 * The face editor's phone-only settings: how hard the face works and how fast
 * it moves. The reactor kit's Quality, Frame rate and All speeds controls, plus
 * the two switches the owner asked for on top of them.
 *
 * Per device and never synced: a phone and a desktop have different graphics
 * hardware, so what one can draw says nothing about the other. None of it
 * touches the desktop or its settings.
 *
 * Pure Kotlin, with its own tiny text format ([encode]/[decode]) rather than
 * org.json, so a JVM unit test can round-trip it - org.json is only stubs
 * there (see LookTest).
 */
data class FaceTuning(
    /** Used only while [autoAdjust] is off. */
    val quality: QualityTier = QualityTier.DEFAULT,
    /** Used only while [autoAdjust] is off. */
    val frameRate: FrameRateTarget = FrameRateTarget.DEFAULT,
    /** The kit's "All speeds": a multiplier on how fast the face moves. */
    val speed: Float = 1f,
    /** Let the phone pick quality and frame rate, and step down when frames run late. */
    val autoAdjust: Boolean = true,
    /**
     * The owner's own battery saver. Android's Battery Saver turns the same
     * behaviour on while it is on, without changing this.
     */
    val batterySaver: Boolean = false,
) {
    /** Speed pulled into range, and NaN back to 1. */
    fun clamped(): FaceTuning = copy(
        speed = if (speed.isFinite()) speed.coerceIn(MIN_SPEED, MAX_SPEED) else 1f,
    )

    /** One line, e.g. `q=high;f=auto;s=1.0;a=1;b=0`. Every field is written. */
    fun encode(): String =
        "q=${quality.id};f=${frameRate.id};s=$speed;a=${if (autoAdjust) 1 else 0};b=${if (batterySaver) 1 else 0}"

    companion object {
        /**
         * Slow-down only, for now. The kit's slider runs from 0.05x to 3-6x,
         * but some faces pulse their own brightness on the face's clock, and
         * the flash limits in `Spec` police the state COLOURS, not those
         * pulses. Faster than 1x stays off until those pulses are checked
         * against the same limits - which keeps the audit's standing rule
         * that motion settings only ever slow the face.
         */
        const val MIN_SPEED = 0.25f
        const val MAX_SPEED = 1f

        /** The choices the editor offers. 1x is the default. */
        val SPEEDS: List<Float> = listOf(0.25f, 0.5f, 0.75f, 1f)

        /**
         * Anything unreadable falls back to the default for that field, and a
         * wholly unreadable line is the default tuning - a corrupt preference
         * must never be a phone that will not open.
         */
        fun decode(raw: String?): FaceTuning = runCatching {
            if (raw.isNullOrBlank()) return FaceTuning()
            val fields = HashMap<String, String>()
            for (part in raw.split(';')) {
                val at = part.indexOf('=')
                if (at <= 0) continue
                fields[part.substring(0, at).trim()] = part.substring(at + 1).trim()
            }
            val d = FaceTuning()
            FaceTuning(
                quality = QualityTier.byId(fields["q"]),
                frameRate = FrameRateTarget.byId(fields["f"]),
                speed = fields["s"]?.toFloatOrNull() ?: d.speed,
                autoAdjust = flag(fields["a"], d.autoAdjust),
                batterySaver = flag(fields["b"], d.batterySaver),
            ).clamped()
        }.getOrDefault(FaceTuning())

        private fun flag(v: String?, default: Boolean): Boolean = when (v) {
            "1", "true" -> true
            "0", "false" -> false
            else -> default
        }
    }
}
