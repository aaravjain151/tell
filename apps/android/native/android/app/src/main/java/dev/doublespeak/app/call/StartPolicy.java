package dev.doublespeak.app.call;

/**
 * How auto-listen starts on each Android version (pure, unit-tested). Background here means: no Tell activity is
 * resumed, which is the normal case on a call (the phone app's in-call screen is in front, or the screen is off).
 *
 *  - API 22..29 (Android 5.1..10): DIRECT. Starting a foreground service from a broadcast is allowed and the
 *    microphone has no "while-in-use" restriction yet.
 *  - API 30 (Android 11): TAP. A background start is allowed, but a microphone service started from the background
 *    gets no microphone access (while-in-use restriction): Android would hand the app silence.
 *  - API 31..33 (Android 12, 12L, 13): TAP. startForegroundService from the background throws
 *    ForegroundServiceStartNotAllowedException; receiving PHONE_STATE is not one of the exemptions.
 *  - API 34+ (Android 14+): TAP. As 12-13, and a microphone-type service started from the background throws
 *    SecurityException.
 *  - Any version with a Tell activity resumed: DIRECT (a visible app may start a microphone service).
 *
 * TAP = a high-priority notification "Call answered. Tap Listen"; tapping its action starts the service
 * (a notification tap is an allowed start and grants microphone access on every version).
 */
public final class StartPolicy {
    public enum Path { DIRECT, TAP }

    private StartPolicy() {}

    public static Path decide(int sdk, boolean appResumed) {
        if (appResumed) return Path.DIRECT;
        if (sdk < 30) return Path.DIRECT;
        return Path.TAP;
    }

    /** A DIRECT start that the platform refused (exception) falls back to the tap notification. */
    public static Path afterDirectFailed() { return Path.TAP; }
}
