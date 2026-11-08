package dev.doublespeak.app;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;

import androidx.core.app.ActivityCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.ContextCompat;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.util.ArrayList;
import java.util.List;

import dev.doublespeak.app.call.PermissionGate;
import dev.doublespeak.app.call.StartPolicy;

/**
 * JS: Capacitor.Plugins.ListenService
 *   start() / stop()                       the page's own listening (foreground service only, capture in the WebView)
 *   getAutoListen()                        {available, enabled, consented, sdk, permissions, missing, state, background}
 *   setAutoListen({enabled})               turning on asks for Phone, Microphone and (Android 13+) Notifications;
 *                                          any refusal leaves the setting OFF and returns {enabled:false, missing, message}
 *   stopAutoListen()                       the app's Stop while auto-listening
 *   openAppSettings()                      Android's app info screen (for a permission refused for good)
 *   event "autoListen" {kind, state, level}  kind: state | level | call
 */
@CapacitorPlugin(
    name = "ListenService",
    permissions = {
        @Permission(alias = "phone", strings = { Manifest.permission.READ_PHONE_STATE }),
        @Permission(alias = "microphone", strings = { Manifest.permission.RECORD_AUDIO }),
        @Permission(alias = "notifications", strings = { Manifest.permission.POST_NOTIFICATIONS })
    }
)
public class ListenServicePlugin extends Plugin {

    @Override
    public void load() {
        AutoListenBus.set((kind, state, level) -> {
            JSObject o = new JSObject();
            o.put("kind", kind);
            o.put("state", state);
            o.put("level", level);
            notifyListeners("autoListen", o);
        });
    }

    @PluginMethod
    public void start(PluginCall call) {
        // Notification permission (Android 13+) is asked once; the service still runs if it is denied.
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(getContext(), Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(getActivity(), new String[]{Manifest.permission.POST_NOTIFICATIONS}, 4401);
        }
        // Android 14 refuses a microphone service without RECORD_AUDIO; the page calls start() after getUserMedia succeeded.
        if (ContextCompat.checkSelfPermission(getContext(), Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            call.reject("microphone permission missing");
            return;
        }
        if (CallListenService.running) {       // auto-listen already streams this call: the page must not open a second session
            call.reject("auto-listen is already listening");
            return;
        }
        try {
            ContextCompat.startForegroundService(getContext(), new Intent(getContext(), ListenService.class));
            JSObject r = new JSObject();
            r.put("started", true);
            call.resolve(r);
        } catch (Exception e) {
            call.reject("could not start the listening service: " + e.getClass().getSimpleName());
        }
    }

    @PluginMethod
    public void stop(PluginCall call) {
        getContext().stopService(new Intent(getContext(), ListenService.class));
        call.resolve();
    }

    // ---------- auto-listen ----------

    private boolean has(String p) { return ContextCompat.checkSelfPermission(getContext(), p) == PackageManager.PERMISSION_GRANTED; }

    private boolean notificationsOk() {
        if (Build.VERSION.SDK_INT >= 33 && !has(Manifest.permission.POST_NOTIFICATIONS)) return false;
        return NotificationManagerCompat.from(getContext()).areNotificationsEnabled();
    }

    private List<String> missing() {
        return PermissionGate.missing(has(Manifest.permission.READ_PHONE_STATE), has(Manifest.permission.RECORD_AUDIO), notificationsOk());
    }

    private JSObject status() {
        JSObject o = new JSObject();
        boolean enabled = AutoListenPrefs.enabled(getContext());
        List<String> miss = missing();
        o.put("available", true);
        o.put("enabled", enabled);
        o.put("consented", AutoListenPrefs.consented(getContext()));
        o.put("sdk", Build.VERSION.SDK_INT);
        JSObject perms = new JSObject();
        perms.put("phone", has(Manifest.permission.READ_PHONE_STATE));
        perms.put("microphone", has(Manifest.permission.RECORD_AUDIO));
        perms.put("notifications", notificationsOk());
        o.put("permissions", perms);
        o.put("missing", new JSArray(miss));
        o.put("state", CallListenService.running ? AutoListenBus.state : "idle");
        o.put("background", StartPolicy.decide(Build.VERSION.SDK_INT, false) == StartPolicy.Path.DIRECT ? "direct" : "tap");
        return o;
    }

    @PluginMethod
    public void getAutoListen(PluginCall call) {
        call.resolve(status());
    }

    @PluginMethod
    public void setAutoListen(PluginCall call) {
        boolean on = Boolean.TRUE.equals(call.getBoolean("enabled", false));
        if (!on) {
            AutoListenPrefs.setEnabled(getContext(), false);
            CallMonitor.get(getContext()).onSettingChanged(false);
            call.resolve(status());
            return;
        }
        List<String> aliases = new ArrayList<>();
        if (getPermissionState("phone") != PermissionState.GRANTED) aliases.add("phone");
        if (getPermissionState("microphone") != PermissionState.GRANTED) aliases.add("microphone");
        if (Build.VERSION.SDK_INT >= 33 && getPermissionState("notifications") != PermissionState.GRANTED) aliases.add("notifications");
        if (aliases.isEmpty()) { finishEnable(call); return; }
        requestPermissionForAliases(aliases.toArray(new String[0]), call, "autoListenPerms");
    }

    @PermissionCallback
    private void autoListenPerms(PluginCall call) { finishEnable(call); }

    private void finishEnable(PluginCall call) {
        List<String> miss = missing();
        if (!miss.isEmpty()) {
            AutoListenPrefs.setEnabled(getContext(), false);
            JSObject o = status();
            o.put("message", PermissionGate.explain(miss));
            call.resolve(o);
            return;
        }
        AutoListenPrefs.setEnabled(getContext(), true);
        CallMonitor.get(getContext()).onSettingChanged(true);
        Notices.channels(getContext());
        call.resolve(status());
    }

    @PluginMethod
    public void stopAutoListen(PluginCall call) {
        CallMonitor.get(getContext()).onUserStop();
        getContext().stopService(new Intent(getContext(), CallListenService.class));
        call.resolve();
    }

    @PluginMethod
    public void openAppSettings(PluginCall call) {
        Intent i = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", getContext().getPackageName(), null));
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        getContext().startActivity(i);
        call.resolve();
    }
}
