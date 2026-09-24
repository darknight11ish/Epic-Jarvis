package com.jarvis.client.voice

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.nio.FloatBuffer

/**
 * Smart Turn v3.2 (`assets/turn/smart-turn-v3.2-cpu.onnx`), run by the same
 * ONNX Runtime 1.22.0 the wake word uses - see [OrtWakeModels] for why that
 * exact version. One input, `input_features` [1, 80, 800]; one output, the
 * probability the turn is complete (the model applies its own sigmoid).
 *
 * CPU, one thread: it runs once per pause, not continuously.
 *
 * The same class runs on a desktop JVM with the plain `onnxruntime` jar,
 * which is how it was checked against the PC's Python on the same clips.
 */
class OrtTurnModel private constructor(
    private val env: OrtEnvironment,
    private val session: OrtSession,
) : TurnModel {

    private val input = session.inputNames.first()

    override fun probability(features: FloatArray): Float {
        val shape = longArrayOf(1, WhisperFeatures.N_MELS.toLong(), WhisperFeatures.N_FRAMES.toLong())
        return OnnxTensor.createTensor(env, FloatBuffer.wrap(features), shape).use { t ->
            session.run(mapOf(input to t)).use { r ->
                @Suppress("UNCHECKED_CAST")
                (r.get(0).value as Array<FloatArray>)[0][0]
            }
        }
    }

    override fun close() {
        runCatching { session.close() }
    }

    companion object {
        /** In `assets/turn/`, and on the PC in `voice-models\turn`. */
        const val FILE = "smart-turn-v3.2-cpu.onnx"

        /** Throws if the model will not load; the caller then uses the old fixed pause. */
        fun load(bytes: ByteArray): OrtTurnModel {
            val env = OrtEnvironment.getEnvironment()
            val opts = OrtSession.SessionOptions()
            opts.setIntraOpNumThreads(1)
            opts.setInterOpNumThreads(1)
            return OrtTurnModel(env, env.createSession(bytes, opts))
        }
    }
}
