import XCTest
@testable import Doublespeak

final class FakeBackend: CaptureBackend {
    var failActivate = false, failStart = false, rate = 48_000.0
    var installs = 0, removes = 0, activations = 0, deactivations = 0, starts = 0, stops = 0
    var running = false
    var tap: (([Float]) -> Void)?

    func activateSession() throws { activations += 1; if failActivate { throw NSError(domain: "t", code: 1) } }
    func deactivateSession() { deactivations += 1 }
    func inputFormat() -> (sampleRate: Double, channels: Int) { (rate, 1) }
    func installTap(_ block: @escaping ([Float]) -> Void) { installs += 1; tap = block }
    func removeTap() { removes += 1; tap = nil }
    func startEngine() throws { starts += 1; if failStart { throw NSError(domain: "t", code: 2) }; running = true }
    func stopEngine() { stops += 1; running = false }
    var engineRunning: Bool { running }
    var tapsLive: Int { installs - removes }
}

final class MicCaptureRollbackTests: XCTestCase {
    func testFailedEngineStartRollsBackTapAndSession() {
        let b = FakeBackend(); b.failStart = true
        let m = MicCapture(backend: b)
        XCTAssertThrowsError(try m.start())
        XCTAssertFalse(m.running)
        XCTAssertFalse(m.tapInstalled)
        XCTAssertFalse(m.sessionActive)
        XCTAssertEqual(b.tapsLive, 0, "a failed start must not leave a tap")
        XCTAssertEqual(b.deactivations, 1)
    }

    func testRetryAfterFailureInstallsExactlyOneTap() throws {
        let b = FakeBackend(); b.failStart = true
        let m = MicCapture(backend: b)
        XCTAssertThrowsError(try m.start())
        b.failStart = false
        try m.start()
        XCTAssertTrue(m.running)
        XCTAssertEqual(b.tapsLive, 1)
        try m.start()                                           // already running: no second tap
        XCTAssertEqual(b.tapsLive, 1)
        m.stop()
        XCTAssertEqual(b.tapsLive, 0)
        XCTAssertFalse(m.sessionActive)
    }

    func testFailedSessionActivationInstallsNothing() {
        let b = FakeBackend(); b.failActivate = true
        let m = MicCapture(backend: b)
        XCTAssertThrowsError(try m.start())
        XCTAssertEqual(b.installs, 0)
        XCTAssertEqual(b.deactivations, 0)
    }

    func testNoInputFormatRollsBack() {
        let b = FakeBackend(); b.rate = 0
        let m = MicCapture(backend: b)
        XCTAssertThrowsError(try m.start())
        XCTAssertEqual(b.tapsLive, 0)
        XCTAssertEqual(b.deactivations, 1)
    }

    func testFramesFlowAndStopWipesThePartialFrame() throws {
        let b = FakeBackend()
        let m = MicCapture(backend: b)
        var frames = 0
        m.onFrame = { _ in frames += 1 }
        try m.start()
        b.tap?([Float](repeating: 0.1, count: 4_800))           // exactly one 100 ms frame at 48 kHz
        b.tap?([Float](repeating: 0.1, count: 2_400))           // half a frame, buffered
        XCTAssertEqual(frames, 1)
        m.stop()
        try m.start()
        b.tap?([Float](repeating: 0.1, count: 2_400))           // the old half frame must not complete this one
        XCTAssertEqual(frames, 1)
        m.stop()
    }

    func testStopIsSafeInAnyState() {
        let m = MicCapture(backend: FakeBackend())
        m.stop(); m.stop()
        XCTAssertFalse(m.running)
    }
}

@MainActor
final class ServerEndedTests: XCTestCase {
    private func listening() -> ListenController {
        let c = ListenController(callObserver: FakeCalls())
        c.consentAccepted = true
        c._setMode(.listening)
        return c
    }

    func testServerEndStopsListeningWithAClearMessage() {
        for reason in ["panic", "deleted", "max_length", "engine_closed", "bridge stopped"] {
            let c = listening()
            c.inbound(.ended(reason: reason))
            XCTAssertEqual(c.mode, .ended, reason)
            XCTAssertEqual(c.notice?.title, "Listening stopped on your computer")
            XCTAssertFalse(c.notice?.body.isEmpty ?? true)
            XCTAssertFalse(c.showAlert)
        }
    }

    func testEndedWhileIdleChangesNothing() {
        let c = ListenController(callObserver: FakeCalls())
        c._setMode(.idle)
        c.inbound(.ended(reason: "panic"))
        XCTAssertEqual(c.mode, .idle)
        XCTAssertNil(c.notice)
    }

    func testProtocolParsesEnded() {
        XCTAssertEqual(Protocol.parse("{\"type\":\"ended\",\"reason\":\"panic\",\"detail\":\"x\"}"), .ended(reason: "panic"))
    }
}
