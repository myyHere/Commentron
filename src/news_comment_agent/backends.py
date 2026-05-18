from __future__ import annotations

import base64
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from .generation import create_visual_prompt, generate_candidate_comments
from .models import CandidateComment, CommentPattern, NewsInput, PostUnderstanding
from .prompts import (
    build_generation_system_prompt,
    build_generation_user_payload,
    build_ranking_system_prompt,
    build_ranking_user_payload,
    build_understanding_system_prompt,
    build_understanding_user_payload,
)
from .ranking import rank_candidates
from .understanding import analyze_post


@dataclass
class RuntimeSettings:
    backend_name: str = "heuristic"
    model: str = "gpt-4.1-mini"
    api_base: str = "https://api.openai.com/v1/responses"
    api_key: str | None = None
    proxy_url: str | None = None
    api_mode: str = "responses"

    @classmethod
    def from_args(
        cls,
        backend_name: str = "heuristic",
        model: str | None = None,
        api_base: str | None = None,
        proxy_url: str | None = None,
        api_mode: str | None = None,
        api_key: str | None = None,
    ) -> "RuntimeSettings":
        resolved_api_base = api_base or "https://api.openai.com/v1/responses"
        return cls(
            backend_name=backend_name,
            model=model or "gpt-4.1-mini",
            api_base=resolved_api_base,
            api_key=api_key or os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY"),
            proxy_url=proxy_url or os.getenv("OPENAI_HTTPS_PROXY") or os.getenv("OPENAI_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("https_proxy"),
            api_mode=api_mode or _infer_api_mode(resolved_api_base),
        )


class BaseBackend:
    name = "base"

    def analyze_post(self, news_input: NewsInput) -> PostUnderstanding:
        raise NotImplementedError

    def generate_candidates(
        self,
        understanding: PostUnderstanding,
        patterns: list[CommentPattern],
    ) -> list[CandidateComment]:
        raise NotImplementedError

    def rank_candidates(
        self,
        candidates: list[CandidateComment],
    ) -> tuple[list[CandidateComment], CandidateComment]:
        raise NotImplementedError


class HeuristicBackend(BaseBackend):
    name = "heuristic"

    def analyze_post(self, news_input: NewsInput) -> PostUnderstanding:
        return analyze_post(news_input)

    def generate_candidates(
        self,
        understanding: PostUnderstanding,
        patterns: list[CommentPattern],
    ) -> list[CandidateComment]:
        return generate_candidate_comments(understanding, patterns)

    def rank_candidates(
        self,
        candidates: list[CandidateComment],
    ) -> tuple[list[CandidateComment], CandidateComment]:
        return rank_candidates(candidates)


class OpenAIBackend(BaseBackend):
    name = "openai"

    def __init__(self, settings: RuntimeSettings):
        if not settings.api_key:
            raise RuntimeError("OPENAI_API_KEY is required when using the openai backend.")
        _validate_openai_settings(settings)
        self.settings = settings
        self.opener = _build_openai_opener(settings.proxy_url)

    def analyze_post(self, news_input: NewsInput) -> PostUnderstanding:
        prompt_text = build_understanding_user_payload(news_input)
        content = [{"type": "input_text", "text": prompt_text}]
        for image_url in news_input.image_urls:
            content.append({"type": "input_image", "image_url": image_url})
        for local_path in news_input.local_image_paths:
            content.append({"type": "input_image", "image_url": _file_to_data_url(local_path)})

        payload = self._create_payload(
            system_prompt=build_understanding_system_prompt(),
            user_content=content,
        )
        data = self._call_json(payload)
        return PostUnderstanding(**_normalize_understanding_json(data))

    def generate_candidates(
        self,
        understanding: PostUnderstanding,
        patterns: list[CommentPattern],
    ) -> list[CandidateComment]:
        payload = self._create_payload(
            system_prompt=build_generation_system_prompt(),
            user_content=[{"type": "input_text", "text": build_generation_user_payload(understanding, patterns)}],
        )
        data = self._call_json(payload)
        raw_candidates = data.get("candidate_comments", [])
        if not raw_candidates:
            raise RuntimeError("OpenAI backend returned no candidate_comments.")
        return [CandidateComment(**_normalize_candidate_json(item)) for item in raw_candidates]

    def rank_candidates(
        self,
        candidates: list[CandidateComment],
    ) -> tuple[list[CandidateComment], CandidateComment]:
        payload = self._create_payload(
            system_prompt=build_ranking_system_prompt(),
            user_content=[{"type": "input_text", "text": build_ranking_user_payload(candidates)}],
        )
        data = self._call_json(payload)
        scores = data.get("scores", [])
        for item in scores:
            index = item.get("index")
            score = item.get("score")
            if isinstance(index, int) and 0 <= index < len(candidates):
                candidates[index].score = float(score)
                reason = item.get("reason", "").strip()
                if reason:
                    candidates[index].rationale = f"{candidates[index].rationale} 评审说明：{reason}"

        if not scores:
            return rank_candidates(candidates)

        ranked = sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
        best_index = data.get("best_index")
        if isinstance(best_index, int) and 0 <= best_index < len(candidates):
            best_body = candidates[best_index].body
            for candidate in ranked:
                if candidate.body == best_body:
                    return ranked, candidate
        return ranked, ranked[0]

    def _create_payload(self, system_prompt: str, user_content: list[dict[str, Any]]) -> dict[str, Any]:
        if self.settings.api_mode == "chat":
            return {
                "model": self.settings.model,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": _chat_content_to_text(user_content),
                    },
                ],
                "response_format": {
                    "type": "json_object"
                },
            }
        return {
            "model": self.settings.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
            "text": {
                "format": {
                    "type": "json_object"
                }
            },
        }

    def _call_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            self.settings.api_base,
            data=body,
            headers=_build_api_headers(self.settings),
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=60) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"OpenAI API request failed: HTTP {exc.code} {detail}") from exc
        except URLError as exc:
            proxy_hint = f" via proxy {self.settings.proxy_url}" if self.settings.proxy_url else ""
            raise RuntimeError(
                "OpenAI API request failed due to network error"
                f"{proxy_hint}. "
                "If you are in WSL or behind a local proxy, pass a reachable HTTP/HTTPS proxy with --proxy."
            ) from exc

        if self.settings.api_mode == "chat":
            extracted = _extract_chat_output_text(raw)
            if not extracted:
                raise RuntimeError("Chat Completions API response did not contain message content.")
            return _parse_json_response(extracted)

        text = raw.get("output_text")
        if text:
            return _parse_json_response(text)

        extracted = _extract_output_text(raw.get("output", []))
        if not extracted:
            raise RuntimeError("Responses API response did not contain output_text.")
        return _parse_json_response(extracted)


def create_backend(settings: RuntimeSettings) -> BaseBackend:
    if settings.backend_name == "heuristic":
        return HeuristicBackend()
    if settings.backend_name == "openai":
        return OpenAIBackend(settings)
    raise ValueError(f"Unsupported backend: {settings.backend_name}")


def _validate_openai_settings(settings: RuntimeSettings) -> None:
    if not settings.api_base.isascii():
        raise RuntimeError(
            "The --api-base value must be a real ASCII URL, not a placeholder like "
            "'https://你的网关/v1/responses'."
        )
    if not settings.model.isascii():
        raise RuntimeError(
            "The --model value must be a real model id, not a placeholder like '你要用的模型'."
        )

    parsed = urlsplit(settings.api_base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(
            "The --api-base value must be a full URL such as "
            "'https://api.openai.com/v1/responses' or your compatible gateway endpoint."
        )
    if settings.api_mode not in {"responses", "chat"}:
        raise RuntimeError("The API mode must be either 'responses' or 'chat'.")

    if settings.proxy_url:
        if not settings.proxy_url.isascii():
            raise RuntimeError("The --proxy value must be an ASCII URL such as 'http://127.0.0.1:PORT'.")
        proxy_parsed = urlsplit(settings.proxy_url)
        if proxy_parsed.scheme not in {"http", "https"} or not proxy_parsed.netloc:
            raise RuntimeError("The --proxy value must be a full HTTP or HTTPS proxy URL such as 'http://127.0.0.1:PORT'.")


def _build_openai_opener(proxy_url: str | None):
    if proxy_url:
        return build_opener(ProxyHandler({"http": proxy_url, "https": proxy_url}))
    return build_opener(ProxyHandler({}))


def _build_api_headers(settings: RuntimeSettings) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
        "User-Agent": "news-comment-agent/0.1",
    }
    if "openrouter.ai" in settings.api_base.lower():
        headers["HTTP-Referer"] = "https://news-comment-agent.local"
        headers["X-Title"] = "news-comment-agent"
    return headers


def _infer_api_mode(api_base: str) -> str:
    lowered = api_base.lower()
    if lowered.endswith("/chat/completions") or "/chat/completions" in lowered:
        return "chat"
    return "responses"


def _chat_content_to_text(user_content: list[dict[str, Any]]) -> str:
    text_chunks: list[str] = []
    image_urls: list[str] = []
    for item in user_content:
        if item.get("type") == "input_text" and item.get("text"):
            text_chunks.append(str(item["text"]))
        elif item.get("type") == "input_image" and item.get("image_url"):
            image_urls.append(str(item["image_url"]))
    if image_urls:
        text_chunks.append("Image inputs:")
        text_chunks.extend(image_urls)
    return "\n\n".join(text_chunks).strip()


def _extract_output_text(output_items: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for item in output_items:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                chunks.append(content["text"])
    return "".join(chunks).strip()


def _extract_chat_output_text(raw: dict[str, Any]) -> str:
    choices = raw.get("choices", [])
    if not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                parts.append(str(item["text"]))
            elif isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        return "".join(parts).strip()
    return ""


def _parse_json_response(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if not cleaned:
        raise RuntimeError("Model response was empty when JSON was expected.")

    candidates = [cleaned]
    if cleaned.startswith("```"):
        fence_match = cleaned.split("```")
        if len(fence_match) >= 3:
            candidates.append(fence_match[1].lstrip("json").strip())

    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidates.append(cleaned[first_brace:last_brace + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    raise RuntimeError(f"Model response was not valid JSON: {cleaned[:400]}")


def _file_to_data_url(path: str) -> str:
    file_path = Path(path)
    mime_type, _ = mimetypes.guess_type(file_path.name)
    if not mime_type:
        mime_type = "image/png"
    encoded = base64.b64encode(file_path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def _normalize_understanding_json(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "category": _string_value(data, "category") or "general",
        "summary": _string_value(data, "summary"),
        "core_claim": _string_value(data, "core_claim"),
        "tone": _string_value(data, "tone"),
        "controversies": _string_list_value(data, "controversies"),
        "humor_hooks": _string_list_value(data, "humor_hooks"),
        "debate_hooks": _string_list_value(data, "debate_hooks"),
        "visual_hooks": _string_list_value(data, "visual_hooks"),
        "evidence": _string_list_value(data, "evidence"),
        "topic_keywords": _string_list_value(data, "topic_keywords"),
    }


def _normalize_candidate_json(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "style": _string_value(data, "style"),
        "body": _string_value(data, "body"),
        "target_emotion": _string_value(data, "target_emotion"),
        "expected_engagement": _string_value(data, "expected_engagement"),
        "risk_notes": _string_value(data, "risk_notes"),
        "rationale": _string_value(data, "rationale"),
    }


def _string_value(data: dict[str, Any], key: str) -> str:
    value = data.get(key, "")
    return value if isinstance(value, str) else str(value)


def _string_list_value(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if isinstance(value, list):
        return [str(item) for item in value]
    if value:
        return [str(value)]
    return []
