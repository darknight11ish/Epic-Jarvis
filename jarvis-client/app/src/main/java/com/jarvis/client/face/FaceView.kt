package com.jarvis.client.face

import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.input.pointer.pointerInput
import com.jarvis.client.FaceState
import androidx.compose.foundation.Canvas
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.hypot
import kotlin.math.max
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import kotlinx.coroutines.delay
import kotlin.math.min
import kotlin.math.sin
import kotlin.random.Random

/**
 * The shell that hosts a face.
 *
 * **Everything here is shell-level and happens exactly once.** If a face's own
 * draw code ever needs to know about envelopes, crossfades, frame pacing or
 * overlays, it is in the wrong layer — that was the whole finding behind the
 * `state_transforms` block: twenty faces each implementing the same four
 * borrowed states twenty different ways.
 */
@Composable
fun FaceView(
    state: FaceState,
    notches: Int,
    modifier: Modifier = Modifier,
    face: Face = Faces.default,
    bindings: Bindings = Bindings.DEFAULTS,
    /** The owner's microphone, 0..1, per audio frame. Null when the mic is shut. */
    micLevel: () -> Float? = { null },
    /** Jarvis's own voice, 0..1, per audio frame. Null when nothing is playing. */
    speechLevel: () -> Float? = { null },
) {
    val host = remember { FaceHost() }
    var frame by remember { mutableStateOf(host.snapshot()) }

    // The loop below is keyed on face and bindings, not on these. Called
    // directly they would be captured from whichever composition started the
    // loop and never updated — so the first non-remembered lambda a caller
    // passes would freeze the mic at its opening value for the life of the
    // face. rememberUpdatedState is the fix for exactly that shape.
    val mic by rememberUpdatedState(micLevel)
    val speech by rememberUpdatedState(speechLevel)

    // One glow sprite, painted once and reused.
    //
    // It used to be a Brush.radialGradient built inside the draw: a new
    // ArrayList, two boxed Colors, a new ShaderBrush and — because a
    // ShaderBrush caches its native shader per instance — a fresh
    // RadialGradient and gradient ramp, every active frame. At radius 2.1x it
    // covers essentially the whole canvas, roughly thirty times the fill of the
    // entire particle field, so it was the single most expensive thing on
    // screen and it was being rebuilt sixty times a second.
    val glow = rememberGlowSprite()

    LaunchedEffect(state) { host.onStateChange(state) }

    LaunchedEffect(face, bindings) {
        var last = 0L
        while (true) {
            val fps = Spec.fpsFor(state)
            if (fps in 1..15) {
                // Below 15fps the frame clock was still waking at the display
                // rate to decide to do nothing: a Choreographer callback and a
                // coroutine resume 60-120 times a second, across what the spec
                // itself calls nine tenths of screen-on time. Sleeping to the
                // next due instant costs nothing in between.
                val stepMs = 1000L / fps
                delay(stepMs)
                val now = System.nanoTime()
                if (last == 0L) last = now
                val dt = ((now - last) / 1_000_000_000.0).toFloat().coerceIn(0f, 0.25f)
                last = now
                if (host.advance(dt, state, mic(), speech(), bindings, face)) {
                    frame = host.snapshot()
                }
            } else {
                withFrameNanos { now ->
                    if (last == 0L) last = now
                    val dt = ((now - last) / 1_000_000_000.0).toFloat().coerceIn(0f, 0.25f)
                    last = now
                    // Resting states draw at 30 rather than the display rate.
                    // The accumulated dt is handed to the draw, so motion covers
                    // the same distance — frame skipping, not slow motion.
                    if (host.advance(dt, state, mic(), speech(), bindings, face)) {
                        frame = host.snapshot()
                    }
                }
            }
        }
    }

    Box(
        modifier
            .pointerInput(Unit) {
                detectTapGestures(onPress = { host.onTap(it, size.width.toFloat()) })
            }
            .pointerInput(Unit) {
                detectDragGestures(
                    onDragEnd = { host.onDragEnd() },
                ) { change, drag ->
                    change.consume()
                    host.onDrag(drag)
                }
            },
    ) {
        Canvas(Modifier.matchParentSize()) {
            drawFace(frame, face, notches, glow)
        }
    }
}

/** Everything the draw needs, computed once per advanced frame. */
data class FaceFrame(
    val state: FaceState,
    val swatch: Swatch,
    val angle: Float,
    val tableAngle: Float,
    val motion: FaceState,
    val amp: Float,
    val speechPush: Float,
    val dim: Float,
    val overlay: Spec.Overlay,
    val clockFrac: Float,
    val hitchPhase: Float,
    val shake: Offset,
    val flinch: Offset,
    val ringAt: Offset?,
    val ringFrac: Float,
    val yaw: Float,
    val pitch: Float,
    val t: Float,
)

/**
 * The state machine behind a face. Not a composable: it is mutable, per-frame
 * and deliberately outside the snapshot system, because running it as Compose
 * state would invalidate the tree sixty times a second to change a float.
 */
class FaceHost {

    private val governor = FlashGovernor()

    /**
     * Per surface, like the governor and for the same reason: a strobe budget
     * shared between faces would stop one face because another had been
     * strobing.
     */
    private val strobeBudget = StrobeBudget()

    private var t = 0f
    private var angle = 0f
    private var tableAngle = 0f
    private var rate = 1f
    private var rateTarget = 1f

    private var mic = 0f
    private var voice = 0f
    private var lastVoiceAt = -999f

    private var colFrom: Swatch? = null
    private var colShown: Swatch = Swatch(Spec.ICE_3, Spec.ICE_3)
    private var colEase = 1f

    private var state: FaceState = FaceState.IDLE
    private var changedAt = -999f

    private var clockStartedAt = -999f

    private var yaw = 0f
    private var pitch = 0f
    private var yawVel = 0f
    private var dragging = false

    private var tapAt: Offset? = null
    private var tapStartedAt = -999f
    private var faceWidth = 1f

    private var accum = 0f

    fun onStateChange(next: FaceState) {
        if (next == state) return
        state = next
        changedAt = t
        // The RATE is eased, not snapped: a face whose rate steps from 0.22 to
        // 1.35 in one frame reads as a cut even when the angle is continuous.
        rateTarget = Spec.transformFor(next).rate
        // Remember the colour actually on screen and fade from it, so a state
        // change reads as the same object changing its mind rather than a cut.
        colFrom = colShown
        colEase = 0f
        if (next == FaceState.APPROVAL) clockStartedAt = t
        governor.reset()
    }

    fun onTap(at: Offset, width: Float) {
        tapAt = at
        tapStartedAt = t
        faceWidth = max(1f, width)
    }

    fun onDrag(delta: Offset) {
        dragging = true
        yaw += delta.x * Spec.DRAG_YAW_PER_PX
        pitch = (pitch + delta.y * Spec.DRAG_PITCH_PER_PX)
            .coerceIn(-Spec.DRAG_PITCH_LIMIT, Spec.DRAG_PITCH_LIMIT)
        yawVel = (delta.x * Spec.DRAG_YAW_PER_PX * 60f)
            .coerceIn(-Spec.DRAG_MAX_RAD_S, Spec.DRAG_MAX_RAD_S)
    }

    fun onDragEnd() {
        dragging = false
    }

    /**
     * @return true when this frame should be drawn. False means the state's
     *   frame rate says skip — the dt is kept and handed to the next draw.
     */
    fun advance(
        dtIn: Float,
        wanted: FaceState,
        micIn: Float?,
        voiceIn: Float?,
        bindings: Bindings,
        face: Face,
    ): Boolean {
        if (wanted != state) onStateChange(wanted)
        t += dtIn
        accum += dtIn

        val tf = Spec.transformFor(state)

        // Frame pacing. The first 600 ms after any change and any live tap run
        // at full rate so no transition stutters.
        val fps = Spec.fpsFor(state)
        val settled = (t - changedAt) > Spec.FULL_RATE_WINDOW_S &&
            (t - tapStartedAt) > Spec.FULL_RATE_WINDOW_S
        if (fps > 0 && settled) {
            if (accum < 1f / fps) return false
        }
        val dt = accum
        accum = 0f

        // Envelopes, in seconds, so the feel does not change with refresh rate.
        mic = smooth(mic, (micIn ?: 0f).coerceIn(0f, 1f), dt, Spec.MIC_ATTACK_S, Spec.MIC_RELEASE_S)
        if (mic < Spec.MIC_GATE) mic = 0f

        if (voiceIn != null) {
            lastVoiceAt = t
            voice = smooth(voice, voiceIn.coerceIn(0f, 1f), dt, Spec.VOICE_ATTACK_S, Spec.VOICE_RELEASE_S)
        } else if (state == FaceState.SPEAKING && (t - lastVoiceAt) > Spec.SPEECH_FALLBACK_AFTER_S) {
            // Speaking is never frozen, even before TTS is wired: a
            // speech-shaped stand-in keeps the face moving. It is not his
            // voice, but it is not a still picture either.
            voice = smooth(voice, syntheticVoice(t), dt, Spec.VOICE_ATTACK_S, Spec.VOICE_RELEASE_S)
        } else {
            voice = smooth(voice, 0f, dt, Spec.VOICE_ATTACK_S, Spec.VOICE_RELEASE_S)
        }
        if (voice < Spec.VOICE_GATE) voice = 0f

        // What drives the pattern and the scale push.
        val drive = when (state) {
            // Silence is not absence of attention: a person pauses between
            // words, and a face that drops below idle during the pause reads as
            // "it stopped listening" at exactly the moment they check.
            FaceState.LISTENING, FaceState.APPROVAL -> max(Spec.LISTEN_FLOOR, mic)
            FaceState.SPEAKING -> max(Spec.SPEAK_FLOOR, voice)
            else -> 0f
        }

        // Rate easing, then angle ACCUMULATION. Never angle = clock * speed:
        // multiplying the absolute clock by a per-state speed makes the angle
        // jump by clock * (new - old) the instant the state changes — measured
        // at 434 to 773 radians on the reference build, forty to a hundred and
        // twenty revolutions on a single frame, at exactly the moment the owner
        // is looking at the face.
        rate = smooth(rate, rateTarget, dt, Spec.RATE_EASE_S, Spec.RATE_EASE_S)
        val motion = tf.borrow
        val faceSpeed = face.speedFor(motion)
        angle += dt * rate * tf.dir * faceSpeed
        tableAngle += dt * rate * faceSpeed

        // Colour: resolve the target, then crossfade from what is on screen.
        val target = resolve(bindings.of(state), t, drive, governor, strobeBudget)
        colEase = min(1f, colEase + dt / Spec.COLOR_EASE_S)
        val delayed = if (state == FaceState.APPROVAL) {
            // The ring is seen to arrive before the colour follows: the knock
            // comes before the door opens.
            ((t - changedAt) - Spec.TINT_DELAY_APPROVAL_S) / Spec.COLOR_EASE_S
        } else {
            colEase
        }
        val k = smoothstep(delayed.coerceIn(0f, 1f))
        val from = colFrom
        colShown = if (from == null) target else Swatch(
            mix(from.a, target.a, k),
            mix(from.b, target.b, k),
        )

        // Drag inertia: a released face keeps turning and settles rather than
        // stopping dead under the finger.
        if (!dragging) {
            yaw += yawVel * dt
            yawVel *= exp(-dt / Spec.DRAG_INERTIA_TAU_S)
            if (abs(yawVel) < 0.001f) yawVel = 0f
        }

        return true
    }

    fun snapshot(): FaceFrame {
        val tf = Spec.transformFor(state)
        val sinceTap = t - tapStartedAt
        val tapLive = sinceTap in 0f..Spec.TAP_FLINCH_S
        val tapK = if (tapLive) 1f - (sinceTap / Spec.TAP_FLINCH_S) else 0f

        val flinch = if (tapLive && tapAt != null) {
            val a = tapAt!!
            val d = Offset(0.5f * faceWidth - a.x, 0.5f * faceWidth - a.y)
            val len = max(1f, hypot(d.x, d.y))
            val push = faceWidth * Spec.TAP_FLINCH_FRAC * tapK
            Offset(d.x / len * push, d.y / len * push)
        } else {
            Offset.Zero
        }

        val ringFrac = if (sinceTap in 0f..Spec.TAP_RING_S) sinceTap / Spec.TAP_RING_S else -1f

        val drive = when (state) {
            FaceState.LISTENING, FaceState.APPROVAL -> max(Spec.LISTEN_FLOOR, mic)
            FaceState.SPEAKING -> max(Spec.SPEAK_FLOOR, voice)
            else -> 0f
        }

        // The clock overlay closes over twenty seconds, with the first 220 ms
        // sweeping to 12% so the ring is on screen before the tint.
        val clockFrac = if (state == FaceState.APPROVAL) {
            val since = t - clockStartedAt
            if (since < 0.22f) (since / 0.22f) * 0.12f
            else min(1f, 0.12f + (since - 0.22f) / Spec.APPROVAL_CLOCK_S)
        } else {
            0f
        }

        // The error hitch: stop dead in 60 ms, hold, shake, then crawl.
        val sinceChange = t - changedAt
        val shake = if (state == FaceState.ERROR && sinceChange in 0.31f..0.61f) {
            val amp = faceWidth * 0.015f
            Offset(sin(sinceChange * 8f * PI2) * amp, 0f)
        } else {
            Offset.Zero
        }

        return FaceFrame(
            state = state,
            swatch = colShown,
            angle = angle,
            tableAngle = tableAngle,
            motion = tf.borrow,
            amp = drive,
            speechPush = if (state == FaceState.SPEAKING) voice else mic,
            dim = tf.dim,
            overlay = tf.overlay,
            clockFrac = clockFrac,
            hitchPhase = sinceChange,
            shake = shake,
            flinch = flinch,
            ringAt = tapAt,
            ringFrac = ringFrac,
            yaw = yaw,
            pitch = pitch,
            t = t,
        )
    }

    private fun syntheticVoice(time: Float): Float {
        val inRest = (time % Spec.SPEECH_REST_EVERY_S) > (Spec.SPEECH_REST_EVERY_S - Spec.SPEECH_REST_S)
        if (inRest) return 0f
        val syl = sin(time * Spec.SPEECH_SYLLABLE_HZ * PI2) * 0.5f + 0.5f
        // A hash, not a new XorWowRandom every frame. Random(seed) allocated a
        // generator sixty times a second for one float.
        val weight = 0.55f + 0.45f * hashUnit((time * 2f).toInt())
        return (syl * weight).coerceIn(0f, 1f)
    }
}

private fun smoothstep(x: Float) = x * x * (3f - 2f * x)

/**
 * Dims by blending toward the background, never by multiplying toward zero.
 *
 * A multiply lands banked's already-dark colour around 0.002 relative
 * luminance, which many OLED panels quantise to black — so the state that means
 * "something is waiting" would vanish on the device most likely to show it.
 */
private fun dimmed(c: Color, dim: Float): Color = mix(Spec.BACKGROUND, c, dim)

private fun DrawScope.drawFace(f: FaceFrame, face: Face, notches: Int, glow: ImageBitmap) {
    val w = size.minDimension
    val cx = size.width / 2f
    val cy = size.height / 2f
    // faces[].render.fit — a uniform scale so no face touches its edge.
    val radius = w / 2f * 0.5f * face.fit

    // One background for all faces. Each used to paint its own, which showed as
    // a differently tinted rectangle behind every one.
    drawRect(Spec.BACKGROUND, size = Size(size.width, size.height))

    val hot = dimmed(f.swatch.a, f.dim)
    val cool = dimmed(f.swatch.b, f.dim)

    // The speech / microphone push: up to 3.5% growth on a loud syllable.
    // Positional, not luminance, so it is not a flash.
    val push = 1f + Spec.SPEECH_SCALE * f.speechPush
    val lifted = lift(hot, Spec.SPEECH_BRIGHTNESS * f.speechPush)

    translate(f.flinch.x + f.shake.x, f.flinch.y + f.shake.y) {
        // A cached-gradient halo rather than a blur. A real blur over a canvas
        // face was measured at 3-6 ms on a mid-range phone; this is one draw.
        if (Spec.isActive(f.state)) {
            // One textured quad, tinted, composited additively.
            //
            // Additive rather than SrcOver because the spec's own canvas
            // fallback for bloom says the sprite is drawn "lighter" — this is a
            // light source, and a light source adds.
            val r = radius * 2.1f
            val side = (r * 2f).toInt().coerceAtLeast(1)
            drawImage(
                image = glow,
                dstOffset = IntOffset((cx - r).toInt(), (cy - r).toInt()),
                dstSize = IntSize(side, side),
                colorFilter = ColorFilter.tint(lifted.copy(alpha = 0.30f)),
                blendMode = BlendMode.Plus,
            )
        }

        face.draw(this, cx, cy, radius * push, lifted, cool, f)

        when (f.overlay) {
            Spec.Overlay.CLOCK -> drawApprovalClock(cx, cy, radius, lifted, f)
            Spec.Overlay.NOTCHES -> drawNotches(cx, cy, radius, cool, notches)
            else -> Unit
        }

        val at = f.ringAt
        if (at != null && f.ringFrac in 0f..1f) {
            drawCircle(
                color = lifted.copy(alpha = (1f - f.ringFrac) * 0.6f),
                radius = w * Spec.TAP_RING_FRAC * f.ringFrac,
                center = at,
                style = Stroke(width = 2f),
            )
        }
    }
}

/**
 * The waiting clock: an arc from twelve o'clock closing clockwise, with the
 * knock ping on top.
 *
 * Approval and listening measure 4.5 ΔE apart for a deuteranope, so two states
 * may share a hue only if they never share a movement. This is approval's
 * identity, and it is legible with no colour at all.
 */
private fun DrawScope.drawApprovalClock(
    cx: Float, cy: Float, r: Float, tint: Color, f: FaceFrame,
) {
    val ring = r * 1.5f
    drawArc(
        color = tint.copy(alpha = 0.22f),
        startAngle = -90f,
        sweepAngle = 360f,
        useCenter = false,
        topLeft = Offset(cx - ring, cy - ring),
        size = Size(ring * 2, ring * 2),
        style = Stroke(width = 3f),
    )
    drawArc(
        color = tint,
        startAngle = -90f,
        sweepAngle = 360f * f.clockFrac,
        useCenter = false,
        topLeft = Offset(cx - ring, cy - ring),
        size = Size(ring * 2, ring * 2),
        style = Stroke(width = 3f),
    )

    // The knock: a ring leaving the core every 1.6 s. It repeats, it is
    // directional, and it stops the moment you answer.
    val ph = (f.t % 1.6f) / 0.4f
    if (ph <= 1f) {
        val e = 1f - (1f - ph) * (1f - ph) * (1f - ph)
        drawCircle(
            color = tint.copy(alpha = (1f - e) * 0.55f),
            radius = r * (0.12f + e * 0.82f) * 1.5f,
            center = Offset(cx, cy),
            style = Stroke(width = 2f),
        )
    }
}

/** The rim ring drawn full, with one notch per waiting item. */
private fun DrawScope.drawNotches(cx: Float, cy: Float, r: Float, tint: Color, notches: Int) {
    val ring = r * 1.5f
    drawCircle(tint.copy(alpha = 0.35f), ring, Offset(cx, cy), style = Stroke(width = 3f))
    if (notches <= 0) return
    val n = min(notches, 24)
    for (i in 0 until n) {
        val a = (-PI / 2 + i * (PI2 / n)).toFloat()
        val inner = ring - r * 0.12f
        drawLine(
            color = tint,
            start = Offset(cx + cos(a) * inner, cy + sin(a) * inner),
            end = Offset(cx + cos(a) * (ring + r * 0.06f), cy + sin(a) * (ring + r * 0.06f)),
            strokeWidth = 3f,
        )
    }
}


/**
 * The glow ramp: white in the middle, transparent at the edge, painted once.
 *
 * 160px is plenty — a smooth radial ramp upscales invisibly, and at ARGB that
 * is about 100 KB held for the life of the composition. The colour comes from a
 * ColorFilter at draw time rather than from the bitmap, so the sprite never
 * needs rebuilding when the state colour changes.
 *
 * Modifier.drawWithCache does not solve this on its own: its cache re-runs on a
 * size or key change, and the glow's colour changes continuously, so it would
 * invalidate every frame. Splitting the shape from the tint is what makes it
 * cacheable at all.
 */
@Composable
private fun rememberGlowSprite(): ImageBitmap = remember {
    val n = 160
    val bitmap = android.graphics.Bitmap.createBitmap(
        n, n, android.graphics.Bitmap.Config.ARGB_8888,
    )
    android.graphics.Canvas(bitmap).drawCircle(
        n / 2f, n / 2f, n / 2f,
        android.graphics.Paint().apply {
            isAntiAlias = true
            shader = android.graphics.RadialGradient(
                n / 2f, n / 2f, n / 2f,
                android.graphics.Color.WHITE,
                android.graphics.Color.TRANSPARENT,
                android.graphics.Shader.TileMode.CLAMP,
            )
        },
    )
    bitmap.asImageBitmap()
}

/** A cheap deterministic 0..1 from an int. Replaces a per-frame Random. */
private fun hashUnit(seed: Int): Float {
    var x = seed * -1640531527
    x = x xor (x ushr 15)
    x *= -2048144789
    x = x xor (x ushr 13)
    return ((x ushr 8) and 0xFFFF) / 65535f
}
