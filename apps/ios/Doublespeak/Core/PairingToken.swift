import Foundation
import Security

/// Per-launch pairing token. The bridge passes it in its first WebSocket message; the phone refuses anything else.
/// Shown on the phone as XXXX-XXXX (no 0/O/1/I so it can be read out and typed without mistakes).
enum PairingToken {
    static let alphabet = Array("23456789ABCDEFGHJKLMNPQRSTUVWXYZ")
    static let length = 8

    static func generate() -> String {
        var bytes = [UInt8](repeating: 0, count: length)
        if SecRandomCopyBytes(kSecRandomDefault, length, &bytes) != errSecSuccess {
            var g = SystemRandomNumberGenerator()
            bytes = (0..<length).map { _ in UInt8.random(in: 0...255, using: &g) }
        }
        // 256 is a multiple of 32, so the modulo does not bias the pick.
        return String(bytes.map { alphabet[Int($0) % alphabet.count] })
    }

    /// Canonical form: upper case, only characters of the alphabet (dashes and spaces ignored).
    static func normalize(_ s: String) -> String {
        String(s.uppercased().filter { alphabet.contains($0) })
    }

    static func display(_ token: String) -> String {
        let t = normalize(token)
        guard t.count == length else { return t }
        return String(t.prefix(4)) + "-" + String(t.suffix(4))
    }

    /// Constant-time comparison; the bridge may type it with or without the dash and in any case.
    static func matches(_ given: String, expected: String) -> Bool {
        let a = Array(normalize(given).utf8), b = Array(normalize(expected).utf8)
        guard !b.isEmpty else { return false }
        var diff = a.count ^ b.count
        for i in 0..<max(a.count, b.count) {
            diff |= Int(i < a.count ? a[i] : 0) ^ Int(i < b.count ? b[i] : 0)
        }
        return diff == 0
    }
}
