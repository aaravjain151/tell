package dev.doublespeak.app;

import android.Manifest;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.telephony.PhoneStateListener;
import android.telephony.TelephonyCallback;
import android.telephony.TelephonyManager;

import androidx.annotation.RequiresApi;
import androidx.core.content.ContextCompat;

import dev.doublespeak.app.call.AutoListenCore;
import dev.doublespeak.app.call.CallStateMachine;

/**
 * Process-wide auto-listen controller. Call states arrive from two sources (both feed the same machine, which ignores
 * repeats): the manifest PHONE_STATE receiver (works when the process was not running) and an in-process listener,
 * TelephonyCallback.CallStateListener on Android 12+ or PhoneStateListener below. Both need READ_PHONE_STATE.
 */
final class CallMonitor implements AutoListenCore.Effects, AutoListenCore.Env {
    private static CallMonitor instance;

    static synchronized CallMonitor get(Context c) {
        if (instance == null) instance = new CallMonitor(c.getApplicationContext());
        return instance;
    }

    private final Context ctx;
    private final AutoListenCore core;
    private Object listener;   // TelephonyCallback (31+) or PhoneStateListener

    private CallMonitor(Context ctx) {
        this.ctx = ctx;
        this.core = new AutoListenCore(CallStateMachine.restore(AutoListenPrefs.machine(ctx)), this);
    }

    synchronized void onPhoneState(CallStateMachine.Phone p) {
        AutoListenCore.Result r = core.onPhoneState(p, this);
        AutoListenPrefs.saveMachine(ctx, core.machine().snapshot());
        AutoListenBus.emit("call", p.name().toLowerCase(java.util.Locale.ROOT) + ":" + r.name().toLowerCase(java.util.Locale.ROOT), 0);
    }

    synchronized void onUserStop() {
        core.onUserStop();
        AutoListenPrefs.saveMachine(ctx, core.machine().snapshot());
    }

    synchronized void onSessionEnded() {
        core.onSessionEnded();
        AutoListenPrefs.saveMachine(ctx, core.machine().snapshot());
    }

    synchronized void onSettingChanged(boolean on) {
        core.onSettingChanged(on);
        AutoListenPrefs.saveMachine(ctx, core.machine().snapshot());
        if (on) registerTelephony(); else unregisterTelephony();
    }

    boolean inCall() { return core.machine().inCall(); }

    // ---------- in-process listener ----------

    synchronized void registerTelephony() {
        if (listener != null || !granted(Manifest.permission.READ_PHONE_STATE)) return;
        TelephonyManager tm = (TelephonyManager) ctx.getSystemService(Context.TELEPHONY_SERVICE);
        if (tm == null) return;
        try {
            if (Build.VERSION.SDK_INT >= 31) {
                Callback31 cb = new Callback31(this);
                tm.registerTelephonyCallback(ctx.getMainExecutor(), cb);
                listener = cb;
            } else {
                Legacy l = new Legacy(this);
                tm.listen(l, PhoneStateListener.LISTEN_CALL_STATE);
                listener = l;
            }
        } catch (SecurityException e) {
            listener = null;
        }
    }

    synchronized void unregisterTelephony() {
        if (listener == null) return;
        TelephonyManager tm = (TelephonyManager) ctx.getSystemService(Context.TELEPHONY_SERVICE);
        try {
            if (Build.VERSION.SDK_INT >= 31 && listener instanceof TelephonyCallback) tm.unregisterTelephonyCallback((TelephonyCallback) listener);
            else if (listener instanceof PhoneStateListener) tm.listen((PhoneStateListener) listener, PhoneStateListener.LISTEN_NONE);
        } catch (RuntimeException ignored) {}
        listener = null;
    }

    static CallStateMachine.Phone fromInt(int s) {
        if (s == TelephonyManager.CALL_STATE_RINGING) return CallStateMachine.Phone.RINGING;
        if (s == TelephonyManager.CALL_STATE_OFFHOOK) return CallStateMachine.Phone.OFFHOOK;
        return CallStateMachine.Phone.IDLE;
    }

    @RequiresApi(31)
    static final class Callback31 extends TelephonyCallback implements TelephonyCallback.CallStateListener {
        private final CallMonitor m;
        Callback31(CallMonitor m) { this.m = m; }
        @Override public void onCallStateChanged(int state) { m.onPhoneState(fromInt(state)); }
    }

    @SuppressWarnings("deprecation")
    static final class Legacy extends PhoneStateListener {
        private final CallMonitor m;
        Legacy(CallMonitor m) { this.m = m; }
        @Override public void onCallStateChanged(int state, String ignoredNumber) { m.onPhoneState(fromInt(state)); }
    }

    // ---------- Effects ----------

    @Override
    public boolean startDirect() {
        try {
            ContextCompat.startForegroundService(ctx, new Intent(ctx, CallListenService.class).setAction(CallListenService.ACTION_START));
            return true;
        } catch (IllegalStateException | SecurityException e) {   // ForegroundServiceStartNotAllowedException is an IllegalStateException
            return false;
        }
    }

    @Override public void postPrompt() { Notices.prompt(ctx); }
    @Override public void cancelPrompt() { Notices.cancelPrompt(ctx); }

    @Override
    public void stopListening() {
        Notices.cancelPrompt(ctx);
        ctx.stopService(new Intent(ctx, CallListenService.class));
    }

    // ---------- Env ----------

    @Override public boolean enabled() { return AutoListenPrefs.enabled(ctx); }
    @Override public boolean permissionsOk() { return granted(Manifest.permission.READ_PHONE_STATE) && granted(Manifest.permission.RECORD_AUDIO); }
    @Override public int sdk() { return Build.VERSION.SDK_INT; }
    @Override public boolean appResumed() { return TellApp.appResumed(); }
    @Override public boolean pageListening() { return ListenService.running; }

    boolean granted(String perm) { return ContextCompat.checkSelfPermission(ctx, perm) == PackageManager.PERMISSION_GRANTED; }
}
