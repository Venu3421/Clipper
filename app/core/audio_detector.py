import wave
import struct
import math
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np

logger = logging.getLogger("clipstream.audio_detector")

def analyze_audio_energy(
    wav_path: str,
    window_sec: float = 1.0,
    min_clip_sec: float = 25.0,
    max_clip_sec: float = 60.0
) -> Dict[str, Any]:
    """
    Read 16kHz 16-bit PCM WAV and compute RMS audio energy timeline and peaks.
    """
    path = Path(wav_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {wav_path}")

    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        
        duration = n_frames / float(framerate)
        if duration <= 0:
            return {"peaks": [], "timeline": [], "duration": 0}

        # Read frames
        raw_bytes = wf.readframes(n_frames)
        
    # Convert to numpy array (16-bit signed PCM)
    audio_data = np.frombuffer(raw_bytes, dtype=np.int16)
    if n_channels > 1:
        audio_data = audio_data.reshape(-1, n_channels).mean(axis=1)

    # Window size in samples
    window_samples = int(framerate * window_sec)
    if window_samples <= 0:
        window_samples = 16000

    num_windows = len(audio_data) // window_samples
    rms_values = []

    for i in range(num_windows):
        chunk = audio_data[i * window_samples : (i + 1) * window_samples].astype(np.float32)
        # Root Mean Square
        rms = np.sqrt(np.mean(chunk ** 2)) if len(chunk) > 0 else 0.0
        # Convert to relative dB scale
        db = 20 * np.log10(rms + 1e-6)
        rms_values.append(float(db))

    if not rms_values:
        return {"peaks": [], "timeline": [], "duration": duration}

    mean_db = float(np.mean(rms_values))
    std_db = float(np.std(rms_values))
    threshold_db = mean_db + (1.2 * std_db)

    # Find peaks above threshold
    peak_windows = [i for i, db in enumerate(rms_values) if db >= threshold_db]

    candidate_clips = []
    if peak_windows:
        clusters = []
        curr = [peak_windows[0]]
        for idx in peak_windows[1:]:
            if (idx - curr[-1]) * window_sec <= 10:
                curr.append(idx)
            else:
                clusters.append(curr)
                curr = [idx]
        clusters.append(curr)

        for cluster in clusters:
            peak_idx = max(cluster, key=lambda i: rms_values[i])
            peak_time = peak_idx * window_sec
            clip_len = min(max(min_clip_sec, len(cluster) * window_sec + 15), max_clip_sec)

            start_sec = max(0.0, peak_time - (clip_len * 0.6))
            end_sec = min(duration, start_sec + clip_len)

            candidate_clips.append({
                "start_time": round(start_sec, 2),
                "end_time": round(end_sec, 2),
                "duration": round(end_sec - start_sec, 2),
                "peak_time": round(peak_time, 2),
                "peak_db": round(rms_values[peak_idx], 2),
                "score": round((rms_values[peak_idx] - mean_db) / max(std_db, 1.0), 2),
                "type": "audio_energy"
            })

    # Timeline subsampled for UI
    timeline = []
    step = max(1, len(rms_values) // 300) # Keep chart responsive
    for i in range(0, len(rms_values), step):
        timeline.append({
            "time": round(i * window_sec, 1),
            "db": round(rms_values[i], 1)
        })

    candidate_clips.sort(key=lambda c: c["score"], reverse=True)

    return {
        "peaks": candidate_clips,
        "timeline": timeline,
        "mean_db": round(mean_db, 2),
        "threshold_db": round(threshold_db, 2),
        "duration": round(duration, 2)
    }
