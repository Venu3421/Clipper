import json
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from app.config import FFMPEG_PATH, FFPROBE_PATH

logger = logging.getLogger("clipstream.ffmpeg")

def check_ffmpeg() -> bool:
    """Return True if ffmpeg and ffprobe are available."""
    return bool(FFMPEG_PATH and Path(FFMPEG_PATH).exists() and FFPROBE_PATH and Path(FFPROBE_PATH).exists())

def probe_video(file_path: str) -> Dict[str, Any]:
    """Inspect a video/audio file and return structured stream information."""
    if not FFPROBE_PATH:
        raise RuntimeError("ffprobe not found. Please verify FFmpeg installation.")
    
    cmd = [
        FFPROBE_PATH,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        format_info = data.get("format", {})
        duration = float(format_info.get("duration", 0.0))
        
        video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
        
        width = int(video_stream.get("width", 0)) if video_stream else 0
        height = int(video_stream.get("height", 0)) if video_stream else 0
        
        # Calculate fps
        fps = 30.0
        if video_stream and "r_frame_rate" in video_stream:
            try:
                num, den = video_stream["r_frame_rate"].split("/")
                fps = float(num) / float(den) if float(den) != 0 else 30.0
            except Exception:
                fps = 30.0
                
        return {
            "duration": duration,
            "width": width,
            "height": height,
            "fps": fps,
            "format_name": format_info.get("format_name", ""),
            "has_video": video_stream is not None,
            "has_audio": audio_stream is not None,
            "raw": data
        }
    except Exception as e:
        logger.error(f"Error probing video {file_path}: {e}")
        raise

def extract_audio(video_path: str, output_audio_path: str, sample_rate: int = 16000) -> str:
    """Extract 16kHz mono audio from video file for Whisper & audio energy analysis."""
    if not FFMPEG_PATH:
        raise RuntimeError("ffmpeg not found.")
        
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", "1",
        str(output_audio_path)
    ]
    
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return str(output_audio_path)

def extract_clip(
    source_video: str,
    start_time: float,
    end_time: float,
    output_path: str,
    reencode: bool = True  # Always re-encode by default to avoid keyframe-boundary 1-second clips
) -> str:
    """Extract a segment from source video. Re-encodes by default for accurate cuts."""
    if not FFMPEG_PATH:
        raise RuntimeError("ffmpeg not found.")
        
    duration = end_time - start_time
    if duration <= 0:
        raise ValueError("End time must be greater than start time.")
        
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-ss", str(start_time),   # Seek BEFORE -i for fast seek
        "-i", str(source_video),
        "-t", str(duration),
    ]
    
    # Always re-encode for frame-accurate cuts (prevents keyframe 1-second bug)
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart"
    ])

    cmd.append(str(output_path))
    
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return str(output_path)

def generate_thumbnail(video_path: str, timestamp: float, output_image_path: str) -> str:
    """Extract a single frame thumbnail at the specified timestamp."""
    if not FFMPEG_PATH:
        raise RuntimeError("ffmpeg not found.")
        
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-ss", str(timestamp),
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "2",
        str(output_image_path)
    ]
    
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return str(output_image_path)
