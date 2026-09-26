# R8 for the release variant.
#
# Deliberately short, and the reason is worth writing down: nearly everything
# this app needs kept is already kept by rules the libraries ship themselves.
# Verified by looking inside the artifacts rather than by reading a blog:
#
#   kotlinx-serialization-core-jvm-1.7.3.jar
#     META-INF/com.android.tools/r8/kotlinx-serialization-r8.pro
#     META-INF/com.android.tools/r8/kotlinx-serialization-common.pro
#   okhttp-4.12.0.jar
#     META-INF/proguard/okhttp3.pro
#
# R8 consumes those automatically. The build file used to say minification was
# blocked on "the kotlinx-serialization keep rules"; that stopped being true
# several releases ago.
#
# AGP generates keeps for everything named in the manifest - JarvisApp,
# MainActivity, EventService, LinkTileService, BootReceiver - so none of them
# are listed here. The app has no Class.forName, no newInstance, and no
# reflective entry point of its own; every `::class.java` in the source is an
# Intent target or a system-service lookup, both direct references R8 follows.

# The models are reached only through their generated serializers, which the
# library's rules keep. This keeps the @Serializable classes' own members too,
# so a field that is only ever written by the serializer cannot be pruned out
# from under it.
-keepclassmembers,allowobfuscation class com.jarvis.client.net.** {
    *** Companion;
}
-keepclasseswithmembers class com.jarvis.client.net.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# Crash traces are the point of platform/CrashLog: a sideloaded app has no
# Play Console behind it, so the file the owner reads aloud is the only report
# there is. Obfuscated frames would make it useless.
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile

# WorkManager's own Room database, kept by name.
#
# The paragraph at the top of this file said nothing needed adding beyond
# what the libraries ship themselves. That held until the first real release
# build was actually launched on a device rather than only compiled, and it
# crashed before drawing a frame:
#
#   FATAL EXCEPTION: main
#   Unable to get provider androidx.startup.InitializationProvider
#   Caused by: java.lang.RuntimeException: Failed to create an instance of
#       androidx.work.impl.WorkDatabase
#       at androidx.work.WorkManagerInitializer.b(Unknown Source:93)
#
# Nothing in this app's own source uses WorkManager - it arrives only
# transitively, through androidx.glance:glance-appwidget, which schedules
# widget refreshes through it. WorkManager keeps its own job queue in a Room
# database (androidx.work.impl.WorkDatabase), and Room does not construct
# its generated implementation (WorkDatabase_Impl) directly: it looks the
# class up by name at runtime and reflectively calls its no-arg
# constructor. R8 cannot see that reflective call, so with nothing else in
# the app's static call graph referencing WorkDatabase_Impl, it read the
# constructor as unreachable and stripped it - a known, repeatedly-reported
# failure mode of Room-backed libraries under R8's full mode, not something
# specific to this app. androidx.work's and androidx.room's own consumer
# rules evidently do not cover WorkManager's INTERNAL database this way -
# if they did, the crash above would not have happened - so it is named
# explicitly here instead.
#
# NOT verified by inspecting the library's own bytecode: this container has
# no route to dl.google.com (see the top-level CLAUDE.md), so there is no
# way to open the AAR and check its consumer-rules.pro the way the
# kotlinx-serialization and okhttp entries above were checked. This is the
# documented shape of the exact crash above, matched against the exact
# stack trace this build produced rather than assumed from the library
# name alone - and GitHub Actions, the only compiler this module has, is
# what actually confirms it on the next run.
-keep class * extends androidx.room.RoomDatabase {
    <init>();
}

# ONNX Runtime (the "hey Jarvis" spotter). Its native library looks Java
# classes, constructors and fields up BY NAME from C++ (OnnxTensor, OrtSession
# and its Result, OrtException, the OnnxValue types) - calls R8 cannot see, so
# without this it renames or strips them and the first wake-word model load
# fails at runtime in the minified release build only. The 1.22.0 AAR ships no
# consumer rules of its own (checked by unzipping it: no proguard.txt).
-keep class ai.onnxruntime.** { *; }
