#!/usr/bin/env python3
"""
fetch_videos.py
---------------
Fetches YouTube playlist data and produces categorized_videos.json.

Output format:
    {
        "הלכה יומית": [
            { "id": "...", "title": "...", "url": "...", "duration": "...",
              "view_count": 123, "upload_date": "...", "thumbnail": "..." },
            ...   ← all videos from ALL playlists in this category,
                    deduplicated by video ID, sorted by upload_date DESC
        ],
        "דעת ותורה": [ ... ],
        ...
    }

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
        # Example (fill in your real IDs):
        # "PLDOEgolnX2-xqOhwwvEDh01f6fxjqSFqP",  # תשפ"ו
        # "PLDOEgolnX2-zftmHofud7pjevIeXJrck2",  # תשפ"ה
        # "PLDOEgolnX2-z6nuBPrOrOnsePpitIC_MX",  # תשפ"ד
        # "PLDOEgolnX2-wGNuSAg90ZSTeQLU8n1NWy",  # תשפ"ג
        # "PLDOEgolnX2-yIQMrF6ItTWaE8x5wr81LB",  # תשפ"ב
    ],
    "השיעור השבועי": [
    ],
    "שיחת חולין של תלמידי חכמים": [
    ],
}
# ─────────────────────────────────────────────────────────────────────────────

OUTPUT_FILE = os.path.join(
    os.path.dirname(__file__), "..", "frontend", "public", "categorized_videos.json"
)

_EPOCH = datetime.fromtimestamp(0, tz=timezone.utc).isoformat()


def get_youtube_client():
    if not API_KEY:
        raise ValueError("YOUTUBE_API_KEY environment variable is not set.")
    return build("youtube", "v3", developerKey=API_KEY)


def iso_date(raw: str | None) -> str | None:
    """Convert YouTube publishedAt (2024-05-10T14:30:00Z) to an ISO string."""
    if not raw:
        return None
    try:
        dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return raw


def parse_duration(iso: str) -> str:
    """Convert ISO 8601 duration (PT1H3M12S) → HH:MM:SS or MM:SS."""
    if not iso:
        return "Unknown"
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return iso
    h, mn, s = (int(x or 0) for x in m.groups())
    return f"{h}:{mn:02d}:{s:02d}" if h else f"{mn}:{s:02d}"


def fetch_playlist_videos(youtube, playlist_id: str) -> list[dict]:
    """
    Returns every video in a playlist as a flat list of dicts.
    Batch-fetches duration + view_count via the videos.list endpoint.
    """
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
        items = resp.get("items", [])

        # Collect video IDs for the batch details call
        video_ids = [
            item["contentDetails"]["videoId"]
            for item in items
            if item["contentDetails"].get("videoId")
        ]

        if video_ids:
            details_resp = youtube.videos().list(
                part="contentDetails,statistics",
                id=",".join(video_ids),
            ).execute()
            details_map = {v["id"]: v for v in details_resp.get("items", [])}
        else:
            details_map = {}

        for item in items:
            snippet = item["snippet"]
            vid_id = item["contentDetails"].get("videoId", "")
            if not vid_id:
                continue

            details = details_map.get(vid_id, {})
            duration_raw = details.get("contentDetails", {}).get("duration", "")
            view_count_raw = details.get("statistics", {}).get("viewCount")
            thumbnails = snippet.get("thumbnails", {})

            videos.append({
                "id": vid_id,
                "title": snippet.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "duration": parse_duration(duration_raw),
                "view_count": int(view_count_raw) if view_count_raw else None,
                "upload_date": iso_date(snippet.get("publishedAt")),
                "thumbnail": (
                    thumbnails.get("medium") or thumbnails.get("default") or {}
                ).get("url"),
            })

        next_page = resp.get("nextPageToken")
        if not next_page:
            break

    return videos


def build_catalog(youtube) -> dict:
    """
    For each category, collect all videos from every configured playlist,
    deduplicate by video ID, then sort by upload_date descending.
    """
    catalog = {}

    for category, playlist_ids in CATEGORIES.items():
        seen_ids: set[str] = set()
        all_videos: list[dict] = []

        for pl_id in playlist_ids:
            print(f"  [{category}] Fetching playlist {pl_id} …")
            videos = fetch_playlist_videos(youtube, pl_id)

            for video in videos:
                if video["id"] not in seen_ids:
                    seen_ids.add(video["id"])
                    all_videos.append(video)

        # Sort newest-first; videos with no date fall to the bottom
        all_videos.sort(
            key=lambda v: v["upload_date"] or _EPOCH,
            reverse=True,
        )

        catalog[category] = all_videos
        print(f"  [{category}] {len(all_videos)} unique videos total.")

    return catalog


def main():
    print("Starting YouTube fetch …")
    youtube = get_youtube_client()
    catalog = build_catalog(youtube)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    total = sum(len(videos) for videos in catalog.values())
    print(f"Done. {total} videos written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
