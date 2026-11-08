package dev.doublespeak.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

import dev.doublespeak.app.call.Wording;

/**
 * Auto-listen notifications. None of them carries caller text, a number or a verdict.
 *  - "Tell is listening to this call" (ongoing, foreground-service notification, Stop + Turn on speaker)
 *  - "Call answered. Tap Listen" (high priority; the start path on Android 11+ when Tell is in the background)
 *  - "Tell could not reach your computer; plug in the USB cable" (and the other end-of-session notices)
 */
final class Notices {
    static final String CH_LISTEN = "listening", CH_PROMPT = "call_prompt", CH_NOTICE = "notices";
    static final int ID_LISTEN = 7002, ID_PROMPT = 7003, ID_NOTICE = 7004;
    private static final int FLAGS = PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT;

    private Notices() {}

    static void channels(Context c) {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        NotificationChannel l = new NotificationChannel(CH_LISTEN, "Listening", NotificationManager.IMPORTANCE_LOW);
        l.setDescription("Shown while Tell listens through the microphone.");
        l.setShowBadge(false);
        NotificationChannel p = new NotificationChannel(CH_PROMPT, "Call answered", NotificationManager.IMPORTANCE_HIGH);
        p.setDescription("Asks you to tap Listen when a call is answered and Tell cannot start by itself.");
        p.setShowBadge(false);
        NotificationChannel n = new NotificationChannel(CH_NOTICE, "Connection", NotificationManager.IMPORTANCE_DEFAULT);
        n.setDescription("Tells you when Tell could not listen, for example when the computer is not connected.");
        nm.createNotificationChannel(l);
        nm.createNotificationChannel(p);
        nm.createNotificationChannel(n);
    }

    @SuppressWarnings("deprecation")
    private static Notification.Builder builder(Context c, String ch) {
        return Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(c, ch) : new Notification.Builder(c);
    }

    static PendingIntent openApp(Context c) {
        Intent open = new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        return PendingIntent.getActivity(c, 0, open, FLAGS);
    }

    static PendingIntent stop(Context c) {
        return PendingIntent.getService(c, 1, new Intent(c, CallListenService.class).setAction(CallListenService.ACTION_STOP), FLAGS);
    }

    static PendingIntent listen(Context c) {
        Intent i = new Intent(c, CallListenService.class).setAction(CallListenService.ACTION_START).putExtra(CallListenService.EXTRA_TAPPED, true);
        return Build.VERSION.SDK_INT >= 26 ? PendingIntent.getForegroundService(c, 2, i, FLAGS) : PendingIntent.getService(c, 2, i, FLAGS);
    }

    static PendingIntent speaker(Context c) {
        Intent i = new Intent(c, SpeakerActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_NO_ANIMATION);
        return PendingIntent.getActivity(c, 3, i, FLAGS);
    }

    static PendingIntent repost(Context c) {
        return PendingIntent.getService(c, 4, new Intent(c, CallListenService.class).setAction(CallListenService.ACTION_REPOST), FLAGS);
    }

    @SuppressWarnings("deprecation")
    static Notification listening(Context c, boolean silent) {
        channels(c);
        String text = silent ? Wording.SILENT_TEXT : Wording.LISTENING_TEXT;
        Notification.Builder b = builder(c, CH_LISTEN).setSmallIcon(R.drawable.ic_stat_mic)
            .setContentTitle(Wording.LISTENING_TITLE).setContentText(text)
            .setStyle(new Notification.BigTextStyle().bigText(text))
            .setContentIntent(openApp(c)).setOngoing(true).setOnlyAlertOnce(true).setShowWhen(true).setUsesChronometer(true)
            .setCategory(Notification.CATEGORY_SERVICE)
            .setDeleteIntent(repost(c))          // Android 14+ lets the user swipe it away; it comes straight back while listening
            .addAction(new Notification.Action.Builder(0, Wording.ACTION_STOP, stop(c)).build())
            .addAction(new Notification.Action.Builder(0, Wording.ACTION_SPEAKER, speaker(c)).build());
        if (Build.VERSION.SDK_INT >= 31) b.setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE);
        if (Build.VERSION.SDK_INT < 26) b.setPriority(Notification.PRIORITY_LOW);
        return b.build();
    }

    @SuppressWarnings("deprecation")
    static void prompt(Context c) {
        channels(c);
        Notification.Builder b = builder(c, CH_PROMPT).setSmallIcon(R.drawable.ic_stat_mic)
            .setContentTitle(Wording.PROMPT_TITLE).setContentText(Wording.PROMPT_TEXT)
            .setStyle(new Notification.BigTextStyle().bigText(Wording.PROMPT_TEXT))
            .setContentIntent(listen(c)).setAutoCancel(true).setCategory(Notification.CATEGORY_REMINDER)
            .addAction(new Notification.Action.Builder(0, Wording.ACTION_LISTEN, listen(c)).build())
            .addAction(new Notification.Action.Builder(0, Wording.ACTION_SPEAKER, speaker(c)).build());
        if (Build.VERSION.SDK_INT >= 26) b.setTimeoutAfter(10 * 60 * 1000L);
        else b.setPriority(Notification.PRIORITY_HIGH).setDefaults(Notification.DEFAULT_VIBRATE);
        nm(c).notify(ID_PROMPT, b.build());
    }

    static void cancelPrompt(Context c) { nm(c).cancel(ID_PROMPT); }

    @SuppressWarnings("deprecation")
    static void notice(Context c, String text) {
        channels(c);
        Notification.Builder b = builder(c, CH_NOTICE).setSmallIcon(R.drawable.ic_stat_mic)
            .setContentTitle(Wording.NOT_CONNECTED_TITLE).setContentText(text)
            .setStyle(new Notification.BigTextStyle().bigText(text))
            .setContentIntent(openApp(c)).setAutoCancel(true);
        if (Build.VERSION.SDK_INT >= 26) b.setTimeoutAfter(30 * 60 * 1000L);
        nm(c).notify(ID_NOTICE, b.build());
    }

    static void cancelNotice(Context c) { nm(c).cancel(ID_NOTICE); }

    /** The OS silenced the microphone during the call. The engine and cable are fine; say so honestly. */
    @SuppressWarnings("deprecation")
    static void blocked(Context c) {
        channels(c);
        String big = Wording.MIC_BLOCKED_TEXT + " " + Wording.MIC_BLOCKED_SUB;
        Notification.Builder b = builder(c, CH_NOTICE).setSmallIcon(R.drawable.ic_stat_mic)
            .setContentTitle(Wording.MIC_BLOCKED_TITLE).setContentText(Wording.MIC_BLOCKED_TEXT)
            .setStyle(new Notification.BigTextStyle().bigText(big))
            .setContentIntent(openApp(c)).setAutoCancel(true);
        if (Build.VERSION.SDK_INT >= 26) b.setTimeoutAfter(30 * 60 * 1000L);
        nm(c).notify(ID_NOTICE, b.build());
    }

    static NotificationManager nm(Context c) { return (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE); }
}
