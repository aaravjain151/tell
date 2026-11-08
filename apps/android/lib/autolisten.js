/* Auto-listen (start listening when a call is answered): wording and status line. Pure; used by the page and the tests.
   The behaviour lives in the native app (CallMonitor, CallListenService); see docs/android/ANDROID.md "Auto-listen". */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.DSAuto = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  var CONSENT = "When you answer a call, Tell listens through your microphone in speaker mode and sends the audio only to your own computer over the USB cable. Nothing is recorded or stored. Tell the other person if your state requires it.";
  var ON = "Auto-listen is on: Tell starts when you answer";

  var MISSING = {
    phone: "Tell lost the Phone permission it uses to see that a call was answered.",
    microphone: "Tell lost the microphone permission.",
    notifications: "Notifications are off for Tell, so it cannot show Listen or Stop.",
  };

  /* st: the native getAutoListen() result, or null outside the installed app. Returns {line, sub, tone}. */
  function status(st) {
    if (!st || !st.available) return { line: "Auto-listen needs the installed Tell app", sub: "The browser cannot see phone calls.", tone: "off" };
    var miss = st.missing || [];
    if (st.enabled && miss.length) return { line: "Auto-listen is paused", sub: MISSING[miss[0]] || "A permission is missing.", tone: "warn" };
    if (st.enabled) {
      if (st.state === "listening" || st.state === "starting") return { line: "Listening to this call", sub: "Started when you answered. Stop any time.", tone: "on" };
      if (st.state === "silent") return { line: "Listening to this call", sub: "No sound is reaching the microphone. Is the call on speaker?", tone: "warn" };
      return { line: ON, sub: st.background === "tap"
        ? "If Tell is not on screen, Android asks you to tap Listen in a notification. Put the call on speaker."
        : "Put the call on speaker after you answer.", tone: "on" };
    }
    return { line: "Auto-listen is off", sub: "Turn it on and Tell starts listening when you answer a call.", tone: "off" };
  }

  /* Why listening ended, from the native "ended:<outcome>" state. */
  function endedText(state) {
    var o = String(state || "").split(":")[1] || "stopped";
    return {
      not_connected: "Tell could not reach your computer; plug in the USB cable.",
      refused: "Your computer refused Tell. Start the engine with make api-android.",
      busy: "Another listening session is open on your computer.",
      lost: "Lost contact with your computer. Check the USB cable.",
      mic_failed: "Tell could not open the microphone.",
    }[o] || "";
  }

  return { CONSENT: CONSENT, ON: ON, status: status, endedText: endedText };
});
