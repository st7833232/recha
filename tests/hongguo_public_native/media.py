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
sid = "7706908220253555737"
row = spider.detailContent([sid])["list"][0]
lines = dict(zip(row["vod_play_from"].split("$$$"), row["vod_play_url"].split("$$$")))
slots = dict(e.split("$", 1) for e in lines[hg._PUBLIC_LINE].split("#"))
result = spider.playerContent(hg._PUBLIC_LINE, slots[sys.argv[1]])
assert result["url"] and result["parse"] == 0 and result["quality"] == "360P"
Path(sys.argv[2]).write_text(json.dumps(result), encoding="utf-8")
