import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable
import yt_dlp
from app.config import DOWNLOADS_DIR, FFMPEG_PATH

logger = logging.getLogger("clipstream.downloader")

def sanitize_filename(name: str) -> str:
    """Sanitize string for safe filesystem usage."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()[:80]

class VideoDownloader:
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or DOWNLOADS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_info(self, url: str) -> Dict[str, Any]:
        """Fetch video metadata without downloading video stream."""
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        if FFMPEG_PATH:
            ydl_opts["ffmpeg_location"] = str(Path(FFMPEG_PATH).parent)
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "id": info.get("id"),
                "title": info.get("title", "Untitled"),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", "Unknown"),
                "view_count": info.get("view_count", 0),
                "thumbnail": info.get("thumbnail"),
                "description": info.get("description", ""),
                "is_live": info.get("is_live", False),
                "was_live": info.get("was_live", False),
                "webpage_url": info.get("webpage_url", url)
            }

    def download_video(
        self,
        url: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """Download video at 1080p/720p with audio merged."""
        safe_template = str(self.output_dir / "%(id)s_%(title).50s.%(ext)s")
        
        def ydl_hook(d):
            if progress_callback and d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
                downloaded = d.get("downloaded_bytes", 0)
                speed = d.get("speed", 0)
                eta = d.get("eta", 0)
                percent = round((downloaded / total) * 100, 1) if total else 0
                progress_callback({
                    "status": "downloading",
                    "percent": percent,
                    "downloaded": downloaded,
                    "total": total,
                    "speed": speed,
                    "eta": eta
                })
            elif progress_callback and d["status"] == "finished":
                progress_callback({
                    "status": "processing",
                    "percent": 100
                })

        ydl_opts = {
            "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
            "outtmpl": safe_template,
            "merge_output_format": "mp4",
            "progress_hooks": [ydl_hook],
            "quiet": True,
            "no_warnings": True,
            # Also try to extract chat replay if available
            "writesubtitles": False,
        }
        
        if FFMPEG_PATH:
            ydl_opts["ffmpeg_location"] = str(Path(FFMPEG_PATH).parent)
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # Ensure .mp4 extension after merge
            base, _ = os.path.splitext(filename)
            mp4_file = f"{base}.mp4"
            final_path = mp4_file if os.path.exists(mp4_file) else filename
            
            return {
                "file_path": final_path,
                "video_id": info.get("id"),
                "title": info.get("title", "Untitled"),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", "Unknown"),
                "thumbnail": info.get("thumbnail"),
                "description": info.get("description", ""),
                "is_live": info.get("is_live", False),
                "was_live": info.get("was_live", False)
            }
