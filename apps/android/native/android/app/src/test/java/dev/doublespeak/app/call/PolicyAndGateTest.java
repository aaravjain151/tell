package dev.doublespeak.app.call;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.util.Arrays;
import java.util.Collections;

import org.junit.Test;

public class PolicyAndGateTest {
    @Test public void startPathPerAndroidVersion() {
        for (int sdk = 22; sdk <= 29; sdk++) assertEquals(StartPolicy.Path.DIRECT, StartPolicy.decide(sdk, false));
        for (int sdk = 30; sdk <= 35; sdk++) assertEquals("sdk " + sdk, StartPolicy.Path.TAP, StartPolicy.decide(sdk, false));
        for (int sdk = 22; sdk <= 35; sdk++) assertEquals(StartPolicy.Path.DIRECT, StartPolicy.decide(sdk, true));
        assertEquals(StartPolicy.Path.TAP, StartPolicy.afterDirectFailed());
    }

    @Test public void permissionsAllGranted() {
        assertTrue(PermissionGate.missing(true, true, true).isEmpty());
        assertEquals("", PermissionGate.explain(Collections.<String>emptyList()));
    }

    @Test public void phoneDeniedExplainsWhy() {
        assertEquals(Arrays.asList("phone"), PermissionGate.missing(false, true, true));
        String m = PermissionGate.explain(PermissionGate.missing(false, true, true));
        assertTrue(m.startsWith("Auto-listen stays off"));
        assertTrue(m.contains("Phone permission"));
        assertTrue(m.contains("never reads numbers"));
    }

    @Test public void micAndNotificationsDenied() {
        assertTrue(PermissionGate.explain(PermissionGate.missing(true, false, true)).contains("microphone"));
        assertTrue(PermissionGate.explain(PermissionGate.missing(true, true, false)).contains("notifications"));
        assertEquals(Arrays.asList("phone", "microphone", "notifications"), PermissionGate.missing(false, false, false));
    }

    @Test public void consentWordingIsExact() {
        assertEquals("When you answer a call, Tell listens through your microphone in speaker mode and sends the audio only to your own computer over the USB cable. Nothing is recorded or stored. Tell the other person if your state requires it.", Wording.CONSENT);
        assertEquals("Tell could not reach your computer; plug in the USB cable.", Wording.NOT_CONNECTED_TEXT);
        assertEquals("Tell is listening to this call", Wording.LISTENING_TITLE);
    }

    @Test public void micBlockedWordingIsHonestAndDistinctFromTheCableMessage() {
        assertEquals("Your phone is blocking the microphone during the call. On this phone, apps can't hear a call even on speaker.", Wording.MIC_BLOCKED_TEXT);
        assertEquals("Use Tell on your Mac for live calls (answer the call on your Mac).", Wording.MIC_BLOCKED_SUB);
        // the silenced-mic message must never blame the cable, and the cable message must never claim the mic is blocked
        assertFalse(Wording.MIC_BLOCKED_TEXT.toLowerCase().contains("cable"));
        assertFalse(Wording.NOT_CONNECTED_TEXT.toLowerCase().contains("microphone"));
        assertFalse(Wording.LOST_TEXT.toLowerCase().contains("microphone"));
        assertEquals(Wording.MIC_BLOCKED_TEXT, CallSession.textFor(CallSession.Outcome.MIC_SILENCED));
        assertEquals(Wording.LOST_TEXT, CallSession.textFor(CallSession.Outcome.LOST));
        assertEquals("Listening stopped.", CallSession.textFor(CallSession.Outcome.DROPPED));
    }

    @Test public void silenceWatchFiresOnceAfterEightSeconds() {
        SilenceWatch w = new SilenceWatch();
        assertFalse(w.feed(0.0005, 1000));
        assertFalse(w.feed(0.0005, 7900));
        assertTrue(w.feed(0.0005, 8000));
        assertFalse(w.feed(0.0005, 9000));
        SilenceWatch loud = new SilenceWatch();
        loud.feed(0.05, 100);
        assertFalse(loud.feed(0.0, 9000));
    }

    @Test public void rmsOfFullScaleSquare() {
        short[] s = {32767, -32768, 32767, -32768};
        assertEquals(1.0, SilenceWatch.rms(s, 4), 0.001);
        assertEquals(0.0, SilenceWatch.rms(s, 0), 0.0);
    }
}
