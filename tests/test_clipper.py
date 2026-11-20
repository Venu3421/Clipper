import os
import sys
import unittest
from pathlib import Path

# Add root directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import (
    FFMPEG_PATH,
    FFPROBE_PATH,
    get_api_keys,
    update_api_keys,
    LAYOUT_PRESETS,
    SUBTITLE_PRESETS
)
from app.core.chat_analyzer import ChatSpikeDetector
from app.core.subtitle_generator import SubtitleGenerator, format_ass_timestamp
from app.core.viral_scorer import ViralScorer

class TestClipStreamCore(unittest.TestCase):

    def test_ffmpeg_detection(self):
        """Verify that FFmpeg and FFprobe are properly detected."""
        self.assertIsNotNone(FFMPEG_PATH, "FFMPEG_PATH must be found")
        self.assertTrue(Path(FFMPEG_PATH).exists(), f"FFmpeg binary must exist at {FFMPEG_PATH}")
        self.assertIsNotNone(FFPROBE_PATH, "FFPROBE_PATH must be found")
        self.assertTrue(Path(FFPROBE_PATH).exists(), f"FFprobe binary must exist at {FFPROBE_PATH}")

    def test_chat_spike_detection(self):
        """Verify chat velocity calculation and peak clustering."""
        detector = ChatSpikeDetector(bucket_size_sec=5, min_clip_duration=20, max_clip_duration=45)

        # Generate synthetic chat messages with a massive spike around 60 seconds
        messages = []
        # Normal baseline: 1 message every 5 seconds
        for sec in range(0, 120, 5):
            messages.append({"time_in_seconds": float(sec), "message": "hello stream", "author": "user1"})

        # Hype spike between 55s and 65s (30 messages with emotes)
        for _ in range(30):
            messages.append({
                "time_in_seconds": 60.0,
                "message": "OMG BRO NO WAY LMAO KEKW 🔥 W W W",
                "author": "hype_user"
            })

        result = detector.analyze_chat_events(messages, video_duration=120.0)

        self.assertIn("spikes", result)
        self.assertGreater(len(result["spikes"]), 0, "Should detect at least 1 spike")
        top_spike = result["spikes"][0]

        # The top spike should be centered near 60 seconds
        self.assertTrue(top_spike["start_time"] <= 60.0 <= top_spike["end_time"])
        self.assertGreater(top_spike["hype_score"], 20.0)
        self.assertIn(top_spike["tag"], ["funny", "hype", "shock"])

    def test_subtitle_generator_ass(self):
        """Verify ASS subtitle generation with karaoke animation and emojis."""
        generator = SubtitleGenerator(preset_name="mrbeast")

        words = [
            {"word": "Bro", "start": 0.5, "end": 0.8},
            {"word": "look", "start": 0.85, "end": 1.1},
            {"word": "at", "start": 1.15, "end": 1.3},
            {"word": "this", "start": 1.35, "end": 1.6},
            {"word": "insane", "start": 1.65, "end": 2.1}, # Matches 'fire/insane' -> 🔥
            {"word": "win", "start": 2.15, "end": 2.6},    # Matches 'win' -> 🏆
        ]

        test_ass_path = BASE_DIR / "storage" / "temp" / "test_captions.ass"
        generated_path = generator.generate_ass(words, str(test_ass_path), 1080, 1920)

        self.assertTrue(Path(generated_path).exists())
        with open(generated_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("[Script Info]", content)
        self.assertIn("PlayResX: 1080", content)
        self.assertIn("PlayResY: 1920", content)
        self.assertIn("Dialogue:", content)
        # Verify active word highlight tag exists
        self.assertIn(r"\fscx108", content)

    def test_viral_scorer_heuristic(self):
        """Verify heuristic virality evaluator when no API key is provided."""
        scorer = ViralScorer()
        res = scorer._evaluate_heuristic(
            transcript="I cannot believe we just pulled off that impossible victory clutch!",
            duration=35.0,
            tag="hype",
            hype_score=40.0
        )

        self.assertIn("virality_score", res)
        self.assertGreaterEqual(res["virality_score"], 75)
        self.assertIn("viral_titles", res)
        self.assertGreater(len(res["viral_titles"]), 0)

    def test_ass_timestamp_format(self):
        """Verify ASS timestamp formatting."""
        formatted = format_ass_timestamp(65.42)
        self.assertEqual(formatted, "0:01:05.42")

if __name__ == "__main__":
    unittest.main()
