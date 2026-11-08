import Foundation
import Security

/// The user's own block list. Compiled into BOTH the app and the Call Directory extension (see project.yml).
/// Local only: no network code here, numbers are never logged. At rest it is one JSON file under iOS Data Protection
/// (`completeUntilFirstUserAuthentication`, so the extension can still read it while the phone is locked).

enum BlockNumber {
    static let maxChars = 32

    /// E.164 ("+14155550123") or nil. Same rules as services/api/tell/blocklist.py: digits, space . - ( ) / and an
    /// optional leading "+"; "+" or "00" means an explicit country code (7 to 15 digits, first not 0); otherwise the
    /// region decides (US/CA, GB, IN, AU) and anything else is refused. Never crashes on junk.
    static func normalise(_ raw: String, region: String = "US") -> String? {
        let s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !s.isEmpty, s.count <= maxChars else { return nil }
        let allowed = Set("0123456789 ().-/+")
        guard s.allSatisfy({ allowed.contains($0) }), !s.dropFirst().contains("+") else { return nil }
        var digits = String(s.filter { $0 >= "0" && $0 <= "9" })
        var explicit = s.hasPrefix("+")
        if !explicit && digits.hasPrefix("00") { digits.removeFirst(2); explicit = true }
        if explicit {
            return (7...15).contains(digits.count) && digits.first != "0" ? "+" + digits : nil
        }
        let d = Array(digits)
        switch region.uppercased() {
        case "US", "CA":
            var n = d
            if n.count == 11 && n[0] == "1" { n.removeFirst() }
            if n.count == 10, "23456789".contains(n[0]), "23456789".contains(n[3]) { return "+1" + String(n) }
            return nil
        case "GB":
            return d.count == 11 && d[0] == "0" ? "+44" + String(d.dropFirst()) : nil
        case "IN":
            var n = d
            if n.count == 11 && n[0] == "0" { n.removeFirst() }
            return n.count == 10 && "6789".contains(n[0]) ? "+91" + String(n) : nil
        case "AU":
            return d.count == 10 && d[0] == "0" ? "+61" + String(d.dropFirst()) : nil
        default:
            return nil
        }
    }

    /// The integer CXCallDirectoryExtensionContext wants: country code plus national number, no plus sign.
    static func callDirectoryValue(_ e164: String) -> Int64? {
        guard e164.hasPrefix("+") else { return nil }
        return Int64(e164.dropFirst())
    }
}

struct BlockEntry: Codable, Identifiable, Equatable {
    var id: String
    var number: String          // E.164
    var label: String
    var addedAt: Date
    var reports: Int
}

final class BlockListStore {
    static let appGroupKey = "DSAppGroup"       // Info.plist key holding the App Group id
    static let fileName = "blocklist.json"
    static let maxEntries = 5000
    static let maxLabel = 64

    enum Location: Equatable {
        case sharedGroup        // App Group container: the Call Directory extension reads the same file
        case sharedKeychain     // no App Group (free team): the numbers are mirrored into a shared keychain item
        case appOnly            // neither is available on this signing: only the app can read the list
        case custom             // tests
    }

    let directory: URL
    let location: Location

    init(directory: URL, location: Location = .custom) {
        self.directory = directory
        self.location = location
    }

    /// App Group container when the build has one, otherwise the app's own Application Support (extension cannot see it).
    static func standard(bundle: Bundle = .main, fileManager: FileManager = .default) -> BlockListStore {
        if let group = bundle.object(forInfoDictionaryKey: appGroupKey) as? String, !group.isEmpty,
           let url = fileManager.containerURL(forSecurityApplicationGroupIdentifier: group) {
            return BlockListStore(directory: url, location: .sharedGroup)
        }
        let base = (try? fileManager.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true))
            ?? fileManager.temporaryDirectory
        if let kc = SharedKeychain(bundle: bundle), kc.isUsable() {
            let s = BlockListStore(directory: base, location: .sharedKeychain)
            s.keychain = kc
            return s
        }
        return BlockListStore(directory: base, location: .appOnly)
    }

    var keychain: SharedKeychain?
    var sharesWithExtension: Bool { location == .sharedGroup || location == .sharedKeychain }

    /// What the extension calls: the shared file when there is an App Group, otherwise the shared keychain item.
    static func numbersForExtension(bundle: Bundle = .main) -> [Int64] {
        let s = standard(bundle: bundle)
        if s.location == .sharedKeychain { return s.keychain?.readNumbers() ?? [] }
        return s.callDirectoryNumbers()
    }

    private var fileURL: URL { directory.appendingPathComponent(Self.fileName) }

    func load() -> [BlockEntry] {
        guard let data = try? Data(contentsOf: fileURL),
              let list = try? JSONDecoder.iso.decode([BlockEntry].self, from: data) else { return [] }
        return list
    }

    func save(_ list: [BlockEntry]) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let data = try JSONEncoder.iso.encode(list)
        try data.write(to: fileURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        if let kc = keychain { _ = kc.writeNumbers(Array(Set(list.compactMap { BlockNumber.callDirectoryValue($0.number) })).sorted()) }
    }

    enum AddResult: Equatable { case added(BlockEntry), repeated(BlockEntry), invalid, full }

    /// A repeat of the same normalised number raises `reports` instead of duplicating.
    func add(_ raw: String, label: String = "", region: String = "US", now: Date = Date()) -> AddResult {
        guard let e164 = BlockNumber.normalise(raw, region: region) else { return .invalid }
        let clean = String(label.filter { !$0.isNewline && $0.unicodeScalars.allSatisfy { $0.value >= 32 && $0.value != 127 } }
            .prefix(Self.maxLabel)).trimmingCharacters(in: .whitespaces)
        var list = load()
        if let i = list.firstIndex(where: { $0.number == e164 }) {
            list[i].reports = min(list[i].reports + 1, 1_000_000)
            if !clean.isEmpty { list[i].label = clean }
            guard (try? save(list)) != nil else { return .invalid }
            return .repeated(list[i])
        }
        guard list.count < Self.maxEntries else { return .full }
        let e = BlockEntry(id: UUID().uuidString, number: e164, label: clean, addedAt: now, reports: 1)
        list.append(e)
        guard (try? save(list)) != nil else { return .invalid }
        return .added(e)
    }

    func remove(id: String) {
        let list = load()
        let kept = list.filter { $0.id != id }
        if kept.count != list.count { try? save(kept) }
    }

    /// Sorted ascending and de-duplicated: the order `addBlockingEntry(withNextSequentialPhoneNumber:)` requires.
    func callDirectoryNumbers() -> [Int64] {
        Array(Set(load().compactMap { BlockNumber.callDirectoryValue($0.number) })).sorted()
    }
}

extension JSONEncoder {
    static var iso: JSONEncoder { let e = JSONEncoder(); e.dateEncodingStrategy = .iso8601; return e }
}
extension JSONDecoder {
    static var iso: JSONDecoder { let d = JSONDecoder(); d.dateDecodingStrategy = .iso8601; return d }
}

/// Free-team fallback: a Personal Team cannot register an App Group, but it can sign Keychain Sharing. The app mirrors
/// ONLY the sorted numbers (one decimal integer per line, no labels) into one keychain item that the extension reads.
/// Accessible after first unlock, this device only, never synced to iCloud. Unverified on a real phone (see docs).
final class SharedKeychain {
    static let groupKey = "DSKeychainGroup"       // Info.plist: $(AppIdentifierPrefix)dev.doublespeak.shared
    private let group: String
    private let account = "blocklist-numbers"
    private let service = "dev.doublespeak.blocklist"

    init?(bundle: Bundle) {
        guard let g = bundle.object(forInfoDictionaryKey: Self.groupKey) as? String, !g.isEmpty, !g.contains("$(") else { return nil }
        group = g
    }

    private func query() -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
         kSecAttrAccount as String: account, kSecAttrAccessGroup as String: group]
    }

    func writeNumbers(_ nums: [Int64]) -> Bool {
        let data = Data(nums.map(String.init).joined(separator: "\n").utf8)
        let update = SecItemUpdate(query() as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if update == errSecSuccess { return true }
        var add = query()
        add[kSecValueData as String] = data
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        return SecItemAdd(add as CFDictionary, nil) == errSecSuccess
    }

    func readNumbers() -> [Int64] {
        var q = query()
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var out: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let d = out as? Data,
              let text = String(data: d, encoding: .utf8) else { return [] }
        return Array(Set(text.split(separator: "\n").compactMap { Int64($0) })).sorted()
    }

    /// True when this build is signed with the keychain group (a write/delete round trip works).
    func isUsable() -> Bool {
        var probe = query()
        probe[kSecAttrAccount as String] = "probe"
        probe[kSecValueData as String] = Data([1])
        probe[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        SecItemDelete(probe as CFDictionary)
        let ok = SecItemAdd(probe as CFDictionary, nil) == errSecSuccess
        SecItemDelete(probe as CFDictionary)
        return ok
    }
}
