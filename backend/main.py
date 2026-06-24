# main.py
import json
import os
from playlist_utils import get_raw_playlists, categorize_playlists
from playlist_videos_utils import enrich_structured_playlists, OUTPUT_FILE

if __name__ == "__main__":
    target_urls = [
        "https://www.youtube.com/@Rabbi_Aharon_Butbul/playlists",
        "https://www.youtube.com/@%D7%94%D7%A8%D7%91%D7%90%D7%94%D7%A8%D7%95%D7%9F%D7%91%D7%95%D7%98%D7%91%D7%95%D7%9C-%D7%A97%D7%9E/playlists"
    ]

    # 1. Fetch raw playlist feeds
    print("Extracting playlists from YouTube...")
    raw_playlists = get_raw_playlists(target_urls)

    # 2. Categorize them using the custom utility rules
    print(f"Found {len(raw_playlists)} items. Categorizing...")
    structured_data = categorize_playlists(raw_playlists)

    # 3. Output results
    print("\nCategorized Playlists Result:")
    print(json.dumps(structured_data, ensure_ascii=False, indent=4))

    # 4. Extract the videos from YouTube for each found playlist
    final_data = enrich_structured_playlists(structured_data, skip_fallback=True)

    # 5. Write enriched dataset to disk (→ frontend/public/categorized_videos.json)
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=4)

    print(f"\n✨ Success! Results saved to '{OUTPUT_FILE}'")
