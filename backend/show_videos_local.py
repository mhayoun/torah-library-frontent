"""
show_videos_local.py
--------------------
Run locally to display ALL videos from every playlist,
sorted by upload_date (newest first), grouped by playlist.

Usage:
    cd backend
    python show_videos_local.py

    # Optional flags:
    python show_videos_local.py --limit 20        # show only top-N videos globally
    python show_videos_local.py --category "הלכה יומית"  # one category only
    python show_videos_local.py --json            # dump raw JSON instead of pretty print

Requirements: same as the backend (see requirements.txt).
Make sure YOUTUBE_API_KEY is set in your .env or as an env-var.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

# ── Make sure we can import the existing backend modules ───────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from playlist_utils import get_raw_playlists, categorize_playlists
from playlist_videos_utils import enrich_structured_playlists

# ── Channel URLs (same as main.py) ────────────────────────────────────────────
TARGET_URLS = [
    "https://www.youtube.com/@Rabbi_Aharon_Butbul/playlists",
    "https://www.youtube.com/@%D7%94%D7%A8%D7%91%D7%90%D7%94%D7%A8%D7%95%D7%9F%D7%91%D7%95%D7%98%D7%91%D7%95%D7%9C-%D7%A97%D7%9E/playlists",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="List all Torah Library videos locally")
    p.add_argument("--limit",    type=int,   default=None, help="Max videos to show globally")
    p.add_argument("--category", type=str,   default=None, help="Filter to one category name")
    p.add_argument("--json",     action="store_true",      help="Output raw JSON")
    return p.parse_args()


def fmt_date(iso: str | None) -> str:
    """Turn an ISO-8601 string into a readable local date."""
    if not iso:
        return "unknown date"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return iso


def separator(char="─", width=72):
    print(char * width)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    if not os.environ.get("YOUTUBE_API_KEY"):
        print("❌  YOUTUBE_API_KEY is not set. Add it to your .env file.")
        sys.exit(1)

    # 1. Discover playlists
    print("🔍  Discovering playlists from channel pages…")
    raw_playlists = get_raw_playlists(TARGET_URLS)
    structured    = categorize_playlists(raw_playlists)

    # 2. Fetch all videos (pass empty existing_ids → fetch everything)
    print("📥  Fetching ALL videos from YouTube API (this may take a minute)…\n")
    catalogue = enrich_structured_playlists(
        structured,
        skip_fallback=False,   # include "אחר" category too
        logger=None,
        existing_ids=set(),    # no skip → download every video
    )

    # 3. Filter category if requested
    if args.category:
        if args.category not in catalogue:
            print(f"❌  Category '{args.category}' not found.")
            print(f"    Available: {', '.join(catalogue.keys())}")
            sys.exit(1)
        catalogue = {args.category: catalogue[args.category]}

    # 4. Build a flat list sorted by upload_date (newest first) for the global view
    all_videos = []
    for category, videos in catalogue.items():
        for v in videos:
            all_videos.append({**v, "_category": category})

    all_videos.sort(
        key=lambda v: v.get("upload_date") or "1970-01-01T00:00:00+00:00",
        reverse=True,
    )

    if args.limit:
        all_videos = all_videos[: args.limit]

    # 5. Re-group the (possibly limited) list by playlist, keeping date order
    playlists: dict[str, list] = {}
    for v in all_videos:
        pl = v.get("playlist") or "Unknown playlist"
        playlists.setdefault(pl, []).append(v)

    # Each playlist is already newest-first because all_videos is sorted

    # ── JSON output ───────────────────────────────────────────────────────────
    if args.json:
        output = {
            pl: [
                {
                    "title":       v["title"],
                    "upload_date": v.get("upload_date"),
                    "url":         v.get("url"),
                    "duration":    v.get("duration"),
                    "view_count":  v.get("view_count"),
                    "category":    v.get("_category"),
                }
                for v in vids
            ]
            for pl, vids in playlists.items()
        }
        #print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    # ── Pretty-print output ───────────────────────────────────────────────────
    total = sum(len(v) for v in playlists.values())
    print()
    separator("═")
    print(f"  📚  TORAH LIBRARY — {total} video(s) across {len(playlists)} playlist(s)")
    print(f"  Sorted newest → oldest  |  {fmt_date(all_videos[0].get('upload_date') if all_videos else None)} … {fmt_date(all_videos[-1].get('upload_date') if all_videos else None)}")
    separator("═")

    for playlist_name, videos in playlists.items():
        print()
        separator()
        category_label = videos[0].get("_category", "") if videos else ""
        print(f"  📂  {playlist_name}  [{category_label}]  — {len(videos)} video(s)")
        separator()

        for i, v in enumerate(videos, 1):
            date      = fmt_date(v.get("upload_date"))
            title     = v.get("title") or "(no title)"
            duration  = v.get("duration") or ""
            views     = v.get("view_count")
            views_str = f"  👁 {views:,}" if views else ""
            dur_str   = f"  ⏱ {duration}" if duration else ""

            print(f"  {i:>4}.  [{date}]  {title}")
            if dur_str or views_str:
                print(f"         {dur_str}{views_str}")

    print()
    separator("═")
    print(f"  ✅  Done — {total} video(s) listed.")
    separator("═")
    print()


if __name__ == "__main__":
    main()
