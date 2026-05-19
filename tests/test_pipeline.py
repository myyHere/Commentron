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
from news_comment_agent.ingestion import fetch_url_as_text
from news_comment_agent.models import NewsInput
from news_comment_agent.backends import RuntimeSettings
from news_comment_agent.pipeline import run_pipeline
from news_comment_agent.reddit_retrieval import retrieve_reference_comments


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

    def test_pipeline_returns_best_comment(self):
        result = run_pipeline(self._policy_input(), settings=RuntimeSettings())

        self.assertEqual(result.understanding.category, "policy")
        self.assertTrue(result.reference_comments)
        self.assertTrue(result.best_comment.body)
        self.assertGreaterEqual(len(result.candidate_comments), 4)

    @patch("news_comment_agent.reddit_retrieval.build_opener")
    def test_retrieve_reference_comments_uses_live_reddit_results(self, mock_build_opener):
        temp_path = ROOT / "tests" / "tmp_reddit_config.json"
        temp_path.write_text(
            '{\n'
            '  "reddit": {\n'
            '    "user_agent": "CommentronTest/0.1",\n'
            '    "search_limit": 2,\n'
            '    "comment_limit": 2\n'
            '  }\n'
            '}',
            encoding="utf-8",
        )
        mock_opener = mock_build_opener.return_value
        mock_opener.open.side_effect = [
            self._mock_response(
                (
                    '<html><body>'
                    '<a href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.reddit.com%2Fr%2Feconomics%2Fcomments%2Fpost123%2Fpolicy_carveout_debate%2F">'
                    'result</a>'
                    '</body></html>'
                ).encode("utf-8"),
                "https://html.duckduckgo.com/html/?q=policy",
                headers={"Content-Type": "text/html"},
            ),
            self._mock_response(
                (
                    "Title: Policy carveout debate\n"
                    "URL Source: https://www.reddit.com/r/economics/comments/post123/policy_carveout_debate/\n\n"
                    "Markdown Content:\n"
                    "How much of this is actual policy reform versus giant-company fee paying?\n"
                    "Markets pricing in special treatment is the joke and the thesis.\n"
                ).encode("utf-8"),
                "https://r.jina.ai/https://www.reddit.com/r/economics/comments/post123/policy_carveout_debate",
                headers={"Content-Type": "text/plain"},
            ),
        ]

        try:
            comments = retrieve_reference_comments(self._policy_input(), limit=2, config_path=str(temp_path))
        finally:
            temp_path.unlink(missing_ok=True)

        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0].subreddit, "economics")

    @patch("news_comment_agent.reddit_retrieval.build_opener")
    def test_retrieve_reference_comments_falls_back_to_local_samples_on_network_error(self, mock_build_opener):
        mock_opener = mock_build_opener.return_value
        mock_opener.open.side_effect = URLError("[Errno 111] Connection refused")

        comments = retrieve_reference_comments(self._policy_input(), limit=2)

        self.assertEqual(len(comments), 2)
        self.assertTrue(any(comment.subreddit == "wallstreetbets" for comment in comments))

    def test_openai_backend_requires_api_key(self):
        with self.assertRaises(RuntimeError):
            run_pipeline(
                self._policy_input(),
                settings=RuntimeSettings(backend_name="openai", api_key=None),
            )

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
            '    "proxy": "http://127.0.0.1:8080"\n'
            '  },\n'
            '  "reddit": {\n'
            '    "user_agent": "CommentronTest/0.1",\n'
            '    "search_limit": 9,\n'
            '    "comment_limit": 7\n'
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
        self.assertEqual(config.api_key, "test-key")
        self.assertEqual(config.reddit_search_limit, 9)

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

    @patch("news_comment_agent.ingestion.build_opener")
    def test_unknown_url_raises_actionable_error(self, mock_build_opener):
        mock_opener = mock_build_opener.return_value
        mock_opener.open.side_effect = [
            URLError("[Errno 111] Connection refused"),
            URLError("[Errno 111] Connection refused"),
        ]

        with self.assertRaises(RuntimeError) as ctx:
            fetch_url_as_text("https://example.com/news")

        self.assertIn("No article analysis was produced from this URL", str(ctx.exception))

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
        self.assertEqual(result.metadata.get("fetch_mode"), "zhihu_answer_api")

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
