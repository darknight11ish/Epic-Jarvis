# Kotlinx Serialization keeps its generated serializers via companion objects.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class com.jarvis.assistant.network.** {
    *** Companion;
}
-keepclasseswithmembers class com.jarvis.assistant.network.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# OkHttp ships optional Conscrypt/Bouncy Castle hooks that are absent at runtime.
-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
