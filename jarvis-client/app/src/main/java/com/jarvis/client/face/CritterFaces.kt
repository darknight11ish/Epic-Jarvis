package com.jarvis.client.face

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.nativeCanvas
import com.jarvis.client.FaceState

/**
 * An animal face - a CHARACTER, where the other twenty faces are
 * instruments (rings, orbits, a drum skin). Four of them: [RedPanda],
 * [PygmyOwl], [SeaOtter] and [Monkey], each only its shader and its pose; everything
 * about how an animal is drawn on the phone lives here, once.
 *
 * A character needs its own pose for every state, so an animal reads the
 * real state ([FaceFrame.state]) rather than the borrowed movement
 * ([FaceFrame.motion]): it sleeps through standby, sits up and looks at you,
 * still, while waiting on an approval (no wave - the owner's call), wears a
 * still, concerned look at an error and dozes when banked. It also reads
 * the host's eased option weights (calm motion, a serious moment, "Still")
 * and its list of recent changes ([FaceFrame.past]). The shell's transforms
 * (dim, the approval clock, the error shake) still apply around it exactly
 * as for every face.
 *
 * Drawn like [Nucleus]: one AGSL fragment shader through
 * `android.graphics.RuntimeShader`, no mesh and no model file. Each shader
 * comes from the SAME source as the desktop's (`jarvis-desktop/critters/`,
 * generated into [CritterShaders]), and each pose from a Kotlin copy of the
 * desktop's pose code that `CritterPoseTest` checks against it - so the
 * phone's animals are the desktop's, not lookalikes.
 *
 * Colour: the fur and feathers keep their own colours. [draw]'s `hot` - the
 * owner's bound colour for this state - is the orb, which is also a real
 * light on the animal; `cool` is the rim light round it. Repainting the
 * whole animal per state would read as a different animal.
 */
abstract class CritterFace(
    final override val id: String,
    final override val name: String,
    private val source: String,
) : Face {

    /** This animal's pose for the frame (its pose code's flat list). */
    protected abstract fun pose(f: FaceFrame): FloatArray

    /** A pose as uniform name to value, with the voice's mouth. */
    protected abstract fun uniformsOf(p: FloatArray, mouth: FloatArray?): Map<String, FloatArray>

    /** Where a pose's sleeping Zs rise from: [asleep, x, y] (see [CritterPose.overlay]). */
    protected abstract fun overlayOf(p: FloatArray, yaw: Float, pitch: Float): FloatArray

    /**
     * Whether one of its idle happenings (a stretch, a scratch, an ear
     * turning) is playing at clock [t] in [state] - its pose's `busy`, the
     * desktop's `busy(state, t)`, checked against it by CritterPoseTest. Only
     * the frame pacer asks ([FaceHost.restFps]): at rest an animal is drawn
     * 30 or 60 times a second, and at the full rate while one plays.
     */
    abstract fun busyAt(state: FaceState, t: Float): Boolean

    /** What the host remembered at the last state changes (see [CritterPose.Hist]). */
    protected fun hist(f: FaceFrame) =
        CritterPose.Hist(prev2 = f.prevState2, gap = f.prevGap, prevAmp = f.prevAmp, prevAmp2 = f.prevAmp2, past = f.past)

    /** Calm motion, a serious moment, "Still": the host's eased weights (see [CritterPose.Opts]). */
    protected fun opts(f: FaceFrame) = CritterPose.Opts(calm = f.calmW, serious = f.seriousW, still = f.stillW)

    // The shell's spin rate. This receives the BORROWED movement (approval,
    // standby and banked arrive as IDLE, error as THINKING), so the desktop's
    // `st[...].sp` for those four states is set to the borrowed movement's
    // rate - the orb then swirls at the same pace on both. Only the orb's
    // swirl turns with it: breathing and blinking run on the clock, so the
    // animal never freezes when a state's spin stops (banked).
    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 1.0f
        FaceState.THINKING -> 1.6f
        FaceState.SPEAKING -> 0.8f
        else -> 0.5f
    }

    // Compiled lazily on first draw, like Nucleus's: `Faces.all` touches
    // every face at startup, and an owner who never picks an animal should
    // never pay for compiling it. Or ahead of that, off the main thread, by
    // [warm] - the default lazy is synchronized, so a draw that arrives while
    // a background thread is still compiling simply waits for that one
    // compile rather than starting a second.
    private val shader by lazy { android.graphics.RuntimeShader(source) }
    private val paint by lazy { android.graphics.Paint().apply { shader = this@CritterFace.shader } }

    /**
     * Compiles this animal's shader now, on the calling thread, if it is not
     * compiled yet. Only builds the `RuntimeShader` (SkSL's own compile,
     * which needs no GPU and no main thread); nothing is drawn, and every
     * uniform is still set on the main thread at draw time. A shader that
     * fails to compile is left for the draw to fail on, as before.
     */
    fun warm() {
        runCatching { shader }
    }

    // The colour filter that dims the whole animal (DimRule), rebuilt only
    // when the dim or the ground changes - once per state change, not per
    // frame. Main thread only, like every draw.
    private var filterDim = 1f
    private var filterGround: Color? = null
    private var filter: android.graphics.ColorFilter? = null

    private fun filterFor(dim: Float, ground: Color?): android.graphics.ColorFilter? {
        if (ground == null) return null
        if (dim == filterDim && ground == filterGround) return filter
        filterDim = dim
        filterGround = ground
        filter = DimRule.matrix(dim, ground.red, ground.green, ground.blue)
            ?.let { android.graphics.ColorMatrixColorFilter(it) }
        return filter
    }

    /**
     * How much of the phone's full resolution an animal is traced at, before
     * it is enlarged to fill the face: the quality level's
     * [QualityTier.animalTrace] - Lower 0.4, Balanced 0.5, High 0.75, Maximum
     * 1.0 (the spec's `frame_rate.animals.levels`, 2026-09-28).
     *
     * (Before that: High 0.5, Medium 0.4, Low about 0.31, Max 0.75. The
     * reasoning below is why it is not simply always 1.0.)
     *
     * Why not full resolution, as Nucleus does: measured through Skia (the
     * engine Android draws with), the red panda costs about 4 times Nucleus
     * per pixel (the owl and otter are lighter), and at the Large face size
     * that is more than a phone should spend on a face at the display's
     * rate. Half the width and height is a quarter of the pixels, so about a
     * quarter of the work - and because the animals are soft and rounded, the
     * enlarged picture
     * differs from the sharp one by about 1/255 on average; the shader's own
     * feathered outline hides the steps enlarging would otherwise show.
     *
     * Tied to the quality level, so when Auto adjust steps down because
     * frames arrive late, the animal gets cheaper too; and Auto may take an
     * animal up to Maximum - the full resolution - on a phone whose frames
     * take under a quarter of their time (FrameGovernor), never in battery
     * saver and never while it is warm.
     */
    private fun traceScale(): Float = FaceQuality.current.tier.animalTrace

    /**
     * The small offscreen pictures this animal is traced into, one per size
     * STEP, kept apart for the still thumbnail and the live face.
     *
     * Kept apart because the live face and the picker's still thumbnail can
     * be on screen together, and a picture re-recorded for one would change
     * the other's too - a thumbnail that is only drawn once would start
     * showing the live animal. So [FaceFrame.still] is part of the key.
     *
     * One per size STEP ([LAYER_STEP] pixels), not per exact size: while
     * Jarvis speaks or listens the face's radius wobbles a few percent with
     * the voice, and keyed by the exact size that was a new node and a new
     * offscreen buffer almost every frame. Rounded up to a step, the wobble
     * lands on one size, or two neighbours that both stay here. The picture
     * is traced at the step's size, so it is at most a step sharper than
     * asked, never blurrier.
     *
     * Least recently used goes first when full, because a face whose size
     * animates passes through many steps; dropping one is safe - whatever
     * already drew it keeps its own reference until it redraws.
     */
    private val layers = LinkedHashMap<Int, android.graphics.RenderNode>(8, 0.75f, true)

    private fun layerFor(px: Int, still: Boolean): android.graphics.RenderNode {
        val key = if (still) -px else px
        layers[key]?.let { return it }
        if (layers.size >= 4) layers.remove(layers.keys.first())
        return android.graphics.RenderNode(id).apply {
            // Forces an offscreen buffer the size of this node. That buffer
            // is what makes this cheaper: the shader runs once per pixel of
            // IT, and the enlarging happens when it is drawn scaled below.
            setUseCompositingLayer(true, null)
            layers[key] = this
        }
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = drawDimmed(scope, cx, cy, r, hot, cool, f, ground = null)

    /**
     * [draw], with the whole picture dimmed for the state (DimRule): every
     * pixel blended toward [ground] by the shell's own per-state factor, the
     * same one every other face's colours are dimmed by - standby's laid
     * over [FaceFrame.awakeDim] as far as the pose has nodded off
     * ([DimRule.sleep]). FaceView's `drawFace` calls this, handing [hot] and [cool]
     * UNdimmed, since the picture's dim covers the orb as well. A null
     * [ground] dims nothing (a caller that has already dimmed the colours).
     *
     * The filter goes on the paint that runs the shader, so it costs one
     * matrix per pixel of the small traced picture, and the software path
     * gets exactly the same picture.
     */
    /**
     * The dim this animal is drawn with in frame [f] - [drawDimmed]'s own,
     * standby's laid over [FaceFrame.awakeDim] as far as the pose has nodded
     * off ([DimRule.sleep]) - for what is drawn BEHIND it (the sun, moon and
     * weather, `drawSkyBehind`), which darkens and brightens with it.
     */
    fun dimFor(f: FaceFrame): Float = DimRule.sleep(f.awakeDim, overlayOf(pose(f), f.yaw, f.pitch)[0])

    fun drawDimmed(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame, ground: Color?,
    ) = with(scope) {
        val p = pose(f)
        // Standby's dim follows the pose nodding off and waking (DimRule.sleep).
        paint.colorFilter = filterFor(DimRule.sleep(f.awakeDim, overlayOf(p, f.yaw, f.pitch)[0]), ground)
        for ((name, v) in uniformsOf(p, f.mouth)) {
            when (v.size) {
                1 -> shader.setFloatUniform(name, v[0])
                2 -> shader.setFloatUniform(name, v[0], v[1])
                3 -> shader.setFloatUniform(name, v[0], v[1], v[2])
                else -> shader.setFloatUniform(name, v[0], v[1], v[2], v[3])
            }
        }
        shader.setFloatUniform("uHot", hot.red, hot.green, hot.blue)
        shader.setFloatUniform("uCool", cool.red, cool.green, cool.blue)
        // Dragging turns the camera round the animal, as it turns every other
        // 3D face; there is no automatic spin - a character faces you.
        shader.setFloatUniform("uYaw", f.yaw)
        shader.setFloatUniform("uPit", f.pitch)
        shader.setFloatUniform("uZoom", 1f)
        shader.setFloatUniform("uTime", f.angle)
        // No soft shadow on a small face or at Lower (AnimalPace.noShadow):
        // the animal's square, 4r, is the desktop's canvas, in device pixels.
        shader.setFloatUniform(
            "uNoShadow",
            if (AnimalPace.noShadow(4f * r, FaceQuality.current.tier)) 1f else 0f,
        )

        // Same framing as Nucleus: the desktop's p = 1 is half its canvas,
        // which is 2r here. The animal is drawn over the square 4r a side
        // round the centre; a ray that misses it (and the orb's glow)
        // returns transparent, so the corners cost one test and paint nothing.
        val side = 4f * r
        val canvas = drawContext.canvas.nativeCanvas
        if (!canvas.isHardwareAccelerated || side < 1f) {
            // A software canvas (a bitmap snapshot) cannot hold an offscreen
            // layer. Trace at full size, as Nucleus does.
            shader.setFloatUniform("uCenter", cx, cy)
            shader.setFloatUniform("uR", 2f * r)
            shader.setFloatUniform("uPx", 1f / (2f * r))
            // The same paint as the layer below, so the same dim. (It was a
            // ShaderBrush of the same shader; a Paint carries the filter.)
            canvas.drawRect(cx - 2f * r, cy - 2f * r, cx + 2f * r, cy + 2f * r, paint)
            drawZs(this, cx, cy, r, f, p)
            return@with
        }

        // The size traced at: the tier's share of full size, rounded UP to a
        // whole step (see [layers]), and never under 64. Every number the
        // shader gets below is worked out from this px - the node's real
        // size - so the picture fills the face exactly whatever the rounding.
        val need = kotlin.math.ceil(side * traceScale()).toInt().coerceAtLeast(64)
        val px = (need + LAYER_STEP - 1) / LAYER_STEP * LAYER_STEP
        val k = px / side
        shader.setFloatUniform("uCenter", px / 2f, px / 2f)
        shader.setFloatUniform("uR", 2f * r * k)
        // One pixel of the small picture, for the shader's feathered outline.
        shader.setFloatUniform("uPx", 1f / (2f * r * k))

        // For the Face editor's readout: traced / drawn, the live face only.
        if (!f.still) FaceQuality.noteTrace(px, kotlin.math.round(side).toInt())
        val node = layerFor(px, f.still)
        node.setPosition(0, 0, px, px)
        val rec = node.beginRecording(px, px)
        try {
            rec.drawRect(0f, 0f, px.toFloat(), px.toFloat(), paint)
        } finally {
            node.endRecording()
        }
        canvas.save()
        canvas.translate(cx - 2f * r, cy - 2f * r)
        // Enlarged back to full size when composited - filtered, so smooth.
        canvas.scale(1f / k, 1f / k)
        canvas.drawRenderNode(node)
        canvas.restore()
        drawZs(this, cx, cy, r, f, p)
    }

    // One path, reused: the Zs' three strokes, rebuilt per letter (main thread).
    private val zPath = androidx.compose.ui.graphics.Path()

    /**
     * THE SLEEPING Zs (owner, 2026-09-28): small z's rising from beside the
     * head while the animal is on standby - never while Jarvis cannot be
     * reached ([FaceFrame.zsW] fades them out then: the hollow ring alone
     * says that). Where each is, how big and how see-through is
     * [CritterPose.zs] - the desktop's own numbers, checked against its
     * fixture - so both apps draw the same Zs; this only turns them into
     * pixels: the shader's units are 2r from the centre, y UP. Drawn flat
     * over the picture (the shader is at its size limit), in the state's
     * bound colour lightened toward white ([FaceFrame.zsTint]). The letter is
     * three strokes, not a font's "z", so it is the same shape as the
     * desktop's. Calm motion is one still z. TalkBack hears nothing more:
     * the face already says it is on standby.
     */
    private fun drawZs(scope: DrawScope, cx: Float, cy: Float, r: Float, f: FaceFrame, p: FloatArray) {
        if (f.zsW <= 0f || f.still) return
        val ov = overlayOf(p, f.yaw, f.pitch)
        ov[0] *= f.zsW
        if (ov[0] <= 0.002f) return
        val zs = CritterPose.zs(f.t, ov, f.calmW)
        val k = 2f * r
        for (i in 0 until CritterPose.Zs.COUNT) {
            val a = zs[i * 5 + 3]
            if (a <= 0.004f) continue
            val sz = zs[i * 5 + 2] * k
            val hw = sz * CritterPose.Zs.WIDTH / 2f
            val hh = sz / 2f
            val tilt = zs[i * 5 + 4]
            // Counter-clockwise on screen (zs() has y UP): a y-down rotation
            // by -tilt.
            val c = kotlin.math.cos(-tilt)
            val sn = kotlin.math.sin(-tilt)
            val px = cx + zs[i * 5] * k
            val py = cy - zs[i * 5 + 1] * k
            fun pt(x: Float, y: Float) = androidx.compose.ui.geometry.Offset(px + x * c - y * sn, py + x * sn + y * c)
            zPath.reset()
            pt(-hw, -hh).let { zPath.moveTo(it.x, it.y) }
            pt(hw, -hh).let { zPath.lineTo(it.x, it.y) }
            pt(-hw, hh).let { zPath.lineTo(it.x, it.y) }
            pt(hw, hh).let { zPath.lineTo(it.x, it.y) }
            scope.drawPath(
                zPath,
                color = f.zsTint,
                alpha = a,
                style = androidx.compose.ui.graphics.drawscope.Stroke(
                    width = kotlin.math.max(1f, sz * CritterPose.Zs.STROKE),
                    cap = androidx.compose.ui.graphics.StrokeCap.Round,
                    join = androidx.compose.ui.graphics.StrokeJoin.Round,
                ),
            )
        }
    }
}

/**
 * The size step the animals' offscreen pictures are rounded up to, in
 * pixels - see [CritterFace]'s `layers`. Small enough that the extra
 * sharpness costs little (at most 15 pixels a side), big enough that the
 * voice's wobble in the face's size stays inside one or two steps.
 */
private const val LAYER_STEP = 16

// Each animal's mouth is the voice's own mouth shape ([FaceFrame.mouth]: the
// mouth track sampled at what is being heard), or shut when there is none -
// a typed answer, Quiet mode, an answer kept on screen.

/** The red panda, holding its orb in its lap. */
object RedPanda : CritterFace("redpanda", "Red Panda", CritterShaders.RED_PANDA) {
    override fun pose(f: FaceFrame) =
        CritterPose.pose(f.state, f.prevState, f.hitchPhase, f.t, f.amp, hist = hist(f), opts = opts(f))
    override fun uniformsOf(p: FloatArray, mouth: FloatArray?) = CritterPose.uniforms(p, mouth)
    override fun overlayOf(p: FloatArray, yaw: Float, pitch: Float) = CritterPose.overlay(p, yaw, pitch, 1f)
    override fun busyAt(state: FaceState, t: Float) = CritterPose.busy(state, t)
}

/** The pygmy owl on its branch, its orb floating beside it. */
object PygmyOwl : CritterFace("pygmyowl", "Pygmy Owl", CritterShaders.PYGMY_OWL) {
    override fun pose(f: FaceFrame) =
        OwlPose.pose(f.state, f.prevState, f.hitchPhase, f.t, f.amp, hist = hist(f), opts = opts(f))
    override fun uniformsOf(p: FloatArray, mouth: FloatArray?) = OwlPose.uniforms(p, mouth)
    override fun overlayOf(p: FloatArray, yaw: Float, pitch: Float) = OwlPose.overlay(p, yaw, pitch, 1f)
    override fun busyAt(state: FaceState, t: Float) = OwlPose.busy(state, t)
}

/** The sea otter afloat in its pool, a glowing pebble on its chest. */
object SeaOtter : CritterFace("seaotter", "Sea Otter", CritterShaders.SEA_OTTER) {
    override fun pose(f: FaceFrame) =
        OtterPose.pose(f.state, f.prevState, f.hitchPhase, f.t, f.amp, hist = hist(f), opts = opts(f))
    override fun uniformsOf(p: FloatArray, mouth: FloatArray?) = OtterPose.uniforms(p, mouth)
    override fun overlayOf(p: FloatArray, yaw: Float, pitch: Float) = OtterPose.overlay(p, yaw, pitch, 1f)
    override fun busyAt(state: FaceState, t: Float) = OtterPose.busy(state, t)
}

/**
 * The monkey, hanging by one arm from its vine and swinging gently, its
 * banana - its orb - in the other hand; asleep, it sits on the vine.
 */
object Monkey : CritterFace("monkey", "Monkey", CritterShaders.MONKEY) {
    override fun pose(f: FaceFrame) =
        MonkeyPose.pose(f.state, f.prevState, f.hitchPhase, f.t, f.amp, hist = hist(f), opts = opts(f))
    override fun uniformsOf(p: FloatArray, mouth: FloatArray?) = MonkeyPose.uniforms(p, mouth)
    override fun overlayOf(p: FloatArray, yaw: Float, pitch: Float) = MonkeyPose.overlay(p, yaw, pitch, 1f)
    override fun busyAt(state: FaceState, t: Float) = MonkeyPose.busy(state, t)
}

/**
 * Compiles all four animals' shaders on the calling thread - meant for a
 * background one ([kotlinx.coroutines.Dispatchers.Default]). Appearance
 * calls it when it opens: its picker draws a still of every face, and
 * compiling four large animal shaders on the main thread the first time
 * those stills are drawn cost the frame. Drawing is unchanged; each
 * animal's first draw just finds its shader already built.
 */
fun warmCritterShaders() {
    RedPanda.warm()
    PygmyOwl.warm()
    SeaOtter.warm()
    Monkey.warm()
}
