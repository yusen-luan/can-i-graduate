"""Thin Claude API wrapper shared by the LLM pipelines (evaluation_plan.md §3-§4).

One entry point, `call()`, so every pipeline sends requests the same way:
adaptive thinking at ONE fixed effort for all models (defaults differ per model,
which would confound the size ablation), a prompt-cached system prompt, JSON
structured output, and streaming (long thinking would otherwise risk HTTP
timeouts). Returns the raw text plus usage / latency / $ so runs are auditable.

The API key is read from `.env` at the repo root (ANTHROPIC_API_KEY=...).
"""
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Size ablation: one generation (5.5) so only model size varies.
MODELS = {
    "haiku": "claude-haiku-5-5",
    "sonnet": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
}
DEFAULT_EFFORT = "high"

# USD per 1M tokens (Anthropic first-party list prices, 2026-10). Cache writes
# (5-min TTL) bill at 1.25x input. Haiku 5.5 prices apply to prompts <= 100K.
PRICES = {
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_read": 0.01},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_read": 0.20},
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20},
}


@dataclass
class LLMResult:
    model: str
    text: str
    stop_reason: str
    latency_s: float
    cost_usd: float
    request_id: str
    usage: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def get_client():
    """Anthropic client with the key from `.env` (environment wins if already set)."""
    import anthropic
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY not set: copy .env.example to .env and fill it in.")
    return anthropic.Anthropic(max_retries=4)


def cost_usd(model_id, usage):
    p = PRICES[model_id]
    return round((usage.get("input_tokens", 0) * p["input"]
                  + usage.get("cache_creation_input_tokens", 0) * p["input"] * 1.25
                  + usage.get("cache_read_input_tokens", 0) * p["cache_read"]
                  + usage.get("output_tokens", 0) * p["output"]) / 1e6, 6)


def _request(model_id, system, user, schema, effort, max_tokens):
    return dict(
        model=model_id,
        max_tokens=max_tokens,
        # static rules + catalog: identical across instances -> cached prefix
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        thinking={"type": "adaptive"},
        output_config={"effort": effort,
                       "format": {"type": "json_schema", "schema": schema}},
    )


def count_tokens(client, model_key, system, user, schema, effort=DEFAULT_EFFORT):
    """Input-token count for one request (free; used by --dry-run)."""
    req = _request(MODELS[model_key], system, user, schema, effort, 1)
    req.pop("max_tokens")
    return client.messages.count_tokens(**req).input_tokens


def call(client, model_key, system, user, schema, effort=DEFAULT_EFFORT,
         max_tokens=64000) -> LLMResult:
    model_id = MODELS[model_key]
    t0 = time.perf_counter()
    with client.messages.stream(**_request(model_id, system, user, schema,
                                           effort, max_tokens)) as stream:
        msg = stream.get_final_message()
    latency = time.perf_counter() - t0
    u = msg.usage
    usage = {k: getattr(u, k, 0) or 0 for k in
             ("input_tokens", "output_tokens", "cache_creation_input_tokens",
              "cache_read_input_tokens")}
    text = "".join(b.text for b in msg.content if b.type == "text")
    return LLMResult(model=model_id, text=text, stop_reason=msg.stop_reason,
                     latency_s=round(latency, 2), cost_usd=cost_usd(model_id, usage),
                     request_id=getattr(msg, "_request_id", "") or "", usage=usage)
