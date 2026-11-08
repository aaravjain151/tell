package dev.doublespeak.app.call;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

import org.junit.Test;

public class CallSessionTest {
    static final class FakeLink implements CallSession.Link {
        int audioFrames, pings; boolean closed; int failAfter = -1; long bytes;
        CallSession.LinkListener l;
        @Override public void sendAudio(byte[] pcm, int len) throws IOException {
            if (failAfter >= 0 && audioFrames >= failAfter) throw new IOException("broken pipe");
            audioFrames++; bytes += len;
        }
        @Override public void sendText(String json) { if (json.contains("ping")) pings++; }
        @Override public void close() { closed = true; }
    }

    static final class FakeEngine implements CallSession.Engine {
        final FakeLink link = new FakeLink(); CallSession.EngineError err; boolean reachable;
        @Override public CallSession.Link open(CallSession.LinkListener l) throws CallSession.EngineError {
            if (err != null) throw err;
            link.l = l; return link;
        }
        @Override public boolean reachable() { return reachable; }
    }

    /** Each read returns one 100 ms frame and advances the fake clock by 100 ms; stops the session after maxFrames.
        value is the constant sample (3000 = audible, 0 = digital silence); failAt makes a read return -1. */
    static final class FakeMic implements CallSession.Mic {
        boolean startOk = true, released; short value = 3000; int reads, maxFrames = 50, failAt = -1;
        CallSession session; long[] clock; Runnable onRead;
        @Override public boolean start() { return startOk; }
        @Override public int read(short[] buf) {
            if (reads == failAt) return -1;
            java.util.Arrays.fill(buf, value);
            reads++; clock[0] += 100;
            if (onRead != null) onRead.run();
            if (reads >= maxFrames) session.requestStop();
            return buf.length;
        }
        @Override public void release() { released = true; }
    }

    static final class Ui implements CallSession.Ui {
        final List<String> log = new ArrayList<>(); String endedText;
        @Override public void onListening() { log.add("listening"); }
        @Override public void onLevel(double rms) {}
        @Override public void onSilent() { log.add("silent"); }
        @Override public void onVerdict(String json) { log.add("verdict"); }
        @Override public void onEnded(CallSession.Outcome o, String text) { log.add("ended:" + o); endedText = text; }
    }

    private final long[] clock = {0};
    private final FakeEngine engine = new FakeEngine();
    private final FakeMic mic = new FakeMic();
    private final Ui ui = new Ui();
    private final CallSession s = new CallSession(engine, mic, () -> clock[0], ui);
    { mic.session = s; mic.clock = clock; }

    @Test public void streamsFramesPingsAndStopsCleanly() {
        mic.value = 3000;
        mic.maxFrames = 250;                                       // 25 s of fake audio
        assertEquals(CallSession.Outcome.STOPPED, s.run());
        assertEquals(250, engine.link.audioFrames);
        assertEquals(250L * 3200, engine.link.bytes);             // 1600 samples * 2 bytes per 100 ms
        assertEquals(2, engine.link.pings);                        // every 10 s
        assertTrue(engine.link.closed);
        assertTrue(mic.released);
        assertEquals("listening", ui.log.get(0));
        assertEquals("ended:STOPPED", ui.log.get(ui.log.size() - 1));
        assertTrue(!ui.log.contains("silent"));
    }

    @Test public void notConnectedShowsTheCableNoticeAndNeverOpensTheMic() {
        engine.err = new CallSession.EngineError(CallSession.Outcome.NOT_CONNECTED, "ConnectException");
        mic.startOk = true;
        assertEquals(CallSession.Outcome.NOT_CONNECTED, s.run());
        assertEquals("Tell could not reach your computer; plug in the USB cable.", ui.endedText);
        assertEquals(0, mic.reads);
        assertEquals(1, ui.log.size());
    }

    @Test public void refusedAndBusyHaveTheirOwnWords() {
        engine.err = new CallSession.EngineError(CallSession.Outcome.REFUSED, "403");
        s.run();
        assertTrue(ui.endedText.contains("make api-android"));
        assertEquals(Wording.BUSY_TEXT, CallSession.textFor(CallSession.Outcome.BUSY));
    }

    @Test public void micFailureClosesTheLink() {
        mic.startOk = false;
        assertEquals(CallSession.Outcome.MIC_FAILED, s.run());
        assertTrue(engine.link.closed);
        assertTrue(mic.released);
    }

    @Test public void cablePulledMidCallWithEngineGoneIsLost() {
        engine.link.failAfter = 20;
        engine.reachable = false;                 // /health also fails: it really is the cable
        assertEquals(CallSession.Outcome.LOST, s.run());
        assertEquals(Wording.LOST_TEXT, ui.endedText);
        assertTrue(mic.released);
    }

    @Test public void sendFailsButEngineStillReachableIsDroppedNotCable() {
        engine.link.failAfter = 20;
        engine.reachable = true;                  // /health answers: do NOT blame the USB cable
        assertEquals(CallSession.Outcome.DROPPED, s.run());
        assertEquals(Wording.DROPPED_TEXT, ui.endedText);
    }

    @Test public void serverClosingProbesHealth() {
        engine.reachable = false;
        mic.onRead = () -> { if (mic.reads == 10) engine.link.l.onServerClosed("heartbeat_timeout"); };
        assertEquals(CallSession.Outcome.LOST, s.run());
    }

    @Test public void serverClosingWithEngineUpIsDropped() {
        engine.reachable = true;
        mic.onRead = () -> { if (mic.reads == 10) engine.link.l.onServerClosed("disconnect"); };
        assertEquals(CallSession.Outcome.DROPPED, s.run());
    }

    @Test public void serverFinalIsAStop() {
        mic.onRead = () -> { if (mic.reads == 10) engine.link.l.onServerClosed("final"); };
        assertEquals(CallSession.Outcome.STOPPED, s.run());
    }

    @Test public void silencedMicDuringCallStopsCleanlyWithTheHonestMessage() {
        mic.value = 0;                             // the OS gives the mic only digital silence (S20 FE during a call)
        mic.maxFrames = 300;
        assertEquals(CallSession.Outcome.MIC_SILENCED, s.run());
        assertEquals(Wording.MIC_BLOCKED_TEXT, ui.endedText);
        assertTrue(ui.endedText.contains("blocking the microphone"));
        assertTrue(clock[0] <= CallSession.BLOCKED_SILENCE_MS + 200);   // stops at ~4 s, does not spin to 300 frames
        assertTrue(mic.released);
        assertTrue(engine.link.closed);
    }

    @Test public void audioRecordReturningMinusOneAfterStartIsSilencedNotFailed() {
        mic.failAt = 5;                            // AudioRecord read() returns -1 after a good start = OS silenced it
        assertEquals(CallSession.Outcome.MIC_SILENCED, s.run());
        assertEquals(Wording.MIC_BLOCKED_TEXT, ui.endedText);
    }

    @Test public void micThatNeverStartsIsFailedNotSilenced() {
        mic.startOk = false;
        assertEquals(CallSession.Outcome.MIC_FAILED, s.run());
        assertEquals(Wording.MIC_TEXT, ui.endedText);
    }

    @Test public void audibleAudioIsNeverCalledSilenced() {
        mic.value = 3000;                          // real sound: must run to the end as STOPPED
        mic.maxFrames = 100;                       // 10 s, well past the 4 s silence window
        assertEquals(CallSession.Outcome.STOPPED, s.run());
        assertEquals(100, engine.link.audioFrames);
    }

    @Test public void stopBeforeMicOpensClosesLink() {
        s.requestStop();
        assertEquals(CallSession.Outcome.STOPPED, s.run());
        assertTrue(engine.link.closed);
        assertEquals(0, mic.reads);
    }

    @Test public void verdictsAreForwardedOthersIgnored() {
        mic.onRead = () -> { if (mic.reads == 2) { engine.link.l.onServerMessage("verdict", "{}"); engine.link.l.onServerMessage("pong", "{}"); } };
        s.run();
        assertEquals(1, ui.log.stream().filter("verdict"::equals).count());
    }
}
