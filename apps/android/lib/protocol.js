/* Messages for WS /ws/stream (see services/api/tell/stream.py). Pure; used by the page and the tests. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.DSProtocol = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  /* Speakerphone audio blends the caller and the room, so the side is always "mix" (the engine caps confidence). */
  function hello(token) {
    return { type: "hello", token: token, sample_rate: 16000, format: "pcm_s16le", side: "mix", source: "android speaker" };
  }
  /* The engine accepts loopback hosts only; so does this app. ?api= is honoured for tests but never for another host. */
  function loopbackApi(search, fallback) {
    try {
      var u = new URL(new URLSearchParams(search).get("api") || fallback);
      if (u.protocol === "http:" && (u.hostname === "localhost" || u.hostname === "127.0.0.1" || u.hostname === "[::1]"))
        return u.origin;
    } catch (e) {}
    return fallback;
  }
  function wsUrl(api, path) { return api.replace(/^http/, "ws") + path; }
  /* The engine's per-install API token (services/api/tell/api_token.py): urlsafe base64, 32..128 chars. Anything else
     (a pasted line with spaces, half a token) is refused so it never gets stored. */
  function cleanToken(t) {
    var s = String(t == null ? "" : t).trim();
    return /^[A-Za-z0-9_-]{32,128}$/.test(s) ? s : "";
  }
  /* Pairing link fragment "#token=..." (never sent to any server). */
  function tokenFromHash(hash) {
    var m = /^#token=([^&]*)$/.exec(String(hash || ""));
    return m ? cleanToken(decodeURIComponent(m[1])) : "";
  }
  function authHeaders(token, extra) {
    var h = {}, k;
    for (k in extra || {}) h[k] = extra[k];
    if (token) h["X-Tell-Token"] = token;
    return h;
  }
  /* EventSource cannot set headers: the live feed (only) takes ?token=; the engine strips it before logging. */
  function feedUrl(api, token) { return api + "/live/events" + (token ? "?token=" + encodeURIComponent(token) : ""); }
  return { hello: hello, loopbackApi: loopbackApi, wsUrl: wsUrl, cleanToken: cleanToken, tokenFromHash: tokenFromHash,
           authHeaders: authHeaders, feedUrl: feedUrl };
});
