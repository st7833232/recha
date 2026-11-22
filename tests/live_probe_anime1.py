# -*- coding: utf-8 -*-
"""Best-effort Anime1 live API smoke. No movie bytes saved, cookies never printed.

This check is separate from deterministic tests: the upstream may deny CI traffic.
"""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_anime1 import module


def main():
    spider = module.Spider()
    catalog = spider._catalog()
    if not catalog:
        raise SystemExit("UPSTREAM_BLOCKED: Anime1 official and metadata fallback unavailable")
    poster_count = sum(bool(x["cover"]) for x in catalog)
    print("CATALOG", len(catalog), "POSTERS", poster_count,
          "COVERAGE", round(100 * poster_count / len(catalog), 1))
    if not poster_count:
        raise SystemExit("NO_POSTERS")

    example = next((x for x in catalog[:30] if x.get("index")), None)
    if not example:
        raise SystemExit("NO_EPISODE_INDEX")
    episodes = module._episodes_from_index(example["index"])
    if not episodes:
        raise SystemExit("NO_EPISODES")
    episode_url = episodes[-1][1]
    print("EPISODE URL", "valid" if module._safe_episode(episode_url) else "invalid")
    markup = spider._page_html(episode_url)
    if not markup:
        raise SystemExit("UPSTREAM_BLOCKED: episode HTML")
    print("PAGE", "video-js" in markup, "API PARAM", "data-apireq" in markup)
    if "data-apireq" not in markup:
        raise SystemExit("API_PARAM_UNAVAILABLE")
    play = spider.playerContent("Anime1", episode_url)
    if not play.get("url"):
        raise SystemExit("STREAM_NOT_RESOLVED: no playable URL or required cookies")
    print("STREAM RESOLVED", True, "HTTPS", play["url"].startswith("https://"),
          "HAS_COOKIE", bool(play.get("header", {}).get("Cookie")))
    headers = {**play.get("header", {}), "Range": "bytes=0-1023"}
    try:
        with requests.get(play["url"], headers=headers, timeout=(8, 15), stream=True) as resp:
            print("CDN RANGE HTTP", resp.status_code)
            if resp.status_code not in (200, 206):
                raise SystemExit("CDN_RANGE_REJECTED")
            part = next(resp.iter_content(chunk_size=1024), b"")
            if not part:
                raise SystemExit("CDN_NO_BYTES")
            print("CDN SMALL RANGE RECEIVED", bool(part))
    except requests.RequestException as error:
        raise SystemExit("CDN_HTTP_ERROR: %s" % type(error).__name__)

    # Synopsis is sourced separately from Bangumi and shown on the detail page.
    # Search one well-known title, avoiding a large number of public API calls.
    known = next((x for x in catalog if x["title"] == "葬送的芙莉蓮"), None)
    if known:
        metadata = spider._metadata(known)
        print("BANGUMI SYNOPSIS", bool(metadata.get("summary")),
              "ARTWORK", bool(metadata.get("pic")))
    else:
        print("BANGUMI SYNOPSIS", "not checked: known fixture not in catalog")


if __name__ == "__main__":
    main()
