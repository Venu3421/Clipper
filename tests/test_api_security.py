import pytest
from pathlib import Path
import os
import sys
import types
from app import config as cfg


def test_root_access(client):
    """Test that root / path is accessible without API key."""
    response = client.get("/")
    assert response.status_code == 200
    assert "ClipStream AI" in response.text


def test_static_access(client):
    """Test that static files are accessible without API key."""
    response = client.get("/static/css/style.css")
    assert response.status_code == 200
    assert "body" in response.text


def test_api_status_no_key(client):
    """Test API status endpoint is protected by API key."""
    response = client.get("/api/status")
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API key."}


def test_api_status_with_key(client, api_headers):
    """Test API status endpoint with valid API key."""
    response = client.get("/api/status", headers=api_headers)
    assert response.status_code == 200
    data = response.json()
    assert "ffmpeg_installed" in data
    assert "gemini_configured" in data


def test_get_keys_masked(client, api_headers):
    """Test that GET /settings/keys returns masked API keys."""
    response = client.get("/api/settings/keys", headers=api_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["gemini_api_key"] == "mock...23"  # mock-gemini-key-123
    assert data["groq_api_key"] == "mock...56"  # mock-groq-key-456
    assert data["gemini_is_set"]
    assert data["groq_is_set"]


def test_save_keys_and_mask(client, api_headers, monkeypatch):
    """Test saving new keys and verifies masking in response."""
    new_gemini_key = "AIzaSyTESTNEWGEMINIKEY123456789"
    new_groq_key = "gsk_testnewgroqkey123456789"
    # save_keys calls update_api_keys() which itself calls get_api_keys().
    # Patch update_api_keys directly so no real .env file is touched.
    monkeypatch.setattr(
        "app.api.routes.update_api_keys",
        lambda gemini_key=None, groq_key=None: {
            "gemini_api_key": gemini_key if gemini_key is not None else "mock-gemini-key-123",
            "groq_api_key": groq_key if groq_key is not None else "mock-groq-key-456",
        },
    )
    response = client.post(
        "/api/settings/keys",
        headers=api_headers,
        json={
            "gemini_api_key": new_gemini_key,
            "groq_api_key": new_groq_key,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["gemini_api_key"] == "AIza...89"  # AIzaSyTESTNEWGEMINIKEY123456789
    assert data["groq_api_key"] == "gsk_...89"  # gsk_testnewgroqkey123456789
    assert data["gemini_is_set"]
    assert data["groq_is_set"]


def test_test_key_gemini_success(client, api_headers, monkeypatch):
    """Test successful Gemini key validation."""
    import types
    mock_genai = types.ModuleType("google.genai")
    mock_genai.Client = lambda api_key: type("MockGenaiClient", (), {
        "models": type("MockModels", (), {
            "generate_content": lambda model, contents: type("MockResponse", (), {"text": "OK"})
        })
    })()
    monkeypatch.setitem(sys.modules, "google", types.ModuleType("google"))
    monkeypatch.setitem(sys.modules, "google.genai", mock_genai)
    response = client.post(
        "/api/settings/test-key",
        headers=api_headers,
        json={"provider": "gemini", "api_key": "valid-gemini-key"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Gemini connection verified!"}


def test_test_key_groq_success(client, api_headers, monkeypatch):
    """Test successful Groq key validation."""
    import types
    mock_groq = types.ModuleType("groq")
    mock_groq.Groq = lambda api_key: type("MockGroqClient", (), {
        "chat": type("MockChat", (), {
            "completions": type("MockCompletions", (), {
                "create": lambda messages, model, max_tokens: type(
                    "MockChatCompletion",
                    (),
                    {"choices": [type("MockChoice", (), {"message": type("MockMessage", (), {"content": "pong"})})]},
                )
            })
        })
    })()
    monkeypatch.setitem(sys.modules, "groq", mock_groq)
    response = client.post(
        "/api/settings/test-key",
        headers=api_headers,
        json={"provider": "groq", "api_key": "valid-groq-key"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Groq connection verified!"}


def test_test_key_gemini_failure(client, api_headers, monkeypatch):
    """Test Gemini key validation failure."""
    monkeypatch.setitem(sys.modules, "google.genai", None)  # Force import error
    response = client.post(
        "/api/settings/test-key",
        headers=api_headers,
        json={"provider": "gemini", "api_key": "invalid"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "error", "message": "Gemini connection failed."} # Generic message


def test_test_key_groq_failure(client, api_headers, monkeypatch):
    """Test Groq key validation failure."""
    monkeypatch.setitem(sys.modules, "groq", None)  # Force import error
    response = client.post(
        "/api/settings/test-key",
        headers=api_headers,
        json={"provider": "groq", "api_key": "invalid"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "error", "message": "Groq connection failed."} # Generic message


def test_path_traversal_download_export(client, api_headers, tmp_storage):
    """Test path traversal attempt on /api/download/{filename}."""
    bad_filename = "../../../../etc/passwd"
    response = client.get(f"/api/download/{bad_filename}", headers=api_headers)
    assert response.status_code in (403, 404)


def test_path_traversal_get_clip_media(client, api_headers, tmp_storage):
    """Test path traversal attempt on /api/media/clip/{filename}."""
    bad_filename = "../../../../Windows/System32/notepad.exe"
    response = client.get(f"/api/media/clip/{bad_filename}", headers=api_headers)
    assert response.status_code in (403, 404)


def test_path_traversal_get_temp_media(client, api_headers, tmp_storage):
    """Test path traversal attempt on /api/media/temp/{filename}."""
    bad_filename = "..\\..\\..\\boot.ini" # Windows-style traversal
    response = client.get(f"/api/media/temp/{bad_filename}", headers=api_headers)
    assert response.status_code in (403, 404)


def test_ssrf_process_vod_file_scheme(client, api_headers, tmp_storage):
    """Test SSRF attempt with file:// scheme in process_vod."""
    response = client.post(
        "/api/process/vod",
        headers=api_headers,
        json={
            "url": "file:///etc/passwd",
            "content_type": "gaming",
            "min_clip_duration": 20,
            "max_clip_duration": 60
        },
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "URL must be http(s) or a local file inside the uploads directory."}


def test_ssrf_process_vod_internal_ip(client, api_headers, tmp_storage):
    """Test SSRF attempt with internal IP in process_vod (mocking yt-dlp)."""
    # yt-dlp will try to fetch this. For this test, we just check the _is_allowed_source logic
    response = client.post(
        "/api/process/vod",
        headers=api_headers,
        json={
            "url": "http://127.0.0.1/internal-resource",
            "content_type": "gaming",
            "min_clip_duration": 20,
            "max_clip_duration": 60
        },
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "URL must be http(s) or a local file inside the uploads directory."}


def test_process_vod_local_uploads_access(client, api_headers, tmp_storage):
    """Test processing a local file in the allowed uploads directory."""
    uploads_dir = tmp_storage / "downloads" / "uploads"
    test_file = uploads_dir / "test_video.mp4"
    test_file.write_text("mock video content")

    # Mock ffmpeg utils to avoid actual ffmpeg calls
    class MockProbeVideo:
        def __call__(self, *args, **kwargs): return {"duration": 60, "width": 1280, "height": 720}
    class MockExtractAudio: pass
    class MockExtractClip: pass
    class MockGenerateThumbnail: pass
    class MockCheckFfmpeg:
        def __call__(self, *args, **kwargs): return True

    client.app.dependency_overrides[app.core.ffmpeg_utils.probe_video] = MockProbeVideo()
    client.app.dependency_overrides[app.core.ffmpeg_utils.extract_audio] = MockExtractAudio()
    client.app.dependency_overrides[app.core.ffmpeg_utils.extract_clip] = MockExtractClip()
    client.app.dependency_overrides[app.core.ffmpeg_utils.generate_thumbnail] = MockGenerateThumbnail()
    client.app.dependency_overrides[app.core.ffmpeg_utils.check_ffmpeg] = MockCheckFfmpeg()

    response = client.post(
        "/api/process/vod",
        headers=api_headers,
        json={
            "url": str(test_file),
            "content_type": "gaming",
            "min_clip_duration": 20,
            "max_clip_duration": 60
        },
    )
    # We expect this to fail later in the processing pipeline due to actual ffmpeg/AI mocks
    # but it should pass the URL validation step.
    assert response.status_code == 500  # Expecting internal server error due to missing actual ffmpeg/AI
    assert "Internal server error" in response.json()["detail"]


def test_process_vod_remote_url(client, api_headers, tmp_storage, monkeypatch):
    """Test processing a valid remote URL (mocking yt-dlp)."""
    # Mock VideoDownloader to avoid actual network call
    class MockVideoDownloader:
        def download_video(self, url): return {"file_path": str(tmp_storage / "downloads" / "test_remote_video.mp4"), "title": "Test Video", "video_id": "test_id", "duration": 300}
        def get_info(self, url): return {"id": "test_id", "title": "Test Video", "duration": 300, "is_live": False}
    monkeypatch.setattr("app.api.routes.VideoDownloader", MockVideoDownloader)

    # Mock ffmpeg utils to avoid actual ffmpeg calls
    class MockProbeVideo:
        def __call__(self, *args, **kwargs): return {"duration": 60, "width": 1280, "height": 720}
    class MockExtractAudio: pass
    class MockExtractClip: pass
    class MockGenerateThumbnail: pass
    class MockCheckFfmpeg:
        def __call__(self, *args, **kwargs): return True

    client.app.dependency_overrides[app.core.ffmpeg_utils.probe_video] = MockProbeVideo()
    client.app.dependency_overrides[app.core.ffmpeg_utils.extract_audio] = MockExtractAudio()
    client.app.dependency_overrides[app.core.ffmpeg_utils.extract_clip] = MockExtractClip()
    client.app.dependency_overrides[app.core.ffmpeg_utils.generate_thumbnail] = MockGenerateThumbnail()
    client.app.dependency_overrides[app.core.ffmpeg_utils.check_ffmpeg] = MockCheckFfmpeg()

    # Mock transcriber and viral scorer
    class MockAudioTranscriber:
        def transcribe(self, audio_path): return {"text": "mock transcript", "words": [], "engine": "mock", "language": "en"}
    class MockViralScorer:
        def evaluate_clip(self, *args, **kwargs): return {"virality_score": 90, "hook_score": 9, "hook_analysis": "", "viral_reason": "", "viral_titles": [], "suggested_caption": "", "tags": []}
    monkeypatch.setattr("app.api.routes.AudioTranscriber", MockAudioTranscriber)
    monkeypatch.setattr("app.api.routes.ViralScorer", MockViralScorer)

    response = client.post(
        "/api/process/vod",
        headers=api_headers,
        json={
            "url": "https://www.youtube.com/watch?v=mockvideoid",
            "content_type": "gaming",
            "min_clip_duration": 20,
            "max_clip_duration": 60
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["video_info"]["video_id"] == "test_id"


def test_process_vod_bad_url_scheme(client, api_headers):
    """Test that process_vod rejects invalid URL schemes (e.g., ftp)."""
    response = client.post(
        "/api/process/vod",
        headers=api_headers,
        json={
            "url": "ftp://evil.com/malicious.mp4",
            "content_type": "gaming",
            "min_clip_duration": 20,
            "max_clip_duration": 60
        },
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "URL must be http(s) or a local file inside the uploads directory."}


def test_process_vod_arbitrary_local_path_outside_uploads(client, api_headers, tmp_storage):
    """Test that process_vod rejects arbitrary local file paths outside the uploads dir."""
    test_file = tmp_storage / "test_outside.mp4"
    test_file.write_text("mock content")

    response = client.post(
        "/api/process/vod",
        headers=api_headers,
        json={
            "url": str(test_file),
            "content_type": "gaming",
            "min_clip_duration": 20,
            "max_clip_duration": 60
        },
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "URL must be http(s) or a local file inside the uploads directory."}
