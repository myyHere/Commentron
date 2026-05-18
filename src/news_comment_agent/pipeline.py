from __future__ import annotations

from .backends import RuntimeSettings, create_backend
from .generation import create_visual_prompt
from .models import NewsInput, PipelineResult
from .patterns import derive_patterns
from .reddit_retrieval import retrieve_reference_comments


def run_pipeline(news_input: NewsInput, settings: RuntimeSettings | None = None) -> PipelineResult:
    runtime_settings = settings or RuntimeSettings()
    backend = create_backend(runtime_settings)

    understanding = backend.analyze_post(news_input)
    reference_comments = retrieve_reference_comments(news_input, understanding=understanding)
    derived_patterns = derive_patterns(reference_comments)
    candidates = backend.generate_candidates(understanding, derived_patterns)
    ranked_candidates, best_comment = backend.rank_candidates(candidates)
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
