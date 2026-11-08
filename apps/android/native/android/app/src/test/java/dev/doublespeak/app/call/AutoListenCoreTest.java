package dev.doublespeak.app.call;

import static dev.doublespeak.app.call.CallStateMachine.Phone.IDLE;
import static dev.doublespeak.app.call.CallStateMachine.Phone.OFFHOOK;
import static dev.doublespeak.app.call.CallStateMachine.Phone.RINGING;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.junit.Test;

public class AutoListenCoreTest {
    static final class Fx implements AutoListenCore.Effects {
        final List<String> log = new ArrayList<>();
        boolean directAllowed = true;
        @Override public boolean startDirect() { log.add("direct" + (directAllowed ? "" : "-refused")); return directAllowed; }
        @Override public void postPrompt() { log.add("prompt"); }
        @Override public void cancelPrompt() { log.add("cancel"); }
        @Override public void stopListening() { log.add("stop"); }
    }

    static final class Env implements AutoListenCore.Env {
        boolean enabled = true, perms = true, resumed = false, page = false;
        int sdk = 33;
        @Override public boolean enabled() { return enabled; }
        @Override public boolean permissionsOk() { return perms; }
        @Override public int sdk() { return sdk; }
        @Override public boolean appResumed() { return resumed; }
        @Override public boolean pageListening() { return page; }
    }

    private final Fx fx = new Fx();
    private final Env env = new Env();
    private final AutoListenCore core = new AutoListenCore(new CallStateMachine(), fx);

    private AutoListenCore.Result answer() {
        core.onPhoneState(RINGING, env);
        return core.onPhoneState(OFFHOOK, env);
    }

    @Test public void android13InBackgroundPromptsForATap() {
        assertEquals(AutoListenCore.Result.PROMPTED, answer());
        assertEquals(Arrays.asList("prompt"), fx.log);
        assertEquals(AutoListenCore.Result.STOPPED, core.onPhoneState(IDLE, env));
        assertEquals(Arrays.asList("prompt", "stop"), fx.log);
    }

    @Test public void android13WithTellOnScreenStartsDirectly() {
        env.resumed = true;
        assertEquals(AutoListenCore.Result.STARTED_DIRECT, answer());
        assertEquals(Arrays.asList("direct"), fx.log);
    }

    @Test public void android10InBackgroundStartsDirectly() {
        env.sdk = 29;
        assertEquals(AutoListenCore.Result.STARTED_DIRECT, answer());
    }

    @Test public void android11And14InBackgroundPrompt() {
        env.sdk = 30;
        assertEquals(AutoListenCore.Result.PROMPTED, answer());
        core.onPhoneState(IDLE, env);
        env.sdk = 34;
        assertEquals(AutoListenCore.Result.PROMPTED, answer());
    }

    @Test public void refusedDirectStartFallsBackToPrompt() {
        env.resumed = true;
        fx.directAllowed = false;            // ForegroundServiceStartNotAllowedException
        assertEquals(AutoListenCore.Result.PROMPTED, answer());
        assertEquals(Arrays.asList("direct-refused", "prompt"), fx.log);
    }

    @Test public void settingOffNeverStartsOrPrompts() {
        env.enabled = false;
        assertEquals(AutoListenCore.Result.SKIPPED_OFF, answer());
        core.onPhoneState(IDLE, env);
        assertFalse(fx.log.contains("prompt"));
        assertFalse(fx.log.contains("direct"));
    }

    @Test public void phonePermissionRevokedNeverStarts() {
        env.perms = false;
        assertEquals(AutoListenCore.Result.SKIPPED_OFF, answer());
        assertFalse(fx.log.contains("prompt"));
    }

    @Test public void pageAlreadyListeningIsNotDoubled() {
        env.page = true;
        assertEquals(AutoListenCore.Result.SKIPPED_PAGE, answer());
        assertTrue(fx.log.isEmpty());
        assertEquals(AutoListenCore.Result.NONE, core.onPhoneState(IDLE, env));   // nothing of ours to stop
    }

    @Test public void missedCallCancelsAnyPromptAndStartsNothing() {
        core.onPhoneState(RINGING, env);
        core.onPhoneState(IDLE, env);
        assertEquals(Arrays.asList("cancel"), fx.log);
    }

    @Test public void userStopStopsAndCallWaitingDoesNotRestart() {
        answer();
        core.onUserStop();
        core.onPhoneState(RINGING, env);
        assertEquals(AutoListenCore.Result.NONE, core.onPhoneState(OFFHOOK, env));
        assertEquals(Arrays.asList("prompt", "stop"), fx.log);
    }

    @Test public void turningOffMidCallStopsAndCancelsPrompt() {
        answer();
        core.onSettingChanged(false);
        assertEquals(Arrays.asList("prompt", "stop", "cancel"), fx.log);
    }
}
