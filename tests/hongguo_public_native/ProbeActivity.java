package test.hongguo;

import android.app.Activity;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.util.Log;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Iterator;

public final class ProbeActivity extends Activity implements SurfaceHolder.Callback {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private MediaPlayer player;
    private boolean rendered, requestedSeek, completedSeek, finished;

    public void onCreate(Bundle state) {
        super.onCreate(state);
        SurfaceView view = new SurfaceView(this);
        setContentView(view);
        view.getHolder().addCallback(this);
    }

    private void finishTest(boolean ok, String note) {
        if (finished) return;
        finished = true;
        Log.i("HGNative", (ok ? "PASS " : "FAIL ") + note);
        handler.removeCallbacksAndMessages(null);
        if (player != null) player.release();
        player = null;
        finish();
    }

    private final Runnable tick = new Runnable() {
        public void run() {
            if (finished || player == null) return;
            int pos = player.getCurrentPosition();
            int width = player.getVideoWidth(), height = player.getVideoHeight();
            if (rendered && Math.min(width, height) == 1080 && pos > 350 && !requestedSeek) {
                Log.i("HGNative", "rendered " + width + "x" + height + " at " + pos);
                requestedSeek = true;
                player.seekTo(5000L, MediaPlayer.SEEK_CLOSEST);
            } else if (completedSeek && player.isPlaying() && pos >= 5250) {
                finishTest(true, "playing after seek at " + pos);
                return;
            }
            handler.postDelayed(this, 100);
        }
    };

    public void surfaceCreated(SurfaceHolder holder) {
        if (finished || player != null) return;
        try {
            String encoded = getIntent().getStringExtra("source");
            JSONObject src = new JSONObject(new String(Base64.decode(encoded, Base64.DEFAULT), StandardCharsets.UTF_8));
            JSONObject input = src.getJSONObject("header");
            HashMap<String, String> headers = new HashMap<>();
            for (Iterator<String> it = input.keys(); it.hasNext();) {
                String key = it.next();
                headers.put(key, input.getString(key));
            }
            player = new MediaPlayer();
            player.setOnErrorListener((p, what, extra) -> { finishTest(false, "media " + what + "/" + extra); return true; });
            player.setOnInfoListener((p, what, extra) -> {
                if (what == MediaPlayer.MEDIA_INFO_VIDEO_RENDERING_START) rendered = true;
                return false;
            });
            player.setOnSeekCompleteListener(p -> completedSeek = true);
            player.setOnPreparedListener(p -> { p.setVolume(0f, 0f); p.start(); handler.post(tick); });
            player.setDisplay(holder);
            player.setDataSource(this, Uri.parse(src.getString("url")), headers);
            player.prepareAsync();
            handler.postDelayed(() -> finishTest(false, "timeout"), 65000);
        } catch (Exception ex) {
            finishTest(false, ex.getClass().getSimpleName());
        }
    }

    public void surfaceChanged(SurfaceHolder holder, int format, int w, int h) {}
    public void surfaceDestroyed(SurfaceHolder holder) {}
}
