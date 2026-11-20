import os
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from app.config import FFMPEG_PATH, EXPORTS_DIR, TEMP_DIR
from app.core.face_tracker import FaceTracker

logger = logging.getLogger("clipstream.video_processor")

class VideoProcessor:
    def __init__(self):
        if not FFMPEG_PATH:
            raise RuntimeError("FFmpeg executable not configured.")
        self.face_tracker = FaceTracker()

    def render_short(
        self,
        input_video_path: str,
        output_filename: str,
        layout: str = "podcast_blur",
        subtitle_ass_path: Optional[str] = None,
        custom_params: Optional[Dict[str, Any]] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        progress_callback: Optional[callable] = None
    ) -> str:
        """
        Composite and render a 1080x1920 vertical YouTube Short.
        Accepts optional start_time/end_time to seek and trim in one single FFmpeg pass,
        avoiding broken intermediate files.
        """
        input_path = Path(input_video_path).resolve()
        output_path = (EXPORTS_DIR / output_filename).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        custom_params = custom_params or {}

        # Subtitle filter: use filename-only with cwd set to avoid Windows path escaping issues
        sub_filter = ""
        sub_cwd = str(TEMP_DIR)
        if subtitle_ass_path and Path(subtitle_ass_path).exists():
            ass_path = Path(subtitle_ass_path).resolve()
            sub_cwd = str(ass_path.parent)
            # Escape the filename for the filtergraph (single-quote safe on Windows)
            safe_name = ass_path.name.replace("'", "\\'").replace(":", "\\:")
            sub_filter = f",subtitles='{safe_name}'"

        # Sample source video for face detection strictly within the clip range
        face_params = {}
        focus_pos = custom_params.get("focus_position", "auto")
        facecam_pos = custom_params.get("facecam_position", "auto")

        if layout in ("gaming_split", "pip"):
            cam_info = self.face_tracker.find_facecam_region(
                str(input_path),
                start_time=start_time,
                end_time=end_time,
                preferred_position=facecam_pos
            )
            face_params["cx"] = custom_params.get("facecam_x", cam_info["x"])
            face_params["cy"] = custom_params.get("facecam_y", cam_info["y"])
            face_params["cw"] = custom_params.get("facecam_w", cam_info["w"])
            face_params["ch"] = custom_params.get("facecam_h", cam_info["h"])
        elif layout == "smart_face_track":
            track_info = self.face_tracker.compute_smart_tracking_crop(
                str(input_path),
                start_time=start_time,
                end_time=end_time,
                preferred_focus=focus_pos
            )
            face_params["center_ratio"] = custom_params.get("center_x_ratio", track_info["center_x_ratio"])

        # Build filter graph
        if layout == "podcast_blur":
            filter_graph = (
                "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,boxblur=25:5[bg];"
                "[0:v]scale=1080:-2[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2{sub_filter}[outv]"
            )

        elif layout == "gaming_split":
            cx, cy = face_params["cx"], face_params["cy"]
            cw, ch = face_params["cw"], face_params["ch"]
            filter_graph = (
                f"[0:v]crop={cw}:{ch}:{cx}:{cy},"
                "scale=1080:860:force_original_aspect_ratio=increase,crop=1080:860[top];"
                "[0:v]scale=1080:1060:force_original_aspect_ratio=increase,crop=1080:1060[bot];"
                f"[top][bot]vstack=inputs=2{sub_filter}[outv]"
            )

        elif layout == "smart_face_track":
            cr = face_params["center_ratio"]
            filter_graph = (
                f"[0:v]crop=ih*9/16:ih:min(max(0\\,(iw*{cr})-(ih*9/32))\\,iw-(ih*9/16)):0,"
                f"scale=1080:1920{sub_filter}[outv]"
            )

        elif layout == "pip":
            cx, cy = face_params["cx"], face_params["cy"]
            cw, ch = face_params["cw"], face_params["ch"]
            filter_graph = (
                "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
                "[0:v]scale=1080:-2[main];"
                "[bg][main]overlay=(W-w)/2:(H-h)/2[base];"
                f"[0:v]crop={cw}:{ch}:{cx}:{cy},scale=360:360[cam];"
                f"[base][cam]overlay=(W-w)/2:120{sub_filter}[outv]"
            )

        else:  # center_crop
            filter_graph = (
                "[0:v]crop=ih*9/16:ih:(iw-(ih*9/16))/2:0,"
                f"scale=1080:1920{sub_filter}[outv]"
            )

        # Build FFmpeg command — seek BEFORE -i for speed, duration via -t in one pass
        cmd = [FFMPEG_PATH, "-y"]
        if start_time is not None and start_time > 0:
            cmd.extend(["-ss", str(round(start_time, 3))])
        cmd.extend(["-i", str(input_path)])
        if start_time is not None and end_time is not None:
            duration = end_time - start_time
            if duration > 0:
                cmd.extend(["-t", str(round(duration, 3))])

        cmd.extend([
            "-filter_complex", filter_graph,
            "-map", "[outv]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            "-c:a", "aac",
            "-ar", "44100",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path)
        ])

        logger.info(f"Rendering short with layout='{layout}' start={start_time} end={end_time}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                cwd=sub_cwd
            )
            return str(output_path)
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg render error:\n{e.stderr[-3000:]}")
            raise RuntimeError("FFmpeg render failed. Check server logs.")
