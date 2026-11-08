package dev.doublespeak.app.call;

import java.io.IOException;

/**
 * One auto-listen session (pure orchestration, unit-tested with fakes): open the engine link, open the microphone,
 * stream 100 ms PCM16 frames, ping every 10 s, watch for silence, and end with exactly one Outcome.
 * Nothing is written anywhere: frames live in one reused buffer and are overwritten (wiped) at the end.
 */
public final class CallSession {
    public enum Outcome {
        STOPPED,        // call ended, Stop tapped, setting turned off, app task removed
        NOT_CONNECTED,  // engine unreachable (cable out, adb reverse missing, engine not running)
        REFUSED,        // 403: engine started without the app's origin (use make api-android)
        BUSY,           // 429: another session is open
        LOST,           // link dropped mid-call
        MIC_FAILED      // AudioRecord could not start
    }

    public static final int RATE = 16000, FRAME = 1600;     // 100 ms
    public static final long PING_MS = 10000;

    public static final class EngineError extends Exception {
        public final Outcome outcome;
        public EngineError(Outcome o, String detail) { super(detail); outcome = o; }
    }

    public interface LinkListener {
        void onServerMessage(String type, String json);
        void onServerClosed(String why);
    }

    public interface Link {
        void sendAudio(byte[] pcm, int len) throws IOException;
        void sendText(String json) throws IOException;
        void close();
    }

    public interface Engine { Link open(LinkListener l) throws EngineError; }

    public interface Mic {
        boolean start();
        /** Blocking read of up to buf.length samples; returns the count, or a negative number on error. */
        int read(short[] buf);
        void release();
    }

    public interface Clock { long now(); }

    public interface Ui {
        void onListening();
        void onLevel(double rms);
        void onSilent();
        void onVerdict(String json);
        void onEnded(Outcome o, String text);
    }

    private final Engine engine; private final Mic mic; private final Clock clock; private final Ui ui;
    private volatile boolean stop;
    private volatile String lostWhy;

    public CallSession(Engine engine, Mic mic, Clock clock, Ui ui) {
        this.engine = engine; this.mic = mic; this.clock = clock; this.ui = ui;
    }

    public void requestStop() { stop = true; }

    public static String textFor(Outcome o) {
        switch (o) {
            case NOT_CONNECTED: return Wording.NOT_CONNECTED_TEXT;
            case REFUSED: return Wording.REFUSED_TEXT;
            case BUSY: return Wording.BUSY_TEXT;
            case LOST: return Wording.LOST_TEXT;
            case MIC_FAILED: return Wording.MIC_TEXT;
            default: return "";
        }
    }

    /** Runs on a worker thread until the session ends. Always calls ui.onEnded exactly once. */
    public Outcome run() {
        Link link;
        try {
            link = engine.open(new LinkListener() {
                @Override public void onServerMessage(String type, String json) { if ("verdict".equals(type)) ui.onVerdict(json); }
                @Override public void onServerClosed(String why) { lostWhy = why == null ? "closed" : why; }
            });
        } catch (EngineError e) {
            return end(e.outcome);
        }
        if (stop) { link.close(); return end(Outcome.STOPPED); }
        if (!mic.start()) { link.close(); mic.release(); return end(Outcome.MIC_FAILED); }
        ui.onListening();
        short[] buf = new short[FRAME];
        byte[] pcm = new byte[FRAME * 2];
        SilenceWatch silence = new SilenceWatch();
        long t0 = clock.now(), lastPing = t0, lastLevel = 0;
        Outcome out = Outcome.STOPPED;
        try {
            while (!stop) {
                if (lostWhy != null) { out = "final".equals(lostWhy) ? Outcome.STOPPED : Outcome.LOST; break; }
                int n = mic.read(buf);
                if (n < 0) { out = Outcome.MIC_FAILED; break; }
                if (n == 0) continue;
                for (int i = 0; i < n; i++) { pcm[2 * i] = (byte) buf[i]; pcm[2 * i + 1] = (byte) (buf[i] >> 8); }
                long now = clock.now();
                try {
                    link.sendAudio(pcm, n * 2);
                    if (now - lastPing >= PING_MS) { link.sendText("{\"type\":\"ping\"}"); lastPing = now; }
                } catch (IOException e) {
                    out = Outcome.LOST; break;
                }
                double r = SilenceWatch.rms(buf, n);
                if (silence.feed(r, now - t0)) ui.onSilent();
                if (now - lastLevel >= 200) { ui.onLevel(r); lastLevel = now; }
            }
        } finally {
            java.util.Arrays.fill(buf, (short) 0);
            java.util.Arrays.fill(pcm, (byte) 0);
            mic.release();
            link.close();
        }
        return end(out);
    }

    private Outcome end(Outcome o) {
        ui.onEnded(o, textFor(o));
        return o;
    }
}
