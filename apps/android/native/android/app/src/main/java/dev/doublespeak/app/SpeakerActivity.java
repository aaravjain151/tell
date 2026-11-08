package dev.doublespeak.app;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.telecom.TelecomManager;

/**
 * "Turn on speaker": brings the phone app's in-call screen to the front so the user can tap its Speaker button.
 *
 * Tell does NOT switch the audio route itself. On Android 12+ an ordinary app cannot: during a cellular call
 * AudioManager.setSpeakerphoneOn() is ignored for callers without MODIFY_PHONE_STATE (a system permission), and
 * setCommunicationDevice() only takes effect for the app that owns the audio mode (the phone app). Hidden APIs,
 * accessibility services and InCallService (the default-dialer role) are deliberately not used.
 * TelecomManager.showInCallScreen() is public API and needs READ_PHONE_STATE, which auto-listen already holds.
 * Theme.NoDisplay: this activity never draws and finishes in onCreate.
 */
public class SpeakerActivity extends Activity {
    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        try {
            TelecomManager tm = (TelecomManager) getSystemService(Context.TELECOM_SERVICE);
            if (tm != null && Build.VERSION.SDK_INT >= 23 && checkSelfPermission(Manifest.permission.READ_PHONE_STATE) == PackageManager.PERMISSION_GRANTED)
                tm.showInCallScreen(false);
        } catch (SecurityException ignored) {
        }
        finish();
    }
}
