# SDK callbacks must not write OAuth authorization codes or relay URIs to logcat.
-assumenosideeffects class android.util.Log {
    public static int v(...);
    public static int d(...);
    public static int i(...);
}
