from __future__ import annotations

from .models import CommentPattern, RedditComment


STYLE_LIBRARY: dict[str, tuple[str, str, str]] = {
    "one_line_summary": (
        "Compressed verdict with a sarcastic twist.",
        "Use when the article can be reduced to one unfair but memorable truth.",
        "medium"
    ),
    "debate_hook": (
        "Turn the story into a fairness question that invites replies.",
        "Use when policy inconsistency or hypocrisy is central.",
        "medium"
    ),
    "sharp_take": (
        "Blunt reframing that names the hidden incentive.",
        "Use when the post already hints at a cynical interpretation.",
        "high"
    ),
    "dry_joke": (
        "Deadpan line that exaggerates the market's reaction.",
        "Use when investor behavior looks absurd.",
        "low"
    ),
    "role_reversal": (
        "Flip expected roles to expose the power dynamic.",
        "Use when politics and corporations appear mutually performative.",
        "medium"
    ),
    "probing_question": (
        "Question that forces readers to choose between two motives.",
        "Use when the article leaves strategic ambiguity.",
        "low"
    )
}


def derive_patterns(reference_comments: list[RedditComment]) -> list[CommentPattern]:
    patterns: list[CommentPattern] = []
    for comment in reference_comments:
        structure, when_to_use, risk_level = STYLE_LIBRARY.get(
            comment.style,
            ("General engagement pattern.", "Use when the fit is broad.", "medium")
        )
        patterns.append(
            CommentPattern(
                style=_map_style(comment.style),
                structure=structure,
                when_to_use=when_to_use,
                risk_level=risk_level,
                example_pattern=comment.body,
                source_comment=comment.body
            )
        )
    return patterns


def _map_style(raw_style: str) -> str:
    mapping = {
        "one_line_summary": "一针见血",
        "debate_hook": "引发争论",
        "sharp_take": "一针见血",
        "dry_joke": "抖机灵",
        "role_reversal": "抖机灵",
        "probing_question": "反问式"
    }
    return mapping.get(raw_style, raw_style)
