package dev.doublespeak.app.call;

import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * The phone's side of the engine protocol (services/api/tell/stream.py), in plain Java sockets (pure, no Android
 * imports, no third-party library). It can only reach 127.0.0.1: the address is fixed in code, and on the phone that
 * port is the computer's engine through `adb reverse tcp:8000 tcp:8000` (D-012: the USB cable is the only path).
 *
 *   POST /session (Origin http://localhost, the installed app's origin) -> {token, ws_path}
 *   WS ws_path, hello {side:"mix"} -> ready, then binary PCM16 frames + {"type":"ping"} every 10 s, {"type":"stop"} at the end
 *   DELETE /session/{id} afterwards (best effort, wipes the server session)
 */
public final class LoopbackEngine implements CallSession.Engine {
    public static final String ORIGIN = "http://localhost";
    public static final String SOURCE = "android call";
    private final int port;
    private final int connectTimeoutMs;

    public LoopbackEngine(int port, int connectTimeoutMs) {
        this.port = port;
        this.connectTimeoutMs = connectTimeoutMs;
    }

    static InetAddress loopback() throws IOException {
        return InetAddress.getByAddress("localhost", new byte[]{127, 0, 0, 1});
    }

    // ---------- HTTP ----------

    static final class Response {
        final int status; final String body;
        Response(int status, String body) { this.status = status; this.body = body; }
    }

    Response http(String method, String path) throws IOException {
        try (Socket s = new Socket()) {
            s.connect(new InetSocketAddress(loopback(), port), connectTimeoutMs);
            s.setSoTimeout(8000);
            String req = method + " " + path + " HTTP/1.1\r\nHost: localhost:" + port + "\r\nOrigin: " + ORIGIN +
                "\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
            s.getOutputStream().write(req.getBytes(StandardCharsets.US_ASCII));
            s.getOutputStream().flush();
            InputStream in = s.getInputStream();
            String head = readHead(in);
            int status = parseStatus(head);
            ByteArrayOutputStream body = new ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) > 0 && body.size() < (1 << 16)) body.write(buf, 0, n);
            return new Response(status, body.toString("UTF-8"));
        }
    }

    static String readHead(InputStream in) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        int c, state = 0;
        while ((c = in.read()) != -1) {
            b.write(c);
            if (b.size() > 16384) throw new IOException("header too large");
            state = (c == '\r' && (state == 0 || state == 2)) ? state + 1 : (c == '\n' && (state == 1 || state == 3)) ? state + 1 : 0;
            if (state == 4) return b.toString("ISO-8859-1");
        }
        throw new EOFException("connection closed before headers");
    }

    static int parseStatus(String head) throws IOException {
        Matcher m = Pattern.compile("^HTTP/1\\.[01] (\\d{3})").matcher(head);
        if (!m.find()) throw new IOException("bad status line");
        return Integer.parseInt(m.group(1));
    }

    static String jsonString(String json, String key) {
        Matcher m = Pattern.compile("\"" + Pattern.quote(key) + "\"\\s*:\\s*\"([^\"\\\\]*)\"").matcher(json);
        return m.find() ? m.group(1) : null;
    }

    // ---------- session ----------

    @Override
    public CallSession.Link open(CallSession.LinkListener listener) throws CallSession.EngineError {
        Response r;
        try {
            r = http("POST", "/session");
        } catch (IOException e) {
            throw new CallSession.EngineError(CallSession.Outcome.NOT_CONNECTED, e.getClass().getSimpleName());
        }
        if (r.status == 403) throw new CallSession.EngineError(CallSession.Outcome.REFUSED, "403");
        if (r.status == 429) throw new CallSession.EngineError(CallSession.Outcome.BUSY, "429");
        if (r.status != 200) throw new CallSession.EngineError(CallSession.Outcome.NOT_CONNECTED, "status " + r.status);
        String token = jsonString(r.body, "token"), sid = jsonString(r.body, "session_id"), path = jsonString(r.body, "ws_path");
        if (token == null) throw new CallSession.EngineError(CallSession.Outcome.NOT_CONNECTED, "no token");
        if (path == null || !path.startsWith("/")) path = "/ws/stream";
        WsLink link = new WsLink(sid, listener);
        try {
            link.connect(path, token);
        } catch (IOException e) {
            link.close();
            throw new CallSession.EngineError(CallSession.Outcome.NOT_CONNECTED, e.getClass().getSimpleName());
        } catch (CallSession.EngineError e) {
            link.close();
            throw e;
        }
        return link;
    }

    public static String hello(String token) {
        return "{\"type\":\"hello\",\"token\":\"" + token.replace("\\", "").replace("\"", "") +
            "\",\"sample_rate\":16000,\"format\":\"pcm_s16le\",\"side\":\"mix\",\"source\":\"" + SOURCE + "\"}";
    }

    final class WsLink implements CallSession.Link {
        private final String sid;
        private final CallSession.LinkListener listener;
        private Socket sock;
        private OutputStream out;
        private volatile boolean closing;
        private Thread reader;

        WsLink(String sid, CallSession.LinkListener listener) { this.sid = sid; this.listener = listener; }

        void connect(String path, String token) throws IOException, CallSession.EngineError {
            sock = new Socket();
            sock.connect(new InetSocketAddress(loopback(), port), connectTimeoutMs);
            sock.setSoTimeout(8000);
            sock.setTcpNoDelay(true);
            byte[] keyBytes = new byte[16];
            new SecureRandom().nextBytes(keyBytes);
            String key = WsFrames.base64(keyBytes);
            String req = "GET " + path + " HTTP/1.1\r\nHost: localhost:" + port + "\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n" +
                "Sec-WebSocket-Key: " + key + "\r\nSec-WebSocket-Version: 13\r\nOrigin: " + ORIGIN + "\r\n\r\n";
            out = sock.getOutputStream();
            out.write(req.getBytes(StandardCharsets.US_ASCII));
            out.flush();
            InputStream in = sock.getInputStream();
            String head = readHead(in);
            if (parseStatus(head) != 101) throw new CallSession.EngineError(CallSession.Outcome.REFUSED, "ws " + parseStatus(head));
            if (!head.contains(WsFrames.acceptFor(key))) throw new IOException("bad accept");
            sendText(hello(token));
            WsFrames.Frame f = WsFrames.read(in);            // the first answer must be ready (or an error)
            String t = f.text();
            if (t == null || !t.contains("\"ready\"")) {
                String code = t == null ? "closed" : jsonString(t, "code");
                throw new CallSession.EngineError(CallSession.Outcome.NOT_CONNECTED, code == null ? "no ready" : code);
            }
            sock.setSoTimeout(0);
            reader = new Thread(this::readLoop, "tell-ws-reader");
            reader.setDaemon(true);
            reader.start();
        }

        private void readLoop() {
            String why = "closed";
            try {
                InputStream in = sock.getInputStream();
                while (!closing) {
                    WsFrames.Frame f = WsFrames.read(in);
                    if (f.opcode == WsFrames.OP_CLOSE) { why = "closed"; break; }
                    if (f.opcode == WsFrames.OP_PING) { synchronized (this) { out.write(WsFrames.encode(WsFrames.OP_PONG, f.payload, f.payload.length)); } continue; }
                    String t = f.text();
                    if (t == null) continue;
                    String type = jsonString(t, "type");             // the server writes "type" first
                    if ("final".equals(type)) { why = "final"; break; }
                    if ("error".equals(type)) { String c = jsonString(t, "code"); why = c == null ? "error" : c; break; }
                    listener.onServerMessage(type, t);
                }
            } catch (IOException e) {
                why = "closed";
            }
            if (!closing) listener.onServerClosed(why);
        }

        @Override
        public synchronized void sendAudio(byte[] pcm, int len) throws IOException {
            out.write(WsFrames.encode(WsFrames.OP_BINARY, pcm, len));
        }

        @Override
        public synchronized void sendText(String s) throws IOException {
            byte[] b = s.getBytes(StandardCharsets.UTF_8);
            out.write(WsFrames.encode(WsFrames.OP_TEXT, b, b.length));
        }

        @Override
        public void close() {
            closing = true;
            try { if (out != null) sendText("{\"type\":\"stop\"}"); } catch (IOException ignored) {}
            try { if (out != null) synchronized (this) { out.write(WsFrames.encode(WsFrames.OP_CLOSE, new byte[]{0x03, (byte) 0xE8}, 2)); } } catch (IOException ignored) {}
            try { if (sock != null) sock.close(); } catch (IOException ignored) {}
            if (sid != null && sid.matches("[A-Za-z0-9_-]{1,128}")) {
                try { http("DELETE", "/session/" + sid); } catch (IOException ignored) {}   // 404 when already wiped: fine
            }
        }
    }

    /** RFC 6455 client framing (client frames are masked; server frames are not). */
    public static final class WsFrames {
        public static final int OP_CONT = 0, OP_TEXT = 1, OP_BINARY = 2, OP_CLOSE = 8, OP_PING = 9, OP_PONG = 10;
        static final int MAX_MESSAGE = 4 << 20;
        private static final SecureRandom RNG = new SecureRandom();

        public static final class Frame {
            public final int opcode; public final byte[] payload;
            Frame(int opcode, byte[] payload) { this.opcode = opcode; this.payload = payload; }
            public String text() { return opcode == OP_TEXT ? new String(payload, StandardCharsets.UTF_8) : null; }
        }

        public static String acceptFor(String key) {
            try {
                MessageDigest sha1 = MessageDigest.getInstance("SHA-1");
                byte[] d = sha1.digest((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").getBytes(StandardCharsets.US_ASCII));
                return base64(d);
            } catch (Exception e) {
                throw new IllegalStateException(e);
            }
        }

        /** Standard Base64 with padding (java.util.Base64 needs API 26; this app supports API 22). */
        public static String base64(byte[] d) {
            final String a = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
            StringBuilder s = new StringBuilder((d.length + 2) / 3 * 4);
            for (int i = 0; i < d.length; i += 3) {
                int n = (d[i] & 0xFF) << 16 | (i + 1 < d.length ? (d[i + 1] & 0xFF) << 8 : 0) | (i + 2 < d.length ? d[i + 2] & 0xFF : 0);
                s.append(a.charAt(n >>> 18 & 63)).append(a.charAt(n >>> 12 & 63));
                s.append(i + 1 < d.length ? a.charAt(n >>> 6 & 63) : '=').append(i + 2 < d.length ? a.charAt(n & 63) : '=');
            }
            return s.toString();
        }

        public static byte[] encode(int opcode, byte[] data, int len) {
            byte[] mask = new byte[4];
            RNG.nextBytes(mask);
            return encode(opcode, data, len, mask);
        }

        static byte[] encode(int opcode, byte[] data, int len, byte[] mask) {
            int hl = len < 126 ? 2 : len < 65536 ? 4 : 10;
            byte[] f = new byte[hl + 4 + len];
            f[0] = (byte) (0x80 | opcode);
            if (len < 126) f[1] = (byte) (0x80 | len);
            else if (len < 65536) { f[1] = (byte) (0x80 | 126); f[2] = (byte) (len >>> 8); f[3] = (byte) len; }
            else { f[1] = (byte) (0x80 | 127); for (int i = 0; i < 8; i++) f[2 + i] = (byte) (((long) len) >>> (56 - 8 * i)); }
            System.arraycopy(mask, 0, f, hl, 4);
            for (int i = 0; i < len; i++) f[hl + 4 + i] = (byte) (data[i] ^ mask[i & 3]);
            return f;
        }

        /** Reads one message (joins continuation frames). Control frames are returned as they arrive. */
        public static Frame read(InputStream in) throws IOException {
            ByteArrayOutputStream msg = null;
            int msgOp = -1;
            while (true) {
                int b0 = in.read(), b1 = in.read();
                if (b0 < 0 || b1 < 0) throw new EOFException("socket closed");
                boolean fin = (b0 & 0x80) != 0;
                int op = b0 & 0x0F;
                boolean masked = (b1 & 0x80) != 0;
                long len = b1 & 0x7F;
                if (len == 126) {
                    byte[] e = readFully(in, 2);
                    len = ((e[0] & 0xFFL) << 8) | (e[1] & 0xFFL);
                } else if (len == 127) {
                    byte[] e = readFully(in, 8);
                    len = 0;
                    for (int i = 0; i < 8; i++) len = (len << 8) | (e[i] & 0xFFL);
                }
                if (len < 0 || len > MAX_MESSAGE) throw new IOException("frame too large");
                byte[] mask = masked ? readFully(in, 4) : null;
                byte[] payload = readFully(in, (int) len);
                if (mask != null) for (int i = 0; i < payload.length; i++) payload[i] ^= mask[i & 3];
                if (op >= OP_CLOSE) return new Frame(op, payload);            // control frames are never fragmented
                if (op != OP_CONT) { msgOp = op; msg = new ByteArrayOutputStream(); }
                if (msg == null) throw new IOException("continuation without start");
                msg.write(payload);
                if (msg.size() > MAX_MESSAGE) throw new IOException("message too large");
                if (fin) return new Frame(msgOp, msg.toByteArray());
            }
        }

        static byte[] readFully(InputStream in, int n) throws IOException {
            byte[] b = new byte[n];
            int off = 0;
            while (off < n) {
                int r = in.read(b, off, n - off);
                if (r < 0) throw new EOFException("socket closed");
                off += r;
            }
            return b;
        }
    }
}
