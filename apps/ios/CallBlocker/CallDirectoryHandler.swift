import CallKit
import Foundation

/// Call Directory extension: hands iOS the user's own block list so blocked numbers never ring.
/// Runs only when iOS asks (after the app calls reloadExtension). It cannot see incoming calls and sends nothing anywhere.
final class CallDirectoryHandler: CXCallDirectoryProvider {
    override func beginRequest(with context: CXCallDirectoryExtensionContext) {
        // Entries must be added in ascending order; callDirectoryNumbers() is sorted and de-duplicated.
        // Always rebuild the whole set: simplest, and correct for incremental requests too.
        if context.isIncremental { context.removeAllBlockingEntries() }
        for n in BlockListStore.numbersForExtension() {
            context.addBlockingEntry(withNextSequentialPhoneNumber: CXCallDirectoryPhoneNumber(n))
        }
        context.completeRequest()
    }
}
