from __future__ import annotations

import json

from .models import CandidateComment, CommentPattern, NewsInput, PostUnderstanding


def build_understanding_system_prompt() -> str:
    return (
        "You are a news-post analysis assistant. "
        "Return only JSON. "
        "Read the title, article body, and any image cues. "
        "Extract the parts that are most useful for writing high-engagement comments."
    )


def build_understanding_user_payload(news_input: NewsInput) -> str:
    payload = {
        "task": "Analyze this news post for comment-writing.",
        "required_json_keys": [
            "summary",
            "core_claim",
            "tone",
            "controversies",
            "humor_hooks",
            "debate_hooks",
            "visual_hooks",
            "evidence",
        ],
        "title": news_input.title,
        "url": news_input.url,
        "body": news_input.body,
        "image_descriptions": news_input.image_descriptions,
        "metadata": news_input.metadata,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_generation_system_prompt() -> str:
    return (
        "You write original, punchy social comments about news. "
        "Return only JSON. "
        "Do not copy reference comments. "
        "Generate varied comments that are tightly grounded in the post understanding."
    )


def build_generation_user_payload(
    understanding: PostUnderstanding,
    patterns: list[CommentPattern],
) -> str:
    payload = {
        "task": "Generate exactly 4 candidate comments.",
        "required_styles": ["一针见血", "抖机灵", "引发争论", "反问式"],
        "required_json_keys": [
            "candidate_comments"
        ],
        "candidate_comment_keys": [
            "style",
            "body",
            "target_emotion",
            "expected_engagement",
            "risk_notes",
            "rationale",
        ],
        "understanding": understanding.__dict__,
        "patterns": [pattern.__dict__ for pattern in patterns],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_ranking_system_prompt() -> str:
    return (
        "You are choosing the strongest public-facing comment. "
        "Return only JSON. "
        "Prefer comments that are factual, distinctive, and likely to trigger replies without becoming incoherent."
    )


def build_ranking_user_payload(candidates: list[CandidateComment]) -> str:
    payload = {
        "task": "Rank the candidate comments and pick the single best one.",
        "required_json_keys": ["best_index", "scores"],
        "scores_item_keys": ["index", "score", "reason"],
        "candidates": [
            {
                "index": index,
                "style": candidate.style,
                "body": candidate.body,
                "target_emotion": candidate.target_emotion,
                "expected_engagement": candidate.expected_engagement,
                "risk_notes": candidate.risk_notes,
            }
            for index, candidate in enumerate(candidates)
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
