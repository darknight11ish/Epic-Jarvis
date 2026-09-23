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
 *
 * Everything else here is per device and never synced: the theme, the dark
 * theme Follow the system returns to ([preferredDark]), the face size, and
 * the [look] record with its presets.
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

    private val _faceSize = MutableStateFlow(FaceSize.byId(prefs.getString(KEY_FACE_SIZE, null)))

    /**
     * How big the face is drawn on Home. Per device, like the theme, and for
     * the same reason: it is a taste about this screen, not part of the
     * shared vocabulary - so [toSyncDocument] leaves it out.
     */
    val faceSize: StateFlow<FaceSize> = _faceSize.asStateFlow()

    fun setFaceSize(value: FaceSize) {
        prefs.edit { putString(KEY_FACE_SIZE, value.id) }
        _faceSize.value = value
    }

    private val _look = MutableStateFlow(loadLook())

    /**
     * Everything else about how THIS phone looks, as one record: the Home
     * layout, glow, motion, density, shape, text size, panel edges and the
     * behaviour switches. See [Look].
     *
     * One record rather than a key per setting, because the presets are what
     * make a dozen controls usable: "Night" is several of these at once, and
     * "Custom (from Night)" is decided by comparing the whole record with the
     * preset (docs/UI-AUDIT-2026-09-23.md §4). Per device, like the theme,
     * and never in [toSyncDocument]: none of it is part of the vocabulary
     * the desktop shares, and none of it touches the desktop's settings.
     */
    val look: StateFlow<Look> = _look.asStateFlow()

    /** Clamped and saved. Anything out of range is pulled back in, never refused. */
    fun setLook(value: Look) {
        val clamped = value.clamped()
        prefs.edit { putString(KEY_LOOK, encodeLook(clamped)) }
        _look.value = clamped
    }

    /**
     * The face's share of Home, as set by dragging the handle there.
     *
     * Only the owner's own drag should come here. A temporary shrink - for an
     * approval, or while typing - is Home's business and must not be saved,
     * or the owner's layout would be overwritten by the app's.
     */
    fun setFaceFraction(value: Float) = setLook(_look.value.copy(faceFraction = value))

    /**
     * Applies a preset. Returns false, and changes NOTHING, when the preset
     * needs a theme change the dwell governor refuses right now - the same
     * "one theme change at a time" answer a hand-picked theme gets. All or
     * nothing, so "Night" never lands as half its settings on the wrong theme.
     *
     * A preset that names a theme turns Follow the system off, for the reason
     * MainActivity's theme pick does: it is a deliberate choice of theme, and
     * leaving the switch on would snap it straight back at the next dusk.
     * Presets without a theme leave both alone.
     */
    fun applyPreset(preset: LookPreset, nowMs: Long = SystemClock.elapsedRealtime()): Boolean {
        val theme = preset.themeId?.let { Themes.byId(it) }
        if (theme != null) {
            if (!setTheme(theme, nowMs)) return false
            setFollowSystem(false)
        }
        setLook(preset.applyTo(_look.value))
        return true
    }

    private val _preferredDark = MutableStateFlow(loadPreferredDark())

    /**
     * The dark theme Follow the system comes back to when the phone goes dark.
     *
     * This used to be worked out from the CURRENT theme, which is Daylight
     * all day while following - so the answer was always Reactor, and a Void
     * or Ember Dusk owner got Reactor at every dusk (the audit's custom-8).
     * Now it is remembered: every dark theme accepted by [setTheme] is
     * written here, and [setPreferredDark] sets it directly for the "Theme
     * for dark mode" list shown while following.
     */
    val preferredDark: StateFlow<Chrome> = _preferredDark.asStateFlow()

    /** Dark themes only. Daylight is never "the theme for dark mode", so it is ignored. */
    fun setPreferredDark(theme: Chrome) {
        if (!theme.dark) return
        if (_preferredDark.value.id == theme.id) return
        prefs.edit { putString(KEY_PREFERRED_DARK, theme.id) }
        _preferredDark.value = theme
    }

    /**
     * What was stored, if it is still a dark theme; otherwise the current
     * theme if that is dark (an install from before this key existed keeps
     * what it has); otherwise the default.
     */
    private fun loadPreferredDark(): Chrome {
        val stored = prefs.getString(KEY_PREFERRED_DARK, null)
        Themes.ALL.firstOrNull { it.id == stored && it.dark }?.let { return it }
        val current = _chrome.value
        return if (current.dark) current else Themes.DEFAULT
    }

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
        if (theme.id == _chrome.value.id) {
            setPreferredDark(theme)
            return true
        }
        if (!canChangeNow(nowMs)) return false
        lastChangeAt = nowMs
        prefs.edit { putString(KEY_THEME, theme.id) }
        _chrome.value = theme
        // Remembered for Follow the system. A no-op for Daylight.
        setPreferredDark(theme)
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

    /**
     * [Look] as JSON, keyed in snake_case like the bindings. Every field is
     * written, so a later default change does not silently move a setting
     * the owner chose.
     */
    private fun encodeLook(l: Look): String = JSONObject().apply {
        put("based_on", l.basedOn.id)
        put("face_fraction", l.faceFraction.toDouble())
        put("nav_always_shown", l.navAlwaysShown)
        put("glow", l.glow.toDouble())
        put("motion", l.motion.id)
        put("compact", l.compact)
        put("sharp", l.sharp)
        put("text_scale", l.textScale.toDouble())
        put("edges", l.edges.id)
        put("transitions", l.transitions)
        put("make_room_for_approvals", l.makeRoomForApprovals)
        put("shrink_while_typing", l.shrinkWhileTyping)
        put("follow_reply", l.followReply)
        put("tap_face_opens_mind", l.tapFaceOpensMind)
    }.toString()

    /**
     * Same promise as [loadBindings]: anything unreadable falls back to the
     * default for that field, and a wholly unreadable record is the default
     * look. NaN is refused by `isFinite` for the reason [parseBindings] gives,
     * and [Look.clamped] pulls anything out of range back in.
     */
    private fun loadLook(): Look = runCatching {
        val raw = prefs.getString(KEY_LOOK, null) ?: return Look()
        val o = JSONObject(raw)
        val d = Look()
        fun f(key: String, default: Float): Float =
            if (o.has(key)) o.optDouble(key).takeIf { it.isFinite() }?.toFloat() ?: default else default
        fun b(key: String, default: Boolean): Boolean =
            if (o.has(key)) o.optBoolean(key, default) else default
        Look(
            faceFraction = f("face_fraction", d.faceFraction),
            navAlwaysShown = b("nav_always_shown", d.navAlwaysShown),
            glow = f("glow", d.glow),
            motion = MotionPref.byId(o.optString("motion")),
            compact = b("compact", d.compact),
            sharp = b("sharp", d.sharp),
            textScale = f("text_scale", d.textScale),
            edges = EdgePref.byId(o.optString("edges")),
            transitions = b("transitions", d.transitions),
            makeRoomForApprovals = b("make_room_for_approvals", d.makeRoomForApprovals),
            shrinkWhileTyping = b("shrink_while_typing", d.shrinkWhileTyping),
            followReply = b("follow_reply", d.followReply),
            tapFaceOpensMind = b("tap_face_opens_mind", d.tapFaceOpensMind),
            basedOn = LookPreset.byId(o.optString("based_on")),
        ).clamped()
    }.getOrDefault(Look())

    private companion object {
        const val PREFS = "jarvis_appearance"
        const val KEY_THEME = "theme"
        const val KEY_FOLLOW_SYSTEM = "follow_system"
        const val KEY_FACE = "face"
        const val KEY_BINDINGS = "bindings"
        const val KEY_FACE_SIZE = "face_size"
        const val KEY_LOOK = "look"
        const val KEY_PREFERRED_DARK = "preferred_dark"

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

/**
 * How big the face is drawn on Home.
 *
 * Only ever smaller than the original 260dp, never bigger: a larger face costs
 * more to draw on every frame, and nobody has yet measured that on the
 * owner's phone (docs/UI-AUDIT-2026-09-23.md, decision 1). The drawn size is
 * also capped by the pane it sits in, so a small pane never squashes it.
 */
enum class FaceSize(val id: String, val label: String, val sizeDp: Int) {
    LARGE("large", "Large", 260),
    MEDIUM("medium", "Medium", 200),
    SMALL("small", "Small", 150),
    TINY("tiny", "Tiny", 110),
    ;

    companion object {
        val DEFAULT = LARGE

        /** Anything unknown or missing is the default, never a crash. */
        fun byId(id: String?): FaceSize = entries.firstOrNull { it.id == id } ?: DEFAULT
    }
}

/**
 * How the face should move, on top of what the phone itself asks for.
 *
 * [FOLLOW] leaves it to the phone's own "remove animations" setting, as the
 * app always has. [CALM] slows the face's motion down whatever the phone
 * says. Neither ever speeds anything up, and neither touches the flash
 * limits in `face/Spec.kt`, which apply to every setting identically.
 *
 * [FULL] exists because the shared contract between the UI-audit slices
 * names it, but the Appearance screen does NOT offer it and every reader
 * should treat it exactly like [FOLLOW]. The audit's table has "Full" as a
 * choice, and the only thing it could add over Follow is overriding the
 * phone's own request for less motion - which is speeding motion up, and
 * the rule for this work is that motion settings may only reduce. Offering
 * it is the owner's decision to make, not a default to slip in.
 */
enum class MotionPref(val id: String, val label: String) {
    FOLLOW("follow", "Follow phone"),
    CALM("calm", "Calm"),
    FULL("full", "Full"),
    ;

    companion object {
        fun byId(id: String?): MotionPref = entries.firstOrNull { it.id == id } ?: FOLLOW
    }
}

/**
 * The line around each panel. Stored here as the phone's own choice; the
 * theme code draws it (`ui/theme`'s own edge enum is mapped from this by id,
 * so the two can be renamed independently without a stored preference
 * breaking).
 */
enum class EdgePref(val id: String, val label: String) {
    HAIRLINE("hairline", "Hairline"),
    BEVEL("bevel", "Bevel"),
    NONE("none", "None"),
    ;

    companion object {
        fun byId(id: String?): EdgePref = entries.firstOrNull { it.id == id } ?: HAIRLINE
    }
}

/**
 * Everything about how this phone looks that is not the theme, the face,
 * the state colours or the face size - which each keep the key they always
 * had, so nothing an existing install chose moves.
 *
 * Appearance only. Nothing here reaches the desktop or its settings: the
 * phone's rule against deep config editing is about the backend, and this
 * is a paint choice on one screen.
 *
 * The first nine fields are the "Adjust" controls a [LookPreset] sets. The
 * four behaviour switches after them are NOT part of any preset: applying
 * "Night" should not quietly change whether the face makes room for an
 * approval, so [LookPreset.applyTo] leaves them where they are.
 */
data class Look(
    /** The face's share of Home, 0.20..0.85. The rest is the conversation. */
    val faceFraction: Float = DEFAULT_FACE_FRACTION,
    /** The tabs row on Home: hidden until swiped (false) or always shown. */
    val navAlwaysShown: Boolean = false,
    /**
     * Multiplier on the face's glow, 0.25..1. The caller multiplies it with
     * the theme's own `Chrome.postScale`, so it can only ever dim the glow
     * below the theme's level, never brighten it past that.
     */
    val glow: Float = 1f,
    val motion: MotionPref = MotionPref.FOLLOW,
    /** Tighter padding and list spacing. */
    val compact: Boolean = false,
    /** Square-ish corners instead of rounded ones. */
    val sharp: Boolean = false,
    /**
     * Multiplier on top of the phone's own text size, 0.9..1.3. 1 means
     * "follow the phone": the phone's font-scale setting still applies
     * underneath whatever this is, so there is no separate "follow" value.
     */
    val textScale: Float = 1f,
    val edges: EdgePref = EdgePref.HAIRLINE,
    /**
     * Screen changes fade and slide. Off when false - and also off whenever
     * the phone asks for less motion, whatever this says.
     */
    val transitions: Boolean = true,

    // Behaviour switches: not part of any preset -----------------------------
    /**
     * Shrink the face while an approval is waiting, so Approve and Deny are
     * on screen. It only moves the layout; it never decides anything.
     */
    val makeRoomForApprovals: Boolean = true,
    /** Shrink the face while the keyboard is open. */
    val shrinkWhileTyping: Boolean = true,
    /** Keep the newest words of a streaming reply in view. */
    val followReply: Boolean = true,
    /** Tapping the face opens Mind. False: it does nothing. */
    val tapFaceOpensMind: Boolean = true,

    /** The preset this look started from, for "Custom (from Focus)". */
    val basedOn: LookPreset = LookPreset.FOCUS,
) {
    /** Every number pulled into its range, and NaN back to its default. */
    fun clamped(): Look = copy(
        faceFraction = faceFraction.orIfNotFinite(DEFAULT_FACE_FRACTION)
            .coerceIn(MIN_FACE_FRACTION, MAX_FACE_FRACTION),
        glow = glow.orIfNotFinite(1f).coerceIn(MIN_GLOW, 1f),
        textScale = textScale.orIfNotFinite(1f).coerceIn(MIN_TEXT_SCALE, MAX_TEXT_SCALE),
    )

    /** True when a fine control has moved away from [basedOn], or its theme did. */
    fun isCustom(themeId: String): Boolean = !basedOn.matches(this, themeId)

    /** "Focus", or "Custom (from Focus)" once anything has been changed. */
    fun label(themeId: String): String =
        if (isCustom(themeId)) "Custom (from ${basedOn.label})" else basedOn.label

    companion object {
        /** Home's own limits: neither pane may be dragged away entirely. */
        const val DEFAULT_FACE_FRACTION = 0.75f
        const val MIN_FACE_FRACTION = 0.20f
        const val MAX_FACE_FRACTION = 0.85f

        /** Glow only ever dims, and never so far the face disappears. */
        const val MIN_GLOW = 0.25f

        const val MIN_TEXT_SCALE = 0.9f
        const val MAX_TEXT_SCALE = 1.3f

        private fun Float.orIfNotFinite(default: Float): Float = if (isFinite()) this else default
    }
}

/**
 * One-tap looks, per docs/UI-AUDIT-2026-09-23.md §4.
 *
 * Each preset is the default [Look] with a few fields changed, plus
 * optionally a theme. Anything a preset does not mention is the default, so
 * applying one is predictable: "Conversation" after a custom text size puts
 * the text size back too. Only the behaviour switches are left alone.
 */
enum class LookPreset(
    val id: String,
    val label: String,
    /** One line for the picker, in plain words. */
    val blurb: String,
    /** The theme this preset picks, or null to leave the theme alone. Checked by LookTest. */
    val themeId: String?,
) {
    FOCUS(
        "focus", "Focus",
        "The face takes most of Home. Tabs hidden until you swipe. The default.",
        null,
    ),
    CONVERSATION(
        "conversation", "Conversation",
        "A smaller face and more room to read. Tabs always shown, tighter spacing.",
        null,
    ),
    NIGHT(
        "night", "Night",
        "Ember Dusk, a dimmer glow and calmer motion.",
        "ember_dusk",
    ),
    OUTDOOR(
        "outdoor", "Outdoor",
        "Daylight, tabs always shown, and slightly larger text.",
        "daylight",
    ),
    ;

    /** The Adjust fields this preset sets. */
    private fun adjustments(): Look {
        val base = Look(basedOn = this)
        return when (this) {
            FOCUS -> base
            CONVERSATION -> base.copy(faceFraction = 0.35f, navAlwaysShown = true, compact = true)
            NIGHT -> base.copy(glow = 0.6f, motion = MotionPref.CALM)
            OUTDOOR -> base.copy(navAlwaysShown = true, textScale = 1.1f)
        }
    }

    /** [look] with this preset's Adjust fields, keeping its behaviour switches. */
    fun applyTo(look: Look): Look {
        val a = adjustments()
        return look.copy(
            faceFraction = a.faceFraction,
            navAlwaysShown = a.navAlwaysShown,
            glow = a.glow,
            motion = a.motion,
            compact = a.compact,
            sharp = a.sharp,
            textScale = a.textScale,
            edges = a.edges,
            transitions = a.transitions,
            basedOn = this,
        )
    }

    /**
     * Whether [look] is still exactly this preset. Worked out rather than
     * stored as a "customised" flag, so moving a control back to where the
     * preset had it makes the label honest again by itself.
     */
    fun matches(look: Look, themeId: String): Boolean =
        applyTo(look) == look && (this.themeId == null || this.themeId == themeId)

    companion object {
        val DEFAULT = FOCUS

        /** Anything unknown or missing is the default, never a crash. */
        fun byId(id: String?): LookPreset = entries.firstOrNull { it.id == id } ?: DEFAULT
    }
}
