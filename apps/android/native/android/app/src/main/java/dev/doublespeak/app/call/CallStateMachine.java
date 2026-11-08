package dev.doublespeak.app.call;

/**
 * Pure call-state machine for auto-listen (no Android imports, unit-tested on the JVM).
 *
 * Input: the phone's aggregate call state as Android reports it (TelephonyManager CALL_STATE_*): IDLE (no call),
 * RINGING (a call is ringing, also while another call is active = call waiting), OFFHOOK (at least one call is
 * dialing, active or on hold). Android reports IDLE only when every call has ended.
 *
 * Rules:
 *  - START once per call group, on the first OFFHOOK that follows a RINGING (= the user answered an incoming call),
 *    and only when the setting is on. An outgoing call (IDLE -> OFFHOOK) does not start listening; if a call waiting
 *    is then answered (RINGING -> OFFHOOK) it does.
 *  - STOP on IDLE (all calls ended), when the user taps Stop (no restart for the rest of that call group), and when
 *    the setting is turned off mid-call.
 *  - A missed or rejected call (RINGING -> IDLE) does nothing. Repeated identical states are ignored (Android may
 *    deliver a state twice: once to the manifest receiver and once to the in-process TelephonyCallback).
 */
public final class CallStateMachine {
    public enum Phone { IDLE, RINGING, OFFHOOK }
    public enum Action { NONE, START, STOP }

    private Phone last = Phone.IDLE;
    private boolean rang;            // a RINGING was seen in the current call group
    private boolean started;         // START already emitted in this call group
    private boolean listening;       // a listening session is believed to be running
    private boolean stoppedByUser;   // the user tapped Stop: no restart until the call group ends

    public Action onPhoneState(Phone p, boolean enabled) {
        if (p == null) return Action.NONE;
        if (p == last) return Action.NONE;
        Phone prev = last;
        last = p;
        switch (p) {
            case RINGING:
                rang = true;                       // incoming call, or call waiting during an active call
                return Action.NONE;
            case OFFHOOK:
                if (prev == Phone.RINGING && enabled && !started && !stoppedByUser) {
                    started = true;
                    listening = true;
                    return Action.START;
                }
                return Action.NONE;
            case IDLE:
            default:
                boolean wasListening = listening;
                reset();
                return wasListening ? Action.STOP : Action.NONE;
        }
    }

    /** The user tapped Stop (notification or app). */
    public Action onUserStop() {
        stoppedByUser = true;
        boolean was = listening;
        listening = false;
        return was ? Action.STOP : Action.NONE;
    }

    /** The setting changed. Turning it off mid-call stops; turning it on mid-call does not start (no answer event). */
    public Action onSettingChanged(boolean enabled) {
        if (!enabled && listening) {
            listening = false;
            stoppedByUser = true;
            return Action.STOP;
        }
        return Action.NONE;
    }

    /** The session ended by itself (engine unreachable, cable pulled, app killed). Do not restart in this call group. */
    public void onSessionEnded() {
        listening = false;
    }

    public boolean isListening() { return listening; }
    public boolean inCall() { return last != Phone.IDLE; }
    public Phone last() { return last; }

    private void reset() {
        rang = false; started = false; listening = false; stoppedByUser = false;
    }

    /** Tiny persisted form, so a process restarted between RINGING and OFFHOOK still recognises the answer. */
    public String snapshot() {
        return last.name() + "," + (rang ? 1 : 0) + "," + (started ? 1 : 0) + "," + (listening ? 1 : 0) + "," + (stoppedByUser ? 1 : 0);
    }

    public static CallStateMachine restore(String s) {
        CallStateMachine m = new CallStateMachine();
        if (s == null) return m;
        String[] f = s.split(",");
        if (f.length != 5) return m;
        try {
            m.last = Phone.valueOf(f[0]);
            m.rang = "1".equals(f[1]); m.started = "1".equals(f[2]); m.listening = "1".equals(f[3]); m.stoppedByUser = "1".equals(f[4]);
        } catch (IllegalArgumentException e) {
            return new CallStateMachine();
        }
        return m;
    }
}
