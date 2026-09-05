# Chaquopy Python 运行时（com.chaquo 是 Chaquopy 的 Java 包名，chaquopy 仅是插件 ID）
-keep class com.chaquo.** { *; }

# Python 模块调用
-keep class com.dorm.management.** { *; }

# AndroidX 和 Material
-dontwarn androidx.**
-dontwarn com.google.android.material.**

# Flask 相关
-keep class org.python.** { *; }