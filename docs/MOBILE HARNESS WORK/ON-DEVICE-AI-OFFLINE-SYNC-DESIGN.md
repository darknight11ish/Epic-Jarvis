# On-Device AI & Offline Two-Way Sync: Design (Slice 1)

**Status:** DESIGN ONLY - NOTHING IN THIS DOCUMENT IS BUILT  
**Target Module:** `jarvis-client` (Android companion) & `backend` (Desktop Python server)  
**Reference Architecture:** [`orailnoor/cross-platform-llm-client`](https://github.com/orailnoor/cross-platform-llm-client) (C++ `llama.cpp` ARM64 + Vulkan engine)  
**Location:** `docs/MOBILE HARNESS WORK/ON-DEVICE-AI-OFFLINE-SYNC-DESIGN.md`

> **What exists today: nothing.** This is a specification for future work, not a
> description of the shipped app. The Android app has no model runtime, no
> offline queue and no sync: it cannot answer while the PC is unreachable, and
> its Settings plate says so (`OnDeviceModelPlate.kt`). An earlier revision of
> this feature shipped a mock - a "native" load that always failed, a fixed
> sentence presented as the model's answer, invented model-transfer inventory
> and three screens with no call site. All of it was removed rather than
> shipped, and the tests that pinned those claims were removed with it. The
> rest of this document is the plan for building the real thing; read every
> present-tense sentence below as "will", not "does".

---

## 1. Overview & Objectives

This document specifies the complete design for **running local AI directly on the Android phone** and enabling **seamless two-way synchronization** with the main Jarvis installation running on the desktop PC.

### Two Modes of Operation
1. **Offline Companion Mode (Autonomous Fallback):**
   When the phone is away from home, out of signal, or the desktop PC is asleep/disconnected, the phone does not freeze into a disconnected state. Instead, it activates a local, compact on-device language model (GGUF format, such as *Llama 3.2 1B/3B* or *Qwen 2.5 1.5B*). The local model answers questions, captures thoughts, takes notes, schedules local reminders, and records new facts into an offline memory queue.
2. **Connected Mobile Lane (Collaborative Operation):**
   When the phone is connected over Tailscale or NordVPN Meshnet to the desktop PC, the phone's local model is recognized by the desktop Jarvis as an available edge worker. The phone can be selected as a lightweight compute lane, execute on-the-go tasks, or process mobile-specific context locally before streaming results back to the desktop.
3. **Automatic Two-Way Re-synchronization:**
   The instant the phone re-establishes a live link with the desktop PC (`LinkState.CONNECTED`), an idempotent background sync protocol uploads offline conversations, ingests offline memories into the desktop's long-term brain, updates tasks, and downloads new desktop state to the phone.

---

## 2. Compliance with the Five Rules

| Rule | How this design enforces it |
|---|---|
| **Rule 1: Private things stay local** | The on-device model runs 100% on the phone's CPU/GPU. No words, transcripts, or memories are transmitted to external cloud providers. Synced data travels only across the private mesh directly to the owner's desktop PC. |
| **Rule 2: No public tunnels** | Model transfers and sync payloads travel strictly over the existing private peer-to-peer network (Tailscale `*.ts.net` or NordVPN Meshnet `*.nord`) and loopback. No public relays or tunnels are used. |
| **Rule 3: Keys & credentials security** | Model files and offline databases reside strictly within Android private app storage (`context.filesDir` / encrypted app container). Sync requests authenticate using the established pairing token (`X-Jarvis-Token`). |
| **Rule 4: Never auto-approve risky actions** | Offline actions are restricted to safe, reversible local operations (answering, drafting notes, queuing facts). Risky actions (e.g. system commands, sending emails, external writes) cannot be executed offline and are queued for explicit desktop approval upon reconnection. |
| **Rule 5: Non-commercial & open standards** | Uses open GGUF model formats, open-source C++ `llama.cpp` runtime (MIT License), and standard Android Jetpack architecture. |

---

## 3. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       ANDROID PHONE (jarvis-client)                     │
│                                                                         │
│  ┌───────────────────────┐             ┌─────────────────────────────┐  │
│  │    Chat / Voice UI    │             │      MobileLlamaEngine      │  │
│  │  (HomeScreen/History) │◄───────────►│ (C++ libllama.so + Vulkan)  │  │
│  └───────────┬───────────┘             └──────────────┬──────────────┘  │
│              │                                        │                 │
│              ▼                                        ▼                 │
│  ┌───────────────────────┐             ┌─────────────────────────────┐  │
│  │     OfflineStore      │             │         ModelStore          │  │
│  │   (Local SQLite DB)   │             │   (Local .gguf model file)  │  │
│  │ - offline_chats       │             │   e.g. Qwen2.5-1.5B-Q4_K_M  │  │
│  │ - offline_memories    │             └─────────────────────────────┘  │
│  │ - pending_sync_queue  │                            ▲                 │
│  └───────────┬───────────┘                            │                 │
│              │                                        │                 │
│              ▼                                        │                 │
│  ┌───────────────────────┐                            │ (Mesh Transfer) │
│  │      SyncWorker       │                            │                 │
│  │ (Triggered on Connect)│◄───────────────────────────┼─────────────────┤
│  └───────────┬───────────┘                            │                 │
└──────────────┼────────────────────────────────────────┼─────────────────┘
               │                                        │
      Private Mesh (Tailscale/Meshnet)                  │
               │                                        │
┌──────────────┼────────────────────────────────────────┼─────────────────┐
│              ▼                                        ▼                 │
│  ┌───────────────────────┐             ┌─────────────────────────────┐  │
│  │      Sync Routes      │             │     Model Push Service      │  │
│  │ POST /api/sync/upload │             │  POST /api/models/transfer  │  │
│  │ GET  /api/sync/pull   │             │  (Pushes GGUF to Phone)     │  │
│  └───────────┬───────────┘             └─────────────────────────────┘  │
│              │                                                          │
│              ▼                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    MAIN DESKTOP JARVIS (PC)                       │  │
│  │  • chat.db (AES-256-GCM)       • memory.db (Long-term Facts)      │  │
│  │  • jarvis_agent.py             • jarvis_gate.py (Approvals)       │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Subsystem Specifications

### 4.1 On-Device LLM Runtime (`MobileLlamaEngine`) - planned, absent
Adapted from the core native layer in `orailnoor/cross-platform-llm-client`:
- **Native Binaries (not in this project):** Precompiled `libllama.so` and `libggml.so` for `arm64-v8a`, linked with Android NDK 26+. No `.so`, `jniLibs` folder or NDK build exists in `jarvis-client` today, so there is no engine to call.
- **Hardware Acceleration:**
  - **Vulkan Backend:** Detects GPU compute capability via Vulkan API. If compatible, offloads transformer layers to the phone's GPU (e.g. Pixel 9 Mali-G715).
  - **ARM NEON CPU Fallback:** If Vulkan is unavailable or system thermal throttling is active, falls back to multi-threaded ARM NEON execution (utilizing 4 high-efficiency/performance CPU cores).
- **RAM & Lifecycle Management:**
  - Cold load on first offline prompt: ~1.2s on Pixel 9.
  - Generates tokens via streaming callback: `(token: String) -> Unit`.
  - **Idle Unload Watchdog:** Unloads the model weight tensors from RAM after 5 minutes of inactivity or when the app is placed in the background, freeing memory and preserving battery.
  - Low battery threshold: If phone battery is below 15% without a charger, local inference asks for confirmation before running.

### 4.2 Loading Models on the Phone (`ModelStore`)
The user can provide or update the on-device model in two simple ways:

1. **Direct Transfer from Desktop Jarvis (Recommended):**
   - The desktop Jarvis backend provides a model transfer helper:
     `POST /api/models/transfer-to-phone`
   - The desktop verifies the SHA-256 of a recommended lightweight GGUF model (e.g. `qwen2.5-1.5b-instruct-q4_k_m.gguf` ~1.08 GB), slices it into signed chunks, and transfers it directly over the private mesh link into the phone app's model storage.
   - Eliminates third-party downloads on the phone and guarantees cryptographic integrity.
2. **Local File Picker on Phone:**
   - In phone **Settings -> Model -> Load On-Device Model**, the user can use the Android document picker to select an existing `.gguf` file stored in their Downloads or device storage.
   - The app verifies header magic (`GGUF`), architecture, and quantization compatibility before registering it.

### 4.3 Offline Storage Schema (`OfflineStore.kt`) - planned, absent
Planned to be stored in private SQLite on the phone (`offline_jarvis.db`). No
offline store ships today: an earlier revision used plaintext SharedPreferences
and has been removed.

```sql
-- Offline conversation turns
CREATE TABLE offline_turns (
    turn_id TEXT PRIMARY KEY,           -- UUIDv4
    conversation_id TEXT NOT NULL,
    timestamp INTEGER NOT NULL,         -- Epoch milliseconds
    user_query TEXT NOT NULL,
    model_response TEXT NOT NULL,
    model_name TEXT NOT NULL,           -- e.g. "ondevice:qwen2.5-1.5b"
    sync_status TEXT NOT NULL DEFAULT 'PENDING' -- PENDING, SYNCED, FAILED
);

-- Facts and memories captured offline
CREATE TABLE offline_memories (
    memory_id TEXT PRIMARY KEY,         -- UUIDv4
    timestamp INTEGER NOT NULL,
    fact_text TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    sensitive INTEGER NOT NULL DEFAULT 0,
    sync_status TEXT NOT NULL DEFAULT 'PENDING'
);

-- Notes and tasks drafted offline
CREATE TABLE offline_tasks (
    task_id TEXT PRIMARY KEY,
    timestamp INTEGER NOT NULL,
    action_type TEXT NOT NULL,          -- "note", "reminder", "todo"
    payload_json TEXT NOT NULL,
    sync_status TEXT NOT NULL DEFAULT 'PENDING'
);
```

---

## 5. Synchronization Protocol (Reconnection Phase)

When `JarvisRuntime.linkState` switches from `OFFLINE` or `RECONNECTING` to `CONNECTED`, the background `SyncWorker` executes:

### Step 1: Upstream Sync (`POST /api/sync/offline-batch`)
The phone packages all records with `sync_status = 'PENDING'` into a single JSON payload:

```json
{
  "device_id": "pixel9_owner",
  "client_version": "0.2.1300",
  "sync_timestamp": 1731375000000,
  "turns": [
    {
      "turn_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "conversation_id": "daily_chat",
      "timestamp": 1731374500000,
      "user_query": "What are the three main ingredients of pesto?",
      "model_response": "Pesto traditionally consists of fresh basil, pine nuts, and garlic...",
      "model_name": "ondevice:qwen2.5-1.5b"
    }
  ],
  "memories": [
    {
      "memory_id": "5c2e1a3b-4f5a-6b7c-8d9e-0f1a2b3c4d5e",
      "timestamp": 1731374600000,
      "fact_text": "Dentist appointment is scheduled for Thursday at 3 PM",
      "category": "health",
      "sensitive": true
    }
  ],
  "tasks": []
}
```

### Step 2: Desktop Ingestion & Safety Gates
1. **Turns Ingestion:**
   The desktop receives the turns and appends them to the encrypted chat history (`chat.db`), explicitly marking the turn metadata with `"surface": "phone-offline", "model": "ondevice:qwen2.5-1.5b"`.
2. **Memories Ingestion:**
   - Non-sensitive memories are ingested directly into `memory.db` following standard auto-learn rules.
   - Sensitive memories (e.g. health, finances) raise a standard **Approval Card** on the desktop:
     *"Jarvis learned this while your phone was offline: 'Dentist appointment is scheduled for Thursday at 3 PM'. Keep this memory?"*
   - Adheres strictly to **Rule 4** (no silent auto-approval of sensitive facts).
3. **Task & Notes Reconciliation:**
   Offline notes and reminders are inserted into desktop notes/schedules.

### Step 3: Desktop Acknowledgement & Downstream Sync
The desktop responds with:
```json
{
  "ok": true,
  "accepted_turns": ["9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"],
  "accepted_memories": ["5c2e1a3b-4f5a-6b7c-8d9e-0f1a2b3c4d5e"],
  "accepted_tasks": [],
  "server_sync_time": 1731375010000,
  "latest_desktop_updates": {
    "memory_count": 142,
    "active_reminders_count": 3
  }
}
```
Upon receiving `"ok": true`, the phone marks the uploaded rows as `sync_status = 'SYNCED'`.

---

## 6. Connected Mobile Lane (Desktop Collaboration)

When the phone is connected to the desktop:
- The desktop `/api/lanes` endpoint can list the connected phone as a designated edge capability:
  `lane: "mobile-edge-lane"` (`device: "pixel9"`).
- **Offloading:** The owner can choose in desktop settings or chat to route small formatting tasks or phone-specific device queries (e.g. battery check, local notification summary) directly to the phone's on-device model.
- **Latency & Redundancy:** Provides instant local text completion without consuming desktop RTX 2080 GPU memory when heavy desktop workloads are executing.

---

## 7. Implementation Roadmap

1. **Slice 1 (This Document):** Complete architectural and API specification.
2. **Slice 2 (Offline Database & Sync Routes):**
   - Implement `OfflineStore.kt` in `jarvis-client`.
   - Implement `/api/sync/offline-batch` route and test suite in `backend/`.
   - Test offline queuing and reconnection sync with contract tests.
3. **Slice 3 (On-Device Inference Integration):**
   - Integrate `libllama.so` (ARM64-v8a + Vulkan) and JNI bindings into `jarvis-client/app/src/main/jniLibs`.
   - Implement `MobileLlamaEngine.kt` to run GGUF models.
   - Add model management settings plate on the phone and desktop transfer route.
4. **Slice 4 (Verification & Field Testing):**
   - Offline prompt generation tests.
   - Airplane mode toggle disconnect/reconnect sync verification.
