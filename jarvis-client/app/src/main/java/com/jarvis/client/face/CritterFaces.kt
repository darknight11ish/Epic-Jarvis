package com.jarvis.client.face

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.nativeCanvas
import com.jarvis.client.FaceState

/**
 * An animal face - a CHARACTER, where the other twenty faces are
 * instruments (rings, orbits, a drum skin). Three of them: [RedPanda],
 * [PygmyOwl] and [SeaOtter], each only its shader and its pose; everything
 * about how an animal is drawn on the phone lives here, once.
 *
 * A character needs its own pose for every state, so an animal reads the
 * real state ([FaceFrame.state]) rather than the borrowed movement
 * ([FaceFrame.motion]): it sleeps through standby, waves for an approval,
 * is puzzled at an error and dozes when banked. The shell's transforms (dim,
 * the approval clock, the error shake) still apply around it exactly as for
 * every face.
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

    /** This animal's pose for the frame, as uniform name to value. */
    protected abstract fun uniforms(f: FaceFrame): Map<String, FloatArray>

    /** What the host remembered at the last state change (see [CritterPose.Hist]). */
    protected fun hist(f: FaceFrame) =
        CritterPose.Hist(prev2 = f.prevState2, gap = f.prevGap, prevAmp = f.prevAmp)

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
    // never pay for compiling it.
    private val shader by lazy { android.graphics.RuntimeShader(source) }
    private val brush by lazy { androidx.compose.ui.graphics.ShaderBrush(shader) }
    private val paint by lazy { android.graphics.Paint().apply { shader = this@CritterFace.shader } }

    /**
     * How much of the phone's full resolution an animal is traced at, before
     * it is enlarged to fill the face.
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
     * Tied to the quality tier's own graphics scale, so when Auto adjust
     * steps down because frames arrive late, the animal gets cheaper too
     * (High 0.5, Medium 0.4, Low about 0.31). Max, chosen by hand, asks for
     * sharpness and gets 0.75.
     */
    private fun traceScale(): Float {
        val tier = FaceQuality.current.tier
        return if (tier == QualityTier.MAX) 0.75f else 0.5f * tier.gpu
    }

    /**
     * The small offscreen pictures this animal is traced into, one per size.
     *
     * One per SIZE rather than one shared: the live face and the picker's
     * still thumbnail can be on screen together, and a picture re-recorded
     * for one would change the other's too - a thumbnail that is only drawn
     * once would start showing the live animal. Different places draw it at
     * different sizes, so the size tells them apart. Capped, because a face
     * whose size animates passes through many sizes; dropping one is safe -
     * whatever already drew it keeps its own reference until it redraws.
     */
    private val layers = LinkedHashMap<Int, android.graphics.RenderNode>()

    private fun layerFor(px: Int): android.graphics.RenderNode {
        layers[px]?.let { return it }
        if (layers.size >= 4) layers.remove(layers.keys.first())
        return android.graphics.RenderNode(id).apply {
            // Forces an offscreen buffer the size of this node. That buffer
            // is what makes this cheaper: the shader runs once per pixel of
            // IT, and the enlarging happens when it is drawn scaled below.
            setUseCompositingLayer(true, null)
            layers[px] = this
        }
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        for ((name, v) in uniforms(f)) {
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
            drawRect(brush = brush, topLeft = Offset(cx - 2f * r, cy - 2f * r), size = Size(side, side))
            return@with
        }

        val px = kotlin.math.ceil(side * traceScale()).toInt().coerceIn(64, kotlin.math.ceil(side).toInt().coerceAtLeast(64))
        val k = px / side
        shader.setFloatUniform("uCenter", px / 2f, px / 2f)
        shader.setFloatUniform("uR", 2f * r * k)
        // One pixel of the small picture, for the shader's feathered outline.
        shader.setFloatUniform("uPx", 1f / (2f * r * k))

        val node = layerFor(px)
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
    }
}

/** The red panda, holding its orb in its lap. */
object RedPanda : CritterFace("redpanda", "Red Panda", CritterShaders.RED_PANDA) {
    override fun uniforms(f: FaceFrame) = CritterPose.uniforms(
        CritterPose.pose(f.state, f.prevState, f.hitchPhase, f.t, f.amp, hist = hist(f)),
    )
}

/** The pygmy owl on its branch, its orb floating beside it. */
object PygmyOwl : CritterFace("pygmyowl", "Pygmy Owl", CritterShaders.PYGMY_OWL) {
    override fun uniforms(f: FaceFrame) = OwlPose.uniforms(
        OwlPose.pose(f.state, f.prevState, f.hitchPhase, f.t, f.amp, hist = hist(f)),
    )
}

/** The sea otter afloat in its pool, a glowing pebble on its chest. */
object SeaOtter : CritterFace("seaotter", "Sea Otter", CritterShaders.SEA_OTTER) {
    override fun uniforms(f: FaceFrame) = OtterPose.uniforms(
        OtterPose.pose(f.state, f.prevState, f.hitchPhase, f.t, f.amp, hist = hist(f)),
    )
}
