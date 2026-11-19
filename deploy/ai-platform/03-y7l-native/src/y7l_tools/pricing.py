"""Deterministic LLM model pricing helper for Day-1 Google Sheet FinOps tracking."""

from __future__ import annotations

# USD per 1,000,000 tokens
MODEL_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "yggdrasil-default-llm": (0.27, 1.10),
    "deepseek-chat": (0.27, 1.10),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gemini-2.5-flash": (0.15, 0.60),
    "nvidia/llama-3.1-nemotron-70b-instruct": (0.88, 0.88),
    "text-embedding-3-small": (0.02, 0.00),
    "whisper-1": (0.00, 0.00),
}


def estimate_cost_usd(
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> float:
    """Compute estimated USD cost rounded to 6 decimal places for a single LLM/embedding call."""
    normalized = model.strip().lower()
    if "/" in normalized and normalized not in MODEL_PRICING_PER_1M:
        suffix = normalized.split("/", 1)[1]
        if suffix in MODEL_PRICING_PER_1M:
            normalized = suffix

    in_rate, out_rate = MODEL_PRICING_PER_1M.get(normalized, (0.30, 1.20))
    cost = (max(0, prompt_tokens) * in_rate + max(0, completion_tokens) * out_rate) / 1_000_000.0
    return round(cost, 6)
