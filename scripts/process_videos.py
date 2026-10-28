#!/usr/bin/env python3
"""
Script 2: Process videos through AutoClip with live status table.
Reads videos.json, processes each through AutoClip, shows real-time status.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

INPUT_FILE = "videos.json"
STATUS_FILE = "processing_status.json"


def load_videos():
    """Load videos from JSON file."""
    if not Path(INPUT_FILE).exists():
        print(f"[ERROR] {INPUT_FILE} not found. Run scripts/get_urls.py first.")
        return []
    
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def format_duration(seconds: int) -> str:
    """Format seconds to human readable string."""
    if seconds >= 3600:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m"
    return f"{seconds // 60} min"


def print_status_table(videos, status, current_idx=None):
    """Print live status table."""
    os.system("cls" if os.name == "nt" else "clear")
    
    print("+=======+=================================================+===========+===========+")
    print("| #     | Video                                           | Status    | Progress  |")
    print("+=======+=================================================+===========+===========+")
    
    done = sum(1 for v in videos if status.get(v["url"]) == "done")
    failed = sum(1 for v in videos if status.get(v["url"]) in ("failed", "error"))
    processing = sum(1 for v in videos if status.get(v["url"]) == "processing")
    pending = len(videos) - done - failed - processing
    
    for i, v in enumerate(videos, 1):
        url = v["url"]
        video_status = status.get(url, "pending")
        
        if video_status == "done":
            status_display = "[OK] done"
            progress = "100%"
        elif video_status == "processing":
            status_display = "[...] processing"
            progress = "..."
        elif video_status in ("failed", "error"):
            status_display = "[FAIL] failed"
            progress = "0%"
        else:
            status_display = "[WAIT] pending"
            progress = "0%"
        
        prefix = "-> " if i - 1 == current_idx else "   "
        title = v["title"][:45] + ".." if len(v["title"]) > 47 else v["title"]
        
        print(f"| {i:<3}  | {prefix}{title:<45} | {status_display:<9} | {progress:<9} |")
    
    print("+=======+=================================================+===========+===========+")
    print(f"[SUMMARY] [OK] {done} done  [FAIL] {failed} failed  [...] {processing} processing  [WAIT] {pending} pending")
    print()


def main():
    videos = load_videos()
    if not videos:
        return
    
    status = load_status()
    
    for v in videos:
        if v["url"] not in status:
            status[v["url"]] = "pending"
    
    print(f"[START] Starting processing of {len(videos)} videos...\n")
    time.sleep(1)
    
    for idx, video in enumerate(videos):
        url = video["url"]
        
        if status.get(url) == "done":
            print_status_table(videos, status, idx)
            continue
        
        status[url] = "processing"
        save_status(status)
        print_status_table(videos, status, idx)
        
        print(f"   Processing: {video['title'][:60]}...")
        success, stdout, stderr = process_video(url, video["title"])
        
        if success:
            status[url] = "done"
            print(f"   [OK] Completed: {video['title'][:60]}")
        else:
            status[url] = "failed"
            print(f"   [FAIL] Failed: {video['title'][:60]}")
            if stderr:
                print(f"      Error: {stderr[:200]}")
        
        save_status(status)
        print_status_table(videos, status, idx)
        
        if idx < len(videos) - 1:
            print("   [...] Waiting 5 seconds before next video...")
            time.sleep(5)
    
    failed_urls = [v["url"] for v in videos if status.get(v["url"]) in ("failed", "error")]
    if failed_urls:
        print(f"\n[RETRY] Retrying {len(failed_urls)} failed video(s)...")
        time.sleep(2)
        
        for url in failed_urls:
            video = next(v for v in videos if v["url"] == url)
            status[url] = "processing"
            save_status(status)
            print_status_table(videos, status)
            
            print(f"   Retrying: {video['title'][:60]}...")
            success, stdout, stderr = process_video(url, video["title"])
            
            if success:
                status[url] = "done"
                print(f"   [OK] Retry succeeded: {video['title'][:60]}")
            else:
                status[url] = "failed"
                print(f"   [FAIL] Retry failed: {video['title'][:60]}")
            
            save_status(status)
            print_status_table(videos, status)
            time.sleep(5)
    
    done = sum(1 for v in videos if status.get(v["url"]) == "done")
    failed = sum(1 for v in videos if status.get(v["url"]) in ("failed", "error"))
    
    print(f"\n{'='*60}")
    print(f"[DONE] Processing Complete!")
    print(f"   [OK] Successful: {done}")
    print(f"   [FAIL] Failed: {failed}")
    print(f"   [INFO] Check results at: http://localhost:8000")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()