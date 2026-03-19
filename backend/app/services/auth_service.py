import hashlib

import httpx

from app.core.config import get_settings


async def exchange_wechat_code_for_openid(code: str) -> str:
    settings = get_settings()
    if settings.WECHAT_APPID and settings.WECHAT_SECRET:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.weixin.qq.com/sns/jscode2session",
                params={
                    "appid": settings.WECHAT_APPID,
                    "secret": settings.WECHAT_SECRET,
                    "js_code": code,
                    "grant_type": "authorization_code",
                },
            )
            data = resp.json()
            openid = data.get("openid")
            if openid:
                return openid

    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()[:24]
    return f"dev_{digest}"
