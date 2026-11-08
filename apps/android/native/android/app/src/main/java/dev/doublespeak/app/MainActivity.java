package dev.doublespeak.app;

import android.os.Bundle;
import android.view.WindowManager;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(ListenServicePlugin.class);
        super.onCreate(savedInstanceState);
        // The page also asks for a Screen Wake Lock while listening; this keeps the screen on while the app is in front.
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }
}
