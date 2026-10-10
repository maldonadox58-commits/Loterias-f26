package com.f26.resultados;

import android.Manifest;
import android.app.Activity;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.webkit.JavascriptInterface;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public class MainActivity extends Activity {
    private WebView web;
    private static final String URL = "file:///android_asset/www/index.html";
    private static final String OFFLINE =
        "<html><body style='font-family:sans-serif;background:#eef2f0;color:#10221c;padding:32px;text-align:center'>"
      + "<h2 style='color:#0e7a52'>Resultados de Loter&iacute;as F-26</h2>"
      + "<p>No hay conexi&oacute;n a internet.</p>"
      + "<button style='font-size:18px;padding:12px 24px;border:0;border-radius:10px;background:#0e7a52;color:#fff' "
      + "onclick=\"location.href='" + URL + "'\">Reintentar</button></body></html>";

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#eef2f0"));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setAllowFileAccess(true);
        s.setAllowUniversalAccessFromFileURLs(true);
        web.addJavascriptInterface(new Puente(), "F26Android");
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel c = new NotificationChannel("alarmas", "Alarmas de activación", NotificationManager.IMPORTANCE_HIGH);
            getSystemService(NotificationManager.class).createNotificationChannel(c);
        }
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
        }
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                if (u.getScheme() != null && u.getScheme().equals("file")) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception e) { }
                return true;
            }
            @Override
            public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
                if (r.isForMainFrame()) v.loadDataWithBaseURL(URL, OFFLINE, "text/html", "utf-8", null);
            }
        });
        setContentView(web);
        if (b != null) web.restoreState(b); else web.loadUrl(URL);
    }

    class Puente {
        private int id = 1;
        @JavascriptInterface
        public void notificar(String titulo, String cuerpo) {
            Intent i = new Intent(MainActivity.this, MainActivity.class);
            i.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
            PendingIntent pi = PendingIntent.getActivity(MainActivity.this, 0, i, PendingIntent.FLAG_IMMUTABLE);
            android.app.Notification.Builder b = Build.VERSION.SDK_INT >= 26
                ? new android.app.Notification.Builder(MainActivity.this, "alarmas")
                : new android.app.Notification.Builder(MainActivity.this);
            b.setSmallIcon(R.mipmap.ic_launcher).setContentTitle(titulo).setContentText(cuerpo)
             .setStyle(new android.app.Notification.BigTextStyle().bigText(cuerpo))
             .setAutoCancel(true).setContentIntent(pi);
            getSystemService(NotificationManager.class).notify(id++, b.build());
        }
    }

    @Override protected void onSaveInstanceState(Bundle o) { super.onSaveInstanceState(o); web.saveState(o); }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }
}
