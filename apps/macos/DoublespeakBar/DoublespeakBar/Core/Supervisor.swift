import Foundation

/// Everything needed to start one child. Absolute paths only; no shell.
struct LaunchSpec: Equatable {
    var name: String
    var executable: String
    var arguments: [String]
    var cwd: String
    var environment: [String: String]
    /// Graceful stop signal. The listener uses SIGINT so it wipes the RAM ring and stops the tap.
    var stopSignal: Int32 = SIGTERM
}

protocol ChildHandle: AnyObject {
    var isRunning: Bool { get }
    func stop(signal: Int32)
    func kill()
}

protocol ChildLauncher {
    /// `onLine` and `onExit` may be called from any thread; the supervisor hops to its own queue.
    func launch(_ spec: LaunchSpec, onLine: @escaping (String) -> Void, onExit: @escaping (Int32) -> Void) throws -> ChildHandle
}

/// Delayed work that tests can drive by hand.
protocol Scheduler {
    func after(_ seconds: TimeInterval, _ block: @escaping () -> Void) -> () -> Void   // returns a cancel closure
    var now: Date { get }
}

struct SystemScheduler: Scheduler {
    var now: Date { Date() }
    func after(_ seconds: TimeInterval, _ block: @escaping () -> Void) -> () -> Void {
        let item = DispatchWorkItem(block: block)
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds, execute: item)
        return { item.cancel() }
    }
}

enum Backoff {
    /// 1, 2, 4, 8, 16, 30, 30 ...
    static func delay(afterFailures n: Int) -> TimeInterval { min(30, pow(2, Double(max(0, n - 1)))) }
}

/// Keeps one child alive: restarts on crash with exponential backoff, resets the backoff after a healthy run,
/// and reports `gaveUp` after repeated fast failures so the UI can say "problem" instead of flapping forever.
/// Main-thread only.
final class ProcessSupervisor {
    enum Status: Equatable { case stopped, running, backingOff(failures: Int) }

    let spec: LaunchSpec
    private let launcher: ChildLauncher
    private let scheduler: Scheduler
    private(set) var status: Status = .stopped
    private(set) var restarts = 0
    private(set) var gaveUp = false
    private(set) var lastExitCode: Int32?
    private(set) var lastLine: String?

    var healthyAfter: TimeInterval = 30
    var giveUpAfterFastFailures = 4
    var onChange: (() -> Void)?
    var onLine: ((String) -> Void)?

    private var handle: ChildHandle?
    private var dying: ChildHandle?
    private var startedAt = Date()
    private var failures = 0
    private var cancelRestart: (() -> Void)?
    private var wanted = false
    private var generation = 0

    init(spec: LaunchSpec, launcher: ChildLauncher, scheduler: Scheduler = SystemScheduler()) {
        self.spec = spec; self.launcher = launcher; self.scheduler = scheduler
    }

    var isRunning: Bool { status == .running }

    func start() {
        wanted = true
        gaveUp = false
        failures = 0
        launch()
    }

    func stop() {
        wanted = false
        cancelRestart?(); cancelRestart = nil
        generation += 1
        if let h = handle, h.isRunning {
            h.stop(signal: spec.stopSignal)
            let doomed = h
            _ = scheduler.after(4) { if doomed.isRunning { doomed.kill() } }
        }
        dying = handle
        handle = nil
        status = .stopped
        onChange?()
    }

    /// Blocks (briefly) until a child that was told to stop has exited; kills it at the timeout. For Quit only.
    func waitForExit(timeout: TimeInterval) {
        let end = Date().addingTimeInterval(timeout)
        while let d = dying, d.isRunning, Date() < end { Thread.sleep(forTimeInterval: 0.05) }
        if let d = dying, d.isRunning { d.kill() }
        dying = nil
    }

    private func launch() {
        cancelRestart = nil
        generation += 1
        let gen = generation
        startedAt = scheduler.now
        do {
            handle = try launcher.launch(spec,
                onLine: { [weak self] line in DispatchQueue.main.async { self?.lastLine = line; self?.onLine?(line) } },
                onExit: { [weak self] code in DispatchQueue.main.async { self?.exited(code, generation: gen) } })
            status = .running
        } catch {
            lastLine = "could not start: \(error.localizedDescription)"
            handle = nil
            fail()
            return
        }
        onChange?()
    }

    /// Called by the launcher (already on main) when the child exits.
    func exited(_ code: Int32, generation gen: Int) {
        guard gen == generation, wanted else { return }
        lastExitCode = code
        handle = nil
        if scheduler.now.timeIntervalSince(startedAt) >= healthyAfter { failures = 0 }
        fail()
    }

    private func fail() {
        failures += 1
        restarts += 1
        if failures >= giveUpAfterFastFailures { gaveUp = true }
        status = .backingOff(failures: failures)
        onChange?()
        guard wanted else { return }
        cancelRestart = scheduler.after(Backoff.delay(afterFailures: failures)) { [weak self] in
            guard let self, self.wanted else { return }
            self.launch()
        }
    }
}
