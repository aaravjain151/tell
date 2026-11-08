import CallKit
import Foundation

/// UI state for "Blocked numbers". The list itself is BlockListStore (local file); this only talks to CallKit.
@MainActor
final class BlockController: ObservableObject {
    static let extensionID = "dev.doublespeak.app.ios.CallBlocker"

    enum Enablement: Equatable { case unknown, enabled, disabled, error }

    @Published private(set) var entries: [BlockEntry] = []
    @Published var enablement: Enablement = .unknown
    @Published var message: String?
    @Published private(set) var reloadFailed = false

    let store: BlockListStore
    init(store: BlockListStore = .standard()) {
        self.store = store
        refresh()
    }

    /// Whether the extension can read what the app saves (App Group file or shared keychain item).
    var sharedWithExtension: Bool { store.sharesWithExtension }

    func refresh() {
        entries = store.load().sorted { $0.addedAt > $1.addedAt }
        CXCallDirectoryManager.sharedInstance.getEnabledStatusForExtension(withIdentifier: Self.extensionID) { [weak self] status, _ in
            Task { @MainActor in
                switch status {
                case .enabled: self?.enablement = .enabled
                case .disabled: self?.enablement = .disabled
                default: self?.enablement = .error      // includes .unknown (not installed, e.g. the simulator build without the extension)
                }
            }
        }
    }

    func add(number: String, label: String) -> Bool {
        switch store.add(number, label: label) {
        case .added: message = nil
        case .repeated: message = "Already on the list. Counted again."
        case .invalid: message = "That does not look like a phone number. Include the country code, for example +1 415 555 0123."; return false
        case .full: message = "The list is full (\(BlockListStore.maxEntries) numbers)."; return false
        }
        changed()
        return true
    }

    func remove(_ e: BlockEntry) { store.remove(id: e.id); changed() }

    private func changed() {
        refresh()
        CXCallDirectoryManager.sharedInstance.reloadExtension(withIdentifier: Self.extensionID) { [weak self] err in
            Task { @MainActor in self?.reloadFailed = err != nil }       // the error text is not shown or logged
        }
    }

    func openSettings() {
        CXCallDirectoryManager.sharedInstance.openSettings { _ in }
    }
}
