from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass

import dateparser
import httpx

from app.core.config import get_settings


_AMOUNT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:元|块|rmb|RMB)?")


def _guess_finance_type(text: str) -> str:
    income_words = ["收入", "收款", "入账", "工资", "奖金", "报销", "到账"]
    expense_words = ["花", "花了", "支出", "付款", "买", "消费", "用了", "扣款"]
    if any(w in text for w in income_words):
        return "income"
    if any(w in text for w in expense_words):
        return "expense"
    return "expense"


def _guess_finance_category(text: str) -> str:
    mapping: list[tuple[str, str]] = [
        ("餐", "food"),
        ("饭", "food"),
        ("奶茶", "food"),
        ("咖啡", "food"),
        ("外卖", "food"),
        ("公交", "transport"),
        ("地铁", "transport"),
        ("打车", "transport"),
        ("出租", "transport"),
        ("油", "transport"),
        ("房租", "rent"),
        ("租金", "rent"),
        ("水电", "utilities"),
        ("电费", "utilities"),
        ("水费", "utilities"),
        ("网费", "utilities"),
        ("话费", "utilities"),
        ("购物", "shopping"),
        ("买", "shopping"),
        ("衣", "shopping"),
        ("鞋", "shopping"),
        ("电影", "entertainment"),
        ("游戏", "entertainment"),
        ("门票", "entertainment"),
        ("工资", "salary"),
        ("奖金", "salary"),
        ("报销", "reimbursement"),
    ]
    for k, v in mapping:
        if k in text:
            return v
    return "other"


def _extract_amount(text: str) -> float | None:
    matches = _AMOUNT_RE.findall(text)
    if not matches:
        return None
    try:
        return float(matches[-1][0])
    except ValueError:
        return None


def _now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def _iso_no_seconds(d: dt.datetime) -> str:
    if d.tzinfo is None:
        return d.replace(second=0, microsecond=0).isoformat()
    return d.replace(second=0, microsecond=0).isoformat()


@dataclass(frozen=True)
class _LLMClient:
    base_url: str
    api_key: str
    model: str

    def chat_json(self, *, system: str, user: str) -> dict | None:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = self.base_url.rstrip("/") + "/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
        }
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return None

        try:
            content = data["choices"][0]["message"]["content"]
        except Exception:
            return None

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


def _get_llm_client() -> _LLMClient | None:
    settings = get_settings()
    if not settings.LLM_PROVIDER:
        return None
    if settings.LLM_PROVIDER.lower() != "openai":
        return None
    if not settings.OPENAI_API_KEY:
        return None
    base_url = settings.OPENAI_BASE_URL or "https://api.openai.com"
    return _LLMClient(base_url=base_url, api_key=settings.OPENAI_API_KEY, model=settings.OPENAI_MODEL)


def parse_finance_text(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {"amount": None, "type": None, "category": None}

    amount = _extract_amount(text)
    record_type = _guess_finance_type(text)
    category = _guess_finance_category(text)

    if amount is not None and amount < 0:
        amount = abs(amount)
        record_type = "expense" if record_type == "income" else "income"

    if amount is not None:
        return {"amount": amount, "type": record_type, "category": category}

    client = _get_llm_client()
    if not client:
        return {"amount": None, "type": record_type, "category": category}

    system = "Extract finance data from user text. Return JSON with fields: amount (number), type (income|expense), category (string)."
    data = client.chat_json(system=system, user=text) or {}
    return {
        "amount": data.get("amount"),
        "type": data.get("type") or record_type,
        "category": data.get("category") or category,
    }


def parse_schedule_text(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {"title": None, "start_time": None, "end_time": None}

    settings = {"RELATIVE_BASE": _now_local(), "PREFER_DATES_FROM": "future"}
    start = dateparser.parse(text, languages=["zh"], settings=settings) or dateparser.parse(text, settings=settings)

    title = text
    if start:
        title = re.sub(r"(今天|明天|后天|下周|周[一二三四五六日天])", "", title)
        title = re.sub(r"(\d{1,2}点(?:半)?|\d{1,2}:\d{2})", "", title)
        title = re.sub(r"(上午|下午|晚上|中午|凌晨)", "", title)
        title = re.sub(r"[，,。\\.\\s]+", " ", title).strip()

    end: dt.datetime | None = None
    duration = re.search(r"(\d+(?:\.\d+)?)\s*(小时|h|H|分钟|min|MIN)", text)
    if start and duration:
        value = float(duration.group(1))
        unit = duration.group(2).lower()
        if "小时" in unit or unit == "h":
            end = start + dt.timedelta(hours=value)
        else:
            end = start + dt.timedelta(minutes=value)

    if not title:
        title = "日程"

    return {
        "title": title,
        "start_time": _iso_no_seconds(start) if start else None,
        "end_time": _iso_no_seconds(end) if end else None,
    }
