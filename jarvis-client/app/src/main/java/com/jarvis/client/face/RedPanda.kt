package com.jarvis.client.face

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
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
        // which is 2r here.
        shader.setFloatUniform("uCenter", cx, cy)
        shader.setFloatUniform("uR", 2f * r)
        // A ray that misses the panda (and the orb's glow) returns
        // transparent, so the square's corners cost one test and paint nothing.
        drawRect(
            brush = brush,
            topLeft = Offset(cx - 2f * r, cy - 2f * r),
            size = Size(4f * r, 4f * r),
        )
    }
}
