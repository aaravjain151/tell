package dev.doublespeak.app.call;

/**
 * Notices a microphone that stays silent (pure). Android silences ordinary apps' microphones during a cellular call
 * on many builds; when that happens the user gets told instead of Tell quietly judging silence.
 */
public final class SilenceWatch {
    public static final double THRESHOLD = 0.003;   // same as the page's 8 s "no sound" check
    public static final long AFTER_MS = 8000;

    private double max;
    private boolean fired;

    /** Feed one frame's RMS (0..1) at elapsed ms since capture began. Returns true once, when silence is established. */
    public boolean feed(double rms, long elapsedMs) {
        if (rms > max) max = rms;
        if (!fired && elapsedMs >= AFTER_MS && max < THRESHOLD) { fired = true; return true; }
        return false;
    }

    public double max() { return max; }

    public static double rms(short[] s, int n) {
        if (n <= 0) return 0;
        double acc = 0;
        for (int i = 0; i < n; i++) { double x = s[i] / 32768.0; acc += x * x; }
        return Math.sqrt(acc / n);
    }
}
