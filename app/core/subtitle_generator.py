import re
import math
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.config import SUBTITLE_PRESETS

logger = logging.getLogger("clipstream.subtitle_generator")

# Common viral word-to-emoji mapping
EMOJI_MAP = {
    r"\b(money|rich|dollar|cash|bank|paid|crypto)\b": "💸",
    r"\b(fire|hot|lit|insane|wild)\b": "🔥",
    r"\b(win|won|winner|first|champion|clutch|goat)\b": "🏆",
    r"\b(dead|died|kill|killed|rip|skull|headshot)\b": "💀",
    r"\b(shock|shocked|omg|crazy|impossible|unreal)\b": "🤯",
    r"\b(car|drive|fast|speed)\b": "🏎️",
    r"\b(laugh|funny|lol|lmao|joke)\b": "😂",
    r"\b(love|heart|favorite)\b": "❤️",
    r"\b(stop|wait|pause|danger)\b": "🛑",
    r"\b(brain|smart|iq|genius)\b": "🧠",
    r"\b(fight|hit|punch|strike|battle)\b": "🥊",
    r"\b(secret|mystery|lie|exposed)\b": "🤫",
    r"\b(time|clock|late|hurry)\b": "⏱️",
    r"\b(ghost|scary|horror|creepy)\b": "👻",
    r"\b(king|queen|crown)\b": "👑",
}

def format_ass_timestamp(seconds: float) -> str:
    """Format seconds into ASS timestamp H:MM:SS.cs (centiseconds)."""
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"

class SubtitleGenerator:
    def __init__(self, preset_name: str = "mrbeast", custom_options: Optional[Dict[str, Any]] = None):
        self.preset = dict(SUBTITLE_PRESETS.get(preset_name, SUBTITLE_PRESETS["mrbeast"]))
        if custom_options:
            self.preset.update(custom_options)

    def _find_emoji(self, text: str) -> Optional[str]:
        """Find matching emoji for text."""
        for pattern, emoji in EMOJI_MAP.items():
            if re.search(pattern, text, re.IGNORECASE):
                return emoji
        return None

    def chunk_words(self, words: List[Dict[str, Any]], words_per_chunk: int = 3) -> List[List[Dict[str, Any]]]:
        """Group words into high-retention short 2-4 word cards."""
        if not words:
            return []

        chunks = []
        curr_chunk = []

        for w in words:
            curr_chunk.append(w)
            # Break if reached limit or word ends with strong punctuation
            word_str = w.get("word", "")
            if len(curr_chunk) >= words_per_chunk or word_str.endswith((".", "!", "?")):
                chunks.append(curr_chunk)
                curr_chunk = []

        if curr_chunk:
            chunks.append(curr_chunk)

        return chunks

    def generate_ass(
        self,
        words: List[Dict[str, Any]],
        output_ass_path: str,
        video_width: int = 1080,
        video_height: int = 1920
    ) -> str:
        """
        Generate ASS subtitle content with karaoke active-word animation.
        """
        font_name = self.preset.get("font_family", "Montserrat")
        font_size = self.preset.get("font_size", 68)
        pri_col = self.preset.get("primary_color", "&H00FFFFFF")
        hl_col = self.preset.get("highlight_color", "&H0000E6FF")
        out_col = self.preset.get("outline_color", "&H00000000")
        out_w = self.preset.get("outline_width", 5.5)
        shad_w = self.preset.get("shadow_width", 2.5)
        use_emojis = self.preset.get("emojis", True)

        # Vertical placement:
        # 2 = Bottom Center, 5 = Middle Center
        alignment = 2
        # MarginV determines distance from bottom
        margin_v = 450 if self.preset.get("position") == "middle-bottom" else 280

        header = f"""[Script Info]
Title: ClipStream Viral Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: {video_width}
PlayResY: {video_height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{pri_col},{hl_col},{out_col},&H80000000,-1,0,0,0,100,100,1,0,1,{out_w},{shad_w},{alignment},50,50,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        events = []
        chunks = self.chunk_words(words, words_per_chunk=3)

        for chunk in chunks:
            if not chunk:
                continue

            chunk_start = chunk[0]["start"]
            chunk_end = chunk[-1]["end"]
            
            # Find any emoji for this chunk
            chunk_text = " ".join(w["word"] for w in chunk)
            emoji_str = f" {self._find_emoji(chunk_text)}" if use_emojis and self._find_emoji(chunk_text) else ""

            # For each word in the chunk, generate a dialogue line where that specific word is highlighted
            for i, active_w in enumerate(chunk):
                w_start = active_w["start"]
                # End of this word's highlight is next word's start, or chunk_end
                w_end = chunk[i + 1]["start"] if (i + 1 < len(chunk)) else chunk_end
                if w_end <= w_start:
                    w_end = w_start + 0.15

                start_ts = format_ass_timestamp(w_start)
                end_ts = format_ass_timestamp(w_end)

                # Assemble line: unhighlighted words in pri_col, active word in hl_col
                line_parts = []
                for j, w in enumerate(chunk):
                    clean_word = w["word"].upper().replace("{", "").replace("}", "")
                    if j == i:
                        # Highlighted active word (with slightly larger scale pop)
                        line_parts.append(f"{{\\c{hl_col}\\fscx108\\fscy108}}{clean_word}{{\\fscx100\\fscy100\\c{pri_col}}}")
                    else:
                        line_parts.append(clean_word)

                dialogue_text = f"{{\\fs{font_size}}}" + " ".join(line_parts) + emoji_str
                events.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{dialogue_text}")

        full_content = header + "\n".join(events) + "\n"

        out_path = Path(output_ass_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(full_content)

        return str(out_path)
