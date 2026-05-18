from __future__ import annotations

import json
from pathlib import Path

from .models import NewsInput, PostUnderstanding, RedditComment


def retrieve_reference_comments(
    news_input: NewsInput,
    understanding: PostUnderstanding | None = None,
    limit: int = 4,
) -> list[RedditComment]:
    path = Path(__file__).with_name("sample_data") / "reddit_comments.json"
    raw_comments = json.loads(path.read_text(encoding="utf-8"))
    comments = [RedditComment(**item) for item in raw_comments]

    tags = set(news_input.metadata.get("topic_tags", []))
    if not tags:
        tags = set(news_input.title.lower().split()) | set(news_input.body.lower().split())
    if understanding:
        tags |= {keyword.lower() for keyword in understanding.topic_keywords}
        tags.add(understanding.category.lower())

    ranked = sorted(
        comments,
        key=lambda item: _score_comment(item, tags, understanding.category if understanding else None),
        reverse=True,
    )
    return ranked[:limit]


def _score_comment(comment: RedditComment, tags: set[str], category: str | None) -> tuple[int, int, int]:
    overlap = len({tag.lower() for tag in comment.tags} & {tag.lower() for tag in tags})
    category_bonus = 0
    if category == "deal" and any(tag in {"deal", "discount", "consumer", "tablet", "apple"} for tag in comment.tags):
        category_bonus = 2
    elif category == "policy" and any(tag in {"policy", "regulation", "politics", "markets", "big tech"} for tag in comment.tags):
        category_bonus = 2
    elif category == "earnings" and any(tag in {"earnings", "valuation", "cash flow", "aws", "cloud", "capex"} for tag in comment.tags):
        category_bonus = 2
    return category_bonus, overlap, comment.score
