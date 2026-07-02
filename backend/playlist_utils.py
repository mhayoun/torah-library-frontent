# playlist_utils.py
import yt_dlp

DEBUG = True

# Category rules mapping: { "Category Name": [list of keywords to match] }
# NOTE: order matters - categorize_playlists checks categories in this order
# and stops at the first match. Keep more specific phrases ABOVE generic ones
# (e.g. a rabbi's name) to avoid accidental cross-matches.
CATEGORY_MAPPING = {
    "הלכה יומית": ["הלכה יומית"],
    "השיעור השבועי": ["השיעור השבועי", "הרב עובדיה יוסף בוטבול"],
    "שיחת חולין": ["שיחת חולין"],
    "דעת ותורה": ["דעת ותורה"],
    "הליכות עולם": ["הליכות עולם"]
}

# Per-source-channel category overrides.
#
# Some channels (e.g. Rabbi Nissim Trabelsy's) don't put any of the usual
# keywords in their playlist/video titles, so title matching alone would
# dump everything from them into "אחר". Any entry whose ORIGIN url (the
# TARGET_URL it was discovered under - see `_source_url` set in
# get_raw_playlists) contains one of these markers is force-assigned to
# the given category - but only if the title also contains the required
# keyword below, so unrelated videos on the same channel (e.g. other
# rabbis' guest lectures) aren't swept in by mistake.
#
# This also covers channel tabs like '/streams' and '/videos', which list
# raw videos rather than named playlists - those get flagged with
# kind="video" in categorize_playlists so enrich_structured_playlists can
# fetch them by video ID directly instead of treating them as playlists.
CHANNEL_CATEGORY_OVERRIDES = {
    "youtube.com/@nissimtrabelsy3957": {
        "category": "השיעור השבועי",
        "required_keyword": "בוטבול",
    },
}


def get_raw_playlists(urls):
    """Fetches all playlists (and, for channel tabs like /streams or /videos,
    individual videos) from the provided YouTube channel URLs.

    Each returned entry is tagged with '_source_url' = the TARGET_URL it
    came from, so downstream code (category overrides, video-vs-playlist
    detection) knows its origin.
    """
    ydl_opts = {
        'extract_flat': 'in_playlist',
        'skip_download': True,
        'quiet': True
    }

    raw_entries = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for url in urls:
            try:
                result = ydl.extract_info(url, download=False)
                if result and 'entries' in result:
                    for entry in result['entries']:
                        if not entry:
                            continue  # yt-dlp can yield None for unavailable/private items
                        entry['_source_url'] = url
                        raw_entries.append(entry)
            except Exception as e:
                print(f"Error fetching from {url}: {e}")
    return raw_entries


def find_matching_categories(title):
    """
    Returns a list of ALL categories whose keywords appear in `title`.
    Used for debug purposes to catch ambiguous titles that match more
    than one category (the first one wins in categorize_playlists, but
    that may not be the "correct" one).
    """
    matches = []
    for category, keywords in CATEGORY_MAPPING.items():
        for keyword in keywords:
            if keyword in title:
                matches.append((category, keyword))
    return matches


def categorize_playlists(raw_entries):
    """Groups playlists into specified categories using title matching rules."""
    categorized = {category: [] for category in CATEGORY_MAPPING}
    categorized["אחר"] = []

    for entry in raw_entries:
        url = entry.get('url', '')
        _type = entry.get('_type', '')
        source_url = entry.get('_source_url', '')

        if _type != 'url' and 'playlist' not in url:
            continue

        title = entry.get('title', '')
        video_id = entry.get('id')

        # Channel tabs like '/streams' and '/videos' list individual videos,
        # not named playlists (unlike '/playlists', which lists real
        # playlists with a proper `list=` URL). Flag these so
        # enrich_structured_playlists knows to fetch them directly by video
        # ID instead of trying to treat `url` as a playlist.
        is_direct_video = (
            'watch?v=' in url
            or 'shorts/' in url
            or source_url.rstrip('/').endswith(('/streams', '/videos'))
        )

        playlist_data = {
            "title": title,
            "url": url,
            "kind": "video" if is_direct_video else "playlist",
        }
        if is_direct_video and video_id:
            playlist_data["video_id"] = video_id

        # 1) Explicit per-channel override. If this entry's source URL
        #    matches a channel override, it is handled ENTIRELY by this
        #    branch: either it goes to the override's category (title has
        #    the required keyword), or it is dropped completely (title is
        #    missing the required keyword) - it does NOT fall through to
        #    keyword matching or "אחר" in either case.
        matched_rule = None
        for marker, rule in CHANNEL_CATEGORY_OVERRIDES.items():
            if marker in source_url:
                matched_rule = rule
                break

        if matched_rule:
            required_keyword = matched_rule.get("required_keyword")
            if required_keyword and required_keyword not in (title or ""):
                if DEBUG:
                    print(
                        f"[DEBUG][categorize] ⛔ SKIPPED '{title}' - channel override "
                        f"matched ({source_url}) but title is missing required keyword "
                        f"'{required_keyword}'; not added to any category."
                    )
                continue  # deliberately not added anywhere, not even "אחר"

            override = matched_rule["category"]
            categorized.setdefault(override, [])
            if DEBUG:
                print(f"[DEBUG][categorize] '{title}' -> '{override}' (channel override: {source_url})")

            # IMPORTANT: passing this playlist's title check only means the
            # PLAYLIST's own title had the keyword - it says nothing about
            # the individual videos inside it (a playlist named "הרב בוטבול"
            # can still contain totally unrelated videos someone saved into
            # it). Stamp the required_keyword onto the entry so the fetch
            # step re-checks it against EACH video's own title before
            # adding it - same "skip entirely, don't insert anywhere" rule.
            if required_keyword:
                playlist_data["required_keyword"] = required_keyword

            categorized[override].append(playlist_data)
            continue

        # 2) Fall back to keyword matching on the title.
        all_matches = find_matching_categories(title)

        if DEBUG:
            if not all_matches:
                print(f"[DEBUG][categorize] '{title}' -> NO MATCH (אחר)")
            elif len(all_matches) > 1:
                # Ambiguous: title matches keywords from more than one category.
                # The first one (by CATEGORY_MAPPING order) wins - flag it so
                # you can see if that's actually the wrong choice.
                chosen_category, chosen_keyword = all_matches[0]
                others = ", ".join(f"{c} (kw='{k}')" for c, k in all_matches[1:])
                print(
                    f"[DEBUG][categorize] ⚠️ AMBIGUOUS '{title}' -> chose "
                    f"'{chosen_category}' (kw='{chosen_keyword}'), also matched: {others}"
                )
            else:
                category, keyword = all_matches[0]
                print(f"[DEBUG][categorize] '{title}' -> '{category}' (kw='{keyword}')")

        if all_matches:
            chosen_category = all_matches[0][0]
            categorized[chosen_category].append(playlist_data)
        else:
            categorized["אחר"].append(playlist_data)

    return categorized
