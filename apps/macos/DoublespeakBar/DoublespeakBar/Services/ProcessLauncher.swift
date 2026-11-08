import Foundation

final class RealChild: ChildHandle {
    let process: Process
    init(_ p: Process) { process = p }
    var isRunning: Bool { process.isRunning }
    func stop(signal: Int32) {
        guard process.isRunning else { return }
        if signal == SIGINT { process.interrupt() } else { process.terminate() }
    }
    func kill() { if process.isRunning { Foundation.kill(process.processIdentifier, SIGKILL) } }
}

/// Foundation.Process with pipes. Lines of stdout and stderr are passed through; nothing is stored.
struct ProcessLauncher: ChildLauncher {
    func launch(_ spec: LaunchSpec, onLine: @escaping (String) -> Void, onExit: @escaping (Int32) -> Void) throws -> ChildHandle {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: spec.executable)
        p.arguments = spec.arguments
        p.currentDirectoryURL = URL(fileURLWithPath: spec.cwd)
        p.environment = spec.environment
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        p.standardInput = FileHandle.nullDevice
        var buffer = Data()
        pipe.fileHandleForReading.readabilityHandler = { h in
            let chunk = h.availableData
            if chunk.isEmpty { h.readabilityHandler = nil; return }
            buffer.append(chunk)
            while let nl = buffer.firstIndex(of: 0x0A) {
                let line = String(decoding: buffer[buffer.startIndex..<nl], as: UTF8.self)
                buffer.removeSubrange(buffer.startIndex...nl)
                if !line.isEmpty { onLine(line) }
            }
            if buffer.count > 65_536 { buffer.removeAll() }
        }
        p.terminationHandler = { proc in onExit(proc.terminationStatus) }
        try p.run()
        return RealChild(p)
    }
}
