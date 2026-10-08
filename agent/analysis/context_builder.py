from agent.llm.prompts import ISSUE_TEMPLATE, REPRODUCE_INSTRUCTION, SKIP_REPRO_INSTRUCTION


def truncate(text: str, limit: int) -> str:
    """Keep the head and tail of long output; the middle is usually the least useful part."""
    if len(text) <= limit:
        return text
    head = int(limit * 0.6)
    tail = limit - head
    return f"{text[:head]}\n... [{len(text) - limit} chars truncated] ...\n{text[-tail:]}"


def build_initial_message(issue, repo_map_text: str, cfg) -> str:
    instruction = REPRODUCE_INSTRUCTION if cfg.reproduce_first else SKIP_REPRO_INSTRUCTION
    return ISSUE_TEMPLATE.format(
        issue_text=truncate(issue.to_text(), 8000),
        repo_map=repo_map_text or "(not provided; use the repo_map tool)",
        instruction=instruction,
    )


def compact_history(messages: list, keep_recent: int = 6) -> None:
    """Replace old, bulky tool results with a placeholder (in place). Structure stays valid."""
    cutoff = len(messages) - keep_recent * 2
    for m in messages[1:max(cutoff, 1)]:
        if m["role"] != "user" or not isinstance(m["content"], list):
            continue
        for block in m["content"]:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                content = block.get("content", "")
                if isinstance(content, str) and len(content) > 300:
                    block["content"] = f"[older output omitted: {len(content)} chars]"