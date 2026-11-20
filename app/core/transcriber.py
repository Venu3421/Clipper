import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.config import get_api_keys

logger = logging.getLogger("clipstream.transcriber")

class AudioTranscriber:
    def __init__(self, model_size: str = "base", compute_type: str = "int8"):
        self.model_size = model_size
        self.compute_type = compute_type
        self._local_model = None

    def _get_local_model(self):
        """Lazy load faster-whisper local model."""
        if self._local_model is None:
            from faster_whisper import WhisperModel
            logger.info(f"Loading local faster-whisper model ({self.model_size}, {self.compute_type})...")
            self._local_model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type=self.compute_type
            )
        return self._local_model

    def transcribe(self, audio_path: str) -> Dict[str, Any]:
        """
        Transcribe audio file and extract word-level timestamps.
        Tries Groq API first (ultra-fast), falls back to local faster-whisper.
        """
        api_keys = get_api_keys()
        groq_key = api_keys.get("groq_api_key", "").strip()

        if groq_key:
            try:
                logger.info("Transcribing with Groq Whisper API (ultra-fast)...")
                return self._transcribe_groq(audio_path, groq_key)
            except Exception as e:
                logger.warning(f"Groq Whisper failed ({e}), falling back to local faster-whisper.")

        # Local fallback
        return self._transcribe_local(audio_path)

    def _transcribe_groq(self, audio_path: str, api_key: str) -> Dict[str, Any]:
        """Use Groq API for rapid transcription with word-level timestamps."""
        from groq import Groq
        client = Groq(api_key=api_key)

        with open(audio_path, "rb") as audio_file:
            # Request verbose_json with word timestamps
            transcription = client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3-turbo",
                response_format="verbose_json",
                timestamp_granularities=["word"]
            )

        words = []
        raw_words = getattr(transcription, "words", []) or []
        for w in raw_words:
            # w can be dict or object
            word_str = w.get("word") if isinstance(w, dict) else getattr(w, "word", "")
            start = w.get("start") if isinstance(w, dict) else getattr(w, "start", 0.0)
            end = w.get("end") if isinstance(w, dict) else getattr(w, "end", 0.0)
            words.append({
                "word": word_str.strip(),
                "start": float(start),
                "end": float(end)
            })

        full_text = getattr(transcription, "text", "") or ""
        return {
            "text": full_text.strip(),
            "words": words,
            "engine": "groq-whisper-turbo",
            "language": getattr(transcription, "language", "en")
        }

    def _transcribe_local(self, audio_path: str) -> Dict[str, Any]:
        """Transcribe locally using faster-whisper with word-level timestamps."""
        model = self._get_local_model()
        logger.info(f"Transcribing {audio_path} locally with faster-whisper...")

        segments, info = model.transcribe(
            str(audio_path),
            word_timestamps=True,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        all_words = []
        text_parts = []

        for seg in segments:
            text_parts.append(seg.text)
            if seg.words:
                for w in seg.words:
                    all_words.append({
                        "word": w.word.strip(),
                        "start": round(w.start, 2),
                        "end": round(w.end, 2),
                        "probability": round(w.probability, 2)
                    })

        return {
            "text": " ".join(text_parts).strip(),
            "words": all_words,
            "engine": f"faster-whisper-{self.model_size}",
            "language": info.language
        }
