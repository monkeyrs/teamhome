from __future__ import annotations

import httpx

from app.services.llm.openrouter import get_llm_client


class TranscriptionError(RuntimeError):
    def __init__(self, public_message: str, *, status_code: int = 502) -> None:
        super().__init__(public_message)
        self.status_code = status_code


def transcribe_audio_file(file_path: str) -> str:
    client = get_llm_client()
    if not client:
        raise TranscriptionError("Audio transcription service is unavailable.", status_code=503)

    try:
        text = client.transcribe_audio(file_path=file_path).strip()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 402:
            raise TranscriptionError("Audio transcription quota is unavailable.", status_code=503) from exc
        raise TranscriptionError("Audio transcription request failed.") from exc
    except Exception as exc:
        raise TranscriptionError("Audio transcription failed.") from exc

    if not text:
        raise TranscriptionError("Audio transcription returned an empty result.")
    return text
