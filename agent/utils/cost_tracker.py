"""Accumulates token usage across LLM calls and converts it to USD using the prices in Config."""

# Prompt-cache multipliers relative to the base input price.
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.10


class CostTracker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_write_tokens = 0
        self.cache_read_tokens = 0

    def add(self, usage) -> None:
        """Record one response's `usage` (anthropic Usage object or anything with the same attributes)."""
        self.calls += 1
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0

    @property
    def total_cost(self) -> float:
        p_in = self.cfg.price_input_per_mtok / 1_000_000
        p_out = self.cfg.price_output_per_mtok / 1_000_000
        return (
            self.input_tokens * p_in
            + self.cache_write_tokens * p_in * CACHE_WRITE_MULTIPLIER
            + self.cache_read_tokens * p_in * CACHE_READ_MULTIPLIER
            + self.output_tokens * p_out
        )

    def summary(self) -> dict:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_cost_usd": round(self.total_cost, 4),
        }
