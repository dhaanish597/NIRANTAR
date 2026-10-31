"""Sarvam Bulbul v4-flash (<250ms) and Bulbul v3 fallback vernacular CAP audio alert synthesis."""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
import json
import struct
import time
from typing import Any
from urllib import request

from app.config import Settings


BULBUL_V4_FLASH_LANGUAGES: frozenset[str] = frozenset(
    {"en-IN", "hi-IN", "bn-IN", "ta-IN", "te-IN", "kn-IN", "mr-IN", "gu-IN"}
)
BULBUL_V3_FALLBACK_LANGUAGES: frozenset[str] = frozenset({"ml-IN", "od-IN", "pa-IN", "as-IN"})


@dataclass
class BulbulTtsResult:
    language_code: str
    model_used: str
    fallback_triggered: bool
    speaker_voice: str
    latency_ms: float
    audio_base64: str
    text_synthesized: str
    source_mode: str = "deterministic_offline"

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


class SarvamBulbulTtsService:
    """Synthesizes vernacular disaster alerts via Sarvam AI Bulbul TTS with deterministic offline fallback."""

    SARVAM_TTS_ENDPOINT = "https://api.sarvam.ai/text-to-speech"
    SPEAKER_BY_LANGUAGE: dict[str, str] = {
        "ta-IN": "anushka",
        "hi-IN": "abhilash",
        "ml-IN": "arya",
        "bn-IN": "anushka",
        "te-IN": "manisha",
        "kn-IN": "vidya",
        "en-IN": "anushka",
    }

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def select_model_for_language(self, language_code: str) -> tuple[str, bool]:
        normalized = str(language_code).strip()
        if normalized in BULBUL_V4_FLASH_LANGUAGES:
            return self.settings.sarvam_tts_flash_model, False
        if normalized in BULBUL_V3_FALLBACK_LANGUAGES:
            return self.settings.sarvam_tts_fallback_model, True
        return self.settings.sarvam_tts_flash_model, False

    def synthesize_alert(
        self,
        text: str,
        language_code: str = "ta-IN",
        speaker: str | None = None,
        prefer_live_api: bool = False,
    ) -> BulbulTtsResult:
        t0 = time.perf_counter()
        clean_text = str(text).strip()
        if not clean_text:
            raise ValueError("TTS alert text must not be empty")

        model_used, fallback_triggered = self.select_model_for_language(language_code)
        speaker_voice = speaker or self.SPEAKER_BY_LANGUAGE.get(language_code, "anushka")

        if prefer_live_api and self.settings.sarvam_api_key:
            live_audio = self._try_live_sarvam_tts(clean_text, language_code, speaker_voice, model_used)
            if live_audio:
                latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
                return BulbulTtsResult(
                    language_code=language_code,
                    model_used=model_used,
                    fallback_triggered=fallback_triggered,
                    speaker_voice=speaker_voice,
                    latency_ms=latency_ms,
                    audio_base64=live_audio,
                    text_synthesized=clean_text,
                    source_mode="live_sarvam_api",
                )

        wav_bytes = self._build_pcm16_alert_wav(clean_text, sample_rate=8000)
        audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return BulbulTtsResult(
            language_code=language_code,
            model_used=model_used,
            fallback_triggered=fallback_triggered,
            speaker_voice=speaker_voice,
            latency_ms=latency_ms,
            audio_base64=audio_b64,
            text_synthesized=clean_text,
            source_mode="deterministic_offline",
        )

    def _try_live_sarvam_tts(
        self,
        text: str,
        language_code: str,
        speaker: str,
        preferred_model: str,
    ) -> str | None:
        candidate_models = [preferred_model, "bulbul:v3", "bulbul:v2"]
        for model_tag in dict.fromkeys(candidate_models):
            try:
                payload = json.dumps(
                    {
                        "inputs": [text[:500]],
                        "target_language_code": language_code,
                        "speaker": speaker,
                        "pitch": 0,
                        "pace": 1.05,
                        "loudness": 1.5,
                        "speech_sample_rate": 8000,
                        "enable_preprocessing": True,
                        "model": model_tag,
                    }
                ).encode("utf-8")
                req = request.Request(
                    self.SARVAM_TTS_ENDPOINT,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "api-subscription-key": self.settings.sarvam_api_key,
                    },
                    method="POST",
                )
                with request.urlopen(req, timeout=6.0) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    audios = body.get("audios") or []
                    if audios and isinstance(audios[0], str) and audios[0]:
                        return audios[0]
            except Exception:
                continue
        return None

    @staticmethod
    def _build_pcm16_alert_wav(text: str, sample_rate: int = 8000) -> bytes:
        num_samples = max(400, min(2400, len(text) * 16))
        data_size = num_samples * 2
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            36 + data_size,
            b"WAVE",
            b"fmt ",
            16,
            1,
            1,
            sample_rate,
            sample_rate * 2,
            2,
            16,
            b"data",
            data_size,
        )
        seed_val = sum(ord(ch) for ch in text) % 251 + 1
        samples = [((idx * seed_val) % 4000) - 2000 for idx in range(num_samples)]
        pcm_payload = struct.pack(f"<{num_samples}h", *samples)
        return header + pcm_payload
