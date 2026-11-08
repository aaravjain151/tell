package dev.doublespeak.app;

import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;

/** The opt-in setting (OFF by default), the consent flag and the call-state snapshot. No numbers, no audio. */
final class AutoListenPrefs {
    private static final String FILE = "autolisten";
    private static final String ENABLED = "enabled", CONSENT = "consent_v1", MACHINE = "machine";

    private AutoListenPrefs() {}

    private static SharedPreferences p(Context c) { return c.getApplicationContext().getSharedPreferences(FILE, Context.MODE_PRIVATE); }

    static boolean enabled(Context c) { return p(c).getBoolean(ENABLED, false); }
    static boolean consented(Context c) { return p(c).getBoolean(CONSENT, false); }
    static String machine(Context c) { return p(c).getString(MACHINE, null); }
    static void saveMachine(Context c, String s) { p(c).edit().putString(MACHINE, s).apply(); }

    /** Also enables or disables the PHONE_STATE receiver, so with the setting off Tell is never even woken by a call. */
    static void setEnabled(Context c, boolean on) {
        SharedPreferences.Editor e = p(c).edit().putBoolean(ENABLED, on);
        if (on) e.putBoolean(CONSENT, true);
        e.apply();
        c.getPackageManager().setComponentEnabledSetting(new ComponentName(c, CallStateReceiver.class),
            on ? PackageManager.COMPONENT_ENABLED_STATE_ENABLED : PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
            PackageManager.DONT_KILL_APP);
    }
}
