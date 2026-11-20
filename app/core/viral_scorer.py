import json
import logging
from typing import Dict, Any, List, Optional
from app.config import get_api_keys

logger = logging.getLogger("clipstream.viral_scorer")

PROMPT_TEMPLATE = """You are a world-class viral video editor specializing in YouTube Shorts and TikTok content that garners millions of views.
Analyze the following transcript and metrics from a candidate video clip and evaluate its viral potential.

---
CLIP METRICS:
Duration: {duration} seconds
Spike Category: {tag}
Chat Excitement Score: {hype_score}

TRANSCRIPT:
"{transcript}"
---

Provide a structured JSON response with the following exact keys:
{{
  "virality_score": <integer from 0 to 100 representing how viral this clip will be>,
  "hook_score": <integer from 0 to 10 evaluating the first 3 seconds>,
  "hook_analysis": "<1 sentence explanation of why the hook works or how to improve it>",
  "viral_reason": "<1-2 sentences on why viewers will share and watch until the end>",
  "viral_titles": [
    "<High-CTR Title 1 (curiosity gap or high emotion)>",
    "<High-CTR Title 2 (dramatic or funny)>",
    "<High-CTR Title 3 (shock or question)>"
  ],
  "suggested_caption": "<A compelling 1-line caption for on-screen or description>",
  "tags": ["#shorts", "#viral", "#trending", "<2 relevant niche hashtags>"]
}}

Respond ONLY with valid JSON.
"""

class ViralScorer:
    def __init__(self):
        pass

    def evaluate_clip(
        self,
        transcript: str,
        duration: float,
        tag: str = "hype",
        hype_score: float = 10.0
    ) -> Dict[str, Any]:
        """
        Evaluate viral potential using Google Gemini API, Groq API, or Local Heuristic fallback.
        """
        keys = get_api_keys()
        gemini_key = keys.get("gemini_api_key", "").strip()
        groq_key = keys.get("groq_api_key", "").strip()

        # 1. Try Google Gemini API
        if gemini_key:
            try:
                logger.info("Evaluating virality with Google Gemini API...")
                return self._evaluate_gemini(gemini_key, transcript, duration, tag, hype_score)
            except Exception as e:
                logger.warning(f"Gemini evaluation failed: {e}. Falling back...")

        # 2. Try Groq API
        if groq_key:
            try:
                logger.info("Evaluating virality with Groq API (Llama 3)...")
                return self._evaluate_groq(groq_key, transcript, duration, tag, hype_score)
            except Exception as e:
                logger.warning(f"Groq evaluation failed: {e}. Falling back...")

        # 3. Rule-based Heuristic Fallback
        return self._evaluate_heuristic(transcript, duration, tag, hype_score)

    def _evaluate_gemini(
        self,
        api_key: str,
        transcript: str,
        duration: float,
        tag: str,
        hype_score: float
    ) -> Dict[str, Any]:
        """Use Google GenAI SDK for virality assessment."""
        from google import genai
        client = genai.Client(api_key=api_key)

        prompt = PROMPT_TEMPLATE.format(
            duration=round(duration, 1),
            tag=tag,
            hype_score=round(hype_score, 1),
            transcript=transcript or "[No speech detected - pure visual/gameplay action]"
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        raw_text = response.text.strip()
        return self._parse_json(raw_text)

    def _evaluate_groq(
        self,
        api_key: str,
        transcript: str,
        duration: float,
        tag: str,
        hype_score: float
    ) -> Dict[str, Any]:
        """Use Groq API (Llama 3) for virality assessment."""
        from groq import Groq
        client = Groq(api_key=api_key)

        prompt = PROMPT_TEMPLATE.format(
            duration=round(duration, 1),
            tag=tag,
            hype_score=round(hype_score, 1),
            transcript=transcript or "[No speech detected - pure visual/gameplay action]"
        )

        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a master viral YouTube Shorts editor. Output only JSON."},
                {"role": "user", "content": prompt}
            ],
            model="openai/gpt-oss-120b",
            temperature=0.7,
            response_format={"type": "json_object"}
        )

        raw_text = chat_completion.choices[0].message.content.strip()
        return self._parse_json(raw_text)

    def _evaluate_heuristic(
        self,
        transcript: str,
        duration: float,
        tag: str,
        hype_score: float
    ) -> Dict[str, Any]:
        """Heuristic evaluation when no external API key is configured."""
        base_score = 70
        if hype_score > 30:
            base_score += 18
        elif hype_score > 15:
            base_score += 10

        if 25 <= duration <= 45:
            base_score += 7 # Ideal Shorts sweetspot

        virality_score = min(98, base_score)

        title_presets = {
            "funny": [
                "I CAN'T STOP LAUGHING AT THIS 😂",
                "Wait for what happened next... 💀",
                "Bro thought he got away with it 🤣"
            ],
            "hype": [
                "THE GREATEST MOMENT EVER SEEN 🔥",
                "He actually pulled this off?! 🏆",
                "Nobody expected this to happen! 😱"
            ],
            "shock": [
                "WHAT JUST HAPPENED?! 🤯",
                "This cannot be real... 👀",
                "I have never seen anything like this 🛑"
            ]
        }
        titles = title_presets.get(tag, title_presets["hype"])

        return {
            "virality_score": virality_score,
            "hook_score": 8,
            "hook_analysis": "Strong energetic opening backed by immediate activity spike.",
            "viral_reason": f"High {tag} intensity with rapid pace that maintains viewer engagement.",
            "viral_titles": titles,
            "suggested_caption": titles[0],
            "tags": ["#shorts", "#viral", "#trending", f"#{tag}"]
        }

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """Clean markdown markers and parse JSON safely."""
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except Exception:
            return self._evaluate_heuristic("", 30, "hype", 20.0)
