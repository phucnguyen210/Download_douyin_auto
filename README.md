# Douyin Downloader - Vietnamese Voiceover Pipeline

Local Python tool for a personal video workflow:

1. Open a Douyin profile/video source.
2. Download videos.
3. Extract audio and run ASR.
4. Translate Chinese transcript to Vietnamese.
5. Generate Vietnamese TTS voiceover.
6. Mix original audio at low volume with Vietnamese voice.
7. Export Facebook-friendly MP4 files as H.264/AAC.

Use this project only for content you own, have permission to process, or are legally allowed to reuse. The project does not include credentials, cookies, downloaded media, generated videos, or database files.

## Main Features

- Tkinter desktop GUI: `python run_gui.py`
- Douyin download workflow with Playwright/yt-dlp fallback
- OpenAI ASR and transcript translation
- Translation style selection for drama/story content
- TTS voice selection: OpenAI, Edge Vietnamese, or gTTS
- Timestamp-aware TTS generation
- Original audio reduced to 5 percent when mixing final voiceover
- Final MP4 export as `H.264/AAC`, `yuv420p`, `+faststart`
- SQLite local database for processed video status
- Utility script to convert old HEVC final videos to H.264

## Requirements

- Python 3.11+ recommended
- FFmpeg and FFprobe available in `PATH`
- A browser login session if Douyin requires account access
- OpenAI API key for ASR, translation, and OpenAI TTS

Check FFmpeg:

```powershell
ffmpeg -version
ffprobe -version
```

## Install

```powershell
cd D:\Workspcae\MMO\AUTO_RENDER_UPLOAD_FB\douyin_downloader
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -U pip
pip install -r requirements.txt
python -m playwright install chromium
```

Create local config:

```powershell
copy .env.example .env
```

Then edit `.env` and fill at least:

```env
OPENAI_API_KEY=your_key_here
```

Do not commit `.env`.

## Run GUI

```powershell
.\.venv\Scripts\activate
python run_gui.py
```

Typical GUI flow:

1. Enter Douyin profile URL.
2. Enter target month if needed.
3. Download videos.
4. Select downloaded videos.
5. Choose translation style.
6. Choose TTS voice.
7. Run pipeline.
8. Final videos are written to `output/final/`.

## Output Folders

Generated files are intentionally ignored by Git:

```text
downloads/              Original downloaded videos
output/work/            ASR, translation, TTS, intermediate files
output/final/           Final rendered videos
output/final_h264/      Converted H.264 versions of old HEVC videos
data/app.db             Local SQLite database
logs/                   Runtime logs
pw_profile/             Playwright browser login/session profile
```

## Convert Old HEVC Finals to H.264

If Windows Media Player asks for HEVC codec, or Facebook uploads audio-only/black video, convert old final files:

```powershell
python tools\convert_hevc_finals_to_h264.py
```

Converted files are saved to:

```text
output/final_h264/
```

Verify codec manually:

```powershell
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,codec_tag_string,pix_fmt -of default=nw=1 "output\final_h264\your_video.mp4"
```

Expected:

```text
codec_name=h264
codec_tag_string=avc1
pix_fmt=yuv420p
```

## Build Windows EXE

```powershell
pip install pyinstaller
.\build_windows.bat
```

Build output is ignored by Git:

```text
dist/
build/
```

## GitHub Safety

The `.gitignore` excludes:

- `.env`, cookies, tokens, browser profiles
- SQLite databases and runtime state
- downloaded videos and generated media
- ASR/TTS/subtitle/transcript outputs
- logs, cache, virtualenvs, and build artifacts

Before pushing, check:

```powershell
git status --ignored
```

Only source code, docs, requirements, and safe examples should be committed.

## Useful Commands

Run GUI:

```powershell
python run_gui.py
```

Convert HEVC old finals:

```powershell
python tools\convert_hevc_finals_to_h264.py
```

Dry-run conversion list:

```powershell
python tools\convert_hevc_finals_to_h264.py --dry-run
```
## Generate Facebook Titles from SRT

After the Vietnamese subtitle is created, the GUI pipeline calls OpenAI to generate a Facebook-ready title from the SRT content and saves it to SQLite:

```text
data/app.db -> videos.title
```

That title is used later by `DownVidFB` when syncing Douyin final videos into the Facebook publishing database.

Useful environment variables:

```env
OPENAI_TITLE_MODEL=gpt-4.1-mini
TITLE_FROM_SRT_MAX_CHARS=8000
TITLE_MAX_CHARS=100
```

Generate titles for old completed videos without re-rendering:

```powershell
python tools\generate_titles_from_srt.py --dry-run --limit 10
python tools\generate_titles_from_srt.py --limit 10
```

Use `--overwrite` if you want to regenerate titles that were already saved.