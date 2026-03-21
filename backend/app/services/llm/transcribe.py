from __future__ import annotations

import httpx

from app.services.llm.openrouter import get_llm_client


def transcribe_audio_file(file_path: str) -> str:
    client = get_llm_client()
    if not client:
        raise RuntimeError("未配置语音转写服务")

    try:
        text = client.transcribe_audio(file_path=file_path).strip()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        if exc.response.status_code == 402:
            raise RuntimeError("当前 OpenRouter key 没有可用音频额度，语音识别不可用") from exc
        raise RuntimeError(f"语音转写请求失败: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"语音转写失败: {exc}") from exc

    if not text:
        raise RuntimeError("语音转写结果为空")
    return text
