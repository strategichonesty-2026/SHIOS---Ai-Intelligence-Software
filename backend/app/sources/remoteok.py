"""RemoteOK job source — real job postings, no API key required.

RemoteOK publishes a free JSON API at https://remoteok.com/api that returns
the latest remote job postings. No authentication is needed. Rate limiting
is handled by the standard retry wrapper in external.py.

Each job becomes a CollectedItem with doc_type="job" and synthetic=False,
so the "Demo data" banner disappears automatically once this source is active.

Enable by adding "remoteok" to ENABLED_SOURCES in Railway environment variables,
and removing "sample_jobs" from the same list.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from app.sources.base import CollectedItem, RateLimitExceeded, Source, SourceUnavailable

log = logging.getLogger("shios.sources.remoteok")

REMOTEOK_API = "https://remoteok.com/api"

# Tags to filter for — only collect jobs relevant to the tech/data/AI job market
RELEVANT_TAGS = {
    "python", "javascript", "typescript", "react", "node", "java", "golang", "rust",
    "data", "ml", "ai", "llm", "devops", "cloud", "aws", "gcp", "azure", "backend",
    "frontend", "fullstack", "engineer", "developer", "senior", "lead", "manager",
    "product", "design", "analytics", "sql", "postgres", "docker", "kubernetes",
    "agile", "scrum", "remote", "api", "saas", "startup",
}


class RemoteOKSource(Source):
    """Real remote job postings from RemoteOK — no API key required."""

    source_id = "remoteok"
    doc_type = "job"

    def is_configured(self) -> bool:
        return True  # no credentials needed

    def collect(self, limit: int = 200) -> list[CollectedItem]:
        try:
            response = httpx.get(
                REMOTEOK_API,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://remoteok.com/",
                },
                timeout=30.0,
                follow_redirects=True,
            )
        except Exception as exc:
            raise SourceUnavailable(f"RemoteOK unreachable: {exc}") from exc

        if response.status_code == 429:
            raise RateLimitExceeded("RemoteOK rate limit reached")
        if response.status_code == 403:
            raise SourceUnavailable(f"RemoteOK blocked this server (HTTP 403) — try again later or use a different job source")
        if not response.is_success:
            raise SourceUnavailable(f"RemoteOK returned HTTP {response.status_code}: {response.text[:200]}")

        try:
            raw = response.json()
        except Exception as exc:
            raise SourceUnavailable(f"RemoteOK returned invalid JSON: {exc}") from exc

        # First item is always a legal/meta notice — skip it
        jobs = [j for j in raw if isinstance(j, dict) and j.get("id") and j.get("position")]

        items: list[CollectedItem] = []
        for job in jobs[:limit]:
            try:
                item = self._to_item(job)
                if item:
                    items.append(item)
            except Exception as exc:
                log.debug("skipping job id=%s: %s", job.get("id"), exc)
                continue

        log.info("remoteok: collected %d jobs", len(items))
        return items

    def _to_item(self, job: dict) -> CollectedItem | None:
        position = (job.get("position") or "").strip()
        company = (job.get("company") or "").strip()
        if not position or not company:
            return None

        tags = [t.lower() for t in (job.get("tags") or []) if isinstance(t, str)]
        location = (job.get("location") or "remote").strip()
        url = job.get("url") or f"https://remoteok.com/l/{job['id']}"
        description = (job.get("description") or "").strip()
        salary_min = job.get("salary_min")
        salary_max = job.get("salary_max")

        # Parse date — RemoteOK uses ISO format or Unix timestamp
        date_raw = job.get("date") or job.get("epoch")
        observed_at: datetime
        if isinstance(date_raw, int | float):
            observed_at = datetime.fromtimestamp(date_raw, tz=UTC)
        elif isinstance(date_raw, str):
            try:
                observed_at = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
            except ValueError:
                observed_at = datetime.now(UTC)
        else:
            observed_at = datetime.now(UTC)

        # Build content text for extraction — position + company + description + tags
        content_parts = [
            f"{position} at {company}",
            f"Location: {location}",
        ]
        if salary_min and salary_max:
            content_parts.append(f"Salary: ${salary_min:,}–${salary_max:,}")
        if description:
            # Truncate to 2000 chars — enough for entity extraction
            content_parts.append(description[:2000])
        if tags:
            content_parts.append(f"Skills: {', '.join(tags)}")

        return CollectedItem(
            external_id=str(job["id"]),
            content="\n\n".join(content_parts),
            doc_type="job",
            observed_at=observed_at,
            metadata={
                "title": position,
                "company": company,
                "location": location,
                "remote_type": "remote",
                "salary_min": int(salary_min) if salary_min else None,
                "salary_max": int(salary_max) if salary_max else None,
                "skills": tags,
                "url": url,
                "synthetic": False,  # real data — hides the demo banner
            },
        )
