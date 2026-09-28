package com.jarvis.client.net

/**
 * Can this installed model hold a conversation? An embedding model such as
 * nomic-embed-text only turns text into numbers for memory search; switching
 * to it would leave Jarvis unable to answer anything (play tester,
 * 2026-09-27: Brain › Model offered "Use" on it, on the desktop and here).
 *
 * The same rule as the desktop's `src/model-chat.js`, and the same words.
 * Both are held to `contract/model-chat-cases.json`, which
 * tools/gen_model_chat_cases.py writes for both apps
 * (ModelChatContractTest here, tests/model-chat.mjs on the desktop).
 *
 * The real `/api/models` sends `installed` as bare names (gpu-offload.patch),
 * so the name is usually all there is. When a row does carry Ollama's own
 * `capabilities` list, that wins: no "completion" in it means no chat.
 * Otherwise a BERT-family model, or "embed" / "minilm" / "bge" in the name,
 * is an embedding model - the ones Ollama's library offers are named that way.
 */
object ModelChat {

    /** Shown on the row instead of a "Use" button: why there is none. */
    const val CANNOT_CHAT = "for memory search only - it cannot chat"

    // Matched against the lower-cased name. The desktop's regex is
    // /embed|minilm|(^|[^a-z])bge/i; lower-casing first gives the same
    // answer for these ASCII names without relying on how a case-insensitive
    // negated class like [^a-z] behaves, which differs between engines.
    private val EMBEDDING_NAME = Regex("embed|minilm|(^|[^a-z])bge")

    fun canChat(ref: String, family: String? = null, capabilities: List<String>? = null): Boolean {
        if (capabilities != null) return "completion" in capabilities
        if (family != null && family.contains("bert", ignoreCase = true)) return false
        return !EMBEDDING_NAME.containsMatchIn(ref.lowercase())
    }
}
