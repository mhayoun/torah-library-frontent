#!/usr/bin/env python3
"""
fetch_videos.py
---------------
Fetches YouTube playlist data and produces categorized_videos.json.

Requirements:
    pip install google-api-python-client python-dotenv

Usage:
    Set YOUTUBE_API_KEY in a .env file or as an environment variable.
    Configure CATEGORIES below with your actual playlist IDs.
    Run: python fetch_videos.py
"""

import os
import json
import re
from datetime import datetime, timezone
from dotenv import load_dotenv
from googleapiclient.discovery import build

load_dotenv()

API_KEY = os.environ.get("YOUTUBE_API_KEY", "")

# ── Configure your categories and playlist IDs here ──────────────────────────
CATEGORIES = {
    "דעת ותורה": [
        # Add playlist IDs, e.g. "PLxxxxxxxxxxxxxxxxxxxx"
    ],
    "הליכות עולם": [
    ],
    "הלכה יומית": [
    ],
    "השיעור השבועי": [
    ],
    "שיחת חולין של תלמידי חכמים": [
    ],
}
# ─────────────────────────────────────────────────────────────────────────────

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "categorized_videos.json")


def get_youtube_client():
    if not API_KEY:
        raise ValueError("YOUTUBE_API_KEY environment variable is not set.")
    return build("youtube", "v3", developerKey=API_KEY)


def iso_date(raw: str | None) -> str | None:
    """Convert YouTube publishedAt (2024-05-10T14:30:00Z) to ISO string."""
    if not raw:
        return None
    try:
        dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return raw


def parse_duration(iso: str) -> str:
    """Convert ISO 8601 duration (PT1H3M12S) to HH:MM:SS or MM:SS."""
    if not iso:
        return "Unknown"
    pattern = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
    m = pattern.match(iso)
    if not m:
        return iso
    h, mn, s = (int(x or 0) for x in m.groups())
    if h:
        return f"{h}:{mn:02d}:{s:02d}"
    return f"{mn}:{s:02d}"


def fetch_playlist_info(youtube, playlist_id: str) -> dict:
    resp = youtube.playlists().list(
        part="snippet,contentDetails",
        id=playlist_id
    ).execute()
    items = resp.get("items", [])
    if not items:
        return {"title": "Unknown Playlist", "video_count": 0}
    item = items[0]
    return {
        "title": item["snippet"]["title"],
        "video_count": item["contentDetails"]["itemCount"],
    }


def fetch_playlist_videos(youtube, playlist_id: str) -> list:
    videos = []
    next_page = None

    while True:
        params = dict(
            part="snippet,contentDetails",
            playlistId=playlist_id,
            maxResults=50,
        )
        if next_page:
            params["pageToken"] = next_page

        resp = youtube.playlistItems().list(**params).execute()
        video_ids = [
            item["contentDetails"]["videoId"]
            for item in resp.get("items", [])
            if item["contentDetails"].get("videoId")
        ]

        # Batch-fetch durations and view counts
        if video_ids:
            details_resp = youtube.videos().list(
                part="contentDetails,statistics",
                id=",".join(video_ids)
            ).execute()
            details_map = {
                v["id"]: v for v in details_resp.get("items", [])
            }
        else:
            details_map = {}

        for item in resp.get("items", []):
            snippet = item["snippet"]
            vid_id = item["contentDetails"].get("videoId", "")
            details = details_map.get(vid_id, {})
            duration_raw = details.get("contentDetails", {}).get("duration", "")
            view_count_raw = details.get("statistics", {}).get("viewCount")

            videos.append({
                "id": vid_id,
                "title": snippet.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "duration": parse_duration(duration_raw),
                "view_count": int(view_count_raw) if view_count_raw else None,
                "upload_date": iso_date(snippet.get("publishedAt")),
                "thumbnail": (snippet.get("thumbnails", {}).get("medium", {}) or
                              snippet.get("thumbnails", {}).get("default", {})).get("url"),
            })

        next_page = resp.get("nextPageToken")
        if not next_page:
            break

    return videos


def build_catalog(youtube) -> dict:
    catalog = {}

    for category, playlist_ids in CATEGORIES.items():
        catalog[category] = []
        for pl_id in playlist_ids:
            print(f"  [{category}] Fetching playlist {pl_id} …")
            info = fetch_playlist_info(youtube, pl_id)
            videos = fetch_playlist_videos(youtube, pl_id)
            catalog[category].append({
                "title": info["title"],
                "url": f"https://www.youtube.com/playlist?list={pl_id}",
                "video_count": len(videos),
                "videos": videos,
            })

    return catalog


def main():
    print("Starting YouTube fetch …")
    youtube = get_youtube_client()
    catalog = build_catalog(youtube)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    total = sum(
        sum(pl["video_count"] for pl in pls)
        for pls in catalog.values()
    )
    print(f"Done. {total} videos written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
