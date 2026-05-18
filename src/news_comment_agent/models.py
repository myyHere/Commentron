from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class NewsInput:
    source_id: str
    title: str
    url: str | None
    body: str
    image_descriptions: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    local_image_paths: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PostUnderstanding:
    category: str
    summary: str
    core_claim: str
    tone: str
    controversies: list[str]
    humor_hooks: list[str]
    debate_hooks: list[str]
    visual_hooks: list[str]
    evidence: list[str]
    topic_keywords: list[str] = field(default_factory=list)


@dataclass
class RedditComment:
    subreddit: str
    topic: str
    score: int
    style: str
    body: str
    tags: list[str]


@dataclass
class CommentPattern:
    style: str
    structure: str
    when_to_use: str
    risk_level: str
    example_pattern: str
    source_comment: str


@dataclass
class CandidateComment:
    style: str
    body: str
    target_emotion: str
    expected_engagement: str
    risk_notes: str
    rationale: str
    score: float = 0.0


@dataclass
class VisualPrompt:
    concept: str
    prompt: str


@dataclass
class PipelineResult:
    news_input: NewsInput
    understanding: PostUnderstanding
    reference_comments: list[RedditComment]
    derived_patterns: list[CommentPattern]
    candidate_comments: list[CandidateComment]
    best_comment: CandidateComment
    visual_prompt: VisualPrompt
    execution: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
