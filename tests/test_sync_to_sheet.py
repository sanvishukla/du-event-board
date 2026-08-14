import json
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from sync_to_sheet import (
    get_sheet_field,
    create_full_payload,
    format_boolean,
    format_featured,
    get_derived_category,
)


def test_get_sheet_field():
    """Test get_sheet_field retrieves values using aliases."""
    s_ev_new = {
        "Event Name": "AI Summit",
        "Start Date": "2026-12-01",
        "Location": "Boston, MA",
    }
    assert get_sheet_field(s_ev_new, "event_name") == "AI Summit"
    assert get_sheet_field(s_ev_new, "start_date") == "2026-12-01"
    assert get_sheet_field(s_ev_new, "location") == "Boston, MA"

    s_ev_old = {
        "event_name": "AI Summit Legacy",
        "start_date": "2026-12-02",
        "location": "Boston",
    }
    assert get_sheet_field(s_ev_old, "event_name") == "AI Summit Legacy"
    assert get_sheet_field(s_ev_old, "start_date") == "2026-12-02"
    assert get_sheet_field(s_ev_old, "location") == "Boston"


def test_format_boolean_and_featured():
    """Test boolean and featured formatters."""
    assert format_boolean(True) == "Yes"
    assert format_boolean(False) == "No"
    assert format_boolean("true") == "Yes"
    assert format_boolean("false") == "No"
    assert format_boolean("") == ""

    assert format_featured(True) == "1"
    assert format_featured(False) == "0"
    assert format_featured("yes") == "1"
    assert format_featured("no") == "0"
    assert format_featured("") == "0"


def test_get_derived_category():
    """Test get_derived_category logic."""
    assert get_derived_category(True, True) == "hybrid"
    assert get_derived_category(True, False) == "in-person"
    assert get_derived_category(False, True) == "online"
    assert get_derived_category(False, False) == ""


def test_create_full_payload():
    """Test create_full_payload outputs both legacy keys and new form header aliases."""
    event = {
        "id": "20261010001",
        "title": "Global Tech Expo",
        "date": "2026-11-15",
        "time": "10:00",
        "end_date": "2026-11-17",
        "end_time": "18:00",
        "category": "Exhibition",
        "description": "Annual tech expo.",
        "location": "Las Vegas, NV, USA",
        "region": "North America",
        "city": "Las Vegas",
        "state-province": "NV",
        "country": "USA",
        "tags": ["tech", "expo"],
        "organization_name": "Expo Org",
        "acronym": "EO",
        "organization_url": "https://expo.example.com",
        "url_linkedin": "https://linkedin.com/company/expo",
        "url_twitter": "https://twitter.com/expo",
        "url_other": "https://contact.expo.example.com",
        "paid_or_free": "paid",
        "url": "https://register.expo.example.com",
        "image_url": "https://expo.example.com/banner.png",
        "in_person": True,
        "virtual": False,
        "featured": True,
        "language": "English",
    }

    payload = create_full_payload(event)

    # Check ID
    assert payload["id"] == "20261010001"

    # Check legacy keys
    assert payload["event_name"] == "Global Tech Expo"
    assert payload["start_date"] == "2026-11-15"
    assert payload["start_time"] == "10:00"
    assert payload["end_date"] == "2026-11-17"
    assert payload["end_time"] == "18:00"
    assert payload["event_type"] == "Exhibition"
    assert payload["featured"] == "1"

    # Check new Google Form header aliases
    assert payload["Event Name"] == "Global Tech Expo"
    assert payload["Start Date"] == "2026-11-15"
    assert payload["Start Time"] == "10:00"
    assert payload["End Date"] == "2026-11-17"
    assert payload["End Time"] == "18:00"
    assert payload["Event Type (Conference, Workshop, Webinar, etc.)"] == "Exhibition"
    assert payload["Featured?"] == "1"
    assert payload["Relevant Tags (Separated by commas)"] == "tech, expo"
    assert payload["Organization Name"] == "Expo Org"
    assert payload["Organization Acronym"] == "EO"
    assert payload["Official Organization Website URL"] == "https://expo.example.com"
    assert payload["LinkedIn Profile URL for Organization"] == "https://linkedin.com/company/expo"
    assert payload["Twitter/X Profile URL for Organization"] == "https://twitter.com/expo"
    assert payload["Other Social Media/Contact URL"] == "https://contact.expo.example.com"
    assert payload["Is the Event Paid or Free?"] == "paid"
    assert payload["Official Event Registration/Information URL"] == "https://register.expo.example.com"
    assert payload["Event Image/Logo URL (Must be publicly accessible)"] == "https://expo.example.com/banner.png"
    assert payload["In-Person?"] == "Yes"
    assert payload["Virtual?"] == "No"
    assert payload["Location"] == "Las Vegas, NV, USA"
    assert payload["City"] == "Las Vegas"
    assert payload["State/Province"] == "NV"
    assert payload["Country"] == "USA"
    assert payload["Region"] == "North America"
    assert payload["Primary Language of the Event"] == "English"
