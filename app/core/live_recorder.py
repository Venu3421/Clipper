import os
import time
import shutil
import threading
import subprocess
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, Any
from app.config import TEMP_DIR, DOWNLOADS_DIR, FFMPEG_PATH

logger = logging.getLogger("clipstream.live_recorder")

class LiveStreamRecorder:
    def __init__(self, stream_url: str, output_name: Optional[str] = None):
        self.stream_url = stream_url
        self.session_id = output_name or f"live_{int(time.time())}"
        self.output_dir = DOWNLOADS_DIR / self.session_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.raw_output_file = self.output_dir / "stream_capture.ts"
        self.final_mp4_file = self.output_dir / "recorded_session.mp4"
        
        self.process: Optional[subprocess.Popen] = None
        self.is_recording = False
        self._thread: Optional[threading.Thread] = None
        self.start_time: float = 0
        self.duration_recorded: float = 0

    def start(self, quality: str = "720p,best"):
        """Start capturing the live stream in background thread."""
        if self.is_recording:
            logger.warning("Recorder already running.")
            return

        self.is_recording = True
        self.start_time = time.time()

        # Streamlink command to pipe into file
        cmd = [
            "streamlink",
            "--default-stream", quality,
            "--output", str(self.raw_output_file),
            "--force",
            self.stream_url,
            "best"
        ]

        def _record_worker():
            try:
                logger.info(f"Starting Streamlink capture: {' '.join(cmd)}")
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                self.process.wait()
            except Exception as e:
                logger.error(f"Error in stream recorder: {e}")
            finally:
                self.is_recording = False
                self.duration_recorded = time.time() - self.start_time
                logger.info(f"Stream capture ended. Duration: {self.duration_recorded:.1f}s")

        self._thread = threading.Thread(target=_record_worker, daemon=True)
        self._thread.start()

    def stop(self) -> Dict[str, Any]:
        """Stop capturing and remux to MP4."""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

        self.is_recording = False
        self.duration_recorded = time.time() - self.start_time

        # Remux .ts to .mp4 with FFmpeg for instant seekability
        if self.raw_output_file.exists() and self.raw_output_file.stat().st_size > 0:
            if FFMPEG_PATH:
                remux_cmd = [
                    FFMPEG_PATH,
                    "-y",
                    "-i", str(self.raw_output_file),
                    "-c", "copy",
                    "-movflags", "+faststart",
                    str(self.final_mp4_file)
                ]
                try:
                    subprocess.run(remux_cmd, capture_output=True, check=True)
                    return {
                        "status": "completed",
                        "file_path": str(self.final_mp4_file),
                        "duration": self.duration_recorded,
                        "session_id": self.session_id
                    }
                except Exception as e:
                    logger.error(f"Failed to remux live capture: {e}")
            
            return {
                "status": "completed",
                "file_path": str(self.raw_output_file),
                "duration": self.duration_recorded,
                "session_id": self.session_id
            }

        return {
            "status": "empty",
            "message": "No stream data was captured.",
            "duration": 0
        }

    def get_status(self) -> Dict[str, Any]:
        """Get live recorder stats."""
        elapsed = time.time() - self.start_time if self.is_recording else self.duration_recorded
        file_size = 0
        if self.raw_output_file.exists():
            file_size = self.raw_output_file.stat().st_size
            
        return {
            "is_recording": self.is_recording,
            "session_id": self.session_id,
            "elapsed_seconds": round(elapsed, 1),
            "bytes_captured": file_size,
            "megabytes": round(file_size / (1024 * 1024), 2)
        }
