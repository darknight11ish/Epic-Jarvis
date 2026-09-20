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
