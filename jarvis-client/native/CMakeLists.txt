# libjarvis_llama.so - CPU-only single-library build of llama.cpp for Jarvis Android.
#
# Derived from the MIT-licensed Android plugin in
#   orailnoor/cross-platform-llm-client  (MIT (c) 2025 dragneel2074)
#   local_plugins/llama_flutter_android/android/CMakeLists.txt
# adapted for the Epic-Jarvis JNI contract (com.jarvis.client.localai.LlamaNative).
# llama.cpp itself is MIT (c) the ggml authors. See licenses/ in this folder.
#
# Deliberate differences from the PrivateLM CMakeLists:
#   * one shared library: llama + ggml are built STATIC and linked into
#     libjarvis_llama.so, instead of shipping libllama.so/libggml*.so modules;
#   * GGML_BACKEND_DL=OFF: the CPU backend is compiled in and registered
#     statically, so there is no libggml-cpu-*.so to dlopen;
#   * Vulkan OFF, RPC (phone cluster) OFF, mtmd/vision not built;
#   * LLAMA_BUILD_COMMON/TOOLS/TESTS/EXAMPLES/SERVER/APP all OFF - the JNI
#     wrapper is the only consumer of llama.h;
#   * OpenMP OFF (the NDK ships no libomp, and packaging it is not wanted);
#   * 16 KB page-size link flags for Android 15+ devices.
#
# This file intentionally does not change any vendored llama.cpp source.

cmake_minimum_required(VERSION 3.22)

project(jarvis_llama LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Note: C standard and GNU extensions are left at the NDK/llama.cpp defaults -
# llama.cpp is built by the same subtree and may rely on gnu++17.

# Static archives must be position independent to go into a .so. The NDK
# already defaults to PIC for Android, but state it so a host build behaves.
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Android 15+ ships 16 KB page devices; this must be on LINK options of the
# final .so. Verified with llvm-readelf (LOAD align 0x4000).
add_link_options(-Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384)

# ---------------------------------------------------------------------------
# llama.cpp build configuration: one CPU-only shared library.
# Every option below is set BEFORE add_subdirectory so llama.cpp's option()
# calls see the cache value and do not re-default it.
# ---------------------------------------------------------------------------
set(BUILD_SHARED_LIBS OFF CACHE BOOL "build llama/ggml as static archives linked into one .so" FORCE)

# GGML_STATIC adds a bare -static to the linker, which cannot work on Android.
# It is NOT what makes the archives static; BUILD_SHARED_LIBS=OFF does that.
set(GGML_STATIC OFF CACHE BOOL "never pass -static to the Android linker" FORCE)

# CPU only, no runtime backend loading, no GPU, no cluster.
set(GGML_BACKEND_DL OFF CACHE BOOL "CPU backend compiled in, no dlopen modules" FORCE)
set(GGML_CPU_ALL_VARIANTS OFF CACHE BOOL "no per-Arm-generation backend modules" FORCE)
set(GGML_VULKAN OFF CACHE BOOL "no Vulkan backend (E3 feature)" FORCE)
set(GGML_RPC OFF CACHE BOOL "no phone-cluster RPC backend" FORCE)
set(GGML_OPENMP OFF CACHE BOOL "NDK has no libomp to package" FORCE)
set(GGML_NATIVE OFF CACHE BOOL "cross-compiling: never tune for the build host" FORCE)
set(GGML_CPU ON CACHE BOOL "CPU backend" FORCE)
set(GGML_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(GGML_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)

# Llamafile's sgemm stays ON: it is the same default the PrivateLM arm64 build
# used, and ggml guards the FP16 NEON path behind __ARM_FEATURE_FP16_*.

# llama.cpp: library only. Nothing here needs common/, tools/, server or app.
set(LLAMA_BUILD_COMMON OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_SERVER OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_APP OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_MTMD OFF CACHE BOOL "no vision/multimodal for E1" FORCE)
set(LLAMA_CURL OFF CACHE BOOL "" FORCE)
set(LLAMA_OPENSSL OFF CACHE BOOL "" FORCE)
set(LLAMA_SUBPROCESS OFF CACHE BOOL "" FORCE)

add_subdirectory(vendor/llama.cpp)

# ---------------------------------------------------------------------------
# The JNI wrapper - the only target this project adds.
# ---------------------------------------------------------------------------
add_library(jarvis_llama SHARED jni/jarvis_llama_jni.cpp)

target_compile_features(jarvis_llama PRIVATE cxx_std_17)
target_compile_options(jarvis_llama PRIVATE -O3 -fvisibility=hidden)
target_link_options(jarvis_llama PRIVATE
    -Wl,--exclude-libs,ALL          # do not export llama/ggml/libc++ symbols
    -Wl,-z,max-page-size=16384
    -Wl,-z,common-page-size=16384
)

target_include_directories(jarvis_llama PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/vendor/llama.cpp/include
    ${CMAKE_CURRENT_SOURCE_DIR}/vendor/llama.cpp/ggml/include
)

# llama PUBLIC-links ggml; naming ggml as well keeps the intent explicit.
target_link_libraries(jarvis_llama PRIVATE llama ggml android log)

set_target_properties(jarvis_llama PROPERTIES
    OUTPUT_NAME jarvis_llama
    LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN ON
)

message(STATUS "jarvis_llama: JNI wrapper -> ${CMAKE_BINARY_DIR}/lib/libjarvis_llama.so")
