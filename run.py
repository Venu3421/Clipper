import os
import sys
import webbrowser
import uvicorn
from pathlib import Path

# Add current workspace to python path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import (
    FFMPEG_PATH,
    FFPROBE_PATH,
    ensure_directories,
    get_api_keys
)

def main():
    ensure_directories()
    
    print("\n" + "=" * 65)
    print(" 🚀 Starting ClipStream AI Studio")
    print("=" * 65)
    print(f" • Workspace Directory : {BASE_DIR}")
    print(f" • FFmpeg Binary        : {FFMPEG_PATH or '⚠️ Not detected'}")
    print(f" • FFprobe Binary       : {FFPROBE_PATH or '⚠️ Not detected'}")

    keys = get_api_keys()
    gemini_status = "✓ Ready" if keys.get("gemini_api_key") else "○ Key placeholder in Web UI"
    groq_status = "✓ Ready" if keys.get("groq_api_key") else "○ Key placeholder in Web UI"
    api_token = os.getenv("CLIPSTREAM_API_TOKEN", "").strip()
    print(f" • Google Gemini AI     : {gemini_status}")
    print(f" • Groq Whisper / Llama : {groq_status}")
    print(f" • Web Dashboard URL    : http://127.0.0.1:8000")
    print(f" • API Token Gate       : {'✓ Set' if api_token else '✗ NOT SET (all /api/* requests will 503)'}")
    print("=" * 65 + "\n")

    # Start FastAPI server (localhost-only)
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()
