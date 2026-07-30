"""Job RSS source — parses public job board RSS feeds as real job postings.

LinkedIn, Indeed, and other job boards publish public RSS feeds that don't
require API keys. Each entry is parsed as doc_type="job" with synthetic=False
so it counts as real market signal and clears the demo data banner.

Default feeds cover remote tech/AI/data roles. Add more via JOB_RSS_FEEDS
environment variable (comma-separated URLs).

LinkedIn RSS format:
  https://www.linkedin.com/jobs/search/?keywords=python&location=Remote&f_WT=2&f_TPR=r604800

Indeed RSS format:
  https://www.indeed.com/rss?q=software+engineer&l=remote&sort=date
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

import httpx

from app.config import settings
from app.sources.base import CollectedItem, RateLimitExceeded, Source, SourceUnavailable

log = logging.getLogger("shios.sources.job_rss")

_TAG_RE = re.compile(r"<[^>]+>")


def _strip(text: str) -> str:
    return _TAG_RE.sub(" ", text or "").replace("&nbsp;", " ").replace("&amp;", "&").strip()


# Default job RSS feeds — public, no key needed
DEFAULT_JOB_FEEDS = [
    # Indeed remote tech jobs
    "https://www.indeed.com/rss?q=software+engineer+OR+data+engineer+OR+AI+engineer&l=remote&sort=date&limit=50",
    # Indeed remote data/ML jobs
    "https://www.indeed.com/rss?q=machine+learning+OR+data+scientist+OR+LLM&l=remote&sort=date&limit=50",
    # LinkedIn remote engineering jobs (public RSS)
    "https://www.linkedin.com/jobs/search/?keywords=software+engineer&location=Remote&f_WT=2&f_TPR=r604800&format=rss",
]


class JobRSSSource(Source):
    """Real job postings from public RSS feeds — no API key required."""

    source_id = "job_rss"
    doc_type = "job"

    def __init__(self, feeds: list[str] | None = None) -> None:
        # Allow override via env var JOB_RSS_FEEDS
        env_feeds = getattr(settings, "job_rss_feeds", None)
        if feeds is not None:
            self.feeds = feeds
        elif env_feeds:
            self.feeds = [f.strip() for f in env_feeds.split(",") if f.strip()]
        else:
            self.feeds = DEFAULT_JOB_FEEDS

    def is_configured(self) -> bool:
        return bool(self.feeds)

    def collect(self, limit: int = 200) -> list[CollectedItem]:
        try:
            import feedparser
        except ImportError as exc:
            raise SourceUnavailable("feedparser is not installed") from exc

        items: list[CollectedItem] = []
        seen_ids: set[str] = set()
        per_feed = max(1, limit // max(1, len(self.feeds)))

        for feed_url in self.feeds:
            try:
                batch = self._fetch_feed(feed_url, feedparser, per_feed, seen_ids)
                items.extend(batch)
                log.info("job_rss: feed=%s collected=%d", feed_url[:60], len(batch))
            except RateLimitExceeded:
                raise
            except Exception as exc:
                log.warning("job_rss: feed=%s failed: %s", feed_url[:60], exc)
                continue

        log.info("job_rss: total collected=%d", len(items))
        return items[:limit]

    def _fetch_feed(
        self,
        feed_url: str,
        feedparser,
        limit: int,
        seen_ids: set[str],
    ) -> list[CollectedItem]:
        try:
            response = httpx.get(
                feed_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; job-market-research-bot/1.0)",
                    "Accept": "application/rss+xml, application/xml, text/xml, */*",
                },
                timeout=20.0,
                follow_redirects=True,
            )
        except Exception as exc:
            raise SourceUnavailable(f"feed unreachable: {exc}") from exc

        if response.status_code == 429:
            raise RateLimitExceeded(f"rate limited by {feed_url}")
        if not response.ok:
            raise SourceUnavailable(f"feed returned HTTP {response.status_code}")

        parsed = feedparser.parse(response.text)
        items: list[CollectedItem] = []

        for entry in parsed.entries[:limit]:
            entry_id = entry.get("id") or entry.get("link") or ""
            if not entry_id or entry_id in seen_ids:
                continue
            seen_ids.add(entry_id)

            title = _strip(entry.get("title", "")).strip()
            if not title:
                continue

            # Parse date
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            observed_at = (
                datetime(*published[:6], tzinfo=UTC) if published else datetime.now(UTC)
            )

            # Build content for entity extraction
            summary = _strip(entry.get("summary", "") or entry.get("description", ""))
            company = _strip(entry.get("author", "") or "")
            link = entry.get("link", "")

            # Try to extract company from title (common pattern: "Job Title at Company")
            if not company and " at " in title:
                parts = title.rsplit(" at ", 1)
                if len(parts) == 2:
                    company = parts[1].strip()

            content_parts = [title]
            if company:
                content_parts.append(f"Company: {company}")
            content_parts.append("Location: Remote")
            if summary:
                content_parts.append(summary[:1500])

            items.append(
                CollectedItem(
                    external_id=entry_id,
                    content="\n\n".join(content_parts),
                    doc_type="job",
                    observed_at=observed_at,
                    metadata={
                        "title": title,
                        "company": company or None,
                        "location": "Remote",
                        "remote_type": "remote",
                        "url": link,
                        "salary_min": None,
                        "salary_max": None,
                        "skills": [],
                        "synthetic": False,
                    },
                )
            )

        return items
