package com.jarvis.client.face

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.nativeCanvas
import com.jarvis.client.FaceState

/**
 * The red panda - the first animal face, and the first CHARACTER.
 *
 * The other twenty are instruments: rings, orbits, a drum skin. A character
 * needs its own pose for every state, so this one reads the real state
 * ([FaceFrame.state]) rather than the borrowed movement ([FaceFrame.motion]):
 * it sleeps through standby, waves for an approval, scratches its head at an
 * error and dozes when banked. The shell's transforms (dim, the approval
 * clock, the error shake) still apply around it exactly as for every face.
 *
 * Drawn like [Nucleus]: one AGSL fragment shader through
 * `android.graphics.RuntimeShader`, one ray per real pixel, no mesh and no
 * model file. The shader comes from the SAME source as the desktop's
 * (`jarvis-desktop/critters/redpanda.sksl`, generated into [CritterShaders]),
 * and the pose from [CritterPose], which is checked against the desktop's
 * copy by `CritterPoseTest` - so the phone's panda is the desktop's panda,
 * not a lookalike.
 *
 * Colour: the fur keeps its own colours. [draw]'s `hot` - the owner's bound
 * colour for this state - is the orb the panda holds, which is also a real
 * light on its paws and chin; `cool` is the rim light round its fur.
 * Repainting the whole animal per state would read as a different animal.
 */
object RedPanda : Face {
    override val id = "redpanda"
    override val name = "Red Panda"

    // The shell's spin rate. This receives the BORROWED movement (approval,
    // standby and banked arrive as IDLE, error as THINKING), so the desktop's
    // `st[...].sp` for those four states is set to the borrowed movement's
    // rate - the orb then swirls at the same pace on both. Only the orb's
    // swirl turns with it: breathing and blinking run on the clock, so the
    // panda never freezes when a state's spin stops (banked).
    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 1.0f
        FaceState.THINKING -> 1.6f
        FaceState.SPEAKING -> 0.8f
        else -> 0.5f
    }

    // Compiled lazily on first draw, like Nucleus's: `Faces.all` touches
    // every face at startup, and an owner who never picks the panda should
    // never pay for compiling it.
    private val shader by lazy { android.graphics.RuntimeShader(CritterShaders.RED_PANDA) }
    private val brush by lazy { androidx.compose.ui.graphics.ShaderBrush(shader) }
    private val paint by lazy { android.graphics.Paint().apply { shader = this@RedPanda.shader } }

    /**
     * How much of the phone's full resolution the panda is traced at, before
     * it is enlarged to fill the face.
     *
     * Why not full resolution, as Nucleus does: measured through Skia (the
     * engine Android draws with), the panda costs 10-12 times Nucleus per
     * pixel, and at the Large face size a Pixel 9 would be asked for well
     * over what its graphics chip can do at the display's rate. Half the
     * width and height is a quarter of the pixels, so about a quarter of the
     * work - and because the panda is soft and rounded, the enlarged picture
     * differs from the sharp one by about 1/255 on average; the shader's own
     * feathered outline hides the steps enlarging would otherwise show.
     *
     * Tied to the quality tier's own graphics scale, so when Auto adjust
     * steps down because frames arrive late, the panda gets cheaper too
     * (High 0.5, Medium 0.4, Low about 0.31). Max, chosen by hand, asks for
     * sharpness and gets 0.75.
     */
    private fun traceScale(): Float {
        val tier = FaceQuality.current.tier
        return if (tier == QualityTier.MAX) 0.75f else 0.5f * tier.gpu
    }

    /**
     * The small offscreen pictures the panda is traced into, one per size.
     *
     * One per SIZE rather than one shared: the live face and the picker's
     * still thumbnail can be on screen together, and a picture re-recorded
     * for one would change the other's too - a thumbnail that is only drawn
     * once would start showing the live panda. Different places draw it at
     * different sizes, so the size tells them apart. Capped, because a face
     * whose size animates passes through many sizes; dropping one is safe -
     * whatever already drew it keeps its own reference until it redraws.
     */
    private val layers = LinkedHashMap<Int, android.graphics.RenderNode>()

    private fun layerFor(px: Int): android.graphics.RenderNode {
        layers[px]?.let { return it }
        if (layers.size >= 4) layers.remove(layers.keys.first())
        return android.graphics.RenderNode("redpanda").apply {
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
        val pose = CritterPose.pose(
            state = f.state,
            prevState = f.prevState,
            since = f.hitchPhase,
            t = f.t,
            amp = f.amp,
            hist = CritterPose.Hist(prev2 = f.prevState2, gap = f.prevGap, prevAmp = f.prevAmp),
        )
        for ((name, v) in CritterPose.uniforms(pose)) {
            when (v.size) {
                1 -> shader.setFloatUniform(name, v[0])
                2 -> shader.setFloatUniform(name, v[0], v[1])
                3 -> shader.setFloatUniform(name, v[0], v[1], v[2])
                else -> shader.setFloatUniform(name, v[0], v[1], v[2], v[3])
            }
        }
        shader.setFloatUniform("uHot", hot.red, hot.green, hot.blue)
        shader.setFloatUniform("uCool", cool.red, cool.green, cool.blue)
        // Dragging turns the camera round the panda, as it turns every other
        // 3D face; there is no automatic spin - a character faces you.
        shader.setFloatUniform("uYaw", f.yaw)
        shader.setFloatUniform("uPit", f.pitch)
        shader.setFloatUniform("uZoom", 1f)
        shader.setFloatUniform("uTime", f.angle)

        // Same framing as Nucleus: the desktop's p = 1 is half its canvas,
        // which is 2r here. The panda is drawn over the square 4r a side
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
