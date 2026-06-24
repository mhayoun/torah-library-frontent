# playlist_utils.py
import yt_dlp

# Category rules mapping: { "Category Name": [list of keywords to match] }
CATEGORY_MAPPING = {
    "הלכה יומית": ["הלכה יומית"],
    "השיעור השבועי": ["השיעור השבועי", "הרב עובדיה יוסף בוטבול"],
    "שיחת חולין": ["שיחת חולין"],
    "דעת ותורה": ["דעת ותורה"],
    "הליכות עולם": ["הליכות עולם"]
}


def get_raw_playlists(urls):
    """Fetches all playlists from the provided YouTube channel URLs."""
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
                    raw_entries.extend(result['entries'])
            except Exception as e:
                print(f"Error fetching from {url}: {e}")
    return raw_entries


def categorize_playlists(raw_entries):
    """Groups playlists into specified categories using title matching rules."""
    categorized = {category: [] for category in CATEGORY_MAPPING}
    categorized["אחר"] = []

    for entry in raw_entries:
        url = entry.get('url', '')
        _type = entry.get('_type', '')

        if _type != 'url' and 'playlist' not in url:
            continue

        title = entry.get('title', '')
        playlist_data = {"title": title, "url": url}
        matched = False

        for category, keywords in CATEGORY_MAPPING.items():
            if any(keyword in title for keyword in keywords):
                categorized[category].append(playlist_data)
                matched = True
                break

        if not matched:
            categorized["אחר"].append(playlist_data)

    return categorized
