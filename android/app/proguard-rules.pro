# Chaquopy Python 运行时
-keep class com.chaquo.** { *; }
-keep class com.dorm.management.** { *; }
-keep class org.python.** { *; }

# Kotlin 协程与反射
-dontwarn kotlinx.coroutines.**
-keep class kotlinx.coroutines.** { *; }
-keepclassmembers class kotlinx.coroutines.** { *; }
-keep class kotlin.reflect.** { *; }

# AndroidX Core
-keep class androidx.core.** { *; }
-keep class androidx.appcompat.** { *; }
-keep class androidx.webkit.** { *; }
-keep class androidx.core.splashscreen.** { *; }
-dontwarn androidx.**

# Material Design
-keep class com.google.android.material.** { *; }
-dontwarn com.google.android.material.**

# Lottie 动画库
-keep class com.airbnb.lottie.** { *; }
-dontwarn com.airbnb.lottie.**

# WebView JavaScript Interface
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}

# 序列化
-keepclassmembers class * implements java.io.Serializable {
    static final long serialVersionUID;
    private static final java.io.ObjectStreamField[] serialPersistentFields;
    !static !transient <fields>;
    private void writeObject(java.io.ObjectOutputStream);
    private void readObject(java.io.ObjectInputStream);
    java.lang.Object writeReplace();
    java.lang.Object readResolve();
}

# 通用优化
-dontwarn java.lang.invoke.StringConcatFactory
-dontwarn javax.annotation.**
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile