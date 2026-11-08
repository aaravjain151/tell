package dev.doublespeak.app.call;

import static org.junit.Assert.assertEquals;
import static org.junit.Assume.assumeTrue;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.junit.Test;

/**
 * Opt-in: the real engine on this computer. Skipped unless TELL_ENGINE_PORT is set, e.g.
 *   cd services/api && TELL_CORS_ORIGINS=http://localhost ../../.venv/bin/python -m uvicorn tell.main:app --port 8077
 *   TELL_ENGINE_PORT=8077 ./gradlew testDebugUnitTest --tests '*RealEngineIT*'
 * Streams 12 s of a quiet tone through CallSession + LoopbackEngine and expects a clean STOPPED.
 */
public class RealEngineIT {
    @Test public void streamsToTheRealEngine() {
        String p = System.getenv("TELL_ENGINE_PORT");
        assumeTrue("TELL_ENGINE_PORT not set", p != null && !p.isEmpty());
        final long[] clock = {0};
        final List<String> log = Collections.synchronizedList(new ArrayList<>());
        final CallSession[] s = new CallSession[1];
        CallSession.Mic mic = new CallSession.Mic() {
            int reads;
            @Override public boolean start() { return true; }
            @Override public int read(short[] buf) {
                for (int i = 0; i < buf.length; i++) buf[i] = (short) (3000 * Math.sin(2 * Math.PI * 220 * (reads * buf.length + i) / 16000.0));
                reads++; clock[0] += 100;
                try { Thread.sleep(100); } catch (InterruptedException e) { return -1; }
                if (reads >= 120) s[0].requestStop();
                return buf.length;
            }
            @Override public void release() {}
        };
        s[0] = new CallSession(new LoopbackEngine(Integer.parseInt(p), 1500), mic, () -> clock[0], new CallSession.Ui() {
            @Override public void onListening() { log.add("listening"); }
            @Override public void onLevel(double rms) {}
            @Override public void onSilent() { log.add("silent"); }
            @Override public void onVerdict(String json) { log.add("verdict"); }
            @Override public void onEnded(CallSession.Outcome o, String text) { log.add("ended:" + o); }
        });
        CallSession.Outcome o = s[0].run();
        System.out.println("RealEngineIT log: " + log);
        assertEquals(CallSession.Outcome.STOPPED, o);
    }
}
