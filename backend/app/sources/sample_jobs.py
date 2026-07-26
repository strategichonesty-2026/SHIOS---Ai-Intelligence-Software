"""Deterministic job-market source.

Why this exists: a fresh install has no history, and a trend engine with no history has
nothing honest to say. This source generates a reproducible 12-week posting history so the
full loop — trend, prediction, reality check, learning — is demonstrable on first run and
assertable in tests. It is seeded, so two runs produce identical data.

It is clearly labelled `sample_jobs` in every record it writes. Nothing downstream treats it
as authoritative; disable it by removing it from ENABLED_SOURCES.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from app.sources.base import CollectedItem, Source

COMPANIES = [
    "Northwind Health",
    "Cedar Systems",
    "Lakeline Financial",
    "Granite Labs",
    "Blue Harbor Logistics",
    "Meridian Retail",
]

# (role title, skill phrases, technology phrases, weekly base volume, weekly growth)
ROLE_PROFILES = [
    (
        "Senior Scrum Master",
        ["agile", "scrum", "coaching", "stakeholder", "risk management"],
        ["jira", "azure"],
        6,
        0.35,
    ),
    (
        "Technical Program Manager",
        ["program management", "stakeholder", "budget", "risk register"],
        ["jira", "aws", "python"],
        5,
        0.55,
    ),
    (
        "AI Engineer",
        ["prompt engineering", "generative ai", "machine learning", "automation"],
        ["python", "langchain", "anthropic", "aws"],
        4,
        1.20,
    ),
    (
        "Agile Coach",
        ["agile coach", "coaching", "change management", "facilitation"],
        ["jira"],
        4,
        -0.25,
    ),
    (
        "Platform Engineer",
        ["cloud architecture", "automation", "security"],
        ["kubernetes", "terraform", "docker", "aws"],
        5,
        0.30,
    ),
    (
        "Data Scientist",
        ["data analysis", "machine learning", "sql"],
        ["python", "databricks", "snowflake"],
        5,
        0.10,
    ),
]

TEMPLATE = """{seniority} {title} — {company} ({location}, {remote})

About the role
{company} is hiring a {seniority} {title} to lead delivery across product and platform teams.
You will own outcomes end to end, keep executive stakeholders informed, and raise the bar for
how the team works.

What you will do
{bullets}

What we look for
- Demonstrated experience in {skills_line}.
- Working familiarity with {tech_line}.
- Clear written communication and comfort operating without perfect information.

Compensation: ${salary_low},000 - ${salary_high},000 depending on experience.
Posted {posted}."""

LOCATIONS = [
    ("Minneapolis, MN", "hybrid"),
    ("Remote, US", "remote"),
    ("Chicago, IL", "onsite"),
    ("Austin, TX", "hybrid"),
    ("Remote, US", "remote"),
]

SENIORITY = ["Senior", "Lead", "Principal", "Senior", "Mid-level"]


class SampleJobsSource(Source):
    source_id = "sample_jobs"
    doc_type = "job"

    def __init__(self, weeks: int = 12, seed: int = 20260725) -> None:
        self.weeks = weeks
        self.seed = seed

    def collect(self, limit: int = 500) -> list[CollectedItem]:
        rng = random.Random(self.seed)
        today = datetime.now(UTC)
        # Anchor to the most recent Monday so week boundaries are stable.
        anchor = today - timedelta(days=today.weekday())
        items: list[CollectedItem] = []

        for week_offset in range(self.weeks, 0, -1):
            week_start = anchor - timedelta(weeks=week_offset - 1)
            elapsed = self.weeks - week_offset
            for title, skills, techs, base, growth in ROLE_PROFILES:
                volume = max(1, round(base + growth * elapsed + rng.uniform(-1.0, 1.0)))
                for n in range(volume):
                    posted = week_start + timedelta(days=rng.randint(0, 6), hours=rng.randint(8, 18))
                    if posted > today:
                        posted = today - timedelta(hours=1)
                    company = rng.choice(COMPANIES)
                    location, remote = rng.choice(LOCATIONS)
                    seniority = rng.choice(SENIORITY)
                    picked_skills = rng.sample(skills, k=min(len(skills), rng.randint(3, len(skills))))
                    picked_tech = rng.sample(techs, k=min(len(techs), rng.randint(1, len(techs))))
                    salary_low = rng.choice([110, 125, 140, 155])
                    content = TEMPLATE.format(
                        seniority=seniority,
                        title=title,
                        company=company,
                        location=location,
                        remote=remote,
                        bullets="\n".join(f"- Apply {s} to day-to-day delivery." for s in picked_skills),
                        skills_line=", ".join(picked_skills),
                        tech_line=", ".join(picked_tech),
                        salary_low=salary_low,
                        salary_high=salary_low + 35,
                        posted=posted.date().isoformat(),
                    )
                    external_id = f"{title}-{company}-{posted.date().isoformat()}-{n}".replace(" ", "_")
                    items.append(
                        CollectedItem(
                            external_id=external_id,
                            content=content,
                            doc_type="job",
                            observed_at=posted,
                            metadata={
                                "title": f"{seniority} {title}",
                                "company": company,
                                "location": location,
                                "remote_type": remote,
                                "synthetic": True,
                            },
                        )
                    )
        # A limit should trim the *oldest* history, never the most recent weeks: downstream
        # trend and forecast logic depends on the latest periods being complete.
        items.sort(key=lambda i: i.observed_at)
        return items[-limit:] if limit and len(items) > limit else items
