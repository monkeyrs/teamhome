from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.llm.model_fallbacks import build_chat_candidates, parse_fallback_models


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
    model: str | None = None


_RETRYABLE_HTTP_STATUS = {402, 408, 409, 425, 429, 500, 502, 503, 504}
_RETRYABLE_ERROR_TOKENS = {
    "insufficient_quota",
    "quota",
    "rate limit",
    "rate_limit",
    "model_not_found",
    "model is overloaded",
    "temporarily unavailable",
    "capacity",
    "timeout",
}


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
        self.ssl_verify = settings.OPENAI_SSL_VERIFY
        self.auto_switch_models = bool(settings.OPENAI_AUTO_SWITCH_MODELS)
        self.max_model_attempts = max(int(settings.OPENAI_MODEL_MAX_ATTEMPTS), 1)
        self.model_fallbacks = parse_fallback_models(settings.OPENAI_MODEL_FALLBACKS)
        self.site_url = settings.OPENROUTER_SITE_URL
        self.app_name = settings.OPENROUTER_APP_NAME

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        if "openrouter.ai" in self.base_url:
            headers["HTTP-Referer"] = self.site_url
            headers["X-Title"] = self.app_name
            headers["X-OpenRouter-Title"] = self.app_name
        return headers

    @staticmethod
    def _is_retryable_http_error(exc: httpx.HTTPStatusError) -> bool:
        status = exc.response.status_code
        body = (exc.response.text or "").lower()
        if status in _RETRYABLE_HTTP_STATUS:
            return True
        return any(token in body for token in _RETRYABLE_ERROR_TOKENS)

    @staticmethod
    def _is_retryable_transport_error(exc: Exception) -> bool:
        return isinstance(
            exc,
            (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.WriteTimeout,
                httpx.RemoteProtocolError,
            ),
        )

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = 0,
        max_tokens: int | None = None,
        allow_auto_switch: bool = True,
    ) -> ChatResult:
        candidates: list[str]
        if allow_auto_switch and self.auto_switch_models:
            candidates = build_chat_candidates(model or self.default_model, self.model_fallbacks)
        else:
            candidates = [model or self.default_model]
        if not candidates:
            raise RuntimeError("No model candidates available")

        payload: dict[str, Any] = {"messages": messages}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        last_error: Exception | None = None
        attempt_limit = min(self.max_model_attempts, len(candidates))
        with httpx.Client(timeout=45, verify=self.ssl_verify) as client:
            for idx, candidate in enumerate(candidates[:attempt_limit]):
                payload["model"] = candidate
                try:
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
                    return ChatResult(text=str(text or "").strip(), raw=data, model=candidate)
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    can_retry = self._is_retryable_http_error(exc) and idx + 1 < attempt_limit
                    if not can_retry:
                        raise
                except Exception as exc:
                    last_error = exc
                    can_retry = self._is_retryable_transport_error(exc) and idx + 1 < attempt_limit
                    if not can_retry:
                        raise

        if last_error:
            raise last_error
        raise RuntimeError("LLM call failed without explicit exception")

    def chat_json(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int | None = None,
        allow_auto_switch: bool = True,
    ) -> dict[str, Any] | None:
        try:
            result = self.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                max_tokens=max_tokens,
                allow_auto_switch=allow_auto_switch,
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
                max_tokens=max_tokens,
                allow_auto_switch=allow_auto_switch,
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
            allow_auto_switch=False,
        )
        return result.text


def get_llm_client() -> OpenAICompatibleClient | None:
    try:
        return OpenAICompatibleClient()
    except RuntimeError:
        return None
