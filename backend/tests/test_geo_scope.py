"""Tests for US-only / English-language job scoping, using real location strings
observed from Jobicy, We Work Remotely and Arbeitnow."""

from __future__ import annotations

from app.services.geo_scope import is_english_language, is_us_scoped_location


def test_explicit_us_locations_are_in_scope():
    assert is_us_scoped_location("USA")
    assert is_us_scoped_location("United States")
    assert is_us_scoped_location("Austin, TX")
    assert is_us_scoped_location("Remote (US)")


def test_german_locations_are_out_of_scope():
    assert not is_us_scoped_location("Munich")
    assert not is_us_scoped_location("Berlin")
    assert not is_us_scoped_location("Germany")
    assert not is_us_scoped_location("Berlin - hybrid")
    assert not is_us_scoped_location("Stuttgart Schockenriedstr. 17")


def test_unrestricted_remote_is_in_scope_by_default():
    assert is_us_scoped_location("Anywhere in the World")
    assert is_us_scoped_location("Remote")
    assert is_us_scoped_location("")


def test_title_can_override_an_unrestricted_remote_location():
    # Real We Work Remotely case: region says "Anywhere in the World" but the title
    # names a specific non-US city.
    assert not is_us_scoped_location(
        "Anywhere in the World", title="Cloudflare: Principal Partner Solutions Engineer, SAARC (Based in Bangalore)"
    )


def test_other_non_us_countries_are_out_of_scope():
    for location in ["India", "United Kingdom", "London", "Canada", "Toronto", "Singapore"]:
        assert not is_us_scoped_location(location), location


def test_english_text_passes():
    assert is_english_language("We are hiring a Senior Software Engineer to join our team.")


def test_german_text_is_flagged():
    assert not is_english_language("Wir suchen einen Mitarbeiter mit Erfahrung in Vollzeit.")
    assert not is_english_language("Erfahrung mit Kenntnisse gewünscht")
