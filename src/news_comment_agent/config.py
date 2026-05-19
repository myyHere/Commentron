from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = "agent_config.json"
EXAMPLE_CONFIG_PATH = "agent_config.example.json"


@dataclass
class AppConfig:
    backend: str = "heuristic"
    model: str = "gpt-4.1-mini"
    api_base: str = "https://api.openai.com/v1/responses"
    api_mode: str | None = None
    api_key: str | None = None
    proxy: str | None = None
    reddit_user_agent: str | None = None
    reddit_search_limit: int = 6
    reddit_comment_limit: int = 6


def load_app_config(path: str | None = None) -> AppConfig:
    requested_path = Path(path or DEFAULT_CONFIG_PATH)
    config_path = requested_path
    if not config_path.exists() and requested_path.name == DEFAULT_CONFIG_PATH:
        example_path = requested_path.with_name(EXAMPLE_CONFIG_PATH)
        if example_path.exists():
            config_path = example_path

    if not config_path.exists():
        return AppConfig()

    data = json.loads(config_path.read_text(encoding="utf-8"))
    runtime = data.get("runtime", data)
    reddit = data.get("reddit", {})
    return AppConfig(
        backend=_string_value(runtime.get("backend"), "heuristic"),
        model=_string_value(runtime.get("model"), "gpt-4.1-mini"),
        api_base=_string_value(runtime.get("api_base"), "https://api.openai.com/v1/responses"),
        api_mode=_optional_string(runtime.get("api_mode")),
        api_key=_optional_string(runtime.get("api_key")),
        proxy=_optional_string(runtime.get("proxy")),
        reddit_user_agent=_optional_string(reddit.get("user_agent")),
        reddit_search_limit=_int_value(reddit.get("search_limit"), 6),
        reddit_comment_limit=_int_value(reddit.get("comment_limit"), 6),
    )


def _string_value(value: Any, default: str) -> str:
    if value is None:
        return default
    return str(value)


def _optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _int_value(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
