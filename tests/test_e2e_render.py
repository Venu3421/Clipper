import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import FFMPEG_PATH, TEMP_DIR, EXPORTS_DIR
from app.core.ffmpeg_utils import probe_video, extract_audio
from app.core.subtitle_generator import SubtitleGenerator
from app.core.video_processor import VideoProcessor

def test_render_pipeline():
    print("Testing End-to-End Render Pipeline...")

    # 1. Generate a 4-second synthetic test video (1280x720, 30fps) with a sine beep audio
    test_src = TEMP_DIR / "synthetic_test_video.mp4"
    gen_cmd = [
        FFMPEG_PATH,
        "-y",
        "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=4",
        "-t", "4",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(test_src)
    ]
    subprocess.run(gen_cmd, capture_output=True, check=True)
    print(f"Generated synthetic video at: {test_src}")

    # 2. Extract audio
    test_audio = TEMP_DIR / "synthetic_audio.wav"
    extract_audio(str(test_src), str(test_audio))
    assert Path(test_audio).exists(), "Audio extraction failed"
    print("Audio extraction verified.")

    # 3. Generate ASS kinetic subtitles
    words = [
        {"word": "Welcome", "start": 0.5, "end": 1.2},
        {"word": "to", "start": 1.25, "end": 1.5},
        {"word": "ClipStream", "start": 1.55, "end": 2.2},
        {"word": "AI", "start": 2.25, "end": 2.8},
        {"word": "viral", "start": 2.85, "end": 3.4},
        {"word": "shorts", "start": 3.45, "end": 3.9}
    ]
    sub_gen = SubtitleGenerator(preset_name="mrbeast")
    ass_path = TEMP_DIR / "test_synthetic.ass"
    sub_gen.generate_ass(words, str(ass_path), 1080, 1920)
    assert Path(ass_path).exists(), "ASS generation failed"
    print("ASS subtitle generation verified.")

    # 4. Render Layout 1: Podcast Blurred Letterbox
    processor = VideoProcessor()
    out_blur = processor.render_short(
        input_video_path=str(test_src),
        output_filename="test_short_podcast_blur.mp4",
        layout="podcast_blur",
        subtitle_ass_path=str(ass_path)
    )
    assert Path(out_blur).exists(), "Podcast blur render failed"
    blur_info = probe_video(out_blur)
    print(f"Podcast Blur Render Output: {blur_info['width']}x{blur_info['height']} duration={blur_info['duration']}s")
    assert blur_info["width"] == 1080 and blur_info["height"] == 1920, "Podcast blur must be 1080x1920"

    # 5. Render Layout 2: Gaming Split Screen
    out_split = processor.render_short(
        input_video_path=str(test_src),
        output_filename="test_short_gaming_split.mp4",
        layout="gaming_split",
        subtitle_ass_path=str(ass_path),
        custom_params={"facecam_x": 0, "facecam_y": 0, "facecam_w": 400, "facecam_h": 300}
    )
    assert Path(out_split).exists(), "Gaming split render failed"
    split_info = probe_video(out_split)
    print(f"Gaming Split Render Output: {split_info['width']}x{split_info['height']} duration={split_info['duration']}s")
    assert split_info["width"] == 1080 and split_info["height"] == 1920, "Gaming split must be 1080x1920"

    print("\n✓ ALL END-TO-END RENDER PIPELINE CHECKS PASSED!\n")

if __name__ == "__main__":
    test_render_pipeline()
