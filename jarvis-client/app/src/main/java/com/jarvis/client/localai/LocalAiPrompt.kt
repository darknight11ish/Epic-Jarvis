package com.jarvis.client.localai

/**
 * Builds the text a GGUF model is asked with, including the conversation so
 * far.
 *
 * ## Where this comes from
 *
 * A Kotlin re-expression of PrivateLM's prompt builders in
 * `lib/services/inference_android.dart` (`_buildChatML`, `_buildGemma`,
 * `_buildLlama3`; `orailnoor/cross-platform-llm-client`, MIT, © 2025
 * dragneel2074). The shapes, the 300-character turn cap and the "last few
 * turns" window are carried across; the Flutter layer is not.
 *
 * ## Why the app needs it at all
 *
 * The JNI contract takes ONE prompt string. A model has no memory of the last
 * call, so without this a "chat" would be a series of unrelated questions.
 * The phone therefore sends the recent turns in the format the model was
 * trained on:
 *
 * - Gemma models: `<start_of_turn>user … <end_of_turn>` with an opening
 *   "Understood." turn;
 * - Llama 3 models: the `<|start_header_id|>` headers;
 * - everything else (Qwen2.5, the model this slice expects): ChatML's
 *   `<|im_start|>role … <|im_end|>`.
 *
 * The template is chosen from the model's own file name, the same
 * auto-detection PrivateLM uses. A wrong guess produces a worse answer, never
 * a crash, and the chat keeps working; the model's header could carry a
 * template name, but that is a later refinement, not something to invent here.
 *
 * Pure Kotlin, so `LocalAiPromptTest` can hold every byte of every format on a
 * JVM.
 */
object LocalAiPrompt {

    /** Who said a turn. */
    enum class Role { USER, ASSISTANT }

    /** One previous turn, with the words exactly as they were shown. */
    data class Turn(val role: Role, val text: String)

    /** The template a model expects. */
    enum class Template { CHATML, GEMMA, LLAMA3 }

    /**
     * The system sentence every template starts with. Short on purpose: a
     * small model on a phone spends real seconds on every token of prompt, and
     * this is not a place to restate the app.
     */
    const val SYSTEM =
        "You are Jarvis, a small assistant running on the owner's phone. " +
            "Answer briefly, in plain words. Nothing you say leaves this phone."

    /** How many previous turns are sent at most. */
    const val MAX_HISTORY_TURNS = 8

    /** A previous turn longer than this is cut, with "..." - the Dart rule. */
    const val MAX_TURN_CHARS = 300

    /** Which template [modelName] looks like, from its own file name. */
    fun templateFor(modelName: String?): Template {
        val name = modelName.orEmpty().lowercase()
        return when {
            name.contains("gemma") -> Template.GEMMA
            name.contains("llama-3") || name.contains("llama3") -> Template.LLAMA3
            else -> Template.CHATML
        }
    }

    /**
     * The whole prompt for [message]: the system sentence, the last
     * [MAX_HISTORY_TURNS] turns, then the new question and the assistant's
     * opening marker.
     */
    fun build(
        modelName: String?,
        history: List<Turn>,
        message: String,
        systemPrompt: String = SYSTEM,
    ): String {
        val recent = history.takeLast(MAX_HISTORY_TURNS).map { Turn(it.role, truncate(it.text)) }
        return when (templateFor(modelName)) {
            Template.GEMMA -> gemma(message, recent, systemPrompt)
            Template.LLAMA3 -> llama3(message, recent, systemPrompt)
            Template.CHATML -> chatMl(message, recent, systemPrompt)
        }
    }

    private fun chatMl(message: String, history: List<Turn>, systemPrompt: String): String {
        val out = StringBuilder()
        out.append("<|im_start|>system\n").append(systemPrompt).append("<|im_end|>\n")
        for (turn in history) {
            out.append("<|im_start|>")
                .append(if (turn.role == Role.ASSISTANT) "assistant" else "user")
                .append("\n")
                .append(turn.text)
                .append("<|im_end|>\n")
        }
        out.append("<|im_start|>user\n").append(message).append("<|im_end|>\n")
        out.append("<|im_start|>assistant\n")
        return out.toString()
    }

    private fun gemma(message: String, history: List<Turn>, systemPrompt: String): String {
        val out = StringBuilder()
        out.append("<start_of_turn>user\n")
            .append(systemPrompt)
            .append("<end_of_turn>\n<start_of_turn>model\nUnderstood.<end_of_turn>\n")
        for (turn in history) {
            val role = if (turn.role == Role.ASSISTANT) "model" else "user"
            out.append("<start_of_turn>").append(role).append("\n")
                .append(turn.text)
                .append("<end_of_turn>\n")
        }
        out.append("<start_of_turn>user\n").append(message).append("<end_of_turn>\n")
        out.append("<start_of_turn>model\n")
        return out.toString()
    }

    private fun llama3(message: String, history: List<Turn>, systemPrompt: String): String {
        val out = StringBuilder()
        out.append("<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n")
            .append(systemPrompt)
            .append("<|eot_id|>")
        for (turn in history) {
            val role = if (turn.role == Role.ASSISTANT) "assistant" else "user"
            out.append("<|start_header_id|>").append(role).append("<|end_header_id|>\n\n")
                .append(turn.text)
                .append("<|eot_id|>")
        }
        out.append("<|start_header_id|>user<|end_header_id|>\n\n")
            .append(message)
            .append("<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n")
        return out.toString()
    }

    private fun truncate(text: String): String =
        if (text.length > MAX_TURN_CHARS) text.take(MAX_TURN_CHARS) + "..." else text
}
