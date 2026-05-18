from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .backends import RuntimeSettings
from .config import DEFAULT_CONFIG_PATH, load_app_config
from .ingestion import fetch_url_as_text, load_json_file, load_sample, load_text_file
from .pipeline import run_pipeline
from .reporting import write_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="News comment agent prototype CLI")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to runtime JSON config file")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sample", help="Load a packaged sample input by name")
    group.add_argument("--input-file", help="Load a JSON file that matches the NewsInput schema")
    group.add_argument("--text-file", help="Load plain text or markdown copied from a page")
    group.add_argument("--url", help="Fetch and analyze a URL directly")
    parser.add_argument("--title", help="Optional title to use with --text-file")
    parser.add_argument("--source-url", help="Optional original URL to record with --text-file")
    parser.add_argument("--allow-sample-fallback", action="store_true", help="Allow known demo URLs to fall back to bundled sample data when fetching fails")
    parser.add_argument("--output-dir", help="Directory for JSON and Markdown outputs")
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

    if args.sample:
        news_input = load_sample(args.sample)
    elif args.input_file:
        news_input = load_json_file(args.input_file)
    elif args.text_file:
        news_input = load_text_file(args.text_file, title=args.title, source_url=args.source_url)
    else:
        news_input = fetch_url_as_text(args.url, allow_sample_fallback=args.allow_sample_fallback)

    settings = RuntimeSettings.from_args(
        backend_name=args.backend or app_config.backend,
        model=args.model or app_config.model,
        api_base=args.api_base or app_config.api_base,
        proxy_url=args.proxy or app_config.proxy,
        api_mode=args.api_mode or app_config.api_mode,
        api_key=app_config.api_key,
    )
    result = run_pipeline(news_input, settings=settings)
    output_dir = args.output_dir or app_config.output_dir
    json_path, md_path = write_outputs(result, output_dir)

    print(f"Analysis complete for: {result.news_input.title}")
    if app_config.source_path:
        print(f"Config: {Path(app_config.source_path).resolve()}")
    print(f"Backend: {result.execution['backend']} ({result.execution['model']})")
    print(f"Best comment: {result.best_comment.body}")
    print(f"JSON output: {Path(json_path).resolve()}")
    print(f"Markdown report: {Path(md_path).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
