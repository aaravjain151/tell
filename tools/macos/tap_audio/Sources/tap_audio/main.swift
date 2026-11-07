import AVFoundation
import AppKit
import CoreAudio
import Foundation
import Darwin

// tap_audio: record the macOS system audio mix (or one app) with a Core Audio
// process tap, as 16 kHz mono 16-bit PCM. No virtual audio driver needed.

func err(_ s: String) { FileHandle.standardError.write(Data((s + "\n").utf8)) }

let usage = """
usage: tap_audio --seconds N --out PATH.wav [--process NAME]
       tap_audio --stream [--seconds N] [--process NAME]   (raw PCM16 16 kHz mono to stdout)
       tap_audio --list          list processes currently producing audio
       tap_audio --self-test     check the resampler and WAV writer (no audio capture)
"""

let permissionHelp = """
tap_audio: could not capture system audio.
 - Needs macOS 14.4 or newer (this is \(ProcessInfo.processInfo.operatingSystemVersionString)).
 - Grant access in System Settings > Privacy & Security > "Screen & System Audio Recording"
   (the "System Audio Recording Only" / "Audio Capture" list). Enable the terminal app you
   run this from (Terminal, iTerm, VS Code, Claude Code ...), then quit and reopen that app.
"""

// MARK: Core Audio helpers

func getProp<T>(_ obj: AudioObjectID, _ sel: AudioObjectPropertySelector, _ def: T,
                scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal) -> T? {
    var addr = AudioObjectPropertyAddress(mSelector: sel, mScope: scope, mElement: kAudioObjectPropertyElementMain)
    var v = def
    var size = UInt32(MemoryLayout<T>.size)
    let st = AudioObjectGetPropertyData(obj, &addr, 0, nil, &size, &v)
    return st == noErr ? v : nil
}

func processObjects() -> [AudioObjectID] {
    var addr = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyProcessObjectList,
                                          mScope: kAudioObjectPropertyScopeGlobal,
                                          mElement: kAudioObjectPropertyElementMain)
    var size: UInt32 = 0
    guard AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size) == noErr else { return [] }
    var ids = [AudioObjectID](repeating: 0, count: Int(size) / MemoryLayout<AudioObjectID>.size)
    guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size, &ids) == noErr else { return [] }
    return ids
}

func processInfo(_ id: AudioObjectID) -> (pid: pid_t, bundle: String, running: Bool) {
    let pid: pid_t = getProp(id, kAudioProcessPropertyPID, pid_t(0)) ?? 0
    var bundle = ""
    if let cf: CFString = getProp(id, kAudioProcessPropertyBundleID, "" as CFString) { bundle = cf as String }
    let out: UInt32 = getProp(id, kAudioProcessPropertyIsRunningOutput, UInt32(0)) ?? 0
    return (pid, bundle, out != 0)
}

func execName(_ pid: pid_t) -> String {
    var buf = [CChar](repeating: 0, count: 256)
    return proc_name(pid, &buf, 256) > 0 ? String(cString: buf) : ""
}

func processName(_ pid: pid_t, _ bundle: String) -> String {
    NSRunningApplication(processIdentifier: pid)?.localizedName ?? (execName(pid).isEmpty ? bundle : execName(pid))
}

func listProcesses() {
    var any = false
    for id in processObjects() {
        let p = processInfo(id)
        guard p.running else { continue }
        any = true
        print("\(processName(p.pid, p.bundle))\t\(p.bundle)\tpid \(p.pid)")
    }
    if !any { err("no process is producing audio right now") }
}

/// Process objects belonging to an app matched by name or bundle id (includes helper processes).
func resolveProcesses(_ name: String) -> [AudioObjectID] {
    let q = name.lowercased()
    var rootBundles = Set<String>()
    var pids = Set<pid_t>()
    for app in NSWorkspace.shared.runningApplications {
        let n = (app.localizedName ?? "").lowercased()
        let b = (app.bundleIdentifier ?? "").lowercased()
        if n == q || b == q || n.contains(q) || b.contains(q) {
            pids.insert(app.processIdentifier)
            if let bid = app.bundleIdentifier { rootBundles.insert(bid.lowercased()) }
        }
    }
    return processObjects().filter { id in
        let p = processInfo(id)
        let b = p.bundle.lowercased()
        return pids.contains(p.pid) || execName(p.pid).lowercased().contains(q) || rootBundles.contains(where: { b == $0 || b.hasPrefix($0 + ".") }) || b.contains(q)
    }
}

// MARK: Capture

final class Capture {
    var tapID = AudioObjectID(kAudioObjectUnknown)
    var aggID = AudioObjectID(kAudioObjectUnknown)
    var procID: AudioDeviceIOProcID?
    var resampler: Resampler?
    let lock = NSLock()
    var pcm = Data()
    var stats = Stats()
    var window = Stats()
    var callbacks = 0
    let streaming: Bool
    init(streaming: Bool) { self.streaming = streaming }

    func start(processes: [AudioObjectID]?) -> String? {
        let desc: CATapDescription
        if let procs = processes {
            desc = CATapDescription(stereoMixdownOfProcesses: procs)
        } else {
            // Global tap, excluding this process.
            var addr = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyTranslatePIDToProcessObject,
                                                  mScope: kAudioObjectPropertyScopeGlobal,
                                                  mElement: kAudioObjectPropertyElementMain)
            var pid = getpid()
            var me = AudioObjectID(kAudioObjectUnknown)
            var sz = UInt32(MemoryLayout<AudioObjectID>.size)
            _ = AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr,
                                           UInt32(MemoryLayout<pid_t>.size), &pid, &sz, &me)
            desc = CATapDescription(stereoGlobalTapButExcludeProcesses: me == kAudioObjectUnknown ? [] : [me])
        }
        let uuid = UUID()
        desc.uuid = uuid
        desc.name = "doublespeak-tap"
        desc.isPrivate = true
        desc.muteBehavior = .unmuted

        var st = AudioHardwareCreateProcessTap(desc, &tapID)
        guard st == noErr else { return "AudioHardwareCreateProcessTap failed (OSStatus \(st))" }

        guard let asbd: AudioStreamBasicDescription = getProp(tapID, kAudioTapPropertyFormat, AudioStreamBasicDescription()) else {
            return "could not read the tap format"
        }
        var a = asbd
        guard let fmt = AVAudioFormat(streamDescription: &a), let rs = Resampler(from: fmt) else {
            return "unsupported tap format"
        }
        resampler = rs

        var dict: [String: Any] = [
            kAudioAggregateDeviceNameKey: "doublespeak-agg",
            kAudioAggregateDeviceUIDKey: UUID().uuidString,
            kAudioAggregateDeviceIsPrivateKey: true,
            kAudioAggregateDeviceTapAutoStartKey: true,
            kAudioAggregateDeviceTapListKey: [[
                kAudioSubTapUIDKey: uuid.uuidString,
                kAudioSubTapDriftCompensationKey: true,
            ]],
        ]
        if let out: AudioObjectID = getProp(AudioObjectID(kAudioObjectSystemObject), kAudioHardwarePropertyDefaultSystemOutputDevice, AudioObjectID(0)),
           let uid: CFString = getProp(out, kAudioDevicePropertyDeviceUID, "" as CFString) {
            dict[kAudioAggregateDeviceMainSubDeviceKey] = uid as String
        }
        st = AudioHardwareCreateAggregateDevice(dict as CFDictionary, &aggID)
        guard st == noErr else { return "AudioHardwareCreateAggregateDevice failed (OSStatus \(st))" }

        let queue = DispatchQueue(label: "tap_audio.io", qos: .userInitiated)
        st = AudioDeviceCreateIOProcIDWithBlock(&procID, aggID, queue) { [weak self] _, inData, _, _, _ in
            self?.handle(inData)
        }
        guard st == noErr else { return "AudioDeviceCreateIOProcIDWithBlock failed (OSStatus \(st))" }
        st = AudioDeviceStart(aggID, procID)
        guard st == noErr else { return "AudioDeviceStart failed (OSStatus \(st))" }
        return nil
    }

    private func handle(_ list: UnsafePointer<AudioBufferList>) {
        guard let rs = resampler,
              let buf = AVAudioPCMBuffer(pcmFormat: rs.inFormat, bufferListNoCopy: list, deallocator: nil) else { return }
        callbacks += 1
        let samples = rs.convert(buf)
        if samples.isEmpty { return }
        let data = samples.withUnsafeBufferPointer { Data(buffer: $0) }
        lock.lock()
        for s in samples { stats.add(s); window.add(s) }
        if !streaming { pcm.append(data) }
        lock.unlock()
        if streaming { FileHandle.standardOutput.write(data) }
    }

    func takeWindow() -> Stats {
        lock.lock(); defer { lock.unlock() }
        let w = window; window = Stats(); return w
    }

    func stop() {
        if let p = procID { AudioDeviceStop(aggID, p); AudioDeviceDestroyIOProcID(aggID, p) }
        if aggID != kAudioObjectUnknown { AudioHardwareDestroyAggregateDevice(aggID) }
        if tapID != kAudioObjectUnknown { AudioHardwareDestroyProcessTap(tapID) }
    }
}

func meter(_ rms: Float) -> String {
    let db = rms > 0 ? 20 * log10(rms) : -120
    let n = max(0, min(30, Int((db + 80) / 80 * 30)))
    return "[" + String(repeating: "#", count: n) + String(repeating: ".", count: 30 - n) + "]" + String(format: " %6.1f dBFS", db)
}

// MARK: Self test

func selfTest() -> Int32 {
    var ok = true
    let fmt = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 48000, channels: 2, interleaved: false)!
    let frames: AVAudioFrameCount = 48000
    let buf = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: frames)!
    buf.frameLength = frames
    for i in 0..<Int(frames) {
        let v = Float(0.5 * sin(2 * Double.pi * 440 * Double(i) / 48000))
        buf.floatChannelData![0][i] = v
        buf.floatChannelData![1][i] = v
    }
    let out = Resampler(from: fmt)!.convert(buf)
    var s = Stats(); out.forEach { s.add($0) }
    print("resample: \(out.count) samples (expect ~16000), peak \(s.peak), rms \(s.rms) (expect ~0.5 / ~0.354)")
    if abs(out.count - 16000) > 1500 || abs(s.peak - 0.5) > 0.05 || abs(s.rms - 0.354) > 0.05 { ok = false }
    let w = wavData(pcm: out.withUnsafeBufferPointer { Data(buffer: $0) })
    let hdrOK = w.count == 44 + out.count * 2 && String(decoding: w.prefix(4), as: UTF8.self) == "RIFF"
    print("wav: \(w.count) bytes, header \(hdrOK ? "ok" : "BAD")")
    if !hdrOK { ok = false }
    print(ok ? "self-test OK" : "self-test FAILED")
    return ok ? 0 : 1
}

// MARK: Main

var args = Array(CommandLine.arguments.dropFirst())
func take(_ flag: String) -> String? {
    guard let i = args.firstIndex(of: flag), i + 1 < args.count else { return nil }
    let v = args[i + 1]; args.removeSubrange(i...i + 1); return v
}
func has(_ flag: String) -> Bool {
    if let i = args.firstIndex(of: flag) { args.remove(at: i); return true }
    return false
}

if has("--help") || has("-h") { print(usage); exit(0) }
if has("--self-test") { exit(selfTest()) }
if has("--list") { listProcesses(); exit(0) }
let stream = has("--stream")
let secondsArg = take("--seconds")
let outPath = take("--out")
let procName = take("--process")
if !args.isEmpty { err("unknown arguments: \(args.joined(separator: " "))\n\(usage)"); exit(64) }

guard #available(macOS 14.4, *) else { err(permissionHelp); exit(3) }

if !stream && outPath == nil {
    err("tap_audio: refusing to record without an explicit --out PATH.wav (or --stream).\n\(usage)")
    exit(64)
}
var seconds: Double? = nil
if let s = secondsArg {
    guard let v = Double(s), v > 0, v <= 3600 else { err("--seconds must be a number between 0 and 3600"); exit(64) }
    seconds = v
}
if !stream && seconds == nil { err("--seconds N is required with --out\n\(usage)"); exit(64) }

err("RECORDING ALL SYSTEM AUDIO\(procName.map { " from '\($0)'" } ?? ""). Recording or analysing a call may need the other party's consent depending on where you are.")

var procs: [AudioObjectID]? = nil
if let n = procName {
    let r = resolveProcesses(n)
    if r.isEmpty {
        err("tap_audio: no audio process matches '\(n)'. Is the app running and has it played audio? Try --list.")
        exit(3)
    }
    procs = r
}

let cap = Capture(streaming: stream)
if let e = cap.start(processes: procs) {
    cap.stop()
    err("tap_audio: \(e)\n\(permissionHelp)")
    exit(3)
}

signal(SIGINT, SIG_IGN)
let sigSrc = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
var stopRequested = false
sigSrc.setEventHandler { stopRequested = true }
sigSrc.resume()

let start = Date()
var nextMeter = 0.5
while !stopRequested {
    let el = Date().timeIntervalSince(start)
    if let s = seconds, el >= s { break }
    if el >= nextMeter {
        let w = cap.takeWindow()
        err(String(format: "%5.1fs ", el) + meter(w.rms) + String(format: "  peak %.4f", w.peak))
        nextMeter += 0.5
    }
    RunLoop.main.run(until: Date().addingTimeInterval(0.05))
}
cap.stop()

cap.lock.lock()
let st = cap.stats
let pcmData = cap.pcm
cap.lock.unlock()
let dur = Double(st.n) / 16000
let silent = st.peak < 0.0005
if let p = outPath {
    do { try wavData(pcm: pcmData).write(to: URL(fileURLWithPath: p)) }
    catch { err("tap_audio: cannot write \(p): \(error)"); exit(1) }
}
err(String(format: "summary: %.2fs captured, %d IO callbacks, peak %.4f, rms %.5f, %@%@",
           dur, cap.callbacks, st.peak, st.rms, silent ? "SILENT" : "audio present",
           outPath.map { " -> \($0)" } ?? ""))
if silent {
    err("""
    tap_audio: only silence was captured. Either nothing was playing, or the permission was not granted
    (macOS delivers zeros instead of an error when access is denied).
    \(permissionHelp)
    """)
    exit(2)
}
exit(0)
