package com.rallydot.app;

import android.net.Uri;
import com.google.androidbrowserhelper.trusted.LauncherActivity;

/** Browser-owned login and signing; this shell has no JS or wallet bridge. */
public final class RallyActivity extends LauncherActivity {
    @Override protected Uri getLaunchingUrl() {
        Uri incoming = getIntent().getData();
        if (incoming != null && "https".equals(incoming.getScheme())
                && "rallydot.com".equalsIgnoreCase(incoming.getHost())
                && incoming.getUserInfo() == null
                && (incoming.getPort() == -1 || incoming.getPort() == 443)
                && isAppPath(incoming.getPath())) {
            return incoming;
        }
        return Uri.parse("https://rallydot.com/?view=home&section=markets&tab=memes");
    }

    private static boolean isAppPath(String path) {
        return "/".equals(path) || "/app".equals(path)
                || "/app/".equals(path) || "/authorize".equals(path);
    }
}
