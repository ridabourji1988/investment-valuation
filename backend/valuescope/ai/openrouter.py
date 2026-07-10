"""OpenRouter chat client — GLM via the Streamlake provider, with prompt caching.

Prompt caching (PRD cost note): the large, static methodology/system prompt is
sent as a single cached breakpoint (`cache_control: ephemeral`). OpenRouter
forwards the breakpoint to providers that support caching (Streamlake for GLM),
so repeated calls reuse the cached prefix at the discounted rate. Per-request
data goes in the *user* message so it never busts the cached prefix.
"""
from __future__ import annotations

import httpx

from ..config import config


class OpenRouterError(RuntimeError):
    pass


def _api_keys() -> list[str]:
    raw = config.OPENROUTER_API_KEY or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


def build_payload(system_prompt: str, user_prompt: str, *, temperature: float = 0.3,
                  max_tokens: int = 800) -> dict:
    """Construct the request body with a cached system prefix and provider routing."""
    return {
        "model": config.OPENROUTER_MODEL,
        # Prefer Streamlake for the GLM caching discount; allow fallbacks so a
        # provider outage still returns an answer.
        "provider": {"order": [config.OPENROUTER_PROVIDER], "allow_fallbacks": True},
        "messages": [
            {
                "role": "system",
                "content": [
                    {"type": "text", "text": system_prompt,
                     "cache_control": {"type": "ephemeral"}},
                ],
            },
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "usage": {"include": True},
    }


def chat(system_prompt: str, user_prompt: str, *, temperature: float = 0.3,
         max_tokens: int = 800, timeout: float = 45.0) -> dict:
    """Call OpenRouter. Returns {text, usage, model, provider}. Raises on failure."""
    keys = _api_keys()
    if not keys:
        raise OpenRouterError("no OpenRouter API key configured")

    payload = build_payload(system_prompt, user_prompt, temperature=temperature,
                            max_tokens=max_tokens)
    last_err: Exception | None = None
    for key in keys:
        headers = {
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": "https://valuescope.app",
            "X-Title": "ValueScope",
            "Content-Type": "application/json",
        }
        try:
            r = httpx.post(f"{config.OPENROUTER_BASE_URL}/chat/completions",
                           json=payload, headers=headers, timeout=timeout)
            if r.status_code == 401:
                last_err = OpenRouterError("401 unauthorized")
                continue  # try next key
            r.raise_for_status()
            data = r.json()
            choice = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return {
                "text": choice if isinstance(choice, str) else _flatten(choice),
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
                    "cost": usage.get("cost"),
                },
                "model": data.get("model"),
                "provider": data.get("provider"),
            }
        except Exception as e:  # noqa: BLE001 — try next key, then surface
            last_err = e
            continue
    raise OpenRouterError(f"all OpenRouter attempts failed: {last_err}")


def _flatten(content) -> str:
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content)
