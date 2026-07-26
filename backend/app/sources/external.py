"""Live external sources: RSS/news, GitHub, Gmail (LinkedIn job alerts).

All three fail soft with automatic retry and exponential backoff. A source
that exhausts its retries raises SourceUnavailable; the Collector Agent
records `document.collection_failed` with retry_count in the payload, and
the rest of the loop continues on the sources that did work.

Gmail adds OAuth token refresh on top of the common retry wrapper so that
an expired token is refreshed once and the request retried transparently.
"""

from __future__ import annotations

import base64
import logging
import re
import time
from datetime import UTC, datetime

import httpx

from app.config import settings
from app.sources.base import CollectedItem, RateLimitExceeded, Source, SourceUnavailable

log = logging.getLogger("shios.sources")

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(value: str) -> str:
    return _TAG_RE.sub(" ", value or "").replace("&nbsp;", " ").strip()


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------

def _with_retry(fn, *, source_id: str):
    """Call fn() with exponential backoff.

    - RateLimitExceeded is never retried (the upstream told us to back off).
    - SourceUnavailable and any other exception are retried up to
      settings.source_max_retries times with exponential backoff starting at
      settings.source_backoff_seconds.
    - Raises SourceUnavailable with retry_count attached on final failure.
    """
    max_retries = settings.source_max_retries
    backoff = settings.source_backoff_seconds
    last_exc: Exception = SourceUnavailable("unknown error")

    for attempt in range(max_retries + 1):
        try:
            return fn()
        except RateLimitExceeded:
            raise  # never retry rate limits
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                wait = backoff * (2 ** attempt)
                log.warning(
                    "source=%s attempt=%d/%d failed, retrying in %.1fs: %s",
                    source_id, attempt + 1, max_retries, wait, exc,
                )
                time.sleep(wait)
            else:
                log.error(
                    "source=%s exhausted %d retries: %s",
                    source_id, max_retries, exc,
                )

    err = SourceUnavailable(str(last_exc))
    err.retry_count = max_retries  # type: ignore[attr-defined]
    raise err


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

class RSSSource(Source):
    source_id = "rss"
    doc_type = "article"

    def __init__(self, feeds: list[str] | None = None) -> None:
        self.feeds = feeds if feeds is not None else settings.rss_feed_list

    def is_configured(self) -> bool:
        return bool(self.feeds)

    def collect(self, limit: int = 100) -> list[CollectedItem]:
        try:
            import feedparser  # lazy — keeps the package optional
        except ImportError as exc:  # pragma: no cover
            raise SourceUnavailable("feedparser is not installed") from exc

        items: list[CollectedItem] = []
        for feed_url in self.feeds:
            try:
                items.extend(_with_retry(
                    lambda url=feed_url: self._fetch_feed(url, feedparser, limit),
                    source_id=self.source_id,
                ))
            except RateLimitExceeded:
                raise
            except SourceUnavailable as exc:
                log.warning("rss feed gave up url=%s retries=%s", feed_url,
                            getattr(exc, "retry_count", "?"))
                continue
            if len(items) >= limit:
                break
        return items[:limit]

    def _fetch_feed(self, feed_url: str, feedparser, limit: int) -> list[CollectedItem]:
        response = httpx.get(
            feed_url,
            timeout=settings.source_timeout_seconds,
            follow_redirects=True,
        )
        if response.status_code == 429:
            raise RateLimitExceeded(f"rate limited by {feed_url}")
        response.raise_for_status()
        parsed = feedparser.parse(response.text)
        items: list[CollectedItem] = []
        for entry in parsed.entries[:limit]:
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            observed = (
                datetime(*published[:6], tzinfo=UTC) if published else datetime.now(UTC)
            )
            summary = strip_html(entry.get("summary", ""))
            title = entry.get("title", "untitled")
            items.append(
                CollectedItem(
                    external_id=entry.get("id") or entry.get("link") or f"{feed_url}:{title}",
                    content=f"{title}\n\n{summary}",
                    doc_type="article",
                    observed_at=observed,
                    metadata={"title": title, "link": entry.get("link"), "feed": feed_url},
                )
            )
        return items


class GitHubSource(Source):
    """Repository momentum by topic — a leading indicator for technology adoption."""

    source_id = "github"
    doc_type = "repo"

    def __init__(self, topics: list[str] | None = None) -> None:
        self.topics = topics if topics is not None else settings.github_topic_list

    def is_configured(self) -> bool:
        return bool(self.topics)

    def collect(self, limit: int = 100) -> list[CollectedItem]:
        headers = {"Accept": "application/vnd.github+json"}
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"

        items: list[CollectedItem] = []
        per_topic = max(1, limit // max(1, len(self.topics)))
        for topic in self.topics:
            try:
                batch = _with_retry(
                    lambda t=topic: self._fetch_topic(t, headers, per_topic),
                    source_id=self.source_id,
                )
                items.extend(batch)
            except RateLimitExceeded:
                raise
            except SourceUnavailable as exc:
                log.warning("github topic gave up topic=%s retries=%s", topic,
                            getattr(exc, "retry_count", "?"))
                continue
        return items[:limit]

    def _fetch_topic(self, topic: str, headers: dict, per_page: int) -> list[CollectedItem]:
        response = httpx.get(
            "https://api.github.com/search/repositories",
            params={"q": f"topic:{topic}", "sort": "updated", "per_page": per_page},
            headers=headers,
            timeout=settings.source_timeout_seconds,
        )
        if response.status_code == 403:
            raise RateLimitExceeded("github search rate limit reached")
        response.raise_for_status()
        items: list[CollectedItem] = []
        for repo in response.json().get("items", []):
            pushed = repo.get("pushed_at") or repo.get("updated_at")
            observed = (
                datetime.fromisoformat(pushed.replace("Z", "+00:00"))
                if pushed
                else datetime.now(UTC)
            )
            content = (
                f"{repo.get('full_name')}\n\n{repo.get('description') or ''}\n\n"
                f"Topics: {', '.join(repo.get('topics', []))}\n"
                f"Language: {repo.get('language') or 'unknown'}\n"
                f"Stars: {repo.get('stargazers_count', 0)}"
            )
            items.append(
                CollectedItem(
                    external_id=str(repo.get("id")),
                    content=content,
                    doc_type="repo",
                    observed_at=observed,
                    metadata={
                        "title": repo.get("full_name"),
                        "topic": topic,
                        "stars": repo.get("stargazers_count", 0),
                        "language": repo.get("language"),
                    },
                )
            )
        return items


class GmailSource(Source):
    """LinkedIn job alerts arriving by email.

    Adds OAuth token refresh on top of the standard retry wrapper. When the
    Google client raises an auth error the token is refreshed once and the
    listing call retried before the retry wrapper counts it as a failure.
    """

    source_id = "gmail_linkedin_jobs"
    doc_type = "email"

    def is_configured(self) -> bool:
        return bool(settings.gmail_credentials_json)

    def collect(self, limit: int = 100) -> list[CollectedItem]:
        if not self.is_configured():
            raise SourceUnavailable("gmail credentials not configured")
        return _with_retry(
            lambda: self._collect_once(limit),
            source_id=self.source_id,
        )

    def _collect_once(self, limit: int) -> list[CollectedItem]:  # pragma: no cover
        try:
            import json

            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise SourceUnavailable("google-api-python-client is not installed") from exc

        try:
            info = json.loads(settings.gmail_credentials_json or "{}")
            creds = Credentials.from_authorized_user_info(
                info, ["https://www.googleapis.com/auth/gmail.readonly"]
            )
            # Refresh token if expired — this is the core of the OAuth hardening.
            if creds.expired and creds.refresh_token:
                log.info("gmail: access token expired, refreshing")
                creds.refresh(Request())
                log.info("gmail: token refreshed successfully")

            service = build("gmail", "v1", credentials=creds, cache_discovery=False)
            listing = (
                service.users()
                .messages()
                .list(userId="me", q=settings.gmail_query, maxResults=limit)
                .execute()
            )
        except ImportError:
            raise
        except Exception as exc:
            raise SourceUnavailable(f"gmail unavailable: {exc}") from exc

        items: list[CollectedItem] = []
        for ref in listing.get("messages", []):
            message = (
                service.users().messages().get(userId="me", id=ref["id"], format="full").execute()
            )
            headers = {
                h["name"].lower(): h["value"]
                for h in message["payload"].get("headers", [])
            }
            body = _extract_gmail_body(message["payload"])
            items.append(
                CollectedItem(
                    external_id=ref["id"],
                    content=f"{headers.get('subject', '')}\n\n{strip_html(body)}",
                    doc_type="email",
                    observed_at=datetime.fromtimestamp(
                        int(message.get("internalDate", 0)) / 1000, tz=UTC
                    ),
                    metadata={
                        "title": headers.get("subject", ""),
                        "from": headers.get("from", ""),
                    },
                )
            )
        return items


def _extract_gmail_body(payload: dict) -> str:  # pragma: no cover - live API
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "ignore")
    for part in payload.get("parts", []):
        text = _extract_gmail_body(part)
        if text:
            return text
    return ""
