#!/bin/bash
# Compile-checks the phone's pure (non-Android) Kotlin in the voice-phone worktree and runs JVM tests.
# Copied from ../phonep/build-main.sh and pointed at this agent's worktree.
# Usage: build-main.sh "<source files>" "<test classes>"
set -u
K=/tmp/claude-0/-home-user-Epic-Jarvis/786d7fdd-6b1c-5483-a32b-fd87a501a213/scratchpad/kt
F=/tmp/claude-0/-home-user-Epic-Jarvis/786d7fdd-6b1c-5483-a32b-fd87a501a213/scratchpad/mainphone
W=/home/user/Epic-Jarvis/jarvis-client/app/src
M=$W/main/java/com/jarvis/client
cd "$F"
mkdir -p stub
sed -n '/^sealed interface ApiError/,/^inline fun <T, R> ApiResult<T>.map/p' "$M/net/JarvisApi.kt" > stub/body.txt
{
  echo "package com.jarvis.client.net"
  echo
  cat stub/body.txt
  echo "    is ApiResult.Ok -> ApiResult.Ok(block(value))"
  echo "    is ApiResult.Failed -> this"
  echo "}"
  echo 'class JarvisApi { companion object { const val TOKEN_HEADER = "X-Jarvis-Token"; const val SOURCE_WAKE_WORD = "wake_word"; const val SOURCE_PUSH_TO_TALK = "push_to_talk"; const val MIC_PHONE = "phone"'
  echo '  fun quote(s: String): String = JarvisJson.encodeToString(kotlinx.serialization.serializer<String>(), s) } }'
} > stub/ApiStub.kt
CP=$K/kotlinx-serialization-json-jvm-1.7.3.jar:$K/kotlinx-serialization-core-jvm-1.7.3.jar:$K/junit-4.13.2.jar:$K/hamcrest-core-1.3.jar:/tmp/claude-0/-home-user-Epic-Jarvis/786d7fdd-6b1c-5483-a32b-fd87a501a213/scratchpad/phonelock/kotlinx-coroutines-core-jvm-1.9.0.jar
rm -rf out && mkdir out
cd "$W/.."
"$K/kotlinc/bin/kotlinc" -Xplugin="$K/kotlinc/lib/kotlinx-serialization-compiler-plugin.jar" -cp "$CP" -d "$F/out" \
  "$F/stub/ApiStub.kt" $1 2>&1 | grep -v "unable to find kotlin-stdlib" | grep -v "^warning" | head -80
echo "compile exit: ${PIPESTATUS[0]}"
cp -r "$W/test/resources/." "$F/out/"
if [ -n "${2:-}" ]; then
  java -cp "$F/out:$CP:$K/kotlinc/lib/kotlin-stdlib.jar" org.junit.runner.JUnitCore $2 2>&1 | grep -v "^\s*at " | tail -40
fi
