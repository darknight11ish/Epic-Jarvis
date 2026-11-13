# libjarvis_llama.so — native build report (Android E1)

Lane: `engine-native` · date 2026-11-13 (off-peak MAX OUT) · write scope
`D:\jarvis-scratch\android-engine-native-2026-11-13\` (nothing in the repo or the
engine worktree was written).

Goal: one CPU-only shared library implementing the exact JNI contract in
`ANDROID-LOCAL-ENGINE-2026-11-13\PLAN.md`, reproducibly, MIT-only, and proven
(both statically and by generating text on the owner's real phone).

## 1. TL;DR

| item | value |
|---|---|
| output (phone) | `dist\arm64-v8a\libjarvis_llama.so` |
| size | **4,381,104 bytes** (4.18 MiB; 47,146,048 unstripped) |
| sha256 | **`3de1334045f8f4deb716d2c828faaa4a84fcfa0dc8fa2468c544cf3156e882da`** |
| output (emulator) | `dist\x86_64\libjarvis_llama.so` |
| size | **4,791,688 bytes** (46,068,368 unstripped) |
| sha256 | **`dd4b5c35cd19c2838d8a5ed21c8e5cba4bf19cf39a16daf31daa92e83d205511`** |
| JNI symbols | **8/8 present** in both ABIs (`nm -D`) |
| 16 KB pages | **all 4 LOAD segments aligned `0x4000`** in both ABIs (`llvm-readelf -l`) |
| self-contained | yes — links `c++_static`, **no `libc++_shared.so` dependency** |
| reproducible | a `-Clean` rebuild produced a **bit-identical** arm64 sha256 |
| on-device proof | **PASS** on CPH2419, Android 15: real GGUF load + generation at **19.92 tokens/s** |
| external deps at build time | none beyond the vendored source + the standalone toolchain |

## 2. Deliverables in this folder

| path | what |
|---|---|
| `dist\arm64-v8a\libjarvis_llama.so` | the phone library (stripped Release) |
| `dist\arm64-v8a\BUILD-INFO.txt` | size, sha256, symbols, LOAD segments, toolchain versions |
| `dist\x86_64\libjarvis_llama.so` | optional emulator library (same contract) |
| `dist\x86_64\BUILD-INFO.txt` | same evidence for x86_64 |
| `build-native.ps1` | reproduces both builds from this folder + the toolchain |
| `PROVENANCE.json` | machine-readable source/toolchain/artifact/verification record |
| `licenses\LICENSE-llama.cpp` | llama.cpp MIT (© 2023-2026 The ggml authors) |
| `licenses\LICENSE-PrivateLM-plugin` | plugin MIT (© 2025 dragneel2074) |
| `licenses\LICENSE-PrivateLM-repo` | PrivateLM repository MIT |
| `licenses\llama.cpp-tree.sha256` | per-file manifest behind the tree hash |
| `jni\jarvis_llama_jni.cpp` | adapted JNI bridge |
| `CMakeLists.txt` | single-library CPU-only build definition |
| `vendor\llama.cpp\` | vendored llama.cpp 0.5.0-dev (1,738 files, 32.5 MB) |
| `probe\src\` + `run-probe.ps1` | Java/app_process probe used for the on-device proof |
| `build-arm64*.log`, `build-x86_64*.log` | full build logs |
| `probe\probe-*.log` | full on-device probe logs |

## 3. What was built and from what

* **llama.cpp 0.5.0-dev** (ggml 0.25.1), MIT, copied from PrivateLM’s vendored
  plugin at `local_plugins\llama_flutter_android\android\src\main\cpp\llama.cpp`.
  Copied without `.git`, `examples`, `tests`, `tools`, `docs`, `python`,
  `scripts`, or any compiled binary. PrivateLM commit
  `8a5f3b0c0ca8c2108b76ac9619fe5faf6a6a098e`. The vendored snapshot does not
  record its upstream llama.cpp commit, so provenance is **PrivateLM commit +
  tree hash**, exactly as the PLAN anticipated.
* **Tree hash** of the copied sources:
  `9ecc1ed57a9e235f4e7a5c94840ab32a6ec7b7badb2bed390d34ab2dd8d40b51`
  over 1,738 files, method and per-file manifest in `PROVENANCE.json` /
  `licenses\llama.cpp-tree.sha256`.
* **Adapted wrapper**: PrivateLM’s `jni_wrapper.cpp` (MIT © 2025
  dragneel2074) → `jni\jarvis_llama_jni.cpp`. Kept its proven llama.cpp call
  sequence (GGUF pre-flight, batched prompt decode, KV-cache prefix reuse,
  UTF-8-safe streaming, log capture). Replaced its Flutter-entry/global-state
  shape with exactly the eight contract functions and one engine per `handle`.
  Attribution header is in both adapted files.

### The JNI contract that is exported

```
Java_com_jarvis_client_localai_LlamaNative_nativeCreate
Java_com_jarvis_client_localai_LlamaNative_nativeLoad
Java_com_jarvis_client_localai_LlamaNative_nativeGenerate
Java_com_jarvis_client_localai_LlamaNative_nativeUnload
Java_com_jarvis_client_localai_LlamaNative_nativeDestroy
Java_com_jarvis_client_localai_LlamaNative_nativeLastError
Java_com_jarvis_client_localai_LlamaNative_nativeVersion
Java_com_jarvis_client_localai_LlamaNative_nativeStats
```

Return codes: `0` success, negative failure (`-1` bad handle, `-2` bad argument,
`-3` no model loaded, `-4` model load, `-5` tokenise, `-6` decode, `-7` internal).
`nativeLastError(handle)` carries the readable reason; `nativeStats` returns
`[promptTokens, genTokens, genMillis]`.

## 4. Toolchain and exact build recipe

From `D:\Android\tools\TOOLCHAIN-READY.txt` (ended with `DONE=1`):

| tool | path | version |
|---|---|---|
| NDK | `D:\Android\ndk\android-ndk-r27c` | 27.2.12479018 (clang 18.0.3) |
| CMake | `D:\Android\cmake\bin\cmake.exe` | 3.31.6 |
| Ninja | `D:\Android\ninja\ninja.exe` | 1.12.1 |

```
pwsh -NoProfile -File .\build-native.ps1              # arm64-v8a
pwsh -NoProfile -File .\build-native.ps1 -Abi x86_64  # optional emulator ABI
```

The script reads the marker for `NDK_DIR` / `CMAKE_EXE` / `NINJA_EXE`
(overridable with `-NdkDir` / `-CMakeExe` / `-NinjaExe`), configures with the
NDK toolchain and Ninja, builds target `jarvis_llama`, strips the published copy,
and writes `BUILD-INFO.txt` with fresh evidence. **No network, no git, no
FetchContent** is involved: the fetch-using options (Vulkan headers, etc.) are
switched off.

Effective configure line:

```
cmake -S <root> -B build\<abi> -G Ninja
      -DCMAKE_TOOLCHAIN_FILE=<ndk>\build\cmake\android.toolchain.cmake
      -DANDROID_ABI=<abi> -DANDROID_PLATFORM=android-33
      -DANDROID_STL=c++_static -DCMAKE_BUILD_TYPE=Release
      -DCMAKE_MAKE_PROGRAM=<ninja>
```

## 5. What was disabled, and why (single CPU library)

| option | value | reason |
|---|---|---|
| `BUILD_SHARED_LIBS` | OFF | llama/ggml build as **static archives linked into the one `.so`** |
| `GGML_STATIC` | OFF | that option adds a bare `-static` to the link, which cannot work on Android; it is *not* what makes archives static |
| `GGML_BACKEND_DL` | OFF | CPU backend compiled in and registered statically — no `libggml-cpu-*.so` to `dlopen` |
| `GGML_CPU_ALL_VARIANTS` | OFF | would require backend-DL modules, i.e. more than one library |
| `GGML_VULKAN` | OFF | E3 feature |
| `GGML_RPC` | OFF | phone-cluster feature, not in E1 |
| `GGML_OPENMP` | OFF | the NDK ships no `libomp`, and packaging one is not wanted |
| `GGML_NATIVE` | OFF | cross-compiling; never tune for the build host |
| `LLAMA_BUILD_COMMON/TOOLS/TESTS/EXAMPLES/SERVER/APP` | OFF | the JNI wrapper is the only consumer of `llama.h` |
| `LLAMA_BUILD_MTMD` | OFF | no vision/multimodal in E1 |
| `LLAMA_CURL/OPENSSL/SUBPROCESS` | OFF | not used by the library |

Link flags: `-Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384`
(16 KB pages) and `-Wl,--exclude-libs,ALL` (static-library symbols are not
exported). C++17. `c++_static` so the app needs **no extra STL `.so`**.

> **Performance note, stated honestly.** This is a *baseline* arm64-v8a build:
> ggml’s runtime/compile-time feature checks did not enable dotprod, fp16
> vector arithmetic, i8mm or SVE (that needs `-march` tuning or PrivateLM’s
> per-CPU-variant backend modules). It is maximally portable and was measured at
> ~19.7 tok/s on a 0.5B Q4_K_M. Faster per-CPU variants are an E3 follow-up.

## 6. Evidence

### 6.1 Static (both ABIs)

`llvm-nm -D --defined-only` → the 8 `Java_…` symbols above, and only those JNI
symbols. `llvm-readelf -l` for arm64:

```
LOAD 0x000000 0x…000000 0x…000000 0x105a34 0x105a34 R   0x4000
LOAD 0x105a40 0x…109a40 0x…109a40 0x311030 0x311030 R E 0x4000
LOAD 0x416a70 0x…41ea70 0x…41ea70 0x015cc8 0x019590 RW  0x4000
LOAD 0x42c738 0x…438738 0x…438738 0x000938 0x0841b8 RW  0x4000
```

`llvm-readelf -d`: `NEEDED libandroid.so, liblog.so, libm.so, libdl.so,
libc.so`; **no `libc++_shared.so`**, no `TEXTREL`, `BIND_NOW` set.

Reproducibility: `build-native.ps1 -Clean` rebuilt arm64 and produced the same
sha256 `3de13340…e882da` — bit-identical, not merely “it built again”.

### 6.2 On the real phone (not just symbols)

Because the owner’s phone was attached (`f0a5b32b`, CPH2419, Android 15,
arm64-v8a), the library was exercised end-to-end **without an APK or root**:
a Java probe with the same binary names/signatures as the Kotlin contract
(`com.jarvis.client.localai.LlamaNative`, `TokenSink`) was dexed with `d8` and
run through `app_process`; the library was loaded with
`System.load("/data/local/tmp/jarvis-probe/libjarvis_llama.so")`. The probe
declares the natives as **instance methods**, which is the shape Kotlin’s
`object LlamaNative` compiles to (the JNI second argument is a `jobject`, not a
`jclass`), so the calling convention is the one the app will use.

Model: `qwen2.5-0.5b-instruct-q4_k_m.gguf`, 491,400,032 bytes, sha256
`74a4da8c…a9db` (a local test asset, not shipped).

Result: **RESULT PASS (15/15 checks, device exit code 0)**, log
`probe\probe-20261113-042920.log`:

```
PASS System.load
PASS nativeVersion - llama.cpp 0.5.0-dev / jarvis_llama 1 / arm64-v8a / CPU
PASS nativeCreate - handle=…
PASS nativeLoad(missing file) fails - rc=-4 error=GGUF file is missing or unreadable: …
PASS nativeLastError is readable
PASS nativeLoad - 270 ms, ctx=2048, threads=4
PASS nativeGenerate - rc=0 error=
OUTPUT>>> Paris. It is the largest city in Europe and the second largest in the world. It is also the capital of the<<<
PASS generated text - chars=107
PASS nativeStats length - [5, 24, 1205]
PASS stats counted tokens - prompt=5 gen=24 ms=1205
TOKENS_PER_SEC>>>19.92
PASS nativeGenerate(again) reuses cache - rc=0 chars=76
PASS unicode prompt + reply - rc=0 chars=37 nonAscii=true cjk=true
ZH_CODEPOINTS>>>U+5DF4 U+9ECE U+3002 U+5DF4 U+9ECE U+662F U+6CD5 U+56FD
OUTPUT_ZH>>>巴黎。巴黎是法国的首都，位于法国南部，是法国的首都，位于法国南部，是法国的<<<
PASS stopped() cancels cleanly - rc=0 emits=0
PASS unload resets stats - [0, 0, 0]
PASS nativeDestroy
RESULT PASS
```

This proves, on the actual phone: load, tokenisation, greedy generation, stats,
KV-cache prefix reuse on a second call, correct UTF-8 ↔ UTF-16 (CJK code
points, not mojibake), `stopped()` cancellation, unload/destroy, and a readable
error path. Measured: **19.92 tokens/s** (0.5B Q4_K_M, ctx 2048, 4 threads;
repeat runs 19.7–20.0 tok/s).

> One probe-harness bug was found and fixed during this work, and is recorded so
> nobody misreads the earlier log: the Chinese prompt literal was compiled with
> javac’s Windows default charset, turning its UTF-8 bytes into Latin-1
> characters; the Unicode check failed once for that reason. Adding
> `-encoding UTF-8` (now in `run-probe.ps1`) made the *same library* pass. The
> bug was in the test harness, not in `libjarvis_llama.so`.

## 7. Size, and why the published file is stripped

The Release build initially produced 47,146,048 bytes, of which 42,764,331 bytes
(40.8 MB) were `.debug_*` sections and symbol tables — measured: `.debug_info`
13.78 MB, `.debug_loc` 11.06 MB, `.debug_str` 10.42 MB, `.debug_ranges`
3.51 MB, `.debug_line` 2.60 MB, `.symtab` 0.52 MB, `.strtab` 0.72 MB.
`llvm-strip --strip-unneeded` leaves all 8 JNI dynamic symbols and the unwind
tables intact and yields **4,381,104 bytes** — a 10.8× reduction that matters
for the APK. `build-native.ps1` now strips by default; the unstripped library is
still available at `build\arm64-v8a\lib\libjarvis_llama.so`, and
`-KeepDebugSymbols` publishes an unstripped copy.

## 8. Integration notes for the Lead (from what was measured)

1. Copy `dist\arm64-v8a\libjarvis_llama.so` →
   `jarvis-client\app\src\main\jniLibs\arm64-v8a\libjarvis_llama.so`.
   Optionally add `dist\x86_64\libjarvis_llama.so` under `jniLibs\x86_64\`:
   the app’s `build.gradle.kts` already has
   `abiFilters += listOf("arm64-v8a", "x86_64")` and `minSdk = 33`, which
   matches this library’s `android-33` build.
2. **No `libc++_shared.so` needs packaging.** The library is self-contained
   (`c++_static`, `--exclude-libs,ALL`); its only `NEEDED` entries are public
   system libraries (`libandroid`, `liblog`, `libm`, `libdl`, `libc`).
3. **R8 keep rules are required** — JNI looks classes and methods up by name:
   ```proguard
   -keep class com.jarvis.client.localai.LlamaNative { *; }
   -keep interface com.jarvis.client.localai.TokenSink { *; }
   -keepclasseswithmembers class * implements com.jarvis.client.localai.TokenSink {
       public void emit(java.lang.String);
       public boolean stopped();
   }
   ```
   Without them, `GetMethodID` returns null and generation fails with
   `TokenSink does not implement emit(String)/stopped()` rather than crashing —
   but it does fail.
4. `System.loadLibrary("jarvis_llama")` must stay lazy (inside
   `LlamaEngine.create()`), as the PLAN says; the library is arm64/x86_64 only,
   so JVM unit tests must not touch it.
5. 16 KB page checks (`tools/check_apk_16kb.py`) should pass: all LOAD segments
   are 0x4000-aligned. Note `jniLibs { useLegacyPackaging = true }` is set in
   the app; the extracted library keeps its alignment.
6. Contract details worth mirroring in Kotlin: `nativeStats` returns exactly 3
   longs; `temperature <= 0` selects greedy; `stopped()` is polled once per
   token and cancelling returns `0` (not an error); a failed call returns
   negative and the reason is in `nativeLastError(handle)`; `nativeLastError`
   never returns null.

## 9. What is not verified (honest gaps)

* **The app-level integration is not tested.** The probe mirrors the Kotlin
  object’s instance-method shape and passed, but the real Kotlin `LlamaNative`
  class, `LocalEnginePolicy` (idle unload / 180 s hard cap), UI, R8 build and APK
  packaging are the integration lane’s work.
* **x86_64 was built and statically checked but not executed** (no emulator was
  started). If emulator smoke matters before merge, run
  `build-native.ps1 -Abi x86_64` output through the same probe on an emulator.
* Only the owner’s CPH2419 / Android 15 was exercised; other devices are
  unverified.
* CPU performance is baseline only (see §5); no per-CPU-variant tuning.
* No GPU/Vulkan, no RPC cluster, no vision — by design for E1.

## 10. Licence / attribution block (ready for THIRD-PARTY-NOTICES.txt)

```
llama.cpp (ggml) — MIT
Copyright (c) 2023-2026 The ggml authors
Version built: 0.5.0-dev (ggml 0.25.1)
Vendored from cross-platform-llm-client commit
8a5f3b0c0ca8c2108b76ac9619fe5faf6a6a098e (local_plugins/llama_flutter_android)
Source tree hash: 9ecc1ed57a9e235f4e7a5c94840ab32a6ec7b7badb2bed390d34ab2dd8d40b51
Full licence: licenses/LICENSE-llama.cpp

llama_flutter_android JNI wrapper / Android CMake — MIT
Copyright (c) 2025 dragneel2074
Adapted into jni/jarvis_llama_jni.cpp and CMakeLists.txt
Full licence: licenses/LICENSE-PrivateLM-plugin
```
