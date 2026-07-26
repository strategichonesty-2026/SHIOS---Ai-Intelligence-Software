"""Career-intelligence taxonomy.

Deliberately a flat, editable dictionary rather than an ontology. Section 0 of the spec calls
out "no perfect ontology" as a non-goal; this is the smallest thing that produces countable,
auditable entities. Extend by editing the lists — no migration required.
"""

from __future__ import annotations

import re

SKILLS: dict[str, list[str]] = {
    "agile delivery": ["agile", "scrum", "kanban", "safe framework", "sprint planning"],
    "product ownership": ["product owner", "backlog", "roadmap ownership"],
    "program management": ["program management", "pgmp", "portfolio management"],
    "stakeholder management": ["stakeholder", "executive communication"],
    "risk management": ["risk management", "risk register", "raid log"],
    "change management": ["change management", "organizational change", "prosci"],
    "data analysis": ["data analysis", "analytics", "sql", "dashboarding"],
    "ai literacy": ["prompt engineering", "generative ai", "llm", "ai literacy", "genai"],
    "machine learning": ["machine learning", "deep learning", "model training", "mlops"],
    "cloud architecture": ["cloud architecture", "aws", "azure", "gcp", "kubernetes"],
    "security": ["security", "compliance", "soc 2", "zero trust"],
    "coaching": ["coaching", "mentoring", "facilitation"],
    "financial acumen": ["budget", "forecasting", "p&l", "cost management"],
    "automation": ["automation", "ci/cd", "workflow automation", "rpa"],
}

TECHNOLOGIES: dict[str, list[str]] = {
    "python": ["python"],
    "typescript": ["typescript", "javascript"],
    "react": ["react", "next.js"],
    "postgresql": ["postgresql", "postgres"],
    "kubernetes": ["kubernetes", "k8s"],
    "aws": ["aws", "amazon web services"],
    "azure": ["azure"],
    "gcp": ["gcp", "google cloud"],
    "jira": ["jira", "atlassian"],
    "snowflake": ["snowflake"],
    "databricks": ["databricks"],
    "langchain": ["langchain"],
    "openai api": ["openai api", "gpt-4", "gpt-5"],
    "anthropic api": ["anthropic", "claude api"],
    "terraform": ["terraform"],
    "docker": ["docker"],
}

ROLES: dict[str, list[str]] = {
    "scrum master": ["scrum master"],
    "agile coach": ["agile coach", "enterprise coach"],
    "product manager": ["product manager", "product owner"],
    "program manager": ["program manager", "technical program manager", "tpm"],
    "project manager": ["project manager"],
    "data scientist": ["data scientist"],
    "ml engineer": ["machine learning engineer", "ml engineer", "ai engineer"],
    "software engineer": ["software engineer", "developer", "sde"],
    "platform engineer": ["platform engineer", "devops engineer", "sre"],
    "engineering manager": ["engineering manager", "director of engineering"],
}

SENIORITY_PATTERNS: list[tuple[str, str]] = [
    ("principal", r"\bprincipal\b|\bdistinguished\b"),
    ("director", r"\bdirector\b|\bhead of\b|\bvp\b"),
    ("lead", r"\blead\b|\bstaff\b"),
    ("senior", r"\bsenior\b|\bsr\.?\b"),
    ("junior", r"\bjunior\b|\bjr\.?\b|\bassociate\b|\bentry[- ]level\b"),
    ("mid", r"\bmid[- ]level\b|\bii\b"),
]

REMOTE_PATTERNS: list[tuple[str, str]] = [
    ("remote", r"\bremote\b|\bwork from home\b|\bdistributed team\b"),
    ("hybrid", r"\bhybrid\b"),
    ("onsite", r"\bon[- ]?site\b|\bin[- ]office\b"),
]

SALARY_RE = re.compile(r"\$\s?(\d{2,3})(?:,\d{3}|k)\s*(?:-|to|–)\s*\$?\s?(\d{2,3})(?:,\d{3}|k)", re.I)


def _match_dictionary(text: str, dictionary: dict[str, list[str]]) -> list[str]:
    lowered = text.lower()
    hits: list[str] = []
    for canonical, aliases in dictionary.items():
        for alias in aliases:
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lowered):
                hits.append(canonical)
                break
    return sorted(set(hits))


def find_skills(text: str) -> list[str]:
    return _match_dictionary(text, SKILLS)


def find_technologies(text: str) -> list[str]:
    return _match_dictionary(text, TECHNOLOGIES)


def find_roles(text: str) -> list[str]:
    return _match_dictionary(text, ROLES)


def find_seniority(text: str) -> str:
    lowered = text.lower()
    for label, pattern in SENIORITY_PATTERNS:
        if re.search(pattern, lowered):
            return label
    return "unknown"


def find_remote_type(text: str) -> str:
    lowered = text.lower()
    for label, pattern in REMOTE_PATTERNS:
        if re.search(pattern, lowered):
            return label
    return "unknown"


def find_salary(text: str) -> tuple[float | None, float | None]:
    match = SALARY_RE.search(text)
    if not match:
        return None, None
    low = float(match.group(1)) * 1000
    high = float(match.group(2)) * 1000
    return (low, high) if high >= low else (high, low)


def normalize_role(title: str) -> str:
    roles = find_roles(title)
    return roles[0] if roles else "other"
