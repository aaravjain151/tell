package dev.doublespeak.app;

// SCAFFOLD, NOT WIRED IN. This file sits outside android/app/src so the existing debug APK build is unchanged.
// To enable it, follow docs/BLOCK-SPAM.md ("Android plan"): copy it to android/app/src/main/java/dev/doublespeak/app/,
// add the <service> block from AndroidManifest.snippet.xml, and run the role request in the app. Not built, not installed.
//
// Local only: the list is read from a private file in the app's own storage (blocklist_numbers.txt, one E.164 number
// per line, written by the app from GET /blocklist/export?format=csv or calldirectory). No network, no logging of numbers.

import android.content.Context;
import android.telecom.Call;
import android.telecom.CallScreeningService;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.util.HashSet;
import java.util.Set;

public class BlockScreeningService extends CallScreeningService {
    static final String LIST_FILE = "blocklist_numbers.txt";
    // false = silence the ring and let it reach the call log as a missed call; true = reject outright.
    static final boolean REJECT = false;

    @Override
    public void onScreenCall(Call.Details details) {
        CallResponse.Builder r = new CallResponse.Builder();
        // Only incoming calls with a visible number can be matched. Hidden/private numbers are never blocked here.
        if (details.getCallDirection() == Call.Details.DIRECTION_INCOMING && details.getHandle() != null
                && "tel".equals(details.getHandle().getScheme())) {
            String number = normalise(details.getHandle().getSchemeSpecificPart());
            if (number != null && loadList(this).contains(number)) {
                r.setDisallowCall(true)
                 .setRejectCall(REJECT)
                 .setSilenceCall(!REJECT)
                 .setSkipCallLog(false)          // keep it in the log so the user can see what was stopped
                 .setSkipNotification(true);
            }
        }
        respondToCall(details, r.build());       // an empty response lets the call through
    }

    /** Digits only, '+' kept; matches the server's E.164 output for numbers that already carry a country code. */
    static String normalise(String raw) {
        if (raw == null) return null;
        String s = raw.replaceAll("[^0-9+]", "");
        if (s.startsWith("00")) s = "+" + s.substring(2);
        return s.matches("\\+[1-9][0-9]{6,14}") ? s : null;
    }

    static Set<String> loadList(Context c) {
        Set<String> out = new HashSet<>();
        File f = new File(c.getFilesDir(), LIST_FILE);
        if (!f.exists()) return out;
        try (BufferedReader br = new BufferedReader(new FileReader(f))) {
            String line;
            while ((line = br.readLine()) != null) {
                String n = normalise(line.trim());
                if (n != null) out.add(n);
            }
        } catch (Exception e) {
            // Never log the exception message or the file contents: they hold phone numbers.
        }
        return out;
    }
}
