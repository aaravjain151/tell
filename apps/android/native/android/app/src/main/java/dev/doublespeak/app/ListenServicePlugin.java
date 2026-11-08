package dev.doublespeak.app;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;

import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/** JS: Capacitor.Plugins.ListenService.start() / stop(). Starts or stops the microphone foreground service. */
@CapacitorPlugin(name = "ListenService")
public class ListenServicePlugin extends Plugin {

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
}
