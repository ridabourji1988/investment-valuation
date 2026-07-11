from valuescope.ai.guardrails import collect_numbers, validate_numbers
from valuescope.ai.openrouter import build_payload


def test_guardrail_accepts_numbers_from_payload_strings():
    # Numbers embedded in engine strings (e.g. the sizing line) are legitimate.
    payload = {"sizing": "≈ 15% of a 10 000 US$ portfolio (~1,500 US$); hold 5-10 positions."}
    nums = collect_numbers(payload)
    assert 1500.0 in nums and 15.0 in nums
    r = validate_numbers("Suggested position is about 1,500 US$ (15% of the portfolio).", payload)
    assert r["ok"], r


def test_guardrail_accepts_magnitude_restatements():
    # 281,700,000,000 narrated as "281.7 billion" must validate.
    payload = {"revenue_ttm_usd": 281_700_000_000}
    r = validate_numbers("The company makes about $281.7 billion in revenue.", payload)
    assert r["ok"], r


def test_guardrail_rejects_invented_numbers():
    payload = {"price": 88.0, "fair_value": 186.2}
    r = validate_numbers("The stock will hit 204.82 US$ soon.", payload)
    assert not r["ok"]
    assert "204.82" in " ".join(r["unverified"])


def test_guardrail_rejects_jargon():
    payload = {"price": 88.0}
    r = validate_numbers("The idiosyncratic risk profile is at 88.0.", payload)
    assert not r["ok"] and r["jargon"]


def test_payload_plain_system_prompt_no_cache_control():
    """Anthropic-style cache_control breakpoints divert OpenRouter routing away
    from StreamLake (observed live) — GLM caches implicitly. Keep the system
    message a plain string."""
    p = build_payload("SYSTEM", "USER")
    assert p["messages"][0] == {"role": "system", "content": "SYSTEM"}
    assert "cache_control" not in str(p["messages"])


def test_payload_reasoning_disabled():
    """GLM 5.2 is a thinking model; with reasoning on, small max_tokens budgets
    return empty content (observed live)."""
    p = build_payload("SYSTEM", "USER")
    assert p["reasoning"] == {"enabled": False}


def test_payload_provider_order_uses_config_slug():
    p = build_payload("SYSTEM", "USER")
    assert p["provider"]["order"] and isinstance(p["provider"]["order"][0], str)
    assert p["provider"]["allow_fallbacks"] is True
