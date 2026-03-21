from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings


def _normalize_base_url(base_url: str | None) -> str:
    if not base_url:
        return "https://api.openai.com/v1"
    if base_url.rstrip("/").endswith("/v1"):
        return base_url.rstrip("/")
    return f"{base_url.rstrip('/')}/v1"


@dataclass(frozen=True)
class ChatResult:
    text: str
    raw: dict[str, Any]


class OpenAICompatibleClient:
    def __init__(self) -> None:
        settings = get_settings()
        provider = (settings.LLM_PROVIDER or "").lower()
        if provider != "openai":
            raise RuntimeError("LLM provider is not configured")
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        self.api_key = settings.OPENAI_API_KEY
        self.base_url = _normalize_base_url(settings.OPENAI_BASE_URL)
        self.default_model = settings.OPENAI_MODEL
        self.audio_model = settings.OPENAI_AUDIO_MODEL
        self.site_url = settings.OPENROUTER_SITE_URL
        self.app_name = settings.OPENROUTER_APP_NAME

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if "openrouter.ai" in self.base_url:
            headers["HTTP-Referer"] = self.site_url
            headers["X-Title"] = self.app_name
            headers["X-OpenRouter-Title"] = self.app_name
        return headers

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = 0,
        max_tokens: int | None = None,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        with httpx.Client(timeout=45) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        text = data["choices"][0]["message"]["content"]
        if isinstance(text, list):
            text = "".join(
                part.get("text", "")
                for part in text
                if isinstance(part, dict) and part.get("type") == "text"
            )
        return ChatResult(text=str(text or "").strip(), raw=data)

    def chat_json(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            result = self.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
            )
        except httpx.HTTPStatusError as exc:
            raw_error = exc.response.text.lower()
            if exc.response.status_code != 400 or "developer instruction is not enabled" not in raw_error:
                raise
            result = self.chat(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": f"System instructions:\n{system}\n\nUser request:\n{user}",
                    }
                ],
                temperature=0,
            )
        content = result.text
        try:
            return json.loads(content)
        except Exception:
            pass

        if "{" in content and "}" in content:
            snippet = content[content.find("{") : content.rfind("}") + 1]
            try:
                return json.loads(snippet)
            except Exception:
                return None
        return None

    def transcribe_audio(self, *, file_path: str) -> str:
        _, ext = os.path.splitext(file_path)
        audio_format = (ext or ".mp3").lstrip(".").lower()
        with open(file_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")

        result = self.chat(
            model=self.audio_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Please transcribe this audio file to plain text."},
                        {
                            "type": "input_audio",
                            "inputAudio": {
                                "data": encoded,
                                "format": audio_format,
                            },
                        },
                    ],
                }
            ],
            temperature=0,
        )
        return result.text


def get_llm_client() -> OpenAICompatibleClient | None:
    try:
        return OpenAICompatibleClient()
    except RuntimeError:
        return None
