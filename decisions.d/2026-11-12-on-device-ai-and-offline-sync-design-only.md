- **2026-11-12 — On-device AI and offline sync stay a design, not a shipped mock:** The work
  for this pull request is reduced to a specification (`docs/MOBILE HARNESS WORK/ON-DEVICE-AI-OFFLINE-SYNC-DESIGN.md`)
  and an honest Settings plate. Nothing runs a model on the phone, no offline store
  or sync route ships, and the phone cannot answer while the PC is unreachable; the
  plate says that in those words. The removed layer was not salvageable as it stood:
  `MobileLlamaEngine` called a `libllama_android.so` that does not exist and then
  streamed a fixed 28-word sentence labelled as the model's answer; `OfflineStore`
  was plaintext SharedPreferences described as an encrypted SQLite database; the
  sync module called `jarvis_chat_log.get_log`, `jarvis_memory.get_store` and
  `jarvis_gate.record_pending`, none of which exist, swallowed every failure and
  reported success; the transfer route returned two hard-coded model records as the
  PC's inventory; and `ProjectExplorerPlate`, `WebPreviewPlate`, `MobileAgentDispatcher`
  and `KeystoreVault` had no call site at all. Those claims are gone with them, and
  the tests that pinned the false sentences went too. Building the real feature is
  an owner decision (a native llama.cpp dependency, and a card design for sensitive
  memories arriving offline); until then the design document is the whole of it.
