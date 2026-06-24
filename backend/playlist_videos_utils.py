import os
import json
import re
from datetime import datetime, timezone
from googleapiclient.discovery import build

from playlist_utils import CATEGORY_MAPPING, find_matching_categories
from debug_logger import DebugLogger

API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
DEBUG = True
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "categorized_videos.json")

_EPOCH = datetime.fromtimestamp(0, tz=timezone.utc).isoformat()


# ── helpers ───────────────────────────────────────────────────────────────────

def iso_date(raw):
    """Convert YouTube publishedAt (2024-05-10T14:30:00Z) to an ISO string."""
    if not raw:
        return None
    try:
        dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return raw


def parse_duration(iso):
    """Convert ISO 8601 duration (PT1H3M12S) -> HH:MM:SS or MM:SS."""
    if not iso:
        return "Unknown"
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return iso
    h, mn, s = (int(x or 0) for x in m.groups())
    return f"{h}:{mn:02d}:{s:02d}" if h else f"{mn}:{s:02d}"


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


def check_video_category_mismatch(video_title, current_category, playlist_title, playlist_url, logger: DebugLogger | None = None):
    """
    Checks whether a video's own title matches a category keyword set that is
    DIFFERENT from the category its containing playlist was filed under.
    Logs the mismatch to the debug logger (and stdout in DEBUG mode).

    Returns the set of matched categories that differ from current_category,
    or an empty set if there is no mismatch.
    """
    if not video_title:
        return set()

    matches = find_matching_categories(video_title)
    matched_categories = {c for c, _ in matches}

    if matched_categories and current_category not in matched_categories:
        msg = (
            f"[DEBUG][video-mismatch] ⚠️ Video '{video_title}' looks like it "
            f"belongs to {sorted(matched_categories)}, but is filed under "
            f"'{current_category}' because it's inside playlist "
            f"'{playlist_title}' ({playlist_url})"
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


def fetch_videos_for_playlist(playlist_url, existing_ids, category=None, playlist_title=None, logger: DebugLogger | None = None):
    """
    Hits YouTube API, checks for new videos, and breaks early when a duplicate
    is found (incremental update). For every NEW video, also fetches its
    duration/view_count via a batched videos.list() call.

    Tracks success/fail counts per video and logs errors to `logger`.

    Returns:
        tuple(
            videos            – list of video objects that belong in `category`,
            mismatched_videos – list of (video_obj, target_categories) for videos
                               whose title suggests a different category.
        )
    """
    playlist_id = extract_playlist_id(playlist_url)
    videos = []
    mismatched_videos = []   # [(video_obj, set_of_target_categories)]
    next_page_token = None
    should_continue = True

    try:
        youtube = build("youtube", "v3", developerKey=API_KEY)

        while should_continue:
            try:
                request = youtube.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=next_page_token
                )
                response = request.execute()
            except Exception as page_exc:
                if logger:
                    logger.log_playlist_fetch_error(
                        playlist_url=playlist_url,
                        playlist_title=playlist_title or "",
                        error=page_exc,
                    )
                print(f"❌ Failed to fetch page for {playlist_url}: {page_exc}")
                break

            items = response.get("items", [])
            if not items:
                break

            # Find genuinely new items before the more expensive details call.
            page_new_items = []
            for item in items:
                content_details = item.get("contentDetails", {})
                video_id = content_details.get("videoId")

                if video_id in existing_ids:
                    if DEBUG:
                        print(f"   [DEBUG] Hit known video ID: {video_id}. Stopping pagination early.")
                    should_continue = False
                    break

                page_new_items.append(item)

            if page_new_items:
                video_ids = [
                    it["contentDetails"]["videoId"]
                    for it in page_new_items
                    if it.get("contentDetails", {}).get("videoId")
                ]

                details_map = {}
                if video_ids:
                    try:
                        details_resp = youtube.videos().list(
                            part="contentDetails,statistics",
                            id=",".join(video_ids),
                        ).execute()
                        details_map = {v["id"]: v for v in details_resp.get("items", [])}
                    except Exception as details_exc:
                        # Non-fatal: we'll just proceed without enrichment data.
                        print(f"   ⚠️  Could not fetch video details for batch: {details_exc}")
                        if logger:
                            logger.log_video_error(
                                playlist_url=playlist_url,
                                playlist_title=playlist_title or "",
                                error=details_exc,
                                extra="Failed to fetch details batch; affected IDs: " + ", ".join(video_ids),
                            )

                for item in page_new_items:
                    snippet = item.get("snippet", {})
                    content_details = item.get("contentDetails", {})
                    video_id = content_details.get("videoId")
                    title = snippet.get("title")

                    try:
                        if DEBUG:
                            safe_title = (title or "").encode('utf-8', errors='replace').decode('utf-8')
                            print(f"   [DEBUG NEW ITEM] {safe_title}")

                        details = details_map.get(video_id, {})
                        duration_raw = details.get("contentDetails", {}).get("duration", "")
                        view_count_raw = details.get("statistics", {}).get("viewCount")
                        thumbnails = snippet.get("thumbnails", {})

                        video_obj = {
                            "id": video_id,
                            "title": title,
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                            "duration": parse_duration(duration_raw),
                            "view_count": int(view_count_raw) if view_count_raw else None,
                            "upload_date": iso_date(snippet.get("publishedAt")),
                            "thumbnail": (
                                thumbnails.get("medium") or thumbnails.get("default") or {}
                            ).get("url"),
                        }

                        # Record this video as "found" in the logger
                        if logger:
                            logger.record_found(
                                playlist_url=playlist_url,
                                playlist_title=playlist_title or "",
                            )

                        # Check for category mismatch; collect for rerouting later
                        target_categories: set = set()
                        if category is not None:
                            target_categories = check_video_category_mismatch(
                                title, category, playlist_title, playlist_url, logger=logger
                            )

                        if target_categories:
                            # Mismatch detected – queue for rerouting; exclude from
                            # the primary category list so it doesn't appear twice.
                            mismatched_videos.append((video_obj, target_categories))
                        else:
                            videos.append(video_obj)

                        # Record success in the logger
                        if logger:
                            logger.record_success(
                                playlist_url=playlist_url,
                                playlist_title=playlist_title or "",
                            )

                    except Exception as video_exc:
                        print(f"   ❌ Error processing video '{title}' ({video_id}): {video_exc}")
                        if logger:
                            logger.log_video_error(
                                playlist_url=playlist_url,
                                playlist_title=playlist_title or "",
                                video_id=video_id or "",
                                video_title=title or "",
                                error=video_exc,
                            )

            if not should_continue:
                break

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

    except Exception as e:
        print(f"❌ Failed to fetch updates for {playlist_url}: {e}")
        if logger:
            logger.log_playlist_fetch_error(
                playlist_url=playlist_url,
                playlist_title=playlist_title or "",
                error=e,
            )

    return videos, mismatched_videos


def enrich_structured_playlists(structured_data, skip_fallback=True, logger: DebugLogger | None = None):
    """
    Takes freshly categorized playlists, fetches all their videos,
    and returns a flat dict where each category key maps directly to
    a deduplicated list of video objects sorted by upload_date DESC.

    When a video's title signals a different category than the playlist it
    lives in, it is rerouted to the correct category bucket (not duplicated).
    If it already exists there, it is silently skipped.

    Pass a DebugLogger instance to capture errors and per-playlist stats.
    """
    cached_playlists_map, existing_ids = load_cached_videos_map(OUTPUT_FILE)

    print("\nDeep scanning matched playlists for inner videos...")

    # Pre-build result buckets for ALL categories (so rerouted videos always
    # have a destination, even if that category had no playlists of its own).
    result: dict[str, list] = {cat: [] for cat in structured_data}
    # seen_ids per category – used to deduplicate across playlists AND reroutes
    seen_ids: dict[str, set] = {cat: set() for cat in structured_data}

    # ── Pass 1: collect old (cached) videos into their buckets ────────────────
    for category, playlists in structured_data.items():
        if skip_fallback and category == "אחר":
            continue
        if not playlists:
            continue
        for playlist in playlists:
            playlist_url = playlist.get("url")
            old_videos = cached_playlists_map.get(playlist_url, [])
            for video in old_videos:
                vid_id = video.get("id")
                if vid_id and vid_id not in seen_ids[category]:
                    seen_ids[category].add(vid_id)
                    result[category].append(video)

    # ── Pass 2: fetch new videos, apply rerouting, record stats ───────────────
    # Collect rerouted videos separately so they can be inserted after all
    # playlists in the target category have been processed (avoids ordering
    # issues and keeps the dedup logic clean).
    pending_reroutes: list[tuple[dict, str, str, str, str]] = []
    # [(video_obj, target_category, original_category, playlist_title, playlist_url)]

    for category, playlists in structured_data.items():
        if skip_fallback and category == "אחר":
            continue
        if not playlists:
            continue

        print(f"\n📂 Processing Category: {category}")

        for playlist in playlists:
            playlist_url = playlist.get("url")
            playlist_title = playlist.get("title")
            print(f"   -> Scanning: '{playlist_title}'")

            new_videos, mismatched_videos = fetch_videos_for_playlist(
                playlist_url, existing_ids,
                category=category,
                playlist_title=playlist_title,
                logger=logger,
            )

            # Insert correctly-categorized new videos
            added_count = 0
            for video in new_videos:
                vid_id = video.get("id")
                if vid_id and vid_id not in seen_ids[category]:
                    seen_ids[category].add(vid_id)
                    result[category].append(video)
                    added_count += 1

            # Queue mismatched videos for rerouting
            for video_obj, target_categories in mismatched_videos:
                # Pick the first matching target category (CATEGORY_MAPPING order)
                target_category = next(
                    (cat for cat in structured_data if cat in target_categories),
                    None,
                )
                if target_category:
                    pending_reroutes.append(
                        (video_obj, target_category, category, playlist_title, playlist_url)
                    )
                else:
                    # Target category not in result keys (e.g. not in structured_data)
                    # – fall back to original category so the video isn't lost.
                    vid_id = video_obj.get("id")
                    if vid_id and vid_id not in seen_ids[category]:
                        seen_ids[category].add(vid_id)
                        result[category].append(video_obj)
                        added_count += 1

            if logger:
                logger.record_added(
                    playlist_url=playlist_url,
                    playlist_title=playlist_title or "",
                    count=added_count,
                )
            print(f"      Found {len(new_videos) + len(mismatched_videos)} new  |  Added to '{category}': {added_count}")

            # Write per-playlist summary now that counts are recorded
            if logger:
                logger.log_playlist_summary(
                    playlist_url=playlist_url,
                    playlist_title=playlist_title or "",
                )

    # ── Pass 3: apply reroutes ─────────────────────────────────────────────────
    for video_obj, target_category, original_category, playlist_title, playlist_url in pending_reroutes:
        vid_id = video_obj.get("id")
        video_title = video_obj.get("title", "")

        if target_category not in seen_ids:
            seen_ids[target_category] = set()
        if target_category not in result:
            result[target_category] = []

        if vid_id and vid_id in seen_ids[target_category]:
            if DEBUG:
                print(
                    f"   [DEBUG][reroute] Skipping duplicate '{video_title}' "
                    f"(already in '{target_category}')"
                )
            continue

        if vid_id:
            seen_ids[target_category].add(vid_id)
        result[target_category].append(video_obj)

        print(
            f"   ↪  Rerouted '{video_title}' from '{original_category}' "
            f"→ '{target_category}'"
        )
        if logger:
            logger.record_rerouted(
                playlist_url=playlist_url,
                playlist_title=playlist_title or "",
            )
            logger.log_category_reroute(
                video_title=video_title,
                video_id=vid_id or "",
                original_category=original_category,
                target_category=target_category,
                playlist_title=playlist_title,
                playlist_url=playlist_url,
            )

    # ── Sort each category newest-first ───────────────────────────────────────
    for category in result:
        result[category].sort(
            key=lambda v: v.get("upload_date") or _EPOCH,
            reverse=True,
        )
        if result[category]:
            print(f"   ✅ {len(result[category])} unique videos in '{category}'")

    return result
