from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator

from app.config import LAYOUT_PRESETS, SUBTITLE_PRESETS

LAYOUTS = tuple(LAYOUT_PRESETS.keys())
SUBTITLE_PRESET_NAMES = tuple(SUBTITLE_PRESETS.keys()) + ("none",)


class ApiKeysModel(BaseModel):
    gemini_api_key: Optional[str] = ""
    groq_api_key: Optional[str] = ""


class TestKeyRequest(BaseModel):
    provider: str  # "gemini" or "groq"
    api_key: str

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("gemini", "groq"):
            raise ValueError("provider must be 'gemini' or 'groq'")
        return v


class ProcessVideoRequest(BaseModel):
    url: str
    content_type: str = "gaming"  # "gaming" or "podcast"
    min_clip_duration: int = Field(default=25, ge=5, le=120)
    max_clip_duration: int = Field(default=60, ge=5, le=600)


class LiveStartRequest(BaseModel):
    url: str
    quality: str = "720p,best"


class ExportClipRequest(BaseModel):
    video_path: str
    source_video_path: Optional[str] = None
    start_time: float = Field(ge=0.0)
    end_time: float = Field(ge=0.0)
    layout: str = "podcast_blur"
    subtitle_preset: str = "mrbeast"
    subtitle_font_size: Optional[int] = Field(default=None, ge=40, le=160)
    focus_position: Optional[str] = "auto"
    facecam_position: Optional[str] = "auto"
    burn_subtitles: bool = True
    custom_title: Optional[str] = None
    facecam_coords: Optional[Dict[str, int]] = None
    words: Optional[List[Dict[str, Any]]] = None

    @field_validator("layout")
    @classmethod
    def _validate_layout(cls, v: str) -> str:
        if v not in LAYOUTS:
            raise ValueError(f"layout must be one of {LAYOUTS}")
        return v

    @field_validator("subtitle_preset")
    @classmethod
    def _validate_subtitle_preset(cls, v: str) -> str:
        if v not in SUBTITLE_PRESET_NAMES:
            raise ValueError(f"subtitle_preset must be one of {SUBTITLE_PRESET_NAMES}")
        return v


class StatusResponse(BaseModel):
    status: str
    message: str


class KeysResponse(BaseModel):
    gemini_api_key: str
    groq_api_key: str
    gemini_is_set: bool
    groq_is_set: bool


class TestKeyResponse(BaseModel):
    status: str
    message: str


class ExportResponse(BaseModel):
    status: str
    export_id: str
    filename: str
    download_url: str
    file_size_mb: float
    duration: float
    resolution: str
    layout: str
    subtitle_preset: str