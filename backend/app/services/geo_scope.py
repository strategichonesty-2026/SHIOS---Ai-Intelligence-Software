"""US-only, English-language scoping for job postings.

Rule-based on purpose: the job source APIs this system pulls from (Jobicy, We Work
Remotely, Arbeitnow) don't offer a documented country+language request parameter between
them, so scoping happens by inspecting each posting's free-text location (and, as a
fallback signal, its title) after collection. Deliberately simple regex matching rather
than a language-detection library — the inputs are short job titles/locations, not prose,
and every decision here should be readable in a diff, matching the "statistics first, no
guessing" rule the rest of the trend/prediction pipeline follows.
"""

from __future__ import annotations

import re

# Order matters: non-US markers are checked first, so "Berlin (remote, open to EU)"
# is excluded even though it also contains no explicit US marker.
_NON_US_LOCATION_MARKERS = re.compile(
    r"\b("
    r"germany|deutschland|berlin|munich|münchen|stuttgart|hamburg|frankfurt|cologne|köln|leipzig|"
    r"united kingdom|\buk\b|london|manchester|"
    r"india|bangalore|bengaluru|mumbai|hyderabad|delhi|pune|"
    r"canada|toronto|vancouver|montreal|"
    r"ireland|dublin|netherlands|amsterdam|france|paris|spain|madrid|barcelona|"
    r"poland|warsaw|portugal|lisbon|italy|milan|rome|"
    r"australia|sydney|melbourne|singapore|philippines|manila|"
    r"mexico|brazil|são paulo|sao paulo|japan|tokyo|china|beijing|shanghai"
    r")\b",
    re.I,
)

_US_LOCATION_MARKERS = re.compile(
    r"\b("
    r"united states|usa|u\.s\.a?\.?|"
    r"alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|"
    r"georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|"
    r"massachusetts|michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|"
    r"new hampshire|new jersey|new mexico|new york|north carolina|north dakota|ohio|"
    r"oklahoma|oregon|pennsylvania|rhode island|south carolina|south dakota|tennessee|"
    r"texas|utah|vermont|virginia|washington|west virginia|wisconsin|wyoming|"
    r"san francisco|new york city|nyc|austin|seattle|boston|chicago|denver|atlanta"
    r")\b",
    re.I,
)

# WWR-style "anywhere/worldwide" remote postings carry no country restriction, so they're
# open to US applicants by construction — treated as in-scope unless a non-US marker
# elsewhere (often only in the title, e.g. "Based in Bangalore") says otherwise.
_UNRESTRICTED_REMOTE = re.compile(r"\b(anywhere|worldwide|global|remote)\b", re.I)

_GERMAN_LANGUAGE_MARKERS = re.compile(
    r"[äöüÄÖÜß]|\b(wir suchen|erfahrung|kenntnisse|unternehmen|mitarbeiter|bewerbung|"
    r"vollzeit|teilzeit|unbefristet|gehalt|standort|arbeitsort)\b",
    re.I,
)


def is_us_scoped_location(location: str, title: str = "") -> bool:
    """True if a posting's location (with title as a fallback signal) indicates the US."""
    combined = f"{location} {title}"
    if _NON_US_LOCATION_MARKERS.search(combined):
        return False
    if _US_LOCATION_MARKERS.search(location):
        return True
    if not location.strip() or _UNRESTRICTED_REMOTE.search(location):
        return True
    return False


def is_english_language(text: str) -> bool:
    """True unless the text trips the (small, explicit) German-language heuristic.

    Only German is checked because it's the concrete case observed in production
    (Arbeitnow mixes German-market listings into the feed); extend the marker list if
    another non-English source is added.
    """
    return not _GERMAN_LANGUAGE_MARKERS.search(text)
