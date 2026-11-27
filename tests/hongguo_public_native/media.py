"""Resolve an official, publicly linked sample just before the native smoke test."""
import importlib.util
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("hg", root / "py" / "红果短剧.py")
hg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hg)
spider = hg.Spider()
number, target = sys.argv[1:3]
required = int(sys.argv[3]) if len(sys.argv) > 3 else 360
samples = ["7706908220253555737"]
if required == 1080:
    samples.extend(["7710503618658454553", "7710822671759461438", "7709153171259542553"])

for sid in samples:
    payload = hg._data(hg.SITE + "/detail?series_id=" + sid, include_player_paths=True)
    slots = hg._public_slots(payload, sid)
    vid = slots.get(int(number))
    if not vid:
        print("series", sid, "episode", number, "has no current public link", flush=True)
        continue
    if required == 1080:
        original = spider.playerContent(hg._PUBLIC_PAGE_LINE, hg._PUBLIC_PAGE_PREFIX + sid + ":" + vid)
        if original.get("url") and original.get("quality") == "1080P":
            result = original
        else:
            # Measure the actual media returned by the site's ordinary guest player.
            # A selected or advertised quality alone does not qualify.
            try:
                url = hg._public_web_media_url(vid)
                info = hg._public_mp4_info(url)
            except (hg.HongguoPluginError, hg.requests.RequestException) as exc:
                print(sid, "public media unavailable:", type(exc).__name__, flush=True)
                continue
            print(sid, "episode", number, "public original:", original.get("quality", "unavailable"),
                  "public MP4:", info["width"], info["height"], info["codec"], flush=True)
            if info["quality"] != required:
                continue
            # A direct public 1080P result must also be available to a normal Spider caller.
            result = spider.playerContent("官網公開 1080P", hg._PUBLIC_HD_SLOT_PREFIX + sid + ":" + number)
    else:
        row = spider.detailContent([sid])["list"][0]
        lines = dict(zip(row["vod_play_from"].split("$$$"), row["vod_play_url"].split("$$$")))
        key = dict(e.split("$", 1) for e in lines[hg._PUBLIC_LINE].split("#"))[number]
        result = spider.playerContent(hg._PUBLIC_LINE, key)
    if not result.get("url") or result.get("parse") != 0:
        continue
    if min(result["width"], result["height"]) != required:
        continue
    print("selected", sid, "episode", number, result["width"], result["height"], flush=True)
    Path(target).write_text(json.dumps(result), encoding="utf-8")
    break
else:
    sys.exit("No verified publicly playable %dP Hongguo episode in this sample set" % required)
