from __future__ import annotations


_AVAILABLE_MODELS_TEXT = """
deepseek-r1
deepseek-r1-0528
deepseek-r1-distill-llama-70b
deepseek-r1-distill-qwen-14b
deepseek-r1-distill-qwen-32b
deepseek-r1-distill-qwen-7b
deepseek-v3
deepseek-v3.1
deepseek-v3.2
deepseek-v3.2-exp
glm-4.5
glm-4.5-air
glm-4.6
glm-4.7
glm-5
gui-plus
kimi-k2.5
kimi-k2-thinking
llama-4-maverick-17b-128e-instruct
llama-4-scout-17b-16e-instruct
MiniMax-M2.1
MiniMax-M2.5
Moonshot-Kimi-K2-Instruct
opennlu-v1
qvq-72b-preview
qvq-max
qvq-max-2025-03-25
qvq-max-2025-05-15
qvq-max-latest
qvq-plus
qvq-plus-2025-05-15
qvq-plus-latest
qwen1.5-110b-chat
qwen1.5-14b-chat
qwen1.5-32b-chat
qwen1.5-72b-chat
qwen1.5-7b-chat
qwen2.5-0.5b-instruct
qwen2.5-1.5b-instruct
qwen2.5-14b-instruct
qwen2.5-14b-instruct-1m
qwen2.5-32b-instruct
qwen2.5-3b-instruct
qwen2.5-72b-instruct
qwen2.5-7b-instruct
qwen2.5-7b-instruct-1m
qwen2.5-coder-14b-instruct
qwen2.5-coder-32b-instruct
qwen2.5-coder-7b-instruct
qwen2.5-math-72b-instruct
qwen2.5-math-7b-instruct
qwen2.5-vl-32b-instruct
qwen2.5-vl-3b-instruct
qwen2.5-vl-72b-instruct
qwen2.5-vl-7b-instruct
qwen2-57b-a14b-instruct
qwen2-72b-instruct
qwen2-7b-instruct
qwen2-vl-2b-instruct
qwen2-vl-72b-instruct
qwen2-vl-7b-instruct
qwen3.5-122b-a10b
qwen3.5-27b
qwen3.5-397b-a17b
qwen3.5-flash
qwen3.5-flash-2026-02-23
qwen3.5-plus
qwen3.5-plus-2026-02-15
qwen3-0.6b
qwen3-1.7b
qwen3-14b
qwen3-235b-a22b
qwen3-235b-a22b-instruct-2507
qwen3-235b-a22b-thinking-2507
qwen3-30b-a3b
qwen3-30b-a3b-instruct-2507
qwen3-30b-a3b-thinking-2507
qwen3-32b
qwen3-4b
qwen3-8b
qwen3-coder-30b-a3b-instruct
qwen3-coder-480b-a35b-instruct
qwen3-coder-flash
qwen3-coder-flash-2025-07-28
qwen3-coder-next
qwen3-coder-plus
qwen3-coder-plus-2025-07-22
qwen3-coder-plus-2025-09-23
qwen3-max
qwen3-max-2025-09-23
qwen3-max-2026-01-23
qwen3-max-preview
qwen3-next-80b-a3b-instruct
qwen3-next-80b-a3b-thinking
qwen3-vl-235b-a22b-instruct
qwen3-vl-235b-a22b-thinking
qwen3-vl-30b-a3b-instruct
qwen3-vl-30b-a3b-thinking
qwen3-vl-8b-instruct
qwen3-vl-8b-thinking
qwen3-vl-flash
qwen3-vl-flash-2025-10-15
qwen3-vl-flash-2026-01-22
qwen3-vl-plus
qwen3-vl-plus-2025-09-23
qwen3-vl-plus-2025-12-19
qwen-coder-plus
qwen-coder-plus-1106
qwen-coder-plus-latest
qwen-coder-turbo
qwen-coder-turbo-0919
qwen-coder-turbo-latest
qwen-flash
qwen-flash-2025-07-28
qwen-flash-character
qwen-flash-character-2026-02-26
qwen-long
qwen-long-2025-01-25
qwen-long-latest
qwen-math-plus
qwen-math-plus-0816
qwen-math-plus-0919
qwen-math-plus-latest
qwen-math-turbo
qwen-math-turbo-0919
qwen-math-turbo-latest
qwen-max
qwen-max-0428
qwen-max-0919
qwen-max-2025-01-25
qwen-max-latest
qwen-mt-flash
qwen-mt-lite
qwen-mt-plus
qwen-mt-turbo
qwen-plus
qwen-plus-0112
qwen-plus-1220
qwen-plus-2025-01-25
qwen-plus-2025-04-28
qwen-plus-2025-07-14
qwen-plus-2025-07-28
qwen-plus-2025-09-11
qwen-plus-2025-12-01
qwen-plus-character
qwen-plus-latest
qwen-turbo
qwen-turbo-1101
qwen-turbo-2025-02-11
qwen-turbo-2025-04-28
qwen-turbo-2025-07-15
qwen-turbo-latest
qwen-vl-max
qwen-vl-max-1119
qwen-vl-max-1230
qwen-vl-max-2025-01-25
qwen-vl-max-2025-04-02
qwen-vl-max-2025-04-08
qwen-vl-max-2025-08-13
qwen-vl-max-latest
qwen-vl-ocr
qwen-vl-ocr-1028
qwen-vl-ocr-2025-04-13
qwen-vl-ocr-2025-08-28
qwen-vl-ocr-2025-11-20
qwen-vl-ocr-latest
qwen-vl-plus
qwen-vl-plus-0102
qwen-vl-plus-2025-01-25
qwen-vl-plus-2025-05-07
qwen-vl-plus-2025-08-15
qwen-vl-plus-latest
qwq-32b
qwq-32b-preview
qwq-plus
qwq-plus-2025-03-05
qwq-plus-latest
tongyi-intent-detect-v3
tongyi-xiaomi-analysis-flash
tongyi-xiaomi-analysis-pro
"""

AVAILABLE_MODELS: tuple[str, ...] = tuple(
    line.strip() for line in _AVAILABLE_MODELS_TEXT.splitlines() if line.strip()
)

# Prioritize balanced chat models for assistant orchestration.
DEFAULT_CHAT_FALLBACKS: tuple[str, ...] = (
    "qwen-plus-latest",
    "qwen-plus",
    "qwen-turbo-latest",
    "qwen-turbo",
    "deepseek-v3.2",
    "deepseek-v3.1",
    "glm-5",
    "qwen3.5-plus",
)


def parse_fallback_models(raw: str | None) -> list[str]:
    if not raw:
        return []
    models = [item.strip() for item in raw.split(",")]
    return [item for item in models if item]


def build_chat_candidates(primary_model: str, configured_fallbacks: list[str] | None = None) -> list[str]:
    ordered: list[str] = []

    def _append(model: str) -> None:
        text = (model or "").strip()
        if not text or text in ordered:
            return
        ordered.append(text)

    _append(primary_model)
    for model in configured_fallbacks or []:
        _append(model)
    for model in DEFAULT_CHAT_FALLBACKS:
        _append(model)
    for model in AVAILABLE_MODELS:
        _append(model)
    return ordered
