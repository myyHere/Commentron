from __future__ import annotations

import json
import re
from gzip import decompress as gzip_decompress
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from .models import NewsInput


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

def fetch_url_as_text(url: str) -> NewsInput:
    normalized_url = _normalize_url(url)
    try:
        html, final_url = _fetch_with_redirects(normalized_url)
    except (HTTPError, URLError) as exc:
        zhihu_fallback = _try_fetch_zhihu_answer(normalized_url, exc)
        if zhihu_fallback is not None:
            return zhihu_fallback
        reader_fallback = _try_fetch_via_reader(normalized_url)
        if reader_fallback is not None:
            return reader_fallback
        raise RuntimeError(
            _build_fetch_error_message(normalized_url, exc)
        ) from exc

    title = _extract_title(html, normalized_url)
    body = _extract_visible_text(html)
    return NewsInput(
        source_id=_slugify(title),
        title=title,
        url=final_url,
        body=body,
        image_descriptions=[],
        metadata={
            "fetch_mode": "url",
            "requested_url": normalized_url,
            "resolved_url": final_url,
        }
    )


def _extract_visible_text(html: str) -> str:
    stripped = re.sub(r"<script.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    stripped = re.sub(r"<style.*?</style>", " ", stripped, flags=re.IGNORECASE | re.DOTALL)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    cleaned = _clean_html(stripped)
    return _trim_article_noise(cleaned)


def _clean_html(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _slugify(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    return lowered.strip("-") or "news-input"


def _extract_title(html: str, fallback_url: str) -> str:
    patterns = [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+name=["\']twitter:title["\'][^>]+content=["\'](.*?)["\']',
        r"<title>(.*?)</title>",
        r"<h1[^>]*>(.*?)</h1>",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if match:
            title = _clean_html(match.group(1))
            title = re.sub(r"\s*\|\s*AInvest.*$", "", title, flags=re.IGNORECASE)
            if title:
                return title
    return fallback_url


def _normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip()
    normalized_path = parsed.path or "/"
    rebuilt = f"{parsed.scheme}://{parsed.netloc}{normalized_path}"
    if parsed.query:
        rebuilt = f"{rebuilt}?{parsed.query}"
    return rebuilt


def _fetch_with_redirects(url: str, max_redirects: int = 5) -> tuple[str, str]:
    opener = build_opener(ProxyHandler({}))
    current_url = url
    visited: set[str] = set()

    for _ in range(max_redirects + 1):
        if current_url in visited:
            raise RuntimeError(f"Redirect loop detected while fetching URL: {url}")
        visited.add(current_url)

        request = Request(
            current_url,
            headers=_build_request_headers(current_url),
        )
        try:
            with opener.open(request, timeout=10) as response:
                html = _read_response_text(response)
                return html, _normalize_url(response.geturl())
        except HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                location = exc.headers.get("Location") if exc.headers else None
                if not location:
                    raise
                current_url = _normalize_url(urljoin(current_url, location))
                continue
            raise

    raise RuntimeError(f"Too many redirects while fetching URL: {url}")


def _trim_article_noise(text: str) -> str:
    start_markers = [
        "News Details",
        "Article with URL markers:",
    ]
    end_markers = [
        "Stay ahead of the market.",
        "Editorial Disclosure",
        "Investment Warning:",
        "PRODUCTS",
        "Recommended",
    ]

    trimmed = text
    for marker in start_markers:
        index = trimmed.find(marker)
        if index != -1:
            trimmed = trimmed[index + len(marker):].strip()
            break

    for marker in end_markers:
        index = trimmed.find(marker)
        if index != -1:
            trimmed = trimmed[:index].strip()
            break

    trimmed = re.sub(r"\bSymbols\b", " ", trimmed, flags=re.IGNORECASE)
    trimmed = re.sub(r"\bAInvest\b", " ", trimmed, flags=re.IGNORECASE)
    trimmed = re.sub(r"\b\d-DAY FREE\b", " ", trimmed, flags=re.IGNORECASE)
    trimmed = re.sub(r"\s+", " ", trimmed).strip()
    return trimmed or text


def _read_response_text(response) -> str:
    body = response.read()
    encoding = ""
    headers = getattr(response, "headers", None)
    if headers is not None:
        encoding = headers.get("Content-Encoding", "")
    if "gzip" in encoding.lower():
        body = gzip_decompress(body)
    return body.decode("utf-8", errors="ignore")


def _build_request_headers(url: str) -> dict[str, str]:
    parsed = urlsplit(url)
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    if "zhihu.com" in parsed.netloc:
        headers.update(
            {
                "Referer": f"{parsed.scheme}://{parsed.netloc}/",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Upgrade-Insecure-Requests": "1",
            }
        )
    return headers


def _try_fetch_zhihu_answer(url: str, exc: Exception) -> NewsInput | None:
    if not isinstance(exc, HTTPError) or exc.code != 403:
        return None
    answer_id = _extract_zhihu_answer_id(url)
    if answer_id is None:
        return None

    api_url = (
        f"https://www.zhihu.com/api/v4/answers/{answer_id}"
        "?include=content,excerpt,question.title,author.name,voteup_count,comment_count,created_time,updated_time"
    )
    opener = build_opener(ProxyHandler({}))
    request = Request(
        api_url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip",
            "Referer": url,
            "X-Requested-With": "fetch",
        },
    )
    try:
        with opener.open(request, timeout=10) as response:
            payload = json.loads(_read_response_text(response))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None

    question = payload.get("question") or {}
    title = _clean_html(str(question.get("title") or "").strip())
    body_html = str(payload.get("content") or payload.get("excerpt") or "").strip()
    body = _extract_visible_text(body_html) if "<" in body_html else _clean_html(body_html)
    if not title or not body:
        return None

    return NewsInput(
        source_id=_slugify(title),
        title=title,
        url=url,
        body=body,
        image_descriptions=[],
        metadata={
            "fetch_mode": "zhihu_answer_api",
            "requested_url": url,
            "resolved_url": url,
            "answer_id": answer_id,
            "author_name": (payload.get("author") or {}).get("name"),
            "voteup_count": payload.get("voteup_count"),
            "comment_count": payload.get("comment_count"),
        },
    )


def _try_fetch_via_reader(url: str) -> NewsInput | None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return None

    reader_url = f"https://r.jina.ai/{url}"
    opener = build_opener(ProxyHandler({}))
    request = Request(
        reader_url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/plain, text/markdown;q=0.9, */*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip",
            "x-respond-with": "markdown",
            "x-no-cache": "true",
        },
    )
    try:
        with opener.open(request, timeout=15) as response:
            markdown = _read_response_text(response)
    except (HTTPError, URLError, TimeoutError):
        return None

    title, body = _extract_reader_content(markdown, fallback_url=url)
    if not body:
        return None

    return NewsInput(
        source_id=_slugify(title),
        title=title,
        url=url,
        body=body,
        image_descriptions=[],
        metadata={
            "fetch_mode": "reader_proxy",
            "requested_url": url,
            "resolved_url": url,
            "reader_url": reader_url,
        },
    )


def _extract_zhihu_answer_id(url: str) -> str | None:
    match = re.search(r"/answer/(\d+)", url)
    if match:
        return match.group(1)
    return None


def _extract_reader_content(markdown: str, fallback_url: str) -> tuple[str, str]:
    title = fallback_url
    title_match = re.search(r"(?mi)^Title:\s*(.+?)\s*$", markdown)
    if title_match:
        title = _clean_html(title_match.group(1))
    else:
        heading_match = re.search(r"(?m)^#\s+(.+?)\s*$", markdown)
        if heading_match:
            title = _clean_html(heading_match.group(1))

    body = markdown
    marker_match = re.search(r"(?is)Markdown Content:\s*(.+)$", markdown)
    if marker_match:
        body = marker_match.group(1)

    body = re.sub(r"(?mi)^URL Source:\s*.+?$", " ", body)
    body = re.sub(r"(?mi)^Title:\s*.+?$", " ", body)
    body = re.sub(r"(?mi)^Markdown Content:\s*$", " ", body)
    body = re.sub(r"(?m)^#{1,6}\s+", "", body)
    body = _clean_html(body)
    return title, body


def _format_fetch_error(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return f"HTTP {exc.code}: {exc.reason}"
    reason = getattr(exc, "reason", exc)
    return str(reason)


def _build_fetch_error_message(url: str, exc: URLError) -> str:
    reason = _format_fetch_error(exc)
    message = (
        f"Unable to fetch URL: {url}. "
        f"Network error: {reason}. "
        "This often means the site blocked the request, the local proxy/network refused the connection, "
        "or outbound HTTPS is unavailable. No article analysis was produced from this URL."
    )
    if "zhihu.com" in url and "403" in reason:
        message = (
            f"{message} "
            "Zhihu commonly blocks unauthenticated scraping requests."
        )
    return message
