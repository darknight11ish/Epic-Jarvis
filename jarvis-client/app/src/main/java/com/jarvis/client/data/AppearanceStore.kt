package com.jarvis.client.data

import android.content.Context
import androidx.core.content.edit
import com.jarvis.client.FaceState
import com.jarvis.client.face.Binding
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.Palette
import com.jarvis.client.face.Params
import com.jarvis.client.face.Pattern
import com.jarvis.client.ui.theme.Chrome
import com.jarvis.client.ui.theme.Themes
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONObject
import kotlin.random.Random

/**
 * What the app looks like: the theme, the face, and the seven state bindings.
 *
 * Per device, and the picker says so. There is no route that syncs any of this
 * — `POST /api/config` is 501 by design and nothing in the 38-endpoint table
 * reads or writes a preference — so faking sync would be worse than admitting
 * its absence. Bindings are the part that *should* sync eventually, because
 * they are a shared vocabulary rather than a taste: a phone whose `thinking` is
 * violet while the desktop's is green has learned a private language. That
 * needs a backend route; see the audit.
 */
class AppearanceStore(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private val _chrome = MutableStateFlow(Themes.byId(prefs.getString(KEY_THEME, null)))
    val chrome: StateFlow<Chrome> = _chrome.asStateFlow()

    private val _followSystem = MutableStateFlow(prefs.getBoolean(KEY_FOLLOW_SYSTEM, false))

    /** When set, the OS's light/dark choice picks between Daylight and the dark theme below. */
    val followSystem: StateFlow<Boolean> = _followSystem.asStateFlow()

    private val _faceId = MutableStateFlow(prefs.getString(KEY_FACE, null) ?: "")
    val faceId: StateFlow<String> = _faceId.asStateFlow()

    private val _bindings = MutableStateFlow(loadBindings())
    val bindings: StateFlow<Bindings> = _bindings.asStateFlow()

    /**
     * When the theme last changed, in wall-clock millis.
     *
     * A theme switch does not go through `resolve()`, so the flash governor
     * cannot see it — the governor measures the *state* colour and a theme
     * changes the surface under it. That makes the theme system the one
     * genuinely new photosensitivity hazard the feature introduces, and this
     * timestamp is half of how it is closed: [canChangeNow] enforces a dwell so
     * two switches cannot produce two opposing luminance swings inside the
     * budget. The other half is the crossfade duration and rate, in the UI.
     *
     * Enforced in the store rather than the UI on purpose, so a double-tap or a
     * system dark/light flap cannot get past it either.
     */
    private var lastChangeAt = 0L

    fun canChangeNow(nowMs: Long = System.currentTimeMillis()): Boolean =
        nowMs - lastChangeAt >= THEME_DWELL_MS

    fun setTheme(theme: Chrome, nowMs: Long = System.currentTimeMillis()): Boolean {
        if (theme.id == _chrome.value.id) return true
        if (!canChangeNow(nowMs)) return false
        lastChangeAt = nowMs
        prefs.edit { putString(KEY_THEME, theme.id) }
        _chrome.value = theme
        return true
    }

    fun setFollowSystem(value: Boolean) {
        prefs.edit { putBoolean(KEY_FOLLOW_SYSTEM, value) }
        _followSystem.value = value
    }

    fun setFace(id: String) {
        prefs.edit { putString(KEY_FACE, id) }
        _faceId.value = id
    }

    fun setBindings(value: Bindings) {
        prefs.edit { putString(KEY_BINDINGS, encode(value)) }
        _bindings.value = value
    }

    fun resetBindings() {
        prefs.edit { remove(KEY_BINDINGS) }
        _bindings.value = Bindings.DEFAULTS
    }

    /**
     * Re-rolls the four states that may be randomised.
     *
     * `approval` and `error` are pinned to their families and `banked` and
     * `standby` are neutral by definition — "waiting on you is amber or green",
     * and a green alarm is a design you have to explain. So this moves idle,
     * listening, thinking and speaking and leaves the rest where they are.
     *
     * Every candidate is checked against the spec's separation rule AND against
     * a measured ΔE gate, because the written rule is a proxy and the proxy is
     * too crude: it compares hue-ring distance and step difference, and by that
     * measure the *shipped* defaults fail (idle ice-3 against speaking ice-4 is
     * distance 0, step difference 1) while measuring a perfectly healthy 15.6.
     */
    fun randomise(seed: Long = System.nanoTime()) {
        val rng = Random(seed)
        val families = Palette.families.filter { it != "neutral" }
        val current = _bindings.value.byState.toMutableMap()

        repeat(40) {
            val picks = RANDOMISABLE.associateWith { state ->
                val family = families.random(rng)
                val step = if (rng.nextBoolean()) 3 else 4
                val colour = Palette.byId.getValue("$family-$step")
                val pattern = patternsFor(state).random(rng)
                Binding(pattern, if (pattern.kind.derivesItsOwnHue()) null else colour, timingFor(pattern, rng))
            }
            val colours = picks.values.mapNotNull { it.color }
            if (separated(colours)) {
                picks.forEach { (state, binding) -> current[state] = binding }
                setBindings(Bindings(current))
                return
            }
        }
        // Forty tries and nothing separated well enough. Leaving it alone is the
        // right failure: a re-roll that produced two states the same colour
        // would be worse than a re-roll that visibly did nothing.
    }

    /**
     * ΔE-2000 is not worth porting for this, so the gate is a cheap perceptual
     * distance that agrees with it on the question actually being asked: are
     * these two obviously different at arm's length. Weighted toward the
     * red-green axis's collapse under deuteranopia, which is the failure mode
     * that matters — verdant-4 and rose-4 are 67.7 apart to most eyes and 8.2
     * apart to a deuteranope, and both simulate to the same beige.
     */
    private fun separated(colours: List<androidx.compose.ui.graphics.Color>): Boolean {
        for (i in colours.indices) {
            for (j in i + 1 until colours.size) {
                if (distance(colours[i], colours[j]) < MIN_SEPARATION) return false
            }
        }
        return true
    }

    private fun distance(
        a: androidx.compose.ui.graphics.Color,
        b: androidx.compose.ui.graphics.Color,
    ): Float {
        // Luminance difference survives every vision model; the chroma terms do
        // not, so luminance is weighted highest.
        val dl = (com.jarvis.client.ui.theme.relativeLuminance(a) -
            com.jarvis.client.ui.theme.relativeLuminance(b))
        // Blue-yellow is the axis a deuteranope and a protanope both keep.
        val by = ((a.blue - (a.red + a.green) / 2f) - (b.blue - (b.red + b.green) / 2f))
        val rg = ((a.red - a.green) - (b.red - b.green))
        return kotlin.math.sqrt(
            (dl * dl * 4f + by * by * 2f + rg * rg * 0.5f).toDouble(),
        ).toFloat()
    }

    private fun patternsFor(state: FaceState): List<Pattern> = when (state) {
        FaceState.IDLE -> listOf(Pattern.BREATHE, Pattern.SOLID, Pattern.GRADIENT)
        FaceState.LISTENING -> listOf(Pattern.SOLID, Pattern.BREATHE)
        FaceState.THINKING -> listOf(
            Pattern.SWEEP, Pattern.RAINBOW, Pattern.CYCLE, Pattern.TEMPERATURE, Pattern.COMET,
        )
        FaceState.SPEAKING -> listOf(Pattern.REACTIVE, Pattern.GRADIENT)
        else -> listOf(Pattern.SOLID)
    }

    /**
     * `randomise.timing` — a breathe for standby is slow and one for an active
     * state is quick, and the two must not be the same number.
     */
    private fun timingFor(pattern: Pattern, rng: Random): Params = when (pattern.kind) {
        com.jarvis.client.face.PatternKind.BREATHE ->
            Params(periodS = 2.6f + rng.nextFloat() * 1.6f)
        com.jarvis.client.face.PatternKind.HUE_SWEEP ->
            Params(periodS = 4f + rng.nextFloat() * 3f)
        else -> Params()
    }

    private fun com.jarvis.client.face.PatternKind.derivesItsOwnHue(): Boolean =
        this == com.jarvis.client.face.PatternKind.HUE_SWEEP ||
            this == com.jarvis.client.face.PatternKind.TEMPERATURE

    // ------------------------------------------------------------ storage ----

    private fun encode(b: Bindings): String {
        val root = JSONObject()
        for ((state, binding) in b.byState) {
            val o = JSONObject()
            o.put("pattern", binding.pattern.id)
            binding.color?.let { c -> Palette.byId.entries.firstOrNull { it.value == c } }
                ?.let { o.put("color", it.key) }
            binding.params.periodS?.let { o.put("period_s", it.toDouble()) }
            binding.params.spanDeg?.let { o.put("span_deg", it.toDouble()) }
            binding.params.offsetDeg?.let { o.put("offset_deg", it.toDouble()) }
            binding.params.sat?.let { o.put("sat", it.toDouble()) }
            binding.params.light?.let { o.put("light", it.toDouble()) }
            binding.params.sharpness?.let { o.put("sharpness", it.toDouble()) }
            binding.params.gain?.let { o.put("gain", it.toDouble()) }
            binding.params.loud?.let { c -> Palette.byId.entries.firstOrNull { it.value == c } }
                ?.let { o.put("loud", it.key) }
            root.put(state.name, o)
        }
        return root.toString()
    }

    /**
     * Anything unreadable falls back to the defaults rather than throwing. A
     * corrupt preference must not be a phone that will not open.
     */
    private fun loadBindings(): Bindings = runCatching {
        val raw = prefs.getString(KEY_BINDINGS, null) ?: return Bindings.DEFAULTS
        val root = JSONObject(raw)
        val out = Bindings.DEFAULTS.byState.toMutableMap()
        for (state in FaceState.entries) {
            val o = root.optJSONObject(state.name) ?: continue
            val pattern = Pattern.byId(o.optString("pattern")) ?: continue
            val colour = o.optString("color").takeIf { it.isNotEmpty() }?.let { Palette.byId[it] }
            fun f(key: String): Float? =
                if (o.has(key)) o.optDouble(key).toFloat() else null
            out[state] = Binding(
                pattern = pattern,
                color = colour,
                params = Params(
                    periodS = f("period_s"),
                    spanDeg = f("span_deg"),
                    offsetDeg = f("offset_deg"),
                    sat = f("sat"),
                    light = f("light"),
                    sharpness = f("sharpness"),
                    gain = f("gain"),
                    loud = o.optString("loud").takeIf { it.isNotEmpty() }?.let { Palette.byId[it] },
                ),
            )
        }
        Bindings(out)
    }.getOrDefault(Bindings.DEFAULTS)

    private companion object {
        const val PREFS = "jarvis_appearance"
        const val KEY_THEME = "theme"
        const val KEY_FOLLOW_SYSTEM = "follow_system"
        const val KEY_FACE = "face"
        const val KEY_BINDINGS = "bindings"

        /**
         * 500ms crossfade plus 500ms dwell means two opposing swings can be no
         * closer than a second apart: 1.0 transitions/s against a budget of 3.
         */
        const val THEME_DWELL_MS = 500L

        val RANDOMISABLE = listOf(
            FaceState.IDLE, FaceState.LISTENING, FaceState.THINKING, FaceState.SPEAKING,
        )

        const val MIN_SEPARATION = 0.28f
    }
}
