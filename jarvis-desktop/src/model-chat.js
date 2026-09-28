/**
 * Can this installed model hold a conversation? An embedding model such as
 * nomic-embed-text only turns text into numbers for memory search; switching
 * to it would leave Jarvis unable to answer anything (play tester,
 * 2026-09-27: Brain › Model offered "Use" on it).
 *
 * The phone applies the same rule (`net/ModelChat.kt`). Both are held to
 * tests/fixtures/model-chat-cases.json, which tools/gen_model_chat_cases.py
 * writes for both apps (tests/model-chat.mjs here, ModelChatContractTest on
 * the phone).
 *
 * No page, no Tauri: node can import it.
 *
 * @module model-chat
 */

/** Why a model has no "Use" button. */
export const CANNOT_CHAT = "for memory search only - it cannot chat";

/**
 * The real `/api/models` sends `installed` as bare names (gpu-offload.patch),
 * so the name is usually all there is. When a row does carry Ollama's own
 * `capabilities` list, that wins: no "completion" means no chat. Otherwise
 * a BERT-family model or "embed" / "minilm" / "bge" in the name is an
 * embedding model - the ones Ollama's library offers are named that way.
 *
 * @param {{capabilities?: unknown, family?: unknown}} m the row
 * @param {string} ref the model's name
 */
export function canChat(m, ref) {
  if (Array.isArray(m.capabilities)) return m.capabilities.includes("completion");
  if (/bert/i.test(String(m.family || ""))) return false;
  return !/embed|minilm|(^|[^a-z])bge/i.test(ref);
}
