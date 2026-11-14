// jarvis_llama_jni.cpp - JNI bridge for the Jarvis on-device GGUF engine (E1).
//
// Adapted for Epic-Jarvis from the MIT-licensed Android plugin in
//   orailnoor/cross-platform-llm-client  (MIT (c) 2025 dragneel2074)
//   local_plugins/llama_flutter_android/android/src/main/cpp/jni_wrapper.cpp
// The original is a Flutter plugin wrapper with global state, mtmd/vision,
// Vulkan and phone-cluster support. This file keeps its proven llama.cpp call
// sequence (GGUF pre-flight, batched prompt evaluation, KV-cache prefix reuse,
// UTF-8-safe token streaming, log capture) and re-shapes it to the Epic-Jarvis
// contract:
//
//   object LlamaNative {
//       external fun nativeCreate(): Long
//       external fun nativeLoad(handle: Long, modelPath: String, nThreads: Int, nCtx: Int): Int
//       external fun nativeGenerate(handle: Long, prompt: String, maxTokens: Int,
//                                   temperature: Float, sink: TokenSink): Int
//       external fun nativeUnload(handle: Long)
//       external fun nativeDestroy(handle: Long)
//       external fun nativeLastError(handle: Long): String
//       external fun nativeVersion(): String
//       external fun nativeStats(handle: Long): LongArray  // [promptTokens, genTokens, genMillis]
//   }
//   interface TokenSink { fun emit(piece: String); fun stopped(): Boolean }
//
// Differences from the wrapper that matter:
//   * one Engine per `handle` (a Java long) instead of process-wide globals, so
//     unload/destroy are well defined;
//   * CPU only: no Vulkan, no RPC/phone-cluster, no mtmd, no dynamic backends;
//   * cancellation is the TokenSink.stopped() poll, checked once per token,
//     instead of a separate nativeStop() entry point;
//   * strings cross the JNI boundary as real UTF-8 <-> UTF-16 (NewString with
//     jchar), not NewStringUTF/GetStringUTFChars, because modified UTF-8 mangles
//     emoji and partial multi-byte token pieces. The wrapper's sanitizeUTF8()
//     approach is replaced by a stream that holds an incomplete trailing code
//     point until the next token completes it.
//
// Return codes are 0 on success and negative on failure; the human-readable
// reason is available from nativeLastError(handle).
//
// llama.cpp is MIT (c) the ggml authors. See licenses/ for both licences.

#include <jni.h>
#include <android/log.h>

#include "llama.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <exception>
#include <fstream>
#include <mutex>
#include <new>
#include <string>
#include <thread>
#include <vector>

#define LOG_TAG "JarvisLlama"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGW(...) __android_log_print(ANDROID_LOG_WARN, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

namespace {

// --- result codes -----------------------------------------------------------
// Kept negative so a caller that only checks "!= 0" - or that logs the number -
// can tell success from failure at a glance.
enum : jint {
    JARVIS_RC_OK          =  0,
    JARVIS_RC_BAD_HANDLE  = -1,
    JARVIS_RC_BAD_ARG     = -2,
    JARVIS_RC_NOT_LOADED  = -3,
    JARVIS_RC_MODEL_LOAD  = -4,
    JARVIS_RC_TOKENIZE    = -5,
    JARVIS_RC_DECODE      = -6,
    JARVIS_RC_INTERNAL    = -7,
};

// --- llama.cpp log forwarding + load-error capture --------------------------
// llama.cpp logs through a process-wide callback. During model/context load we
// capture the last ERROR block so nativeLoad() can return "why" instead of a
// bare failure (same idea as the wrapper's g_load_error).
std::mutex g_capture_mutex;
std::string g_captured_error;
bool g_capture_errors = false;
std::atomic<bool> g_last_log_was_debug{false};

void jarvisLlamaLog(ggml_log_level level, const char* text, void* /*user_data*/) {
    if (!text) return;

    // Newer llama.cpp emits thousands of DEBUG lines per load; suppress them
    // and the CONT lines that belong to them (same policy as the wrapper).
    if (level == GGML_LOG_LEVEL_DEBUG) {
        g_last_log_was_debug = true;
        return;
    }
    const bool cont_of_debug = (level == GGML_LOG_LEVEL_CONT && g_last_log_was_debug);
    if (level != GGML_LOG_LEVEL_CONT) g_last_log_was_debug = false;
    if (cont_of_debug) return;

    int priority = ANDROID_LOG_INFO;
    if (level == GGML_LOG_LEVEL_ERROR) priority = ANDROID_LOG_ERROR;
    else if (level == GGML_LOG_LEVEL_WARN) priority = ANDROID_LOG_WARN;
    __android_log_write(priority, LOG_TAG, text);

    std::lock_guard<std::mutex> lock(g_capture_mutex);
    if (!g_capture_errors) return;
    if (level == GGML_LOG_LEVEL_ERROR) {
        g_captured_error.assign(text);
    } else if (level == GGML_LOG_LEVEL_CONT && !g_captured_error.empty()) {
        g_captured_error.append(text);
    }
    if (g_captured_error.size() > 4096) {
        g_captured_error.erase(0, g_captured_error.size() - 4096);
    }
}

void beginCapture() {
    std::lock_guard<std::mutex> lock(g_capture_mutex);
    g_captured_error.clear();
    g_capture_errors = true;
}

std::string endCapture() {
    std::lock_guard<std::mutex> lock(g_capture_mutex);
    g_capture_errors = false;
    while (!g_captured_error.empty() &&
           (g_captured_error.back() == '\n' || g_captured_error.back() == '\r')) {
        g_captured_error.pop_back();
    }
    return g_captured_error;
}

// --- UTF-8 <-> UTF-16 -------------------------------------------------------
void appendUtf8(std::string& out, uint32_t cp) {
    if (cp <= 0x7F) {
        out.push_back(static_cast<char>(cp));
    } else if (cp <= 0x7FF) {
        out.push_back(static_cast<char>(0xC0 | (cp >> 6)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    } else if (cp <= 0xFFFF) {
        out.push_back(static_cast<char>(0xE0 | (cp >> 12)));
        out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    } else {
        out.push_back(static_cast<char>(0xF0 | (cp >> 18)));
        out.push_back(static_cast<char>(0x80 | ((cp >> 12) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    }
}

// Java String -> standard UTF-8. (GetStringUTFChars would give modified UTF-8,
// which is not what llama_tokenize() expects.)
std::string jstringToUtf8(JNIEnv* env, jstring value) {
    if (!value) return {};
    const jsize len = env->GetStringLength(value);
    if (len <= 0) return {};
    const jchar* chars = env->GetStringChars(value, nullptr);
    if (!chars) return {};

    std::string out;
    out.reserve(static_cast<size_t>(len) * 3);
    for (jsize i = 0; i < len; ++i) {
        uint32_t cp = chars[i];
        if (cp >= 0xD800 && cp <= 0xDBFF) {
            if (i + 1 < len) {
                const uint32_t lo = chars[i + 1];
                if (lo >= 0xDC00 && lo <= 0xDFFF) {
                    cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                    ++i;
                } else {
                    cp = 0xFFFD;
                }
            } else {
                cp = 0xFFFD;
            }
        } else if (cp >= 0xDC00 && cp <= 0xDFFF) {
            cp = 0xFFFD;
        }
        appendUtf8(out, cp);
    }
    env->ReleaseStringChars(value, chars);
    return out;
}

// Standard UTF-8 -> Java String (UTF-16). Input is produced by Utf8Stream below
// and is valid, but malformed bytes are replaced rather than trusted.
jstring newStringFromUtf8(JNIEnv* env, const std::string& utf8) {
    std::u16string u16;
    u16.reserve(utf8.size());
    size_t i = 0;
    while (i < utf8.size()) {
        const unsigned char c = static_cast<unsigned char>(utf8[i]);
        uint32_t cp = 0xFFFD;
        size_t used = 1;
        if (c < 0x80) {
            cp = c;
        } else if ((c & 0xE0) == 0xC0 && i + 1 < utf8.size()) {
            cp = ((c & 0x1Fu) << 6) | (static_cast<unsigned char>(utf8[i + 1]) & 0x3Fu);
            used = 2;
        } else if ((c & 0xF0) == 0xE0 && i + 2 < utf8.size()) {
            cp = ((c & 0x0Fu) << 12) |
                 ((static_cast<unsigned char>(utf8[i + 1]) & 0x3Fu) << 6) |
                 (static_cast<unsigned char>(utf8[i + 2]) & 0x3Fu);
            used = 3;
        } else if ((c & 0xF8) == 0xF0 && i + 3 < utf8.size()) {
            cp = ((c & 0x07u) << 18) |
                 ((static_cast<unsigned char>(utf8[i + 1]) & 0x3Fu) << 12) |
                 ((static_cast<unsigned char>(utf8[i + 2]) & 0x3Fu) << 6) |
                 (static_cast<unsigned char>(utf8[i + 3]) & 0x3Fu);
            used = 4;
        }
        if (cp > 0x10FFFF) cp = 0xFFFD;
        if (cp >= 0x10000) {
            cp -= 0x10000;
            u16.push_back(static_cast<char16_t>(0xD800 + (cp >> 10)));
            u16.push_back(static_cast<char16_t>(0xDC00 + (cp & 0x3FF)));
        } else if (cp >= 0xD800 && cp <= 0xDFFF) {
            u16.push_back(static_cast<char16_t>(0xFFFD));
        } else {
            u16.push_back(static_cast<char16_t>(cp));
        }
        i += used;
    }
    return env->NewString(reinterpret_cast<const jchar*>(u16.data()),
                          static_cast<jsize>(u16.size()));
}

bool decodeCodepoint(const std::string& s, size_t at, size_t need, uint32_t& cp) {
    cp = 0;
    switch (need) {
        case 2:
            if ((static_cast<unsigned char>(s[at + 1]) & 0xC0) != 0x80) return false;
            cp = ((static_cast<unsigned char>(s[at]) & 0x1Fu) << 6) |
                 (static_cast<unsigned char>(s[at + 1]) & 0x3Fu);
            return cp >= 0x80;
        case 3:
            if ((static_cast<unsigned char>(s[at + 1]) & 0xC0) != 0x80 ||
                (static_cast<unsigned char>(s[at + 2]) & 0xC0) != 0x80) {
                return false;
            }
            cp = ((static_cast<unsigned char>(s[at]) & 0x0Fu) << 12) |
                 ((static_cast<unsigned char>(s[at + 1]) & 0x3Fu) << 6) |
                 (static_cast<unsigned char>(s[at + 2]) & 0x3Fu);
            if (cp < 0x800) return false;
            if (cp >= 0xD800 && cp <= 0xDFFF) return false;
            return true;
        case 4:
            if ((static_cast<unsigned char>(s[at + 1]) & 0xC0) != 0x80 ||
                (static_cast<unsigned char>(s[at + 2]) & 0xC0) != 0x80 ||
                (static_cast<unsigned char>(s[at + 3]) & 0xC0) != 0x80) {
                return false;
            }
            cp = ((static_cast<unsigned char>(s[at]) & 0x07u) << 18) |
                 ((static_cast<unsigned char>(s[at + 1]) & 0x3Fu) << 12) |
                 ((static_cast<unsigned char>(s[at + 2]) & 0x3Fu) << 6) |
                 (static_cast<unsigned char>(s[at + 3]) & 0x3Fu);
            return cp >= 0x10000 && cp <= 0x10FFFF;
        default:
            return false;
    }
}

// A token piece may end in the middle of a multi-byte code point: llama.cpp
// splits text at token boundaries, not at character boundaries. Hold the
// incomplete tail here and prepend it to the next piece instead of emitting a
// replacement character (what sanitizeUTF8() in the original wrapper did).
class Utf8Stream {
public:
    std::string feed(const char* data, size_t len) {
        pending_.append(data, len);
        std::string out;
        size_t i = 0;
        while (i < pending_.size()) {
            const unsigned char c = static_cast<unsigned char>(pending_[i]);
            if (c < 0x80) {
                out.push_back(static_cast<char>(c));
                ++i;
                continue;
            }
            size_t need = 0;
            if ((c & 0xE0) == 0xC0) need = 2;
            else if ((c & 0xF0) == 0xE0) need = 3;
            else if ((c & 0xF8) == 0xF0) need = 4;

            if (need == 0) {  // invalid lead byte
                out += "\xEF\xBF\xBD";
                ++i;
                continue;
            }
            if (i + need > pending_.size()) break;  // wait for the next piece

            uint32_t cp = 0;
            if (!decodeCodepoint(pending_, i, need, cp)) {
                out += "\xEF\xBF\xBD";
                ++i;
                continue;
            }
            out.append(pending_, i, need);
            i += need;
        }
        pending_.erase(0, i);
        return out;
    }

    std::string flush() {
        if (pending_.empty()) return {};
        pending_.clear();
        return "\xEF\xBF\xBD";
    }

private:
    std::string pending_;
};

// --- engine state -----------------------------------------------------------
struct Engine {
    std::mutex mu;  // serialises load/generate/unload for this handle

    llama_model* model = nullptr;
    llama_context* ctx = nullptr;
    const llama_vocab* vocab = nullptr;

    // Tokens currently held in the KV cache (sequence 0), in order, so each
    // turn can reuse the prefix it shares with the previous prompt + reply.
    std::vector<llama_token> cached;
    int n_past = 0;

    // Last generation, reported by nativeStats().
    long long prompt_tokens = 0;
    long long gen_tokens = 0;
    long long gen_millis = 0;

    std::string last_error;
};

Engine* engineFrom(jlong handle) {
    return reinterpret_cast<Engine*>(static_cast<std::uintptr_t>(handle));
}

jint fail(Engine* e, jint code, const std::string& message) {
    if (e) e->last_error = message;
    LOGE("%s", message.c_str());
    return code;
}

void freeModelLocked(Engine* e) {
    if (e->ctx) {
        llama_free(e->ctx);
        e->ctx = nullptr;
    }
    if (e->model) {
        llama_model_free(e->model);
        e->model = nullptr;
    }
    e->vocab = nullptr;
    e->cached.clear();
    e->n_past = 0;
}

std::once_flag g_backend_once;

const std::string& buildVersionString() {
    static const std::string value = [] {
        std::string v = "llama.cpp ";
        v += llama_version();
        v += " / jarvis_llama 1 / ";
#if defined(__aarch64__)
        v += "arm64-v8a";
#elif defined(__x86_64__)
        v += "x86_64";
#else
        v += "unknown-abi";
#endif
        v += " / CPU";
        return v;
    }();
    return value;
}

}  // namespace

// ---------------------------------------------------------------------------
// JNI entry points.  Package com.jarvis.client.localai, class LlamaNative.
// ---------------------------------------------------------------------------

extern "C" JNIEXPORT jlong JNICALL
Java_com_jarvis_client_localai_LlamaNative_nativeCreate(JNIEnv* /*env*/, jobject /*thiz*/) {
    std::call_once(g_backend_once, [] {
        llama_log_set(jarvisLlamaLog, nullptr);
        llama_backend_init();
        LOGI("llama.cpp %s backend initialised (CPU only)", llama_version());
    });
    Engine* engine = new (std::nothrow) Engine();
    if (!engine) return 0;
    return static_cast<jlong>(reinterpret_cast<std::uintptr_t>(engine));
}

extern "C" JNIEXPORT jint JNICALL
Java_com_jarvis_client_localai_LlamaNative_nativeLoad(
        JNIEnv* env, jobject /*thiz*/, jlong handle, jstring model_path,
        jint n_threads, jint n_ctx) {
    Engine* engine = engineFrom(handle);
    if (!engine) return JARVIS_RC_BAD_HANDLE;
    try {
    std::lock_guard<std::mutex> lock(engine->mu);

    engine->last_error.clear();
    freeModelLocked(engine);

    if (!model_path) return fail(engine, JARVIS_RC_BAD_ARG, "model path is null");
    const std::string path = jstringToUtf8(env, model_path);
    if (path.empty()) return fail(engine, JARVIS_RC_BAD_ARG, "model path is empty");

    // Cheap pre-flight so the common mistakes produce a readable message
    // instead of a llama.cpp log line (same checks as the wrapper).
    {
        std::ifstream file(path, std::ios::binary | std::ios::ate);
        if (!file) {
            return fail(engine, JARVIS_RC_MODEL_LOAD,
                        "GGUF file is missing or unreadable: " + path);
        }
        const std::streamsize size = file.tellg();
        if (size < 4) {
            return fail(engine, JARVIS_RC_MODEL_LOAD,
                        "GGUF file is empty or truncated: " + path);
        }
        unsigned char magic[4] = {};
        file.seekg(0, std::ios::beg);
        file.read(reinterpret_cast<char*>(magic), sizeof(magic));
        if (!file || std::memcmp(magic, "GGUF", sizeof(magic)) != 0) {
            return fail(engine, JARVIS_RC_MODEL_LOAD,
                        "not a GGUF file (bad magic): " + path);
        }
    }

    int threads = n_threads > 0 ? static_cast<int>(n_threads)
                                : static_cast<int>(std::thread::hardware_concurrency());
    if (threads <= 0) threads = 4;
    threads = std::clamp(threads, 1, 32);

    llama_model_params model_params = llama_model_default_params();
    model_params.n_gpu_layers = 0;   // CPU only
    model_params.devices = nullptr;  // only the statically built CPU backend exists
    model_params.use_extra_bufts = true;
    model_params.check_tensors = false;

    beginCapture();
    engine->model = llama_model_load_from_file(path.c_str(), model_params);
    const std::string load_detail = endCapture();

    if (!engine->model) {
        std::string message = "failed to load GGUF model";
        if (!load_detail.empty()) {
            message += ": " + load_detail;
        } else {
            message += " (out of memory, or an unsupported GGUF architecture)";
        }
        return fail(engine, JARVIS_RC_MODEL_LOAD, message);
    }

    const int train_ctx = llama_model_n_ctx_train(engine->model);
    int ctx_size = n_ctx > 0
        ? static_cast<int>(n_ctx)
        : std::min(train_ctx > 0 ? train_ctx : 4096, 4096);
    if (ctx_size < 256) {
        LOGW("requested n_ctx=%d is too small; using 256", ctx_size);
        ctx_size = 256;
    }
    if (ctx_size > 131072) {
        LOGW("requested n_ctx=%d clamped to 131072", ctx_size);
        ctx_size = 131072;
    }
    const uint32_t batch = static_cast<uint32_t>(std::min(ctx_size, 512));

    llama_context_params ctx_params = llama_context_default_params();
    ctx_params.n_ctx = static_cast<uint32_t>(ctx_size);
    ctx_params.n_batch = batch;
    ctx_params.n_ubatch = batch;
    ctx_params.n_threads = threads;
    ctx_params.n_threads_batch = threads;
    ctx_params.embeddings = false;
    ctx_params.offload_kqv = false;
    ctx_params.op_offload = false;
    ctx_params.no_perf = true;

    beginCapture();
    engine->ctx = llama_init_from_model(engine->model, ctx_params);
    const std::string ctx_detail = endCapture();

    if (!engine->ctx) {
        std::string message = "failed to create llama context";
        if (!ctx_detail.empty()) message += ": " + ctx_detail;
        freeModelLocked(engine);
        return fail(engine, JARVIS_RC_MODEL_LOAD, message);
    }

    engine->vocab = llama_model_get_vocab(engine->model);
    if (!engine->vocab) {
        freeModelLocked(engine);
        return fail(engine, JARVIS_RC_MODEL_LOAD, "model has no vocabulary");
    }

    engine->cached.clear();
    engine->n_past = 0;
    engine->prompt_tokens = 0;
    engine->gen_tokens = 0;
    engine->gen_millis = 0;

    LOGI("model loaded: ctx=%d (train %d), batch=%u, threads=%d", ctx_size, train_ctx,
         batch, threads);
    return JARVIS_RC_OK;
    } catch (const std::exception& ex) {
        return fail(engine, JARVIS_RC_INTERNAL,
                    std::string("unhandled native exception while loading: ") + ex.what());
    } catch (...) {
        return fail(engine, JARVIS_RC_INTERNAL,
                    "unhandled native exception while loading the model");
    }
}

extern "C" JNIEXPORT jint JNICALL
Java_com_jarvis_client_localai_LlamaNative_nativeGenerate(
        JNIEnv* env, jobject /*thiz*/, jlong handle, jstring prompt,
        jint max_tokens, jfloat temperature, jobject sink) {
    Engine* engine = engineFrom(handle);
    if (!engine) return JARVIS_RC_BAD_HANDLE;
    try {
    std::lock_guard<std::mutex> lock(engine->mu);

    engine->last_error.clear();
    engine->prompt_tokens = 0;
    engine->gen_tokens = 0;
    engine->gen_millis = 0;

    if (!engine->model || !engine->ctx || !engine->vocab) {
        return fail(engine, JARVIS_RC_NOT_LOADED, "no model is loaded");
    }
    if (!prompt) return fail(engine, JARVIS_RC_BAD_ARG, "prompt is null");
    if (!sink) return fail(engine, JARVIS_RC_BAD_ARG, "TokenSink is null");
    if (max_tokens <= 0) {
        return fail(engine, JARVIS_RC_BAD_ARG, "maxTokens must be greater than 0");
    }

    const std::string prompt_text = jstringToUtf8(env, prompt);
    if (prompt_text.empty()) return fail(engine, JARVIS_RC_BAD_ARG, "prompt is empty");

    // --- tokenise -----------------------------------------------------------
    const int32_t probe = llama_tokenize(engine->vocab, prompt_text.data(),
                                         static_cast<int32_t>(prompt_text.size()),
                                         nullptr, 0, /*add_special=*/true,
                                         /*parse_special=*/true);
    if (probe == INT32_MIN) {
        return fail(engine, JARVIS_RC_TOKENIZE, "prompt tokenisation overflowed");
    }
    const int32_t needed = probe < 0 ? -probe : probe;
    if (needed <= 0) {
        return fail(engine, JARVIS_RC_TOKENIZE, "prompt produced no tokens");
    }

    std::vector<llama_token> tokens(static_cast<size_t>(needed));
    const int32_t got = llama_tokenize(engine->vocab, prompt_text.data(),
                                       static_cast<int32_t>(prompt_text.size()),
                                       tokens.data(), static_cast<int32_t>(tokens.size()),
                                       /*add_special=*/true, /*parse_special=*/true);
    if (got < 0) {
        return fail(engine, JARVIS_RC_TOKENIZE, "failed to tokenise the prompt");
    }
    tokens.resize(static_cast<size_t>(got));

    // --- fit the prompt into the context -----------------------------------
    const int n_ctx = static_cast<int>(llama_n_ctx(engine->ctx));
    const int reserve = static_cast<int>(
        std::min<long long>(std::max<long long>(static_cast<long long>(max_tokens), 64),
                            n_ctx / 2));
    const int budget = std::max(2, n_ctx - reserve);
    if (static_cast<int>(tokens.size()) > budget) {
        // Keep the start (system prompt) and the most recent part.
        const int head = std::min(256, budget / 4);
        std::vector<llama_token> trimmed(tokens.begin(), tokens.begin() + head);
        trimmed.insert(trimmed.end(), tokens.end() - (budget - head), tokens.end());
        LOGI("prompt of %zu tokens trimmed to %d to fit context %d", tokens.size(), budget,
             n_ctx);
        tokens.swap(trimmed);
    }
    engine->prompt_tokens = static_cast<long long>(tokens.size());

    // --- KV-cache prefix reuse ---------------------------------------------
    llama_memory_t memory = llama_get_memory(engine->ctx);
    if (!memory) return fail(engine, JARVIS_RC_INTERNAL, "context has no memory");

    size_t reuse = 0;
    while (reuse < engine->cached.size() && reuse < tokens.size() &&
           engine->cached[reuse] == tokens[reuse]) {
        ++reuse;
    }
    // At least one token must be decoded so there are logits to sample from.
    if (reuse >= tokens.size()) reuse = tokens.size() - 1;
    llama_memory_seq_rm(memory, 0, static_cast<llama_pos>(reuse), -1);
    engine->cached.resize(reuse);
    engine->n_past = static_cast<int>(reuse);

    // --- one batch buffer, used for prompt and for single-token decode ------
    int32_t batch_capacity = static_cast<int32_t>(
        std::min<uint32_t>(llama_n_batch(engine->ctx), 512));
    if (batch_capacity < 1) batch_capacity = 512;

    llama_batch batch = llama_batch_init(batch_capacity, 0, 1);
    if (!batch.token) {
        return fail(engine, JARVIS_RC_INTERNAL, "could not allocate a token batch");
    }

    int processed = static_cast<int>(reuse);
    while (processed < static_cast<int>(tokens.size())) {
        batch.n_tokens = 0;
        const int chunk =
            std::min(static_cast<int>(tokens.size()) - processed, batch_capacity);
        for (int i = 0; i < chunk; ++i) {
            const int position = processed + i;
            const int index = batch.n_tokens;
            batch.token[index] = tokens[static_cast<size_t>(position)];
            batch.pos[index] = static_cast<llama_pos>(position);
            batch.n_seq_id[index] = 1;
            batch.seq_id[index][0] = 0;
            batch.logits[index] =
                (position == static_cast<int>(tokens.size()) - 1) ? 1 : 0;
            batch.n_tokens++;
        }
        const int rc = llama_decode(engine->ctx, batch);
        if (rc != 0) {
            llama_batch_free(batch);
            return fail(engine, JARVIS_RC_DECODE,
                        "failed to evaluate the prompt (llama_decode returned " +
                            std::to_string(rc) + ")");
        }
        processed += chunk;
    }
    engine->n_past = static_cast<int>(tokens.size());
    engine->cached = tokens;

    // --- sampler ------------------------------------------------------------
    float temp = std::isfinite(static_cast<float>(temperature))
        ? static_cast<float>(temperature)
        : 0.7f;
    temp = std::clamp(temp, 0.0f, 2.0f);

    llama_sampler_chain_params sampler_params = llama_sampler_chain_default_params();
    sampler_params.no_perf = true;
    llama_sampler* sampler = llama_sampler_chain_init(sampler_params);
    if (!sampler) {
        llama_batch_free(batch);
        return fail(engine, JARVIS_RC_INTERNAL, "could not create the sampler chain");
    }
    if (temp <= 0.0f) {
        llama_sampler_chain_add(sampler, llama_sampler_init_greedy());
    } else {
        llama_sampler_chain_add(sampler, llama_sampler_init_temp(temp));
        llama_sampler_chain_add(sampler, llama_sampler_init_dist(LLAMA_DEFAULT_SEED));
    }

    // --- TokenSink callbacks ------------------------------------------------
    jclass sink_class = env->GetObjectClass(sink);
    jmethodID emit_method = nullptr;
    jmethodID stopped_method = nullptr;
    if (sink_class) {
        emit_method = env->GetMethodID(sink_class, "emit", "(Ljava/lang/String;)V");
        stopped_method = env->GetMethodID(sink_class, "stopped", "()Z");
    }
    if (!sink_class || !emit_method || !stopped_method) {
        env->ExceptionClear();
        if (sink_class) env->DeleteLocalRef(sink_class);
        llama_sampler_free(sampler);
        llama_batch_free(batch);
        return fail(engine, JARVIS_RC_BAD_ARG,
                    "TokenSink does not implement emit(String)/stopped()");
    }

    // --- generation loop ----------------------------------------------------
    const auto gen_start = std::chrono::steady_clock::now();
    long long generated = 0;
    bool jni_exception = false;
    bool decode_failed = false;
    int decode_rc = 0;
    Utf8Stream stream;

    for (int i = 0; i < max_tokens; ++i) {
        const jboolean stopped = env->CallBooleanMethod(sink, stopped_method);
        if (env->ExceptionCheck()) {
            jni_exception = true;
            break;
        }
        if (stopped == JNI_TRUE) break;

        const llama_token id = llama_sampler_sample(sampler, engine->ctx, -1);
        if (llama_vocab_is_eog(engine->vocab, id)) break;

        char piece_buffer[256];
        int32_t piece_length = llama_token_to_piece(engine->vocab, id, piece_buffer,
                                                    sizeof(piece_buffer), 0, true);
        std::string piece;
        if (piece_length < 0) {
            // Buffer too small: -piece_length is the required size.
            std::vector<char> big(static_cast<size_t>(-piece_length));
            piece_length = llama_token_to_piece(engine->vocab, id, big.data(),
                                                static_cast<int32_t>(big.size()), 0, true);
            if (piece_length > 0) {
                piece.assign(big.data(), static_cast<size_t>(piece_length));
            }
        } else if (piece_length > 0) {
            piece.assign(piece_buffer, static_cast<size_t>(piece_length));
        }

        if (!piece.empty()) {
            const std::string text = stream.feed(piece.data(), piece.size());
            if (!text.empty()) {
                jstring java_piece = newStringFromUtf8(env, text);
                if (!java_piece) {
                    jni_exception = true;
                    break;
                }
                env->CallVoidMethod(sink, emit_method, java_piece);
                env->DeleteLocalRef(java_piece);
                if (env->ExceptionCheck()) {
                    jni_exception = true;
                    break;
                }
            }
        }

        batch.n_tokens = 1;
        batch.token[0] = id;
        batch.pos[0] = static_cast<llama_pos>(engine->n_past);
        batch.n_seq_id[0] = 1;
        batch.seq_id[0][0] = 0;
        batch.logits[0] = 1;

        decode_rc = llama_decode(engine->ctx, batch);
        if (decode_rc != 0) {
            decode_failed = true;
            break;
        }
        engine->n_past++;
        engine->cached.push_back(id);
        generated++;
    }

    // Flush any incomplete UTF-8 tail, unless a Java exception is pending.
    if (!jni_exception) {
        const std::string tail = stream.flush();
        if (!tail.empty()) {
            jstring java_piece = newStringFromUtf8(env, tail);
            if (java_piece) {
                env->CallVoidMethod(sink, emit_method, java_piece);
                env->DeleteLocalRef(java_piece);
                if (env->ExceptionCheck()) jni_exception = true;
            } else {
                jni_exception = true;
            }
        }
    }

    const auto gen_end = std::chrono::steady_clock::now();
    engine->gen_tokens = generated;
    engine->gen_millis = static_cast<long long>(
        std::chrono::duration_cast<std::chrono::milliseconds>(gen_end - gen_start).count());

    env->DeleteLocalRef(sink_class);
    llama_sampler_free(sampler);
    llama_batch_free(batch);

    if (jni_exception) {
        // Leave the Java exception pending; the JVM turns this call into a throw.
        engine->last_error = "TokenSink callback threw an exception";
        return JARVIS_RC_INTERNAL;
    }
    if (decode_failed) {
        return fail(engine, JARVIS_RC_DECODE,
                    "generation stopped after a decode failure (llama_decode returned " +
                        std::to_string(decode_rc) + ")");
    }

    LOGI("generated %lld token(s) in %lld ms (prompt %zu tokens, %zu reused)",
         generated, engine->gen_millis, tokens.size(), reuse);
    return JARVIS_RC_OK;
    } catch (const std::exception& ex) {
        return fail(engine, JARVIS_RC_INTERNAL,
                    std::string("unhandled native exception while generating: ") + ex.what());
    } catch (...) {
        return fail(engine, JARVIS_RC_INTERNAL, "unhandled native exception while generating");
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_jarvis_client_localai_LlamaNative_nativeUnload(JNIEnv* /*env*/, jobject /*thiz*/,
                                                        jlong handle) {
    Engine* engine = engineFrom(handle);
    if (!engine) return;
    std::lock_guard<std::mutex> lock(engine->mu);
    freeModelLocked(engine);
    engine->prompt_tokens = 0;
    engine->gen_tokens = 0;
    engine->gen_millis = 0;
    LOGI("model unloaded");
}

extern "C" JNIEXPORT void JNICALL
Java_com_jarvis_client_localai_LlamaNative_nativeDestroy(JNIEnv* /*env*/, jobject /*thiz*/,
                                                         jlong handle) {
    Engine* engine = engineFrom(handle);
    if (!engine) return;
    {
        std::lock_guard<std::mutex> lock(engine->mu);
        freeModelLocked(engine);
    }
    delete engine;
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_jarvis_client_localai_LlamaNative_nativeLastError(JNIEnv* env, jobject /*thiz*/,
                                                           jlong handle) {
    Engine* engine = engineFrom(handle);
    if (!engine) return newStringFromUtf8(env, "invalid native handle (0)");
    std::lock_guard<std::mutex> lock(engine->mu);
    return newStringFromUtf8(env, engine->last_error);
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_jarvis_client_localai_LlamaNative_nativeVersion(JNIEnv* env, jobject /*thiz*/) {
    return newStringFromUtf8(env, buildVersionString());
}

extern "C" JNIEXPORT jlongArray JNICALL
Java_com_jarvis_client_localai_LlamaNative_nativeStats(JNIEnv* env, jobject /*thiz*/,
                                                       jlong handle) {
    jlong values[3] = {0, 0, 0};
    Engine* engine = engineFrom(handle);
    if (engine) {
        std::lock_guard<std::mutex> lock(engine->mu);
        values[0] = engine->prompt_tokens;
        values[1] = engine->gen_tokens;
        values[2] = engine->gen_millis;
    }
    jlongArray result = env->NewLongArray(3);
    if (!result) return nullptr;
    env->SetLongArrayRegion(result, 0, 3, values);
    return result;
}
