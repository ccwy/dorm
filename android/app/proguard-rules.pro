# Chaquopy Python 运行时
-keep class chaquopy.** { *; }
-keep class com.chaquo.** { *; }

# Python 模块调用
-keep class com.dorm.management.** { *; }

# AndroidX 和 Material
-dontwarn androidx.**
-dontwarn com.google.android.material.**

# Flask 相关
-keep class org.python.** { *; }