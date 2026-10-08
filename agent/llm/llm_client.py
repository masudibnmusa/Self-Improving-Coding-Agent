import anthropic


class LLMClient:
    def __init__(self, cfg, cost_tracker):
        self.cfg = cfg
        self.cost = cost_tracker
        self.client = anthropic.Anthropic(api_key=cfg.anthropic_api_key, max_retries=5)

    def create(self, system: str, messages: list, tools: list):
        resp = self.client.messages.create(
            model=self.cfg.model,
            max_tokens=self.cfg.max_output_tokens,
            system=system,
            messages=messages,
            tools=tools,
        )
        self.cost.add(resp.usage)
        return resp