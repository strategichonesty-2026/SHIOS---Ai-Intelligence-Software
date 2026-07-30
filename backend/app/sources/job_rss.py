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


# Default job RSS feeds — verified working, no API key needed
DEFAULT_JOB_FEEDS = [
    # Arbeitnow — remote + relocation tech jobs RSS (verified working)
    "https://www.arbeitnow.com/api/job-board-api",
    # Jobicy — remote-only tech jobs RSS (verified working)
    "https://jobicy.com/?feed=job_feed&job_categories=dev-engineer&remote=1",
    # Jobicy — data/ML/AI roles
    "https://jobicy.com/?feed=job_feed&job_categories=data-science&remote=1",
    # Remotive — remote tech jobs RSS (verified working)
    "https://remotive.com/remote-jobs/feed/software-dev",
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
                    "Accept": "application/json, application/rss+xml, application/xml, text/xml, */*",
                },
                timeout=20.0,
                follow_redirects=True,
            )
        except Exception as exc:
            raise SourceUnavailable(f"feed unreachable: {exc}") from exc

        if response.status_code == 429:
            raise RateLimitExceeded(f"rate limited by {feed_url}")
        if not response.is_success:
            raise SourceUnavailable(f"feed returned HTTP {response.status_code}")

        # Handle JSON job feeds (e.g. Arbeitnow)
        content_type = response.headers.get("content-type", "")
        if "json" in content_type or response.text.strip().startswith("{"):
            return self._parse_json_feed(response.text, limit, seen_ids)

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

    def _parse_json_feed(self, text: str, limit: int, seen_ids: set[str]) -> list[CollectedItem]:
        import json
        try:
            data = json.loads(text)
        except Exception:
            return []

        jobs = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(jobs, list):
            return []

        items: list[CollectedItem] = []
        for job in jobs[:limit]:
            entry_id = str(job.get("slug") or job.get("id") or job.get("url") or "")
            if not entry_id or entry_id in seen_ids:
                continue
            seen_ids.add(entry_id)

            title = _strip(job.get("title") or job.get("position") or "").strip()
            company = _strip(job.get("company_name") or job.get("company") or "").strip()
            if not title:
                continue

            description = _strip(job.get("description") or "")
            tags = job.get("tags") or job.get("keywords") or []
            url = job.get("url") or job.get("apply_url") or ""

            content_parts = [f"{title} at {company}" if company else title]
            content_parts.append("Location: Remote")
            if description:
                content_parts.append(description[:1500])
            if tags:
                content_parts.append(f"Skills: {', '.join(str(t) for t in tags[:10])}")

            items.append(CollectedItem(
                external_id=entry_id,
                content="\n\n".join(content_parts),
                doc_type="job",
                observed_at=datetime.now(UTC),
                metadata={
                    "title": title,
                    "company": company or None,
                    "location": "Remote",
                    "remote_type": "remote",
                    "url": url,
                    "salary_min": None,
                    "salary_max": None,
                    "skills": [str(t) for t in tags[:10]],
                    "synthetic": False,
                },
            ))
        return items
