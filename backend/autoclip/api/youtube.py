import json
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

router = APIRouter(prefix="/api/youtube", tags=["youtube"])

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

_oauth_flows: dict[str, Flow] = {}
_pending_uploads: dict[str, dict] = {}


def _client_config() -> dict:
    """Read YouTube OAuth client config from env vars."""
    client_id = os.environ.get("AUTOCLIP_YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("AUTOCLIP_YOUTUBE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail="YouTube OAuth client not configured. Set AUTOCLIP_YOUTUBE_CLIENT_ID and AUTOCLIP_YOUTUBE_CLIENT_SECRET.",
        )
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [os.environ.get("AUTOCLIP_YOUTUBE_REDIRECT_URI", "http://localhost:8000/api/youtube/callback")],
        }
    }


@router.get("/auth/start")
async def auth_start(request: Request, state: str | None = None):
    """Begin OAuth flow — redirects user to Google consent screen."""
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=os.environ.get("AUTOCLIP_YOUTUBE_REDIRECT_URI", "http://localhost:8000/api/youtube/callback"),
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    state = state or str(uuid.uuid4())
    _oauth_flows[state] = flow
    return {"auth_url": auth_url, "state": state}


@router.get("/callback")
async def auth_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    """OAuth callback — exchanges code for credentials and stores them."""
    if error:
        return HTMLResponse(f"<h1>YouTube auth failed:</h1><pre>{error}</pre>", status_code=400)
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter.")

    flow = _oauth_flows.pop(state, None)
    if flow is None:
        raise HTTPException(status_code=400, detail="Invalid or expired state token.")

    flow.fetch_token(code=code)
    credentials = flow.credentials

    user_token = str(uuid.uuid4())
    _pending_uploads[user_token] = {
        "credentials": {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
        }
    }

    return HTMLResponse(
        """
        <html>
        <body style="font-family: system-ui; text-align: center; padding: 2rem;">
            <h1 style="color: #10b981;">✅ YouTube connected!</h1>
            <p>You can close this window and return to AutoClip.</p>
            <script>window.close();</script>
        </body>
        </html>
        """,
        status_code=200,
    )


@router.get("/auth/status")
async def auth_status(user_token: str = Query(...)):
    """Check if the user has valid YouTube credentials."""
    pending = _pending_uploads.get(user_token)
    if not pending or "credentials" not in pending:
        return {"authenticated": False}
    return {"authenticated": True}

@router.post("/generate-metadata")
async def generate_metadata(payload: dict):
    """Use the active LLM provider to generate YouTube title, description, and tags."""
    from ..providers import build_provider, detection_config
    from ..config import load as load_settings

    settings = load_settings()
    provider = build_provider(settings.active_provider, settings)
    config = detection_config(settings)

    title = payload.get("title", "")
    description = payload.get("description", "")
    duration = payload.get("duration", 0)
    category = payload.get("category", "General")

    system_prompt = (
        "You are an expert YouTube Shorts strategist. Your job is to write "
        "viral-worthy titles, SEO-optimized descriptions, and trending tags "
        "for 9:16 vertical short-form videos. Keep titles under 60 characters, "
        "descriptions under 500 characters with hashtags at the end, and "
        "provide 10-15 relevant tags."
    )

    user_prompt = f"""
    Video title: {title}
    Video description: {description}
    Duration: {duration} seconds
    Category: {category}

    Generate:
    1. A viral YouTube Shorts title (max 60 chars, include emoji, curiosity gap)
    2. An SEO description (first 2 lines hook, include keywords, end with hashtags)
    3. 10-15 trending tags (comma-separated)

    Output as JSON: {{"title": "...", "description": "...", "tags": ["tag1", "tag2", ...]}}
    """

    try:
        response = await provider._complete(system_prompt, user_prompt, config)
        import re
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            metadata = json.loads(json_match.group())
        else:
            metadata = {
                "title": title[:60],
                "description": description[:500],
                "tags": [category.lower()],
            }
        return metadata
    except Exception as exc:
        return {
            "title": title[:60],
            "description": description[:500],
            "tags": [category.lower(), "shorts", "viral"],
        }


@router.post("/upload")
async def upload_video(payload: dict):
    """Upload a processed clip to YouTube with AI-generated metadata."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    user_token = payload.get("url")
    if not user_token or user_token not in _pending_uploads:
        raise HTTPException(status_code=401, detail="Not authenticated with YouTube. Call /auth/start first.")

    creds_data = _pending_uploads[user_token]["credentials"]
    credentials = Credentials(**creds_data)

    youtube = build("youtube", "v3", credentials=credentials)

    video_path = payload.get("video_path")
    if not video_path or not Path(video_path).exists():
        raise HTTPException(status_code=400, detail="Video file not found.")

    title = payload.get("title", "AutoClip Short")
    description = payload.get("description", "")
    tags = payload.get("tags", [])
    category_id = payload.get("category_id", "22")
    privacy_status = payload.get("privacy_status", "public")

    request_body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:500] if tags else [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)

    try:
        request = youtube.videos().insert(
            part="snippet,status",
            body=request_body,
            media_body=media,
        )
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Upload progress: {int(status.progress() * 100)}%")

        video_id = response["id"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        _pending_uploads[user_token]["last_upload"] = {
            "video_id": video_id,
            "video_url": video_url,
            "title": title,
        }

        return {
            "success": True,
            "video_id": video_id,
            "video_url": video_url,
            "title": title,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"YouTube upload failed: {str(exc)}")


@router.get("/auth/logout")
async def auth_logout(user_token: str = Query(...)):
    """Clear stored YouTube credentials."""
    _pending_uploads.pop(user_token, None)
    return {"success": True}
