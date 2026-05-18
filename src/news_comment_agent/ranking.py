from __future__ import annotations

from .models import CandidateComment


def rank_candidates(candidates: list[CandidateComment]) -> tuple[list[CandidateComment], CandidateComment]:
    for candidate in candidates:
        candidate.score = _score(candidate)

    ranked = sorted(candidates, key=lambda item: item.score, reverse=True)
    return ranked, ranked[0]


def _score(candidate: CandidateComment) -> float:
    score = 5.0
    if "?" in candidate.body:
        score += 1.0
    if candidate.expected_engagement == "high":
        score += 1.5
    elif candidate.expected_engagement == "medium-high":
        score += 1.0
    if candidate.style in {"引发争论", "反问式"}:
        score += 0.8
    if "过度" in candidate.risk_notes:
        score -= 0.3
    if len(candidate.body) < 80:
        score += 0.2
    return round(score, 2)
