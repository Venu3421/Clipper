import os
import re
import uuid
import time
import shutil
import threading
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import (
    get_api_keys,
    update_api_keys,
    LAYOUT_PRESETS,
    SUBTITLE_PRESETS,
    FFMPEG_PATH,
    FFPROBE_PATH,
    TEMP_DIR,
    EXPORTS_DIR,
    DOWNLOADS_DIR,
    CLIPS_DIR
)
from app.api.models import (
    ApiKeysModel,
    TestKeyRequest,
    ProcessVideoRequest,
    LiveStartRequest,
    ExportClipRequest,
    KeysResponse,
    TestKeyResponse,
    ExportResponse,
)
from app.core.ffmpeg_utils import (
    probe_video,
    extract_audio,
    extract_clip,
    generate_thumbnail,
    check_ffmpeg
)
from app.core.downloader import VideoDownloader
from app.core.live_recorder import LiveStreamRecorder
from app.core.chat_analyzer import (
    ChatSpikeDetector,
    LiveChatStreamReader,
    fetch_chat_replay
)
from app.core.audio_detector import analyze_audio_energy
from app.core.transcriber import AudioTranscriber
from app.core.subtitle_generator import SubtitleGenerator
from app.core.viral_scorer import ViralScorer
from app.core.video_processor import VideoProcessor

logger = logging.getLogger("clipstream.routes")
router = APIRouter(prefix="/api")

# Global singleton states for live monitoring
active_live_recorder: Optional[LiveStreamRecorder] = None
active_live_chat_reader: Optional[LiveChatStreamReader] = None
live_chat_buffer: List[Dict[str, Any]] = []
_live_state_lock = threading.Lock()


_ALLOWED_URL_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)

# Hostnames/IPs that must never be fetched server-side (SSRF protection)
_BLOCKED_HOSTS = frozenset({
    "localhost", "127.0.0.1", "::1", "0.0.0.0",
    "169.254.169.254",  # AWS / cloud metadata endpoint
})
_BLOCKED_PREFIXES = ("10.", "192.168.", "172.16.", "172.17.", "172.18.",
                     "172.19.", "172.20.", "172.21.", "172.22.", "172.23.",
                     "172.24.", "172.25.", "172.26.", "172.27.", "172.28.",
                     "172.29.", "172.30.", "172.31.", "fc00:", "fe80:", "fd00:")


def _host_is_blocked(host: str) -> bool:
    host = host.lower().strip().rstrip(".")
    if host in _BLOCKED_HOSTS:
        return True
    for prefix in _BLOCKED_PREFIXES:
        if host.startswith(prefix):
            return True
    return False


def _is_allowed_source(url: str) -> bool:
    """Return True only for http(s) URLs (non-internal) or files inside uploads."""
    if not isinstance(url, str) or not url:
        return False
    if _ALLOWED_URL_RE.match(url):
        # Extract host and reject internal / metadata addresses (SSRF)
        try:
            host = url.split("/", 3)[2]  # scheme://host[:port]/...
        except IndexError:
            return False
        if _host_is_blocked(host):
            return False
        return True
    # Local file: must live inside the configured uploads directory
    try:
        resolved = Path(url).resolve()
    except Exception:
        return False
    uploads = (DOWNLOADS_DIR / "uploads").resolve()
    uploads.mkdir(parents=True, exist_ok=True)
    return str(resolved).startswith(str(uploads) + os.sep) or resolved == uploads


def _safe_path(base_dir: Path, filename: str) -> Path:
    """Resolve a user-supplied filename inside base_dir and reject escapes.

    Raises HTTPException(403) if the resolved path leaves the base directory,
    or if filename is not a bare name (no path separators / traversal).
    """
    if not filename or not isinstance(filename, str):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    # Reject anything that isn't a single path component
    if filename != os.path.basename(filename) or filename in (".", ".."):
        raise HTTPException(status_code=403, detail="Invalid filename.")
    base = Path(base_dir).resolve()
    resolved = (base / filename).resolve()
    if not str(resolved).startswith(str(base) + os.sep) and resolved != base:
        raise HTTPException(status_code=403, detail="Access denied.")
    return resolved

@router.get("/status")
def get_system_status():
    """Return status of system components, FFmpeg, and API keys."""
    keys = get_api_keys()
    return {
        "ffmpeg_installed": check_ffmpeg(),
        "ffmpeg_path": FFMPEG_PATH,
        "ffprobe_path": FFPROBE_PATH,
        "gemini_configured": bool(keys.get("gemini_api_key")),
        "groq_configured": bool(keys.get("groq_api_key")),
        "layout_presets": LAYOUT_PRESETS,
        "subtitle_presets": SUBTITLE_PRESETS
    }

def _mask_key(key: str) -> str:
    """Return a masked representation of an API key.

    Never returns the full key, even for short values — a ≤10-char key would
    otherwise be disclosed in full by the previous slice-based mask.
    """
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-2:]}"


@router.get("/settings/keys", response_model=KeysResponse)
def get_keys():
    """Get currently configured API keys (masked for security)."""
    keys = get_api_keys()
    gemini = keys.get("gemini_api_key", "")
    groq = keys.get("groq_api_key", "")
    return {
        "gemini_api_key": _mask_key(gemini),
        "groq_api_key": _mask_key(groq),
        "gemini_is_set": bool(gemini),
        "groq_is_set": bool(groq)
    }

@router.post("/settings/keys")
def save_keys(payload: ApiKeysModel):
    """Save API keys into environment and .env."""
    updated = update_api_keys(
        gemini_key=payload.gemini_api_key,
        groq_key=payload.groq_api_key
    )
    return {
        "status": "success",
        "message": "API keys saved successfully.",
        "gemini_is_set": bool(updated.get("gemini_api_key")),
        "groq_is_set": bool(updated.get("groq_api_key"))
    }

@router.post("/settings/test-key", response_model=TestKeyResponse)
def test_key(payload: TestKeyRequest):
    """Test validity of a provided API key."""
    provider = payload.provider
    key = payload.api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key cannot be empty.")

    if provider == "gemini":
        try:
            from google import genai
            client = genai.Client(api_key=key)
            client.models.generate_content(
                model="gemini-2.5-flash",
                contents="Reply with 'OK'."
            )
            return {"status": "success", "message": "Gemini connection verified!"}
        except Exception as e:
            logger.warning("Gemini key test failed: %s", e)
            return {"status": "error", "message": "Gemini connection failed."}

    elif provider == "groq":
        try:
            from groq import Groq
            client = Groq(api_key=key)
            client.chat.completions.create(
                messages=[{"role": "user", "content": "Ping"}],
                model="openai/gpt-oss-20b",
                max_tokens=5
            )
            return {"status": "success", "message": "Groq connection verified!"}
        except Exception as e:
            logger.warning("Groq key test failed: %s", e)
            return {"status": "error", "message": "Groq connection failed."}

@router.post("/process/vod")
def process_vod(req: ProcessVideoRequest):
    """
    Process a YouTube VOD or pre-recorded video:
    1. Downloads video/audio
    2. Analyzes chat spikes or audio energy peaks
    3. Transcribes candidate clips with Whisper
    4. Evaluates viral potential with AI
    """
    logger.info(f"Processing VOD URL: {req.url}")
    downloader = VideoDownloader()

    # Only allow remote URLs or files inside the uploads directory.
    # Arbitrary local paths (e.g. C:\Windows\... or /etc/shadow) are rejected
    # to prevent the server from reading/processing any file on disk.
    if not _is_allowed_source(req.url):
        raise HTTPException(
            status_code=400,
            detail="URL must be http(s) or a local file inside the uploads directory."
        )

    # Check if local file or remote URL
    if os.path.exists(req.url):
        video_path = req.url
        title = Path(video_path).stem
        video_id = str(uuid.uuid4())[:8]
        duration = probe_video(video_path)["duration"]
    else:
        # Download video via yt-dlp
        download_result = downloader.download_video(req.url)
        video_path = download_result["file_path"]
        title = download_result["title"]
        video_id = download_result["video_id"]
        duration = download_result["duration"] or probe_video(video_path)["duration"]

    # Extract 16kHz mono audio for Whisper & RMS analysis
    audio_path = str(TEMP_DIR / f"{video_id}_audio.wav")
    extract_audio(video_path, audio_path)

    # 1. Analyze Chat Replay (if available)
    candidate_spikes = []
    chat_detector = ChatSpikeDetector(
        min_clip_duration=req.min_clip_duration,
        max_clip_duration=req.max_clip_duration
    )

    chat_messages = fetch_chat_replay(video_id, max_messages=10000)
    chat_analysis = None
    if chat_messages:
        logger.info(f"Loaded {len(chat_messages)} chat replay messages.")
        chat_analysis = chat_detector.analyze_chat_events(chat_messages, video_duration=duration)
        candidate_spikes = chat_analysis.get("spikes", [])

    # 2. Audio Energy Analysis (for both gaming screams and podcast punchlines)
    audio_analysis = analyze_audio_energy(
        audio_path,
        min_clip_sec=req.min_clip_duration,
        max_clip_sec=req.max_clip_duration
    )
    audio_peaks = audio_analysis.get("peaks", [])

    # Merge candidate moments
    merged_candidates = []
    if candidate_spikes:
        # Prioritize chat spikes, enrich with audio energy
        for s in candidate_spikes[:6]: # Top 6 chat spikes
            merged_candidates.append({
                "start_time": s["start_time"],
                "end_time": s["end_time"],
                "duration": s["duration"],
                "tag": s.get("tag", "hype"),
                "hype_score": s.get("hype_score", 15.0),
                "source": "chat_spike"
            })
    
    # If fewer than 4 clips, supplement with top audio peaks
    for a in audio_peaks:
        if len(merged_candidates) >= 5:
            break
        # Avoid overlapping existing candidates
        overlaps = any(
            abs(a["start_time"] - m["start_time"]) < 20
            for m in merged_candidates
        )
        if not overlaps:
            merged_candidates.append({
                "start_time": a["start_time"],
                "end_time": a["end_time"],
                "duration": a["duration"],
                "tag": "audio_climax",
                "hype_score": round(a["score"] * 10, 1),
                "source": "audio_energy"
            })

    # If still no candidates (e.g. calm short video), create default smart windows
    if not merged_candidates:
        step = max(30.0, duration / 3.0)
        for i in range(min(3, int(duration // 30))):
            s_time = i * step
            e_time = min(duration, s_time + 45.0)
            merged_candidates.append({
                "start_time": round(s_time, 1),
                "end_time": round(e_time, 1),
                "duration": round(e_time - s_time, 1),
                "tag": "highlight",
                "hype_score": 10.0,
                "source": "interval"
            })

    # 3. Transcribe & Score Top Candidates
    transcriber = AudioTranscriber()
    scorer = ViralScorer()
    processed_clips = []

    for idx, c in enumerate(merged_candidates[:5]):
        clip_id = f"{video_id}_clip_{idx+1}"
        clip_audio_path = str(TEMP_DIR / f"{clip_id}.wav")
        clip_video_path = str(CLIPS_DIR / f"{clip_id}_raw.mp4")
        thumb_path = str(TEMP_DIR / f"{clip_id}_thumb.jpg")

        # Extract clip audio for transcription (re-encode for accurate cut)
        extract_clip(video_path, c["start_time"], c["end_time"], clip_video_path, reencode=True)
        extract_audio(clip_video_path, clip_audio_path)

        # Generate thumbnail at peak time
        thumb_timestamp = c["start_time"] + (c["duration"] / 2.0)
        try:
            generate_thumbnail(video_path, thumb_timestamp, thumb_path)
        except Exception:
            pass

        # Transcribe with Whisper (word-level timestamps)
        transcription = transcriber.transcribe(clip_audio_path)
        transcript_text = transcription.get("text", "")
        words = transcription.get("words", [])

        # Normalize word timestamps relative to clip start (0.0s)
        # Note: since clip audio is already cut, words are relative to 0.0s
        
        # Evaluate Virality with AI
        ai_eval = scorer.evaluate_clip(
            transcript=transcript_text,
            duration=c["duration"],
            tag=c["tag"],
            hype_score=c["hype_score"]
        )

        processed_clips.append({
            "clip_id": clip_id,
            "raw_video_path": clip_video_path,
            "source_video_path": video_path,
            "thumbnail_path": thumb_path if Path(thumb_path).exists() else None,
            "start_time": c["start_time"],
            "end_time": c["end_time"],
            "duration": c["duration"],
            "tag": c["tag"],
            "hype_score": c["hype_score"],
            "source": c["source"],
            "transcript": transcript_text,
            "words": words,
            "virality_score": ai_eval.get("virality_score", 85),
            "hook_score": ai_eval.get("hook_score", 8),
            "hook_analysis": ai_eval.get("hook_analysis", ""),
            "viral_reason": ai_eval.get("viral_reason", ""),
            "viral_titles": ai_eval.get("viral_titles", [title]),
            "suggested_caption": ai_eval.get("suggested_caption", ""),
            "tags": ai_eval.get("tags", ["#shorts", "#viral"])
        })

    # Sort processed clips by virality score
    processed_clips.sort(key=lambda x: x["virality_score"], reverse=True)

    return {
        "status": "success",
        "video_info": {
            "title": title,
            "video_id": video_id,
            "duration": duration,
            "source_path": video_path
        },
        "chat_timeline": chat_analysis.get("timeline", []) if chat_analysis else [],
        "audio_timeline": audio_analysis.get("timeline", []),
        "clips": processed_clips
    }

@router.post("/live/start")
def start_live_stream(req: LiveStartRequest):
    """Start capturing a live stream via Streamlink and monitoring live chat."""
    global active_live_recorder, active_live_chat_reader, live_chat_buffer
    with _live_state_lock:
        if active_live_recorder and active_live_recorder.is_recording:
            return {"status": "running", "message": "Live recorder is already recording.", "session": active_live_recorder.get_status()}

        live_chat_buffer = []
        active_live_recorder = LiveStreamRecorder(req.url)
        active_live_recorder.start(quality=req.quality)

        # If YouTube Live URL, also start LiveChatStreamReader
        video_id_match = VideoDownloader().get_info(req.url) if "youtube" in req.url or "youtu.be" in req.url else None
        if video_id_match and video_id_match.get("id"):
            yt_id = video_id_match["id"]
            def on_msg(item):
                # The chat reader runs on its own thread; append under the lock.
                with _live_state_lock:
                    live_chat_buffer.append(item)
            active_live_chat_reader = LiveChatStreamReader(yt_id, on_message=on_msg)
            active_live_chat_reader.start()

        session_id = active_live_recorder.session_id

    return {
        "status": "started",
        "message": f"Live stream capture started for {req.url}",
        "session_id": session_id
    }

@router.get("/live/status")
def get_live_status():
    """Get real-time live recorder status and recent chat velocity."""
    global active_live_recorder, live_chat_buffer
    with _live_state_lock:
        if not active_live_recorder:
            return {"is_recording": False, "message": "No active recording."}

        recorder = active_live_recorder
        snapshot = list(live_chat_buffer)

    rec_status = recorder.get_status()
    # Compute chat velocity in the last 15 seconds
    now_sec = rec_status.get("elapsed_seconds", 0)
    recent_msgs = [m for m in snapshot if now_sec - m.get("time_in_seconds", 0) <= 15]
    recent_velocity = len(recent_msgs) / 15.0 if recent_msgs else 0.0

    return {
        "recording": rec_status,
        "chat_message_count": len(snapshot),
        "recent_velocity": round(recent_velocity, 2),
        "recent_messages": snapshot[-10:] if snapshot else []
    }

@router.post("/live/stop")
def stop_live_stream():
    """Stop live recording, remux file, and prepare for clipping."""
    global active_live_recorder, active_live_chat_reader, live_chat_buffer
    with _live_state_lock:
        if not active_live_recorder:
            return {"status": "error", "message": "No active recorder to stop."}
        recorder = active_live_recorder
        chat_reader = active_live_chat_reader
        active_live_recorder = None
        active_live_chat_reader = None
        live_chat_buffer = []

    stop_result = recorder.stop()
    if chat_reader:
        chat_reader.stop()

    return {
        "status": "stopped",
        "result": stop_result,
        "chat_messages_recorded": len(live_chat_buffer)
    }

@router.post("/export", response_model=ExportResponse)
def export_short(req: ExportClipRequest):
    """
    Export final 1080x1920 YouTube Short with:
    1. Selected Layout (Split, Blur, Face-Track, Center, PiP)
    2. Kinetic Karaoke Subtitles with Emojis burned in
    Single-pass seek, layout compositing, and subtitle burning to guarantee exact duration.
    """
    logger.info(f"Exporting clip with layout '{req.layout}' and subtitle style '{req.subtitle_preset}'...")
    export_id = f"short_{int(time.time())}_{str(uuid.uuid4())[:6]}"
    output_filename = f"{export_id}.mp4"

    # 1. Determine input video file (prefer full source_video_path if available)
    candidate_paths = [
        req.source_video_path,
        req.video_path
    ]
    chosen_video = next((p for p in candidate_paths if p and Path(p).exists()), None)
    if not chosen_video:
        raise HTTPException(status_code=400, detail="Input video file not found.")

    probe = probe_video(chosen_video)
    video_dur = probe.get("duration", 0.0)

    start_t = float(req.start_time)
    end_t = float(req.end_time)

    # Resiliency check: If start_time >= video_dur, the input file was ALREADY a trimmed clip
    if video_dur > 0 and start_t >= video_dur:
        logger.info(f"Start time ({start_t}s) exceeds file duration ({video_dur}s); input is already a pre-cut clip.")
        start_t = 0.0
        end_t = video_dur
    elif video_dur > 0 and end_t > video_dur:
        end_t = video_dur

    if end_t <= start_t:
        end_t = start_t + min(30.0, video_dur - start_t if video_dur > start_t else 30.0)

    # 2. Subtitles Generation
    ass_path = None
    if req.burn_subtitles and req.subtitle_preset != "none":
        words = req.words
        if not words:
            # Transcribe the selected segment
            temp_sub_audio = str(TEMP_DIR / f"{export_id}_sub.wav")
            # Extract audio of the exact slice
            if start_t > 0:
                extract_clip(chosen_video, start_t, end_t, str(TEMP_DIR / f"{export_id}_sub.mp4"), reencode=False)
                extract_audio(str(TEMP_DIR / f"{export_id}_sub.mp4"), temp_sub_audio)
            else:
                extract_audio(chosen_video, temp_sub_audio)
            transcription = AudioTranscriber().transcribe(temp_sub_audio)
            words = transcription.get("words", [])

        if words:
            custom_opts = {}
            if req.subtitle_font_size and req.subtitle_font_size > 0:
                custom_opts["font_size"] = req.subtitle_font_size
                custom_opts["outline_width"] = round(req.subtitle_font_size * 0.08, 1)
            sub_gen = SubtitleGenerator(
                preset_name=req.subtitle_preset,
                custom_options=custom_opts if custom_opts else None
            )
            ass_path = str(TEMP_DIR / f"{export_id}.ass")
            sub_gen.generate_ass(
                words=words,
                output_ass_path=ass_path,
                video_width=1080,
                video_height=1920
            )

    # 3. Composite and Render Multi-Layout Short in single pass
    custom_dict = dict(req.facecam_coords or {})
    custom_dict["focus_position"] = req.focus_position or "auto"
    custom_dict["facecam_position"] = req.facecam_position or "auto"

    processor = VideoProcessor()
    rendered_path = processor.render_short(
        input_video_path=chosen_video,
        output_filename=output_filename,
        layout=req.layout,
        subtitle_ass_path=ass_path,
        custom_params=custom_dict,
        start_time=start_t if start_t > 0 else None,
        end_time=end_t
    )

    file_size_mb = round(os.path.getsize(rendered_path) / (1024 * 1024), 2)
    probe_info = probe_video(rendered_path)

    return {
        "status": "success",
        "export_id": export_id,
        "filename": output_filename,
        "download_url": f"/api/download/{output_filename}",
        "file_size_mb": file_size_mb,
        "duration": probe_info.get("duration", 0),
        "resolution": f"{probe_info.get('width')}x{probe_info.get('height')}",
        "layout": req.layout,
        "subtitle_preset": req.subtitle_preset
    }

@router.get("/download/{filename}")
def download_export(filename: str):
    """Download exported video file."""
    file_path = _safe_path(EXPORTS_DIR, filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=filename
    )

@router.get("/media/clip/{filename}")
def get_clip_media(filename: str):
    """Serve raw preview clips from storage/clips/ for the in-browser preview player."""
    file_path = _safe_path(CLIPS_DIR, filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Clip file not found.")
    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"}
    )

@router.get("/media/temp/{filename}")
def get_temp_media(filename: str):
    """Serve thumbnail or temp preview file."""
    file_path = _safe_path(TEMP_DIR, filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    media_type = "image/jpeg" if filename.endswith((".jpg", ".jpeg")) else "video/mp4"
    return FileResponse(path=str(file_path), media_type=media_type)
