"""Accumulates token usage across LLM calls and converts it to USD using the prices in Config."""

PER_MTOK = 1_000_000


class CostTracker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_write_tokens = 0
        self.cache_read_tokens = 0

    def add(self, usage) -> None:
        """Record one response's `usage` (anthropic Usage object or anything with the same attributes).
        `input_tokens` excludes cached tokens, so the four counts are billed separately."""
        self.calls += 1
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0

    @property
    def total_cost(self) -> float:
        c = self.cfg
        return (
            self.input_tokens * c.price_input_per_mtok
            + self.output_tokens * c.price_output_per_mtok
            + self.cache_write_tokens * c.price_cache_write_per_mtok
            + self.cache_read_tokens * c.price_cache_read_per_mtok
        ) / PER_MTOK

    def summary(self) -> dict:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_cost_usd": round(self.total_cost, 4),
        }
