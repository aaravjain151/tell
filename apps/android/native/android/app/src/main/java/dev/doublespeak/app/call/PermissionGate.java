package dev.doublespeak.app.call;

import java.util.ArrayList;
import java.util.List;

/**
 * What auto-listen needs before the setting may be on (pure, unit-tested).
 *  - phone (READ_PHONE_STATE): to learn that a call was answered and when it ended. Never used for numbers.
 *  - microphone (RECORD_AUDIO): to listen; Android 14 also refuses a microphone service without it.
 *  - notifications (POST_NOTIFICATIONS, runtime permission from Android 13): the listening notification with Stop,
 *    the tap-to-listen prompt (the only start path in the background from Android 11) and the "could not reach your
 *    computer" notice. Below Android 13 it is not a runtime permission; the caller passes whether notifications are
 *    enabled for the app.
 */
public final class PermissionGate {
    public static final String PHONE = "phone", MICROPHONE = "microphone", NOTIFICATIONS = "notifications";

    private PermissionGate() {}

    public static List<String> missing(boolean phone, boolean mic, boolean notifications) {
        List<String> m = new ArrayList<>();
        if (!phone) m.add(PHONE);
        if (!mic) m.add(MICROPHONE);
        if (!notifications) m.add(NOTIFICATIONS);
        return m;
    }

    /** Fixed wording shown when a permission was refused; the setting stays off. */
    public static String explain(List<String> missing) {
        if (missing.isEmpty()) return "";
        String first = missing.get(0);
        if (PHONE.equals(first))
            return "Auto-listen stays off: Tell needs the Phone permission to know when you answer a call and when it ends. It never reads numbers or contacts.";
        if (MICROPHONE.equals(first))
            return "Auto-listen stays off: Tell needs the microphone to listen to the call on speakerphone.";
        return "Auto-listen stays off: Tell needs notifications to show that it is listening and to give you a Stop button.";
    }
}
