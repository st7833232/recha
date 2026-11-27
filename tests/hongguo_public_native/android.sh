#!/usr/bin/env bash
set -euo pipefail
src="$PWD/tests/hongguo_public_native"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
build="$(find "$ANDROID_HOME/build-tools" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -1)"
jar="$(find "$ANDROID_HOME/platforms" -name android.jar | sort -V | tail -1)"
mkdir "$tmp/classes" "$tmp/dex"
javac -encoding UTF-8 -source 8 -target 8 -classpath "$jar" -d "$tmp/classes" "$src/ProbeActivity.java"
"$build/d8" --lib "$jar" --min-api 26 --output "$tmp/dex" "$tmp"/classes/test/hongguo/*.class
"$build/aapt2" link -I "$jar" --manifest "$src/AndroidManifest.xml" -o "$tmp/probe.apk"
(cd "$tmp/dex" && zip -q "$tmp/probe.apk" classes.dex)
"$build/zipalign" -f 4 "$tmp/probe.apk" "$tmp/aligned.apk"
keytool -genkeypair -keystore "$tmp/debug.p12" -storepass android -alias probe -keyalg RSA -validity 2 -dname CN=Preview >/dev/null 2>&1
"$build/apksigner" sign --ks "$tmp/debug.p12" --ks-pass pass:android --out "$tmp/probe-signed.apk" "$tmp/aligned.apk"
adb install -r "$tmp/probe-signed.apk"
adb shell input keyevent 82
for ep in 1 3; do
    python "$src/media.py" "$ep" "$tmp/media.json" 1080
    adb shell am force-stop test.hongguo
    adb logcat -c
    payload="$(base64 -w0 "$tmp/media.json")"
    adb shell am start -n test.hongguo/.ProbeActivity --es source "$payload" >/dev/null
    for _ in $(seq 1 75); do
        status="$(adb logcat -d -s HGNative:I '*:S')"
        if [[ "$status" == *"PASS "* || "$status" == *"FAIL "* ]]; then break; fi
        sleep 1
    done
    echo "Episode $ep"
    echo "$status"
    [[ "$status" == *"PASS "* ]]
done
