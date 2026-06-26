import os
import json
import re
from datetime import datetime, timezone
from googleapiclient.discovery import build

from playlist_utils import CATEGORY_MAPPING, find_matching_categories
from debug_logger import DebugLogger

API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
DEBUG   = True

# Legacy path kept for backward-compat (local script mode still writes here)
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "categorized_videos.json")

_EPOCH = datetime.fromtimestamp(0, tz=timezone.utc).isoformat()


# ── helpers ───────────────────────────────────────────────────────────────────

def iso_date(raw):
    if not raw:
        return None
    try:
        dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return raw


def parse_duration(iso):
    if not iso:
        return "Unknown"
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return iso
    h, mn, s = (int(x or 0) for x in m.groups())
    return f"{h}:{mn:02d}:{s:02d}" if h else f"{mn}:{s:02d}"


def load_cached_videos_map(filename=OUTPUT_FILE):
    """
    Reads the on-disk JSON and returns:
      cached_map   : { playlist_url: [video, ...] }
      existing_ids : set of all known video IDs
    Only used in LOCAL (script) mode. In API mode, existing_ids is passed
    directly from Redis by main.py.
    """
    cached_map   = {}
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
                url    = playlist.get("url")
                videos = playlist.get("videos", [])
                if url:
                    cached_map[url] = videos
                    for video in videos:
                        if "id" in video:
                            existing_ids.add(video["id"])

        if DEBUG:
            print(f"[DEBUG] Loaded cached data: {len(cached_map)} playlists, {len(existing_ids)} IDs.")
    except Exception as e:
        print(f"⚠️  Warning: Could not read cache file ({e}).")

    return cached_map, existing_ids


def extract_playlist_id(url):
    match = re.search(r"[&?]list=([^&]+)", url)
    return match.group(1) if match else url


def check_video_category_mismatch(video_title, current_category, playlist_title, playlist_url, logger=None):
    if not video_title:
        return set()
    matches = find_matching_categories(video_title)
    matched_categories = {c for c, _ in matches}
    if matched_categories and current_category not in matched_categories:
        msg = (
            f"[DEBUG][video-mismatch] ⚠️ Video '{video_title}' looks like "
            f"{sorted(matched_categories)}, filed under '{current_category}' "
            f"(playlist '{playlist_title}')"
        )
        if DEBUG:
            print(msg)
        if logger:
            logger.log_category_mismatch(
                video_title=video_title,
                current_category=current_category,
                matched_categories=matched_categories,
                playlist_title=playlist_title,
                playlist_url=playlist_url,
            )
        return matched_categories
    return set()


def fetch_videos_for_playlist(
    playlist_url,
    existing_ids,
    category=None,
    playlist_title=None,
    logger=None,
):
    """
    Fetches NEW videos only from a playlist where new videos are appended
    at the END (oldest-first order on YouTube).

    Strategy:
      1. Paginate through ALL pages to reach the last page.
      2. On the last page, scan items in REVERSE order (end → beginning).
      3. Collect items whose ID is not in existing_ids.
      4. Stop scanning the moment a known ID is hit — everything before it
         (earlier in the playlist) is already stored.
      5. Batch-fetch details only for the collected new IDs.

    This is the inverse of the previous strategy which assumed newest-first
    ordering. Because the playlist is oldest-first, new videos appear at
    the end, so we must reach the last page before we can detect them.

    Returns (videos, mismatched_videos).
    """
    playlist_id = extract_playlist_id(playlist_url)
    videos      = []
    mismatched  = []

    try:
        youtube = build("youtube", "v3", developerKey=API_KEY)

        # ── Phase 1: paginate to collect ALL pages of raw items ───────────────
        # We must reach the last page to find new videos, so we can't short-
        # circuit pagination early. We only store (videoId, item) tuples to
        # keep memory minimal.
        all_items  = []   # list of raw playlistItem dicts, in playlist order
        next_page  = None

        while True:
            try:
                resp = youtube.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=next_page,
                ).execute()
            except Exception as exc:
                if logger:
                    logger.log_playlist_fetch_error(
                        playlist_url=playlist_url,
                        playlist_title=playlist_title or "",
                        error=exc,
                    )
                print(f"❌ Failed page fetch for {playlist_url}: {exc}")
                break

            items = resp.get("items", [])
            if not items:
                break

            all_items.extend(items)

            next_page = resp.get("nextPageToken")
            if not next_page:
                break   # reached the last page

        if DEBUG:
            print(f"   [DEBUG] Fetched {len(all_items)} total items from playlist.")

        if not all_items:
            return videos, mismatched

        # ── Phase 2: scan in REVERSE — newest additions are at the end ────────
        # Walk backwards through all_items; collect unknowns; stop at first
        # known ID (everything before it in the playlist is already stored).
        new_items = []
        for item in reversed(all_items):
            vid_id = item.get("contentDetails", {}).get("videoId")
            if not vid_id:
                continue
            if vid_id in existing_ids:
                if DEBUG:
                    print(f"   [DEBUG] Known ID {vid_id} — stopping reverse scan.")
                break   # hit the boundary between known and new
            new_items.append(item)

        if DEBUG:
            print(f"   [DEBUG] {len(new_items)} new item(s) found after reverse scan.")

        if not new_items:
            return videos, mismatched

        # ── Phase 3: batch-fetch details for new IDs only ─────────────────────
        vid_ids = [
            it["contentDetails"]["videoId"]
            for it in new_items
            if it.get("contentDetails", {}).get("videoId")
        ]
        details_map = {}
        if vid_ids:
            try:
                det = youtube.videos().list(
                    part="contentDetails,statistics",
                    id=",".join(vid_ids),
                ).execute()
                details_map = {v["id"]: v for v in det.get("items", [])}
            except Exception as det_exc:
                print(f"   ⚠️  Details batch failed: {det_exc}")
                if logger:
                    logger.log_video_error(
                        playlist_url=playlist_url,
                        playlist_title=playlist_title or "",
                        error=det_exc,
                        extra="details batch; IDs: " + ", ".join(vid_ids),
                    )

        # ── Phase 4: build video objects ──────────────────────────────────────
        for item in new_items:
            snippet = item.get("snippet", {})
            vid_id  = item["contentDetails"].get("videoId")
            title   = snippet.get("title")

            try:
                det    = details_map.get(vid_id, {})
                thumbs = snippet.get("thumbnails", {})
                video_obj = {
                    "id":          vid_id,
                    "title":       title,
                    "url":         f"https://www.youtube.com/watch?v={vid_id}",
                    "duration":    parse_duration(det.get("contentDetails", {}).get("duration", "")),
                    "view_count":  int(det["statistics"]["viewCount"]) if det.get("statistics", {}).get("viewCount") else None,
                    "upload_date": iso_date(snippet.get("publishedAt")),
                    "thumbnail":   (thumbs.get("medium") or thumbs.get("default") or {}).get("url"),
                    "category":    category or "אחר",
                    "playlist":    playlist_title,
                }

                if logger:
                    logger.record_found(playlist_url=playlist_url, playlist_title=playlist_title or "")

                target_cats = set()
                if category:
                    target_cats = check_video_category_mismatch(
                        title, category, playlist_title, playlist_url, logger=logger
                    )

                if target_cats:
                    mismatched.append((video_obj, target_cats))
                else:
                    videos.append(video_obj)

                if logger:
                    logger.record_success(playlist_url=playlist_url, playlist_title=playlist_title or "")

            except Exception as exc:
                print(f"   ❌ Error processing '{title}' ({vid_id}): {exc}")
                if logger:
                    logger.log_video_error(
                        playlist_url=playlist_url,
                        playlist_title=playlist_title or "",
                        video_id=vid_id or "",
                        video_title=title or "",
                        error=exc,
                    )

    except Exception as exc:
        print(f"❌ Failed to fetch playlist {playlist_url}: {exc}")
        if logger:
            logger.log_playlist_fetch_error(
                playlist_url=playlist_url,
                playlist_title=playlist_title or "",
                error=exc,
            )

    return videos, mismatched


def enrich_structured_playlists(
    structured_data,
    skip_fallback=True,
    logger=None,
    existing_ids=None,          # NEW: passed from Redis in API mode
):
    """
    Fetches new videos for all playlists and returns a flat catalogue dict:
      { category: [video, ...] }

    In API mode, pass `existing_ids` (a set of known video IDs from Redis).
    In local script mode, existing_ids is loaded from the on-disk JSON.

    Videos whose title signals a different category are rerouted.
    """
    # In local script mode, fall back to reading from disk
    if existing_ids is None:
        _, existing_ids = load_cached_videos_map(OUTPUT_FILE)

    print("\nScanning playlists for new videos...")

    result:    dict[str, list] = {cat: [] for cat in structured_data}
    seen_ids:  dict[str, set]  = {cat: set() for cat in structured_data}

    pending_reroutes = []  # [(video_obj, target_cat, orig_cat, pl_title, pl_url)]

    for category, playlists in structured_data.items():
        if skip_fallback and category == "אחר":
            continue
        if not playlists:
            continue

        print(f"\n📂 {category}")

        for playlist in playlists:
            pl_url   = playlist.get("url")
            pl_title = playlist.get("title")
            print(f"   → {pl_title}")

            new_vids, mismatched = fetch_videos_for_playlist(
                pl_url,
                existing_ids,
                category=category,
                playlist_title=pl_title,
                logger=logger,
            )

            added = 0
            for v in new_vids:
                vid_id = v.get("id")
                if vid_id and vid_id not in seen_ids[category]:
                    seen_ids[category].add(vid_id)
                    result[category].append(v)
                    added += 1

            for v, target_cats in mismatched:
                target = next((c for c in structured_data if c in target_cats), None)
                if target:
                    pending_reroutes.append((v, target, category, pl_title, pl_url))
                else:
                    vid_id = v.get("id")
                    if vid_id and vid_id not in seen_ids[category]:
                        seen_ids[category].add(vid_id)
                        result[category].append(v)
                        added += 1

            if logger:
                logger.record_added(playlist_url=pl_url, playlist_title=pl_title or "", count=added)
                logger.log_playlist_summary(playlist_url=pl_url, playlist_title=pl_title or "")

            print(f"      +{added} new videos added to '{category}'")

    # Apply reroutes
    for v, target_cat, orig_cat, pl_title, pl_url in pending_reroutes:
        vid_id = v.get("id")
        if target_cat not in seen_ids:
            seen_ids[target_cat] = set()
        if target_cat not in result:
            result[target_cat] = []
        if vid_id and vid_id in seen_ids[target_cat]:
            continue
        if vid_id:
            seen_ids[target_cat].add(vid_id)
        v["category"] = target_cat  # ← ADD THIS LINE
        result[target_cat].append(v)
        print(f"   ↪  Rerouted '{v.get('title')}': '{orig_cat}' → '{target_cat}'")
        if logger:
            logger.record_rerouted(playlist_url=pl_url, playlist_title=pl_title or "")
            logger.log_category_reroute(
                video_title=v.get("title", ""),
                video_id=vid_id or "",
                original_category=orig_cat,
                target_category=target_cat,
                playlist_title=pl_title,
                playlist_url=pl_url,
            )

    # Sort newest-first per category
    for cat in result:
        result[cat].sort(key=lambda x: x.get("upload_date") or _EPOCH, reverse=True)
        if result[cat]:
            print(f"   ✅ {len(result[cat])} videos in '{cat}'")

    return result
