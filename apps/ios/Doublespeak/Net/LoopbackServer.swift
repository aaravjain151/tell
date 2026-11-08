import Foundation
import Network

/// A tiny WebSocket SERVER on the PHONE's loopback only. An iPhone cannot reach the Mac's localhost, so the
/// direction is inverted: the Mac-side bridge (tools/ios/bridge.py) reaches this port through `iproxy` (USB, usbmuxd)
/// and connects as the client. Nothing here listens on Wi-Fi or cellular: `requiredInterfaceType = .loopback`
/// bound to the loopback addresses (acceptLocalOnly would refuse 127.0.0.1 peers). One client at a time; it must send {"type":"auth","token":...} within 5 s.
final class LoopbackServer: @unchecked Sendable {
    enum Event {
        case listening
        case failed(String)
        case clientAuthenticated
        case message(Protocol.Inbound)
        case clientGone
    }

    var onEvent: ((Event) -> Void)?
    private let queue = DispatchQueue(label: "dev.doublespeak.loopback")
    private var listeners: [NWListener] = []
    private var client: NWConnection?
    private var authenticated = false
    private var token = ""
    private var authFailures = 0
    private let port: UInt16

    init(port: UInt16 = Protocol.port) { self.port = port }

    func start(token: String) {
        queue.async { [self] in
            self.token = token
            stopLocked()
            do {
                // Two listeners, each bound to a loopback ADDRESS (127.0.0.1 and ::1) and to the loopback interface:
                // nothing is reachable from Wi-Fi or cellular. usbmuxd (iproxy) arrives over loopback.
                for host in [NWEndpoint.Host.ipv4(.loopback), NWEndpoint.Host.ipv6(.loopback)] {
                    let ws = NWProtocolWebSocket.Options()
                    ws.autoReplyPing = true
                    ws.maximumMessageSize = 1 << 20
                    // Accept only non-browser clients: a web page always sends an Origin header, the bridge never does.
                    ws.setClientRequestHandler(queue) { _, headers in
                        if headers.contains(where: { $0.name.lowercased() == "origin" }) {
                            return NWProtocolWebSocket.Response(status: .reject, subprotocol: nil)
                        }
                        return NWProtocolWebSocket.Response(status: .accept, subprotocol: nil)
                    }
                    let params = NWParameters.tcp
                    params.requiredInterfaceType = .loopback
                    params.allowLocalEndpointReuse = true
                    params.requiredLocalEndpoint = NWEndpoint.hostPort(host: host, port: NWEndpoint.Port(rawValue: port)!)
                    params.defaultProtocolStack.applicationProtocols.insert(ws, at: 0)
                    let l = try NWListener(using: params)
                    l.stateUpdateHandler = { [weak self] st in
                        switch st {
                        case .ready: self?.emit(.listening)
                        case .failed(let e): self?.emit(.failed("\(e)"))
                        default: break
                        }
                    }
                    l.newConnectionHandler = { [weak self] c in self?.accept(c) }
                    listeners.append(l)
                    l.start(queue: queue)
                }
            } catch {
                emit(.failed("\(error)"))
            }
        }
    }

    func stop() { queue.async { [self] in stopLocked() } }

    private func stopLocked() {
        client?.cancel(); client = nil; authenticated = false
        listeners.forEach { $0.cancel() }; listeners = []
    }

    func send(_ out: Protocol.Outbound) { sendText(out.json) }

    func sendText(_ s: String) {
        queue.async { [self] in
            guard let c = client, authenticated || s.contains("\"ready\"") else { return }
            let md = NWProtocolWebSocket.Metadata(opcode: .text)
            let ctx = NWConnection.ContentContext(identifier: "text", metadata: [md])
            c.send(content: s.data(using: .utf8), contentContext: ctx, isComplete: true, completion: .contentProcessed { [weak self, weak c] err in self?.sendDone(err, c) })
        }
    }

    func sendFrame(_ data: Data) {
        queue.async { [self] in
            guard let c = client, authenticated else { return }
            let md = NWProtocolWebSocket.Metadata(opcode: .binary)
            let ctx = NWConnection.ContentContext(identifier: "bin", metadata: [md])
            c.send(content: data, contentContext: ctx, isComplete: true, completion: .contentProcessed { [weak self, weak c] err in self?.sendDone(err, c) })
        }
    }

    /// Drop the current client (e.g. the user changed their mind). The bridge reconnects by itself.
    func disconnectClient() { queue.async { [self] in dropClient() } }

    // MARK: private

    /// A failed send is not swallowed: the client is dropped, which the app shows as "Lost contact with your computer".
    private func sendDone(_ err: NWError?, _ c: NWConnection?) {
        guard err != nil, let c else { return }
        queue.async { [weak self] in
            guard let self, self.client === c else { return }
            self.dropClient()
        }
    }


    private func emit(_ e: Event) { DispatchQueue.main.async { [weak self] in self?.onEvent?(e) } }

    private func accept(_ c: NWConnection) {
        guard client == nil else { c.cancel(); return }        // one client only
        client = c
        authenticated = false
        c.stateUpdateHandler = { [weak self, weak c] st in
            guard let self, let c, self.client === c else { return }
            switch st {
            case .failed, .cancelled: self.dropClient()
            default: break
            }
        }
        c.start(queue: queue)
        receive(c)
        queue.asyncAfter(deadline: .now() + 5) { [weak self, weak c] in
            guard let self, let c, self.client === c, !self.authenticated else { return }
            c.cancel(); self.dropClient()
        }
    }

    private func dropClient() {
        guard client != nil else { return }
        let was = authenticated
        client?.cancel(); client = nil; authenticated = false
        if was { emit(.clientGone) }
    }

    private func receive(_ c: NWConnection) {
        c.receiveMessage { [weak self, weak c] data, ctx, _, error in
            guard let self, let c, self.client === c else { return }
            if error != nil { self.dropClient(); return }
            let md = ctx?.protocolMetadata(definition: NWProtocolWebSocket.definition) as? NWProtocolWebSocket.Metadata
            switch md?.opcode {
            case .close?: self.dropClient(); return
            case .text?:
                if let data, let text = String(data: data, encoding: .utf8) { self.handleText(text, c) }
            default: break            // the bridge never sends binary
            }
            self.receive(c)
        }
    }

    private func handleText(_ text: String, _ c: NWConnection) {
        let msg = Protocol.parse(text)
        if !authenticated {
            guard case .auth(let given) = msg, PairingToken.matches(given, expected: token) else {
                authFailures += 1
                c.cancel(); dropClient()
                return
            }
            authenticated = true
            authFailures = 0
            send(.ready)
            emit(.clientAuthenticated)
            return
        }
        emit(.message(msg))
    }
}
