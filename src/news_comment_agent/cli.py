from __future__ import annotations

import argparse
import sys

from .backends import RuntimeSettings
from .config import DEFAULT_CONFIG_PATH, load_app_config
from .ingestion import fetch_url_as_text
from .pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate one comment from a news URL")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to runtime JSON config file")
    parser.add_argument("--url", required=True, help="Fetch and analyze a URL directly")
    parser.add_argument("--backend", choices=["heuristic", "openai"], help="Inference backend")
    parser.add_argument("--model", help="Model name for the OpenAI backend")
    parser.add_argument("--api-base", help="Responses or chat completions API endpoint")
    parser.add_argument("--api-mode", choices=["responses", "chat"], help="Force API wire format for model requests")
    parser.add_argument("--proxy", help="Optional HTTP/HTTPS proxy URL for OpenAI requests, e.g. http://127.0.0.1:PORT")
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args()
    app_config = load_app_config(args.config)

    _log_progress(f"Fetching URL: {args.url}")
    news_input = fetch_url_as_text(args.url)

    settings = RuntimeSettings.from_args(
        backend_name=args.backend or app_config.backend,
        model=args.model or app_config.model,
        api_base=args.api_base or app_config.api_base,
        proxy_url=args.proxy or app_config.proxy,
        api_mode=args.api_mode or app_config.api_mode,
        api_key=app_config.api_key,
    )
    _log_progress(
        f"Starting pipeline with backend={settings.backend_name}"
        + (f", model={settings.model}" if settings.backend_name == "openai" else "")
    )
    result = run_pipeline(news_input, settings=settings, config_path=args.config)
    print(result.best_comment.body)
    return 0


def _log_progress(message: str) -> None:
    print(f"[progress] {message}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
