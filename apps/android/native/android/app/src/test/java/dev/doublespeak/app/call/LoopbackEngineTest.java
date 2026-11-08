package dev.doublespeak.app.call;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.Test;

/** The engine client against a fake engine on 127.0.0.1 (real sockets, no Android, no network beyond loopback). */
public class LoopbackEngineTest {

    @Test public void acceptKeyMatchesRfc6455Example() {
        assertEquals("s3pPLMBiTxaQ9kYGzzhZRbK+xOo=", LoopbackEngine.WsFrames.acceptFor("dGhlIHNhbXBsZSBub25jZQ=="));
        assertEquals("", LoopbackEngine.WsFrames.base64(new byte[0]));
        assertEquals("Zm9vYmFy", LoopbackEngine.WsFrames.base64("foobar".getBytes(StandardCharsets.US_ASCII)));
        assertEquals("Zm9vYg==", LoopbackEngine.WsFrames.base64("foob".getBytes(StandardCharsets.US_ASCII)));
    }

    @Test public void maskedFrameRoundTripsAllLengthForms() throws IOException {
        for (int len : new int[]{0, 5, 125, 126, 3200, 65535, 70000}) {
            byte[] data = new byte[len];
            for (int i = 0; i < len; i++) data[i] = (byte) (i * 7);
            byte[] f = LoopbackEngine.WsFrames.encode(LoopbackEngine.WsFrames.OP_BINARY, data, len);
            assertTrue("client frames are masked", (f[1] & 0x80) != 0);
            LoopbackEngine.WsFrames.Frame back = LoopbackEngine.WsFrames.read(new ByteArrayInputStream(f));
            assertEquals(LoopbackEngine.WsFrames.OP_BINARY, back.opcode);
            assertArrayEquals(data, back.payload);
        }
    }

    @Test public void continuationFramesAreJoined() throws IOException {
        byte[] a = {(byte) 0x01, 3, 'a', 'b', 'c'}, b = {(byte) 0x80, 2, 'd', 'e'};   // TEXT (no FIN) + CONT (FIN), unmasked
        byte[] all = new byte[a.length + b.length];
        System.arraycopy(a, 0, all, 0, a.length); System.arraycopy(b, 0, all, a.length, b.length);
        assertEquals("abcde", LoopbackEngine.WsFrames.read(new ByteArrayInputStream(all)).text());
    }

    @Test public void helloMatchesTheEngineHandshake() {
        assertEquals("{\"type\":\"hello\",\"token\":\"tok\",\"sample_rate\":16000,\"format\":\"pcm_s16le\",\"side\":\"mix\",\"source\":\"android call\"}", LoopbackEngine.hello("tok"));
        assertEquals("abc", LoopbackEngine.jsonString("{\"x\": 1, \"token\": \"abc\"}", "token"));
    }

    @Test public void nothingListeningMeansNotConnected() throws Exception {
        int port;
        try (ServerSocket s = new ServerSocket(0, 1, InetAddress.getByName("127.0.0.1"))) { port = s.getLocalPort(); }
        try {
            new LoopbackEngine(port, 500).open(null);
            fail("expected EngineError");
        } catch (CallSession.EngineError e) {
            assertEquals(CallSession.Outcome.NOT_CONNECTED, e.outcome);
            assertEquals(Wording.NOT_CONNECTED_TEXT, CallSession.textFor(e.outcome));
        }
    }

    @Test public void reachableIsTrueOnlyWhenHealthAnswersOk() throws Exception {
        int dead;
        try (ServerSocket s = new ServerSocket(0, 1, InetAddress.getByName("127.0.0.1"))) { dead = s.getLocalPort(); }
        assertFalse(new LoopbackEngine(dead, 400).reachable());               // nothing listening = the cable is gone
        try (ServerSocket ss = new ServerSocket(0, 1, InetAddress.getByName("127.0.0.1"))) {
            Thread t = new Thread(() -> {
                try (Socket c = ss.accept()) {
                    String head = LoopbackEngine.readHead(c.getInputStream());
                    assertTrue(head.startsWith("GET /health"));
                    String body = "{\"ok\": true}";
                    c.getOutputStream().write(("HTTP/1.1 200 OK\r\nContent-Length: " + body.length() + "\r\nConnection: close\r\n\r\n" + body).getBytes(StandardCharsets.US_ASCII));
                } catch (IOException ignored) {}
            });
            t.start();
            assertTrue(new LoopbackEngine(ss.getLocalPort(), 1000).reachable());   // engine answers = not the cable
            t.join(2000);
        }
    }

    @Test public void status403IsRefusedAnd429IsBusy() throws Exception {
        assertEquals(CallSession.Outcome.REFUSED, outcomeFor(403));
        assertEquals(CallSession.Outcome.BUSY, outcomeFor(429));
    }

    private CallSession.Outcome outcomeFor(int status) throws Exception {
        try (ServerSocket ss = new ServerSocket(0, 1, InetAddress.getByName("127.0.0.1"))) {
            Thread t = new Thread(() -> {
                try (Socket c = ss.accept()) {
                    LoopbackEngine.readHead(c.getInputStream());
                    c.getOutputStream().write(("HTTP/1.1 " + status + " X\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}").getBytes(StandardCharsets.US_ASCII));
                } catch (IOException ignored) {}
            });
            t.start();
            try {
                new LoopbackEngine(ss.getLocalPort(), 1000).open(null);
                fail("expected EngineError");
            } catch (CallSession.EngineError e) {
                return e.outcome;
            } finally {
                t.join(2000);
            }
        }
        return null;
    }

    /** Full happy path: POST /session (Origin http://localhost), WS upgrade, hello, ready, audio, ping, stop, DELETE. */
    @Test public void fullSessionAgainstFakeEngine() throws Exception {
        final List<String> seen = Collections.synchronizedList(new ArrayList<>());
        final CountDownLatch done = new CountDownLatch(1);
        try (ServerSocket ss = new ServerSocket(0, 4, InetAddress.getByName("127.0.0.1"))) {
            Thread server = new Thread(() -> {
                try {
                    try (Socket c = ss.accept()) {                                   // POST /session
                        String head = LoopbackEngine.readHead(c.getInputStream());
                        seen.add(head.split("\r\n")[0]);
                        if (head.contains("Origin: http://localhost\r\n")) seen.add("origin-ok");
                        String body = "{\"session_id\": \"sid_1\", \"token\": \"T0K\", \"ws_path\": \"/ws/stream\", \"params\": {}}";
                        c.getOutputStream().write(("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + body.length() + "\r\nConnection: close\r\n\r\n" + body).getBytes(StandardCharsets.US_ASCII));
                    }
                    try (Socket c = ss.accept()) {                                   // WS
                        InputStream in = c.getInputStream(); OutputStream out = c.getOutputStream();
                        String head = LoopbackEngine.readHead(in);
                        seen.add(head.split("\r\n")[0]);
                        Matcher m = Pattern.compile("Sec-WebSocket-Key: (\\S+)").matcher(head);
                        m.find();
                        out.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + LoopbackEngine.WsFrames.acceptFor(m.group(1)) + "\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
                        seen.add("hello:" + LoopbackEngine.WsFrames.read(in).text());
                        out.write(serverText("{\"type\": \"ready\"}"));
                        int audio = 0;
                        while (true) {
                            LoopbackEngine.WsFrames.Frame f = LoopbackEngine.WsFrames.read(in);
                            if (f.opcode == LoopbackEngine.WsFrames.OP_BINARY) { audio++; if (audio == 3) out.write(serverText("{\"type\": \"verdict\", \"tick\": 0}")); continue; }
                            if (f.opcode == LoopbackEngine.WsFrames.OP_TEXT) { seen.add("text:" + f.text()); if (f.text().contains("stop")) break; }
                            if (f.opcode == LoopbackEngine.WsFrames.OP_CLOSE) break;
                        }
                        seen.add("audio:" + audio);
                    }
                    try (Socket c = ss.accept()) {                                   // DELETE /session/sid_1
                        seen.add(LoopbackEngine.readHead(c.getInputStream()).split("\r\n")[0]);
                        c.getOutputStream().write("HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}".getBytes(StandardCharsets.US_ASCII));
                    }
                } catch (IOException e) {
                    seen.add("server-error:" + e);
                } finally {
                    done.countDown();
                }
            });
            server.start();
            final List<String> msgs = Collections.synchronizedList(new ArrayList<>());
            CallSession.Link link = new LoopbackEngine(ss.getLocalPort(), 1000).open(new CallSession.LinkListener() {
                @Override public void onServerMessage(String type, String json) { msgs.add(type); }
                @Override public void onServerClosed(String why) { msgs.add("closed:" + why); }
            });
            byte[] pcm = new byte[3200];
            for (int i = 0; i < 5; i++) link.sendAudio(pcm, pcm.length);
            link.sendText("{\"type\":\"ping\"}");
            Thread.sleep(200);
            link.close();
            assertTrue(done.await(5, TimeUnit.SECONDS));
            assertEquals("POST /session HTTP/1.1", seen.get(0));
            assertTrue(seen.contains("origin-ok"));
            assertEquals("GET /ws/stream HTTP/1.1", seen.get(2));
            assertTrue(seen.get(3).contains("\"side\":\"mix\"") && seen.get(3).contains("\"token\":\"T0K\""));
            assertTrue(seen.contains("text:{\"type\":\"ping\"}"));
            assertTrue(seen.contains("text:{\"type\":\"stop\"}"));
            assertTrue(seen.contains("audio:5"));
            assertEquals("DELETE /session/sid_1 HTTP/1.1", seen.get(seen.size() - 1));
            assertTrue(msgs.contains("verdict"));
            assertTrue("a requested close is not reported as lost", !msgs.toString().contains("closed:"));
        }
    }

    static byte[] serverText(String s) {
        byte[] b = s.getBytes(StandardCharsets.UTF_8);
        byte[] f = new byte[2 + b.length];
        f[0] = (byte) 0x81; f[1] = (byte) b.length;
        System.arraycopy(b, 0, f, 2, b.length);
        return f;
    }
}
