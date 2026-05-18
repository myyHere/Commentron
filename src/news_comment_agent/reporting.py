from __future__ import annotations

import json
from pathlib import Path

from .models import PipelineResult


def write_outputs(result: PipelineResult, output_dir: str) -> tuple[Path, Path]:
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)

    json_path = base / "result.json"
    md_path = base / "report.md"

    json_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    md_path.write_text(_build_markdown(result), encoding="utf-8")
    return json_path, md_path


def _build_markdown(result: PipelineResult) -> str:
    reference_lines = "\n".join(
        f"- r/{item.subreddit} | {item.style} | score {item.score}: {item.body}"
        for item in result.reference_comments
    )
    pattern_lines = "\n".join(
        f"- {item.style}: {item.structure} 风险 {item.risk_level}"
        for item in result.derived_patterns
    )
    candidate_lines = "\n".join(
        f"- [{item.style}] {item.body}\n  理由: {item.rationale}\n  互动预期: {item.expected_engagement} | 风险: {item.risk_notes} | 分数: {item.score}"
        for item in result.candidate_comments
    )

    return f"""# 新闻神评论 Agent 输出报告

## 输入新闻
- 标题: {result.news_input.title}
- 来源: {result.news_input.url or "local input"}
- 执行后端: {result.execution.get("backend", "unknown")} | 模型: {result.execution.get("model", "unknown")}

## 帖子理解
- 分类: {result.understanding.category}
- 摘要: {result.understanding.summary}
- 核心观点: {result.understanding.core_claim}
- 语气: {result.understanding.tone}
- 争议点: {", ".join(result.understanding.controversies)}
- 槽点/笑点: {", ".join(result.understanding.humor_hooks)}
- 讨论切口: {", ".join(result.understanding.debate_hooks)}
- 视觉线索: {", ".join(result.understanding.visual_hooks)}

## Reddit 参考评论
{reference_lines}

## 提炼出的互动模式
{pattern_lines}

## 候选评论
{candidate_lines}

## 主推评论
{result.best_comment.body}

## 配图构思
- 概念: {result.visual_prompt.concept}
- Prompt: {result.visual_prompt.prompt}
"""
