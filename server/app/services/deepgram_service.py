"""DeepGram Speech-to-Text and Speaker Diarization service.

Integrates with DeepGram Nova-3 model for pre-recorded audio/video transcription,
speaker diarization, and word/utterance level timestamps.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

DEEPGRAM_API_URL = "https://api.deepgram.com/v1/listen"


@dataclass
class DiarizedUtterance:
    """Represents a spoken segment from a single speaker."""

    speaker_index: int
    speaker_label: str
    start_time_seconds: float
    end_time_seconds: float
    text: str
    confidence: float | None = None


@dataclass
class DeepGramTranscriptionResult:
    """Parsed transcription output containing utterances, duration, and speaker info."""

    duration_seconds: float
    speakers: list[str]  # e.g. ["Speaker 1", "Speaker 2"]
    utterances: list[DiarizedUtterance]
    full_transcript: str
    raw_response: dict[str, Any]


class DeepGramService:
    """Service handling audio transcription requests to DeepGram API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.DEEPGRAM_API_KEY
        if not self.api_key:
            logger.warning("DEEPGRAM_API_KEY is not configured in settings.")

    def _get_headers(self) -> dict[str, str]:
        """Builds HTTP request headers with API authorization token."""
        return {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/octet-stream",
        }

    def _get_query_params(self) -> dict[str, str | bool]:
        """
        Builds DeepGram query parameters enforcing Nova-3, diarization, and utterances.
        """
        return {
            "model": "nova-3",
            "language": "en",
            "diarize": "true",
            "punctuate": "true",
            "smart_format": "true",
            "utterances": "true",
            "paragraphs": "true",
        }

    def parse_response(self, data: dict[str, Any]) -> DeepGramTranscriptionResult:
        """
        Parses DeepGram JSON response into structured transcription entities.

        Converts 0-indexed integer speaker IDs (0, 1, 2) into human-friendly
        labels ('Speaker 1', 'Speaker 2', etc.).
        """
        results = data.get("results", {})
        metadata = data.get("metadata", {})
        duration = float(metadata.get("duration", 0.0))

        channels = results.get("channels", [])
        full_transcript = ""
        if channels and len(channels) > 0:
            alts = channels[0].get("alternatives", [])
            if alts and len(alts) > 0:
                full_transcript = alts[0].get("transcript", "")

        raw_utterances = results.get("utterances", [])
        parsed_utterances: list[DiarizedUtterance] = []
        speaker_indices: set[int] = set()

        if raw_utterances:
            for utt in raw_utterances:
                spk_idx = int(utt.get("speaker", 0))
                speaker_indices.add(spk_idx)
                speaker_label = f"Speaker {spk_idx + 1}"
                start_sec = float(utt.get("start", 0.0))
                end_sec = float(utt.get("end", 0.0))
                text = str(utt.get("transcript", "")).strip()
                conf = (
                    float(utt.get("confidence", 0.0))
                    if utt.get("confidence") is not None
                    else None
                )

                if text:
                    parsed_utterances.append(
                        DiarizedUtterance(
                            speaker_index=spk_idx,
                            speaker_label=speaker_label,
                            start_time_seconds=round(start_sec, 3),
                            end_time_seconds=round(end_sec, 3),
                            text=text,
                            confidence=round(conf, 3) if conf is not None else None,
                        )
                    )
        elif channels and len(channels) > 0:
            alts = channels[0].get("alternatives", [])
            if alts and len(alts) > 0:
                paragraphs_obj = alts[0].get("paragraphs", {})
                paragraphs_list = paragraphs_obj.get("paragraphs", [])
                for p_idx, p in enumerate(paragraphs_list):
                    spk_idx = int(p.get("speaker", 0))
                    speaker_indices.add(spk_idx)
                    speaker_label = f"Speaker {spk_idx + 1}"
                    start_sec = float(p.get("start", 0.0))
                    end_sec = float(p.get("end", 0.0))
                    p_text = " ".join([s.get("text", "") for s in p.get("sentences", [])]).strip()
                    if not p_text:
                        p_text = full_transcript
                    if p_text:
                        parsed_utterances.append(
                            DiarizedUtterance(
                                speaker_index=spk_idx,
                                speaker_label=speaker_label,
                                start_time_seconds=round(start_sec, 3),
                                end_time_seconds=round(end_sec, 3),
                                text=p_text,
                                confidence=None,
                            )
                        )

        if not parsed_utterances and full_transcript:
            speaker_indices.add(0)
            parsed_utterances.append(
                DiarizedUtterance(
                    speaker_index=0,
                    speaker_label="Speaker 1",
                    start_time_seconds=0.0,
                    end_time_seconds=duration if duration > 0 else 1.0,
                    text=full_transcript.strip(),
                    confidence=None,
                )
            )

        sorted_speakers = [f"Speaker {idx + 1}" for idx in sorted(speaker_indices)]
        if not sorted_speakers:
            sorted_speakers = ["Speaker 1"]

        if duration <= 0.0 and parsed_utterances:
            duration = max(u.end_time_seconds for u in parsed_utterances)

        return DeepGramTranscriptionResult(
            duration_seconds=round(duration, 3),
            speakers=sorted_speakers,
            utterances=parsed_utterances,
            full_transcript=full_transcript,
            raw_response=data,
        )

    async def transcribe_file(
        self,
        audio_path: str | Path,
        max_retries: int = 3,
        timeout_seconds: float = 300.0,
    ) -> DeepGramTranscriptionResult:
        """
        Sends audio file to DeepGram API and returns structured transcription result.
        """
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found at path: {path}")

        file_bytes = path.read_bytes()
        return await self.transcribe_bytes(
            audio_bytes=file_bytes,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        )

    async def transcribe_bytes(
        self,
        audio_bytes: bytes,
        max_retries: int = 3,
        timeout_seconds: float = 300.0,
    ) -> DeepGramTranscriptionResult:
        """
        Sends raw audio bytes to DeepGram API with retries.
        """
        if not self.api_key:
            raise RuntimeError("Cannot transcribe: DEEPGRAM_API_KEY is not configured.")

        headers = self._get_headers()
        params = self._get_query_params()

        last_exception: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    "Sending audio payload to DeepGram (attempt %d/%d, size=%d bytes)...",
                    attempt,
                    max_retries,
                    len(audio_bytes),
                )
                async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                    response = await client.post(
                        DEEPGRAM_API_URL,
                        params=params,
                        headers=headers,
                        content=audio_bytes,
                    )

                if response.status_code == 200:
                    data = response.json()
                    logger.info("DeepGram transcription succeeded.")
                    return self.parse_response(data)

                if 400 <= response.status_code < 500:
                    err_text = response.text
                    logger.error(
                        "DeepGram client error (status=%d): %s", response.status_code, err_text
                    )
                    raise RuntimeError(
                        f"DeepGram API rejected request with status {response.status_code}: {err_text}"
                    )

                err_text = response.text
                logger.warning(
                    "DeepGram server error (status=%d, attempt %d/%d): %s",
                    response.status_code,
                    attempt,
                    max_retries,
                    err_text,
                )
                last_exception = RuntimeError(
                    f"DeepGram API error {response.status_code}: {err_text}"
                )

            except httpx.RequestError as exc:
                logger.warning(
                    "Network error connecting to DeepGram (attempt %d/%d): %s",
                    attempt,
                    max_retries,
                    str(exc),
                )
                last_exception = exc

            if attempt < max_retries:
                backoff = 2**attempt
                logger.info("Backing off for %d seconds before retrying DeepGram call...", backoff)
                await asyncio.sleep(backoff)

        raise RuntimeError(
            f"DeepGram transcription failed after {max_retries} attempts: {last_exception}"
        )


deepgram_service = DeepGramService()
