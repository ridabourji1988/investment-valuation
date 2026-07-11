"""OpenRouter chat client — GLM 5.2 via the StreamLake provider, with prompt caching.

Prompt caching (PRD cost note): GLM providers cache the prompt prefix
IMPLICITLY — no cache_control markers needed. The large, static methodology
system prompt therefore goes first as a plain string, and per-request data goes
in the *user* message so it never busts the cached prefix. Verified live:
repeat calls bill cached tokens at ~19% of the prompt rate.

Do NOT add Anthropic-style `cache_control` breakpoints here: sending them makes
OpenRouter's routing bypass StreamLake (observed live — requests divert to a
~3x more expensive provider).

Reasoning is disabled: GLM 5.2 is a thinking model, but narration is a
formatting task — with reasoning on, small max_tokens budgets get consumed by
reasoning tokens and the content comes back empty (observed live).
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
        # Prefer StreamLake for the GLM caching discount; allow fallbacks so a
        # provider outage still returns an answer.
        "provider": {"order": [config.OPENROUTER_PROVIDER], "allow_fallbacks": True},
        # Narration doesn't need chain-of-thought; leaving it on empties small
        # completion budgets (reasoning tokens count against max_tokens).
        "reasoning": {"enabled": False},
        "messages": [
            {"role": "system", "content": system_prompt},
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
            text = choice if isinstance(choice, str) else _flatten(choice)
            if not (text or "").strip():
                # Reasoning models can exhaust max_tokens before emitting
                # content; surface as a failure so callers fall back.
                last_err = OpenRouterError("empty completion (reasoning consumed budget?)")
                continue
            usage = data.get("usage", {})
            return {
                "text": text,
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
