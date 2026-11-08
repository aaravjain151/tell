package dev.doublespeak.app;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Service;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.Build;
import android.os.IBinder;

import androidx.core.content.ContextCompat;

import dev.doublespeak.app.call.CallSession;
import dev.doublespeak.app.call.LoopbackEngine;

/**
 * Auto-listen microphone foreground service (type microphone). Unlike ListenService (which only keeps the page's own
 * capture alive), this one captures natively, so it works when the page is not open: AudioRecord at 16 kHz mono PCM16
 * -> WS /ws/stream on 127.0.0.1:8000 (= the computer, through adb reverse). Nothing is written to storage.
 * Started directly by CallMonitor (app in front, or Android 10 and older) or by the "Listen" notification action.
 * Stops on call end (CallMonitor stops the service), the Stop action, the setting turned off, the task swiped away.
 */
public class CallListenService extends Service {
    static final String ACTION_START = "dev.doublespeak.app.CALL_START";
    static final String ACTION_STOP = "dev.doublespeak.app.CALL_STOP";
    static final String ACTION_REPOST = "dev.doublespeak.app.CALL_REPOST";
    static final String EXTRA_TAPPED = "tapped";
    static final int PORT = 8000;

    static volatile boolean running;
    private CallSession session;
    private Thread worker;
    private volatile boolean silent;

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? null : intent.getAction();
        if (ACTION_STOP.equals(action)) {                 // the Stop action: no restart for the rest of this call
            CallMonitor.get(this).onUserStop();
            end();
            return START_NOT_STICKY;
        }
        if (ACTION_REPOST.equals(action)) {              // the user swiped the ongoing notification away (Android 14+)
            if (session != null) Notices.nm(this).notify(Notices.ID_LISTEN, Notices.listening(this, silent));
            return START_NOT_STICKY;
        }
        if (!ACTION_START.equals(action) || session != null) return START_NOT_STICKY;
        Notices.cancelPrompt(this);
        // Never start when the setting is off, without the microphone permission, or after the call ended.
        if (!AutoListenPrefs.enabled(this) || !granted(Manifest.permission.RECORD_AUDIO) || !CallMonitor.get(this).inCall()) {
            beForegroundBriefly();
            end();
            return START_NOT_STICKY;
        }
        try {
            if (Build.VERSION.SDK_INT >= 29) startForeground(Notices.ID_LISTEN, Notices.listening(this, false), ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
            else startForeground(Notices.ID_LISTEN, Notices.listening(this, false));
        } catch (RuntimeException e) {                    // Android 14: background microphone start refused -> ask for a tap
            Notices.prompt(this);
            stopSelf();
            return START_NOT_STICKY;
        }
        running = true;
        Notices.cancelNotice(this);
        AutoListenBus.emit("state", "starting", 0);
        session = new CallSession(new LoopbackEngine(PORT, 1500), new AndroidMic(this), System::currentTimeMillis, new CallSession.Ui() {
            @Override public void onListening() { AutoListenBus.emit("state", "listening", 0); }
            @Override public void onLevel(double rms) { AutoListenBus.emit("level", "listening", rms); }
            @Override public void onSilent() {
                silent = true;
                Notices.nm(CallListenService.this).notify(Notices.ID_LISTEN, Notices.listening(CallListenService.this, true));
                AutoListenBus.emit("state", "silent", 0);
            }
            @Override public void onVerdict(String json) {}       // the page shows verdicts from the engine's own feed
            @Override public void onEnded(CallSession.Outcome o, String text) {
                // STOPPED and DROPPED are clean ends (no scary notice). MIC_SILENCED gets the honest "can't hear this call"
                // notice; the engine-unreachable outcomes get the "plug in the USB cable" notice.
                if (o == CallSession.Outcome.MIC_SILENCED)
                    Notices.blocked(CallListenService.this);
                else if (o != CallSession.Outcome.STOPPED && o != CallSession.Outcome.DROPPED)
                    Notices.notice(CallListenService.this, text);
                CallMonitor.get(CallListenService.this).onSessionEnded();
                AutoListenBus.emit("state", "ended:" + o.name().toLowerCase(java.util.Locale.ROOT), 0);
                end();
            }
        });
        final CallSession s = session;
        worker = new Thread(s::run, "tell-call-listen");
        worker.start();
        return START_NOT_STICKY;
    }

    /** startForegroundService() must be followed by startForeground() even when we decide not to listen. */
    private void beForegroundBriefly() {
        try {
            if (Build.VERSION.SDK_INT >= 29) startForeground(Notices.ID_LISTEN, Notices.listening(this, false), ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
            else startForeground(Notices.ID_LISTEN, Notices.listening(this, false));
        } catch (RuntimeException ignored) {}
    }

    private synchronized void end() {
        CallSession s = session;
        session = null;
        if (s != null) s.requestStop();
        running = false;
        silent = false;
        if (Build.VERSION.SDK_INT >= 24) stopForeground(STOP_FOREGROUND_REMOVE); else stopForegroundLegacy();
        stopSelf();
    }

    @SuppressWarnings("deprecation")
    private void stopForegroundLegacy() { stopForeground(true); }

    @Override
    public void onTaskRemoved(Intent rootIntent) {      // the app was swiped away from Recents: stop, as on app kill
        CallMonitor.get(this).onUserStop();
        end();
    }

    @Override
    public void onDestroy() {
        CallSession s = session;
        session = null;
        if (s != null) s.requestStop();
        running = false;                                  // the worker ends within one 100 ms frame and reports "ended"
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }

    private boolean granted(String p) { return ContextCompat.checkSelfPermission(this, p) == PackageManager.PERMISSION_GRANTED; }

    /** AudioRecord, 16 kHz mono PCM16, raw where the phone offers it (UNPROCESSED), else VOICE_RECOGNITION (no AGC). */
    static final class AndroidMic implements CallSession.Mic {
        private final Service ctx;
        private AudioRecord rec;

        AndroidMic(Service ctx) { this.ctx = ctx; }

        @SuppressLint("MissingPermission")   // checked by onStartCommand before the session exists
        @Override
        public boolean start() {
            if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) return false;
            int src = MediaRecorder.AudioSource.VOICE_RECOGNITION;
            if (Build.VERSION.SDK_INT >= 24) {
                AudioManager am = (AudioManager) ctx.getSystemService(AUDIO_SERVICE);
                if (am != null && "true".equals(am.getProperty(AudioManager.PROPERTY_SUPPORT_AUDIO_SOURCE_UNPROCESSED)))
                    src = MediaRecorder.AudioSource.UNPROCESSED;
            }
            int min = AudioRecord.getMinBufferSize(CallSession.RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
            if (min <= 0) return false;
            try {
                rec = new AudioRecord(src, CallSession.RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, Math.max(min, CallSession.FRAME * 2 * 4));
                if (rec.getState() != AudioRecord.STATE_INITIALIZED) { release(); return false; }
                rec.startRecording();
                return rec.getRecordingState() == AudioRecord.RECORDSTATE_RECORDING;
            } catch (RuntimeException e) {
                release();
                return false;
            }
        }

        @Override
        public int read(short[] buf) {
            AudioRecord r = rec;
            if (r == null) return -1;
            int off = 0;
            while (off < buf.length) {
                int n = r.read(buf, off, buf.length - off);
                if (n < 0) return -1;
                if (n == 0) break;
                off += n;
            }
            return off;
        }

        @Override
        public void release() {
            AudioRecord r = rec;
            rec = null;
            if (r == null) return;
            try { r.stop(); } catch (RuntimeException ignored) {}
            r.release();
        }
    }
}
