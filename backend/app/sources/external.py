"""Live external sources: RSS/news, GitHub, Gmail (LinkedIn job alerts).

All three fail soft: a source that cannot reach its upstream raises SourceUnavailable, the
Collector Agent records `document.collection_failed`, and the rest of the loop continues on
the sources that did work. One dead feed must never stop the system.
"""

from __future__ import annotations

import base64
import logging
import re
from datetime import UTC, datetime

import httpx

from app.config import settings
from app.sources.base import CollectedItem, RateLimitExceeded, Source, SourceUnavailable

log = logging.getLogger("shios.sources")

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(value: str) -> str:
    return _TAG_RE.sub(" ", value or "").replace("&nbsp;", " ").strip()


class RSSSource(Source):
    source_id = "rss"
    doc_type = "article"

    def __init__(self, feeds: list[str] | None = None) -> None:
        self.feeds = feeds if feeds is not None else settings.rss_feed_list

    def is_configured(self) -> bool:
        return bool(self.feeds)

    def collect(self, limit: int = 100) -> list[CollectedItem]:
        try:
            import feedparser  # imported lazily so the package stays optional
        except ImportError as exc:  # pragma: no cover
            raise SourceUnavailable("feedparser is not installed") from exc

        items: list[CollectedItem] = []
        for feed_url in self.feeds:
            try:
                response = httpx.get(feed_url, timeout=20, follow_redirects=True)
                if response.status_code == 429:
                    raise RateLimitExceeded(f"rate limited by {feed_url}")
                response.raise_for_status()
                parsed = feedparser.parse(response.text)
            except RateLimitExceeded:
                raise
            except Exception as exc:
                log.warning("rss feed failed url=%s error=%s", feed_url, exc)
                continue

            for entry in parsed.entries[:limit]:
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                observed = (
                    datetime(*published[:6], tzinfo=UTC)
                    if published
                    else datetime.now(UTC)
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
                if len(items) >= limit:
                    return items
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
                response = httpx.get(
                    "https://api.github.com/search/repositories",
                    params={"q": f"topic:{topic}", "sort": "updated", "per_page": per_topic},
                    headers=headers,
                    timeout=20,
                )
                if response.status_code == 403:
                    raise RateLimitExceeded("github search rate limit reached")
                response.raise_for_status()
            except RateLimitExceeded:
                raise
            except Exception as exc:
                log.warning("github topic failed topic=%s error=%s", topic, exc)
                continue

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
        return items[:limit]


class GmailSource(Source):
    """LinkedIn job alerts arriving by email.

    Requires a Google service-account or OAuth credential JSON in GMAIL_CREDENTIALS_JSON.
    Unconfigured is a normal state, not an error — the source simply reports itself as
    unconfigured and the Collector skips it.
    """

    source_id = "gmail_linkedin_jobs"
    doc_type = "email"

    def is_configured(self) -> bool:
        return bool(settings.gmail_credentials_json)

    def collect(self, limit: int = 100) -> list[CollectedItem]:
        if not self.is_configured():
            raise SourceUnavailable("gmail credentials not configured")
        try:  # pragma: no cover - requires live Google credentials
            import json

            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            info = json.loads(settings.gmail_credentials_json or "{}")
            creds = Credentials.from_authorized_user_info(
                info, ["https://www.googleapis.com/auth/gmail.readonly"]
            )
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)
            listing = (
                service.users()
                .messages()
                .list(userId="me", q=settings.gmail_query, maxResults=limit)
                .execute()
            )
        except ImportError as exc:
            raise SourceUnavailable("google-api-python-client is not installed") from exc
        except Exception as exc:
            raise SourceUnavailable(f"gmail unavailable: {exc}") from exc

        items: list[CollectedItem] = []
        for ref in listing.get("messages", []):  # pragma: no cover - live API
            message = service.users().messages().get(userId="me", id=ref["id"], format="full").execute()
            headers = {h["name"].lower(): h["value"] for h in message["payload"].get("headers", [])}
            body = _extract_gmail_body(message["payload"])
            items.append(
                CollectedItem(
                    external_id=ref["id"],
                    content=f"{headers.get('subject', '')}\n\n{strip_html(body)}",
                    doc_type="email",
                    observed_at=datetime.fromtimestamp(
                        int(message.get("internalDate", 0)) / 1000, tz=UTC
                    ),
                    metadata={"title": headers.get("subject", ""), "from": headers.get("from", "")},
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
