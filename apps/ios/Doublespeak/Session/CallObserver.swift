import CallKit
import Foundation

/// Whether a phone call is active on THIS iPhone. CallKit's CXCallObserver reports only that: it gives no audio, no
/// numbers shown here, and needs no entitlement. iOS will not let a third-party app start (or keep) the microphone
/// during a call, so the app says so plainly instead of failing with a vague error.
protocol CallObserving: AnyObject {
    var hasActiveCall: Bool { get }
    var onChange: ((Bool) -> Void)? { get set }
    func start()
}

final class SystemCallObserver: NSObject, CallObserving, CXCallObserverDelegate {
    var onChange: ((Bool) -> Void)?
    private let observer = CXCallObserver()

    var hasActiveCall: Bool { observer.calls.contains { !$0.hasEnded } }

    func start() { observer.setDelegate(self, queue: .main) }

    func callObserver(_ callObserver: CXCallObserver, callChanged call: CXCall) {
        onChange?(hasActiveCall)
    }
}

/// Fixed wording for the call states (no caller text, nothing about who is calling).
enum CallBanner: Equatable {
    case inCall                 // idle/ended, a call is active: Start is off
    case interrupted            // listening was running and the call took the microphone

    var title: String {
        switch self {
        case .inCall: return "A phone call is using the microphone"
        case .interrupted: return "The call interrupted the microphone"
        }
    }

    var body: String {
        switch self {
        case .inCall:
            return "iOS does not let apps listen during a call. Listen to a call on another device, or use the Mac (Calls on Other Devices)."
        case .interrupted:
            return "Doublespeak will try again when the call ends. Nothing is being heard right now."
        }
    }

    static func current(callActive: Bool, listening: Bool, interrupted: Bool) -> CallBanner? {
        if listening && (interrupted || callActive) { return .interrupted }
        if !listening && callActive { return .inCall }
        return nil
    }
}
