"""
debug_sync.py
-------------
Diagnoses why _build_response() is not inserting new videos into Redis
when cours_response is empty.

It runs the EXACT same steps as _build_response() but prints a detailed
report at each checkpoint so you can see exactly where videos are lost.

Usage:
    cd backend
    python debug_sync.py

    # To also clear cours_response beforehand (simulate the real trigger):
    python debug_sync.py --clear-cache

    # To inspect what is already stored in Redis without running a sync:
    python debug_sync.py --inspect-redis

    # Combine: clear cache, run sync, full report
    python debug_sync.py --clear-cache --verbose
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from redis.asyncio import Redis as aioredis
from playlist_utils import get_raw_playlists, categorize_playlists, find_matching_categories
from playlist_videos_utils import enrich_structured_playlists, fetch_videos_for_playlist, extract_playlist_id

TARGET_URLS = [
    "https://www.youtube.com/@Rabbi_Aharon_Butbul/playlists",
    "https://www.youtube.com/@%D7%94%D7%A8%D7%91%D7%90%D7%94%D7%A8%D7%95%D7%9F%D7%91%D7%95%D7%98%D7%91%D7%95%D7%9C-%D7%A97%D7%9E/playlists",
]

CACHE_TTL = 6 * 3600


# ── Formatting helpers ────────────────────────────────────────────────────────

def sep(char="─", w=72): print(char * w)
def ok(msg):   print(f"  ✅  {msg}")
def warn(msg): print(f"  ⚠️   {msg}")
def err(msg):  print(f"  ❌  {msg}")
def info(msg): print(f"  ℹ️   {msg}")
def hdr(msg):  sep("═"); print(f"  {msg}"); sep("═")


# ── Redis connection ──────────────────────────────────────────────────────────

async def get_redis():
    url = os.environ.get("REDIS_URL")
    if not url:
        err("REDIS_URL is not set in .env")
        sys.exit(1)
    try:
        r = await aioredis.from_url(url, decode_responses=True)
        await r.ping()
        return r
    except Exception as e:
        err(f"Cannot connect to Redis: {e}")
        sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 0 — Inspect Redis as-is
# ══════════════════════════════════════════════════════════════════════════════

async def inspect_redis(r, verbose=False):
    hdr("STEP 0 — Redis state before sync")

    # cours_response
    cached = await r.get("cours_response")
    ttl    = await r.ttl("cours_response")
    if cached:
        body = json.loads(cached)
        ok(f"cours_response  EXISTS  (TTL {ttl}s ≈ {ttl//3600}h {(ttl%3600)//60}m)")
        info(f"  total={body.get('total')}  new={body.get('new')}  last_sync={body.get('last_sync')}")
        cats = body.get("catalog", {})
        for cat, vids in cats.items():
            info(f"    {cat}: {len(vids)} videos")
    else:
        warn("cours_response  MISSING  (this is what triggers _build_response)")

    # cours_full
    full_raw = await r.get("cours_full")
    if full_raw:
        full = json.loads(full_raw)
        ok(f"cours_full      EXISTS  ({len(full)} videos stored permanently)")
        if verbose and full:
            newest = sorted(full, key=lambda v: v.get("upload_date") or "", reverse=True)
            info(f"  Newest stored : [{newest[0].get('upload_date','?')}] {newest[0].get('title','?')}")
            info(f"  Oldest stored : [{newest[-1].get('upload_date','?')}] {newest[-1].get('title','?')}")
    else:
        warn("cours_full      MISSING  (first run ever — will fetch everything)")

    # last_sync_date
    last_sync = await r.get("last_sync_date")
    if last_sync:
        ok(f"last_sync_date  = {last_sync}")
    else:
        warn("last_sync_date  MISSING")

    print()
    return full_raw, cached


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — existing_ids
# ══════════════════════════════════════════════════════════════════════════════

async def check_existing_ids(r):
    hdr("STEP 1 — existing_ids loaded from cours_full")

    full_raw = await r.get("cours_full")
    existing: list[dict] = json.loads(full_raw) if full_raw else []
    existing_ids: set[str] = {v["id"] for v in existing if v.get("id")}

    if not existing_ids:
        warn("existing_ids is EMPTY — this means every video on YouTube will be treated as NEW")
        warn("If you still see 0 new videos after sync, the bug is downstream (YouTube API or merge step)")
    else:
        ok(f"existing_ids has {len(existing_ids)} known video IDs")

    print()
    return existing, existing_ids


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Playlist discovery
# ══════════════════════════════════════════════════════════════════════════════

def check_playlist_discovery():
    hdr("STEP 2 — Playlist discovery (yt-dlp)")

    try:
        raw = get_raw_playlists(TARGET_URLS)
    except Exception as e:
        err(f"get_raw_playlists() raised: {e}")
        return None, None

    if not raw:
        err("get_raw_playlists() returned EMPTY list — yt-dlp found no playlists")
        err("Possible causes: channel URL wrong, YouTube blocked the request, yt-dlp outdated")
        return None, None

    ok(f"yt-dlp found {len(raw)} raw playlist entries")

    structured = categorize_playlists(raw)
    total_playlists = sum(len(v) for v in structured.values())
    ok(f"categorize_playlists() produced {total_playlists} categorised playlists across {len(structured)} categories")

    for cat, playlists in structured.items():
        if playlists:
            info(f"  {cat}: {len(playlists)} playlist(s)")
        else:
            warn(f"  {cat}: 0 playlists (category is empty)")

    uncategorised = structured.get("אחר", [])
    if uncategorised:
        warn(f"  {len(uncategorised)} playlist(s) fell into 'אחר' (unmatched keywords)")
        for pl in uncategorised:
            warn(f"    → '{pl.get('title')}' — no keyword matched CATEGORY_MAPPING")

    print()
    return raw, structured


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Per-playlist fetch probe (one playlist at a time)
# ══════════════════════════════════════════════════════════════════════════════

def check_per_playlist_fetch(structured, existing_ids, verbose=False):
    hdr("STEP 3 — Per-playlist YouTube API fetch (incremental logic probe)")

    total_new = 0

    for category, playlists in structured.items():
        if category == "אחר":
            continue  # skip_fallback=True mirrors _build_response behaviour
        if not playlists:
            continue

        for pl in playlists:
            pl_url   = pl.get("url", "")
            pl_title = pl.get("title", "")
            pl_id    = extract_playlist_id(pl_url)

            print()
            info(f"Playlist : {pl_title}")
            info(f"Category : {category}")
            info(f"URL      : {pl_url}")
            info(f"ID       : {pl_id}")

            if not pl_id or pl_id == pl_url:
                err("Could not extract a playlist ID from the URL — yt-dlp may have returned a bad URL")
                continue

            try:
                new_vids, mismatched = fetch_videos_for_playlist(
                    pl_url,
                    existing_ids,
                    category=category,
                    playlist_title=pl_title,
                    logger=None,
                )
            except Exception as e:
                err(f"fetch_videos_for_playlist() raised: {e}")
                continue

            # ── Diagnosis ────────────────────────────────────────────────────

            if not new_vids and not mismatched:
                # The most common reason: every video in the playlist is in existing_ids
                # so the early-stop triggered on page 1
                warn(f"0 new videos found — EARLY STOP triggered")
                warn(f"  This means the first video in the YouTube playlist is already in cours_full")
                warn(f"  If new videos WERE uploaded since last sync, check that:")
                warn(f"    1. The video appears at the TOP of the playlist on YouTube (newest-first order)")
                warn(f"    2. cours_full actually contains the expected video IDs")
            else:
                ok(f"{len(new_vids)} new video(s)  +  {len(mismatched)} rerouted")
                total_new += len(new_vids) + len(mismatched)
                if verbose:
                    for v in new_vids[:5]:
                        info(f"    [{v.get('upload_date','?')}] {v.get('title','?')}")
                    if len(new_vids) > 5:
                        info(f"    … and {len(new_vids)-5} more")

            # ── Category mismatch check ───────────────────────────────────────
            if mismatched:
                warn(f"  {len(mismatched)} video(s) will be REROUTED away from '{category}':")
                for v, target_cats in mismatched[:3]:
                    warn(f"    '{v.get('title')}' → {sorted(target_cats)}")

    print()
    if total_new == 0:
        warn("TOTAL new videos across all playlists = 0")
        warn("This is why _build_response adds nothing: there is genuinely nothing new,")
        warn("OR the early-stop is firing incorrectly (see per-playlist output above).")
    else:
        ok(f"TOTAL new videos found across all playlists = {total_new}")

    return total_new


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Merge logic simulation
# ══════════════════════════════════════════════════════════════════════════════

def check_merge(existing, existing_ids, structured, verbose=False):
    hdr("STEP 4 — Merge logic (mirrors _build_response exactly)")

    fresh_catalogue = enrich_structured_playlists(
        structured,
        skip_fallback=True,
        logger=None,
        existing_ids=existing_ids,
    )

    fresh_flat: list[dict] = [
        v for videos in fresh_catalogue.values() for v in videos
    ]
    fresh_ids  = {v["id"] for v in fresh_flat if v.get("id")}
    new_count  = len(fresh_ids - existing_ids)

    ok(f"fresh_flat      : {len(fresh_flat)} video(s) returned by enrich_structured_playlists()")
    ok(f"Genuinely new   : {new_count}  (fresh_ids − existing_ids)")

    if new_count == 0 and len(fresh_flat) > 0:
        warn("fresh_flat is non-empty but new_count=0")
        warn("This means every video returned by enrich is already in existing_ids")
        warn("The early-stop in fetch_videos_for_playlist() is not working as expected,")
        warn("OR cours_full already contains those IDs from a previous run.")

    all_videos: list[dict] = fresh_flat + [
        v for v in existing if v.get("id") not in fresh_ids
    ]
    ok(f"all_videos after merge: {len(all_videos)}")

    # ── Category re-correction ────────────────────────────────────────────────
    corrections = 0
    for v in all_videos:
        matches = find_matching_categories(v.get("title", ""))
        if matches:
            correct_cat = matches[0][0]
            if correct_cat != v.get("category", "אחר"):
                corrections += 1
    if corrections:
        warn(f"{corrections} video(s) will have their category corrected during merge")
    else:
        ok("No category corrections needed")

    print()
    return all_videos, new_count


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — Write to Redis (dry-run by default)
# ══════════════════════════════════════════════════════════════════════════════

async def check_redis_write(r, all_videos, new_count, dry_run=True):
    hdr("STEP 5 — Redis write" + (" (DRY RUN — pass --write to commit)" if dry_run else " (LIVE WRITE)"))

    catalogue: dict[str, list] = {}
    for v in all_videos:
        cat = v.get("category", "אחר")
        catalogue.setdefault(cat, []).append(v)

    now = datetime.now(timezone.utc).isoformat()
    response_body = {
        "catalog":   catalogue,
        "total":     len(all_videos),
        "new":       new_count,
        "last_sync": now,
    }

    info(f"Would write cours_full      : {len(all_videos)} videos (no TTL)")
    info(f"Would write cours_response  : {len(json.dumps(response_body))} bytes  (TTL {CACHE_TTL}s)")
    info(f"Would write last_sync_date  : {now}")
    for cat, vids in catalogue.items():
        info(f"  Catalogue → {cat}: {len(vids)} videos")

    if not dry_run:
        await r.set("cours_full",     json.dumps(all_videos))
        await r.set("last_sync_date", now)
        await r.setex("cours_response", CACHE_TTL, json.dumps(response_body))
        ok("✅  Written to Redis.")
    else:
        warn("Dry run — nothing written. Use --write to actually commit.")

    print()


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def print_summary(existing_ids, total_new_from_probe, all_videos, new_count):
    hdr("SUMMARY — most likely root cause")

    if not existing_ids and total_new_from_probe == 0:
        err("cours_full is empty AND 0 new videos found from YouTube API")
        err("→ Check YOUTUBE_API_KEY is valid and has quota remaining")
        err("→ Check the playlist URLs are still correct")

    elif existing_ids and total_new_from_probe == 0:
        warn("cours_full has data, but 0 new videos found")
        warn("→ Most likely: no new videos have been uploaded since last sync (expected)")
        warn("→ Or: early-stop triggered because YouTube returned an already-known ID first")
        warn("   (happens if YouTube reorders a playlist — it's not always newest-first)")

    elif total_new_from_probe > 0 and new_count == 0:
        err("Videos were found by the API but new_count=0 after merge")
        err("→ All returned IDs are already in cours_full — possible double-sync")

    elif new_count > 0:
        ok(f"Everything looks correct — {new_count} new video(s) ready to write")
        ok("If you saw this script produce new_count > 0 but the live API didn't,")
        ok("the issue is likely a race condition or exception swallowed by the try/except")
        ok("in get_cours() (main.py line: return {\"error\": str(e), ...})")

    print()


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(description="Diagnose why _build_response is not inserting new videos")
    p.add_argument("--clear-cache",   action="store_true", help="Delete cours_response from Redis before running")
    p.add_argument("--inspect-redis", action="store_true", help="Only inspect Redis keys, do not run sync")
    p.add_argument("--write",         action="store_true", help="Actually write results to Redis (default: dry run)")
    p.add_argument("--verbose",       action="store_true", help="Print sample video titles at each step")
    return p.parse_args()


async def main():
    args = parse_args()

    if not os.environ.get("YOUTUBE_API_KEY"):
        err("YOUTUBE_API_KEY is not set. Add it to your .env file.")
        sys.exit(1)

    r = await get_redis()
    ok("Connected to Redis")
    print()

    try:
        # ── Optional: clear the cache to simulate the real trigger ────────────
        if args.clear_cache:
            await r.delete("cours_response")
            warn("cours_response deleted — simulating cache miss trigger")
            print()

        # ── Inspect-only mode ─────────────────────────────────────────────────
        await inspect_redis(r, verbose=args.verbose)
        if args.inspect_redis:
            return

        # ── Full diagnostic run ───────────────────────────────────────────────
        existing, existing_ids = await check_existing_ids(r)

        raw, structured = check_playlist_discovery()
        if structured is None:
            err("Aborting — playlist discovery failed")
            return

        total_new_from_probe = check_per_playlist_fetch(structured, existing_ids, verbose=args.verbose)

        all_videos, new_count = check_merge(existing, existing_ids, structured, verbose=args.verbose)

        await check_redis_write(r, all_videos, new_count, dry_run=not args.write)

        print_summary(existing_ids, total_new_from_probe, all_videos, new_count)

    finally:
        await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
