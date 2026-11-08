import XCTest
@testable import Doublespeak

final class FakeCalls: CallObserving {
    var hasActiveCall = false
    var onChange: ((Bool) -> Void)?
    var started = false
    func start() { started = true }
    func set(_ active: Bool) { hasActiveCall = active; onChange?(active) }
}

final class CallBannerTests: XCTestCase {
    func testMapping() {
        XCTAssertNil(CallBanner.current(callActive: false, listening: false, interrupted: false))
        XCTAssertNil(CallBanner.current(callActive: false, listening: true, interrupted: false))
        XCTAssertEqual(CallBanner.current(callActive: true, listening: false, interrupted: false), .inCall)
        XCTAssertEqual(CallBanner.current(callActive: true, listening: true, interrupted: false), .interrupted)
        XCTAssertEqual(CallBanner.current(callActive: false, listening: true, interrupted: true), .interrupted)
    }

    func testFixedHonestWording() {
        XCTAssertEqual(CallBanner.inCall.title, "A phone call is using the microphone")
        XCTAssertTrue(CallBanner.inCall.body.contains("iOS does not let apps listen during a call"))
        XCTAssertTrue(CallBanner.inCall.body.contains("another device"))
        XCTAssertTrue(CallBanner.inCall.body.contains("Calls on Other Devices"))
        XCTAssertEqual(CallBanner.interrupted.title, "The call interrupted the microphone")
        XCTAssertTrue(CallBanner.interrupted.body.contains("try again when the call ends"))
    }
}

@MainActor
final class CallStateControllerTests: XCTestCase {
    private func make(call: Bool = false) -> (ListenController, FakeCalls) {
        let f = FakeCalls(); f.hasActiveCall = call
        let c = ListenController(callObserver: f)
        c.consentAccepted = true
        c.observeCalls()
        return (c, f)
    }

    func testCallActiveAtLaunchBlocksStartAndShowsBanner() {
        let (c, f) = make(call: true)
        XCTAssertTrue(f.started)
        c._setMode(.idle)
        XCTAssertTrue(c.callActive)
        XCTAssertEqual(c.callBanner, .inCall)
        c.startTapped()
        XCTAssertEqual(c.mode, .idle, "Start must do nothing during a call")
        XCTAssertNil(c.notice)
        XCTAssertNil(c.sheet)
    }

    func testBannerClearsWhenTheCallEnds() {
        let (c, f) = make()
        c._setMode(.idle)
        XCTAssertNil(c.callBanner)
        f.set(true)
        let e1 = expectation(description: "banner")
        DispatchQueue.main.async { XCTAssertEqual(c.callBanner, .inCall); e1.fulfill() }
        wait(for: [e1], timeout: 2)
        f.set(false)
        let e2 = expectation(description: "cleared")
        DispatchQueue.main.async { XCTAssertNil(c.callBanner); XCTAssertFalse(c.callActive); e2.fulfill() }
        wait(for: [e2], timeout: 2)
    }

    func testCallStartingWhileListeningShowsInterruptedThenClears() {
        let (c, f) = make()
        c._setMode(.listening)
        f.set(true)
        let e1 = expectation(description: "interrupted")
        DispatchQueue.main.async { XCTAssertEqual(c.callBanner, .interrupted); e1.fulfill() }
        wait(for: [e1], timeout: 2)
        f.set(false)                                   // call ended: a safe resume is attempted (no capture running in tests)
        let e2 = expectation(description: "clear")
        DispatchQueue.main.async { XCTAssertNil(c.callBanner); XCTAssertEqual(c.mode, .listening); e2.fulfill() }
        wait(for: [e2], timeout: 2)
    }
}
