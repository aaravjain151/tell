package dev.doublespeak.app.call;

/** Fixed user-facing strings for auto-listen, in one place so the tests and the docs can check them. */
public final class Wording {
    private Wording() {}

    public static final String CONSENT = "When you answer a call, Tell listens through your microphone in speaker mode and sends the audio only to your own computer over the USB cable. Nothing is recorded or stored. Tell the other person if your state requires it.";

    public static final String LISTENING_TITLE = "Tell is listening to this call";
    public static final String LISTENING_TEXT = "Speaker mode. Audio goes only to your computer over USB. Nothing is saved.";
    public static final String SILENT_TEXT = "No sound is reaching the microphone. Is the call on speaker? Android may be silencing the microphone during calls.";

    public static final String PROMPT_TITLE = "Call answered";
    public static final String PROMPT_TEXT = "Tap Listen to let Tell listen. Put the call on speaker first.";

    public static final String NOT_CONNECTED_TITLE = "Tell is not listening";
    public static final String NOT_CONNECTED_TEXT = "Tell could not reach your computer; plug in the USB cable.";
    public static final String REFUSED_TEXT = "Your computer refused Tell. Start the engine with make api-android.";
    public static final String BUSY_TEXT = "Another listening session is open on your computer.";
    public static final String LOST_TEXT = "Lost contact with your computer. Check the USB cable.";
    public static final String DROPPED_TEXT = "Listening stopped.";
    public static final String MIC_TEXT = "Tell could not open the microphone.";

    // The OS silenced the microphone during the call (verified on the Galaxy S20 FE / Android 13). Engine and cable are fine.
    public static final String MIC_BLOCKED_TITLE = "Tell can't hear this call";
    public static final String MIC_BLOCKED_TEXT = "Your phone is blocking the microphone during the call. On this phone, apps can't hear a call even on speaker.";
    public static final String MIC_BLOCKED_SUB = "Use Tell on your Mac for live calls (answer the call on your Mac).";

    public static final String ACTION_STOP = "Stop";
    public static final String ACTION_LISTEN = "Listen";
    public static final String ACTION_SPEAKER = "Turn on speaker";
}
