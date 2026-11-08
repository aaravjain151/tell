package dev.doublespeak.app.call;

import static dev.doublespeak.app.call.CallStateMachine.Action.NONE;
import static dev.doublespeak.app.call.CallStateMachine.Action.START;
import static dev.doublespeak.app.call.CallStateMachine.Action.STOP;
import static dev.doublespeak.app.call.CallStateMachine.Phone.IDLE;
import static dev.doublespeak.app.call.CallStateMachine.Phone.OFFHOOK;
import static dev.doublespeak.app.call.CallStateMachine.Phone.RINGING;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class CallStateMachineTest {
    private final CallStateMachine m = new CallStateMachine();

    @Test public void answeredCallStartsThenStopsOnIdle() {
        assertEquals(NONE, m.onPhoneState(RINGING, true));
        assertEquals(START, m.onPhoneState(OFFHOOK, true));
        assertTrue(m.isListening());
        assertEquals(STOP, m.onPhoneState(IDLE, true));
        assertFalse(m.isListening());
        assertFalse(m.inCall());
    }

    @Test public void settingOffNeverStarts() {
        assertEquals(NONE, m.onPhoneState(RINGING, false));
        assertEquals(NONE, m.onPhoneState(OFFHOOK, false));
        assertEquals(NONE, m.onPhoneState(IDLE, false));
    }

    @Test public void missedCallDoesNothing() {
        assertEquals(NONE, m.onPhoneState(RINGING, true));
        assertEquals(NONE, m.onPhoneState(IDLE, true));
        assertFalse(m.isListening());
        // and the next answered call still starts
        m.onPhoneState(RINGING, true);
        assertEquals(START, m.onPhoneState(OFFHOOK, true));
    }

    @Test public void outgoingCallDoesNotStart() {
        assertEquals(NONE, m.onPhoneState(OFFHOOK, true));
        assertEquals(NONE, m.onPhoneState(IDLE, true));
    }

    @Test public void callWaitingKeepsOneSession() {
        m.onPhoneState(RINGING, true);
        assertEquals(START, m.onPhoneState(OFFHOOK, true));
        assertEquals(NONE, m.onPhoneState(RINGING, true));     // second call rings during the first
        assertEquals(NONE, m.onPhoneState(OFFHOOK, true));     // answered (first on hold) or rejected: same session
        assertTrue(m.isListening());
        assertEquals(STOP, m.onPhoneState(IDLE, true));        // only when every call ended
    }

    @Test public void twoCallsInARowEachStart() {
        m.onPhoneState(RINGING, true);
        assertEquals(START, m.onPhoneState(OFFHOOK, true));
        assertEquals(STOP, m.onPhoneState(IDLE, true));
        m.onPhoneState(RINGING, true);
        assertEquals(START, m.onPhoneState(OFFHOOK, true));
        assertEquals(STOP, m.onPhoneState(IDLE, true));
    }

    @Test public void outgoingThenCallWaitingAnsweredStarts() {
        assertEquals(NONE, m.onPhoneState(OFFHOOK, true));
        assertEquals(NONE, m.onPhoneState(RINGING, true));
        assertEquals(START, m.onPhoneState(OFFHOOK, true));
    }

    @Test public void duplicateStatesAreIgnored() {
        m.onPhoneState(RINGING, true);
        assertEquals(NONE, m.onPhoneState(RINGING, true));
        assertEquals(START, m.onPhoneState(OFFHOOK, true));
        assertEquals(NONE, m.onPhoneState(OFFHOOK, true));     // receiver + TelephonyCallback both deliver it
        assertEquals(STOP, m.onPhoneState(IDLE, true));
        assertEquals(NONE, m.onPhoneState(IDLE, true));
    }

    @Test public void userStopIsNotUndoneByCallWaiting() {
        m.onPhoneState(RINGING, true);
        m.onPhoneState(OFFHOOK, true);
        assertEquals(STOP, m.onUserStop());
        assertEquals(NONE, m.onPhoneState(RINGING, true));
        assertEquals(NONE, m.onPhoneState(OFFHOOK, true));
        assertEquals(NONE, m.onPhoneState(IDLE, true));        // already stopped
        m.onPhoneState(RINGING, true);
        assertEquals(START, m.onPhoneState(OFFHOOK, true));    // a new call starts again
    }

    @Test public void turningSettingOffMidCallStops() {
        m.onPhoneState(RINGING, true);
        m.onPhoneState(OFFHOOK, true);
        assertEquals(STOP, m.onSettingChanged(false));
        assertEquals(NONE, m.onPhoneState(IDLE, false));
    }

    @Test public void turningSettingOnMidCallDoesNotStart() {
        m.onPhoneState(RINGING, false);
        m.onPhoneState(OFFHOOK, false);
        assertEquals(NONE, m.onSettingChanged(true));
        assertEquals(NONE, m.onPhoneState(RINGING, true));     // call waiting...
        assertEquals(START, m.onPhoneState(OFFHOOK, true));    // ...answered with the setting now on: starts
    }

    @Test public void sessionEndedByItselfDoesNotRestartInSameCall() {
        m.onPhoneState(RINGING, true);
        m.onPhoneState(OFFHOOK, true);
        m.onSessionEnded();                                     // e.g. computer not connected
        assertEquals(NONE, m.onPhoneState(RINGING, true));
        assertEquals(NONE, m.onPhoneState(OFFHOOK, true));
        assertEquals(NONE, m.onPhoneState(IDLE, true));
    }

    @Test public void snapshotSurvivesProcessRestartBetweenRingAndAnswer() {
        m.onPhoneState(RINGING, true);
        CallStateMachine again = CallStateMachine.restore(m.snapshot());
        assertEquals(START, again.onPhoneState(OFFHOOK, true));
        assertEquals(STOP, CallStateMachine.restore(again.snapshot()).onPhoneState(IDLE, true));
    }

    @Test public void garbageSnapshotGivesFreshMachine() {
        assertEquals(IDLE, CallStateMachine.restore("nonsense").last());
        assertEquals(IDLE, CallStateMachine.restore("X,1,1,1,1").last());
        assertEquals(IDLE, CallStateMachine.restore(null).last());
    }

    @Test public void nullStateIgnored() {
        assertEquals(NONE, m.onPhoneState(null, true));
    }
}
