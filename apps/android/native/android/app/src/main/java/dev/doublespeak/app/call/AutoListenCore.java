package dev.doublespeak.app.call;

/**
 * Glue between the call-state machine, the per-version start policy and the side effects (pure, unit-tested).
 * The Android layer (CallMonitor) implements Effects and feeds it call states from the PHONE_STATE receiver and the
 * in-process TelephonyCallback / PhoneStateListener.
 */
public final class AutoListenCore {
    public interface Effects {
        /** Start the microphone service directly. Returns false if the platform refused (background start). */
        boolean startDirect();
        /** Post the high-priority "Call answered. Tap Listen" notification. */
        void postPrompt();
        void cancelPrompt();
        /** Stop listening (service stop + wipe) and remove the prompt. */
        void stopListening();
    }

    public interface Env {
        boolean enabled();
        boolean permissionsOk();
        int sdk();
        boolean appResumed();
        /** The page is already listening by hand (Start listening): do not open a second session. */
        boolean pageListening();
    }

    public enum Result { NONE, STARTED_DIRECT, PROMPTED, SKIPPED_PAGE, SKIPPED_OFF, STOPPED }

    private CallStateMachine m;
    private final Effects fx;

    public AutoListenCore(CallStateMachine m, Effects fx) { this.m = m; this.fx = fx; }

    public CallStateMachine machine() { return m; }

    public Result onPhoneState(CallStateMachine.Phone p, Env env) {
        boolean on = env.enabled() && env.permissionsOk();
        CallStateMachine.Action a = m.onPhoneState(p, on);
        if (a == CallStateMachine.Action.STOP) { fx.stopListening(); return Result.STOPPED; }
        if (p == CallStateMachine.Phone.IDLE) { fx.cancelPrompt(); return Result.NONE; }   // missed call: drop any prompt
        if (a != CallStateMachine.Action.START) return (p == CallStateMachine.Phone.OFFHOOK && !on) ? Result.SKIPPED_OFF : Result.NONE;
        if (env.pageListening()) { m.onSessionEnded(); return Result.SKIPPED_PAGE; }
        if (StartPolicy.decide(env.sdk(), env.appResumed()) == StartPolicy.Path.DIRECT && fx.startDirect()) return Result.STARTED_DIRECT;
        fx.postPrompt();
        return Result.PROMPTED;
    }

    /** Stop from the notification or the app. */
    public void onUserStop() {
        m.onUserStop();
        fx.stopListening();
    }

    public void onSettingChanged(boolean enabled) {
        if (m.onSettingChanged(enabled) == CallStateMachine.Action.STOP) fx.stopListening();
        if (!enabled) fx.cancelPrompt();
    }

    /** The session ended on its own (not connected, lost, mic failed). */
    public void onSessionEnded() { m.onSessionEnded(); }
}
