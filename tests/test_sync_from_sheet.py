import json
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from sync_from_sheet import (
    FIELD_MAPPING,
    get_field_value,
    normalize_time,
    parse_location_parts,
    clean_boolean,
    clean_tags,
)


def test_get_field_value_case_insensitive_and_aliases():
    """Test get_field_value resolves candidate field names correctly."""
    sheet_event = {
        "Event Name": "PyCon 2026",
        "Start Date": "2026-11-01",
        "Start Time": "09:00:00 AM",
        "End Date": "2026-11-03",
        "End Time": "05:00:00 PM",
        "Location": "San Francisco, CA, USA",
        "Primary Language of the Event": "English",
        "Is the Event Paid or Free?": "Free",
        "Organization Name": "Python Foundation",
        "Organization Acronym": "PSF",
    }

    assert get_field_value(sheet_event, "title") == "PyCon 2026"
    assert get_field_value(sheet_event, "date") == "2026-11-01"
    assert get_field_value(sheet_event, "time") == "09:00:00 AM"
    assert get_field_value(sheet_event, "end_date") == "2026-11-03"
    assert get_field_value(sheet_event, "end_time") == "05:00:00 PM"
    assert get_field_value(sheet_event, "location") == "San Francisco, CA, USA"
    assert get_field_value(sheet_event, "language") == "English"
    assert get_field_value(sheet_event, "paid_or_free") == "Free"
    assert get_field_value(sheet_event, "organization_name") == "Python Foundation"
    assert get_field_value(sheet_event, "acronym") == "PSF"


def test_normalize_time():
    """Test normalize_time with 12-hour AM/PM and 24-hour time strings."""
    assert normalize_time("12:00:00 AM") == "00:00"
    assert normalize_time("09:30:00 AM") == "09:30"
    assert normalize_time("12:00:00 PM") == "12:00"
    assert normalize_time("05:30:00 PM") == "17:30"
    assert normalize_time("14:30") == "14:30"
    assert normalize_time("14:30:00") == "14:30"
    assert normalize_time("") == ""


def test_parse_location_parts():
    """Test parse_location_parts extracts city, state, country from location string."""
    city, state, country = parse_location_parts("Online")
    assert (city, state, country) == ("", "", "")

    city, state, country = parse_location_parts("San Francisco, CA, USA")
    assert city == "San Francisco"
    assert state == "CA"
    assert country == "USA"

    city, state, country = parse_location_parts("London, UK")
    assert city == "London"
    assert state == ""
    assert country == "UK"

    city, state, country = parse_location_parts("Paris")
    assert city == "Paris"
    assert state == ""
    assert country == ""
