import os
import json
import re
import traceback
from googleapiclient.discovery import build

API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
DEBUG = True
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "categorized_videos.json")


def load_cached_videos_map(filename=OUTPUT_FILE):
    """
    Reads the file on disk and maps playlist URLs to their already saved video arrays.
    Returns: A dictionary of { playlist_url: [list_of_videos] } and a set of all video IDs.
    """
    cached_map = {}
    existing_ids = set()

    if not os.path.exists(filename):
        return cached_map, existing_ids

    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)

        for category, playlists in data.items():
            if not isinstance(playlists, list):
                continue
            for playlist in playlists:
                url = playlist.get("url")
                videos = playlist.get("videos", [])
                if url:
                    cached_map[url] = videos
                    for video in videos:
                        if "id" in video:
                            existing_ids.add(video.get("id"))

        if DEBUG:
            print(f"[DEBUG] Loaded cached data for {len(cached_map)} playlists containing {len(existing_ids)} unique video IDs.")
    except Exception as e:
        print(f"⚠️  Warning: Could not read existing cache file safely ({e}).")

    return cached_map, existing_ids


def extract_playlist_id(url):
    """Helper to extract the playlist ID from a YouTube URL."""
    match = re.search(r"[&?]list=([^&]+)", url)
    extracted = match.group(1) if match else url
    return extracted


def fetch_videos_for_playlist(playlist_url, existing_ids):
    """Hits YouTube API, checks for new videos, and breaks early when a duplicate is found."""
    playlist_id = extract_playlist_id(playlist_url)
    videos = []
    next_page_token = None
    new_items_count = 0
    should_continue = True

    try:
        youtube = build("youtube", "v3", developerKey=API_KEY)

        while should_continue:
            request = youtube.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()
            items = response.get("items", [])

            if not items:
                break

            for item in items:
                snippet = item.get("snippet", {})
                content_details = item.get("contentDetails", {})
                video_id = content_details.get("videoId")
                title = snippet.get("title")

                if video_id in existing_ids:
                    if DEBUG:
                        print(f"   [DEBUG] Hit known video ID: {video_id}. Stopping pagination early.")
                    should_continue = False
                    break

                new_items_count += 1
                if DEBUG:
                    safe_title = title.encode('utf-8', errors='replace').decode('utf-8')
                    print(f"   [DEBUG NEW ITEM] {safe_title}")

                videos.append({
                    "id": video_id,
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "duration": "Unknown",
                    "view_count": None,
                    "upload_date": snippet.get("publishedAt")
                })

            if not should_continue:
                break

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

    except Exception as e:
        print(f"❌ Failed to fetch updates for {playlist_url}: {e}")

    return videos


def enrich_structured_playlists(structured_data, skip_fallback=True):
    """
    Takes freshly categorized playlists, fetches all their videos,
    and returns a flat dict where each category key maps directly to
    a deduplicated list of video objects sorted by upload_date DESC:

        {
            "הלכה יומית": [ {id, title, url, duration, ...}, ... ],
            ...
        }
    """
    cached_playlists_map, existing_ids = load_cached_videos_map(OUTPUT_FILE)

    print("\nDeep scanning matched playlists for inner videos...")

    result = {}
    _epoch = "1970-01-01T00:00:00+00:00"

    for category, playlists in structured_data.items():
        if skip_fallback and category == "אחר":
            continue
        if not playlists:
            continue

        print(f"\n📂 Processing Category: {category}")

        seen_ids = set()
        all_videos = []

        for playlist in playlists:
            playlist_url = playlist.get('url')
            playlist_title = playlist.get('title')
            print(f"   -> Scanning: '{playlist_title}'")

            old_videos = cached_playlists_map.get(playlist_url, [])
            new_videos = fetch_videos_for_playlist(playlist_url, existing_ids)

            for video in (new_videos + old_videos):
                vid_id = video.get("id")
                if vid_id and vid_id not in seen_ids:
                    seen_ids.add(vid_id)
                    all_videos.append(video)

        # Sort newest-first; videos without a date fall to the bottom
        all_videos.sort(
            key=lambda v: v.get("upload_date") or _epoch,
            reverse=True,
        )

        result[category] = all_videos
        print(f"   ✅ {len(all_videos)} unique videos in '{category}'")

    return result