import XCTest
@testable import Doublespeak

final class BlockNumberTests: XCTestCase {
    func testNormaliseTable() {
        let cases: [(String, String?)] = [
            ("(415) 555-0123", "+14155550123"), ("415.555.0123", "+14155550123"), ("1 415 555 0123", "+14155550123"),
            ("+1 (415) 555-0123", "+14155550123"), ("001 415 555 0123", "+14155550123"),
            ("+44 20 7946 0958", "+442079460958"), ("+91 98765 43210", "+919876543210"),
            ("415-555-012", nil), ("155-555-0123", nil), ("1-800-FLOWERS", nil), ("+0123456789", nil), ("+123", nil),
            ("+1234567890123456", nil), ("", nil), ("   ", nil), ("++14155550123", nil), ("911", nil),
            (String(repeating: "x", count: 500), nil), ("+1415555012\u{0663}", nil),
        ]
        for (raw, want) in cases { XCTAssertEqual(BlockNumber.normalise(raw), want, raw) }
        XCTAssertEqual(BlockNumber.normalise("020 7946 0958", region: "GB"), "+442079460958")
        XCTAssertNil(BlockNumber.normalise("4155550123", region: "DE"))
    }

    func testCallDirectoryValue() {
        XCTAssertEqual(BlockNumber.callDirectoryValue("+14155550123"), 14155550123)
        XCTAssertNil(BlockNumber.callDirectoryValue("14155550123"))
    }
}

final class BlockListStoreTests: XCTestCase {
    private var dir: URL!
    override func setUp() {
        dir = FileManager.default.temporaryDirectory.appendingPathComponent("bl-\(UUID().uuidString)")
    }
    override func tearDown() { try? FileManager.default.removeItem(at: dir) }

    func testRepeatIncrementsReportsNoDuplicate() {
        let s = BlockListStore(directory: dir)
        guard case .added(let a) = s.add("(415) 555-0123", label: "Robocall") else { return XCTFail() }
        guard case .repeated(let b) = s.add("+1 415 555 0123") else { return XCTFail() }
        XCTAssertEqual(b.id, a.id); XCTAssertEqual(b.reports, 2); XCTAssertEqual(b.label, "Robocall")
        XCTAssertEqual(s.load().count, 1)
    }

    func testInvalidAndFull() {
        let s = BlockListStore(directory: dir)
        XCTAssertEqual(s.add("junk"), .invalid)
        XCTAssertTrue(s.load().isEmpty)
    }

    func testRemove() {
        let s = BlockListStore(directory: dir)
        guard case .added(let a) = s.add("415-555-0123") else { return XCTFail() }
        s.remove(id: a.id)
        XCTAssertTrue(s.load().isEmpty)
    }

    func testCallDirectoryNumbersAscendingAndUnique() {
        let s = BlockListStore(directory: dir)
        for n in ["+442079460958", "415-555-0123", "(212) 555-0100", "+1 415 555 0123", "+919876543210"] { _ = s.add(n) }
        XCTAssertEqual(s.callDirectoryNumbers(), [12125550100, 14155550123, 442079460958, 919876543210])
    }

    func testLabelIsCleaned() {
        let s = BlockListStore(directory: dir)
        guard case .added(let a) = s.add("415-555-0123", label: "a\u{0}b\nc" + String(repeating: "z", count: 100)) else { return XCTFail() }
        XCTAssertFalse(a.label.contains("\u{0}")); XCTAssertFalse(a.label.contains("\n"))
        XCTAssertLessThanOrEqual(a.label.count, BlockListStore.maxLabel)
    }

    func testStandardWithoutGroupIsAppOnly() {
        // The unit-test host has no App Group entitlement, so the store must say it is not shared.
        XCTAssertNotEqual(BlockListStore.standard().location, .sharedGroup)
    }
}
