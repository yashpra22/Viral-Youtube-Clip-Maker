"""One-click discovery, processing, and export of trading video shorts."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import paths
from ..config import load as load_settings
from ..db import store
from ..db.models import Job, new_id
from ..jobs.queue import queue
from ..pipeline import ingest
from .schemas import ExportRequestIn

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/automation", tags=["automation"])

PROJECT_DIR = Path(__file__).resolve().parents[3]
VIDEOS_FILE = PROJECT_DIR / "videos.json"
STATUS_FILE = PROJECT_DIR / "processing_status.json"
MIN_RESULTS = 20
SEARCH_QUERY = "trading investing stock market trading strategies"


class VideoItem(BaseModel):
    title: str
    url: str
    duration: int = 0
    view_count: int = 0
    category: str = "Trading"
    license: str = "Standard"
    status: str = "pending"
    job_id: str | None = None
    stage: str = ""
    progress: float = 0
    error: str | None = None


class VideoListResponse(BaseModel):
    videos: list[VideoItem]
    total: int


class StatusResponse(BaseModel):
    statuses: dict[str, str]
    active: bool = False
    phase: str = "idle"
    message: str = ""
    total: int = 0
    completed: int = 0
    eta_seconds: int | None = None
    error: str | None = None


class StartRequest(BaseModel):
    query: str = Field(default=SEARCH_QUERY, min_length=3, max_length=200)
    count: int = Field(default=MIN_RESULTS, ge=MIN_RESULTS, le=50)
    fresh: bool = False


_batch_task: asyncio.Task | None = None
_state: dict[str, Any] = {
    "active": False,
    "phase": "idle",
    "message": "Ready",
    "total": 0,
    "completed": 0,
    "started_at": None,
    "eta_seconds": None,
    "error": None,
    "statuses": {},
    "videos": [],
}


def _load_state() -> None:
    global _state
    if STATUS_FILE.exists():
        try:
            loaded = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and "statuses" in loaded:
                _state.update(loaded)
                if _state.get("active"):
                    _state.update(
                        active=False,
                        phase="interrupted",
                        message="Server restarted; press Start to resume.",
                    )
        except (OSError, json.JSONDecodeError):
            log.warning("Could not read automation state file %s", STATUS_FILE)


def _save_state() -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATUS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(_state, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(STATUS_FILE)


def _public_status() -> StatusResponse:
    return StatusResponse(
        statuses=_state.get("statuses", {}),
        active=bool(_state.get("active")),
        phase=_state.get("phase", "idle"),
        message=_state.get("message", ""),
        total=_state.get("total", 0),
        completed=_state.get("completed", 0),
        eta_seconds=_state.get("eta_seconds"),
        error=_state.get("error"),
    )


@router.get("/videos", response_model=VideoListResponse)
async def get_videos() -> VideoListResponse:
    videos = _state.get("videos")
    if not videos and VIDEOS_FILE.exists():
        try:
            videos = json.loads(VIDEOS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            videos = []
    items = [VideoItem(**item) for item in videos or []]
    for item in items:
        if item.status == "done" and not await asyncio.to_thread(
            _project_exports_complete, item.job_id
        ):
            item.status = "failed"
            item.stage = "Missing project exports"
            item.error = "Rendered MP4s are missing from the project. Retry failed videos to restore them."
    # Reflect the latest per-video fields kept in the running batch state.
    running_job_id = queue.status().running_job_id
    if running_job_id:
        running_job = await asyncio.to_thread(store.get_job, running_job_id)
        if running_job:
            for item in items:
                if item.job_id == running_job.id:
                    item.status = "processing"
                    item.stage = running_job.current_stage or running_job.status
                    item.progress = round(running_job.progress * 100, 1)
                    item.error = running_job.error
                    break
    return VideoListResponse(videos=items, total=len(items))


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    status = _public_status()
    running_job_id = queue.status().running_job_id
    if not status.active:
        if status.phase in {"complete", "failed", "interrupted"}:
            videos = _state.get("videos", [])
            completed = 0
            for video in videos:
                if video.get("status") == "done" and await asyncio.to_thread(
                    _project_exports_complete, video.get("job_id")
                ):
                    completed += 1
            status.completed = completed
            if status.completed < status.total:
                status.message = (
                    f"{status.completed}/{status.total} videos have project shorts. "
                    "Retry failed videos to restore missing outputs."
                )
        return status
    if not running_job_id:
        return status
    running_job = await asyncio.to_thread(store.get_job, running_job_id)
    if running_job:
        status.phase = "exporting" if running_job.current_stage == "export" else "processing"
        videos = _state.get("videos", [])
        index = next(
            (i for i, video in enumerate(videos) if video.get("job_id") == running_job.id),
            None,
        )
        if index is not None:
            status.message = (
                f"{index + 1}/{len(videos)} · {videos[index]['title']} · "
                f"{running_job.current_stage or running_job.status}"
            )
    return status


@router.post("/start", response_model=StatusResponse, status_code=202)
async def start_batch(payload: StartRequest = StartRequest()) -> StatusResponse:
    global _batch_task
    if _batch_task is not None and not _batch_task.done():
        raise HTTPException(status_code=409, detail="Automation is already running.")
    saved_videos = _state.get("videos", [])
    failed_videos_exist = any(
        video.get("status") in {"failed", "error"}
        for video in saved_videos
    )
    missing_exports_exist = any(
        video.get("status") == "done"
        and not _project_exports_complete(video.get("job_id"))
        for video in saved_videos
    )
    can_resume = not payload.fresh and bool(saved_videos) and (
        _state.get("phase") == "interrupted"
        or (
            _state.get("phase") in {"complete", "failed"}
            and (failed_videos_exist or missing_exports_exist)
        )
    )
    if can_resume:
        completed_before_resume = sum(
            video.get("status") == "done"
            and _project_exports_complete(video.get("job_id"))
            for video in saved_videos
        )
        _state.update(
            active=True,
            phase="resuming",
            message="Resuming saved jobs and retrying failed videos…",
            started_at=time.time(),
            eta_seconds=None,
            error=None,
            completed=completed_before_resume,
            eta_seed_completed=completed_before_resume,
        )
    else:
        _state.update(
            active=True,
            phase="searching",
            message=f"Finding at least {payload.count} trading videos…",
            total=payload.count,
            completed=0,
            eta_seed_completed=0,
            started_at=time.time(),
            eta_seconds=None,
            error=None,
            statuses={},
            videos=[],
        )
    _publish_videos()
    _save_state()
    _batch_task = asyncio.create_task(_run_batch(payload), name="autoclip-automation")
    return _public_status()


@router.post("/trigger/{url:path}")
async def trigger_processing(url: str) -> dict:
    raise HTTPException(status_code=410, detail="Use Start automation to run the complete batch.")


async def _discover(query: str, count: int) -> list[dict[str, Any]]:
    def fetch() -> list[dict[str, Any]]:
        try:
            import yt_dlp
        except ImportError as exc:  # pragma: no cover - package dependency
            raise RuntimeError("yt-dlp is missing. Reinstall AutoClip dependencies.") from exc
        options = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            search_count = max(count * 3, 60)
            queries = [
                query,
                "trading podcast stock market investing",
                "technical analysis stock trading strategies",
                "forex trading education investing",
            ]
            results: list[dict[str, Any]] = []
            seen: set[str] = set()
            for search_query in dict.fromkeys(queries):
                try:
                    info = ydl.extract_info(
                        f"ytsearch{search_count}:{search_query}", download=False
                    )
                except Exception:
                    log.exception("YouTube search failed for %r", search_query)
                    continue
                for entry in (info or {}).get("entries", []):
                    if not entry:
                        continue
                    duration = int(entry.get("duration") or 0)
                    video_id = entry.get("id")
                    if (
                        not video_id
                        or video_id in seen
                        or duration < 180
                        or duration > 7200
                    ):
                        continue
                    seen.add(video_id)
                    license_text = str(entry.get("license") or "Standard").lower()
                    results.append(
                        {
                            "title": entry.get("title") or "Untitled trading video",
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                            "duration": duration,
                            "view_count": int(entry.get("view_count") or 0),
                            "category": "Trading",
                            "license": (
                                "Creative Commons"
                                if "creative" in license_text
                                else "Standard"
                            ),
                            "status": "pending",
                            "job_id": None,
                            "stage": "",
                            "progress": 0,
                            "error": None,
                        }
                    )
                    if len(results) >= count:
                        return results
        return results

    return await asyncio.to_thread(fetch)


def _publish_videos() -> None:
    VIDEOS_FILE.parent.mkdir(parents=True, exist_ok=True)
    VIDEOS_FILE.write_text(
        json.dumps(_state.get("videos", []), indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _update_video(video: dict[str, Any], status: str, **fields: Any) -> None:
    video.update(status=status, **fields)
    _state.setdefault("statuses", {})[video["url"]] = status
    _publish_videos()
    _save_state()


def _update_eta(completed_fraction: float, total: int) -> None:
    fraction_this_run = max(
        0.0, completed_fraction - float(_state.get("eta_seed_completed") or 0)
    )
    if fraction_this_run <= 0.05:
        return
    elapsed = max(0, time.time() - float(_state.get("started_at") or time.time()))
    if elapsed < 30:
        return
    average = elapsed / fraction_this_run
    _state["eta_seconds"] = round(average * max(0, total - completed_fraction))


def _batch_job_settings(settings, job_id: str) -> dict[str, Any]:
    snapshot = settings.model_dump(mode="json")
    snapshot["automation_export_dir"] = str(
        PROJECT_DIR / ".autoclip" / "exports" / job_id
    )
    return snapshot


def _project_exports_complete(job_id: str | None) -> bool:
    """Return true only when every saved clip has a usable project-local MP4."""
    if not job_id:
        return False

    destination_dir = PROJECT_DIR / ".autoclip" / "exports" / job_id
    clips = store.list_clips(job_id)
    if not clips:
        return False

    for clip in clips:
        exports = store.list_exports(clip.id)
        if not any(
            export.ratio == "9:16"
            and export.style == "bold_pop"
            and Path(export.path).parent == destination_dir
            and Path(export.path).is_file()
            and Path(export.path).stat().st_size > 0
            for export in exports
        ):
            return False
    return True


def _cleanup_automation_artifacts(job_id: str) -> None:
    """Remove only this successful YouTube job's disposable source/work files."""
    job = store.get_job(job_id)
    if job is None:
        return

    targets = [(paths.work_dir(), paths.job_work_dir(job_id))]
    source = store.get_source(job.source_id)
    if source and source.type == "youtube":
        targets.append((paths.media_dir(), Path(source.path).parent))

    for root, target in targets:
        root_path = root.resolve()
        target_path = target.resolve()
        if target_path.parent != root_path or not target_path.exists():
            continue
        try:
            shutil.rmtree(target_path)
        except OSError:
            log.warning("Could not remove temporary automation data at %s", target_path)


async def _run_batch(payload: StartRequest) -> None:
    try:
        resuming = _state.get("phase") == "resuming"
        if resuming:
            videos = list(_state.get("videos", []))
            _state.update(
                total=len(videos),
                phase="processing",
                message=f"Resuming {len(videos)} saved trading videos…",
            )
        else:
            videos = await _discover(payload.query, payload.count)
            if len(videos) < payload.count:
                raise RuntimeError(
                    f"YouTube returned only {len(videos)} eligible videos; "
                    f"at least {payload.count} are required. Try another search phrase."
                )
            _state.update(
                videos=videos,
                total=len(videos),
                phase="processing",
                message=f"Found {len(videos)} videos. Processing in order…",
            )
            _publish_videos()
            _save_state()
        processing_videos = list(videos)
        display_index = {video["url"]: i + 1 for i, video in enumerate(videos)}
        if resuming and (running_job_id := queue.status().running_job_id):
            running_video = next(
                (video for video in videos if video.get("job_id") == running_job_id), None
            )
            if running_video is not None:
                processing_videos = [running_video] + [
                    video for video in videos if video is not running_video
                ]
        settings = load_settings()
        batch_settings = settings.model_copy(deep=True)
        # Keep the one-click batch's output size manageable on a CPU-first
        # workstation while still producing a few reviewable choices per source.
        batch_settings.clips.max_clips = min(batch_settings.clips.max_clips, 3)
        batch_settings.export.ratio = "9:16"
        batch_settings.export.caption_style = "bold_pop"
        batch_settings.export.x264_preset = "veryfast"
        # Trading videos are usually English and YouTube captions save the
        # large amount of CPU time that Whisper would spend on every source.
        # The runner falls back to Whisper when no JSON3 sidecar is available.
        batch_settings.ingest.prefer_youtube_captions = True

        for index, video in enumerate(processing_videos):
            if video.get("status") == "done" and await asyncio.to_thread(
                _project_exports_complete, video.get("job_id")
            ):
                await asyncio.to_thread(
                    _cleanup_automation_artifacts, video["job_id"]
                )
                continue
            _state.update(
                message=(
                    f"Downloading {display_index[video['url']]}/{len(videos)}: "
                    f"{video['title']}"
                ),
                phase="downloading",
            )
            job = None
            if video.get("job_id"):
                job = await asyncio.to_thread(store.get_job, video["job_id"])
                if job:
                    source = await asyncio.to_thread(store.get_source, job.source_id)
                    if source is None or not Path(source.path).is_file():
                        # A previous cleanup may have removed source media. Re-ingest
                        # the URL below and attach a fresh job instead of retrying a
                        # job whose input path can never succeed.
                        job = None
            if job:
                retry_without_clips = bool(
                    job
                    and job.status == "done"
                    and not await asyncio.to_thread(store.list_clips, job.id)
                )
                retry_missing_exports = bool(
                    job
                    and job.status == "done"
                    and not await asyncio.to_thread(_project_exports_complete, job.id)
                )
                if job and (
                    job.status in ("failed", "cancelled", "running", "queued")
                    or retry_without_clips
                    or retry_missing_exports
                ):
                    await asyncio.to_thread(
                        store.update_job,
                        job.id,
                        status="queued",
                        provider=settings.active_provider,
                        settings=_batch_job_settings(batch_settings, job.id),
                        progress=0.0,
                        error=None,
                        current_stage="",
                        started_at=None,
                        finished_at=None,
                    )
                    job = await asyncio.to_thread(store.get_job, job.id)
                    queue.notify()
                    _update_video(
                        video,
                        "processing",
                        stage="Retrying saved source",
                        progress=0,
                        error=None,
                    )

            if job is None:
                _update_video(video, "downloading", stage="Downloading source")
                try:
                    source = await asyncio.to_thread(
                        ingest.ingest_youtube, video["url"], batch_settings.ingest
                    )
                except Exception as exc:
                    log.exception("Could not download automation source %s", video["url"])
                    _update_video(video, "failed", error=str(exc))
                    _state["completed"] = min(len(videos), _state["completed"] + 1)
                    _update_eta(_state["completed"], len(videos))
                    _save_state()
                    continue
                await asyncio.to_thread(store.create_source, source)
                job_id = new_id()
                job = Job(
                    id=job_id,
                    source_id=source.id,
                    provider=settings.active_provider,
                    settings=_batch_job_settings(batch_settings, job_id),
                )
                await asyncio.to_thread(store.create_job, job)
                queue.notify()
                video["job_id"] = job.id
                _update_video(video, "processing", stage="Queued for clipping", progress=0)
            elif job.status == "queued":
                queue.notify()

            while True:
                current = await asyncio.to_thread(store.get_job, job.id)
                if current is None:
                    raise RuntimeError(f"Processing job {job.id} disappeared.")
                video.update(
                    stage=current.current_stage or current.status,
                    progress=round(current.progress * 100, 1),
                )
                _state["message"] = (
                    f"{display_index[video['url']]}/{len(videos)} · "
                    f"{video['title']} · {video['stage']}"
                )
                _update_eta(_state["completed"] + current.progress, len(videos))
                _publish_videos()
                _save_state()
                if current.status in ("done", "failed", "cancelled"):
                    break
                await asyncio.sleep(3)

            if current.status != "done":
                _update_video(video, "failed", error=current.error or f"Job {current.status}")
            else:
                # The pipeline creates editable clip candidates. Render their
                # 9:16 captioned MP4s as part of this same one-click workflow.
                from .clips import _export_clip

                clips = await asyncio.to_thread(store.list_clips, job.id)
                if not clips:
                    _update_video(
                        video,
                        "failed",
                        stage="No clips generated",
                        error="The clip pipeline completed, but did not find a usable short.",
                    )
                else:
                    export_error = None
                    for clip_index, clip in enumerate(clips, 1):
                        destination_dir = PROJECT_DIR / ".autoclip" / "exports" / job.id
                        previous_exports = await asyncio.to_thread(store.list_exports, clip.id)
                        if any(
                            export.ratio == "9:16"
                            and export.style == "bold_pop"
                            and Path(export.path).parent == destination_dir
                            and Path(export.path).is_file()
                            for export in previous_exports
                        ):
                            continue
                        video.update(
                            stage=f"Rendering short {clip_index}/{len(clips)}",
                            progress=round((clip_index - 1) / len(clips) * 100, 1),
                        )
                        _state.update(
                            phase="exporting",
                            message=(
                                f"Rendering short {clip_index}/{len(clips)} · {video['title']}"
                            ),
                        )
                        _update_eta(
                            _state["completed"] + (clip_index - 1) / len(clips), len(videos)
                        )
                        _publish_videos()
                        _save_state()
                        try:
                            await _export_clip(
                                clip.id,
                                ExportRequestIn(ratio="9:16", style="bold_pop"),
                                destination_dir=destination_dir,
                            )
                        except Exception as exc:
                            export_error = str(exc)
                            log.exception("Could not render clip %s", clip.id)
                            break
                    if export_error:
                        _update_video(
                            video, "failed", error=f"Short rendering failed: {export_error}"
                        )
                    else:
                        _update_video(
                            video, "done", stage=f"Ready · {len(clips)} shorts", progress=100
                        )
            if video.get("status") == "done" and await asyncio.to_thread(
                _project_exports_complete, video.get("job_id")
            ):
                await asyncio.to_thread(
                    _cleanup_automation_artifacts, video["job_id"]
                )
            _state["completed"] = min(len(videos), _state["completed"] + 1)
            _state["eta_seconds"] = 0 if index == len(videos) - 1 else _state.get("eta_seconds")
            _save_state()

        _state.update(
            active=False,
            phase="complete",
            message=f"Finished {len(videos)} videos. Shorts are ready to review.",
            eta_seconds=0,
        )
    except Exception as exc:
        log.exception("Automation batch failed")
        _state.update(
            active=False,
            phase="failed",
            message="Automation stopped because of an error.",
            error=str(exc),
            eta_seconds=None,
        )
    finally:
        _save_state()


_load_state()
