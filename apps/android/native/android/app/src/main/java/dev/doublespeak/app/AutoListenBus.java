package dev.doublespeak.app;

/** Tells the page (through ListenServicePlugin) what auto-listen is doing. Carries states only: no audio, no text from the call. */
final class AutoListenBus {
    interface Listener { void onEvent(String kind, String state, double level); }

    private static volatile Listener listener;
    static volatile String state = "idle";   // idle | starting | listening | silent | ended

    private AutoListenBus() {}

    static void set(Listener l) { listener = l; }

    static void emit(String kind, String s, double level) {
        if ("state".equals(kind)) state = s;
        Listener l = listener;
        if (l != null) try { l.onEvent(kind, s, level); } catch (RuntimeException ignored) {}
    }
}
