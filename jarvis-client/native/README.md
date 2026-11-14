# `jarvis-client/native` — the on-device GGUF engine's native half (E1)

This folder holds the source that produces the shipped native library
`app/src/main/jniLibs/<abi>/libjarvis_llama.so`, plus its provenance and the MIT licence files.
The engine runs **on the phone only**; it is not a backend route and it never touches the network.

## What it is

- `CMakeLists.txt` — one shared library (`libjarvis_llama.so`) built from llama.cpp (MIT) with the
  JNI wrapper. CPU only: no Vulkan, no phone-cluster RPC, no dynamic backend modules, no multimodal.
  Linker flags set 16 KB page alignment (`LOAD` align `0x4000`), which `tools/check_apk_16kb.py`
  enforces on the release APK.
- `jni/jarvis_llama_jni.cpp` — the JNI bridge for `com.jarvis.client.localai.LlamaNative`, adapted
  from the MIT-licensed Android plugin in `orailnoor/cross-platform-llm-client` (MIT © 2025
  dragneel2074) and re-shaped to this repository's contract.
- `build-native.ps1` — builds and strips the `.so` from a vendored llama.cpp tree plus a standalone
  Android NDK/CMake/Ninja toolchain.
- `PROVENANCE.json` — the exact toolchain, source commit, tree hash, output sha256 and the measured
  on-device probe result.
- `licenses/` — llama.cpp MIT, PrivateLM plugin MIT, and a per-file sha256 tree listing of the
  vendored llama.cpp source.

## Rebuilding (only needed to change the native code; not needed to build the app)

The vendored llama.cpp source is deliberately **not** committed (33.6 MB). Fetch it at the pinned
commit, then build:

```powershell
# 1. get the vendored source the pinned PrivateLM commit carries
git clone https://github.com/orailnoor/cross-platform-llm-client D:\jarvis-scratch\repos\cross-platform-llm-client
git -C D:\jarvis-scratch\repos\cross-platform-llm-client checkout 8a5f3b0c0ca8c2108b76ac9619fe5faf6a6a098e
Copy-Item "D:\jarvis-scratch\repos\cross-platform-llm-client\local_plugins\llama_flutter_android\android\src\main\cpp\llama.cpp" ".\vendor\llama.cpp" -Recurse

# 2. get a standalone Android toolchain (about 1 GB, kept off the system drive)
#    NDK r27c:  https://dl.google.com/android/repository/android-ndk-r27c-windows.zip
#    CMake:     https://github.com/Kitware/CMake/releases (portable zip, 3.22+)
#    Ninja:     https://github.com/ninja-build/ninja/releases (ninja-win.zip)
#    Write D:\Android\tools\TOOLCHAIN-READY.txt with NDK_DIR, CMAKE_EXE, NINJA_EXE and DONE=1.

# 3. build both ABIs (the script strips the output)
.\build-native.ps1 -Abi arm64-v8a
.\build-native.ps1 -Abi x86_64

# 4. publish the stripped libraries and verify them
Copy-Item .\dist\arm64-v8a\libjarvis_llama.so ..\app\src\main\jniLibs\arm64-v8a\ -Force
Copy-Item .\dist\x86_64\libjarvis_llama.so      ..\app\src\main\jniLibs\x86_64\  -Force
llvm-readelf -l ..\app\src\main\jniLibs\arm64-v8a\libjarvis_llama.so   # every LOAD must say 0x4000
llvm-nm -D ..\app\src\main\jniLibs\arm64-v8a\libjarvis_llama.so        # 8 Java_com_jarvis_client_localai_* symbols
```

Record the new sha256 in `PROVENANCE.json` when the binary changes. The `jniLibs` binaries ARE
committed because CI has no NDK and must not build native code: the app job only packages them.

## Honest scope (2026-11-13)

Built and proven: CPU inference on the real phone (CPH2419) through a standalone JVM probe —
`nativeLoad` 262 ms, 24 generated tokens in 1.2 s (≈19–20 tok/s) with Qwen2.5-0.5B-Instruct Q4_K_M,
cancellation, unload and destroy all PASS. The in-app Local AI screen is the next proof; it is
BLOCKED until driven on a real phone, never assumed. Vulkan GPU offload, in-app download and vision
are later waves (E2/E3).
