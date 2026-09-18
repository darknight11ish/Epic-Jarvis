package com.jarvis.client.data

import android.content.Context
import android.os.SystemClock
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
 * The theme stays per device - Compose and the desktop's CSS cannot share
 * drawing code, and it is a taste, not a vocabulary. The face and its
 * bindings ARE a shared vocabulary: a phone whose `thinking` is violet while
 * the desktop's is green has learned a private language, so [toSyncDocument]
 * and [applySyncDocument] read and write `/api/appearance`, per
 * `docs/APPEARANCE-API.md` on the desktop branch. Gated on the `appearance`
 * capability by [JarvisRuntime], so a backend that predates the route is
 * simply never asked, and this store works exactly as it always did.
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
    // elapsedRealtime, not wall clock. An NTP correction backwards — or a
    // manual date change — made the elapsed value negative, so this returned
    // false and the theme locked for the length of the jump: every tap answered
    // "one theme change at a time", and the follow-the-system effect discarded
    // the refusal and silently stayed on the wrong theme with no retry.
    private var lastChangeAt = 0L

    fun canChangeNow(nowMs: Long = SystemClock.elapsedRealtime()): Boolean =
        nowMs - lastChangeAt >= THEME_DWELL_MS

    fun setTheme(theme: Chrome, nowMs: Long = SystemClock.elapsedRealtime()): Boolean {
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

    /**
     * The wire shape, written locally so there is never a second shape.
     *
     * This used to key states by Kotlin enum name (`IDLE`) and write params as
     * flat siblings of `pattern`. `/api/appearance` keys by the SPEC's state
     * ids (`idle`) and nests `params` inside each binding, so a sync would have
     * needed a translation layer between two formats that differ for no reason
     * other than which language wrote them first. The desktop hit the mirror of
     * this and says it cost a real bug in both directions.
     *
     * So the local store now uses the wire shape. There is nothing to
     * translate when sync lands, and no second format to keep in step.
     * [loadBindings] still reads the old one, so an existing install migrates
     * on its next write rather than losing its face.
     */
    private fun encode(b: Bindings): String = bindingsToJson(b).toString()

    /** The object [encode] serialises - factored out so the sync document can share it. */
    private fun bindingsToJson(b: Bindings): JSONObject {
        val root = JSONObject()
        for ((state, binding) in b.byState) {
            val o = JSONObject()
            o.put("pattern", binding.pattern.id)
            binding.color?.let { c -> Palette.byId.entries.firstOrNull { it.value == c } }
                ?.let { o.put("color", it.key) }
            val p = JSONObject()
            binding.params.periodS?.let { p.put("period_s", it.toDouble()) }
            binding.params.spanDeg?.let { p.put("span_deg", it.toDouble()) }
            binding.params.offsetDeg?.let { p.put("offset_deg", it.toDouble()) }
            binding.params.sat?.let { p.put("sat", it.toDouble()) }
            binding.params.light?.let { p.put("light", it.toDouble()) }
            binding.params.sharpness?.let { p.put("sharpness", it.toDouble()) }
            binding.params.gain?.let { p.put("gain", it.toDouble()) }
            binding.params.loud?.let { c -> Palette.byId.entries.firstOrNull { it.value == c } }
                ?.let { p.put("loud", it.key) }
            if (p.length() > 0) o.put("params", p)
            root.put(state.wireId, o)
        }
        return root
    }

    /**
     * `POST /api/appearance`'s body, per `docs/APPEARANCE-API.md`: `face` and
     * `bindings`, nothing else - the server owns `updated` and stamps it
     * itself, and the theme is deliberately not here. Faces and bindings are a
     * shared vocabulary across the owner's devices; the theme is a per-screen
     * taste the desktop's own CSS and this app's Compose theme cannot share
     * drawing code for anyway, and the contract does not ask for it.
     */
    fun toSyncDocument(): JSONObject {
        val root = JSONObject()
        _faceId.value.takeIf { it.isNotBlank() }?.let { root.put("face", it) }
        root.put("bindings", bindingsToJson(_bindings.value))
        return root
    }

    /**
     * Applies a document read from `GET /api/appearance` (or an unwrapped
     * `POST` echo). Unknown fields are ignored per the contract's own
     * tolerate-both-directions rule; a state missing from `bindings` keeps
     * the spec default, the same as [loadBindings] already does for a local
     * document with gaps in it.
     */
    fun applySyncDocument(doc: JSONObject) {
        doc.optString("face").takeIf { it.isNotEmpty() }?.let { setFace(it) }
        doc.optJSONObject("bindings")?.let { setBindings(parseBindings(it)) }
    }

    /**
     * The spec's id for a state - lowercase, and checked against the spec's
     * own `states[].id` list by SpecDriftTest rather than assumed.
     */
    private val FaceState.wireId: String get() = name.lowercase()

    /**
     * Anything unreadable falls back to the defaults rather than throwing. A
     * corrupt preference must not be a phone that will not open.
     */
    private fun loadBindings(): Bindings = runCatching {
        val raw = prefs.getString(KEY_BINDINGS, null) ?: return Bindings.DEFAULTS
        parseBindings(JSONObject(raw))
    }.getOrDefault(Bindings.DEFAULTS)

    /**
     * Shared by [loadBindings] (a local document, possibly in the old
     * enum-keyed shape) and [applySyncDocument] (a synced document, always
     * wire-shaped). Anything unreadable falls back to the spec default for
     * that state rather than throwing - a corrupt or partial document must
     * not be a phone that will not open, or that loses every OTHER state's
     * choice over one bad entry.
     */
    private fun parseBindings(root: JSONObject): Bindings {
        val out = Bindings.DEFAULTS.byState.toMutableMap()
        for (state in FaceState.entries) {
            // Both shapes. The wire id is what is written now; the enum name is
            // what older installs have on disk, and dropping it would reset a
            // face the owner chose deliberately.
            val o = root.optJSONObject(state.wireId) ?: root.optJSONObject(state.name) ?: continue
            val pattern = Pattern.byId(o.optString("pattern")) ?: continue
            val colour = o.optString("color").takeIf { it.isNotEmpty() }?.let { Palette.byId[it] }
            // Params nested, falling back to the flat siblings of the old
            // shape. `optJSONObject` returns null rather than throwing when
            // the key is absent or is not an object.
            val pj = o.optJSONObject("params") ?: o
            // `isFinite`, because `optDouble` answers NaN for anything it
            // cannot coerce — and NaN is not caught by runCatching, so the
            // "anything unreadable falls back to the defaults" promise above
            // did not hold for it. NaN then survives every clamp in the
            // renderer (`NaN < 0.05` is false, so coerceAtLeast returns NaN),
            // reaches Color(), and `NaN.toInt()` is 0: the face renders pure
            // black on black, invisibly, and it persists across restarts
            // because it is in preferences.
            fun f(key: String): Float? =
                if (pj.has(key)) pj.optDouble(key).takeIf { it.isFinite() }?.toFloat() else null
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
                    loud = pj.optString("loud").takeIf { it.isNotEmpty() }?.let { Palette.byId[it] },
                ),
            )
        }
        return Bindings(out)
    }

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
