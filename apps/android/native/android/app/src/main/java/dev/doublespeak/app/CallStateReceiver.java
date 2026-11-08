package dev.doublespeak.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.telephony.TelephonyManager;

import dev.doublespeak.app.call.CallStateMachine;

/**
 * Manifest receiver for android.intent.action.PHONE_STATE (a protected broadcast: only the system can send it).
 * It wakes Tell when a call rings, is answered or ends, even if the app process is not running. Disabled in the
 * manifest and enabled only while the auto-listen setting is on. It reads the state only, never the number
 * (EXTRA_INCOMING_NUMBER needs READ_CALL_LOG, which Tell does not request).
 */
public class CallStateReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || !TelephonyManager.ACTION_PHONE_STATE_CHANGED.equals(intent.getAction())) return;
        CallStateMachine.Phone p = map(intent.getStringExtra(TelephonyManager.EXTRA_STATE));
        if (p == null) return;
        CallMonitor m = CallMonitor.get(context);
        m.registerTelephony();                 // the process may have just been started by this broadcast
        m.onPhoneState(p);
    }

    static CallStateMachine.Phone map(String s) {
        if (TelephonyManager.EXTRA_STATE_RINGING.equals(s)) return CallStateMachine.Phone.RINGING;
        if (TelephonyManager.EXTRA_STATE_OFFHOOK.equals(s)) return CallStateMachine.Phone.OFFHOOK;
        if (TelephonyManager.EXTRA_STATE_IDLE.equals(s)) return CallStateMachine.Phone.IDLE;
        return null;
    }
}
