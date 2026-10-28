#!/usr/bin/env python3
"""
Script 1: Fetch YouTube video details and save to JSON.
Searches YouTube, extracts video metadata, and displays in a table.
"""
import json
import subprocess
import sys
from pathlib import Path
from datetime import timedelta

# Configuration
SEARCH_QUERY = "business podcast india"
MAX_RESULTS = 10
OUTPUT_FILE = "videos.json"
MIN_DURATION = 180      # 3 minutes
MAX_DURATION = 3600     # 60 minutes


def format_duration(seconds: int) -> str:
    """Format seconds to human readable string."""
    if seconds >= 3600:
        return str(timedelta(seconds=seconds))
    return f"{seconds // 60} min"


def format_views(count: int) -> str:
    """Format view count to human readable string."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def get_category_from_tags(tags: list) -> str:
    """Map YouTube tags to our categories."""
    if not tags:
        return "General"
    
    tags_lower = [t.lower() for t in tags]
    
    category_map = {
        "education": ["education", "learning", "tutorial", "course", "lecture", "howto"],
        "business": ["business", "entrepreneur", "startup", "finance", "investing", "money"],
        "tech": ["tech", "technology", "programming", "coding", "software", "ai", "computer"],
        "health": ["health", "fitness", "workout", "gym", "nutrition", "wellness", "yoga"],
        "podcast": ["podcast", "interview", "conversation", "talk", "discussion"],
        "entertainment": ["comedy", "funny", "entertainment", "vlog", "reaction"],
        "news": ["news", "politics", "current", "breaking"],
        "science": ["science", "physics", "biology", "chemistry", "research"],
    }
    
    for cat, keywords in category_map.items():
        if any(kw in " ".join(tags_lower) for kw in keywords):
            return cat.title()
    
    return "General"


def search_videos():
    """Search YouTube and return video metadata."""
    print(f"[SEARCH] Searching YouTube for: '{SEARCH_QUERY}' (max {MAX_RESULTS} results)...\n")
    
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-j", "--flat-playlist",
        "--no-warnings",
        f"ytsearch{MAX_RESULTS}:{SEARCH_QUERY}"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"[ERROR] Error: {result.stderr}")
        return []
    
    videos = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        
        duration = data.get("duration", 0) or 0
        if not (MIN_DURATION <= duration <= MAX_DURATION):
            continue
        
        video_id = data.get("id")
        if not video_id:
            continue
        
        title = data.get("title", "Unknown")
        url = f"https://www.youtube.com/watch?v={video_id}"
        view_count = data.get("view_count", 0) or 0
        tags = data.get("tags", []) or []
        license_type = data.get("license", "Standard YouTube License")
        
        # Simplify license
        if "creative" in license_type.lower() or "cc" in license_type.lower():
            license_simple = "Creative Commons"
        else:
            license_simple = "Standard"
        
        category = get_category_from_tags(tags)
        
        videos.append({
            "title": title,
            "url": url,
            "duration": duration,
            "view_count": view_count,
            "category": category,
            "license": license_simple,
            "status": "pending"
        })
    
    # Save to JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(videos, f, indent=2, ensure_ascii=False)
    
    return videos


def print_table(videos):
    """Print videos in a formatted table."""
    if not videos:
        print("No videos found matching criteria.")
        return
    
    # Table header
    print(f"{'#':<4} {'Title':<45} {'Duration':<10} {'Views':<10} {'Category':<12} {'License':<18} {'Status':<10}")
    print("-" * 115)
    
    for i, v in enumerate(videos, 1):
        title = v["title"][:43] + ".." if len(v["title"]) > 45 else v["title"]
        print(f"{i:<4} {title:<45} {format_duration(v['duration']):<10} "
              f"{format_views(v['view_count']):<10} {v['category']:<12} {v['license']:<18} {v['status']:<10}")
    
    print("-" * 115)
    print(f"[OK] Found {len(videos)} videos. Saved to {OUTPUT_FILE}")


def main():
    videos = search_videos()
    print_table(videos)


if __name__ == "__main__":
    main()