from __future__ import annotations

import httpx

from app.services.llm.openrouter import get_llm_client


def transcribe_audio_file(file_path: str) -> str:
    client = get_llm_client()
    if not client:
        raise RuntimeError("Audio transcription service is not configured.")

    try:
        text = client.transcribe_audio(file_path=file_path).strip()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        if exc.response.status_code == 402:
            raise RuntimeError("The current OpenRouter key has no audio transcription quota.") from exc
        raise RuntimeError(f"Audio transcription request failed: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"Audio transcription failed: {exc}") from exc

    if not text:
        raise RuntimeError("Audio transcription returned an empty result.")
    return text
