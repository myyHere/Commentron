from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, unquote, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from .config import DEFAULT_CONFIG_PATH, load_app_config
from .models import NewsInput, PostUnderstanding, RedditComment


SEARCH_ENGINE_URL = "https://html.duckduckgo.com/html/"
DEFAULT_USER_AGENT = "Commentron/0.1"


@dataclass
class RedditSearchSettings:
    user_agent: str = DEFAULT_USER_AGENT
    search_limit: int = 6
    comment_limit: int = 6


def retrieve_reference_comments(
    news_input: NewsInput,
    understanding: PostUnderstanding | None = None,
    limit: int = 4,
    config_path: str | None = None,
) -> list[RedditComment]:
    tags = _build_tags(news_input, understanding)
    settings = _load_reddit_settings(config_path)
    _log_progress("Searching for related Reddit threads")
    online_comments = _retrieve_online_reference_comments(
        news_input,
        understanding=understanding,
        tags=tags,
        settings=settings,
    )
    if online_comments:
        ranked = sorted(
            online_comments,
            key=lambda item: _score_comment(item, tags, understanding.category if understanding else None),
            reverse=True,
        )
        return ranked[:limit]

    _log_progress("Online Reddit retrieval returned no usable comments, falling back to local samples")
    comments = _load_sample_comments()
    ranked = sorted(
        comments,
        key=lambda item: _score_comment(item, tags, understanding.category if understanding else None),
        reverse=True,
    )
    return ranked[:limit]


def _load_reddit_settings(config_path: str | None) -> RedditSearchSettings:
    app_config = load_app_config(config_path or DEFAULT_CONFIG_PATH)
    return RedditSearchSettings(
        user_agent=app_config.reddit_user_agent or DEFAULT_USER_AGENT,
        search_limit=max(1, app_config.reddit_search_limit),
        comment_limit=max(1, app_config.reddit_comment_limit),
    )


def _load_sample_comments() -> list[RedditComment]:
    path = Path(__file__).with_name("sample_data") / "reddit_comments.json"
    raw_comments = json.loads(path.read_text(encoding="utf-8"))
    return [RedditComment(**item) for item in raw_comments]


def _build_tags(news_input: NewsInput, understanding: PostUnderstanding | None) -> set[str]:
    tags = set(news_input.metadata.get("topic_tags", []))
    if not tags:
        tags = set(news_input.title.lower().split()) | set(news_input.body.lower().split())
    if understanding:
        tags |= {keyword.lower() for keyword in understanding.topic_keywords}
        tags.add(understanding.category.lower())
    return tags


def _retrieve_online_reference_comments(
    news_input: NewsInput,
    understanding: PostUnderstanding | None,
    tags: set[str],
    settings: RedditSearchSettings,
) -> list[RedditComment]:
    opener = build_opener(ProxyHandler({}))
    query = _build_search_query(news_input, understanding, tags)
    _log_progress(f"Search query: {query}")
    post_urls = _search_reddit_post_urls(opener, settings, query)
    if not post_urls:
        _log_progress("Search returned no Reddit thread URLs")
        return []

    _log_progress(f"Found {len(post_urls)} Reddit thread URLs")
    comments: list[RedditComment] = []
    seen_bodies: set[str] = set()
    for index, post_url in enumerate(post_urls[:settings.search_limit], start=1):
        _log_progress(f"Fetching Reddit thread {index}/{min(len(post_urls), settings.search_limit)}")
        for comment in _fetch_post_comments(opener, settings, post_url):
            normalized_body = comment.body.strip().lower()
            if normalized_body in seen_bodies:
                continue
            seen_bodies.add(normalized_body)
            comments.append(comment)
        _log_progress(f"Collected {len(comments)} comment candidates so far")
    return comments


def _search_reddit_post_urls(opener, settings: RedditSearchSettings, query: str) -> list[str]:
    search_query = f"site:reddit.com/r {query}"
    request = Request(
        f"{SEARCH_ENGINE_URL}?q={quote_plus(search_query)}",
        headers={
            "User-Agent": settings.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )

    try:
        with opener.open(request, timeout=10) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError, TimeoutError):
        return []

    links = re.findall(r'href="([^"]+)"', html, flags=re.IGNORECASE)
    urls: list[str] = []
    seen: set[str] = set()
    for link in links:
        normalized = _extract_reddit_url(link)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
    return urls


def _extract_reddit_url(link: str) -> str | None:
    candidate = link.strip()
    if not candidate:
        return None
    if "uddg=" in candidate:
        parsed = urlsplit(candidate)
        encoded = parse_qs(parsed.query).get("uddg", [])
        if encoded:
            candidate = unquote(encoded[0])
    if candidate.startswith("//"):
        candidate = f"https:{candidate}"
    if not candidate.startswith(("http://", "https://")):
        return None
    parsed = urlsplit(candidate)
    if "reddit.com" not in parsed.netloc:
        return None
    if "/comments/" not in parsed.path:
        return None
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")


def _fetch_post_comments(opener, settings: RedditSearchSettings, post_url: str) -> list[RedditComment]:
    reader_url = f"https://r.jina.ai/{post_url}"
    request = Request(
        reader_url,
        headers={
            "User-Agent": settings.user_agent,
            "Accept": "text/plain, text/markdown;q=0.9, */*;q=0.8",
            "x-respond-with": "markdown",
            "x-no-cache": "true",
        },
    )

    try:
        with opener.open(request, timeout=15) as response:
            markdown = response.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError, TimeoutError):
        return []

    if "whoa there, pardner!" in markdown.lower():
        return []

    title = _extract_reader_title(markdown, post_url)
    subreddit = _extract_subreddit(post_url)
    candidate_lines = _extract_comment_lines(markdown)

    comments: list[RedditComment] = []
    for body in candidate_lines[:settings.comment_limit]:
        comment = _normalize_comment(body, title=title, subreddit=subreddit)
        if comment is None:
            continue
        comments.append(comment)
    return comments


def _extract_reader_title(markdown: str, fallback_url: str) -> str:
    title_match = re.search(r"(?mi)^Title:\s*(.+?)\s*$", markdown)
    if title_match:
        return title_match.group(1).strip()
    heading_match = re.search(r"(?m)^#\s+(.+?)\s*$", markdown)
    if heading_match:
        return heading_match.group(1).strip()
    return fallback_url


def _extract_subreddit(post_url: str) -> str:
    match = re.search(r"/r/([^/]+)/comments/", post_url)
    if match:
        return match.group(1)
    return "reddit"


def _extract_comment_lines(markdown: str) -> list[str]:
    marker_match = re.search(r"(?is)Markdown Content:\s*(.+)$", markdown)
    body = marker_match.group(1) if marker_match else markdown
    lines = [line.strip() for line in body.splitlines()]

    results: list[str] = []
    seen: set[str] = set()
    for line in lines:
        cleaned = _clean_comment_line(line)
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        results.append(cleaned)
    return results


def _clean_comment_line(line: str) -> str:
    cleaned = re.sub(r"^>\s*", "", line).strip()
    cleaned = re.sub(r"^\s*[-*]\s*", "", cleaned)
    if not cleaned:
        return ""
    if cleaned.startswith(("Title:", "URL Source:", "Markdown Content:")):
        return ""
    if cleaned.startswith("#"):
        return ""
    lowered = cleaned.lower()
    if any(token in lowered for token in [
        "reddit",
        "share",
        "award",
        "sort by",
        "comments",
        "posted by",
        "submitted",
        "vote",
        "login",
        "sign up",
        "blocked due to a network policy",
    ]):
        return ""
    if len(cleaned) < 24 or len(cleaned) > 320:
        return ""
    if cleaned.count(" ") < 3:
        return ""
    return cleaned


def _build_search_query(
    news_input: NewsInput,
    understanding: PostUnderstanding | None,
    tags: set[str],
) -> str:
    parts: list[str] = []
    if understanding and understanding.topic_keywords:
        parts.extend(understanding.topic_keywords[:4])
    metadata_tags = [str(item).strip() for item in news_input.metadata.get("topic_tags", []) if str(item).strip()]
    parts.extend(metadata_tags[:4])

    title_tokens = [token for token in news_input.title.replace(":", " ").split() if len(token) > 3]
    parts.extend(title_tokens[:4])

    if understanding and understanding.category:
        parts.append(understanding.category)
    elif tags:
        parts.extend(sorted(tags)[:2])

    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        lowered = part.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(part)
    return " ".join(deduped[:7]) or news_input.title


def _normalize_comment(body: str, title: str, subreddit: str) -> RedditComment | None:
    cleaned = body.strip()
    if not cleaned or cleaned in {"[deleted]", "[removed]"}:
        return None

    style = _infer_style(cleaned)
    tags = _extract_tags(title, cleaned, subreddit)
    score = max(1, min(9999, len(cleaned) * 3))
    return RedditComment(
        subreddit=subreddit,
        topic=title,
        score=score,
        style=style,
        body=cleaned,
        tags=tags,
    )


def _infer_style(body: str) -> str:
    lowered = body.lower()
    if "?" in body:
        if any(token in lowered for token in ["is this", "are we", "how much", "at what point", "do we"]):
            return "probing_question"
        return "debate_hook"
    if any(token in lowered for token in ["amazing how", "translation:", "less than", "really means", "in other words"]):
        return "sharp_take"
    if any(token in lowered for token in ["lol", "lmao", "yeah sure", "priced in", "coupon", "vip", "as if"]):
        return "dry_joke"
    return "one_line_summary"


def _extract_tags(topic: str, body: str, subreddit: str) -> list[str]:
    tokens = {
        token.lower()
        for token in (f"{topic} {body} {subreddit}").replace("/", " ").replace("-", " ").split()
        if len(token) > 3
    }
    preferred = [
        "apple", "ipad", "tablet", "deal", "discount", "consumer", "policy", "politics",
        "markets", "regulation", "tariff", "earnings", "valuation", "cash", "flow",
        "cloud", "capex", "investment", "question", "joke",
    ]
    tags = [token for token in preferred if token in tokens]
    if tags:
        return tags
    return sorted(tokens)[:5]


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


def _log_progress(message: str) -> None:
    print(f"[progress] {message}", file=sys.stderr, flush=True)
