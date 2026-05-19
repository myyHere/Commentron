from __future__ import annotations

import sys

from .backends import RuntimeSettings, create_backend
from .generation import create_visual_prompt
from .models import NewsInput, PipelineResult
from .patterns import derive_patterns
from .reddit_retrieval import retrieve_reference_comments


def run_pipeline(
    news_input: NewsInput,
    settings: RuntimeSettings | None = None,
    config_path: str | None = None,
) -> PipelineResult:
    runtime_settings = settings or RuntimeSettings()
    backend = create_backend(runtime_settings)

    _log_progress(f"Understanding post with backend: {backend.name}")
    understanding = backend.analyze_post(news_input)
    _log_progress("Retrieving Reddit reference comments")
    reference_comments = retrieve_reference_comments(
        news_input,
        understanding=understanding,
        config_path=config_path,
    )
    _log_progress(f"Retrieved {len(reference_comments)} reference comments")
    derived_patterns = derive_patterns(reference_comments)
    _log_progress("Generating candidate comments")
    candidates = backend.generate_candidates(understanding, derived_patterns)
    _log_progress(f"Ranking {len(candidates)} candidate comments")
    ranked_candidates, best_comment = backend.rank_candidates(candidates)
    _log_progress("Creating visual prompt")
    visual_prompt = create_visual_prompt(best_comment, understanding)
    return PipelineResult(
        news_input=news_input,
        understanding=understanding,
        reference_comments=reference_comments,
        derived_patterns=derived_patterns,
        candidate_comments=ranked_candidates,
        best_comment=best_comment,
        visual_prompt=visual_prompt,
        execution={
            "backend": backend.name,
            "model": runtime_settings.model if runtime_settings.backend_name == "openai" else "heuristic-rules",
        },
    )


def _log_progress(message: str) -> None:
    print(f"[progress] {message}", file=sys.stderr, flush=True)
