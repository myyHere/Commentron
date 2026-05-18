from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from io import BytesIO
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from news_comment_agent.config import load_app_config
from news_comment_agent.ingestion import fetch_url_as_text, load_text_file
from news_comment_agent.models import NewsInput
from news_comment_agent.backends import RuntimeSettings, _extract_chat_output_text, _infer_api_mode
from news_comment_agent.pipeline import run_pipeline


class PipelineTests(unittest.TestCase):
    def _policy_input(self) -> NewsInput:
        return NewsInput(
            source_id="policy-case",
            title="MegaCorp pledges billions while lobbying for new trade exemptions",
            url="https://example.com/policy-case",
            body=(
                "MegaCorp announced a major domestic investment plan while analysts framed it as a possible path "
                "to tariff relief. Supporters called it strategic industrial policy. Critics called it a costly "
                "political shortcut that only the largest firms can afford."
            ),
            metadata={"topic_tags": ["policy", "tariff", "regulation", "markets", "big tech"]},
        )

    def test_pipeline_returns_ranked_candidates(self):
        news_input = self._policy_input()
        result = run_pipeline(news_input, settings=RuntimeSettings())

        self.assertTrue(result.news_input.title.startswith("MegaCorp"))
        self.assertEqual(result.understanding.category, "policy")
        self.assertTrue(result.reference_comments)
        self.assertGreaterEqual(len(result.candidate_comments), 4)
        self.assertGreaterEqual(result.best_comment.score, result.candidate_comments[-1].score)
        self.assertTrue(result.visual_prompt.prompt)

    def test_understanding_captures_controversy_and_hooks(self):
        news_input = self._policy_input()
        result = run_pipeline(news_input, settings=RuntimeSettings())

        self.assertTrue(result.understanding.controversies)
        self.assertTrue(result.understanding.debate_hooks)
        self.assertTrue(result.understanding.humor_hooks)
        self.assertTrue(any(candidate.style in {"引发争论", "反问式"} for candidate in result.candidate_comments))

    def test_openai_backend_requires_api_key(self):
        news_input = self._policy_input()
        with self.assertRaises(RuntimeError):
            run_pipeline(
                news_input,
                settings=RuntimeSettings(backend_name="openai", api_key=None),
            )

    def test_openai_backend_rejects_placeholder_api_base(self):
        news_input = self._policy_input()
        with self.assertRaises(RuntimeError) as ctx:
            run_pipeline(
                news_input,
                settings=RuntimeSettings(
                    backend_name="openai",
                    api_key="test-key",
                    api_base="https://你的网关/v1/responses",
                    model="gpt-4.1-mini",
                ),
            )

        self.assertIn("real ASCII URL", str(ctx.exception))

    def test_openai_backend_rejects_placeholder_model(self):
        news_input = self._policy_input()
        with self.assertRaises(RuntimeError) as ctx:
            run_pipeline(
                news_input,
                settings=RuntimeSettings(
                    backend_name="openai",
                    api_key="test-key",
                    api_base="https://api.openai.com/v1/responses",
                    model="你要用的模型",
                ),
            )

        self.assertIn("real model id", str(ctx.exception))

    def test_openai_backend_rejects_invalid_proxy(self):
        news_input = self._policy_input()
        with self.assertRaises(RuntimeError) as ctx:
            run_pipeline(
                news_input,
                settings=RuntimeSettings(
                    backend_name="openai",
                    api_key="test-key",
                    api_base="https://api.openai.com/v1/responses",
                    model="gpt-4.1-mini",
                    proxy_url="socks5://127.0.0.1:9999",
                ),
            )

        self.assertIn("HTTP or HTTPS proxy URL", str(ctx.exception))

    def test_api_mode_is_inferred_from_chat_completions_endpoint(self):
        self.assertEqual(
            _infer_api_mode("https://openrouter.ai/api/v1/chat/completions"),
            "chat",
        )
        self.assertEqual(
            _infer_api_mode("https://api.openai.com/v1/responses"),
            "responses",
        )

    def test_extract_chat_output_text_from_openrouter_style_response(self):
        raw = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "{\"summary\":\"ok\"}",
                    }
                }
            ]
        }
        self.assertEqual(_extract_chat_output_text(raw), "{\"summary\":\"ok\"}")

    def test_deal_story_generates_deal_relevant_comments(self):
        news_input = NewsInput(
            source_id="tablet-deal",
            title="Flagship tablet bundle hits a new low with a $120 discount",
            url="https://example.com/tablet-deal",
            body=(
                "A flagship tablet with 256GB storage and cellular support is now available for $679, "
                "a $120 discount from its list price. The sale is framed as a limited-time offer and "
                "includes strong upsell pressure around accessories and storage tiers."
            ),
            metadata={"topic_tags": ["tablet", "deal", "discount", "consumer", "cellular"]},
        )

        result = run_pipeline(news_input, settings=RuntimeSettings())

        self.assertIn("retail deal", result.understanding.core_claim.lower())
        self.assertEqual(result.understanding.category, "deal")
        self.assertTrue(any("256GB" in candidate.body or "低价" in candidate.body or "优惠" in candidate.body for candidate in result.candidate_comments))

    def test_text_file_input_creates_news_input(self):
        temp_path = ROOT / "tests" / "tmp_input.txt"
        temp_path.write_text("Some copied article body text.", encoding="utf-8")
        try:
            result = load_text_file(str(temp_path), title="Copied Article", source_url="https://example.com/copied")
        finally:
            temp_path.unlink(missing_ok=True)

        self.assertEqual(result.title, "Copied Article")
        self.assertEqual(result.url, "https://example.com/copied")
        self.assertEqual(result.metadata.get("fetch_mode"), "text_file")

    def test_load_app_config_reads_runtime_block(self):
        temp_path = ROOT / "tests" / "tmp_config.json"
        temp_path.write_text(
            '{\n'
            '  "runtime": {\n'
            '    "backend": "openai",\n'
            '    "model": "deepseek-v4-flash",\n'
            '    "api_base": "https://api.deepseek.com/chat/completions",\n'
            '    "api_mode": "chat",\n'
            '    "api_key": "test-key",\n'
            '    "proxy": "http://127.0.0.1:8080",\n'
            '    "output_dir": "outputs/test_run"\n'
            '  }\n'
            '}',
            encoding="utf-8",
        )
        try:
            config = load_app_config(str(temp_path))
        finally:
            temp_path.unlink(missing_ok=True)

        self.assertEqual(config.backend, "openai")
        self.assertEqual(config.model, "deepseek-v4-flash")
        self.assertEqual(config.api_base, "https://api.deepseek.com/chat/completions")
        self.assertEqual(config.api_mode, "chat")
        self.assertEqual(config.api_key, "test-key")
        self.assertEqual(config.proxy, "http://127.0.0.1:8080")
        self.assertEqual(config.output_dir, "outputs/test_run")

    def test_earnings_story_generates_earnings_relevant_comments(self):
        news_input = NewsInput(
            source_id="cloud-earnings",
            title="Cloud giant posts strong quarter while cash flow weakens under AI capex",
            url="https://example.com/cloud-q1",
            body=(
                "The company reported strong quarterly revenue and operating income, but free cash flow fell sharply "
                "after massive AI infrastructure capex. Its cloud division kept growing while valuation stayed elevated."
            ),
            metadata={"topic_tags": ["earnings", "free cash flow", "valuation", "cloud", "capex"]},
        )

        result = run_pipeline(news_input, settings=RuntimeSettings())

        self.assertEqual(result.understanding.category, "earnings")
        self.assertIn("company performance", result.understanding.core_claim.lower())
        self.assertTrue(any("现金流" in candidate.body or "估值" in candidate.body for candidate in result.candidate_comments))

    @patch("news_comment_agent.ingestion.load_sample")
    @patch("news_comment_agent.ingestion.build_opener")
    @patch.dict("news_comment_agent.ingestion.SAMPLE_URL_ALIASES", {"https://example.com/demo-article": "demo_sample"}, clear=True)
    def test_known_sample_url_falls_back_when_fetch_fails(self, mock_build_opener, mock_load_sample):
        mock_opener = mock_build_opener.return_value
        mock_opener.open.side_effect = URLError("[Errno 111] Connection refused")
        mock_load_sample.return_value = NewsInput(
            source_id="demo-sample",
            title="Demo fallback sample",
            url="https://example.com/demo-article",
            body="Fallback body",
        )

        result = fetch_url_as_text(
            "https://example.com/demo-article",
            allow_sample_fallback=True,
        )

        self.assertEqual(result.source_id, "demo-sample")
        self.assertEqual(result.metadata.get("fetch_mode"), "sample_fallback")
        self.assertIn("Connection refused", result.metadata.get("fetch_error", ""))

    @patch("news_comment_agent.ingestion.build_opener")
    def test_unknown_url_raises_actionable_error(self, mock_build_opener):
        mock_opener = mock_build_opener.return_value
        mock_opener.open.side_effect = [
            URLError("[Errno 111] Connection refused"),
            URLError("[Errno 111] Connection refused"),
        ]

        with self.assertRaises(RuntimeError) as ctx:
            fetch_url_as_text("https://example.com/news")

        self.assertIn("Network error", str(ctx.exception))
        self.assertIn("--input-file", str(ctx.exception))

    @patch("news_comment_agent.ingestion.build_opener")
    def test_zhihu_403_mentions_text_file_workflow(self, mock_build_opener):
        mock_opener = mock_build_opener.return_value
        mock_opener.open.side_effect = [
            HTTPError(
                url="https://www.zhihu.com/question/demo",
                code=403,
                msg="Forbidden",
                hdrs=None,
                fp=BytesIO(b""),
            ),
            HTTPError(
                url="https://r.jina.ai/https://www.zhihu.com/question/demo",
                code=451,
                msg="Unavailable",
                hdrs=None,
                fp=BytesIO(b""),
            ),
        ]

        with self.assertRaises(RuntimeError) as ctx:
            fetch_url_as_text("https://www.zhihu.com/question/demo")

        self.assertIn("--text-file", str(ctx.exception))

    @patch("news_comment_agent.ingestion.build_opener")
    def test_zhihu_answer_403_falls_back_to_answer_api(self, mock_build_opener):
        mock_opener = mock_build_opener.return_value
        mock_opener.open.side_effect = [
            HTTPError(
                url="https://www.zhihu.com/question/1/answer/2039653511797920206",
                code=403,
                msg="Forbidden",
                hdrs=None,
                fp=BytesIO(b""),
            ),
            self._mock_response(
                (
                    '{"question":{"title":"Zhihu Answer Title"},'
                    '"content":"<p>Detailed answer body.</p>",'
                    '"author":{"name":"Writer"},'
                    '"voteup_count":12,'
                    '"comment_count":3}'
                ).encode("utf-8"),
                "https://www.zhihu.com/api/v4/answers/2039653511797920206",
                headers={"Content-Type": "application/json"},
            ),
        ]

        result = fetch_url_as_text("https://www.zhihu.com/question/1/answer/2039653511797920206")

        self.assertEqual(result.title, "Zhihu Answer Title")
        self.assertEqual(result.body, "Detailed answer body.")
        self.assertEqual(result.metadata.get("fetch_mode"), "zhihu_answer_api")
        self.assertEqual(result.metadata.get("answer_id"), "2039653511797920206")

    @patch("news_comment_agent.ingestion.build_opener")
    @patch.dict("news_comment_agent.ingestion.SAMPLE_URL_ALIASES", {"https://example.com/demo-article": "demo_sample"}, clear=True)
    def test_known_sample_url_does_not_fallback_by_default(self, mock_build_opener):
        mock_opener = mock_build_opener.return_value
        mock_opener.open.side_effect = [
            URLError("[Errno 111] Connection refused"),
            URLError("[Errno 111] Connection refused"),
        ]

        with self.assertRaises(RuntimeError) as ctx:
            fetch_url_as_text("https://example.com/demo-article")

        self.assertIn("No article analysis was produced from this URL", str(ctx.exception))
        self.assertIn("--allow-sample-fallback", str(ctx.exception))

    @patch("news_comment_agent.ingestion.build_opener")
    def test_http_308_redirect_is_followed(self, mock_build_opener):
        mock_opener = mock_build_opener.return_value
        redirect = HTTPError(
            url="https://example.com/news",
            code=308,
            msg="Permanent Redirect",
            hdrs={"Location": "/final"},
            fp=BytesIO(b""),
        )

        mock_opener.open.side_effect = [
            redirect,
            self._mock_response(
                b"<html><title>Final Article</title><body>News Details Final body text.</body></html>",
                "https://example.com/final",
            ),
        ]

        result = fetch_url_as_text("https://example.com/news")

        self.assertEqual(result.title, "Final Article")
        self.assertEqual(result.url, "https://example.com/final")

    def test_normalize_url_preserves_trailing_slash(self):
        from news_comment_agent.ingestion import _normalize_url

        self.assertEqual(
            _normalize_url("https://example.com/path/"),
            "https://example.com/path/",
        )
        self.assertEqual(
            _normalize_url("https://example.com/path"),
            "https://example.com/path",
        )

    @patch("news_comment_agent.ingestion.build_opener")
    def test_fetch_url_falls_back_to_reader_proxy(self, mock_build_opener):
        mock_opener = mock_build_opener.return_value
        mock_opener.open.side_effect = [
            HTTPError(
                url="https://example.com/blocked",
                code=403,
                msg="Forbidden",
                hdrs=None,
                fp=BytesIO(b""),
            ),
            self._mock_response(
                (
                    "Title: Reader Title\n"
                    "URL Source: https://example.com/blocked\n\n"
                    "Markdown Content:\n"
                    "This is the extracted body."
                ).encode("utf-8"),
                "https://r.jina.ai/https://example.com/blocked",
                headers={"Content-Type": "text/plain"},
            ),
        ]

        result = fetch_url_as_text("https://example.com/blocked")

        self.assertEqual(result.title, "Reader Title")
        self.assertEqual(result.body, "This is the extracted body.")
        self.assertEqual(result.metadata.get("fetch_mode"), "reader_proxy")

    @staticmethod
    def _mock_response(body: bytes, url: str, headers=None):
        class _Response:
            def __init__(self, body: bytes, url: str, headers):
                self._body = body
                self._url = url
                self.headers = headers or {}

            def read(self) -> bytes:
                return self._body

            def geturl(self) -> str:
                return self._url

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        return _Response(body, url, headers)
