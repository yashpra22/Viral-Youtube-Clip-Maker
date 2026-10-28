# AutoClip

**Open-source, local-first AI video clipper.** Long video in → ranked, caption-burned, speaker-tracked 9:16 shorts out.

[![CI](https://github.com/artbyjazi/autoclip/actions/workflows/ci.yml/badge.svg)](https://github.com/artbyjazi/autoclip/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11 | 3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)

Paste a YouTube link or drop a file. AutoClip transcribes it, uses an LLM to find the moments worth clipping, reframes them to vertical while tracking whoever is speaking, burns in animated captions, and exports platform-ready MP4s.

No accounts. No uploads to anyone's servers. No watermarks. No subscription.

---

## ✨ What's New in This Release

| Feature | Description |
|---------|-------------|
| 🤖 **NVIDIA Nemotron-3.5-Super-VL-120b-A2B** | Free NVIDIA NIM LLM for highlight detection |
| 🎯 **Automation Pipeline** | Batch fetch YouTube URLs + process all videos with live status |
| 📊 **Automation UI** | Real-time table view at `/automation` |
| 🔧 **One-Command Setup** | Clone → setup → ready to go |
| 💾 **Config Persistence** | Settings saved to `~/.autoclip/config.json` |

---

## 🚀 Quick Start (Clone & Run)

### Option 1: One-Command Setup (Windows)

```powershell
git clone https://github.com/artbyjazi/autoclip.git
cd autoclip
.\\setup.bat
```

### Option 2: Manual Setup

```powershell
# 1. Clone
git clone https://github.com/artbyjazi/autoclip.git
cd autoclip

# 2. Create virtual environment
python -m venv .venv
.venv\\Scripts\\activate

---

## 📦 Project Structure

```
autoclip/
├── scripts/                 # Automation scripts
│   ├── get_urls.py          # Fetch YouTube video URLs by topic
│   └── process_videos.py    # Batch process videos with live status
├── config/
│   └── .env.example         # Environment variables template
├── backend/autoclip/        # Python backend (FastAPI)
├── frontend/src/            # React + TypeScript UI
├── docs/                    # Documentation
├── docker/                  # Docker configuration
├── tests/                   # Test suite
├── .github/                 # CI/CD workflows
├── pyproject.toml           # Python project config
├── README.md                # This file
└── LICENSE                  # MIT License
```

---

## 🤖 LLM Providers

| Provider | Setup | Cost | Best For |
|----------|-------|------|----------|

---

## 🎯 Automation Pipeline

```powershell
# 1. Fetch videos from YouTube
.venv\\Scripts\\python scripts\\get_urls.py

# 2. View table at http://localhost:8000/automation

# 3. Process all videos
.venv\\Scripts\\python scripts\\process_videos.py
```

---

## 📋 Output Locations

| Type | Path |
|------|------|
| Source videos | `~/.autoclip/media/<job_id>/source.mp4` |
| Processing work | `~/.autoclip/work/<job_id>/` |
| Exported clips | `~/.autoclip/exports/` |
| Database | `~/.autoclip/autoclip.db` |
| Config | `~/.autoclip/config.json` |


---

## ⚖️ Legal

AutoClip bundles [yt-dlp](https://github.com/yt-dlp/yt-dlp). **Only download content you own or have the rights to process.** AutoClip contains no workarounds for DRM or paywalled content and never will.

MIT License — see [LICENSE](LICENSE).
---

## ⚠️ Requirements

| Component | Version | Notes |
|-----------|---------|-------|
| **Python** | 3.11 or 3.12 | Not 3.13+ (MediaPipe has no wheels) |
| **ffmpeg** | Full build | Must include `libass` and `libx264` |
| **Node.js** | 20+ | Only needed to build UI |
| **GPU** | Optional | NVIDIA CUDA or Apple Silicon |

Run `autoclip doctor` to verify your setup.
| **NVIDIA NIM** (via OpenAI compat) | `AUTOCLIP_OPENAI_KEY` + base_url to `integrate.api.nvidia.com` | Free tier available | **Recommended** - Nemotron-3.5-Super-VL-120b-A2B |
| **Ollama** | Install Ollama locally | Free | Fully local, no API key |
| **OpenAI** | `AUTOCLIP_OPENAI_KEY` | Paid | GPT-4o, GPT-4o-mini |
| **Anthropic** | `AUTOCLIP_ANTHROPIC_KEY` | Paid | Claude models |
| **Gemini** | `AUTOCLIP_GEMINI_KEY` | Paid | Gemini models |

Copy `config/.env.example` to `.env` and fill in your keys.

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Install ffmpeg (full build with libass)
# Windows: winget install Gyan.FFmpeg
# macOS: brew install ffmpeg-full
# Linux: sudo apt install ffmpeg

# 5. Build frontend (for UI)
cd frontend && npm install && npm run build && cd ..

# 6. Verify setup
autoclip doctor

# 7. Start server
autoclip serve
# Open http://localhost:8000
```