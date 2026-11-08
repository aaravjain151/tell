package dev.doublespeak.app;

import android.app.Activity;
import android.app.Application;
import android.os.Bundle;

/** Tracks whether a Tell activity is resumed (the only case where Android 11+ lets auto-listen start without a tap). */
public class TellApp extends Application {
    private static int resumed;

    static boolean appResumed() { return resumed > 0; }

    @Override
    public void onCreate() {
        super.onCreate();
        registerActivityLifecycleCallbacks(new ActivityLifecycleCallbacks() {
            @Override public void onActivityResumed(Activity a) { resumed++; }
            @Override public void onActivityPaused(Activity a) { resumed = Math.max(0, resumed - 1); }
            @Override public void onActivityCreated(Activity a, Bundle b) {}
            @Override public void onActivityStarted(Activity a) {}
            @Override public void onActivityStopped(Activity a) {}
            @Override public void onActivitySaveInstanceState(Activity a, Bundle b) {}
            @Override public void onActivityDestroyed(Activity a) {}
        });
        if (AutoListenPrefs.enabled(this)) CallMonitor.get(this).registerTelephony();
    }
}
