import os
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

# Load existing environment variables
load_dotenv(dotenv_path=ENV_PATH, override=True)

STORAGE_DIR = BASE_DIR / "storage"
DOWNLOADS_DIR = STORAGE_DIR / "downloads"
TEMP_DIR = STORAGE_DIR / "temp"
CLIPS_DIR = STORAGE_DIR / "clips"
EXPORTS_DIR = STORAGE_DIR / "exports"
BIN_DIR = BASE_DIR / "bin"
FONTS_DIR = BASE_DIR / "app" / "web" / "static" / "fonts"

def ensure_directories():
    """Ensure all required runtime directories exist."""
    for d in [STORAGE_DIR, DOWNLOADS_DIR, TEMP_DIR, CLIPS_DIR, EXPORTS_DIR, BIN_DIR, FONTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def find_executable(name: str) -> Optional[str]:
    """Locate an executable binary (e.g. ffmpeg or ffprobe)."""
    # 1. Local bin folder
    local_binary = BIN_DIR / f"{name}.exe"
    if local_binary.exists():
        return str(local_binary)
    
    # 2. In PATH
    which_path = shutil.which(name)
    if which_path:
        return which_path

    # 3. Standard WinGet Gyan.FFmpeg installation directory
    winget_root = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if winget_root.exists():
        matches = list(winget_root.glob(f"**/{name}.exe"))
        if matches:
            return str(matches[0])
            
    return None

FFMPEG_PATH = find_executable("ffmpeg")
FFPROBE_PATH = find_executable("ffprobe")

def get_api_keys() -> Dict[str, str]:
    """Retrieve current API keys."""
    # Reload from .env in case it was updated
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    return {
        "gemini_api_key": os.getenv("GEMINI_API_KEY", "").strip(),
        "groq_api_key": os.getenv("GROQ_API_KEY", "").strip(),
    }

def update_api_keys(gemini_key: Optional[str] = None, groq_key: Optional[str] = None) -> Dict[str, str]:
    """Save updated API keys to .env file and environment."""
    current = get_api_keys()
    new_gemini = gemini_key.strip() if gemini_key is not None else current["gemini_api_key"]
    new_groq = groq_key.strip() if groq_key is not None else current["groq_api_key"]

    lines = []
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated_gemini = False
    updated_groq = False
    new_lines = []

    for line in lines:
        if line.startswith("GEMINI_API_KEY="):
            new_lines.append(f"GEMINI_API_KEY={new_gemini}\n")
            updated_gemini = True
        elif line.startswith("GROQ_API_KEY="):
            new_lines.append(f"GROQ_API_KEY={new_groq}\n")
            updated_groq = True
        else:
            new_lines.append(line)

    if not updated_gemini:
        new_lines.append(f"GEMINI_API_KEY={new_gemini}\n")
    if not updated_groq:
        new_lines.append(f"GROQ_API_KEY={new_groq}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    os.environ["GEMINI_API_KEY"] = new_gemini
    os.environ["GROQ_API_KEY"] = new_groq

    return {"gemini_api_key": new_gemini, "groq_api_key": new_groq}

# Layout Presets
LAYOUT_PRESETS = {
    "podcast_blur": {
        "name": "Podcast Blurred Letterbox",
        "description": "Original 16:9 video centered with ambient blurred background filling 9:16. Perfect for podcasts & widescreen discussions.",
        "ideal_for": "podcast"
    },
    "gaming_split": {
        "name": "Gaming Split-Screen",
        "description": "Top section features the streamer facecam, bottom section features full-action gameplay.",
        "ideal_for": "gaming"
    },
    "smart_face_track": {
        "name": "Smart Face-Tracked 9:16",
        "description": "Auto-tracks the primary speaker's face to create a dynamic vertical crop.",
        "ideal_for": "general"
    },
    "center_crop": {
        "name": "Direct Centered Crop",
        "description": "Crops the central 9:16 region directly for centered subjects.",
        "ideal_for": "general"
    },
    "pip": {
        "name": "Picture-in-Picture (PiP)",
        "description": "Main gameplay or screen full vertical, with floating facecam overlay.",
        "ideal_for": "gaming"
    }
}

# Subtitle Presets (Optimized for 1080x1920 mobile viewport)
SUBTITLE_PRESETS = {
    "mrbeast": {
        "name": "MrBeast Hype",
        "font_family": "Montserrat",
        "font_size": 68,
        "primary_color": "&H00FFFFFF",     # White
        "highlight_color": "&H0000E6FF",   # Bright Yellow/Gold (&H00BBGGRR)
        "outline_color": "&H00000000",     # Black outline
        "outline_width": 5.5,
        "shadow_width": 2.5,
        "emojis": True,
        "position": "middle-bottom"
    },
    "hormozi": {
        "name": "Hormozi Impact",
        "font_family": "Montserrat",
        "font_size": 72,
        "primary_color": "&H00FFFFFF",     # White
        "highlight_color": "&H0000FF00",   # Neon Green
        "outline_color": "&H00000000",
        "outline_width": 6.0,
        "shadow_width": 2.0,
        "emojis": True,
        "position": "middle-bottom"
    },
    "cyber_neon": {
        "name": "Cyber Neon",
        "font_family": "Montserrat",
        "font_size": 68,
        "primary_color": "&H00FFFFFF",
        "highlight_color": "&H00FFFF00",   # Cyan
        "outline_color": "&H00990066",     # Deep Neon Violet
        "outline_width": 5.5,
        "shadow_width": 3.5,
        "emojis": True,
        "position": "middle-bottom"
    },
    "minimal": {
        "name": "Clean Minimalist",
        "font_family": "Arial",
        "font_size": 58,
        "primary_color": "&H00FFFFFF",
        "highlight_color": "&H00E0E0E0",
        "outline_color": "&H00000000",
        "outline_width": 4.0,
        "shadow_width": 1.5,
        "emojis": False,
        "position": "bottom"
    }
}

# Ensure directories on module import
ensure_directories()
