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

# THE SAME REFLECTIVE HOLE, ONE STEP FURTHER ALONG - found on a real phone on
# 2026-10-27, after the Room rule above had already stopped the crash.
#
# WorkManager names its default InputMerger as a STRING and loads it by name:
#
#   WorkRequest.Builder -> inputMergerClassName = OverwritingInputMerger.class.getName()
#   WorkerWrapper       -> Class.forName(that string).newInstance()
#
# androidx.work's own consumer rules are why the CLASS survives at all, and
# also why it still failed. Unzipped from the artifact this app actually
# bundles (work-runtime-2.7.1.aar, its proguard.txt):
#
#   -keep class * extends androidx.work.InputMerger
#
# A `-keep class` with no member specification keeps the class and its name,
# not its constructors. Nothing in any static call graph calls
# OverwritingInputMerger's no-arg constructor - only `newInstance()` does,
# invisibly to R8 - so it was stripped. On the phone that is not a crash; it
# is a silent, permanent failure:
#
#   E/WM-InputMerger: Trouble instantiating + androidx.work.OverwritingInputMerger
#       java.lang.InstantiationException: java.lang.Class<...> has no zero
#       argument constructor
#   E/WM-WorkerWrapper: Could not create Input Merger androidx.work.OverwritingInputMerger
#
# WorkManager needs that merger to run ANY job, and Glance runs a home-screen
# widget's entire composition inside one of those jobs
# (androidx.glance.session.SessionWorker, a CoroutineWorker). So no Glance
# worker ever started, no widget was ever drawn, and every Jarvis widget sat
# on the launcher's `initialLayout` - Glance's own bare ProgressBar, the
# "buffering for ever" the owner reported - while the app itself worked
# perfectly, because the app never uses WorkManager directly.
#
# CHECKED AGAINST THE SHIPPED APK'S OWN DEX, the artifact that actually failed
# (pulled from the phone, not inferred): `dexdump classes.dex` shows
# Landroidx/work/OverwritingInputMerger; with no <init> at all, only the
# obfuscated merge method - and shows SessionWorker's public
# (Context, WorkerParameters) constructor still present, kept by
# WorkManager's own ListenableWorker rule. So this is the missing piece, not
# one of several.
#
# This is also the part the note above says could not be verified, because the
# dev container has no route to dl.google.com. It can now be: the AAR is in
# this PC's Gradle cache and its proguard.txt is quoted verbatim above.
-keep class * extends androidx.work.InputMerger {
    <init>(...);
}

# ONNX Runtime (the "hey Jarvis" spotter). Its native library looks Java
# classes, constructors and fields up BY NAME from C++ (OnnxTensor, OrtSession
# and its Result, OrtException, the OnnxValue types) - calls R8 cannot see, so
# without this it renames or strips them and the first wake-word model load
# fails at runtime in the minified release build only. The 1.22.0 AAR ships no
# consumer rules of its own (checked by unzipping it: no proguard.txt).
-keep class ai.onnxruntime.** { *; }

# A HOME-SCREEN WIDGET'S CLASS NAME IS ITS IDENTITY TO GLANCE - R8 MUST NOT
# MERGE THESE SEVEN CLASSES INTO ONE. (Measured 2026-10-30, from the shipped
# APK and the library it uses, not inferred.)
#
# Glance's redraw call is
#   GlanceAppWidget.updateAll(context) ->
#     GlanceAppWidgetManager.getGlanceIds(this.getClass())
# and getGlanceIds does `klass.getCanonicalName()` and looks that name up in
# `State.providerNameToReceivers`, a table built from this package's receivers
# (each receiver is instantiated and the class of its `glanceAppWidget` is the
# key). It then calls `update()` on the SAME widget instance for every id it
# finds. Two widget classes with the same canonical name are therefore
# indistinguishable: EACH one's updateAll repaints BOTH widgets' cards with its
# own content.
#
# R8 gave them the same name by merging them. `dexdump classes.dex` on the
# shipped client-latest APK (jarvis-client-263ea0d.apk, commit 263ea0d - the
# 0.2.3285 build) shows all seven classes gone and only two obfuscated ones
# created by the receivers:
#
#   JarvisBoardWidgetOne/Two/ThreeReceiver -> new-instance Ljd2; (slot 0/1/2)
#   Approval/QuickLink/CalendarWidgetReceiver -> new-instance Lvo; (disc 0/1/2)
#
# The phone symptom (field test, 2026-10-30 18:17-18:27): the owner put the
# saved widget into slot 2 and the launcher card kept reading "No widget
# chosen". JarvisBoardWidgets.updateAll calls One, then Two, then Three; with
# one merged class all three calls resolve to the same receiver list, so the
# last call - slot 3, which was empty - repainted every board card. The debug
# APK is not minified (`isMinifyEnabled = false` in build.gradle.kts), which is
# why the same code worked in the morning and only the release build failed.
# The same merge lets Approval, QuickLink and Calendar repaint each other's
# cards with their own words.
#
# A kept class cannot be renamed or optimized into another, so these seven
# names survive and each receiver maps to exactly its own widget. No member
# spec is needed: the constructors are called directly by this app's code, and
# what the merge broke is class identity, not reflection by name.
-keep class com.jarvis.client.widget.ApprovalWidget
-keep class com.jarvis.client.widget.QuickLinkWidget
-keep class com.jarvis.client.widget.CalendarWidget
-keep class com.jarvis.client.widget.JarvisBoardWidget
-keep class com.jarvis.client.widget.JarvisBoardWidgetOne
-keep class com.jarvis.client.widget.JarvisBoardWidgetTwo
-keep class com.jarvis.client.widget.JarvisBoardWidgetThree
